# feature: F04
"""FP-04: URL-safe tokens.

Assertions follow Full_PRD.original.md FP-04 (L185–L209). Failure objects are read
through the exception classes and attributes the Interface Contract
states.
"""

from __future__ import annotations

import hashlib

from _harness import (
    frozen_clock,
    replace_bytes,
    workspace,
)
from F01_helpers import (
    distinct_pair,
    runtime_ascii_digit,
    runtime_ascii_letter,
    runtime_secret,
)
from F02_helpers import (
    JSON_LIST_ONE_THROUGH_FOUR,
    PUBLIC_ID_MAPPING,
    TEXT_SEPARATOR,
    chop_last_character,
    dump_object,
    dump_to_stream,
    load_from_stream,
    load_object,
    load_object_call,
    make_helper,
    require_load_failure,
    require_load_success,
    require_payload_decode_failure,
    require_round_trip_object,
    require_signature_mismatch,
    require_unsafe_pair,
    runtime_mapping,
    tagged_text_codec,
    unsafe_load_object,
)
from F03_helpers import (
    AGE_EXPIRED_SECONDS,
    AGE_SUCCESS_SECONDS,
    MAX_AGE_SECONDS,
    OTHER_SIGNING_INSTANT,
    PUBLIC_SIGNING_INSTANT,
    assert_signature_mismatch_not_missing_timestamp,
    require_integer_list,
    require_returned_signing_time,
    require_signing_time_absent,
    require_signing_time_on_failure,
)
from F04_helpers import (
    COMPRESSION_LENGTH_LIMIT,
    CROSS_LOAD_SECRET,
    PUBLIC_INTEGER_LIST,
    PUBLIC_README_MAPPING,
    PUBLIC_README_NAME,
    PUBLIC_README_SALT,
    PUBLIC_README_SECRET,
    THOUSAND_A,
    arrange_runtime_invalid_compressed_token,
    arrange_runtime_invalid_urlsafe_token,
    arrange_signed_letter_A_token,
    arrange_signed_period_eight_A_token,
    assert_urlsafe_missing_not_malformed_timestamp,
    make_urlsafe_helper,
    make_urlsafe_timestamped_helper,
    repeated_letter,
    require_compressed_payload_section,
    require_id_equals,
    require_readme_mapping,
    require_shorter_than,
    require_uncompressed_payload_section,
    require_urlsafe_text_token,
    runtime_letter_other_than_a,
    uppercase_signature_letters,
)


def _public_urlsafe(secret=PUBLIC_README_SECRET, salt=PUBLIC_README_SALT):
    return make_urlsafe_helper(secret, salt=salt)


def _public_urlsafe_timed(secret=PUBLIC_README_SECRET, salt=PUBLIC_README_SALT):
    return make_urlsafe_timestamped_helper(secret, salt=salt)


def _cross_urlsafe():
    return make_urlsafe_helper(CROSS_LOAD_SECRET)


def _cross_urlsafe_timed():
    return make_urlsafe_timestamped_helper(CROSS_LOAD_SECRET)


def _assert_tamper_is_mismatch(helper, obj, transform):
    token = dump_object(helper, obj)
    require_load_success(load_object_call(helper, token), expected=obj)
    require_urlsafe_text_token(token)
    tampered = transform(token)
    print(
        f"tamper from_len={len(token)} to_len={len(tampered)} "
        f"from_type={type(token).__name__}",
        flush=True,
    )
    assert tampered != token, f"transform was a no-op on {token!r}"
    require_signature_mismatch(helper, tampered)


def _uppercase_token(token: str) -> str:
    changed = token.upper()
    if changed == token:
        raise AssertionError(f"uppercasing was a no-op on {token!r}")
    return changed


def _append_runtime_char(token: str) -> str:
    extra = runtime_ascii_letter()
    return token + extra


def _replace_first_char(token: str) -> str:
    if not token:
        raise AssertionError("cannot replace the first character of an empty token")
    first = token[:1]
    replacement = "X" if first != "X" else "Y"
    return replacement + token[1:]


def _drop_signature_separator(token: str) -> str:
    require_uncompressed_payload_section(token)
    return replace_bytes(token, TEXT_SEPARATOR, "", count=1)


def _require_urlsafe_expired(result, *, instant):
    exc = require_load_failure(result)
    dt = require_signing_time_on_failure(exc, instant)
    assert dt == instant, (
        "expiry failure signing time "
        f"{dt.isoformat()} != frozen signing instant {instant.isoformat()}"
    )
    print("classified as URL-safe expiry (failure + datetime==T)", flush=True)
    return exc


# ---------------------------------------------------------------------------
# A. README mapping round-trip is a text token (L13, L185, L191, L206)
# ---------------------------------------------------------------------------


def test_readme_mapping_round_trip_is_text():
    helper = _public_urlsafe()
    token = dump_object(helper, PUBLIC_README_MAPPING)
    require_urlsafe_text_token(token)
    assert not isinstance(token, (bytes, bytearray))
    loaded = load_object(helper, token)
    require_readme_mapping(loaded)
    print(f"readme token is text len={len(token)}", flush=True)


def test_readme_mapping_recovers_name_and_id():
    helper = _public_urlsafe()
    token = dump_object(helper, PUBLIC_README_MAPPING)
    loaded = load_object(helper, token)
    require_readme_mapping(loaded)
    assert loaded["name"] == PUBLIC_README_NAME
    assert loaded["id"] == 5
    print(f"readme name={loaded['name']!r} id={loaded['id']!r}", flush=True)


def test_runtime_urlsafe_mapping_round_trip_is_text():
    secret = runtime_secret()
    salt = runtime_secret()
    obj = runtime_mapping()
    helper = make_urlsafe_helper(secret, salt=salt)
    token = dump_object(helper, obj)
    require_urlsafe_text_token(token)
    loaded = load_object(helper, token)
    assert loaded == obj
    print(f"runtime mapping token_len={len(token)}", flush=True)


def test_urlsafe_helper_round_trips_a_list():
    helper = _public_urlsafe()
    token = dump_object(helper, PUBLIC_INTEGER_LIST)
    require_urlsafe_text_token(token)
    loaded = load_object(helper, token)
    require_integer_list(loaded, PUBLIC_INTEGER_LIST)
    assert loaded == PUBLIC_INTEGER_LIST
    secret = runtime_secret()
    salt = runtime_secret()
    runtime_list = [int(runtime_ascii_digit()) + 10, int(runtime_ascii_digit()) + 20]
    while runtime_list == PUBLIC_INTEGER_LIST:
        runtime_list.append(int(runtime_ascii_digit()) + 30)
    other = make_urlsafe_helper(secret, salt=salt)
    other_token = dump_object(other, runtime_list)
    require_urlsafe_text_token(other_token)
    other_loaded = load_object(other, other_token)
    require_integer_list(other_loaded, runtime_list)
    assert other_loaded == runtime_list
    print(f"list round-trip public={loaded!r} runtime={runtime_list!r}", flush=True)


def test_second_urlsafe_helper_loads_readme_token():
    helper_a = _public_urlsafe()
    token = dump_object(helper_a, PUBLIC_README_MAPPING)
    require_urlsafe_text_token(token)
    helper_b = _public_urlsafe()
    loaded = load_object(helper_b, token)
    require_readme_mapping(loaded)
    assert loaded["id"] == 5
    assert loaded["name"] == PUBLIC_README_NAME
    print("second helper loaded first helper's README token", flush=True)


# ---------------------------------------------------------------------------
# B. URL-safe alphabet and compact JSON (L59, L192–L193, L206–L207)
# ---------------------------------------------------------------------------


def test_default_list_token_contains_json_with_brackets_and_spaces():
    default = make_helper(PUBLIC_README_SECRET, salt=PUBLIC_README_SALT)
    token = dump_object(default, PUBLIC_INTEGER_LIST)
    loaded = load_object(default, token)
    require_integer_list(loaded, PUBLIC_INTEGER_LIST)
    if isinstance(token, str):
        assert JSON_LIST_ONE_THROUGH_FOUR in token, (
            "default token does not contain JSON list text with brackets "
            f"and spaces: {token!r}"
        )
    elif isinstance(token, (bytes, bytearray)):
        needle = JSON_LIST_ONE_THROUGH_FOUR.encode("utf-8")
        assert needle in token, (
            "default token does not contain JSON list text with brackets "
            f"and spaces: {token!r}"
        )
    else:
        raise AssertionError(
            f"default dump is neither text nor bytes: {type(token).__name__}"
        )
    print(f"default list token carries {JSON_LIST_ONE_THROUGH_FOUR!r}", flush=True)


def test_urlsafe_list_token_has_no_brackets_or_spaces_and_loads():
    helper = _public_urlsafe()
    token = dump_object(helper, PUBLIC_INTEGER_LIST)
    require_urlsafe_text_token(token)
    assert "[" not in token and "]" not in token, (
        f"URL-safe list token still contains brackets: {token!r}"
    )
    assert " " not in token, f"URL-safe list token still contains spaces: {token!r}"
    loaded = load_object(helper, token)
    require_integer_list(loaded, PUBLIC_INTEGER_LIST)
    print(f"urlsafe list token_len={len(token)} loaded={loaded!r}", flush=True)


def test_urlsafe_tokens_use_only_urlsafe_alphabet():
    helper = _public_urlsafe()
    objects = (
        PUBLIC_README_MAPPING,
        PUBLIC_ID_MAPPING,
        THOUSAND_A,
        runtime_mapping(),
    )
    for obj in objects:
        token = dump_object(helper, obj)
        require_urlsafe_text_token(token)
        loaded = load_object(helper, token)
        assert loaded == obj
        print(f"alphabet-ok obj_type={type(obj).__name__} len={len(token)}", flush=True)


def test_timestamped_urlsafe_tokens_use_only_urlsafe_alphabet():
    helper = _public_urlsafe_timed()
    objects = (
        PUBLIC_README_MAPPING,
        PUBLIC_INTEGER_LIST,
        PUBLIC_ID_MAPPING,
        THOUSAND_A,
        runtime_mapping(),
    )
    for obj in objects:
        token = dump_object(helper, obj)
        require_urlsafe_text_token(token)
        loaded = load_object(helper, token)
        assert loaded == obj
        print(
            f"timed alphabet-ok obj_type={type(obj).__name__} len={len(token)}",
            flush=True,
        )


def test_urlsafe_compact_dump_still_loads():
    helper = _public_urlsafe()
    list_token = dump_object(helper, PUBLIC_INTEGER_LIST)
    require_urlsafe_text_token(list_token)
    loaded_list = load_object(helper, list_token)
    require_integer_list(loaded_list, PUBLIC_INTEGER_LIST)
    assert loaded_list == PUBLIC_INTEGER_LIST

    obj = runtime_mapping()
    mapped = require_round_trip_object(helper, obj)
    require_urlsafe_text_token(mapped)
    loaded_map = load_object(helper, mapped)
    assert loaded_map == obj
    print("URL-safe compact dump then load recovered list and mapping", flush=True)


# ---------------------------------------------------------------------------
# C. Compress when shorter; both forms load (L11, L194, L206–L207)
# ---------------------------------------------------------------------------


def test_thousand_a_is_compressed_shorter_than_1000():
    helper = _public_urlsafe()
    token = dump_object(helper, THOUSAND_A)
    require_urlsafe_text_token(token)
    require_shorter_than(token, COMPRESSION_LENGTH_LIMIT)
    loaded = load_object(helper, token)
    assert loaded == THOUSAND_A
    print(f"thousand-a token_len={len(token)}", flush=True)


def test_thousand_a_payload_section_begins_with_period():
    helper = _public_urlsafe()
    token = dump_object(helper, THOUSAND_A)
    require_urlsafe_text_token(token)
    require_compressed_payload_section(token)
    assert load_object(helper, token) == THOUSAND_A


def test_id_42_is_uncompressed_payload_not_leading_period():
    helper = _public_urlsafe()
    token = dump_object(helper, PUBLIC_ID_MAPPING)
    require_urlsafe_text_token(token)
    require_uncompressed_payload_section(token)
    loaded = load_object(helper, token)
    require_id_equals(loaded, 42)
    assert loaded == PUBLIC_ID_MAPPING


def test_runtime_repeated_letter_is_compressed():
    secret = runtime_secret()
    salt = runtime_secret()
    letter = runtime_letter_other_than_a()
    blob = repeated_letter(letter, 1000)
    assert blob != THOUSAND_A
    helper = make_urlsafe_helper(secret, salt=salt)
    token = dump_object(helper, blob)
    require_urlsafe_text_token(token)
    require_shorter_than(token, COMPRESSION_LENGTH_LIMIT)
    require_compressed_payload_section(token)
    loaded = load_object(helper, token)
    assert loaded == blob
    print(f"runtime repeated {letter!r} token_len={len(token)}", flush=True)


def test_runtime_small_mapping_is_uncompressed():
    secret = runtime_secret()
    salt = runtime_secret()
    obj = runtime_mapping()
    assert obj != PUBLIC_ID_MAPPING
    helper = make_urlsafe_helper(secret, salt=salt)
    token = dump_object(helper, obj)
    require_urlsafe_text_token(token)
    require_uncompressed_payload_section(token)
    assert load_object(helper, token) == obj


def test_compressed_and_uncompressed_both_load():
    helper = _public_urlsafe()
    compressed = dump_object(helper, THOUSAND_A)
    uncompressed = dump_object(helper, PUBLIC_ID_MAPPING)
    require_urlsafe_text_token(compressed)
    require_urlsafe_text_token(uncompressed)
    require_compressed_payload_section(compressed)
    require_uncompressed_payload_section(uncompressed)
    assert load_object(helper, compressed) == THOUSAND_A
    loaded_small = load_object(helper, uncompressed)
    require_id_equals(loaded_small, 42)
    print("both compressed and uncompressed forms load", flush=True)


def test_second_urlsafe_helper_loads_first_helpers_compressed_and_readme_tokens():
    helper_a = _public_urlsafe()
    first = dump_object(helper_a, THOUSAND_A)
    second = dump_object(helper_a, PUBLIC_README_MAPPING)
    require_urlsafe_text_token(first)
    require_urlsafe_text_token(second)
    assert load_object(helper_a, first) == THOUSAND_A
    helper_b = _public_urlsafe()
    assert load_object(helper_b, first) == THOUSAND_A
    require_readme_mapping(load_object(helper_b, second))
    print("second helper loaded both of first helper's tokens", flush=True)


# ---------------------------------------------------------------------------
# D. Timestamped URL-safe: same objects, age 10, signing time, still compressed
# ---------------------------------------------------------------------------


def test_timestamped_urlsafe_round_trips_named_objects_as_text():
    helper = _public_urlsafe_timed()
    runtime_obj = runtime_mapping()
    objects = (
        PUBLIC_README_MAPPING,
        PUBLIC_INTEGER_LIST,
        PUBLIC_ID_MAPPING,
        THOUSAND_A,
        runtime_obj,
    )
    for obj in objects:
        token = dump_object(helper, obj)
        require_urlsafe_text_token(token)
        loaded = load_object(helper, token)
        assert loaded == obj
        print(
            f"timed round-trip obj_type={type(obj).__name__} len={len(token)}",
            flush=True,
        )


def test_timestamped_urlsafe_thousand_a_still_compressed():
    helper = _public_urlsafe_timed()
    token = dump_object(helper, THOUSAND_A)
    require_urlsafe_text_token(token)
    require_shorter_than(token, COMPRESSION_LENGTH_LIMIT)
    require_compressed_payload_section(token)
    assert load_object(helper, token) == THOUSAND_A


def test_timestamped_urlsafe_id_42_uncompressed():
    helper = _public_urlsafe_timed()
    token = dump_object(helper, PUBLIC_ID_MAPPING)
    require_urlsafe_text_token(token)
    require_uncompressed_payload_section(token)
    loaded = load_object(helper, token)
    require_id_equals(loaded, 42)
    assert loaded["id"] == 42


def test_timestamped_urlsafe_max_age_10_succeeds_at_one_second():
    helper = _public_urlsafe_timed()
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper, PUBLIC_ID_MAPPING)
        require_urlsafe_text_token(token)
        clock.tick(AGE_SUCCESS_SECONDS)
        loaded = load_object(helper, token, max_age=MAX_AGE_SECONDS)
        require_id_equals(loaded, 42)
        assert loaded["id"] == 42
        print(f"max-age 10 at 1s loaded={loaded!r}", flush=True)


def test_timestamped_urlsafe_max_age_10_expired_at_eleven():
    helper = _public_urlsafe_timed()
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper, PUBLIC_ID_MAPPING)
        instant = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        young = load_object(helper, token, max_age=MAX_AGE_SECONDS)
        require_id_equals(young, 42)
        assert young["id"] == 42
        clock.tick(AGE_EXPIRED_SECONDS - AGE_SUCCESS_SECONDS)
        expired = load_object_call(helper, token, max_age=MAX_AGE_SECONDS)
        assert expired.exception is not None, (
            "token accepted at eleven seconds under max-age 10: "
            f"{expired.value!r}"
        )
        _require_urlsafe_expired(expired, instant=instant)
        still = load_object(helper, token)
        require_id_equals(still, 42)
        assert still["id"] == 42
        print("eleven seconds expired; same token without max-age still loads", flush=True)


def test_timestamped_urlsafe_eleven_seconds_without_max_age_still_loads():
    helper = _public_urlsafe_timed()
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper, PUBLIC_ID_MAPPING)
        clock.tick(AGE_EXPIRED_SECONDS)
        loaded = load_object(helper, token)
        require_id_equals(loaded, 42)
        assert loaded["id"] == 42


def test_timestamped_urlsafe_thousand_a_max_age_10_succeeds_at_one_second():
    helper = _public_urlsafe_timed()
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper, THOUSAND_A)
        require_compressed_payload_section(token)
        clock.tick(AGE_SUCCESS_SECONDS)
        loaded = load_object(helper, token, max_age=MAX_AGE_SECONDS)
        assert loaded == THOUSAND_A


def test_timestamped_urlsafe_thousand_a_max_age_10_expired_at_eleven():
    helper = _public_urlsafe_timed()
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper, THOUSAND_A)
        instant = clock.instant
        require_compressed_payload_section(token)
        clock.tick(AGE_SUCCESS_SECONDS)
        assert load_object(helper, token, max_age=MAX_AGE_SECONDS) == THOUSAND_A
        clock.tick(AGE_EXPIRED_SECONDS - AGE_SUCCESS_SECONDS)
        _require_urlsafe_expired(
            load_object_call(helper, token, max_age=MAX_AGE_SECONDS),
            instant=instant,
        )
        assert load_object(helper, token) == THOUSAND_A


def test_timestamped_urlsafe_ask_signing_time_after_tick_equals_instant():
    helper = _public_urlsafe_timed()
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper, PUBLIC_ID_MAPPING)
        instant = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        assert clock.instant != instant
        value, dt = require_returned_signing_time(
            load_object_call(helper, token, return_timestamp=True),
            PUBLIC_ID_MAPPING,
            instant,
        )
        require_id_equals(value, 42)
        print(f"asked signing time dt={dt.isoformat()} instant={instant.isoformat()}", flush=True)

    secret = runtime_secret()
    salt = runtime_secret()
    obj = runtime_mapping()
    other = make_urlsafe_timestamped_helper(secret, salt=salt)
    with frozen_clock(OTHER_SIGNING_INSTANT) as clock:
        token = dump_object(other, obj)
        instant = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        require_returned_signing_time(
            load_object_call(other, token, return_timestamp=True),
            obj,
            instant,
        )


def test_timestamped_urlsafe_ask_signing_time_on_compressed():
    helper = _public_urlsafe_timed()
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper, THOUSAND_A)
        instant = clock.instant
        require_compressed_payload_section(token)
        clock.tick(AGE_SUCCESS_SECONDS)
        value, dt = require_returned_signing_time(
            load_object_call(helper, token, return_timestamp=True),
            THOUSAND_A,
            instant,
        )
        assert value == THOUSAND_A
        print(f"compressed asked signing time dt={dt.isoformat()}", flush=True)


def test_timestamped_urlsafe_return_time_with_max_age_succeeds_then_expires():
    helper = _public_urlsafe_timed()
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper, PUBLIC_ID_MAPPING)
        instant = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        value, dt = require_returned_signing_time(
            load_object_call(
                helper, token, max_age=MAX_AGE_SECONDS, return_timestamp=True
            ),
            PUBLIC_ID_MAPPING,
            instant,
        )
        assert value["id"] == 42
        assert dt == instant
        clock.tick(AGE_EXPIRED_SECONDS - AGE_SUCCESS_SECONDS)
        expired = load_object_call(
            helper, token, max_age=MAX_AGE_SECONDS, return_timestamp=True
        )
        assert expired.exception is not None, (
            "joint max-age+return-time load succeeded at eleven seconds: "
            f"{expired.value!r}"
        )
        _require_urlsafe_expired(expired, instant=instant)
        print("joint max-age+return-time succeeded then expired", flush=True)


def test_runtime_timestamped_urlsafe_max_age_10():
    secret = runtime_secret()
    salt = runtime_secret()
    obj = runtime_mapping()
    helper = make_urlsafe_timestamped_helper(secret, salt=salt)
    with frozen_clock(OTHER_SIGNING_INSTANT) as clock:
        token = dump_object(helper, obj)
        instant = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        assert load_object(helper, token, max_age=MAX_AGE_SECONDS) == obj
        clock.tick(AGE_EXPIRED_SECONDS - AGE_SUCCESS_SECONDS)
        _require_urlsafe_expired(
            load_object_call(helper, token, max_age=MAX_AGE_SECONDS),
            instant=instant,
        )
        assert load_object(helper, token) == obj


def test_second_timestamped_urlsafe_helper_reads_signing_time_from_token():
    helper_a = _public_urlsafe_timed()
    helper_b = _public_urlsafe_timed()
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper_a, PUBLIC_ID_MAPPING)
        instant = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        young = load_object(helper_b, token, max_age=MAX_AGE_SECONDS)
        require_id_equals(young, 42)
        assert young["id"] == 42
        value, dt = require_returned_signing_time(
            load_object_call(helper_b, token, return_timestamp=True),
            PUBLIC_ID_MAPPING,
            instant,
        )
        require_id_equals(value, 42)
        assert value["id"] == 42
        assert dt == instant
        print(
            f"second timed helper read dt={dt.isoformat()} from token",
            flush=True,
        )


def test_timestamped_urlsafe_earlier_token_keeps_its_signing_time():
    helper = _public_urlsafe_timed()
    first_obj = PUBLIC_ID_MAPPING
    second_obj = PUBLIC_README_MAPPING
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token_a = dump_object(helper, first_obj)
        instant_a = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        token_b = dump_object(helper, second_obj)
        instant_b = clock.instant
        assert instant_b != instant_a
        clock.tick(AGE_SUCCESS_SECONDS)
        require_returned_signing_time(
            load_object_call(helper, token_a, return_timestamp=True),
            first_obj,
            instant_a,
        )
        require_returned_signing_time(
            load_object_call(helper, token_b, return_timestamp=True),
            second_obj,
            instant_b,
        )
        print(
            f"earlier token kept T1={instant_a.isoformat()} "
            f"later T2={instant_b.isoformat()}",
            flush=True,
        )


def test_second_timestamped_urlsafe_helper_expires_first_helpers_token():
    helper_a = _public_urlsafe_timed()
    helper_b = _public_urlsafe_timed()
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper_a, PUBLIC_ID_MAPPING)
        instant = clock.instant
        clock.tick(AGE_SUCCESS_SECONDS)
        young = load_object(helper_b, token, max_age=MAX_AGE_SECONDS)
        require_id_equals(young, 42)
        assert young["id"] == 42
        clock.tick(AGE_EXPIRED_SECONDS - AGE_SUCCESS_SECONDS)
        expired = load_object_call(helper_b, token, max_age=MAX_AGE_SECONDS)
        assert expired.exception is not None, (
            "second helper accepted first helper's token at eleven seconds "
            f"under max-age 10: {expired.value!r}"
        )
        _require_urlsafe_expired(expired, instant=instant)
        print("second timed helper expired first helper's token", flush=True)


def test_second_timestamped_urlsafe_helper_age_and_signing_time_on_compressed_token():
    helper_a = _public_urlsafe_timed()
    helper_b = _public_urlsafe_timed()
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        token = dump_object(helper_a, THOUSAND_A)
        instant = clock.instant
        require_urlsafe_text_token(token)
        require_shorter_than(token, COMPRESSION_LENGTH_LIMIT)
        require_compressed_payload_section(token)
        clock.tick(AGE_SUCCESS_SECONDS)
        loaded = load_object(helper_b, token, max_age=MAX_AGE_SECONDS)
        assert loaded == THOUSAND_A
        value, dt = require_returned_signing_time(
            load_object_call(helper_b, token, return_timestamp=True),
            THOUSAND_A,
            instant,
        )
        assert value == THOUSAND_A
        assert dt == instant
        clock.tick(AGE_EXPIRED_SECONDS - AGE_SUCCESS_SECONDS)
        expired = load_object_call(helper_b, token, max_age=MAX_AGE_SECONDS)
        assert expired.exception is not None, (
            "second helper accepted first helper's compressed token at "
            f"eleven seconds under max-age 10: {expired.value!r}"
        )
        _require_urlsafe_expired(expired, instant=instant)
        still = load_object(helper_b, token)
        assert still == THOUSAND_A
        print(
            "second timed helper aged and read signing time from compressed token",
            flush=True,
        )


def test_timestamped_urlsafe_earlier_compressed_token_keeps_its_signing_time():
    helper = _public_urlsafe_timed()
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        compressed = dump_object(helper, THOUSAND_A)
        instant_a = clock.instant
        require_compressed_payload_section(compressed)
        clock.tick(AGE_SUCCESS_SECONDS)
        mapping_token = dump_object(helper, PUBLIC_ID_MAPPING)
        instant_b = clock.instant
        assert instant_b != instant_a
        clock.tick(AGE_SUCCESS_SECONDS)
        require_returned_signing_time(
            load_object_call(helper, compressed, return_timestamp=True),
            THOUSAND_A,
            instant_a,
        )
        require_returned_signing_time(
            load_object_call(helper, mapping_token, return_timestamp=True),
            PUBLIC_ID_MAPPING,
            instant_b,
        )
        print(
            f"earlier compressed token kept T1={instant_a.isoformat()} "
            f"later mapping T2={instant_b.isoformat()}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# E. Four tamper transforms are a signature mismatch (L139, L185, L199, L207)
# ---------------------------------------------------------------------------


def test_urlsafe_uppercased_token_is_signature_mismatch():
    helper = _public_urlsafe()
    _assert_tamper_is_mismatch(helper, PUBLIC_README_MAPPING, _uppercase_token)
    _assert_tamper_is_mismatch(helper, PUBLIC_ID_MAPPING, _uppercase_token)
    # Full-token uppercasing also rewrites the URL-safe payload encoding
    # (the alphabet is case-sensitive). Holding the payload section fixed
    # and uppercasing only signature letters isolates L199's signature
    # mismatch from that encoding covariate.
    _assert_tamper_is_mismatch(
        helper, PUBLIC_README_MAPPING, uppercase_signature_letters
    )
    _assert_tamper_is_mismatch(helper, PUBLIC_ID_MAPPING, uppercase_signature_letters)


def test_urlsafe_appended_character_is_signature_mismatch():
    helper = _public_urlsafe()
    _assert_tamper_is_mismatch(helper, PUBLIC_README_MAPPING, _append_runtime_char)
    _assert_tamper_is_mismatch(helper, PUBLIC_ID_MAPPING, _append_runtime_char)


def test_urlsafe_replaced_first_character_is_signature_mismatch():
    helper = _public_urlsafe()
    for obj in (PUBLIC_README_MAPPING, PUBLIC_ID_MAPPING):
        token = dump_object(helper, obj)
        require_urlsafe_text_token(token)
        require_load_success(load_object_call(helper, token), expected=obj)
        _assert_tamper_is_mismatch(helper, obj, _replace_first_char)


def test_urlsafe_separator_removed_is_signature_mismatch():
    helper = _public_urlsafe()
    _assert_tamper_is_mismatch(
        helper, PUBLIC_README_MAPPING, _drop_signature_separator
    )
    _assert_tamper_is_mismatch(helper, PUBLIC_ID_MAPPING, _drop_signature_separator)


def test_runtime_urlsafe_tamper_transforms_are_signature_mismatch():
    secret = runtime_secret()
    salt = runtime_secret()
    helper = make_urlsafe_helper(secret, salt=salt)
    obj = runtime_mapping()
    _assert_tamper_is_mismatch(helper, obj, _uppercase_token)
    _assert_tamper_is_mismatch(helper, obj, _append_runtime_char)
    _assert_tamper_is_mismatch(helper, obj, _replace_first_char)
    _assert_tamper_is_mismatch(helper, obj, _drop_signature_separator)


def test_compressed_urlsafe_uppercased_appended_and_replaced_are_signature_mismatch():
    helper = _public_urlsafe()
    token = dump_object(helper, THOUSAND_A)
    require_load_success(load_object_call(helper, token), expected=THOUSAND_A)
    require_compressed_payload_section(token)
    _assert_tamper_is_mismatch(helper, THOUSAND_A, _uppercase_token)
    _assert_tamper_is_mismatch(helper, THOUSAND_A, _append_runtime_char)
    _assert_tamper_is_mismatch(helper, THOUSAND_A, _replace_first_char)


def test_timestamped_urlsafe_appended_character_is_signature_mismatch():
    helper = _public_urlsafe_timed()
    _assert_tamper_is_mismatch(helper, PUBLIC_ID_MAPPING, _append_runtime_char)
    secret = runtime_secret()
    salt = runtime_secret()
    other = make_urlsafe_timestamped_helper(secret, salt=salt)
    obj = runtime_mapping()
    _assert_tamper_is_mismatch(other, obj, _append_runtime_char)
    print("timestamped URL-safe appended character is signature mismatch", flush=True)


# ---------------------------------------------------------------------------
# F. Invalid URL-safe encoding or fake compression is payload-decode failure
# ---------------------------------------------------------------------------


def test_signed_letter_A_payload_is_payload_decode_failure():
    helper = _public_urlsafe()
    legal = dump_object(helper, PUBLIC_ID_MAPPING)
    require_id_equals(load_object(helper, legal), 42)
    garbage = arrange_signed_letter_A_token(
        PUBLIC_README_SECRET, PUBLIC_README_SALT
    )
    refused = load_object_call(helper, garbage)
    assert refused.exception is not None, (
        "valid signature over letter-A payload loaded as success: "
        f"{refused.value!r}"
    )
    require_payload_decode_failure(helper, garbage)
    print("signed letter-A payload is payload-decode failure", flush=True)


def test_signed_period_plus_eight_A_is_payload_decode_failure():
    helper = _public_urlsafe()
    legal = dump_object(helper, THOUSAND_A)
    assert load_object(helper, legal) == THOUSAND_A
    garbage = arrange_signed_period_eight_A_token(
        PUBLIC_README_SECRET, PUBLIC_README_SALT
    )
    require_compressed_payload_section(garbage)
    refused = load_object_call(helper, garbage)
    assert refused.exception is not None, (
        "valid signature over period-plus-eight-A payload loaded as success: "
        f"{refused.value!r}"
    )
    require_payload_decode_failure(helper, garbage)
    print("signed period-plus-eight-A payload is payload-decode failure", flush=True)


def test_payload_decode_distinguishable_from_signature_mismatch():
    helper = _public_urlsafe()
    legal = dump_object(helper, PUBLIC_ID_MAPPING)
    require_id_equals(load_object(helper, legal), 42)
    chopped = chop_last_character(legal)
    chopped_load = load_object_call(helper, chopped)
    assert chopped_load.exception is not None, (
        f"chopped token loaded as success: {chopped_load.value!r}"
    )
    require_signature_mismatch(helper, chopped)
    invalid = arrange_signed_letter_A_token(
        PUBLIC_README_SECRET, PUBLIC_README_SALT
    )
    invalid_load = load_object_call(helper, invalid)
    assert invalid_load.exception is not None, (
        "valid signature over letter-A payload loaded as success: "
        f"{invalid_load.value!r}"
    )
    require_payload_decode_failure(helper, invalid)
    fake_compressed = arrange_signed_period_eight_A_token(
        PUBLIC_README_SECRET, PUBLIC_README_SALT
    )
    fake_load = load_object_call(helper, fake_compressed)
    assert fake_load.exception is not None, (
        "valid signature over period-plus-eight-A payload loaded as success: "
        f"{fake_load.value!r}"
    )
    require_payload_decode_failure(helper, fake_compressed)
    print("payload-decode and chopped-signature outcomes differ", flush=True)


def test_chopped_compressed_token_is_signature_mismatch():
    helper = _public_urlsafe()
    token = dump_object(helper, THOUSAND_A)
    require_load_success(load_object_call(helper, token), expected=THOUSAND_A)
    require_compressed_payload_section(token)
    chopped = chop_last_character(token)
    chopped_load = load_object_call(helper, chopped)
    assert chopped_load.exception is not None, (
        f"chopped compressed token loaded as success: {chopped_load.value!r}"
    )
    require_signature_mismatch(helper, chopped)
    print("chopped compressed token is a signature mismatch", flush=True)


def test_runtime_invalid_urlsafe_and_invalid_compressed():
    secret = runtime_secret()
    salt = runtime_secret()
    helper = make_urlsafe_helper(secret, salt=salt)
    obj = runtime_mapping()
    legal = dump_object(helper, obj)
    require_load_success(load_object_call(helper, legal), expected=obj)
    invalid = arrange_runtime_invalid_urlsafe_token(secret, salt)
    invalid_load = load_object_call(helper, invalid)
    assert invalid_load.exception is not None, (
        "valid signature over runtime invalid URL-safe encoding loaded as "
        f"success: {invalid_load.value!r}"
    )
    require_payload_decode_failure(helper, invalid)
    fake = arrange_runtime_invalid_compressed_token(secret, salt)
    fake_load = load_object_call(helper, fake)
    assert fake_load.exception is not None, (
        "valid signature over runtime fake compressed data loaded as success: "
        f"{fake_load.value!r}"
    )
    require_payload_decode_failure(helper, fake)


# ---------------------------------------------------------------------------
# G. No time field: same-secret uncompressed is missing; compressed is
# malformed; different secret is signature mismatch (L170, L201, L206)
# ---------------------------------------------------------------------------


def test_uncompressed_urlsafe_token_is_missing_timestamp():
    plain = _cross_urlsafe()
    timed = _cross_urlsafe_timed()
    token = dump_object(plain, PUBLIC_ID_MAPPING)
    require_urlsafe_text_token(token)
    require_uncompressed_payload_section(token)
    require_id_equals(load_object(plain, token), 42)
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        legal = dump_object(timed, PUBLIC_ID_MAPPING)
        instant = clock.instant
        clock.tick(AGE_EXPIRED_SECONDS)
        expired = _require_urlsafe_expired(
            load_object_call(timed, legal, max_age=MAX_AGE_SECONDS),
            instant=instant,
        )
        require_id_equals(load_object(timed, legal), 42)
    refused = load_object_call(timed, token)
    exc = require_load_failure(refused)
    require_signing_time_absent(exc)
    assert expired is not None
    print("uncompressed cross-load refused; not expiry", flush=True)


def test_missing_timestamp_signing_time_absent():
    plain = _cross_urlsafe()
    timed = _cross_urlsafe_timed()
    token = dump_object(plain, PUBLIC_ID_MAPPING)
    require_uncompressed_payload_section(token)
    refused = load_object_call(timed, token)
    assert refused.exception is not None, (
        "uncompressed non-timestamped token loaded on the timestamped "
        f"helper as success: {refused.value!r}"
    )
    exc = require_load_failure(refused)
    require_signing_time_absent(exc)


def test_compressed_thousand_a_on_timestamped_is_malformed_not_expiry():
    plain = _cross_urlsafe()
    timed = _cross_urlsafe_timed()
    token = dump_object(plain, THOUSAND_A)
    require_urlsafe_text_token(token)
    require_compressed_payload_section(token)
    assert load_object(plain, token) == THOUSAND_A
    with frozen_clock(PUBLIC_SIGNING_INSTANT) as clock:
        legal = dump_object(timed, THOUSAND_A)
        instant = clock.instant
        clock.tick(AGE_EXPIRED_SECONDS)
        expired = _require_urlsafe_expired(
            load_object_call(timed, legal, max_age=MAX_AGE_SECONDS),
            instant=instant,
        )
        assert load_object(timed, legal) == THOUSAND_A
    refused = load_object_call(timed, token)
    exc = require_load_failure(refused)
    require_signing_time_absent(exc)
    assert expired is not None
    print("compressed thousand-a cross-load refused; not expiry", flush=True)


def test_compressed_cross_load_signing_time_absent():
    plain = _cross_urlsafe()
    timed = _cross_urlsafe_timed()
    token = dump_object(plain, THOUSAND_A)
    require_compressed_payload_section(token)
    refused = load_object_call(timed, token)
    assert refused.exception is not None, (
        "compressed non-timestamped token loaded on the timestamped "
        f"helper as success: {refused.value!r}"
    )
    exc = require_load_failure(refused)
    require_signing_time_absent(exc)


def test_runtime_uncompressed_cross_load_refused():
    secret = runtime_secret()
    salt = runtime_secret()
    obj = runtime_mapping()
    plain = make_urlsafe_helper(secret, salt=salt)
    timed = make_urlsafe_timestamped_helper(secret, salt=salt)
    token = dump_object(plain, obj)
    require_uncompressed_payload_section(token)
    assert load_object(plain, token) == obj
    exc = require_load_failure(load_object_call(timed, token))
    require_signing_time_absent(exc)


def test_runtime_compressed_cross_load_refused():
    secret = runtime_secret()
    salt = runtime_secret()
    letter = runtime_letter_other_than_a()
    blob = repeated_letter(letter, 1000)
    plain = make_urlsafe_helper(secret, salt=salt)
    timed = make_urlsafe_timestamped_helper(secret, salt=salt)
    token = dump_object(plain, blob)
    require_compressed_payload_section(token)
    assert load_object(plain, token) == blob
    exc = require_load_failure(load_object_call(timed, token))
    require_signing_time_absent(exc)


def test_uncompressed_mapping_different_secret_is_signature_mismatch_not_missing():
    timed = _cross_urlsafe_timed()
    legal = dump_object(timed, PUBLIC_ID_MAPPING)
    require_id_equals(load_object(timed, legal), 42)

    same_plain = _cross_urlsafe()
    missing_token = dump_object(same_plain, PUBLIC_ID_MAPPING)
    require_urlsafe_text_token(missing_token)
    require_uncompressed_payload_section(missing_token)
    require_id_equals(load_object(same_plain, missing_token), 42)
    missing_exc = require_load_failure(load_object_call(timed, missing_token))
    require_signing_time_absent(missing_exc)

    other = runtime_secret()
    while other == CROSS_LOAD_SECRET:
        other = runtime_secret()
    other_plain = make_urlsafe_helper(other)
    mismatch_token = dump_object(other_plain, PUBLIC_ID_MAPPING)
    require_urlsafe_text_token(mismatch_token)
    require_uncompressed_payload_section(mismatch_token)
    require_id_equals(load_object(other_plain, mismatch_token), 42)
    mismatch_load = load_object_call(timed, mismatch_token)
    assert mismatch_load.exception is not None, (
        "different-secret uncompressed mapping loaded on the timestamped "
        f"helper as success: {mismatch_load.value!r}"
    )
    mismatch_exc, _ = require_signature_mismatch(timed, mismatch_token)
    assert_signature_mismatch_not_missing_timestamp(
        mismatch_exc,
        missing_exc,
    )
    print(
        "different-secret uncompressed mapping is signature mismatch, "
        "not missing timestamp",
        flush=True,
    )


def test_runtime_uncompressed_different_secret_is_signature_mismatch_not_missing():
    shared, other = distinct_pair()
    salt = runtime_secret()
    obj = runtime_mapping()
    timed = make_urlsafe_timestamped_helper(shared, salt=salt)
    legal = dump_object(timed, obj)
    assert load_object(timed, legal) == obj

    same_plain = make_urlsafe_helper(shared, salt=salt)
    missing_token = dump_object(same_plain, obj)
    require_uncompressed_payload_section(missing_token)
    assert load_object(same_plain, missing_token) == obj
    missing_exc = require_load_failure(load_object_call(timed, missing_token))
    require_signing_time_absent(missing_exc)

    other_plain = make_urlsafe_helper(other, salt=salt)
    mismatch_token = dump_object(other_plain, obj)
    require_uncompressed_payload_section(mismatch_token)
    assert load_object(other_plain, mismatch_token) == obj
    mismatch_load = load_object_call(timed, mismatch_token)
    assert mismatch_load.exception is not None, (
        "runtime different-secret uncompressed mapping loaded on the "
        f"timestamped helper as success: {mismatch_load.value!r}"
    )
    mismatch_exc, _ = require_signature_mismatch(timed, mismatch_token)
    assert_signature_mismatch_not_missing_timestamp(
        mismatch_exc,
        missing_exc,
    )
    print(
        "runtime different-secret uncompressed mapping is signature mismatch, "
        "not missing timestamp",
        flush=True,
    )


def test_urlsafe_missing_and_malformed_cross_load_are_distinguishable():
    plain = _cross_urlsafe()
    timed = _cross_urlsafe_timed()

    missing_token = dump_object(plain, PUBLIC_ID_MAPPING)
    require_urlsafe_text_token(missing_token)
    require_uncompressed_payload_section(missing_token)
    require_id_equals(load_object(plain, missing_token), 42)
    missing_exc = require_load_failure(load_object_call(timed, missing_token))
    require_signing_time_absent(missing_exc)

    malformed_token = dump_object(plain, THOUSAND_A)
    require_urlsafe_text_token(malformed_token)
    require_compressed_payload_section(malformed_token)
    assert load_object(plain, malformed_token) == THOUSAND_A
    malformed_exc = require_load_failure(load_object_call(timed, malformed_token))
    require_signing_time_absent(malformed_exc)

    assert_urlsafe_missing_not_malformed_timestamp(
        missing_exc,
        malformed_exc,
    )
    print(
        "same-secret uncompressed missing is distinguishable from "
        "compressed thousand-a malformed",
        flush=True,
    )


def test_runtime_urlsafe_missing_and_malformed_cross_load_are_distinguishable():
    secret = runtime_secret()
    salt = runtime_secret()
    obj = runtime_mapping()
    letter = runtime_letter_other_than_a()
    blob = repeated_letter(letter, 1000)
    plain = make_urlsafe_helper(secret, salt=salt)
    timed = make_urlsafe_timestamped_helper(secret, salt=salt)

    missing_token = dump_object(plain, obj)
    require_uncompressed_payload_section(missing_token)
    assert load_object(plain, missing_token) == obj
    missing_exc = require_load_failure(load_object_call(timed, missing_token))
    require_signing_time_absent(missing_exc)

    malformed_token = dump_object(plain, blob)
    require_compressed_payload_section(malformed_token)
    assert load_object(plain, malformed_token) == blob
    malformed_exc = require_load_failure(load_object_call(timed, malformed_token))
    require_signing_time_absent(malformed_exc)

    assert_urlsafe_missing_not_malformed_timestamp(
        missing_exc,
        malformed_exc,
    )
    print(
        "runtime same-secret uncompressed missing is distinguishable from "
        "runtime compressed malformed",
        flush=True,
    )


# ---------------------------------------------------------------------------
# H. Product-emitted tokens never contain plus or slash (L202, L207)
# ---------------------------------------------------------------------------


def test_product_emitted_urlsafe_tokens_never_contain_plus_or_slash():
    helper = _public_urlsafe()
    objects = (
        PUBLIC_README_MAPPING,
        PUBLIC_INTEGER_LIST,
        PUBLIC_ID_MAPPING,
        THOUSAND_A,
        runtime_mapping(),
    )
    for obj in objects:
        token = dump_object(helper, obj)
        require_urlsafe_text_token(token)
        loaded = load_object(helper, token)
        assert loaded == obj
        assert "+" not in token, f"product-emitted token contains plus: {token!r}"
        assert "/" not in token, f"product-emitted token contains slash: {token!r}"
        print(f"no plus/slash obj_type={type(obj).__name__}", flush=True)


def test_timestamped_product_emitted_tokens_never_contain_plus_or_slash():
    helper = _public_urlsafe_timed()
    objects = (
        PUBLIC_README_MAPPING,
        PUBLIC_INTEGER_LIST,
        PUBLIC_ID_MAPPING,
        THOUSAND_A,
        runtime_mapping(),
    )
    for obj in objects:
        token = dump_object(helper, obj)
        require_urlsafe_text_token(token)
        loaded = load_object(helper, token)
        assert loaded == obj
        assert "+" not in token, f"product-emitted timed token contains plus: {token!r}"
        assert "/" not in token, f"product-emitted timed token contains slash: {token!r}"
        print(f"timed no plus/slash obj_type={type(obj).__name__}", flush=True)


# ---------------------------------------------------------------------------
# I. Inherited FP-02 serializer behaviour on the URL-safe helper (L187)
# ---------------------------------------------------------------------------


def test_urlsafe_per_call_salt_is_isolated():
    helper = make_urlsafe_helper("secret-key")
    baseline = dump_object(helper, PUBLIC_ID_MAPPING)
    require_urlsafe_text_token(baseline)
    require_id_equals(load_object(helper, baseline), 42)

    token = dump_object(helper, PUBLIC_ID_MAPPING, salt="other")
    require_urlsafe_text_token(token)
    refused = load_object_call(helper, token)
    assert refused.exception is not None, (
        "default-salt load of a salt-other URL-safe token succeeded: "
        f"{refused.value!r}"
    )
    require_signature_mismatch(helper, token, expected=PUBLIC_ID_MAPPING)
    loaded = load_object(helper, token, salt="other")
    require_id_equals(loaded, 42)
    assert loaded == PUBLIC_ID_MAPPING

    secret = runtime_secret()
    salt = runtime_secret()
    obj = runtime_mapping()
    runtime_helper = make_urlsafe_helper(secret)
    runtime_token = dump_object(runtime_helper, obj, salt=salt)
    require_urlsafe_text_token(runtime_token)
    require_signature_mismatch(runtime_helper, runtime_token, expected=obj)
    runtime_loaded = load_object(runtime_helper, runtime_token, salt=salt)
    assert runtime_loaded == obj
    print("URL-safe per-call salt is isolated", flush=True)


def test_urlsafe_none_derivation_salt_other_loads_under_default_salt():
    mixing = make_urlsafe_helper("secret-key")
    mixing_token = dump_object(mixing, PUBLIC_ID_MAPPING, salt="other")
    require_signature_mismatch(
        mixing, mixing_token, expected=PUBLIC_ID_MAPPING
    )

    none_helper = make_urlsafe_helper(
        "secret-key", signer_kwargs={"key_derivation": "none"}
    )
    none_token = dump_object(none_helper, PUBLIC_ID_MAPPING, salt="other")
    require_urlsafe_text_token(none_token)
    loaded_with_salt = load_object(none_helper, none_token, salt="other")
    assert loaded_with_salt == PUBLIC_ID_MAPPING
    default_load = load_object_call(none_helper, none_token)
    if default_load.exception is not None:
        raise AssertionError(
            "under the none key-derivation scheme, a URL-safe dump that "
            "passed salt 'other' must still load under the helper's default "
            f"salt; refused with {type(default_load.exception).__name__}: "
            f"{default_load.exception!r}"
        )
    loaded_default = require_load_success(
        default_load, expected=PUBLIC_ID_MAPPING
    )
    assert loaded_default == PUBLIC_ID_MAPPING
    print(
        "none derivation: URL-safe dump with salt other loaded under "
        "the helper's default salt",
        flush=True,
    )

    secret = runtime_secret()
    obj = runtime_mapping()
    runtime_none = make_urlsafe_helper(
        secret, signer_kwargs={"key_derivation": "none"}
    )
    runtime_token = dump_object(runtime_none, obj, salt="other")
    runtime_default = load_object_call(runtime_none, runtime_token)
    if runtime_default.exception is not None:
        raise AssertionError(
            "under the none key-derivation scheme, a runtime URL-safe dump "
            "that passed salt 'other' must still load under the helper's "
            f"default salt; refused with {type(runtime_default.exception).__name__}: "
            f"{runtime_default.exception!r}"
        )
    runtime_loaded = require_load_success(runtime_default, expected=obj)
    assert runtime_loaded == obj


def test_urlsafe_fallback_loads_when_current_cannot_verify():
    sha256 = make_urlsafe_helper(
        "secret-key", signer_kwargs={"digest_method": hashlib.sha256}
    )
    token = dump_object(sha256, PUBLIC_ID_MAPPING)
    require_urlsafe_text_token(token)
    with_fb = make_urlsafe_helper(
        "secret-key",
        signer_kwargs={"digest_method": hashlib.sha1},
        fallback_signers=[{"digest_method": hashlib.sha256}],
    )
    loaded = load_object(with_fb, token)
    require_id_equals(loaded, 42)
    assert loaded == PUBLIC_ID_MAPPING
    sha1_only = make_urlsafe_helper(
        "secret-key", signer_kwargs={"digest_method": hashlib.sha1}
    )
    baseline = dump_object(sha1_only, PUBLIC_ID_MAPPING)
    require_id_equals(load_object(sha1_only, baseline), 42)
    refused = load_object_call(sha1_only, token)
    assert refused.exception is not None, (
        "SHA-1 URL-safe helper without fallback loaded a SHA-256 token as "
        f"{refused.value!r}"
    )
    require_signature_mismatch(sha1_only, token, expected=PUBLIC_ID_MAPPING)
    print("URL-safe SHA-256 token loads on SHA-1 helper only with fallback", flush=True)


def test_urlsafe_unsafe_load_valid_token_is_valid_and_object():
    helper = make_urlsafe_helper("secret-key")
    token = dump_object(helper, PUBLIC_ID_MAPPING)
    require_urlsafe_text_token(token)
    require_id_equals(load_object(helper, token), 42)
    first, second = require_unsafe_pair(unsafe_load_object(helper, token))
    assert first, (
        f"unsafe load of a valid URL-safe token did not report a valid "
        f"signature: first={first!r} second={second!r}"
    )
    require_id_equals(second, 42)
    assert second == PUBLIC_ID_MAPPING

    obj = runtime_mapping()
    runtime_token = dump_object(helper, obj)
    require_urlsafe_text_token(runtime_token)
    assert load_object(helper, runtime_token) == obj
    first_rt, second_rt = require_unsafe_pair(
        unsafe_load_object(helper, runtime_token)
    )
    assert first_rt, (
        "unsafe load of a valid runtime URL-safe token did not report a "
        f"valid signature: first={first_rt!r} second={second_rt!r}"
    )
    assert second_rt == obj
    print(
        "unsafe load of a valid URL-safe token is (signature valid, object)",
        flush=True,
    )


def test_urlsafe_dump_then_load_through_file_stream():
    with workspace() as ws:
        helper = make_urlsafe_helper("secret-key")
        with ws.open_text_write("id42.txt") as fp:
            dump_to_stream(helper, PUBLIC_ID_MAPPING, fp)
        with ws.open_text("id42.txt") as fp:
            loaded = require_load_success(
                load_from_stream(helper, fp), expected=PUBLIC_ID_MAPPING
            )
        require_id_equals(loaded, 42)
        assert loaded == PUBLIC_ID_MAPPING

        obj = runtime_mapping()
        assert obj != PUBLIC_ID_MAPPING
        with ws.open_text_write("runtime.txt") as fp:
            dump_to_stream(helper, obj, fp)
        with ws.open_text("runtime.txt") as fp:
            loaded_rt = require_load_success(
                load_from_stream(helper, fp), expected=obj
            )
        assert loaded_rt == obj
        print("URL-safe dump then load through a file stream recovered objects", flush=True)


def test_urlsafe_custom_dump_load_object_round_trips():
    secret = runtime_secret()
    salt = runtime_secret()
    codec = tagged_text_codec()
    helper = make_urlsafe_helper(secret, salt=salt, serializer=codec)
    obj = runtime_mapping()
    token = dump_object(helper, obj)
    require_urlsafe_text_token(token)
    loaded = load_object(helper, token)
    assert loaded == obj

    json_helper = make_urlsafe_helper(secret, salt=salt)
    json_token = dump_object(json_helper, obj)
    require_urlsafe_text_token(json_token)
    assert load_object(json_helper, json_token) == obj
    refused = load_object_call(json_helper, token)
    assert refused.exception is not None, (
        "JSON URL-safe helper loaded a non-JSON dump/load token as a "
        f"successful object: {refused.value!r}"
    )
    require_payload_decode_failure(json_helper, token)
    print(
        "URL-safe helper with attached dump/load object round-trips; "
        "JSON helper cannot load that token",
        flush=True,
    )
