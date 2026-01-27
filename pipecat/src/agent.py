"""
Pipecat Agent with Thymia Sentinel

A voice agent using Pipecat with real-time biomarker monitoring via Thymia Sentinel.

Based on the Pipecat quickstart example:
https://github.com/pipecat-ai/pipecat-quickstart

Run with: uv run python src/agent.py
Then open http://localhost:7860 in your browser and click Connect.
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv(".env.local")

from loguru import logger

# Logging configuration
logger.remove()
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"))

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    Frame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    UserAudioRawFrame,
    TTSTextFrame,
    TextFrame,
    BotStoppedSpeakingFrame,
    LLMMessagesUpdateFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.daily.transport import DailyParams
from pipecat.runner.run import main
from pipecat.runner.utils import create_transport

import thymia
from prompts import SYSTEM_PROMPT, format_action_update

# Audio configuration
SAMPLE_RATE = 16000


class UserInputProcessor(FrameProcessor):
    """Captures user audio before STT consumes it."""

    def __init__(self, sentinel_instance: thymia.Sentinel):
        super().__init__()
        self._sentinel = sentinel_instance

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, UserAudioRawFrame):
            await self._sentinel.send_user_audio(frame.audio)

        # Capture user transcripts (STT output)
        elif isinstance(frame, TranscriptionFrame):
            if frame.text:
                await self._sentinel.send_user_transcript(frame.text, is_final=True)

        await self.push_frame(frame, direction)


class AgentOutputProcessor(FrameProcessor):
    """Captures agent audio, transcripts, and user transcripts after STT."""

    def __init__(self, sentinel_instance: thymia.Sentinel):
        super().__init__()
        self._sentinel = sentinel_instance
        self._agent_transcript_buffer = []

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        # Capture agent audio (TTS output)
        if isinstance(frame, TTSAudioRawFrame):
            await self._sentinel.send_agent_audio(frame.audio)

        # Capture agent text responses (before TTS)
        elif isinstance(frame, TTSTextFrame):
            if frame.text and direction == FrameDirection.DOWNSTREAM:
                self._agent_transcript_buffer.append(frame.text)

        # Flush agent transcript when bot stops speaking
        elif isinstance(frame, BotStoppedSpeakingFrame):
            await self._flush_agent_transcript()

        await self.push_frame(frame, direction)

    async def _flush_agent_transcript(self):
        """Flush accumulated agent transcript to Sentinel."""
        if self._agent_transcript_buffer:
            full_text = ' '.join(self._agent_transcript_buffer)
            await self._sentinel.send_agent_transcript(full_text, is_final=True)
            self._agent_transcript_buffer.clear()

async def apply_recommended_action(action: str, context: LLMContext, task: PipelineTask) -> None:
    """Apply a recommended action from the safety system by updating the LLM context."""
    updated_instructions = format_action_update(SYSTEM_PROMPT, action)

    logger.info("=" * 60)
    logger.info("APPLYING RECOMMENDED ACTION")
    logger.info(f"Action: {action}")
    logger.info("=" * 60)

    # Update the system message in the context
    if context.messages and context.messages[0].get("role") == "system":
        context.messages[0]["content"] = updated_instructions

        # Push frame to notify the LLM service of the context update
        await task.queue_frames([LLMMessagesUpdateFrame(messages=list(context.messages))])
        logger.info("Context update pushed to pipeline")

def transport_params():
    """Return transport parameters for Daily."""
    return {
        "daily": lambda: DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=SAMPLE_RATE,
            audio_out_sample_rate=SAMPLE_RATE,
            vad_analyzer=SileroVADAnalyzer(params=VADParams()),
            transcription_enabled=False,
        ),
    }

async def bot(runner_args):
    """Main bot function called by the pipecat runner."""

    # Reconfigure logger here - AFTER main() has set it up
    logger.remove()
    logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"))

    # Initialize Thymia Sentinel
    async def handle_policy_result(result: thymia.PolicyResult):
        policy_name = result.get('policy', 'unknown')
        inner_result = result.get('result', {})
        result_type = inner_result.get('type', 'unknown')

        logger.info(f"Policy [{policy_name}]: type={result_type}")

        # Handle safety policy results
        if result_type == 'safety_analysis':
            classification = inner_result.get('classification', {})
            concerns = inner_result.get('concerns', [])
            level = classification.get('level', 0)
            alert = classification.get('alert', 'none')
            logger.info(f"Sentinel: level={level} alert={alert}")
            if concerns:
                logger.info(f"   Concerns: {concerns}")

            actions = inner_result.get('recommended_actions', {})
            for_agent = actions.get('for_agent', '')
            if for_agent:
                await apply_recommended_action(for_agent, context, task)

        # Handle field extraction results
        elif result_type == 'extracted_fields':
            fields = inner_result.get('fields', {})
            extracted = {k: v.get('value') for k, v in fields.items() if v.get('value') is not None}
            if extracted:
                logger.info(f"   Extracted: {extracted}")

    sentinel = thymia.Sentinel(
        user_label="550e8400-e29b-41d4-a716-446655440000",
        date_of_birth="1990-01-01",
        birth_sex="MALE",
        language="en-GB",
        on_policy_result=handle_policy_result,
        policies=["passthrough"],  # ["passthrough", "field_extraction", "safety_analysis", "agent_eval"]
        biomarkers=["helios"]  # ["helios", "apollo"]
    )

    # Connect to Thymia server
    await sentinel.connect()

    try:
        # Create transport using the runner
        transport = await create_transport(runner_args, transport_params())

        # Initialize services
        stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

        tts = CartesiaTTSService(
            api_key=os.getenv("CARTESIA_API_KEY"),
            voice_id="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
        )

        llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4o")

        # Initialize context
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
        ]
        context = LLMContext(messages)
        user_aggregator, assistant_aggregator = LLMContextAggregatorPair(context)

        # Create Sentinel processors
        user_input_processor = UserInputProcessor(sentinel)
        agent_output_processor = AgentOutputProcessor(sentinel)

        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                user_input_processor,  # Capture user audio and transcripts
                user_aggregator,
                llm,
                tts,
                agent_output_processor,  # Capture transcripts and agent output after TTS
                transport.output(),
                assistant_aggregator,
            ]
        )

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                allow_interruptions=True,
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
        )

        @transport.event_handler("on_first_participant_joined")
        async def on_first_participant_joined(_, participant):
            logger.info(f"Participant joined: {participant['id']}")
            await task.queue_frames(
                [TextFrame("Hello! I'm here to chat with you. How are you doing today?")]
            )

        @transport.event_handler("on_participant_left")
        async def on_participant_left(_, participant, reason):
            logger.info(f"Participant left: {participant['id']}")
            await task.cancel()

        runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
        await runner.run(task)

    finally:
        await sentinel.close()
        logger.info("Sentinel connection closed.")


if __name__ == "__main__":
    # Default to Daily transport
    if "--transport" not in sys.argv and "-t" not in sys.argv:
        sys.argv.extend(["--transport", "daily"])
    main()