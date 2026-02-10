"""
LiveKit Thymia Plugin - Mental Wellness Analysis for LiveKit Agents

This plugin streams audio from LiveKit to a Thymia WebSocket server for analysis.
It extends thymia-sentinel with LiveKit-specific RTCTrack integration.
"""

from .sentinel import Sentinel

# Re-export models from thymia_sentinel for convenience
from thymia_sentinel import (
    ReasonerResult,
    ReasonerClassification,
    ReasonerBiomarkerSummary,
    ReasonerConversationContext,
    ReasonerConcordanceAnalysis,
    ReasonerFlags,
    ReasonerRecommendedActions,
    PolicyResult,
    ProgressResult,
    BiomarkerProgress,
)

__all__ = [
    "Sentinel",
    "ReasonerResult",
    "ReasonerClassification",
    "ReasonerBiomarkerSummary",
    "ReasonerConversationContext",
    "ReasonerConcordanceAnalysis",
    "ReasonerFlags",
    "ReasonerRecommendedActions",
    "PolicyResult",
    "ProgressResult",
    "BiomarkerProgress",
]
