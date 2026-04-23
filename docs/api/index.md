# API Reference

## SentinelClient

::: thymia_sentinel.SentinelClient
    options:
      show_source: false
      heading_level: 3

### Event Handlers

Register handlers using decorators or constructor callbacks:

```python
sentinel = SentinelClient(
    user_label="user-123",
    policies=["demo_wellbeing_awareness"],
)

# Decorator pattern (recommended)
@sentinel.on_policy_result
async def handle_policy(result: PolicyResult):
    level = result["result"]["classification"]["level"]
    if level >= 2:
        await take_action(result)

@sentinel.on_progress
async def handle_progress(result: ProgressResult):
    for name, status in result["biomarkers"].items():
        print(f"{name}: {status['speech_seconds']:.1f}s")

# Alternative: constructor callbacks
sentinel = SentinelClient(
    on_policy_result=handle_policy,
    on_progress_result=handle_progress,
    # ...
)
```

Multiple handlers can be registered for each event type. Both sync and async handlers are supported.

---

## Type Definitions

### PolicyResult

The main result type received from the Lyra server.

```python
class PolicyResult(TypedDict, total=False):
    type: Literal["POLICY_RESULT"]
    policy: str                    # Executor type (e.g., "safety_analysis", "passthrough")
    policy_name: str               # Policy name (e.g., "demo_wellbeing_awareness", "demo_field_extraction")
    triggered_at_turn: int         # User turn that triggered this policy
    timestamp: float               # Unix timestamp
    result: dict                   # Policy-specific result data
```

!!! note
    `policy` is the **executor type** (e.g., `"safety_analysis"`), while `policy_name` is the **name of the specific policy** from your org config (e.g., `"demo_wellbeing_awareness"`). When multiple policies share the same executor, use `policy_name` to distinguish them.

### ProgressResult

Progress update for biomarker collection.

```python
class ProgressResult(TypedDict, total=False):
    type: Literal["PROGRESS"]
    biomarkers: dict[str, BiomarkerProgress]
    timestamp: float

class BiomarkerProgress(TypedDict, total=False):
    speech_seconds: float          # Seconds of speech collected
    trigger_seconds: float         # Seconds required to trigger
    processing: bool               # Whether analysis is in progress
```

### Wellbeing Awareness Analysis Types

```python
class ReasonerClassification(TypedDict):
    level: int                     # Awareness level 0-3
    alert: str
    confidence: Literal["low", "medium", "high"]

class ReasonerRecommendedActions(TypedDict, total=False):
    for_agent: str                 # Guidance for the AI agent
    for_human_reviewer: str | None # Notes for human reviewers
    urgency: Literal["routine", "follow_up", "attentive", "supportive"]

class ReasonerConcordanceAnalysis(TypedDict, total=False):
    scenario: str                  # mood_not_discussed, concordance, minimization, amplification
    agreement_level: str           # high, moderate, low, n/a
    mismatch_type: str | None
    mismatch_severity: str         # none, mild, moderate, severe

class ReasonerFlags(TypedDict, total=False):
    suicidal_content: bool
    severe_mismatch: bool
    mood_not_yet_discussed: bool
    critical_symptoms: bool
```

### Biomarker Summary

```python
class ReasonerBiomarkerSummary(BaseModel):
    # Helios wellness scores (0-1)
    distress: float | None
    stress: float | None
    burnout: float | None
    fatigue: float | None
    low_self_esteem: float | None

    # Psyche scores (0-1)
    neutral: float | None
    happy: float | None
    sad: float | None
    angry: float | None
    fearful: float | None
    disgusted: float | None
    surprised: float | None

    # Apollo disorder probabilities (0-1)
    depression_probability: float | None
    anxiety_probability: float | None

    # Depression symptoms (0-1)
    symptom_anhedonia: float | None
    symptom_low_mood: float | None
    symptom_sleep_issues: float | None
    symptom_low_energy: float | None
    symptom_appetite: float | None
    symptom_worthlessness: float | None
    symptom_concentration: float | None
    symptom_psychomotor: float | None

    # Anxiety symptoms (0-1)
    symptom_nervousness: float | None
    symptom_uncontrollable_worry: float | None
    symptom_excessive_worry: float | None
    symptom_trouble_relaxing: float | None
    symptom_restlessness: float | None
    symptom_irritability: float | None
    symptom_dread: float | None

    # Summary
    interpretation: str | None
```

---

## Protocol Reference

### WebSocket Messages

#### Authentication

The API key is sent as an `X-Api-Key` HTTP header on the WebSocket upgrade request. The `SentinelClient` handles this automatically when you provide the `api_key` parameter or `THYMIA_API_KEY` environment variable.

#### Configuration (Client → Server)

Sent immediately after connection:

```json
{
    "user_label": "user-123",
    "language": "en-GB",
    "biomarkers": ["helios", "apollo"],
    "policies": ["demo_wellbeing_awareness"],
    "audio_config": {
        "sample_rate": 16000,
        "format": "pcm16",
        "channels": 1
    },
    "progress_updates": {
        "enabled": true,
        "interval_seconds": 1.0
    }
}
```

#### Audio Header (Client → Server)

Sent before each audio chunk:

```json
{
    "type": "AUDIO_HEADER",
    "track": "user",
    "format": "pcm16",
    "sample_rate": 16000,
    "channels": 1,
    "bytes": 3200
}
```

Immediately followed by raw audio bytes.

#### Transcript (Client → Server)

```json
{
    "type": "TRANSCRIPT",
    "speaker": "user",
    "text": "I'm feeling okay today",
    "is_final": true,
    "language": "en-GB",
    "timestamp": 1234567890.123
}
```

#### Policy Result (Server → Client)

```json
{
    "type": "POLICY_RESULT",
    "policy": "safety_analysis",
    "policy_name": "demo_wellbeing_awareness",
    "triggered_at_turn": 3,
    "timestamp": 1234567890.456,
    "result": {
        "type": "safety_analysis",
        "classification": { ... },
        "concerns": [ ... ],
        "recommended_actions": { ... }
    }
}
```

#### Progress (Server → Client)

```json
{
    "type": "PROGRESS",
    "biomarkers": {
        "helios": {
            "speech_seconds": 8.2,
            "trigger_seconds": 10.0,
            "processing": false
        }
    },
    "timestamp": 1234567890.789
}
```

#### Error (Server → Client)

```json
{
    "type": "ERROR",
    "error_code": "INVALID_CONFIG",
    "message": "Invalid date_of_birth format",
    "details": "Expected YYYY-MM-DD"
}
```
