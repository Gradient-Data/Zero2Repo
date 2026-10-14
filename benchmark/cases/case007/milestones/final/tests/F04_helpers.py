# feature: F04
"""Observation helpers for otpauth provisioning URI generation (FP-04).

Helpers classify URI-build success and refusal. They never return
``None`` to mean "the observation could not be classified". Named URIs,
paths, and query spellings are fixed inputs of this suite. Percent
encoding is never mirrored with ``quote`` / ``urlencode``.
"""

from __future__ import annotations

import secrets
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, unquote, urlparse

import F02_helpers as _f02
from _harness import CallResult, HarnessError, call_method

# Public URI-build entry on HMAC / time helpers (interface name).
URI_BUILD_ENTRY = "provisioning_uri"

# README URIs for secret JBSWY3DPEHPK3PXP.
JBSWY_SECRET = "JBSWY3DPEHPK3PXP"
README_TOTP_URI = (
    "otpauth://totp/Secure%20App:alice%40google.com"
    "?secret=JBSWY3DPEHPK3PXP&issuer=Secure%20App"
)
README_HOTP_URI = (
    "otpauth://hotp/Secure%20App:alice%40google.com"
    "?secret=JBSWY3DPEHPK3PXP&issuer=Secure%20App&counter=0"
)

# no-account Secret URI.
S46_SECRET = "S46SQCPPTCNPROMHWYBDCTBZXV"
SECRET_PLACEHOLDER_URI = (
    "otpauth://totp/Secret?secret=S46SQCPPTCNPROMHWYBDCTBZXV"
)
SECRET_PLACEHOLDER = "Secret"

# eight-digit SHA256 FooCorp row.
C7UXU_SECRET = "c7uxuqhgflpw7oruedmglbrk7u6242vb"

# SHA512 image URI.
NAMED_IMAGE_URL = "https://test.net/test.png"
SHA512_IMAGE_URI = (
    "otpauth://totp/i:n?secret=GEZDGNBV&issuer=i"
    "&algorithm=SHA512&image=https%3A%2F%2Ftest.net%2Ftest.png"
)

# named failed-check candidate.
NAMED_FAILED_CANDIDATE = "123456"

# named paths (leading slash, encoded).
PATH_ALICE_EXAMPLE = "/alice%40example.com"
PATH_FOOCORP_BANG_ALICE = "/FooCorp%21:alice%40example.com"
PATH_FOOCORP_BACO = "/FooCorp:baco%40peperina"

# named accounts and issuers.
NAMED_ACCOUNT_GOOGLE = "alice@google.com"
NAMED_ACCOUNT_EXAMPLE = "alice@example.com"
NAMED_ACCOUNT_BACO = "baco@peperina"
NAMED_ACCOUNT_N = "n"
NAMED_ISSUER_SECURE_APP = "Secure App"
NAMED_ISSUER_FOOCORP_BANG = "FooCorp!"
NAMED_ISSUER_FOOCORP = "FooCorp"
NAMED_ISSUER_I = "i"

NAMED_LABELS = frozenset(
    {
        SECRET_PLACEHOLDER,
        NAMED_ACCOUNT_GOOGLE,
        NAMED_ACCOUNT_EXAMPLE,
        NAMED_ACCOUNT_BACO,
        NAMED_ACCOUNT_N,
        NAMED_ISSUER_SECURE_APP,
        NAMED_ISSUER_FOOCORP_BANG,
        NAMED_ISSUER_FOOCORP,
        NAMED_ISSUER_I,
    }
)

NAMED_SECRETS = frozenset(
    {
        _f02.WRN3_SECRET,
        _f02.GEZDGNBV_SECRET,
        JBSWY_SECRET,
        S46_SECRET,
        C7UXU_SECRET,
    }
)
NAMED_SECRET_LENGTHS = frozenset(len(secret) for secret in NAMED_SECRETS)

# Query field names; extra-field picker must not land on these.
RESERVED_QUERY_KEYS = frozenset(
    {"secret", "issuer", "counter", "digits", "period", "algorithm", "image"}
)

# Fixed illegal image value.
NAMED_ILLEGAL_IMAGE = "nourl"

# Encodings of @, ! and space.
AT_ENCODED = "%40"
BANG_ENCODED = "%21"
SPACE_ENCODED = "%20"

# URI digit-count set includes 7.
UNPUBLISHED_DIGIT_SEVEN = 7

_BASE32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
_LABEL_BAND_ORIGIN = 1000
_LABEL_BAND = 48


@dataclass(frozen=True)
class ParsedOtpauth:
    """One parsed otpauth URI. Empty query is a real empty mapping."""

    scheme: str
    otp_type: str
    path: str
    query: dict[str, str]
    raw_query: str


def build_uri(helper: object, **kwargs: Any) -> CallResult:
    """Drive the public provisioning-URI builder on *helper*."""
    return call_method(helper, URI_BUILD_ENTRY, **kwargs)


def _value_prefix(value: Any, limit: int = 160) -> str:
    text = repr(value)
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def _as_otpauth_text(value: Any) -> str | None:
    """Return *value* when it is an otpauth URI string; else ``None``.

    ``None`` here means "not an otpauth URI", a classified observation,
    not a failed lookup.
    """
    if not isinstance(value, str):
        return None
    try:
        parsed = urlparse(value)
    except Exception:
        return None
    if parsed.scheme != "otpauth":
        return None
    return value


def require_uri(result: CallResult) -> str:
    """Return a successful otpauth URI (scheme otpauth, text, returned)."""
    if result.exception is not None:
        raise AssertionError(
            "URI build raised; there is no otpauth URI to observe: "
            f"carrier={type(result.exception).__name__} "
            f"value={_value_prefix(result.value)}"
        )
    value = result.value
    if not isinstance(value, str):
        raise AssertionError(
            "URI build did not return text: "
            f"type={type(value).__name__} value={_value_prefix(value)}"
        )
    try:
        parsed = urlparse(value)
    except Exception as exc:
        raise AssertionError(
            "URI build returned text that could not be parsed as a URI: "
            f"value={_value_prefix(value)} error={exc!r}"
        ) from exc
    if parsed.scheme != "otpauth":
        raise AssertionError(
            "URI build returned text whose scheme is not otpauth: "
            f"scheme={parsed.scheme!r} value={_value_prefix(value)}"
        )
    print(
        f"uri ok scheme={parsed.scheme!r} type={parsed.netloc!r} "
        f"path={parsed.path!r} query_len={len(parsed.query)}",
        flush=True,
    )
    return value


def require_named_uri(result: CallResult, expected: str) -> str:
    """Return a URI that equals a suite-named string (after scheme/type)."""
    if not isinstance(expected, str) or not expected:
        raise HarnessError(
            f"require_named_uri expected is not a named URI: {expected!r}"
        )
    uri = require_uri(result)
    assert uri == expected, (
        "built URI is not the named string: "
        f"expected={expected!r} got={uri!r}"
    )
    print(f"named uri ok expected={expected!r}", flush=True)
    return uri


def require_build_refused(result: CallResult) -> None:
    """Require that the build did not hand back an otpauth URI.

    A captured exception whose value is not otpauth text, or a return
    whose value is not otpauth text (including ``None`` / non-text /
    wrong scheme), both count. Returning an otpauth string does not.
    Exception class and message are not pinned. Other entries are never
    probed to interpret this outcome.
    """
    handed = _as_otpauth_text(result.value)
    if handed is not None:
        raise AssertionError(
            "URI build still handed back an otpauth URI: "
            f"{_value_prefix(handed)}"
        )
    if result.exception is not None:
        print(
            "URI build refused; no otpauth URI returned "
            f"(carrier={type(result.exception).__name__})",
            flush=True,
        )
        return
    print(
        "URI build refused; no otpauth URI returned "
        f"(value_type={type(result.value).__name__} "
        f"value={_value_prefix(result.value)})",
        flush=True,
    )


def parsed_otpauth(uri: str) -> ParsedOtpauth:
    """Parse one otpauth URI. Failure raises — never an empty mapping."""
    if not isinstance(uri, str):
        raise HarnessError(
            f"parsed_otpauth expected text; got {type(uri).__name__}"
        )
    try:
        parsed = urlparse(uri)
    except Exception as exc:
        raise HarnessError(
            f"parsed_otpauth cannot parse URI {_value_prefix(uri)}: {exc}"
        ) from exc
    if parsed.scheme != "otpauth":
        raise HarnessError(
            "parsed_otpauth scheme is not otpauth: "
            f"scheme={parsed.scheme!r} value={_value_prefix(uri)}"
        )
    try:
        pairs = parse_qsl(parsed.query, keep_blank_values=True)
    except Exception as exc:
        raise HarnessError(
            "parsed_otpauth cannot parse query "
            f"{parsed.query!r}: {exc}"
        ) from exc
    query: dict[str, str] = {}
    for key, value in pairs:
        query[key] = value
    observed = ParsedOtpauth(
        scheme=parsed.scheme,
        otp_type=parsed.netloc,
        path=parsed.path,
        query=query,
        raw_query=parsed.query,
    )
    print(
        f"parsed scheme={observed.scheme!r} type={observed.otp_type!r} "
        f"path={observed.path!r} keys={sorted(observed.query)}",
        flush=True,
    )
    return observed


def require_path(uri: str, expected: str) -> str:
    """Require ``urlparse(uri).path`` equals a named path (leading slash)."""
    if not isinstance(expected, str) or not expected.startswith("/"):
        raise HarnessError(
            f"require_path expected is not a named path: {expected!r}"
        )
    parsed = parsed_otpauth(uri)
    assert parsed.path == expected, (
        "URI path is not the named path: "
        f"expected={expected!r} got={parsed.path!r}"
    )
    print(f"path ok expected={expected!r}", flush=True)
    return parsed.path


def require_query_includes(uri: str, mapping: Mapping[str, str]) -> dict[str, str]:
    """Require decoded query keys exist with the named string values."""
    if not mapping:
        raise HarnessError("require_query_includes mapping is empty")
    parsed = parsed_otpauth(uri)
    missing: list[str] = []
    mismatched: list[str] = []
    for key, expected in mapping.items():
        if not isinstance(expected, str):
            raise HarnessError(
                "require_query_includes values must be text "
                f"(key={key!r} type={type(expected).__name__})"
            )
        if key not in parsed.query:
            missing.append(key)
            continue
        actual = parsed.query[key]
        if actual != expected:
            mismatched.append(
                f"{key!r}: expected={expected!r} got={actual!r}"
            )
    if missing or mismatched:
        raise AssertionError(
            "decoded query does not include the named fields: "
            f"missing={missing!r} mismatched={mismatched!r} "
            f"actual_keys={sorted(parsed.query)}"
        )
    print(
        f"query includes {sorted(mapping)}",
        flush=True,
    )
    return parsed.query


def require_query_omits(uri: str, *keys: str) -> dict[str, str]:
    """Require decoded query lacks *keys* after a successful URI.

    Secret must still be present (success carrier). Presence of a named
    default key fails — that is "defaults still written".
    """
    if not keys:
        raise HarnessError("require_query_omits requires at least one key")
    parsed = parsed_otpauth(uri)
    if "secret" not in parsed.query:
        raise AssertionError(
            "URI has no secret query field; omission cannot be observed "
            f"on a successful build: keys={sorted(parsed.query)}"
        )
    present = [key for key in keys if key in parsed.query]
    if present:
        shown = {key: parsed.query[key] for key in present}
        raise AssertionError(
            "default query fields were written: "
            f"{shown!r} keys={sorted(parsed.query)}"
        )
    print(f"query omits {list(keys)}", flush=True)
    return parsed.query


def require_space_encoded_not_plus(uri: str, text: str) -> None:
    """Require a space in *text* is `%20` in the raw URI, not `+`."""
    if not isinstance(text, str) or " " not in text:
        raise HarnessError(
            f"require_space_encoded_not_plus text has no space: {text!r}"
        )
    plus_form = text.replace(" ", "+")
    assert SPACE_ENCODED in uri, (
        "raw URI does not contain %20 for a space in the label/query: "
        f"text={text!r} uri={uri!r}"
    )
    assert plus_form not in uri, (
        "raw URI wrote a space as plus instead of %20: "
        f"text={text!r} plus_form={plus_form!r} uri={uri!r}"
    )
    parsed = parsed_otpauth(uri)
    decoded_path = unquote(parsed.path)
    decoded_blobs = [decoded_path, *parsed.query.values()]
    if not any(text in blob for blob in decoded_blobs):
        raise AssertionError(
            "decoded path/query does not contain the spaced text: "
            f"text={text!r} path={decoded_path!r} "
            f"query={parsed.query!r}"
        )
    print(
        f"space encoded as %20 not plus text={text!r}",
        flush=True,
    )


def require_at_encoded_in_path(uri: str, account: str) -> None:
    """Require `@` in *account* is `%40` in the path, not a bare `@`."""
    if not isinstance(account, str) or "@" not in account:
        raise HarnessError(
            f"require_at_encoded_in_path account has no @: {account!r}"
        )
    parsed = parsed_otpauth(uri)
    assert AT_ENCODED in parsed.path, (
        "path does not contain %40 for an @ in the account: "
        f"account={account!r} path={parsed.path!r}"
    )
    assert "@" not in parsed.path, (
        "path still contains an unencoded @: "
        f"account={account!r} path={parsed.path!r}"
    )
    decoded_path = unquote(parsed.path)
    assert account in decoded_path, (
        "decoded path does not contain the account: "
        f"account={account!r} decoded_path={decoded_path!r}"
    )
    print(f"at encoded as %40 account={account!r}", flush=True)


def require_bang_encoded(uri: str, issuer: str) -> None:
    """Require `!` in *issuer* is `%21` in path and raw query."""
    if not isinstance(issuer, str) or "!" not in issuer:
        raise HarnessError(
            f"require_bang_encoded issuer has no !: {issuer!r}"
        )
    parsed = parsed_otpauth(uri)
    assert BANG_ENCODED in parsed.path, (
        "path does not contain %21 for an ! in the issuer: "
        f"issuer={issuer!r} path={parsed.path!r}"
    )
    assert "!" not in parsed.path, (
        "path still contains a bare !: "
        f"issuer={issuer!r} path={parsed.path!r}"
    )
    decoded_path = unquote(parsed.path)
    assert issuer in decoded_path, (
        "decoded path does not contain the issuer: "
        f"issuer={issuer!r} decoded_path={decoded_path!r}"
    )
    require_query_includes(uri, {"issuer": issuer})
    assert BANG_ENCODED in parsed.raw_query, (
        "raw query does not contain %21 for an ! in the issuer: "
        f"issuer={issuer!r} raw_query={parsed.raw_query!r}"
    )
    assert "!" not in parsed.raw_query, (
        "raw query still contains a bare !: "
        f"issuer={issuer!r} raw_query={parsed.raw_query!r}"
    )
    print(f"bang encoded as %21 issuer={issuer!r}", flush=True)


def require_image_query(uri: str, url: str) -> None:
    """Require decoded ``image`` equals *url* and raw query has no `://`."""
    if not isinstance(url, str) or not url:
        raise HarnessError(f"require_image_query url is not text: {url!r}")
    parsed = parsed_otpauth(uri)
    require_query_includes(uri, {"image": url})
    assert "://" not in parsed.raw_query, (
        "raw query still contains an unencoded :// for the image URL: "
        f"url={url!r} raw_query={parsed.raw_query!r}"
    )
    print(f"image query encoded url={url!r}", flush=True)


def _pick_unpublished_text(
    band: list[str],
    forbidden: Collection[str],
    *,
    label: str,
) -> str:
    if not band:
        raise HarnessError(f"{label}: empty selection band")
    forbidden_set = set(forbidden)
    eligible = [item for item in band if item not in forbidden_set]
    if len(eligible) < _f02._UNPUBLISHED_MIN_ELIGIBLE:
        raise HarnessError(
            f"{label} band has {len(eligible)} eligible strings; "
            f"need at least {_f02._UNPUBLISHED_MIN_ELIGIBLE} "
            f"(forbidden={sorted(forbidden_set)!r})"
        )
    skip = _f02._UNPUBLISHED_SKIP_PREFIX
    if len(eligible) - skip < 1:
        raise HarnessError(
            f"{label} pool after skipping the prefix is empty: "
            f"eligible={len(eligible)} skip={skip}"
        )
    pool = eligible[skip:]
    chosen = secrets.SystemRandom().choice(pool)
    if chosen in forbidden_set:
        raise HarnessError(
            f"{label} produced a named value: {chosen!r} "
            f"(forbidden={sorted(forbidden_set)!r})"
        )
    print(f"{label} chosen={chosen!r}", flush=True)
    return chosen


def unpublished_label(forbidden: Collection[str]) -> str:
    """Pick an alphanumeric label avoiding named accounts / issuers / Secret."""
    merged = set(forbidden) | set(NAMED_LABELS)
    token = secrets.token_hex(2)
    band = [
        f"Acct{_LABEL_BAND_ORIGIN + n:04d}{token}" for n in range(_LABEL_BAND)
    ]
    chosen = _pick_unpublished_text(
        band, merged, label="unpublished_label"
    )
    if not chosen.isalnum() or chosen in NAMED_LABELS:
        raise HarnessError(
            f"unpublished_label is not a usable alphanumeric label: {chosen!r}"
        )
    return chosen


def unpublished_label_with(forbidden: Collection[str], extra_char: str) -> str:
    """Alphanumeric body plus exactly one *extra_char* (`!`, space, or `@`)."""
    if extra_char not in ("!", " ", "@"):
        raise HarnessError(
            f"unpublished_label_with extra_char is not ! / space / @: "
            f"{extra_char!r}"
        )
    merged = set(forbidden) | set(NAMED_LABELS)
    token = secrets.token_hex(2)
    bodies = [
        f"Lbl{_LABEL_BAND_ORIGIN + n:04d}{token}" for n in range(_LABEL_BAND)
    ]
    tails = [f"Zz{n:02d}{token}" for n in range(_LABEL_BAND)]
    band = [f"{body}{extra_char}{tail}" for body, tail in zip(bodies, tails)]
    chosen = _pick_unpublished_text(
        band, merged, label=f"unpublished_label_with[{extra_char!r}]"
    )
    if chosen.count(extra_char) != 1:
        raise HarnessError(
            "unpublished_label_with did not contain exactly one "
            f"extra_char={extra_char!r}: {chosen!r}"
        )
    if chosen in NAMED_LABELS:
        raise HarnessError(
            f"unpublished_label_with landed on a named label: {chosen!r}"
        )
    return chosen


def unpublished_base32_secret(forbidden: Collection[str]) -> str:
    """Pick a base32 secret whose length is not any named secret's length.

    Length must also be one the product can decode after it restores
    ``=`` padding (remainder 0, 2, 4, 5, or 7). Remainder 1, 3, or 6
    is not a usable secret: emit/check then fail with padding errors,
    which is not an unpublished-secret observation.
    """
    merged_secrets = set(forbidden) | set(NAMED_SECRETS)
    length_band = list(range(10, 10 + _f02._UNPUBLISHED_BAND + 16))

    def _usable_unpublished_secret_length(n: object) -> bool:
        if type(n) is not int or n < 10 or n in NAMED_SECRET_LENGTHS:
            return False
        return n % 8 in {0, 2, 4, 5, 7}

    length = _f02._pick_unpublished_int(
        length_band,
        NAMED_SECRET_LENGTHS,
        predicate=_usable_unpublished_secret_length,
        label="unpublished_base32_secret_length",
    )
    rng = secrets.SystemRandom()
    chosen = "".join(rng.choice(_BASE32_ALPHABET) for _ in range(length))
    if (
        len(chosen) in NAMED_SECRET_LENGTHS
        or chosen in merged_secrets
        or any(ch not in _BASE32_ALPHABET for ch in chosen)
        or len(chosen) % 8 not in {0, 2, 4, 5, 7}
    ):
        raise HarnessError(
            "unpublished_base32_secret produced a named secret or "
            f"illegal alphabet: length={len(chosen)} value={chosen!r}"
        )
    print(
        f"unpublished_base32_secret length={len(chosen)}",
        flush=True,
    )
    return chosen


def unpublished_extra_field_name(forbidden: Collection[str]) -> str:
    """Pick a query key that is not a reserved otpauth field name."""
    merged = set(forbidden) | set(RESERVED_QUERY_KEYS)
    token = secrets.token_hex(2)
    band = [
        f"fld{_LABEL_BAND_ORIGIN + n:04d}{token}" for n in range(_LABEL_BAND)
    ]
    chosen = _pick_unpublished_text(
        band, merged, label="unpublished_extra_field_name"
    )
    if chosen in RESERVED_QUERY_KEYS:
        raise HarnessError(
            f"unpublished_extra_field_name landed on a reserved key: {chosen!r}"
        )
    return chosen


def unpublished_extra_field_value(forbidden: Collection[str]) -> str:
    """Pick unpublished text for an extra query field value."""
    merged = set(forbidden)
    token = secrets.token_hex(2)
    band = [
        f"val{_LABEL_BAND_ORIGIN + n:04d}{token}" for n in range(_LABEL_BAND)
    ]
    return _pick_unpublished_text(
        band, merged, label="unpublished_extra_field_value"
    )


def unpublished_https_image_url(forbidden: Collection[str]) -> str:
    """Pick an https URL with host and path, not the named PNG URL."""
    merged = set(forbidden) | {NAMED_IMAGE_URL}
    token = secrets.token_hex(2)
    band = [
        f"https://img{_LABEL_BAND_ORIGIN + n}.example.net/p/{token}/{n}.png"
        for n in range(_LABEL_BAND)
    ]
    chosen = _pick_unpublished_text(
        band, merged, label="unpublished_https_image_url"
    )
    parsed = urlparse(chosen)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or not parsed.path
        or not parsed.path.startswith("/")
        or chosen == NAMED_IMAGE_URL
    ):
        raise HarnessError(
            "unpublished_https_image_url is not a usable https URL "
            f"with host and path: {chosen!r}"
        )
    return chosen


def unpublished_no_scheme_image_token(forbidden: Collection[str]) -> str:
    """Pick a no-scheme token that is not the named `nourl` example."""
    merged = set(forbidden) | {NAMED_ILLEGAL_IMAGE}
    token = secrets.token_hex(2)
    band = [
        f"imgToken{_LABEL_BAND_ORIGIN + n:04d}{token}"
        for n in range(_LABEL_BAND)
    ]
    chosen = _pick_unpublished_text(
        band, merged, label="unpublished_no_scheme_image_token"
    )
    parsed = urlparse(chosen)
    if parsed.scheme or chosen == NAMED_ILLEGAL_IMAGE:
        raise HarnessError(
            "unpublished_no_scheme_image_token has a scheme or is nourl: "
            f"{chosen!r} scheme={parsed.scheme!r}"
        )
    return chosen


def unpublished_wrong_scheme_image_url(forbidden: Collection[str]) -> str:
    """http URL that still has host and path (image-rule conjunction)."""
    merged = set(forbidden) | {NAMED_ILLEGAL_IMAGE, NAMED_IMAGE_URL}
    token = secrets.token_hex(2)
    band = [
        f"http://img{_LABEL_BAND_ORIGIN + n}.example.net/p/{token}/{n}.png"
        for n in range(_LABEL_BAND)
    ]
    chosen = _pick_unpublished_text(
        band, merged, label="unpublished_wrong_scheme_image_url"
    )
    parsed = urlparse(chosen)
    if parsed.scheme == "https" or not parsed.netloc or not parsed.path:
        raise HarnessError(
            "unpublished_wrong_scheme_image_url is not a non-https "
            f"URL with host and path: {chosen!r}"
        )
    return chosen


def unpublished_https_image_missing_path(forbidden: Collection[str]) -> str:
    """https URL with host and empty path (image-rule conjunction)."""
    merged = set(forbidden) | {NAMED_ILLEGAL_IMAGE, NAMED_IMAGE_URL}
    token = secrets.token_hex(2)
    band = [
        f"https://img{_LABEL_BAND_ORIGIN + n}{token}.example.net"
        for n in range(_LABEL_BAND)
    ]
    chosen = _pick_unpublished_text(
        band, merged, label="unpublished_https_image_missing_path"
    )
    parsed = urlparse(chosen)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path:
        raise HarnessError(
            "unpublished_https_image_missing_path is not https+host "
            f"with empty path: {chosen!r} path={parsed.path!r}"
        )
    return chosen


def unpublished_https_image_missing_host(forbidden: Collection[str]) -> str:
    """https URL with path and empty host (image-rule conjunction)."""
    merged = set(forbidden) | {NAMED_ILLEGAL_IMAGE, NAMED_IMAGE_URL}
    token = secrets.token_hex(2)
    band = [
        f"https:///p/{token}/{_LABEL_BAND_ORIGIN + n}.png"
        for n in range(_LABEL_BAND)
    ]
    chosen = _pick_unpublished_text(
        band, merged, label="unpublished_https_image_missing_host"
    )
    parsed = urlparse(chosen)
    if parsed.scheme != "https" or parsed.netloc or not parsed.path:
        raise HarnessError(
            "unpublished_https_image_missing_host is not https+path "
            f"with empty host: {chosen!r} netloc={parsed.netloc!r}"
        )
    return chosen


def unpublished_period_seconds(forbidden: Collection[int]) -> int:
    """Pick a positive time-step that is not 30 and not 60."""
    merged = set(forbidden) | {30, 60}
    band = list(range(1, 1 + _f02._UNPUBLISHED_BAND + 16))
    return _f02._pick_unpublished_int(
        band,
        merged,
        predicate=lambda n: type(n) is int and n > 0 and n not in (30, 60),
        label="unpublished_period_seconds",
    )
