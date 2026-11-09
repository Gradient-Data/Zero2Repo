# feature: F00
"""Shared transport and build machinery; no product expectations live here.

Feature helpers supply public package names, feature flags, ABI declarations,
and thin driver source. Drivers must serialize public results with a real JSON
serializer, including explicit error/absence fields, and consume lazy results
inside their error boundary. This module never interprets those fields.

Each Driver invocation starts a fresh process. To reuse an object, submit the
entire sequence of operations in one request and implement it in that driver.
C driver source receives ``library`` (a ctypes.CDLL), ``bind_c_function``, and
``ctypes`` as globals, and reads stdin/writes stdout normally. Native calls and
result consumption therefore happen within the parent's bounded process run.
"""

from __future__ import annotations

import contextlib as _contextlib
import ctypes as _ctypes
import dataclasses as _dataclasses
import json as _json
import math as _math
import os as _os
from pathlib import Path as _Path
import runpy as _runpy
import signal as _signal
import subprocess as _subprocess
import sys as _sys
import tempfile as _tempfile


class HelperError(AssertionError):
    """Raise for observation failures, never a product answer or a test skip.

    ``result`` retains captured process output/status when available; ``cause``
    retains an underlying exception. No exit status is invented on launch errors.
    """

    def __init__(self, message, *, result=None, cause=None):
        self.result = result
        self.cause = cause
        if result is not None:
            message += (f"\ncommand: {result.command!r}\nexit: {result.returncode}"
                        f"\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}")
        if cause is not None:
            message += f"\ncause: {cause!r}"
        super().__init__(message)


class InterfaceUnavailable(HelperError):
    """Raise for missing/ambiguous build interfaces; no product value is returned.

    This is a handoff failure, not evidence for a feature's semantic outcome.
    Inherits the original diagnostics and optional process result from HelperError.
    """


class MeasurementBlocked(HelperError):
    """Raise when a caller cannot establish measurement prerequisites.

    No timing conclusion, success, or skip is returned. The caller supplies raw
    records in the message and may attach the original result/cause.
    """


@_dataclasses.dataclass(frozen=True)
class ProcessResult:
    """Return a command's raw stdout/stderr bytes and actual integer returncode.

    Ordinary nonzero exits are observable when checking is disabled. Signals,
    timeouts and launch failures raise HelperError instead of returning an answer.
    """

    command: tuple[str, ...]
    returncode: int
    stdout: bytes
    stderr: bytes


@_dataclasses.dataclass(frozen=True)
class JsonResult:
    """Return parsed JSON in ``value`` and its ProcessResult in ``process``.

    Product error/absence fields remain unchanged. Nonzero exit, malformed JSON,
    timeout and transport failures raise rather than creating a JSON result.
    """

    value: object
    process: ProcessResult


def environment(updates=None, *, base=None):
    """Return a copied environment with updates; a None value removes a key.

    With no base, inherit the current environment. Never mutate global state;
    invalid mappings raise their original exceptions. There is no exit status.
    """
    values = dict(_os.environ if base is None else base)
    for key, value in ({} if updates is None else updates).items():
        if value is None:
            values.pop(key, None)
        else:
            values[key] = value
    return values


@_contextlib.contextmanager
def temporary_workspace(*, parent=None):
    """Yield a temporary Path, removing it at context exit, including on failure.

    File/cleanup errors propagate unchanged; this context has no process status.
    Callers can instead supply pytest's temporary directory to build helpers.
    """
    with _tempfile.TemporaryDirectory(prefix="suite-driver-", dir=parent) as path:
        yield _Path(path)


def _positive_timeout(timeout):
    if not _math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")


def run_process(command, *, input_bytes=b"", cwd=None, env=None,
                timeout=30.0, check=False):
    """Return ProcessResult with byte streams; never invoke a command shell.

    ``env`` is a complete environment (None inherits); use environment() for
    overlays. ``check=False`` exposes ordinary exit codes, including nonzero.
    Launch failure, signal termination and timeout always raise HelperError;
    ``check=True`` also raises on a nonzero exit. Timeout cleanup is bounded to
    five seconds and kills only the new process group created by this call.
    """
    _positive_timeout(timeout)
    if isinstance(command, (str, bytes)) or not command:
        raise ValueError("command must be a nonempty argument sequence")
    argv = tuple(_os.fsdecode(part) for part in command)
    if not isinstance(input_bytes, bytes):
        raise TypeError("input_bytes must be bytes")
    try:
        process = _subprocess.Popen(
            argv, cwd=cwd, env=env, stdin=_subprocess.PIPE,
            stdout=_subprocess.PIPE, stderr=_subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        raise HelperError(f"Cannot launch {argv!r}", cause=exc) from exc
    try:
        stdout, stderr = process.communicate(input_bytes, timeout=timeout)
    except BaseException as exc:
        # The session belongs to this invocation, never to a discovered process.
        try:
            _os.killpg(process.pid, _signal.SIGKILL)
        except ProcessLookupError:
            pass  # Exiting between timeout and cleanup is a normal race.
        try:
            stdout, stderr = process.communicate(timeout=5.0)
        except _subprocess.TimeoutExpired as cleanup:
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()
            raise HelperError(
                f"Cleanup exceeded its deadline for {argv!r}; "
                f"initial failure: {exc!r}", cause=cleanup,
            ) from exc
        result = ProcessResult(argv, process.returncode, stdout, stderr)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise HelperError("Process communication failed or exceeded its deadline",
                          result=result, cause=exc) from exc
    result = ProcessResult(argv, process.returncode, stdout, stderr)
    if process.returncode < 0 or (check and process.returncode != 0):
        raise HelperError("Process did not complete successfully", result=result)
    return result


def _reject_constant(value):
    raise ValueError(f"Non-JSON numeric constant: {value}")


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def _decode_json(data, process):
    try:
        return _json.loads(data, parse_constant=_reject_constant,
                           object_pairs_hook=_object_pairs)
    except (ValueError, UnicodeError) as exc:
        raise HelperError("Cannot parse JSON output", result=process,
                          cause=exc) from exc


def run_json(command, request, *, cwd=None, env=None, timeout=30.0):
    """Send one JSON value on stdin and return JsonResult for the whole stdout.

    Stderr is retained, never parsed for answers. Nonzero exit or malformed JSON
    raises HelperError. Unserializable requests raise their original exception;
    successful JSON, including explicit product errors or null, is not rewritten.
    """
    payload = (_json.dumps(request, ensure_ascii=True, allow_nan=False) + "\n").encode()
    result = run_process(command, input_bytes=payload, cwd=cwd, env=env,
                         timeout=timeout, check=True)
    return JsonResult(_decode_json(result.stdout, result), result)


@_dataclasses.dataclass(frozen=True)
class Driver:
    """Describe a real subprocess entry point; construction does not execute it.

    ``run`` returns raw process status; ``json`` returns parsed JSON plus status.
    Both raise on transport failures, and json also raises on nonzero exit.
    """

    command: tuple[str, ...]
    cwd: _Path
    env: object = None

    def run(self, input_bytes=b"", *, timeout=30.0, check=True):
        """Return ProcessResult; raise on transport errors or checked exit failure."""
        return run_process(self.command, input_bytes=input_bytes, cwd=self.cwd,
                           env=self.env, timeout=timeout, check=check)

    def json(self, request, *, timeout=30.0):
        """Return JsonResult; raise on nonzero exit, protocol or transport errors."""
        return run_json(self.command, request, cwd=self.cwd, env=self.env,
                        timeout=timeout)


def cargo_metadata(manifest, *, cargo="cargo", env=None, timeout=120.0):
    """Return JsonResult from Cargo's version-1, no-dependencies metadata API.

    The caller supplies the root manifest and Cargo executable. Nonzero exit,
    invalid JSON, launch and timeout failures raise with original diagnostics.
    """
    manifest = _Path(manifest).resolve(strict=True)
    result = run_process(
        [cargo, "metadata", "--format-version", "1", "--no-deps",
         "--manifest-path", str(manifest)],
        cwd=manifest.parent, env=env, timeout=timeout, check=True,
    )
    return JsonResult(_decode_json(result.stdout, result), result)


def _package(metadata, package):
    try:
        matches = [item for item in metadata.value["packages"]
                   if item["name"] == package
                   and item["id"] in metadata.value["workspace_members"]]
    except (KeyError, TypeError) as exc:
        raise HelperError("Invalid Cargo metadata structure",
                          result=metadata.process, cause=exc) from exc
    if len(matches) != 1:
        raise InterfaceUnavailable(
            f"Expected one workspace package named {package!r}, found {len(matches)}",
            result=metadata.process,
        )
    return matches[0]


@_dataclasses.dataclass(frozen=True)
class CargoBuild:
    """Return Cargo metadata, parsed build messages and successful process output.

    No product behavior is interpreted. Build failures raise before construction;
    artifact lookup raises on missing/ambiguous metadata rather than guessing paths.
    """

    metadata: JsonResult
    messages: tuple
    process: ProcessResult

    def artifact(self, package, *, kind, target=None, executable=False, suffix=None):
        """Return one existing artifact Path selected by Cargo's named fields.

        ``kind`` selects a target kind or crate type (e.g. bin or cdylib).
        ``executable`` reads the explicit executable field; otherwise read filenames.
        Dynamic-library requests select loadable library files from the target's
        outputs, which can also include Rust libraries or linker sidecars.
        Optional target/suffix disambiguate outputs. Missing/ambiguous outputs raise
        InterfaceUnavailable; malformed messages/filesystem errors are never values.
        """
        package_id = _package(self.metadata, package)["id"]
        paths = set()
        try:
            for message in self.messages:
                if message["reason"] != "compiler-artifact":
                    continue
                info = message["target"]
                if message["package_id"] != package_id:
                    continue
                if kind not in info["kind"] and kind not in info["crate_types"]:
                    continue
                if target is not None and info["name"] != target:
                    continue
                candidates = ([message["executable"]] if executable
                              else message["filenames"])
                for candidate in candidates:
                    # Cargo reports all crate types of a target together. A
                    # cdylib target may also emit an rlib, import library, or
                    # debug sidecar; none is the library ctypes can load.
                    if (candidate is not None and kind == "cdylib"
                            and _Path(candidate).suffix not in (".so", ".dylib", ".dll")):
                        continue
                    if candidate is not None and (suffix is None or candidate.endswith(suffix)):
                        paths.add(_Path(candidate))
        except (KeyError, TypeError, AttributeError) as exc:
            raise HelperError("Invalid Cargo artifact message",
                              result=self.process, cause=exc) from exc
        if len(paths) != 1:
            raise InterfaceUnavailable(
                f"Expected one artifact for {package!r}/{kind}, found {sorted(map(str, paths))}",
                result=self.process,
            )
        path = paths.pop().resolve(strict=True)
        if not path.is_file():
            raise HelperError(f"Cargo artifact is not a file: {path}", result=self.process)
        return path


def cargo_build(manifest, *, target_dir, package=None, features=(),
                bin_name=None, release=True, cargo="cargo", env=None, timeout=300.0):
    """Build a caller-selected Cargo entry and return CargoBuild, including logs.

    All outputs go to target_dir; Cargo may write its lockfile beside the supplied
    manifest. Feature flags/package names are caller-owned, never inferred from
    internal directories. Metadata and build each have the supplied finite timeout.
    Build, JSON or transport failures raise; no stale artifact substitutes success.
    """
    manifest = _Path(manifest).resolve(strict=True)
    target_dir = _Path(target_dir).resolve()
    metadata = cargo_metadata(manifest, cargo=cargo, env=env, timeout=timeout)
    command = [cargo, "build", "--manifest-path", str(manifest),
               "--target-dir", str(target_dir), "--message-format=json"]
    if package is not None:
        _package(metadata, package)
        command += ["--package", package]
    if bin_name is not None:
        command += ["--bin", bin_name]
    if release:
        command.append("--release")
    if features:
        command += ["--features", ",".join(features)]
    process = run_process(command, cwd=manifest.parent, env=env,
                          timeout=timeout, check=True)
    messages = tuple(_decode_json(line, process)
                     for line in process.stdout.splitlines() if line.strip())
    return CargoBuild(metadata, messages, process)


def build_rust_driver(directory, source, *, product_manifest, package,
                      features=(), dependency_name=None, dependencies_toml="",
                      cargo="cargo", env=None, timeout=300.0):
    """Write/build caller-provided Rust source; return an executable Driver.

    directory must not exist and is owned/cleaned by the caller. Product package
    location comes from Cargo metadata, never an internal path. dependency_name
    optionally renames the dependency; dependencies_toml supplies extra entries
    within [dependencies], such as a real JSON serializer. Source must call public
    exports. Filesystem errors propagate; build/interface/transport errors raise.
    """
    metadata = cargo_metadata(product_manifest, cargo=cargo, env=env, timeout=timeout)
    product = _package(metadata, package)
    product_dir = _Path(product["manifest_path"]).parent
    directory = _Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "src").mkdir()
    quote = _json.dumps
    dependency = package if dependency_name is None else dependency_name
    manifest = (
        '[package]\nname = "suite-driver"\nversion = "0.0.0"\nedition = "2021"\n'
        '[workspace]\n[dependencies]\n'
        f'{quote(dependency)} = {{ package = {quote(package)}, '
        f'path = {quote(str(product_dir))}, features = {quote(list(features))} }}\n'
        + dependencies_toml + '\n'
    )
    (directory / "Cargo.toml").write_text(manifest, encoding="utf-8")
    (directory / "src" / "main.rs").write_text(source, encoding="utf-8")
    build = cargo_build(directory / "Cargo.toml", target_dir=directory / "target",
                        package="suite-driver", bin_name="suite-driver",
                        cargo=cargo, env=env, timeout=timeout)
    executable = build.artifact("suite-driver", kind="bin", executable=True)
    return Driver((str(executable),), directory, env)


def bind_c_function(library, name, *, argtypes, restype):
    """Return a ctypes function with the caller's exact public ABI declaration.

    Used inside C driver workers; this operation binds but does not call native
    code. Missing symbols raise InterfaceUnavailable. Null pointers, counts and
    error fields from later calls are not interpreted here; workers encode them.
    """
    try:
        function = getattr(library, name)
    except AttributeError as exc:
        raise InterfaceUnavailable(f"Missing public C symbol {name!r}", cause=exc) from exc
    function.argtypes = list(argtypes)
    function.restype = restype
    return function


def build_c_driver(directory, source, *, library, python=None, env=None):
    """Write a ctypes worker and return a Driver; no native call happens here.

    directory must not exist; the caller owns its cleanup. library is the exact
    artifact path, preferably from CargoBuild.artifact. Source binds the published
    ABI, invokes it, consumes results and serializes output in the worker. Worker
    load/binding failures yield nonzero exits and are raised by Driver.json/run;
    timeout and crashes always raise. File errors here propagate unchanged.
    """
    library = _Path(library).resolve(strict=True)
    directory = _Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    script = directory / "driver.py"
    script.write_text(source, encoding="utf-8")
    executable = _sys.executable if python is None else _os.fspath(python)
    return Driver((executable, str(_Path(__file__).resolve()), "--c-worker",
                   str(library), str(script)), directory, env)


def _c_worker(library, script):
    loaded = _ctypes.CDLL(library)
    _runpy.run_path(script, run_name="__main__", init_globals={
        "library": loaded, "ctypes": _ctypes, "bind_c_function": bind_c_function,
    })


if __name__ == "__main__":
    if len(_sys.argv) != 4 or _sys.argv[1] != "--c-worker":
        raise SystemExit("Usage: _helpers.py --c-worker LIBRARY DRIVER_SOURCE")
    _c_worker(_sys.argv[2], _sys.argv[3])
