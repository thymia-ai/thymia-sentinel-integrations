# Gemini Live API Thymia Sentinel Integration

An example integration of Thymia Sentinel with [Google Gemini Live API](https://ai.google.dev/gemini-api/docs/live), demonstrating how to add real-time voice biomarker monitoring to a voice AI agent.

## About This Example

This integration shows how Thymia Sentinel can be added to a Gemini Live API voice agent. The agent code is adapted from Google's [Microphone streaming example](https://ai.google.dev/gemini-api/docs/live?example=mic-stream#get-started).

The example is currently configured to:

- Stream user and agent audio to Thymia's servers
- Use the **passthrough** policy with **Helios** biomarkers
- Receive real-time wellness scores (distress, stress, burnout, fatigue, low_self_esteem)

Other policies and biomarkers are also available - see the [main README](../README.md) for the full list.

## Current Architecture

The `src/thymia/` folder contains the Sentinel implementation. This is a **standalone module** that can be used with any Gemini Live API project:

```python
from thymia import Sentinel
```

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
# Gemini
GEMINI_API_KEY=your-gemini-api-key

# Thymia
THYMIA_API_KEY=your-thymia-api-key
```

### 3. Run the Agent

```bash
uv run python src/agent.py
```

The agent will start listening on your default microphone and speaking through your default audio output.

> **Important:** Use headphones to prevent the agent from hearing its own audio output, which causes feedback loops.

## Usage in Your Agent

Adding Sentinel to your Gemini Live API agent requires minimal changes:

```python
from thymia import Sentinel, ProgressResult

# Define a callback for policy results
async def handle_policy_result(result):
    policy = result.get('policy')
    inner = result.get('result', {})

    if inner.get('type') == 'passthrough':
        biomarkers = inner.get('biomarkers', {})
        print(f"Stress: {biomarkers.get('stress')}")
        print(f"Distress: {biomarkers.get('distress')}")

# Define a callback for progress updates (optional)
async def handle_progress_result(result: ProgressResult):
    timestamp = result.get('timestamp', 0.0)
    biomarkers = result.get('biomarkers', {})
    for name, progress in biomarkers.items():
        print(f"{name}: {progress.get('speech_seconds', 0):.1f}s speech collected")

# Create the Sentinel
sentinel = Sentinel(
    user_label="user-123",
    date_of_birth="1990-01-01",
    birth_sex="MALE",
    on_policy_result=handle_policy_result,
    on_progress_result=handle_progress_result,  # Optional: receive progress updates if this is defined, defaults to None
    policies=["passthrough"],      # or ["safety_analysis", "field_extraction"]
    biomarkers=["helios"],         # or ["helios", "apollo"]
)

# Connect to Thymia server
await sentinel.connect()

# In your audio loop, send audio and transcripts:
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
| `on_policy_result` | `callable` | `None` | Callback for policy results |
| `on_progress_result` | `callable` | `None` | Callback for progress updates |
| `progress_updates_frequency` | `float` | `1.0` | Progress update interval in seconds |
| `server_url` | `str` | env var | WebSocket server URL |
| `api_key` | `str` | env var | Thymia API key |

## Project Structure

```
gemini_live/
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

## Troubleshooting

**No results received?**
- Ensure the user has spoken for at least a few seconds
- Check that `THYMIA_API_KEY` is set correctly

**Audio issues?**
- Make sure PyAudio is installed correctly
- Check your default microphone and speaker settings

## License

MIT License - see [LICENSE](../LICENSE) for details.