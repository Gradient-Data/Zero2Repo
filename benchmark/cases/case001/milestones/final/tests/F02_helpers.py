# feature: F02
"""Observation helpers for native TOML scalar types (FP-02).

Classifiers raise when the object cannot be typed. They never return
``None`` to mean "not this kind" or "timezone missing".
"""

from __future__ import annotations

import math
import uuid
from datetime import date, datetime, time, timedelta
from typing import Any

from _harness import CallResult, HarnessError
from F01_helpers import require_decode_failure

_RESERVED_BASE_DIGITS = {
    2: frozenset({"0", "1", "101", "11010110"}),
    8: frozenset({"0", "755", "765"}),
    16: frozenset({"0", "deadbeef"}),
}


def is_bool(obj: Any) -> bool:
    """Return whether *obj* is a Boolean. ``None`` cannot be classified."""
    if obj is None:
        raise HarnessError("cannot classify None as a bool")
    return isinstance(obj, bool)


def is_int(obj: Any) -> bool:
    """Return whether *obj* is a non-Boolean integer. ``None`` cannot be classified."""
    if obj is None:
        raise HarnessError("cannot classify None as an int")
    return isinstance(obj, int) and not isinstance(obj, bool)


def is_float(obj: Any) -> bool:
    """Return whether *obj* is a float. ``None`` cannot be classified."""
    if obj is None:
        raise HarnessError("cannot classify None as a float")
    return isinstance(obj, float)


def is_str(obj: Any) -> bool:
    """Return whether *obj* is a text string. ``None`` cannot be classified."""
    if obj is None:
        raise HarnessError("cannot classify None as a str")
    return isinstance(obj, str)


def require_bool(obj: Any, expected: bool) -> bool:
    """Assert *obj* is Boolean *expected*, not an integer or string stand-in."""
    if not is_bool(obj):
        raise AssertionError(
            f"expected bool {expected!r}, got {type(obj)!r}: {obj!r}"
        )
    if obj is not expected:
        raise AssertionError(f"expected bool {expected!r}, got {obj!r}")
    return obj


def require_int(obj: Any, expected: int) -> int:
    """Assert *obj* is a non-Boolean integer equal to *expected*."""
    if not is_int(obj):
        raise AssertionError(
            f"expected non-bool int {expected!r}, got {type(obj)!r}: {obj!r}"
        )
    if obj != expected:
        raise AssertionError(f"expected integer {expected!r}, got {obj!r}")
    return obj


def require_str(obj: Any, expected: str) -> str:
    """Assert *obj* is a string equal to *expected*."""
    if not is_str(obj):
        raise AssertionError(
            f"expected str {expected!r}, got {type(obj)!r}: {obj!r}"
        )
    if obj != expected:
        raise AssertionError(f"expected string {expected!r}, got {obj!r}")
    return obj


def require_finite_float(obj: Any, expected: float) -> float:
    """Assert *obj* is a finite float equal to *expected*."""
    if not is_float(obj):
        raise AssertionError(
            f"expected finite float {expected!r}, got {type(obj)!r}: {obj!r}"
        )
    if not math.isfinite(obj):
        raise AssertionError(f"expected finite float {expected!r}, got {obj!r}")
    if obj != expected:
        raise AssertionError(f"expected float {expected!r}, got {obj!r}")
    return obj


def require_inf(obj: Any, *, negative: bool) -> float:
    """Assert *obj* is an infinity of the named sign. Requires a float first."""
    if not is_float(obj):
        raise AssertionError(
            f"expected an infinity float, got {type(obj)!r}: {obj!r}"
        )
    if not math.isinf(obj):
        raise AssertionError(f"expected an infinity, got {obj!r}")
    if negative:
        if not (obj < 0):
            raise AssertionError(f"expected negative infinity, got {obj!r}")
    elif not (obj > 0):
        raise AssertionError(f"expected positive infinity, got {obj!r}")
    return obj


def require_nan(obj: Any) -> float:
    """Assert *obj* is a NaN float. Sign bit is not observed."""
    if not is_float(obj):
        raise AssertionError(f"expected a NaN float, got {type(obj)!r}: {obj!r}")
    if not math.isnan(obj):
        raise AssertionError(f"expected a NaN, got {obj!r}")
    return obj


def require_aware_datetime(obj: Any) -> datetime:
    """Assert *obj* is a timezone-aware datetime. Naive or wrong type fails."""
    if not isinstance(obj, datetime):
        raise AssertionError(
            f"expected a timezone-aware datetime, got {type(obj)!r}: {obj!r}"
        )
    if obj.tzinfo is None or obj.utcoffset() is None:
        raise AssertionError(
            f"expected timezone-aware datetime, timezone is missing: {obj!r}"
        )
    return obj


def require_naive_datetime(obj: Any) -> datetime:
    """Assert *obj* is a timezone-naive datetime. Aware or wrong type fails."""
    if not isinstance(obj, datetime):
        raise AssertionError(
            f"expected a timezone-naive datetime, got {type(obj)!r}: {obj!r}"
        )
    if obj.tzinfo is not None:
        raise AssertionError(
            f"expected timezone-naive datetime, tzinfo is {obj.tzinfo!r}"
        )
    return obj


def require_date(obj: Any, year: int, month: int, day: int) -> date:
    """Assert *obj* is a date (not a datetime) with those calendar fields."""
    if isinstance(obj, datetime):
        raise AssertionError(
            f"expected a date with no time, got datetime {obj!r}"
        )
    if not isinstance(obj, date):
        raise AssertionError(
            f"expected a date {year:04d}-{month:02d}-{day:02d}, "
            f"got {type(obj)!r}: {obj!r}"
        )
    if obj.year != year or obj.month != month or obj.day != day:
        raise AssertionError(
            f"expected date {year:04d}-{month:02d}-{day:02d}, got "
            f"{obj.year:04d}-{obj.month:02d}-{obj.day:02d}"
        )
    return obj


def require_time(
    obj: Any, hour: int, minute: int, second: int = 0
) -> time:
    """Assert *obj* is a clock time (not a datetime). Microseconds are not pinned."""
    if isinstance(obj, datetime):
        raise AssertionError(f"expected a time with no date, got datetime {obj!r}")
    if not isinstance(obj, time):
        raise AssertionError(
            f"expected a time {hour:02d}:{minute:02d}:{second:02d}, "
            f"got {type(obj)!r}: {obj!r}"
        )
    if obj.hour != hour or obj.minute != minute or obj.second != second:
        raise AssertionError(
            f"expected time {hour:02d}:{minute:02d}:{second:02d}, got "
            f"{obj.hour:02d}:{obj.minute:02d}:{obj.second:02d}"
        )
    return obj


def require_no_document_mapping(result: CallResult) -> BaseException:
    """Require that the parse failed as the decode error (a value error).

    FP-02 illegal integer, float, string, and date-time tokens fail
    the same way as FP-04: the product's decode error, a kind of
    value error, with no document mapping. Recursion errors are not this
    carrier.
    """
    return require_decode_failure(result)


def require_utcoffset(dt: datetime, hours: int, minutes: int = 0) -> timedelta:
    """Read the UTC offset of an already-aware datetime. Naive raises."""
    if not isinstance(dt, datetime):
        raise HarnessError(
            f"require_utcoffset expected a datetime, got {type(dt)!r}"
        )
    if dt.tzinfo is None:
        raise AssertionError(
            f"cannot read utcoffset from a naive datetime: {dt!r}"
        )
    offset = dt.utcoffset()
    if offset is None:
        raise AssertionError(
            f"aware datetime {dt!r} has tzinfo but utcoffset() is None"
        )
    expected = timedelta(hours=hours, minutes=minutes)
    if offset != expected:
        raise AssertionError(
            f"expected utcoffset {expected!r}, got {offset!r} on {dt!r}"
        )
    return offset


def multiline_basic_document(key: str, body: str) -> str:
    """TOML assigning a multiline basic string. *body* is the interior only."""
    if not isinstance(key, str) or not key:
        raise HarnessError(f"multiline_basic_document key must be a non-empty str")
    if not isinstance(body, str):
        raise HarnessError(
            f"multiline_basic_document body must be str, got {type(body)!r}"
        )
    return f'{key} = """{body}"""'


def unclosed(form: str, text: str, *, key: str = "k") -> str:
    """TOML that opens one of the four string forms and never closes it."""
    openers = {
        "basic": '"',
        "literal": "'",
        "multiline_basic": '"""',
        "multiline_literal": "'''",
    }
    if form not in openers:
        raise HarnessError(
            f"unclosed form must be one of {sorted(openers)}, got {form!r}"
        )
    if not isinstance(text, str):
        raise HarnessError(f"unclosed text must be str, got {type(text)!r}")
    if not isinstance(key, str) or not key:
        raise HarnessError("unclosed key must be a non-empty str")
    return f"{key} = {openers[form]}{text}"


def base_digit_string(base: int) -> tuple[str, int]:
    """Process-local digit run for *base* 2, 8, or 16, plus ``int(digits, base)``.

    The digit string is not one of the hex/octal/binary document literals.
    It is not a TOML parse; callers still go through the string-parse entry.
    """
    if base not in (2, 8, 16):
        raise HarnessError(f"base_digit_string supports 2, 8, 16; got {base!r}")
    reserved = _RESERVED_BASE_DIGITS[base]
    seed = int(uuid.uuid4().hex[:12], 16)
    if base == 16:
        n = seed % (16**7 - 16**6) + 16**6
        digits = format(n, "x")
    elif base == 8:
        n = seed % (8**6 - 8**5) + 8**5
        digits = format(n, "o")
    else:
        n = seed % (2**14 - 2**10) + 2**10
        digits = format(n, "b")
    if digits.lower() in reserved:
        extra = "a" if base == 16 else "1"
        digits = digits + extra
    return digits, int(digits, base)
