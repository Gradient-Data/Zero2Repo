# feature: F03
"""Acceptance tests for message-body framing (FP-03).

Exercises how a side already in SEND_BODY chooses framing from headers,
method, and peer HTTP version; how the peer recovers the body; the
passthrough send of a length-bearing placeholder; and the named local
and remote refusals. Event construction is FP-01. Connection roles,
need-data, and Host-first encoding are FP-02.
"""

from __future__ import annotations

from typing import Any

from _harness import as_optional_bytes
from F01_helpers import (
    data_payload,
    event_version,
    local_protocol_error_type,
    named_pairs,
    ordinary_pairs,
    payload_letters,
    remote_protocol_error_type,
    request_method,
    request_target,
    require_local_refusal,
    runtime_int,
    runtime_token,
    trailing_pairs,
)
from F02_helpers import (
    client_connection,
    event_is_kind,
    feed_bytes,
    make_data,
    make_eom,
    make_request,
    make_response,
    pull_next,
    require_no_extra_bytes,
    require_pulled_event,
    require_remote_refusal,
    require_send_bytes,
    send_event,
    server_connection,
    wire_header_value,
)
from F03_helpers import (
    chunk_role,
    chunked_post_server,
    client_sent_empty_get,
    feed_ok,
    length_placeholder,
    make_eom_with,
    neighbor_hello_chunk,
    passthrough_send,
    payload_as_bytes,
    fixed_hello_role_marks,
    pull_kind,
    pull_until_remote_refusal,
    require_hex_size_then_payload,
    require_no_wire_header,
    require_our_state,
    require_passthrough_pieces,
    require_token_absent_from_public,
    require_trailer_after_zero_chunk,
    require_zero_size_final_chunk,
    runtime_body_n,
    runtime_two_parts,
    server_after_empty_get,
    server_after_empty_head,
    substitute_placeholder,
    unframed_get_round_trip,
    wire_has_header,
)


# ---------------------------------------------------------------------------
# S. Present-arm empty-body GET encode and pull
# ---------------------------------------------------------------------------


def test_empty_body_get_round_trips_when_package_importable():
    client = client_connection()
    encoded = require_send_bytes(
        send_event(client, make_request(headers=[("Host", "example.com")]))
    )
    eom = require_no_extra_bytes(send_event(client, make_eom()))
    print(f"empty GET encoded_len={len(encoded)} eom={eom!r}", flush=True)
    server = server_connection()
    feed_ok(server, encoded + eom)
    pulled = pull_kind(server, "request")
    assert request_method(pulled) == b"GET"
    assert request_target(pulled) == b"/"
    hosts = named_pairs(ordinary_pairs(pulled), b"host")
    assert (b"host", b"example.com") in hosts
    immediate = require_pulled_event(pull_next(server))
    print(f"immediate after request={type(immediate).__name__}", flush=True)
    assert event_is_kind(immediate, "end-of-message")
    assert not event_is_kind(immediate, "data")


def test_empty_body_get_encode_fails_when_package_not_importable():
    # The product is exercised by
    # send then end-of-message with no extra body bytes, then a peer pull of
    # request then end-of-message — not an import-stripped child.
    client = client_connection()
    encoded = require_send_bytes(
        send_event(client, make_request(headers=[("Host", "example.com")]))
    )
    eom = require_no_extra_bytes(send_event(client, make_eom()))
    print(f"present-arm empty GET encoded_len={len(encoded)} eom={eom!r}", flush=True)
    server = server_connection()
    feed_ok(server, encoded + eom)
    pulled = pull_kind(server, "request")
    assert request_method(pulled) == b"GET"
    assert request_target(pulled) == b"/"
    hosts = named_pairs(ordinary_pairs(pulled), b"host")
    assert (b"host", b"example.com") in hosts
    immediate = require_pulled_event(pull_next(server))
    print(f"immediate after request={type(immediate).__name__}", flush=True)
    assert event_is_kind(immediate, "end-of-message")
    assert not event_is_kind(immediate, "data")


# ---------------------------------------------------------------------------
# A. Request: no framing headers = empty body
# ---------------------------------------------------------------------------


def test_request_without_framing_headers_is_empty_body():
    client, raw = client_sent_empty_get()
    print(f"public empty GET raw_len={len(raw)}", flush=True)
    server = server_connection()
    feed_ok(server, raw)
    pulled = pull_kind(server, "request")
    assert request_method(pulled) == b"GET"
    immediate = require_pulled_event(pull_next(server))
    assert event_is_kind(immediate, "end-of-message")
    assert not event_is_kind(immediate, "data")


def test_runtime_request_without_framing_headers_is_empty_body():
    # Live baseline: the fixed GET / Host example.com request is empty-body.
    # The runtime arm differs only in target and Host.
    public = unframed_get_round_trip("/", "example.com")
    assert request_method(public) == b"GET"
    assert request_target(public) == b"/"
    fixed_hosts = named_pairs(ordinary_pairs(public), b"host")
    assert (b"host", b"example.com") in fixed_hosts

    token = runtime_token()
    target = "/" + token[:8]
    host = token + ".test"
    assert target != "/"
    assert host.lower() != "example.com"
    pulled = unframed_get_round_trip(target, host)
    assert request_method(pulled) == b"GET"
    assert request_target(pulled) == target.encode("ascii")
    assert request_target(pulled) != b"/"
    hosts = named_pairs(ordinary_pairs(pulled), b"host")
    assert (b"host", host.encode("ascii")) in hosts
    assert (b"host", b"example.com") not in hosts
    print(f"runtime empty-body target={target!r} host={host!r}", flush=True)


def test_post_without_framing_headers_is_empty_body():
    client = client_connection()
    encoded = require_send_bytes(
        send_event(
            client,
            make_request(method="POST", headers=[("Host", "example.com")]),
        )
    )
    require_no_extra_bytes(send_event(client, make_eom()))
    server = server_connection()
    feed_ok(server, encoded)
    pulled = pull_kind(server, "request")
    assert request_method(pulled) == b"POST"
    immediate = require_pulled_event(pull_next(server))
    print(f"POST empty-body immediate={type(immediate).__name__}", flush=True)
    assert event_is_kind(immediate, "end-of-message")
    assert not event_is_kind(immediate, "data")


# ---------------------------------------------------------------------------
# B. Request: Content-Length N = exactly N raw bytes
# ---------------------------------------------------------------------------


def test_content_length_10_request_is_ten_raw_bytes():
    client = client_connection()
    encoded = require_send_bytes(
        send_event(
            client,
            make_request(
                headers=[("Host", "example.com"), ("Content-Length", "10")]
            ),
        )
    )
    first = require_send_bytes(send_event(client, make_data(b"12345")))
    second = require_send_bytes(send_event(client, make_data(b"67890")))
    print(f"CL10 first={first!r} second={second!r}", flush=True)
    assert first == b"12345"
    assert second == b"67890"
    require_no_extra_bytes(send_event(client, make_eom()))
    server = server_connection()
    feed_ok(server, encoded)
    pull_kind(server, "request")
    feed_ok(server, first)
    d1 = pull_kind(server, "data")
    feed_ok(server, second)
    d2 = pull_kind(server, "data")
    recovered = payload_letters(data_payload(d1)) + payload_letters(
        data_payload(d2)
    )
    assert recovered == "1234567890"
    assert event_is_kind(require_pulled_event(pull_next(server)), "end-of-message")


def test_runtime_content_length_request_is_exact_raw_bytes():
    n = runtime_body_n()
    first, second = runtime_two_parts(n)
    client = client_connection()
    encoded = require_send_bytes(
        send_event(
            client,
            make_request(
                headers=[("Host", "example.com"), ("Content-Length", str(n))]
            ),
        )
    )
    a = require_send_bytes(send_event(client, make_data(first)))
    b = require_send_bytes(send_event(client, make_data(second)))
    print(f"runtime CL send a={a!r} b={b!r}", flush=True)
    assert a == first
    assert b == second
    require_no_extra_bytes(send_event(client, make_eom()))
    server = server_connection()
    feed_ok(server, encoded)
    pull_kind(server, "request")
    feed_ok(server, a)
    d1 = pull_kind(server, "data")
    feed_ok(server, b)
    d2 = pull_kind(server, "data")
    recovered = payload_as_bytes(d1) + payload_as_bytes(d2)
    assert recovered == first + second
    assert event_is_kind(require_pulled_event(pull_next(server)), "end-of-message")


def test_content_length_0_request_is_empty_body():
    client = client_connection()
    encoded = require_send_bytes(
        send_event(
            client,
            make_request(
                headers=[("Host", "example.com"), ("Content-Length", "0")]
            ),
        )
    )
    require_no_extra_bytes(send_event(client, make_eom()))
    server = server_connection()
    feed_ok(server, encoded)
    pull_kind(server, "request")
    immediate = require_pulled_event(pull_next(server))
    print(f"CL0 immediate={type(immediate).__name__}", flush=True)
    assert event_is_kind(immediate, "end-of-message")


# ---------------------------------------------------------------------------
# C. Request: Transfer-Encoding chunked
# ---------------------------------------------------------------------------


def test_chunked_request_two_payloads_and_trailer():
    client = client_connection()
    encoded = require_send_bytes(
        send_event(
            client,
            make_request(
                headers=[
                    ("Host", "example.com"),
                    ("Transfer-Encoding", "chunked"),
                ]
            ),
        )
    )
    first = require_send_bytes(send_event(client, make_data(b"1234567890")))
    second = require_send_bytes(send_event(client, make_data(b"abcde")))
    print(f"chunked first={first!r} second={second!r}", flush=True)
    assert first != b"1234567890"
    assert second != b"abcde"
    require_hex_size_then_payload(first, b"1234567890")
    require_hex_size_then_payload(second, b"abcde")
    eom = require_send_bytes(
        send_event(client, make_eom_with([("hello", "there")]))
    )
    require_trailer_after_zero_chunk(eom, b"hello", b"there")
    server = server_connection()
    feed_ok(server, encoded + first + second + eom)
    pull_kind(server, "request")
    d1 = pull_kind(server, "data")
    d2 = pull_kind(server, "data")
    recovered = payload_letters(data_payload(d1)) + payload_letters(
        data_payload(d2)
    )
    assert recovered == "1234567890abcde"
    done = pull_kind(server, "end-of-message")
    trailers = trailing_pairs(done)
    assert (b"hello", b"there") in trailers


def test_empty_data_on_chunked_encodes_no_bytes():
    client = client_connection()
    require_send_bytes(
        send_event(
            client,
            make_request(
                headers=[
                    ("Host", "example.com"),
                    ("Transfer-Encoding", "chunked"),
                ]
            ),
        )
    )
    nonempty = require_send_bytes(send_event(client, make_data(b"1234567890")))
    require_hex_size_then_payload(nonempty, b"1234567890")
    empty = require_no_extra_bytes(send_event(client, make_data(b"")))
    print(f"empty data on chunked encoded={empty!r}", flush=True)
    assert empty == b""


def test_chunked_eom_without_trailers_is_final_chunk():
    client = client_connection()
    encoded = require_send_bytes(
        send_event(
            client,
            make_request(
                headers=[
                    ("Host", "example.com"),
                    ("Transfer-Encoding", "chunked"),
                ]
            ),
        )
    )
    body = require_send_bytes(send_event(client, make_data(b"abcde")))
    require_no_extra_bytes(send_event(client, make_data(b"")))
    eom = require_send_bytes(send_event(client, make_eom()))
    print(f"chunked EOM without trailers={eom!r}", flush=True)
    require_zero_size_final_chunk(eom)
    server = server_connection()
    feed_ok(server, encoded + body + eom)
    pull_kind(server, "request")
    pull_kind(server, "data")
    done = require_pulled_event(pull_next(server))
    assert event_is_kind(done, "end-of-message")


def test_runtime_chunked_request_recovers_payloads_and_trailer():
    token = runtime_token().encode("ascii")
    first = (token + b"aaaa")[:7]
    second = (token + b"bbbb")[:6]
    name = b"x" + token[:5]
    value = token[2:9]
    client = client_connection()
    encoded = require_send_bytes(
        send_event(
            client,
            make_request(
                headers=[
                    ("Host", "example.com"),
                    ("Transfer-Encoding", "chunked"),
                ]
            ),
        )
    )
    a = require_send_bytes(send_event(client, make_data(first)))
    b = require_send_bytes(send_event(client, make_data(second)))
    require_hex_size_then_payload(a, first)
    require_hex_size_then_payload(b, second)
    eom = require_send_bytes(
        send_event(client, make_eom_with([(name, value)]))
    )
    require_trailer_after_zero_chunk(eom, name, value)
    renamed = _fresh_chunked_eom_encoding(name + b"z", value)
    assert eom != renamed
    server = server_connection()
    feed_ok(server, encoded + a + b + eom)
    pull_kind(server, "request")
    d1 = pull_kind(server, "data")
    d2 = pull_kind(server, "data")
    assert payload_as_bytes(d1) + payload_as_bytes(d2) == first + second
    done = pull_kind(server, "end-of-message")
    trailers = trailing_pairs(done)
    print(f"runtime trailers={trailers!r}", flush=True)
    assert (name.lower(), value) in trailers


def _fresh_chunked_eom_encoding(name: bytes, value: bytes) -> bytes:
    client = client_connection()
    require_send_bytes(
        send_event(
            client,
            make_request(
                headers=[
                    ("Host", "example.com"),
                    ("Transfer-Encoding", "chunked"),
                ]
            ),
        )
    )
    require_send_bytes(send_event(client, make_data(b"abcde")))
    return require_send_bytes(
        send_event(client, make_eom_with([(name, value)]))
    )


# ---------------------------------------------------------------------------
# D. Response: Content-Length N
# ---------------------------------------------------------------------------


def test_content_length_response_is_exact_raw_bytes():
    client, raw = client_sent_empty_get()
    server, _ = server_after_empty_get()
    resp = require_send_bytes(
        send_event(server, make_response(200, headers=[("Content-Length", "10")]))
    )
    first = require_send_bytes(send_event(server, make_data(b"12345")))
    second = require_send_bytes(send_event(server, make_data(b"67890")))
    print(f"CL response first={first!r} second={second!r}", flush=True)
    assert first == b"12345"
    assert second == b"67890"
    require_no_extra_bytes(send_event(server, make_eom()))
    feed_ok(client, resp)
    pull_kind(client, "response")
    feed_ok(client, first)
    d1 = pull_kind(client, "data")
    feed_ok(client, second)
    d2 = pull_kind(client, "data")
    assert (
        payload_letters(data_payload(d1)) + payload_letters(data_payload(d2))
        == "1234567890"
    )
    assert event_is_kind(require_pulled_event(pull_next(client)), "end-of-message")


def test_runtime_content_length_response_is_exact_raw_bytes():
    n = runtime_body_n()
    first, second = runtime_two_parts(n)
    client, _ = client_sent_empty_get()
    server, _ = server_after_empty_get()
    resp = require_send_bytes(
        send_event(
            server, make_response(200, headers=[("Content-Length", str(n))])
        )
    )
    a = require_send_bytes(send_event(server, make_data(first)))
    b = require_send_bytes(send_event(server, make_data(second)))
    assert a == first
    assert b == second
    require_no_extra_bytes(send_event(server, make_eom()))
    feed_ok(client, resp)
    pull_kind(client, "response")
    feed_ok(client, a)
    d1 = pull_kind(client, "data")
    feed_ok(client, b)
    d2 = pull_kind(client, "data")
    assert payload_as_bytes(d1) + payload_as_bytes(d2) == first + second
    assert event_is_kind(require_pulled_event(pull_next(client)), "end-of-message")


def test_content_length_0_response_keeps_content_length():
    client, _ = client_sent_empty_get()
    server, _ = server_after_empty_get()
    resp = require_send_bytes(
        send_event(server, make_response(200, headers=[("Content-Length", "0")]))
    )
    print(f"CL0 response headers TE={wire_has_header(resp, b'Transfer-Encoding')}", flush=True)
    assert wire_has_header(resp, b"Content-Length")
    require_no_wire_header(resp, b"Transfer-Encoding")
    assert wire_header_value(resp, b"Content-Length") == b"0"
    require_no_extra_bytes(send_event(server, make_eom()))
    feed_ok(client, resp)
    pull_kind(client, "response")
    done = require_pulled_event(pull_next(client))
    assert event_is_kind(done, "end-of-message")


# ---------------------------------------------------------------------------
# E. Unknown-length response follows peer version
# ---------------------------------------------------------------------------


def test_unframed_200_to_http11_is_chunked():
    client, _ = client_sent_empty_get()
    server, _ = server_after_empty_get(version=b"1.1")
    resp = require_send_bytes(send_event(server, make_response(200, headers=[])))
    print(f"unframed 1.1 TE={wire_has_header(resp, b'Transfer-Encoding')}", flush=True)
    assert wire_has_header(resp, b"Transfer-Encoding")
    assert wire_header_value(resp, b"Transfer-Encoding") == b"chunked"
    require_no_wire_header(resp, b"Content-Length")
    body = require_send_bytes(send_event(server, make_data(b"12345")))
    assert body != b"12345"
    require_hex_size_then_payload(body, b"12345")
    eom = require_send_bytes(send_event(server, make_eom()))
    feed_ok(client, resp + body + eom)
    pulled = pull_kind(client, "response")
    tes = named_pairs(ordinary_pairs(pulled), b"transfer-encoding")
    assert (b"transfer-encoding", b"chunked") in tes
    data = pull_kind(client, "data")
    assert payload_letters(data_payload(data)) == "12345"
    pull_kind(client, "end-of-message")


def test_explicit_chunked_200_to_http11_is_chunked():
    client, _ = client_sent_empty_get()
    server, _ = server_after_empty_get(version=b"1.1")
    resp = require_send_bytes(
        send_event(
            server,
            make_response(200, headers=[("Transfer-Encoding", "chunked")]),
        )
    )
    assert wire_has_header(resp, b"Transfer-Encoding")
    assert wire_header_value(resp, b"Transfer-Encoding") == b"chunked"
    require_no_wire_header(resp, b"Content-Length")
    body = require_send_bytes(send_event(server, make_data(b"12345")))
    require_hex_size_then_payload(body, b"12345")
    eom = require_send_bytes(send_event(server, make_eom()))
    feed_ok(client, resp + body + eom)
    pulled = pull_kind(client, "response")
    tes = named_pairs(ordinary_pairs(pulled), b"transfer-encoding")
    assert (b"transfer-encoding", b"chunked") in tes
    pull_kind(client, "data")
    pull_kind(client, "end-of-message")


def test_unframed_200_to_http10_is_close_delimited():
    server, _ = server_after_empty_get(version=b"1.0")
    resp = require_send_bytes(send_event(server, make_response(200, headers=[])))
    print(f"unframed 1.0 CL={wire_has_header(resp, b'Content-Length')}", flush=True)
    require_no_wire_header(resp, b"Content-Length")
    require_no_wire_header(resp, b"Transfer-Encoding")
    body = require_send_bytes(send_event(server, make_data(b"12345")))
    assert body == b"12345"
    require_no_extra_bytes(send_event(server, make_eom()))
    require_our_state(server, "MUST_CLOSE")


def test_response_before_any_request_is_close_delimited():
    server = server_connection()
    resp = require_send_bytes(send_event(server, make_response(200, headers=[])))
    require_no_wire_header(resp, b"Content-Length")
    require_no_wire_header(resp, b"Transfer-Encoding")
    body = require_send_bytes(send_event(server, make_data(b"12345")))
    assert body == b"12345"
    require_no_extra_bytes(send_event(server, make_eom()))
    require_our_state(server, "MUST_CLOSE")

    other = server_connection()
    te = require_send_bytes(
        send_event(
            other,
            make_response(200, headers=[("Transfer-Encoding", "chunked")]),
        )
    )
    require_no_wire_header(te, b"Content-Length")
    require_no_wire_header(te, b"Transfer-Encoding")
    raw = require_send_bytes(send_event(other, make_data(b"abcde")))
    print(f"idle TE-asked body={raw!r}", flush=True)
    assert raw == b"abcde"
    require_no_extra_bytes(send_event(other, make_eom()))
    require_our_state(other, "MUST_CLOSE")


def test_runtime_unknown_length_follows_peer_version():
    token = runtime_token().encode("ascii")
    payload = (token + b"zzzz")[:8]
    status = 201 + (runtime_int() % 3)
    if status in (204, 304):
        status = 201
    print(f"runtime unknown-length status={status} payload={payload!r}", flush=True)

    client11, _ = client_sent_empty_get()
    server11, _ = server_after_empty_get(version=b"1.1")
    resp11 = require_send_bytes(
        send_event(server11, make_response(status, headers=[]))
    )
    assert wire_has_header(resp11, b"Transfer-Encoding")
    require_no_wire_header(resp11, b"Content-Length")
    body11 = require_send_bytes(send_event(server11, make_data(payload)))
    require_hex_size_then_payload(body11, payload)
    eom11 = require_send_bytes(send_event(server11, make_eom()))
    feed_ok(client11, resp11 + body11 + eom11)
    pull_kind(client11, "response")
    assert payload_as_bytes(pull_kind(client11, "data")) == payload

    server10, _ = server_after_empty_get(version=b"1.0")
    resp10 = require_send_bytes(
        send_event(server10, make_response(status, headers=[]))
    )
    require_no_wire_header(resp10, b"Content-Length")
    require_no_wire_header(resp10, b"Transfer-Encoding")
    body10 = require_send_bytes(send_event(server10, make_data(payload)))
    assert body10 == payload
    require_no_extra_bytes(send_event(server10, make_eom()))
    require_our_state(server10, "MUST_CLOSE")


# ---------------------------------------------------------------------------
# F. Receive-side HTTP/1.0 close-delimited + empty feed
# ---------------------------------------------------------------------------


def test_http10_unframed_200_empty_feed_is_eom_then_closed():
    client, _ = client_sent_empty_get()
    feed_ok(client, b"HTTP/1.0 200 \r\n\r\n")
    pulled = pull_kind(client, "response")
    assert event_version(pulled) == b"1.0"
    feed_ok(client, b"12345")
    assert payload_letters(data_payload(pull_kind(client, "data"))) == "12345"
    feed_ok(client, b"67890")
    assert payload_letters(data_payload(pull_kind(client, "data"))) == "67890"
    feed_ok(client, b"")
    done = require_pulled_event(pull_next(client))
    print(f"http10 empty-feed first={type(done).__name__}", flush=True)
    assert event_is_kind(done, "end-of-message")
    closed = require_pulled_event(pull_next(client))
    assert event_is_kind(closed, "connection-closed")
    require_our_state(client, "MUST_CLOSE")


def test_http10_empty_feed_is_not_remote_error():
    client, _ = client_sent_empty_get()
    feed_ok(client, b"HTTP/1.0 200 \r\n\r\n")
    pull_kind(client, "response")
    feed_ok(client, b"12345")
    pull_kind(client, "data")
    feed_ok(client, b"")
    result = pull_next(client)
    print(
        f"http10 empty-feed exc={type(result.exception).__name__ if result.exception else None}",
        flush=True,
    )
    event = require_pulled_event(result)
    assert event_is_kind(event, "end-of-message")
    assert not event_is_kind(event, "data")


def test_unfinished_content_length_empty_feed_is_remote_error():
    neighbor = client_connection()
    require_send_bytes(
        send_event(neighbor, make_request(headers=[("Host", "example.com")]))
    )
    require_no_extra_bytes(send_event(neighbor, make_eom()))
    feed_ok(neighbor, b"HTTP/1.0 200 \r\n\r\n")
    pull_kind(neighbor, "response")
    feed_ok(neighbor, b"12345")
    pull_kind(neighbor, "data")
    feed_ok(neighbor, b"")
    ok = require_pulled_event(pull_next(neighbor))
    assert event_is_kind(ok, "end-of-message")

    client, _ = client_sent_empty_get()
    feed_ok(client, b"HTTP/1.0 200 \r\nContent-Length: 100\r\n\r\n")
    pull_kind(client, "response")
    feed_ok(client, b"12345")
    pull_kind(client, "data")
    feed_ok(client, b"")
    result = pull_next(client)
    print(
        f"unfinished CL empty-feed exc={type(result.exception).__name__ if result.exception else None}",
        flush=True,
    )
    require_remote_refusal(result)
    assert result.value is None or not event_is_kind(result.value, "data")
    assert result.value is None or not event_is_kind(result.value, "end-of-message")


def test_unfinished_chunked_empty_feed_is_remote_error():
    neighbor = chunked_post_server()
    neighbor_hello_chunk(neighbor)

    server = chunked_post_server()
    feed_ok(server, b"5\r\nhel")
    pulled = pull_kind(server, "data")
    assert payload_letters(data_payload(pulled)) == "hel"
    feed_ok(server, b"")
    result = pull_next(server)
    print(
        f"unfinished chunked empty-feed exc="
        f"{type(result.exception).__name__ if result.exception else None}",
        flush=True,
    )
    require_remote_refusal(result)


def test_runtime_http10_close_delimited_body():
    token = runtime_token().encode("ascii")
    first = (token + b"1111")[:6]
    second = (token + b"2222")[:7]
    client, _ = client_sent_empty_get()
    feed_ok(client, b"HTTP/1.0 200 \r\n\r\n")
    pull_kind(client, "response")
    feed_ok(client, first)
    assert payload_as_bytes(pull_kind(client, "data")) == first
    feed_ok(client, second)
    assert payload_as_bytes(pull_kind(client, "data")) == second
    feed_ok(client, b"")
    assert event_is_kind(require_pulled_event(pull_next(client)), "end-of-message")
    assert event_is_kind(
        require_pulled_event(pull_next(client)), "connection-closed"
    )
    require_our_state(client, "MUST_CLOSE")


# ---------------------------------------------------------------------------
# G. TE wins over Content-Length on a response
# ---------------------------------------------------------------------------


def test_response_te_wins_over_content_length():
    client, _ = client_sent_empty_get()
    server, _ = server_after_empty_get(version=b"1.1")
    resp = require_send_bytes(
        send_event(
            server,
            make_response(
                200,
                headers=[
                    ("Transfer-Encoding", "chunked"),
                    ("Content-Length", "100"),
                ],
            ),
        )
    )
    require_no_wire_header(resp, b"Content-Length")
    assert wire_has_header(resp, b"Transfer-Encoding")
    assert wire_header_value(resp, b"Transfer-Encoding") == b"chunked"
    body = require_send_bytes(send_event(server, make_data(b"12345")))
    assert body != b"12345"
    require_hex_size_then_payload(body, b"12345")
    eom = send_event(server, make_eom())
    print(
        f"TE-wins EOM exc={type(eom.exception).__name__ if eom.exception else None}",
        flush=True,
    )
    require_send_bytes(eom)

    cl_only, _ = server_after_empty_get(version=b"1.1")
    cl_resp = require_send_bytes(
        send_event(
            cl_only, make_response(200, headers=[("Content-Length", "100")])
        )
    )
    assert wire_has_header(cl_resp, b"Content-Length")
    raw = require_send_bytes(send_event(cl_only, make_data(b"12345")))
    assert raw == b"12345"
    early = send_event(cl_only, make_eom())
    require_local_refusal(early)


def test_runtime_response_te_wins_over_content_length():
    n = 40 + (runtime_int() % 50)
    if n == 100:
        n = 80
    payload = runtime_token().encode("ascii")[:6]
    assert len(payload) != n
    server, _ = server_after_empty_get(version=b"1.1")
    resp = require_send_bytes(
        send_event(
            server,
            make_response(
                200,
                headers=[
                    ("Transfer-Encoding", "chunked"),
                    ("Content-Length", str(n)),
                ],
            ),
        )
    )
    require_no_wire_header(resp, b"Content-Length")
    assert wire_header_value(resp, b"Transfer-Encoding") == b"chunked"
    body = require_send_bytes(send_event(server, make_data(payload)))
    require_hex_size_then_payload(body, payload)
    require_send_bytes(send_event(server, make_eom()))


def test_response_te_and_content_length_to_http10_is_close_delimited():
    server, _ = server_after_empty_get(version=b"1.0")
    resp = require_send_bytes(
        send_event(
            server,
            make_response(
                200,
                headers=[
                    ("Transfer-Encoding", "chunked"),
                    ("Content-Length", "100"),
                ],
            ),
        )
    )
    print(
        f"TE+CL 1.0 CL={wire_has_header(resp, b'Content-Length')} "
        f"TE={wire_has_header(resp, b'Transfer-Encoding')}",
        flush=True,
    )
    require_no_wire_header(resp, b"Content-Length")
    require_no_wire_header(resp, b"Transfer-Encoding")
    body = require_send_bytes(send_event(server, make_data(b"12345")))
    assert body == b"12345"
    require_no_extra_bytes(send_event(server, make_eom()))
    require_our_state(server, "MUST_CLOSE")


# ---------------------------------------------------------------------------
# H. HEAD / 204 / 304 empty body; HEAD advertises GET framing
# ---------------------------------------------------------------------------


def _peer_sees_empty_body(client: Any, resp: bytes, eom: bytes | None) -> None:
    feed_ok(client, resp + (eom or b""))
    pull_kind(client, "response")
    nxt = require_pulled_event(pull_next(client))
    print(f"empty-body peer next={type(nxt).__name__}", flush=True)
    assert event_is_kind(nxt, "end-of-message")
    assert not event_is_kind(nxt, "data")


def test_head_204_304_complete_with_empty_body():
    client_h = client_connection()
    head_req = require_send_bytes(
        send_event(
            client_h, make_request(method="HEAD", headers=[("Host", "example.com")])
        )
    )
    require_no_extra_bytes(send_event(client_h, make_eom()))
    server_h, _ = server_after_empty_head(version=b"1.1")
    resp_h = require_send_bytes(send_event(server_h, make_response(200, headers=[])))
    eom_h = send_event(server_h, make_eom())
    assert eom_h.exception is None
    eom_h_bytes = as_optional_bytes(eom_h.value)
    _peer_sees_empty_body(client_h, resp_h, eom_h_bytes)
    _ = head_req

    client_204, _ = client_sent_empty_get()
    server_204, _ = server_after_empty_get()
    resp_204 = require_send_bytes(
        send_event(server_204, make_response(204, headers=[]))
    )
    eom_204 = send_event(server_204, make_eom())
    assert eom_204.exception is None
    _peer_sees_empty_body(client_204, resp_204, as_optional_bytes(eom_204.value))

    client_304, _ = client_sent_empty_get()
    server_304, _ = server_after_empty_get()
    resp_304 = require_send_bytes(
        send_event(server_304, make_response(304, headers=[]))
    )
    eom_304 = send_event(server_304, make_eom())
    assert eom_304.exception is None
    _peer_sees_empty_body(client_304, resp_304, as_optional_bytes(eom_304.value))


def _offer_body_must_not_appear(server: Any, payload: bytes) -> None:
    result = send_event(server, make_data(payload))
    if result.exception is not None:
        print(
            f"empty-body data offer refused n={len(payload)} "
            f"exc={type(result.exception).__name__}",
            flush=True,
        )
        refused = True
        encoded = None
    else:
        encoded = as_optional_bytes(result.value)
        refused = False
        print(f"empty-body data offer encoded={encoded!r}", flush=True)
    has_body_bytes = encoded is not None and len(encoded) > 0
    print(
        f"empty-body data offer refused={refused} has_body_bytes={has_body_bytes}",
        flush=True,
    )
    assert refused or not has_body_bytes


def test_empty_body_data_event_is_not_sent():
    baseline_server, _ = server_after_empty_get()
    require_send_bytes(
        send_event(
            baseline_server,
            make_response(200, headers=[("Content-Length", "10")]),
        )
    )
    ten = require_send_bytes(send_event(baseline_server, make_data(b"12345")))
    ten += require_send_bytes(send_event(baseline_server, make_data(b"67890")))
    print(f"baseline 200+CL10 body={ten!r}", flush=True)
    assert ten == b"1234567890"

    head_server, _ = server_after_empty_head(version=b"1.1")
    require_send_bytes(send_event(head_server, make_response(200, headers=[])))
    _offer_body_must_not_appear(head_server, b"12345")

    s204, _ = server_after_empty_get()
    require_send_bytes(send_event(s204, make_response(204, headers=[])))
    _offer_body_must_not_appear(s204, b"12345")

    s304, _ = server_after_empty_get()
    require_send_bytes(send_event(s304, make_response(304, headers=[])))
    _offer_body_must_not_appear(s304, b"12345")


def test_empty_body_ignores_caller_framing_headers():
    client = client_connection()
    require_send_bytes(
        send_event(
            client, make_request(method="HEAD", headers=[("Host", "example.com")])
        )
    )
    require_no_extra_bytes(send_event(client, make_eom()))
    server, _ = server_after_empty_head(version=b"1.1")
    resp = require_send_bytes(
        send_event(
            server, make_response(200, headers=[("Content-Length", "10")])
        )
    )
    eom = send_event(server, make_eom())
    assert eom.exception is None
    _peer_sees_empty_body(client, resp, as_optional_bytes(eom.value))

    head2, _ = server_after_empty_head(version=b"1.1")
    require_send_bytes(
        send_event(
            head2, make_response(200, headers=[("Content-Length", "10")])
        )
    )
    _offer_body_must_not_appear(head2, b"1234567890")

    te_server, _ = server_after_empty_head(version=b"1.1")
    te_resp = require_send_bytes(
        send_event(
            te_server,
            make_response(200, headers=[("Transfer-Encoding", "chunked")]),
        )
    )
    te_client = client_connection()
    require_send_bytes(
        send_event(
            te_client,
            make_request(method="HEAD", headers=[("Host", "example.com")]),
        )
    )
    require_no_extra_bytes(send_event(te_client, make_eom()))
    te_eom = send_event(te_server, make_eom())
    assert te_eom.exception is None
    _peer_sees_empty_body(te_client, te_resp, as_optional_bytes(te_eom.value))


def test_head_to_http11_advertises_chunked_like_get():
    get_server, _ = server_after_empty_get(version=b"1.1")
    get_resp = require_send_bytes(
        send_event(get_server, make_response(200, headers=[]))
    )
    assert wire_has_header(get_resp, b"Transfer-Encoding")
    assert wire_header_value(get_resp, b"Transfer-Encoding") == b"chunked"
    require_no_wire_header(get_resp, b"Content-Length")

    head_server, _ = server_after_empty_head(version=b"1.1")
    head_resp = require_send_bytes(
        send_event(head_server, make_response(200, headers=[]))
    )
    print(
        f"HEAD 1.1 TE={wire_has_header(head_resp, b'Transfer-Encoding')}",
        flush=True,
    )
    assert wire_has_header(head_resp, b"Transfer-Encoding")
    assert wire_header_value(head_resp, b"Transfer-Encoding") == b"chunked"
    require_no_wire_header(head_resp, b"Content-Length")


def test_head_to_http10_advertises_close_like_get():
    get_server, _ = server_after_empty_get(version=b"1.0")
    get_resp = require_send_bytes(
        send_event(get_server, make_response(200, headers=[]))
    )
    require_no_wire_header(get_resp, b"Content-Length")
    require_no_wire_header(get_resp, b"Transfer-Encoding")
    assert not wire_has_header(get_resp, b"Content-Length")
    assert not wire_has_header(get_resp, b"Transfer-Encoding")

    head_server, _ = server_after_empty_head(version=b"1.0")
    head_resp = require_send_bytes(
        send_event(head_server, make_response(200, headers=[]))
    )
    print(
        f"HEAD 1.0 CL={wire_has_header(head_resp, b'Content-Length')} "
        f"TE={wire_has_header(head_resp, b'Transfer-Encoding')}",
        flush=True,
    )
    require_no_wire_header(head_resp, b"Content-Length")
    require_no_wire_header(head_resp, b"Transfer-Encoding")
    assert not wire_has_header(head_resp, b"Content-Length")
    assert not wire_has_header(head_resp, b"Transfer-Encoding")
    assert wire_has_header(head_resp, b"Content-Length") == wire_has_header(
        get_resp, b"Content-Length"
    )
    assert wire_has_header(head_resp, b"Transfer-Encoding") == wire_has_header(
        get_resp, b"Transfer-Encoding"
    )


# ---------------------------------------------------------------------------
# I. Chunk start/end marks, extensions, spaces/tabs after size
# ---------------------------------------------------------------------------


def test_whole_five_byte_chunk_is_start_and_end():
    roles = fixed_hello_role_marks()
    server = chunked_post_server()
    feed_ok(server, b"5\r\nhello\r\n")
    event = pull_kind(server, "data")
    assert payload_letters(data_payload(event)) == "hello"
    role = chunk_role(event, roles)
    print(f"whole hello role={role}", flush=True)
    assert role == "both"


def test_split_five_byte_chunk_is_start_middle_end():
    roles = fixed_hello_role_marks()
    server = chunked_post_server()
    feed_ok(server, b"5\r\nhel")
    first = pull_kind(server, "data")
    feed_ok(server, b"l")
    middle = pull_kind(server, "data")
    feed_ok(server, b"o\r\n")
    last = pull_kind(server, "data")
    recovered = (
        payload_letters(data_payload(first))
        + payload_letters(data_payload(middle))
        + payload_letters(data_payload(last))
    )
    assert recovered == "hello"
    r1, r2, r3 = (
        chunk_role(first, roles),
        chunk_role(middle, roles),
        chunk_role(last, roles),
    )
    print(f"split hello roles={r1},{r2},{r3}", flush=True)
    assert r1 == "start"
    assert r2 == "neither"
    assert r3 == "end"
    assert len({r1, r2, r3, "both"}) == 4


def test_runtime_split_chunk_marks():
    roles = fixed_hello_role_marks()
    token = runtime_token().encode("ascii")
    payload = (token * 3)[:7]
    assert len(payload) != 5
    size = format(len(payload), "x").encode("ascii")
    first, mid, last = payload[:2], payload[2:5], payload[5:]
    assert first and mid and last

    whole = chunked_post_server()
    feed_ok(whole, size + b"\r\n" + payload + b"\r\n")
    both_event = pull_kind(whole, "data")
    assert payload_as_bytes(both_event) == payload
    assert chunk_role(both_event, roles) == "both"

    split = chunked_post_server()
    feed_ok(split, size + b"\r\n" + first)
    e1 = pull_kind(split, "data")
    feed_ok(split, mid)
    e2 = pull_kind(split, "data")
    feed_ok(split, last + b"\r\n")
    e3 = pull_kind(split, "data")
    assert payload_as_bytes(e1) + payload_as_bytes(e2) + payload_as_bytes(e3) == payload
    print(
        f"runtime split roles={chunk_role(e1, roles)},"
        f"{chunk_role(e2, roles)},{chunk_role(e3, roles)}",
        flush=True,
    )
    assert chunk_role(e1, roles) == "start"
    assert chunk_role(e2, roles) == "neither"
    assert chunk_role(e3, roles) == "end"


def test_two_chunks_in_one_feed_are_two_both_events():
    roles = fixed_hello_role_marks()
    first = b"abcdef"
    second = b"uvwxyz"
    raw = b"6\r\nabcdef\r\n6\r\nuvwxyz\r\n"
    server = chunked_post_server()
    feed_ok(server, raw)
    e1 = pull_kind(server, "data")
    e2 = pull_kind(server, "data")
    print(
        f"two-chunk roles={chunk_role(e1, roles)},{chunk_role(e2, roles)}",
        flush=True,
    )
    assert payload_as_bytes(e1) == first
    assert payload_as_bytes(e2) == second
    assert chunk_role(e1, roles) == "both"
    assert chunk_role(e2, roles) == "both"


def test_chunk_extension_discarded_payload_kept():
    neighbor = chunked_post_server()
    feed_ok(neighbor, b"5\r\nxxxxx\r\n")
    plain = pull_kind(neighbor, "data")
    assert payload_letters(data_payload(plain)) == "xxxxx"

    server = chunked_post_server()
    feed_ok(server, b"5;hello=there\r\nxxxxx\r\n")
    event = pull_kind(server, "data")
    assert payload_letters(data_payload(event)) == "xxxxx"
    require_token_absent_from_public(event, b"hello=there")


def test_runtime_chunk_extension_discarded():
    token = runtime_token().encode("ascii")
    ext_name = b"z" + token[:6]
    ext = ext_name + b"=1"
    assert ext != b"hello=there"
    server = chunked_post_server()
    feed_ok(server, b"5;" + ext + b"\r\nxxxxx\r\n")
    event = pull_kind(server, "data")
    assert payload_letters(data_payload(event)) == "xxxxx"
    require_token_absent_from_public(event, ext)
    require_token_absent_from_public(event, ext_name)


def test_spaces_after_chunk_size_accepted():
    neighbor = chunked_post_server()
    neighbor_hello_chunk(neighbor)
    server = chunked_post_server()
    feed_ok(server, b"5 \r\nhello\r\n")
    event = pull_kind(server, "data")
    print(f"space-after-size payload={data_payload(event)!r}", flush=True)
    assert payload_letters(data_payload(event)) == "hello"


def test_tabs_after_chunk_size_accepted():
    neighbor = chunked_post_server()
    neighbor_hello_chunk(neighbor)
    server = chunked_post_server()
    feed_ok(server, b"5\t\r\nhello\r\n")
    event = pull_kind(server, "data")
    print(f"tab-after-size payload={data_payload(event)!r}", flush=True)
    assert payload_letters(data_payload(event)) == "hello"


def _send_data_on_fresh_chunked(event: Any) -> bytes:
    client = client_connection()
    require_send_bytes(
        send_event(
            client,
            make_request(
                method="POST",
                headers=[
                    ("Host", "example.com"),
                    ("Transfer-Encoding", "chunked"),
                ],
            ),
        )
    )
    return require_send_bytes(send_event(client, event))


def test_chunk_marks_are_ignored_when_data_is_sent():
    roles = fixed_hello_role_marks()
    source = chunked_post_server()
    feed_ok(source, b"5\r\nhello\r\n")
    marked = pull_kind(source, "data")
    assert payload_letters(data_payload(marked)) == "hello"
    assert chunk_role(marked, roles) == "both"

    plain = make_data(b"hello")
    marked_wire = _send_data_on_fresh_chunked(marked)
    plain_wire = _send_data_on_fresh_chunked(plain)
    print(
        f"ignored-marks both marked_wire={marked_wire!r} plain_wire={plain_wire!r}",
        flush=True,
    )
    assert marked_wire == plain_wire
    require_hex_size_then_payload(marked_wire, b"hello")

    split = chunked_post_server()
    feed_ok(split, b"5\r\nhel")
    start_event = pull_kind(split, "data")
    assert payload_as_bytes(start_event) == b"hel"
    assert chunk_role(start_event, roles) == "start"
    start_wire = _send_data_on_fresh_chunked(start_event)
    hel_wire = _send_data_on_fresh_chunked(make_data(b"hel"))
    print(
        f"ignored-marks start start_wire={start_wire!r} hel_wire={hel_wire!r}",
        flush=True,
    )
    assert start_wire == hel_wire
    require_hex_size_then_payload(start_wire, b"hel")

    cl_client = client_connection()
    require_send_bytes(
        send_event(
            cl_client,
            make_request(
                headers=[("Host", "example.com"), ("Content-Length", "5")],
            ),
        )
    )
    cl_wire = require_send_bytes(send_event(cl_client, marked))
    print(f"ignored-marks CL wire={cl_wire!r}", flush=True)
    assert cl_wire == b"hello"


# ---------------------------------------------------------------------------
# J. Passthrough placeholder identity
# ---------------------------------------------------------------------------


def _server_after_get_and_200(headers: list, *, version: bytes = b"1.1") -> Any:
    server, _ = server_after_empty_get(version=version)
    require_send_bytes(send_event(server, make_response(200, headers=headers)))
    return server


def test_passthrough_content_length_is_only_placeholder():
    server = _server_after_get_and_200([("Content-Length", "10")])
    placeholder = length_placeholder(10)
    pieces = require_passthrough_pieces(
        passthrough_send(server, make_data(placeholder))
    )
    print(f"CL passthrough pieces={pieces!r}", flush=True)
    assert pieces == (placeholder,)
    assert pieces[0] is placeholder


def test_passthrough_content_length_eom_then_succeeds():
    server = _server_after_get_and_200([("Content-Length", "10")])
    placeholder = length_placeholder(10)
    pieces = require_passthrough_pieces(
        passthrough_send(server, make_data(placeholder))
    )
    print(f"CL passthrough-then-EOM pieces={pieces!r}", flush=True)
    assert any(item is placeholder for item in pieces)
    eom = require_no_extra_bytes(send_event(server, make_eom()))
    print(f"CL passthrough-then-EOM eom={eom!r}", flush=True)
    assert eom == b""


def test_passthrough_short_placeholder_eom_is_local_error():
    n = 10
    neighbor = _server_after_get_and_200([("Content-Length", str(n))])
    full = length_placeholder(n)
    require_passthrough_pieces(passthrough_send(neighbor, make_data(full)))
    require_no_extra_bytes(send_event(neighbor, make_eom()))

    server = _server_after_get_and_200([("Content-Length", str(n))])
    short = length_placeholder(n - 3)
    pieces = require_passthrough_pieces(
        passthrough_send(server, make_data(short))
    )
    assert any(item is short for item in pieces)
    early = send_event(server, make_eom())
    print(
        f"short placeholder EOM exc="
        f"{type(early.exception).__name__ if early.exception else None}",
        flush=True,
    )
    require_local_refusal(early)


def test_passthrough_chunked_keeps_placeholder_among_framing():
    server = _server_after_get_and_200([("Transfer-Encoding", "chunked")])
    placeholder = length_placeholder(10)
    pieces = require_passthrough_pieces(
        passthrough_send(server, make_data(placeholder))
    )
    print(f"chunked passthrough n={len(pieces)}", flush=True)
    assert any(item is placeholder for item in pieces)
    extras = [item for item in pieces if item is not placeholder]
    assert extras, "chunked passthrough sequence has no framing pieces"
    joined = substitute_placeholder(pieces, placeholder, b"x" * 10)
    client = client_connection()
    require_send_bytes(
        send_event(client, make_request(headers=[("Host", "example.com")]))
    )
    require_no_extra_bytes(send_event(client, make_eom()))
    peer_server, _ = server_after_empty_get(version=b"1.1")
    resp_bytes = require_send_bytes(
        send_event(
            peer_server,
            make_response(200, headers=[("Transfer-Encoding", "chunked")]),
        )
    )
    feed_ok(client, resp_bytes + joined)
    pull_kind(client, "response")
    data = pull_kind(client, "data")
    assert payload_as_bytes(data) == b"x" * 10


def test_passthrough_http10_is_only_placeholder():
    server = _server_after_get_and_200([], version=b"1.0")
    placeholder = length_placeholder(10)
    pieces = require_passthrough_pieces(
        passthrough_send(server, make_data(placeholder))
    )
    print(f"http10 passthrough pieces={pieces!r}", flush=True)
    assert pieces == (placeholder,)
    assert pieces[0] is placeholder


def test_runtime_passthrough_placeholder_identity():
    n = runtime_body_n()
    server = _server_after_get_and_200([("Content-Length", str(n))])
    placeholder = length_placeholder(n)
    pieces = require_passthrough_pieces(
        passthrough_send(server, make_data(placeholder))
    )
    assert pieces == (placeholder,)
    require_no_extra_bytes(send_event(server, make_eom()))

    short_n = n + 4
    short_server = _server_after_get_and_200([("Content-Length", str(short_n))])
    short = length_placeholder(n)
    require_passthrough_pieces(passthrough_send(short_server, make_data(short)))
    require_local_refusal(send_event(short_server, make_eom()))

    chunked = _server_after_get_and_200([("Transfer-Encoding", "chunked")])
    xs = length_placeholder(n)
    chunk_pieces = require_passthrough_pieces(
        passthrough_send(chunked, make_data(xs))
    )
    assert any(item is xs for item in chunk_pieces)
    extras = [item for item in chunk_pieces if item is not xs]
    assert extras
    joined = substitute_placeholder(chunk_pieces, xs, b"x" * n)
    client = client_connection()
    require_send_bytes(
        send_event(client, make_request(headers=[("Host", "example.com")]))
    )
    require_no_extra_bytes(send_event(client, make_eom()))
    peer, _ = server_after_empty_get(version=b"1.1")
    resp = require_send_bytes(
        send_event(
            peer, make_response(200, headers=[("Transfer-Encoding", "chunked")])
        )
    )
    feed_ok(client, resp + joined)
    pull_kind(client, "response")
    assert payload_as_bytes(pull_kind(client, "data")) == b"x" * n


# ---------------------------------------------------------------------------
# K. Local protocol errors: CL extra / short / illegal trailers
# ---------------------------------------------------------------------------


def test_data_exceeding_content_length_is_local_error():
    neighbor = client_connection()
    require_send_bytes(
        send_event(
            neighbor,
            make_request(
                headers=[("Host", "example.com"), ("Content-Length", "10")]
            ),
        )
    )
    require_send_bytes(send_event(neighbor, make_data(b"1234567890")))
    neighbor_eom = require_no_extra_bytes(send_event(neighbor, make_eom()))
    assert neighbor_eom == b""

    client = client_connection()
    require_send_bytes(
        send_event(
            client,
            make_request(
                headers=[("Host", "example.com"), ("Content-Length", "10")]
            ),
        )
    )
    require_send_bytes(send_event(client, make_data(b"12345")))
    extra = send_event(client, make_data(b"678901"))
    print(
        f"exceed CL exc={type(extra.exception).__name__ if extra.exception else None}",
        flush=True,
    )
    exc = require_local_refusal(extra)
    local_t = local_protocol_error_type()
    remote_t = remote_protocol_error_type()
    assert extra.exception is exc
    assert extra.value is None
    assert isinstance(exc, local_t)
    assert not isinstance(exc, remote_t)


def test_eom_before_content_length_satisfied_is_local_error():
    neighbor = client_connection()
    require_send_bytes(
        send_event(
            neighbor,
            make_request(
                headers=[("Host", "example.com"), ("Content-Length", "10")]
            ),
        )
    )
    require_send_bytes(send_event(neighbor, make_data(b"1234567890")))
    neighbor_eom = require_no_extra_bytes(send_event(neighbor, make_eom()))
    assert neighbor_eom == b""

    client = client_connection()
    require_send_bytes(
        send_event(
            client,
            make_request(
                headers=[("Host", "example.com"), ("Content-Length", "10")]
            ),
        )
    )
    require_send_bytes(send_event(client, make_data(b"12345")))
    early = send_event(client, make_eom())
    print(
        f"short CL EOM exc={type(early.exception).__name__ if early.exception else None}",
        flush=True,
    )
    exc = require_local_refusal(early)
    local_t = local_protocol_error_type()
    remote_t = remote_protocol_error_type()
    assert early.exception is exc
    assert early.value is None
    assert isinstance(exc, local_t)
    assert not isinstance(exc, remote_t)


def test_response_data_exceeding_content_length_is_local_error():
    neighbor, _ = server_after_empty_get()
    require_send_bytes(
        send_event(neighbor, make_response(200, headers=[("Content-Length", "10")]))
    )
    require_send_bytes(send_event(neighbor, make_data(b"1234567890")))
    neighbor_eom = require_no_extra_bytes(send_event(neighbor, make_eom()))
    assert neighbor_eom == b""

    server, _ = server_after_empty_get()
    require_send_bytes(
        send_event(server, make_response(200, headers=[("Content-Length", "10")]))
    )
    require_send_bytes(send_event(server, make_data(b"12345")))
    extra = send_event(server, make_data(b"678901"))
    print(
        f"response exceed CL exc="
        f"{type(extra.exception).__name__ if extra.exception else None}",
        flush=True,
    )
    exc = require_local_refusal(extra)
    local_t = local_protocol_error_type()
    remote_t = remote_protocol_error_type()
    assert extra.exception is exc
    assert extra.value is None
    assert isinstance(exc, local_t)
    assert not isinstance(exc, remote_t)


def test_response_eom_before_content_length_satisfied_is_local_error():
    neighbor, _ = server_after_empty_get()
    require_send_bytes(
        send_event(neighbor, make_response(200, headers=[("Content-Length", "10")]))
    )
    require_send_bytes(send_event(neighbor, make_data(b"1234567890")))
    neighbor_eom = require_no_extra_bytes(send_event(neighbor, make_eom()))
    assert neighbor_eom == b""

    server, _ = server_after_empty_get()
    require_send_bytes(
        send_event(server, make_response(200, headers=[("Content-Length", "10")]))
    )
    require_send_bytes(send_event(server, make_data(b"12345")))
    early = send_event(server, make_eom())
    print(
        f"response short CL EOM exc="
        f"{type(early.exception).__name__ if early.exception else None}",
        flush=True,
    )
    exc = require_local_refusal(early)
    local_t = local_protocol_error_type()
    remote_t = remote_protocol_error_type()
    assert early.exception is exc
    assert early.value is None
    assert isinstance(exc, local_t)
    assert not isinstance(exc, remote_t)


def test_trailers_on_content_length_are_local_error():
    neighbor = client_connection()
    require_send_bytes(
        send_event(
            neighbor,
            make_request(
                headers=[("Host", "example.com"), ("Content-Length", "10")]
            ),
        )
    )
    require_send_bytes(send_event(neighbor, make_data(b"1234567890")))
    neighbor_eom = require_no_extra_bytes(send_event(neighbor, make_eom()))
    assert neighbor_eom == b""

    client = client_connection()
    require_send_bytes(
        send_event(
            client,
            make_request(
                headers=[("Host", "example.com"), ("Content-Length", "10")]
            ),
        )
    )
    require_send_bytes(send_event(client, make_data(b"1234567890")))
    trailed = send_event(client, make_eom_with([("hello", "there")]))
    print(
        f"CL trailer exc={type(trailed.exception).__name__ if trailed.exception else None}",
        flush=True,
    )
    exc = require_local_refusal(trailed)
    local_t = local_protocol_error_type()
    remote_t = remote_protocol_error_type()
    assert trailed.exception is exc
    assert trailed.value is None
    assert isinstance(exc, local_t)
    assert not isinstance(exc, remote_t)


def test_trailers_on_http10_close_delimited_are_local_error():
    neighbor, _ = server_after_empty_get(version=b"1.0")
    require_send_bytes(send_event(neighbor, make_response(200, headers=[])))
    require_send_bytes(send_event(neighbor, make_data(b"12345")))
    neighbor_eom = require_no_extra_bytes(send_event(neighbor, make_eom()))
    assert neighbor_eom == b""

    server, _ = server_after_empty_get(version=b"1.0")
    require_send_bytes(send_event(server, make_response(200, headers=[])))
    require_send_bytes(send_event(server, make_data(b"12345")))
    trailed = send_event(server, make_eom_with([("hello", "there")]))
    print(
        f"http10 trailer exc="
        f"{type(trailed.exception).__name__ if trailed.exception else None}",
        flush=True,
    )
    exc = require_local_refusal(trailed)
    local_t = local_protocol_error_type()
    remote_t = remote_protocol_error_type()
    assert trailed.exception is exc
    assert trailed.value is None
    assert isinstance(exc, local_t)
    assert not isinstance(exc, remote_t)


def test_trailers_to_http10_peer_refused_even_if_caller_asked_chunked():
    neighbor, _ = server_after_empty_get(version=b"1.0")
    require_send_bytes(
        send_event(
            neighbor,
            make_response(200, headers=[("Transfer-Encoding", "chunked")]),
        )
    )
    require_send_bytes(send_event(neighbor, make_data(b"12345")))
    neighbor_eom = require_no_extra_bytes(send_event(neighbor, make_eom()))
    assert neighbor_eom == b""

    server, _ = server_after_empty_get(version=b"1.0")
    resp = require_send_bytes(
        send_event(
            server,
            make_response(200, headers=[("Transfer-Encoding", "chunked")]),
        )
    )
    require_no_wire_header(resp, b"Transfer-Encoding")
    assert not wire_has_header(resp, b"Transfer-Encoding")
    require_send_bytes(send_event(server, make_data(b"12345")))
    trailed = send_event(server, make_eom_with([("hello", "there")]))
    print(
        f"1.0 asked-chunked trailer exc="
        f"{type(trailed.exception).__name__ if trailed.exception else None}",
        flush=True,
    )
    exc = require_local_refusal(trailed)
    local_t = local_protocol_error_type()
    remote_t = remote_protocol_error_type()
    assert trailed.exception is exc
    assert trailed.value is None
    assert isinstance(exc, local_t)
    assert not isinstance(exc, remote_t)


# ---------------------------------------------------------------------------
# L. Remote protocol errors: bad chunk size / terminator
# ---------------------------------------------------------------------------


def test_chunk_size_longer_than_32_hex_digits_is_remote_error():
    neighbor = chunked_post_server()
    neighbor_hello_chunk(neighbor)

    server = chunked_post_server()
    feed_ok(server, b"1" * 33 + b"\r\n")
    result = pull_next(server)
    print(
        f"33-digit size exc={type(result.exception).__name__ if result.exception else None}",
        flush=True,
    )
    require_remote_refusal(result)
    assert result.value is None or not event_is_kind(result.value, "data")


def test_runtime_overlong_chunk_size_is_remote_error():
    neighbor = chunked_post_server()
    neighbor_hello_chunk(neighbor)
    n = 34 + (runtime_int() % 5)
    assert n > 32 and n != 33
    server = chunked_post_server()
    feed_ok(server, b"2" * n + b"\r\n")
    result = pull_next(server)
    print(f"runtime overlong n={n} refused={result.exception is not None}", flush=True)
    require_remote_refusal(result)


def test_two_digit_hex_chunk_size_is_accepted():
    payload = b"abcdefghijklmnop"
    assert len(payload) == 16
    server = chunked_post_server()
    feed_ok(server, b"10\r\n" + payload + b"\r\n")
    event = pull_kind(server, "data")
    print(f"size 10 payload={payload_as_bytes(event)!r}", flush=True)
    assert payload_as_bytes(event) == payload


def test_runtime_two_digit_hex_chunk_size_is_accepted():
    n = 17 + (runtime_int() % 14)
    hex_size = format(n, "x").encode("ascii")
    assert len(hex_size) == 2
    assert hex_size != b"10"
    payload = (runtime_token().encode("ascii") * 8)[:n]
    server = chunked_post_server()
    feed_ok(server, hex_size + b"\r\n" + payload + b"\r\n")
    event = pull_kind(server, "data")
    print(f"runtime two-digit size={hex_size!r} n={n}", flush=True)
    assert payload_as_bytes(event) == payload


def test_chunk_size_containing_nul_is_remote_error():
    neighbor = chunked_post_server()
    neighbor_hello_chunk(neighbor)
    server = chunked_post_server()
    feed_ok(server, b"5\x00\r\nxxxxx")
    result = pull_next(server)
    print(
        f"NUL size exc={type(result.exception).__name__ if result.exception else None}",
        flush=True,
    )
    require_remote_refusal(result)
    assert result.value is None or not event_is_kind(result.value, "data")


def test_chunk_size_3_not_followed_by_crlf_is_remote_error():
    neighbor = chunked_post_server()
    feed_ok(neighbor, b"3\r\nxxx\r\n")
    ok = pull_kind(neighbor, "data")
    assert payload_letters(data_payload(ok)) == "xxx"

    for label, blob in (
        ("xx", b"3\r\nxxx__"),
        ("cr_underscore", b"3\r\nxxx\r_"),
        ("underscore_lf", b"3\r\nxxx_\n"),
    ):
        server = chunked_post_server()
        feed_ok(server, blob)
        print(f"bad terminator {label} pulling until remote refusal", flush=True)
        pull_until_remote_refusal(server)
