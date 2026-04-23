"""
Thymia Sentinel - WebSocket client for streaming audio to the Lyra server.

The Sentinel monitors voice conversations for mental wellness indicators by
streaming audio and transcripts to Thymia's Lyra server, which performs
real-time biomarker extraction and policy-based safety analysis.
"""

import asyncio
import json
import os
import time
import traceback
from typing import Optional, Callable, Union, Awaitable, TypeVar

from loguru import logger
import websockets

from .models import PolicyResult, ProgressResult

# Type variable for decorator return type preservation
F = TypeVar("F", bound=Callable)


class SentinelClient:
    """
    Thymia Sentinel client for streaming audio to the Lyra server.

    Streams both user and agent audio, plus transcripts, to enable multimodal
    safety analysis combining speech biomarkers with conversation content.

    Example using decorators:
        ```python
        from thymia_sentinel import SentinelClient

        sentinel = SentinelClient(
            user_label="user-123",
            policies=["demo_wellbeing_awareness"],
        )

        @sentinel.on_policy_result
        async def handle_policy(result):
            level = result["result"]["classification"]["level"]
            if level >= 2:
                print(f"Elevated risk: {result['result']['concerns']}")

        @sentinel.on_progress
        async def handle_progress(result):
            for name, status in result["biomarkers"].items():
                print(f"{name}: {status['speech_seconds']:.1f}s")

        await sentinel.connect()

        # In your audio loop:
        await sentinel.send_user_audio(audio_bytes)
        await sentinel.send_agent_audio(audio_bytes)
        await sentinel.send_user_transcript("Hello")
        await sentinel.send_agent_transcript("Hi there!")

        await sentinel.close()
        ```

    Example using callbacks:
        ```python
        sentinel = SentinelClient(
            user_label="user-123",
            on_policy_result=handle_policy_result,
            on_progress_result=handle_progress,
        )
        ```

    Attributes:
        user_label: Optional unique identifier for the user being monitored
        date_of_birth: Optional user's date of birth (YYYY-MM-DD format, improves accuracy)
        birth_sex: Optional user's birth sex ("MALE" or "FEMALE", improves accuracy)
        language: Language code (default: "en-GB")
        sample_rate: Audio sample rate in Hz (default: 16000)
    """

    DEFAULT_SERVER_URL = "wss://ws.thymia.ai"
    DEFAULT_SAMPLE_RATE = 16000

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
        custom_policies: Optional[list[dict]] = None,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        server_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """
        Initialize the Sentinel client.

        Args:
            user_label: Optional unique identifier for the user (UUID format recommended)
            date_of_birth: Optional date of birth in YYYY-MM-DD format (improves accuracy, imputed from voice if omitted)
            birth_sex: Optional, either "MALE" or "FEMALE" (improves accuracy, imputed from voice if omitted)
            language: Language code (default: "en-GB")
            policies: List of policies to execute (e.g., ["demo_wellbeing_awareness"])
            biomarkers: List of biomarkers to extract (default: ["helios"])
            on_policy_result: Callback for policy results (sync or async)
            on_progress_result: Callback for progress updates (sync or async)
            progress_updates_frequency: How often to receive progress updates in seconds
            custom_policies: Optional inline policy definitions (requires feature flag on API key)
            sample_rate: Audio sample rate in Hz (default: 16000)
            server_url: WebSocket server URL (default: from THYMIA_SERVER_URL env or wss://ws.thymia.ai)
            api_key: Thymia API key (default: from THYMIA_API_KEY env)

        Raises:
            ValueError: If THYMIA_API_KEY is not provided and not in environment
        """
        self.user_label = user_label
        self.date_of_birth = date_of_birth
        self.birth_sex = birth_sex
        self.language = language
        self.policies = policies
        self.biomarkers = biomarkers if biomarkers is not None else ["helios"]
        self.custom_policies = custom_policies
        self.progress_updates_frequency = progress_updates_frequency
        self.sample_rate = sample_rate
        self.server_url = server_url or os.getenv(
            "THYMIA_SERVER_URL", self.DEFAULT_SERVER_URL
        )
        self.api_key = api_key or os.getenv("THYMIA_API_KEY")

        if not self.api_key:
            raise ValueError(
                "THYMIA_API_KEY environment variable or api_key parameter required"
            )

        self._websocket = None
        self._audio_send_lock = asyncio.Lock()
        self._receive_task = None
        self._connected = False

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

        Args:
            func: Async or sync function that receives a PolicyResult

        Returns:
            The original function (unchanged)
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

        Args:
            func: Async or sync function that receives a ProgressResult

        Returns:
            The original function (unchanged)
        """
        self._progress_handlers.append(func)
        return func

    async def connect(self) -> None:
        """
        Connect to the Lyra server and start receiving events.

        Establishes WebSocket connection, sends configuration, and starts
        the background task to receive server events.
        """
        logger.info("Thymia Sentinel activated")
        logger.info(f"Monitoring user: {self.user_label}")
        logger.info(f"Connecting to: {self.server_url}")

        self._websocket = await websockets.connect(
            self.server_url,
            max_size=None,
            additional_headers={"X-Api-Key": self.api_key},
        )
        logger.info("Connected to Thymia server")

        # Enable progress updates if any handlers are registered
        progress_enabled = len(self._progress_handlers) > 0

        # Send configuration
        config = {
            "language": self.language,
            "biomarkers": self.biomarkers,
            "policies": self.policies,
            "audio_config": {
                "sample_rate": self.sample_rate,
                "format": "pcm16",
                "channels": 1,
            },
            "progress_updates": {
                "enabled": progress_enabled,
                "interval_seconds": self.progress_updates_frequency,
            },
        }
        if self.user_label is not None:
            config["user_label"] = self.user_label
        if self.date_of_birth is not None:
            config["date_of_birth"] = self.date_of_birth
        if self.birth_sex is not None:
            config["birth_sex"] = self.birth_sex
        if self.custom_policies is not None:
            config["custom_policies"] = self.custom_policies
        await self._websocket.send(json.dumps(config))
        logger.info("Sentinel configuration sent")

        # Start receiving server events
        self._receive_task = asyncio.create_task(self._receive_server_events())
        self._connected = True

    async def _receive_server_events(self) -> None:
        """Receive and handle events from the server."""
        try:
            while self._websocket:
                message_json = await self._websocket.recv()
                message = json.loads(message_json)

                event_type = message.get("type")

                if event_type == "STATUS":
                    logger.debug(
                        f"Buffer status: "
                        f"{message.get('buffer_duration', 0):.1f}s buffered, "
                        f"{message.get('speech_duration', 0):.1f}s speech"
                    )

                elif event_type == "ERROR":
                    error_code = message.get("error_code", "UNKNOWN")
                    error_msg = message.get("message", "Unknown error")
                    logger.error(f"Server error [{error_code}]: {error_msg}")
                    if message.get("details"):
                        logger.error(f"   Details: {message['details']}")

                elif event_type == "POLICY_RESULT":
                    self._log_policy_result(message)
                    for handler in self._policy_result_handlers:
                        await self._invoke_callback(handler, message)

                elif event_type == "PROGRESS":
                    for handler in self._progress_handlers:
                        await self._invoke_callback(handler, message)

                else:
                    logger.debug(f"Server message: {event_type}")

        except websockets.exceptions.ConnectionClosed:
            logger.info("Server closed connection")
        except Exception as e:
            logger.error(f"Error receiving server events: {e}")
            logger.error(traceback.format_exc())

    async def _invoke_callback(self, callback, message) -> None:
        """Invoke a callback, handling both sync and async functions."""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(message)
            else:
                callback(message)
        except Exception as e:
            logger.error(f"Error in callback: {e}")

    def _log_policy_result(self, message: dict) -> None:
        """Log a policy execution result."""
        policy = message.get('policy', 'unknown')
        policy_name = message.get('policy_name', policy)
        logger.info("=" * 60)
        logger.info(f"POLICY_RESULT [{policy_name}] (executor={policy})")
        logger.info("=" * 60)

        logger.info(
            f"  turn: {message.get('triggered_at_turn')} | ts: {message.get('timestamp')}"
        )

        result = message.get("result", {})
        result_type = result.get("type", "unknown")

        if result_type == "safety_analysis":
            classification = result.get("classification", {})
            logger.info(
                f"  level: {classification.get('level')} | "
                f"alert: {classification.get('alert')} | "
                f"confidence: {classification.get('confidence')}"
            )
            concerns = result.get("concerns", [])
            if concerns:
                logger.info(f"  concerns: {concerns}")
            actions = result.get("recommended_actions", {})
            if actions.get("for_agent"):
                logger.info(f"  for_agent: {actions['for_agent']}")

        elif result_type == "extracted_fields":
            fields = result.get("fields", {})
            for field_name, field_data in fields.items():
                value = field_data.get("value")
                confidence = field_data.get("confidence", 0)
                if value is not None:
                    logger.info(f"  {field_name}: {value} (conf={confidence:.2f})")

        logger.info("=" * 60)

    async def _send_audio(self, audio_data: bytes, track: str) -> None:
        """Send audio data to the server."""
        if not self._websocket or not self._connected:
            return

        async with self._audio_send_lock:
            try:
                header = {
                    "type": "AUDIO_HEADER",
                    "track": track,
                    "format": "pcm16",
                    "sample_rate": self.sample_rate,
                    "channels": 1,
                    "bytes": len(audio_data),
                }
                await self._websocket.send(json.dumps(header))
                await self._websocket.send(audio_data)
            except Exception as e:
                logger.error(f"Error sending {track} audio: {e}")

    async def send_user_audio(self, audio_data: bytes) -> None:
        """
        Send user audio to the Lyra server.

        Args:
            audio_data: PCM16 audio bytes at the configured sample rate
        """
        await self._send_audio(audio_data, "user")

    async def send_agent_audio(self, audio_data: bytes) -> None:
        """
        Send agent audio to the Lyra server.

        Args:
            audio_data: PCM16 audio bytes at the configured sample rate
        """
        await self._send_audio(audio_data, "agent")

    async def _send_transcript(
        self, text: str, speaker: str, is_final: bool = True
    ) -> None:
        """Send a transcript to the server."""
        if not self._websocket or not self._connected:
            return

        if not text:
            return

        try:
            transcript_event = {
                "type": "TRANSCRIPT",
                "speaker": speaker,
                "text": text,
                "is_final": is_final,
                "language": self.language,
                "timestamp": time.time(),
            }
            await self._websocket.send(json.dumps(transcript_event))
            logger.info(f"TRANSCRIPT [{speaker}]: {text}")
        except Exception as e:
            logger.error(f"Error sending {speaker} transcript: {e}")

    async def send_user_transcript(self, text: str, is_final: bool = True) -> None:
        """
        Send user transcript to the Lyra server.

        Args:
            text: The transcribed text from the user
            is_final: Whether this is a final transcript (default: True)
        """
        await self._send_transcript(text, "user", is_final)

    async def send_agent_transcript(self, text: str, is_final: bool = True) -> None:
        """
        Send agent transcript to the Lyra server.

        Args:
            text: The text that the agent is speaking
            is_final: Whether this is a final transcript (default: True)
        """
        await self._send_transcript(text, "agent", is_final)

    async def close(self) -> None:
        """
        Close the connection to the Lyra server.

        Cancels the receive task and closes the WebSocket connection.
        """
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

    @property
    def connected(self) -> bool:
        """Whether the client is currently connected."""
        return self._connected