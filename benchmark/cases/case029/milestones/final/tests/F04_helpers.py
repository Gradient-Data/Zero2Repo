# feature: F04
"""Application tools and public run observations for execution acceptance tests."""
from pydantic import BaseModel
from _helpers import invoke
from velmora import FunctionTool, RunConfig, Runner
from openai.types.responses import ResponseOutputMessage, ResponseOutputRefusal


def execution_tool(effects, *, name="record", needs_approval=False):
    async def apply(context, arguments):
        import json
        value = json.loads(arguments)["value"]
        effects.append(value)
        return f"recorded:{value}"

    return FunctionTool(
        name=name, description="Record an application value.",
        params_json_schema={"type": "object", "properties": {
            "value": {"type": "string"}}, "required": ["value"],
            "additionalProperties": False},
        on_invoke_tool=apply, needs_approval=needs_approval,
    )


async def execution_run(agent, input="Proceed.", *, config=None, **kwargs):
    return await invoke(Runner.run, agent, input=input,
                        run_config=config or RunConfig(tracing_disabled=True), **kwargs)


def refusal_message(reason):
    return ResponseOutputMessage(id="refusal", type="message", role="assistant",
                                 status="completed", content=[ResponseOutputRefusal(
                                     type="refusal", refusal=reason)])


def conversation_text(items):
    """Read assistant output text from its public Responses content carrier."""
    return [part["text"] for item in items
            if isinstance(item, dict) and item.get("role") == "assistant"
            for part in item["content"] if part["type"] == "output_text"]


class RecoveryOutput(BaseModel):
    summary: str
