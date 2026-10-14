"""Pipeline-owned sealed test helpers.

This file is the complete module. Import what you need (`from _helpers import ...`). Add a new helper here, with the imports and constants it closes over. Do not paste a sealed body into a feature file. Do not change a sealed name unless you own it and that feature's PRD was amended.
"""

from __future__ import annotations

import fcntl
import io
import os
import pty
import re
import select
import subprocess
import sys
import termios
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

from _harness import DEFAULT_TIMEOUT, InvokeResult, RunResult, workspace

# Longest suffix first so `_command` is not eaten as `_cmd` and `_group` is
# not eaten as `_grp`.
_TRAILING_NAME_SUFFIXES = ("_command", "_group", "_cmd", "_grp")


def default_invoked_name(function_name: str) -> str:
    """Return the default invoked command name from a function name.

    Spec oracle (FP-01): lowercase, strip one trailing ``_command`` /
    ``_cmd`` / ``_group`` / ``_grp`` (longest match first), then replace
    underscores with dashes. Example: ``init_data_command`` → ``init-data``.
    """
    name = function_name.lower()
    for suffix in _TRAILING_NAME_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[: -len(suffix)]
            break
    return name.replace("_", "-")


def _status_and_streams(result: Any) -> tuple[int, str, str]:
    """Return (status, stdout, stderr) or raise if the result is unreadable."""
    if isinstance(result, InvokeResult):
        return result.exit_code, result.stdout_text, result.stderr_text
    if isinstance(result, RunResult):
        return result.returncode, result.stdout_text, result.stderr_text
    raise TypeError(
        f"cannot classify invocation result of type {type(result)!r}"
    )


def require_success_with_marker(result: Any, marker: str) -> None:
    """Standalone success: status 0, *marker* appears exactly once on stdout."""
    if not marker:
        raise ValueError("marker must be a non-empty string")
    code, stdout, stderr = _status_and_streams(result)
    assert code == 0, (
        f"expected success exit 0, got {code}; stderr={stderr!r}"
    )
    count = stdout.count(marker)
    assert count == 1, (
        f"expected marker {marker!r} exactly once on stdout, found {count}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )


def require_success_marker_present(result: Any, marker: str) -> None:
    """Standalone success: status 0, *marker* appears at least once on stdout."""
    if not marker:
        raise ValueError("marker must be a non-empty string")
    code, stdout, stderr = _status_and_streams(result)
    assert code == 0, (
        f"expected success exit 0, got {code}; stderr={stderr!r}"
    )
    count = stdout.count(marker)
    assert count >= 1, (
        f"expected marker {marker!r} on stdout, found {count}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )


def require_usage_error_without_marker(result: Any, marker: str) -> None:
    """Usage-error class: status 2, *marker* absent from stdout."""
    if not marker:
        raise ValueError("marker must be a non-empty string")
    code, stdout, stderr = _status_and_streams(result)
    assert code == 2, (
        f"expected usage-error exit 2, got {code}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    assert marker not in stdout, (
        f"callback marker {marker!r} present on a usage-error run; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )


def help_page_remainder(result: Any, *covariates: str) -> str:
    """Help-page stdout with named covariates stripped.

    Carrier: stdout only — the same stream already shown to contain the
    command description. Stderr and captured warning records are not part
    of the page (those belong to the invocation-warning duty). An empty
    remainder after stripping is a real observation (no extra mark on the
    page). A failure to read stdout raises — it is not treated as "no mark".
    """
    if isinstance(result, (InvokeResult, RunResult)):
        try:
            text = result.stdout_text
        except Exception as exc:
            raise RuntimeError(
                f"failed to read help-page stdout: {exc}"
            ) from exc
    else:
        raise TypeError(
            f"cannot read help-page stdout from {type(result)!r}"
        )
    if text is None:
        raise RuntimeError("help-page stdout is None; cannot observe")
    for covariate in covariates:
        if covariate:
            text = text.replace(covariate, "")
    return text


def require_help_page_mark_unlike(
    deprecated_result: Any,
    baseline_result: Any,
    *covariates: str,
) -> None:
    """Help-page stdout remainders must differ after stripping covariates.

    The unlike is restricted to help-page text. An invocation warning on
    stderr or in captured warning records is not a passing remainder.
    """
    deprecated_rest = help_page_remainder(deprecated_result, *covariates)
    baseline_rest = help_page_remainder(baseline_result, *covariates)
    assert deprecated_rest != baseline_rest, (
        "help pages are not distinct after stripping shared text from "
        f"stdout; deprecated remainder={deprecated_rest!r} "
        f"baseline remainder={baseline_rest!r}"
    )


def caller_visible_remainder(result: Any, *covariates: str) -> str:
    """Caller-visible text with named covariates stripped.

    Carriers: mixed stdout/stderr, plus each captured warning message when
    *result* is an ``InvokeResult``. An empty remainder after stripping is
    a real observation (no extra warning). A failure to read the carriers
    raises — it is not treated as "no warning".
    """
    chunks: list[str] = []
    if isinstance(result, InvokeResult):
        try:
            chunks.append(result.output_text)
            warnings = result.warnings
        except Exception as exc:
            raise RuntimeError(
                f"failed to read caller-visible carriers: {exc}"
            ) from exc
        if warnings is None:
            raise RuntimeError("InvokeResult.warnings is None; cannot observe")
        try:
            for record in warnings:
                chunks.append(str(record.message))
        except Exception as exc:
            raise RuntimeError(
                f"failed to read captured warning messages: {exc}"
            ) from exc
    elif isinstance(result, RunResult):
        try:
            chunks.append(result.stdout_text)
            chunks.append(result.stderr_text)
        except Exception as exc:
            raise RuntimeError(
                f"failed to read child-process streams: {exc}"
            ) from exc
    else:
        raise TypeError(
            f"cannot read caller-visible carriers from {type(result)!r}"
        )
    text = "".join(chunks)
    for covariate in covariates:
        if covariate:
            text = text.replace(covariate, "")
    return text


def require_deprecation_distinct(
    deprecated_result: Any,
    baseline_result: Any,
    greeting: str,
    note: str | None = None,
) -> None:
    """Deprecated and non-deprecated runs both succeed with *greeting*.

    After stripping *greeting*, caller-visible remainders must differ. When
    *note* is supplied it must appear in the deprecated remainder and must
    be absent from the baseline remainder.
    """
    require_success_marker_present(deprecated_result, greeting)
    require_success_marker_present(baseline_result, greeting)
    deprecated_rest = caller_visible_remainder(deprecated_result, greeting)
    baseline_rest = caller_visible_remainder(baseline_result, greeting)
    assert deprecated_rest != baseline_rest, (
        "deprecation warning is not distinguishable from ordinary output "
        f"after stripping {greeting!r}; deprecated remainder={deprecated_rest!r} "
        f"baseline remainder={baseline_rest!r}"
    )
    if note is not None:
        assert note in deprecated_rest, (
            f"custom deprecation note {note!r} missing from warning remainder "
            f"{deprecated_rest!r}"
        )
        assert note not in baseline_rest, (
            f"custom deprecation note {note!r} appeared on the non-deprecated "
            f"baseline remainder {baseline_rest!r}"
        )


def require_failure_propagates(call: Callable[[], Any]) -> BaseException:
    """Run *call*; a raised exception is propagation.

    Completing as an ``InvokeResult`` (including standalone-shaped
    ``exit_code == 2``) or returning a value is not propagation.
    ``SystemExit`` is implicit process exit, not integrator propagation.
    """
    try:
        outcome = call()
    except SystemExit as exc:
        raise AssertionError(
            f"call ended with SystemExit({exc.code!r}); failure did not "
            "propagate to the caller"
        ) from exc
    except Exception as exc:
        return exc
    if isinstance(outcome, InvokeResult):
        raise AssertionError(
            "failure completed as a returned result instead of propagating; "
            f"exit_code={outcome.exit_code!r} return_value={outcome.return_value!r}"
        )
    raise AssertionError(
        f"failure returned {outcome!r} instead of propagating to the caller"
    )


def unrelated_dispatch_token(*forbidden: str) -> str:
    """Mint a runtime token that is not any forbidden name or case variant."""
    blocked: set[str] = set()
    for item in forbidden:
        if not item:
            continue
        blocked.add(item)
        blocked.add(item.lower())
        blocked.add(item.upper())
        blocked.add(item.swapcase())
    for _ in range(64):
        token = f"zxq-{uuid.uuid4().hex[:10]}"
        if token not in blocked and token.lower() not in blocked:
            return token
    raise RuntimeError(
        f"could not mint a dispatch token outside {sorted(blocked)!r}"
    )


def require_intentional_help(result: Any, greeting: str, *marks: str) -> None:
    """Intentional help: status 0, callback greeting absent, marks on stdout.

    The help page carrier is stdout. An empty stdout is a failure. Other
    exit statuses hard-fail with stderr in the message.
    """
    code, stdout, stderr = _status_and_streams(result)
    assert code == 0, (
        f"intentional help expected exit 0, got {code}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    assert stdout.strip(), (
        f"intentional help produced empty stdout; stderr={stderr!r}"
    )
    assert greeting not in stdout, (
        f"intentional help ran the callback; greeting {greeting!r} on stdout; "
        f"stdout={stdout!r}"
    )
    for mark in marks:
        assert mark in stdout, (
            f"intentional help missing {mark!r} on stdout; stdout={stdout!r} "
            f"stderr={stderr!r}"
        )


def require_usage_without_help_page(
    result: Any, greeting: str, *page_marks: str
) -> None:
    """Leftover-empty or unknown-name usage error: status 2, no help page.

    Greeting is absent from both streams. Each *page_mark* (the unique
    description from the same object's no-arguments help page) is absent
    from caller-visible stdout+stderr. Stderr must be non-empty (usage-class
    report). Other exit statuses hard-fail. Does not require an unknown
    token to be named.
    """
    if not greeting:
        raise ValueError("greeting must be a non-empty string")
    code, stdout, stderr = _status_and_streams(result)
    assert code == 2, (
        f"expected usage-error exit 2 without a help page, got {code}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    assert greeting not in stdout and greeting not in stderr, (
        f"callback greeting {greeting!r} present on a leftover/unknown run; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    visible = stdout + stderr
    for mark in page_marks:
        if not mark:
            raise ValueError("page marks must be non-empty")
        assert mark not in visible, (
            f"no-arguments help-page mark {mark!r} appeared on a "
            f"leftover/unknown run; stdout={stdout!r} stderr={stderr!r}"
        )
    assert stderr.strip(), (
        "usage-class report missing: stderr is empty; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )


def require_usage_help(result: Any, greeting: str, *marks: str) -> None:
    """No-args-is-help / missing-subcommand help: status 2, greeting absent.

    The Contract puts a help page shown because of incorrect usage on
    standard error; marks are required there.
    Other exit statuses hard-fail.
    """
    code, stdout, stderr = _status_and_streams(result)
    assert code == 2, (
        f"usage-help expected exit 2, got {code}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    assert greeting not in stdout and greeting not in stderr, (
        f"usage-help ran the callback; greeting {greeting!r} present; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    visible = stderr
    assert visible.strip(), (
        f"usage-help produced an empty help page on stderr; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    for mark in marks:
        assert mark in visible, (
            f"usage-help missing {mark!r} on stderr; "
            f"stdout={stdout!r} stderr={stderr!r}"
        )


def require_eager_identity(result: Any, greeting: str, identity: str) -> None:
    """Eager version flag: status 0, greeting absent, identity on stdout."""
    if not identity:
        raise ValueError("identity must be a non-empty string")
    code, stdout, stderr = _status_and_streams(result)
    assert code == 0, (
        f"eager version expected exit 0, got {code}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    assert greeting not in stdout, (
        f"eager version ran the callback; greeting {greeting!r} on stdout; "
        f"stdout={stdout!r}"
    )
    assert identity in stdout, (
        f"eager version missing identity {identity!r} on stdout; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )


def require_printed_identity_is(result: Any, greeting: str, identity: str) -> None:
    """Custom-version: status 0, greeting absent, stdout is *identity* plus whitespace.

    If *identity* is absent, this fails — an empty remainder is not success.
    """
    if not identity:
        raise ValueError("identity must be a non-empty string")
    code, stdout, stderr = _status_and_streams(result)
    assert code == 0, (
        f"custom-version expected exit 0, got {code}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    assert greeting not in stdout, (
        f"custom-version ran the callback; greeting {greeting!r} on stdout; "
        f"stdout={stdout!r}"
    )
    assert identity in stdout, (
        f"custom-version identity {identity!r} missing from stdout; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    remainder = stdout.replace(identity, "")
    assert remainder.strip() == "", (
        f"custom-version stdout has template remainder after stripping "
        f"identity {identity!r}; remainder={remainder!r} stdout={stdout!r}"
    )


def option_help_record(page: str, public_name: str, *sibling_names: str) -> str:
    """Slice of help-page stdout from *public_name* to the next sibling.

    Raises if *public_name* is absent. An empty slice is not returned as a
    stand-in for a missing option.
    """
    if not public_name:
        raise ValueError("public_name must be a non-empty string")
    if page is None:
        raise RuntimeError("help page is None; cannot observe option record")
    start = page.find(public_name)
    if start < 0:
        raise AssertionError(
            f"option public name {public_name!r} not found on help page; "
            f"page={page!r}"
        )
    end = len(page)
    for sibling in sibling_names:
        if not sibling or sibling == public_name:
            continue
        pos = page.find(sibling, start + len(public_name))
        if 0 <= pos < end:
            end = pos
    return page[start:end]


def usage_line(page: str, prog_name: str) -> str:
    """Return the usage line that contains *prog_name*. Raises if absent."""
    if not prog_name:
        raise ValueError("prog_name must be a non-empty string")
    if page is None:
        raise RuntimeError("help page is None; cannot observe usage line")
    for line in page.splitlines():
        if prog_name in line:
            return line
    raise AssertionError(
        f"no usage line containing prog name {prog_name!r}; page={page!r}"
    )


def description_block(page: str, *anchor_tokens: str) -> str:
    """Return the line span of *page* that covers every anchor token.

    Raises if any anchor is missing. Does not return an empty string to
    mean 'could not find the description'.
    """
    if page is None:
        raise RuntimeError("help page is None; cannot observe description")
    if not anchor_tokens:
        raise ValueError("description_block requires at least one anchor token")
    positions: list[tuple[int, int]] = []
    for token in anchor_tokens:
        if not token:
            raise ValueError("anchor tokens must be non-empty")
        pos = page.find(token)
        if pos < 0:
            raise AssertionError(
                f"description anchor {token!r} not found on help page; "
                f"page={page!r}"
            )
        positions.append((pos, pos + len(token)))
    start = min(p[0] for p in positions)
    end = max(p[1] for p in positions)
    line_start = page.rfind("\n", 0, start) + 1
    line_end = page.find("\n", end)
    if line_end < 0:
        line_end = len(page)
    block = page[line_start:line_end]
    if not block.strip():
        raise AssertionError(
            f"description block covering {anchor_tokens!r} is empty; "
            f"page={page!r}"
        )
    return block


def write_installed_distribution(
    root: str | Path,
    dist_name: str,
    version: str,
    import_names: Sequence[str],
) -> Path:
    """Write a discoverable dist-info tree under *root*.

    Layout: ``{dist_name}-{version}.dist-info/METADATA`` plus
    ``top_level.txt`` listing *import_names*. I/O failure raises.
    Returns the dist-info directory. Does not map a missing distribution
    to an empty version.
    """
    if not dist_name:
        raise ValueError("dist_name must be a non-empty string")
    if not version:
        raise ValueError("version must be a non-empty string")
    dest = Path(root) / f"{dist_name}-{version}.dist-info"
    try:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "METADATA").write_text(
            "Metadata-Version: 2.1\n"
            f"Name: {dist_name}\n"
            f"Version: {version}\n",
            encoding="utf-8",
        )
        (dest / "top_level.txt").write_text(
            "".join(f"{name}\n" for name in import_names),
            encoding="utf-8",
        )
    except OSError as exc:
        raise RuntimeError(
            f"failed to write installed distribution {dist_name!r} "
            f"version {version!r} under {root}: {exc}"
        ) from exc
    if not (dest / "METADATA").is_file():
        raise RuntimeError(f"distribution metadata missing after write: {dest}")
    return dest


def require_declaration_refused(call: Callable[[], Any]) -> BaseException:
    """Run *call*; a raised exception is a refused declaration.

    Returning a value (including a built command object) is a failure.
    Does not interpret usage-class exit statuses — those are invocation
    outcomes, not declaration refusals.
    """
    try:
        outcome = call()
    except Exception as exc:
        return exc
    raise AssertionError(
        f"declaration was accepted; got {outcome!r}"
    )


def usage_stderr_remainder(result: Any, *covariates: str) -> str:
    """Usage-error stderr with named covariates stripped.

    Carrier: stderr only (FP-13). An empty remainder after stripping is a
    real observation. A failure to read stderr raises — it is not
    treated as "no report".
    """
    if isinstance(result, (InvokeResult, RunResult)):
        try:
            text = result.stderr_text
        except Exception as exc:
            raise RuntimeError(
                f"failed to read usage-error stderr: {exc}"
            ) from exc
    else:
        raise TypeError(
            f"cannot read usage-error stderr from {type(result)!r}"
        )
    if text is None:
        raise RuntimeError("usage-error stderr is None; cannot observe")
    for covariate in covariates:
        if covariate:
            text = text.replace(covariate, "")
    return text


def require_usage_names_option(result: Any, greeting: str, public_name: str) -> None:
    """Usage-error class: status 2, greeting absent from stdout, *public_name* on stderr."""
    if not greeting:
        raise ValueError("greeting must be a non-empty string")
    if not public_name:
        raise ValueError("public_name must be a non-empty string")
    code, stdout, stderr = _status_and_streams(result)
    assert code == 2, (
        f"expected usage-error exit 2, got {code}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    assert greeting not in stdout, (
        f"callback marker {greeting!r} present on a usage-error run; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    assert public_name in stderr, (
        f"usage error did not name option {public_name!r} on stderr; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )


def require_usage_names_argument(result: Any, greeting: str, dest: str) -> None:
    """Usage class: exit 2, greeting absent, *dest* identified on stderr.

    The report must name the omitted or rejected argument. Case of the
    dest token is not pinned. Does not pin sentence wording.
    """
    if not dest:
        raise ValueError("dest must be a non-empty string")
    require_usage_class(result, greeting)
    _, stdout, stderr = _status_and_streams(result)
    assert dest.casefold() in stderr.casefold(), (
        f"usage error did not name argument {dest!r} on stderr; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )


def require_usage_names_path(result: Any, greeting: str, path: str) -> None:
    """Usage-error class: status 2, greeting absent, *path* on stderr.

    Only for conversion-time file-open failures (missing read target,
    non-lazy write that cannot open). Path-check failures must use
    ``require_usage_names_option`` / ``require_usage_error_without_marker``
    instead — those do not require the path token.
    """
    if not greeting:
        raise ValueError("greeting must be a non-empty string")
    if not path:
        raise ValueError("path must be a non-empty string")
    require_usage_error_without_marker(result, greeting)
    code, stdout, stderr = _status_and_streams(result)
    assert path in stderr, (
        f"usage error did not name path {path!r} on stderr; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )


def require_general_file_error_names_path(
    result: Any, path: str, started_marker: str
) -> None:
    """General file-open class: status 1, *started_marker* present, *path* on stderr.

    Other exit statuses hard-fail with both streams in the message. A
    failure to read the streams raises. Does not pin sentence wording
    and does not require the callback marker to be absent.
    """
    if not path:
        raise ValueError("path must be a non-empty string")
    if not started_marker:
        raise ValueError("started_marker must be a non-empty string")
    code, stdout, stderr = _status_and_streams(result)
    assert code == 1, (
        f"expected general file-open exit 1, got {code}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    if started_marker not in stdout and started_marker not in stderr:
        raise AssertionError(
            f"started marker {started_marker!r} missing on a general "
            f"file-open run; stdout={stdout!r} stderr={stderr!r}"
        )
    assert path in stderr, (
        f"general file-open error did not name path {path!r} on stderr; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )


def require_usage_kinds_unlike(
    left: Any,
    right: Any,
    greeting: str,
    *covariates: str,
) -> None:
    """Two usage-error runs (exit 2, greeting absent) with unlike stderr remainders.

    After stripping *covariates* from stderr, the remainders must differ.
    Restricted to the FP-03 non-sequence-default vs omitted-required contrast: do not use this
    to compare omitted-required against an illegal boolean environment word.
    """
    require_usage_error_without_marker(left, greeting)
    require_usage_error_without_marker(right, greeting)
    left_rest = usage_stderr_remainder(left, *covariates)
    right_rest = usage_stderr_remainder(right, *covariates)
    assert left_rest != right_rest, (
        "usage-error stderr remainders are not distinct after stripping "
        f"{covariates!r}; left={left_rest!r} right={right_rest!r}"
    )


def require_abort_without_marker(result: Any, marker: str) -> None:
    """Abort class: status 1, *marker* absent, stderr non-empty.

    Other exit statuses hard-fail with both streams in the message. A
    failure to read the streams raises — it is not treated as 'no abort'.
    Does not pin abort-sentence wording.
    """
    if not marker:
        raise ValueError("marker must be a non-empty string")
    code, stdout, stderr = _status_and_streams(result)
    assert code == 1, (
        f"expected abort-class exit 1, got {code}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    assert marker not in stdout and marker not in stderr, (
        f"callback marker {marker!r} present on an abort-class run; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    assert stderr.strip(), (
        "abort-class report missing: stderr is empty; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )


def require_abort_unlike_usage(
    abort_result: Any,
    usage_result: Any,
    greeting: str,
    *covariates: str,
) -> None:
    """Abort (exit 1) and usage (exit 2) with unlike stderr remainders.

    Both greetings must be absent. After stripping *covariates* from
    stderr, the remainders must differ. Does not pin abort or usage
    sentence wording.
    """
    require_abort_without_marker(abort_result, greeting)
    require_usage_error_without_marker(usage_result, greeting)
    abort_rest = usage_stderr_remainder(abort_result, *covariates)
    usage_rest = usage_stderr_remainder(usage_result, *covariates)
    assert abort_rest != usage_rest, (
        "abort and usage stderr remainders are not distinct after "
        f"stripping {covariates!r}; abort={abort_rest!r} usage={usage_rest!r}"
    )


def require_usage_class(result: Any, greeting: str) -> None:
    """Usage class: exit 2, greeting absent from both streams, stderr non-empty.

    Other exit statuses hard-fail with both streams in the message. A
    failure to read the streams raises. Does not pin usage-sentence wording.
    """
    if not greeting:
        raise ValueError("greeting must be a non-empty string")
    code, stdout, stderr = _status_and_streams(result)
    assert code == 2, (
        f"expected usage-class exit 2, got {code}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    assert greeting not in stdout and greeting not in stderr, (
        f"callback greeting {greeting!r} present on a usage-class run; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    assert stderr.strip(), (
        "usage-class report missing: stderr is empty; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )


def require_remaining_skipped(result: Any, before: str, after: str) -> None:
    """*before* is on stdout; *after* is absent from both streams.

    A failure to read the streams raises. Does not treat a particular
    exit status as skipped remaining work.
    """
    if not before:
        raise ValueError("before must be a non-empty string")
    if not after:
        raise ValueError("after must be a non-empty string")
    if before == after:
        raise ValueError("before and after markers must differ")
    _, stdout, stderr = _status_and_streams(result)
    assert before in stdout, (
        f"start marker {before!r} missing from stdout; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    assert after not in stdout and after not in stderr, (
        f"remaining-work marker {after!r} present after a mid-callback stop; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )


def require_abort_indication_unlike_usage(
    abort_result: Any,
    usage_result: Any,
    greeting: str,
    *covariates: str,
) -> None:
    """Abort indication unlike usage; abort remainder nonempty after stripping.

    Abort arm: exit 1, greeting absent, stderr non-empty. Usage arm: usage
    class. After stripping *covariates* from stderr, the abort remainder
    must be non-empty once whitespace is stripped, and must differ from
    the usage remainder. Does not pin abort-sentence wording.
    """
    require_abort_without_marker(abort_result, greeting)
    require_usage_class(usage_result, greeting)
    abort_rest = usage_stderr_remainder(abort_result, *covariates)
    usage_rest = usage_stderr_remainder(usage_result, *covariates)
    assert abort_rest.strip(), (
        "abort indication missing: stderr remainder is empty after "
        f"stripping {covariates!r}; abort={abort_rest!r} usage={usage_rest!r}"
    )
    assert abort_rest != usage_rest, (
        "abort and usage stderr remainders are not distinct after "
        f"stripping {covariates!r}; abort={abort_rest!r} usage={usage_rest!r}"
    )


def require_process_exit_not_captured_exception(result: Any) -> None:
    """Standalone outcome is a process exit, not a remapped generic exception.

    The in-process runner records an implicit process exit as SystemExit
    (cleared on status 0). Any other captured exception is remapped to
    status 1 without having performed the author-requested stop or abort.
    Does not pin product exception classes.
    """
    if not isinstance(result, InvokeResult):
        raise TypeError(
            "cannot observe process-exit vs captured exception on "
            f"{type(result)!r}"
        )
    try:
        exc = result.exception
        code = result.exit_code
        stdout = result.stdout_text
        stderr = result.stderr_text
    except Exception as err:
        raise RuntimeError(
            f"failed to read invocation outcome: {err}"
        ) from err
    if isinstance(exc, Exception):
        raise AssertionError(
            "invocation ended as a captured exception remapped to "
            f"status {code}, not a standalone process exit; "
            f"{type(exc).__name__}: {exc!r}; "
            f"stdout={stdout!r} stderr={stderr!r}"
        )


# Verdict names the suite audit can see at the call site. Imported helpers
# are matched by name (assert / verify / expect / check / must_), not by
# walking this module; the require_* functions above remain the bodies.
assert_success_with_marker = require_success_with_marker
assert_success_marker_present = require_success_marker_present
assert_usage_error_without_marker = require_usage_error_without_marker
assert_deprecation_distinct = require_deprecation_distinct
assert_failure_propagates = require_failure_propagates
assert_help_page_mark_unlike = require_help_page_mark_unlike
assert_intentional_help = require_intentional_help
assert_usage_help = require_usage_help
assert_usage_without_help_page = require_usage_without_help_page
assert_eager_identity = require_eager_identity
assert_printed_identity_is = require_printed_identity_is
assert_declaration_refused = require_declaration_refused
assert_usage_names_option = require_usage_names_option
assert_usage_names_argument = require_usage_names_argument
assert_usage_names_path = require_usage_names_path
assert_general_file_error_names_path = require_general_file_error_names_path
assert_usage_kinds_unlike = require_usage_kinds_unlike
assert_abort_without_marker = require_abort_without_marker
assert_abort_unlike_usage = require_abort_unlike_usage
assert_usage_class = require_usage_class
assert_remaining_skipped = require_remaining_skipped
assert_abort_indication_unlike_usage = require_abort_indication_unlike_usage
assert_process_exit_not_captured_exception = (
    require_process_exit_not_captured_exception
)


def call_with_fed_stdin(text: str, call: Callable[[], Any]) -> Any:
    """Redirect stdin to *text*, run *call*, restore stdin, return its value.

    Construction or restore failure raises. An exception from *call*
    propagates — empty input or EOF is not mapped to a default.
    """
    if not isinstance(text, str):
        raise TypeError(f"stdin text must be str, got {type(text)!r}")
    try:
        buf = io.StringIO(text)
    except Exception as exc:
        raise RuntimeError(f"failed to build fed stdin: {exc}") from exc
    old = sys.stdin
    try:
        sys.stdin = buf
        return call()
    finally:
        sys.stdin = old


def automatic_env_name(prefix: str, *parts: str) -> str:
    """FP-07 rule: prefix, then each command/param name, uppercased.

    Dashes in every part become underscores. Parts are joined with
    underscores. The top-level invocation name is not a part — callers
    pass only the first subcommand through the owning command, then the
    parameter name (or just the parameter name on a top-level command).
    """
    if not prefix:
        raise ValueError("prefix must be a non-empty string")
    chunks = [prefix, *parts]
    for chunk in chunks:
        if not chunk:
            raise ValueError("automatic env name parts must be non-empty")
    return "_".join(chunk.upper().replace("-", "_") for chunk in chunks)


def labeled_stdout_field(result: Any, label: str) -> str:
    """Return the field after *label* on stdout. *label* must appear once.

    The field is the text from the end of *label* to the next newline
    (or end of stdout). An empty field is a real observation. Missing
    or repeated *label* raises — it is not treated as an empty field.
    """
    if not label:
        raise ValueError("label must be a non-empty string")
    if isinstance(result, (InvokeResult, RunResult)):
        try:
            text = result.stdout_text
        except Exception as exc:
            raise RuntimeError(f"failed to read stdout for {label!r}: {exc}") from exc
    else:
        raise TypeError(
            f"cannot read a labeled stdout field from {type(result)!r}"
        )
    if text is None:
        raise RuntimeError(f"stdout is None; cannot observe {label!r}")
    matches: list[str] = []
    for line in text.splitlines():
        if line.startswith(label):
            matches.append(line[len(label) :])
    if len(matches) != 1:
        raise AssertionError(
            f"label {label!r} occurred {len(matches)} times as a line "
            f"prefix; stdout={text!r}"
        )
    return matches[0]


def require_labeled_fields_unlike(
    *results: Any,
    label: str,
    covariates: Sequence[str] = (),
) -> None:
    """Labeled stdout fields must be pairwise distinct after stripping.

    Each result must expose *label* exactly once. After each named
    covariate is removed from that field, every pair of remainders
    must differ. Does not require two calls of the same origin to
    be byte-identical.
    """
    if len(results) < 2:
        raise ValueError("require_labeled_fields_unlike needs at least two results")
    if not label:
        raise ValueError("label must be a non-empty string")
    remainders: list[str] = []
    for result in results:
        field = labeled_stdout_field(result, label)
        for covariate in covariates:
            if covariate:
                field = field.replace(covariate, "")
        remainders.append(field)
    for i, left in enumerate(remainders):
        for j, right in enumerate(remainders):
            if j <= i:
                continue
            assert left != right, (
                f"labeled fields for {label!r} are not distinct after "
                f"stripping {tuple(covariates)!r}; "
                f"left[{i}]={left!r} right[{j}]={right!r}"
            )


def ansi_escape_present(text: str) -> bool:
    """True when *text* contains an ESC byte used to start a style sequence.

    A read failure is the caller's job: *text* must already be a string.
    Does not pin a CSI opcode or a color name.
    """
    if text is None:
        raise RuntimeError("text is None; cannot observe an ANSI escape")
    return "\x1b" in text


def require_ansi_escape_present(result: Any) -> None:
    """Stdout of *result* must contain an ESC-led style sequence."""
    if isinstance(result, (InvokeResult, RunResult)):
        try:
            text = result.stdout_text
        except Exception as exc:
            raise RuntimeError(f"failed to read stdout for ANSI: {exc}") from exc
    else:
        raise TypeError(f"cannot read stdout from {type(result)!r}")
    if text is None:
        raise RuntimeError("stdout is None; cannot observe an ANSI escape")
    assert ansi_escape_present(text), (
        f"expected an ANSI escape on stdout; stdout={text!r}"
    )


def require_ansi_escape_absent(result: Any) -> None:
    """Stdout of *result* must not contain an ESC-led style sequence."""
    if isinstance(result, (InvokeResult, RunResult)):
        try:
            text = result.stdout_text
        except Exception as exc:
            raise RuntimeError(f"failed to read stdout for ANSI: {exc}") from exc
    else:
        raise TypeError(f"cannot read stdout from {type(result)!r}")
    if text is None:
        raise RuntimeError("stdout is None; cannot observe an ANSI escape")
    assert not ansi_escape_present(text), (
        f"unexpected ANSI escape on stdout; stdout={text!r}"
    )


def styled_stdout_remainder(result: Any, payload: str) -> str:
    """Stdout with *payload* stripped. *payload* must be present.

    The remainder is the carrier for 'this invocation's named style'
    versus the same text without that style. An empty remainder is a
    real observation (no extra bytes). A missing payload raises.
    """
    if not payload:
        raise ValueError("payload must be a non-empty string")
    if isinstance(result, (InvokeResult, RunResult)):
        try:
            text = result.stdout_text
        except Exception as exc:
            raise RuntimeError(
                f"failed to read stdout for style remainder: {exc}"
            ) from exc
    else:
        raise TypeError(f"cannot read stdout from {type(result)!r}")
    if text is None:
        raise RuntimeError("stdout is None; cannot observe a style remainder")
    if payload not in text:
        raise AssertionError(
            f"payload {payload!r} missing from stdout; stdout={text!r}"
        )
    return text.replace(payload, "")


def _take_stdin_as_controlling_tty() -> None:
    """Make the pty on fd 0 the child's controlling terminal.

    Runs in the forked child after ``start_new_session`` made it a
    session leader, so ``/dev/tty`` resolves to the pty as it does in
    a real terminal session.
    """
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)


def run_python_on_tty(code: str, *, timeout: float = DEFAULT_TIMEOUT) -> RunResult:
    """Run *code* in a child interpreter whose stdio is a real pty.

    Opening the pty or starting the child raises. A missing pty is not
    mapped to 'no sequences' or skipped. Stdout of the result is the
    bytes read from the master side (stderr is mixed on a pty).
    """
    if not code:
        raise ValueError("code must be a non-empty string")
    python = sys.executable
    if not python:
        raise RuntimeError("sys.executable is empty; cannot spawn an interpreter")
    try:
        master, slave = pty.openpty()
    except OSError as exc:
        raise RuntimeError(f"failed to open a pty: {exc}") from exc

    argv = (python, "-c", code)
    with workspace() as ws:
        try:
            proc = subprocess.Popen(
                list(argv),
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=str(ws.path),
                env=ws.env,
                close_fds=True,
                start_new_session=True,
                preexec_fn=_take_stdin_as_controlling_tty,
            )
        except Exception as exc:
            os.close(master)
            os.close(slave)
            raise RuntimeError(f"failed to start tty child: {exc}") from exc
        os.close(slave)
        chunks: list[bytes] = []
        deadline = time.monotonic() + timeout

        def _read_ready() -> bytes | None:
            try:
                data = os.read(master, 4096)
            except OSError:
                return None
            return data

        try:
            while True:
                if time.monotonic() > deadline:
                    proc.kill()
                    proc.wait()
                    raise RuntimeError("tty child timed out")
                finished = proc.poll() is not None
                wait = 0.05 if finished else 0.2
                ready, _, _ = select.select([master], [], [], wait)
                if ready:
                    data = _read_ready()
                    if not data:
                        break
                    chunks.append(data)
                elif finished:
                    break
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            os.close(master)
        if proc.returncode is None:
            raise RuntimeError("tty child ended without a return code")
        raw = b"".join(chunks)
        return RunResult(
            returncode=proc.returncode,
            stdout=raw,
            stderr=b"",
            argv=argv,
            cwd=str(ws.path),
        )


def write_strict_utf8_text(text: str) -> bytes:
    """Write *text* through a UTF-8 ``errors=strict`` byte-backed stream.

    Returns the bytes that landed on the wrapper. Encoding or write
    failure raises — an empty byte string is not returned as success
    when *text* is non-empty. Does not use an in-memory text buffer.
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text)!r}")
    buf = io.BytesIO()
    wrapper = io.TextIOWrapper(buf, encoding="utf-8", errors="strict")
    try:
        wrapper.write(text)
        wrapper.flush()
        data = buf.getvalue()
    except Exception as exc:
        raise RuntimeError(
            f"strict utf-8 write of {text!r} failed: {exc}"
        ) from exc
    finally:
        try:
            wrapper.detach()
        except Exception:
            pass
    if text and not data:
        raise RuntimeError(
            f"strict utf-8 write produced no bytes for non-empty text {text!r}"
        )
    return data


def is_readable_file_object(value: object) -> bool:
    """True when *value* is a readable file object (has a callable read).

    A missing or non-callable read is the only accepted 'not an open
    file' answer. This helper does not call read: a failed or empty
    read is not mapped to that answer.
    """
    read = getattr(value, "read", None)
    return callable(read)


def require_file_still_readable(file: Any, expected: str | bytes) -> None:
    """*file* is still open and a read contains *expected*.

    Probe failure raises — it is not treated as readable. An empty
    read when *expected* is non-empty is not success. Does not drain
    past ``len(expected)``.
    """
    if not expected:
        raise ValueError("expected must be a non-empty string or byte string")
    if file is None:
        raise RuntimeError("file is None; cannot observe readability")
    try:
        closed_attr = getattr(file, "closed", None)
    except Exception as exc:
        raise RuntimeError(f"failed to probe file.closed: {exc}") from exc
    if closed_attr is True:
        raise AssertionError(
            f"file reported closed; not still readable; expected={expected!r}"
        )
    read = getattr(file, "read", None)
    if not callable(read):
        raise RuntimeError(
            "file has no callable read; cannot observe readability"
        )
    try:
        data = read(len(expected))
    except Exception as exc:
        raise RuntimeError(f"read of still-open file failed: {exc}") from exc
    try:
        present = expected in data
    except TypeError as exc:
        raise AssertionError(
            f"cannot check {expected!r} in read result {data!r}: {exc}"
        ) from exc
    if not present:
        raise AssertionError(
            f"read result does not contain {expected!r}; "
            f"closed={closed_attr!r} data={data!r}"
        )


def require_file_no_longer_usable(file: Any) -> None:
    """Object reports closed, or a further read fails.

    An object that does not report closed and whose read succeeds
    (including an empty result) is still usable. Probe failure
    raises — it is not treated as closed. Does not pin an exception
    class for the failed read.
    """
    if file is None:
        raise RuntimeError("file is None; cannot observe usability")
    try:
        closed_attr = getattr(file, "closed", None)
    except Exception as exc:
        raise RuntimeError(f"failed to probe file.closed: {exc}") from exc
    if closed_attr is True:
        return
    read = getattr(file, "read", None)
    if not callable(read):
        raise RuntimeError(
            "file did not report closed and has no callable read; "
            "cannot observe usability"
        )
    try:
        data = read(1)
    except Exception:
        return
    raise AssertionError(
        "file did not report closed and a further read succeeded "
        f"(including empty); closed={closed_attr!r} data={data!r}"
    )


def marker_occurs(text: str, marker: str) -> bool:
    """True when *marker* occurs in *text* not glued to a word character.

    A labeled marker such as ``T:42`` must start a token: the same
    characters inside a random id (``GREET:42ab...``) are not the
    marker. Everything after the marker start is still a plain
    substring match, so a marker followed by extra text counts.
    """
    if not marker:
        raise ValueError("marker must be a non-empty string")
    if text is None:
        raise RuntimeError(f"text is None; cannot observe {marker!r}")
    return re.search(r"(?<!\w)" + re.escape(marker), text) is not None


def assert_marker_absent(text: str, marker: str) -> None:
    """*marker* must not occur in *text* as a token (see :func:`marker_occurs`)."""
    if marker_occurs(text, marker):
        raise AssertionError(
            f"marker {marker!r} unexpectedly present; text={text!r}"
        )


def labeled_stdout_fields(result: Any, label: str) -> list[str]:
    """Every stdout field after *label* as a line prefix, in order.

    Zero occurrences is a real observation (empty sequence). A
    failure to read stdout raises — it is not treated as zero
    occurrences. Does not require the label to appear once.
    """
    if not label:
        raise ValueError("label must be a non-empty string")
    if isinstance(result, (InvokeResult, RunResult)):
        try:
            text = result.stdout_text
        except Exception as exc:
            raise RuntimeError(
                f"failed to read stdout for {label!r}: {exc}"
            ) from exc
    else:
        raise TypeError(
            f"cannot read labeled stdout fields from {type(result)!r}"
        )
    if text is None:
        raise RuntimeError(f"stdout is None; cannot observe {label!r}")
    matches: list[str] = []
    for line in text.splitlines():
        if line.startswith(label):
            matches.append(line[len(label) :])
    return matches


def require_positional_items(payload: Any, *items: Any) -> None:
    """*payload* is not str/bytes; ``payload[i] == items[i]`` and matching length.

    Index or ``len`` failure is an assertion failure (with the original
    exception). Zero *items* means an empty sequence. Does not convert
    *payload* with ``tuple()``.
    """
    if isinstance(payload, (str, bytes)):
        raise AssertionError(
            f"payload is a string or byte string, not a positional "
            f"sequence; payload={payload!r}"
        )
    try:
        length = len(payload)
    except Exception as exc:
        raise AssertionError(
            f"len(payload) failed: {exc}; payload={payload!r}"
        ) from exc
    assert length == len(items), (
        f"payload length {length} != {len(items)}; payload={payload!r}"
    )
    for index, expected in enumerate(items):
        try:
            got = payload[index]
        except Exception as exc:
            raise AssertionError(
                f"payload[{index}] failed: {exc}; payload={payload!r}"
            ) from exc
        assert got == expected, (
            f"payload[{index}] is {got!r}, expected {expected!r}; "
            f"payload={payload!r}"
        )


def posix_app_slug(app_name: str) -> str:
    """FP-11 rule: lowercase, whitespace runs become a single dash.

    Not a product-internal transform.
    """
    if not app_name:
        raise ValueError("app_name must be a non-empty string")
    parts = app_name.split()
    if not parts:
        raise ValueError("app_name must contain a non-whitespace character")
    return "-".join(part.lower() for part in parts)


def styled_text_remainder(text: str, payload: str) -> str:
    """In-process styled string with *payload* stripped. *payload* must be in *text*.

    An empty remainder is a real observation. ``text is None`` or a missing
    payload raises — it is not treated as 'no style'.
    """
    if text is None:
        raise RuntimeError("styled text is None; cannot observe a remainder")
    if not payload:
        raise ValueError("payload must be a non-empty string")
    if payload not in text:
        raise AssertionError(
            f"payload {payload!r} missing from styled text; text={text!r}"
        )
    return text.replace(payload, "")


def styled_text_suffix(text: str, payload: str) -> str:
    """Slice of *text* after the first *payload*. *payload* must be present.

    An empty suffix is a real observation (nothing was appended after the
    payload). ``text is None`` or a missing payload raises — it is not
    treated as 'no trailing reset'.
    """
    if text is None:
        raise RuntimeError("styled text is None; cannot observe a suffix")
    if not payload:
        raise ValueError("payload must be a non-empty string")
    if not isinstance(text, str):
        raise TypeError(f"styled text must be str, got {type(text)!r}")
    start = text.find(payload)
    if start < 0:
        raise AssertionError(
            f"payload {payload!r} missing from styled text; text={text!r}"
        )
    return text[start + len(payload) :]


def failure_report_remainder(text: str, *covariates: str) -> str:
    """Failure-report string with named covariates stripped.

    An empty remainder is a real observation (two empty remainders then
    fail a distinguishability assert). ``text is None`` raises — it is
    not treated as a successful character.
    """
    if text is None:
        raise RuntimeError("failure report is None; cannot observe")
    if not isinstance(text, str):
        raise TypeError(f"failure report must be str, got {type(text)!r}")
    for covariate in covariates:
        if covariate:
            text = text.replace(covariate, "")
    return text


# POSIX names a default-application opener is looked up under. Tests do
# not assert which of these was exec'd — only that a launch record exists.
_POSIX_DEFAULT_OPENERS = (
    "xdg-open",
    "gio",
    "gvfs-open",
    "gnome-open",
    "kde-open",
    "kde-open5",
    "exo-open",
    "mimeopen",
    "open",
    "cygstart",
)


@contextmanager
def recording_default_application(root: str | Path) -> Iterator[Path]:
    """Install a recording default application at the front of PATH.

    Yields the sentinel path the recorder writes. Restores PATH and the
    browser environment variable on exit. Construction failure raises.
    Does not map a missing record to a successful launch.
    """
    dest_root = Path(root)
    bindir = dest_root / f"openers-{uuid.uuid4().hex[:10]}"
    sentinel = dest_root / f"launch-record-{uuid.uuid4().hex[:10]}"
    python = sys.executable
    if not python:
        raise RuntimeError("sys.executable is empty; cannot write a recorder")
    try:
        bindir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(
            f"failed to create default-application bindir: {exc}"
        ) from exc
    body = (
        f"#!{python}\n"
        "import sys\n"
        f"path = {str(sentinel)!r}\n"
        "with open(path, 'a', encoding='utf-8') as fh:\n"
        "    fh.write(' '.join(sys.argv) + '\\n')\n"
        "    fh.flush()\n"
    )
    recorder = bindir / "default-open"
    try:
        recorder.write_text(body, encoding="utf-8")
        recorder.chmod(0o755)
        for name in _POSIX_DEFAULT_OPENERS:
            opener = bindir / name
            opener.write_text(body, encoding="utf-8")
            opener.chmod(0o755)
    except OSError as exc:
        raise RuntimeError(
            f"failed to install recording default application: {exc}"
        ) from exc

    old_path = os.environ.get("PATH")
    old_browser = os.environ.get("BROWSER")
    os.environ["PATH"] = f"{bindir}{os.pathsep}{old_path or ''}"
    os.environ["BROWSER"] = str(recorder)
    try:
        yield sentinel
    finally:
        if old_path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = old_path
        if old_browser is None:
            os.environ.pop("BROWSER", None)
        else:
            os.environ["BROWSER"] = old_browser


def application_launch_record(
    sentinel: Path,
    call: Callable[[], Any],
    *,
    timeout: float = 8.0,
) -> str:
    """Run *call* and return the default application's recorded argv text.

    Clears *sentinel* first so a leftover file is not a launch. *call*
    must finish within *timeout*. A missing or empty record raises —
    it is not returned as 'nothing was launched'. Does not pin the
    opener's executable name.
    """
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if sentinel is None:
        raise RuntimeError("launch sentinel is None; cannot observe a launch")
    try:
        if sentinel.exists():
            sentinel.unlink()
    except OSError as exc:
        raise RuntimeError(
            f"failed to clear launch record {sentinel}: {exc}"
        ) from exc
    require_completed_within(call, timeout)
    deadline = time.monotonic() + timeout
    while True:
        try:
            present = sentinel.is_file()
            text = sentinel.read_text(encoding="utf-8") if present else ""
        except OSError as exc:
            raise RuntimeError(
                f"failed to read launch record {sentinel}: {exc}"
            ) from exc
        if text.strip():
            return text
        if time.monotonic() > deadline:
            raise AssertionError(
                "no application was launched; launch record missing or empty "
                f"at {sentinel}"
            )
        time.sleep(0.05)


def require_completed_within(call: Callable[[], Any], timeout: float) -> Any:
    """Run *call* in a worker thread; timeout is an assertion failure.

    A timeout is not mapped to 'did nothing'. An exception from *call*
    is re-raised on this thread. Does not kill a stuck worker.
    """
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    box: list[tuple[str, Any]] = []

    def _run() -> None:
        try:
            box.append(("ok", call()))
        except BaseException as exc:
            box.append(("err", exc))

    worker = threading.Thread(target=_run, name="require_completed_within")
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        raise AssertionError(
            f"call did not complete within {timeout}s"
        )
    if not box:
        raise RuntimeError("worker finished without recording an outcome")
    kind, value = box[0]
    if kind == "err":
        raise value
    return value


class TtySession:
    """A child interpreter whose stdio is a live pty, still running.

    Opening the pty or starting the child raises. A missing pty is not
    mapped to 'no sequences' or skipped. Accumulated stdout is the bytes
    read from the master (stderr is mixed on a pty).
    """

    def __init__(
        self,
        proc: subprocess.Popen[bytes],
        master: int,
        argv: tuple[str, ...],
        cwd: Path,
        deadline: float,
        workspace_cleanup: Callable[[], None] | None = None,
    ) -> None:
        self._proc = proc
        self._master = master
        self._argv = argv
        self.cwd = cwd
        self._deadline = deadline
        self._workspace_cleanup = workspace_cleanup
        self._chunks: list[bytes] = []
        self._lock = threading.Lock()
        self._closed = False
        self._reader = threading.Thread(
            target=self._read_loop, name="tty-session-reader", daemon=True
        )
        self._reader.start()

    def _read_loop(self) -> None:
        while True:
            if time.monotonic() > self._deadline:
                break
            if self._master < 0:
                break
            try:
                ready, _, _ = select.select([self._master], [], [], 0.1)
            except (OSError, ValueError):
                break
            if not ready:
                if self._proc.poll() is not None:
                    self._drain_rest()
                    break
                continue
            try:
                data = os.read(self._master, 4096)
            except OSError:
                break
            if not data:
                break
            with self._lock:
                self._chunks.append(data)
        if self._proc.poll() is not None:
            self._drain_rest()

    def _drain_rest(self) -> None:
        if self._master < 0:
            return
        while True:
            try:
                ready, _, _ = select.select([self._master], [], [], 0.05)
            except (OSError, ValueError):
                return
            if not ready:
                return
            try:
                data = os.read(self._master, 4096)
            except OSError:
                return
            if not data:
                return
            with self._lock:
                self._chunks.append(data)

    def accumulated(self) -> bytes:
        with self._lock:
            return b"".join(self._chunks)

    def accumulated_text(self) -> str:
        return self.accumulated().decode("utf-8", errors="replace")

    def feed(self, data: str | bytes) -> None:
        if isinstance(data, str):
            raw = data.encode("utf-8")
        else:
            raw = data
        if not raw:
            raise ValueError("feed data must be non-empty")
        if self._master < 0:
            raise RuntimeError("tty master is closed; cannot feed")
        try:
            os.write(self._master, raw)
        except OSError as exc:
            raise RuntimeError(f"failed to feed tty: {exc}") from exc

    def wait_until(
        self,
        predicate: Callable[[], bool],
        *,
        timeout: float | None = None,
        message: str = "condition",
    ) -> None:
        cap = timeout if timeout is not None else max(
            0.0, self._deadline - time.monotonic()
        )
        deadline = time.monotonic() + cap
        while True:
            try:
                ok = predicate()
            except Exception as exc:
                raise RuntimeError(
                    f"tty wait predicate raised: {exc}"
                ) from exc
            if ok:
                return
            if time.monotonic() > deadline:
                raise RuntimeError(
                    f"timed out waiting for {message}; "
                    f"output={self.accumulated_text()!r} "
                    f"returncode={self._proc.poll()!r}"
                )
            if self._proc.poll() is not None and not predicate():
                self._drain_rest()
                if predicate():
                    return
                raise RuntimeError(
                    f"tty child exited before {message}; "
                    f"output={self.accumulated_text()!r} "
                    f"returncode={self._proc.returncode!r}"
                )
            time.sleep(0.05)

    def kill(self) -> None:
        if self._proc.poll() is None:
            self._proc.kill()
            self._proc.wait()
        self._close_master()

    def _close_master(self) -> None:
        if self._master < 0:
            return
        fd = self._master
        self._master = -1
        try:
            os.close(fd)
        except OSError:
            pass

    def wait(self, timeout: float | None = None) -> RunResult:
        cap = timeout if timeout is not None else max(
            0.05, self._deadline - time.monotonic()
        )
        try:
            self._proc.wait(timeout=cap)
        except subprocess.TimeoutExpired:
            self.kill()
            self._cleanup_workspace()
            raise RuntimeError("tty child timed out") from None
        self._reader.join(timeout=2.0)
        self._drain_rest()
        self._close_master()
        if self._proc.returncode is None:
            self._cleanup_workspace()
            raise RuntimeError("tty child ended without a return code")
        raw = self.accumulated()
        self._closed = True
        self._cleanup_workspace()
        return RunResult(
            returncode=self._proc.returncode,
            stdout=raw,
            stderr=b"",
            argv=self._argv,
            cwd=str(self.cwd),
        )

    def close(self) -> None:
        if self._closed:
            return
        if self._proc.poll() is None:
            self.kill()
        else:
            self._close_master()
        self._closed = True
        self._cleanup_workspace()

    def _cleanup_workspace(self) -> None:
        cleanup = self._workspace_cleanup
        if cleanup is None:
            return
        self._workspace_cleanup = None
        cleanup()


def start_python_on_tty(
    code: str, *, timeout: float = DEFAULT_TIMEOUT
) -> TtySession:
    """Start *code* in a child interpreter whose stdio is a real pty.

    Opening the pty or starting the child raises. The caller must
    :meth:`TtySession.wait` or :meth:`TtySession.close`. A missing pty
    is not mapped to 'no sequences' or skipped.
    """
    if not code:
        raise ValueError("code must be a non-empty string")
    python = sys.executable
    if not python:
        raise RuntimeError("sys.executable is empty; cannot spawn an interpreter")
    try:
        master, slave = pty.openpty()
    except OSError as exc:
        raise RuntimeError(f"failed to open a pty: {exc}") from exc

    argv = (python, "-c", code)
    ws_cm = workspace()
    ws = ws_cm.__enter__()
    released = False

    def _release_workspace() -> None:
        nonlocal released
        if released:
            return
        released = True
        ws_cm.__exit__(None, None, None)

    env = dict(ws.env)
    env["PYTHONUNBUFFERED"] = "1"
    try:
        proc = subprocess.Popen(
            list(argv),
            stdin=slave,
            stdout=slave,
            stderr=slave,
            cwd=str(ws.path),
            env=env,
            close_fds=True,
            start_new_session=True,
            preexec_fn=_take_stdin_as_controlling_tty,
        )
    except Exception as exc:
        os.close(master)
        os.close(slave)
        _release_workspace()
        raise RuntimeError(f"failed to start tty child: {exc}") from exc
    os.close(slave)
    return TtySession(
        proc,
        master,
        argv,
        ws.path,
        time.monotonic() + timeout,
        workspace_cleanup=_release_workspace,
    )


def run_python_on_tty_feed(
    code: str,
    tty_feed: str | bytes,
    timeout: float = DEFAULT_TIMEOUT,
) -> RunResult:
    """Run *code* on a pty and write *tty_feed* to the master.

    Feed or start failure raises. A timeout raises — it is not mapped
    to a successful keypress.
    """
    if not code:
        raise ValueError("code must be a non-empty string")
    if not tty_feed:
        raise ValueError("tty_feed must be non-empty")
    session = start_python_on_tty(code, timeout=timeout)
    try:
        session.feed(tty_feed)
        return session.wait()
    except Exception:
        session.close()
        raise


def run_python_on_tty_blocked_until_feed(
    code: str,
    ready_mark: str,
    done_mark: str,
    tty_feed: str | bytes,
    timeout: float = DEFAULT_TIMEOUT,
) -> RunResult:
    """Wait for *ready_mark* on the pty; *done_mark* must still be absent.

    Then write *tty_feed* and wait for *done_mark*. A done mark that is
    already present when the ready mark appears means the call did not
    block. Opening the pty or a timeout raises; do not skip.
    """
    if not code:
        raise ValueError("code must be a non-empty string")
    if not ready_mark:
        raise ValueError("ready_mark must be a non-empty string")
    if not done_mark:
        raise ValueError("done_mark must be a non-empty string")
    if ready_mark == done_mark:
        raise ValueError("ready_mark and done_mark must differ")
    if not tty_feed:
        raise ValueError("tty_feed must be non-empty")
    session = start_python_on_tty(code, timeout=timeout)
    try:
        session.wait_until(
            lambda: ready_mark in session.accumulated_text(),
            message=f"ready mark {ready_mark!r}",
        )
        seen = session.accumulated_text()
        if done_mark in seen:
            raise RuntimeError(
                f"done mark {done_mark!r} already present before feed; "
                f"call did not block; output={seen!r}"
            )
        session.feed(tty_feed)
        session.wait_until(
            lambda: done_mark in session.accumulated_text(),
            message=f"done mark {done_mark!r}",
        )
        return session.wait()
    except Exception:
        session.close()
        raise


def run_python_pipe_stdin_controlling_tty(
    code: str,
    stdin_bytes: str | bytes,
    tty_feed: str | bytes,
    timeout: float = DEFAULT_TIMEOUT,
) -> RunResult:
    """Run *code* with stdin as a pipe and a pty as the controlling terminal.

    *stdin_bytes* are written to the pipe. *tty_feed* is written to the
    pty master after the child has printed something, so ``setraw``
    (TCSAFLUSH) cannot discard the key. Opening the pty or a timeout
    raises; do not skip.
    """
    if not code:
        raise ValueError("code must be a non-empty string")
    if not tty_feed:
        raise ValueError("tty_feed must be non-empty")
    python = sys.executable
    if not python:
        raise RuntimeError("sys.executable is empty; cannot spawn an interpreter")
    if isinstance(stdin_bytes, str):
        stdin_raw = stdin_bytes.encode("utf-8")
    else:
        stdin_raw = stdin_bytes
    if isinstance(tty_feed, str):
        feed_raw = tty_feed.encode("utf-8")
    else:
        feed_raw = tty_feed

    stdin_r, stdin_w = os.pipe()
    stdout_r, stdout_w = os.pipe()
    stderr_r, stderr_w = os.pipe()

    with workspace() as ws:
        env = dict(ws.env)
        env["PYTHONUNBUFFERED"] = "1"
        try:
            pid, master = pty.fork()
        except OSError as exc:
            for fd in (stdin_r, stdin_w, stdout_r, stdout_w, stderr_r, stderr_w):
                os.close(fd)
            raise RuntimeError(f"failed to fork a pty: {exc}") from exc

        if pid == 0:
            os.close(stdin_w)
            os.close(stdout_r)
            os.close(stderr_r)
            try:
                os.close(master)
            except OSError:
                pass
            keep = os.dup(0)
            os.dup2(stdin_r, 0)
            os.dup2(stdout_w, 1)
            os.dup2(stderr_w, 2)
            for fd in (stdin_r, stdout_w, stderr_w):
                if fd not in (0, 1, 2, keep):
                    os.close(fd)
            try:
                os.chdir(str(ws.path))
            except OSError:
                os._exit(124)
            os.execve(python, [python, "-c", code], env)
            os._exit(127)

        os.close(stdin_r)
        os.close(stdout_w)
        os.close(stderr_w)
        argv = (python, "-c", code)
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        returncode = 1
        stdin_closed = False

        def _read_pipes(wait: float) -> None:
            ready, _, _ = select.select([stdout_r, stderr_r], [], [], wait)
            for fd in ready:
                try:
                    data = os.read(fd, 4096)
                except OSError:
                    data = b""
                if not data:
                    continue
                if fd == stdout_r:
                    stdout_chunks.append(data)
                else:
                    stderr_chunks.append(data)

        def _harvest(status: int) -> int:
            for fd, bucket in ((stdout_r, stdout_chunks), (stderr_r, stderr_chunks)):
                while True:
                    rlist, _, _ = select.select([fd], [], [], 0)
                    if not rlist:
                        break
                    try:
                        data = os.read(fd, 4096)
                    except OSError:
                        break
                    if not data:
                        break
                    bucket.append(data)
            if os.WIFEXITED(status):
                return os.WEXITSTATUS(status)
            if os.WIFSIGNALED(status):
                return -os.WTERMSIG(status)
            return 1

        try:
            os.write(stdin_w, stdin_raw)
            os.close(stdin_w)
            stdin_closed = True
            deadline = time.monotonic() + timeout

            saw_output = False
            while time.monotonic() < deadline:
                _read_pipes(0.1)
                if stdout_chunks or stderr_chunks:
                    saw_output = True
                    break
                waited = os.waitpid(pid, os.WNOHANG)
                if waited[0] == pid:
                    returncode = _harvest(waited[1])
                    saw_output = True
                    break
            if not saw_output:
                os.kill(pid, 9)
                os.waitpid(pid, 0)
                raise RuntimeError(
                    "controlling-tty child produced no output before getchar"
                )

            waited = os.waitpid(pid, os.WNOHANG)
            if waited[0] != pid:
                time.sleep(0.25)
                try:
                    os.write(master, feed_raw)
                except OSError as exc:
                    os.kill(pid, 9)
                    os.waitpid(pid, 0)
                    raise RuntimeError(
                        f"failed to feed controlling tty: {exc}"
                    ) from exc
                while time.monotonic() < deadline:
                    _read_pipes(0.1)
                    waited = os.waitpid(pid, os.WNOHANG)
                    if waited[0] == pid:
                        returncode = _harvest(waited[1])
                        break
                else:
                    os.kill(pid, 9)
                    os.waitpid(pid, 0)
                    raise RuntimeError("controlling-tty child timed out")
            elif waited[0] == pid:
                returncode = _harvest(waited[1])
        finally:
            if not stdin_closed:
                try:
                    os.close(stdin_w)
                except OSError:
                    pass
            for fd in (stdout_r, stderr_r, master):
                try:
                    os.close(fd)
                except OSError:
                    pass
        return RunResult(
            returncode=returncode,
            stdout=b"".join(stdout_chunks),
            stderr=b"".join(stderr_chunks),
            argv=argv,
            cwd=str(ws.path),
        )


assert_labeled_fields_unlike = require_labeled_fields_unlike
assert_ansi_escape_present = require_ansi_escape_present
assert_ansi_escape_absent = require_ansi_escape_absent
assert_file_still_readable = require_file_still_readable
assert_file_no_longer_usable = require_file_no_longer_usable
assert_positional_items = require_positional_items


# ---------------------------------------------------------------------------
# FP-12 shell completion (F12)
# ---------------------------------------------------------------------------

_INDEX_COMPLETION_SHELLS = frozenset({"bash", "zsh", "powershell"})
_FISH_COMPLETION_SHELL = "fish"
_KNOWN_COMPLETION_SHELLS = _INDEX_COMPLETION_SHELLS | {_FISH_COMPLETION_SHELL}


def complete_variable_name(executable: str) -> str:
    """FP-12 rule: underscore + uppercase executable + ``_COMPLETE``.

    Dashes become underscores. Dots are left as written — FP-12 does not
    name that substitution.
    """
    if not executable:
        raise ValueError("executable must be a non-empty string")
    if not isinstance(executable, str):
        raise TypeError(f"executable must be str, got {type(executable)!r}")
    return f"_{executable.replace('-', '_').upper()}_COMPLETE"


def completion_instruction_env(
    executable: str, instruction: str
) -> dict[str, str]:
    """Environment with only the completion variable set to *instruction*."""
    if not instruction:
        raise ValueError("instruction must be a non-empty string")
    if not isinstance(instruction, str):
        raise TypeError(f"instruction must be str, got {type(instruction)!r}")
    return {complete_variable_name(executable): instruction}


def completion_line_env(
    shell: str,
    executable: str,
    completed_words: Sequence[str],
    incomplete: str,
) -> dict[str, str]:
    """Feed one shell's word list and incomplete token into the process env.

    Also sets ``{shell}_complete`` on the FP-12 variable. Does not assert
    that these keys appear on stdout — they are the feed, not the contract.
    Fish puts the incomplete token in ``COMP_CWORD``; index shells put
    the cursor index there.
    """
    if shell not in _KNOWN_COMPLETION_SHELLS:
        raise ValueError(
            f"unknown completion shell {shell!r}; "
            f"known={sorted(_KNOWN_COMPLETION_SHELLS)!r}"
        )
    if not executable:
        raise ValueError("executable must be a non-empty string")
    if incomplete is None:
        raise ValueError("incomplete must be a string (empty is allowed)")
    if not isinstance(incomplete, str):
        raise TypeError(f"incomplete must be str, got {type(incomplete)!r}")
    try:
        completed = [str(word) for word in completed_words]
    except TypeError as exc:
        raise TypeError(
            f"completed_words must be a sequence of strings: {exc}"
        ) from exc
    for word in completed:
        if not word:
            raise ValueError("completed words must be non-empty strings")

    env = completion_instruction_env(executable, f"{shell}_complete")
    line = [executable, *completed]
    if shell == _FISH_COMPLETION_SHELL:
        if incomplete:
            line.append(incomplete)
        env["COMP_WORDS"] = " ".join(line)
        env["COMP_CWORD"] = incomplete
        return env

    if incomplete:
        line.append(incomplete)
        env["COMP_CWORD"] = str(len(line) - 1)
    else:
        env["COMP_CWORD"] = str(len(line))
    env["COMP_WORDS"] = " ".join(line)
    return env


def completion_stream_remainder(result: Any, *covariates: str) -> str:
    """Suggestion/source stdout with named covariates stripped.

    An empty remainder is a real observation (match-nothing). A failure
    to read stdout raises — it is not treated as an empty stream.
    """
    if isinstance(result, (InvokeResult, RunResult)):
        try:
            text = result.stdout_text
        except Exception as exc:
            raise RuntimeError(
                f"failed to read completion-stream stdout: {exc}"
            ) from exc
    else:
        raise TypeError(
            f"cannot read completion-stream stdout from {type(result)!r}"
        )
    if text is None:
        raise RuntimeError("completion-stream stdout is None; cannot observe")
    for covariate in covariates:
        if covariate:
            text = text.replace(covariate, "")
    return text


def require_callback_skipped(result: Any, greeting: str) -> None:
    """Greeting is absent from stdout and stderr.

    Does not treat a particular exit status as 'skipped'. A failure to
    read the streams raises — it is not treated as a skipped callback.
    """
    if not greeting:
        raise ValueError("greeting must be a non-empty string")
    code, stdout, stderr = _status_and_streams(result)
    assert greeting not in stdout and greeting not in stderr, (
        f"callback greeting {greeting!r} present on a skipped-callback run "
        f"(exit {code}); stdout={stdout!r} stderr={stderr!r}"
    )


def require_not_usage_class(result: Any, greeting: str) -> None:
    """Not a usage-class exit 2; greeting absent from both streams.

    Does not pin a success exit of 0. A failure to read the streams raises.
    """
    if not greeting:
        raise ValueError("greeting must be a non-empty string")
    code, stdout, stderr = _status_and_streams(result)
    assert code != 2, (
        f"expected a non-usage-class outcome, got usage-class exit 2; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    assert greeting not in stdout and greeting not in stderr, (
        f"callback greeting {greeting!r} present on a non-usage complete run "
        f"(exit {code}); stdout={stdout!r} stderr={stderr!r}"
    )


def import_trace_present(path: Path) -> bool:
    """True when the import-side-effect file exists.

    I/O failure raises. A missing file is the only accepted 'not loaded'
    answer — it is not returned when the probe itself fails.
    """
    if path is None:
        raise RuntimeError("import trace path is None; cannot observe")
    try:
        return path.is_file()
    except OSError as exc:
        raise RuntimeError(
            f"failed to observe import trace {path}: {exc}"
        ) from exc


assert_callback_skipped = require_callback_skipped
assert_not_usage_class = require_not_usage_class
assert_import_trace_present = import_trace_present


def product_runner_streams(result: Any) -> tuple[int, str, str]:
    """Return (status, stdout text, stderr text) from a product runner result.

    Harness result types are rejected. Missing fields or a read failure
    raise — they are not mapped to empty strings. Stdout/stderr must be
    text; bytes-only fields are read by ``product_runner_bytes``.
    """
    if isinstance(result, (InvokeResult, RunResult)):
        raise TypeError(
            "harness invocation result is not a product runner result; "
            f"got {type(result)!r}"
        )
    try:
        status = result.exit_code
        stdout = result.stdout
        stderr = result.stderr
    except Exception as exc:
        raise RuntimeError(
            f"failed to read product runner status/streams: {exc}"
        ) from exc
    if status is None:
        raise RuntimeError("product runner exit status is None; cannot observe")
    try:
        code = int(status)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"product runner exit status is not an integer: {status!r}"
        ) from exc
    if not isinstance(stdout, str):
        raise TypeError(
            "product runner stdout text is not str; "
            f"got {type(stdout)!r}"
        )
    if not isinstance(stderr, str):
        raise TypeError(
            "product runner stderr text is not str; "
            f"got {type(stderr)!r}"
        )
    return code, stdout, stderr


def product_runner_bytes(result: Any) -> tuple[bytes, bytes]:
    """Return (stdout bytes, stderr bytes) from a product runner result.

    Does not encode the text fields. Missing byte fields or a read
    failure raise — they are not treated as empty captures.
    """
    product_runner_streams(result)
    try:
        stdout_b = result.stdout_bytes
        stderr_b = result.stderr_bytes
    except Exception as exc:
        raise RuntimeError(
            f"failed to read product runner byte captures: {exc}"
        ) from exc
    if not isinstance(stdout_b, (bytes, bytearray)):
        raise TypeError(
            "product runner stdout bytes are missing; "
            f"got {type(stdout_b)!r}"
        )
    if not isinstance(stderr_b, (bytes, bytearray)):
        raise TypeError(
            "product runner stderr bytes are missing; "
            f"got {type(stderr_b)!r}"
        )
    return bytes(stdout_b), bytes(stderr_b)


def require_runner_success_with_marker(result: Any, marker: str) -> None:
    """Product-runner success: status 0, *marker* exactly once on stdout text."""
    if not marker:
        raise ValueError("marker must be a non-empty string")
    code, stdout, stderr = product_runner_streams(result)
    assert code == 0, (
        f"expected success exit 0, got {code}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    count = stdout.count(marker)
    assert count == 1, (
        f"expected marker {marker!r} exactly once on stdout, found {count}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )


def require_runner_success_marker_present(result: Any, marker: str) -> None:
    """Product-runner success: status 0, *marker* at least once on stdout text."""
    if not marker:
        raise ValueError("marker must be a non-empty string")
    code, stdout, stderr = product_runner_streams(result)
    assert code == 0, (
        f"expected success exit 0, got {code}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    count = stdout.count(marker)
    assert count >= 1, (
        f"expected marker {marker!r} on stdout, found {count}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )


def require_runner_text_and_bytes_carry(result: Any, marker: str) -> None:
    """Exit 0; *marker* in stdout text and the same ASCII bytes in stdout bytes."""
    if not marker:
        raise ValueError("marker must be a non-empty string")
    require_runner_success_marker_present(result, marker)
    out_b, _err_b = product_runner_bytes(result)
    marker_b = marker.encode("ascii")
    assert marker_b in out_b, (
        f"marker {marker!r} present in stdout text but missing from "
        f"stdout bytes; stdout_bytes={out_b!r}"
    )


def runner_captured_text(result: Any) -> str:
    """Stdout text plus stderr text from a product runner result.

    An empty string is a real observation (nothing echoed). A failure
    to read either stream raises.
    """
    _code, stdout, stderr = product_runner_streams(result)
    return stdout + stderr


def require_runner_exception_inspectable(result: Any, token: str) -> None:
    """Result carries a truthy exception object on which *token* is visible.

    The status field must be readable. Does not require a non-zero
    status and does not pin an exception type name.
    """
    if not token:
        raise ValueError("token must be a non-empty string")
    product_runner_streams(result)
    try:
        exc = result.exception
    except Exception as err:
        raise RuntimeError(
            f"failed to read product runner exception: {err}"
        ) from err
    assert exc, (
        f"expected an inspectable exception on the result, got {exc!r}"
    )
    try:
        shown = str(exc)
    except Exception as err:
        raise RuntimeError(
            f"failed to observe exception object as text: {err}"
        ) from err
    try:
        pictured = repr(exc)
    except Exception as err:
        raise RuntimeError(
            f"failed to observe exception object repr: {err}"
        ) from err
    assert token in shown or token in pictured, (
        f"exception object does not carry token {token!r}; "
        f"str={shown!r} repr={pictured!r}"
    )


def require_runner_no_exception(result: Any) -> None:
    """Exit 0 and the exception field is absent or false.

    A missing attribute raises — it is not treated as 'no exception'.
    """
    code, stdout, stderr = product_runner_streams(result)
    assert code == 0, (
        f"expected success exit 0 with no exception, got {code}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    try:
        exc = result.exception
    except Exception as err:
        raise RuntimeError(
            f"failed to read product runner exception: {err}"
        ) from err
    assert not exc, (
        f"expected no exception on a successful result, got {exc!r}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )


assert_product_runner_streams = product_runner_streams
assert_product_runner_bytes = product_runner_bytes
assert_runner_success_with_marker = require_runner_success_with_marker
assert_runner_success_marker_present = require_runner_success_marker_present
assert_runner_text_and_bytes_carry = require_runner_text_and_bytes_carry
assert_runner_captured_text = runner_captured_text
assert_runner_exception_inspectable = require_runner_exception_inspectable
assert_runner_no_exception = require_runner_no_exception
