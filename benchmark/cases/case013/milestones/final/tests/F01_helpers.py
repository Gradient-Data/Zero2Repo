# feature: F01
"""Observation helpers for the membundle init command (FP-01).

Every public name here is an observation of files or of a ``RunResult``
from ``membundle init``. Helpers raise ``HarnessError`` when a query cannot be
classified, and ``AssertionError`` when a classified observation misses a
carrier the tests require. They never return ``None`` / ``{}`` / ``""`` to
mean "could not look".
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path

from _harness import (
    HarnessError,
    RunResult,
    Workspace,
    list_dir,
    path_is_dir,
    path_is_file,
    read_file,
    utc_today_iso,
)

_ISO_DATETIME = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Pids / run counters: two or more digits as a whole token. Single digits
# around a version like 0.2 must survive.
_DIGIT_TOKEN = re.compile(r"\b\d{2,}\b")
_WRAP_PUNCT = re.compile(r"[\"'`]+")
_ATX = re.compile(r"^(#{1,6})(?:[ \t]+(.+?))?[ \t]*#*[ \t]*$")
_SETEXT_UNDER = re.compile(r"^(?:=+|-+)[ \t]*$")
_LIST_ITEM = re.compile(r"^[ \t]*(?:[*+\-]|\d+[.)])[ \t]+(.*)$")
_VERSION_KEY = re.compile(r"^[ \t]*membundle_version[ \t]*:(.*)$")
_ISO_HEADING = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SKILL_REL = Path(".agents") / "skills" / "membundle-memory"
_RESERVED_ROOT_MD = frozenset({"log.md", "AGENTS.md"})
# Recipe artifact name. The binary is built in a writable copy, not the judge cwd.
_BIN_REL = Path("bin") / "membundle"
_BUILD_LOCK = threading.Lock()
_BUILD_DONE = False
_BUILT_BIN: Path | None = None


def unique_leaf(prefix: str) -> str:
    """Return a runtime-unique directory leaf that is not an MEMBUNDLE/version token."""
    for _ in range(8):
        leaf = f"{prefix}-{uuid.uuid4().hex}"
        lowered = leaf.lower()
        if "membundle" in lowered or "0.2" in leaf:
            continue
        return leaf
    raise HarnessError(
        f"could not generate a leaf from prefix {prefix!r} without "
        f"MEMBUNDLE/version tokens (choose a prefix that does not contain them)"
    )


def _workdir_has_product_sources(root: Path) -> bool:
    """True when *root* is a product tree: a Go module (``go.mod``) with a root
    ``Makefile`` (Contract "Build": ``make build`` at the root writes
    ``bin/membundle``). The Makefile's text is not read."""
    return (root / "Makefile").is_file() and (root / "go.mod").is_file()


def stage_writable_sources(root: Path) -> Path:
    """Copy *root* to a writable directory, excluding any existing binary.

    The judge cwd is not writable by the judge user, so ``make build`` must
    not run there, and a binary already present under that cwd must not be
    reused. Same staging as the F04-F10 helpers.
    """
    stage = Path(tempfile.mkdtemp(prefix="membundle-build-"))
    shutil.copytree(
        root,
        stage,
        symlinks=True,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".git", "bin"),
    )
    for dirpath, _dirnames, filenames in os.walk(stage):
        os.chmod(dirpath, os.stat(dirpath).st_mode | 0o700)
        for name in filenames:
            path = Path(dirpath) / name
            if path.is_symlink():
                continue
            os.chmod(path, path.stat().st_mode | 0o600)
    prebuilt = stage / _BIN_REL
    if prebuilt.is_symlink() or prebuilt.exists():
        prebuilt.unlink()
    return stage


def _run_product_build(root: Path) -> None:
    """Run ``GOFLAGS=-buildvcs=false make build`` in a writable copy of the judge workdir.

    Uses the Go toolchain and module cache already in the environment.
    A build that does not produce the binary is not a substrate exception;
    callers then observe the missing init results.
    """
    env = dict(os.environ)
    env["GOFLAGS"] = "-buildvcs=false"
    print(f"[F01] GOFLAGS=-buildvcs=false make build cwd={root}", flush=True)
    try:
        completed = subprocess.run(
            ["make", "build"],
            cwd=str(root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        print(f"[F01] make build could not start: {exc}", flush=True)
        return
    print(f"[F01] make build exit={completed.returncode}", flush=True)
    if completed.returncode != 0:
        print(
            f"[F01] make build stdout={completed.stdout[-2000:]!r} "
            f"stderr={completed.stderr[-2000:]!r}",
            flush=True,
        )


def _workdir_membundle() -> Path | None:
    """Return the ``bin/membundle`` built from the judge workdir sources.

    The judge workdir is the pytest process cwd. Its sources are built in a
    writable copy (``stage_writable_sources``). Does not search ``PATH``,
    does not honor ``PRODUCT_BIN``, and does not use a binary this build did
    not just produce. An empty workdir therefore has no executable. The
    build runs once per process when the workdir contains the product sources.
    """
    global _BUILD_DONE, _BUILT_BIN
    with _BUILD_LOCK:
        if not _BUILD_DONE:
            root = Path.cwd().resolve()
            candidate: Path | None = None
            if _workdir_has_product_sources(root):
                stage = stage_writable_sources(root)
                _run_product_build(stage)
                candidate = (stage / _BIN_REL).resolve()
            if (
                candidate is not None
                and candidate.is_file()
                and os.access(candidate, os.X_OK)
            ):
                _BUILT_BIN = candidate
            else:
                _BUILT_BIN = None
            _BUILD_DONE = True
            print(f"[F01] resolved workdir binary={_BUILT_BIN!r}", flush=True)
        return _BUILT_BIN


def _init_without_executable(
    ws: Workspace,
    args: Sequence[str],
    cwd: str | Path | None,
) -> RunResult:
    """Non-success init outcome with no report and no files written.

    Existing init-result assertions fail on this outcome because the target
    index and log were not written and the process did not report that an
    MEMBUNDLE v0.2 bundle was initialized.
    """
    if cwd is not None:
        workdir = str(Path(cwd).resolve())
    else:
        workdir = str(ws.path)
    return RunResult(
        returncode=1,
        stdout=b"",
        stderr=b"",
        argv=("membundle", *args),
        cwd=workdir,
    )


def run_init(
    ws: Workspace,
    extra_args: Sequence[str] = (),
    env_updates: dict[str, str | None] | None = None,
    cwd: str | Path | None = None,
) -> RunResult:
    """Invoke ``membundle init`` with optional path arguments. No other flags.

    Builds ``bin/membundle`` from a writable copy of the judge workdir when it contains
    the product sources, then runs only that binary. When it is still absent,
    returns a failed init result instead of raising ``FileNotFoundError``.
    """
    args = ["init", *[str(a) for a in extra_args]]
    print(f"[F01] init extra_args={list(extra_args)!r} cwd={cwd!r}", flush=True)
    binary = _workdir_membundle()
    if binary is None:
        # TEST-FIX(F01): with no bin/membundle there is no product to run; per the Contract "Build" form, make build at the repository root writes that binary.
        return _init_without_executable(ws, args, cwd)
    try:
        return ws.invoke(args, env_updates=env_updates, cwd=cwd, binary=binary)
    except FileNotFoundError:
        # TEST-FIX(F01): with no bin/membundle there is no product to run; per the Contract "Build" form, make build at the repository root writes that binary.
        if binary.is_file() and os.access(binary, os.X_OK):
            raise
        return _init_without_executable(ws, args, cwd)


def run_init_with_dates(
    ws: Workspace,
    extra_args: Sequence[str] = (),
    env_updates: dict[str, str | None] | None = None,
    cwd: str | Path | None = None,
) -> tuple[RunResult, frozenset[str]]:
    """Run init and capture the host UTC dates spanning the invoke."""
    before = utc_today_iso()
    result = run_init(
        ws, extra_args=extra_args, env_updates=env_updates, cwd=cwd
    )
    after = utc_today_iso()
    return result, utc_dates_spanning_invoke(before, after)


def combined_report(result: RunResult) -> str:
    """UTF-8 stdout+stderr. Decode failure raises ``HarnessError``."""
    return result.stdout_text + result.stderr_text


def names_membundle_and_version(text: str) -> bool:
    """True when *text* names the format and version ``0.2`` / ``v0.2``.

    The format may be spelled as the contiguous token ``membundle`` in any
    case, or as the phrase ``Open Bundle Format`` in any case.
    Contiguous uppercase ``MEMBUNDLE`` is accepted but not required.
    """
    lowered = text.lower()
    has_format = ("membundle" in lowered) or ("open bundle format" in lowered)
    has_version = ("0.2" in text) or ("v0.2" in text)
    return has_format and has_version


INIT_FAILURE_PREFIX = "Error initializing bundle: "


def init_named_path(result: RunResult) -> str | None:
    """The path argument this test passed to ``init`` (``None`` when omitted).

    Read from the test's own argument vector, not from product output.
    """
    args = list(result.argv[2:])
    if args and not args[0].startswith("-"):
        return args[0]
    return None


def init_success_names_path(report: str, path: str) -> bool:
    """Contract Output forms, ``init``: the one success line contains ``'<path>'``."""
    return f"'{path}'" in report


def require_init_success(
    result: RunResult, expected_path: str | None = None
) -> str:
    """Success carrier: status 0 and the stated one-line success report.

    Contract Output forms, ``init``: success prints exactly one line on
    standard output that contains ``'<path>'`` (other wording free), and
    nothing on standard error. PRD FP-01: the report states that an
    MEMBUNDLE v0.2 bundle was initialized at the target path, so the line
    also names the format and version. ``<path>`` is the named path; an
    omit-path caller passes the default bundle path (``knowledge`` or ``.``)
    it set up.
    """
    named = init_named_path(result)
    path = named if named is not None else expected_path
    if path is None:
        raise HarnessError(
            "omit-path init: caller must pass the expected default bundle path"
        )
    stdout = result.stdout_text
    stderr = result.stderr_text
    expected = f"'{path}'"
    print(
        f"[F01] success-carrier exit={result.returncode} stdout={stdout!r} "
        f"stderr={stderr!r} expected-path={expected!r}",
        flush=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"init did not end successfully (exit {result.returncode}); "
            f"stdout={stdout!r} stderr={stderr!r}"
        )
    if not stdout.endswith("\n") or stdout.count("\n") != 1:
        raise AssertionError(
            f"init success output is not exactly one line: {stdout!r}"
        )
    if not init_success_names_path(stdout, path):
        raise AssertionError(
            f"init success line does not contain {expected!r}: {stdout!r}"
        )
    if not names_membundle_and_version(stdout):
        raise AssertionError(
            f"init success line does not name the format and version 0.2: {stdout!r}"
        )
    if stderr:
        raise AssertionError(
            f"init success wrote on standard error: {stderr!r}"
        )
    return stdout


def require_init_failure(
    result: RunResult,
    success_report: str | None = None,
    path_tokens: Sequence[str] = (),
) -> str:
    """Failure carrier: the stated ``init`` failure form.

    Contract Output forms, failure classes: ``init`` failure is status ``1``
    with a standard-error line that begins ``Error initializing bundle: ``.
    *success_report* and *path_tokens* are accepted for call compatibility
    and are not read.
    """
    del success_report, path_tokens
    stderr = result.stderr_text
    print(
        f"[F01] failure-carrier exit={result.returncode} "
        f"stdout={result.stdout_text!r} stderr={stderr!r}",
        flush=True,
    )
    assert result.returncode == 1, (
        f"init of an uncreatable target did not end with status 1 "
        f"(exit {result.returncode}); stderr={stderr!r}"
    )
    assert any(
        line.startswith(INIT_FAILURE_PREFIX) for line in stderr.splitlines()
    ), (
        f"init failure has no standard-error line beginning "
        f"{INIT_FAILURE_PREFIX!r}: {stderr!r}"
    )
    return stderr


def strip_generated_covariates(report: str) -> str:
    """Strip ISO dates/date-times, wrapping quotes, and digit-only counters.

    Does not strip directory basenames.
    """
    text = _ISO_DATETIME.sub("", report)
    text = _ISO_DATE.sub("", text)
    text = _WRAP_PUNCT.sub("", text)
    text = _DIGIT_TOKEN.sub("", text)
    return text


def report_remainder_after_stripping_paths(
    report: str, paths: Sequence[str]
) -> str:
    """Remove path spellings and their basenames from *report*.

    A standalone ``.`` path token is removed without eating the dot inside
    ``0.2``.
    """
    tokens: list[str] = []
    for raw in paths:
        if not raw:
            continue
        text = str(raw)
        tokens.append(text)
        tokens.append(text.replace("\\", "/"))
        base = os.path.basename(text.rstrip("/\\"))
        if base:
            tokens.append(base)
    seen: set[str] = set()
    ordered: list[str] = []
    for tok in sorted(tokens, key=len, reverse=True):
        if not tok or tok == "." or tok in seen:
            continue
        seen.add(tok)
        ordered.append(tok)
    remainder = report
    for tok in ordered:
        remainder = remainder.replace(tok, "")
    remainder = re.sub(r"(?<![A-Za-z0-9])\.(?![A-Za-z0-9])", "", remainder)
    return remainder


def split_yaml_frontmatter(text: str) -> tuple[str, str]:
    """Split conventional ``---`` fences into ``(mapping_text, body)``.

    Raises ``HarnessError`` when opening or closing fences are missing.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise HarnessError(
            "frontmatter does not begin with a triple-dash fence line"
        )
    closing: int | None = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing = index
            break
    if closing is None:
        raise HarnessError("frontmatter has no closing triple-dash fence")
    mapping_text = "\n".join(lines[1:closing])
    body = "\n".join(lines[closing + 1 :])
    return mapping_text, body


def membundle_version_declared(mapping_text: str) -> str:
    """Return the stripped ``membundle_version`` scalar from a YAML mapping.

    Line-oriented key read: blank lines and comment-only lines are skipped.
    Surrounding YAML quotes on the scalar are stripped. Raises
    ``HarnessError`` if the key is absent. Does not substring-search the
    fenced block.
    """
    for line in mapping_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        match = _VERSION_KEY.match(line)
        if match is None:
            continue
        scalar = match.group(1).strip()
        if (
            len(scalar) >= 2
            and scalar[0] == scalar[-1]
            and scalar[0] in "\"'"
        ):
            scalar = scalar[1:-1].strip()
        return scalar
    raise HarnessError("membundle_version mapping key is absent")


def first_heading_text(markdown: str) -> str:
    """Return the first Markdown heading's text (ATX or Setext).

    Markers and optional closing ATX hashes are stripped. Raises
    ``HarnessError`` if there is no heading with non-empty text. Callers
    pass the split body for an index, never the raw file with YAML.
    """
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        atx = _ATX.match(line)
        if atx is not None and line.lstrip().startswith("#"):
            text = (atx.group(2) or "").strip()
            if text:
                return text
            continue
        if index + 1 < len(lines) and _SETEXT_UNDER.match(lines[index + 1]):
            text = line.strip()
            if text:
                return text
    raise HarnessError("markdown has no heading with non-empty text")


def _heading_content_starts(lines: list[str]) -> list[int]:
    """Line indices where heading content begins (the line after the marker)."""
    starts: list[int] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        atx = _ATX.match(line)
        if atx is not None and line.lstrip().startswith("#"):
            text = (atx.group(2) or "").strip()
            if text:
                starts.append(index + 1)
                index += 1
                continue
        if index + 1 < len(lines) and _SETEXT_UNDER.match(lines[index + 1]):
            if line.strip():
                starts.append(index + 2)
                index += 2
                continue
        index += 1
    return starts


def dated_section_after_first_heading(log_markdown: str) -> str:
    """Text after the first heading until the next heading or EOF.

    Raises ``HarnessError`` if there is no first heading.
    """
    # Confirm a first heading exists (raises otherwise).
    first_heading_text(log_markdown)
    lines = log_markdown.splitlines()
    starts = _heading_content_starts(lines)
    if not starts:
        raise HarnessError("log has no first heading section")
    begin = starts[0]
    # *starts[1]* is the first content line of heading 2. Cut the section
    # at the next heading's marker line.
    if len(starts) > 1:
        end = _heading_marker_line(lines, starts[1])
    else:
        end = len(lines)
    return "\n".join(lines[begin:end])


def _heading_marker_line(lines: list[str], content_start: int) -> int:
    """Return the line index of the heading whose content starts at *content_start*."""
    if content_start <= 0:
        return 0
    prev = lines[content_start - 1]
    if _SETEXT_UNDER.match(prev) and content_start >= 2:
        return content_start - 2
    return content_start - 1


def dated_section_has_membundle_list_item(section: str) -> bool:
    """True when a list item in *section* names the format and 0.2/v0.2."""
    for line in section.splitlines():
        match = _LIST_ITEM.match(line)
        if match is None:
            continue
        item = match.group(1)
        if names_membundle_and_version(item):
            return True
    return False


def list_markdown_relative(bundle_dir: str | Path) -> list[str]:
    """Sorted bundle-relative ``.md`` paths. Raises if *bundle_dir* is not a directory."""
    root = Path(bundle_dir)
    if not path_is_dir(root):
        raise HarnessError(f"not a directory, cannot list markdown: {root}")
    found: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if not name.endswith(".md"):
                continue
            full = Path(dirpath) / name
            found.append(full.relative_to(root).as_posix())
    return sorted(found)


def concept_markdown_relative(bundle_dir: str | Path) -> list[str]:
    """``.md`` paths that are not reserved documents."""
    extra: list[str] = []
    for rel in list_markdown_relative(bundle_dir):
        name = Path(rel).name
        if name == "index.md":
            continue
        if rel in _RESERVED_ROOT_MD:
            continue
        extra.append(rel)
    return extra


def assert_index_structure(index_path: str | Path) -> None:
    """B observations: version **key** scalar ``0.2`` and a body heading."""
    text = read_file(index_path)
    mapping, body = split_yaml_frontmatter(text)
    version = membundle_version_declared(mapping)
    print(
        f"[F01] index {index_path} membundle_version={version!r} body_len={len(body)}",
        flush=True,
    )
    if version != "0.2":
        raise AssertionError(
            f"membundle_version scalar is {version!r}, expected 0.2"
        )
    heading = first_heading_text(body)
    if not heading.strip():
        raise AssertionError("index body heading text is empty")
    print(f"[F01] index body heading={heading!r}", flush=True)


def assert_log_structure(
    log_path: str | Path,
    allowed_dates: frozenset[str] | None = None,
) -> None:
    """C observations: UTC ISO first heading and dated-section format item."""
    dates = allowed_dates if allowed_dates is not None else frozenset({utc_today_iso()})
    text = read_file(log_path)
    heading = first_heading_text(text)
    print(
        f"[F01] log {log_path} first_heading={heading!r} allowed={sorted(dates)}",
        flush=True,
    )
    if _ISO_HEADING.fullmatch(heading) is None:
        raise AssertionError(
            f"log first heading is not ISO 8601 YYYY-MM-DD: {heading!r}"
        )
    if heading not in dates:
        raise AssertionError(
            f"log first heading {heading!r} is not today's UTC date "
            f"among {sorted(dates)}"
        )
    section = dated_section_after_first_heading(text)
    print(f"[F01] dated section={section!r}", flush=True)
    if not dated_section_has_membundle_list_item(section):
        raise AssertionError(
            "dated heading section has no list item naming the format "
            "and 0.2/v0.2"
        )


def assert_init_scaffold(
    bundle_dir: str | Path,
    allowed_dates: frozenset[str] | None = None,
) -> None:
    """B/C file observations on a bundle that should have both root files."""
    root = Path(bundle_dir)
    if not path_is_dir(root):
        raise AssertionError(f"init target directory does not exist: {root}")
    index_path = root / "index.md"
    log_path = root / "log.md"
    if not path_is_file(index_path):
        raise AssertionError(f"missing root index.md under {root}")
    if not path_is_file(log_path):
        raise AssertionError(f"missing root log.md under {root}")
    assert_index_structure(index_path)
    assert_log_structure(log_path, allowed_dates=allowed_dates)


def assert_bare_bundle_layout(bundle_dir: str | Path) -> None:
    """I checks: no extra concepts, no root AGENTS.md, Makefile, or skill tree.

    Does not fail solely because a nested ``index.md`` exists.
    """
    root = Path(bundle_dir)
    extras = concept_markdown_relative(root)
    if extras:
        raise AssertionError(
            f"init created extra concept markdown files: {extras}"
        )
    names = list_dir(root)
    if "AGENTS.md" in names:
        raise AssertionError("init created root AGENTS.md")
    if "Makefile" in names:
        raise AssertionError("init created a Makefile")
    skill = root / _SKILL_REL
    if path_is_dir(skill):
        raise AssertionError(
            "init created .agents/skills/membundle-memory/"
        )


def utc_dates_spanning_invoke(before: str, after: str) -> frozenset[str]:
    """Host UTC calendar dates observed immediately before and after an invoke."""
    return frozenset({before, after})


def _require_zone_effective(tz_value: str, offset_hours: int) -> None:
    """Raise ``HarnessError`` unless ``TZ=tz_value`` really shifts local time.

    A zone the environment cannot resolve (for example a missing zoneinfo
    database, or a POSIX string a program does not parse) silently falls
    back to UTC. The local date would then equal the UTC date and every
    UTC-versus-local contrast built on it would pass vacuously. A fresh
    interpreter with only ``TZ`` set must report the expected UTC offset.
    """
    zone_file = Path("/usr/share/zoneinfo") / tz_value
    if not zone_file.is_file():
        raise HarnessError(
            f"zoneinfo database has no {tz_value!r} at {zone_file}; a TZ "
            "contrast in this environment would silently be UTC"
        )
    probe = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import time; print(time.localtime().tm_gmtoff)",
        ],
        env={"TZ": tz_value, "PATH": os.environ.get("PATH", "")},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    reported = probe.stdout.decode("utf-8", errors="replace").strip()
    expected = str(offset_hours * 3600)
    if probe.returncode != 0 or reported != expected:
        raise HarnessError(
            f"TZ={tz_value!r} is not effective in this environment: local "
            f"UTC offset is {reported!r} seconds, expected {expected}; "
            f"stderr={probe.stderr[-400:]!r}"
        )


def tz_offset_where_local_date_differs() -> tuple[str, str]:
    """Pick a zoneinfo ``TZ`` whose local calendar date is not today's UTC date.

    Returns ``(tz_value, local_iso_date)``. Uses the fixed-offset zones
    ``Etc/GMT+12`` (UTC−12h) or ``Etc/GMT-14`` (UTC+14h) so the dates
    split; one of the two always does. Zoneinfo names are honored by the Go
    runtime and by the C library alike, unlike POSIX offset strings such as
    ``UTC+12`` that some runtimes silently read as UTC. Raises
    ``HarnessError`` if the chosen zone is not effective in this
    environment, so the contrast can never pass vacuously.
    """
    now = datetime.now(timezone.utc)
    utc_dates = {now.date()}
    candidates = (
        ("Etc/GMT+12", -12),
        ("Etc/GMT-14", 14),
    )
    for tz_value, offset_hours in candidates:
        local_date = (now + timedelta(hours=offset_hours)).date()
        if local_date not in utc_dates:
            _require_zone_effective(tz_value, offset_hours)
            return tz_value, local_date.isoformat()
    raise HarnessError(
        "could not choose a TZ offset whose local date differs from UTC"
    )
