"""
Thymia Sentinel - Data models for policy results and biomarker progress.

These models define the structure of events received from the Thymia Lyra server.
"""

from typing import Optional, Literal
from typing_extensions import TypedDict
from pydantic import BaseModel, Field


# =============================================================================
# Safety Analysis Types
# =============================================================================


class ReasonerClassification(TypedDict):
    """Safety classification from the reasoner.

    Attributes:
        level: Risk level from 0-3 (0=no concern, 3=crisis)
        alert: Alert type indicating recommended response
        confidence: Confidence in the classification
    """

    level: int
    alert: str
    confidence: Literal["low", "medium", "high"]


class ReasonerBiomarkerSummary(BaseModel):
    """Summary of biomarkers used in safety analysis.

    Contains scores from multiple biomarker models:
    - Helios: Wellness indicators (distress, stress, burnout, etc.)
    - Psyche: Real-time affect detection
    - Apollo: Clinical disorder probabilities and symptom severities
    """

    # Helios wellness scores (0-1 scale)
    distress: Optional[float] = Field(default=None, description="Distress score 0-1")
    stress: Optional[float] = Field(default=None, description="Stress score 0-1")
    burnout: Optional[float] = Field(default=None, description="Burnout score 0-1")
    fatigue: Optional[float] = Field(default=None, description="Fatigue score 0-1")
    low_self_esteem: Optional[float] = Field(
        default=None, description="Low self-esteem score 0-1"
    )

    # Psyche scores (real-time affect, 0-1 scale)
    neutral: Optional[float] = Field(default=None, description="Neutral/flat affect 0-1")
    happy: Optional[float] = Field(default=None, description="Happy/joy 0-1")
    sad: Optional[float] = Field(default=None, description="Sadness 0-1")
    angry: Optional[float] = Field(default=None, description="Anger/frustration 0-1")
    fearful: Optional[float] = Field(default=None, description="Fear/anxiety in voice 0-1")
    disgusted: Optional[float] = Field(default=None, description="Disgust 0-1")
    surprised: Optional[float] = Field(default=None, description="Surprise 0-1")

    # Apollo disorder probabilities (0-1 scale)
    depression_probability: Optional[float] = Field(
        default=None, description="Depression probability 0-1"
    )
    anxiety_probability: Optional[float] = Field(
        default=None, description="Anxiety probability 0-1"
    )

    # Apollo depression symptom severities (0-1 scale)
    symptom_anhedonia: Optional[float] = Field(
        default=None, description="Anhedonia severity 0-1"
    )
    symptom_low_mood: Optional[float] = Field(
        default=None, description="Low mood severity 0-1"
    )
    symptom_sleep_issues: Optional[float] = Field(
        default=None, description="Sleep issues severity 0-1"
    )
    symptom_low_energy: Optional[float] = Field(
        default=None, description="Low energy severity 0-1"
    )
    symptom_appetite: Optional[float] = Field(
        default=None, description="Appetite changes severity 0-1"
    )
    symptom_worthlessness: Optional[float] = Field(
        default=None, description="Worthlessness severity 0-1"
    )
    symptom_concentration: Optional[float] = Field(
        default=None, description="Concentration issues severity 0-1"
    )
    symptom_psychomotor: Optional[float] = Field(
        default=None, description="Psychomotor changes severity 0-1"
    )

    # Apollo anxiety symptom severities (0-1 scale)
    symptom_nervousness: Optional[float] = Field(
        default=None, description="Nervousness severity 0-1"
    )
    symptom_uncontrollable_worry: Optional[float] = Field(
        default=None, description="Uncontrollable worry severity 0-1"
    )
    symptom_excessive_worry: Optional[float] = Field(
        default=None, description="Excessive worry severity 0-1"
    )
    symptom_trouble_relaxing: Optional[float] = Field(
        default=None, description="Trouble relaxing severity 0-1"
    )
    symptom_restlessness: Optional[float] = Field(
        default=None, description="Restlessness severity 0-1"
    )
    symptom_irritability: Optional[float] = Field(
        default=None, description="Irritability severity 0-1"
    )
    symptom_dread: Optional[float] = Field(default=None, description="Dread severity 0-1")

    # Summary
    interpretation: Optional[str] = Field(
        default=None, description="Human-readable interpretation"
    )


class ReasonerConversationContext(TypedDict, total=False):
    """Context about the conversation analyzed."""

    mood_discussed: bool
    topics: list[str]
    user_insight: str  # good, fair, poor, unknown


class ReasonerConcordanceAnalysis(TypedDict, total=False):
    """Analysis of text-biomarker concordance.

    Detects patterns where what the user says differs from what their
    voice biomarkers indicate (minimization, amplification, etc.).
    """

    scenario: str  # mood_not_discussed, mood_discussed, concordance, minimization, amplification
    agreement_level: str  # high, moderate, low, n/a
    mismatch_type: Optional[str]
    mismatch_severity: str  # none, mild, moderate, severe


class ReasonerFlags(TypedDict, total=False):
    """Safety flags from analysis."""

    suicidal_content: bool
    severe_mismatch: bool
    mood_not_yet_discussed: bool
    critical_symptoms: bool


class ReasonerRecommendedActions(TypedDict, total=False):
    """Recommended actions from the reasoner."""

    for_agent: str  # What the AI agent should do/say next
    for_human_reviewer: Optional[str]  # Notes for human reviewer
    urgency: Literal["routine", "within_week", "within_48hrs", "within_24hrs", "immediate"]


class ReasonerResult(TypedDict, total=False):
    """Full safety assessment result from the reasoner.

    This is the detailed result structure for 'safety' policy executions.
    """

    type: Literal["RESULT"]
    analysis_type: Literal["initial", "update", "holistic"]
    segment_number: int
    timestamp: str  # Time range of segment analyzed (e.g., '0-60s')
    user_turn_count: int

    classification: ReasonerClassification
    concerns: list[str]
    rationale: str

    biomarker_summary: Optional[ReasonerBiomarkerSummary]
    conversation_context: Optional[ReasonerConversationContext]
    concordance_analysis: Optional[ReasonerConcordanceAnalysis]
    flags: Optional[ReasonerFlags]
    recommended_actions: ReasonerRecommendedActions


# =============================================================================
# Policy Result Types
# =============================================================================


class PolicyResult(TypedDict, total=False):
    """Policy execution result from the Lyra server.

    This is the generic container for any policy executor output (safety analysis,
    field extraction, biomarker passthrough, etc.).

    Attributes:
        type: Always "POLICY_RESULT"
        policy: Name of the policy that was executed (e.g., "demo_wellbeing_awareness", "demo_field_extraction")
        triggered_at_turn: The user turn number that triggered this policy
        timestamp: Unix timestamp when the result was generated
        result: Policy-specific result data (structure varies by policy type)
    """

    type: Literal["POLICY_RESULT"]
    policy: str
    triggered_at_turn: int
    timestamp: float
    result: dict


# =============================================================================
# Progress Types
# =============================================================================


class BiomarkerProgress(TypedDict, total=False):
    """Progress status for a single biomarker.

    Attributes:
        speech_seconds: Seconds of speech collected for this biomarker
        trigger_seconds: Seconds of speech required to trigger analysis
        processing: Whether analysis is currently in progress
    """

    speech_seconds: float
    trigger_seconds: float
    processing: bool


class ProgressResult(TypedDict, total=False):
    """Progress update from the Lyra server.

    Sent periodically to report biomarker collection progress.

    Attributes:
        type: Always "PROGRESS"
        biomarkers: Dict mapping biomarker name to its progress status
        timestamp: Unix timestamp of this progress update
    """

    type: Literal["PROGRESS"]
    biomarkers: dict[str, BiomarkerProgress]
    timestamp: float