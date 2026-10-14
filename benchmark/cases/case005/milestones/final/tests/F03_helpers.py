# feature: F03
"""Observation helpers for message-body framing (FP-03).

Helpers classify send / passthrough / feed / pull outcomes. They never
return a sentinel to mean "the observation could not be classified".
A missing framing header is a successfully parsed header block that
does not contain that name — parse failure raises. A chunk mark that
cannot be read as four distinguishable roles raises; it is never
rewritten as "neither". A discarded extension is a successful public
surface that does not carry the token — a probe crash is not absence.
"""

from __future__ import annotations

from typing import Any, Hashable

from _harness import (
    CallResult,
    HarnessError,
    as_bool,
    as_sequence,
    call_method,
)
from F01_helpers import (
    construct,
    data_payload,
    payload_letters,
    require_event,
    runtime_int,
    runtime_token,
)
from F02_helpers import (
    client_connection,
    connection_side_states,
    event_is_kind,
    feed_bytes,
    make_eom,
    make_request,
    named_state,
    pull_next,
    require_no_extra_bytes,
    require_pulled_event,
    require_remote_refusal,
    require_send_bytes,
    send_event,
    server_connection,
    wire_header_names,
)

_ROLE_BOTH = "both"
_ROLE_START = "start"
_ROLE_NEITHER = "neither"
_ROLE_END = "end"


def feed_ok(conn: Any, data: Any) -> None:
    """Store bytes on *conn*. A product exception is not "feed did nothing"."""
    result = feed_bytes(conn, data)
    if result.exception is not None:
        raise HarnessError(
            f"feed raised {type(result.exception).__name__}: {result.exception!r}"
        )


def pull_kind(conn: Any, kind: str) -> Any:
    """Pull one event and require it is the named kind."""
    event = require_pulled_event(pull_next(conn))
    if not event_is_kind(event, kind):
        raise AssertionError(
            f"expected {kind} event, got {type(event)!r}"
        )
    print(f"pull_kind {kind} type={type(event).__name__}", flush=True)
    return event


def require_our_state(conn: Any, name: str) -> Any:
    """Require our-state equals the named package-root state."""
    our, _their = connection_side_states(conn)
    expected = named_state(name)
    if our != expected:
        raise AssertionError(
            f"our_state is {our!r}, expected named state {name}"
        )
    print(f"require_our_state {name} ok", flush=True)
    return our


def make_eom_with(headers: Any) -> Any:
    """Construct an end-of-message that carries trailing headers."""
    return require_event(construct("end-of-message", headers=list(headers)))


def passthrough_send(conn: Any, event: Any) -> CallResult:
    """Passthrough-send *event* on *conn*. Failure is not an empty sequence."""
    result = call_method(conn, "send_with_data_passthrough", event)
    print(
        f"passthrough_send exc="
        f"{type(result.exception).__name__ if result.exception else None} "
        f"value_type={type(result.value).__name__ if result.exception is None else None}",
        flush=True,
    )
    return result


def require_passthrough_pieces(result: CallResult) -> tuple[Any, ...]:
    """Require passthrough succeeded and returned a sequence of pieces.

    An exception is never classified as an empty piece list. A single
    concatenated byte string is not a piece sequence.
    """
    if result.exception is not None:
        raise HarnessError(
            "passthrough send raised "
            f"{type(result.exception).__name__}: {result.exception!r}; "
            "there is no piece sequence to observe"
        )
    value = result.value
    if value is None:
        raise HarnessError(
            "passthrough send returned none; there is no piece sequence"
        )
    try:
        pieces = as_sequence(value)
    except HarnessError as exc:
        raise HarnessError(
            "passthrough send did not return a sequence of pieces: "
            f"{exc}"
        ) from exc
    print(f"require_passthrough_pieces n={len(pieces)}", flush=True)
    return pieces


def length_placeholder(n: int) -> Any:
    """A non-byte object whose length is *n*."""

    class _LengthPlaceholder:
        def __init__(self, length: int) -> None:
            self._length = length

        def __len__(self) -> int:
            return self._length

        def __repr__(self) -> str:
            return f"LengthPlaceholder({self._length})"

    obj = _LengthPlaceholder(n)
    print(f"length_placeholder n={n} id={id(obj)}", flush=True)
    return obj


def payload_as_bytes(event: Any) -> bytes:
    """Data-event payload as bytes. Unreadable content raises."""
    raw = data_payload(event)
    if isinstance(raw, (bytes, bytearray)):
        out = bytes(raw)
        print(f"payload_as_bytes {out!r}", flush=True)
        return out
    if isinstance(raw, str):
        try:
            out = raw.encode("ascii")
        except UnicodeEncodeError as exc:
            raise AssertionError(
                f"payload text {raw!r} is not ASCII bytes"
            ) from exc
        print(f"payload_as_bytes from text {out!r}", flush=True)
        return out
    raise AssertionError(
        f"payload is not recoverable bytes: {type(raw)!r}"
    )


def wire_has_header(encoded: bytes, name: bytes) -> bool:
    """Return whether *name* is present in a successfully parsed header block.

    Parse failure raises — never returns False to mean "could not look".
    """
    names = wire_header_names(encoded)
    want = name.lower()
    present = any(n.lower() == want for n in names)
    print(f"wire_has_header {name!r} present={present}", flush=True)
    return present


def require_no_wire_header(encoded: bytes, name: bytes) -> None:
    """Require a parsed header block that does not contain *name*."""
    if wire_has_header(encoded, name):
        raise AssertionError(
            f"encoded header block has {name!r}; it must be absent"
        )


def require_hex_size_then_payload(encoded: bytes, payload: bytes) -> None:
    """Require *encoded* is not the raw payload and holds hex(len) then payload.

    Hex digits are matched case-insensitively. Line-ending decoration
    is not pinned.
    """
    if not isinstance(encoded, (bytes, bytearray)):
        raise HarnessError(
            f"require_hex_size_then_payload expected bytes; got {type(encoded)!r}"
        )
    raw = bytes(encoded)
    if raw == payload:
        raise AssertionError(
            "chunked data encoded as the raw payload with no hex size"
        )
    hex_digits = format(len(payload), "x").encode("ascii")
    lowered = raw.lower()
    idx = lowered.find(hex_digits)
    if idx < 0:
        raise AssertionError(
            f"encoded {raw!r} has no case-insensitive hex size {hex_digits!r}"
        )
    after = raw[idx + len(hex_digits) :]
    if payload not in after:
        raise AssertionError(
            f"payload {payload!r} does not follow hex size in {raw!r}"
        )
    print(
        f"hex_size_then_payload hex={hex_digits!r} payload_len={len(payload)}",
        flush=True,
    )


_HEX_DIGITS = b"0123456789abcdefABCDEF"


def require_zero_size_final_chunk(encoded: bytes) -> None:
    """Require *encoded* is the zero-size final chunk, not an empty send.

    Hex size spelling and line-ending decoration are not pinned. A
    later peer pull of end-of-message is not this check.
    """
    if not isinstance(encoded, (bytes, bytearray)):
        raise HarnessError(
            f"require_zero_size_final_chunk expected bytes; got {type(encoded)!r}"
        )
    raw = bytes(encoded)
    if raw == b"":
        raise AssertionError(
            "end-of-message encoded as empty; it must be the zero-size final chunk"
        )
    i = 0
    while i < len(raw) and raw[i] in b" \t":
        i += 1
    start = i
    while i < len(raw) and raw[i] in _HEX_DIGITS:
        i += 1
    if start == i:
        raise AssertionError(
            f"EOM encoding {raw!r} has no hexadecimal chunk size"
        )
    size_token = raw[start:i]
    if int(size_token, 16) != 0:
        raise AssertionError(
            f"EOM encoding {raw!r} has size {size_token!r}, not a zero-size chunk"
        )
    while i < len(raw) and raw[i] in b" \t":
        i += 1
    if i < len(raw) and raw[i] == ord(";"):
        while i < len(raw) and raw[i] not in b"\r\n":
            i += 1
    if i >= len(raw):
        raise AssertionError(
            f"EOM encoding {raw!r} has a zero size but is not a chunk "
            "(no size-line ending)"
        )
    if raw[i] == 13:
        i += 1
        if i < len(raw) and raw[i] == 10:
            i += 1
    elif raw[i] == 10:
        i += 1
    else:
        raise AssertionError(
            f"EOM encoding {raw!r} has a zero size but is not a chunk "
            "(no size-line ending)"
        )
    rest = raw[i:]
    rest_body = rest.replace(b"\r", b"").replace(b"\n", b"")
    if rest_body:
        raise AssertionError(
            f"EOM encoding {raw!r} has payload or trailers after the "
            "zero-size chunk"
        )
    print(
        f"zero_size_final_chunk size={size_token!r} rest={rest!r}",
        flush=True,
    )


def require_trailer_after_zero_chunk(
    encoded: bytes, name: bytes, value: bytes
) -> None:
    """Require trailer name/value after a zero-size chunk and before a blank line.

    Does not pin a particular hex-zero spelling or line-ending pair.
    """
    if not isinstance(encoded, (bytes, bytearray)):
        raise HarnessError(
            f"require_trailer_after_zero_chunk expected bytes; got {type(encoded)!r}"
        )
    raw = bytes(encoded)
    lowered = raw.lower()
    zero_at = None
    for token in (b"0",):
        found = lowered.find(token)
        if found >= 0:
            zero_at = found
            break
    if zero_at is None:
        raise AssertionError(
            f"EOM encoding {raw!r} has no zero-size chunk before trailers"
        )
    after_zero = raw[zero_at:]
    after_lower = after_zero.lower()
    name_l = name.lower()
    name_at = after_lower.find(name_l)
    if name_at < 0:
        raise AssertionError(
            f"trailer name {name!r} is not after a zero-size chunk in {raw!r}"
        )
    rest = after_zero[name_at:]
    if value not in rest and value.lower() not in rest.lower():
        raise AssertionError(
            f"trailer value {value!r} is not after the zero-size chunk in {raw!r}"
        )
    value_at = rest.lower().find(value.lower())
    after_value = rest[value_at + len(value) :]
    if b"\r\n\r\n" not in after_value and b"\n\n" not in after_value:
        raise AssertionError(
            f"no final blank line after trailer in {raw!r}"
        )
    print(
        f"trailer_after_zero_chunk name={name!r} value={value!r}",
        flush=True,
    )


def _public_names(event: Any) -> list[str]:
    if event is None:
        raise HarnessError("cannot read public attributes of None")
    try:
        names = dir(event)
    except Exception as exc:
        raise HarnessError(
            f"cannot list public attributes of {type(event).__name__}: {exc}"
        ) from exc
    return [name for name in names if not name.startswith("_")]


def _public_value(event: Any, name: str) -> Any:
    try:
        return getattr(event, name)
    except Exception as exc:
        raise HarnessError(
            f"cannot read public attribute {name!r} on {type(event).__name__}: {exc}"
        ) from exc


def chunk_mark(event: Any) -> Hashable:
    """Return ``(chunk_start, chunk_end)`` of a pulled data event.

    The Interface Contract states both fields, each exactly ``bool``.
    A missing field or a non-bool value raises — never rewritten as
    "neither".
    """
    if event is None:
        raise HarnessError("cannot read a chunk mark from None")
    marks = []
    for name in ("chunk_start", "chunk_end"):
        value = _public_value(event, name)
        if type(value) is not bool:
            raise HarnessError(
                f"{type(event).__name__}.{name} is not a bool: {value!r}"
            )
        marks.append(value)
    mark: Hashable = (marks[0], marks[1])
    print(f"chunk_mark {mark!r}", flush=True)
    return mark


_STATED_ROLE_MARKS: dict[str, Hashable] = {
    _ROLE_BOTH: (True, True),
    _ROLE_START: (True, False),
    _ROLE_NEITHER: (False, False),
    _ROLE_END: (False, True),
}


def _feed_chunked_post(server: Any) -> None:
    feed_ok(
        server,
        b"POST / HTTP/1.1\r\n"
        b"Host: example.com\r\n"
        b"Transfer-Encoding: chunked\r\n"
        b"\r\n",
    )
    pulled = pull_kind(server, "request")
    print(f"chunked POST pulled {type(pulled).__name__}", flush=True)


def fixed_hello_role_marks() -> dict[str, Hashable]:
    """Calibrate the four chunk-role marks from the fixed hello walks.

    Raises if the four situations are not four distinct public marks.
    """
    whole = server_connection()
    _feed_chunked_post(whole)
    feed_ok(whole, b"5\r\nhello\r\n")
    both_event = pull_kind(whole, "data")
    if payload_letters(data_payload(both_event)) != "hello":
        raise AssertionError(
            f"whole hello payload is {data_payload(both_event)!r}, not hello"
        )
    both_mark = chunk_mark(both_event)

    split = server_connection()
    _feed_chunked_post(split)
    feed_ok(split, b"5\r\nhel")
    start_event = pull_kind(split, "data")
    feed_ok(split, b"l")
    neither_event = pull_kind(split, "data")
    feed_ok(split, b"o\r\n")
    end_event = pull_kind(split, "data")
    recovered = (
        payload_letters(data_payload(start_event))
        + payload_letters(data_payload(neither_event))
        + payload_letters(data_payload(end_event))
    )
    if recovered != "hello":
        raise AssertionError(f"split hello recovered {recovered!r}, not hello")
    start_mark = chunk_mark(start_event)
    neither_mark = chunk_mark(neither_event)
    end_mark = chunk_mark(end_event)
    roles = {
        _ROLE_BOTH: both_mark,
        _ROLE_START: start_mark,
        _ROLE_NEITHER: neither_mark,
        _ROLE_END: end_mark,
    }
    if roles != _STATED_ROLE_MARKS:
        raise AssertionError(
            "hello walks did not produce the stated chunk marks: "
            f"got {roles!r}, expected {_STATED_ROLE_MARKS!r}"
        )
    print(f"fixed_hello_role_marks {roles!r}", flush=True)
    return roles


def chunk_role(event: Any, roles: dict[str, Hashable] | None = None) -> str:
    """Map a pulled data event to start / end / both / neither.

    *roles* is the four-mark table from :func:`fixed_hello_role_marks`.
    An unknown mark raises — it is never rewritten as neither.
    """
    table = roles if roles is not None else fixed_hello_role_marks()
    mark = chunk_mark(event)
    for role, known in table.items():
        if mark == known:
            print(f"chunk_role {role}", flush=True)
            return role
    raise HarnessError(
        f"chunk mark {mark!r} is not one of the four calibrated roles {table!r}"
    )


def public_value_blobs(event: Any) -> list[bytes]:
    """Byte views of every public field value. Probe failure raises."""
    blobs: list[bytes] = []
    for name in _public_names(event):
        value = _public_value(event, name)
        if callable(value):
            continue
        if isinstance(value, (bytes, bytearray)):
            blobs.append(bytes(value))
            continue
        if isinstance(value, str):
            blobs.append(value.encode("utf-8", errors="surrogateescape"))
            continue
        if type(value) is bool or type(value) is int:
            blobs.append(repr(value).encode("ascii"))
            continue
        try:
            blobs.append(repr(value).encode("utf-8", errors="surrogateescape"))
        except Exception as exc:
            raise HarnessError(
                f"cannot view public field {name!r} as bytes: {exc}"
            ) from exc
    print(f"public_value_blobs n={len(blobs)}", flush=True)
    return blobs


def require_token_absent_from_public(event: Any, token: bytes) -> None:
    """Require *token* is not carried on the public surface of *event*.

    A failed probe raises. Absence is only a successful scan that does
    not contain the token.
    """
    if not token:
        raise HarnessError("extension token is empty; cannot test discard")
    blobs = public_value_blobs(event)
    if not blobs:
        raise HarnessError(
            "data event public surface produced no field values to scan"
        )
    needle = token.lower()
    for blob in blobs:
        if needle in blob.lower():
            raise AssertionError(
                f"public surface still carries extension token {token!r} "
                f"inside {blob!r}"
            )
    print(f"extension token {token!r} absent from public surface", flush=True)


def substitute_placeholder(
    pieces: tuple[Any, ...], placeholder: Any, replacement: bytes
) -> bytes:
    """Join passthrough pieces, replacing *placeholder* by identity."""
    out: list[bytes] = []
    found = False
    for item in pieces:
        if item is placeholder:
            out.append(replacement)
            found = True
            continue
        if isinstance(item, (bytes, bytearray, memoryview)):
            out.append(bytes(item))
            continue
        raise HarnessError(
            "passthrough piece is neither the placeholder nor bytes: "
            f"{type(item)!r}"
        )
    if not found:
        raise AssertionError(
            "placeholder object is not in the passthrough sequence"
        )
    joined = b"".join(out)
    print(f"substitute_placeholder joined_len={len(joined)}", flush=True)
    return joined


def unframed_get_round_trip(target: str, host: str) -> Any:
    """Send GET *target* with Host *host* and no framing headers, then EOM.

    The matching end-of-message encodes with no extra body bytes. A new
    server that is fed only those bytes pulls the request and then, with
    no further feed, end-of-message — not data. Returns that request.
    """
    client = client_connection()
    encoded = require_send_bytes(
        send_event(
            client,
            make_request(target=target, headers=[("Host", host)]),
        )
    )
    eom = require_no_extra_bytes(send_event(client, make_eom()))
    server = server_connection()
    feed_ok(server, encoded + eom)
    pulled = pull_kind(server, "request")
    immediate = require_pulled_event(pull_next(server))
    print(
        f"unframed_get_round_trip target={target!r} host={host!r} "
        f"immediate={type(immediate).__name__}",
        flush=True,
    )
    if not event_is_kind(immediate, "end-of-message"):
        raise AssertionError(
            f"unframed GET {target!r} Host {host!r}: after the request, "
            f"expected end-of-message, got {type(immediate)!r}"
        )
    if event_is_kind(immediate, "data"):
        raise AssertionError(
            f"unframed GET {target!r} Host {host!r}: pulled a data event "
            "instead of an empty body"
        )
    return pulled


def client_sent_empty_get() -> tuple[Any, bytes]:
    """Client that has sent GET / Host example.com plus end-of-message."""
    client = client_connection()
    encoded = require_send_bytes(
        send_event(client, make_request(headers=[("Host", "example.com")]))
    )
    eom = require_no_extra_bytes(send_event(client, make_eom()))
    print(f"client_sent_empty_get request_len={len(encoded)} eom={eom!r}", flush=True)
    return client, encoded + eom


def server_after_empty_get(*, version: bytes = b"1.1") -> tuple[Any, Any]:
    """Server that has pulled an empty-body GET for / with Host example.com."""
    server = server_connection()
    if version == b"1.1":
        raw = (
            b"GET / HTTP/1.1\r\n"
            b"Host: example.com\r\n"
            b"\r\n"
        )
    elif version == b"1.0":
        raw = (
            b"GET / HTTP/1.0\r\n"
            b"Host: example.com\r\n"
            b"\r\n"
        )
    else:
        raise HarnessError(f"unsupported request version {version!r}")
    feed_ok(server, raw)
    request = pull_kind(server, "request")
    pull_kind(server, "end-of-message")
    print(f"server_after_empty_get version={version!r}", flush=True)
    return server, request


def server_after_empty_head(*, version: bytes = b"1.1") -> tuple[Any, Any]:
    """Server that has pulled an empty-body HEAD for / with Host example.com."""
    server = server_connection()
    raw = (
        b"HEAD / HTTP/" + version + b"\r\n"
        b"Host: example.com\r\n"
        b"\r\n"
    )
    feed_ok(server, raw)
    request = pull_kind(server, "request")
    pull_kind(server, "end-of-message")
    print(f"server_after_empty_head version={version!r}", flush=True)
    return server, request


def chunked_post_server() -> Any:
    """Server that has pulled a chunked POST and is ready for body chunks."""
    server = server_connection()
    _feed_chunked_post(server)
    return server


def runtime_body_n() -> int:
    """A Content-Length that is not 10, built from the process-local integer."""
    n = 6 + (runtime_int() % 4)
    if n == 10:
        n = 8
    print(f"runtime_body_n={n}", flush=True)
    return n


def runtime_two_parts(n: int) -> tuple[bytes, bytes]:
    """Two payloads that concatenate to *n* bytes; neither piece has length 5."""
    token = runtime_token().encode("ascii")
    raw = (token * (n // len(token) + 3))[:n]
    split = 3 if n > 6 else 2
    if n - split == 5:
        split = 2 if n != 7 else 3
    if split == 5:
        split = 3
    first, second = raw[:split], raw[split:]
    if len(first) == 5 or len(second) == 5 or len(first) + len(second) != n:
        raise HarnessError(
            f"could not split {n} into two parts neither of length 5"
        )
    print(
        f"runtime_two_parts n={n} a={len(first)} b={len(second)}",
        flush=True,
    )
    return first, second


def pull_until_remote_refusal(conn: Any):
    """Pull until a remote protocol error. A data event may precede the refusal.

    A successful end-of-message or need-data is not that refusal.
    """
    last_data = None
    for _ in range(8):
        result = pull_next(conn)
        if result.exception is not None:
            return require_remote_refusal(result)
        value = result.value
        if event_is_kind(value, "data"):
            last_data = value
            print(
                f"pull_until_remote_refusal saw data {payload_as_bytes(value)!r}",
                flush=True,
            )
            continue
        raise AssertionError(
            "expected a remote protocol error, got "
            f"{type(value).__name__} {value!r}"
            + ("" if last_data is None else " after a data event")
        )
    raise AssertionError("never got a remote protocol error")


def neighbor_hello_chunk(server: Any) -> Any:
    """Live baseline: a well-formed size-5 hello chunk pulls as data."""
    feed_ok(server, b"5\r\nhello\r\n")
    event = pull_kind(server, "data")
    if payload_letters(data_payload(event)) != "hello":
        raise AssertionError(
            f"neighbor hello chunk payload is {data_payload(event)!r}"
        )
    print("neighbor_hello_chunk ok", flush=True)
    return event


__all__ = (
    "chunk_mark",
    "chunk_role",
    "chunked_post_server",
    "client_sent_empty_get",
    "feed_ok",
    "length_placeholder",
    "make_eom_with",
    "neighbor_hello_chunk",
    "passthrough_send",
    "payload_as_bytes",
    "fixed_hello_role_marks",
    "pull_until_remote_refusal",
    "public_value_blobs",
    "pull_kind",
    "require_hex_size_then_payload",
    "require_no_wire_header",
    "require_our_state",
    "require_passthrough_pieces",
    "require_token_absent_from_public",
    "require_trailer_after_zero_chunk",
    "require_zero_size_final_chunk",
    "runtime_body_n",
    "runtime_two_parts",
    "server_after_empty_get",
    "server_after_empty_head",
    "substitute_placeholder",
    "unframed_get_round_trip",
    "wire_has_header",
)
