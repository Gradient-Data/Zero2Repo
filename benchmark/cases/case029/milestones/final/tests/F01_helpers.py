# feature: F01
"""Application-owned model and protocol peer for agent acceptance tests."""
from __future__ import annotations

import copy
import json
import threading
import sys
from pathlib import Path
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

# The harness builds and tests in separate containers; import the delivered source.
sys.path.insert(0, str(Path.cwd() / "src"))

from velmora import Model, ModelResponse, RunConfig, Runner, Usage
from _helpers import invoke


def text_message(text):
    return ResponseOutputMessage(
        id="message", type="message", role="assistant", status="completed",
        content=[ResponseOutputText(type="output_text", text=text, annotations=[])],
    )


def function_call(name, arguments, call_id):
    return ResponseFunctionToolCall(
        type="function_call", name=name, arguments=json.dumps(arguments), call_id=call_id,
    )


class RecordingModel(Model):
    """Supply application-controlled model responses and retain incoming requests."""

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.requests = []

    async def get_response(self, system_instructions, input, model_settings, tools,
                           output_schema, handoffs, tracing, **kwargs):
        self.requests.append({
            "instructions": system_instructions, "input": copy.deepcopy(input),
            "tools": list(tools), "output_schema": output_schema, **kwargs,
        })
        if not self.outputs:
            raise AssertionError("Unexpected model request.")
        output = self.outputs.pop(0)
        if isinstance(output, str):
            output = [text_message(output)]
        return ModelResponse(output=output, usage=Usage(), response_id=None)

    async def stream_response(self, *args, **kwargs):
        raise AssertionError("Unexpected streaming request.")
        yield


async def run_agent(agent, *, context=None, input="Please proceed."):
    return await invoke(Runner.run, agent, input=input, context=context,
                        run_config=RunConfig(tracing_disabled=True))


@contextmanager
def responses_peer():
    """Serve Responses JSON over real local HTTP and record complete request bodies."""
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            requests.append({"path": self.path, "body": json.loads(body)})
            payload = json.dumps({
                "id": "resp_local", "object": "response", "created_at": 1,
                "model": "application-model", "status": "completed",
                "output": [text_message("Template response.").model_dump()],
                "parallel_tool_calls": False, "tool_choice": "auto", "tools": [],
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

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
        assert not worker.is_alive(), "Protocol peer failed to stop."
