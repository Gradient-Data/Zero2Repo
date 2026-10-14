# feature: F04
"""Observation helpers for connection lifecycle, keep-alive, and pipelining.

Helpers classify send / feed / pull / start-next-cycle outcomes. They
never return a sentinel to mean "the observation could not be
classified". A missing Connection header after a successful parse is
classified as no close token. A trailing-data probe that cannot read
the leftover bytes raises — it never returns empty bytes to mean
"could not look".
"""

from __future__ import annotations

from typing import Any

from _harness import (
    CallResult,
    HarnessError,
    as_pair,
    attr,
    call_method,
    require_value,
)
from F01_helpers import (
    client_connection,
    package,
    request_method,
    request_target,
    require_local_refusal,
    runtime_int,
    runtime_token,
)
from F02_helpers import (
    connection_side_states,
    encoded_first_line,
    encoded_head_and_rest,
    event_is_kind,
    make_eom,
    make_request,
    make_response,
    named_state,
    need_data_token,
    require_send_bytes,
    send_event,
    server_connection,
)
from F03_helpers import (
    feed_ok,
    payload_as_bytes,
    pull_kind,
)

_EVENT_KINDS = (
    "request",
    "informational",
    "response",
    "data",
    "end-of-message",
    "connection-closed",
)


def paused_result() -> Any:
    """Return the package-root paused non-event result. Missing raises."""
    pkg = package()
    try:
        token = getattr(pkg, "PAUSED")
    except AttributeError as exc:
        raise HarnessError("package root has no paused result") from exc
    print(f"paused_result={token!r}", flush=True)
    return token


def _is_need_data_value(value: Any) -> bool:
    token = need_data_token()
    if value is token:
        return True
    try:
        return value == token
    except Exception:
        return False


def _is_paused_value(value: Any) -> bool:
    token = paused_result()
    if value is token:
        return True
    try:
        return value == token
    except Exception:
        return False


def _is_http_event(value: Any) -> bool:
    return any(event_is_kind(value, kind) for kind in _EVENT_KINDS)


def require_paused(result: CallResult) -> Any:
    """Require pull succeeded and returned paused, not an event or need-data.

    A crash is never classified as paused.
    """
    value = require_value(result)
    if _is_http_event(value):
        raise AssertionError(
            f"pull returned an event {type(value)!r}, not paused"
        )
    if _is_need_data_value(value):
        raise AssertionError("pull returned need-data, not paused")
    if not _is_paused_value(value):
        raise AssertionError(
            f"pull returned {type(value)!r} {value!r}, not paused"
        )
    print("require_paused ok", flush=True)
    return value


def start_next_cycle(conn: Any) -> CallResult:
    """Call the public start-next-cycle entry. Failure is not rewritten as success."""
    result = call_method(conn, "start_next_cycle")
    print(
        f"start_next_cycle exc="
        f"{type(result.exception).__name__ if result.exception else None}",
        flush=True,
    )
    return result


def require_both_idle(conn: Any) -> None:
    """Require our-state and their-state are both IDLE. Unreadable states raise."""
    our, their = connection_side_states(conn)
    idle = named_state("IDLE")
    if our != idle or their != idle:
        raise AssertionError(
            f"expected both sides IDLE; our={our!r} their={their!r}"
        )
    print("require_both_idle ok", flush=True)


def require_neither_error(conn: Any) -> None:
    """Require neither side is ERROR. Unreadable states raise."""
    our, their = connection_side_states(conn)
    error = named_state("ERROR")
    if our == error or their == error:
        raise AssertionError(
            f"a side is ERROR; our={our!r} their={their!r}"
        )
    print("require_neither_error ok", flush=True)


def require_local_cycle_refusal(
    result: CallResult,
    conn: Any,
    *,
    our: str | None = None,
    their: str | None = None,
) -> BaseException:
    """Require start-next-cycle failed as a local protocol error.

    Start did not leave both sides IDLE. Neither side is ERROR. When
    *our* or *their* is given, that side must still be the named state
    after the refusal — a start that jumps to IDLE cannot pass. A probe
    crash is never classified as "start did nothing".
    """
    exc = require_local_refusal(result)
    got_our, got_their = connection_side_states(conn)
    idle = named_state("IDLE")
    if got_our == idle and got_their == idle:
        raise AssertionError(
            "start-next-cycle refused but both sides are IDLE"
        )
    require_neither_error(conn)
    if our is not None:
        expected = named_state(our)
        if got_our != expected:
            raise AssertionError(
                f"after refused start our_state is {got_our!r}, expected {our}"
            )
    if their is not None:
        expected = named_state(their)
        if got_their != expected:
            raise AssertionError(
                f"after refused start their_state is {got_their!r}, expected {their}"
            )
    print(
        f"local_cycle_refusal our={got_our!r} their={got_their!r}",
        flush=True,
    )
    return exc


def encoded_status_code(encoded: bytes) -> int:
    """Read the integer status from the encoded status line. Parse failure raises."""
    line = encoded_first_line(encoded)
    parts = line.split()
    if len(parts) < 2:
        raise HarnessError(
            f"status line {line!r} does not contain a status code"
        )
    try:
        status = int(parts[1])
    except ValueError as exc:
        raise HarnessError(
            f"status line {line!r} has a non-integer status {parts[1]!r}"
        ) from exc
    print(f"encoded_status_code={status} line={line!r}", flush=True)
    return status


def connection_has_close_token(encoded: bytes) -> bool:
    """Return whether a parsed header block has a Connection close token.

    Tokens are comma-separated; a token matches when the stripped
    segment equals ``close`` case-insensitively. No Connection header
    after a successful parse is False. Parse failure raises — never
    returns False to mean "could not look".
    """
    head, _rest = encoded_head_and_rest(encoded)
    if b"\r\n" in head:
        lines = head.split(b"\r\n")
    else:
        lines = head.split(b"\n")
    found_close = False
    saw_connection = False
    for line in lines[1:]:
        if b":" not in line:
            continue
        raw_name, raw_value = line.split(b":", 1)
        if raw_name.strip().lower() != b"connection":
            continue
        saw_connection = True
        for piece in raw_value.split(b","):
            token = piece.strip()
            if token.lower() == b"close":
                found_close = True
    print(
        f"connection_has_close_token={found_close} "
        f"saw_connection={saw_connection}",
        flush=True,
    )
    return found_close


def require_close_token(encoded: bytes) -> None:
    """Require the encoded header block contains a close token."""
    if not connection_has_close_token(encoded):
        raise AssertionError(
            "encoded response has no Connection close token"
        )


def require_no_close_token(encoded: bytes) -> None:
    """Require a successful parse with no close token. Parse failure raises."""
    if connection_has_close_token(encoded):
        raise AssertionError(
            "encoded response has a Connection close token"
        )


def trailing_held_bytes(conn: Any) -> bytes:
    """Read leftover bytes from the public trailing-data record.

    Probe failure raises. Empty bytes are returned only when the public
    surface successfully reports an empty leftover.
    """
    raw = attr(conn, "trailing_data")
    try:
        leftover, _closed = as_pair(raw)
    except HarnessError as exc:
        raise HarnessError(
            f"trailing data is not a (bytes, closed) pair: {exc}"
        ) from exc
    if isinstance(leftover, (bytes, bytearray, memoryview)):
        held = bytes(leftover)
        print(f"trailing_held_bytes len={len(held)}", flush=True)
        return held
    raise HarnessError(
        f"trailing data leftover is not bytes: {type(leftover)!r}"
    )


def require_their_state(conn: Any, name: str) -> Any:
    """Require their-state equals the named package-root state."""
    _our, their = connection_side_states(conn)
    expected = named_state(name)
    if their != expected:
        raise AssertionError(
            f"their_state is {their!r}, expected named state {name}"
        )
    print(f"require_their_state {name} ok", flush=True)
    return their


def require_both_done(conn: Any) -> None:
    """Require both sides are DONE. Unreadable states raise."""
    our, their = connection_side_states(conn)
    done = named_state("DONE")
    if our != done or their != done:
        raise AssertionError(
            f"expected both sides DONE; our={our!r} their={their!r}"
        )
    print("require_both_done ok", flush=True)


def require_both_must_close(conn: Any) -> None:
    """Require both sides are MUST_CLOSE. Unreadable states raise."""
    our, their = connection_side_states(conn)
    must_close = named_state("MUST_CLOSE")
    if our != must_close or their != must_close:
        raise AssertionError(
            f"expected both sides MUST_CLOSE; our={our!r} their={their!r}"
        )
    print("require_both_must_close ok", flush=True)


def send_completed_eom(conn: Any) -> bytes:
    """Send end-of-message. Success may be empty or a framing trailer.

    A product exception is never classified as empty bytes.
    """
    result = send_event(conn, make_eom())
    if result.exception is not None:
        raise HarnessError(
            "end-of-message send raised "
            f"{type(result.exception).__name__}: {result.exception!r}"
        )
    value = result.value
    if value is None:
        print("send_completed_eom none", flush=True)
        return b""
    if type(value) is bytes:
        print(f"send_completed_eom len={len(value)}", flush=True)
        return value
    if isinstance(value, (bytearray, memoryview)):
        raw = bytes(value)
        print(f"send_completed_eom len={len(raw)}", flush=True)
        return raw
    raise HarnessError(
        f"end-of-message send did not return bytes or none; got {type(value)!r}"
    )


def require_start_succeeded(result: CallResult, conn: Any) -> None:
    """Require start-next-cycle returned and both sides are IDLE.

    Returning without error is not enough: a no-op that leaves both
    sides DONE is not a successful start.
    """
    if result.exception is not None:
        raise AssertionError(
            "start-next-cycle raised "
            f"{type(result.exception).__name__}: {result.exception!r}"
        )
    our, their = connection_side_states(conn)
    idle = named_state("IDLE")
    done = named_state("DONE")
    if our != idle or their != idle:
        raise AssertionError(
            "start-next-cycle returned without error but sides are not "
            f"both IDLE; our={our!r} their={their!r}"
        )
    if our == done or their == done:
        raise AssertionError(
            "start-next-cycle left a side in DONE; "
            f"our={our!r} their={their!r}"
        )
    print("require_start_succeeded both IDLE", flush=True)


def client_sent_named_get(*, host: str, target: str = "/") -> tuple[Any, bytes]:
    """Client that has sent GET *target* with Host *host* plus end-of-message."""
    client = client_connection()
    encoded = require_send_bytes(
        send_event(
            client,
            make_request(target=target, headers=[("Host", host)]),
        )
    )
    eom = send_completed_eom(client)
    print(
        f"client_sent_named_get host={host!r} target={target!r} "
        f"len={len(encoded) + len(eom)}",
        flush=True,
    )
    return client, encoded + eom


def pull_response_then_eom(conn: Any) -> Any:
    """Pull a response event, then the matching end-of-message (empty body)."""
    response = pull_kind(conn, "response")
    done = pull_kind(conn, "end-of-message")
    print(
        f"pull_response_then_eom response={type(response).__name__} "
        f"eom={type(done).__name__}",
        flush=True,
    )
    return response


def complete_empty_http11_cycle(
    *, host: str, target: str = "/"
) -> tuple[Any, Any, bytes]:
    """Run one empty-body HTTP/1.1 GET/200 on a fresh pair. Both sides DONE.

    Returns ``(client, server, encoded_response)``.
    """
    client, raw = client_sent_named_get(host=host, target=target)
    server = server_connection()
    feed_ok(server, raw)
    pull_kind(server, "request")
    pull_kind(server, "end-of-message")
    resp = require_send_bytes(send_event(server, make_response(200, headers=[])))
    eom = send_completed_eom(server)
    feed_ok(client, resp + eom)
    pull_response_then_eom(client)
    require_both_done(client)
    require_both_done(server)
    print(
        f"complete_empty_http11_cycle host={host!r} target={target!r}",
        flush=True,
    )
    return client, server, resp


def fixed_three_get_block(*, host: bytes = b"a") -> bytes:
    """The fixed three-GET pipelined block for /1 /2 /3."""
    block = (
        b"GET /1 HTTP/1.1\r\nHost: "
        + host
        + b"\r\nContent-Length: 5\r\n\r\n"
        b"12345"
        b"GET /2 HTTP/1.1\r\nHost: "
        + host
        + b"\r\nContent-Length: 5\r\n\r\n"
        b"67890"
        b"GET /3 HTTP/1.1\r\nHost: "
        + host
        + b"\r\n\r\n"
    )
    print(f"fixed_three_get_block host={host!r} len={len(block)}", flush=True)
    return block


def send_final_200(server: Any, *, headers: Any = ()) -> bytes:
    """Send a 200 plus end-of-message on *server*; return concatenated bytes."""
    resp = require_send_bytes(
        send_event(server, make_response(200, headers=list(headers)))
    )
    eom = send_completed_eom(server)
    print(f"send_final_200 resp_len={len(resp)} eom_len={len(eom)}", flush=True)
    return resp + eom


def runtime_close_substring_token() -> str:
    """A Connection segment containing the letters close that is not the close token.

    The segment is not a whole-segment ``close`` and is not ``enclosed``
    or ``closed``. Generated in-process.
    """
    token = runtime_token() + "close"
    lowered = token.lower()
    if lowered in {"close", "enclosed", "closed"} or b"," in token.encode("ascii"):
        token = "fore" + runtime_token() + "close"
        lowered = token.lower()
    if lowered in {"close", "enclosed", "closed"}:
        token = "xclose" + runtime_token()
    print(f"runtime_close_substring_token={token!r}", flush=True)
    return token


def runtime_host() -> str:
    """A Host that is not the fixture ``a``."""
    host = runtime_token() + ".test"
    print(f"runtime_host={host!r}", flush=True)
    return host


def runtime_target() -> str:
    """A request target that is not a fixture path."""
    token = runtime_token()
    target = "/" + token[:8]
    if target in {"/", "/foo", "/1", "/2", "/3", "/4"}:
        target = "/r" + token[:6]
    print(f"runtime_target={target!r}", flush=True)
    return target


def runtime_informational_status() -> int:
    """A 1xx status in [100, 200) that is not 100, 101, 102, or 199."""
    status = 103 + (runtime_int() % 90)
    if status in (100, 101, 102, 199):
        status = 150
    print(f"runtime_informational_status={status}", flush=True)
    return status


def runtime_final_not_408() -> int:
    """A final status that is not the fixture 408."""
    status = 400 + (runtime_int() % 80)
    if status == 408:
        status = 418
    if status < 200 or status >= 1000:
        status = 503
    print(f"runtime_final_not_408={status}", flush=True)
    return status


def runtime_final_not_204_or_200() -> int:
    """A final status that is neither 204 nor 200."""
    status = 201 + (runtime_int() % 40)
    if status in (200, 204):
        status = 404
    if status < 200:
        status = 201
    print(f"runtime_final_not_204_or_200={status}", flush=True)
    return status


def second_request_method() -> str:
    """A request method that is neither GET nor DELETE."""
    method = "PUT" if runtime_int() % 2 else "POST"
    print(f"second_request_method={method}", flush=True)
    return method


def client_send_empty(
    client: Any,
    *,
    method: str = "GET",
    target: str = "/",
    host: str = "a",
    extra_headers: list[tuple[str, str]] | None = None,
) -> bytes:
    """Send one empty-body request plus end-of-message; return both encodings."""
    headers: list[tuple[str, str]] = [("Host", host)]
    if extra_headers:
        headers.extend(extra_headers)
    encoded = require_send_bytes(
        send_event(
            client,
            make_request(method=method, target=target, headers=headers),
        )
    )
    eom = send_completed_eom(client)
    print(
        f"client_send_empty method={method} target={target} host={host} "
        f"len={len(encoded) + len(eom)}",
        flush=True,
    )
    return encoded + eom


def pull_empty_request(server: Any, raw: bytes) -> Any:
    """Feed *raw* and pull a request then end-of-message."""
    feed_ok(server, raw)
    pulled = pull_kind(server, "request")
    pull_kind(server, "end-of-message")
    print(
        f"pull_empty_request method={request_method(pulled)!r} "
        f"target={request_target(pulled)!r}",
        flush=True,
    )
    return pulled


def server_send_status(
    server: Any, status: int, headers: list[tuple[str, str]] | None = None
) -> bytes:
    """Send a final response plus end-of-message; return concatenated bytes."""
    encoded = require_send_bytes(
        send_event(server, make_response(status, headers=headers or []))
    )
    eom = send_completed_eom(server)
    print(
        f"server_send_status status={status} len={len(encoded) + len(eom)}",
        flush=True,
    )
    return encoded + eom


def bodied_get_pair() -> tuple[Any, Any, bytes]:
    """Client/server pair after a Content-Length 5 GET has been sent and pulled."""
    client = client_connection()
    server = server_connection()
    require_both_idle(client)
    require_both_idle(server)
    req = require_send_bytes(
        send_event(
            client,
            make_request(headers=[("Host", "a"), ("Content-Length", "5")]),
        )
    )
    require_our_state_send_body = named_state("SEND_BODY")
    our, their = connection_side_states(client)
    if our != require_our_state_send_body:
        raise AssertionError(f"client our_state is {our!r}, expected SEND_BODY")
    if their != named_state("SEND_RESPONSE"):
        raise AssertionError(
            f"client their_state is {their!r}, expected SEND_RESPONSE"
        )
    feed_ok(server, req)
    pulled = pull_kind(server, "request")
    if request_method(pulled) != b"GET":
        raise AssertionError(
            f"bodied GET pulled method {request_method(pulled)!r}"
        )
    s_our, s_their = connection_side_states(server)
    if s_our != named_state("SEND_RESPONSE"):
        raise AssertionError(f"server our_state is {s_our!r}")
    if s_their != named_state("SEND_BODY"):
        raise AssertionError(f"server their_state is {s_their!r}")
    print("bodied_get_pair ready", flush=True)
    return client, server, req


def feed_public_three_gets(server: Any) -> None:
    """Feed the fixed /1 /2 /3 block and pull the /1 request, data, EOM."""
    feed_ok(server, fixed_three_get_block())
    first = pull_kind(server, "request")
    if request_target(first) != b"/1":
        raise AssertionError(
            f"first pipelined target is {request_target(first)!r}, not /1"
        )
    data = pull_kind(server, "data")
    if payload_as_bytes(data) != b"12345":
        raise AssertionError(
            f"first pipelined body is {payload_as_bytes(data)!r}, not 12345"
        )
    pull_kind(server, "end-of-message")
    print("feed_public_three_gets pulled /1", flush=True)


__all__ = (
    "bodied_get_pair",
    "client_send_empty",
    "client_sent_named_get",
    "complete_empty_http11_cycle",
    "connection_has_close_token",
    "encoded_status_code",
    "feed_public_three_gets",
    "paused_result",
    "fixed_three_get_block",
    "pull_empty_request",
    "pull_response_then_eom",
    "require_both_done",
    "require_both_idle",
    "require_both_must_close",
    "require_close_token",
    "require_local_cycle_refusal",
    "require_neither_error",
    "require_no_close_token",
    "require_paused",
    "require_start_succeeded",
    "require_their_state",
    "runtime_close_substring_token",
    "runtime_final_not_204_or_200",
    "runtime_final_not_408",
    "runtime_host",
    "runtime_informational_status",
    "runtime_target",
    "second_request_method",
    "send_completed_eom",
    "send_final_200",
    "server_send_status",
    "start_next_cycle",
    "trailing_held_bytes",
)
