"""
VAPI Agent with Thymia Sentinel

A voice agent using VAPI WebSocket transport with real-time biomarker monitoring
via Thymia Sentinel.

Architecture:
1. Create a VAPI call with WebSocket transport via REST API
2. Connect to VAPI's WebSocket for bidirectional audio streaming
3. Capture microphone audio and send to VAPI
4. Receive agent audio from VAPI and play through speakers
5. Stream both user and agent audio to Thymia Sentinel for biomarker analysis

Run with: uv run python src/agent.py

Prerequisites:
- On Mac: brew install portaudio
"""
import asyncio
import json
import os
import sys
from dotenv import load_dotenv

load_dotenv(".env.local")

from loguru import logger

# Logging configuration
logger.remove()
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"))

import httpx
import pyaudio
import websockets

from thymia_sentinel import SentinelClient, PolicyResult, ProgressResult
from prompts import SYSTEM_PROMPT, format_action_message

# Audio configuration
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SIZE = 1600  # 100ms of audio at 16kHz
FORMAT = pyaudio.paInt16

# VAPI configuration
VAPI_API_KEY = os.getenv("VAPI_PRIVATE_API_KEY")


async def create_websocket_call() -> dict:
    """Create a VAPI call with WebSocket transport."""
    if not VAPI_API_KEY:
        raise ValueError("VAPI_PRIVATE_API_KEY not set in environment")

    assistant_config = {"transport": {
        "provider": "vapi.websocket",
        "audioFormat": {
            "format": "pcm_s16le",
            "container": "raw",
            "sampleRate": SAMPLE_RATE
        }
    }, "assistant": {
        "firstMessage": "Hello! I'm here to chat with you. How are you doing today?",
        "model": {
            "provider": "openai",
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                }
            ],
        },
        "voice": {
            "provider": "11labs",
            "voiceId": "sarah",
        },
    }}

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.vapi.ai/call",
            headers={
                "Authorization": f"Bearer {VAPI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=assistant_config,
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()


async def send_microphone_audio(
    ws: websockets.WebSocketClientProtocol,
    sentinel: SentinelClient,
    audio_stream: pyaudio.Stream,
    stop_event: asyncio.Event,
):
    """Capture microphone audio and send to VAPI and Sentinel."""
    loop = asyncio.get_event_loop()

    while not stop_event.is_set():
        try:
            # Read audio from microphone (run in executor to avoid blocking)
            audio_data = await loop.run_in_executor(
                None,
                lambda: audio_stream.read(CHUNK_SIZE, exception_on_overflow=False)
            )

            # Send to VAPI
            await ws.send(audio_data)

            # Send to Sentinel for biomarker analysis
            await sentinel.send_user_audio(audio_data)

        except Exception as e:
            if not stop_event.is_set():
                logger.error(f"Error sending audio: {e}")
            break


async def receive_vapi_messages(
    ws: websockets.WebSocketClientProtocol,
    sentinel: SentinelClient,
    audio_output: pyaudio.Stream,
    stop_event: asyncio.Event,
):
    """Receive messages from VAPI WebSocket."""
    loop = asyncio.get_event_loop()

    try:
        async for message in ws:
            if stop_event.is_set():
                break

            # Binary message = audio data from assistant
            if isinstance(message, bytes):
                # Play through speakers
                await loop.run_in_executor(
                    None,
                    lambda: audio_output.write(message)
                )

                # Send to Sentinel for biomarker analysis
                await sentinel.send_agent_audio(message)

            # Text message = JSON control message
            else:
                try:
                    data = json.loads(message)
                    await handle_vapi_message(data, sentinel)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON message: {message}")

    except websockets.exceptions.ConnectionClosed:
        logger.info("VAPI WebSocket closed")
    except Exception as e:
        if not stop_event.is_set():
            logger.error(f"Error receiving messages: {e}")

    stop_event.set()


async def handle_vapi_message(data: dict, sentinel: SentinelClient):
    """Handle JSON messages from VAPI."""
    msg_type = data.get("type", "")

    if msg_type == "transcript":
        role = data.get("role", "")
        text = data.get("transcript", "")
        transcript_type = data.get("transcriptType", "")

        if transcript_type == "final" and text:
            # Send transcript to Sentinel
            if role == "user":
                await sentinel.send_user_transcript(text, is_final=True)
            elif role == "assistant":
                await sentinel.send_agent_transcript(text, is_final=True)

    elif msg_type == "speech-update":
        status = data.get("status", "")
        role = data.get("role", "")
        logger.debug(f"Speech {status}: {role}")

    elif msg_type == "conversation-update":
        logger.debug("Conversation updated")

    elif msg_type == "call-ended":
        logger.info("Call ended by VAPI")

    elif msg_type == "error":
        logger.error(f"VAPI error: {data}")

    else:
        logger.debug(f"VAPI message: {msg_type}")


async def apply_recommended_action(action: str, ws: websockets.WebSocketClientProtocol):
    """Inject a recommended action into VAPI as a system message."""
    logger.info("=" * 60)
    logger.info("APPLYING RECOMMENDED ACTION")
    logger.info(f"Action: {action}")
    logger.info("=" * 60)

    # Send as a control message to inject into conversation
    message = {
        "type": "add-message",
        "message": {
            "role": "system",
            "content": format_action_message(action),
        },
        "triggerResponseEnabled": False,  # Don't interrupt current speech
    }
    await ws.send(json.dumps(message))


async def main():
    """Run the VAPI agent with Thymia Sentinel."""
    logger.info("Creating VAPI WebSocket call...")

    # Create call and get WebSocket URL
    call_data = await create_websocket_call()
    call_id = call_data.get("id")
    transport = call_data.get("transport", {})
    ws_url = transport.get("websocketCallUrl")

    if not ws_url:
        logger.error("No WebSocket URL returned from VAPI")
        logger.error(f"Response: {call_data}")
        return

    logger.info(f"Call created: {call_id}")
    logger.info(f"Connecting to WebSocket...")

    # Store WebSocket reference for action injection
    vapi_ws = None

    # Initialize Sentinel
    async def handle_policy_result(result: PolicyResult):
        policy = result.get('policy', 'unknown')
        policy_name = result.get('policy_name', policy)
        inner_result = result.get('result', {})
        result_type = inner_result.get('type', 'unknown')

        logger.info(f"Policy [{policy_name}] (executor={policy}): type={result_type}")

        if result_type == 'safety_analysis':
            classification = inner_result.get('classification', {})
            concerns = inner_result.get('concerns', [])
            level = classification.get('level', 0)
            alert = classification.get('alert', 'none')
            logger.info(f"Sentinel: level={level} alert={alert}")
            if concerns:
                logger.info(f"   Concerns: {concerns}")

            # Apply recommended action
            actions = inner_result.get('recommended_actions', {})
            for_agent = actions.get('for_agent', '')
            if for_agent and vapi_ws:
                await apply_recommended_action(for_agent, vapi_ws)

        elif result_type == 'extracted_fields':
            fields = inner_result.get('fields', {})
            extracted = {k: v.get('value') for k, v in fields.items() if v.get('value') is not None}
            if extracted:
                logger.info(f"   Extracted: {extracted}")

        elif result_type == 'passthrough':
            biomarkers = inner_result.get('biomarkers', {})
            if biomarkers:
                scores = ", ".join(f"{k}={v:.2f}" for k, v in biomarkers.items() if v is not None)
                logger.info(f"   Biomarkers: {scores}")

    async def handle_progress_result(result: ProgressResult):
        timestamp = result.get('timestamp', 0.0)
        biomarkers = result.get('biomarkers', {})
        logger.info(f"Progress at {timestamp}: biomarkers={biomarkers}")

    sentinel = SentinelClient(
        user_label="550e8400-e29b-41d4-a716-446655440000",
        language="en-GB",
        on_policy_result=handle_policy_result,
        policies=["demo_wellbeing_awareness"],  # ["demo_wellbeing_awareness", "demo_field_extraction"]
        biomarkers=["helios"],  # ["helios", "apollo", "psyche"]
        on_progress_result=handle_progress_result,
    )

    # Initialize PyAudio
    p = pyaudio.PyAudio()

    # Open microphone input stream
    input_stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE,
    )

    # Open speaker output stream
    output_stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        output=True,
        frames_per_buffer=CHUNK_SIZE,
    )

    stop_event = asyncio.Event()

    try:
        # Connect to Sentinel
        await sentinel.connect()

        # Connect to VAPI WebSocket
        async with websockets.connect(ws_url, max_size=None) as ws:
            vapi_ws = ws
            logger.info("Connected to VAPI WebSocket")
            logger.info("Call active. Speak into your microphone. Press Ctrl+C to end.")

            # Run send and receive tasks concurrently
            await asyncio.gather(
                send_microphone_audio(ws, sentinel, input_stream, stop_event),
                receive_vapi_messages(ws, sentinel, output_stream, stop_event),
            )

    except KeyboardInterrupt:
        logger.info("Stopping call...")
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        stop_event.set()

        # Cleanup
        input_stream.stop_stream()
        input_stream.close()
        output_stream.stop_stream()
        output_stream.close()
        p.terminate()

        await sentinel.close()
        logger.info("Call ended")


if __name__ == "__main__":
    asyncio.run(main())