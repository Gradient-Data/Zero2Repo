# feature: F08
"""Observation helpers for the membundle validate command and membundle_validate tool (FP-08).

Helpers raise ``HarnessError`` when a query cannot be classified, and
``AssertionError`` when a classified observation misses a carrier the
tests require. They never return ``None`` / ``{}`` / ``""`` / ``[]`` /
``0`` to mean "could not look".
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NoReturn

from _harness import (
    HarnessError,
    McpBatchResult,
    RunResult,
    Workspace,
    json_stdout,
    parse_json,
    path_is_dir,
    rpc_request,
)
from F01_helpers import (
    combined_report,
    report_remainder_after_stripping_paths,
    strip_generated_covariates,
    unique_leaf,
)
from F03_helpers import (
    INDEX_MARKDOWN,
    _normalized_remainder,
    mcp_is_protocol_error,
    mcp_is_tool_error,
    mcp_payload_and_text,
    mcp_reply_for_id,
    unique_tokens,
)
from F05_helpers import SEED_LOG_DATE

_WRAP_PUNCT = re.compile(r"[\"'`\[\]\(\)\{\}<>*_.,:;]+")
_WHITESPACE = re.compile(r"\s+")

PASSING_AGENTS_TEXT = (
    "# 0. Domain Codex\n"
    "FORMAT: diagrams => ASSERT(syntax == mermaid)\n"
    "\n"
    "<!-- BEGIN MEMBUNDLE AGENT MEMORY -->\n"
    "MUST keep working memory in this block.\n"
    "<!-- END MEMBUNDLE AGENT MEMORY -->\n"
)
SSOT_LINKS = (
    ("CLAUDE.md", "AGENTS.md"),
    (".cursorrules", "AGENTS.md"),
    (".windsurfrules", "AGENTS.md"),
    (".github/copilot-instructions.md", "../AGENTS.md"),
)

# Recipe artifact name. The binary is built in a writable copy, not the judge cwd.
_BIN_REL = Path("bin") / "membundle"
_BUILD_LOCK = threading.Lock()
_BUILD_DONE = False
_BUILT_BIN: Path | None = None
_NEVER_EXECUTED = (
    "the call was never executed; validate results are missing"
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
    print(f"[F08] GOFLAGS=-buildvcs=false make build cwd={root}", flush=True)
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
        print(f"[F08] make build could not start: {exc}", flush=True)
        return False
    print(f"[F08] make build exit={completed.returncode}", flush=True)
    if completed.returncode != 0:
        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
        print(
            f"[F08] make build stdout={stdout[-2000:]!r} "
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
            print(f"[F08] resolved built binary={_BUILT_BIN!r}", flush=True)
        return _BUILT_BIN


def resolve_validate_binary() -> Path:
    """Single resolver for every F08 validate-command and validate-tool call.

    When the pytest cwd contains the product sources, copies those sources
    to a writable directory, runs ``GOFLAGS=-buildvcs=false make build``
    there, and returns only that ``bin/membundle``. When that executable
    is absent, fails the test. Does not return a synthetic status 0, 1,
    or 2 or a synthetic tool error: those are validate outcomes, and an
    empty workspace would then look like a failed gate or a load failure.
    """
    binary = _workdir_membundle()
    # TEST-FIX((none)): the build writes bin/membundle under the tree it runs in, which fails in a read-only working directory (hence the writable staging copy); without it validate never runs and its results are missing.
    assert binary is not None, _NEVER_EXECUTED
    return binary


def _raise_if_validate_binary_missing(binary: Path, exc: FileNotFoundError) -> NoReturn:
    """Turn a vanished workdir binary into the never-executed assertion."""
    if binary.is_file() and os.access(binary, os.X_OK):
        raise exc
    # TEST-FIX(F08): with no bin/membundle there is no product to run; per the Contract "Build" form, make build at the repository root writes that binary.
    raise AssertionError(_NEVER_EXECUTED) from None


@dataclass(frozen=True)
class McpValidateOutcome:
    """Classified JSON-RPC reply to one membundle_validate tools/call.

    A missing reply for the requested id raises ``HarnessError`` before
    this object is built. None of the fields is a sentinel for "no reply".
    """

    batch: McpBatchResult
    reply: dict[str, Any]
    payload: Any
    report_text: str


def utc_yesterday() -> str:
    """Yesterday's UTC calendar date as ISO 8601 ``YYYY-MM-DD``."""
    return (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()


def utc_tomorrow() -> str:
    """Tomorrow's UTC calendar date as ISO 8601 ``YYYY-MM-DD``."""
    return (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    text = str(value)
    if text == "" or text != text.strip() or any(ch in text for ch in ":#{}[]&*!%@,?'\"\n"):
        return json.dumps(text)
    return text


def _emit_yaml(lines: list[str], key: str, value: Any, indent: int = 0) -> None:
    pad = "  " * indent
    if isinstance(value, Mapping):
        lines.append(f"{pad}{key}:")
        if not value:
            return
        for nested_key, nested in value.items():
            _emit_yaml(lines, str(nested_key), nested, indent + 1)
        return
    if isinstance(value, list):
        lines.append(f"{pad}{key}:")
        if not value:
            return
        for item in value:
            if isinstance(item, Mapping):
                first = True
                for nested_key, nested in item.items():
                    rendered = _yaml_scalar(nested) if not isinstance(nested, (Mapping, list)) else None
                    if first:
                        if rendered is not None:
                            lines.append(f"{pad}  - {nested_key}: {rendered}")
                        else:
                            lines.append(f"{pad}  - {nested_key}:")
                            if isinstance(nested, Mapping):
                                for inner_k, inner_v in nested.items():
                                    _emit_yaml(lines, str(inner_k), inner_v, indent + 3)
                        first = False
                    else:
                        if rendered is not None:
                            lines.append(f"{pad}    {nested_key}: {rendered}")
                        else:
                            _emit_yaml(lines, str(nested_key), nested, indent + 2)
            else:
                lines.append(f"{pad}  - {_yaml_scalar(item)}")
        return
    lines.append(f"{pad}{key}: {_yaml_scalar(value)}")


def render_membundle_markdown(*, body: str, frontmatter: Mapping[str, Any] | None) -> str:
    """Render a concept file the test writes. Does not call the product."""
    body_text = body if body.endswith("\n") else f"{body}\n"
    if frontmatter is None:
        return body_text
    lines = ["---"]
    for key, value in frontmatter.items():
        _emit_yaml(lines, str(key), value, 0)
    lines.append("---")
    return "\n".join(lines) + "\n" + body_text


def render_index_markdown(
    *,
    membundle_version: str | None = "0.2",
    listings: Sequence[tuple[str, str, str]] = (),
    extra_body: str = "",
) -> str:
    """Root index the test writes. ``membundle_version is None`` omits the declaration."""
    chunks: list[str] = []
    if membundle_version is not None:
        chunks.append("---")
        chunks.append(f"membundle_version: {membundle_version}")
        chunks.append("---")
        chunks.append("")
    chunks.append("# Bundle")
    chunks.append("")
    for title, href, description in listings:
        chunks.append(f"- [{title}]({href}) - {description}")
    if listings:
        chunks.append("")
    if extra_body:
        chunks.append(extra_body if extra_body.endswith("\n") else extra_body + "\n")
    return "\n".join(chunks) if chunks[-1].endswith("\n") else "\n".join(chunks) + "\n"


def default_validatable_log(log_date: str = SEED_LOG_DATE) -> str:
    """Two-hash ISO log heading that is not today."""
    return f"## {log_date}\n\n- seed\n"


def seed_validatable_bundle(
    ws: Workspace,
    rel: str | Path,
    concepts: Sequence[Mapping[str, Any]] = (),
    *,
    membundle_version: str | None = "0.2",
    log_date: str = SEED_LOG_DATE,
    log_markdown: str | None = None,
    index_markdown: str | None = None,
    listings: Sequence[tuple[str, str, str]] = (),
    agents: str | None = None,
) -> Path:
    """Write a loadable bundle. Does not call the product.

    Each concept mapping uses ``identity``, optional ``frontmatter`` (``None``
    means no YAML fences), ``body``, and optional ``raw`` to plant exact bytes.
    """
    root = ws.resolve(rel) if str(rel) not in ("", ".") else ws.path
    root.mkdir(parents=True, exist_ok=True)
    if index_markdown is not None:
        index_text = index_markdown
    elif membundle_version == "0.2" and not listings:
        index_text = INDEX_MARKDOWN
    else:
        index_text = render_index_markdown(membundle_version=membundle_version, listings=listings)
    (root / "index.md").write_text(index_text, encoding="utf-8")
    log_text = log_markdown if log_markdown is not None else default_validatable_log(log_date)
    (root / "log.md").write_text(log_text, encoding="utf-8")
    if agents is not None:
        (root / "AGENTS.md").write_text(agents, encoding="utf-8")
    for spec in concepts:
        identity = str(spec["identity"])
        if not identity or identity.startswith("/") or ".." in Path(identity).parts:
            raise HarnessError(f"refusing to write escaping identity {identity!r}")
        dest = root / f"{identity}.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if "raw" in spec and spec["raw"] is not None:
            dest.write_text(str(spec["raw"]), encoding="utf-8")
            continue
        dest.write_text(
            render_membundle_markdown(
                body=str(spec.get("body", "body\n")),
                frontmatter=spec.get("frontmatter"),
            ),
            encoding="utf-8",
        )
    print(
        f"[F08] seeded validatable bundle {root} concepts={len(concepts)} "
        f"version={membundle_version!r}",
        flush=True,
    )
    return root


def fact_concept(
    identity: str,
    *,
    body: str = "body\n",
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Type Fact with no other required fields."""
    frontmatter: dict[str, Any] = {"type": "Fact"}
    if extra:
        frontmatter.update(dict(extra))
    return {"identity": identity, "frontmatter": frontmatter, "body": body}


def run_validate(
    ws: Workspace,
    bundle: str | Path | None = None,
    *,
    strict: bool = False,
    stale: bool = False,
    drift: bool = False,
    agents: bool = False,
    structured: bool = False,
    extra_args: Sequence[str] = (),
    env_updates: dict[str, str | None] | None = None,
    cwd: str | Path | None = None,
) -> RunResult:
    """Invoke ``membundle validate`` with optional bundle path and caller options."""
    args: list[str] = ["validate"]
    if bundle is not None:
        args.append(str(bundle))
    if strict:
        args.append("--strict")
    if stale:
        args.append("--stale")
    if drift:
        args.append("--drift")
    if agents:
        args.append("--agents")
    if structured:
        args.append("--json")
    args.extend(str(a) for a in extra_args)
    print(
        f"[F08] validate argv={args!r} cwd={cwd!r} structured={structured}",
        flush=True,
    )
    binary = resolve_validate_binary()
    try:
        return ws.invoke(
            args, env_updates=env_updates, cwd=cwd, binary=binary
        )
    except FileNotFoundError as exc:
        _raise_if_validate_binary_missing(binary, exc)


def run_validate_structured(
    ws: Workspace,
    bundle: str | Path | None = None,
    **kwargs: Any,
) -> tuple[RunResult, Any]:
    """CLI ``--json`` validate. Raises if stdout is not parseable JSON."""
    kwargs.pop("structured", None)
    result = run_validate(ws, bundle, structured=True, **kwargs)
    payload = json_stdout(result, what="validate --json stdout")
    print(f"[F08] structured payload type={type(payload).__name__}", flush=True)
    return result, payload


def mcp_membundle_validate(
    ws: Workspace,
    arguments: Mapping[str, Any],
    *,
    request_id: int | str = 10,
    cwd: str | Path | None = None,
    env_updates: dict[str, str | None] | None = None,
) -> McpValidateOutcome:
    """One ``membundle_validate`` tools/call. A missing reply for *request_id* raises."""
    lines = [
        rpc_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "f08-suite", "version": "0"},
            },
            id=1,
        ),
        rpc_request(
            "tools/call",
            {"name": "membundle_validate", "arguments": dict(arguments)},
            id=request_id,
        ),
    ]
    print(
        f"[F08] mcp membundle_validate arguments={dict(arguments)!r} id={request_id!r}",
        flush=True,
    )
    binary = resolve_validate_binary()
    try:
        batch = ws.mcp_batch(
            lines, cwd=cwd, env_updates=env_updates, binary=binary
        )
    except FileNotFoundError as exc:
        _raise_if_validate_binary_missing(binary, exc)
    reply = mcp_reply_for_id(batch, request_id)
    payload, report_text = mcp_payload_and_text(reply)
    print(
        f"[F08] mcp reply protocol_error={mcp_is_protocol_error(reply)} "
        f"tool_error={mcp_is_tool_error(reply)} text={report_text!r}",
        flush=True,
    )
    return McpValidateOutcome(
        batch=batch, reply=reply, payload=payload, report_text=report_text
    )


def mcp_validate(
    ws: Workspace,
    bundle: str | Path | None = None,
    *,
    strict: bool | None = None,
    stale: bool | None = None,
    request_id: int | str = 10,
    cwd: str | Path | None = None,
    env_updates: dict[str, str | None] | None = None,
) -> McpValidateOutcome:
    """membundle_validate with optional bundle / strict / stale. Omit keys left unset."""
    arguments: dict[str, Any] = {}
    if bundle is not None:
        arguments["bundle"] = str(bundle)
    if strict is not None:
        arguments["strict"] = bool(strict)
    if stale is not None:
        arguments["stale"] = bool(stale)
    return mcp_membundle_validate(
        ws, arguments, request_id=request_id, cwd=cwd, env_updates=env_updates
    )


def require_cli_status_0(result: RunResult) -> str:
    """CLI success carrier: POSIX status 0."""
    report = combined_report(result)
    print(f"[F08] status-0 exit={result.returncode} report_len={len(report)}", flush=True)
    assert result.returncode == 0, (
        f"validate did not end with status 0 (exit {result.returncode}); "
        f"report={report!r}"
    )
    return report


def require_cli_status_1(result: RunResult) -> str:
    """CLI non-conformance or failed producer gate: POSIX status 1."""
    report = combined_report(result)
    print(f"[F08] status-1 exit={result.returncode} report_len={len(report)}", flush=True)
    assert result.returncode == 1, (
        f"validate did not end with status 1 (exit {result.returncode}); "
        f"report={report!r}"
    )
    return report


def require_cli_status_2(result: RunResult) -> str:
    """CLI load failure: POSIX status 2."""
    report = combined_report(result)
    print(f"[F08] status-2 exit={result.returncode} report_len={len(report)}", flush=True)
    assert result.returncode == 2, (
        f"validate did not end with status 2 (exit {result.returncode}); "
        f"report={report!r}"
    )
    return report


def _walk_values(obj: Any, *, want: type) -> list[Any]:
    """Generic JSON walker. Kept only because ``F10_helpers`` imports it;
    no F08 reader uses it."""
    found: list[Any] = []

    def _walk(value: Any) -> None:
        if isinstance(value, bool):
            if want is bool:
                found.append(value)
            return
        if isinstance(value, (int, float)):
            if want is not bool:
                found.append(value)
            return
        if isinstance(value, str):
            return
        if isinstance(value, Mapping):
            for item in value.values():
                _walk(item)
            return
        if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            for item in value:
                _walk(item)
            return
        if value is None:
            return
        raise HarnessError(
            f"structured report is not a walkable JSON value: {type(value).__name__}"
        )

    _walk(obj)
    return found


# ---------------------------------------------------------------------------
# Structured validate report (``validate --json`` / ``membundle_validate``).
# Contract "Output forms": one JSON object with ``bundle_path``,
# ``declared_version`` (absent when none), ``concept_count``, ``errors``,
# ``warnings``, ``gate_findings`` (strings beginning ``<bundle-relative path>: ``),
# ``broken_links`` (objects ``source_concept`` / ``target_href`` / ``reason``;
# null or [] when none), ``orphans`` (identity strings; null or [] when none),
# ``stale_count``, ``is_conformant``, ``gate_passed``.
# ---------------------------------------------------------------------------

FINDING_KEYS = ("errors", "warnings", "gate_findings")


def _report_object(payload: Any) -> Mapping[str, Any]:
    if isinstance(payload, McpValidateOutcome):
        payload = _mcp_report_payload(payload)
    if not isinstance(payload, Mapping):
        raise AssertionError(
            "validate report is not one JSON object; "
            f"payload={payload!r}"
        )
    return payload


def report_bool(payload: Any, key: str) -> bool:
    """The boolean report field *key* (``is_conformant`` / ``gate_passed``)."""
    report = _report_object(payload)
    assert key in report, f"validate report has no {key!r}; payload={report!r}"
    value = report[key]
    assert isinstance(value, bool), (
        f"validate report {key!r} is not a boolean: {value!r}; payload={report!r}"
    )
    return value


def report_int(payload: Any, key: str) -> int:
    """The integer report field *key* (``concept_count`` / ``stale_count``)."""
    report = _report_object(payload)
    assert key in report, f"validate report has no {key!r}; payload={report!r}"
    value = report[key]
    assert isinstance(value, int) and not isinstance(value, bool), (
        f"validate report {key!r} is not an integer: {value!r}; payload={report!r}"
    )
    return value


def report_strings(payload: Any, key: str) -> list[str]:
    """The string array *key* (``errors`` / ``warnings`` / ``gate_findings``)."""
    report = _report_object(payload)
    assert key in report, f"validate report has no {key!r}; payload={report!r}"
    value = report[key]
    assert isinstance(value, list) and all(isinstance(v, str) for v in value), (
        f"validate report {key!r} is not an array of strings: {value!r}"
    )
    return list(value)


def report_orphans(payload: Any) -> list[str]:
    """``orphans``: identity strings; ``null`` or ``[]`` when there are none."""
    report = _report_object(payload)
    assert "orphans" in report, f"validate report has no 'orphans'; payload={report!r}"
    value = report["orphans"]
    if value is None:
        return []
    assert isinstance(value, list) and all(isinstance(v, str) for v in value), (
        f"validate report 'orphans' is not an array of strings: {value!r}"
    )
    return list(value)


def report_broken_links(payload: Any) -> list[Mapping[str, Any]]:
    """``broken_links``: objects; ``null`` or ``[]`` when there are none."""
    report = _report_object(payload)
    assert "broken_links" in report, (
        f"validate report has no 'broken_links'; payload={report!r}"
    )
    value = report["broken_links"]
    if value is None:
        return []
    assert isinstance(value, list) and all(isinstance(v, Mapping) for v in value), (
        f"validate report 'broken_links' is not an array of objects: {value!r}"
    )
    for entry in value:
        for key in ("source_concept", "target_href"):
            assert isinstance(entry.get(key), str), (
                f"broken_links entry has no string {key!r}: {entry!r}"
            )
    return list(value)


def findings_concerning(payload: Any, key: str, concerns: str) -> list[str]:
    """Entries of *key* that begin with the bundle-relative path *concerns* + ``: ``."""
    if not concerns:
        raise HarnessError("concerned path is empty")
    prefix = f"{concerns}: "
    found = [s for s in report_strings(payload, key) if s.startswith(prefix)]
    print(f"[F08] {key} concerning {concerns!r}: {found!r}", flush=True)
    return found


def assert_finding_concerns(payload: Any, key: str, concerns: str) -> None:
    """*key* has at least one entry about the file *concerns*."""
    found = findings_concerning(payload, key, concerns)
    assert found, (
        f"validate report {key!r} has no entry beginning {concerns + ': '!r}; "
        f"{key}={report_strings(payload, key)!r}"
    )


def assert_more_findings(
    defective: Any, repaired: Any, key: str, concerns: str
) -> None:
    """Relational: the defective arm's *key* has more entries about *concerns*."""
    bad = findings_concerning(defective, key, concerns)
    ok = findings_concerning(repaired, key, concerns)
    assert len(bad) > len(ok), (
        f"defective report has no additional {key!r} entry about {concerns!r}; "
        f"defective={report_strings(defective, key)!r} "
        f"repaired={report_strings(repaired, key)!r}"
    )


def _count_field(payload: Any, field: str) -> int:
    if field not in ("concept_count", "stale_count"):
        raise HarnessError(f"not a count field: {field!r}")
    return report_int(payload, field)


def assert_numbers_later_greater(
    earlier: Any, later: Any, field: str = "concept_count"
) -> None:
    """Relative order: the later arm's *field* exceeds the earlier arm's."""
    left = _count_field(earlier, field)
    right = _count_field(later, field)
    print(f"[F08] {field} earlier={left} later={right}", flush=True)
    assert right > left, (
        f"later arm's {field} ({right}) is not greater than the earlier arm's "
        f"({left})"
    )


def assert_numbers_not_greater(
    baseline: Any, other: Any, field: str = "concept_count"
) -> None:
    """Adding a reserved/non-concept file must not increase *field*."""
    left = _count_field(baseline, field)
    right = _count_field(other, field)
    print(f"[F08] {field} baseline={left} other={right}", flush=True)
    assert right <= left, (
        f"{field} increased after adding a reserved or skipped file; "
        f"baseline={left} other={right}"
    )


def assert_both_pass(obj: Any) -> None:
    """Conformant gate-pass: ``is_conformant`` and ``gate_passed`` both true."""
    conformant = report_bool(obj, "is_conformant")
    gate = report_bool(obj, "gate_passed")
    assert conformant and gate, (
        f"expected is_conformant=true gate_passed=true, got "
        f"is_conformant={conformant} gate_passed={gate}; payload={obj!r}"
    )


def assert_conformant_gate_fail(obj: Any) -> None:
    """Conformant but failed producer gate."""
    conformant = report_bool(obj, "is_conformant")
    gate = report_bool(obj, "gate_passed")
    assert conformant and not gate, (
        f"expected is_conformant=true gate_passed=false, got "
        f"is_conformant={conformant} gate_passed={gate}; payload={obj!r}"
    )


def assert_nonconformant(obj: Any, *, concerns: str | None = None) -> None:
    """Hard non-conformance: both booleans false and a hard error is listed."""
    conformant = report_bool(obj, "is_conformant")
    gate = report_bool(obj, "gate_passed")
    assert not conformant and not gate, (
        f"expected is_conformant=false gate_passed=false, got "
        f"is_conformant={conformant} gate_passed={gate}; payload={obj!r}"
    )
    assert report_strings(obj, "errors"), (
        f"non-conformant report lists no hard error; payload={obj!r}"
    )
    if concerns is not None:
        assert_finding_concerns(obj, "errors", concerns)


# ---------------------------------------------------------------------------
# Human validate report. Contract "Output forms": finding lines
# ``warn  <warning>``, ``<label>  <finding>``, ``<label>  <identity>.md: `` then
# free text for a broken link, ``<label>  <identity>.md: `` then free text
# containing ``orphan`` for an orphan, ``error <error>``; ``<label>`` is ``gate``
# under ``--strict`` and ``warn`` otherwise; then an empty line and the summary
# line (free text).
# ---------------------------------------------------------------------------

_LINE_PREFIX = {"warn": "warn  ", "gate": "gate  ", "error": "error "}


def human_finding_lines(result: RunResult, label: str) -> list[str]:
    """Text after the ``<label>`` prefix of each finding line on stdout."""
    if label not in _LINE_PREFIX:
        raise HarnessError(f"unknown finding label {label!r}")
    prefix = _LINE_PREFIX[label]
    if "--json" in result.argv:
        raise HarnessError("human finding lines requested from a --json run")
    return [
        line[len(prefix):]
        for line in result.stdout_text.splitlines()
        if line.startswith(prefix)
    ]


def _strict_label(result: RunResult) -> str:
    return "gate" if "--strict" in result.argv else "warn"


def human_lines_concerning(
    result: RunResult, concerns: str, labels: Sequence[str]
) -> list[str]:
    """Finding lines under *labels* whose finding begins ``<concerns>: ``."""
    prefix = f"{concerns}: "
    found: list[str] = []
    for label in labels:
        found.extend(
            f"{label}: {text}"
            for text in human_finding_lines(result, label)
            if text.startswith(prefix)
        )
    print(f"[F08] human {labels} lines concerning {concerns!r}: {found!r}", flush=True)
    return found


def assert_human_more_lines(
    defective: RunResult,
    repaired: RunResult,
    concerns: str,
    *,
    labels: Sequence[str],
    repaired_labels: Sequence[str] | None = None,
) -> None:
    """Relational: the defective report has more *labels* lines about *concerns*."""
    bad = human_lines_concerning(defective, concerns, labels)
    ok = human_lines_concerning(
        repaired, concerns, labels if repaired_labels is None else repaired_labels
    )
    assert len(bad) > len(ok), (
        f"defective human report has no additional {labels} line about "
        f"{concerns!r}; defective={defective.stdout_text!r} "
        f"repaired={repaired.stdout_text!r}"
    )


def assert_human_orphan_line(result: RunResult, identity: str) -> None:
    """A line ``<label>  <identity>.md: `` then text containing ``orphan`` is present."""
    label = _strict_label(result)
    expected = f"{_LINE_PREFIX[label]}{identity}.md: "
    lines = result.stdout_text.splitlines()
    print(f"[F08] human orphan line? {expected!r} + 'orphan'", flush=True)
    assert any(
        line.startswith(expected) and "orphan" in line[len(expected):]
        for line in lines
    ), (
        f"human validate report has no orphan line beginning {expected!r} "
        f"whose text names 'orphan': {result.stdout_text!r}"
    )


# ---------------------------------------------------------------------------
# Identity / href listing reads.
# ---------------------------------------------------------------------------


def assert_identity_listed(obs: Any, identity: str) -> None:
    """The concept identity is an orphan of the report.

    Structured: an exact entry of ``orphans``. Human: the orphan line for
    ``<identity>.md`` with the label the run's ``--strict`` selects. The
    bundles this is used on hold two or more unlinked concepts, so every
    loaded concept is an orphan.
    """
    if not identity:
        raise HarnessError("identity is empty; cannot assert it is listed")
    if isinstance(obs, RunResult):
        assert_human_orphan_line(obs, identity)
        return
    orphans = report_orphans(obs)
    print(f"[F08] orphans={orphans!r} want {identity!r}", flush=True)
    assert identity in orphans, (
        f"validate report 'orphans' does not list {identity!r}; orphans={orphans!r}"
    )


def assert_identity_not_listed(obs: Any, identity: str) -> None:
    """The identity is not a loaded concept the report names: not an
    ``orphans`` entry and not the ``source_concept`` of a broken link."""
    if not identity:
        raise HarnessError("identity is empty; cannot assert it is unlisted")
    orphans = report_orphans(obs)
    sources = [bl["source_concept"] for bl in report_broken_links(obs)]
    print(
        f"[F08] identity {identity!r} unlisted? orphans={orphans!r} "
        f"broken sources={sources!r}",
        flush=True,
    )
    assert identity not in orphans, (
        f"validate report 'orphans' lists {identity!r}; orphans={orphans!r}"
    )
    assert f"{identity}.md" not in sources, (
        f"validate report has a broken link from {identity!r}; sources={sources!r}"
    )


def assert_identity_absent_from_string_values(payload: Any, identity: str) -> None:
    """A reserved file is not a concept the report names (see
    ``assert_identity_not_listed``)."""
    assert_identity_not_listed(payload, identity)


def assert_absent_from_loaded_concept_set(
    payload: Any,
    identity: str,
    *,
    markdown_only: Any,
) -> None:
    """A skipped file is not in the loaded concept set: not named as a
    concept, and ``concept_count`` is not greater than the markdown-only twin."""
    if not identity:
        raise HarnessError("identity is empty; cannot assert it is absent")
    print(
        f"[F08] absent from loaded concept set identity={identity!r}",
        flush=True,
    )
    assert_identity_not_listed(payload, identity)
    assert_numbers_not_greater(markdown_only, payload)


def assert_report_includes_path_token(payload: Any, token: str) -> None:
    """``bundle_path`` is the bundle path as the caller named it."""
    if not token:
        raise HarnessError("bundle path token is empty")
    report = _report_object(payload)
    value = report.get("bundle_path")
    print(f"[F08] bundle_path={value!r} want {token!r}", flush=True)
    assert value == token, (
        f"validate report bundle_path is {value!r}, not the named path {token!r}"
    )


def _broken_with_href(obs: Any, href: str) -> list[Mapping[str, Any]]:
    return [bl for bl in report_broken_links(obs) if bl["target_href"] == href]


def assert_href_listed(obs: Any, href: str, *, source: str | None = None) -> None:
    """A ``broken_links`` entry has ``target_href`` *href* (and, when given,
    ``source_concept`` *source*)."""
    if not href:
        raise HarnessError("href is empty; cannot assert it is listed")
    matches = _broken_with_href(obs, href)
    print(f"[F08] broken links with href {href!r}: {matches!r}", flush=True)
    assert matches, (
        f"validate report has no broken link to {href!r}; "
        f"broken_links={report_broken_links(obs)!r}"
    )
    if source is not None:
        assert any(bl["source_concept"] == source for bl in matches), (
            f"no broken link to {href!r} has source_concept {source!r}; "
            f"matches={matches!r}"
        )


def assert_href_not_listed(obs: Any, href: str) -> None:
    """No ``broken_links`` entry has ``target_href`` *href*."""
    if not href:
        raise HarnessError("href is empty; cannot assert it is unlisted")
    matches = _broken_with_href(obs, href)
    assert not matches, (
        f"validate report lists {href!r} as a broken link: {matches!r}"
    )


# ---------------------------------------------------------------------------
# Remainder comparison. No F08 test uses these; kept because F09_acceptance
# imports ``assert_report_differs_after_strip``.
# ---------------------------------------------------------------------------


def strip_tokens_from(text: str, tokens: Sequence[str]) -> str:
    """Remove fixture scalars from *text*, longest first. Empty text is allowed."""
    remainder = text
    ordered = sorted({tok for tok in tokens if tok}, key=len, reverse=True)
    for tok in ordered:
        remainder = remainder.replace(tok, "")
    return remainder


def report_remainder(
    report: str,
    *,
    path_tokens: Sequence[str] = (),
    extra_tokens: Sequence[str] = (),
) -> str:
    """Strip paths, fixture scalars, dates, wrapping punctuation; collapse space."""
    if not isinstance(report, str):
        raise HarnessError(f"report remainder requires a string, got {type(report)!r}")
    text = strip_tokens_from(report, extra_tokens)
    text = strip_generated_covariates(text)
    text = report_remainder_after_stripping_paths(text, path_tokens)
    text = _WRAP_PUNCT.sub("", text)
    return _normalized_remainder(text)


def assert_report_differs_after_strip(
    left: str,
    right: str,
    *,
    path_tokens: Sequence[str] = (),
    extra_tokens: Sequence[str] = (),
) -> None:
    """After stripping identities/paths/dates/scalars, a stable difference remains."""
    left_rem = report_remainder(
        left, path_tokens=path_tokens, extra_tokens=extra_tokens
    )
    right_rem = report_remainder(
        right, path_tokens=path_tokens, extra_tokens=extra_tokens
    )
    print(
        f"[F08] remainder left={left_rem!r} right={right_rem!r}",
        flush=True,
    )
    assert left_rem != right_rem, (
        "reports do not differ after stripping paths, dates, and fixture "
        f"scalars; remainder={left_rem!r}"
    )


# ---------------------------------------------------------------------------
# Finding classes.
# ---------------------------------------------------------------------------


def require_warning_class(
    defective: RunResult,
    repaired: RunResult,
    *,
    concerns: str,
) -> None:
    """Advisory warning about the file *concerns*: both arms status 0; the
    defective human report has more ``warn  <concerns>: `` lines than the
    repaired one. Under ``--strict`` the ``warn`` label is only a warning."""
    require_cli_status_0(defective)
    require_cli_status_0(repaired)
    assert_human_more_lines(defective, repaired, concerns, labels=("warn",))


def assert_warning_absent(
    actual: RunResult,
    baseline: RunResult,
    *,
    concerns: str,
) -> None:
    """Negative arm: as many ``warn`` lines in total, and about *concerns*, as
    the no-warning baseline. Status 0 is not treated as proof."""
    actual_all = human_finding_lines(actual, "warn")
    base_all = human_finding_lines(baseline, "warn")
    actual_c = human_lines_concerning(actual, concerns, ("warn",))
    base_c = human_lines_concerning(baseline, concerns, ("warn",))
    assert len(actual_c) == len(base_c) and len(actual_all) == len(base_all), (
        "warn lines do not match the no-warning baseline; "
        f"actual={actual_all!r} baseline={base_all!r}"
    )


def require_gate_finding_class(
    without_strict: RunResult,
    with_strict: RunResult,
    repaired_strict: RunResult,
    *,
    concerns: str,
    structured_strict: Any | None = None,
) -> None:
    """Gate finding on declared 0.2 about the file *concerns*.

    Without ``--strict`` (human run): status 0 and a ``warn  <concerns>: ``
    line. With ``--strict``: status 1, conformant gate-fail, and more
    ``gate_findings`` entries (or ``gate`` lines) about *concerns* than the
    repaired ``--strict`` twin, which is status 0.
    """
    require_cli_status_0(without_strict)
    require_cli_status_1(with_strict)
    require_cli_status_0(repaired_strict)
    strict_json = "--json" in with_strict.argv
    repaired_json = "--json" in repaired_strict.argv
    if structured_strict is None and strict_json:
        structured_strict = json_stdout(with_strict, what="validate --strict --json")
    if structured_strict is not None:
        assert_conformant_gate_fail(structured_strict)
    if strict_json and repaired_json:
        assert_more_findings(
            structured_strict,
            json_stdout(repaired_strict, what="repaired validate --json"),
            "gate_findings",
            concerns,
        )
    elif not strict_json and not repaired_json:
        assert_human_more_lines(
            with_strict, repaired_strict, concerns, labels=("gate",)
        )
    else:
        raise HarnessError("strict and repaired arms must use the same output form")
    lines = human_lines_concerning(without_strict, concerns, ("warn",))
    assert lines, (
        f"human report without --strict has no 'warn  {concerns}: ' line; "
        f"stdout={without_strict.stdout_text!r}"
    )


def require_hard_error_class(
    defective: RunResult,
    repaired: RunResult,
    *,
    structured_defective: Any | None = None,
    concerns: str | None = None,
) -> None:
    """Hard error: status 1, non-conformant with an ``errors`` entry (about
    *concerns* when given); repaired status 0."""
    require_cli_status_1(defective)
    require_cli_status_0(repaired)
    if structured_defective is not None:
        assert_nonconformant(structured_defective, concerns=concerns)


# ---------------------------------------------------------------------------
# MCP membundle_validate.
# ---------------------------------------------------------------------------


def _first_content_text(reply: Mapping[str, Any]) -> str:
    result = reply.get("result")
    if not isinstance(result, Mapping):
        raise AssertionError(f"tools/call reply has no result object; reply={reply!r}")
    content = result.get("content")
    if not isinstance(content, list) or not content:
        raise AssertionError(f"tools/call result has no content; reply={reply!r}")
    first = content[0]
    if not isinstance(first, Mapping) or not isinstance(first.get("text"), str):
        raise AssertionError(
            f"first content item has no text; reply={reply!r}"
        )
    return first["text"]


def _mcp_report_payload(outcome: McpValidateOutcome) -> Mapping[str, Any]:
    """The tool result text, parsed as the one JSON report object."""
    text = _first_content_text(outcome.reply)
    try:
        parsed = parse_json(text, what="membundle_validate result text")
    except HarnessError as exc:
        raise AssertionError(
            f"membundle_validate result text is not JSON; text={text!r}"
        ) from exc
    if not isinstance(parsed, Mapping):
        raise AssertionError(
            f"membundle_validate result text is not one JSON object; text={text!r}"
        )
    return parsed


def require_mcp_validate_report(outcome: McpValidateOutcome) -> Any:
    """Present-bundle MCP carrier: the result text is the validate report."""
    if mcp_is_protocol_error(outcome.reply):
        raise AssertionError(
            "membundle_validate returned a JSON-RPC protocol error instead of a "
            f"validate report; reply={outcome.reply!r}"
        )
    payload = _mcp_report_payload(outcome)
    report_bool(payload, "is_conformant")
    report_bool(payload, "gate_passed")
    print(
        f"[F08] mcp report tool_error={mcp_is_tool_error(outcome.reply)}",
        flush=True,
    )
    return payload


def require_mcp_validate_tool_error(outcome: McpValidateOutcome) -> str:
    """Named-bundle load failure: ``isError`` true and the first content text
    begins ``Failed to load bundle from ``."""
    print(
        f"[F08] mcp named-bundle load-failure protocol_error="
        f"{mcp_is_protocol_error(outcome.reply)} "
        f"tool_error={mcp_is_tool_error(outcome.reply)}",
        flush=True,
    )
    if mcp_is_protocol_error(outcome.reply):
        raise AssertionError(
            "membundle_validate named-bundle load failure returned a JSON-RPC "
            "protocol error instead of a tool-level load failure; "
            f"reply={outcome.reply!r}"
        )
    assert mcp_is_tool_error(outcome.reply), (
        "membundle_validate named-bundle load failure is not isError true; "
        f"reply={outcome.reply!r}"
    )
    text = _first_content_text(outcome.reply)
    assert text.startswith("Failed to load bundle from "), (
        "membundle_validate load failure text does not begin "
        f"'Failed to load bundle from '; text={text!r}"
    )
    return text


def assert_mcp_validate_not_both_pass(outcome: McpValidateOutcome) -> None:
    """Named-bundle load failure. Delegates to ``require_mcp_validate_tool_error``."""
    require_mcp_validate_tool_error(outcome)


def require_mcp_validate_both_pass(outcome: McpValidateOutcome) -> Any:
    """Present-bundle MCP carrier whose report is conformant gate-pass."""
    payload = require_mcp_validate_report(outcome)
    assert_both_pass(payload)
    return payload


def assert_requested_structured_validate_is_machine_readable(result: RunResult) -> Any:
    """``validate --json`` stdout is one JSON object (the validate report)."""
    payload = json_stdout(result, what="requested structured validate")
    if not isinstance(payload, Mapping):
        raise AssertionError(
            "requested structured validate is not one JSON object; "
            f"payload={payload!r}"
        )
    report_bool(payload, "is_conformant")
    report_bool(payload, "gate_passed")
    return payload


def plant_ssot_links(root: str | Path, *, omit: str | None = None, regular: str | None = None) -> None:
    """Create the four SSoT mappings under *root*. Does not call the product."""
    base = Path(root)
    if not path_is_dir(base):
        raise HarnessError(f"cannot plant SSoT links; not a directory: {base}")
    for rel, target in SSOT_LINKS:
        dest = base / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if omit is not None and rel == omit:
            if dest.exists() or dest.is_symlink():
                dest.unlink()
            continue
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        if regular is not None and rel == regular:
            dest.write_text("not-a-symlink\n", encoding="utf-8")
            continue
        os.symlink(target, dest)
    print(f"[F08] planted SSoT links under {base} omit={omit!r} regular={regular!r}", flush=True)


def unique_id(prefix: str = "id") -> str:
    """Runtime-unique concept identity leaf."""
    return unique_leaf(prefix)


def seed_fact_identities(
    ws: Workspace,
    rel: str | Path,
    identities: Sequence[str],
    **kwargs: Any,
) -> Path:
    """Seed a validatable bundle whose concepts are type-Fact only."""
    concepts = [fact_concept(ident) for ident in identities]
    return seed_validatable_bundle(ws, rel, concepts, **kwargs)


def require_gate_finding_pair(
    ws: Workspace,
    ident: str,
    bad_extra: Mapping[str, Any],
    good_extra: Mapping[str, Any],
    *,
    body: str = "body\n",
) -> Any:
    """Declared-0.2 gate finding vs repaired twin. Returns the strict structured payload."""
    rel_bad, rel_ok = unique_tokens("bd", "ok")
    seed_validatable_bundle(
        ws, rel_bad, [fact_concept(ident, body=body, extra=dict(bad_extra))]
    )
    seed_validatable_bundle(
        ws, rel_ok, [fact_concept(ident, body=body, extra=dict(good_extra))]
    )
    without = run_validate(ws, rel_bad)
    with_strict, strict_payload = run_validate_structured(ws, rel_bad, strict=True)
    repaired, _repaired_payload = run_validate_structured(ws, rel_ok, strict=True)
    require_gate_finding_class(
        without,
        with_strict,
        repaired,
        structured_strict=strict_payload,
        concerns=f"{ident}.md",
    )
    return strict_payload


def seed_drift_bundle(
    ws: Workspace,
    rel: str | Path,
    ident: str,
    title: str,
    description: str,
    listing_desc: str,
    extra: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> Path:
    """Single-concept 0.2 bundle with a root-index listing for the drift audit."""
    fm: dict[str, Any] = {"description": description, "title": title}
    if extra:
        fm.update(dict(extra))
    return seed_validatable_bundle(
        ws,
        rel,
        [fact_concept(ident, extra=fm)],
        listings=[(title, f"{ident}.md", listing_desc)],
        **kwargs,
    )
