"""
Thymia Sentinel for Pipecat - Monitors audio streams for mental wellness indicators
"""
import asyncio
import json
import os
import time
import traceback
from typing import Optional, Callable, Union, Awaitable, TypedDict, Literal
from loguru import logger
import websockets
from pydantic import BaseModel, Field

SAMPLE_RATE = 16000

# Reasoner Result Event types
class ReasonerClassification(TypedDict):
    """Safety classification from reasoner"""
    level: int  # Risk level 0-3
    alert: Literal["none", "monitor", "professional_referral", "crisis"]
    confidence: Literal["low", "medium", "high"]


class ReasonerBiomarkerSummary(BaseModel):
    """Summary of biomarkers used in analysis"""
    # Helios wellness scores
    distress: Optional[float] = Field(default=None, description="Distress score 0-1")
    stress: Optional[float] = Field(default=None, description="Stress score 0-1")
    burnout: Optional[float] = Field(default=None, description="Burnout score 0-1")
    fatigue: Optional[float] = Field(default=None, description="Fatigue score 0-1")
    low_self_esteem: Optional[float] = Field(default=None, description="Low self-esteem score 0-1")
    # Emotion scores (real-time)
    neutral: Optional[float] = Field(default=None, description="Neutral/flat affect 0-1")
    happy: Optional[float] = Field(default=None, description="Happy/joy 0-1")
    sad: Optional[float] = Field(default=None, description="Sadness 0-1")
    angry: Optional[float] = Field(default=None, description="Anger/frustration 0-1")
    fearful: Optional[float] = Field(default=None, description="Fear/anxiety in voice 0-1")
    disgusted: Optional[float] = Field(default=None, description="Disgust 0-1")
    surprised: Optional[float] = Field(default=None, description="Surprise 0-1")
    # Apollo disorder probabilities
    depression_probability: Optional[float] = Field(default=None, description="Depression probability 0-1")
    anxiety_probability: Optional[float] = Field(default=None, description="Anxiety probability 0-1")
    # Apollo depression symptom severities
    symptom_anhedonia: Optional[float] = Field(default=None, description="Anhedonia severity 0-1")
    symptom_low_mood: Optional[float] = Field(default=None, description="Low mood severity 0-1")
    symptom_sleep_issues: Optional[float] = Field(default=None, description="Sleep issues severity 0-1")
    symptom_low_energy: Optional[float] = Field(default=None, description="Low energy severity 0-1")
    symptom_appetite: Optional[float] = Field(default=None, description="Appetite changes severity 0-1")
    symptom_worthlessness: Optional[float] = Field(default=None, description="Worthlessness severity 0-1")
    symptom_concentration: Optional[float] = Field(default=None, description="Concentration issues severity 0-1")
    symptom_psychomotor: Optional[float] = Field(default=None, description="Psychomotor changes severity 0-1")
    # Apollo anxiety symptom severities
    symptom_nervousness: Optional[float] = Field(default=None, description="Nervousness severity 0-1")
    symptom_uncontrollable_worry: Optional[float] = Field(default=None, description="Uncontrollable worry severity 0-1")
    symptom_excessive_worry: Optional[float] = Field(default=None, description="Excessive worry severity 0-1")
    symptom_trouble_relaxing: Optional[float] = Field(default=None, description="Trouble relaxing severity 0-1")
    symptom_restlessness: Optional[float] = Field(default=None, description="Restlessness severity 0-1")
    symptom_irritability: Optional[float] = Field(default=None, description="Irritability severity 0-1")
    symptom_dread: Optional[float] = Field(default=None, description="Dread severity 0-1")
    # Summary
    interpretation: Optional[str] = Field(default=None, description="Human-readable interpretation")



class ReasonerConversationContext(TypedDict, total=False):
    """Context about the conversation analyzed"""
    mood_discussed: bool
    topics: list[str]
    user_insight: str  # good, fair, poor, unknown


class ReasonerConcordanceAnalysis(TypedDict, total=False):
    """Analysis of text-biomarker concordance"""
    scenario: str  # mood_not_discussed, mood_discussed, concordance, minimization, amplification
    agreement_level: str  # high, moderate, low, n/a
    mismatch_type: Optional[str]
    mismatch_severity: str  # none, mild, moderate, severe


class ReasonerFlags(TypedDict, total=False):
    """Safety flags from analysis"""
    suicidal_content: bool
    severe_mismatch: bool
    mood_not_yet_discussed: bool
    critical_symptoms: bool


class ReasonerRecommendedActions(TypedDict, total=False):
    """Recommended actions from reasoner"""
    for_agent: str  # What the AI agent should do/say next
    for_human_reviewer: Optional[str]  # Notes for human reviewer
    urgency: Literal["routine", "within_week", "within_48hrs", "within_24hrs", "immediate"]


class ReasonerResult(TypedDict, total=False):
    """Safety assessment results from the reasoner.

    This event contains the output from the ConversationalSafetyMonitor
    which analyzes conversation context and biomarkers to assess risk.
    """
    type: Literal["RESULT"]
    analysis_type: Literal["initial", "update", "holistic"]
    segment_number: int  # 1-indexed
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


class PolicyResult(TypedDict, total=False):
    """Policy execution result from the policy orchestrator.

    This is a generic result type for any policy executor (safety analysis,
    field extraction, biomarker passthrough, etc.).
    """
    type: Literal["POLICY_RESULT"]
    policy: str  # Policy name (e.g., "safety", "field_extraction")
    triggered_at_turn: int  # User turn that triggered this policy
    timestamp: float  # Unix timestamp

    # Policy-specific result - structure varies by policy type
    result: dict


class BiomarkerProgress(TypedDict, total=False):
    speech_seconds: float
    trigger_seconds: float
    processing: bool


class ProgressResult(TypedDict, total=False):
    type: Literal["PROGRESS"]
    biomarkers: dict[str, BiomarkerProgress]
    timestamp: float


class Sentinel:
    """
    Thymia Sentinel for Pipecat - Monitors audio for mental wellness indicators.

    Streams both user and agent audio, plus transcripts to Thymia server.

    Example:
    ```python
        from thymia import Sentinel

        async def handle_policy_result(result):
            print(f"Policy result: {result}")

        sentinel = Sentinel(
            user_label="user-123",
            date_of_birth="1990-01-01",
            birth_sex="MALE",
            on_policy_result=handle_policy_result,
        )

        await sentinel.connect()

        # In your audio loop:
        await sentinel.send_user_audio(audio_bytes)
        await sentinel.send_agent_audio(audio_bytes)
        await sentinel.send_user_transcript("Hello")
        await sentinel.send_agent_transcript("Hi there!")
    ```
    """

    def __init__(
        self,
        user_label: str,
        date_of_birth: str,
        birth_sex: str,
        language: str = "en-GB",
        buffer_strategy: str = "simple_reset",
        policies: Optional[list[str]] = None,
        biomarkers: Optional[list[str]] = None,
        on_policy_result: Optional[
            Union[Callable[[PolicyResult], None], Callable[[PolicyResult], Awaitable[None]]]
        ] = None,
        on_progress_result: Optional[
            Union[Callable[[ProgressResult], None], Callable[[ProgressResult], Awaitable[None]]]
        ] = None,
        progress_updates_frequency: float = 1.0,
        server_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.user_label = user_label
        self.date_of_birth = date_of_birth
        self.birth_sex = birth_sex
        self.language = language
        self.buffer_strategy = buffer_strategy
        self.policies = policies if policies is not None else ["passthrough"]
        self.biomarkers = biomarkers if biomarkers is not None else ["helios"]
        self.on_policy_result = on_policy_result
        self.on_progress_result = on_progress_result
        self.progress_updates_frequency = progress_updates_frequency
        self.server_url = server_url or os.getenv(
            "THYMIA_SERVER_URL",
            "wss://ws.thymia.ai"
        )
        self.thymia_api_key = api_key or os.getenv("THYMIA_API_KEY")
        if not self.thymia_api_key:
            raise ValueError("THYMIA_API_KEY environment variable or api_key parameter required")

        self._websocket = None
        self._audio_send_lock = asyncio.Lock()
        self._receive_task = None
        self._connected = False

    async def connect(self):
        """Connect to Thymia server and start receiving events."""
        logger.info("Thymia Sentinel (Pipecat) activated")
        logger.info(f"Monitoring user: {self.user_label}")
        logger.info(f"Connecting to: {self.server_url}")

        self._websocket = await websockets.connect(self.server_url, max_size=None)
        logger.info("Connected to Thymia server")

        # Send configuration
        config = {
            'api_key': self.thymia_api_key,
            'user_label': self.user_label,
            'date_of_birth': self.date_of_birth,
            'birth_sex': self.birth_sex,
            'language': self.language,
            'buffer_strategy': self.buffer_strategy,
            'biomarkers': self.biomarkers,
            'policies': self.policies,
            'sample_rate': SAMPLE_RATE,
            'progress_updates': {
                'enabled': True if self.on_progress_result is not None else False,
                'interval_seconds': self.progress_updates_frequency
            },
            'format': 'pcm16',
            'channels': 1
        }
        await self._websocket.send(json.dumps(config))
        logger.info("Sentinel configuration sent")

        # Start receiving server events
        self._receive_task = asyncio.create_task(self._receive_server_events())
        self._connected = True

    async def _receive_server_events(self):
        """Receive and handle events from server"""
        try:
            while self._websocket:
                message_json = await self._websocket.recv()
                message = json.loads(message_json)

                event_type = message.get('type')

                if event_type == 'STATUS':
                    logger.debug(
                        f"📊 Buffer status: "
                        f"{message.get('buffer_duration', 0):.1f}s buffered, "
                        f"{message.get('speech_duration', 0):.1f}s speech"
                    )

                elif event_type == 'ERROR':
                    error_code = message.get('error_code', 'UNKNOWN')
                    error_msg = message.get('message', 'Unknown error')
                    logger.error(f"❌ Server error [{error_code}]: {error_msg}")
                    if message.get('details'):
                        logger.error(f"   Details: {message['details']}")

                elif event_type == 'POLICY_RESULT':
                    self._log_policy_result(message)
                    if self.on_policy_result:
                        try:
                            if asyncio.iscoroutinefunction(self.on_policy_result):
                                await self.on_policy_result(message)
                            else:
                                self.on_policy_result(message)
                        except Exception as e:
                            logger.error(f"Error in on_policy_result callback: {e}")

                elif event_type == 'PROGRESS':
                    if self.on_progress_result:
                        try:
                            if asyncio.iscoroutinefunction(self.on_progress_result):
                                await self.on_progress_result(message)
                            else:
                                self.on_progress_result(message)
                        except Exception as e:
                            logger.error(f"Error in on_progress_result callback: {e}")

                else:
                    logger.debug(f"Server message: {event_type}")

        except websockets.exceptions.ConnectionClosed:
            logger.info("Server closed connection")
        except Exception as e:
            logger.error(f"Error receiving server events: {e}")
            logger.error(traceback.format_exc())

    def _log_policy_result(self, message: dict):
        """Log policy execution result"""
        logger.info("=" * 60)
        logger.info(f"POLICY_RESULT [{message.get('policy', 'unknown')}]")
        logger.info("=" * 60)

        logger.info(f"  turn: {message.get('triggered_at_turn')} | ts: {message.get('timestamp')}")

        result = message.get('result', {})
        result_type = result.get('type', 'unknown')

        if result_type == 'safety_analysis':
            classification = result.get('classification', {})
            logger.info(f"  level: {classification.get('level')} | alert: {classification.get('alert')} | confidence: {classification.get('confidence')}")
            concerns = result.get('concerns', [])
            if concerns:
                logger.info(f"  concerns: {concerns}")
            actions = result.get('recommended_actions', {})
            if actions.get('for_agent'):
                logger.info(f"  for_agent: {actions['for_agent']}")

        elif result_type == 'extracted_fields':
            fields = result.get('fields', {})
            for field_name, field_data in fields.items():
                value = field_data.get('value')
                confidence = field_data.get('confidence', 0)
                if value is not None:
                    logger.info(f"  {field_name}: {value} (conf={confidence:.2f})")

        logger.info("=" * 60)

    async def _send_audio(self, audio_data: bytes, track: str):
        """Send audio to Thymia server"""
        if not self._websocket or not self._connected:
            return

        async with self._audio_send_lock:
            try:
                header = {
                    'type': 'AUDIO_HEADER',
                    'track': track,
                    'format': 'pcm16',
                    'sample_rate': SAMPLE_RATE,
                    'channels': 1,
                    'bytes': len(audio_data),
                }
                await self._websocket.send(json.dumps(header))
                await self._websocket.send(audio_data)
            except Exception as e:
                logger.error(f"Error sending {track} audio: {e}")

    async def send_user_audio(self, audio_data: bytes):
        """Send user audio to Thymia server"""
        await self._send_audio(audio_data, 'user')

    async def send_agent_audio(self, audio_data: bytes):
        """Send agent audio to Thymia server"""
        await self._send_audio(audio_data, 'agent')

    async def send_user_transcript(self, text: str, is_final: bool = True):
        """Send user transcript to Thymia server"""
        if not self._websocket or not self._connected:
            return

        if not text:
            return

        try:
            transcript_event = {
                'type': 'TRANSCRIPT',
                'speaker': 'user',
                'text': text,
                'is_final': is_final,
                'language': self.language,
                'timestamp': time.time()
            }
            await self._websocket.send(json.dumps(transcript_event))
            logger.info(f"TRANSCRIPT [user]: {text}")
        except Exception as e:
            logger.error(f"Error sending user transcript: {e}")

    async def send_agent_transcript(self, text: str, is_final: bool = True):
        """Send agent transcript to Thymia server"""
        if not self._websocket or not self._connected:
            return

        if not text:
            return

        try:
            transcript_event = {
                'type': 'TRANSCRIPT',
                'speaker': 'agent',
                'text': text,
                'is_final': is_final,
                'timestamp': time.time()
            }
            await self._websocket.send(json.dumps(transcript_event))
            logger.info(f"TRANSCRIPT [agent]: {text}")
        except Exception as e:
            logger.error(f"Error sending agent transcript: {e}")

    async def close(self):
        """Close the connection to Thymia server"""
        self._connected = False
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        if self._websocket:
            await self._websocket.close()
            self._websocket = None
        logger.info("Thymia Sentinel deactivated")