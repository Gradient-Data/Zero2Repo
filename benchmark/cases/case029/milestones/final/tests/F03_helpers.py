# feature: F03
"""Public tool-result observations and application-owned tracing destination."""
from contextlib import contextmanager

from F01_helpers import RecordingModel, function_call, run_agent
from velmora import Agent
from velmora import TracingProcessor, set_trace_provider
from velmora.tracing import get_trace_provider
from velmora.tracing.provider import DefaultTraceProvider


def tool_outputs(request, *, kind="function_call_output"):
    """Read tool outputs by their protocol discriminator and correlation identifier."""
    return {item["call_id"]: item["output"] for item in request["input"]
            if isinstance(item, dict) and item.get("type") == kind}


async def tool_turn(tool, arguments, *, context=None):
    """Execute one real tool call and retain the following model request."""
    model = RecordingModel([function_call(tool.name, arguments, "application-call")], "Finished.")
    result = await run_agent(Agent(name="Application", model=model, tools=[tool]), context=context)
    assert result.final_output == "Finished."
    return result, model


class ToolTraceCollector(TracingProcessor):
    """Collect exported public payloads synchronously without a remote exporter."""

    def __init__(self):
        self.spans = []

    def on_trace_start(self, trace):
        pass

    def on_trace_end(self, trace):
        pass

    def on_span_start(self, span):
        pass

    def on_span_end(self, span):
        self.spans.append(span.export())

    def shutdown(self):
        pass

    def force_flush(self):
        pass


@contextmanager
def tool_trace_destination():
    """Install an isolated public tracing provider and restore the prior provider."""
    previous = get_trace_provider()
    provider = DefaultTraceProvider()
    collector = ToolTraceCollector()
    provider.set_processors([collector])
    set_trace_provider(provider)
    try:
        yield collector
    finally:
        set_trace_provider(previous)
        provider.shutdown()
