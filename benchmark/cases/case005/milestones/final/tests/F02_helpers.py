# feature: F02
"""Observation helpers for the bring-your-own-I/O connection (FP-02).

Helpers classify send / feed / pull outcomes. They never return a
sentinel to mean "the observation could not be classified". An absent
peer HTTP version is a classified record state (no field, or a present
empty/None value), not a probe crash. Pair states may arrive in any
container that can be resolved to the two sides.
"""

from __future__ import annotations

from typing import Any

from _harness import (
    CallResult,
    HarnessError,
    as_mapping,
    as_sequence,
    attr,
    call,
    call_method,
    require_exception,
    require_value,
)
from F01_helpers import (
    client_connection,
    connection_side_states,
    construct,
    event_ctor,
    local_protocol_error_type,
    package,
    remote_protocol_error_type,
    require_event,
    request_result,
)

_EVENT_KINDS = (
    "request",
    "informational",
    "response",
    "data",
    "end-of-message",
    "connection-closed",
)

_STATE_NAMES = (
    "IDLE",
    "SEND_RESPONSE",
    "SEND_BODY",
    "DONE",
    "MUST_CLOSE",
    "CLOSED",
    "MIGHT_SWITCH_PROTOCOL",
    "SWITCHED_PROTOCOL",
    "ERROR",
)

_ABSENT = object()


def client_role() -> Any:
    """Return the package-root client role. Missing raises."""
    pkg = package()
    try:
        role = getattr(pkg, "CLIENT")
    except AttributeError as exc:
        raise HarnessError("package root has no client role") from exc
    print(f"client_role={role!r}", flush=True)
    return role


def server_role() -> Any:
    """Return the package-root server role. Missing raises."""
    pkg = package()
    try:
        role = getattr(pkg, "SERVER")
    except AttributeError as exc:
        raise HarnessError("package root has no server role") from exc
    print(f"server_role={role!r}", flush=True)
    return role


def connection_for(role: Any) -> Any:
    """Construct a connection from an already-resolved role value."""
    pkg = package()
    try:
        ctor = getattr(pkg, "Connection")
    except AttributeError as exc:
        raise HarnessError("package root has no Connection") from exc
    if not callable(ctor):
        raise HarnessError(f"Connection is not callable; got {type(ctor)!r}")
    result = call(ctor, role)
    conn = require_value(result)
    print(f"connection_for role={role!r} type={type(conn).__name__}", flush=True)
    return conn


def server_connection() -> Any:
    """Construct a server-role connection from the package root."""
    conn = connection_for(server_role())
    print(f"server_connection type={type(conn).__name__}", flush=True)
    return conn


def named_state(name: str) -> Any:
    """Return one of the nine package-root states. Unknown or missing raises."""
    if name not in _STATE_NAMES:
        raise HarnessError(f"unknown state name {name!r}")
    pkg = package()
    try:
        value = getattr(pkg, name)
    except AttributeError as exc:
        raise HarnessError(f"package root has no state {name!r}") from exc
    print(f"named_state {name}={value!r}", flush=True)
    return value


def need_data_token() -> Any:
    """Return the package-root need-data result. Missing raises."""
    pkg = package()
    try:
        token = getattr(pkg, "NEED_DATA")
    except AttributeError as exc:
        raise HarnessError("package root has no need-data result") from exc
    print(f"need_data_token={token!r}", flush=True)
    return token


def send_event(conn: Any, event: Any) -> CallResult:
    """Encode *event* on *conn*. Never rewrites an exception as empty bytes."""
    result = call_method(conn, "send", event)
    print(
        f"send_event exc={type(result.exception).__name__ if result.exception else None} "
        f"value_type={type(result.value).__name__ if result.exception is None else None}",
        flush=True,
    )
    return result


def feed_bytes(conn: Any, data: Any) -> CallResult:
    """Store received bytes on *conn*. A crash is not treated as success."""
    result = call_method(conn, "receive_data", data)
    print(
        f"feed_bytes n={len(data) if isinstance(data, (bytes, bytearray)) else '?'} "
        f"exc={type(result.exception).__name__ if result.exception else None}",
        flush=True,
    )
    return result


def pull_next(conn: Any) -> CallResult:
    """Pull one event (or need-data) from *conn*."""
    result = call_method(conn, "next_event")
    print(
        f"pull_next exc={type(result.exception).__name__ if result.exception else None} "
        f"value_type={type(result.value).__name__ if result.exception is None else None}",
        flush=True,
    )
    return result


def require_send_bytes(result: CallResult) -> bytes:
    """Require send succeeded and returned a byte buffer (length may be 0).

    Failure raises — never returns ``b""`` to mean "send failed".
    """
    if result.exception is not None:
        raise HarnessError(
            "send raised "
            f"{type(result.exception).__name__}: {result.exception!r}; "
            "there are no bytes to observe"
        )
    value = result.value
    if type(value) is bytes:
        raw = value
    elif isinstance(value, (bytearray, memoryview)):
        raw = bytes(value)
    else:
        raise HarnessError(
            f"send did not return a byte buffer; got {type(value)!r}"
        )
    print(f"require_send_bytes len={len(raw)}", flush=True)
    return raw


def require_no_extra_bytes(result: CallResult) -> bytes:
    """Require send succeeded and produced no extra payload.

    ``None`` and a zero-length buffer both mean no bytes. An exception
    is never classified as "no bytes".
    """
    if result.exception is not None:
        raise HarnessError(
            "send raised "
            f"{type(result.exception).__name__}: {result.exception!r}; "
            "cannot treat a failure as no extra bytes"
        )
    value = result.value
    if value is None:
        print("require_no_extra_bytes none", flush=True)
        return b""
    if type(value) is bytes:
        raw = value
    elif isinstance(value, (bytearray, memoryview)):
        raw = bytes(value)
    else:
        raise HarnessError(
            f"send did not return a byte buffer or none; got {type(value)!r}"
        )
    if len(raw) != 0:
        raise AssertionError(
            f"expected no extra bytes; got {len(raw)} bytes {raw[:64]!r}"
        )
    print("require_no_extra_bytes empty", flush=True)
    return raw


def _event_types() -> tuple[type, ...]:
    return tuple(event_ctor(kind) for kind in _EVENT_KINDS)


def _is_need_data(value: Any) -> bool:
    token = need_data_token()
    if value is token:
        return True
    try:
        return value == token
    except Exception:
        return False


def require_need_data(result: CallResult) -> Any:
    """Require pull succeeded and returned need-data, not an event."""
    value = require_value(result)
    if any(isinstance(value, typ) for typ in _event_types()):
        raise AssertionError(
            f"pull returned an event {type(value)!r}, not need-data"
        )
    if not _is_need_data(value):
        raise AssertionError(
            f"pull returned {type(value)!r} {value!r}, not need-data"
        )
    print("require_need_data ok", flush=True)
    return value


def require_pulled_event(result: CallResult) -> Any:
    """Require pull succeeded and returned one of the six events."""
    value = require_value(result)
    if _is_need_data(value):
        raise AssertionError("pull returned need-data, not an event")
    types = _event_types()
    if not isinstance(value, types):
        raise AssertionError(
            f"pull returned {type(value)!r}, not an HTTP event"
        )
    print(f"require_pulled_event type={type(value).__name__}", flush=True)
    return value


def require_remote_refusal(result: CallResult) -> BaseException:
    """Require pull produced no event and a remote (not local, not runtime) error."""
    exc = require_exception(result)
    if result.value is not None and isinstance(result.value, _event_types()):
        raise AssertionError(
            f"remote refusal still produced an event: {type(result.value)!r}"
        )
    remote_t = remote_protocol_error_type()
    local_t = local_protocol_error_type()
    assert isinstance(exc, remote_t), (
        f"expected a remote protocol error, got {type(exc)!r}: {exc!r}"
    )
    assert not isinstance(exc, local_t), (
        "remote protocol error must not also be a local protocol error: "
        f"{type(exc)!r}"
    )
    print(f"remote refusal type={type(exc).__name__}", flush=True)
    return exc


def require_runtime_refusal(result: CallResult) -> BaseException:
    """Require a runtime error that is neither local nor remote protocol error.

    Unclassifiable failures raise. A particular English class name is
    not the only legal spelling of this kind.
    """
    exc = require_exception(result)
    local_t = local_protocol_error_type()
    remote_t = remote_protocol_error_type()
    assert not isinstance(exc, local_t), (
        f"expected a runtime error, got a local protocol error: {exc!r}"
    )
    assert not isinstance(exc, remote_t), (
        f"expected a runtime error, got a remote protocol error: {exc!r}"
    )
    print(f"runtime refusal type={type(exc).__name__}", flush=True)
    return exc


def require_no_connection(result: CallResult) -> BaseException:
    """Require construction failed and did not yield a connection object."""
    exc = require_exception(result)
    value = result.value
    if value is not None:
        pkg = package()
        try:
            ctor = getattr(pkg, "Connection")
        except AttributeError as probe:
            raise HarnessError(
                "cannot classify a connection object: package root has no Connection"
            ) from probe
        if isinstance(value, ctor):
            raise AssertionError(
                f"role refusal still produced a connection: {type(value)!r}"
            )
    print(f"no_connection type={type(exc).__name__}", flush=True)
    return exc


def peer_http_version(conn: Any) -> bytes | None:
    """Read the peer HTTP version record.

    Classified absence (no record, missing attribute, or a present
    None/empty value) returns ``None``. Values ``1.0`` / ``1.1`` are
    returned as those versions. An unclassifiable probe crash raises.
    Absence is never rewritten as ``1.1``.
    """
    if conn is None:
        raise HarnessError("cannot read peer HTTP version from None")
    try:
        present = hasattr(conn, "their_http_version")
    except Exception as exc:
        raise HarnessError(
            f"cannot probe peer HTTP version: {exc}"
        ) from exc
    if not present:
        print("peer_http_version absent (no record)", flush=True)
        return None
    try:
        value = getattr(conn, "their_http_version")
    except Exception as exc:
        raise HarnessError(
            f"cannot read peer HTTP version: {exc}"
        ) from exc
    if value is None:
        print("peer_http_version absent (None)", flush=True)
        return None
    if value in (b"", ""):
        print("peer_http_version absent (empty)", flush=True)
        return None
    if value in (b"1.0", "1.0"):
        print("peer_http_version=1.0", flush=True)
        return b"1.0"
    if value in (b"1.1", "1.1"):
        print("peer_http_version=1.1", flush=True)
        return b"1.1"
    raise HarnessError(
        f"unclassifiable peer HTTP version: {value!r}"
    )


def connection_pair_states(conn: Any) -> tuple[Any, Any]:
    """Read the pair of states resolved to (client_side, server_side).

    Accepts a role-keyed mapping, a two-item ``(our, their)`` pair, or
    a two-item ``(client, server)`` pair. Missing and unresolvable
    containers raise. Does not require one container shape.
    """
    our, their = connection_side_states(conn)
    client = client_role()
    server = server_role()
    our_role = attr(conn, "our_role")
    raw = attr(conn, "states")

    resolved_client: Any = _ABSENT
    resolved_server: Any = _ABSENT

    mapping: dict[Any, Any] | None
    try:
        mapping = as_mapping(raw)
    except HarnessError:
        mapping = None

    if mapping is not None:
        if client in mapping:
            resolved_client = mapping[client]
        if server in mapping:
            resolved_server = mapping[server]
        if resolved_client is _ABSENT or resolved_server is _ABSENT:
            their_role = server if our_role is client else client
            if our_role in mapping:
                if our_role is client:
                    resolved_client = mapping[our_role]
                elif our_role is server:
                    resolved_server = mapping[our_role]
            if their_role in mapping:
                if their_role is client:
                    resolved_client = mapping[their_role]
                elif their_role is server:
                    resolved_server = mapping[their_role]

    if resolved_client is _ABSENT or resolved_server is _ABSENT:
        try:
            items = as_sequence(raw)
        except HarnessError as exc:
            raise HarnessError(
                f"pair states are not a resolvable mapping or sequence: {exc}"
            ) from exc
        if len(items) != 2:
            raise HarnessError(
                f"pair states sequence has length {len(items)}, not 2"
            )
        first, second = items
        if our_role is client:
            if resolved_client is _ABSENT:
                resolved_client = first
            if resolved_server is _ABSENT:
                resolved_server = second
        elif our_role is server:
            if (first, second) == (our, their):
                if resolved_server is _ABSENT:
                    resolved_server = first
                if resolved_client is _ABSENT:
                    resolved_client = second
            elif (first, second) == (their, our):
                if resolved_client is _ABSENT:
                    resolved_client = first
                if resolved_server is _ABSENT:
                    resolved_server = second
            else:
                raise HarnessError(
                    "pair states sequence does not match our/their values: "
                    f"{first!r}, {second!r} vs our={our!r} their={their!r}"
                )
        else:
            raise HarnessError(
                f"cannot resolve pair states for unrecognized role {our_role!r}"
            )

    if resolved_client is _ABSENT or resolved_server is _ABSENT:
        raise HarnessError(
            "cannot resolve client and server sides from pair states"
        )
    print(
        f"connection_pair_states client={resolved_client!r} "
        f"server={resolved_server!r}",
        flush=True,
    )
    return (resolved_client, resolved_server)


def encoded_first_line(encoded: bytes) -> bytes:
    """Return the first line of encoded send bytes. Parse failure raises."""
    if not isinstance(encoded, (bytes, bytearray)):
        raise HarnessError(
            f"encoded_first_line expected bytes; got {type(encoded)!r}"
        )
    data = bytes(encoded)
    if b"\r\n" in data:
        return data.split(b"\r\n", 1)[0]
    if b"\n" in data:
        return data.split(b"\n", 1)[0]
    raise HarnessError(
        "encoded output has no line ending; cannot read the first line"
    )


def encoded_head_and_rest(encoded: bytes) -> tuple[bytes, bytes]:
    """Split encoded send bytes on the header-block blank line. Failure raises."""
    if not isinstance(encoded, (bytes, bytearray)):
        raise HarnessError(
            f"encoded_head_and_rest expected bytes; got {type(encoded)!r}"
        )
    data = bytes(encoded)
    for sep in (b"\r\n\r\n", b"\n\n"):
        if sep in data:
            head, rest = data.split(sep, 1)
            return head, rest
    raise HarnessError(
        "encoded output has no blank line after the header block"
    )


def status_line_reason(encoded: bytes, status_code: int) -> bytes:
    """Return the reason phrase after *status_code* on the encoded status line.

    Parse failure raises — never returns ``b""`` to mean "could not look".
    An omitted phrase is a successfully parsed empty reason.
    """
    line = encoded_first_line(encoded)
    parts = line.split(None, 2)
    if len(parts) < 2:
        raise HarnessError(
            f"status line {line!r} does not contain a status code"
        )
    try:
        got = int(parts[1])
    except ValueError as exc:
        raise HarnessError(
            f"status line {line!r} has a non-integer status {parts[1]!r}"
        ) from exc
    if got != status_code:
        raise HarnessError(
            f"status line {line!r} has status {got}, expected {status_code}"
        )
    if len(parts) == 2:
        print(
            f"status_line_reason status={status_code} reason=b''",
            flush=True,
        )
        return b""
    phrase = parts[2]
    print(
        f"status_line_reason status={status_code} reason={phrase!r}",
        flush=True,
    )
    return phrase


def wire_header_names(encoded: bytes) -> list[bytes]:
    """Return header names in encoded order (construction casing preserved)."""
    head, _ = encoded_head_and_rest(encoded)
    if b"\r\n" in head:
        lines = head.split(b"\r\n")
    else:
        lines = head.split(b"\n")
    names: list[bytes] = []
    for line in lines[1:]:
        if b":" not in line:
            continue
        name = line.split(b":", 1)[0]
        names.append(name)
    print(f"wire_header_names={names!r}", flush=True)
    return names


def wire_header_value(encoded: bytes, name: bytes) -> bytes:
    """Return the first header value whose name equals *name* (case-insensitive).

    Missing name or unparseable block raises — never returns empty to
    mean "not found".
    """
    head, _ = encoded_head_and_rest(encoded)
    if b"\r\n" in head:
        lines = head.split(b"\r\n")
    else:
        lines = head.split(b"\n")
    want = name.lower()
    for line in lines[1:]:
        if b":" not in line:
            continue
        raw_name, raw_value = line.split(b":", 1)
        if raw_name.strip().lower() == want:
            value = raw_value.strip()
            print(f"wire_header_value {name!r}={value!r}", flush=True)
            return value
    raise HarnessError(
        f"encoded header block has no {name!r} header"
    )


def make_request(**fields: Any) -> Any:
    """Construct a request event; default method GET and target /."""
    return require_event(request_result(**fields))


def make_informational(
    status_code: int = 100,
    headers: Any = (),
    reason: Any = None,
) -> Any:
    """Construct an informational-response event."""
    fields: dict[str, Any] = {"status_code": status_code, "headers": list(headers)}
    if reason is not None:
        fields["reason"] = reason
    return require_event(construct("informational", **fields))


def make_response(
    status_code: int = 200,
    headers: Any = (),
    reason: Any = None,
) -> Any:
    """Construct a final response event."""
    fields: dict[str, Any] = {"status_code": status_code, "headers": list(headers)}
    if reason is not None:
        fields["reason"] = reason
    return require_event(construct("response", **fields))


def make_data(payload: Any) -> Any:
    """Construct a data event with *payload*."""
    return require_event(construct("data", data=payload))


def make_eom() -> Any:
    """Construct an end-of-message event with no trailers."""
    return require_event(construct("end-of-message"))


def event_is_kind(event: Any, kind: str) -> bool:
    """Return whether *event* is the named event kind."""
    return isinstance(event, event_ctor(kind))


def fixed_get_headers(content_length: int = 10) -> list[tuple[str, str]]:
    """Headers for the fixed GET / Host example.com Content-Length walk."""
    return [("Host", "example.com"), ("Content-Length", str(content_length))]


def send_fixed_get(conn: Any, *, content_length: int = 10) -> bytes:
    """Send the fixed GET walk on *conn* and return the encoded bytes."""
    event = make_request(headers=fixed_get_headers(content_length))
    encoded = require_send_bytes(send_event(conn, event))
    print(f"public GET encoded len={len(encoded)}", flush=True)
    return encoded


def client_server_after_public_get() -> tuple[Any, Any, bytes, Any]:
    """Client send + server feed/pull of the fixed GET. Returns both sides."""
    client = client_connection()
    encoded = send_fixed_get(client)
    server = server_connection()
    fed = feed_bytes(server, encoded)
    if fed.exception is not None:
        raise HarnessError(f"feed of public GET failed: {fed.exception!r}")
    pulled = require_pulled_event(pull_next(server))
    return client, server, encoded, pulled


def header_index(
    names: list[bytes], needle: bytes, *, ignore_case: bool = False
) -> int:
    """Return the index of *needle* in *names*. Missing raises."""
    for index, name in enumerate(names):
        left = name.lower() if ignore_case else name
        right = needle.lower() if ignore_case else needle
        if left == right:
            return index
    raise AssertionError(f"header {needle!r} not in {names!r}")


def neighbor_request_pulls() -> Any:
    """Successful nearby request pull used as the live baseline for refusals."""
    server = server_connection()
    fed = feed_bytes(server, b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n")
    if fed.exception is not None:
        raise HarnessError(f"neighbor request feed failed: {fed.exception!r}")
    pulled = require_pulled_event(pull_next(server))
    if not event_is_kind(pulled, "request"):
        raise AssertionError(
            f"neighbor request pull was {type(pulled)!r}, not a request"
        )
    return pulled


def neighbor_response_pulls() -> Any:
    """Successful nearby response pull used as the live baseline for refusals."""
    client = client_connection()
    require_send_bytes(
        send_event(client, make_request(headers=[("Host", "example.com")]))
    )
    fed = feed_bytes(client, b"HTTP/1.1 200 \r\nContent-Length: 0\r\n\r\n")
    if fed.exception is not None:
        raise HarnessError(f"neighbor response feed failed: {fed.exception!r}")
    pulled = require_pulled_event(pull_next(client))
    if not event_is_kind(pulled, "response"):
        raise AssertionError(
            f"neighbor response pull was {type(pulled)!r}, not a response"
        )
    return pulled


__all__ = (
    "client_role",
    "client_server_after_public_get",
    "connection_for",
    "connection_pair_states",
    "encoded_first_line",
    "encoded_head_and_rest",
    "event_is_kind",
    "feed_bytes",
    "header_index",
    "neighbor_request_pulls",
    "neighbor_response_pulls",
    "fixed_get_headers",
    "send_fixed_get",
    "make_data",
    "make_eom",
    "make_informational",
    "make_request",
    "make_response",
    "named_state",
    "need_data_token",
    "peer_http_version",
    "pull_next",
    "require_need_data",
    "require_no_connection",
    "require_no_extra_bytes",
    "require_pulled_event",
    "require_remote_refusal",
    "require_runtime_refusal",
    "require_send_bytes",
    "send_event",
    "server_connection",
    "server_role",
    "status_line_reason",
    "wire_header_names",
    "wire_header_value",
)
