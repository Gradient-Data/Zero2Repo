# feature: F09
"""Observation helpers for the membundle mcp JSON-RPC server (FP-09).

Helpers raise ``HarnessError`` when a query cannot be classified, and
``AssertionError`` when a classified observation misses a carrier the
tests require. They never return ``None`` / ``{}`` / ``""`` / ``[]`` / ``0``
to mean "could not look".
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn

from _harness import (
    HarnessError,
    McpBatchResult,
    Workspace,
    encode_rpc_line,
    rpc_request,
)
from F03_helpers import (
    mcp_is_protocol_error,
    mcp_is_tool_error,
    mcp_reply_for_id,
)

SIX_TOOL_NAMES = frozenset(
    {
        "membundle_search",
        "membundle_show",
        "membundle_create",
        "membundle_update",
        "membundle_relate",
        "membundle_validate",
    }
)


# Recipe artifact name. The binary is built in a writable copy, not the judge cwd.
_BIN_REL = Path("bin") / "membundle"
_BUILD_LOCK = threading.Lock()
_BUILD_DONE = False
_BUILT_BIN: Path | None = None
_NEVER_STARTED = (
    "the server was never started; MCP results are missing"
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
    print(f"[F09] GOFLAGS=-buildvcs=false make build cwd={root}", flush=True)
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
        print(f"[F09] make build could not start: {exc}", flush=True)
        return False
    print(f"[F09] make build exit={completed.returncode}", flush=True)
    if completed.returncode != 0:
        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
        print(
            f"[F09] make build stdout={stdout[-2000:]!r} "
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
            print(f"[F09] resolved built binary={_BUILT_BIN!r}", flush=True)
        return _BUILT_BIN


def resolve_mcp_binary() -> Path:
    """Single resolver for every F09 ``membundle mcp`` start.

    When the pytest cwd contains the product sources, copies those sources
    to a writable directory, runs ``GOFLAGS=-buildvcs=false make build``
    there, and returns only that ``bin/membundle``. When that executable
    is absent, fails the test. Does not return an empty transcript, a
    synthetic JSON-RPC error, or a synthetic tool result: those are MCP
    outcomes, and an empty workspace would then look like a protocol
    failure or a tool error.
    """
    binary = _workdir_membundle()
    # TEST-FIX((none)): the build writes bin/membundle under the tree it runs in, which fails in a read-only working directory (hence the writable staging copy); without it the MCP server never starts and its results are missing.
    assert binary is not None, _NEVER_STARTED
    return binary


def _raise_if_mcp_binary_missing(binary: Path, exc: FileNotFoundError) -> NoReturn:
    """Turn a vanished workdir binary into the never-started assertion."""
    if binary.is_file() and os.access(binary, os.X_OK):
        raise exc
    # TEST-FIX(F09): with no bin/membundle there is no product to run before any JSON-RPC line; per the Contract "Build" form, make build at the repository root writes that binary.
    raise AssertionError(_NEVER_STARTED) from None


def initialize_request(request_id: int | str = 1) -> dict[str, Any]:
    """JSON-RPC initialize request. Client params are not read."""
    return rpc_request(
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "f09-suite", "version": "0"},
        },
        id=request_id,
    )


def mcp_script(
    ws: Workspace,
    extra_lines: Sequence[str | Mapping[str, Any]] = (),
    *,
    args: Sequence[str] | None = None,
    env_updates: dict[str, str | None] | None = None,
    cwd: str | Path | None = None,
    initialize_id: int | str = 1,
) -> McpBatchResult:
    """Initialize then *extra_lines* through ``membundle mcp`` (stdin closed)."""
    lines: list[str | Mapping[str, Any]] = [
        initialize_request(initialize_id),
        *list(extra_lines),
    ]
    print(
        f"[F09] mcp_script lines={len(lines)} args={args!r} cwd={cwd!r}",
        flush=True,
    )
    binary = resolve_mcp_binary()
    try:
        return ws.mcp_batch(
            lines, args=args, env_updates=env_updates, cwd=cwd, binary=binary
        )
    except FileNotFoundError as exc:
        _raise_if_mcp_binary_missing(binary, exc)


def tools_call_request(
    name: str,
    arguments: Mapping[str, Any] | None = None,
    *,
    request_id: int | str = 10,
) -> dict[str, Any]:
    """``tools/call`` with object params (name + arguments object)."""
    params: dict[str, Any] = {"name": name, "arguments": dict(arguments or {})}
    return rpc_request("tools/call", params, id=request_id)


def tools_call_params_line(
    *,
    request_id: int | str,
    shape: str,
) -> str:
    """Raw JSON-RPC line whose ``params`` is an array, a string, or omitted."""
    message: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
    }
    if shape == "array":
        message["params"] = []
    elif shape == "string":
        message["params"] = "not-an-object"
    elif shape == "omitted":
        pass
    else:
        raise HarnessError(f"unknown tools/call params shape {shape!r}")
    return encode_rpc_line(message)


def require_rpc_error_code(reply: Mapping[str, Any], code: int) -> Mapping[str, Any]:
    """Reply is a JSON-RPC error object whose numeric code equals *code*."""
    if not mcp_is_protocol_error(reply):
        raise AssertionError(
            f"reply is not a JSON-RPC error object (wanted code {code}); "
            f"reply={reply!r}"
        )
    error = reply.get("error")
    if not isinstance(error, Mapping):
        raise HarnessError(
            f"JSON-RPC error is not an object; cannot read a code: {reply!r}"
        )
    raw = error.get("code")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise HarnessError(
            f"JSON-RPC error has no numeric code; cannot classify: {reply!r}"
        )
    observed = int(raw)
    print(f"[F09] rpc error code={observed} wanted={code}", flush=True)
    assert observed == int(code), (
        f"JSON-RPC error code is {observed}, expected {int(code)}; "
        f"reply={reply!r}"
    )
    return error


def require_some_rpc_error_code(batch: McpBatchResult, code: int) -> dict[str, Any]:
    """Some stdout message is a JSON-RPC error with numeric *code*. Raise if none."""
    matches: list[dict[str, Any]] = []
    for message in batch.messages:
        if not isinstance(message, dict):
            raise HarnessError(
                f"MCP stdout line is not an object: {message!r}"
            )
        if not mcp_is_protocol_error(message):
            continue
        error = message.get("error")
        if not isinstance(error, Mapping):
            raise HarnessError(
                f"JSON-RPC error is not an object; cannot read a code: "
                f"{message!r}"
            )
        raw = error.get("code")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise HarnessError(
                f"JSON-RPC error has no numeric code; cannot classify: "
                f"{message!r}"
            )
        if int(raw) == int(code):
            matches.append(message)
    print(
        f"[F09] messages_with_code_{code}={len(matches)} total={len(batch.messages)}",
        flush=True,
    )
    if not matches:
        raise AssertionError(
            f"no stdout JSON-RPC error with code {int(code)}; "
            f"messages={batch.messages!r}"
        )
    return matches[0]


def require_initialize_handshake(reply: Mapping[str, Any]) -> Any:
    """Initialize result: ``protocolVersion``, ``serverInfo.name``, ``capabilities``.

    Reads the stated initialize result members directly.
    """
    if mcp_is_protocol_error(reply):
        raise AssertionError(
            "initialize replied with a JSON-RPC error object; "
            f"reply={reply!r}"
        )
    if "result" not in reply:
        raise AssertionError(f"initialize reply has no result member: {reply!r}")
    result = reply.get("result")
    assert isinstance(result, Mapping), (
        f"initialize result is not a JSON object: {result!r}"
    )
    protocol = result.get("protocolVersion")
    server_info = result.get("serverInfo")
    name = server_info.get("name") if isinstance(server_info, Mapping) else None
    print(
        f"[F09] initialize protocolVersion={protocol!r} serverInfo.name={name!r}",
        flush=True,
    )
    assert protocol == "2024-11-05", (
        f"initialize result protocolVersion is {protocol!r}, not '2024-11-05'; "
        f"result={result!r}"
    )
    assert isinstance(server_info, Mapping), (
        f"initialize result serverInfo is not an object: {result!r}"
    )
    assert name == "membundle-agent-memory", (
        f"initialize result serverInfo.name is {name!r}, not "
        f"'membundle-agent-memory'; result={result!r}"
    )
    assert_initialize_advertises_tools_resources_prompts(result)
    return result


def assert_initialize_advertises_tools_resources_prompts(result: Any) -> None:
    """Initialize ``capabilities`` has object members ``tools``, ``resources``, ``prompts``.

    The members of each capability object are free and are not read.
    """
    if not isinstance(result, Mapping):
        raise AssertionError(f"initialize result is not a JSON object: {result!r}")
    capabilities = result.get("capabilities")
    assert isinstance(capabilities, Mapping), (
        f"initialize result capabilities is not an object: {result!r}"
    )
    missing = [
        name
        for name in ("tools", "resources", "prompts")
        if not isinstance(capabilities.get(name), Mapping)
    ]
    print(
        f"[F09] initialize capabilities missing object members={missing!r}",
        flush=True,
    )
    assert not missing, (
        "initialize result capabilities does not carry object members "
        f"{missing!r}; capabilities={capabilities!r}"
    )


def require_empty_ping(reply: Mapping[str, Any]) -> Any:
    """Ping is a JSON-RPC success whose ``result`` is the empty object ``{}``.

    A reply that only echoes the request id (no result member) is not an
    empty result.
    """
    if mcp_is_protocol_error(reply):
        raise AssertionError(
            f"ping replied with a JSON-RPC error object; reply={reply!r}"
        )
    if "result" not in reply:
        raise AssertionError(
            "ping reply has no present result member; echoing the request "
            f"id alone is not an empty result; reply={reply!r}"
        )
    result = reply.get("result")
    print(f"[F09] ping result={result!r}", flush=True)
    assert isinstance(result, Mapping) and len(result) == 0, (
        f"ping result is not the empty object {{}}; reply={reply!r}"
    )
    return result


def listed_tool_names(result: Any) -> frozenset[str]:
    """Tool names from a ``tools/list`` result's ``tools`` array (each item's ``name``).

    The array has exactly six items with six distinct names; an extra tool
    object of any name fails.
    """
    if not isinstance(result, Mapping):
        raise AssertionError(f"tools/list result is not a JSON object: {result!r}")
    tools = result.get("tools")
    assert isinstance(tools, list), (
        f"tools/list result has no tools array: {result!r}"
    )
    names: list[str] = []
    for item in tools:
        assert isinstance(item, Mapping) and isinstance(item.get("name"), str), (
            f"tools/list item is not an object with a string name: {item!r}"
        )
        names.append(item["name"])
    print(f"[F09] listed tools={names!r}", flush=True)
    assert len(names) == len(set(names)), (
        f"tools/list repeats a tool name; names={names!r}"
    )
    extra = sorted(set(names) - SIX_TOOL_NAMES)
    if extra:
        raise AssertionError(
            "tools/list includes additional tool names "
            f"{extra!r}; listed={names!r}"
        )
    if len(tools) != 6:
        raise AssertionError(
            "tools/list tools array is not exactly six long; "
            f"length={len(tools)} names={names!r}"
        )
    return frozenset(names)


def assert_json_arrays_empty(result: Any, key: str) -> list[Any]:
    """Success result is an object whose *key* member is the empty array ``[]``.

    A protocol error is not an empty collection; neither is an empty
    object, a null member, or a missing member. Other members are free.
    """
    if isinstance(result, Mapping) and mcp_is_protocol_error(result):
        raise AssertionError(
            "protocol error is not an empty collection; "
            f"reply={result!r}"
        )
    if not isinstance(result, Mapping):
        raise AssertionError(f"list result is not a JSON object: {result!r}")
    value = result.get(key)
    print(f"[F09] list result {key}={value!r}", flush=True)
    assert isinstance(value, list) and len(value) == 0, (
        f"list result member {key!r} is not the empty array []; result={result!r}"
    )
    return value


def assert_request_reply_count(
    batch: McpBatchResult,
    request_ids: Sequence[int | str],
) -> None:
    """Stdout message count equals the request ids; each id has a reply."""
    wanted = list(request_ids)
    print(
        f"[F09] messages={len(batch.messages)} request_ids={wanted!r}",
        flush=True,
    )
    assert len(batch.messages) == len(wanted), (
        "stdout JSON-RPC message count does not equal the number of requests "
        f"that carried an id; messages={len(batch.messages)} ids={wanted!r} "
        f"payload={batch.messages!r}"
    )
    seen: list[Any] = []
    for message in batch.messages:
        if not isinstance(message, dict):
            raise HarnessError(
                f"MCP stdout line is not an object: {message!r}"
            )
        seen.append(message.get("id"))
    for request_id in wanted:
        mcp_reply_for_id(batch, request_id)


def require_tool_error_not_protocol(reply: Mapping[str, Any]) -> tuple[Any, str]:
    """Tool-error channel: result ``isError`` true, not a JSON-RPC protocol error.

    Returns the result object and the text of its first content item.
    """
    if mcp_is_protocol_error(reply):
        raise AssertionError(
            "failure used a JSON-RPC protocol error instead of the MCP "
            f"tool-error channel; reply={reply!r}"
        )
    assert mcp_is_tool_error(reply), (
        "reply is not marked as a tool error; a JSON-RPC success (including "
        f"an empty result) is not this class; reply={reply!r}"
    )
    return reply.get("result"), tool_result_text(reply)


def require_tool_success(reply: Mapping[str, Any]) -> tuple[Any, str]:
    """tools/call JSON-RPC result that is not a tool error and not a protocol error.

    Returns the result object and the text of its first content item.
    """
    if mcp_is_protocol_error(reply):
        raise AssertionError(
            f"tools/call returned a JSON-RPC protocol error; reply={reply!r}"
        )
    if mcp_is_tool_error(reply):
        raise AssertionError(
            f"tools/call marked a tool error on a success path; reply={reply!r}"
        )
    if "result" not in reply:
        raise AssertionError(
            f"tools/call success reply has no result member: {reply!r}"
        )
    return reply.get("result"), tool_result_text(reply)


def tool_result_text(reply: Mapping[str, Any]) -> str:
    """Text of the first content item of a ``tools/call`` result.

    The result is an object whose ``content`` is an array; its first item
    is an object with ``type`` ``text`` and a string ``text``.
    """
    result = reply.get("result")
    assert isinstance(result, Mapping), (
        f"tools/call reply has no result object: {reply!r}"
    )
    content = result.get("content")
    assert isinstance(content, list) and content, (
        f"tools/call result has no non-empty content array: {reply!r}"
    )
    first = content[0]
    assert (
        isinstance(first, Mapping)
        and first.get("type") == "text"
        and isinstance(first.get("text"), str)
    ), f"tools/call first content item is not a text item: {reply!r}"
    return first["text"]


def tool_result_json(reply: Mapping[str, Any], *, what: str) -> Any:
    """Parse the first content item text of a tools/call result as JSON."""
    text = tool_result_text(reply)
    try:
        return json.loads(text)
    except ValueError as exc:
        raise AssertionError(
            f"{what} tool result text is not JSON: {exc}; text={text!r}"
        ) from None


def require_tool_error_prefix(reply: Mapping[str, Any], prefix: str) -> str:
    """Tool error whose first content text begins with *prefix*."""
    _result, text = require_tool_error_not_protocol(reply)
    print(f"[F09] tool-error text={text!r} wanted prefix={prefix!r}", flush=True)
    assert text.startswith(prefix), (
        f"tool-error text does not begin {prefix!r}; text={text!r}"
    )
    return text


def assert_outside_root_remainder_distinct(
    outside_reply: Mapping[str, Any],
    unknown_reply: Mapping[str, Any],
    missing_reply: Mapping[str, Any],
    unknown_name: str,
) -> None:
    """Outside-root, unknown-tool, and missing-bundle tool errors carry their stated prefixes.

    ``Path traversal denied: `` for the outside-root bundle,
    ``Unknown tool: <name>`` for the unknown tool, and
    ``Failed to load bundle from `` for the missing inside-root bundle, so
    the outside-root failure is distinct from the other two classes.
    """
    require_tool_error_prefix(outside_reply, "Path traversal denied: ")
    require_tool_error_prefix(unknown_reply, f"Unknown tool: {unknown_name}")
    require_tool_error_prefix(missing_reply, "Failed to load bundle from ")


def batch_blob(batch: McpBatchResult) -> str:
    """Concatenated JSON of every stdout message plus decoded stdout. Raises on bad UTF-8."""
    chunks: list[str] = [batch.stdout_text]
    for message in batch.messages:
        try:
            chunks.append(json.dumps(message, ensure_ascii=False))
        except (TypeError, ValueError) as exc:
            raise HarnessError(
                f"cannot serialize MCP stdout message: {exc}; message={message!r}"
            ) from exc
    return "\n".join(chunks)


def assert_token_absent_from_batch(batch: McpBatchResult, token: str) -> None:
    """*token* does not appear in any stdout JSON-RPC message."""
    if not token:
        raise HarnessError("token is empty; cannot assert absence from the transcript")
    blob = batch_blob(batch)
    print(
        f"[F09] token {token!r} absent from transcript={token not in blob}",
        flush=True,
    )
    assert token not in blob, (
        f"stdout transcript contains token {token!r} that must be unread; "
        f"blob={blob!r}"
    )


def assert_token_present_in_text(text: str, token: str) -> None:
    """*token* appears in *text*. Empty text is a classified miss, not a lookup failure."""
    if not token:
        raise HarnessError("token is empty; cannot assert presence")
    if not isinstance(text, str):
        raise HarnessError(f"presence text is not a string: {text!r}")
    assert token in text, (
        f"success payload does not contain token {token!r}; text={text!r}"
    )


def mcp_search_hits(batch: McpBatchResult, request_id: int | str) -> list[dict[str, Any]]:
    """``membundle_search`` success: the tool text is a JSON array of hit objects.

    Not a protocol error and not a tool error. Each hit is an object with a
    string ``concept_id``. Zero hits is ``[]``.
    """
    reply = mcp_reply_for_id(batch, request_id)
    if mcp_is_protocol_error(reply):
        raise AssertionError(
            f"membundle_search returned a protocol error instead of a hit list: "
            f"{reply!r}"
        )
    if mcp_is_tool_error(reply):
        raise AssertionError(
            f"membundle_search marked a tool error on a successful search: {reply!r}"
        )
    hits = tool_result_json(reply, what="membundle_search")
    assert isinstance(hits, list), (
        f"membundle_search tool text is not a JSON array: {hits!r}"
    )
    for hit in hits:
        assert isinstance(hit, Mapping) and isinstance(hit.get("concept_id"), str), (
            f"membundle_search hit is not an object with a string concept_id: {hit!r}"
        )
    print(
        f"[F09] search id={request_id!r} hits={[h['concept_id'] for h in hits]!r}",
        flush=True,
    )
    return hits


def hit_ids(hits: Sequence[Mapping[str, Any]]) -> list[str]:
    """``concept_id`` of each hit, in rank order."""
    return [hit["concept_id"] for hit in hits]


def ordered_fixture_hit_ids(
    hits: Sequence[Mapping[str, Any]], expected: Sequence[str]
) -> list[str]:
    """Rank-ordered ``concept_id`` values; each is a fixture identity, none repeats."""
    ids = hit_ids(hits)
    for ident in ids:
        assert ident in expected, (
            f"hit concept_id {ident!r} is not one of the seeded identities"
        )
    assert len(ids) == len(set(ids)), f"a concept_id repeats among hits: {ids!r}"
    return ids


def require_empty_search(batch: McpBatchResult, request_id: int | str) -> list[Any]:
    """``membundle_search`` success whose hit array is ``[]``."""
    hits = mcp_search_hits(batch, request_id)
    assert hits == [], f"membundle_search returned hits where none fit: {hits!r}"
    return hits


def require_search_hits_identity(
    batch: McpBatchResult, request_id: int | str, identity: str
) -> list[Any]:
    """membundle_search hit array has a hit whose ``concept_id`` is *identity*."""
    hits = mcp_search_hits(batch, request_id)
    assert identity in hit_ids(hits), (
        "membundle_search success hit list has no hit whose concept_id is the "
        f"seeded identity {identity!r}; hits={hits!r}"
    )
    return hits


def mcp_validate_report(batch: McpBatchResult, request_id: int | str) -> dict[str, Any]:
    """``membundle_validate`` report: the tool text is one JSON object.

    Reads the stated members ``concept_count`` (integer), ``warnings``
    (array of strings), ``orphans`` (array or null), ``is_conformant`` and
    ``gate_passed`` (booleans). A protocol error is not a report.
    """
    reply = mcp_reply_for_id(batch, request_id)
    if mcp_is_protocol_error(reply):
        raise AssertionError(
            "membundle_validate returned a JSON-RPC protocol error instead of a "
            f"validate report; reply={reply!r}"
        )
    report = tool_result_json(reply, what="membundle_validate")
    assert isinstance(report, dict), (
        f"membundle_validate tool text is not a JSON object: {report!r}"
    )
    count = report.get("concept_count")
    assert isinstance(count, int) and not isinstance(count, bool), (
        f"validate report concept_count is not an integer: {report!r}"
    )
    for key in ("is_conformant", "gate_passed"):
        assert isinstance(report.get(key), bool), (
            f"validate report {key} is not a boolean: {report!r}"
        )
    warnings = report.get("warnings")
    assert isinstance(warnings, list) and all(
        isinstance(item, str) for item in warnings
    ), f"validate report warnings is not an array of strings: {report!r}"
    orphans = report.get("orphans")
    assert orphans is None or (
        isinstance(orphans, list) and all(isinstance(i, str) for i in orphans)
    ), f"validate report orphans is not an array of strings or null: {report!r}"
    print(
        f"[F09] validate id={request_id!r} concept_count={count} "
        f"is_conformant={report['is_conformant']} gate_passed={report['gate_passed']} "
        f"orphans={orphans!r} warnings={warnings!r}",
        flush=True,
    )
    return report


def assert_report_conformant_gate_fail(report: Mapping[str, Any]) -> None:
    """``is_conformant`` true and ``gate_passed`` false."""
    assert report["is_conformant"] is True and report["gate_passed"] is False, (
        "expected a conformant report whose producer gate failed; "
        f"is_conformant={report['is_conformant']!r} "
        f"gate_passed={report['gate_passed']!r}"
    )


def assert_report_both_pass(report: Mapping[str, Any]) -> None:
    """``is_conformant`` true and ``gate_passed`` true."""
    assert report["is_conformant"] is True and report["gate_passed"] is True, (
        "expected a conformant report whose producer gate passed; "
        f"is_conformant={report['is_conformant']!r} "
        f"gate_passed={report['gate_passed']!r}"
    )


def assert_orphan_listed(report: Mapping[str, Any], identity: str) -> None:
    """*identity* is one of the report's ``orphans``."""
    orphans = report.get("orphans") or []
    assert identity in orphans, (
        f"validate report orphans does not list {identity!r}; orphans={orphans!r}"
    )


def path_covariates(*paths: str | Path) -> list[str]:
    """Path spellings to strip from tool-error remainders."""
    tokens: list[str] = []
    for raw in paths:
        if raw is None:
            continue
        text = str(raw)
        if not text:
            continue
        tokens.append(text)
        posix = text.replace("\\", "/")
        tokens.append(posix)
        tokens.append(posix.rstrip("/"))
        name = Path(text).name
        if name:
            tokens.append(name)
        try:
            resolved = str(Path(text).resolve())
        except OSError:
            resolved = text
        tokens.append(resolved)
        tokens.append(resolved.replace("\\", "/"))
    return tokens
