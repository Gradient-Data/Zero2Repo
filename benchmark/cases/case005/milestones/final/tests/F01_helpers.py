# feature: F01
"""Observation helpers for HTTP event construction (FP-01).

Helpers classify constructor outcomes. They never return a sentinel to
mean "the observation could not be classified". Suggested-status lookup
raises when no integer carrier is present; it does not default to 400.
``require_bytes`` demands ``type is bytes`` and does not copy a buffer.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable

from _harness import (
    CallResult,
    HarnessError,
    as_int,
    as_pairs,
    attr,
    call,
    product_package_name,
    require_callable_attr,
    require_exception,
    require_value,
)

_EVENT_KINDS = (
    "request",
    "informational",
    "response",
    "data",
    "end-of-message",
    "connection-closed",
)

_CTOR_EXPORT = {
    "request": "Request",
    "informational": "InformationalResponse",
    "response": "Response",
    "data": "Data",
    "end-of-message": "EndOfMessage",
    "connection-closed": "ConnectionClosed",
}

_PUBLIC_TOKENS = frozenset(
    {
        "example.com",
        "example.org",
        "asdf",
        "gzip",
        "chunked",
        "chunked",
        "deflate",
        "keep-alive",
        "get",
        "ok",
        "host",
        "connection",
        "content-length",
        "transfer-encoding",
    }
)

_HTTP_FIELD_READERS: dict[str, str] = {
    "method": "request_method",
    "target": "request_target",
    "status": "status_code",
    "reason": "reason",
    "payload": "data_payload",
    "headers": "ordinary_pairs",
}


def package() -> Any:
    """Return the package-root module. Raises if discovery or import fails."""
    name = product_package_name()
    import httpwire as pkg

    root = pkg.__name__.split(".", 1)[0]
    if root != name:
        raise HarnessError(
            f"imported package root is {root!r}, filesystem discovery says {name!r}"
        )
    return pkg


def event_ctor(kind: str) -> Callable[..., Any]:
    """Return one of the six event constructors from the package root."""
    export = _CTOR_EXPORT.get(kind)
    if export is None:
        raise HarnessError(f"unknown event kind {kind!r}")
    pkg = package()
    try:
        ctor = getattr(pkg, export)
    except AttributeError as exc:
        raise HarnessError(
            f"package root has no event constructor {export!r}"
        ) from exc
    if not callable(ctor):
        raise HarnessError(f"{export!r} is not callable; got {type(ctor)!r}")
    return ctor


def local_protocol_error_type() -> type:
    """Return the public local-protocol-error type from the package root."""
    pkg = package()
    try:
        typ = getattr(pkg, "LocalProtocolError")
    except AttributeError as exc:
        raise HarnessError(
            "package root has no local protocol error type"
        ) from exc
    if not isinstance(typ, type):
        raise HarnessError(
            f"local protocol error type is not a class: {type(typ)!r}"
        )
    return typ


def remote_protocol_error_type() -> type:
    """Return the public remote-protocol-error type from the package root."""
    pkg = package()
    try:
        typ = getattr(pkg, "RemoteProtocolError")
    except AttributeError as exc:
        raise HarnessError(
            "package root has no remote protocol error type"
        ) from exc
    if not isinstance(typ, type):
        raise HarnessError(
            f"remote protocol error type is not a class: {type(typ)!r}"
        )
    return typ


def construct(kind: str, **fields: Any) -> CallResult:
    """Call one event constructor through the sealed harness."""
    ctor = event_ctor(kind)
    result = call(ctor, **fields)
    print(
        f"construct kind={kind!r} fields={list(fields)!r} "
        f"exc={type(result.exception).__name__ if result.exception else None}",
        flush=True,
    )
    return result


def require_event(result: CallResult) -> Any:
    """Return the constructed event. Raises if the call failed or is not an event."""
    value = require_value(result)
    ctors = tuple(event_ctor(kind) for kind in _EVENT_KINDS)
    if not isinstance(value, ctors):
        raise AssertionError(
            f"constructor returned {type(value)!r}, not an event"
        )
    return value


def suggested_status(exc: BaseException) -> int:
    """Read the suggested status from a protocol error.

    The Interface Contract states the carrier: ``error_status_hint``,
    exactly an ``int``. Missing or non-int raises :class:`HarnessError`;
    never defaults to 400.
    """
    try:
        value = getattr(exc, "error_status_hint")
    except AttributeError as probe_exc:
        raise HarnessError(
            "protocol error has no error_status_hint: "
            f"{type(exc).__name__}: {exc!r}"
        ) from probe_exc
    except Exception as probe_exc:
        raise HarnessError(
            f"cannot read error_status_hint: {probe_exc}"
        ) from probe_exc
    if type(value) is not int:
        raise HarnessError(
            f"error_status_hint is not an int: {type(value)!r} {value!r}"
        )
    print(f"suggested_status={value}", flush=True)
    return value


def require_local_refusal(
    result: CallResult, *, suggested: int | None = None
) -> BaseException:
    """Require construction produced no event and a local (not remote) protocol error.

    When *suggested* is 400 or 501, that integer must be present on the
    failure. When *suggested* is ``None``, the integer is not pinned.
    """
    exc = require_exception(result)
    assert result.value is None, (
        f"refusal still produced a value: {type(result.value)!r}"
    )
    local_t = local_protocol_error_type()
    remote_t = remote_protocol_error_type()
    assert isinstance(exc, local_t), (
        f"expected a local protocol error, got {type(exc)!r}: {exc!r}"
    )
    assert not isinstance(exc, remote_t), (
        "local protocol error must not also be a remote protocol error: "
        f"{type(exc)!r}"
    )
    if suggested is not None:
        got = suggested_status(exc)
        assert got == suggested, (
            f"suggested status is {got}, expected {suggested}"
        )
    print(
        f"local refusal suggested={suggested!r} type={type(exc).__name__}",
        flush=True,
    )
    return exc


def require_bytes(value: Any) -> bytes:
    """Require ``type(value) is bytes``. Does not copy a ``bytearray``."""
    if type(value) is not bytes:
        raise AssertionError(
            f"expected type bytes, got {type(value)!r}"
        )
    return value


def ordinary_pairs(event: Any) -> tuple[tuple[bytes, bytes], ...]:
    """Ordinary header view: lowercase name paired with the stored value."""
    container = attr(event, "headers")
    pairs = as_pairs(container)
    out: list[tuple[bytes, bytes]] = []
    for name, value in pairs:
        out.append((require_bytes(name), require_bytes(value)))
    print(f"ordinary_pairs={out!r}", flush=True)
    return tuple(out)


def raw_pairs(event: Any) -> tuple[tuple[bytes, bytes], ...]:
    """Raw-items view: caller-supplied name casing paired with the value."""
    container = attr(event, "headers")
    raw_fn = require_callable_attr(container, "raw_items")
    result = call(raw_fn)
    items = require_value(result)
    pairs = as_pairs(items)
    out: list[tuple[bytes, bytes]] = []
    for name, value in pairs:
        out.append((require_bytes(name), require_bytes(value)))
    print(f"raw_pairs={out!r}", flush=True)
    return tuple(out)


def request_method(event: Any) -> bytes:
    return require_bytes(attr(event, "method"))


def request_target(event: Any) -> bytes:
    return require_bytes(attr(event, "target"))


def event_version(event: Any) -> bytes:
    return require_bytes(attr(event, "http_version"))


def request_version(event: Any) -> bytes:
    return event_version(event)


def status_code(event: Any) -> int:
    return as_int(attr(event, "status_code"))


def reason(event: Any) -> bytes:
    return require_bytes(attr(event, "reason"))


def data_payload(event: Any) -> Any:
    """Return the data payload field. Missing field raises; no type coercion."""
    return attr(event, "data")


def trailing_pairs(event: Any) -> tuple[tuple[bytes, bytes], ...]:
    return ordinary_pairs(event)


def http_field_absent(event: Any, field: str) -> None:
    """Require *field* is classified-absent on *event*.

    Same read path as the other five events. A present value fails the
    assertion. A probe crash raises. A missing attribute is classified
    absence and returns.
    """
    reader_name = _HTTP_FIELD_READERS.get(field)
    if reader_name is None:
        raise HarnessError(f"unknown HTTP field {field!r}")
    reader = globals()[reader_name]
    try:
        value = reader(event)
    except HarnessError as exc:
        text = str(exc)
        if "has no attribute" in text:
            print(
                f"field {field!r} absent on {type(event).__name__}",
                flush=True,
            )
            return
        raise
    except Exception as exc:
        raise HarnessError(
            f"cannot probe HTTP field {field!r}: {exc}"
        ) from exc
    raise AssertionError(
        f"expected no HTTP field {field!r} on {type(event).__name__}; "
        f"found {value!r}"
    )


def runtime_token() -> str:
    """Process-local alphanumeric token that avoids fixture spellings."""
    seed = time.time_ns() ^ (os.getpid() << 16)
    token = f"t{seed:x}"
    if token.lower() in _PUBLIC_TOKENS:
        token = token + "z"
    print(f"runtime_token={token!r}", flush=True)
    return token


def runtime_int() -> int:
    """Process-local positive integer that avoids fixture statuses."""
    n = int((time.time_ns() % 800) + 50)
    forbidden = {0, 1, 2, 100, 199, 200, 204, 999}
    if n in forbidden:
        n = 317
    print(f"runtime_int={n}", flush=True)
    return n


def request_result(**fields: Any) -> CallResult:
    """Construct a request event; default method GET and target /."""
    fields.setdefault("method", "GET")
    fields.setdefault("target", "/")
    return construct("request", **fields)


def named_pairs(
    pairs: tuple[tuple[bytes, bytes], ...], name: bytes
) -> list[tuple[bytes, bytes]]:
    """Return ordinary/raw pairs whose name equals *name*."""
    return [(n, v) for n, v in pairs if n == name]


def payload_letters(value: Any) -> str:
    """Return stored data-event payload as letters.

    Native text or a byte buffer are both answers. Any other type, or a
    buffer that is not letters, raises — the observation has no answer
    and is not treated as empty content. The PRD requires the letter
    content, not a text-to-bytes conversion.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        try:
            return bytes(value).decode("ascii")
        except UnicodeDecodeError as exc:
            raise AssertionError(
                f"payload {bytes(value)!r} is not recoverable letters"
            ) from exc
    raise AssertionError(
        f"payload is not recoverable content: {type(value)!r}"
    )


def client_connection() -> Any:
    """Construct a client-role connection from the package root.

    Used to observe that a failed event construction leaves any
    already-created connection unaffected. Raises if the public
    constructor or client role is missing.
    """
    pkg = package()
    try:
        ctor = getattr(pkg, "Connection")
    except AttributeError as exc:
        raise HarnessError("package root has no Connection") from exc
    try:
        role = getattr(pkg, "CLIENT")
    except AttributeError as exc:
        raise HarnessError("package root has no CLIENT role") from exc
    if not callable(ctor):
        raise HarnessError(f"Connection is not callable; got {type(ctor)!r}")
    result = call(ctor, role)
    conn = require_value(result)
    print(f"client_connection type={type(conn).__name__}", flush=True)
    return conn


def connection_side_states(conn: Any) -> tuple[Any, Any]:
    """Read the queryable our-state and their-state.

    Missing attributes raise. A present value is returned as-is; this
    helper does not invent IDLE or any other sentinel.
    """
    our = attr(conn, "our_state")
    their = attr(conn, "their_state")
    print(
        f"connection_side_states our={our!r} their={their!r}",
        flush=True,
    )
    return (our, their)
