# feature: F05
"""Observation helpers for the membundle create command and membundle_create tool (FP-05).

Helpers raise ``HarnessError`` when a query cannot be classified, and
``AssertionError`` when a classified observation misses a carrier the
tests require. They never return ``None`` / ``{}`` / ``""`` / ``[]`` to
mean "could not look".
"""

from __future__ import annotations

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
    path_is_dir,
    path_is_file,
    read_bytes,
    read_file,
    rpc_request,
)
from F01_helpers import (
    _heading_content_starts,
    _heading_marker_line,
    combined_report,
    first_heading_text,
    membundle_version_declared,
    report_remainder_after_stripping_paths,
    split_yaml_frontmatter,
    strip_generated_covariates,
)
from F03_helpers import (
    _normalized_remainder,
    mcp_is_protocol_error,
    mcp_is_tool_error,
    mcp_payload_and_text,
    mcp_reply_for_id,
    record_string_values,
    snapshot_tree,
    write_bundle,
)

_ATX = re.compile(r"^(#{1,6})(?:[ \t]+(.+?))?[ \t]*#*[ \t]*$")
_LIST_ITEM = re.compile(r"^[ \t]*(?:[*+\-]|\d+[.)])[ \t]+(.*)$")
_INLINE_LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
_WRAP_PUNCT = re.compile(r"[\"'`\[\]\(\)\{\}<>*_.,:;]+")
_KEY_LINE = re.compile(r"^[ \t]*([^:#\s][^:]*)[ \t]*:(.*)$")
_BLOCK_KEY_LINE = re.compile(
    r"""^[ \t]*("(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[^:#\s"'][^:]*?)[ \t]*:(.*)$"""
)
_COMBINED_AT = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})"
    r"[T ]"
    r"(?P<hour>\d{2}):(?P<minute>\d{2})"
    r"(?::(?P<second>\d{2})(?:\.(?P<fraction>\d+))?)?"
    r"(?P<tz>Z|[+-]\d{2}:?\d{2})?$"
)

SEED_LOG_DATE = "2020-01-01"
# Generated nested-identity sample (parent directory plus a hyphenated leaf),
# a capitalized type word, and a three-word title with a letters-plus-digit
# word. Fresh per test process; the documents carry none of these values.
def _gen_hex(n: int = 8) -> str:
    """Runtime-unique lowercase hex (the suite's own generated sample material)."""
    import uuid as _uuid

    return _uuid.uuid4().hex[:n]

SAMPLE_PARENT = f"d{_gen_hex(7)}"
SAMPLE_IDENTITY = f"{SAMPLE_PARENT}/a{_gen_hex(6)}-f{_gen_hex(6)}"
SAMPLE_TYPE = f"T{_gen_hex(7)}"
SAMPLE_TITLE = f"Q{_gen_hex(5)}2 A{_gen_hex(6)} F{_gen_hex(6)}"

# Recipe artifact name. The binary is built in a writable copy, not the judge cwd.
_BIN_REL = Path("bin") / "membundle"
_BUILD_LOCK = threading.Lock()
_BUILD_DONE = False
_BUILT_BIN: Path | None = None
_NEVER_EXECUTED = (
    "the call was never executed; create results are missing"
)


@dataclass(frozen=True)
class McpCreateOutcome:
    """Classified JSON-RPC reply to one membundle_create tools/call.

    A missing reply for the requested id raises ``HarnessError`` before
    this object is built. None of the fields is a sentinel for "no reply".
    """

    batch: McpBatchResult
    reply: dict[str, Any]
    payload: Any
    report_text: str


def concept_filename(identity: str) -> str:
    """On-disk filename of a concept identity (final segment plus ``.md``)."""
    name = Path(str(identity)).name
    if not name:
        raise HarnessError(f"identity has no filename segment: {identity!r}")
    return f"{name}.md"


def concept_file(bundle: str | Path, identity: str) -> Path:
    """Bundle-relative path of ``identity.md``."""
    return Path(bundle) / f"{identity}.md"


def parent_index_path(bundle: str | Path, identity: str) -> Path:
    """Immediate parent directory's ``index.md`` for *identity*."""
    parent = Path(identity).parent
    root = Path(bundle)
    if str(parent) in ("", "."):
        return root / "index.md"
    return root / parent / "index.md"


def seed_bundle(
    ws: Workspace,
    rel: str | Path,
    concepts: Sequence[Mapping[str, Any]] = (),
    *,
    agents: str | None = None,
    log_date: str = SEED_LOG_DATE,
) -> Path:
    """Write root index, a not-today log heading, and optional concepts.

    Does not call the product. Log heading defaults to ``2020-01-01``.
    """
    root = write_bundle(ws, rel, concepts, agents=agents)
    (root / "log.md").write_text(
        f"## {log_date}\n\n- seed\n",
        encoding="utf-8",
    )
    print(f"[F05] seeded bundle {root} log_date={log_date!r}", flush=True)
    return root


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
    print(f"[F05] GOFLAGS=-buildvcs=false make build cwd={root}", flush=True)
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
        print(f"[F05] make build could not start: {exc}", flush=True)
        return False
    print(f"[F05] make build exit={completed.returncode}", flush=True)
    if completed.returncode != 0:
        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
        print(
            f"[F05] make build stdout={stdout[-2000:]!r} "
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
            print(f"[F05] resolved built binary={_BUILT_BIN!r}", flush=True)
        return _BUILT_BIN


def resolve_create_binary() -> Path:
    """Single resolver for every F05 create-command and create-tool call.

    When the pytest cwd contains the product sources, copies those sources
    to a writable directory, runs ``GOFLAGS=-buildvcs=false make build``
    there, and returns only that ``bin/membundle``. When that executable
    is absent, fails the test. Does not return a synthetic non-zero
    result or a synthetic tool error: F05 refusal checks accept any
    non-zero exit and any tool error and would then pass on an empty
    workspace.
    """
    binary = _workdir_membundle()
    # TEST-FIX((none)): the build writes bin/membundle under the tree it runs in, which fails in a read-only working directory (hence the writable staging copy); without it create never runs and its results are missing.
    assert binary is not None, _NEVER_EXECUTED
    return binary


def _raise_if_create_binary_missing(binary: Path, exc: FileNotFoundError) -> NoReturn:
    """Turn a vanished workdir binary into the never-executed assertion."""
    if binary.is_file() and os.access(binary, os.X_OK):
        raise exc
    # TEST-FIX(F05): with no bin/membundle there is no product to run; per the Contract "Build" form, make build at the repository root writes that binary.
    raise AssertionError(_NEVER_EXECUTED) from None


def run_create(
    ws: Workspace,
    concept_id: str | None = None,
    bundle: str | Path | None = None,
    *,
    concept_type: str | None = None,
    title: str | None = None,
    description: str | None = None,
    body: str | None = None,
    tags: str | None = None,
    actor: str | None = None,
    skip_log: bool = False,
    skip_index: bool = False,
    structured: bool = False,
    extra_args: Sequence[str] = (),
    env_updates: dict[str, str | None] | None = None,
    cwd: str | Path | None = None,
) -> RunResult:
    """Invoke ``membundle create`` with identity, optional bundle, and caller options."""
    args: list[str] = ["create"]
    if concept_id is not None:
        args.append(str(concept_id))
    if bundle is not None:
        args.append(str(bundle))
    if concept_type is not None:
        args.extend(["--type", concept_type])
    if title is not None:
        args.extend(["--title", title])
    if description is not None:
        args.extend(["--desc", description])
    if body is not None:
        args.extend(["--body", body])
    if tags is not None:
        args.extend(["--tags", tags])
    if actor is not None:
        args.extend(["--actor", actor])
    if skip_log:
        args.append("--no-log")
    if skip_index:
        args.append("--no-index")
    if structured:
        args.append("--json")
    args.extend(str(item) for item in extra_args)
    print(f"[F05] create argv={args!r} cwd={cwd!r}", flush=True)
    binary = resolve_create_binary()
    try:
        return ws.invoke(
            args, env_updates=env_updates, cwd=cwd, binary=binary
        )
    except FileNotFoundError as exc:
        _raise_if_create_binary_missing(binary, exc)


def run_create_with_instants(
    ws: Workspace,
    concept_id: str | None = None,
    bundle: str | Path | None = None,
    *,
    concept_type: str | None = None,
    title: str | None = None,
    description: str | None = None,
    body: str | None = None,
    tags: str | None = None,
    actor: str | None = None,
    skip_log: bool = False,
    skip_index: bool = False,
    structured: bool = False,
    extra_args: Sequence[str] = (),
    env_updates: dict[str, str | None] | None = None,
    cwd: str | Path | None = None,
) -> tuple[RunResult, datetime, datetime]:
    """Run create and capture host UTC instants spanning the invoke."""
    before = datetime.now(timezone.utc)
    result = run_create(
        ws,
        concept_id,
        bundle,
        concept_type=concept_type,
        title=title,
        description=description,
        body=body,
        tags=tags,
        actor=actor,
        skip_log=skip_log,
        skip_index=skip_index,
        structured=structured,
        extra_args=extra_args,
        env_updates=env_updates,
        cwd=cwd,
    )
    after = datetime.now(timezone.utc)
    return result, before, after


def utc_instants_spanning_invoke(
    before: datetime, after: datetime
) -> tuple[datetime, datetime]:
    """Host UTC instants observed immediately before and after an invoke."""
    if before.tzinfo is None or after.tzinfo is None:
        raise HarnessError("invoke-window instants must be timezone-aware")
    return before.astimezone(timezone.utc), after.astimezone(timezone.utc)


def require_create_success(result: RunResult) -> str:
    """CLI success carrier: POSIX success. Files are asserted separately."""
    report = combined_report(result)
    print(
        f"[F05] create-success exit={result.returncode} report_len={len(report)}",
        flush=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"create did not end successfully (exit {result.returncode}); "
            f"report={report!r}"
        )
    return report


def require_create_failure(result: RunResult) -> str:
    """CLI failure carrier: process status is not success."""
    report = combined_report(result)
    print(
        f"[F05] create-failure exit={result.returncode} report={report!r}",
        flush=True,
    )
    assert result.returncode != 0, (
        f"create ended successfully when it must not; report={report!r}"
    )
    return report


def _filename_as_path(value: str, filename: str) -> bool:
    posix = value.replace("\\", "/")
    if posix == filename or posix.endswith("/" + filename):
        return True
    return Path(posix).name == filename


def require_create_structured_success(
    result: RunResult, identity: str, filename: str
) -> Any:
    """``create --json`` success: status 0 and one JSON object on stdout.

    Output forms: ``status`` is the string ``success``, ``concept_id`` is
    the identity, ``path`` is ``<identity>.md``. Other keys are not read.
    *filename* is kept for call compatibility; the stated ``path`` value
    is the bundle-relative ``<identity>.md``.
    """
    require_create_success(result)
    parsed = json_stdout(result)
    print(f"[F05] structured create object={parsed!r}", flush=True)
    if not isinstance(parsed, dict):
        raise AssertionError(
            f"create --json stdout is not one JSON object; parsed={parsed!r}"
        )
    assert parsed.get("status") == "success", (
        f"create --json status is not the string 'success'; parsed={parsed!r}"
    )
    assert parsed.get("concept_id") == identity, (
        f"create --json concept_id is not this run's identity {identity!r}; "
        f"parsed={parsed!r}"
    )
    assert parsed.get("path") == f"{identity}.md", (
        f"create --json path is not {identity + '.md'!r} "
        f"(filename {filename!r}); parsed={parsed!r}"
    )
    return parsed


def _class_remainder(report: str, path_tokens: Sequence[str]) -> str:
    if not report:
        raise HarnessError("empty report; cannot compute a class remainder")
    return _normalized_remainder(
        report_remainder_after_stripping_paths(
            strip_generated_covariates(report), path_tokens
        )
    )


def _stderr_lines(result: RunResult) -> list[str]:
    return result.stderr_text.splitlines()


def require_cli_usage_failure(result: RunResult, what: str) -> str:
    """Output forms, Usage failure: status 1, usage text contains ``Usage:``.

    Whether the usage text is on stdout or stderr is free; both are read.
    """
    report = combined_report(result)
    print(
        f"[F05] usage-class {what} exit={result.returncode} report={report!r}",
        flush=True,
    )
    assert result.returncode == 1, (
        f"{what}: usage failure must end with status 1, got "
        f"{result.returncode}; report={report!r}"
    )
    assert "Usage:" in report, (
        f"{what}: usage failure text does not contain the literal 'Usage:'; "
        f"report={report!r}"
    )
    return report


def require_cli_rejected_failure(result: RunResult, what: str) -> str:
    """Output forms, Rejected input or refused write: status 1, stderr line ``Error: ``."""
    lines = _stderr_lines(result)
    print(
        f"[F05] rejected-class {what} exit={result.returncode} stderr={lines!r}",
        flush=True,
    )
    assert result.returncode == 1, (
        f"{what}: rejected input must end with status 1, got "
        f"{result.returncode}; stderr={lines!r}"
    )
    assert any(line.startswith("Error: ") for line in lines), (
        f"{what}: standard error has no line that begins 'Error: '; "
        f"stderr={lines!r} stdout={result.stdout_text!r}"
    )
    return result.stderr_text


def require_create_report_line(
    result: RunResult, identity: str, title: str, bundle: str
) -> str:
    """Output forms, ``create`` (human): exactly one stdout line, wording free.

    The line contains ``'<identity>.md'`` and ``'<bundle>'``, where
    ``<bundle>`` is the bundle path as the caller named it (or the default
    bundle path when omitted). *title* is accepted for call compatibility.
    """
    del title
    require_create_success(result)
    expected = (f"'{identity}.md'", f"'{bundle}'")
    lines = result.stdout_text.splitlines()
    print(f"[F05] create stdout lines={lines!r} expected={expected!r}", flush=True)
    assert len(lines) == 1 and all(part in lines[0] for part in expected), (
        f"create human success is not one line containing {expected!r}; "
        f"stdout={result.stdout_text!r}"
    )
    return lines[0]


def require_create_usage_failure(
    missing: RunResult,
    empty_identity: RunResult,
    reserved: RunResult,
    success: RunResult,
    identity: str,
    title: str,
    bundle: str,
) -> str:
    """Missing identity is the Usage failure class; the others are their own classes.

    Each outcome is read in the class the Output forms section states for
    it: the missing identity argument is a Usage failure; the empty and
    the reserved identity are Rejected input; the live create is the
    ``create`` human success line.
    """
    report = require_cli_usage_failure(missing, "create with no identity argument")
    require_cli_rejected_failure(empty_identity, "create of the empty identity")
    require_cli_rejected_failure(reserved, "create of the reserved identity index")
    require_create_report_line(success, identity, title, bundle)
    return report


def mcp_membundle_create(
    ws: Workspace,
    arguments: Mapping[str, Any],
    *,
    request_id: int | str = 10,
    cwd: str | Path | None = None,
    env_updates: dict[str, str | None] | None = None,
) -> McpCreateOutcome:
    """One ``membundle_create`` tools/call. A missing reply for *request_id* raises."""
    lines = [
        rpc_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "f05-suite", "version": "0"},
            },
            id=1,
        ),
        rpc_request(
            "tools/call",
            {"name": "membundle_create", "arguments": dict(arguments)},
            id=request_id,
        ),
    ]
    print(
        f"[F05] mcp membundle_create arguments={dict(arguments)!r} id={request_id!r}",
        flush=True,
    )
    binary = resolve_create_binary()
    try:
        batch = ws.mcp_batch(
            lines, cwd=cwd, env_updates=env_updates, binary=binary
        )
    except FileNotFoundError as exc:
        _raise_if_create_binary_missing(binary, exc)
    reply = mcp_reply_for_id(batch, request_id)
    payload, report_text = mcp_payload_and_text(reply)
    print(
        f"[F05] mcp reply protocol_error={mcp_is_protocol_error(reply)} "
        f"tool_error={mcp_is_tool_error(reply)} text={report_text!r}",
        flush=True,
    )
    return McpCreateOutcome(
        batch=batch, reply=reply, payload=payload, report_text=report_text
    )


def mcp_create(
    ws: Workspace,
    concept_id: str,
    *,
    concept_type: str,
    title: str,
    description: str | None = None,
    body: str | None = None,
    bundle: str | Path | None = None,
    request_id: int | str = 10,
    cwd: str | Path | None = None,
    env_updates: dict[str, str | None] | None = None,
) -> McpCreateOutcome:
    """membundle_create with required identity/type/title and optional fields."""
    arguments: dict[str, Any] = {
        "concept_id": concept_id,
        "type": concept_type,
        "title": title,
    }
    if description is not None:
        arguments["description"] = description
    if body is not None:
        arguments["body"] = body
    if bundle is not None:
        arguments["bundle"] = str(bundle)
    return mcp_membundle_create(
        ws,
        arguments,
        request_id=request_id,
        cwd=cwd,
        env_updates=env_updates,
    )


def mcp_create_with_instants(
    ws: Workspace,
    concept_id: str,
    *,
    concept_type: str,
    title: str,
    description: str | None = None,
    body: str | None = None,
    bundle: str | Path | None = None,
    request_id: int | str = 10,
    cwd: str | Path | None = None,
    env_updates: dict[str, str | None] | None = None,
) -> tuple[McpCreateOutcome, datetime, datetime]:
    """Run membundle_create and capture host UTC instants spanning the invoke."""
    before = datetime.now(timezone.utc)
    outcome = mcp_create(
        ws,
        concept_id,
        concept_type=concept_type,
        title=title,
        description=description,
        body=body,
        bundle=bundle,
        request_id=request_id,
        cwd=cwd,
        env_updates=env_updates,
    )
    after = datetime.now(timezone.utc)
    return outcome, before, after


def observe_cli_refusal(
    ws: Workspace,
    concept_id: str | None,
    bundle: str | Path | None = None,
    **run_kwargs: Any,
) -> RunResult:
    """CLI create fails (non-success) and writes no new concept file."""
    before = snapshot_tree(ws.path)
    result = run_create(ws, concept_id, bundle, **run_kwargs)
    require_create_failure(result)
    bundle_rel = str(bundle) if bundle is not None else "."
    assert_no_new_concept_file(ws.path, before, bundle_rel=bundle_rel)
    return result


def observe_mcp_refusal(
    ws: Workspace,
    arguments: Mapping[str, Any],
    *,
    bundle_rel: str,
    request_id: int | str = 10,
    cwd: str | Path | None = None,
) -> McpCreateOutcome:
    """MCP create is a tool error and writes no new concept file."""
    before = snapshot_tree(ws.path)
    outcome = mcp_membundle_create(
        ws, arguments, request_id=request_id, cwd=cwd
    )
    require_mcp_create_tool_error(outcome)
    assert_no_new_concept_file(ws.path, before, bundle_rel=bundle_rel)
    return outcome


def require_mcp_create_success(outcome: McpCreateOutcome) -> str:
    """MCP success: not a tool error and not a protocol error."""
    if mcp_is_protocol_error(outcome.reply):
        raise AssertionError(
            f"membundle_create returned a protocol error instead of a tool result: "
            f"{outcome.reply!r}"
        )
    if mcp_is_tool_error(outcome.reply):
        raise AssertionError(
            f"membundle_create marked a tool error on a successful create: "
            f"{outcome.report_text!r}"
        )
    return outcome.report_text


def require_mcp_create_tool_error(outcome: McpCreateOutcome) -> str:
    """MCP field/identity failure: tool-error channel, not a protocol error."""
    if mcp_is_protocol_error(outcome.reply):
        raise AssertionError(
            "membundle_create rejected the call as a JSON-RPC protocol error; "
            "the PRD requires tool-level failures as tool errors, not "
            f"protocol errors; reply={outcome.reply!r}"
        )
    assert mcp_is_tool_error(outcome.reply), (
        "membundle_create is not marked as a tool error; a successful tools/call "
        f"is not this class; reply={outcome.reply!r}"
    )
    return outcome.report_text


def mcp_first_content_text(reply: Mapping[str, Any]) -> str:
    """Text of the first content item of a tools/call result."""
    result = reply.get("result")
    if not isinstance(result, Mapping):
        raise AssertionError(f"tools/call reply has no result object: {reply!r}")
    content = result.get("content")
    if (
        not isinstance(content, Sequence)
        or isinstance(content, (str, bytes))
        or not content
        or not isinstance(content[0], Mapping)
        or not isinstance(content[0].get("text"), str)
    ):
        raise AssertionError(
            f"tools/call result has no first text content item: {reply!r}"
        )
    return content[0]["text"]


def require_mcp_tool_error_prefix(reply: Mapping[str, Any], prefix: str, what: str) -> str:
    """Output forms, tool-level failures: ``isError`` true and first text begins *prefix*."""
    if mcp_is_protocol_error(reply):
        raise AssertionError(
            f"{what}: JSON-RPC protocol error instead of a tool error; reply={reply!r}"
        )
    assert mcp_is_tool_error(reply), (
        f"{what}: tool result is not marked isError true; reply={reply!r}"
    )
    text = mcp_first_content_text(reply)
    print(f"[F05] {what} tool-error text={text!r} prefix={prefix!r}", flush=True)
    assert text.startswith(prefix), (
        f"{what}: tool-error text does not begin {prefix!r}; text={text!r}"
    )
    return text


def mcp_bundle_dir(ws: Workspace, bundle: str | Path | None) -> str:
    """Absolute bundle directory (symbolic links resolved) an MCP write targets."""
    base = ws.path if bundle is None else ws.path / bundle
    return str(Path(base).resolve())


def require_mcp_create_report(
    outcome: McpCreateOutcome, identity: str, bundle_dir: str
) -> str:
    """Output forms, ``membundle_create`` result: exactly one line, wording free.

    The line contains ``<identity>.md`` and ends with `` <bundle>``, where
    ``<bundle>`` is the absolute bundle directory (symbolic links resolved).
    """
    require_mcp_create_success(outcome)
    text = mcp_first_content_text(outcome.reply)
    line = text[:-1] if text.endswith("\n") else text
    print(
        f"[F05] mcp create text={text!r} identity={identity!r} bundle={bundle_dir!r}",
        flush=True,
    )
    assert (
        "\n" not in line
        and f"{identity}.md" in line
        and line.endswith(f" {bundle_dir}")
    ), (
        f"membundle_create success text is not one line containing "
        f"{identity + '.md'!r} and ending with {' ' + bundle_dir!r}; text={text!r}"
    )
    return text


def _strip_yaml_quotes(scalar: str) -> str:
    text = scalar.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1].strip()
    return text


def _mapping_lines(mapping_text: str) -> list[str]:
    lines: list[str] = []
    for line in mapping_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(line)
    return lines


def frontmatter_scalar(mapping_text: str, key: str) -> str:
    """Line-oriented mapping-key scalar. Raises if the key is absent."""
    pattern = re.compile(rf"^[ \t]*{re.escape(key)}[ \t]*:(.*)$")
    for line in _mapping_lines(mapping_text):
        match = pattern.match(line)
        if match is None:
            continue
        return _strip_yaml_quotes(match.group(1))
    raise HarnessError(f"frontmatter mapping key {key!r} is absent")


def _has_mapping_key(mapping_text: str, key: str) -> bool:
    pattern = re.compile(rf"^[ \t]*{re.escape(key)}[ \t]*:")
    return any(pattern.match(line) for line in _mapping_lines(mapping_text))


def assert_no_verified_key(mapping_text: str) -> None:
    """Fresh create does not invent a verified mapping key."""
    if _has_mapping_key(mapping_text, "verified"):
        raise AssertionError(
            "create invented a verified frontmatter key; "
            f"mapping={mapping_text!r}"
        )


def _yaml_quoted_scalar(text: str, start: int) -> tuple[str, int]:
    """Read a YAML single- or double-quoted scalar starting at ``start``.

    Returns the decoded value and the index just past the closing quote.
    """
    quote = text[start]
    index = start + 1
    out: list[str] = []
    while index < len(text):
        char = text[index]
        if quote == "'":
            if char == "'":
                if text[index + 1 : index + 2] == "'":
                    out.append("'")
                    index += 2
                    continue
                return "".join(out), index + 1
            out.append(char)
            index += 1
            continue
        if char == "\\":
            escape = text[index + 1 : index + 2]
            simple = {
                '"': '"', "\\": "\\", "/": "/", "n": "\n", "t": "\t",
                "r": "\r", "0": "\0", " ": " ", "b": "\b", "f": "\f",
            }
            if escape in simple:
                out.append(simple[escape])
                index += 2
                continue
            widths = {"x": 2, "u": 4, "U": 8}
            if escape in widths:
                digits = text[index + 2 : index + 2 + widths[escape]]
                if len(digits) != widths[escape] or not all(
                    d in "0123456789abcdefABCDEF" for d in digits
                ):
                    raise HarnessError(
                        f"bad escape in YAML double-quoted scalar: {text!r}"
                    )
                out.append(chr(int(digits, 16)))
                index += 2 + widths[escape]
                continue
            raise HarnessError(
                f"unsupported escape in YAML double-quoted scalar: {text!r}"
            )
        if char == '"':
            return "".join(out), index + 1
        out.append(char)
        index += 1
    raise HarnessError(f"unterminated YAML quoted scalar: {text!r}")


def _yaml_flow_mapping(text: str) -> dict[str, str]:
    """Parse a one-level YAML flow mapping ``{k: v, "k": 'v', ...}``.

    Keys and values may be plain, single-quoted, or double-quoted scalars.
    Raises ``HarnessError`` when the text is not such a mapping.
    """
    body = text.strip()
    if not (body.startswith("{") and body.endswith("}")):
        raise HarnessError(f"not a YAML flow mapping: {text!r}")
    inner = body[1:-1]
    result: dict[str, str] = {}
    index = 0

    def skip_space(pos: int) -> int:
        while pos < len(inner) and inner[pos] in " \t\r\n":
            pos += 1
        return pos

    def read_scalar(pos: int, is_key: bool) -> tuple[str, int]:
        pos = skip_space(pos)
        if pos < len(inner) and inner[pos] in "\"'":
            value, pos = _yaml_quoted_scalar(inner, pos)
            return value, skip_space(pos)
        begin = pos
        while pos < len(inner):
            char = inner[pos]
            if char == ",":
                break
            if is_key and char == ":":
                following = inner[pos + 1 : pos + 2]
                if following == "" or following in " \t\r\n,":
                    break
            if char in "{}[]":
                raise HarnessError(
                    f"nested flow collection in generated mapping: {text!r}"
                )
            pos += 1
        return inner[begin:pos].strip(), pos

    while True:
        index = skip_space(index)
        if index >= len(inner):
            break
        key, index = read_scalar(index, is_key=True)
        if index >= len(inner) or inner[index] != ":":
            raise HarnessError(f"flow mapping entry has no ':': {text!r}")
        value, index = read_scalar(index + 1, is_key=False)
        result[key] = value
        index = skip_space(index)
        if index < len(inner):
            if inner[index] != ",":
                raise HarnessError(f"unexpected text in flow mapping: {text!r}")
            index += 1
    return result


def _yaml_key(raw: str) -> str:
    text = raw.strip()
    if text and text[0] in "\"'":
        value, end = _yaml_quoted_scalar(text, 0)
        if text[end:].strip():
            raise HarnessError(f"unexpected text after quoted key: {raw!r}")
        return value
    return text


def _yaml_block_scalar(raw: str) -> str:
    text = raw.strip()
    if text and text[0] in "\"'":
        value, _end = _yaml_quoted_scalar(text, 0)
        return value
    return text


def _flow_mapping_text(first: str, following: list[str]) -> str:
    """Collect a flow mapping that may continue over following lines."""
    collected = first
    remaining = iter(following)
    while True:
        depth = 0
        quote: str | None = None
        index = 0
        while index < len(collected):
            char = collected[index]
            if quote is not None:
                if quote == '"' and char == "\\":
                    index += 2
                    continue
                if char == quote:
                    quote = None
            elif char in "\"'":
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return collected[: index + 1]
            index += 1
        nxt = next(remaining, None)
        if nxt is None:
            raise HarnessError(f"unterminated generated flow mapping: {first!r}")
        collected += "\n" + nxt


def generated_by_and_at(mapping_text: str) -> tuple[str, str]:
    """Return ``(by, at)`` from a generated mapping (flow or nested block).

    Keys and values may be plain or quoted, as YAML allows.
    """
    lines = mapping_text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(
            r"""^[ \t]*(?:generated|"generated"|'generated')[ \t]*:(.*)$""",
            line,
        )
        if match is None:
            continue
        rest = match.group(1).strip()
        if rest.startswith("{"):
            flow = _flow_mapping_text(rest, lines[index + 1 :])
            entries = _yaml_flow_mapping(flow)
            if "by" not in entries or "at" not in entries:
                raise HarnessError(
                    f"generated flow mapping is missing by or at: {flow!r}"
                )
            return entries["by"], entries["at"]
        by_val: str | None = None
        at_val: str | None = None
        parent_indent = len(line) - len(line.lstrip(" \t"))
        for nested in lines[index + 1 :]:
            if not nested.strip() or nested.strip().startswith("#"):
                continue
            indent = len(nested) - len(nested.lstrip(" \t"))
            if indent <= parent_indent:
                break
            nested_match = _BLOCK_KEY_LINE.match(nested.strip())
            if nested_match is None:
                continue
            nested_key = _yaml_key(nested_match.group(1))
            nested_val = _yaml_block_scalar(nested_match.group(2))
            if nested_key == "by":
                by_val = nested_val
            elif nested_key == "at":
                at_val = nested_val
        if by_val is None or at_val is None:
            raise HarnessError(
                "generated mapping is missing by or at; "
                f"mapping={mapping_text!r}"
            )
        return by_val, at_val
    raise HarnessError("generated mapping key is absent")


def parse_iso8601_combined_instant(value: str) -> datetime:
    """Parse ISO 8601 combined date-and-time into a UTC datetime.

    Date-only is not combined form. Seconds are optional. ``Z`` and numeric
    offsets are accepted. Raises ``HarnessError`` if the value cannot be
    classified as combined date-and-time.
    """
    text = value.strip()
    if not text:
        raise HarnessError("generated.at is empty; not combined date-and-time")
    match = _COMBINED_AT.match(text)
    if match is None:
        raise HarnessError(
            f"generated.at is not ISO 8601 combined date-and-time: {value!r}"
        )
    date = match.group("date")
    hour = match.group("hour")
    minute = match.group("minute")
    second = match.group("second") or "00"
    fraction = match.group("fraction")
    tz = match.group("tz")
    if fraction:
        fraction = fraction[:6].ljust(6, "0")
        time_part = f"{hour}:{minute}:{second}.{fraction}"
    else:
        time_part = f"{hour}:{minute}:{second}"
    if tz is None or tz == "Z":
        tz_norm = "+00:00"
    elif len(tz) == 5:
        tz_norm = f"{tz[:3]}:{tz[3:]}"
    else:
        tz_norm = tz
    stamp = f"{date}T{time_part}{tz_norm}"
    try:
        parsed = datetime.fromisoformat(stamp)
    except ValueError as exc:
        raise HarnessError(
            f"generated.at cannot be parsed as combined date-and-time: "
            f"{value!r}"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def assert_instant_in_invoke_window(
    instant: datetime, before: datetime, after: datetime
) -> None:
    """Parsed instant falls in the invoke window (minute-truncated lower bound)."""
    lo, hi = utc_instants_spanning_invoke(before, after)
    floor = lo.replace(second=0, microsecond=0)
    ceiling = hi + timedelta(seconds=1)
    print(
        f"[F05] at instant={instant.isoformat()} window=[{floor.isoformat()}, "
        f"{ceiling.isoformat()}]",
        flush=True,
    )
    if not (floor <= instant <= ceiling):
        raise AssertionError(
            f"generated.at instant {instant.isoformat()} is not the current "
            f"UTC time in the invoke window [{floor.isoformat()}, "
            f"{ceiling.isoformat()}]"
        )


def _split_flow_scalars(payload: str) -> list[str]:
    inner = payload.strip()
    if inner.startswith("[") and inner.endswith("]"):
        inner = inner[1:-1]
    scalars: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    for char in inner:
        if quote is not None:
            if char == quote:
                quote = None
            else:
                buf.append(char)
            continue
        if char in "\"'":
            quote = char
            continue
        if char == ",":
            token = "".join(buf).strip()
            if token:
                scalars.append(_strip_yaml_quotes(token))
            buf = []
            continue
        buf.append(char)
    token = "".join(buf).strip()
    if token:
        scalars.append(_strip_yaml_quotes(token))
    return scalars


def tag_scalars(mapping_text: str) -> list[str]:
    """Tags mapping value as a list of scalars (flow or block list)."""
    lines = mapping_text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^[ \t]*tags[ \t]*:(.*)$", line)
        if match is None:
            continue
        rest = match.group(1).strip()
        if rest:
            return _split_flow_scalars(rest)
        parent_indent = len(line) - len(line.lstrip(" \t"))
        items: list[str] = []
        for nested in lines[index + 1 :]:
            if not nested.strip() or nested.strip().startswith("#"):
                continue
            indent = len(nested) - len(nested.lstrip(" \t"))
            if indent <= parent_indent:
                break
            item = nested.strip()
            if item.startswith("- "):
                items.append(_strip_yaml_quotes(item[2:]))
            elif item.startswith("-"):
                items.append(_strip_yaml_quotes(item[1:]))
        if not items:
            raise HarnessError("tags key is present but has no scalars")
        return items
    raise HarnessError("tags mapping key is absent")


def tags_mapping_region(mapping_text: str) -> str:
    """Raw tags mapping value (same-line rest plus nested lines).

    Raises if the tags key is absent or has no value. Does not split on
    commas or trim tokens into separate scalars.
    """
    lines = mapping_text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^[ \t]*tags[ \t]*:(.*)$", line)
        if match is None:
            continue
        rest = match.group(1)
        parent_indent = len(line) - len(line.lstrip(" \t"))
        chunks = [rest]
        for nested in lines[index + 1 :]:
            if not nested.strip() or nested.strip().startswith("#"):
                continue
            indent = len(nested) - len(nested.lstrip(" \t"))
            if indent <= parent_indent:
                break
            chunks.append(nested)
        region = "\n".join(chunks)
        if not region.strip():
            raise HarnessError("tags key is present but has no value")
        return region
    raise HarnessError("tags mapping key is absent")


def assert_concept_written(
    path: str | Path,
    *,
    concept_type: str,
    generated_by: str,
    title: str | None = None,
    description: str | None = None,
    body_token: str | None = None,
    unused_body_token: str | None = None,
    unused_description_token: str | None = None,
) -> tuple[str, str]:
    """File exists with YAML type, generated.by, and optional field values."""
    if not path_is_file(path):
        raise AssertionError(f"concept file was not written: {path}")
    text = read_file(path)
    mapping, body = split_yaml_frontmatter(text)
    found_type = frontmatter_scalar(mapping, "type")
    print(
        f"[F05] concept {path} type={found_type!r} body_len={len(body)}",
        flush=True,
    )
    if found_type != concept_type:
        raise AssertionError(
            f"frontmatter type is {found_type!r}, expected {concept_type!r}"
        )
    by, at = generated_by_and_at(mapping)
    if by != generated_by:
        raise AssertionError(
            f"generated.by is {by!r}, expected {generated_by!r}"
        )
    parse_iso8601_combined_instant(at)
    if title is not None:
        found_title = frontmatter_scalar(mapping, "title")
        if found_title != title:
            raise AssertionError(
                f"frontmatter title is {found_title!r}, expected {title!r}"
            )
    if description is not None:
        found_desc = frontmatter_scalar(mapping, "description")
        if found_desc != description:
            raise AssertionError(
                f"frontmatter description is {found_desc!r}, expected "
                f"{description!r}"
            )
    if unused_description_token is not None and unused_description_token in mapping:
        raise AssertionError(
            "omitted description token appeared in frontmatter: "
            f"{unused_description_token!r}"
        )
    if body_token is not None and body_token not in body:
        raise AssertionError(
            f"supplied body token {body_token!r} is not in the post-fence body"
        )
    if unused_body_token is not None and unused_body_token in body:
        raise AssertionError(
            "omitted body token appeared after the fence: "
            f"{unused_body_token!r}"
        )
    assert_no_verified_key(mapping)
    return mapping, body


def _href_is_filename(href: str, filename: str) -> bool:
    target = href.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    if not target:
        return False
    target = target.split()[0]
    return target in {filename, f"./{filename}"}


def _list_item_texts(markdown: str) -> list[str]:
    items: list[str] = []
    for line in markdown.splitlines():
        match = _LIST_ITEM.match(line)
        if match is not None:
            items.append(match.group(1))
    return items


def listing_filename_targets(index_path: str | Path) -> list[str]:
    """Filename link targets (``file.md`` / ``./file.md``) in list items."""
    if not path_is_file(index_path):
        raise HarnessError(f"parent index is not a file: {index_path}")
    text = read_file(index_path)
    targets: list[str] = []
    for item in _list_item_texts(text):
        for _visible, href in _INLINE_LINK.findall(item):
            raw = href.strip().split()[0]
            if raw.startswith("./"):
                raw = raw[2:]
            if "/" not in raw.replace("\\", "/") and raw.endswith(".md"):
                targets.append(raw)
    return targets


def parent_index_listing_item(index_path: str | Path, filename: str) -> str:
    """The list item whose inline link target is *filename*."""
    if not path_is_file(index_path):
        raise HarnessError(f"parent index is not a file: {index_path}")
    text = read_file(index_path)
    matches: list[str] = []
    for item in _list_item_texts(text):
        for _visible, href in _INLINE_LINK.findall(item):
            if _href_is_filename(href, filename):
                matches.append(item)
                break
    if not matches:
        raise AssertionError(
            f"parent index has no list item linking to filename {filename!r}; "
            f"index={text!r}"
        )
    return matches[0]


def assert_parent_listing(
    index_path: str | Path,
    *,
    filename: str,
    title: str,
    description: str | None = None,
    unused_description_token: str | None = None,
) -> str:
    """Parent index lists the filename with title and optional description."""
    item = parent_index_listing_item(index_path, filename)
    visible_ok = False
    for visible, href in _INLINE_LINK.findall(item):
        if _href_is_filename(href, filename) and title in visible:
            visible_ok = True
            break
    print(
        f"[F05] listing item={item!r} filename={filename!r} title_in_link={visible_ok}",
        flush=True,
    )
    if not visible_ok:
        raise AssertionError(
            f"listing link for {filename!r} does not use title {title!r} as "
            f"visible text; item={item!r}"
        )
    stripped = item.replace(title, "").replace(filename, "").replace(f"./{filename}", "")
    if description is not None:
        if description not in stripped:
            raise AssertionError(
                "listing item does not contain the description after title "
                f"and filename are stripped; item={item!r}"
            )
    if unused_description_token is not None and unused_description_token in item:
        raise AssertionError(
            "omitted description token appeared in the listing item: "
            f"{unused_description_token!r} item={item!r}"
        )
    return item


def assert_filename_not_listed(index_path: str | Path, filename: str) -> None:
    """Existing parent index has no list item linking the new filename."""
    if not path_is_file(index_path):
        raise HarnessError(
            f"parent index should exist to observe a skipped listing: {index_path}"
        )
    text = read_file(index_path)
    for item in _list_item_texts(text):
        for _visible, href in _INLINE_LINK.findall(item):
            if _href_is_filename(href, filename):
                raise AssertionError(
                    f"skipped index still lists filename {filename!r}; "
                    f"item={item!r}"
                )


def assert_parent_index_absent(index_path: str | Path) -> None:
    """Missing parent index was not created."""
    if path_is_file(index_path):
        raise AssertionError(
            f"parent index was written when index bookkeeping was skipped: "
            f"{index_path}"
        )


def assert_nested_index_has_no_membundle_version(index_path: str | Path) -> None:
    """Nested parent index has no ``membundle_version`` key."""
    if not path_is_file(index_path):
        raise AssertionError(f"nested parent index was not created: {index_path}")
    text = read_file(index_path)
    try:
        mapping, _body = split_yaml_frontmatter(text)
    except HarnessError:
        print(f"[F05] nested index {index_path} has no frontmatter", flush=True)
        return
    try:
        version = membundle_version_declared(mapping)
    except HarnessError:
        print(
            f"[F05] nested index {index_path} frontmatter has no membundle_version",
            flush=True,
        )
        return
    raise AssertionError(
        f"nested parent index declared membundle_version {version!r}"
    )


def _heading_text_for_start(lines: list[str], content_start: int) -> str:
    marker = _heading_marker_line(lines, content_start)
    line = lines[marker]
    atx = _ATX.match(line)
    if atx is not None and line.lstrip().startswith("#"):
        return (atx.group(2) or "").strip()
    return line.strip()


def heading_texts(markdown: str) -> list[str]:
    """Ordered heading texts (ATX or Setext). Raises if none exist."""
    lines = markdown.splitlines()
    starts = _heading_content_starts(lines)
    if not starts:
        raise HarnessError("markdown has no heading with non-empty text")
    return [_heading_text_for_start(lines, start) for start in starts]


def dated_section_for_heading(log_markdown: str, date_text: str) -> str:
    """Section under the heading whose text is *date_text*."""
    lines = log_markdown.splitlines()
    starts = _heading_content_starts(lines)
    if not starts:
        raise HarnessError("log has no heading; cannot take a dated section")
    for index, start in enumerate(starts):
        text = _heading_text_for_start(lines, start)
        if text != date_text:
            continue
        begin = start
        if index + 1 < len(starts):
            end = _heading_marker_line(lines, starts[index + 1])
        else:
            end = len(lines)
        return "\n".join(lines[begin:end])
    raise HarnessError(
        f"log has no heading whose text is {date_text!r}; "
        f"headings={heading_texts(log_markdown)!r}"
    )


def _whole_token_present(text: str, token: str) -> bool:
    cleaned = _WRAP_PUNCT.sub(" ", text)
    return any(part == token for part in cleaned.split())


def _item_names_file(item: str, identity: str, filename: str) -> bool:
    posix_item = item.replace("\\", "/")
    return (
        filename in posix_item
        or f"{identity}.md" in posix_item
        or identity in posix_item
    )


def _creation_remainder(
    item: str,
    identity: str,
    filename: str,
    title: str | None,
    path_tokens: Sequence[str],
) -> str:
    tokens = [filename, f"{identity}.md", identity, *[str(t) for t in path_tokens if t]]
    if title:
        tokens.append(title)
    text = item
    for tok in sorted({t for t in tokens if t}, key=len, reverse=True):
        text = text.replace(tok, "")
    text = strip_generated_covariates(text)
    text = _WRAP_PUNCT.sub(" ", text)
    return text


def _creation_item_in_section(
    section: str,
    identity: str,
    filename: str,
    title: str | None,
    path_tokens: Sequence[str],
) -> str | None:
    """List item in the stated Creation bullet form for *identity*.

    Proposed log-bullet form: the item text (after the list marker) begins
    ``**Creation**: `` and contains ``<identity>.md``. *filename*, *title*,
    and *path_tokens* are kept for call compatibility and are not read.
    """
    return _log_bullet_in_section(section, "Creation", identity)


def _log_bullet_in_section(section: str, kind: str, identity: str) -> str | None:
    prefix = f"**{kind}**: "
    concept_path = f"{identity}.md"
    for item in _list_item_texts(section):
        if item.startswith(prefix) and concept_path in item:
            return item
    return None


def assert_creation_bullet(
    log_path: str | Path,
    *,
    identity: str,
    filename: str,
    today: str,
    title: str | None = None,
    path_tokens: Sequence[str] = (),
    expect_first_heading: bool = False,
    allowed_dates: frozenset[str] | None = None,
) -> str:
    """Today's UTC date heading has a Creation list item naming the new file."""
    if not path_is_file(log_path):
        raise HarnessError(f"log.md is not a file: {log_path}")
    text = read_file(log_path)
    headings = heading_texts(text)
    dates = allowed_dates if allowed_dates is not None else frozenset({today})
    today_headings = [h for h in headings if h in dates]
    print(
        f"[F05] log headings={headings!r} today={today!r} hits={today_headings!r}",
        flush=True,
    )
    if not today_headings:
        raise AssertionError(
            f"log.md has no heading whose text is today's UTC date among "
            f"{sorted(dates)}; headings={headings!r}"
        )
    heading_date = today_headings[0]
    if expect_first_heading:
        first = first_heading_text(text)
        if first not in dates:
            raise AssertionError(
                "today's UTC date heading was not inserted at the top; "
                f"first_heading={first!r} allowed={sorted(dates)}"
            )
    section = dated_section_for_heading(text, heading_date)
    item = _creation_item_in_section(
        section, identity, filename, title, path_tokens
    )
    if item is None:
        raise AssertionError(
            "dated heading section has no Creation list item naming "
            f"{filename!r}; section={section!r}"
        )
    return item


def assert_creation_absent(
    log_path: str | Path,
    *,
    identity: str,
    filename: str,
    title: str | None = None,
    path_tokens: Sequence[str] = (),
) -> None:
    """No Creation list item naming the new file appears in log.md."""
    if not path_is_file(log_path):
        raise HarnessError(f"log.md is not a file: {log_path}")
    text = read_file(log_path)
    item = _creation_item_in_section(
        text, identity, filename, title, path_tokens
    )
    if item is not None:
        raise AssertionError(
            "log.md gained a Creation bullet naming the new file when log "
            f"bookkeeping was skipped; item={item!r}"
        )


def assert_today_heading_not_duplicated(
    log_path: str | Path, today: str, allowed_dates: frozenset[str]
) -> None:
    """Exactly one heading whose text is today's UTC date."""
    text = read_file(log_path)
    headings = heading_texts(text)
    hits = [h for h in headings if h in allowed_dates or h == today]
    if len(hits) != 1:
        raise AssertionError(
            "log.md duplicated today's UTC date heading; "
            f"date_headings={hits!r} all={headings!r}"
        )


def _is_reserved_md(rel: str, bundle_rel: str) -> bool:
    posix = Path(rel).as_posix()
    if Path(posix).name == "index.md":
        return True
    bundle = Path(bundle_rel).as_posix()
    if bundle in ("", "."):
        return posix in {"log.md", "AGENTS.md"}
    prefix = bundle.rstrip("/") + "/"
    if posix.startswith(prefix):
        rest = posix[len(prefix) :]
        return rest in {"log.md", "AGENTS.md"}
    return False


def report_names_named_bundle(report: str, named: str) -> None:
    """Success report identifies *named* as the bundle, not only nested knowledge/.

    the PRD requires that human CLI success and the MCP create confirmation name
    the named path as the bundle. This does not pin message wording: it
    requires the caller-supplied path to appear, and requires at least one
    occurrence that is not the nested ``named/knowledge`` spelling.
    """
    if not report:
        raise AssertionError(
            "success report is empty; the PRD requires it name the named path "
            f"{named!r} as the bundle"
        )
    if named not in report:
        raise AssertionError(
            f"success report does not name the named path {named!r} as the "
            f"bundle; report={report!r}"
        )
    nested = f"{named}/knowledge"
    named_as_bundle = False
    start = 0
    while True:
        pos = report.find(named, start)
        if pos < 0:
            break
        if report[pos : pos + len(nested)] != nested:
            named_as_bundle = True
            break
        start = pos + 1
    if not named_as_bundle:
        raise AssertionError(
            "success report names the nested knowledge/ subdirectory as the "
            f"bundle, not the named path {named!r}; report={report!r}"
        )
    print(f"[F05] report names named bundle {named!r}", flush=True)


def assert_named_path_create_landing(
    named_root: str | Path,
    nested_root: str | Path,
    identity: str,
    *,
    concept_type: str,
    generated_by: str,
    title: str,
    description: str,
    body_token: str,
    nested_index_before: bytes,
    nested_log_before: bytes,
    today: str,
    allowed_dates: frozenset[str],
    path_tokens: Sequence[str],
) -> tuple[str, str]:
    """Concept and default bookkeeping land under the named path, not nested knowledge/.

    a named path is the write root even when it has no root
    ``index.md`` and contains a nested conventional bundle subdirectory.
    The new concept file, parent index, and log bookkeeping are present
    under the named path and absent from that nested subdirectory.
    """
    named = Path(named_root)
    nested = Path(nested_root)
    filename = concept_filename(identity)
    written = named / f"{identity}.md"
    nested_written = nested / f"{identity}.md"
    if not path_is_file(written):
        raise AssertionError(
            f"named-path create did not write the concept under the named "
            f"path: {written}"
        )
    if path_is_file(nested_written):
        raise AssertionError(
            "named-path create wrote the concept into the nested knowledge/ "
            f"subdirectory: {nested_written}"
        )
    mapping, body = assert_concept_written(
        written,
        concept_type=concept_type,
        generated_by=generated_by,
        title=title,
        description=description,
        body_token=body_token,
    )
    parent = named / "index.md"
    if not path_is_file(parent):
        raise AssertionError(
            "named-path create did not write parent-index bookkeeping under "
            f"the named path: {parent}"
        )
    assert_parent_listing(
        parent, filename=filename, title=title, description=description
    )
    log_path = named / "log.md"
    if not path_is_file(log_path):
        raise AssertionError(
            "named-path create did not write log bookkeeping under the "
            f"named path: {log_path}"
        )
    assert_creation_bullet(
        log_path,
        identity=identity,
        filename=filename,
        today=today,
        title=title,
        path_tokens=path_tokens,
        allowed_dates=allowed_dates,
    )
    if read_bytes(nested / "index.md") != nested_index_before:
        raise AssertionError(
            "named-path create changed the nested knowledge/ index.md; "
            "bookkeeping must stay under the named path"
        )
    if read_bytes(nested / "log.md") != nested_log_before:
        raise AssertionError(
            "named-path create changed the nested knowledge/ log.md; "
            "bookkeeping must stay under the named path"
        )
    print(
        f"[F05] named-path landing identity={identity!r} named={named} "
        f"nested_untouched=1",
        flush=True,
    )
    return mapping, body


def assert_no_new_concept_file(
    root: str | Path,
    before: Mapping[str, bytes],
    *,
    bundle_rel: str,
) -> dict[str, bytes]:
    """Workspace snapshot gained no new non-reserved Markdown concept file."""
    if not path_is_dir(root):
        raise HarnessError(f"not a directory, cannot snapshot: {root}")
    after = snapshot_tree(root)
    before_concepts = {
        key
        for key in before
        if key.endswith(".md") and not _is_reserved_md(key, bundle_rel)
    }
    after_concepts = {
        key
        for key in after
        if key.endswith(".md") and not _is_reserved_md(key, bundle_rel)
    }
    new = after_concepts - before_concepts
    print(f"[F05] new concept files={sorted(new)!r}", flush=True)
    if new:
        raise AssertionError(
            f"refusing create wrote new concept file(s): {sorted(new)!r}"
        )
    return after
