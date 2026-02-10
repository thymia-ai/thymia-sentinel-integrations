# LiveKit Integration

The LiveKit integration provides automatic audio capture from LiveKit rooms through RTCTrack subscriptions.

## Features

- Automatic user audio capture via track subscriptions
- Automatic agent audio capture from local tracks
- Session event forwarding (transcripts, state changes)
- Seamless integration with LiveKit Agents framework

## Installation

```bash
cd examples/livekit
uv sync
```

## Quick Start

```python
from livekit.agents import JobContext, cli, WorkerOptions
from livekit.plugins import thymia

async def entrypoint(ctx: JobContext):
    # Your agent setup...
    session = AgentSession(stt=stt, llm=llm, tts=tts)

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    await session.start(agent=agent, room=ctx.room)

    # Define callbacks
    async def handle_policy_result(result: thymia.PolicyResult):
        inner = result.get("result", {})
        if inner.get("type") == "safety_analysis":
            actions = inner.get("recommended_actions", {})
            if actions.get("for_agent"):
                await agent.apply_recommended_action(actions["for_agent"])

    # Initialize Sentinel
    sentinel = thymia.Sentinel(
        user_label="user-123",
        policies=["safety"],
        biomarkers=["helios", "apollo"],
        on_policy_result=handle_policy_result,
    )

    # Start monitoring - handles all audio capture automatically
    await sentinel.start(ctx, session)

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
```

## How It Works

When you call `sentinel.start(ctx, session)`:

1. **Connects to Lyra server** via WebSocket
2. **Registers track handlers** on the LiveKit room
3. **Subscribes to user audio** from remote participants
4. **Captures agent audio** from local TTS tracks
5. **Forwards session events** (transcripts, state changes)

All audio streaming happens automatically—you don't need to manually route audio.

## Session Event Capture

If you pass a `session` to `start()`, Sentinel automatically captures:

- `user_input_transcribed` → User transcripts
- `conversation_item_added` → Agent responses
- `user_state_changed` / `agent_state_changed` → State metadata
- `speech_created` → Speech events
- `metrics_collected` → Performance metrics

## Applying Safety Actions

The example shows how to apply recommended actions by updating the agent's instructions:

```python
class SafetyAwareAssistant(Agent):
    async def apply_recommended_action(self, action: str):
        updated_instructions = format_action_update(self._base_instructions, action)
        await self.update_instructions(updated_instructions)
```

## Publishing Results to UI

Forward results to your frontend via LiveKit data channels:

```python
async def handle_policy_result(result: thymia.PolicyResult):
    # Publish to UI
    await ctx.room.local_participant.publish_data(
        payload=json.dumps(result).encode("utf-8"),
        topic="thymia-policy-result",
    )

async def handle_progress_result(result: thymia.ProgressResult):
    await ctx.room.local_participant.publish_data(
        payload=json.dumps(result).encode("utf-8"),
        topic="thymia-progress-result",
    )
```

## Environment Variables

```bash
THYMIA_API_KEY=your-api-key
LIVEKIT_URL=wss://your-livekit-server
LIVEKIT_API_KEY=your-livekit-key
LIVEKIT_API_SECRET=your-livekit-secret
DEEPGRAM_API_KEY=your-deepgram-key
OPENAI_API_KEY=your-openai-key
```

## Running the Example

```bash
cd examples/livekit
cp .env.example .env.local
# Edit .env.local with your API keys

uv run python src/agent.py dev
```
