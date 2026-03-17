"""
Gemini Live API Agent with Thymia Sentinel

A voice agent using Google's Gemini Live API with real-time biomarker monitoring via Thymia Sentinel.
"""
import asyncio
import sys
import os
from dotenv import load_dotenv

load_dotenv(".env.local")

from google import genai
import pyaudio

from loguru import logger

# Logging configuration
logger.remove()
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"))


from thymia_sentinel import SentinelClient, PolicyResult, ProgressResult
from prompts import SYSTEM_PROMPT, format_action_message

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# --- pyaudio config ---
FORMAT = pyaudio.paInt16
CHANNELS = 1
SAMPLE_RATE = 24000
CHUNK_SIZE = 1024

pya = pyaudio.PyAudio()

# --- Live API config ---
MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
CONFIG = {
    "response_modalities": ["AUDIO"],
    "system_instruction": SYSTEM_PROMPT,
    "input_audio_transcription": {},
    "output_audio_transcription": {},
}

audio_queue_output = asyncio.Queue()
audio_queue_mic = asyncio.Queue(maxsize=5)
audio_stream = None

# Global sentinel reference
sentinel: SentinelClient = None
# Global session reference for context updates
live_session = None


async def apply_recommended_action(action: str) -> None:
    """Apply a recommended action by injecting guidance into the Gemini session."""
    global live_session

    if not live_session:
        logger.warning("Cannot apply action - no active session")
        return

    logger.info("=" * 60)
    logger.info("APPLYING RECOMMENDED ACTION")
    logger.info(f"Action: {action}")
    logger.info("=" * 60)

    # Inject just the action as context (system prompt is already set)
    action_message = format_action_message(action)

    try:
        await live_session.send_client_content(
            turns=[{"role": "user", "parts": [{"text": action_message}]}],
            turn_complete=True,
        )
        logger.info("Action injected into Gemini session")
    except Exception as e:
        logger.error(f"Failed to inject action: {e}")


async def listen_audio():
    """Listens for audio and puts it into the mic audio queue."""
    global audio_stream
    mic_info = pya.get_default_input_device_info()
    logger.info(f"Using microphone: {mic_info['name']}")
    audio_stream = await asyncio.to_thread(
        pya.open,
        format=FORMAT,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        input_device_index=mic_info["index"],
        frames_per_buffer=CHUNK_SIZE,
    )
    kwargs = {"exception_on_overflow": False} if __debug__ else {}
    while True:
        data = await asyncio.to_thread(audio_stream.read, CHUNK_SIZE, **kwargs)

        # Send to Gemini
        await audio_queue_mic.put({
            "data": data,
            "mime_type": "audio/pcm"
        })

        await sentinel.send_user_audio(data)


async def send_realtime(session):
    """Sends audio from the mic audio queue to the GenAI session."""
    while True:
        msg = await audio_queue_mic.get()
        try:
            await session.send_realtime_input(audio=msg)
        except Exception as e:
            logger.error(f"Error sending audio to Gemini: {e}")


async def receive_audio(session):
    """Receives responses from GenAI and puts audio data into the speaker audio queue."""
    user_transcript_buffer = []
    agent_transcript_buffer = []

    async def flush_user():
        if user_transcript_buffer:
            await sentinel.send_user_transcript(''.join(user_transcript_buffer))
            user_transcript_buffer.clear()

    async def flush_agent():
        if agent_transcript_buffer:
            await sentinel.send_agent_transcript(''.join(agent_transcript_buffer))
            agent_transcript_buffer.clear()

    while True:
        async for response in session.receive():
            sc = response.server_content
            if not sc:
                continue

            if sc.input_transcription and sc.input_transcription.text:
                user_transcript_buffer.append(sc.input_transcription.text)

            if sc.output_transcription and sc.output_transcription.text:
                await flush_user()
                agent_transcript_buffer.append(sc.output_transcription.text)

            if sc.model_turn:
                for part in sc.model_turn.parts:
                    if part.inline_data and isinstance(part.inline_data.data, bytes):
                        audio_queue_output.put_nowait(part.inline_data.data)
                        await sentinel.send_agent_audio(part.inline_data.data)

            if sc.turn_complete:
                await flush_user()
                await flush_agent()

            if sc.interrupted:
                await flush_agent()
                while not audio_queue_output.empty():
                    audio_queue_output.get_nowait()


async def play_audio():
    """Plays audio from the speaker audio queue."""
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


async def run():
    """Main function to run the audio loop."""
    global sentinel

    try:
        # Initialize Sentinel
        async def handle_policy_result(result: PolicyResult):
            policy = result.get('policy', 'unknown')
            policy_name = result.get('policy_name', policy)
            inner_result = result.get('result', {})
            result_type = inner_result.get('type', 'unknown')

            logger.info(f"Policy [{policy_name}] (executor={policy}): type={result_type}")

            # Handle safety policy results
            if result_type == 'safety_analysis':
                classification = inner_result.get('classification', {})
                concerns = inner_result.get('concerns', [])
                level = classification.get('level', 0)
                alert = classification.get('alert', 'none')
                logger.info(f"Sentinel: level={level} alert={alert}")
                if concerns:
                    logger.info(f"   Concerns: {concerns}")

                actions = inner_result.get('recommended_actions', {})
                for_agent = actions.get('for_agent', '')
                if for_agent:
                    await apply_recommended_action(for_agent)

            # Handle field extraction results
            elif result_type == 'extracted_fields':
                fields = inner_result.get('fields', {})
                extracted = {k: v.get('value') for k, v in fields.items() if v.get('value') is not None}
                if extracted:
                    logger.info(f"   Extracted: {extracted}")

        async def handle_progress_result(result: ProgressResult):
            timestamp = result.get('timestamp', 0.0)
            biomarkers = result.get('biomarkers', {})
            logger.info(f"Progress at {timestamp}: biomarkers={biomarkers}")

        sentinel = SentinelClient(
            user_label="550e8400-e29b-41d4-a716-446655440000",
            language="en-GB",
            sample_rate=SAMPLE_RATE,  # Gemini uses 24kHz
            on_policy_result=handle_policy_result,
            policies=["demo_wellbeing_awareness"],  # ["demo_wellbeing_awareness", "demo_field_extraction"]
            biomarkers=["helios"],  # ["helios", "apollo", "psyche"]
            on_progress_result=handle_progress_result,
        )

        # Connect to Thymia server
        await sentinel.connect()

        async with client.aio.live.connect(
            model=MODEL, config=CONFIG
        ) as session:
            global live_session
            live_session = session
            logger.info("Connected to Gemini!")

            # Send initial greeting
            await session.send_client_content(
                turns=[{"role": "user", "parts": [{"text": "Say hello and introduce yourself briefly."}]}],
                turn_complete=True,
            )

            async with asyncio.TaskGroup() as tg:
                tg.create_task(send_realtime(session))
                tg.create_task(listen_audio())
                tg.create_task(receive_audio(session))
                tg.create_task(play_audio())

    except asyncio.CancelledError:
        pass
    finally:
        if sentinel:
            await sentinel.close()
        if audio_stream:
            audio_stream.close()
        pya.terminate()
        logger.info("\nConnection closed.")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")