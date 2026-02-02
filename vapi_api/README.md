# VAPI Thymia Sentinel Integration

An integration of Thymia Sentinel with [VAPI](https://vapi.ai), demonstrating how to add real-time voice biomarker monitoring to a VAPI voice AI assistant.

## About This Example

This integration shows how Thymia Sentinel can be added to a VAPI voice assistant using VAPI's [WebSocket Transport](https://docs.vapi.ai/calls/websocket-transport) for bidirectional audio streaming.

The example is currently configured to:

- Stream user and agent audio to Thymia's servers via WebSocket
- Send transcripts from VAPI to Sentinel for analysis
- Use the **passthrough** policy with **Helios** biomarkers
- Receive real-time wellness scores (distress, stress, burnout, fatigue, low_self_esteem)
- Inject recommended actions from `safety_analysis` policy back into VAPI mid-conversation

Other policies and biomarkers are also available - see the [main README](../README.md) for the full list.

## Architecture

```
┌─────────────┐                    ┌─────────────┐
│  Microphone │ ──── User Audio ──▶│             │
└─────────────┘                    │             │
                                   │   agent.py  │
┌─────────────┐                    │             │
│   Speaker   │ ◀── Agent Audio ───│             │
└─────────────┘                    └──────┬──────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
                    ▼                     ▼                     ▼
            ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
            │     VAPI     │      │    Thymia    │      │    Thymia    │
            │  (WebSocket) │      │   Audio &    │      │   Policy     │
            │              │      │  Transcripts │      │   Results    │
            └──────────────┘      └──────────────┘      └──────┬───────┘
                    ▲                                          │
                    │                                          │
                    └──────── Recommended Actions ─────────────┘
```

1. Capture microphone audio and send to VAPI WebSocket
2. Receive agent audio from VAPI and play through speakers
3. Stream both user and agent audio + transcripts to Thymia Sentinel
4. Receive policy results (wellness scores, safety analysis) from Sentinel
5. Inject recommended actions back into VAPI as system messages (non-interrupting)

## Quick Start

### 1. Install Dependencies

```bash
uv sync
```

Note: On Mac, you need to install PortAudio for PyAudio:

```bash
brew install portaudio
```

### 2. Configure Environment

```bash
cp .env.example .env.local
```

Fill in your credentials:

```bash
# VAPI API Key (from https://dashboard.vapi.ai)
# Note: Use your PRIVATE key for WebSocket transport
VAPI_PRIVATE_API_KEY=your-private-key

# Thymia
THYMIA_API_KEY=your-thymia-api-key

# Optional
LOG_LEVEL=INFO
```

### 3. Run the Agent

```bash
uv run python src/agent.py
```

The agent will:
1. Create a VAPI call with WebSocket transport
2. Connect to Thymia Sentinel
3. Start streaming audio bidirectionally

Speak into your microphone to interact with the assistant.

## Configuration Options

### Environment Variables

| Variable              | Default    | Description              |
|-----------------------|------------|--------------------------|
| `VAPI_PRIVATE_API_KEY`| required   | VAPI private API key     |
| `THYMIA_API_KEY`      | required   | Thymia API key           |
| `LOG_LEVEL`           | `INFO`     | Logging level            |

### Sentinel Configuration

In `agent.py`, you can configure which policies and biomarkers to use:

```python
sentinel = thymia.Sentinel(
    user_label="unique-user-id",
    date_of_birth="1990-01-01",
    birth_sex="MALE",
    language="en-GB",
    on_policy_result=handle_policy_result,
    policies=["passthrough"],  # Options: passthrough, safety_analysis, field_extraction, agent_eval
    biomarkers=["helios"]      # Options: helios, apollo
)
```

### VAPI Assistant Configuration

The assistant is configured inline in `create_websocket_call()`:

- **Model**: GPT-4o via OpenAI
- **Voice**: ElevenLabs "sarah"
- **Audio Format**: PCM 16-bit, 16kHz, mono

## Features

### Recommended Action Injection

When using the `safety_analysis` policy, Sentinel returns recommended actions for the agent. These are injected into VAPI using the `add-message` API with `triggerResponseEnabled: false` to avoid interrupting the assistant mid-speech:

```python
message = {
    "type": "add-message",
    "message": {
        "role": "system",
        "content": format_action_message(action),
    },
    "triggerResponseEnabled": False,  # Don't interrupt current speech
}
```

The agent receives the guidance and incorporates it into its next response naturally.

## Project Structure

```
vapi_api/
├── src/
│   ├── __init__.py
│   ├── agent.py          # VAPI WebSocket client with Sentinel integration
│   ├── prompts.py        # Agent system prompts
│   └── thymia/           # Sentinel module
│       ├── __init__.py
│       └── sentinel.py
├── .env.example
├── pyproject.toml
└── README.md
```

## Troubleshooting

**No audio input?**
- Check your microphone permissions
- On Mac, ensure PortAudio is installed: `brew install portaudio`

**No results from Sentinel?**
- Ensure `THYMIA_API_KEY` is set correctly
- Check that audio is being sent (enable `LOG_LEVEL=DEBUG`)

**"No WebSocket URL returned from VAPI"?**
- Verify `VAPI_PRIVATE_API_KEY` is correct (must be private key, not public)
- The WebSocket URL is in `response["transport"]["websocketCallUrl"]`
- Check the logged response for error details

**Call not starting?**
- Verify `VAPI_PRIVATE_API_KEY` is correct (must be private key for WebSocket transport)
- Check VAPI dashboard for API key status


## License

MIT License - see [LICENSE](../LICENSE) for details.