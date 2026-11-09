# feature: F01
"""Acceptance coverage for agent declarations and local application context."""
import json
from typing import Any

import pytest
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field

from F01_helpers import RecordingModel, function_call, responses_peer, run_agent

from velmora import Agent, AgentOutputSchema, ModelBehaviorError, RunContextWrapper, UserError, function_tool
from velmora import OpenAIResponsesModel


class Report(BaseModel):
    label: str
    count: int = Field(ge=0)


@pytest.mark.asyncio
async def test_f01_t01():
    @function_tool
    def lookup() -> str:
        return "Application lookup."

    first = RecordingModel('{"label":"north","count":7}')
    agent = Agent(name="Analyst", instructions="Keep CASE and spacing.\n  Report precisely.",
                  model=first, tools=[lookup], output_type=Report)
    result = await run_agent(agent)
    assert result.final_output == Report(label="north", count=7)
    assert first.requests[0]["instructions"] == agent.instructions
    assert [tool.name for tool in first.requests[0]["tools"]] == [lookup.name]
    assert first.requests[0]["output_schema"].is_plain_text() is False

    def instructions(ctx, current):
        assert current is agent
        return f"{current.name}: {ctx.context['region']}"

    async def async_instructions(ctx, current):
        return instructions(ctx, current)

    for callback in (instructions, async_instructions):
        agent.instructions = callback
        for name, region in (("Planner", "west"), ("Reviewer", "east")):
            selected = RecordingModel('{"label":"chosen","count":3}')
            agent.model = selected
            agent.name = name
            assert (await run_agent(agent, context={"region": region})).final_output == Report(label="chosen", count=3)
            assert selected.requests[0]["instructions"] == f"{name}: {region}"
            assert [tool.name for tool in selected.requests[0]["tools"]] == [lookup.name]
    assert len(first.requests) == 1


@pytest.mark.asyncio
async def test_f01_t02():
    context = {"secret": "private-credential-7d2", "count": 0, "public": "approved-summary"}
    seen = []

    def instructions(ctx, current):
        assert ctx.context is context
        seen.append(ctx.context["count"])
        ctx.context["prepared"] = True
        return f"{current.name}: {ctx.context['public']}"

    @function_tool(failure_error_function=None)
    async def advance(ctx: RunContextWrapper[dict[str, Any]]) -> str:
        assert ctx.context is context
        assert ctx.context["prepared"] is True
        assert ctx.context["count"] == 0
        ctx.context["count"] += 10
        return ctx.context["public"]

    model = RecordingModel([function_call("advance", {}, "advance-1")], "Finished locally.")
    agent = Agent(name="Local", instructions=instructions, tools=[advance], model=model)
    result = await run_agent(agent, context=context)
    assert result.final_output == "Finished locally."
    assert 0 in seen and 10 in seen
    assert context["count"] == 10
    assert len(model.requests) == 2
    for request in model.requests:
        assert request["instructions"] == "Local: approved-summary"
        visible = json.dumps({"instructions": request["instructions"], "input": request["input"]})
        assert context["secret"] not in visible
    outputs = [item for item in model.requests[1]["input"] if item.get("type") == "function_call_output"]
    assert [(item["call_id"], item["output"]) for item in outputs] == [("advance-1", "approved-summary")]


@pytest.mark.asyncio
async def test_f01_t03():
    for text in ("Unstructured answer.", "A different final answer."):
        result = await run_agent(Agent(name="Text", model=RecordingModel(text)))
        assert type(result.final_output) is str
        assert result.final_output == text

    model = RecordingModel('{"label":"delta","count":19}')
    result = await run_agent(Agent(name="Record", model=model, output_type=Report))
    assert isinstance(result.final_output, Report)
    assert result.final_output.label == "delta"
    assert result.final_output.count == 19

    # Non-object declarations use the public model-response envelope.
    for declaration, value in ((list[int], [8, -3, 14]), (int, 42), (bool, False)):
        model = RecordingModel(json.dumps({"response": value}))
        result = await run_agent(Agent(name="Value", model=model, output_type=declaration))
        assert type(result.final_output) is type(value)
        assert result.final_output == value


@pytest.mark.asyncio
async def test_f01_t04():
    valid = await run_agent(Agent(name="Valid", output_type=Report,
                                 model=RecordingModel('{"label":"ok","count":4}')))
    assert valid.final_output == Report(label="ok", count=4)
    invalid = ["not JSON", '{"label":"bad"}', '{"label":"bad","count":-1}',
               '{"label":"bad","count":"4"}', '{"label":"bad","count":true}']
    for content in invalid:
        with pytest.raises(ModelBehaviorError):
            await run_agent(Agent(name="Invalid", output_type=Report, model=RecordingModel(content)))
    # Strict validation also governs enveloped collection and scalar declarations.
    for declaration, content in ((int, '{"response":"4"}'), (int, '{"response":true}'),
                                 (list[int], '{"response":[1,"2"]}')):
        with pytest.raises(ModelBehaviorError):
            await run_agent(Agent(name="Invalid value", output_type=declaration,
                                  model=RecordingModel(content)))

    permissive = AgentOutputSchema(output_type=Report, strict_json_schema=False)
    converted = await run_agent(Agent(name="Convert", output_type=permissive,
                                     model=RecordingModel('{"label":"converted","count":"6"}')))
    assert converted.final_output == Report(label="converted", count=6)
    assert type(converted.final_output.count) is int

    class OpenRecord(BaseModel):
        model_config = ConfigDict(extra="allow")
        label: str

    with pytest.raises(UserError):
        declaration = AgentOutputSchema(output_type=OpenRecord)
        await run_agent(Agent(name="Open", output_type=declaration,
                              model=RecordingModel('{"label":"open"}')))


@pytest.mark.asyncio
async def test_f01_t05():
    @function_tool
    def initial() -> str:
        return "Initial."

    @function_tool
    def added() -> str:
        return "Added."

    @function_tool
    def replacement() -> str:
        return "Replacement."

    model = RecordingModel('{"label":"original","count":1}', '{"label":"derived","count":2}',
                           '{"label":"replaced","count":3}')
    original = Agent(name="Original", instructions="Original instructions.", model=model,
                     tools=[initial], output_type=Report)
    derived = original.clone(name="Derived", instructions="Derived instructions.")
    assert derived is not original
    assert original.name == "Original"
    assert original.instructions == "Original instructions."
    assert derived.name == "Derived"
    assert derived.instructions == "Derived instructions."
    assert derived.model is model
    for field in ("tools", "handoffs", "mcp_servers", "input_guardrails", "output_guardrails"):
        assert getattr(derived, field) is getattr(original, field)
    assert derived.output_type == original.output_type == Report
    derived.tools.append(added)
    assert original.tools == [initial, added]
    replaced = original.clone(tools=[replacement])
    assert replaced.tools == [replacement]
    assert original.tools == [initial, added]
    assert replaced.output_type == Report
    # The retained output declaration is effective, not just readable.
    assert (await run_agent(original)).final_output == Report(label="original", count=1)
    assert (await run_agent(derived)).final_output == Report(label="derived", count=2)
    assert (await run_agent(replaced)).final_output == Report(label="replaced", count=3)
    assert all(req["output_schema"].is_plain_text() is False for req in model.requests)
    assert [req["instructions"] for req in model.requests] == [
        "Original instructions.", "Derived instructions.", "Original instructions."]
    assert [sorted(tool.name for tool in req["tools"]) for req in model.requests] == [
        ["added", "initial"], ["added", "initial"], ["replacement"]]


@pytest.mark.asyncio
async def test_f01_t06():
    with responses_peer() as (url, requests):
        async with AsyncOpenAI(base_url=url, api_key="local-test-key", max_retries=0) as client:
            model = OpenAIResponsesModel(model="application-model", openai_client=client)
            selection = {"id": "template-static", "version": "3", "variables": {"region": "west"}}
            agent = Agent(name="Template", model=model, prompt=selection)
            assert (await run_agent(agent)).final_output == "Template response."
            assert requests[-1]["path"] == "/v1/responses"
            assert requests[-1]["body"]["prompt"] == selection

            def choose(data):
                assert data.agent is agent
                assert data.context.context is context
                return {"id": data.context.context["template"], "version": "8",
                        "variables": {"region": data.agent.name}}

            async def choose_async(data):
                return choose(data)

            for callback, name, template in ((choose, "North", "template-dynamic"),
                                             (choose_async, "South", "template-async")):
                context = {"template": template, "secret": f"undisclosed-{name}-91c"}
                agent.prompt = callback
                agent.name = name
                assert (await run_agent(agent, context=context)).final_output == "Template response."
                assert requests[-1]["body"]["prompt"] == {
                    "id": template, "version": "8", "variables": {"region": name}}
                # Context members the application did not disclose never reach the wire.
                assert context["secret"] not in json.dumps(requests[-1]["body"])
