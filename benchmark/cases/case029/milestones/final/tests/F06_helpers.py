# feature: F06
"""Application observers and trace destinations for observability checks."""
import copy
from F01_helpers import RecordingModel
from F03_helpers import ToolTraceCollector
from velmora import RunHooks, AgentHooks
from velmora.tracing.processor_interface import TracingExporter


class RunObserver(RunHooks):
    def __init__(self):
        self.events = []

    async def on_agent_start(self, context, agent):
        self.events.append(("start", agent))

    async def on_agent_end(self, context, agent, output):
        self.events.append(("end", agent, output))

    async def on_llm_start(self, context, agent, system_prompt, input_items):
        self.events.append(("request", agent, system_prompt, copy.deepcopy(input_items)))

    async def on_llm_end(self, context, agent, response):
        self.events.append(("response", agent, response))

    async def on_tool_start(self, context, agent, tool):
        self.events.append(("tool_start", agent, tool, context.tool_call_id,
                            context.tool_arguments))

    async def on_tool_end(self, context, agent, tool, result):
        self.events.append(("tool_end", agent, tool, result))

    async def on_handoff(self, context, from_agent, to_agent):
        self.events.append(("handoff", from_agent, to_agent))


class AgentObserver(AgentHooks):
    def __init__(self):
        self.events = []

    on_start = RunObserver.on_agent_start
    on_end = RunObserver.on_agent_end
    on_llm_start = RunObserver.on_llm_start
    on_llm_end = RunObserver.on_llm_end
    on_tool_start = RunObserver.on_tool_start
    on_tool_end = RunObserver.on_tool_end

    async def on_handoff(self, context, agent, source):
        self.events.append(("handoff", source, agent))


class UsageModel(RecordingModel):
    def __init__(self, usages, *outputs):
        super().__init__(*outputs)
        self.usages = list(usages)

    async def get_response(self, *args, **kwargs):
        response = await super().get_response(*args, **kwargs)
        response.usage = self.usages.pop(0)
        return response


class WorkflowCollector(ToolTraceCollector):
    def __init__(self):
        super().__init__()
        self.traces = []

    def on_trace_end(self, trace):
        self.traces.append(trace.export())


class ExportDestination(TracingExporter):
    def __init__(self):
        self.records = []

    def export(self, items):
        self.records.extend(copy.deepcopy(item.export()) for item in items)


def chat_payload(text=None, *, calls=None):
    """A protocol peer's Chat Completions reply, not a product replacement."""
    message = {"role": "assistant", "content": text}
    if calls is not None:
        message["tool_calls"] = calls
    return {"id": "chat_observed", "object": "chat.completion", "created": 1,
            "model": "peer-model", "choices": [{"index": 0,
                "finish_reason": "tool_calls" if calls else "stop", "message": message}]}


class ApprovalRejector(RunHooks):
    """An application rejects requested function calls through the public context."""
    def __init__(self, message):
        self.message = message

    async def on_llm_end(self, context, agent, response):
        from velmora import ToolApprovalItem
        for item in response.output:
            if item.type == "function_call":
                context.reject_tool(ToolApprovalItem(agent=agent, raw_item=item,
                    tool_name=item.name), rejection_message=self.message)
