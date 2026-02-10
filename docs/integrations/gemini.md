# Gemini Live Integration

The Gemini Live integration shows how to use Sentinel with Google's Gemini Live API for real-time voice conversations.

## Installation

```bash
cd examples/gemini_live
uv sync

# On macOS, you also need:
brew install portaudio
```

## Quick Start

```python
from google import genai
from thymia_sentinel import SentinelClient

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

async def run():
    sentinel = SentinelClient(
        user_label="user-123",
        sample_rate=24000,  # Gemini uses 24kHz
        policies=["safety"],
        on_policy_result=handle_policy_result,
    )

    await sentinel.connect()

    async with client.aio.live.connect(model=MODEL, config=CONFIG) as session:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(listen_audio(sentinel))
            tg.create_task(send_realtime(session))
            tg.create_task(receive_audio(session, sentinel))
            tg.create_task(play_audio())

    await sentinel.close()
```

## Audio Configuration

Gemini Live uses 24kHz sample rate. Configure Sentinel to match:

```python
SAMPLE_RATE = 24000

sentinel = SentinelClient(
    sample_rate=SAMPLE_RATE,  # Match Gemini's rate
    # ...
)
```

## Capturing Audio

```python
async def listen_audio(sentinel):
    """Capture microphone and send to both Gemini and Sentinel."""
    audio_stream = pya.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
    )

    while True:
        data = await asyncio.to_thread(audio_stream.read, CHUNK_SIZE)

        # Send to Gemini queue
        await audio_queue_mic.put({"data": data, "mime_type": "audio/pcm"})

        # Send to Sentinel
        await sentinel.send_user_audio(data)
```

## Capturing Transcripts

Gemini provides input and output transcriptions:

```python
async def receive_audio(session, sentinel):
    user_buffer = []
    agent_buffer = []

    async for response in session.receive():
        sc = response.server_content
        if not sc:
            continue

        # User transcript (input transcription)
        if sc.input_transcription and sc.input_transcription.text:
            user_buffer.append(sc.input_transcription.text)

        # Agent transcript (output transcription)
        if sc.output_transcription and sc.output_transcription.text:
            # Flush user transcript first
            if user_buffer:
                await sentinel.send_user_transcript("".join(user_buffer))
                user_buffer.clear()
            agent_buffer.append(sc.output_transcription.text)

        # Agent audio
        if sc.model_turn:
            for part in sc.model_turn.parts:
                if part.inline_data and isinstance(part.inline_data.data, bytes):
                    await sentinel.send_agent_audio(part.inline_data.data)

        # Turn complete - flush buffers
        if sc.turn_complete:
            if user_buffer:
                await sentinel.send_user_transcript("".join(user_buffer))
                user_buffer.clear()
            if agent_buffer:
                await sentinel.send_agent_transcript("".join(agent_buffer))
                agent_buffer.clear()
```

## Injecting Safety Actions

Inject actions as user turns:

```python
async def apply_recommended_action(action: str, session):
    await session.send_client_content(
        turns=[{
            "role": "user",
            "parts": [{"text": f"[SAFETY GUIDANCE]: {action}"}]
        }],
        turn_complete=True,
    )
```

## Gemini Configuration

```python
MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"

CONFIG = {
    "response_modalities": ["AUDIO"],
    "system_instruction": SYSTEM_PROMPT,
    "input_audio_transcription": {},   # Enable input transcription
    "output_audio_transcription": {},  # Enable output transcription
}
```

## Environment Variables

```bash
THYMIA_API_KEY=your-api-key
GEMINI_API_KEY=your-gemini-key
```

## Running the Example

```bash
cd examples/gemini_live
cp .env.example .env.local
# Edit .env.local with your API keys

uv run python src/agent.py
```

The example will start a voice conversation using your microphone and speakers.
