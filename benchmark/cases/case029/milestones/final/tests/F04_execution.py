# feature: F04
"""Acceptance coverage for the public agent loop and its result/recovery policies."""
import asyncio
import copy

import pytest
from openai.types.responses import ResponseReasoningItem

from F01_helpers import RecordingModel, function_call, text_message
from F02_helpers import AttemptModel
from F03_helpers import tool_outputs
from F04_helpers import (
    RecoveryOutput, conversation_text, execution_run, execution_tool, refusal_message,
)
from velmora import (
    Agent, MaxTurnsExceeded, ModelBehaviorError, ModelRefusalError, ModelSettings,
    RunConfig, RunErrorHandlerResult, Runner, UserError, handoff,
)
from velmora import ToolsToFinalOutputResult
from velmora.run import ModelInputData


def test_f04_t01():
    # run_sync owns its event loop; the async entry is exercised by all later tests.
    effects = []
    tool = execution_tool(effects)
    model = RecordingModel(
        [text_message("Working."), function_call(tool.name, {"value": "one"}, "c1")],
        [function_call(tool.name, {"value": "two"}, "c2")], "Complete.")
    result = Runner.run_sync(Agent(name="Worker", model=model, tools=[tool]),
                             "Start here.", run_config=RunConfig(tracing_disabled=True))
    assert effects == ["one", "two"]
    assert result.final_output == "Complete."
    assert model.requests[0]["input"] == [{"role": "user", "content": "Start here."}]
    assert tool_outputs(model.requests[1]) == {"c1": "recorded:one"}
    assert tool_outputs(model.requests[2]) == {"c1": "recorded:one", "c2": "recorded:two"}
    assert len(model.requests) == 3


@pytest.mark.asyncio
async def test_f04_t02():
    for allowance, completed_turns, succeeds in (("default", 10, True),
                                               ("default", 11, False),
                                               (2, 2, True), (2, 3, False),
                                               (None, 12, True)):
        effects = []
        tool = execution_tool(effects)
        outputs = [[function_call(tool.name, {"value": f"{turn}:a"}, f"{turn}a"),
                    function_call(tool.name, {"value": f"{turn}:b"}, f"{turn}b")]
                   for turn in range(completed_turns - 1)] + ["Done."]
        model = RecordingModel(*outputs)
        agent = Agent(name="Counter", model=model, tools=[tool])
        options = {} if allowance == "default" else {"max_turns": allowance}
        if succeeds:
            result = await execution_run(agent, **options)
            assert result.final_output == "Done."
            assert len(model.requests) == completed_turns
            assert sorted(effects) == sorted(f"{turn}:{suffix}"
                for turn in range(completed_turns - 1) for suffix in ("a", "b"))
        else:
            with pytest.raises(MaxTurnsExceeded):
                await execution_run(agent, **options)
            # Do not demand whether an extra request probes exhaustion.
            limit = 10 if allowance == "default" else allowance
            assert len(model.requests) >= limit
            assert set(f"{turn}:{suffix}" for turn in range(limit - 1)
                       for suffix in ("a", "b")).issubset(effects)


@pytest.mark.asyncio
async def test_f04_t03():
    # One response requests two tools and also carries an assistant answer: the
    # first-result policy, the selected tool (requested second) and the callback
    # (seeing every result) must each be distinguishable, and outrank the answer.
    for policy in (None, "run_llm_again", "stop_on_first_tool", "selected", "callback_continue", "callback_finish"):
        effects, observed = [], []
        side = execution_tool(effects, name="side")
        tool = execution_tool(effects)
        # The selected tool also finishes after "side", so request and completion order agree.
        record = tool.on_invoke_tool
        async def later(context, arguments, record=record):
            await asyncio.sleep(0.05)
            return await record(context, arguments)
        tool.on_invoke_tool = later
        def choose(context, results):
            observed.extend(result.output for result in results)
            return ToolsToFinalOutputResult(policy == "callback_finish", "Chosen by app.")
        behavior = ({"stop_at_tool_names": [tool.name]} if policy == "selected" else
                    choose if policy.startswith("callback") else policy) if policy else None
        model = RecordingModel([function_call(side.name, {"value": "side"}, "s"),
                                function_call(tool.name, {"value": "policy"}, "p"),
                                text_message("Accompanying answer.")], "Model continuation.")
        agent = Agent(name="Policies", model=model, tools=[side, tool],
                      **({"tool_use_behavior": behavior} if behavior else {}))
        result = await execution_run(agent)
        assert sorted(effects) == ["policy", "side"]
        if policy in ("stop_on_first_tool", "selected", "callback_finish"):
            assert result.final_output == {"stop_on_first_tool": "recorded:side", "selected": "recorded:policy",
                                           "callback_finish": "Chosen by app."}[policy]
            assert len(model.requests) == 1
        else:
            assert result.final_output == "Model continuation."
            assert tool_outputs(model.requests[1]) == {"s": "recorded:side", "p": "recorded:policy"}
            assert len(model.requests) == 2
        if policy and policy.startswith("callback"):
            assert sorted(observed) == ["recorded:policy", "recorded:side"]

    # A selected policy must continue through non-selected tools.
    effects = []
    first = execution_tool(effects, name="first")
    selected = execution_tool(effects, name="selected")
    model = RecordingModel([function_call(first.name, {"value": "a"}, "a")],
                           [function_call(selected.name, {"value": "b"}, "b")])
    result = await execution_run(Agent(name="Select", model=model, tools=[first, selected],
        tool_use_behavior={"stop_at_tool_names": [selected.name]}))
    assert effects == ["a", "b"]
    assert result.final_output == "recorded:b"
    assert tool_outputs(model.requests[1]) == {"a": "recorded:a"}


@pytest.mark.asyncio
async def test_f04_t04():
    for choice, retain in (("auto", False), ("none", False), ("required", False),
                           ("record", False), ("required", True), ("record", True)):
        effects = []
        tool = execution_tool(effects)
        model = AttemptModel(*(["No tools."] if choice == "none" else [
            [function_call(tool.name, {"value": "choice"}, "choice")], "Finished."]))
        result = await execution_run(Agent(name="Choice", model=model, tools=[tool],
            model_settings=ModelSettings(tool_choice=choice), reset_tool_choice=not retain))
        assert model.requests[0]["settings"].tool_choice == choice
        assert result.final_output == ("No tools." if choice == "none" else "Finished.")
        if choice != "none":
            assert effects == ["choice"]
            next_choice = model.requests[1]["settings"].tool_choice
            if retain:
                assert next_choice == choice
            else:
                assert next_choice in (None, "auto")
            assert tool_outputs(model.requests[1]) == {"choice": "recorded:choice"}


@pytest.mark.asyncio
async def test_f04_t05():
    effects = []
    tool = execution_tool(effects)
    reasoning = ResponseReasoningItem(id="thought", type="reasoning", summary=[
        {"type": "summary_text", "text": "Consider the task."}])
    call = function_call(tool.name, {"value": "history"}, "history-call")
    answer = text_message("History complete.")
    originals = [reasoning, call, answer]
    before = [item.model_dump() for item in originals]
    model = RecordingModel([reasoning, call], [answer])
    agent = Agent(name="History", model=model, tools=[tool])
    initial = [{"role": "user", "content": "Keep this input."}]
    result = await execution_run(agent, copy.deepcopy(initial))
    assert result.final_output == "History complete."
    assert result.last_agent is agent
    assert [[item.model_dump() for item in response.output] for response in result.raw_responses] == [before[:2], before[2:]]
    items = {kind: [item for item in result.new_items if item.type == kind] for kind in
             ("reasoning_item", "tool_call_item", "tool_call_output_item", "message_output_item")}
    assert [item.raw_item.model_dump() for item in items["reasoning_item"]] == [before[0]]
    assert [item.raw_item.call_id for item in items["tool_call_item"]] == ["history-call"]
    assert [(item.raw_item["call_id"], item.output) for item in items["tool_call_output_item"]] == [("history-call", "recorded:history")]
    assert [item.raw_item.model_dump() for item in items["message_output_item"]] == [before[2]]
    history = result.to_input_list()
    assert history[:1] == initial
    assert [item["summary"] for item in history if item.get("type") == "reasoning"] == [before[0]["summary"]]
    assert [item["call_id"] for item in history if item.get("type") == "function_call"] == ["history-call"]
    assert tool_outputs({"input": history}) == {"history-call": "recorded:history"}
    assert conversation_text(history) == ["History complete."]
    continuation = RecordingModel("Continued.")
    resumed = await execution_run(Agent(name="Continuation", model=continuation), history)
    assert resumed.final_output == "Continued."
    assert continuation.requests[0]["input"] == history
    assert [item.model_dump() for item in originals] == before


@pytest.mark.asyncio
async def test_f04_t06():
    effects, seen = [], []
    tool = execution_tool(effects)
    async def transform(data):
        seen.append(copy.deepcopy(data.model_data.input))
        return ModelInputData(input=data.model_data.input + [{"role": "user", "content": f"Request {len(seen)}"}],
                              instructions=f"Filtered {len(seen)}")
    model = RecordingModel([function_call(tool.name, {"value": "filtered"}, "f")], "Filtered answer.")
    result = await execution_run(Agent(name="Filtered", instructions="Original instructions", model=model, tools=[tool]),
        "Original input", config=RunConfig(tracing_disabled=True, call_model_input_filter=transform))
    assert result.final_output == "Filtered answer."
    assert len(seen) == 2
    for index, request in enumerate(model.requests, 1):
        assert request["instructions"] == f"Filtered {index}"
        assert request["input"] == seen[index - 1] + [{"role": "user", "content": f"Request {index}"}]
    assert tool_outputs(model.requests[1]) == {"f": "recorded:filtered"}
    history = result.to_input_list()
    assert history[0] == {"role": "user", "content": "Original input"}
    assert not any(item.get("role") == "user" and item["content"].startswith("Request ") for item in history)
    assert tool_outputs({"input": history}) == {"f": "recorded:filtered"}
    next_model = RecordingModel("Next.")
    next_result = await execution_run(Agent(name="Next", model=next_model), history)
    assert next_result.final_output == "Next."
    assert next_model.requests[0]["input"] == history


@pytest.mark.asyncio
async def test_f04_t07():
    for continue_missing in (False, True):
        model = RecordingModel([function_call("unavailable", {}, "missing")], "Recovered by model.")
        agent = Agent(name="Missing", model=model)
        if not continue_missing:
            with pytest.raises(ModelBehaviorError):
                await execution_run(agent)
        else:
            result = await execution_run(agent, config=RunConfig(tracing_disabled=True,
                tool_not_found_behavior="return_error_to_model"))
            assert result.final_output == "Recovered by model."
            outputs = tool_outputs(model.requests[1])
            assert set(outputs) == {"missing"}
            assert isinstance(outputs["missing"], str) and outputs["missing"]
            assert len(model.requests) == 2


@pytest.mark.asyncio
async def test_f04_t08():
    config = RunConfig(tracing_disabled=True, tool_name_collision_policy="error")
    effects = []
    tool = execution_tool(effects, name="route")
    target_model = RecordingModel("Transferred.")
    target = Agent(name="Target", model=target_model)
    transfer = handoff(target, tool_name_override="transfer")
    model = RecordingModel([function_call("route", {"value": "valid"}, "valid")],
                           [function_call("transfer", {}, "transfer")])
    result = await execution_run(Agent(name="Valid", model=model, tools=[tool], handoffs=[transfer]), config=config)
    assert result.final_output == "Transferred."
    assert result.last_agent is target
    assert effects == ["valid"]
    assert tool_outputs(target_model.requests[0])["valid"] == "recorded:valid"
    for collision in ("functions", "handoffs", "mixed"):
        effects = []
        model = RecordingModel("Must not dispatch.")
        a = execution_tool(effects, name="duplicate")
        b = execution_tool(effects, name="duplicate")
        h1 = handoff(Agent(name="One", model=RecordingModel("One.")), tool_name_override="duplicate")
        h2 = handoff(Agent(name="Two", model=RecordingModel("Two.")), tool_name_override="duplicate")
        agent = Agent(name="Conflict", model=model,
                      tools=[a, b] if collision == "functions" else [a] if collision == "mixed" else [],
                      handoffs=[h1, h2] if collision == "handoffs" else [h1] if collision == "mixed" else [])
        with pytest.raises(UserError):
            await execution_run(agent, config=config)
        assert effects == []


@pytest.mark.asyncio
async def test_f04_t09():
    for kind, error_class in (("max_turns", MaxTurnsExceeded), ("model_refusal", ModelRefusalError),
                              ("invalid_final_output", ModelBehaviorError)):
        def setup():
            effects = []
            tool = execution_tool(effects)
            outputs = ([function_call(tool.name, {"value": "limit"}, "limit")]
                       if kind == "max_turns" else [refusal_message("Cannot comply.")]
                       if kind == "model_refusal" else [text_message("invalid JSON")])
            model = RecordingModel(outputs)
            return Agent(name="Recovery", model=model, tools=[tool], output_type=RecoveryOutput), model
        options = {"max_turns": 1} if kind == "max_turns" else {}
        for handler_mode in ("absent", "decline", "replace", "invalid"):
            agent, model = setup()
            observed = []
            def handle(data):
                observed.append(data)
                if handler_mode == "decline":
                    return None
                return {"summary": "Application replacement."} if handler_mode == "replace" else {"unexpected": "value"}
            handlers = {} if handler_mode == "absent" else {"error_handlers": {kind: handle}}
            if handler_mode == "replace":
                result = await execution_run(agent, **options, **handlers)
                assert isinstance(result.final_output, RecoveryOutput)
                assert result.final_output.summary == "Application replacement."
            else:
                with pytest.raises(UserError if handler_mode == "invalid" else error_class):
                    await execution_run(agent, **options, **handlers)
            if handler_mode != "absent":
                assert len(observed) == 1
                assert isinstance(observed[0].error, error_class)
            assert len(model.requests) == 1

    for inclusion in ("default", False):
        effects = []
        tool = execution_tool(effects)
        model = RecordingModel([function_call(tool.name, {"value": "past"}, "past")])
        replacement = (RunErrorHandlerResult("Limit summary.") if inclusion == "default" else
                       RunErrorHandlerResult("Limit summary.", include_in_history=False))
        result = await execution_run(Agent(name="History recovery", model=model, tools=[tool]), max_turns=1,
                                    error_handlers={"max_turns": lambda data: replacement})
        assert result.final_output == "Limit summary."
        assert conversation_text(result.to_input_list()) == (["Limit summary."] if inclusion == "default" else [])
        assert tool_outputs({"input": result.to_input_list()}) == {"past": "recorded:past"}


@pytest.mark.asyncio
async def test_f04_t10():
    effects = []
    tool = execution_tool(effects)
    model = RecordingModel([function_call(tool.name, {"value": "once"}, "once")],
                           "not structured", [function_call(tool.name, {"value": "replayed"}, "again")])
    result = await execution_run(Agent(name="In-place recovery", model=model, tools=[tool], output_type=RecoveryOutput),
        error_handlers={"invalid_final_output": lambda data: {"summary": "Repaired locally."}})
    assert result.final_output == RecoveryOutput(summary="Repaired locally.")
    assert effects == ["once"]
    assert len(model.requests) == 2
    assert tool_outputs(model.requests[1]) == {"once": "recorded:once"}
    assert tool_outputs({"input": result.to_input_list()}) == {"once": "recorded:once"}


@pytest.mark.asyncio
async def test_f04_t11():
    # Compare identical mixed responses with and without an approval requirement.
    for approval in (False, True):
        effects = []
        ready = execution_tool(effects, name="ready")
        gated = execution_tool(effects, name="gated", needs_approval=approval)
        target_model = RecordingModel("Destination answer.")
        target = Agent(name="Destination", model=target_model)
        transfer = handoff(target, tool_name_override="transfer_destination")
        model = RecordingModel([function_call(ready.name, {"value": "ready"}, "ready"),
                                function_call(gated.name, {"value": "approved"}, "gate"),
                                function_call(transfer.tool_name, {}, "transfer"),
                                text_message("Source answer.")])
        source = Agent(name="Source", model=model, tools=[ready, gated], handoffs=[transfer],
                       tool_use_behavior="stop_on_first_tool")
        result = await execution_run(source)
        if approval:
            assert len(result.interruptions) == 1
            assert result.interruptions[0].tool_name == gated.name
            assert target_model.requests == []
            assert effects == ["ready"]
            state = result.to_state()
            state.approve(result.interruptions[0])
            result = await execution_run(source, state)
        assert result.final_output == "Destination answer."
        assert result.last_agent is target
        assert sorted(effects) == ["approved", "ready"]
        assert len(model.requests) == 1
        assert len(target_model.requests) == 1
        assert tool_outputs(target_model.requests[0])["ready"] == "recorded:ready"
        assert tool_outputs(target_model.requests[0])["gate"] == "recorded:approved"


@pytest.mark.asyncio
async def test_f04_t12():
    # Cases: refusal alone or after an earlier answer (last message refuses); tool
    # completion; remaining tool work under the default policy; and an earlier
    # refusal followed by a final answer (the last message does not refuse).
    for case in ("refusal", "last_refusal", "tool_completion", "tool_work", "earlier_refusal"):
        effects = []
        tool = execution_tool(effects)
        call = function_call(tool.name, {"value": "priority"}, "priority")
        refusal = refusal_message("Explicit refusal.")
        output = {"refusal": [refusal], "last_refusal": [text_message("Preface."), refusal],
                  "tool_completion": [call, refusal], "tool_work": [call, refusal],
                  "earlier_refusal": [refusal, text_message("Accepted answer.")]}[case]
        model = RecordingModel(output, "After tool work.")
        options = {"tool_use_behavior": "stop_on_first_tool"} if case == "tool_completion" else {}
        agent = Agent(name="Refusal priority", model=model, tools=[tool], **options)
        if case in ("refusal", "last_refusal"):
            with pytest.raises(ModelRefusalError) as error:
                await execution_run(agent)
            assert error.value.refusal == "Explicit refusal."
        else:
            result = await execution_run(agent)
            assert result.final_output == {"tool_completion": "recorded:priority", "tool_work": "After tool work.",
                                           "earlier_refusal": "Accepted answer."}[case]
        assert effects == (["priority"] if case.startswith("tool") else [])
        assert len(model.requests) == (2 if case == "tool_work" else 1)
        if case == "tool_work":
            assert tool_outputs(model.requests[1]) == {"priority": "recorded:priority"}
