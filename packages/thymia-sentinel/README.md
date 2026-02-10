# Thymia Sentinel

Voice AI safety monitoring through multimodal biomarker analysis.

Sentinel streams voice conversations to Thymia's Lyra server for real-time extraction of clinical speech biomarkers, combined with policy-based safety reasoning to detect mental health concerns that text-only systems miss.

## Why Multimodal?

Text-only safety moderation has two fundamental failure modes:

1. **False negatives (minimization)**: Users experiencing mental health crises frequently downplay their distress verbally. "I'm fine, just tired" may be spoken with voice biomarkers indicating severe depression.

2. **False positives (alarm fatigue)**: Phrases like "I'm dying of embarrassment" trigger crisis pathways despite no clinical concern, leading to desensitization and wasted resources.

Both failures stem from the same limitation: reliance on semantic content without physiological ground truth. Sentinel addresses this by combining speech biomarkers with conversation analysis through explicit concordance checking.

## Installation

```bash
pip install thymia-sentinel
```

## Quick Start

```python
from thymia_sentinel import SentinelClient

async def handle_result(result):
    policy = result["policy"]
    if policy == "safety":
        classification = result["result"]["classification"]
        level = classification["level"]  # 0-3
        alert = classification["alert"]  # none, monitor, professional_referral, crisis

        if level >= 2:
            print(f"Risk level {level}: {alert}")
            print(f"Recommended: {result['result']['recommended_actions']['for_agent']}")

sentinel = SentinelClient(
    user_label="user-123",
    policies=["safety"],
    biomarkers=["helios", "apollo"],
    on_policy_result=handle_result,
)

await sentinel.connect()

# In your voice AI audio loop:
await sentinel.send_user_audio(user_audio_bytes)      # PCM16 @ 16kHz
await sentinel.send_agent_audio(agent_audio_bytes)
await sentinel.send_user_transcript("I've been feeling okay lately")
await sentinel.send_agent_transcript("That's good to hear. How has your sleep been?")

# When done:
await sentinel.close()
```

## Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `user_label` | str | None | Unique user identifier |
| `date_of_birth` | str | None | YYYY-MM-DD format (improves accuracy, imputed from voice if omitted) |
| `birth_sex` | str | None | "MALE" or "FEMALE" (improves accuracy, imputed from voice if omitted) |
| `language` | str | "en-GB" | Language code |
| `policies` | list[str] | ["passthrough"] | Policies to execute |
| `biomarkers` | list[str] | ["helios"] | Biomarkers to extract |
| `sample_rate` | int | 16000 | Audio sample rate in Hz |
| `on_policy_result` | callable | None | Callback for policy results |
| `on_progress_result` | callable | None | Callback for progress updates |
| `api_key` | str | env THYMIA_API_KEY | Your Thymia API key |

## Policies

- **`passthrough`**: Returns raw biomarker values without interpretation
- **`safety`**: Full safety analysis with 4-level risk classification and recommended actions

## Biomarkers

- **`helios`**: Wellness indicators (distress, stress, burnout, fatigue, low self-esteem)
- **`apollo`**: Clinical disorder probabilities (depression, anxiety) and symptom-level severities
- **`psyche`**: Real-time affect detection (happy, sad, angry, fearful, etc.)

## Risk Classification

The safety policy returns a 4-level classification:

| Level | Alert | Description |
|-------|-------|-------------|
| 0 | none | No concern detected |
| 1 | monitor | Mild indicators, continue monitoring |
| 2 | professional_referral | Moderate concern, consider referral |
| 3 | crisis | Crisis level, immediate intervention |

## Framework Integrations

For framework-specific examples, see the [examples directory](../../examples/):

- [LiveKit Agents](../../examples/livekit/) - Automatic audio capture from LiveKit rooms
- [Pipecat](../../examples/pipecat/) - Integration with Pipecat pipelines
- [VAPI](../../examples/vapi_api/) - WebSocket integration for VAPI
- [Gemini Live](../../examples/gemini_live/) - Google Gemini Live API integration

## License

MIT License - see [LICENSE](../../LICENSE) for details.
