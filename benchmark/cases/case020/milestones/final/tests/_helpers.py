# feature: F00
"""Shared public-interface driving machinery, without behavioral expectations.

All commands are argv sequences. Environments and working directories are
explicit. Completed nonzero statuses are observations, not helper failures.
Launch, timeout, IO and parse failures raise, retaining their original cause.
Diagnostic schemas not published by the interface must be supplied by callers;
this module never infers a category from human-readable error messages.
"""

import contextlib as _contextlib
import dataclasses as _dataclasses
import json as _json
import math as _math
import os as _os
from pathlib import Path as _Path
import signal as _signal
import subprocess as _subprocess
import tempfile as _tempfile
import threading as _threading
import time as _time


# The portable recipe provisions product dependencies in this runtime.
# Keep product launches independent of pytest and caller-controlled PATH.
PRODUCT_PYTHON = "/opt/runtime/bin/python"

# Native tools are provisioned here by the image, independently of pytest's
# interpreter. Caller PATH overrides are applied after this default binding.
NATIVE_TOOL_DIRECTORY = "/opt/runtime/bin"

# Bounds only for a hung process, never a speed requirement: the judge host can be
# heavily loaded; under a load spike one CLI call printed nothing for 300 s.
COMMAND_TIMEOUT = 900
SERVICE_READY_TIMEOUT = 120


class HelperError(AssertionError):
    """Machinery failure with chained cause; never a product result/status."""


def _timeout(value):
    if not _math.isfinite(value) or value <= 0:
        raise ValueError("Timeout must be finite and positive")
    return value


def _argv(command):
    if isinstance(command, (str, bytes, _os.PathLike)):
        raise TypeError("Command must be an argv sequence, not a shell string")
    command = tuple(_os.fspath(part) for part in command)
    if not command:
        raise ValueError("Command cannot be empty")
    return command


@_dataclasses.dataclass(frozen=True)
class CommandResult:
    """Raw argv/cwd/returncode/stdout/stderr; nonzero statuses are preserved.

    stdout and stderr are bytes; a negative POSIX status denotes a signal.
    No product-specific success rule is applied.
    """

    args: tuple
    cwd: str
    returncode: int
    stdout: bytes
    stderr: bytes

    def text(self, channel, *, encoding="utf-8"):
        """Return strictly decoded stdout or stderr at any exit status.

        Invalid channel raises ValueError; decoding failure raises HelperError.
        """
        if channel not in ("stdout", "stderr"):
            raise ValueError("Channel must be stdout or stderr")
        try:
            return getattr(self, channel).decode(encoding)
        except UnicodeError as exc:
            raise HelperError("Cannot decode output channel: " + channel) from exc

    def json(self, channel):
        """Return the complete channel parsed as JSON, regardless of status.

        Decode/parse errors raise; logs are never stripped to guess JSON bounds.
        """
        return parse_json(self.text(channel))


def environment(base, *, updates=None, remove=()):
    """Return a copied environment with explicit edits; no process/status.

    No ambient environment is implicitly inherited or mutated. Invalid input
    raises; removing a key already absent has no effect.
    """
    result = dict(base)
    for key in remove:
        result.pop(key, None)
    if updates is not None:
        result.update(updates)
    return result


@_contextlib.contextmanager
def isolated_directories(*, parent=None):
    """Yield root/home/project Paths in a fresh temporary root, then clean up.

    Does not initialize the product or detect profiles. IO/cleanup errors raise;
    there is no product exit status. All state belongs only to this scope.
    """
    with _tempfile.TemporaryDirectory(dir=parent, prefix="suite-") as directory:
        root = _Path(directory)
        home, project = root / "home", root / "project"
        home.mkdir()
        project.mkdir()
        yield {"root": root, "home": home, "project": project}


def write_file(path, content):
    """Write caller bytes or UTF-8 text, returning Path; IO errors raise.

    Creates parents, without product invocation or status interpretation.
    """
    path = _Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_bytes(content)
    return path


def read_bytes(path):
    """Return exact file bytes; missing/unreadable files raise HelperError.

    No missing-file sentinel or product exit status is returned.
    """
    try:
        return _Path(path).read_bytes()
    except OSError as exc:
        raise HelperError(f"Cannot read file: {path}") from exc


def parse_json(data):
    """Return a complete parsed JSON value; invalid input raises HelperError.

    JSON null is preserved, not used as an error sentinel. No status inference.
    """
    try:
        return _json.loads(data)
    except (ValueError, UnicodeError, TypeError) as exc:
        raise HelperError("Cannot parse JSON document") from exc


def read_json(path):
    """Return parsed JSON from the exact file; IO/parse errors raise.

    Does not infer status from file existence, document content or filename.
    """
    return parse_json(read_bytes(path))


def field(document, *keys):
    """Return explicitly supplied nested keys/indices; missing paths raise.

    HelperError preserves the underlying lookup cause. No defaults or product
    exit-status interpretation are applied.
    """
    try:
        for key in keys:
            document = document[key]
        return document
    except (KeyError, IndexError, TypeError) as exc:
        raise HelperError(f"Cannot read field path: {keys!r}") from exc


def graph_nodes(report, *, reference, context):
    """Return all nodes matching exact public ref/context fields, not node IDs.

    Empty match is an observation; missing fields or malformed nodes raise.
    This accessor does not decide product success or expect a node count.
    """
    nodes = field(report, "graph", "nodes")
    if not isinstance(nodes, dict):
        raise HelperError("graph.nodes must be a JSON object")
    return [node for node in nodes.values()
            if field(node, "ref") == reference and field(node, "context") == context]


def repository_report(report):
    """Return full repository JSON, preserving every revision/error hierarchy.

    Non-object input raises HelperError. Empty data and reported errors are
    never conflated or converted into success; exit status is not inferred.
    """
    if not isinstance(report, dict):
        raise HelperError("Repository report must be a JSON object")
    return report


def classify_report(report, *, status_path, states):
    """Return a caller-defined label for an explicitly published status value.

    states maps documented field values to labels (e.g. empty/missing/error).
    Missing/unknown/unhashable values raise; no generic nonzero-exit rule or
    guessed diagnostic schema is imposed.
    """
    value = field(report, *status_path)
    try:
        return states[value]
    except (KeyError, TypeError) as exc:
        raise HelperError(f"Unknown published report status: {value!r}") from exc


def _kill_owned(process):
    if _os.name == "posix":
        try:
            _os.killpg(process.pid, _signal.SIGKILL)
        except ProcessLookupError:
            pass  # The exact owned group has already exited.
    elif process.poll() is None:
        process.kill()


def run(command, *, cwd, env, stdin=b"", timeout=COMMAND_TIMEOUT):
    """Return CommandResult for a bounded public CLI invocation at any status.

    Explicit argv, cwd and complete env are required. stdin is bytes or UTF-8
    text followed by EOF. Launch/IO/timeout errors raise HelperError with cause
    and captured diagnostics. Both streams are fully consumed, including JSONL.
    No shell, profile detection, setup or automatic retry is performed.
    """
    args = _argv(command)
    _timeout(timeout)
    if isinstance(stdin, str):
        stdin = stdin.encode("utf-8")
    if not isinstance(stdin, bytes):
        raise TypeError("stdin must be bytes or text")
    try:
        with _tempfile.TemporaryFile() as out, _tempfile.TemporaryFile() as err:
            process = _subprocess.Popen(
                args, cwd=cwd, env=dict(env), stdin=_subprocess.PIPE,
                stdout=out, stderr=err, start_new_session=(_os.name == "posix"))
            try:
                process.communicate(stdin, timeout=timeout)
            except _subprocess.TimeoutExpired as exc:
                _kill_owned(process)
                process.wait(timeout=5)
                out.seek(0)
                err.seek(0)
                raise HelperError(f"Command timed out: {args!r}; "
                                  f"stdout={out.read()!r}; stderr={err.read()!r}") from exc
            finally:
                _kill_owned(process)
            out.seek(0)
            err.seek(0)
            return CommandResult(args, str(cwd), process.returncode, out.read(), err.read())
    except (OSError, _subprocess.TimeoutExpired) as exc:
        raise HelperError(f"Cannot execute/clean up command: {args!r}") from exc


def json_lines(result, channel):
    """Return every parsed record from an explicitly JSONL output channel.

    Empty stream returns an empty list. Blank/malformed records raise, never
    disappear; result.returncode remains the caller's separate observation.
    """
    return [parse_json(line) for line in result.text(channel).splitlines()]


@_dataclasses.dataclass(frozen=True)
class Client:
    """Independent CLI binding; command, cwd and full env are caller-supplied.

    Does not install settings, remotes or credentials. run returns any completed
    status; accessors raise when they cannot obtain the requested observation.
    """

    command: tuple
    cwd: object
    env: dict

    def run(self, *args, stdin=b"", timeout=COMMAND_TIMEOUT):
        """Return CommandResult at any exit status; machinery failures raise."""
        return run((*_argv(self.command), *args), cwd=self.cwd, env=self.env,
                   stdin=stdin, timeout=timeout)

    def cache_path(self, reference, *, folder=None, timeout=COMMAND_TIMEOUT):
        """Return artifact Path from public cache path JSON's cache_path field.

        A nonzero locator status, invalid JSON or missing path field raises.
        For negative-path tests use run to retain the complete failing result.
        No internal directory layout or file-existence expectation is used.
        """
        args = ["cache", "path", reference, "--format=json"]
        if folder is not None:
            args.extend(["--folder", folder])
        result = self.run(*args, timeout=timeout)
        if result.returncode != 0:
            raise HelperError(f"Cannot locate artifact: {result!r}")
        value = field(result.json("stdout"), "cache_path")
        if not isinstance(value, str) or not value:
            raise HelperError("cache_path must be a nonempty string")
        path = _Path(value)
        return path if path.is_absolute() else _Path(self.cwd) / path


def file_bytes(root, relative_paths):
    """Return selected relative names mapped to exact independently read bytes.

    Missing files or paths escaping root raise; no product-generated expected
    values or behavioral comparisons are made. No exit status applies.
    """
    root = _Path(root).resolve()
    result = {}
    for name in relative_paths:
        path = (root / name).resolve()
        if path != root and root not in path.parents:
            raise HelperError(f"File escapes observation root: {name}")
        result[str(name)] = read_bytes(path)
    return result


@_contextlib.contextmanager
def unavailable_paths(paths):
    """Yield while caller-owned original paths are absent, then restore them.

    Renames only explicitly supplied paths. Missing paths, collisions and restore
    failures raise. This prevents lookup by original location, not discovery by
    a hostile process. Keep delivered archives outside these paths. No status
    interpretation or product cache-layout knowledge is involved.
    """
    paths = tuple(_Path(path).absolute() for path in paths)
    moved = []
    with _tempfile.TemporaryDirectory(prefix="suite-isolation-") as token:
        try:
            for original in paths:
                parked = original.with_name(original.name + "." + _Path(token).name)
                if parked.exists():
                    raise HelperError(f"Isolation destination exists: {parked}")
                original.rename(parked)
                moved.append((original, parked))
            yield paths
        finally:
            for original, parked in reversed(moved):
                if original.exists():
                    raise HelperError(f"Original path recreated: {original}")
                parked.rename(original)


class ServiceProcess:
    """Owned real service process with bounded lifecycle and raw capture.

    No container management or fabricated responses. Launch/cleanup failures
    raise; snapshot preserves any service exit status without interpretation.
    """

    def __init__(self, name, command, *, cwd, env):
        """Start explicitly named argv; launch errors raise with original cause."""
        if not name:
            raise ValueError("Service must have an explicit name")
        self.name = name
        self._out = _tempfile.TemporaryFile()
        self._err = _tempfile.TemporaryFile()
        try:
            self._process = _subprocess.Popen(
                _argv(command), cwd=cwd, env=dict(env), stdin=_subprocess.DEVNULL,
                stdout=self._out, stderr=self._err,
                start_new_session=(_os.name == "posix"))
        except BaseException:
            self._out.close()
            self._err.close()
            raise

    def snapshot(self):
        """Return current status (None while live) and separate raw byte streams.

        IO errors raise; no success or readiness inference is performed.
        """
        def _capture(stream):
            # Independent read handle leaves the service writer offset intact.
            if hasattr(_os, "pread"):
                return _os.pread(stream.fileno(), _os.fstat(stream.fileno()).st_size, 0)
            if self._process.poll() is None:
                raise HelperError("Live capture requires pread on this platform")
            stream.seek(0)
            return stream.read()
        return {"returncode": self._process.poll(),
                "stdout": _capture(self._out), "stderr": _capture(self._err)}

    def wait_ready(self, probe, *, timeout=SERVICE_READY_TIMEOUT, interval=0.05):
        """Return first truthy caller probe result; early exit/deadline raises.

        probe receives remaining seconds and must bound its IO accordingly.
        False means pending; probe exceptions propagate unchanged, never retry.
        Does not guess readiness from logs or a particular HTTP status.
        """
        deadline = _time.monotonic() + _timeout(timeout)
        _timeout(interval)
        while True:
            if self._process.poll() is not None:
                raise HelperError(f"Service exited before readiness: {self.name}: {self.snapshot()!r}")
            remaining = deadline - _time.monotonic()
            if remaining <= 0:
                raise HelperError(f"Service readiness timed out: {self.name}: {self.snapshot()!r}")
            result = probe(remaining)
            if _time.monotonic() >= deadline:
                raise HelperError(f"Readiness probe exceeded deadline: {self.name}")
            if result:
                return result
            _time.sleep(min(interval, max(0, deadline - _time.monotonic())))

    def close(self, *, timeout=5):
        """Stop only this owned group and return final raw status/output.

        Bounded cleanup failures raise; cleanup signal status is not a product
        behavior assertion. This method is called once by service_process.
        """
        _timeout(timeout)
        _kill_owned(self._process)
        try:
            self._process.wait(timeout=timeout)
            return self.snapshot()
        except _subprocess.TimeoutExpired as exc:
            raise HelperError(f"Cannot stop service: {self.name}") from exc
        finally:
            self._out.close()
            self._err.close()


@_contextlib.contextmanager
def service_process(name, command, *, cwd, env, probe, timeout=SERVICE_READY_TIMEOUT):
    """Yield a ready real service, then stop only its exact owned process group.

    Caller supplies public service argv/configuration and readiness probe.
    Launch/readiness/cleanup failures raise. Read raw status via snapshot.
    """
    service = ServiceProcess(name, command, cwd=cwd, env=env)
    try:
        service.wait_ready(probe, timeout=timeout)
        yield service
    finally:
        service.close()


class CommunicationRecorder:
    """Transparent observer around a caller-supplied public HTTP transport.

    The transport must return its real response; request does not replace or
    mutate it. Capture must consume/restore bodies according to that transport's
    documented API. This class makes no unadvertised product transport binding.
    For CLI traffic use a real recording proxy started through service_process,
    then read its published JSON records with read_json/json_lines.
    """

    def __init__(self, transport, capture):
        """Bind transport/capture callables; return no status or network result.

        capture(request,response) must return an observation with raw bytes and
        published HTTP status; errors propagate, never fabricated records.
        """
        self._transport = transport
        self._capture = capture
        self._records = []
        self._lock = _threading.Lock()
        self._next = 0

    @property
    def records(self):
        """Return immutable snapshot of correlated observations; no filtering.

        Each item is (local request identity, caller-captured observation).
        Transport errors raise and cannot appear as successful empty responses.
        """
        with self._lock:
            return tuple(self._records)

    def request(self, request, *, timeout):
        """Return the real response unchanged; transport/capture errors raise.

        transport(request, timeout=seconds) must enforce this complete deadline;
        timeout is finite and explicit. HTTP error statuses remain responses.
        No retry, response substitution or status interpretation is performed.
        """
        _timeout(timeout)
        with self._lock:
            identity = self._next
            self._next += 1
        started = _time.monotonic()
        response = self._transport(request, timeout=timeout)
        observation = self._capture(request, response)
        if _time.monotonic() - started > timeout:
            raise HelperError("Transport/capture exceeded deadline")
        with self._lock:
            self._records.append((identity, observation))
        return response
