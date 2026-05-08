# OpenAI Realtime + Thymia Sentinel

Real-time voice biomarker monitoring for [OpenAI's Realtime API](https://developers.openai.com/api/docs/guides/realtime) using `gpt-realtime-2`.

## Demo scenario: pre-presentation coach

The agent plays a calm coach helping the user in the last few minutes before something high-stakes — an interview, pitch, talk, audition, or exam. This is a deliberately chosen scenario for showcasing Thymia: people routinely **say** they feel ready while their voice reveals elevated stress, anxiety, or fatigue. That **discordance** between text and voice is exactly what Thymia Sentinel detects.

The agent's default mode is curious listening — asking specific questions about what's coming up, not prescribing techniques. Once Sentinel fires a hint that signals are elevated, the agent surfaces it literally and humanly:

> *"I'm picking up quite a bit of stress in your voice right now — what's underneath that?"*

It's that one sentence — naming the gap between what was said and how it sounded — that makes the technology visible to viewers.

To try it: run the agent, tell it what you're "walking into" and how long you have, then either play it cool or play it stressed and watch the conversation shift.

## Features

- **Native audio streaming** — Direct WebSocket integration with the Realtime API
- **Transcript capture** — Input and output transcriptions wired into Sentinel
- **24kHz support** — Matches the Realtime API's native sample rate
- **Safety actions** — Recommended actions are injected as priority conversation items, with the Sentinel concerns list passed through so the agent can name what it's hearing literally
- **Semantic VAD** — Model-driven turn detection, more robust than level-based VAD against agent audio leaking back through the mic
- **Half-duplex mode** — Toggleable via `ALLOW_INTERRUPTION=false` for laptop-speaker demos without acoustic echo cancellation
- **Reasoning effort: low** — Recommended setting for production voice agents

## Quick Start

### 1. Install Dependencies

PyAudio links against PortAudio, so install the native library **before** running `uv sync`:

```bash
# macOS (Apple Silicon and Intel)
brew install portaudio

# Debian / Ubuntu
sudo apt-get install portaudio19-dev
```

Then sync the Python deps:

```bash
uv sync
```

**Troubleshooting:** if `uv sync` fails with `fatal error: 'portaudio.h' file not found`, PortAudio isn't installed (or `brew` lost the keg). Reinstall with `brew install portaudio`, clear the cached build with `uv cache clean pyaudio`, and re-run `uv sync`.

### 2. Configure Environment

```bash
cp .env.example .env.local
```

```bash
OPENAI_API_KEY=your-openai-api-key
THYMIA_API_KEY=your-thymia-api-key
```

### 3. Run

```bash
uv run python src/agent.py
```

> **Tip:** Use headphones to prevent feedback loops. If you have to play the agent through laptop or external speakers (e.g. live demos), set `ALLOW_INTERRUPTION=false` in `.env.local` — this switches the agent to half-duplex (the mic is muted while it's speaking) so its own voice can't loop back and interrupt itself.

## Usage

```python
import websockets
from thymia_sentinel import SentinelClient, PolicyResult

SAMPLE_RATE = 24000  # OpenAI Realtime uses 24kHz

sentinel = SentinelClient(
    sample_rate=SAMPLE_RATE,
    policies=["demo_wellbeing_awareness"],
    biomarkers=["helios"],
)

@sentinel.on_policy_result
async def handle_policy_result(result: PolicyResult):
    inner = result.get("result", {})
    if inner.get("type") == "safety_analysis":
        level = inner.get("level", 0)  # top-level on the new payload
        if level >= 2:
            action = inner["recommended_actions"]["for_agent"]
            await apply_action(action, ws)

await sentinel.connect()

async with websockets.connect(
    "wss://api.openai.com/v1/realtime?model=gpt-realtime-2",
    additional_headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
    max_size=None,
) as ws:
    # session.update, then run send/receive/play tasks concurrently
    ...

await sentinel.close()
```

## Capturing Audio

Mic audio is base64-encoded and sent via `input_audio_buffer.append`; the same raw PCM16 bytes are forked into Sentinel:

```python
import base64

async def listen_audio(sentinel):
    while True:
        pcm = await asyncio.to_thread(audio_stream.read, CHUNK_SIZE)
        await ws.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(pcm).decode("ascii"),
        }))
        await sentinel.send_user_audio(pcm)
```

Agent audio arrives as `response.output_audio.delta` events; decode and fork to speakers + Sentinel:

```python
async for raw in ws:
    event = json.loads(raw)
    if event["type"] == "response.output_audio.delta":
        pcm = base64.b64decode(event["delta"])
        speaker_queue.put_nowait(pcm)
        await sentinel.send_agent_audio(pcm)

    elif event["type"] == "response.output_audio_transcript.done":
        await sentinel.send_agent_transcript(transcript_buffer)

    elif event["type"] == "conversation.item.input_audio_transcription.completed":
        await sentinel.send_user_transcript(event["transcript"])
```

## Injecting Safety Actions

Recommended actions are appended to the conversation as a `conversation.item.create` user message. We deliberately do **not** call `response.create` here: server VAD auto-creates a response on user-speech-end, and a manual `response.create` racing with that fires `conversation_already_has_active_response`. The appended item is picked up by whichever response generates next, which is what we want anyway:

```python
async def apply_action(action: str, ws):
    await ws.send(json.dumps({
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": format_action_message(action)}],
        },
    }))
```

## Configuration

### `SentinelClient` parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `date_of_birth` | `str` | `None` | YYYY-MM-DD format (improves accuracy) |
| `birth_sex` | `str` | `None` | "MALE" or "FEMALE" (improves accuracy) |
| `sample_rate` | `int` | `16000` | **Set to 24000 for OpenAI Realtime** |
| `policies` | `list[str]` | required | Policies to run |
| `biomarkers` | `list[str]` | `["helios"]` | Biomarkers to extract |

`date_of_birth` and `birth_sex` are optional but improve biomarker accuracy. The example prompts for them on each run; press Enter to accept defaults or type `skip` to omit and let Sentinel impute from voice.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | required | OpenAI API key |
| `THYMIA_API_KEY` | required | Thymia API key |
| `LOG_LEVEL` | `INFO` | `DEBUG` for verbose Sentinel SDK logging |
| `ALLOW_INTERRUPTION` | `true` | Set to `false` for laptop-speaker demos (half-duplex) |
| `THYMIA_DOB` | unset | Pre-fill DOB and skip the prompt (e.g. `1997-11-18`) |
| `THYMIA_BIRTH_SEX` | unset | Pre-fill birth sex and skip the prompt (`MALE`/`FEMALE`) |
| `WRAP_WIDTH` | auto | Override log wrap width (`0` to disable wrapping) |

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
                # speech rather than just "loud enough" — better at ignoring
                # echo than a level-based VAD.
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

## Project Structure

```
openai_realtime/
├── src/
│   ├── agent.py           # Core integration: OpenAI Realtime ↔ Sentinel
│   ├── display.py         # Terminal logging, formatting, and prompts
│   └── prompts.py         # System prompt + safety-action wrapper
├── pyproject.toml
└── README.md
```

`agent.py` is intentionally kept minimal as a reference implementation.
All terminal rendering, log formatting, transcript filtering, and the
DOB/birth-sex prompt live in `display.py`.

## License

MIT License — see [LICENSE](../../LICENSE)
