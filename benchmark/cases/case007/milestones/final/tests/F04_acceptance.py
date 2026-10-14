# feature: F04
"""FP-04: otpauth provisioning URI generation.

Assertions follow the Full PRD FP-04 plus the PRD's shared defaults
(Terminology, Non-functional constraints). Failure message text,
exception class names, unpublished full-URI goldens, HMAC ``period``,
and URI parsing (FP-05) are not pinned.
"""

from __future__ import annotations

from hashlib import sha1, sha256, sha512
from urllib.parse import unquote

from otpkit import HOTP, TOTP

from _harness import call
import F02_helpers as _f02
from F02_helpers import (
    GEZDGNBV_SECRET,
    WRN3_SECRET,
    check_candidate,
    require_helper,
    require_rejected,
    success_carrier,
    unpublished_starting_counter,
)
from F03_helpers import check_at_instant, success_carrier_at
from F04_helpers import (
    AT_ENCODED,
    BANG_ENCODED,
    C7UXU_SECRET,
    JBSWY_SECRET,
    NAMED_ACCOUNT_BACO,
    NAMED_ACCOUNT_EXAMPLE,
    NAMED_ACCOUNT_GOOGLE,
    NAMED_ACCOUNT_N,
    NAMED_FAILED_CANDIDATE,
    NAMED_ILLEGAL_IMAGE,
    NAMED_IMAGE_URL,
    NAMED_ISSUER_FOOCORP,
    NAMED_ISSUER_FOOCORP_BANG,
    NAMED_ISSUER_I,
    NAMED_ISSUER_SECURE_APP,
    NAMED_SECRETS,
    PATH_ALICE_EXAMPLE,
    PATH_FOOCORP_BACO,
    PATH_FOOCORP_BANG_ALICE,
    README_HOTP_URI,
    README_TOTP_URI,
    S46_SECRET,
    SECRET_PLACEHOLDER,
    SECRET_PLACEHOLDER_URI,
    SHA512_IMAGE_URI,
    UNPUBLISHED_DIGIT_SEVEN,
    build_uri,
    parsed_otpauth,
    require_at_encoded_in_path,
    require_bang_encoded,
    require_build_refused,
    require_image_query,
    require_named_uri,
    require_path,
    require_query_includes,
    require_query_omits,
    require_space_encoded_not_plus,
    require_uri,
    unpublished_base32_secret,
    unpublished_extra_field_name,
    unpublished_extra_field_value,
    unpublished_https_image_missing_host,
    unpublished_https_image_missing_path,
    unpublished_https_image_url,
    unpublished_label,
    unpublished_label_with,
    unpublished_no_scheme_image_token,
    unpublished_period_seconds,
    unpublished_wrong_scheme_image_url,
)


HMAC_WRONG_CANDIDATE = "000000"
FAILED_CHECK_INSTANT = 1_000_000


# ---------------------------------------------------------------------------
# A. otpauth scheme; totp vs hotp; query always includes secret
# ---------------------------------------------------------------------------


def test_otpauth_scheme_totp_vs_hotp_and_query_includes_secret():
    totp = require_helper(call(TOTP, WRN3_SECRET, name=NAMED_ACCOUNT_EXAMPLE))
    hotp = require_helper(call(HOTP, WRN3_SECRET, name=NAMED_ACCOUNT_EXAMPLE))
    totp_uri = require_uri(build_uri(totp))
    hotp_uri = require_uri(build_uri(hotp))
    totp_parsed = parsed_otpauth(totp_uri)
    hotp_parsed = parsed_otpauth(hotp_uri)
    print(
        f"named wrn3 totp_type={totp_parsed.otp_type!r} "
        f"hotp_type={hotp_parsed.otp_type!r}",
        flush=True,
    )
    assert totp_parsed.scheme == "otpauth" and hotp_parsed.scheme == "otpauth"
    assert totp_parsed.otp_type == "totp", (
        "time-based helper must produce type totp: "
        f"got={totp_parsed.otp_type!r} uri={totp_uri!r}"
    )
    assert hotp_parsed.otp_type == "hotp", (
        "HMAC-based helper must produce type hotp: "
        f"got={hotp_parsed.otp_type!r} uri={hotp_uri!r}"
    )
    require_query_includes(totp_uri, {"secret": WRN3_SECRET})
    require_query_includes(hotp_uri, {"secret": WRN3_SECRET})

    secret = unpublished_base32_secret(NAMED_SECRETS)
    account = unpublished_label({NAMED_ACCOUNT_EXAMPLE})
    u_totp = require_helper(call(TOTP, secret, name=account))
    u_hotp = require_helper(call(HOTP, secret, name=account))
    u_totp_uri = require_uri(build_uri(u_totp))
    u_hotp_uri = require_uri(build_uri(u_hotp))
    u_totp_parsed = parsed_otpauth(u_totp_uri)
    u_hotp_parsed = parsed_otpauth(u_hotp_uri)
    print(
        f"unpublished totp_type={u_totp_parsed.otp_type!r} "
        f"hotp_type={u_hotp_parsed.otp_type!r} secret_len={len(secret)}",
        flush=True,
    )
    assert u_totp_parsed.otp_type == "totp"
    assert u_hotp_parsed.otp_type == "hotp"
    require_query_includes(u_totp_uri, {"secret": secret})
    require_query_includes(u_hotp_uri, {"secret": secret})
    assert u_totp_parsed.query["secret"] not in NAMED_SECRETS
    stripped_totp = _f02._strip_secret_forms(u_totp_uri, secret)
    stripped_hotp = _f02._strip_secret_forms(u_hotp_uri, secret)
    print(
        f"stripped totp_has_type={'totp' in stripped_totp} "
        f"hotp_has_type={'hotp' in stripped_hotp}",
        flush=True,
    )
    assert "totp" in stripped_totp and "hotp" in stripped_hotp, (
        "after removing the secret text, totp vs hotp type markers "
        f"must still differ: totp={stripped_totp!r} hotp={stripped_hotp!r}"
    )
    assert stripped_totp != stripped_hotp, (
        "time-based and HMAC URIs are not distinguishable after "
        f"stripping the secret: totp={stripped_totp!r} hotp={stripped_hotp!r}"
    )


# ---------------------------------------------------------------------------
# B. Two JBSWY3 README URIs; constructor vs build-time override
# ---------------------------------------------------------------------------


def test_jbswy3_readme_totp_and_hotp_uris_match_exactly():
    totp_secret_only = require_helper(call(TOTP, JBSWY_SECRET))
    require_named_uri(
        build_uri(
            totp_secret_only,
            name=NAMED_ACCOUNT_GOOGLE,
            issuer_name=NAMED_ISSUER_SECURE_APP,
        ),
        README_TOTP_URI,
    )
    hotp_secret_only = require_helper(call(HOTP, JBSWY_SECRET))
    require_named_uri(
        build_uri(
            hotp_secret_only,
            name=NAMED_ACCOUNT_GOOGLE,
            issuer_name=NAMED_ISSUER_SECURE_APP,
            initial_count=0,
        ),
        README_HOTP_URI,
    )

    totp_constructed = require_helper(
        call(
            TOTP,
            JBSWY_SECRET,
            name=NAMED_ACCOUNT_GOOGLE,
            issuer=NAMED_ISSUER_SECURE_APP,
        )
    )
    require_named_uri(build_uri(totp_constructed), README_TOTP_URI)
    hotp_constructed = require_helper(
        call(
            HOTP,
            JBSWY_SECRET,
            name=NAMED_ACCOUNT_GOOGLE,
            issuer=NAMED_ISSUER_SECURE_APP,
            initial_count=0,
        )
    )
    require_named_uri(build_uri(hotp_constructed), README_HOTP_URI)
    print("constructor-supplied README values match named URIs", flush=True)

    secret = unpublished_base32_secret(NAMED_SECRETS)
    account = unpublished_label(set())
    issuer = unpublished_label_with({account}, " ")
    u_totp = require_helper(call(TOTP, secret, name=account, issuer=issuer))
    u_hotp = require_helper(call(HOTP, secret, name=account, issuer=issuer))
    u_totp_uri = require_uri(build_uri(u_totp))
    u_hotp_uri = require_uri(build_uri(u_hotp))
    print(
        f"unpublished totp={u_totp_uri!r} hotp={u_hotp_uri!r}",
        flush=True,
    )
    assert u_totp_uri != README_TOTP_URI, (
        "unpublished time-based URI must not equal the README totp string: "
        f"{u_totp_uri!r}"
    )
    assert u_hotp_uri != README_HOTP_URI, (
        "unpublished HMAC URI must not equal the README hotp string: "
        f"{u_hotp_uri!r}"
    )
    assert parsed_otpauth(u_totp_uri).scheme == "otpauth"
    assert parsed_otpauth(u_hotp_uri).scheme == "otpauth"
    require_query_includes(u_totp_uri, {"secret": secret})
    require_query_includes(u_hotp_uri, {"secret": secret})
    require_space_encoded_not_plus(u_totp_uri, issuer)
    require_space_encoded_not_plus(u_hotp_uri, issuer)


# ---------------------------------------------------------------------------
# C. Path: issuer:account / account-only / placeholder Secret
# ---------------------------------------------------------------------------


def test_path_is_issuer_colon_account_or_account_or_secret():
    hotp_account = require_helper(
        call(HOTP, WRN3_SECRET, name=NAMED_ACCOUNT_EXAMPLE)
    )
    hotp_account_uri = require_uri(build_uri(hotp_account))
    require_path(hotp_account_uri, PATH_ALICE_EXAMPLE)
    totp_account = require_helper(
        call(TOTP, WRN3_SECRET, name=NAMED_ACCOUNT_EXAMPLE)
    )
    totp_account_uri = require_uri(build_uri(totp_account))
    require_path(totp_account_uri, PATH_ALICE_EXAMPLE)
    assert parsed_otpauth(totp_account_uri).otp_type == "totp"
    print("account-only path shared across helper kinds", flush=True)

    hotp_issuer = require_helper(
        call(
            HOTP,
            WRN3_SECRET,
            name=NAMED_ACCOUNT_EXAMPLE,
            issuer=NAMED_ISSUER_FOOCORP_BANG,
        )
    )
    hotp_issuer_uri = require_uri(build_uri(hotp_issuer))
    require_path(hotp_issuer_uri, PATH_FOOCORP_BANG_ALICE)
    path = parsed_otpauth(hotp_issuer_uri).path
    assert ":" in path, (
        "issuer+account path must keep a literal colon between the "
        f"encoded segments: path={path!r}"
    )
    left, right = path.split(":", 1)
    assert BANG_ENCODED in left and AT_ENCODED in right, (
        "colon must sit between the encoded issuer and encoded account: "
        f"path={path!r}"
    )

    totp_secret = require_helper(call(TOTP, S46_SECRET))
    require_named_uri(build_uri(totp_secret), SECRET_PLACEHOLDER_URI)

    totp_no_account = require_helper(
        call(TOTP, unpublished_base32_secret(NAMED_SECRETS))
    )
    no_account_uri = require_uri(build_uri(totp_no_account))
    assert SECRET_PLACEHOLDER in parsed_otpauth(no_account_uri).path, (
        "building without an account must use the Secret placeholder: "
        f"path={parsed_otpauth(no_account_uri).path!r}"
    )
    override_account = unpublished_label(set())
    override_uri = require_uri(build_uri(totp_no_account, name=override_account))
    override_path = parsed_otpauth(override_uri).path
    print(
        f"placeholder path={parsed_otpauth(no_account_uri).path!r} "
        f"override path={override_path!r} account={override_account!r}",
        flush=True,
    )
    assert override_path != f"/{SECRET_PLACEHOLDER}", (
        "build-time account override must leave the Secret placeholder: "
        f"path={override_path!r}"
    )
    assert override_account in unquote(override_path), (
        "overridden path must contain the unpublished account: "
        f"account={override_account!r} path={override_path!r}"
    )


def test_hmac_without_account_uses_secret_placeholder_and_keeps_counter():
    helper = require_helper(call(HOTP, WRN3_SECRET))
    uri = require_uri(build_uri(helper))
    parsed = parsed_otpauth(uri)
    print(
        f"hmac no-account type={parsed.otp_type!r} path={parsed.path!r}",
        flush=True,
    )
    assert parsed.otp_type == "hotp"
    require_path(uri, f"/{SECRET_PLACEHOLDER}")
    require_query_includes(uri, {"secret": WRN3_SECRET})
    assert "counter" in parsed.query, (
        "HMAC URI without an account must still include counter: "
        f"keys={sorted(parsed.query)}"
    )


# ---------------------------------------------------------------------------
# D. Percent-encoding: @ %40, ! %21, space %20 not plus
# ---------------------------------------------------------------------------


def test_at_bang_and_space_are_percent_encoded_not_plus():
    for account in (
        NAMED_ACCOUNT_GOOGLE,
        NAMED_ACCOUNT_EXAMPLE,
        NAMED_ACCOUNT_BACO,
    ):
        helper = require_helper(call(TOTP, WRN3_SECRET, name=account))
        uri = require_uri(build_uri(helper))
        require_at_encoded_in_path(uri, account)
        print(
            f"named @ account={account!r} path={parsed_otpauth(uri).path!r}",
            flush=True,
        )

    bang_helper = require_helper(
        call(
            HOTP,
            WRN3_SECRET,
            name=NAMED_ACCOUNT_EXAMPLE,
            issuer=NAMED_ISSUER_FOOCORP_BANG,
        )
    )
    bang_uri = require_uri(build_uri(bang_helper))
    require_path(bang_uri, PATH_FOOCORP_BANG_ALICE)
    require_bang_encoded(bang_uri, NAMED_ISSUER_FOOCORP_BANG)
    require_query_includes(bang_uri, {"issuer": NAMED_ISSUER_FOOCORP_BANG})

    space_issuer = unpublished_label_with(set(), " ")
    space_helper = require_helper(
        call(TOTP, WRN3_SECRET, name=NAMED_ACCOUNT_EXAMPLE, issuer=space_issuer)
    )
    space_uri = require_uri(build_uri(space_helper))
    require_space_encoded_not_plus(space_uri, space_issuer)
    print(f"unpublished spaced issuer={space_issuer!r}", flush=True)

    at_account = unpublished_label_with(set(), "@")
    at_helper = require_helper(call(TOTP, WRN3_SECRET, name=at_account))
    at_uri = require_uri(build_uri(at_helper))
    require_at_encoded_in_path(at_uri, at_account)

    bang_issuer = unpublished_label_with(set(), "!")
    bang_unpub = require_helper(
        call(TOTP, WRN3_SECRET, name=NAMED_ACCOUNT_EXAMPLE, issuer=bang_issuer)
    )
    bang_unpub_uri = require_uri(build_uri(bang_unpub))
    require_bang_encoded(bang_unpub_uri, bang_issuer)

    spaced_account = unpublished_label_with(set(), " ")
    spaced_account_helper = require_helper(
        call(TOTP, WRN3_SECRET, name=spaced_account)
    )
    spaced_account_uri = require_uri(build_uri(spaced_account_helper))
    require_space_encoded_not_plus(spaced_account_uri, spaced_account)
    decoded_path = unquote(parsed_otpauth(spaced_account_uri).path)
    assert spaced_account in decoded_path
    assert "issuer" not in parsed_otpauth(spaced_account_uri).query
    print(
        f"unpublished spaced account={spaced_account!r} "
        f"path={parsed_otpauth(spaced_account_uri).path!r}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# E. HMAC URI always writes counter, including 0; override 7 to 0
# ---------------------------------------------------------------------------


def test_hmac_uri_writes_counter_zero_twelve_and_override_zero():
    default = require_helper(
        call(HOTP, WRN3_SECRET, name=NAMED_ACCOUNT_EXAMPLE)
    )
    default_uri = require_uri(build_uri(default))
    require_query_includes(
        default_uri, {"secret": WRN3_SECRET, "counter": "0"}
    )
    print(f"default counter=0 uri={default_uri!r}", flush=True)

    started_12 = require_helper(
        call(HOTP, WRN3_SECRET, name=NAMED_ACCOUNT_EXAMPLE, initial_count=12)
    )
    uri_12 = require_uri(build_uri(started_12))
    require_query_includes(uri_12, {"counter": "12"})

    stored_7 = require_helper(
        call(HOTP, WRN3_SECRET, name=NAMED_ACCOUNT_EXAMPLE, initial_count=7)
    )
    baseline_7 = require_uri(build_uri(stored_7))
    require_query_includes(baseline_7, {"counter": "7"})

    # Overlay proof is a first build, not a later build of the helper above:
    # a fresh helper stored as 7 whose first build is asked for 0 must write
    # counter=0 (zero written, not omitted).
    overlay_stored_7 = require_helper(
        call(HOTP, WRN3_SECRET, name=NAMED_ACCOUNT_EXAMPLE, initial_count=7)
    )
    override_0 = require_uri(build_uri(overlay_stored_7, initial_count=0))
    parsed_override = parsed_otpauth(override_0)
    require_query_includes(override_0, {"counter": "0"})
    assert "counter" in parsed_override.query
    print(
        f"stored7={parsed_otpauth(baseline_7).query['counter']!r} "
        f"first_build_overlay0={parsed_override.query['counter']!r}",
        flush=True,
    )

    start_k = unpublished_starting_counter({0, 7, 12})
    stored_k = require_helper(
        call(
            HOTP,
            WRN3_SECRET,
            name=NAMED_ACCOUNT_EXAMPLE,
            initial_count=start_k,
        )
    )
    uri_k = require_uri(build_uri(stored_k))
    require_query_includes(uri_k, {"counter": str(start_k)})

    overlay_stored_k = require_helper(
        call(
            HOTP,
            WRN3_SECRET,
            name=NAMED_ACCOUNT_EXAMPLE,
            initial_count=start_k,
        )
    )
    uri_k_to_0 = require_uri(build_uri(overlay_stored_k, initial_count=0))
    parsed_k0 = parsed_otpauth(uri_k_to_0)
    require_query_includes(uri_k_to_0, {"counter": "0"})
    assert "counter" in parsed_k0.query
    print(
        f"unpublished start={start_k} first_build_overlay_counter="
        f"{parsed_k0.query['counter']!r}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# F. Default digits/period/algorithm omitted; non-defaults written uppercase
# ---------------------------------------------------------------------------


def test_nondefault_digits_period_algorithm_written_defaults_omitted():
    eight_60_sha256 = require_helper(
        call(
            TOTP,
            C7UXU_SECRET,
            digits=8,
            interval=60,
            digest=sha256,
            name=NAMED_ACCOUNT_BACO,
            issuer=NAMED_ISSUER_FOOCORP,
        )
    )
    uri_256 = require_uri(build_uri(eight_60_sha256))
    require_path(uri_256, PATH_FOOCORP_BACO)
    require_query_includes(
        uri_256,
        {
            "secret": C7UXU_SECRET,
            "issuer": NAMED_ISSUER_FOOCORP,
            "digits": "8",
            "period": "60",
            "algorithm": "SHA256",
        },
    )
    print(f"c7uxu 8/60/SHA256 uri={uri_256!r}", flush=True)

    eight_60_sha1 = require_helper(
        call(
            TOTP,
            C7UXU_SECRET,
            digits=8,
            interval=60,
            digest=sha1,
            name=NAMED_ACCOUNT_BACO,
            issuer=NAMED_ISSUER_FOOCORP,
        )
    )
    uri_sha1 = require_uri(build_uri(eight_60_sha1))
    require_query_includes(
        uri_sha1, {"digits": "8", "period": "60", "secret": C7UXU_SECRET}
    )
    require_query_omits(uri_sha1, "algorithm")

    eight_default_step = require_helper(
        call(
            TOTP,
            C7UXU_SECRET,
            digits=8,
            digest=sha1,
            name=NAMED_ACCOUNT_BACO,
            issuer=NAMED_ISSUER_FOOCORP,
        )
    )
    uri_eight = require_uri(build_uri(eight_default_step))
    require_query_includes(uri_eight, {"digits": "8", "secret": C7UXU_SECRET})
    require_query_omits(uri_eight, "period", "algorithm")

    default_totp = require_helper(
        call(TOTP, WRN3_SECRET, name=NAMED_ACCOUNT_EXAMPLE)
    )
    default_uri = require_uri(build_uri(default_totp))
    require_query_includes(default_uri, {"secret": WRN3_SECRET})
    require_query_omits(default_uri, "digits", "period", "algorithm")

    secret = unpublished_base32_secret(NAMED_SECRETS)
    account = unpublished_label(set())
    issuer = unpublished_label({account})
    ctor_kw = {"name": account, "issuer": issuer}

    nondefault = require_helper(
        call(TOTP, secret, digits=8, interval=60, digest=sha256, **ctor_kw)
    )
    nondefault_uri = require_uri(build_uri(nondefault))
    require_query_includes(
        nondefault_uri,
        {"digits": "8", "period": "60", "algorithm": "SHA256", "secret": secret},
    )
    assert parsed_otpauth(nondefault_uri).query["algorithm"] != "sha256"

    default_unpub = require_helper(call(TOTP, secret, **ctor_kw))
    default_unpub_uri = require_uri(build_uri(default_unpub))
    require_query_includes(default_unpub_uri, {"secret": secret})
    require_query_omits(default_unpub_uri, "digits", "period", "algorithm")

    eight_default_step_unpub = require_helper(
        call(TOTP, secret, digits=8, digest=sha1, **ctor_kw)
    )
    eight_unpub_uri = require_uri(build_uri(eight_default_step_unpub))
    require_query_includes(eight_unpub_uri, {"digits": "8"})
    require_query_omits(eight_unpub_uri, "period", "algorithm")

    seven = require_helper(
        call(TOTP, secret, digits=UNPUBLISHED_DIGIT_SEVEN, digest=sha1, **ctor_kw)
    )
    seven_uri = require_uri(build_uri(seven))
    require_query_includes(seven_uri, {"digits": "7"})
    require_query_omits(seven_uri, "period", "algorithm")

    period = unpublished_period_seconds({30, 60})
    period_helper = require_helper(
        call(TOTP, secret, interval=period, digest=sha1, **ctor_kw)
    )
    period_uri = require_uri(build_uri(period_helper))
    require_query_includes(period_uri, {"period": str(period)})
    require_query_omits(period_uri, "digits", "algorithm")

    sha512_helper = require_helper(call(TOTP, secret, digest=sha512, **ctor_kw))
    sha512_uri = require_uri(build_uri(sha512_helper))
    require_query_includes(sha512_uri, {"algorithm": "SHA512"})
    assert parsed_otpauth(sha512_uri).query["algorithm"] != "sha512"
    require_query_omits(sha512_uri, "digits", "period")
    print(
        f"unpublished period={period} seven=7 sha512=SHA512",
        flush=True,
    )


# ---------------------------------------------------------------------------
# G. HMAC non-default digits/algorithm still always include counter
# ---------------------------------------------------------------------------


def test_hmac_eight_digit_sha256_includes_digits_algorithm_and_counter():
    named = require_helper(
        call(
            HOTP,
            C7UXU_SECRET,
            digits=8,
            digest=sha256,
            name=NAMED_ACCOUNT_BACO,
            issuer=NAMED_ISSUER_FOOCORP,
        )
    )
    named_uri = require_uri(build_uri(named))
    require_query_includes(
        named_uri,
        {"digits": "8", "algorithm": "SHA256", "counter": "0"},
    )
    print(f"hmac c7uxu 8/SHA256 uri={named_uri!r}", flush=True)

    secret = unpublished_base32_secret(NAMED_SECRETS)
    account_default = unpublished_label(set())
    default_hmac = require_helper(call(HOTP, secret, name=account_default))
    default_uri = require_uri(build_uri(default_hmac))
    require_query_omits(default_uri, "digits", "algorithm")
    require_query_includes(default_uri, {"counter": "0", "secret": secret})

    account_eight = unpublished_label({account_default})
    eight_hmac = require_helper(
        call(HOTP, secret, digits=8, digest=sha256, name=account_eight)
    )
    eight_uri = require_uri(build_uri(eight_hmac))
    require_query_includes(
        eight_uri, {"digits": "8", "algorithm": "SHA256"}
    )
    assert "counter" in parsed_otpauth(eight_uri).query

    seven_hmac = require_helper(
        call(
            HOTP,
            secret,
            digits=UNPUBLISHED_DIGIT_SEVEN,
            digest=sha1,
            name=account_eight,
        )
    )
    seven_uri = require_uri(build_uri(seven_hmac))
    require_query_includes(seven_uri, {"digits": "7"})
    require_query_omits(seven_uri, "algorithm")
    assert "counter" in parsed_otpauth(seven_uri).query
    print("hmac unpublished default/8/7 counter still present", flush=True)


# ---------------------------------------------------------------------------
# H. Valid https image is query-encoded; named SHA512 URI
# ---------------------------------------------------------------------------


def test_https_image_is_query_encoded_and_named_sha512_uri_matches():
    named = require_helper(
        call(
            TOTP,
            GEZDGNBV_SECRET,
            digest=sha512,
            name=NAMED_ACCOUNT_N,
            issuer=NAMED_ISSUER_I,
        )
    )
    require_named_uri(
        build_uri(named, image=NAMED_IMAGE_URL),
        SHA512_IMAGE_URI,
    )

    secret = unpublished_base32_secret(NAMED_SECRETS)
    account = unpublished_label(set())
    unpub_totp = require_helper(call(TOTP, secret, name=account))
    named_image_uri = require_uri(build_uri(unpub_totp, image=NAMED_IMAGE_URL))
    require_image_query(named_image_uri, NAMED_IMAGE_URL)
    print(f"unpublished helper + named image uri={named_image_uri!r}", flush=True)

    other_url = unpublished_https_image_url({NAMED_IMAGE_URL})
    other_uri = require_uri(build_uri(unpub_totp, image=other_url))
    require_image_query(other_uri, other_url)
    assert other_url != NAMED_IMAGE_URL

    hmac_named = require_helper(call(HOTP, secret, name=account))
    hmac_named_uri = require_uri(build_uri(hmac_named, image=NAMED_IMAGE_URL))
    require_image_query(hmac_named_uri, NAMED_IMAGE_URL)
    assert "counter" in parsed_otpauth(hmac_named_uri).query

    hmac_other_uri = require_uri(build_uri(hmac_named, image=other_url))
    require_image_query(hmac_other_uri, other_url)
    assert "counter" in parsed_otpauth(hmac_other_uri).query
    print(f"hmac image other_url={other_url!r}", flush=True)


# ---------------------------------------------------------------------------
# I. Illegal image and non-text extra query field: build does not succeed
# ---------------------------------------------------------------------------


def test_nourl_image_and_non_text_extra_query_are_refused():
    totp = require_helper(
        call(
            TOTP,
            GEZDGNBV_SECRET,
            digest=sha512,
            name=NAMED_ACCOUNT_N,
            issuer=NAMED_ISSUER_I,
        )
    )
    baseline = require_uri(build_uri(totp, image=NAMED_IMAGE_URL))
    require_image_query(baseline, NAMED_IMAGE_URL)
    print("totp valid-image baseline ok", flush=True)

    require_build_refused(build_uri(totp, image=NAMED_ILLEGAL_IMAGE))

    no_scheme = unpublished_no_scheme_image_token({NAMED_ILLEGAL_IMAGE})
    require_build_refused(build_uri(totp, image=no_scheme))

    wrong_scheme = unpublished_wrong_scheme_image_url(set())
    missing_path = unpublished_https_image_missing_path(set())
    missing_host = unpublished_https_image_missing_host(set())
    for illegal in (wrong_scheme, missing_path, missing_host):
        print(f"totp refuse image={illegal!r}", flush=True)
        require_build_refused(build_uri(totp, image=illegal))

    extra_key = unpublished_extra_field_name(set())
    extra_value = unpublished_extra_field_value(set())
    extra_ok = require_uri(build_uri(totp, **{extra_key: extra_value}))
    require_query_includes(extra_ok, {extra_key: extra_value})
    require_build_refused(build_uri(totp, **{extra_key: 42}))
    print(f"totp extra key={extra_key!r} text ok, int refused", flush=True)

    hmac = require_helper(call(HOTP, WRN3_SECRET, name=NAMED_ACCOUNT_EXAMPLE))
    hmac_baseline = require_uri(build_uri(hmac, image=NAMED_IMAGE_URL))
    require_image_query(hmac_baseline, NAMED_IMAGE_URL)
    assert "counter" in parsed_otpauth(hmac_baseline).query
    require_build_refused(build_uri(hmac, image=NAMED_ILLEGAL_IMAGE))
    require_build_refused(build_uri(hmac, image=no_scheme))
    for illegal in (wrong_scheme, missing_path, missing_host):
        print(f"hmac refuse image={illegal!r}", flush=True)
        require_build_refused(build_uri(hmac, image=illegal))
    hmac_extra_ok = require_uri(build_uri(hmac, **{extra_key: extra_value}))
    require_query_includes(hmac_extra_ok, {extra_key: extra_value})
    require_build_refused(build_uri(hmac, **{extra_key: 42}))


# ---------------------------------------------------------------------------
# J. Build does not require a prior check; failed check does not rewrite
# ---------------------------------------------------------------------------


def test_secret_uri_unchanged_after_checking_123456():
    helper = require_helper(call(TOTP, S46_SECRET))
    first = require_named_uri(build_uri(helper), SECRET_PLACEHOLDER_URI)
    carrier = success_carrier_at(helper, FAILED_CHECK_INSTANT)
    require_rejected(
        check_at_instant(helper, NAMED_FAILED_CANDIDATE, FAILED_CHECK_INSTANT),
        carrier,
    )
    second = require_named_uri(build_uri(helper), SECRET_PLACEHOLDER_URI)
    assert first == second == SECRET_PLACEHOLDER_URI
    print("S46 Secret URI unchanged after checking 123456", flush=True)

    secret = unpublished_base32_secret(NAMED_SECRETS)
    account = unpublished_label(set())
    issuer = unpublished_label({account})
    unpub = require_helper(call(TOTP, secret, name=account, issuer=issuer))
    before = require_uri(build_uri(unpub))
    unpub_carrier = success_carrier_at(unpub, FAILED_CHECK_INSTANT)
    require_rejected(
        check_at_instant(unpub, NAMED_FAILED_CANDIDATE, FAILED_CHECK_INSTANT),
        unpub_carrier,
    )
    after = require_uri(build_uri(unpub))
    print(f"unpublished before={before!r} after={after!r}", flush=True)
    assert before == after, (
        "failed check rewrote the unpublished URI: "
        f"before={before!r} after={after!r}"
    )


def test_failed_hmac_check_does_not_rewrite_uri():
    helper = require_helper(
        call(HOTP, WRN3_SECRET, name=NAMED_ACCOUNT_EXAMPLE)
    )
    first = require_uri(build_uri(helper))
    require_query_includes(first, {"counter": "0", "secret": WRN3_SECRET})
    carrier = success_carrier(helper, 0)
    require_rejected(check_candidate(helper, HMAC_WRONG_CANDIDATE, 0), carrier)
    second = require_uri(build_uri(helper))
    print(f"hmac before={first!r} after={second!r}", flush=True)
    assert first == second, (
        "failed HMAC check rewrote the URI: "
        f"before={first!r} after={second!r}"
    )


# ---------------------------------------------------------------------------
# K. Build-time account and issuer overrides
# ---------------------------------------------------------------------------


def test_build_time_account_and_issuer_overrides_change_label_and_query():
    account_a = unpublished_label(set())
    issuer_1 = unpublished_label({account_a})
    account_b = unpublished_label({account_a, issuer_1})
    issuer_2 = unpublished_label({account_a, issuer_1, account_b})
    helper = require_helper(
        call(TOTP, WRN3_SECRET, name=account_a, issuer=issuer_1)
    )
    baseline = require_uri(build_uri(helper))
    require_path(baseline, f"/{issuer_1}:{account_a}")
    require_query_includes(baseline, {"issuer": issuer_1})

    overridden = require_uri(
        build_uri(helper, name=account_b, issuer_name=issuer_2)
    )
    require_path(overridden, f"/{issuer_2}:{account_b}")
    require_query_includes(overridden, {"issuer": issuer_2})
    over_path = parsed_otpauth(overridden).path
    assert account_a not in unquote(over_path)
    assert issuer_1 not in unquote(over_path)
    stripped_base = parsed_otpauth(baseline).path
    stripped_over = over_path
    for token in (account_a, issuer_1):
        stripped_base = stripped_base.replace(token, "")
        stripped_over = stripped_over.replace(token, "")
    print(
        f"stripped baseline={stripped_base!r} overridden={stripped_over!r}",
        flush=True,
    )
    assert stripped_base != stripped_over, (
        "after stripping constructor labels, override path must still "
        f"differ: baseline={stripped_base!r} overridden={stripped_over!r}"
    )

    no_issuer = require_helper(call(TOTP, WRN3_SECRET, name=account_a))
    account_only = require_uri(build_uri(no_issuer))
    require_path(account_only, f"/{account_a}")
    assert "issuer" not in parsed_otpauth(account_only).query
    added_issuer = require_uri(build_uri(no_issuer, issuer_name=issuer_2))
    require_path(added_issuer, f"/{issuer_2}:{account_a}")
    require_query_includes(added_issuer, {"issuer": issuer_2})
    print(
        f"added issuer path={parsed_otpauth(added_issuer).path!r}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# L. Extra text query field (not image)
# ---------------------------------------------------------------------------


def test_extra_text_query_field_is_included():
    key = unpublished_extra_field_name(set())
    value = unpublished_extra_field_value(set())
    totp = require_helper(call(TOTP, WRN3_SECRET, name=NAMED_ACCOUNT_EXAMPLE))
    totp_uri = require_uri(build_uri(totp, **{key: value}))
    require_query_includes(totp_uri, {key: value, "secret": WRN3_SECRET})
    assert key != "image"
    print(f"totp extra {key}={value!r}", flush=True)

    hmac = require_helper(call(HOTP, WRN3_SECRET, name=NAMED_ACCOUNT_EXAMPLE))
    hmac_uri = require_uri(build_uri(hmac, **{key: value}))
    require_query_includes(
        hmac_uri, {key: value, "secret": WRN3_SECRET, "counter": "0"}
    )
    print(f"hmac extra {key}={value!r}", flush=True)
