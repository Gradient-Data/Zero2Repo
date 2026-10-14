# feature: F05
"""YAML 1.2 exponent-only float text for default-dump quoting.

Integer mantissa, then ``e``, then decimal digits. No decimal point
and no exponent sign. Not the suite-named ``12e03``. Draw failure raises.

Pad-inside-brackets off-state: no inner space after ``[`` or before ``]``.
"""

from __future__ import annotations

import uuid

from _harness import HarnessError
from _helpers import flow_square_inner_space

_SUITE_NAMED = "12e03"


def exponent_only_float_token() -> str:
    """Integer-mantissa unsigned-exponent text. Not ``12e03``.

    Form is digits, then ``e``, then digits. Exponent width is not
    pinned. Raises if 64 draws cannot produce a token that is not the
    suite-named constant and not dotted or signed.
    """
    for _ in range(64):
        bits = uuid.uuid4().int
        mantissa_width = 1 + (bits % 2)
        mantissa = 1 + ((bits >> 2) % (10 ** mantissa_width - 1))
        exp_bits = uuid.uuid4().int
        # The suite-named constant is 12e03. Keep the magnitude a finite Core float
        # (overflow such as 1e999 stays a string, so it would not need quotes).
        exponent = 1 + (exp_bits % 20)
        exp_width = 1 + ((exp_bits >> 8) % 3)
        if exponent >= 10 ** exp_width:
            exp_width = len(str(exponent))
        text = f"{mantissa}e{exponent:0{exp_width}d}"
        if text == _SUITE_NAMED:
            continue
        if "." in text or "+" in text or "-" in text:
            continue
        if text.count("e") != 1:
            continue
        body, exp_text = text.split("e", 1)
        if not body.isdigit() or not exp_text.isdigit():
            continue
        if not body or not exp_text:
            continue
        return text
    raise HarnessError(
        "could not draw an exponent-only float token distinct from 12e03"
    )


def require_no_flow_square_inner_space(text: str) -> None:
    """Assert a flow dump has no inner space after ``[`` or before ``]``.

    L211's pad-inside-brackets switch is off. ``flow_square_inner_space``
    raises when square brackets are missing, so a dump that is not a
    flow sequence is not treated as unpadded.
    """
    if flow_square_inner_space(text):
        assert False, (
            "flow dump with pad-inside-brackets off must have no inner "
            f"space after '[' or before ']'; got {text!r}"
        )
