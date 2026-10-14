# feature: F09
"""Inputs and probe wrappers for building a bitmap from a non-decreasing list.

JSON fields are the probe's encoding. A draw that lands on a named sample
raises. Comparisons of 64-bit values and of emitted bytes happen inside
the probe; the JSON carries booleans and small integers only.
"""

from __future__ import annotations

import secrets
from collections import Counter
from typing import Sequence

from F01_helpers import PUBLIC_U64_SAMPLES, wrap_probe_body
from F02_helpers import F02_NAMED_U64_SAMPLES, zig_u64_list
from F03_helpers import F03_NAMED_U64_SAMPLES
from F04_helpers import (
    F04_NAMED_U64,
    U64_MAX,
    trace_arch_network_syscalls,
    unpublished_u64_f04,
)
from _helpers import HarnessError

# Values FP-09 names, plus the public samples earlier features already used.
# An unpublished draw that lands here raises; it is not returned.
_F09_NAMED = frozenset(
    {
        0,
        1,
        999,
        1000,
        4999,
        5000,
        6000,
        1 << 16,
        1 << 32,
        (1 << 32) + (1 << 16) - 1,
        1 << 40,
        1 << 48,
        1 << 63,
        U64_MAX,
        U64_MAX - 1,
    }
)

_BLOCKED = (
    frozenset(PUBLIC_U64_SAMPLES)
    | frozenset(F02_NAMED_U64_SAMPLES)
    | frozenset(F03_NAMED_U64_SAMPLES)
    | frozenset(F04_NAMED_U64)
    | _F09_NAMED
)

# The prefix whose start is 2^32: low 16 bits run across one 2^16-wide block.
# This is not the prefix whose high-48 key equals 2^32 (that block starts at 2^48).
_WINDOW_LO = 1 << 32
_WINDOW_HI = _WINDOW_LO + (1 << 16) - 1
_WINDOW_KEY = _WINDOW_LO >> 16


def unpublished_u64_f09(
    forbidden: set[int] | frozenset[int] | None = None,
    *,
    above: int | None = None,
) -> int:
    """A 64-bit value the public samples of this feature do not name.

    Raises if the draw is a named sample or is in *forbidden*.
    """
    extra = set(_F09_NAMED)
    if forbidden is not None:
        extra.update(forbidden)
    value = unpublished_u64_f04(extra, above=above)
    if value in extra or value in _BLOCKED:
        raise HarnessError(
            f"unpublished_u64_f09 collided with a forbidden value: {value}"
        )
    return value


def trace_network_argv(argv, *, cwd, env, timeout):
    """Run the sealed arch-network tracer on *argv*.

    Same observer for the product path and for the deliberate socket.
    """
    return trace_arch_network_syscalls(
        argv,
        cwd=cwd,
        env=env,
        timeout=timeout,
    )


def _unique_non_decreasing(values: Sequence[int]) -> list[int]:
    """Distinct values of a non-decreasing list, in that order.

    A decreasing adjacent pair is a generator bug. It raises and does not
    call the product.
    """
    vals = [int(v) for v in values]
    for i in range(1, len(vals)):
        if vals[i] < vals[i - 1]:
            raise HarnessError(
                "generated list decreases; refusing to call the product"
            )
    unique: list[int] = []
    for value in vals:
        if not unique or unique[-1] != value:
            unique.append(value)
    for i in range(1, len(unique)):
        if unique[i] <= unique[i - 1]:
            raise HarnessError("unique list is not strictly ascending")
    return unique


def _low_positive_f09(forbidden: set[int]) -> int:
    """A value in 1 .. 2^32-1 that is not a named sample and not *forbidden*."""
    blocked = set(_BLOCKED) | forbidden
    span = (1 << 32) - 1
    for _ in range(64):
        value = 1 + secrets.randbelow(span)
        if value in blocked or value == 0 or value >= (1 << 32):
            continue
        if _WINDOW_LO <= value <= _WINDOW_HI:
            raise HarnessError("low draw fell inside the 2^32 prefix")
        return value
    raise HarnessError("could not draw a positive value below 2^32")


def mixed_unpublished_list_f09() -> tuple[list[int], list[int], int]:
    """Non-decreasing list that does not start at 0, with one repeated value.

    The repeated value sits outside the prefix that starts at 2^32 and is
    not the 64-bit maximum. The maximum and one less than the maximum are
    both present, and they are not the only distinct values.

    Returns ``(values, sorted unique, one absent value)``.
    """
    low = _low_positive_f09(set())
    mid = unpublished_u64_f09(forbidden={low})
    extra = unpublished_u64_f09(forbidden={low, mid})
    if mid in (0, U64_MAX, U64_MAX - 1, low) or extra in (
        0,
        U64_MAX,
        U64_MAX - 1,
        low,
        mid,
    ):
        raise HarnessError("mixed list drew a named extreme as an ordinary value")
    reps = 2 + secrets.randbelow(3)
    values = [low] * reps + [mid, extra, U64_MAX - 1, U64_MAX]
    values.sort()
    unique = _unique_non_decreasing(values)
    if 0 in values or values[0] == 0 or values[0] != low:
        raise HarnessError("mixed list starts at 0 or lost its minimum")
    if values[-1] != U64_MAX or unique[-1] != U64_MAX:
        raise HarnessError("mixed list does not end at the 64-bit maximum")
    if U64_MAX - 1 not in unique:
        raise HarnessError("mixed list lost one less than the maximum")
    if len(unique) < 3 or len(values) <= len(unique):
        raise HarnessError("mixed list is not a multi-value list with a duplicate")
    if len(unique) in (5000, 6000) or len(values) in (5000, 6000):
        raise HarnessError("mixed list collided with a named length")
    counts = Counter(values)
    repeated = [value for value, count in counts.items() if count >= 2]
    if repeated != [low]:
        raise HarnessError("mixed list repeated a value other than the low one")
    if low == U64_MAX or _WINDOW_LO <= low <= _WINDOW_HI:
        raise HarnessError("repeated value sits on the maximum or in the 2^32 prefix")
    absent = unpublished_u64_f09(forbidden=set(values))
    if absent in values or absent == 0:
        raise HarnessError("absent draw is present or is 0")
    return values, unique, absent


def repeated_maximum_list_f09() -> tuple[list[int], int]:
    """Two or more copies of the 64-bit maximum, and nothing else.

    The repeat count is not 5000 and not 6000.
    """
    count = 2 + secrets.randbelow(200)
    if count < 2 or count in (5000, 6000):
        raise HarnessError(f"repeat count {count} is not an unpublished repeat")
    return [U64_MAX] * count, count


def six_thousand_list_f09() -> tuple[list[int], list[int], int]:
    """6000-element list, dense in the prefix that starts at 2^32, with duplicates.

    Other elements lie on at least 1000 different prefixes, each once.
    Returns ``(values, sorted unique, one absent value inside that prefix)``.
    """
    dense_count = 4000 + secrets.randbelow(1001)
    if not 4000 <= dense_count <= 5000:
        raise HarnessError(f"dense appearance count {dense_count} left its range")
    scattered = 6000 - dense_count
    if scattered < 1000:
        raise HarnessError("scattered tail is shorter than 1000")
    distinct_w = 2000 + secrets.randbelow(dense_count - 2000)
    if not 2000 <= distinct_w < dense_count or distinct_w >= (1 << 16):
        raise HarnessError(f"window distinct count {distinct_w} is not usable")
    chosen = {_WINDOW_LO, _WINDOW_HI}
    need = distinct_w - 2
    while len(chosen) < distinct_w:
        low = 1 + secrets.randbelow((1 << 16) - 2)
        chosen.add(_WINDOW_LO + low)
    if len(chosen) != distinct_w:
        raise HarnessError("window sample did not reach the distinct count")
    distinct = list(chosen)
    values = list(distinct)
    extras = dense_count - distinct_w
    if extras < 1:
        raise HarnessError("window sample has no duplicate")
    for _ in range(extras):
        values.append(distinct[secrets.randbelow(len(distinct))])
    if len(values) != dense_count:
        raise HarnessError("window multiset has the wrong length")
    present = set(distinct)
    hole = None
    for _ in range(64):
        candidate = _WINDOW_LO + secrets.randbelow(1 << 16)
        if candidate not in present:
            hole = candidate
            break
    if hole is None:
        for candidate in range(_WINDOW_LO, _WINDOW_HI + 1):
            if candidate not in present:
                hole = candidate
                break
    if hole is None or hole in present or not _WINDOW_LO <= hole <= _WINDOW_HI:
        raise HarnessError("no absent value inside the 2^32 prefix")
    used = {_WINDOW_KEY}
    scattered_vals: list[int] = []
    # One prefix below the 2^32 block, so the minimum is not glued to that block's start.
    low_key = 1 + secrets.randbelow(_WINDOW_KEY - 1)
    low_bits = secrets.randbelow(1 << 16)
    low_value = (low_key << 16) | low_bits
    if low_value == 0 or _WINDOW_LO <= low_value <= _WINDOW_HI:
        raise HarnessError("low scattered value fell on 0 or inside the window")
    used.add(low_key)
    scattered_vals.append(low_value)
    guard = 0
    while len(scattered_vals) < scattered:
        guard += 1
        if guard > 100000:
            raise HarnessError("could not draw scattered prefixes")
        key = 1 + secrets.randbelow((1 << 48) - 2)
        if key in used or key == _WINDOW_KEY:
            continue
        low = secrets.randbelow(1 << 16)
        value = (key << 16) | low
        if value == 0 or _WINDOW_LO <= value <= _WINDOW_HI:
            continue
        used.add(key)
        scattered_vals.append(value)
    values.extend(scattered_vals)
    values.sort()
    unique = _unique_non_decreasing(values)
    _validate_six_thousand(values, unique, hole)
    return values, unique, hole


def _validate_six_thousand(values: list[int], unique: list[int], hole: int) -> None:
    if len(values) != 6000:
        raise HarnessError(f"six-thousand list has length {len(values)}")
    if 0 in values or unique[0] == 0 or unique[0] != values[0] or unique[-1] != values[-1]:
        raise HarnessError("six-thousand list starts at 0 or lost its ends")
    if len(unique) >= 6000 or len(unique) != len(set(values)):
        raise HarnessError("six-thousand unique count is not below 6000")
    in_window = [value for value in values if _WINDOW_LO <= value <= _WINDOW_HI]
    distinct_w = set(in_window)
    if not 4000 <= len(in_window) <= 5000:
        raise HarnessError(f"window appearances {len(in_window)}")
    if len(distinct_w) < 2000 or len(distinct_w) >= len(in_window):
        raise HarnessError("window is not dense-with-a-duplicate")
    if len(distinct_w) >= (1 << 16):
        raise HarnessError("window has no room for an absent value")
    if _WINDOW_LO not in distinct_w or _WINDOW_HI not in distinct_w:
        raise HarnessError("window is missing an endpoint")
    if hole in distinct_w or not _WINDOW_LO <= hole <= _WINDOW_HI:
        raise HarnessError("hole is not an absent value of the 2^32 prefix")
    others = [value for value in values if value < _WINDOW_LO or value > _WINDOW_HI]
    keys = [value >> 16 for value in others]
    if _WINDOW_KEY in keys or len(keys) != len(set(keys)) or len(set(keys)) < 1000:
        raise HarnessError("scattered prefixes are not 1000 distinct foreign prefixes")


def five_thousand_prefix_values_f09() -> list[int]:
    """The 5000 values named by FP-09: ``(i << 32) + (i mod 1000)`` for i in 0..4999."""
    values = [((i << 32) + (i % 1000)) for i in range(5000)]
    if values[0] != 0:
        raise HarnessError("frozen series does not start at 0")
    if values[1] != ((1 << 32) + 1):
        raise HarnessError("frozen series second value is not (1 << 32) + 1")
    if values[-1] != ((4999 << 32) + 999):
        raise HarnessError("frozen series does not end at the named maximum")
    if len(values) != 5000 or len(set(values)) != 5000:
        raise HarnessError("frozen series is not 5000 distinct values")
    if 1 in values:
        raise HarnessError("frozen series contains 1")
    _unique_non_decreasing(values)
    return values


def absent_beside_prefix_series_f09(values: Sequence[int], modulus: int) -> int:
    """A value under one of the series' high prefixes that the series does not hold.

    Not the value 1. 1 is the separate named absence.
    """
    if modulus < 2:
        raise HarnessError(f"modulus {modulus} is below 2")
    present = set(values)
    width = len(values)
    for _ in range(64):
        index = secrets.randbelow(width)
        low = secrets.randbelow(1 << 16)
        if low == (index % modulus):
            continue
        candidate = (index << 32) | low
        if candidate in present or candidate == 1 or candidate == 0:
            continue
        return candidate
    raise HarnessError("could not draw an absent value beside the prefix series")


def unpublished_prefix_series_f09() -> tuple[int, int, list[int], int]:
    """Same shape as the 5000-value series, with a different count and modulus.

    Returns ``(count, modulus, values, one absent high-prefix value)``.
    """
    count = 100 + secrets.randbelow(3901)
    modulus = 2 + secrets.randbelow(499)
    if count < 100 or count > 4000 or count == 5000:
        raise HarnessError(f"prefix-series count {count} is a named size")
    if modulus < 2 or modulus > 500 or modulus == 1000:
        raise HarnessError(f"prefix-series modulus {modulus} is the named modulus")
    values = [((i << 32) + (i % modulus)) for i in range(count)]
    if values[0] != 0 or len(values) != count or len(set(values)) != count:
        raise HarnessError("unpublished prefix series is not a strict high-prefix run")
    last = ((count - 1) << 32) + ((count - 1) % modulus)
    if values[-1] != last:
        raise HarnessError("unpublished prefix series does not end on its formula")
    if 1 in values:
        raise HarnessError("unpublished prefix series contains 1")
    _unique_non_decreasing(values)
    absent = absent_beside_prefix_series_f09(values, modulus)
    return count, modulus, values, absent


def consecutive_thousands_list_f09() -> tuple[list[int], list[int], int, int, int]:
    """Thousands of consecutive values on a prefix that is not 0 and not 2^32.

    At least 500 further prefixes sit strictly above that block. One adjacent
    duplicate is inside the consecutive run, and one is on a prefix that holds
    only that single distinct value.

    Returns ``(values, sorted unique, prefix start, run length, absent hole)``.
    The hole is the integer just past the run, still inside the same prefix.
    """
    start_key = None
    for _ in range(32):
        key = 1 + secrets.randbelow((1 << 20) - 1)
        if key == _WINDOW_KEY or key == 0:
            continue
        start_key = key
        break
    if start_key is None:
        raise HarnessError("could not choose a prefix start")
    start = start_key << 16
    if (
        start < (1 << 16)
        or start >= (1 << 48)
        or start == 0
        or start == _WINDOW_LO
        or start % (1 << 16) != 0
        or (start >> 16) == _WINDOW_KEY
    ):
        raise HarnessError(f"prefix start {start} is not a foreign block below 2^48")
    run_len = 2000 + secrets.randbelow(2001)
    if not 2000 <= run_len <= 4000 or start + run_len >= start + (1 << 16):
        raise HarnessError(f"consecutive length {run_len} fills or misses the block")
    run = list(range(start, start + run_len))
    dup_at = secrets.randbelow(run_len)
    run.insert(dup_at, run[dup_at])
    others = 500 + secrets.randbelow(200)
    if others < 500:
        raise HarnessError("not enough prefixes above the run")
    higher: list[int] = []
    used = {start_key, _WINDOW_KEY}
    guard = 0
    span = (1 << 32) - (start_key + 1)
    if span < others + 2:
        raise HarnessError("no room for prefixes above the chosen start")
    while len(higher) < others:
        guard += 1
        if guard > 100000:
            raise HarnessError("could not draw prefixes above the run")
        key = start_key + 1 + secrets.randbelow(span - 1)
        if key in used or key == _WINDOW_KEY or key <= start_key:
            continue
        low = secrets.randbelow(1 << 16)
        value = (key << 16) | low
        if value <= start + run_len - 1 or value == 0:
            raise HarnessError("higher value is not above the consecutive run")
        used.add(key)
        higher.append(value)
    higher.sort()
    dup_higher = secrets.randbelow(len(higher))
    higher.insert(dup_higher, higher[dup_higher])
    values = run + higher
    unique = _unique_non_decreasing(values)
    hole = start + run_len
    _validate_consecutive(values, unique, start, run_len, hole, others)
    return values, unique, start, run_len, hole


def _validate_consecutive(
    values: list[int],
    unique: list[int],
    start: int,
    run_len: int,
    hole: int,
    others: int,
) -> None:
    if 0 in values or values[0] != start or unique[0] != start:
        raise HarnessError("consecutive list does not start at its prefix")
    if len(values) == 6000 or len(unique) == 5000:
        raise HarnessError("consecutive list collided with a named length")
    if len(unique) != run_len + others or len(values) != len(unique) + 2:
        raise HarnessError("consecutive duplicate accounting is wrong")
    if not len(unique) > run_len or not len(values) > len(unique):
        raise HarnessError("cardinality would not sit strictly between run length and list length")
    if hole != start + run_len or hole in unique or hole >= start + (1 << 16):
        raise HarnessError("hole is not the next integer inside the prefix")
    if (start + run_len - 1) not in unique:
        raise HarnessError("end of the consecutive run is missing")
    if _WINDOW_LO <= start <= _WINDOW_HI or (start >> 16) == _WINDOW_KEY:
        raise HarnessError("consecutive run sits on the 2^32 prefix")
    counts = Counter(values)
    duplicated = [value for value, count in counts.items() if count >= 2]
    in_run = [value for value in duplicated if start <= value < start + run_len]
    sparse = [value for value in duplicated if (value >> 16) > (start >> 16)]
    if len(in_run) < 1:
        raise HarnessError("consecutive run has no duplicate")
    if len(sparse) != 1:
        raise HarnessError("expected one duplicate on a higher prefix")
    sparse_key = sparse[0] >> 16
    if sparse_key == (start >> 16) or sparse_key == _WINDOW_KEY:
        raise HarnessError("sparse duplicate sits on the dense prefix or on 2^32")
    on_key = {value for value in values if (value >> 16) == sparse_key}
    if on_key != {sparse[0]}:
        raise HarnessError("sparse prefix holds more than one distinct value")
    higher_keys = {value >> 16 for value in values if (value >> 16) > (start >> 16)}
    higher_keys.discard(_WINDOW_KEY)
    if len(higher_keys) < 500:
        raise HarnessError("fewer than 500 prefixes above the run")
    if any(_WINDOW_LO <= value <= _WINDOW_HI for value in values):
        raise HarnessError("consecutive list contains a value of the 2^32 prefix")


_F09_ZIG = r"""
fn requireNonDecreasing(vals: []const u64) !void {
    var i: usize = 1;
    while (i < vals.len) : (i += 1) {
        if (vals[i] < vals[i - 1]) return error.DecreasingInput;
    }
}

fn requireStrict(vals: []const u64) !void {
    if (vals.len == 0) return error.EmptyUnique;
    var i: usize = 1;
    while (i < vals.len) : (i += 1) {
        if (vals[i] <= vals[i - 1]) return error.UniqueNotStrict;
    }
}

fn allMembers(bm: *const klyvmap.Bitmap, unique: []const u64) bool {
    for (unique) |v| {
        if (!bm.contains(v)) return false;
    }
    return true;
}

fn extremaMatch(bm: *const klyvmap.Bitmap, lo: u64, hi: u64) bool {
    const mn = bm.minimum() orelse return false;
    const mx = bm.maximum() orelse return false;
    return mn == lo and mx == hi;
}

fn drainTwice(bm: *const klyvmap.Bitmap, unique: []const u64) bool {
    var it = bm.iterator();
    for (unique) |w| {
        const got = it.next() orelse return false;
        if (got != w) return false;
    }
    if (it.next() != null) return false;
    if (it.next() != null) return false;
    return true;
}

fn arrayEquals(bm: *const klyvmap.Bitmap, alloc: std.mem.Allocator, unique: []const u64) !bool {
    const arr = try bm.toArray(alloc);
    defer alloc.free(arr);
    if (arr.len != unique.len) return false;
    for (unique, arr) |w, g| {
        if (w != g) return false;
    }
    return true;
}

fn arrayLen(bm: *const klyvmap.Bitmap, alloc: std.mem.Allocator) !usize {
    const arr = try bm.toArray(alloc);
    defer alloc.free(arr);
    return arr.len;
}

fn setLoopEquals(alloc: std.mem.Allocator, vals: []const u64, unique: []const u64) !bool {
    var other = try klyvmap.Bitmap.init(alloc);
    defer other.deinit();
    for (vals) |v| _ = try other.set(v);
    return arrayEquals(&other, alloc, unique);
}

fn firstEquals(bm: *const klyvmap.Bitmap, want: u64) bool {
    var it = bm.iterator();
    const got = it.next() orelse return false;
    return got == want;
}

fn moreAfterFirst(bm: *const klyvmap.Bitmap) bool {
    var it = bm.iterator();
    if (it.next() == null) return false;
    return it.next() != null;
}

fn secondEquals(bm: *const klyvmap.Bitmap, unique: []const u64) bool {
    if (unique.len < 2) return true;
    var it = bm.iterator();
    if (it.next() == null) return false;
    const got = it.next() orelse return false;
    return got == unique[1];
}

fn headerOf(buf: []const u8) struct { len: usize, b0: usize, b1: usize, res: usize } {
    return .{
        .len = buf.len,
        .b0 = if (buf.len > 0) buf[0] else 0xff,
        .b1 = if (buf.len > 1) buf[1] else 0xff,
        .res = if (buf.len == 0) 1 else @intFromPtr(buf.ptr) % 8,
    };
}

fn emitParts(
    init: std.process.Init,
    gpa: std.mem.Allocator,
    comptime left_fmt: []const u8,
    left_args: anytype,
    comptime right_fmt: []const u8,
    right_args: anytype,
) !void {
    const left = try std.fmt.allocPrint(gpa, left_fmt, left_args);
    defer gpa.free(left);
    const right = try std.fmt.allocPrint(gpa, right_fmt, right_args);
    defer gpa.free(right);
    const text = try std.fmt.allocPrint(gpa, "{s}{s}", .{ left, right });
    defer gpa.free(text);
    try writeStdout(init, text);
}

fn byteControl(gpa: std.mem.Allocator, snap: []const u8) !bool {
    if (snap.len == 0) return false;
    const mutated = try gpa.alloc(u8, snap.len);
    defer gpa.free(mutated);
    @memcpy(mutated, snap);
    mutated[0] ^= 1;
    return !std.mem.eql(u8, snap, mutated);
}

const OpenedBytes = struct {
    bytes_same: bool,
    untouched: bool,
    control: bool,
    len: usize,
    b0: usize,
    b1: usize,
    res: usize,
    copy_res: usize,
};

fn openedBytes(
    bm: *const klyvmap.Bitmap,
    opened: *const klyvmap.Bitmap,
    copy: []const u8,
    snap: []const u8,
    gpa: std.mem.Allocator,
) !OpenedBytes {
    const src = bm.toBuffer();
    const hdr = headerOf(src);
    const copy_res: usize = if (copy.len == 0) 1 else @intFromPtr(copy.ptr) % 8;
    return .{
        .bytes_same = std.mem.eql(u8, opened.toBuffer(), src),
        .untouched = std.mem.eql(u8, copy, snap),
        .control = try byteControl(gpa, snap),
        .len = hdr.len,
        .b0 = hdr.b0,
        .b1 = hdr.b1,
        .res = hdr.res,
        .copy_res = copy_res,
    };
}

const Round = struct {
    bytes_same: bool,
    untouched: bool,
    control: bool,
    opened_members: bool,
    opened_array: bool,
    opened_drain: bool,
    opened_has_a: bool,
    opened_has_b: bool,
    opened_hole_absent: bool,
    opened_contains0: bool,
    opened_card: u64,
    len: usize,
    b0: usize,
    b1: usize,
    res: usize,
    copy_res: usize,
};

fn roundTrip(
    bm: *const klyvmap.Bitmap,
    alloc: std.mem.Allocator,
    gpa: std.mem.Allocator,
    unique: []const u64,
    marker_a: u64,
    marker_b: u64,
    hole: u64,
    want_hole: bool,
) !Round {
    const copy = try bm.toBufferCopy(alloc);
    defer alloc.free(copy);
    const snap = try gpa.alloc(u8, copy.len);
    defer gpa.free(snap);
    @memcpy(snap, copy);
    var opened = try klyvmap.Bitmap.fromBuffer(alloc, copy, .borrow);
    defer opened.deinit();
    const bytes = try openedBytes(bm, &opened, copy, snap, gpa);
    return .{
        .bytes_same = bytes.bytes_same,
        .untouched = bytes.untouched,
        .control = bytes.control,
        .opened_members = allMembers(&opened, unique),
        .opened_array = try arrayEquals(&opened, alloc, unique),
        .opened_drain = drainTwice(&opened, unique),
        .opened_has_a = opened.contains(marker_a),
        .opened_has_b = opened.contains(marker_b),
        .opened_hole_absent = if (want_hole) !opened.contains(hole) else true,
        .opened_contains0 = opened.contains(0),
        .opened_card = opened.getCardinality(),
        .len = bytes.len,
        .b0 = bytes.b0,
        .b1 = bytes.b1,
        .res = bytes.res,
        .copy_res = bytes.copy_res,
    };
}
"""


def wrap_sorted_probe(body: str) -> str:
    """Wrap a sorted-list probe. Helpers are test encoding, not a product API."""
    src = wrap_probe_body(body)
    marker = "\nfn run("
    idx = src.find(marker)
    if idx < 0:
        raise HarnessError("wrap_probe_body produced no run function")
    return src[:idx] + "\n" + _F09_ZIG + src[idx:]


_BUILD_BODY = r"""
    const vals = [_]u64{
        __VALS__
    };
    const unique = [_]u64{
        __UNIQUE__
    };
    const marker_a: u64 = __MARKER_A__;
    const marker_b: u64 = __MARKER_B__;
    const absent: u64 = __ABSENT__;
    const hole: u64 = __HOLE__;
    const want_hole = __WANT_HOLE__;
    try requireNonDecreasing(&vals);
    try requireStrict(&unique);
    const before = track.live;
    var bm = try klyvmap.Bitmap.fromSortedList(allocator, &vals);
    const card = bm.getCardinality();
    const empty = bm.isEmpty();
    const contains0 = bm.contains(0);
    const has_a = bm.contains(marker_a);
    const has_b = bm.contains(marker_b);
    const absent_out = !bm.contains(absent);
    const hole_absent = if (want_hole) !bm.contains(hole) else true;
    const members = allMembers(&bm, &unique);
    const extrema = extremaMatch(&bm, unique[0], unique[unique.len - 1]);
    const drained = drainTwice(&bm, &unique);
    const first_ok = firstEquals(&bm, unique[0]);
    const more = moreAfterFirst(&bm);
    const second_ok = secondEquals(&bm, &unique);
    const array_ok = try arrayEquals(&bm, allocator, &unique);
    const array_len = try arrayLen(&bm, allocator);
    const set_ok = try setLoopEquals(allocator, &vals, &unique);
    const rt = try roundTrip(&bm, allocator, init.gpa, &unique, marker_a, marker_b, hole, want_hole);
    bm.deinit();
    const released = track.live == before;
    const nvals: usize = vals.len;
    const unique_len: usize = unique.len;
    try emitParts(init, init.gpa,
        "{{\"card\":{d},\"empty\":{s},\"contains0\":{s},\"has_a\":{s},\"has_b\":{s},\"absent_out\":{s},\"hole_absent\":{s},\"members\":{s},\"extrema\":{s},\"drained\":{s},\"first_ok\":{s},\"more\":{s},\"second_ok\":{s},\"array_ok\":{s},\"array_len\":{d},\"set_ok\":{s},",
        .{
            card, jsonBool(empty), jsonBool(contains0), jsonBool(has_a), jsonBool(has_b),
            jsonBool(absent_out), jsonBool(hole_absent), jsonBool(members), jsonBool(extrema),
            jsonBool(drained), jsonBool(first_ok), jsonBool(more), jsonBool(second_ok),
            jsonBool(array_ok), array_len, jsonBool(set_ok),
        },
        "\"bytes_same\":{s},\"untouched\":{s},\"control\":{s},\"opened_members\":{s},\"opened_array\":{s},\"opened_drain\":{s},\"opened_has_a\":{s},\"opened_has_b\":{s},\"opened_hole_absent\":{s},\"opened_contains0\":{s},\"opened_card\":{d},\"len\":{d},\"b0\":{d},\"b1\":{d},\"res\":{d},\"copy_res\":{d},\"released\":{s},\"nvals\":{d},\"unique_len\":{d}}}",
        .{
            jsonBool(rt.bytes_same), jsonBool(rt.untouched), jsonBool(rt.control),
            jsonBool(rt.opened_members), jsonBool(rt.opened_array), jsonBool(rt.opened_drain),
            jsonBool(rt.opened_has_a), jsonBool(rt.opened_has_b), jsonBool(rt.opened_hole_absent),
            jsonBool(rt.opened_contains0), rt.opened_card, rt.len, rt.b0, rt.b1, rt.res,
            rt.copy_res, jsonBool(released), nvals, unique_len,
        },
    );
"""


def sorted_build_source(
    values: Sequence[int],
    unique: Sequence[int],
    *,
    marker_a: int,
    marker_b: int,
    absent: int,
    hole: int = 0,
    want_hole: bool = False,
) -> str:
    """Probe source that builds *values* and compares them with *unique*."""
    if len(values) == 0 or len(unique) == 0:
        raise HarnessError("sorted build probe requires a non-empty list")
    from F01_helpers import fill_u64

    body = fill_u64(
        _BUILD_BODY,
        vals=zig_u64_list(values),
        unique=zig_u64_list(unique),
        marker_a=int(marker_a),
        marker_b=int(marker_b),
        absent=int(absent),
        hole=int(hole),
        want_hole="true" if want_hole else "false",
    )
    return wrap_sorted_probe(body)


_EMPTY_BODY = r"""
    const fresh_a: u64 = __FRESH_A__;
    const fresh_b: u64 = __FRESH_B__;
    if (fresh_a == fresh_b) return error.SameFreshValue;
    const vals = [_]u64{};
    const before = track.live;
    var bm = try klyvmap.Bitmap.fromSortedList(allocator, &vals);
    const empty = bm.isEmpty();
    const card = bm.getCardinality();
    const contains0 = bm.contains(0);
    const min_j = try optU64Json(init.gpa, bm.minimum());
    defer init.gpa.free(min_j);
    const max_j = try optU64Json(init.gpa, bm.maximum());
    defer init.gpa.free(max_j);
    var it = bm.iterator();
    const first = it.next();
    const first_exhausted = first == null;
    const first_was_zero = if (first) |v| v == 0 else false;
    const second = it.next();
    const second_exhausted = second == null;
    const second_was_zero = if (second) |v| v == 0 else false;
    const array_len = try arrayLen(&bm, allocator);
    const copy = try bm.toBufferCopy(allocator);
    const snap = try init.gpa.alloc(u8, copy.len);
    defer init.gpa.free(snap);
    @memcpy(snap, copy);
    var opened = try klyvmap.Bitmap.fromBuffer(allocator, copy, .borrow);
    const opened_empty = opened.isEmpty();
    const opened_card0 = opened.getCardinality();
    const opened_contains0 = opened.contains(0);
    const opened_min_j = try optU64Json(init.gpa, opened.minimum());
    defer init.gpa.free(opened_min_j);
    const opened_max_j = try optU64Json(init.gpa, opened.maximum());
    defer init.gpa.free(opened_max_j);
    const bytes = try openedBytes(&bm, &opened, copy, snap, init.gpa);
    _ = try bm.set(fresh_a);
    const orig_has = bm.contains(fresh_a);
    const orig_card = bm.getCardinality();
    const orig_empty = bm.isEmpty();
    const orig_still0 = bm.contains(0);
    const orig_extrema = extremaMatch(&bm, fresh_a, fresh_a);
    const orig_not_b = !bm.contains(fresh_b);
    _ = try opened.set(fresh_b);
    const open_has = opened.contains(fresh_b);
    const open_card = opened.getCardinality();
    const open_empty = opened.isEmpty();
    const open_still0 = opened.contains(0);
    const open_not_a = !opened.contains(fresh_a);
    const open_extrema = extremaMatch(&opened, fresh_b, fresh_b);
    opened.deinit();
    allocator.free(copy);
    bm.deinit();
    const released = track.live == before;
    try emitParts(init, init.gpa,
        "{{\"empty\":{s},\"cardinality\":{d},\"contains0\":{s},\"min\":{s},\"max\":{s},\"first_exhausted\":{s},\"second_exhausted\":{s},\"first_was_zero\":{s},\"second_was_zero\":{s},\"array_len\":{d},\"opened_empty\":{s},\"opened_cardinality\":{d},\"opened_contains0\":{s},\"opened_min\":{s},\"opened_max\":{s},",
        .{
            jsonBool(empty), card, jsonBool(contains0), min_j, max_j,
            jsonBool(first_exhausted), jsonBool(second_exhausted),
            jsonBool(first_was_zero), jsonBool(second_was_zero), array_len,
            jsonBool(opened_empty), opened_card0, jsonBool(opened_contains0),
            opened_min_j, opened_max_j,
        },
        "\"bytes_same\":{s},\"untouched\":{s},\"control\":{s},\"len\":{d},\"b0\":{d},\"b1\":{d},\"res\":{d},\"copy_res\":{d},\"orig_has\":{s},\"orig_card\":{d},\"orig_empty\":{s},\"orig_still0\":{s},\"orig_extrema\":{s},\"orig_not_b\":{s},\"open_has\":{s},\"open_card\":{d},\"open_empty\":{s},\"open_still0\":{s},\"open_not_a\":{s},\"open_extrema\":{s},\"released\":{s}}}",
        .{
            jsonBool(bytes.bytes_same), jsonBool(bytes.untouched), jsonBool(bytes.control),
            bytes.len, bytes.b0, bytes.b1, bytes.res, bytes.copy_res,
            jsonBool(orig_has), orig_card, jsonBool(orig_empty), jsonBool(orig_still0),
            jsonBool(orig_extrema), jsonBool(orig_not_b),
            jsonBool(open_has), open_card, jsonBool(open_empty), jsonBool(open_still0),
            jsonBool(open_not_a), jsonBool(open_extrema), jsonBool(released),
        },
    );
"""


def empty_list_source(fresh_a: int, fresh_b: int) -> str:
    """Probe source for a length-zero sequence, then one later set on each bitmap."""
    if fresh_a == fresh_b:
        raise HarnessError("the two later-set values are the same")
    if fresh_a <= (1 << 40) or fresh_b <= (1 << 40):
        raise HarnessError("a later-set value is not above 2^40")
    from F01_helpers import fill_u64

    return wrap_sorted_probe(
        fill_u64(_EMPTY_BODY, fresh_a=int(fresh_a), fresh_b=int(fresh_b))
    )


_IO_BODY = r"""
    const vals = [_]u64{
        __VALS__
    };
    const unique = [_]u64{
        __UNIQUE__
    };
    try requireNonDecreasing(&vals);
    var bm = try klyvmap.Bitmap.fromSortedList(allocator, &vals);
    defer bm.deinit();
    if (bm.getCardinality() != unique.len) return error.CardMismatch;
    if (!bm.contains(unique[0])) return error.MissingMember;
    const copy = try bm.toBufferCopy(allocator);
    defer allocator.free(copy);
    var opened = try klyvmap.Bitmap.fromBuffer(allocator, copy, .borrow);
    defer opened.deinit();
    if (!opened.contains(unique[0])) return error.OpenedMissing;
    if (opened.getCardinality() != unique.len) return error.OpenedCard;
    const view = opened.toBuffer();
    if (view.len == 0) return error.EmptyEmit;
    _ = view[0];
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
"""


def io_honest_source(values: Sequence[int], unique: Sequence[int]) -> str:
    """Representative sorted-list path: build, query, emit, borrow-open, query."""
    if len(values) == 0 or len(unique) == 0:
        raise HarnessError("I/O probe requires a non-empty list")
    from F01_helpers import fill_u64

    return wrap_sorted_probe(
        fill_u64(
            _IO_BODY,
            vals=zig_u64_list(values),
            unique=zig_u64_list(unique),
        )
    )
