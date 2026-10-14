# feature: F03
"""FP-03: Time-based one-time passwords (TOTP).

Assertions follow the Full PRD FP-03 plus the PRD's shared defaults
(Terminology, Non-functional constraints). Failure message text, exception class names, and URI / HMAC-counter behavior are not pinned.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from hashlib import md5, sha1, sha256, sha512, shake_128

from otpkit import TOTP

from _harness import (
    call,
    frozen_clock,
    local_datetime,
    process_timezone,
    utc_datetime,
)
from F02_helpers import (
    GEZDGNBV_SECRET,
    RFC_SECRET,
    WRN3_SECRET,
    _is_usable_helper,
    fullwidth_digit_form,
    require_accepted,
    require_code,
    require_construction_refused,
    require_helper,
    require_named_code,
    require_rejected,
    require_secret_bound_pair,
    unpublished_digit_count_above_ten,
)
from F03_helpers import (
    ABCDEFGH_SECRET,
    EPOCH_MINUS_1,
    EPOCH_MINUS_29_5,
    EPOCH_MINUS_30,
    EPOCH_STEP_CODE,
    FROZEN_CODE,
    FROZEN_PLUS_STEP,
    FROZEN_UNIX,
    MATCHING_STEP_MINUS_1,
    MATCHING_STEP_ON,
    MATCHING_STEP_PLUS_1,
    NAMED_UNIX_INSTANTS,
    OFFSET_0_CODE,
    OFFSET_INSTANT,
    OFFSET_MINUS_1_CODE,
    OFFSET_PLUS_1_CODE,
    RFC6238_SHA1_TABLE,
    RFC6238_SHA256_TABLE,
    RFC6238_SHA512_TABLE,
    RFC_SIX_DIGIT,
    SHA256_ASCII_KEY,
    SHA512_ASCII_KEY,
    SIXTY_AT_30,
    SIXTY_AT_60,
    WINDOW_REJECT_CODE,
    ascii_key_as_base32,
    check_at_instant,
    check_current_clock,
    emit_current_clock,
    emit_for_instant,
    matching_step_at,
    require_a_step_number,
    require_negative_instant_refused,
    require_negative_window_aborted,
    require_no_step_number,
    require_step_number,
    success_carrier_at,
    success_carrier_current,
    unpublished_negative_window,
    unpublished_positive_window,
    unpublished_unix_in_open_interval,
    unpublished_unix_instant,
)


WRONG_CANDIDATE = "000000"
HOST_TZ_NOT_UTC = "PST8"


def _other_six_digit(code: str) -> str:
    other = WRONG_CANDIDATE if code != WRONG_CANDIDATE else "111111"
    assert other != code
    return other


# ---------------------------------------------------------------------------
# A. Current clock equals explicit instant; window-0 accept twice; expire
# ---------------------------------------------------------------------------


def test_current_clock_matches_explicit_instant_accepts_twice_then_expires():
    helper = require_helper(call(TOTP, WRN3_SECRET))
    with frozen_clock(FROZEN_UNIX):
        now_code = require_named_code(emit_current_clock(helper), FROZEN_CODE)
        at_code = require_named_code(emit_for_instant(helper, FROZEN_UNIX), FROZEN_CODE)
        print(
            f"frozen {FROZEN_UNIX} now={now_code!r} at={at_code!r}",
            flush=True,
        )
        assert now_code == at_code == FROZEN_CODE, (
            "current-clock emit must equal explicit emit at the frozen instant: "
            f"now={now_code!r} at={at_code!r} expected={FROZEN_CODE!r}"
        )
        carrier = success_carrier_current(helper)
        require_accepted(check_current_clock(helper, FROZEN_CODE), carrier)
        require_accepted(check_current_clock(helper, FROZEN_CODE), carrier)
        print("frozen current-clock check accepted twice", flush=True)

    with frozen_clock(FROZEN_PLUS_STEP):
        later_carrier = success_carrier_current(helper)
        require_rejected(check_current_clock(helper, FROZEN_CODE), later_carrier)
        print(
            f"current-clock check of {FROZEN_CODE!r} rejected at {FROZEN_PLUS_STEP}",
            flush=True,
        )

    plus_carrier = success_carrier_at(helper, FROZEN_PLUS_STEP)
    require_rejected(
        check_at_instant(helper, FROZEN_CODE, FROZEN_PLUS_STEP),
        plus_carrier,
    )

    unpublished = unpublished_unix_instant(NAMED_UNIX_INSTANTS)
    rfc_helper = require_helper(call(TOTP, RFC_SECRET))
    with frozen_clock(unpublished):
        now_u = require_code(emit_current_clock(rfc_helper), 6)
        unix_u = require_code(emit_for_instant(rfc_helper, unpublished), 6)
        utc_u = require_code(
            emit_for_instant(rfc_helper, utc_datetime(unpublished)),
            6,
        )
        print(
            f"unpublished T={unpublished} now={now_u!r} unix={unix_u!r} utc={utc_u!r}",
            flush=True,
        )
        assert now_u == unix_u == utc_u, (
            "current-clock emit must equal explicit Unix and UTC-datetime "
            "emit at the same unpublished instant: "
            f"now={now_u!r} unix={unix_u!r} utc={utc_u!r}"
        )
        u_carrier = success_carrier_current(rfc_helper)
        require_accepted(check_current_clock(rfc_helper, now_u), u_carrier)
        require_accepted(check_current_clock(rfc_helper, now_u), u_carrier)
    with frozen_clock(unpublished + 30):
        expired = success_carrier_current(rfc_helper)
        require_rejected(check_current_clock(rfc_helper, now_u), expired)
        print(
            f"unpublished T+30 current-clock rejected previous code={now_u!r}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# B. Unix / aware-UTC / naive-local forms of one instant
# ---------------------------------------------------------------------------


def test_unix_aware_utc_and_naive_local_forms_of_the_same_instant_match():
    helper = require_helper(call(TOTP, ABCDEFGH_SECRET))
    forms = (
        OFFSET_INSTANT,
        utc_datetime(OFFSET_INSTANT),
        local_datetime(OFFSET_INSTANT),
    )
    observed = []
    for instant in forms:
        code = require_named_code(emit_for_instant(helper, instant), OFFSET_0_CODE)
        carrier = success_carrier_at(helper, instant)
        require_accepted(
            check_at_instant(helper, OFFSET_0_CODE, instant),
            carrier,
        )
        observed.append(code)
        print(
            f"instant form={instant!r} type={type(instant).__name__} code={code!r}",
            flush=True,
        )
    assert observed == [OFFSET_0_CODE, OFFSET_0_CODE, OFFSET_0_CODE], (
        "Unix, aware-UTC, and naive-local forms of Unix 200 must all emit "
        f"{OFFSET_0_CODE!r}: got={observed!r}"
    )


def test_aware_utc_and_naive_same_civil_differ_when_host_tz_is_not_utc():
    helper = require_helper(call(TOTP, ABCDEFGH_SECRET))
    civil = datetime(1970, 1, 1, 0, 3, 20)
    aware = civil.replace(tzinfo=timezone.utc)
    naive = civil.replace(tzinfo=None)
    assert aware.tzinfo is not None
    assert naive.tzinfo is None
    assert (
        (aware.year, aware.month, aware.day, aware.hour, aware.minute, aware.second)
        == (naive.year, naive.month, naive.day, naive.hour, naive.minute, naive.second)
    )

    with process_timezone(HOST_TZ_NOT_UTC):
        aware_code = require_named_code(
            emit_for_instant(helper, aware, isolate=False),
            OFFSET_0_CODE,
        )
        naive_code = require_code(
            emit_for_instant(helper, naive, isolate=False),
            6,
        )
        local_unix = int(naive.timestamp())
        print(
            f"tz={HOST_TZ_NOT_UTC!r} aware={aware_code!r} naive={naive_code!r} "
            f"local_unix={local_unix!r}",
            flush=True,
        )
        assert local_unix != OFFSET_INSTANT, (
            f"host timezone {HOST_TZ_NOT_UTC!r} must move naive civil "
            f"{civil!r} off Unix {OFFSET_INSTANT}: got local unix {local_unix!r}"
        )
        unix_as_local_code = require_code(
            emit_for_instant(helper, local_unix, isolate=False),
            6,
        )
        print(
            f"emit at local unix {local_unix!r}={unix_as_local_code!r}",
            flush=True,
        )
        assert naive_code == unix_as_local_code, (
            "naive civil numbers under the host timezone must emit the same "
            "string as emit at the Unix timestamp of that instant read as "
            f"local time: naive={naive_code!r} at_unix={unix_as_local_code!r} "
            f"local_unix={local_unix!r}"
        )
        assert aware_code != naive_code, (
            "aware-UTC and naive forms of the same civil numbers must differ "
            "under a non-UTC host timezone: "
            f"aware={aware_code!r} naive={naive_code!r}"
        )

    restored = require_named_code(
        emit_for_instant(helper, OFFSET_INSTANT),
        OFFSET_0_CODE,
    )
    print(f"after tz restore unix 200={restored!r}", flush=True)


# ---------------------------------------------------------------------------
# C. wrn3 uppercase matches the named frozen-clock code
# ---------------------------------------------------------------------------


def test_wrn3_uppercase_matches_named_frozen_clock_code():
    upper = WRN3_SECRET.upper()
    assert upper != WRN3_SECRET
    helper = require_helper(call(TOTP, upper))
    with frozen_clock(FROZEN_UNIX):
        code = require_named_code(emit_current_clock(helper), FROZEN_CODE)
        carrier = success_carrier_current(helper)
        require_accepted(check_current_clock(helper, FROZEN_CODE), carrier)
        print(f"uppercase wrn3 frozen code={code!r}", flush=True)
    with frozen_clock(FROZEN_PLUS_STEP):
        later = success_carrier_current(helper)
        require_rejected(check_current_clock(helper, FROZEN_CODE), later)


# ---------------------------------------------------------------------------
# D. Six-digit RFC times keep leading zeros; frozen check of 050471
# ---------------------------------------------------------------------------


def test_rfc_six_digit_times_keep_leading_zeros_and_check_050471():
    helper = require_helper(call(TOTP, RFC_SECRET))
    for instant, expected in RFC_SIX_DIGIT:
        code = require_named_code(emit_for_instant(helper, instant), expected)
        assert isinstance(code, str), (
            "six-digit RFC code must be text, not an integer: "
            f"type={type(code).__name__} value={code!r}"
        )
        assert len(code) == 6, (
            "six-digit RFC code must keep leading zeros as six characters: "
            f"length={len(code)} value={code!r} expected={expected!r}"
        )
        print(f"rfc six-digit unix={instant} code={code!r}", flush=True)

    first_instant, first_code = RFC_SIX_DIGIT[0]
    with frozen_clock(first_instant):
        carrier = success_carrier_current(helper)
        require_accepted(check_current_clock(helper, first_code), carrier)
        print(
            f"frozen {first_instant} current-clock accepted {first_code!r}",
            flush=True,
        )

    plus_carrier = success_carrier_at(helper, FROZEN_PLUS_STEP)
    require_rejected(
        check_at_instant(helper, first_code, FROZEN_PLUS_STEP),
        plus_carrier,
    )


# ---------------------------------------------------------------------------
# E. RFC 6238 Appendix B eight-digit SHA1 / SHA256 / SHA512 tables
# ---------------------------------------------------------------------------


def test_rfc6238_eight_digit_sha1_table():
    helper = require_helper(call(TOTP, RFC_SECRET, digits=8, digest=sha1))
    observed = []
    for instant, expected in RFC6238_SHA1_TABLE:
        code = require_named_code(emit_for_instant(helper, instant), expected)
        assert isinstance(code, str), (
            "eight-digit RFC 6238 SHA1 code must be text, not an integer: "
            f"unix={instant} type={type(code).__name__} value={code!r}"
        )
        assert len(code) == 8, (
            "eight-digit RFC 6238 SHA1 code must keep leading zeros as "
            f"eight characters: unix={instant} length={len(code)} "
            f"value={code!r} expected={expected!r}"
        )
        assert code == expected, (
            "eight-digit RFC 6238 SHA1 code is not the named string: "
            f"unix={instant} expected={expected!r} got={code!r}"
        )
        observed.append((instant, code))
        print(f"rfc6238 SHA1 unix={instant} code={code!r}", flush=True)
    assert len(observed) == 6, (
        "RFC 6238 Appendix B names six SHA1 instants; "
        f"observed {len(observed)} rows: {observed!r}"
    )
    assert observed == list(RFC6238_SHA1_TABLE), (
        "eight-digit RFC 6238 SHA1 table must match Appendix B at all "
        f"six named instants: got={observed!r}"
    )


def test_rfc6238_eight_digit_sha256_table():
    secret = ascii_key_as_base32(SHA256_ASCII_KEY)
    helper = require_helper(call(TOTP, secret, digits=8, digest=sha256))
    observed = []
    for instant, expected in RFC6238_SHA256_TABLE:
        code = require_named_code(emit_for_instant(helper, instant), expected)
        assert isinstance(code, str), (
            "eight-digit RFC 6238 SHA256 code must be text, not an integer: "
            f"unix={instant} type={type(code).__name__} value={code!r}"
        )
        assert len(code) == 8, (
            "eight-digit RFC 6238 SHA256 code must keep leading zeros as "
            f"eight characters: unix={instant} length={len(code)} "
            f"value={code!r} expected={expected!r}"
        )
        assert code == expected, (
            "eight-digit RFC 6238 SHA256 code is not the named string: "
            f"unix={instant} expected={expected!r} got={code!r}"
        )
        observed.append((instant, code))
        print(f"rfc6238 SHA256 unix={instant} code={code!r}", flush=True)
    assert len(observed) == 6, (
        "RFC 6238 Appendix B names six SHA256 instants; "
        f"observed {len(observed)} rows: {observed!r}"
    )
    assert observed == list(RFC6238_SHA256_TABLE), (
        "eight-digit RFC 6238 SHA256 table must match Appendix B at all "
        f"six named instants: got={observed!r}"
    )
    sha256_codes = [code for _, code in observed]
    sha1_codes = [code for _, code in RFC6238_SHA1_TABLE]
    assert sha256_codes != sha1_codes, (
        "eight-digit SHA256 codes must not match the SHA1 Appendix B table: "
        f"sha256={sha256_codes!r} sha1={sha1_codes!r}"
    )


def test_rfc6238_eight_digit_sha512_table():
    secret = ascii_key_as_base32(SHA512_ASCII_KEY)
    helper = require_helper(call(TOTP, secret, digits=8, digest=sha512))
    observed = []
    for instant, expected in RFC6238_SHA512_TABLE:
        code = require_named_code(emit_for_instant(helper, instant), expected)
        assert isinstance(code, str), (
            "eight-digit RFC 6238 SHA512 code must be text, not an integer: "
            f"unix={instant} type={type(code).__name__} value={code!r}"
        )
        assert len(code) == 8, (
            "eight-digit RFC 6238 SHA512 code must keep leading zeros as "
            f"eight characters: unix={instant} length={len(code)} "
            f"value={code!r} expected={expected!r}"
        )
        assert code == expected, (
            "eight-digit RFC 6238 SHA512 code is not the named string: "
            f"unix={instant} expected={expected!r} got={code!r}"
        )
        observed.append((instant, code))
        print(f"rfc6238 SHA512 unix={instant} code={code!r}", flush=True)
    assert len(observed) == 6, (
        "RFC 6238 Appendix B names six SHA512 instants; "
        f"observed {len(observed)} rows: {observed!r}"
    )
    assert observed == list(RFC6238_SHA512_TABLE), (
        "eight-digit RFC 6238 SHA512 table must match Appendix B at all "
        f"six named instants: got={observed!r}"
    )
    sha512_codes = [code for _, code in observed]
    sha1_codes = [code for _, code in RFC6238_SHA1_TABLE]
    assert sha512_codes != sha1_codes, (
        "eight-digit SHA512 codes must not match the SHA1 Appendix B table: "
        f"sha512={sha512_codes!r} sha1={sha1_codes!r}"
    )


# ---------------------------------------------------------------------------
# F. Non-default 60-second step; default step length 30
# ---------------------------------------------------------------------------


def test_sixty_second_step_matches_shifted_thirty_second_codes():
    sixty = require_helper(
        call(TOTP, GEZDGNBV_SECRET, digest=sha1, interval=60)
    )
    thirty = require_helper(call(TOTP, GEZDGNBV_SECRET))
    at_30 = require_named_code(emit_for_instant(sixty, 30), SIXTY_AT_30)
    at_60 = require_named_code(emit_for_instant(sixty, 60), SIXTY_AT_60)
    shifted_0 = require_named_code(emit_for_instant(thirty, 0), SIXTY_AT_30)
    shifted_30 = require_named_code(emit_for_instant(thirty, 30), SIXTY_AT_60)
    print(
        f"60s at 30/60={at_30!r}/{at_60!r} "
        f"30s at 0/30={shifted_0!r}/{shifted_30!r}",
        flush=True,
    )
    assert at_30 == shifted_0 == SIXTY_AT_30
    assert at_60 == shifted_30 == SIXTY_AT_60

    shared = unpublished_unix_in_open_interval(30, 60, {59})
    sixty_shared = require_named_code(emit_for_instant(sixty, shared), SIXTY_AT_30)
    thirty_shared = require_named_code(
        emit_for_instant(thirty, shared),
        SIXTY_AT_60,
    )
    print(
        f"unpublished (30, 60) t={shared} "
        f"60s={sixty_shared!r} 30s={thirty_shared!r}",
        flush=True,
    )
    assert sixty_shared != thirty_shared, (
        "60-second and default-30 helpers must not share a code in (30, 60): "
        f"t={shared} sixty={sixty_shared!r} thirty={thirty_shared!r}"
    )


def test_explicit_interval_30_matches_omitted_interval():
    omitted = require_helper(call(TOTP, RFC_SECRET))
    explicit = require_helper(call(TOTP, RFC_SECRET, interval=30))
    instant, expected = RFC_SIX_DIGIT[0]
    omitted_code = require_named_code(emit_for_instant(omitted, instant), expected)
    explicit_code = require_named_code(
        emit_for_instant(explicit, instant),
        expected,
    )
    print(
        f"omitted interval={omitted_code!r} explicit-30={explicit_code!r}",
        flush=True,
    )
    assert omitted_code == explicit_code == expected


# ---------------------------------------------------------------------------
# G. Whole-step offsets at Unix 200
# ---------------------------------------------------------------------------


def test_abcdefgh_whole_step_offsets_at_unix_200():
    helper = require_helper(call(TOTP, ABCDEFGH_SECRET))
    on = require_named_code(
        emit_for_instant(helper, OFFSET_INSTANT, 0),
        OFFSET_0_CODE,
    )
    prev = require_named_code(
        emit_for_instant(helper, OFFSET_INSTANT, -1),
        OFFSET_MINUS_1_CODE,
    )
    nxt = require_named_code(
        emit_for_instant(helper, OFFSET_INSTANT, 1),
        OFFSET_PLUS_1_CODE,
    )
    print(
        f"offsets at {OFFSET_INSTANT}: 0={on!r} -1={prev!r} +1={nxt!r}",
        flush=True,
    )
    mapped_prev = require_named_code(
        emit_for_instant(helper, OFFSET_INSTANT - 30, 0),
        OFFSET_MINUS_1_CODE,
    )
    mapped_next = require_named_code(
        emit_for_instant(helper, OFFSET_INSTANT + 30, 0),
        OFFSET_PLUS_1_CODE,
    )
    assert prev == mapped_prev == OFFSET_MINUS_1_CODE
    assert nxt == mapped_next == OFFSET_PLUS_1_CODE


# ---------------------------------------------------------------------------
# H. Acceptance window 1 vs 0; different-secret check does not abort
# ---------------------------------------------------------------------------


def test_window_1_accepts_adjacent_codes_window_0_only_on_step():
    helper = require_helper(call(TOTP, ABCDEFGH_SECRET))
    carrier = success_carrier_at(helper, OFFSET_INSTANT)

    require_accepted(
        check_at_instant(helper, OFFSET_MINUS_1_CODE, OFFSET_INSTANT, window=1),
        carrier,
    )
    require_accepted(
        check_at_instant(helper, OFFSET_0_CODE, OFFSET_INSTANT, window=1),
        carrier,
    )
    require_accepted(
        check_at_instant(helper, OFFSET_PLUS_1_CODE, OFFSET_INSTANT, window=1),
        carrier,
    )
    require_rejected(
        check_at_instant(helper, WINDOW_REJECT_CODE, OFFSET_INSTANT, window=1),
        carrier,
    )
    print("window 1 accepted adjacent codes and rejected 195979", flush=True)

    require_accepted(
        check_at_instant(helper, OFFSET_0_CODE, OFFSET_INSTANT, window=0),
        carrier,
    )
    require_rejected(
        check_at_instant(helper, OFFSET_MINUS_1_CODE, OFFSET_INSTANT, window=0),
        carrier,
    )
    require_rejected(
        check_at_instant(helper, OFFSET_PLUS_1_CODE, OFFSET_INSTANT, window=0),
        carrier,
    )
    require_rejected(
        check_at_instant(helper, WINDOW_REJECT_CODE, OFFSET_INSTANT, window=0),
        carrier,
    )
    print("window 0 accepted only the on-step code", flush=True)


def test_code_from_a_different_secret_is_rejected_without_abort():
    helper = require_helper(call(TOTP, ABCDEFGH_SECRET))
    carrier = success_carrier_at(helper, OFFSET_INSTANT)
    require_rejected(
        check_at_instant(helper, FROZEN_CODE, OFFSET_INSTANT, window=0),
        carrier,
    )
    require_accepted(
        check_at_instant(helper, OFFSET_0_CODE, OFFSET_INSTANT, window=0),
        carrier,
    )
    print(
        f"foreign code {FROZEN_CODE!r} rejected; on-step still accepted",
        flush=True,
    )


# ---------------------------------------------------------------------------
# I. Matching time-step numbers; negative window aborts
# ---------------------------------------------------------------------------


def test_matching_step_returns_5_6_7_rejects_195979_and_does_not_remember():
    helper = require_helper(call(TOTP, ABCDEFGH_SECRET))
    step_minus = require_step_number(
        matching_step_at(helper, OFFSET_MINUS_1_CODE, OFFSET_INSTANT, window=1),
        MATCHING_STEP_MINUS_1,
    )
    step_on = require_step_number(
        matching_step_at(helper, OFFSET_0_CODE, OFFSET_INSTANT, window=1),
        MATCHING_STEP_ON,
    )
    step_plus = require_step_number(
        matching_step_at(helper, OFFSET_PLUS_1_CODE, OFFSET_INSTANT, window=1),
        MATCHING_STEP_PLUS_1,
    )
    assert step_minus == 5, (
        "matching-step window 1 at Unix 200 must yield 5 for 451564: "
        f"got={step_minus!r}"
    )
    assert step_on == 6, (
        "matching-step window 1 at Unix 200 must yield 6 for 028307: "
        f"got={step_on!r}"
    )
    assert step_plus == 7, (
        "matching-step window 1 at Unix 200 must yield 7 for 681610: "
        f"got={step_plus!r}"
    )
    # no time-step number, and a negative result — not a
    # successful non-integer return equal to an accepted ordinary check.
    check_success = success_carrier_at(helper, OFFSET_INSTANT)
    rejected_step = matching_step_at(
        helper, WINDOW_REJECT_CODE, OFFSET_INSTANT, window=1
    )
    rejected_value = require_no_step_number(rejected_step)
    require_rejected(rejected_step, check_success)
    assert rejected_step.exception is None, (
        "matching-step of 195979 must return a negative result, not abort: "
        f"carrier={type(rejected_step.exception).__name__}"
    )
    assert type(rejected_value) is not int, (
        "matching-step of 195979 must not yield a time-step number: "
        f"got={rejected_value!r}"
    )
    print(
        "matching-step 195979 observed as failure "
        f"(not a time-step number; differs from check success "
        f"{check_success!r})",
        flush=True,
    )
    again = require_step_number(
        matching_step_at(helper, OFFSET_MINUS_1_CODE, OFFSET_INSTANT, window=1),
        MATCHING_STEP_MINUS_1,
    )
    assert again == 5, (
        "matching-step must not remember the previous 451564 success: "
        f"second call got={again!r}"
    )
    print(f"matching-step 451564 a second time still {again!r}", flush=True)

    step_on_window_0 = require_step_number(
        matching_step_at(helper, OFFSET_0_CODE, OFFSET_INSTANT, window=0),
        MATCHING_STEP_ON,
    )
    assert step_on_window_0 == 6, (
        "matching-step window 0 at Unix 200 must yield 6 for 028307: "
        f"got={step_on_window_0!r}"
    )
    neighbor_window_0 = require_no_step_number(
        matching_step_at(helper, OFFSET_MINUS_1_CODE, OFFSET_INSTANT, window=0)
    )
    assert type(neighbor_window_0) is not int, (
        "matching-step window 0 must not yield a time-step number for "
        f"451564: got={neighbor_window_0!r}"
    )


def test_negative_matching_window_aborts_unlike_rejected_candidate():
    helper = require_helper(call(TOTP, ABCDEFGH_SECRET))
    require_step_number(
        matching_step_at(helper, OFFSET_0_CODE, OFFSET_INSTANT, window=0),
        MATCHING_STEP_ON,
    )

    named_neg = matching_step_at(
        helper, OFFSET_0_CODE, OFFSET_INSTANT, window=-1
    )
    print(
        f"window -1 exception="
        f"{type(named_neg.exception).__name__ if named_neg.exception else None} "
        f"value={named_neg.value!r}",
        flush=True,
    )
    require_negative_window_aborted(named_neg)

    other = unpublished_negative_window({-1})
    unpublished_neg = matching_step_at(
        helper, OFFSET_0_CODE, OFFSET_INSTANT, window=other
    )
    print(
        f"window {other} exception="
        f"{type(unpublished_neg.exception).__name__ if unpublished_neg.exception else None} "
        f"value={unpublished_neg.value!r}",
        flush=True,
    )
    require_negative_window_aborted(unpublished_neg)

    positive = unpublished_positive_window({0, 1})
    require_step_number(
        matching_step_at(
            helper, OFFSET_0_CODE, OFFSET_INSTANT, window=positive
        ),
        MATCHING_STEP_ON,
    )
    print(f"positive window {positive} still yielded step 6", flush=True)

    require_no_step_number(
        matching_step_at(helper, WINDOW_REJECT_CODE, OFFSET_INSTANT, window=1)
    )
    carrier = success_carrier_at(helper, OFFSET_INSTANT)
    require_rejected(
        check_at_instant(helper, WINDOW_REJECT_CODE, OFFSET_INSTANT, window=0),
        carrier,
    )


# ---------------------------------------------------------------------------
# J. Compatibility-equivalent fullwidth check
# ---------------------------------------------------------------------------


def test_fullwidth_form_of_expected_totp_code_is_accepted():
    helper = require_helper(call(TOTP, ABCDEFGH_SECRET))
    ascii_code = require_named_code(
        emit_for_instant(helper, OFFSET_INSTANT),
        OFFSET_0_CODE,
    )
    carrier = success_carrier_at(helper, OFFSET_INSTANT)
    require_accepted(
        check_at_instant(helper, ascii_code, OFFSET_INSTANT),
        carrier,
    )
    named_fullwidth = fullwidth_digit_form(OFFSET_0_CODE)
    require_accepted(
        check_at_instant(helper, named_fullwidth, OFFSET_INSTANT),
        carrier,
    )
    require_rejected(
        check_at_instant(helper, WRONG_CANDIDATE, OFFSET_INSTANT),
        carrier,
    )
    print(
        f"named fullwidth accepted; {WRONG_CANDIDATE!r} rejected",
        flush=True,
    )

    rfc_helper = require_helper(call(TOTP, RFC_SECRET))
    unpublished = unpublished_unix_instant(NAMED_UNIX_INSTANTS)
    emitted = require_code(emit_for_instant(rfc_helper, unpublished), 6)
    unpublished_fullwidth = fullwidth_digit_form(emitted)
    unpublished_carrier = success_carrier_at(rfc_helper, unpublished)
    require_accepted(
        check_at_instant(rfc_helper, unpublished_fullwidth, unpublished),
        unpublished_carrier,
    )
    print(
        f"unpublished T={unpublished} ascii={emitted!r} "
        f"fullwidth={unpublished_fullwidth!r}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# K. Epoch step yields 755224; Unix −30 is refused
# ---------------------------------------------------------------------------


def test_unix_minus_1_and_minus_29_5_yield_755224_minus_30_refused():
    helper = require_helper(call(TOTP, RFC_SECRET))
    require_named_code(emit_for_instant(helper, EPOCH_MINUS_1), EPOCH_STEP_CODE)
    require_named_code(
        emit_for_instant(helper, EPOCH_MINUS_29_5),
        EPOCH_STEP_CODE,
    )

    refused = emit_for_instant(helper, EPOCH_MINUS_30)
    print(
        f"unix -30 exception="
        f"{type(refused.exception).__name__ if refused.exception else None} "
        f"value={refused.value!r}",
        flush=True,
    )
    require_negative_instant_refused(refused)

    inside = unpublished_unix_in_open_interval(-30, 0, {-1})
    inside_code = require_named_code(
        emit_for_instant(helper, inside),
        EPOCH_STEP_CODE,
    )
    print(f"unpublished epoch-step t={inside} code={inside_code!r}", flush=True)

    carrier_0 = success_carrier_at(helper, 0)
    require_rejected(
        check_at_instant(helper, WRONG_CANDIDATE, 0),
        carrier_0,
    )
    require_named_code(emit_for_instant(helper, EPOCH_MINUS_1), EPOCH_STEP_CODE)


# ---------------------------------------------------------------------------
# L. Digit count and digest construction rules on the time helper
# ---------------------------------------------------------------------------


def test_totp_digit_count_11_refused_6_and_8_accepted():
    baseline = require_helper(call(TOTP, RFC_SECRET, digits=6))
    instant, expected = RFC_SIX_DIGIT[0]
    six_code = require_named_code(emit_for_instant(baseline, instant), expected)
    assert six_code == expected, (
        "digit count 6 must emit the named six-digit RFC code: "
        f"expected={expected!r} got={six_code!r}"
    )

    refused_11 = call(TOTP, RFC_SECRET, digits=11)
    print(
        f"digits=11 exception="
        f"{type(refused_11.exception).__name__ if refused_11.exception else None} "
        f"helper={refused_11.value is not None}",
        flush=True,
    )
    require_construction_refused(refused_11)
    assert not _is_usable_helper(refused_11.value), (
        "digit count 11 must be refused at construction; a helper was returned: "
        f"type={type(refused_11.value).__name__}"
    )

    extra = unpublished_digit_count_above_ten({11})
    assert extra > 10 and extra != 11, (
        "unpublished digit count must be greater than 10 and not the named 11: "
        f"got={extra!r}"
    )
    refused_extra = call(TOTP, RFC_SECRET, digits=extra)
    print(
        f"digits={extra} exception="
        f"{type(refused_extra.exception).__name__ if refused_extra.exception else None} "
        f"helper={refused_extra.value is not None}",
        flush=True,
    )
    require_construction_refused(refused_extra)
    assert not _is_usable_helper(refused_extra.value), (
        f"digit count {extra} must be refused at construction; "
        f"a helper was returned: type={type(refused_extra.value).__name__}"
    )

    eight = require_helper(call(TOTP, RFC_SECRET, digits=8))
    eight_code = require_named_code(emit_for_instant(eight, 59), "94287082")
    assert eight_code == "94287082", (
        "digit count 8 must emit the named RFC 6238 SHA1 code at Unix 59: "
        f"got={eight_code!r}"
    )
    assert len(eight_code) == 8, (
        "digit count 8 must emit eight characters, not the default width: "
        f"length={len(eight_code)} value={eight_code!r}"
    )


def test_totp_md5_and_shake128_refused_sha_family_accepted():
    default_helper = require_helper(call(TOTP, RFC_SECRET))
    instant, expected = RFC_SIX_DIGIT[0]
    require_named_code(emit_for_instant(default_helper, instant), expected)
    sha1_helper = require_helper(call(TOTP, RFC_SECRET, digest=sha1))
    require_named_code(emit_for_instant(sha1_helper, instant), expected)

    refused_md5 = call(TOTP, RFC_SECRET, digest=md5)
    print(
        f"MD5 exception="
        f"{type(refused_md5.exception).__name__ if refused_md5.exception else None} "
        f"helper={refused_md5.value is not None}",
        flush=True,
    )
    require_construction_refused(refused_md5)

    refused_shake = call(TOTP, RFC_SECRET, digest=shake_128)
    print(
        f"SHAKE-128 exception="
        f"{type(refused_shake.exception).__name__ if refused_shake.exception else None} "
        f"helper={refused_shake.value is not None}",
        flush=True,
    )
    require_construction_refused(refused_shake)

    sha256_helper = require_helper(call(TOTP, RFC_SECRET, digest=sha256))
    sha256_0 = require_code(emit_for_instant(sha256_helper, 0), 6)
    sha256_carrier = success_carrier_at(sha256_helper, 0)
    require_accepted(check_at_instant(sha256_helper, sha256_0, 0), sha256_carrier)

    sha512_helper = require_helper(call(TOTP, RFC_SECRET, digest=sha512))
    sha512_0 = require_code(emit_for_instant(sha512_helper, 0), 6)
    sha512_carrier = success_carrier_at(sha512_helper, 0)
    require_accepted(check_at_instant(sha512_helper, sha512_0, 0), sha512_carrier)
    print(
        f"SHA256 width=6 SHA512 width=6 (literals not pinned)",
        flush=True,
    )


# ---------------------------------------------------------------------------
# M. Unpublished instants: round-trip, next-step reject, secret bind
# ---------------------------------------------------------------------------


def test_unpublished_instant_round_trips_rejects_next_step_and_binds_secret():
    unpublished = unpublished_unix_instant(NAMED_UNIX_INSTANTS)
    helper = require_helper(call(TOTP, RFC_SECRET))
    code = require_code(emit_for_instant(helper, unpublished), 6)
    carrier = success_carrier_at(helper, unpublished)
    require_accepted(check_at_instant(helper, code, unpublished), carrier)
    next_carrier = success_carrier_at(helper, unpublished + 30)
    require_rejected(check_at_instant(helper, code, unpublished + 30), next_carrier)
    other = _other_six_digit(code)
    require_rejected(check_at_instant(helper, other, unpublished), carrier)
    print(
        f"unpublished T={unpublished} code={code!r} other={other!r}",
        flush=True,
    )

    wrn_helper = require_helper(call(TOTP, WRN3_SECRET))
    wrn_code = require_code(emit_for_instant(wrn_helper, unpublished), 6)
    require_secret_bound_pair(code, wrn_code, RFC_SECRET, WRN3_SECRET)


def test_unpublished_eight_digit_sha1_and_sha256_bind_secret_and_reject_next_step():
    t2 = unpublished_unix_instant(NAMED_UNIX_INSTANTS)
    sha1_helper = require_helper(call(TOTP, RFC_SECRET, digits=8, digest=sha1))
    sha1_code = require_code(emit_for_instant(sha1_helper, t2), 8)
    sha1_carrier = success_carrier_at(sha1_helper, t2)
    require_accepted(check_at_instant(sha1_helper, sha1_code, t2), sha1_carrier)
    sha1_next = success_carrier_at(sha1_helper, t2 + 30)
    require_rejected(check_at_instant(sha1_helper, sha1_code, t2 + 30), sha1_next)
    wrn_sha1 = require_helper(call(TOTP, WRN3_SECRET, digits=8, digest=sha1))
    wrn_sha1_code = require_code(emit_for_instant(wrn_sha1, t2), 8)
    require_secret_bound_pair(sha1_code, wrn_sha1_code, RFC_SECRET, WRN3_SECRET)
    print(f"eight-digit SHA1 unpublished T2={t2} code={sha1_code!r}", flush=True)

    t3 = unpublished_unix_instant({t2} | set(NAMED_UNIX_INSTANTS))
    sha256_helper = require_helper(
        call(TOTP, RFC_SECRET, digits=8, digest=sha256)
    )
    sha256_code = require_code(emit_for_instant(sha256_helper, t3), 8)
    sha256_carrier = success_carrier_at(sha256_helper, t3)
    require_accepted(
        check_at_instant(sha256_helper, sha256_code, t3),
        sha256_carrier,
    )
    sha256_next = success_carrier_at(sha256_helper, t3 + 30)
    require_rejected(
        check_at_instant(sha256_helper, sha256_code, t3 + 30),
        sha256_next,
    )
    wrn_sha256 = require_helper(call(TOTP, WRN3_SECRET, digits=8, digest=sha256))
    wrn_sha256_code = require_code(emit_for_instant(wrn_sha256, t3), 8)
    require_secret_bound_pair(
        sha256_code, wrn_sha256_code, RFC_SECRET, WRN3_SECRET
    )
    print(
        f"eight-digit SHA256 unpublished T3={t3} code={sha256_code!r}",
        flush=True,
    )

    sha1_at_t3 = require_helper(call(TOTP, RFC_SECRET, digits=8, digest=sha1))
    sha1_t3_code = require_code(emit_for_instant(sha1_at_t3, t3), 8)
    require_secret_bound_pair(sha256_code, sha1_t3_code, RFC_SECRET, RFC_SECRET)
    print(
        f"T3 SHA256 vs SHA1 after stripping secret: "
        f"sha256={sha256_code!r} sha1={sha1_t3_code!r}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# N. Account name and issuer may be supplied
# ---------------------------------------------------------------------------


def test_account_and_issuer_may_be_supplied_without_changing_rfc_totp_code():
    account = "acct-" + secrets.token_hex(8)
    issuer = "iss-" + secrets.token_hex(8)
    helper = require_helper(call(TOTP, RFC_SECRET, name=account, issuer=issuer))
    instant, expected = RFC_SIX_DIGIT[0]
    code = require_named_code(emit_for_instant(helper, instant), expected)
    print(
        f"account={account!r} issuer={issuer!r} code={code!r}",
        flush=True,
    )
    assert code == expected, (
        "supplying an account name and issuer must not change the RFC "
        "six-digit TOTP code: "
        f"account={account!r} issuer={issuer!r} got={code!r} "
        f"expected={expected!r}"
    )


# ---------------------------------------------------------------------------
# O. Explicit SHA1 and digit 6 match defaults
# ---------------------------------------------------------------------------


def test_explicit_sha1_and_digit_6_match_totp_defaults():
    default_helper = require_helper(call(TOTP, RFC_SECRET))
    sha1_helper = require_helper(call(TOTP, RFC_SECRET, digest=sha1))
    digits6_helper = require_helper(call(TOTP, RFC_SECRET, digits=6))
    instant, expected = RFC_SIX_DIGIT[0]
    default_code = require_named_code(
        emit_for_instant(default_helper, instant),
        expected,
    )
    sha1_code = require_named_code(emit_for_instant(sha1_helper, instant), expected)
    digits6_code = require_named_code(
        emit_for_instant(digits6_helper, instant),
        expected,
    )
    print(
        f"default={default_code!r} explicit SHA1={sha1_code!r} "
        f"explicit digits=6={digits6_code!r}",
        flush=True,
    )
    assert sha1_code == default_code == expected
    assert digits6_code == expected


# ---------------------------------------------------------------------------
# P. Unpublished instant: offset, window 1/0, matching step
# ---------------------------------------------------------------------------


def test_unpublished_instant_offset_window_and_matching_step():
    helper = require_helper(call(TOTP, ABCDEFGH_SECRET))
    unpublished = unpublished_unix_instant(NAMED_UNIX_INSTANTS)

    offset_plus = require_code(
        emit_for_instant(helper, unpublished, 1),
        6,
    )
    shifted = require_code(
        emit_for_instant(helper, unpublished + 30, 0),
        6,
    )
    print(
        f"unpublished T={unpublished} offset+1={offset_plus!r} "
        f"T+30 offset0={shifted!r}",
        flush=True,
    )
    assert offset_plus == shifted, (
        "offset +1 at T must equal offset 0 at T+30: "
        f"T={unpublished} offset_plus={offset_plus!r} shifted={shifted!r}"
    )

    neighbor = offset_plus
    carrier = success_carrier_at(helper, unpublished)
    require_accepted(
        check_at_instant(helper, neighbor, unpublished, window=1),
        carrier,
    )
    require_rejected(
        check_at_instant(helper, neighbor, unpublished, window=0),
        carrier,
    )

    on_step = require_code(emit_for_instant(helper, unpublished, 0), 6)
    step_on = require_a_step_number(
        matching_step_at(helper, on_step, unpublished, window=0)
    )
    step_neighbor = require_a_step_number(
        matching_step_at(helper, neighbor, unpublished, window=1)
    )
    print(
        f"unpublished matching steps on={step_on!r} neighbor={step_neighbor!r}",
        flush=True,
    )
    assert step_on != step_neighbor, (
        "matching-step numbers for the on-step emit and the adjacent-step "
        "emit at the same unpublished instant must differ: "
        f"on={step_on!r} neighbor={step_neighbor!r}"
    )
    require_no_step_number(
        matching_step_at(helper, neighbor, unpublished, window=0)
    )
