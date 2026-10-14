# feature: F01
"""Observation helpers for random shared-secret generation (FP-01).

Helpers classify outcomes of the two public secret helpers. They never
return ``None`` to mean "the observation could not be classified".
Alphabets are the sets the PRD states, not a copy of product source.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Collection, Iterable
from typing import Any

from _harness import CallResult, HarnessError, call, require_exception, require_text

# every character is one of A–Z or 2–7.
BASE32_ALPHABET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")
# every character is one of A–F or 0–9.
HEX_ALPHABET = frozenset("ABCDEF0123456789")

# N>=5 draws, then not all identical. Not pairwise distinct.
NONCONSTANT_DRAWS = 5

# Consecutive integers in the unpublished-length band. After removing
# forbidden values the band must still hold at least this many eligibles.
_UNPUBLISHED_BAND = 32
_UNPUBLISHED_MIN_ELIGIBLE = 16
# Drop the first this-many eligibles so the picker is never "the first N
# integers at or above the minimum that are not forbidden".
_UNPUBLISHED_SKIP_PREFIX = 4


def require_secret(result: CallResult, length: int, alphabet: Collection[str]) -> str:
    """Return a successful secret of exactly *length* from *alphabet*.

    The call must have returned text. Wrong type, wrong length, or a
    character outside *alphabet* fails the observation — never a sentinel.
    """
    text = require_text(result)
    actual_len = len(text)
    if actual_len != length:
        raise AssertionError(
            "secret is not the requested length: "
            f"type={type(text).__name__} length={actual_len} expected={length} "
            f"value={text!r}"
        )
    illegal = sorted({ch for ch in text if ch not in alphabet})
    if illegal:
        raise AssertionError(
            "secret contains characters outside the named alphabet: "
            f"illegal={illegal!r} length={actual_len} value={text!r}"
        )
    print(
        f"secret ok length={actual_len} alphabet_size={len(alphabet)}",
        flush=True,
    )
    return text


def require_secret_refused(result: CallResult) -> BaseException:
    """Require a failure with no secret string handed back.

    The caller must observe a failure (any exception; class and message
    are not pinned) and ``value`` must not be a secret string. Returning
    ``None`` without failing is not a failure.
    """
    exc = require_exception(result)
    assert not isinstance(result.value, str), (
        "failure still handed back a secret string: "
        f"{result.value!r}"
    )
    print(
        f"secret refused; no secret string returned "
        f"(carrier={type(exc).__name__})",
        flush=True,
    )
    return exc


def collect_secrets(
    helper: Callable[..., Any],
    n: int,
    *,
    expected_length: int,
    alphabet: Collection[str],
    **kwargs: Any,
) -> list[str]:
    """Call *helper* *n* times through ``call`` and collect valid secrets.

    Each draw must succeed and pass :func:`require_secret`. A failed
    mid-loop call raises — this never returns a short list. *kwargs* are
    forwarded to the helper (the length override, when present).
    """
    if n < 2:
        raise HarnessError(f"collect_secrets requires n >= 2; got {n}")
    collected: list[str] = []
    for index in range(n):
        result = call(helper, **kwargs)
        secret = require_secret(result, expected_length, alphabet)
        collected.append(secret)
        print(
            f"draw {index + 1}/{n} length={len(secret)}",
            flush=True,
        )
    if len(collected) != n:
        raise HarnessError(
            f"collect_secrets expected {n} secrets; got {len(collected)}"
        )
    return collected


def require_not_constant(secrets_drawn: Iterable[str]) -> None:
    """Require that the draws are not a single canned string.

    Needs at least two successful secrets. Does not require adjacent
    draws to differ, pairwise uniqueness, or an entropy bound.
    """
    drawn = list(secrets_drawn)
    if len(drawn) < 2:
        raise HarnessError(
            f"require_not_constant needs at least 2 secrets; got {len(drawn)}"
        )
    distinct = set(drawn)
    print(
        f"nonconstant draws={len(drawn)} distinct={len(distinct)}",
        flush=True,
    )
    assert len(distinct) >= 2, (
        "helper returned one canned secret on every draw: "
        f"n={len(drawn)} value={drawn[0]!r}"
    )


def unpublished_lengths(
    minimum: int,
    forbidden: Collection[int],
    count: int = 2,
) -> tuple[int, ...]:
    """Pick *count* unpublished widths at or above *minimum*.

    Builds a band of consecutive integers starting at *minimum* with at
    least 16 eligible values (not in *forbidden*). Selection is a random
    sample from that band after dropping a prefix of eligible integers,
    so the result is never "the first N integers at or above the
    minimum that are not forbidden". 39 and 41 are not preferred.
    Raises if a valid pair cannot be formed — never falls back to a
    named width.
    """
    if count < 1:
        raise HarnessError(f"unpublished_lengths count must be >= 1; got {count}")
    if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 1:
        raise HarnessError(f"unpublished_lengths minimum is not a usable int: {minimum!r}")

    forbidden_set = set(forbidden)
    band = list(range(minimum, minimum + _UNPUBLISHED_BAND))
    eligible = [width for width in band if width not in forbidden_set]
    if len(eligible) < _UNPUBLISHED_MIN_ELIGIBLE:
        raise HarnessError(
            "unpublished length band has "
            f"{len(eligible)} eligible integers; need at least "
            f"{_UNPUBLISHED_MIN_ELIGIBLE} "
            f"(minimum={minimum}, forbidden={sorted(forbidden_set)!r})"
        )

    skip = _UNPUBLISHED_SKIP_PREFIX
    if len(eligible) - skip < count:
        raise HarnessError(
            "unpublished length pool after skipping the prefix is too small: "
            f"eligible={len(eligible)} skip={skip} count={count}"
        )
    pool = eligible[skip:]
    chosen = tuple(secrets.SystemRandom().sample(pool, count))
    if len(set(chosen)) != count:
        raise HarnessError(f"unpublished lengths are not distinct: {chosen!r}")
    for width in chosen:
        if width < minimum or width in forbidden_set:
            raise HarnessError(
                "unpublished_lengths produced a named or below-minimum width: "
                f"{width!r} (minimum={minimum}, forbidden={sorted(forbidden_set)!r})"
            )
    print(
        f"unpublished_lengths minimum={minimum} chosen={chosen!r}",
        flush=True,
    )
    return chosen
