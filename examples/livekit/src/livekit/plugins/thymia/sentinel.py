"""
Thymia Sentinel for LiveKit - Monitors LiveKit audio streams for mental wellness indicators.

This module extends thymia-sentinel with LiveKit-specific RTCTrack integration
for automatic audio capture from LiveKit rooms.
"""

import asyncio
import json
import os
import time
from typing import Optional, Callable, Union, Awaitable, TypeVar

from loguru import logger
import websockets

from livekit import rtc
from livekit.agents import JobContext

# Import models from thymia_sentinel
from thymia_sentinel import PolicyResult, ProgressResult

# Type variable for decorator return type preservation
F = TypeVar("F", bound=Callable)


class Sentinel:
    """
    Thymia Sentinel - Monitors audio for mental wellness indicators.

    Automatically captures all agent events and streams to Thymia server.
    Streams both user and agent audio as separate tracks.

    Example using decorators:
        ```python
        from livekit.plugins import thymia

        sentinel = thymia.Sentinel(
            user_label="user-123",
            policies=["demo_wellbeing_awareness"],
        )

        @sentinel.on_policy_result
        async def handle_policy(result: thymia.PolicyResult):
            level = result["result"]["classification"]["level"]
            if level >= 2:
                await apply_safety_action(result)

        @sentinel.on_progress
        async def handle_progress(result: thymia.ProgressResult):
            for name, status in result["biomarkers"].items():
                print(f"{name}: {status['speech_seconds']:.1f}s")

        await sentinel.start(ctx, session)
        ```

    Example using callbacks:
        ```python
        sentinel = thymia.Sentinel(
            user_label="user-123",
            on_policy_result=handle_policy_result,
            on_progress_result=handle_progress,
        )
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
        user_label: Optional[str] = None,
        date_of_birth: Optional[str] = None,
        birth_sex: Optional[str] = None,
        language: str = "en-GB",
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
            user_label: Optional unique identifier for the user (UUID format recommended)
            date_of_birth: Optional date of birth in YYYY-MM-DD format (improves accuracy, imputed from voice if omitted)
            birth_sex: Optional, either "MALE" or "FEMALE" (improves accuracy, imputed from voice if omitted)
            language: Language code (default: "en-GB")
            on_policy_result: Optional callback for PolicyResult (POLICY_RESULT events)
            server_url: WebSocket server URL (default: from THYMIA_SERVER_URL env var)
            api_key: Thymia API key (default: from THYMIA_API_KEY env var)
        """
        self.user_label = user_label
        self.date_of_birth = date_of_birth
        self.birth_sex = birth_sex
        self.language = language
        self.policies = policies
        self.biomarkers = biomarkers if biomarkers is not None else ["helios"]
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

        # Handler lists for callbacks (constructor + decorator-registered)
        self._policy_result_handlers: list[
            Union[Callable[[PolicyResult], None], Callable[[PolicyResult], Awaitable[None]]]
        ] = []
        self._progress_handlers: list[
            Union[Callable[[ProgressResult], None], Callable[[ProgressResult], Awaitable[None]]]
        ] = []

        # Add constructor callbacks to handler lists if provided
        if on_policy_result is not None:
            self._policy_result_handlers.append(on_policy_result)
        if on_progress_result is not None:
            self._progress_handlers.append(on_progress_result)

    def on_policy_result(self, func: F) -> F:
        """
        Decorator to register a policy result handler.

        The handler will be called whenever a policy result is received from
        the server. Multiple handlers can be registered.

        Example:
            ```python
            @sentinel.on_policy_result
            async def handle_policy(result: PolicyResult):
                level = result["result"]["classification"]["level"]
                if level >= 2:
                    await apply_safety_action(result)
            ```
        """
        self._policy_result_handlers.append(func)
        return func

    def on_progress(self, func: F) -> F:
        """
        Decorator to register a progress handler.

        The handler will be called periodically with biomarker extraction
        progress updates. Multiple handlers can be registered.

        Note: Registering a progress handler automatically enables progress
        updates from the server.

        Example:
            ```python
            @sentinel.on_progress
            async def handle_progress(result: ProgressResult):
                for name, status in result["biomarkers"].items():
                    pct = (status["speech_seconds"] / status["trigger_seconds"]) * 100
                    print(f"{name}: {pct:.0f}%")
            ```
        """
        self._progress_handlers.append(func)
        return func

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
                    logger.debug(f"Sent META_DATA: {event_type}")

                else:
                    # All other events become META_DATA
                    meta_event = {
                        'type': 'META_DATA',
                        'event_name': event_type,
                        'data': sanitized_data,
                        'timestamp': time.time()
                    }
                    await self._websocket.send(json.dumps(meta_event))
                    logger.debug(f"Sent META_DATA: {event_type}")
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
        policy = message.get('policy', 'unknown')
        policy_name = message.get('policy_name', policy)
        logger.info("=" * 60)
        logger.info(f"POLICY_RESULT [{policy_name}] (executor={policy})")
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
            logger.info("Thymia Sentinel activated")
            logger.info(f"Monitoring user: {self.user_label}")
            logger.info(f"Connected to: {self.server_url}")

            websocket = None

            try:
                websocket = await websockets.connect(
                    self.server_url,
                    max_size=None,
                    additional_headers={"X-Api-Key": self.thymia_api_key},
                )
                self._websocket = websocket
                logger.info("Connected to Thymia server")

                # Enable progress updates if any handlers are registered
                progress_enabled = len(self._progress_handlers) > 0

                # Send configuration
                config = {
                    'language': self.language,
                    'biomarkers': self.biomarkers,
                    'policies': self.policies,
                    'audio_config': {
                        'sample_rate': 16000,
                        'format': 'pcm16',
                        'channels': 1,
                    },
                    'progress_updates': {
                        'enabled': progress_enabled,
                        'interval_seconds': self.progress_updates_frequency
                    },
                }
                if self.user_label is not None:
                    config['user_label'] = self.user_label
                if self.date_of_birth is not None:
                    config['date_of_birth'] = self.date_of_birth
                if self.birth_sex is not None:
                    config['birth_sex'] = self.birth_sex
                await websocket.send(json.dumps(config))
                logger.info("Sentinel configuration sent")

                # Register event handlers if session provided
                if session:
                    logger.info("Registering event handlers...")
                    self._register_event_handlers(session)
                    logger.info("Event handlers registered")

                # Wait for participant
                participant = await ctx.wait_for_participant()
                logger.info(f"Monitoring audio from {participant.identity}")

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
                                    f"Buffer status: "
                                    f"{message.get('buffer_duration', 0):.1f}s buffered, "
                                    f"{message.get('speech_duration', 0):.1f}s speech"
                                )

                            elif event_type == 'ERROR':
                                error_code = message.get('error_code', 'UNKNOWN')
                                error_msg = message.get('message', 'Unknown error')
                                logger.error(f"Server error [{error_code}]: {error_msg}")
                                if message.get('details'):
                                    logger.error(f"   Details: {message['details']}")

                            elif event_type == 'POLICY_RESULT':
                                self._log_policy_result(message)
                                for handler in self._policy_result_handlers:
                                    try:
                                        if asyncio.iscoroutinefunction(handler):
                                            await handler(message)
                                        else:
                                            handler(message)
                                    except Exception as e:
                                        logger.error(f"Error in policy result handler: {e}")

                            elif event_type == 'PROGRESS':
                                for handler in self._progress_handlers:
                                    try:
                                        if asyncio.iscoroutinefunction(handler):
                                            await handler(message)
                                        else:
                                            handler(message)
                                    except Exception as e:
                                        logger.error(f"Error in progress handler: {e}")

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
                            #     logger.debug(f"[{track_type}] Frame #{frame_count}: {len(audio_data)} bytes")

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
                    logger.info(f"Subscribed to user audio from {participant.identity}")
                    asyncio.create_task(stream_audio(track, 'user'))

                ctx.room.on("track_subscribed", on_track_subscribed)

                # Check for existing user audio tracks
                for publication in participant.track_publications.values():
                    if publication.subscribed and publication.track and publication.track.kind == rtc.TrackKind.KIND_AUDIO:
                        logger.info(f"Found existing user audio track")
                        asyncio.create_task(stream_audio(publication.track, 'user'))

                # Subscribe to local participant audio (agent TTS)
                def on_local_track_published(publication: rtc.LocalTrackPublication):
                    if publication.track and publication.track.kind == rtc.TrackKind.KIND_AUDIO:
                        logger.info("Capturing agent TTS audio")
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
                logger.info("Listening for agent audio tracks")

                # Wait until done
                await done.wait()

            except asyncio.CancelledError:
                logger.info("Sentinel deactivated")
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