"""
Thymia Sentinel - Monitors LiveKit audio streams for mental wellness indicators
"""

import asyncio
import json
import os
import time
from typing import Optional, Callable, Union, Awaitable, TypedDict, Literal
from loguru import logger
import websockets
from pydantic import BaseModel, Field

from livekit import rtc
from livekit.agents import JobContext


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
    Thymia Sentinel - Monitors audio for mental wellness indicators.

    Automatically captures all agent events and streams to Thymia server.
    Streams both user and agent audio as separate tracks.

    Example:
```python
        from livekit.plugins import thymia

        async def handle_policy_result(result: thymia.PolicyResult):
            policy = result.get('policy')
            policy_result = result.get('result', {})
            print(f"Policy '{policy}' result: {policy_result}")

        sentinel = thymia.Sentinel(
            user_label="user-123",
            date_of_birth="1990-01-01",
            birth_sex="MALE",
            on_policy_result=handle_policy_result,
        )

        await sentinel.start(ctx, session)
```
    """

    # Events to automatically capture from agent session
    EVENTS_TO_CAPTURE = [
        "user_state_changed",
        "agent_state_changed",
        "user_input_transcribed",
        "conversation_item_added",
        "agent_false_interruption",
        "function_tools_executed",
        "metrics_collected",
        "speech_created",
        "error",
        "close",
    ]

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
        """
        Initialize the Thymia Sentinel.

        Args:
            user_label: Unique identifier for the user (UUID format recommended)
            date_of_birth: Date of birth in YYYY-MM-DD format
            birth_sex: Either "MALE" or "FEMALE"
            language: Language code (default: "en-GB")
            buffer_strategy: Buffer processing strategy (default: "simple_reset")
            on_policy_result: Optional callback for PolicyResult (POLICY_RESULT events)
            server_url: WebSocket server URL (default: from THYMIA_SERVER_URL env var)
            api_key: Thymia API key (default: from THYMIA_API_KEY env var)
        """
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
            "THYMIA_SERVER_URL", # For internal use against experimental Lyra servers
            "wss://ws.thymia.ai"
        )
        self.thymia_api_key = api_key or os.getenv("THYMIA_API_KEY")
        if not self.thymia_api_key:
            raise ValueError("THYMIA_API_KEY environment variable or api_key parameter required")

        self._websocket = None
        self._audio_send_lock = asyncio.Lock()
        self._frame_counter = 0

    def _sanitize_for_json(self, obj):
        """Recursively sanitize objects to be JSON serializable"""
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        elif isinstance(obj, dict):
            return {k: self._sanitize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._sanitize_for_json(item) for item in obj]
        elif hasattr(obj, 'model_dump'):
            try:
                return self._sanitize_for_json(obj.model_dump())
            except Exception:
                return str(obj)
        elif hasattr(obj, '__dict__'):
            try:
                return self._sanitize_for_json(obj.__dict__)
            except Exception:
                return str(obj)
        else:
            return str(obj)

    async def send_event(self, event_type: str, data: dict):
        """Send event to the Thymia server using new protocol"""
        if self._websocket:
            try:
                sanitized_data = self._sanitize_for_json(data)

                # Handle user transcription events - only send final transcripts
                if event_type == 'user_input_transcribed':
                    if not sanitized_data.get('is_final', False):
                        return  # Skip interim transcripts
                    transcript_event = {
                        'type': 'TRANSCRIPT',
                        'speaker': 'user',
                        'text': sanitized_data.get('transcript', ''),
                        'is_final': True,
                        'language': sanitized_data.get('language'),
                        'timestamp': time.time()
                    }
                    await self._websocket.send(json.dumps(transcript_event))
                    logger.info(f"TRANSCRIPT [user]: {sanitized_data.get('transcript', '')}")

                # Handle conversation_item_added - extract agent messages
                elif event_type == 'conversation_item_added':
                    item = sanitized_data.get('item', {})
                    role = item.get('role')
                    content = item.get('content', [])

                    # Extract text from agent messages
                    if role == 'assistant' and content:
                        text_parts = []
                        for part in content:
                            if isinstance(part, dict) and part.get('type') == 'text':
                                text_parts.append(part.get('text', ''))
                            elif isinstance(part, str):
                                text_parts.append(part)

                        if text_parts:
                            agent_text = ' '.join(text_parts)
                            transcript_event = {
                                'type': 'TRANSCRIPT',
                                'speaker': 'agent',
                                'text': agent_text,
                                'is_final': True,
                                'timestamp': time.time()
                            }
                            await self._websocket.send(json.dumps(transcript_event))
                            logger.info(f"TRANSCRIPT [agent]: {agent_text}")

                    # Still send as META_DATA for other processing
                    meta_event = {
                        'type': 'META_DATA',
                        'event_name': event_type,
                        'data': sanitized_data,
                        'timestamp': time.time()
                    }
                    await self._websocket.send(json.dumps(meta_event))
                    logger.debug(f"📤 Sent META_DATA: {event_type}")

                else:
                    # All other events become META_DATA
                    meta_event = {
                        'type': 'META_DATA',
                        'event_name': event_type,
                        'data': sanitized_data,
                        'timestamp': time.time()
                    }
                    await self._websocket.send(json.dumps(meta_event))
                    logger.debug(f"📤 Sent META_DATA: {event_type}")
            except Exception as e:
                logger.error(f"Failed to send event {event_type}: {e}")

    def _create_event_handler(self, event_name: str):
        """Factory to create event handlers"""
        def handler(message):
            if hasattr(message, 'model_dump'):
                data = message.model_dump()
            elif hasattr(message, '__dict__'):
                data = message.__dict__
            else:
                data = {'raw': str(message)}

            asyncio.create_task(self.send_event(event_name, data))

        return handler

    def _register_event_handlers(self, session):
        """Register all event handlers on the session"""
        for event_name in self.EVENTS_TO_CAPTURE:
            try:
                session.on(event_name, self._create_event_handler(event_name))
                logger.debug(f"Registered handler for: {event_name}")
            except Exception as e:
                logger.warning(f"Could not register {event_name}: {e}")

    def _log_policy_result(self, message: dict):
        """Log policy execution result"""
        logger.info("=" * 60)
        logger.info(f"POLICY_RESULT [{message.get('policy', 'unknown')}]")
        logger.info("=" * 60)

        logger.info(f"  turn: {message.get('triggered_at_turn')} | ts: {message.get('timestamp')}")

        result = message.get('result', {})
        result_type = result.get('type', 'unknown')

        if result_type == 'safety_analysis':
            # Safety analysis result
            classification = result.get('classification', {})
            logger.info(f"  level: {classification.get('level')} | alert: {classification.get('alert')} | confidence: {classification.get('confidence')}")
            concerns = result.get('concerns', [])
            if concerns:
                logger.info(f"  concerns: {concerns}")
            actions = result.get('recommended_actions', {})
            if actions.get('for_agent'):
                logger.info(f"  for_agent: {actions['for_agent']}")

        elif result_type == 'extracted_fields':
            # Field extraction result
            fields = result.get('fields', {})
            for field_name, field_data in fields.items():
                value = field_data.get('value')
                confidence = field_data.get('confidence', 0)
                if value is not None:
                    logger.info(f"  {field_name}: {value} (conf={confidence:.2f})")
                else:
                    logger.info(f"  {field_name}: null")
            if result.get('notes'):
                logger.info(f"  notes: {result['notes']}")

        else:
            # Generic/unknown policy result - just dump the result
            logger.info(f"  result_type: {result_type}")
            for key, value in result.items():
                if key != 'type':
                    logger.info(f"  {key}: {value}")

        logger.info("=" * 60)

    async def start(self, ctx: JobContext, session=None) -> Optional[asyncio.Task]:
        """
        Start the Sentinel to monitor audio streams.

        Args:
            ctx: JobContext from LiveKit agent
            session: AgentSession (optional) - if provided, will capture all events

        Returns:
            Optional[asyncio.Task]: The background task running the sentinel
        """

        async def _run_sentinel():
            logger.info("🛡️  Thymia Sentinel activated")
            logger.info(f"Monitoring user: {self.user_label}")
            logger.info(f"Connected to: {self.server_url}")

            websocket = None

            try:
                websocket = await websockets.connect(self.server_url, max_size=None)
                self._websocket = websocket
                logger.info("Connected to Thymia server")

                # Send configuration with API key
                config = {
                    'api_key': self.thymia_api_key,
                    'user_label': self.user_label,
                    'date_of_birth': self.date_of_birth,
                    'birth_sex': self.birth_sex,
                    'language': self.language,
                    'buffer_strategy': self.buffer_strategy,
                    'biomarkers': self.biomarkers,
                    'policies': self.policies,
                    'sample_rate': 16000,
                    'progress_updates': {
                        'enabled': True if self.on_progress_result is not None else False,
                        'interval_seconds': self.progress_updates_frequency
                    },
                    'format': 'pcm16',
                    'channels': 1
                }
                await websocket.send(json.dumps(config))
                logger.info("Sentinel configuration sent")

                # Register event handlers if session provided
                if session:
                    logger.info("📡 Registering event handlers...")
                    self._register_event_handlers(session)
                    logger.info("✅ Event handlers registered")

                # Wait for participant
                participant = await ctx.wait_for_participant()
                logger.info(f"👤 Monitoring audio from {participant.identity}")

                done = asyncio.Event()

                async def receive_server_events():
                    """Receive and handle events from server"""
                    try:
                        while not done.is_set():
                            message_json = await websocket.recv()
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
                                logger.warning(f"Unknown message from server: {list(message.keys())}")

                    except websockets.exceptions.ConnectionClosed:
                        logger.info("Server closed connection")
                        done.set()
                    except Exception as e:
                        logger.error(f"Error receiving server events: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                        done.set()

                result_task = asyncio.create_task(receive_server_events())

                # Stream user audio
                async def stream_audio(track: rtc.Track, track_type: str):
                    """Stream audio frames with AUDIO_HEADER protocol"""
                    try:
                        audio_stream = rtc.AudioStream(track, sample_rate=16000, num_channels=1)
                        frame_count = 0

                        async for event in audio_stream:
                            if done.is_set():
                                break

                            frame_count += 1
                            audio_data = bytes(event.frame.data)

                            # Uncomment for frame-level debugging:
                            # if frame_count % 100 == 0:
                            #     logger.debug(f"📏 [{track_type}] Frame #{frame_count}: {len(audio_data)} bytes")

                            async with self._audio_send_lock:
                                header = {
                                    'type': 'AUDIO_HEADER',
                                    'track': track_type,
                                    'format': 'pcm16',
                                    'sample_rate': 16000,
                                    'channels': 1,
                                    'bytes': len(audio_data),
                                }
                                await websocket.send(json.dumps(header))
                                await websocket.send(audio_data)

                        logger.info(f"Finished streaming {track_type} audio ({frame_count} frames)")

                    except Exception as e:
                        logger.error(f"Audio streaming error ({track_type}): {e}")
                        import traceback
                        logger.error(traceback.format_exc())

                # Subscribe to remote participant audio (user)
                def on_track_subscribed(
                    track: rtc.Track,
                    publication: rtc.TrackPublication,
                    participant: rtc.RemoteParticipant,
                ):
                    if track.kind != rtc.TrackKind.KIND_AUDIO:
                        return
                    logger.info(f"🎤 Subscribed to user audio from {participant.identity}")
                    asyncio.create_task(stream_audio(track, 'user'))

                ctx.room.on("track_subscribed", on_track_subscribed)

                # Check for existing user audio tracks
                for publication in participant.track_publications.values():
                    if publication.subscribed and publication.track and publication.track.kind == rtc.TrackKind.KIND_AUDIO:
                        logger.info(f"🎤 Found existing user audio track")
                        asyncio.create_task(stream_audio(publication.track, 'user'))

                # Subscribe to local participant audio (agent TTS)
                def on_local_track_published(publication: rtc.LocalTrackPublication):
                    if publication.track and publication.track.kind == rtc.TrackKind.KIND_AUDIO:
                        logger.info("🤖 Capturing agent TTS audio")
                        asyncio.create_task(stream_audio(publication.track, 'agent'))

                def on_local_track_published_room(publication: rtc.LocalTrackPublication, participant: rtc.LocalParticipant):
                    on_local_track_published(publication)

                # Check existing local tracks
                local_participant = ctx.room.local_participant
                if local_participant:
                    for publication in local_participant.track_publications.values():
                        if isinstance(publication, rtc.LocalTrackPublication):
                            on_local_track_published(publication)

                ctx.room.on("local_track_published", on_local_track_published_room)
                logger.info("👂 Listening for agent audio tracks")

                # Wait until done
                await done.wait()

            except asyncio.CancelledError:
                logger.info("🛡️  Sentinel deactivated")
                raise
            except Exception as e:
                logger.error(f"Sentinel error: {e}")
                import traceback
                logger.error(traceback.format_exc())
            finally:
                self._websocket = None
                if websocket:
                    await websocket.close()

        task = asyncio.create_task(_run_sentinel())

        async def cleanup():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        ctx.add_shutdown_callback(cleanup)
        return task