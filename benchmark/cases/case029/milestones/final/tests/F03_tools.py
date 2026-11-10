# feature: F03
"""Acceptance tests for application tools through real agent runs."""
import asyncio
import json
from typing import Annotated, Any

import pytest
from pydantic import Field
from openai.types.responses import ResponseCustomToolCall, ResponseFunctionToolCall

from F01_helpers import RecordingModel, function_call, run_agent
from F03_helpers import tool_outputs, tool_trace_destination, tool_turn
from _helpers import invoke
from velmora import (
    Agent, CustomTool, FunctionTool, ModelBehaviorError, RunConfig,
    RunContextWrapper, Runner, ToolOutputFileContent, ToolOutputImage,
    ToolOutputText, ToolTimeoutError, UserError, function_tool,
)


@pytest.mark.asyncio
async def test_f03_t01():
    seen = []

    def quote(ctx: RunContextWrapper[Any], units: int, label: str = "standard") -> str:
        """Quote the requested units with the application multiplier."""
        seen.append((ctx.context, units, label))
        return f"{label}:{units * ctx.context['multiplier']}"

    async def async_quote(ctx: RunContextWrapper[Any], units: int, label: str = "standard") -> str:
        """Quote the requested units with the application multiplier."""
        return quote(ctx, units, label)

    for handler in (quote, async_quote):
        tool = function_tool(handler, failure_error_function=None)
        for arguments, expected in (({"units": 7}, "standard:21"),
                                    ({"units": 4, "label": "express"}, "express:12")):
            context = {"multiplier": 3}
            previous_calls = len(seen)
            _, model = await tool_turn(tool, arguments, context=context)
            assert len(seen) == previous_calls + 1
            assert seen[-1] == (context, arguments["units"], arguments.get("label", "standard"))
            assert seen[-1][0] is context
            assert tool_outputs(model.requests[-1]) == {"application-call": expected}
            declared = model.requests[0]["tools"]
            assert [item.name for item in declared] == [tool.name]
            assert declared[0].description == "Quote the requested units with the application multiplier."
            assert declared[0].params_json_schema["properties"]["units"]["type"] == "integer"
    assert len(seen) == 4

    async def explicit(ctx, raw):
        arguments = json.loads(raw)
        ctx.context["received"] = arguments
        return f"{arguments['city']}:{ctx.context['zone']}"

    tool = FunctionTool(name="zone_lookup", description="Look up a city zone.",
                        params_json_schema={"type": "object", "properties": {
                            "city": {"type": "string"}}, "required": ["city"]},
                        on_invoke_tool=explicit)
    context = {"zone": "west"}
    _, model = await tool_turn(tool, {"city": "Harbor"}, context=context)
    assert context["received"] == {"city": "Harbor"}
    assert tool_outputs(model.requests[-1]) == {"application-call": "Harbor:west"}


@pytest.mark.asyncio
async def test_f03_t02():
    seen = []

    @function_tool(failure_error_function=None)
    def reserve(units: Annotated[int, Field(gt=0)]) -> str:
        seen.append(units)
        return f"Reserved {units}"

    _, model = await tool_turn(reserve, {"units": 3})
    assert tool_outputs(model.requests[-1]) == {"application-call": "Reserved 3"}
    for raw in ('{}', '{"units":', '{"units":0}', '{"units":[]}'):
        seen.clear()
        call = ResponseFunctionToolCall(type="function_call", name=reserve.name,
                                       arguments=raw, call_id="invalid")
        model = RecordingModel([call])
        with pytest.raises(ModelBehaviorError):
            await run_agent(Agent(name="Reservations", tools=[reserve], model=model))
        assert seen == []

    failure = RuntimeError("reservation backend failed")

    @function_tool(failure_error_function=None)
    async def fail(units: int) -> str:
        seen.append(units)
        raise failure

    with pytest.raises(UserError) as caught:
        await tool_turn(fail, {"units": 8})
    assert caught.value.__cause__ is failure
    assert seen == [8]


@pytest.mark.asyncio
async def test_f03_t03():
    secret = "application-private-failure-7c39"
    for arguments in ({"units": 2}, {}):
        executed = []

        @function_tool
        async def fail(units: int) -> str:
            executed.append(units)
            raise RuntimeError(secret)

        model = RecordingModel([function_call(fail.name, arguments, "failure")], "Recovered.")
        with tool_trace_destination() as destination:
            result = await invoke(Runner.run, Agent(name="Failures", tools=[fail], model=model),
                                  "Proceed.", run_config=RunConfig(trace_include_sensitive_data=True))
        assert result.final_output == "Recovered."
        outputs = tool_outputs(model.requests[-1])
        assert set(outputs) == {"failure"}
        assert isinstance(outputs["failure"], str) and outputs["failure"]
        assert executed == ([2] if arguments else [])
        assert secret not in json.dumps(model.requests[-1]["input"])
        function_spans = [span for span in destination.spans
                          if span["span_data"]["type"] == "function"]
        assert function_spans
        assert secret not in json.dumps(destination.spans)

    failure = LookupError(secret)
    for asynchronous in (False, True):
        received = []
        context = {"approved": "Application-approved error"}

        def formatter(ctx, error):
            assert ctx.context is context
            received.append(error)
            return ctx.context["approved"]

        async def async_formatter(ctx, error):
            return formatter(ctx, error)

        @function_tool(failure_error_function=async_formatter if asynchronous else formatter)
        def fail() -> str:
            raise failure

        _, model = await tool_turn(fail, {}, context=context)
        assert received == [failure]
        assert tool_outputs(model.requests[-1]) == {"application-call": context["approved"]}

    @function_tool(failure_error_function=None)
    def propagate() -> str:
        raise failure

    with pytest.raises(UserError) as caught:
        await tool_turn(propagate, {})
    assert caught.value.__cause__ is failure


@pytest.mark.asyncio
async def test_f03_t04():
    for predicate_kind in ("static", "sync", "async"):
        for enabled in (True, False):
            effects = []
            context = {"allowed": enabled}

            def predicate(ctx, agent):
                assert ctx.context is context
                return agent.name == "Authorized" and ctx.context["allowed"]

            async def async_predicate(ctx, agent):
                return predicate(ctx, agent)

            policy = enabled if predicate_kind == "static" else (
                async_predicate if predicate_kind == "async" else predicate)

            @function_tool(is_enabled=policy)
            def deliver(parcel: str) -> str:
                effects.append(parcel)
                return f"Delivered {parcel}"

            model = RecordingModel([function_call(deliver.name, {"parcel": "box"}, "delivery")], "Done.")
            agent = Agent(name="Authorized", model=model, tools=[deliver])
            if enabled:
                assert (await run_agent(agent, context=context)).final_output == "Done."
                assert effects == ["box"]
                assert tool_outputs(model.requests[-1]) == {"delivery": "Delivered box"}
            else:
                with pytest.raises(ModelBehaviorError):
                    await run_agent(agent, context=context)
                assert effects == []
            assert [tool.name for tool in model.requests[0]["tools"]] == ([deliver.name] if enabled else [])
        if predicate_kind != "static":
            context = {"allowed": True}
            effects = []
            model = RecordingModel([function_call(deliver.name, {"parcel": "box"}, "delivery")])
            agent = Agent(name="Unauthorized", model=model, tools=[deliver])
            with pytest.raises(ModelBehaviorError):
                await run_agent(agent, context=context)
            assert effects == []
            assert model.requests[0]["tools"] == []

    # Change eligibility at the application model boundary, after declaration.
    for revoke in (False, True):
        context = {"allowed": True}
        effects = []

        @function_tool(is_enabled=lambda ctx, agent: ctx.context["allowed"])
        def guarded() -> str:
            effects.append("delivered")
            return "Delivered"

        class RevokingModel(RecordingModel):
            async def get_response(self, *args, **kwargs):
                response = await super().get_response(*args, **kwargs)
                context["allowed"] = not revoke
                return response

        model = RevokingModel([function_call(guarded.name, {}, "guarded")], "Done.")
        agent = Agent(name="Authorized", model=model, tools=[guarded])
        if revoke:
            with pytest.raises(ModelBehaviorError):
                await run_agent(agent, context=context)
            assert effects == []
        else:
            await run_agent(agent, context=context)
            assert effects == ["delivered"]
            assert tool_outputs(model.requests[-1]) == {"guarded": "Delivered"}
        assert [tool.name for tool in model.requests[0]["tools"]] == [guarded.name]


@pytest.mark.asyncio
async def test_f03_t05():
    text = ToolOutputText(text="Application report")
    image = ToolOutputImage(image_url="https://example.org/chart.png", detail="high")
    file = ToolOutputFileContent(file_data="cmVwb3J0Cg==", filename="report.txt")
    expected = {
        "text": {"type": "input_text", "text": text.text},
        "image": {"type": "input_image", "image_url": image.image_url, "detail": image.detail},
        "file": {"type": "input_file", "file_data": file.file_data, "filename": file.filename},
    }
    for content, kinds in ((text, ["text"]), (image, ["image"]), (file, ["file"]),
                           ([text, image, file], ["text", "image", "file"])):
        executed = []

        @function_tool
        def report():
            executed.append("reported")
            return content

        _, model = await tool_turn(report, {})
        assert executed == ["reported"]
        outputs = tool_outputs(model.requests[-1])
        assert set(outputs) == {"application-call"}
        parts = outputs["application-call"]
        assert isinstance(parts, list) and len(parts) == len(kinds)
        assert sorted(json.dumps(part, sort_keys=True) for part in parts) == sorted(
            json.dumps(expected[kind], sort_keys=True) for kind in kinds)


@pytest.mark.asyncio
async def test_f03_t06():
    private = {"view": "private-rendering-91d", "scores": [3, 9]}
    observed = []

    def extract(ctx):
        observed.append((ctx.output, ctx.raw_item["call_id"]))
        return private

    @function_tool(custom_data_extractor=extract)
    def result() -> str:
        return "Public summary"

    run, model = await tool_turn(result, {})
    outputs = [item for item in run.new_items if item.type == "tool_call_output_item"]
    assert len(outputs) == 1
    assert outputs[0].custom_data == private
    assert observed == [("Public summary", "application-call")]
    assert tool_outputs(model.requests[-1]) == {"application-call": "Public summary"}
    assert private["view"] not in json.dumps(model.requests[-1]["input"])
    assert all("custom_data" not in item for item in model.requests[-1]["input"])


@pytest.mark.asyncio
async def test_f03_t07():
    # A blocked application operation cannot finish without a release; the
    # outer helper deadline bounds broken implementations that ignore timeouts.
    # "slow" outlasts the short deadline used by the blocked modes but stays within
    # its own configured duration, so the caller-supplied value must be honoured.
    for mode in ("complete", "slow", "default", "formatted", "raise"):
        started, release = asyncio.Event(), asyncio.Event()
        effects, errors = [], []
        if mode == "complete":
            release.set()

        async def work() -> str:
            started.set()
            if mode == "slow":
                await asyncio.sleep(0.6)
            else:
                await release.wait()
            effects.append("committed")
            return "Committed"

        def timeout_formatter(ctx, error):
            errors.append(error)
            return "Application timeout"

        settings = {"timeout": 10 if mode == "slow" else 0.1,
                    "timeout_behavior": "raise_exception" if mode == "raise" else "error_as_result"}
        if mode == "formatted":
            settings["timeout_error_function"] = timeout_formatter
        tool = function_tool(work, **settings)
        if mode == "raise":
            with pytest.raises(ToolTimeoutError):
                await tool_turn(tool, {})
            assert effects == []
        else:
            _, model = await tool_turn(tool, {})
            output = tool_outputs(model.requests[-1])["application-call"]
            if mode in ("complete", "slow"):
                assert output == "Committed"
                assert effects == ["committed"]
            else:
                assert isinstance(output, str) and output and output != "Committed"
                assert effects == []
            if mode == "formatted":
                assert output == "Application timeout"
                assert len(errors) == 1 and isinstance(errors[0], ToolTimeoutError)
        assert started.is_set()


@pytest.mark.asyncio
async def test_f03_t08():
    def synchronous() -> str:
        return "Sync result"

    async def asynchronous() -> str:
        return "Async result"

    # Configuration and first use share the capture, leaving validation timing free.
    for handler, timeout in ((synchronous, 1), (asynchronous, 0), (asynchronous, -0.5)):
        with pytest.raises(ValueError):
            tool = function_tool(handler, timeout=timeout)
            await tool_turn(tool, {})
    tool = function_tool(asynchronous, timeout=1)
    _, model = await tool_turn(tool, {})
    assert tool_outputs(model.requests[-1]) == {"application-call": "Async result"}


@pytest.mark.asyncio
async def test_f03_t09():
    for format in (None, {"type": "grammar", "syntax": "lark", "definition": 'start: "MOVE" INT "to" INT\n%import common.INT\n%import common.WS\n%ignore WS'}):
        received = []
        context = {"prefix": "Executed"}

        async def execute(ctx, raw):
            assert ctx.context is context
            received.append(raw)
            return f"{ctx.context['prefix']}: {raw}"

        tool = CustomTool(name="raw_command", description="Execute a raw command.",
                          on_invoke_tool=execute, format=format)
        raw = "  MOVE 12 to 7\n"
        call = ResponseCustomToolCall(type="custom_tool_call", name=tool.name,
                                      call_id="raw-call", input=raw)
        model = RecordingModel([call], "Finished.")
        result = await run_agent(Agent(name="Raw", model=model, tools=[tool]), context=context)
        assert result.final_output == "Finished."
        assert received == [raw]
        assert tool_outputs(model.requests[-1], kind="custom_tool_call_output") == {
            "raw-call": f"Executed: {raw}"}
        declaration = model.requests[0]["tools"]
        assert [item.name for item in declaration] == [tool.name]
        assert declaration[0].description == tool.description
        assert declaration[0].format == format
