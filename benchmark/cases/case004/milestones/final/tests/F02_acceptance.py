# feature: F02
"""FP-02: serialize and sign structured objects.

Assertions follow Full_PRD.original.md FP-02 (L120–L153). Failure objects are read
through the exception classes and attributes the Interface Contract
states.
"""

from __future__ import annotations

import hashlib

from signtoken import Serializer, Signer  # noqa: F401

from _harness import (
    binary_buffer,
    replace_bytes,
    text_buffer,
    workspace,
)
from F02_helpers import (
    JSON_LIST_ONE_THROUGH_FOUR,
    PUBLIC_ID_MAPPING,
    TEXT_SEPARATOR,
    chop_last_character,
    dump_object,
    dump_to_stream,
    json_string_literal,
    load_from_stream,
    load_object,
    load_object_call,
    make_helper,
    marked_failing_codec,
    payload_section,
    require_absent_object,
    require_dumped_bytes,
    require_dumped_text,
    require_illegal_separator_refused,
    require_json_then_sep_then_signature,
    require_load_accepts_text_or_bytes,
    require_load_success,
    require_marker_on_failure,
    require_payload_decode_failure,
    require_recovered_from_failure,
    require_round_trip_object,
    require_signature_mismatch,
    require_token_carries_codec_format,
    require_unsafe_pair,
    runtime_mapping,
    runtime_marker,
    runtime_text_with_period,
    runtime_tuple_key,
    sampled_ascii_digit,
    sampled_ascii_letter,
    sampled_non_ascii_text,
    sampled_secret,
    sampled_secret_pair,
    sampled_text,
    sha256_default_signer_type,
    sha512_default_signer_type,
    shorten_payload,
    signature_section,
    signed_garbage_token,
    tagged_bytes_codec,
    tagged_text_codec,
    token_as_text,
    unsafe_load_from_stream,
    unsafe_load_object,
    join_payload_and_signature,
)


# ---------------------------------------------------------------------------
# S. Package available: dump then load mapping id 42 (L38, L126)
# ---------------------------------------------------------------------------


def test_dump_load_when_package_importable():
    helper = make_helper("secret-key")
    token = dump_object(helper, PUBLIC_ID_MAPPING)
    loaded = load_object(helper, token)
    assert loaded == PUBLIC_ID_MAPPING
    print(f"importable recovered={loaded!r}", flush=True)


def test_serializer_round_trip_is_required_unconditionally():
    # L38 remainder after the substrate paragraph was dropped: construct
    # a helper and dump then load of a mapping whose id is 42 recovers
    # that mapping. Do not require a hard error when the package is absent.
    helper = make_helper("secret-key")
    token = dump_object(helper, PUBLIC_ID_MAPPING)
    loaded = load_object(helper, token)
    print(f"available-package recovered={loaded!r}", flush=True)
    assert loaded == PUBLIC_ID_MAPPING


# ---------------------------------------------------------------------------
# A. Object round-trip; default JSON; list layout; period in JSON (L128, L149)
# ---------------------------------------------------------------------------


def test_round_trip_null_true_text_list_mapping():
    helper = make_helper("secret-key")
    samples = (
        ("json-null", None),
        ("json-true", True),
        ("text", "a text string"),
        ("list-1-2-3", [1, 2, 3]),
        ("mapping-id-42", PUBLIC_ID_MAPPING),
    )
    for label, obj in samples:
        token = require_round_trip_object(helper, obj)
        loaded = load_object(helper, token)
        assert loaded == obj, (
            f"{label} dump then load did not recover an equal object: "
            f"got {loaded!r}"
        )
        print(f"{label} token_len={len(token)} recovered_ok", flush=True)


def test_token_for_list_one_through_four_includes_json_text():
    helper = make_helper("secret-key")
    token = dump_object(helper, [1, 2, 3, 4])
    loaded = load_object(helper, token)
    assert loaded == [1, 2, 3, 4]
    if isinstance(token, str):
        assert JSON_LIST_ONE_THROUGH_FOUR in token
    else:
        assert JSON_LIST_ONE_THROUGH_FOUR.encode("utf-8") in token
    sig = require_json_then_sep_then_signature(token, JSON_LIST_ONE_THROUGH_FOUR)
    payload = payload_section(token)
    if isinstance(payload, bytes):
        assert payload == JSON_LIST_ONE_THROUGH_FOUR.encode("utf-8")
    else:
        assert payload == JSON_LIST_ONE_THROUGH_FOUR
    assert sig
    print(f"list-1-through-4 payload={payload!r} sig_len={len(sig)}", flush=True)


def test_runtime_text_and_mapping_round_trip():
    secret = sampled_secret()
    helper = make_helper(secret)
    text = sampled_text()
    mapping = runtime_mapping()
    assert mapping != PUBLIC_ID_MAPPING
    require_round_trip_object(helper, text)
    require_round_trip_object(helper, mapping)


def test_json_false_round_trip():
    helper = make_helper(sampled_secret())
    token = require_round_trip_object(helper, False)
    loaded = load_object(helper, token)
    assert loaded == False  # noqa: E712 — JSON false, not a truthy stand-in
    assert loaded != True  # noqa: E712 — JSON false is not JSON true


def test_non_ascii_text_round_trip():
    helper = make_helper(sampled_secret())
    text = sampled_non_ascii_text()
    token = require_round_trip_object(helper, text)
    loaded = load_object(helper, token)
    assert loaded == text, (
        f"non-ASCII text dump then load did not recover the original: "
        f"got {loaded!r}"
    )


def test_text_with_period_round_trips_and_keeps_json_then_sep_then_sig():
    helper = make_helper("secret-key")
    listed = dump_object(helper, [1, 2, 3, 4])
    require_json_then_sep_then_signature(listed, JSON_LIST_ONE_THROUGH_FOUR)

    text = runtime_text_with_period()
    assert "." in text
    token = require_round_trip_object(helper, text)
    json_text = json_string_literal(text)
    assert "." in json_text
    sig = require_json_then_sep_then_signature(token, json_text)
    assert sig
    print(f"period-text json_text={json_text!r} token_len={len(token)}", flush=True)


# ---------------------------------------------------------------------------
# B. Text/bytes dump; dual-form load; streams (L129–L130, L145, L149)
# ---------------------------------------------------------------------------


def test_default_dump_returns_text_load_accepts_text_or_bytes():
    helper = make_helper("secret-key")
    token = require_dumped_text(dump_object(helper, PUBLIC_ID_MAPPING))
    print(f"default dump type={type(token).__name__}", flush=True)
    recovered = require_load_accepts_text_or_bytes(
        helper, token, PUBLIC_ID_MAPPING
    )
    assert recovered == PUBLIC_ID_MAPPING

    mapping = runtime_mapping()
    assert mapping != PUBLIC_ID_MAPPING
    runtime_token = require_dumped_text(dump_object(helper, mapping))
    runtime_recovered = require_load_accepts_text_or_bytes(
        helper, runtime_token, mapping
    )
    assert runtime_recovered == mapping


def test_bytes_dump_load_object_returns_bytes():
    secret = sampled_secret()
    salt = sampled_secret()
    codec = tagged_bytes_codec()
    probe = codec.dumps({"probe": 1})
    assert isinstance(probe, bytes)
    helper = make_helper(secret, salt=salt, serializer=codec)
    obj = runtime_mapping()
    token = require_dumped_bytes(dump_object(helper, obj))
    print(f"bytes dump type={type(token).__name__}", flush=True)
    require_token_carries_codec_format(token, codec.prefix)
    recovered = require_load_accepts_text_or_bytes(helper, token, obj)
    assert recovered == obj


def test_stream_dump_load_mapping_id_42():
    helper = make_helper("secret-key")
    buf = text_buffer()
    dump_to_stream(helper, PUBLIC_ID_MAPPING, buf)
    buf.seek(0)
    loaded = require_load_success(load_from_stream(helper, buf), expected=PUBLIC_ID_MAPPING)
    assert loaded == PUBLIC_ID_MAPPING


def test_stream_dump_load_runtime_object():
    helper = make_helper(sampled_secret())
    obj = runtime_mapping()
    assert obj != PUBLIC_ID_MAPPING
    buf = text_buffer()
    dump_to_stream(helper, obj, buf)
    buf.seek(0)
    loaded = require_load_success(load_from_stream(helper, buf), expected=obj)
    assert loaded == obj

    codec = tagged_bytes_codec()
    bhelper = make_helper(sampled_secret(), serializer=codec)
    bbuf = binary_buffer()
    dump_to_stream(bhelper, obj, bbuf)
    bbuf.seek(0)
    bloaded = require_load_success(load_from_stream(bhelper, bbuf), expected=obj)
    assert bloaded == obj


def test_stream_unsafe_load_valid_token():
    helper = make_helper("secret-key")
    for obj in (PUBLIC_ID_MAPPING, runtime_mapping()):
        buf = text_buffer()
        dump_to_stream(helper, obj, buf)
        buf.seek(0)
        first, second = require_unsafe_pair(unsafe_load_from_stream(helper, buf))
        print(f"stream unsafe valid first={first!r} second={second!r}", flush=True)
        assert first, f"stream unsafe load did not report a valid signature: {first!r}"
        assert second == obj


def test_stream_unsafe_load_chopped_signature_is_invalid():
    helper = make_helper("secret-key")
    for obj in (PUBLIC_ID_MAPPING, runtime_mapping()):
        token = dump_object(helper, obj)
        buf_ok = text_buffer(token_as_text(token))
        ok_first, ok_second = require_unsafe_pair(unsafe_load_from_stream(helper, buf_ok))
        assert ok_first
        assert ok_second == obj

        chopped = chop_last_character(token)
        buf = text_buffer(token_as_text(chopped))
        first, second = require_unsafe_pair(unsafe_load_from_stream(helper, buf))
        print(
            f"stream unsafe chopped first={first!r} second={second!r}",
            flush=True,
        )
        assert not first, (
            "stream unsafe load reported a valid signature after the last "
            f"character was chopped: first={first!r}"
        )
        assert second == obj
        if ok_first == first:
            raise AssertionError(
                "valid and chopped stream unsafe reports were not distinguishable"
            )


def test_real_file_stream_round_trip():
    with workspace() as ws:
        helper = make_helper("secret-key")
        with ws.open_text_write("id42.txt") as fp:
            dump_to_stream(helper, PUBLIC_ID_MAPPING, fp)
        with ws.open_text("id42.txt") as fp:
            loaded = require_load_success(
                load_from_stream(helper, fp), expected=PUBLIC_ID_MAPPING
            )
        assert loaded == PUBLIC_ID_MAPPING

        obj = runtime_mapping()
        assert obj != PUBLIC_ID_MAPPING
        with ws.open_text_write("runtime.txt") as fp:
            dump_to_stream(helper, obj, fp)
        with ws.open_text("runtime.txt") as fp:
            loaded_rt = require_load_success(load_from_stream(helper, fp), expected=obj)
        assert loaded_rt == obj

        codec = tagged_bytes_codec()
        bhelper = make_helper(sampled_secret(), serializer=codec)
        with ws.open_binary_write("runtime.bin") as fp:
            dump_to_stream(bhelper, obj, fp)
        with ws.open_binary("runtime.bin") as fp:
            loaded_bin = require_load_success(
                load_from_stream(bhelper, fp), expected=obj
            )
        assert loaded_bin == obj


# ---------------------------------------------------------------------------
# C. Per-call salt; none exception (L22, L124, L131, L149)
# ---------------------------------------------------------------------------


def test_salt_other_refused_by_default_load():
    helper = make_helper("secret-key")
    baseline = dump_object(helper, PUBLIC_ID_MAPPING)
    assert load_object(helper, baseline) == PUBLIC_ID_MAPPING
    token = dump_object(helper, PUBLIC_ID_MAPPING, salt="other")
    refused = load_object_call(helper, token)
    assert refused.exception is not None, (
        "default-salt load of a salt-other token succeeded: "
        f"{refused.value!r}"
    )
    _exc, (first, second) = require_signature_mismatch(
        helper, token, expected=PUBLIC_ID_MAPPING
    )
    assert not first, (
        "default-salt load of a salt-other token must be a signature "
        f"mismatch; unsafe first={first!r} second={second!r}"
    )
    assert second == PUBLIC_ID_MAPPING


def test_salt_other_accepted_when_passed_to_load():
    helper = make_helper("secret-key")
    token = dump_object(helper, PUBLIC_ID_MAPPING, salt="other")
    loaded = load_object(helper, token, salt="other")
    assert loaded == PUBLIC_ID_MAPPING


def test_runtime_salt_isolation():
    secret = sampled_secret()
    salt = sampled_secret()
    helper = make_helper(secret)
    obj = runtime_mapping()
    token = dump_object(helper, obj, salt=salt)
    require_signature_mismatch(helper, token, expected=obj)
    loaded = load_object(helper, token, salt=salt)
    assert loaded == obj


def test_none_derivation_ignores_per_call_salt():
    secret = sampled_secret()
    helper_default = make_helper(secret)
    token_default = dump_object(helper_default, PUBLIC_ID_MAPPING, salt="other")
    require_signature_mismatch(
        helper_default, token_default, expected=PUBLIC_ID_MAPPING
    )

    helper_none = make_helper(secret, signer_kwargs={"key_derivation": "none"})
    token_none = dump_object(helper_none, PUBLIC_ID_MAPPING, salt="other")
    loaded = load_object(helper_none, token_none)
    assert loaded == PUBLIC_ID_MAPPING
    print("none derivation recovered under default-salt load", flush=True)


# ---------------------------------------------------------------------------
# L124. FP-01 separator alphabet on the signer this helper constructs
# ---------------------------------------------------------------------------


def test_period_separator_round_trips_on_this_helper():
    default = make_helper("secret-key")
    require_round_trip_object(default, PUBLIC_ID_MAPPING)
    explicit = make_helper("secret-key", signer_kwargs={"sep": "."})
    token = require_round_trip_object(explicit, PUBLIC_ID_MAPPING)
    loaded = load_object(explicit, token)
    assert loaded == PUBLIC_ID_MAPPING
    print("period separator accepted on this helper", flush=True)


def test_hyphen_separator_refused_on_this_helper():
    refused = require_illegal_separator_refused("-")
    print(
        f"hyphen separator refused via {type(refused).__name__}",
        flush=True,
    )
    assert refused is not None, (
        "hyphen separator must be refused for the signer this helper "
        "constructs; caller must not receive a signed token"
    )


def test_underscore_and_equals_separators_refused_on_this_helper():
    for sep in ("_", "="):
        refused = require_illegal_separator_refused(sep)
        print(
            f"separator {sep!r} refused via {type(refused).__name__}",
            flush=True,
        )
        assert refused is not None, (
            f"separator {sep!r} must be refused for the signer this helper "
            "constructs; caller must not receive a signed token"
        )


def test_runtime_letter_and_digit_separators_refused_on_this_helper():
    letter = sampled_ascii_letter()
    digit = sampled_ascii_digit()
    print(f"runtime letter={letter!r} digit={digit!r}", flush=True)
    letter_refused = require_illegal_separator_refused(letter)
    digit_refused = require_illegal_separator_refused(digit)
    assert letter_refused is not None, (
        f"letter separator {letter!r} must be refused for the signer this "
        "helper constructs; caller must not receive a signed token"
    )
    assert digit_refused is not None, (
        f"digit separator {digit!r} must be refused for the signer this "
        "helper constructs; caller must not receive a signed token"
    )


# ---------------------------------------------------------------------------
# D. Replace dump/load object; skip-non-basic-keys (L132, L149–L150)
# ---------------------------------------------------------------------------


def test_custom_dump_load_object_round_trips():
    secret = sampled_secret()
    salt = sampled_secret()
    codec = tagged_text_codec()
    sample = codec.dumps({"x": 1})
    assert not sample.startswith("{")
    helper = make_helper(secret, salt=salt, serializer=codec)
    obj = runtime_mapping()
    token = require_round_trip_object(helper, obj)
    print(f"custom codec token_prefix={token[:16]!r}", flush=True)
    require_token_carries_codec_format(token, codec.prefix)


def test_json_helper_load_of_non_json_token_is_payload_decode_failure():
    secret = sampled_secret()
    salt = sampled_secret()
    codec = tagged_text_codec()
    custom = make_helper(secret, salt=salt, serializer=codec)
    json_helper = make_helper(secret, salt=salt)
    obj = runtime_mapping()
    require_round_trip_object(json_helper, obj)
    token = dump_object(custom, obj)
    require_round_trip_object(custom, obj)
    refused = load_object_call(json_helper, token)
    assert refused.exception is not None, (
        "JSON helper loaded a non-JSON token as a successful object: "
        f"{refused.value!r}"
    )
    require_payload_decode_failure(json_helper, token)
    unsafe = unsafe_load_object(json_helper, token)
    assert unsafe.exception is not None, (
        "unsafe load converted a non-JSON payload-decode failure into a pair: "
        f"{unsafe.value!r}"
    )


def test_skip_non_basic_keys_empty_tuple_loads_as_empty_mapping():
    helper = make_helper("secret-key", serializer_kwargs={"skipkeys": True})
    token = dump_object(helper, {(): 1})
    loaded = load_object(helper, token)
    print(f"skipkeys empty-tuple loaded={loaded!r}", flush=True)
    assert loaded == {}


def test_skip_non_basic_keys_runtime_tuple_and_mixed_mapping():
    helper = make_helper(
        sampled_secret(), serializer_kwargs={"skipkeys": True}
    )
    require_round_trip_object(helper, PUBLIC_ID_MAPPING)

    runtime_key = runtime_tuple_key()
    token_only = dump_object(helper, {runtime_key: 1})
    loaded_only = load_object(helper, token_only)
    assert loaded_only == {}

    mixed = {runtime_key: 1, "id": 42}
    token_mixed = dump_object(helper, mixed)
    loaded_mixed = load_object(helper, token_mixed)
    print(f"skipkeys mixed loaded={loaded_mixed!r}", flush=True)
    assert loaded_mixed == PUBLIC_ID_MAPPING


def test_without_skip_non_basic_keys_still_recovers_id_mapping():
    # L132 requires skip-non-basic-keys to load {(): 1} as {}. It does not
    # specify dump of that mapping without the option (refuse, skip, or
    # serialize are all unwritten). This arm is the live baseline: a
    # helper that does not skip non-basic keys still dump-then-load
    # recovers {id: 42}, so skip-non-basic-keys is not "always dump {}".
    helper = make_helper("secret-key")
    token = require_round_trip_object(helper, PUBLIC_ID_MAPPING)
    loaded = load_object(helper, token)
    print(f"no-skipkeys mapping recovered={loaded!r}", flush=True)
    assert loaded == PUBLIC_ID_MAPPING
    assert loaded != {}

    skip_helper = make_helper("secret-key", serializer_kwargs={"skipkeys": True})
    skip_loaded = load_object(
        skip_helper, dump_object(skip_helper, PUBLIC_ID_MAPPING)
    )
    assert skip_loaded == PUBLIC_ID_MAPPING
    assert skip_loaded != {}


# ---------------------------------------------------------------------------
# E. Replace signer type or signing options (L30, L124, L133, L149)
# ---------------------------------------------------------------------------


def test_hmac_derivation_round_trips():
    helper = make_helper(
        "secret-key", signer_kwargs={"key_derivation": "hmac"}
    )
    token = require_round_trip_object(helper, PUBLIC_ID_MAPPING)
    assert load_object(helper, token) == PUBLIC_ID_MAPPING
    runtime_obj = runtime_mapping()
    token_rt = require_round_trip_object(helper, runtime_obj)
    assert load_object(helper, token_rt) == runtime_obj


def test_default_and_hmac_tokens_differ_and_do_not_interchange():
    secret = sampled_secret()
    obj = PUBLIC_ID_MAPPING
    default = make_helper(secret)
    hmac_helper = make_helper(secret, signer_kwargs={"key_derivation": "hmac"})
    token_default = dump_object(default, obj)
    token_hmac = dump_object(hmac_helper, obj)
    print(
        f"default_token_len={len(token_default)} hmac_token_len={len(token_hmac)}",
        flush=True,
    )
    assert token_default != token_hmac
    require_round_trip_object(default, obj)
    require_round_trip_object(hmac_helper, obj)
    require_signature_mismatch(hmac_helper, token_default, expected=obj)
    require_signature_mismatch(default, token_hmac, expected=obj)

    runtime_obj = runtime_mapping()
    t_default = dump_object(default, runtime_obj)
    t_hmac = dump_object(hmac_helper, runtime_obj)
    assert t_default != t_hmac
    require_signature_mismatch(hmac_helper, t_default, expected=runtime_obj)
    require_signature_mismatch(default, t_hmac, expected=runtime_obj)


def test_replaced_signer_type_sha512_round_trips_and_differs_from_hmac_options():
    secret = sampled_secret()
    Sha512Signer = sha512_default_signer_type()
    typed = make_helper(secret, signer=Sha512Signer)

    token_listed = require_round_trip_object(typed, [42])
    assert load_object(typed, token_listed) == [42]
    runtime_obj = runtime_mapping()
    token_typed = require_round_trip_object(typed, runtime_obj)
    print(f"typed_len={len(token_typed)} listed_len={len(token_listed)}", flush=True)
    assert load_object(typed, token_typed) == runtime_obj


# ---------------------------------------------------------------------------
# F. Fallback forms; listed digest only (L31, L134, L144, L149–L150)
# ---------------------------------------------------------------------------


def test_sha256_token_loads_on_sha1_helper_with_digest_fallback():
    secret = "secret-key"
    obj = PUBLIC_ID_MAPPING
    sha256 = make_helper(secret, signer_kwargs={"digest_method": hashlib.sha256})
    token = dump_object(sha256, obj)
    with_fb = make_helper(
        secret,
        signer_kwargs={"digest_method": hashlib.sha1},
        fallback_signers=[{"digest_method": hashlib.sha256}],
    )
    loaded = load_object(with_fb, token)
    assert loaded == obj


def test_sha1_helper_without_fallback_refuses_sha256_token():
    secret = "secret-key"
    obj = PUBLIC_ID_MAPPING
    sha256 = make_helper(secret, signer_kwargs={"digest_method": hashlib.sha256})
    token = dump_object(sha256, obj)
    sha1_only = make_helper(secret, signer_kwargs={"digest_method": hashlib.sha1})
    baseline = require_round_trip_object(sha1_only, obj)
    assert load_object(sha1_only, baseline) == obj
    refused = load_object_call(sha1_only, token)
    assert refused.exception is not None, (
        "SHA-1 helper without fallback loaded a SHA-256 token as "
        f"{refused.value!r}"
    )
    _exc, (first, second) = require_signature_mismatch(
        sha1_only, token, expected=obj
    )
    assert not first, (
        "SHA-1 helper without fallback must refuse a SHA-256 token as a "
        f"signature mismatch; unsafe first={first!r} second={second!r}"
    )
    assert second == obj


def test_fallback_signer_type_loads_sha256_token():
    # L132: an alternative signer type is constructed with the helper's
    # current signing options (default digest SHA-1). Listing that type
    # as fallback must not be treated as a class-default-digest rescue of
    # a SHA-256 token. The remaining promise is dump then load of a
    # mapping whose id is 42 on a helper that lists the type.
    secret = sampled_secret()
    obj = PUBLIC_ID_MAPPING
    Sha256Signer = sha256_default_signer_type()
    type_fb = make_helper(secret, fallback_signers=[Sha256Signer])
    loaded = load_object(type_fb, dump_object(type_fb, obj))
    print(f"type-fallback current round-trip recovered={loaded!r}", flush=True)
    assert loaded == obj


def test_fallback_type_and_options_pair_loads_sha256_token():
    secret = sampled_secret()
    obj = PUBLIC_ID_MAPPING
    sha256 = make_helper(secret, signer_kwargs={"digest_method": hashlib.sha256})
    token = dump_object(sha256, obj)
    pair_fb = make_helper(
        secret,
        fallback_signers=[(Signer, {"digest_method": hashlib.sha256})],
    )
    loaded = load_object(pair_fb, token)
    assert loaded == obj


def test_fallback_mapping_and_type_rescue_sha512_runtime_object():
    secret = sampled_secret()
    obj = runtime_mapping()
    sha512 = make_helper(secret, signer_kwargs={"digest_method": hashlib.sha512})
    token = dump_object(sha512, obj)

    mapping_fb = make_helper(
        secret,
        signer_kwargs={"digest_method": hashlib.sha1},
        fallback_signers=[{"digest_method": hashlib.sha512}],
    )
    assert load_object(mapping_fb, token) == obj

    pair_fb = make_helper(
        secret,
        fallback_signers=[(Signer, {"digest_method": hashlib.sha512})],
    )
    assert load_object(pair_fb, token) == obj


def test_fallback_type_with_current_sha1_options_does_not_override_to_class_default():
    # L134: a type-only fallback is constructed with the helper's current
    # signing options. Pinning those options to SHA-1 must not let a
    # subclass whose class default is SHA-256 rescue a SHA-256 token.
    secret = sampled_secret()
    obj = PUBLIC_ID_MAPPING
    sha256 = make_helper(secret, signer_kwargs={"digest_method": hashlib.sha256})
    token = dump_object(sha256, obj)
    Sha256Signer = sha256_default_signer_type()

    pinned_sha1 = make_helper(
        secret,
        signer_kwargs={"digest_method": hashlib.sha1},
        fallback_signers=[Sha256Signer],
    )
    baseline = require_round_trip_object(pinned_sha1, obj)
    assert load_object(pinned_sha1, baseline) == obj
    refused = load_object_call(pinned_sha1, token)
    assert refused.exception is not None, (
        "type-only SHA-256-default fallback constructed with current "
        f"SHA-1 options loaded a SHA-256 token as {refused.value!r}"
    )
    _exc, (first, second) = require_signature_mismatch(
        pinned_sha1, token, expected=obj
    )
    assert not first, (
        "current SHA-1 signing options must be applied to a type-only "
        f"fallback; unsafe first={first!r} second={second!r}"
    )
    assert second == obj


def test_fallbacks_tried_until_one_verifies():
    secret = sampled_secret()
    obj = PUBLIC_ID_MAPPING
    sha256 = make_helper(secret, signer_kwargs={"digest_method": hashlib.sha256})
    token = dump_object(sha256, obj)

    mismatch_then_hit = make_helper(
        secret,
        signer_kwargs={"digest_method": hashlib.sha1},
        fallback_signers=[
            {"digest_method": hashlib.sha512},
            {"digest_method": hashlib.sha256},
        ],
    )
    assert load_object(mismatch_then_hit, token) == obj

    hit_then_mismatch = make_helper(
        secret,
        signer_kwargs={"digest_method": hashlib.sha1},
        fallback_signers=[
            {"digest_method": hashlib.sha256},
            {"digest_method": hashlib.sha512},
        ],
    )
    assert load_object(hit_then_mismatch, token) == obj


def test_all_signers_including_fallbacks_fail_as_signature_mismatch():
    secret = sampled_secret()
    obj = runtime_mapping()
    sha512 = make_helper(secret, signer_kwargs={"digest_method": hashlib.sha512})
    token = dump_object(sha512, obj)
    sha1_sha256_fb = make_helper(
        secret,
        signer_kwargs={"digest_method": hashlib.sha1},
        fallback_signers=[{"digest_method": hashlib.sha256}],
    )
    baseline = require_round_trip_object(sha1_sha256_fb, obj)
    assert load_object(sha1_sha256_fb, baseline) == obj
    refused = load_object_call(sha1_sha256_fb, token)
    assert refused.exception is not None, (
        "SHA-1 helper with only a SHA-256 fallback loaded a SHA-512 token as "
        f"{refused.value!r}"
    )
    _exc, (first, second) = require_signature_mismatch(
        sha1_sha256_fb, token, expected=obj
    )
    assert not first, (
        "every signer including fallbacks failing must be a signature "
        f"mismatch; unsafe first={first!r} second={second!r}"
    )
    assert second == obj


# ---------------------------------------------------------------------------
# G. Inspected payload after signature mismatch (L136, L149)
# ---------------------------------------------------------------------------


def test_chopped_signature_load_is_mismatch_payload_decodes():
    helper = make_helper("secret-key")
    token = dump_object(helper, PUBLIC_ID_MAPPING)
    require_load_success(load_object_call(helper, token), expected=PUBLIC_ID_MAPPING)
    chopped = chop_last_character(token)
    exc, _pair = require_signature_mismatch(
        helper, chopped, expected=PUBLIC_ID_MAPPING
    )
    recovered = require_recovered_from_failure(
        exc, PUBLIC_ID_MAPPING, token=chopped
    )
    assert recovered == PUBLIC_ID_MAPPING


def test_runtime_chopped_signature_exposes_original_object():
    helper = make_helper(sampled_secret())
    obj = runtime_mapping()
    assert obj != PUBLIC_ID_MAPPING
    token = dump_object(helper, obj)
    require_load_success(load_object_call(helper, token), expected=obj)
    chopped = chop_last_character(token)
    exc, _pair = require_signature_mismatch(helper, chopped, expected=obj)
    recovered = require_recovered_from_failure(exc, obj, token=chopped)
    assert recovered == obj
    assert recovered != PUBLIC_ID_MAPPING


def test_chopped_signature_of_period_containing_text_exposes_object():
    helper = make_helper("secret-key")
    text = runtime_text_with_period()
    token = dump_object(helper, text)
    require_load_success(load_object_call(helper, token), expected=text)
    chopped = chop_last_character(token)
    exc, _pair = require_signature_mismatch(helper, chopped, expected=text)
    recovered = require_recovered_from_failure(exc, text, token=chopped)
    assert recovered == text


# ---------------------------------------------------------------------------
# H. Valid signature over garbage; retain decode error (L33, L142–L143, L150)
# ---------------------------------------------------------------------------


def test_valid_signature_over_garbage_is_payload_decode_failure():
    secret = sampled_secret()
    salt = sampled_secret()
    helper = make_helper(secret, salt=salt)
    token = dump_object(helper, PUBLIC_ID_MAPPING)
    assert load_object(helper, token) == PUBLIC_ID_MAPPING
    payload = payload_section(token)
    shortened = shorten_payload(payload)
    garbage = signed_garbage_token(shortened, secret=secret, salt=salt)
    refused = load_object_call(helper, garbage)
    assert refused.exception is not None, (
        "valid signature over garbage loaded as a successful object: "
        f"{refused.value!r}"
    )
    require_payload_decode_failure(helper, garbage)
    unsafe = unsafe_load_object(helper, garbage)
    assert unsafe.exception is not None, (
        "unsafe load converted a payload-decode failure into a pair: "
        f"{unsafe.value!r}"
    )


def test_payload_decode_failure_retains_original_decode_error():
    """Two marked codecs must leave distinguishable payload-decode failures.

    L142 retains the original decode error so two attached dump/load
    objects that fail with different decode errors stay distinguishable.
    The retained error is read from the stated ``original_error``
    attribute. Dropping the original error fails this test.
    """
    secret = sampled_secret()
    salt = sampled_secret()
    marker_a = runtime_marker()
    marker_b = runtime_marker()
    while marker_b == marker_a:
        marker_b = runtime_marker()
    codec_a = marked_failing_codec(marker_a)
    codec_b = marked_failing_codec(marker_b, prefix="NK|")
    helper_a = make_helper(secret, salt=salt, serializer=codec_a)
    helper_b = make_helper(secret, salt=salt, serializer=codec_b)
    obj = runtime_mapping()
    token_a = require_round_trip_object(helper_a, obj)
    token_b = require_round_trip_object(helper_b, obj)

    garbage_a = signed_garbage_token(
        shorten_payload(payload_section(token_a)), secret=secret, salt=salt
    )
    garbage_b = signed_garbage_token(
        shorten_payload(payload_section(token_b)), secret=secret, salt=salt
    )
    load_a, unsafe_a = require_payload_decode_failure(helper_a, garbage_a)
    load_b, unsafe_b = require_payload_decode_failure(helper_b, garbage_b)
    seen_a = require_marker_on_failure(load_a, marker_a)
    seen_b = require_marker_on_failure(load_b, marker_b)
    require_marker_on_failure(unsafe_a, marker_a)
    require_marker_on_failure(unsafe_b, marker_b)
    assert seen_a != seen_b
    print(f"markers distinguishable {seen_a!r} vs {seen_b!r}", flush=True)


def test_unsafe_load_does_not_convert_payload_decode_into_success_pair():
    secret = sampled_secret()
    salt = sampled_secret()
    helper = make_helper(secret, salt=salt)
    token = dump_object(helper, PUBLIC_ID_MAPPING)
    first_ok, second_ok = require_unsafe_pair(unsafe_load_object(helper, token))
    assert first_ok
    assert second_ok == PUBLIC_ID_MAPPING

    garbage = signed_garbage_token(
        shorten_payload(payload_section(token)), secret=secret, salt=salt
    )
    _load_exc, unsafe_exc = require_payload_decode_failure(helper, garbage)
    print(
        f"unsafe payload-decode aborted via {type(unsafe_exc).__name__}",
        flush=True,
    )


def test_signature_mismatch_and_payload_decode_are_distinguishable():
    secret = sampled_secret()
    salt = sampled_secret()
    helper = make_helper(secret, salt=salt)
    token = dump_object(helper, PUBLIC_ID_MAPPING)
    chopped = chop_last_character(token)
    mismatch_exc, mismatch_pair = require_signature_mismatch(
        helper, chopped, expected=PUBLIC_ID_MAPPING
    )
    garbage = signed_garbage_token(
        shorten_payload(payload_section(token)), secret=secret, salt=salt
    )
    decode_exc, decode_unsafe = require_payload_decode_failure(helper, garbage)
    print(
        f"mismatch pair={mismatch_pair!r} decode_load={type(decode_exc).__name__} "
        f"decode_unsafe={type(decode_unsafe).__name__}",
        flush=True,
    )
    assert not mismatch_pair[0]
    assert mismatch_pair[1] == PUBLIC_ID_MAPPING
    require_recovered_from_failure(
        mismatch_exc, PUBLIC_ID_MAPPING, token=chopped
    )
    assert decode_unsafe is not None
    assert decode_exc is not None


# ---------------------------------------------------------------------------
# I. Unsafe load three states (L32, L137, L145, L149)
# ---------------------------------------------------------------------------


def _assert_unsafe_three_states(helper, obj, *, secret, salt):
    token = dump_object(helper, obj)
    first_ok, second_ok = require_unsafe_pair(unsafe_load_object(helper, token))
    assert first_ok, f"valid token did not report a valid signature: {first_ok!r}"
    assert second_ok == obj

    chopped = chop_last_character(token)
    first_chop, second_chop = require_unsafe_pair(unsafe_load_object(helper, chopped))
    assert not first_chop, (
        "chopped signature was reported valid: "
        f"first={first_chop!r} second={second_chop!r}"
    )
    assert second_chop == obj
    if first_ok == first_chop:
        raise AssertionError("valid and chopped signature reports were not distinguishable")

    payload = payload_section(token)
    shortened = shorten_payload(payload)
    garbage = signed_garbage_token(shortened, secret=secret, salt=salt)
    chopped_garbage = chop_last_character(garbage)
    first_none, second_none = require_unsafe_pair(
        unsafe_load_object(helper, chopped_garbage)
    )
    assert not first_none, (
        "undecodable chopped token was reported valid: "
        f"first={first_none!r}"
    )
    require_absent_object(
        second_none,
        original=obj,
        leftover=shortened,
        chopped_token=chopped_garbage,
    )
    assert second_none != obj
    return first_ok, first_chop, first_none, second_chop, second_none


def test_unsafe_load_valid_token_is_valid_and_object():
    helper = make_helper("secret-key")
    first, second = require_unsafe_pair(
        unsafe_load_object(helper, dump_object(helper, PUBLIC_ID_MAPPING))
    )
    assert first
    assert second == PUBLIC_ID_MAPPING

    obj = runtime_mapping()
    first_rt, second_rt = require_unsafe_pair(
        unsafe_load_object(helper, dump_object(helper, obj))
    )
    assert first_rt
    assert second_rt == obj


def test_unsafe_load_chopped_signature_is_invalid_and_object():
    helper = make_helper("secret-key")
    token = dump_object(helper, PUBLIC_ID_MAPPING)
    chopped = chop_last_character(token)
    first, second = require_unsafe_pair(unsafe_load_object(helper, chopped))
    assert not first
    assert second == PUBLIC_ID_MAPPING

    obj = runtime_mapping()
    chopped_rt = chop_last_character(dump_object(helper, obj))
    first_rt, second_rt = require_unsafe_pair(unsafe_load_object(helper, chopped_rt))
    assert not first_rt
    assert second_rt == obj


def test_unsafe_load_chopped_undecodable_is_invalid_and_no_object():
    secret = sampled_secret()
    salt = sampled_secret()
    helper = make_helper(secret, salt=salt)
    _assert_unsafe_three_states(
        helper, PUBLIC_ID_MAPPING, secret=secret, salt=salt
    )
    obj = runtime_mapping()
    _assert_unsafe_three_states(helper, obj, secret=secret, salt=salt)


def test_unsafe_load_never_reports_bad_signature_as_valid():
    secret = sampled_secret()
    salt = sampled_secret()
    helper = make_helper(secret, salt=salt)
    first_ok, first_chop, first_none, second_chop, second_none = (
        _assert_unsafe_three_states(
            helper, PUBLIC_ID_MAPPING, secret=secret, salt=salt
        )
    )
    assert first_ok
    assert not first_chop
    assert not first_none
    assert second_chop == PUBLIC_ID_MAPPING
    assert second_none != PUBLIC_ID_MAPPING


# ---------------------------------------------------------------------------
# J. Four tamper transforms are signature mismatch (L141, L150)
# ---------------------------------------------------------------------------


def _assert_transform_is_mismatch(helper, obj, transform, **mismatch_kwargs):
    token = dump_object(helper, obj)
    require_load_success(load_object_call(helper, token), expected=obj)
    tampered = transform(token)
    print(
        f"tamper from_len={len(token)} to_len={len(tampered)} "
        f"from_type={type(token).__name__}",
        flush=True,
    )
    assert tampered != token
    require_signature_mismatch(helper, tampered, **mismatch_kwargs)


def test_uppercased_token_is_signature_mismatch():
    helper = make_helper("secret-key")

    def upper(token: str | bytes) -> str | bytes:
        if isinstance(token, bytes):
            changed = token.upper()
        else:
            changed = token.upper()
        if changed == token:
            raise AssertionError(f"uppercasing was a no-op on {token!r}")
        return changed

    _assert_transform_is_mismatch(helper, PUBLIC_ID_MAPPING, upper)
    mapping = runtime_mapping()
    _assert_transform_is_mismatch(helper, mapping, upper)


def test_appended_character_is_signature_mismatch():
    helper = make_helper("secret-key")
    extra = sampled_ascii_letter()

    def append(token: str | bytes) -> str | bytes:
        if isinstance(token, bytes):
            return token + extra.encode("ascii")
        return token + extra

    _assert_transform_is_mismatch(
        helper, PUBLIC_ID_MAPPING, append, expected=PUBLIC_ID_MAPPING
    )
    mapping = runtime_mapping()
    _assert_transform_is_mismatch(helper, mapping, append, expected=mapping)


def test_replaced_first_character_is_signature_mismatch():
    helper = make_helper("secret-key")

    def replace_first(token: str | bytes) -> str | bytes:
        if isinstance(token, bytes):
            first = token[:1]
            replacement = b"X" if first != b"X" else b"Y"
            return replacement + token[1:]
        first = token[:1]
        replacement = "X" if first != "X" else "Y"
        return replacement + token[1:]

    _assert_transform_is_mismatch(helper, PUBLIC_ID_MAPPING, replace_first)
    _assert_transform_is_mismatch(helper, runtime_mapping(), replace_first)


def test_separator_removed_is_signature_mismatch():
    helper = make_helper("secret-key")

    def drop_sep(token: str | bytes) -> str | bytes:
        if isinstance(token, bytes):
            return replace_bytes(token, b".", b"", count=1)
        return replace_bytes(token, TEXT_SEPARATOR, "", count=1)

    _assert_transform_is_mismatch(helper, PUBLIC_ID_MAPPING, drop_sep)
    _assert_transform_is_mismatch(helper, runtime_mapping(), drop_sep)


# ---------------------------------------------------------------------------
# K. Default digest SHA-1; SHA-512 longer and self round-trip (L29, L133, L135)
# ---------------------------------------------------------------------------


def test_default_digest_matches_explicit_sha1_on_list_42():
    secret = sampled_secret()
    default = make_helper(secret)
    explicit = make_helper(secret, signer_kwargs={"digest_method": hashlib.sha1})
    token_default = dump_object(default, [42])
    token_explicit = dump_object(explicit, [42])
    print(
        f"default={token_default!r} explicit_sha1={token_explicit!r}",
        flush=True,
    )
    assert token_default == token_explicit


def test_sha512_token_differs_and_signature_longer():
    secret = sampled_secret()
    sha1 = make_helper(secret, signer_kwargs={"digest_method": hashlib.sha1})
    sha512 = make_helper(secret, signer_kwargs={"digest_method": hashlib.sha512})
    token_sha1 = dump_object(sha1, [42])
    token_sha512 = dump_object(sha512, [42])
    sig_sha1 = signature_section(token_sha1)
    sig_sha512 = signature_section(token_sha512)
    print(
        f"sha1_sig_len={len(sig_sha1)} sha512_sig_len={len(sig_sha512)}",
        flush=True,
    )
    assert token_sha512 != token_sha1
    assert len(sig_sha512) > len(sig_sha1)


def test_sha512_helper_round_trips_and_refuses_changed_payload():
    secret = sampled_secret()
    sha512 = make_helper(secret, signer_kwargs={"digest_method": hashlib.sha512})
    token = require_round_trip_object(sha512, [42])
    assert load_object(sha512, token) == [42]
    runtime_obj = runtime_mapping()
    token_rt = require_round_trip_object(sha512, runtime_obj)
    assert load_object(sha512, token_rt) == runtime_obj
    payload = payload_section(token)
    signature = signature_section(token)
    changed = replace_bytes(payload, "42" if isinstance(payload, str) else b"42",
                             "43" if isinstance(payload, str) else b"43")
    tampered = join_payload_and_signature(changed, signature)
    refused = load_object_call(sha512, tampered)
    assert refused.exception is not None, (
        f"SHA-512 helper loaded a changed payload as {refused.value!r}"
    )
    _exc, (first, second) = require_signature_mismatch(sha512, tampered)
    assert not first, (
        "changed payload under SHA-512 must be a signature mismatch; "
        f"unsafe first={first!r} second={second!r}"
    )


def test_sha1_helper_without_fallback_cannot_load_sha512_token():
    secret = sampled_secret()
    sha1 = make_helper(secret, signer_kwargs={"digest_method": hashlib.sha1})
    sha512 = make_helper(secret, signer_kwargs={"digest_method": hashlib.sha512})
    token = dump_object(sha512, [42])
    baseline = require_round_trip_object(sha1, [42])
    assert load_object(sha1, baseline) == [42]
    refused = load_object_call(sha1, token)
    assert refused.exception is not None, (
        f"SHA-1 helper without fallback loaded a SHA-512 token as {refused.value!r}"
    )
    _exc, (first, second) = require_signature_mismatch(
        sha1, token, expected=[42]
    )
    assert not first, (
        "SHA-1 helper without a SHA-512 fallback must refuse the SHA-512 "
        f"token as a signature mismatch; unsafe first={first!r} second={second!r}"
    )
    assert second == [42]


# ---------------------------------------------------------------------------
# L. Secret lists forwarded through this helper (L21, L100, L124)
# ---------------------------------------------------------------------------


def test_secret_a_token_loads_on_a_then_b():
    helper_a = make_helper("a")
    token = dump_object(helper_a, PUBLIC_ID_MAPPING)
    helper_ab = make_helper(["a", "b"])
    loaded = load_object(helper_ab, token)
    assert loaded == PUBLIC_ID_MAPPING


def test_secret_a_token_refused_after_dropping_a():
    helper_a = make_helper("a")
    token = dump_object(helper_a, PUBLIC_ID_MAPPING)
    helper_ab = make_helper(["a", "b"])
    assert load_object(helper_ab, token) == PUBLIC_ID_MAPPING
    helper_b = make_helper("b")
    require_round_trip_object(helper_b, PUBLIC_ID_MAPPING)
    require_signature_mismatch(helper_b, token, expected=PUBLIC_ID_MAPPING)


def test_token_from_a_then_b_refused_by_only_a():
    helper_ab = make_helper(["a", "b"])
    token = dump_object(helper_ab, PUBLIC_ID_MAPPING)
    helper_a = make_helper("a")
    require_round_trip_object(helper_a, PUBLIC_ID_MAPPING)
    require_signature_mismatch(helper_a, token, expected=PUBLIC_ID_MAPPING)
    helper_b = make_helper("b")
    assert load_object(helper_b, token) == PUBLIC_ID_MAPPING


def test_runtime_older_key_loads_until_dropped():
    k_old, k_new = sampled_secret_pair()
    obj = runtime_mapping()
    helper_old = make_helper(k_old)
    token = dump_object(helper_old, obj)
    helper_both = make_helper([k_old, k_new])
    assert load_object(helper_both, token) == obj
    helper_new = make_helper(k_new)
    require_round_trip_object(helper_new, obj)
    require_signature_mismatch(helper_new, token, expected=obj)
