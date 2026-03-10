# Pipecat + Thymia Sentinel

Real-time voice biomarker monitoring for [Pipecat](https://github.com/pipecat-ai/pipecat) pipelines.

## Features

- **FrameProcessor integration** — Capture audio and transcripts from your pipeline
- **Non-invasive** — Processors pass frames through unchanged
- **Flexible placement** — Insert processors wherever makes sense in your pipeline

## Quick Start

### 1. Install Dependencies

```bash
uv sync
```

### 2. Configure Environment

```bash
cp .env.example .env.local
```

```bash
# Daily.co
DAILY_API_KEY=your-daily-api-key

# AI Services
DEEPGRAM_API_KEY=your-deepgram-key
OPENAI_API_KEY=your-openai-key
CARTESIA_API_KEY=your-cartesia-key

# Thymia
THYMIA_API_KEY=your-thymia-api-key
```

### 3. Run the Agent

```bash
uv run python src/agent.py
```

Then open http://localhost:7860 and click "Connect".

## Usage

```python
from thymia_sentinel import SentinelClient, PolicyResult, ProgressResult
from pipecat.frames.frames import (
    Frame, TranscriptionFrame, TTSAudioRawFrame,
    UserAudioRawFrame, TTSTextFrame, BotStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

class UserInputProcessor(FrameProcessor):
    def __init__(self, sentinel: SentinelClient):
        super().__init__()
        self._sentinel = sentinel

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, UserAudioRawFrame):
            await self._sentinel.send_user_audio(frame.audio)
        elif isinstance(frame, TranscriptionFrame) and frame.text:
            await self._sentinel.send_user_transcript(frame.text)
        await self.push_frame(frame, direction)

class AgentOutputProcessor(FrameProcessor):
    def __init__(self, sentinel: SentinelClient):
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
            await self._sentinel.send_agent_transcript(" ".join(self._buffer))
            self._buffer.clear()
        await self.push_frame(frame, direction)

# Initialize
sentinel = SentinelClient(
    user_label="user-123",
    policies=["demo_wellbeing_awareness"],
)

@sentinel.on_policy_result
async def handle_policy_result(result: PolicyResult):
    inner = result.get("result", {})
    if inner.get("type") == "safety_analysis":
        level = inner["classification"]["level"]
        if level >= 2:
            action = inner["recommended_actions"]["for_agent"]
            # Update LLM context
            context.messages[0]["content"] = f"{SYSTEM_PROMPT}\n\n{action}"
            await task.queue_frames([LLMMessagesUpdateFrame(messages=list(context.messages))])

await sentinel.connect()

# Add to pipeline
pipeline = Pipeline([
    transport.input(),
    stt,
    UserInputProcessor(sentinel),
    user_aggregator,
    llm,
    tts,
    AgentOutputProcessor(sentinel),
    transport.output(),
    assistant_aggregator,
])
```

## Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `user_label` | `str` | `None` | Unique user identifier |
| `date_of_birth` | `str` | `None` | YYYY-MM-DD format (improves accuracy) |
| `birth_sex` | `str` | `None` | "MALE" or "FEMALE" (improves accuracy) |
| `language` | `str` | `"en-GB"` | Language code |
| `policies` | `list[str]` | required | Policies to run |
| `biomarkers` | `list[str]` | `["helios"]` | Biomarkers to extract |

Use `@sentinel.on_policy_result` and `@sentinel.on_progress` decorators to register handlers.

## Project Structure

```
pipecat/
├── src/
│   ├── agent.py           # Example agent with processors
│   └── prompts.py         # System prompts
├── pyproject.toml
└── README.md
```

## License

MIT License — see [LICENSE](../../LICENSE)
