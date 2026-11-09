# feature: F06
"""Importable author workloads and fresh-process history observations."""
import ast
import base64
import hashlib
import io
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path

import velnora
from velnora import Scheduler, task
from velnora.cli import VelnoraClient
from velnora.config import Config
from velnora.scheduler import JobInfo
from velnora.value import Value, get_type_registry

from _helpers import (execute_client, read_export_jsonl, read_log_json,
                      run_process, run_python, workspace, write_text)
from F01_helpers import AuthoredFailure
from F02_helpers import run_value_workflow


@task(namespace="f06.history")
def increment(value: int):
    return value + 9


@task(namespace="f06.history")
def multiply(value: int):
    return value * 4


@task(namespace="f06.history")
def pipeline(value: int = 7):
    return multiply(increment(value))


@task(namespace="f06.history")
def broken(value: str):
    raise AuthoredFailure(value)


@task(namespace="f06.history")
def failing_parent(value: str):
    return broken(value)


@task(namespace="f06.identity", priority=13, cache=False)
def identify(label: str, info=JobInfo()):
    return {"label": label, "execution": info.execution_id,
            "job": info.job_id, "priority": info.options["priority"]}


@task(namespace="f06.identity", cache=False)
def siblings():
    return [identify("left"), identify.options(priority=29)("right")]


class BytePayload(Value):
    """A lossless author protocol with exactly one byte per payload byte."""
    type_name = "f06.BytePayload"

    def __init__(self, data):
        self.data = data

    def __repr__(self):
        return "BytePayload(size={})".format(len(self.data))

    def serialize(self):
        return self.data

    @classmethod
    def deserialize(cls, raw_type, data):
        return cls(data)

    def get_hash(self, data=None):
        return hashlib.sha1(self.data if data is None else data).hexdigest()


def prepare_repository(directory, **backend_options):
    directory.mkdir()
    uri = "sqlite:///" + str(directory / "history.db")
    options = {"db_uri": uri, **backend_options}
    write_text(directory / "velnora.ini", "[backend]\n" + "".join(
        "{} = {}\n".format(key, value) for key, value in options.items()))


@contextmanager
def postgres_repository(directory):
    """Run a private real server over a short, isolated Unix socket path."""
    binaries = Path("/usr/lib/postgresql/16/bin")
    with workspace() as root:
        data = root / "data"
        socket = root / "socket"
        socket.mkdir()
        initialized = run_process([
            binaries / "initdb", "-D", data, "-A", "trust", "-U", "author",
        ], cwd=root)
        assert initialized.returncode == 0, initialized
        started = run_process([
            binaries / "pg_ctl", "-D", data, "-l", root / "server.log",
            "-w", "-t", "30", "-o", "-F -k {} -h ''".format(socket), "start",
        ], cwd=root)
        assert started.returncode == 0, (started, (root / "server.log").read_text())
        try:
            prepare_repository(directory, db_uri="postgresql://author@/postgres?host=" + str(socket))
            initialized = execute_client(VelnoraClient(), [
                "velnora", "--config", str(directory), "db", "upgrade",
                "latest",
            ])
            assert initialized.exception is None, initialized
            yield directory
        finally:
            stopped = run_process([
                binaries / "pg_ctl", "-D", data, "-w", "-t", "30", "stop",
            ], cwd=root)
            assert stopped.returncode == 0, stopped


def history_scheduler(directory):
    config = Config()
    config.read_path(str(Path(directory) / "velnora.ini"))
    scheduler = Scheduler(config=config)
    scheduler.load()
    return scheduler


def history_snapshot(directory):
    """Read only public JSON carriers; query and parsing failures propagate."""
    prefix = ["velnora", "--config", str(directory)]
    output = io.StringIO()
    result = execute_client(VelnoraClient(stdout=output), prefix + [
        "log", "--all", "--format", "json", "--no-pager"])
    assert result.exception is None, result
    logged = read_log_json(output.getvalue())
    target = Path(directory) / "export.jsonl"
    result = execute_client(VelnoraClient(), prefix + ["export", "--file", str(target)])
    assert result.exception is None, result
    return {"log": logged, "export": read_export_jsonl(target)}


def job_task_name(job, values):
    """Resolve a job's required task identity, including unfinished calls."""
    task = values[job["task_hash"]]["subtype"]
    assert task["_type"] == "Task"
    return ".".join(part for part in (task["namespace"], task["name"]) if part)


def failure_diagnostic(directory, job_id):
    """Read labelled public failure diagnostics without restoring internal objects."""
    output = io.StringIO()
    result = execute_client(VelnoraClient(stdout=output), [
        "velnora", "--config", str(directory), "log", "--no-pager", "--job", job_id])
    assert result.exception is None, result
    lines = [line.strip() for line in output.getvalue().splitlines()]
    raised = [line.removeprefix("Raised:").strip() for line in lines
              if line.startswith("Raised:")]
    assert len(raised) == 1, output.getvalue()
    expression = ast.parse(raised[0], mode="eval").body
    assert isinstance(expression, ast.Call) and isinstance(expression.func, ast.Name), raised
    assert not expression.keywords, raised
    payload = [ast.literal_eval(arg) for arg in expression.args]
    assert lines.count("Traceback:") == 1, output.getvalue()
    trace = lines[lines.index("Traceback:") + 1:]
    frame_form = re.compile(r'(?:Job [^:]+: )?File ".*", line [0-9]+, in (.+)')
    frames = [match.group(1) for line in trace if (match := frame_form.fullmatch(line))]
    assert frames, output.getvalue()
    return {"type": expression.func.id, "args": payload, "frames": frames}

def history_action(directory, action, value):
    """Run a single client lifetime; test observations are saved separately."""
    global multiply
    directory = Path(directory)
    if action == "snapshot":
        answer = history_snapshot(directory)
    elif action == "failure_diagnostic":
        answer = failure_diagnostic(directory, value)
    elif action == "default":
        prefix = ["velnora", "--config", str(directory)]
        if not directory.exists():
            result = execute_client(VelnoraClient(), prefix + ["init"])
            assert result.exception is None, result
        result = execute_client(VelnoraClient(), prefix + [
            "run", __file__, "f06.history.pipeline", "--value", str(value)])
        assert result.exception is None, result
        answer = result.value
    else:
        scheduler = history_scheduler(directory)
        if action == "version":
            multiply = task(name="multiply", namespace="f06.history", version=value)(multiply.func)
            answer = run_value_workflow(scheduler, pipeline(7))
        elif action == "run":
            answer = run_value_workflow(scheduler, pipeline(value))
        elif action == "fail":
            from _helpers import run_workflow
            result = run_workflow(scheduler, failing_parent(value))
            assert isinstance(result.exception, AuthoredFailure), result
            assert result.exception.args == (value,)
            answer = "failed"
        elif action == "identity":
            answer = run_value_workflow(scheduler, siblings())
        elif action == "recover":
            restored, present = scheduler.backend.get_value(value)
            assert present is True
            assert restored == 64
            answer = run_value_workflow(scheduler, multiply(restored))
        elif action == "missing":
            restored, present = scheduler.backend.get_value(value)
            assert (restored, present) == (None, False)
            answer = "missing"
        elif action == "default_limit":
            from velnora.backends.db import VelnoraDatabaseError
            registry = get_type_registry()
            payload = BytePayload(b"q" * 1_000_000_000)
            assert len(registry.serialize(payload)) == 1_000_000_000
            key = scheduler.backend.record_value(payload)
            recovered, present = scheduler.backend.get_value(key)
            assert present is True
            assert isinstance(recovered, BytePayload)
            assert recovered.data == payload.data
            del recovered, payload
            payload = BytePayload(b"r" * 1_000_000_001)
            assert len(registry.serialize(payload)) == 1_000_000_001
            try:
                scheduler.backend.record_value(payload)
            except VelnoraDatabaseError:
                answer = "boundary enforced"
            else:
                raise AssertionError("Oversized serialized value was accepted")
        else:
            raise ValueError("Unknown history action: " + action)
    (directory / "observation.json").write_text(json.dumps(answer), encoding="utf-8")


def fresh_history(directory, action, value=None, timeout=90):
    """A new interpreter for every writer/reader, never an in-memory restart."""
    source = """import json, sys
from F06_helpers import history_action
history_action(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]))
"""
    tests_dir = str(Path(__file__).parent)
    result = run_python(source, cwd=directory.parent,
                        args=[str(directory), action, json.dumps(value)],
                        env={"PYTHONPATH": os.pathsep.join([tests_dir,
                             str(Path(velnora.__file__).resolve().parent.parent),
                             os.environ.get("PYTHONPATH", "")])},
                        timeout=timeout)
    assert result.returncode == 0, result
    return json.loads((directory / "observation.json").read_text(encoding="utf-8"))


def records_of(snapshot, kind, channel="export"):
    return [row for row in snapshot[channel] if row["_type"] == kind]


def decoded_record(row):
    return get_type_registry().deserialize(row["type"], base64.b64decode(row["data"], validate=True))
