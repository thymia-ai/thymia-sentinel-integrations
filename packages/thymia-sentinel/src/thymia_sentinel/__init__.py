"""
Thymia Sentinel - Voice AI safety monitoring through multimodal analysis.

Sentinel streams voice conversations to Thymia's Lyra server for real-time
biomarker extraction and policy-based safety analysis. It addresses the
fundamental limitation of text-only safety systems by combining speech
biomarkers with conversation content to detect:

- **Minimization**: When users verbally downplay genuine distress
- **Alarm fatigue**: False positives from innocuous language patterns

## Quick Start

```python
from thymia_sentinel import SentinelClient

async def handle_result(result):
    level = result["result"]["classification"]["level"]
    if level >= 2:
        print(f"Elevated risk detected: level {level}")

sentinel = SentinelClient(
    user_label="user-123",
    policies=["demo_wellbeing_awareness"],
    biomarkers=["helios", "apollo"],
    on_policy_result=handle_result,
)

await sentinel.connect()

# Stream audio and transcripts from your voice AI framework
await sentinel.send_user_audio(audio_bytes)
await sentinel.send_user_transcript("I'm doing okay")

await sentinel.close()
```

## Available Demo Policies

- `demo_wellbeing_awareness`: Wellbeing awareness analysis with risk classification
- `demo_field_extraction`: Extracts basic user fields (name, age) from conversation

## Available Biomarkers

- `helios`: Wellness indicators (distress, stress, burnout, fatigue)
- `apollo`: Clinical probabilities (depression, anxiety) and symptoms
- `psyche`: Real-time affect detection
"""

from .client import SentinelClient
from .models import (
    # Safety analysis types
    ReasonerClassification,
    ReasonerBiomarkerSummary,
    ReasonerConversationContext,
    ReasonerConcordanceAnalysis,
    ReasonerFlags,
    ReasonerRecommendedActions,
    ReasonerResult,
    # Policy result types
    PolicyResult,
    # Progress types
    BiomarkerProgress,
    ProgressResult,
)

__version__ = "1.1.0"

__all__ = [
    # Client
    "SentinelClient",
    # Safety analysis types
    "ReasonerClassification",
    "ReasonerBiomarkerSummary",
    "ReasonerConversationContext",
    "ReasonerConcordanceAnalysis",
    "ReasonerFlags",
    "ReasonerRecommendedActions",
    "ReasonerResult",
    # Policy result types
    "PolicyResult",
    # Progress types
    "BiomarkerProgress",
    "ProgressResult",
]