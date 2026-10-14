# feature: F05
"""Observation helpers for otpauth provisioning URI parsing (FP-05).

Helpers classify parse success (a usable helper) and parse refusal (no
helper). They never return ``None`` to mean "the observation could not
be classified". Named URIs and codes are fixed inputs of this suite.
HMAC / TOTP is never reimplemented here. Expected URI paths are never
produced with ``quote``.
"""

from __future__ import annotations

import secrets
from collections.abc import Collection
from urllib.parse import unquote

import F02_helpers as _f02
import F04_helpers as _f04
from _harness import CallResult, HarnessError, call

# GEZDGNBV totp SHA1 parse input and named rebuilds.
GEZDGNBV_TOTP_SHA1_URI = (
    "otpauth://totp/?algorithm=SHA1&secret=GEZDGNBV&algorithm=SHA1"
)
GEZDGNBV_SECRET_PLACEHOLDER_URI = "otpauth://totp/Secret?secret=GEZDGNBV"
GEZDGNBV_N_I_REBUILD_URI = "otpauth://totp/i:n?secret=GEZDGNBV&issuer=i"

# same skeleton with period=60.
GEZDGNBV_TOTP_PERIOD60_URI = (
    "otpauth://totp/?algorithm=SHA1&secret=GEZDGNBV&algorithm=SHA1&period=60"
)

# hotp GEZDGNBV parse inputs.
GEZDGNBV_HOTP_URI = (
    "otpauth://hotp/?algorithm=SHA1&secret=GEZDGNBV&algorithm=SHA1"
)
GEZDGNBV_HOTP_COUNTER1_URI = (
    "otpauth://hotp/?algorithm=SHA1&secret=GEZDGNBV&algorithm=SHA1&counter=1"
)

# last algorithm SHA256 / SHA512 parse inputs.
GEZDGNBV_TOTP_SHA256_URI = (
    "otpauth://totp/?algorithm=SHA1&secret=GEZDGNBV&algorithm=SHA256"
)
GEZDGNBV_TOTP_SHA512_URI = (
    "otpauth://totp/?algorithm=SHA1&secret=GEZDGNBV&algorithm=SHA512"
)

# image accepted and ignored.
GEZDGNBV_IMAGE_FOOBAR_URI = "otpauth://totp/?secret=GEZDGNBV&image=foobar"
GEZDGNBV_NO_IMAGE_URI = "otpauth://totp/?secret=GEZDGNBV"

# literal-colon vs encoded-colon labels.
FFFFF_SECRET = "FFFFFFFAAAAAABBBBBBB"
TEXT_COLON_URI = (
    "otpauth://totp/Text%3A%20More%20Text:Secret"
    "?secret=FFFFFFFAAAAAABBBBBBB&issuer=Text%3A%20More%20Text"
)
A_ENCODED_COLON_B_URI = "otpauth://totp/a%3Ab?secret=GEZDGNBV"
BIG_CORP_URI = (
    "otpauth://totp/Big%20Corp:bob?secret=GEZDGNBV&issuer=Big%20Corp"
)
TEXT_MORE_ISSUER = "Text: More Text"
ACCOUNT_A_COLON_B = "a:b"
ACCOUNT_BOB = "bob"
ISSUER_BIG_CORP = "Big Corp"

# Fixed refusal inputs.
HTTP_HELLO_URI = "http://hello.com"
OTPAUTH_TOTP_NO_SECRET_URI = "otpauth://totp/"
DERP_SECRET_URI = "otpauth://derp/?secret=foo"
DIGITS_MINUS_ONE_URI = "otpauth://totp/?digits=-1"
SOME_ANOTHER_ISSUER_URI = "otpauth://totp/SomeIssuer:?issuer=AnotherIssuer"
ALGORITHM_AES_URI = "otpauth://totp/?algorithm=aes"
NAMED_ISSUER_SOME = "SomeIssuer"
NAMED_ISSUER_ANOTHER = "AnotherIssuer"

# Fixed codes.
CODE_734055 = "734055"
CODE_662488 = "662488"
CODE_289363 = "289363"
CODE_918961 = "918961"
CODE_934470 = "934470"
CODE_816660 = "816660"
CODE_524153 = "524153"

NAMED_PARSE_UNIX = frozenset({0, 30, 60, 9000})
NAMED_PARSE_COUNTS = frozenset({0, 1, 2})
NAMED_PERIODS = frozenset({30, 60})
NAMED_URI_DIGITS = frozenset({6, 7, 8, -1})
NAMED_URI_ALGORITHMS = frozenset({"SHA1", "SHA256", "SHA512", "aes"})
NAMED_OTP_TYPES = frozenset({"totp", "hotp", "derp"})
NAMED_SCHEMES = frozenset({"otpauth", "http", "https"})

F05_NAMED_SECRETS = frozenset(set(_f04.NAMED_SECRETS) | {FFFFF_SECRET})
F05_NAMED_LABELS = frozenset(
    set(_f04.NAMED_LABELS)
    | {
        TEXT_MORE_ISSUER,
        ACCOUNT_A_COLON_B,
        ACCOUNT_BOB,
        ISSUER_BIG_CORP,
        NAMED_ISSUER_SOME,
        NAMED_ISSUER_ANOTHER,
        "foobar",
    }
)

_F05_BAND = 48
_F05_BAND_ORIGIN = 2000
_LETTER_BODY = "abcdefghjkmnpqrstuvwxyz"


def run_parse(parse_fn: object, uri: str) -> CallResult:
    """Drive the public provisioning-URI parser with one URI string."""
    if not isinstance(uri, str):
        raise HarnessError(
            f"run_parse uri is not text: type={type(uri).__name__}"
        )
    print(f"parse uri={uri!r}", flush=True)
    return call(parse_fn, uri)


def require_parse_refused(result: CallResult) -> None:
    """Require that the parse did not hand back a usable helper.

    A captured exception whose value is not a helper, or a return whose
    value is not a helper (including ``None`` / text / a number), both
    count. Handing back a usable helper does not. Exception class and
    message are not pinned. Emit and URI-build are never probed to
    interpret this outcome.
    """
    if result.exception is not None:
        if _f02._is_usable_helper(result.value):
            raise AssertionError(
                "parse reported a failure but still handed back a helper: "
                f"type={type(result.value).__name__}"
            )
        print(
            "parse refused; no helper returned "
            f"(carrier={type(result.exception).__name__})",
            flush=True,
        )
        return
    if _f02._is_usable_helper(result.value):
        raise AssertionError(
            "parse returned a usable helper; "
            f"type={type(result.value).__name__}"
        )
    print(
        "parse refused; no helper returned "
        f"(value_type={type(result.value).__name__} "
        f"value={_f04._value_prefix(result.value)})",
        flush=True,
    )


def label_from_rebuild(
    helper: object,
    expected_issuer: str | None,
    expected_account: str,
) -> tuple[str | None, str]:
    """Read account / issuer from a no-override rebuild URI.

    Returns ``(observed_issuer_or_none, decoded_path)``. Decoded path
    (leading ``/`` stripped, then unquoted) is compared by concatenating
    the expected issuer, a colon, and the expected account — the decoded
    path is never split on colon. Rebuild or parse failure raises;
    ``None`` is never returned to mean absence.
    """
    if not isinstance(expected_account, str) or not expected_account:
        raise HarnessError(
            "label_from_rebuild expected_account is not text: "
            f"{expected_account!r}"
        )
    uri = _f04.require_uri(_f04.build_uri(helper))
    parsed = _f04.parsed_otpauth(uri)
    raw_path = parsed.path
    stripped = raw_path[1:] if raw_path.startswith("/") else raw_path
    decoded = unquote(stripped)
    if expected_issuer is None:
        _f04.require_query_omits(uri, "issuer")
        if decoded != expected_account:
            raise AssertionError(
                "rebuilt path is not the expected account (no issuer): "
                f"expected={expected_account!r} decoded={decoded!r} "
                f"path={raw_path!r}"
            )
        print(
            f"label no-issuer account={expected_account!r} "
            f"decoded={decoded!r}",
            flush=True,
        )
        return (None, decoded)
    if not isinstance(expected_issuer, str) or not expected_issuer:
        raise HarnessError(
            "label_from_rebuild expected_issuer is not text: "
            f"{expected_issuer!r}"
        )
    query = _f04.require_query_includes(uri, {"issuer": expected_issuer})
    expected_decoded = expected_issuer + ":" + expected_account
    if decoded != expected_decoded:
        raise AssertionError(
            "rebuilt path is not issuer + colon + account: "
            f"expected={expected_decoded!r} decoded={decoded!r} "
            f"path={raw_path!r}"
        )
    print(
        f"label issuer={expected_issuer!r} account={expected_account!r} "
        f"decoded={decoded!r}",
        flush=True,
    )
    return (query["issuer"], decoded)


def round_trip_built_uri(
    parse_fn: object, helper: object, **build_kwargs: object
) -> tuple[str, object]:
    """Parse an FP-04-built URI and rebuild; require the same string."""
    built = _f04.require_uri(_f04.build_uri(helper, **build_kwargs))
    parsed = _f02.require_helper(run_parse(parse_fn, built))
    rebuilt = _f04.require_uri(_f04.build_uri(parsed))
    assert rebuilt == built, (
        "parse-then-rebuild is not the URI FP-04 just built: "
        f"built={built!r} rebuilt={rebuilt!r}"
    )
    print(f"round-trip ok length={len(built)}", flush=True)
    return built, parsed


def unpublished_period_gt_sixty(forbidden: Collection[int]) -> int:
    """Pick a time-step strictly greater than 60 (not 30, not 60)."""
    merged = set(forbidden) | set(NAMED_PERIODS)
    band = list(range(61, 61 + _f02._UNPUBLISHED_BAND + 16))
    chosen = _f02._pick_unpublished_int(
        band,
        merged,
        predicate=lambda n: type(n) is int and n > 60,
        label="unpublished_period_gt_sixty",
    )
    if chosen <= 60 or chosen in NAMED_PERIODS:
        raise HarnessError(
            "unpublished_period_gt_sixty is not greater than 60: "
            f"{chosen!r}"
        )
    return chosen


def unpublished_otp_type(forbidden: Collection[str]) -> str:
    """Pick a letter-only otpauth type other than totp / hotp / derp."""
    merged = set(forbidden) | set(NAMED_OTP_TYPES)
    suffix = _letter_suffix()
    band = [_letter_token("kind", n, suffix) for n in range(_F05_BAND)]
    chosen = _f04._pick_unpublished_text(
        band, merged, label="unpublished_otp_type"
    )
    if not chosen.isalpha() or chosen in NAMED_OTP_TYPES:
        raise HarnessError(
            f"unpublished_otp_type is not a usable letter type: {chosen!r}"
        )
    return chosen


def unpublished_non_otpauth_scheme(forbidden: Collection[str]) -> str:
    """Pick a letter-only scheme other than otpauth / http / https."""
    merged = set(forbidden) | set(NAMED_SCHEMES)
    suffix = _letter_suffix()
    band = [_letter_token("sch", n, suffix) for n in range(_F05_BAND)]
    chosen = _f04._pick_unpublished_text(
        band, merged, label="unpublished_non_otpauth_scheme"
    )
    if (
        not chosen.isalpha()
        or chosen in NAMED_SCHEMES
        or chosen.lower() in NAMED_SCHEMES
    ):
        raise HarnessError(
            "unpublished_non_otpauth_scheme is not a usable scheme: "
            f"{chosen!r}"
        )
    return chosen


def unpublished_illegal_digits(forbidden: Collection[int]) -> int:
    """Pick an integer digit count outside {6, 7, 8}, not the named −1."""
    merged = set(forbidden) | set(NAMED_URI_DIGITS)
    band = list(range(-25, 25))
    chosen = _f02._pick_unpublished_int(
        band,
        merged,
        predicate=lambda n: type(n) is int
        and n not in (6, 7, 8)
        and n != -1,
        label="unpublished_illegal_digits",
    )
    if chosen in (6, 7, 8, -1):
        raise HarnessError(
            f"unpublished_illegal_digits landed on a named count: {chosen!r}"
        )
    return chosen


def unpublished_illegal_algorithm(forbidden: Collection[str]) -> str:
    """Pick an algorithm token other than SHA1 / SHA256 / SHA512 / aes."""
    merged = set(forbidden) | set(NAMED_URI_ALGORITHMS)
    suffix = _letter_suffix()
    band = [_letter_token("alg", n, suffix) for n in range(_F05_BAND)]
    chosen = _f04._pick_unpublished_text(
        band, merged, label="unpublished_illegal_algorithm"
    )
    if chosen in NAMED_URI_ALGORITHMS or chosen.upper() in {
        "SHA1",
        "SHA256",
        "SHA512",
        "AES",
    }:
        raise HarnessError(
            "unpublished_illegal_algorithm landed on a named digest: "
            f"{chosen!r}"
        )
    return chosen


def unpublished_colon_issuer(forbidden: Collection[str]) -> str:
    """Alphanumeric + one literal colon + alphanumeric, not Text: More Text."""
    merged = set(forbidden) | set(F05_NAMED_LABELS)
    token = secrets.token_hex(2)
    band = [
        f"Col{_F05_BAND_ORIGIN + n:04d}{token}:Seg{n:02d}{token}"
        for n in range(_F05_BAND)
    ]
    chosen = _f04._pick_unpublished_text(
        band, merged, label="unpublished_colon_issuer"
    )
    if chosen.count(":") != 1 or chosen == TEXT_MORE_ISSUER:
        raise HarnessError(
            "unpublished_colon_issuer must contain exactly one colon "
            f"and avoid the named issuer: {chosen!r}"
        )
    left, right = chosen.split(":", 1)
    if not left.isalnum() or not right.isalnum():
        raise HarnessError(
            "unpublished_colon_issuer parts must be alphanumeric: "
            f"{chosen!r}"
        )
    return chosen


def _letter_suffix() -> str:
    rng = secrets.SystemRandom()
    return "".join(rng.choice(_LETTER_BODY) for _ in range(6))


def _letter_token(prefix: str, n: int, suffix: str) -> str:
    first = _LETTER_BODY[n % len(_LETTER_BODY)]
    second = _LETTER_BODY[(n // len(_LETTER_BODY)) % len(_LETTER_BODY)]
    return f"{prefix}{first}{second}{suffix}"
