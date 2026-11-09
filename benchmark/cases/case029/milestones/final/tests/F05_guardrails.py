# feature: F05
"""Acceptance checks for run and function-tool guardrail decisions."""
import asyncio
import json

import pytest

from F01_helpers import RecordingModel, function_call
from F03_helpers import tool_outputs
from F04_helpers import conversation_text, execution_run, execution_tool
from F05_helpers import ApprovalBoundaryModel
from _helpers import bounded
from velmora import (
    Agent, GuardrailFunctionOutput, InputGuardrail, InputGuardrailTripwireTriggered,
    OutputGuardrail, OutputGuardrailTripwireTriggered, RunConfig, handoff,
)
from velmora import ToolGuardrailFunctionOutput, ToolInputGuardrail, ToolOutputGuardrail
from velmora import ToolInputGuardrailTripwireTriggered, ToolOutputGuardrailTripwireTriggered


@pytest.mark.asyncio
async def test_f05_t01():
    for rejected in (None, "initial", "global"):
        seen = []

        def check(label):
            def callback(context, agent, value):
                seen.append((label, agent, value))
                return GuardrailFunctionOutput({"check": label}, label == rejected)
            return InputGuardrail(guardrail_function=callback, name=label, run_in_parallel=False)

        initial, global_check, later = check("initial"), check("global"), check("later")
        target = Agent(name="Destination", model=RecordingModel("Arrived."),
                       input_guardrails=[later])
        transfer = handoff(target)
        model = RecordingModel([function_call(transfer.tool_name, {}, "transfer")])
        start = Agent(name="Start", model=model, handoffs=[transfer], input_guardrails=[initial])
        config = RunConfig(tracing_disabled=True, input_guardrails=[global_check])
        if rejected is None:
            result = await execution_run(start, "Inspect initial input.", config=config)
            assert result.final_output == "Arrived."
            assert {r.guardrail.get_name(): r.output.output_info for r in result.input_guardrail_results} == {
                "initial": {"check": "initial"}, "global": {"check": "global"}}
            assert sorted(label for label, _, _ in seen) == ["global", "initial"]
            assert all(agent is start and value == "Inspect initial input." for _, agent, value in seen)
        else:
            with pytest.raises(InputGuardrailTripwireTriggered) as caught:
                await execution_run(start, "Inspect initial input.", config=config)
            verdict = caught.value.guardrail_result
            assert verdict.guardrail is (initial if rejected == "initial" else global_check)
            assert verdict.output.tripwire_triggered is True
            assert verdict.output.output_info == {"check": rejected}


@pytest.mark.asyncio
async def test_f05_t02():
    # The application event is an actual tool effect, not a guardrail-start signal.
    for policy, reject in ((False, False), (False, True), (None, True)):
        effects = []
        applied, entered, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        approved = False
        tool = execution_tool(effects)
        application = tool.on_invoke_tool

        async def apply(context, arguments):
            if policy is False:
                assert approved, "Application ran before blocking approval."
            value = await application(context, arguments)
            applied.set()
            return value

        tool.on_invoke_tool = apply
        model = ApprovalBoundaryModel(
            lambda: approved if policy is False else True,
            [function_call(tool.name, {"value": "effect"}, "effect-call")], "Done.")

        async def check(context, agent, value):
            nonlocal approved
            entered.set()
            if policy is None:
                await bounded(applied.wait())
            else:
                await bounded(release.wait())
            approved = not reject
            return GuardrailFunctionOutput("approval-decision", reject)

        options = {} if policy is None else {"run_in_parallel": policy}
        guard = InputGuardrail(guardrail_function=check, **options)
        agent = Agent(name="Worker", model=model, tools=[tool], input_guardrails=[guard])
        task = asyncio.create_task(execution_run(agent))
        try:
            await bounded(entered.wait())
            if policy is False:
                # Give independently runnable agent work an opportunity to reach the
                # model boundary while the approval event remains closed. The verdict
                # checks approval at each actual request, not elapsed execution speed.
                await asyncio.sleep(0.05)
                assert model.requests == []
                assert effects == []
                release.set()
            if reject:
                with pytest.raises(InputGuardrailTripwireTriggered) as caught:
                    await bounded(task)
                assert caught.value.guardrail_result.guardrail is guard
                assert caught.value.guardrail_result.output.tripwire_triggered is True
            else:
                assert (await bounded(task)).final_output == "Done."
            assert effects == ([] if policy is False and reject else ["effect"])
            if policy is False and reject:
                assert model.requests == []
        finally:
            release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_f05_t03():
    for mode in ("allow", "reject", "global-reject", "callback-error"):
        seen = []
        failure = LookupError("Application check failed.")

        def final_check(context, agent, value):
            seen.append(("final", agent, value))
            if mode == "callback-error":
                raise failure
            return GuardrailFunctionOutput({"review": "final"}, mode == "reject")

        def global_check(context, agent, value):
            seen.append(("global", agent, value))
            return GuardrailFunctionOutput({"review": "global"}, mode == "global-reject")

        guard = OutputGuardrail(guardrail_function=final_check, name="final-review")
        global_guard = OutputGuardrail(guardrail_function=global_check, name="global-review")
        target = Agent(name="Finisher", model=RecordingModel("Reviewed answer."), output_guardrails=[guard])
        transfer = handoff(target)

        def wrong_check(*args):
            raise AssertionError("Starting agent must not review the finishing agent's answer.")

        start = Agent(name="Start", model=RecordingModel([function_call(transfer.tool_name, {}, "handoff")]),
                      handoffs=[transfer], output_guardrails=[OutputGuardrail(guardrail_function=wrong_check)])
        config = RunConfig(tracing_disabled=True, output_guardrails=[global_guard])
        if mode == "allow":
            result = await execution_run(start, config=config)
            assert result.final_output == "Reviewed answer."
            results = {r.guardrail.get_name(): r for r in result.output_guardrail_results}
            assert set(results) == {"final-review", "global-review"}
            for label, result_item in results.items():
                assert result_item.agent is target
                assert result_item.agent_output == "Reviewed answer."
                assert result_item.output.tripwire_triggered is False
                assert result_item.output.output_info == {"review": "final" if label == "final-review" else "global"}
            assert sorted(label for label, _, _ in seen) == ["final", "global"]
        elif mode in ("reject", "global-reject"):
            with pytest.raises(OutputGuardrailTripwireTriggered) as caught:
                await execution_run(start, config=config)
            verdict = caught.value.guardrail_result
            assert verdict.guardrail is (guard if mode == "reject" else global_guard)
            assert verdict.output.tripwire_triggered is True
            assert verdict.output.output_info == {"review": "final" if mode == "reject" else "global"}
        else:
            with pytest.raises(LookupError) as caught:
                await execution_run(start, config=config)
            assert caught.value is failure
        assert all(agent is target and value == "Reviewed answer." for _, agent, value in seen)


@pytest.mark.asyncio
async def test_f05_t04():
    for mode in ("allow", "replace", "stop"):
        effects, seen = [], []
        tool = execution_tool(effects)

        def check(data):
            seen.append(json.loads(data.context.tool_arguments))
            if mode == "allow":
                return ToolGuardrailFunctionOutput.allow("input-audit")
            if mode == "replace":
                return ToolGuardrailFunctionOutput.reject_content("Input withheld.", "input-audit")
            return ToolGuardrailFunctionOutput.raise_exception("input-audit")

        guard = ToolInputGuardrail(check, name="tool-input-review")
        tool.tool_input_guardrails = [guard]
        model = RecordingModel([function_call(tool.name, {"value": "requested"}, "guarded")], "Continued.")
        agent = Agent(name="Worker", model=model, tools=[tool])
        if mode == "stop":
            with pytest.raises(ToolInputGuardrailTripwireTriggered) as caught:
                await execution_run(agent)
            assert caught.value.guardrail is guard
            assert caught.value.output.output_info == "input-audit"
            assert len(model.requests) == 1
        else:
            result = await execution_run(agent)
            assert result.final_output == "Continued."
            assert tool_outputs(model.requests[1]) == {
                "guarded": "recorded:requested" if mode == "allow" else "Input withheld."}
        assert seen == [{"value": "requested"}]
        assert effects == (["requested"] if mode == "allow" else [])


@pytest.mark.asyncio
async def test_f05_t05():
    for mode in ("allow", "replace", "stop"):
        effects, seen = [], []
        tool = execution_tool(effects)

        def check(data):
            seen.append(data.output)
            if mode == "allow":
                return ToolGuardrailFunctionOutput.allow("output-audit")
            if mode == "replace":
                return ToolGuardrailFunctionOutput.reject_content("Output withheld.", "output-audit")
            return ToolGuardrailFunctionOutput.raise_exception("output-audit")

        guard = ToolOutputGuardrail(check, name="tool-output-review")
        tool.tool_output_guardrails = [guard]
        model = RecordingModel([function_call(tool.name, {"value": "produced"}, "guarded")], "Continued.")
        agent = Agent(name="Worker", model=model, tools=[tool])
        if mode == "stop":
            with pytest.raises(ToolOutputGuardrailTripwireTriggered) as caught:
                await execution_run(agent)
            assert caught.value.guardrail is guard
            assert caught.value.output.output_info == "output-audit"
            assert len(model.requests) == 1
        else:
            result = await execution_run(agent)
            assert result.final_output == "Continued."
            assert tool_outputs(model.requests[1]) == {
                "guarded": "recorded:produced" if mode == "allow" else "Output withheld."}
        assert effects == ["produced"]
        assert seen == ["recorded:produced"]


@pytest.mark.asyncio
async def test_f05_t06():
    effects = []
    accepted = execution_tool(effects, name="accepted")
    terminal = execution_tool(effects, name="terminal")
    payload = "recorded:unaccepted-payload"

    def audit(data):
        return ToolGuardrailFunctionOutput.allow({"copy": data.output})

    terminal.tool_output_guardrails = [ToolOutputGuardrail(audit)]
    model = RecordingModel([function_call(accepted.name, {"value": "earlier"}, "prior")], "Accepted answer.")
    agent = Agent(name="Worker", model=model, tools=[accepted, terminal])
    first = await execution_run(agent)
    assert first.final_output == "Accepted answer."
    state = first.to_state()
    agent.tool_use_behavior = {"stop_at_tool_names": [terminal.name]}

    def reject(context, current, value):
        assert value == payload
        return GuardrailFunctionOutput({"copy": value}, True)

    guard = OutputGuardrail(guardrail_function=reject)
    agent.output_guardrails = [guard]
    model.outputs.append([function_call(terminal.name, {"value": "unaccepted-payload"}, "terminal-call")])
    with pytest.raises(OutputGuardrailTripwireTriggered) as caught:
        await execution_run(agent, state)
    error = caught.value
    assert error.guardrail_result.guardrail is guard
    assert error.guardrail_result.output.tripwire_triggered is True
    assert effects == ["earlier", "unaccepted-payload"]
    assert payload not in json.dumps(state.to_json())
    assert "recorded:earlier" in json.dumps(state.to_json())
    assert "Accepted answer." in json.dumps(state.to_json())
    assert payload not in json.dumps(error.guardrail_result.agent_output)
    assert payload not in json.dumps(error.guardrail_result.output.output_info)
    # Replaying the retained checkpoint must deliver the accepted earlier result.
    agent.output_guardrails = []
    agent.tool_use_behavior = "run_llm_again"
    model.outputs.append("Recovered.")
    recovered = await execution_run(agent, state)
    assert recovered.final_output == "Recovered."
    assert tool_outputs(model.requests[-1])["prior"] == "recorded:earlier"
    assert conversation_text(model.requests[-1]["input"]) == ["Accepted answer."]
    assert payload not in json.dumps(model.requests[-1]["input"])
