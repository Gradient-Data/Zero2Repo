# feature: F03
"""Observation helpers for time-based one-time passwords (FP-03).

Helpers classify constructor, current-clock / at-instant emit, check,
and matching-step outcomes. They never return ``None`` to mean "the
observation could not be classified". Named secrets, instants, and
codes are fixed inputs of this suite. HMAC / TOTP is never
reimplemented here.
"""

from __future__ import annotations

import base64
import math
import secrets
from collections.abc import Collection
from typing import Any

import F02_helpers as _f02
from _harness import CallResult, HarnessError, call_method, require_text

# frozen-clock vector.
FROZEN_UNIX = 1297553958
FROZEN_PLUS_STEP = FROZEN_UNIX + 30
FROZEN_CODE = "102705"

# six-digit RFC times (leading zeros kept).
RFC_SIX_DIGIT = (
    (1111111111, "050471"),
    (1234567890, "005924"),
    (2000000000, "279037"),
)

# RFC 6238 Appendix B eight-digit tables.
RFC6238_TIMES = (59, 1111111109, 1111111111, 1234567890, 2000000000, 20000000000)
RFC6238_SHA1_CODES = (
    "94287082",
    "07081804",
    "14050471",
    "89005924",
    "69279037",
    "65353130",
)
RFC6238_SHA256_CODES = (
    "46119246",
    "68084774",
    "67062674",
    "91819424",
    "90698825",
    "77737706",
)
RFC6238_SHA512_CODES = (
    "90693936",
    "25091201",
    "99943326",
    "93441116",
    "38618901",
    "47863826",
)
RFC6238_SHA1_TABLE = tuple(zip(RFC6238_TIMES, RFC6238_SHA1_CODES))
RFC6238_SHA256_TABLE = tuple(zip(RFC6238_TIMES, RFC6238_SHA256_CODES))
RFC6238_SHA512_TABLE = tuple(zip(RFC6238_TIMES, RFC6238_SHA512_CODES))

# ASCII inputs that the constructor consumes as base32.
SHA256_ASCII_KEY = "12345678901234567890123456789012"
SHA512_ASCII_KEY = (
    "1234567890123456789012345678901234567890123456789012345678901234"
)

# 60-second step on GEZDGNBV.
SIXTY_AT_30 = "734055"
SIXTY_AT_60 = "662488"

# ABCDEFGH at Unix 200, offsets and window.
ABCDEFGH_SECRET = "ABCDEFGH"
OFFSET_INSTANT = 200
OFFSET_0_CODE = "028307"
OFFSET_MINUS_1_CODE = "451564"
OFFSET_PLUS_1_CODE = "681610"
WINDOW_REJECT_CODE = "195979"
MATCHING_STEP_MINUS_1 = 5
MATCHING_STEP_ON = 6
MATCHING_STEP_PLUS_1 = 7

# epoch-step success / Unix −30 refusal.
EPOCH_MINUS_1 = -1
EPOCH_MINUS_29_5 = -29.5
EPOCH_MINUS_30 = -30
EPOCH_STEP_CODE = "755224"

# default time-step length.
DEFAULT_STEP_SECONDS = 30

# Public current-clock emit and matching-step entries on the time helper.
# Emit-at-instant / check names stay on the sealed F02 module.
NOW_ENTRY = "now"
MATCHING_STEP_ENTRY = "verify_and_get_timecode"

# Named instants the unpublished Unix picker must not land on (and whose
# default 30-second cells are excluded). Includes the float −29.5.
NAMED_UNIX_INSTANTS = frozenset(
    {
        FROZEN_UNIX,
        FROZEN_PLUS_STEP,
        1111111111,
        1234567890,
        2000000000,
        59,
        1111111109,
        20000000000,
        30,
        60,
        OFFSET_INSTANT,
        EPOCH_MINUS_1,
        EPOCH_MINUS_29_5,
        EPOCH_MINUS_30,
    }
)

NAMED_NEGATIVE_WINDOWS = frozenset({-1})
NAMED_WINDOWS = frozenset({0, 1})

# Band origin far from every named 30-second cell above.
_UNPUBLISHED_UNIX_ORIGIN = 8_765_432


def _default_step_start(instant: float) -> int:
    """Return the start of the default 30-second half-open cell of *instant*."""
    return int(math.floor(float(instant) / DEFAULT_STEP_SECONDS) * DEFAULT_STEP_SECONDS)


def _named_default_step_starts() -> frozenset[int]:
    return frozenset(_default_step_start(instant) for instant in NAMED_UNIX_INSTANTS)


def _is_decimal_code_string(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    return all(ch in _f02.DECIMAL_ALPHABET for ch in value)


def ascii_key_as_base32(ascii_key: str) -> str:
    """Encode a suite-named ASCII key as base32 for construction.

    The SHA256 / SHA512 secrets are the base32 form of a
    named ASCII string. Encoding failure raises — never a sentinel.
    The base32 spelling is an input form, not a product output golden.
    """
    if not isinstance(ascii_key, str) or not ascii_key:
        raise HarnessError(
            f"ascii_key_as_base32 ascii_key is not text: {ascii_key!r}"
        )
    try:
        raw = ascii_key.encode("ascii")
    except UnicodeEncodeError as exc:
        raise HarnessError(
            f"ascii_key_as_base32 cannot encode as ASCII: {ascii_key!r}"
        ) from exc
    try:
        encoded = base64.b32encode(raw).decode("ascii")
    except (ValueError, UnicodeDecodeError) as exc:
        raise HarnessError(
            f"ascii_key_as_base32 cannot form base32 from {ascii_key!r}: {exc}"
        ) from exc
    if not encoded:
        raise HarnessError(
            "ascii_key_as_base32 produced empty base32; "
            f"input_len={len(ascii_key)}"
        )
    print(
        f"ascii_key_as_base32 input_len={len(ascii_key)} "
        f"base32_len={len(encoded)}",
        flush=True,
    )
    return encoded


def emit_current_clock(helper: object) -> CallResult:
    """Drive the public current-clock emit entry (no instant argument).

    Must run inside ``frozen_clock``. Uses ``isolate=False`` so the
    frozen process clock is the one the entry reads.
    """
    return call_method(helper, NOW_ENTRY, isolate=False)


def emit_for_instant(
    helper: object,
    instant: Any,
    offset: int = 0,
    *,
    isolate: bool = True,
) -> CallResult:
    """Drive the public emit entry at *instant* plus a whole-step *offset*."""
    return call_method(helper, _f02.EMIT_ENTRY, instant, offset, isolate=isolate)


def check_at_instant(
    helper: object,
    candidate: str,
    instant: Any,
    window: int = 0,
    *,
    isolate: bool = True,
) -> CallResult:
    """Drive the public check entry at an explicit *instant*."""
    return call_method(
        helper,
        _f02.CHECK_ENTRY,
        candidate,
        instant,
        window,
        isolate=isolate,
    )


def check_current_clock(
    helper: object,
    candidate: str,
    window: int = 0,
) -> CallResult:
    """Drive the public check entry with no instant (current clock).

    Must run inside ``frozen_clock``. Uses ``isolate=False``.
    """
    return call_method(
        helper,
        _f02.CHECK_ENTRY,
        candidate,
        valid_window=window,
        isolate=False,
    )


def matching_step_at(
    helper: object,
    candidate: str,
    instant: Any,
    window: int = 0,
    *,
    isolate: bool = True,
) -> CallResult:
    """Drive the public matching-time-step check at *instant*."""
    return call_method(
        helper,
        MATCHING_STEP_ENTRY,
        candidate,
        instant,
        window,
        isolate=isolate,
    )


def success_carrier_at(
    helper: object,
    instant: Any,
    window: int = 0,
    *,
    isolate: bool = True,
) -> Any:
    """Return the check outcome of the code just emitted at *instant*.

    Emit or check failure raises — never a sentinel. Window contrasts
    still compare reject arms against the window-0 carrier.
    """
    emitted = emit_for_instant(helper, instant, isolate=isolate)
    code = _f02._require_decimal_text(
        require_text(emitted),
        label="success-carrier-at emit",
    )
    print(
        f"success-carrier-at instant={instant!r} window={window} code={code!r}",
        flush=True,
    )
    return _f02.require_check_returned(
        check_at_instant(helper, code, instant, window=window, isolate=isolate)
    )


def success_carrier_current(helper: object, window: int = 0) -> Any:
    """Return the current-clock check outcome of the current-clock code.

    Emit or check failure raises — never a sentinel. Must run inside
    the same ``frozen_clock`` as the surrounding current-clock arms.
    """
    emitted = emit_current_clock(helper)
    code = _f02._require_decimal_text(
        require_text(emitted),
        label="success-carrier-current emit",
    )
    print(
        f"success-carrier-current window={window} code={code!r}",
        flush=True,
    )
    return _f02.require_check_returned(
        check_current_clock(helper, code, window=window)
    )


def require_step_number(result: CallResult, expected: int) -> int:
    """Require a matching-step check returned the named time-step integer.

    The check must return (not abort). The value must be a non-bool
    ``int`` equal to *expected* (5 / 6 / 7 on the named Unix-200 row).
    """
    if type(expected) is not int:
        raise HarnessError(
            f"require_step_number expected is not a named step: {expected!r}"
        )
    value = _f02.require_check_returned(result)
    if type(value) is not int:
        raise AssertionError(
            "matching-step check did not return a time-step number: "
            f"type={type(value).__name__} value={value!r} expected={expected!r}"
        )
    assert value == expected, (
        "matching-step number is not the named integer: "
        f"expected={expected!r} got={value!r}"
    )
    print(f"step number ok expected={expected!r}", flush=True)
    return value


def require_a_step_number(result: CallResult) -> int:
    """Require a matching-step check returned some non-bool int.

    Does not pin the integer against 5 / 6 / 7.
    """
    value = _f02.require_check_returned(result)
    if type(value) is not int:
        raise AssertionError(
            "matching-step check did not return a time-step number: "
            f"type={type(value).__name__} value={value!r}"
        )
    print(f"step number present value={value!r}", flush=True)
    return value


def require_no_step_number(result: CallResult) -> Any:
    """Require a matching-step check returned without a time-step int.

    Must return (not abort) so this is distinguishable from a negative
    window abort. ``False`` (bool) is not a time-step number. Returning
    ``0`` or ``99`` still is a time-step number.
    """
    value = _f02.require_check_returned(result)
    if type(value) is int:
        raise AssertionError(
            "matching-step check handed back a time-step number: "
            f"{value!r}"
        )
    assert value is False, (
        "a rejected matching-step check must return False "
        f"(Interface Contract form): got={value!r}"
    )
    print(
        f"no step number; type={type(value).__name__} value={value!r}",
        flush=True,
    )
    return value


def require_negative_window_aborted(result: CallResult) -> BaseException:
    """Require a matching-step negative window aborted with no step int.

    The caller observes a failure (any exception; class
    and message are not pinned) and the value is not a non-bool int.
    Returning a negative result without failing is not this arm.
    """
    if result.exception is None:
        raise AssertionError(
            "negative matching window returned instead of aborting: "
            f"type={type(result.value).__name__} value={result.value!r}"
        )
    if type(result.value) is int:
        raise AssertionError(
            "negative matching window aborted but still handed back "
            f"a time-step number: {result.value!r}"
        )
    print(
        "negative matching window aborted; no step number "
        f"(carrier={type(result.exception).__name__})",
        flush=True,
    )
    return result.exception


def require_negative_instant_refused(result: CallResult) -> None:
    """Require emit at a negative instant did not hand back a code string.

    Unix −30 does not succeed; no code is returned. Either a
    captured exception whose value is not a decimal code string, or a
    return whose value is not a decimal code string, counts. A
    configured-width decimal string does not. Exception class is not
    pinned. Checking is never probed to interpret this outcome.
    """
    if _is_decimal_code_string(result.value):
        raise AssertionError(
            "negative instant still handed back a decimal code string: "
            f"{result.value!r}"
        )
    if result.exception is not None:
        print(
            "negative instant refused; no code string returned "
            f"(carrier={type(result.exception).__name__})",
            flush=True,
        )
        return
    print(
        "negative instant refused; no code string returned "
        f"(value_type={type(result.value).__name__} value={result.value!r})",
        flush=True,
    )


def unpublished_unix_instant(forbidden: Collection[Any]) -> int:
    """Pick a Unix instant outside every named default 30-second cell.

    *forbidden* is merged with the named instants. The default 30-second
    half-open cell of each named instant, and the cell immediately
    before it (so T+30 is not a named cell), are excluded. Does not
    draw from (30, 60) or (−30, 0).
    """
    named_starts = _named_default_step_starts()
    blocked_starts = set(named_starts)
    for start in named_starts:
        blocked_starts.add(start - DEFAULT_STEP_SECONDS)
    merged = set(forbidden) | {
        n for n in NAMED_UNIX_INSTANTS if type(n) is int
    }
    width = _f02._UNPUBLISHED_BAND + 16
    band = list(range(_UNPUBLISHED_UNIX_ORIGIN, _UNPUBLISHED_UNIX_ORIGIN + width))

    def _eligible(n: int) -> bool:
        if type(n) is not int or n < 0:
            return False
        return _default_step_start(n) not in blocked_starts

    chosen = _f02._pick_unpublished_int(
        band,
        merged,
        predicate=_eligible,
        label="unpublished_unix_instant",
    )
    if chosen in merged or _default_step_start(chosen) in named_starts:
        raise HarnessError(
            "unpublished_unix_instant landed on a named instant or "
            f"named 30-second cell: {chosen!r}"
        )
    print(
        f"unpublished_unix_instant chosen={chosen} "
        f"step_start={_default_step_start(chosen)}",
        flush=True,
    )
    return chosen


def unpublished_unix_in_open_interval(
    low: float,
    high: float,
    forbidden: Collection[int],
) -> int:
    """Pick an integer in the open interval (*low*, *high*).

    Caller passes named instants themselves (not default 30-second
    cells). Drawing an endpoint or a forbidden value raises.
    """
    try:
        low_f = float(low)
        high_f = float(high)
    except (TypeError, ValueError) as exc:
        raise HarnessError(
            f"open-interval bounds are not numbers: {low!r} {high!r}"
        ) from exc
    if not (low_f < high_f):
        raise HarnessError(
            f"open interval is empty or reversed: ({low!r}, {high!r})"
        )
    first = math.floor(low_f) + 1
    last = math.ceil(high_f) - 1
    if last < first:
        raise HarnessError(
            f"open interval ({low!r}, {high!r}) holds no integer"
        )
    band = list(range(first, last + 1))
    forbidden_set = set(forbidden)

    def _in_open(n: int) -> bool:
        return type(n) is int and n > low_f and n < high_f

    chosen = _f02._pick_unpublished_int(
        band,
        forbidden_set,
        predicate=_in_open,
        label="unpublished_unix_in_open_interval",
    )
    if chosen <= low_f or chosen >= high_f or chosen in forbidden_set:
        raise HarnessError(
            "unpublished_unix_in_open_interval landed on an endpoint "
            f"or a forbidden instant: {chosen!r} interval=({low!r}, {high!r}) "
            f"forbidden={sorted(forbidden_set)!r}"
        )
    print(
        f"unpublished_unix_in_open_interval chosen={chosen} "
        f"interval=({low!r}, {high!r})",
        flush=True,
    )
    return chosen


def unpublished_negative_window(forbidden: Collection[int]) -> int:
    """Pick a negative acceptance window other than the named −1."""
    merged = set(forbidden) | NAMED_NEGATIVE_WINDOWS
    band = list(range(-2, -2 - _f02._UNPUBLISHED_BAND, -1))
    return _f02._pick_unpublished_int(
        band,
        merged,
        predicate=lambda n: type(n) is int and n < 0,
        label="unpublished_negative_window",
    )


def unpublished_positive_window(forbidden: Collection[int]) -> int:
    """Pick a positive acceptance window greater than the named 1.

    The matching step is 6 for the on-step code at Unix 200. A
    window larger than 6 at that row includes a negative time-step,
    which the PRD does not emit. The draw stays in (1, 6] so the PRD's
    "a positive window is accepted" is observed on the named row
    without crossing that boundary. Skips the first eligible so the
    pick is not "the integer after 1".
    """
    merged = set(forbidden) | set(NAMED_WINDOWS)
    band = list(range(2, MATCHING_STEP_ON + 1))
    eligible = [n for n in band if n not in merged and type(n) is int and n > 1]
    if len(eligible) < 2:
        raise HarnessError(
            "unpublished_positive_window band has "
            f"{len(eligible)} eligible integers; need at least 2 "
            f"(forbidden={sorted(merged)!r})"
        )
    skip = 1
    pool = eligible[skip:]
    if not pool:
        raise HarnessError(
            "unpublished_positive_window pool after skipping the "
            f"prefix is empty: eligible={eligible!r}"
        )
    chosen = secrets.SystemRandom().choice(pool)
    if chosen in merged or type(chosen) is not int or chosen <= 1:
        raise HarnessError(
            "unpublished_positive_window produced a named or "
            f"out-of-band value: {chosen!r} (forbidden={sorted(merged)!r})"
        )
    if chosen > MATCHING_STEP_ON:
        raise HarnessError(
            "unpublished_positive_window exceeded the named on-step "
            f"number {MATCHING_STEP_ON}: {chosen!r}"
        )
    print(f"unpublished_positive_window chosen={chosen}", flush=True)
    return chosen
