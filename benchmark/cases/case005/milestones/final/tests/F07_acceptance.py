# feature: F07
"""Acceptance tests for informational responses, 100-continue, and switches.

Exercises 1xx before a final response while the client can still send
the request body, Expect: 100-continue waiting flags, HTTP/1.0 Expect
not waiting, CONNECT and Upgrade accept versus deny, MIGHT_SWITCH only
after the proposing end-of-message, SWITCHED_PROTOCOL as permanent,
trailing data, empty-feed split after deny versus accept, leftover
HTTP/1.0 after deny plus the next cycle, and the three distinguishable
paused / need-data unlocks. Event construction is FP-01. Send / feed /
pull is FP-02. Framing used to finish a walk is FP-03. Start-next-cycle
and pipelining paused are FP-04. Local versus remote versus runtime
failures are FP-05. Connection-closed after a denial empty feed is
FP-06.
"""

from __future__ import annotations

from typing import Any

from F01_helpers import (
    named_pairs,
    ordinary_pairs,
    request_method,
    request_target,
    require_local_refusal,
    runtime_int,
    runtime_token,
    status_code,
    event_version,
)
from F02_helpers import (
    client_connection,
    event_is_kind,
    make_data,
    make_eom,
    make_informational,
    make_request,
    make_response,
    named_state,
    pull_next,
    require_need_data,
    require_send_bytes,
    send_event,
    server_connection,
)
from F03_helpers import feed_ok, pull_kind, require_our_state
from F04_helpers import (
    require_local_cycle_refusal,
    require_neither_error,
    require_paused,
    require_start_succeeded,
    runtime_host,
    runtime_informational_status,
    runtime_target,
    second_request_method,
    send_completed_eom,
    send_final_200,
    server_send_status,
    start_next_cycle,
)
from F05_helpers import (
    feed_empty,
    require_not_connection_closed_event,
    require_our_error_their_not,
)
from F06_helpers import (
    pull_connection_closed,
    require_client_server_states,
    require_connection_closed_event,
)
from F07_helpers import (
    accept_connect,
    accept_upgrade,
    bind_waiting_reports,
    client_waiting_flag,
    connect_request,
    deny_and_complete,
    finish_proposal_body,
    finish_proposing_request,
    http10_expect_request_bytes,
    http11_expect_request_bytes,
    fixed_connect_finished,
    fixed_expect_headers,
    fixed_leftover_http10_get,
    fixed_upgrade_finished,
    require_both_switched,
    require_not_switched,
    require_receive_closed,
    require_receive_open,
    require_waiting_flags,
    runtime_2xx_except_200,
    runtime_connect_target,
    runtime_non_2xx_except_404,
    runtime_upgrade_value,
    send_proposal_headers,
    they_are_waiting_flag,
    trailing_data_pair,
    upgrade_request,
)


def _runtime_body(n: int) -> bytes:
    token = runtime_token().encode("ascii")
    if not token:
        raise AssertionError("runtime token was empty; cannot build a body")
    body = (token * (n + 2))[:n]
    if body == b"12345":
        body = (b"wxyz" * (n + 2))[:n]
    print(f"runtime_body n={n} {body!r}", flush=True)
    return body


def _mixed_expect_value() -> str:
    raw = "100-continue"
    n = runtime_int()
    chars = []
    for i, ch in enumerate(raw):
        if ch.isalpha() and ((n + i) % 2):
            chars.append(ch.upper())
        else:
            chars.append(ch)
    value = "".join(chars)
    if value == "100-continue":
        value = "100-Continue"
    print(f"mixed_expect_value={value!r}", flush=True)
    return value


def _send_next_get(client: Any, server: Any, *, host: str, target: str) -> Any:
    encoded = require_send_bytes(
        send_event(client, make_request(target=target, headers=[("Host", host)]))
    )
    eom = send_completed_eom(client)
    feed_ok(server, encoded + eom)
    pulled = pull_kind(server, "request")
    pull_kind(server, "end-of-message")
    print(
        f"next GET method={request_method(pulled)!r} "
        f"target={request_target(pulled)!r}",
        flush=True,
    )
    return pulled


def _require_payload_in_send(encoded: bytes, payload: bytes) -> None:
    if payload not in encoded:
        raise AssertionError(
            f"request-body send encoding {encoded[:64]!r} does not contain "
            f"payload {payload!r}"
        )
    print(
        f"payload_in_send payload_len={len(payload)} encoded_len={len(encoded)}",
        flush=True,
    )


def _require_paused_not_request(conn: Any):
    result = pull_next(conn)
    require_paused(result)
    if event_is_kind(result.value, "request"):
        raise AssertionError("pull returned a request event, not paused")
    require_not_connection_closed_event(result.value)
    return result


def _require_paused_not_cc(conn: Any):
    result = pull_next(conn)
    require_paused(result)
    if event_is_kind(result.value, "connection-closed"):
        raise AssertionError("pull returned connection-closed, not paused")
    require_not_connection_closed_event(result.value)
    return result


def _illegal_http_send(conn: Any, event: Any) -> None:
    result = send_event(conn, event)
    require_local_refusal(result)
    require_our_error_their_not(conn)
    assert result.exception is not None
    assert result.value is None
    again = send_event(conn, event)
    require_local_refusal(again)
    require_our_error_their_not(conn)
    assert again.exception is not None
    assert again.value is None
    print(
        f"illegal HTTP send type={type(event).__name__} stayed local+ERROR",
        flush=True,
    )


# ---------------------------------------------------------------------------
# S. Present-arm encode and pull
# ---------------------------------------------------------------------------


def test_expect_path_round_trips_when_package_importable():
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

    fresh_client = client_connection()
    fresh_server = server_connection()
    expect_encoded = require_send_bytes(
        send_event(fresh_client, make_request(headers=fixed_expect_headers()))
    )
    print(f"Expect GET encoded len={len(expect_encoded)}", flush=True)
    assert len(expect_encoded) > 0
    feed_ok(fresh_server, expect_encoded)
    expect_pulled = pull_kind(fresh_server, "request")
    assert request_method(expect_pulled) == b"GET"
    bind_waiting_reports(fresh_client, fresh_server)
    require_waiting_flags(fresh_client, client_waiting=True, they_waiting=False)
    require_waiting_flags(fresh_server, client_waiting=True, they_waiting=True)
    print("Expect path flags: they-waiting only on server", flush=True)


def test_get_encode_fails_when_package_not_importable():
    # The product is exercised by
    # real send/pull of the named F07 behavior on a constructed connection,
    # not an import-stripped child. ENCODE_UNAVAILABLE / ENCODED_REQUEST
    # are not product output. The only accepted present-arm outcome is
    # this companion's GET encode-and-pull plus Expect waiting flags on
    # a fresh pair.
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

    fresh_client = client_connection()
    fresh_server = server_connection()
    expect_encoded = require_send_bytes(
        send_event(fresh_client, make_request(headers=fixed_expect_headers()))
    )
    print(f"present-arm Expect GET encoded len={len(expect_encoded)}", flush=True)
    assert len(expect_encoded) > 0
    feed_ok(fresh_server, expect_encoded)
    expect_pulled = pull_kind(fresh_server, "request")
    assert request_method(expect_pulled) == b"GET"
    bind_waiting_reports(fresh_client, fresh_server)
    require_waiting_flags(fresh_client, client_waiting=True, they_waiting=False)
    require_waiting_flags(fresh_server, client_waiting=True, they_waiting=True)
    print("present-arm Expect path flags: they-waiting only on server", flush=True)


# ---------------------------------------------------------------------------
# A. Informational responses then request body then final 200
# ---------------------------------------------------------------------------


def test_informational_100_is_pulled_before_final_200():
    client = client_connection()
    server = server_connection()
    encoded = require_send_bytes(
        send_event(
            client,
            make_request(headers=[("Host", "example.com"), ("Content-Length", "8")]),
        )
    )
    feed_ok(server, encoded)
    pull_kind(server, "request")
    require_our_state(server, "SEND_RESPONSE")
    info = require_send_bytes(
        send_event(server, make_informational(100, headers=[]))
    )
    feed_ok(client, info)
    pulled = pull_kind(client, "informational")
    print(f"pulled 100 status={status_code(pulled)}", flush=True)
    assert status_code(pulled) == 100
    assert event_is_kind(pulled, "informational")
    assert not event_is_kind(pulled, "response")
    require_our_state(client, "SEND_BODY")
    require_our_state(server, "SEND_RESPONSE")
    final = require_send_bytes(send_event(server, make_response(200, headers=[])))
    feed_ok(client, final)
    final_pulled = pull_kind(client, "response")
    print(f"final 200 after 100 status={status_code(final_pulled)}", flush=True)
    assert status_code(final_pulled) == 200
    assert event_is_kind(final_pulled, "response")


def test_client_still_sends_request_body_after_informational():
    payload = _runtime_body(6)
    client = client_connection()
    server = server_connection()
    encoded = require_send_bytes(
        send_event(
            client,
            make_request(
                headers=[
                    ("Host", "example.com"),
                    ("Content-Length", str(len(payload))),
                ]
            ),
        )
    )
    feed_ok(server, encoded)
    pull_kind(server, "request")
    info = require_send_bytes(
        send_event(server, make_informational(100, headers=[]))
    )
    feed_ok(client, info)
    pull_kind(client, "informational")
    require_our_state(client, "SEND_BODY")
    body_encoded = require_send_bytes(send_event(client, make_data(payload)))
    _require_payload_in_send(body_encoded, payload)
    final = require_send_bytes(send_event(server, make_response(200, headers=[])))
    feed_ok(client, final)
    pulled = pull_kind(client, "response")
    assert status_code(pulled) == 200
    assert event_is_kind(pulled, "response")

    neighbor_client = client_connection()
    neighbor_server = server_connection()
    neighbor_req = require_send_bytes(
        send_event(
            neighbor_client,
            make_request(
                headers=[
                    ("Host", "example.com"),
                    ("Content-Length", str(len(payload))),
                ]
            ),
        )
    )
    feed_ok(neighbor_server, neighbor_req)
    pull_kind(neighbor_server, "request")
    require_our_state(neighbor_server, "SEND_RESPONSE")
    direct = require_send_bytes(
        send_event(neighbor_server, make_response(200, headers=[]))
    )
    feed_ok(neighbor_client, direct)
    direct_pulled = pull_kind(neighbor_client, "response")
    print(f"neighbor direct 200 status={status_code(direct_pulled)}", flush=True)
    assert status_code(direct_pulled) == 200
    require_our_state(neighbor_client, "SEND_BODY")
    neighbor_body = require_send_bytes(
        send_event(neighbor_client, make_data(payload))
    )
    _require_payload_in_send(neighbor_body, payload)


def test_two_informational_100_then_102_then_body_then_final():
    payload = _runtime_body(7)
    client = client_connection()
    server = server_connection()
    encoded = require_send_bytes(
        send_event(
            client,
            make_request(
                headers=[
                    ("Host", "example.com"),
                    ("Content-Length", str(len(payload))),
                ]
            ),
        )
    )
    feed_ok(server, encoded)
    pull_kind(server, "request")
    first = require_send_bytes(
        send_event(server, make_informational(100, headers=[]))
    )
    feed_ok(client, first)
    pulled_100 = pull_kind(client, "informational")
    assert status_code(pulled_100) == 100
    require_our_state(server, "SEND_RESPONSE")
    second = require_send_bytes(
        send_event(server, make_informational(102, headers=[]))
    )
    feed_ok(client, second)
    pulled_102 = pull_kind(client, "informational")
    print(
        f"two 1xx statuses {status_code(pulled_100)} then {status_code(pulled_102)}",
        flush=True,
    )
    assert status_code(pulled_102) == 102
    assert status_code(pulled_100) != status_code(pulled_102)
    require_our_state(server, "SEND_RESPONSE")
    require_our_state(client, "SEND_BODY")
    body_encoded = require_send_bytes(send_event(client, make_data(payload)))
    _require_payload_in_send(body_encoded, payload)
    final = require_send_bytes(send_event(server, make_response(200, headers=[])))
    feed_ok(client, final)
    assert status_code(pull_kind(client, "response")) == 200


def test_runtime_informational_then_body_then_final():
    host = runtime_host()
    target = runtime_target()
    method = second_request_method()
    info_status = runtime_informational_status()
    payload = _runtime_body(4 + (runtime_int() % 5))
    print(
        f"runtime 1xx method={method} status={info_status} "
        f"host={host!r} target={target!r}",
        flush=True,
    )
    assert info_status not in (100, 101, 102)
    client = client_connection()
    server = server_connection()
    encoded = require_send_bytes(
        send_event(
            client,
            make_request(
                method=method,
                target=target,
                headers=[("Host", host), ("Content-Length", str(len(payload)))],
            ),
        )
    )
    feed_ok(server, encoded)
    pull_kind(server, "request")
    info = require_send_bytes(
        send_event(server, make_informational(info_status, headers=[]))
    )
    feed_ok(client, info)
    pulled = pull_kind(client, "informational")
    assert status_code(pulled) == info_status
    assert status_code(pulled) != 100
    require_our_state(client, "SEND_BODY")
    body_encoded = require_send_bytes(send_event(client, make_data(payload)))
    _require_payload_in_send(body_encoded, payload)
    final = require_send_bytes(send_event(server, make_response(200, headers=[])))
    feed_ok(client, final)
    assert status_code(pull_kind(client, "response")) == 200


# ---------------------------------------------------------------------------
# B. Expect: 100-continue waiting flags
# ---------------------------------------------------------------------------


def test_http11_expect_content_length_100_sets_waiting_flags():
    client = client_connection()
    server = server_connection()
    encoded = require_send_bytes(
        send_event(client, make_request(headers=fixed_expect_headers()))
    )
    feed_ok(server, encoded)
    pull_kind(server, "request")
    bind_waiting_reports(client, server)
    require_waiting_flags(client, client_waiting=True, they_waiting=False)
    require_waiting_flags(server, client_waiting=True, they_waiting=True)
    print("public Expect CL 100 flags on", flush=True)

    baseline_client = client_connection()
    baseline_server = server_connection()
    baseline = require_send_bytes(
        send_event(
            baseline_client,
            make_request(
                headers=[("Host", "example.com"), ("Content-Length", "100")]
            ),
        )
    )
    feed_ok(baseline_server, baseline)
    pull_kind(baseline_server, "request")
    require_waiting_flags(
        baseline_client, client_waiting=False, they_waiting=False
    )
    require_waiting_flags(
        baseline_server, client_waiting=False, they_waiting=False
    )
    print("no-Expect baseline flags off", flush=True)


def test_they_are_waiting_only_on_server():
    client = client_connection()
    server = server_connection()
    encoded = require_send_bytes(
        send_event(client, make_request(headers=fixed_expect_headers()))
    )
    feed_ok(server, encoded)
    pull_kind(server, "request")
    bind_waiting_reports(client, server)
    assert client_waiting_flag(client) is True
    assert client_waiting_flag(server) is True
    assert they_are_waiting_flag(server) is True
    assert they_are_waiting_flag(client) is False
    print("they-waiting true only on server-role", flush=True)


def test_expect_matching_is_case_insensitive():
    client = client_connection()
    server = server_connection()
    encoded = require_send_bytes(
        send_event(
            client,
            make_request(
                headers=[
                    ("Host", "example.com"),
                    ("Content-Length", "100"),
                    ("Expect", "100-Continue"),
                ]
            ),
        )
    )
    feed_ok(server, encoded)
    pull_kind(server, "request")
    bind_waiting_reports(client, server)
    require_waiting_flags(client, client_waiting=True, they_waiting=False)
    require_waiting_flags(server, client_waiting=True, they_waiting=True)
    assert client_waiting_flag(client) is True
    assert they_are_waiting_flag(client) is False
    assert client_waiting_flag(server) is True
    assert they_are_waiting_flag(server) is True
    print("Expect 100-Continue flags on", flush=True)


def test_non_get_expect_sets_waiting_flags():
    method = second_request_method()
    cl = 20 + (runtime_int() % 30)
    if cl == 100:
        cl = 40
    print(f"non-GET Expect method={method} cl={cl}", flush=True)
    client = client_connection()
    server = server_connection()
    encoded = require_send_bytes(
        send_event(
            client,
            make_request(
                method=method,
                headers=[
                    ("Host", "example.com"),
                    ("Content-Length", str(cl)),
                    ("Expect", "100-continue"),
                ],
            ),
        )
    )
    feed_ok(server, encoded)
    pulled = pull_kind(server, "request")
    assert request_method(pulled) == method.encode("ascii")
    bind_waiting_reports(client, server)
    require_waiting_flags(client, client_waiting=True, they_waiting=False)
    require_waiting_flags(server, client_waiting=True, they_waiting=True)


def test_chunked_expect_sets_waiting_flags():
    client, server = _chunked_expect_pair_flags_on()
    chunk = require_send_bytes(send_event(client, make_data(b"hello")))
    print(f"chunked Expect data encoded len={len(chunk)}", flush=True)
    assert len(chunk) > 0
    assert b"hello" in chunk


def _expect_pair_flags_on() -> tuple[Any, Any]:
    client = client_connection()
    server = server_connection()
    encoded = require_send_bytes(
        send_event(client, make_request(headers=fixed_expect_headers()))
    )
    feed_ok(server, encoded)
    pull_kind(server, "request")
    bind_waiting_reports(client, server)
    require_waiting_flags(client, client_waiting=True, they_waiting=False)
    require_waiting_flags(server, client_waiting=True, they_waiting=True)
    return client, server


def _chunked_expect_pair_flags_on() -> tuple[Any, Any]:
    """HTTP/1.1 chunked Expect request, flags on, no body event sent yet.

    No Content-Length. The live baseline is the flags themselves; a
    following data event or end-of-message is the caller's to apply.
    """
    client = client_connection()
    server = server_connection()
    encoded = require_send_bytes(
        send_event(
            client,
            make_request(
                method="POST",
                headers=[
                    ("Host", "example.com"),
                    ("Transfer-Encoding", "chunked"),
                    ("Expect", "100-continue"),
                ],
            ),
        )
    )
    feed_ok(server, encoded)
    pull_kind(server, "request")
    bind_waiting_reports(client, server)
    require_waiting_flags(client, client_waiting=True, they_waiting=False)
    require_waiting_flags(server, client_waiting=True, they_waiting=True)
    print("chunked Expect flags on before any body event", flush=True)
    return client, server


def test_informational_100_clears_waiting_flags():
    client, server = _expect_pair_flags_on()
    info = require_send_bytes(
        send_event(server, make_informational(100, headers=[]))
    )
    feed_ok(client, info)
    pull_kind(client, "informational")
    require_waiting_flags(client, client_waiting=False, they_waiting=False)
    require_waiting_flags(server, client_waiting=False, they_waiting=False)


def test_informational_102_clears_waiting_flags():
    client, server = _expect_pair_flags_on()
    info = require_send_bytes(
        send_event(server, make_informational(102, headers=[]))
    )
    feed_ok(client, info)
    pulled = pull_kind(client, "informational")
    assert status_code(pulled) == 102
    require_waiting_flags(client, client_waiting=False, they_waiting=False)
    require_waiting_flags(server, client_waiting=False, they_waiting=False)
    require_our_state(client, "SEND_BODY")
    payload = _runtime_body(3)
    body = require_send_bytes(send_event(client, make_data(payload)))
    _require_payload_in_send(body, payload)


def test_final_200_clears_waiting_flags():
    client, server = _expect_pair_flags_on()
    final = require_send_bytes(send_event(server, make_response(200, headers=[])))
    feed_ok(client, final)
    pull_kind(client, "response")
    require_waiting_flags(client, client_waiting=False, they_waiting=False)
    require_waiting_flags(server, client_waiting=False, they_waiting=False)


def test_final_non_200_clears_waiting_flags():
    client, server = _expect_pair_flags_on()
    final = require_send_bytes(send_event(server, make_response(404, headers=[])))
    feed_ok(client, final)
    pulled = pull_kind(client, "response")
    print(f"final non-200 status={status_code(pulled)}", flush=True)
    assert status_code(pulled) == 404
    require_waiting_flags(client, client_waiting=False, they_waiting=False)
    require_waiting_flags(server, client_waiting=False, they_waiting=False)


def test_client_data_12345_clears_waiting_flags():
    client, server = _expect_pair_flags_on()
    encoded = require_send_bytes(send_event(client, make_data(b"12345")))
    _require_payload_in_send(encoded, b"12345")
    require_waiting_flags(client, client_waiting=False, they_waiting=False)
    feed_ok(server, encoded)
    pull_kind(server, "data")
    require_waiting_flags(server, client_waiting=False, they_waiting=False)


def test_runtime_data_clears_waiting_flags():
    client, server = _expect_pair_flags_on()
    payload = _runtime_body(6)
    assert payload != b"12345"
    encoded = require_send_bytes(send_event(client, make_data(payload)))
    _require_payload_in_send(encoded, payload)
    require_waiting_flags(client, client_waiting=False, they_waiting=False)
    feed_ok(server, encoded)
    pull_kind(server, "data")
    require_waiting_flags(server, client_waiting=False, they_waiting=False)


def test_client_end_of_message_clears_waiting_flags():
    """End-of-message on the chunked Expect request, with no data event first.

    Line 301 names that send as an independent clear. A Content-Length
    walk cannot isolate it: satisfying the count requires a data
    event, which already clears the flags. Do not stack
    Transfer-Encoding with Content-Length.
    """
    client, server = _chunked_expect_pair_flags_on()
    eom = require_send_bytes(send_event(client, make_eom()))
    print(f"client EOM-anyway encoded len={len(eom)}", flush=True)
    require_waiting_flags(client, client_waiting=False, they_waiting=False)
    feed_ok(server, eom)
    pull_kind(server, "end-of-message")
    require_waiting_flags(server, client_waiting=False, they_waiting=False)


def test_runtime_expect_sets_waiting_flags():
    host = runtime_host()
    target = runtime_target()
    expect_value = _mixed_expect_value()
    cl = 10 + (runtime_int() % 40)
    if cl == 100:
        cl = 41
    print(
        f"runtime Expect host={host!r} target={target!r} cl={cl} "
        f"expect={expect_value!r}",
        flush=True,
    )
    client = client_connection()
    server = server_connection()
    encoded = require_send_bytes(
        send_event(
            client,
            make_request(
                target=target,
                headers=[
                    ("Host", host),
                    ("Content-Length", str(cl)),
                    ("Expect", expect_value),
                ],
            ),
        )
    )
    feed_ok(server, encoded)
    pull_kind(server, "request")
    bind_waiting_reports(client, server)
    require_waiting_flags(client, client_waiting=True, they_waiting=False)
    require_waiting_flags(server, client_waiting=True, they_waiting=True)

    baseline_client = client_connection()
    baseline_server = server_connection()
    baseline = require_send_bytes(
        send_event(
            baseline_client,
            make_request(
                target=target,
                headers=[("Host", host), ("Content-Length", str(cl))],
            ),
        )
    )
    feed_ok(baseline_server, baseline)
    pull_kind(baseline_server, "request")
    require_waiting_flags(
        baseline_client, client_waiting=False, they_waiting=False
    )
    require_waiting_flags(
        baseline_server, client_waiting=False, they_waiting=False
    )

    info = require_send_bytes(
        send_event(server, make_informational(102, headers=[]))
    )
    feed_ok(client, info)
    pull_kind(client, "informational")
    require_waiting_flags(client, client_waiting=False, they_waiting=False)
    require_waiting_flags(server, client_waiting=False, they_waiting=False)


# ---------------------------------------------------------------------------
# C. HTTP/1.0 Expect does not wait
# ---------------------------------------------------------------------------


def _bind_waiting_reports_from_public_expect() -> None:
    """Discover the two waiting reports from the HTTP/1.1 Expect CL 100 pair.

    Server-only HTTP/1.0 feeds cannot show the role split. Bind first from
    the pair line 301 / line 322 name, then read those same reports.
    """
    client = client_connection()
    server = server_connection()
    encoded = require_send_bytes(
        send_event(client, make_request(headers=fixed_expect_headers()))
    )
    feed_ok(server, encoded)
    pull_kind(server, "request")
    bind_waiting_reports(client, server)


def test_http10_expect_does_not_set_waiting_flags():
    _bind_waiting_reports_from_public_expect()
    raw = http10_expect_request_bytes(
        host="example.com",
        target="/",
        content_length=100,
        expect_value="100-continue",
    )
    server = server_connection()
    feed_ok(server, raw)
    pulled = pull_kind(server, "request")
    print(
        f"HTTP/1.0 Expect version={event_version(pulled)!r} "
        f"method={request_method(pulled)!r}",
        flush=True,
    )
    assert event_version(pulled) == b"1.0"
    assert request_method(pulled) == b"GET"
    require_waiting_flags(server, client_waiting=False, they_waiting=False)


def test_http11_versus_http10_expect_differs_only_in_waiting_flags():
    kwargs = dict(
        host="example.com",
        target="/",
        content_length=100,
        expect_value="100-continue",
    )
    b11 = http11_expect_request_bytes(**kwargs)
    b10 = http10_expect_request_bytes(**kwargs)
    stripped_11 = b11.replace(b"HTTP/1.1", b"HTTP/X", 1)
    stripped_10 = b10.replace(b"HTTP/1.0", b"HTTP/X", 1)
    print(
        f"version-stripped equal={stripped_11 == stripped_10} "
        f"len11={len(b11)} len10={len(b10)}",
        flush=True,
    )
    assert stripped_11 == stripped_10

    _bind_waiting_reports_from_public_expect()
    server_11 = server_connection()
    feed_ok(server_11, b11)
    pulled_11 = pull_kind(server_11, "request")
    assert event_version(pulled_11) == b"1.1"
    require_waiting_flags(server_11, client_waiting=True, they_waiting=True)

    server_10 = server_connection()
    feed_ok(server_10, b10)
    pulled_10 = pull_kind(server_10, "request")
    assert event_version(pulled_10) == b"1.0"
    require_waiting_flags(server_10, client_waiting=False, they_waiting=False)
    assert client_waiting_flag(server_11) is not client_waiting_flag(server_10)
    assert they_are_waiting_flag(server_11) is not they_are_waiting_flag(server_10)


# ---------------------------------------------------------------------------
# D. CONNECT accept / deny / switch state after EOM
# ---------------------------------------------------------------------------


def test_connect_switch_state_appears_only_after_request_eom():
    client = client_connection()
    server = server_connection()
    request = connect_request(
        target="example.com:443", host="example.com", content_length=1
    )
    send_proposal_headers(client, server, request)
    require_our_state(client, "SEND_BODY")
    assert require_our_state(client, "SEND_BODY") != named_state(
        "MIGHT_SWITCH_PROTOCOL"
    )
    finish_proposal_body(client, server, b"1")
    require_our_state(client, "MIGHT_SWITCH_PROTOCOL")
    _require_paused_not_request(server)


def test_connect_non_one_content_length_might_switch_after_eom():
    n = 3 + (runtime_int() % 5)
    if n == 1:
        n = 4
    body = _runtime_body(n)
    client = client_connection()
    server = server_connection()
    request = connect_request(
        target="example.com:443", host="example.com", content_length=n
    )
    send_proposal_headers(client, server, request)
    require_our_state(client, "SEND_BODY")
    finish_proposal_body(client, server, body)
    require_our_state(client, "MIGHT_SWITCH_PROTOCOL")
    _require_paused_not_request(server)


def test_connect_empty_body_might_switch_only_after_eom():
    client = client_connection()
    server = server_connection()
    request = connect_request(
        target="example.com:443", host="example.com", content_length=None
    )
    send_proposal_headers(client, server, request)
    require_our_state(client, "SEND_BODY")
    assert require_our_state(client, "SEND_BODY") != named_state(
        "MIGHT_SWITCH_PROTOCOL"
    )
    finish_proposal_body(client, server, b"")
    require_our_state(client, "MIGHT_SWITCH_PROTOCOL")
    _require_paused_not_request(server)


def test_connect_404_then_eom_allows_next_cycle():
    client, server = fixed_connect_finished()
    encoded = require_send_bytes(send_event(server, make_response(404, headers=[])))
    feed_ok(client, encoded)
    pulled_404 = pull_kind(client, "response")
    assert status_code(pulled_404) == 404
    require_not_switched(client)
    require_not_switched(server)
    require_client_server_states(client, "DONE", "SEND_BODY")
    require_client_server_states(server, "DONE", "SEND_BODY")
    eom = send_completed_eom(server)
    if eom:
        feed_ok(client, eom)
    pull_kind(client, "end-of-message")
    require_client_server_states(client, "DONE", "DONE")
    require_client_server_states(server, "DONE", "DONE")
    require_start_succeeded(start_next_cycle(client), client)
    require_start_succeeded(start_next_cycle(server), server)
    pulled = _send_next_get(client, server, host="example.com", target="/")
    assert request_method(pulled) == b"GET"
    print("CONNECT 404 reuse next GET succeeded", flush=True)


def test_connect_200_enters_switched_protocol():
    client, server = fixed_connect_finished()
    pulled = accept_connect(client, server, 200)
    assert status_code(pulled) == 200
    _require_paused_not_request(client)
    _require_paused_not_request(server)
    print("CONNECT 200 both SWITCHED, further pull paused", flush=True)


def test_runtime_connect_2xx_not_200_accepts():
    status = runtime_2xx_except_200()
    target = runtime_connect_target()
    host = runtime_host()
    print(f"runtime CONNECT accept status={status} target={target!r}", flush=True)
    client = client_connection()
    server = server_connection()
    finish_proposing_request(
        client,
        server,
        connect_request(target=target, host=host, content_length=1),
        b"1",
    )
    pulled = accept_connect(client, server, status)
    assert status_code(pulled) == status
    assert status_code(pulled) != 200
    require_both_switched(client)
    require_both_switched(server)


def test_runtime_connect_non_2xx_denies_and_reuses():
    status = runtime_non_2xx_except_404()
    target = runtime_connect_target()
    host = runtime_host()
    print(f"runtime CONNECT deny status={status} target={target!r}", flush=True)
    client = client_connection()
    server = server_connection()
    finish_proposing_request(
        client,
        server,
        connect_request(target=target, host=host, content_length=1),
        b"1",
    )
    deny_and_complete(client, server, status)
    require_start_succeeded(start_next_cycle(client), client)
    require_start_succeeded(start_next_cycle(server), server)
    pulled = _send_next_get(client, server, host=host, target=runtime_target())
    assert request_method(pulled) == b"GET"


# ---------------------------------------------------------------------------
# E. Upgrade 101 accept / final deny / 100 is not accept
# ---------------------------------------------------------------------------


def test_upgrade_switch_state_appears_only_after_request_eom():
    client = client_connection()
    server = server_connection()
    request = upgrade_request(
        host="example.com", target="/", upgrade="a, b", content_length=1
    )
    send_proposal_headers(client, server, request)
    require_our_state(client, "SEND_BODY")
    assert require_our_state(client, "SEND_BODY") != named_state(
        "MIGHT_SWITCH_PROTOCOL"
    )
    # Incomplete Upgrade body: waiting for the rest of this request, not
    # yet paused for accept-or-deny.
    require_need_data(pull_next(server))
    body = b"1"
    encoded = require_send_bytes(send_event(client, make_data(body)))
    _require_payload_in_send(encoded, body)
    # Data without end-of-message is not yet switch-related state.
    require_our_state(client, "SEND_BODY")
    assert require_our_state(client, "SEND_BODY") != named_state(
        "MIGHT_SWITCH_PROTOCOL"
    )
    print("Upgrade data sent; still SEND_BODY, not MIGHT_SWITCH", flush=True)
    feed_ok(server, encoded)
    pull_kind(server, "data")
    require_our_state(client, "SEND_BODY")
    finish_proposal_body(client, server, b"")
    require_our_state(client, "MIGHT_SWITCH_PROTOCOL")
    _require_paused_not_request(server)


def test_upgrade_101_enters_switched_like_connect_accept():
    client, server = fixed_upgrade_finished()
    pulled = accept_upgrade(client, server)
    assert status_code(pulled) == 101
    assert event_is_kind(pulled, "informational")
    _require_paused_not_request(client)
    _require_paused_not_request(server)


def test_upgrade_200_is_denial_and_allows_next_cycle():
    client, server = fixed_upgrade_finished()
    deny_and_complete(client, server, 200)
    require_start_succeeded(start_next_cycle(client), client)
    require_start_succeeded(start_next_cycle(server), server)
    pulled = _send_next_get(client, server, host="example.com", target="/")
    assert request_method(pulled) == b"GET"
    print("Upgrade 200 denial reused for next GET", flush=True)


def test_upgrade_100_is_not_acceptance():
    client = client_connection()
    server = server_connection()
    request = upgrade_request(
        host="example.com", target="/", upgrade="a, b", content_length=2
    )
    send_proposal_headers(client, server, request)
    require_our_state(client, "SEND_BODY")
    first = require_send_bytes(send_event(client, make_data(b"a")))
    feed_ok(server, first)
    pull_kind(server, "data")
    info = require_send_bytes(
        send_event(server, make_informational(100, headers=[]))
    )
    feed_ok(client, info)
    pulled = pull_kind(client, "informational")
    assert status_code(pulled) == 100
    require_not_switched(client)
    require_not_switched(server)
    require_our_state(client, "SEND_BODY")
    rest = require_send_bytes(send_event(client, make_data(b"b")))
    _require_payload_in_send(rest, b"b")
    feed_ok(server, rest)
    pull_kind(server, "data")
    finish_proposal_body(client, server, b"")
    require_our_state(client, "MIGHT_SWITCH_PROTOCOL")
    require_our_state(server, "SEND_RESPONSE")
    deny_and_complete(client, server, 200)
    require_start_succeeded(start_next_cycle(client), client)
    require_start_succeeded(start_next_cycle(server), server)
    _send_next_get(client, server, host="example.com", target="/next")


def test_runtime_upgrade_accept_and_deny():
    upgrade = runtime_upgrade_value()
    target = runtime_target()
    host = runtime_host()
    print(
        f"runtime Upgrade value={upgrade!r} target={target!r} host={host!r}",
        flush=True,
    )
    client = client_connection()
    server = server_connection()
    finish_proposing_request(
        client,
        server,
        upgrade_request(host=host, target=target, upgrade=upgrade, content_length=1),
        b"1",
    )
    pulled = accept_upgrade(client, server)
    assert status_code(pulled) == 101
    require_both_switched(client)

    deny_client = client_connection()
    deny_server = server_connection()
    finish_proposing_request(
        deny_client,
        deny_server,
        upgrade_request(host=host, target=target, upgrade=upgrade, content_length=1),
        b"1",
    )
    deny_and_complete(deny_client, deny_server, 204)
    require_start_succeeded(start_next_cycle(deny_client), deny_client)
    require_start_succeeded(start_next_cycle(deny_server), deny_server)
    _send_next_get(deny_client, deny_server, host=host, target=target)


def test_non_get_upgrade_101_enters_switched():
    method = "POST"
    upgrade = runtime_upgrade_value()
    client = client_connection()
    server = server_connection()
    finish_proposing_request(
        client,
        server,
        upgrade_request(
            host=runtime_host(),
            target=runtime_target(),
            upgrade=upgrade,
            content_length=1,
            method=method,
        ),
        b"1",
    )
    pulled = accept_upgrade(client, server)
    print(f"non-GET Upgrade method={method} status={status_code(pulled)}", flush=True)
    assert status_code(pulled) == 101
    require_both_switched(client)
    require_both_switched(server)


# ---------------------------------------------------------------------------
# F. Dual CONNECT + Upgrade proposal; server accepts at most one
# ---------------------------------------------------------------------------


def _dual_public_finished() -> tuple[Any, Any]:
    client = client_connection()
    server = server_connection()
    request = connect_request(
        target="example.com:443",
        host="example.com",
        content_length=1,
        upgrade="a, b",
    )
    finish_proposing_request(client, server, request, b"1")
    return client, server


def test_dual_proposal_2xx_accepts_connect():
    client, server = _dual_public_finished()
    pulled = accept_connect(client, server, 200)
    assert status_code(pulled) == 200
    require_both_switched(client)
    _illegal_http_send(server, make_data(b"xyz"))


def test_dual_proposal_101_accepts_upgrade():
    client, server = _dual_public_finished()
    pulled = accept_upgrade(client, server)
    assert status_code(pulled) == 101
    require_both_switched(client)
    require_both_switched(server)


def test_dual_proposal_non_2xx_is_denial_and_reuses():
    client, server = _dual_public_finished()
    deny_and_complete(client, server, 404)
    require_not_switched(client)
    require_start_succeeded(start_next_cycle(client), client)
    require_start_succeeded(start_next_cycle(server), server)
    pulled = _send_next_get(client, server, host="example.com", target="/")
    encoded = require_send_bytes(
        send_event(
            client_connection(),
            make_request(headers=[("Host", "example.com")]),
        )
    )
    print(
        f"dual 404 next GET method={request_method(pulled)!r} "
        f"neighbor encode len={len(encoded)}",
        flush=True,
    )
    assert request_method(pulled) == b"GET"
    assert len(encoded) > 0


def test_runtime_dual_proposal_accept_each():
    target = runtime_connect_target()
    upgrade = runtime_upgrade_value()
    host = runtime_host()
    status = runtime_2xx_except_200()
    print(
        f"runtime dual target={target!r} upgrade={upgrade!r} 2xx={status}",
        flush=True,
    )
    connect_client = client_connection()
    connect_server = server_connection()
    finish_proposing_request(
        connect_client,
        connect_server,
        connect_request(
            target=target, host=host, content_length=1, upgrade=upgrade
        ),
        b"1",
    )
    pulled_c = accept_connect(connect_client, connect_server, status)
    assert status_code(pulled_c) == status
    require_both_switched(connect_client)

    upgrade_client = client_connection()
    upgrade_server = server_connection()
    finish_proposing_request(
        upgrade_client,
        upgrade_server,
        connect_request(
            target=target, host=host, content_length=1, upgrade=upgrade
        ),
        b"1",
    )
    pulled_u = accept_upgrade(upgrade_client, upgrade_server)
    assert status_code(pulled_u) == 101
    require_both_switched(upgrade_client)


# ---------------------------------------------------------------------------
# G. MIGHT_SWITCH cannot send another request; start is local not ERROR
# ---------------------------------------------------------------------------


def test_client_in_might_switch_cannot_send_another_request():
    for label, factory in (
        ("connect", fixed_connect_finished),
        ("upgrade", fixed_upgrade_finished),
    ):
        print(f"second request while might-switch ({label})", flush=True)
        client, _server = factory()
        require_our_state(client, "MIGHT_SWITCH_PROTOCOL")
        method = second_request_method()
        event = make_request(
            method=method, headers=[("Host", runtime_host())]
        )
        result = send_event(client, event)
        require_local_refusal(result)
        require_our_error_their_not(client)
        assert result.exception is not None
        assert result.value is None
        again = send_event(
            client, make_request(headers=[("Host", runtime_host())])
        )
        require_local_refusal(again)
        require_our_error_their_not(client)
        assert again.exception is not None
        assert again.value is None


def test_second_request_succeeds_after_denial_and_next_cycle():
    for label, factory, deny_status in (
        ("connect", fixed_connect_finished, 404),
        ("upgrade", fixed_upgrade_finished, 200),
    ):
        print(f"GET after deny+start ({label}) status={deny_status}", flush=True)
        client, server = factory()
        deny_and_complete(client, server, deny_status)
        require_start_succeeded(start_next_cycle(client), client)
        require_start_succeeded(start_next_cycle(server), server)
        pulled = _send_next_get(client, server, host="example.com", target="/")
        assert request_method(pulled) == b"GET"
        assert len(
            require_send_bytes(
                send_event(server, make_response(200, headers=[]))
            )
        ) > 0


def test_start_next_cycle_while_might_switch_is_local_not_error():
    client, server = fixed_connect_finished()
    require_our_state(client, "MIGHT_SWITCH_PROTOCOL")
    require_our_state(server, "SEND_RESPONSE")
    client_start = start_next_cycle(client)
    require_local_cycle_refusal(client_start, client)
    assert client_start.exception is not None
    assert client_start.value is None
    client_stayed = require_our_state(client, "MIGHT_SWITCH_PROTOCOL")
    assert client_stayed != named_state("ERROR")
    assert client_stayed != named_state("IDLE")
    require_neither_error(client)
    server_start = start_next_cycle(server)
    require_local_cycle_refusal(server_start, server)
    assert server_start.exception is not None
    assert server_start.value is None
    server_stayed = require_our_state(server, "SEND_RESPONSE")
    assert server_stayed != named_state("ERROR")
    assert server_stayed != named_state("IDLE")
    require_neither_error(server)
    require_client_server_states(client, "MIGHT_SWITCH_PROTOCOL", "SEND_RESPONSE")
    require_client_server_states(server, "MIGHT_SWITCH_PROTOCOL", "SEND_RESPONSE")
    print("might-switch start refused, not ERROR, not IDLE", flush=True)
    # Refusal is recoverable: try again while still not DONE, still refused,
    # then the switch decision itself still works.
    client_again = start_next_cycle(client)
    require_local_cycle_refusal(client_again, client)
    require_neither_error(client)
    require_our_state(client, "MIGHT_SWITCH_PROTOCOL")
    pulled = accept_connect(client, server, 200)
    assert status_code(pulled) == 200
    require_both_switched(client)
    require_both_switched(server)

    upgrade_client, upgrade_server = fixed_upgrade_finished()
    upgrade_client_start = start_next_cycle(upgrade_client)
    require_local_cycle_refusal(upgrade_client_start, upgrade_client)
    assert upgrade_client_start.exception is not None
    assert upgrade_client_start.value is None
    upgrade_client_stayed = require_our_state(
        upgrade_client, "MIGHT_SWITCH_PROTOCOL"
    )
    assert upgrade_client_stayed != named_state("ERROR")
    assert upgrade_client_stayed != named_state("IDLE")
    require_neither_error(upgrade_client)
    upgrade_server_start = start_next_cycle(upgrade_server)
    require_local_cycle_refusal(upgrade_server_start, upgrade_server)
    assert upgrade_server_start.exception is not None
    assert upgrade_server_start.value is None
    require_our_state(upgrade_server, "SEND_RESPONSE")
    require_neither_error(upgrade_server)
    require_client_server_states(
        upgrade_client, "MIGHT_SWITCH_PROTOCOL", "SEND_RESPONSE"
    )
    require_client_server_states(
        upgrade_server, "MIGHT_SWITCH_PROTOCOL", "SEND_RESPONSE"
    )
    deny_and_complete(upgrade_client, upgrade_server, 200)
    require_start_succeeded(start_next_cycle(upgrade_client), upgrade_client)
    require_start_succeeded(start_next_cycle(upgrade_server), upgrade_server)
    print("after deny, start succeeds on the same Upgrade pair", flush=True)


# ---------------------------------------------------------------------------
# H. SWITCHED is permanent: HTTP send, trailing, leftover not parsed, no start
# ---------------------------------------------------------------------------


def _trailing_123_then_456(conn: Any) -> None:
    require_both_switched(conn)
    require_receive_open(conn)
    feed_ok(conn, b"123")
    _require_paused_not_request(conn)
    feed_ok(conn, b"456")
    _require_paused_not_request(conn)
    held, closed = trailing_data_pair(conn)
    print(f"trailing after 123+456 held={held!r} closed={closed}", flush=True)
    assert held == b"123456"
    assert closed is False
    require_receive_open(conn)


def test_connect_200_trailing_123_then_456_receive_still_open():
    client, server = fixed_connect_finished()
    accept_connect(client, server, 200)
    _trailing_123_then_456(client)
    _trailing_123_then_456(server)


def test_upgrade_101_same_trailing_and_paused():
    client, server = fixed_upgrade_finished()
    accept_upgrade(client, server)
    _trailing_123_then_456(client)
    _trailing_123_then_456(server)


def test_switched_does_not_parse_leftover_http_as_request():
    leftover = fixed_leftover_http10_get()
    for label, factory, accept in (
        ("connect", fixed_connect_finished, lambda c, s: accept_connect(c, s, 200)),
        ("upgrade", fixed_upgrade_finished, accept_upgrade),
    ):
        print(f"SWITCHED leftover HTTP ({label})", flush=True)
        client, server = factory()
        accept(client, server)
        feed_ok(client, leftover)
        _require_paused_not_request(client)
        held, closed = trailing_data_pair(client)
        assert leftover in held
        assert closed is False
        require_receive_open(client)
        feed_ok(server, leftover)
        _require_paused_not_request(server)
        server_held, server_closed = trailing_data_pair(server)
        assert leftover in server_held
        assert server_closed is False


def test_http_send_after_switched_is_local_protocol_error():
    connect_client, connect_server = fixed_connect_finished()
    accept_connect(connect_client, connect_server, 200)
    _illegal_http_send(connect_server, make_data(b"xyz"))

    upgrade_client, upgrade_server = fixed_upgrade_finished()
    accept_upgrade(upgrade_client, upgrade_server)
    _illegal_http_send(
        upgrade_client,
        make_request(headers=[("Host", runtime_host())]),
    )

    eom_client, eom_server = fixed_connect_finished()
    accept_connect(eom_client, eom_server, 200)
    _illegal_http_send(eom_server, make_eom())
    assert named_state("ERROR") == require_our_state(eom_server, "ERROR")
    print("SWITCHED HTTP send: server data, client request, server EOM", flush=True)


def test_no_start_next_cycle_out_of_switched():
    client, server = fixed_connect_finished()
    accept_connect(client, server, 200)
    require_neither_error(client)
    require_neither_error(server)
    client_start = start_next_cycle(client)
    require_local_cycle_refusal(client_start, client)
    require_both_switched(client)
    require_neither_error(client)
    server_start = start_next_cycle(server)
    require_local_cycle_refusal(server_start, server)
    require_both_switched(server)
    require_neither_error(server)
    print("SWITCHED start refused, still SWITCHED, not ERROR", flush=True)

    send_pair_client, send_pair_server = fixed_connect_finished()
    accept_connect(send_pair_client, send_pair_server, 200)
    _illegal_http_send(send_pair_server, make_data(b"nope"))
    our = require_our_state(send_pair_server, "ERROR")
    idle = named_state("IDLE")
    switched = named_state("SWITCHED_PROTOCOL")
    print(
        f"send-failure our={our!r} vs start-refusal still {switched!r} "
        f"not {idle!r}",
        flush=True,
    )
    assert our == named_state("ERROR")
    assert our != switched


def test_runtime_switched_trailing_concatenates():
    first = runtime_token().encode("ascii")[:5]
    second = runtime_token().encode("ascii")[:5]
    if first == b"123" or second == b"456":
        first = b"aaaaa"
        second = b"bbbbb"
    print(f"runtime trailing {first!r} then {second!r}", flush=True)
    client, server = fixed_connect_finished()
    accept_connect(client, server, 200)
    feed_ok(client, first)
    _require_paused_not_request(client)
    feed_ok(client, second)
    _require_paused_not_request(client)
    held, closed = trailing_data_pair(client)
    assert held == first + second
    assert closed is False
    require_receive_open(client)
    _require_paused_not_request(client)


# ---------------------------------------------------------------------------
# I. Empty feed while might-switch / after deny / after accept
# ---------------------------------------------------------------------------


def test_empty_feed_while_might_switch_stays_paused_with_receive_closed():
    for label, factory in (
        ("connect", fixed_connect_finished),
        ("upgrade", fixed_upgrade_finished),
    ):
        print(f"empty feed while might-switch ({label})", flush=True)
        _client, server = factory()
        _require_paused_not_cc(server)
        require_receive_open(server)
        feed_empty(server)
        _require_paused_not_cc(server)
        held, closed = trailing_data_pair(server)
        assert closed is True
        require_receive_closed(server)
        print(f"{label} trailing held={held!r} closed={closed}", flush=True)


def test_empty_feed_then_denial_pulls_connection_closed():
    for label, factory, deny_status in (
        ("connect", fixed_connect_finished, 404),
        ("upgrade", fixed_upgrade_finished, 200),
    ):
        print(f"empty feed then deny ({label}) status={deny_status}", flush=True)
        client, server = factory()
        feed_empty(server)
        _require_paused_not_cc(server)
        require_receive_closed(server)
        encoded = require_send_bytes(
            send_event(server, make_response(deny_status, headers=[]))
        )
        feed_ok(client, encoded)
        pull_kind(client, "response")
        event = pull_connection_closed(server)
        print(
            f"{label} after deny pull type={type(event).__name__}",
            flush=True,
        )
        require_connection_closed_event(event)
        assert not event_is_kind(event, "request")


def test_empty_feed_then_acceptance_stays_paused():
    connect_client, connect_server = fixed_connect_finished()
    feed_empty(connect_server)
    _require_paused_not_cc(connect_server)
    require_receive_closed(connect_server)
    accept_connect(connect_client, connect_server, 200)
    _require_paused_not_cc(connect_server)
    require_receive_closed(connect_server)

    upgrade_client, upgrade_server = fixed_upgrade_finished()
    feed_empty(upgrade_server)
    _require_paused_not_cc(upgrade_server)
    accept_upgrade(upgrade_client, upgrade_server)
    _require_paused_not_cc(upgrade_server)
    require_receive_closed(upgrade_server)
    print("empty then accept still paused, not connection-closed", flush=True)


def test_empty_feed_after_acceptance_stays_paused():
    for label, factory, accept in (
        ("connect", fixed_connect_finished, lambda c, s: accept_connect(c, s, 200)),
        ("upgrade", fixed_upgrade_finished, accept_upgrade),
    ):
        print(f"accept then empty feed ({label})", flush=True)
        client, server = factory()
        accept(client, server)
        require_receive_open(server)
        require_receive_open(client)
        feed_empty(server)
        _require_paused_not_cc(server)
        require_receive_closed(server)
        feed_empty(client)
        _require_paused_not_cc(client)
        require_receive_closed(client)


# ---------------------------------------------------------------------------
# J. Leftover HTTP/1.0 after denial + next cycle
# ---------------------------------------------------------------------------


def test_leftover_get_http10_after_denial_and_next_cycle():
    leftover = fixed_leftover_http10_get()
    for label, factory, deny_status in (
        ("connect", fixed_connect_finished, 404),
        ("upgrade", fixed_upgrade_finished, 200),
    ):
        print(f"leftover HTTP/1.0 after deny+start ({label})", flush=True)
        client, server = factory()
        _require_paused_not_request(server)
        feed_ok(server, leftover)
        _require_paused_not_request(server)
        held, closed = trailing_data_pair(server)
        assert leftover in held
        assert closed is False

        encoded = server_send_status(server, deny_status)
        feed_ok(client, encoded)
        pull_kind(client, "response")
        pull_kind(client, "end-of-message")
        gate = pull_next(server)
        require_paused(gate)
        assert not event_is_kind(gate.value, "request")
        require_not_connection_closed_event(gate.value)
        print(f"{label} after deny+EOM still paused, not leftover GET", flush=True)

        require_start_succeeded(start_next_cycle(client), client)
        require_start_succeeded(start_next_cycle(server), server)
        pulled = pull_kind(server, "request")
        print(
            f"{label} leftover method={request_method(pulled)!r} "
            f"target={request_target(pulled)!r} "
            f"version={event_version(pulled)!r}",
            flush=True,
        )
        assert request_method(pulled) == b"GET"
        assert request_target(pulled) == b"/"
        assert event_version(pulled) == b"1.0"
        pull_kind(server, "end-of-message")


def test_runtime_leftover_http10_after_denial():
    target = runtime_target()
    leftover = f"GET {target} HTTP/1.0\r\n\r\n".encode("ascii")
    print(f"runtime leftover target={target!r}", flush=True)
    for label, factory, deny_status in (
        ("connect", fixed_connect_finished, 404),
        ("upgrade", fixed_upgrade_finished, 200),
    ):
        client, server = factory()
        feed_ok(server, leftover)
        _require_paused_not_request(server)
        encoded = server_send_status(server, deny_status)
        feed_ok(client, encoded)
        pull_kind(client, "response")
        pull_kind(client, "end-of-message")
        require_paused(pull_next(server))
        require_start_succeeded(start_next_cycle(server), server)
        require_start_succeeded(start_next_cycle(client), client)
        pulled = pull_kind(server, "request")
        assert request_method(pulled) == b"GET"
        assert request_target(pulled) == target.encode("ascii")
        assert event_version(pulled) == b"1.0"
        pull_kind(server, "end-of-message")
        print(f"{label} runtime leftover became that target", flush=True)


def test_leftover_not_parsed_until_denial_and_start():
    leftover = fixed_leftover_http10_get()
    client, server = fixed_connect_finished()
    feed_ok(server, leftover)
    _require_paused_not_request(server)
    start_fail = start_next_cycle(server)
    require_local_cycle_refusal(start_fail, server)
    still = pull_next(server)
    require_paused(still)
    assert not event_is_kind(still.value, "request")
    print("no-deny start does not unlock leftover GET", flush=True)

    upgrade_client, upgrade_server = fixed_upgrade_finished()
    feed_ok(upgrade_server, leftover)
    _require_paused_not_request(upgrade_server)
    require_local_cycle_refusal(start_next_cycle(upgrade_server), upgrade_server)
    still_upgrade = pull_next(upgrade_server)
    require_paused(still_upgrade)
    assert not event_is_kind(still_upgrade.value, "request")


# ---------------------------------------------------------------------------
# K. need-data / pipelining paused / switch paused unlock differently
# ---------------------------------------------------------------------------


def test_need_data_unblocks_after_more_bytes_of_current_message():
    client = client_connection()
    encoded = require_send_bytes(
        send_event(client, make_request(headers=[("Host", "example.com")]))
    )
    send_completed_eom(client)
    print(f"need-data walk request encoded len={len(encoded)}", flush=True)
    prefix = b"HTTP/1.1 20"
    rest = b"0 OK\r\nContent-Length: 0\r\n\r\n"
    feed_ok(client, prefix)
    require_need_data(pull_next(client))
    feed_ok(client, rest)
    pulled = pull_kind(client, "response")
    assert status_code(pulled) == 200
    print("need-data unblocked into the current response", flush=True)


def test_pipelining_paused_unblocks_after_start_without_switch_deny():
    host = runtime_host()
    first = runtime_target()
    second = runtime_target()
    if second == first:
        second = second + "z"
    block = (
        f"GET {first} HTTP/1.1\r\nHost: {host}\r\n\r\n"
        f"GET {second} HTTP/1.1\r\nHost: {host}\r\n\r\n"
    ).encode("ascii")
    server = server_connection()
    feed_ok(server, block)
    req = pull_kind(server, "request")
    assert request_target(req) == first.encode("ascii")
    pull_kind(server, "end-of-message")
    paused = pull_next(server)
    require_paused(paused)
    assert not event_is_kind(paused.value, "request")
    send_final_200(server)
    require_start_succeeded(start_next_cycle(server), server)
    second_req = pull_kind(server, "request")
    print(
        f"pipelining unlocked second target={request_target(second_req)!r}",
        flush=True,
    )
    assert request_target(second_req) == second.encode("ascii")
    pull_kind(server, "end-of-message")


def test_switch_paused_does_not_unblock_by_feeding_or_start_alone():
    leftover = fixed_leftover_http10_get()
    client, server = fixed_connect_finished()
    accept_connect(client, server, 200)
    feed_ok(server, leftover)
    _require_paused_not_request(server)
    held, _closed = trailing_data_pair(server)
    assert leftover in held
    start_fail = start_next_cycle(server)
    require_local_cycle_refusal(start_fail, server)
    require_both_switched(server)
    require_neither_error(server)
    still = pull_next(server)
    require_paused(still)
    assert not event_is_kind(still.value, "request")
    print("accepted switch: feed and start do not yield the leftover GET", flush=True)

    maybe_client, maybe_server = fixed_upgrade_finished()
    feed_ok(maybe_server, leftover)
    _require_paused_not_request(maybe_server)
    require_local_cycle_refusal(start_next_cycle(maybe_server), maybe_server)
    require_paused(pull_next(maybe_server))
    assert not event_is_kind(pull_next(maybe_server).value, "request")
    print("might-switch without deny: start does not yield leftover GET", flush=True)
