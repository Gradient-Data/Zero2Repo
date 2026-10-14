# feature: F01
"""Observation helpers for cryptographic signing of byte values (FP-01).

Helpers classify outcomes of the public signer. They never return ``None``
to mean "the observation could not be classified".
"""

from __future__ import annotations

import secrets
import string
from typing import Any

from _harness import (
    CallResult,
    HarnessError,
    as_bytes,
    call,
    drop_suffix,
    require_exception,
    require_value,
    rsplit_once,
)


class BUILT_IN_DERIVATIONS(tuple):
    """The four built-in key-derivation names the signer accepts.

    Downstream suites import this name and iterate it. The binding is the
    four-name sequence, not a callable.
    """


BUILT_IN_DERIVATIONS = BUILT_IN_DERIVATIONS(
    ("concat", "django-concat", "hmac", "none")
)


class DEFAULT_SEPARATOR(bytes):
    """The product default payload/signature separator: a period.

    Downstream suites import this name and use it as bytes (containment,
    concatenation, replacement). The binding is the period byte, not a
    callable.
    """


DEFAULT_SEPARATOR = DEFAULT_SEPARATOR(b".")


def load_signer_surface() -> tuple[Any, Any, Any]:
    """Import the public signer and algorithms from the package root.

    Import happens at call time so construction is observed through
    ``construct_signer``, not at helper-module import. Absence of the
    package from the import path is not a graded product outcome.
    """
    from signtoken import HMACAlgorithm, NoneAlgorithm, Signer

    for label, obj in (
        ("Signer", Signer),
        ("HMACAlgorithm", HMACAlgorithm),
        ("NoneAlgorithm", NoneAlgorithm),
    ):
        if not callable(obj):
            raise HarnessError(f"{label} is not callable; got {type(obj)!r}")
    return Signer, HMACAlgorithm, NoneAlgorithm


def construct_signer(*args: Any, **kwargs: Any) -> CallResult:
    """Construct a signer through the public class. Returns the CallResult."""
    signer_cls, _, _ = load_signer_surface()
    return call(signer_cls, *args, **kwargs)


def assert_construction_refused(result: CallResult) -> BaseException:
    """Require construction to refuse: the caller must not receive a signer.

    The PRD's carrier for an illegal separator is that constructing the
    signer is refused. Raises if the constructor returned a value.
    """
    exc = require_exception(result)
    assert result.value is None, (
        "construction produced a signer instead of refusing: "
        f"{type(result.value)!r}"
    )
    print(
        f"construction refused via {type(exc).__name__}",
        flush=True,
    )
    return exc


def make_signer(*args: Any, **kwargs: Any) -> Any:
    """Construct a signer that must succeed. Raises if construction fails."""
    result = construct_signer(*args, **kwargs)
    signer = require_value(result)
    print(
        f"constructed signer args={args!r} kwargs={list(kwargs)!r}",
        flush=True,
    )
    return signer


def hmac_algorithm(*args: Any, **kwargs: Any) -> Any:
    """Construct the public HMAC algorithm object."""
    _, hmac_cls, _ = load_signer_surface()
    return require_value(call(hmac_cls, *args, **kwargs))


def noop_algorithm() -> Any:
    """Construct the public no-op algorithm object."""
    _, _, noop_cls = load_signer_surface()
    return require_value(call(noop_cls))


def require_bytes(value: Any) -> bytes:
    """Return *value* if it is a byte string (``isinstance(..., bytes)``).

    A bytes subclass is a byte string. Never treats str as success. Does
    not demand ``type(...) is bytes``.
    """
    if not isinstance(value, bytes):
        raise AssertionError(
            f"expected bytes, got {type(value).__name__}: {value!r}"
        )
    return value


def expected_bytes(value: str | bytes) -> bytes:
    """UTF-8 encode text; return bytes unchanged."""
    return as_bytes(value)


def attempt_sign(signer: Any, value: str | bytes) -> CallResult:
    return call(signer.sign, value)


def sign_value(signer: Any, value: str | bytes) -> bytes:
    """Sign *value* and return a bytes token. Raises if signing fails."""
    result = attempt_sign(signer, value)
    token = require_value(result)
    print(
        f"signed type={type(value).__name__} token_len={len(require_bytes(token))}",
        flush=True,
    )
    return require_bytes(token)


def recover_value(signer: Any, token: str | bytes) -> CallResult:
    return call(signer.unsign, token)


def validity_of(signer: Any, token: str | bytes) -> CallResult:
    return call(signer.validate, token)


def require_round_trip(signer: Any, value: str | bytes) -> bytes:
    """Sign then recover. Recovered bytes must equal UTF-8 / original bytes."""
    token = sign_value(signer, value)
    recovered = require_recovered_bytes(signer, token, value)
    return token


def require_recovered_bytes(
    signer: Any, token: str | bytes, value: str | bytes
) -> bytes:
    result = recover_value(signer, token)
    recovered = require_bytes(require_value(result))
    expected = expected_bytes(value)
    if recovered != expected:
        raise AssertionError(
            f"recovery yielded {recovered!r}, expected {expected!r}"
        )
    print(f"recovered {recovered!r}", flush=True)
    return recovered


def require_recovery_failure(result: CallResult) -> BaseException:
    """Return the failure object. Not a successful hand-back of a value."""
    if result.exception is None:
        raise AssertionError(
            "recovery returned "
            f"{result.value!r} (type={type(result.value)!r}) "
            "instead of refusing"
        )
    print(
        f"recovery refused via {type(result.exception).__name__}",
        flush=True,
    )
    return result.exception


def require_validity_success(
    result: CallResult, *, payload: bytes | None = None
) -> Any:
    """Validity must report success by returning, not by refusing."""
    if result.exception is not None:
        raise AssertionError(
            "validity check refused with a failure instead of reporting "
            f"success: {type(result.exception).__name__}: {result.exception!r}"
        )
    value = result.value
    if not value:
        raise AssertionError(
            f"validity check did not report success; got {value!r}"
        )
    if payload is not None and value == payload:
        raise AssertionError(
            "validity check returned the payload bytes instead of a "
            "success report"
        )
    print(f"validity success report type={type(value).__name__}", flush=True)
    return value


def require_validity_failure(result: CallResult) -> Any:
    """Validity must report failure by returning, not by refusing."""
    if result.exception is not None:
        raise AssertionError(
            "validity check refused with a failure instead of reporting "
            f"failure: {type(result.exception).__name__}: {result.exception!r}"
        )
    value = result.value
    if value:
        raise AssertionError(
            f"validity check did not report failure; got {value!r}"
        )
    print(f"validity failure report={value!r}", flush=True)
    return value


def _bytes_on_failure(exc: BaseException) -> list[bytes]:
    """Return the failure's stated ``payload`` attribute when it is bytes.

    The Interface Contract states that a refusal carries the unverified
    payload section on ``payload`` (bytes, or ``None`` when there is none).
    """
    value = getattr(exc, "payload", None)
    if isinstance(value, (bytes, bytearray)):
        return [bytes(value)]
    return []


def payload_carried_on_failure(exc: BaseException, expected: bytes) -> bytes:
    """Require the failure's ``payload`` attribute to equal *expected*.

    Does not take the token. Raises if the stated attribute is missing or
    differs from the original payload.
    """
    expected = require_bytes(expected)
    found = _bytes_on_failure(exc)
    print(
        f"failure payload attribute={getattr(exc, 'payload', '<absent>')!r} "
        f"expected_payload={expected!r}",
        flush=True,
    )
    if found and found[0] == expected:
        return found[0]
    raise AssertionError(
        "failure object's payload attribute is not the original payload "
        f"{expected!r}; type={type(exc).__name__} "
        f"payload={getattr(exc, 'payload', '<absent>')!r}"
    )


def assert_token_accepted(signer: Any, token: bytes, value: str | bytes) -> bytes:
    recovered = require_recovered_bytes(signer, token, value)
    require_validity_success(validity_of(signer, token), payload=recovered)
    return recovered


def assert_token_refused(
    signer: Any, token: bytes, *, expected_payload: bytes | None = None
) -> BaseException:
    exc = require_recovery_failure(recover_value(signer, token))
    if expected_payload is not None:
        payload_carried_on_failure(exc, expected_payload)
    require_validity_failure(validity_of(signer, token))
    return exc


def split_token(
    token: bytes, sep: bytes = DEFAULT_SEPARATOR
) -> tuple[bytes, bytes]:
    """Split on the last separator. Raises if the separator is absent."""
    token_b = require_bytes(token)
    sep_b = require_bytes(sep)
    left, right = rsplit_once(token_b, sep_b)
    return require_bytes(left), require_bytes(right)


def require_layout(
    token: bytes,
    payload: str | bytes,
    *,
    sep: bytes = DEFAULT_SEPARATOR,
    signature_nonempty: bool = True,
) -> bytes:
    """Require token == payload + sep + signature (payload is the whole left)."""
    token_b = require_bytes(token)
    payload_b = expected_bytes(payload)
    prefix = payload_b + sep
    if not token_b.startswith(prefix):
        raise AssertionError(
            "token is not payload-then-separator-then-signature: "
            f"payload={payload_b!r} sep={sep!r} token_prefix={token_b[: len(prefix) + 8]!r}"
        )
    signature = token_b[len(prefix) :]
    if signature_nonempty and not signature:
        raise AssertionError("signature section is empty")
    print(
        f"layout payload_len={len(payload_b)} sig_len={len(signature)}",
        flush=True,
    )
    return signature


def replace_in_payload(
    token: bytes, old: bytes, new: bytes, *, sep: bytes = DEFAULT_SEPARATOR
) -> bytes:
    """Replace *old* with *new* in the payload section only."""
    from _harness import replace_bytes

    payload, signature = split_token(token, sep)
    changed = require_bytes(replace_bytes(payload, old, new, count=1))
    return changed + sep + signature


def flip_bit(data: bytes, index: int) -> bytes:
    """Flip one bit. Raises if *index* is out of range; never returns *data*."""
    raw = require_bytes(data)
    if not isinstance(index, int) or isinstance(index, bool):
        raise HarnessError(f"bit index is not an int: {index!r}")
    nbits = len(raw) * 8
    if index < 0 or index >= nbits:
        raise HarnessError(
            f"bit index {index} out of range for {len(raw)} bytes ({nbits} bits)"
        )
    byte_i, bit_i = divmod(index, 8)
    out = bytearray(raw)
    out[byte_i] ^= 1 << (7 - bit_i)
    flipped = bytes(out)
    if flipped == raw:
        raise HarnessError("bit flip produced an identical value")
    return flipped


def chop_last_byte(token: bytes) -> bytes:
    chopped = drop_suffix(require_bytes(token), 1)
    return require_bytes(chopped)


def runtime_secret() -> str:
    return "sk-" + secrets.token_hex(16)


def runtime_text() -> str:
    return "txt-" + secrets.token_hex(8)


def runtime_non_ascii_text() -> str:
    return "\u00f1-\u4e16\u754c-" + secrets.token_hex(4)


def latin1_bytes(text: str) -> bytes:
    """Encode *text* as latin-1. Raises if the text is not encodable.

    Used only as a contrast against the UTF-8 encoding the PRD names.
    Never treats an encode failure as a sampled payload.
    """
    if not isinstance(text, str):
        raise HarnessError(f"latin-1 contrast requires text, got {type(text)!r}")
    try:
        encoded = text.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise HarnessError(
            f"text is not latin-1 encodable, cannot contrast with UTF-8: {exc}"
        ) from exc
    return encoded


def runtime_utf8_distinct_text() -> str:
    """Runtime text whose UTF-8 bytes differ from latin-1.

    U+00F1 is one byte in latin-1 and two bytes in UTF-8. ASCII-only
    runtime text cannot measure the UTF-8 encoding the PRD names.
    """
    text = "\u00f1-" + secrets.token_hex(8)
    utf8 = expected_bytes(text)
    other = latin1_bytes(text)
    if utf8 == other:
        raise HarnessError("sampled text does not distinguish UTF-8 from latin-1")
    return text


def require_utf8_not_latin1(recovered: bytes, text: str) -> bytes:
    """Require *recovered* to be UTF-8 of *text*, not the latin-1 encoding."""
    recovered_b = require_bytes(recovered)
    utf8 = expected_bytes(text)
    other = latin1_bytes(text)
    if utf8 == other:
        raise HarnessError("text does not distinguish UTF-8 from latin-1")
    if recovered_b != utf8:
        raise AssertionError(
            f"recovery yielded {recovered_b!r}, expected UTF-8 {utf8!r}"
        )
    if recovered_b == other:
        raise AssertionError(
            "recovery yielded the latin-1 encoding of the text, not UTF-8"
        )
    print(
        f"utf8={utf8!r} latin1={other!r} recovered={recovered_b!r}",
        flush=True,
    )
    return recovered_b


def runtime_invalid_utf8_bytes(n: int = 8) -> bytes:
    """Runtime bytes that are not valid UTF-8 and do not contain the separator.

    An implementation that transcodes signed bytes through a text codec
    cannot round-trip a leading 0xFF payload.
    """
    for _ in range(32):
        data = b"\xff" + secrets.token_bytes(n)
        if DEFAULT_SEPARATOR in data:
            continue
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return data
    raise HarnessError("could not sample a payload that is not valid UTF-8")


def runtime_payload(n: int = 12) -> bytes:
    return secrets.token_bytes(n)


def runtime_payload_without_sep(
    sep: bytes = DEFAULT_SEPARATOR, n: int = 12
) -> bytes:
    for _ in range(32):
        data = secrets.token_bytes(n)
        if sep not in data and data != b"b":
            return data
    raise HarnessError("could not sample payload without the separator")


def runtime_payload_with_sep(sep: bytes = DEFAULT_SEPARATOR) -> bytes:
    left = runtime_payload_without_sep(sep, n=6)
    right = runtime_payload_without_sep(sep, n=6)
    return left + sep + right


def distinct_pair() -> tuple[str, str]:
    left = runtime_secret()
    right = runtime_secret()
    while right == left:
        right = runtime_secret()
    return left, right


def runtime_ascii_letter() -> str:
    return secrets.choice(string.ascii_letters)


def runtime_ascii_digit() -> str:
    return secrets.choice(string.digits)


def runtime_unknown_derivation() -> str:
    for _ in range(16):
        name = "kd-" + secrets.token_hex(8)
        if name not in BUILT_IN_DERIVATIONS:
            return name
    raise HarnessError("could not sample an unrecognized derivation name")
