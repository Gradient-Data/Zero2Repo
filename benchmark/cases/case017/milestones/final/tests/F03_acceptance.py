# feature: F03
"""FP-03: cardinality, extrema, and ascending enumeration.

Assertions follow Full_PRD.original.md FP-03 (L144–L171) together with
in-scope pre-FP obligations the public query / iterator / array entries
can trigger: the L7 first path (cardinality 2; 0 is not end of
iteration; values above 2^32 stay), values in the closed 64-bit range
with no second copy (L17–L19), library with no file or network I/O
(L37, L55), 64-bit domain (L60), and no removable-substrate negative
control (L59, L78).
"""

from __future__ import annotations

from pathlib import Path

from F01_helpers import (
    fill_u64,
    network_syscalls_in_trace,
    product_created_files,
    run_bitmap_probe,
    run_traced_network,
    wrap_probe_body,
    _walk_regular_files,
)
from F02_helpers import (
    LARGE_PROBE_TIMEOUT,
    nine_boundary_values,
    require_bool_field,
    require_int_field,
    shuffle_not_sorted,
    unpublished_dense_interior,
    unpublished_thousands_length,
    unpublished_u64_f02,
    zig_u64_list,
)
from F03_helpers import (
    compile_probe_or_raise,
    independent_sorted_unique_dense_and_scattered,
    require_allocated_matches_independent,
    require_card_empty,
    require_destination_matches_independent,
    require_false,
    require_no_integer,
    require_true,
    sentinel_absent_from,
    unpublished_extrema_pair,
    unpublished_hundreds_length,
    unpublished_low_high_runs,
    unpublished_prefix_run_length,
    unpublished_scattered_pair,
    unpublished_three_prefix_values,
    unpublished_u64_f03,
    unused_suffix_slots,
    wrap_enumeration_probe,
)
from F02_helpers import (
    block_checkpoints,
    require_sweep_seen,
    require_sweep_true,
    run_block_sweep,
    shrink_checkpoints,
)
from _helpers import DEFAULT_TIMEOUT, HarnessError, workspace


# ---------------------------------------------------------------------------
# A. Cardinality, emptiness, empty extrema
# ---------------------------------------------------------------------------


def test_empty_bitmap_cardinality_zero_empty_true_extrema_absent():
    source = wrap_enumeration_probe(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    const min_j = try optU64Json(init.gpa, bm.minimum());
    defer init.gpa.free(min_j);
    const max_j = try optU64Json(init.gpa, bm.maximum());
    defer init.gpa.free(max_j);
    try emitJson(init, init.gpa,
        "{{\"empty\":{s},\"card\":{d},\"min\":{s},\"max\":{s},\"extrema_absent\":{s}}}",
        .{
            jsonBool(bm.isEmpty()), bm.getCardinality(), min_j, max_j,
            jsonBool(extremaAbsent(&bm)),
        },
    );
"""
    )
    report = run_bitmap_probe(source)
    require_card_empty(report, card=0, empty=True)
    require_no_integer(report, "min")
    require_no_integer(report, "max")
    require_true(report, "extrema_absent")


def test_emptiness_agrees_with_cardinality_zero_after_removing_last_value():
    value = unpublished_u64_f03()
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const value: u64 = __VALUE__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(value);
    const mid_empty = bm.isEmpty();
    const mid_card = bm.getCardinality();
    const mid_extrema = extremaEqual(&bm, value, value);
    _ = bm.remove(value);
    const min_j = try optU64Json(init.gpa, bm.minimum());
    defer init.gpa.free(min_j);
    const max_j = try optU64Json(init.gpa, bm.maximum());
    defer init.gpa.free(max_j);
    try emitJson(init, init.gpa,
        "{{\"mid_empty\":{s},\"mid_card\":{d},\"mid_extrema\":{s},\"empty\":{s},\"card\":{d},\"min\":{s},\"max\":{s},\"extrema_absent\":{s}}}",
        .{
            jsonBool(mid_empty), mid_card, jsonBool(mid_extrema),
            jsonBool(bm.isEmpty()), bm.getCardinality(), min_j, max_j,
            jsonBool(extremaAbsent(&bm)),
        },
    );
""",
            value=value,
        )
    )
    report = run_bitmap_probe(source)
    require_card_empty(report, card=1, empty=False, card_key="mid_card", empty_key="mid_empty")
    require_true(report, "mid_extrema")
    require_card_empty(report, card=0, empty=True)
    require_no_integer(report, "min")
    require_no_integer(report, "max")
    require_true(report, "extrema_absent")


def test_cardinality_counts_distinct_present_values_not_duplicate_sets():
    first = unpublished_u64_f03()
    second = unpublished_u64_f03(forbidden={first})
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const a: u64 = __A__;
    const b: u64 = __B__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(a);
    _ = try bm.set(a);
    _ = try bm.set(b);
    try emitJson(init, init.gpa,
        "{{\"empty\":{s},\"card\":{d}}}",
        .{ jsonBool(bm.isEmpty()), bm.getCardinality() },
    );
""",
            a=first,
            b=second,
        )
    )
    report = run_bitmap_probe(source)
    require_card_empty(report, card=2, empty=False)


def test_set_42_and_unpublished_above_2_pow_40_cardinality_two():
    high = unpublished_u64_f02(above=1 << 40)
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const high: u64 = __HIGH__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(42);
    _ = try bm.set(high);
    try emitJson(init, init.gpa,
        "{{\"empty\":{s},\"card\":{d}}}",
        .{ jsonBool(bm.isEmpty()), bm.getCardinality() },
    );
""",
            high=high,
        )
    )
    report = run_bitmap_probe(source)
    require_card_empty(report, card=2, empty=False)


# ---------------------------------------------------------------------------
# B. Non-empty extrema; max can fall back
# ---------------------------------------------------------------------------


def test_set_zero_makes_minimum_and_maximum_the_value_zero():
    source = wrap_enumeration_probe(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    const before_absent = extremaAbsent(&bm);
    _ = try bm.set(0);
    const min_is_0 = if (bm.minimum()) |m| m == 0 else false;
    const max_is_0 = if (bm.maximum()) |m| m == 0 else false;
    try emitJson(init, init.gpa,
        "{{\"before_absent\":{s},\"empty\":{s},\"card\":{d},\"min_is_0\":{s},\"max_is_0\":{s}}}",
        .{
            jsonBool(before_absent), jsonBool(bm.isEmpty()), bm.getCardinality(),
            jsonBool(min_is_0), jsonBool(max_is_0),
        },
    );
"""
    )
    report = run_bitmap_probe(source)
    require_true(report, "before_absent", "min_is_0", "max_is_0")
    require_card_empty(report, card=1, empty=False)


def test_two_unpublished_extrema_are_smallest_and_largest_regardless_of_insert_order():
    lo, hi = unpublished_extrema_pair()
    order = shuffle_not_sorted((lo, hi))
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const a: u64 = __A__;
    const b: u64 = __B__;
    const first: u64 = __FIRST__;
    const second: u64 = __SECOND__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(first);
    _ = try bm.set(second);
    try emitJson(init, init.gpa,
        "{{\"empty\":{s},\"card\":{d},\"extrema\":{s}}}",
        .{
            jsonBool(bm.isEmpty()), bm.getCardinality(),
            jsonBool(extremaEqual(&bm, a, b)),
        },
    );
""",
            a=lo,
            b=hi,
            first=order[0],
            second=order[1],
        )
    )
    report = run_bitmap_probe(source)
    require_card_empty(report, card=2, empty=False)
    require_true(report, "extrema")


def test_removing_current_maximum_leaves_maximum_as_largest_remaining():
    lo, hi = unpublished_extrema_pair()
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const a: u64 = __A__;
    const b: u64 = __B__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(a);
    _ = try bm.set(b);
    const before = extremaEqual(&bm, a, b);
    _ = bm.remove(b);
    try emitJson(init, init.gpa,
        "{{\"before\":{s},\"empty\":{s},\"card\":{d},\"after\":{s}}}",
        .{
            jsonBool(before), jsonBool(bm.isEmpty()), bm.getCardinality(),
            jsonBool(extremaEqual(&bm, a, a)),
        },
    );
""",
            a=lo,
            b=hi,
        )
    )
    report = run_bitmap_probe(source)
    require_true(report, "before", "after")
    require_card_empty(report, card=1, empty=False)


def test_zero_and_2_pow_32_minimum_zero_maximum_2_pow_32():
    source = wrap_enumeration_probe(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(0);
    _ = try bm.set(@as(u64, 1) << 32);
    try emitJson(init, init.gpa,
        "{{\"empty\":{s},\"card\":{d},\"extrema\":{s}}}",
        .{
            jsonBool(bm.isEmpty()), bm.getCardinality(),
            jsonBool(extremaEqual(&bm, 0, @as(u64, 1) << 32)),
        },
    );
"""
    )
    report = run_bitmap_probe(source)
    require_card_empty(report, card=2, empty=False)
    require_true(report, "extrema")


def test_after_removing_0_through_99_minimum_is_2_pow_16_not_absent_or_removed():
    run_len = unpublished_prefix_run_length()
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const run_len: u64 = __RUN_LEN__;
    const remain_max: u64 = (@as(u64, 1) << 16) + run_len - 1;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    var i: u64 = 0;
    while (i < 100) : (i += 1) {
        _ = try bm.set(i);
    }
    var j: u64 = 0;
    while (j < run_len) : (j += 1) {
        _ = try bm.set((@as(u64, 1) << 16) + j);
    }
    const before = extremaEqual(&bm, 0, remain_max);
    const before_empty = bm.isEmpty();
    i = 0;
    while (i < 100) : (i += 1) {
        _ = bm.remove(i);
    }
    const min_is_2p16 = if (bm.minimum()) |m| m == (@as(u64, 1) << 16) else false;
    const max_is_remain = if (bm.maximum()) |m| m == remain_max else false;
    const min_is_0 = if (bm.minimum()) |m| m == 0 else false;
    const min_is_99 = if (bm.minimum()) |m| m == 99 else false;
    const max_is_99 = if (bm.maximum()) |m| m == 99 else false;
    try emitJson(init, init.gpa,
        "{{\"before\":{s},\"before_empty\":{s},\"empty\":{s},\"card\":{d},\"min_is_2p16\":{s},\"max_is_remain\":{s},\"min_is_0\":{s},\"min_is_99\":{s},\"max_is_99\":{s}}}",
        .{
            jsonBool(before), jsonBool(before_empty),
            jsonBool(bm.isEmpty()), bm.getCardinality(),
            jsonBool(min_is_2p16), jsonBool(max_is_remain),
            jsonBool(min_is_0), jsonBool(min_is_99), jsonBool(max_is_99),
        },
    );
""",
            run_len=run_len,
        )
    )
    report = run_bitmap_probe(source)
    require_true(report, "before")
    require_false(report, "before_empty")
    require_card_empty(report, card=run_len, empty=False)
    require_true(report, "min_is_2p16", "max_is_remain")
    require_false(report, "min_is_0", "min_is_99", "max_is_99")


def test_after_emptying_unpublished_low_run_minimum_is_smallest_remaining():
    low_start, low_len, high_start, high_len = unpublished_low_high_runs()
    remain_max = high_start + high_len - 1
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const low_start: u64 = __LOW_START__;
    const low_len: u64 = __LOW_LEN__;
    const high_start: u64 = __HIGH_START__;
    const high_len: u64 = __HIGH_LEN__;
    const remain_max: u64 = __REMAIN_MAX__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    var i: u64 = 0;
    while (i < low_len) : (i += 1) {
        _ = try bm.set(low_start + i);
    }
    i = 0;
    while (i < high_len) : (i += 1) {
        _ = try bm.set(high_start + i);
    }
    const before = extremaEqual(&bm, low_start, remain_max);
    i = 0;
    while (i < low_len) : (i += 1) {
        _ = bm.remove(low_start + i);
    }
    try emitJson(init, init.gpa,
        "{{\"before\":{s},\"empty\":{s},\"card\":{d},\"after\":{s}}}",
        .{
            jsonBool(before), jsonBool(bm.isEmpty()), bm.getCardinality(),
            jsonBool(extremaEqual(&bm, high_start, remain_max)),
        },
    );
""",
            low_start=low_start,
            low_len=low_len,
            high_start=high_start,
            high_len=high_len,
            remain_max=remain_max,
        )
    )
    report = run_bitmap_probe(source)
    require_true(report, "before", "after")
    require_card_empty(report, card=high_len, empty=False)


def test_after_emptying_unpublished_high_run_maximum_is_largest_remaining():
    low_start, low_len, high_start, high_len = unpublished_low_high_runs()
    low_last = low_start + low_len - 1
    high_last = high_start + high_len - 1
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const low_start: u64 = __LOW_START__;
    const low_len: u64 = __LOW_LEN__;
    const high_start: u64 = __HIGH_START__;
    const high_len: u64 = __HIGH_LEN__;
    const low_last: u64 = __LOW_LAST__;
    const high_last: u64 = __HIGH_LAST__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    var i: u64 = 0;
    while (i < low_len) : (i += 1) {
        _ = try bm.set(low_start + i);
    }
    i = 0;
    while (i < high_len) : (i += 1) {
        _ = try bm.set(high_start + i);
    }
    const before = extremaEqual(&bm, low_start, high_last);
    i = 0;
    while (i < high_len) : (i += 1) {
        _ = bm.remove(high_start + i);
    }
    const max_is_high = if (bm.maximum()) |m| m == high_last else false;
    try emitJson(init, init.gpa,
        "{{\"before\":{s},\"empty\":{s},\"card\":{d},\"after\":{s},\"max_is_high\":{s}}}",
        .{
            jsonBool(before), jsonBool(bm.isEmpty()), bm.getCardinality(),
            jsonBool(extremaEqual(&bm, low_start, low_last)),
            jsonBool(max_is_high),
        },
    );
""",
            low_start=low_start,
            low_len=low_len,
            high_start=high_start,
            high_len=high_len,
            low_last=low_last,
            high_last=high_last,
        )
    )
    report = run_bitmap_probe(source)
    require_true(report, "before", "after")
    require_false(report, "max_is_high")
    require_card_empty(report, card=low_len, empty=False)


# ---------------------------------------------------------------------------
# C. Iterator: strictly ascending, 0 is a real value, exhaustion stays
# ---------------------------------------------------------------------------


def test_empty_iterator_exhausted_on_first_and_next_pull():
    source = wrap_enumeration_probe(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    var it = bm.iterator();
    const first = pullAbsent(&it);
    const second = pullAbsent(&it);
    try emitJson(init, init.gpa,
        "{{\"first\":{s},\"second\":{s}}}",
        .{ jsonBool(first), jsonBool(second) },
    );
"""
    )
    report = run_bitmap_probe(source)
    require_true(report, "first", "second")


def test_bitmap_containing_only_zero_yields_zero_then_exhaustion_twice():
    source = wrap_enumeration_probe(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(0);
    var it = bm.iterator();
    const first = yieldedEquals(&it, 0);
    const ex1 = pullAbsent(&it);
    const ex2 = pullAbsent(&it);
    try emitJson(init, init.gpa,
        "{{\"first\":{s},\"ex1\":{s},\"ex2\":{s}}}",
        .{ jsonBool(first), jsonBool(ex1), jsonBool(ex2) },
    );
"""
    )
    report = run_bitmap_probe(source)
    require_true(report, "first", "ex1", "ex2")


def test_zero_and_2_pow_32_iterator_yields_zero_then_2_pow_32_then_exhaustion():
    source = wrap_enumeration_probe(
        r"""
    const hi: u64 = @as(u64, 1) << 32;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(0);
    _ = try bm.set(hi);
    var it = bm.iterator();
    const y0 = yieldedEquals(&it, 0);
    const y1 = yieldedEquals(&it, hi);
    const ex1 = pullAbsent(&it);
    const ex2 = pullAbsent(&it);
    try emitJson(init, init.gpa,
        "{{\"y0\":{s},\"y1\":{s},\"ex1\":{s},\"ex2\":{s}}}",
        .{ jsonBool(y0), jsonBool(y1), jsonBool(ex1), jsonBool(ex2) },
    );
"""
    )
    report = run_bitmap_probe(source)
    require_true(report, "y0", "y1", "ex1", "ex2")


def test_zero_and_unpublished_above_2_pow_32_iterator_does_not_stop_at_zero():
    high = unpublished_u64_f03()
    if high <= (1 << 32):
        raise HarnessError("unpublished high is not above 2^32")
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const high: u64 = __HIGH__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(0);
    _ = try bm.set(high);
    var it = bm.iterator();
    const y0 = yieldedEquals(&it, 0);
    const y1 = yieldedEquals(&it, high);
    const ex1 = pullAbsent(&it);
    try emitJson(init, init.gpa,
        "{{\"y0\":{s},\"y1\":{s},\"ex1\":{s}}}",
        .{ jsonBool(y0), jsonBool(y1), jsonBool(ex1) },
    );
""",
            high=high,
        )
    )
    report = run_bitmap_probe(source)
    require_true(report, "y0", "y1", "ex1")


def test_dense_run_0_through_4999_iterator_full_sequence_then_exhaustion():
    source = wrap_enumeration_probe(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    var i: u64 = 0;
    while (i < 5000) : (i += 1) {
        _ = try bm.set(i);
    }
    var it = bm.iterator();
    var seq_ok = true;
    i = 0;
    while (i < 5000) : (i += 1) {
        const got = it.next() orelse {
            seq_ok = false;
            break;
        };
        if (got != i) seq_ok = false;
    }
    const ex1 = pullAbsent(&it);
    const ex2 = pullAbsent(&it);
    try emitJson(init, init.gpa,
        "{{\"empty\":{s},\"card\":{d},\"seq_ok\":{s},\"ex1\":{s},\"ex2\":{s}}}",
        .{
            jsonBool(bm.isEmpty()), bm.getCardinality(),
            jsonBool(seq_ok), jsonBool(ex1), jsonBool(ex2),
        },
    );
"""
    )
    report = run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
    require_card_empty(report, card=5000, empty=False)
    require_true(report, "seq_ok", "ex1", "ex2")


def test_dense_run_unpublished_thousands_yields_zero_first_then_consecutive():
    length = unpublished_thousands_length()
    if length == 5000:
        raise HarnessError("unpublished thousands length collided with 5000")
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const n: u64 = __N__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    var i: u64 = 0;
    while (i < n) : (i += 1) {
        _ = try bm.set(i);
    }
    var it = bm.iterator();
    const first = yieldedEquals(&it, 0);
    var mid_ok = true;
    i = 1;
    while (i + 1 < n) : (i += 1) {
        const got = it.next() orelse {
            mid_ok = false;
            break;
        };
        if (got != i) mid_ok = false;
    }
    const last = yieldedEquals(&it, n - 1);
    const ex1 = pullAbsent(&it);
    try emitJson(init, init.gpa,
        "{{\"first\":{s},\"mid_ok\":{s},\"last\":{s},\"ex1\":{s},\"card\":{d}}}",
        .{
            jsonBool(first), jsonBool(mid_ok), jsonBool(last), jsonBool(ex1),
            bm.getCardinality(),
        },
    );
""",
            n=length,
        )
    )
    report = run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
    require_true(report, "first", "mid_ok", "last", "ex1")
    assert require_int_field(report, "card") == length


def test_nine_boundary_values_shuffled_iterator_strictly_ascending_each_once():
    named = nine_boundary_values()
    order = shuffle_not_sorted(named)
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const vals = [_]u64{ __VALS__ };
    const max_u64: u64 = std.math.maxInt(u64);
    const want = [_]u64{
        0,
        65535,
        @as(u64, 1) << 16,
        (@as(u64, 1) << 32) + 5,
        (@as(u64, 1) << 32) + 65535,
        (@as(u64, 1) << 48) + 7,
        (@as(u64, 1) << 48) + (@as(u64, 1) << 32),
        max_u64 - 1,
        max_u64,
    };
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    const before0 = bm.contains(0);
    const before_mid = bm.contains((@as(u64, 1) << 32) + 5);
    const before_max = bm.contains(max_u64);
    for (vals) |v| {
        _ = try bm.set(v);
    }
    var it = bm.iterator();
    var seq_ok = true;
    for (want) |w| {
        const got = it.next() orelse {
            seq_ok = false;
            break;
        };
        if (got != w) seq_ok = false;
    }
    const after = pullAbsent(&it);
    const again = pullAbsent(&it);
    try emitJson(init, init.gpa,
        "{{\"before0\":{s},\"before_mid\":{s},\"before_max\":{s},\"seq_ok\":{s},\"after\":{s},\"again\":{s},\"empty\":{s},\"card\":{d}}}",
        .{
            jsonBool(before0), jsonBool(before_mid), jsonBool(before_max),
            jsonBool(seq_ok), jsonBool(after), jsonBool(again),
            jsonBool(bm.isEmpty()), bm.getCardinality(),
        },
    );
""",
            vals=zig_u64_list(order),
        )
    )
    report = run_bitmap_probe(source)
    require_false(report, "before0", "before_mid", "before_max")
    require_true(report, "seq_ok", "after", "again")
    require_card_empty(report, card=9, empty=False)


def test_iterate_42_and_unpublished_above_2_pow_40_ascending():
    high = unpublished_u64_f02(above=1 << 40)
    order = shuffle_not_sorted((42, high))
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const high: u64 = __HIGH__;
    const first: u64 = __FIRST__;
    const second: u64 = __SECOND__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(first);
    _ = try bm.set(second);
    var it = bm.iterator();
    const y0 = yieldedEquals(&it, 42);
    const y1 = yieldedEquals(&it, high);
    const ex1 = pullAbsent(&it);
    try emitJson(init, init.gpa,
        "{{\"y0\":{s},\"y1\":{s},\"ex1\":{s}}}",
        .{ jsonBool(y0), jsonBool(y1), jsonBool(ex1) },
    );
""",
            high=high,
            first=order[0],
            second=order[1],
        )
    )
    report = run_bitmap_probe(source)
    require_true(report, "y0", "y1", "ex1")


# ---------------------------------------------------------------------------
# D. Removed values and emptied prefixes do not appear
# ---------------------------------------------------------------------------


def test_after_set_5_2_pow_16_2x_2_pow_16_remove_2_pow_16_iterator_skips_removed():
    order = shuffle_not_sorted((5, 1 << 16, 2 << 16))
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const vals = [_]u64{ __VALS__ };
    const mid: u64 = @as(u64, 1) << 16;
    const hi: u64 = @as(u64, 2) << 16;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    for (vals) |v| {
        _ = try bm.set(v);
    }
    const before = drainEquals(&bm, &.{ 5, mid, hi });
    _ = bm.remove(mid);
    const after = drainEquals(&bm, &.{ 5, hi });
    try emitJson(init, init.gpa,
        "{{\"before\":{s},\"after\":{s},\"empty\":{s},\"card\":{d},\"extrema\":{s}}}",
        .{
            jsonBool(before), jsonBool(after),
            jsonBool(bm.isEmpty()), bm.getCardinality(),
            jsonBool(extremaEqual(&bm, 5, hi)),
        },
    );
""",
            vals=zig_u64_list(order),
        )
    )
    report = run_bitmap_probe(source)
    require_true(report, "before", "after", "extrema")
    require_card_empty(report, card=2, empty=False)


def test_unpublished_three_prefixes_remove_middle_omits_removed_and_empty_prefix():
    lo, mid, hi = unpublished_three_prefix_values()
    order = shuffle_not_sorted((lo, mid, hi))
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const vals = [_]u64{ __VALS__ };
    const a: u64 = __A__;
    const b: u64 = __B__;
    const c: u64 = __C__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    for (vals) |v| {
        _ = try bm.set(v);
    }
    const before = drainEquals(&bm, &.{ a, b, c });
    _ = bm.remove(b);
    const after = drainEquals(&bm, &.{ a, c });
    try emitJson(init, init.gpa,
        "{{\"before\":{s},\"after\":{s},\"empty\":{s},\"card\":{d}}}",
        .{
            jsonBool(before), jsonBool(after),
            jsonBool(bm.isEmpty()), bm.getCardinality(),
        },
    );
""",
            vals=zig_u64_list(order),
            a=lo,
            b=mid,
            c=hi,
        )
    )
    report = run_bitmap_probe(source)
    require_true(report, "before", "after")
    require_card_empty(report, card=2, empty=False)


def test_after_removing_0_through_99_iterator_starts_at_2_pow_16():
    run_len = unpublished_prefix_run_length()
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const run_len: u64 = __RUN_LEN__;
    const remain_max: u64 = (@as(u64, 1) << 16) + run_len - 1;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    var i: u64 = 0;
    while (i < 100) : (i += 1) {
        _ = try bm.set(i);
    }
    var j: u64 = 0;
    while (j < run_len) : (j += 1) {
        _ = try bm.set((@as(u64, 1) << 16) + j);
    }
    i = 0;
    while (i < 100) : (i += 1) {
        _ = bm.remove(i);
    }
    var it = bm.iterator();
    const first = yieldedEquals(&it, @as(u64, 1) << 16);
    var mid_ok = true;
    var n: u64 = 1;
    while (n + 1 < run_len) : (n += 1) {
        const got = it.next() orelse {
            mid_ok = false;
            break;
        };
        if (got != (@as(u64, 1) << 16) + n) mid_ok = false;
    }
    const last = if (run_len == 1) first else yieldedEquals(&it, remain_max);
    const ex1 = pullAbsent(&it);
    const saw_0 = blk: {
        var walk = bm.iterator();
        while (walk.next()) |v| {
            if (v == 0 or v == 99) break :blk true;
        }
        break :blk false;
    };
    try emitJson(init, init.gpa,
        "{{\"first\":{s},\"mid_ok\":{s},\"last\":{s},\"ex1\":{s},\"saw_0\":{s},\"empty\":{s},\"card\":{d}}}",
        .{
            jsonBool(first), jsonBool(mid_ok), jsonBool(last), jsonBool(ex1),
            jsonBool(saw_0), jsonBool(bm.isEmpty()), bm.getCardinality(),
        },
    );
""",
            run_len=run_len,
        )
    )
    report = run_bitmap_probe(source)
    require_true(report, "first", "mid_ok", "last", "ex1")
    require_false(report, "saw_0")
    require_card_empty(report, card=run_len, empty=False)


def test_iterator_omits_removed_interior_of_dense_0_through_4999():
    hole = unpublished_dense_interior()
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const hole: u64 = __HOLE__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    var i: u64 = 0;
    while (i < 5000) : (i += 1) {
        _ = try bm.set(i);
    }
    const before = blk: {
        var it = bm.iterator();
        var k: u64 = 0;
        while (k < 5000) : (k += 1) {
            const got = it.next() orelse break :blk false;
            if (got != k) break :blk false;
        }
        break :blk true;
    };
    const hole_before = blk: {
        var it = bm.iterator();
        while (it.next()) |v| {
            if (v == hole) break :blk true;
        }
        break :blk false;
    };
    _ = bm.remove(hole);
    var it = bm.iterator();
    const first = yieldedEquals(&it, 0);
    const seq_ok = drainRunSkipping(&bm, 0, 4999, hole);
    const adjacent = neighboursAdjacentAfterHole(&bm, hole);
    const last_ok = blk: {
        var walk = bm.iterator();
        var last: ?u64 = null;
        var n: u64 = 0;
        while (walk.next()) |v| {
            last = v;
            n += 1;
        }
        break :blk n == 4999 and last == 4999;
    };
    const ex1 = blk: {
        var walk = bm.iterator();
        var n: u64 = 0;
        while (walk.next()) |_| n += 1;
        break :blk pullAbsent(&walk);
    };
    try emitJson(init, init.gpa,
        "{{\"before\":{s},\"hole_before\":{s},\"first\":{s},\"seq_ok\":{s},\"adjacent\":{s},\"last_ok\":{s},\"ex1\":{s},\"empty\":{s},\"card\":{d}}}",
        .{
            jsonBool(before), jsonBool(hole_before), jsonBool(first),
            jsonBool(seq_ok), jsonBool(adjacent), jsonBool(last_ok),
            jsonBool(ex1), jsonBool(bm.isEmpty()), bm.getCardinality(),
        },
    );
""",
            hole=hole,
        )
    )
    report = run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
    require_true(
        report,
        "before",
        "hole_before",
        "first",
        "seq_ok",
        "adjacent",
        "last_ok",
        "ex1",
    )
    require_card_empty(report, card=4999, empty=False)


def test_after_emptying_unpublished_high_run_iterator_ends_at_remaining_maximum():
    low_start, low_len, high_start, high_len = unpublished_low_high_runs()
    high_last = high_start + high_len - 1
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const low_start: u64 = __LOW_START__;
    const low_len: u64 = __LOW_LEN__;
    const high_start: u64 = __HIGH_START__;
    const high_len: u64 = __HIGH_LEN__;
    const high_last: u64 = __HIGH_LAST__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    var i: u64 = 0;
    while (i < low_len) : (i += 1) {
        _ = try bm.set(low_start + i);
    }
    i = 0;
    while (i < high_len) : (i += 1) {
        _ = try bm.set(high_start + i);
    }
    const high_before = blk: {
        var it = bm.iterator();
        while (it.next()) |v| {
            if (v == high_last) break :blk true;
        }
        break :blk false;
    };
    i = 0;
    while (i < high_len) : (i += 1) {
        _ = bm.remove(high_start + i);
    }
    const after = drainRunFrom(&bm, low_start, low_len);
    const saw_high = blk: {
        var it = bm.iterator();
        while (it.next()) |v| {
            if (v >= high_start and v < high_start + high_len) break :blk true;
        }
        break :blk false;
    };
    try emitJson(init, init.gpa,
        "{{\"high_before\":{s},\"after\":{s},\"saw_high\":{s},\"empty\":{s},\"card\":{d}}}",
        .{
            jsonBool(high_before), jsonBool(after), jsonBool(saw_high),
            jsonBool(bm.isEmpty()), bm.getCardinality(),
        },
    );
""",
            low_start=low_start,
            low_len=low_len,
            high_start=high_start,
            high_len=high_len,
            high_last=high_last,
        )
    )
    report = run_bitmap_probe(source)
    require_true(report, "high_before", "after")
    require_false(report, "saw_high")
    require_card_empty(report, card=low_len, empty=False)


# ---------------------------------------------------------------------------
# E. Allocated array matches a full iterator drain
# ---------------------------------------------------------------------------


def test_allocated_array_empty_has_length_zero():
    source = wrap_enumeration_probe(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    const arr = try bm.toArray(allocator);
    defer allocator.free(arr);
    try emitJson(init, init.gpa,
        "{{\"len\":{d}}}",
        .{ arr.len },
    );
"""
    )
    report = run_bitmap_probe(source)
    assert require_int_field(report, "len") == 0


def test_allocated_array_of_zero_and_2_pow_32_matches_iterator():
    source = wrap_enumeration_probe(
        r"""
    const hi: u64 = @as(u64, 1) << 32;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(0);
    _ = try bm.set(hi);
    const arr = try bm.toArray(allocator);
    defer allocator.free(arr);
    const match = arrayEqualsDrain(&bm, arr);
    const want = arr.len == 2 and arr[0] == 0 and arr[1] == hi;
    try emitJson(init, init.gpa,
        "{{\"empty\":{s},\"card\":{d},\"len\":{d},\"match\":{s},\"want\":{s}}}",
        .{
            jsonBool(bm.isEmpty()), bm.getCardinality(), arr.len,
            jsonBool(match), jsonBool(want),
        },
    );
"""
    )
    report = run_bitmap_probe(source)
    require_card_empty(report, card=2, empty=False)
    assert require_int_field(report, "len") == 2
    require_true(report, "match", "want")


def test_allocated_array_of_shuffled_nine_is_sorted_unique():
    named = nine_boundary_values()
    order = shuffle_not_sorted(named)
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const vals = [_]u64{ __VALS__ };
    const max_u64: u64 = std.math.maxInt(u64);
    const want = [_]u64{
        0,
        65535,
        @as(u64, 1) << 16,
        (@as(u64, 1) << 32) + 5,
        (@as(u64, 1) << 32) + 65535,
        (@as(u64, 1) << 48) + 7,
        (@as(u64, 1) << 48) + (@as(u64, 1) << 32),
        max_u64 - 1,
        max_u64,
    };
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    for (vals) |v| {
        _ = try bm.set(v);
    }
    const arr = try bm.toArray(allocator);
    defer allocator.free(arr);
    const match = arrayEqualsDrain(&bm, arr);
    var want_ok = arr.len == 9;
    if (want_ok) {
        for (arr, want) |a, w| {
            if (a != w) want_ok = false;
        }
    }
    try emitJson(init, init.gpa,
        "{{\"len\":{d},\"match\":{s},\"want_ok\":{s},\"card\":{d}}}",
        .{ arr.len, jsonBool(match), jsonBool(want_ok), bm.getCardinality() },
    );
""",
            vals=zig_u64_list(order),
        )
    )
    report = run_bitmap_probe(source)
    assert require_int_field(report, "len") == 9
    assert require_int_field(report, "card") == 9
    require_true(report, "match", "want_ok")


def test_allocated_array_mixed_dense_and_scattered_matches_sorted_unique_newly_set():
    dense_len = unpublished_hundreds_length()
    s1, s2 = unpublished_scattered_pair()
    want = independent_sorted_unique_dense_and_scattered(dense_len, s1, s2)
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const dense_len: u64 = __DENSE_LEN__;
    const s1: u64 = __S1__;
    const s2: u64 = __S2__;
    const want = [_]u64{ __WANT__ };
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    var i: u64 = 0;
    while (i < dense_len) : (i += 1) {
        _ = try bm.set(i);
    }
    _ = try bm.set(s1);
    _ = try bm.set(s2);
    const dup = try bm.set(s1);
    const arr = try bm.toArray(allocator);
    defer allocator.free(arr);
    const match = arrayEqualsDrain(&bm, arr);
    var want_ok = arr.len == want.len;
    if (want_ok) {
        for (arr, want) |a, w| {
            if (a != w) want_ok = false;
        }
    }
    try emitJson(init, init.gpa,
        "{{\"dup\":{s},\"len\":{d},\"card\":{d},\"match\":{s},\"want_ok\":{s}}}",
        .{
            jsonBool(dup), arr.len, bm.getCardinality(),
            jsonBool(match), jsonBool(want_ok),
        },
    );
""",
            dense_len=dense_len,
            s1=s1,
            s2=s2,
            want=zig_u64_list(want),
        )
    )
    report = run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
    require_false(report, "dup")
    require_allocated_matches_independent(report, want)
    require_true(report, "match")


def test_allocated_array_after_remove_2_pow_16_matches_post_remove_iterator():
    order = shuffle_not_sorted((5, 1 << 16, 2 << 16))
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const vals = [_]u64{ __VALS__ };
    const mid: u64 = @as(u64, 1) << 16;
    const hi: u64 = @as(u64, 2) << 16;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    for (vals) |v| {
        _ = try bm.set(v);
    }
    _ = bm.remove(mid);
    const arr = try bm.toArray(allocator);
    defer allocator.free(arr);
    const match = arrayEqualsDrain(&bm, arr);
    const want = arr.len == 2 and arr[0] == 5 and arr[1] == hi;
    const has_mid = blk: {
        for (arr) |v| {
            if (v == mid) break :blk true;
        }
        break :blk false;
    };
    try emitJson(init, init.gpa,
        "{{\"len\":{d},\"card\":{d},\"match\":{s},\"want\":{s},\"has_mid\":{s}}}",
        .{
            arr.len, bm.getCardinality(),
            jsonBool(match), jsonBool(want), jsonBool(has_mid),
        },
    );
""",
            vals=zig_u64_list(order),
        )
    )
    report = run_bitmap_probe(source)
    assert require_int_field(report, "len") == 2
    assert require_int_field(report, "card") == 2
    require_true(report, "match", "want")
    require_false(report, "has_mid")


def test_allocated_array_of_0_through_4999_matches_iterator():
    source = wrap_enumeration_probe(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    var i: u64 = 0;
    while (i < 5000) : (i += 1) {
        _ = try bm.set(i);
    }
    const arr = try bm.toArray(allocator);
    defer allocator.free(arr);
    const match = arrayEqualsDrain(&bm, arr);
    var item_ok = arr.len == 5000;
    if (item_ok) {
        i = 0;
        while (i < 5000) : (i += 1) {
            if (arr[i] != i) item_ok = false;
        }
    }
    try emitJson(init, init.gpa,
        "{{\"len\":{d},\"card\":{d},\"match\":{s},\"item_ok\":{s}}}",
        .{ arr.len, bm.getCardinality(), jsonBool(match), jsonBool(item_ok) },
    );
"""
    )
    report = run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
    assert require_int_field(report, "len") == 5000
    assert require_int_field(report, "card") == 5000
    require_true(report, "match", "item_ok")


# ---------------------------------------------------------------------------
# F. Destination write: prefix matches iterator, suffix stays sentinel
# ---------------------------------------------------------------------------


def test_empty_destination_length_zero_writes_nothing_into_sentinel_buffer():
    present: set[int] = set()
    sentinel = sentinel_absent_from(present)
    extra = unused_suffix_slots()
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const sentinel: u64 = __SENTINEL__;
    const extra: usize = __EXTRA__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    const buf = try allocator.alloc(u64, extra);
    defer allocator.free(buf);
    fillSentinel(buf, sentinel);
    const dest = buf[0..0];
    bm.toArrayInto(dest);
    try emitJson(init, init.gpa,
        "{{\"len\":{d},\"untouched\":{s}}}",
        .{ dest.len, jsonBool(suffixUntouched(buf, 0, sentinel)) },
    );
""",
            sentinel=sentinel,
            extra=extra,
        )
    )
    report = run_bitmap_probe(source)
    assert require_int_field(report, "len") == 0
    require_true(report, "untouched")


def test_destination_write_zero_and_2_pow_32_leaves_sentinel_suffix():
    sentinel = sentinel_absent_from({0, 1 << 32})
    extra = unused_suffix_slots()
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const hi: u64 = @as(u64, 1) << 32;
    const sentinel: u64 = __SENTINEL__;
    const extra: usize = __EXTRA__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(0);
    _ = try bm.set(hi);
    const baseline = drainEquals(&bm, &.{ 0, hi });
    const card: usize = @intCast(bm.getCardinality());
    const buf = try allocator.alloc(u64, card + extra);
    defer allocator.free(buf);
    fillSentinel(buf, sentinel);
    bm.toArrayInto(buf[0..card]);
    const prefix = arrayEqualsDrain(&bm, buf[0..card]);
    const suffix = suffixUntouched(buf, card, sentinel);
    const want = buf[0] == 0 and buf[1] == hi;
    try emitJson(init, init.gpa,
        "{{\"baseline\":{s},\"prefix\":{s},\"suffix\":{s},\"want\":{s},\"card\":{d}}}",
        .{
            jsonBool(baseline), jsonBool(prefix), jsonBool(suffix),
            jsonBool(want), bm.getCardinality(),
        },
    );
""",
            sentinel=sentinel,
            extra=extra,
        )
    )
    report = run_bitmap_probe(source)
    require_true(report, "baseline", "prefix", "suffix", "want")
    assert require_int_field(report, "card") == 2


def test_destination_write_mixed_dense_scattered_leaves_sentinel_suffix():
    dense_len = unpublished_hundreds_length()
    s1, s2 = unpublished_scattered_pair()
    want = independent_sorted_unique_dense_and_scattered(dense_len, s1, s2)
    sentinel = sentinel_absent_from(want)
    extra = unused_suffix_slots()
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const dense_len: u64 = __DENSE_LEN__;
    const s1: u64 = __S1__;
    const s2: u64 = __S2__;
    const sentinel: u64 = __SENTINEL__;
    const extra: usize = __EXTRA__;
    const want = [_]u64{ __WANT__ };
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    var i: u64 = 0;
    while (i < dense_len) : (i += 1) {
        _ = try bm.set(i);
    }
    _ = try bm.set(s1);
    _ = try bm.set(s2);
    _ = try bm.set(s1);
    const dest_len: usize = want.len;
    const arr = try bm.toArray(allocator);
    defer allocator.free(arr);
    const baseline = arrayEqualsDrain(&bm, arr);
    const buf = try allocator.alloc(u64, dest_len + extra);
    defer allocator.free(buf);
    fillSentinel(buf, sentinel);
    bm.toArrayInto(buf[0..dest_len]);
    const prefix = arrayEqualsDrain(&bm, buf[0..dest_len]);
    var same = arr.len == dest_len;
    if (same) {
        for (arr, buf[0..dest_len]) |a, d| {
            if (a != d) same = false;
        }
    }
    var want_ok = true;
    for (buf[0..dest_len], want) |d, w| {
        if (d != w) want_ok = false;
    }
    const suffix = suffixUntouched(buf, dest_len, sentinel);
    try emitJson(init, init.gpa,
        "{{\"baseline\":{s},\"prefix\":{s},\"same\":{s},\"want_ok\":{s},\"suffix\":{s},\"card\":{d}}}",
        .{
            jsonBool(baseline), jsonBool(prefix), jsonBool(same),
            jsonBool(want_ok), jsonBool(suffix), bm.getCardinality(),
        },
    );
""",
            dense_len=dense_len,
            s1=s1,
            s2=s2,
            sentinel=sentinel,
            extra=extra,
            want=zig_u64_list(want),
        )
    )
    report = run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
    require_true(report, "baseline", "prefix", "same")
    require_destination_matches_independent(report, want)


def test_destination_write_shuffled_nine_matches_iterator_leaves_sentinel_suffix():
    named = nine_boundary_values()
    order = shuffle_not_sorted(named)
    sentinel = sentinel_absent_from(named)
    extra = unused_suffix_slots()
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const vals = [_]u64{ __VALS__ };
    const sentinel: u64 = __SENTINEL__;
    const extra: usize = __EXTRA__;
    const max_u64: u64 = std.math.maxInt(u64);
    const want = [_]u64{
        0,
        65535,
        @as(u64, 1) << 16,
        (@as(u64, 1) << 32) + 5,
        (@as(u64, 1) << 32) + 65535,
        (@as(u64, 1) << 48) + 7,
        (@as(u64, 1) << 48) + (@as(u64, 1) << 32),
        max_u64 - 1,
        max_u64,
    };
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    for (vals) |v| {
        _ = try bm.set(v);
    }
    const baseline = drainEquals(&bm, &want);
    const card: usize = @intCast(bm.getCardinality());
    const buf = try allocator.alloc(u64, card + extra);
    defer allocator.free(buf);
    fillSentinel(buf, sentinel);
    bm.toArrayInto(buf[0..card]);
    const prefix = arrayEqualsDrain(&bm, buf[0..card]);
    var want_ok = card == 9;
    if (want_ok) {
        for (buf[0..card], want) |d, w| {
            if (d != w) want_ok = false;
        }
    }
    const suffix = suffixUntouched(buf, card, sentinel);
    try emitJson(init, init.gpa,
        "{{\"baseline\":{s},\"prefix\":{s},\"want_ok\":{s},\"suffix\":{s}}}",
        .{
            jsonBool(baseline), jsonBool(prefix), jsonBool(want_ok),
            jsonBool(suffix),
        },
    );
""",
            vals=zig_u64_list(order),
            sentinel=sentinel,
            extra=extra,
        )
    )
    report = run_bitmap_probe(source)
    require_true(report, "baseline", "prefix", "want_ok", "suffix")


def test_destination_write_after_remove_2_pow_16_matches_iterator_leaves_sentinel_suffix():
    order = shuffle_not_sorted((5, 1 << 16, 2 << 16))
    sentinel = sentinel_absent_from({5, 1 << 16, 2 << 16})
    extra = unused_suffix_slots()
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const vals = [_]u64{ __VALS__ };
    const mid: u64 = @as(u64, 1) << 16;
    const hi: u64 = @as(u64, 2) << 16;
    const sentinel: u64 = __SENTINEL__;
    const extra: usize = __EXTRA__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    for (vals) |v| {
        _ = try bm.set(v);
    }
    _ = bm.remove(mid);
    const baseline = drainEquals(&bm, &.{ 5, hi });
    const card: usize = @intCast(bm.getCardinality());
    const buf = try allocator.alloc(u64, card + extra);
    defer allocator.free(buf);
    fillSentinel(buf, sentinel);
    bm.toArrayInto(buf[0..card]);
    const prefix = arrayEqualsDrain(&bm, buf[0..card]);
    const want = card == 2 and buf[0] == 5 and buf[1] == hi;
    const has_mid = buf[0] == mid or (card > 1 and buf[1] == mid);
    const suffix = suffixUntouched(buf, card, sentinel);
    try emitJson(init, init.gpa,
        "{{\"baseline\":{s},\"prefix\":{s},\"want\":{s},\"has_mid\":{s},\"suffix\":{s}}}",
        .{
            jsonBool(baseline), jsonBool(prefix), jsonBool(want),
            jsonBool(has_mid), jsonBool(suffix),
        },
    );
""",
            vals=zig_u64_list(order),
            sentinel=sentinel,
            extra=extra,
        )
    )
    report = run_bitmap_probe(source)
    require_true(report, "baseline", "prefix", "want", "suffix")
    require_false(report, "has_mid")


def test_destination_write_0_through_4999_leaves_sentinel_suffix():
    sentinel = sentinel_absent_from(set(range(5000)))
    extra = unused_suffix_slots()
    source = wrap_enumeration_probe(
        fill_u64(
            r"""
    const sentinel: u64 = __SENTINEL__;
    const extra: usize = __EXTRA__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    var i: u64 = 0;
    while (i < 5000) : (i += 1) {
        _ = try bm.set(i);
    }
    const card: usize = @intCast(bm.getCardinality());
    const buf = try allocator.alloc(u64, card + extra);
    defer allocator.free(buf);
    fillSentinel(buf, sentinel);
    bm.toArrayInto(buf[0..card]);
    const prefix = arrayEqualsDrain(&bm, buf[0..card]);
    var item_ok = card == 5000;
    if (item_ok) {
        i = 0;
        while (i < 5000) : (i += 1) {
            if (buf[i] != i) item_ok = false;
        }
    }
    const suffix = suffixUntouched(buf, card, sentinel);
    try emitJson(init, init.gpa,
        "{{\"prefix\":{s},\"item_ok\":{s},\"suffix\":{s},\"card\":{d}}}",
        .{
            jsonBool(prefix), jsonBool(item_ok), jsonBool(suffix),
            bm.getCardinality(),
        },
    );
""",
            sentinel=sentinel,
            extra=extra,
        )
    )
    report = run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
    require_true(report, "prefix", "item_ok", "suffix")
    assert require_int_field(report, "card") == 5000


# ---------------------------------------------------------------------------
# G. No file or network I/O on query / iterate / dump paths
# ---------------------------------------------------------------------------


def test_cardinality_extrema_enumeration_write_no_files():
    s1, s2 = unpublished_scattered_pair()
    dense = wrap_enumeration_probe(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    var i: u64 = 0;
    while (i < 5000) : (i += 1) {
        _ = try bm.set(i);
    }
    var it = bm.iterator();
    while (it.next()) |_| {}
    const arr = try bm.toArray(allocator);
    defer allocator.free(arr);
    const dest = try allocator.alloc(u64, arr.len + 4);
    defer allocator.free(dest);
    fillSentinel(dest, 1);
    bm.toArrayInto(dest[0..arr.len]);
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
"""
    )
    mixed = wrap_enumeration_probe(
        fill_u64(
            r"""
    const s1: u64 = __S1__;
    const s2: u64 = __S2__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    var i: u64 = 0;
    while (i < 300) : (i += 1) {
        _ = try bm.set(i);
    }
    _ = try bm.set(s1);
    _ = try bm.set(s2);
    const arr = try bm.toArray(allocator);
    defer allocator.free(arr);
    const dest = try allocator.alloc(u64, arr.len + 4);
    defer allocator.free(dest);
    fillSentinel(dest, 1);
    bm.toArrayInto(dest[0..arr.len]);
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
""",
            s1=s1,
            s2=s2,
        )
    )

    with workspace() as ws:
        tmp = ws.mkdir("tmp")
        ws.env["TMPDIR"] = str(tmp)
        ws.env["TEMP"] = str(tmp)
        ws.env["TMP"] = str(tmp)
        home_file = (Path(ws.home) / "home_side.txt").resolve()
        tmp_file = (tmp / "tmp_side.txt").resolve()
        roots = (ws.path, ws.home, tmp)

        compile_probe_or_raise(
            ws, dense, relpath="dense.zig", output="dense", timeout=LARGE_PROBE_TIMEOUT
        )
        compile_probe_or_raise(
            ws, mixed, relpath="mixed.zig", output="mixed", timeout=LARGE_PROBE_TIMEOUT
        )

        before_dense = set()
        for root in roots:
            before_dense |= _walk_regular_files(root)
        run_dense = ws.run_command(
            [str(ws.resolve("dense"))], timeout=LARGE_PROBE_TIMEOUT
        )
        if run_dense.returncode != 0:
            raise HarnessError(
                f"dense I/O probe exited {run_dense.returncode}\n{run_dense.stderr_text}"
            )
        created_dense = product_created_files(before=before_dense, roots=roots)
        assert created_dense == set(), f"dense enumeration wrote files: {created_dense}"

        before_mixed = set()
        for root in roots:
            before_mixed |= _walk_regular_files(root)
        run_mixed = ws.run_command(
            [str(ws.resolve("mixed"))], timeout=LARGE_PROBE_TIMEOUT
        )
        if run_mixed.returncode != 0:
            raise HarnessError(
                f"mixed I/O probe exited {run_mixed.returncode}\n{run_mixed.stderr_text}"
            )
        created_mixed = product_created_files(before=before_mixed, roots=roots)
        assert created_mixed == set(), f"mixed enumeration wrote files: {created_mixed}"

        vandal = wrap_probe_body(
            fill_u64(
                r"""
    var cwd = std.Io.Dir.cwd();
    var f1 = try cwd.createFile(init.io, "cwd_side.txt", .{});
    f1.close(init.io);
    var f2 = try std.Io.Dir.createFileAbsolute(init.io, "__HOME_FILE__", .{});
    f2.close(init.io);
    var f3 = try std.Io.Dir.createFileAbsolute(init.io, "__TMP_FILE__", .{});
    f3.close(init.io);
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
""",
                home_file=str(home_file),
                tmp_file=str(tmp_file),
            )
        )
        compile_probe_or_raise(
            ws, vandal, relpath="vandal.zig", output="vandal", timeout=DEFAULT_TIMEOUT
        )
        before_v = set()
        for root in roots:
            before_v |= _walk_regular_files(root)
        run_v = ws.run_command([str(ws.resolve("vandal"))], timeout=DEFAULT_TIMEOUT)
        if run_v.returncode != 0:
            raise HarnessError(
                f"file-I/O positive control exited {run_v.returncode}\n{run_v.stderr_text}"
            )
        created_v = product_created_files(before=before_v, roots=roots)
        names = {p.name for p in created_v}
        assert "cwd_side.txt" in names, f"cwd write not observed: {created_v}"
        assert "home_side.txt" in names, f"HOME write not observed: {created_v}"
        assert "tmp_side.txt" in names, f"TMPDIR write not observed: {created_v}"
        resolved = {p.resolve() for p in created_v}
        assert home_file in resolved
        assert tmp_file in resolved


def test_cardinality_extrema_enumeration_open_no_sockets():
    honest = wrap_enumeration_probe(
        r"""
    const hi: u64 = @as(u64, 1) << 32;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(0);
    _ = try bm.set(hi);
    _ = bm.getCardinality();
    _ = bm.isEmpty();
    _ = bm.minimum();
    _ = bm.maximum();
    var it = bm.iterator();
    while (it.next()) |_| {}
    const arr = try bm.toArray(allocator);
    defer allocator.free(arr);
    const dest = try allocator.alloc(u64, arr.len);
    defer allocator.free(dest);
    bm.toArrayInto(dest);
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
"""
    )
    vandal = wrap_probe_body(
        r"""
    const linux = std.os.linux;
    _ = linux.socket(linux.AF.INET, linux.SOCK.STREAM, 0);
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
"""
    )
    with workspace() as ws:
        compile_probe_or_raise(
            ws, honest, relpath="probe.zig", output="probe", timeout=DEFAULT_TIMEOUT
        )
        run, hits = run_traced_network(
            ws, [str(ws.resolve("probe"))], timeout=DEFAULT_TIMEOUT
        )
        if run.returncode != 0:
            raise HarnessError(
                f"honest network probe exited {run.returncode}\n{run.stderr_text}"
            )
        hits = network_syscalls_in_trace(hits)
        assert hits == [], f"query/iterate/dump issued network syscalls: {hits}"

        compile_probe_or_raise(
            ws, vandal, relpath="vandal.zig", output="vandal", timeout=DEFAULT_TIMEOUT
        )
        run_v, hits_v = run_traced_network(
            ws, [str(ws.resolve("vandal"))], timeout=DEFAULT_TIMEOUT
        )
        if run_v.returncode != 0:
            raise HarnessError(
                f"network positive control exited {run_v.returncode}\n{run_v.stderr_text}"
            )
        hits_v = network_syscalls_in_trace(hits_v)
        assert hits_v, "network positive control did not observe a socket/connect"


# ---------------------------------------------------------------------------
# Enumeration of one prefix at every population on the way to full and back
# ---------------------------------------------------------------------------


def test_one_prefix_enumerates_exactly_at_every_population_while_filled_and_emptied():
    # Cardinality, extrema, the ascending walk, the allocated array and the
    # caller-supplied destination agree with the values present, whatever
    # number of values already share their high 48 bits.
    report = run_block_sweep(
        r"""
    const Enum = struct {
        fn check(bm: *const klyvmap.Bitmap, b: Block, lo: u64, hi: u64, alloc: std.mem.Allocator, scratch: []u64) !bool {
            const n: usize = @intCast(hi - lo);
            if (bm.getCardinality() != hi - lo or bm.isEmpty()) return false;
            const mn = bm.minimum() orelse return false;
            const mx = bm.maximum() orelse return false;
            if (mn != b.lowest(lo, hi) or mx != b.highest(lo, hi)) return false;
            if (!b.walk(bm, lo, hi, false)) return false;
            const arr = try bm.toArray(alloc);
            defer alloc.free(arr);
            if (arr.len != n) return false;
            var it = bm.iterator();
            for (arr) |x| {
                const y = it.next() orelse return false;
                if (x != y) return false;
            }
            const sentinel: u64 = 0xA5A5_5A5A_A5A5_5A5A;
            @memset(scratch[0 .. n + 3], sentinel);
            bm.toArrayInto(scratch[0..n]);
            for (arr, scratch[0..n]) |x, y| {
                if (x != y) return false;
            }
            for (scratch[n .. n + 3]) |y| {
                if (y != sentinel) return false;
            }
            return true;
        }
    };
    const scratch = try init.gpa.alloc(u64, 65536 + 3);
    defer init.gpa.free(scratch);
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    var grow_ok = true;
    var grow_seen: u64 = 0;
    var n: u64 = 0;
    while (n < 65536) : (n += 1) {
        _ = try bm.set(block.val(n));
        if (Block.isCheckpoint(n + 1, &checkpoints)) {
            if (!try Enum.check(&bm, block, 0, n + 1, allocator, scratch)) grow_ok = false;
            grow_seen += 1;
        }
    }
    var shrink_ok = true;
    var shrink_seen: u64 = 0;
    n = 0;
    while (n < 65536) : (n += 1) {
        _ = bm.remove(block.val(n));
        const left: u64 = 65536 - (n + 1);
        if (left != 0 and Block.isCheckpoint(left, &checkpoints)) {
            if (!try Enum.check(&bm, block, n + 1, 65536, allocator, scratch)) shrink_ok = false;
            shrink_seen += 1;
        }
    }
    const arr0 = try bm.toArray(allocator);
    defer allocator.free(arr0);
    const emptied = bm.isEmpty() and bm.getCardinality() == 0 and bm.minimum() == null and
        bm.maximum() == null and block.walk(&bm, 0, 0, false) and arr0.len == 0;
    try emitJson(init, init.gpa,
        "{{\"grow_ok\":{s},\"grow_seen\":{d},\"shrink_ok\":{s},\"shrink_seen\":{d},\"emptied\":{s}}}",
        .{ jsonBool(grow_ok), grow_seen, jsonBool(shrink_ok), shrink_seen, jsonBool(emptied) },
    );
"""
    )
    require_sweep_true(report, "grow_ok", "shrink_ok", "emptied")
    require_sweep_seen(report, "grow_seen", len(block_checkpoints()))
    require_sweep_seen(report, "shrink_seen", len(shrink_checkpoints()) - 1)
