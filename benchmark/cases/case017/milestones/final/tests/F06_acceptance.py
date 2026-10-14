# feature: F06
"""FP-06: materializing intersection, union, and n-ary union.

Assertions follow Full_PRD.original.md FP-06 (L229–L252) and the
pre-FP sentences these three entries can trigger.
"""

from __future__ import annotations

from pathlib import Path

from F01_helpers import (
    _walk_regular_files,
    fill_u64,
    network_syscalls_in_trace,
    product_created_files,
    require_empty_snapshot,
    run_traced_network,
)
from F02_helpers import require_bool_field, require_int_field, shuffle_not_sorted, zig_u64_list
from F03_helpers import compile_probe_or_raise, require_strictly_ascending_once
from F04_helpers import (
    file_write_syscalls_in_trace,
    require_emit_shape,
    run_traced_arch_network,
    run_traced_file_writes,
    unexpected_file_reads_in_trace,
)
from F06_helpers import (
    bitmap_block,
    consecutive_run_f06,
    disjoint_sides_f06,
    draw_distinct_f06,
    fresh_prefix_values_f06,
    require_probe_true,
    run_f06_probe,
    split_pair_f06,
    unpublished_nary_count_f06,
    unpublished_pair_size_f06,
    unpublished_u64_f06,
    values_at_named_position_f06,
    wrap_f06_probe,
)
from F02_helpers import (
    block_checkpoints,
    require_sweep_seen,
    require_sweep_true,
    run_block_sweep,
    shrink_checkpoints,
)
from _helpers import DEFAULT_TIMEOUT, HarnessError, workspace

_INTERSECTION_ORDERS = r"""
    const left_ins = [_]u64{ __LEFT_INS__ };
    const right_ins = [_]u64{ __RIGHT_INS__ };
    const left_sorted = [_]u64{ __LEFT_SORTED__ };
    const right_sorted = [_]u64{ __RIGHT_SORTED__ };
    const expected = [_]u64{ __EXPECTED__ };
    const only_left = [_]u64{ __ONLY_LEFT__ };
    const only_right = [_]u64{ __ONLY_RIGHT__ };
    const absent: u64 = __ABSENT__;
    var left = try buildFrom(allocator, &left_ins);
    defer left.deinit();
    var right = try buildFrom(allocator, &right_ins);
    defer right.deinit();
    var ab = try klyvmap.Bitmap.And(allocator, &left, &right);
    defer ab.deinit();
    var ba = try klyvmap.Bitmap.And(allocator, &right, &left);
    defer ba.deinit();
    const ab_seq = valuesMatch(&ab, &expected);
    const ba_seq = valuesMatch(&ba, &expected);
    const ab_mem = containsAll(&ab, &expected) and containsNone(&ab, &only_left) and containsNone(&ab, &only_right) and !ab.contains(absent);
    const ba_mem = containsAll(&ba, &expected) and containsNone(&ba, &only_left) and containsNone(&ba, &only_right) and !ba.contains(absent);
    const ab_ext = extremaMatch(&ab, &expected);
    const ba_ext = extremaMatch(&ba, &expected);
    const ops = valuesMatch(&left, &left_sorted) and valuesMatch(&right, &right_sorted);
    try emitJson(init, init.gpa,
        "{{\"ab_seq\":{s},\"ba_seq\":{s},\"ab_mem\":{s},\"ba_mem\":{s},\"ab_ext\":{s},\"ba_ext\":{s},\"ops\":{s}}}",
        .{ jsonBool(ab_seq), jsonBool(ba_seq), jsonBool(ab_mem), jsonBool(ba_mem), jsonBool(ab_ext), jsonBool(ba_ext), jsonBool(ops) },
    );
"""

_UNION_ORDERS = r"""
    const left_ins = [_]u64{ __LEFT_INS__ };
    const right_ins = [_]u64{ __RIGHT_INS__ };
    const left_sorted = [_]u64{ __LEFT_SORTED__ };
    const right_sorted = [_]u64{ __RIGHT_SORTED__ };
    const expected = [_]u64{ __EXPECTED__ };
    const absent: u64 = __ABSENT__;
    var left = try buildFrom(allocator, &left_ins);
    defer left.deinit();
    var right = try buildFrom(allocator, &right_ins);
    defer right.deinit();
    var ab = try klyvmap.Bitmap.Or(allocator, &left, &right);
    defer ab.deinit();
    var ba = try klyvmap.Bitmap.Or(allocator, &right, &left);
    defer ba.deinit();
    const ab_seq = valuesMatch(&ab, &expected);
    const ba_seq = valuesMatch(&ba, &expected);
    const ab_mem = containsAll(&ab, &expected) and !ab.contains(absent);
    const ba_mem = containsAll(&ba, &expected) and !ba.contains(absent);
    const ab_ext = extremaMatch(&ab, &expected);
    const ba_ext = extremaMatch(&ba, &expected);
    const ops = valuesMatch(&left, &left_sorted) and valuesMatch(&right, &right_sorted);
    try emitJson(init, init.gpa,
        "{{\"ab_seq\":{s},\"ba_seq\":{s},\"ab_mem\":{s},\"ba_mem\":{s},\"ab_ext\":{s},\"ba_ext\":{s},\"ops\":{s}}}",
        .{ jsonBool(ab_seq), jsonBool(ba_seq), jsonBool(ab_mem), jsonBool(ba_mem), jsonBool(ab_ext), jsonBool(ba_ext), jsonBool(ops) },
    );
"""

_ORDER_KEYS = ("ab_seq", "ba_seq", "ab_mem", "ba_mem", "ab_ext", "ba_ext", "ops")


def _lit(values: list[int]) -> str:
    ordered = sorted(values)
    require_strictly_ascending_once(ordered, cardinality=len(ordered))
    return zig_u64_list(ordered)


def _ins(values: list[int]) -> str:
    return zig_u64_list(shuffle_not_sorted(values))


def _exclusive(side: list[int], other: list[int]) -> list[int]:
    only = sorted(set(side) - set(other))
    if not only:
        raise HarnessError("exclusive side is empty")
    return only


def _assert_orders(report) -> None:
    require_probe_true(report, *_ORDER_KEYS)


def _pair_subs(left: list[int], right: list[int], expected: list[int], absent: int) -> dict:
    return {
        "left_ins": _ins(left),
        "right_ins": _ins(right),
        "left_sorted": _lit(left),
        "right_sorted": _lit(right),
        "expected": _lit(expected),
        "absent": absent,
    }


def _emit_snap(prefix: str) -> str:
    """Zig statements and a format fragment are filled by the caller.

    This returns the JSON object fragment's field list for one snapshot
    whose zig locals are ``{prefix}snap``, ``{prefix}min``, ``{prefix}max``.
    """
    return (
        f'"{prefix}empty":{{s}},"{prefix}cardinality":{{d}},"{prefix}contains0":{{s}},'
        f'"{prefix}min":{{s}},"{prefix}max":{{s}},"{prefix}exhausted_twice":{{s}}'
    )


def _snap_locals(name: str, bitmap: str) -> str:
    return (
        f"    const {name} = emptyView(&{bitmap});\n"
        f"    const {name}_min = try optU64Json(init.gpa, {bitmap}.minimum());\n"
        f"    defer init.gpa.free({name}_min);\n"
        f"    const {name}_max = try optU64Json(init.gpa, {bitmap}.maximum());\n"
        f"    defer init.gpa.free({name}_max);\n"
    )


def _assert_snap(report, prefix: str = "") -> None:
    require_empty_snapshot(report, prefix=prefix)
    require_probe_true(report, f"{prefix}exhausted_twice")


# ---------------------------------------------------------------------------
# A. Intersection equals the values present on both sides
# ---------------------------------------------------------------------------


def test_intersection_of_1500_matches_set_intersection_operands_unchanged():
    left, right, expected, absent = split_pair_f06(1500)
    subs = _pair_subs(left, right, expected, absent)
    subs["only_left"] = _lit(_exclusive(left, right))
    subs["only_right"] = _lit(_exclusive(right, left))
    report = run_f06_probe(_INTERSECTION_ORDERS, **subs)
    _assert_orders(report)


def test_intersection_of_unpublished_size_matches_set_intersection():
    left, right, expected, absent = split_pair_f06(unpublished_pair_size_f06())
    subs = _pair_subs(left, right, expected, absent)
    subs["only_left"] = _lit(_exclusive(left, right))
    subs["only_right"] = _lit(_exclusive(right, left))
    report = run_f06_probe(_INTERSECTION_ORDERS, **subs)
    _assert_orders(report)


def test_intersection_containing_zero_yields_zero_then_later_values():
    shared = unpublished_u64_f06(above=1 << 32)
    left_only = unpublished_u64_f06({shared}, above=1 << 32)
    right_only = unpublished_u64_f06({shared, left_only}, above=1 << 32)
    left = [0, shared, left_only]
    right = [0, shared, right_only]
    expected = sorted({0, shared})
    rest = expected[1:]
    report = run_f06_probe(
        r"""
    const left_ins = [_]u64{ __LEFT_INS__ };
    const right_ins = [_]u64{ __RIGHT_INS__ };
    const left_sorted = [_]u64{ __LEFT_SORTED__ };
    const right_sorted = [_]u64{ __RIGHT_SORTED__ };
    const expected = [_]u64{ __EXPECTED__ };
    const rest = [_]u64{ __REST__ };
    const left_only: u64 = __LEFT_ONLY__;
    const right_only: u64 = __RIGHT_ONLY__;
    var left = try buildFrom(allocator, &left_ins);
    defer left.deinit();
    var right = try buildFrom(allocator, &right_ins);
    defer right.deinit();
    var ab = try klyvmap.Bitmap.And(allocator, &left, &right);
    defer ab.deinit();
    var ba = try klyvmap.Bitmap.And(allocator, &right, &left);
    defer ba.deinit();
    const ab_ok = valuesMatch(&ab, &expected) and zeroThenRest(&ab, &rest) and ab.contains(0) and !ab.contains(left_only) and !ab.contains(right_only) and extremaMatch(&ab, &expected);
    const ba_ok = valuesMatch(&ba, &expected) and zeroThenRest(&ba, &rest) and ba.contains(0) and extremaMatch(&ba, &expected);
    const ops = valuesMatch(&left, &left_sorted) and valuesMatch(&right, &right_sorted);
    try emitJson(init, init.gpa, "{{\"ab_ok\":{s},\"ba_ok\":{s},\"ops\":{s}}}", .{ jsonBool(ab_ok), jsonBool(ba_ok), jsonBool(ops) });
""",
        left_ins=_ins(left),
        right_ins=_ins(right),
        left_sorted=_lit(left),
        right_sorted=_lit(right),
        expected=_lit(expected),
        rest=_lit(rest),
        left_only=left_only,
        right_only=right_only,
    )
    require_probe_true(report, "ab_ok", "ba_ok", "ops")


# ---------------------------------------------------------------------------
# B. Disjoint four-value intersection is empty and still accepts a set
# ---------------------------------------------------------------------------


def _disjoint_body(tag: str) -> str:
    return f"""
    const {tag}_l_ins = [_]u64{{ __{tag.upper()}_L_INS__ }};
    const {tag}_r_ins = [_]u64{{ __{tag.upper()}_R_INS__ }};
    const {tag}_l_sorted = [_]u64{{ __{tag.upper()}_L_SORTED__ }};
    const {tag}_r_sorted = [_]u64{{ __{tag.upper()}_R_SORTED__ }};
    const {tag}_fresh: u64 = __{tag.upper()}_FRESH__;
    var {tag}_l = try buildFrom(allocator, &{tag}_l_ins);
    defer {tag}_l.deinit();
    var {tag}_r = try buildFrom(allocator, &{tag}_r_ins);
    defer {tag}_r.deinit();
    var {tag}_a = try klyvmap.Bitmap.And(allocator, &{tag}_l, &{tag}_r);
    const {tag}_s1 = emptyView(&{tag}_a);
    const {tag}_min1 = try optU64Json(init.gpa, {tag}_a.minimum());
    defer init.gpa.free({tag}_min1);
    const {tag}_max1 = try optU64Json(init.gpa, {tag}_a.maximum());
    defer init.gpa.free({tag}_max1);
    const {tag}_added = try {tag}_a.set({tag}_fresh);
    const {tag}_has = {tag}_a.contains({tag}_fresh);
    const {tag}_card1 = {tag}_a.getCardinality() == 1;
    const {tag}_ops1 = valuesMatch(&{tag}_l, &{tag}_l_sorted) and valuesMatch(&{tag}_r, &{tag}_r_sorted) and !{tag}_l.contains({tag}_fresh) and !{tag}_r.contains({tag}_fresh);
    {tag}_a.deinit();
    var {tag}_b = try klyvmap.Bitmap.And(allocator, &{tag}_l, &{tag}_r);
    defer {tag}_b.deinit();
    const {tag}_s2 = emptyView(&{tag}_b);
    const {tag}_min2 = try optU64Json(init.gpa, {tag}_b.minimum());
    defer init.gpa.free({tag}_min2);
    const {tag}_max2 = try optU64Json(init.gpa, {tag}_b.maximum());
    defer init.gpa.free({tag}_max2);
    const {tag}_no_fresh = !{tag}_b.contains({tag}_fresh);
    const {tag}_ops2 = valuesMatch(&{tag}_l, &{tag}_l_sorted) and valuesMatch(&{tag}_r, &{tag}_r_sorted);
"""


def test_disjoint_four_value_intersection_is_empty_operands_unchanged():
    pairs = []
    used: set[int] = set()
    for _ in range(2):
        left, right = disjoint_sides_f06(4)
        if set(left) & used or set(right) & used:
            raise HarnessError("disjoint pairs collided")
        used |= set(left) | set(right)
        if not any(v > (1 << 32) for v in left) or not any(v > (1 << 32) for v in right):
            raise HarnessError("disjoint side has no value above 2^32")
        fresh = unpublished_u64_f06(used)
        used.add(fresh)
        pairs.append((left, right, fresh))
    subs = {}
    for tag, (left, right, fresh) in zip(("p", "q"), pairs):
        subs[f"{tag}_l_ins"] = _ins(left)
        subs[f"{tag}_r_ins"] = _ins(right)
        subs[f"{tag}_l_sorted"] = _lit(left)
        subs[f"{tag}_r_sorted"] = _lit(right)
        subs[f"{tag}_fresh"] = fresh
    body = _disjoint_body("p") + _disjoint_body("q") + r"""
    const part_p = try std.fmt.allocPrint(init.gpa,
        "{{\"p_empty\":{s},\"p_cardinality\":{d},\"p_contains0\":{s},\"p_min\":{s},\"p_max\":{s},\"p_exhausted_twice\":{s},\"p_added\":{s},\"p_has\":{s},\"p_card1\":{s},\"p_ops1\":{s},\"p_second_empty\":{s},\"p_second_cardinality\":{d},\"p_second_contains0\":{s},\"p_second_min\":{s},\"p_second_max\":{s},\"p_second_exhausted_twice\":{s},\"p_no_fresh\":{s},\"p_ops2\":{s},",
        .{
            jsonBool(p_s1.empty), p_s1.card, jsonBool(p_s1.c0), p_min1, p_max1, jsonBool(p_s1.exh),
            jsonBool(p_added), jsonBool(p_has), jsonBool(p_card1), jsonBool(p_ops1),
            jsonBool(p_s2.empty), p_s2.card, jsonBool(p_s2.c0), p_min2, p_max2, jsonBool(p_s2.exh),
            jsonBool(p_no_fresh), jsonBool(p_ops2),
        },
    );
    defer init.gpa.free(part_p);
    const part_q = try std.fmt.allocPrint(init.gpa,
        "\"q_empty\":{s},\"q_cardinality\":{d},\"q_contains0\":{s},\"q_min\":{s},\"q_max\":{s},\"q_exhausted_twice\":{s},\"q_added\":{s},\"q_has\":{s},\"q_card1\":{s},\"q_ops1\":{s},\"q_second_empty\":{s},\"q_second_cardinality\":{d},\"q_second_contains0\":{s},\"q_second_min\":{s},\"q_second_max\":{s},\"q_second_exhausted_twice\":{s},\"q_no_fresh\":{s},\"q_ops2\":{s}}}",
        .{
            jsonBool(q_s1.empty), q_s1.card, jsonBool(q_s1.c0), q_min1, q_max1, jsonBool(q_s1.exh),
            jsonBool(q_added), jsonBool(q_has), jsonBool(q_card1), jsonBool(q_ops1),
            jsonBool(q_s2.empty), q_s2.card, jsonBool(q_s2.c0), q_min2, q_max2, jsonBool(q_s2.exh),
            jsonBool(q_no_fresh), jsonBool(q_ops2),
        },
    );
    defer init.gpa.free(part_q);
    try writeStdout(init, part_p);
    try writeStdout(init, part_q);
"""
    report = run_f06_probe(body, **subs)
    _assert_snap(report, "p_")
    _assert_snap(report, "p_second_")
    _assert_snap(report, "q_")
    _assert_snap(report, "q_second_")
    require_probe_true(
        report,
        "p_added",
        "p_has",
        "p_card1",
        "p_ops1",
        "p_no_fresh",
        "p_ops2",
        "q_added",
        "q_has",
        "q_card1",
        "q_ops1",
        "q_no_fresh",
        "q_ops2",
    )


# ---------------------------------------------------------------------------
# C. Intersection with the same values, with itself, and with empty
# ---------------------------------------------------------------------------


def _same_set_then_alien(op: str) -> str:
    body = r"""
    const ins = [_]u64{ __INS__ };
    const sorted = [_]u64{ __SORTED__ };
    const fresh: u64 = __FRESH__;
    var a = try buildFrom(allocator, &ins);
    defer a.deinit();
    var b = try buildFrom(allocator, &ins);
    defer b.deinit();
    var res = try klyvmap.Bitmap.OPNAME(allocator, &a, &b);
    defer res.deinit();
    const seq = valuesMatch(&res, &sorted) and containsAll(&res, &sorted) and extremaMatch(&res, &sorted);
    const ops = valuesMatch(&a, &sorted) and valuesMatch(&b, &sorted);
    const added = try res.set(fresh);
    const has = res.contains(fresh);
    const not_a = !a.contains(fresh);
    const not_b = !b.contains(fresh);
    const ops_after = valuesMatch(&a, &sorted) and valuesMatch(&b, &sorted);
    try emitJson(init, init.gpa,
        "{{\"seq\":{s},\"ops\":{s},\"added\":{s},\"has\":{s},\"not_a\":{s},\"not_b\":{s},\"ops_after\":{s}}}",
        .{ jsonBool(seq), jsonBool(ops), jsonBool(added), jsonBool(has), jsonBool(not_a), jsonBool(not_b), jsonBool(ops_after) },
    );
"""
    if op not in ("And", "Or"):
        raise HarnessError(f"unknown materializing op {op}")
    return body.replace("OPNAME", op)


def test_intersection_of_two_bitmaps_with_the_same_values_equals_that_set():
    values = draw_distinct_f06(unpublished_pair_size_f06())
    fresh = unpublished_u64_f06(set(values))
    report = run_f06_probe(
        _same_set_then_alien("And"),
        ins=_ins(values),
        sorted=_lit(values),
        fresh=fresh,
    )
    require_probe_true(report, "seq", "ops", "added", "has", "not_a", "not_b", "ops_after")


def test_intersection_of_a_bitmap_with_itself_is_a_new_bitmap_of_that_set():
    values = draw_distinct_f06(unpublished_pair_size_f06())
    fresh = unpublished_u64_f06(set(values))
    report = run_f06_probe(
        r"""
    const ins = [_]u64{ __INS__ };
    const sorted = [_]u64{ __SORTED__ };
    const fresh: u64 = __FRESH__;
    var bm = try buildFrom(allocator, &ins);
    defer bm.deinit();
    var res = try klyvmap.Bitmap.And(allocator, &bm, &bm);
    defer res.deinit();
    const seq = valuesMatch(&res, &sorted) and containsAll(&res, &sorted) and extremaMatch(&res, &sorted);
    const ops = valuesMatch(&bm, &sorted);
    const added = try res.set(fresh);
    const has = res.contains(fresh);
    const not_on = !bm.contains(fresh);
    const ops_after = valuesMatch(&bm, &sorted);
    try emitJson(init, init.gpa,
        "{{\"seq\":{s},\"ops\":{s},\"added\":{s},\"has\":{s},\"not_on\":{s},\"ops_after\":{s}}}",
        .{ jsonBool(seq), jsonBool(ops), jsonBool(added), jsonBool(has), jsonBool(not_on), jsonBool(ops_after) },
    );
""",
        ins=_ins(values),
        sorted=_lit(values),
        fresh=fresh,
    )
    require_probe_true(report, "seq", "ops", "added", "has", "not_on", "ops_after")


def test_intersection_with_empty_is_empty_either_order():
    values = draw_distinct_f06(unpublished_pair_size_f06())
    fresh_ab = unpublished_u64_f06(set(values))
    fresh_ba = unpublished_u64_f06(set(values) | {fresh_ab})
    report = run_f06_probe(
        r"""
    const ins = [_]u64{ __INS__ };
    const sorted = [_]u64{ __SORTED__ };
    const fresh_ab: u64 = __FRESH_AB__;
    const fresh_ba: u64 = __FRESH_BA__;
    var full = try buildFrom(allocator, &ins);
    defer full.deinit();
    var empty_bm = try klyvmap.Bitmap.init(allocator);
    defer empty_bm.deinit();

    var ab = try klyvmap.Bitmap.And(allocator, &full, &empty_bm);
    const ab_s = emptyView(&ab);
    const ab_min = try optU64Json(init.gpa, ab.minimum());
    defer init.gpa.free(ab_min);
    const ab_max = try optU64Json(init.gpa, ab.maximum());
    defer init.gpa.free(ab_max);
    const ab_added = try ab.set(fresh_ab);
    const ab_has = ab.contains(fresh_ab);
    const ab_card1 = ab.getCardinality() == 1;
    const ab_full_same = valuesMatch(&full, &sorted) and !full.contains(fresh_ab);
    const ab_empty_still = emptyView(&empty_bm);
    const ab_empty_min = try optU64Json(init.gpa, empty_bm.minimum());
    defer init.gpa.free(ab_empty_min);
    const ab_empty_max = try optU64Json(init.gpa, empty_bm.maximum());
    defer init.gpa.free(ab_empty_max);
    const ab_not_empty = !empty_bm.contains(fresh_ab);
    ab.deinit();
    var ab2 = try klyvmap.Bitmap.And(allocator, &full, &empty_bm);
    defer ab2.deinit();
    const ab2_s = emptyView(&ab2);
    const ab2_min = try optU64Json(init.gpa, ab2.minimum());
    defer init.gpa.free(ab2_min);
    const ab2_max = try optU64Json(init.gpa, ab2.maximum());
    defer init.gpa.free(ab2_max);
    const ab2_no = !ab2.contains(fresh_ab);

    var ba = try klyvmap.Bitmap.And(allocator, &empty_bm, &full);
    const ba_s = emptyView(&ba);
    const ba_min = try optU64Json(init.gpa, ba.minimum());
    defer init.gpa.free(ba_min);
    const ba_max = try optU64Json(init.gpa, ba.maximum());
    defer init.gpa.free(ba_max);
    const ba_added = try ba.set(fresh_ba);
    const ba_has = ba.contains(fresh_ba);
    const ba_card1 = ba.getCardinality() == 1;
    const ba_full_same = valuesMatch(&full, &sorted) and !full.contains(fresh_ba);
    const ba_empty_still = emptyView(&empty_bm);
    const ba_empty_min = try optU64Json(init.gpa, empty_bm.minimum());
    defer init.gpa.free(ba_empty_min);
    const ba_empty_max = try optU64Json(init.gpa, empty_bm.maximum());
    defer init.gpa.free(ba_empty_max);
    ba.deinit();
    var ba2 = try klyvmap.Bitmap.And(allocator, &empty_bm, &full);
    defer ba2.deinit();
    const ba2_s = emptyView(&ba2);
    const ba2_min = try optU64Json(init.gpa, ba2.minimum());
    defer init.gpa.free(ba2_min);
    const ba2_max = try optU64Json(init.gpa, ba2.maximum());
    defer init.gpa.free(ba2_max);
    const ba2_no = !ba2.contains(fresh_ba);
    const full_final = valuesMatch(&full, &sorted);

    const part_ab = try std.fmt.allocPrint(init.gpa,
        "{{\"ab_empty\":{s},\"ab_cardinality\":{d},\"ab_contains0\":{s},\"ab_min\":{s},\"ab_max\":{s},\"ab_exhausted_twice\":{s},\"ab_added\":{s},\"ab_has\":{s},\"ab_card1\":{s},\"ab_full_same\":{s},\"ab_e_empty\":{s},\"ab_e_cardinality\":{d},\"ab_e_contains0\":{s},\"ab_e_min\":{s},\"ab_e_max\":{s},\"ab_e_exhausted_twice\":{s},\"ab_not_empty\":{s},\"ab2_empty\":{s},\"ab2_cardinality\":{d},\"ab2_contains0\":{s},\"ab2_min\":{s},\"ab2_max\":{s},\"ab2_exhausted_twice\":{s},\"ab2_no\":{s},",
        .{
            jsonBool(ab_s.empty), ab_s.card, jsonBool(ab_s.c0), ab_min, ab_max, jsonBool(ab_s.exh),
            jsonBool(ab_added), jsonBool(ab_has), jsonBool(ab_card1), jsonBool(ab_full_same),
            jsonBool(ab_empty_still.empty), ab_empty_still.card, jsonBool(ab_empty_still.c0), ab_empty_min, ab_empty_max, jsonBool(ab_empty_still.exh),
            jsonBool(ab_not_empty),
            jsonBool(ab2_s.empty), ab2_s.card, jsonBool(ab2_s.c0), ab2_min, ab2_max, jsonBool(ab2_s.exh),
            jsonBool(ab2_no),
        },
    );
    defer init.gpa.free(part_ab);
    const part_ba = try std.fmt.allocPrint(init.gpa,
        "\"ba_empty\":{s},\"ba_cardinality\":{d},\"ba_contains0\":{s},\"ba_min\":{s},\"ba_max\":{s},\"ba_exhausted_twice\":{s},\"ba_added\":{s},\"ba_has\":{s},\"ba_card1\":{s},\"ba_full_same\":{s},\"ba_e_empty\":{s},\"ba_e_cardinality\":{d},\"ba_e_contains0\":{s},\"ba_e_min\":{s},\"ba_e_max\":{s},\"ba_e_exhausted_twice\":{s},\"ba2_empty\":{s},\"ba2_cardinality\":{d},\"ba2_contains0\":{s},\"ba2_min\":{s},\"ba2_max\":{s},\"ba2_exhausted_twice\":{s},\"ba2_no\":{s},\"full_final\":{s}}}",
        .{
            jsonBool(ba_s.empty), ba_s.card, jsonBool(ba_s.c0), ba_min, ba_max, jsonBool(ba_s.exh),
            jsonBool(ba_added), jsonBool(ba_has), jsonBool(ba_card1), jsonBool(ba_full_same),
            jsonBool(ba_empty_still.empty), ba_empty_still.card, jsonBool(ba_empty_still.c0), ba_empty_min, ba_empty_max, jsonBool(ba_empty_still.exh),
            jsonBool(ba2_s.empty), ba2_s.card, jsonBool(ba2_s.c0), ba2_min, ba2_max, jsonBool(ba2_s.exh),
            jsonBool(ba2_no), jsonBool(full_final),
        },
    );
    defer init.gpa.free(part_ba);
    try writeStdout(init, part_ab);
    try writeStdout(init, part_ba);
""",
        ins=_ins(values),
        sorted=_lit(values),
        fresh_ab=fresh_ab,
        fresh_ba=fresh_ba,
    )
    _assert_snap(report, "ab_")
    _assert_snap(report, "ab_e_")
    _assert_snap(report, "ab2_")
    _assert_snap(report, "ba_")
    _assert_snap(report, "ba_e_")
    _assert_snap(report, "ba2_")
    require_probe_true(
        report,
        "ab_added",
        "ab_has",
        "ab_card1",
        "ab_full_same",
        "ab_not_empty",
        "ab2_no",
        "ba_added",
        "ba_has",
        "ba_card1",
        "ba_full_same",
        "ba2_no",
        "full_final",
    )


# ---------------------------------------------------------------------------
# D. Union equals the values present on either side
# ---------------------------------------------------------------------------


def test_union_of_1500_matches_set_union_either_order_operands_unchanged():
    left, right, _inter, absent = split_pair_f06(1500)
    expected = sorted(set(left) | set(right))
    if not any(v > (1 << 32) and v not in set(right) for v in left):
        raise HarnessError("union pair has no left-only value above 2^32")
    if not any(v > (1 << 32) and v not in set(left) for v in right):
        raise HarnessError("union pair has no right-only value above 2^32")
    report = run_f06_probe(_UNION_ORDERS, **_pair_subs(left, right, expected, absent))
    _assert_orders(report)


def test_union_of_unpublished_size_matches_set_union_either_order():
    left, right, _inter, absent = split_pair_f06(unpublished_pair_size_f06())
    expected = sorted(set(left) | set(right))
    report = run_f06_probe(_UNION_ORDERS, **_pair_subs(left, right, expected, absent))
    _assert_orders(report)


def test_union_containing_zero_yields_zero_then_later_values():
    left_high = unpublished_u64_f06(above=1 << 32)
    right_high = unpublished_u64_f06({left_high}, above=1 << 32)
    left = [0, left_high]
    right = [0, right_high]
    expected = sorted({0, left_high, right_high})
    if len(expected) != 3 or expected[0] != 0:
        raise HarnessError("zero-union expectation is not 0 then two highs")
    rest = expected[1:]
    report = run_f06_probe(
        r"""
    const left_ins = [_]u64{ __LEFT_INS__ };
    const right_ins = [_]u64{ __RIGHT_INS__ };
    const left_sorted = [_]u64{ __LEFT_SORTED__ };
    const right_sorted = [_]u64{ __RIGHT_SORTED__ };
    const expected = [_]u64{ __EXPECTED__ };
    const rest = [_]u64{ __REST__ };
    var left = try buildFrom(allocator, &left_ins);
    defer left.deinit();
    var right = try buildFrom(allocator, &right_ins);
    defer right.deinit();
    var ab = try klyvmap.Bitmap.Or(allocator, &left, &right);
    defer ab.deinit();
    var ba = try klyvmap.Bitmap.Or(allocator, &right, &left);
    defer ba.deinit();
    const ab_ok = valuesMatch(&ab, &expected) and zeroThenRest(&ab, &rest) and ab.contains(0) and extremaMatch(&ab, &expected) and ab.getCardinality() == 3;
    const ba_ok = valuesMatch(&ba, &expected) and zeroThenRest(&ba, &rest) and ba.contains(0) and extremaMatch(&ba, &expected) and ba.getCardinality() == 3;
    const ops = valuesMatch(&left, &left_sorted) and valuesMatch(&right, &right_sorted);
    try emitJson(init, init.gpa, "{{\"ab_ok\":{s},\"ba_ok\":{s},\"ops\":{s}}}", .{ jsonBool(ab_ok), jsonBool(ba_ok), jsonBool(ops) });
""",
        left_ins=_ins(left),
        right_ins=_ins(right),
        left_sorted=_lit(left),
        right_sorted=_lit(right),
        expected=_lit(expected),
        rest=_lit(rest),
    )
    require_probe_true(report, "ab_ok", "ba_ok", "ops")


def test_union_of_dense_consecutive_run_matches_set_union_either_order():
    _prefix, run = consecutive_run_f06()
    if len(run) < 1000:
        raise HarnessError("dense run is shorter than one thousand")
    picked = run[:: max(1, len(run) // 8)][:8]
    outsider = unpublished_u64_f06(set(run))
    if (outsider >> 16) == (run[0] >> 16):
        raise HarnessError("outsider landed in the dense prefix")
    if not any(v > (1 << 32) for v in run) and outsider <= (1 << 32):
        raise HarnessError("dense union has no value above 2^32")
    other = picked + [outsider]
    left = list(run)
    right = list(other)
    expected = sorted(set(left) | set(right))
    absent = unpublished_u64_f06(set(expected))
    only_dense = sorted(set(run) - set(other))
    if not only_dense:
        raise HarnessError("dense side has no exclusive value")
    report = run_f06_probe(_UNION_ORDERS, **_pair_subs(left, right, expected, absent))
    _assert_orders(report)


# ---------------------------------------------------------------------------
# E. Union with empty, with itself, and with an equal bitmap
# ---------------------------------------------------------------------------


def test_union_with_empty_equals_nonempty_either_order_and_result_is_new():
    values = draw_distinct_f06(unpublished_pair_size_f06())
    absent = unpublished_u64_f06(set(values))
    fresh_ab = unpublished_u64_f06(set(values) | {absent})
    fresh_ba = unpublished_u64_f06(set(values) | {absent, fresh_ab})
    report = run_f06_probe(
        r"""
    const ins = [_]u64{ __INS__ };
    const sorted = [_]u64{ __SORTED__ };
    const absent: u64 = __ABSENT__;
    const fresh_ab: u64 = __FRESH_AB__;
    const fresh_ba: u64 = __FRESH_BA__;
    var full = try buildFrom(allocator, &ins);
    defer full.deinit();
    var empty_bm = try klyvmap.Bitmap.init(allocator);
    defer empty_bm.deinit();
    var ab = try klyvmap.Bitmap.Or(allocator, &full, &empty_bm);
    defer ab.deinit();
    var ba = try klyvmap.Bitmap.Or(allocator, &empty_bm, &full);
    defer ba.deinit();
    const ab_ok = valuesMatch(&ab, &sorted) and containsAll(&ab, &sorted) and extremaMatch(&ab, &sorted) and !ab.contains(absent);
    const ba_ok = valuesMatch(&ba, &sorted) and containsAll(&ba, &sorted) and extremaMatch(&ba, &sorted) and !ba.contains(absent);
    const ab_added = try ab.set(fresh_ab);
    const ab_has = ab.contains(fresh_ab);
    const ab_not_full = !full.contains(fresh_ab);
    const ba_added = try ba.set(fresh_ba);
    const ba_has = ba.contains(fresh_ba);
    const ba_not_full = !full.contains(fresh_ba);
    const empty_s = emptyView(&empty_bm);
    const empty_min = try optU64Json(init.gpa, empty_bm.minimum());
    defer init.gpa.free(empty_min);
    const empty_max = try optU64Json(init.gpa, empty_bm.maximum());
    defer init.gpa.free(empty_max);
    const full_same = valuesMatch(&full, &sorted);
    const empty_lacks = !empty_bm.contains(fresh_ab) and !empty_bm.contains(fresh_ba);
    try emitJson(init, init.gpa,
        "{{\"ab_ok\":{s},\"ba_ok\":{s},\"ab_added\":{s},\"ab_has\":{s},\"ab_not_full\":{s},\"ba_added\":{s},\"ba_has\":{s},\"ba_not_full\":{s},\"empty\":{s},\"cardinality\":{d},\"contains0\":{s},\"min\":{s},\"max\":{s},\"exhausted_twice\":{s},\"full_same\":{s},\"empty_lacks\":{s}}}",
        .{
            jsonBool(ab_ok), jsonBool(ba_ok), jsonBool(ab_added), jsonBool(ab_has), jsonBool(ab_not_full),
            jsonBool(ba_added), jsonBool(ba_has), jsonBool(ba_not_full),
            jsonBool(empty_s.empty), empty_s.card, jsonBool(empty_s.c0), empty_min, empty_max, jsonBool(empty_s.exh),
            jsonBool(full_same), jsonBool(empty_lacks),
        },
    );
""",
        ins=_ins(values),
        sorted=_lit(values),
        absent=absent,
        fresh_ab=fresh_ab,
        fresh_ba=fresh_ba,
    )
    require_probe_true(
        report,
        "ab_ok",
        "ba_ok",
        "ab_added",
        "ab_has",
        "ab_not_full",
        "ba_added",
        "ba_has",
        "ba_not_full",
        "full_same",
        "empty_lacks",
    )
    _assert_snap(report)


def test_union_of_a_bitmap_with_itself_equals_that_set_and_result_is_new():
    values = draw_distinct_f06(unpublished_pair_size_f06())
    fresh = unpublished_u64_f06(set(values))
    absent = unpublished_u64_f06(set(values) | {fresh})
    report = run_f06_probe(
        r"""
    const ins = [_]u64{ __INS__ };
    const sorted = [_]u64{ __SORTED__ };
    const fresh: u64 = __FRESH__;
    const absent: u64 = __ABSENT__;
    var bm = try buildFrom(allocator, &ins);
    defer bm.deinit();
    var res = try klyvmap.Bitmap.Or(allocator, &bm, &bm);
    defer res.deinit();
    const seq = valuesMatch(&res, &sorted) and containsAll(&res, &sorted) and extremaMatch(&res, &sorted) and !res.contains(absent);
    const ops = valuesMatch(&bm, &sorted);
    const added = try res.set(fresh);
    const has = res.contains(fresh);
    const not_on = !bm.contains(fresh);
    const ops_after = valuesMatch(&bm, &sorted);
    try emitJson(init, init.gpa,
        "{{\"seq\":{s},\"ops\":{s},\"added\":{s},\"has\":{s},\"not_on\":{s},\"ops_after\":{s}}}",
        .{ jsonBool(seq), jsonBool(ops), jsonBool(added), jsonBool(has), jsonBool(not_on), jsonBool(ops_after) },
    );
""",
        ins=_ins(values),
        sorted=_lit(values),
        fresh=fresh,
        absent=absent,
    )
    require_probe_true(report, "seq", "ops", "added", "has", "not_on", "ops_after")


def test_union_of_two_equal_bitmaps_equals_that_set():
    values = draw_distinct_f06(unpublished_pair_size_f06())
    fresh = unpublished_u64_f06(set(values))
    report = run_f06_probe(
        _same_set_then_alien("Or"),
        ins=_ins(values),
        sorted=_lit(values),
        fresh=fresh,
    )
    require_probe_true(report, "seq", "ops", "added", "has", "not_a", "not_b", "ops_after")


# ---------------------------------------------------------------------------
# F. N-ary union
# ---------------------------------------------------------------------------


def _nary_match_body(block: str, *, fold: bool) -> str:
    fold_zig = """
    var folded = try foldUnion(allocator, &ptrs);
    defer folded.deinit();
    const fold_ok = valuesMatch(&folded, &expected);
"""
    fold_json = ',\\"fold_ok\\":{s}' if fold else ""
    fold_arg = ", jsonBool(fold_ok)" if fold else ""
    return (
        block
        + r"""
    const expected = [_]u64{ __EXPECTED__ };
    const absent: u64 = __ABSENT__;
    var res = try klyvmap.Bitmap.fastOr(allocator, &ptrs);
    defer res.deinit();
"""
        + (fold_zig if fold else "")
        + r"""
    const seq = valuesMatch(&res, &expected);
    const mem = containsAll(&res, &expected) and !res.contains(absent);
    const ext = extremaMatch(&res, &expected);
    try emitJson(init, init.gpa,
        "{{\"seq\":{s},\"mem\":{s},\"ext\":{s}"""
        + fold_json
        + r"""}}",
        .{ jsonBool(seq), jsonBool(mem), jsonBool(ext)"""
        + fold_arg
        + r""" },
    );
"""
    )


def _value_specs(groups: list[list[int]]) -> list[tuple]:
    specs = []
    for group in groups:
        if len(group) < 2:
            specs.append(("values", list(group)))
        else:
            specs.append(("values", shuffle_not_sorted(group)))
    return specs


def test_nary_union_of_empty_list_returns_empty_bitmap_that_accepts_a_set():
    fresh = unpublished_u64_f06()
    report = run_f06_probe(
        r"""
    const fresh: u64 = __FRESH__;
    var first = try klyvmap.Bitmap.fastOr(allocator, &.{});
    const s1 = emptyView(&first);
    const min1 = try optU64Json(init.gpa, first.minimum());
    defer init.gpa.free(min1);
    const max1 = try optU64Json(init.gpa, first.maximum());
    defer init.gpa.free(max1);
    const added = try first.set(fresh);
    const has = first.contains(fresh);
    const card1 = first.getCardinality() == 1;
    first.deinit();
    var second = try klyvmap.Bitmap.fastOr(allocator, &.{});
    defer second.deinit();
    const s2 = emptyView(&second);
    const min2 = try optU64Json(init.gpa, second.minimum());
    defer init.gpa.free(min2);
    const max2 = try optU64Json(init.gpa, second.maximum());
    defer init.gpa.free(max2);
    const no_fresh = !second.contains(fresh);
    try emitJson(init, init.gpa,
        "{{\"empty\":{s},\"cardinality\":{d},\"contains0\":{s},\"min\":{s},\"max\":{s},\"exhausted_twice\":{s},\"added\":{s},\"has\":{s},\"card1\":{s},\"second_empty\":{s},\"second_cardinality\":{d},\"second_contains0\":{s},\"second_min\":{s},\"second_max\":{s},\"second_exhausted_twice\":{s},\"no_fresh\":{s}}}",
        .{
            jsonBool(s1.empty), s1.card, jsonBool(s1.c0), min1, max1, jsonBool(s1.exh),
            jsonBool(added), jsonBool(has), jsonBool(card1),
            jsonBool(s2.empty), s2.card, jsonBool(s2.c0), min2, max2, jsonBool(s2.exh),
            jsonBool(no_fresh),
        },
    );
""",
        fresh=fresh,
    )
    _assert_snap(report)
    _assert_snap(report, "second_")
    require_probe_true(report, "added", "has", "card1", "no_fresh")


def test_nary_union_of_one_bitmap_matches_0_3_2_pow_16_2_pow_48_and_is_not_aliased():
    named = [0, 3, 1 << 16, 1 << 48]
    absent = unpublished_u64_f06(set(named) | {1 << 40})
    report = run_f06_probe(
        r"""
    const ins = [_]u64{ __INS__ };
    const sorted = [_]u64{ __SORTED__ };
    const rest = [_]u64{ __REST__ };
    const absent: u64 = __ABSENT__;
    var src = try buildFrom(allocator, &ins);
    defer src.deinit();
    const ptrs = [_]*const klyvmap.Bitmap{ &src };
    var res = try klyvmap.Bitmap.fastOr(allocator, &ptrs);
    defer res.deinit();
    const seq = valuesMatch(&res, &sorted) and zeroThenRest(&res, &rest) and extremaMatch(&res, &sorted);
    const mem = res.contains(0) and res.contains(3) and res.contains(1 << 16) and res.contains(1 << 48) and !res.contains(absent);
    const card4 = res.getCardinality() == 4;
    const added = try res.set(1 << 40);
    const has = res.contains(1 << 40);
    const not_on = !src.contains(1 << 40);
    const src_same = valuesMatch(&src, &sorted);
    try emitJson(init, init.gpa,
        "{{\"seq\":{s},\"mem\":{s},\"card4\":{s},\"added\":{s},\"has\":{s},\"not_on\":{s},\"src_same\":{s}}}",
        .{ jsonBool(seq), jsonBool(mem), jsonBool(card4), jsonBool(added), jsonBool(has), jsonBool(not_on), jsonBool(src_same) },
    );
""",
        ins=_ins(named),
        sorted=_lit(named),
        rest=_lit(sorted(named)[1:]),
        absent=absent,
    )
    require_probe_true(report, "seq", "mem", "card4", "added", "has", "not_on", "src_same")


def test_nary_union_of_sixty_random_bitmaps_matches_fold_of_union():
    groups: list[list[int]] = []
    used: set[int] = set()
    prefixes: list[int] = []
    for _ in range(57):
        prefix, vals = fresh_prefix_values_f06(2, set(prefixes), used)
        prefixes.append(prefix)
        used |= set(vals)
        groups.append(vals)
    unique_prefix, unique_vals = fresh_prefix_values_f06(2, set(prefixes), used)
    if unique_prefix in prefixes:
        raise HarnessError("unique prefix collided")
    used |= set(unique_vals)
    removed = draw_distinct_f06(3, used)
    used |= set(removed)
    specs: list[tuple] = _value_specs(groups)
    specs.insert(4, ("empty",))
    specs.insert(11, ("removed", shuffle_not_sorted(removed)))
    specs.append(("values", shuffle_not_sorted(unique_vals)))
    if len(specs) != 60:
        raise HarnessError(f"sixty-list has {len(specs)} inputs")
    expected = sorted(set().union(*groups) | set(unique_vals))
    if not any((v >> 16) == unique_prefix for v in expected):
        raise HarnessError("unique prefix missing from the expected union")
    absent = unpublished_u64_f06(set(expected) | set(removed))
    body = _nary_match_body(bitmap_block(specs), fold=True)
    report = run_f06_probe(body, expected=_lit(expected), absent=absent)
    require_probe_true(report, "seq", "mem", "ext", "fold_ok")


def test_nary_union_of_bitmaps_that_share_no_prefixes():
    count = unpublished_nary_count_f06()
    groups = []
    prefixes: list[int] = []
    used: set[int] = set()
    for _ in range(count):
        prefix, vals = fresh_prefix_values_f06(2, set(prefixes), used)
        prefixes.append(prefix)
        used |= set(vals)
        groups.append(vals)
    if len(set(prefixes)) != count:
        raise HarnessError("prefixes were shared")
    expected = sorted(set().union(*groups))
    absent = unpublished_u64_f06(set(expected))
    body = _nary_match_body(bitmap_block(_value_specs(groups)), fold=False)
    report = run_f06_probe(body, expected=_lit(expected), absent=absent)
    require_probe_true(report, "seq", "mem", "ext")


def test_nary_union_of_bitmaps_piled_into_one_prefix():
    count = unpublished_nary_count_f06()
    _prefix, pool = fresh_prefix_values_f06(count + 3, set(), set())
    shared = pool[0]
    groups = [[shared, pool[i + 1]] for i in range(count)]
    if len({v >> 16 for group in groups for v in group}) != 1:
        raise HarnessError("piled values left their prefix")
    expected = sorted({value for group in groups for value in group})
    if expected.count(shared) != 1:
        raise HarnessError("shared value was not unique in the expectation")
    absent = unpublished_u64_f06(set(expected))
    body = _nary_match_body(bitmap_block(_value_specs(groups)), fold=False)
    report = run_f06_probe(body, expected=_lit(expected), absent=absent)
    require_probe_true(report, "seq", "mem", "ext")


def test_nary_union_of_dense_consecutive_run_matches_set_union():
    _prefix, run = consecutive_run_f06()
    if len(run) < 1000:
        raise HarnessError("dense n-ary run is shorter than one thousand")
    mid = len(run) // 2
    first = run[:mid]
    later = run[mid:]
    overlap = run[mid - 5 : mid + 5]
    if not later or set(later) <= set(first):
        raise HarnessError("later bitmap has nothing the first lacks")
    marker = later[-1]
    if marker in first:
        raise HarnessError("marker is already on the first bitmap")
    groups = [first, overlap, later]
    expected = sorted(set(run))
    absent = unpublished_u64_f06(set(expected))
    body = _nary_match_body(bitmap_block(_value_specs(groups)), fold=True)
    report = run_f06_probe(body, expected=_lit(expected), absent=absent)
    require_probe_true(report, "seq", "mem", "ext", "fold_ok")


def test_nary_union_ignores_empty_and_fully_removed_inputs():
    present = draw_distinct_f06(unpublished_pair_size_f06())
    removed = draw_distinct_f06(3, set(present))
    fresh = unpublished_u64_f06(set(present) | set(removed))
    specs = [
        ("values", shuffle_not_sorted(present)),
        ("empty",),
        ("removed", shuffle_not_sorted(removed)),
        ("empty",),
    ]
    block = bitmap_block(specs)
    report = run_f06_probe(
        block
        + r"""
    const expected = [_]u64{ __EXPECTED__ };
    const fresh: u64 = __FRESH__;
    if (b2.getCardinality() != 0) return error.RemovedStillHolds;
    var res = try klyvmap.Bitmap.fastOr(allocator, &ptrs);
    defer res.deinit();
    const seq = valuesMatch(&res, &expected) and containsAll(&res, &expected) and extremaMatch(&res, &expected);
    const src_same = valuesMatch(&b0, &expected);
    const added = try res.set(fresh);
    const has = res.contains(fresh);
    const not_src = !b0.contains(fresh);
    const not_empty = !b1.contains(fresh) and !b3.contains(fresh);
    const not_removed = !b2.contains(fresh);
    const src_after = valuesMatch(&b0, &expected);
    const removed_still = b2.getCardinality() == 0;
    const empty_still = b1.getCardinality() == 0 and b3.getCardinality() == 0;
    try emitJson(init, init.gpa,
        "{{\"seq\":{s},\"src_same\":{s},\"added\":{s},\"has\":{s},\"not_src\":{s},\"not_empty\":{s},\"not_removed\":{s},\"src_after\":{s},\"removed_still\":{s},\"empty_still\":{s}}}",
        .{
            jsonBool(seq), jsonBool(src_same), jsonBool(added), jsonBool(has), jsonBool(not_src),
            jsonBool(not_empty), jsonBool(not_removed), jsonBool(src_after), jsonBool(removed_still), jsonBool(empty_still),
        },
    );
""",
        expected=_lit(present),
        fresh=fresh,
    )
    require_probe_true(
        report,
        "seq",
        "src_same",
        "added",
        "has",
        "not_src",
        "not_empty",
        "not_removed",
        "src_after",
        "removed_still",
        "empty_still",
    )


def test_nary_union_of_inputs_that_hold_nothing_is_empty_then_accepts_a_set():
    removed = draw_distinct_f06(3)
    fresh = unpublished_u64_f06(set(removed))
    specs = [
        ("empty",),
        ("removed", shuffle_not_sorted(removed)),
        ("empty",),
    ]
    block = bitmap_block(specs)
    report = run_f06_probe(
        block
        + r"""
    const fresh: u64 = __FRESH__;
    var first = try klyvmap.Bitmap.fastOr(allocator, &ptrs);
    const s1 = emptyView(&first);
    const min1 = try optU64Json(init.gpa, first.minimum());
    defer init.gpa.free(min1);
    const max1 = try optU64Json(init.gpa, first.maximum());
    defer init.gpa.free(max1);
    const added = try first.set(fresh);
    const has = first.contains(fresh);
    const card1 = first.getCardinality() == 1;
    first.deinit();
    var second = try klyvmap.Bitmap.fastOr(allocator, &ptrs);
    defer second.deinit();
    const s2 = emptyView(&second);
    const min2 = try optU64Json(init.gpa, second.minimum());
    defer init.gpa.free(min2);
    const max2 = try optU64Json(init.gpa, second.maximum());
    defer init.gpa.free(max2);
    const no_fresh = !second.contains(fresh);
    try emitJson(init, init.gpa,
        "{{\"empty\":{s},\"cardinality\":{d},\"contains0\":{s},\"min\":{s},\"max\":{s},\"exhausted_twice\":{s},\"added\":{s},\"has\":{s},\"card1\":{s},\"second_empty\":{s},\"second_cardinality\":{d},\"second_contains0\":{s},\"second_min\":{s},\"second_max\":{s},\"second_exhausted_twice\":{s},\"no_fresh\":{s}}}",
        .{
            jsonBool(s1.empty), s1.card, jsonBool(s1.c0), min1, max1, jsonBool(s1.exh),
            jsonBool(added), jsonBool(has), jsonBool(card1),
            jsonBool(s2.empty), s2.card, jsonBool(s2.c0), min2, max2, jsonBool(s2.exh),
            jsonBool(no_fresh),
        },
    );
""",
        fresh=fresh,
    )
    _assert_snap(report)
    _assert_snap(report, "second_")
    require_probe_true(report, "added", "has", "card1", "no_fresh")


def test_nary_union_containing_zero_yields_zero_then_later_values():
    later = unpublished_u64_f06(above=1 << 32)
    other = unpublished_u64_f06({later}, above=1 << 32)
    groups = [[0, later], [other]]
    expected = sorted({0, later, other})
    rest = expected[1:]
    absent = unpublished_u64_f06(set(expected))
    block = bitmap_block(_value_specs(groups))
    report = run_f06_probe(
        block
        + r"""
    const expected = [_]u64{ __EXPECTED__ };
    const rest = [_]u64{ __REST__ };
    const absent: u64 = __ABSENT__;
    var res = try klyvmap.Bitmap.fastOr(allocator, &ptrs);
    defer res.deinit();
    const seq = valuesMatch(&res, &expected) and zeroThenRest(&res, &rest);
    const mem = containsAll(&res, &expected) and res.contains(0) and !res.contains(absent);
    const ext = extremaMatch(&res, &expected);
    try emitJson(init, init.gpa,
        "{{\"seq\":{s},\"mem\":{s},\"ext\":{s}}}",
        .{ jsonBool(seq), jsonBool(mem), jsonBool(ext) },
    );
""",
        expected=_lit(expected),
        rest=_lit(rest),
        absent=absent,
    )
    require_probe_true(report, "seq", "mem", "ext")


def test_nary_union_list_order_does_not_change_the_set():
    count = unpublished_nary_count_f06()
    groups = []
    prefixes: list[int] = []
    used: set[int] = set()
    for _ in range(count):
        prefix, vals = fresh_prefix_values_f06(2, set(prefixes), used)
        prefixes.append(prefix)
        used |= set(vals)
        groups.append(vals)
    expected = sorted(set().union(*groups))
    absent = unpublished_u64_f06(set(expected))
    block = bitmap_block(_value_specs(groups))
    names = ", ".join(f"&b{i}" for i in range(count))
    rev = ", ".join(f"&b{i}" for i in range(count - 1, -1, -1))
    report = run_f06_probe(
        block
        + f"""
    const rev = [_]*const klyvmap.Bitmap{{ {rev} }};
"""
        + r"""
    const expected = [_]u64{ __EXPECTED__ };
    const absent: u64 = __ABSENT__;
    var res = try klyvmap.Bitmap.fastOr(allocator, &ptrs);
    defer res.deinit();
    var flipped = try klyvmap.Bitmap.fastOr(allocator, &rev);
    defer flipped.deinit();
    const seq = valuesMatch(&res, &expected) and containsAll(&res, &expected) and extremaMatch(&res, &expected) and !res.contains(absent);
    const seq_b = valuesMatch(&flipped, &expected) and containsAll(&flipped, &expected) and extremaMatch(&flipped, &expected) and !flipped.contains(absent);
    try emitJson(init, init.gpa, "{{\"seq\":{s},\"seq_b\":{s}}}", .{ jsonBool(seq), jsonBool(seq_b) });
""",
        expected=_lit(expected),
        absent=absent,
    )
    if names == rev and count > 1:
        raise HarnessError("reversed pointer list is identical")
    require_probe_true(report, "seq", "seq_b")


# ---------------------------------------------------------------------------
# G. Results stay usable: emit, open, compact, set, remove
# ---------------------------------------------------------------------------


def _shared_dense_operands():
    _prefix, dense = consecutive_run_f06()
    if len(dense) < 1000:
        raise HarnessError("emit run is shorter than one thousand")
    under32 = values_at_named_position_f06(1 << 32, 2)
    under48 = values_at_named_position_f06(1 << 48, 2)
    shared = list(dense) + under32 + under48
    avoid = {value >> 16 for value in shared}
    _pa, excl_a = fresh_prefix_values_f06(4, avoid, set(shared))
    _pb, excl_b = fresh_prefix_values_f06(4, avoid | {_pa}, set(shared) | set(excl_a))
    if (1 << 32) not in shared or (1 << 48) not in shared:
        raise HarnessError("named positions missing from the shared set")
    left = shared + excl_a
    right = shared + excl_b
    expected = sorted(set(shared))
    return left, right, expected, excl_a, excl_b


_EMIT_INTERSECTION = r"""
    const left_ins = [_]u64{ __LEFT_INS__ };
    const right_ins = [_]u64{ __RIGHT_INS__ };
    const left_sorted = [_]u64{ __LEFT_SORTED__ };
    const right_sorted = [_]u64{ __RIGHT_SORTED__ };
    const expected = [_]u64{ __EXPECTED__ };
    const excl_a = [_]u64{ __EXCL_A__ };
    const excl_b = [_]u64{ __EXCL_B__ };
    var left = try buildFrom(allocator, &left_ins);
    defer left.deinit();
    var right = try buildFrom(allocator, &right_ins);
    defer right.deinit();
    var res = try klyvmap.Bitmap.And(allocator, &left, &right);
    defer res.deinit();
    const seq = valuesMatch(&res, &expected) and containsAll(&res, &expected) and containsNone(&res, &excl_a) and containsNone(&res, &excl_b) and extremaMatch(&res, &expected);
    const ops = valuesMatch(&left, &left_sorted) and valuesMatch(&right, &right_sorted);
    const emitted = res.toBuffer();
    const shape = try shapeOf(emitted);
    const opened = try openedMatches(allocator, &res, &expected);
    try emitJson(init, init.gpa,
        "{{\"seq\":{s},\"ops\":{s},\"opened\":{s},\"len\":{d},\"b0\":{d},\"b1\":{d},\"res\":{d}}}",
        .{ jsonBool(seq), jsonBool(ops), jsonBool(opened), shape.len, shape.b0, shape.b1, shape.res },
    );
"""


def _emit_report():
    left, right, expected, excl_a, excl_b = _shared_dense_operands()
    return run_f06_probe(
        _EMIT_INTERSECTION,
        left_ins=_ins(left),
        right_ins=_ins(right),
        left_sorted=_lit(left),
        right_sorted=_lit(right),
        expected=_lit(expected),
        excl_a=_lit(excl_a),
        excl_b=_lit(excl_b),
    )


def test_intersection_emits_buffer_that_reopens_with_same_values_and_inuse_bytes():
    report = _emit_report()
    require_probe_true(report, "seq", "ops", "opened")
    require_emit_shape(report, length="len", b0="b0", b1="b1", residue="res")


def test_intersection_emit_is_even_length_and_aligned():
    report = _emit_report()
    require_emit_shape(report, length="len", b0="b0", b1="b1", residue="res")
    require_probe_true(report, "seq", "opened")


def test_union_and_nary_results_open_with_same_values_and_inuse_bytes():
    left, right, _both, absent = split_pair_f06(unpublished_pair_size_f06())
    union_expected = sorted(set(left) | set(right))
    groups = [draw_distinct_f06(3), draw_distinct_f06(3), draw_distinct_f06(3)]
    nary_expected = sorted(set().union(*groups))
    nary_absent = unpublished_u64_f06(set(nary_expected))
    block = bitmap_block(_value_specs(groups))
    report = run_f06_probe(
        r"""
    const left_ins = [_]u64{ __LEFT_INS__ };
    const right_ins = [_]u64{ __RIGHT_INS__ };
    const union_expected = [_]u64{ __UNION_EXPECTED__ };
    const absent: u64 = __ABSENT__;
    var left = try buildFrom(allocator, &left_ins);
    defer left.deinit();
    var right = try buildFrom(allocator, &right_ins);
    defer right.deinit();
    var uni = try klyvmap.Bitmap.Or(allocator, &left, &right);
    defer uni.deinit();
    const uni_open = try openedMatches(allocator, &uni, &union_expected);
    const uni_mem = containsAll(&uni, &union_expected) and !uni.contains(absent);
"""
        + block
        + r"""
    const nary_expected = [_]u64{ __NARY_EXPECTED__ };
    const nary_absent: u64 = __NARY_ABSENT__;
    var nary = try klyvmap.Bitmap.fastOr(allocator, &ptrs);
    defer nary.deinit();
    const nary_open = try openedMatches(allocator, &nary, &nary_expected);
    const nary_mem = containsAll(&nary, &nary_expected) and !nary.contains(nary_absent);
    try emitJson(init, init.gpa,
        "{{\"uni_open\":{s},\"uni_mem\":{s},\"nary_open\":{s},\"nary_mem\":{s}}}",
        .{ jsonBool(uni_open), jsonBool(uni_mem), jsonBool(nary_open), jsonBool(nary_mem) },
    );
""",
        left_ins=_ins(left),
        right_ins=_ins(right),
        union_expected=_lit(union_expected),
        absent=absent,
        nary_expected=_lit(nary_expected),
        nary_absent=nary_absent,
    )
    require_probe_true(report, "uni_open", "uni_mem", "nary_open", "nary_mem")


def test_intersection_union_and_nary_results_can_be_compacted():
    left, right, inter, _absent = split_pair_f06(unpublished_pair_size_f06())
    union_expected = sorted(set(left) | set(right))
    groups = [draw_distinct_f06(3), draw_distinct_f06(3, set(union_expected))]
    nary_expected = sorted(set().union(*groups))
    fresh = unpublished_u64_f06(set(union_expected) | set(nary_expected))
    block = bitmap_block(_value_specs(groups))
    report = run_f06_probe(
        r"""
    const left_ins = [_]u64{ __LEFT_INS__ };
    const right_ins = [_]u64{ __RIGHT_INS__ };
    const left_sorted = [_]u64{ __LEFT_SORTED__ };
    const right_sorted = [_]u64{ __RIGHT_SORTED__ };
    const inter = [_]u64{ __INTER__ };
    const union_expected = [_]u64{ __UNION_EXPECTED__ };
    const fresh: u64 = __FRESH__;
    var left = try buildFrom(allocator, &left_ins);
    defer left.deinit();
    var right = try buildFrom(allocator, &right_ins);
    defer right.deinit();
    var hit = try klyvmap.Bitmap.And(allocator, &left, &right);
    defer hit.deinit();
    var uni = try klyvmap.Bitmap.Or(allocator, &left, &right);
    defer uni.deinit();
"""
        + block
        + r"""
    const nary_expected = [_]u64{ __NARY_EXPECTED__ };
    var nary = try klyvmap.Bitmap.fastOr(allocator, &ptrs);
    defer nary.deinit();
    try hit.compact();
    try uni.compact();
    try nary.compact();
    const hit_ok = valuesMatch(&hit, &inter) and containsAll(&hit, &inter);
    const uni_ok = valuesMatch(&uni, &union_expected) and containsAll(&uni, &union_expected);
    const nary_ok = valuesMatch(&nary, &nary_expected) and containsAll(&nary, &nary_expected);
    const added = try hit.set(fresh);
    const has = hit.contains(fresh);
    const ops = valuesMatch(&left, &left_sorted) and valuesMatch(&right, &right_sorted) and !left.contains(fresh) and !right.contains(fresh);
    try emitJson(init, init.gpa,
        "{{\"hit_ok\":{s},\"uni_ok\":{s},\"nary_ok\":{s},\"added\":{s},\"has\":{s},\"ops\":{s}}}",
        .{ jsonBool(hit_ok), jsonBool(uni_ok), jsonBool(nary_ok), jsonBool(added), jsonBool(has), jsonBool(ops) },
    );
""",
        left_ins=_ins(left),
        right_ins=_ins(right),
        left_sorted=_lit(left),
        right_sorted=_lit(right),
        inter=_lit(inter),
        union_expected=_lit(union_expected),
        nary_expected=_lit(nary_expected),
        fresh=fresh,
    )
    require_probe_true(report, "hit_ok", "uni_ok", "nary_ok", "added", "has", "ops")


def _mutate_probe(kind: str, block: str) -> str:
    if kind == "and":
        produce = """
    var left = try buildFrom(allocator, &left_ins);
    defer left.deinit();
    var right = try buildFrom(allocator, &right_ins);
    defer right.deinit();
    var res = try klyvmap.Bitmap.And(allocator, &left, &right);
    defer res.deinit();
    const ops_before = valuesMatch(&left, &left_sorted) and valuesMatch(&right, &right_sorted);
"""
        ops_after = """
    const ops_after = valuesMatch(&left, &left_sorted) and valuesMatch(&right, &right_sorted);
    const fresh_not = !left.contains(fresh) and !right.contains(fresh);
    const victim_stays = left.contains(victim) and right.contains(victim);
"""
    elif kind == "or":
        produce = """
    var left = try buildFrom(allocator, &left_ins);
    defer left.deinit();
    var right = try buildFrom(allocator, &right_ins);
    defer right.deinit();
    var res = try klyvmap.Bitmap.Or(allocator, &left, &right);
    defer res.deinit();
    const ops_before = valuesMatch(&left, &left_sorted) and valuesMatch(&right, &right_sorted);
"""
        ops_after = """
    const ops_after = valuesMatch(&left, &left_sorted) and valuesMatch(&right, &right_sorted);
    const fresh_not = !left.contains(fresh) and !right.contains(fresh);
    const victim_stays = left.contains(victim) or right.contains(victim);
"""
    else:
        produce = block + """
    const s0 = [_]u64{ __S0__ };
    const s1 = [_]u64{ __S1__ };
    const s2 = [_]u64{ __S2__ };
    var res = try klyvmap.Bitmap.fastOr(allocator, &ptrs);
    defer res.deinit();
    const ops_before = valuesMatch(&b0, &s0) and valuesMatch(&b1, &s1) and valuesMatch(&b2, &s2);
"""
        ops_after = """
    const ops_after = valuesMatch(&b0, &s0) and valuesMatch(&b1, &s1) and valuesMatch(&b2, &s2);
    const fresh_not = !b0.contains(fresh) and !b1.contains(fresh) and !b2.contains(fresh);
    const victim_stays = b0.contains(victim) or b1.contains(victim) or b2.contains(victim);
"""
    return (
        produce
        + r"""
    const expected = [_]u64{ __EXPECTED__ };
    const rest = [_]u64{ __REST__ };
    const fresh: u64 = __FRESH__;
    const victim: u64 = __VICTIM__;
    const before: u64 = expected.len;
    const matched = valuesMatch(&res, &expected) and containsAll(&res, &expected);
    const added = try res.set(fresh);
    const has_fresh = res.contains(fresh);
    const card_up = res.getCardinality() == before + 1;
    const kept = containsAll(&res, &expected);
    const removed = res.remove(victim);
    const gone = !res.contains(victim);
    const card_down = res.getCardinality() == before;
    const rest_ok = containsAll(&res, &rest) and res.contains(fresh);
"""
        + ops_after
        + r"""
    try emitJson(init, init.gpa,
        "{{\"matched\":{s},\"added\":{s},\"has_fresh\":{s},\"card_up\":{s},\"kept\":{s},\"removed\":{s},\"gone\":{s},\"card_down\":{s},\"rest_ok\":{s},\"ops_before\":{s},\"ops_after\":{s},\"fresh_not\":{s},\"victim_stays\":{s}}}",
        .{
            jsonBool(matched), jsonBool(added), jsonBool(has_fresh), jsonBool(card_up), jsonBool(kept),
            jsonBool(removed), jsonBool(gone), jsonBool(card_down), jsonBool(rest_ok),
            jsonBool(ops_before), jsonBool(ops_after), jsonBool(fresh_not), jsonBool(victim_stays),
        },
    );
"""
    )


_MUTATE_KEYS = (
    "matched",
    "added",
    "has_fresh",
    "card_up",
    "kept",
    "removed",
    "gone",
    "card_down",
    "rest_ok",
    "ops_before",
    "ops_after",
    "fresh_not",
    "victim_stays",
)


def test_intersection_result_accepts_set_and_remove_without_mutating_operands():
    # The probe removes one shared value and keeps the rest, so the overlap
    # needs at least two values: split_pair_f06 shares size // 3 of them.
    left, right, expected, _absent = split_pair_f06(max(6, unpublished_pair_size_f06()))
    if set(expected) == set(left) or set(expected) == set(right):
        raise HarnessError("intersection equals an operand")
    victim = expected[0]
    rest = expected[1:]
    if not rest:
        raise HarnessError("intersection has no value left after the victim")
    fresh = unpublished_u64_f06(set(left) | set(right))
    report = run_f06_probe(
        r"""
    const left_ins = [_]u64{ __LEFT_INS__ };
    const right_ins = [_]u64{ __RIGHT_INS__ };
    const left_sorted = [_]u64{ __LEFT_SORTED__ };
    const right_sorted = [_]u64{ __RIGHT_SORTED__ };
"""
        + _mutate_probe("and", ""),
        left_ins=_ins(left),
        right_ins=_ins(right),
        left_sorted=_lit(left),
        right_sorted=_lit(right),
        expected=_lit(expected),
        rest=_lit(rest),
        fresh=fresh,
        victim=victim,
    )
    require_probe_true(report, *_MUTATE_KEYS)


def test_union_and_nary_results_accept_set_and_remove():
    left, right, _both, _absent = split_pair_f06(unpublished_pair_size_f06())
    union_expected = sorted(set(left) | set(right))
    victim_u = union_expected[0]
    rest_u = union_expected[1:]
    fresh_u = unpublished_u64_f06(set(union_expected))
    groups = [draw_distinct_f06(3), draw_distinct_f06(3), draw_distinct_f06(3)]
    nary_expected = sorted(set().union(*groups))
    victim_n = nary_expected[0]
    rest_n = nary_expected[1:]
    fresh_n = unpublished_u64_f06(set(nary_expected))
    block = bitmap_block(_value_specs(groups))
    union_body = (
        r"""
    const left_ins = [_]u64{ __LEFT_INS__ };
    const right_ins = [_]u64{ __RIGHT_INS__ };
    const left_sorted = [_]u64{ __LEFT_SORTED__ };
    const right_sorted = [_]u64{ __RIGHT_SORTED__ };
"""
        + _mutate_probe("or", "")
    )
    # The union probe and the n-ary probe are separate runs so the placeholders
    # do not collide. N-ary inputs are checked by the fresh-leak errors above.
    report_u = run_f06_probe(
        union_body,
        left_ins=_ins(left),
        right_ins=_ins(right),
        left_sorted=_lit(left),
        right_sorted=_lit(right),
        expected=_lit(union_expected),
        rest=_lit(rest_u),
        fresh=fresh_u,
        victim=victim_u,
    )
    require_probe_true(report_u, *_MUTATE_KEYS)
    report_n = run_f06_probe(
        _mutate_probe("nary", block),
        expected=_lit(nary_expected),
        rest=_lit(rest_n),
        fresh=fresh_n,
        victim=victim_n,
        s0=_lit(groups[0]),
        s1=_lit(groups[1]),
        s2=_lit(groups[2]),
    )
    require_probe_true(report_n, *_MUTATE_KEYS)


# ---------------------------------------------------------------------------
# H. No file or network I/O on the materializing path
# ---------------------------------------------------------------------------


def test_materializing_set_algebra_path_performs_no_file_or_network_io():
    left = draw_distinct_f06(6)
    right = draw_distinct_f06(6, set(left))
    third = draw_distinct_f06(4, set(left) | set(right))
    honest = wrap_f06_probe(
        fill_u64(
            r"""
    const left_ins = [_]u64{ __LEFT__ };
    const right_ins = [_]u64{ __RIGHT__ };
    const third_ins = [_]u64{ __THIRD__ };
    var a = try buildFrom(allocator, &left_ins);
    defer a.deinit();
    var b = try buildFrom(allocator, &right_ins);
    defer b.deinit();
    var c = try buildFrom(allocator, &third_ins);
    defer c.deinit();
    var hit = try klyvmap.Bitmap.And(allocator, &a, &b);
    defer hit.deinit();
    var uni = try klyvmap.Bitmap.Or(allocator, &a, &b);
    defer uni.deinit();
    const ptrs = [_]*const klyvmap.Bitmap{ &a, &b, &c };
    var nary = try klyvmap.Bitmap.fastOr(allocator, &ptrs);
    defer nary.deinit();
    const view = nary.toBuffer();
    if (view.len < 2) return error.ShortEmit;
    _ = view[0];
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
""",
            left=zig_u64_list(shuffle_not_sorted(left)),
            right=zig_u64_list(shuffle_not_sorted(right)),
            third=zig_u64_list(shuffle_not_sorted(third)),
        )
    )
    vandal = wrap_f06_probe(
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
    net_vandal = wrap_f06_probe(
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
        compile_probe_or_raise(ws, honest, relpath="honest.zig", output="honest")
        compile_probe_or_raise(ws, vandal_src, relpath="vandal.zig", output="vandal")
        compile_probe_or_raise(ws, net_vandal, relpath="net.zig", output="net")
        roots = (ws.path, ws.home, tmp)
        harness_names = {"honest.zig", "vandal.zig", "net.zig", "honest", "vandal", "net"}
        before: set[Path] = set()
        for root in roots:
            before |= _walk_regular_files(root)
        run = ws.run_command([str(ws.resolve("honest"))], timeout=DEFAULT_TIMEOUT)
        if run.returncode != 0:
            raise HarnessError(f"algebra I/O probe exited {run.returncode}\n{run.stderr_text}")
        created = product_created_files(before=before, roots=roots, ignore_names=harness_names)
        assert created == set(), f"materializing path wrote files: {created}"

        before_v: set[Path] = set()
        for root in roots:
            before_v |= _walk_regular_files(root)
        run_v = ws.run_command([str(ws.resolve("vandal"))], timeout=DEFAULT_TIMEOUT)
        if run_v.returncode != 0:
            raise HarnessError(f"file positive control exited {run_v.returncode}\n{run_v.stderr_text}")
        created_v = product_created_files(before=before_v, roots=roots, ignore_names=harness_names)
        names_v = {path.name for path in created_v}
        assert "cwd_side.txt" in names_v, f"workspace write not observed: {created_v}"
        assert "home_side.txt" in names_v, f"HOME write not observed: {created_v}"
        assert "tmp_side.txt" in names_v, f"TMPDIR write not observed: {created_v}"

        run_w, writes, reads = run_traced_file_writes(ws, [str(ws.resolve("honest"))], timeout=DEFAULT_TIMEOUT)
        if run_w.returncode != 0:
            raise HarnessError(f"traced algebra probe exited {run_w.returncode}\n{run_w.stderr_text}")
        assert file_write_syscalls_in_trace(writes) == []
        assert unexpected_file_reads_in_trace(reads) == []

        run_n, hits = run_traced_arch_network(ws, [str(ws.resolve("honest"))], timeout=DEFAULT_TIMEOUT)
        if run_n.returncode != 0:
            raise HarnessError(f"traced algebra network probe exited {run_n.returncode}\n{run_n.stderr_text}")
        assert network_syscalls_in_trace(hits) == []

        run_nv, vandal_hits = run_traced_network(ws, [str(ws.resolve("net"))], timeout=DEFAULT_TIMEOUT)
        if run_nv.returncode != 0:
            raise HarnessError(f"network positive control exited {run_nv.returncode}\n{run_nv.stderr_text}")
        assert network_syscalls_in_trace(vandal_hits), "network positive control observed nothing"


# ---------------------------------------------------------------------------
# Results that hold 2^k - 1, 2^k or 2^k + 1 values of one prefix
# ---------------------------------------------------------------------------


def test_intersection_union_and_nary_union_are_exact_when_one_prefix_holds_each_population():
    # For each population c: an intersection of two overlapping stretches of
    # one prefix that keeps exactly c of its values, a union of two
    # overlapping stretches that covers exactly c, and the n-ary union of
    # three adjacent stretches covering c. Each result is checked against the
    # arithmetic oracle; operands are checked unchanged.
    report = run_block_sweep(
        r"""
    const Build = struct {
        fn range(b: Block, alloc: std.mem.Allocator, lo: u64, hi: u64, edges: bool) !klyvmap.Bitmap {
            var bm = try klyvmap.Bitmap.init(alloc);
            errdefer bm.deinit();
            _ = try b.setRange(&bm, lo, hi);
            if (edges) _ = try b.setEdges(&bm);
            return bm;
        }
    };
    var and_ok = true;
    var or_ok = true;
    var nary_ok = true;
    var seen: u64 = 0;
    for (checkpoints) |c| {
        const x: u64 = @min(c, (65536 - c) / 2);
        {
            var l = try Build.range(block, allocator, 0, c + x, true);
            defer l.deinit();
            var r = try Build.range(block, allocator, x, c + 2 * x, true);
            defer r.deinit();
            var lr = try klyvmap.Bitmap.And(allocator, &l, &r);
            defer lr.deinit();
            var rl = try klyvmap.Bitmap.And(allocator, &r, &l);
            defer rl.deinit();
            and_ok = and_ok and lr.getCardinality() == c + 2 and block.walk(&lr, x, c + x, true);
            and_ok = and_ok and rl.getCardinality() == c + 2 and block.walk(&rl, x, c + x, true);
            and_ok = and_ok and block.walk(&l, 0, c + x, true) and block.walk(&r, x, c + 2 * x, true);
        }
        {
            const a = c - c / 3;
            const bb = c / 3;
            var l = try Build.range(block, allocator, 0, a, true);
            defer l.deinit();
            var r = try Build.range(block, allocator, bb, c, false);
            defer r.deinit();
            var lr = try klyvmap.Bitmap.Or(allocator, &l, &r);
            defer lr.deinit();
            var rl = try klyvmap.Bitmap.Or(allocator, &r, &l);
            defer rl.deinit();
            or_ok = or_ok and lr.getCardinality() == c + 2 and block.walk(&lr, 0, c, true);
            or_ok = or_ok and rl.getCardinality() == c + 2 and block.walk(&rl, 0, c, true);
            or_ok = or_ok and block.walk(&l, 0, a, true) and block.walk(&r, bb, c, false);
        }
        {
            const q1 = c / 3;
            const q2 = c - c / 3;
            var p1 = try Build.range(block, allocator, 0, q1, false);
            defer p1.deinit();
            var p2 = try Build.range(block, allocator, q1, q2, true);
            defer p2.deinit();
            var p3 = try Build.range(block, allocator, q2, c, false);
            defer p3.deinit();
            const parts = [_]*const klyvmap.Bitmap{ &p3, &p1, &p2 };
            var u = try klyvmap.Bitmap.fastOr(allocator, &parts);
            defer u.deinit();
            nary_ok = nary_ok and u.getCardinality() == c + 2 and block.walk(&u, 0, c, true);
            nary_ok = nary_ok and block.walk(&p1, 0, q1, false) and block.walk(&p2, q1, q2, true) and block.walk(&p3, q2, c, false);
        }
        seen += 1;
    }
    try emitJson(init, init.gpa,
        "{{\"and_ok\":{s},\"or_ok\":{s},\"nary_ok\":{s},\"seen\":{d}}}",
        .{ jsonBool(and_ok), jsonBool(or_ok), jsonBool(nary_ok), seen },
    );
"""
    )
    require_sweep_true(report, "and_ok", "or_ok", "nary_ok")

    require_sweep_seen(report, "seen", len(block_checkpoints()))
