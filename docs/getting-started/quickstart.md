# Quick Start

This guide shows how to integrate Sentinel into any voice application.

## Basic Usage

```python
import asyncio
from thymia_sentinel import SentinelClient, PolicyResult

async def main():
    # Create the client
    sentinel = SentinelClient(
        user_label="user-123",           # Unique identifier
        policies=["your-policy"],        # Your configured policies
        biomarkers=["helios", "psyche"], # Biomarker models to enable
    )

    # Register handlers using decorators
    @sentinel.on_policy_result
    async def handle_result(result: PolicyResult):
        policy = result["policy"]
        inner = result["result"]

        print(f"Policy '{policy}' triggered at turn {result['triggered_at_turn']}")

        # Handle alerts
        for alert in inner.get("alerts", []):
            print(f"  Alert: {alert['type']} ({alert['severity']})")

        # Handle recommended actions
        actions = inner.get("recommended_actions", {})
        if actions.get("for_agent"):
            print(f"  Agent guidance: {actions['for_agent']}")

    await sentinel.connect()
    print("Connected to Lyra server")

    # Simulate streaming audio and transcripts
    # In a real app, this comes from your voice AI framework
    for _ in range(10):
        # Send user audio (PCM16 @ 16kHz)
        user_audio = b"\x00" * 3200  # 100ms of silence
        await sentinel.send_user_audio(user_audio)

        # Send agent audio
        agent_audio = b"\x00" * 3200
        await sentinel.send_agent_audio(agent_audio)

        await asyncio.sleep(0.1)

    # Send transcripts
    await sentinel.send_user_transcript("Hello, how are you?")
    await sentinel.send_agent_transcript("I'm doing well, thanks for asking!")

    # Keep alive to receive results
    await asyncio.sleep(5)

    await sentinel.close()

if __name__ == "__main__":
    asyncio.run(main())
```

You can also pass callbacks directly to the constructor:

```python
sentinel = SentinelClient(
    user_label="user-123",
    on_policy_result=handle_result,
    on_progress_result=handle_progress,
)
```

## Audio Format

Sentinel expects PCM16 audio:

- **Format**: 16-bit signed integer, little-endian
- **Sample rate**: 16000 Hz (configurable via `sample_rate` parameter)
- **Channels**: Mono (1 channel)

```python
# Example: Converting from different formats
import numpy as np

# From float32 [-1, 1] to PCM16
def float32_to_pcm16(audio_float32: np.ndarray) -> bytes:
    audio_int16 = (audio_float32 * 32767).astype(np.int16)
    return audio_int16.tobytes()

# Using a different sample rate (e.g., Gemini at 24kHz)
sentinel = SentinelClient(
    sample_rate=24000,
    # ...
)
```

## Handling Progress Updates

Track biomarker collection progress:

```python
sentinel = SentinelClient(
    user_label="user-123",
    progress_updates_frequency=2.0,  # Every 2 seconds
)

@sentinel.on_progress
def handle_progress(result):
    print(f"Progress at {result['timestamp']}:")
    for name, status in result["biomarkers"].items():
        collected = status["speech_seconds"]
        required = status["trigger_seconds"]
        processing = status.get("processing", False)

        if processing:
            print(f"  {name}: PROCESSING")
        else:
            pct = (collected / required) * 100
            print(f"  {name}: {pct:.0f}%")
```

Registering a progress handler automatically enables progress updates from the server.

## Handling Policy Results

Policy results vary by policy type. Here's a general pattern:

```python
async def handle_result(result: PolicyResult):
    policy = result["policy"]
    inner = result["result"]

    # All policies may include alerts
    for alert in inner.get("alerts", []):
        if alert["severity"] == "severe":
            await escalate(alert)
        elif alert["severity"] == "moderate":
            await log_alert(alert)

    # Handle recommended actions
    actions = inner.get("recommended_actions", {})

    # For AI agent (real-time guidance)
    if actions.get("for_agent"):
        await update_agent_instructions(actions["for_agent"])

    # For human review (async)
    if actions.get("for_human_reviewer"):
        await queue_for_review(result, actions["urgency"])

    # Raw biomarkers (passthrough policy or biomarker_summary)
    biomarkers = inner.get("biomarkers") or inner.get("biomarker_summary")
    if biomarkers:
        await log_biomarkers(biomarkers)
```

## Next Steps

- **[LiveKit Integration](../integrations/livekit.md)** — Automatic audio capture from LiveKit
- **[Pipecat Integration](../integrations/pipecat.md)** — FrameProcessor patterns for Pipecat
- **[Biomarkers Reference](../concepts/biomarkers.md)** — Full list of available biomarkers
- **[Policies Reference](../concepts/policies.md)** — Policy configuration and library
