# feature: F07
"""Observation helpers for in-place intersection, union, difference, and cleanup.

JSON fields a probe emits are test encoding, not a product output contract.
A compile or run that cannot be classified raises. It is never folded into
"the left set is empty", "the right operand is unchanged", "the length
stayed", or "the allocator refused so the call counts as success".
"""

from __future__ import annotations

import secrets
from typing import Any, Mapping, Sequence

from F01_helpers import (
    PUBLIC_U64_SAMPLES,
    ZIG_PRELUDE,
    fill_u64,
    run_bitmap_probe,
    wrap_probe_body,
)
from F02_helpers import F02_NAMED_U64_SAMPLES, LARGE_PROBE_TIMEOUT, zig_u64_list
from F03_helpers import F03_NAMED_U64_SAMPLES
from F04_helpers import F04_NAMED_U64
from F05_helpers import F05_NAMED_U64
from F06_helpers import F06_NAMED_U64, unpublished_u64_f06
from _helpers import HarnessError

# Values FP-07 names as inputs. Unpublished draws must not land here.
F07_NAMED_U64 = frozenset({0, 3, 1 << 16, 1 << 60})

_EARLIER_NAMED = (
    frozenset(PUBLIC_U64_SAMPLES)
    | frozenset(F02_NAMED_U64_SAMPLES)
    | frozenset(F03_NAMED_U64_SAMPLES)
    | frozenset(F04_NAMED_U64)
    | frozenset(F05_NAMED_U64)
    | frozenset(F06_NAMED_U64)
    | F07_NAMED_U64
)

# Widths FP-07 names as populations, not as pair sizes.
_NAMED_WIDTHS = frozenset({3000, 500, 800})

U64_MAX = (1 << 64) - 1
PREFIX_SPACE = 1 << 48
LOW_SPACE = 1 << 16


def unpublished_u64_f07(
    forbidden: set[int] | frozenset[int] | None = None,
    *,
    above: int | None = None,
) -> int:
    """A 64-bit value this feature's named samples do not include.

    Also avoids values earlier features published. A draw that lands in
    *forbidden* or on a named sample raises.
    """
    extra = set(F07_NAMED_U64)
    if forbidden is not None:
        extra.update(forbidden)
    value = unpublished_u64_f06(extra, above=above)
    if value in extra or value in _EARLIER_NAMED:
        raise HarnessError(
            f"unpublished_u64_f07 collided with a forbidden value: {value}"
        )
    return value


def u64_body(values: Sequence[int]) -> str:
    """Comma-separated u64 literals. An empty sequence is an empty Zig list."""
    if not values:
        return ""
    return zig_u64_list(values)


def draw_distinct_f07(
    count: int,
    forbidden: set[int] | frozenset[int] | None = None,
    *,
    above: int | None = None,
) -> list[int]:
    """*count* distinct unpublished values. A collision raises."""
    if count <= 0:
        raise HarnessError(f"draw count {count} is empty")
    blocked: set[int] = set(forbidden) if forbidden is not None else set()
    out: list[int] = []
    while len(out) < count:
        value = unpublished_u64_f07(blocked, above=above)
        if value in blocked or value in out:
            raise HarnessError(f"distinct draw collided: {value}")
        blocked.add(value)
        out.append(value)
    return out


def unpublished_pair_size_f07(avoid: set[int] | None = None) -> int:
    """A pair width that is not 3000, 500, or 800, and not in *avoid*."""
    banned = set(_NAMED_WIDTHS)
    if avoid:
        banned |= set(avoid)
    for _ in range(32):
        size = 6 + secrets.randbelow(18)
        if size not in banned:
            return size
    raise HarnessError("could not draw an unpublished pair width")


def _fresh_prefix(blocked: set[int]) -> int:
    for _ in range(128):
        prefix = 1 + secrets.randbelow(PREFIX_SPACE - 2)
        if prefix in blocked or prefix == 0:
            continue
        return prefix
    raise HarnessError("could not draw a high-48 prefix at or above 1")


def _value_on_prefix(prefix: int, forbidden: set[int]) -> int:
    for _ in range(64):
        low = secrets.randbelow(LOW_SPACE)
        value = (prefix << 16) | low
        if value in forbidden or value in _EARLIER_NAMED:
            continue
        return value
    raise HarnessError(f"could not draw a value under prefix {prefix}")


def _one_per_prefix(count: int, forbidden: set[int], *, above: int | None) -> list[int]:
    """*count* values, each under its own high-48 prefix.

    When *above* is set, every value is strictly greater than *above*.
    Prefix 0 is never used, so every value is at least 2^16.
    """
    if count <= 0:
        raise HarnessError("prefix population is empty")
    blocked = {value >> 16 for value in forbidden} | {value >> 16 for value in _EARLIER_NAMED}
    blocked.add(0)
    out: list[int] = []
    guard = 0
    while len(out) < count:
        guard += 1
        if guard > count * 8 + 64:
            raise HarnessError("could not draw one value per prefix")
        prefix = _fresh_prefix(blocked)
        value = _value_on_prefix(prefix, forbidden | set(out))
        if above is not None and value <= above:
            blocked.add(prefix)
            continue
        blocked.add(prefix)
        out.append(value)
    return out


def split_pair_f07(size: int) -> tuple[list[int], list[int], int]:
    """Two *size*-value sets with overlap and both exclusive sides.

    Each value sits under its own prefix at or above 2^16 and is above 2^32.
    Returns ``(left, right, absent)``.
    """
    if size < 3:
        raise HarnessError(f"split pair size {size} cannot show all three parts")
    if size in _NAMED_WIDTHS:
        raise HarnessError(f"split pair width {size} is a named population")
    overlap_n = max(1, size // 3)
    only_n = size - overlap_n
    if only_n < 1:
        raise HarnessError("split pair has no exclusive side")
    shared = _one_per_prefix(overlap_n, set(), above=1 << 32)
    left_only = _one_per_prefix(only_n, set(shared), above=1 << 32)
    right_only = _one_per_prefix(only_n, set(shared) | set(left_only), above=1 << 32)
    left = shared + left_only
    right = shared + right_only
    if len(set(left)) != size or len(set(right)) != size:
        raise HarnessError("split pair is not the requested width")
    if not (set(left) & set(right)):
        raise HarnessError("split pair has no overlap")
    if not (set(left) - set(right)) or not (set(right) - set(left)):
        raise HarnessError("split pair is missing an exclusive side")
    prefixes = [value >> 16 for value in set(left) | set(right)]
    if len(prefixes) != len(set(prefixes)):
        raise HarnessError("split pair put two values under one prefix")
    if any(value <= (1 << 32) for value in left + right):
        raise HarnessError("split pair has a value that is not above 2^32")
    absent = _one_per_prefix(1, set(left) | set(right), above=1 << 32)[0]
    return left, right, absent


def disjoint_sides_f07(width: int | None = None) -> tuple[list[int], list[int], int]:
    """Two unpublished sets with nothing in common, plus an absent value."""
    size = width if width is not None else unpublished_pair_size_f07()
    if size in _NAMED_WIDTHS:
        raise HarnessError(f"disjoint width {size} is a named population")
    left = _one_per_prefix(size, set(), above=1 << 32)
    right = _one_per_prefix(size, set(left), above=1 << 32)
    if set(left) & set(right):
        raise HarnessError("disjoint draw overlapped")
    absent = _one_per_prefix(1, set(left) | set(right), above=1 << 32)[0]
    return left, right, absent


def one_prefix_roles_f07() -> tuple[int, int, int, int]:
    """Three values under one prefix at or above 2^16, plus an absent value.

    Returns ``(left_only, shared, right_only, absent)``.
    """
    prefix = _fresh_prefix({0})
    if prefix < 1:
        raise HarnessError("role prefix is below 2^16")
    forbidden: set[int] = set()
    values: list[int] = []
    while len(values) < 3:
        value = _value_on_prefix(prefix, forbidden)
        if (value >> 16) != prefix:
            raise HarnessError("role value left its prefix")
        forbidden.add(value)
        values.append(value)
    absent_prefix = _fresh_prefix({prefix, 0})
    absent = _value_on_prefix(absent_prefix, set(values))
    return values[0], values[1], values[2], absent


def zero_result_sides_f07() -> dict[str, list[int]]:
    """Three pairs whose intersection, union, and difference each contain 0 and a later value."""
    shared = unpublished_u64_f07(above=1 << 32)
    left_only = unpublished_u64_f07({shared}, above=1 << 32)
    right_only = unpublished_u64_f07({shared, left_only}, above=1 << 32)
    union_extra = unpublished_u64_f07({shared, left_only, right_only}, above=1 << 32)
    diff_drop = unpublished_u64_f07(
        {shared, left_only, right_only, union_extra}, above=1 << 32
    )
    diff_keep = unpublished_u64_f07(
        {shared, left_only, right_only, union_extra, diff_drop}, above=1 << 32
    )
    return {
        "inter_left": [0, shared, left_only],
        "inter_right": [0, shared, right_only],
        "inter_expected": sorted({0, shared}),
        "inter_absent": sorted({left_only, right_only}),
        "union_left": [0, left_only],
        "union_right": [union_extra],
        "union_expected": sorted({0, left_only, union_extra}),
        "union_absent": [right_only],
        "diff_left": [0, diff_keep, diff_drop],
        "diff_right": [diff_drop],
        "diff_expected": sorted({0, diff_keep}),
        "diff_absent": [diff_drop],
    }


def self_population_f07() -> tuple[list[int], int]:
    """A non-empty unpublished set above 2^32, plus a value that is not in it."""
    size = unpublished_pair_size_f07()
    values = _one_per_prefix(size, set(), above=1 << 32)
    absent = _one_per_prefix(1, set(values), above=1 << 32)[0]
    return values, absent


def identity_population_f07() -> tuple[list[int], int]:
    """A set that contains a value above 2^32 and a value other than 0, plus an absent value."""
    high = unpublished_u64_f07(above=1 << 32)
    other = unpublished_u64_f07({high})
    if other == 0:
        raise HarnessError("identity population drew 0")
    absent = unpublished_u64_f07({high, other})
    return [high, other], absent


def spread_3000_f07() -> tuple[list[int], int, list[int]]:
    """Exactly 3000 values across at least three prefixes at or above 2^16.

    Returns ``(left, survivor, right_only)``. The survivor is one of the left
    values and is neither 3 nor 2^60.
    """
    per = 1000
    prefixes = [_fresh_prefix(set())]
    while len(prefixes) < 3:
        prefixes.append(_fresh_prefix(set(prefixes)))
    forbidden = set(F07_NAMED_U64)
    left: list[int] = []
    for prefix in prefixes:
        if prefix < 1:
            raise HarnessError("3000 population used a prefix below 2^16")
        block = forbidden | set(left)
        guard = 0
        got = 0
        while got < per:
            guard += 1
            if guard > per * 4:
                raise HarnessError("could not fill a 3000-value prefix")
            value = _value_on_prefix(prefix, block)
            if value in (3, 1 << 60) or value in F07_NAMED_U64:
                raise HarnessError("3000 population drew a named value")
            block.add(value)
            left.append(value)
            got += 1
    if len(left) != 3000 or len(set(left)) != 3000:
        raise HarnessError("3000 population is not 3000 distinct values")
    if len({value >> 16 for value in left}) < 3:
        raise HarnessError("3000 population uses fewer than three prefixes")
    survivor = left[secrets.randbelow(len(left))]
    if survivor in (3, 1 << 60):
        raise HarnessError("survivor is a named value")
    right_only = _one_per_prefix(4, set(left), above=1 << 32)
    return left, survivor, right_only


def difference_high_prefix_f07() -> tuple[list[int], list[int], list[int]]:
    """A left set with a high prefix to empty and values to keep.

    Returns ``(left, right, kept)``. *right* holds exactly the values that
    must disappear. Those values share one prefix at or above 2^16.
    """
    drop_prefix = _fresh_prefix(set())
    keep_a = _one_per_prefix(2, set(), above=1 << 32)
    blocked = {drop_prefix} | {value >> 16 for value in keep_a}
    drop = [_value_on_prefix(drop_prefix, set(keep_a)) for _ in range(3)]
    if len(set(drop)) != 3:
        raise HarnessError("difference drop values collided")
    if any((value >> 16) < 1 for value in drop):
        raise HarnessError("difference drop prefix is below 2^16")
    if set(drop) & set(keep_a):
        raise HarnessError("difference drop overlaps the kept values")
    _ = blocked
    left = keep_a + drop
    return left, drop, keep_a


def low_prefix_arm_f07() -> tuple[list[int], list[int], list[int]]:
    """Low values below 2^16 plus at least one value at or above 2^16.

    Returns ``(low, high, absent)``. Intersection or difference can drop
    *low* and leave *high*.
    """
    low: list[int] = []
    while len(low) < 4:
        value = secrets.randbelow(LOW_SPACE)
        if value in _EARLIER_NAMED or value in low or value in F07_NAMED_U64:
            continue
        low.append(value)
    high = _one_per_prefix(3, set(low), above=1 << 16)
    if any(value < (1 << 16) for value in high):
        raise HarnessError("high arm is below 2^16")
    if any(value >= (1 << 16) for value in low):
        raise HarnessError("low arm is not below 2^16")
    absent = _one_per_prefix(1, set(low) | set(high), above=1 << 32)[0]
    return low, high, absent


def neighbouring_prefixes_f07() -> tuple[list[int], list[int], list[int]]:
    """Four consecutive prefixes at or above 2^16. Ends stay, the middle two go.

    Returns ``(ends, middles, absent)``.
    """
    start = 1 + secrets.randbelow(PREFIX_SPACE - 8)
    prefixes = [start + i for i in range(4)]
    if any(prefix < 1 for prefix in prefixes):
        raise HarnessError("neighbouring prefix is below 2^16")
    if prefixes != list(range(prefixes[0], prefixes[0] + 4)):
        raise HarnessError("neighbouring prefixes are not consecutive")
    values = [_value_on_prefix(prefix, set()) for prefix in prefixes]
    if len({value >> 16 for value in values}) != 4:
        raise HarnessError("neighbouring values do not cover four prefixes")
    ends = [values[0], values[3]]
    middles = [values[1], values[2]]
    absent = _one_per_prefix(1, set(values), above=1 << 32)[0]
    return ends, middles, absent


def emptied_all_f07() -> tuple[list[int], list[int]]:
    """Left values on at least two high prefixes, and a disjoint non-empty right."""
    left = _one_per_prefix(2, set(), above=1 << 16)
    if len({value >> 16 for value in left}) < 2:
        raise HarnessError("emptied-all left is not on two prefixes")
    right = _one_per_prefix(2, set(left), above=1 << 16)
    if set(left) & set(right):
        raise HarnessError("emptied-all sides overlap")
    return left, right


def prefixes_500_and_800_f07() -> tuple[list[int], list[int]]:
    """500 prefixes including 0's prefix, and 800 fresh high-prefix values.

    Every prefix other than 0 holds one value at or above 2^16.
    """
    removed: list[int] = []
    blocked = {0}
    while len(removed) < 499:
        prefix = _fresh_prefix(blocked)
        value = _value_on_prefix(prefix, set(removed) | {0})
        if value < (1 << 16) or (value >> 16) < 1:
            raise HarnessError("500-prefix value is not a high prefix")
        blocked.add(prefix)
        removed.append(value)
    if len({value >> 16 for value in removed} | {0}) != 500:
        raise HarnessError("500-prefix construction is not 500 prefixes")
    fresh_blocked = blocked | {value >> 16 for value in removed}
    added = _one_per_prefix(800, set(removed) | {0}, above=1 << 16)
    if len(added) != 800:
        raise HarnessError("800-value draw is the wrong width")
    if any((value >> 16) < 1 for value in added):
        raise HarnessError("800-value draw used a low prefix")
    if set(added) & (set(removed) | {0}):
        raise HarnessError("800-value draw repeated a used value")
    _ = fresh_blocked
    return removed, added


def hundreds_prefixes_f07() -> tuple[list[int], int, int]:
    """At least 600 high prefixes, the survivor, and a fresh value to set later."""
    count = 600 + secrets.randbelow(5)
    if count < 600:
        raise HarnessError("hundreds population is under 600")
    values = _one_per_prefix(count, set(), above=1 << 16)
    if len({value >> 16 for value in values}) < 600:
        raise HarnessError("hundreds population has fewer than 600 prefixes")
    survivor = values[secrets.randbelow(len(values))]
    fresh = _one_per_prefix(1, set(values), above=1 << 16)[0]
    return values, survivor, fresh


def dense_against_sparse_f07() -> tuple[list[int], list[int]]:
    """A consecutive run below 2^16 of length at least 1000, and a sparse handful.

    The handful has a low value inside the run, a low value outside it, and
    a value at or above 2^16 and below 2^32.
    """
    length = 1000 + secrets.randbelow(200)
    if length < 1000:
        raise HarnessError("dense run is under 1000")
    room = LOW_SPACE - length
    if room <= 1:
        raise HarnessError("no room for a dense run below 2^16")
    start = secrets.randbelow(room)
    run = list(range(start, start + length))
    if any(value >= LOW_SPACE for value in run):
        raise HarnessError("dense run left the prefix below 2^16")
    inside = run[secrets.randbelow(len(run))]
    outside = None
    for _ in range(64):
        candidate = secrets.randbelow(LOW_SPACE)
        if candidate not in run and candidate not in F07_NAMED_U64:
            outside = candidate
            break
    if outside is None:
        raise HarnessError("could not draw a low value outside the run")
    mid = (1 << 16) + secrets.randbelow((1 << 32) - (1 << 16))
    if not ((1 << 16) <= mid < (1 << 32)):
        raise HarnessError("sparse mid value is not in [2^16, 2^32)")
    sparse = [inside, outside, mid]
    return run, sparse


def union_thousands_f07() -> tuple[list[int], list[int], list[int]]:
    """Two runs below 2^16 whose union is one consecutive run of length at least 5000.

    Neither side alone is that whole run.
    """
    total = 5000 + secrets.randbelow(400)
    if total < 5000 or total > LOW_SPACE:
        raise HarnessError(f"union length {total} is out of range")
    room = LOW_SPACE - total
    start = secrets.randbelow(room + 1) if room > 0 else 0
    cut = 1 + secrets.randbelow(total - 1)
    left = list(range(start, start + cut))
    right = list(range(start + cut, start + total))
    union = list(range(start, start + total))
    if len(union) < 5000:
        raise HarnessError("union run is under five thousand")
    if left == union or right == union:
        raise HarnessError("one side is already the whole run")
    if sorted(set(left) | set(right)) != union:
        raise HarnessError("union of the two runs is not the consecutive run")
    if any(value >= LOW_SPACE for value in union):
        raise HarnessError("union run is not below 2^16")
    return left, right, union


def borrow_sides_f07() -> tuple[list[int], list[int], int]:
    """Caller values and a distinct right side, each containing a value above 2^32."""
    caller = _one_per_prefix(4, set(), above=1 << 32)
    extra_low = unpublished_u64_f07(set(caller))
    if extra_low > (1 << 32):
        caller = caller[:-1] + [extra_low]
    if not any(value > (1 << 32) for value in caller):
        raise HarnessError("borrowed caller set has no value above 2^32")
    right = _one_per_prefix(3, set(caller), above=1 << 32)
    if set(caller) & set(right):
        raise HarnessError("borrowed sides overlap")
    if not any(value > (1 << 32) for value in right):
        raise HarnessError("borrowed right set has no value above 2^32")
    absent = _one_per_prefix(1, set(caller) | set(right), above=1 << 32)[0]
    return caller, right, absent


def refuse_population_f07() -> tuple[list[int], int, list[int]]:
    """Left values that empty one high prefix and leave one value.

    Returns ``(left, survivor, dropped)``.
    """
    survivor = _one_per_prefix(1, set(), above=1 << 16)[0]
    dropped = _one_per_prefix(2, {survivor}, above=1 << 16)
    if (survivor >> 16) < 1 or any((value >> 16) < 1 for value in dropped):
        raise HarnessError("refuse population did not empty a high prefix")
    if (survivor >> 16) in {value >> 16 for value in dropped}:
        raise HarnessError("refuse survivor shares a prefix with a dropped value")
    return [survivor, *dropped], survivor, dropped


def require_probe_true(report: Mapping[str, Any], *keys: str) -> None:
    """Every named JSON bool is true. Missing or non-bool fails the assertion."""
    from F02_helpers import require_bool_field

    for key in keys:
        assert require_bool_field(report, key) is True, key


_F07_ZIG = r"""
fn valuesMatch(bm: *const klyvmap.Bitmap, sorted: []const u64) bool {
    if (bm.getCardinality() != sorted.len) return false;
    var it = bm.iterator();
    for (sorted) |want| {
        const got = it.next() orelse return false;
        if (got != want) return false;
    }
    if (it.next() != null) return false;
    return it.next() == null;
}

fn containsAll(bm: *const klyvmap.Bitmap, vals: []const u64) bool {
    for (vals) |v| if (!bm.contains(v)) return false;
    return true;
}

fn containsNone(bm: *const klyvmap.Bitmap, vals: []const u64) bool {
    for (vals) |v| if (bm.contains(v)) return false;
    return true;
}

fn emptySnap(bm: *const klyvmap.Bitmap) bool {
    if (bm.getCardinality() != 0) return false;
    if (!bm.isEmpty()) return false;
    if (bm.minimum() != null) return false;
    if (bm.maximum() != null) return false;
    if (bm.contains(0)) return false;
    var it = bm.iterator();
    if (it.next() != null) return false;
    return it.next() == null;
}

fn operandIntact(bm: *const klyvmap.Bitmap, sorted: []const u64) bool {
    if (sorted.len == 0) return emptySnap(bm);
    if (bm.isEmpty()) return false;
    if (bm.getCardinality() != sorted.len) return false;
    const mn = bm.minimum() orelse return false;
    const mx = bm.maximum() orelse return false;
    if (mn != sorted[0] or mx != sorted[sorted.len - 1]) return false;
    if (!containsAll(bm, sorted)) return false;
    return valuesMatch(bm, sorted);
}

fn leftIs(bm: *const klyvmap.Bitmap, sorted: []const u64, absent: []const u64) bool {
    if (sorted.len == 0) {
        if (!emptySnap(bm)) return false;
    } else if (!operandIntact(bm, sorted)) return false;
    return containsNone(bm, absent);
}

fn buildFrom(alloc: std.mem.Allocator, vals: []const u64) !klyvmap.Bitmap {
    var bm = try klyvmap.Bitmap.init(alloc);
    for (vals) |v| _ = try bm.set(v);
    return bm;
}

fn shapeOf(buf: []const u8) !struct { len: usize, b0: u8, b1: u8, res: usize } {
    if (buf.len < 2) return error.ShortHeader;
    return .{
        .len = buf.len,
        .b0 = buf[0],
        .b1 = buf[1],
        .res = @intFromPtr(buf.ptr) % 8,
    };
}

fn zeroThenRest(bm: *const klyvmap.Bitmap, rest: []const u64) bool {
    var it = bm.iterator();
    const first = it.next() orelse return false;
    if (first != 0) return false;
    for (rest) |want| {
        const got = it.next() orelse return false;
        if (got != want) return false;
    }
    if (it.next() != null) return false;
    return it.next() == null;
}

fn applyOp(left: *klyvmap.Bitmap, right: *const klyvmap.Bitmap, which: u8) !void {
    if (which == 0) {
        left.andInPlace(right);
        return;
    }
    if (which == 1) {
        try left.orInPlace(right);
        return;
    }
    if (which == 2) {
        left.andNotInPlace(right);
        return;
    }
    return error.BadOp;
}

fn checkOp(
    alloc: std.mem.Allocator,
    left_ins: []const u64,
    right_ins: []const u64,
    left_sorted: []const u64,
    right_sorted: []const u64,
    expected: []const u64,
    absent: []const u64,
    which: u8,
) !bool {
    var left = try buildFrom(alloc, left_ins);
    defer left.deinit();
    var right = try buildFrom(alloc, right_ins);
    defer right.deinit();
    _ = left_sorted;
    try applyOp(&left, &right, which);
    const left_ok = leftIs(&left, expected, absent);
    const right_ok = operandIntact(&right, right_sorted);
    const card_ok = left.getCardinality() == expected.len;
    return left_ok and right_ok and card_ok and operandIntact(&left, expected);
}

fn openedIs(alloc: std.mem.Allocator, bm: *const klyvmap.Bitmap, sorted: []const u64) !bool {
    const view = bm.toBuffer();
    var opened = try klyvmap.Bitmap.fromBuffer(alloc, view, .borrow);
    defer opened.deinit();
    return leftIs(&opened, sorted, &[_]u64{});
}
"""

_REFUSE_ZIG = r"""
const NextRefuse = struct {
    parent: std.mem.Allocator,
    live: usize = 0,
    hold: bool = false,
    refused: usize = 0,
    scratch: []align(8) u8 = &.{},

    fn allocator(self: *NextRefuse) std.mem.Allocator {
        return .{
            .ptr = self,
            .vtable = &.{
                .alloc = alloc,
                .resize = resize,
                .remap = remap,
                .free = free,
            },
        };
    }

    fn alloc(ctx: *anyopaque, len: usize, alignment: std.mem.Alignment, ret_addr: usize) ?[*]u8 {
        const self: *NextRefuse = @ptrCast(@alignCast(ctx));
        if (self.hold) {
            self.refused += 1;
            return null;
        }
        const p = self.parent.vtable.alloc(self.parent.ptr, len, alignment, ret_addr) orelse return null;
        self.live += len;
        return p;
    }

    fn resize(ctx: *anyopaque, memory: []u8, alignment: std.mem.Alignment, new_len: usize, ret_addr: usize) bool {
        const self: *NextRefuse = @ptrCast(@alignCast(ctx));
        // A further request is a new allocation, or a resize that needs more
        // room than this block already holds. Shrinking the block is not that
        // request: cleanup reclaims an emptied prefix by giving room back.
        if (self.hold and new_len > memory.len) {
            self.refused += 1;
            return false;
        }
        if (!self.parent.vtable.resize(self.parent.ptr, memory, alignment, new_len, ret_addr)) return false;
        self.live = self.live - memory.len + new_len;
        return true;
    }

    fn remap(ctx: *anyopaque, memory: []u8, alignment: std.mem.Alignment, new_len: usize, ret_addr: usize) ?[*]u8 {
        const self: *NextRefuse = @ptrCast(@alignCast(ctx));
        if (self.hold and new_len > memory.len) {
            self.refused += 1;
            return null;
        }
        const p = self.parent.vtable.remap(self.parent.ptr, memory, alignment, new_len, ret_addr) orelse return null;
        self.live = self.live - memory.len + new_len;
        return p;
    }

    fn free(ctx: *anyopaque, memory: []u8, alignment: std.mem.Alignment, ret_addr: usize) void {
        const self: *NextRefuse = @ptrCast(@alignCast(ctx));
        self.parent.vtable.free(self.parent.ptr, memory, alignment, ret_addr);
        self.live -= memory.len;
    }
};

fn proveNextAllocFails(allocator: std.mem.Allocator, next: *NextRefuse) !void {
    const live_before = next.live;
    const refused_before = next.refused;
    if (allocator.alignedAlloc(u8, .@"8", 64)) |_| {
        return error.RefuseReportedSuccess;
    } else |_| {}
    if (next.live != live_before or next.refused <= refused_before) return error.RefuseSilent;
    // The same hold must not score a shrink of a block already held as the
    // further-request refusal. The parent may still decline an in-place
    // shrink; that decline is not this window.
    if (next.scratch.len < 64) return error.ShrinkSetupFailed;
    const refused_at_shrink = next.refused;
    if (allocator.resize(next.scratch, 32)) next.scratch = next.scratch[0..32];
    if (next.refused != refused_at_shrink) return error.ShrinkCountedAsRefusal;
}
"""


def wrap_f07_probe(body: str) -> str:
    """Wrap *body* in the tracking-allocator probe with F07 comparisons in scope."""
    src = wrap_probe_body(body)
    marker = "\nfn run("
    idx = src.find(marker)
    if idx < 0:
        raise HarnessError("wrap_probe_body produced no run function")
    src = src[:idx] + "\n" + _F07_ZIG + src[idx:]
    needle = "    const alloc_anchor = allocator;\n"
    insert = (
        needle
        + "    comptime { _ = valuesMatch; _ = containsAll; _ = containsNone; "
        + "_ = emptySnap; _ = operandIntact; _ = leftIs; _ = buildFrom; "
        + "_ = shapeOf; _ = zeroThenRest; _ = openedIs; _ = applyOp; _ = checkOp; }\n"
    )
    if needle not in src:
        raise HarnessError("tracking probe has no alloc anchor")
    return src.replace(needle, insert, 1)


def wrap_f07_refuse(body: str) -> str:
    """Wrap *body* so ``allocator`` refuses a new allocation while ``next.hold`` is set.

    A resize or remap that only shrinks a block this allocator already holds
    still succeeds. A resize or remap that asks for a longer block is a further
    request and fails with the new allocation. Construction before the window
    uses the same allocator with the hold clear. ``init.gpa`` is not this allocator.
    """
    return (
        ZIG_PRELUDE
        + "\n"
        + _F07_ZIG
        + "\n"
        + _REFUSE_ZIG
        + "\nfn run(init: std.process.Init, allocator: std.mem.Allocator, next: *NextRefuse) !void {\n"
        + "    comptime { _ = valuesMatch; _ = containsAll; _ = containsNone; "
        + "_ = emptySnap; _ = operandIntact; _ = leftIs; _ = buildFrom; "
        + "_ = shapeOf; _ = zeroThenRest; _ = openedIs; _ = applyOp; _ = checkOp; _ = proveNextAllocFails; }\n"
        + body
        + "\n}\n\n"
        + "pub fn main(init: std.process.Init) !void {\n"
        + "    var next: NextRefuse = .{ .parent = init.gpa };\n"
        + "    const backing = next.allocator();\n"
        + "    next.scratch = try backing.alignedAlloc(u8, .@\"8\", 64);\n"
        + "    defer backing.free(next.scratch);\n"
        + "    try run(init, backing, &next);\n"
        + "}\n"
    )


def run_f07_probe(body: str, **values: int | str) -> dict[str, Any]:
    """Compile and run one tracking probe. Non-zero status is a harness failure."""
    source = wrap_f07_probe(fill_u64(body, **values) if values else body)
    return run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)


def run_f07_refuse(body: str, **values: int | str) -> dict[str, Any]:
    """Compile and run one refusal-window probe."""
    source = wrap_f07_refuse(fill_u64(body, **values) if values else body)
    return run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
