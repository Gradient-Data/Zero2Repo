# feature: F06
"""Observation helpers for the membundle update command and membundle_update tool (FP-06).

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

from _harness import (
    HarnessError,
    McpBatchResult,
    RunResult,
    Workspace,
    path_is_file,
    read_bytes,
    read_file,
    rpc_request,
)
from F01_helpers import (
    combined_report,
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
)
from F05_helpers import (
    SEED_LOG_DATE,
    _class_remainder,
    _log_bullet_in_section,
    mcp_first_content_text,
    parent_index_listing_item,
    require_cli_rejected_failure,
    require_cli_usage_failure,
    require_mcp_tool_error_prefix,
    _INLINE_LINK,
    _href_is_filename,
    _list_item_texts,
    _whole_token_present,
    assert_instant_in_invoke_window,
    concept_file,
    concept_filename,
    dated_section_for_heading,
    frontmatter_scalar,
    generated_by_and_at,
    heading_texts,
    parent_index_path,
    parse_iso8601_combined_instant,
    seed_bundle,
)

_WRAP_PUNCT = re.compile(r"[\"'`\[\]\(\)\{\}<>*_.,:;]+")
_ISO_HEADING = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_KEY_LINE = re.compile(r"^[ \t]*([^:#\s][^:]*)[ \t]*:(.*)$")

SEED_GENERATED_AT = "2020-01-01T00:00:00Z"
SEED_GENERATED_BY = "seed/prior"
# Generated one-sentence description ending with a period (fresh per process).
def _gen_hex(n: int = 8) -> str:
    """Runtime-unique lowercase hex (the suite's own generated sample material)."""
    import uuid as _uuid

    return _uuid.uuid4().hex[:n]

SAMPLE_DESC = f"Use K{_gen_hex(6)}."

# Recipe artifact name. The binary is built in a writable copy, not the judge cwd.
_BIN_REL = Path("bin") / "membundle"
_BUILD_LOCK = threading.Lock()
_BUILD_DONE = False
_BUILT_BIN: Path | None = None
_NEVER_EXECUTED = (
    "the call was never executed; update results are missing"
)


@dataclass(frozen=True)
class McpUpdateOutcome:
    """Classified JSON-RPC reply to one membundle_update tools/call.

    A missing reply for the requested id raises ``HarnessError`` before
    this object is built. None of the fields is a sentinel for "no reply".
    """

    batch: McpBatchResult
    reply: dict[str, Any]
    payload: Any
    report_text: str


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
    print(f"[F06] GOFLAGS=-buildvcs=false make build cwd={root}", flush=True)
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
        print(f"[F06] make build could not start: {exc}", flush=True)
        return False
    print(f"[F06] make build exit={completed.returncode}", flush=True)
    if completed.returncode != 0:
        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
        print(
            f"[F06] make build stdout={stdout[-2000:]!r} "
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
            print(f"[F06] resolved built binary={_BUILT_BIN!r}", flush=True)
        return _BUILT_BIN


def resolve_update_binary() -> Path:
    """Single resolver for every F06 update-command and update-tool call.

    When the pytest cwd contains the product sources, copies those sources
    to a writable directory, runs ``GOFLAGS=-buildvcs=false make build``
    there, and returns only that ``bin/membundle``. When that executable
    is absent, fails the test. Does not return a synthetic non-zero
    result or a synthetic tool error: F06 refusal checks accept any
    non-zero exit and any tool error and would then pass on an empty
    workspace.
    """
    binary = _workdir_membundle()
    # TEST-FIX((none)): the build writes bin/membundle under the tree it runs in, which fails in a read-only working directory (hence the writable staging copy); without it update never runs and its results are missing.
    assert binary is not None, _NEVER_EXECUTED
    return binary


def _raise_if_update_binary_missing(binary: Path, exc: FileNotFoundError) -> NoReturn:
    """Turn a vanished workdir binary into the never-executed assertion."""
    if binary.is_file() and os.access(binary, os.X_OK):
        raise exc
    # TEST-FIX(F06): with no bin/membundle there is no product to run; per the Contract "Build" form, make build at the repository root writes that binary.
    raise AssertionError(_NEVER_EXECUTED) from None


def run_update(
    ws: Workspace,
    concept_id: str | None = None,
    bundle: str | Path | None = None,
    *,
    title: str | None = None,
    description: str | None = None,
    body: str | None = None,
    actor: str | None = None,
    skip_log: bool = False,
    skip_index: bool = False,
    structured: bool = False,
    extra_args: Sequence[str] = (),
    env_updates: dict[str, str | None] | None = None,
    cwd: str | Path | None = None,
) -> RunResult:
    """Invoke ``membundle update`` with identity, optional bundle, and caller options."""
    args: list[str] = ["update"]
    if concept_id is not None:
        args.append(str(concept_id))
    if bundle is not None:
        args.append(str(bundle))
    if title is not None:
        args.extend(["--title", title])
    if description is not None:
        args.extend(["--desc", description])
    if body is not None:
        args.extend(["--body", body])
    if actor is not None:
        args.extend(["--actor", actor])
    if skip_log:
        args.append("--no-log")
    if skip_index:
        args.append("--no-index")
    if structured:
        args.append("--json")
    args.extend(str(item) for item in extra_args)
    print(f"[F06] update argv={args!r} cwd={cwd!r}", flush=True)
    binary = resolve_update_binary()
    try:
        return ws.invoke(
            args, env_updates=env_updates, cwd=cwd, binary=binary
        )
    except FileNotFoundError as exc:
        _raise_if_update_binary_missing(binary, exc)


def run_update_with_instants(
    ws: Workspace,
    concept_id: str | None = None,
    bundle: str | Path | None = None,
    **kwargs: Any,
) -> tuple[RunResult, datetime, datetime]:
    """Run update and capture host UTC instants spanning the invoke."""
    before = datetime.now(timezone.utc)
    result = run_update(ws, concept_id, bundle, **kwargs)
    after = datetime.now(timezone.utc)
    return result, before, after


def require_update_success(result: RunResult) -> str:
    """CLI success carrier: POSIX success. Files are asserted separately."""
    report = combined_report(result)
    print(
        f"[F06] update-success exit={result.returncode} report_len={len(report)}",
        flush=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"update did not end successfully (exit {result.returncode}); "
            f"report={report!r}"
        )
    return report


def require_update_failure(result: RunResult) -> str:
    """CLI failure carrier: process status is not success."""
    report = combined_report(result)
    print(
        f"[F06] update-failure exit={result.returncode} report={report!r}",
        flush=True,
    )
    assert result.returncode != 0, (
        f"update ended successfully when it must not; report={report!r}"
    )
    return report


def class_remainder_after_identity(
    report: str, path_tokens: Sequence[str], identity: str
) -> str:
    """Remainder after stripping paths, identity, and generated covariates."""
    if not report:
        raise HarnessError("empty report; cannot compute a class remainder")
    stripped = report.replace(identity, "") if identity else report
    return _normalized_remainder(
        report_remainder_after_stripping_paths(
            strip_generated_covariates(stripped), path_tokens
        )
    )


def require_update_report_line(result: RunResult, identity: str, bundle: str) -> str:
    """Output forms, ``update`` (human): exactly one stdout line, wording free.

    The line contains ``'<identity>.md'`` and ``'<bundle>'``, where
    ``<bundle>`` is the bundle path as the caller named it (or the default
    bundle path).
    """
    require_update_success(result)
    expected = (f"'{identity}.md'", f"'{bundle}'")
    lines = result.stdout_text.splitlines()
    print(f"[F06] update stdout lines={lines!r} expected={expected!r}", flush=True)
    assert len(lines) == 1 and all(part in lines[0] for part in expected), (
        f"update human success is not one line containing {expected!r}; "
        f"stdout={result.stdout_text!r}"
    )
    return lines[0]


def require_update_not_found(result: RunResult, identity: str, what: str) -> str:
    """Output forms, Not found: status 1, stderr line begins ``Concept '<identity>' not found``."""
    lines = result.stderr_text.splitlines()
    prefix = f"Concept '{identity}' not found"
    print(
        f"[F06] not-found {what} exit={result.returncode} stderr={lines!r} "
        f"prefix={prefix!r}",
        flush=True,
    )
    assert result.returncode == 1, (
        f"{what}: not-found must end with status 1, got {result.returncode}; "
        f"stderr={lines!r}"
    )
    assert any(line.startswith(prefix) for line in lines), (
        f"{what}: standard error has no line that begins {prefix!r}; "
        f"stderr={lines!r} stdout={result.stdout_text!r}"
    )
    return result.stderr_text


def require_update_load_failure(result: RunResult, what: str) -> str:
    """Output forms, Load failure: status 2, stderr line begins ``Error loading bundle: ``."""
    lines = result.stderr_text.splitlines()
    print(
        f"[F06] load-failure {what} exit={result.returncode} stderr={lines!r}",
        flush=True,
    )
    assert result.returncode == 2, (
        f"{what}: load failure must end with status 2, got {result.returncode}; "
        f"stderr={lines!r}"
    )
    assert any(line.startswith("Error loading bundle: ") for line in lines), (
        f"{what}: standard error has no line that begins 'Error loading bundle: '; "
        f"stderr={lines!r} stdout={result.stdout_text!r}"
    )
    return result.stderr_text


def require_update_usage_failure(
    missing: RunResult,
    empty_identity: RunResult,
    reserved: RunResult,
    not_found: RunResult,
    load_error: RunResult,
    success: RunResult,
    *,
    not_found_identity: str,
    success_identity: str,
    success_bundle: str,
) -> str:
    """Missing identity is the Usage failure class; the others are their own classes.

    Each outcome is read in the class the Output forms section states for
    it: missing identity argument = Usage failure; empty and reserved
    identity = Rejected input; absent identity = Not found; missing bundle
    directory = Load failure; live update = the ``update`` success line.
    """
    report = require_cli_usage_failure(missing, "update with no identity argument")
    require_cli_rejected_failure(empty_identity, "update of the empty identity")
    require_cli_rejected_failure(reserved, "update of the reserved identity index")
    require_update_not_found(not_found, not_found_identity, "update of an absent identity")
    require_update_load_failure(load_error, "update in a missing bundle directory")
    require_update_report_line(success, success_identity, success_bundle)
    return report


def require_mcp_update_not_found(outcome: "McpUpdateOutcome", identity: str, what: str) -> str:
    """Tool-level failure ``Concept '<identity>' not found``."""
    return require_mcp_tool_error_prefix(
        outcome.reply, f"Concept '{identity}' not found", what
    )


def require_mcp_update_load_failure(outcome: "McpUpdateOutcome", what: str) -> str:
    """Tool-level failure ``Failed to load bundle from ``."""
    return require_mcp_tool_error_prefix(
        outcome.reply, "Failed to load bundle from ", what
    )


def require_mcp_update_report(
    outcome: "McpUpdateOutcome", identity: str, bundle_dir: str
) -> str:
    """Output forms, ``membundle_update`` result: exactly one line, wording free.

    The line contains ``<identity>.md`` and ends with `` <bundle>``, where
    ``<bundle>`` is the absolute bundle directory (symbolic links resolved).
    """
    require_mcp_update_success(outcome)
    text = mcp_first_content_text(outcome.reply)
    line = text[:-1] if text.endswith("\n") else text
    print(
        f"[F06] mcp update text={text!r} identity={identity!r} bundle={bundle_dir!r}",
        flush=True,
    )
    assert (
        "\n" not in line
        and f"{identity}.md" in line
        and line.endswith(f" {bundle_dir}")
    ), (
        f"membundle_update success text is not one line containing "
        f"{identity + '.md'!r} and ending with {' ' + bundle_dir!r}; text={text!r}"
    )
    return text


def mcp_membundle_update(
    ws: Workspace,
    arguments: Mapping[str, Any],
    *,
    request_id: int | str = 10,
    cwd: str | Path | None = None,
    env_updates: dict[str, str | None] | None = None,
) -> McpUpdateOutcome:
    """One ``membundle_update`` tools/call. A missing reply for *request_id* raises."""
    lines = [
        rpc_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "f06-suite", "version": "0"},
            },
            id=1,
        ),
        rpc_request(
            "tools/call",
            {"name": "membundle_update", "arguments": dict(arguments)},
            id=request_id,
        ),
    ]
    print(
        f"[F06] mcp membundle_update arguments={dict(arguments)!r} id={request_id!r}",
        flush=True,
    )
    binary = resolve_update_binary()
    try:
        batch = ws.mcp_batch(
            lines, cwd=cwd, env_updates=env_updates, binary=binary
        )
    except FileNotFoundError as exc:
        _raise_if_update_binary_missing(binary, exc)
    reply = mcp_reply_for_id(batch, request_id)
    payload, report_text = mcp_payload_and_text(reply)
    print(
        f"[F06] mcp reply protocol_error={mcp_is_protocol_error(reply)} "
        f"tool_error={mcp_is_tool_error(reply)} text={report_text!r}",
        flush=True,
    )
    return McpUpdateOutcome(
        batch=batch, reply=reply, payload=payload, report_text=report_text
    )


def mcp_update(
    ws: Workspace,
    concept_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
    body: str | None = None,
    bundle: str | Path | None = None,
    request_id: int | str = 10,
    cwd: str | Path | None = None,
    env_updates: dict[str, str | None] | None = None,
) -> McpUpdateOutcome:
    """membundle_update with required identity and optional title/description/body."""
    arguments: dict[str, Any] = {"concept_id": concept_id}
    if title is not None:
        arguments["title"] = title
    if description is not None:
        arguments["description"] = description
    if body is not None:
        arguments["body"] = body
    if bundle is not None:
        arguments["bundle"] = str(bundle)
    return mcp_membundle_update(
        ws,
        arguments,
        request_id=request_id,
        cwd=cwd,
        env_updates=env_updates,
    )


def mcp_update_with_instants(
    ws: Workspace,
    concept_id: str,
    **kwargs: Any,
) -> tuple[McpUpdateOutcome, datetime, datetime]:
    """Run membundle_update and capture host UTC instants spanning the invoke."""
    before = datetime.now(timezone.utc)
    outcome = mcp_update(ws, concept_id, **kwargs)
    after = datetime.now(timezone.utc)
    return outcome, before, after


def require_mcp_update_success(outcome: McpUpdateOutcome) -> str:
    """MCP success: not a tool error and not a protocol error."""
    if not outcome.batch.stdout and not outcome.batch.stderr:
        raise HarnessError("membundle_update produced a silent empty transcript")
    if mcp_is_protocol_error(outcome.reply):
        raise AssertionError(
            f"membundle_update returned a protocol error instead of a tool result: "
            f"{outcome.reply!r}"
        )
    if mcp_is_tool_error(outcome.reply):
        raise AssertionError(
            f"membundle_update marked a tool error on a successful update: "
            f"{outcome.report_text!r}"
        )
    return outcome.report_text


def require_mcp_update_tool_error(outcome: McpUpdateOutcome) -> str:
    """MCP update without identity: tool-error channel, not a protocol error."""
    if not outcome.batch.stdout and not outcome.batch.stderr:
        raise HarnessError("membundle_update produced a silent empty transcript")
    if mcp_is_protocol_error(outcome.reply):
        raise AssertionError(
            "membundle_update without identity rejected the call as a JSON-RPC "
            "protocol error; the PRD requires that missing-identity MCP update "
            f"as a tool error, not a protocol error; reply={outcome.reply!r}"
        )
    assert mcp_is_tool_error(outcome.reply), (
        "membundle_update without identity is not marked as a tool error; a "
        "successful tools/call is not this class; "
        f"reply={outcome.reply!r}"
    )
    return outcome.report_text


def require_mcp_update_non_success(outcome: McpUpdateOutcome) -> str:
    """MCP update did not succeed. Tool-error vs JSON-RPC channel is not distinguished here."""
    if not outcome.batch.stdout and not outcome.batch.stderr:
        raise HarnessError("membundle_update produced a silent empty transcript")
    if mcp_is_protocol_error(outcome.reply) or mcp_is_tool_error(outcome.reply):
        return outcome.report_text
    raise AssertionError(
        "membundle_update succeeded as a tools/call result when the update must "
        f"not succeed; reply={outcome.reply!r}"
    )


def _render_updatable_markdown(
    *,
    concept_type: str,
    title: str,
    description: str,
    body: str,
    generated_by: str,
    generated_at: str,
    extra: Mapping[str, str] | None = None,
    verified_by: str | None = None,
    verified_at: str | None = None,
    sources_token: str | None = None,
    tags: Sequence[str] | None = None,
    status: str | None = None,
    governance: str | None = None,
    code_refs: str | None = None,
) -> str:
    lines = [
        "---",
        f"type: {concept_type}",
        f"title: {title}",
        f"description: {description}",
    ]
    if tags:
        lines.append("tags:")
        for tag in tags:
            lines.append(f"  - {tag}")
    lines.append("generated:")
    lines.append(f"  by: {generated_by}")
    lines.append(f"  at: {generated_at}")
    if verified_by is not None and verified_at is not None:
        lines.append(f"verified: {{ by: {verified_by}, at: {verified_at} }}")
    if sources_token is not None:
        lines.append("sources:")
        lines.append(f"  - resource: {sources_token}")
    if status is not None:
        lines.append(f"status: {status}")
    if governance is not None:
        lines.append(f"governance: {governance}")
    if code_refs is not None:
        lines.append("code_refs:")
        lines.append(f"  - {code_refs}")
    if extra:
        for key, value in extra.items():
            lines.append(f"{key}: {value}")
    lines.append("---")
    body_text = body if body.endswith("\n") else body + "\n"
    return "\n".join(lines) + "\n" + body_text


def _write_parent_listing(
    bundle: Path, identity: str, title: str, description: str
) -> None:
    filename = concept_filename(identity)
    index = parent_index_path(bundle, identity)
    index.parent.mkdir(parents=True, exist_ok=True)
    item = f"* [{title}]({filename}) - {description}\n"
    if index.is_file():
        existing = index.read_text(encoding="utf-8")
        index.write_text(existing.rstrip("\n") + "\n" + item, encoding="utf-8")
    else:
        index.write_text(f"# Index\n\n{item}", encoding="utf-8")


def seed_updatable_concept(
    ws: Workspace,
    rel: str | Path,
    identity: str,
    *,
    concept_type: str,
    title: str,
    description: str,
    body: str,
    extra: Mapping[str, str] | None = None,
    generated_by: str = SEED_GENERATED_BY,
    generated_at: str = SEED_GENERATED_AT,
    verified_by: str | None = None,
    verified_at: str | None = None,
    sources_token: str | None = None,
    tags: Sequence[str] | None = None,
    status: str | None = None,
    governance: str | None = None,
    code_refs: str | None = None,
    agents: str | None = None,
    write_listing: bool = True,
) -> Path:
    """Seed a bundle plus one updatable concept. Does not call the product."""
    extra_map = dict(extra) if extra is not None else {}
    if extra_map and len(extra_map) < 2:
        raise HarnessError(
            "seed extra keys must be two runtime-unique keys so preserving "
            f"only one fails; got {sorted(extra_map)!r}"
        )
    root = seed_bundle(ws, rel, agents=agents)
    dest = concept_file(root, identity)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        _render_updatable_markdown(
            concept_type=concept_type,
            title=title,
            description=description,
            body=body,
            generated_by=generated_by,
            generated_at=generated_at,
            extra=extra_map or None,
            verified_by=verified_by,
            verified_at=verified_at,
            sources_token=sources_token,
            tags=tags,
            status=status,
            governance=governance,
            code_refs=code_refs,
        ),
        encoding="utf-8",
    )
    if write_listing:
        _write_parent_listing(root, identity, title, description)
    print(
        f"[F06] seeded updatable {identity!r} at {dest} extras={sorted(extra_map)}",
        flush=True,
    )
    return root


def _mapping_has_key(mapping_text: str, key: str) -> bool:
    pattern = re.compile(rf"^[ \t]*{re.escape(key)}[ \t]*:")
    for line in mapping_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if pattern.match(line):
            return True
    return False


def _mapping_region(mapping_text: str, key: str) -> str:
    """Raw mapping value (same-line rest plus nested lines). Raises if absent."""
    lines = mapping_text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(rf"^[ \t]*{re.escape(key)}[ \t]*:(.*)$", line)
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
            raise HarnessError(f"{key} key is present but has no value")
        return region
    raise HarnessError(f"{key} mapping key is absent")


def assert_extra_keys_survive(mapping_text: str, extra: Mapping[str, str]) -> None:
    """Each seeded unknown extra key still equals its seeded scalar."""
    if len(extra) < 2:
        raise HarnessError(
            "extra-key survival requires two keys so keeping only one fails"
        )
    for key, expected in extra.items():
        found = frontmatter_scalar(mapping_text, key)
        print(f"[F06] extra {key!r}={found!r} expected={expected!r}", flush=True)
        if found != expected:
            raise AssertionError(
                f"unknown extra key {key!r} did not survive the rewrite: "
                f"found {found!r}, seeded {expected!r}"
            )


def assert_verified_survives(
    mapping_text: str, verified_by: str, verified_at: str
) -> None:
    """Verified mapping still has the seeded by and at token."""
    region = _mapping_region(mapping_text, "verified")
    print(f"[F06] verified region={region!r}", flush=True)
    if verified_by not in region:
        raise AssertionError(
            f"verified.by token {verified_by!r} is absent after the rewrite; "
            f"region={region!r}"
        )
    if verified_at not in region:
        raise AssertionError(
            f"verified.at token {verified_at!r} is absent after the rewrite; "
            f"region={region!r}"
        )
    by, _at = generated_by_and_at(mapping_text)
    if by != verified_by and by in region:
        raise AssertionError(
            "update invented a verified entry using generated.by "
            f"{by!r}; verified region={region!r}"
        )


def assert_sources_survive(mapping_text: str, sources_token: str) -> None:
    """Sources token is still present in frontmatter."""
    if not _mapping_has_key(mapping_text, "sources"):
        raise AssertionError(
            "sources mapping key is absent after the rewrite; "
            f"mapping={mapping_text!r}"
        )
    region = _mapping_region(mapping_text, "sources")
    if sources_token not in region:
        raise AssertionError(
            f"sources token {sources_token!r} is absent after the rewrite; "
            f"region={region!r}"
        )


def assert_description_cleared(mapping_text: str, old_description: str) -> None:
    """Old description token is not the description value. Key may remain."""
    if not _mapping_has_key(mapping_text, "description"):
        print("[F06] description key absent after clear", flush=True)
        return
    value = frontmatter_scalar(mapping_text, "description")
    print(f"[F06] cleared description value={value!r}", flush=True)
    if value == old_description or old_description in value:
        raise AssertionError(
            "empty-description update left the old description as the "
            f"description value: {value!r}"
        )


def assert_concept_updated(
    path: str | Path,
    *,
    concept_type: str,
    generated_by: str,
    seed_generated_at: str,
    before: datetime,
    after: datetime,
    title: str | None = None,
    description: str | None = None,
    body_token: str | None = None,
    absent_body_token: str | None = None,
) -> tuple[str, str]:
    """File exists with original type, optional field values, and a new generated.at."""
    if not path_is_file(path):
        raise AssertionError(f"concept file is missing after update: {path}")
    text = read_file(path)
    mapping, body = split_yaml_frontmatter(text)
    found_type = frontmatter_scalar(mapping, "type")
    print(
        f"[F06] concept {path} type={found_type!r} body_len={len(body)}",
        flush=True,
    )
    if found_type != concept_type:
        raise AssertionError(
            f"frontmatter type is {found_type!r}, expected original {concept_type!r}"
        )
    by, at = generated_by_and_at(mapping)
    if by != generated_by:
        raise AssertionError(
            f"generated.by is {by!r}, expected {generated_by!r}"
        )
    if at == seed_generated_at:
        raise AssertionError(
            "generated.at was not refreshed; still the planted seed "
            f"{seed_generated_at!r}"
        )
    instant = parse_iso8601_combined_instant(at)
    assert_instant_in_invoke_window(instant, before, after)
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
    if body_token is not None and body_token not in body:
        raise AssertionError(
            f"supplied body token {body_token!r} is not in the post-fence body"
        )
    if absent_body_token is not None and absent_body_token in body:
        raise AssertionError(
            f"replaced body token {absent_body_token!r} is still after the fence"
        )
    return mapping, body


def _item_names_concept(item: str, identity: str, filename: str) -> bool:
    posix = item.replace("\\", "/")
    return (
        filename in posix
        or f"{identity}.md" in posix
        or identity in posix
    )


def listing_item_naming_concept(
    index_path: str | Path,
    identity: str,
    filename: str,
    *,
    must_contain: str | None = None,
) -> str:
    """The parent-index list item whose inline link target is *filename*.

    Full_PRD create/update: the parent listing is a Markdown bullet whose
    link target is the concept filename. *identity* is kept for call
    compatibility. With *must_contain*, that item must contain it.
    """
    first = parent_index_listing_item(index_path, filename)
    if must_contain is None:
        return first
    text = read_file(index_path)
    for item in _list_item_texts(text):
        if must_contain not in item:
            continue
        for _visible, href in _INLINE_LINK.findall(item):
            if _href_is_filename(href, filename):
                return item
    raise AssertionError(
        f"parent index has no list item linking {filename!r} that contains "
        f"{must_contain!r}; index={text!r}"
    )


def _strip_listing_identity(
    item: str, identity: str, filename: str, title: str | None = None
) -> str:
    tokens = [filename, f"{identity}.md", identity]
    if title:
        tokens.append(title)
    text = item
    for tok in sorted({t for t in tokens if t}, key=len, reverse=True):
        text = text.replace(tok, "")
    return text


def assert_listing_follows_description(
    index_path: str | Path,
    *,
    identity: str,
    filename: str,
    new_description: str,
    old_description: str,
    title: str | None = None,
) -> str:
    """Item that names the concept: after strip, new desc present and old gone."""
    item = listing_item_naming_concept(
        index_path, identity, filename, must_contain=new_description
    )
    stripped = _strip_listing_identity(item, identity, filename, title)
    print(f"[F06] listing item={item!r} stripped={stripped!r}", flush=True)
    if new_description not in stripped:
        raise AssertionError(
            "listing item that names the concept does not contain the new "
            f"description after title/filename/identity strip; item={item!r}"
        )
    if old_description in stripped:
        raise AssertionError(
            "listing item that names the concept still contains the old "
            f"description after title/filename/identity strip; item={item!r}"
        )
    return item


def assert_listing_keeps_old_description(
    index_path: str | Path,
    *,
    identity: str,
    filename: str,
    old_description: str,
    new_description: str,
) -> str:
    """Skip-index: the item still names the concept and keeps the old description."""
    item = listing_item_naming_concept(index_path, identity, filename)
    print(f"[F06] skip-index listing item={item!r}", flush=True)
    if old_description not in item:
        raise AssertionError(
            "skipped index no longer contains the old description on the "
            f"item that names the concept; item={item!r}"
        )
    if new_description in item:
        raise AssertionError(
            "skipped index listing was rewritten with the new description; "
            f"item={item!r}"
        )
    return item


def assert_listing_cleared_description(
    index_path: str | Path,
    *,
    identity: str,
    filename: str,
    old_description: str,
    title: str | None = None,
) -> str:
    """Empty-description: item still names the concept; old desc gone after strip."""
    item = listing_item_naming_concept(index_path, identity, filename)
    stripped = _strip_listing_identity(item, identity, filename, title)
    print(f"[F06] cleared listing item={item!r} stripped={stripped!r}", flush=True)
    if old_description in stripped:
        raise AssertionError(
            "listing item still contains the old description after it was "
            f"cleared; item={item!r}"
        )
    return item


def _update_item_remainder(
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
    text = _ISO_DATE.sub(" ", text)
    text = _WRAP_PUNCT.sub(" ", text)
    return text


def _update_item_in_section(
    section: str,
    identity: str,
    filename: str,
    title: str | None,
    path_tokens: Sequence[str],
) -> str | None:
    """List item in the stated Update bullet form for *identity*.

    Proposed log-bullet form: the item text (after the list marker) begins
    ``**Update**: `` and contains ``<identity>.md``. *filename*, *title*,
    and *path_tokens* are kept for call compatibility and are not read.
    """
    return _log_bullet_in_section(section, "Update", identity)


def assert_update_bullet(
    log_path: str | Path,
    *,
    identity: str,
    filename: str,
    today: str,
    title: str | None = None,
    path_tokens: Sequence[str] = (),
    allowed_dates: frozenset[str] | None = None,
    older_date: str = SEED_LOG_DATE,
) -> str:
    """Among dated headings, today appears, precedes the older seed, and has Update."""
    if not path_is_file(log_path):
        raise HarnessError(f"log.md is not a file: {log_path}")
    text = read_file(log_path)
    headings = heading_texts(text)
    dated = [h for h in headings if _ISO_HEADING.match(h)]
    dates = allowed_dates if allowed_dates is not None else frozenset({today})
    today_hits = [h for h in dated if h in dates]
    print(
        f"[F06] log dated={dated!r} today={today!r} hits={today_hits!r}",
        flush=True,
    )
    if not today_hits:
        raise AssertionError(
            "log.md has no dated heading whose text is today's UTC date among "
            f"{sorted(dates)}; dated={dated!r} all={headings!r}"
        )
    heading_date = today_hits[0]
    if older_date in dated:
        if dated.index(heading_date) >= dated.index(older_date):
            raise AssertionError(
                "today's UTC date heading does not precede the older seed date "
                f"among dated headings; dated={dated!r}"
            )
    section = dated_section_for_heading(text, heading_date)
    item = _update_item_in_section(
        section, identity, filename, title, path_tokens
    )
    if item is None:
        raise AssertionError(
            "dated heading section has no Update list item naming "
            f"{filename!r}; section={section!r}"
        )
    return item


def assert_update_absent(
    log_path: str | Path,
    *,
    identity: str,
    filename: str,
    title: str | None = None,
    path_tokens: Sequence[str] = (),
) -> None:
    """No Update list item naming the file appears in log.md."""
    if not path_is_file(log_path):
        raise HarnessError(f"log.md is not a file: {log_path}")
    text = read_file(log_path)
    item = _update_item_in_section(
        text, identity, filename, title, path_tokens
    )
    if item is not None:
        raise AssertionError(
            "log.md gained an Update bullet naming the file when log "
            f"bookkeeping was skipped; item={item!r}"
        )


def assert_named_path_update_landing(
    named_root: str | Path,
    nested_root: str | Path,
    identity: str,
    *,
    concept_type: str,
    generated_by: str,
    title: str,
    old_description: str,
    new_description: str,
    extra: Mapping[str, str],
    seed_generated_at: str,
    before: datetime,
    after: datetime,
    nested_concept_before: bytes,
    nested_index_before: bytes,
    nested_log_before: bytes,
    today: str,
    allowed_dates: frozenset[str],
    path_tokens: Sequence[str],
) -> tuple[str, str]:
    """Rewritten concept and bookkeeping land under the named path; nested stays."""
    named = Path(named_root)
    nested = Path(nested_root)
    filename = concept_filename(identity)
    written = named / f"{identity}.md"
    nested_written = nested / f"{identity}.md"
    if not path_is_file(written):
        raise AssertionError(
            f"named-path update did not write the concept under the named "
            f"path: {written}"
        )
    mapping, body = assert_concept_updated(
        written,
        concept_type=concept_type,
        generated_by=generated_by,
        seed_generated_at=seed_generated_at,
        before=before,
        after=after,
        title=title,
        description=new_description,
    )
    assert_extra_keys_survive(mapping, extra)
    parent = parent_index_path(named, identity)
    if not path_is_file(parent):
        raise AssertionError(
            "named-path update did not write parent-index bookkeeping under "
            f"the named path: {parent}"
        )
    assert_listing_follows_description(
        parent,
        identity=identity,
        filename=filename,
        new_description=new_description,
        old_description=old_description,
        title=title,
    )
    log_path = named / "log.md"
    if not path_is_file(log_path):
        raise AssertionError(
            "named-path update did not write log bookkeeping under the "
            f"named path: {log_path}"
        )
    assert_update_bullet(
        log_path,
        identity=identity,
        filename=filename,
        today=today,
        title=title,
        path_tokens=path_tokens,
        allowed_dates=allowed_dates,
        older_date=SEED_LOG_DATE,
    )
    if path_is_file(nested_written):
        if read_bytes(nested_written) != nested_concept_before:
            raise AssertionError(
                "named-path update changed the nested knowledge/ concept; "
                "nested files must remain as they were"
            )
    if read_bytes(nested / "index.md") != nested_index_before:
        raise AssertionError(
            "named-path update changed the nested knowledge/ index.md; "
            "nested files must remain as they were"
        )
    if read_bytes(nested / "log.md") != nested_log_before:
        raise AssertionError(
            "named-path update changed the nested knowledge/ log.md; "
            "nested files must remain as they were"
        )
    print(
        f"[F06] named-path landing identity={identity!r} named={named} "
        f"nested_untouched=1",
        flush=True,
    )
    return mapping, body


def assert_no_successful_rewrite(
    bundle: str | Path,
    identity: str,
    *,
    seed_title: str,
    seed_description: str,
    seed_body: str,
    seed_generated_at: str = SEED_GENERATED_AT,
    new_title: str | None = None,
    new_description: str | None = None,
    new_body: str | None = None,
    title: str | None = None,
    path_tokens: Sequence[str] = (),
) -> None:
    """Present identity was not rewritten: seed tokens, planted at, no Update item."""
    path = concept_file(bundle, identity)
    if not path_is_file(path):
        raise AssertionError(
            f"present concept file disappeared after a refusing update: {path}"
        )
    text = read_file(path)
    mapping, body = split_yaml_frontmatter(text)
    if seed_title not in text:
        raise AssertionError(
            f"refusing update dropped seed title {seed_title!r}"
        )
    if seed_description not in text:
        raise AssertionError(
            f"refusing update dropped seed description {seed_description!r}"
        )
    if seed_body not in body:
        raise AssertionError(
            f"refusing update dropped seed body token {seed_body!r}"
        )
    if new_title is not None and new_title and new_title in mapping:
        found = None
        if _mapping_has_key(mapping, "title"):
            found = frontmatter_scalar(mapping, "title")
        if found == new_title:
            raise AssertionError(
                f"refusing update wrote new title {new_title!r}"
            )
    if new_description is not None and new_description:
        if _mapping_has_key(mapping, "description"):
            found_desc = frontmatter_scalar(mapping, "description")
            if found_desc == new_description:
                raise AssertionError(
                    f"refusing update wrote new description {new_description!r}"
                )
    if new_body is not None and new_body and new_body in body:
        raise AssertionError(
            f"refusing update wrote new body token {new_body!r}"
        )
    _by, at = generated_by_and_at(mapping)
    if at != seed_generated_at:
        raise AssertionError(
            "refusing update refreshed generated.at; planted "
            f"{seed_generated_at!r} became {at!r}"
        )
    log_path = Path(bundle) / "log.md"
    if path_is_file(log_path):
        assert_update_absent(
            log_path,
            identity=identity,
            filename=concept_filename(identity),
            title=title if title is not None else seed_title,
            path_tokens=path_tokens,
        )
    print(f"[F06] no successful rewrite of {identity!r}", flush=True)
