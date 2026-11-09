# feature: F06
"""Acceptance checks for lifecycle, usage and trace disclosure."""
import copy
import json
from datetime import datetime

import pytest
from openai import AsyncOpenAI
from F01_helpers import RecordingModel, function_call
from F02_helpers import model_peer, response_payload
from F03_helpers import tool_trace_destination, tool_outputs
from F04_helpers import execution_run, execution_tool
from F06_helpers import (RunObserver, AgentObserver, UsageModel, WorkflowCollector,
                         ExportDestination, chat_payload, ApprovalRejector)
from _helpers import environment
from velmora import (Agent, RunConfig, Usage, ModelSettings, handoff,
                    OpenAIChatCompletionsModel, OpenAIResponsesModel,
                    InputGuardrail, GuardrailFunctionOutput, InputGuardrailTripwireTriggered)
from velmora import trace, custom_span, set_trace_processors, add_trace_processor, flush_traces, set_tracing_disabled
from velmora.tracing.processors import BatchTraceProcessor


@pytest.mark.asyncio
async def test_f06_t01():
    effects = []
    tool = execution_tool(effects)
    run_observer, first_observer, last_observer = RunObserver(), AgentObserver(), AgentObserver()
    target = Agent(name="Reviewer", model=RecordingModel("Reviewed."), hooks=last_observer)
    transfer = handoff(target)
    model = RecordingModel([function_call(tool.name, {"value": "document"}, "work")],
                           [function_call(transfer.tool_name, {}, "move")])
    first = Agent(name="Worker", instructions="Inspect documents.", model=model,
                  tools=[tool], handoffs=[transfer], hooks=first_observer)
    result = await execution_run(first, "Review document.", hooks=run_observer)
    assert effects == ["document"]
    assert result.final_output == "Reviewed."
    for observer, agents in ((run_observer, [first, target]),
                             (first_observer, [first]), (last_observer, [target])):
        assert [event[1] for event in observer.events if event[0] == "start"] == agents
        requests = [event for event in observer.events if event[0] == "request"]
        responses = [event for event in observer.events if event[0] == "response"]
        assert len(requests) == len(responses) == (3 if observer is run_observer else 2 if observer is first_observer else 1)
        expected = [(first, model.requests, result.raw_responses[:2]),
                    (target, target.model.requests, result.raw_responses[2:])]
        for agent, inputs, outputs in expected:
            if agent in agents:
                assert [event[3] for event in requests if event[1] is agent] == [r["input"] for r in inputs]
                assert [event[2] for event in responses if event[1] is agent] == outputs
                assert [event[2] for event in requests if event[1] is agent] == [r["instructions"] for r in inputs]
        if first in agents:
            assert ("tool_end", first, tool, "recorded:document") in observer.events
            starts = [e for e in observer.events if e[0] == "tool_start"]
            assert len(starts) == 1 and starts[0][1:4] == (first, tool, "work")
            assert json.loads(starts[0][4]) == {"value": "document"}
            assert all(e[2] == "Inspect documents." for e in requests if e[1] is first)
        if observer is not last_observer:
            assert ("handoff", first, target) in observer.events
        if target in agents:
            assert ("end", target, "Reviewed.") in observer.events


@pytest.mark.asyncio
async def test_f06_t02():
    usages = [Usage(requests=1, input_tokens=i, output_tokens=o, total_tokens=t,
                    input_tokens_details={"cached_tokens": c, "cache_write_tokens": w},
                    output_tokens_details={"reasoning_tokens": r})
              for i, o, t, c, w, r in [(11, 5, 16, 3, 2, 1), (23, 7, 30, 4, 6, 2), (31, 9, 40, 8, 1, 4)]]
    effects = []
    tool = execution_tool(effects)
    target = Agent(name="Usage target", model=UsageModel([usages[2]], "Complete."))
    transfer = handoff(target)
    model = UsageModel(usages[:2], [function_call(tool.name, {"value": "accounted"}, "work")],
                       [function_call(transfer.tool_name, {}, "move")])
    result = await execution_run(Agent(name="Usage source", model=model, tools=[tool], handoffs=[transfer]))
    assert result.final_output == "Complete." and effects == ["accounted"]
    total = result.context_wrapper.usage
    assert (total.requests, total.input_tokens, total.output_tokens, total.total_tokens) == (3, 65, 21, 86)
    assert (total.input_tokens_details.cached_tokens, total.input_tokens_details.cache_write_tokens,
            total.output_tokens_details.reasoning_tokens) == (15, 9, 7)
    for observed in ([r.usage for r in result.raw_responses], total.request_usage_entries):
        assert [(u.input_tokens, u.output_tokens, u.total_tokens,
                 u.input_tokens_details.cached_tokens, u.input_tokens_details.cache_write_tokens,
                 u.output_tokens_details.reasoning_tokens) for u in observed] == [
                     (11, 5, 16, 3, 2, 1), (23, 7, 30, 4, 6, 2), (31, 9, 40, 8, 1, 4)]
    fresh = await execution_run(Agent(name="New conversation", model=UsageModel([usages[0]], "New.")))
    assert fresh.final_output == "New."
    assert (fresh.context_wrapper.usage.requests, fresh.context_wrapper.usage.total_tokens) == (1, 16)
    assert total.total_tokens == 86


@pytest.mark.asyncio
async def test_f06_t03():
    with tool_trace_destination():
        collector = WorkflowCollector()
        set_trace_processors([collector])
        with trace("Document workflow", group_id="conversation", metadata={"application": "audit", "revision": 4}) as workflow:
            with custom_span("Application review", data={"section": "methods"}) as operation:
                effects = []
                tool = execution_tool(effects)
                target = Agent(name="Trace target", model=RecordingModel("Transferred."))
                transfer = handoff(target)
                source = Agent(name="Trace source", tools=[tool], handoffs=[transfer], model=RecordingModel(
                    [function_call(tool.name, {"value": "traced"}, "work")],
                    [function_call(transfer.tool_name, {}, "move")]))
                result = await execution_run(source, config=RunConfig())
                assert result.final_output == "Transferred." and effects == ["traced"]
            with model_peer(text="Model traced.") as (url, requests):
                async with AsyncOpenAI(api_key="local", base_url=url, max_retries=0) as client:
                    agent = Agent(name="Trace model", model=OpenAIChatCompletionsModel(model="peer-model", openai_client=client))
                    result = await execution_run(agent, config=RunConfig())
                    assert result.final_output == "Model traced." and len(requests) == 1
            def reject(context, agent, value):
                return GuardrailFunctionOutput({"reason": "policy"}, True)
            guard = InputGuardrail(guardrail_function=reject, name="Policy review", run_in_parallel=False)
            with pytest.raises(InputGuardrailTripwireTriggered):
                await execution_run(Agent(name="Blocked", model=RecordingModel(), input_guardrails=[guard]), config=RunConfig())
        assert len(collector.traces) == 1
        record = collector.traces[0]
        assert record["id"] == workflow.trace_id
        assert record["workflow_name"] == "Document workflow"
        assert record["group_id"] == "conversation"
        assert record["metadata"] == {"application": "audit", "revision": 4}
        spans = collector.spans
        by_id = {s["id"]: s for s in spans}
        assert len(by_id) == len(spans)
        for span in spans:
            assert span["trace_id"] == workflow.trace_id
            assert datetime.fromisoformat(span["started_at"]) <= datetime.fromisoformat(span["ended_at"])
            assert span["parent_id"] is None or span["parent_id"] in by_id
        custom = by_id[operation.span_id]
        assert custom["span_data"] == {"type": "custom", "name": "Application review", "data": {"section": "methods"}}
        agents = {s["span_data"]["name"]: s for s in spans if s["span_data"]["type"] == "agent"}
        assert {"Trace source", "Trace target", "Trace model", "Blocked"} <= agents.keys()
        # The application's custom scope encloses both agents of the delegated run.
        for name in ("Trace source", "Trace target"):
            current = agents[name]
            ancestors = set()
            for _ in range(len(spans)):
                parent = current["parent_id"]
                if parent is None:
                    break
                ancestors.add(parent)
                current = by_id[parent]
            assert operation.span_id in ancestors
        functions = [s for s in spans if s["span_data"]["type"] == "function"]
        assert any(s["span_data"]["name"] == tool.name and s["error"] is None for s in functions)
        assert any(s["span_data"]["type"] == "generation" and s["span_data"]["model"] == "peer-model" for s in spans)
        assert any(s["span_data"]["type"] == "handoff" and
                   s["span_data"]["from_agent"] == "Trace source" and
                   s["span_data"]["to_agent"] == "Trace target" for s in spans)
        assert any(s["span_data"]["type"] == "guardrail" and
                   s["span_data"]["name"] == "Policy review" and
                   s["span_data"]["triggered"] is True for s in spans)
        for kind, owner in (("function", "Trace source"), ("handoff", "Trace source"),
                            ("generation", "Trace model")):
            associated = [s for s in spans if s["span_data"]["type"] == kind]
            assert associated
            for child in associated:
                ancestors = set()
                for _ in spans:
                    parent = child["parent_id"]
                    if parent is None:
                        break
                    ancestors.add(parent)
                    child = by_id[parent]
                assert agents[owner]["id"] in ancestors, kind
        collector.spans.clear()
        standalone = await execution_run(Agent(name="Default trace", model=RecordingModel("Default.")), config=RunConfig(
            workflow_name="Standalone", group_id="conversation", trace_metadata={"application": "second"}))
        assert standalone.final_output == "Default."
        assert len(collector.traces) == 2
        assert collector.traces[-1]["workflow_name"] == "Standalone"
        assert collector.traces[-1]["group_id"] == record["group_id"]
        assert collector.traces[-1]["metadata"] == {"application": "second"}
        assert collector.traces[-1]["id"] != record["id"]
        assert any(s["span_data"]["type"] == "agent" and
                   s["span_data"]["name"] == "Default trace" for s in collector.spans)
        assert all(s["trace_id"] == collector.traces[-1]["id"] for s in collector.spans)


@pytest.mark.asyncio
async def test_f06_t04():
    for mode in ("default", "run", "global"):
        with tool_trace_destination():
            collector = WorkflowCollector()
            set_trace_processors([collector])
            if mode == "global":
                set_tracing_disabled(True)
            result = await execution_run(Agent(name="Switch", model=RecordingModel("Executed.")),
                                         config=RunConfig(tracing_disabled=mode == "run"))
            assert result.final_output == "Executed."
            if mode == "default":
                assert len(collector.traces) == 1
                assert any(s["span_data"]["type"] == "agent" for s in collector.spans)
            else:
                assert collector.traces == [] and collector.spans == []
            if mode == "run":
                # Run-level suppression also covers a run inside an active caller trace;
                # the caller's own trace and operation are not the affected work.
                effects = []
                tool = execution_tool(effects)
                model = RecordingModel([function_call(tool.name, {"value": "masked"}, "masked")], "Masked.")
                with trace("Caller workflow") as outer:
                    with custom_span("Caller operation", data={"step": "enclosing"}) as operation:
                        result = await execution_run(Agent(name="Masked run", model=model, tools=[tool]),
                                                     config=RunConfig(tracing_disabled=True))
                assert result.final_output == "Masked." and effects == ["masked"]
                assert [t["id"] for t in collector.traces] == [outer.trace_id]
                assert [s["id"] for s in collector.spans] == [operation.span_id]


def test_f06_t05():
    with tool_trace_destination():
        first, second, replacement = ExportDestination(), ExportDestination(), ExportDestination()
        processors = [BatchTraceProcessor(destination, schedule_delay=60) for destination in (first, second, replacement)]
        try:
            set_trace_processors([processors[0]])
            with trace("Initial") as initial:
                with custom_span("first operation", data={"value": "first"}):
                    pass
            flush_traces()
            assert any(r["object"] == "trace" and r["id"] == initial.trace_id for r in first.records)
            assert any(r["object"] == "trace.span" and r["trace_id"] == initial.trace_id and
                       r["span_data"]["data"] == {"value": "first"} for r in first.records)
            add_trace_processor(processors[1])
            with trace("Added") as added:
                with custom_span("second operation", data={"value": "second"}):
                    pass
            flush_traces()
            for destination in (first, second):
                records = [r for r in destination.records if r.get("trace_id", r["id"]) == added.trace_id]
                assert any(r["object"] == "trace" for r in records)
                assert any(r["object"] == "trace.span" and r["span_data"]["data"] == {"value": "second"} for r in records)
            before = (copy.deepcopy(first.records), copy.deepcopy(second.records))
            set_trace_processors([processors[2]])
            with trace("Replacement") as replaced:
                with custom_span("pending operation", data={"value": "pending"}):
                    pass
            set_tracing_disabled(True)
            flush_traces()
            assert (first.records, second.records) == before
            assert any(r["object"] == "trace" and r["id"] == replaced.trace_id for r in replacement.records)
            assert any(r["object"] == "trace.span" and r["trace_id"] == replaced.trace_id and
                       r["span_data"]["data"] == {"value": "pending"} for r in replacement.records)
        finally:
            for processor in processors:
                processor.shutdown()


@pytest.mark.asyncio
async def test_f06_t06():
    # Rebuild both arms: the disclosure setting is their only differing input.
    for sensitive in (None, False):
        config = RunConfig() if sensitive is None else RunConfig(trace_include_sensitive_data=False)
        effects = []
        tool = execution_tool(effects)
        arguments = json.dumps({"value": "private-document"})
        call = {"id": "private-call", "type": "function",
                "function": {"name": tool.name, "arguments": arguments}}
        replies = [(200, chat_payload(calls=[call]), {}),
                   (200, chat_payload("Private answer."), {})]
        with tool_trace_destination() as collector:
            with model_peer(replies=replies) as (url, requests):
                async with AsyncOpenAI(api_key="local", base_url=url, max_retries=0) as client:
                    result = await execution_run(Agent(name="Disclosure", tools=[tool],
                        model=OpenAIChatCompletionsModel(model="peer-model", openai_client=client)),
                        "Private question.", config=config)
            assert result.final_output == "Private answer."
            assert effects == ["private-document"]
            assert len(requests) == 2
            assert requests[1]["body"]["messages"][-1]["content"] == "recorded:private-document"
            models = [s["span_data"] for s in collector.spans if s["span_data"]["type"] == "generation"]
            functions = [s["span_data"] for s in collector.spans if s["span_data"]["type"] == "function"]
            assert len(models) == 2 and len(functions) == 1
            if sensitive is None:
                assert models[0]["input"][-1]["content"] == "Private question."
                assert models[1]["output"][0]["content"] == "Private answer."
                assert json.loads(functions[0]["input"]) == {"value": "private-document"}
                assert functions[0]["output"] == "recorded:private-document"
            else:
                for data in models + functions:
                    assert data["input"] is None and data["output"] is None

        rejection = "Private approval decision."
        gated = execution_tool([], needs_approval=True)
        model = RecordingModel([function_call(gated.name, {"value": "pending"}, "gate")], "Decision received.")
        agent = Agent(name="Approval disclosure", model=model, tools=[gated])
        with tool_trace_destination() as collector:
            result = await execution_run(agent, config=config, hooks=ApprovalRejector(rejection))
            assert result.final_output == "Decision received."
            assert tool_outputs(model.requests[-1])["gate"] == rejection
            rejected = [s for s in collector.spans if s["span_data"]["type"] == "function" and s["error"] is not None]
            assert len(rejected) == 1, collector.spans
            if sensitive is None:
                assert rejected[0]["error"]["message"] == rejection
            else:
                assert rejection not in json.dumps(collector.spans)
                assert rejected[0]["span_data"]["input"] is None
                assert rejected[0]["span_data"]["output"] is None


@pytest.mark.asyncio
async def test_f06_t07():
    from velmora.extensions.models.any_llm_model import AnyLLMModel
    with environment({"LITELLM_LOCAL_MODEL_COST_MAP": "True"}):
        from velmora.extensions.models.litellm_model import LitellmModel

    for adapter in ("responses", "chat", "any", "litellm"):
        is_responses = adapter in ("responses", "any")
        usage = ({"input_tokens": 17, "output_tokens": 4, "total_tokens": 21,
                  "input_tokens_details": {"cached_tokens": 0},
                  "output_tokens_details": {"reasoning_tokens": 2}} if is_responses else
                 {"prompt_tokens": 17, "completion_tokens": 4, "total_tokens": 21,
                  "prompt_tokens_details": {"cached_tokens": 0},
                  "completion_tokens_details": {"reasoning_tokens": 2}})
        # Extra provider fields are supplied inputs, not a required field catalogue.
        usage["billing"] = {"units": [3, 5]}
        zero = copy.deepcopy(usage)
        details = "input_tokens_details" if is_responses else "prompt_tokens_details"
        zero[details]["cache_write_tokens"] = 0
        payloads = []
        for supplied in (usage, zero, None):
            payload = response_payload("Usage answer.") if is_responses else chat_payload("Usage answer.")
            if supplied is not None:
                payload["usage"] = supplied
            payloads.append((200, payload, {}))
        with model_peer(replies=payloads) as (url, requests):
            async with AsyncOpenAI(api_key="local", base_url=url, max_retries=0) as client:
                if adapter == "responses":
                    model = OpenAIResponsesModel(model="peer-model", openai_client=client)
                elif adapter == "chat":
                    model = OpenAIChatCompletionsModel(model="peer-model", openai_client=client)
                elif adapter == "any":
                    model = AnyLLMModel("openai/peer-model", base_url=url, api_key="local", api="responses")
                else:
                    model = LitellmModel("openai/peer-model", base_url=url, api_key="local")
                try:
                    snapshots = []
                    for _ in payloads:
                        result = await execution_run(Agent(name="Raw accounting", model=model,
                            model_settings=ModelSettings(preserve_raw_usage=True)))
                        assert result.final_output == "Usage answer."
                        assert len(result.raw_responses) == 1
                        snapshots.append(result.raw_responses[0].raw_usage)
                    assert len(requests) == len(payloads)
                    if adapter == "litellm":
                        assert snapshots == [None, None, None]
                    else:
                        assert snapshots == [usage, zero, None], adapter
                        snapshots[0]["billing"]["units"].append(99)
                        assert snapshots[1] == zero
                        assert payloads[0][1]["usage"] == usage
                finally:
                    if adapter == "any":
                        await model.close()
