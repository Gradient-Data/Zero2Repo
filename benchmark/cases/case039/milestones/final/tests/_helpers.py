# feature: F00
"""Shared transport and data utilities; product expectations belong in tests.

Commands are argument vectors, never shell scripts. Paths, build commands,
decoders, and result consumers are supplied by callers. Native API adapters
belong in the feature helpers; this module defines no database wire protocol.
"""

import collections as _collections
import contextlib as _contextlib
import csv as _csv
import dataclasses as _dataclasses
import decimal as _decimal
import io as _io
import json as _json
import math as _math
import os as _os
import pathlib as _pathlib
import signal as _signal
import subprocess as _subprocess
import tempfile as _tempfile
import time as _time

__all__ = [
    "ProcessResult", "InvocationTimeout", "run_command", "build_artifact",
    "locate_artifact", "isolated_directory", "make_environment",
    "record_process", "capture_result", "parse_json", "parse_json_lines",
    "parse_csv", "typed_key", "typed_equal", "rows_equal", "tied_rows_equal",
]


@_dataclasses.dataclass(frozen=True)
class ProcessResult:
    """Raw process observation, including nonzero status without raising.

    stdout and stderr are bytes; returncode is the native subprocess status
    (negative for a POSIX signal). elapsed is monotonic wall time in seconds.
    Launch and transport failures never produce a ProcessResult.
    """

    command: tuple
    cwd: str
    stdout: bytes
    stderr: bytes
    returncode: int
    elapsed: float


class InvocationTimeout(AssertionError):
    """Transport deadline failure, never a product timeout result.

    result holds the observation after forced termination, including captured
    output and termination status. The original TimeoutExpired is the cause.
    """

    def __init__(self, result, timeout):
        """Create a failure retaining raw output; returns None, not a status."""
        self.result = result
        self.timeout = timeout
        super().__init__(f"Command exceeded {timeout}s: {result.command!r}; "
                         f"stdout={result.stdout!r}; stderr={result.stderr!r}")


def make_environment(updates=None, *, base=None):
    """Return a copied environment with explicit updates; None removes a key.

    base=None copies the current environment. No global environment is changed;
    invalid key/value types raise TypeError. There is no process exit status.
    """
    result = dict(_os.environ if base is None else base)
    for name, value in ({} if updates is None else updates).items():
        if not isinstance(name, str):
            raise TypeError("Environment names must be strings")
        if value is None:
            result.pop(name, None)
        elif isinstance(value, str):
            result[name] = value
        else:
            raise TypeError("Environment values must be strings or None")
    return result


@_contextlib.contextmanager
def isolated_directory(*, parent=None, prefix="suite-"):
    """Yield a fresh Path and remove only that directory on context exit.

    Creation and cleanup errors propagate; no process status is involved.
    Callers must finish owned processes before leaving the context.
    """
    with _tempfile.TemporaryDirectory(dir=parent, prefix=prefix) as directory:
        yield _pathlib.Path(directory)


def run_command(command, *, cwd, timeout, input_bytes=b"", env=None):
    """Return ProcessResult with separate byte streams and any exit status.

    command is a nonempty argument sequence, cwd is explicit, timeout is finite
    positive seconds, and env is a full environment (None inherits). stdin is
    closed after input_bytes, including for empty input. No shell is used.
    Launch/I/O errors propagate. A deadline kills this invocation's POSIX
    process group and raises InvocationTimeout from TimeoutExpired. Cleanup
    has its own five-second bound; cleanup failure raises instead of returning
    an incomplete observation. This runner requires POSIX process groups.
    """
    if _os.name != "posix":
        raise RuntimeError("This runner requires POSIX process groups")
    if isinstance(command, (str, bytes)):
        raise TypeError("command must be an argument sequence")
    args = tuple(_os.fspath(part) for part in command)
    if not args:
        raise ValueError("command must not be empty")
    if not _math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    if not isinstance(input_bytes, bytes):
        raise TypeError("input_bytes must be bytes")
    directory = str(_pathlib.Path(cwd).resolve(strict=True))
    started = _time.monotonic()
    process = _subprocess.Popen(
        args, cwd=directory, env=env, stdin=_subprocess.PIPE,
        stdout=_subprocess.PIPE, stderr=_subprocess.PIPE,
        start_new_session=True,
    )
    try:
        try:
            stdout, stderr = process.communicate(input_bytes, timeout=timeout)
        except _subprocess.TimeoutExpired as error:
            _kill_group(process)
            stdout, stderr = process.communicate(timeout=5)
            result = ProcessResult(args, directory, stdout, stderr,
                                   process.returncode, _time.monotonic() - started)
            raise InvocationTimeout(result, timeout) from error
        return ProcessResult(args, directory, stdout, stderr,
                             process.returncode, _time.monotonic() - started)
    finally:
        if process.poll() is None:
            _kill_group(process)
            process.wait(timeout=5)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


def _kill_group(process):
    try:
        _os.killpg(process.pid, _signal.SIGKILL)
    except ProcessLookupError:
        # The owned group already exited between the deadline and kill.
        pass


def locate_artifact(path, *, root, executable=False):
    """Return the resolved explicit file path; never search or choose a build.

    Relative paths use root. Missing files, nonfiles, or requested executable
    access failures raise; there is no process status or fallback artifact.
    """
    path = _pathlib.Path(path)
    if not path.is_absolute():
        path = _pathlib.Path(root) / path
    path = path.resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"Artifact is not a file: {path}")
    if executable and not _os.access(path, _os.X_OK):
        raise PermissionError(f"Artifact is not executable: {path}")
    return path


def build_artifact(command, *, cwd, artifact, timeout, env=None, executable=False):
    """Run an explicit build and return (artifact Path, raw ProcessResult).

    Nonzero build status raises CalledProcessError with both byte streams;
    launch/deadline/artifact errors propagate. Use a fresh isolated build
    directory when freshness is required; no cache or alternate build is chosen.
    """
    result = run_command(command, cwd=cwd, timeout=timeout, env=env)
    if result.returncode != 0:
        raise _subprocess.CalledProcessError(
            result.returncode, result.command, result.stdout, result.stderr)
    return locate_artifact(artifact, root=cwd, executable=executable), result


def record_process(result, directory):
    """Write exact streams and JSON invocation metadata; return directory Path.

    directory must not exist. Status is recorded unchanged, not interpreted;
    filesystem/serialization errors propagate. Environment secrets are omitted.
    """
    directory = _pathlib.Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "stdout.bin").write_bytes(result.stdout)
    (directory / "stderr.bin").write_bytes(result.stderr)
    metadata = {"command": [_os.fsdecode(a) for a in result.command],
                "cwd": result.cwd, "returncode": result.returncode,
                "elapsed": result.elapsed}
    (directory / "process.json").write_text(
        _json.dumps(metadata, ensure_ascii=True, indent=2), encoding="utf-8")
    return directory


def capture_result(invoke, consume):
    """Return consume(invoke()), keeping invocation and full reading together.

    Both callbacks are caller supplied. consume must fully materialize lazy
    results and preserve metadata/types/errors from the public API. Exceptions
    from either callback propagate unchanged to the same caller error boundary;
    returned public error/status values are not interpreted or replaced.
    """
    return consume(invoke())


def _reject_constant(value):
    raise ValueError(f"Non-JSON numeric constant: {value}")


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Ambiguous duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def parse_json(document):
    """Return parsed JSON with exact int and Decimal numbers and null as None.

    Arrays retain order and duplicates. Invalid JSON, ambiguous duplicate object
    keys and non-JSON numeric constants raise. No schema or exit status is inferred.
    """
    return _json.loads(document, parse_float=_decimal.Decimal,
                       parse_constant=_reject_constant,
                       object_pairs_hook=_object_pairs)


def parse_json_lines(document):
    """Return one parsed value per JSON line, preserving order and precision.

    Bytes are decoded as strict UTF-8; empty input yields no records. Blank or
    malformed record lines raise; a final newline is allowed. No status is inferred.
    """
    if isinstance(document, bytes):
        document = document.decode("utf-8")
    return [parse_json(line) for line in document.splitlines()]


def parse_csv(document, *, dialect="excel", **options):
    """Return CSV records as lists of strings, including any header record.

    Bytes use strict UTF-8. csv.reader handles quoting and embedded newlines;
    parse errors propagate. No header, missing marker, type or status is guessed.
    """
    if isinstance(document, bytes):
        document = document.decode("utf-8")
    return list(_csv.reader(_io.StringIO(document, newline=""),
                            dialect=dialect, strict=True, **options))


def typed_key(value):
    """Return a hashable structural key retaining Python scalar/container types.

    None, bool, int and numeric types remain distinct. Mapping order is ignored;
    sequence order is retained. Unsupported unhashable values raise TypeError;
    this transformation makes no product assertion and has no exit status.
    """
    if isinstance(value, dict):
        payload = frozenset((typed_key(k), typed_key(v)) for k, v in value.items())
    elif isinstance(value, (list, tuple)):
        payload = tuple(typed_key(v) for v in value)
    else:
        hash(value)
        payload = value
    return type(value), payload


def typed_equal(left, right):
    """Return structural type-sensitive equality; unsupported values raise.

    No coercion, tolerance, product expectation or exit status is supplied.
    """
    return typed_key(left) == typed_key(right)


def rows_equal(left, right, *, ordered):
    """Return type-sensitive sequence or multiset equality, selected by caller.

    Duplicate multiplicities are preserved. No sorting/order guarantee is
    inferred; invalid values or iteration errors propagate, not False/status.
    """
    left = [typed_key(row) for row in left]
    right = [typed_key(row) for row in right]
    if ordered:
        return left == right
    return _collections.Counter(left) == _collections.Counter(right)


def tied_rows_equal(left, right, *, key):
    """Return equality allowing permutations only within consecutive equal keys.

    key is caller supplied and must include every ordering expression. Group
    sequence is compared as supplied, never sorted; each group is a multiset.
    Callback/type/iteration errors propagate. No product rule/status is assumed.
    """
    def groups(rows):
        result = []
        for row in rows:
            group_key = typed_key(key(row))
            if not result or result[-1][0] != group_key:
                result.append((group_key, _collections.Counter()))
            result[-1][1][typed_key(row)] += 1
        return result
    return groups(left) == groups(right)
