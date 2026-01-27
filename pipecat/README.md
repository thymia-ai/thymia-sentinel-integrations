# Pipecat Thymia Sentinel Integration

An example integration of Thymia Sentinel with [Pipecat](https://github.com/pipecat-ai/pipecat), demonstrating how to add real-time voice biomarker monitoring to a Pipecat voice AI agent.

## About This Example

This integration shows how Thymia Sentinel can be added to a Pipecat voice agent. The agent code is adapted from the [Pipecat Quickstart](https://github.com/pipecat-ai/pipecat-quickstart).

The example is currently configured to:

- Stream user and agent audio to Thymia's servers
- Use the **passthrough** policy with **Helios** biomarkers
- Receive real-time wellness scores (distress, stress, burnout, fatigue, low_self_esteem)

Other policies and biomarkers are also available - see the [main README](../README.md) for the full list.

## Current Architecture

The `src/thymia/` folder contains the Sentinel client implementation. This is a **standalone module** that can be used with any Pipecat project:

```python
from thymia import Sentinel
```

The example agent (`src/agent.py`) shows how to create Pipecat `FrameProcessor` classes that capture audio and transcripts from the pipeline and forward them to Sentinel.

## Quick Start

### 1. Install Dependencies

```bash
uv sync
```

### 2. Configure Environment

```bash
cp .env.example .env.local
```

Fill in your credentials:

```bash
# Daily.co (get your API key from https://dashboard.daily.co/developers)
DAILY_API_KEY=your-daily-api-key

# AI Services
DEEPGRAM_API_KEY=your-deepgram-api-key
OPENAI_API_KEY=your-openai-api-key
CARTESIA_API_KEY=your-cartesia-api-key

# Thymia
THYMIA_API_KEY=your-thymia-api-key

# Optional
LOG_LEVEL=INFO
```

### 3. Run the Agent

```bash
uv run python src/agent.py
```

Then open http://localhost:7860 in your browser and click "Connect" to talk with the agent.

## Usage in Your Agent

### Using FrameProcessors (Recommended)

Create Pipecat `FrameProcessor` classes to capture audio and transcripts from the pipeline:

```python
from pipecat.frames.frames import (
    Frame, TranscriptionFrame, TTSAudioRawFrame,
    UserAudioRawFrame, TTSTextFrame, BotStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from thymia import Sentinel

# Processor to capture user audio and transcripts
class UserInputProcessor(FrameProcessor):
    def __init__(self, sentinel: Sentinel):
        super().__init__()
        self._sentinel = sentinel

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, UserAudioRawFrame):
            await self._sentinel.send_user_audio(frame.audio)
        elif isinstance(frame, TranscriptionFrame) and frame.text:
            await self._sentinel.send_user_transcript(frame.text)
        await self.push_frame(frame, direction)

# Processor to capture agent audio and transcripts
class AgentOutputProcessor(FrameProcessor):
    def __init__(self, sentinel: Sentinel):
        super().__init__()
        self._sentinel = sentinel
        self._buffer = []

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSAudioRawFrame):
            await self._sentinel.send_agent_audio(frame.audio)
        elif isinstance(frame, TTSTextFrame) and frame.text:
            self._buffer.append(frame.text)
        elif isinstance(frame, BotStoppedSpeakingFrame) and self._buffer:
            await self._sentinel.send_agent_transcript(' '.join(self._buffer))
            self._buffer.clear()
        await self.push_frame(frame, direction)

# Create Sentinel and processors
sentinel = Sentinel(
    user_label="user-123",
    date_of_birth="1990-01-01",
    birth_sex="MALE",
    on_policy_result=handle_policy_result,
)
await sentinel.connect()

user_processor = UserInputProcessor(sentinel)
agent_processor = AgentOutputProcessor(sentinel)

# Add to pipeline
pipeline = Pipeline([
    transport.input(),
    stt,
    user_processor,      # Capture user audio and transcripts (after STT)
    user_aggregator,
    llm,
    tts,
    agent_processor,     # Capture agent audio and transcripts
    transport.output(),
    assistant_aggregator,
])
```

### Direct API Usage

For non-Pipecat integrations, you can use the Sentinel API directly:

```python
from thymia import Sentinel

sentinel = Sentinel(
    user_label="user-123",
    date_of_birth="1990-01-01",
    birth_sex="MALE",
    on_policy_result=handle_policy_result,
)
await sentinel.connect()

# Send audio and transcripts as they become available
await sentinel.send_user_audio(audio_bytes)
await sentinel.send_agent_audio(audio_bytes)
await sentinel.send_user_transcript("Hello")
await sentinel.send_agent_transcript("Hi there!")

# When done
await sentinel.close()
```

## Configuration Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `user_label` | `str` | required | Unique user identifier |
| `date_of_birth` | `str` | required | YYYY-MM-DD format |
| `birth_sex` | `str` | required | "MALE" or "FEMALE" |
| `language` | `str` | `"en-GB"` | BCP-47 language code |
| `policies` | `list[str]` | `["passthrough"]` | Which policies to run |
| `biomarkers` | `list[str]` | `["helios"]` | Which biomarker providers to use |
| `on_policy_result` | `callable` | `None` | Callback for results |
| `buffer_strategy` | `str` | `"simple_reset"` | Audio buffering strategy |
| `server_url` | `str` | env var | WebSocket server URL |
| `api_key` | `str` | env var | Thymia API key |

## Project Structure

```
pipecat/
├── src/
│   ├── agent.py           # Example agent with Sentinel
│   ├── prompts.py         # Agent system prompts
│   └── thymia/            # Sentinel module
│       ├── __init__.py
│       └── sentinel.py
├── .env.example
├── pyproject.toml
└── README.md
```

## Pipecat Services

This example uses the following Pipecat services:

- **Transport**: [Daily.co](https://daily.co) - WebRTC transport for real-time audio
- **STT**: [Deepgram](https://deepgram.com) - Speech-to-text
- **LLM**: [OpenAI](https://openai.com) - GPT-4o for conversation
- **TTS**: [Cartesia](https://cartesia.ai) - Text-to-speech

You can swap these for other Pipecat-supported services as needed.

## Troubleshooting

**No results received?**
- Ensure the user has spoken for at least a few seconds
- Check that `THYMIA_API_KEY` is set correctly

**Can't connect to Daily room?**
- Make sure `DAILY_API_KEY` is set correctly
- Get your API key from https://dashboard.daily.co/developers

**Audio issues?**
- Check your browser's microphone permissions
- Ensure the Daily room is configured for audio

## License

MIT License - see [LICENSE](../LICENSE) for details.