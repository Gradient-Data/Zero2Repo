# feature: F01
"""FP-01: random shared-secret generation.

Assertions follow the Full PRD FP-01. Failure message
text, exception class names, bit counts, and entropy statistics are not
pinned. A missing-package start failure is not an F01 duty.
"""

from __future__ import annotations

from otpkit import random_base32, random_hex

from _harness import call, product_package_name, run_python
from F01_helpers import (
    BASE32_ALPHABET,
    HEX_ALPHABET,
    NONCONSTANT_DRAWS,
    collect_secrets,
    require_not_constant,
    require_secret,
    require_secret_refused,
    unpublished_lengths,
)


# ---------------------------------------------------------------------------
# A. Default base32 secret
# ---------------------------------------------------------------------------


def test_default_base32_secret_is_length_32_from_named_alphabet():
    result = call(random_base32)
    secret = require_secret(result, 32, BASE32_ALPHABET)
    print(
        f"default base32 length={len(secret)} "
        f"forbidden_digits={sorted(set(secret) & set('0189'))!r}",
        flush=True,
    )
    assert len(secret) == 32
    assert set(secret) <= BASE32_ALPHABET


# ---------------------------------------------------------------------------
# B. Overridden base32 length 34
# ---------------------------------------------------------------------------


def test_base32_length_34_is_exact_and_same_alphabet():
    default_result = call(random_base32)
    default_secret = require_secret(default_result, 32, BASE32_ALPHABET)
    print(f"baseline default base32 length={len(default_secret)}", flush=True)
    assert len(default_secret) != 34

    override_result = call(random_base32, length=34)
    override_secret = require_secret(override_result, 34, BASE32_ALPHABET)
    print(f"override base32 length={len(override_secret)}", flush=True)
    assert len(override_secret) == 34
    assert set(override_secret) <= BASE32_ALPHABET


# ---------------------------------------------------------------------------
# C. Default hex secret
# ---------------------------------------------------------------------------


def test_default_hex_secret_is_length_40_from_named_alphabet():
    result = call(random_hex)
    secret = require_secret(result, 40, HEX_ALPHABET)
    outside_letters = sorted(
        ch for ch in secret if ch.isalpha() and ch not in HEX_ALPHABET
    )
    print(
        f"default hex length={len(secret)} outside_letters={outside_letters!r}",
        flush=True,
    )
    assert len(secret) == 40
    assert set(secret) <= HEX_ALPHABET


# ---------------------------------------------------------------------------
# D. Overridden hex length 42
# ---------------------------------------------------------------------------


def test_hex_length_42_is_exact_and_same_alphabet():
    default_result = call(random_hex)
    default_secret = require_secret(default_result, 40, HEX_ALPHABET)
    print(f"baseline default hex length={len(default_secret)}", flush=True)
    assert len(default_secret) != 42

    override_result = call(random_hex, length=42)
    override_secret = require_secret(override_result, 42, HEX_ALPHABET)
    print(f"override hex length={len(override_secret)}", flush=True)
    assert len(override_secret) == 42
    assert set(override_secret) <= HEX_ALPHABET


# ---------------------------------------------------------------------------
# E. Each generation is a newly drawn string
# ---------------------------------------------------------------------------


def test_base32_helper_is_not_a_single_canned_secret():
    drawn = collect_secrets(
        random_base32,
        NONCONSTANT_DRAWS,
        expected_length=32,
        alphabet=BASE32_ALPHABET,
    )
    print(
        f"base32 default draws={len(drawn)} distinct={len(set(drawn))}",
        flush=True,
    )
    assert len(set(drawn)) >= 2, (
        "helper returned one canned secret on every draw: "
        f"n={len(drawn)} value={drawn[0]!r}"
    )
    require_not_constant(drawn)


def test_hex_helper_is_not_a_single_canned_secret():
    drawn = collect_secrets(
        random_hex,
        NONCONSTANT_DRAWS,
        expected_length=40,
        alphabet=HEX_ALPHABET,
    )
    print(
        f"hex default draws={len(drawn)} distinct={len(set(drawn))}",
        flush=True,
    )
    assert len(set(drawn)) >= 2, (
        "helper returned one canned secret on every draw: "
        f"n={len(drawn)} value={drawn[0]!r}"
    )
    require_not_constant(drawn)


def test_base32_length_34_is_not_a_single_canned_secret():
    drawn = collect_secrets(
        random_base32,
        NONCONSTANT_DRAWS,
        expected_length=34,
        alphabet=BASE32_ALPHABET,
        length=34,
    )
    print(
        f"base32 length-34 draws={len(drawn)} distinct={len(set(drawn))}",
        flush=True,
    )
    assert len(set(drawn)) >= 2, (
        "helper returned one canned secret on every draw: "
        f"n={len(drawn)} value={drawn[0]!r}"
    )
    require_not_constant(drawn)


def test_hex_length_42_is_not_a_single_canned_secret():
    drawn = collect_secrets(
        random_hex,
        NONCONSTANT_DRAWS,
        expected_length=42,
        alphabet=HEX_ALPHABET,
        length=42,
    )
    print(
        f"hex length-42 draws={len(drawn)} distinct={len(set(drawn))}",
        flush=True,
    )
    assert len(set(drawn)) >= 2, (
        "helper returned one canned secret on every draw: "
        f"n={len(drawn)} value={drawn[0]!r}"
    )
    require_not_constant(drawn)


# ---------------------------------------------------------------------------
# F. Below-minimum lengths fail with no secret
# ---------------------------------------------------------------------------


def test_base32_length_31_fails_with_no_secret():
    baseline = call(random_base32, length=32)
    baseline_secret = require_secret(baseline, 32, BASE32_ALPHABET)
    print(f"base32 length-32 baseline ok length={len(baseline_secret)}", flush=True)

    refused = call(random_base32, length=31)
    print(
        f"base32 length-31 exception={type(refused.exception).__name__ if refused.exception else None} "
        f"value_is_str={isinstance(refused.value, str)}",
        flush=True,
    )
    assert refused.exception is not None, (
        "asking for a base32 secret of length 31 must fail; "
        "the caller observed no failure"
    )
    assert not isinstance(refused.value, str), (
        "failure still handed back a secret string: "
        f"{refused.value!r}"
    )
    require_secret_refused(refused)


def test_hex_length_39_fails_with_no_secret():
    baseline = call(random_hex, length=40)
    baseline_secret = require_secret(baseline, 40, HEX_ALPHABET)
    print(f"hex length-40 baseline ok length={len(baseline_secret)}", flush=True)

    refused = call(random_hex, length=39)
    print(
        f"hex length-39 exception={type(refused.exception).__name__ if refused.exception else None} "
        f"value_is_str={isinstance(refused.value, str)}",
        flush=True,
    )
    assert refused.exception is not None, (
        "asking for a hex secret of length 39 must fail; "
        "the caller observed no failure"
    )
    assert not isinstance(refused.value, str), (
        "failure still handed back a secret string: "
        f"{refused.value!r}"
    )
    require_secret_refused(refused)


# ---------------------------------------------------------------------------
# G. Lengths at or above the minimum
# ---------------------------------------------------------------------------


def test_base32_accepts_minimum_and_runtime_length_at_or_above_32():
    named = call(random_base32, length=32)
    named_secret = require_secret(named, 32, BASE32_ALPHABET)
    print(f"explicit base32 minimum length={len(named_secret)}", flush=True)

    extras = unpublished_lengths(32, frozenset({32, 34}), count=2)
    print(f"unpublished base32 widths={extras!r}", flush=True)
    assert len(extras) == 2
    assert extras[0] != extras[1]
    for width in extras:
        result = call(random_base32, length=width)
        secret = require_secret(result, width, BASE32_ALPHABET)
        print(
            f"unpublished base32 width={width} got_length={len(secret)}",
            flush=True,
        )


def test_hex_accepts_minimum_and_runtime_length_at_or_above_40():
    named = call(random_hex, length=40)
    named_secret = require_secret(named, 40, HEX_ALPHABET)
    print(f"explicit hex minimum length={len(named_secret)}", flush=True)

    extras = unpublished_lengths(40, frozenset({40, 42}), count=2)
    print(f"unpublished hex widths={extras!r}", flush=True)
    assert len(extras) == 2
    assert extras[0] != extras[1]
    for width in extras:
        result = call(random_hex, length=width)
        secret = require_secret(result, width, HEX_ALPHABET)
        print(
            f"unpublished hex width={width} got_length={len(secret)}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# H. Default base32 secret — one unconditional branch
# ---------------------------------------------------------------------------


def test_base32_helper_prints_default_secret_in_child_process_with_package_present():
    """Asking the public base32 helper for a default secret yields a
    32-character string from A–Z and 2–7.

    One branch only. F01 does not promise a hard start failure when the
    package is missing; interpreter ImportError is not an F01 obligation,
    and an absent-package alternative is not accepted.
    """
    pkg = product_package_name()
    code = (
        f"from {pkg} import random_base32\n"
        "secret = random_base32()\n"
        "print(secret)\n"
    )

    observed = run_python(code=code, include_product=True)
    print(
        f"default-secret rc={observed.returncode} "
        f"stdout={observed.stdout_text!r} stderr={observed.stderr_text[:500]!r}",
        flush=True,
    )
    assert observed.returncode == 0, (
        "asking the public base32 helper for a default secret must succeed; "
        f"exit={observed.returncode} stderr={observed.stderr_text!r}"
    )
    printed_lines = [line for line in observed.stdout_text.splitlines() if line]
    assert printed_lines, (
        "default-secret run printed no secret; "
        f"stdout={observed.stdout_text!r}"
    )
    printed = printed_lines[-1]
    assert len(printed) == 32, (
        "asking the base32 helper for a default secret must print a "
        "32-character string; "
        f"got length={len(printed)} value={printed!r}"
    )
    illegal = sorted({ch for ch in printed if ch not in BASE32_ALPHABET})
    assert not illegal, (
        "default base32 secret is outside the named alphabet: "
        f"illegal={illegal!r} value={printed!r}"
    )
