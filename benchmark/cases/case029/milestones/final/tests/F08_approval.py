# feature: F08
"""Acceptance checks for tool approval and detached run continuation."""
import copy
import json
import math
from pathlib import Path

import pytest
from pydantic import BaseModel, field_validator
from openai.types.responses import ResponseCustomToolCall
from _helpers import bounded, run_python
from F01_helpers import RecordingModel, function_call
from F03_helpers import tool_outputs
from F04_helpers import execution_tool, execution_run
from F08_helpers import (ApprovalContext, IdentifiedResponseModel, InterruptedWriteSession, checkpoint_scenario,
                         pending_calls, routed_checkpoint_scenario)
from velmora import (Agent, CustomTool, GuardrailFunctionOutput, InputGuardrail,
                    RunConfig, RunHooks, Runner, RunState)
from velmora.decorators import tool
from velmora import InputGuardrailTripwireTriggered, ModelBehaviorError, UserError
from velmora import Usage


@pytest.mark.asyncio
async def test_f08_t01():
    for approval in (True, "conditional"):
        effects, policies = [], []
        def policy(context, arguments, call_id):
            policies.append((context.context, arguments, call_id))
            return arguments["value"] == "review"
        operation = execution_tool(effects, needs_approval=policy if approval == "conditional" else True)
        calls = [function_call(operation.name, {"value": "review"}, "gated")]
        if approval == "conditional":
            calls.append(function_call(operation.name, {"value": "open"}, "free"))
        model = RecordingModel(calls, "Completed.")
        agent = Agent(name="Approval", model=model, tools=[operation])
        paused = await execution_run(agent, context={"owner": "application"})
        assert set(pending_calls(paused)) == {"gated"}
        proposal = pending_calls(paused)["gated"].raw_item
        assert proposal.name == operation.name
        assert json.loads(proposal.arguments) == {"value": "review"}
        assert paused.final_output is None
        assert effects == (["open"] if approval == "conditional" else [])
        if approval == "conditional":
            assert sorted(policies, key=lambda x: x[2]) == [
                ({"owner": "application"}, {"value": "open"}, "free"),
                ({"owner": "application"}, {"value": "review"}, "gated")]
        policies_before_resume = copy.deepcopy(policies)
        state = paused.to_state()
        state.approve(pending_calls(state)["gated"])
        resumed = await execution_run(agent, state)
        assert resumed.final_output == "Completed."
        assert policies == policies_before_resume
        assert sorted(effects) == (["open", "review"] if approval == "conditional" else ["review"])
        assert tool_outputs(model.requests[-1])["gated"] == "recorded:review"

    for decision in ("manual-approve", "manual-reject", True, False):
        effects, decisions = [], []
        async def execute(context, text):
            effects.append(text)
            return text.upper()
        async def decide(context, item):
            decisions.append(item.raw_item.input)
            return {"approve": decision, "reason": "Application refused."}
        operation = CustomTool(name="raw", description="Apply raw input", format={"type": "text"},
            on_invoke_tool=execute, needs_approval=True,
            on_approval=decide if isinstance(decision, bool) else None)
        model = RecordingModel([ResponseCustomToolCall(type="custom_tool_call", name="raw",
                               call_id="raw-call", input="raw application text")], "Finished raw.")
        agent = Agent(name="Raw approval", model=model, tools=[operation])
        result = await execution_run(agent)
        if isinstance(decision, str):
            assert set(pending_calls(result)) == {"raw-call"}
            proposal = pending_calls(result)["raw-call"].raw_item
            assert proposal.name == operation.name
            assert proposal.input == "raw application text"
            assert result.final_output is None and effects == []
            state = result.to_state()
            if decision == "manual-reject":
                state.reject(pending_calls(state)["raw-call"], rejection_message="Application refused.")
            else:
                state.approve(pending_calls(state)["raw-call"])
            result = await execution_run(agent, state)
        else:
            assert decisions == ["raw application text"]
        assert result.final_output == "Finished raw." and not result.interruptions
        assert effects == ([] if decision in (False, "manual-reject") else ["raw application text"])
        assert tool_outputs(model.requests[-1], kind="custom_tool_call_output")["raw-call"] == (
            "Application refused." if decision in (False, "manual-reject") else "RAW APPLICATION TEXT")


@pytest.mark.asyncio
async def test_f08_t02():
    # Uninspectable arguments require manual review without invoking the policy.
    # Approval of ordinary JSON still follows normal invocation validation.
    cases = [("", "default"), ("   ", "invalid"), ("{", "invalid"),
             ("[]", "invalid"), ('{"number":NaN}', "nan"),
             ('{"number":Infinity}', "infinity"), ('{"number":-Infinity}', "negative infinity")]
    for arguments, outcome in cases:
        policies, effects = [], []
        def policy(context, values, call_id):
            policies.append(values)
            return False
        @tool(needs_approval=policy, strict_mode=False, failure_error_function=None)
        def numeric(number: float = 2.5) -> str:
            effects.append(number)
            return "Application executed."
        call = function_call(numeric.name, {}, "numeric")
        call.arguments = arguments
        model = RecordingModel([call], "Finished numeric.")
        agent = Agent(name="Numeric approval", model=model, tools=[numeric])
        paused = await execution_run(agent)
        assert set(pending_calls(paused)) == {"numeric"}
        assert paused.final_output is None and policies == [] and effects == []
        state = paused.to_state()
        if outcome in ("nan", "infinity", "negative infinity"):
            state.reject(pending_calls(state)["numeric"], rejection_message="Application refused.")
            result = await execution_run(agent, state)
            assert result.final_output == "Finished numeric."
            assert tool_outputs(model.requests[-1])["numeric"] == "Application refused."
            assert policies == [] and effects == []
            continue
        state.approve(pending_calls(state)["numeric"])
        if outcome == "invalid":
            with pytest.raises(ModelBehaviorError):
                await execution_run(agent, state)
            assert effects == []
        else:
            result = await execution_run(agent, state)
            assert result.final_output == "Finished numeric."
            assert tool_outputs(model.requests[-1])["numeric"] == "Application executed."
            assert len(effects) == 1
            assert effects == [2.5]
        assert policies == []


@pytest.mark.asyncio
async def test_f08_t03():
    # "exact" is the control: declared arguments needing no preparation are decided by
    # the conditional callback itself, so a manual-only implementation is distinguished.
    for kind in ("exact", "default", "conversion", "extra", "validator", "invalid"):
        policies, validations, effects = [], [], []
        def policy(context, values, call_id):
            policies.append((values, call_id))
            return False
        class ValidatedRequest(BaseModel):
            value: int
            @field_validator("value")
            @classmethod
            def validate_value(cls, value):
                validations.append(value)
                if value < 0:
                    raise ValueError("Value must be nonnegative")
                return value + 10
        if kind in ("validator", "invalid"):
            async def operation(request: ValidatedRequest) -> str:
                effects.append(request.value)
                return str(request.value)
            arguments = {"request": {"value": 3 if kind == "validator" else -3}}
            expected = 13
        else:
            async def operation(value: int = 9) -> str:
                effects.append(value)
                return str(value)
            arguments = {"exact": {"value": 6}, "default": {}, "conversion": {"value": "12"},
                         "extra": {"value": 6, "undeclared": "discard"}}[kind]
            expected = {"exact": 6, "default": 9, "conversion": 12, "extra": 6}[kind]
        operation = tool(operation, strict_mode=False, needs_approval=policy, failure_error_function=None)
        model = RecordingModel([function_call(operation.name, arguments, "declaration")], "Validated.")
        agent = Agent(name="Declaration approval", model=model, tools=[operation])
        paused = await execution_run(agent)
        if kind == "exact":
            assert paused.final_output == "Validated." and not paused.interruptions
            assert policies == [({"value": 6}, "declaration")] and effects == [6]
            assert tool_outputs(model.requests[-1])["declaration"] == "6"
            continue
        assert set(pending_calls(paused)) == {"declaration"}
        assert paused.final_output is None and policies == [] and validations == [] and effects == []
        state = await RunState.from_json(agent, paused.to_state().to_json())
        state.approve(pending_calls(state)["declaration"])
        if kind == "invalid":
            with pytest.raises(ModelBehaviorError):
                await execution_run(agent, state)
            assert effects == [] and validations == [-3]
        else:
            result = await execution_run(agent, state)
            assert result.final_output == "Validated." and effects == [expected]
            assert tool_outputs(model.requests[-1])["declaration"] == str(expected)
            assert validations == ([3] if kind == "validator" else [])
        assert policies == []


@pytest.mark.asyncio
async def test_f08_t04():
    effects = []
    operation = execution_tool(effects, needs_approval=True)
    model = RecordingModel([function_call(operation.name, {"value": value}, value)
                            for value in ("accepted", "refused", "undecided")], "Batch complete.")
    agent = Agent(name="Batch", model=model, tools=[operation])
    config = RunConfig(tracing_disabled=True, tool_error_formatter=lambda data: "Run-wide refusal.")
    paused = await execution_run(agent, config=config)
    assert set(pending_calls(paused)) == {"accepted", "refused", "undecided"}
    state = paused.to_state()
    state.add_input("Supplement accepted by the server.")
    state.approve(pending_calls(state)["accepted"])
    state.reject(pending_calls(state)["refused"], rejection_message="Per-call refusal.")
    partial = await execution_run(agent, state, config=config)
    assert set(pending_calls(partial)) == {"undecided"}
    assert partial.final_output is None and effects == ["accepted"]
    state = partial.to_state()
    state.reject(pending_calls(state)["undecided"])
    result = await execution_run(agent, state, config=config)
    assert result.final_output == "Batch complete." and effects == ["accepted"]
    assert tool_outputs(model.requests[-1]) == {"accepted": "recorded:accepted",
        "refused": "Per-call refusal.", "undecided": "Run-wide refusal."}


@pytest.mark.asyncio
async def test_f08_t05():
    for approved in (True, False):
        effects = []
        operation = execution_tool(effects, needs_approval=True)
        model = RecordingModel([function_call(operation.name, {"value": "first"}, "first")],
            [function_call(operation.name, {"value": "second"}, "second")], "Sticky complete.")
        agent = Agent(name="Owner", model=model, tools=[operation])
        paused = await execution_run(agent, context={"application": "shared"})
        state = paused.to_state()
        item = pending_calls(state)["first"]
        if approved:
            state.approve(item, always_approve=True)
        else:
            state.reject(item, always_reject=True, rejection_message="Persistent refusal.")
        state = await RunState.from_json(agent, state.to_json())
        config = RunConfig(tracing_disabled=True, tool_error_formatter=lambda data: "Persistent refusal.")
        result = await execution_run(agent, state, config=config)
        assert result.final_output == "Sticky complete." and not result.interruptions
        assert effects == (["first", "second"] if approved else [])
        assert tool_outputs(model.requests[-1])["second"] == (
            "recorded:second" if approved else "Persistent refusal.")
        for index, (context, owner, should_pause) in enumerate((
            (result.context_wrapper, agent, False),
            (result.context_wrapper, Agent(name=agent.name, tools=[operation]), True),
            (result.context_wrapper.context, agent, True),
        )):
            call_id = f"later-{index}"
            fresh_model = RecordingModel([function_call(operation.name, {"value": "later"}, call_id)],
                                         "Later complete.")
            owner.model = fresh_model
            before = list(effects)
            later = await execution_run(owner, context=context, config=config)
            if should_pause:
                assert set(pending_calls(later)) == {call_id}
                assert later.final_output is None and effects == before
            else:
                assert later.final_output == "Later complete." and not later.interruptions
                assert effects == before + (["later"] if approved else [])
                assert tool_outputs(fresh_model.requests[-1])[call_id] == (
                    "recorded:later" if approved else "Persistent refusal.")
        # The decision belongs to that function tool: a different approval-requiring
        # tool on the same agent still pauses under the approval-bearing context.
        sibling_effects = []
        sibling = execution_tool(sibling_effects, name="sibling", needs_approval=True)
        agent.tools = [operation, sibling]
        agent.model = RecordingModel([function_call(sibling.name, {"value": "sibling"}, "sibling-call")],
                                     "Sibling complete.")
        later = await execution_run(agent, context=result.context_wrapper, config=config)
        assert set(pending_calls(later)) == {"sibling-call"}
        assert later.final_output is None and sibling_effects == []


@pytest.mark.asyncio
async def test_f08_t06():
    agent, model, effects, paused = await checkpoint_scenario(context={"tenant": "snapshot"})
    before_history = copy.deepcopy(paused.to_input_list())
    first, second = paused.to_state(), paused.to_state()
    first.approve(pending_calls(first)["pending"])
    result = await execution_run(agent, first)
    assert result.final_output == "Continued." and result.last_agent is agent
    assert effects == ["captured"]
    assert result.to_input_list()[:len(before_history)] == before_history
    assert (result.context_wrapper.usage.requests, result.context_wrapper.usage.input_tokens,
            result.context_wrapper.usage.output_tokens, result.context_wrapper.usage.total_tokens) == (2, 28, 8, 36)
    assert paused.final_output is None and paused.to_input_list() == before_history
    assert paused.context_wrapper.usage.total_tokens == 14
    untouched = await execution_run(agent, second)
    assert set(pending_calls(untouched)) == {"pending"} and untouched.final_output is None
    assert untouched.to_input_list() == before_history and effects == ["captured"]
    assert untouched.context_wrapper.usage.total_tokens == 14
    # Continuing a completed checkpoint starts a new model turn from its captured history.
    completed_a, completed_b = result.to_state(), result.to_state()
    completed_a.clear_pending_input()
    model.outputs.extend(["Continuation A.", "Continuation B."])
    model.usages.extend([Usage(requests=1, input_tokens=2, output_tokens=1, total_tokens=3),
                         Usage(requests=1, input_tokens=2, output_tokens=1, total_tokens=3)])
    for checkpoint, answer in ((completed_a, "Continuation A."), (completed_b, "Continuation B.")):
        restored = await execution_run(agent, checkpoint)
        assert restored.final_output == answer and restored.last_agent is agent
        assert restored.to_input_list()[:len(result.to_input_list())] == result.to_input_list()
        assert restored.context_wrapper.usage.total_tokens == 39
    assert result.final_output == "Continued." and result.context_wrapper.usage.total_tokens == 36
    assert effects == ["captured"] and len(model.requests) == 4
    # The active agent is checkpoint data: after a handoff, resuming from the starting
    # agent (in memory or restored) continues with the agent that owned the pause.
    for restore in (False, True):
        owner, router, owner_model, routed_effects, routed = await routed_checkpoint_scenario()
        state = routed.to_state()
        if restore:
            state = await RunState.from_json(router, state.to_json())
        state.approve(pending_calls(state)["pending"])
        resumed = await execution_run(router, state)
        assert resumed.final_output == "Continued." and resumed.last_agent is owner
        assert routed_effects == ["captured"] and len(owner_model.requests) == 2
        assert len(router.model.requests) == 1
        assert tool_outputs(owner_model.requests[-1])["pending"] == "recorded:captured"


@pytest.mark.asyncio
async def test_f08_t07():
    source = '''import asyncio, json, sys
sys.path.insert(0, sys.argv[1])
from F08_helpers import checkpoint_process
print(json.dumps(asyncio.run(checkpoint_process(sys.argv[2], json.load(sys.stdin)))))
'''
    helper_path = str(Path(__file__).parent)
    capture = run_python(source, args=(helper_path, "capture"), input=b"{}")
    assert capture.returncode == 0, capture.stderr.decode()
    payload = json.loads(capture.stdout)
    assert payload["effects"] == ["before"]
    restore = run_python(source, args=(helper_path, "restore"), input=capture.stdout)
    assert restore.returncode == 0, restore.stderr.decode()
    observed = json.loads(restore.stdout)
    assert observed["effects"] == ["after"] and observed["output"] == "Restored."
    assert observed["agent"] == "Durable owner" and observed["context"] == {"tenant": "retained"}
    assert observed["usage"] == {"requests": 3, "input_tokens": 39, "output_tokens": 12, "total_tokens": 51}
    assert observed["history"][:len(payload["history"])] == payload["history"]
    assert tool_outputs({"input": observed["request"]}) == {
        "completed-call": "recorded:before", "pending-call": "recorded:after"}

    agent, _, _, paused = await checkpoint_scenario(context=ApprovalContext("custom"))
    state = paused.to_state()
    with pytest.raises(UserError):
        state.to_json(strict_context=True)
    encoded = state.to_json(strict_context=True, context_serializer=lambda value: {"tenant": value.tenant})
    with pytest.raises(UserError):
        await RunState.from_json(agent, encoded, strict_context=True)
    for options in ({"context_override": ApprovalContext("replacement")},
                    {"context_deserializer": lambda data: ApprovalContext(data["tenant"])}):
        restored = await RunState.from_json(agent, encoded, strict_context=True, **options)
        waiting = await execution_run(agent, restored)
        assert waiting.context_wrapper.context.tenant == ("replacement" if "context_override" in options else "custom")
        assert set(pending_calls(waiting)) == {"pending"}
    for context in (None, {"tenant": "direct", "permissions": ["read", "write"]}):
        direct_agent, _, direct_effects, direct_paused = await checkpoint_scenario(context=context)
        direct_encoded = direct_paused.to_state().to_json(strict_context=True)
        direct_state = await RunState.from_json(direct_agent, direct_encoded, strict_context=True)
        direct_waiting = await execution_run(direct_agent, direct_state)
        assert direct_waiting.context_wrapper.context == context
        assert set(pending_calls(direct_waiting)) == {"pending"}
        assert direct_waiting.final_output is None and direct_effects == []
    with pytest.raises(UserError):
        await RunState.from_json(Agent(name="Unbound owner"), encoded, context_override={})
    incompatible = copy.deepcopy(encoded)
    incompatible["$schemaVersion"] = "999.0"
    with pytest.raises(UserError):
        await RunState.from_json(agent, incompatible, context_override={})


@pytest.mark.asyncio
async def test_f08_t08():
    for stopped in (False, True):
        agent, model, effects, paused = await checkpoint_scenario()
        state = paused.to_state()
        if stopped:
            state.approve(pending_calls(state)["pending"])
            stream = Runner.run_streamed(agent, state, run_config=RunConfig(tracing_disabled=True))
            async def stop_after_tool():
                async for event in stream.stream_events():
                    if event.type == "run_item_stream_event" and event.name == "tool_output":
                        stream.cancel(mode="after_turn")
            await bounded(stop_after_tool())
            assert effects == ["captured"]
            state = stream.to_state()
        additions = [{"role": "user", "content": "First supplement."},
                     {"role": "user", "content": "Second supplement."}]
        state.add_input(additions[0]["content"])
        state.add_input([additions[1]])
        assert state.pending_input == additions
        state = await RunState.from_json(agent, state.to_json())
        assert state.pending_input == additions
        if not stopped:
            waiting = await execution_run(agent, state)
            assert set(pending_calls(waiting)) == {"pending"} and waiting.final_output is None
            assert state.pending_input == additions and effects == []
            state.approve(pending_calls(state)["pending"])
        seen = []
        def inspect(label, trip):
            def guard(context, current, input):
                seen.append((label, current.name, copy.deepcopy(input)))
                return GuardrailFunctionOutput(output_info=label, tripwire_triggered=trip)
            return InputGuardrail(guardrail_function=guard, run_in_parallel=False)
        agent.input_guardrails = [inspect("agent", False)]
        config = RunConfig(tracing_disabled=True, input_guardrails=[inspect("run", True)])
        with pytest.raises(InputGuardrailTripwireTriggered):
            await execution_run(agent, state, config=config)
        assert "run" in {row[0] for row in seen}
        assert {row[0] for row in seen} <= {"agent", "run"}
        assert all(row[1:] == (agent.name, additions) for row in seen)
        assert state.pending_input == additions and len(model.requests) == 1
        seen.clear()
        agent.input_guardrails = [inspect("agent", True)]
        config.input_guardrails = [inspect("run", False)]
        with pytest.raises(InputGuardrailTripwireTriggered):
            await execution_run(agent, state, config=config)
        assert "agent" in {row[0] for row in seen}
        assert all(row[1:] == (agent.name, additions) for row in seen)
        assert state.pending_input == additions and len(model.requests) == 1
        seen.clear()
        agent.input_guardrails = [inspect("agent", False)]
        result = await execution_run(agent, state, config=config)
        assert result.final_output == "Continued." and result.last_agent is agent
        assert state.pending_input == [] and effects == ["captured"]
        assert model.requests[-1]["input"][-2:] == additions
        assert {row[0] for row in seen} == {"agent", "run"}
    # After a handoff, the agent owning the paused run checks staged input, not the
    # agent the run (and its resume call) started from.
    owner, router, owner_model, routed_effects, routed = await routed_checkpoint_scenario()
    state = routed.to_state()
    state.add_input("Routed supplement.")
    state = await RunState.from_json(router, state.to_json())
    state.approve(pending_calls(state)["pending"])
    seen = []
    def routed_guard(label, trip):
        def guard(context, current, input):
            seen.append((label, current.name, copy.deepcopy(input)))
            return GuardrailFunctionOutput(output_info=label, tripwire_triggered=trip)
        return InputGuardrail(guardrail_function=guard, run_in_parallel=False)
    router.input_guardrails = [routed_guard("router", True)]
    owner.input_guardrails = [routed_guard("owner", False)]
    result = await execution_run(router, state)
    assert result.final_output == "Continued." and result.last_agent is owner
    assert seen == [("owner", owner.name, [{"role": "user", "content": "Routed supplement."}])]
    assert routed_effects == ["captured"]
    assert owner_model.requests[-1]["input"][-1] == {"role": "user", "content": "Routed supplement."}


@pytest.mark.asyncio
async def test_f08_t09():
    agent, _, _, paused = await checkpoint_scenario()
    state = paused.to_state()
    state.add_input("Allowed supplement.")
    assert state.pending_input == [{"role": "user", "content": "Allowed supplement."}]
    state.clear_pending_input()
    assert state.pending_input == []
    # Boundary: one model turn remains, so staged input is still admitted and used.
    last_agent, last_model, last_effects, last_paused = await checkpoint_scenario(max_turns=2)
    last_state = last_paused.to_state()
    last_state.add_input("Last-turn supplement.")
    assert last_state.pending_input == [{"role": "user", "content": "Last-turn supplement."}]
    last_state.approve(pending_calls(last_state)["pending"])
    last_result = await execution_run(last_agent, last_state, max_turns=2)
    assert last_result.final_output == "Continued." and last_effects == ["captured"]
    assert last_model.requests[-1]["input"][-1] == {"role": "user", "content": "Last-turn supplement."}
    states = []
    completed = await execution_run(Agent(name="Terminal", model=RecordingModel("Done.")))
    states.append(completed.to_state())
    exhausted = await checkpoint_scenario(max_turns=1)
    states.append(exhausted[-1].to_state())
    terminal_tool = await checkpoint_scenario(terminal=True)
    states.append(terminal_tool[-1].to_state())
    # A pending call to a tool named as a stopping tool is also potentially terminal,
    # while naming a different tool leaves the paused run continuable.
    for stop_names, terminal in ((["record"], True), (["unrelated"], False)):
        named = (await checkpoint_scenario(tool_use_behavior={"stop_at_tool_names": stop_names}))[-1].to_state()
        if terminal:
            states.append(named)
        else:
            named.add_input("Continuable supplement.")
            assert named.pending_input == [{"role": "user", "content": "Continuable supplement."}]
    # A public end-of-response hook failure retains an accepted response awaiting
    # local processing; obtaining this state never edits private checkpoint flags.
    hook_error = RuntimeError("Application response hook failed")
    class FailAfterResponse(RunHooks):
        async def on_llm_end(self, context, agent, response):
            raise hook_error
    accepted_tool = execution_tool([], needs_approval=True)
    accepted_model = IdentifiedResponseModel([function_call(accepted_tool.name, {"value": "accepted"}, "accepted")],
                                    "Accepted final.")
    agent = Agent(name="Accepted response", tools=[accepted_tool], model=accepted_model)
    paused = await execution_run(agent, auto_previous_response_id=True)
    state = paused.to_state()
    state.add_input("Supplement accepted by the server.")
    state.approve(pending_calls(state)["accepted"])
    with pytest.raises(RuntimeError) as error:
        await execution_run(agent, state, hooks=FailAfterResponse(), auto_previous_response_id=True)
    assert error.value is hook_error
    states.append(state)
    for index, rejected in enumerate(states):
        before = rejected.pending_input
        try:
            rejected.add_input("Incompatible supplement.")
        except UserError:
            assert rejected.pending_input == before
        else:
            pytest.fail(f"Incompatible checkpoint {index} accepted staged input")


@pytest.mark.asyncio
async def test_f08_t10(tmp_path):
    for failure in ("before", "after"):
        session = InterruptedWriteSession(failure, tmp_path / (failure + ".db"))
        try:
            agent, model, effects, paused = await checkpoint_scenario(session=session)
            state = paused.to_state()
            state.approve(pending_calls(state)["pending"])
            session.failure = failure
            with pytest.raises(RuntimeError) as error:
                await execution_run(agent, state, session=session)
            assert error.value is session.error and effects == ["captured"]
            assert session.failed_items
            state = await RunState.from_json(agent, state.to_json())
            result = await execution_run(agent, state, session=session)
            assert result.final_output == "Continued." and effects == ["captured"]
            history = await session.get_items()
            assert history == result.to_input_list()
            calls = [item for item in history if item.get("type") == "function_call"]
            outputs = [item for item in history if item.get("type") == "function_call_output"]
            assert [item["call_id"] for item in calls] == ["pending"]
            assert [(item["call_id"], item["output"]) for item in outputs] == [("pending", "recorded:captured")]
        finally:
            session.close()


@pytest.mark.asyncio
async def test_f08_t11(tmp_path):
    for corruption in ("partial", "conflicting", "terminal"):
        session = InterruptedWriteSession(corruption, tmp_path / (corruption + ".db"))
        try:
            agent, _, effects, paused = await checkpoint_scenario(session=session, terminal=corruption == "terminal",
                values=("captured",) if corruption == "terminal" else ("captured", "sibling"))
            state = paused.to_state()
            for item in pending_calls(state).values():
                state.approve(item)
            expected_effects = ["captured"] if corruption == "terminal" else ["captured", "sibling"]
            session.failure = "before"
            with pytest.raises(RuntimeError) as error:
                await execution_run(agent, state, session=session)
            assert error.value is session.error and sorted(effects) == expected_effects
            if corruption != "terminal":
                batch = copy.deepcopy(session.failed_items)
                assert len(batch) >= 2
                await session.store.add_items(batch[:1] if corruption == "partial" else
                                             [{"role": "user", "content": "Conflicting history."}])
            before = await session.get_items()
            with pytest.raises(UserError):
                restored = await RunState.from_json(agent, state.to_json())
                await execution_run(agent, restored, session=session)
            assert await session.get_items() == before and sorted(effects) == expected_effects
        finally:
            session.close()
