# Thymia Sentinel

**Voice biomarker platform for real-time conversation intelligence.**

Sentinel streams voice conversations to Thymia's Lyra server for real-time extraction of speech biomarkers, combined with policy-based reasoning to surface insights that text-only systems miss.

<div class="grid cards" markdown>

-   :material-microphone:{ .lg .middle } __Voice Biomarkers__

    ---

    Extract clinical-grade and wellness biomarkers from speech in real-time.

-   :material-file-document-edit:{ .lg .middle } __Custom Policies__

    ---

    Define policies that combine biomarkers with conversation context to drive actions.

-   :material-puzzle:{ .lg .middle } __Framework Agnostic__

    ---

    Works with LiveKit, Pipecat, VAPI, Gemini, and any voice AI stack that produces audio.

-   :material-domain:{ .lg .middle } __Any Domain__

    ---

    Mental health safety, contact centers, education, coaching, employee wellness, and more.

</div>

## How It Works

1. **Stream audio** from your voice application to Sentinel
2. **Biomarkers are extracted** in real-time by Thymia's Lyra server
3. **Policies analyze** biomarkers + conversation context
4. **Actions are returned** for your application to act on

Policies are configured with Thymia based on your use case. In code, you simply reference which policies to run:

```python
sentinel = SentinelClient(
    user_label="user-123",
    policies=["demo_wellbeing_awareness"],  # Your configured policies
)
```

## Use Cases

| Domain | Example Policies | What You Learn |
|--------|------------------|----------------|
| **Mental Health Safety** | Risk classification, crisis detection | Distress levels, minimization detection, recommended interventions |
| **Contact Centers** | Caller frustration, agent burnout | Escalation risk, when to transfer, agent wellness alerts |
| **Education** | Student anxiety, tutor wellbeing | Learning barriers, engagement drops, burnout risk |
| **Coaching** | Client engagement, session effectiveness | Emotional state, receptiveness, session quality |
| **Employee Wellness** | Stress monitoring, burnout detection | Team health trends, early intervention signals |

## Quick Start

```bash
pip install thymia-sentinel
```

```python
from thymia_sentinel import SentinelClient

sentinel = SentinelClient(
    user_label="user-123",
    policies=["your-policy"],
)

@sentinel.on_policy_result
async def handle_result(result):
    # Policy results contain actions for your application
    actions = result["result"].get("recommended_actions", {})
    if actions.get("for_agent"):
        print(f"Agent guidance: {actions['for_agent']}")

await sentinel.connect()

# Stream audio and transcripts from your voice app
await sentinel.send_user_audio(audio_bytes)
await sentinel.send_user_transcript("transcript text")

await sentinel.close()
```

## Framework Integrations

Sentinel provides plug-and-play integrations for popular voice AI frameworks:

- **[LiveKit](integrations/livekit.md)** — Automatic audio capture from LiveKit rooms
- **[Pipecat](integrations/pipecat.md)** — FrameProcessor integration for Pipecat pipelines
- **[VAPI](integrations/vapi.md)** — WebSocket transport integration
- **[Gemini Live](integrations/gemini.md)** — Google Gemini Live API integration

## Getting Access

Sentinel requires an API key from Thymia. [Contact us](mailto:support@thymia.ai) to get started.

## License

MIT License — see [LICENSE](https://github.com/thymia-ai/thymia-sentinel-integrations/blob/main/LICENSE) for details.
