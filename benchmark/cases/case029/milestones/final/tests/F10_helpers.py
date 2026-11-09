# feature: F10
"""Application streaming model and cooperative tool boundaries."""
import asyncio

from F01_helpers import text_message
from F02_helpers import AttemptModel, completed_event
from velmora import FunctionTool, RunConfig, Runner
from openai.types.responses import ResponseTextDeltaEvent


def stream_completion(*items):
    event = completed_event("")
    return event.model_copy(update={"response": event.response.model_copy(update={"output": list(items)})})


def stream_delta(text):
    return ResponseTextDeltaEvent(type="response.output_text.delta", sequence_number=0,
        item_id="message", output_index=0, content_index=0, delta=text, logprobs=[])


class BoundaryStreamModel(AttemptModel):
    """Hold selected responses open until the event consumer releases them."""
    def __init__(self, *outputs, gates=None):
        super().__init__(*outputs)
        self.gates = gates or {}

    async def stream_response(self, system_instructions, input, model_settings, tools,
                              output_schema, handoffs, tracing, **kwargs):
        output = await self.next_action(input, model_settings, **kwargs)
        index = len(self.requests)
        if isinstance(output, str):
            output = [text_message(output)]
        for item in output:
            if item.type == "message":
                yield stream_delta(item.content[0].text[:4])
                yield stream_delta(item.content[0].text[4:])
        if index in self.gates:
            await self.gates[index].wait()
        yield stream_completion(*output)


def start_stream(agent, input="Proceed.", **kwargs):
    return Runner.run_streamed(agent, input, run_config=RunConfig(tracing_disabled=True), **kwargs)


class CooperativeWork:
    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.stopped = asyncio.Event()
        self.effects = []

        async def apply(context, arguments):
            self.effects.append("before")
            self.entered.set()
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.stopped.set()
                raise
            self.effects.append("after")
            return "work completed"

        self.tool = FunctionTool(name="cooperate", description="Perform cooperative application work.",
            params_json_schema={"type": "object", "properties": {}, "additionalProperties": False},
            on_invoke_tool=apply)


class DeliveredFailureModel(AttemptModel):
    """Keep the response open until the consumer has received partial output."""
    def __init__(self, *actions):
        super().__init__(*actions)
        self.delivered = asyncio.Event()

    async def stream_response(self, *args, **kwargs):
        async for event in super().stream_response(*args, **kwargs):
            yield event
            if event.type == "response.output_text.delta":
                await self.delivered.wait()
