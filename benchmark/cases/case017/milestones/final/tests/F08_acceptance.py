# feature: F08
"""FP-08: fused intersection, union, and difference cardinalities.

Assertions follow Full_PRD.original.md FP-08 and the pre-FP sentences these
three entries can trigger. Counts are the integers the PRD names, or the
ordinary set sizes of the values the test inserted.
"""

from __future__ import annotations

from pathlib import Path

from F01_helpers import (
    _walk_regular_files,
    compile_product_source,
    fill_u64,
    network_syscalls_in_trace,
    product_created_files,
    require_empty_snapshot,
    run_traced_network,
)
from F02_helpers import require_bool_field, require_int_field, zig_u64_list
from F04_helpers import (
    file_write_syscalls_in_trace,
    run_traced_arch_network,
    run_traced_file_writes,
    unexpected_file_reads_in_trace,
)
from F08_helpers import (
    NAMED_SET_F08,
    algebra_f08,
    assert_fused_f08,
    borrow_sides_f08,
    crossing_runs_f08,
    exclusive_pair_f08,
    overlapping_pair_f08,
    prefixes_miss_named_f08,
    refuse_pair_f08,
    run_f08_probe,
    run_f08_refuse,
    shared_prefixes_no_common_value_f08,
    split_prefix_above_2_pow_32_f08,
    uncleaned_population_f08,
    unpublished_u64_f08,
    wrap_f08_probe,
)
from F02_helpers import (
    block_checkpoints,
    require_sweep_seen,
    require_sweep_true,
    run_block_sweep,
)
from _helpers import DEFAULT_TIMEOUT, HarnessError, workspace

_LISTS = r"""
    const lvals = [_]u64{ __LVALS__ };
    const rvals = [_]u64{ __RVALS__ };
    const absent: u64 = __ABSENT__;
    var left = try buildFrom(allocator, &lvals);
    defer left.deinit();
    var right = try buildFrom(allocator, &rvals);
    defer right.deinit();
    const report = try fullLists(allocator, init.gpa, &left, &right, &lvals, &rvals, absent);
    try emitPair(init, init.gpa, report);
"""


def _expect_lists(left: list[int], right: list[int], absent: int) -> dict:
    report = run_f08_probe(
        _LISTS,
        lvals=zig_u64_list(left),
        rvals=zig_u64_list(right),
        absent=absent,
    )
    inter, union, diff_lr, diff_rl = algebra_f08(left, right)
    assert_fused_f08(
        report,
        inter=inter,
        union=union,
        diff_lr=diff_lr,
        diff_rl=diff_rl,
        left_card=len(set(left)),
        right_card=len(set(right)),
    )
    return report


def test_fused_counts_match_materialized_inplace_and_set_sizes_either_order():
    left, right, absent = overlapping_pair_f08()
    _expect_lists(left, right, absent)


def test_fused_counts_on_unpublished_size_either_operand_on_the_left():
    left, right, absent = overlapping_pair_f08()
    report = _expect_lists(left, right, absent)
    swapped = _expect_lists(right, left, absent)
    if require_int_field(report, "and_lr") != require_int_field(swapped, "and_lr"):
        raise AssertionError("fused intersection changed when the operands swapped")
    if require_int_field(report, "or_lr") != require_int_field(swapped, "or_lr"):
        raise AssertionError("fused union changed when the operands swapped")
    if require_int_field(report, "diff_lr") != require_int_field(swapped, "diff_rl"):
        raise AssertionError("fused difference did not follow the operand placed on the left")


def test_fused_counts_split_one_prefix_above_2_pow_32():
    left, right, absent = split_prefix_above_2_pow_32_f08()
    report = _expect_lists(left, right, absent)
    if require_int_field(report, "and_lr") != 1:
        raise AssertionError("one shared value inside a high prefix did not count as 1")
    if require_int_field(report, "or_lr") != 3:
        raise AssertionError("three values inside one high prefix did not count as 3")
    if require_int_field(report, "diff_lr") != 1 or require_int_field(report, "diff_rl") != 1:
        raise AssertionError("each side's exclusive value inside that prefix did not count as 1")


def test_fused_counts_against_empty_on_a_fixed_five_value_set():
    absent = unpublished_u64_f08(NAMED_SET_F08)
    report = run_f08_probe(
        r"""
    const named = [_]u64{ __NAMED__ };
    const absent: u64 = __ABSENT__;
    var full = try buildFrom(allocator, &named);
    defer full.deinit();
    var empty_bm = try freshEmpty(allocator);
    defer empty_bm.deinit();
    const named_card = full.getCardinality();
    const named_in = containsAll(&full, &named);
    const has_zero = full.contains(0);
    const has_max = full.contains(__MAX__);
    const empty_card = empty_bm.getCardinality();
    const empty_flag = empty_bm.isEmpty();
    const contains0 = empty_bm.contains(0);
    const min_j = try optU64Json(init.gpa, empty_bm.minimum());
    defer init.gpa.free(min_j);
    const max_j = try optU64Json(init.gpa, empty_bm.maximum());
    defer init.gpa.free(max_j);
    const forward = try fullLists(allocator, init.gpa, &full, &empty_bm, &named, &[_]u64{}, absent);
    var full_b = try buildFrom(allocator, &named);
    defer full_b.deinit();
    var empty_b = try freshEmpty(allocator);
    defer empty_b.deinit();
    const backward = try fullLists(allocator, init.gpa, &empty_b, &full_b, &[_]u64{}, &named, absent);
    const still_named = containsAll(&full, &named) and full.getCardinality() == named_card;
    const still_empty = empty_bm.getCardinality() == 0 and !empty_bm.contains(0) and empty_bm.isEmpty();
    try emitJson(init, init.gpa,
        "{{\"and_lr\":{d},\"or_lr\":{d},\"diff_lr\":{d},\"and_rl\":{d},\"or_rl\":{d},\"diff_rl\":{d},\"back_and\":{d},\"back_or\":{d},\"back_diff\":{d},\"named_card\":{d},\"named_in\":{s},\"has_zero\":{s},\"has_max\":{s},\"empty\":{s},\"cardinality\":{d},\"contains0\":{s},\"min\":{s},\"max\":{s},\"still_named\":{s},\"still_empty\":{s},\"left_same\":{s},\"right_same\":{s},\"back_left_same\":{s},\"back_right_same\":{s},\"mat_and\":{d},\"mat_or\":{d},\"ip_and\":{d},\"ip_diff_lr\":{d},\"back_mat_and\":{d},\"back_or_count\":{d},\"back_diff_rl\":{d}}}",
        .{
            forward.and_lr, forward.or_lr, forward.diff_lr, forward.and_rl, forward.or_rl, forward.diff_rl,
            backward.and_lr, backward.or_lr, backward.diff_lr,
            named_card, jsonBool(named_in), jsonBool(has_zero), jsonBool(has_max),
            jsonBool(empty_flag), empty_card, jsonBool(contains0), min_j, max_j,
            jsonBool(still_named), jsonBool(still_empty),
            jsonBool(forward.left_same), jsonBool(forward.right_same),
            jsonBool(backward.left_same), jsonBool(backward.right_same),
            forward.mat_and, forward.mat_or, forward.ip_and, forward.ip_diff_lr,
            backward.mat_and, backward.or_lr, backward.diff_rl,
        },
    );
""",
        named=zig_u64_list(NAMED_SET_F08),
        absent=absent,
        max=str(NAMED_SET_F08[-1]),
    )
    require_empty_snapshot(report)
    if require_int_field(report, "named_card") != 5 or require_bool_field(report, "named_in") is not True:
        raise AssertionError("named set is not the five stated values")
    if require_bool_field(report, "has_zero") is not True or require_bool_field(report, "has_max") is not True:
        raise AssertionError("named set dropped 0 or the 64-bit maximum")
    # S against empty, then empty against S. Intersection is 0 either way.
    # Union is 5 either way. Difference is the left cardinality.
    for key, want in (
        ("and_lr", 0),
        ("and_rl", 0),
        ("or_lr", 5),
        ("or_rl", 5),
        ("diff_lr", 5),
        ("back_and", 0),
        ("back_or", 5),
        ("back_diff", 0),
        ("mat_and", 0),
        ("mat_or", 5),
        ("ip_and", 0),
        ("ip_diff_lr", 5),
        ("back_mat_and", 0),
        ("back_or_count", 5),
        ("back_diff_rl", 5),
    ):
        got = require_int_field(report, key)
        if got != want:
            raise AssertionError(f"{key} is {got}, want {want}")
    for key in ("still_named", "still_empty", "left_same", "right_same", "back_left_same", "back_right_same"):
        if require_bool_field(report, key) is not True:
            raise AssertionError(f"{key} is not true")


def test_fused_union_of_two_empty_bitmaps_is_zero():
    report = run_f08_probe(
        r"""
    var a = try freshEmpty(allocator);
    defer a.deinit();
    var b = try freshEmpty(allocator);
    defer b.deinit();
    const min_j = try optU64Json(init.gpa, a.minimum());
    defer init.gpa.free(min_j);
    const max_j = try optU64Json(init.gpa, a.maximum());
    defer init.gpa.free(max_j);
    const report = try fullLists(allocator, init.gpa, &a, &b, &[_]u64{}, &[_]u64{}, 0);
    try emitJson(init, init.gpa,
        "{{\"and_lr\":{d},\"or_lr\":{d},\"diff_lr\":{d},\"and_rl\":{d},\"or_rl\":{d},\"diff_rl\":{d},\"mat_and\":{d},\"mat_or\":{d},\"ip_diff_lr\":{d},\"left_same\":{s},\"right_same\":{s},\"empty\":{s},\"cardinality\":{d},\"contains0\":{s},\"min\":{s},\"max\":{s}}}",
        .{
            report.and_lr, report.or_lr, report.diff_lr, report.and_rl, report.or_rl, report.diff_rl,
            report.mat_and, report.mat_or, report.ip_diff_lr,
            jsonBool(report.left_same), jsonBool(report.right_same),
            jsonBool(a.isEmpty()), a.getCardinality(), jsonBool(a.contains(0)), min_j, max_j,
        },
    );
"""
    )
    require_empty_snapshot(report)
    for key in ("and_lr", "or_lr", "diff_lr", "and_rl", "or_rl", "diff_rl", "mat_and", "mat_or", "ip_diff_lr"):
        if require_int_field(report, key) != 0:
            raise AssertionError(f"two empty bitmaps: {key} is {report.get(key)!r}, want 0")
    if require_bool_field(report, "left_same") is not True or require_bool_field(report, "right_same") is not True:
        raise AssertionError("empty operands changed")


def test_fused_counts_of_a_fixed_five_value_set_against_itself():
    absent = unpublished_u64_f08(NAMED_SET_F08)
    report = run_f08_probe(
        r"""
    const named = [_]u64{ __NAMED__ };
    const absent: u64 = __ABSENT__;
    var bm = try buildFrom(allocator, &named);
    defer bm.deinit();
    const report = try fullLists(allocator, init.gpa, &bm, &bm, &named, &named, absent);
    try emitPair(init, init.gpa, report);
""",
        named=zig_u64_list(NAMED_SET_F08),
        absent=absent,
    )
    assert_fused_f08(
        report,
        inter=5,
        union=5,
        diff_lr=0,
        diff_rl=0,
        left_card=5,
        right_card=5,
    )


def test_fused_counts_when_prefixes_miss_a_fixed_five_value_set():
    other, absent = prefixes_miss_named_f08()
    named = list(NAMED_SET_F08)
    report = _expect_lists(named, other, absent)
    inter, union, diff_lr, diff_rl = algebra_f08(named, other)
    if inter != 0:
        raise AssertionError("prefix-miss pair is not disjoint")
    if union != 5 + len(other) or diff_lr != 5 or diff_rl != len(other):
        raise AssertionError("prefix-miss counts are not the disjoint identities")
    if require_int_field(report, "and_lr") != require_int_field(report, "and_rl"):
        raise AssertionError("disjoint intersection depended on order")
    if require_int_field(report, "or_lr") != require_int_field(report, "or_rl"):
        raise AssertionError("disjoint union depended on order")
    if diff_lr == diff_rl:
        raise AssertionError("prefix-miss sides have equal cardinality; the draw must show order")


def test_fused_counts_when_shared_low_and_high_prefixes_have_no_common_value():
    other, absent = shared_prefixes_no_common_value_f08()
    named = list(NAMED_SET_F08)
    report = _expect_lists(named, other, absent)
    inter, union, diff_lr, _diff_rl = algebra_f08(named, other)
    if inter != 0 or union != len(named) + len(other) or diff_lr != len(named):
        raise AssertionError("shared prefixes with no common value are not disjoint")
    if require_int_field(report, "and_lr") != 0:
        raise AssertionError("a shared high prefix with no common value counted as intersection")


def test_fused_counts_on_zero_through_4999_and_2957_through_7956():
    left = set(range(0, 5000))
    right = set(range(2957, 7957))
    inter, union, diff_lr, diff_rl = algebra_f08(sorted(left), sorted(right))
    if (inter, union, diff_lr, diff_rl) != (2043, 7957, 2957, 2957):
        raise HarnessError(f"named runs did not produce 2043/7957/2957/2957: {(inter, union, diff_lr, diff_rl)}")
    absent = unpublished_u64_f08()
    report = run_f08_probe(
        r"""
    const absent: u64 = __ABSENT__;
    var left = try freshEmpty(allocator);
    defer left.deinit();
    var right = try freshEmpty(allocator);
    defer right.deinit();
    try fillRange(&left, 0, 4999);
    try fillRange(&right, 2957, 7956);
    const report = try fullRanges(allocator, init.gpa, &left, &right, 0, 4999, 2957, 7956, absent);
    try emitPair(init, init.gpa, report);
""",
        absent=absent,
    )
    assert_fused_f08(
        report,
        inter=2043,
        union=7957,
        diff_lr=2957,
        diff_rl=2957,
        left_card=5000,
        right_card=5000,
    )


def test_fused_counts_on_two_identical_runs_of_those_5000_values():
    absent = unpublished_u64_f08()
    report = run_f08_probe(
        r"""
    const absent: u64 = __ABSENT__;
    var left = try freshEmpty(allocator);
    defer left.deinit();
    var right = try freshEmpty(allocator);
    defer right.deinit();
    try fillRange(&left, 0, 4999);
    try fillRange(&right, 0, 4999);
    const report = try fullRanges(allocator, init.gpa, &left, &right, 0, 4999, 0, 4999, absent);
    try emitPair(init, init.gpa, report);
""",
        absent=absent,
    )
    assert_fused_f08(
        report,
        inter=5000,
        union=5000,
        diff_lr=0,
        diff_rl=0,
        left_card=5000,
        right_card=5000,
    )


def test_fused_counts_on_unpublished_runs_that_cross_2_pow_16():
    a0, a1, b0, b1, absent = crossing_runs_f08()
    left = list(range(a0, a1 + 1))
    right = list(range(b0, b1 + 1))
    inter, union, diff_lr, diff_rl = algebra_f08(left, right)
    if {inter, union, diff_lr, diff_rl} & {2043, 7957, 2957}:
        raise HarnessError("crossing run redrew a named count")
    report = run_f08_probe(
        r"""
    const absent: u64 = __ABSENT__;
    var left = try freshEmpty(allocator);
    defer left.deinit();
    var right = try freshEmpty(allocator);
    defer right.deinit();
    try fillRange(&left, __A0__, __A1__);
    try fillRange(&right, __B0__, __B1__);
    const report = try fullRanges(allocator, init.gpa, &left, &right, __A0__, __A1__, __B0__, __B1__, absent);
    try emitPair(init, init.gpa, report);
""",
        absent=absent,
        a0=a0,
        a1=a1,
        b0=b0,
        b1=b1,
    )
    assert_fused_f08(
        report,
        inter=inter,
        union=union,
        diff_lr=diff_lr,
        diff_rl=diff_rl,
        left_card=len(left),
        right_card=len(right),
    )


def test_fused_intersection_of_dense_run_plus_2_pow_32_and_sparse_is_2_either_order():
    left = list(range(0, 4000)) + [1 << 32]
    right = [5, 4000, 4001, 1 << 32]
    absent = unpublished_u64_f08(left + right)
    inter, union, diff_lr, diff_rl = algebra_f08(left, right)
    if inter != 2:
        raise HarnessError(f"dense-plus-2^32 intersection is {inter}, not 2")
    report = run_f08_probe(
        r"""
    const rvals = [_]u64{ __RVALS__ };
    const absent: u64 = __ABSENT__;
    var left = try freshEmpty(allocator);
    defer left.deinit();
    try fillRange(&left, 0, 3999);
    _ = try left.set(1 << 32);
    var right = try buildFrom(allocator, &rvals);
    defer right.deinit();
    const left_snap = try takeSnap(init.gpa, &left);
    defer init.gpa.free(left_snap.bytes);
    const right_snap = try takeSnap(init.gpa, &right);
    defer init.gpa.free(right_snap.bytes);
    try proveComparator(init.gpa, left_snap.bytes);
    const fused = readFused(&left, &right);
    const ctl = try controls(allocator, &left, &right);
    const left_values_held = rangeHeld(&left, 0, 3999, absent, 4001) and left.contains(1 << 32)
        and !left.contains(4000) and !left.contains(4001);
    const left_same = left_values_held and bytesSame(&left, left_snap) and left.getCardinality() == 4001;
    const right_same = listHeld(&right, &rvals, absent, right_snap.card) and bytesSame(&right, right_snap);
    const report = finishReport(fused, ctl, left_snap, right_snap, left_same, right_same);
    try emitPair(init, init.gpa, report);
""",
        rvals=zig_u64_list(right),
        absent=absent,
    )
    assert_fused_f08(
        report,
        inter=2,
        union=union,
        diff_lr=diff_lr,
        diff_rl=diff_rl,
        left_card=4001,
        right_card=4,
    )


def _uncleaned_probe(removed: list[int], partner: list[int], cover: list[int], absent: int) -> dict:
    return run_f08_probe(
        r"""
    const removed = [_]u64{ __REMOVED__ };
    const partner_vals = [_]u64{ __PARTNER__ };
    const cover_vals = [_]u64{ __COVER__ };
    const absent: u64 = __ABSENT__;
    var origin = try buildFrom(allocator, &removed);
    defer origin.deinit();
    var emptied = try origin.clone();
    defer emptied.deinit();
    var partner = try buildFrom(allocator, &partner_vals);
    defer partner.deinit();
    emptied.andInPlace(&partner);
    const emptied_ok = emptied.getCardinality() == 0 and containsNone(&emptied, &removed);
    var cover = try buildFrom(allocator, &cover_vals);
    defer cover.deinit();
    const cover_ok = containsAll(&cover, &removed) and cover.getCardinality() == cover_vals.len;
    const placed = try fullLists(allocator, init.gpa, &emptied, &cover, &[_]u64{}, &cover_vals, absent);
    const emptied_stays = emptied.getCardinality() == 0 and containsNone(&emptied, &removed);
    try emitJson(init, init.gpa,
        "{{\"emptied_ok\":{s},\"cover_ok\":{s},\"emptied_stays\":{s},\"and_lr\":{d},\"and_rl\":{d},\"or_lr\":{d},\"or_rl\":{d},\"diff_lr\":{d},\"diff_rl\":{d},\"mat_and\":{d},\"mat_or\":{d},\"ip_and\":{d},\"ip_diff_lr\":{d},\"ip_diff_rl\":{d},\"left_same\":{s},\"right_same\":{s},\"left_card\":{d},\"right_card\":{d},\"left_len\":{d},\"right_len\":{d},\"left_res\":{d},\"right_res\":{d}}}",
        .{
            jsonBool(emptied_ok), jsonBool(cover_ok), jsonBool(emptied_stays),
            placed.and_lr, placed.and_rl, placed.or_lr, placed.or_rl, placed.diff_lr, placed.diff_rl,
            placed.mat_and, placed.mat_or, placed.ip_and, placed.ip_diff_lr, placed.ip_diff_rl,
            jsonBool(placed.left_same), jsonBool(placed.right_same),
            placed.left_card, placed.right_card, placed.left_len, placed.right_len,
            placed.left_res, placed.right_res,
        },
    );
""",
        removed=zig_u64_list(removed),
        partner=zig_u64_list(partner),
        cover=zig_u64_list(cover),
        absent=absent,
    )


def test_fused_counts_treat_uncleaned_empty_left_as_empty():
    removed, partner, cover, absent = uncleaned_population_f08()
    report = _uncleaned_probe(removed, partner, cover, absent)
    for key in ("emptied_ok", "cover_ok", "emptied_stays", "left_same", "right_same"):
        if require_bool_field(report, key) is not True:
            raise AssertionError(f"{key} is not true")
    cover_card = len(cover)
    for key, want in (
        ("and_lr", 0),
        ("and_rl", 0),
        ("or_lr", cover_card),
        ("or_rl", cover_card),
        ("diff_lr", 0),
        ("diff_rl", cover_card),
        ("mat_and", 0),
        ("mat_or", cover_card),
        ("ip_and", 0),
        ("ip_diff_lr", 0),
        ("ip_diff_rl", cover_card),
        ("left_card", 0),
        ("right_card", cover_card),
    ):
        got = require_int_field(report, key)
        if got != want:
            raise AssertionError(f"{key} is {got}, want {want}")


def test_fused_counts_treat_uncleaned_empty_as_the_other_operand():
    removed, partner, cover, absent = uncleaned_population_f08()
    # Swap: the uncleaned bitmap is on the right. fullLists' diff_rl is
    # right\left when left is emptied; rebuild with cover on the left.
    report = run_f08_probe(
        r"""
    const removed = [_]u64{ __REMOVED__ };
    const partner_vals = [_]u64{ __PARTNER__ };
    const cover_vals = [_]u64{ __COVER__ };
    const absent: u64 = __ABSENT__;
    var origin = try buildFrom(allocator, &removed);
    defer origin.deinit();
    var emptied = try origin.clone();
    defer emptied.deinit();
    var partner = try buildFrom(allocator, &partner_vals);
    defer partner.deinit();
    emptied.andInPlace(&partner);
    const emptied_ok = emptied.getCardinality() == 0 and containsNone(&emptied, &removed);
    var cover = try buildFrom(allocator, &cover_vals);
    defer cover.deinit();
    const cover_ok = containsAll(&cover, &removed);
    const placed = try fullLists(allocator, init.gpa, &cover, &emptied, &cover_vals, &[_]u64{}, absent);
    const emptied_stays = emptied.getCardinality() == 0 and containsNone(&emptied, &removed);
    try emitJson(init, init.gpa,
        "{{\"emptied_ok\":{s},\"cover_ok\":{s},\"emptied_stays\":{s},\"and_lr\":{d},\"or_lr\":{d},\"diff_lr\":{d},\"mat_and\":{d},\"mat_or\":{d},\"ip_and\":{d},\"ip_diff_lr\":{d},\"left_same\":{s},\"right_same\":{s},\"left_card\":{d},\"right_card\":{d}}}",
        .{
            jsonBool(emptied_ok), jsonBool(cover_ok), jsonBool(emptied_stays),
            placed.and_lr, placed.or_lr, placed.diff_lr,
            placed.mat_and, placed.mat_or, placed.ip_and, placed.ip_diff_lr,
            jsonBool(placed.left_same), jsonBool(placed.right_same),
            placed.left_card, placed.right_card,
        },
    );
""",
        removed=zig_u64_list(removed),
        partner=zig_u64_list(partner),
        cover=zig_u64_list(cover),
        absent=absent,
    )
    for key in ("emptied_ok", "cover_ok", "emptied_stays", "left_same", "right_same"):
        if require_bool_field(report, key) is not True:
            raise AssertionError(f"{key} is not true")
    cover_card = len(cover)
    for key, want in (
        ("and_lr", 0),
        ("or_lr", cover_card),
        ("diff_lr", cover_card),
        ("mat_and", 0),
        ("mat_or", cover_card),
        ("ip_and", 0),
        ("ip_diff_lr", cover_card),
        ("left_card", cover_card),
        ("right_card", 0),
    ):
        got = require_int_field(report, key)
        if got != want:
            raise AssertionError(f"{key} is {got}, want {want}")


def test_fused_difference_depends_on_order_when_exclusive_counts_differ():
    left, right, absent = exclusive_pair_f08()
    inter, union, diff_lr, diff_rl = algebra_f08(left, right)
    if diff_lr == diff_rl:
        raise HarnessError("exclusive counts do not differ")
    report = _expect_lists(left, right, absent)
    if require_int_field(report, "diff_lr") == require_int_field(report, "diff_rl"):
        raise AssertionError("fused differences matched on sets with different exclusive counts")
    if require_int_field(report, "diff_lr") != diff_lr or require_int_field(report, "diff_rl") != diff_rl:
        raise AssertionError("fused difference did not match that side's exclusive count")
    if require_int_field(report, "and_lr") != inter or require_int_field(report, "or_lr") != union:
        raise AssertionError("order pair lost intersection or union")


def test_fused_intersection_and_union_ignore_order_on_that_pair():
    left, right, absent = exclusive_pair_f08()
    report = _expect_lists(left, right, absent)
    if require_int_field(report, "and_lr") != require_int_field(report, "and_rl"):
        raise AssertionError("fused intersection depended on operand order")
    if require_int_field(report, "or_lr") != require_int_field(report, "or_rl"):
        raise AssertionError("fused union depended on operand order")


def test_fused_counts_are_integers_and_need_no_released_bitmap():
    left, right, absent = overlapping_pair_f08()
    report = _expect_lists(left, right, absent)
    for key in ("and_lr", "or_lr", "diff_lr", "diff_rl"):
        require_int_field(report, key)


def test_fused_counts_still_return_when_allocations_during_the_calls_are_refused():
    left, right, absent = refuse_pair_f08()
    inter, union, diff_lr, diff_rl = algebra_f08(left, right)
    willing = _expect_lists(left, right, absent)
    refused = run_f08_refuse(
        r"""
    const lvals = [_]u64{ __LVALS__ };
    const rvals = [_]u64{ __RVALS__ };
    const absent: u64 = __ABSENT__;
    var left = try buildFrom(allocator, &lvals);
    defer left.deinit();
    var right = try buildFrom(allocator, &rvals);
    defer right.deinit();
    const left_snap = try takeSnap(init.gpa, &left);
    defer init.gpa.free(left_snap.bytes);
    const right_snap = try takeSnap(init.gpa, &right);
    defer init.gpa.free(right_snap.bytes);
    window.blocked = true;
    const fused = readFused(&left, &right);
    const left_same = listHeld(&left, &lvals, absent, left_snap.card) and bytesSame(&left, left_snap);
    const right_same = listHeld(&right, &rvals, absent, right_snap.card) and bytesSame(&right, right_snap);
    const completed = true;
    window.blocked = false;
    try emitJson(init, init.gpa,
        "{{\"and_lr\":{d},\"and_rl\":{d},\"or_lr\":{d},\"or_rl\":{d},\"diff_lr\":{d},\"diff_rl\":{d},\"left_same\":{s},\"right_same\":{s},\"completed\":{s}}}",
        .{
            fused.and_lr, fused.and_rl, fused.or_lr, fused.or_rl, fused.diff_lr, fused.diff_rl,
            jsonBool(left_same), jsonBool(right_same), jsonBool(completed),
        },
    );
""",
        lvals=zig_u64_list(left),
        rvals=zig_u64_list(right),
        absent=absent,
    )
    proof = run_f08_refuse(
        r"""
    window.blocked = true;
    try proveEveryAllocRefused(allocator, window);
    window.blocked = false;
    try emitJson(init, init.gpa, "{{\"refused\":true}}", .{});
"""
    )
    if require_bool_field(proof, "refused") is not True:
        raise AssertionError("refusal window reported success")
    if require_bool_field(refused, "completed") is not True:
        raise AssertionError("fused calls did not complete while allocations were refused")
    for key, want in (
        ("and_lr", inter),
        ("and_rl", inter),
        ("or_lr", union),
        ("or_rl", union),
        ("diff_lr", diff_lr),
        ("diff_rl", diff_rl),
    ):
        got = require_int_field(refused, key)
        if got != want or got != require_int_field(willing, key):
            raise AssertionError(f"{key} under refusal is {got}, want {want}")
    if require_bool_field(refused, "left_same") is not True or require_bool_field(refused, "right_same") is not True:
        raise AssertionError("operands changed while allocations were refused")


def test_fused_counts_on_a_borrowed_bitmap_do_not_write_the_caller_buffer():
    caller, other, absent = borrow_sides_f08()
    inter, union, diff_lr, diff_rl = algebra_f08(caller, other)
    report = run_f08_probe(
        r"""
    const cvals = [_]u64{ __CVALS__ };
    const ovals = [_]u64{ __OVALS__ };
    const absent: u64 = __ABSENT__;
    var owned = try buildFrom(allocator, &cvals);
    const caller = try owned.toBufferCopy(allocator);
    defer allocator.free(caller);
    owned.deinit();
    const snap = try init.gpa.dupe(u8, caller);
    defer init.gpa.free(snap);
    var borrowed = try klyvmap.Bitmap.fromBuffer(allocator, caller, .borrow);
    defer borrowed.deinit();
    var right = try buildFrom(allocator, &ovals);
    defer right.deinit();
    const right_snap = try takeSnap(init.gpa, &right);
    defer init.gpa.free(right_snap.bytes);
    const fused = readFused(&borrowed, &right);
    const bytes_same = std.mem.eql(u8, caller, snap);
    var again = try klyvmap.Bitmap.fromBuffer(allocator, caller, .borrow);
    defer again.deinit();
    const reopened = containsAll(&again, &cvals) and again.getCardinality() == cvals.len and !again.contains(absent);
    const right_same = listHeld(&right, &ovals, absent, right_snap.card) and bytesSame(&right, right_snap);
    var scribbled = try init.gpa.dupe(u8, snap);
    defer init.gpa.free(scribbled);
    scribbled[0] ^= 0xff;
    const saw_change = !std.mem.eql(u8, scribbled, snap);
    if (!saw_change) return error.ObserverSilent;
    const res = @intFromPtr(caller.ptr) % 8;
    try emitJson(init, init.gpa,
        "{{\"and_lr\":{d},\"and_rl\":{d},\"or_lr\":{d},\"or_rl\":{d},\"diff_lr\":{d},\"diff_rl\":{d},\"bytes_same\":{s},\"reopened\":{s},\"right_same\":{s},\"saw_change\":{s},\"res\":{d}}}",
        .{
            fused.and_lr, fused.and_rl, fused.or_lr, fused.or_rl, fused.diff_lr, fused.diff_rl,
            jsonBool(bytes_same), jsonBool(reopened), jsonBool(right_same), jsonBool(saw_change), res,
        },
    );
""",
        cvals=zig_u64_list(caller),
        ovals=zig_u64_list(other),
        absent=absent,
    )
    for key, want in (
        ("and_lr", inter),
        ("and_rl", inter),
        ("or_lr", union),
        ("or_rl", union),
        ("diff_lr", diff_lr),
        ("diff_rl", diff_rl),
    ):
        got = require_int_field(report, key)
        if got != want:
            raise AssertionError(f"{key} is {got}, want {want}")
    for key in ("bytes_same", "reopened", "right_same", "saw_change"):
        if require_bool_field(report, key) is not True:
            raise AssertionError(f"{key} is not true")
    if require_int_field(report, "res") != 0:
        raise AssertionError("borrowed caller buffer is not 8-byte aligned")


def test_fused_cardinality_path_performs_no_file_or_network_io():
    left = [unpublished_u64_f08()]
    right = [unpublished_u64_f08(left)]
    honest = wrap_f08_probe(
        fill_u64(
            r"""
    const lvals = [_]u64{ __LVALS__ };
    const rvals = [_]u64{ __RVALS__ };
    var a = try buildFrom(allocator, &lvals);
    defer a.deinit();
    var b = try buildFrom(allocator, &rvals);
    defer b.deinit();
    _ = readFused(&a, &b);
    _ = readFused(&b, &a);
    const view = a.toBuffer();
    if (view.len == 0) return error.EmptyEmit;
    _ = view[0];
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
""",
            lvals=zig_u64_list(left),
            rvals=zig_u64_list(right),
        )
    )
    vandal = wrap_f08_probe(
        r"""
    var cwd = std.Io.Dir.cwd();
    var f1 = try cwd.createFile(init.io, "cwd_side.txt", .{});
    f1.close(init.io);
    var f2 = try std.Io.Dir.createFileAbsolute(init.io, "__HOME_FILE__", .{});
    f2.close(init.io);
    var f3 = try std.Io.Dir.createFileAbsolute(init.io, "__TMP_FILE__", .{});
    f3.close(init.io);
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
"""
    )
    net_vandal = wrap_f08_probe(
        r"""
    const linux = std.os.linux;
    _ = linux.socket(linux.AF.INET, linux.SOCK.STREAM, 0);
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
"""
    )
    with workspace() as ws:
        tmp = ws.mkdir("tmp")
        ws.env["TMPDIR"] = str(tmp)
        ws.env["TEMP"] = str(tmp)
        ws.env["TMP"] = str(tmp)
        home_file = (Path(ws.home) / "home_side.txt").resolve()
        tmp_file = (tmp / "tmp_side.txt").resolve()
        vandal_src = fill_u64(vandal, home_file=str(home_file), tmp_file=str(tmp_file))
        for label, source in (("honest", honest), ("vandal", vandal_src), ("net", net_vandal)):
            compiled = compile_product_source(ws, source, relpath=f"{label}.zig", output=label)
            if compiled.returncode != 0:
                raise HarnessError(f"{label} failed to compile\n{compiled.stderr_text}")
        roots = (ws.path, ws.home, tmp)
        harness_names = {"honest.zig", "vandal.zig", "net.zig", "honest", "vandal", "net"}
        before: set[Path] = set()
        for root in roots:
            before |= _walk_regular_files(root)
        run = ws.run_command([str(ws.resolve("honest"))], timeout=DEFAULT_TIMEOUT)
        if run.returncode != 0:
            raise HarnessError(f"fused I/O probe exited {run.returncode}\n{run.stderr_text}")
        created = product_created_files(before=before, roots=roots, ignore_names=harness_names)
        if created != set():
            raise AssertionError(f"fused path wrote files: {created}")

        before_v: set[Path] = set()
        for root in roots:
            before_v |= _walk_regular_files(root)
        run_v = ws.run_command([str(ws.resolve("vandal"))], timeout=DEFAULT_TIMEOUT)
        if run_v.returncode != 0:
            raise HarnessError(f"file positive control exited {run_v.returncode}\n{run_v.stderr_text}")
        created_v = product_created_files(before=before_v, roots=roots, ignore_names=harness_names)
        names_v = {path.name for path in created_v}
        if "cwd_side.txt" not in names_v:
            raise AssertionError(f"workspace write not observed: {created_v}")
        if "home_side.txt" not in names_v:
            raise AssertionError(f"HOME write not observed: {created_v}")
        if "tmp_side.txt" not in names_v:
            raise AssertionError(f"TMPDIR write not observed: {created_v}")

        run_w, writes, reads = run_traced_file_writes(
            ws, [str(ws.resolve("honest"))], timeout=DEFAULT_TIMEOUT
        )
        if run_w.returncode != 0:
            raise HarnessError(f"traced fused probe exited {run_w.returncode}\n{run_w.stderr_text}")
        if file_write_syscalls_in_trace(writes) != []:
            raise AssertionError(f"fused path wrote through syscalls: {writes}")
        if unexpected_file_reads_in_trace(reads) != []:
            raise AssertionError(f"fused path read unexpected files: {reads}")

        run_n, hits = run_traced_arch_network(
            ws, [str(ws.resolve("honest"))], timeout=DEFAULT_TIMEOUT
        )
        if run_n.returncode != 0:
            raise HarnessError(f"traced fused network probe exited {run_n.returncode}\n{run_n.stderr_text}")
        if network_syscalls_in_trace(hits) != []:
            raise AssertionError(f"fused path opened a network syscall: {hits}")

        run_nv, vandal_hits = run_traced_network(
            ws, [str(ws.resolve("net"))], timeout=DEFAULT_TIMEOUT
        )
        if run_nv.returncode != 0:
            raise HarnessError(f"network positive control exited {run_nv.returncode}\n{run_nv.stderr_text}")
        if not network_syscalls_in_trace(vandal_hits):
            raise AssertionError("network positive control observed nothing")


# ---------------------------------------------------------------------------
# Fused counts when each operand holds 2^k - 1, 2^k or 2^k + 1 values of one prefix
# ---------------------------------------------------------------------------


def test_fused_counts_are_exact_when_each_operand_holds_each_population_of_one_prefix():
    # Left holds c values of one prefix plus the two values just outside it;
    # right holds another c values of that prefix, shifted by x. The counts
    # follow from the ranges: |L & R| = c - x, |L | R| = c + x + 2,
    # |L \ R| = x + 2, |R \ L| = x. Operands are checked unchanged.
    report = run_block_sweep(
        r"""
    var ok = true;
    var self_ok = true;
    var intact = true;
    var seen: u64 = 0;
    for (checkpoints) |c| {
        const x: u64 = @min(c, (65536 - c) / 2);
        var l = try klyvmap.Bitmap.init(allocator);
        defer l.deinit();
        _ = try block.setRange(&l, 0, c);
        _ = try block.setEdges(&l);
        var r = try klyvmap.Bitmap.init(allocator);
        defer r.deinit();
        _ = try block.setRangeDown(&r, x, x + c);
        const lsnap = try init.gpa.dupe(u8, l.toBuffer());
        defer init.gpa.free(lsnap);
        const rsnap = try init.gpa.dupe(u8, r.toBuffer());
        defer init.gpa.free(rsnap);
        ok = ok and l.andCardinality(&r) == c - x and r.andCardinality(&l) == c - x;
        ok = ok and l.orCardinality(&r) == c + x + 2 and r.orCardinality(&l) == c + x + 2;
        ok = ok and l.andNotCardinality(&r) == x + 2 and r.andNotCardinality(&l) == x;
        self_ok = self_ok and l.andCardinality(&l) == c + 2 and l.orCardinality(&l) == c + 2 and l.andNotCardinality(&l) == 0;
        self_ok = self_ok and r.andCardinality(&r) == c and r.orCardinality(&r) == c and r.andNotCardinality(&r) == 0;
        intact = intact and std.mem.eql(u8, l.toBuffer(), lsnap) and std.mem.eql(u8, r.toBuffer(), rsnap);
        intact = intact and l.getCardinality() == c + 2 and r.getCardinality() == c;
        intact = intact and block.walk(&l, 0, c, true) and block.walk(&r, x, x + c, false);
        seen += 1;
    }
    try emitJson(init, init.gpa,
        "{{\"ok\":{s},\"self_ok\":{s},\"intact\":{s},\"seen\":{d}}}",
        .{ jsonBool(ok), jsonBool(self_ok), jsonBool(intact), seen },
    );
"""
    )
    require_sweep_true(report, "ok", "self_ok", "intact")
    require_sweep_seen(report, "seen", len(block_checkpoints()))
