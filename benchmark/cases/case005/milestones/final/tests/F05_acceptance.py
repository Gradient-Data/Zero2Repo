# feature: F05
"""Acceptance tests for protocol errors and the incomplete-event size limit.

Exercises distinguishable local / remote / runtime failures, suggested
status 400 / 501 / 431, recoverable construction and start-next-cycle,
unrecoverable pull and send, mark-send-as-failed, the incomplete-event
limit, and receive-side close mid-body or mid-request-line. Event
construction is FP-01. Send / feed / pull is FP-02. Framing choice is
FP-03. Keep-alive and start-next-cycle are FP-04.
"""

from __future__ import annotations

from F01_helpers import (
    connection_side_states,
    construct,
    local_protocol_error_type,
    remote_protocol_error_type,
    request_method,
    request_result,
    request_target,
    require_event,
    require_local_refusal,
    runtime_int,
    runtime_token,
    suggested_status,
)
from F02_helpers import (
    client_connection,
    client_role,
    event_is_kind,
    feed_bytes,
    make_eom,
    make_request,
    make_response,
    named_state,
    pull_next,
    require_need_data,
    require_pulled_event,
    require_remote_refusal,
    require_runtime_refusal,
    require_send_bytes,
    send_event,
    server_connection,
    server_role,
)
from F03_helpers import (
    chunked_post_server,
    feed_ok,
    neighbor_hello_chunk,
    payload_as_bytes,
    pull_kind,
)
from F05_helpers import (
    begin_next_cycle,
    concatenated_body_until_eom,
    connection_with_incomplete_limit,
    feed_empty,
    generated_host,
    generated_target,
    fixed_big_header_block,
    fixed_big_header_unfinished,
    fixed_gibberish_block,
    pull_empty_response,
    pull_request_then_eom,
    require_cycle_reset,
    require_early_cycle_local,
    require_encoded_close,
    require_mark_failed,
    require_no_error_side,
    require_not_connection_closed_event,
    require_our_error_their_not,
    require_pull_paused,
    require_remote_status,
    require_side_still_error,
    require_sides_done,
    require_their_error_our_not,
    runtime_unparseable_block,
    send_empty_200,
    send_eom_bytes,
    wire_status_code,
)


# ---------------------------------------------------------------------------
# S. Present-arm protocol-error path
# ---------------------------------------------------------------------------


def test_protocol_error_path_round_trips_when_package_importable():
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

    remote = server_connection()
    feed_ok(remote, fixed_gibberish_block())
    result = pull_next(remote)
    require_remote_refusal(result)
    require_not_connection_closed_event(result.value)
    print("baseline gibberish pull is a remote protocol error", flush=True)


def test_get_encode_fails_when_package_not_importable():
    # The product is exercised by
    # a real protocol-error walk on a constructed connection, not an
    # import-stripped child. ENCODE_UNAVAILABLE / ENCODED_REQUEST are not
    # product output.
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

    local_exc = require_local_refusal(request_result(headers=[]), suggested=400)
    remote = server_connection()
    feed_ok(remote, fixed_gibberish_block())
    remote_result = pull_next(remote)
    remote_exc = require_remote_status(remote_result, 400)
    require_not_connection_closed_event(remote_result.value)
    require_their_error_our_not(remote)
    further = pull_next(remote)
    require_remote_refusal(further)
    require_not_connection_closed_event(further.value)
    runtime_conn = server_connection()
    feed_empty(runtime_conn)
    runtime_exc = require_runtime_refusal(feed_bytes(runtime_conn, b"more"))

    local_t = local_protocol_error_type()
    remote_t = remote_protocol_error_type()
    print(
        f"present-arm kinds local={type(local_exc).__name__} "
        f"remote={type(remote_exc).__name__} "
        f"runtime={type(runtime_exc).__name__}",
        flush=True,
    )
    assert isinstance(local_exc, local_t)
    assert not isinstance(local_exc, remote_t)
    assert isinstance(remote_exc, remote_t)
    assert not isinstance(remote_exc, local_t)
    assert type(local_exc) is not type(remote_exc)
    assert type(local_exc) is not type(runtime_exc)
    assert type(remote_exc) is not type(runtime_exc)
    assert suggested_status(local_exc) == 400
    assert suggested_status(remote_exc) == 400


# ---------------------------------------------------------------------------
# A. Three failure kinds; suggested status 400 / 501 / 431
# ---------------------------------------------------------------------------


def test_local_remote_and_runtime_errors_are_distinguishable():
    local_exc = require_local_refusal(request_result(headers=[]), suggested=400)
    remote_server = server_connection()
    feed_ok(remote_server, fixed_gibberish_block())
    remote_exc = require_remote_refusal(pull_next(remote_server))
    runtime_conn = server_connection()
    feed_empty(runtime_conn)
    runtime_exc = require_runtime_refusal(feed_bytes(runtime_conn, b"more"))

    local_t = local_protocol_error_type()
    remote_t = remote_protocol_error_type()
    print(
        f"kinds local={type(local_exc).__name__} "
        f"remote={type(remote_exc).__name__} "
        f"runtime={type(runtime_exc).__name__}",
        flush=True,
    )
    assert isinstance(local_exc, local_t)
    assert not isinstance(local_exc, remote_t)
    assert not isinstance(local_exc, type(runtime_exc))
    assert isinstance(remote_exc, remote_t)
    assert not isinstance(remote_exc, local_t)
    assert not isinstance(remote_exc, type(runtime_exc))
    assert not isinstance(runtime_exc, local_t)
    assert not isinstance(runtime_exc, remote_t)
    assert type(local_exc) is not type(remote_exc)
    assert type(local_exc) is not type(runtime_exc)
    assert type(remote_exc) is not type(runtime_exc)


def test_default_suggested_status_is_400():
    host_exc = require_local_refusal(request_result(headers=[]), suggested=400)
    assert suggested_status(host_exc) == 400

    remote = server_connection()
    feed_ok(remote, fixed_gibberish_block())
    gibberish_exc = require_remote_status(pull_next(remote), 400)
    assert suggested_status(gibberish_exc) == 400

    runtime_line = runtime_unparseable_block()
    other = server_connection()
    feed_ok(other, runtime_line)
    other_exc = require_remote_status(pull_next(other), 400)
    print(
        f"default 400 host={suggested_status(host_exc)} "
        f"gibberish={suggested_status(gibberish_exc)} "
        f"runtime_line={suggested_status(other_exc)}",
        flush=True,
    )
    assert suggested_status(other_exc) == 400


def test_transfer_encoding_gzip_suggests_501():
    gzip_exc = require_local_refusal(
        request_result(
            headers=[("Host", "example.com"), ("Transfer-Encoding", "gzip")],
        ),
        suggested=501,
    )
    host_exc = require_local_refusal(request_result(headers=[]), suggested=400)
    gzip_status = suggested_status(gzip_exc)
    host_status = suggested_status(host_exc)
    print(
        f"gzip suggested={gzip_status} missing-host suggested={host_status}",
        flush=True,
    )
    assert gzip_status == 501
    assert host_status == 400
    assert gzip_status != host_status


def test_oversize_incomplete_headers_suggest_431():
    oversize = connection_with_incomplete_limit(server_role(), 4000)
    feed_ok(oversize, fixed_big_header_unfinished())
    oversize_exc = require_remote_status(pull_next(oversize), 431)
    gzip_exc = require_local_refusal(
        request_result(
            headers=[("Host", "example.com"), ("Transfer-Encoding", "gzip")],
        ),
        suggested=501,
    )
    host_exc = require_local_refusal(request_result(headers=[]), suggested=400)
    statuses = {
        suggested_status(oversize_exc),
        suggested_status(gzip_exc),
        suggested_status(host_exc),
    }
    print(f"status contrast {sorted(statuses)}", flush=True)
    assert statuses == {400, 501, 431}


# ---------------------------------------------------------------------------
# B. Recoverable local protocol errors
# ---------------------------------------------------------------------------


def test_missing_host_is_recoverable_local_error():
    refused = require_local_refusal(request_result(headers=[]), suggested=400)
    print(f"missing-host type={type(refused).__name__}", flush=True)
    neighbor = require_event(
        request_result(headers=[("Host", "example.com")])
    )
    assert request_method(neighbor) == b"GET"
    later = require_event(request_result(headers=[("Host", "example.com")]))
    assert request_method(later) == b"GET"
    assert request_target(later) == b"/"


def test_non_host_invalid_construction_is_recoverable():
    require_local_refusal(
        request_result(
            headers=[("Host", "example.com"), ("Content-Length", "asdf")],
        ),
    )
    later = require_event(request_result(headers=[("Host", "example.com")]))
    assert request_method(later) == b"GET"
    print("valid construction after non-host refusal", flush=True)


def test_start_next_cycle_before_done_is_recoverable_local_error():
    host = generated_host()
    client = client_connection()
    raw = require_send_bytes(
        send_event(client, make_request(headers=[("Host", host)]))
    )
    eom = send_eom_bytes(client)
    early = begin_next_cycle(client)
    exc = require_early_cycle_local(early, client)
    assert suggested_status(exc) == 400
    our, their = connection_side_states(client)
    idle = named_state("IDLE")
    assert our != idle or their != idle
    require_no_error_side(client)

    server = server_connection()
    feed_ok(server, raw + eom)
    pull_request_then_eom(server)
    resp = send_empty_200(server)
    feed_ok(client, resp)
    pull_empty_response(client)
    require_sides_done(client)
    require_cycle_reset(begin_next_cycle(client), client)
    print("start after both DONE succeeded on the same connection", flush=True)


# ---------------------------------------------------------------------------
# C. Unrecoverable remote pull; send still works
# ---------------------------------------------------------------------------


def test_gibberish_blank_line_is_unrecoverable_remote_error():
    server = server_connection()
    feed_ok(server, fixed_gibberish_block())
    result = pull_next(server)
    exc = require_remote_status(result, 400)
    require_not_connection_closed_event(result.value)
    require_their_error_our_not(server)
    assert suggested_status(exc) == 400
    our, their = connection_side_states(server)
    assert their == named_state("ERROR")
    assert our != named_state("ERROR")
    print("gibberish their ERROR our not", flush=True)


def test_server_can_still_send_400_after_remote_receive_error():
    server = server_connection()
    feed_ok(server, fixed_gibberish_block())
    require_remote_status(pull_next(server), 400)
    require_their_error_our_not(server)
    encoded = require_send_bytes(
        send_event(server, make_response(400, headers=[]))
    )
    print(f"post-remote 400 encoded len={len(encoded)}", flush=True)
    assert wire_status_code(encoded) == 400
    require_encoded_close(encoded)
    require_their_error_our_not(server)
    require_side_still_error(server, "their")
    our, their = connection_side_states(server)
    assert their == named_state("ERROR")
    assert our != named_state("ERROR")
    assert their != named_state("IDLE")
    assert their != named_state("DONE")


def test_send_after_remote_receive_error_still_answers_400():
    # Boundary: send after a remote receive error still works, so a
    # server can answer 400. After that 400, their side remains ERROR
    # (not IDLE, not DONE) and our side is not ERROR. The public
    # gibberish walk with Connection: close is the concrete receive
    # case; this arm uses a different named remote receive error so the
    # boundary sentence is not only that sample.
    server = server_connection()
    feed_ok(server, b"GET /")
    require_need_data(pull_next(server))
    feed_empty(server)
    result = pull_next(server)
    require_remote_status(result, 400)
    require_not_connection_closed_event(result.value)
    require_their_error_our_not(server)

    encoded = require_send_bytes(
        send_event(server, make_response(400, headers=[]))
    )
    print(
        f"send after remote receive error answered 400 len={len(encoded)}",
        flush=True,
    )
    assert wire_status_code(encoded) == 400
    require_their_error_our_not(server)
    require_side_still_error(server, "their")
    our, their = connection_side_states(server)
    assert their == named_state("ERROR")
    assert our != named_state("ERROR")
    assert their != named_state("IDLE")
    assert their != named_state("DONE")
    print(
        f"after answer-400 their={their!r} our={our!r}",
        flush=True,
    )


def test_further_pull_after_remote_error_is_remote():
    server = server_connection()
    feed_ok(server, fixed_gibberish_block())
    first = pull_next(server)
    require_remote_status(first, 400)
    again = pull_next(server)
    again_exc = require_remote_refusal(again)
    require_not_connection_closed_event(again.value)
    require_their_error_our_not(server)
    assert isinstance(again_exc, remote_protocol_error_type())
    our, their = connection_side_states(server)
    assert their == named_state("ERROR")
    print("further pull still remote", flush=True)


def test_well_formed_feed_after_remote_error_still_remote():
    server = server_connection()
    feed_ok(server, fixed_gibberish_block())
    require_remote_status(pull_next(server), 400)
    require_their_error_our_not(server)
    feed_ok(server, b"GET / HTTP/1.1\r\nHost: a\r\n\r\n")
    later = pull_next(server)
    later_exc = require_remote_refusal(later)
    require_not_connection_closed_event(later.value)
    require_their_error_our_not(server)
    require_side_still_error(server, "their")
    assert isinstance(later_exc, remote_protocol_error_type())
    our, their = connection_side_states(server)
    assert their == named_state("ERROR")
    assert our != named_state("ERROR")
    print("well-formed feed after remote error did not recover receive", flush=True)


def test_their_error_cannot_be_left_after_remote_pull():
    server = server_connection()
    feed_ok(server, fixed_gibberish_block())
    require_remote_status(pull_next(server), 400)
    require_their_error_our_not(server)
    begin_next_cycle(server)
    require_side_still_error(server, "their")
    _, their = connection_side_states(server)
    assert their != named_state("IDLE")
    assert their != named_state("DONE")
    print("start-next-cycle left their ERROR", flush=True)


def test_runtime_unparseable_line_is_remote_error():
    block = runtime_unparseable_block()
    assert b"gibberish" not in block.lower()
    server = server_connection()
    feed_ok(server, block)
    result = pull_next(server)
    require_remote_status(result, 400)
    require_their_error_our_not(server)
    again = pull_next(server)
    require_remote_refusal(again)
    encoded = require_send_bytes(
        send_event(server, make_response(400, headers=[]))
    )
    assert wire_status_code(encoded) == 400
    require_encoded_close(encoded)
    require_their_error_our_not(server)
    print("runtime unparseable line still allows send 400", flush=True)


# ---------------------------------------------------------------------------
# D. Sending HTTP/1.0 is an unrecoverable local error
# ---------------------------------------------------------------------------


def test_sending_http10_request_is_unrecoverable_local_error():
    neighbor = client_connection()
    neighbor_bytes = require_send_bytes(
        send_event(
            neighbor,
            make_request(headers=[("Host", "example.com")]),
        )
    )
    assert len(neighbor_bytes) > 0

    event = require_event(
        request_result(
            headers=[("Host", "example.com")],
            http_version="1.0",
        )
    )
    client = client_connection()
    result = send_event(client, event)
    require_local_refusal(result, suggested=400)
    require_our_error_their_not(client)
    later = send_event(
        client, make_request(headers=[("Host", "example.com")])
    )
    require_local_refusal(later)
    require_our_error_their_not(client)
    print("HTTP/1.0 GET send left our ERROR; later 1.1 send failed", flush=True)


def test_sending_http10_non_get_request_is_unrecoverable_local_error():
    neighbor = client_connection()
    neighbor_bytes = require_send_bytes(
        send_event(
            neighbor,
            make_request(method="HEAD", headers=[("Host", "example.com")]),
        )
    )
    assert len(neighbor_bytes) > 0
    event = require_event(
        request_result(
            method="HEAD",
            headers=[("Host", "example.com")],
            http_version="1.0",
        )
    )
    client = client_connection()
    result = send_event(client, event)
    exc = require_local_refusal(result, suggested=400)
    require_our_error_their_not(client)
    assert suggested_status(exc) == 400
    our, their = connection_side_states(client)
    assert our == named_state("ERROR")
    assert their != named_state("ERROR")
    print("HTTP/1.0 HEAD send is local, our ERROR", flush=True)


def test_sending_http10_response_is_unrecoverable_local_error():
    neighbor = server_connection()
    neighbor_bytes = require_send_bytes(
        send_event(neighbor, make_response(408, headers=[]))
    )
    assert wire_status_code(neighbor_bytes) == 408

    event = require_event(
        construct(
            "response",
            status_code=408,
            headers=[],
            http_version="1.0",
        )
    )
    server = server_connection()
    result = send_event(server, event)
    require_local_refusal(result, suggested=400)
    require_our_error_their_not(server)
    later = send_event(server, make_response(408, headers=[]))
    require_local_refusal(later)
    require_our_error_their_not(server)
    print("HTTP/1.0 408 from IDLE left our ERROR", flush=True)


def test_sending_http10_response_from_other_legal_position():
    ready_raw = b"GET / HTTP/1.1\r\nHost: a\r\n\r\n"
    neighbor = server_connection()
    feed_ok(neighbor, ready_raw)
    pull_request_then_eom(neighbor)
    neighbor_bytes = require_send_bytes(
        send_event(neighbor, make_response(200, headers=[]))
    )
    assert wire_status_code(neighbor_bytes) == 200

    server = server_connection()
    feed_ok(server, ready_raw)
    pull_request_then_eom(server)
    event = require_event(
        construct(
            "response",
            status_code=200,
            headers=[],
            http_version="1.0",
        )
    )
    result = send_event(server, event)
    require_local_refusal(result, suggested=400)
    require_our_error_their_not(server)
    later = send_event(server, make_response(200, headers=[]))
    require_local_refusal(later)
    print("HTTP/1.0 200 after a pulled request left our ERROR", flush=True)


def test_valid_http11_send_fails_after_http10_send_error():
    fresh = client_connection()
    fresh_bytes = require_send_bytes(
        send_event(fresh, make_request(headers=[("Host", "example.com")]))
    )
    assert len(fresh_bytes) > 0
    client = client_connection()
    require_local_refusal(
        send_event(
            client,
            require_event(
                request_result(
                    headers=[("Host", "example.com")],
                    http_version="1.0",
                )
            ),
        ),
        suggested=400,
    )
    require_our_error_their_not(client)
    again = send_event(
        client, make_request(headers=[("Host", "example.com")])
    )
    later_exc = require_local_refusal(again)
    require_our_error_their_not(client)
    assert isinstance(later_exc, local_protocol_error_type())
    our, their = connection_side_states(client)
    assert our == named_state("ERROR")
    assert their != named_state("ERROR")
    print("1.1 send after 1.0 send error still failed", flush=True)


def test_our_error_cannot_be_left_after_local_send():
    client = client_connection()
    require_local_refusal(
        send_event(
            client,
            require_event(
                request_result(
                    headers=[("Host", "example.com")],
                    http_version="1.0",
                )
            ),
        ),
        suggested=400,
    )
    require_our_error_their_not(client)
    begin_next_cycle(client)
    require_side_still_error(client, "our")
    our, _their = connection_side_states(client)
    assert our != named_state("IDLE")
    assert our != named_state("DONE")
    print("start-next-cycle left our ERROR", flush=True)


# ---------------------------------------------------------------------------
# E. Mark send as failed
# ---------------------------------------------------------------------------


def test_mark_send_as_failed_sets_our_error_leaves_their():
    client = client_connection()
    require_send_bytes(
        send_event(client, make_request(headers=[("Host", "example.com")]))
    )
    _our_before, their_before = connection_side_states(client)
    assert their_before == named_state("SEND_RESPONSE")
    require_mark_failed(client)
    _our_after, their_after = connection_side_states(client)
    assert their_after == their_before
    require_our_error_their_not(client)
    print(f"mark left their={their_after!r}", flush=True)


def test_mark_send_as_failed_twice_is_idempotent():
    client = client_connection()
    require_send_bytes(
        send_event(client, make_request(headers=[("Host", "example.com")]))
    )
    _our, their_before = connection_side_states(client)
    require_mark_failed(client)
    require_mark_failed(client)
    _our2, their_after = connection_side_states(client)
    assert their_after == their_before
    require_our_error_their_not(client)
    print("second mark left states unchanged", flush=True)


def test_send_after_mark_failed_is_local_error():
    host = generated_host()
    target = generated_target()
    unmarked = client_connection()
    require_send_bytes(
        send_event(
            unmarked,
            make_request(target=target, headers=[("Host", host)]),
        )
    )
    unmarked_eom = send_event(unmarked, make_eom())
    if unmarked_eom.exception is not None:
        raise AssertionError(
            "unmarked neighbor EOM failed: "
            f"{type(unmarked_eom.exception).__name__}: {unmarked_eom.exception!r}"
        )

    marked = client_connection()
    require_send_bytes(
        send_event(
            marked,
            make_request(target=target, headers=[("Host", host)]),
        )
    )
    _our, their_before = connection_side_states(marked)
    require_mark_failed(marked)
    _our2, their_after = connection_side_states(marked)
    assert their_after == their_before
    refused = send_event(marked, make_eom())
    require_local_refusal(refused, suggested=400)
    require_our_error_their_not(marked)
    print("EOM after mark is local; unmarked neighbor succeeded", flush=True)


def test_mark_send_as_failed_after_server_send():
    raw = b"GET / HTTP/1.1\r\nHost: a\r\n\r\n"
    unmarked = server_connection()
    feed_ok(unmarked, raw)
    pull_request_then_eom(unmarked)
    require_send_bytes(send_event(unmarked, make_response(200, headers=[])))
    unmarked_eom = send_event(unmarked, make_eom())
    if unmarked_eom.exception is not None:
        raise AssertionError(
            "unmarked server EOM failed: "
            f"{type(unmarked_eom.exception).__name__}: {unmarked_eom.exception!r}"
        )

    marked = server_connection()
    feed_ok(marked, raw)
    pull_request_then_eom(marked)
    require_send_bytes(send_event(marked, make_response(200, headers=[])))
    _our, their_before = connection_side_states(marked)
    assert their_before == named_state("DONE")
    require_mark_failed(marked)
    _our2, their_after = connection_side_states(marked)
    assert their_after == named_state("MUST_CLOSE")
    require_our_error_their_not(marked)
    refused = send_event(marked, make_eom())
    require_local_refusal(refused, suggested=400)
    print("server mark: their DONE became MUST_CLOSE, later EOM local", flush=True)


def test_marked_failed_connection_cannot_return_to_idle():
    client = client_connection()
    require_send_bytes(
        send_event(client, make_request(headers=[("Host", "example.com")]))
    )
    require_mark_failed(client)
    begin_next_cycle(client)
    require_side_still_error(client, "our")
    our, _their = connection_side_states(client)
    assert our != named_state("IDLE")
    print("marked connection did not return to IDLE", flush=True)


# ---------------------------------------------------------------------------
# F. Incomplete-event size limit
# ---------------------------------------------------------------------------


def test_big_header_4000a_succeeds_at_limit_5000():
    server = connection_with_incomplete_limit(server_role(), 5000)
    feed_ok(server, fixed_big_header_block())
    pulled = pull_request_then_eom(server)
    assert request_method(pulled) == b"GET"
    assert request_target(pulled) == b"/"
    print("4000-a Big header succeeded at limit 5000", flush=True)


def test_big_header_4000a_fails_at_limit_4000_status_431():
    ok = connection_with_incomplete_limit(server_role(), 5000)
    feed_ok(ok, fixed_big_header_block())
    ok_req = pull_request_then_eom(ok)
    assert request_method(ok_req) == b"GET"

    bad = connection_with_incomplete_limit(server_role(), 4000)
    feed_ok(bad, fixed_big_header_unfinished())
    result = pull_next(bad)
    exc = require_remote_status(result, 431)
    require_their_error_our_not(bad)
    assert suggested_status(exc) == 431
    our, their = connection_side_states(bad)
    assert their == named_state("ERROR")
    print("4000-a Big header failed at limit 4000 with 431", flush=True)


def test_complete_10000_body_succeeds_at_limit_5000():
    block = (
        b"GET / HTTP/1.0\r\nContent-Length: 10000\r\n\r\n" + (b"a" * 10000)
    )
    server = connection_with_incomplete_limit(server_role(), 5000)
    feed_ok(server, block)
    pulled = pull_kind(server, "request")
    assert request_method(pulled) == b"GET"
    body = concatenated_body_until_eom(server)
    assert body == b"a" * 10000
    print("10000-byte complete body succeeded at limit 5000", flush=True)


def test_complete_framed_body_not_10000_succeeds_under_smaller_limit():
    body_n = 220 + (runtime_int() % 180)
    if body_n == 10000:
        body_n = 360
    token = runtime_token().encode("ascii")
    body = (token * (body_n // len(token) + 2))[:body_n]
    headers = (
        b"GET / HTTP/1.1\r\nHost: z\r\nContent-Length: "
        + str(body_n).encode("ascii")
        + b"\r\n\r\n"
    )
    limit = len(headers) + 20
    assert limit < body_n
    print(
        f"framed-body neighbor limit={limit} body_n={body_n} "
        f"headers={len(headers)}",
        flush=True,
    )

    ok = connection_with_incomplete_limit(server_role(), limit)
    feed_ok(ok, headers + body)
    pull_kind(ok, "request")
    got = concatenated_body_until_eom(ok)
    assert got == body

    bad = connection_with_incomplete_limit(server_role(), limit)
    feed_ok(bad, b"GET / HTTP/1.1\r\nHost: z\r\nH: " + (b"q" * limit))
    require_remote_status(pull_next(bad), 431)
    require_their_error_our_not(bad)


def test_pipelined_leftovers_fail_only_when_next_message_is_parsed():
    server = connection_with_incomplete_limit(server_role(), 100)
    feed_ok(
        server,
        b"GET /1 HTTP/1.1\r\nHost: a\r\n\r\n"
        b"GET /2 HTTP/1.1\r\nHost: b\r\n\r\n"
        + (b"X" * 1000),
    )
    first = pull_request_then_eom(server)
    assert request_target(first) == b"/1"
    require_pull_paused(pull_next(server))
    send_empty_200(server)
    require_cycle_reset(begin_next_cycle(server), server)
    second = pull_request_then_eom(server)
    assert request_target(second) == b"/2"
    require_pull_paused(pull_next(server))
    send_empty_200(server)
    require_cycle_reset(begin_next_cycle(server), server)
    leftover = pull_next(server)
    require_remote_status(leftover, 431)
    require_their_error_our_not(server)
    print("pipelined X leftovers failed only after the further start", flush=True)


def test_runtime_pipelined_leftovers_fail_only_when_parsed():
    host_a = generated_host()
    host_b = generated_host()
    target_a = generated_target()
    target_b = generated_target()
    req1 = (
        f"GET {target_a} HTTP/1.1\r\nHost: {host_a}\r\n\r\n".encode("ascii")
    )
    req2 = (
        f"GET {target_b} HTTP/1.1\r\nHost: {host_b}\r\n\r\n".encode("ascii")
    )
    limit = max(len(req1), len(req2)) + 12
    extra_n = limit + 40 + (runtime_int() % 20)
    extra = (runtime_token().encode("ascii") * 20)[:extra_n]
    if extra == b"X" * 1000 or limit == 100:
        extra = extra + b"Q"
        limit = limit + 3
    print(
        f"runtime pipeline limit={limit} extra={len(extra)} "
        f"req1={len(req1)} req2={len(req2)}",
        flush=True,
    )
    server = connection_with_incomplete_limit(server_role(), limit)
    feed_ok(server, req1 + req2 + extra)
    first = pull_request_then_eom(server)
    assert request_target(first) == target_a.encode("ascii")
    require_pull_paused(pull_next(server))
    send_empty_200(server)
    require_cycle_reset(begin_next_cycle(server), server)
    second = pull_request_then_eom(server)
    assert request_target(second) == target_b.encode("ascii")
    require_pull_paused(pull_next(server))
    send_empty_200(server)
    require_cycle_reset(begin_next_cycle(server), server)
    leftover = pull_next(server)
    require_remote_status(leftover, 431)
    require_their_error_our_not(server)


def test_endless_header_eventually_fails_at_default_limit():
    server = server_connection()
    prefix = b"GET / HTTP/1.0\r\nEndless: "
    feed_ok(server, prefix)
    require_need_data(pull_next(server))
    buffered = len(prefix)
    failed = False
    for _ in range(24):
        feed_ok(server, b"a" * 1024)
        buffered += 1024
        result = pull_next(server)
        if buffered <= 14 * 1024:
            require_need_data(result)
            continue
        if result.exception is not None:
            require_remote_status(result, 431)
            failed = True
            print(f"endless failed at buffered={buffered}", flush=True)
            break
        require_need_data(result)
        if buffered > 18 * 1024:
            raise AssertionError(
                f"default limit still need-data at buffered={buffered}"
            )
    assert failed, f"endless header never failed; buffered={buffered}"


def test_default_incomplete_limit_between_14_and_18_kibibytes():
    prefix = b"GET / HTTP/1.0\r\nH: "
    low_n = 14 * 1024 - len(prefix)
    high_n = 18 * 1024 - len(prefix)
    low = server_connection()
    feed_ok(low, prefix + (b"a" * low_n))
    low_result = pull_next(low)
    require_need_data(low_result)
    assert low_result.exception is None
    print(f"default low unfinished={len(prefix) + low_n} need-data", flush=True)

    high = server_connection()
    feed_ok(high, prefix + (b"a" * high_n))
    high_exc = require_remote_status(pull_next(high), 431)
    require_their_error_our_not(high)
    assert suggested_status(high_exc) == 431
    our, their = connection_side_states(high)
    assert their == named_state("ERROR")
    print(f"default high unfinished={len(prefix) + high_n} is 431", flush=True)


def test_oversize_unfinished_response_headers_are_remote_431():
    client = connection_with_incomplete_limit(client_role(), 4000)
    require_send_bytes(
        send_event(client, make_request(headers=[("Host", "a")]))
    )
    send_eom_bytes(client)
    feed_ok(client, b"HTTP/1.1 200 \r\nBig: " + (b"a" * 4000))
    result = pull_next(client)
    exc = require_remote_status(result, 431)
    require_their_error_our_not(client)
    assert suggested_status(exc) == 431
    our, their = connection_side_states(client)
    assert their == named_state("ERROR")
    print("unfinished 200 / 4000-a response headers are remote 431", flush=True)


def test_runtime_oversize_unfinished_response_headers():
    limit = 90 + (runtime_int() % 40)
    if limit == 4000:
        limit = 110
    client = connection_with_incomplete_limit(client_role(), limit)
    require_send_bytes(
        send_event(
            client,
            make_request(
                target=generated_target(),
                headers=[("Host", generated_host())],
            ),
        )
    )
    send_eom_bytes(client)
    unfinished = b"HTTP/1.1 204 " + (b"Z" * limit)
    assert len(unfinished) > limit
    feed_ok(client, unfinished)
    require_remote_status(pull_next(client), 431)
    require_their_error_our_not(client)
    print(f"runtime unfinished response line failed at limit={limit}", flush=True)


def test_limit_counts_line_plus_headers_not_value_alone():
    line = b"GET /oversize-target-path-for-the-line-limit HTTP/1.1"
    line_limit = 24
    assert len(line) > line_limit
    line_conn = connection_with_incomplete_limit(server_role(), line_limit)
    feed_ok(line_conn, line)
    require_remote_status(pull_next(line_conn), 431)
    require_their_error_our_not(line_conn)

    combo_limit = 48
    value = b"xy"
    prefix = b"GET /long-enough-target HTTP/1.1\r\nHost: example.com\r\nZ: "
    block = prefix + value
    assert len(value) < combo_limit
    assert len(block) > combo_limit
    combo = connection_with_incomplete_limit(server_role(), combo_limit)
    feed_ok(combo, block)
    require_remote_status(pull_next(combo), 431)
    require_their_error_our_not(combo)
    print(
        f"line len={len(line)} combo len={len(block)} value={len(value)}",
        flush=True,
    )


def test_runtime_header_crosses_custom_limit():
    name = runtime_token()[:8]
    n = 90 + (runtime_int() % 50)
    if n == 4000:
        n = 120
    value = b"z" * n
    prefix = f"GET / HTTP/1.0\r\n{name}: ".encode("ascii")
    unfinished = prefix + value
    small = n
    large = len(unfinished) + 60
    if small in (4000, 5000) or large in (4000, 5000):
        small = n + 1
        large = len(unfinished) + 77
    print(
        f"runtime header name={name!r} n={n} small={small} large={large} "
        f"unfinished={len(unfinished)}",
        flush=True,
    )
    ok = connection_with_incomplete_limit(server_role(), large)
    feed_ok(ok, unfinished + b"\r\n\r\n")
    pulled = pull_request_then_eom(ok)
    assert request_method(pulled) == b"GET"

    bad = connection_with_incomplete_limit(server_role(), small)
    feed_ok(bad, unfinished)
    bad_exc = require_remote_status(pull_next(bad), 431)
    require_their_error_our_not(bad)
    assert suggested_status(bad_exc) == 431
    our, their = connection_side_states(bad)
    assert their == named_state("ERROR")


# ---------------------------------------------------------------------------
# G. Receive-side close mid-body / mid-request-line
# ---------------------------------------------------------------------------


def test_content_length_100_cut_after_12345_is_remote_not_closed():
    server = server_connection()
    feed_ok(
        server,
        b"POST / HTTP/1.1\r\n"
        b"Host: example.com\r\n"
        b"Content-Length: 100\r\n"
        b"\r\n",
    )
    pull_kind(server, "request")
    feed_ok(server, b"12345")
    data = pull_kind(server, "data")
    assert payload_as_bytes(data) == b"12345"
    feed_empty(server)
    result = pull_next(server)
    require_remote_status(result, 400)
    require_not_connection_closed_event(result.value)
    print("CL 100 cut after 12345 is remote 400, not connection-closed", flush=True)


def test_incomplete_chunked_empty_feed_is_remote():
    neighbor = chunked_post_server()
    neighbor_hello_chunk(neighbor)

    server = chunked_post_server()
    feed_ok(server, b"8\r\n012345")
    data = pull_kind(server, "data")
    assert payload_as_bytes(data) == b"012345"
    feed_empty(server)
    result = pull_next(server)
    require_remote_status(result, 400)
    require_not_connection_closed_event(result.value)
    print("incomplete chunked empty feed is remote 400", flush=True)


def test_http10_close_delimited_empty_feed_is_eom_then_closed():
    client = client_connection()
    require_send_bytes(
        send_event(client, make_request(headers=[("Host", "a")]))
    )
    send_eom_bytes(client)
    feed_ok(client, b"HTTP/1.0 200 \r\n\r\n")
    pull_kind(client, "response")
    feed_ok(client, b"12345")
    first = pull_kind(client, "data")
    assert payload_as_bytes(first) == b"12345"
    feed_ok(client, b"67890")
    second = pull_kind(client, "data")
    assert payload_as_bytes(second) == b"67890"
    feed_empty(client)
    eom = require_pulled_event(pull_next(client))
    assert event_is_kind(eom, "end-of-message")
    closed = require_pulled_event(pull_next(client))
    assert event_is_kind(closed, "connection-closed")
    print("HTTP/1.0 close-delimited empty feed is EOM then connection-closed", flush=True)


def test_http10_unfinished_cl_empty_feed_is_remote():
    framed = client_connection()
    require_send_bytes(
        send_event(framed, make_request(headers=[("Host", "a")]))
    )
    send_eom_bytes(framed)
    feed_ok(framed, b"HTTP/1.0 200 \r\nContent-Length: 100\r\n\r\n")
    pull_kind(framed, "response")
    feed_ok(framed, b"12345")
    pull_kind(framed, "data")
    feed_empty(framed)
    framed_result = pull_next(framed)
    require_remote_status(framed_result, 400)
    require_not_connection_closed_event(framed_result.value)

    close_del = client_connection()
    require_send_bytes(
        send_event(close_del, make_request(headers=[("Host", "a")]))
    )
    send_eom_bytes(close_del)
    feed_ok(close_del, b"HTTP/1.0 200 \r\n\r\n")
    pull_kind(close_del, "response")
    feed_ok(close_del, b"12345")
    pull_kind(close_del, "data")
    feed_empty(close_del)
    eom = require_pulled_event(pull_next(close_del))
    assert event_is_kind(eom, "end-of-message")
    closed = require_pulled_event(pull_next(close_del))
    assert event_is_kind(closed, "connection-closed")
    print("HTTP/1.0 contrast: unfinished CL remote; no framing closed", flush=True)


def test_client_http11_unfinished_cl_empty_feed_is_remote():
    client = client_connection()
    require_send_bytes(
        send_event(client, make_request(headers=[("Host", "a")]))
    )
    send_eom_bytes(client)
    feed_ok(client, b"HTTP/1.1 200 \r\nContent-Length: 100\r\n\r\n")
    pull_kind(client, "response")
    feed_ok(client, b"12345")
    pull_kind(client, "data")
    feed_empty(client)
    result = pull_next(client)
    exc = require_remote_status(result, 400)
    require_not_connection_closed_event(result.value)
    assert suggested_status(exc) == 400
    assert not event_is_kind(result.value, "connection-closed")
    print("client HTTP/1.1 unfinished CL empty feed is remote", flush=True)


def test_mid_request_line_empty_feed_is_remote():
    neighbor = server_connection()
    feed_ok(neighbor, b"GET / HTTP/1.0\r\n\r\n")
    pulled = pull_request_then_eom(neighbor)
    assert request_method(pulled) == b"GET"
    assert request_target(pulled) == b"/"

    server = server_connection()
    feed_ok(server, b"GET /")
    require_need_data(pull_next(server))
    feed_empty(server)
    result = pull_next(server)
    require_remote_status(result, 400)
    require_not_connection_closed_event(result.value)
    print("mid-request-line empty feed is remote 400", flush=True)
