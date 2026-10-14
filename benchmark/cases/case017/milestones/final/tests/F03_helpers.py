# feature: F03
"""Observation helpers for cardinality, extrema, and ascending enumeration.

JSON fields emitted by a probe are test encoding, not a product output
contract. A compile or run that cannot be classified raises HarnessError
— never a sentinel that could pass for “empty”, “cardinality 0”,
“exhausted”, or “array length 0”.
"""

from __future__ import annotations

import secrets
from typing import Any, Mapping, Sequence

from F01_helpers import compile_product_source, wrap_probe_body
from F02_helpers import (
    F02_NAMED_U64_SAMPLES,
    require_bool_field,
    require_int_field,
    unpublished_u64_f02,
)
from _helpers import DEFAULT_TIMEOUT, HarnessError

# Values this feature's PRD names as inputs, plus F01/F02 public samples.
# Unpublished draws must not land here.
F03_NAMED_U64_SAMPLES = frozenset(
    {
        0,
        1,
        2,
        5,
        42,
        99,
        1 << 16,
        2 << 16,
        1 << 32,
        4999,
        5000,
        1 << 40,
    }
)

# Injected above wrap_probe_body's run(). Test encoding, not a product API.
_F03_ZIG_EXTRAS = r"""
fn pullAbsent(it: *klyvmap.Iterator) bool {
    return it.next() == null;
}

fn yieldedEquals(it: *klyvmap.Iterator, want: u64) bool {
    const got = it.next() orelse return false;
    return got == want;
}

fn extremaAbsent(bm: *const klyvmap.Bitmap) bool {
    return bm.minimum() == null and bm.maximum() == null;
}

fn extremaEqual(bm: *const klyvmap.Bitmap, want_min: u64, want_max: u64) bool {
    const mn = bm.minimum() orelse return false;
    const mx = bm.maximum() orelse return false;
    return mn == want_min and mx == want_max;
}

fn drainEquals(bm: *const klyvmap.Bitmap, want: []const u64) bool {
    var it = bm.iterator();
    for (want) |w| {
        const got = it.next() orelse return false;
        if (got != w) return false;
    }
    return it.next() == null;
}

fn drainRunFrom(bm: *const klyvmap.Bitmap, start: u64, count: u64) bool {
    var it = bm.iterator();
    var i: u64 = 0;
    while (i < count) : (i += 1) {
        const got = it.next() orelse return false;
        if (got != start + i) return false;
    }
    return it.next() == null;
}

fn drainRunSkipping(bm: *const klyvmap.Bitmap, start: u64, last: u64, skip: u64) bool {
    var it = bm.iterator();
    var i: u64 = start;
    while (i <= last) : (i += 1) {
        if (i == skip) continue;
        const got = it.next() orelse return false;
        if (got != i) return false;
    }
    return it.next() == null;
}

fn neighboursAdjacentAfterHole(bm: *const klyvmap.Bitmap, hole: u64) bool {
    var it = bm.iterator();
    var prev: ?u64 = null;
    var adjacent = false;
    while (it.next()) |v| {
        if (v == hole) return false;
        if (prev) |p| {
            if (p == hole - 1 and v == hole + 1) adjacent = true;
        }
        prev = v;
    }
    return adjacent;
}

fn arrayEqualsDrain(bm: *const klyvmap.Bitmap, arr: []const u64) bool {
    if (arr.len != @as(usize, @intCast(bm.getCardinality()))) return false;
    var it = bm.iterator();
    for (arr) |a| {
        const got = it.next() orelse return false;
        if (got != a) return false;
    }
    return it.next() == null;
}

fn suffixUntouched(buf: []const u64, start: usize, sentinel: u64) bool {
    var i: usize = start;
    while (i < buf.len) : (i += 1) {
        if (buf[i] != sentinel) return false;
    }
    return true;
}

fn fillSentinel(buf: []u64, sentinel: u64) void {
    for (buf) |*slot| slot.* = sentinel;
}
"""


def wrap_enumeration_probe(body: str) -> str:
    """Wrap a query / iterator / array probe, with drain helpers in scope.

    Helpers are test encoding. They do not invent a product API.
    """
    src = wrap_probe_body(body)
    marker = "\nfn run("
    idx = src.find(marker)
    if idx < 0:
        raise HarnessError("wrap_probe_body produced no run function")
    return src[:idx] + "\n" + _F03_ZIG_EXTRAS + src[idx:]


def compile_probe_or_raise(
    ws,
    source: str,
    *,
    relpath: str,
    output: str,
    timeout: float | None = DEFAULT_TIMEOUT,
):
    """Compile *source* under *ws*. Non-zero compile is a harness failure."""
    compiled = compile_product_source(
        ws, source, relpath=relpath, output=output, timeout=timeout
    )
    if compiled.returncode != 0:
        raise HarnessError(
            f"{output} failed to compile\n{compiled.stderr_text}"
        )
    return compiled


def _blocked_u64(extra: set[int] | frozenset[int] | None) -> set[int]:
    blocked = set(F02_NAMED_U64_SAMPLES)
    blocked.update(F03_NAMED_U64_SAMPLES)
    if extra is not None:
        blocked.update(extra)
    return blocked


def unpublished_u64_f03(
    forbidden: set[int] | frozenset[int] | None = None,
    *,
    above: int | None = None,
) -> int:
    """Return a 64-bit value F01 / F02 / F03 public materials do not name.

    Uses the F02 draw (open range, dropped prefix). Extra forbidden values
    include this feature's named samples. A collision raises.
    """
    return unpublished_u64_f02(_blocked_u64(forbidden), above=above)


def unpublished_extrema_pair() -> tuple[int, int]:
    """Two unpublished values A < B, both greater than 0."""
    first = unpublished_u64_f03()
    second = unpublished_u64_f03(forbidden={first})
    if first == second:
        raise HarnessError("extrema pair draw produced equal values")
    lo, hi = (first, second) if first < second else (second, first)
    if lo == 0:
        raise HarnessError("extrema pair landed on 0")
    return lo, hi


def unpublished_three_prefix_values() -> tuple[int, int, int]:
    """Three unpublished values on distinct high-48-bit prefixes, sorted."""
    values: list[int] = []
    prefixes: set[int] = set()
    extra: set[int] = set()
    for _ in range(64):
        value = unpublished_u64_f03(forbidden=extra)
        prefix = value >> 16
        extra.add(value)
        if prefix in prefixes:
            continue
        prefixes.add(prefix)
        values.append(value)
        if len(values) == 3:
            values.sort()
            return values[0], values[1], values[2]
    raise HarnessError(
        "could not draw three unpublished values on distinct high-48 prefixes"
    )


def unpublished_scattered_pair() -> tuple[int, int]:
    """Two unpublished values on distinct prefixes, both at or above 2^32."""
    first = unpublished_u64_f03()
    extra = {first}
    for _ in range(32):
        second = unpublished_u64_f03(forbidden=extra)
        extra.add(second)
        if (second >> 16) != (first >> 16) and second >= (1 << 32):
            return first, second
    raise HarnessError(
        "could not draw two unpublished values on distinct high prefixes"
    )


def unpublished_low_high_runs() -> tuple[int, int, int, int]:
    """Consecutive low and high runs on unpublished prefixes.

    Returns ``(low_start, low_len, high_start, high_len)``. Low is not
    0..99. After emptying low, the remaining minimum is not 2^16. Each
    run stays inside its high-48 prefix. High length is at least 2.
    """
    low_prefix = 4 + secrets.randbelow(8)
    high_prefix = low_prefix + 2 + secrets.randbelow(8)
    if low_prefix in {0, 1} or high_prefix in {0, 1}:
        raise HarnessError("low/high run prefixes collided with named prefixes")
    low_off = secrets.randbelow(32)
    high_off = secrets.randbelow(32)
    low_len = 2 + secrets.randbelow(6)
    high_len = 2 + secrets.randbelow(6)
    if low_off + low_len > 0xFFFF:
        low_len = 2
    if high_off + high_len > 0xFFFF:
        high_len = 2
    low_start = (low_prefix << 16) | low_off
    high_start = (high_prefix << 16) | high_off
    if high_start == (1 << 16):
        raise HarnessError("remaining minimum after emptying low is 2^16")
    if low_start <= 99:
        raise HarnessError("low run overlaps the named 0..99 prefix")
    return low_start, low_len, high_start, high_len


def unpublished_prefix_run_length() -> int:
    """Length of a dense run under prefix 2^16: at least 2, not a block size."""
    return 2 + secrets.randbelow(19)


def unpublished_hundreds_length() -> int:
    """A consecutive run length in the hundreds, not the public 5000."""
    return 200 + secrets.randbelow(300)


def independent_sorted_unique_dense_and_scattered(
    dense_len: int, *scatter: int
) -> list[int]:
    """Sorted unique list of 0..dense_len-1 plus the scatter values the test chose.

    This is the FP-03 mixed allocated-array oracle. It is built from the
    inputs the test itself picked, not from set()'s newly-added report
    and not from a product dump.
    """
    if dense_len < 1:
        raise HarnessError(f"dense run length must be positive, got {dense_len}")
    if len(scatter) < 2:
        raise HarnessError("mixed bitmap needs at least two scatter values")
    present = set(range(dense_len))
    present.update(int(value) for value in scatter)
    return sorted(present)


def unused_suffix_slots() -> int:
    """How many unused destination slots to fill with a sentinel."""
    return 3 + secrets.randbelow(6)


def sentinel_absent_from(present: set[int] | frozenset[int] | Sequence[int]) -> int:
    """A 64-bit value that is not in *present*. Raises if a draw is present."""
    blocked = set(present)
    value = unpublished_u64_f03(forbidden=blocked)
    if value in blocked:
        raise HarnessError(f"sentinel draw landed in the present set: {value}")
    return value


def require_strictly_ascending_once(
    values: Sequence[int], *, cardinality: int
) -> None:
    """Assert *values* has *cardinality* entries, strictly ascending, unique.

    Expected sequences come from values the test itself set and has not
    removed, not from a reimplementation of the product.
    """
    if len(values) != cardinality:
        raise AssertionError(
            f"sequence length {len(values)} != cardinality {cardinality}"
        )
    if len(set(values)) != len(values):
        raise AssertionError("sequence contains duplicates")
    for i in range(1, len(values)):
        if values[i] <= values[i - 1]:
            raise AssertionError(
                f"sequence is not strictly ascending at index {i}"
            )


def require_allocated_matches_independent(
    report: Mapping[str, Any],
    want: Sequence[int],
    *,
    want_key: str = "want_ok",
    len_key: str = "len",
    card_key: str = "card",
) -> None:
    """Pin allocated-array length and contents to *want*.

    *want* is the independent unique list the test built from the values
    it set. Agreement among an empty dump, an empty iterator, and a
    product-derived empty harvest is not this check.
    """
    if not want:
        raise HarnessError("independent unique list is empty")
    n = len(want)
    assert require_int_field(report, len_key) == n
    assert require_int_field(report, card_key) == n
    require_true(report, want_key)


def require_destination_matches_independent(
    report: Mapping[str, Any],
    want: Sequence[int],
    *,
    want_key: str = "want_ok",
    suffix_key: str = "suffix",
    card_key: str = "card",
) -> None:
    """Pin destination prefix to *want* and unused suffix to sentinel.

    Destination length is *want*'s length — the unique list the test
    built from the values it set — not a product cardinality() report.
    Agreement among an empty write, an empty iterator, and an empty
    allocated array on a sentinel-filled buffer is not this check. The
    unused suffix staying sentinel only counts after that prefix has
    actually been written.
    """
    if not want:
        raise HarnessError("independent unique list is empty")
    n = len(want)
    assert require_int_field(report, card_key) == n
    require_true(report, want_key, suffix_key)


def require_no_integer(report: Mapping[str, Any], key: str) -> None:
    """*key* is JSON null: the probe did not deliver a 64-bit integer."""
    if key not in report:
        raise HarnessError(f"probe JSON missing {key!r}; have {sorted(report)}")
    value = report[key]
    if value is not None:
        raise AssertionError(
            f"{key} delivered {value!r}; absence is not a delivered integer"
        )


def require_true(report: Mapping[str, Any], *keys: str) -> None:
    """Every named JSON bool is true. Missing or non-bool is harness failure."""
    for key in keys:
        assert require_bool_field(report, key) is True, f"{key} is not true"


def require_false(report: Mapping[str, Any], *keys: str) -> None:
    """Every named JSON bool is false. Missing or non-bool is harness failure."""
    for key in keys:
        assert require_bool_field(report, key) is False, f"{key} is not false"


def require_card_empty(
    report: Mapping[str, Any],
    *,
    card: int,
    empty: bool,
    card_key: str = "card",
    empty_key: str = "empty",
) -> None:
    """Read cardinality and emptiness together (L150 biconditional)."""
    assert require_int_field(report, card_key) == card
    assert require_bool_field(report, empty_key) is empty
