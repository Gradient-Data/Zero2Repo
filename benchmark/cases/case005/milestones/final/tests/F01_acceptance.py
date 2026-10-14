# feature: F01
"""Acceptance tests for HTTP events and header normalization (FP-01).

Exercises event constructors on their own, before any connection is
involved. Failures must be local protocol errors (not remote).
Transfer-Encoding gzip or chunked together with gzip is a local
protocol error whose suggested status is 501. Host refusals in this
feature are graded as local protocol errors; this feature does not name
a suggested-status integer for them.
"""

from __future__ import annotations

import time
from http import HTTPStatus

from F01_helpers import (
    client_connection,
    connection_side_states,
    construct,
    data_payload,
    event_version,
    http_field_absent,
    named_pairs,
    ordinary_pairs,
    payload_letters,
    raw_pairs,
    reason,
    request_method,
    request_result,
    request_target,
    request_version,
    require_bytes,
    require_event,
    require_local_refusal,
    runtime_int,
    runtime_token,
    status_code,
    suggested_status,
    trailing_pairs,
)


# ---------------------------------------------------------------------------
# S. Loaded-package GET / with Host example.com
# ---------------------------------------------------------------------------


def test_get_slash_host_constructs_when_package_importable():
    ev = require_event(
        request_result(headers=[("Host", "example.com")])
    )
    method = request_method(ev)
    target = request_target(ev)
    version = request_version(ev)
    print(
        f"baseline request method={method!r} target={target!r} version={version!r}",
        flush=True,
    )
    assert method == b"GET"
    assert target == b"/"
    assert version == b"1.1"
    assert type(method) is bytes
    assert type(target) is bytes
    assert type(version) is bytes


# ---------------------------------------------------------------------------
# A. Six distinguishable events; named successful constructions
# ---------------------------------------------------------------------------


def test_six_event_kinds_are_distinguishable():
    events = [
        require_event(request_result(headers=[("Host", "example.com")])),
        require_event(construct("informational", status_code=100, headers=[])),
        require_event(construct("response", status_code=204, headers=[])),
        require_event(construct("data", data=b"asdf")),
        require_event(construct("end-of-message")),
        require_event(construct("connection-closed")),
    ]
    types = [type(ev) for ev in events]
    print(f"event types={[t.__name__ for t in types]}", flush=True)
    assert len(types) == 6
    assert len(set(types)) == 6
    for i, left in enumerate(types):
        for j, right in enumerate(types):
            if i != j:
                assert left is not right


def test_get_slash_host_example_com_is_request():
    ev = require_event(request_result(headers=[("Host", "example.com")]))
    assert type(ev) is type(
        require_event(request_result(headers=[("Host", "example.com")]))
    )
    assert request_method(ev) == b"GET"
    assert request_target(ev) == b"/"
    assert request_version(ev) == b"1.1"
    pairs = ordinary_pairs(ev)
    assert (b"host", b"example.com") in pairs


def test_informational_100_empty_headers():
    ev = require_event(construct("informational", status_code=100, headers=[]))
    assert status_code(ev) == 100
    assert ordinary_pairs(ev) == ()


def test_response_204_http10_empty_headers():
    ev = require_event(
        construct("response", status_code=204, headers=[], http_version="1.0")
    )
    assert status_code(ev) == 204
    assert ordinary_pairs(ev) == ()
    version = event_version(ev)
    print(f"response 204 stored version={version!r}", flush=True)
    assert version == b"1.0"
    assert type(version) is bytes


def test_data_payload_asdf_recovered():
    ev = require_event(construct("data", data=b"asdf"))
    payload = data_payload(ev)
    recovered = payload_letters(payload)
    print(f"data payload={payload!r} recovered={recovered!r}", flush=True)
    assert recovered == "asdf"


def test_runtime_data_payload_recovered():
    letters = runtime_token()
    ev = require_event(construct("data", data=letters.encode("ascii")))
    payload = data_payload(ev)
    recovered = payload_letters(payload)
    print(f"runtime data payload={payload!r} recovered={recovered!r}", flush=True)
    assert recovered == letters


def test_end_of_message_defaults_to_empty_trailers():
    ev = require_event(construct("end-of-message"))
    trailers = trailing_pairs(ev)
    print(f"eom trailers={trailers!r}", flush=True)
    assert trailers == ()


def test_connection_closed_has_no_fields():
    ev = require_event(construct("connection-closed"))
    for field in ("method", "target", "status", "reason", "payload", "headers"):
        http_field_absent(ev, field)
    other = require_event(request_result(headers=[("Host", "example.com")]))
    assert type(ev) is not type(other)


def test_runtime_request_constructs():
    method = "X" + runtime_token()[:8]
    target = "/" + runtime_token()[:8]
    host = runtime_token()
    ev = require_event(
        request_result(method=method, target=target, headers=[("Host", host)])
    )
    stored_method = request_method(ev)
    stored_target = request_target(ev)
    print(
        f"runtime request method={stored_method!r} target={stored_target!r}",
        flush=True,
    )
    assert stored_method == method.encode("ascii")
    assert stored_target == target.encode("ascii")
    assert (b"host", host.encode("ascii")) in ordinary_pairs(ev)


# ---------------------------------------------------------------------------
# B. Method / target / version stored as bytes; default 1.1; comparable
# ---------------------------------------------------------------------------


def test_method_target_version_from_ascii_text_are_bytes():
    ev = require_event(
        request_result(
            method="GET",
            target="/",
            headers=[("Host", "example.com")],
            http_version="1.1",
        )
    )
    method = request_method(ev)
    target = request_target(ev)
    version = request_version(ev)
    assert type(method) is bytes
    assert type(target) is bytes
    assert type(version) is bytes
    assert method == b"GET"
    assert target == b"/"
    assert version == b"1.1"


def test_method_target_version_from_byte_buffer_are_bytes():
    ev = require_event(
        request_result(
            method=bytearray(b"GET"),
            target=bytearray(b"/"),
            headers=[("Host", "example.com")],
            http_version=bytearray(b"1.1"),
        )
    )
    method = request_method(ev)
    target = request_target(ev)
    version = request_version(ev)
    assert type(method) is bytes
    assert type(target) is bytes
    assert type(version) is bytes
    assert method == b"GET"
    assert target == b"/"
    assert version == b"1.1"


def test_request_http_version_defaults_to_1_1():
    ev = require_event(request_result(headers=[("Host", "example.com")]))
    version = request_version(ev)
    print(f"default version={version!r}", flush=True)
    assert version == b"1.1"
    assert type(version) is bytes


def test_http10_version_compares_less_than_1_1():
    headers = [("Host", "example.com")]
    ev10 = require_event(
        request_result(headers=headers, http_version="1.0")
    )
    ev11 = require_event(request_result(headers=headers))
    v10 = request_version(ev10)
    v11 = request_version(ev11)
    one_one = b"1.1"
    print(f"compare v10={v10!r} v11={v11!r}", flush=True)
    assert v10 < one_one
    assert not (v11 < one_one)


# ---------------------------------------------------------------------------
# C. Host: required on 1.1, optional on 1.0, two Hosts refused
# ---------------------------------------------------------------------------


def test_http10_get_slash_empty_headers_succeeds():
    ev = require_event(request_result(headers=[], http_version="1.0"))
    assert request_method(ev) == b"GET"
    assert request_target(ev) == b"/"
    assert request_version(ev) == b"1.0"
    assert ordinary_pairs(ev) == ()


def test_host_spelled_hOSt_ordinary_and_raw():
    ev = require_event(request_result(headers=[("hOSt", "example.com")]))
    assert ordinary_pairs(ev) == ((b"host", b"example.com"),)
    assert raw_pairs(ev) == ((b"hOSt", b"example.com"),)


def test_runtime_mixed_case_host_ordinary_and_raw():
    host = runtime_token()
    ev = require_event(request_result(headers=[("HoSt", host)]))
    assert ordinary_pairs(ev) == ((b"host", host.encode("ascii")),)
    assert raw_pairs(ev) == ((b"HoSt", host.encode("ascii")),)


def test_http11_missing_host_empty_headers_is_local_protocol_error():
    neighbor = require_event(request_result(headers=[("Host", "example.com")]))
    assert request_method(neighbor) == b"GET"
    require_local_refusal(request_result(headers=[]))


def test_http11_missing_host_with_only_non_host_header_is_local_protocol_error():
    neighbor = require_event(
        request_result(
            headers=[
                ("Connection", "keep-alive"),
                ("Host", "example.com"),
            ]
        )
    )
    assert (b"connection", b"keep-alive") in ordinary_pairs(neighbor)
    require_local_refusal(
        request_result(headers=[("Connection", "keep-alive")]),
    )


def test_two_hosts_refused_on_http10():
    neighbor = require_event(request_result(headers=[], http_version="1.0"))
    assert request_version(neighbor) == b"1.0"
    require_local_refusal(
        request_result(
            headers=[("Host", "example.com"), ("Host", "example.org")],
            http_version="1.0",
        ),
    )


def test_two_hosts_refused_on_http11():
    neighbor = require_event(request_result(headers=[("Host", "example.com")]))
    assert (b"host", b"example.com") in ordinary_pairs(neighbor)
    require_local_refusal(
        request_result(
            headers=[("Host", "example.com"), ("Host", "example.org")],
        ),
    )


def test_two_hosts_mixed_case_refused():
    neighbor = require_event(request_result(headers=[("hOSt", "example.com")]))
    assert ordinary_pairs(neighbor) == ((b"host", b"example.com"),)
    require_local_refusal(
        request_result(headers=[("Host", "example.com"), ("hOSt", "example.com")]),
    )


def test_valid_request_still_constructs_after_missing_host_refusal():
    require_local_refusal(request_result(headers=[]))
    ev = require_event(request_result(headers=[("Host", "example.com")]))
    assert request_method(ev) == b"GET"
    assert request_target(ev) == b"/"


def test_valid_construction_after_non_host_refusal():
    require_local_refusal(
        request_result(
            headers=[("Host", "example.com"), ("Content-Length", "asdf")],
        ),
    )
    ev = require_event(request_result(headers=[("Host", "example.com")]))
    assert request_method(ev) == b"GET"


def test_missing_host_leaves_connection_unaffected():
    conn = client_connection()
    before = connection_side_states(conn)
    print(f"before missing-host refusal states={before!r}", flush=True)
    require_local_refusal(request_result(headers=[]))
    after = connection_side_states(conn)
    print(f"after missing-host refusal states={after!r}", flush=True)
    assert after == before


# ---------------------------------------------------------------------------
# D. Status ranges, reason, status constants, crossed pair, non-integer
# ---------------------------------------------------------------------------


def test_informational_100_and_199_succeed():
    ev100 = require_event(construct("informational", status_code=100, headers=[]))
    ev199 = require_event(construct("informational", status_code=199, headers=[]))
    assert status_code(ev100) == 100
    assert status_code(ev199) == 199


def test_response_204_and_999_succeed():
    ev204 = require_event(
        construct("response", status_code=204, headers=[], http_version="1.0")
    )
    ev999 = require_event(construct("response", status_code=999, headers=[]))
    assert status_code(ev204) == 204
    assert status_code(ev999) == 999


def test_response_200_is_final_not_informational():
    ev = require_event(construct("response", status_code=200, headers=[]))
    assert status_code(ev) == 200
    info = require_event(construct("informational", status_code=100, headers=[]))
    assert type(ev) is not type(info)
    assert type(ev) is type(
        require_event(construct("response", status_code=204, headers=[]))
    )


def test_runtime_interior_informational_and_response_succeed():
    info_status = 101 + (time.time_ns() % 98)
    if info_status in (100, 199):
        info_status = 150
    resp_status = 201 + (time.time_ns() % 798)
    if resp_status in (200, 204, 999):
        resp_status = 418
    print(
        f"runtime interior informational={info_status} response={resp_status}",
        flush=True,
    )
    ev_i = require_event(
        construct("informational", status_code=info_status, headers=[])
    )
    ev_r = require_event(
        construct("response", status_code=resp_status, headers=[])
    )
    assert status_code(ev_i) == info_status
    assert status_code(ev_r) == resp_status


def test_informational_and_response_default_version_1_1():
    ev_i = require_event(construct("informational", status_code=100, headers=[]))
    ev_r = require_event(construct("response", status_code=200, headers=[]))
    assert event_version(ev_i) == b"1.1"
    assert event_version(ev_r) == b"1.1"
    assert type(event_version(ev_i)) is bytes
    assert type(event_version(ev_r)) is bytes


def test_reason_defaults_empty_and_ok_stored_as_bytes():
    info_ok = require_event(
        construct(
            "informational",
            status_code=100,
            headers=[],
            reason="OK",
        )
    )
    resp_ok = require_event(
        construct("response", status_code=200, headers=[], reason="OK")
    )
    info_ok_reason = reason(info_ok)
    resp_ok_reason = reason(resp_ok)
    print(
        f"supplied OK informational={info_ok_reason!r} response={resp_ok_reason!r}",
        flush=True,
    )
    assert type(info_ok_reason) is bytes
    assert type(resp_ok_reason) is bytes
    assert info_ok_reason == b"OK"
    assert resp_ok_reason == b"OK"

    info_empty = require_event(
        construct("informational", status_code=100, headers=[])
    )
    resp_empty = require_event(construct("response", status_code=200, headers=[]))
    info_empty_reason = reason(info_empty)
    resp_empty_reason = reason(resp_empty)
    print(
        f"omitted reason informational={info_empty_reason!r} "
        f"response={resp_empty_reason!r}",
        flush=True,
    )
    assert type(info_empty_reason) is bytes
    assert type(resp_empty_reason) is bytes
    assert len(info_empty_reason) == 0
    assert len(resp_empty_reason) == 0
    assert info_empty_reason == b""
    assert resp_empty_reason == b""


def test_integer_status_constant_stored_as_plain_int():
    ev = require_event(
        construct("response", status_code=HTTPStatus.OK, headers=[])
    )
    code = status_code(ev)
    print(
        f"OK constant stored={code!r} type={type(code)!r}",
        flush=True,
    )
    assert code == 200
    assert type(code) is int
    assert type(code) is not type(HTTPStatus.OK)


def test_second_integer_status_constant_stored_as_plain_int():
    const = HTTPStatus.CREATED
    ev = require_event(construct("response", status_code=const, headers=[]))
    code = status_code(ev)
    print(
        f"second constant stored={code!r} type={type(code)!r}",
        flush=True,
    )
    assert code == int(const)
    assert type(code) is int
    assert type(code) is not type(const)


def test_informational_200_refused():
    neighbor = require_event(construct("response", status_code=200, headers=[]))
    assert status_code(neighbor) == 200
    require_local_refusal(
        construct("informational", status_code=200, headers=[]),
    )


def test_response_100_refused():
    neighbor = require_event(
        construct("informational", status_code=100, headers=[])
    )
    assert status_code(neighbor) == 100
    require_local_refusal(
        construct("response", status_code=100, headers=[]),
    )


def test_non_integer_status_text_100_refused():
    neighbor = require_event(
        construct("informational", status_code=100, headers=[])
    )
    assert status_code(neighbor) == 100
    require_local_refusal(
        construct("informational", status_code="100", headers=[]),
    )


def test_runtime_non_integer_status_refused():
    text = runtime_token()
    neighbor = require_event(
        construct("informational", status_code=100, headers=[])
    )
    assert status_code(neighbor) == 100
    require_local_refusal(
        construct("response", status_code=text, headers=[]),
    )


def test_informational_status_below_100_refused():
    neighbor = require_event(construct("informational", status_code=100, headers=[]))
    assert status_code(neighbor) == 100
    require_local_refusal(
        construct("informational", status_code=99, headers=[]),
    )
    below = int(time.time_ns() % 99)
    print(f"runtime informational below 100: {below}", flush=True)
    require_local_refusal(
        construct("informational", status_code=below, headers=[]),
    )


def test_response_status_1000_or_greater_refused():
    neighbor = require_event(construct("response", status_code=999, headers=[]))
    assert status_code(neighbor) == 999
    require_local_refusal(
        construct("response", status_code=1000, headers=[]),
    )
    above = 1000 + runtime_int()
    print(f"runtime response 1000 or greater: {above}", flush=True)
    require_local_refusal(
        construct("response", status_code=above, headers=[]),
    )


# ---------------------------------------------------------------------------
# E. Header normalization, order, ordinary vs raw-items
# ---------------------------------------------------------------------------


def test_host_then_connection_ordinary_and_raw():
    ev = require_event(
        request_result(
            headers=[
                ("Host", "example.org"),
                ("Connection", "keep-alive"),
            ]
        )
    )
    assert ordinary_pairs(ev) == (
        (b"host", b"example.org"),
        (b"connection", b"keep-alive"),
    )
    assert raw_pairs(ev) == (
        (b"Host", b"example.org"),
        (b"Connection", b"keep-alive"),
    )


def test_construction_preserves_caller_order_including_host_not_first():
    ev = require_event(
        request_result(headers=[("foo", "bar"), ("Host", "example.com")])
    )
    names = [name for name, _ in ordinary_pairs(ev)]
    print(f"construction order names={names!r}", flush=True)
    assert names == [b"foo", b"host"]
    assert ordinary_pairs(ev)[0] == (b"foo", b"bar")
    assert ordinary_pairs(ev)[1] == (b"host", b"example.com")


def test_headers_from_ascii_and_byte_buffer_are_bytes():
    ev_text = require_event(
        request_result(
            headers=[
                ("Host", "example.com"),
                ("Connection", "keep-alive"),
            ]
        )
    )
    for name, value in ordinary_pairs(ev_text) + raw_pairs(ev_text):
        require_bytes(name)
        require_bytes(value)

    ev_buf = require_event(
        request_result(
            headers=[
                (bytearray(b"Host"), bytearray(b"example.com")),
                (bytearray(b"Connection"), bytearray(b"keep-alive")),
            ]
        )
    )
    for name, value in ordinary_pairs(ev_buf) + raw_pairs(ev_buf):
        require_bytes(name)
        require_bytes(value)
        assert type(name) is bytes
        assert type(value) is bytes


def test_header_value_uppercase_preserved():
    value = "Foo" + runtime_token()
    ev = require_event(
        request_result(
            headers=[
                ("Host", "example.com"),
                ("X-Trace", value),
            ]
        )
    )
    expected = value.encode("ascii")
    assert (b"x-trace", expected) in ordinary_pairs(ev)
    assert (b"X-Trace", expected) in raw_pairs(ev)


def test_informational_headers_ordinary_and_raw():
    ev = require_event(
        construct(
            "informational",
            status_code=100,
            headers=[("X-Foo", "bar")],
        )
    )
    assert ordinary_pairs(ev) == ((b"x-foo", b"bar"),)
    assert raw_pairs(ev) == ((b"X-Foo", b"bar"),)


def test_response_headers_ordinary_and_raw():
    ev = require_event(
        construct("response", status_code=204, headers=[("X-Foo", "bar")])
    )
    assert ordinary_pairs(ev) == ((b"x-foo", b"bar"),)
    assert raw_pairs(ev) == ((b"X-Foo", b"bar"),)


def test_end_of_message_trailing_headers_normalized():
    ev = require_event(
        construct("end-of-message", headers=[("X-Foo", "bar")])
    )
    assert ordinary_pairs(ev) == ((b"x-foo", b"bar"),)
    assert raw_pairs(ev) == ((b"X-Foo", b"bar"),)


def test_runtime_header_order_and_raw_casing():
    token_a = runtime_token()
    token_b = runtime_token()
    token_c = runtime_token()
    mixed = "X-" + "".join(
        ch.upper() if i % 2 == 0 else ch.lower()
        for i, ch in enumerate(token_a[:6])
    )
    ev_text = require_event(
        request_result(
            headers=[
                (mixed, token_a),
                ("Host", "example.com"),
                ("X-Next", token_b),
            ]
        )
    )
    text_names = [name for name, _ in ordinary_pairs(ev_text)]
    print(f"runtime order ordinary names={text_names!r}", flush=True)
    assert text_names == [mixed.lower().encode("ascii"), b"host", b"x-next"]
    raw_names = [name for name, _ in raw_pairs(ev_text)]
    assert raw_names == [mixed.encode("ascii"), b"Host", b"X-Next"]
    assert ordinary_pairs(ev_text)[0][1] == token_a.encode("ascii")
    assert ordinary_pairs(ev_text)[2][1] == token_b.encode("ascii")

    ev_buf = require_event(
        request_result(
            headers=[
                (bytearray(mixed.encode("ascii")), bytearray(token_c.encode("ascii"))),
                (bytearray(b"Host"), bytearray(b"example.com")),
            ]
        )
    )
    for name, value in ordinary_pairs(ev_buf) + raw_pairs(ev_buf):
        assert type(name) is bytes
        assert type(value) is bytes
    assert ordinary_pairs(ev_buf)[0][1] == token_c.encode("ascii")


# ---------------------------------------------------------------------------
# F. Content-Length accept / collapse / refuse
# ---------------------------------------------------------------------------


def test_content_length_1_normalized():
    ev = require_event(
        request_result(
            headers=[("Host", "example.com"), ("Content-Length", "1")],
        )
    )
    cl = named_pairs(ordinary_pairs(ev), b"content-length")
    assert cl == [(b"content-length", b"1")]


def test_two_content_length_0_collapse():
    ev = require_event(
        request_result(
            headers=[
                ("Host", "example.com"),
                ("Content-Length", "0"),
                ("Content-Length", "0"),
            ]
        )
    )
    cl = named_pairs(ordinary_pairs(ev), b"content-length")
    print(f"two CL 0 collapsed={cl!r}", flush=True)
    assert cl == [(b"content-length", b"0")]


def test_single_content_length_0_comma_0_collapses():
    ev = require_event(
        request_result(
            headers=[("Host", "example.com"), ("Content-Length", "0 , 0")],
        )
    )
    cl = named_pairs(ordinary_pairs(ev), b"content-length")
    print(f"CL 0 , 0 collapsed={cl!r}", flush=True)
    assert cl == [(b"content-length", b"0")]


def test_eighteen_digit_content_length_succeeds():
    digits = "123456789012345678"
    assert len(digits) == 18
    ev = require_event(
        request_result(
            headers=[("Host", "example.com"), ("Content-Length", digits)],
        )
    )
    cl = named_pairs(ordinary_pairs(ev), b"content-length")
    assert cl == [(b"content-length", digits.encode("ascii"))]


def test_runtime_content_length_accepted():
    n = 10 + (runtime_int() % 89)
    digits = str(n)
    ev = require_event(
        request_result(
            headers=[("Host", "example.com"), ("Content-Length", digits)],
        )
    )
    cl = named_pairs(ordinary_pairs(ev), b"content-length")
    assert cl == [(b"content-length", digits.encode("ascii"))]


def test_content_length_asdf_and_1x_refused():
    neighbor = require_event(
        request_result(
            headers=[("Host", "example.com"), ("Content-Length", "1")],
        )
    )
    assert named_pairs(ordinary_pairs(neighbor), b"content-length") == [
        (b"content-length", b"1")
    ]
    require_local_refusal(
        request_result(
            headers=[("Host", "example.com"), ("Content-Length", "asdf")],
        ),
    )
    require_local_refusal(
        request_result(
            headers=[("Host", "example.com"), ("Content-Length", "1x")],
        ),
    )


def test_disagreeing_content_length_headers_refused():
    neighbor = require_event(
        request_result(
            headers=[
                ("Host", "example.com"),
                ("Content-Length", "0"),
                ("Content-Length", "0"),
            ]
        )
    )
    assert named_pairs(ordinary_pairs(neighbor), b"content-length") == [
        (b"content-length", b"0")
    ]
    require_local_refusal(
        request_result(
            headers=[
                ("Host", "example.com"),
                ("Content-Length", "1"),
                ("Content-Length", "2"),
            ]
        ),
    )


def test_disagreeing_content_length_pair_not_public_refused():
    neighbor = require_event(
        request_result(
            headers=[
                ("Host", "example.com"),
                ("Content-Length", "0"),
                ("Content-Length", "0"),
            ]
        )
    )
    assert named_pairs(ordinary_pairs(neighbor), b"content-length") == [
        (b"content-length", b"0")
    ]
    require_local_refusal(
        request_result(
            headers=[
                ("Host", "example.com"),
                ("Content-Length", "7"),
                ("Content-Length", "9"),
            ]
        ),
    )


def test_disagreeing_comma_pieces_1_1_2_refused():
    neighbor = require_event(
        request_result(
            headers=[("Host", "example.com"), ("Content-Length", "0 , 0")],
        )
    )
    assert named_pairs(ordinary_pairs(neighbor), b"content-length") == [
        (b"content-length", b"0")
    ]
    require_local_refusal(
        request_result(
            headers=[("Host", "example.com"), ("Content-Length", "1 , 1,2")],
        ),
    )


def test_disagreeing_comma_pieces_not_public_refused():
    neighbor = require_event(
        request_result(
            headers=[("Host", "example.com"), ("Content-Length", "0 , 0")],
        )
    )
    assert named_pairs(ordinary_pairs(neighbor), b"content-length") == [
        (b"content-length", b"0")
    ]
    require_local_refusal(
        request_result(
            headers=[("Host", "example.com"), ("Content-Length", "3 , 3,4")],
        ),
    )


def test_thirty_three_ones_content_length_refused():
    digits18 = "123456789012345678"
    neighbor = require_event(
        request_result(
            headers=[("Host", "example.com"), ("Content-Length", digits18)],
        )
    )
    assert named_pairs(ordinary_pairs(neighbor), b"content-length") == [
        (b"content-length", digits18.encode("ascii"))
    ]
    require_local_refusal(
        request_result(
            headers=[("Host", "example.com"), ("Content-Length", "1" * 33)],
        ),
    )


def test_runtime_longer_than_digit_limit_content_length_refused():
    digits18 = "123456789012345678"
    neighbor = require_event(
        request_result(
            headers=[("Host", "example.com"), ("Content-Length", digits18)],
        )
    )
    assert named_pairs(ordinary_pairs(neighbor), b"content-length") == [
        (b"content-length", digits18.encode("ascii"))
    ]
    long_digits = "4" * (34 + (runtime_int() % 7))
    assert len(long_digits) > 32 and len(long_digits) != 33
    require_local_refusal(
        request_result(
            headers=[("Host", "example.com"), ("Content-Length", long_digits)],
        ),
    )


def test_three_content_length_not_all_equal_refused():
    neighbor = require_event(
        request_result(
            headers=[
                ("Host", "example.com"),
                ("Content-Length", "0"),
                ("Content-Length", "0"),
            ]
        )
    )
    assert named_pairs(ordinary_pairs(neighbor), b"content-length") == [
        (b"content-length", b"0")
    ]
    require_local_refusal(
        request_result(
            headers=[
                ("Host", "example.com"),
                ("Content-Length", "0"),
                ("Content-Length", "0"),
                ("Content-Length", "5"),
            ]
        ),
    )


def test_content_length_mixed_case_disagreeing_refused():
    neighbor = require_event(
        request_result(
            headers=[("Host", "example.com"), ("Content-Length", "1")],
        )
    )
    assert named_pairs(ordinary_pairs(neighbor), b"content-length") == [
        (b"content-length", b"1")
    ]
    require_local_refusal(
        request_result(
            headers=[
                ("Host", "example.com"),
                ("Content-Length", "4"),
                ("content-length", "8"),
            ]
        ),
    )


def test_content_length_asdf_refused_on_non_request():
    neighbor = require_event(
        construct("informational", status_code=100, headers=[("X-Ok", "yes")])
    )
    assert ordinary_pairs(neighbor) == ((b"x-ok", b"yes"),)
    require_local_refusal(
        construct(
            "informational",
            status_code=100,
            headers=[("Content-Length", "asdf")],
        ),
    )


# ---------------------------------------------------------------------------
# G. Transfer-Encoding: chunked, second header, non-chunked 501
# ---------------------------------------------------------------------------


def test_transfer_encoding_chunked_normalized():
    ev = require_event(
        request_result(
            headers=[("Host", "example.com"), ("Transfer-Encoding", "chunked")],
        )
    )
    te = named_pairs(ordinary_pairs(ev), b"transfer-encoding")
    assert te == [(b"transfer-encoding", b"chunked")]


def test_transfer_encoding_cHuNkEd_normalized():
    ev = require_event(
        request_result(
            headers=[("Host", "example.com"), ("Transfer-Encoding", "cHuNkEd")],
        )
    )
    te = named_pairs(ordinary_pairs(ev), b"transfer-encoding")
    assert te == [(b"transfer-encoding", b"chunked")]


def test_transfer_encoding_third_mixed_case_chunked_normalized():
    ev = require_event(
        request_result(
            headers=[("Host", "example.com"), ("Transfer-Encoding", "ChUnKeD")],
        )
    )
    te = named_pairs(ordinary_pairs(ev), b"transfer-encoding")
    assert te == [(b"transfer-encoding", b"chunked")]


def test_second_transfer_encoding_chunked_refused():
    neighbor = require_event(
        request_result(
            headers=[("Host", "example.com"), ("Transfer-Encoding", "chunked")],
        )
    )
    assert named_pairs(ordinary_pairs(neighbor), b"transfer-encoding") == [
        (b"transfer-encoding", b"chunked")
    ]
    require_local_refusal(
        request_result(
            headers=[
                ("Host", "example.com"),
                ("Transfer-Encoding", "chunked"),
                ("Transfer-Encoding", "chunked"),
            ]
        ),
        suggested=501,
    )


def test_second_transfer_encoding_mixed_case_names_refused():
    neighbor = require_event(
        request_result(
            headers=[("Host", "example.com"), ("Transfer-Encoding", "chunked")],
        )
    )
    assert named_pairs(ordinary_pairs(neighbor), b"transfer-encoding") == [
        (b"transfer-encoding", b"chunked")
    ]
    require_local_refusal(
        request_result(
            headers=[
                ("Host", "example.com"),
                ("Transfer-Encoding", "chunked"),
                ("TRANSFER-ENCODING", "chunked"),
            ]
        ),
        suggested=501,
    )


def test_transfer_encoding_gzip_is_local_error_status_501():
    neighbor = require_event(
        request_result(
            headers=[("Host", "example.com"), ("Transfer-Encoding", "chunked")],
        )
    )
    assert named_pairs(ordinary_pairs(neighbor), b"transfer-encoding") == [
        (b"transfer-encoding", b"chunked")
    ]
    require_local_refusal(
        request_result(
            headers=[("Host", "example.com"), ("Transfer-Encoding", "gzip")],
        ),
        suggested=501,
    )


def test_chunked_together_with_gzip_is_501():
    neighbor = require_event(
        request_result(
            headers=[("Host", "example.com"), ("Transfer-Encoding", "chunked")],
        )
    )
    assert named_pairs(ordinary_pairs(neighbor), b"transfer-encoding") == [
        (b"transfer-encoding", b"chunked")
    ]
    require_local_refusal(
        request_result(
            headers=[
                ("Host", "example.com"),
                ("Transfer-Encoding", "chunked, gzip"),
            ]
        ),
        suggested=501,
    )


def test_deflate_transfer_encoding_is_501():
    neighbor = require_event(
        request_result(
            headers=[("Host", "example.com"), ("Transfer-Encoding", "chunked")],
        )
    )
    assert named_pairs(ordinary_pairs(neighbor), b"transfer-encoding") == [
        (b"transfer-encoding", b"chunked")
    ]
    require_local_refusal(
        request_result(
            headers=[("Host", "example.com"), ("Transfer-Encoding", "deflate")],
        ),
    )


def test_runtime_non_chunked_transfer_encoding_is_501():
    token = "x" + runtime_token()[:8]
    neighbor = require_event(
        request_result(
            headers=[("Host", "example.com"), ("Transfer-Encoding", "chunked")],
        )
    )
    assert named_pairs(ordinary_pairs(neighbor), b"transfer-encoding") == [
        (b"transfer-encoding", b"chunked")
    ]
    require_local_refusal(
        request_result(
            headers=[("Host", "example.com"), ("Transfer-Encoding", token)],
        ),
    )


def test_gzip_501_differs_from_missing_host_400():
    gzip_exc = require_local_refusal(
        request_result(
            headers=[("Host", "example.com"), ("Transfer-Encoding", "gzip")],
        ),
        suggested=501,
    )
    host_exc = require_local_refusal(
        request_result(headers=[]),
    )
    gzip_status = suggested_status(gzip_exc)
    print(
        f"gzip suggested={gzip_status} missing-host type={type(host_exc).__name__}",
        flush=True,
    )
    assert gzip_status == 501


def test_transfer_encoding_gzip_refused_on_non_request():
    neighbor = require_event(
        construct("end-of-message", headers=[("X-Ok", "yes")])
    )
    assert ordinary_pairs(neighbor) == ((b"x-ok", b"yes"),)
    require_local_refusal(
        construct("end-of-message", headers=[("Transfer-Encoding", "gzip")]),
        suggested=501,
    )


# ---------------------------------------------------------------------------
# H. Illegal names / values / targets / methods; keep some control bytes
# ---------------------------------------------------------------------------


def test_header_name_leading_or_trailing_whitespace_refused():
    neighbor = require_event(
        request_result(
            headers=[("Host", "example.com"), ("X-Foo", "bar")],
        )
    )
    assert (b"x-foo", b"bar") in ordinary_pairs(neighbor)
    require_local_refusal(
        request_result(headers=[("Host", "example.com"), ("X-Foo ", "bar")]),
    )
    require_local_refusal(
        request_result(headers=[("Host", "example.com"), (" X-Foo", "bar")]),
    )


def test_header_name_leading_or_trailing_tab_refused():
    neighbor = require_event(
        request_result(
            headers=[("Host", "example.com"), ("X-Foo", "bar")],
        )
    )
    assert (b"x-foo", b"bar") in ordinary_pairs(neighbor)
    require_local_refusal(
        request_result(headers=[("Host", "example.com"), ("X-Foo\t", "bar")]),
    )
    require_local_refusal(
        request_result(headers=[("Host", "example.com"), ("\tX-Foo", "bar")]),
    )


def test_header_name_space_nul_nonascii_control_refused():
    neighbor = require_event(
        request_result(
            headers=[("Host", "example.com"), ("X-Foo", "bar")],
        )
    )
    assert (b"x-foo", b"bar") in ordinary_pairs(neighbor)
    require_local_refusal(
        request_result(headers=[("Host", "example.com"), ("X Foo", "bar")]),
    )
    require_local_refusal(
        request_result(
            headers=[("Host", "example.com"), (b"X\x00Foo", b"bar")],
        ),
    )
    require_local_refusal(
        request_result(
            headers=[("Host", "example.com"), (b"X\xffFoo", b"bar")],
        ),
    )
    require_local_refusal(
        request_result(
            headers=[("Host", "example.com"), (b"X\x01Foo", b"bar")],
        ),
    )


def test_header_value_cr_lf_ff_vt_nul_refused():
    neighbor = require_event(
        request_result(
            headers=[("Host", "example.com"), ("X-Foo", "bar")],
        )
    )
    assert (b"x-foo", b"bar") in ordinary_pairs(neighbor)
    for bad in ("a\rb", "a\nb", "a\fb", "a\vb", "a\x00b"):
        print(f"refusing header value {bad!r}", flush=True)
        require_local_refusal(
            request_result(headers=[("Host", "example.com"), ("X-Foo", bad)]),
        )


def test_header_value_leading_trailing_space_or_tab_refused():
    neighbor = require_event(
        request_result(
            headers=[("Host", "example.com"), ("X-Foo", "bar")],
        )
    )
    assert (b"x-foo", b"bar") in ordinary_pairs(neighbor)
    require_local_refusal(
        request_result(headers=[("Host", "example.com"), ("X-Foo", " bar")]),
    )
    require_local_refusal(
        request_result(headers=[("Host", "example.com"), ("X-Foo", "bar ")]),
    )
    require_local_refusal(
        request_result(headers=[("Host", "example.com"), ("X-Foo", "\tbar")]),
    )
    require_local_refusal(
        request_result(headers=[("Host", "example.com"), ("X-Foo", "bar\t")]),
    )


def test_header_illegal_name_or_value_refused_on_response():
    neighbor = require_event(
        construct("response", status_code=200, headers=[("X-Foo", "bar")])
    )
    assert ordinary_pairs(neighbor) == ((b"x-foo", b"bar"),)
    require_local_refusal(
        construct("response", status_code=200, headers=[("X-Foo ", "bar")]),
    )


def test_header_illegal_name_or_value_refused_on_informational_or_eom():
    neighbor = require_event(
        construct("end-of-message", headers=[("X-Foo", "bar")])
    )
    assert ordinary_pairs(neighbor) == ((b"x-foo", b"bar"),)
    require_local_refusal(
        construct("end-of-message", headers=[(b"X\x00Foo", b"bar")]),
    )


def test_target_nul_space_127_238_embedded_in_slash_refused():
    neighbor = require_event(request_result(headers=[("Host", "example.com")]))
    assert request_target(neighbor) == b"/"
    for bad in (0x00, 0x20, 0x7F, 0xEE):
        target = b"/" + bytes([bad])
        print(f"refusing embedded target {target!r}", flush=True)
        require_local_refusal(
            request_result(target=target, headers=[("Host", "example.com")]),
        )


def test_method_not_a_single_token_refused():
    neighbor = require_event(request_result(headers=[("Host", "example.com")]))
    assert request_method(neighbor) == b"GET"
    require_local_refusal(
        request_result(
            method="GET / HTTP/1.1",
            headers=[("Host", "example.com")],
        ),
    )


def test_runtime_method_not_a_token_refused():
    neighbor = require_event(request_result(headers=[("Host", "example.com")]))
    assert request_method(neighbor) == b"GET"
    method = "PUT " + runtime_token()
    require_local_refusal(
        request_result(method=method, headers=[("Host", "example.com")]),
    )


def test_set_cookie_byte_1_kept():
    value = b"a=\x01"
    ev = require_event(
        request_result(
            headers=[("Host", "example.com"), ("Set-Cookie", value)],
        )
    )
    assert (b"set-cookie", value) in ordinary_pairs(ev)
    assert (b"Set-Cookie", value) in raw_pairs(ev)


def test_header_value_bytes_1_2_127_kept():
    name = "X-" + runtime_token()[:6]
    value = bytes([1, 2, 127])
    ev = require_event(
        request_result(headers=[("Host", "example.com"), (name, value)])
    )
    assert (name.lower().encode("ascii"), value) in ordinary_pairs(ev)
    assert (name.encode("ascii"), value) in raw_pairs(ev)
