# feature: F07
"""Observation helpers for informational responses, 100-continue, and switches.

Helpers classify send / feed / pull / start / flag / trailing outcomes.
They never return a sentinel to mean the observation could not be
classified. A missing waiting flag or a trailing-data probe that is
not a (bytes, bool) pair raises — it is never rewritten as False,
empty leftover, or "not waiting".
"""

from __future__ import annotations

from typing import Any

from _harness import (
    CallResult,
    HarnessError,
    as_bool,
    as_pair,
    attr,
)
from F01_helpers import (
    client_connection,
    connection_side_states,
    runtime_int,
    runtime_token,
)
from F02_helpers import (
    event_is_kind,
    make_data,
    make_eom,
    make_informational,
    make_request,
    make_response,
    named_state,
    pull_next,
    require_send_bytes,
    send_event,
    server_connection,
)
from F03_helpers import feed_ok, pull_kind, require_our_state
from F04_helpers import (
    require_both_done,
    require_paused,
    require_their_state,
    server_send_status,
)


# Waiting-flag reports are the two attributes the Interface Contract
# names. bind_waiting_reports still checks their role split.
_CLIENT_WAITING_NAME: str = "client_is_waiting_for_100_continue"
_THEY_WAITING_NAME: str = "they_are_waiting_for_100_continue"


def _public_bools(conn: Any) -> dict[str, bool]:
    """Map public attribute names to bool values. Probe failure raises.

    A missing listing, a lookup crash, or a public name that cannot
    be read is not rewritten as "no booleans" or False.
    """
    if conn is None:
        raise HarnessError("cannot read public booleans of None")
    try:
        names = dir(conn)
    except Exception as exc:
        raise HarnessError(
            f"cannot list public attributes of {type(conn).__name__}: {exc}"
        ) from exc
    found: dict[str, bool] = {}
    for name in names:
        if name.startswith("_"):
            continue
        raw = attr(conn, name)
        if callable(raw):
            continue
        if type(raw) is bool:
            try:
                found[name] = as_bool(raw)
            except HarnessError as exc:
                raise HarnessError(
                    f"public attribute {name!r} is not a bool: {exc}"
                ) from exc
    print(
        f"public_bools n={len(found)} true={sum(1 for v in found.values() if v)}",
        flush=True,
    )
    return found


def bind_waiting_reports(client: Any, server: Any) -> tuple[str, str]:
    """Check the two stated waiting reports on a waiting pair.

    After an HTTP/1.1 Expect 100-continue request has been sent by
    *client* and pulled by *server*: ``client_is_waiting_for_100_continue``
    is true on both connections, and ``they_are_waiting_for_100_continue``
    is true on the server-role connection and false on the client-role
    connection. Missing reports or a value that is not exactly a bool
    raise — never rewritten as False.
    """
    flags = {}
    for label, conn in (("client", client), ("server", server)):
        for name in (_CLIENT_WAITING_NAME, _THEY_WAITING_NAME):
            raw = attr(conn, name)
            if type(raw) is not bool:
                raise HarnessError(
                    f"{label} connection {name} is not a bool: {raw!r}"
                )
            flags[(label, name)] = raw
    if not (flags[("client", _CLIENT_WAITING_NAME)] is True
            and flags[("server", _CLIENT_WAITING_NAME)] is True):
        raise AssertionError(
            "client_is_waiting_for_100_continue is not true on both the "
            "client-role and server-role connections after Expect 100-continue"
        )
    if not (flags[("server", _THEY_WAITING_NAME)] is True
            and flags[("client", _THEY_WAITING_NAME)] is False):
        raise AssertionError(
            "they_are_waiting_for_100_continue is not true only on the "
            "server-role connection after Expect 100-continue"
        )
    print(
        "waiting_reports checked: client-waiting true on both, "
        "they-waiting true only on server",
        flush=True,
    )
    return _CLIENT_WAITING_NAME, _THEY_WAITING_NAME


def _ensure_waiting_reports() -> tuple[str, str]:
    """Return the two stated waiting-report attribute names."""
    return _CLIENT_WAITING_NAME, _THEY_WAITING_NAME


def _read_bound_bool(conn: Any, name: str, *, label: str) -> bool:
    raw = attr(conn, name)
    try:
        flag = as_bool(raw)
    except HarnessError as exc:
        raise HarnessError(f"{label} is not a bool: {exc}") from exc
    print(f"{label}={flag}", flush=True)
    return flag


def client_waiting_flag(conn: Any) -> bool:
    """Read whether the client is waiting for 100-continue.

    Reads the attribute the Interface Contract names.
    Attribute missing, probe crash, or a non-bool value raises. Never
    returns False to mean "could not look".
    """
    name, _they = _ensure_waiting_reports()
    return _read_bound_bool(conn, name, label="client_waiting_flag")


def they_are_waiting_flag(conn: Any) -> bool:
    """Read whether the peer is waiting for 100-continue.

    Reads the attribute the Interface Contract names.
    Attribute missing, probe crash, or a non-bool value raises. Never
    returns False to mean "could not look".
    """
    _client, name = _ensure_waiting_reports()
    return _read_bound_bool(conn, name, label="they_are_waiting_flag")


def require_waiting_flags(
    conn: Any, *, client_waiting: bool, they_waiting: bool
) -> None:
    """Require both waiting flags match. Unreadable flags raise."""
    got_client = client_waiting_flag(conn)
    got_they = they_are_waiting_flag(conn)
    if got_client is not client_waiting or got_they is not they_waiting:
        raise AssertionError(
            f"waiting flags client={got_client} they={got_they}, "
            f"expected client={client_waiting} they={they_waiting}"
        )
    print(
        f"require_waiting_flags client={client_waiting} they={they_waiting}",
        flush=True,
    )


def trailing_data_pair(conn: Any) -> tuple[bytes, bool]:
    """Return (unparsed bytes, receive-closed flag). Not a pair raises.

    Empty bytes are returned only when the public surface reports an
    empty leftover. Probe failure never becomes ``(b"", False)``.
    """
    raw = attr(conn, "trailing_data")
    try:
        leftover, closed = as_pair(raw)
    except HarnessError as exc:
        raise HarnessError(
            f"trailing data is not a (bytes, closed) pair: {exc}"
        ) from exc
    if isinstance(leftover, (bytes, bytearray, memoryview)):
        held = bytes(leftover)
    else:
        raise HarnessError(
            f"trailing leftover is not bytes: {type(leftover)!r}"
        )
    try:
        flag = as_bool(closed)
    except HarnessError as exc:
        raise HarnessError(
            f"trailing receive-closed flag is not a bool: {exc}"
        ) from exc
    print(
        f"trailing_data_pair len={len(held)} receive_closed={flag}",
        flush=True,
    )
    return held, flag


def require_receive_open(conn: Any) -> None:
    """Require the trailing-data receive-closed flag is false. Probe failure raises."""
    _held, closed = trailing_data_pair(conn)
    if closed:
        raise AssertionError("receive side is closed; expected still open")
    print("require_receive_open ok", flush=True)


def require_receive_closed(conn: Any) -> None:
    """Require the trailing-data receive-closed flag is true. Probe failure raises."""
    _held, closed = trailing_data_pair(conn)
    if not closed:
        raise AssertionError("receive side is still open; expected closed")
    print("require_receive_closed ok", flush=True)


def require_both_switched(conn: Any) -> None:
    """Require both sides are SWITCHED_PROTOCOL. Unreadable states raise."""
    require_our_state(conn, "SWITCHED_PROTOCOL")
    require_their_state(conn, "SWITCHED_PROTOCOL")
    print("require_both_switched ok", flush=True)


def require_not_switched(conn: Any) -> None:
    """Require neither side is SWITCHED_PROTOCOL. Unreadable states raise."""
    switched = named_state("SWITCHED_PROTOCOL")
    our, their = connection_side_states(conn)
    if our == switched or their == switched:
        raise AssertionError(
            f"a side is SWITCHED_PROTOCOL; our={our!r} their={their!r}"
        )
    print("require_not_switched ok", flush=True)


def fixed_expect_headers() -> list[tuple[str, str]]:
    """Public GET / Host example.com Content-Length 100 Expect 100-continue."""
    return [
        ("Host", "example.com"),
        ("Content-Length", "100"),
        ("Expect", "100-continue"),
    ]


def _complete_expect_request_bytes(
    *,
    version: bytes,
    host: str,
    target: str,
    content_length: int,
    expect_value: str,
) -> bytes:
    """A complete request whose request-line version is *version*.

    A host, target, or expect value that cannot form that complete
    request raises. A truncated prefix is never returned.
    """
    if version not in (b"1.0", b"1.1"):
        raise HarnessError(f"unsupported HTTP version {version!r}")
    if not host or not target:
        raise HarnessError(
            "complete Expect request needs a non-empty host and target; "
            f"got host={host!r} target={target!r}"
        )
    if content_length < 0:
        raise HarnessError(
            f"Content-Length {content_length} is negative; "
            "cannot form a complete request"
        )
    if any(ch in host for ch in "\r\n") or any(ch in target for ch in "\r\n"):
        raise HarnessError(
            "host or target contains a line break; cannot form a complete request"
        )
    if any(ch in expect_value for ch in "\r\n"):
        raise HarnessError(
            "Expect value contains a line break; cannot form a complete request"
        )
    try:
        host_b = host.encode("ascii")
        target_b = target.encode("ascii")
        expect_b = expect_value.encode("ascii")
        cl_b = str(content_length).encode("ascii")
    except UnicodeEncodeError as exc:
        raise HarnessError(
            f"cannot encode Expect request as ASCII: {exc}"
        ) from exc
    raw = (
        b"GET "
        + target_b
        + b" HTTP/"
        + version
        + b"\r\nHost: "
        + host_b
        + b"\r\nContent-Length: "
        + cl_b
        + b"\r\nExpect: "
        + expect_b
        + b"\r\n\r\n"
    )
    if not raw.startswith(b"GET "):
        raise HarnessError("complete Expect request is missing the request line")
    first, sep, rest = raw.partition(b"\r\n")
    if not sep or b"HTTP/" + version not in first:
        raise HarnessError(
            f"complete Expect request line is missing HTTP/{version!r}"
        )
    if b"Host: " not in raw or b"Expect: " not in raw:
        raise HarnessError("complete Expect request is missing Host or Expect")
    if not raw.endswith(b"\r\n\r\n"):
        raise HarnessError(
            "complete Expect request is missing the terminating blank line; "
            "refusing to return a prefix"
        )
    head, blank, after = raw.partition(b"\r\n\r\n")
    if not blank or after:
        raise HarnessError(
            "complete Expect request terminator is missing or trailed by extra bytes"
        )
    if b"\r\n" not in head:
        raise HarnessError(
            "complete Expect request has no header line after the request line"
        )
    print(
        f"complete_expect_request version={version!r} host={host!r} "
        f"target={target!r} cl={content_length} len={len(raw)}",
        flush=True,
    )
    return raw


def http11_expect_request_bytes(
    *, host: str, target: str, content_length: int, expect_value: str
) -> bytes:
    """Complete HTTP/1.1 Expect request. Incomplete construction raises."""
    return _complete_expect_request_bytes(
        version=b"1.1",
        host=host,
        target=target,
        content_length=content_length,
        expect_value=expect_value,
    )


def http10_expect_request_bytes(
    *, host: str, target: str, content_length: int, expect_value: str
) -> bytes:
    """Complete HTTP/1.0 Expect request. Incomplete construction raises."""
    return _complete_expect_request_bytes(
        version=b"1.0",
        host=host,
        target=target,
        content_length=content_length,
        expect_value=expect_value,
    )


def connect_request(
    *,
    target: str,
    host: str,
    content_length: int | None = 1,
    upgrade: str | None = None,
) -> Any:
    """Construct a CONNECT switch proposal.

    ``content_length=None`` means no Content-Length and no chunked
    framing (empty body).
    """
    headers: list[tuple[str, str]] = [("Host", host)]
    if content_length is not None:
        headers.append(("Content-Length", str(content_length)))
    if upgrade is not None:
        headers.append(("Upgrade", upgrade))
    event = make_request(method="CONNECT", target=target, headers=headers)
    print(
        f"connect_request target={target!r} host={host!r} "
        f"cl={content_length!r} upgrade={upgrade!r}",
        flush=True,
    )
    return event


def upgrade_request(
    *,
    host: str,
    target: str,
    upgrade: str,
    content_length: int = 1,
    method: str = "GET",
) -> Any:
    """Construct an Upgrade switch proposal. *method* is for the non-GET arm."""
    headers: list[tuple[str, str]] = [
        ("Host", host),
        ("Content-Length", str(content_length)),
        ("Upgrade", upgrade),
    ]
    event = make_request(method=method, target=target, headers=headers)
    print(
        f"upgrade_request method={method!r} target={target!r} "
        f"host={host!r} upgrade={upgrade!r} cl={content_length}",
        flush=True,
    )
    return event


def send_proposal_headers(client: Any, server: Any, request: Any) -> Any:
    """Send *request*, align the server, require client still SEND_BODY.

    Failure raises. A client that is already MIGHT_SWITCH_PROTOCOL is
    not returned as a successful header-only proposal.
    """
    encoded = require_send_bytes(send_event(client, request))
    feed_ok(server, encoded)
    pulled = pull_kind(server, "request")
    require_our_state(client, "SEND_BODY")
    might = named_state("MIGHT_SWITCH_PROTOCOL")
    our, _their = connection_side_states(client)
    if our == might:
        raise AssertionError(
            "client entered MIGHT_SWITCH_PROTOCOL before the proposing "
            "request's end-of-message"
        )
    print(
        f"send_proposal_headers encoded_len={len(encoded)} "
        f"pulled={type(pulled).__name__}",
        flush=True,
    )
    return pulled


def _feed_nonempty_send(server: Any, result: CallResult) -> None:
    """Feed send bytes to *server* only when the send produced a non-empty buffer.

    An exception is never treated as "no bytes". An empty buffer is not
    fed (that would be a receive-side close).
    """
    if result.exception is not None:
        raise HarnessError(
            "send raised "
            f"{type(result.exception).__name__}: {result.exception!r}; "
            "cannot treat a failure as no extra bytes"
        )
    value = result.value
    if value is None:
        return
    if type(value) is bytes:
        raw = value
    elif isinstance(value, (bytearray, memoryview)):
        raw = bytes(value)
    else:
        raise HarnessError(
            f"send did not return a byte buffer or none; got {type(value)!r}"
        )
    if raw:
        feed_ok(server, raw)


def finish_proposal_body(client: Any, server: Any, body: bytes) -> None:
    """Send data (if *body* is non-empty) then EOM. Require MIGHT_SWITCH + paused.

    ``body == b""`` sends only end-of-message. Mid-walk failure raises;
    a half-switched pair is never returned as success.
    """
    if body:
        encoded = require_send_bytes(send_event(client, make_data(body)))
        feed_ok(server, encoded)
        print(f"finish_proposal_body data_len={len(body)}", flush=True)
    eom_result = send_event(client, make_eom())
    _feed_nonempty_send(server, eom_result)
    require_our_state(client, "MIGHT_SWITCH_PROTOCOL")
    if body:
        pull_kind(server, "data")
    pull_kind(server, "end-of-message")
    paused = pull_next(server)
    require_paused(paused)
    if event_is_kind(paused.value, "request"):
        raise AssertionError(
            "server pull after proposing EOM was a request, not paused"
        )
    print("finish_proposal_body client MIGHT_SWITCH server paused", flush=True)


def finish_proposing_request(
    client: Any, server: Any, request: Any, body: bytes
) -> Any:
    """Headers then body. Failure raises; never returns a half-switched pair."""
    pulled = send_proposal_headers(client, server, request)
    finish_proposal_body(client, server, body)
    return pulled


def runtime_connect_target() -> str:
    """A CONNECT target that is not the fixed ``example.com:443``."""
    token = runtime_token()
    target = token[:12] + ".test:9443"
    if target == "example.com:443":
        target = token[:10] + ".invalid:8443"
    print(f"runtime_connect_target={target!r}", flush=True)
    return target


def runtime_upgrade_value() -> str:
    """An Upgrade value that is not the fixed ``a, b``."""
    token = runtime_token()
    value = token[:8] + "-proto"
    if value.lower() in {"a, b", "a,b", "websocket"}:
        value = token[:6] + "-alt"
    print(f"runtime_upgrade_value={value!r}", flush=True)
    return value


def runtime_2xx_except_200() -> int:
    """A status in [200, 300) that is not 200. Drawn from the range, not a table."""
    status = 201 + (runtime_int() % 98)
    if status == 200 or status < 200 or status >= 300:
        status = 201 + (runtime_int() % 50)
    if status == 200:
        status = 204
    if not (200 <= status < 300) or status == 200:
        raise HarnessError(
            f"runtime 2xx produced {status}, which is not a non-200 2xx"
        )
    print(f"runtime_2xx_except_200={status}", flush=True)
    return status


def runtime_non_2xx_except_404() -> int:
    """A final non-2xx status that is not 404. Drawn from the range, not a table."""
    status = 400 + (runtime_int() % 200)
    if status == 404:
        status = 400 + ((runtime_int() // 7) % 200)
    if status == 404:
        status = 418
    if 200 <= status < 300:
        status = 503
    if status < 200 or status >= 1000:
        status = 500
    if status == 404 or 200 <= status < 300:
        raise HarnessError(
            f"runtime non-2xx produced {status}, which is 2xx or 404"
        )
    print(f"runtime_non_2xx_except_404={status}", flush=True)
    return status


def fixed_leftover_http10_get() -> bytes:
    """Public leftover ``GET / HTTP/1.0`` with no headers."""
    raw = b"GET / HTTP/1.0\r\n\r\n"
    if not raw.startswith(b"GET / HTTP/1.0"):
        raise HarnessError("public leftover is missing GET / HTTP/1.0")
    if not raw.endswith(b"\r\n\r\n"):
        raise HarnessError(
            "public leftover is missing the terminating blank line; "
            "refusing to return a prefix"
        )
    print(f"fixed_leftover_http10_get len={len(raw)}", flush=True)
    return raw


def fixed_connect_finished() -> tuple[Any, Any]:
    """Public CONNECT example.com:443 CL 1, finished through EOM."""
    client = client_connection()
    server = server_connection()
    request = connect_request(
        target="example.com:443", host="example.com", content_length=1
    )
    finish_proposing_request(client, server, request, b"1")
    print("fixed_connect_finished", flush=True)
    return client, server


def fixed_upgrade_finished() -> tuple[Any, Any]:
    """Public GET / Upgrade a, b CL 1, finished through EOM."""
    client = client_connection()
    server = server_connection()
    request = upgrade_request(
        host="example.com", target="/", upgrade="a, b", content_length=1
    )
    finish_proposing_request(client, server, request, b"1")
    print("fixed_upgrade_finished", flush=True)
    return client, server


def accept_connect(client: Any, server: Any, status: int = 200) -> Any:
    """Server sends a 2xx response; client pulls it; both sides SWITCHED.

    Does not send end-of-message (the connection has left HTTP).
    """
    encoded = require_send_bytes(
        send_event(server, make_response(status, headers=[]))
    )
    feed_ok(client, encoded)
    pulled = pull_kind(client, "response")
    require_both_switched(client)
    require_both_switched(server)
    print(f"accept_connect status={status}", flush=True)
    return pulled


def accept_upgrade(client: Any, server: Any) -> Any:
    """Server sends informational 101; client pulls it; both sides SWITCHED."""
    encoded = require_send_bytes(
        send_event(server, make_informational(101, headers=[]))
    )
    feed_ok(client, encoded)
    pulled = pull_kind(client, "informational")
    require_both_switched(client)
    require_both_switched(server)
    print("accept_upgrade 101", flush=True)
    return pulled


def deny_and_complete(client: Any, server: Any, status: int) -> Any:
    """Server sends a final non-accepting response plus EOM; both sides DONE."""
    encoded = server_send_status(server, status)
    feed_ok(client, encoded)
    pulled = pull_kind(client, "response")
    pull_kind(client, "end-of-message")
    require_not_switched(client)
    require_not_switched(server)
    require_both_done(client)
    require_both_done(server)
    print(f"deny_and_complete status={status}", flush=True)
    return pulled


__all__ = (
    "accept_connect",
    "accept_upgrade",
    "bind_waiting_reports",
    "client_waiting_flag",
    "connect_request",
    "deny_and_complete",
    "finish_proposal_body",
    "finish_proposing_request",
    "http10_expect_request_bytes",
    "http11_expect_request_bytes",
    "fixed_connect_finished",
    "fixed_expect_headers",
    "fixed_leftover_http10_get",
    "fixed_upgrade_finished",
    "require_both_switched",
    "require_not_switched",
    "require_receive_closed",
    "require_receive_open",
    "require_waiting_flags",
    "runtime_2xx_except_200",
    "runtime_connect_target",
    "runtime_non_2xx_except_404",
    "runtime_upgrade_value",
    "send_proposal_headers",
    "they_are_waiting_flag",
    "trailing_data_pair",
    "upgrade_request",
)
