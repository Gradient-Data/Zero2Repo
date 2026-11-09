# feature: F10
"""Acceptance tests for incremental delivery, interruptions and cancellation."""
import asyncio

import pytest
from F01_helpers import function_call, text_message
from F04_helpers import execution_tool, conversation_text
from F07_helpers import ApplicationSession
from F08_helpers import pending_calls
from F10_helpers import BoundaryStreamModel, DeliveredFailureModel, CooperativeWork, start_stream, stream_completion, stream_delta
from _helpers import Observation, consume
from velmora import (Agent, GuardrailFunctionOutput, OutputGuardrailTripwireTriggered,
                    output_guardrail, handoff, UserError)
from openai.types.responses import ResponseReasoningItem


@pytest.mark.asyncio
async def test_f10_t01():
    effects = []
    tool = execution_tool(effects)
    first_gate, last_gate = asyncio.Event(), asyncio.Event()
    model = BoundaryStreamModel(
        [text_message("Starting work."), ResponseReasoningItem(id="reason", type="reasoning", summary=[]),
         function_call(tool.name, {"value": "incremental"}, "work")],
        [], "Delivered answer.", gates={1: first_gate, 3: last_gate})
    delegate = Agent(name="Delegate", model=model)
    transfer = handoff(delegate)
    model.actions[1] = [function_call(transfer.tool_name, {}, "transfer")]
    agent = Agent(name="Origin", model=model, tools=[tool], handoffs=[transfer])
    result = start_stream(agent)
    seen = []
    delivered_text = []

    async def observe():
        async for event in result.stream_events():
            seen.append(event)
            if event.type == "raw_response_event" and event.data.type == "response.output_text.delta":
                assert not result.is_complete
                delivered_text.append(event.data.delta)
                text = "".join(delivered_text)
                if text == "Starting work.":
                    first_gate.set()
                elif text == "Starting work.Delivered answer.":
                    names = {e.name for e in seen if e.type == "run_item_stream_event"}
                    assert {"reasoning_item_created", "tool_called", "tool_output",
                            "handoff_requested", "handoff_occured"} <= names
                    last_gate.set()
    await asyncio.wait_for(observe(), 10)
    assert first_gate.is_set() and last_gate.is_set()
    assert "".join(delivered_text) == "Starting work.Delivered answer."
    updates = [e.new_agent for e in seen if e.type == "agent_updated_stream_event"]
    assert agent in updates and delegate in updates
    items = [e for e in seen if e.type == "run_item_stream_event"]
    call = next(e.item for e in items if e.name == "tool_called")
    output = next(e.item for e in items if e.name == "tool_output")
    assert call.raw_item.call_id == output.raw_item["call_id"] == "work"
    assert output.raw_item["output"] == "recorded:incremental"
    assert call.agent is agent and output.agent is agent
    requested = next(e.item for e in items if e.name == "handoff_requested")
    transferred = next(e.item for e in items if e.name == "handoff_occured")
    assert requested.raw_item.call_id == transferred.raw_item["call_id"] == "transfer"
    assert transferred.source_agent is agent and transferred.target_agent is delegate
    reasoning = next(e.item for e in items if e.name == "reasoning_item_created")
    assert reasoning.raw_item.id == "reason"
    assert reasoning.agent is agent
    initial_message = next(e.item for e in items
                           if e.name == "message_output_created" and e.item.agent is agent)
    assert initial_message.raw_item.content[0].text == "Starting work."
    message = next(e.item for e in items if e.name == "message_output_created" and e.item.agent is delegate)
    assert message.raw_item.content[0].text == "Delivered answer."
    assert effects == ["incremental"]
    assert result.is_complete and result.final_output == "Delivered answer."
    assert result.last_agent is delegate


@pytest.mark.asyncio
async def test_f10_t02():
    effects = []
    done = execution_tool(effects, name="completed")
    pending = execution_tool(effects, needs_approval=True)
    model = BoundaryStreamModel(
        [function_call(done.name, {"value": "before"}, "done")],
        [function_call(pending.name, {"value": "approved"}, "approval")], "Resumed answer.")
    agent = Agent(name="Approval", model=model, tools=[done, pending])
    result = start_stream(agent)
    await consume(result.stream_events(), timeout=10)
    assert result.is_complete and result.final_output is None
    assert set(pending_calls(result)) == {"approval"}
    assert effects == ["before"]
    state = result.to_state()
    state.approve(pending_calls(state)["approval"])
    resumed = start_stream(agent, state)
    events = await consume(resumed.stream_events(), timeout=10)
    assert resumed.is_complete and resumed.interruptions == []
    assert resumed.final_output == "Resumed answer."
    assert effects == ["before", "approved"]
    assert len(model.requests) == 3
    outputs = [e.item.raw_item for e in events
               if e.type == "run_item_stream_event" and e.name == "tool_output"]
    assert [(i["call_id"], i["output"]) for i in outputs] == [("approval", "recorded:approved")]


@pytest.mark.asyncio
async def test_f10_t03():
    for cancel in (False, True):
        work = CooperativeWork()
        model = BoundaryStreamModel([function_call(work.tool.name, {}, "cooperative")], "Finished.")
        agent = Agent(name="Cancellation", model=model, tools=[work.tool])
        result = start_stream(agent)
        consumer = asyncio.create_task(consume(result.stream_events(), timeout=10))
        await asyncio.wait_for(work.entered.wait(), 5)
        assert work.effects == ["before"]
        if cancel:
            result.cancel()
            await consumer
            await asyncio.wait_for(work.stopped.wait(), 5)
            assert result.is_complete and result.final_output is None
            assert work.effects == ["before"]
            assert len(model.requests) == 1
        else:
            work.release.set()
            await consumer
            assert result.is_complete and result.final_output == "Finished."
            assert work.effects == ["before", "after"]
            assert len(model.requests) == 2


@pytest.mark.asyncio
async def test_f10_t04(tmp_path):
    work = CooperativeWork()
    model = BoundaryStreamModel([function_call(work.tool.name, {}, "retained")], "Continued answer.")
    agent = Agent(name="After turn", model=model, tools=[work.tool])
    session = ApplicationSession("after-turn", tmp_path / "turn.db")
    try:
        result = start_stream(agent, session=session)
        consumer = asyncio.create_task(consume(result.stream_events(), timeout=10))
        await asyncio.wait_for(work.entered.wait(), 5)
        result.cancel(mode="after_turn")
        work.release.set()
        events = await consumer
        assert result.is_complete and result.final_output is None
        assert work.effects == ["before", "after"]
        assert len(model.requests) == 1
        assert any(e.type == "run_item_stream_event" and e.name == "tool_output"
                   and e.item.raw_item["call_id"] == "retained"
                   and e.item.raw_item["output"] == "work completed" for e in events)
        history = result.to_input_list()
        assert any(i.get("type") == "function_call_output" and i["call_id"] == "retained"
                   and i["output"] == "work completed" for i in history)
        assert await session.get_items() == history
        resumed = start_stream(agent, result.to_state(), session=session)
        await consume(resumed.stream_events(), timeout=10)
        assert resumed.is_complete and resumed.final_output == "Continued answer."
        assert model.requests[1]["input"] == history
        assert work.effects == ["before", "after"]
    finally:
        session.close()


@pytest.mark.asyncio
async def test_f10_t05(tmp_path):
    for boundary in ("model", "guardrail", "tool", "persistence"):
        error = RuntimeError(f"Application {boundary} failure")
        tools, guardrails = [], []
        session = None
        if boundary == "model":
            model = DeliveredFailureModel([stream_delta("partial evidence"), error])
        elif boundary == "tool":
            async def fail(context, arguments):
                raise error
            tool = execution_tool([], name="fail")
            tool.on_invoke_tool = fail
            tools = [tool]
            model = DeliveredFailureModel([stream_delta("partial evidence"),
                stream_completion(function_call(tool.name, {"value": "attempt"}, "failed-call"))])
        else:
            model = DeliveredFailureModel([stream_delta("partial evidence"), stream_completion(text_message("Candidate."))])
            if boundary == "guardrail":
                @output_guardrail
                async def reject(context, agent, output):
                    return GuardrailFunctionOutput(output_info="rejected", tripwire_triggered=True)
                guardrails = [reject]
            else:
                session = ApplicationSession("failure", tmp_path / "failure.db")
                def fail_output_write():
                    session.write_error = error
                    return [stream_delta("partial evidence"), stream_completion(text_message("Candidate."))]
                model = DeliveredFailureModel(fail_output_write)
        agent = Agent(name="Failure", model=model, tools=tools, output_guardrails=guardrails)
        result = start_stream(agent, session=session)
        observation = Observation()
        try:
            expected = {"guardrail": OutputGuardrailTripwireTriggered, "tool": UserError}.get(boundary, RuntimeError)
            async def delivered_events():
                async for event in result.stream_events():
                    if event.type == "raw_response_event" and event.data.type == "response.output_text.delta":
                        model.delivered.set()
                    yield event
            with pytest.raises(expected) as caught:
                await consume(delivered_events(), timeout=10, observation=observation)
            if boundary == "tool":
                assert caught.value.__cause__ is error
            elif boundary != "guardrail":
                assert caught.value is error, boundary
            assert any(e.type == "raw_response_event" and e.data.type == "response.output_text.delta"
                       and e.data.delta == "partial evidence" for e in observation.items), boundary
            # The failed run does not settle into an accepted final answer.
            assert result.final_output is None, boundary
            if session is not None:
                assert conversation_text(session.failed_items) == ["Candidate."]
                assert await session.get_items() == [{"role": "user", "content": "Proceed."}]
        finally:
            if session is not None:
                session.close()
