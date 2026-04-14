# LiveKit + Thymia Sentinel

Real-time voice biomarker monitoring for [LiveKit Agents](https://docs.livekit.io/agents/).

## Features

- **Automatic audio capture** — RTCTrack subscriptions for user and agent audio
- **Session event forwarding** — Transcripts captured from STT automatically
- **Zero manual routing** — Just call `sentinel.start(ctx, session)`

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
# LiveKit
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret

# Thymia
THYMIA_API_KEY=your-thymia-api-key

# AI Services
OPENAI_API_KEY=your-openai-key

# STT Provider (choose one — Deepgram is default)
DEEPGRAM_API_KEY=your-deepgram-key        # Required if using Deepgram (default)
SPEECHMATICS_API_KEY=your-speechmatics-key # Required if using Speechmatics
```

### 3. Run the Agent

```bash
uv run python src/agent.py dev
```

### 4. Connect

Use [agents-playground.livekit.io](https://agents-playground.livekit.io/) or dispatch to a room:

```bash
source .env.local
lk dispatch create --api-key $LIVEKIT_API_KEY --api-secret $LIVEKIT_API_SECRET \
    --url $LIVEKIT_URL --room test-room --agent-name test-agent
```

Generate a token for the playground:
```bash

lk create-token --api-key $LIVEKIT_API_KEY --api-secret $LIVEKIT_API_SECRET \
    --url $LIVEKIT_URL --join --room test-room --identity test-user-1 --valid-for 24h
```

## Usage

```python
from livekit.plugins import thymia

sentinel = thymia.Sentinel(
    user_label="user-123",
    policies=["demo_wellbeing_awareness"],
    biomarkers=["helios", "apollo"],
)

@sentinel.on_policy_result
async def handle_policy_result(result: thymia.PolicyResult):
    inner = result.get("result", {})
    if inner.get("type") == "safety_analysis":
        level = inner["classification"]["level"]
        if level >= 2:
            action = inner["recommended_actions"]["for_agent"]
            await agent.apply_recommended_action(action)

@sentinel.on_progress
async def handle_progress(result: thymia.ProgressResult):
    for name, status in result["biomarkers"].items():
        pct = (status["speech_seconds"] / status["trigger_seconds"]) * 100
        print(f"{name}: {pct:.0f}%")

# After session.start()
await sentinel.start(ctx, session)
```

The Sentinel automatically captures:
- User audio from remote participant tracks
- Agent audio from local TTS tracks
- Transcripts from session STT events

## Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `user_label` | `str` | `None` | Unique user identifier |
| `date_of_birth` | `str` | `None` | YYYY-MM-DD format (improves accuracy) |
| `birth_sex` | `str` | `None` | "MALE" or "FEMALE" (improves accuracy) |
| `language` | `str` | `"en-GB"` | Language code |
| `policies` | `list[str]` | required | Policies to run |
| `biomarkers` | `list[str]` | `["helios"]` | Biomarkers to extract |
| `stt_provider` | `str` | `"deepgram"` | STT provider: `"deepgram"` or `"speechmatics"` |
| `on_policy_result` | `callable` | `None` | Callback for results |
| `on_progress_result` | `callable` | `None` | Callback for progress |

## STT Provider

The agent supports two STT providers, selectable via the `sttProvider` field in job metadata:

| Provider | Value | Env Variable | Turn Detection |
|----------|-------|--------------|----------------|
| Deepgram | `deepgram` (default) | `DEEPGRAM_API_KEY` | Confidence-based end-of-turn |
| Speechmatics | `speechmatics` | `SPEECHMATICS_API_KEY` | Fixed silence-based (1.5s) |

To use Speechmatics, pass it in the dispatch metadata:

```bash
lk dispatch create --api-key $LIVEKIT_API_KEY --api-secret $LIVEKIT_API_SECRET \
    --url $LIVEKIT_URL --room test-room --agent-name test-agent \
    --metadata '{"sttProvider": "speechmatics"}'
```

## Publishing Results to UI

Forward results to your frontend via LiveKit data channels:

```python
async def handle_policy_result(result):
    await ctx.room.local_participant.publish_data(
        payload=json.dumps(result).encode("utf-8"),
        topic="thymia-policy-result",
    )
```

## Project Structure

```
livekit/
├── src/
│   ├── agent.py                      # Example agent
│   ├── prompts.py                    # System prompts
│   ├── tools.py                      # Agent tools
│   └── livekit/plugins/thymia/       # LiveKit-specific adapter
│       ├── __init__.py
│       └── sentinel.py
├── pyproject.toml
└── README.md
```

The LiveKit adapter extends `thymia-sentinel` with RTCTrack integration.

## License

MIT License — see [LICENSE](../../LICENSE)
