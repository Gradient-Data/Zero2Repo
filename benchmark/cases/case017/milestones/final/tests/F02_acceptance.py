# feature: F02
"""FP-02: set, membership, and remove of 64-bit values.

Covers FP-02 together with the product-wide rules the set / membership /
remove entries touch: values in the closed 64-bit range with no second
copy, no file or network I/O, and no 32-bit variant.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from F01_helpers import (
    compile_product_source,
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
    block_checkpoints,
    block_sweep_zig,
    nine_boundary_values,
    require_bool_field,
    require_int_field,
    shuffle_not_sorted,
    six_hundred_prefix_inserts,
    unpublished_dense_interior,
    unpublished_pair_sharing_high_48,
    unpublished_thousands_length,
    unpublished_u64_f02,
    zig_u64_list,
)
from _helpers import DEFAULT_TIMEOUT, HarnessError, workspace


# ---------------------------------------------------------------------------
# A. Set reports newly added; cardinality grows only on true
# ---------------------------------------------------------------------------


def test_set_42_reports_newly_added_then_not_and_cardinality_stays_one():
    source = wrap_probe_body(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    const before_member = bm.contains(42);
    const before_card = bm.getCardinality();
    const first = try bm.set(42);
    const mid_member = bm.contains(42);
    const mid_card = bm.getCardinality();
    const second = try bm.set(42);
    try emitJson(init, init.gpa,
        "{{\"before_member\":{s},\"before_card\":{d},\"first\":{s},\"mid_member\":{s},\"mid_card\":{d},\"second\":{s},\"after_member\":{s},\"after_card\":{d}}}",
        .{
            jsonBool(before_member), before_card, jsonBool(first),
            jsonBool(mid_member), mid_card, jsonBool(second),
            jsonBool(bm.contains(42)), bm.getCardinality(),
        },
    );
"""
    )
    report = run_bitmap_probe(source)
    assert require_bool_field(report, "before_member") is False
    assert require_int_field(report, "before_card") == 0
    assert require_bool_field(report, "first") is True
    assert require_bool_field(report, "mid_member") is True
    assert require_int_field(report, "mid_card") == 1
    assert require_bool_field(report, "second") is False
    assert require_bool_field(report, "after_member") is True
    assert require_int_field(report, "after_card") == 1
    assert report["first"] != report["second"]


def test_set_42_and_unpublished_above_2_pow_40_both_present_cardinality_two():
    high = unpublished_u64_f02(above=1 << 40)
    source = wrap_probe_body(
        fill_u64(
            r"""
    const high: u64 = __HIGH__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    const first_42 = try bm.set(42);
    const first_high = try bm.set(high);
    try emitJson(init, init.gpa,
        "{{\"first_42\":{s},\"first_high\":{s},\"has_42\":{s},\"has_high\":{s},\"card\":{d}}}",
        .{
            jsonBool(first_42), jsonBool(first_high),
            jsonBool(bm.contains(42)), jsonBool(bm.contains(high)),
            bm.getCardinality(),
        },
    );
""",
            high=high,
        )
    )
    report = run_bitmap_probe(source)
    assert require_bool_field(report, "first_42") is True
    assert require_bool_field(report, "first_high") is True
    assert require_bool_field(report, "has_42") is True
    assert require_bool_field(report, "has_high") is True
    assert require_int_field(report, "card") == 2


def test_set_unpublished_value_twice_grows_cardinality_only_once():
    value = unpublished_u64_f02()
    source = wrap_probe_body(
        fill_u64(
            r"""
    const value: u64 = __VALUE__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    const before_member = bm.contains(value);
    const before_card = bm.getCardinality();
    const first = try bm.set(value);
    const mid_card = bm.getCardinality();
    const second = try bm.set(value);
    try emitJson(init, init.gpa,
        "{{\"before_member\":{s},\"before_card\":{d},\"first\":{s},\"mid_card\":{d},\"second\":{s},\"after_member\":{s},\"after_card\":{d}}}",
        .{
            jsonBool(before_member), before_card, jsonBool(first),
            mid_card, jsonBool(second),
            jsonBool(bm.contains(value)), bm.getCardinality(),
        },
    );
""",
            value=value,
        )
    )
    report = run_bitmap_probe(source)
    assert require_bool_field(report, "before_member") is False
    assert require_int_field(report, "before_card") == 0
    assert require_bool_field(report, "first") is True
    assert require_int_field(report, "mid_card") == 1
    assert require_bool_field(report, "second") is False
    assert require_bool_field(report, "after_member") is True
    assert require_int_field(report, "after_card") == 1
    assert report["first"] != report["second"]


def test_set_two_unpublished_values_each_newly_added_then_duplicate_stays():
    first = unpublished_u64_f02()
    second = unpublished_u64_f02(forbidden={first})
    source = wrap_probe_body(
        fill_u64(
            r"""
    const a: u64 = __A__;
    const b: u64 = __B__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    const add_a = try bm.set(a);
    const add_b = try bm.set(b);
    const card_two = bm.getCardinality();
    const dup_a = try bm.set(a);
    try emitJson(init, init.gpa,
        "{{\"add_a\":{s},\"add_b\":{s},\"has_a\":{s},\"has_b\":{s},\"card_two\":{d},\"dup_a\":{s},\"card_after\":{d}}}",
        .{
            jsonBool(add_a), jsonBool(add_b),
            jsonBool(bm.contains(a)), jsonBool(bm.contains(b)),
            card_two, jsonBool(dup_a), bm.getCardinality(),
        },
    );
""",
            a=first,
            b=second,
        )
    )
    report = run_bitmap_probe(source)
    assert require_bool_field(report, "add_a") is True
    assert require_bool_field(report, "add_b") is True
    assert require_bool_field(report, "has_a") is True
    assert require_bool_field(report, "has_b") is True
    assert require_int_field(report, "card_two") == 2
    assert require_bool_field(report, "dup_a") is False
    assert require_int_field(report, "card_after") == 2


# ---------------------------------------------------------------------------
# B. Membership is true exactly for set-and-not-since-removed
# ---------------------------------------------------------------------------


def test_zero_round_trips_through_membership():
    source = wrap_probe_body(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    const before = bm.contains(0);
    _ = try bm.set(0);
    try emitJson(init, init.gpa,
        "{{\"before\":{s},\"after\":{s}}}",
        .{ jsonBool(before), jsonBool(bm.contains(0)) },
    );
"""
    )
    report = run_bitmap_probe(source)
    assert require_bool_field(report, "before") is False
    assert require_bool_field(report, "after") is True
    assert report["before"] != report["after"]


def test_membership_true_exactly_for_set_and_not_since_removed():
    a = unpublished_u64_f02()
    b = unpublished_u64_f02(forbidden={a})
    c = unpublished_u64_f02(forbidden={a, b})
    source = wrap_probe_body(
        fill_u64(
            r"""
    const a: u64 = __A__;
    const b: u64 = __B__;
    const c: u64 = __C__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(a);
    _ = try bm.set(b);
    const has_a = bm.contains(a);
    const has_b = bm.contains(b);
    const has_c = bm.contains(c);
    _ = bm.remove(a);
    try emitJson(init, init.gpa,
        "{{\"has_a\":{s},\"has_b\":{s},\"has_c\":{s},\"after_a\":{s},\"after_b\":{s},\"after_c\":{s}}}",
        .{
            jsonBool(has_a), jsonBool(has_b), jsonBool(has_c),
            jsonBool(bm.contains(a)), jsonBool(bm.contains(b)), jsonBool(bm.contains(c)),
        },
    );
""",
            a=a,
            b=b,
            c=c,
        )
    )
    report = run_bitmap_probe(source)
    assert require_bool_field(report, "has_a") is True
    assert require_bool_field(report, "has_b") is True
    assert require_bool_field(report, "has_c") is False
    assert require_bool_field(report, "after_a") is False
    assert require_bool_field(report, "after_b") is True
    assert require_bool_field(report, "after_c") is False
    assert report["has_a"] != report["after_a"]


def test_membership_false_for_never_set_unpublished_value():
    other = unpublished_u64_f02()
    never = unpublished_u64_f02(forbidden={other})
    source = wrap_probe_body(
        fill_u64(
            r"""
    const other: u64 = __OTHER__;
    const never: u64 = __NEVER__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(other);
    try emitJson(init, init.gpa,
        "{{\"has_other\":{s},\"has_never\":{s}}}",
        .{ jsonBool(bm.contains(other)), jsonBool(bm.contains(never)) },
    );
""",
            other=other,
            never=never,
        )
    )
    report = run_bitmap_probe(source)
    assert require_bool_field(report, "has_other") is True
    assert require_bool_field(report, "has_never") is False


# ---------------------------------------------------------------------------
# C. Remove reports was-present; set after remove is newly added
# ---------------------------------------------------------------------------


def test_remove_present_once_then_false_then_set_again_newly_added():
    a = unpublished_u64_f02()
    b = unpublished_u64_f02(forbidden={a})
    source = wrap_probe_body(
        fill_u64(
            r"""
    const a: u64 = __A__;
    const b: u64 = __B__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(a);
    _ = try bm.set(b);
    const before_a = bm.contains(a);
    const before_card = bm.getCardinality();
    const first_rm = bm.remove(a);
    const after_first_a = bm.contains(a);
    const after_first_b = bm.contains(b);
    const after_first_card = bm.getCardinality();
    const second_rm = bm.remove(a);
    const after_second_a = bm.contains(a);
    const after_second_b = bm.contains(b);
    const after_second_card = bm.getCardinality();
    const readd = try bm.set(a);
    try emitJson(init, init.gpa,
        "{{\"before_a\":{s},\"before_card\":{d},\"first_rm\":{s},\"after_first_a\":{s},\"after_first_b\":{s},\"after_first_card\":{d},\"second_rm\":{s},\"after_second_a\":{s},\"after_second_b\":{s},\"after_second_card\":{d},\"readd\":{s},\"after_readd_a\":{s},\"after_readd_b\":{s},\"after_readd_card\":{d}}}",
        .{
            jsonBool(before_a), before_card, jsonBool(first_rm),
            jsonBool(after_first_a), jsonBool(after_first_b), after_first_card,
            jsonBool(second_rm), jsonBool(after_second_a), jsonBool(after_second_b),
            after_second_card, jsonBool(readd),
            jsonBool(bm.contains(a)), jsonBool(bm.contains(b)), bm.getCardinality(),
        },
    );
""",
            a=a,
            b=b,
        )
    )
    report = run_bitmap_probe(source)
    assert require_bool_field(report, "before_a") is True
    assert require_int_field(report, "before_card") == 2
    assert require_bool_field(report, "first_rm") is True
    assert require_bool_field(report, "after_first_a") is False
    assert require_bool_field(report, "after_first_b") is True
    assert require_int_field(report, "after_first_card") == 1
    assert require_bool_field(report, "second_rm") is False
    assert require_bool_field(report, "after_second_a") is False
    assert require_bool_field(report, "after_second_b") is True
    assert require_int_field(report, "after_second_card") == 1
    assert require_bool_field(report, "readd") is True
    assert require_bool_field(report, "after_readd_a") is True
    assert require_bool_field(report, "after_readd_b") is True
    assert require_int_field(report, "after_readd_card") == 2
    assert report["first_rm"] != report["second_rm"]
    assert report["readd"] is True


def test_remove_never_set_unpublished_reports_false_cardinality_unchanged():
    other = unpublished_u64_f02()
    never = unpublished_u64_f02(forbidden={other})
    source = wrap_probe_body(
        fill_u64(
            r"""
    const other: u64 = __OTHER__;
    const never: u64 = __NEVER__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(other);
    const card_before = bm.getCardinality();
    const removed = bm.remove(never);
    try emitJson(init, init.gpa,
        "{{\"removed\":{s},\"card_before\":{d},\"card_after\":{d},\"has_other\":{s},\"has_never\":{s}}}",
        .{
            jsonBool(removed), card_before, bm.getCardinality(),
            jsonBool(bm.contains(other)), jsonBool(bm.contains(never)),
        },
    );
""",
            other=other,
            never=never,
        )
    )
    report = run_bitmap_probe(source)
    assert require_bool_field(report, "removed") is False
    assert require_int_field(report, "card_before") == 1
    assert require_int_field(report, "card_after") == 1
    assert require_bool_field(report, "has_other") is True
    assert require_bool_field(report, "has_never") is False


def test_remove_2_pow_32_from_bitmap_with_no_value_of_that_high_prefix():
    source = wrap_probe_body(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(0);
    _ = try bm.set(65535);
    const removed = bm.remove(@as(u64, 1) << 32);
    const min_j = try optU64Json(init.gpa, bm.minimum());
    defer init.gpa.free(min_j);
    try emitJson(init, init.gpa,
        "{{\"removed\":{s},\"card\":{d},\"has0\":{s},\"has65535\":{s},\"min\":{s}}}",
        .{
            jsonBool(removed), bm.getCardinality(),
            jsonBool(bm.contains(0)), jsonBool(bm.contains(65535)), min_j,
        },
    );
"""
    )
    report = run_bitmap_probe(source)
    assert require_bool_field(report, "removed") is False
    assert require_int_field(report, "card") == 2
    assert require_bool_field(report, "has0") is True
    assert require_bool_field(report, "has65535") is True


def test_remove_of_zero_alone_in_its_high_bits_leaves_other_high_prefixes():
    source = wrap_probe_body(
        r"""
    const mid: u64 = (@as(u64, 1) << 32) + 5;
    const hi: u64 = (@as(u64, 1) << 48) + 7;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(0);
    _ = try bm.set(mid);
    _ = try bm.set(hi);
    const removed = bm.remove(0);
    try emitJson(init, init.gpa,
        "{{\"removed\":{s},\"has0\":{s},\"has_mid\":{s},\"has_hi\":{s},\"card\":{d}}}",
        .{
            jsonBool(removed), jsonBool(bm.contains(0)),
            jsonBool(bm.contains(mid)), jsonBool(bm.contains(hi)),
            bm.getCardinality(),
        },
    );
"""
    )
    report = run_bitmap_probe(source)
    assert require_bool_field(report, "removed") is True
    assert require_bool_field(report, "has0") is False
    assert require_bool_field(report, "has_mid") is True
    assert require_bool_field(report, "has_hi") is True
    assert require_int_field(report, "card") == 2


def test_remove_zero_after_zero_and_65535_leaves_65535_as_minimum():
    source = wrap_probe_body(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(0);
    _ = try bm.set(65535);
    const removed = bm.remove(0);
    const min_j = try optU64Json(init.gpa, bm.minimum());
    defer init.gpa.free(min_j);
    try emitJson(init, init.gpa,
        "{{\"removed\":{s},\"has0\":{s},\"has65535\":{s},\"min\":{s},\"card\":{d}}}",
        .{
            jsonBool(removed), jsonBool(bm.contains(0)),
            jsonBool(bm.contains(65535)), min_j, bm.getCardinality(),
        },
    );
"""
    )
    report = run_bitmap_probe(source)
    assert require_bool_field(report, "removed") is True
    assert require_bool_field(report, "has0") is False
    assert require_bool_field(report, "has65535") is True
    assert require_int_field(report, "card") == 1
    if "min" not in report:
        raise HarnessError("probe JSON missing min")
    assert report["min"] == 65535


def test_remove_unpublished_sharing_high_48_leaves_sibling_and_other_prefix():
    sib_a, sib_b = unpublished_pair_sharing_high_48()
    other = None
    for _ in range(8):
        candidate = unpublished_u64_f02(forbidden={sib_a, sib_b})
        if (candidate >> 16) != (sib_a >> 16):
            other = candidate
            break
    if other is None:
        raise HarnessError(
            "could not draw a third unpublished value on a different high-48 prefix"
        )
    source = wrap_probe_body(
        fill_u64(
            r"""
    const a: u64 = __A__;
    const b: u64 = __B__;
    const c: u64 = __C__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(a);
    _ = try bm.set(b);
    _ = try bm.set(c);
    const before_a = bm.contains(a);
    const removed = bm.remove(a);
    try emitJson(init, init.gpa,
        "{{\"before_a\":{s},\"removed\":{s},\"has_a\":{s},\"has_b\":{s},\"has_c\":{s},\"card\":{d}}}",
        .{
            jsonBool(before_a), jsonBool(removed),
            jsonBool(bm.contains(a)), jsonBool(bm.contains(b)), jsonBool(bm.contains(c)),
            bm.getCardinality(),
        },
    );
""",
            a=sib_a,
            b=sib_b,
            c=other,
        )
    )
    report = run_bitmap_probe(source)
    assert require_bool_field(report, "before_a") is True
    assert require_bool_field(report, "removed") is True
    assert require_bool_field(report, "has_a") is False
    assert require_bool_field(report, "has_b") is True
    assert require_bool_field(report, "has_c") is True
    assert require_int_field(report, "card") == 2


def test_remove_2_pow_32_plus_5_leaves_sibling_and_other_prefixes():
    source = wrap_probe_body(
        r"""
    const a: u64 = (@as(u64, 1) << 32) + 5;
    const b: u64 = (@as(u64, 1) << 32) + 65535;
    const hi: u64 = (@as(u64, 1) << 48) + 7;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(a);
    _ = try bm.set(b);
    _ = try bm.set(0);
    _ = try bm.set(hi);
    const removed = bm.remove(a);
    try emitJson(init, init.gpa,
        "{{\"removed\":{s},\"has_a\":{s},\"has_b\":{s},\"has0\":{s},\"has_hi\":{s},\"card\":{d}}}",
        .{
            jsonBool(removed), jsonBool(bm.contains(a)), jsonBool(bm.contains(b)),
            jsonBool(bm.contains(0)), jsonBool(bm.contains(hi)), bm.getCardinality(),
        },
    );
"""
    )
    report = run_bitmap_probe(source)
    assert require_bool_field(report, "removed") is True
    assert require_bool_field(report, "has_a") is False
    assert require_bool_field(report, "has_b") is True
    assert require_bool_field(report, "has0") is True
    assert require_bool_field(report, "has_hi") is True
    assert require_int_field(report, "card") == 3


# ---------------------------------------------------------------------------
# D. Nine boundary values, shuffled, each present once
# ---------------------------------------------------------------------------


def test_nine_boundary_values_shuffled_each_present_once_cardinality_nine():
    named = nine_boundary_values()
    order = shuffle_not_sorted(named)
    redo = order[secrets.randbelow(len(order))]
    source = wrap_probe_body(
        fill_u64(
            r"""
    const vals = [_]u64{ __VALS__ };
    const redo: u64 = __REDO__;
    const max_u64: u64 = std.math.maxInt(u64);
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    const before0 = bm.contains(0);
    const before_mid = bm.contains((@as(u64, 1) << 32) + 5);
    const before_max = bm.contains(max_u64);
    var all_new = true;
    for (vals) |v| {
        if (!try bm.set(v)) all_new = false;
    }
    var all_here = true;
    for (vals) |v| {
        if (!bm.contains(v)) all_here = false;
    }
    const min_j = try optU64Json(init.gpa, bm.minimum());
    defer init.gpa.free(min_j);
    const max_is_max = if (bm.maximum()) |m| m == max_u64 else false;
    const dup = try bm.set(redo);
    try emitJson(init, init.gpa,
        "{{\"before0\":{s},\"before_mid\":{s},\"before_max\":{s},\"all_new\":{s},\"all_here\":{s},\"card\":{d},\"min\":{s},\"max_is_max\":{s},\"absent1\":{s},\"absent_mid\":{s},\"absent_47\":{s},\"dup\":{s},\"card_after\":{d}}}",
        .{
            jsonBool(before0), jsonBool(before_mid), jsonBool(before_max),
            jsonBool(all_new), jsonBool(all_here), bm.getCardinality(),
            min_j, jsonBool(max_is_max),
            jsonBool(bm.contains(1)),
            jsonBool(bm.contains((@as(u64, 1) << 32) + 6)),
            jsonBool(bm.contains(@as(u64, 1) << 47)),
            jsonBool(dup), bm.getCardinality(),
        },
    );
""",
            vals=zig_u64_list(order),
            redo=redo,
        )
    )
    report = run_bitmap_probe(source)
    assert require_bool_field(report, "before0") is False
    assert require_bool_field(report, "before_mid") is False
    assert require_bool_field(report, "before_max") is False
    assert require_bool_field(report, "all_new") is True
    assert require_bool_field(report, "all_here") is True
    assert require_int_field(report, "card") == 9
    if "min" not in report:
        raise HarnessError("probe JSON missing min")
    assert report["min"] == 0
    assert require_bool_field(report, "max_is_max") is True
    assert require_bool_field(report, "absent1") is False
    assert require_bool_field(report, "absent_mid") is False
    assert require_bool_field(report, "absent_47") is False
    assert require_bool_field(report, "dup") is False
    assert require_int_field(report, "card_after") == 9


# ---------------------------------------------------------------------------
# E. Dense consecutive run starting at 0
# ---------------------------------------------------------------------------


def test_dense_run_zero_through_4999_all_present_cardinality_5000():
    source = wrap_probe_body(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    var i: u64 = 0;
    var all_new = true;
    while (i < 5000) : (i += 1) {
        if (!try bm.set(i)) all_new = false;
    }
    const every = allPresent(&bm, 0, 4999);
    const min_j = try optU64Json(init.gpa, bm.minimum());
    defer init.gpa.free(min_j);
    const max_j = try optU64Json(init.gpa, bm.maximum());
    defer init.gpa.free(max_j);
    try emitJson(init, init.gpa,
        "{{\"all_new\":{s},\"every\":{s},\"card\":{d},\"min\":{s},\"max\":{s},\"past\":{s}}}",
        .{
            jsonBool(all_new), jsonBool(every), bm.getCardinality(),
            min_j, max_j, jsonBool(bm.contains(5000)),
        },
    );
"""
    )
    report = run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
    assert require_bool_field(report, "all_new") is True
    assert require_bool_field(report, "every") is True
    assert require_int_field(report, "card") == 5000
    if "min" not in report or "max" not in report:
        raise HarnessError("probe JSON missing min/max")
    assert report["min"] == 0
    assert report["max"] == 4999
    assert require_bool_field(report, "past") is False


def test_dense_run_unpublished_thousands_length_all_present_not_past_end():
    length = unpublished_thousands_length()
    source = wrap_probe_body(
        fill_u64(
            r"""
    const n: u64 = __N__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    var i: u64 = 0;
    var all_new = true;
    while (i < n) : (i += 1) {
        if (!try bm.set(i)) all_new = false;
    }
    const every = allPresent(&bm, 0, n - 1);
    try emitJson(init, init.gpa,
        "{{\"all_new\":{s},\"every\":{s},\"card\":{d},\"past\":{s}}}",
        .{
            jsonBool(all_new), jsonBool(every), bm.getCardinality(),
            jsonBool(bm.contains(n)),
        },
    );
""",
            n=length,
        )
    )
    report = run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
    assert require_bool_field(report, "all_new") is True
    assert require_bool_field(report, "every") is True
    assert require_int_field(report, "card") == length
    assert require_bool_field(report, "past") is False


def test_remove_interior_of_dense_run_5000_leaves_neighbours():
    interior = unpublished_dense_interior()
    source = wrap_probe_body(
        fill_u64(
            r"""
    const v: u64 = __V__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    var i: u64 = 0;
    while (i < 5000) : (i += 1) {
        _ = try bm.set(i);
    }
    const every = allPresent(&bm, 0, 4999);
    const left_before = bm.contains(v - 1);
    const mid_before = bm.contains(v);
    const right_before = bm.contains(v + 1);
    const card_before = bm.getCardinality();
    const removed = bm.remove(v);
    try emitJson(init, init.gpa,
        "{{\"every\":{s},\"left_before\":{s},\"mid_before\":{s},\"right_before\":{s},\"card_before\":{d},\"removed\":{s},\"has_v\":{s},\"has_left\":{s},\"has_right\":{s},\"card\":{d}}}",
        .{
            jsonBool(every), jsonBool(left_before), jsonBool(mid_before),
            jsonBool(right_before), card_before, jsonBool(removed),
            jsonBool(bm.contains(v)), jsonBool(bm.contains(v - 1)),
            jsonBool(bm.contains(v + 1)), bm.getCardinality(),
        },
    );
""",
            v=interior,
        )
    )
    report = run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
    assert require_bool_field(report, "every") is True
    assert require_bool_field(report, "left_before") is True
    assert require_bool_field(report, "mid_before") is True
    assert require_bool_field(report, "right_before") is True
    assert require_int_field(report, "card_before") == 5000
    assert require_bool_field(report, "removed") is True
    assert require_bool_field(report, "has_v") is False
    assert require_bool_field(report, "has_left") is True
    assert require_bool_field(report, "has_right") is True
    assert require_int_field(report, "card") == 4999


# ---------------------------------------------------------------------------
# F. Hundreds of distinct high-48-bit prefixes
# ---------------------------------------------------------------------------


def test_six_hundred_high_48_prefixes_three_values_each_inserted_out_of_order():
    shuffled, absent, present = six_hundred_prefix_inserts()
    source = wrap_probe_body(
        fill_u64(
            r"""
    const vals = [_]u64{ __VALS__ };
    const absent: u64 = __ABSENT__;
    const p0: u64 = __P0__;
    const p1: u64 = __P1__;
    const p2: u64 = __P2__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    var all_new = true;
    for (vals) |v| {
        if (!try bm.set(v)) all_new = false;
    }
    var all_here = true;
    for (vals) |v| {
        if (!bm.contains(v)) all_here = false;
    }
    try emitJson(init, init.gpa,
        "{{\"all_new\":{s},\"all_here\":{s},\"card\":{d},\"absent\":{s},\"p0\":{s},\"p1\":{s},\"p2\":{s}}}",
        .{
            jsonBool(all_new), jsonBool(all_here), bm.getCardinality(),
            jsonBool(bm.contains(absent)),
            jsonBool(bm.contains(p0)), jsonBool(bm.contains(p1)), jsonBool(bm.contains(p2)),
        },
    );
""",
            vals=zig_u64_list(shuffled),
            absent=absent,
            p0=present[0],
            p1=present[1],
            p2=present[2],
        )
    )
    report = run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
    assert require_bool_field(report, "all_new") is True
    assert require_bool_field(report, "all_here") is True
    assert require_int_field(report, "card") == 1800
    assert require_bool_field(report, "absent") is False
    assert require_bool_field(report, "p0") is True
    assert require_bool_field(report, "p1") is True
    assert require_bool_field(report, "p2") is True


# ---------------------------------------------------------------------------
# G. Set / membership / remove perform no file or network I/O
# ---------------------------------------------------------------------------


def _compile_or_raise(ws, source: str, *, relpath: str, output: str, timeout: float):
    compiled = compile_product_source(
        ws, source, relpath=relpath, output=output, timeout=timeout
    )
    if compiled.returncode != 0:
        raise HarnessError(
            f"{output} failed to compile\n{compiled.stderr_text}"
        )
    return compiled


def test_set_membership_remove_write_no_files():
    interior = unpublished_dense_interior()
    dense = wrap_probe_body(
        fill_u64(
            r"""
    const v: u64 = __V__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    var i: u64 = 0;
    while (i < 5000) : (i += 1) {
        _ = try bm.set(i);
    }
    _ = bm.remove(v);
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
""",
            v=interior,
        )
    )
    shuffled, _absent, _present = six_hundred_prefix_inserts()
    prefixes = wrap_probe_body(
        fill_u64(
            r"""
    const vals = [_]u64{ __VALS__ };
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    for (vals) |v| {
        _ = try bm.set(v);
    }
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
""",
            vals=zig_u64_list(shuffled),
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

        _compile_or_raise(
            ws, dense, relpath="dense.zig", output="dense", timeout=LARGE_PROBE_TIMEOUT
        )
        _compile_or_raise(
            ws,
            prefixes,
            relpath="prefixes.zig",
            output="prefixes",
            timeout=LARGE_PROBE_TIMEOUT,
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
        assert created_dense == set(), f"dense set/remove wrote files: {created_dense}"

        before_pref = set()
        for root in roots:
            before_pref |= _walk_regular_files(root)
        run_pref = ws.run_command(
            [str(ws.resolve("prefixes"))], timeout=LARGE_PROBE_TIMEOUT
        )
        if run_pref.returncode != 0:
            raise HarnessError(
                f"prefix I/O probe exited {run_pref.returncode}\n{run_pref.stderr_text}"
            )
        created_pref = product_created_files(before=before_pref, roots=roots)
        assert created_pref == set(), f"prefix set wrote files: {created_pref}"

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
        _compile_or_raise(
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


def test_set_membership_remove_open_no_sockets():
    high = unpublished_u64_f02(above=1 << 32)
    honest = wrap_probe_body(
        fill_u64(
            r"""
    const high: u64 = __HIGH__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try bm.set(42);
    _ = try bm.set(high);
    _ = bm.contains(42);
    _ = bm.contains(high);
    _ = bm.remove(42);
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
""",
            high=high,
        )
    )
    vandal = wrap_probe_body(
        r"""
    const linux = std.os.linux;
    _ = linux.socket(linux.AF.INET, linux.SOCK.STREAM, 0);
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
"""
    )
    with workspace() as ws:
        _compile_or_raise(
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
        assert hits == [], f"set/membership/remove issued network syscalls: {hits}"

        _compile_or_raise(
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
# One prefix filled to every one of its values and emptied again
# ---------------------------------------------------------------------------


def test_one_prefix_filled_and_emptied_value_by_value_keeps_membership_at_every_population():
    # Any 64-bit value set is present and counts once, and remove deletes
    # exactly the value it names, whatever number of values already share its
    # high 48 bits. Populations 2^k - 1, 2^k and 2^k + 1 are observed in full.
    source = wrap_probe_body(
        block_sweep_zig()
        + r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    const edges_new = try block.setEdges(&bm);
    var grow_step = true;
    var grow_full = true;
    var grow_seen: u64 = 0;
    var n: u64 = 0;
    while (n < 65536) : (n += 1) {
        const v = block.val(n);
        const fresh = try bm.set(v);
        const again = try bm.set(v);
        if (!fresh or again or !bm.contains(v) or bm.getCardinality() != n + 3) grow_step = false;
        if (n + 1 < 65536 and bm.contains(block.val(n + 1))) grow_step = false;
        if (!bm.contains(block.below) or !bm.contains(block.above)) grow_step = false;
        if (Block.isCheckpoint(n + 1, &checkpoints)) {
            if (!block.members(&bm, 0, n + 1, true)) grow_full = false;
            grow_seen += 1;
        }
    }
    var shrink_step = true;
    var shrink_full = true;
    var shrink_seen: u64 = 0;
    n = 0;
    while (n < 65536) : (n += 1) {
        const v = block.val(n);
        const had = bm.remove(v);
        const again = bm.remove(v);
        const left: u64 = 65536 - (n + 1);
        if (!had or again or bm.contains(v) or bm.getCardinality() != left + 2) shrink_step = false;
        if (n + 1 < 65536 and !bm.contains(block.val(n + 1))) shrink_step = false;
        if (!bm.contains(block.below) or !bm.contains(block.above)) shrink_step = false;
        if (left == 0 or Block.isCheckpoint(left, &checkpoints)) {
            if (!block.members(&bm, n + 1, 65536, true)) shrink_full = false;
            shrink_seen += 1;
        }
    }
    const refill = try bm.set(block.val(0)) and bm.contains(block.val(0)) and bm.getCardinality() == 3;
    try emitJson(init, init.gpa,
        "{{\"edges_new\":{s},\"grow_step\":{s},\"grow_full\":{s},\"grow_seen\":{d},\"shrink_step\":{s},\"shrink_full\":{s},\"shrink_seen\":{d},\"refill\":{s}}}",
        .{
            jsonBool(edges_new), jsonBool(grow_step), jsonBool(grow_full), grow_seen,
            jsonBool(shrink_step), jsonBool(shrink_full), shrink_seen, jsonBool(refill),
        },
    );
"""
    )
    report = run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
    for key in ("edges_new", "grow_step", "grow_full", "shrink_step", "shrink_full", "refill"):
        assert require_bool_field(report, key) is True, key
    points = block_checkpoints()
    if require_int_field(report, "grow_seen") != len(points):
        raise HarnessError("growing sweep did not reach every checkpoint")
    shrink_points = {0} | {c for c in points if c < 65536}
    if require_int_field(report, "shrink_seen") != len(shrink_points):
        raise HarnessError("shrinking sweep did not reach every checkpoint")
