"""Pipeline-owned sealed test helpers.

This file is the complete module. Import what you need (`from _helpers import ...`). Add a new helper here, with the imports and constants it closes over. Do not paste a sealed body into a feature file. Do not change a sealed name unless you own it and that feature's PRD was amended.
"""

from __future__ import annotations

import base64
import json
import math
import re
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from _harness import (
    UNDEFINED,
    CallResult,
    ErrorInfo,
    HarnessError,
    JsBytes,
    JsDate,
    JsFunction,
    JsMap,
    JsObject,
    JsRegexp,
    JsSet,
    JsUndefined,
    SCHEMA_CORE,
    SCHEMA_FAILSAFE,
    SCHEMA_JSON,
    SCHEMA_YAML11,
    dump,
    evaluate,
    load,
    workspace,
)

# Integers the suite's own named fixtures use. Runtime draws stay outside.
_GOLDEN_CORE_INTS = frozenset({1, 2, 42, 123})
_SUITE_NAMED_UNICODE_SCALAR = 0x1F600
_SUITE_NAMED_TAG_HANDLE = "!a1!"


def unique_token() -> str:
    """Alphanumeric fragment that is safe as a YAML key, anchor, tag, or word."""
    return "k" + uuid.uuid4().hex[:12]


def core_int_token() -> int:
    """A Core decimal integer that is not a public F01 golden."""
    for _ in range(32):
        number = 3 + (uuid.uuid4().int % 90)
        if number not in _GOLDEN_CORE_INTS:
            return number
    return 17


def distinct_core_ints(count: int) -> list[int]:
    """Return *count* distinct values from :func:`core_int_token`."""
    if count < 1:
        raise ValueError("count must be positive")
    seen: set[int] = set()
    out: list[int] = []
    guard = 0
    while len(out) < count:
        number = core_int_token()
        if number not in seen:
            seen.add(number)
            out.append(number)
        guard += 1
        if guard > 200:
            raise HarnessError("could not draw distinct Core integers")
    return out


def eight_hex_scalar() -> tuple[str, str]:
    """Return ``(eight hex digits, character)`` for a legal Unicode scalar.

    Avoids the suite-named ``U+1F600``, surrogates, and out-of-range values.
    The expected character is ``chr`` of that code point — not a YAML scan.
    """
    base = 0x1F300
    span = 0x2FF
    code = base + (uuid.uuid4().int % span)
    if code == _SUITE_NAMED_UNICODE_SCALAR:
        code = 0x1F601
    return f"{code:08X}", chr(code)


def digit_tag_handle() -> str:
    """A ``%TAG`` handle that contains a digit and is not the suite-named ``!a1!``."""
    letters = "bcdefghkmnprstwxyz"
    letter = letters[uuid.uuid4().int % len(letters)]
    digit = str(2 + uuid.uuid4().int % 8)
    handle = f"!{letter}{digit}!"
    if handle == _SUITE_NAMED_TAG_HANDLE:
        handle = "!z9!"
    return handle


def with_source_path_label(label: str) -> dict[str, Any]:
    """Sealed parse options that attach a source-path label to failure reports."""
    return {"filename": label}


def with_json_compat() -> dict[str, Any]:
    """Sealed parse options that enable JSON-parse compatibility for duplicates."""
    return {"json": True}


def observer_visible_report(error: ErrorInfo) -> str:
    """All caller-visible failure material the harness already captured.

    Raises if the report object cannot be read. Empty individual fields are
    observations, not a stand-in for "the helper could not look".
    """
    if error is None:
        raise HarnessError("failure report is missing")
    if not isinstance(error, ErrorInfo):
        raise HarnessError(
            f"failure report is not ErrorInfo: {type(error).__name__}"
        )
    parts: list[str] = [
        error.name,
        error.message,
        error.text,
    ]
    if error.reason is not None:
        parts.append(error.reason)
    if error.stack is not None:
        parts.append(error.stack)
    mark = error.mark
    if mark is not None:
        if mark.name is not None:
            parts.append(str(mark.name))
        if mark.line is not None:
            parts.append(f"line={mark.line}")
        if mark.column is not None:
            parts.append(f"column={mark.column}")
        if mark.position is not None:
            parts.append(f"position={mark.position}")
    return "\n".join(parts)


def report_has_label(error: ErrorInfo, label: str) -> bool:
    """Whether the stated failure form carries *label*.

    Reads only the error ``message`` and ``mark.name`` (Interface Contract,
    thrown failure form); a stack trace is not evidence.
    """
    if not label:
        raise ValueError("label must be a non-empty string")
    if error is None:
        raise HarnessError("failure report is missing")
    if not isinstance(error, ErrorInfo):
        raise HarnessError(
            f"failure report is not ErrorInfo: {type(error).__name__}"
        )
    in_message = bool(error.message) and label in error.message
    in_mark = error.mark is not None and error.mark.name == label
    return in_message and in_mark


def require_document(result: CallResult) -> Any:
    """Return the constructed value, or assert if the parse did not succeed."""
    if result is None:
        raise HarnessError("parse result is missing")
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"parse result is not CallResult: {type(result).__name__}"
        )
    if not result.ok:
        report = (
            observer_visible_report(result.error)
            if result.error is not None
            else "<no error payload>"
        )
        assert False, f"parse failed; report={report}"
    return result.value


def require_parse_failure(result: CallResult) -> ErrorInfo:
    """Return the failure payload, or assert if a document was produced."""
    if result is None:
        raise HarnessError("parse result is missing")
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"parse result is not CallResult: {type(result).__name__}"
        )
    if result.ok:
        assert False, (
            f"parse succeeded unexpectedly; value={result.value!r}"
        )
    if result.error is None:
        raise HarnessError("parse failed but error payload is missing")
    return result.error


def require_plain_mapping(value: Any) -> Any:
    """Return *value* if it is a constructed mapping; assert otherwise."""
    if isinstance(value, JsObject):
        return value
    if isinstance(value, dict):
        return value
    assert False, f"expected a mapping, got {type(value).__name__}: {value!r}"


def mapping_get(value: Any, key: str) -> Any:
    """Read *key* from a constructed mapping; missing key is a hard failure."""
    mapping = require_plain_mapping(value)
    if key not in mapping:
        keys = list(mapping.keys())
        assert False, f"mapping missing key {key!r}; keys={keys!r}"
    return mapping[key]


def is_number_not_string(value: Any, expected: int) -> bool:
    """True when *value* is the number *expected*, not a string or bool."""
    if isinstance(value, (bool, str)):
        return False
    if isinstance(value, (int, float)):
        return value == expected
    return False


def same_identity(left: Any, right: Any) -> bool:
    """Whether *left* and *right* are the same constructed object."""
    return left is right


def load_utf16_units(units: Sequence[int], *, multi: bool = False) -> CallResult:
    """Parse text built from UTF-16 code units inside the product process.

    Lone surrogates cannot be written through the UTF-8 request file.
    The units are assembled with ``String.fromCharCode`` and then passed
    to the public single-document or multi-document parse entry.
    """
    if not units:
        raise HarnessError("UTF-16 unit list is empty")
    cleaned: list[int] = []
    for item in units:
        if not isinstance(item, int) or item < 0 or item > 0xFFFF:
            raise HarnessError(f"not a UTF-16 code unit: {item!r}")
        cleaned.append(item)
    args = ",".join(str(code) for code in cleaned)
    entry = "loadAll" if multi else "load"
    print(f"[helpers] utf16-units entry={entry} units={cleaned!r}", flush=True)
    return evaluate(f"return lib.{entry}(String.fromCharCode({args}))")


def attempt_load_without_artifact(source: str) -> CallResult | None:
    """Single-document parse with the built library hidden from discovery.

    Returns a :class:`CallResult` when the driver ran, or ``None`` when
    the substrate could not import the library (classified: no document).
    Unclassified failures raise. Never skips.
    """
    with workspace() as ws:
        try:
            return load(source, root=ws.path)
        except FileNotFoundError as exc:
            print(f"artifact absent (missing file): {exc}", flush=True)
            return None
        except HarnessError as exc:
            print(f"artifact absent (driver): {exc}", flush=True)
            return None


def is_successful_answer_42(result: CallResult | None) -> bool:
    """Whether *result* is a successful document whose ``answer`` is 42."""
    if result is None or not result.ok:
        return False
    try:
        answer = mapping_get(result.value, "answer")
    except AssertionError:
        return False
    return is_number_not_string(answer, 42)


# ---------------------------------------------------------------------------
# F02: schema knobs, type predicates, and runtime notation tokens
# ---------------------------------------------------------------------------

YAML11_TRUE_WORDS = ("y", "Y", "yes", "Yes", "YES", "on", "On", "ON")
YAML11_FALSE_WORDS = ("n", "N", "no", "No", "NO", "off", "Off", "OFF")

_F02_SUITE_NAMED_INT_TEXTS = frozenset({
    "0123",
    "0o123",
    "0x1A",
    "0b1010",
    "1_000",
    "1:23",
    "1:99",
    "09",
    "+685230",
    "+0o123",
    "-0x1A",
})
_F02_SUITE_NAMED_FLOAT_TEXTS = frozenset({
    "12.",
    "1_000.0",
    ".5",
    "01.0",
    "+12.3",
    "1e999",
    "190:20:30.15",
    "685.230_15e+03",
    "685.23015e03",
    "6.8523015e+5",
    "685.23015e+03",
    "685230.15",
})
_F02_AVOIDED_INT_VALUES = _GOLDEN_CORE_INTS | {0, 10, 26, 83, 1000, 685230}

_IEEE_NON_NUMBER = (
    str,
    list,
    dict,
    JsObject,
    JsMap,
    JsSet,
    JsBytes,
    JsDate,
    JsFunction,
    JsRegexp,
    JsUndefined,
)


def with_failsafe_schema() -> dict[str, Any]:
    """Sealed parse options that select the Failsafe schema."""
    return {"schema": SCHEMA_FAILSAFE}


def with_json_schema() -> dict[str, Any]:
    """Sealed parse options that select the JSON schema."""
    return {"schema": SCHEMA_JSON}


def with_core_schema() -> dict[str, Any]:
    """Sealed parse options that select the Core schema."""
    return {"schema": SCHEMA_CORE}


def with_yaml11_schema() -> dict[str, Any]:
    """Sealed parse options that select the YAML 1.1 schema."""
    return {"schema": SCHEMA_YAML11}


def is_bool(value: Any, expected: bool) -> bool:
    """True when *value* is the boolean *expected* (not an int)."""
    return type(value) is bool and value is expected


def is_js_null(value: Any) -> bool:
    """True when *value* is the constructed null."""
    return value is None


def is_string_text(value: Any, text: str) -> bool:
    """True when *value* is exactly *text*, not a number or boolean."""
    return type(value) is str and value == text


def is_finite_number(value: Any, expected: float) -> bool:
    """True when *value* is the finite number *expected*, not a bool or str."""
    if isinstance(value, (bool, str)):
        return False
    if isinstance(value, (int, float)):
        if math.isnan(value) or math.isinf(value):
            return False
        return value == expected
    return False


def is_any_finite_number(value: Any) -> bool:
    """True when *value* is a finite number of any magnitude, not a bool or str."""
    if isinstance(value, (bool, str)):
        return False
    if isinstance(value, (int, float)):
        return not math.isnan(value) and not math.isinf(value)
    return False


def _as_ieee_float(value: Any, *, what: str) -> float | None:
    """Return a float observation, or None when *value* is a known non-number.

    Raises if the value cannot be classified. Never treats a read failure
    as "looked and it was not a special float".
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, _IEEE_NON_NUMBER):
        return None
    raise HarnessError(
        f"cannot classify {what}: unreadable type {type(value).__name__}"
    )


def is_pos_inf(value: Any) -> bool:
    """Whether *value* is IEEE positive infinity."""
    number = _as_ieee_float(value, what="+inf")
    if number is None or math.isnan(number):
        return False
    return math.isinf(number) and number > 0


def is_neg_inf(value: Any) -> bool:
    """Whether *value* is IEEE negative infinity."""
    number = _as_ieee_float(value, what="-inf")
    if number is None or math.isnan(number):
        return False
    return math.isinf(number) and number < 0


def is_nan_number(value: Any) -> bool:
    """Whether *value* is IEEE not-a-number."""
    number = _as_ieee_float(value, what="nan")
    if number is None:
        return False
    return math.isnan(number)


def require_sequence(value: Any) -> list:
    """Return *value* if it is a constructed sequence; assert otherwise."""
    if isinstance(value, list):
        return value
    assert False, f"expected a sequence, got {type(value).__name__}: {value!r}"


def _draw(span: int) -> int:
    if span < 1:
        raise HarnessError("draw span must be positive")
    return uuid.uuid4().int % span


def _reject_suite_named_token(text: str, value: int | None = None) -> bool:
    if text in _F02_SUITE_NAMED_INT_TEXTS or text in _F02_SUITE_NAMED_FLOAT_TEXTS:
        return True
    if value is not None and value in _F02_AVOIDED_INT_VALUES:
        return True
    return False


def oversized_decimal_token() -> str:
    """Decimal text too long to be a finite JavaScript number.

    Digit count exceeds the IEEE finite range, plus runtime jitter.
    Generation failure raises.
    """
    length = 320 + _draw(40)
    chunks: list[str] = []
    while sum(len(part) for part in chunks) < length:
        chunks.append(str(uuid.uuid4().int))
    text = "".join(chunks)[:length]
    if not text or text[0] == "0":
        text = "7" + text[1:]
    if len(text) < 309:
        raise HarnessError(
            "oversized decimal is not long enough to overflow a JS number"
        )
    if not text.isdigit():
        raise HarnessError("oversized decimal is not all digits")
    return text


def overflow_float_token() -> str:
    """Decimal-exponent text whose exponent is beyond a finite JS number.

    Not the suite-named ``1e999``. Does not reuse the oversized-integer helper.
    """
    for _ in range(32):
        coeff = 2 + _draw(7)
        exp = 400 + _draw(200)
        text = f"{coeff}e{exp}"
        if text == "1e999":
            continue
        return text
    raise HarnessError("could not draw an overflow float token")


def json_legal_decimal_token() -> tuple[str, int]:
    """JSON-legal decimal (no plus, no leading zero) and its integer value."""
    for _ in range(64):
        number = 200 + _draw(8000)
        if _reject_suite_named_token(str(number), number):
            continue
        return str(number), number
    raise HarnessError("could not draw a JSON-legal decimal")


def plus_decimal_int_token() -> str:
    """Leading-plus decimal integer text. Not the suite-named ``+685230``."""
    for _ in range(64):
        number = 200 + _draw(8000)
        text = f"+{number}"
        if _reject_suite_named_token(text, number):
            continue
        return text
    raise HarnessError("could not draw a leading-plus decimal integer")


def leading_zero_octal_token() -> tuple[str, int, int]:
    """Leading-zero token of octal digits: text, decimal value, octal value.

    Not the suite-named ``0123``. JSON keeps the text; Core uses decimal
    arithmetic; YAML 1.1 uses octal arithmetic.
    """
    for _ in range(64):
        d1 = 1 + _draw(7)
        d2 = _draw(8)
        d3 = _draw(8)
        text = f"0{d1}{d2}{d3}"
        decimal = int(text, 10)
        octal = int(text, 8)
        if _reject_suite_named_token(text, decimal) or octal in _F02_AVOIDED_INT_VALUES:
            continue
        return text, decimal, octal
    raise HarnessError("could not draw a leading-zero octal token")


def zero_o_int_token() -> tuple[str, int]:
    """``0o`` + octal digits and ``int(digits, 8)``. Not the suite-named ``0o123``."""
    for _ in range(64):
        digits = f"{1 + _draw(7)}{_draw(8)}{_draw(8)}"
        text = f"0o{digits}"
        value = int(digits, 8)
        if _reject_suite_named_token(text, value):
            continue
        return text, value
    raise HarnessError("could not draw a 0o integer token")


def hex_int_token() -> tuple[str, int]:
    """``0x`` + hex digits and ``int(digits, 16)``. Not the suite-named ``0x1A``."""
    alphabet = "0123456789ABCDEF"
    for _ in range(64):
        digits = f"{alphabet[2 + _draw(14)]}{alphabet[_draw(16)]}"
        text = f"0x{digits}"
        value = int(digits, 16)
        if _reject_suite_named_token(text, value):
            continue
        return text, value
    raise HarnessError("could not draw a 0x integer token")


def bin_int_token() -> tuple[str, int]:
    """``0b`` + bits and ``int(bits, 2)``. Not the suite-named ``0b1010``."""
    for _ in range(64):
        bits = "".join(str(_draw(2)) for _ in range(5))
        if bits == "00000" or bits == "01010":
            continue
        text = f"0b{bits}"
        value = int(bits, 2)
        if _reject_suite_named_token(text, value):
            continue
        return text, value
    raise HarnessError("could not draw a 0b integer token")


def plus_zero_o_int_token() -> tuple[str, int]:
    """``+0o`` + octal digits and ``int(digits, 8)``. Not the suite-named ``+0o123``."""
    for _ in range(64):
        text, value = zero_o_int_token()
        signed = f"+{text}"
        if _reject_suite_named_token(signed, value):
            continue
        return signed, value
    raise HarnessError("could not draw a +0o integer token")


def minus_hex_int_token() -> tuple[str, int]:
    """``-0x`` + hex digits and ``-int(digits, 16)``. Not the suite-named ``-0x1A``."""
    for _ in range(64):
        text, value = hex_int_token()
        signed = f"-{text}"
        negated = -value
        if _reject_suite_named_token(signed, negated):
            continue
        return signed, negated
    raise HarnessError("could not draw a -0x integer token")


def underscore_int_token() -> tuple[str, int]:
    """Underscored decimal and the integer after removing underscores.

    Not the suite-named ``1_000``.
    """
    for _ in range(64):
        left = 2 + _draw(8)
        right = 100 + _draw(900)
        text = f"{left}_{right}"
        value = int(text.replace("_", ""), 10)
        if _reject_suite_named_token(text, value):
            continue
        return text, value
    raise HarnessError("could not draw an underscored integer")


def sexagesimal_int_token() -> tuple[str, int]:
    """``a:b`` with minutes < 60 and value ``a * 60 + b``. Not ``1:23``."""
    for _ in range(64):
        hours = 2 + _draw(8)
        minutes = _draw(60)
        text = f"{hours}:{minutes}"
        value = hours * 60 + minutes
        if _reject_suite_named_token(text, value):
            continue
        return text, value
    raise HarnessError("could not draw a sexagesimal integer")


def illegal_sexagesimal_token() -> str:
    """``a:b`` with minutes >= 60. Not the suite-named ``1:99``."""
    for _ in range(64):
        hours = 2 + _draw(8)
        minutes = 60 + _draw(40)
        text = f"{hours}:{minutes}"
        if _reject_suite_named_token(text):
            continue
        return text
    raise HarnessError("could not draw an illegal sexagesimal token")


def plus_plain_decimal_token() -> tuple[str, float]:
    """``+`` plus a plain decimal (not an exponent, not a leading dot).

    Not the suite-named ``+12.3``. Value is independent decimal arithmetic.
    """
    for _ in range(64):
        whole = 3 + _draw(20)
        frac = 11 + _draw(80)
        if whole == 12:
            continue
        text = f"+{whole}.{frac}"
        if _reject_suite_named_token(text):
            continue
        value = whole + frac / (10 ** len(str(frac)))
        return text, value
    raise HarnessError("could not draw a leading-plus plain decimal")


def leading_dot_float_token() -> str:
    """Leading-dot decimal text. Not the suite-named ``.5``."""
    for _ in range(64):
        frac = 11 + _draw(80)
        text = f".{frac}"
        if _reject_suite_named_token(text):
            continue
        return text
    raise HarnessError("could not draw a leading-dot float")


def leading_zero_float_token() -> str:
    """Leading-zero float text. Not the suite-named ``01.0``."""
    for _ in range(64):
        whole = 2 + _draw(7)
        frac = 1 + _draw(80)
        text = f"0{whole}.{frac}"
        if _reject_suite_named_token(text):
            continue
        return text
    raise HarnessError("could not draw a leading-zero float")


def trailing_dot_token() -> tuple[str, float]:
    """Trailing-dot decimal and its number. Not the suite-named ``12.``."""
    for _ in range(64):
        number = 3 + _draw(20)
        if number == 12:
            continue
        text = f"{number}."
        if _reject_suite_named_token(text, number):
            continue
        return text, float(number)
    raise HarnessError("could not draw a trailing-dot decimal")


def underscore_float_token() -> str:
    """Underscored float text. Not the suite-named ``1_000.0``."""
    for _ in range(64):
        left = 2 + _draw(8)
        right = 100 + _draw(900)
        frac = 1 + _draw(9)
        text = f"{left}_{right}.{frac}"
        if _reject_suite_named_token(text):
            continue
        return text
    raise HarnessError("could not draw an underscored float")


def unsigned_exponent_float_token() -> str:
    """Float text with an unsigned exponent. Not ``685.23015e03``."""
    for _ in range(64):
        mantissa = 1 + _draw(8)
        frac = 11 + _draw(80)
        exp = 2 + _draw(4)
        text = f"{mantissa}.{frac}e{exp:02d}"
        if _reject_suite_named_token(text):
            continue
        return text
    raise HarnessError("could not draw an unsigned-exponent float")


def signed_underscore_exponent_float_token() -> str:
    """Underscored float with a signed exponent. Not ``685.230_15e+03``."""
    for _ in range(64):
        whole = 1 + _draw(8)
        frac_a = 11 + _draw(80)
        frac_b = 11 + _draw(80)
        exp = 1 + _draw(3)
        text = f"{whole}.{frac_a}_{frac_b}e+{exp:02d}"
        if _reject_suite_named_token(text):
            continue
        return text
    raise HarnessError("could not draw a signed underscored-exponent float")


def sexagesimal_float_token() -> str:
    """Sexagesimal float with minutes and seconds < 60. Not ``190:20:30.15``."""
    for _ in range(64):
        hours = 1 + _draw(8)
        minutes = _draw(60)
        seconds = _draw(60)
        frac = 1 + _draw(80)
        text = f"{hours}:{minutes}:{seconds}.{frac}"
        if _reject_suite_named_token(text):
            continue
        return text
    raise HarnessError("could not draw a sexagesimal float")


def non_bool_word() -> str:
    """A word that is not a documented boolean spelling. Not ``garbage``."""
    banned = {w.lower() for w in YAML11_TRUE_WORDS + YAML11_FALSE_WORDS}
    banned.update({"true", "false", "garbage"})
    for _ in range(32):
        word = unique_token()
        if word.lower() not in banned:
            return word
    raise HarnessError("could not draw a non-boolean word")


def non_int_text() -> str:
    """Text that is not integer form. Not the suite-named ``1.5``."""
    for _ in range(32):
        frac = 2 + _draw(7)
        text = f"3.{frac}"
        if text != "1.5":
            return text
    raise HarnessError("could not draw non-integer text")


def non_float_text() -> str:
    """Text that is not float form. Not the suite-named ``abc``."""
    for _ in range(32):
        word = unique_token()
        if word != "abc":
            return word
    raise HarnessError("could not draw non-float text")


def nonempty_seq_scalar() -> str:
    """A nonempty scalar for an explicit sequence tag. Not ``foo``."""
    for _ in range(32):
        word = unique_token()
        if word != "foo":
            return word
    raise HarnessError("could not draw a nonempty sequence scalar")


# ---------------------------------------------------------------------------
# F03: mapping-container knobs, Map observation, proto channels, YAML builders
# ---------------------------------------------------------------------------

_REAL_MAP_TAG = "realMapTag"
_LEGACY_MAP_TAG = "legacyMapTag"


def with_real_map_schema() -> dict[str, Any]:
    """Sealed parse/dump options: Core plus the real-map replacement tag."""
    return {"schema": SCHEMA_CORE, "extra_tags": [_REAL_MAP_TAG]}


def with_legacy_map_schema() -> dict[str, Any]:
    """Sealed parse/dump options: Core plus the legacy-map replacement tag."""
    return {"schema": SCHEMA_CORE, "extra_tags": [_LEGACY_MAP_TAG]}


def with_real_map_on_failsafe() -> dict[str, Any]:
    """Sealed parse/dump options: Failsafe plus the real-map replacement tag."""
    return {"schema": SCHEMA_FAILSAFE, "extra_tags": [_REAL_MAP_TAG]}


def with_real_map_on_json() -> dict[str, Any]:
    """Sealed parse/dump options: JSON plus the real-map replacement tag."""
    return {"schema": SCHEMA_JSON, "extra_tags": [_REAL_MAP_TAG]}


def require_real_map(value: Any) -> JsMap:
    """Return *value* if it is the observed ``Map`` type; assert otherwise.

    A read that cannot classify the container raises. A plain object is
    a failed assertion, not an empty map.
    """
    if isinstance(value, JsMap):
        return value
    assert False, f"expected a Map, got {type(value).__name__}: {value!r}"


def _map_entries_equal(left: Any, right: Any) -> bool:
    """Structural equality for Map lookup: entries only, no identity fields."""
    if isinstance(left, JsMap) and isinstance(right, JsMap):
        if len(left.entries) != len(right.entries):
            return False
        return all(
            _map_entries_equal(lk, rk) and _map_entries_equal(lv, rv)
            for (lk, lv), (rk, rv) in zip(left.entries, right.entries)
        )
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return False
        return all(_map_entries_equal(a, b) for a, b in zip(left, right))
    if type(left) is bool or type(right) is bool:
        return type(left) is bool and type(right) is bool and left is right
    return left == right


def map_get(mapping: Any, key: Any) -> Any:
    """Read *key* from an observed ``Map`` by entry equality.

    Scalar and sequence keys compare by value. A ``Map`` key compares
    entries only and ignores identity fields. Missing key asserts.
    Never returns a default empty.
    """
    real = require_real_map(mapping)
    for item_key, item_value in real.entries:
        if _map_entries_equal(item_key, key):
            return item_value
    shown = [repr(item_key) for item_key, _ in real.entries]
    assert False, f"map missing key {key!r}; keys={shown}"


def map_size(mapping: Any) -> int:
    """Number of entries on a classified ``Map``. Unreadable input asserts."""
    return len(require_real_map(mapping))


def require_own_data_property(obj: Any, key: str) -> Any:
    """Return the value of an own data property, or assert if it is absent.

    A bare dict or any object without an own-name channel is
    unclassifiable and raises — never treated as "looked and not own".
    """
    if not isinstance(obj, JsObject):
        raise HarnessError(
            f"cannot read own names: not a constructed object "
            f"({type(obj).__name__})"
        )
    if not hasattr(obj, "own_names"):
        raise HarnessError("constructed object has no own-name channel")
    if key not in obj.own_names:
        assert False, (
            f"own names missing {key!r}; own={list(obj.own_names)!r}"
        )
    if key not in obj.props:
        raise HarnessError(
            f"own name {key!r} is listed but its value is unreadable"
        )
    return obj.props[key]


def ordinary_js_object_rendering() -> str:
    """Language ``String`` of an ordinary object. Not a YAML transform.

    The PRD names this rendering as the stored property name when a
    mapping is used as a key. A missing or unreadable observation raises.
    """
    result = evaluate("return String({})")
    if result is None:
        raise HarnessError("ordinary object rendering result is missing")
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"ordinary object rendering is not CallResult: "
            f"{type(result).__name__}"
        )
    if not result.ok:
        report = (
            observer_visible_report(result.error)
            if result.error is not None
            else "<no error payload>"
        )
        raise HarnessError(
            f"ordinary object rendering failed; report={report}"
        )
    if not isinstance(result.value, str) or result.value == "":
        raise HarnessError(
            f"ordinary object rendering is not text: "
            f"{type(result.value).__name__}: {result.value!r}"
        )
    print(
        f"[helpers] ordinary-object-rendering={result.value!r}",
        flush=True,
    )
    return result.value


def require_ordinary_object_prototype(obj: Any) -> None:
    """Assert the prototype classification is the ordinary object prototype.

    A missing channel raises. ``null`` / ``other`` assert.
    """
    if not isinstance(obj, JsObject):
        raise HarnessError(
            f"cannot classify prototype: not a constructed object "
            f"({type(obj).__name__})"
        )
    if not hasattr(obj, "proto"):
        raise HarnessError("constructed object has no prototype classification")
    if obj.proto != "object":
        assert False, (
            f"prototype is {obj.proto!r}, not the ordinary object prototype"
        )


def is_inherited_visible(obj: Any, name: str) -> bool:
    """Whether *name* appears in the ``for...in`` visible-name channel.

    A missing channel raises. Never returns False to mean "could not look".
    """
    if not name:
        raise ValueError("visible name must be a non-empty string")
    if not isinstance(obj, JsObject):
        raise HarnessError(
            f"cannot read visible names: not a constructed object "
            f"({type(obj).__name__})"
        )
    if not hasattr(obj, "in_keys"):
        raise HarnessError("constructed object has no for-in channel")
    return name in obj.in_keys


def require_yaml_text(result: CallResult) -> str:
    """Return dump text, or assert/raise. Never uses ``""`` to mean failure."""
    if result is None:
        raise HarnessError("dump result is missing")
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"dump result is not CallResult: {type(result).__name__}"
        )
    if not result.ok:
        report = (
            observer_visible_report(result.error)
            if result.error is not None
            else "<no error payload>"
        )
        assert False, f"dump failed; report={report}"
    if not isinstance(result.value, str):
        assert False, (
            f"dump did not yield text: {type(result.value).__name__}: "
            f"{result.value!r}"
        )
    return result.value


def dump_then_load(value: Any, options: Mapping[str, Any] | None = None) -> CallResult:
    """Public dump then public parse, same options on both steps.

    Either step's failure is exposed. Does not swallow or invent text.
    """
    dumped = dump(value, options)
    text = require_yaml_text(dumped)
    print(f"[helpers] dump-then-load chars={len(text)}", flush=True)
    return load(text, options)


def _require_plain_word(text: str, *, what: str) -> str:
    if not isinstance(text, str) or not text:
        raise HarnessError(f"{what} must be a nonempty string")
    if any(ch.isspace() for ch in text):
        raise HarnessError(f"{what} contains whitespace")
    return text


def explicit_scalar_key_yaml(key: str, value: str) -> str:
    """YAML with an explicit scalar key and a scalar value."""
    key = _require_plain_word(key, what="explicit scalar key")
    value = _require_plain_word(value, what="explicit scalar value")
    return f"? {key}\n: {value}\n"


def explicit_sequence_key_yaml(items: Sequence[str], value: str) -> str:
    """YAML with an explicit sequence key whose items are plain scalars."""
    if not items:
        raise HarnessError("explicit sequence key items are empty")
    cleaned: list[str] = []
    for index, item in enumerate(items):
        cleaned.append(
            _require_plain_word(item, what=f"sequence key item {index}")
        )
    value = _require_plain_word(value, what="sequence key value")
    lines = ["?"]
    for item in cleaned:
        lines.append(f"  - {item}")
    lines.append(f": {value}")
    return "\n".join(lines) + "\n"


def explicit_mapping_key_yaml(pairs: Sequence[tuple[str, str]], value: str) -> str:
    """YAML with an explicit flow-mapping key."""
    if not pairs:
        raise HarnessError("explicit mapping key pairs are empty")
    cleaned: list[tuple[str, str]] = []
    for index, pair in enumerate(pairs):
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise HarnessError(f"mapping key pair {index} is not a 2-tuple")
        left = _require_plain_word(pair[0], what=f"mapping key name {index}")
        right = _require_plain_word(pair[1], what=f"mapping key value {index}")
        cleaned.append((left, right))
    value = _require_plain_word(value, what="outer mapping value")
    inner = ", ".join(f"{left}: {right}" for left, right in cleaned)
    return f"? {{ {inner} }}\n: {value}\n"


def explicit_nested_array_key_yaml(word: str) -> str:
    """YAML whose explicit key is a sequence containing another sequence."""
    word = _require_plain_word(word, what="nested array key word")
    return f"? - - {word}\n: value\n"


def explicit_sequence_key_containing_nested_yaml(word: str, nested_word: str) -> str:
    """YAML whose explicit sequence key has one scalar and one nested sequence."""
    word = _require_plain_word(word, what="sequence-with-nested word")
    nested_word = _require_plain_word(nested_word, what="nested item word")
    return f"? - {word}\n  - - {nested_word}\n: value\n"


def alias_nested_array_key_yaml(word: str) -> str:
    """YAML that anchors a nested sequence as a value, then uses it as a key."""
    word = _require_plain_word(word, what="alias nested-array word")
    return f"holder: &a\n  - - {word}\n? *a\n: value\n"


# ---------------------------------------------------------------------------
# F04: YAML 1.1 types, merge-on-Core knob, byte/set/date classification
# ---------------------------------------------------------------------------

_MERGE_TAG = "mergeTag"

_READABLE_OBSERVATION = (
    type(None),
    bool,
    int,
    float,
    str,
    list,
    dict,
    JsObject,
    JsMap,
    JsSet,
    JsDate,
    JsBytes,
    JsUndefined,
    JsFunction,
    JsRegexp,
)


def with_merge_on_core() -> dict[str, Any]:
    """Sealed parse/dump options: Core plus the merge tag."""
    return {"schema": SCHEMA_CORE, "extra_tags": [_MERGE_TAG]}


def with_yaml11_real_map() -> dict[str, Any]:
    """Sealed parse/dump options: YAML 1.1 plus the real-map replacement tag."""
    return {"schema": SCHEMA_YAML11, "extra_tags": [_REAL_MAP_TAG]}


def _is_readable_observation(value: Any) -> bool:
    return isinstance(value, _READABLE_OBSERVATION)


def require_js_bytes(value: Any) -> JsBytes:
    """Return *value* if it is the observed byte array; assert otherwise.

    An empty byte array is a legal success. A read that cannot classify
    the value raises — never returns an empty buffer to mean "not bytes".
    """
    if isinstance(value, JsBytes):
        return value
    if _is_readable_observation(value):
        assert False, f"expected a byte array, got {type(value).__name__}: {value!r}"
    raise HarnessError(
        f"cannot classify bytes: unreadable type {type(value).__name__}"
    )


def require_js_set(value: Any) -> JsSet:
    """Return *value* if it is the observed ``Set``; assert otherwise.

    An empty ``Set`` is a legal success. A plain object is a failed
    assertion, not an empty set. Unreadable input raises.
    """
    if isinstance(value, JsSet):
        return value
    if _is_readable_observation(value):
        assert False, f"expected a Set, got {type(value).__name__}: {value!r}"
    raise HarnessError(
        f"cannot classify Set: unreadable type {type(value).__name__}"
    )


def require_js_date(value: Any) -> JsDate:
    """Return *value* if it is the observed date; assert otherwise.

    A string that looks like a date is a failed assertion. Unreadable
    input raises — never returns ``None`` to mean "not a date".
    """
    if isinstance(value, JsDate):
        return value
    if _is_readable_observation(value):
        assert False, f"expected a date, got {type(value).__name__}: {value!r}"
    raise HarnessError(
        f"cannot classify date: unreadable type {type(value).__name__}"
    )


def is_js_bytes(value: Any) -> bool:
    """Whether *value* is the observed byte array. Unreadable input raises."""
    if isinstance(value, JsBytes):
        return True
    if _is_readable_observation(value):
        return False
    raise HarnessError(
        f"cannot classify bytes: unreadable type {type(value).__name__}"
    )


def is_js_set(value: Any) -> bool:
    """Whether *value* is the observed ``Set``. Unreadable input raises."""
    if isinstance(value, JsSet):
        return True
    if _is_readable_observation(value):
        return False
    raise HarnessError(
        f"cannot classify Set: unreadable type {type(value).__name__}"
    )


def is_js_date(value: Any) -> bool:
    """Whether *value* is the observed date. Unreadable input raises."""
    if isinstance(value, JsDate):
        return True
    if _is_readable_observation(value):
        return False
    raise HarnessError(
        f"cannot classify date: unreadable type {type(value).__name__}"
    )


def core_type_absent(result: CallResult, predicate: Callable[[Any], bool]) -> None:
    """Assert a YAML 1.1 construction is absent on a Core (or Core+merge) parse.

    The result must be readable. A refusal is allowed (type closed). A
    successful document must make *predicate* false. A driver crash
    raises — never treated as "looked and the type was absent".
    """
    if result is None:
        raise HarnessError("parse result is missing")
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"parse result is not CallResult: {type(result).__name__}"
        )
    if not result.ok:
        if result.error is None:
            raise HarnessError("parse failed but error payload is missing")
        print(
            f"[helpers] core type absent via refusal; "
            f"report={observer_visible_report(result.error)}",
            flush=True,
        )
        assert result.error is not None
        return
    present = predicate(result.value)
    print(
        f"[helpers] core type absent check present={present} "
        f"value_type={type(result.value).__name__}",
        flush=True,
    )
    assert not present, (
        f"YAML 1.1 construction appeared under a schema that closes it: "
        f"{result.value!r}"
    )


def bytes_payload() -> bytes:
    """Runtime bytes that are not the suite-named GIF fixture and not empty."""
    data = uuid.uuid4().bytes + bytes([1 + _draw(254), 1 + _draw(254)])
    if data[:3] == b"GIF":
        data = b"X" + data[1:]
    if not data:
        raise HarnessError("bytes payload is empty")
    return data


def b64_of(data: bytes) -> str:
    """Standard-library Base64 of *data*. Encode failure raises."""
    if not isinstance(data, (bytes, bytearray)):
        raise HarnessError(f"b64_of needs bytes, got {type(data).__name__}")
    try:
        return base64.b64encode(bytes(data)).decode("ascii")
    except Exception as exc:
        raise HarnessError(f"standard-library Base64 encode failed: {exc}") from exc


def b64_decode_stripped(text: str) -> bytes:
    """Decode Base64 after removing whitespace. Decode failure raises."""
    if not isinstance(text, str):
        raise HarnessError(
            f"b64_decode_stripped needs text, got {type(text).__name__}"
        )
    cleaned = "".join(ch for ch in text if not ch.isspace())
    try:
        return base64.b64decode(cleaned, validate=True)
    except Exception as exc:
        raise HarnessError(f"standard-library Base64 decode failed: {exc}") from exc


def utc_epoch_ms(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
    millisecond: int = 0,
    *,
    tz_hours: int = 0,
    tz_minutes: int = 0,
) -> int:
    """UTC milliseconds from calendar fields. Independent of the product.

    *tz_hours* / *tz_minutes* are the ISO offset (same sign). Does not
    call the library and does not use host date-string parsing.
    """
    if not isinstance(millisecond, int) or millisecond < 0 or millisecond > 999:
        raise HarnessError(f"millisecond out of range: {millisecond!r}")
    try:
        wall = datetime(
            year,
            month,
            day,
            hour,
            minute,
            second,
            millisecond * 1000,
            tzinfo=timezone.utc,
        )
    except ValueError as exc:
        raise HarnessError(f"cannot form calendar instant: {exc}") from exc
    instant = wall - timedelta(hours=tz_hours, minutes=tz_minutes)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = instant - epoch
    return delta.days * 86_400_000 + delta.seconds * 1000 + delta.microseconds // 1000


def set_member_texts(value: Any) -> set[str]:
    """Member texts of an observed ``Set``. Unreadable members raise."""
    observed = require_js_set(value)
    texts: set[str] = set()
    for item in observed.items:
        if not isinstance(item, str):
            raise HarnessError(
                f"set member is not text: {type(item).__name__}: {item!r}"
            )
        texts.add(item)
    return texts


def _plain_yaml_scalar(value: Any, *, what: str) -> str:
    if type(value) is bool:
        raise HarnessError(f"{what} is a boolean")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return _require_plain_word(value, what=what)
    raise HarnessError(f"{what} is not a plain YAML scalar: {type(value).__name__}")


def _flow_map(pairs: Mapping[str, Any], *, what: str) -> str:
    if not pairs:
        raise HarnessError(f"{what} mapping is empty")
    parts: list[str] = []
    for index, (key, value) in enumerate(pairs.items()):
        if not isinstance(key, str):
            raise HarnessError(f"{what} key {index} is not text")
        name = _require_plain_word(key, what=f"{what} key {index}")
        item = _plain_yaml_scalar(value, what=f"{what} value {index}")
        parts.append(f"{name}: {item}")
    return "{ " + ", ".join(parts) + " }"


def binary_scalar_yaml(b64_text: str, *, insert_whitespace: str | None = None) -> str:
    """Explicit ``!!binary`` scalar. Optional whitespace is inserted into the payload."""
    if not isinstance(b64_text, str) or not b64_text:
        raise HarnessError("binary payload must be nonempty Base64 text")
    if any(ch.isspace() for ch in b64_text):
        raise HarnessError("binary payload already contains whitespace")
    payload = b64_text
    if insert_whitespace is not None:
        if not insert_whitespace or not all(ch.isspace() for ch in insert_whitespace):
            raise HarnessError("insert_whitespace must be whitespace characters")
        mid = max(len(payload) // 2, 1)
        payload = payload[:mid] + insert_whitespace + payload[mid:]
    return f'!!binary "{payload}"\n'


def defaults_development_yaml(adapter: str, host: str, database: str) -> str:
    """defaults/development document with ``<<: *defaults``."""
    adapter = _require_plain_word(adapter, what="adapter")
    host = _require_plain_word(host, what="host")
    database = _require_plain_word(database, what="database")
    return (
        "defaults: &defaults\n"
        f"  adapter: {adapter}\n"
        f"  host: {host}\n"
        "\n"
        "development:\n"
        "  <<: *defaults\n"
        f"  database: {database}\n"
    )


def sequence_merge_yaml(
    earlier: Mapping[str, Any],
    later: Mapping[str, Any],
    *,
    explicit: Mapping[str, Any] | None = None,
    explicit_before: bool = False,
) -> str:
    """A mapping whose ``<<`` value is a two-item merge sequence."""
    merge = (
        f"<<: [ {_flow_map(earlier, what='earlier merge')}, "
        f"{_flow_map(later, what='later merge')} ]"
    )
    explicit_lines: list[str] = []
    if explicit:
        for index, (key, value) in enumerate(explicit.items()):
            name = _require_plain_word(key, what=f"explicit key {index}")
            item = _plain_yaml_scalar(value, what=f"explicit value {index}")
            explicit_lines.append(f"{name}: {item}")
    if explicit_before:
        lines = explicit_lines + [merge]
    else:
        lines = [merge] + explicit_lines
    return "\n".join(lines) + "\n"


def several_merge_keys_yaml(
    first: Mapping[str, Any],
    middle_key: str,
    middle_value: Any,
    second: Mapping[str, Any],
) -> str:
    """Two ``<<`` keys in one mapping with an explicit pair between them."""
    mid_key = _require_plain_word(middle_key, what="middle merge key")
    mid_value = _plain_yaml_scalar(middle_value, what="middle merge value")
    return (
        f"<<: {_flow_map(first, what='first merge')}\n"
        f"{mid_key}: {mid_value}\n"
        f"<<: {_flow_map(second, what='second merge')}\n"
    )


def set_explicit_item_yaml(key: str, value: str | None = None) -> str:
    """``!!set`` with a ``?`` key. *value* ``None`` is an empty (null) value."""
    key = _require_plain_word(key, what="set item key")
    if value is None:
        return f"!!set\n? {key}\n"
    value = _require_plain_word(value, what="set item value")
    return f"!!set\n? {key}\n: {value}\n"


def omap_mapping_yaml(pairs: Sequence[tuple[str, str]]) -> str:
    """``!!omap`` written as a mapping (not a sequence)."""
    if not pairs:
        raise HarnessError("omap mapping pairs are empty")
    lines = ["!!omap"]
    for index, pair in enumerate(pairs):
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise HarnessError(f"omap mapping pair {index} is not a 2-tuple")
        key = _require_plain_word(pair[0], what=f"omap map key {index}")
        value = _require_plain_word(pair[1], what=f"omap map value {index}")
        lines.append(f"  {key}: {value}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# F05: dump knobs, dump observation, shared-identity dump
# ---------------------------------------------------------------------------

_F05_QUOTE_STYLE_SINGLE = "single"
_F05_QUOTE_STYLE_DOUBLE = "double"
_ANCHOR_THEN_TAG = "anchor_then_tag"
_TAG_THEN_ANCHOR = "tag_then_anchor"


def with_double_quote_style() -> dict[str, Any]:
    """Sealed dump options that select double quotes when quotes are required."""
    return {"quoteStyle": _F05_QUOTE_STYLE_DOUBLE}


def with_single_quote_style() -> dict[str, Any]:
    """Sealed dump options that select single quotes when quotes are required."""
    return {"quoteStyle": _F05_QUOTE_STYLE_SINGLE}


def with_quote_non_key_strings() -> dict[str, Any]:
    """Sealed dump options that quote every non-key string."""
    return {"forceQuotes": True}


def with_no_reuse() -> dict[str, Any]:
    """Sealed dump options that inline repeated objects instead of aliasing."""
    return {"noRefs": True}


def with_skip_unrepresentable() -> dict[str, Any]:
    """Sealed dump options that omit unrepresentable values instead of failing."""
    return {"skipInvalid": True}


def with_indent_width(n: int) -> dict[str, Any]:
    """Sealed dump options that set block indentation width in spaces."""
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise HarnessError(f"indent width must be a positive int, got {n!r}")
    return {"indent": n}


def with_line_width(n: int) -> dict[str, Any]:
    """Sealed dump options that set the maximum line width."""
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise HarnessError(f"line width must be a positive int, got {n!r}")
    return {"lineWidth": n}


def with_no_extra_sequence_indent() -> dict[str, Any]:
    """Sealed dump options that align a sequence dash with its mapping key."""
    return {"seqNoIndent": True}


def with_nested_sequence_next_line() -> dict[str, Any]:
    """Sealed dump options that start a nested sequence on the next line."""
    return {"seqInlineFirst": False}


def with_flow_depth(n: int) -> dict[str, Any]:
    """Sealed dump options that switch collections to flow at *n*."""
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        raise HarnessError(f"flow depth must be a non-negative int, got {n!r}")
    return {"flowLevel": n}


def with_flow_bracket_padding() -> dict[str, Any]:
    """Sealed dump options that pad inside flow collection brackets."""
    return {"flowBracketPadding": True}


def with_flow_no_comma_space() -> dict[str, Any]:
    """Sealed dump options that drop the space after flow commas."""
    return {"flowSkipCommaSpace": True}


def with_flow_no_colon_space() -> dict[str, Any]:
    """Sealed dump options that drop the space after flow colons."""
    return {"flowSkipColonSpace": True}


def with_quote_flow_keys() -> dict[str, Any]:
    """Sealed dump options that quote keys in flow mappings."""
    return {"quoteFlowKeys": True}


def with_tag_before_anchor() -> dict[str, Any]:
    """Sealed dump options that emit an explicit tag before an anchor."""
    return {"tagBeforeAnchor": True}


def with_sort_keys() -> dict[str, Any]:
    """Sealed dump options that request a comparator-less key sort."""
    return {"sortKeys": True}


def merge_dump_options(*parts: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge dump option dicts. Conflicting keys raise; never silent override."""
    merged: dict[str, Any] = {}
    for index, part in enumerate(parts):
        if part is None:
            continue
        if not isinstance(part, Mapping):
            raise HarnessError(
                f"dump option part {index} is not a mapping: "
                f"{type(part).__name__}"
            )
        for key, value in part.items():
            if key in merged and merged[key] != value:
                raise HarnessError(
                    f"dump option {key!r} conflict: {merged[key]!r} vs {value!r}"
                )
            merged[key] = value
    return merged


def require_dump_failure(result: CallResult) -> ErrorInfo:
    """Return the dump failure payload. Success (including empty text) asserts.

    A missing or unreadable result raises. Never treats a successful empty
    string as a failure.
    """
    if result is None:
        raise HarnessError("dump result is missing")
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"dump result is not CallResult: {type(result).__name__}"
        )
    if result.ok:
        if isinstance(result.value, str):
            assert False, (
                f"dump succeeded with YAML text; chars={len(result.value)}; "
                f"text={result.value!r}"
            )
        assert False, f"dump succeeded unexpectedly; value={result.value!r}"
    if result.error is None:
        raise HarnessError("dump failed but error payload is missing")
    return result.error


def require_empty_yaml_text(result: CallResult) -> str:
    """Return successful dump text of length 0. Failure or non-text asserts."""
    text = require_yaml_text(result)
    if len(text) != 0:
        assert False, f"expected empty YAML text, got {text!r}"
    return text


def is_plain_scalar_dump(text: str, scalar: str) -> bool:
    """True when *text* is exactly ``scalar`` plus a newline."""
    if not isinstance(text, str):
        raise HarnessError(
            f"dump text is not readable text: {type(text).__name__}"
        )
    if not isinstance(scalar, str):
        raise HarnessError(
            f"scalar is not text: {type(scalar).__name__}"
        )
    return text == scalar + "\n"


def require_quoted_scalar_dump(text: str, scalar: str) -> None:
    """Assert *text* is not the plain ``scalar`` + newline form."""
    if not isinstance(text, str):
        raise HarnessError(
            f"dump text is not readable text: {type(text).__name__}"
        )
    if not isinstance(scalar, str):
        raise HarnessError(
            f"scalar is not text: {type(scalar).__name__}"
        )
    if is_plain_scalar_dump(text, scalar):
        assert False, f"dump of {scalar!r} is the plain newline form: {text!r}"


def require_single_quoted_scalar(text: str, scalar: str) -> None:
    """Assert *scalar* is wrapped in single quotes. Not merely 'not plain'."""
    if not isinstance(text, str):
        raise HarnessError(
            f"dump text is not readable text: {type(text).__name__}"
        )
    if not isinstance(scalar, str):
        raise HarnessError(
            f"scalar is not text: {type(scalar).__name__}"
        )
    wrapped = "'" + scalar + "'"
    if wrapped not in text:
        assert False, (
            f"expected single-quoted {scalar!r} in dump text; got {text!r}"
        )


def require_double_quoted_scalar(text: str, scalar: str) -> None:
    """Assert *scalar* is wrapped in double quotes. Not merely 'not plain'."""
    if not isinstance(text, str):
        raise HarnessError(
            f"dump text is not readable text: {type(text).__name__}"
        )
    if not isinstance(scalar, str):
        raise HarnessError(
            f"scalar is not text: {type(scalar).__name__}"
        )
    wrapped = '"' + scalar + '"'
    if wrapped not in text:
        assert False, (
            f"expected double-quoted {scalar!r} in dump text; got {text!r}"
        )


def dump_then_parse(
    value: Any,
    dump_options: Mapping[str, Any] | None = None,
    load_options: Mapping[str, Any] | None = None,
) -> CallResult:
    """Public dump then public parse. The two option sets may differ.

    Either step's failure is exposed. Does not swallow or invent text.
    """
    dumped = dump(value, dump_options)
    text = require_yaml_text(dumped)
    print(
        f"[helpers] dump-then-parse chars={len(text)} "
        f"dump_opts={dump_options!r} load_opts={load_options!r}",
        flush=True,
    )
    return load(text, load_options)


def _js_embed(value: Any, *, what: str) -> str:
    """JavaScript literal for a simple dump-option or property value."""
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(int(value))
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "-Infinity" if value < 0 else "Infinity"
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value)
    raise HarnessError(
        f"{what} cannot be embedded in dump helper JS: {type(value).__name__}"
    )


def _js_options_expr(options: Mapping[str, Any] | None) -> str:
    """JS expression that builds dump options, resolving schema from ``lib``."""
    if not options:
        return "undefined"
    if not isinstance(options, Mapping):
        raise HarnessError(
            f"dump options are not a mapping: {type(options).__name__}"
        )
    parts: list[str] = []
    schema = options.get("schema")
    extra = options.get("extra_tags")
    for key, value in options.items():
        if key in ("schema", "extra_tags"):
            continue
        if not isinstance(key, str) or not key:
            raise HarnessError(f"dump option key is not text: {key!r}")
        parts.append(f"{json.dumps(key)}: {_js_embed(value, what=key)}")
    if schema is not None:
        if not isinstance(schema, str) or not schema:
            raise HarnessError(f"schema name is not text: {schema!r}")
        schema_expr = f"lib[{json.dumps(schema)}]"
        if extra is not None:
            if not isinstance(extra, (list, tuple)):
                raise HarnessError("extra_tags must be a list of export names")
            tag_exprs = []
            for index, name in enumerate(extra):
                if not isinstance(name, str) or not name:
                    raise HarnessError(
                        f"extra_tags[{index}] is not a text export name"
                    )
                tag_exprs.append(f"lib[{json.dumps(name)}]")
            schema_expr = f"{schema_expr}.withTags({', '.join(tag_exprs)})"
        parts.append(f"schema: {schema_expr}")
    elif extra is not None:
        raise HarnessError("schema is required when extra_tags is set")
    return "{ " + ", ".join(parts) + " }"


def dump_identical_pair(
    props: Mapping[str, Any],
    dump_options: Mapping[str, Any] | None = None,
) -> CallResult:
    """Construct one ordinary object, put it in an array twice, public dump.

    Construction failure raises. The product dump outcome is returned.
    """
    if not isinstance(props, Mapping) or not props:
        raise HarnessError("identical-pair props must be a nonempty mapping")
    fields: list[str] = []
    for index, (key, value) in enumerate(props.items()):
        if not isinstance(key, str) or not key:
            raise HarnessError(f"identical-pair key {index} is not text")
        fields.append(
            f"{json.dumps(key)}: {_js_embed(value, what=f'identical-pair {key}')}"
        )
    opts = _js_options_expr(dump_options)
    source = (
        "const obj = { " + ", ".join(fields) + " };\n"
        f"return lib.dump([obj, obj], {opts});"
    )
    print(f"[helpers] dump-identical-pair keys={list(props)}", flush=True)
    return evaluate(source)


def dump_identical_set(
    members: Sequence[Any],
    dump_options: Mapping[str, Any] | None = None,
) -> CallResult:
    """Construct one Set, put it in an array twice, public dump."""
    if members is None:
        raise HarnessError("identical-set members are missing")
    items: list[str] = []
    for index, member in enumerate(members):
        items.append(_js_embed(member, what=f"identical-set member {index}"))
    opts = _js_options_expr(dump_options)
    source = (
        "const s = new Set([" + ", ".join(items) + "]);\n"
        f"return lib.dump([s, s], {opts});"
    )
    print(f"[helpers] dump-identical-set n={len(items)}", flush=True)
    return evaluate(source)


def dump_cycle(
    props: Mapping[str, Any],
    backref_key: str,
    dump_options: Mapping[str, Any] | None = None,
) -> CallResult:
    """Construct a self-referential mapping and public-dump it."""
    backref = _require_plain_word(backref_key, what="cycle backref key")
    if not isinstance(props, Mapping):
        raise HarnessError("cycle props must be a mapping")
    fields: list[str] = []
    for index, (key, value) in enumerate(props.items()):
        name = _require_plain_word(key, what=f"cycle prop key {index}")
        if name == backref:
            raise HarnessError("cycle backref key is also listed in props")
        fields.append(
            f"{json.dumps(name)}: {_js_embed(value, what=f'cycle {name}')}"
        )
    opts = _js_options_expr(dump_options)
    source = (
        "const obj = { " + ", ".join(fields) + " };\n"
        f"obj[{json.dumps(backref)}] = obj;\n"
        f"return lib.dump(obj, {opts});"
    )
    print(f"[helpers] dump-cycle backref={backref!r}", flush=True)
    return evaluate(source)


def anchor_tag_order_on_node(text: str, tag: str) -> str:
    """Order of ``&`` vs *tag* on the one node that carries both.

    Returns ``anchor_then_tag`` or ``tag_then_anchor``. Missing pair raises.
    Does not compare the first ``&`` in the document to the first tag.
    """
    if not isinstance(text, str):
        raise HarnessError(
            f"dump text is not readable text: {type(text).__name__}"
        )
    if not isinstance(tag, str) or not tag:
        raise HarnessError("explicit tag must be nonempty text")
    anchor = r"&[^\s&*,\[\]{}]+"
    tag_esc = re.escape(tag)
    found: list[tuple[int, str]] = []
    for match in re.finditer(anchor + r"[ \t]+" + tag_esc, text):
        found.append((match.start(), _ANCHOR_THEN_TAG))
    for match in re.finditer(tag_esc + r"[ \t]+" + anchor, text):
        found.append((match.start(), _TAG_THEN_ANCHOR))
    if not found:
        raise HarnessError(
            f"no node carries both an anchor and {tag!r}; text={text!r}"
        )
    found.sort(key=lambda item: item[0])
    order = found[0][1]
    print(f"[helpers] anchor-tag-order={order} tag={tag!r}", flush=True)
    return order


def has_float_marker_after_strip(text: str) -> bool:
    """Whether a decimal point or exponent letter remains after digits/signs."""
    if not isinstance(text, str):
        raise HarnessError(
            f"dump text is not readable text: {type(text).__name__}"
        )
    leftover = "".join(
        ch for ch in text if not (ch.isdigit() or ch in "+-" or ch.isspace())
    )
    return any(ch in leftover for ch in ".eE")


def scalar_word_content_lines(text: str, words: Sequence[str]) -> int:
    """Non-empty lines that still hold *words* after keys and punctuation."""
    if not isinstance(text, str):
        raise HarnessError(
            f"dump text is not readable text: {type(text).__name__}"
        )
    if not words:
        raise HarnessError("word list is empty")
    wanted = []
    for index, word in enumerate(words):
        if not isinstance(word, str) or not word:
            raise HarnessError(f"word {index} is not nonempty text")
        wanted.append(word)
    wanted_set = set(wanted)
    punct = set(":-,'\">|{}[]&*!?#")
    count = 0
    for line in text.splitlines():
        cleaned = "".join(" " if ch in punct else ch for ch in line)
        tokens = cleaned.split()
        if not tokens:
            continue
        if any(token in wanted_set for token in tokens):
            count += 1
    return count


def require_flow_container(text: str) -> None:
    """Assert the dump root is a flow collection (``{...}`` or ``[...]``)."""
    if not isinstance(text, str):
        raise HarnessError(
            f"dump text is not readable text: {type(text).__name__}"
        )
    body = text.strip()
    if body.startswith("---"):
        body = body[3:].lstrip()
    body = body.strip()
    if len(body) < 2:
        assert False, f"dump root is not a flow container: {text!r}"
    start, end = body[0], body[-1]
    paired = (start == "{" and end == "}") or (start == "[" and end == "]")
    if not paired:
        assert False, f"dump root is not a flow container: {text!r}"


def require_flow_mapping(text: str) -> None:
    """Assert the dump root is a flow mapping (``{...}``), not a sequence."""
    require_flow_container(text)
    body = text.strip()
    if body.startswith("---"):
        body = body[3:].lstrip()
    body = body.strip()
    if not (body.startswith("{") and body.endswith("}")):
        assert False, f"dump root is not a flow mapping: {text!r}"


def function_value() -> JsFunction:
    """A function value encoded for the public dump entry."""
    return JsFunction(name="")


def regexp_value() -> JsRegexp:
    """A regular-expression value encoded for the public dump entry."""
    return JsRegexp(source=".", flags="")


def undefined_value() -> JsUndefined:
    """The JavaScript undefined value encoded for the public dump entry."""
    return UNDEFINED


def complex_key_map(
    first_inner: str,
    first_value: Any,
    second_inner: str,
    second_value: Any,
) -> JsMap:
    """Real-map input: two mapping keys in insertion order.

    Each mapping key is a one-entry object whose key is the given inner
    word. *first_value* / *second_value* are the Map values. Construction
    failure raises.
    """
    first_key = _require_plain_word(first_inner, what="first complex inner key")
    second_key = _require_plain_word(second_inner, what="second complex inner key")
    return JsMap(
        entries=[
            ({first_key: 1}, first_value),
            ({second_key: 1}, second_value),
        ],
        object_id=-1,
    )


def relative_nested_indent(text: str, parent: str, child: str) -> int:
    """Spaces of *child* relative to *parent*. Missing key raises."""
    if not isinstance(text, str):
        raise HarnessError(
            f"dump text is not readable text: {type(text).__name__}"
        )
    parent = _require_plain_word(parent, what="parent mapping key")
    child = _require_plain_word(child, what="child mapping key")
    return _indent_of_key(text, child) - _indent_of_key(text, parent)


def key_and_dash_indents(text: str, key: str) -> tuple[int, int]:
    """Indent of *key* and of the first dash after it. Missing dash raises."""
    if not isinstance(text, str):
        raise HarnessError(
            f"dump text is not readable text: {type(text).__name__}"
        )
    key = _require_plain_word(key, what="sequence parent key")
    needle = f"{key}:"
    lines = text.splitlines()
    key_indent: int | None = None
    start = -1
    for index, line in enumerate(lines):
        if needle in line:
            key_indent = len(line) - len(line.lstrip(" "))
            start = index
            break
    if key_indent is None:
        raise HarnessError(f"key {key!r} not found in dump text: {text!r}")
    for line in lines[start + 1 :]:
        stripped = line.lstrip(" ")
        if stripped.startswith("-"):
            dash_indent = len(line) - len(line.lstrip(" "))
            return key_indent, dash_indent
    raise HarnessError(f"no sequence dash after key {key!r}; text={text!r}")


def has_same_line_nested_dashes(text: str) -> bool:
    """Whether a parent dash and a child dash share one line."""
    if not isinstance(text, str):
        raise HarnessError(
            f"dump text is not readable text: {type(text).__name__}"
        )
    for line in text.splitlines():
        if re.search(r"-[ \t]+-", line):
            return True
    return False


def has_nested_dash_on_following_line(text: str) -> bool:
    """Whether a parent dash is followed by a child dash on a later line.

    Empty or flattened dumps (no later dash) are a classified absence.
    Unreadable input raises.
    """
    if not isinstance(text, str):
        raise HarnessError(
            f"dump text is not readable text: {type(text).__name__}"
        )
    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.lstrip(" ")
        if not stripped.startswith("-"):
            continue
        for later in lines[index + 1 :]:
            later_stripped = later.lstrip(" ")
            if not later_stripped:
                continue
            return later_stripped.startswith("-")
    return False


def mapping_key_position(text: str, key: str) -> int:
    """Index of ``key:`` in dump text. Missing key raises."""
    if not isinstance(text, str):
        raise HarnessError(
            f"dump text is not readable text: {type(text).__name__}"
        )
    key = _require_plain_word(key, what="mapping key")
    needle = f"{key}:"
    pos = text.find(needle)
    if pos < 0:
        raise HarnessError(f"key {key!r} not found in dump text: {text!r}")
    return pos


def flow_square_inner_space(text: str) -> bool:
    """Whether a ``[`` has inner whitespace (after ``[`` or before ``]``)."""
    if not isinstance(text, str):
        raise HarnessError(
            f"dump text is not readable text: {type(text).__name__}"
        )
    if "[" not in text or "]" not in text:
        raise HarnessError(f"no square brackets in dump text: {text!r}")
    return bool(re.search(r"\[\s", text) or re.search(r"\s\]", text))


def has_space_after_comma(text: str) -> bool:
    """Whether a comma is followed by a space. No comma raises."""
    if not isinstance(text, str):
        raise HarnessError(
            f"dump text is not readable text: {type(text).__name__}"
        )
    if "," not in text:
        raise HarnessError(f"no comma in dump text: {text!r}")
    return ", " in text


def has_space_after_colon(text: str) -> bool:
    """Whether a colon is followed by a space. No colon raises."""
    if not isinstance(text, str):
        raise HarnessError(
            f"dump text is not readable text: {type(text).__name__}"
        )
    if ":" not in text:
        raise HarnessError(f"no colon in dump text: {text!r}")
    return ": " in text


def quoted_token_present(text: str, token: str) -> bool:
    """Whether *token* appears wrapped in single or double quotes."""
    if not isinstance(text, str):
        raise HarnessError(
            f"dump text is not readable text: {type(text).__name__}"
        )
    if not isinstance(token, str) or not token:
        raise HarnessError("quoted token must be nonempty text")
    return ("'" + token + "'") in text or ('"' + token + '"') in text


def mapping_value_is_plain(text: str, key: str, value: str) -> bool:
    """Whether ``key: value`` appears without quotes around *value*."""
    if not isinstance(text, str):
        raise HarnessError(
            f"dump text is not readable text: {type(text).__name__}"
        )
    key = _require_plain_word(key, what="mapping key")
    if not isinstance(value, str) or not value:
        raise HarnessError("mapping value must be nonempty text")
    return f"{key}: {value}" in text


def _indent_of_key(text: str, key: str) -> int:
    needle = f"{key}:"
    for line in text.splitlines():
        if needle in line:
            return len(line) - len(line.lstrip(" "))
    raise HarnessError(f"key {key!r} not found in dump text: {text!r}")


# ---------------------------------------------------------------------------
# F06: custom-tag descriptions, schema attach/create, tagged parse/dump
# ---------------------------------------------------------------------------

_F06_PUBLIC_LOCAL_TAGS = frozenset(
    {
        "!tag2",
        "!point",
        "!space",
        "!Include",
        "!foo",
        "!foo2",
        "!bar",
        "!unknown_scalar_tag",
        "!unknown_sequence_tag",
        "!unknown_mapping_tag",
    }
)
_F06_SCHEMA_EXPORTS = frozenset(
    {SCHEMA_CORE, SCHEMA_JSON, SCHEMA_FAILSAFE, SCHEMA_YAML11}
)
_F06_SPEC_KEY = "_f06_spec"
_F06_NEVER_INT = "int_object"
_F06_NEVER_XYZ = "xyz_point"
_F06_NEVER_SPACE = "space"


def _f06_local_tag(name: Any, *, what: str) -> str:
    if not isinstance(name, str) or not name.startswith("!"):
        raise HarnessError(f"{what} is not a local tag handle: {name!r}")
    if any(ch.isspace() for ch in name):
        raise HarnessError(f"{what} contains whitespace: {name!r}")
    return name


def _f06_schema_export(base: Any) -> str:
    if not isinstance(base, str) or base not in _F06_SCHEMA_EXPORTS:
        raise HarnessError(f"base schema is not a built-in export: {base!r}")
    return base


def _f06_as_specs(specs: Any, *, what: str) -> list[dict[str, Any]]:
    if specs is None:
        raise HarnessError(f"{what} is missing")
    if isinstance(specs, Mapping) and _F06_SPEC_KEY in specs:
        return [dict(specs)]
    if not isinstance(specs, (list, tuple)):
        raise HarnessError(f"{what} is not a spec list: {type(specs).__name__}")
    out: list[dict[str, Any]] = []
    for index, item in enumerate(specs):
        if not isinstance(item, Mapping) or _F06_SPEC_KEY not in item:
            raise HarnessError(f"{what}[{index}] is not a tag spec")
        out.append(dict(item))
    return out


def _f06_spec_groups(spec_groups: Any) -> list[list[dict[str, Any]]]:
    if not isinstance(spec_groups, (list, tuple)) or not spec_groups:
        raise HarnessError("spec_groups must be a nonempty sequence of spec lists")
    groups: list[list[dict[str, Any]]] = []
    for index, group in enumerate(spec_groups):
        groups.append(_f06_as_specs(group, what=f"spec_groups[{index}]"))
        if not groups[-1]:
            raise HarnessError(f"spec_groups[{index}] is empty")
    return groups


def _js_plain_tree(value: Any, *, what: str) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(int(value))
    if isinstance(value, float):
        return _js_embed(value, what=what)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (list, tuple)):
        parts = [
            _js_plain_tree(item, what=f"{what}[{index}]")
            for index, item in enumerate(value)
        ]
        return "[" + ", ".join(parts) + "]"
    if isinstance(value, Mapping):
        parts = []
        for index, (key, item) in enumerate(value.items()):
            if not isinstance(key, str) or not key:
                raise HarnessError(f"{what} key {index} is not text")
            parts.append(
                f"{json.dumps(key)}: {_js_plain_tree(item, what=f'{what}.{key}')}"
            )
        return "{ " + ", ".join(parts) + " }"
    raise HarnessError(
        f"{what} cannot be embedded as a plain JS value: {type(value).__name__}"
    )


def _js_tag(spec: Mapping[str, Any]) -> str:
    kind = spec.get(_F06_SPEC_KEY)
    name = json.dumps(spec.get("name"))
    prefix = "true" if spec.get("prefix") else "false"
    if kind == "scalar_int_object":
        field = json.dumps(spec["field"])
        return (
            "lib.defineScalarTag(" + name + ", {\n"
            f"  matchByTagPrefix: {prefix},\n"
            "  resolve: (source) => {\n"
            "    const o = { __f06: 'f06_int_object' };\n"
            f"    o[{field}] = Number.parseInt(source, 10);\n"
            "    return o;\n"
            "  },\n"
            "  identify: (v) => !!(v && typeof v === 'object' && "
            "v.__f06 === 'f06_int_object'),\n"
            f"  represent: (v) => String(v[{field}])\n"
            "})"
        )
    if kind == "scalar_text":
        return (
            "lib.defineScalarTag(" + name + ", {\n"
            f"  matchByTagPrefix: {prefix},\n"
            "  resolve: (source) => source\n"
            "})"
        )
    if kind == "scalar_stamp":
        stamp = json.dumps(spec["stamp"])
        implicit = "true" if spec.get("implicit") else "false"
        return (
            "lib.defineScalarTag(" + name + ", {\n"
            f"  implicit: {implicit},\n"
            f"  matchByTagPrefix: {prefix},\n"
            "  resolve: (source) => ({ __f06: 'f06_stamp', "
            f"stamp: {stamp}, text: source }}),\n"
            "  identify: (v) => !!(v && v.__f06 === 'f06_stamp' && "
            f"v.stamp === {stamp}),\n"
            "  represent: (v) => String(v.text)\n"
            "})"
        )
    if kind == "scalar_remember":
        return (
            "lib.defineScalarTag(" + name + ", {\n"
            f"  matchByTagPrefix: {prefix},\n"
            "  resolve: (source, _explicit, tagName) => ({ __f06: 'f06_remember', "
            "kind: 'scalar', tagName, body: source }),\n"
            "  identify: (v) => !!(v && v.__f06 === 'f06_remember' && "
            "v.kind === 'scalar'),\n"
            "  representTagName: (v) => v.tagName,\n"
            "  represent: (v) => v.body\n"
            "})"
        )
    if kind == "sequence_xyz":
        return (
            "lib.defineSequenceTag(" + name + ", {\n"
            f"  matchByTagPrefix: {prefix},\n"
            "  create: () => ({ __f06: 'f06_xyz', x: 0, y: 0, z: 0 }),\n"
            "  addItem: (point, value, index) => {\n"
            "    if (index === 0) point.x = value;\n"
            "    else if (index === 1) point.y = value;\n"
            "    else if (index === 2) point.z = value;\n"
            "  },\n"
            "  identify: (v) => !!(v && v.__f06 === 'f06_xyz'),\n"
            "  represent: (point) => [point.x, point.y, point.z]\n"
            "})"
        )
    if kind == "sequence_frozen":
        arity = int(spec["arity"])
        return (
            "lib.defineSequenceTag(" + name + ", {\n"
            f"  matchByTagPrefix: {prefix},\n"
            "  create: () => [],\n"
            "  addItem: (carrier, item) => { carrier.push(item); },\n"
            "  finalize: (carrier) => {\n"
            f"    if (carrier.length !== {arity}) "
            "throw new Error('refused collected items');\n"
            "    const o = { __f06: 'f06_frozen' };\n"
            "    for (let i = 0; i < carrier.length; i++) o['n' + i] = carrier[i];\n"
            "    return o;\n"
            "  },\n"
            "  identify: (v) => !!(v && v.__f06 === 'f06_frozen'),\n"
            "  represent: (v) => {\n"
            "    const out = [];\n"
            "    for (let i = 0; ; i++) {\n"
            "      const key = 'n' + i;\n"
            "      if (!Object.prototype.hasOwnProperty.call(v, key)) break;\n"
            "      out.push(v[key]);\n"
            "    }\n"
            "    return out;\n"
            "  }\n"
            "})"
        )
    if kind == "sequence_stamp":
        stamp = json.dumps(spec["stamp"])
        return (
            "lib.defineSequenceTag(" + name + ", {\n"
            f"  matchByTagPrefix: {prefix},\n"
            f"  create: () => ({{ __f06: 'f06_seqstamp', stamp: {stamp}, items: [] }}),\n"
            "  addItem: (carrier, item) => { carrier.items.push(item); },\n"
            "  identify: (v) => !!(v && v.__f06 === 'f06_seqstamp' && "
            f"v.stamp === {stamp}),\n"
            "  represent: (v) => v.items\n"
            "})"
        )
    if kind == "sequence_remember":
        return (
            "lib.defineSequenceTag(" + name + ", {\n"
            f"  matchByTagPrefix: {prefix},\n"
            "  create: (tagName) => ({ __f06: 'f06_remember', kind: 'sequence', "
            "tagName, body: [] }),\n"
            "  addItem: (carrier, item) => { carrier.body.push(item); },\n"
            "  identify: (v) => !!(v && v.__f06 === 'f06_remember' && "
            "v.kind === 'sequence'),\n"
            "  representTagName: (v) => v.tagName,\n"
            "  represent: (v) => v.body\n"
            "})"
        )
    if kind == "mapping_space":
        return (
            "lib.defineMappingTag(" + name + ", {\n"
            f"  matchByTagPrefix: {prefix},\n"
            "  create: () => ({ __f06: 'f06_space', height: 0, width: 0, points: [] }),\n"
            "  addPair: (space, key, value) => {\n"
            "    if (key === 'height') space.height = value;\n"
            "    else if (key === 'width') space.width = value;\n"
            "    else if (key === 'points') space.points = value;\n"
            "    return '';\n"
            "  },\n"
            "  has: () => false,\n"
            "  keys: (space) => ['height', 'width', 'points'],\n"
            "  get: (space, key) => space[key],\n"
            "  identify: (v) => !!(v && v.__f06 === 'f06_space'),\n"
            "  represent: (space) => new Map([\n"
            "    ['height', space.height],\n"
            "    ['width', space.width],\n"
            "    ['points', space.points]\n"
            "  ])\n"
            "})"
        )
    if kind == "mapping_pairs":
        return (
            "lib.defineMappingTag(" + name + ", {\n"
            f"  matchByTagPrefix: {prefix},\n"
            "  create: () => ({}),\n"
            "  addPair: (container, key, value) => {\n"
            "    container[String(key)] = value;\n"
            "    return '';\n"
            "  },\n"
            "  has: (container, key) => Object.prototype.hasOwnProperty.call("
            "container, String(key)),\n"
            "  keys: (container) => Object.keys(container),\n"
            "  get: (container, key) => container[String(key)]\n"
            "})"
        )
    if kind == "mapping_remember":
        return (
            "lib.defineMappingTag(" + name + ", {\n"
            f"  matchByTagPrefix: {prefix},\n"
            "  create: (tagName) => ({ __f06: 'f06_remember', kind: 'mapping', "
            "tagName, body: {} }),\n"
            "  addPair: (carrier, key, value) => {\n"
            "    carrier.body[String(key)] = value;\n"
            "    return '';\n"
            "  },\n"
            "  has: (carrier, key) => Object.prototype.hasOwnProperty.call("
            "carrier.body, String(key)),\n"
            "  keys: (carrier) => Object.keys(carrier.body),\n"
            "  get: (carrier, key) => carrier.body[String(key)],\n"
            "  identify: (v) => !!(v && v.__f06 === 'f06_remember' && "
            "v.kind === 'mapping'),\n"
            "  representTagName: (v) => v.tagName,\n"
            "  represent: (v) => new Map(Object.entries(v.body))\n"
            "})"
        )
    raise HarnessError(f"tag spec kind is not usable: {kind!r}")


def _js_attach_schema(specs: Sequence[Mapping[str, Any]], base: str) -> str:
    export = _f06_schema_export(base)
    tags = ",\n".join(_js_tag(spec) for spec in specs)
    return (
        f"const tags = [\n{tags}\n];\n"
        f"const schema = lib[{json.dumps(export)}].withTags(tags);\n"
    )


def _js_sequential_schema(
    spec_groups: Sequence[Sequence[Mapping[str, Any]]], base: str
) -> str:
    export = _f06_schema_export(base)
    lines = [f"let schema = lib[{json.dumps(export)}];"]
    for group in spec_groups:
        tags = ",\n".join(_js_tag(spec) for spec in group)
        lines.append(f"schema = schema.withTags([\n{tags}\n]);")
    return "\n".join(lines) + "\n"


def _js_never_parsed(kind: str, payload: Mapping[str, Any]) -> str:
    if not isinstance(kind, str) or not kind:
        raise HarnessError("never-parsed kind must be nonempty text")
    if not isinstance(payload, Mapping):
        raise HarnessError(
            f"never-parsed payload is not a mapping: {type(payload).__name__}"
        )
    if kind == _F06_NEVER_INT:
        field = payload.get("field")
        value = payload.get("value")
        if not isinstance(field, str) or not field:
            raise HarnessError("int_object payload field must be nonempty text")
        if not isinstance(value, int) or isinstance(value, bool):
            raise HarnessError("int_object payload value must be an int")
        return (
            "{ __f06: 'f06_int_object', "
            f"{json.dumps(field)}: {int(value)} }}"
        )
    if kind == _F06_NEVER_XYZ:
        for key in ("x", "y", "z"):
            number = payload.get(key)
            if not isinstance(number, int) or isinstance(number, bool):
                raise HarnessError(f"xyz_point payload {key} must be an int")
        return (
            "{ __f06: 'f06_xyz', "
            f"x: {int(payload['x'])}, y: {int(payload['y'])}, "
            f"z: {int(payload['z'])} }}"
        )
    if kind == _F06_NEVER_SPACE:
        height = payload.get("height")
        width = payload.get("width")
        points = payload.get("points")
        if not isinstance(height, int) or isinstance(height, bool):
            raise HarnessError("space payload height must be an int")
        if not isinstance(width, int) or isinstance(width, bool):
            raise HarnessError("space payload width must be an int")
        if not isinstance(points, (list, tuple)):
            raise HarnessError("space payload points must be a sequence")
        pts = _js_plain_tree(list(points), what="space.points")
        return (
            "{ __f06: 'f06_space', "
            f"height: {int(height)}, width: {int(width)}, points: {pts} }}"
        )
    raise HarnessError(f"never-parsed kind is not usable: {kind!r}")


def _eval_f06(source: str) -> CallResult:
    if not isinstance(source, str) or not source:
        raise HarnessError("F06 evaluate source is empty")
    print(f"[helpers] f06-eval chars={len(source)}", flush=True)
    return evaluate(source)


def scalar_int_object_spec(
    name: str, *, field: str, prefix: bool = False
) -> dict[str, Any]:
    """Explicit scalar: decimal integer text becomes a caller object.

    *field* is the property that holds the integer. Construction
    failure raises.
    """
    handle = _f06_local_tag(name, what="scalar int-object tag")
    key = _require_plain_word(field, what="int-object field")
    if type(prefix) is not bool:
        raise HarnessError("prefix flag must be a boolean")
    return {
        _F06_SPEC_KEY: "scalar_int_object",
        "name": handle,
        "field": key,
        "prefix": prefix,
    }


def scalar_text_spec(name: str) -> dict[str, Any]:
    """Explicit scalar whose constructed value is the source text."""
    handle = _f06_local_tag(name, what="scalar text tag")
    return {_F06_SPEC_KEY: "scalar_text", "name": handle, "prefix": False}


def scalar_stamp_spec(
    name: str,
    stamp: str,
    *,
    prefix: bool = False,
    implicit: bool = False,
) -> dict[str, Any]:
    """Scalar whose result carries a test-written stamp plus the source text.

    *stamp* must not be the tag name. Construction failure raises.
    """
    handle = _f06_local_tag(name, what="scalar stamp tag")
    if not isinstance(stamp, str) or not stamp:
        raise HarnessError("stamp must be nonempty text")
    if stamp == handle:
        raise HarnessError("stamp must not be the tag name")
    if type(prefix) is not bool or type(implicit) is not bool:
        raise HarnessError("prefix and implicit flags must be booleans")
    return {
        _F06_SPEC_KEY: "scalar_stamp",
        "name": handle,
        "stamp": stamp,
        "prefix": prefix,
        "implicit": implicit,
    }


def scalar_remember_spec(name: str, *, prefix: bool = True) -> dict[str, Any]:
    """Scalar that remembers the node tag name and the source text."""
    handle = _f06_local_tag(name, what="scalar remember tag")
    if type(prefix) is not bool:
        raise HarnessError("prefix flag must be a boolean")
    return {
        _F06_SPEC_KEY: "scalar_remember",
        "name": handle,
        "prefix": prefix,
    }


def sequence_xyz_spec(name: str) -> dict[str, Any]:
    """Sequence that stores items in order as ``x`` / ``y`` / ``z``."""
    handle = _f06_local_tag(name, what="xyz sequence tag")
    return {_F06_SPEC_KEY: "sequence_xyz", "name": handle, "prefix": False}


def sequence_frozen_point_spec(
    name: str, *, arity: int = 2
) -> dict[str, Any]:
    """Sequence that collects items and yields a different result.

    Wrong length is a refusal. Identification is self-contained so a
    never-parsed value of the same family can be dumped.
    """
    handle = _f06_local_tag(name, what="frozen-point sequence tag")
    if not isinstance(arity, int) or isinstance(arity, bool) or arity < 1:
        raise HarnessError(f"frozen-point arity must be a positive int, got {arity!r}")
    return {
        _F06_SPEC_KEY: "sequence_frozen",
        "name": handle,
        "prefix": False,
        "arity": arity,
    }


def sequence_stamp_spec(name: str, stamp: str) -> dict[str, Any]:
    """Exact sequence whose result carries a test-written stamp and the items."""
    handle = _f06_local_tag(name, what="sequence stamp tag")
    if not isinstance(stamp, str) or not stamp:
        raise HarnessError("sequence stamp must be nonempty text")
    if stamp == handle:
        raise HarnessError("sequence stamp must not be the tag name")
    return {
        _F06_SPEC_KEY: "sequence_stamp",
        "name": handle,
        "stamp": stamp,
        "prefix": False,
    }


def sequence_remember_spec(name: str, *, prefix: bool = True) -> dict[str, Any]:
    """Sequence that remembers the node tag name and the item list."""
    handle = _f06_local_tag(name, what="sequence remember tag")
    if type(prefix) is not bool:
        raise HarnessError("prefix flag must be a boolean")
    return {
        _F06_SPEC_KEY: "sequence_remember",
        "name": handle,
        "prefix": prefix,
    }


def mapping_space_spec(name: str) -> dict[str, Any]:
    """Mapping that understands ``height``, ``width``, and ``points``."""
    handle = _f06_local_tag(name, what="space mapping tag")
    return {_F06_SPEC_KEY: "mapping_space", "name": handle, "prefix": False}


def mapping_pairs_spec(name: str) -> dict[str, Any]:
    """Mapping that writes each pair onto an ordinary mapping."""
    handle = _f06_local_tag(name, what="pairs mapping tag")
    return {_F06_SPEC_KEY: "mapping_pairs", "name": handle, "prefix": False}


def mapping_remember_spec(name: str, *, prefix: bool = True) -> dict[str, Any]:
    """Mapping that remembers the node tag name and each pair."""
    handle = _f06_local_tag(name, what="mapping remember tag")
    if type(prefix) is not bool:
        raise HarnessError("prefix flag must be a boolean")
    return {
        _F06_SPEC_KEY: "mapping_remember",
        "name": handle,
        "prefix": prefix,
    }


def unique_local_tag() -> str:
    """``!`` plus a runtime word, avoiding the suite-named local tags."""
    for _ in range(32):
        handle = "!" + unique_token()
        if handle not in _F06_PUBLIC_LOCAL_TAGS:
            return handle
    raise HarnessError("could not draw a local tag handle")


def parse_with_attached_tags(
    source: str, specs: Any, *, base: str
) -> CallResult:
    """Attach *specs* to *base* and public single-document parse *source*."""
    if not isinstance(source, str):
        raise HarnessError("parse source must be text")
    attached = _f06_as_specs(specs, what="attached specs")
    js = (
        _js_attach_schema(attached, base)
        + f"return lib.load({json.dumps(source)}, {{ schema }});\n"
    )
    print(f"[helpers] parse-with-tags base={base} n={len(attached)}", flush=True)
    return _eval_f06(js)


def parse_with_sequential_attach(
    source: str, spec_groups: Any, *, base: str
) -> CallResult:
    """Attach each spec group in order, then public single-document parse."""
    if not isinstance(source, str):
        raise HarnessError("parse source must be text")
    groups = _f06_spec_groups(spec_groups)
    js = (
        _js_sequential_schema(groups, base)
        + f"return lib.load({json.dumps(source)}, {{ schema }});\n"
    )
    print(
        f"[helpers] sequential-attach base={base} groups={len(groups)}",
        flush=True,
    )
    return _eval_f06(js)


def dump_with_attached_tags(
    value: Any, specs: Any, *, base: str
) -> CallResult:
    """Attach *specs* to *base* and public-dump a plain encodable *value*."""
    attached = _f06_as_specs(specs, what="dump specs")
    embedded = _js_plain_tree(value, what="dump value")
    js = (
        _js_attach_schema(attached, base)
        + f"return lib.dump({embedded}, {{ schema }});\n"
    )
    print(f"[helpers] dump-with-tags base={base} n={len(attached)}", flush=True)
    return _eval_f06(js)


def parse_then_dump_with_attached_tags(
    source: str, specs: Any, *, base: str
) -> CallResult:
    """Same process: attach, public parse, public dump. Returns the dump."""
    if not isinstance(source, str):
        raise HarnessError("parse source must be text")
    attached = _f06_as_specs(specs, what="parse-then-dump specs")
    js = (
        _js_attach_schema(attached, base)
        + f"const first = lib.load({json.dumps(source)}, {{ schema }});\n"
        + "return lib.dump(first, { schema });\n"
    )
    print(f"[helpers] parse-then-dump base={base} n={len(attached)}", flush=True)
    return _eval_f06(js)


def parse_dump_parse_with_attached_tags(
    source: str, specs: Any, *, base: str
) -> CallResult:
    """Same process: parse → dump → parse. Either step's failure is exposed."""
    if not isinstance(source, str):
        raise HarnessError("parse source must be text")
    attached = _f06_as_specs(specs, what="parse-dump-parse specs")
    js = (
        _js_attach_schema(attached, base)
        + f"const first = lib.load({json.dumps(source)}, {{ schema }});\n"
        + "const text = lib.dump(first, { schema });\n"
        + "return lib.load(text, { schema });\n"
    )
    print(
        f"[helpers] parse-dump-parse base={base} n={len(attached)}",
        flush=True,
    )
    return _eval_f06(js)


def dump_never_parsed_with_attached_tags(
    kind: str, payload: Mapping[str, Any], specs: Any, *, base: str
) -> CallResult:
    """Construct a never-parsed value from *kind*/*payload* and public-dump it.

    ``int_object`` payload: ``field`` + ``value``.
    ``xyz_point`` payload: ``x`` / ``y`` / ``z``.
    ``space`` payload: ``height`` / ``width`` / ``points``.
    """
    attached = _f06_as_specs(specs, what="never-parsed dump specs")
    value_js = _js_never_parsed(kind, payload)
    js = (
        _js_attach_schema(attached, base)
        + f"const value = {value_js};\n"
        + "return lib.dump(value, { schema });\n"
    )
    print(
        f"[helpers] dump-never-parsed kind={kind!r} base={base}",
        flush=True,
    )
    return _eval_f06(js)


def dump_parse_never_parsed_with_attached_tags(
    kind: str, payload: Mapping[str, Any], specs: Any, *, base: str
) -> CallResult:
    """Never-parsed construct → dump → parse. Either step's failure is exposed."""
    attached = _f06_as_specs(specs, what="never-parsed dump-parse specs")
    value_js = _js_never_parsed(kind, payload)
    js = (
        _js_attach_schema(attached, base)
        + f"const value = {value_js};\n"
        + "const text = lib.dump(value, { schema });\n"
        + "return lib.load(text, { schema });\n"
    )
    print(
        f"[helpers] dump-parse-never-parsed kind={kind!r} base={base}",
        flush=True,
    )
    return _eval_f06(js)


def attempt_schema_attach(specs: Any, *, base: str) -> CallResult:
    """Attach *specs* to a built-in schema. Does not parse."""
    attached = _f06_as_specs(specs, what="attach specs")
    js = (
        _js_attach_schema(attached, base)
        + "return { usable: typeof schema.withTags === 'function' };\n"
    )
    print(f"[helpers] attempt-attach base={base} n={len(attached)}", flush=True)
    return _eval_f06(js)


def attempt_schema_create(specs: Any) -> CallResult:
    """Public create operation whose tag table is exactly *specs* (may be empty)."""
    if specs is None:
        raise HarnessError("create specs are missing")
    if isinstance(specs, (list, tuple)) and len(specs) == 0:
        attached: list[dict[str, Any]] = []
    else:
        attached = _f06_as_specs(specs, what="create specs")
    tags = ",\n".join(_js_tag(spec) for spec in attached)
    js = (
        f"const tags = [\n{tags}\n];\n"
        "const schema = new lib.Schema(tags);\n"
        "return { usable: typeof schema.withTags === 'function' };\n"
    )
    print(f"[helpers] attempt-create n={len(attached)}", flush=True)
    return _eval_f06(js)


def require_schema_unusable(result: CallResult) -> ErrorInfo:
    """Assert the attach/create operation failed and yielded no usable schema.

    A successful return (including an object the caller could keep) asserts.
    Unreadable results raise. A later parse failure is not used as evidence.
    """
    if result is None:
        raise HarnessError("schema operation result is missing")
    if not isinstance(result, CallResult):
        raise HarnessError(
            f"schema operation result is not CallResult: {type(result).__name__}"
        )
    if result.ok:
        assert False, (
            f"schema operation succeeded; caller obtained {result.value!r}"
        )
    if result.error is None:
        raise HarnessError("schema operation failed but error payload is missing")
    print(
        f"[helpers] schema unusable; "
        f"report={observer_visible_report(result.error)}",
        flush=True,
    )
    return result.error


def explicit_local_tag_present(text: str, handle: str) -> bool:
    """Whether *handle* appears as a local tag in dump text.

    Unreadable text raises. A classified absence is ``False``, never
    ``None``. A longer handle that only shares a prefix does not count.
    """
    if not isinstance(text, str):
        raise HarnessError(
            f"dump text is not readable text: {type(text).__name__}"
        )
    handle = _f06_local_tag(handle, what="explicit local tag")
    start = 0
    while True:
        pos = text.find(handle, start)
        if pos < 0:
            return False
        after = pos + len(handle)
        if after >= len(text) or not (
            text[after].isalnum() or text[after] in "_-"
        ):
            return True
        start = after


def require_explicit_local_tag(text: str, handle: str) -> None:
    """Assert dump text contains the local tag *handle*."""
    present = explicit_local_tag_present(text, handle)
    print(
        f"[helpers] explicit-tag present={present} handle={handle!r}",
        flush=True,
    )
    assert present, f"dump text has no local tag {handle!r}; text={text!r}"


def require_no_explicit_local_tag(text: str, handle: str) -> None:
    """Assert dump text does not contain the local tag *handle*."""
    present = explicit_local_tag_present(text, handle)
    print(
        f"[helpers] explicit-tag absent={not present} handle={handle!r}",
        flush=True,
    )
    assert not present, f"dump text unexpectedly has {handle!r}; text={text!r}"


def require_caller_mapping(value: Any) -> Any:
    """Return *value* if it is a caller mapping; sequences and scalars assert.

    Unreadable input raises.
    """
    if isinstance(value, JsObject):
        return value
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        assert False, f"expected a caller mapping, got a sequence: {value!r}"
    if _is_readable_observation(value):
        assert False, (
            f"expected a caller mapping, got {type(value).__name__}: {value!r}"
        )
    raise HarnessError(
        f"cannot classify caller mapping: {type(value).__name__}"
    )


def value_holds_numbers(value: Any, expected: Sequence[Any]) -> bool:
    """Whether *expected* numbers are visible as items or mapping values.

    One level only. A read that cannot classify *value* raises — never
    returns False to mean "could not look".
    """
    if value is None and expected is not None:
        # None is a classified constructed null, not a missing read.
        pass
    if not isinstance(expected, (list, tuple)) or not expected:
        raise HarnessError("expected numbers must be a nonempty sequence")
    for index, item in enumerate(expected):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise HarnessError(
                f"expected number {index} is not a number: {item!r}"
            )
    nums: list[Any] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, bool):
                continue
            if isinstance(item, (int, float)):
                nums.append(item)
            elif not _is_readable_observation(item):
                raise HarnessError(
                    f"cannot classify sequence item: {type(item).__name__}"
                )
    elif isinstance(value, (JsObject, dict)):
        for item in value.values():
            if isinstance(item, bool):
                continue
            if isinstance(item, (int, float)):
                nums.append(item)
            elif not _is_readable_observation(item):
                raise HarnessError(
                    f"cannot classify mapping value: {type(item).__name__}"
                )
    elif isinstance(value, bool):
        pass
    elif isinstance(value, (int, float)):
        nums.append(value)
    elif _is_readable_observation(value):
        pass
    else:
        raise HarnessError(
            f"cannot classify numbers on {type(value).__name__}"
        )
    held = all(any(number == want for number in nums) for want in expected)
    print(
        f"[helpers] holds-numbers held={held} nums={nums!r} "
        f"expected={list(expected)!r}",
        flush=True,
    )
    return held


def _remembered_walk(value: Any) -> tuple[list[str], list[Any], list[Any]]:
    texts: list[str] = []
    sequences: list[Any] = []
    mappings: list[Any] = []

    def take(item: Any, depth: int) -> None:
        if depth > 2:
            return
        if isinstance(item, str):
            texts.append(item)
            return
        if isinstance(item, list):
            sequences.append(item)
            for child in item:
                take(child, depth + 1)
            return
        if isinstance(item, (JsObject, dict)):
            mappings.append(item)
            for child in item.values():
                take(child, depth + 1)
            return
        if isinstance(item, (int, float, bool)) or item is None:
            return
        if _is_readable_observation(item):
            return
        raise HarnessError(
            f"cannot classify remembered field: {type(item).__name__}"
        )

    take(value, 0)
    return texts, sequences, mappings


def _sequence_matches(observed: Sequence[Any], content: Sequence[Any]) -> bool:
    if len(observed) != len(content):
        return False
    for left, right in zip(observed, content):
        if isinstance(right, (int, float)) and not isinstance(right, bool):
            if isinstance(left, bool) or not isinstance(left, (int, float)):
                return False
            if left != right:
                return False
        elif left != right:
            return False
    return True


def _mapping_holds_pairs(observed: Any, content: Mapping[str, Any]) -> bool:
    try:
        mapping = require_plain_mapping(observed)
    except AssertionError:
        return False
    for key, want in content.items():
        if key not in mapping:
            return False
        got = mapping[key]
        if isinstance(want, (int, float)) and not isinstance(want, bool):
            if isinstance(got, bool) or not isinstance(got, (int, float)):
                return False
            if got != want:
                return False
        elif got != want:
            return False
    return True


def require_remembered(value: Any, name: str, content: Any) -> None:
    """Assert a remembered-tag value shows *name* and *content*.

    *content* is scalar text, a number sequence, or key/value pairs.
    Field names stay inside the remember spec. Unreadable input raises.
    """
    if not isinstance(name, str) or not name:
        raise HarnessError("remembered name must be nonempty text")
    obj = require_caller_mapping(value)
    texts, sequences, mappings = _remembered_walk(obj)
    print(
        f"[helpers] remembered name={name!r} texts={texts!r} "
        f"nseq={len(sequences)} nmap={len(mappings)}",
        flush=True,
    )
    if name not in texts:
        assert False, (
            f"remembered tag name {name!r} is not visible; texts={texts!r}"
        )
    if isinstance(content, str):
        if content not in texts:
            assert False, (
                f"remembered text {content!r} is not visible; texts={texts!r}"
            )
        return
    if isinstance(content, (list, tuple)):
        if any(_sequence_matches(seq, content) for seq in sequences):
            return
        assert False, f"remembered sequence {list(content)!r} is not visible"
    if isinstance(content, Mapping):
        if any(_mapping_holds_pairs(item, content) for item in mappings):
            return
        assert False, f"remembered pairs {dict(content)!r} are not visible"
    raise HarnessError(
        f"remembered content type is unusable: {type(content).__name__}"
    )


# ---------------------------------------------------------------------------
# F07: resource limits (nesting / alias / merge-key budgets)
# ---------------------------------------------------------------------------

# Sealed encodings for "unlimited" / "disabled". Feature tests must not
# write these sentinels; they go through the knob helpers below.
_F07_ALIAS_UNLIMITED = -1
_F07_MERGE_BUDGET_DISABLED = -1


def _f07_positive_int(value: Any, *, what: str, minimum: int = 1) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise HarnessError(f"{what} must be an int >= {minimum}, got {value!r}")
    return value


def _f07_pairs(
    pairs: Any, *, what: str, minimum: int = 1
) -> list[tuple[str, Any]]:
    if not isinstance(pairs, (list, tuple)) or len(pairs) < minimum:
        raise HarnessError(f"{what} must have at least {minimum} pairs")
    out: list[tuple[str, Any]] = []
    for index, item in enumerate(pairs):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise HarnessError(f"{what}[{index}] is not a pair")
        key = _require_plain_word(item[0], what=f"{what}[{index}] key")
        out.append((key, item[1]))
    return out


def _f07_alias_names(names: Any) -> list[str]:
    if not isinstance(names, (list, tuple)) or not names:
        raise HarnessError("alias_names must be a nonempty sequence")
    return [
        _require_plain_word(name, what=f"alias_names[{index}]")
        for index, name in enumerate(names)
    ]


def with_nesting_limit(n: int) -> dict[str, Any]:
    """Sealed parse options that set the collection nesting limit to *n*."""
    depth = _f07_positive_int(n, what="nesting limit")
    return {"maxDepth": depth}


def with_alias_budget(n: int) -> dict[str, Any]:
    """Sealed parse options that set the per-document alias budget to *n*."""
    budget = _f07_positive_int(n, what="alias budget", minimum=0)
    return {"maxAliases": budget}


def with_unlimited_alias_budget() -> dict[str, Any]:
    """Sealed parse options that explicitly request an unlimited alias budget."""
    return {"maxAliases": _F07_ALIAS_UNLIMITED}


def with_merge_budget(n: int) -> dict[str, Any]:
    """Sealed parse options that set the per-call merge-key budget to *n*."""
    budget = _f07_positive_int(n, what="merge budget", minimum=0)
    return {"maxTotalMergeKeys": budget}


def with_merge_budget_disabled() -> dict[str, Any]:
    """Sealed parse options that disable the merge-key budget."""
    return {"maxTotalMergeKeys": _F07_MERGE_BUDGET_DISABLED}


def merge_parse_options(*parts: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge parse option dicts. Conflicting keys raise; never silent override."""
    merged: dict[str, Any] = {}
    for index, part in enumerate(parts):
        if part is None:
            continue
        if not isinstance(part, Mapping):
            raise HarnessError(
                f"parse option part {index} is not a mapping: "
                f"{type(part).__name__}"
            )
        for key, value in part.items():
            if key in merged and merged[key] != value:
                raise HarnessError(
                    f"parse option {key!r} conflict: {merged[key]!r} vs {value!r}"
                )
            merged[key] = value
    return merged


def nested_empty_flow_sequences(n: int) -> str:
    """*n* nested empty flow sequences, innermost empty."""
    depth = _f07_positive_int(n, what="nested flow sequence depth")
    return ("[" * depth) + ("]" * depth) + "\n"


def nested_empty_flow_mappings(n: int) -> str:
    """*n* nested empty flow mappings with a scalar key; innermost empty.

    Does not use an empty mapping as a key.
    """
    depth = _f07_positive_int(n, what="nested flow mapping depth")
    if depth == 1:
        return "{}\n"
    body = "{}"
    for _ in range(depth - 1):
        body = "{ a: " + body + " }"
    return body + "\n"


def nested_empty_block_sequences(n: int) -> str:
    """*n* nested empty block sequences, innermost empty flow ``[]``."""
    depth = _f07_positive_int(n, what="nested block sequence depth")
    if depth == 1:
        return "[]\n"
    lines: list[str] = []
    for index in range(depth - 1):
        lines.append(("  " * index) + "-")
    lines.append(("  " * (depth - 1)) + "[]")
    return "\n".join(lines) + "\n"


def sibling_empty_flow_sequences(n: int) -> str:
    """One parent sequence holding *n* sibling empty sequences (depth 2)."""
    count = _f07_positive_int(n, what="sibling empty sequence count")
    inner = ", ".join("[]" for _ in range(count))
    return f"[{inner}]\n"


def nested_sequences_under_mapping(key: str, n: int) -> str:
    """A mapping whose value is *n* nested empty flow sequences."""
    name = _require_plain_word(key, what="nested-under-mapping key")
    return f"{name}: {nested_empty_flow_sequences(n)}"


def opening_brackets(n: int) -> str:
    """*n* opening square brackets and nothing else (hostile nest)."""
    count = _f07_positive_int(n, what="opening bracket count")
    return "[" * count


def two_alias_document(
    anchor: str, key: str, value: Any, alias_names: Sequence[str]
) -> str:
    """One anchored mapping plus alias keys that all point at it."""
    handle = _require_plain_word(anchor, what="two-alias anchor")
    inner = _require_plain_word(key, what="two-alias inner key")
    item = _plain_yaml_scalar(value, what="two-alias inner value")
    names = _f07_alias_names(alias_names)
    lines = [f"{handle}: &{handle} {{ {inner}: {item} }}"]
    for name in names:
        lines.append(f"{name}: *{handle}")
    return "\n".join(lines) + "\n"


def single_alias_document(
    anchor: str, key: str, value: Any, alias_name: str
) -> str:
    """One anchored mapping plus a single alias key."""
    alias = _require_plain_word(alias_name, what="single alias name")
    return two_alias_document(anchor, key, value, [alias])


def two_alias_sequence_document(anchor: str, key: str, value: Any) -> str:
    """An anchored mapping, then a sequence holding two aliases to it."""
    handle = _require_plain_word(anchor, what="sequence-alias anchor")
    inner = _require_plain_word(key, what="sequence-alias inner key")
    item = _plain_yaml_scalar(value, what="sequence-alias inner value")
    return f"- &{handle} {{ {inner}: {item} }}\n- [*{handle}, *{handle}]\n"


def recursive_self_alias_sequence(anchor: str) -> str:
    """A sequence that aliases itself: ``&anchor [*anchor]``."""
    handle = _require_plain_word(anchor, what="recursive alias anchor")
    return f"&{handle} [*{handle}]\n"


def two_docs_one_alias_each(
    first_anchor: str,
    first_key: str,
    first_value: Any,
    first_alias: str,
    second_anchor: str,
    second_key: str,
    second_value: Any,
    second_alias: str,
) -> str:
    """Two documents, each with one anchored mapping and one alias."""
    first = single_alias_document(
        first_anchor, first_key, first_value, first_alias
    )
    second = single_alias_document(
        second_anchor, second_key, second_value, second_alias
    )
    return first.rstrip("\n") + "\n---\n" + second


def shallow_alias_sequence_document(anchor: str, n: int) -> str:
    """An anchored empty sequence plus a sequence of *n* aliases to it."""
    handle = _require_plain_word(anchor, what="shallow-alias anchor")
    count = _f07_positive_int(n, what="shallow alias count")
    aliases = ", ".join(f"*{handle}" for _ in range(count))
    return f"- &{handle} []\n- [{aliases}]\n"


def one_key_merges_document(pairs: Sequence[tuple[str, Any]]) -> str:
    """Merge one-key mappings into one target. Sources sit in the ``<<`` list."""
    cleaned = _f07_pairs(pairs, what="one-key merge pairs")
    lines = ["<<:"]
    for index, (key, value) in enumerate(cleaned):
        item = _plain_yaml_scalar(value, what=f"one-key merge value {index}")
        lines.append(f"  - {{ {key}: {item} }}")
    return "\n".join(lines) + "\n"


def two_docs_merge_two_keys_each(
    first_pairs: Sequence[tuple[str, Any]],
    second_pairs: Sequence[tuple[str, Any]],
) -> str:
    """Two documents that each merge one already-two-key source."""
    first = _f07_pairs(first_pairs, what="first two-key merge", minimum=2)
    second = _f07_pairs(second_pairs, what="second two-key merge", minimum=2)
    if len(first) != 2:
        raise HarnessError("first two-key merge must be exactly two pairs")
    if len(second) != 2:
        raise HarnessError("second two-key merge must be exactly two pairs")
    left = "<<: " + _flow_map(dict(first), what="first two-key merge")
    right = "<<: " + _flow_map(dict(second), what="second two-key merge")
    return left + "\n---\n" + right + "\n"


def single_merge_of_mapping(pairs: Sequence[tuple[str, Any]]) -> str:
    """A sequence: source mapping, then one ``<<`` of that same mapping."""
    cleaned = _f07_pairs(pairs, what="single-merge pairs")
    handle = unique_token()
    lines = [f"- &{handle}"]
    for index, (key, value) in enumerate(cleaned):
        item = _plain_yaml_scalar(value, what=f"single-merge value {index}")
        lines.append(f"  {key}: {item}")
    lines.append(f"- <<: *{handle}")
    return "\n".join(lines) + "\n"


def double_merge_of_same_mapping(pairs: Sequence[tuple[str, Any]]) -> str:
    """A sequence: source mapping, then ``<<: [*s, *s]`` of that mapping."""
    cleaned = _f07_pairs(pairs, what="double-merge pairs")
    handle = unique_token()
    lines = [f"- &{handle}"]
    for index, (key, value) in enumerate(cleaned):
        item = _plain_yaml_scalar(value, what=f"double-merge value {index}")
        lines.append(f"  {key}: {item}")
    lines.append(f"- <<: [*{handle}, *{handle}]")
    return "\n".join(lines) + "\n"


def merge_chain_yaml(n: int) -> str:
    """A ``<<`` chain whose last mapping holds *n* keys.

    Each step merges the previous mapping and adds one new key. The last
    item of the constructed sequence is that mapping.
    """
    length = _f07_positive_int(n, what="merge chain length")
    parts = ["- &c0\n  k0: 0"]
    for index in range(1, length):
        parts.append(f"- &c{index}\n  <<: *c{index - 1}\n  k{index}: {index}")
    return "\n".join(parts) + "\n"


def nested_sequence_depth(value: Any) -> int:
    """Levels along the unique child sequence down to an empty sequence.

    Wrong shape asserts. Unreadable input raises. Never returns 0 to
    mean "could not look".
    """
    current = require_sequence(value)
    depth = 1
    while True:
        if len(current) == 0:
            print(f"[helpers] nested-seq-depth={depth}", flush=True)
            return depth
        if len(current) != 1:
            assert False, (
                f"nested sequence is not a single-child nest; "
                f"len={len(current)} value={current!r}"
            )
        child = current[0]
        if not isinstance(child, list):
            assert False, (
                f"nested sequence child is not a sequence: "
                f"{type(child).__name__}: {child!r}"
            )
        depth += 1
        current = child


def nested_mapping_depth(value: Any) -> int:
    """Levels along the unique child mapping down to an empty mapping.

    A complex key or any other wrong shape asserts. Unreadable input
    raises. Never returns 0 to mean "could not look".
    """
    current = require_plain_mapping(value)
    depth = 1
    while True:
        keys = list(current.keys())
        if len(keys) == 0:
            print(f"[helpers] nested-map-depth={depth}", flush=True)
            return depth
        if len(keys) != 1:
            assert False, (
                f"nested mapping is not a single-child nest; "
                f"keys={keys!r}"
            )
        child = current[keys[0]]
        if isinstance(child, (JsObject, dict)):
            current = child
            depth += 1
            continue
        if _is_readable_observation(child):
            assert False, (
                f"nested mapping child is not a mapping: "
                f"{type(child).__name__}: {child!r}"
            )
        raise HarnessError(
            f"cannot classify nested mapping child: {type(child).__name__}"
        )


def mapping_key_count(value: Any) -> int:
    """Number of keys on a constructed mapping. Unreadable input raises."""
    mapping = require_plain_mapping(value)
    count = len(list(mapping.keys()))
    print(f"[helpers] mapping-key-count={count}", flush=True)
    return count


def require_parse_failure_not_host_overflow(result: CallResult) -> ErrorInfo:
    """Classified parse failure after the process ended. Not a host crash.

    Timeout or a dead process is a harness failure (never green). Does
    not scan the payload for overflow wording. Success or an unreadable
    result must not be treated as "not overflow".
    """
    error = require_parse_failure(result)
    print(
        "[helpers] parse-failure-not-overflow "
        f"report={observer_visible_report(error)}",
        flush=True,
    )
    return error


def require_no_usable_prefix(result: CallResult) -> ErrorInfo:
    """Multi-document limit crossing: failure, not a successful prefix list."""
    error = require_parse_failure(result)
    print(
        "[helpers] no-usable-prefix "
        f"report={observer_visible_report(error)}",
        flush=True,
    )
    return error

