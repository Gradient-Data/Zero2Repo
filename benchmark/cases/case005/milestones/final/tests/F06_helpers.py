# feature: F06
"""Observation helpers for half-duplex connection shutdown.

Helpers classify send / feed / pull of a connection-closed event. They
never return a sentinel to mean the observation could not be
classified. A failed send is never rewritten as "no bytes". A failed
or need-data pull is never rewritten as connection-closed. A host or
target that cannot form a complete GET raises; a truncated prefix is
never returned as if it were a complete request.
"""

from __future__ import annotations

from typing import Any

from _harness import CallResult, HarnessError
from F01_helpers import construct, require_event, runtime_int, runtime_token
from F02_helpers import (
    connection_pair_states,
    event_is_kind,
    make_data,
    make_eom,
    make_request,
    named_state,
    pull_next,
    require_no_extra_bytes,
    require_pulled_event,
    send_event,
)
from F04_helpers import runtime_host, runtime_target


def make_connection_closed() -> Any:
    """Construct a connection-closed event. Construction failure raises."""
    event = require_event(construct("connection-closed"))
    print(
        f"make_connection_closed type={type(event).__name__}",
        flush=True,
    )
    return event


def send_connection_closed(conn: Any) -> CallResult:
    """Send connection-closed. Success produces no bytes.

    A product exception is never classified as "no bytes".
    """
    result = send_event(conn, make_connection_closed())
    require_no_extra_bytes(result)
    print("send_connection_closed no bytes", flush=True)
    return result


def require_connection_closed_event(value: Any) -> Any:
    """Require *value* is a connection-closed event, not need-data."""
    if not event_is_kind(value, "connection-closed"):
        raise AssertionError(
            "expected a connection-closed event, got "
            f"{type(value)!r} {value!r}"
        )
    print(
        f"require_connection_closed_event type={type(value).__name__}",
        flush=True,
    )
    return value


def pull_connection_closed(conn: Any) -> Any:
    """Pull once and require a connection-closed event.

    A crash or need-data is never classified as connection-closed.
    """
    event = require_pulled_event(pull_next(conn))
    return require_connection_closed_event(event)


def require_client_server_states(
    conn: Any, client_name: str, server_name: str
) -> tuple[Any, Any]:
    """Require the pair of states matches the named client and server states.

    Unreadable pair states raise. A mismatch is an assertion failure.
    """
    client_side, server_side = connection_pair_states(conn)
    want_client = named_state(client_name)
    want_server = named_state(server_name)
    if client_side != want_client or server_side != want_server:
        raise AssertionError(
            f"pair states client={client_side!r} server={server_side!r}, "
            f"expected client {client_name} server {server_name}"
        )
    print(
        f"require_client_server_states client={client_name} "
        f"server={server_name}",
        flush=True,
    )
    return client_side, server_side


def fixed_two_bodied_gets_then_empty() -> bytes:
    """Public pipelined GET /1 and /2 with five-byte bodies.

    Does not include a trailing empty chunk; the test feeds that
    separately.
    """
    block = (
        b"GET /1 HTTP/1.1\r\nHost: a\r\nContent-Length: 5\r\n\r\n"
        b"12345"
        b"GET /2 HTTP/1.1\r\nHost: a\r\nContent-Length: 5\r\n\r\n"
        b"67890"
    )
    print(f"fixed_two_bodied_gets_then_empty len={len(block)}", flush=True)
    return block


def runtime_two_bodied_gets() -> tuple[bytes, bytes, bytes, bytes, bytes]:
    """Two bodied GETs whose targets, Host, and bodies are not the fixtures.

    Returns ``(block, target1, target2, body1, body2)``. Content-Length
    matches each body. Probe failure raises.
    """
    host = runtime_host()
    target1 = runtime_target()
    target2 = runtime_target()
    if target2 == target1:
        target2 = target2 + "z"
    n1 = 3 + (runtime_int() % 4)
    if n1 == 5:
        n1 = 4
    n2 = 4 + ((runtime_int() // 3) % 4)
    if n2 == 5:
        n2 = 6
    token = runtime_token().encode("ascii")
    if not token:
        raise HarnessError("runtime token was empty; cannot build bodies")
    body1 = (token * (n1 + 2))[:n1]
    body2 = (token[::-1] * (n2 + 2))[:n2]
    if body1 == b"12345":
        body1 = b"abcd"[:n1].ljust(n1, b"x")
    if body2 == b"67890":
        body2 = b"wxyz"[:n2].ljust(n2, b"y")
    try:
        host_b = host.encode("ascii")
        t1_b = target1.encode("ascii")
        t2_b = target2.encode("ascii")
    except UnicodeEncodeError as exc:
        raise HarnessError(
            f"cannot encode runtime pipelined GET as ASCII: {exc}"
        ) from exc
    cl1 = str(len(body1)).encode("ascii")
    cl2 = str(len(body2)).encode("ascii")
    block = (
        b"GET "
        + t1_b
        + b" HTTP/1.1\r\nHost: "
        + host_b
        + b"\r\nContent-Length: "
        + cl1
        + b"\r\n\r\n"
        + body1
        + b"GET "
        + t2_b
        + b" HTTP/1.1\r\nHost: "
        + host_b
        + b"\r\nContent-Length: "
        + cl2
        + b"\r\n\r\n"
        + body2
    )
    print(
        f"runtime_two_bodied_gets t1={t1_b!r} t2={t2_b!r} "
        f"n1={len(body1)} n2={len(body2)}",
        flush=True,
    )
    return block, t1_b, t2_b, body1, body2


def complete_new_get_bytes(*, host: str, target: str) -> bytes:
    """A complete GET: request line, Host, and terminating blank line.

    A host or target that cannot form that complete request raises. A
    truncated prefix is never returned.
    """
    if not host or not target:
        raise HarnessError(
            "complete GET needs a non-empty host and target; "
            f"got host={host!r} target={target!r}"
        )
    if any(ch in host for ch in "\r\n") or any(ch in target for ch in "\r\n"):
        raise HarnessError(
            "host or target contains a line break; cannot form a complete GET"
        )
    try:
        host_b = host.encode("ascii")
        target_b = target.encode("ascii")
    except UnicodeEncodeError as exc:
        raise HarnessError(
            f"cannot encode complete GET host/target as ASCII: {exc}"
        ) from exc
    raw = b"GET " + target_b + b" HTTP/1.1\r\nHost: " + host_b + b"\r\n\r\n"
    if not raw.startswith(b"GET "):
        raise HarnessError("complete GET is missing the request line")
    if b"Host: " not in raw:
        raise HarnessError("complete GET is missing the Host header")
    if not raw.endswith(b"\r\n\r\n"):
        raise HarnessError(
            "complete GET is missing the terminating blank line; "
            "refusing to return a prefix"
        )
    head, sep, rest = raw.partition(b"\r\n\r\n")
    if not sep or rest:
        raise HarnessError(
            "complete GET terminator is missing or trailed by extra bytes"
        )
    if b"\r\n" not in head:
        raise HarnessError("complete GET has no header line after the request line")
    print(
        f"complete_new_get_bytes host={host!r} target={target!r} "
        f"len={len(raw)}",
        flush=True,
    )
    return raw


def incomplete_get_then_rest(*, host: str, target: str) -> tuple[bytes, bytes]:
    """Split a complete GET into a non-complete prefix and the remainder.

    The prefix is the request line plus its line ending. It is not a
    complete request: a pull after only that prefix must be need-data,
    not a request event. The rest completes the same GET. A split
    that accidentally leaves a complete request in the prefix, or
    that puts the target into the rest, raises instead of returning a
    hollow pair.
    """
    raw = complete_new_get_bytes(host=host, target=target)
    sep = raw.find(b"\r\n")
    if sep < 0:
        raise HarnessError("complete GET has no request-line ending")
    prefix = raw[: sep + 2]
    rest = raw[sep + 2 :]
    if not prefix.startswith(b"GET ") or not prefix.endswith(b"\r\n"):
        raise HarnessError("prefix is not a GET request line")
    if prefix.endswith(b"\r\n\r\n") or b"\r\n\r\n" in prefix:
        raise HarnessError(
            "prefix is already a complete GET; refusing to return it "
            "as an incomplete fragment"
        )
    if not rest or not rest.endswith(b"\r\n\r\n"):
        raise HarnessError(
            "rest does not complete the GET; refusing a truncated split"
        )
    try:
        target_b = target.encode("ascii")
    except UnicodeEncodeError as exc:
        raise HarnessError(
            f"cannot encode incomplete-GET target as ASCII: {exc}"
        ) from exc
    if target_b not in prefix:
        raise HarnessError("prefix dropped the request target")
    if target_b in rest:
        raise HarnessError(
            "target leaked into the rest fragment; a later pull of "
            "that target would not prove the prefix was retained"
        )
    print(
        f"incomplete_get_then_rest target={target!r} "
        f"prefix_len={len(prefix)} rest_len={len(rest)}",
        flush=True,
    )
    return prefix, rest


def runtime_finished_bodied_request() -> tuple[Any, Any, Any, bytes]:
    """A finished Content-Length request that is not the fixed ten-byte GET.

    Returns ``(request, data, end-of-message, payload)``. Length is not
    10. Method, target, Host, and payload are process-local.
    """
    n = 4 + (runtime_int() % 5)
    if n == 10:
        n = 7
    method = "POST" if runtime_int() % 2 else "PUT"
    target = runtime_target()
    host = runtime_host()
    token = runtime_token().encode("ascii")
    if not token:
        raise HarnessError("runtime token was empty; cannot build a body")
    payload = (token * (n + 2))[:n]
    if len(payload) == 10:
        payload = payload[:7]
        n = 7
    request = make_request(
        method=method,
        target=target,
        headers=[("Host", host), ("Content-Length", str(n))],
    )
    data = make_data(payload)
    eom = make_eom()
    print(
        f"runtime_finished_bodied_request method={method} "
        f"target={target!r} n={n}",
        flush=True,
    )
    return request, data, eom, payload


__all__ = (
    "complete_new_get_bytes",
    "incomplete_get_then_rest",
    "make_connection_closed",
    "fixed_two_bodied_gets_then_empty",
    "pull_connection_closed",
    "require_client_server_states",
    "require_connection_closed_event",
    "runtime_finished_bodied_request",
    "runtime_two_bodied_gets",
    "send_connection_closed",
)
