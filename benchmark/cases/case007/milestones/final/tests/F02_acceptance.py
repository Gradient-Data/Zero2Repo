# feature: F02
"""FP-02: HMAC-based one-time passwords (HOTP).

Assertions follow the Full PRD FP-02 plus the PRD's shared defaults
(Terminology, Non-functional constraints). Failure message
text, exception class names, SHA256/SHA512/eight-digit HMAC strings,
and URI / clock-window behavior are not pinned.
"""

from __future__ import annotations

import secrets
from hashlib import md5, sha1, sha256, sha512, shake_128

from otpkit import HOTP

from _harness import call, frozen_clock, product_package_name, run_python
from F02_helpers import (
    FULLWIDTH_755224,
    GEZDGNBV_SECRET,
    NAMED_RELATIVE_COUNTS,
    N3OV_CODES,
    N3OV_SECRET,
    README_AT_0,
    README_AT_1,
    README_AT_1401,
    README_SECRET,
    RFC_CODES,
    RFC_SECRET,
    START1_AT_0,
    START1_AT_1,
    WRN3_SECRET,
    check_candidate,
    emit_at,
    fullwidth_digit_form,
    hmac_app_source,
    require_accepted,
    require_code,
    require_construction_refused,
    require_emit_refused,
    require_helper,
    require_named_code,
    require_rejected,
    require_secret_bound_pair,
    restore_base32_padding,
    success_carrier,
    unpublished_clock_pair,
    unpublished_digit_count_above_ten,
    unpublished_negative_relative_count,
    unpublished_relative_count,
    unpublished_starting_counter,
)


WRONG_CANDIDATE = "000000"


# ---------------------------------------------------------------------------
# A. RFC 4226 ten codes and 520489 at 9 / 10
# ---------------------------------------------------------------------------


def test_rfc4226_secret_emits_ten_named_codes_and_checks_520489():
    helper = require_helper(call(HOTP, RFC_SECRET))
    for count, expected in enumerate(RFC_CODES):
        code = require_named_code(emit_at(helper, count), expected)
        print(f"rfc count={count} code={code!r}", flush=True)

    carrier_9 = success_carrier(helper, 9)
    require_accepted(check_candidate(helper, RFC_CODES[9], 9), carrier_9)

    carrier_10 = success_carrier(helper, 10)
    first = require_rejected(check_candidate(helper, RFC_CODES[9], 10), carrier_10)
    second = require_rejected(check_candidate(helper, RFC_CODES[9], 10), carrier_10)
    print(
        f"520489 at 9 accepted; at 10 rejected twice "
        f"first={first!r} second={second!r}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# B. README secret, leading zero, 1401 / 1402
# ---------------------------------------------------------------------------


def test_readme_secret_keeps_leading_zero_and_checks_316439():
    helper = require_helper(call(HOTP, README_SECRET))
    require_named_code(emit_at(helper, 0), README_AT_0)

    at_one = emit_at(helper, 1)
    code_one = require_named_code(at_one, README_AT_1)
    assert isinstance(code_one, str), (
        "code at relative count 1 must be text, not an integer: "
        f"type={type(code_one).__name__} value={code_one!r}"
    )
    assert len(code_one) == 6, (
        "code at relative count 1 must keep the leading zero as six characters: "
        f"length={len(code_one)} value={code_one!r}"
    )
    print(f"readme leading-zero code={code_one!r}", flush=True)

    require_named_code(emit_at(helper, 1401), README_AT_1401)
    carrier_1401 = success_carrier(helper, 1401)
    require_accepted(check_candidate(helper, README_AT_1401, 1401), carrier_1401)
    carrier_1402 = success_carrier(helper, 1402)
    require_rejected(check_candidate(helper, README_AT_1401, 1402), carrier_1402)


# ---------------------------------------------------------------------------
# C. Published five codes; missing padding is not the caller's problem
# ---------------------------------------------------------------------------


def test_published_five_code_sequence_for_n3ov_secret():
    helper = require_helper(call(HOTP, N3OV_SECRET))
    observed = []
    for count, expected in enumerate(N3OV_CODES):
        code = require_named_code(emit_at(helper, count), expected)
        print(f"n3ov count={count} code={code!r}", flush=True)
        assert code == expected, (
            "N3OV secret must emit the named code at this relative count: "
            f"count={count} expected={expected!r} got={code!r}"
        )
        observed.append(code)
    assert tuple(observed) == N3OV_CODES, (
        "N3OV secret at relative counts 0-4 must be the published five codes: "
        f"expected={N3OV_CODES!r} got={tuple(observed)!r}"
    )


def test_n3ov_with_restored_padding_matches_named_five_codes():
    padded = restore_base32_padding(N3OV_SECRET)
    assert padded != N3OV_SECRET, (
        "padding restore must change the input spelling; "
        f"unpadded={N3OV_SECRET!r} padded={padded!r}"
    )
    assert padded.startswith(N3OV_SECRET), (
        "padding restore must only append padding to the same secret: "
        f"unpadded={N3OV_SECRET!r} padded={padded!r}"
    )
    helper = require_helper(call(HOTP, padded))
    for count, expected in enumerate(N3OV_CODES):
        code = require_named_code(emit_at(helper, count), expected)
        print(f"n3ov padded count={count} code={code!r}", flush=True)


# ---------------------------------------------------------------------------
# D. Lowercase secret equals uppercase; wrn3 is usable
# ---------------------------------------------------------------------------


def test_n3ov_lowercase_matches_named_five_codes():
    lower = N3OV_SECRET.lower()
    assert lower != N3OV_SECRET
    helper = require_helper(call(HOTP, lower))
    for count, expected in enumerate(N3OV_CODES):
        code = require_named_code(emit_at(helper, count), expected)
        print(f"n3ov lower count={count} code={code!r}", flush=True)


def test_wrn3_lowercase_is_usable_and_matches_uppercase():
    lower_helper = require_helper(call(HOTP, WRN3_SECRET))
    upper_helper = require_helper(call(HOTP, WRN3_SECRET.upper()))
    lower_code = require_code(emit_at(lower_helper, 0), 6)
    upper_code = require_code(emit_at(upper_helper, 0), 6)
    print(
        f"wrn3 lower={lower_code!r} upper={upper_code!r}",
        flush=True,
    )
    assert lower_code == upper_code, (
        "lowercase wrn3 secret must emit the same code as uppercase: "
        f"lower={lower_code!r} upper={upper_code!r}"
    )


# ---------------------------------------------------------------------------
# E. Default digits 6 and digest SHA1; explicit SHA1 / 6 match
# ---------------------------------------------------------------------------


def test_explicit_sha1_and_digit_6_match_defaults():
    default_helper = require_helper(call(HOTP, RFC_SECRET))
    sha1_helper = require_helper(call(HOTP, RFC_SECRET, digest=sha1))
    digits6_helper = require_helper(call(HOTP, RFC_SECRET, digits=6))

    default_0 = require_named_code(emit_at(default_helper, 0), RFC_CODES[0])
    default_9 = require_named_code(emit_at(default_helper, 9), RFC_CODES[9])
    sha1_0 = require_named_code(emit_at(sha1_helper, 0), RFC_CODES[0])
    sha1_9 = require_named_code(emit_at(sha1_helper, 9), RFC_CODES[9])
    digits6_0 = require_named_code(emit_at(digits6_helper, 0), RFC_CODES[0])
    print(
        f"default 0/9={default_0!r}/{default_9!r} "
        f"explicit SHA1 0/9={sha1_0!r}/{sha1_9!r} "
        f"explicit digits=6 at 0={digits6_0!r}",
        flush=True,
    )
    assert sha1_0 == default_0 == RFC_CODES[0], (
        "explicit SHA1 must emit the same relative-0 code as the default digest: "
        f"default={default_0!r} sha1={sha1_0!r} expected={RFC_CODES[0]!r}"
    )
    assert sha1_9 == default_9 == RFC_CODES[9], (
        "explicit SHA1 must emit the same relative-9 code as the default digest: "
        f"default={default_9!r} sha1={sha1_9!r} expected={RFC_CODES[9]!r}"
    )
    assert digits6_0 == RFC_CODES[0], (
        "explicit digit count 6 must emit the default six-digit relative-0 code: "
        f"got={digits6_0!r} expected={RFC_CODES[0]!r}"
    )


# ---------------------------------------------------------------------------
# F. Starting counter maps relative 0 onto default relative N
# ---------------------------------------------------------------------------


def test_starting_counter_1_on_gezdgnbv_emits_662488_then_289363():
    started = require_helper(call(HOTP, GEZDGNBV_SECRET, initial_count=1))
    require_named_code(emit_at(started, 0), START1_AT_0)
    require_named_code(emit_at(started, 1), START1_AT_1)

    default = require_helper(call(HOTP, GEZDGNBV_SECRET))
    mapped = require_code(emit_at(default, 1), 6)
    print(f"default-start relative 1={mapped!r}", flush=True)
    assert mapped == START1_AT_0, (
        "start-1 relative 0 must equal default-start relative 1: "
        f"start1={START1_AT_0!r} default_at_1={mapped!r}"
    )


def test_explicit_start_0_matches_omitted_start():
    omitted = require_helper(call(HOTP, RFC_SECRET))
    explicit = require_helper(call(HOTP, RFC_SECRET, initial_count=0))
    omitted_0 = require_named_code(emit_at(omitted, 0), RFC_CODES[0])
    explicit_0 = require_named_code(emit_at(explicit, 0), RFC_CODES[0])
    omitted_9 = require_named_code(emit_at(omitted, 9), RFC_CODES[9])
    explicit_9 = require_named_code(emit_at(explicit, 9), RFC_CODES[9])
    print(
        f"omitted 0/9={omitted_0!r}/{omitted_9!r} "
        f"explicit-start-0 0/9={explicit_0!r}/{explicit_9!r}",
        flush=True,
    )
    assert omitted_0 == explicit_0 == RFC_CODES[0], (
        "explicit starting counter 0 must match the omitted start at relative 0: "
        f"omitted={omitted_0!r} explicit={explicit_0!r} expected={RFC_CODES[0]!r}"
    )
    assert omitted_9 == explicit_9 == RFC_CODES[9], (
        "explicit starting counter 0 must match the omitted start at relative 9: "
        f"omitted={omitted_9!r} explicit={explicit_9!r} expected={RFC_CODES[9]!r}"
    )


def test_unpublished_starting_counter_matches_default_at_offset():
    k = unpublished_starting_counter({0, 1})
    default = require_helper(call(HOTP, RFC_SECRET))
    offset = require_helper(call(HOTP, RFC_SECRET, initial_count=k))

    at_zero = require_code(emit_at(offset, 0), 6)
    at_k = require_code(emit_at(default, k), 6)
    print(f"start-{k} rel 0={at_zero!r} default rel {k}={at_k!r}", flush=True)
    assert at_zero == at_k, (
        "start-k relative 0 must equal default-start relative k: "
        f"k={k} start_k={at_zero!r} default_k={at_k!r}"
    )

    at_one = require_code(emit_at(offset, 1), 6)
    at_k1 = require_code(emit_at(default, k + 1), 6)
    print(f"start-{k} rel 1={at_one!r} default rel {k + 1}={at_k1!r}", flush=True)
    assert at_one == at_k1, (
        "start-k relative 1 must equal default-start relative k+1: "
        f"k={k} start_k1={at_one!r} default_k1={at_k1!r}"
    )

    rfc_k = require_helper(call(HOTP, RFC_SECRET, initial_count=k))
    wrn_k = require_helper(call(HOTP, WRN3_SECRET, initial_count=k))
    rfc_code = require_code(emit_at(rfc_k, 0), 6)
    wrn_code = require_code(emit_at(wrn_k, 0), 6)
    require_secret_bound_pair(rfc_code, wrn_code, RFC_SECRET, WRN3_SECRET)


# ---------------------------------------------------------------------------
# G. Compatibility-equivalent check; generated codes are text
# ---------------------------------------------------------------------------


def test_fullwidth_candidate_accepted_non_equivalent_rejected_codes_are_text():
    helper = require_helper(call(HOTP, RFC_SECRET))
    emitted = require_named_code(emit_at(helper, 0), RFC_CODES[0])
    assert isinstance(emitted, str), (
        "generated code must be text: "
        f"type={type(emitted).__name__} value={emitted!r}"
    )

    carrier = success_carrier(helper, 0)
    require_accepted(check_candidate(helper, RFC_CODES[0], 0), carrier)
    require_accepted(check_candidate(helper, FULLWIDTH_755224, 0), carrier)
    require_rejected(check_candidate(helper, WRONG_CANDIDATE, 0), carrier)
    print(
        f"named fullwidth accepted; {WRONG_CANDIDATE!r} rejected",
        flush=True,
    )

    count = unpublished_relative_count(NAMED_RELATIVE_COUNTS)
    unpublished = require_code(emit_at(helper, count), 6)
    fullwidth = fullwidth_digit_form(unpublished)
    unpublished_carrier = success_carrier(helper, count)
    require_accepted(check_candidate(helper, fullwidth, count), unpublished_carrier)
    print(
        f"unpublished count={count} ascii={unpublished!r} fullwidth={fullwidth!r}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# H. Negative relative count aborts; wrong check does not
# ---------------------------------------------------------------------------


def test_negative_relative_count_aborts_unlike_wrong_candidate_check():
    helper = require_helper(call(HOTP, RFC_SECRET))
    require_named_code(emit_at(helper, 0), RFC_CODES[0])

    named_negative = emit_at(helper, -1)
    print(
        f"relative -1 exception="
        f"{type(named_negative.exception).__name__ if named_negative.exception else None} "
        f"value_is_str={isinstance(named_negative.value, str)}",
        flush=True,
    )
    require_emit_refused(named_negative)

    other = unpublished_negative_relative_count({-1})
    unpublished_negative = emit_at(helper, other)
    print(
        f"relative {other} exception="
        f"{type(unpublished_negative.exception).__name__ if unpublished_negative.exception else None} "
        f"value_is_str={isinstance(unpublished_negative.value, str)}",
        flush=True,
    )
    require_emit_refused(unpublished_negative)

    carrier = success_carrier(helper, 0)
    require_rejected(check_candidate(helper, WRONG_CANDIDATE, 0), carrier)
    require_named_code(emit_at(helper, 0), RFC_CODES[0])
    print(
        "wrong-candidate check returned; same helper still emits at 0",
        flush=True,
    )


# ---------------------------------------------------------------------------
# I. Digit count 11 refused; 6 and 8 accepted; width follows digits
# ---------------------------------------------------------------------------


def test_digit_count_11_refused_6_and_8_accepted():
    baseline = require_helper(call(HOTP, RFC_SECRET, digits=6))
    require_named_code(emit_at(baseline, 0), RFC_CODES[0])

    refused_11 = call(HOTP, RFC_SECRET, digits=11)
    print(
        f"digits=11 exception="
        f"{type(refused_11.exception).__name__ if refused_11.exception else None} "
        f"helper={refused_11.value is not None}",
        flush=True,
    )
    require_construction_refused(refused_11)

    extra = unpublished_digit_count_above_ten({11})
    refused_extra = call(HOTP, RFC_SECRET, digits=extra)
    print(
        f"digits={extra} exception="
        f"{type(refused_extra.exception).__name__ if refused_extra.exception else None} "
        f"helper={refused_extra.value is not None}",
        flush=True,
    )
    require_construction_refused(refused_extra)

    eight = require_helper(call(HOTP, RFC_SECRET, digits=8))
    code0 = require_code(emit_at(eight, 0), 8)
    carrier0 = success_carrier(eight, 0)
    require_accepted(check_candidate(eight, code0, 0), carrier0)
    require_rejected(check_candidate(eight, RFC_CODES[0], 0), carrier0)
    print(f"eight-digit relative 0 width=8 code={code0!r}", flush=True)

    count = unpublished_relative_count(NAMED_RELATIVE_COUNTS)
    code_c = require_code(emit_at(eight, count), 8)
    carrier_c = success_carrier(eight, count)
    require_accepted(check_candidate(eight, code_c, count), carrier_c)
    require_rejected(check_candidate(eight, code0, count), carrier_c)
    print(f"eight-digit unpublished count={count} code={code_c!r}", flush=True)

    wrn_eight = require_helper(call(HOTP, WRN3_SECRET, digits=8))
    wrn_code0 = require_code(emit_at(wrn_eight, 0), 8)
    require_secret_bound_pair(code0, wrn_code0, RFC_SECRET, WRN3_SECRET)


# ---------------------------------------------------------------------------
# J. MD5 / SHAKE-128 refused; SHA1 / SHA256 / SHA512 accepted
# ---------------------------------------------------------------------------


def test_md5_and_shake128_refused_sha_family_accepted():
    default_helper = require_helper(call(HOTP, RFC_SECRET))
    require_named_code(emit_at(default_helper, 0), RFC_CODES[0])
    sha1_helper = require_helper(call(HOTP, RFC_SECRET, digest=sha1))
    require_named_code(emit_at(sha1_helper, 0), RFC_CODES[0])

    refused_md5 = call(HOTP, RFC_SECRET, digest=md5)
    print(
        f"MD5 exception="
        f"{type(refused_md5.exception).__name__ if refused_md5.exception else None} "
        f"helper={refused_md5.value is not None}",
        flush=True,
    )
    require_construction_refused(refused_md5)

    refused_shake = call(HOTP, RFC_SECRET, digest=shake_128)
    print(
        f"SHAKE-128 exception="
        f"{type(refused_shake.exception).__name__ if refused_shake.exception else None} "
        f"helper={refused_shake.value is not None}",
        flush=True,
    )
    require_construction_refused(refused_shake)

    sha256_helper = require_helper(call(HOTP, RFC_SECRET, digest=sha256))
    sha256_0 = require_code(emit_at(sha256_helper, 0), 6)
    sha256_carrier_0 = success_carrier(sha256_helper, 0)
    require_accepted(check_candidate(sha256_helper, sha256_0, 0), sha256_carrier_0)

    sha512_helper = require_helper(call(HOTP, RFC_SECRET, digest=sha512))
    sha512_0 = require_code(emit_at(sha512_helper, 0), 6)
    sha512_carrier_0 = success_carrier(sha512_helper, 0)
    require_accepted(check_candidate(sha512_helper, sha512_0, 0), sha512_carrier_0)
    print(
        f"SHA256 width=6 SHA512 width=6 (literals not pinned)",
        flush=True,
    )

    count = unpublished_relative_count(NAMED_RELATIVE_COUNTS)
    sha256_c = require_code(emit_at(sha256_helper, count), 6)
    sha256_carrier_c = success_carrier(sha256_helper, count)
    require_accepted(check_candidate(sha256_helper, sha256_c, count), sha256_carrier_c)
    require_rejected(check_candidate(sha256_helper, sha256_0, count), sha256_carrier_c)

    wrn_sha256 = require_helper(call(HOTP, WRN3_SECRET, digest=sha256))
    wrn_c = require_code(emit_at(wrn_sha256, count), 6)
    require_secret_bound_pair(sha256_c, wrn_c, RFC_SECRET, WRN3_SECRET)
    print(f"SHA256 unpublished count={count}", flush=True)


# ---------------------------------------------------------------------------
# K. Wrong-counter fails; helper does not store or advance
# ---------------------------------------------------------------------------


def test_helper_does_not_store_or_advance_counter():
    helper = require_helper(call(HOTP, RFC_SECRET))
    require_named_code(emit_at(helper, 0), RFC_CODES[0])

    carrier_9 = success_carrier(helper, 9)
    require_accepted(check_candidate(helper, RFC_CODES[9], 9), carrier_9)
    require_accepted(check_candidate(helper, RFC_CODES[9], 9), carrier_9)

    carrier_10 = success_carrier(helper, 10)
    require_rejected(check_candidate(helper, RFC_CODES[9], 10), carrier_10)
    require_rejected(check_candidate(helper, RFC_CODES[9], 10), carrier_10)

    require_named_code(emit_at(helper, 0), RFC_CODES[0])
    require_named_code(emit_at(helper, 9), RFC_CODES[9])
    print("same instance still emits 755224 at 0 and 520489 at 9", flush=True)


# ---------------------------------------------------------------------------
# L. Emit at a supplied count ignores the process clock
# ---------------------------------------------------------------------------


def test_emit_at_fixed_count_ignores_process_clock():
    helper = require_helper(call(HOTP, RFC_SECRET))
    require_named_code(emit_at(helper, 0), RFC_CODES[0])

    first_epoch, second_epoch = unpublished_clock_pair(30)
    with frozen_clock(first_epoch):
        first = require_named_code(emit_at(helper, 0), RFC_CODES[0])
    with frozen_clock(second_epoch):
        second = require_named_code(emit_at(helper, 0), RFC_CODES[0])
    print(
        f"clock pair first={first!r} second={second!r} "
        f"epochs=({first_epoch!r}, {second_epoch!r})",
        flush=True,
    )
    assert first == second == RFC_CODES[0]


# ---------------------------------------------------------------------------
# M. Unpublished relative count: emit, check, neighbor reject, secret bind
# ---------------------------------------------------------------------------


def test_unpublished_relative_count_round_trips_and_rejects_neighbor():
    count = unpublished_relative_count(NAMED_RELATIVE_COUNTS)
    helper = require_helper(call(HOTP, RFC_SECRET))
    code = require_code(emit_at(helper, count), 6)
    carrier = success_carrier(helper, count)
    require_accepted(check_candidate(helper, code, count), carrier)
    neighbor_carrier = success_carrier(helper, count + 1)
    require_rejected(check_candidate(helper, code, count + 1), neighbor_carrier)

    other = "111111" if code != "111111" else "222222"
    require_rejected(check_candidate(helper, other, count), carrier)
    print(
        f"unpublished count={count} code={code!r} other={other!r}",
        flush=True,
    )

    wrn_helper = require_helper(call(HOTP, WRN3_SECRET))
    wrn_code = require_code(emit_at(wrn_helper, count), 6)
    require_secret_bound_pair(code, wrn_code, RFC_SECRET, WRN3_SECRET)


# ---------------------------------------------------------------------------
# N. Account name and issuer may be supplied
# ---------------------------------------------------------------------------


def test_account_and_issuer_may_be_supplied_without_changing_rfc_code():
    account = "acct-" + secrets.token_hex(8)
    issuer = "iss-" + secrets.token_hex(8)
    helper = require_helper(call(HOTP, RFC_SECRET, name=account, issuer=issuer))
    code = require_named_code(emit_at(helper, 0), RFC_CODES[0])
    print(
        f"account={account!r} issuer={issuer!r} code={code!r}",
        flush=True,
    )
    assert code == RFC_CODES[0], (
        "supplying an account name and issuer must not change the RFC "
        "relative-0 code: "
        f"account={account!r} issuer={issuer!r} got={code!r} "
        f"expected={RFC_CODES[0]!r}"
    )


# ---------------------------------------------------------------------------
# O. Present-package HMAC baseline
# ---------------------------------------------------------------------------


def test_hmac_helper_emits_and_accepts_code_in_child_process_with_package_present():
    """When the interpreter is present and the package is imported,
    an HMAC-based helper with secret GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ
    yields 755224 at relative count 0, and checking that string at
    relative count 0 succeeds.

    One branch: include_product=True, print of 755224 at relative
    count 0, and the check of that string. Unconditional live
    baseline. No absent-package alternative is accepted. Interpreter
    ImportError, a stripped-path first import, a printed 755224 with
    either exit status on a blocked-package child, or a missing
    755224 after a refused import is not a substitute for this
    present-package print and check.
    """
    helper = require_helper(call(HOTP, RFC_SECRET))
    require_named_code(emit_at(helper, 0), RFC_CODES[0])
    carrier = success_carrier(helper, 0)
    require_accepted(check_candidate(helper, RFC_CODES[0], 0), carrier)
    print(f"live-helper relative-0 code={RFC_CODES[0]!r}", flush=True)

    pkg = product_package_name()
    script = hmac_app_source(pkg, RFC_SECRET)

    present = run_python(code=script, include_product=True)
    print(
        f"present-package rc={present.returncode} "
        f"stdout={present.stdout_text!r} stderr={present.stderr_text[:500]!r}",
        flush=True,
    )
    assert present.returncode == 0, (
        "HMAC helper must succeed when the package is importable; "
        f"exit={present.returncode} stderr={present.stderr_text!r}"
    )
    printed_lines = [line for line in present.stdout_text.splitlines() if line]
    assert printed_lines, (
        "present-package run printed no code; "
        f"stdout={present.stdout_text!r}"
    )
    printed = printed_lines[-1]
    assert printed == RFC_CODES[0], (
        "present-package run must print the RFC relative-0 code; "
        f"got={printed!r}"
    )
