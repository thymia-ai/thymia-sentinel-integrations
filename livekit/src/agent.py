"""
Safety-Aware Agent with Thymia Sentinel

The agent receives safety assessments from the Sentinel and adapts its behavior accordingly.
"""
import json
import os
import sys
from dotenv import load_dotenv

load_dotenv(".env.local")

from loguru import logger

# Logging configuration
logger.remove()
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"))

from livekit.agents import (
    Agent,
    AgentSession,
    AutoSubscribe,
    JobContext,
    JobProcess,
    RoomInputOptions,
    WorkerOptions,
    cli,
)

from livekit.plugins import noise_cancellation, deepgram, rime, openai, thymia, elevenlabs
from tools import get_tools_from_config, AgentConfig

from prompts import SYSTEM_PROMPT, format_action_update


class SafetyAwareAssistant(Agent):
    def __init__(self, config: AgentConfig, tools: list) -> None:
        self._base_instructions = f"{SYSTEM_PROMPT} {config.system_prompt}"
        super().__init__(tools=tools, instructions=self._base_instructions)
        self._current_action: str | None = None

    async def apply_recommended_action(self, action: str) -> None:
        """Apply a recommended action from the safety system."""
        self._current_action = action
        updated_instructions = format_action_update(self._base_instructions, action)

        # Log BEFORE update
        logger.info("=" * 60)
        logger.info("🎯 APPLYING RECOMMENDED ACTION")
        logger.info(f"Action: {action}")
        logger.info("-" * 60)
        logger.info("Full updated instructions:")
        logger.info(updated_instructions)
        logger.info("=" * 60)

        # Apply the update
        await self.update_instructions(updated_instructions)

        # Log AFTER update - check what the agent actually has
        logger.info(f"✅ Instructions updated. Current agent instructions:")
        logger.info(f"{self.instructions}")
        logger.info("=" * 60)


def prewarm(proc: JobProcess):
    proc.userdata["tts"] = rime.TTS(
        model="mistv2",
        speaker="rainforest",
        reduce_latency=True,
        temperature=0.8,
    )

async def entrypoint(ctx: JobContext):
    if ctx.job.metadata:
        config = AgentConfig.model_validate_json(ctx.job.metadata)
    else:
        config = AgentConfig()

    tools = get_tools_from_config(config)
    assistant = SafetyAwareAssistant(config, tools)

    stt_instance = deepgram.STTv2(
        model="flux-general-en",
        eager_eot_threshold=0.3,
        eot_threshold=0.5,
        eot_timeout_ms=2000,
    )

    # Change voice settings
    if config.voice:
        ctx.proc.userdata["tts"].update_options(speaker=config.voice)

    session = AgentSession(
        stt=stt_instance,
        llm=openai.LLM(model="gpt-4o", temperature=config.temperature),
        tts=ctx.proc.userdata["tts"],
        preemptive_generation=True,
    )

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    await session.start(
        agent=assistant,
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await session.generate_reply(instructions="Hello!")

    async def handle_policy_result(result: thymia.PolicyResult):
        # Forward policy result to UI via data channel
        await ctx.room.local_participant.publish_data(
            payload=json.dumps(result).encode("utf-8"),
            topic="thymia-policy-result",
        )

        policy_name = result.get('policy', 'unknown')
        inner_result = result.get('result', {})
        result_type = inner_result.get('type', 'unknown')

        logger.info(f"📋 Policy [{policy_name}]: type={result_type}")

        # Handle safety policy results - apply agent actions
        if result_type == 'safety_analysis':
            actions = inner_result.get('recommended_actions', {})
            concerns = inner_result.get('concerns', [])
            level = inner_result.get('level', 0)
            alert = inner_result.get('alert', 'none')
            logger.info(f"🛡️ Sentinel: level={level} alert={alert}")
            if concerns:
                logger.info(f"   Concerns: {concerns}")

            for_agent = actions.get('for_agent', '')
            if for_agent:
                await assistant.apply_recommended_action(for_agent)

        # Handle field extraction results - log extracted fields
        elif result_type == 'extracted_fields':
            fields = inner_result.get('fields', {})
            extracted = {k: v.get('value') for k, v in fields.items() if v.get('value') is not None}
            if extracted:
                logger.info(f"   Extracted: {extracted}")


    async def handle_progress_result(result: thymia.ProgressResult):
        # Forward progress result to UI via data channel
        await ctx.room.local_participant.publish_data(
            payload=json.dumps(result).encode("utf-8"),
            topic="thymia-progress-result",
        )
        timestamp = result.get('timestamp', 0.0)
        biomarkers = result.get('biomarkers', {})
        logger.info(f"Progress at {timestamp}:: biomarkers={biomarkers}")

    sentinel = thymia.Sentinel(
        user_label="550e8400-e29b-41d4-a716-446655440000",
        date_of_birth="1990-01-01",
        birth_sex="MALE",
        language="en-GB",
        on_policy_result=handle_policy_result,
        policies=["passthrough"], # ["passthrough", "field_extraction", "safety_analysis", "agent_eval"]
        biomarkers=["helios"], # ["helios", "apollo"]
        on_progress_result=handle_progress_result,
    )

    # Pass both ctx and session - Sentinel handles everything else
    await sentinel.start(ctx, session)

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm, agent_name=os.getenv("LIVEKIT_AGENT_NAME")))
