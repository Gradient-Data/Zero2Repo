# feature: F03
"""Observation helpers for timestamped signatures and expiry (FP-03).

Helpers classify outcomes of the timestamped signer and the timestamped
serialize-and-sign helper. They never return ``None`` to mean "the
observation could not be classified".
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from _harness import (
    CallResult,
    HarnessError,
    as_bytes,
    as_pair,
    as_text,
    call,
    frozen_clock,
    require_value,
    rsplit_once,
)
from F01_helpers import (
    DEFAULT_SEPARATOR,
    expected_bytes,
    make_signer,
    payload_carried_on_failure,
    require_bytes,
    require_recovery_failure,
    sign_value,
)
from F02_helpers import (
    TEXT_SEPARATOR,
    load_object_call,
    require_load_failure,
    require_load_success,
    require_recovered_from_failure,
)

PUBLIC_VALUE = "value"
PUBLIC_CHANGED_VALUE = "my string"
PUBLIC_CHANGE_OLD = b"my"
PUBLIC_CHANGE_NEW = b"other"


class MAX_AGE_SECONDS(int):
    """PRD maximum age: 10 seconds.

    Downstream suites import this name, pass it as ``max_age``, and
    subtract it from other age bindings. The binding is the integer 10,
    not a callable.
    """


MAX_AGE_SECONDS = MAX_AGE_SECONDS(10)


class AGE_SUCCESS_SECONDS(int):
    """One second after signing still succeeds with maximum age 10.

    Downstream suites import this name and tick the frozen clock by it.
    The binding is the integer 1, not a callable.
    """


AGE_SUCCESS_SECONDS = AGE_SUCCESS_SECONDS(1)


class AGE_EXPIRED_SECONDS(int):
    """Eleven seconds after signing is expired when maximum age is 10.

    Downstream suites import this name, tick the frozen clock by it, and
    subtract the success age from it. The binding is the integer 11, not
    a callable.
    """


AGE_EXPIRED_SECONDS = AGE_EXPIRED_SECONDS(11)


class PUBLIC_SIGNING_INSTANT(datetime):
    """Frozen UTC instant the suite signs at.

    Downstream suites import this name and freeze the clock on it.
    The binding is 2020-06-24 00:09:05 UTC, not a callable.
    """


PUBLIC_SIGNING_INSTANT = PUBLIC_SIGNING_INSTANT(
    2020, 6, 24, 0, 9, 5, tzinfo=timezone.utc
)


class OTHER_SIGNING_INSTANT(datetime):
    """A second frozen UTC instant, distinct from the first.

    Downstream suites import this name and freeze the clock on it.
    The binding is 2018-03-11 14:22:00 UTC, not a callable.
    """


OTHER_SIGNING_INSTANT = OTHER_SIGNING_INSTANT(
    2018, 3, 11, 14, 22, 0, tzinfo=timezone.utc
)
FUTURE_CHECK_INSTANT = datetime(1971, 5, 31, 0, 0, 0, tzinfo=timezone.utc)
DUMMY_UNDECODABLE_SUFFIX = b"notAtimeStamp!!"


def load_timestamped_signer_surface() -> Any:
    """Import the timestamped signer from the package root.

    Import happens here, not at module import time, so this helper still
    loads when the product is absent from ``sys.path``.
    """
    from signtoken import TimestampSigner

    if not callable(TimestampSigner):
        raise HarnessError(
            f"TimestampSigner is not callable; got {type(TimestampSigner)!r}"
        )
    return TimestampSigner


def load_timestamped_serializer_surface() -> Any:
    """Import the timestamped serialize-and-sign helper from the package root."""
    from signtoken import TimedSerializer

    if not callable(TimedSerializer):
        raise HarnessError(
            f"TimedSerializer is not callable; got {type(TimedSerializer)!r}"
        )
    return TimedSerializer


def construct_timestamped_signer(*args: Any, **kwargs: Any) -> CallResult:
    return call(load_timestamped_signer_surface(), *args, **kwargs)


def construct_timestamped_serializer(*args: Any, **kwargs: Any) -> CallResult:
    return call(load_timestamped_serializer_surface(), *args, **kwargs)


def make_timestamped_signer(*args: Any, **kwargs: Any) -> Any:
    signer = require_value(construct_timestamped_signer(*args, **kwargs))
    print(
        f"constructed timestamped signer args={args!r} kwargs={list(kwargs)!r}",
        flush=True,
    )
    return signer


def make_timestamped_serializer(*args: Any, **kwargs: Any) -> Any:
    helper = require_value(construct_timestamped_serializer(*args, **kwargs))
    print(
        f"constructed timestamped serialize-and-sign helper args={args!r} "
        f"kwargs={list(kwargs)!r}",
        flush=True,
    )
    return helper


def recover_timestamped(signer: Any, token: str | bytes, **kwargs: Any) -> CallResult:
    return call(signer.unsign, token, **kwargs)


def validity_of_timestamped(
    signer: Any, token: str | bytes, **kwargs: Any
) -> CallResult:
    return call(signer.validate, token, **kwargs)


def require_timestamped_bytes(result: CallResult, value: str | bytes) -> bytes:
    recovered = require_bytes(require_value(result))
    expected = expected_bytes(value)
    if recovered != expected:
        raise AssertionError(
            f"recovery yielded {recovered!r}, expected {expected!r}"
        )
    print(f"timestamped recovered {recovered!r}", flush=True)
    return recovered


def require_exact_bytes(value: Any) -> bytes:
    """Require *value* is exactly ``bytes`` (PRD: recovered value as bytes).

    ``isinstance(..., bytes)`` is not enough: a bytes subclass compares equal
    to the public sample and would leave that sample unmeasured.
    """
    if type(value) is not bytes:
        raise AssertionError(
            "recovery must yield bytes, not "
            f"{type(value).__name__}: {value!r}"
        )
    print(f"exact bytes type={type(value).__name__} value={value!r}", flush=True)
    return value


def require_integer_id(loaded: Any, *, ident: int = 42) -> Any:
    """Require *loaded* exposes ``id`` as the exact integer *ident*.

    Mapping equality accepts ``42.0 == 42``. Round-trip must return an
    equal object of the same JSON type, so a float stand-in for the
    integer is a different object.
    Lookup failure raises — never treated as a missing id.
    """
    try:
        value = loaded["id"]
    except Exception as exc:
        raise AssertionError(
            f"cannot read id from loaded object {loaded!r}: {exc}"
        ) from exc
    if type(value) is not int:
        raise AssertionError(
            "mapping id must be an integer, got "
            f"{type(value).__name__}: {value!r}"
        )
    if value != ident:
        raise AssertionError(f"mapping id is {value!r}, expected {ident!r}")
    print(
        f"integer id type={type(value).__name__} value={value!r}",
        flush=True,
    )
    return loaded


def runtime_integer_list() -> list[int]:
    """A short list of integers, not the public id-42 mapping.

    Used so a helper that only round-trips mappings, or that memorizes
    one canned triple, cannot satisfy the non-mapping dump/load arm.
    """
    length = 2 + secrets.randbelow(3)
    items = [10 + secrets.randbelow(10**6) for _ in range(length)]
    if items == [7, 8, 9]:
        items = [items[0] + 1, *items[1:]]
    print(f"runtime integer list={items!r}", flush=True)
    return items


def require_integer_list(loaded: Any, expected: list[int]) -> Any:
    """Require *loaded* is exactly a ``list`` of the given integers.

    Sequence equality accepts ``7.0 == 7`` and a list subclass. The PRD
    names a list of integers, so those stand-ins are a different object.
    """
    if type(loaded) is not list:
        raise AssertionError(
            "non-mapping round-trip must yield a list, not "
            f"{type(loaded).__name__}: {loaded!r}"
        )
    if len(loaded) != len(expected):
        raise AssertionError(
            f"list length {len(loaded)} != {len(expected)}: {loaded!r}"
        )
    for index, (item, want) in enumerate(zip(loaded, expected)):
        if type(item) is not int:
            raise AssertionError(
                f"list item {index} must be an integer, got "
                f"{type(item).__name__}: {item!r}"
            )
        if item != want:
            raise AssertionError(
                f"list item {index} is {item!r}, expected {want!r}"
            )
    print(
        f"integer list type={type(loaded).__name__} value={loaded!r}",
        flush=True,
    )
    return loaded


def default_json_text(obj: Any) -> str:
    """Default JSON text of *obj* (language JSON library, PRD default)."""
    try:
        return json.dumps(obj)
    except (TypeError, ValueError) as exc:
        raise HarnessError(f"cannot JSON-dump object for layout: {exc}") from exc


def require_aware_utc(dt: Any) -> datetime:
    """Require a timezone-aware datetime whose UTC offset is zero.

    Does not pin a particular tz object identity. Naive or non-UTC raises.
    """
    if not isinstance(dt, datetime):
        raise AssertionError(
            "signing time is not a datetime; "
            f"got {type(dt).__name__}: {dt!r}"
        )
    if dt.tzinfo is None:
        raise AssertionError(
            f"signing time is naive (no timezone); got {dt!r}"
        )
    try:
        offset = dt.utcoffset()
    except Exception as exc:
        raise HarnessError(
            f"cannot read UTC offset of signing time {dt!r}: {exc}"
        ) from exc
    if offset is None:
        raise AssertionError(
            f"signing time tzinfo does not supply a UTC offset: {dt!r}"
        )
    if offset != timedelta(0):
        raise AssertionError(
            f"signing time is not UTC (offset={offset!r}): {dt!r}"
        )
    print(f"aware UTC datetime={dt.isoformat()}", flush=True)
    return dt


def require_returned_signing_time(
    result: CallResult, expected_value: Any, instant: datetime
) -> tuple[Any, datetime]:
    """Successful recover/load that asked for the signing time."""
    pair = as_pair(require_value(result))
    value, dt = pair
    if value != expected_value:
        raise AssertionError(
            "asked-for signing time pair first item "
            f"{value!r} (type={type(value)!r}) != {expected_value!r}"
        )
    aware = require_aware_utc(dt)
    if aware != instant:
        raise AssertionError(
            "returned signing time "
            f"{aware.isoformat()} != frozen signing instant {instant.isoformat()}"
        )
    print(
        f"returned signing time value={value!r} dt={aware.isoformat()} "
        f"instant={instant.isoformat()}",
        flush=True,
    )
    return value, aware


def datetimes_on_failure(exc: BaseException) -> list[datetime]:
    """Return the failure's stated ``date_signed`` attribute when it is a datetime.

    A missing attribute or ``None`` means the signing time is absent.
    """
    value = getattr(exc, "date_signed", None)
    found = [value] if isinstance(value, datetime) else []
    print(
        f"failure date_signed={[d.isoformat() for d in found]}",
        flush=True,
    )
    return found


def require_signing_time_on_failure(
    exc: BaseException, instant: datetime | None = None
) -> datetime:
    """Require a timezone-aware UTC datetime on the failure object.

    Raises if none is present — never returns ``None`` to mean absent.
    """
    found = datetimes_on_failure(exc)
    if not found:
        raise AssertionError(
            "failure object's date_signed carries no signing-time datetime"
        )
    aware: list[datetime] = []
    errors: list[str] = []
    for dt in found:
        try:
            aware.append(require_aware_utc(dt))
        except AssertionError as exc_aware:
            errors.append(str(exc_aware))
    if not aware:
        raise AssertionError(
            "failure carries datetime field(s) but none is timezone-aware "
            f"UTC; errors={errors!r}"
        )
    if instant is not None:
        matched = [dt for dt in aware if dt == instant]
        if not matched:
            raise AssertionError(
                "failure signing time "
                f"{[dt.isoformat() for dt in aware]} != "
                f"frozen signing instant {instant.isoformat()}"
            )
        return matched[0]
    return aware[0]


def require_signing_time_absent(exc: BaseException) -> None:
    """Require that no datetime is present on the failure object.

    Probe failure already raised inside :func:`datetimes_on_failure`.
    """
    found = datetimes_on_failure(exc)
    if found:
        raise AssertionError(
            "signing-time field must be absent; "
            f"found {[dt.isoformat() for dt in found]}"
        )
    print("signing-time field absent", flush=True)


def require_expired_recovery(
    result: CallResult,
    *,
    payload: str | bytes | None = None,
    instant: datetime | None = None,
) -> BaseException:
    """Expired recover: failure + original payload bytes + signing time."""
    exc = require_recovery_failure(result)
    if payload is not None:
        payload_carried_on_failure(exc, expected_bytes(payload))
    require_signing_time_on_failure(exc, instant)
    print("classified as expired recovery", flush=True)
    return exc


def require_expired_load(
    result: CallResult,
    *,
    token: str | bytes,
    expected_object: Any,
    instant: datetime | None = None,
) -> BaseException:
    """Expired load: failure + inspected payload decodes + signing time."""
    exc = require_load_failure(result)
    require_recovered_from_failure(exc, expected_object, token=token)
    require_signing_time_on_failure(exc, instant)
    print("classified as expired load", flush=True)
    return exc


def _token_kind_sep(token: str | bytes) -> tuple[str | bytes, str | bytes]:
    if isinstance(token, bytes):
        return token, DEFAULT_SEPARATOR
    if isinstance(token, str):
        return token, TEXT_SEPARATOR
    raise HarnessError(f"token is not text or bytes: {type(token)!r}")


def _as_same_kind(value: str | bytes, token: str | bytes) -> str | bytes:
    if isinstance(token, bytes):
        return value if isinstance(value, bytes) else as_bytes(value)
    if isinstance(token, str):
        return value if isinstance(value, str) else as_text(value)
    raise HarnessError(f"token is not text or bytes: {type(token)!r}")


def require_three_part_layout(token: str | bytes, payload: str | bytes) -> Any:
    """Require payload, then separator, then a non-empty time field, then signature.

    The payload prefix is the *entire* original payload (including any
    separator bytes it contains), then one separator. Does not publish a
    split algorithm as a product contract.
    """
    token_v, sep = _token_kind_sep(token)
    payload_v = _as_same_kind(payload, token)
    prefix = payload_v + sep  # type: ignore[operator]
    if not token_v.startswith(prefix):  # type: ignore[union-attr]
        raise AssertionError(
            "timestamped token is not entire-payload-then-separator-then-time: "
            f"payload={payload_v!r} token_prefix={token_v[: len(prefix) + 12]!r}"
        )
    rest = token_v[len(prefix) :]
    if sep not in rest:
        raise AssertionError(
            "timestamped token has no time field between payload and signature; "
            f"rest={rest!r}"
        )
    time_field, signature = rest.split(sep, 1)  # type: ignore[arg-type]
    if not time_field:
        raise AssertionError("time field between payload and signature is empty")
    if not signature:
        raise AssertionError("signature section after the time field is empty")
    print(
        f"three-part layout payload_len={len(payload_v)} "
        f"time_len={len(time_field)} sig_len={len(signature)}",
        flush=True,
    )
    return time_field


def _split_three(token: str | bytes) -> tuple[Any, Any, Any, Any]:
    """Fixture split: payload, time field, signature. Raises if not three parts."""
    token_v, sep = _token_kind_sep(token)
    if sep not in token_v:
        raise HarnessError(
            f"token has no separator {sep!r}; cannot locate a time field"
        )
    left, signature = rsplit_once(token_v, sep)
    if sep not in left:
        raise HarnessError(
            "token has only two sections; no middle time field to replace"
        )
    payload, time_field = rsplit_once(left, sep)
    if not time_field:
        raise HarnessError("middle time field is empty")
    if not signature:
        raise HarnessError("signature section is empty")
    return payload, time_field, signature, sep


def replace_time_field(token: str | bytes, new_field: str | bytes) -> str | bytes:
    """Replace only the middle time field. Does not re-sign."""
    payload, old_field, signature, sep = _split_three(token)
    replacement = _as_same_kind(new_field, token)
    if replacement == old_field:
        raise HarnessError(
            "replacement time field equals the existing field; "
            "the token would be unchanged"
        )
    changed = payload + sep + replacement + sep + signature
    print(
        f"replaced time field old_len={len(old_field)} new_len={len(replacement)}",
        flush=True,
    )
    return changed


def replace_in_timestamped_payload(
    token: bytes, old: bytes, new: bytes
) -> bytes:
    """Replace *old* with *new* in the payload section only (not time/signature)."""
    from _harness import replace_bytes

    payload, time_field, signature, sep = _split_three(require_bytes(token))
    payload_b = require_bytes(payload)
    changed = require_bytes(replace_bytes(payload_b, old, new, count=1))
    sep_b = require_bytes(sep)
    return (
        changed
        + sep_b
        + require_bytes(time_field)
        + sep_b
        + require_bytes(signature)
    )


def dummy_undecodable_time_suffix() -> bytes:
    """L173 fixture: a dummy time-looking suffix that does not decode to a time."""
    return DUMMY_UNDECODABLE_SUFFIX


def _product_time_field(signer: Any, dummy: bytes) -> bytes:
    """Middle time field this helper just emitted. Not a product API."""
    token = sign_value(signer, dummy)
    field = require_three_part_layout(token, dummy)
    return require_bytes(field)


def in_range_time_field(signer: Any) -> bytes:
    """L174 contrast: a time field this helper emitted at an in-range instant.

    Freezes the clock at a convertible Unix epoch and reads the middle
    field of a freshly signed token. Epoch 0 is skipped: some integer
    encodings of zero are empty, which is not a time field. Does not
    spell the field as this checkout's URL-safe base64 of the integer
    bytes.
    """
    dummy = b"inr-" + secrets.token_hex(8).encode("ascii")
    # Non-zero so the middle field cannot be the empty encoding of 0.
    epoch = 1
    datetime.fromtimestamp(epoch, tz=timezone.utc)
    with frozen_clock(epoch):
        field = _product_time_field(signer, dummy)
    print(
        f"in-range time field from helper at epoch={epoch} field={field!r}",
        flush=True,
    )
    return field


def out_of_range_time_field(signer: Any) -> bytes:
    """L174 fixture: a time field this helper emitted that is not a calendar date.

    The sealed clock helper refuses to start at an overflow epoch because
    it prints a calendar instant. Freeze at a last-year instant, tick past
    the last convertible date, then read the middle field this helper
    itself just signed. Does not encode a chosen overflow epoch with this
    checkout's wire spelling.
    """
    dummy = b"oor-" + secrets.token_hex(8).encode("ascii")
    base = datetime(9999, 12, 1, tzinfo=timezone.utc)
    for extra_seconds in (86400 * 400, 86400 * 4000, 10**10, 10**12):
        with frozen_clock(base) as clock:
            clock.tick(extra_seconds)
            used_epoch = clock.epoch
            field = _product_time_field(signer, dummy)
        try:
            datetime.fromtimestamp(used_epoch, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            print(
                "out-of-range time field from helper "
                f"epoch={used_epoch} field={field!r}",
                flush=True,
            )
            return field
    raise HarnessError(
        "could not freeze a clock past the last calendar date for the "
        "out-of-range time-field fixture"
    )


def arrange_missing_timestamp_token(
    value: str | bytes, *, secret: str | bytes
) -> bytes:
    """FP-01 non-timestamped signer token (payload + signature, no time field)."""
    signer = make_signer(secret)
    token = sign_value(signer, value)
    print(
        f"arranged non-timestamped token payload={expected_bytes(value)!r} "
        f"token_len={len(token)}",
        flush=True,
    )
    return token


def arrange_dummy_suffix_token(
    value: str | bytes, *, secret: str | bytes, suffix: bytes | None = None
) -> bytes:
    """L173: non-timestamped signer signs payload + period + dummy suffix."""
    dummy = dummy_undecodable_time_suffix() if suffix is None else suffix
    payload = expected_bytes(value) + DEFAULT_SEPARATOR + dummy
    signer = make_signer(secret)
    token = sign_value(signer, payload)
    print(
        f"arranged dummy-suffix token payload={payload!r} token_len={len(token)}",
        flush=True,
    )
    return token


def arrange_replaced_out_of_range_token(
    signer: Any, value: str | bytes
) -> bytes:
    """L174: timestamped sign, then replace only the time field. Do not re-sign."""
    token = sign_value(signer, value)
    require_three_part_layout(token, expected_bytes(value))
    changed = replace_time_field(token, out_of_range_time_field(signer))
    if not isinstance(changed, bytes):
        raise HarnessError(
            f"replaced token is not bytes; got {type(changed)!r}"
        )
    print(
        f"arranged out-of-range-replaced token token_len={len(changed)}",
        flush=True,
    )
    return changed


def arrange_replaced_in_range_token(
    signer: Any, value: str | bytes
) -> bytes:
    """Same replace-without-re-sign as L174, but the field is a calendar date.

    The signature is also broken. A correct helper still decodes the
    time field, so this refusal must carry a signing-time datetime —
    unlike an out-of-range replacement.
    """
    token = sign_value(signer, value)
    require_three_part_layout(token, expected_bytes(value))
    changed = replace_time_field(token, in_range_time_field(signer))
    if not isinstance(changed, bytes):
        raise HarnessError(
            f"replaced token is not bytes; got {type(changed)!r}"
        )
    print(
        f"arranged in-range-replaced token token_len={len(changed)}",
        flush=True,
    )
    return changed


# Failure kinds, read from the stated exception classes (and, for the
# timestamp kinds, the `reason` attribute the Contract states).
FAILURE_KINDS = (
    "signature",
    "time-signature",
    "missing-timestamp",
    "malformed-timestamp",
    "expired",
    "payload",
)
MISSING_REASON = "missing"
MALFORMED_REASON = "malformed"
_NO_REASON_ATTR = object()


def failure_kind(exc: BaseException) -> str:
    """Classify a refusal by its stated exception class.

    The three non-expired ``BadTimeSignature`` kinds are told apart by
    the ``reason`` attribute the Contract states: ``"missing"`` for a
    missing timestamp, ``"malformed"`` for a malformed timestamp, ``None``
    for a time-signature failure. Message text is not consulted. Raises
    if the failure is none of the stated failure classes.
    """
    import signtoken

    if isinstance(exc, signtoken.SignatureExpired):
        kind = "expired"
    elif isinstance(exc, signtoken.BadTimeSignature):
        reason = getattr(exc, "reason", _NO_REASON_ATTR)
        if reason is _NO_REASON_ATTR:
            raise AssertionError(
                "BadTimeSignature refusal has no `reason` attribute; "
                f"type={type(exc).__name__} message={str(exc)!r}"
            )
        if reason == MISSING_REASON:
            kind = "missing-timestamp"
        elif reason == MALFORMED_REASON:
            kind = "malformed-timestamp"
        elif reason is None:
            kind = "time-signature"
        else:
            raise AssertionError(
                "BadTimeSignature `reason` is not 'missing', 'malformed' or "
                f"None; got {reason!r}"
            )
    elif isinstance(exc, signtoken.BadSignature):
        kind = "signature"
    elif isinstance(exc, signtoken.BadPayload):
        kind = "payload"
    else:
        raise AssertionError(
            "refusal is not one of the stated failure classes; "
            f"got {type(exc).__name__}: {exc!r}"
        )
    print(f"failure kind={kind} type={type(exc).__name__}", flush=True)
    return kind


def require_failure_kind(exc: BaseException, kind: str) -> BaseException:
    if kind not in FAILURE_KINDS:
        raise HarnessError(f"unknown failure kind {kind!r}")
    got = failure_kind(exc)
    assert got == kind, (
        f"refusal is a {got} failure, expected {kind}; "
        f"type={type(exc).__name__} message={str(exc)!r}"
    )
    return exc


def require_distinct_failure_kinds(
    first: BaseException,
    second: BaseException,
    *,
    expect: tuple[str, str],
) -> None:
    """Require two refusals to be the two named, different failure kinds."""
    left_kind, right_kind = expect
    assert left_kind != right_kind, "expected kinds must differ"
    require_failure_kind(first, left_kind)
    require_failure_kind(second, right_kind)


def assert_signature_mismatch_not_missing_timestamp(
    mismatch: BaseException,
    missing: BaseException,
) -> None:
    """L170: different-secret non-timestamped refusal is not a missing timestamp.

    The name carries ``assert`` so an imported call is a check the suite
    bail-out audit can see; ``require_*`` imported from another module is not.
    """
    require_distinct_failure_kinds(
        mismatch, missing, expect=("signature", "missing-timestamp")
    )
    print(
        "different-secret non-timestamped refusal is a signature mismatch, "
        "not a missing timestamp",
        flush=True,
    )


require_signature_mismatch_not_missing_timestamp = (
    assert_signature_mismatch_not_missing_timestamp
)


def make_none_derivation_timestamped_serializer(*args: Any, **kwargs: Any) -> Any:
    """Timestamped serialize-and-sign helper under the ``none`` scheme.

    FP-02 via L158: under ``none`` the salt is not mixed in.
    """
    signer_kwargs = dict(kwargs.pop("signer_kwargs", None) or {})
    signer_kwargs["key_derivation"] = "none"
    return make_timestamped_serializer(*args, signer_kwargs=signer_kwargs, **kwargs)


def require_none_derivation_default_salt_load(
    helper: Any, token: str | bytes, expected: Any
) -> Any:
    """Under ``none``, a dump that passed salt ``other`` still loads by default.

    Refusal is an assertion failure, not an unclassifiable harness error.
    """
    result = load_object_call(helper, token)
    if result.exception is not None:
        raise AssertionError(
            "under the none key-derivation scheme, a timestamped dump that "
            "passed salt 'other' must still load under the helper's default "
            f"salt; refused with {type(result.exception).__name__}: "
            f"{result.exception!r}"
        )
    loaded = require_load_success(result, expected=expected)
    print(
        "none derivation default-salt load recovered "
        f"type={type(loaded).__name__} value={loaded!r}",
        flush=True,
    )
    return loaded


def require_expired_not_signature_mismatch(
    expired: BaseException,
    mismatch: BaseException,
) -> None:
    """Require an expired refusal and a time-signature mismatch to be those kinds."""
    require_distinct_failure_kinds(
        expired, mismatch, expect=("expired", "time-signature")
    )
    print(
        "expired refusal is a distinct kind from signature mismatch",
        flush=True,
    )
