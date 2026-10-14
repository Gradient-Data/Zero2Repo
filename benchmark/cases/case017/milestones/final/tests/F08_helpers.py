# feature: F08
"""Observation helpers for fused intersection, union, and difference counts.

JSON fields are test encoding. A compile or run that cannot be classified
raises. Counts and membership flags may cross JSON; values above 2^53 and
emitted bytes are compared inside the probe.
"""

from __future__ import annotations

import secrets
from typing import Any, Mapping, Sequence

from F01_helpers import (
    PUBLIC_U64_SAMPLES,
    ZIG_PRELUDE,
    fill_u64,
    require_positive_buffer_length,
    run_bitmap_probe,
    wrap_probe_body,
)
from F02_helpers import (
    F02_NAMED_U64_SAMPLES,
    LARGE_PROBE_TIMEOUT,
    require_bool_field,
    require_int_field,
    zig_u64_list,
)
from F03_helpers import F03_NAMED_U64_SAMPLES
from F04_helpers import F04_NAMED_U64, U64_MAX
from F05_helpers import F05_NAMED_U64
from F06_helpers import F06_NAMED_U64
from F07_helpers import F07_NAMED_U64
from _helpers import HarnessError

# Values and counts FP-08 names. Unpublished draws must not land on the values.
_F08_NAMED_VALUES = frozenset(
    {
        0,
        5,
        7,
        4000,
        4001,
        1 << 16,
        1 << 32,
        (1 << 32) + 5,
        4999,
        2957,
        7956,
        U64_MAX,
    }
)
_PUBLIC_COUNTS = frozenset({2, 2043, 2957, 5000, 7957})
_LOW = 1 << 16

NAMED_SET_F08 = (0, 7, 1 << 16, (1 << 32) + 5, U64_MAX)


def _forbidden(extra: set[int] | frozenset[int] | Sequence[int] | None = None) -> set[int]:
    blocked = set(PUBLIC_U64_SAMPLES)
    blocked |= set(F02_NAMED_U64_SAMPLES)
    blocked |= set(F03_NAMED_U64_SAMPLES)
    blocked |= set(F04_NAMED_U64)
    blocked |= set(F05_NAMED_U64)
    blocked |= set(F06_NAMED_U64)
    blocked |= set(F07_NAMED_U64)
    blocked |= set(_F08_NAMED_VALUES)
    if extra is not None:
        blocked.update(extra)
    return blocked


def unpublished_u64_f08(
    forbidden: set[int] | frozenset[int] | Sequence[int] | None = None,
) -> int:
    """One 64-bit value above 2^32 that this feature has not named.

    A draw that lands on a forbidden value raises. It is not remapped.
    """
    blocked = _forbidden(forbidden)
    low = (1 << 32) + 1
    high = (1 << 63) - 1
    start = low + 1 + secrets.randbelow((high - low) // 4)
    value = start + secrets.randbelow(high - start)
    if value in blocked or value <= (1 << 32):
        raise HarnessError(f"unpublished draw collided with a forbidden value: {value}")
    return value


def _prefix(value: int) -> int:
    return value >> 16


def _distinct(values: Sequence[int]) -> list[int]:
    out = [int(v) for v in values]
    if len(out) != len(set(out)):
        raise HarnessError("value list is not distinct")
    return out


def algebra_f08(left: Sequence[int], right: Sequence[int]) -> tuple[int, int, int, int]:
    """Ordinary set sizes: intersection, union, left\\right, right\\left."""
    a = set(_distinct(left))
    b = set(_distinct(right))
    return (len(a & b), len(a | b), len(a - b), len(b - a))


def assert_fused_f08(
    report: Mapping[str, Any],
    *,
    inter: int,
    union: int,
    diff_lr: int,
    diff_rl: int,
    left_card: int,
    right_card: int,
) -> None:
    """Counts equal the ordinary sizes and the materialized / in-place sizes.

    Missing fields raise. They are not read as zero.
    """
    expect = {
        "and_lr": inter,
        "and_rl": inter,
        "or_lr": union,
        "or_rl": union,
        "diff_lr": diff_lr,
        "diff_rl": diff_rl,
        "mat_and": inter,
        "mat_or": union,
        "ip_and": inter,
        "ip_diff_lr": diff_lr,
        "ip_diff_rl": diff_rl,
        "left_card": left_card,
        "right_card": right_card,
    }
    for key, want in expect.items():
        got = require_int_field(report, key)
        if got != want:
            raise AssertionError(f"{key} is {got}, want {want}")
    for key in ("left_same", "right_same"):
        if require_bool_field(report, key) is not True:
            raise AssertionError(f"{key} is not true")
    if require_int_field(report, "left_res") != 0 or require_int_field(report, "right_res") != 0:
        raise AssertionError(
            f"emitted address mod 8 is {report.get('left_res')!r}, {report.get('right_res')!r}"
        )
    require_positive_buffer_length(require_int_field(report, "left_len"))
    require_positive_buffer_length(require_int_field(report, "right_len"))


def overlapping_pair_f08() -> tuple[list[int], list[int], int]:
    """Unpublished values above 2^32 with only-left, only-right, and shared values.

    The pair size is not one of the named public counts. Exclusive counts differ
    so a later order check is not the only pair that can see a difference, but
    this draw is not that check.
    """
    for _ in range(32):
        blocked: set[int] = set()
        shared = unpublished_u64_f08(blocked)
        blocked.add(shared)
        only_left = [unpublished_u64_f08(blocked)]
        blocked.add(only_left[0])
        only_left.append(unpublished_u64_f08(blocked))
        blocked.add(only_left[1])
        only_right = [unpublished_u64_f08(blocked)]
        blocked.add(only_right[0])
        only_right.append(unpublished_u64_f08(blocked))
        blocked.add(only_right[1])
        absent = unpublished_u64_f08(blocked)
        left = [shared, *only_left]
        right = [shared, *only_right]
        inter, union, _diff_lr, _diff_rl = algebra_f08(left, right)
        if inter == 0:
            continue
        if {inter, union, len(left), len(right)} & _PUBLIC_COUNTS:
            continue
        if any(v <= (1 << 32) for v in left + right):
            raise HarnessError("overlapping pair dropped a value above 2^32")
        return _distinct(left), _distinct(right), absent
    raise HarnessError("could not draw an unpublished overlapping pair")


def split_prefix_above_2_pow_32_f08() -> tuple[list[int], list[int], int]:
    """Three values on one high prefix: only left, only right, and both.

    The prefix sits above 2^32. Intersection is 1, union is 3, each difference is 1.
    """
    prefix = (1 << 16) + 1 + secrets.randbelow(1 << 20)
    lows: list[int] = []
    while len(lows) < 3:
        low = secrets.randbelow(_LOW)
        if low not in lows:
            lows.append(low)
    values = [(prefix << 16) | low for low in lows]
    if any(v <= (1 << 32) for v in values):
        raise HarnessError("split-prefix values are not above 2^32")
    if len({_prefix(v) for v in values}) != 1:
        raise HarnessError("split-prefix values do not share one prefix")
    blocked = _forbidden(values)
    absent = unpublished_u64_f08(blocked)
    if _prefix(absent) == prefix:
        raise HarnessError("absent value landed on the split prefix")
    only_left, both, only_right = values
    return [only_left, both], [only_right, both], absent


def prefixes_miss_named_f08() -> tuple[list[int], int]:
    """Values whose high 48 bits miss every prefix of the named set.

    Includes a value above 2^32. Raises if a draw lands on a named prefix.
    """
    named_prefixes = {_prefix(v) for v in NAMED_SET_F08}
    picked: list[int] = []
    for _ in range(32):
        if len(picked) == 3:
            break
        value = unpublished_u64_f08(picked)
        if _prefix(value) in named_prefixes:
            raise HarnessError(f"prefix-miss draw hit a named prefix: {value}")
        picked.append(value)
    if len(picked) != 3 or not any(v > (1 << 32) for v in picked):
        raise HarnessError("prefix-miss side is incomplete")
    if set(picked) & set(NAMED_SET_F08):
        raise HarnessError("prefix-miss side shares a named value")
    return picked, unpublished_u64_f08(picked)


def shared_prefixes_no_common_value_f08() -> tuple[list[int], int]:
    """Share the low prefix and every named high prefix, with no common value.

    The other side is disjoint from the named set. Sharing only the low prefix
    is rejected.
    """
    named = set(NAMED_SET_F08)
    named_high = [v for v in NAMED_SET_F08 if _prefix(v) != 0]
    if len(named_high) < 3:
        raise HarnessError("named set lost a high prefix")
    low = None
    for _ in range(64):
        candidate = 1 + secrets.randbelow(_LOW - 1)
        if candidate in (0, 7) or candidate in _forbidden():
            continue
        low = candidate
        break
    if low is None:
        raise HarnessError("could not place a low-prefix value other than 0 and 7")
    other = [low]
    for named_value in named_high:
        prefix = _prefix(named_value)
        named_low = named_value & (_LOW - 1)
        placed = None
        for _ in range(64):
            candidate_low = secrets.randbelow(_LOW)
            if candidate_low == named_low:
                continue
            candidate = (prefix << 16) | candidate_low
            if candidate in named or candidate in other or candidate in _forbidden():
                continue
            placed = candidate
            break
        if placed is None:
            raise HarnessError("could not place a non-overlapping value on a named high prefix")
        other.append(placed)
    if set(other) & named:
        raise HarnessError("shared-prefix side contains a named value")
    other_prefixes = {_prefix(v) for v in other}
    if 0 not in other_prefixes:
        raise HarnessError("shared-prefix side missed the low prefix")
    if not other_prefixes & {_prefix(v) for v in named_high}:
        raise HarnessError("shared-prefix side missed every named high prefix")
    if other_prefixes == {0}:
        raise HarnessError("shared-prefix side has only the low prefix")
    absent = unpublished_u64_f08(other)
    return other, absent


def crossing_runs_f08() -> tuple[int, int, int, int, int]:
    """Two inclusive runs, one longer than a prefix, plus an absent value.

    Both cross the same 2^16 boundary, and so does their intersection.
    The long run contains two values with the same low 16 bits, so keeping
    only those bits changes the intersection, union, or difference size.
    A run that merely steps across one boundary does not: that map is still
    one-to-one, and the three sizes stay the same. The public 2043 / 7957 /
    2957 counts are rejected.
    """
    boundary_index = 1 + secrets.randbelow(4)
    boundary = boundary_index << 16
    before = 30 + secrets.randbelow(80)
    after = _LOW + 30 + secrets.randbelow(80)
    a0 = boundary - before
    a1 = boundary + after - 1
    b_before = 1 + secrets.randbelow(before)
    b_after = 1 + secrets.randbelow(40)
    b0 = boundary - b_before
    b1 = boundary + b_after - 1
    if not (a0 < boundary <= a1 and b0 < boundary <= b1):
        raise HarnessError("crossing runs do not cross the boundary")
    if _prefix(a0) == _prefix(a1):
        raise HarnessError("long run does not cross a prefix")
    inter_lo = max(a0, b0)
    inter_hi = min(a1, b1)
    if inter_lo >= boundary or inter_hi < boundary:
        raise HarnessError("crossing intersection stays on one side of the boundary")
    full_left = set(range(a0, a1 + 1))
    full_right = set(range(b0, b1 + 1))
    full = (
        len(full_left & full_right),
        len(full_left | full_right),
        len(full_left - full_right),
        len(full_right - full_left),
    )
    trunc_left = {v & (_LOW - 1) for v in full_left}
    trunc_right = {v & (_LOW - 1) for v in full_right}
    truncated = (
        len(trunc_left & trunc_right),
        len(trunc_left | trunc_right),
        len(trunc_left - trunc_right),
    )
    if truncated == full[:3]:
        raise HarnessError("low-16 truncation did not change the interval counts")
    if set(full) & {2043, 7957, 2957}:
        raise HarnessError("crossing run redrew a named count")
    absent = unpublished_u64_f08()
    if a0 <= absent <= a1 or b0 <= absent <= b1:
        raise HarnessError("absent value fell inside a crossing run")
    return a0, a1, b0, b1, absent


def exclusive_pair_f08() -> tuple[list[int], list[int], int]:
    """Overlapping unpublished values whose two differences have different sizes.

    Not the named 0..4999 against 2957..7956 pair.
    """
    left, right, absent = overlapping_pair_f08()
    extra = unpublished_u64_f08([*left, *right, absent])
    left = [*left, extra]
    _, _, diff_lr, diff_rl = algebra_f08(left, right)
    if diff_lr == diff_rl:
        raise HarnessError("exclusive pair differences are equal")
    if {len(left), len(right)} & _PUBLIC_COUNTS:
        raise HarnessError("exclusive pair size landed on a named count")
    if set(left) <= set(range(7957)) or set(right) <= set(range(7957)):
        raise HarnessError("exclusive pair collapsed onto the named low runs")
    return left, right, absent


def uncleaned_population_f08() -> tuple[list[int], list[int], list[int], int]:
    """Values to empty, a disjoint partner, a cover of every emptied value, an absent.

    The removed values sit on a low prefix and on prefixes above 2^32.
    The cover holds every removed value plus one extra value.
    """
    low = None
    for _ in range(64):
        candidate = 8 + secrets.randbelow(_LOW - 8)
        if candidate in _forbidden():
            continue
        low = candidate
        break
    if low is None:
        raise HarnessError("could not place an uncleaned low-prefix value")
    removed = [low]
    blocked = set(removed)
    attempts = 0
    while len(removed) < 3:
        attempts += 1
        if attempts > 32:
            raise HarnessError("could not place uncleaned values on distinct prefixes")
        value = unpublished_u64_f08(blocked)
        if _prefix(value) in {_prefix(v) for v in removed}:
            continue
        removed.append(value)
        blocked.add(value)
    if len({_prefix(v) for v in removed}) < 3:
        raise HarnessError("uncleaned values do not cover three prefixes")
    if not any(_prefix(v) == 0 for v in removed):
        raise HarnessError("uncleaned values missed the low prefix")
    if not any(v > (1 << 32) for v in removed):
        raise HarnessError("uncleaned values missed a value above 2^32")
    partner_value = unpublished_u64_f08(blocked)
    if _prefix(partner_value) in {_prefix(v) for v in removed}:
        raise HarnessError("emptying partner shares a prefix with the removed values")
    extra = unpublished_u64_f08(blocked | {partner_value})
    cover = [*removed, extra]
    if set(removed) - set(cover):
        raise HarnessError("cover dropped a removed value")
    absent = unpublished_u64_f08(set(cover) | {partner_value})
    return removed, [partner_value], cover, absent


def refuse_pair_f08() -> tuple[list[int], list[int], int]:
    """A small overlapping pair above 2^32, built before a refusal window."""
    return overlapping_pair_f08()


def borrow_sides_f08() -> tuple[list[int], list[int], int]:
    """Caller-buffer values and a second owned bitmap, with one shared value."""
    return overlapping_pair_f08()


_F08_ZIG = r"""
const FusedCounts = struct {
    and_lr: u64,
    and_rl: u64,
    or_lr: u64,
    or_rl: u64,
    diff_lr: u64,
    diff_rl: u64,
};

const PairReport = struct {
    and_lr: u64,
    and_rl: u64,
    or_lr: u64,
    or_rl: u64,
    diff_lr: u64,
    diff_rl: u64,
    mat_and: u64,
    mat_or: u64,
    ip_and: u64,
    ip_diff_lr: u64,
    ip_diff_rl: u64,
    left_same: bool,
    right_same: bool,
    left_len: usize,
    right_len: usize,
    left_res: usize,
    right_res: usize,
    left_card: u64,
    right_card: u64,
};

const Snap = struct {
    card: u64,
    bytes: []u8,
    res: usize,
};

fn buildFrom(alloc: std.mem.Allocator, vals: []const u64) !klyvmap.Bitmap {
    var bm = try klyvmap.Bitmap.init(alloc);
    for (vals) |v| _ = try bm.set(v);
    return bm;
}

fn freshEmpty(alloc: std.mem.Allocator) !klyvmap.Bitmap {
    return klyvmap.Bitmap.init(alloc);
}

fn fillRange(bm: *klyvmap.Bitmap, start: u64, end_inclusive: u64) !void {
    var x = start;
    while (x <= end_inclusive) : (x += 1) _ = try bm.set(x);
}

fn takeSnap(gpa: std.mem.Allocator, bm: *const klyvmap.Bitmap) !Snap {
    const view = bm.toBuffer();
    if (view.len == 0) return error.EmptyEmit;
    const res = @intFromPtr(view.ptr) % 8;
    if (res != 0) return error.Unaligned;
    return .{
        .card = bm.getCardinality(),
        .bytes = try gpa.dupe(u8, view),
        .res = res,
    };
}

fn proveComparator(gpa: std.mem.Allocator, sample: []const u8) !void {
    if (sample.len == 0) return error.EmptyEmit;
    const copy = try gpa.dupe(u8, sample);
    defer gpa.free(copy);
    copy[0] ^= 0xff;
    if (std.mem.eql(u8, copy, sample)) return error.ObserverSilent;
}

fn listHeld(bm: *const klyvmap.Bitmap, vals: []const u64, absent: u64, card: u64) bool {
    if (bm.getCardinality() != card) return false;
    for (vals) |v| if (!bm.contains(v)) return false;
    if (bm.contains(absent)) return false;
    return true;
}

fn rangeHeld(bm: *const klyvmap.Bitmap, start: u64, end_inclusive: u64, absent: u64, card: u64) bool {
    if (bm.getCardinality() != card) return false;
    if (bm.contains(absent)) return false;
    var x = start;
    while (x <= end_inclusive) : (x += 1) if (!bm.contains(x)) return false;
    return true;
}

fn bytesSame(bm: *const klyvmap.Bitmap, snap: Snap) bool {
    const view = bm.toBuffer();
    if (@intFromPtr(view.ptr) % 8 != 0) return false;
    return std.mem.eql(u8, view, snap.bytes);
}

fn readFused(left: *const klyvmap.Bitmap, right: *const klyvmap.Bitmap) FusedCounts {
    return .{
        .and_lr = left.andCardinality(right),
        .and_rl = right.andCardinality(left),
        .or_lr = left.orCardinality(right),
        .or_rl = right.orCardinality(left),
        .diff_lr = left.andNotCardinality(right),
        .diff_rl = right.andNotCardinality(left),
    };
}

fn controls(alloc: std.mem.Allocator, left: *const klyvmap.Bitmap, right: *const klyvmap.Bitmap) !PairReport {
    var mand = try klyvmap.Bitmap.And(alloc, left, right);
    defer mand.deinit();
    var mor = try klyvmap.Bitmap.Or(alloc, left, right);
    defer mor.deinit();
    var ip_and_bm = try left.clone();
    defer ip_and_bm.deinit();
    ip_and_bm.andInPlace(right);
    var ip_lr = try left.clone();
    defer ip_lr.deinit();
    ip_lr.andNotInPlace(right);
    var ip_rl = try right.clone();
    defer ip_rl.deinit();
    ip_rl.andNotInPlace(left);
    return .{
        .and_lr = 0,
        .and_rl = 0,
        .or_lr = 0,
        .or_rl = 0,
        .diff_lr = 0,
        .diff_rl = 0,
        .mat_and = mand.getCardinality(),
        .mat_or = mor.getCardinality(),
        .ip_and = ip_and_bm.getCardinality(),
        .ip_diff_lr = ip_lr.getCardinality(),
        .ip_diff_rl = ip_rl.getCardinality(),
        .left_same = false,
        .right_same = false,
        .left_len = 0,
        .right_len = 0,
        .left_res = 0,
        .right_res = 0,
        .left_card = 0,
        .right_card = 0,
    };
}

fn finishReport(fused: FusedCounts, ctl: PairReport, left_snap: Snap, right_snap: Snap, left_same: bool, right_same: bool) PairReport {
    return .{
        .and_lr = fused.and_lr,
        .and_rl = fused.and_rl,
        .or_lr = fused.or_lr,
        .or_rl = fused.or_rl,
        .diff_lr = fused.diff_lr,
        .diff_rl = fused.diff_rl,
        .mat_and = ctl.mat_and,
        .mat_or = ctl.mat_or,
        .ip_and = ctl.ip_and,
        .ip_diff_lr = ctl.ip_diff_lr,
        .ip_diff_rl = ctl.ip_diff_rl,
        .left_same = left_same,
        .right_same = right_same,
        .left_len = left_snap.bytes.len,
        .right_len = right_snap.bytes.len,
        .left_res = left_snap.res,
        .right_res = right_snap.res,
        .left_card = left_snap.card,
        .right_card = right_snap.card,
    };
}

fn fullLists(
    alloc: std.mem.Allocator,
    gpa: std.mem.Allocator,
    left: *klyvmap.Bitmap,
    right: *klyvmap.Bitmap,
    lvals: []const u64,
    rvals: []const u64,
    absent: u64,
) !PairReport {
    const left_snap = try takeSnap(gpa, left);
    defer gpa.free(left_snap.bytes);
    const right_snap = try takeSnap(gpa, right);
    defer gpa.free(right_snap.bytes);
    try proveComparator(gpa, left_snap.bytes);
    const fused = readFused(left, right);
    const ctl = try controls(alloc, left, right);
    const left_same = listHeld(left, lvals, absent, left_snap.card) and bytesSame(left, left_snap);
    const right_same = listHeld(right, rvals, absent, right_snap.card) and bytesSame(right, right_snap);
    return finishReport(fused, ctl, left_snap, right_snap, left_same, right_same);
}

fn fullRanges(
    alloc: std.mem.Allocator,
    gpa: std.mem.Allocator,
    left: *klyvmap.Bitmap,
    right: *klyvmap.Bitmap,
    a0: u64,
    a1: u64,
    b0: u64,
    b1: u64,
    absent: u64,
) !PairReport {
    const left_snap = try takeSnap(gpa, left);
    defer gpa.free(left_snap.bytes);
    const right_snap = try takeSnap(gpa, right);
    defer gpa.free(right_snap.bytes);
    try proveComparator(gpa, left_snap.bytes);
    const fused = readFused(left, right);
    const ctl = try controls(alloc, left, right);
    const left_same = rangeHeld(left, a0, a1, absent, left_snap.card) and bytesSame(left, left_snap);
    const right_same = rangeHeld(right, b0, b1, absent, right_snap.card) and bytesSame(right, right_snap);
    return finishReport(fused, ctl, left_snap, right_snap, left_same, right_same);
}

fn emitPair(init: std.process.Init, gpa: std.mem.Allocator, r: PairReport) !void {
    try emitJson(init, gpa,
        "{{\"and_lr\":{d},\"and_rl\":{d},\"or_lr\":{d},\"or_rl\":{d},\"diff_lr\":{d},\"diff_rl\":{d},\"mat_and\":{d},\"mat_or\":{d},\"ip_and\":{d},\"ip_diff_lr\":{d},\"ip_diff_rl\":{d},\"left_same\":{s},\"right_same\":{s},\"left_len\":{d},\"right_len\":{d},\"left_res\":{d},\"right_res\":{d},\"left_card\":{d},\"right_card\":{d}}}",
        .{
            r.and_lr, r.and_rl, r.or_lr, r.or_rl, r.diff_lr, r.diff_rl,
            r.mat_and, r.mat_or, r.ip_and, r.ip_diff_lr, r.ip_diff_rl,
            jsonBool(r.left_same), jsonBool(r.right_same),
            r.left_len, r.right_len, r.left_res, r.right_res, r.left_card, r.right_card,
        },
    );
}

fn containsAll(bm: *const klyvmap.Bitmap, vals: []const u64) bool {
    for (vals) |v| if (!bm.contains(v)) return false;
    return true;
}

fn containsNone(bm: *const klyvmap.Bitmap, vals: []const u64) bool {
    for (vals) |v| if (bm.contains(v)) return false;
    return true;
}
"""

_REFUSE_EVERY_ZIG = r"""
const RefuseEvery = struct {
    parent: std.mem.Allocator,
    blocked: bool = false,
    refused: usize = 0,

    fn allocator(self: *RefuseEvery) std.mem.Allocator {
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
        const self: *RefuseEvery = @ptrCast(@alignCast(ctx));
        if (self.blocked) {
            self.refused += 1;
            return null;
        }
        const p = self.parent.vtable.alloc(self.parent.ptr, len, alignment, ret_addr) orelse return null;
        return p;
    }

    fn resize(ctx: *anyopaque, memory: []u8, alignment: std.mem.Alignment, new_len: usize, ret_addr: usize) bool {
        const self: *RefuseEvery = @ptrCast(@alignCast(ctx));
        if (self.blocked and new_len > memory.len) {
            self.refused += 1;
            return false;
        }
        return self.parent.vtable.resize(self.parent.ptr, memory, alignment, new_len, ret_addr);
    }

    fn remap(ctx: *anyopaque, memory: []u8, alignment: std.mem.Alignment, new_len: usize, ret_addr: usize) ?[*]u8 {
        const self: *RefuseEvery = @ptrCast(@alignCast(ctx));
        if (self.blocked and new_len > memory.len) {
            self.refused += 1;
            return null;
        }
        return self.parent.vtable.remap(self.parent.ptr, memory, alignment, new_len, ret_addr);
    }

    fn free(ctx: *anyopaque, memory: []u8, alignment: std.mem.Alignment, ret_addr: usize) void {
        const self: *RefuseEvery = @ptrCast(@alignCast(ctx));
        self.parent.vtable.free(self.parent.ptr, memory, alignment, ret_addr);
    }
};

fn proveEveryAllocRefused(allocator: std.mem.Allocator, window: *RefuseEvery) !void {
    const before = window.refused;
    if (allocator.alignedAlloc(u8, .@"8", 64)) |_| {
        return error.RefuseReportedSuccess;
    } else |_| {}
    if (window.refused <= before) return error.RefuseSilent;
}
"""

_COMPTIME_REFS = (
    "    comptime { _ = buildFrom; _ = freshEmpty; _ = fillRange; _ = takeSnap; "
    "_ = proveComparator; _ = listHeld; _ = rangeHeld; _ = bytesSame; _ = readFused; "
    "_ = controls; _ = finishReport; _ = fullLists; _ = fullRanges; _ = emitPair; "
    "_ = containsAll; _ = containsNone; }\n"
)


def wrap_f08_probe(body: str) -> str:
    """Wrap *body* in the tracking probe with fused-count helpers in scope."""
    src = wrap_probe_body(body)
    marker = "\nfn run("
    idx = src.find(marker)
    if idx < 0:
        raise HarnessError("wrap_probe_body produced no run function")
    src = src[:idx] + "\n" + _F08_ZIG + src[idx:]
    needle = "    const alloc_anchor = allocator;\n"
    if needle not in src:
        raise HarnessError("tracking probe has no alloc anchor")
    return src.replace(needle, needle + _COMPTIME_REFS, 1)


def wrap_f08_refuse_every(body: str) -> str:
    """Wrap *body* so every allocation is refused while ``window.blocked`` is set.

    The window is not a one-shot refusal. Free still runs. Construction before
    the flag is set uses the same allocator and is allowed.
    """
    return (
        ZIG_PRELUDE
        + "\n"
        + _F08_ZIG
        + "\n"
        + _REFUSE_EVERY_ZIG
        + "\nfn run(init: std.process.Init, allocator: std.mem.Allocator, window: *RefuseEvery) !void {\n"
        + _COMPTIME_REFS
        + "    comptime { _ = proveEveryAllocRefused; }\n"
        + body
        + "\n}\n\n"
        + "pub fn main(init: std.process.Init) !void {\n"
        + "    var window: RefuseEvery = .{ .parent = init.gpa };\n"
        + "    try run(init, window.allocator(), &window);\n"
        + "}\n"
    )


def run_f08_probe(body: str, **values: int | str) -> dict[str, Any]:
    """Compile and run one tracking probe. Non-zero status is a harness failure."""
    source = wrap_f08_probe(fill_u64(body, **values) if values else body)
    return run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)


def run_f08_refuse(body: str, **values: int | str) -> dict[str, Any]:
    """Compile and run one every-allocation refusal probe."""
    source = wrap_f08_refuse_every(fill_u64(body, **values) if values else body)
    return run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
