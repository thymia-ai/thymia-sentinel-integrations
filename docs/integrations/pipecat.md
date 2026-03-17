# Pipecat Integration

The Pipecat integration uses FrameProcessors to capture audio and transcripts from your pipeline.

## Installation

```bash
cd examples/pipecat
uv sync
```

## Quick Start

```python
from thymia_sentinel import SentinelClient, PolicyResult
from pipecat.frames.frames import (
    Frame, TranscriptionFrame, TTSAudioRawFrame,
    UserAudioRawFrame, TTSTextFrame, BotStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

# Frame processor to capture user audio and transcripts
class UserInputProcessor(FrameProcessor):
    def __init__(self, sentinel: SentinelClient):
        super().__init__()
        self._sentinel = sentinel

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, UserAudioRawFrame):
            await self._sentinel.send_user_audio(frame.audio)

        elif isinstance(frame, TranscriptionFrame):
            if frame.text:
                await self._sentinel.send_user_transcript(frame.text)

        await self.push_frame(frame, direction)

# Frame processor to capture agent audio and transcripts
class AgentOutputProcessor(FrameProcessor):
    def __init__(self, sentinel: SentinelClient):
        super().__init__()
        self._sentinel = sentinel
        self._transcript_buffer = []

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TTSAudioRawFrame):
            await self._sentinel.send_agent_audio(frame.audio)

        elif isinstance(frame, TTSTextFrame):
            if frame.text and direction == FrameDirection.DOWNSTREAM:
                self._transcript_buffer.append(frame.text)

        elif isinstance(frame, BotStoppedSpeakingFrame):
            if self._transcript_buffer:
                text = " ".join(self._transcript_buffer)
                await self._sentinel.send_agent_transcript(text)
                self._transcript_buffer.clear()

        await self.push_frame(frame, direction)
```

## Pipeline Setup

```python
async def bot(runner_args):
    # Initialize Sentinel
    async def handle_policy_result(result: PolicyResult):
        inner = result.get("result", {})
        if inner.get("type") == "safety_analysis":
            actions = inner.get("recommended_actions", {})
            if actions.get("for_agent"):
                await apply_recommended_action(actions["for_agent"], context, task)

    sentinel = SentinelClient(
        user_label="user-123",
        policies=["demo_wellbeing_awareness"],
        on_policy_result=handle_policy_result,
    )

    await sentinel.connect()

    try:
        # Create processors
        user_processor = UserInputProcessor(sentinel)
        agent_processor = AgentOutputProcessor(sentinel)

        # Build pipeline with processors
        pipeline = Pipeline([
            transport.input(),
            stt,
            user_processor,      # Capture user audio/transcripts
            user_aggregator,
            llm,
            tts,
            agent_processor,     # Capture agent audio/transcripts
            transport.output(),
            assistant_aggregator,
        ])

        # Run pipeline...

    finally:
        await sentinel.close()
```

## Applying Safety Actions

Update the LLM context when actions are recommended:

```python
async def apply_recommended_action(action: str, context: LLMContext, task: PipelineTask):
    # Update system message in context
    if context.messages and context.messages[0].get("role") == "system":
        context.messages[0]["content"] = format_action_update(
            SYSTEM_PROMPT, action
        )
        await task.queue_frames([
            LLMMessagesUpdateFrame(messages=list(context.messages))
        ])
```

## Environment Variables

```bash
THYMIA_API_KEY=your-api-key
DEEPGRAM_API_KEY=your-deepgram-key
OPENAI_API_KEY=your-openai-key
CARTESIA_API_KEY=your-cartesia-key
DAILY_API_KEY=your-daily-key
```

## Running the Example

```bash
cd examples/pipecat
cp .env.example .env.local
# Edit .env.local with your API keys

uv run python src/agent.py
```

Then open http://localhost:7860 and click Connect.
