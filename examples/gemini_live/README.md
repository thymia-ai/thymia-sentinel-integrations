# Gemini Live + Thymia Sentinel

Real-time voice biomarker monitoring for [Google Gemini Live API](https://ai.google.dev/gemini-api/docs/live).

## Features

- **Native audio streaming** — Direct integration with Gemini's audio API
- **Transcript capture** — Input and output transcriptions from Gemini
- **24kHz support** — Matches Gemini's native sample rate

## Quick Start

### 1. Install Dependencies

```bash
uv sync

# On macOS:
brew install portaudio
```

### 2. Configure Environment

```bash
cp .env.example .env.local
```

```bash
GEMINI_API_KEY=your-gemini-api-key
THYMIA_API_KEY=your-thymia-api-key
```

### 3. Run

```bash
uv run python src/agent.py
```

> **Tip:** Use headphones to prevent feedback loops.

## Usage

```python
from google import genai
from thymia_sentinel import SentinelClient, PolicyResult

SAMPLE_RATE = 24000  # Gemini uses 24kHz

sentinel = SentinelClient(
    user_label="user-123",
    sample_rate=SAMPLE_RATE,  # Match Gemini's rate
    policies=["demo_wellbeing_awareness"],
)

@sentinel.on_policy_result
async def handle_policy_result(result: PolicyResult):
    inner = result.get("result", {})
    if inner.get("type") == "safety_analysis":
        level = inner["classification"]["level"]
        if level >= 2:
            action = inner["recommended_actions"]["for_agent"]
            await apply_action(action, session)

await sentinel.connect()

async with client.aio.live.connect(model=MODEL, config=CONFIG) as session:
    async with asyncio.TaskGroup() as tg:
        tg.create_task(listen_audio(sentinel))
        tg.create_task(send_realtime(session))
        tg.create_task(receive_audio(session, sentinel))
        tg.create_task(play_audio())

await sentinel.close()
```

## Capturing Audio

```python
async def listen_audio(sentinel):
    while True:
        data = await asyncio.to_thread(audio_stream.read, CHUNK_SIZE)
        await audio_queue.put({"data": data, "mime_type": "audio/pcm"})
        await sentinel.send_user_audio(data)

async def receive_audio(session, sentinel):
    user_buffer, agent_buffer = [], []

    async for response in session.receive():
        sc = response.server_content
        if not sc:
            continue

        # User transcript
        if sc.input_transcription and sc.input_transcription.text:
            user_buffer.append(sc.input_transcription.text)

        # Agent transcript
        if sc.output_transcription and sc.output_transcription.text:
            if user_buffer:
                await sentinel.send_user_transcript("".join(user_buffer))
                user_buffer.clear()
            agent_buffer.append(sc.output_transcription.text)

        # Agent audio
        if sc.model_turn:
            for part in sc.model_turn.parts:
                if part.inline_data:
                    await sentinel.send_agent_audio(part.inline_data.data)

        # Turn complete
        if sc.turn_complete:
            if user_buffer:
                await sentinel.send_user_transcript("".join(user_buffer))
                user_buffer.clear()
            if agent_buffer:
                await sentinel.send_agent_transcript("".join(agent_buffer))
                agent_buffer.clear()
```

## Injecting Safety Actions

```python
async def apply_action(action: str, session):
    await session.send_client_content(
        turns=[{"role": "user", "parts": [{"text": f"[SAFETY]: {action}"}]}],
        turn_complete=True,
    )
```

## Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `user_label` | `str` | `None` | Unique user identifier |
| `date_of_birth` | `str` | `None` | YYYY-MM-DD format (improves accuracy) |
| `birth_sex` | `str` | `None` | "MALE" or "FEMALE" (improves accuracy) |
| `sample_rate` | `int` | `16000` | **Set to 24000 for Gemini** |
| `policies` | `list[str]` | required | Policies to run |
| `biomarkers` | `list[str]` | `["helios"]` | Biomarkers to extract |

## Gemini Configuration

```python
MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"

CONFIG = {
    "response_modalities": ["AUDIO"],
    "system_instruction": SYSTEM_PROMPT,
    "input_audio_transcription": {},   # Enable
    "output_audio_transcription": {},  # Enable
}
```

## Project Structure

```
gemini_live/
├── src/
│   ├── agent.py           # Gemini Live client
│   └── prompts.py         # System prompts
├── pyproject.toml
└── README.md
```

## License

MIT License — see [LICENSE](../../LICENSE)
