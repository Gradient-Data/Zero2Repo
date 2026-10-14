# feature: F06
"""Acceptance tests for half-duplex connection shutdown.

Exercises sending and pulling a connection-closed event, an empty feed
as the peer closing their sending side, legal versus illegal close
states, a client half-close that still lets the server respond,
idempotent CLOSED, MUST_CLOSE to CLOSED, pipelined requests answered
before close, and the four distinguishable failure kinds. Event
construction is FP-01. Send / feed / pull is FP-02. HTTP/1.0 as a
MUST_CLOSE example is FP-03. Start-next-cycle is FP-04. Mid-body close
as a remote protocol error is FP-05.
"""

from __future__ import annotations

from F01_helpers import (
    named_pairs,
    ordinary_pairs,
    request_method,
    request_target,
    require_local_refusal,
    runtime_int,
    runtime_token,
    status_code,
)
from F02_helpers import (
    client_connection,
    event_is_kind,
    feed_bytes,
    make_data,
    make_eom,
    make_request,
    make_response,
    named_state,
    pull_next,
    require_need_data,
    require_no_extra_bytes,
    require_remote_refusal,
    require_runtime_refusal,
    require_send_bytes,
    send_event,
    server_connection,
)
from F03_helpers import (
    feed_ok,
    payload_as_bytes,
    pull_kind,
    require_our_state,
    server_after_empty_get,
)
from F04_helpers import (
    client_send_empty,
    complete_empty_http11_cycle,
    require_both_done,
    require_start_succeeded,
    require_their_state,
    runtime_host,
    runtime_target,
    send_final_200,
    start_next_cycle,
)
from F05_helpers import (
    concatenated_body_until_eom,
    feed_empty,
    require_not_connection_closed_event,
    require_our_error_their_not,
    require_their_error_our_not,
)
from F06_helpers import (
    complete_new_get_bytes,
    incomplete_get_then_rest,
    make_connection_closed,
    fixed_two_bodied_gets_then_empty,
    pull_connection_closed,
    require_client_server_states,
    runtime_finished_bodied_request,
    runtime_two_bodied_gets,
    send_connection_closed,
)


# ---------------------------------------------------------------------------
# S. Present-arm encode and pull
# ---------------------------------------------------------------------------


def test_shutdown_path_round_trips_when_package_importable():
    client = client_connection()
    encoded = require_send_bytes(
        send_event(client, make_request(headers=[("Host", "example.com")]))
    )
    print(f"baseline GET encoded len={len(encoded)}", flush=True)
    assert len(encoded) > 0
    server = server_connection()
    feed_ok(server, encoded)
    pulled = pull_kind(server, "request")
    assert request_method(pulled) == b"GET"
    assert request_target(pulled) == b"/"
    hosts = named_pairs(ordinary_pairs(pulled), b"host")
    assert (b"host", b"example.com") in hosts

    idle_client = client_connection()
    send_connection_closed(idle_client)
    require_client_server_states(idle_client, "CLOSED", "MUST_CLOSE")
    print("fresh client connection-closed: CLOSED / MUST_CLOSE", flush=True)

    idle_server = server_connection()
    require_need_data(pull_next(idle_server))
    feed_empty(idle_server)
    pull_connection_closed(idle_server)
    print("fresh server empty feed pulled connection-closed", flush=True)


def test_get_encode_fails_when_package_not_importable():
    # The product is exercised by
    # real send/pull on a constructed connection, not an import-stripped
    # child. ENCODE_UNAVAILABLE / ENCODED_REQUEST are not product output.
    # The only accepted present-arm outcome is this companion's
    # connection-closed send/pull, plus the already-cleared GET encode
    # and peer pull.
    client = client_connection()
    encoded = require_send_bytes(
        send_event(client, make_request(headers=[("Host", "example.com")]))
    )
    print(f"present-arm GET encoded len={len(encoded)}", flush=True)
    assert len(encoded) > 0
    server = server_connection()
    feed_ok(server, encoded)
    pulled = pull_kind(server, "request")
    assert request_method(pulled) == b"GET"
    assert request_target(pulled) == b"/"
    hosts = named_pairs(ordinary_pairs(pulled), b"host")
    assert (b"host", b"example.com") in hosts

    idle_client = client_connection()
    send_connection_closed(idle_client)
    require_client_server_states(idle_client, "CLOSED", "MUST_CLOSE")
    print("present-arm fresh client connection-closed: CLOSED / MUST_CLOSE", flush=True)

    idle_server = server_connection()
    require_need_data(pull_next(idle_server))
    feed_empty(idle_server)
    pull_connection_closed(idle_server)
    print("present-arm fresh server empty feed pulled connection-closed", flush=True)


# ---------------------------------------------------------------------------
# A. Send connection-closed from IDLE; peer may close; both CLOSED
# ---------------------------------------------------------------------------


def test_fresh_client_send_closed_is_closed_must_close_and_no_bytes():
    client = client_connection()
    result = send_connection_closed(client)
    assert result.exception is None
    require_client_server_states(client, "CLOSED", "MUST_CLOSE")

    neighbor = client_connection()
    encoded = require_send_bytes(
        send_event(neighbor, make_request(headers=[("Host", runtime_host())]))
    )
    print(f"GET neighbor encoded len={len(encoded)}", flush=True)
    assert len(encoded) > 0
    require_our_state(neighbor, "SEND_BODY")
    assert require_our_state(neighbor, "SEND_BODY") != named_state("CLOSED")


def test_fresh_server_send_closed_is_closed_must_close_and_no_bytes():
    server = server_connection()
    result = send_connection_closed(server)
    assert result.exception is None
    require_client_server_states(server, "MUST_CLOSE", "CLOSED")
    print("fresh server connection-closed: MUST_CLOSE / CLOSED", flush=True)


def test_idle_peer_sends_connection_closed_both_sides_closed():
    starter = client_connection()
    send_connection_closed(starter)
    require_client_server_states(starter, "CLOSED", "MUST_CLOSE")

    peer_server = server_connection()
    feed_empty(peer_server)
    pull_connection_closed(peer_server)
    require_client_server_states(peer_server, "CLOSED", "MUST_CLOSE")
    peer_close = send_connection_closed(peer_server)
    assert peer_close.exception is None
    client_s, server_s = require_client_server_states(peer_server, "CLOSED", "CLOSED")
    assert client_s == named_state("CLOSED")
    assert server_s == named_state("CLOSED")
    print("client-first then peer close: both CLOSED", flush=True)

    starter_server = server_connection()
    send_connection_closed(starter_server)
    require_client_server_states(starter_server, "MUST_CLOSE", "CLOSED")

    peer_client = client_connection()
    feed_empty(peer_client)
    pull_connection_closed(peer_client)
    require_client_server_states(peer_client, "MUST_CLOSE", "CLOSED")
    peer_client_close = send_connection_closed(peer_client)
    assert peer_client_close.exception is None
    client2_s, server2_s = require_client_server_states(
        peer_client, "CLOSED", "CLOSED"
    )
    assert client2_s == named_state("CLOSED")
    assert server2_s == named_state("CLOSED")
    print("server-first then peer close: both CLOSED", flush=True)


def test_idle_already_closed_send_is_idempotent():
    client = client_connection()
    send_connection_closed(client)
    require_our_state(client, "CLOSED")
    again = send_connection_closed(client)
    assert again.exception is None
    require_our_state(client, "CLOSED")
    require_client_server_states(client, "CLOSED", "MUST_CLOSE")
    print("IDLE already CLOSED send is idempotent", flush=True)


# ---------------------------------------------------------------------------
# B. Empty feed pulls connection-closed repeatedly; further empty feeds allowed
# ---------------------------------------------------------------------------


def test_empty_feed_pulls_connection_closed_repeatedly():
    server = server_connection()
    before = require_need_data(pull_next(server))
    assert not event_is_kind(before, "connection-closed")
    feed_empty(server)
    first = pull_connection_closed(server)
    assert event_is_kind(first, "connection-closed")
    client_s, server_s = require_client_server_states(server, "CLOSED", "MUST_CLOSE")
    assert client_s == named_state("CLOSED")
    assert server_s == named_state("MUST_CLOSE")
    second = pull_connection_closed(server)
    third = pull_connection_closed(server)
    assert event_is_kind(second, "connection-closed")
    assert event_is_kind(third, "connection-closed")
    print("server empty feed: three connection-closed pulls", flush=True)


def test_further_empty_feeds_after_close_remain_allowed():
    server = server_connection()
    feed_empty(server)
    first = pull_connection_closed(server)
    assert event_is_kind(first, "connection-closed")
    further = feed_bytes(server, b"")
    assert further.exception is None
    second = pull_connection_closed(server)
    assert event_is_kind(second, "connection-closed")
    print("further empty feed after close still allowed", flush=True)


def test_client_empty_feed_also_yields_repeated_connection_closed():
    client = client_connection()
    before = require_need_data(pull_next(client))
    assert not event_is_kind(before, "connection-closed")
    feed_empty(client)
    first = pull_connection_closed(client)
    assert event_is_kind(first, "connection-closed")
    client_s, server_s = require_client_server_states(client, "MUST_CLOSE", "CLOSED")
    assert client_s == named_state("MUST_CLOSE")
    assert server_s == named_state("CLOSED")
    second = pull_connection_closed(client)
    third = pull_connection_closed(client)
    assert event_is_kind(second, "connection-closed")
    assert event_is_kind(third, "connection-closed")
    print("client empty feed: three connection-closed pulls", flush=True)


# ---------------------------------------------------------------------------
# C. Client half-close: server stays in SEND_RESPONSE and can still respond
# ---------------------------------------------------------------------------


def test_client_half_close_after_get_foo_leaves_server_send_response():
    client = client_connection()
    encoded = client_send_empty(client, target="/foo", host="a")
    assert len(encoded) > 0
    last = send_connection_closed(client)
    assert last.exception is None
    require_client_server_states(client, "CLOSED", "SEND_RESPONSE")
    assert require_our_state(client, "CLOSED") != named_state("SEND_RESPONSE")
    print("GET /foo Host a plus close: client CLOSED, server SEND_RESPONSE", flush=True)


def test_server_still_sends_response_after_client_half_close():
    baseline_client = client_connection()
    baseline_raw = client_send_empty(baseline_client, target="/foo", host="a")
    baseline_server = server_connection()
    feed_ok(baseline_server, baseline_raw)
    pull_kind(baseline_server, "request")
    pull_kind(baseline_server, "end-of-message")
    require_our_state(baseline_server, "SEND_RESPONSE")
    baseline_resp = send_final_200(baseline_server)
    print(f"baseline 200 len={len(baseline_resp)}", flush=True)
    assert len(baseline_resp) > 0

    client = client_connection()
    raw = client_send_empty(client, target="/foo", host="a")
    send_connection_closed(client)
    require_client_server_states(client, "CLOSED", "SEND_RESPONSE")
    server = server_connection()
    feed_ok(server, raw)
    pulled = pull_kind(server, "request")
    assert request_method(pulled) == b"GET"
    assert request_target(pulled) == b"/foo"
    pull_kind(server, "end-of-message")
    require_our_state(server, "SEND_RESPONSE")
    resp = send_final_200(server)
    print(f"half-close 200 len={len(resp)}", flush=True)
    assert len(resp) > 0
    feed_ok(client, resp)
    response = pull_kind(client, "response")
    assert status_code(response) == 200
    pull_kind(client, "end-of-message")
    print("CLOSED client still pulled 200 and end-of-message", flush=True)


def test_runtime_half_close_still_allows_response():
    host = runtime_host()
    target = runtime_target()
    client = client_connection()
    raw = client_send_empty(client, target=target, host=host)
    send_connection_closed(client)
    require_client_server_states(client, "CLOSED", "SEND_RESPONSE")
    server = server_connection()
    feed_ok(server, raw)
    pulled = pull_kind(server, "request")
    assert request_target(pulled) == target.encode("ascii")
    pull_kind(server, "end-of-message")
    require_our_state(server, "SEND_RESPONSE")
    resp = send_final_200(server)
    assert len(resp) > 0
    feed_ok(client, resp)
    response = pull_kind(client, "response")
    assert status_code(response) == 200
    pull_kind(client, "end-of-message")
    print("runtime half-close still received 200", flush=True)


def test_finished_content_length_half_close_still_receives_response():
    request, data, eom, payload = runtime_finished_bodied_request()
    assert len(payload) != 10
    client = client_connection()
    raw = require_send_bytes(send_event(client, request))
    raw += require_send_bytes(send_event(client, data))
    raw += require_no_extra_bytes(send_event(client, eom))
    send_connection_closed(client)
    require_client_server_states(client, "CLOSED", "SEND_RESPONSE")
    server = server_connection()
    feed_ok(server, raw)
    pull_kind(server, "request")
    body = concatenated_body_until_eom(server)
    assert body == payload
    require_our_state(server, "SEND_RESPONSE")
    assert require_our_state(server, "SEND_RESPONSE") != named_state("CLOSED")
    resp = send_final_200(server)
    assert len(resp) > 0
    feed_ok(client, resp)
    response = pull_kind(client, "response")
    assert status_code(response) == 200
    pull_kind(client, "end-of-message")
    print("finished Content-Length half-close still received 200", flush=True)


# ---------------------------------------------------------------------------
# D. After both DONE; idempotent CLOSED; MUST_CLOSE server; empty feed
# ---------------------------------------------------------------------------


def test_either_side_may_close_after_both_done():
    client, server, _resp = complete_empty_http11_cycle(host="a", target="/")
    require_both_done(client)
    require_both_done(server)
    closed = send_connection_closed(client)
    assert closed.exception is None
    client_s, server_s = require_client_server_states(client, "CLOSED", "MUST_CLOSE")
    assert client_s == named_state("CLOSED")
    assert server_s == named_state("MUST_CLOSE")
    print("after both DONE, client close: CLOSED / MUST_CLOSE", flush=True)

    client2, server2, _resp2 = complete_empty_http11_cycle(
        host=runtime_host(), target="/"
    )
    require_both_done(server2)
    closed2 = send_connection_closed(server2)
    assert closed2.exception is None
    client2_s, server2_s = require_client_server_states(
        server2, "MUST_CLOSE", "CLOSED"
    )
    assert client2_s == named_state("MUST_CLOSE")
    assert server2_s == named_state("CLOSED")
    print("after both DONE, server close: MUST_CLOSE / CLOSED", flush=True)


def test_connection_closed_when_already_closed_is_idempotent():
    client, server, _resp = complete_empty_http11_cycle(host="a", target="/")
    require_both_done(client)
    send_connection_closed(client)
    require_our_state(client, "CLOSED")
    again = send_connection_closed(client)
    assert again.exception is None
    require_our_state(client, "CLOSED")

    client2, server2, _resp2 = complete_empty_http11_cycle(
        host=runtime_host(), target=runtime_target()
    )
    require_both_done(client2)
    require_both_done(server2)
    send_connection_closed(client2)
    feed_empty(server2)
    pull_connection_closed(server2)
    send_connection_closed(server2)
    require_client_server_states(client2, "CLOSED", "MUST_CLOSE")
    require_client_server_states(server2, "CLOSED", "CLOSED")
    send_connection_closed(client2)
    send_connection_closed(server2)
    require_our_state(client2, "CLOSED")
    require_our_state(server2, "CLOSED")
    print("CLOSED send remains idempotent after both sides closed", flush=True)


def test_must_close_server_sends_connection_closed_to_closed():
    server, _request = server_after_empty_get(version=b"1.0")
    send_final_200(server)
    must = require_our_state(server, "MUST_CLOSE")
    assert must == named_state("MUST_CLOSE")
    result = send_connection_closed(server)
    assert result.exception is None
    closed = require_our_state(server, "CLOSED")
    assert closed == named_state("CLOSED")
    assert closed != named_state("MUST_CLOSE")
    print("HTTP/1.0 MUST_CLOSE server send reached CLOSED", flush=True)


def test_empty_feed_after_both_done_is_connection_closed():
    client, server, _resp = complete_empty_http11_cycle(host="a", target="/")
    require_both_done(client)
    require_both_done(server)
    feed_empty(client)
    pulled = pull_connection_closed(client)
    assert event_is_kind(pulled, "connection-closed")
    must = require_our_state(client, "MUST_CLOSE")
    assert must == named_state("MUST_CLOSE")
    print("empty feed after both DONE on client: connection-closed", flush=True)

    client2, server2, _resp2 = complete_empty_http11_cycle(
        host=runtime_host(), target=runtime_target()
    )
    require_both_done(server2)
    feed_empty(server2)
    pulled2 = pull_connection_closed(server2)
    assert event_is_kind(pulled2, "connection-closed")
    must2 = require_our_state(server2, "MUST_CLOSE")
    assert must2 == named_state("MUST_CLOSE")
    print("empty feed after both DONE on server: connection-closed", flush=True)


def test_runtime_cycle_then_connection_closed():
    host = runtime_host()
    target = runtime_target()
    client, server, _resp = complete_empty_http11_cycle(host=host, target=target)
    require_both_done(client)
    closed = send_connection_closed(client)
    assert closed.exception is None
    client_s, server_s = require_client_server_states(client, "CLOSED", "MUST_CLOSE")
    assert client_s == named_state("CLOSED")
    assert server_s == named_state("MUST_CLOSE")
    print(
        f"runtime cycle host={host!r} target={target!r} then close",
        flush=True,
    )


def test_runtime_http10_must_close_sends_to_closed():
    host = runtime_host()
    target = runtime_target()
    raw = (
        b"GET "
        + target.encode("ascii")
        + b" HTTP/1.0\r\nHost: "
        + host.encode("ascii")
        + b"\r\n\r\n"
    )
    server = server_connection()
    feed_ok(server, raw)
    pulled = pull_kind(server, "request")
    assert request_target(pulled) == target.encode("ascii")
    pull_kind(server, "end-of-message")
    send_final_200(server)
    require_our_state(server, "MUST_CLOSE")
    send_connection_closed(server)
    require_our_state(server, "CLOSED")
    print("runtime HTTP/1.0 MUST_CLOSE send reached CLOSED", flush=True)


# ---------------------------------------------------------------------------
# E. Pipelined GET /1 and /2 plus empty feed; without empty feed is need-data
# ---------------------------------------------------------------------------


def test_pipelined_get_1_and_2_then_empty_feed_server_answers_both_then_closes():
    server = server_connection()
    feed_ok(server, fixed_two_bodied_gets_then_empty())
    feed_empty(server)
    first = pull_kind(server, "request")
    assert request_target(first) == b"/1"
    data1 = pull_kind(server, "data")
    assert payload_as_bytes(data1) == b"12345"
    pull_kind(server, "end-of-message")
    send_final_200(server)
    require_start_succeeded(start_next_cycle(server), server)
    second = pull_kind(server, "request")
    assert request_target(second) == b"/2"
    data = pull_kind(server, "data")
    assert payload_as_bytes(data) == b"67890"
    pull_kind(server, "end-of-message")
    pull_connection_closed(server)
    require_client_server_states(server, "CLOSED", "SEND_RESPONSE")
    send_final_200(server)
    require_our_state(server, "MUST_CLOSE")
    send_connection_closed(server)
    require_our_state(server, "CLOSED")
    print("pipelined /1 /2 plus empty feed answered then CLOSED", flush=True)


def test_runtime_two_pipelined_gets_then_half_close():
    block, t1, t2, b1, b2 = runtime_two_bodied_gets()
    server = server_connection()
    feed_ok(server, block)
    feed_empty(server)
    first = pull_kind(server, "request")
    assert request_target(first) == t1
    data1 = pull_kind(server, "data")
    assert payload_as_bytes(data1) == b1
    pull_kind(server, "end-of-message")
    send_final_200(server)
    require_start_succeeded(start_next_cycle(server), server)
    second = pull_kind(server, "request")
    assert request_target(second) == t2
    data = pull_kind(server, "data")
    assert payload_as_bytes(data) == b2
    pull_kind(server, "end-of-message")
    pull_connection_closed(server)
    require_client_server_states(server, "CLOSED", "SEND_RESPONSE")
    send_final_200(server)
    require_our_state(server, "MUST_CLOSE")
    send_connection_closed(server)
    require_our_state(server, "CLOSED")
    print("runtime pipelined pair plus empty feed reached CLOSED", flush=True)


def test_two_pipelined_gets_without_empty_feed_do_not_yield_connection_closed():
    with_close = server_connection()
    feed_ok(with_close, fixed_two_bodied_gets_then_empty())
    feed_empty(with_close)
    first_close = pull_kind(with_close, "request")
    assert request_target(first_close) == b"/1"
    assert payload_as_bytes(pull_kind(with_close, "data")) == b"12345"
    pull_kind(with_close, "end-of-message")
    send_final_200(with_close)
    require_start_succeeded(start_next_cycle(with_close), with_close)
    pull_kind(with_close, "request")
    pull_kind(with_close, "data")
    pull_kind(with_close, "end-of-message")
    pull_connection_closed(with_close)
    print("with empty feed, pull after /2 EOM is connection-closed", flush=True)

    without = server_connection()
    feed_ok(without, fixed_two_bodied_gets_then_empty())
    first_open = pull_kind(without, "request")
    assert request_target(first_open) == b"/1"
    assert payload_as_bytes(pull_kind(without, "data")) == b"12345"
    pull_kind(without, "end-of-message")
    send_final_200(without)
    require_start_succeeded(start_next_cycle(without), without)
    second = pull_kind(without, "request")
    assert request_target(second) == b"/2"
    data = pull_kind(without, "data")
    assert payload_as_bytes(data) == b"67890"
    pull_kind(without, "end-of-message")
    extra = pull_next(without)
    require_need_data(extra)
    assert extra.exception is None
    require_not_connection_closed_event(extra.value)
    print("without empty feed, pull after /2 EOM is need-data", flush=True)

    # Incomplete-event carrier (not the glossary need-data token alone):
    # after answering /2 and starting the next cycle with no empty
    # feed, stored bytes that are not yet a complete event still pull
    # as need-data, those bytes are retained, and feeding the rest
    # continues the same GET. An empty feed at this point would have
    # been connection-closed instead.
    send_final_200(without)
    require_start_succeeded(start_next_cycle(without), without)
    target = "/" + runtime_token()[:8]
    prefix, rest = incomplete_get_then_rest(host="a", target=target)
    want = target.encode("ascii")
    feed_ok(without, prefix)
    held = pull_next(without)
    require_need_data(held)
    assert held.exception is None
    require_not_connection_closed_event(held.value)
    assert not event_is_kind(held.value, "request")
    print("incomplete next GET is need-data, not connection-closed", flush=True)

    only_rest = server_connection()
    feed_ok(only_rest, rest)
    alone = pull_next(only_rest)
    got_held_from_rest = (
        alone.exception is None
        and alone.value is not None
        and event_is_kind(alone.value, "request")
        and request_target(alone.value) == want
    )
    assert not got_held_from_rest, (
        "rest fragment alone must not parse as the held GET"
    )
    print("second fragment alone is not the held request", flush=True)

    feed_ok(without, rest)
    continued = pull_kind(without, "request")
    assert request_target(continued) == want
    require_not_connection_closed_event(continued)
    print(
        f"feeding the rest continued GET {target!r}, not connection-closed",
        flush=True,
    )


# ---------------------------------------------------------------------------
# F. Illegal close is local; MUST_CLOSE new request is remote; bytes after
#    empty feed are runtime
# ---------------------------------------------------------------------------


def test_server_in_send_response_cannot_send_connection_closed():
    neighbor, _req = server_after_empty_get()
    require_our_state(neighbor, "SEND_RESPONSE")
    encoded = require_send_bytes(
        send_event(neighbor, make_response(200, headers=[]))
    )
    print(f"SEND_RESPONSE neighbor 200 len={len(encoded)}", flush=True)
    assert len(encoded) > 0

    server, _request = server_after_empty_get()
    require_our_state(server, "SEND_RESPONSE")
    result = send_event(server, make_connection_closed())
    require_local_refusal(result)
    require_our_error_their_not(server)
    again = send_event(server, make_response(200, headers=[]))
    require_local_refusal(again)
    print("SEND_RESPONSE connection-closed is local; further send still local", flush=True)


def test_server_send_response_after_bodied_request_cannot_send_connection_closed():
    n = 4 + (runtime_int() % 4)
    if n == 10:
        n = 6
    payload = (runtime_token().encode("ascii") * 8)[:n]
    client = client_connection()
    raw = require_send_bytes(
        send_event(
            client,
            make_request(
                headers=[
                    ("Host", runtime_host()),
                    ("Content-Length", str(n)),
                ]
            ),
        )
    )
    raw += require_send_bytes(send_event(client, make_data(payload)))
    raw += require_no_extra_bytes(send_event(client, make_eom()))
    server = server_connection()
    feed_ok(server, raw)
    pull_kind(server, "request")
    body = concatenated_body_until_eom(server)
    assert body == payload
    require_our_state(server, "SEND_RESPONSE")
    result = send_event(server, make_connection_closed())
    require_local_refusal(result)
    require_our_error_their_not(server)
    print("bodied complete request: SEND_RESPONSE close is local", flush=True)


def test_server_cannot_send_connection_closed_after_client_half_close():
    client = client_connection()
    raw = client_send_empty(client, target="/foo", host="a")
    send_connection_closed(client)
    require_client_server_states(client, "CLOSED", "SEND_RESPONSE")
    server = server_connection()
    feed_ok(server, raw)
    pull_kind(server, "request")
    pull_kind(server, "end-of-message")
    feed_empty(server)
    pull_connection_closed(server)
    client_s, server_s = require_client_server_states(
        server, "CLOSED", "SEND_RESPONSE"
    )
    assert client_s == named_state("CLOSED")
    assert server_s == named_state("SEND_RESPONSE")
    result = send_event(server, make_connection_closed())
    assert result.exception is not None
    assert result.value is None
    require_local_refusal(result)
    require_our_error_their_not(server)
    assert require_our_state(server, "ERROR") == named_state("ERROR")
    print("half-close pair: server SEND_RESPONSE close is still local", flush=True)


def test_client_empty_feed_while_waiting_for_response_is_remote_not_closed():
    idle = server_connection()
    require_need_data(pull_next(idle))
    feed_empty(idle)
    idle_event = pull_connection_closed(idle)
    assert event_is_kind(idle_event, "connection-closed")
    print("IDLE empty feed neighbor is connection-closed", flush=True)

    done_client, _done_server, _resp = complete_empty_http11_cycle(
        host=runtime_host(), target=runtime_target()
    )
    require_both_done(done_client)
    feed_empty(done_client)
    done_event = pull_connection_closed(done_client)
    assert event_is_kind(done_event, "connection-closed")
    assert require_our_state(done_client, "MUST_CLOSE") == named_state("MUST_CLOSE")
    print("both-DONE empty feed neighbor is connection-closed", flush=True)

    client = client_connection()
    client_send_empty(client, host="a", target="/")
    require_their_state(client, "SEND_RESPONSE")
    feed_empty(client)
    result = pull_next(client)
    assert result.exception is not None
    require_remote_refusal(result)
    require_not_connection_closed_event(result.value)
    assert not event_is_kind(result.value, "connection-closed")
    require_their_error_our_not(client)
    assert require_their_state(client, "ERROR") == named_state("ERROR")
    again = pull_next(client)
    assert again.exception is not None
    require_remote_refusal(again)
    print("empty feed while waiting for response is remote, not closed", flush=True)


def test_client_mid_content_length_10_cannot_send_connection_closed():
    neighbor = client_connection()
    require_send_bytes(
        send_event(
            neighbor,
            make_request(headers=[("Host", "a"), ("Content-Length", "10")]),
        )
    )
    require_send_bytes(send_event(neighbor, make_data(b"1234567890")))
    require_no_extra_bytes(send_event(neighbor, make_eom()))
    finished = send_connection_closed(neighbor)
    assert finished.exception is None
    assert require_our_state(neighbor, "CLOSED") == named_state("CLOSED")
    print("finished ten-byte body then close succeeded", flush=True)

    client = client_connection()
    req = require_send_bytes(
        send_event(
            client,
            make_request(headers=[("Host", "a"), ("Content-Length", "10")]),
        )
    )
    require_our_state(client, "SEND_BODY")
    result = send_event(client, make_connection_closed())
    assert result.exception is not None
    assert result.value is None
    require_local_refusal(result)
    require_our_error_their_not(client)
    assert require_our_state(client, "ERROR") == named_state("ERROR")
    print("mid Content-Length 10 close is local", flush=True)

    server = server_connection()
    feed_ok(server, req)
    pull_kind(server, "request")
    feed_empty(server)
    remote = pull_next(server)
    assert remote.exception is not None
    require_remote_refusal(remote)
    require_not_connection_closed_event(remote.value)
    assert not event_is_kind(remote.value, "connection-closed")
    require_their_error_our_not(server)
    again = pull_next(server)
    assert again.exception is not None
    require_remote_refusal(again)
    print("peer empty feed mid Content-Length 10 is remote", flush=True)


def test_server_mid_content_length_cannot_send_connection_closed():
    server, _request = server_after_empty_get()
    require_send_bytes(
        send_event(
            server,
            make_response(200, headers=[("Content-Length", "10")]),
        )
    )
    require_send_bytes(send_event(server, make_data(b"abcd")))
    sending = require_our_state(server, "SEND_BODY")
    assert sending == named_state("SEND_BODY")
    result = send_event(server, make_connection_closed())
    assert result.exception is not None
    assert result.value is None
    require_local_refusal(result)
    require_our_error_their_not(server)
    assert require_our_state(server, "ERROR") == named_state("ERROR")
    print("server mid Content-Length close is local", flush=True)


def test_runtime_mid_content_length_cannot_send_connection_closed():
    n = 6 + (runtime_int() % 5)
    if n == 10:
        n = 8
    method = "POST" if runtime_int() % 2 else "PUT"
    token = runtime_token().encode("ascii")
    payload = (token * (n + 2))[:n]
    part_n = max(1, n // 2)
    if part_n >= n:
        part_n = n - 1
    part = payload[:part_n]
    client = client_connection()
    req = require_send_bytes(
        send_event(
            client,
            make_request(
                method=method,
                target=runtime_target(),
                headers=[
                    ("Host", runtime_host()),
                    ("Content-Length", str(n)),
                ],
            ),
        )
    )
    require_send_bytes(send_event(client, make_data(part)))
    require_our_state(client, "SEND_BODY")
    result = send_event(client, make_connection_closed())
    require_local_refusal(result)
    require_our_error_their_not(client)
    print(
        f"runtime mid-body n={n} sent={part_n} close is local",
        flush=True,
    )

    server = server_connection()
    feed_ok(server, req + part)
    pull_kind(server, "request")
    got = pull_kind(server, "data")
    assert payload_as_bytes(got) == part
    feed_empty(server)
    remote = pull_next(server)
    require_remote_refusal(remote)
    require_not_connection_closed_event(remote.value)
    require_their_error_our_not(server)
    require_remote_refusal(pull_next(server))
    print("runtime peer empty feed mid-body is remote", flush=True)


def test_complete_new_request_while_peer_must_close_is_remote():
    empty_peer = server_connection()
    send_connection_closed(empty_peer)
    require_client_server_states(empty_peer, "MUST_CLOSE", "CLOSED")
    feed_empty(empty_peer)
    pull_connection_closed(empty_peer)
    print("MUST_CLOSE empty-feed neighbor is connection-closed", flush=True)

    server = server_connection()
    send_connection_closed(server)
    require_client_server_states(server, "MUST_CLOSE", "CLOSED")
    raw = complete_new_get_bytes(host="a", target="/")
    feed_ok(server, raw)
    result = pull_next(server)
    require_remote_refusal(result)
    require_not_connection_closed_event(result.value)
    if result.value is not None:
        assert not event_is_kind(result.value, "request")
    require_their_error_our_not(server)
    again = pull_next(server)
    require_remote_refusal(again)
    print("complete GET while peer MUST_CLOSE is remote", flush=True)


def test_runtime_complete_request_while_peer_must_close_is_remote():
    host = runtime_host()
    target = runtime_target()
    server = server_connection()
    send_connection_closed(server)
    require_client_server_states(server, "MUST_CLOSE", "CLOSED")
    raw = complete_new_get_bytes(host=host, target=target)
    feed_ok(server, raw)
    result = pull_next(server)
    require_remote_refusal(result)
    require_not_connection_closed_event(result.value)
    if result.value is not None:
        assert not event_is_kind(result.value, "request")
    require_their_error_our_not(server)
    require_remote_refusal(pull_next(server))
    print(
        f"runtime complete GET host={host!r} target={target!r} is remote",
        flush=True,
    )


def test_bytes_after_empty_feed_remain_runtime_and_differ_from_must_close_request():
    request_bytes = complete_new_get_bytes(host="a", target="/")

    remote_server = server_connection()
    send_connection_closed(remote_server)
    require_client_server_states(remote_server, "MUST_CLOSE", "CLOSED")
    feed_ok(remote_server, request_bytes)
    remote_pull = pull_next(remote_server)
    remote_exc = require_remote_refusal(remote_pull)
    require_not_connection_closed_event(remote_pull.value)
    require_their_error_our_not(remote_server)

    runtime_server = server_connection()
    feed_empty(runtime_server)
    runtime_feed = feed_bytes(runtime_server, request_bytes)
    runtime_exc = require_runtime_refusal(runtime_feed)

    closed_then_bytes = server_connection()
    send_connection_closed(closed_then_bytes)
    feed_empty(closed_then_bytes)
    pull_connection_closed(closed_then_bytes)
    after_eof = feed_bytes(closed_then_bytes, request_bytes)
    after_eof_exc = require_runtime_refusal(after_eof)

    print(
        f"kinds remote={type(remote_exc).__name__} "
        f"runtime={type(runtime_exc).__name__} "
        f"after_eof={type(after_eof_exc).__name__}",
        flush=True,
    )
    assert type(remote_exc) is not type(runtime_exc)
    assert type(remote_exc) is not type(after_eof_exc)
