# feature: F05
"""FP-05: otpauth provisioning URI parsing.

Assertions follow the Full PRD FP-05 plus the PRD's shared defaults
(Terminology, Non-functional constraints). Failure message text, exception class names, Steam, and
internal URI split/assembly are not pinned.
"""

from __future__ import annotations

from hashlib import sha1, sha256, sha512

from otpkit import HOTP, TOTP, parse_uri

from _harness import call
from F02_helpers import (
    GEZDGNBV_SECRET,
    WRN3_SECRET,
    _strip_secret_forms,
    emit_at,
    require_code,
    require_helper,
    require_named_code,
    require_rejected,
    unpublished_relative_count,
    unpublished_starting_counter,
)
from F03_helpers import (
    NAMED_UNIX_INSTANTS,
    check_at_instant,
    emit_for_instant,
    success_carrier_at,
    unpublished_unix_instant,
)
from F04_helpers import (
    BANG_ENCODED,
    C7UXU_SECRET,
    JBSWY_SECRET,
    NAMED_ACCOUNT_BACO,
    NAMED_ACCOUNT_EXAMPLE,
    NAMED_ACCOUNT_GOOGLE,
    NAMED_ACCOUNT_N,
    NAMED_IMAGE_URL,
    NAMED_ISSUER_FOOCORP,
    NAMED_ISSUER_FOOCORP_BANG,
    NAMED_ISSUER_I,
    NAMED_ISSUER_SECURE_APP,
    README_HOTP_URI,
    README_TOTP_URI,
    S46_SECRET,
    SECRET_PLACEHOLDER,
    SECRET_PLACEHOLDER_URI,
    SHA512_IMAGE_URI,
    build_uri,
    parsed_otpauth,
    require_named_uri,
    require_query_includes,
    require_query_omits,
    require_uri,
    unpublished_base32_secret,
    unpublished_label,
    unpublished_no_scheme_image_token,
)
from F05_helpers import (
    ACCOUNT_A_COLON_B,
    ACCOUNT_BOB,
    A_ENCODED_COLON_B_URI,
    ALGORITHM_AES_URI,
    BIG_CORP_URI,
    CODE_289363,
    CODE_524153,
    CODE_662488,
    CODE_734055,
    CODE_816660,
    CODE_918961,
    CODE_934470,
    DERP_SECRET_URI,
    DIGITS_MINUS_ONE_URI,
    F05_NAMED_LABELS,
    F05_NAMED_SECRETS,
    FFFFF_SECRET,
    GEZDGNBV_HOTP_COUNTER1_URI,
    GEZDGNBV_HOTP_URI,
    GEZDGNBV_IMAGE_FOOBAR_URI,
    GEZDGNBV_NO_IMAGE_URI,
    GEZDGNBV_N_I_REBUILD_URI,
    GEZDGNBV_SECRET_PLACEHOLDER_URI,
    GEZDGNBV_TOTP_PERIOD60_URI,
    GEZDGNBV_TOTP_SHA1_URI,
    GEZDGNBV_TOTP_SHA256_URI,
    GEZDGNBV_TOTP_SHA512_URI,
    HTTP_HELLO_URI,
    ISSUER_BIG_CORP,
    NAMED_PARSE_UNIX,
    OTPAUTH_TOTP_NO_SECRET_URI,
    SOME_ANOTHER_ISSUER_URI,
    TEXT_COLON_URI,
    TEXT_MORE_ISSUER,
    label_from_rebuild,
    require_parse_refused,
    round_trip_built_uri,
    run_parse,
    unpublished_colon_issuer,
    unpublished_illegal_algorithm,
    unpublished_illegal_digits,
    unpublished_non_otpauth_scheme,
    unpublished_otp_type,
    unpublished_period_gt_sixty,
)

WRONG_SIX_DIGIT = "000000"


def _direct_totp(secret, **kwargs):
    return require_helper(call(TOTP, secret, **kwargs))


def _direct_hotp(secret, **kwargs):
    return require_helper(call(HOTP, secret, **kwargs))


def _parse(uri):
    return require_helper(run_parse(parse_uri, uri))


def _rebuild(helper, **kwargs):
    return require_uri(build_uri(helper, **kwargs))


def _totp_kind(helper):
    uri = _rebuild(helper)
    parsed = parsed_otpauth(uri)
    assert parsed.otp_type == "totp", (
        "helper kind must be time-based (type totp): "
        f"got={parsed.otp_type!r} uri={uri!r}"
    )
    return uri


def _hotp_kind(helper):
    uri = _rebuild(helper)
    parsed = parsed_otpauth(uri)
    assert parsed.otp_type == "hotp", (
        "helper kind must be HMAC-based (type hotp): "
        f"got={parsed.otp_type!r} uri={uri!r}"
    )
    assert "counter" in parsed.query, (
        "HMAC rebuild must include counter: "
        f"keys={sorted(parsed.query)} uri={uri!r}"
    )
    return uri


# ---------------------------------------------------------------------------
# A. FP-04 built URIs round-trip except image
# ---------------------------------------------------------------------------


def test_fp04_built_uris_round_trip_except_image():
    totp_readme = _direct_totp(
        JBSWY_SECRET,
        name=NAMED_ACCOUNT_GOOGLE,
        issuer=NAMED_ISSUER_SECURE_APP,
    )
    totp_u, _ = round_trip_built_uri(parse_uri, totp_readme)
    require_named_uri(build_uri(totp_readme), README_TOTP_URI)
    print(f"readme totp round-trip {totp_u!r}", flush=True)

    hotp_readme = _direct_hotp(
        JBSWY_SECRET,
        name=NAMED_ACCOUNT_GOOGLE,
        issuer=NAMED_ISSUER_SECURE_APP,
        initial_count=0,
    )
    hotp_u, _ = round_trip_built_uri(parse_uri, hotp_readme)
    require_named_uri(build_uri(hotp_readme), README_HOTP_URI)
    print(f"readme hotp round-trip {hotp_u!r}", flush=True)

    s46 = _direct_totp(S46_SECRET)
    s46_u, _ = round_trip_built_uri(parse_uri, s46)
    require_named_uri(build_uri(s46), SECRET_PLACEHOLDER_URI)
    print(f"s46 Secret round-trip {s46_u!r}", flush=True)

    foocorp = _direct_hotp(
        WRN3_SECRET,
        name=NAMED_ACCOUNT_EXAMPLE,
        issuer=NAMED_ISSUER_FOOCORP_BANG,
    )
    foocorp_u, parsed_foocorp = round_trip_built_uri(parse_uri, foocorp)
    assert BANG_ENCODED in foocorp_u, (
        "HMAC FooCorp! round-trip must keep the encoded bang in the path: "
        f"uri={foocorp_u!r}"
    )
    require_query_includes(
        foocorp_u, {"secret": WRN3_SECRET, "issuer": NAMED_ISSUER_FOOCORP_BANG}
    )
    assert "counter" in parsed_otpauth(foocorp_u).query
    _hotp_kind(parsed_foocorp)
    print(f"foocorp bang hmac round-trip {foocorp_u!r}", flush=True)

    c7_256 = _direct_totp(
        C7UXU_SECRET,
        digits=8,
        interval=60,
        digest=sha256,
        name=NAMED_ACCOUNT_BACO,
        issuer=NAMED_ISSUER_FOOCORP,
    )
    c7_256_u, parsed_c7_256 = round_trip_built_uri(parse_uri, c7_256)
    require_query_includes(
        c7_256_u,
        {
            "secret": C7UXU_SECRET,
            "digits": "8",
            "period": "60",
            "algorithm": "SHA256",
        },
    )
    instant_t = unpublished_unix_instant(NAMED_UNIX_INSTANTS | NAMED_PARSE_UNIX)
    before = require_code(emit_for_instant(c7_256, instant_t), 8)
    after = require_code(emit_for_instant(parsed_c7_256, instant_t), 8)
    print(
        f"c7uxu sha256 T={instant_t} before={before!r} after={after!r}",
        flush=True,
    )
    assert before == after, (
        "parsed c7uxu helper must emit the same 8-digit code as the "
        f"builder at T={instant_t}: before={before!r} after={after!r}"
    )

    c7_sha1_60 = _direct_totp(
        C7UXU_SECRET,
        digits=8,
        interval=60,
        digest=sha1,
        name=NAMED_ACCOUNT_BACO,
        issuer=NAMED_ISSUER_FOOCORP,
    )
    c7_sha1_60_u, _ = round_trip_built_uri(parse_uri, c7_sha1_60)
    require_query_includes(
        c7_sha1_60_u, {"digits": "8", "period": "60", "secret": C7UXU_SECRET}
    )
    require_query_omits(c7_sha1_60_u, "algorithm")

    c7_sha1_30 = _direct_totp(
        C7UXU_SECRET,
        digits=8,
        digest=sha1,
        name=NAMED_ACCOUNT_BACO,
        issuer=NAMED_ISSUER_FOOCORP,
    )
    c7_sha1_30_u, _ = round_trip_built_uri(parse_uri, c7_sha1_30)
    require_query_includes(c7_sha1_30_u, {"digits": "8", "secret": C7UXU_SECRET})
    require_query_omits(c7_sha1_30_u, "period", "algorithm")

    hmac_c7 = _direct_hotp(
        C7UXU_SECRET,
        digits=8,
        digest=sha256,
        name=NAMED_ACCOUNT_BACO,
        issuer=NAMED_ISSUER_FOOCORP,
    )
    hmac_c7_u, parsed_hmac_c7 = round_trip_built_uri(parse_uri, hmac_c7)
    require_query_includes(
        hmac_c7_u, {"digits": "8", "algorithm": "SHA256"}
    )
    assert "counter" in parsed_otpauth(hmac_c7_u).query
    hmac_c7_direct = _direct_hotp(C7UXU_SECRET, digits=8, digest=sha256)
    hmac_c7_code = require_code(emit_at(parsed_hmac_c7, 0), 8)
    hmac_c7_direct_code = require_code(emit_at(hmac_c7_direct, 0), 8)
    print(
        f"hmac c7uxu relative0 parsed={hmac_c7_code!r} "
        f"direct={hmac_c7_direct_code!r}",
        flush=True,
    )
    assert hmac_c7_code == hmac_c7_direct_code

    start_12 = _direct_hotp(
        WRN3_SECRET, name=NAMED_ACCOUNT_EXAMPLE, initial_count=12
    )
    round_trip_built_uri(parse_uri, start_12)
    require_query_includes(_rebuild(start_12), {"counter": "12"})

    stored_7 = _direct_hotp(
        WRN3_SECRET, name=NAMED_ACCOUNT_EXAMPLE, initial_count=7
    )
    overlay_u, _ = round_trip_built_uri(parse_uri, stored_7, initial_count=0)
    require_query_includes(overlay_u, {"counter": "0"})
    print(f"stored7 overlay0 round-trip {overlay_u!r}", flush=True)

    secret = unpublished_base32_secret(F05_NAMED_SECRETS)
    account = unpublished_label(F05_NAMED_LABELS)
    issuer = unpublished_label(set(F05_NAMED_LABELS) | {account})
    unpub_totp = _direct_totp(secret, name=account, issuer=issuer)
    round_trip_built_uri(parse_uri, unpub_totp)

    start_k = unpublished_starting_counter({7, 12})
    unpub_hotp = _direct_hotp(
        secret, name=account, issuer=issuer, initial_count=start_k
    )
    unpub_hotp_u, parsed_unpub_hotp = round_trip_built_uri(
        parse_uri, unpub_hotp
    )
    require_query_includes(unpub_hotp_u, {"counter": str(start_k)})
    direct_k = _direct_hotp(secret, initial_count=start_k)
    parsed_k_code = require_code(emit_at(parsed_unpub_hotp, 0), 6)
    direct_k_code = require_code(emit_at(direct_k, 0), 6)
    print(
        f"unpublished hmac K={start_k} parsed={parsed_k_code!r} "
        f"direct={direct_k_code!r}",
        flush=True,
    )
    assert parsed_k_code == direct_k_code

    hmac8_secret = unpublished_base32_secret(set(F05_NAMED_SECRETS) | {secret})
    hmac8_account = unpublished_label(set(F05_NAMED_LABELS) | {account, issuer})
    hmac8_issuer = unpublished_label(
        set(F05_NAMED_LABELS) | {account, issuer, hmac8_account}
    )
    hmac8 = _direct_hotp(
        hmac8_secret,
        digits=8,
        digest=sha256,
        name=hmac8_account,
        issuer=hmac8_issuer,
    )
    hmac8_u, parsed_hmac8 = round_trip_built_uri(parse_uri, hmac8)
    require_query_includes(hmac8_u, {"digits": "8"})
    assert "algorithm" in parsed_otpauth(hmac8_u).query
    hmac8_direct = _direct_hotp(hmac8_secret, digits=8, digest=sha256)
    hmac8_code = require_code(emit_at(parsed_hmac8, 0), 8)
    hmac8_direct_code = require_code(emit_at(hmac8_direct, 0), 8)
    print(
        f"unpublished hmac 8/sha256 parsed={hmac8_code!r} "
        f"direct={hmac8_direct_code!r}",
        flush=True,
    )
    assert hmac8_code == hmac8_direct_code

    image_helper = _direct_totp(
        GEZDGNBV_SECRET,
        digest=sha512,
        name=NAMED_ACCOUNT_N,
        issuer=NAMED_ISSUER_I,
    )
    image_u = require_named_uri(
        build_uri(image_helper, image=NAMED_IMAGE_URL),
        SHA512_IMAGE_URI,
    )
    parsed_image = _parse(image_u)
    require_named_code(emit_for_instant(parsed_image, 0), CODE_816660)
    rebuilt_image = _rebuild(parsed_image)
    require_query_omits(rebuilt_image, "image")
    require_query_includes(
        rebuilt_image,
        {
            "secret": GEZDGNBV_SECRET,
            "issuer": NAMED_ISSUER_I,
            "algorithm": "SHA512",
        },
    )
    label_from_rebuild(parsed_image, NAMED_ISSUER_I, NAMED_ACCOUNT_N)
    print(
        f"image dropped on rebuild uri={rebuilt_image!r}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# B. JBSWY README URIs match direct construction
# ---------------------------------------------------------------------------


def test_jbswy_readme_uris_parse_to_helpers_matching_direct():
    parsed_totp = _parse(README_TOTP_URI)
    totp_uri = _totp_kind(parsed_totp)
    direct_totp = _direct_totp(JBSWY_SECRET)
    unix0_parsed = require_code(emit_for_instant(parsed_totp, 0), 6)
    unix0_direct = require_code(emit_for_instant(direct_totp, 0), 6)
    print(
        f"jbswy totp unix0 parsed={unix0_parsed!r} direct={unix0_direct!r}",
        flush=True,
    )
    assert unix0_parsed == unix0_direct

    instant_t = unpublished_unix_instant(NAMED_UNIX_INSTANTS | NAMED_PARSE_UNIX)
    t_parsed = require_code(emit_for_instant(parsed_totp, instant_t), 6)
    t_direct = require_code(emit_for_instant(direct_totp, instant_t), 6)
    t30_parsed = require_code(emit_for_instant(parsed_totp, instant_t + 30), 6)
    t30_direct = require_code(emit_for_instant(direct_totp, instant_t + 30), 6)
    print(
        f"jbswy totp T={instant_t} parsed={t_parsed!r}/{t30_parsed!r} "
        f"direct={t_direct!r}/{t30_direct!r}",
        flush=True,
    )
    assert t_parsed == t_direct
    assert t30_parsed == t30_direct

    parsed_hotp = _parse(README_HOTP_URI)
    hotp_uri = _hotp_kind(parsed_hotp)
    require_query_includes(hotp_uri, {"counter": "0"})
    direct_hotp = _direct_hotp(JBSWY_SECRET)
    rel0_parsed = require_code(emit_at(parsed_hotp, 0), 6)
    rel0_direct = require_code(emit_at(direct_hotp, 0), 6)
    print(
        f"jbswy hotp relative0 parsed={rel0_parsed!r} direct={rel0_direct!r}",
        flush=True,
    )
    assert rel0_parsed == rel0_direct
    relative_n = unpublished_relative_count(set())
    n_parsed = require_code(emit_at(parsed_hotp, relative_n), 6)
    n_direct = require_code(emit_at(direct_hotp, relative_n), 6)
    print(
        f"jbswy hotp N={relative_n} parsed={n_parsed!r} direct={n_direct!r}",
        flush=True,
    )
    assert n_parsed == n_direct

    stripped_totp = _strip_secret_forms(totp_uri, JBSWY_SECRET)
    stripped_hotp = _strip_secret_forms(hotp_uri, JBSWY_SECRET)
    print(
        f"stripped totp_has_totp={'totp' in stripped_totp} "
        f"hotp_has_hotp={'hotp' in stripped_hotp}",
        flush=True,
    )
    assert "totp" in stripped_totp and "hotp" in stripped_hotp, (
        "after removing the secret text, totp vs hotp type markers "
        f"must remain: totp={stripped_totp!r} hotp={stripped_hotp!r}"
    )


# ---------------------------------------------------------------------------
# C. GEZDGNBV totp SHA1 named codes and named rebuilds
# ---------------------------------------------------------------------------


def test_gezdgnbv_totp_sha1_codes_and_named_rebuilds():
    helper = _parse(GEZDGNBV_TOTP_SHA1_URI)
    _totp_kind(helper)
    require_named_code(emit_for_instant(helper, 0), CODE_734055)
    require_named_code(emit_for_instant(helper, 30), CODE_662488)
    require_named_code(emit_for_instant(helper, 60), CODE_289363)
    require_named_uri(build_uri(helper), GEZDGNBV_SECRET_PLACEHOLDER_URI)
    require_named_uri(
        build_uri(helper, name=NAMED_ACCOUNT_N, issuer_name=NAMED_ISSUER_I),
        GEZDGNBV_N_I_REBUILD_URI,
    )
    direct = _direct_totp(GEZDGNBV_SECRET)
    require_named_code(emit_for_instant(direct, 0), CODE_734055)
    print("gezdgnbv totp sha1 named codes and rebuilds ok", flush=True)


# ---------------------------------------------------------------------------
# D. period=60 shifts named codes; last-wins; unpublished P>60
# ---------------------------------------------------------------------------


def test_period_60_shifts_named_codes_and_rebuild_includes_period():
    period60 = _parse(GEZDGNBV_TOTP_PERIOD60_URI)
    require_named_code(emit_for_instant(period60, 30), CODE_734055)
    require_named_code(emit_for_instant(period60, 60), CODE_662488)
    rebuilt_60 = _rebuild(
        period60, name=NAMED_ACCOUNT_N, issuer_name=NAMED_ISSUER_I
    )
    require_query_includes(rebuilt_60, {"period": "60"})
    assert parsed_otpauth(rebuilt_60).otp_type == "totp"

    default_30 = _parse(GEZDGNBV_TOTP_SHA1_URI)
    require_named_code(emit_for_instant(default_30, 30), CODE_662488)
    print("period=60 vs default 30 at unix 30", flush=True)

    forward = _parse(
        "otpauth://totp/?algorithm=SHA1&secret=GEZDGNBV&algorithm=SHA1"
        "&period=30&period=60"
    )
    require_named_code(emit_for_instant(forward, 30), CODE_734055)

    reverse = _parse(
        "otpauth://totp/?algorithm=SHA1&secret=GEZDGNBV&algorithm=SHA1"
        "&period=60&period=30"
    )
    require_named_code(emit_for_instant(reverse, 30), CODE_662488)
    print("period last-wins forward 60 / reverse 30", flush=True)

    period_p = unpublished_period_gt_sixty({30, 60})
    parsed_p = _parse(
        "otpauth://totp/?algorithm=SHA1&secret=GEZDGNBV&algorithm=SHA1"
        f"&period={period_p}"
    )
    rebuilt_p = _rebuild(
        parsed_p, name=NAMED_ACCOUNT_N, issuer_name=NAMED_ISSUER_I
    )
    require_query_includes(rebuilt_p, {"period": str(period_p)})
    require_named_code(emit_for_instant(parsed_p, 30), CODE_734055)
    code_p_at_60 = require_named_code(
        emit_for_instant(parsed_p, 60), CODE_734055
    )
    code_60_at_60 = require_named_code(
        emit_for_instant(period60, 60), CODE_662488
    )
    print(
        f"P={period_p} unix60={code_p_at_60!r} period60_unix60={code_60_at_60!r}",
        flush=True,
    )
    assert code_p_at_60 != code_60_at_60
    direct_p = _direct_totp(GEZDGNBV_SECRET, interval=period_p)
    require_named_code(emit_for_instant(direct_p, 60), CODE_734055)


# ---------------------------------------------------------------------------
# E. hotp GEZDGNBV named codes; counter 0/1; last-wins
# ---------------------------------------------------------------------------


def test_hotp_gezdgnbv_codes_counter_zero_and_one():
    hotp0 = _parse(GEZDGNBV_HOTP_URI)
    _hotp_kind(hotp0)
    require_named_code(emit_at(hotp0, 0), CODE_734055)
    require_named_code(emit_at(hotp0, 1), CODE_662488)
    require_named_code(emit_at(hotp0, 2), CODE_289363)
    rebuilt0 = _rebuild(
        hotp0, name=NAMED_ACCOUNT_N, issuer_name=NAMED_ISSUER_I
    )
    require_query_includes(rebuilt0, {"counter": "0"})
    assert parsed_otpauth(rebuilt0).otp_type == "hotp"

    hotp1 = _parse(GEZDGNBV_HOTP_COUNTER1_URI)
    require_named_code(emit_at(hotp1, 0), CODE_662488)
    require_named_code(emit_at(hotp1, 1), CODE_289363)
    rebuilt1 = _rebuild(
        hotp1, name=NAMED_ACCOUNT_N, issuer_name=NAMED_ISSUER_I
    )
    require_query_includes(rebuilt1, {"counter": "1"})
    print("hotp counter=1 shifts relative 0/1", flush=True)

    require_named_code(emit_at(hotp0, 0), CODE_734055)

    forward = _parse(
        "otpauth://hotp/?algorithm=SHA1&secret=GEZDGNBV&algorithm=SHA1"
        "&counter=0&counter=1"
    )
    require_named_code(emit_at(forward, 0), CODE_662488)
    reverse = _parse(
        "otpauth://hotp/?algorithm=SHA1&secret=GEZDGNBV&algorithm=SHA1"
        "&counter=1&counter=0"
    )
    require_named_code(emit_at(reverse, 0), CODE_734055)
    print("counter last-wins forward 1 / reverse 0", flush=True)


# ---------------------------------------------------------------------------
# F. last algorithm SHA256 / SHA512; hotp symmetric
# ---------------------------------------------------------------------------


def test_last_algorithm_sha256_and_sha512_named_codes():
    sha256_helper = _parse(GEZDGNBV_TOTP_SHA256_URI)
    require_named_code(emit_for_instant(sha256_helper, 0), CODE_918961)
    require_named_code(emit_for_instant(sha256_helper, 9000), CODE_934470)

    sha512_helper = _parse(GEZDGNBV_TOTP_SHA512_URI)
    require_named_code(emit_for_instant(sha512_helper, 0), CODE_816660)
    require_named_code(emit_for_instant(sha512_helper, 9000), CODE_524153)

    sha1_helper = _parse(GEZDGNBV_TOTP_SHA1_URI)
    sha1_unix0 = require_named_code(emit_for_instant(sha1_helper, 0), CODE_734055)
    assert sha1_unix0 != CODE_918961 and sha1_unix0 != CODE_816660
    print("GEZDGNBV last algorithm named codes differ at unix 0", flush=True)

    reverse_256 = _parse(
        "otpauth://totp/?algorithm=SHA256&secret=GEZDGNBV&algorithm=SHA1"
    )
    require_named_code(emit_for_instant(reverse_256, 0), CODE_734055)
    reverse_512 = _parse(
        "otpauth://totp/?algorithm=SHA512&secret=GEZDGNBV&algorithm=SHA1"
    )
    require_named_code(emit_for_instant(reverse_512, 0), CODE_734055)

    secret = unpublished_base32_secret(F05_NAMED_SECRETS)
    parsed_unpub_256 = _parse(
        f"otpauth://totp/?secret={secret}&algorithm=SHA1&algorithm=SHA256"
    )
    parsed_unpub_sha1 = _parse(
        f"otpauth://totp/?secret={secret}&algorithm=SHA1&algorithm=SHA1"
    )
    direct_256 = _direct_totp(secret, digest=sha256)
    direct_sha1 = _direct_totp(secret, digest=sha1)
    unpub_256_code = require_code(emit_for_instant(parsed_unpub_256, 0), 6)
    unpub_sha1_code = require_code(emit_for_instant(parsed_unpub_sha1, 0), 6)
    assert unpub_256_code == require_code(emit_for_instant(direct_256, 0), 6)
    assert unpub_sha1_code == require_code(emit_for_instant(direct_sha1, 0), 6)

    parsed_unpub_512 = _parse(
        f"otpauth://totp/?secret={secret}&algorithm=SHA1&algorithm=SHA512"
    )
    direct_512 = _direct_totp(secret, digest=sha512)
    unpub_512_code = require_code(emit_for_instant(parsed_unpub_512, 0), 6)
    assert unpub_512_code == require_code(emit_for_instant(direct_512, 0), 6)
    print(
        f"unpublished totp last-algorithm unix0 "
        f"sha256={unpub_256_code!r} sha1={unpub_sha1_code!r} "
        f"sha512={unpub_512_code!r}",
        flush=True,
    )

    hmac_fwd = _parse(
        f"otpauth://hotp/?secret={secret}&algorithm=SHA1&algorithm=SHA256"
    )
    hmac_rev = _parse(
        "otpauth://hotp/?secret=GEZDGNBV&algorithm=SHA256&algorithm=SHA1"
    )
    hmac_direct_256 = _direct_hotp(secret, digest=sha256)
    hmac_fwd_code = require_code(emit_at(hmac_fwd, 0), 6)
    assert hmac_fwd_code == require_code(emit_at(hmac_direct_256, 0), 6)
    require_named_code(emit_at(hmac_rev, 0), CODE_734055)
    print(
        f"hotp algorithm last-wins unpublished sha256={hmac_fwd_code!r} "
        "reverse GEZDGNBV sha1=734055",
        flush=True,
    )

    hmac_512 = _parse(
        f"otpauth://hotp/?secret={secret}&algorithm=SHA1&algorithm=SHA512"
    )
    hmac_sha1 = _parse(
        f"otpauth://hotp/?secret={secret}&algorithm=SHA1"
    )
    hmac_direct_512 = _direct_hotp(secret, digest=sha512)
    hmac_direct_sha1 = _direct_hotp(secret, digest=sha1)
    hmac_512_code = require_code(emit_at(hmac_512, 0), 6)
    hmac_sha1_code = require_code(emit_at(hmac_sha1, 0), 6)
    assert hmac_512_code == require_code(emit_at(hmac_direct_512, 0), 6)
    assert hmac_sha1_code == require_code(emit_at(hmac_direct_sha1, 0), 6)
    print(
        f"hotp sha512 relative0={hmac_512_code!r} sha1={hmac_sha1_code!r}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# G. last secret / digits; digits=7; issuer as-read
# ---------------------------------------------------------------------------


def test_last_query_occurrence_wins_for_secret_and_digits():
    unpub_secret = unpublished_base32_secret(F05_NAMED_SECRETS)
    totp_secret_fwd = _parse(
        f"otpauth://totp/?secret=GEZDGNBV&secret={unpub_secret}"
    )
    totp_secret_rev = _parse(
        f"otpauth://totp/?secret={unpub_secret}&secret=GEZDGNBV"
    )
    direct_unpub_totp = _direct_totp(unpub_secret)
    fwd_code = require_code(emit_for_instant(totp_secret_fwd, 0), 6)
    assert fwd_code == require_code(emit_for_instant(direct_unpub_totp, 0), 6)
    require_named_code(emit_for_instant(totp_secret_rev, 0), CODE_734055)

    hotp_secret_fwd = _parse(
        f"otpauth://hotp/?secret=GEZDGNBV&secret={unpub_secret}"
    )
    hotp_secret_rev = _parse(
        f"otpauth://hotp/?secret={unpub_secret}&secret=GEZDGNBV"
    )
    direct_unpub_hotp = _direct_hotp(unpub_secret)
    hotp_fwd_code = require_code(emit_at(hotp_secret_fwd, 0), 6)
    assert hotp_fwd_code == require_code(emit_at(direct_unpub_hotp, 0), 6)
    require_named_code(emit_at(hotp_secret_rev, 0), CODE_734055)
    print(
        f"secret last-wins totp/hotp unpublished={fwd_code!r}/{hotp_fwd_code!r}",
        flush=True,
    )

    totp_digits_fwd = _parse(
        "otpauth://totp/?secret=GEZDGNBV&digits=6&digits=8"
    )
    totp_digits_rev = _parse(
        "otpauth://totp/?secret=GEZDGNBV&digits=8&digits=6"
    )
    direct_eight_totp = _direct_totp(GEZDGNBV_SECRET, digits=8)
    direct_six_totp = _direct_totp(GEZDGNBV_SECRET, digits=6)
    eight_code = require_code(emit_for_instant(totp_digits_fwd, 0), 8)
    six_direct = require_named_code(
        emit_for_instant(direct_six_totp, 0), CODE_734055
    )
    assert eight_code == require_code(emit_for_instant(direct_eight_totp, 0), 8)
    assert eight_code != six_direct
    rev_six = require_code(emit_for_instant(totp_digits_rev, 0), 6)
    assert rev_six == six_direct

    hotp_digits_fwd = _parse(
        "otpauth://hotp/?secret=GEZDGNBV&digits=6&digits=8"
    )
    hotp_digits_rev = _parse(
        "otpauth://hotp/?secret=GEZDGNBV&digits=8&digits=6"
    )
    direct_eight_hotp = _direct_hotp(GEZDGNBV_SECRET, digits=8)
    direct_six_hotp = _direct_hotp(GEZDGNBV_SECRET, digits=6)
    hotp_eight = require_code(emit_at(hotp_digits_fwd, 0), 8)
    hotp_six_direct = require_named_code(emit_at(direct_six_hotp, 0), CODE_734055)
    assert hotp_eight == require_code(emit_at(direct_eight_hotp, 0), 8)
    assert hotp_eight != hotp_six_direct
    hotp_rev_six = require_code(emit_at(hotp_digits_rev, 0), 6)
    assert hotp_rev_six == hotp_six_direct
    print(
        f"digits last-wins totp eight={eight_code!r} hotp eight={hotp_eight!r}",
        flush=True,
    )

    totp7 = _parse("otpauth://totp/?secret=GEZDGNBV&digits=7")
    rebuilt7 = _rebuild(totp7)
    require_query_includes(rebuilt7, {"digits": "7"})
    totp7_code = require_code(emit_for_instant(totp7, 0), 7)
    direct7_totp = _direct_totp(GEZDGNBV_SECRET, digits=7)
    assert totp7_code == require_code(emit_for_instant(direct7_totp, 0), 7)
    assert totp7_code != six_direct

    hotp7 = _parse("otpauth://hotp/?secret=GEZDGNBV&digits=7")
    rebuilt_hotp7 = _rebuild(hotp7)
    require_query_includes(rebuilt_hotp7, {"digits": "7"})
    assert "counter" in parsed_otpauth(rebuilt_hotp7).query
    hotp7_code = require_code(emit_at(hotp7, 0), 7)
    direct7_hotp = _direct_hotp(GEZDGNBV_SECRET, digits=7)
    assert hotp7_code == require_code(emit_at(direct7_hotp, 0), 7)
    assert hotp7_code != hotp_six_direct
    print(
        f"digits=7 totp={totp7_code!r} hotp={hotp7_code!r}",
        flush=True,
    )

    issuer_i = unpublished_label(F05_NAMED_LABELS)
    issuer_j = unpublished_label(set(F05_NAMED_LABELS) | {issuer_i})
    account = unpublished_label(set(F05_NAMED_LABELS) | {issuer_i, issuer_j})
    secret_asread = unpublished_base32_secret(
        set(F05_NAMED_SECRETS) | {unpub_secret}
    )
    path = f"{issuer_i}:{account}"
    baseline = _parse(
        f"otpauth://totp/{path}?secret={secret_asread}&issuer={issuer_i}"
    )
    label_from_rebuild(baseline, issuer_i, account)

    equal_dup = _parse(
        f"otpauth://totp/{path}?secret={secret_asread}"
        f"&issuer={issuer_i}&issuer={issuer_i}"
    )
    label_from_rebuild(equal_dup, issuer_i, account)

    require_parse_refused(
        run_parse(
            parse_uri,
            f"otpauth://totp/{path}?secret={secret_asread}"
            f"&issuer={issuer_i}&issuer={issuer_j}",
        )
    )
    require_parse_refused(
        run_parse(
            parse_uri,
            f"otpauth://totp/{path}?secret={secret_asread}"
            f"&issuer={issuer_j}&issuer={issuer_i}",
        )
    )
    require_parse_refused(
        run_parse(
            parse_uri,
            f"otpauth://totp/{path}?secret={secret_asread}&issuer={issuer_j}",
        )
    )
    print(
        f"issuer as-read totp I={issuer_i!r} J={issuer_j!r}",
        flush=True,
    )

    hotp_match = _parse(
        f"otpauth://hotp/{path}?secret={secret_asread}&issuer={issuer_i}"
    )
    label_from_rebuild(hotp_match, issuer_i, account)
    require_parse_refused(
        run_parse(
            parse_uri,
            f"otpauth://hotp/{path}?secret={secret_asread}"
            f"&issuer={issuer_j}&issuer={issuer_i}",
        )
    )
    print("issuer as-read hotp J-then-I refused", flush=True)


# ---------------------------------------------------------------------------
# H. literal colon separates; %3A is not a separator
# ---------------------------------------------------------------------------


def test_literal_colon_separates_label_encoded_colon_does_not():
    text_helper = _parse(TEXT_COLON_URI)
    text_issuer, text_decoded = label_from_rebuild(
        text_helper, TEXT_MORE_ISSUER, SECRET_PLACEHOLDER
    )
    assert text_issuer == TEXT_MORE_ISSUER, (
        "named Text%3A More Text URI must recover issuer Text: More Text: "
        f"issuer={text_issuer!r}"
    )
    assert text_decoded == TEXT_MORE_ISSUER + ":" + SECRET_PLACEHOLDER, (
        "named Text%3A More Text URI must recover path issuer:account "
        "without treating %3A as the separator: "
        f"decoded={text_decoded!r}"
    )
    print(
        f"text-colon issuer={text_issuer!r} decoded={text_decoded!r}",
        flush=True,
    )

    constructed = _direct_totp(
        FFFFF_SECRET, name=SECRET_PLACEHOLDER, issuer=TEXT_MORE_ISSUER
    )
    constructed_u = _rebuild(constructed)
    parsed_constructed = _parse(constructed_u)
    constructed_issuer, constructed_decoded = label_from_rebuild(
        parsed_constructed, TEXT_MORE_ISSUER, SECRET_PLACEHOLDER
    )
    assert constructed_issuer == TEXT_MORE_ISSUER, (
        "build-then-parse of Text: More Text / Secret must recover the issuer: "
        f"issuer={constructed_issuer!r}"
    )
    assert constructed_decoded == TEXT_MORE_ISSUER + ":" + SECRET_PLACEHOLDER, (
        "build-then-parse of Text: More Text / Secret must recover the same "
        f"two parts: decoded={constructed_decoded!r}"
    )

    encoded_account = _parse(A_ENCODED_COLON_B_URI)
    encoded_issuer, encoded_decoded = label_from_rebuild(
        encoded_account, None, ACCOUNT_A_COLON_B
    )
    assert encoded_issuer is None, (
        "a%3Ab must not treat the encoded colon as the issuer separator: "
        f"issuer={encoded_issuer!r}"
    )
    assert encoded_decoded == ACCOUNT_A_COLON_B, (
        "a%3Ab must be account a:b with no issuer: "
        f"decoded={encoded_decoded!r}"
    )
    print(
        f"encoded-colon account decoded={encoded_decoded!r} "
        f"issuer={encoded_issuer!r}",
        flush=True,
    )

    big_corp = _parse(BIG_CORP_URI)
    big_issuer, big_decoded = label_from_rebuild(
        big_corp, ISSUER_BIG_CORP, ACCOUNT_BOB
    )
    assert big_issuer == ISSUER_BIG_CORP, (
        "Big Corp:bob must recover issuer Big Corp: "
        f"issuer={big_issuer!r}"
    )
    assert big_decoded == ISSUER_BIG_CORP + ":" + ACCOUNT_BOB, (
        "Big Corp:bob must recover path Big Corp:bob: "
        f"decoded={big_decoded!r}"
    )

    colon_issuer = unpublished_colon_issuer(F05_NAMED_LABELS)
    account = unpublished_label(set(F05_NAMED_LABELS) | {colon_issuer})
    secret = unpublished_base32_secret(F05_NAMED_SECRETS)
    source = _direct_totp(secret, name=account, issuer=colon_issuer)
    parsed_unpub = _parse(_rebuild(source))
    unpub_issuer, unpub_decoded = label_from_rebuild(
        parsed_unpub, colon_issuer, account
    )
    assert unpub_issuer == colon_issuer, (
        "unpublished issuer containing a literal colon must round-trip: "
        f"expected={colon_issuer!r} issuer={unpub_issuer!r}"
    )
    assert unpub_decoded == colon_issuer + ":" + account, (
        "unpublished colon issuer plus account must rebuild as concatenation: "
        f"expected={(colon_issuer + ':' + account)!r} decoded={unpub_decoded!r}"
    )
    print(
        f"unpublished colon issuer={colon_issuer!r} account={account!r}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# I. optional image accepted, ignored, dropped
# ---------------------------------------------------------------------------


def test_image_query_is_accepted_ignored_and_dropped_on_rebuild():
    baseline = _parse(GEZDGNBV_NO_IMAGE_URI)
    require_named_code(emit_for_instant(baseline, 0), CODE_734055)

    foobar = _parse(GEZDGNBV_IMAGE_FOOBAR_URI)
    _totp_kind(foobar)
    require_named_code(emit_for_instant(foobar, 0), CODE_734055)
    direct = _direct_totp(GEZDGNBV_SECRET)
    assert require_code(emit_for_instant(foobar, 0), 6) == require_code(
        emit_for_instant(direct, 0), 6
    )
    rebuilt = _rebuild(foobar)
    require_query_omits(rebuilt, "image")
    require_query_includes(rebuilt, {"secret": GEZDGNBV_SECRET})
    print(f"foobar image dropped rebuilt={rebuilt!r}", flush=True)

    secret = unpublished_base32_secret(F05_NAMED_SECRETS)
    token = unpublished_no_scheme_image_token({"foobar", "nourl"})
    parsed_unpub = _parse(
        f"otpauth://totp/?secret={secret}&image={token}"
    )
    direct_unpub = _direct_totp(secret)
    unpub_code = require_code(emit_for_instant(parsed_unpub, 0), 6)
    assert unpub_code == require_code(emit_for_instant(direct_unpub, 0), 6)
    unpub_rebuilt = _rebuild(parsed_unpub)
    require_query_omits(unpub_rebuilt, "image")
    print(
        f"unpublished image token dropped code={unpub_code!r}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# J. six refusals return no helper; unlike a failed check
# ---------------------------------------------------------------------------


def test_six_parse_refusals_return_no_helper_unlike_failed_check():
    digits7 = _parse("otpauth://totp/?secret=GEZDGNBV&digits=7")
    digits7_code = require_code(emit_for_instant(digits7, 0), 7)
    direct7 = _direct_totp(GEZDGNBV_SECRET, digits=7)
    assert digits7_code == require_code(emit_for_instant(direct7, 0), 7)
    print(f"digits=7 baseline {digits7_code!r}", flush=True)

    totp_ok = _parse(GEZDGNBV_NO_IMAGE_URI)
    require_named_code(emit_for_instant(totp_ok, 0), CODE_734055)
    hotp_ok = _parse(GEZDGNBV_HOTP_URI)
    require_named_code(emit_at(hotp_ok, 0), CODE_734055)

    require_parse_refused(run_parse(parse_uri, HTTP_HELLO_URI))
    require_parse_refused(
        run_parse(
            parse_uri,
            "https://hello.example/path?secret=GEZDGNBV",
        )
    )
    scheme = unpublished_non_otpauth_scheme(set())
    require_parse_refused(
        run_parse(
            parse_uri,
            f"{scheme}://totp/acct?secret=GEZDGNBV",
        )
    )
    print(f"non-otpauth scheme refused including {scheme!r}", flush=True)

    require_parse_refused(run_parse(parse_uri, OTPAUTH_TOTP_NO_SECRET_URI))
    require_parse_refused(run_parse(parse_uri, "otpauth://hotp/"))
    require_parse_refused(run_parse(parse_uri, "otpauth://totp/?digits=6"))
    require_parse_refused(run_parse(parse_uri, "otpauth://hotp/?counter=0"))
    print("missing secret refused with and without other query fields", flush=True)

    require_parse_refused(run_parse(parse_uri, DERP_SECRET_URI))
    otp_type = unpublished_otp_type(set())
    require_parse_refused(
        run_parse(parse_uri, f"otpauth://{otp_type}/?secret=GEZDGNBV")
    )
    print(f"unsupported type refused including {otp_type!r}", flush=True)

    require_parse_refused(run_parse(parse_uri, DIGITS_MINUS_ONE_URI))
    require_parse_refused(
        run_parse(parse_uri, "otpauth://totp/?secret=GEZDGNBV&digits=-1")
    )
    illegal_digits = unpublished_illegal_digits({-1, 6, 7, 8})
    require_parse_refused(
        run_parse(
            parse_uri,
            f"otpauth://totp/?secret=GEZDGNBV&digits={illegal_digits}",
        )
    )
    require_parse_refused(
        run_parse(
            parse_uri,
            f"otpauth://hotp/?secret=GEZDGNBV&digits={illegal_digits}",
        )
    )
    print(f"illegal digits refused including {illegal_digits}", flush=True)

    require_parse_refused(run_parse(parse_uri, SOME_ANOTHER_ISSUER_URI))
    issuer_i = unpublished_label(F05_NAMED_LABELS)
    issuer_j = unpublished_label(set(F05_NAMED_LABELS) | {issuer_i})
    account = unpublished_label(set(F05_NAMED_LABELS) | {issuer_i, issuer_j})
    match = _parse(
        f"otpauth://totp/{issuer_i}:{account}"
        f"?secret=GEZDGNBV&issuer={issuer_i}"
    )
    label_from_rebuild(match, issuer_i, account)
    require_parse_refused(
        run_parse(
            parse_uri,
            f"otpauth://totp/{issuer_i}:{account}"
            f"?secret=GEZDGNBV&issuer={issuer_j}",
        )
    )
    print(
        f"issuer mismatch isolated I={issuer_i!r} J={issuer_j!r}",
        flush=True,
    )

    require_parse_refused(run_parse(parse_uri, ALGORITHM_AES_URI))
    algo = unpublished_illegal_algorithm(set())
    require_parse_refused(
        run_parse(
            parse_uri,
            f"otpauth://totp/?secret=GEZDGNBV&algorithm={algo}",
        )
    )
    hotp_sha1 = _parse(
        "otpauth://hotp/?secret=GEZDGNBV&algorithm=SHA1"
    )
    require_named_code(emit_at(hotp_sha1, 0), CODE_734055)
    require_parse_refused(
        run_parse(
            parse_uri,
            f"otpauth://hotp/?secret=GEZDGNBV&algorithm={algo}",
        )
    )
    print(f"illegal algorithm refused including {algo!r}", flush=True)

    carrier = success_carrier_at(totp_ok, 0)
    require_rejected(
        check_at_instant(totp_ok, WRONG_SIX_DIGIT, 0), carrier
    )
    print(
        "failed check on a parsed helper returns; parse refusals have no helper",
        flush=True,
    )
