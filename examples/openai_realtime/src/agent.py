"""
OpenAI Realtime API Agent with Thymia Sentinel.

Streams microphone audio to OpenAI's Realtime API for the conversation, and
to Thymia Sentinel for biomarker analysis. When Sentinel flags elevated
signals, the recommended action is injected into the OpenAI session as a
priority conversation item.

All terminal display, logging, and user prompts live in display.py to keep
this file focused on the integration logic.

Run with: uv run python src/agent.py
Prerequisites: brew install portaudio (macOS) / apt-get install portaudio19-dev
"""
import asyncio
import base64
import json
import os
from dotenv import load_dotenv

load_dotenv(".env.local")

import pyaudio
import websockets
from loguru import logger

from thymia_sentinel import SentinelClient, PolicyResult, ProgressResult
from prompts import SYSTEM_PROMPT, format_action_message
from display import (
    configure_logging,
    is_valid_user_transcript,
    log_agent_transcript,
    log_audio_device,
    log_policy,
    log_progress,
    log_startup,
    log_user_profile,
    log_user_transcript,
    prompt_user_profile,
)

configure_logging()


# --- Audio config ------------------------------------------------------------
FORMAT = pyaudio.paInt16
CHANNELS = 1
SAMPLE_RATE = 24000
CHUNK_SIZE = 1024


# --- OpenAI Realtime config --------------------------------------------------
MODEL = "gpt-realtime-2"
WS_URL = f"wss://api.openai.com/v1/realtime?model={MODEL}"
VOICE = "marin"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")


# --- Behaviour ---------------------------------------------------------------
# When False, the mic is muted while the agent is speaking — use this when
# playing the agent through laptop/external speakers without echo cancellation,
# otherwise the agent's own voice loops back and triggers a self-interruption.
ALLOW_INTERRUPTION = os.getenv("ALLOW_INTERRUPTION", "true").lower() != "false"
PLAYBACK_TAIL_GRACE_SECS = 0.5  # mic stays muted this long after agent stops


# --- Globals -----------------------------------------------------------------
pya = pyaudio.PyAudio()
audio_queue_output: asyncio.Queue = asyncio.Queue()
audio_queue_mic: asyncio.Queue = asyncio.Queue(maxsize=5)
audio_stream = None

sentinel: SentinelClient | None = None
realtime_ws: websockets.ClientConnection | None = None
agent_speaking: bool = False  # True while OpenAI is streaming audio to us


# --- Audio loop tasks --------------------------------------------------------

async def listen_audio() -> None:
    """Capture mic audio. Forward to OpenAI and Sentinel."""
    global audio_stream
    mic_info = pya.get_default_input_device_info()
    log_audio_device("mic", mic_info["name"])
    audio_stream = await asyncio.to_thread(
        pya.open,
        format=FORMAT,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        input_device_index=mic_info["index"],
        frames_per_buffer=CHUNK_SIZE,
    )
    while True:
        data = await asyncio.to_thread(
            audio_stream.read, CHUNK_SIZE, exception_on_overflow=False
        )
        # Half-duplex: drop mic audio while the agent is speaking so its own
        # voice (leaking via speakers) can't trigger a false interruption.
        if not ALLOW_INTERRUPTION and agent_speaking:
            continue
        await audio_queue_mic.put(data)
        await sentinel.send_user_audio(data)


async def send_realtime() -> None:
    """Forward queued mic audio to the OpenAI WebSocket as base64 PCM16."""
    while True:
        chunk = await audio_queue_mic.get()
        await realtime_ws.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(chunk).decode("ascii"),
        }))


async def play_audio() -> None:
    """Drain the speaker queue to the output device."""
    speaker_info = pya.get_default_output_device_info()
    log_audio_device("out", speaker_info["name"])
    stream = await asyncio.to_thread(
        pya.open,
        format=FORMAT,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        output=True,
    )
    while True:
        bytestream = await audio_queue_output.get()
        await asyncio.to_thread(stream.write, bytestream)


# --- OpenAI event handling ---------------------------------------------------

async def receive_events() -> None:
    """Receive Realtime events from OpenAI and dispatch to speakers + Sentinel."""
    global agent_speaking

    user_buffer: list[str] = []
    agent_buffer: list[str] = []

    async def flush_user(log: bool = True) -> None:
        if not user_buffer:
            return
        text = "".join(user_buffer).strip()
        user_buffer.clear()
        if not is_valid_user_transcript(text):
            return
        if log:
            log_user_transcript(text)
        await sentinel.send_user_transcript(text)

    async def flush_agent(log: bool = True) -> None:
        if not agent_buffer:
            return
        text = "".join(agent_buffer).strip()
        agent_buffer.clear()
        if not text:
            return
        if log:
            log_agent_transcript(text)
        await sentinel.send_agent_transcript(text)

    async for raw in realtime_ws:
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        etype = event.get("type", "")

        if etype == "response.output_audio.delta":
            agent_speaking = True
            pcm = base64.b64decode(event.get("delta", ""))
            if pcm:
                audio_queue_output.put_nowait(pcm)
                await sentinel.send_agent_audio(pcm)

        elif etype == "response.output_audio_transcript.delta":
            agent_speaking = True
            delta = event.get("delta", "")
            if delta:
                agent_buffer.append(delta)

        elif etype == "response.output_audio_transcript.done":
            # Don't flip agent_speaking yet — audio is still playing through
            # speakers. We wait for response.done + queue drain instead.
            await flush_agent()

        elif etype == "conversation.item.input_audio_transcription.completed":
            transcript = (event.get("transcript") or "").strip()
            if transcript and not user_buffer and is_valid_user_transcript(transcript):
                log_user_transcript(transcript)
                await sentinel.send_user_transcript(transcript)
            else:
                await flush_user()

        elif etype == "input_audio_buffer.speech_started":
            # User interrupted (or echo did). Drop pending playback. Forward
            # the partial agent transcript silently — the .done event will
            # log the final version.
            agent_speaking = False
            while not audio_queue_output.empty():
                audio_queue_output.get_nowait()
            await flush_agent(log=False)

        elif etype == "response.done":
            await flush_user()
            await flush_agent()
            asyncio.create_task(_release_after_playback())

        elif etype == "error":
            logger.error(f"OpenAI error: {event}")


async def _release_after_playback() -> None:
    """Hold agent_speaking=True until the speaker queue has drained.

    The transcript and final response events arrive *before* the audio has
    finished playing through speakers. Flipping agent_speaking off too early
    re-engages the mic while the speaker tail is still emitting, which leaks
    back in and self-interrupts. Waiting for the queue + a small grace fixes it.
    """
    global agent_speaking
    while not audio_queue_output.empty():
        await asyncio.sleep(0.05)
    await asyncio.sleep(PLAYBACK_TAIL_GRACE_SECS)
    agent_speaking = False


# --- Sentinel safety hint injection ------------------------------------------

async def apply_recommended_action(action: str, concerns: list[str] | None = None) -> None:
    """Inject a Sentinel-recommended action into the OpenAI session.

    Sent as a `conversation.item.create` user message so the model picks it up
    on the next response. We deliberately do NOT call response.create here —
    server VAD races with the policy callback and a manual response.create
    collides with the in-flight response.
    """
    if not realtime_ws:
        return
    await realtime_ws.send(json.dumps({
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [{
                "type": "input_text",
                "text": format_action_message(action, concerns),
            }],
        },
    }))


# --- Main --------------------------------------------------------------------

async def run() -> None:
    global sentinel, realtime_ws

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set in environment")

    dob, birth_sex = prompt_user_profile()
    log_user_profile(dob, birth_sex)

    async def handle_policy_result(result: PolicyResult) -> None:
        log_policy(result)
        inner = result.get("result", {})
        if inner.get("type") == "safety_analysis":
            for_agent = (inner.get("recommended_actions") or {}).get("for_agent", "")
            concerns = list(inner.get("concerns") or [])
            if for_agent:
                await apply_recommended_action(for_agent, concerns)

    async def handle_progress_result(result: ProgressResult) -> None:
        log_progress(result.get("biomarkers", {}), agent_speaking=agent_speaking)

    sentinel = SentinelClient(
        date_of_birth=dob,
        birth_sex=birth_sex,
        language="en-GB",
        sample_rate=SAMPLE_RATE,
        on_policy_result=handle_policy_result,
        on_progress_result=handle_progress_result,
        policies=["demo_wellbeing_awareness"],
        biomarkers=["helios"],
    )

    try:
        await sentinel.connect()

        async with websockets.connect(
            WS_URL,
            additional_headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            max_size=None,
        ) as ws:
            realtime_ws = ws
            log_startup(
                MODEL, SAMPLE_RATE, VOICE, ALLOW_INTERRUPTION,
                sentinel.policies, sentinel.biomarkers,
            )

            await ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "model": MODEL,
                    "reasoning": {"effort": "low"},
                    "instructions": SYSTEM_PROMPT,
                    "audio": {
                        "input": {
                            "format": {"type": "audio/pcm", "rate": SAMPLE_RATE},
                            "transcription": {"model": "whisper-1"},
                            # Semantic VAD is better at ignoring agent audio
                            # leaking back into the mic than a level-based VAD.
                            "turn_detection": {
                                "type": "semantic_vad",
                                "eagerness": "auto",
                            },
                        },
                        "output": {
                            "format": {"type": "audio/pcm", "rate": SAMPLE_RATE},
                            "voice": VOICE,
                        },
                    },
                },
            }))

            await ws.send(json.dumps({
                "type": "response.create",
                "response": {
                    "instructions": (
                        "Greet the user in EXACTLY two short sentences and then stop. "
                        "Sentence one: a warm hello, identify yourself simply as their "
                        "coach for today, and acknowledge that something is coming up. "
                        "Sentence two: invite them to share what it is — one open question. "
                        "Do not add a follow-up. Do not list capabilities. Stop after the question."
                    ),
                },
            }))

            async with asyncio.TaskGroup() as tg:
                tg.create_task(listen_audio())
                tg.create_task(send_realtime())
                tg.create_task(receive_events())
                tg.create_task(play_audio())

    except asyncio.CancelledError:
        pass
    finally:
        if sentinel:
            await sentinel.close()
        if audio_stream:
            audio_stream.close()
        pya.terminate()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
