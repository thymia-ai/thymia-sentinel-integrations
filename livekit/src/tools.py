import json
import logging

from livekit.agents import function_tool, RunContext, get_job_context, ToolError
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class ToolParameter(BaseModel):
    name: str
    description: str = ""
    type: str = "string"
    required: bool = True


class TemporaryTool(BaseModel):
    model_tool_name: str = Field(alias="modelToolName")
    description: str
    dynamic_parameters: list[ToolParameter] = Field(default_factory=list, alias="dynamicParameters")


class ToolConfig(BaseModel):
    tool_name: str | None = Field(default=None, alias="toolName")
    temporary_tool: TemporaryTool | None = Field(default=None, alias="temporaryTool")

class AgentConfig(BaseModel):
    system_prompt: str = Field(default="", alias="systemPrompt")
    tools: list[ToolConfig] | None = Field(default=None)
    voice: str = Field(default="")
    temperature: float = Field(default=None)

@function_tool
async def hangup(context: RunContext):
    """End the call when the user wants to hang up or says goodbye."""
    job_ctx = get_job_context()
    await job_ctx.room.disconnect()
    context.session.shutdown()
    return "Goodbye!"

BUILTIN_TOOLS = {
    "hangUp": hangup,
}


def create_client_tool(tool_config: TemporaryTool):
    """Create a tool that calls the frontend via RPC and returns the response."""
    properties = {}
    required = []
    for p in tool_config.dynamic_parameters:
        properties[p.name] = {
            "type": p.type,
            "description": p.description,
        }
        if p.required:
            required.append(p.name)

    raw_schema = {
        "name": tool_config.model_tool_name,
        "description": tool_config.description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }

    tool_name = tool_config.model_tool_name

    async def handler(raw_arguments: dict):
        try:
            room = get_job_context().room
            participant_identity = next(iter(room.remote_participants))
            response = await room.local_participant.perform_rpc(
                destination_identity=participant_identity,
                method=tool_name,
                payload=json.dumps(raw_arguments),
                response_timeout=10.0,
            )
            return response
        except StopIteration:
            raise ToolError("No participants to send RPC to")
        except Exception as e:
            raise ToolError(f"Failed to call {tool_name}: {e}")

    return function_tool(handler, raw_schema=raw_schema)

def get_tools_from_config(config: AgentConfig):
    """Resolve tool configs to actual tool functions."""
    tools = []

    if not config.tools:
        return tools

    for tool_config in config.tools:
        # Built-in tool
        if tool_config.tool_name and tool_config.tool_name in BUILTIN_TOOLS:
            tools.append(BUILTIN_TOOLS[tool_config.tool_name])

        # Dynamic client tool
        elif tool_config.temporary_tool:
            tool = create_client_tool(tool_config.temporary_tool)
            tools.append(tool)

        else:
            logger.warning(f"Unknown tool config: {tool_config}")

    return tools
