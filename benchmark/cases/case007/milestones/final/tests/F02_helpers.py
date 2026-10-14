# feature: F02
"""Observation helpers for HMAC-based one-time passwords (FP-02).

Helpers classify constructor, emit, and check outcomes. They never
return ``None`` to mean "the observation could not be classified".
Named secrets and codes are fixed inputs of this suite, not a copy
of product source. HMAC is never reimplemented here.
"""

from __future__ import annotations

import secrets
from collections.abc import Collection
from typing import Any

from _harness import (
    CallResult,
    HarnessError,
    call_method,
    require_exception,
    require_text,
    require_value,
)

# generated codes are decimal-digit text of the configured width.
DECIMAL_ALPHABET = frozenset("0123456789")

# RFC 4226 example secret and the ten published codes at 0–9.
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
RFC_CODES = (
    "755224",
    "287082",
    "359152",
    "969429",
    "338314",
    "254676",
    "287922",
    "162583",
    "399871",
    "520489",
)

# README secret and the three published codes at 0 / 1 / 1401.
README_SECRET = "base32secret3232"
README_AT_0 = "260182"
README_AT_1 = "055283"
README_AT_1401 = "316439"

# published five-code sequence.
N3OV_SECRET = "N3OVNIBRERIO5OHGVCMDGS4V4RJ3AUZOUN34J6FRM4P6JIFCG3ZA"
N3OV_CODES = (
    "737863",
    "390601",
    "363354",
    "936780",
    "654019",
)

# additional named secrets.
WRN3_SECRET = "wrn3pqx5uqxqvnqr"
GEZDGNBV_SECRET = "GEZDGNBV"
START1_AT_0 = "662488"
START1_AT_1 = "289363"

# named fullwidth-digit candidate for RFC relative count 0.
FULLWIDTH_755224 = "７５５２２４"

# Public emit / check entries on the HMAC helper (interface names).
EMIT_ENTRY = "at"
CHECK_ENTRY = "verify"

# Counts the plan publishes as goldens or neighbor checks. Unpublished
# relative-count draws must not land on these.
NAMED_RELATIVE_COUNTS = frozenset({0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 1401, 1402})
NAMED_STARTING_COUNTERS = frozenset({0, 1})
NAMED_NEGATIVE_RELATIVE_COUNTS = frozenset({-1})
NAMED_DIGIT_COUNTS_ABOVE_TEN = frozenset({11})

_UNPUBLISHED_BAND = 32
_UNPUBLISHED_MIN_ELIGIBLE = 16
_UNPUBLISHED_SKIP_PREFIX = 4

# Maps ASCII digits onto their fullwidth (NFKC-equivalent) forms.
_FULLWIDTH_DIGIT_TABLE = str.maketrans("0123456789", "０１２３４５６７８９")


def _is_usable_helper(value: Any) -> bool:
    """Return whether *value* is an ``HOTP`` or ``TOTP`` instance.

    The Interface Contract states a refused construction or parse as
    "raises, or returns something that is not an HOTP/TOTP instance";
    a successful one returns such an instance.
    """
    from otpkit import HOTP, TOTP

    return isinstance(value, (HOTP, TOTP))


def _require_decimal_text(value: str, *, label: str) -> str:
    if not isinstance(value, str):
        raise AssertionError(
            f"{label} is {type(value).__name__}, not text; "
            "there is no decimal code to observe"
        )
    if not value:
        raise AssertionError(f"{label} is empty; there is no decimal code to observe")
    illegal = sorted({ch for ch in value if ch not in DECIMAL_ALPHABET})
    if illegal:
        raise AssertionError(
            f"{label} is not decimal-digit text: "
            f"type={type(value).__name__} length={len(value)} "
            f"illegal={illegal!r} value={value!r}"
        )
    return value


def require_helper(result: CallResult) -> object:
    """Return a constructed helper.

    The constructor must have returned. ``None``, text, or a number is
    not a helper — never a sentinel for "construction failed".
    """
    value = require_value(result)
    if not _is_usable_helper(value):
        raise AssertionError(
            "construction did not hand back a helper: "
            f"type={type(value).__name__} value={value!r}"
        )
    print(f"helper ok type={type(value).__name__}", flush=True)
    return value


def require_code(result: CallResult, width: int) -> str:
    """Return a successful code: text, exactly *width* decimal digits."""
    if not isinstance(width, int) or isinstance(width, bool) or width < 1:
        raise HarnessError(f"require_code width is not a usable digit count: {width!r}")
    text = require_text(result)
    actual_len = len(text)
    illegal = sorted({ch for ch in text if ch not in DECIMAL_ALPHABET})
    if actual_len != width or illegal:
        raise AssertionError(
            "emitted code is not decimal text of the configured width: "
            f"type={type(text).__name__} length={actual_len} expected={width} "
            f"illegal={illegal!r} value={text!r}"
        )
    print(f"code ok width={actual_len} value={text!r}", flush=True)
    return text


def require_named_code(result: CallResult, expected: str) -> str:
    """Return a code that equals a suite-named string (after width/type)."""
    if not isinstance(expected, str) or not expected:
        raise HarnessError(f"require_named_code expected is not a named code: {expected!r}")
    code = require_code(result, len(expected))
    assert code == expected, (
        "emitted code is not the named string: "
        f"expected={expected!r} got={code!r}"
    )
    print(f"named code ok expected={expected!r}", flush=True)
    return code


def require_emit_refused(result: CallResult) -> BaseException:
    """Require an emit abort with no code string.

    The caller must observe a failure (any exception; class and message
    are not pinned) and ``value`` must not be a code string. Returning
    ``None`` without failing is not an abort.
    """
    exc = require_exception(result)
    assert not isinstance(result.value, str), (
        "negative-count emit still handed back a code string: "
        f"{result.value!r}"
    )
    print(
        f"emit refused; no code string returned "
        f"(carrier={type(exc).__name__})",
        flush=True,
    )
    return exc


def require_construction_refused(result: CallResult) -> None:
    """Require that construction did not hand back a usable helper.

    The PRD says construction "does not succeed"; they do not require
    an exception. A returned ``None`` / text / number, or a captured
    exception whose value is not a helper, both count. A returned helper
    does not. Emit is never probed to interpret this outcome.
    """
    if result.exception is not None:
        if _is_usable_helper(result.value):
            raise AssertionError(
                "construction reported a failure but still handed back a helper: "
                f"type={type(result.value).__name__}"
            )
        print(
            "construction refused; no helper returned "
            f"(carrier={type(result.exception).__name__})",
            flush=True,
        )
        return
    if _is_usable_helper(result.value):
        raise AssertionError(
            "construction returned a usable helper; "
            f"type={type(result.value).__name__}"
        )
    print(
        "construction refused; no helper returned "
        f"(value_type={type(result.value).__name__})",
        flush=True,
    )


def emit_at(helper: object, count: int) -> CallResult:
    """Drive the public emit entry at relative *count*."""
    return call_method(helper, EMIT_ENTRY, count)


def check_candidate(helper: object, candidate: str, count: int) -> CallResult:
    """Drive the public check entry at relative *count*."""
    return call_method(helper, CHECK_ENTRY, candidate, count)


def require_check_returned(result: CallResult) -> Any:
    """Return a check outcome. Aborting the caller fails the observation.

    The exception class name is printed only to show that an abort
    happened — it is not a contract.
    """
    if result.exception is not None:
        raise AssertionError(
            "check aborted the caller "
            f"(carrier={type(result.exception).__name__})"
        )
    print(
        f"check returned type={type(result.value).__name__}",
        flush=True,
    )
    return result.value


def success_carrier(helper: object, count: int) -> Any:
    """Return the check outcome of the code just emitted at *count*.

    Emit or check failure raises — never a sentinel.
    """
    emitted = emit_at(helper, count)
    code = _require_decimal_text(require_text(emitted), label="success-carrier emit")
    print(f"success-carrier emit count={count} code={code!r}", flush=True)
    return require_check_returned(check_candidate(helper, code, count))


def require_accepted(result: CallResult, carrier: Any) -> Any:
    """Require that a check returned the same value as *carrier*."""
    value = require_check_returned(result)
    assert value is True, (
        "an accepted check must return True (Interface Contract verify form): "
        f"got={value!r}"
    )
    assert value == carrier, (
        "check did not match the success carrier: "
        f"carrier={carrier!r} got={value!r}"
    )
    print("check accepted (returned True)", flush=True)
    return value


def require_rejected(result: CallResult, carrier: Any) -> Any:
    """Require that a check returned a value different from *carrier*."""
    value = require_check_returned(result)
    assert value is False, (
        "a rejected check must return False (Interface Contract verify form): "
        f"got={value!r}"
    )
    assert value != carrier, (
        "check matched the success carrier; the candidate was not rejected: "
        f"carrier={carrier!r} got={value!r}"
    )
    print("check rejected (returned False)", flush=True)
    return value


def _strip_secret_forms(text: str, *secret_values: str) -> str:
    stripped = text
    forms: set[str] = set()
    for secret in secret_values:
        if not isinstance(secret, str) or not secret:
            raise HarnessError(f"secret for stripping is not text: {secret!r}")
        forms.add(secret)
        forms.add(secret.upper())
        forms.add(secret.lower())
    for form in forms:
        stripped = stripped.replace(form, "")
    return stripped


def require_secret_bound_pair(
    code_a: str,
    code_b: str,
    secret_a: str,
    secret_b: str,
) -> None:
    """Require two codes still differ after stripping both secrets.

    The secret is a construction input and the code is
    indexed by secret plus count. After removing the secret strings
    themselves (and their letter-case variants) a stable difference
    must remain. HMAC is not mirrored.
    """
    _require_decimal_text(code_a, label="secret-bound code A")
    _require_decimal_text(code_b, label="secret-bound code B")
    stripped_a = _strip_secret_forms(code_a, secret_a, secret_b)
    stripped_b = _strip_secret_forms(code_b, secret_a, secret_b)
    print(
        f"secret-bound stripped_a={stripped_a!r} stripped_b={stripped_b!r}",
        flush=True,
    )
    assert stripped_a != stripped_b, (
        "codes for two secrets are not distinguishable after removing "
        "the secret strings themselves: "
        f"code_a={code_a!r} code_b={code_b!r}"
    )


def _pick_unpublished_int(
    band: list[int],
    forbidden: Collection[int],
    *,
    predicate: Any,
    label: str,
) -> int:
    if not band:
        raise HarnessError(f"{label}: empty selection band")
    forbidden_set = set(forbidden)
    eligible = [n for n in band if n not in forbidden_set and predicate(n)]
    if len(eligible) < _UNPUBLISHED_MIN_ELIGIBLE:
        raise HarnessError(
            f"{label} band has {len(eligible)} eligible integers; "
            f"need at least {_UNPUBLISHED_MIN_ELIGIBLE} "
            f"(forbidden={sorted(forbidden_set)!r})"
        )
    skip = _UNPUBLISHED_SKIP_PREFIX
    if len(eligible) - skip < 1:
        raise HarnessError(
            f"{label} pool after skipping the prefix is empty: "
            f"eligible={len(eligible)} skip={skip}"
        )
    pool = eligible[skip:]
    chosen = secrets.SystemRandom().choice(pool)
    if chosen in forbidden_set or not predicate(chosen):
        raise HarnessError(
            f"{label} produced a named or out-of-band value: {chosen!r} "
            f"(forbidden={sorted(forbidden_set)!r})"
        )
    print(f"{label} chosen={chosen}", flush=True)
    return chosen


def unpublished_relative_count(forbidden: Collection[int]) -> int:
    """Pick a non-negative relative count the plan does not name."""
    merged = set(forbidden) | NAMED_RELATIVE_COUNTS
    band = list(range(0, 0 + _UNPUBLISHED_BAND + 16))
    return _pick_unpublished_int(
        band,
        merged,
        predicate=lambda n: isinstance(n, int) and not isinstance(n, bool) and n >= 0,
        label="unpublished_relative_count",
    )


def unpublished_starting_counter(forbidden: Collection[int]) -> int:
    """Pick a starting counter the plan does not name."""
    merged = set(forbidden) | NAMED_STARTING_COUNTERS
    band = list(range(0, 0 + _UNPUBLISHED_BAND + 16))
    return _pick_unpublished_int(
        band,
        merged,
        predicate=lambda n: isinstance(n, int) and not isinstance(n, bool) and n >= 0,
        label="unpublished_starting_counter",
    )


def unpublished_negative_relative_count(forbidden: Collection[int]) -> int:
    """Pick a negative relative count other than the named −1."""
    merged = set(forbidden) | NAMED_NEGATIVE_RELATIVE_COUNTS
    band = list(range(-2, -2 - _UNPUBLISHED_BAND, -1))
    return _pick_unpublished_int(
        band,
        merged,
        predicate=lambda n: isinstance(n, int) and not isinstance(n, bool) and n < 0,
        label="unpublished_negative_relative_count",
    )


def unpublished_digit_count_above_ten(forbidden: Collection[int]) -> int:
    """Pick a digit count greater than 10 that is not the named 11."""
    merged = set(forbidden) | NAMED_DIGIT_COUNTS_ABOVE_TEN
    band = list(range(12, 12 + _UNPUBLISHED_BAND))
    return _pick_unpublished_int(
        band,
        merged,
        predicate=lambda n: isinstance(n, int) and not isinstance(n, bool) and n > 10,
        label="unpublished_digit_count_above_ten",
    )


def unpublished_clock_pair(min_apart: float = 30) -> tuple[float, float]:
    """Return two unpublished epochs at least *min_apart* seconds apart."""
    try:
        gap_floor = float(min_apart)
    except (TypeError, ValueError) as exc:
        raise HarnessError(
            f"unpublished_clock_pair min_apart is not a number: {min_apart!r}"
        ) from exc
    if gap_floor <= 0:
        raise HarnessError(
            f"unpublished_clock_pair min_apart must be positive: {min_apart!r}"
        )
    rng = secrets.SystemRandom()
    first = rng.uniform(10_000.0, 1_800_000_000.0)
    gap = gap_floor + rng.uniform(1.0, 86_400.0)
    second = first + gap
    if first == second or abs(second - first) < gap_floor:
        raise HarnessError(
            "unpublished_clock_pair could not form two epochs "
            f">= {gap_floor} seconds apart: {first!r} {second!r}"
        )
    print(
        f"unpublished_clock_pair first={first!r} second={second!r} "
        f"gap={abs(second - first)!r}",
        flush=True,
    )
    return (first, second)


def fullwidth_digit_form(code: str) -> str:
    """Map ASCII digits onto the fullwidth digits."""
    _require_decimal_text(code, label="fullwidth_digit_form input")
    mapped = code.translate(_FULLWIDTH_DIGIT_TABLE)
    if mapped == code:
        raise HarnessError(
            "fullwidth_digit_form produced no digit-shape change: "
            f"{code!r}"
        )
    print(f"fullwidth form {code!r} -> {mapped!r}", flush=True)
    return mapped


def hmac_app_source(pkg: str, secret: str) -> str:
    """Dependent-app source: construct the HMAC helper, emit and check at 0.

    The caller prints the emitted code. Checking the same string at
    relative count 0 must differ from checking a non-matching candidate,
    or the child exits non-zero. Exception class names are not pinned.
    """
    if not isinstance(pkg, str) or not pkg:
        raise HarnessError(f"hmac_app_source pkg is not a package name: {pkg!r}")
    if not isinstance(secret, str) or not secret:
        raise HarnessError(f"hmac_app_source secret is not text: {secret!r}")
    return (
        f"from {pkg} import HOTP\n"
        f"helper = HOTP({secret!r})\n"
        "code = helper.at(0)\n"
        "print(code)\n"
        "accepted = helper.verify(code, 0)\n"
        "rejected = helper.verify('000000', 0)\n"
        "if accepted == rejected:\n"
        "    raise SystemExit('check did not accept the emitted code')\n"
    )


def restore_base32_padding(secret: str) -> str:
    """Restore the missing base32 padding so length is a multiple of 8.

    Padding characters are an input spelling, not an output golden.
    A secret whose length is already a multiple of 8 is refused — this
    slice only uses the published unpadded N3OV secret.
    """
    if not isinstance(secret, str) or not secret:
        raise HarnessError(f"restore_base32_padding secret is not text: {secret!r}")
    remainder = len(secret) % 8
    if remainder == 0:
        raise HarnessError(
            "restore_base32_padding requires a secret whose length is "
            f"not a multiple of 8; got length={len(secret)}"
        )
    padded = secret + ("=" * (8 - remainder))
    if len(padded) % 8 != 0:
        raise HarnessError(
            "restore_base32_padding did not reach a multiple of 8: "
            f"length={len(padded)}"
        )
    print(
        f"restored base32 padding length {len(secret)} -> {len(padded)}",
        flush=True,
    )
    return padded
