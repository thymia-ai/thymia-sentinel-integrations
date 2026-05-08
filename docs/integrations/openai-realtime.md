# OpenAI Realtime Integration

The OpenAI Realtime integration shows how to use Sentinel with OpenAI's `gpt-realtime-2` model over a raw WebSocket for real-time voice conversations.

## Installation

```bash
cd examples/openai_realtime
uv sync

# On macOS, you also need:
brew install portaudio

# On Debian / Ubuntu:
sudo apt-get install portaudio19-dev
```

## Quick Start

```python
import websockets
from thymia_sentinel import SentinelClient

SAMPLE_RATE = 24000  # OpenAI Realtime uses 24kHz

async def run():
    sentinel = SentinelClient(
        sample_rate=SAMPLE_RATE,
        policies=["demo_wellbeing_awareness"],
        biomarkers=["helios"],
        on_policy_result=handle_policy_result,
    )

    await sentinel.connect()

    async with websockets.connect(
        f"wss://api.openai.com/v1/realtime?model=gpt-realtime-2",
        additional_headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        max_size=None,
    ) as ws:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(listen_audio(ws, sentinel))
            tg.create_task(receive_events(ws, sentinel))
            tg.create_task(play_audio())

    await sentinel.close()
```

## Audio Configuration

OpenAI's Realtime API uses 24kHz PCM16 mono in both directions. Configure Sentinel to match:

```python
SAMPLE_RATE = 24000

sentinel = SentinelClient(
    sample_rate=SAMPLE_RATE,  # Match the Realtime API's rate
    # ...
)
```

## Capturing Audio

Mic audio is base64-encoded for the OpenAI WebSocket and forked as raw PCM into Sentinel:

```python
import base64

async def listen_audio(ws, sentinel):
    audio_stream = pya.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
    )

    while True:
        pcm = await asyncio.to_thread(audio_stream.read, CHUNK_SIZE)

        # Send to OpenAI as base64
        await ws.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(pcm).decode("ascii"),
        }))

        # Send to Sentinel as raw PCM
        await sentinel.send_user_audio(pcm)
```

## Capturing Transcripts

OpenAI emits separate events for input and output transcription:

```python
async def receive_events(ws, sentinel):
    user_buffer = []
    agent_buffer = []

    async for raw in ws:
        event = json.loads(raw)
        etype = event.get("type", "")

        # Agent audio
        if etype == "response.output_audio.delta":
            pcm = base64.b64decode(event["delta"])
            speaker_queue.put_nowait(pcm)
            await sentinel.send_agent_audio(pcm)

        # Agent transcript (streamed)
        elif etype == "response.output_audio_transcript.delta":
            agent_buffer.append(event["delta"])

        elif etype == "response.output_audio_transcript.done":
            await sentinel.send_agent_transcript("".join(agent_buffer))
            agent_buffer.clear()

        # User transcript (final)
        elif etype == "conversation.item.input_audio_transcription.completed":
            await sentinel.send_user_transcript(event["transcript"])
```

## Injecting Safety Actions

Append the recommended action as a `conversation.item.create` user message. **Do not** call `response.create` afterwards — server VAD auto-creates a response on user-speech-end, and a manual call collides with the in-flight response (`conversation_already_has_active_response`). The appended item is picked up by whichever response generates next:

```python
async def apply_recommended_action(action: str, ws):
    await ws.send(json.dumps({
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": f"[SAFETY HINT]: {action}"}],
        },
    }))
```

## OpenAI Realtime Configuration

```python
MODEL = "gpt-realtime-2"

await ws.send(json.dumps({
    "type": "session.update",
    "session": {
        "type": "realtime",
        "model": MODEL,
        "reasoning": {"effort": "low"},  # recommended for production voice agents
        "instructions": SYSTEM_PROMPT,
        "audio": {
            "input": {
                "format": {"type": "audio/pcm", "rate": 24000},
                "transcription": {"model": "whisper-1"},
                # Semantic VAD lets the model decide if audio is meaningful
                # speech rather than just "loud enough" - much better at
                # ignoring agent audio leaking back into the mic than a
                # level-based VAD.
                "turn_detection": {"type": "semantic_vad", "eagerness": "auto"},
            },
            "output": {
                "format": {"type": "audio/pcm", "rate": 24000},
                "voice": "marin",
            },
        },
    },
}))
```

## Half-Duplex for Speaker Demos

If you have to play the agent through laptop or external speakers (e.g. a live demo without headphones), the agent's own voice will leak into the mic and trigger a self-interruption loop. The example provides an `ALLOW_INTERRUPTION=false` env flag that switches to half-duplex — muting the mic while the agent is speaking, plus a small grace period for the speaker queue to drain:

```python
ALLOW_INTERRUPTION = os.getenv("ALLOW_INTERRUPTION", "true").lower() != "false"

async def listen_audio(ws, sentinel):
    while True:
        data = await asyncio.to_thread(audio_stream.read, CHUNK_SIZE)
        if not ALLOW_INTERRUPTION and agent_speaking:
            continue  # Drop mic audio while agent speaks
        await ws.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(data).decode("ascii"),
        }))
        await sentinel.send_user_audio(data)
```

Use headphones (full-duplex) for normal development, half-duplex for stage demos.

## Environment Variables

```bash
THYMIA_API_KEY=your-api-key
OPENAI_API_KEY=your-openai-key

# Optional
ALLOW_INTERRUPTION=true        # set "false" for laptop-speaker demos
THYMIA_DOB=1997-11-18          # bypass the DOB prompt
THYMIA_BIRTH_SEX=MALE          # bypass the birth-sex prompt
LOG_LEVEL=INFO                 # set DEBUG for verbose Sentinel SDK logging
WRAP_WIDTH=110                 # log word-wrap width (0 disables)
```

## Running the Example

```bash
cd examples/openai_realtime
cp .env.example .env.local
# Edit .env.local with your API keys

uv run python src/agent.py
```

The example will prompt for date of birth and birth sex (press Enter for defaults, type `skip` to omit), then start a voice conversation using your microphone and speakers.
