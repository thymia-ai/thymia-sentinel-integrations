# LiveKit Thymia Sentinel Integration

An example integration of Thymia Sentinel with [LiveKit Agents](https://docs.livekit.io/agents/), demonstrating how to add real-time voice biomarker monitoring to a voice AI agent.

## About This Example

This integration shows how Thymia Sentinel can be added to a LiveKit voice agent. The example is currently configured to:

- Stream user and agent audio to Thymia's servers
- Use the **passthrough** policy with **Helios** biomarkers
- Receive real-time wellness scores (distress, stress, burnout, fatigue, low_self_esteem)

Other policies and biomarkers are also available - see the [main README](../README.md) for the full list.

## Current Architecture

The `src/livekit/plugins/thymia/` folder contains the Sentinel plugin implementation. This is a **temporary approach** for development - the intention is for this to become a pip-installable package:

```bash
# Future (not yet available):
pip install livekit-plugins-thymia
```

For now, the plugin code lives alongside the example agent.

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
# LiveKit
LIVEKIT_AGENT_NAME=your-agent-name
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret

# Thymia
THYMIA_API_KEY=your-thymia-api-key

# LLM/STT/TTS providers
OPENAI_API_KEY=your-openai-key
DEEPGRAM_API_KEY=your-deepgram-key
RIME_API_KEY=your-rime-key
```

### 3. Run the Agent

```bash
uv run python src/agent.py dev
```

### 4. Dispatch the Agent and Generate a Token

Source the local environment file:
```bash
source .env.local
```

Dispatch the agent to a room:
```bash
lk dispatch create --api-key $LIVEKIT_API_KEY --api-secret $LIVEKIT_API_SECRET --url $LIVEKIT_URL --room test-room --agent-name test-agent-thymia
```

Generate a token:
```bash
lk token create --api-key $LIVEKIT_API_KEY --api-secret $LIVEKIT_API_SECRET --url $LIVEKIT_URL --join --room test-room --identity test-user
```

### 5. Connect via LiveKit Playground

Open [agents-playground.livekit.io](https://agents-playground.livekit.io/), connect with a token, and start talking.

## Usage in Your Agent

Adding Sentinel to your LiveKit agent requires minimal changes:

```python
from livekit.plugins import thymia

# Define a callback for policy results
async def handle_policy_result(result: thymia.PolicyResult):
    policy = result.get('policy')
    inner = result.get('result', {})

    if inner.get('type') == 'passthrough':
        biomarkers = inner.get('biomarkers', {})
        print(f"Stress: {biomarkers.get('stress')}")
        print(f"Distress: {biomarkers.get('distress')}")

# Define a callback for progress updates (optional)
async def handle_progress_result(result: thymia.ProgressResult):
    timestamp = result.get('timestamp', 0.0)
    biomarkers = result.get('biomarkers', {})
    for name, progress in biomarkers.items():
        print(f"{name}: {progress.get('speech_seconds', 0):.1f}s speech collected")

# Create the Sentinel
sentinel = thymia.Sentinel(
    user_label="user-123",
    date_of_birth="1990-01-01",
    birth_sex="MALE",
    on_policy_result=handle_policy_result,
    on_progress_result=handle_progress_result,  # Optional: receive progress updates if this is defined, defaults to None
    policies=["passthrough"],      # or ["safety_analysis", "field_extraction"]
    biomarkers=["helios"],         # or ["helios", "apollo"]
)

# Start monitoring (after session.start())
await sentinel.start(ctx, session)
```

The Sentinel automatically:
- Captures audio from both user and agent tracks
- Sends transcripts from the session's STT
- Streams everything to the Thymia server
- Calls your callback when results arrive

## Configuration Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `user_label` | `str` | required | Unique user identifier |
| `date_of_birth` | `str` | required | YYYY-MM-DD format |
| `birth_sex` | `str` | required | "MALE" or "FEMALE" |
| `language` | `str` | `"en-GB"` | BCP-47 language code |
| `policies` | `list[str]` | `["passthrough"]` | Which policies to run |
| `biomarkers` | `list[str]` | `["helios"]` | Which biomarker providers to use |
| `on_policy_result` | `callable` | `None` | Callback for policy results |
| `on_progress_result` | `callable` | `None` | Callback for progress updates |
| `progress_updates_frequency` | `float` | `1.0` | Progress update interval in seconds |
| `server_url` | `str` | env var | WebSocket server URL |
| `api_key` | `str` | env var | Thymia API key |

## Project Structure

```
livekit/
├── src/
│   ├── agent.py                    # Example agent with Sentinel
│   ├── prompts.py                  # Agent system prompts
│   ├── tools.py                    # Agent tools
│   └── livekit/plugins/thymia/     # Sentinel plugin (temporary location)
│       ├── __init__.py
│       └── sentinel.py
├── .env.example
├── pyproject.toml
└── README.md
```

## Troubleshooting

**No results received?**
- Ensure the user has spoken for at least `min_speech_duration` seconds
- Check that `THYMIA_API_KEY` is set correctly

## License

MIT License - see [LICENSE](../LICENSE) for details.