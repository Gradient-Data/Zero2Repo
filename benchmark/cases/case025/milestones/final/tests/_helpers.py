# feature: F00
"""Shared transport and observation helpers; feature tests own all expectations.

Entry points, recognized exit statuses, report paths and format-specific readers
are supplied by callers. No missing report is interpreted as an empty report.
The working product remains importable through the inherited environment; this
module never changes sys.path or installs dependencies. Temporary project paths
must be explicitly passed as CLI targets/import roots where needed.
"""

import ast as _ast
import contextlib as _contextlib
import dataclasses as _dataclasses
import importlib.metadata as _metadata
import json as _json
import math as _math
import os as _os
import pathlib as _pathlib
import platform as _platform
import signal as _signal
import subprocess as _subprocess
import sys as _sys
import tempfile as _tempfile


__all__ = [
    "RunResult", "HarnessError", "run_command", "run_cli", "probe_entry",
    "workspace", "write_files", "run_pair", "read_text", "read_json",
    "read_report", "records_at", "source_positions", "parse_type_display",
    "environment_info", "verify_dependencies",
]


@_dataclasses.dataclass(frozen=True)
class RunResult:
    """Return command, absolute cwd, integer returncode and complete text streams.

    Nonzero recognized exit statuses are data, not success or failure verdicts.
    Launch errors, signals, timeouts and unrecognized statuses raise HarnessError
    instead of producing this result. Output is decoded strictly as UTF-8.
    """

    command: tuple[str, ...]
    cwd: _pathlib.Path
    returncode: int
    stdout: str
    stderr: str


class HarnessError(RuntimeError):
    """Raise for transport/observation failures; never represents a product answer.

    ``result`` holds a completed RunResult when available. Chained exceptions
    retain original OS, decoding, parsing or timeout details.
    """

    def __init__(self, message, *, result=None):
        """Initialize an exception, returning None; retain optional process evidence."""
        self.result = result
        if result is not None:
            message += (
                f"\ncommand={result.command!r}\ncwd={str(result.cwd)!r}"
                f"\nreturncode={result.returncode}"
                f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        super().__init__(message)


def run_command(command, *, cwd, allowed_returncodes, input_text=None,
                env=None, timeout=30.0):
    """Return RunResult from an argv sequence, without a shell.

    ``allowed_returncodes`` explicitly lists statuses the caller can interpret;
    all other statuses and signal exits raise HarnessError with captured output.
    ``env`` overlays the inherited environment; None values remove named keys.
    stdin is UTF-8 text, or immediate EOF when omitted. All waits are bounded.
    Launch, timeout and decoding failures raise with their original cause.
    On POSIX a timed-out process group is killed, including its descendants.
    """
    if isinstance(command, (str, bytes)):
        raise TypeError("command must be an argv sequence")
    argv = tuple(_os.fspath(arg) for arg in command)
    if not argv:
        raise ValueError("command must not be empty")
    if not _math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be positive and finite")
    statuses = frozenset(allowed_returncodes)
    if not statuses or any(type(code) is not int or code < 0 for code in statuses):
        raise ValueError("allowed_returncodes must contain nonnegative integers")
    directory = _pathlib.Path(cwd).resolve(strict=True)
    child_env = _os.environ.copy()
    for key, value in ({} if env is None else env).items():
        if value is None:
            child_env.pop(key, None)
        else:
            child_env[key] = value
    payload = None if input_text is None else input_text.encode("utf-8")
    try:
        process = _subprocess.Popen(
            argv, cwd=directory, env=child_env, stdin=_subprocess.PIPE,
            stdout=_subprocess.PIPE, stderr=_subprocess.PIPE,
            start_new_session=(_os.name == "posix"),
        )
    except OSError as exc:
        raise HarnessError(f"Cannot launch {argv!r} in {str(directory)!r}") from exc
    try:
        stdout, stderr = process.communicate(payload, timeout=timeout)
    except _subprocess.TimeoutExpired as exc:
        try:
            if _os.name == "posix":
                _os.killpg(process.pid, _signal.SIGKILL)
            else:
                process.kill()
            stdout, stderr = process.communicate(timeout=5.0)
        except (OSError, _subprocess.TimeoutExpired) as cleanup_exc:
            process.stdin.close()
            process.stdout.close()
            process.stderr.close()
            raise HarnessError(
                f"Command timed out after {timeout}s: {argv!r}; "
                f"cleanup failed: {cleanup_exc!r}; "
                f"stdout={exc.output!r}; stderr={exc.stderr!r}"
            ) from exc
        raise HarnessError(
            f"Command timed out after {timeout}s: {argv!r}; "
            f"stdout={stdout!r}; stderr={stderr!r}"
        ) from exc
    try:
        result = RunResult(argv, directory, process.returncode,
                           stdout.decode("utf-8"), stderr.decode("utf-8"))
    except UnicodeError as exc:
        raise HarnessError(
            f"Cannot decode output from {argv!r}; returncode={process.returncode}; "
            f"stdout={stdout!r}; stderr={stderr!r}"
        ) from exc
    if result.returncode not in statuses:
        raise HarnessError("Unrecognized process exit status", result=result)
    return result


def run_cli(module, args=(), *, cwd, allowed_returncodes, python=None,
            input_text=None, env=None, timeout=30.0):
    """Return RunResult for ``python -m module`` with the supplied CLI arguments.

    Uses this interpreter unless ``python`` is explicitly supplied. Files,
    directories, multiple targets, inline input and configuration are expressed
    in ``args`` exactly as the public CLI specifies. Error/status semantics are
    those of run_command; no product module is imported by this helper.
    """
    if isinstance(args, (str, bytes)):
        raise TypeError("args must be an argv sequence")
    executable = _sys.executable if python is None else _os.fspath(python)
    return run_command(
        [executable, "-m", module, *args], cwd=cwd,
        allowed_returncodes=allowed_returncodes, input_text=input_text,
        env=env, timeout=timeout,
    )


def probe_entry(command, *, cwd, allowed_returncodes, env=None, timeout=10.0):
    """Return a bounded entry-point probe's RunResult, or raise as run_command.

    The caller supplies a documented probe command and interpretable statuses.
    This establishes invocation only; feature activity must be asserted by the
    feature test using a triggering input and its observed results.
    """
    return run_command(command, cwd=cwd, allowed_returncodes=allowed_returncodes,
                       env=env, timeout=timeout)


def write_files(root, files):
    """Return relative-name to absolute-Path mappings for written project files.

    ``files`` maps relative paths to exact UTF-8 text or bytes; no dedenting or
    newline conversion is performed. Absolute paths and escapes from root are
    rejected. Filesystem/type errors propagate; no process status is involved.
    """
    directory = _pathlib.Path(root).resolve(strict=True)
    paths = {}
    for name, content in files.items():
        relative = _pathlib.Path(name)
        path = (directory / relative).resolve()
        if relative.is_absolute() or path == directory or directory not in path.parents:
            raise ValueError(f"File path must stay inside workspace: {name!r}")
        if not isinstance(content, (str, bytes)):
            raise TypeError(f"File content must be text or bytes: {name!r}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
        paths[name] = path
    return paths


@_contextlib.contextmanager
def workspace(files=None, *, parent=None):
    """Yield a fresh absolute project Path and remove it on context exit.

    Optional relative files are created by write_files. File creation, caller
    and cleanup errors propagate; there is no subprocess or exit status here.
    The process's own cwd and environment are never modified.
    """
    with _tempfile.TemporaryDirectory(prefix="suite-", dir=parent) as name:
        root = _pathlib.Path(name).resolve()
        write_files(root, {} if files is None else files)
        yield root


def run_pair(files, first, second, *, parent=None):
    """Return two callback results from independently rebuilt identical projects.

    Each callback receives its own workspace Path and must read needed artifacts
    before returning. Results, including RunResult statuses, are not compared.
    Exceptions propagate; the second arm is not substituted for a failed first
    arm. Callbacks must use bounded runners. Paths expire on callback completion.
    """
    initial = dict(files)
    with workspace(initial, parent=parent) as root:
        first_result = first(root)
    with workspace(initial, parent=parent) as root:
        second_result = second(root)
    return first_result, second_result


def read_text(path, *, result=None):
    """Return exact UTF-8 file text; missing/unreadable/invalid files raise.

    HarnessError chains the original error and includes optional RunResult
    evidence. The supplied process status is preserved, never reinterpreted.
    """
    try:
        return _pathlib.Path(path).read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise HarnessError(f"Cannot read output file {str(path)!r}", result=result) from exc


def read_report(path, parser, *, result=None):
    """Return parser(UTF-8 file text), preserving its format-specific structure.

    Requires an explicit parser for formats without a shared published grammar.
    Read/parse errors raise HarnessError with the original cause and optional
    process evidence; neither missing output nor parse failure becomes a value.
    """
    text = read_text(path, result=result)
    try:
        return parser(text)
    except Exception as exc:
        raise HarnessError(f"Cannot parse output file {str(path)!r}", result=result) from exc


def _reject_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}")


def read_json(path, *, result=None):
    """Return the JSON document without imposing a diagnostic schema.

    Missing files, invalid UTF-8 and malformed JSON (including nonfinite number
    constants) raise HarnessError, retaining the cause and optional RunResult.
    A valid JSON null remains None; it is never converted to an empty collection.
    """
    return read_report(path, lambda text: _json.loads(
        text, parse_constant=_reject_constant), result=result)


def records_at(records, **fields):
    """Return records whose directly named fields equal every supplied value.

    Field names and location units come from the caller's public contract. No
    path normalization, sorting or text guessing is performed. Missing queried
    fields raise KeyError, malformed records raise TypeError; no match returns
    an empty list for the test to interpret. Exit status is not consulted.
    """
    selected = []
    for record in records:
        values = {key: record[key] for key in fields}
        if values == fields:
            selected.append(record)
    return selected


def source_positions(source, node_type, *, filename="<source>"):
    """Return AST locations for nodes of the caller-supplied public AST class.

    Tuples are (lineno, col_offset, end_lineno, end_col_offset): lines are
    one-based and columns are zero-based UTF-8 byte offsets, as in Python AST.
    Syntax/type/missing-location errors propagate; no matches yields an empty
    list. This parses input source only and makes no inference or status claim.
    """
    tree = _ast.parse(source, filename=filename)
    return [(node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)
            for node in _ast.walk(tree) if isinstance(node, node_type)]


def parse_type_display(text, parser):
    """Return a caller-supplied public type-grammar parser's result.

    No type grammar is assumed without an interface contract. The parser must
    consume the display and raise on malformed input. Exceptions are chained
    into HarnessError; there is no process exit status or type comparison here.
    """
    try:
        return parser(text)
    except Exception as exc:
        raise HarnessError(f"Cannot parse public type display: {text!r}") from exc


def environment_info():
    """Return actual interpreter, version, platform and implementation metadata.

    Describes the current test interpreter, also run_cli's default interpreter.
    Errors propagate; no product process or exit status is involved. Version
    applicability decisions belong to callers and are not implicit skips.
    """
    return {
        "executable": _sys.executable,
        "version": tuple(_sys.version_info),
        "platform": _sys.platform,
        "implementation": _sys.implementation.name,
        "implementation_version": _platform.python_version(),
    }


def verify_dependencies(locked_versions):
    """Return installed distribution versions after checking caller-supplied pins.

    Keys are distribution names and values exact version strings. Missing
    dependencies or pin mismatches raise HarnessError, never skip a test. These
    are environment checks, not product outcomes; no process status is involved.
    """
    actual = {}
    for name, expected in locked_versions.items():
        try:
            actual[name] = _metadata.version(name)
        except _metadata.PackageNotFoundError as exc:
            raise HarnessError(f"Required distribution is missing: {name}") from exc
        if actual[name] != expected:
            raise HarnessError(
                f"Distribution {name!r}: expected {expected!r}, found {actual[name]!r}"
            )
    return actual
