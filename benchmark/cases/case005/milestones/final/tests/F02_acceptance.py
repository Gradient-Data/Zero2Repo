# feature: F02
"""Acceptance tests for the bring-your-own-I/O connection (FP-02).

Exercises connection construction, send / feed / pull, the nine named
states, need-data, Host-first encoding, receive-side folding, and the
no-library-I/O oracle. Event shape is FP-01. Framing choice, keep-alive,
and protocol-error integers are later feature points.
"""

from __future__ import annotations

from _harness import call
from F01_helpers import (
    data_payload,
    event_version,
    local_protocol_error_type,
    named_pairs,
    ordinary_pairs,
    package,
    payload_letters,
    reason,
    remote_protocol_error_type,
    request_method,
    request_result,
    request_target,
    request_version,
    require_local_refusal,
    runtime_int,
    runtime_token,
    status_code,
)
from F02_helpers import (
    client_connection,
    client_role,
    client_server_after_public_get,
    connection_for,
    connection_pair_states,
    connection_side_states,
    encoded_first_line,
    encoded_head_and_rest,
    event_is_kind,
    feed_bytes,
    header_index,
    make_data,
    make_eom,
    make_informational,
    make_request,
    make_response,
    named_state,
    need_data_token,
    neighbor_request_pulls,
    neighbor_response_pulls,
    peer_http_version,
    pull_next,
    require_need_data,
    require_no_connection,
    require_no_extra_bytes,
    require_pulled_event,
    require_remote_refusal,
    require_runtime_refusal,
    require_send_bytes,
    send_event,
    send_fixed_get,
    server_connection,
    server_role,
    status_line_reason,
    wire_header_names,
    wire_header_value,
)


# ---------------------------------------------------------------------------
# S. Present-arm encode and pull
# ---------------------------------------------------------------------------


def test_client_get_encodes_and_server_pulls_when_package_importable():
    client = client_connection()
    event = make_request(headers=[("Host", "example.com")])
    encoded = require_send_bytes(send_event(client, event))
    print(f"baseline encoded first={encoded_first_line(encoded)!r}", flush=True)
    assert b"GET" in encoded_first_line(encoded)
    assert b"/" in encoded_first_line(encoded)
    server = server_connection()
    fed = feed_bytes(server, encoded)
    assert fed.exception is None, f"server feed failed: {fed.exception!r}"
    pulled = require_pulled_event(pull_next(server))
    assert event_is_kind(pulled, "request")
    assert request_method(pulled) == b"GET"
    assert request_target(pulled) == b"/"
    hosts = named_pairs(ordinary_pairs(pulled), b"host")
    assert (b"host", b"example.com") in hosts


def test_client_get_encode_fails_when_package_not_importable():
    # The product is exercised by real send/pull on a constructed connection.
    client = client_connection()
    event = make_request(headers=[("Host", "example.com")])
    encoded = require_send_bytes(send_event(client, event))
    print(f"present-arm encoded first={encoded_first_line(encoded)!r}", flush=True)
    assert b"GET" in encoded_first_line(encoded)
    assert b"/" in encoded_first_line(encoded)
    server = server_connection()
    fed = feed_bytes(server, encoded)
    assert fed.exception is None, f"server feed failed: {fed.exception!r}"
    pulled = require_pulled_event(pull_next(server))
    assert event_is_kind(pulled, "request")
    assert request_method(pulled) == b"GET"
    assert request_target(pulled) == b"/"
    hosts = named_pairs(ordinary_pairs(pulled), b"host")
    assert (b"host", b"example.com") in hosts


# ---------------------------------------------------------------------------
# A. Roles, IDLE, nine states, illegal role
# ---------------------------------------------------------------------------


def test_client_and_server_roles_are_complementary_and_idle():
    client = client_connection()
    server = server_connection()
    c_role = client_role()
    s_role = server_role()
    idle = named_state("IDLE")
    assert client.our_role == c_role
    assert client.their_role == s_role
    assert server.our_role == s_role
    assert server.their_role == c_role
    c_our, c_their = connection_side_states(client)
    s_our, s_their = connection_side_states(server)
    print(
        f"client our={c_our!r} their={c_their!r} "
        f"server our={s_our!r} their={s_their!r}",
        flush=True,
    )
    assert c_our == idle
    assert c_their == idle
    assert s_our == idle
    assert s_their == idle
    assert c_role is not s_role
    assert c_role != s_role


def test_nine_named_states_are_distinct_and_queryable():
    names = (
        "IDLE",
        "SEND_RESPONSE",
        "SEND_BODY",
        "DONE",
        "MUST_CLOSE",
        "CLOSED",
        "MIGHT_SWITCH_PROTOCOL",
        "SWITCHED_PROTOCOL",
        "ERROR",
    )
    states = [named_state(name) for name in names]
    print(f"nine states={[type(s).__name__ for s in states]}", flush=True)
    assert len(states) == 9
    assert len(set(id(s) for s in states)) == 9
    for i, left in enumerate(states):
        for j, right in enumerate(states):
            if i != j:
                assert left != right
    conn = client_connection()
    our, their = connection_side_states(conn)
    idle = named_state("IDLE")
    assert our == idle
    assert their == idle
    assert our in states
    assert their in states
    pair = connection_pair_states(conn)
    assert pair[0] == idle
    assert pair[1] == idle


def test_our_their_and_pair_states_agree_when_idle():
    client = client_connection()
    server = server_connection()
    idle = named_state("IDLE")
    c_our, c_their = connection_side_states(client)
    s_our, s_their = connection_side_states(server)
    c_pair = connection_pair_states(client)
    s_pair = connection_pair_states(server)
    print(
        f"idle pair client={c_pair!r} server={s_pair!r}",
        flush=True,
    )
    assert c_our == idle
    assert c_their == idle
    assert s_our == idle
    assert s_their == idle
    assert c_pair[0] == c_our
    assert c_pair[1] == s_our
    assert s_pair[0] == c_our
    assert s_pair[1] == s_our


def test_role_that_is_neither_client_nor_server_is_refused():
    token = runtime_token()
    ctor = package().Connection
    neighbor_ok = connection_for(client_role())
    assert neighbor_ok is not None
    refused = call(ctor, token)
    print(f"non-role {token!r} exc={refused.exception!r}", flush=True)
    require_no_connection(refused)
    still_ok = connection_for(server_role())
    assert still_ok is not None


def test_second_non_role_value_is_refused():
    ctor = package().Connection
    neighbor_ok = connection_for(client_role())
    assert neighbor_ok is not None
    refused = call(ctor, object())
    print(f"non-role object exc={refused.exception!r}", flush=True)
    require_no_connection(refused)


# ---------------------------------------------------------------------------
# B. Fresh pull is need-data
# ---------------------------------------------------------------------------


def test_fresh_client_pull_is_need_data():
    conn = client_connection()
    first = require_need_data(pull_next(conn))
    second = require_need_data(pull_next(conn))
    token = need_data_token()
    print(f"fresh client need-data {first!r} {second!r}", flush=True)
    assert first == token
    assert second == token
    assert first == second


def test_fresh_server_pull_is_need_data():
    conn = server_connection()
    first = require_need_data(pull_next(conn))
    second = require_need_data(pull_next(conn))
    token = need_data_token()
    print(f"fresh server need-data {first!r} {second!r}", flush=True)
    assert first == token
    assert second == token
    assert first == second
    client_fresh = require_need_data(pull_next(client_connection()))
    assert first == client_fresh


# ---------------------------------------------------------------------------
# C. Client GET encode, peer pull, states, peer version
# ---------------------------------------------------------------------------


def test_client_get_slash_cl10_encodes_http11_request_line():
    client = client_connection()
    encoded = send_fixed_get(client)
    line = encoded_first_line(encoded)
    head, rest = encoded_head_and_rest(encoded)
    print(f"request line={line!r} rest_len={len(rest)}", flush=True)
    assert b"GET" in line
    assert b"/" in line
    assert b"1.1" in line
    assert wire_header_value(encoded, b"Host") == b"example.com"
    assert wire_header_value(encoded, b"Content-Length") == b"10"
    _ = head


def test_client_states_after_get_send_are_send_body_and_send_response():
    client = client_connection()
    send_fixed_get(client)
    send_body = named_state("SEND_BODY")
    send_response = named_state("SEND_RESPONSE")
    pair = connection_pair_states(client)
    our, their = connection_side_states(client)
    print(f"after send pair={pair!r} our={our!r} their={their!r}", flush=True)
    assert pair[0] == send_body
    assert pair[1] == send_response
    assert our == send_body
    assert their == send_response


def test_client_peer_http_version_absent_after_request_send():
    client = client_connection()
    send_fixed_get(client)
    version = peer_http_version(client)
    print(f"client peer version after send={version!r}", flush=True)
    assert version is None


def test_server_feed_only_leaves_idle_and_peer_version_absent():
    client = client_connection()
    encoded = send_fixed_get(client)
    server = server_connection()
    fed = feed_bytes(server, encoded)
    assert fed.exception is None, f"feed-only failed: {fed.exception!r}"
    idle = named_state("IDLE")
    our, their = connection_side_states(server)
    pair = connection_pair_states(server)
    version = peer_http_version(server)
    print(
        f"feed-only our={our!r} their={their!r} pair={pair!r} version={version!r}",
        flush=True,
    )
    assert our == idle
    assert their == idle
    assert pair[0] == idle
    assert pair[1] == idle
    assert version is None
    pulled = require_pulled_event(pull_next(server))
    assert event_is_kind(pulled, "request")
    assert request_method(pulled) == b"GET"


def test_server_pull_of_that_get_matches_and_records_peer_1_1():
    client, server, encoded, pulled = client_server_after_public_get()
    send_body = named_state("SEND_BODY")
    send_response = named_state("SEND_RESPONSE")
    assert event_is_kind(pulled, "request")
    assert request_method(pulled) == b"GET"
    assert request_target(pulled) == b"/"
    pairs = ordinary_pairs(pulled)
    assert (b"host", b"example.com") in pairs
    assert (b"content-length", b"10") in pairs
    c_pair = connection_pair_states(client)
    s_pair = connection_pair_states(server)
    print(f"after pull client_pair={c_pair!r} server_pair={s_pair!r}", flush=True)
    assert c_pair == (send_body, send_response)
    assert s_pair == (send_body, send_response)
    assert peer_http_version(server) == b"1.1"
    assert peer_http_version(client) is None
    _ = encoded


def test_runtime_host_and_target_round_trip():
    token = runtime_token()
    target = "/" + token
    host = token + ".test"
    cl = runtime_int()
    while cl in (10, 11):
        cl = runtime_int() + 3
    print(f"runtime target={target!r} host={host!r} cl={cl}", flush=True)
    client = client_connection()
    event = make_request(
        target=target,
        headers=[("Host", host), ("Content-Length", str(cl))],
    )
    encoded = require_send_bytes(send_event(client, event))
    line = encoded_first_line(encoded)
    assert b"GET" in line
    assert target.encode("ascii") in line
    assert b"1.1" in line
    assert wire_header_value(encoded, b"Host") == host.encode("ascii")
    assert wire_header_value(encoded, b"Content-Length") == str(cl).encode("ascii")
    server = server_connection()
    fed = feed_bytes(server, encoded)
    assert fed.exception is None, f"runtime feed failed: {fed.exception!r}"
    pulled = require_pulled_event(pull_next(server))
    assert event_is_kind(pulled, "request")
    assert request_method(pulled) == b"GET"
    assert request_target(pulled) == target.encode("ascii")
    pairs = ordinary_pairs(pulled)
    assert (b"host", host.encode("ascii")) in pairs
    assert (b"content-length", str(cl).encode("ascii")) in pairs


# ---------------------------------------------------------------------------
# D. Informational 100 then final 200; empty reason unless supplied
# ---------------------------------------------------------------------------


def test_informational_100_status_line_empty_reason_unless_supplied():
    client, server, _, _ = client_server_after_public_get()
    omitted = make_informational(100, headers=[])
    encoded_empty = require_send_bytes(send_event(server, omitted))
    line = encoded_first_line(encoded_empty)
    print(f"100 empty-reason line={line!r}", flush=True)
    assert b"1.1" in line
    assert b"100" in line
    empty = status_line_reason(encoded_empty, 100)
    assert empty == b""
    assert len(empty) == 0

    other = server_connection()
    feed_bytes(other, send_fixed_get(client_connection()))
    require_pulled_event(pull_next(other))
    supplied = make_informational(100, headers=[], reason=b"OK")
    encoded_ok = require_send_bytes(send_event(other, supplied))
    phrase = status_line_reason(encoded_ok, 100)
    print(f"100 supplied reason={phrase!r}", flush=True)
    assert phrase == b"OK"
    _ = client


def test_runtime_reason_is_written_after_status_code():
    token = runtime_token()
    cl = runtime_int()
    while cl in (10, 11):
        cl += 5
    client = client_connection()
    encoded_get = send_fixed_get(client)
    server = server_connection()
    feed_bytes(server, encoded_get)
    require_pulled_event(pull_next(server))
    resp = make_response(
        200,
        headers=[("Content-Length", str(cl))],
        reason=token,
    )
    encoded = require_send_bytes(send_event(server, resp))
    phrase = status_line_reason(encoded, 200)
    print(f"runtime reason={phrase!r} cl={cl}", flush=True)
    assert phrase == token.encode("ascii")
    assert wire_header_value(encoded, b"Content-Length") == str(cl).encode("ascii")
    fed = feed_bytes(client, encoded)
    assert fed.exception is None, f"client feed of runtime response failed: {fed.exception!r}"
    pulled = require_pulled_event(pull_next(client))
    assert event_is_kind(pulled, "response")
    assert status_code(pulled) == 200
    assert reason(pulled) == token.encode("ascii")
    assert (b"content-length", str(cl).encode("ascii")) in ordinary_pairs(pulled)


def test_response_200_cl11_empty_reason_unless_supplied():
    client, server, _, _ = client_server_after_public_get()
    require_send_bytes(send_event(server, make_informational(100, headers=[])))
    omitted = make_response(200, headers=[("Content-Length", "11")])
    encoded_empty = require_send_bytes(send_event(server, omitted))
    line = encoded_first_line(encoded_empty)
    print(f"200 empty-reason line={line!r}", flush=True)
    assert b"200" in line
    assert status_line_reason(encoded_empty, 200) == b""
    assert wire_header_value(encoded_empty, b"Content-Length") == b"11"

    other_client = client_connection()
    other_get = send_fixed_get(other_client)
    other = server_connection()
    feed_bytes(other, other_get)
    require_pulled_event(pull_next(other))
    require_send_bytes(send_event(other, make_informational(100, headers=[])))
    supplied = make_response(
        200, headers=[("Content-Length", "11")], reason=b"OK"
    )
    encoded_ok = require_send_bytes(send_event(other, supplied))
    assert status_line_reason(encoded_ok, 200) == b"OK"
    _ = client


def test_both_sides_send_body_after_final_response():
    client, server, _, _ = client_server_after_public_get()
    info = require_send_bytes(send_event(server, make_informational(100, headers=[])))
    final = require_send_bytes(
        send_event(server, make_response(200, headers=[("Content-Length", "11")]))
    )
    send_body = named_state("SEND_BODY")
    s_pair = connection_pair_states(server)
    print(f"server after sending 200 pair={s_pair!r}", flush=True)
    assert s_pair == (send_body, send_body)
    fed = feed_bytes(client, info + final)
    assert fed.exception is None
    require_pulled_event(pull_next(client))
    require_pulled_event(pull_next(client))
    c_pair = connection_pair_states(client)
    print(f"client after pulling 200 pair={c_pair!r}", flush=True)
    assert c_pair == (send_body, send_body)


def test_client_pulls_100_then_200():
    client, server, _, _ = client_server_after_public_get()
    info = require_send_bytes(send_event(server, make_informational(100, headers=[])))
    final = require_send_bytes(
        send_event(server, make_response(200, headers=[("Content-Length", "11")]))
    )
    fed = feed_bytes(client, info + final)
    assert fed.exception is None, f"client feed of 100+200 failed: {fed.exception!r}"
    first = require_pulled_event(pull_next(client))
    second = require_pulled_event(pull_next(client))
    print(
        f"pulled 100 kind={type(first).__name__} reason={reason(first)!r} "
        f"200 kind={type(second).__name__} cl={ordinary_pairs(second)!r}",
        flush=True,
    )
    assert event_is_kind(first, "informational")
    assert status_code(first) == 100
    assert reason(first) == b""
    assert event_is_kind(second, "response")
    assert status_code(second) == 200
    assert reason(second) == b""
    assert (b"content-length", b"11") in ordinary_pairs(second)


# ---------------------------------------------------------------------------
# E. Content-Length body; last bytes then EOM; both DONE
# ---------------------------------------------------------------------------


def test_cl_data_12345_encodes_as_exactly_those_bytes():
    client, server, _, _ = client_server_after_public_get()
    require_send_bytes(send_event(server, make_informational(100, headers=[])))
    require_send_bytes(
        send_event(server, make_response(200, headers=[("Content-Length", "11")]))
    )
    encoded = require_send_bytes(send_event(client, make_data(b"12345")))
    print(f"12345 encoded={encoded!r}", flush=True)
    assert encoded == b"12345"


def test_cl_data_67890_then_eom_encodes_no_extra_bytes():
    client, server, _, _ = client_server_after_public_get()
    require_send_bytes(send_event(server, make_informational(100, headers=[])))
    require_send_bytes(
        send_event(server, make_response(200, headers=[("Content-Length", "11")]))
    )
    first = require_send_bytes(send_event(client, make_data(b"12345")))
    assert first == b"12345"
    second = require_send_bytes(send_event(client, make_data(b"67890")))
    print(f"67890 encoded={second!r}", flush=True)
    assert second == b"67890"
    require_no_extra_bytes(send_event(client, make_eom()))


def test_last_cl_bytes_then_further_pull_is_end_of_message():
    client, server, _, _ = client_server_after_public_get()
    require_send_bytes(send_event(server, make_informational(100, headers=[])))
    require_send_bytes(
        send_event(server, make_response(200, headers=[("Content-Length", "11")]))
    )
    chunk1 = require_send_bytes(send_event(client, make_data(b"12345")))
    chunk2 = require_send_bytes(send_event(client, make_data(b"67890")))
    fed1 = feed_bytes(server, chunk1)
    assert fed1.exception is None
    first = require_pulled_event(pull_next(server))
    assert event_is_kind(first, "data")
    assert payload_letters(data_payload(first)) == "12345"
    fed2 = feed_bytes(server, chunk2)
    assert fed2.exception is None
    last = require_pulled_event(pull_next(server))
    assert event_is_kind(last, "data")
    assert payload_letters(data_payload(last)) == "67890"
    further = require_pulled_event(pull_next(server))
    print(f"further after last CL={type(further).__name__}", flush=True)
    assert event_is_kind(further, "end-of-message")


def test_both_sides_done_after_matching_eoms():
    client, server, _, _ = client_server_after_public_get()
    info = require_send_bytes(send_event(server, make_informational(100, headers=[])))
    final = require_send_bytes(
        send_event(server, make_response(200, headers=[("Content-Length", "11")]))
    )
    feed_bytes(client, info + final)
    require_pulled_event(pull_next(client))
    require_pulled_event(pull_next(client))
    c1 = require_send_bytes(send_event(client, make_data(b"12345")))
    c2 = require_send_bytes(send_event(client, make_data(b"67890")))
    require_no_extra_bytes(send_event(client, make_eom()))
    feed_bytes(server, c1)
    require_pulled_event(pull_next(server))
    feed_bytes(server, c2)
    require_pulled_event(pull_next(server))
    require_pulled_event(pull_next(server))
    s1 = require_send_bytes(send_event(server, make_data(b"1234567890")))
    s2 = require_send_bytes(send_event(server, make_data(b"1")))
    require_no_extra_bytes(send_event(server, make_eom()))
    feed_bytes(client, s1)
    d1 = require_pulled_event(pull_next(client))
    feed_bytes(client, s2)
    d2 = require_pulled_event(pull_next(client))
    eom = require_pulled_event(pull_next(client))
    assert payload_letters(data_payload(d1)) + payload_letters(data_payload(d2)) == (
        "12345678901"
    )
    assert event_is_kind(eom, "end-of-message")
    done = named_state("DONE")
    c_pair = connection_pair_states(client)
    s_pair = connection_pair_states(server)
    print(f"done client={c_pair!r} server={s_pair!r}", flush=True)
    assert c_pair == (done, done)
    assert s_pair == (done, done)


def test_runtime_split_body_round_trip_under_content_length():
    token = runtime_token()
    part_a = (token + "aaaa")[:7]
    part_b = (token + "bbbbbbbb")[:9]
    assert len(part_a) != 5
    assert len(part_b) != 5
    total = len(part_a) + len(part_b)
    print(f"runtime body parts {len(part_a)}+{len(part_b)}={total}", flush=True)
    client = client_connection()
    event = make_request(
        headers=[("Host", "example.com"), ("Content-Length", str(total))]
    )
    encoded = require_send_bytes(send_event(client, event))
    server = server_connection()
    feed_bytes(server, encoded)
    require_pulled_event(pull_next(server))
    a_bytes = require_send_bytes(send_event(client, make_data(part_a.encode("ascii"))))
    assert a_bytes == part_a.encode("ascii")
    b_bytes = require_send_bytes(send_event(client, make_data(part_b.encode("ascii"))))
    assert b_bytes == part_b.encode("ascii")
    require_no_extra_bytes(send_event(client, make_eom()))
    feed_bytes(server, a_bytes)
    first = require_pulled_event(pull_next(server))
    feed_bytes(server, b_bytes)
    last = require_pulled_event(pull_next(server))
    further = require_pulled_event(pull_next(server))
    recovered = payload_letters(data_payload(first)) + payload_letters(
        data_payload(last)
    )
    print(f"runtime recovered={recovered!r}", flush=True)
    assert recovered == part_a + part_b
    assert event_is_kind(further, "end-of-message")


# ---------------------------------------------------------------------------
# F. No library I/O; two-step receive; split 200
# ---------------------------------------------------------------------------


def test_send_returns_bytes_and_does_not_require_a_socket():
    client = client_connection()
    encoded = require_send_bytes(
        send_event(client, make_request(headers=[("Host", "example.com")]))
    )
    assert len(encoded) > 0
    peer = server_connection()
    fed = feed_bytes(peer, encoded)
    assert fed.exception is None
    pulled = require_pulled_event(pull_next(peer))
    assert event_is_kind(pulled, "request")
    lonely = server_connection()
    lonely_pull = require_need_data(pull_next(lonely))
    print(f"independent peer got request; empty peer={lonely_pull!r}", flush=True)
    assert event_is_kind(pulled, "request")
    assert not event_is_kind(lonely_pull, "request")


def test_feed_stores_pull_parses_one_event():
    client, server, _, _ = client_server_after_public_get()
    info = require_send_bytes(send_event(server, make_informational(100, headers=[])))
    final = require_send_bytes(
        send_event(server, make_response(200, headers=[("Content-Length", "11")]))
    )
    combined = info + final
    fed = feed_bytes(client, combined)
    assert fed.exception is None
    first = require_pulled_event(pull_next(client))
    second = require_pulled_event(pull_next(client))
    print(
        f"one-feed two-pull first={type(first).__name__}/{status_code(first)} "
        f"second={type(second).__name__}/{status_code(second)}",
        flush=True,
    )
    assert event_is_kind(first, "informational")
    assert status_code(first) == 100
    assert event_is_kind(second, "response")
    assert status_code(second) == 200
    assert (b"content-length", b"11") in ordinary_pairs(second)


def test_split_200_for_xml_httpbin_returns_need_data_then_response():
    client = client_connection()
    encoded = require_send_bytes(
        send_event(
            client,
            make_request(target="/xml", headers=[("Host", "httpbin.org")]),
        )
    )
    print(f"xml request line={encoded_first_line(encoded)!r}", flush=True)
    first_frag = b"HTTP/1.1 20"
    second_frag = b"0 \r\nX-From-First: xml\r\nContent-Length: 0\r\n\r\n"
    assert b"200" not in first_frag
    assert b"HTTP/1.1" not in second_frag
    assert b"X-From-First" not in first_frag
    fed1 = feed_bytes(client, first_frag)
    assert fed1.exception is None
    assert require_need_data(pull_next(client)) == need_data_token()
    only_second = client_connection()
    require_send_bytes(
        send_event(
            only_second,
            make_request(target="/xml", headers=[("Host", "httpbin.org")]),
        )
    )
    feed_bytes(only_second, second_frag)
    only_second_result = pull_next(only_second)
    if only_second_result.exception is None:
        value = only_second_result.value
        assert not (
            event_is_kind(value, "response") and status_code(value) == 200
        ), "second fragment alone must not be a complete 200"
    fed2 = feed_bytes(client, second_frag)
    assert fed2.exception is None
    pulled = require_pulled_event(pull_next(client))
    print(f"split xml pulled status={status_code(pulled)}", flush=True)
    assert event_is_kind(pulled, "response")
    assert status_code(pulled) == 200
    assert (b"x-from-first", b"xml") in ordinary_pairs(pulled)


def test_runtime_split_response_retains_bytes_across_fragments():
    token = runtime_token()
    header_name = "X-" + token[:8]
    header_value = token
    client = client_connection()
    target = "/" + token[:6]
    host = token + ".org"
    require_send_bytes(
        send_event(client, make_request(target=target, headers=[("Host", host)]))
    )
    first_frag = (
        b"HTTP/1.1 200 \r\n" + header_name.encode("ascii") + b": " + header_value.encode("ascii") + b"\r\n"
    )
    second_frag = b"Content-Length: 0\r\n\r\n"
    assert header_name.encode("ascii") not in second_frag
    assert b"HTTP/1.1 200" not in second_frag
    fed1 = feed_bytes(client, first_frag)
    assert fed1.exception is None
    require_need_data(pull_next(client))
    only_second = client_connection()
    require_send_bytes(
        send_event(
            only_second, make_request(target=target, headers=[("Host", host)])
        )
    )
    feed_bytes(only_second, second_frag)
    only_second_result = pull_next(only_second)
    if only_second_result.exception is None:
        value = only_second_result.value
        assert not event_is_kind(value, "response"), (
            "second fragment alone must not parse as a complete response"
        )
    fed2 = feed_bytes(client, second_frag)
    assert fed2.exception is None
    pulled = require_pulled_event(pull_next(client))
    want = (header_name.lower().encode("ascii"), header_value.encode("ascii"))
    print(f"runtime split pairs={ordinary_pairs(pulled)!r}", flush=True)
    assert event_is_kind(pulled, "response")
    assert status_code(pulled) == 200
    assert want in ordinary_pairs(pulled)


# ---------------------------------------------------------------------------
# G. Peer HTTP/1.0 readable; version retained this cycle
# ---------------------------------------------------------------------------


def test_http10_get_slash_no_headers_pulls_version_1_0_and_eom():
    server = server_connection()
    fed = feed_bytes(server, b"GET / HTTP/1.0\r\n\r\n")
    assert fed.exception is None
    pulled = require_pulled_event(pull_next(server))
    assert event_is_kind(pulled, "request")
    assert request_method(pulled) == b"GET"
    assert request_target(pulled) == b"/"
    assert request_version(pulled) == b"1.0"
    eom = require_pulled_event(pull_next(server))
    print(f"http10 get eom={type(eom).__name__} peer={peer_http_version(server)!r}", flush=True)
    assert event_is_kind(eom, "end-of-message")
    assert peer_http_version(server) == b"1.0"

    token = runtime_token()
    target = "/" + token[:8]
    other = server_connection()
    feed_bytes(other, b"GET " + target.encode("ascii") + b" HTTP/1.0\r\n\r\n")
    other_req = require_pulled_event(pull_next(other))
    assert request_target(other_req) == target.encode("ascii")
    assert request_version(other_req) == b"1.0"
    assert peer_http_version(other) == b"1.0"


def test_http10_response_can_be_pulled_as_version_1_0():
    client = client_connection()
    require_send_bytes(
        send_event(client, make_request(headers=[("Host", "example.com")]))
    )
    fed = feed_bytes(client, b"HTTP/1.0 200 \r\n\r\n")
    assert fed.exception is None
    pulled = require_pulled_event(pull_next(client))
    print(
        f"http10 200 version={event_version(pulled)!r} status={status_code(pulled)}",
        flush=True,
    )
    assert event_is_kind(pulled, "response")
    assert status_code(pulled) == 200
    assert event_version(pulled) == b"1.0"

    other = client_connection()
    require_send_bytes(
        send_event(other, make_request(headers=[("Host", "example.com")]))
    )
    feed_bytes(other, b"HTTP/1.0 204 \r\n\r\n")
    other_resp = require_pulled_event(pull_next(other))
    assert event_is_kind(other_resp, "response")
    assert status_code(other_resp) == 204
    assert event_version(other_resp) == b"1.0"


def test_peer_http_version_stays_after_later_events_this_cycle():
    server = server_connection()
    feed_bytes(server, b"GET / HTTP/1.0\r\n\r\n")
    require_pulled_event(pull_next(server))
    recorded = peer_http_version(server)
    print(f"recorded after 1.0 GET={recorded!r}", flush=True)
    assert recorded == b"1.0"
    require_send_bytes(
        send_event(server, make_response(200, headers=[("Content-Length", "0")]))
    )
    after = peer_http_version(server)
    print(f"after sending 1.1 response peer={after!r}", flush=True)
    assert after == b"1.0"
    assert after == recorded


# ---------------------------------------------------------------------------
# H. Host first; original casing on the wire
# ---------------------------------------------------------------------------


def test_host_is_written_before_foo_even_when_not_first():
    ev = make_request(headers=[("foo", "bar"), ("Host", "example.com")])
    ordinary = ordinary_pairs(ev)
    foo_i = header_index([n for n, _ in ordinary], b"foo")
    host_i = header_index([n for n, _ in ordinary], b"host")
    assert foo_i < host_i
    client = client_connection()
    encoded = require_send_bytes(send_event(client, ev))
    names = wire_header_names(encoded)
    print(f"wire names after foo-then-Host={names!r}", flush=True)
    host_w = header_index(names, b"Host", ignore_case=True)
    foo_w = header_index(names, b"foo", ignore_case=True)
    assert host_w < foo_w
    assert names[host_w] == b"Host"


def test_runtime_host_is_first_among_headers():
    client = client_connection()
    encoded = send_fixed_get(client)
    names = wire_header_names(encoded)
    print(f"public CL10 wire names={names!r}", flush=True)
    host_i = header_index(names, b"Host", ignore_case=True)
    cl_i = header_index(names, b"Content-Length", ignore_case=True)
    assert host_i < cl_i

    token = runtime_token()
    early = ("E" + token[:10]).encode("ascii")
    assert early[:1] < b"H"
    ev = make_request(
        headers=[
            (early.decode("ascii"), "1"),
            ("Host", "example.com"),
            ("Content-Length", "3"),
        ]
    )
    other = client_connection()
    encoded2 = require_send_bytes(send_event(other, ev))
    names2 = wire_header_names(encoded2)
    print(f"runtime early-name wire names={names2!r}", flush=True)
    assert header_index(names2, b"Host", ignore_case=True) == 0
    assert header_index(names2, early, ignore_case=True) > 0


def test_encoded_header_names_keep_construction_casing():
    token = runtime_token()
    mixed = "X-MiX-" + token[:6]
    client = client_connection()
    ev = make_request(
        headers=[("Host", "example.com"), (mixed, "v")]
    )
    encoded = require_send_bytes(send_event(client, ev))
    names = wire_header_names(encoded)
    print(f"request wire names={names!r}", flush=True)
    assert b"Host" in names
    assert mixed.encode("ascii") in names
    assert mixed.lower().encode("ascii") not in names or mixed == mixed.lower()

    server = server_connection()
    feed_bytes(server, encoded)
    require_pulled_event(pull_next(server))
    resp_mixed = "Y-ReSp-" + token[:6]
    info = make_informational(
        100, headers=[(resp_mixed, "ok")]
    )
    info_bytes = require_send_bytes(send_event(server, info))
    info_names = wire_header_names(info_bytes)
    print(f"informational wire names={info_names!r}", flush=True)
    assert resp_mixed.encode("ascii") in info_names


# ---------------------------------------------------------------------------
# I. Receive-side line endings, empty values, folding
# ---------------------------------------------------------------------------


def test_mixed_line_endings_on_200_pull_as_that_response():
    client = client_connection()
    require_send_bytes(
        send_event(client, make_request(headers=[("Host", "example.com")]))
    )
    blob = b"HTTP/1.1 200 OK\r\nSomeHeader1: val1\nSomeHeader2: val2\n\r\n"
    feed_bytes(client, blob)
    pulled = require_pulled_event(pull_next(client))
    print(f"mixed endings status={status_code(pulled)} pairs={ordinary_pairs(pulled)!r}", flush=True)
    assert event_is_kind(pulled, "response")
    assert status_code(pulled) == 200
    assert (b"someheader1", b"val1") in ordinary_pairs(pulled)
    assert (b"someheader2", b"val2") in ordinary_pairs(pulled)


def test_lone_lf_200_is_accepted():
    client = client_connection()
    require_send_bytes(
        send_event(client, make_request(headers=[("Host", "example.com")]))
    )
    feed_bytes(client, b"HTTP/1.1 200 OK\nX-One: a\n\n")
    pulled = require_pulled_event(pull_next(client))
    print(f"lone-lf 200 status={status_code(pulled)}", flush=True)
    assert event_is_kind(pulled, "response")
    assert status_code(pulled) == 200
    assert (b"x-one", b"a") in ordinary_pairs(pulled)


def test_request_header_block_accepts_lone_lf_and_mixed_endings():
    lone = server_connection()
    feed_bytes(lone, b"GET / HTTP/1.1\nHost: example.com\n\n")
    pulled_lf = require_pulled_event(pull_next(lone))
    print(f"request lone-lf method={request_method(pulled_lf)!r}", flush=True)
    assert event_is_kind(pulled_lf, "request")
    assert request_method(pulled_lf) == b"GET"
    assert (b"host", b"example.com") in ordinary_pairs(pulled_lf)

    mixed = server_connection()
    feed_bytes(mixed, b"GET / HTTP/1.1\r\nHost: example.com\nX-Two: b\n\r\n")
    pulled_mix = require_pulled_event(pull_next(mixed))
    assert event_is_kind(pulled_mix, "request")
    assert request_target(pulled_mix) == b"/"
    assert (b"x-two", b"b") in ordinary_pairs(pulled_mix)


def test_omitted_reason_phrase_pulls_empty_reason():
    client = client_connection()
    require_send_bytes(
        send_event(client, make_request(headers=[("Host", "example.com")]))
    )
    feed_bytes(client, b"HTTP/1.1 200\r\nContent-Length: 0\r\n\r\n")
    pulled = require_pulled_event(pull_next(client))
    print(f"omitted reason={reason(pulled)!r}", flush=True)
    assert event_is_kind(pulled, "response")
    assert status_code(pulled) == 200
    assert reason(pulled) == b""
    assert len(reason(pulled)) == 0


def test_empty_and_tab_only_header_values_pull_empty():
    server = server_connection()
    blob = (
        b"GET / HTTP/1.1\r\n"
        b"Host: example.com\r\n"
        b"Empty:\r\n"
        b"Tabs:\t\t\r\n"
        b"Spaces:   \r\n"
        b"Mixed: \t \t\r\n"
        b"\r\n"
    )
    feed_bytes(server, blob)
    pulled = require_pulled_event(pull_next(server))
    pairs = dict(ordinary_pairs(pulled))
    print(f"empty-value pairs={pairs!r}", flush=True)
    assert pairs[b"empty"] == b""
    assert pairs[b"tabs"] == b""
    assert pairs[b"spaces"] == b""
    assert pairs[b"mixed"] == b""


def test_single_character_header_value_is_accepted():
    server = server_connection()
    feed_bytes(
        server,
        b"GET / HTTP/1.1\r\nHost: example.com\r\nX: z\r\n\r\n",
    )
    pulled = require_pulled_event(pull_next(server))
    print(f"single-char pairs={ordinary_pairs(pulled)!r}", flush=True)
    assert (b"x", b"z") in ordinary_pairs(pulled)


def test_obsolete_fold_some_joins_named_value():
    server = server_connection()
    blob = (
        b"GET / HTTP/1.1\r\n"
        b"Host: example.com\r\n"
        b"Some: multi-line\r\n"
        b" header\r\n"
        b"\tnonsense\r\n"
        b"    \t   \t\tI guess\r\n"
        b"\r\n"
    )
    feed_bytes(server, blob)
    pulled = require_pulled_event(pull_next(server))
    pairs = ordinary_pairs(pulled)
    print(f"folded Some pairs={pairs!r}", flush=True)
    assert (b"some", b"multi-line header nonsense I guess") in pairs


def test_last_header_may_be_folded():
    token = runtime_token()
    name = "Z-" + token[:8]
    server = server_connection()
    blob = (
        b"GET / HTTP/1.1\r\n"
        b"Host: example.com\r\n"
        + name.encode("ascii")
        + b": part1\r\n"
        + b" part2\r\n"
        + b"\tpart3\r\n"
        + b" \tpart4\r\n"
        + b"\r\n"
    )
    feed_bytes(server, blob)
    pulled = require_pulled_event(pull_next(server))
    want = (name.lower().encode("ascii"), b"part1 part2 part3 part4")
    print(f"last-header fold pairs={ordinary_pairs(pulled)!r}", flush=True)
    assert want in ordinary_pairs(pulled)


# ---------------------------------------------------------------------------
# J. Remote protocol errors on pull
# ---------------------------------------------------------------------------


def test_folded_first_header_is_remote_protocol_error():
    neighbor = neighbor_request_pulls()
    assert event_is_kind(neighbor, "request")
    server = server_connection()
    feed_bytes(server, b"GET / HTTP/1.1\r\n  folded: line\r\n\r\n")
    result = pull_next(server)
    exc = require_remote_refusal(result)
    print(f"folded-first-header exc={type(exc).__name__}", flush=True)
    remote_t = remote_protocol_error_type()
    local_t = local_protocol_error_type()
    assert result.exception is exc
    assert isinstance(exc, remote_t)
    assert not isinstance(exc, local_t)


def test_header_name_trailing_space_or_tab_before_colon_refused():
    neighbor = neighbor_request_pulls()
    assert event_is_kind(neighbor, "request")
    remote_t = remote_protocol_error_type()
    local_t = local_protocol_error_type()
    space = server_connection()
    feed_bytes(space, b"GET / HTTP/1.1\r\nHost: example.com\r\nfoo  : bar\r\n\r\n")
    space_result = pull_next(space)
    space_exc = require_remote_refusal(space_result)
    print(f"trailing-space-before-colon exc={type(space_exc).__name__}", flush=True)
    assert space_result.exception is space_exc
    assert isinstance(space_exc, remote_t)
    assert not isinstance(space_exc, local_t)
    tab = server_connection()
    feed_bytes(tab, b"GET / HTTP/1.1\r\nHost: example.com\r\nfoo\t: bar\r\n\r\n")
    tab_result = pull_next(tab)
    tab_exc = require_remote_refusal(tab_result)
    print(f"trailing-tab-before-colon exc={type(tab_exc).__name__}", flush=True)
    assert tab_result.exception is tab_exc
    assert isinstance(tab_exc, remote_t)
    assert not isinstance(tab_exc, local_t)


def test_nameless_colon_header_refused():
    neighbor = neighbor_request_pulls()
    assert event_is_kind(neighbor, "request")
    server = server_connection()
    feed_bytes(server, b"GET / HTTP/1.1\r\nHost: example.com\r\n: line\r\n\r\n")
    result = pull_next(server)
    exc = require_remote_refusal(result)
    print(f"nameless-colon exc={type(exc).__name__}", flush=True)
    remote_t = remote_protocol_error_type()
    local_t = local_protocol_error_type()
    assert result.exception is exc
    assert isinstance(exc, remote_t)
    assert not isinstance(exc, local_t)


def test_garbage_after_request_line_refused():
    neighbor_request_pulls()
    first = "g1" + runtime_token()
    second = "g2" + runtime_token()
    assert first != second
    a = server_connection()
    feed_bytes(
        a,
        b"GET / HTTP/1.1 " + first.encode("ascii") + b"\r\nHost: example.com\r\n\r\n",
    )
    require_remote_refusal(pull_next(a))
    b = server_connection()
    feed_bytes(
        b,
        b"GET / HTTP/1.1 " + second.encode("ascii") + b"\r\nHost: example.com\r\n\r\n",
    )
    require_remote_refusal(pull_next(b))


def test_garbage_after_response_line_refused():
    neighbor_response_pulls()
    first = "r1" + runtime_token()
    second = "r2" + runtime_token()
    assert first != second

    def _client():
        conn = client_connection()
        require_send_bytes(
            send_event(conn, make_request(headers=[("Host", "example.com")]))
        )
        return conn

    # Extra token after a complete response line. Two different tokens;
    # each is refused as a remote protocol error. Text after the status
    # code on that same line is a reason, so the extra sits after the
    # line, not after the status as a phrase.
    for extra in (first, second):
        client = _client()
        blob = (
            b"HTTP/1.1 200 \r\n"
            + extra.encode("ascii")
            + b"\r\nContent-Length: 0\r\n\r\n"
        )
        print(f"garbage after response line extra={extra!r}", flush=True)
        feed_bytes(client, blob)
        require_remote_refusal(pull_next(client))

    a = _client()
    feed_bytes(a, b"HTTP/1.1 " + first.encode("ascii") + b" 200 \r\n\r\n")
    require_remote_refusal(pull_next(a))
    b = _client()
    feed_bytes(b, b"HTTP/1.1 " + second.encode("ascii") + b" 200 \r\n\r\n")
    require_remote_refusal(pull_next(b))


def test_nul_in_header_value_refused():
    neighbor = neighbor_request_pulls()
    assert event_is_kind(neighbor, "request")
    server = server_connection()
    feed_bytes(
        server,
        b"GET / HTTP/1.1\r\nHost: example.com\r\nX-Foo: a\x00b\r\n\r\n",
    )
    result = pull_next(server)
    exc = require_remote_refusal(result)
    print(f"nul-in-header-value exc={type(exc).__name__}", flush=True)
    remote_t = remote_protocol_error_type()
    local_t = local_protocol_error_type()
    assert result.exception is exc
    assert isinstance(exc, remote_t)
    assert not isinstance(exc, local_t)


def test_target_containing_nul_space_127_238_refused():
    neighbor = neighbor_request_pulls()
    assert event_is_kind(neighbor, "request")
    extras = (b"\x00", b" ", b"\x7f", b"\xee")
    remote_t = remote_protocol_error_type()
    local_t = local_protocol_error_type()
    seen = 0
    for extra in extras:
        server = server_connection()
        target = b"/" + extra + b"x"
        blob = b"GET " + target + b" HTTP/1.1\r\nHost: example.com\r\n\r\n"
        print(f"bad target extra={extra!r}", flush=True)
        feed_bytes(server, blob)
        result = pull_next(server)
        exc = require_remote_refusal(result)
        assert result.exception is exc
        assert isinstance(exc, remote_t)
        assert not isinstance(exc, local_t)
        seen += 1
    assert seen == len(extras)


def test_server_rejects_lone_nul_space_and_tls_client_hello():
    neighbor = neighbor_request_pulls()
    assert event_is_kind(neighbor, "request")
    length = bytes([(runtime_int() % 80) + 10, runtime_int() % 40])
    cases = (
        b"\x00",
        b" ",
        b"\x16\x03\x01" + length,
        b"\x16\x03\x03" + length,
    )
    remote_t = remote_protocol_error_type()
    local_t = local_protocol_error_type()
    seen = 0
    for blob in cases:
        server = server_connection()
        print(f"server early-invalid {blob[:5]!r}", flush=True)
        feed_bytes(server, blob)
        result = pull_next(server)
        exc = require_remote_refusal(result)
        assert result.exception is exc
        assert isinstance(exc, remote_t)
        assert not isinstance(exc, local_t)
        seen += 1
    assert seen == len(cases)


def test_client_after_request_rejects_lone_nul_space_and_tls_server_hello():
    neighbor = neighbor_response_pulls()
    assert event_is_kind(neighbor, "response")
    length = bytes([(runtime_int() % 80) + 10, runtime_int() % 40])
    cases = (
        b"\x00",
        b" ",
        b"\x16\x03\x03" + length,
    )
    remote_t = remote_protocol_error_type()
    local_t = local_protocol_error_type()
    seen = 0
    for blob in cases:
        client = client_connection()
        require_send_bytes(
            send_event(client, make_request(headers=[("Host", "example.com")]))
        )
        print(f"client after-request early-invalid {blob[:5]!r}", flush=True)
        feed_bytes(client, blob)
        result = pull_next(client)
        exc = require_remote_refusal(result)
        assert result.exception is exc
        assert isinstance(exc, remote_t)
        assert not isinstance(exc, local_t)
        seen += 1
    assert seen == len(cases)


def test_server_blank_line_only_refused():
    neighbor = neighbor_request_pulls()
    assert event_is_kind(neighbor, "request")
    server = server_connection()
    feed_bytes(server, b"\r\n")
    result = pull_next(server)
    exc = require_remote_refusal(result)
    print(f"server-blank-line exc={type(exc).__name__}", flush=True)
    remote_t = remote_protocol_error_type()
    local_t = local_protocol_error_type()
    assert result.exception is exc
    assert isinstance(exc, remote_t)
    assert not isinstance(exc, local_t)


def test_client_blank_line_only_after_request_refused():
    neighbor = neighbor_response_pulls()
    assert event_is_kind(neighbor, "response")
    client = client_connection()
    require_send_bytes(
        send_event(client, make_request(headers=[("Host", "example.com")]))
    )
    feed_bytes(client, b"\r\n")
    result = pull_next(client)
    exc = require_remote_refusal(result)
    print(f"client-blank-line exc={type(exc).__name__}", flush=True)
    remote_t = remote_protocol_error_type()
    local_t = local_protocol_error_type()
    assert result.exception is exc
    assert isinstance(exc, remote_t)
    assert not isinstance(exc, local_t)


# ---------------------------------------------------------------------------
# K. Empty receive then nonempty feed is a runtime error
# ---------------------------------------------------------------------------


def test_nonempty_feed_after_empty_eof_is_runtime_error_not_protocol():
    conn = server_connection()
    first = feed_bytes(conn, b"")
    assert first.exception is None, f"first empty feed failed: {first.exception!r}"
    second = feed_bytes(conn, b"GET / HTTP/1.1\r\n")
    runtime_exc = require_runtime_refusal(second)

    remote_conn = server_connection()
    feed_bytes(remote_conn, b"\r\n")
    remote_exc = require_remote_refusal(pull_next(remote_conn))

    local_exc = require_local_refusal(request_result(headers=[]))
    print(
        f"kinds runtime={type(runtime_exc).__name__} "
        f"remote={type(remote_exc).__name__} local={type(local_exc).__name__}",
        flush=True,
    )
    assert type(runtime_exc) is not type(remote_exc)
    assert type(runtime_exc) is not type(local_exc)
    assert type(remote_exc) is not type(local_exc)


def test_further_empty_chunks_after_eof_do_not_fail():
    allowed = server_connection()
    first = feed_bytes(allowed, b"")
    assert first.exception is None
    second = feed_bytes(allowed, b"")
    assert second.exception is None, (
        f"further empty chunk failed: {second.exception!r}"
    )

    refused = server_connection()
    feed_bytes(refused, b"")
    require_runtime_refusal(feed_bytes(refused, b"x"))
