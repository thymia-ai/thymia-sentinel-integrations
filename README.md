# Thymia Sentinel Integrations

**Beta Product** - Integration examples for Thymia Sentinel, a real-time voice biomarker and safety monitoring service for voice AI agents.

## What is Thymia Sentinel?

Thymia Sentinel allows you to stream audio from a voice agent conversation to Thymia's servers and receive back:

- **Biomarker scores** - Real-time mental wellness indicators extracted from voice (stress, distress, burnout, fatigue, emotions, etc.)
- **Policy results** - Configurable analysis outputs like safety assessments, field extraction, or raw biomarker passthrough

This enables voice AI agents to be aware of user wellbeing and adapt their responses accordingly.

## How It Works

![How Sentinel Works](./assets/diagram.gif)

## Integration Protocol

To integrate with Thymia Sentinel, your voice agent needs to:

### 1. Connect via WebSocket

Connect to the Thymia WebSocket server (default: `wss://ws.thymia.ai`).

### 2. Send Configuration

Send a CONFIG message as the first message after connecting:

```json
{
  "api_key": "your-thymia-api-key",
  "user_label": "unique-user-id",
  "date_of_birth": "1990-01-15",
  "birth_sex": "MALE",
  "language": "en-GB",
  "biomarkers": ["helios"],
  "policies": ["passthrough"],
  "sample_rate": 16000,
  "format": "pcm16",
  "channels": 1
}
```

### 3. Stream Audio

Send audio as header + binary pairs:

```json
{
  "type": "AUDIO_HEADER",
  "track": "user",
  "bytes": 3200,
  "format": "pcm16",
  "sample_rate": 16000,
  "channels": 1
}
```
Followed immediately by binary PCM16 audio data.

Track can be `"user"` (the human) or `"agent"` (your AI's TTS output).

### 4. Send Transcripts

Send transcription results as they become available:

```json
{
  "type": "TRANSCRIPT",
  "speaker": "user",
  "text": "I've been feeling quite stressed lately",
  "is_final": true,
  "timestamp": 1701234567.89
}
```

### 5. Receive Results

The server sends back `POLICY_RESULT` messages containing biomarkers and analysis:

```json
{
  "type": "POLICY_RESULT",
  "policy": "passthrough",
  "triggered_at_turn": 2,
  "timestamp": 1701234567.89,
  "result": {
    "type": "passthrough",
    "biomarkers": {
      "distress": 0.45,
      "stress": 0.62,
      "burnout": 0.18,
      "fatigue": 0.35,
      "low_self_esteem": 0.25
    },
    "turn_count": 2
  }
}
```

## Available Biomarkers

| Provider | Biomarkers | Description |
|----------|------------|-------------|
| `helios` | distress, stress, burnout, fatigue, low_self_esteem | Wellness indicators (0-1 scale) |
| `apollo` | depression_probability, anxiety_probability, + 15 symptom scores | Disorder detection |

## Available Policies

| Policy | Description | Requires LLM |
|--------|-------------|--------------|
| `passthrough` | Raw biomarker scores on each user turn | No |
| `safety_analysis` | Risk classification with recommended agent actions | Yes |
| `field_extraction` | Extract structured fields from conversation | Yes |
| `agent_eval` | Evaluate agent response quality | Yes |

## Example Integrations

| Integration | User Audio | Agent Audio | Multi-Participant | Policy Results |
|-------------|:----------:|:-----------:|:-----------------:|:--------------:|
| [LiveKit](./livekit/README.md) | ✅ | ✅ | 🚫 | ✅ |
| [Gemini Live API](./gemini_live/README.md) | ✅ | ✅ | 🚫 | ✅ |
| [Pipecat](./pipecat/README.md) | ✅ | ✅ | 🚫 | ✅ |

### Other Frameworks

If you're using a different voice agent framework and would like to integrate with Thymia Sentinel, the protocol above describes everything you need. We welcome contributions of new integrations!

## Getting Access

Thymia Sentinel is currently in beta. Contact Thymia for API access:

- Website: https://thymia.ai
- API Docs: https://api.thymia.ai/docs

## License

MIT License - see [LICENSE](./LICENSE) for details.