# httpwire — Full Product Requirements Document

## Product overview

**httpwire** is a pure-Python HTTP/1.1 wire protocol library. It implements the first chapter of HTTP/1.1 as specified in RFC 7230 (Message Syntax and Routing): taking bytes on and off the wire, and the headers that control that framing. It does not perform any network I/O of its own. An integrator supplies whatever I/O they already have — synchronous, threaded, asynchronous, or otherwise — and uses httpwire only to turn high-level HTTP events into bytes and bytes back into events.

If either side violates HTTP/1.1, the operation does not succeed and the failure is a protocol error.

This document specifies **user- and integrator-observable behavior only**. Exact published symbol names, import paths, and call spellings belong in the Interface Contract, not here. Every feature point below corresponds to behavior that exists in the finished httpwire product. Feature points are ordered so foundational capabilities come first; a later feature point may depend on an earlier one, never the reverse.

## Terminology

| Term | Meaning in this PRD |
| --- | --- |
| **Connection object** | The object that tracks one HTTP/1.1 connection. It is created in either the client role or the server role. It does not open sockets or read from the network. |
| **Event** | A high-level HTTP unit the integrator sends or receives instead of raw bytes. The six event kinds are listed in FP-01. |
| **Request event** | The start of an HTTP request: method, target, headers, and HTTP version. |
| **Informational-response event** | An HTTP 1xx response: status code in the range 100 inclusive to 200 exclusive, headers, HTTP version, and reason phrase. |
| **Response event** | The start of a final HTTP response: status code in the range 200 inclusive to 1000 exclusive, headers, HTTP version, and reason phrase. |
| **Data event** | A piece of a message body. |
| **End-of-message event** | The end of a request or response, optionally carrying trailing headers. |
| **Connection-closed event** | The sending side of this HTTP conversation will send no more data. The receiving side may still be open. |
| **Send operation** | Encode one event into bytes for the integrator to write, and update the connection’s state. A connection-closed event produces no bytes. |
| **Passthrough send** | The send variant that returns a sequence of pieces instead of one concatenated byte string, and that keeps a caller-supplied body placeholder intact so the integrator can hand it to an operating-system sendfile-style write. Specified in FP-03. |
| **Feed received bytes** | Give the connection bytes that just arrived from the peer. This only stores them. Feeding an empty chunk means the peer closed its sending side. |
| **Pull the next event** | Parse one event out of the stored bytes, update state, and return it. |
| **Need-data** | The pull result that means no further real event is available until more bytes are fed. |
| **Paused** | The pull result that means no further real event is available until something else happens (the next cycle is started, or a protocol switch is resolved). Specified in FP-04 and FP-07. |
| **Start the next cycle** | Reset a reusable connection so another request/response can run on it. Specified in FP-04. |
| **Mark send as failed** | Tell the connection that the integrator did not actually transmit the bytes the last send produced. Specified in FP-05. |
| **Client role / server role** | Which side of HTTP this connection is playing. The other side is the peer. |
| **Our state / their state** | The current state-machine state of our role and of the peer’s role. The nine states are enumerated in FP-02. |
| **Local protocol error** | A protocol failure caused by the integrator’s own event or send. It is one of the two concrete kinds of protocol error. |
| **Remote protocol error** | A protocol failure caused by the peer’s bytes. It is the other concrete kind of protocol error. |
| **Suggested status** | An integer on a protocol error suggesting which HTTP status a server might send (or might have sent) for that violation. The default is 400. |
| **Keep-alive** | Reusing one connection for another request/response cycle after both sides reach DONE. Specified in FP-04. |
| **Trailing data** | Bytes that have been fed but not yet parsed, plus whether the receive side has been closed. Specified in FP-07. |

## Public surface inventory

httpwire is a **library**. Integrators install the httpwire package and construct connection objects and events in Python. There is no command-line product, no socket layer, and no configuration file of httpwire’s own.

The public surfaces, grouped by feature point, are:

- The six event kinds, their fields, header normalization, and construction-time checks (FP-01).
- A connection object in the client or server role: send encodes events to bytes; feed-then-pull turns bytes into events; both sides of the conversation are tracked; need-data is returned when a pull cannot yet complete (FP-02).
- Body framing through `Content-Length`, `Transfer-Encoding: chunked`, and HTTP/1.0 close-delimited bodies, including the passthrough send for sendfile-style placeholders (FP-03).
- The state machine across a request/response cycle, keep-alive reuse, `Connection: close`, HTTP/1.0 peers, client non-pipelining, and serial server pipelining (FP-04).
- Local versus remote protocol errors, unrecoverable send/receive failure, the incomplete-event size limit, and marking a send as failed (FP-05).
- Half-duplex connection shutdown, clean versus unclean close, and the connection-closed event (FP-06).
- Informational responses, `Expect: 100-continue`, `CONNECT`, and `Upgrade:` protocol switches with trailing data (FP-07).

## Non-functional constraints

- **Form factor:** A pure-Python library with zero runtime third-party dependencies. No compiled extensions, native code, GPU, or accelerator are required or claimed.
- **Layout.** The importable package directory is `httpwire`.
- **Language:** Python 3.8 or newer, including the CPython and PyPy implementations.
- **Platforms:** Intended to work on Linux, macOS, and Windows. Linux with a supported interpreter is the documented execution platform.
- **Hardware:** CPU-only. There is no accelerator profile and no removable extra device. A supported interpreter on a standard host is enough to install from this source tree and use the library.
- **I/O:** httpwire contains no I/O. Bytes in and bytes out are the entire interface to the network. The library never opens sockets or starts processes.
- **Own implementation:** httpwire implements its own HTTP/1.1 parser and serializer. It does not delegate to the standard-library HTTP client or server, or to another HTTP library.
- **Protocol dialect:** httpwire itself speaks only HTTP/1.1 on the wire. It understands HTTP/1.0 peers when reading. It does not implement HTTP/2.
- **Scope:** RFC 7230 message syntax and routing, plus `Expect: 100-continue` from RFC 7231. Not URL routing, conditional GET, cookie policy, or content negotiation.
- **Error text:** The wording of protocol-error messages is free and carries no requirement.

## Non-goals

- Performing any network I/O, TLS, DNS, or URL parsing.
- Replacing an HTTP client such as requests, or a web framework. httpwire is a toolkit for building those things.
- HTTP/2 or HTTP/3.
- Supporting the HTTP/1.0 `Connection: keep-alive` pseudo-standard. An HTTP/1.0 peer always ends the connection after one cycle.
- Transfer encodings other than `chunked`. `gzip` and `deflate` as transfer encodings are refused.
- Generating a table of reason phrases. A caller who wants a reason phrase supplies one; the product does not look one up.
- Preserving chunk-extension metadata. Extensions are parsed and discarded.
- URL routing, authentication, cookies as a policy, caching, or content negotiation.
- Shipping a command-line program, a server binary, or a benchmark as a product surface.

---

## Feature points

### FP-01: HTTP events and header normalization

**Public entry:** httpwire’s event constructors, used on their own or as the values passed to the send operation in FP-02. This feature point is what an event looks like and which constructions succeed or fail **before** any connection is involved. Sending those events on a connection, and the bytes that produces, is FP-02. Body-length accounting while sending or receiving is FP-03.

**Normal behavior:**

- There are exactly six event kinds: request, informational-response, response, data, end-of-message, and connection-closed. Each kind is a distinct type.
- A request event carries a method, a target, a header list, and an HTTP version. The default HTTP version is `1.1`. Method, target, and version are stored as byte strings: native text that is ASCII, or any byte buffer, is accepted at construction and becomes bytes. Version numbers are two digits separated by a dot, so comparing versions as byte strings is meaningful.
- An HTTP/1.0 request needs no Host header. An HTTP/1.1 request needs exactly one Host header; its name is matched case-insensitively.
- An informational-response event carries an integer status in the range 100 inclusive to 200 exclusive. A response event carries an integer status in the range 200 inclusive to 1000 exclusive. A status that is an integer-valued enumeration member is stored as a plain integer. Informational-response and response events default to HTTP version `1.1`. Both carry a reason phrase that defaults to empty; a caller-supplied reason is stored as a byte string. The product never invents a reason phrase.
- A data event stores its payload unchanged. An end-of-message event constructed with no arguments has an empty trailing-header list. A connection-closed event has no fields.
- Headers on request, informational-response, response, and end-of-message events are an ordered list of name/value pairs. After construction, each name and each value is a byte string and each name is lowercase. Native ASCII text and byte-buffer values are accepted at construction. Header order is preserved as the caller gave it (sending applies the Host-first rule in FP-02).
- The ordinary header view is the lowercased name paired with the value. A raw-items view on the same header list recovers, for each header in order, the name exactly as the caller spelled it, paired with the value.
- `Content-Length` and `Transfer-Encoding` are normalized on every event’s header list. Repeated `Content-Length` values, whether given as separate headers or as comma-separated pieces of one header (whitespace around the commas is allowed), that are all equal collapse to a single `content-length` header with that value. A single `Transfer-Encoding` header whose value is `chunked` in any letter case is stored as `transfer-encoding` with the lowercase value `chunked`.
- Header values may contain any byte other than NUL, carriage return, line feed, form feed, and vertical tab, including other control bytes and non-ASCII bytes. Space and tab are allowed only between other bytes: a value that begins or ends with a space or tab breaks this rule and is refused, not stripped. Values that follow the rule are stored unchanged.

**Boundary / error behavior:**

Every refusal below is a local protocol error. No event is produced, and any existing connection is unaffected; a later valid construction succeeds.

- An HTTP/1.1 request with no Host header is refused. A request with more than one Host header (in any letter case) is refused, whatever its HTTP version.
- A header name must be an RFC 7230 token; any other name is refused. A header value that breaks the value rule above is refused. These rules apply to the header list of every event kind that carries headers.
- A request target must be one or more visible ASCII characters (bytes 33 through 126); any other byte in it is refused. A method must be a single RFC 7230 token; anything else is refused.
- A status outside the range for its event kind is refused. A status that is not an integer is refused.
- A `Content-Length` value must be a decimal integer; a value with any other character is refused. Every value of at most 18 digits is accepted; the maximum digit count is a fixed number of the implementer’s choice, from 18 to 32 inclusive, and a longer value is refused. `Content-Length` values that disagree, whether across separate headers or across the comma-separated pieces of one header, are refused.
- A `Transfer-Encoding` value other than exactly `chunked` (in any letter case), including a list that combines `chunked` with another coding, is refused with suggested status 501. A second `Transfer-Encoding` header is refused with suggested status 501, even when both values are `chunked`.

---

### FP-02: Bring-your-own-I/O connection

**Public entry:** httpwire’s connection object, constructed in the client role or the server role. The integrator encodes events with the send operation and recovers events by feeding received bytes then pulling the next event. Event shape is FP-01. Body framing rules that decide *how* a body is encoded are FP-03. Which sequences of events are legal across a cycle, and reuse of the connection, are FP-04. Protocol failures are FP-05.

**This feature point uses FP-01.** Every event named here is an event from FP-01.

**Normal behavior:**

- Constructing a connection in the client role records our role as client and the peer role as server. Constructing one in the server role records the reverse. Both sides start in IDLE. Our state, their state, and the pair of states are each queryable and always agree. The nine states a side can be in are exactly: IDLE, SEND_RESPONSE, SEND_BODY, DONE, MUST_CLOSE, CLOSED, MIGHT_SWITCH_PROTOCOL, SWITCHED_PROTOCOL, and ERROR.
- A pull on a connection with nothing stored returns need-data. It does not fail.
- Sending a request produces a complete HTTP/1.1 request: a request line naming the method, the target and version 1.1, then the headers, then a blank line. Sending moves the client to SEND_BODY and the server to SEND_RESPONSE. A server-role connection that is fed those bytes and pulls the request reaches the same states and records the peer’s HTTP version. The client does not record a peer HTTP version from its own send.
- The events one role sends are the events the other role pulls: method, target, headers (by ordinary view), version, status, reason, and payloads survive the round trip.
- Sending an informational-response or response produces an HTTP/1.1 status line with the status code followed by the reason the caller supplied, or an empty reason when none was supplied, then the headers and a blank line. An informational response other than a protocol-switch acceptance (FP-07) leaves the server in SEND_RESPONSE; a final response moves the server to SEND_BODY, and a client that pulls it records the same states.
- Under Content-Length framing (FP-03), a data event encodes as exactly its payload, and an end-of-message that completes the declared length encodes as no bytes. After the last declared body byte has been pulled, the next pull yields end-of-message without more input. When both sides have sent (or pulled) their end-of-message, both sides are DONE.
- Send never writes to a socket; the integrator receives bytes (or no bytes, for a connection-closed event) and transmits them. Feeding received bytes never reads from a socket. The two-step receive is required: feeding only stores bytes, and changes no state and records no peer version; pulling parses one event. Each pull yields at most one event, and bytes for later events stay stored for later pulls. A body may be pulled as several data events when it is fed in several pieces, and a sender may send several data events for one body.
- When the stored bytes are not yet a complete event, a pull returns need-data and the stored bytes are retained. Feeding another piece and pulling again continues the same event.
- httpwire itself encodes only HTTP/1.1. A request or response event whose HTTP version is not `1.1` cannot be sent (FP-05). A peer’s HTTP/1.0 request or response can still be pulled, and its version is reported as `1.0`. An HTTP/1.0 request with no framing headers has an empty body (FP-03).
- When encoding a request, the Host header is written before every other header, even if it was not first in the caller’s header list. The other headers keep the caller’s order.
- When encoding headers, the original name casing from construction (FP-01 raw items) is what is written. The ordinary lowercased view is not what goes on the wire.
- Received header blocks that use a lone line feed, or a mix of carriage-return/line-feed and lone line feed, as line endings are accepted. A response status line that omits the reason phrase is accepted and the reason is empty.
- Obsolete line folding (RFC 7230 §3.2.4) is accepted when **reading** headers: each continuation line (a line that starts with a space or tab) is joined to the previous header’s value, with its leading run of spaces and tabs replaced by a single space.
- After a request has been pulled, the peer HTTP version is retained for the rest of this connection; later sends on the same cycle do not change it, and it stays after the next cycle is started (FP-04).

**Boundary / error behavior:**

- Constructing a connection with a role that is neither client nor server is refused. No connection object is produced.
- Peer bytes are refused when pulled, as a remote protocol error, whenever they are not a legal HTTP/1.1 (or HTTP/1.0) message under the RFC 7230 grammar, allowing only the leniencies stated above, or when header names, header values, or request targets break the FP-01 rules.
- When the first stored byte where a request line (server role) or status line (client role, after sending a request) is expected is a space or a control byte (byte value below 33), the pull fails at once as a remote protocol error. It does not wait for a line ending.
- Feeding a non-empty chunk after an empty chunk has already been fed (the empty chunk meaning the receive side closed) is refused at feed time as a runtime error, not as a protocol error. It is a distinct failure from a local or remote protocol error. Feeding an empty chunk never fails.

---

### FP-03: Message body framing

**Public entry:** The same send, passthrough send, feed, and pull operations as FP-02, once a request or response has put that side into SEND_BODY. Which framing applies is chosen from the request or response headers (and, for responses, from the request method and the peer’s HTTP version). Event construction rules for those headers are FP-01.

**Normal behavior:**

- On a **request**, the framing is:
  - No `Content-Length` and no `Transfer-Encoding`: empty body, equivalent to Content-Length 0, whatever the method. Sending the request and then an end-of-message produces no body bytes. A server that pulls that request also pulls an end-of-message immediately.
  - `Content-Length` equal to a non-negative integer N: the sender must provide exactly N body bytes across data events. Each data event encodes as its payload with no extra framing. When N bytes have been sent, the matching end-of-message encodes as empty. The peer that pulls observes data whose payloads concatenate to those N bytes, then end-of-message.
  - `Transfer-Encoding: chunked`: the sender may provide any number of body bytes. Each non-empty data event is encoded as one HTTP/1.1 chunk (hexadecimal size line, the payload, then CRLF). An empty data event encodes as no bytes. The end-of-message event encodes as the zero-size final chunk; trailing headers it carries are written after the zero-size chunk and before the final blank line. The peer that pulls recovers the concatenated payloads and those trailing headers.
- On a **response**, `Content-Length` equal to N is the same as on a request: exactly N bytes, then end-of-message. The `Content-Length` header is kept on the wire, including when N is 0.
- On a **response**, `Transfer-Encoding: chunked`, or neither framing header, are treated as the same choice from the caller’s point of view: a body of not-yet-known length. The product picks the wire form from the peer’s HTTP version:
  - Peer HTTP/1.1: the response is sent with `Transfer-Encoding: chunked` (and without `Content-Length`), and the body is chunked as above.
  - Peer HTTP/1.0, or no request has been seen yet: the response is sent with neither framing header, the body data events encode as raw payloads, end-of-message encodes as empty, and the connection must close afterwards (FP-04, FP-06).
- If a response is constructed with both `Transfer-Encoding: chunked` and `Content-Length`, transfer-encoding wins: Content-Length is not sent, and the body is framed as in the previous bullet.
- On the receive side, the same framings are recovered from the peer’s bytes. A response with neither framing header from an HTTP/1.0 peer is close-delimited: its body is every byte until the receive side closes. That close (an empty feed) ends the body: the pulls yield end-of-message, then connection-closed, and it is not a remote protocol error (contrast FP-05). The client side is then MUST_CLOSE.
- These response situations always have an empty body, regardless of framing headers the caller set: a response to HEAD; a response whose status is 204; a response whose status is 304. No data is sent and end-of-message completes an empty body.
- A server answering HEAD writes the same framing headers it would have used for GET: chunked when the peer is HTTP/1.1, and connection-close framing when the peer is HTTP/1.0.
- When pulling a chunked body, each data event carries marks stating whether it begins a chunk, ends a chunk, both, or neither. The product emits at least one data event per received chunk, and may emit more than one when the chunk arrives in pieces: the first piece of a chunk is marked as its start, the piece that completes it is marked as its end, and a chunk delivered in one piece is marked as both. Data events from non-chunked bodies carry neither mark. These marks are ignored when a data event is sent; the encoding depends only on the payload.
- A chunk-size line is a hexadecimal number of at most a fixed number of digits of the implementer’s choice, from 16 to 32 inclusive, optionally followed by a chunk extension (starting with `;`), optionally followed by spaces or tabs, then the line ending. Chunk extensions are parsed and discarded; they never appear on a pulled data event.
- The passthrough send of a data event whose payload is not a byte string but an object with a length returns a sequence of pieces in which that same object (not a copy) is one piece, unchanged. Any framing the chosen mode needs (the chunk size line and the chunk terminator) is added as separate byte-string pieces; Content-Length and close-delimited framing add no pieces. The object’s length counts as body bytes sent, exactly as a byte payload of that length would.

**Boundary / error behavior:**

- Sending a data event whose payload would exceed the remaining Content-Length is refused as a local protocol error. Sending end-of-message before the declared Content-Length has been sent in full is refused as a local protocol error. Sending trailing headers on an end-of-message when the framing is Content-Length or HTTP/1.0 close-delimited is refused as a local protocol error.
- Sending trailing headers on an end-of-message to an HTTP/1.0 peer is refused as a local protocol error even if the caller asked for chunked framing, because the product will not actually use chunked framing for that peer.
- A received chunk-size line that breaks the rule above (more hexadecimal digits than that maximum, or any other byte) is refused. The bytes after each chunk’s data must be exactly CRLF; anything else is refused. These refusals are remote protocol errors when they come from pulled peer bytes.
- Transfer encodings other than `chunked` are refused at event construction (FP-01) and therefore never become a framing mode.

---

### FP-04: Connection lifecycle, keep-alive, reuse, and pipelining

**Public entry:** The same connection object as FP-02, plus starting the next cycle, plus the queryable states. Framing that interacts with keep-alive (HTTP/1.0 close-delimited responses) is FP-03. Protocol-switch states are refined in FP-07. Close states are refined in FP-06.

**Normal behavior:**

- A client in IDLE may send a request event and then goes to SEND_BODY. A server goes from IDLE to SEND_RESPONSE when that request is sent or pulled. The server in SEND_RESPONSE may send any number of informational-response events (staying in SEND_RESPONSE) and then one response event, and then goes to SEND_BODY. Each side in SEND_BODY may send data events (staying in SEND_BODY) and then an end-of-message event, and then goes to DONE. The same transitions apply when the events are pulled from the peer.
- A server in IDLE may send a final response event (any final status) without any request having arrived. That response is encoded, with the framing rules for a peer whose version is unknown (FP-03), and the server goes to SEND_BODY. This is how a server times out or rejects unparseable input (FP-05) without a request event.
- Keep-alive is enabled when, and only when, both sides speak HTTP/1.1 and neither side has sent a `Connection` header containing the token `close`. The token is matched case-insensitively and as a whole element of the comma-separated `Connection` value. An HTTP/1.0 request or response disables keep-alive even if its `Connection` value says `keep-alive`. When keep-alive is disabled, a side that would have entered DONE enters MUST_CLOSE instead.
- When keep-alive is disabled, the product adds `Connection: close` to the response the server sends, even if the caller omitted it (and drops any `keep-alive` token from it). A response sent with close-delimited framing (FP-03: unknown body length, and the peer is HTTP/1.0 or no request has been seen) also gets `Connection: close` and disables keep-alive.
- When both sides are in DONE, starting the next cycle succeeds and both sides return to IDLE. Further request/response cycles can then run on the same connection. The peer HTTP version recorded in FP-02 is still present after the cycle starts.
- As a client, a second request cannot be sent until the next cycle has been started, and the next cycle cannot be started until the server has reached DONE (the full response has been pulled). Client pipelining is not supported.
- As a server, requests a client pipelined are handled one cycle at a time. While the peer side is DONE and fed bytes remain unparsed, a pull returns paused and does not parse them, however many more bytes are fed. After both sides reach DONE and the next cycle is started, pulls parse the stored bytes as the next request. When the current request is finished and nothing is stored, a pull returns need-data; if bytes then arrive while the peer is still DONE, pulls return paused and those bytes appear in trailing data (FP-07).
- Starting the next cycle is refused as a local protocol error when either side is not in DONE. This refusal changes nothing: neither side moves and neither enters ERROR (contrast FP-05), and a later attempt after both sides reach DONE succeeds.

**Boundary / error behavior:**

- A client that tries to send a response or informational-response event is refused as a local protocol error. A server that tries to send a request event is refused as a local protocol error. A client that sends a second request without starting the next cycle is refused as a local protocol error.
- An HTTP/1.0 peer cannot be kept alive. Starting the next cycle after a completed HTTP/1.0 exchange (both sides MUST_CLOSE) is refused and both sides stay MUST_CLOSE.
- Paused is not need-data: after a pipelined leftover, feeding more bytes does not make the next request appear until the next cycle is started. After a switch (FP-07), paused is permanent for HTTP parsing.

---

### FP-05: Protocol errors and the incomplete-event size limit

**Public entry:** Event construction (FP-01), send, pull, start-the-next-cycle (FP-04), and mark-send-as-failed. This feature point is how failures are distinguished and what remains possible afterwards: local versus remote protocol errors, suggested status, recoverable construction and start-next-cycle, unrecoverable send and receive, mark-send-as-failed, and the incomplete-event size limit. Shutdown that is not a protocol violation is FP-06.

**Normal behavior:**

- Protocol errors come in two concrete kinds, each a distinct type: local (the integrator’s event or send violated the protocol) and remote (the peer’s bytes violated the protocol). Both kinds are protocol errors. A local protocol error is not a remote protocol error, and the reverse. Neither is the generic runtime error used when bytes are fed after the receive side has already been closed (FP-02, FP-06).
- Every protocol error carries a suggested status. The default is 400. Three specified exceptions: a `Transfer-Encoding` other than `chunked` at construction (FP-01) suggests 501; a second `Transfer-Encoding` header (even when both values are `chunked`) suggests 501; exceeding the incomplete-event size limit (below) suggests 431.
- Constructing an invalid event (FP-01) is a local protocol error and is recoverable: no event is produced, and a later valid construction succeeds. No connection state changes, because no connection was involved.
- Starting the next cycle when the connection is not ready (FP-04) is a local protocol error and is recoverable: the connection stays usable.
- A failed pull because the peer violated the protocol is a remote protocol error and is unrecoverable for receiving. Their state becomes ERROR and our state does not. Every further pull also fails as a remote protocol error, even if well-formed bytes are fed afterwards. Sending still works: after a remote protocol error a server can still send a response (typically an error status), and because the peer can no longer be kept alive that response carries `Connection: close`.
- A failed send because the integrator violated the protocol (any send refused as a local protocol error, such as an event that is illegal in the current state or an event whose HTTP version is not `1.1`) is unrecoverable for sending. The send produces no bytes, our state becomes ERROR, and their state does not. Every further send also fails as a local protocol error, including one that would have succeeded on a fresh connection.
- Whenever one side is in ERROR and the other side is in DONE, the DONE side becomes MUST_CLOSE.
- Marking a send as failed puts our state in ERROR and leaves their state unchanged, except that if their side was DONE it becomes MUST_CLOSE. It produces no bytes and doing it twice in a row has the same result. After this, send fails as a local protocol error. This is how an integrator tells httpwire that the bytes from a previous send never went out (for example a cancelled upload), so the connection must not be returned to a keep-alive pool (FP-04).
- The connection is constructed with an incomplete-event size limit, in bytes. The default is a fixed value of the implementer’s choice, at least 14 kibibytes and less than 18 kibibytes. The limit applies only while a pull cannot complete the current event because a request or response line, or its header block, is unfinished: if the stored unparsed bytes then exceed the limit, the pull fails as a remote protocol error with suggested status 431, and their state becomes ERROR. The whole unfinished line plus headers counts, not any single header value. Body bytes of a framed body are delivered as data as they arrive and never count against the limit. Bytes held while a pull is paused (FP-04, FP-07) are not counted against the limit until a later cycle starts parsing them.
- A receive-side close (an empty feed) while the current incoming message is unfinished is a remote protocol error, not a clean connection-closed event (FP-06): in the middle of a request or status line or header block, in the middle of a Content-Length body, or in the middle of a chunked body. An HTTP/1.0 close-delimited body is the opposite case: the empty feed ends the body (FP-03).

**Boundary / error behavior:**

- A local protocol error and a remote protocol error are distinct failures, distinct from each other and from the runtime error used for “bytes after end-of-receive.”
- ERROR cannot be left. No operation, including starting the next cycle, returns a side from ERROR to IDLE, DONE, or any other state.
- Send after a remote receive error still works, so a server can answer with an error response. Receive after a local send error is not required to work beyond what the peer has already sent; send itself stays failed.

---

### FP-06: Connection shutdown

**Public entry:** Sending or pulling a connection-closed event, and feeding an empty chunk to mean the receive side ended. Keep-alive transitions into MUST_CLOSE are FP-04. Unexpected close in the middle of a message is a remote protocol error in FP-05.

**Normal behavior:**

- A connection-closed event means this party will not send more HTTP data. It does not by itself mean the party cannot still receive. Sending a connection-closed event updates state and produces no bytes.
- A side may send connection-closed when it is in IDLE, DONE, MUST_CLOSE, or CLOSED; that side becomes CLOSED. Sending it again when already CLOSED is allowed (idempotent).
- Whenever one side is CLOSED and the other side is in IDLE or DONE, that other side becomes MUST_CLOSE. A side in any other state keeps its state and may continue its message.
- Feeding an empty chunk means the peer has closed its sending side. When nothing else is stored and the peer is in a state from which it may send connection-closed (above), a pull yields a connection-closed event and the same state changes apply as if the peer had sent it. Once a connection-closed event has been pulled, further pulls also yield a connection-closed event, and feeding further empty chunks remains allowed.
- A server that has pipelined requests stored before the client half-closed handles them one cycle at a time (FP-04) and pulls connection-closed only after the stored requests have been consumed.
- A side in MUST_CLOSE sends connection-closed to enter CLOSED.

**Boundary / error behavior:**

- A side in any other state (SEND_RESPONSE, SEND_BODY, MIGHT_SWITCH_PROTOCOL, SWITCHED_PROTOCOL) cannot send connection-closed; that send is a local protocol error (FP-05).
- A pulled close from a peer that is not allowed to close in its current state is a remote protocol error, not a clean connection-closed event (FP-05).
- Feeding a non-empty chunk after the receive side has already been closed is a runtime error, not a protocol error (FP-02).
- Bytes received from a peer that is in MUST_CLOSE are a remote protocol error.

---

### FP-07: Informational responses, 100-continue, and protocol switching

**Public entry:** The same connection object as FP-02, plus the waiting-for-100-continue flags, plus trailing data. Informational-response events are defined in FP-01. Paused as a flow-control result is introduced in FP-04. This feature point is the 1xx / Expect / CONNECT / Upgrade behavior that those earlier points do not specify.

**Normal behavior:**

- A server in SEND_RESPONSE may send one or more informational-response events (any 1xx status) before the final response event. A client that has sent a request pulls those informational-response events in order and remains able to send the request body.
- A request of HTTP version `1.1` whose `Expect` header contains the token `100-continue` (matched case-insensitively), with any method, makes the connection record that the client is waiting for 100-continue: on the client-role connection after it sends the request, and on the server-role connection after it pulls it. The server-role connection also reports that *they* (the peer) are waiting; a client-role connection never reports that the peer is waiting. An `Expect: 100-continue` header on an HTTP/1.0 request does not set either flag.
- The waiting flags turn off, on each connection as it sends or pulls the event, when the server sends any informational response or any final response, or when the client sends any data event or its end-of-message.
- Two kinds of switch proposal exist, and they follow the same pattern. The client proposes; the server accepts or denies; on denial, HTTP/1.1 continues; on acceptance, both sides enter SWITCHED_PROTOCOL and httpwire stops parsing HTTP.
  - A request whose method is `CONNECT`: acceptance is a final response whose status is in the 2xx range; any other final response is a denial.
  - A request carrying an `Upgrade` header: acceptance is an informational-response whose status is 101; a final response is a denial. Other informational responses neither accept nor deny.
  - A request may propose both. The server accepts at most one: a 2xx response accepts CONNECT; a 101 informational-response accepts Upgrade.
- The client must finish the proposing request (data and end-of-message) before switch-related state appears; until then it is in SEND_BODY and an unfinished body pulls as need-data. After that end-of-message, the client side is in MIGHT_SWITCH_PROTOCOL, and server-role pulls return paused (whether or not any further bytes are stored) until the server answers.
- On denial, both sides follow the ordinary rules (client DONE, server SEND_BODY, then DONE after the server’s end-of-message). Starting the next cycle is then allowed, and bytes the client sent after the proposal are parsed as the next HTTP request in that new cycle.
- On acceptance, both sides are in SWITCHED_PROTOCOL; the accepting response has no body and no end-of-message. Further pulls return paused forever. The send operation refuses every further HTTP event as a local protocol error (FP-05). Starting the next cycle is refused. Bytes stored or fed after the accepting response are never parsed as HTTP; they accumulate, in order, in trailing data.
- Trailing data is a pair: the stored unparsed bytes, and a flag that is true once an empty chunk has been fed (receive side closed). While paused for a switch proposal, feeding an empty chunk sets that flag and the pull stays paused. After a denial, that close is then pulled as a connection-closed event (FP-06). After an acceptance, it never is: the pull stays paused (the close belongs to the new protocol, not to HTTP).
- A client in MIGHT_SWITCH_PROTOCOL cannot send another request. That send is a local protocol error.

**Boundary / error behavior:**

- Status 101 is an informational-response event, not a final response event. A 2xx on CONNECT is a final response event. Using the wrong event kind for a status is already refused by FP-01.
- An accepted switch is permanent for this connection object: the connection never resumes HTTP, and no operation returns either side to IDLE or any other HTTP message state. A refused HTTP send after acceptance still makes our side ERROR, as for any refused send (FP-05), while their side stays SWITCHED_PROTOCOL. The integrator abandons the connection object and uses the socket for the new protocol, reading any leftover bytes from trailing data.
- Starting the next cycle while a proposal is unanswered (client MIGHT_SWITCH_PROTOCOL, server SEND_RESPONSE) is the recoverable local refusal of FP-04: neither side moves or enters ERROR.
- Paused because of a switch proposal, paused because of pipelining (FP-04), and need-data are distinguishable: need-data becomes a real event after more bytes of the *current* HTTP message; pipelining paused becomes a real event after the next cycle; switch paused either becomes HTTP again after a denial plus the next cycle, or stays paused forever after acceptance.
