# Interface Contract

## Product overview

**httpwire** is a pure-Python HTTP/1.1 wire protocol library (RFC 7230 message syntax and routing, plus `Expect: 100-continue` from RFC 7231). It turns high-level HTTP events into bytes and bytes back into events. What the product does, and under which conditions, is specified in the PRD; this document states only the entries a caller touches and the form of everything they return or raise.

The finished product is an **importable Python library**: not a command-line program, not a network service, and not a socket layer. There is no product-owned configuration file, no console-script or `python -m` entry, and there are no product exit codes. Outcomes are returned from, or raised by, library calls.

## Shape of the public surface

The public surface is the importable top-level package `httpwire` (a single top-level package directory named `httpwire`; the installable distribution has the same name). Every published entry is importable from the package root, both as `httpwire.<name>` and as `from httpwire import <name>`:

- `Request`, `InformationalResponse`, `Response`, `Data`, `EndOfMessage`, `ConnectionClosed` — the six event types. Each is a class; callers construct an event by calling the class. A successful construction returns an instance of that class.
- `Connection` — the connection class.
- `CLIENT`, `SERVER` — the two role values. They are distinct objects and do not compare equal.
- `NEED_DATA`, `PAUSED` — the two non-event results of `Connection.next_event`. They are distinct from each other and are not instances of any event type.
- `IDLE`, `SEND_RESPONSE`, `SEND_BODY`, `DONE`, `MUST_CLOSE`, `CLOSED`, `MIGHT_SWITCH_PROTOCOL`, `SWITCHED_PROTOCOL`, `ERROR` — the nine state values. They are package-root objects (not strings, and not values that exist only on a `Connection`); they are nine distinct objects and no two compare equal.
- `LocalProtocolError`, `RemoteProtocolError` — the two protocol-error classes. Both are exception classes; neither is a subclass of the other.

The full list of package-root names is:

```
CLIENT  CLOSED  Connection  ConnectionClosed  Data  DONE  EndOfMessage  ERROR
IDLE  InformationalResponse  LocalProtocolError  MIGHT_SWITCH_PROTOCOL  MUST_CLOSE
NEED_DATA  PAUSED  RemoteProtocolError  Request  Response  SEND_BODY  SEND_RESPONSE
SERVER  SWITCHED_PROTOCOL
```

Other names the package may define are the implementer’s choice and are not part of this surface.

## Events

Each event type is constructed with keyword arguments named after its fields. Every field is readable as an attribute of the same name on the constructed event.

| Type | Constructor keywords (optional ones marked *opt*; defaults are the PRD’s, FP-01) | Stored field types |
| --- | --- | --- |
| `Request` | `method`, `target`, `headers`, `http_version` (*opt*) | `method`, `target`, `http_version`: `bytes`; `headers`: header list |
| `InformationalResponse` | `status_code`, `headers`, `http_version` (*opt*), `reason` (*opt*) | `status_code`: `int`; `http_version`, `reason`: `bytes`; `headers`: header list |
| `Response` | `status_code`, `headers`, `http_version` (*opt*), `reason` (*opt*) | same as `InformationalResponse` |
| `Data` | `data`, `chunk_start` (*opt*), `chunk_end` (*opt*) | `data`: the payload as given; `chunk_start`, `chunk_end`: `bool` |
| `EndOfMessage` | `headers` (*opt*) | `headers`: header list (the trailing headers) |
| `ConnectionClosed` | none | no fields |

- Byte-valued arguments (`method`, `target`, `http_version`, `reason`, header names and values) accept ASCII `str` or any bytes-like object. The stored value is exactly of type `bytes` (not `bytearray`).
- `status_code` accepts an `int` or an integer-valued `int` subclass (such as an `IntEnum` member). The stored value is exactly of type `int`.
- `headers` accepts a sequence of `(name, value)` pairs.
- `Data.chunk_start` and `Data.chunk_end` are the chunk marks of a pulled data event (PRD FP-03): `chunk_start` is `True` when the event begins a chunk, `chunk_end` is `True` when it ends one. Both are exactly `bool`.
- An invalid construction raises `LocalProtocolError` and returns no event.

### Header list

The `headers` attribute of `Request`, `InformationalResponse`, `Response`, and `EndOfMessage` is a sequence container:

- Iterating it (or indexing it) yields the ordinary view: `(name, value)` pairs in order, each a `bytes` pair, `name` lowercase.
- `headers.raw_items()` — a method taking no arguments; returns a sequence of `(name, value)` pairs, each a `bytes` pair, in the same order, with `name` spelled exactly as the caller supplied it.

## Errors

`LocalProtocolError` and `RemoteProtocolError` both carry:

- `error_status_hint` — attribute, exactly of type `int`: the suggested status (PRD FP-05).
- `str(error)` — the message: free text, the implementer’s choice.

Feeding bytes after the receive side was closed (PRD FP-02) raises an exception that is an instance of neither `LocalProtocolError` nor `RemoteProtocolError`; its class is otherwise the implementer’s choice.

## `Connection`

### Signature

```
Connection(role)
Connection(role, max_incomplete_event_size)
```

- `role` — `CLIENT` or `SERVER`, first positional argument. Any other value raises an exception and produces no connection.
- `max_incomplete_event_size` — optional `int`, second positional argument: the incomplete-event size limit in bytes (PRD FP-05). When it is omitted, the PRD default applies; when it is given, that value is used.

### Attributes

| Attribute | Form |
| --- | --- |
| `our_role` | `CLIENT` or `SERVER`: the role passed to the constructor (the same object). |
| `their_role` | The other role value. |
| `our_state` | One of the nine state values: the state of our role. |
| `their_state` | One of the nine state values: the state of the peer’s role. |
| `states` | Both states. Either a mapping keyed by `CLIENT` and `SERVER` whose values are the client-side and server-side states, or a two-item sequence: client-side state, then server-side state. |
| `their_http_version` | The peer’s HTTP version once recorded, as `<major>.<minor>` in `bytes` (native text is also accepted). Before it is recorded the attribute is `None`, empty, or absent; no version is filled in before one is recorded. |
| `client_is_waiting_for_100_continue` | Exactly `bool`: whether the client of this conversation is waiting for 100-continue (PRD FP-07). |
| `they_are_waiting_for_100_continue` | Exactly `bool`: whether the peer is a client waiting for 100-continue (PRD FP-07). |
| `trailing_data` | A two-item pair `(leftover, closed)`: `leftover` is a bytes-like object holding the fed but unparsed bytes, in order; `closed` is a `bool`, `True` once an empty chunk has been fed. |

### Methods

**`send(event)`** — `event` is an instance of one of the six event types. Returns the bytes to transmit as a bytes-like object (`bytes`, `bytearray`, or `memoryview`). When the event produces no bytes, the return is `None` or an empty buffer. A refused send raises `LocalProtocolError` and returns nothing.

**`send_with_data_passthrough(event)`** — same as `send`, but returns a `list` of pieces, never a single concatenated buffer. Each piece is a bytes-like object, except that a `Data` event whose `data` is not bytes-like contributes that same object (by identity) as one piece. A refused send raises `LocalProtocolError`.

**`receive_data(data)`** — `data` is a bytes-like object just received from the peer; an empty one means the peer closed its sending side. Returns `None`. It does not raise for illegal peer bytes (those are reported by `next_event`); it raises the exception described under Errors when a non-empty chunk follows an empty one.

**`next_event()`** — no arguments. Returns `NEED_DATA`, `PAUSED`, or exactly one event instance (`Request`, `InformationalResponse`, `Response`, `Data`, `EndOfMessage`, or `ConnectionClosed`). A result that is not an event is the package-root `NEED_DATA` or `PAUSED` object itself (identity, or equality with it). Illegal peer bytes raise `RemoteProtocolError`.

**`start_next_cycle()`** — no arguments. Returns `None` on success. A refusal raises `LocalProtocolError`.

**`send_failed()`** — no arguments. Returns `None`; produces no bytes.
