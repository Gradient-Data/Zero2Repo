# feature: F04
"""Observation helpers for URL-safe serialize-and-sign tokens (FP-04).

Helpers classify dump / load outcomes of the URL-safe helper and the
URL-safe timestamped helper. They never return ``None`` to mean "the
observation could not be classified".
"""

from __future__ import annotations

import string
from typing import Any

from _harness import (
    CallResult,
    HarnessError,
    call,
    require_value,
)
from F01_helpers import runtime_ascii_letter
from F02_helpers import (
    matching_signer,
    payload_section,
    sign_with_matching_signer,
    signature_section,
    signed_garbage_token,
    join_payload_and_signature,
)
from F03_helpers import require_distinct_failure_kinds

PUBLIC_README_SECRET = "secret key"
PUBLIC_README_SALT = "auth"
PUBLIC_README_NAME = "signtoken"
PUBLIC_README_MAPPING = {"id": 5, "name": PUBLIC_README_NAME}
PUBLIC_INTEGER_LIST = [1, 2, 3, 4]
THOUSAND_A = "a" * 1000
COMPRESSION_LENGTH_LIMIT = 1000
CROSS_LOAD_SECRET = "secret-key"
SIGNED_LETTER_A_PAYLOAD = b"A"
SIGNED_PERIOD_EIGHT_A_PAYLOAD = b".AAAAAAAA"
URLSAFE_ALPHABET = frozenset(string.ascii_letters + string.digits + "_-.")
FORBIDDEN_URLSAFE_CHARS = ("+", "/", "=", " ", "[", "]", '"', "'")


def load_urlsafe_surface() -> Any:
    """Import the URL-safe serialize-and-sign helper from the package root.

    Import happens here, not at module import time, so construction is
    observed through ``construct_urlsafe_helper``.
    """
    from signtoken import URLSafeSerializer

    if not callable(URLSafeSerializer):
        raise HarnessError(
            f"URLSafeSerializer is not callable; got {type(URLSafeSerializer)!r}"
        )
    return URLSafeSerializer


def load_urlsafe_timestamped_surface() -> Any:
    """Import the URL-safe timestamped helper from the package root."""
    from signtoken import URLSafeTimedSerializer

    if not callable(URLSafeTimedSerializer):
        raise HarnessError(
            "URLSafeTimedSerializer is not callable; "
            f"got {type(URLSafeTimedSerializer)!r}"
        )
    return URLSafeTimedSerializer


def construct_urlsafe_helper(*args: Any, **kwargs: Any) -> CallResult:
    return call(load_urlsafe_surface(), *args, **kwargs)


def construct_urlsafe_timestamped_helper(*args: Any, **kwargs: Any) -> CallResult:
    return call(load_urlsafe_timestamped_surface(), *args, **kwargs)


def make_urlsafe_helper(*args: Any, **kwargs: Any) -> Any:
    helper = require_value(construct_urlsafe_helper(*args, **kwargs))
    print(
        f"constructed URL-safe helper args={args!r} kwargs={list(kwargs)!r}",
        flush=True,
    )
    return helper


def make_urlsafe_timestamped_helper(*args: Any, **kwargs: Any) -> Any:
    helper = require_value(construct_urlsafe_timestamped_helper(*args, **kwargs))
    print(
        f"constructed URL-safe timestamped helper args={args!r} "
        f"kwargs={list(kwargs)!r}",
        flush=True,
    )
    return helper


def require_urlsafe_text_token(token: Any) -> str:
    """Require *token* is text using only the URL-safe alphabet.

    Raises if the token is bytes (or any non-text) — never flattens
    bytes into text. Named forbidden characters are asserted explicitly.
    """
    if not isinstance(token, str):
        raise AssertionError(
            "URL-safe token must be text, not "
            f"{type(token).__name__}: {token!r}"
        )
    extras = sorted({ch for ch in token if ch not in URLSAFE_ALPHABET})
    if extras:
        raise AssertionError(
            "URL-safe token contains characters outside the alphabet "
            f"{extras!r}; token={token!r}"
        )
    for ch in FORBIDDEN_URLSAFE_CHARS:
        if ch in token:
            raise AssertionError(
                "URL-safe token contains forbidden character "
                f"{ch!r}; token={token!r}"
            )
    print(
        f"urlsafe text token len={len(token)} alphabet_ok",
        flush=True,
    )
    return token


def _payload_section_value(token: Any) -> str | bytes:
    """Payload section of a text or bytes token. Raises if it cannot be cut."""
    if not isinstance(token, (str, bytes)):
        raise HarnessError(
            "payload-section observation requires text or bytes; "
            f"got {type(token).__name__}"
        )
    section = payload_section(token)
    if not isinstance(section, (str, bytes)):
        raise HarnessError(
            "payload_section did not return text or bytes; "
            f"got {type(section).__name__}: {section!r}"
        )
    if not section:
        raise HarnessError("payload section is empty; cannot classify compression")
    return section


def require_compressed_payload_section(token: Any) -> str | bytes:
    """Require the payload section begins with a period."""
    section = _payload_section_value(token)
    if isinstance(section, bytes):
        ok = section.startswith(b".")
    else:
        ok = section.startswith(".")
    if not ok:
        raise AssertionError(
            "compressed payload section must begin with a period; "
            f"section_prefix={section[:24]!r}"
        )
    print(
        f"compressed payload section len={len(section)} leading_period",
        flush=True,
    )
    return section


def require_uncompressed_payload_section(token: Any) -> str | bytes:
    """Require the payload section does not begin with a period."""
    section = _payload_section_value(token)
    if isinstance(section, bytes):
        leading = section.startswith(b".")
    else:
        leading = section.startswith(".")
    if leading:
        raise AssertionError(
            "uncompressed payload section must not begin with a period; "
            f"section_prefix={section[:24]!r}"
        )
    print(
        f"uncompressed payload section len={len(section)} no_leading_period",
        flush=True,
    )
    return section


def uppercase_signature_letters(token: Any) -> str:
    """Uppercase letters in the signature section; keep the payload intact.

    Full-token uppercasing of a URL-safe token also rewrites the
    URL-safe encoding of the payload (the alphabet is case-sensitive).
    Holding the payload section fixed isolates the signature-mismatch
    refusal from that encoding covariate. Raises if *token* is not text
    or the transform is a no-op — never returns a sentinel.
    """
    if not isinstance(token, str):
        raise AssertionError(
            "uppercase-signature observation requires a text token; "
            f"got {type(token).__name__}: {token!r}"
        )
    payload = payload_section(token)
    signature = signature_section(token)
    if not isinstance(payload, str) or not isinstance(signature, str):
        raise HarnessError(
            "payload_section/signature_section did not return text; "
            f"payload={type(payload).__name__} "
            f"signature={type(signature).__name__}"
        )
    if not signature:
        raise AssertionError(
            f"cannot uppercase an empty signature section; token={token!r}"
        )
    changed_sig = signature.upper()
    if changed_sig == signature:
        raise AssertionError(
            f"uppercasing the signature section was a no-op on {token!r}"
        )
    joined = join_payload_and_signature(payload, changed_sig)
    if not isinstance(joined, str):
        raise HarnessError(
            "rejoined token is not text; "
            f"got {type(joined).__name__}: {joined!r}"
        )
    if joined == token:
        raise AssertionError(
            f"uppercasing the signature section was a no-op on {token!r}"
        )
    print(
        f"uppercased signature letters payload_len={len(payload)} "
        f"sig_len={len(signature)}",
        flush=True,
    )
    return joined


def require_shorter_than(
    token: Any, limit: int = COMPRESSION_LENGTH_LIMIT
) -> str:
    """Require a text token shorter than *limit* characters."""
    text = require_urlsafe_text_token(token)
    if len(text) >= limit:
        raise AssertionError(
            f"token length {len(text)} is not shorter than {limit} characters"
        )
    print(f"token length {len(text)} < {limit}", flush=True)
    return text


def require_readme_mapping(loaded: Any) -> Any:
    """Require *loaded* recovers the README mapping (id equals 5, named name).

    Equality only — does not pin ``id`` to a Python ``int`` type.
    Lookup failure raises; it is never treated as a missing key.
    """
    try:
        ident = loaded["id"]
        name = loaded["name"]
    except Exception as exc:
        raise AssertionError(
            f"cannot read id/name from loaded object {loaded!r}: {exc}"
        ) from exc
    if ident != 5:
        raise AssertionError(f"mapping id is {ident!r}, expected 5")
    if name != PUBLIC_README_NAME:
        raise AssertionError(
            f"mapping name is {name!r}, expected {PUBLIC_README_NAME!r}"
        )
    print(
        f"readme mapping id={ident!r} name={name!r}",
        flush=True,
    )
    return loaded


def require_id_equals(loaded: Any, ident: Any) -> Any:
    """Require *loaded* exposes ``id`` equal to *ident* (no type pin)."""
    try:
        value = loaded["id"]
    except Exception as exc:
        raise AssertionError(
            f"cannot read id from loaded object {loaded!r}: {exc}"
        ) from exc
    if value != ident:
        raise AssertionError(f"mapping id is {value!r}, expected {ident!r}")
    print(f"mapping id equals {ident!r} (got {value!r})", flush=True)
    return loaded


def repeated_letter(ch: str, n: int = 1000) -> str:
    """Repeat a single character *n* times. Raises if *ch* is not one letter."""
    if not isinstance(ch, str) or len(ch) != 1:
        raise HarnessError(
            f"repeated letter must be a single character; got {ch!r}"
        )
    if n < 1:
        raise HarnessError(f"repeat count must be positive; got {n!r}")
    return ch * n


def runtime_letter_other_than_a() -> str:
    """Sample an ASCII letter that is not ``a``. Raises if none can be drawn."""
    for _ in range(32):
        ch = runtime_ascii_letter()
        if ch != "a":
            print(f"runtime letter other than a: {ch!r}", flush=True)
            return ch
    raise HarnessError("could not sample an ASCII letter other than 'a'")


def _sign_garbage_payload(
    payload: str | bytes, secret: str | bytes, salt: str | bytes | None = None
) -> bytes:
    """Sign *payload* with an F01 signer matching *secret* and optional *salt*."""
    if salt is None:
        signer = matching_signer(secret)
        token = sign_with_matching_signer(signer, payload)
    else:
        token = signed_garbage_token(payload, secret=secret, salt=salt)
    if not isinstance(token, (str, bytes)):
        raise HarnessError(
            "signed garbage token is neither text nor bytes; "
            f"got {type(token).__name__}: {token!r}"
        )
    print(
        f"signed garbage payload={payload!r} token_len={len(token)} salt_set={salt is not None}",
        flush=True,
    )
    return token


def arrange_signed_letter_A_token(
    secret: str | bytes, salt: str | bytes | None = None
) -> bytes:
    """F01-signed token whose payload is the letter ``A``. Not a product API."""
    token = _sign_garbage_payload(SIGNED_LETTER_A_PAYLOAD, secret, salt)
    print(
        f"arranged signed letter-A payload token_len={len(token)}",
        flush=True,
    )
    return token


def arrange_signed_period_eight_A_token(
    secret: str | bytes, salt: str | bytes | None = None
) -> bytes:
    """F01-signed token whose payload is ``.`` plus eight letters ``A``."""
    token = _sign_garbage_payload(SIGNED_PERIOD_EIGHT_A_PAYLOAD, secret, salt)
    require_compressed_payload_section(token)
    print(
        f"arranged signed period-plus-eight-A payload token_len={len(token)}",
        flush=True,
    )
    return token


def arrange_runtime_invalid_urlsafe_token(
    secret: str | bytes, salt: str | bytes | None = None
) -> bytes:
    """Signed illegal encoding whose payload is not the letter ``A``."""
    chosen: bytes | None = None
    for _ in range(32):
        ch = runtime_ascii_letter()
        payload = ch.encode("ascii")
        if payload != SIGNED_LETTER_A_PAYLOAD and not payload.startswith(b"."):
            chosen = payload
            break
    if chosen is None:
        raise HarnessError(
            "could not sample an illegal URL-safe payload other than the letter A"
        )
    token = _sign_garbage_payload(chosen, secret, salt)
    print(
        f"arranged runtime invalid URL-safe payload={chosen!r} "
        f"token_len={len(token)}",
        flush=True,
    )
    return token


def arrange_runtime_invalid_compressed_token(
    secret: str | bytes, salt: str | bytes | None = None
) -> bytes:
    """Signed fake-compressed payload that is not ``.AAAAAAAA``."""
    chosen: bytes | None = None
    for _ in range(32):
        ch = runtime_ascii_letter()
        if ch == "A":
            continue
        payload = b"." + (ch.encode("ascii") * 8)
        if payload != SIGNED_PERIOD_EIGHT_A_PAYLOAD:
            chosen = payload
            break
    if chosen is None:
        raise HarnessError(
            "could not sample a fake-compressed payload other than period-plus-eight-A"
        )
    token = _sign_garbage_payload(chosen, secret, salt)
    require_compressed_payload_section(token)
    print(
        f"arranged runtime invalid compressed payload={chosen!r} "
        f"token_len={len(token)}",
        flush=True,
    )
    return token


def assert_urlsafe_missing_not_malformed_timestamp(
    missing: BaseException,
    malformed: BaseException,
) -> None:
    """L201: same-secret uncompressed missing is not the compressed malformed kind."""
    require_distinct_failure_kinds(
        missing, malformed, expect=("missing-timestamp", "malformed-timestamp")
    )
    print(
        "URL-safe missing-timestamp refusal is a distinct kind "
        "from malformed timestamp",
        flush=True,
    )
