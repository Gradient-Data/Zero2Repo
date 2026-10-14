# feature: F01
"""Feature-local helpers for command invocation, verbs, help, version, and exit status."""

from __future__ import annotations

import os
import re
import secrets
import stat
from pathlib import Path
from typing import Mapping, Sequence

from _harness import (
    MEMCAP_ENV,
    SIMD_ENV,
    HarnessError,
    RunResult,
    Workspace,
    files_identical,
    path_is_file,
    read_bytes,
    read_bytes_if_present,
    same_existing_file,
    token as _harness_token,
    workspace,
)

PRODUCT_NAME = "oggrepack"

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
_VORBIS_FILES = {
    "a": _FIXTURE_DIR / "vorbis_a.ogg",
    "b": _FIXTURE_DIR / "vorbis_b.ogg",
}
_OPUS_FILE = _FIXTURE_DIR / "opus_a.opus"

_SPLIT_TOKENS = re.compile(r"[\s|,]+")
_SIDE_PUNCT = "()[]{}<>\"'`"
# One effort-range pair on a line: -1, then later -9. Separator form is open.
_RANGE_PAIR = re.compile(r"(?<![\d])-1(?!\d).*?(?<![\d])-9(?!\d)")
_EFFORT_NINE = re.compile(r"(?<![\d])-9(?!\d)")
# Interface Contract, version: the identity lines a caller reads.
_RELEASE_LINE = re.compile(r"^oggrepack (\S*\d\S*)(?: .*)?$")
_BUILD_HOST_LINE = re.compile(r"^host: (\S+)$")
_OPUS_MODE_LINE = re.compile(r"^opus: \S.*$")
_DISPATCH_LINE = re.compile(r"^dispatch: (\S+)$")
# PRD: on Unix/Linux, batch compress names the archive by appending `.orp`.
BATCH_ARCHIVE_SUFFIX = ".orp"

REQUIRED_HELP_NAMES = (
    "e",
    "d",
    "dump",
    "pages",
    "batch",
    "jobs",
    "progress",
    "progress-lines",
    "no-mmap",
    "0",
    "1",
    "2",
    "3",
    "4",
)

_KNOWN_SHORT = frozenset("hvbpj123456789")
# Interface Contract: ORP_SIMD values and version ``dispatch:`` paths.
SIMD_PORTABLE = "portable"
SIMD_NATIVE = "native"
_LEGAL_SIMD = frozenset({SIMD_PORTABLE, SIMD_NATIVE})


def token(nbytes: int = 6) -> str:
    """Fresh lowercase hex token for runtime-unique fixtures.

    Downstream suites import this name. The byte-count default matches the
    shared harness. Does not contact the product.
    """
    return _harness_token(nbytes)


def unique_name(prefix: str) -> str:
    """Return a runtime-unique relative name. Does not create a file."""
    return f"{prefix}-{token()}"


def run_product(
    ws: Workspace,
    args: Sequence[str],
    env_updates: Mapping[str, str | None] | None = None,
) -> RunResult:
    """Invoke the product in *ws*. A non-zero exit is a result, not an exception."""
    result = ws.invoke(args, env_updates=env_updates)
    print(
        f"[F01] argv={list(args)!r} exit={result.returncode} "
        f"stdout_len={len(result.stdout)} stderr_len={len(result.stderr)}",
        flush=True,
    )
    return result


def require_status(result: RunResult, code: int, *, stderr_required: bool) -> None:
    """Assert *result* has *code*. When required, stderr must be non-empty."""
    assert result.returncode == code, (
        f"expected exit {code}, got {result.returncode}; "
        f"stderr={result.stderr!r} stdout={result.stdout!r}"
    )
    if stderr_required:
        assert result.stderr, (
            f"expected non-empty stderr for exit {code}; stdout={result.stdout!r}"
        )


def require_ok(result: RunResult) -> None:
    require_status(result, 0, stderr_required=False)


def require_refusal(result: RunResult) -> None:
    require_status(result, 1, stderr_required=True)


def require_usage(result: RunResult) -> None:
    require_status(result, 2, stderr_required=True)


def require_file_access(result: RunResult) -> None:
    require_status(result, 3, stderr_required=True)


def require_stdout_text(result: RunResult) -> str:
    """Return decoded stdout. Empty stdout is an assertion failure, not a sentinel."""
    text = result.stdout_text
    assert text, f"expected non-empty stdout; stderr={result.stderr!r}"
    return text


def cli_tokens(text: str) -> set[str]:
    """Split *text* on whitespace, `|`, and `,`; keep hyphenated option names.

    Surrounding bracket punctuation is stripped. A token that begins with `--`
    also contributes its option stem (leading dashes removed, text after `=`
    dropped). Split failure raises rather than returning an empty set that
    could pass for "names are absent".
    """
    if not isinstance(text, str):
        raise HarnessError(f"cli_tokens expected str, got {type(text)!r}")
    pieces: set[str] = set()
    for raw in _SPLIT_TOKENS.split(text):
        piece = raw.strip().strip(_SIDE_PUNCT)
        if not piece:
            continue
        pieces.add(piece)
        if piece.startswith("--"):
            stem = piece.lstrip("-")
            if "=" in stem:
                stem = stem.split("=", 1)[0]
            if stem:
                pieces.add(stem)
    return pieces


def help_has_required_names(text: str) -> None:
    """Assert help stdout names the verbs, option stems, and status-class digits."""
    tokens = cli_tokens(text)
    missing = [name for name in REQUIRED_HELP_NAMES if name not in tokens]
    assert not missing, (
        f"help stdout missing required whole tokens {missing}; "
        f"have={sorted(tokens)}"
    )


def _strip_effort_range_pairs(text: str) -> str:
    """Remove ``-1``…``-9`` range pairs per line. A leftover ``-9`` is the default.

    The characters between the endpoints are not pinned: a usage summary may
    write the range with dots, dashes, or a word. A lone ``-9`` that is not
    the second half of such a pair is left in place.
    """
    if not isinstance(text, str):
        raise HarnessError(f"usage text expected str, got {type(text)!r}")
    return "".join(
        _RANGE_PAIR.sub(" ", line) for line in text.splitlines(keepends=True)
    )


def require_help_usage(text: str) -> None:
    """Assert help names usage elements, including that default effort is -9.

    Already-cleared arms: four verbs, effort endpoints ``-1`` and ``-9``,
    option stems, and the five status-class digits. Default effort is a
    second naming of the option ``-9`` after each line's range pair is
    removed. No language word is required.
    """
    help_has_required_names(text)
    for mark in ("-1", "-9"):
        assert mark in text, f"help stdout does not name effort option {mark!r}"
    remainder = _strip_effort_range_pairs(text)
    assert _EFFORT_NINE.search(remainder), (
        "help stdout does not name that the default effort is -9"
    )


def workspace_regular_files(ws: Workspace) -> frozenset[str]:
    """Relative POSIX paths of regular files under the workspace.

    Walk or stat failure raises. An empty set means a successful listing of
    no regular files — never a disguised I/O failure.
    """
    root = ws.path.resolve()
    found: set[str] = set()
    try:
        for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
            for name in filenames:
                path = Path(dirpath) / name
                try:
                    info = path.lstat()
                except OSError as exc:
                    raise HarnessError(f"cannot stat {path}: {exc}") from exc
                if stat.S_ISREG(info.st_mode):
                    found.add(path.relative_to(root).as_posix())
    except HarnessError:
        raise
    except OSError as exc:
        raise HarnessError(f"cannot walk workspace {root}: {exc}") from exc
    return frozenset(found)


def named_archive_files(ws: Workspace) -> frozenset[str]:
    """Regular files whose names use the PRD batch-archive suffix ``.orp``."""
    return frozenset(
        rel
        for rel in workspace_regular_files(ws)
        if rel.endswith(BATCH_ARCHIVE_SUFFIX)
    )


def derived_batch_archive(input_rel: str) -> str:
    """Return the Unix/Linux batch compress destination for *input_rel*."""
    return f"{input_rel}{BATCH_ARCHIVE_SUFFIX}"


def require_no_new_archives(before: frozenset[str], after: frozenset[str]) -> None:
    """Assert no new PRD-named archive files appeared."""
    added = after - before
    assert not added, f"archive written after usage error: {sorted(added)}"


def run_expect_usage(
    ws: Workspace,
    args: Sequence[str],
    env_updates: Mapping[str, str | None] | None = None,
) -> RunResult:
    """Run *args* and require a usage error (exit 2 and non-empty stderr)."""
    result = run_product(ws, args, env_updates=env_updates)
    require_usage(result)
    return result


def run_expect_usage_no_archive(
    ws: Workspace,
    args: Sequence[str],
    env_updates: Mapping[str, str | None] | None = None,
) -> RunResult:
    """Usage error with no new PRD-named archive file in the workspace."""
    before = named_archive_files(ws)
    result = run_expect_usage(ws, args, env_updates=env_updates)
    require_no_new_archives(before, named_archive_files(ws))
    return result


def _vorbis_bytes(which: str) -> bytes:
    try:
        path = _VORBIS_FILES[which]
    except KeyError as exc:
        raise HarnessError(f"unknown Vorbis fixture id {which!r}") from exc
    if not path.is_file():
        raise HarnessError(f"suite fixture missing: {path}")
    try:
        return read_bytes(path)
    except FileNotFoundError as exc:
        raise HarnessError(f"suite fixture missing: {path}") from exc


def place_vorbis(ws: Workspace, which: str) -> str:
    """Copy a suite-owned short Ogg Vorbis file to a unique workspace path."""
    data = _vorbis_bytes(which)
    other = "b" if which == "a" else "a"
    other_data = _vorbis_bytes(other)
    if data == other_data:
        raise HarnessError("suite Vorbis fixtures must differ in bytes")
    rel = f"{unique_name('vorbis-' + which)}.ogg"
    ws.write(rel, data)
    return rel


def _opus_bytes() -> bytes:
    path = _OPUS_FILE
    if not path.is_file():
        raise HarnessError(f"suite fixture missing: {path}")
    try:
        return read_bytes(path)
    except FileNotFoundError as exc:
        raise HarnessError(f"suite fixture missing: {path}") from exc


def place_opus(ws: Workspace) -> str:
    """Copy a suite-owned short Ogg Opus file to a unique workspace path."""
    data = _opus_bytes()
    if not data.startswith(b"OggS"):
        raise HarnessError("suite Opus fixture is not an Ogg bitstream")
    rel = f"{unique_name('opus')}.opus"
    ws.write(rel, data)
    return rel


def place_non_ogg(ws: Workspace) -> str:
    """Write a runtime-random non-Ogg regular file and return its relative path."""
    rel = f"{unique_name('notogg')}.bin"
    data = secrets.token_bytes(64)
    if data.startswith(b"OggS"):
        data = b"X" + data[1:]
    ws.write(rel, data)
    return rel


def place_placeholder(ws: Workspace) -> str:
    """Write a small existing regular file used only as a path operand."""
    rel = unique_name("hold")
    ws.write(rel, secrets.token_bytes(16))
    return rel


def unknown_verb() -> str:
    """Runtime token that is not a published verb."""
    while True:
        word = token()
        if word not in {"e", "d", "dump", "pages"}:
            return word


def unknown_long_option() -> str:
    """Runtime unknown long option (``--`` plus a fresh token)."""
    return f"--{token()}"


def unknown_short_option() -> str:
    """Runtime unknown short option, excluding published shorts and ``-0``…``-9``."""
    letters = [c for c in "abcdefghijklmnopqrstuvwxyz" if c not in _KNOWN_SHORT]
    if not letters:
        raise HarnessError("no unused short-option letters remain")
    return f"-{secrets.choice(letters)}"


def jobs_trailing_value() -> str:
    """``--jobs`` value: a digit prefix plus runtime letters (not a bare integer).

    ``token()`` is lowercase hex and can be all digits. A digits-only value is
    a legal positive jobs count (PRD: no sign and no trailing text), so the
    trailing portion must include a letter.
    """
    letters = "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(4))
    value = f"1{letters}"
    if value.isdigit():
        raise HarnessError(
            f"jobs trailing value collapsed to a bare integer: {value!r}"
        )
    return value


def malformed_memcap_runtime() -> str:
    """Non-empty value that is not a non-negative integer."""
    return f"{token()[:4]}q"


def invalid_simd_token() -> str:
    """Runtime ORP_SIMD value outside the published legal set."""
    while True:
        word = token()
        if word not in _LEGAL_SIMD:
            return word


def require_path_absent(ws: Workspace, relpath: str) -> None:
    """Assert *relpath* is classified absent. Other I/O failures raise."""
    found = ws.read_bytes_if_present(relpath)
    assert found is None, f"path {relpath!r} exists after a usage or access failure"


def require_bytes_unchanged(ws: Workspace, relpath: str, before: bytes) -> None:
    after = ws.read_bytes(relpath)
    assert after == before, f"bytes of {relpath!r} changed"


def _version_lines(text: str) -> list[str]:
    if not isinstance(text, str):
        raise HarnessError(f"expected str, got {type(text)!r}")
    return [line.strip() for line in text.splitlines() if line.strip()]


def version_release(version_text: str) -> str:
    """``<release>`` of the Contract line ``oggrepack <release>[ ...]``."""
    found = [m.group(1) for line in _version_lines(version_text)
             if (m := _RELEASE_LINE.match(line))]
    assert found, (
        "version stdout has no line `oggrepack <release>` naming a release "
        f"identifier; stdout={version_text!r}"
    )
    return found[0]


def version_build_host(version_text: str) -> str:
    """``<host-triple>`` of the Contract line ``host: <host-triple>``."""
    found = [m.group(1) for line in _version_lines(version_text)
             if (m := _BUILD_HOST_LINE.match(line))]
    assert len(found) == 1, (
        "version stdout does not carry exactly one `host: <host-triple>` "
        f"line; stdout={version_text!r}"
    )
    return found[0]


def opus_mode_lines(version_text: str) -> list[str]:
    """Contract ``opus: <component>`` lines of version stdout."""
    return [line for line in _version_lines(version_text) if _OPUS_MODE_LINE.match(line)]


def version_dispatch(version_text: str) -> str:
    """``<path>`` of the Contract version line ``dispatch: <path>``."""
    found = [m.group(1) for line in _version_lines(version_text)
             if (m := _DISPATCH_LINE.match(line))]
    assert len(found) == 1, (
        "version stdout does not carry exactly one `dispatch: <path>` line; "
        f"stdout={version_text!r}"
    )
    assert found[0] in _LEGAL_SIMD, (
        f"dispatched path {found[0]!r} is not one of {sorted(_LEGAL_SIMD)}"
    )
    return found[0]


def require_compiled_in_identity_field(
    version_text: str, help_text: str
) -> tuple[str, ...]:
    """Version carries the ``opus:`` line (Opus is compiled in).

    This product supports Ogg Opus, so the present arm is required; the
    line is version identity, not help usage.
    """
    lines = opus_mode_lines(version_text)
    assert len(lines) == 1, (
        "version stdout does not carry exactly one `opus: <component>` "
        "line although Ogg Opus encode and decode are compiled in; "
        f"stdout={version_text!r}"
    )
    help_lines = set(_version_lines(help_text))
    assert lines[0] not in help_lines, (
        "the `opus:` line is part of help output, not version identity"
    )
    return tuple(lines)


def require_version_identity(version_text: str, help_text: str) -> None:
    """Assert version stdout names product, release, host, Opus, and code path.

    Reads the Contract's version lines. The build host is the configure host
    triple; its CPU part is this machine's ``uname -m``.
    """
    version_tokens = cli_tokens(version_text)
    assert PRODUCT_NAME in version_tokens, (
        f"version stdout does not name the product as a whole token; "
        f"tokens={sorted(version_tokens)}"
    )
    version_release(version_text)
    host = version_build_host(version_text)
    machine = os.uname().machine.lower()
    parts = host.lower().split("-")
    assert len(parts) >= 3 and parts[0] == machine, (
        f"build host {host!r} is not a configure host triple "
        f"`<cpu>-<vendor>-<os>` for this machine ({machine})"
    )
    require_compiled_in_identity_field(version_text, help_text)
    version_dispatch(version_text)


def require_stderr_identifies_path_failure(result: RunResult, path: str) -> None:
    """Assert the file-access diagnostic on stderr contains the path."""
    text = result.stderr_text
    assert text, f"expected non-empty stderr; stdout={result.stdout!r}"
    assert path in text, (
        f"the file-access diagnostic does not contain the path {path!r}; "
        f"stderr={text!r}"
    )


__all__ = (
    "BATCH_ARCHIVE_SUFFIX",
    "MEMCAP_ENV",
    "PRODUCT_NAME",
    "REQUIRED_HELP_NAMES",
    "SIMD_ENV",
    "SIMD_NATIVE",
    "SIMD_PORTABLE",
    "HarnessError",
    "cli_tokens",
    "derived_batch_archive",
    "files_identical",
    "help_has_required_names",
    "invalid_simd_token",
    "jobs_trailing_value",
    "malformed_memcap_runtime",
    "named_archive_files",
    "opus_mode_lines",
    "path_is_file",
    "place_non_ogg",
    "place_opus",
    "place_placeholder",
    "place_vorbis",
    "read_bytes",
    "read_bytes_if_present",
    "require_bytes_unchanged",
    "require_compiled_in_identity_field",
    "require_file_access",
    "require_help_usage",
    "require_no_new_archives",
    "require_ok",
    "require_path_absent",
    "require_refusal",
    "require_status",
    "require_stderr_identifies_path_failure",
    "require_stdout_text",
    "require_usage",
    "require_version_identity",
    "run_expect_usage",
    "run_expect_usage_no_archive",
    "run_product",
    "same_existing_file",
    "token",
    "unique_name",
    "unknown_long_option",
    "unknown_short_option",
    "unknown_verb",
    "version_build_host",
    "version_release",
    "version_dispatch",
    "workspace",
    "workspace_regular_files",
)
