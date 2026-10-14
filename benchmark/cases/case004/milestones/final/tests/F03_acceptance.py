# feature: F03
"""FP-03: timestamped signatures and expiry.

Assertions follow Full_PRD.original.md FP-03 (L154–L181). Failure objects are read
through the exception classes and attributes the Interface Contract
states.
"""

from __future__ import annotations

import hashlib
from typing import Any

from signtoken import TimedSerializer, TimestampSigner  # noqa: F401

from _harness import (
    frozen_clock,
    replace_bytes,
    workspace,
)
from F01_helpers import (
    BUILT_IN_DERIVATIONS,
    DEFAULT_SEPARATOR,
    assert_construction_refused,
    assert_token_accepted,
    assert_token_refused,
    distinct_pair,
    expected_bytes,
    hmac_algorithm,
    noop_algorithm,
    payload_carried_on_failure,
    require_recovered_bytes,
    require_recovery_failure,
    require_round_trip,
    require_validity_failure,
    require_validity_success,
    runtime_ascii_letter,
    runtime_payload_with_sep,
    runtime_payload_without_sep,
    runtime_secret,
    runtime_text,
    sign_value,
)
from F02_helpers import (
    PUBLIC_ID_MAPPING,
    TEXT_SEPARATOR,
    chop_last_character,
    dump_object,
    dump_to_stream,
    load_from_stream,
    load_object,
    load_object_call,
    require_load_failure,
    require_load_success,
    require_recovered_from_failure,
    require_signature_mismatch,
    require_unsafe_pair,
    runtime_mapping,
    runtime_text_with_period,
    unsafe_load_object,
)
from F03_helpers import (
    AGE_EXPIRED_SECONDS,
    AGE_SUCCESS_SECONDS,
    FUTURE_CHECK_INSTANT,
    MAX_AGE_SECONDS,
    OTHER_SIGNING_INSTANT,
    PUBLIC_CHANGE_NEW,
    PUBLIC_CHANGE_OLD,
    PUBLIC_CHANGED_VALUE,
    PUBLIC_SIGNING_INSTANT,
    PUBLIC_VALUE,
    arrange_dummy_suffix_token,
    arrange_missing_timestamp_token,
    arrange_replaced_out_of_range_token,
    assert_signature_mismatch_not_missing_timestamp,
    construct_timestamped_signer,
    datetimes_on_failure,
    default_json_text,
    dummy_undecodable_time_suffix,
    in_range_time_field,
    make_none_derivation_timestamped_serializer,
    make_timestamped_serializer,
    make_timestamped_signer,
    out_of_range_time_field,
    recover_timestamped,
    replace_in_timestamped_payload,
    replace_time_field,
    require_distinct_failure_kinds,
    require_exact_bytes,
    require_expired_load,
    require_expired_not_signature_mismatch,
    require_expired_recovery,
    require_integer_id,
    require_integer_list,
    require_none_derivation_default_salt_load,
    require_returned_signing_time,
    require_signing_time_absent,
    require_signing_time_on_failure,
    require_three_part_layout,
    require_timestamped_bytes,
    runtime_integer_list,
    validity_of_timestamped,
)


# ---------------------------------------------------------------------------
# S. Constructed timestamped helper round-trip when no maximum age (L160)
# ---------------------------------------------------------------------------


def test_timestamped_sign_recover_when_package_importable():
    signer = make_timestamped_signer("secret-key")
    token = sign_value(signer, PUBLIC_VALUE)
    recovered = require_timestamped_bytes(
        recover_timestamped(signer, token), PUBLIC_VALUE
    )
    require_exact_bytes(recovered)
    assert recovered == b"value"
    print(f"importable recovered={recovered!r}", flush=True)


def test_timestamped_signer_round_trip_is_required_unconditionally():
    """Grade L160's constructed-helper round-trip, not an absent-package error.

    The PRD does not promise a hard error when the package is off the import
    path. A constructed timestamped signer with secret ``secret-key`` must
    still sign ``value`` and recover those bytes when no maximum age is
    supplied.
    """
    signer = make_timestamped_signer("secret-key")
    token = sign_value(signer, PUBLIC_VALUE)
    recovered = require_timestamped_bytes(
        recover_timestamped(signer, token), PUBLIC_VALUE
    )
    require_exact_bytes(recovered)
    assert recovered == b"value"
    print(f"constructed-helper recovered={recovered!r}", flush=True)


def test_timestamped_dump_load_when_package_importable():
    helper = make_timestamped_serializer("secret-key")
    token = dump_object(helper, PUBLIC_ID_MAPPING)
    loaded = load_object(helper, token)
    assert loaded == PUBLIC_ID_MAPPING
    require_integer_id(loaded)
    print(f"importable loaded={loaded!r}", flush=True)


def test_timestamped_serializer_round_trip_is_required_unconditionally():
    """Grade L160's constructed-helper round-trip, not an absent-package error.

    The PRD does not promise a hard error when the package is off the import
    path. Dumping a mapping whose id is 42 and loading with no maximum age
    must recover that mapping.
    """
    helper = make_timestamped_serializer("secret-key")
    token = dump_object(helper, PUBLIC_ID_MAPPING)
    loaded = load_object(helper, token)
    assert loaded == PUBLIC_ID_MAPPING
    require_integer_id(loaded)
    print(f"constructed-helper loaded={loaded!r}", flush=True)


# ---------------------------------------------------------------------------
# A. Round-trip when no maximum age is supplied (L158, L162, L181)
# ---------------------------------------------------------------------------


def test_timestamped_sign_value_recovers_without_max_age():
    signer = make_timestamped_signer("secret-key")
    token = sign_value(signer, PUBLIC_VALUE)
    recovered = require_timestamped_bytes(
        recover_timestamped(signer, token), PUBLIC_VALUE
    )
    require_exact_bytes(recovered)
    assert recovered == b"value"


def test_timestamped_dump_id_42_loads_without_max_age():
    helper = make_timestamped_serializer("secret-key")
    token = dump_object(helper, PUBLIC_ID_MAPPING)
    loaded = load_object(helper, token)
    assert loaded == {"id": 42}
    require_integer_id(loaded)


def test_runtime_timestamped_sign_recover_without_max_age():
    secret = runtime_secret()
    text = runtime_text()
    signer = make_timestamped_signer(secret)
    token = sign_value(signer, text)
    recovered = require_recovered_bytes(signer, token, text)
    assert recovered == expected_bytes(text)
    print(f"runtime recovered={recovered!r}", flush=True)


def test_runtime_timestamped_dump_load_without_max_age():
    secret = runtime_secret()
    obj = runtime_mapping()
    helper = make_timestamped_serializer(secret)
    token = dump_object(helper, obj)
    loaded = load_object(helper, token)
    assert loaded == obj
    assert loaded != PUBLIC_ID_MAPPING
    print(f"runtime loaded={loaded!r}", flush=True)


def test_timestamped_serializer_round_trips_a_list():
    helper = make_timestamped_serializer(runtime_secret())
    canned = [7, 8, 9]
    sampled = runtime_integer_list()
    assert sampled != canned
    loaded_canned = None
    loaded_sampled = None
    for obj in (canned, sampled):
        token = dump_object(helper, obj)
        json_text = default_json_text(obj)
        require_three_part_layout(token, json_text)
        loaded = load_object(helper, token)
        assert loaded == obj
        assert loaded != PUBLIC_ID_MAPPING
        assert type(loaded) is not dict
        require_integer_list(loaded, obj)
        if obj is canned:
            loaded_canned = loaded
        else:
            loaded_sampled = loaded
    assert loaded_canned != loaded_sampled
    print(
        f"list loaded canned={loaded_canned!r} sampled={loaded_sampled!r}",
        flush=True,
    )


def test_timestamped_sign_payload_containing_separator_recovers():
    secret = runtime_secret()
    payload = runtime_payload_with_sep()
    assert DEFAULT_SEPARATOR in payload
    signer = make_timestamped_signer(secret)
    token = sign_value(signer, payload)
    require_three_part_layout(token, payload)
    recovered = require_timestamped_bytes(
        recover_timestamped(signer, token), payload
    )
    require_exact_bytes(recovered)
    assert recovered == payload
    assert DEFAULT_SEPARATOR in recovered

    plain = runtime_payload_without_sep()
    assert DEFAULT_SEPARATOR not in plain
    plain_signer = make_timestamped_signer(secret)
    plain_token = sign_value(plain_signer, plain)
    plain_recovered = require_timestamped_bytes(
        recover_timestamped(plain_signer, plain_token), plain
    )
    require_exact_bytes(plain_recovered)
    assert plain_recovered == plain
    assert DEFAULT_SEPARATOR not in plain_recovered
    assert recovered != plain_recovered
    print(
        f"separator payload recovered_len={len(recovered)} "
        f"plain_len={len(plain_recovered)}",
        flush=True,
    )


def test_timestamped_dump_object_whose_json_contains_period_loads():
    helper = make_timestamped_serializer(runtime_secret())
    obj = runtime_text_with_period()
    json_text = default_json_text(obj)
    assert "." in json_text
    token = dump_object(helper, obj)
    require_three_part_layout(token, json_text)
    loaded = load_object(helper, token)
    assert loaded == obj
    assert type(loaded) is str
    assert "." in loaded

    plain = runtime_text()
    plain_json = default_json_text(plain)
    assert "." not in plain_json
    plain_token = dump_object(helper, plain)
    require_three_part_layout(plain_token, plain_json)
    plain_loaded = load_object(helper, plain_token)
    assert plain_loaded == plain
    assert loaded != plain_loaded
    print(
        f"period-json loaded={loaded!r} plain_loaded={plain_loaded!r}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# L158. Timestamped types still satisfy FP-01 / FP-02 obligations
# ---------------------------------------------------------------------------


def test_timestamped_signer_refuses_value_without_separator():
    signer = make_timestamped_signer("secret-key")
    unsigned = runtime_payload_without_sep()
    assert DEFAULT_SEPARATOR not in unsigned
    print(f"separator-absent value={unsigned!r}", flush=True)
    require_recovery_failure(recover_timestamped(signer, unsigned))
    require_validity_failure(validity_of_timestamped(signer, unsigned))


def test_timestamped_signer_refuses_invalid_separator_at_construction():
    for sep in ("-", "_", "=", "a", "1"):
        result = construct_timestamped_signer("secret-key", sep=sep)
        print(f"sep={sep!r} exception={result.exception!r}", flush=True)
        assert_construction_refused(result)
    period = make_timestamped_signer("secret-key", sep=".")
    require_recovered_bytes(period, sign_value(period, PUBLIC_VALUE), PUBLIC_VALUE)


def test_timestamped_signer_each_derivation_round_trips_and_hmac_does_not_interchange():
    for name in BUILT_IN_DERIVATIONS:
        signer = make_timestamped_signer("secret-key", key_derivation=name)
        recovered = require_recovered_bytes(
            signer, require_round_trip(signer, "value"), "value"
        )
        assert recovered == b"value", f"{name} did not recover value as bytes"
    secret = runtime_secret()
    payload = runtime_text()
    hmac_signer = make_timestamped_signer(secret, key_derivation="hmac")
    django_signer = make_timestamped_signer(secret, key_derivation="django-concat")
    token = require_round_trip(hmac_signer, payload)
    assert_token_refused(django_signer, token)


def test_timestamped_signer_digest_default_sha1_explicit_round_trip_mismatch_refused():
    secret = runtime_secret()
    payload = runtime_text()
    default = make_timestamped_signer(secret)
    explicit = make_timestamped_signer(secret, digest_method=hashlib.sha1)
    token_default = sign_value(default, payload)
    token_explicit = sign_value(explicit, payload)
    print(
        f"default_len={len(token_default)} sha1_len={len(token_explicit)}",
        flush=True,
    )
    assert token_default == token_explicit
    md5 = make_timestamped_signer(secret, digest_method=hashlib.md5)
    require_round_trip(md5, payload)
    sha1 = make_timestamped_signer(secret, digest_method=hashlib.sha1)
    sha512 = make_timestamped_signer(secret, digest_method=hashlib.sha512)
    token = require_round_trip(sha512, payload)
    assert_token_refused(sha1, token)


def test_timestamped_signer_default_hmac_noop_recovers_algorithms_do_not_interchange():
    hmac_default = make_timestamped_signer("secret-key")
    require_round_trip(hmac_default, "value")
    noop = make_timestamped_signer("secret-key", algorithm=noop_algorithm())
    require_round_trip(noop, "value")
    secret = runtime_secret()
    payload = runtime_text()
    hmac_rt = make_timestamped_signer(secret, algorithm=hmac_algorithm())
    noop_rt = make_timestamped_signer(secret, algorithm=noop_algorithm())
    hmac_token = require_round_trip(hmac_rt, payload)
    noop_token = require_round_trip(noop_rt, payload)
    assert_token_refused(noop_rt, hmac_token)
    assert_token_refused(hmac_rt, noop_token)


def test_timestamped_signer_secret_list_oldest_to_newest():
    only_a = make_timestamped_signer("a")
    a_then_b = make_timestamped_signer(["a", "b"])
    token_a = require_round_trip(only_a, "value")
    assert_token_accepted(a_then_b, token_a, "value")
    only_b = make_timestamped_signer("b")
    assert_token_refused(only_b, token_a)
    token_ab = require_round_trip(a_then_b, "value")
    assert_token_refused(only_a, token_ab)
    assert_token_accepted(only_b, token_ab, "value")


def test_timestamped_serializer_tamper_transforms_are_signature_mismatch():
    helper = make_timestamped_serializer("secret-key")
    token = dump_object(helper, PUBLIC_ID_MAPPING)
    require_load_success(load_object_call(helper, token), expected=PUBLIC_ID_MAPPING)

    uppered = token.upper() if isinstance(token, str) else token.upper()
    if uppered == token:
        raise AssertionError(f"uppercasing was a no-op on {token!r}")
    require_signature_mismatch(helper, uppered)

    extra = runtime_ascii_letter()
    appended = token + extra if isinstance(token, str) else token + extra.encode("ascii")
    require_signature_mismatch(helper, appended)

    if isinstance(token, bytes):
        first = token[:1]
        replaced_first = (b"X" if first != b"X" else b"Y") + token[1:]
        dropped_sep = replace_bytes(token, DEFAULT_SEPARATOR, b"", count=1)
    else:
        first_ch = token[:1]
        replaced_first = ("X" if first_ch != "X" else "Y") + token[1:]
        dropped_sep = replace_bytes(token, TEXT_SEPARATOR, "", count=1)
    require_signature_mismatch(helper, replaced_first)
    require_signature_mismatch(helper, dropped_sep)


def test_timestamped_serializer_per_call_salt_is_isolated():
    helper = make_timestamped_serializer("secret-key")
    baseline = dump_object(helper, PUBLIC_ID_MAPPING)
    assert load_object(helper, baseline) == PUBLIC_ID_MAPPING
    token = dump_object(helper, PUBLIC_ID_MAPPING, salt="other")
    require_signature_mismatch(helper, token)
    loaded = load_object(helper, token, salt="other")
    assert loaded == PUBLIC_ID_MAPPING


def test_timestamped_serializer_none_derivation_salt_other_loads_under_default_salt():
    mixing = make_timestamped_serializer("secret-key")
    mixing_token = dump_object(mixing, PUBLIC_ID_MAPPING, salt="other")
    require_signature_mismatch(
        mixing, mixing_token, expected=PUBLIC_ID_MAPPING
    )

    none_helper = make_none_derivation_timestamped_serializer("secret-key")
    none_token = dump_object(none_helper, PUBLIC_ID_MAPPING, salt="other")
    loaded_with_salt = load_object(none_helper, none_token, salt="other")
    assert loaded_with_salt == PUBLIC_ID_MAPPING
    loaded_default = require_none_derivation_default_salt_load(
        none_helper, none_token, PUBLIC_ID_MAPPING
    )
    assert loaded_default == PUBLIC_ID_MAPPING
    print(
        "none derivation: timestamped dump with salt other loaded under "
        "the helper's default salt",
        flush=True,
    )

    secret = runtime_secret()
    obj = runtime_mapping()
    runtime_none = make_none_derivation_timestamped_serializer(secret)
    runtime_token = dump_object(runtime_none, obj, salt="other")
    runtime_loaded = require_none_derivation_default_salt_load(
        runtime_none, runtime_token, obj
    )
    assert runtime_loaded == obj


def test_timestamped_serializer_fallback_loads_when_current_cannot_verify():
    sha256 = make_timestamped_serializer(
        "secret-key", signer_kwargs={"digest_method": hashlib.sha256}
    )
    token = dump_object(sha256, PUBLIC_ID_MAPPING)
    with_fb = make_timestamped_serializer(
        "secret-key",
        signer_kwargs={"digest_method": hashlib.sha1},
        fallback_signers=[{"digest_method": hashlib.sha256}],
    )
    assert load_object(with_fb, token) == PUBLIC_ID_MAPPING
    sha1_only = make_timestamped_serializer(
        "secret-key", signer_kwargs={"digest_method": hashlib.sha1}
    )
    require_signature_mismatch(sha1_only, token)


def test_timestamped_serializer_dump_then_load_through_file_stream():
    with workspace() as ws:
        helper = make_timestamped_serializer("secret-key")
        with ws.open_text_write("id42.txt") as fp:
            dump_to_stream(helper, PUBLIC_ID_MAPPING, fp)
        with ws.open_text("id42.txt") as fp:
            loaded = require_load_success(
                load_from_stream(helper, fp), expected=PUBLIC_ID_MAPPING
            )
        assert loaded == {"id": 42}

        obj = runtime_mapping()
        assert obj != PUBLIC_ID_MAPPING
        with ws.open_text_write("runtime.txt") as fp:
            dump_to_stream(helper, obj, fp)
        with ws.open_text("runtime.txt") as fp:
            loaded_rt = require_load_success(load_from_stream(helper, fp), expected=obj)
        assert loaded_rt == obj


# ---------------------------------------------------------------------------
# B. Time field between payload and signature; asked-for signing time (L163)
# ---------------------------------------------------------------------------


def test_timestamped_token_has_time_field_between_payload_and_signature():
    signer = make_timestamped_signer("secret-key")
    token = sign_value(signer, PUBLIC_VALUE)
    require_three_part_layout(token, b"value")

    secret = runtime_secret()
    runtime_signer = make_timestamped_signer(secret)
    runtime_payload = runtime_text()
    runtime_token = sign_value(runtime_signer, runtime_payload)
    require_three_part_layout(runtime_token, expected_bytes(runtime_payload))

    sep_payload = runtime_payload_with_sep()
    sep_token = sign_value(make_timestamped_signer(secret), sep_payload)
    require_three_part_layout(sep_token, sep_payload)


def test_timestamped_serializer_token_has_time_field():
    helper = make_timestamped_serializer("secret-key")
    token = dump_object(helper, PUBLIC_ID_MAPPING)
    public_payload = default_json_text(PUBLIC_ID_MAPPING)
    public_time = require_three_part_layout(token, public_payload)
    assert public_time, "time field between payload and signature is empty"

    secret = runtime_secret()
    runtime_helper = make_timestamped_serializer(secret)
    obj = runtime_mapping()
    runtime_token = dump_object(runtime_helper, obj)
    runtime_time = require_three_part_layout(runtime_token, default_json_text(obj))
    assert runtime_time, "runtime token time field is empty"

    period_obj = runtime_text_with_period()
    period_token = dump_object(make_timestamped_serializer(secret), period_obj)
    period_time = require_three_part_layout(
        period_token, default_json_text(period_obj)
    )
    assert period_time, "period-json token time field is empty"
    print(
        f"serializer time fields public_len={len(public_time)} "
        f"runtime_len={len(runtime_time)} period_len={len(period_time)}",
        flush=True,
    )


def test_ask_for_signing_time_signer_is_aware_utc_equal_to_frozen_instant():
    signer = make_timestamped_signer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = sign_value(signer, PUBLIC_VALUE)
        instant = clock.instant
        result = recover_timestamped(signer, token, return_timestamp=True)
        value, dt = require_returned_signing_time(result, b"value", instant)
        assert value == b"value"
        print(f"signer asked dt={dt.isoformat()} instant={instant.isoformat()}", flush=True)


def test_ask_for_signing_time_serializer_is_aware_utc_equal_to_frozen_instant():
    helper = make_timestamped_serializer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper, PUBLIC_ID_MAPPING)
        instant = clock.instant
        result = load_object_call(helper, token, return_timestamp=True)
        value, dt = require_returned_signing_time(result, PUBLIC_ID_MAPPING, instant)
        assert value == {"id": 42}
        print(f"serializer asked dt={dt.isoformat()}", flush=True)


def test_runtime_ask_for_signing_time_equals_other_frozen_instant():
    secret = runtime_secret()
    text = runtime_text()
    obj = runtime_mapping()
    signer = make_timestamped_signer(secret)
    helper = make_timestamped_serializer(secret)
    with frozen_clock(OTHER_SIGNING_INSTANT) as clock:
        signed = sign_value(signer, text)
        dumped = dump_object(helper, obj)
        instant = clock.instant
        assert instant != PUBLIC_SIGNING_INSTANT
        require_returned_signing_time(
            recover_timestamped(signer, signed, return_timestamp=True),
            expected_bytes(text),
            instant,
        )
        require_returned_signing_time(
            load_object_call(helper, dumped, return_timestamp=True),
            obj,
            instant,
        )


def test_second_helper_reads_signing_time_from_token_signer():
    secret = runtime_secret()
    first = make_timestamped_signer(secret)
    second = make_timestamped_signer(secret)
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = sign_value(first, PUBLIC_VALUE)
        instant = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        result = recover_timestamped(second, token, return_timestamp=True)
        require_returned_signing_time(result, b"value", instant)
        assert clock.instant != instant


def test_second_helper_reads_signing_time_from_token_serializer():
    secret = runtime_secret()
    first = make_timestamped_serializer(secret)
    second = make_timestamped_serializer(secret)
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(first, PUBLIC_ID_MAPPING)
        instant = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        result = load_object_call(second, token, return_timestamp=True)
        require_returned_signing_time(result, PUBLIC_ID_MAPPING, instant)
        assert clock.instant != instant


def test_same_helper_signing_time_is_per_token_not_last_sign_signer():
    signer = make_timestamped_signer(runtime_secret())
    later_value = runtime_text()
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token_a = sign_value(signer, PUBLIC_VALUE)
        instant_a = clock.instant
        clock.tick(3)
        token_b = sign_value(signer, later_value)
        instant_b = clock.instant
        assert instant_a != instant_b
        require_returned_signing_time(
            recover_timestamped(signer, token_a, return_timestamp=True),
            b"value",
            instant_a,
        )
        require_returned_signing_time(
            recover_timestamped(signer, token_b, return_timestamp=True),
            expected_bytes(later_value),
            instant_b,
        )


def test_same_helper_signing_time_is_per_token_not_last_sign_serializer():
    helper = make_timestamped_serializer(runtime_secret())
    later_obj = runtime_mapping()
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token_a = dump_object(helper, PUBLIC_ID_MAPPING)
        instant_a = clock.instant
        clock.tick(3)
        token_b = dump_object(helper, later_obj)
        instant_b = clock.instant
        assert instant_a != instant_b
        assert later_obj != PUBLIC_ID_MAPPING
        require_returned_signing_time(
            load_object_call(helper, token_a, return_timestamp=True),
            PUBLIC_ID_MAPPING,
            instant_a,
        )
        require_returned_signing_time(
            load_object_call(helper, token_b, return_timestamp=True),
            later_obj,
            instant_b,
        )


# ---------------------------------------------------------------------------
# C. Maximum age 10: 1s success, 11s expired (L164, L176, L180–L181)
# ---------------------------------------------------------------------------


def test_signer_max_age_10_succeeds_at_one_second():
    signer = make_timestamped_signer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = sign_value(signer, PUBLIC_VALUE)
        clock.tick(AGE_SUCCESS_SECONDS)
        recovered = require_timestamped_bytes(
            recover_timestamped(signer, token, max_age=MAX_AGE_SECONDS),
            PUBLIC_VALUE,
        )
        assert recovered == b"value"


def test_signer_max_age_10_expired_at_eleven_seconds():
    signer = make_timestamped_signer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = sign_value(signer, PUBLIC_VALUE)
        instant = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        recovered = require_timestamped_bytes(
            recover_timestamped(signer, token, max_age=MAX_AGE_SECONDS),
            PUBLIC_VALUE,
        )
        assert recovered == b"value"
        clock.tick(AGE_EXPIRED_SECONDS - AGE_SUCCESS_SECONDS)
        exc = require_expired_recovery(
            recover_timestamped(signer, token, max_age=MAX_AGE_SECONDS),
            payload=PUBLIC_VALUE,
            instant=instant,
        )
        carried = payload_carried_on_failure(exc, expected_bytes(PUBLIC_VALUE))
        assert carried == b"value"
        dts = datetimes_on_failure(exc)
        assert dts, "expiry must carry a signing-time datetime"
        assert instant in dts


def test_signer_validity_max_age_10_success_then_failure():
    signer = make_timestamped_signer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = sign_value(signer, PUBLIC_VALUE)
        clock.tick(AGE_SUCCESS_SECONDS)
        require_validity_success(
            validity_of_timestamped(signer, token, max_age=MAX_AGE_SECONDS),
            payload=expected_bytes(PUBLIC_VALUE),
        )
        clock.tick(AGE_EXPIRED_SECONDS - AGE_SUCCESS_SECONDS)
        require_validity_failure(
            validity_of_timestamped(signer, token, max_age=MAX_AGE_SECONDS)
        )


def test_signer_eleven_seconds_without_max_age_still_recovers():
    signer = make_timestamped_signer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = sign_value(signer, PUBLIC_VALUE)
        clock.tick(AGE_EXPIRED_SECONDS)
        recovered = require_recovered_bytes(signer, token, PUBLIC_VALUE)
        assert recovered == b"value"
        require_validity_success(
            validity_of_timestamped(signer, token),
            payload=recovered,
        )


def test_signer_return_signing_time_with_max_age_succeeds_then_expires():
    signer = make_timestamped_signer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = sign_value(signer, PUBLIC_VALUE)
        instant = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        value, dt = require_returned_signing_time(
            recover_timestamped(
                signer, token, max_age=MAX_AGE_SECONDS, return_timestamp=True
            ),
            b"value",
            instant,
        )
        assert value == b"value"
        assert dt == instant
        clock.tick(AGE_EXPIRED_SECONDS - AGE_SUCCESS_SECONDS)
        exc = require_expired_recovery(
            recover_timestamped(
                signer, token, max_age=MAX_AGE_SECONDS, return_timestamp=True
            ),
            payload=PUBLIC_VALUE,
            instant=instant,
        )
        dts = datetimes_on_failure(exc)
        assert dts, "expiry must carry a signing-time datetime, not a success pair"
        assert instant in dts


def test_serializer_max_age_10_succeeds_at_one_second_and_expires_at_eleven():
    helper = make_timestamped_serializer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper, PUBLIC_ID_MAPPING)
        instant = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        loaded = load_object(helper, token, max_age=MAX_AGE_SECONDS)
        assert loaded == {"id": 42}
        clock.tick(AGE_EXPIRED_SECONDS - AGE_SUCCESS_SECONDS)
        require_expired_load(
            load_object_call(helper, token, max_age=MAX_AGE_SECONDS),
            token=token,
            expected_object=PUBLIC_ID_MAPPING,
            instant=instant,
        )


def test_serializer_eleven_seconds_without_max_age_still_loads():
    helper = make_timestamped_serializer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper, PUBLIC_ID_MAPPING)
        clock.tick(AGE_EXPIRED_SECONDS)
        loaded = load_object(helper, token)
        assert loaded == {"id": 42}


def test_serializer_return_signing_time_with_max_age_succeeds_then_expires():
    helper = make_timestamped_serializer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper, PUBLIC_ID_MAPPING)
        instant = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        require_returned_signing_time(
            load_object_call(
                helper, token, max_age=MAX_AGE_SECONDS, return_timestamp=True
            ),
            PUBLIC_ID_MAPPING,
            instant,
        )
        assert clock.instant != instant
        clock.tick(AGE_EXPIRED_SECONDS - AGE_SUCCESS_SECONDS)
        require_expired_load(
            load_object_call(
                helper, token, max_age=MAX_AGE_SECONDS, return_timestamp=True
            ),
            token=token,
            expected_object=PUBLIC_ID_MAPPING,
            instant=instant,
        )


def test_runtime_signer_and_serializer_max_age_10():
    secret = runtime_secret()
    text = runtime_text()
    obj = runtime_mapping()
    signer = make_timestamped_signer(secret)
    helper = make_timestamped_serializer(secret)
    with frozen_clock(OTHER_SIGNING_INSTANT) as clock:
        signed = sign_value(signer, text)
        dumped = dump_object(helper, obj)
        instant = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        require_timestamped_bytes(
            recover_timestamped(signer, signed, max_age=MAX_AGE_SECONDS),
            text,
        )
        assert load_object(helper, dumped, max_age=MAX_AGE_SECONDS) == obj
        require_returned_signing_time(
            load_object_call(
                helper, dumped, max_age=MAX_AGE_SECONDS, return_timestamp=True
            ),
            obj,
            instant,
        )
        clock.tick(AGE_EXPIRED_SECONDS - AGE_SUCCESS_SECONDS)
        require_expired_recovery(
            recover_timestamped(signer, signed, max_age=MAX_AGE_SECONDS),
            payload=text,
            instant=instant,
        )
        require_expired_load(
            load_object_call(
                helper, dumped, max_age=MAX_AGE_SECONDS, return_timestamp=True
            ),
            token=dumped,
            expected_object=obj,
            instant=instant,
        )


def test_second_helper_max_age_10_expires_at_eleven():
    secret = runtime_secret()
    first_signer = make_timestamped_signer(secret)
    second_signer = make_timestamped_signer(secret)
    first_helper = make_timestamped_serializer(secret)
    second_helper = make_timestamped_serializer(secret)
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        signed = sign_value(first_signer, PUBLIC_VALUE)
        dumped = dump_object(first_helper, PUBLIC_ID_MAPPING)
        instant = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        require_timestamped_bytes(
            recover_timestamped(second_signer, signed, max_age=MAX_AGE_SECONDS),
            PUBLIC_VALUE,
        )
        assert load_object(second_helper, dumped, max_age=MAX_AGE_SECONDS) == {
            "id": 42
        }
        clock.tick(AGE_EXPIRED_SECONDS - AGE_SUCCESS_SECONDS)
        require_expired_recovery(
            recover_timestamped(second_signer, signed, max_age=MAX_AGE_SECONDS),
            payload=PUBLIC_VALUE,
            instant=instant,
        )
        require_expired_load(
            load_object_call(second_helper, dumped, max_age=MAX_AGE_SECONDS),
            token=dumped,
            expected_object=PUBLIC_ID_MAPPING,
            instant=instant,
        )


def test_expiry_is_distinguishable_from_mismatch_missing_and_malformed():
    signer = make_timestamped_signer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        legal = sign_value(signer, PUBLIC_VALUE)
        instant = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        require_timestamped_bytes(
            recover_timestamped(signer, legal, max_age=MAX_AGE_SECONDS),
            PUBLIC_VALUE,
        )
        clock.tick(AGE_EXPIRED_SECONDS - AGE_SUCCESS_SECONDS)
        expired_exc = require_expired_recovery(
            recover_timestamped(signer, legal, max_age=MAX_AGE_SECONDS),
            payload=PUBLIC_VALUE,
            instant=instant,
        )
        still_ok = require_recovered_bytes(signer, legal, PUBLIC_VALUE)
        assert still_ok == b"value"

    missing = arrange_missing_timestamp_token(PUBLIC_VALUE, secret="secret-key")
    missing_exc = require_recovery_failure(recover_timestamped(signer, missing))
    require_signing_time_absent(missing_exc)
    require_recovery_failure(recover_timestamped(signer, missing))

    malformed = arrange_dummy_suffix_token(PUBLIC_VALUE, secret="secret-key")
    malformed_exc = require_recovery_failure(recover_timestamped(signer, malformed))
    require_signing_time_absent(malformed_exc)

    changed = replace_in_timestamped_payload(
        sign_value(signer, PUBLIC_CHANGED_VALUE),
        PUBLIC_CHANGE_OLD,
        PUBLIC_CHANGE_NEW,
    )
    changed_exc = require_recovery_failure(recover_timestamped(signer, changed))
    require_signing_time_on_failure(changed_exc)

    expired_dts = datetimes_on_failure(expired_exc)
    assert expired_dts, "expiry must carry a signing-time datetime"
    assert not datetimes_on_failure(missing_exc)
    assert not datetimes_on_failure(malformed_exc)
    require_distinct_failure_kinds(
        malformed_exc,
        missing_exc,
        expect=("malformed-timestamp", "missing-timestamp"),
    )
    print(
        "expiry vs missing/malformed/mismatch distinguished by datetime "
        "presence and by whether the legal token recovers without max_age; "
        "malformed vs missing remain distinct after covariate strip",
        flush=True,
    )


# ---------------------------------------------------------------------------
# D. Expiry still carries payload and signing time (L165, L180)
# ---------------------------------------------------------------------------


def test_serializer_expiry_inspected_payload_decodes_to_id_42():
    helper = make_timestamped_serializer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper, PUBLIC_ID_MAPPING)
        instant = clock.instant
        clock.tick(AGE_EXPIRED_SECONDS)
        exc = require_expired_load(
            load_object_call(helper, token, max_age=MAX_AGE_SECONDS),
            token=token,
            expected_object=PUBLIC_ID_MAPPING,
            instant=instant,
        )
        decoded = require_recovered_from_failure(
            exc, PUBLIC_ID_MAPPING, token=token
        )
        assert decoded == {"id": 42}
        dts = datetimes_on_failure(exc)
        assert dts, "expiry must expose a signing-time datetime"
        assert instant in dts


def test_serializer_expiry_exposes_signing_time_equal_to_instant():
    helper = make_timestamped_serializer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper, PUBLIC_ID_MAPPING)
        instant = clock.instant
        clock.tick(AGE_EXPIRED_SECONDS)
        exc = require_load_failure(
            load_object_call(helper, token, max_age=MAX_AGE_SECONDS)
        )
        dt = require_signing_time_on_failure(exc, instant)
        assert dt == instant


def test_runtime_serializer_expiry_payload_and_signing_time():
    secret = runtime_secret()
    obj = runtime_mapping()
    assert obj != PUBLIC_ID_MAPPING
    helper = make_timestamped_serializer(secret)
    with frozen_clock(OTHER_SIGNING_INSTANT) as clock:
        token = dump_object(helper, obj)
        instant = clock.instant
        clock.tick(AGE_EXPIRED_SECONDS)
        require_expired_load(
            load_object_call(helper, token, max_age=MAX_AGE_SECONDS),
            token=token,
            expected_object=obj,
            instant=instant,
        )
    public_helper = make_timestamped_serializer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as public_clock:
        public_token = dump_object(public_helper, PUBLIC_ID_MAPPING)
        public_instant = public_clock.instant
        public_clock.tick(AGE_EXPIRED_SECONDS)
        require_expired_load(
            load_object_call(
                public_helper, public_token, max_age=MAX_AGE_SECONDS
            ),
            token=public_token,
            expected_object=PUBLIC_ID_MAPPING,
            instant=public_instant,
        )


def test_signer_expiry_carries_original_payload_bytes():
    public = make_timestamped_signer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = sign_value(public, PUBLIC_VALUE)
        instant = clock.instant
        clock.tick(AGE_EXPIRED_SECONDS)
        exc = require_expired_recovery(
            recover_timestamped(public, token, max_age=MAX_AGE_SECONDS),
            payload=PUBLIC_VALUE,
            instant=instant,
        )
        carried = payload_carried_on_failure(exc, expected_bytes(PUBLIC_VALUE))
        assert carried == b"value"
        assert instant in datetimes_on_failure(exc)

    secret = runtime_secret()
    text = runtime_text()
    runtime = make_timestamped_signer(secret)
    with frozen_clock(OTHER_SIGNING_INSTANT) as clock:
        token = sign_value(runtime, text)
        instant = clock.instant
        clock.tick(AGE_EXPIRED_SECONDS)
        exc = require_expired_recovery(
            recover_timestamped(runtime, token, max_age=MAX_AGE_SECONDS),
            payload=text,
            instant=instant,
        )
        expected = expected_bytes(text)
        carried_rt = payload_carried_on_failure(exc, expected)
        assert carried_rt == expected
        assert instant in datetimes_on_failure(exc)
        assert carried_rt != b"value"


# ---------------------------------------------------------------------------
# E. Future signing time with max_age is expired (L166, L180)
# ---------------------------------------------------------------------------


def test_future_signing_time_with_max_age_is_expired():
    signer = make_timestamped_signer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = sign_value(signer, PUBLIC_VALUE)
        instant = clock.instant
        clock.tick(-1 * (PUBLIC_SIGNING_INSTANT - FUTURE_CHECK_INSTANT).total_seconds())
        assert clock.instant < instant
        require_expired_recovery(
            recover_timestamped(signer, token, max_age=MAX_AGE_SECONDS),
            payload=PUBLIC_VALUE,
            instant=instant,
        )


def test_future_signing_time_without_max_age_still_recovers():
    signer = make_timestamped_signer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = sign_value(signer, PUBLIC_VALUE)
        clock.tick(-1 * (PUBLIC_SIGNING_INSTANT - FUTURE_CHECK_INSTANT).total_seconds())
        recovered = require_recovered_bytes(signer, token, PUBLIC_VALUE)
        assert recovered == b"value"


def test_serializer_future_signing_time_with_max_age_is_expired():
    helper = make_timestamped_serializer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper, PUBLIC_ID_MAPPING)
        instant = clock.instant
        clock.tick(-1 * (PUBLIC_SIGNING_INSTANT - FUTURE_CHECK_INSTANT).total_seconds())
        require_expired_load(
            load_object_call(helper, token, max_age=MAX_AGE_SECONDS),
            token=token,
            expected_object=PUBLIC_ID_MAPPING,
            instant=instant,
        )
        loaded = load_object(helper, token)
        assert loaded == {"id": 42}


def test_runtime_future_signing_time_expired():
    secret = runtime_secret()
    text = runtime_text()
    signer = make_timestamped_signer(secret)
    with frozen_clock(OTHER_SIGNING_INSTANT) as clock:
        token = sign_value(signer, text)
        instant = clock.instant
        clock.tick(-120)
        require_expired_recovery(
            recover_timestamped(signer, token, max_age=MAX_AGE_SECONDS),
            payload=text,
            instant=instant,
        )
        recovered = require_recovered_bytes(signer, token, text)
        assert recovered == expected_bytes(text)


# ---------------------------------------------------------------------------
# F. Non-timestamped token is a missing timestamp (L172, L180–L181)
# ---------------------------------------------------------------------------


def test_non_timestamped_token_is_missing_timestamp():
    signer = make_timestamped_signer("secret-key")
    legal = sign_value(signer, PUBLIC_VALUE)
    recovered = require_recovered_bytes(signer, legal, PUBLIC_VALUE)
    assert recovered == b"value"
    token = arrange_missing_timestamp_token(PUBLIC_VALUE, secret="secret-key")
    exc = require_recovery_failure(recover_timestamped(signer, token))
    require_signing_time_absent(exc)
    assert not datetimes_on_failure(exc)


def test_missing_timestamp_signing_time_absent():
    signer = make_timestamped_signer("secret-key")
    token = arrange_missing_timestamp_token(PUBLIC_VALUE, secret="secret-key")
    exc = require_recovery_failure(recover_timestamped(signer, token))
    require_signing_time_absent(exc)
    assert not datetimes_on_failure(exc)


def test_missing_timestamp_distinguishable_from_expiry_and_time_signature():
    signer = make_timestamped_signer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        legal = sign_value(signer, PUBLIC_VALUE)
        instant = clock.instant
        clock.tick(AGE_EXPIRED_SECONDS)
        expired_exc = require_expired_recovery(
            recover_timestamped(signer, legal, max_age=MAX_AGE_SECONDS),
            payload=PUBLIC_VALUE,
            instant=instant,
        )
        require_recovered_bytes(signer, legal, PUBLIC_VALUE)

    missing = arrange_missing_timestamp_token(PUBLIC_VALUE, secret="secret-key")
    missing_exc = require_recovery_failure(recover_timestamped(signer, missing))
    require_signing_time_absent(missing_exc)

    changed = replace_in_timestamped_payload(
        sign_value(signer, PUBLIC_CHANGED_VALUE),
        PUBLIC_CHANGE_OLD,
        PUBLIC_CHANGE_NEW,
    )
    changed_exc = require_recovery_failure(recover_timestamped(signer, changed))
    require_signing_time_on_failure(changed_exc)

    assert datetimes_on_failure(expired_exc)
    assert not datetimes_on_failure(missing_exc)
    assert datetimes_on_failure(changed_exc)


def test_runtime_non_timestamped_token_refused():
    secret = runtime_secret()
    text = runtime_text()
    signer = make_timestamped_signer(secret)
    token = arrange_missing_timestamp_token(text, secret=secret)
    exc = require_recovery_failure(recover_timestamped(signer, token))
    require_signing_time_absent(exc)
    assert not datetimes_on_failure(exc)


def test_non_timestamped_token_with_different_secret_is_signature_mismatch():
    """L170: a non-timestamped token that does not share the secret is a
    signature mismatch, not a missing timestamp.
    """
    signer = make_timestamped_signer("secret-key")
    legal = sign_value(signer, PUBLIC_VALUE)
    recovered = require_recovered_bytes(signer, legal, PUBLIC_VALUE)
    assert recovered == b"value"

    missing_token = arrange_missing_timestamp_token(
        PUBLIC_VALUE, secret="secret-key"
    )
    missing_exc = require_recovery_failure(
        recover_timestamped(signer, missing_token)
    )
    require_signing_time_absent(missing_exc)

    other = runtime_secret()
    while other == "secret-key":
        other = runtime_secret()
    mismatch_token = arrange_missing_timestamp_token(PUBLIC_VALUE, secret=other)
    mismatch_exc = require_recovery_failure(
        recover_timestamped(signer, mismatch_token)
    )
    assert_signature_mismatch_not_missing_timestamp(
        mismatch_exc,
        missing_exc,
    )
    print(
        "different-secret non-timestamped token is signature mismatch, "
        "not missing timestamp",
        flush=True,
    )


def test_runtime_non_timestamped_token_with_different_secret_is_signature_mismatch():
    """L170: a non-timestamped token that does not share the secret is a
    signature mismatch, not a missing timestamp.
    """
    shared, other = distinct_pair()
    payload = runtime_payload_without_sep()
    signer = make_timestamped_signer(shared)
    legal = sign_value(signer, payload)
    recovered = require_recovered_bytes(signer, legal, payload)
    assert recovered == expected_bytes(payload)

    missing_token = arrange_missing_timestamp_token(payload, secret=shared)
    missing_exc = require_recovery_failure(
        recover_timestamped(signer, missing_token)
    )
    require_signing_time_absent(missing_exc)
    mismatch_token = arrange_missing_timestamp_token(payload, secret=other)
    mismatch_exc = require_recovery_failure(
        recover_timestamped(signer, mismatch_token)
    )
    assert_signature_mismatch_not_missing_timestamp(
        mismatch_exc,
        missing_exc,
    )
    print(
        "runtime different-secret non-timestamped token is signature mismatch, "
        "not missing timestamp",
        flush=True,
    )


# ---------------------------------------------------------------------------
# G. Malformed timestamp (L173–L174, L180–L181)
# ---------------------------------------------------------------------------


def test_dummy_time_suffix_is_malformed_timestamp():
    signer = make_timestamped_signer("secret-key")
    token = arrange_dummy_suffix_token(PUBLIC_VALUE, secret="secret-key")
    malformed_exc = require_recovery_failure(recover_timestamped(signer, token))
    require_signing_time_absent(malformed_exc)

    missing = arrange_missing_timestamp_token(PUBLIC_VALUE, secret="secret-key")
    missing_exc = require_recovery_failure(recover_timestamped(signer, missing))
    require_signing_time_absent(missing_exc)

    require_distinct_failure_kinds(
        malformed_exc,
        missing_exc,
        expect=("malformed-timestamp", "missing-timestamp"),
    )
    print(f"dummy suffix={dummy_undecodable_time_suffix()!r}", flush=True)


def test_malformed_signing_time_absent():
    signer = make_timestamped_signer("secret-key")
    token = arrange_dummy_suffix_token(PUBLIC_VALUE, secret="secret-key")
    exc = require_recovery_failure(recover_timestamped(signer, token))
    require_signing_time_absent(exc)
    assert not datetimes_on_failure(exc)


def test_malformed_distinguishable_from_expiry():
    signer = make_timestamped_signer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        legal = sign_value(signer, PUBLIC_VALUE)
        instant = clock.instant
        clock.tick(AGE_EXPIRED_SECONDS)
        expired_exc = require_expired_recovery(
            recover_timestamped(signer, legal, max_age=MAX_AGE_SECONDS),
            payload=PUBLIC_VALUE,
            instant=instant,
        )
        require_recovered_bytes(signer, legal, PUBLIC_VALUE)

    malformed = arrange_dummy_suffix_token(PUBLIC_VALUE, secret="secret-key")
    malformed_exc = require_recovery_failure(recover_timestamped(signer, malformed))
    require_signing_time_absent(malformed_exc)

    missing = arrange_missing_timestamp_token(PUBLIC_VALUE, secret="secret-key")
    missing_exc = require_recovery_failure(recover_timestamped(signer, missing))
    require_signing_time_absent(missing_exc)

    assert datetimes_on_failure(expired_exc)
    assert not datetimes_on_failure(malformed_exc)
    assert not datetimes_on_failure(missing_exc)
    require_distinct_failure_kinds(
        malformed_exc,
        missing_exc,
        expect=("malformed-timestamp", "missing-timestamp"),
    )


def test_replaced_out_of_range_time_field_is_malformed_not_expiry():
    signer = make_timestamped_signer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        legal = sign_value(signer, PUBLIC_VALUE)
        instant = clock.instant
        require_recovered_bytes(signer, legal, PUBLIC_VALUE)
        require_three_part_layout(legal, expected_bytes(PUBLIC_VALUE))
        # Replace-without-re-sign: splice fields this helper itself emitted,
        # not this checkout's URL-safe-base64 spelling of an epoch.
        replaced = replace_time_field(legal, out_of_range_time_field(signer))
        exc = require_recovery_failure(recover_timestamped(signer, replaced))
        require_signing_time_absent(exc)

        in_range = replace_time_field(legal, in_range_time_field(signer))
        mismatch_with_time = require_recovery_failure(
            recover_timestamped(signer, in_range)
        )
        require_signing_time_on_failure(mismatch_with_time)

        require_recovered_bytes(signer, legal, PUBLIC_VALUE)
        clock.tick(AGE_EXPIRED_SECONDS)
        expired_exc = require_expired_recovery(
            recover_timestamped(signer, legal, max_age=MAX_AGE_SECONDS),
            payload=PUBLIC_VALUE,
            instant=instant,
        )
        assert datetimes_on_failure(expired_exc)
        assert not datetimes_on_failure(exc)
        require_distinct_failure_kinds(
            exc, mismatch_with_time,
            expect=("malformed-timestamp", "time-signature"),
        )
        require_distinct_failure_kinds(
            exc, expired_exc,
            expect=("malformed-timestamp", "expired"),
        )


def test_replaced_out_of_range_time_field_signing_time_absent():
    signer = make_timestamped_signer("secret-key")
    replaced = arrange_replaced_out_of_range_token(signer, PUBLIC_VALUE)
    exc = require_recovery_failure(recover_timestamped(signer, replaced))
    require_signing_time_absent(exc)
    assert not datetimes_on_failure(exc)


def test_runtime_replaced_out_of_range_time_field_is_malformed():
    secret = runtime_secret()
    text = runtime_text()
    signer = make_timestamped_signer(secret)
    with frozen_clock(OTHER_SIGNING_INSTANT) as clock:
        legal = sign_value(signer, text)
        instant = clock.instant
        require_three_part_layout(legal, expected_bytes(text))
        replaced = replace_time_field(legal, out_of_range_time_field(signer))
        exc = require_recovery_failure(recover_timestamped(signer, replaced))
        require_signing_time_absent(exc)

        in_range = replace_time_field(legal, in_range_time_field(signer))
        mismatch_with_time = require_recovery_failure(
            recover_timestamped(signer, in_range)
        )
        require_signing_time_on_failure(mismatch_with_time)

        require_recovered_bytes(signer, legal, text)
        clock.tick(AGE_EXPIRED_SECONDS)
        expired_exc = require_expired_recovery(
            recover_timestamped(signer, legal, max_age=MAX_AGE_SECONDS),
            payload=text,
            instant=instant,
        )
        assert datetimes_on_failure(expired_exc)
        assert not datetimes_on_failure(exc)
        require_distinct_failure_kinds(
            exc, mismatch_with_time,
            expect=("malformed-timestamp", "time-signature"),
        )
        require_distinct_failure_kinds(
            exc, expired_exc,
            expect=("malformed-timestamp", "expired"),
        )


# ---------------------------------------------------------------------------
# H. Changed payload is a time-signature failure; unsafe load (L167, L175)
# ---------------------------------------------------------------------------


def test_changed_payload_my_to_other_is_time_signature_failure():
    signer = make_timestamped_signer("secret-key")
    token = sign_value(signer, PUBLIC_CHANGED_VALUE)
    require_recovered_bytes(signer, token, PUBLIC_CHANGED_VALUE)
    changed = replace_in_timestamped_payload(
        token, PUBLIC_CHANGE_OLD, PUBLIC_CHANGE_NEW
    )
    exc = require_recovery_failure(recover_timestamped(signer, changed))
    recovered_ok = require_recovered_bytes(signer, token, PUBLIC_CHANGED_VALUE)
    assert recovered_ok == b"my string"
    print(f"changed-payload refused via {type(exc).__name__}", flush=True)


def test_changed_payload_exposes_signing_time_when_time_decodes():
    signer = make_timestamped_signer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = sign_value(signer, PUBLIC_CHANGED_VALUE)
        instant = clock.instant
        changed = replace_in_timestamped_payload(
            token, PUBLIC_CHANGE_OLD, PUBLIC_CHANGE_NEW
        )
        exc = require_recovery_failure(recover_timestamped(signer, changed))
        dt = require_signing_time_on_failure(exc, instant)
        assert dt == instant


def test_runtime_changed_payload_is_time_signature_failure():
    secret = runtime_secret()
    text = runtime_text()
    signer = make_timestamped_signer(secret)
    with frozen_clock(OTHER_SIGNING_INSTANT) as clock:
        token = sign_value(signer, text)
        instant = clock.instant
        raw = expected_bytes(text)
        changed = replace_in_timestamped_payload(token, raw[:4], b"ZZZZ")
        exc = require_recovery_failure(recover_timestamped(signer, changed))
        require_signing_time_on_failure(exc, instant)
        require_recovered_bytes(signer, token, text)


def test_changed_payload_on_second_helper_exposes_signing_time():
    secret = runtime_secret()
    first = make_timestamped_signer(secret)
    second = make_timestamped_signer(secret)
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = sign_value(first, PUBLIC_CHANGED_VALUE)
        instant = clock.instant
        changed = replace_in_timestamped_payload(
            token, PUBLIC_CHANGE_OLD, PUBLIC_CHANGE_NEW
        )
        clock.tick(AGE_SUCCESS_SECONDS)
        exc = require_recovery_failure(recover_timestamped(second, changed))
        dt = require_signing_time_on_failure(exc, instant)
        assert dt == instant
        assert clock.instant != instant


def test_unsafe_load_with_max_age_valid_pair():
    helper = make_timestamped_serializer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper, PUBLIC_ID_MAPPING)
        clock.tick(AGE_SUCCESS_SECONDS)
        first, second = require_unsafe_pair(
            unsafe_load_object(helper, token, max_age=MAX_AGE_SECONDS)
        )
        if not first:
            raise AssertionError(
                "unsafe load of a one-second-old token with max_age 10 "
                f"did not report a valid signature; first={first!r}"
            )
        assert second == {"id": 42}


def test_unsafe_load_expired_is_invalid_pair_not_abort():
    helper = make_timestamped_serializer("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper, PUBLIC_ID_MAPPING)
        instant = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        first_ok, second_ok = require_unsafe_pair(
            unsafe_load_object(helper, token, max_age=MAX_AGE_SECONDS)
        )
        if not first_ok:
            raise AssertionError("live baseline: one-second unsafe load must be valid")
        assert second_ok == {"id": 42}
        clock.tick(AGE_EXPIRED_SECONDS - AGE_SUCCESS_SECONDS)
        first, second = require_unsafe_pair(
            unsafe_load_object(helper, token, max_age=MAX_AGE_SECONDS)
        )
        if first:
            raise AssertionError(
                "unsafe load reported an expired token as a valid signature; "
                f"first={first!r} second={second!r}"
            )
        assert second == {"id": 42}
        require_expired_load(
            load_object_call(helper, token, max_age=MAX_AGE_SECONDS),
            token=token,
            expected_object=PUBLIC_ID_MAPPING,
            instant=instant,
        )


def test_unsafe_load_signature_mismatch_with_max_age_returns_pair():
    helper = make_timestamped_serializer("secret-key")
    runtime_helper = make_timestamped_serializer(runtime_secret())
    runtime_obj = runtime_mapping()
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper, PUBLIC_ID_MAPPING)
        chopped = chop_last_character(token)
        clock.tick(AGE_SUCCESS_SECONDS)
        first, second = require_unsafe_pair(
            unsafe_load_object(helper, chopped, max_age=MAX_AGE_SECONDS)
        )
        if first:
            raise AssertionError(
                "unsafe load reported a chopped signature as valid; "
                f"first={first!r} second={second!r}"
            )
        assert second == {"id": 42}

    runtime_token = dump_object(runtime_helper, runtime_obj)
    runtime_chopped = chop_last_character(runtime_token)
    first_r, second_r = require_unsafe_pair(
        unsafe_load_object(runtime_helper, runtime_chopped, max_age=MAX_AGE_SECONDS)
    )
    if first_r:
        raise AssertionError(
            "unsafe load reported a chopped runtime token as valid; "
            f"first={first_r!r} second={second_r!r}"
        )
    assert second_r == runtime_obj


def test_runtime_unsafe_load_expired_not_reported_valid():
    secret = runtime_secret()
    obj = runtime_mapping()
    helper = make_timestamped_serializer(secret)
    with frozen_clock(OTHER_SIGNING_INSTANT) as clock:
        token = dump_object(helper, obj)
        instant = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        first_ok, second_ok = require_unsafe_pair(
            unsafe_load_object(helper, token, max_age=MAX_AGE_SECONDS)
        )
        if not first_ok:
            raise AssertionError("runtime one-second unsafe load must be valid")
        assert second_ok == obj
        clock.tick(AGE_EXPIRED_SECONDS - AGE_SUCCESS_SECONDS)
        first, second = require_unsafe_pair(
            unsafe_load_object(helper, token, max_age=MAX_AGE_SECONDS)
        )
        if first:
            raise AssertionError(
                "unsafe load reported a runtime expired token as valid; "
                f"first={first!r} second={second!r}"
            )
        assert second == obj
        require_expired_load(
            load_object_call(helper, token, max_age=MAX_AGE_SECONDS),
            token=token,
            expected_object=obj,
            instant=instant,
        )


# ---------------------------------------------------------------------------
# I. Expired current config is not rescued by fallback (L168, L180–L181)
# ---------------------------------------------------------------------------


def _sha256_with_sha1_fallback(secret: str) -> Any:
    return make_timestamped_serializer(
        secret,
        signer_kwargs={"digest_method": hashlib.sha256},
        fallback_signers=[{"digest_method": hashlib.sha1}],
    )


def _sha1_only_timestamped(secret: str) -> Any:
    return make_timestamped_serializer(
        secret, signer_kwargs={"digest_method": hashlib.sha1}
    )


def test_sha256_with_sha1_fallback_loads_at_one_second():
    helper = _sha256_with_sha1_fallback("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper, PUBLIC_ID_MAPPING)
        clock.tick(AGE_SUCCESS_SECONDS)
        loaded = load_object(helper, token, max_age=MAX_AGE_SECONDS)
        assert loaded == {"id": 42}


def test_expired_sha256_token_not_loaded_via_sha1_fallback():
    helper = _sha256_with_sha1_fallback("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper, PUBLIC_ID_MAPPING)
        instant = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        assert load_object(helper, token, max_age=MAX_AGE_SECONDS) == {"id": 42}
        clock.tick(AGE_EXPIRED_SECONDS - AGE_SUCCESS_SECONDS)
        result = load_object_call(helper, token, max_age=MAX_AGE_SECONDS)
        require_expired_load(
            result,
            token=token,
            expected_object=PUBLIC_ID_MAPPING,
            instant=instant,
        )


def test_expired_sha256_with_sha1_fallback_is_expired_not_mismatch():
    helper = _sha256_with_sha1_fallback("secret-key")
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper, PUBLIC_ID_MAPPING)
        instant = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        assert load_object(helper, token, max_age=MAX_AGE_SECONDS) == {"id": 42}
        clock.tick(AGE_EXPIRED_SECONDS - AGE_SUCCESS_SECONDS)
        still_valid = load_object(helper, token)
        assert still_valid == {"id": 42}
        print(
            "eleven-second token still loads without a maximum age; "
            "the SHA-256 signature remains valid",
            flush=True,
        )
        expired_exc = require_expired_load(
            load_object_call(helper, token, max_age=MAX_AGE_SECONDS),
            token=token,
            expected_object=PUBLIC_ID_MAPPING,
            instant=instant,
        )
        sha1_only = _sha1_only_timestamped("secret-key")
        mismatch_exc, _pair = require_signature_mismatch(
            sha1_only,
            token,
            expected=PUBLIC_ID_MAPPING,
            max_age=MAX_AGE_SECONDS,
        )
        require_expired_not_signature_mismatch(
            expired_exc,
            mismatch_exc,
        )


def test_runtime_expired_token_not_rescued_by_fallback():
    secret = runtime_secret()
    obj = runtime_mapping()
    helper = _sha256_with_sha1_fallback(secret)
    with frozen_clock(OTHER_SIGNING_INSTANT) as clock:
        token = dump_object(helper, obj)
        instant = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        assert load_object(helper, token, max_age=MAX_AGE_SECONDS) == obj
        clock.tick(AGE_EXPIRED_SECONDS - AGE_SUCCESS_SECONDS)
        require_expired_load(
            load_object_call(helper, token, max_age=MAX_AGE_SECONDS),
            token=token,
            expected_object=obj,
            instant=instant,
        )
