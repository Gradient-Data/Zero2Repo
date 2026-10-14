# feature: F10
"""Observation helpers for the membundle agents command (FP-10).

Helpers raise ``HarnessError`` when a query cannot be classified, and
``AssertionError`` when a classified observation misses a carrier the
tests require. They never return ``None`` / ``{}`` / ``""`` / ``[]`` to
mean "could not look".
"""

from __future__ import annotations

import os
import re
import uuid
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, NoReturn

from _harness import (
    HarnessError,
    RunResult,
    Workspace,
    json_stdout,
    path_is_file,
    path_is_symlink,
)
from F01_helpers import (
    combined_report,
    unique_leaf,
)
from F02_helpers import BEGIN_MEMBUNDLE_COMMENT, END_MEMBUNDLE_COMMENT
from F08_helpers import (
    PASSING_AGENTS_TEXT,
    SSOT_LINKS,
)

MBG_RULE_IDS = ("MBG-001", "MBG-002", "MBG-003", "MBG-004", "MBG-005")

SsotKind = Literal["missing", "regular", "correct", "wrong_target"]

_ATX = re.compile(r"^(#{1,6})(?:[ \t]+(.+?))?[ \t]*#*[ \t]*$")
# A small caller cap, generated per test process: large enough that a
# three-word delimited block stays under it, small enough that a thirty-word
# block exceeds it. The documents state no such value.
SAMPLE_SMALL_CAP = 16 + uuid.uuid4().int % 15
_BUDGET_FORBIDDEN = ("20", str(SAMPLE_SMALL_CAP), "400", "mbg-", "mermaid")

_PROFILE_WORDS: dict[str, tuple[str, ...]] = {
    "software": ("clean", "architecture", "tdd"),
    "research": ("citation", "integrity"),
    "legal": ("privacy", "compliance"),
    "coaching": ("icf", "ethics"),
    "books": ("canon", "spoilers"),
}

_TOKEN_STATS_PREFIX = "Token Stats: "
_BUDGET_FIELD = re.compile(r"Budget: (?P<cap>-?[0-9]+)(?![0-9])")
SSOT_LINK_PATHS = (
    "CLAUDE.md",
    ".cursorrules",
    ".windsurfrules",
    ".github/copilot-instructions.md",
)

# Recipe artifact name. The binary is built in a writable copy, not the judge cwd.
_BIN_REL = Path("bin") / "membundle"
_BUILD_LOCK = threading.Lock()
_BUILD_DONE = False
_BUILT_BIN: Path | None = None
_NEVER_EXECUTED = (
    "the agents call was never executed and its results are missing"
)


def _workdir_has_product_sources(root: Path) -> bool:
    """True when *root* is a product tree: a Go module (``go.mod``) with a root
    ``Makefile`` (Contract "Build": ``make build`` at the root writes
    ``bin/membundle``). The Makefile's text is not read."""
    return (root / "Makefile").is_file() and (root / "go.mod").is_file()


def _stage_writable_sources(root: Path) -> Path:
    """Copy *root* to a writable directory, excluding any existing binary.

    The judge cwd may be a read-only filesystem. ``make build`` must not
    run there, and a binary already present under that cwd must not be
    reused.
    """
    stage = Path(tempfile.mkdtemp(prefix="membundle-build-"))
    shutil.copytree(
        root,
        stage,
        symlinks=True,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".git", "bin"),
    )
    # copytree preserves a read-only source mode, including on the stage
    # root, which then rejects mkdir bin. The copy itself must be writable.
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


def _run_product_build(root: Path) -> bool:
    """Run ``GOFLAGS=-buildvcs=false make build`` in a writable source copy.

    *root* is not the judge cwd. Returns True only when ``make`` exits 0.
    A non-zero exit is logged and is not the test result. ``make`` itself
    missing is not a successful build. Does not search ``PATH`` or honor
    ``PRODUCT_BIN``.
    """
    env = dict(os.environ)
    env.pop("PRODUCT_BIN", None)
    env["GOFLAGS"] = "-buildvcs=false"
    print(f"[F10] GOFLAGS=-buildvcs=false make build cwd={root}", flush=True)
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
        print(f"[F10] make build could not start: {exc}", flush=True)
        return False
    print(f"[F10] make build exit={completed.returncode}", flush=True)
    if completed.returncode != 0:
        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
        print(
            f"[F10] make build stdout={stdout[-2000:]!r} "
            f"stderr={stderr[-2000:]!r}",
            flush=True,
        )
        return False
    return True


def _workdir_membundle() -> Path | None:
    """Return the ``bin/membundle`` this build just produced.

    When the pytest cwd contains the product sources, copies them to a
    writable directory and runs ``GOFLAGS=-buildvcs=false make build``
    there. Does not search ``PATH``, does not honor ``PRODUCT_BIN``, does
    not build in the judge cwd, and does not use a binary this build did
    not just produce. An empty cwd, or a build that does not produce an
    executable, returns None so the caller fails because the command
    results are missing.
    """
    global _BUILD_DONE, _BUILT_BIN
    with _BUILD_LOCK:
        if not _BUILD_DONE:
            root = Path.cwd().resolve()
            built: Path | None = None
            if _workdir_has_product_sources(root):
                stage = _stage_writable_sources(root)
                if _run_product_build(stage):
                    candidate = stage / _BIN_REL
                    resolved = candidate.resolve()
                    if (
                        candidate.is_file()
                        and os.access(candidate, os.X_OK)
                        and resolved.is_relative_to(stage.resolve())
                    ):
                        built = resolved
            _BUILT_BIN = built
            _BUILD_DONE = True
            print(f"[F10] resolved built binary={_BUILT_BIN!r}", flush=True)
        return _BUILT_BIN


def resolve_agents_binary() -> Path:
    """Single resolver for every F10 agents lint, init, link, and check call.

    When the pytest cwd contains the product sources, copies those sources
    to a writable directory, runs ``GOFLAGS=-buildvcs=false make build``
    there, and returns only that ``bin/membundle``. When that executable
    is absent, fails the test. Does not return a synthetic success, a
    synthetic lint finding, a synthetic symlink, or a synthetic status:
    those are agents outcomes, and an empty workspace would then look like
    a completed agents command.
    """
    binary = _workdir_membundle()
    # TEST-FIX((none)): the build writes bin/membundle under the tree it runs in, which fails in a read-only working directory (hence the writable staging copy); without it agents never runs and its results are missing.
    assert binary is not None, _NEVER_EXECUTED
    return binary


def _raise_if_agents_binary_missing(binary: Path, exc: FileNotFoundError) -> NoReturn:
    """Turn a vanished workdir binary into the never-executed assertion."""
    if binary.is_file() and os.access(binary, os.X_OK):
        raise exc
    # TEST-FIX(F10): with no bin/membundle there is no product to run before agents lint, init, link, or check; per the Contract "Build" form, make build at the repository root writes that binary.
    raise AssertionError(_NEVER_EXECUTED) from None


def _invoke_agents(
    ws: Workspace,
    args: Sequence[str],
    *,
    cwd: str | Path | None,
) -> RunResult:
    """Invoke agents through the single workdir resolver."""
    binary = resolve_agents_binary()
    try:
        return ws.invoke(args, cwd=cwd, binary=binary)
    except FileNotFoundError as exc:
        _raise_if_agents_binary_missing(binary, exc)


def _root_path(ws: Workspace, root: str | Path | None) -> Path:
    if root is None:
        return ws.path
    path = Path(root)
    if path.is_absolute():
        return path
    return ws.path / path


def budget_safe_token(prefix: str) -> str:
    """Runtime-unique token that cannot be confused with the caps / rule ids."""
    for _ in range(64):
        token = unique_leaf(prefix)
        low = token.lower()
        if any(part in low for part in _BUDGET_FORBIDDEN):
            continue
        return token
    raise HarnessError(
        f"could not generate a budget-safe token from prefix {prefix!r}"
    )


def budget_safe_tokens(*prefixes: str) -> tuple[str, ...]:
    tokens = [budget_safe_token(prefix) for prefix in prefixes]
    for index, left in enumerate(tokens):
        for other, right in enumerate(tokens):
            if index == other:
                continue
            if left in right or right in left:
                raise HarnessError(
                    f"generated tokens overlap: {left!r} vs {right!r}"
                )
    return tuple(tokens)


def budget_word_list(count: int, prefix: str) -> list[str]:
    """Distinct whitespace-separated words for token-budget fixtures."""
    words: list[str] = []
    seen: set[str] = set()
    while len(words) < count:
        word = budget_safe_token(prefix)
        if word in seen:
            continue
        overlap = False
        for existing in words:
            if word in existing or existing in word:
                overlap = True
                break
        if overlap:
            continue
        seen.add(word)
        words.append(word)
    return words


def run_agents_lint(
    ws: Workspace,
    path: str | Path | None = None,
    *,
    budget: int | None = None,
    structured: bool = False,
    extra_args: Sequence[str] = (),
    cwd: str | Path | None = None,
) -> RunResult:
    """Invoke ``membundle agents lint`` with optional path, cap, and structured output."""
    args: list[str] = ["agents", "lint"]
    if budget is not None:
        args.append(f"--budget={budget}")
    if structured:
        args.append("--json")
    args.extend(str(a) for a in extra_args)
    if path is not None:
        args.append(str(path))
    print(
        f"[F10] lint argv={args!r} cwd={cwd!r} structured={structured}",
        flush=True,
    )
    return _invoke_agents(ws, args, cwd=cwd)


def run_agents_init(
    ws: Workspace,
    root: str | Path | None = None,
    *,
    domain: str | None = None,
    name: str | None = None,
    overwrite: bool = False,
    extra_args: Sequence[str] = (),
    cwd: str | Path | None = None,
) -> RunResult:
    """Invoke ``membundle agents init`` with optional domain, name, root, overwrite."""
    args: list[str] = ["agents", "init"]
    if domain is not None:
        args.extend(["--domain", str(domain)])
    if name is not None:
        args.extend(["--name", str(name)])
    if root is not None:
        args.extend(["--root", str(root)])
    if overwrite:
        args.append("--force")
    args.extend(str(a) for a in extra_args)
    print(
        f"[F10] init argv={args!r} cwd={cwd!r} overwrite={overwrite}",
        flush=True,
    )
    return _invoke_agents(ws, args, cwd=cwd)


def run_agents_link(
    ws: Workspace,
    root: str | Path | None = None,
    *,
    check_only: bool = False,
    overwrite: bool = False,
    extra_args: Sequence[str] = (),
    cwd: str | Path | None = None,
) -> RunResult:
    """Invoke ``membundle agents link`` with optional root, check-only, overwrite."""
    args: list[str] = ["agents", "link"]
    if root is not None:
        args.extend(["--root", str(root)])
    if check_only:
        args.append("--check")
    if overwrite:
        args.append("--force")
    args.extend(str(a) for a in extra_args)
    print(
        f"[F10] link argv={args!r} cwd={cwd!r} check_only={check_only} "
        f"overwrite={overwrite}",
        flush=True,
    )
    return _invoke_agents(ws, args, cwd=cwd)


def run_agents_check(
    ws: Workspace,
    root: str | Path | None = None,
    *,
    extra_args: Sequence[str] = (),
    cwd: str | Path | None = None,
) -> RunResult:
    """Invoke ``membundle agents check`` with optional target root."""
    args: list[str] = ["agents", "check"]
    if root is not None:
        args.extend(["--root", str(root)])
    args.extend(str(a) for a in extra_args)
    print(f"[F10] check argv={args!r} cwd={cwd!r}", flush=True)
    return _invoke_agents(ws, args, cwd=cwd)


def require_agents_success(result: RunResult) -> str:
    """Agents success carrier: POSIX status 0."""
    report = combined_report(result)
    print(
        f"[F10] success-carrier exit={result.returncode} report_len={len(report)}",
        flush=True,
    )
    assert result.returncode == 0, (
        f"agents command did not end with status 0 (exit {result.returncode}); "
        f"report={report!r}"
    )
    return report


def require_agents_failure(result: RunResult) -> str:
    """Agents failure carrier: non-zero status. Does not require 1 vs 2."""
    report = combined_report(result)
    print(
        f"[F10] failure-carrier exit={result.returncode} report_len={len(report)}",
        flush=True,
    )
    assert result.returncode != 0, (
        f"agents command succeeded (exit 0) on a case that must not succeed; "
        f"report={report!r}"
    )
    return report


def parse_structured_lint(result: RunResult) -> Any:
    """Parse requested structured lint stdout as JSON. Raises if it cannot."""
    payload = json_stdout(result, what="agents lint --json stdout")
    print(
        f"[F10] structured lint type={type(payload).__name__} "
        f"exit={result.returncode}",
        flush=True,
    )
    return payload


def write_agents(ws: Workspace, rel: str | Path, body: str) -> Path:
    """Write an AGENTS.md-shaped file under the workspace."""
    dest = ws.write(rel, body)
    print(f"[F10] wrote {dest} bytes={len(body.encode('utf-8'))}", flush=True)
    return dest


def ascii_agents_body(
    *,
    invariants_item: str | None = None,
    section0: str | None = "mermaid",
    extra: str = "",
    invariants_heading: str = "Invariants",
    extra_invariants_items: Sequence[str] = (),
    inner: str = "keep compact",
) -> str:
    """Constructable ASCII AGENTS.md that is otherwise a single-rule-clean file.

    Callers pass hyphen-item text. Section 0 includes mermaid when *section0*
    is a string; ``section0=None`` omits the Domain Codex / 0. heading.
    """
    parts: list[str] = []
    if section0 is not None:
        parts.append("# 0. Domain Codex")
        parts.append(section0)
        parts.append("")
    parts.append(BEGIN_MEMBUNDLE_COMMENT)
    parts.append(inner)
    parts.append(END_MEMBUNDLE_COMMENT)
    parts.append("")
    if invariants_item is not None:
        heading = invariants_heading if invariants_heading else "Invariants"
        if not heading.startswith("#"):
            parts.append(f"## {heading}")
        else:
            parts.append(heading)
        parts.append(f"- {invariants_item}")
        for item in extra_invariants_items:
            parts.append(f"- {item}")
        parts.append("")
    if extra:
        parts.append(extra if extra.endswith("\n") else extra + "\n")
    return "\n".join(parts)


def domain_codex_region(text: str) -> str:
    """Slice from a 0. / domain-codex ATX heading to the next heading, BEGIN, or EOF.

    Raises ``HarnessError`` if no such heading exists.
    """
    lines = text.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        match = _ATX.match(line)
        if match is None or not line.lstrip().startswith("#"):
            continue
        content = (match.group(2) or "").strip()
        lower = content.lower()
        if content.startswith("0.") or "domain codex" in lower:
            start = index
            break
    if start is None:
        raise HarnessError(
            "no ATX heading that starts with 0. or contains domain codex"
        )
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if BEGIN_MEMBUNDLE_COMMENT in lines[index]:
            end = index
            break
        match = _ATX.match(lines[index])
        if match is not None and lines[index].lstrip().startswith("#"):
            end = index
            break
    region = "\n".join(lines[start:end])
    print(
        f"[F10] domain-codex region start={start} end={end} len={len(region)}",
        flush=True,
    )
    return region


def _mapping_kind(root: Path, rel: str) -> SsotKind:
    path = root / rel
    agents = root / "AGENTS.md"
    try:
        is_link = path_is_symlink(path)
    except HarnessError:
        raise
    if not is_link:
        try:
            if path.exists():
                if path.is_file() and not path.is_symlink():
                    return "regular"
                raise HarnessError(
                    f"unclassified SSoT mapping at {path}: exists but is "
                    f"neither a symlink nor a regular file"
                )
            return "missing"
        except OSError as exc:
            raise HarnessError(f"cannot stat SSoT mapping {path}: {exc}") from exc
    if not agents.is_file():
        return "wrong_target"
    try:
        resolved = path.resolve()
        if not resolved.exists():
            return "wrong_target"
        if resolved.samefile(agents):
            return "correct"
        return "wrong_target"
    except OSError:
        return "wrong_target"


def assert_ssot_mapping_state(
    root: str | Path,
    rel: str,
    *,
    kind: SsotKind,
) -> SsotKind:
    """Classify one SSoT mapping: missing / regular / correct / wrong_target."""
    base = Path(root)
    if kind not in ("missing", "regular", "correct", "wrong_target"):
        raise HarnessError(f"unclassified requested SSoT kind: {kind!r}")
    actual = _mapping_kind(base, rel)
    print(
        f"[F10] ssot {rel} actual={actual} expected={kind} root={base}",
        flush=True,
    )
    assert actual == kind, (
        f"SSoT mapping {rel} is {actual}, expected {kind}, under {base}"
    )
    return actual


def assert_named_ssot_symlinks(root: str | Path) -> None:
    """All four SSoT link paths are symlinks whose resolved file is root/AGENTS.md."""
    base = Path(root)
    agents = base / "AGENTS.md"
    if not path_is_file(agents):
        raise HarnessError(
            f"cannot verify SSoT symlinks; root AGENTS.md is not a file: {agents}"
        )
    for rel, _target in SSOT_LINKS:
        path = base / rel
        if not path.exists() and not path_is_symlink(path):
            raise HarnessError(f"SSoT mapping is missing: {path}")
        if not path_is_symlink(path):
            raise HarnessError(
                f"SSoT mapping exists but is not a symlink: {path}"
            )
        try:
            resolved = path.resolve()
        except OSError as exc:
            raise HarnessError(
                f"SSoT mapping {path} cannot be resolved: {exc}"
            ) from exc
        if not resolved.exists():
            raise HarnessError(
                f"SSoT mapping {path} is dangling; resolved={resolved}"
            )
        try:
            same = resolved.samefile(agents)
        except OSError as exc:
            raise HarnessError(
                f"cannot compare {resolved} to {agents}: {exc}"
            ) from exc
        if not same:
            raise HarnessError(
                f"SSoT mapping {path} resolves to {resolved}, not {agents}"
            )
    print(f"[F10] all four SSoT mappings resolve to {agents}", flush=True)


def unique_passing_agents() -> tuple[str, str]:
    """Sealed passing sample plus a runtime-unique ASCII line that does not break MBG."""
    token = budget_safe_token("note")
    body = PASSING_AGENTS_TEXT + f"\n## 2. Notes\n{token}\n"
    return body, token


def mentions_profile(region: str, profile: str) -> bool:
    """Domain Codex region contains each keyword of *profile*, ignoring letter case."""
    key = profile.lower()
    if key not in _PROFILE_WORDS:
        raise HarnessError(f"unknown domain profile {profile!r}")
    lowered = region.lower()
    missing = [word for word in _PROFILE_WORDS[key] if word not in lowered]
    print(f"[F10] profile {key} missing keywords={missing!r}", flush=True)
    return not missing


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def lint_report(payload: Any) -> dict[str, Any]:
    """Structured lint object with its stated members, type-checked.

    ``passed`` (boolean), ``error_count`` / ``warn_count`` (integers),
    ``findings`` (array of objects with string ``rule_id`` and
    ``severity`` and integer ``line``), and ``token_stats`` (object with
    integer ``estimated_tokens`` and ``budget_limit`` and boolean
    ``budget_exceeded``).
    """
    assert isinstance(payload, dict), (
        f"agents lint --json stdout is not a JSON object: {payload!r}"
    )
    assert isinstance(payload.get("passed"), bool), (
        f"lint report passed is not a boolean: {payload!r}"
    )
    for key in ("error_count", "warn_count"):
        assert _is_int(payload.get(key)), (
            f"lint report {key} is not an integer: {payload!r}"
        )
    findings = payload.get("findings")
    assert isinstance(findings, list), (
        f"lint report findings is not an array: {payload!r}"
    )
    for item in findings:
        assert (
            isinstance(item, dict)
            and isinstance(item.get("rule_id"), str)
            and item.get("severity") in ("error", "warning")
            and _is_int(item.get("line"))
        ), f"lint finding does not have rule_id/severity/line: {item!r}"
    stats = payload.get("token_stats")
    assert isinstance(stats, dict), (
        f"lint report token_stats is not an object: {payload!r}"
    )
    assert _is_int(stats.get("estimated_tokens")), (
        f"token_stats estimated_tokens is not an integer: {stats!r}"
    )
    assert _is_int(stats.get("budget_limit")), (
        f"token_stats budget_limit is not an integer: {stats!r}"
    )
    assert isinstance(stats.get("budget_exceeded"), bool), (
        f"token_stats budget_exceeded is not a boolean: {stats!r}"
    )
    return payload


def finding_rule_ids(payload: Any) -> list[str]:
    """``rule_id`` of each finding, in report order."""
    ids = [item["rule_id"] for item in lint_report(payload)["findings"]]
    print(f"[F10] finding rule ids={ids!r}", flush=True)
    return ids


def assert_rule_absent(payload: Any, rule_id: str) -> list[str]:
    """No finding carries *rule_id*."""
    ids = finding_rule_ids(payload)
    assert rule_id not in ids, (
        f"structured lint reported {rule_id} on a file that must not; "
        f"rule_ids={ids!r}"
    )
    return ids


def assert_rule_only(payload: Any, rule_id: str) -> list[str]:
    """Some finding carries *rule_id*; no finding carries another MBG rule id."""
    if rule_id not in MBG_RULE_IDS:
        raise HarnessError(f"not an MBG-001–MBG-005 identifier: {rule_id!r}")
    ids = finding_rule_ids(payload)
    assert rule_id in ids, (
        f"structured lint did not report rule {rule_id}; rule_ids={ids!r}"
    )
    others = sorted(set(ids) - {rule_id})
    assert not others, (
        f"structured lint for {rule_id} also reported {others!r}; rule_ids={ids!r}"
    )
    return ids


def assert_structured_counts_greater(fewer: Any, more: Any, *, rule_id: str) -> None:
    """The more-findings arm has a greater ``error_count`` and more *rule_id* findings."""
    few = lint_report(fewer)
    many = lint_report(more)
    few_n = finding_rule_ids(few).count(rule_id)
    many_n = finding_rule_ids(many).count(rule_id)
    print(
        f"[F10] counts error_count fewer={few['error_count']} more={many['error_count']} "
        f"{rule_id} findings fewer={few_n} more={many_n}",
        flush=True,
    )
    assert many["error_count"] > few["error_count"], (
        "structured lint error_count is not greater on the more-findings arm; "
        f"fewer={few['error_count']} more={many['error_count']}"
    )
    assert many_n > few_n, (
        f"structured lint does not report more {rule_id} findings on the "
        f"more-findings arm; fewer={few_n} more={many_n}"
    )


def assert_warning_count_unchanged_when_errors_increase(fewer: Any, more: Any) -> None:
    """``error_count`` matches the error findings and grows; ``warn_count`` stays put."""
    few = lint_report(fewer)
    many = lint_report(more)
    for label, rep in (("fewer", few), ("more", many)):
        errors = sum(1 for f in rep["findings"] if f["severity"] == "error")
        warns = sum(1 for f in rep["findings"] if f["severity"] == "warning")
        assert rep["error_count"] == errors, (
            f"{label} arm error_count {rep['error_count']} does not equal its "
            f"{errors} error findings"
        )
        assert rep["warn_count"] == warns, (
            f"{label} arm warn_count {rep['warn_count']} does not equal its "
            f"{warns} warning findings"
        )
    print(
        f"[F10] error_count fewer={few['error_count']} more={many['error_count']} "
        f"warn_count fewer={few['warn_count']} more={many['warn_count']}",
        flush=True,
    )
    assert many["error_count"] > few["error_count"], (
        "more-findings arm does not have a greater error_count; "
        f"fewer={few['error_count']} more={many['error_count']}"
    )
    assert few["warn_count"] == many["warn_count"], (
        "warn_count changed when the MBG error count increased; "
        f"fewer={few['warn_count']} more={many['warn_count']}"
    )


def budget_limit(payload: Any) -> int:
    return lint_report(payload)["token_stats"]["budget_limit"]


def estimated_tokens(payload: Any) -> int:
    return lint_report(payload)["token_stats"]["estimated_tokens"]


def budget_exceeded(payload: Any) -> bool:
    return lint_report(payload)["token_stats"]["budget_exceeded"]


def assert_in_force_cap_differs(
    omit_payload: Any,
    cap20_payload: Any,
    *,
    also_400: Sequence[Any] = (),
) -> None:
    """``token_stats.budget_limit`` is 400 when omitted / non-positive / 400, and the small cap for the small cap."""
    omit_cap = budget_limit(omit_payload)
    cap20 = budget_limit(cap20_payload)
    print(f"[F10] budget_limit omit={omit_cap} cap20={cap20}", flush=True)
    assert omit_cap == 400, (
        f"structured lint budget_limit is {omit_cap}, not 400, when the caller "
        "omits the cap"
    )
    assert cap20 == SAMPLE_SMALL_CAP, (
        f"structured lint budget_limit is {cap20}, not {SAMPLE_SMALL_CAP}, "
        f"when the caller supplies {SAMPLE_SMALL_CAP}"
    )
    for extra in also_400:
        extra_cap = budget_limit(extra)
        assert extra_cap == 400, (
            f"structured lint budget_limit is {extra_cap}, not 400, for a "
            "non-positive or explicit-400 caller cap"
        )
    estimated_tokens(omit_payload)
    estimated_tokens(cap20_payload)


def assert_exceeded_mark_matches_mbg005(
    under_clean: Any,
    under_other_fail: Any,
    over_mbg005: Any,
) -> None:
    """``token_stats.budget_exceeded`` is true exactly on the arm reporting MBG-005."""
    arms = (
        ("under-budget clean", under_clean, False),
        ("under-budget MBG-001 fail", under_other_fail, False),
        ("over-budget MBG-005", over_mbg005, True),
    )
    for label, payload, want in arms:
        has_005 = "MBG-005" in finding_rule_ids(payload)
        mark = budget_exceeded(payload)
        print(f"[F10] {label}: MBG-005={has_005} budget_exceeded={mark}", flush=True)
        assert has_005 is want, (
            f"{label} arm MBG-005 presence is {has_005}, expected {want}"
        )
        assert mark is want, (
            f"{label} arm budget_exceeded is {mark}, expected {want} "
            "(must match MBG-005 presence)"
        )


def assert_structured_pass_fail_distinct(pass_payload: Any, fail_payload: Any) -> None:
    """``passed`` is true on the passing run and false on the failing one."""
    passed = lint_report(pass_payload)
    failed = lint_report(fail_payload)
    print(
        f"[F10] passed pass-arm={passed['passed']} fail-arm={failed['passed']}",
        flush=True,
    )
    assert passed["passed"] is True and passed["error_count"] == 0, (
        f"passing structured lint is not passed with error_count 0: {passed!r}"
    )
    assert failed["passed"] is False and failed["error_count"] > 0, (
        f"failing structured lint is not passed false with errors: {failed!r}"
    )


def assert_working_memory_estimate_sorts_below(inner_payload: Any, whole_payload: Any) -> None:
    """Begin-then-end run's ``estimated_tokens`` sorts strictly below the whole-file run's."""
    inner = estimated_tokens(inner_payload)
    whole = estimated_tokens(whole_payload)
    print(f"[F10] estimated_tokens inner={inner} whole={whole}", flush=True)
    assert inner < whole, (
        "working-memory estimate for the well-formed begin-then-end run does "
        "not sort strictly below the omitted-delimiter whole-file run; "
        f"inner={inner} whole={whole}"
    )


def human_lint_budget(result: RunResult) -> int:
    """In-force cap from human lint stdout's second line: it begins
    ``Token Stats: `` and contains ``Budget: <cap>`` (Contract Output forms)."""
    lines = result.stdout_text.splitlines()
    print(f"[F10] human lint head={lines[:2]!r}", flush=True)
    assert len(lines) >= 2 and lines[0].startswith("MBG Linter: "), (
        f"human lint stdout does not start with 'MBG Linter: '; stdout={result.stdout_text!r}"
    )
    caps = (
        list(_BUDGET_FIELD.finditer(lines[1]))
        if lines[1].startswith(_TOKEN_STATS_PREFIX)
        else []
    )
    assert len(caps) == 1, (
        "human lint stdout second line does not begin 'Token Stats: ' with "
        f"exactly one 'Budget: <cap>' field; line={lines[1]!r}"
    )
    match = caps[0]
    return int(match.group("cap"))


def link_check_marks(result: RunResult) -> dict[str, str]:
    """``agents link --check`` stdout: link path -> ``✓`` or ``✗`` for each mapping line."""
    lines = result.stdout_text.splitlines()
    assert lines, f"link --check stdout is empty; stdout={result.stdout_text!r}"
    # Contract Output forms, ``agents link``: a free first line, then one
    # mapping line per link path beginning with its mark.
    mapping_lines = [ln for ln in lines[1:] if ln.startswith(("✓ ", "✗ "))]
    marks: dict[str, str] = {}
    for rel in SSOT_LINK_PATHS:
        hits = [ln for ln in mapping_lines if rel in ln]
        assert len(hits) == 1, (
            f"link --check stdout has {len(hits)} mapping lines for {rel}, not one; "
            f"stdout={result.stdout_text!r}"
        )
        marks[rel] = hits[0][0]
    print(f"[F10] link --check marks={marks!r}", flush=True)
    return marks
