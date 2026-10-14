# feature: F02
"""Runtime token unique to FP-02 YAML 1.1 non-octal leading-zero integers.

Draws a leading-zero digit string that is not the suite-named ``09`` and that
cannot be legal octal (it contains 8 or 9). Generation failure raises.

Also exports independent integer-scaled magnitudes for an unsigned
exponent token (coeff * 10**exp) and a leading-plus plain decimal
(mantissa digits / 10**fraction-length), both without a binary-float
intermediate.
"""

from __future__ import annotations

import uuid

from _harness import HarnessError


def plus_plain_decimal_magnitude(token: str) -> float:
    """Independent place value of a leading-plus plain decimal.

    Parses ``+digits.digits`` (no exponent). The magnitude is the
    integer formed by the mantissa digits divided by ``10**len(frac)``,
    with no whole+frac binary-float split. That is the IEEE/JSON value
    of the drawn token, the same integer-scaled approach as
    ``unsigned_exponent_magnitude``. Does not parse YAML. Raises if the
    token is not a leading plus, digits, a single dot, and digits.
    """
    if not token.startswith("+"):
        raise HarnessError(
            f"plus-plain decimal must start with '+': {token!r}"
        )
    body = token[1:]
    if "e" in body or "E" in body:
        raise HarnessError(
            f"plus-plain decimal must not carry an exponent: {token!r}"
        )
    if body.count(".") != 1:
        raise HarnessError(
            f"plus-plain decimal must be +digits.digits: {token!r}"
        )
    whole, frac = body.split(".", 1)
    if not whole.isdigit() or not frac.isdigit() or not whole or not frac:
        raise HarnessError(
            f"plus-plain decimal is not decimal digits: {token!r}"
        )
    digits = int(whole + frac)
    scale = len(frac)
    return digits / (10 ** scale)


def unsigned_exponent_magnitude(token: str) -> int:
    """Independent ``coeff * 10**exp`` for unsigned-exponent decimal text.

    Parses mantissa digits and an unsigned exponent from *token*. The
    coefficient is the integer formed by the digits with the decimal
    point removed; the result is that integer times ``10**(exp - scale)``
    where *scale* is the number of fractional digits. That is the same
    arithmetic as the suite-named values ``-2 * 10**5`` and ``12 * 10**3``,
    and it is the IEEE/JSON value of tokens the sealed generator draws.
    Does not parse YAML. Raises if the token is not ``digits.digits``
    then ``e`` then digits, or if the scaled magnitude would not be an
    integer.
    """
    if token.count("e") != 1:
        raise HarnessError(
            f"unsigned-exponent token must contain exactly one e: {token!r}"
        )
    body, exp_text = token.split("e", 1)
    if body.count(".") != 1:
        raise HarnessError(
            f"unsigned-exponent mantissa must be digits.digits: {token!r}"
        )
    whole, frac = body.split(".", 1)
    if not whole.isdigit() or not frac.isdigit() or not exp_text.isdigit():
        raise HarnessError(
            f"unsigned-exponent token is not decimal digits: {token!r}"
        )
    if not frac:
        raise HarnessError(
            f"unsigned-exponent token has an empty fraction: {token!r}"
        )
    scale = len(frac)
    exp = int(exp_text)
    digits = int(whole + frac)
    if exp < scale:
        raise HarnessError(
            f"unsigned-exponent {token!r} is not an integer-scaled "
            f"coeff * 10**exp (exp={exp} < scale={scale})"
        )
    return digits * (10 ** (exp - scale))


def non_octal_leading_zero_token() -> str:
    """Leading ``0`` plus digits that include 8 or 9. Not the suite-named ``09``.

    The extra digits are not an octal-only leading-zero token. Raises if
    a qualifying token cannot be drawn.
    """
    for _ in range(64):
        extra = 2 + (uuid.uuid4().int % 3)
        digits = [str(uuid.uuid4().int % 10) for _ in range(extra)]
        if not any(d in "89" for d in digits):
            digits[-1] = "8" if (uuid.uuid4().int % 2) == 0 else "9"
        text = "0" + "".join(digits)
        if text == "09":
            continue
        if not text.startswith("0") or len(text) < 3:
            continue
        if not text.isdigit():
            continue
        if not any(ch in "89" for ch in text[1:]):
            continue
        if all(ch in "01234567" for ch in text):
            continue
        return text
    raise HarnessError(
        "could not draw a non-octal leading-zero token distinct from 09"
    )
