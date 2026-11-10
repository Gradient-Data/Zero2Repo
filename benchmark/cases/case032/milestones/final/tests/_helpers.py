# feature: F00
"""Product-agnostic helpers for driving public test entry points."""

from __future__ import annotations

import contextlib
import io
import json
import math
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import threading
import warnings
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Mapping, Sequence


_DEFAULT_TIMEOUT = 60.0


@dataclass(frozen=True)
class ProcessResult:
    """Captured child result: return code, stdout, and stderr."""

    returncode: int
    stdout: bytes
    stderr: bytes

    @property
    def exit_status(self) -> int:
        """Return the child's numeric exit status."""
        return self.returncode

    @property
    def stdout_text(self) -> str:
        """Decode captured standard output as UTF-8, raising on invalid data."""
        return self.stdout.decode("utf-8")

    @property
    def stderr_text(self) -> str:
        """Decode captured standard error as UTF-8, raising on invalid data."""
        return self.stderr.decode("utf-8")


def configure_cpu_environment(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return an environment configured for local CPU and double precision execution."""
    result = dict(os.environ if env is None else env)
    result["JAX_PLATFORM_NAME"] = "cpu"
    result["JAX_PLATFORMS"] = "cpu"
    result["JAX_ENABLE_X64"] = "1"
    return result


@contextlib.contextmanager
def temporary_environment(
    values: Mapping[str, str | None],
) -> Iterator[dict[str, str]]:
    """Yield the effective temporary environment; restore it on exit, propagating errors.

    Set numerical options before importing the numerical backend. Environment
    changes do not reconfigure an already initialized backend.
    """
    old = os.environ.copy()
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)
        yield dict(os.environ)
    finally:
        os.environ.clear()
        os.environ.update(old)


@contextlib.contextmanager
def temporary_directory(**kwargs: Any) -> Iterator[pathlib.Path]:
    """Create a temporary directory and remove it when the context exits."""
    with tempfile.TemporaryDirectory(**kwargs) as name:
        yield pathlib.Path(name)


def _materialize(value: Any) -> Any:
    """Synchronously materialize array-like values, preserving ordinary Python objects."""
    block = getattr(value, "block_until_ready", None)
    if callable(block):
        block()
        return value
    if isinstance(value, Mapping):
        for item in value.values():
            _materialize(item)
    if isinstance(value, tuple):
        for item in value:
            _materialize(item)
    if isinstance(value, list):
        for item in value:
            _materialize(item)
    return value


@contextlib.contextmanager
def deadline(seconds: float) -> Iterator[None]:
    """Yield within a Linux main-thread time budget; timeout raises TimeoutError.

    Existing timers are refused rather than overwritten. Native computations
    may delay Python signal handling; use run_python for a hard process bound.
    """
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("timeout must be finite and positive")
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("in-process deadlines require the main thread")
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise RuntimeError("an existing real-time timer is active")

    def expired(signum: int, frame: Any) -> None:
        raise TimeoutError("public call exceeded its time budget")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def call_public(
    function: Callable[..., Any], /, *args: Any,
    timeout: float = _DEFAULT_TIMEOUT,
    consume: Callable[[Any], Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Return a public call's value after waiting for array leaves; errors propagate.

    Optional consume performs caller-defined observation inside the same error
    and time scope, and its evaluated return value becomes the result. Supply
    construction and the requested operation together in function when checking
    rejection. Use a closure for product keywords named timeout or consume.
    """
    with deadline(timeout):
        result = _materialize(function(*args, **kwargs))
        return _materialize(consume(result)) if consume is not None else result


@dataclass
class CapturedOutput:
    """Live captured text streams and warning records; call errors still propagate."""

    stdout: io.StringIO
    stderr: io.StringIO
    warnings: list[Any]


@contextlib.contextmanager
def capture_output() -> Iterator[CapturedOutput]:
    """Yield Python stdout/stderr buffers and warnings, retaining them even on errors.

    Exceptions are never converted into results. Use child process capture for
    native file-descriptor output; this context captures Python text writes.
    """
    stdout, stderr = io.StringIO(), io.StringIO()
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            yield CapturedOutput(stdout, stderr, records)


def invoke(function: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    """Alias of call_public with identical return and error semantics."""
    return call_public(function, *args, **kwargs)


def run_process(
    command: Sequence[os.PathLike[str] | str],
    *,
    input_data: bytes | str | None = None,
    cwd: os.PathLike[str] | str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> ProcessResult:
    """Run a public command with captured streams; launch, timeout, and I/O errors raise, while nonzero status is returned."""
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    data = input_data.encode("utf-8") if isinstance(input_data, str) else input_data
    completed = subprocess.run(
        [os.fspath(part) for part in command],
        input=data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.fspath(cwd) if cwd is not None else os.getcwd(),
        env=dict(env) if env is not None else configure_cpu_environment(),
        timeout=timeout,
        check=False,
    )
    return ProcessResult(completed.returncode, completed.stdout, completed.stderr)


def run_python(
    source: str, *, executable: os.PathLike[str] | str = sys.executable,
    input_data: bytes | str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
    check: bool = True,
) -> ProcessResult:
    """Execute caller-supplied Python in an isolated CPU-configured child at product cwd.

    Source must use plain imports of documented public entries. Setup precedes
    all imports. By default nonzero status raises CalledProcessError containing
    both raw streams; check=False exposes it for explicit failure-path tests.
    Launch and timeout errors always propagate with their original details.
    """
    result = run_process(
        [executable, "-c", source], input_data=input_data,
        env=configure_cpu_environment(env), timeout=timeout,
    )
    if check and result.returncode:
        raise subprocess.CalledProcessError(
            result.returncode, [os.fspath(executable), "-c", source],
            output=result.stdout, stderr=result.stderr,
        )
    return result


def run_command(*args: Any, **kwargs: Any) -> ProcessResult:
    """Alias of run_process; nonzero child status remains available on the returned result."""
    return run_process(*args, **kwargs)


def parse_json(data: str | bytes | bytearray) -> Any:
    """Parse a complete JSON document and return its decoded value; malformed input raises."""
    return json.loads(data)


def read_json(path: os.PathLike[str] | str) -> Any:
    """Read and parse a JSON file using the JSON parser; read or parse errors raise."""
    with pathlib.Path(path).open("r", encoding="utf-8") as stream:
        return json.load(stream)


def read_text(path: os.PathLike[str] | str) -> str:
    """Read a UTF-8 text file completely; filesystem and decoding errors raise."""
    return pathlib.Path(path).read_text(encoding="utf-8")


def read_array(value: Any) -> Any:
    """Return a host NumPy array after waiting for the supplied value; conversion errors propagate."""
    import numpy as np

    return np.asarray(_materialize(value))


def read_field(value: Mapping[str, Any], name: str) -> Any:
    """Read an explicitly named mapping field and wait for its leaves; missing fields raise KeyError."""
    return _materialize(value[name])


def read_label(text: str, label: str, *, separator: str = ":") -> str:
    """Return the sole line value with an exact caller-specified label and separator.

    Surrounding whitespace is ignored. Missing or duplicate labels raise
    ValueError; unrelated lines remain uninterpreted. This reads a documented
    label/value format, not tables or arbitrary numeric text.
    """
    if not separator or not label:
        raise ValueError("label and separator must be nonempty")
    values = []
    for line in text.splitlines():
        key, found, value = line.partition(separator)
        if found and key.strip() == label:
            values.append(value.strip())
    if len(values) != 1:
        raise ValueError(f"expected one value for label {label!r}, found {len(values)}")
    return values[0]


def copy_environment(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return a mutable copy of an environment with CPU numerical settings applied."""
    return configure_cpu_environment(env)
