# feature: F09
"""Acceptance tests for conversation transfer and manager-controlled delegation."""
import pytest
from pydantic import BaseModel, Field
from F01_helpers import RecordingModel, function_call, text_message
from F03_helpers import tool_outputs
from F04_helpers import execution_run, execution_tool, conversation_text
from F06_helpers import UsageModel
from F08_helpers import pending_calls, IdentifiedResponseModel
from F09_helpers import DelegationModel, history_contents
from velmora import (Agent, RunConfig, ModelSettings, Usage, handoff,
                    HandoffOutputItem, ToolCallOutputItem)
from velmora import ModelBehaviorError, UserError, MaxTurnsExceeded


@pytest.mark.asyncio
async def test_f09_t01():
    class Answer(BaseModel):
        decision: str
    destination = Agent(name="Reviewer", instructions="Review independently.",
        model=DelegationModel('{"decision":"accepted"}'), output_type=Answer)
    unavailable = Agent(name="Unavailable", model=RecordingModel())
    withheld = Agent(name="Withheld", model=RecordingModel())
    decisions = []
    def decide(context, agent):
        decisions.append(context.context["tier"])
        return context.context["tier"] == "premium"
    async def allow(context, agent):
        return True
    selected = handoff(destination, is_enabled=allow)
    hidden = handoff(unavailable, is_enabled=False)
    conditional = handoff(withheld, is_enabled=decide)
    source = Agent(name="Router", model=DelegationModel([
        function_call(selected.tool_name, {}, "route")]), handoffs=[selected, hidden, conditional])
    result = await execution_run(source, "Please review this record.", context={"tier": "basic"})
    assert [h.tool_name for h in source.model.requests[0]["handoffs"]] == [selected.tool_name]
    assert decisions and set(decisions) == {"basic"}
    assert result.last_agent is destination
    assert result.final_output == Answer(decision="accepted")
    request = destination.model.requests[0]
    assert request["instructions"] == "Review independently."
    assert request["output_schema"] is not None
    assert "Please review this record." in history_contents(request["input"])
    assert len(source.model.requests) == len(destination.model.requests) == 1
    assert unavailable.model.requests == []


@pytest.mark.asyncio
async def test_f09_t02():
    class Payload(BaseModel):
        topic: str
        count: int = Field(gt=0)
    for arguments in ({"topic": "invoices", "count": 3}, {"topic": "invoices", "count": 0}, "malformed"):
        received = []
        async def accept(context, payload):
            received.append((context.context, payload))
        destination = Agent(name="Typed", model=RecordingModel("Validated."))
        transfer = handoff(destination, input_type=Payload, on_handoff=accept)
        call = function_call(transfer.tool_name, arguments, "typed")
        if arguments == "malformed":
            call.arguments = "{invalid json"
        source = Agent(name="Source", model=RecordingModel([call]), handoffs=[transfer])
        if isinstance(arguments, dict) and arguments["count"] > 0:
            result = await execution_run(source, "Preserve this conversation.", context={"tenant": "billing"})
            assert result.final_output == "Validated." and result.last_agent is destination
            assert received == [({"tenant": "billing"}, Payload(**arguments))]
            assert "Preserve this conversation." in history_contents(destination.model.requests[0]["input"])
        else:
            with pytest.raises(ModelBehaviorError):
                await execution_run(source, "Preserve this conversation.")
            assert received == [] and destination.model.requests == []


@pytest.mark.asyncio
async def test_f09_t03():
    for specific in (False, True):
        calls = []
        def global_filter(data):
            calls.append("global")
            return data.clone(input_history=({"role": "user", "content": "Global selection"},),
                              pre_handoff_items=(), new_items=())
        def local_filter(data):
            calls.append("local")
            return data.clone(input_history=({"role": "user", "content": "Local selection"},),
                              pre_handoff_items=(), new_items=())
        target = Agent(name="Filtered", model=RecordingModel("Filtered result"))
        transfer = handoff(target, input_filter=local_filter if specific else None)
        source = Agent(name="Source", model=RecordingModel([
            function_call(transfer.tool_name, {}, "filtered")]), handoffs=[transfer])
        config = RunConfig(tracing_disabled=True, handoff_input_filter=global_filter)
        result = await execution_run(source, "Original history", config=config)
        assert result.final_output == "Filtered result"
        assert calls == (["local"] if specific else ["global"])
        assert target.model.requests[0]["input"] == [{"role": "user", "content":
            "Local selection" if specific else "Global selection"}]
        for continuation in ({"conversation_id": "conversation-app"},
                             {"previous_response_id": "application-response"},
                             {"auto_previous_response_id": True}):
            source.model = RecordingModel([function_call(transfer.tool_name, {}, "server")])
            with pytest.raises(UserError):
                await execution_run(source, "Original history", config=config, **continuation)
            assert target.model.requests[1:] == []


@pytest.mark.asyncio
async def test_f09_t04():
    class Work(BaseModel):
        text: str
        language: str
    for structured in (False, True):
        builder_values, extracted = [], []
        async def builder(options):
            builder_values.append(options["params"])
            return [{"role": "user", "content": options["params"]["language"] + ":" + options["params"]["text"]}]
        async def extract(result):
            extracted.append(result.final_output)
            return "chosen:" + result.final_output
        specialist = Agent(name="Specialist", model=RecordingModel("Specialist answer"))
        operation = specialist.as_tool("delegate", "Delegate work", custom_output_extractor=extract,
            **({"parameters": Work, "input_builder": builder} if structured else {}))
        arguments = {"text": "bonjour", "language": "French"} if structured else {"input": "Translate bonjour"}
        manager = Agent(name="Manager", model=RecordingModel([
            function_call(operation.name, arguments, "delegate-call")], "Manager conclusion"), tools=[operation])
        result = await execution_run(manager, "Manage translation")
        assert result.last_agent is manager and result.final_output == "Manager conclusion"
        assert extracted == ["Specialist answer"]
        assert tool_outputs(manager.model.requests[1])["delegate-call"] == "chosen:Specialist answer"
        assert history_contents(specialist.model.requests[0]["input"]) == [
            "French:bonjour" if structured else "Translate bonjour"]
        assert builder_values == ([arguments] if structured else [])


@pytest.mark.asyncio
async def test_f09_t05():
    for allowance in (3, 1):
        effects = []
        work = execution_tool(effects)
        nested = UsageModel([Usage(requests=1, input_tokens=7, output_tokens=2, total_tokens=9)] * 3,
            [function_call(work.name, {"value": "first"}, "inner-one")],
            [function_call(work.name, {"value": "second"}, "inner-two")], "Nested done")
        specialist = Agent(name="Specialist", model=nested, tools=[work])
        operation = specialist.as_tool("delegate", "Delegate", max_turns=allowance,
            run_config=RunConfig(tracing_disabled=True, model_settings=ModelSettings(temperature=0.25)),
            failure_error_function=None)
        outer = UsageModel([Usage(requests=1, input_tokens=11, output_tokens=3, total_tokens=14)] * 2,
            [function_call(operation.name, {"input": "Nested work"}, "outer")], "Manager done")
        manager = Agent(name="Manager", model=outer, tools=[operation])
        config = RunConfig(tracing_disabled=True, model_settings=ModelSettings(temperature=0.75))
        if allowance == 1:
            with pytest.raises(MaxTurnsExceeded):
                await execution_run(manager, config=config, max_turns=2)
            assert effects == ["first"]
        else:
            result = await execution_run(manager, config=config, max_turns=2)
            assert result.final_output == "Manager done" and effects == ["first", "second"]
            usage = result.context_wrapper.usage
            assert (usage.requests, usage.input_tokens, usage.output_tokens, usage.total_tokens) == (5, 43, 12, 55)
    for explicit in (False, True):
        nested = DelegationModel("Nested configured")
        specialist = Agent(name="Configured", model=nested)
        operation = specialist.as_tool("configure", "Delegate", **({"run_config": RunConfig(
            tracing_disabled=True, model_settings=ModelSettings(temperature=0.25))} if explicit else {}))
        outer = DelegationModel([function_call(operation.name, {"input": "Configure"}, "config")], "Done")
        await execution_run(Agent(name="Manager", model=outer, tools=[operation]),
            config=RunConfig(tracing_disabled=True, model_settings=ModelSettings(temperature=0.75)))
        assert outer.requests[0]["settings"].temperature == 0.75
        assert nested.requests[0]["settings"].temperature == (0.25 if explicit else 0.75)


@pytest.mark.asyncio
async def test_f09_t06():
    effects = []
    before = execution_tool(effects, name="before")
    guarded = execution_tool(effects, name="guarded", needs_approval=True)
    nested = RecordingModel([function_call(before.name, {"value": "completed"}, "before-call")],
        [function_call(guarded.name, {"value": "approved"}, "guarded-call")], "Specialist finished")
    specialist = Agent(name="Specialist", model=nested, tools=[before, guarded])
    operation = specialist.as_tool("delegate", "Delegate", needs_approval=True)
    outer = RecordingModel([function_call(operation.name, {"input": "Do work"}, "delegate-call")], "Manager finished")
    manager = Agent(name="Manager", model=outer, tools=[operation])
    paused = await execution_run(manager)
    assert set(pending_calls(paused)) == {"delegate-call"}
    assert effects == [] and nested.requests == [] and paused.final_output is None
    state = paused.to_state()
    state.approve(pending_calls(state)["delegate-call"])
    paused = await execution_run(manager, state)
    assert set(pending_calls(paused)) == {"guarded-call"}
    assert paused.final_output is None and effects == ["completed"]
    assert len(nested.requests) == 2
    state = paused.to_state()
    state.approve(pending_calls(state)["guarded-call"])
    result = await execution_run(manager, state)
    assert result.final_output == "Manager finished" and result.last_agent is manager
    assert effects == ["completed", "approved"] and len(nested.requests) == 3
    assert tool_outputs(nested.requests[-1])["guarded-call"] == "recorded:approved"
    assert tool_outputs(outer.requests[-1])["delegate-call"] == "Specialist finished"


@pytest.mark.asyncio
async def test_f09_t07():
    for transcript in (False, True):
        effects = []
        work = execution_tool(effects)
        final = Agent(name="Final", model=RecordingModel("Final answer"))
        next_transfer = handoff(final)
        middle = Agent(name="Middle", model=RecordingModel([
            text_message("Repeated occurrence"),
            function_call(work.name, {"value": "historical-result"}, "historical-call")],
            [text_message("Current handoff message"), function_call(next_transfer.tool_name, {}, "next")]),
            tools=[work], handoffs=[next_transfer])
        transfer = handoff(middle)
        first = Agent(name="First", model=RecordingModel([
            text_message("Repeated occurrence"), function_call(transfer.tool_name, {}, "first")]), handoffs=[transfer])
        history = [{"role": "user", "content": "Earlier question"},
                   {"role": "assistant", "content": "Earlier answer"},
                   {"type": "reasoning", "id": "reasoning-history", "summary": [
                       {"type": "summary_text", "text": "Earlier reasoning"}]},
                   {"type": "function_call", "name": "previous_operation",
                    "arguments": '{"query":"Earlier tool argument"}', "call_id": "earlier-tool"},
                   {"type": "function_call_output", "call_id": "earlier-tool", "output": "Earlier tool result"},
                   {"role": "user", "content": "Latest question"}]
        # Exercise the default as well as explicit transcript selection.
        history_options = {"nest_handoff_history": True} if transcript else {}
        result = await execution_run(first, history,
            config=RunConfig(tracing_disabled=True, **history_options))
        assert result.last_agent is final and result.final_output == "Final answer"
        assert effects == ["historical-result"]
        destination_input = final.model.requests[0]["input"]
        if transcript:
            content = "\n".join(history_contents(destination_input))
            markers = ["Earlier question", "Earlier answer", "Earlier reasoning",
                       "previous_operation", "Earlier tool argument", "Earlier tool result", "Latest question"]
            assert all(content.count(marker) == 1 for marker in markers)
            assert [content.index(marker) for marker in markers] == sorted(content.index(marker) for marker in markers)
            assert content.count("Repeated occurrence") == 2
            assert "historical-result" in content and "recorded:historical-result" in content
            assert work.name in content
        else:
            assert destination_input[:len(history)] == history
            assert tool_outputs({"input": destination_input})["historical-call"] == "recorded:historical-result"
        assert conversation_text([item for item in destination_input if isinstance(item.get("content"), list)]).count("Current handoff message") == 1
        assert conversation_text([item for item in result.to_input_list() if isinstance(item.get("content"), list)]).count("Repeated occurrence") == 2
        assert conversation_text([item for item in result.to_input_list() if isinstance(item.get("content"), list)]).count("Current handoff message") == 1
        # Continue from the public history rather than reusing internal run state.
        final.model.outputs.append("Continuation answer")
        continued = await execution_run(final, result.to_input_list())
        assert continued.final_output == "Continuation answer"
        assert conversation_text([item for item in final.model.requests[-1]["input"] if isinstance(item.get("content"), list)]).count("Repeated occurrence") == 2


@pytest.mark.asyncio
async def test_f09_t08():
    for mode in ("run", "local-off", "local-on", "mapper", "filter", "server"):
        mapper_calls, filter_calls = [], []
        mapped = [{"role": "user", "content": "Application mapped history"}]
        def mapper(items):
            mapper_calls.append(items)
            return mapped
        def select(data):
            filter_calls.append(data)
            return data.clone(input_history=({"role": "user", "content": "Application filtered history"},),
                              pre_handoff_items=(), new_items=())
        target = Agent(name="Destination", model=IdentifiedResponseModel("Reached"))
        options = {}
        if mode in ("local-on", "local-off"):
            options["nest_handoff_history"] = mode == "local-on"
        if mode == "filter":
            options["input_filter"] = select
        transfer = handoff(target, **options)
        source = Agent(name="Source", model=IdentifiedResponseModel([
            text_message("Handoff turn content"), function_call(transfer.tool_name, {}, "move")]), handoffs=[transfer])
        history = [{"role": "user", "content": "Original user content"}]
        config = RunConfig(tracing_disabled=True, nest_handoff_history=mode != "local-on",
            handoff_history_mapper=mapper if mode in ("mapper", "filter", "server") else None)
        result = await execution_run(source, history, config=config,
            **({"conversation_id": "application-conversation"} if mode == "server" else {}))
        assert result.last_agent is target and result.final_output == "Reached"
        items = target.model.requests[0]["input"]
        if mode == "filter":
            assert items == [{"role": "user", "content": "Application filtered history"}]
            assert len(filter_calls) == 1 and mapper_calls == []
        elif mode == "mapper":
            assert items == mapped
            assert len(mapper_calls) == 1
            assert "Original user content" in history_contents(mapper_calls[0])
        elif mode == "server":
            assert mapper_calls == []
            assert target.model.requests[0]["conversation_id"] == "application-conversation"
            assert "Original user content" not in history_contents(items)
            assert "move" in tool_outputs({"input": items})
        elif mode == "local-off":
            assert items[0] == history[0]
        else:
            assert "Original user content" in "\n".join(history_contents(items))
            assert conversation_text([item for item in items if isinstance(item.get("content"), list)]).count("Handoff turn content") == 1


@pytest.mark.asyncio
async def test_f09_t09():
    invoked = []
    def record(label):
        async def callback(context):
            invoked.append(label)
        return callback
    first = Agent(name="First destination", model=RecordingModel("First took control"))
    second = Agent(name="Second destination", model=RecordingModel())
    third = Agent(name="Third destination", model=RecordingModel())
    transfers = [handoff(agent, on_handoff=record(agent.name)) for agent in (first, second, third)]
    source = Agent(name="Source", model=RecordingModel([
        function_call(t.tool_name, {}, f"handoff-{index}") for index, t in enumerate(transfers)]), handoffs=transfers)
    result = await execution_run(source)
    assert result.last_agent is first and result.final_output == "First took control"
    assert invoked == [first.name]
    assert second.model.requests == third.model.requests == []
    taken = [item for item in result.new_items if isinstance(item, HandoffOutputItem)]
    assert [item.raw_item["call_id"] for item in taken] == ["handoff-0"]
    not_taken = {item.raw_item["call_id"]: item.output for item in result.new_items
                 if isinstance(item, ToolCallOutputItem)}
    assert set(not_taken) == {"handoff-1", "handoff-2"}
    assert all(isinstance(value, str) and value for value in not_taken.values())
    assert tool_outputs(first.model.requests[0]) == {
        "handoff-0": taken[0].raw_item["output"], **not_taken}
