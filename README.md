# Thymia Sentinel

**Voice AI safety monitoring through multimodal biomarker analysis.**

[![PyPI version](https://badge.fury.io/py/thymia-sentinel.svg)](https://badge.fury.io/py/thymia-sentinel)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Sentinel streams voice conversations to Thymia's Lyra server for real-time extraction of clinical speech biomarkers, combined with policy-based safety reasoning to detect mental health concerns that text-only systems miss.

![How Sentinel Works](./assets/diagram.gif)

## Why Multimodal?

Text-only safety moderation has two fundamental failure modes:

| Problem | Text-Only Limitation | Sentinel's Solution |
|---------|---------------------|---------------------|
| **False Negatives** | Users minimize distress: *"I'm fine, just tired"* | Voice biomarkers reveal severe depression despite reassuring words |
| **False Positives** | Innocuous phrases trigger alerts: *"I'm dying of embarrassment"* | Biomarkers confirm no clinical concern, reducing alarm fatigue |

Both failures stem from the same limitation: **relying on words without physiological ground truth**. Sentinel performs explicit concordance analysis between text and biomarkers to detect when these signals disagree.

## Installation

```bash
pip install thymia-sentinel
```

## Quick Start

```python
from thymia_sentinel import SentinelClient

sentinel = SentinelClient(
    user_label="user-123",
    policies=["safety"],
    biomarkers=["helios", "apollo"],
)

@sentinel.on_policy_result
async def handle_result(result):
    level = result["result"]["classification"]["level"]
    if level >= 2:
        print(f"Elevated risk: level {level}")
        print(result["result"]["recommended_actions"]["for_agent"])

@sentinel.on_progress
async def handle_progress(result):
    for name, status in result["biomarkers"].items():
        pct = (status["speech_seconds"] / status["trigger_seconds"]) * 100
        print(f"{name}: {pct:.0f}%")

await sentinel.connect()

# In your voice AI audio loop:
await sentinel.send_user_audio(audio_bytes)      # PCM16 @ 16kHz
await sentinel.send_agent_audio(agent_audio)
await sentinel.send_user_transcript("I'm doing okay")

await sentinel.close()
```

## Risk Classification

The safety policy returns a 4-level classification aligned with clinical intervention protocols:

| Level | Alert | Description |
|-------|-------|-------------|
| 0 | `none` | No concern detected |
| 1 | `monitor` | Mild indicators, continue monitoring |
| 2 | `professional_referral` | Moderate concern, consider referral |
| 3 | `crisis` | Crisis level, immediate intervention |

## Available Biomarkers

| Model | Biomarkers | Description |
|-------|------------|-------------|
| `helios` | distress, stress, burnout, fatigue, low_self_esteem | Wellness indicators (0-1) |
| `apollo` | depression_probability, anxiety_probability + 15 symptom scores | Clinical detection |
| `psyche` | happy, sad, angry, fearful, surprised, disgusted, neutral | Real-time affect |

## Framework Integrations

Plug-and-play examples for popular voice AI frameworks:

| Integration | Features | Guide |
|-------------|----------|-------|
| **[LiveKit](./examples/livekit/)** | Automatic RTCTrack audio capture | [Docs](./docs/integrations/livekit.md) |
| **[Pipecat](./examples/pipecat/)** | FrameProcessor integration | [Docs](./docs/integrations/pipecat.md) |
| **[VAPI](./examples/vapi_api/)** | WebSocket transport | [Docs](./docs/integrations/vapi.md) |
| **[Gemini Live](./examples/gemini_live/)** | Google Gemini Live API | [Docs](./docs/integrations/gemini.md) |

## Repository Structure

```
thymia-sentinel-integrations/
├── packages/
│   └── thymia-sentinel/          # The pip package
├── examples/
│   ├── livekit/                  # LiveKit Agents integration
│   ├── pipecat/                  # Pipecat integration
│   ├── vapi_api/                 # VAPI WebSocket integration
│   └── gemini_live/              # Gemini Live API integration
└── docs/                         # Documentation (MkDocs)
```

## Documentation

Full documentation is available in the `docs/` directory:

- **[Concepts](./docs/concepts/)** — Why multimodal, architecture, biomarkers, policies
- **[Getting Started](./docs/getting-started/)** — Installation and quickstart
- **[Integrations](./docs/integrations/)** — Framework-specific guides
- **[API Reference](./docs/api/)** — Full API documentation

## Running Examples

```bash
# Clone the repo
git clone https://github.com/thymia-ai/thymia-sentinel-integrations.git
cd thymia-sentinel-integrations

# Choose an example
cd examples/livekit  # or pipecat, vapi_api, gemini_live

# Copy environment template and add your API keys
cp .env.example .env.local

# Install dependencies and run
uv sync
uv run python src/agent.py
```

## Getting Access

Sentinel requires an API key from Thymia. [Contact us](mailto:support@thymia.ai) to get access.

- Website: https://thymia.ai
- API Docs: https://api.thymia.ai/docs

## Contributing

We welcome contributions! If you're using a different voice AI framework, we'd love to see integrations.

## License

MIT License — see [LICENSE](./LICENSE) for details.
