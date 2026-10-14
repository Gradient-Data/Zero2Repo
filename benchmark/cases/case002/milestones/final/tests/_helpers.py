"""Pipeline-owned sealed test helpers.

This file is the complete module. Import what you need (`from _helpers import ...`). Add a new helper here, with the imports and constants it closes over. Do not paste a sealed body into a feature file. Do not change a sealed name unless you own it and that feature's PRD was amended.
"""

from __future__ import annotations

import logging
import os
import stat
import sys
import uuid
import zipapp
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from typing import Any

from envfile import envfile_values, find_envfile, get_key, load_envfile, set_key, unset_key

from _harness import (
    CallResult,
    HarnessError,
    RunResult,
    Workspace,
    call,
    file_mode,
    product_package_dir,
    product_package_name,
    repo_root,
    run_command,
    run_python,
)

# Expansion is specified in a later feature. Format observations turn it off
# through the public knob already present on the load / values-mapping entries.
_WITHOUT_EXPANSION = False


def unique_token() -> str:
    """Alphanumeric fragment safe as a binding name or value."""
    return "k" + uuid.uuid4().hex[:12]


def _mapping_from_call(result: CallResult, *, label: str) -> Mapping[str, Any]:
    if result.exception is not None:
        raise HarnessError(f"{label} raised {result.exception!r}")
    mapping = result.value
    if not isinstance(mapping, Mapping):
        raise HarnessError(
            f"{label} did not return a mapping; got {type(mapping)!r}: {mapping!r}"
        )
    return mapping


def bindings_from_text(text: str) -> Mapping[str, Any]:
    """Parse *text* through the values-mapping entry with expansion off.

    Uses an in-memory stream. A product exception or a non-mapping return is
    a harness failure — never an empty mapping meaning "no bindings".
    """
    result = call(
        envfile_values,
        stream=StringIO(text),
        interpolate=_WITHOUT_EXPANSION,
    )
    return _mapping_from_call(result, label="values-mapping(stream)")


def bindings_from_file(path: str | Path) -> Mapping[str, Any]:
    """Parse the file at *path* through the values-mapping entry, expansion off."""
    result = call(
        envfile_values,
        envfile_path=str(path),
        interpolate=_WITHOUT_EXPANSION,
    )
    return _mapping_from_call(result, label=f"values-mapping(file={path!s})")


def require_binding(mapping: Mapping[str, Any], name: str) -> Any:
    """Return the recorded value for *name*. Assert if the name is absent."""
    assert name in mapping, (
        f"{name!r} is not in the mapping; keys={list(mapping)!r}"
    )
    recorded = mapping[name]
    print(f"binding {name!r}={recorded!r}", flush=True)
    return recorded


def require_absent(mapping: Mapping[str, Any], name: str) -> None:
    """Assert *name* is not a binding in *mapping*."""
    assert name not in mapping, (
        f"{name!r} contributed a binding {mapping[name]!r}; keys={list(mapping)!r}"
    )
    print(f"absent {name!r}", flush=True)


def require_empty_string(mapping: Mapping[str, Any], name: str) -> str:
    """Assert *name* is present with the empty string (not no-value, not absent)."""
    recorded = require_binding(mapping, name)
    assert recorded == "", (
        f"{name!r} recorded {recorded!r}, not the empty string"
    )
    return recorded


def require_no_value(mapping: Mapping[str, Any], name: str) -> Any:
    """Assert *name* is present and is not the empty string.

    Absence is not no-value. The recorded marker is not pinned to a language
    sentinel; the Interface Contract states only that it is not a ``str``.
    """
    assert name in mapping, (
        f"{name!r} is absent (not a no-value binding); keys={list(mapping)!r}"
    )
    recorded = mapping[name]
    assert not isinstance(recorded, str), (
        f"{name!r} recorded text {recorded!r}, not the no-value marker"
    )
    print(f"no-value {name!r} recorded={recorded!r}", flush=True)
    return recorded


def require_not_two_char_escape(value: object, letter: str) -> None:
    """Assert *value* is not the two-character literal backslash+*letter*."""
    if not isinstance(value, str):
        raise HarnessError(
            f"escape observation is not text; got {type(value)!r}: {value!r}"
        )
    if len(letter) != 1:
        raise HarnessError(f"letter must be one character; got {letter!r}")
    literal = "\\" + letter
    assert value != literal, (
        f"parsed value is the two-character literal {literal!r}"
    )
    print(f"escape letter={letter!r} value={value!r} is not {literal!r}", flush=True)


def require_script_success(result: RunResult, *, label: str) -> str:
    """Return stdout after a successful child script.

    A non-zero exit is an observation failure — never empty text meaning
    "not found" or "no bindings".
    """
    if result.returncode != 0:
        raise HarnessError(
            f"{label} exited {result.returncode}; "
            f"stderr={result.stderr_text!r}; stdout={result.stdout_text!r}"
        )
    print(f"{label} stdout={result.stdout_text!r}", flush=True)
    return result.stdout_text


def require_labeled_line(text: str, label: str, *, origin: str) -> str:
    """Return the suffix of the last ``label=...`` line in *text*.

    A missing label is an observation failure, not an empty suffix.
    """
    prefix = label + "="
    matches = [
        line[len(prefix) :]
        for line in text.splitlines()
        if line.startswith(prefix)
    ]
    if not matches:
        raise HarnessError(f"{origin} has no {label!r} line; stdout={text!r}")
    recorded = matches[-1]
    print(f"{origin} {label}={recorded!r}", flush=True)
    return recorded


def load_text(text: str) -> CallResult:
    """Load *text* from an in-memory stream with expansion off.

    Returns the ``CallResult``. A product exception is left on the result for
    the test to classify. Harness/timeout failures already raise.
    """
    return call(
        load_envfile,
        stream=StringIO(text),
        interpolate=_WITHOUT_EXPANSION,
    )


def require_utf8_text(data: bytes, *, origin: str) -> str:
    """Decode *data* as UTF-8.

    Invalid UTF-8 is an observation failure — never a replacement, never an
    empty string meaning "could not decode".
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HarnessError(f"{origin} is not UTF-8: {data!r} ({exc})") from exc
    print(f"{origin} utf-8 text={text!r}", flush=True)
    return text


def write_binding(path: str | Path, name: str, value: str) -> CallResult:
    """Write one binding through the file-write entry without naming an encoding."""
    result = call(set_key, str(path), name, value)
    if result.exception is not None:
        raise HarnessError(
            f"file-write of {name!r} to {path!s} raised {result.exception!r}"
        )
    print(f"file-write {name!r}={value!r} path={path!s}", flush=True)
    return result


def load_path(path: str | Path) -> CallResult:
    """Load the file or FIFO at *path* with expansion off.

    FIFO sources must go through this helper (the load entry), not a
    pre-read-then-stream workaround.
    """
    return call(
        load_envfile,
        envfile_path=str(path),
        interpolate=_WITHOUT_EXPANSION,
    )


def run_without_product(code: str) -> RunResult:
    """Run *code* in a child interpreter where the product is not importable.

    ``include_product=False`` drops the source tree from ``PYTHONPATH``. This
    recipe also editable-installs the package into site-packages, so the child
    is started with ``-S`` (no site) and that path scrub together. A harness
    or timeout failure still raises; a non-zero child exit is returned.
    """
    return run_python(argv=["-S", "-c", code], include_product=False)


def environ_value(result: CallResult, name: str) -> str:
    """Return *name* from ``result.environ``.

    A product exception is not a successful lookup. Absence is
    ``name not in result.environ`` at the call site, never a ``None`` return.
    """
    if result.exception is not None:
        raise HarnessError(
            f"load raised {result.exception!r}; cannot read {name!r} from environ"
        )
    if name not in result.environ:
        raise HarnessError(
            f"{name!r} is absent from the process environment; "
            f"keys={sorted(result.environ)!r}"
        )
    recorded = result.environ[name]
    print(f"environ {name!r}={recorded!r}", flush=True)
    return recorded


def locate_call(*args: Any, **kwargs: Any) -> CallResult:
    """Locate a file through the public file-location entry.

    A product exception is left on the result. It is never turned into
    empty text meaning "not found". Pass ``cwd=`` and ``isolate=False``
    (with a workspace environment) when the start is a prepared tree.
    """
    return call(find_envfile, *args, **kwargs)


def located_text(result: CallResult, *, origin: str) -> str:
    """Return the located path text from a successful location call.

    A product exception or a non-text return is an observation failure.
    Empty text is a legal "not found" value.
    """
    if result.exception is not None:
        raise HarnessError(f"{origin} raised {result.exception!r}")
    value = result.value
    if not isinstance(value, str):
        raise HarnessError(
            f"{origin} did not return text; got {type(value)!r}: {value!r}"
        )
    print(f"{origin} located={value!r}", flush=True)
    return value


def located_from_script(result: RunResult, *, label: str) -> str:
    """Return the ``FOUND=`` suffix after a successful child script.

    A non-zero exit or a missing label is an observation failure, never
    an empty path meaning "not found".
    """
    stdout = require_script_success(result, label=label)
    return require_labeled_line(stdout, "FOUND", origin=label)


def require_same_path(found: str, expected: Path, *, origin: str) -> Path:
    """Assert *found* is the same filesystem path as *expected* after resolve."""
    assert found, f"{origin} returned empty text; expected {expected}"
    try:
        resolved_found = Path(found).resolve()
        resolved_expected = Path(expected).resolve()
    except OSError as exc:
        raise AssertionError(
            f"{origin} cannot resolve {found!r} or {expected!s}: {exc}"
        ) from exc
    assert resolved_found == resolved_expected, (
        f"{origin} located {resolved_found}, not {resolved_expected}"
    )
    print(f"{origin} path={resolved_found}", flush=True)
    return resolved_found


def require_empty_located_text(found: str, *, origin: str) -> str:
    """Assert location returned empty text (no path), not a pretended path."""
    assert found == "", f"{origin} expected empty text, got {found!r}"
    print(f"{origin} empty located text", flush=True)
    return found


def run_frozen_packaged_executable(
    source: str,
    *,
    bundle_dir: Path,
    cwd: Path,
    env: Mapping[str, str],
) -> RunResult:
    """Launch *source* as a frozen packaged executable.

    Calling code is bundled under *bundle_dir* (not *cwd*). The process
    is started as that packaged executable, not as ordinary
    interpreter-and-script execution. The helper constructs this process
    class the way a freeze-tool bootloader does; the suite does not
    assert a detection attribute.
    """
    bundle_dir = Path(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    src_dir = bundle_dir / unique_token()
    src_dir.mkdir()
    # Freeze-tool bootloaders mark the packaged process before user code.
    # This only constructs the process class.
    (src_dir / "__main__.py").write_text(
        "import sys\nsys.frozen = True\n" + source,
        encoding="utf-8",
    )
    packaged = bundle_dir / unique_token()
    zipapp.create_archive(
        str(src_dir),
        str(packaged),
        interpreter=sys.executable,
    )
    os.chmod(packaged, 0o755)
    print(
        f"frozen-packaged executable={packaged} bundle={src_dir} cwd={cwd}",
        flush=True,
    )
    return run_command([str(packaged)], cwd=cwd, env=dict(env))


def require_call_completed(result: CallResult, *, origin: str) -> CallResult:
    """Require that the library call returned to the caller.

    A product exception is an aborted caller, not a classified failure
    report. It is never turned into a success/failure value.
    """
    if result.exception is not None:
        raise HarnessError(
            f"{origin} aborted the caller: {result.exception!r}"
        )
    print(f"{origin} completed value={result.value!r}", flush=True)
    return result


def require_environ_absent(result: CallResult, name: str) -> None:
    """Assert *name* is not in the process environment after a completed call.

    A product exception is not absence. Observation failure raises.
    """
    require_call_completed(result, origin=f"absent {name!r}")
    assert name not in result.environ, (
        f"{name!r} was written {result.environ[name]!r}; "
        f"keys={sorted(result.environ)!r}"
    )
    print(f"environ absent {name!r}", flush=True)


def require_surviving_caller_unchanged(
    name: str,
    before: Mapping[str, str],
    *,
    origin: str,
) -> None:
    """Assert *name* in this process environment matches *before*.

    After a public ``run`` that delivered *name* to a child, run must not
    write that name into the surviving caller's process environment (it
    is not the load entry). Presence is ``name in os.environ``; a missing
    name is not turned into a sentinel value.
    """
    before_present = name in before
    after_present = name in os.environ
    before_val = before[name] if before_present else None
    after_val = os.environ[name] if after_present else None
    print(
        f"{origin} surviving caller {name!r} "
        f"before_present={before_present} before={before_val!r} "
        f"after_present={after_present} after={after_val!r}",
        flush=True,
    )
    assert after_present == before_present and after_val == before_val, (
        f"{origin} wrote {name!r} into the surviving caller's process "
        f"environment: before present={before_present} value={before_val!r}; "
        f"after present={after_present} value={after_val!r}"
    )


def load_reports_differ(
    success: CallResult,
    failure: CallResult,
    *,
    origin: str,
) -> None:
    """Require two completed load reports to be distinguishable.

    Does not pin the success or failure marker to a language boolean.
    """
    require_call_completed(success, origin=f"{origin} success")
    require_call_completed(failure, origin=f"{origin} failure")
    assert success.value != failure.value, (
        f"{origin} success and failure reports are indistinguishable: "
        f"{success.value!r}"
    )
    print(
        f"{origin} success_report={success.value!r} "
        f"failure_report={failure.value!r}",
        flush=True,
    )


def diagnostics_text(
    result: CallResult,
    log_records: Sequence[logging.LogRecord],
) -> str:
    """Join captured log messages, warnings, stderr, and stdout.

    Used as a contrast observation, not as a golden message. A decode
    failure on stderr/stdout raises — it is not treated as silence.
    """
    parts: list[str] = [record.getMessage() for record in log_records]
    parts.extend(str(warning.message) for warning in result.warnings)
    if result.stderr:
        parts.append(result.stderr_text)
    if result.stdout:
        parts.append(result.stdout_text)
    text = "\n".join(parts)
    print(f"diagnostics={text!r}", flush=True)
    return text


def strip_path_covariates(text: str, paths: Sequence[str | Path]) -> str:
    """Remove str and resolve() spellings of *paths* from *text*.

    The result is for contrast. It is never interpreted as 'no diagnostic'.
    """
    variants: list[str] = []
    for path in paths:
        variants.append(str(path))
        try:
            variants.append(str(Path(path).resolve()))
        except OSError:
            pass
    stripped = text
    for variant in sorted(set(variants), key=len, reverse=True):
        if variant:
            stripped = stripped.replace(variant, "")
    print(f"stripped diagnostics={stripped!r}", flush=True)
    return stripped



@contextmanager
def _capture_all_loggers(records: list[logging.LogRecord]):
    """Collect records from the root logger and from every non-propagating logger.

    The Contract allows any logger name, so a product logger with
    ``propagate=False`` is captured too. Each record is kept once.
    """

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if not any(r is record for r in records):
                records.append(record)

    handler = _ListHandler()
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    targets: list[logging.Logger] = [root]
    saved: list[tuple[logging.Logger, int]] = []
    try:
        for logger in list(logging.Logger.manager.loggerDict.values()):
            if isinstance(logger, logging.Logger) and not logger.propagate:
                targets.append(logger)
        for logger in targets:
            try:
                logger.addHandler(handler)
            except Exception as exc:
                raise HarnessError(f"cannot attach log handler: {exc}") from exc
            saved.append((logger, logger.level))
            logger.setLevel(logging.DEBUG)
        yield
    finally:
        for logger, level in saved:
            logger.removeHandler(handler)
            logger.setLevel(level)
        handler.close()

def load_with_log_capture(*args: Any, **kwargs: Any) -> tuple[CallResult, list[logging.LogRecord]]:
    """Call the load entry with a memory handler on the root logger.

    Records from every logger are kept (root plus non-propagating
    loggers). Handler install failure raises. The handler is always detached.
    """
    records: list[logging.LogRecord] = []
    with _capture_all_loggers(records):
        result = call(load_envfile, *args, **kwargs)
    print(f"captured {len(records)} log records", flush=True)
    return result, records


class TrackingStream(StringIO):
    """In-memory text stream that records whether it was read."""

    consumed: bool

    def __init__(self, value: str) -> None:
        super().__init__(value)
        self.consumed = False

    def _mark_consumed(self) -> None:
        self.consumed = True

    def read(self, *args: Any, **kwargs: Any) -> str:
        self._mark_consumed()
        return super().read(*args, **kwargs)

    def readline(self, *args: Any, **kwargs: Any) -> str:
        self._mark_consumed()
        return super().readline(*args, **kwargs)

    def readlines(self, *args: Any, **kwargs: Any) -> list[str]:
        self._mark_consumed()
        return super().readlines(*args, **kwargs)

    def __iter__(self):
        self._mark_consumed()
        return super().__iter__()


def read_tracking_stream(text: str) -> TrackingStream:
    """Return a text stream that records whether it was read, iterated, or readline'd.

    A product exception is not evidence the stream was unread; classify
    the exception at the call site. ``consumed`` starts false.
    """
    stream = TrackingStream(text)
    print(f"tracking stream created consumed={stream.consumed}", flush=True)
    return stream


def require_mapping(result: CallResult, *, origin: str) -> Mapping[str, Any]:
    """Require a completed values-mapping call that returned a mapping.

    A product exception is an aborted caller, not an empty mapping.
    A non-mapping return is an observation failure, never ``{}``.
    """
    require_call_completed(result, origin=origin)
    mapping = result.value
    if not isinstance(mapping, Mapping):
        raise HarnessError(
            f"{origin} did not return a mapping; got {type(mapping)!r}: {mapping!r}"
        )
    print(f"{origin} mapping keys={list(mapping)!r}", flush=True)
    return mapping


def require_empty_mapping(result: CallResult, *, origin: str) -> Mapping[str, Any]:
    """Require a completed call that returned a mapping with zero bindings.

    Empty means zero keys, not a sentinel and not a swallowed exception.
    """
    mapping = require_mapping(result, origin=origin)
    assert len(mapping) == 0, (
        f"{origin} expected an empty mapping; got keys={list(mapping)!r} "
        f"values={dict(mapping)!r}"
    )
    print(f"{origin} empty mapping", flush=True)
    return mapping


def call_with_log_capture(
    fn: Any,
    *args: Any,
    **kwargs: Any,
) -> tuple[CallResult, list[logging.LogRecord]]:
    """Call a public entry with a memory handler on the root logger.

    Records from every logger are kept (root plus non-propagating
    loggers). Handler install failure raises. The handler is always detached.
    """
    records: list[logging.LogRecord] = []
    with _capture_all_loggers(records):
        result = call(fn, *args, **kwargs)
    print(f"captured {len(records)} log records", flush=True)
    return result, records


def write_one(path: str | Path, name: str, value: str, **kwargs: Any) -> CallResult:
    """Write one binding through the file-write entry.

    Extra keywords are forwarded to the write entry. A product exception
    is left on the result for the caller to classify.
    """
    result = call(set_key, str(path), name, value, **kwargs)
    print(
        f"write-one name={name!r} value={value!r} path={path!s} "
        f"exception={result.exception!r} report={result.value!r}",
        flush=True,
    )
    return result


def read_one(path: str | Path, name: str, **kwargs: Any) -> CallResult:
    """Read one name through the file-read entry.

    Extra keywords are forwarded to the read entry. A product exception
    is left on the result for the caller to classify.
    """
    result = call(get_key, str(path), name, **kwargs)
    print(
        f"read-one name={name!r} path={path!s} "
        f"exception={result.exception!r} report={result.value!r}",
        flush=True,
    )
    return result


def delete_one(path: str | Path, name: str, **kwargs: Any) -> CallResult:
    """Delete one name through the file-delete entry.

    Extra keywords are forwarded to the delete entry. A product exception
    is left on the result for the caller to classify.
    """
    result = call(unset_key, str(path), name, **kwargs)
    print(
        f"delete-one name={name!r} path={path!s} "
        f"exception={result.exception!r} report={result.value!r}",
        flush=True,
    )
    return result


def require_text_value(result: CallResult, expected: str, *, origin: str) -> str:
    """Require a completed read that returned exactly *expected* text."""
    require_call_completed(result, origin=origin)
    value = result.value
    assert isinstance(value, str), (
        f"{origin} did not return text; got {type(value)!r}: {value!r}"
    )
    assert value == expected, (
        f"{origin} returned {value!r}, not {expected!r}"
    )
    print(f"{origin} text value={value!r}", flush=True)
    return value


def require_no_text_value(result: CallResult, *, origin: str) -> Any:
    """Require a completed read whose return is not text (no-value).

    A product exception is an aborted caller, not no-value. The empty
    string is a text value, not no-value. The concrete non-text carrier
    is not pinned.
    """
    require_call_completed(result, origin=origin)
    value = result.value
    assert not isinstance(value, str), (
        f"{origin} returned text {value!r}, not no-value"
    )
    print(f"{origin} no-text-value recorded={value!r}", flush=True)
    return value


def require_edit_did_not_succeed(
    result: CallResult,
    success: CallResult,
    *,
    origin: str,
) -> None:
    """Require *result* to be distinguishable from a successful edit.

    Does not pin an exception type or a language boolean. A completed
    report must differ from the success report.
    """
    require_call_completed(success, origin=f"{origin} success")
    aborted = result.exception is not None
    if aborted:
        print(f"{origin} aborted with {result.exception!r}", flush=True)
    else:
        print(
            f"{origin} completed report={result.value!r} "
            f"success_report={success.value!r}",
            flush=True,
        )
    assert aborted or result.value != success.value, (
        f"{origin} report {result.value!r} is indistinguishable from "
        f"success {success.value!r}"
    )


def require_owner_rw_only(path: str | Path) -> int:
    """Require *path* to be owner-read/write with no group or other bits.

    ``file_mode`` raises if the path is missing — that is not treated as
    mode 0.
    """
    mode = file_mode(path)
    owner_rw = stat.S_IRUSR | stat.S_IWUSR
    assert mode == owner_rw, (
        f"{path!s} mode is {mode:o}, not owner-read/write only ({owner_rw:o})"
    )
    print(f"{path!s} owner-rw-only mode={mode:o}", flush=True)
    return mode


def require_independent_line(text: str, line: str, *, origin: str) -> None:
    """Require *line* to appear as a whole ``splitlines()`` entry."""
    lines = text.splitlines()
    assert line in lines, (
        f"{origin} missing independent line {line!r}; lines={lines!r}"
    )
    print(f"{origin} has independent line {line!r}", flush=True)


def require_absent_independent_line(text: str, line: str, *, origin: str) -> None:
    """Require *line* not to appear as a whole ``splitlines()`` entry."""
    lines = text.splitlines()
    assert line not in lines, (
        f"{origin} still has independent line {line!r}; lines={lines!r}"
    )
    print(f"{origin} absent independent line {line!r}", flush=True)


def cli_invoke(ws: Workspace, args: Sequence[str], **kwargs: Any) -> RunResult:
    """Run the product CLI as ``python -m <package>`` with *args*.

    Extra keywords are forwarded to ``Workspace.run_module`` (for example
    ``cwd=``). Does not interpret the exit status.
    """
    result = ws.run_module(args, **kwargs)
    print(
        f"cli args={list(args)!r} rc={result.returncode} "
        f"stdout={result.stdout_text!r} stderr={result.stderr_text!r}",
        flush=True,
    )
    return result


def require_cli_success(result: RunResult, *, origin: str) -> str:
    """Return stdout when the CLI process succeeded.

    A non-zero exit is an observation failure — never empty text meaning
    "no output".
    """
    if result.returncode != 0:
        raise HarnessError(
            f"{origin} exited {result.returncode}; "
            f"stderr={result.stderr_text!r}; stdout={result.stdout_text!r}"
        )
    print(f"{origin} stdout={result.stdout_text!r}", flush=True)
    return result.stdout_text


def require_cli_unsuccessful(result: RunResult, *, origin: str) -> RunResult:
    """Require a non-zero CLI exit and return *result*.

    A zero exit is an observation failure, not a classified refusal.
    """
    if result.returncode == 0:
        raise HarnessError(
            f"{origin} exited 0; "
            f"stdout={result.stdout_text!r}; stderr={result.stderr_text!r}"
        )
    print(
        f"{origin} unsuccessful rc={result.returncode} "
        f"stdout={result.stdout_text!r} stderr={result.stderr_text!r}",
        flush=True,
    )
    return result


def cli_streams(result: RunResult) -> str:
    """Join stdout and stderr text.

    A decode failure on either stream raises — it is not treated as silence.
    """
    text = result.stdout_text + result.stderr_text
    print(f"cli_streams={text!r}", flush=True)
    return text


def installed_distribution_version() -> str:
    """Return ``<package>.version.__version__`` (Interface Contract: Version).

    A missing module, a missing attribute, a non-text or empty value is a
    harness failure, never "no version".
    """
    import importlib

    name = product_package_name()
    try:
        module = importlib.import_module(f"{name}.version")
    except ImportError as exc:
        raise HarnessError(f"cannot import {name}.version: {exc}") from exc
    recorded = getattr(module, "__version__", None)
    if not isinstance(recorded, str) or not recorded:
        raise HarnessError(f"{name}.version.__version__ is not a version string: {recorded!r}")
    print(f"installed version={recorded!r} package={name!r}", flush=True)
    return recorded


def cli_without_extra(ws: Workspace, args: Sequence[str], **kwargs: Any) -> RunResult:
    """Run the product module with site disabled so the CLI extra is absent.

    Same interpreter, ``python -S -m <package>``, product ``src/`` on
    ``PYTHONPATH``. Site-packages (and therefore the extra's command-line
    library) are not importable. Does not interpret the exit status.
    Harness or timeout failures raise.
    """
    name = product_package_name(root=ws.root)
    result = ws.run_python(
        argv=["-S", "-m", name, *[str(a) for a in args]],
        include_product=True,
        **kwargs,
    )
    print(
        f"cli-without-extra args={list(args)!r} rc={result.returncode} "
        f"stdout={result.stdout_text!r} stderr={result.stderr_text!r}",
        flush=True,
    )
    return result


def posix_shell_value(assignment_line: str, name: str) -> str:
    """Execute *assignment_line* in ``/bin/sh`` and return *name*'s value.

    A non-zero shell exit is an observation failure — never empty text
    meaning "could not restore". A successful restore may be the empty
    string (an empty stored value).
    """
    if not name or not name[0].isalpha() or not all(
        ch.isalnum() or ch == "_" for ch in name
    ):
        raise HarnessError(
            f"posix_shell_value name is not a POSIX identifier: {name!r}"
        )
    script = assignment_line + "\nprintf '%s' \"$" + name + "\"\n"
    result = run_command(["/bin/sh"], stdin=script)
    if result.returncode != 0:
        raise HarnessError(
            f"posix shell failed rc={result.returncode} "
            f"stderr={result.stderr_text!r} stdout={result.stdout_text!r} "
            f"line={assignment_line!r}"
        )
    print(
        f"posix restored name={name!r} line={assignment_line!r} "
        f"value={result.stdout_text!r}",
        flush=True,
    )
    return result.stdout_text


def strip_cli_covariates(
    text: str,
    paths: Sequence[str | Path],
    tokens: Sequence[str],
) -> str:
    """Strip path spellings then argv tokens from *text*.

    The result is for contrast. It is never interpreted as 'no report'.
    """
    stripped = strip_path_covariates(text, paths)
    for token in sorted({item for item in tokens if item}, key=len, reverse=True):
        stripped = stripped.replace(token, "")
    print(f"stripped cli covariates={stripped!r}", flush=True)
    return stripped


def child_environ_probe_source(names: Sequence[str]) -> str:
    """Return Python source that prints HAS_/VAL_ lines for *names*.

    Each name is embedded as a string literal in the source. The script
    does not read ``sys.argv``. A name missing from the process
    environment prints ``HAS_<name>=0`` and empty ``VAL_<name>=`` — that
    is a legal probe answer, not a query failure. The script ends
    normally (exit 0). *names* must be identifier suffixes for those
    labels.
    """
    if not names:
        raise HarnessError("child_environ_probe_source requires at least one name")
    idents: list[str] = []
    for name in names:
        if not name or not (name[0].isalpha() or name[0] == "_"):
            raise HarnessError(
                f"child_environ_probe_source name is not an identifier: {name!r}"
            )
        if not all(ch.isalnum() or ch == "_" for ch in name):
            raise HarnessError(
                f"child_environ_probe_source name is not an identifier: {name!r}"
            )
        idents.append(name)
    listed = ", ".join(repr(item) for item in idents)
    return (
        "import os\n"
        f"_PROBE_NAMES = ({listed},)\n"
        "for _n in _PROBE_NAMES:\n"
        "    _has = '1' if _n in os.environ else '0'\n"
        "    _val = os.environ[_n] if _n in os.environ else ''\n"
        "    print('HAS_' + _n + '=' + _has)\n"
        "    print('VAL_' + _n + '=' + _val)\n"
    )


def child_argv_probe_source() -> str:
    """Return Python source that prints ``ARGV=<token>`` for each ``sys.argv`` item.

    A missing line is an observation failure at the call site, not
    evidence that a flag was eaten. The script ends normally (exit 0).
    """
    return (
        "import sys\n"
        "for _token in sys.argv:\n"
        "    print('ARGV=' + _token)\n"
    )



# ---------------------------------------------------------------------------
# Carriers the Interface Contract states for diagnostics and CLI reports.
# ---------------------------------------------------------------------------

EXIT_OPERATION_FAILURE = 1
EXIT_USAGE_FAILURE = 2
USAGE_LABEL = "Usage:"


def diagnostic_lines(text: str) -> list[str]:
    """Each non-blank line is one diagnostic (Contract: one line per diagnostic)."""
    return [line for line in text.splitlines() if line.strip()]


def require_line_naming(
    text: str, token: str | Path, *, origin: str, without: str | Path | None = None
) -> str:
    """Require a diagnostic line that contains *token* (and not *without*)."""
    for line in diagnostic_lines(text):
        if str(token) in line and (without is None or str(without) not in line):
            print(f"{origin} line naming {str(token)!r}: {line!r}", flush=True)
            return line
    raise AssertionError(
        f"{origin} has no diagnostic line naming {str(token)!r}"
        + (f" without {str(without)!r}" if without is not None else "")
        + f"; text={text!r}"
    )


def require_no_line_naming(
    text: str, token: str | Path, *, origin: str, without: str | Path | None = None
) -> None:
    """Require no diagnostic line that contains *token* (and not *without*)."""
    for line in diagnostic_lines(text):
        if str(token) in line and (without is None or str(without) not in line):
            raise AssertionError(
                f"{origin} has a diagnostic line naming {str(token)!r}: {line!r}"
            )
    print(f"{origin} no line naming {str(token)!r}", flush=True)


def require_exit(result: RunResult, code: int, *, origin: str) -> None:
    """Require the Contract-stated exit status *code*."""
    assert result.returncode == code, (
        f"{origin} exited {result.returncode}, not {code}; "
        f"stdout={result.stdout_text!r} stderr={result.stderr_text!r}"
    )
    print(f"{origin} exit {code}", flush=True)


def has_usage_label(text: str) -> bool:
    """Whether a line of *text* starts with the Contract's usage label."""
    return any(line.startswith(USAGE_LABEL) for line in text.splitlines())
