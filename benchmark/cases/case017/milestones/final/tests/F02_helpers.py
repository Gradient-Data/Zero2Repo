# feature: F02
"""Observation helpers for set / membership / remove of 64-bit values.

JSON fields emitted by a probe are test encoding, not a product output
contract. A compile or run that cannot be classified raises HarnessError
— never a sentinel that could pass for “not a member” or “cardinality 0”.
"""

from __future__ import annotations

import secrets
from typing import Any, Mapping, Sequence

import F01_helpers as _f01
from _helpers import HarnessError

# Values this feature's PRD names as inputs (FP-02 plus the L7 first-path
# pair and the F01 public samples that must not be reused as “unpublished”).
F02_NAMED_U64_SAMPLES = frozenset(
    {
        0,
        1,
        42,
        65535,
        1 << 16,
        1 << 32,
        (1 << 32) + 5,
        (1 << 32) + 6,
        1 << 40,
        1 << 47,
        (1 << 48) + 7,
        (1 << 48) + (1 << 32),
        1 << 50,
        2999,
        (1 << 64) - 1,
        (1 << 64) - 2,
    }
)

U64_MAX = (1 << 64) - 1

# Dense / multi-prefix probes compile and run more work than a two-value set.
LARGE_PROBE_TIMEOUT = 180.0


def nine_boundary_values() -> tuple[int, ...]:
    """The nine 64-bit values FP-02 names, in PRD writing order.

    Tests shuffle this tuple at runtime; do not treat this order as an
    insertion contract.
    """
    return (
        0,
        65535,
        1 << 16,
        (1 << 32) + 5,
        (1 << 32) + 65535,
        (1 << 48) + 7,
        (1 << 48) + (1 << 32),
        U64_MAX,
        U64_MAX - 1,
    )


def _blocked_u64(extra: set[int] | frozenset[int] | None) -> set[int]:
    blocked = set(_f01.PUBLIC_U64_SAMPLES)
    blocked.update(F02_NAMED_U64_SAMPLES)
    if extra is not None:
        blocked.update(extra)
    return blocked


def _blocked_high_48(extra: set[int] | frozenset[int] | None) -> set[int]:
    blocked = {value >> 16 for value in _blocked_u64(extra)}
    blocked.add(0)
    return blocked


def unpublished_u64_f02(
    forbidden: set[int] | frozenset[int] | None = None,
    *,
    above: int | None = None,
) -> int:
    """Return a 64-bit value the public materials of F01 and F02 do not name.

    Draws from an open range so a 32-bit store cannot hold the result.
    When *above* is set, the draw is strictly greater than that bound
    (used for the L7 “value above 2^40” path). Drops a random prefix of
    the range — never “the next integer after the forbidden set”. Raises
    if a draw lands in *forbidden* or the named-sample set.
    """
    blocked = _blocked_u64(forbidden)
    low = (above + 1) if above is not None else ((1 << 32) + 1)
    high = U64_MAX
    if low >= high:
        raise HarnessError("unpublished_u64_f02 range is empty")
    span = high - low
    prefix = 1 + secrets.randbelow(max(span // 4, 1))
    start = low + prefix
    if start >= high:
        raise HarnessError("unpublished_u64_f02 start exhausted the range")
    width = high - start
    value = start + secrets.randbelow(width)
    if value in blocked:
        raise HarnessError(
            f"unpublished draw collided with a forbidden value: {value}"
        )
    return value


def unpublished_pair_sharing_high_48(
    forbidden: set[int] | frozenset[int] | None = None,
) -> tuple[int, int]:
    """Two unpublished values that share a non-public high-48-bit prefix.

    The prefix is not 0 and is not a high-48 prefix used by the named
    F02 samples. Raises if thirty-two draws cannot produce two distinct
    non-forbidden values (never returns a sentinel pair).
    """
    blocked = _blocked_u64(forbidden)
    blocked_prefixes = _blocked_high_48(forbidden)
    for _ in range(32):
        prefix = 1 + secrets.randbelow((1 << 48) - 2)
        if prefix in blocked_prefixes:
            continue
        lo1 = secrets.randbelow(1 << 16)
        lo2 = secrets.randbelow(1 << 16)
        if lo1 == lo2:
            continue
        first = (prefix << 16) | lo1
        second = (prefix << 16) | lo2
        if first in blocked or second in blocked:
            continue
        return first, second
    raise HarnessError(
        "could not draw an unpublished pair sharing a high-48-bit prefix"
    )


def unpublished_thousands_length() -> int:
    """A run length that is thousands long and is not the public 5000 example."""
    return 1000 + secrets.randbelow(1500)


def unpublished_dense_interior() -> int:
    """A value strictly inside 0 .. 4999 (not an endpoint)."""
    return 1 + secrets.randbelow(4998)


def shuffle_not_sorted(values: Sequence[int]) -> list[int]:
    """Return a permutation of *values* that is not sorted ascending.

    The product may store in any order; this only constrains the *test's*
    insertion sequence so it is not the sorted (and PRD-written) order.
    """
    out = list(values)
    if len(out) < 2:
        raise HarnessError("cannot shuffle a sequence shorter than 2")
    if len(set(out)) != len(out):
        raise HarnessError("shuffle_not_sorted requires distinct values")
    for i in range(len(out) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        out[i], out[j] = out[j], out[i]
    if out == sorted(out):
        out[0], out[-1] = out[-1], out[0]
    if out == sorted(out):
        raise HarnessError("shuffle produced sorted order")
    return out


def zig_u64_list(values: Sequence[int]) -> str:
    """Comma-separated decimal u64 literals for embedding in a probe."""
    if not values:
        raise HarnessError("zig_u64_list of an empty sequence")
    chunks: list[str] = []
    row: list[str] = []
    for value in values:
        row.append(str(int(value)))
        if len(row) == 8:
            chunks.append(", ".join(row))
            row = []
    if row:
        chunks.append(", ".join(row))
    return ",\n        ".join(chunks)


def six_hundred_prefix_inserts() -> tuple[list[int], int, tuple[int, int, int]]:
    """600 unpublished high-48 prefixes × 3 lows, shuffled for insertion.

    Returns ``(shuffled_values, absent_same_prefix, present_on_that_prefix)``.
    *absent_same_prefix* shares a used prefix and a low 16-bit that is not
    one of that prefix's three inserted lows. Prefix origin is drawn at
    runtime so the prefixes are not always 0 .. 599.
    """
    blocked_prefixes = _blocked_high_48(None)
    start = 1 + secrets.randbelow(1 << 32)
    prefixes: list[int] = []
    cursor = start
    while len(prefixes) < 600:
        prefix = cursor % (1 << 48)
        if prefix not in blocked_prefixes and prefix != 0:
            prefixes.append(prefix)
        cursor += 1
        if cursor - start > (1 << 48):
            raise HarnessError("could not collect 600 unpublished high-48 prefixes")
    lows: list[int] = []
    while len(lows) < 3:
        low = secrets.randbelow(1 << 16)
        if low not in lows:
            lows.append(low)
    values = [(prefix << 16) | low for prefix in prefixes for low in lows]
    if len(set(values)) != 1800:
        raise HarnessError("600×3 construction produced non-distinct values")
    shuffled = shuffle_not_sorted(values)
    which = secrets.randbelow(600)
    prefix = prefixes[which]
    absent_low = secrets.randbelow(1 << 16)
    if absent_low in lows:
        absent_low = None
        for candidate in range(1 << 16):
            if candidate not in lows:
                absent_low = candidate
                break
        if absent_low is None:
            raise HarnessError("no unused low 16-bit for same-prefix absence")
    absent = (prefix << 16) | absent_low
    present = tuple((prefix << 16) | low for low in lows)
    return shuffled, absent, present


def require_bool_field(report: Mapping[str, Any], key: str) -> bool:
    """Read a JSON bool the probe emitted. Missing or non-bool is harness failure."""
    return _f01._require_bool(report, key)


def require_int_field(report: Mapping[str, Any], key: str) -> int:
    """Read a JSON int the probe emitted. Missing or non-int is harness failure."""
    return _f01._require_int(report, key)


# ---------------------------------------------------------------------------
# One-block population sweep
# ---------------------------------------------------------------------------
#
# A single high-48 prefix is filled one low 16-bit value at a time, in a drawn
# visiting order, until it holds every one of its 65536 values, and emptied the
# same way. Observations are taken at every population 2^k - 1, 2^k and
# 2^k + 1 (k = 1 .. 16). The PRD does not say how a prefix is packed; it says
# every value set is present and counts once at any population, so any change
# of representation the product makes while a prefix grows or shrinks has to be
# invisible. The oracle is arithmetic in the probe: value i of the visiting
# order is (prefix << 16) | (i * mul mod 2^16) with mul odd, and inv undoes it,
# so "which values are present" is an index range, never product output.

BLOCK_VALUES = 1 << 16


def block_checkpoints() -> list[int]:
    """Populations 2^k - 1, 2^k and 2^k + 1 for k = 1 .. 16, capped at a full block."""
    points = {
        c
        for k in range(1, 17)
        for c in ((1 << k) - 1, 1 << k, (1 << k) + 1)
        if 1 <= c <= BLOCK_VALUES
    }
    return sorted(points)


def block_sweep() -> dict[str, int]:
    """Draw a block and a visiting order over its 65536 low values.

    ``prefix`` is a high-48 prefix that is not 0 and is neither a named-sample
    prefix nor a neighbour of one. ``mul`` is odd, so ``i -> i * mul mod 2^16``
    visits every low value once; ``inv`` is its inverse. ``below`` and
    ``above`` are the integers just outside the block, on the two
    neighbouring prefixes.
    """
    blocked = _blocked_high_48(None)
    for _ in range(64):
        prefix = 2 + secrets.randbelow((1 << 48) - 4)
        if {prefix - 1, prefix, prefix + 1} & blocked:
            continue
        mul = 3 + 2 * secrets.randbelow((BLOCK_VALUES - 4) // 2)
        inv = pow(mul, -1, BLOCK_VALUES)
        if (mul * inv) % BLOCK_VALUES != 1:
            raise HarnessError("visiting-order multiplier has no inverse")
        return {
            "prefix": prefix,
            "mul": mul,
            "inv": inv,
            "below": (prefix << 16) - 1,
            "above": (prefix + 1) << 16,
        }
    raise HarnessError("could not draw an unpublished block prefix")


_BLOCK_SWEEP_ZIG = r"""
    const Block = struct {
        prefix: u64,
        mul: u64,
        inv: u64,
        below: u64,
        above: u64,

        /// Value i of the visiting order (0 <= i < 65536).
        fn val(s: @This(), i: u64) u64 {
            return (s.prefix << 16) | ((i *% s.mul) & 0xFFFF);
        }

        /// Position of x in the visiting order, or null when x is off the block.
        fn index(s: @This(), x: u64) ?u64 {
            if (x >> 16 != s.prefix) return null;
            return ((x & 0xFFFF) *% s.inv) & 0xFFFF;
        }

        fn setRange(s: @This(), bm: *klyvmap.Bitmap, lo: u64, hi: u64) !bool {
            var fresh = true;
            var i = lo;
            while (i < hi) : (i += 1) {
                if (!try bm.set(s.val(i))) fresh = false;
            }
            return fresh;
        }

        fn setRangeDown(s: @This(), bm: *klyvmap.Bitmap, lo: u64, hi: u64) !bool {
            var fresh = true;
            var i = hi;
            while (i > lo) {
                i -= 1;
                if (!try bm.set(s.val(i))) fresh = false;
            }
            return fresh;
        }

        fn setEdges(s: @This(), bm: *klyvmap.Bitmap) !bool {
            const a = try bm.set(s.above);
            const b = try bm.set(s.below);
            return a and b;
        }

        /// The smallest and largest value of positions lo .. hi-1.
        fn lowest(s: @This(), lo: u64, hi: u64) u64 {
            var best: u64 = std.math.maxInt(u64);
            var i = lo;
            while (i < hi) : (i += 1) best = @min(best, s.val(i));
            return best;
        }

        fn highest(s: @This(), lo: u64, hi: u64) u64 {
            var best: u64 = 0;
            var i = lo;
            while (i < hi) : (i += 1) best = @max(best, s.val(i));
            return best;
        }

        /// Membership of every one of the 65536 block values is exactly
        /// "position in lo .. hi-1"; the two edge values are present exactly
        /// when `edges`; cardinality counts those and nothing else.
        fn members(s: @This(), bm: *const klyvmap.Bitmap, lo: u64, hi: u64, edges: bool) bool {
            const extra: u64 = if (edges) 2 else 0;
            if (bm.getCardinality() != hi - lo + extra) return false;
            if (bm.contains(s.below) != edges or bm.contains(s.above) != edges) return false;
            var i: u64 = 0;
            while (i < 65536) : (i += 1) {
                if (bm.contains(s.val(i)) != (i >= lo and i < hi)) return false;
            }
            return true;
        }

        /// The ascending walk yields exactly positions lo .. hi-1 (framed by
        /// the edge values when `edges`), then exhaustion twice.
        fn walk(s: @This(), bm: *const klyvmap.Bitmap, lo: u64, hi: u64, edges: bool) bool {
            var it = bm.iterator();
            var prev: ?u64 = null;
            if (edges) {
                const first = it.next() orelse return false;
                if (first != s.below) return false;
                prev = first;
            }
            var n: u64 = 0;
            while (n < hi - lo) : (n += 1) {
                const x = it.next() orelse return false;
                if (prev) |p| {
                    if (x <= p) return false;
                }
                const i = s.index(x) orelse return false;
                if (i < lo or i >= hi) return false;
                prev = x;
            }
            if (edges) {
                const last = it.next() orelse return false;
                if (last != s.above) return false;
            }
            if (it.next() != null) return false;
            return it.next() == null;
        }

        fn isCheckpoint(c: u64, points: []const u64) bool {
            for (points) |p| {
                if (p == c) return true;
            }
            return false;
        }
    };
    const block: Block = .{
        .prefix = __BLOCK_PREFIX__,
        .mul = __BLOCK_MUL__,
        .inv = __BLOCK_INV__,
        .below = __BLOCK_BELOW__,
        .above = __BLOCK_ABOVE__,
    };
    const checkpoints = [_]u64{ __BLOCK_CHECKS__ };
"""


def block_sweep_zig(sweep: Mapping[str, int] | None = None) -> str:
    """Zig statements declaring ``block`` (a drawn :func:`block_sweep`) and ``checkpoints``.

    Paste at the start of a probe ``run`` body. ``Block.members`` observes
    through ``contains`` and ``getCardinality`` only; ``Block.walk`` through
    ``iterator`` only.
    """
    drawn = dict(sweep) if sweep is not None else block_sweep()
    return _f01.fill_u64(
        _BLOCK_SWEEP_ZIG,
        block_prefix=drawn["prefix"],
        block_mul=drawn["mul"],
        block_inv=drawn["inv"],
        block_below=drawn["below"],
        block_above=drawn["above"],
        block_checks=zig_u64_list(block_checkpoints()),
    )


def run_block_sweep(
    body: str,
    sweep: Mapping[str, int] | None = None,
    *,
    timeout: float | None = LARGE_PROBE_TIMEOUT,
) -> dict[str, Any]:
    """Run a probe whose ``run`` body starts with :func:`block_sweep_zig`."""
    source = _f01.wrap_probe_body(block_sweep_zig(sweep) + body)
    return _f01.run_bitmap_probe(source, timeout=timeout)


def require_sweep_true(report: Mapping[str, Any], *keys: str) -> None:
    for key in keys:
        if require_bool_field(report, key) is not True:
            raise AssertionError(f"{key} is not true")


def require_sweep_seen(report: Mapping[str, Any], key: str, expected: int) -> None:
    """The probe reached every checkpoint it was meant to observe."""
    seen = require_int_field(report, key)
    if seen != expected:
        raise HarnessError(f"{key}={seen}: the sweep observed {seen} of {expected} checkpoints")


def shrink_checkpoints() -> list[int]:
    """Populations observed while a full block is emptied (0 and every checkpoint below full)."""
    return sorted({0} | {c for c in block_checkpoints() if c < BLOCK_VALUES})
