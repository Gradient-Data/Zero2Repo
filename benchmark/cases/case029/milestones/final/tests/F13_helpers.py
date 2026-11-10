# feature: F13
"""Caller-owned local execution environments driven through public SDK entries."""
import base64
import struct
import zlib

from F01_helpers import RecordingModel
from F04_helpers import execution_run
from F12_helpers import raw_dict
from _helpers import run_process
from velmora import Agent, Computer, ShellResult, ShellCommandOutput, ShellCallOutcome, RunState, apply_diff
from velmora import ApplyPatchResult
from openai.types.responses import ResponseComputerToolCall, ResponseFunctionShellToolCall
from openai.types.responses.response_output_item import ResponseApplyPatchToolCall


class CanvasComputer(Computer):
    """A small raster application: pointers paint pixels and typing edits its text."""
    def __init__(self):
        self.pixels = bytearray(32 * 32)
        self.pointer = (0, 0)
        self.text = ""
        self.offset = (0, 0)
        self.ready = False
        self.captures = 0

    @property
    def environment(self):
        return "ubuntu"

    @property
    def dimensions(self):
        return (32, 32)

    def paint(self, x, y, value):
        self.pixels[y * 32 + x] = value

    def click(self, x, y, button):
        self.pointer = (x, y)
        self.paint(x, y, {"left": 80, "right": 120}[button])

    def double_click(self, x, y):
        self.pointer = (x, y)
        self.paint(x, y, 160)
        self.text = ""

    def scroll(self, x, y, scroll_x, scroll_y):
        self.pointer = (x, y)
        self.offset = (self.offset[0] + scroll_x, self.offset[1] + scroll_y)
        self.paint(x, y, 200)

    def type(self, text):
        self.text += text
        for i, value in enumerate(self.text.encode()):
            self.paint(i, 31, value)

    def wait(self):
        self.ready = True
        self.paint(31, 0, 255)

    def move(self, x, y):
        self.pointer = (x, y)
        self.paint(x, y, 40)

    def keypress(self, keys):
        if keys == ["BACKSPACE"]:
            self.text = self.text[:-1]
            self.paint(len(self.text), 31, 0)
        else:
            raise ValueError("Unsupported application key")

    def drag(self, path):
        for x, y in path:
            self.paint(x, y, 240)
        self.pointer = path[-1]

    def render(self):
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        rows = b"".join(b"\0" + bytes(self.pixels[y*32:(y+1)*32]) for y in range(32))
        png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 32, 32, 8, 0, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
        return base64.b64encode(png).decode()

    def screenshot(self):
        self.captures += 1
        return self.render()


class DirectoryExecutor:
    """Execute real shell commands in a selected temporary directory."""
    def __init__(self, directory):
        self.directory = directory
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        action = request.data.action
        outputs = []
        for command in action.commands:
            process = run_process(["/bin/sh", "-c", command], cwd=self.directory,
                                  timeout=action.timeout_ms / 1000 if action.timeout_ms else 10)
            outputs.append(ShellCommandOutput(command=command, stdout=process.stdout.decode(),
                stderr=process.stderr.decode(), outcome=ShellCallOutcome(type="exit", exit_code=process.returncode)))
        return ShellResult(output=outputs)


class DirectoryEditor:
    """Apply edits to real files; application validation failures remain failures."""
    def __init__(self, directory):
        self.directory = directory
        self.operations = []

    def create_file(self, operation):
        self.operations.append(operation)
        path = self.directory / operation.path
        if path.exists():
            # Application refusal reported through the result carrier, not an exception.
            return ApplyPatchResult(status="failed", output="Application refused to replace a file.")
        with path.open("x") as stream:
            stream.write(apply_diff("", operation.diff, mode="create"))
        return ApplyPatchResult(status="completed", output=path.read_text())

    def update_file(self, operation):
        self.operations.append(operation)
        path = self.directory / operation.path
        path.write_text(apply_diff(path.read_text(), operation.diff))
        return ApplyPatchResult(status="completed", output=path.read_text())

    def delete_file(self, operation):
        self.operations.append(operation)
        (self.directory / operation.path).unlink()
        return ApplyPatchResult(status="completed")


def computer_call(actions, checks=()):
    return ResponseComputerToolCall(type="computer_call", id="computer-item", call_id="local-call",
        status="completed", actions=actions, pending_safety_checks=list(checks))


def shell_call(commands, **constraints):
    # Unvalidated model-origin payloads let the SDK reject invalid constraints itself.
    call = ResponseFunctionShellToolCall.model_construct(type="shell_call", id="shell-item",
        call_id="local-call", status="completed", action={"commands": commands, **constraints})
    if "timeout_ms" in constraints:
        call.action.timeout_ms = constraints["timeout_ms"]
    return call


def patch_call(kind, path, diff=None):
    operation = {"type": kind, "path": path}
    if diff is not None:
        operation["diff"] = diff
    return ResponseApplyPatchToolCall.model_construct(type="apply_patch_call", id="patch-item",
        call_id="local-call", status="completed", operation=operation)


async def local_turn(tool, call, *, context=None, owner="Local application"):
    model = RecordingModel([call], "Local turn complete.")
    agent = Agent(name=owner, model=model, tools=[tool])
    result = await execution_run(agent, context=context)
    return agent, model, result


def local_output(result, kind):
    outputs = [raw_dict(item.raw_item) for item in result.new_items
               if raw_dict(item.raw_item).get("type") == kind]
    assert len(outputs) == 1
    return outputs[0]


def local_model_output(model, kind):
    """Read a full local-tool output item from the following model request."""
    items = [item for item in model.requests[-1]["input"]
             if isinstance(item, dict) and item.get("type") == kind]
    assert len(items) == 1
    return items[0]
