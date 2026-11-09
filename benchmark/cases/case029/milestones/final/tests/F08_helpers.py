# feature: F08
"""Application checkpoint scenarios and public-boundary failure injection."""
import copy
from dataclasses import dataclass

from F01_helpers import RecordingModel, function_call
from F04_helpers import execution_tool, execution_run
from F06_helpers import UsageModel
from F07_helpers import ApplicationSession
from velmora import Agent, GuardrailFunctionOutput, RunState, Usage, handoff, output_guardrail


def pending_calls(result_or_state):
    items = (result_or_state.get_interruptions() if isinstance(result_or_state, RunState)
             else result_or_state.interruptions)
    return {(item.raw_item["call_id"] if isinstance(item.raw_item, dict)
             else item.raw_item.call_id): item for item in items}


@output_guardrail
async def accept_answer(context, agent, output):
    return GuardrailFunctionOutput(output_info=None, tripwire_triggered=False)


async def checkpoint_scenario(*, context=None, session=None, terminal=False, max_turns=10, values=("captured",),
                              tool_use_behavior=None):
    """tool_use_behavior, when given, replaces the behavior selected by terminal."""
    if tool_use_behavior is None:
        tool_use_behavior = "stop_on_first_tool" if terminal else "run_llm_again"
    agent, _, model, effects, result = await _checkpoint(context=context, session=session,
        tool_use_behavior=tool_use_behavior, max_turns=max_turns, values=values, routed=False)
    return agent, model, effects, result


async def routed_checkpoint_scenario(*, context=None):
    """Pause after a handoff, so the starting agent differs from the active owner.

    Returns (owner, router, model, effects, result); resume and restoration start from router.
    """
    return await _checkpoint(context=context, session=None, tool_use_behavior="run_llm_again", max_turns=10,
                             values=("captured",), routed=True)


async def _checkpoint(*, context, session, tool_use_behavior, max_turns, values, routed):
    effects = []
    tool = execution_tool(effects, needs_approval=True)
    model = UsageModel([
        Usage(requests=1, input_tokens=11, output_tokens=3, total_tokens=14),
        Usage(requests=1, input_tokens=17, output_tokens=5, total_tokens=22),
    ], [function_call(tool.name, {"value": value}, "pending" if index == 0 else f"pending-{index}")
        for index, value in enumerate(values)], "Continued.")
    agent = Agent(name="Checkpoint owner", model=model, tools=[tool],
                  tool_use_behavior=tool_use_behavior,
                  output_guardrails=[accept_answer])
    start = agent
    if routed:
        transfer = handoff(agent)
        start = Agent(name="Checkpoint router", handoffs=[transfer],
                      model=RecordingModel([function_call(transfer.tool_name, {}, "route")]))
    result = await execution_run(start, context=context, session=session, max_turns=max_turns)
    assert set(pending_calls(result)) == {"pending" if index == 0 else f"pending-{index}"
                                          for index in range(len(values))}
    assert result.final_output is None and effects == [] and result.last_agent is agent
    return agent, start, model, effects, result


class InterruptedWriteSession(ApplicationSession):
    """Fail once at a caller-owned session append, before or after committing it."""
    def __init__(self, identity, path):
        super().__init__(identity, path)
        self.failure = None
        self.error = RuntimeError("Application session write interrupted")

    async def add_items(self, items):
        failure, self.failure = self.failure, None
        if failure is None:
            return await super().add_items(items)
        self.failed_items = copy.deepcopy(items)
        if failure == "after":
            await super().add_items(items)
        elif failure != "before":
            raise ValueError("Unknown application failure mode")
        raise self.error


@dataclass
class ApprovalContext:
    tenant: str


async def checkpoint_process(operation, payload):
    """Run in separate interpreters; only JSON bytes cross their lifetime boundary."""
    if operation == "capture":
        effects = []
        done = execution_tool(effects, name="completed")
        pending = execution_tool(effects, needs_approval=True)
        model = UsageModel([
            Usage(requests=1, input_tokens=7, output_tokens=2, total_tokens=9),
            Usage(requests=1, input_tokens=13, output_tokens=4, total_tokens=17),
        ], [function_call(done.name, {"value": "before"}, "completed-call")],
           [function_call(pending.name, {"value": "after"}, "pending-call")])
        agent = Agent(name="Durable owner", model=model, tools=[done, pending])
        result = await execution_run(agent, context={"tenant": "retained"})
        assert effects == ["before"] and result.final_output is None
        return {"checkpoint": result.to_state().to_json(strict_context=True),
                "history": result.to_input_list(), "effects": effects}
    if operation != "restore":
        raise ValueError("Unknown checkpoint operation")
    effects = []
    done = execution_tool(effects, name="completed")
    pending = execution_tool(effects, needs_approval=True)
    model = UsageModel([Usage(requests=1, input_tokens=19, output_tokens=6, total_tokens=25)],
                       "Restored.")
    agent = Agent(name="Durable owner", model=model, tools=[done, pending])
    state = await RunState.from_json(agent, payload["checkpoint"], strict_context=True)
    assert set(pending_calls(state)) == {"pending-call"}
    state.approve(pending_calls(state)["pending-call"])
    result = await execution_run(agent, state)
    return {"output": result.final_output, "effects": effects,
            "history": result.to_input_list(), "request": model.requests[0]["input"],
            "agent": result.last_agent.name, "context": result.context_wrapper.context,
            "usage": {name: getattr(result.context_wrapper.usage, name) for name in
                      ("requests", "input_tokens", "output_tokens", "total_tokens")}}


class IdentifiedResponseModel(RecordingModel):
    """Application model that returns server response identifiers."""
    async def get_response(self, *args, **kwargs):
        response = await super().get_response(*args, **kwargs)
        response.response_id = f"application-response-{len(self.requests)}"
        return response
