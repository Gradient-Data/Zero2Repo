# feature: F01
"""FP-01: cryptographic signing of byte values.

Assertions follow Full_PRD.original.md FP-01 (L88–L119). Failure objects are read
through the exception classes and attributes the Interface Contract
states.
"""

from __future__ import annotations

import hashlib

from signtoken import HMACAlgorithm, NoneAlgorithm, Signer  # noqa: F401

from _harness import replace_bytes
from F01_helpers import (
    BUILT_IN_DERIVATIONS,
    DEFAULT_SEPARATOR,
    assert_construction_refused,
    assert_token_accepted,
    assert_token_refused,
    attempt_sign,
    chop_last_byte,
    construct_signer,
    distinct_pair,
    expected_bytes,
    flip_bit,
    hmac_algorithm,
    make_signer,
    noop_algorithm,
    payload_carried_on_failure,
    replace_in_payload,
    require_bytes,
    require_layout,
    require_recovered_bytes,
    require_recovery_failure,
    require_round_trip,
    require_validity_failure,
    require_validity_success,
    recover_value,
    runtime_ascii_digit,
    runtime_ascii_letter,
    latin1_bytes,
    require_utf8_not_latin1,
    runtime_invalid_utf8_bytes,
    runtime_non_ascii_text,
    runtime_payload_with_sep,
    runtime_payload_without_sep,
    runtime_secret,
    runtime_text,
    runtime_unknown_derivation,
    runtime_utf8_distinct_text,
    sign_value,
    split_token,
    validity_of,
)


# ---------------------------------------------------------------------------
# S. Constructed-signer round-trip of secret-key / my string (L92)
# ---------------------------------------------------------------------------


def test_sign_recover_when_package_importable():
    signer = make_signer("secret-key")
    token = sign_value(signer, "my string")
    recovered = require_recovered_bytes(signer, token, "my string")
    assert recovered == b"my string"
    require_validity_success(validity_of(signer, token), payload=recovered)


def test_signer_round_trip_is_required_unconditionally():
    """Grade L92's constructed-signer round-trip, not an absent-package error.

    The PRD does not promise a hard error when the package is off the import
    path. A missing or do-nothing signer must not pass: constructing with
    secret ``secret-key``, signing ``my string``, recovering those bytes, and
    a successful validity check are required unconditionally.
    """
    signer = make_signer("secret-key")
    token = sign_value(signer, "my string")
    recovered = require_recovered_bytes(signer, token, "my string")
    print(
        f"recovered type={type(recovered).__name__} value={recovered!r}",
        flush=True,
    )
    require_bytes(recovered)
    assert recovered == b"my string"
    assert not isinstance(recovered, str)
    report = require_validity_success(validity_of(signer, token), payload=recovered)
    assert report != recovered


# ---------------------------------------------------------------------------
# A. Sign, recover, validity; recovery is always bytes (L90, L94, L116)
# ---------------------------------------------------------------------------


def test_public_my_string_round_trip_and_validity():
    signer = make_signer("secret-key")
    token = sign_value(signer, "my string")
    recovered = require_recovered_bytes(signer, token, "my string")
    assert recovered == b"my string"
    assert not isinstance(recovered, str)
    report = require_validity_success(validity_of(signer, token), payload=recovered)
    assert report != recovered


def test_runtime_text_round_trip_utf8_bytes():
    """Runtime text recovers as UTF-8 bytes, not latin-1 and not text (L88, L92)."""
    secret = runtime_secret()
    text = runtime_utf8_distinct_text()
    signer = make_signer(secret)
    token = sign_value(signer, text)
    recovered = require_recovered_bytes(signer, token, text)
    print(
        f"recovered type={type(recovered).__name__} value={recovered!r}",
        flush=True,
    )
    require_bytes(recovered)
    assert not isinstance(recovered, str)
    require_utf8_not_latin1(recovered, text)


def test_text_and_bytes_inputs_recover_identically():
    """Signing text and signing its UTF-8 bytes recover the same UTF-8 bytes (L92)."""
    secret = runtime_secret()
    text = runtime_utf8_distinct_text()
    payload = expected_bytes(text)
    signer = make_signer(secret)
    from_text = require_recovered_bytes(signer, sign_value(signer, text), text)
    from_bytes = require_recovered_bytes(
        signer, sign_value(signer, payload), payload
    )
    print(
        f"from_text type={type(from_text).__name__} "
        f"from_bytes type={type(from_bytes).__name__}",
        flush=True,
    )
    require_bytes(from_text)
    require_bytes(from_bytes)
    assert not isinstance(from_text, str)
    assert not isinstance(from_bytes, str)
    assert from_text == from_bytes == payload
    require_utf8_not_latin1(from_text, text)
    require_utf8_not_latin1(from_bytes, text)


def test_bytes_input_recovers_bytes():
    secret = runtime_secret()
    signer = make_signer(secret)
    text = runtime_utf8_distinct_text()
    utf8_payload = expected_bytes(text)
    recovered_utf8 = require_recovered_bytes(
        signer, sign_value(signer, utf8_payload), utf8_payload
    )
    require_bytes(recovered_utf8)
    assert not isinstance(recovered_utf8, str)
    assert recovered_utf8 == utf8_payload
    require_utf8_not_latin1(recovered_utf8, text)

    raw = runtime_invalid_utf8_bytes()
    recovered_raw = require_recovered_bytes(
        signer, sign_value(signer, raw), raw
    )
    print(
        f"raw={raw!r} recovered_raw type={type(recovered_raw).__name__}",
        flush=True,
    )
    require_bytes(recovered_raw)
    assert not isinstance(recovered_raw, str)
    assert recovered_raw == raw
    assert recovered_raw != utf8_payload


def test_non_ascii_text_recovers_utf8_bytes():
    secret = runtime_secret()
    text = runtime_non_ascii_text()
    signer = make_signer(secret)
    recovered = require_recovered_bytes(
        signer, require_round_trip(signer, text), text
    )
    print(
        f"recovered type={type(recovered).__name__} value={recovered!r}",
        flush=True,
    )
    require_bytes(recovered)
    assert not isinstance(recovered, str)
    assert recovered == expected_bytes(text)
    assert recovered.startswith(expected_bytes("\u00f1"))
    assert not recovered.startswith(latin1_bytes("\u00f1"))


class TestValidityReportIsNotPayload:
    """A validity check reports success without handing back the payload (L94, L116)."""

    def test_validity_success_does_not_return_payload(self):
        signer = make_signer("secret-key")
        token = sign_value(signer, "my string")
        recovered = require_recovered_bytes(signer, token, "my string")
        report = require_validity_success(
            validity_of(signer, token), payload=recovered
        )
        print(
            f"validity report type={type(report).__name__} value={report!r} "
            f"recovered type={type(recovered).__name__}",
            flush=True,
        )
        require_bytes(recovered)
        assert report != recovered
        assert report != b"my string"
        assert report != "my string"


# ---------------------------------------------------------------------------
# B. Token layout, default period, changed separator/payload (L90, L94–L96)
# ---------------------------------------------------------------------------


class TestTokenIsPayloadPeriodSignature:
    """A token for `my string` is payload, then a period, then a signature (L95)."""

    def test_token_is_payload_period_signature(self):
        signer = make_signer("secret-key")
        token = sign_value(signer, "my string")
        signature = require_layout(token, b"my string")
        print(
            f"token_prefix={token[: len(b'my string.') + 8]!r} "
            f"sig_len={len(signature)}",
            flush=True,
        )
        require_bytes(token)
        assert token.startswith(b"my string.")
        assert signature
        recovered = assert_token_accepted(signer, token, "my string")
        print(
            f"recovered type={type(recovered).__name__} value={recovered!r}",
            flush=True,
        )
        require_bytes(recovered)
        assert recovered == b"my string"
        assert not isinstance(recovered, str)


def test_runtime_token_layout_period():
    secret = runtime_secret()
    payload = runtime_payload_without_sep()
    signer = make_signer(secret)
    token = sign_value(signer, payload)
    signature = require_layout(token, payload)
    assert signature
    assert_token_accepted(signer, token, payload)


def test_payload_containing_default_separator_round_trips():
    secret = runtime_secret()
    payload = runtime_payload_with_sep()
    assert DEFAULT_SEPARATOR in payload
    signer = make_signer(secret)
    token = sign_value(signer, payload)
    require_layout(token, payload)
    recovered = require_recovered_bytes(signer, token, payload)
    assert recovered == payload
    require_validity_success(validity_of(signer, token), payload=recovered)


def test_replaced_separator_star_refused():
    signer = make_signer("secret-key")
    token = sign_value(signer, "my string")
    assert_token_accepted(signer, token, "my string")
    tampered = require_bytes(replace_bytes(token, b".", b"*"))
    print(f"replaced period with star: {tampered!r}", flush=True)
    assert_token_refused(signer, tampered)


def test_runtime_replaced_separator_refused():
    secret = runtime_secret()
    payload = runtime_payload_without_sep()
    signer = make_signer(secret)
    token = sign_value(signer, payload)
    assert_token_accepted(signer, token, payload)
    tampered = require_bytes(replace_bytes(token, b".", b"*"))
    assert_token_refused(signer, tampered)


def test_changed_payload_my_to_other_refused():
    signer = make_signer("secret-key")
    token = sign_value(signer, "my string")
    assert_token_accepted(signer, token, "my string")
    tampered = require_bytes(replace_bytes(token, b"my", b"other"))
    print(f"payload my->other: {tampered!r}", flush=True)
    assert_token_refused(signer, tampered)


def test_runtime_changed_payload_refused():
    secret = runtime_secret()
    marker = b"mk" + runtime_payload_without_sep(n=4)
    rest = runtime_payload_without_sep(n=4)
    payload = marker + rest
    signer = make_signer(secret)
    token = sign_value(signer, payload)
    assert_token_accepted(signer, token, payload)
    replacement = b"xx" + runtime_payload_without_sep(n=4)
    while replacement == marker:
        replacement = b"xx" + runtime_payload_without_sep(n=4)
    tampered = replace_in_payload(token, marker, replacement)
    print(f"runtime payload mutated: {tampered!r}", flush=True)
    assert_token_refused(signer, tampered)


# ---------------------------------------------------------------------------
# C. Truncated signature still exposes payload; no separator (L97, L108)
# ---------------------------------------------------------------------------


def test_truncated_signature_of_b_exposes_payload():
    signer = make_signer("secret-key")
    token = sign_value(signer, b"b")
    assert_token_accepted(signer, token, b"b")
    chopped = chop_last_byte(token)
    exc = assert_token_refused(signer, chopped, expected_payload=b"b")
    carried = payload_carried_on_failure(exc, b"b")
    assert carried == b"b"


def test_runtime_truncated_signature_exposes_payload():
    secret = runtime_secret()
    payload = runtime_payload_without_sep()
    assert payload != b"b"
    signer = make_signer(secret)
    token = sign_value(signer, payload)
    assert_token_accepted(signer, token, payload)
    chopped = chop_last_byte(token)
    exc = assert_token_refused(signer, chopped, expected_payload=payload)
    carried = payload_carried_on_failure(exc, payload)
    assert carried == payload


def test_separator_absent_is_signature_failure():
    signer = make_signer("secret-key")
    unsigned = runtime_payload_without_sep()
    assert DEFAULT_SEPARATOR not in unsigned
    print(f"separator-absent value={unsigned!r}", flush=True)
    require_recovery_failure(recover_value(signer, unsigned))
    require_validity_failure(validity_of(signer, unsigned))


def test_separator_absent_vs_bad_signature_both_unverified():
    signer = make_signer("secret-key")
    payload = runtime_payload_without_sep()
    token = sign_value(signer, payload)
    chopped = chop_last_byte(token)
    unsigned = runtime_payload_without_sep()
    assert DEFAULT_SEPARATOR not in unsigned

    chopped_exc = require_recovery_failure(recover_value(signer, chopped))
    require_validity_failure(validity_of(signer, chopped))
    carried = payload_carried_on_failure(chopped_exc, payload)

    require_recovery_failure(recover_value(signer, unsigned))
    require_validity_failure(validity_of(signer, unsigned))

    assert carried == payload
    print(
        "both unverified; truncated failure still carries original payload",
        flush=True,
    )


# ---------------------------------------------------------------------------
# D. Salt isolation, omitted-salt default, none exception (L98–L99, L111)
# ---------------------------------------------------------------------------


def test_different_salts_do_not_interchange():
    left = make_signer("secret-key", salt="salt-one")
    right = make_signer("secret-key", salt="salt-two")
    token_left = require_round_trip(left, "my string")
    token_right = require_round_trip(right, "my string")
    assert_token_refused(right, token_left)
    assert_token_refused(left, token_right)


def test_runtime_salts_do_not_interchange():
    secret = runtime_secret()
    salt_a, salt_b = distinct_pair()
    payload = runtime_text()
    left = make_signer(secret, salt=salt_a)
    right = make_signer(secret, salt=salt_b)
    token_left = require_round_trip(left, payload)
    token_right = require_round_trip(right, payload)
    assert_token_refused(right, token_left)
    assert_token_refused(left, token_right)


def test_same_salt_and_secret_round_trip():
    salt = runtime_secret()
    secret = runtime_secret()
    payload = runtime_text()
    left = make_signer(secret, salt=salt)
    right = make_signer(secret, salt=salt)
    token = require_round_trip(left, payload)
    assert_token_accepted(right, token, payload)
    token_r = require_round_trip(right, payload)
    assert_token_accepted(left, token_r, payload)


def test_omitted_salt_identically_constructed_interchange():
    secret = runtime_secret()
    payload = runtime_text()
    left = make_signer(secret)
    right = make_signer(secret)
    token = require_round_trip(left, payload)
    assert_token_accepted(right, token, payload)
    token_r = require_round_trip(right, payload)
    assert_token_accepted(left, token_r, payload)


def test_none_derivation_ignores_salt():
    secret = runtime_secret()
    salt_a, salt_b = distinct_pair()
    payload = runtime_text()
    mixing_left = make_signer(secret, salt=salt_a)
    mixing_right = make_signer(secret, salt=salt_b)
    mixing_token = require_round_trip(mixing_left, payload)
    assert_token_refused(mixing_right, mixing_token)

    none_left = make_signer(secret, salt=salt_a, key_derivation="none")
    none_right = make_signer(secret, salt=salt_b, key_derivation="none")
    none_token = require_round_trip(none_left, payload)
    assert_token_accepted(none_right, none_token, payload)
    none_token_r = require_round_trip(none_right, payload)
    assert_token_accepted(none_left, none_token_r, payload)


def test_wrong_salt_refused_on_default_derivation():
    secret = runtime_secret()
    salt_a, salt_b = distinct_pair()
    payload = runtime_text()
    left = make_signer(secret, salt=salt_a)
    right = make_signer(secret, salt=salt_b)
    token = require_round_trip(left, payload)
    assert_token_refused(right, token)


def test_wrong_salt_refused_on_concat():
    secret = runtime_secret()
    salt_a, salt_b = distinct_pair()
    payload = runtime_text()
    left = make_signer(secret, salt=salt_a, key_derivation="concat")
    right = make_signer(secret, salt=salt_b, key_derivation="concat")
    token = require_round_trip(left, payload)
    assert_token_refused(right, token)


def test_wrong_salt_refused_on_hmac():
    secret = runtime_secret()
    salt_a, salt_b = distinct_pair()
    payload = runtime_text()
    left = make_signer(secret, salt=salt_a, key_derivation="hmac")
    right = make_signer(secret, salt=salt_b, key_derivation="hmac")
    token = require_round_trip(left, payload)
    assert_token_refused(right, token)


# ---------------------------------------------------------------------------
# E. Secret lists oldest-to-newest (L100)
# ---------------------------------------------------------------------------


def test_secret_a_accepted_by_a_then_b():
    only_a = make_signer("a")
    a_then_b = make_signer(["a", "b"])
    token = require_round_trip(only_a, "my string")
    assert_token_accepted(a_then_b, token, "my string")


def test_secret_a_refused_after_dropping_a():
    only_a = make_signer("a")
    only_b = make_signer("b")
    token = require_round_trip(only_a, "my string")
    assert_token_refused(only_b, token)


def test_token_from_a_then_b_refused_by_only_a():
    a_then_b = make_signer(["a", "b"])
    only_a = make_signer("a")
    token = require_round_trip(a_then_b, "my string")
    assert_token_refused(only_a, token)


def test_token_from_a_then_b_accepted_by_b():
    a_then_b = make_signer(["a", "b"])
    only_b = make_signer("b")
    token = require_round_trip(a_then_b, "my string")
    assert_token_accepted(only_b, token, "my string")


def test_runtime_list_signs_with_newest():
    k1, k2 = distinct_pair()
    k3 = runtime_secret()
    while k3 in {k1, k2}:
        k3 = runtime_secret()
    payload = runtime_text()
    full = make_signer([k1, k2, k3])
    token = require_round_trip(full, payload)
    without_newest = make_signer([k1, k2])
    assert_token_refused(without_newest, token)
    only_newest = make_signer(k3)
    assert_token_accepted(only_newest, token, payload)


def test_runtime_older_key_verifies_until_dropped():
    k_old, k_new = distinct_pair()
    payload = runtime_text()
    only_old = make_signer(k_old)
    token = require_round_trip(only_old, payload)
    rotated = make_signer([k_old, k_new])
    assert_token_accepted(rotated, token, payload)
    dropped = make_signer(k_new)
    assert_token_refused(dropped, token)


# ---------------------------------------------------------------------------
# F. Four derivation schemes; default django-concat; unknown name (L101, L109)
# ---------------------------------------------------------------------------


def test_each_builtin_derivation_round_trips_value():
    for name in BUILT_IN_DERIVATIONS:
        signer = make_signer("secret-key", key_derivation=name)
        recovered = require_recovered_bytes(
            signer, require_round_trip(signer, "value"), "value"
        )
        assert recovered == b"value", f"{name} did not recover value as bytes"


def test_runtime_each_derivation_round_trips():
    secret = runtime_secret()
    payload = runtime_text()
    expected = expected_bytes(payload)
    for name in BUILT_IN_DERIVATIONS:
        signer = make_signer(secret, key_derivation=name)
        recovered = require_recovered_bytes(
            signer, require_round_trip(signer, payload), payload
        )
        assert recovered == expected, f"{name} did not recover the signed bytes"


def test_default_derivation_interchanges_with_django_concat():
    secret = runtime_secret()
    payload = runtime_text()
    default = make_signer(secret)
    named = make_signer(secret, key_derivation="django-concat")
    token_default = require_round_trip(default, payload)
    assert_token_accepted(named, token_default, payload)
    token_named = require_round_trip(named, payload)
    assert_token_accepted(default, token_named, payload)


def test_hmac_token_refused_by_django_concat():
    secret = runtime_secret()
    payload = runtime_text()
    hmac_signer = make_signer(secret, key_derivation="hmac")
    django_signer = make_signer(secret, key_derivation="django-concat")
    token = require_round_trip(hmac_signer, payload)
    assert_token_refused(django_signer, token)


def test_unknown_derivation_does_not_produce_verified_token():
    name = runtime_unknown_derivation()
    print(f"unknown derivation name={name!r}", flush=True)

    builtin_name = "django-concat"
    print(f"builtin baseline derivation={builtin_name!r}", flush=True)
    baseline_built = construct_signer("secret-key", key_derivation=builtin_name)
    assert baseline_built.exception is None, (
        "same constructor refused a built-in key-derivation name; "
        "construction or sign failure on an unrecognized name is accepted "
        "only after this constructor signs successfully under a built-in name"
    )
    baseline_signer = baseline_built.value
    baseline_signed = attempt_sign(baseline_signer, "value")
    assert baseline_signed.exception is None, (
        "sign failed under a built-in key-derivation name; "
        "a sign failure on an unrecognized name is accepted only after "
        "this constructor signs successfully under a built-in name"
    )
    baseline_token = require_bytes(baseline_signed.value)
    require_recovered_bytes(baseline_signer, baseline_token, "value")

    built = construct_signer("secret-key", key_derivation=name)
    if built.exception is not None:
        print(
            f"unknown derivation refused at construction: "
            f"{type(built.exception).__name__}",
            flush=True,
        )
        assert built.value is None
        return
    signer = built.value
    signed = attempt_sign(signer, "value")
    if signed.exception is not None:
        print(
            f"unknown derivation refused at sign: "
            f"{type(signed.exception).__name__}",
            flush=True,
        )
        assert signed.value is None
        return
    token = require_bytes(signed.value)
    print(f"unknown derivation emitted token_len={len(token)}", flush=True)
    require_recovery_failure(recover_value(signer, token))
    require_validity_failure(validity_of(signer, token))
    default = make_signer("secret-key")
    assert_token_refused(default, token)


# ---------------------------------------------------------------------------
# G. Default digest SHA-1; MD5/SHA-512; tamper still refused (L102, L96, L110)
# ---------------------------------------------------------------------------


def test_default_digest_matches_explicit_sha1():
    secret = runtime_secret()
    payload = runtime_text()
    default = make_signer(secret)
    explicit = make_signer(secret, digest_method=hashlib.sha1)
    token_default = sign_value(default, payload)
    token_explicit = sign_value(explicit, payload)
    print(
        f"default_len={len(token_default)} sha1_len={len(token_explicit)}",
        flush=True,
    )
    assert token_default == token_explicit


def test_md5_digest_round_trips_same_signer():
    secret = runtime_secret()
    payload = runtime_text()
    signer = make_signer(secret, digest_method=hashlib.md5)
    recovered = require_recovered_bytes(
        signer, require_round_trip(signer, payload), payload
    )
    assert recovered == expected_bytes(payload)


def test_sha512_signature_longer_than_sha1():
    secret = runtime_secret()
    payload = runtime_text()
    sha1_signer = make_signer(secret, digest_method=hashlib.sha1)
    sha512_signer = make_signer(secret, digest_method=hashlib.sha512)
    token_sha1 = require_round_trip(sha1_signer, payload)
    token_sha512 = require_round_trip(sha512_signer, payload)
    _, sig_sha1 = split_token(token_sha1)
    _, sig_sha512 = split_token(token_sha512)
    print(f"sha1_sig_len={len(sig_sha1)} sha512_sig_len={len(sig_sha512)}", flush=True)
    assert len(sig_sha512) > len(sig_sha1)


def test_sha1_signer_does_not_recover_sha512_token():
    secret = runtime_secret()
    payload = runtime_text()
    sha1_signer = make_signer(secret, digest_method=hashlib.sha1)
    sha512_signer = make_signer(secret, digest_method=hashlib.sha512)
    token = require_round_trip(sha512_signer, payload)
    assert_token_refused(sha1_signer, token)


def test_md5_signer_refuses_changed_payload():
    secret = runtime_secret()
    marker = b"mk" + runtime_payload_without_sep(n=4)
    payload = marker + runtime_payload_without_sep(n=4)
    signer = make_signer(secret, digest_method=hashlib.md5)
    token = require_round_trip(signer, payload)
    replacement = b"xx" + runtime_payload_without_sep(n=4)
    while replacement == marker:
        replacement = b"xx" + runtime_payload_without_sep(n=4)
    tampered = replace_in_payload(token, marker, replacement)
    assert_token_refused(signer, tampered)


def test_sha512_signer_refuses_changed_payload():
    secret = runtime_secret()
    marker = b"mk" + runtime_payload_without_sep(n=4)
    payload = marker + runtime_payload_without_sep(n=4)
    signer = make_signer(secret, digest_method=hashlib.sha512)
    token = require_round_trip(signer, payload)
    replacement = b"xx" + runtime_payload_without_sep(n=4)
    while replacement == marker:
        replacement = b"xx" + runtime_payload_without_sep(n=4)
    tampered = replace_in_payload(token, marker, replacement)
    assert_token_refused(signer, tampered)


# ---------------------------------------------------------------------------
# H. Default HMAC vs no-op algorithm (L103–L104, L110)
# ---------------------------------------------------------------------------


def test_hmac_signature_matches_independent_frozen_vector():
    import base64
    import hmac

    secret = b"frozen-secret-key"
    payload = b"frozen-payload"
    signer = make_signer(
        secret,
        salt=b"frozen-salt",
        key_derivation="none",
        digest_method=hashlib.sha1,
    )
    token = sign_value(signer, payload)
    body, signature = split_token(token)
    assert body == payload
    expected = hmac.new(secret, payload, hashlib.sha1).digest()
    pad = b"=" * ((4 - len(signature) % 4) % 4)
    got = base64.urlsafe_b64decode(signature + pad)
    assert hmac.compare_digest(got, expected), (
        "signature is not HMAC-SHA1(secret, payload); "
        "a concat-of-hashes construction must not pass"
    )
    weak = hashlib.sha1(secret).digest() + hashlib.sha1(payload).digest()
    assert not hmac.compare_digest(got, weak[: len(got)])


def test_hmac_rejects_changed_payload():
    secret = runtime_secret()
    payload = b"my string"
    signer = make_signer(secret)
    token = require_round_trip(signer, payload)
    tampered = require_bytes(replace_bytes(token, b"my", b"other"))
    assert_token_refused(signer, tampered)


def test_noop_algorithm_round_trips_with_empty_signature():
    signer = make_signer("secret-key", algorithm=noop_algorithm())
    token = require_round_trip(signer, "value")
    signature = require_layout(token, b"value", signature_nonempty=False)
    assert signature == b""


def test_noop_algorithm_does_not_detect_tamper():
    secret = runtime_secret()
    payload = b"my string"
    hmac_signer = make_signer(secret, algorithm=hmac_algorithm())
    hmac_token = require_round_trip(hmac_signer, payload)
    hmac_tampered = require_bytes(replace_bytes(hmac_token, b"my", b"other"))
    assert_token_refused(hmac_signer, hmac_tampered)

    noop_signer = make_signer(secret, algorithm=noop_algorithm())
    noop_token = require_round_trip(noop_signer, payload)
    noop_tampered = require_bytes(replace_bytes(noop_token, b"my", b"other"))
    recovered = require_recovered_bytes(noop_signer, noop_tampered, b"other string")
    assert recovered == b"other string"
    require_validity_success(
        validity_of(noop_signer, noop_tampered), payload=recovered
    )


def test_hmac_and_noop_tokens_do_not_interchange():
    secret = runtime_secret()
    payload = runtime_text()
    hmac_signer = make_signer(secret, algorithm=hmac_algorithm())
    noop_signer = make_signer(secret, algorithm=noop_algorithm())
    hmac_token = require_round_trip(hmac_signer, payload)
    noop_token = require_round_trip(noop_signer, payload)
    assert_token_refused(noop_signer, hmac_token)
    assert_token_refused(hmac_signer, noop_token)


# ---------------------------------------------------------------------------
# I. Separator alphabet at construction (L107)
# ---------------------------------------------------------------------------


class TestPeriodAsSeparator:
    """A period is accepted as the separator; it is also the default (L95, L107)."""

    def test_period_separator_accepted(self):
        explicit = make_signer("secret-key", sep=".")
        default = make_signer("secret-key")
        token_explicit = sign_value(explicit, "my string")
        require_layout(token_explicit, b"my string")
        recovered = require_recovered_bytes(explicit, token_explicit, "my string")
        require_bytes(recovered)
        assert recovered == b"my string"
        assert_token_accepted(default, token_explicit, "my string")

        token_default = sign_value(default, "my string")
        require_layout(token_default, b"my string")
        recovered_default = require_recovered_bytes(
            default, token_default, "my string"
        )
        assert recovered_default == b"my string"
        assert_token_accepted(explicit, token_default, "my string")


def test_hyphen_separator_refused_at_construction():
    result = construct_signer("secret-key", sep="-")
    exc = assert_construction_refused(result)
    print(
        f"hyphen separator refused: {type(exc).__name__}",
        flush=True,
    )
    assert result.value is None


def test_underscore_and_equals_separators_refused():
    for sep in ("_", "="):
        result = construct_signer("secret-key", sep=sep)
        print(f"sep={sep!r} exception={result.exception!r}", flush=True)
        assert_construction_refused(result)
        assert result.value is None, (
            f"separator {sep!r} produced a signer instead of refusing"
        )


def test_runtime_letter_and_digit_separators_refused():
    letter = runtime_ascii_letter()
    digit = runtime_ascii_digit()
    print(f"runtime letter={letter!r} digit={digit!r}", flush=True)
    letter_result = construct_signer("secret-key", sep=letter)
    digit_result = construct_signer("secret-key", sep=digit)
    assert_construction_refused(letter_result)
    assert_construction_refused(digit_result)
    assert letter_result.value is None, (
        f"letter separator {letter!r} produced a signer instead of refusing"
    )
    assert digit_result.value is None, (
        f"digit separator {digit!r} produced a signer instead of refusing"
    )


# ---------------------------------------------------------------------------
# J. Wrong secret and flipped bits, including none derivation (L111)
# ---------------------------------------------------------------------------


class TestWrongSecretRefusesRecovery:
    """A wrong secret refuses recovery and the validity check reports failure (L111)."""

    def test_wrong_secret_refuses_recovery(self):
        secret_a, secret_b = distinct_pair()
        payload = runtime_text()
        left = make_signer(secret_a)
        right = make_signer(secret_b)
        token = require_round_trip(left, payload)
        recovered = require_recovered_bytes(left, token, payload)
        require_bytes(recovered)
        assert_token_refused(right, token)


def test_flipped_bit_in_payload_refused():
    secret = runtime_secret()
    payload = runtime_payload_without_sep()
    signer = make_signer(secret)
    token = require_round_trip(signer, payload)
    body, signature = split_token(token)
    flipped = flip_bit(body, 0) + DEFAULT_SEPARATOR + signature
    print(f"flipped payload bit 0", flush=True)
    assert_token_refused(signer, flipped)


def test_flipped_bit_in_signature_refused():
    secret = runtime_secret()
    payload = runtime_payload_without_sep()
    signer = make_signer(secret)
    token = require_round_trip(signer, payload)
    body, signature = split_token(token)
    assert signature, "HMAC signature section must be non-empty to flip a bit"
    flipped = body + DEFAULT_SEPARATOR + flip_bit(signature, 0)
    print(f"flipped signature bit 0", flush=True)
    assert_token_refused(signer, flipped)


def test_none_derivation_wrong_secret_refused():
    secret_a, secret_b = distinct_pair()
    payload = runtime_text()
    left = make_signer(secret_a, key_derivation="none")
    right = make_signer(secret_b, key_derivation="none")
    token = require_round_trip(left, payload)
    assert_token_refused(right, token)


def test_none_derivation_flipped_bit_refused():
    secret = runtime_secret()
    payload = runtime_payload_without_sep()
    signer = make_signer(secret, key_derivation="none")
    token = require_round_trip(signer, payload)
    body, signature = split_token(token)
    assert signature, "none-derivation HMAC signature must be non-empty"
    payload_flipped = flip_bit(body, 0) + DEFAULT_SEPARATOR + signature
    sig_flipped = body + DEFAULT_SEPARATOR + flip_bit(signature, 0)
    assert_token_refused(signer, payload_flipped)
    assert_token_refused(signer, sig_flipped)
