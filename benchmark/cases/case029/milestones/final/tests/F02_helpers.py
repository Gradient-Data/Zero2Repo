# feature: F02
"""Application models and real offline protocol peers for model controls."""
from __future__ import annotations

import asyncio
import copy
import inspect
import json
import threading
import time
from contextlib import contextmanager, asynccontextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from F01_helpers import RecordingModel, text_message
from _helpers import invoke, consume
from velmora import Agent, ModelProvider, ModelResponse, RunConfig, Runner, Usage
from openai.types.responses import Response, ResponseCompletedEvent


def response_payload(text):
    return {
        "id": "resp_peer", "object": "response", "created_at": 1,
        "model": "peer-model", "status": "completed",
        "output": [text_message(text).model_dump()], "parallel_tool_calls": False,
        "tool_choice": "auto", "tools": [],
    }


def completed_event(text):
    return ResponseCompletedEvent(type="response.completed", sequence_number=1,
                                  response=Response.model_validate(response_payload(text)))


@contextmanager
def model_peer(*, text="Peer answer.", chat_message=None, finish_reason="stop", replies=None):
    """Serve actual HTTP, recording path, headers and parsed request body."""
    requests = []
    failures = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            try:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append({"path": self.path, "headers": {key.lower(): value for key, value in self.headers.items()},
                                 "body": body, "time": time.monotonic()})
                if replies is not None:
                    status, payload, headers = replies[len(requests) - 1]
                elif self.path == "/v1/chat/completions":
                    status, headers = 200, {}
                    payload = {"id": "chat_peer", "object": "chat.completion",
                               "created": 1, "model": body["model"],
                               "choices": [{"index": 0, "finish_reason": finish_reason,
                                            "message": chat_message if chat_message is not None else
                                            {"role": "assistant", "content": text}}]}
                else:
                    status, payload, headers = 200, response_payload(text), {}
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(data)
            except BaseException as error:
                failures.append(error)
                raise

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", requests
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
        assert not worker.is_alive(), "HTTP peer failed to stop."
        if failures:
            raise failures[0]


@asynccontextmanager
async def websocket_peer(text):
    from websockets.asyncio.server import serve
    requests = []
    failures = []

    async def handle(connection):
        try:
            async for raw in connection:
                requests.append({"path": connection.request.path, "body": json.loads(raw)})
                await connection.send(json.dumps({"type": "response.completed",
                                                   "sequence_number": 1,
                                                   "response": response_payload(text)}))
        except BaseException as error:
            failures.append(error)
            raise

    async with serve(handle, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        yield f"ws://127.0.0.1:{port}/v1", requests
    if failures:
        raise failures[0]


class SelectedProvider(ModelProvider):
    def __init__(self, model):
        self.model = model
        self.names = []

    def get_model(self, model_name):
        self.names.append(model_name)
        return self.model


class AttemptModel(RecordingModel):
    """Caller-supplied model; each action is an output, error or async application."""
    def __init__(self, *actions, advice=None):
        super().__init__()
        self.actions = list(actions)
        self.advice = advice
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.times = []

    async def next_action(self, input, model_settings, **kwargs):
        self.requests.append({"input": copy.deepcopy(input), "settings": model_settings, **kwargs})
        self.times.append(time.monotonic())
        self.started.set()
        if not self.actions:
            raise AssertionError("Unexpected extra model attempt.")
        action = self.actions.pop(0)
        if isinstance(action, BaseException):
            raise action
        if callable(action):
            action = action()
            if inspect.isawaitable(action):
                action = await action
        return action

    async def get_response(self, system_instructions, input, model_settings, tools,
                           output_schema, handoffs, tracing, **kwargs):
        action = await self.next_action(input, model_settings, **kwargs)
        if isinstance(action, str):
            action = [text_message(action)]
        return ModelResponse(output=action, usage=Usage(), response_id="resp_app")

    async def stream_response(self, system_instructions, input, model_settings, tools,
                              output_schema, handoffs, tracing, **kwargs):
        action = await self.next_action(input, model_settings, **kwargs)
        if isinstance(action, str):
            yield completed_event(action)
        else:
            for event in action:
                if isinstance(event, BaseException):
                    raise event
                yield event

    def get_retry_advice(self, request):
        return self.advice


async def model_run(model=None, *, settings=None, run_settings=None, provider=None,
                    run_model=None, stream=False, tools=None, timeout=10, **kwargs):
    agent = Agent(name="Model controls", model=model, tools=tools or [],
                  model_settings=settings) if settings is not None else Agent(
                      name="Model controls", model=model, tools=tools or [])
    config = RunConfig(tracing_disabled=True, model_settings=run_settings, model=run_model,
                       **({"model_provider": provider} if provider is not None else {}))
    if stream:
        result = Runner.run_streamed(agent, "Process this request.", run_config=config, **kwargs)
        events = await consume(result.stream_events(), timeout=timeout)
        return result, events
    return await invoke(Runner.run, agent, "Process this request.", run_config=config,
                        timeout=timeout, **kwargs)


def retry_settings(policy, count=1, delay=0):
    from velmora import ModelSettings
    from velmora import ModelRetrySettings
    return ModelSettings(retry=ModelRetrySettings(max_retries=count, policy=policy,
                         backoff={"initial_delay": delay, "jitter": False}))
