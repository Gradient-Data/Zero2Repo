# feature: F02
"""Observation helpers for serialize-and-sign of structured objects (FP-02).

Helpers classify dump / load / unsafe-load outcomes. They never return
``None`` to mean "the observation could not be classified".
"""

from __future__ import annotations

import hashlib
import json
import secrets
import string
from typing import Any

from _harness import (
    CallResult,
    HarnessError,
    as_bytes,
    as_pair,
    as_text,
    call,
    drop_suffix,
    require_exception,
    require_value,
    rsplit_once,
)

# Period is the product default separator (PRD). Own name: do not re-export
# a predecessor's DEFAULT_SEPARATOR.
SERIALIZER_SEPARATOR = b"."


class TEXT_SEPARATOR(str):
    """The product default payload/signature separator as text: a period.

    Downstream suites import this name and use it as text (containment,
    concatenation, replacement). The binding is the period character, not a
    callable.
    """


TEXT_SEPARATOR = TEXT_SEPARATOR(".")


class JSON_LIST_ONE_THROUGH_FOUR(str):
    """JSON text of the list of integers 1 through 4, including spaces.

    Downstream suites import this name and use it as that JSON text (membership
    in a token, equality with a payload section). The binding is the text, not
    a callable.
    """


JSON_LIST_ONE_THROUGH_FOUR = JSON_LIST_ONE_THROUGH_FOUR("[1, 2, 3, 4]")


class PUBLIC_ID_MAPPING(dict):
    """Mapping whose ``id`` is 42.

    Downstream suites import this name and dump, load, and compare it as a
    mapping. The binding is that mapping, not a callable.
    """


PUBLIC_ID_MAPPING = PUBLIC_ID_MAPPING({"id": 42})
_NO_EXPECTED = object()


class MarkedDecodeError(Exception):
    """Test-process decode error that carries a runtime marker.

    Not a product type. Used so a payload-decode failure's retained
    ``original_error`` can be identified.
    """

    def __init__(self, marker: str) -> None:
        super().__init__(marker)
        self.marker = marker


def load_serializer_surface() -> Any:
    """Import the public serialize-and-sign helper from the package root.

    Import happens here, not at module import time, so this helper still
    loads when the product is absent from ``sys.path``.
    """
    from signtoken import Serializer

    if not callable(Serializer):
        raise HarnessError(f"Serializer is not callable; got {type(Serializer)!r}")
    return Serializer


def construct_helper(*args: Any, **kwargs: Any) -> CallResult:
    helper_cls = load_serializer_surface()
    return call(helper_cls, *args, **kwargs)


def make_helper(*args: Any, **kwargs: Any) -> Any:
    result = construct_helper(*args, **kwargs)
    helper = require_value(result)
    print(
        f"constructed serialize-and-sign helper args={args!r} "
        f"kwargs={list(kwargs)!r}",
        flush=True,
    )
    return helper


def dump_object(helper: Any, obj: Any, **kwargs: Any) -> str | bytes:
    result = call(helper.dumps, obj, **kwargs)
    token = require_value(result)
    if not isinstance(token, (str, bytes)):
        raise HarnessError(
            "dump did not return text or bytes; "
            f"got {type(token)!r}: {token!r}"
        )
    print(
        f"dumped type={type(token).__name__} token_len={len(token)} "
        f"obj_type={type(obj).__name__}",
        flush=True,
    )
    return token


def require_dumped_text(token: Any) -> str:
    """Require dump to have returned text, matching a text dump/load object."""
    if not isinstance(token, str):
        raise AssertionError(
            "dump must return text when the attached dump/load object "
            f"returns text; got {type(token).__name__}: {token!r}"
        )
    return token


def require_dumped_bytes(token: Any) -> bytes:
    """Require dump to have returned bytes, matching a bytes dump/load object."""
    if not isinstance(token, bytes):
        raise AssertionError(
            "dump must return bytes when the attached dump/load object "
            f"returns bytes; got {type(token).__name__}: {token!r}"
        )
    return token


def require_load_accepts_text_or_bytes(
    helper: Any, token: str | bytes, expected: Any, **kwargs: Any
) -> Any:
    """Load the same token as text and as bytes; both must recover *expected*.

    Raises if the unused form cannot be produced (not UTF-8) rather than
    skipping that arm. Does not return a sentinel for a failed load.
    """
    if isinstance(token, str):
        text_token: str | bytes = token
        try:
            bytes_token: str | bytes = as_bytes(token)
        except HarnessError as exc:
            raise AssertionError(
                "text token was not UTF-8 so the bytes load form could "
                f"not be tried: {exc}"
            ) from exc
    elif isinstance(token, bytes):
        bytes_token = token
        try:
            text_token = as_text(token)
        except HarnessError as exc:
            raise AssertionError(
                "bytes token was not UTF-8 so the text load form could "
                f"not be tried: {exc}"
            ) from exc
    else:
        raise HarnessError(f"token is not text or bytes: {type(token)!r}")
    from_text = load_object(helper, text_token, **kwargs)
    from_bytes = load_object(helper, bytes_token, **kwargs)
    if from_text != from_bytes:
        raise AssertionError(
            "text and bytes load of the same token recovered different "
            f"objects: text={from_text!r} bytes={from_bytes!r}"
        )
    if from_text != expected:
        raise AssertionError(
            "dual-form load recovered "
            f"{from_text!r} (type={type(from_text)!r}), expected {expected!r}"
        )
    print(
        f"dual-form load recovered type={type(from_text).__name__} "
        f"value={from_text!r}",
        flush=True,
    )
    return from_text


def load_object_call(helper: Any, token: str | bytes, **kwargs: Any) -> CallResult:
    return call(helper.loads, token, **kwargs)


def load_object(helper: Any, token: str | bytes, **kwargs: Any) -> Any:
    return require_load_success(load_object_call(helper, token, **kwargs))


def unsafe_load_object(helper: Any, token: str | bytes, **kwargs: Any) -> CallResult:
    return call(helper.loads_unsafe, token, **kwargs)


def dump_to_stream(helper: Any, obj: Any, stream: Any, **kwargs: Any) -> Any:
    result = call(helper.dump, obj, stream, **kwargs)
    require_value(result)
    print(
        f"dumped to stream obj_type={type(obj).__name__} "
        f"stream_type={type(stream).__name__}",
        flush=True,
    )
    return result.value


def load_from_stream(helper: Any, stream: Any, **kwargs: Any) -> CallResult:
    return call(helper.load, stream, **kwargs)


def unsafe_load_from_stream(helper: Any, stream: Any, **kwargs: Any) -> CallResult:
    return call(helper.load_unsafe, stream, **kwargs)


def require_round_trip_object(helper: Any, obj: Any, **kwargs: Any) -> str | bytes:
    token = dump_object(helper, obj, **kwargs)
    loaded = require_load_success(load_object_call(helper, token, **kwargs), expected=obj)
    print(f"round-trip recovered type={type(loaded).__name__}", flush=True)
    return token


def require_load_success(result: CallResult, expected: Any = _NO_EXPECTED) -> Any:
    value = require_value(result)
    if expected is not _NO_EXPECTED and value != expected:
        raise AssertionError(
            f"load recovered {value!r} (type={type(value)!r}), "
            f"expected {expected!r}"
        )
    print(
        f"load success type={type(value).__name__} value={value!r}",
        flush=True,
    )
    return value


def require_load_failure(result: CallResult) -> BaseException:
    if result.exception is None:
        raise AssertionError(
            "load returned "
            f"{result.value!r} (type={type(result.value)!r}) "
            "instead of refusing"
        )
    print(
        f"load refused via {type(result.exception).__name__}",
        flush=True,
    )
    return result.exception


def require_unsafe_pair(result: CallResult) -> tuple[Any, Any]:
    """Require unsafe load to return a pair without aborting the caller."""
    if result.exception is not None:
        raise AssertionError(
            "unsafe load aborted the caller with "
            f"{type(result.exception).__name__}: {result.exception!r}; "
            "a signature mismatch must return a pair"
        )
    pair = as_pair(require_value(result))
    print(
        f"unsafe pair first={pair[0]!r} second_type={type(pair[1]).__name__}",
        flush=True,
    )
    return pair


def require_signature_mismatch(
    helper: Any,
    token: str | bytes,
    *,
    expected: Any = _NO_EXPECTED,
    **kwargs: Any,
) -> tuple[BaseException, tuple[Any, Any]]:
    """Ordinary load fails; unsafe load returns an invalid-signature pair.

    Distinguishes a signature mismatch from a payload-decode failure
    without pinning exception class names. When *expected* is passed, the
    payload can still be decoded, so the pair's second item must be that
    object — not an empty slot.
    """
    exc = require_load_failure(load_object_call(helper, token, **kwargs))
    unsafe = unsafe_load_object(helper, token, **kwargs)
    first, second = require_unsafe_pair(unsafe)
    if first:
        raise AssertionError(
            "unsafe load reported a valid signature on a signature mismatch; "
            f"first={first!r} second={second!r}"
        )
    if expected is not _NO_EXPECTED and second != expected:
        raise AssertionError(
            "signature mismatch left a still-decodable payload, so unsafe "
            "load must yield that object; "
            f"got {second!r}, expected {expected!r}"
        )
    print("classified as signature mismatch", flush=True)
    return exc, (first, second)


def require_payload_decode_failure(
    helper: Any, token: str | bytes, **kwargs: Any
) -> tuple[BaseException, BaseException]:
    """Ordinary load fails; unsafe load does not return a pair.

    Distinguishes a payload-decode failure from a signature mismatch.
    """
    load_exc = require_load_failure(load_object_call(helper, token, **kwargs))
    unsafe = unsafe_load_object(helper, token, **kwargs)
    if unsafe.exception is None:
        pair = as_pair(require_value(unsafe))
        raise AssertionError(
            "unsafe load returned a pair "
            f"{pair!r}; a payload-decode failure must not be converted "
            "into a pair"
        )
    print(
        f"classified as payload-decode failure "
        f"load={type(load_exc).__name__} unsafe={type(unsafe.exception).__name__}",
        flush=True,
    )
    return load_exc, unsafe.exception


def token_as_text(token: str | bytes) -> str:
    """Return a dumped token as text for a text stream.

    Raises if the token is neither text nor valid UTF-8 bytes. Never
    returns a sentinel and never skips the unused form.
    """
    if not isinstance(token, (str, bytes)):
        raise HarnessError(f"token is not text or bytes: {type(token)!r}")
    return as_text(token)


def chop_last_character(token: str | bytes) -> str | bytes:
    if isinstance(token, bytes):
        return chop_signed_bytes(token)
    if isinstance(token, str):
        chopped = drop_suffix(token, 1)
        if not isinstance(chopped, str):
            raise HarnessError(
                f"chopping text token did not yield text; got {type(chopped)!r}"
            )
        return chopped
    raise HarnessError(f"token is not text or bytes: {type(token)!r}")


def signature_section(token: str | bytes) -> str | bytes:
    if isinstance(token, bytes):
        _, sig = split_signed_bytes(token, SERIALIZER_SEPARATOR)
        return sig
    if isinstance(token, str):
        _, sig = rsplit_once(token, TEXT_SEPARATOR)
        return sig
    raise HarnessError(f"token is not text or bytes: {type(token)!r}")


def payload_section(token: str | bytes) -> str | bytes:
    if isinstance(token, bytes):
        payload, _ = split_signed_bytes(token, SERIALIZER_SEPARATOR)
        return payload
    if isinstance(token, str):
        payload, _ = rsplit_once(token, TEXT_SEPARATOR)
        return payload
    raise HarnessError(f"token is not text or bytes: {type(token)!r}")


def join_payload_and_signature(payload: str | bytes, signature: str | bytes) -> str | bytes:
    if isinstance(payload, bytes) and isinstance(signature, bytes):
        return payload + SERIALIZER_SEPARATOR + signature
    if isinstance(payload, str) and isinstance(signature, str):
        return payload + TEXT_SEPARATOR + signature
    raise HarnessError(
        "payload and signature must both be str or both bytes; "
        f"got payload={type(payload).__name__} signature={type(signature).__name__}"
    )


def require_json_then_sep_then_signature(
    token: str | bytes, json_text: str
) -> str | bytes:
    """Require token = JSON text, then the default separator, then a signature.

    Does not pin a split algorithm as a product contract. Raises if the
    signature section is empty.
    """
    if isinstance(token, bytes):
        prefix = as_bytes(json_text) + SERIALIZER_SEPARATOR
        if not token.startswith(prefix):
            raise AssertionError(
                "token is not JSON-text-then-separator-then-signature: "
                f"json_text={json_text!r} token_prefix={token[: len(prefix) + 8]!r}"
            )
        signature = token[len(prefix) :]
    elif isinstance(token, str):
        prefix = json_text + TEXT_SEPARATOR
        if not token.startswith(prefix):
            raise AssertionError(
                "token is not JSON-text-then-separator-then-signature: "
                f"json_text={json_text!r} token_prefix={token[: len(prefix) + 8]!r}"
            )
        signature = token[len(prefix) :]
    else:
        raise HarnessError(f"token is not text or bytes: {type(token)!r}")
    if not signature:
        raise AssertionError("signature section is empty")
    print(
        f"json-then-sep-then-sig json_len={len(json_text)} "
        f"sig_len={len(signature)}",
        flush=True,
    )
    return signature


def require_token_carries_codec_format(
    token: Any, prefix: str | bytes
) -> None:
    """Require the dumped token to start with the attached dump/load format.

    The check is the same for text and bytes tokens: a JSON-shaped token
    that omits the attached object's marker fails. Raises if the token
    is neither text nor bytes, or if the marker is empty.
    """
    if not prefix:
        raise HarnessError("codec format prefix must be non-empty")
    if isinstance(token, str):
        marker: str | bytes = (
            prefix if isinstance(prefix, str) else as_text(prefix)
        )
        carried = token.startswith(marker)
    elif isinstance(token, bytes):
        marker = prefix if isinstance(prefix, bytes) else as_bytes(prefix)
        carried = token.startswith(marker)
    else:
        raise HarnessError(f"token is not text or bytes: {type(token)!r}")
    if not carried:
        raise AssertionError(
            "dumped token must carry the attached dump/load object's "
            f"non-JSON format {prefix!r} rather than JSON; got {token[:48]!r}"
        )
    print(
        f"token carries codec format prefix={prefix!r} "
        f"token_type={type(token).__name__}",
        flush=True,
    )


def json_string_literal(text: str) -> str:
    """JSON string literal for a text that needs no escaping."""
    if any(ch in text for ch in '"\\\x00\n\r\t'):
        raise HarnessError(
            "text is not a bare JSON string candidate (needs escaping): "
            f"{text!r}"
        )
    return '"' + text + '"'


def _token_forms(token: str | bytes) -> list[str | bytes]:
    forms: list[str | bytes] = [token]
    if isinstance(token, str):
        try:
            forms.append(as_bytes(token))
        except HarnessError:
            pass
    elif isinstance(token, bytes):
        try:
            forms.append(as_text(token))
        except HarnessError:
            pass
    return forms


def unsigned_payload_on_failure(
    exc: BaseException, *, token: str | bytes
) -> list[str | bytes]:
    """Return the unsigned payload a signature-mismatch failure carries.

    Reads the stated ``payload`` attribute. A value equal to the full token
    is not the payload section. Raises if the attribute is missing or holds
    no payload. Never returns an empty list or ``None``.
    """
    value = getattr(exc, "payload", None)
    if isinstance(value, bytearray):
        value = bytes(value)
    print(
        f"failure payload attribute type={type(value).__name__}",
        flush=True,
    )
    if not isinstance(value, (str, bytes)):
        raise AssertionError(
            "failure object's payload attribute carries no unsigned payload; "
            f"type={type(exc).__name__} payload={value!r}"
        )
    if value in set(_token_forms(token)):
        raise AssertionError(
            "failure object's payload attribute is the full token, not the "
            "payload section"
        )
    return [value]


def decode_inspected_payload(payload: str | bytes, dumps_loads: Any = None) -> Any:
    codec = json if dumps_loads is None else dumps_loads
    try:
        loads = codec.loads
    except AttributeError as exc:
        raise HarnessError(
            f"dump/load object has no loads; got {type(codec)!r}"
        ) from exc
    forms: list[Any] = [payload]
    if isinstance(payload, bytes):
        try:
            forms.append(as_text(payload))
        except HarnessError:
            pass
    elif isinstance(payload, str):
        try:
            forms.append(as_bytes(payload))
        except HarnessError:
            pass
    errors: list[str] = []
    for form in forms:
        try:
            return loads(form)
        except Exception as exc:
            errors.append(f"{type(form).__name__}:{type(exc).__name__}:{exc}")
    raise HarnessError(
        "cannot decode inspected payload with the dump/load object; "
        f"tried {len(forms)} form(s): {errors!r}"
    )


def recover_object_from_failure(
    exc: BaseException, *, token: str | bytes, dumps_loads: Any = None
) -> Any:
    """Decode an inspectable payload on *exc* to an object. Raises if none."""
    candidates = unsigned_payload_on_failure(exc, token=token)
    if isinstance(candidates, (str, bytes)):
        candidates = [candidates]
    last_error: Exception | None = None
    decoded: list[Any] = []
    for item in candidates:
        try:
            decoded.append(decode_inspected_payload(item, dumps_loads))
        except Exception as exc_decode:
            last_error = exc_decode
            continue
    if not decoded:
        raise HarnessError(
            "no inspectable payload on the failure decoded to an object; "
            f"last_error={last_error!r}"
        )
    print(f"decoded inspectable objects={decoded!r}", flush=True)
    return decoded


def require_recovered_from_failure(
    exc: BaseException,
    expected: Any,
    *,
    token: str | bytes,
    dumps_loads: Any = None,
) -> Any:
    decoded = recover_object_from_failure(
        exc, token=token, dumps_loads=dumps_loads
    )
    for obj in decoded:
        if obj == expected:
            print(f"inspected payload decoded to {obj!r}", flush=True)
            return obj
    raise AssertionError(
        "inspected payload did not decode to the original object "
        f"{expected!r}; decoded={decoded!r}"
    )


def require_marker_on_failure(exc: BaseException, marker: str) -> str:
    """Require the payload-decode failure to retain the original decode error.

    Reads the stated ``original_error`` attribute: it must be the decode
    error the dump/load object raised, so two marked codecs stay
    distinguishable. Missing marker raises — never a sentinel.
    """
    if not marker:
        raise HarnessError("decode marker must be non-empty")
    original = getattr(exc, "original_error", None)
    print(
        f"failure original_error type={type(original).__name__}",
        flush=True,
    )
    if isinstance(original, MarkedDecodeError) and original.marker == marker:
        print(f"decode marker on original_error marker={marker!r}", flush=True)
        return marker
    raise AssertionError(
        "payload-decode failure did not retain the original decode error "
        f"on original_error (marker {marker!r}); "
        f"failure_type={type(exc).__name__} original_error={original!r}"
    )


def require_illegal_separator_refused(
    sep: str, *, secret: str = "secret-key"
) -> BaseException:
    """Refuse an FP-01-illegal separator on this serialize-and-sign helper.

    L124: separators behave as in FP-01 for the signer this helper
    constructs. L107/L115 pin that refusal at *signer* construction, not
    at constructing the serialize-and-sign helper. The helper may build
    that signer immediately, or later when it first dumps; either way
    the caller must not receive a signed token.
    """
    constructed = construct_helper(secret, signer_kwargs={"sep": sep})
    if constructed.exception is not None:
        refused = require_helper_construction_refused(constructed)
        assert constructed.value is None, (
            f"separator {sep!r} produced a helper instead of refusing: "
            f"{constructed.value!r}"
        )
        print(
            f"separator {sep!r} refused at helper construction via "
            f"{type(refused).__name__}",
            flush=True,
        )
        return refused
    helper = constructed.value
    dumped = call(helper.dumps, PUBLIC_ID_MAPPING)
    assert dumped.exception is not None, (
        f"separator {sep!r} produced a signed token instead of refusing: "
        f"{dumped.value!r}"
    )
    assert dumped.value is None, (
        f"separator {sep!r} produced a signed token instead of refusing: "
        f"{dumped.value!r}"
    )
    print(
        f"separator {sep!r} refused when this helper constructed its signer "
        f"via {type(dumped.exception).__name__}",
        flush=True,
    )
    return dumped.exception


def require_absent_object(
    second: Any,
    *,
    original: Any,
    leftover: str | bytes,
    chopped_token: str | bytes | None = None,
) -> Any:
    """Require the unsafe-load object slot to hold no deserialized object.

    Does not pin a language ``None`` sentinel. The slot must not be the
    original object, leftover payload bytes/text, or the chopped token.
    """
    if second == original:
        raise AssertionError(
            "unsafe load yielded the original object where no object is promised: "
            f"{second!r}"
        )
    forbidden = list(_token_forms(leftover))
    if chopped_token is not None:
        forbidden.extend(_token_forms(chopped_token))
    for item in forbidden:
        if second == item:
            raise AssertionError(
                "unsafe load yielded leftover payload or chopped token bytes/text "
                f"instead of no object: {second!r}"
            )
    print(
        f"no-object slot type={type(second).__name__} value={second!r}",
        flush=True,
    )
    return second


def signed_garbage_token(
    payload: str | bytes, *, secret: str | bytes, salt: str | bytes, **signer_kwargs: Any
) -> bytes:
    """Arrange a legally signed token over *payload* with a matching F01 signer."""
    signer = matching_signer(secret, salt=salt, **signer_kwargs)
    token = sign_with_matching_signer(signer, payload)
    print(
        f"arranged signed garbage payload_len={len(payload)} "
        f"token_len={len(token)}",
        flush=True,
    )
    return token


def shorten_payload(payload: str | bytes) -> str | bytes:
    """Return a strictly shorter prefix of *payload*. Raises if empty/too short."""
    if len(payload) < 2:
        raise HarnessError(
            f"payload is too short to shorten: len={len(payload)}"
        )
    shortened = payload[: max(1, len(payload) // 2)]
    if shortened == payload:
        shortened = payload[:-1]
    if not shortened or shortened == payload:
        raise HarnessError("could not produce a shorter payload")
    return shortened


class TaggedTextCodec:
    """Test-process dump/load object: text with a non-JSON prefix."""

    def __init__(self, prefix: str = "TAG|") -> None:
        if not prefix or prefix.startswith("{") or prefix.startswith("["):
            raise HarnessError(f"prefix must be a non-JSON marker; got {prefix!r}")
        self.prefix = prefix

    def dumps(self, obj: Any) -> str:
        return self.prefix + json.dumps(obj)

    def loads(self, payload: str | bytes) -> Any:
        text = payload if isinstance(payload, str) else as_text(payload)
        if not text.startswith(self.prefix):
            raise ValueError("payload is not tagged text")
        return json.loads(text[len(self.prefix) :])


class TaggedBytesCodec:
    """Test-process dump/load object: bytes with a non-JSON prefix."""

    def __init__(self, prefix: bytes = b"BIN|") -> None:
        if not prefix or prefix.startswith(b"{") or prefix.startswith(b"["):
            raise HarnessError(f"prefix must be a non-JSON marker; got {prefix!r}")
        self.prefix = prefix

    def dumps(self, obj: Any) -> bytes:
        return self.prefix + as_bytes(json.dumps(obj))

    def loads(self, payload: str | bytes) -> Any:
        raw = payload if isinstance(payload, bytes) else as_bytes(payload)
        if not raw.startswith(self.prefix):
            raise ValueError("payload is not tagged bytes")
        return json.loads(raw[len(self.prefix) :])


class MarkedFailingCodec:
    """Dump/load object whose load raises a marked error on garbage."""

    def __init__(self, marker: str, prefix: str = "MK|") -> None:
        if not marker:
            raise HarnessError("marker must be non-empty")
        self.marker = marker
        self.prefix = prefix

    def dumps(self, obj: Any) -> str:
        return self.prefix + json.dumps(obj)

    def loads(self, payload: str | bytes) -> Any:
        text = payload if isinstance(payload, str) else as_text(payload)
        if not text.startswith(self.prefix):
            raise MarkedDecodeError(self.marker)
        rest = text[len(self.prefix) :]
        try:
            return json.loads(rest)
        except Exception:
            raise MarkedDecodeError(self.marker) from None


def tagged_text_codec(prefix: str = "TAG|") -> TaggedTextCodec:
    return TaggedTextCodec(prefix=prefix)


def tagged_bytes_codec(prefix: bytes = b"BIN|") -> TaggedBytesCodec:
    return TaggedBytesCodec(prefix=prefix)


def marked_failing_codec(marker: str, prefix: str = "MK|") -> MarkedFailingCodec:
    return MarkedFailingCodec(marker=marker, prefix=prefix)


def public_signer_type() -> Any:
    """Import the public signing helper from the package root.

    Used to attach a signer type or to arrange a legally signed garbage
    payload. Import is deferred so this module still loads when the
    product is absent from ``sys.path``.
    """
    from signtoken import Signer

    if not callable(Signer):
        raise HarnessError(f"Signer is not callable; got {type(Signer)!r}")
    return Signer


def matching_signer(*args: Any, **kwargs: Any) -> Any:
    """Construct a public signer that must succeed. Own name, not make_signer."""
    signer_cls = public_signer_type()
    signer = require_value(call(signer_cls, *args, **kwargs))
    print(
        f"constructed matching signer args={args!r} kwargs={list(kwargs)!r}",
        flush=True,
    )
    return signer


def sign_with_matching_signer(signer: Any, value: str | bytes) -> bytes:
    """Sign *value* through the public signer. Own name, not sign_value."""
    token = require_value(call(signer.sign, value))
    if not isinstance(token, bytes):
        raise HarnessError(
            f"matching signer did not return bytes; got {type(token)!r}: {token!r}"
        )
    print(
        f"signed garbage-arrangement type={type(value).__name__} "
        f"token_len={len(token)}",
        flush=True,
    )
    return token


def require_helper_construction_refused(result: CallResult) -> BaseException:
    """Require helper construction to refuse: the caller must not receive a helper."""
    exc = require_exception(result)
    assert result.value is None, (
        "construction produced a helper instead of refusing: "
        f"{type(result.value)!r}"
    )
    print(
        f"helper construction refused via {type(exc).__name__}",
        flush=True,
    )
    return exc


def chop_signed_bytes(token: bytes) -> bytes:
    """Drop the last byte of a bytes token. Own name, not chop_last_byte."""
    if not isinstance(token, bytes):
        raise HarnessError(f"bytes token required; got {type(token)!r}")
    chopped = drop_suffix(token, 1)
    if not isinstance(chopped, bytes):
        raise HarnessError(
            f"chopping bytes token did not yield bytes; got {type(chopped)!r}"
        )
    return chopped


def split_signed_bytes(
    token: bytes, sep: bytes = SERIALIZER_SEPARATOR
) -> tuple[bytes, bytes]:
    """Split a bytes token on the last separator. Own name, not split_token."""
    if not isinstance(token, bytes):
        raise HarnessError(f"bytes token required; got {type(token)!r}")
    if not isinstance(sep, bytes):
        raise HarnessError(f"bytes separator required; got {type(sep)!r}")
    left, right = rsplit_once(token, sep)
    if not isinstance(left, bytes) or not isinstance(right, bytes):
        raise HarnessError(
            "split of bytes token must yield bytes; "
            f"got left={type(left)!r} right={type(right)!r}"
        )
    return left, right


def sampled_secret() -> str:
    return "sk-" + secrets.token_hex(16)


def sampled_text() -> str:
    return "txt-" + secrets.token_hex(8)


def sampled_non_ascii_text() -> str:
    return "\u00f1-\u4e16\u754c-" + secrets.token_hex(4)


def sampled_ascii_letter() -> str:
    return secrets.choice(string.ascii_letters)


def sampled_ascii_digit() -> str:
    return secrets.choice(string.digits)


def sampled_secret_pair() -> tuple[str, str]:
    left = sampled_secret()
    right = sampled_secret()
    while right == left:
        right = sampled_secret()
    return left, right


def sha512_default_signer_type() -> type:
    signer_cls = public_signer_type()

    class Sha512DefaultSigner(signer_cls):
        default_digest_method = hashlib.sha512

    Sha512DefaultSigner.__name__ = "Sha512DefaultSigner"
    Sha512DefaultSigner.__qualname__ = "Sha512DefaultSigner"
    return Sha512DefaultSigner


def sha256_default_signer_type() -> type:
    signer_cls = public_signer_type()

    class Sha256DefaultSigner(signer_cls):
        default_digest_method = hashlib.sha256

    Sha256DefaultSigner.__name__ = "Sha256DefaultSigner"
    Sha256DefaultSigner.__qualname__ = "Sha256DefaultSigner"
    return Sha256DefaultSigner


def runtime_mapping() -> dict[str, Any]:
    mapping = {"k": sampled_text(), "n": secrets.randbelow(10**9) + 43}
    if mapping == PUBLIC_ID_MAPPING:
        mapping["n"] += 1
    return mapping


def runtime_text_with_period() -> str:
    for _ in range(16):
        text = sampled_text() + "." + sampled_text()
        if "." in text and '"' not in text and "\\" not in text:
            return text
    raise HarnessError("could not sample text whose JSON contains a period")


def runtime_tuple_key() -> tuple[Any, ...]:
    key = (sampled_text(), secrets.randbelow(10**6) + 1)
    if key == ():
        raise HarnessError("runtime tuple key must not be the empty tuple")
    return key


def runtime_marker() -> str:
    return "mk-" + secrets.token_hex(12)
