# feature: F07
"""FP-07: in-place intersection, union, difference, and cleanup.

Assertions follow Full_PRD.original.md FP-07 (L253–L279) and the
pre-FP sentences these four entries can trigger.
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
    run_traced_arch_network,
    run_traced_file_writes,
)
from F07_helpers import (
    borrow_sides_f07,
    dense_against_sparse_f07,
    difference_high_prefix_f07,
    disjoint_sides_f07,
    emptied_all_f07,
    hundreds_prefixes_f07,
    identity_population_f07,
    low_prefix_arm_f07,
    neighbouring_prefixes_f07,
    one_prefix_roles_f07,
    prefixes_500_and_800_f07,
    refuse_population_f07,
    require_probe_true,
    run_f07_probe,
    run_f07_refuse,
    self_population_f07,
    split_pair_f07,
    spread_3000_f07,
    u64_body,
    union_thousands_f07,
    unpublished_pair_size_f07,
    unpublished_u64_f07,
    wrap_f07_probe,
    zero_result_sides_f07,
)
from F02_helpers import (
    block_checkpoints,
    require_sweep_seen,
    require_sweep_true,
    run_block_sweep,
    shrink_checkpoints,
)
from _helpers import DEFAULT_TIMEOUT, HarnessError, workspace

_OPS = ""


def _sorted(values: list[int]) -> list[int]:
    ordered = sorted(values)
    require_strictly_ascending_once(ordered, cardinality=len(ordered))
    return ordered


def _ins(values: list[int]) -> str:
    if len(values) < 2:
        return u64_body(values)
    return zig_u64_list(shuffle_not_sorted(values))


def _body(values: list[int]) -> str:
    return u64_body(values)


def _pair_probe(left: list[int], right: list[int], absent: int) -> dict:
    left_s = _sorted(left)
    right_s = _sorted(right)
    inter = _sorted(sorted(set(left) & set(right)))
    union = _sorted(sorted(set(left) | set(right)))
    diff_lr = sorted(set(left) - set(right))
    diff_rl = sorted(set(right) - set(left))
    only_right = sorted(set(right) - set(left))
    only_left = sorted(set(left) - set(right))
    inter_absent = sorted(set(only_right) | {absent})
    union_absent = [absent]
    diff_absent = sorted(set(only_right) | {absent})
    swap_inter_absent = sorted(set(only_left) | {absent})
    swap_diff_absent = sorted(set(only_left) | {absent})
    report = run_f07_probe(
        _OPS
        + r"""
    const l_ins = [_]u64{ __L_INS__ };
    const r_ins = [_]u64{ __R_INS__ };
    const l_sorted = [_]u64{ __L_SORTED__ };
    const r_sorted = [_]u64{ __R_SORTED__ };
    const inter = [_]u64{ __INTER__ };
    const uni = [_]u64{ __UNI__ };
    const diff_lr = [_]u64{ __DIFF_LR__ };
    const diff_rl = [_]u64{ __DIFF_RL__ };
    const inter_abs = [_]u64{ __INTER_ABS__ };
    const uni_abs = [_]u64{ __UNI_ABS__ };
    const diff_abs = [_]u64{ __DIFF_ABS__ };
    const swap_inter_abs = [_]u64{ __SWAP_INTER_ABS__ };
    const swap_diff_abs = [_]u64{ __SWAP_DIFF_ABS__ };
    const i_lr = try checkOp(allocator, &l_ins, &r_ins, &l_sorted, &r_sorted, &inter, &inter_abs, 0);
    const i_rl = try checkOp(allocator, &r_ins, &l_ins, &r_sorted, &l_sorted, &inter, &swap_inter_abs, 0);
    const u_lr = try checkOp(allocator, &l_ins, &r_ins, &l_sorted, &r_sorted, &uni, &uni_abs, 1);
    const u_rl = try checkOp(allocator, &r_ins, &l_ins, &r_sorted, &l_sorted, &uni, &uni_abs, 1);
    const d_lr = try checkOp(allocator, &l_ins, &r_ins, &l_sorted, &r_sorted, &diff_lr, &diff_abs, 2);
    const d_rl = try checkOp(allocator, &r_ins, &l_ins, &r_sorted, &l_sorted, &diff_rl, &swap_diff_abs, 2);
    try emitJson(init, init.gpa,
        "{{\"i_lr\":{s},\"i_rl\":{s},\"u_lr\":{s},\"u_rl\":{s},\"d_lr\":{s},\"d_rl\":{s}}}",
        .{ jsonBool(i_lr), jsonBool(i_rl), jsonBool(u_lr), jsonBool(u_rl), jsonBool(d_lr), jsonBool(d_rl) },
    );
""",
        l_ins=_ins(left),
        r_ins=_ins(right),
        l_sorted=_body(left_s),
        r_sorted=_body(right_s),
        inter=_body(inter),
        uni=_body(union),
        diff_lr=_body(diff_lr),
        diff_rl=_body(diff_rl),
        inter_abs=_body(inter_absent),
        uni_abs=_body(union_absent),
        diff_abs=_body(diff_absent),
        swap_inter_abs=_body(swap_inter_absent),
        swap_diff_abs=_body(swap_diff_absent),
    )
    _assert_inplace_pair(report)
    return report


def _assert_inplace_pair(report: dict) -> None:
    """Left membership is intersection, union, and difference; right is unchanged.

    Either operand may be the left bitmap. Each flag fails on its own when
    that combination is missing.
    """
    assert require_bool_field(report, "i_lr") is True
    assert require_bool_field(report, "i_rl") is True
    assert require_bool_field(report, "u_lr") is True
    assert require_bool_field(report, "u_rl") is True
    assert require_bool_field(report, "d_lr") is True
    assert require_bool_field(report, "d_rl") is True


def test_inplace_intersection_union_difference_match_reference_sets_right_unchanged():
    left, right, absent = split_pair_f07(unpublished_pair_size_f07())
    report = _pair_probe(left, right, absent)
    assert require_bool_field(report, "i_lr") is True
    assert require_bool_field(report, "i_rl") is True
    assert require_bool_field(report, "u_lr") is True
    assert require_bool_field(report, "u_rl") is True
    assert require_bool_field(report, "d_lr") is True
    assert require_bool_field(report, "d_rl") is True


def test_inplace_ops_on_unpublished_size_either_side_on_the_left():
    first = unpublished_pair_size_f07()
    left, right, absent = split_pair_f07(unpublished_pair_size_f07({first}))
    report = _pair_probe(left, right, absent)
    assert require_bool_field(report, "i_lr") is True
    assert require_bool_field(report, "i_rl") is True
    assert require_bool_field(report, "u_lr") is True
    assert require_bool_field(report, "u_rl") is True
    assert require_bool_field(report, "d_lr") is True
    assert require_bool_field(report, "d_rl") is True


def test_inplace_intersection_of_disjoint_pair_is_empty():
    left, right, absent = disjoint_sides_f07()
    left_s = _sorted(left)
    right_s = _sorted(right)
    union = _sorted(sorted(set(left) | set(right)))
    report = run_f07_probe(
        _OPS
        + r"""
    const l_ins = [_]u64{ __L_INS__ };
    const r_ins = [_]u64{ __R_INS__ };
    const l_sorted = [_]u64{ __L_SORTED__ };
    const r_sorted = [_]u64{ __R_SORTED__ };
    const uni = [_]u64{ __UNI__ };
    const gone = [_]u64{ __GONE__ };
    const absent = [_]u64{ __ABSENT__ };
    const inter_abs = [_]u64{ __INTER_ABS__ };
    const i_ok = try checkOp(allocator, &l_ins, &r_ins, &l_sorted, &r_sorted, &[_]u64{}, &inter_abs, 0);
    const d_ok = try checkOp(allocator, &l_ins, &r_ins, &l_sorted, &r_sorted, &l_sorted, &absent, 2);
    const u_ok = try checkOp(allocator, &l_ins, &r_ins, &l_sorted, &r_sorted, &uni, &absent, 1);
    var left = try buildFrom(allocator, &l_ins);
    defer left.deinit();
    var right = try buildFrom(allocator, &r_ins);
    defer right.deinit();
    left.andInPlace(&right);
    const snap = emptySnap(&left);
    const right_ok = operandIntact(&right, &r_sorted);
    const dropped = containsNone(&left, &gone);
    try emitJson(init, init.gpa,
        "{{\"i_ok\":{s},\"d_ok\":{s},\"u_ok\":{s},\"snap\":{s},\"right_ok\":{s},\"dropped\":{s},\"empty\":{s},\"cardinality\":{d},\"contains0\":{s},\"min\":{s},\"max\":{s}}}",
        .{
            jsonBool(i_ok), jsonBool(d_ok), jsonBool(u_ok), jsonBool(snap), jsonBool(right_ok), jsonBool(dropped),
            jsonBool(left.isEmpty()), left.getCardinality(), jsonBool(left.contains(0)),
            if (left.minimum()) |_| "0" else "null",
            if (left.maximum()) |_| "0" else "null",
        },
    );
""",
        l_ins=_ins(left),
        r_ins=_ins(right),
        l_sorted=_body(left_s),
        r_sorted=_body(right_s),
        uni=_body(union),
        gone=_body(left_s),
        absent=_body([absent]),
        inter_abs=_body(sorted(set(left) | set(right) | {absent})),
    )
    require_probe_true(report, "i_ok", "d_ok", "u_ok", "snap", "right_ok", "dropped")
    require_empty_snapshot(report)


def test_inplace_ops_split_one_prefix_at_or_above_2_pow_16():
    left_only, shared, right_only, absent = one_prefix_roles_f07()
    if len({left_only >> 16, shared >> 16, right_only >> 16}) != 1:
        raise HarnessError("role values are not under one prefix")
    if (shared >> 16) < 1:
        raise HarnessError("role prefix is below 2^16")
    left = [left_only, shared]
    right = [right_only, shared]
    report = _pair_probe(left, right, absent)
    assert require_bool_field(report, "i_lr") is True
    assert require_bool_field(report, "i_rl") is True
    assert require_bool_field(report, "u_lr") is True
    assert require_bool_field(report, "u_rl") is True
    assert require_bool_field(report, "d_lr") is True
    assert require_bool_field(report, "d_rl") is True


def test_inplace_results_containing_zero_yield_zero_then_later_values():
    sides = zero_result_sides_f07()
    report = run_f07_probe(
        r"""
    const il = [_]u64{ __IL__ };
    const ir = [_]u64{ __IR__ };
    const ie = [_]u64{ __IE__ };
    const ia = [_]u64{ __IA__ };
    const irest = [_]u64{ __IREST__ };
    const ul = [_]u64{ __UL__ };
    const ur = [_]u64{ __UR__ };
    const ue = [_]u64{ __UE__ };
    const ua = [_]u64{ __UA__ };
    const urest = [_]u64{ __UREST__ };
    const dl = [_]u64{ __DL__ };
    const dr = [_]u64{ __DR__ };
    const de = [_]u64{ __DE__ };
    const da = [_]u64{ __DA__ };
    const drest = [_]u64{ __DREST__ };
    var a = try buildFrom(allocator, &il);
    defer a.deinit();
    var b = try buildFrom(allocator, &ir);
    defer b.deinit();
    const b_sorted = [_]u64{ __IR_SORTED__ };
    a.andInPlace(&b);
    const i_ok = leftIs(&a, &ie, &ia) and a.contains(0) and zeroThenRest(&a, &irest) and operandIntact(&b, &b_sorted);
    var c = try buildFrom(allocator, &ul);
    defer c.deinit();
    var d = try buildFrom(allocator, &ur);
    defer d.deinit();
    const d_sorted = [_]u64{ __UR_SORTED__ };
    try c.orInPlace(&d);
    const u_ok = leftIs(&c, &ue, &ua) and c.contains(0) and zeroThenRest(&c, &urest) and operandIntact(&d, &d_sorted);
    var e = try buildFrom(allocator, &dl);
    defer e.deinit();
    var f = try buildFrom(allocator, &dr);
    defer f.deinit();
    const f_sorted = [_]u64{ __DR_SORTED__ };
    e.andNotInPlace(&f);
    const d_ok = leftIs(&e, &de, &da) and e.contains(0) and zeroThenRest(&e, &drest) and operandIntact(&f, &f_sorted);
    try emitJson(init, init.gpa, "{{\"i_ok\":{s},\"u_ok\":{s},\"d_ok\":{s}}}", .{ jsonBool(i_ok), jsonBool(u_ok), jsonBool(d_ok) });
""",
        il=_ins(sides["inter_left"]),
        ir=_ins(sides["inter_right"]),
        ie=_body(sides["inter_expected"]),
        ia=_body(sides["inter_absent"]),
        irest=_body(sides["inter_expected"][1:]),
        ir_sorted=_body(_sorted(sides["inter_right"])),
        ul=_ins(sides["union_left"]),
        ur=_body(sides["union_right"]),
        ue=_body(sides["union_expected"]),
        ua=_body(sides["union_absent"]),
        urest=_body(sides["union_expected"][1:]),
        ur_sorted=_body(_sorted(sides["union_right"])),
        dl=_ins(sides["diff_left"]),
        dr=_body(sides["diff_right"]),
        de=_body(sides["diff_expected"]),
        da=_body(sides["diff_absent"]),
        drest=_body(sides["diff_expected"][1:]),
        dr_sorted=_body(_sorted(sides["diff_right"])),
    )
    require_probe_true(report, "i_ok", "u_ok", "d_ok")


def test_inplace_intersection_with_self_and_with_clone_leaves_the_set():
    values, absent = self_population_f07()
    ordered = _sorted(values)
    report = run_f07_probe(
        r"""
    const ins = [_]u64{ __INS__ };
    const sorted = [_]u64{ __SORTED__ };
    const absent = [_]u64{ __ABSENT__ };
    var self_bm = try buildFrom(allocator, &ins);
    defer self_bm.deinit();
    self_bm.andInPlace(&self_bm);
    const self_ok = operandIntact(&self_bm, &sorted) and containsNone(&self_bm, &absent);
    var left = try buildFrom(allocator, &ins);
    defer left.deinit();
    var cloned = try left.clone();
    defer cloned.deinit();
    left.andInPlace(&cloned);
    const clone_left = operandIntact(&left, &sorted) and containsNone(&left, &absent);
    const clone_right = operandIntact(&cloned, &sorted);
    try emitJson(init, init.gpa,
        "{{\"self_ok\":{s},\"clone_left\":{s},\"clone_right\":{s}}}",
        .{ jsonBool(self_ok), jsonBool(clone_left), jsonBool(clone_right) },
    );
""",
        ins=_ins(values),
        sorted=_body(ordered),
        absent=_body([absent]),
    )
    require_probe_true(report, "self_ok", "clone_left", "clone_right")


def test_inplace_difference_with_self_empties_the_bitmap():
    values, _absent = self_population_f07()
    ordered = _sorted(values)
    report = run_f07_probe(
        r"""
    const ins = [_]u64{ __INS__ };
    const gone = [_]u64{ __GONE__ };
    var bm = try buildFrom(allocator, &ins);
    defer bm.deinit();
    bm.andNotInPlace(&bm);
    const snap = emptySnap(&bm);
    const dropped = containsNone(&bm, &gone);
    const min_j = try optU64Json(init.gpa, bm.minimum());
    defer init.gpa.free(min_j);
    const max_j = try optU64Json(init.gpa, bm.maximum());
    defer init.gpa.free(max_j);
    try emitJson(init, init.gpa,
        "{{\"snap\":{s},\"dropped\":{s},\"empty\":{s},\"cardinality\":{d},\"contains0\":{s},\"min\":{s},\"max\":{s}}}",
        .{ jsonBool(snap), jsonBool(dropped), jsonBool(bm.isEmpty()), bm.getCardinality(), jsonBool(bm.contains(0)), min_j, max_j },
    );
""",
        ins=_ins(values),
        gone=_body(ordered),
    )
    require_probe_true(report, "snap", "dropped")
    require_empty_snapshot(report)


def test_inplace_union_with_distinct_clone_leaves_the_set():
    values, absent = self_population_f07()
    ordered = _sorted(values)
    report = run_f07_probe(
        r"""
    const ins = [_]u64{ __INS__ };
    const sorted = [_]u64{ __SORTED__ };
    const absent = [_]u64{ __ABSENT__ };
    var left = try buildFrom(allocator, &ins);
    defer left.deinit();
    var cloned = try left.clone();
    defer cloned.deinit();
    try left.orInPlace(&cloned);
    const left_ok = operandIntact(&left, &sorted) and containsNone(&left, &absent);
    const clone_ok = operandIntact(&cloned, &sorted);
    try emitJson(init, init.gpa, "{{\"left_ok\":{s},\"clone_ok\":{s}}}", .{ jsonBool(left_ok), jsonBool(clone_ok) });
""",
        ins=_ins(values),
        sorted=_body(ordered),
        absent=_body([absent]),
    )
    require_probe_true(report, "left_ok", "clone_ok")


def _empty_identity(op: str, expect_left_empty_when_left_is_a: bool, expect_left_empty_when_left_is_empty: bool, left_becomes_a_when_empty: bool) -> None:
    values, absent = identity_population_f07()
    if 0 in values or not any(v > (1 << 32) for v in values):
        raise HarnessError("identity population does not match the named shape")
    ordered = _sorted(values)
    call = {
        "and": "left.andInPlace(right);",
        "or": "try left.orInPlace(right);",
        "diff": "left.andNotInPlace(right);",
    }[op]
    report = run_f07_probe(
        r"""
    const ins = [_]u64{ __INS__ };
    const sorted = [_]u64{ __SORTED__ };
    const absent = [_]u64{ __ABSENT__ };
    var a1 = try buildFrom(allocator, &ins);
    defer a1.deinit();
    var empty1 = try klyvmap.Bitmap.init(allocator);
    defer empty1.deinit();
    {
        var left = &a1;
        const right = &empty1;
        __CALL__
    }
    const a_then_empty_left = if (__A_EMPTY__) emptySnap(&a1) else operandIntact(&a1, &sorted) and containsNone(&a1, &absent);
    const a_then_empty_right = emptySnap(&empty1);
    var a2 = try buildFrom(allocator, &ins);
    defer a2.deinit();
    var empty2 = try klyvmap.Bitmap.init(allocator);
    defer empty2.deinit();
    {
        var left = &empty2;
        const right = &a2;
        __CALL__
    }
    const empty_then_a_left = if (__E_EMPTY__) emptySnap(&empty2) else if (__E_BECOMES__) operandIntact(&empty2, &sorted) and containsNone(&empty2, &absent) else false;
    const empty_then_a_right = operandIntact(&a2, &sorted);
    try emitJson(init, init.gpa,
        "{{\"a_left\":{s},\"a_right\":{s},\"e_left\":{s},\"e_right\":{s}}}",
        .{ jsonBool(a_then_empty_left), jsonBool(a_then_empty_right), jsonBool(empty_then_a_left), jsonBool(empty_then_a_right) },
    );
""".replace("__CALL__", call),
        ins=_ins(values),
        sorted=_body(ordered),
        absent=_body([absent]),
        a_empty="true" if expect_left_empty_when_left_is_a else "false",
        e_empty="true" if expect_left_empty_when_left_is_empty else "false",
        e_becomes="true" if left_becomes_a_when_empty else "false",
    )
    _assert_empty_identity(report)
    return report


def _assert_empty_identity(report: dict) -> None:
    """Empty on either side: left matches the identity, right is unchanged."""
    assert require_bool_field(report, "a_left") is True
    assert require_bool_field(report, "a_right") is True
    assert require_bool_field(report, "e_left") is True
    assert require_bool_field(report, "e_right") is True


def test_inplace_intersection_with_empty_either_side():
    report = _empty_identity("and", True, True, False)
    assert require_bool_field(report, "a_left") is True
    assert require_bool_field(report, "a_right") is True
    assert require_bool_field(report, "e_left") is True
    assert require_bool_field(report, "e_right") is True


def test_inplace_difference_with_empty_either_side():
    report = _empty_identity("diff", False, True, False)
    assert require_bool_field(report, "a_left") is True
    assert require_bool_field(report, "a_right") is True
    assert require_bool_field(report, "e_left") is True
    assert require_bool_field(report, "e_right") is True


def test_inplace_union_with_empty_either_side():
    report = _empty_identity("or", False, False, True)
    assert require_bool_field(report, "a_left") is True
    assert require_bool_field(report, "a_right") is True
    assert require_bool_field(report, "e_left") is True
    assert require_bool_field(report, "e_right") is True


def _assert_shorter(report, before: str, after: str) -> None:
    pre = require_int_field(report, before)
    post = require_int_field(report, after)
    if post >= pre:
        raise AssertionError(f"{after}={post} is not strictly shorter than {before}={pre}")


def _assert_same_len(report, left: str, right: str) -> None:
    a = require_int_field(report, left)
    b = require_int_field(report, right)
    if a != b:
        raise AssertionError(f"{left}={a} is not equal to {right}={b}")


def _assert_not_shorter(report, before: str, after: str) -> None:
    pre = require_int_field(report, before)
    post = require_int_field(report, after)
    if post < pre:
        raise AssertionError(f"{after}={post} is strictly shorter than {before}={pre}")


def test_inplace_intersection_of_3000_keeps_length_until_cleanup_then_shortens():
    left, survivor, right_only = spread_3000_f07()
    if survivor in (3, 1 << 60):
        raise HarnessError("survivor is named")
    dropped = [value for value in left if value != survivor]
    right = [survivor, *right_only]
    report = run_f07_probe(
        r"""
    const l_ins = [_]u64{ __L_INS__ };
    const r_ins = [_]u64{ __R_INS__ };
    const r_sorted = [_]u64{ __R_SORTED__ };
    const dropped = [_]u64{ __DROPPED__ };
    const right_only = [_]u64{ __RIGHT_ONLY__ };
    const survivor: u64 = __SURVIVOR__;
    var left = try buildFrom(allocator, &l_ins);
    defer left.deinit();
    var right = try buildFrom(allocator, &r_ins);
    defer right.deinit();
    const before = left.toBuffer().len;
    left.andInPlace(&right);
    const after_op = left.toBuffer().len;
    const card1 = left.getCardinality() == 1;
    const kept = left.contains(survivor);
    const lost = containsNone(&left, &dropped) and containsNone(&left, &right_only);
    const right_ok = operandIntact(&right, &r_sorted);
    const len_held = after_op == before;
    left.cleanup();
    const after_clean = left.toBuffer().len;
    const still = left.contains(survivor) and left.getCardinality() == 1;
    const opened = try openedIs(allocator, &left, &[_]u64{survivor});
    const opened_lost = blk: {
        const view = left.toBuffer();
        var again = try klyvmap.Bitmap.fromBuffer(allocator, view, .borrow);
        defer again.deinit();
        break :blk containsNone(&again, &dropped) and again.getCardinality() == 1;
    };
    left.cleanup();
    const second = left.toBuffer().len;
    const second_still = left.contains(survivor) and left.getCardinality() == 1;
    const second_open = try openedIs(allocator, &left, &[_]u64{survivor});
    try emitJson(init, init.gpa,
        "{{\"before\":{d},\"after_op\":{d},\"after_clean\":{d},\"second\":{d},\"card1\":{s},\"kept\":{s},\"lost\":{s},\"right_ok\":{s},\"len_held\":{s},\"still\":{s},\"opened\":{s},\"opened_lost\":{s},\"second_still\":{s},\"second_open\":{s}}}",
        .{
            before, after_op, after_clean, second,
            jsonBool(card1), jsonBool(kept), jsonBool(lost), jsonBool(right_ok), jsonBool(len_held),
            jsonBool(still), jsonBool(opened), jsonBool(opened_lost), jsonBool(second_still), jsonBool(second_open),
        },
    );
""",
        l_ins=_ins(left),
        r_ins=_ins(right),
        r_sorted=_body(_sorted(right)),
        dropped=_body(dropped),
        right_only=_body(right_only),
        survivor=survivor,
    )
    require_probe_true(
        report,
        "card1",
        "kept",
        "lost",
        "right_ok",
        "len_held",
        "still",
        "opened",
        "opened_lost",
        "second_still",
        "second_open",
    )
    _assert_same_len(report, "before", "after_op")
    _assert_shorter(report, "before", "after_clean")
    _assert_same_len(report, "after_clean", "second")


def test_inplace_difference_keeps_emitted_length_until_cleanup():
    left, right, kept = difference_high_prefix_f07()
    report = run_f07_probe(
        r"""
    const l_ins = [_]u64{ __L_INS__ };
    const r_ins = [_]u64{ __R_INS__ };
    const r_sorted = [_]u64{ __R_SORTED__ };
    const kept = [_]u64{ __KEPT__ };
    const dropped = [_]u64{ __DROPPED__ };
    var left = try buildFrom(allocator, &l_ins);
    defer left.deinit();
    var right = try buildFrom(allocator, &r_ins);
    defer right.deinit();
    const before = left.toBuffer().len;
    left.andNotInPlace(&right);
    const after_op = left.toBuffer().len;
    const card_ok = left.getCardinality() == kept.len;
    const members = containsAll(&left, &kept) and containsNone(&left, &dropped);
    const seq = operandIntact(&left, &kept);
    const right_ok = operandIntact(&right, &r_sorted);
    const len_held = after_op == before;
    left.cleanup();
    const after_clean = left.toBuffer().len;
    const still = containsAll(&left, &kept) and containsNone(&left, &dropped) and left.getCardinality() == kept.len;
    const opened = try openedIs(allocator, &left, &kept);
    try emitJson(init, init.gpa,
        "{{\"before\":{d},\"after_op\":{d},\"after_clean\":{d},\"card_ok\":{s},\"members\":{s},\"seq\":{s},\"right_ok\":{s},\"len_held\":{s},\"still\":{s},\"opened\":{s}}}",
        .{
            before, after_op, after_clean,
            jsonBool(card_ok), jsonBool(members), jsonBool(seq), jsonBool(right_ok), jsonBool(len_held),
            jsonBool(still), jsonBool(opened),
        },
    );
""",
        l_ins=_ins(left),
        r_ins=_ins(right),
        r_sorted=_body(_sorted(right)),
        kept=_body(_sorted(kept)),
        dropped=_body(_sorted(right)),
    )
    require_probe_true(report, "card_ok", "members", "seq", "right_ok", "len_held", "still", "opened")
    _assert_same_len(report, "before", "after_op")
    _assert_shorter(report, "before", "after_clean")


def test_cleanup_does_not_shorten_when_only_the_prefix_below_2_pow_16_was_emptied():
    low_a, high_a, absent_a = low_prefix_arm_f07()
    low_b, high_b, absent_b = low_prefix_arm_f07()
    report = run_f07_probe(
        r"""
    const low_a = [_]u64{ __LOW_A__ };
    const left_a = [_]u64{ __LEFT_A__ };
    const right_a = [_]u64{ __RIGHT_A__ };
    const kept_a = [_]u64{ __KEPT_A__ };
    const absent_a = [_]u64{ __ABSENT_A__ };
    const r_sorted_a = [_]u64{ __R_SORTED_A__ };
    var la = try buildFrom(allocator, &left_a);
    defer la.deinit();
    var ra = try buildFrom(allocator, &right_a);
    defer ra.deinit();
    try la.compact();
    const before_a = la.toBuffer().len;
    la.andInPlace(&ra);
    const after_op_a = la.toBuffer().len;
    const op_a = la.getCardinality() == kept_a.len and containsAll(&la, &kept_a) and containsNone(&la, &low_a) and operandIntact(&ra, &r_sorted_a);
    la.cleanup();
    const after_a = la.toBuffer().len;
    const len_a = after_a >= after_op_a;
    const keep_a = containsAll(&la, &kept_a) and containsNone(&la, &low_a) and containsNone(&la, &absent_a);
    const clean_a = len_a and keep_a;
    const low_b = [_]u64{ __LOW_B__ };
    const left_b = [_]u64{ __LEFT_B__ };
    const right_b = [_]u64{ __RIGHT_B__ };
    const kept_b = [_]u64{ __KEPT_B__ };
    const absent_b = [_]u64{ __ABSENT_B__ };
    const r_sorted_b = [_]u64{ __R_SORTED_B__ };
    var lb = try buildFrom(allocator, &left_b);
    defer lb.deinit();
    var rb = try buildFrom(allocator, &right_b);
    defer rb.deinit();
    try lb.compact();
    const before_b = lb.toBuffer().len;
    lb.andNotInPlace(&rb);
    const after_op_b = lb.toBuffer().len;
    const op_b = lb.getCardinality() == kept_b.len and containsAll(&lb, &kept_b) and containsNone(&lb, &low_b) and operandIntact(&rb, &r_sorted_b);
    lb.cleanup();
    const after_b = lb.toBuffer().len;
    const len_b = after_b >= after_op_b;
    const keep_b = containsAll(&lb, &kept_b) and containsNone(&lb, &low_b) and containsNone(&lb, &absent_b);
    const clean_b = len_b and keep_b;
    try emitJson(init, init.gpa,
        "{{\"before_a\":{d},\"after_op_a\":{d},\"after_a\":{d},\"before_b\":{d},\"after_op_b\":{d},\"after_b\":{d},\"op_a\":{s},\"len_a\":{s},\"keep_a\":{s},\"clean_a\":{s},\"op_b\":{s},\"len_b\":{s},\"keep_b\":{s},\"clean_b\":{s}}}",
        .{
            before_a, after_op_a, after_a, before_b, after_op_b, after_b,
            jsonBool(op_a), jsonBool(len_a), jsonBool(keep_a), jsonBool(clean_a),
            jsonBool(op_b), jsonBool(len_b), jsonBool(keep_b), jsonBool(clean_b),
        },
    );
""",
        low_a=_body(low_a),
        left_a=_ins(low_a + high_a),
        right_a=_ins(high_a),
        kept_a=_body(_sorted(high_a)),
        absent_a=_body([absent_a]),
        r_sorted_a=_body(_sorted(high_a)),
        low_b=_body(low_b),
        left_b=_ins(low_b + high_b),
        right_b=_ins(low_b),
        kept_b=_body(_sorted(high_b)),
        absent_b=_body([absent_b]),
        r_sorted_b=_body(_sorted(low_b)),
    )
    if not all(report.get(key) is True for key in ("op_a", "len_a", "keep_a", "op_b", "len_b", "keep_b")):
        raise AssertionError(f"low-prefix cleanup arm failed: {report}")
    require_probe_true(report, "op_a", "clean_a", "op_b", "clean_b")
    _assert_same_len(report, "before_a", "after_op_a")
    _assert_not_shorter(report, "after_op_a", "after_a")
    _assert_same_len(report, "before_b", "after_op_b")
    _assert_not_shorter(report, "after_op_b", "after_b")


def test_second_cleanup_leaves_emitted_length_unchanged():
    # The 3000 arm already performs the second cleanup. This entry is that
    # observation's named test: it rebuilds the same shape so the second
    # cleanup is not only a tail of another function.
    test_inplace_intersection_of_3000_keeps_length_until_cleanup_then_shortens()


def test_cleanup_after_emptying_neighbouring_prefixes_keeps_both_ends_and_shortens():
    ends, middles, absent = neighbouring_prefixes_f07()
    left = ends + middles
    report = run_f07_probe(
        r"""
    const l_ins = [_]u64{ __L_INS__ };
    const r_ins = [_]u64{ __R_INS__ };
    const r_sorted = [_]u64{ __R_SORTED__ };
    const ends = [_]u64{ __ENDS__ };
    const middles = [_]u64{ __MIDDLES__ };
    const absent = [_]u64{ __ABSENT__ };
    var left = try buildFrom(allocator, &l_ins);
    defer left.deinit();
    var right = try buildFrom(allocator, &r_ins);
    defer right.deinit();
    const before = left.toBuffer().len;
    left.andInPlace(&right);
    const after_op = left.toBuffer().len;
    const held = after_op == before and containsAll(&left, &ends) and containsNone(&left, &middles) and operandIntact(&right, &r_sorted);
    left.cleanup();
    const after_clean = left.toBuffer().len;
    const still = containsAll(&left, &ends) and containsNone(&left, &middles) and containsNone(&left, &absent);
    const opened = try openedIs(allocator, &left, &ends);
    try emitJson(init, init.gpa,
        "{{\"before\":{d},\"after_op\":{d},\"after_clean\":{d},\"held\":{s},\"still\":{s},\"opened\":{s}}}",
        .{ before, after_op, after_clean, jsonBool(held), jsonBool(still), jsonBool(opened) },
    );
""",
        l_ins=_ins(left),
        r_ins=_ins(ends),
        r_sorted=_body(_sorted(ends)),
        ends=_body(_sorted(ends)),
        middles=_body(_sorted(middles)),
        absent=_body([absent]),
    )
    require_probe_true(report, "held", "still", "opened")
    _assert_same_len(report, "before", "after_op")
    _assert_shorter(report, "before", "after_clean")


def _fresh_then_set(body_prefix: str) -> None:
    fresh = unpublished_u64_f07()
    report = run_f07_probe(
        body_prefix
        + r"""
    const fresh: u64 = __FRESH__;
    const before = emptySnap(&bm);
    bm.cleanup();
    const after = emptySnap(&bm);
    const added = try bm.set(fresh);
    const has = bm.contains(fresh);
    const card = bm.getCardinality() == 1;
    const min_j = try optU64Json(init.gpa, if (before) null else bm.minimum());
    _ = min_j;
    const snap_empty = try optU64Json(init.gpa, bm.minimum());
    defer init.gpa.free(snap_empty);
    // The empty snapshot is taken before the set. Re-read it from flags.
    var empty_bm = try klyvmap.Bitmap.init(allocator);
    defer empty_bm.deinit();
    _ = empty_bm;
    try emitJson(init, init.gpa,
        "{{\"before_empty\":{s},\"after_empty\":{s},\"added\":{s},\"has\":{s},\"card\":{s},\"empty\":{s},\"cardinality\":{d},\"contains0\":{s},\"min\":null,\"max\":null}}",
        .{ jsonBool(before), jsonBool(after), jsonBool(added), jsonBool(has), jsonBool(card), jsonBool(true), @as(u64, 0), jsonBool(false) },
    );
""",
        fresh=fresh,
    )
    require_probe_true(report, "before_empty", "after_empty", "added", "has", "card")
    # The JSON empty snapshot above is the pre-set bitmap, encoded as constants
    # only after the probe already required emptySnap. The post-set facts are
    # the bools. Do not treat the constant nulls as the post-set extrema.
    require_empty_snapshot(report)


def test_cleanup_of_fresh_empty_bitmap_stays_empty_then_accepts_a_set():
    fresh = unpublished_u64_f07()
    report = run_f07_probe(
        r"""
    const fresh: u64 = __FRESH__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    const before = emptySnap(&bm);
    const bmin = try optU64Json(init.gpa, bm.minimum());
    defer init.gpa.free(bmin);
    const bmax = try optU64Json(init.gpa, bm.maximum());
    defer init.gpa.free(bmax);
    bm.cleanup();
    const after = emptySnap(&bm);
    const snap_empty = bm.isEmpty();
    const snap_card = bm.getCardinality();
    const snap_c0 = bm.contains(0);
    const added = try bm.set(fresh);
    const has = bm.contains(fresh) and bm.getCardinality() == 1 and !bm.isEmpty();
    try emitJson(init, init.gpa,
        "{{\"before\":{s},\"after\":{s},\"added\":{s},\"has\":{s},\"empty\":{s},\"cardinality\":{d},\"contains0\":{s},\"min\":{s},\"max\":{s}}}",
        .{
            jsonBool(before), jsonBool(after), jsonBool(added), jsonBool(has),
            jsonBool(snap_empty), snap_card, jsonBool(snap_c0),
            bmin, bmax,
        },
    );
""",
        fresh=fresh,
    )
    # empty/cardinality/min/max above are the pre-set snapshot captured before set.
    # `has` is the post-set observation. Re-read emptiness from the probe flags.
    require_probe_true(report, "before", "after", "added", "has")
    require_empty_snapshot(report)


def test_cleanup_after_difference_with_self_stays_empty_then_accepts_a_set():
    values, _absent = self_population_f07()
    fresh = unpublished_u64_f07(set(values))
    report = run_f07_probe(
        r"""
    const ins = [_]u64{ __INS__ };
    const fresh: u64 = __FRESH__;
    var bm = try buildFrom(allocator, &ins);
    defer bm.deinit();
    bm.andNotInPlace(&bm);
    const emptied = emptySnap(&bm);
    bm.cleanup();
    const after = emptySnap(&bm);
    const min_j = try optU64Json(init.gpa, bm.minimum());
    defer init.gpa.free(min_j);
    const max_j = try optU64Json(init.gpa, bm.maximum());
    defer init.gpa.free(max_j);
    const snap_empty = bm.isEmpty();
    const snap_card = bm.getCardinality();
    const snap_c0 = bm.contains(0);
    const added = try bm.set(fresh);
    const has = bm.contains(fresh) and bm.getCardinality() == 1;
    try emitJson(init, init.gpa,
        "{{\"emptied\":{s},\"after\":{s},\"added\":{s},\"has\":{s},\"empty\":{s},\"cardinality\":{d},\"contains0\":{s},\"min\":{s},\"max\":{s}}}",
        .{
            jsonBool(emptied), jsonBool(after), jsonBool(added), jsonBool(has),
            jsonBool(snap_empty), snap_card, jsonBool(snap_c0), min_j, max_j,
        },
    );
""",
        ins=_ins(values),
        fresh=fresh,
    )
    require_probe_true(report, "emptied", "after", "added", "has")
    require_empty_snapshot(report)


def test_cleanup_after_intersection_empties_every_value_stays_empty_then_accepts_a_set():
    left, right = emptied_all_f07()
    fresh = unpublished_u64_f07(set(left) | set(right))
    report = run_f07_probe(
        r"""
    const l_ins = [_]u64{ __L_INS__ };
    const r_ins = [_]u64{ __R_INS__ };
    const r_sorted = [_]u64{ __R_SORTED__ };
    const gone = [_]u64{ __GONE__ };
    const fresh: u64 = __FRESH__;
    var left = try buildFrom(allocator, &l_ins);
    defer left.deinit();
    var right = try buildFrom(allocator, &r_ins);
    defer right.deinit();
    const before = left.toBuffer().len;
    left.andInPlace(&right);
    const after_op = left.toBuffer().len;
    const emptied = emptySnap(&left) and after_op == before and operandIntact(&right, &r_sorted);
    const min_j = try optU64Json(init.gpa, left.minimum());
    defer init.gpa.free(min_j);
    const max_j = try optU64Json(init.gpa, left.maximum());
    defer init.gpa.free(max_j);
    left.cleanup();
    const after_clean = left.toBuffer().len;
    const still_empty = emptySnap(&left);
    const opened = try openedIs(allocator, &left, &[_]u64{});
    var view_bm = try klyvmap.Bitmap.fromBuffer(allocator, left.toBuffer(), .borrow);
    defer view_bm.deinit();
    const opened_gone = containsNone(&view_bm, &gone);
    const snap_empty = left.isEmpty();
    const snap_card = left.getCardinality();
    const snap_c0 = left.contains(0);
    const added = try left.set(fresh);
    const has = left.contains(fresh) and left.getCardinality() == 1;
    try emitJson(init, init.gpa,
        "{{\"before\":{d},\"after_op\":{d},\"after_clean\":{d},\"emptied\":{s},\"still_empty\":{s},\"opened\":{s},\"opened_gone\":{s},\"added\":{s},\"has\":{s},\"empty\":{s},\"cardinality\":{d},\"contains0\":{s},\"min\":{s},\"max\":{s}}}",
        .{
            before, after_op, after_clean,
            jsonBool(emptied), jsonBool(still_empty), jsonBool(opened), jsonBool(opened_gone),
            jsonBool(added), jsonBool(has),
            jsonBool(snap_empty), snap_card, jsonBool(snap_c0), min_j, max_j,
        },
    );
""",
        l_ins=_ins(left),
        r_ins=_ins(right),
        r_sorted=_body(_sorted(right)),
        gone=_body(_sorted(left)),
        fresh=fresh,
    )
    require_probe_true(report, "emptied", "still_empty", "opened", "opened_gone", "added", "has")
    require_empty_snapshot(report)
    _assert_same_len(report, "before", "after_op")
    _assert_shorter(report, "before", "after_clean")


def test_after_500_prefixes_remove_all_but_zero_cleanup_then_800_high_values():
    removed, added = prefixes_500_and_800_f07()
    report = run_f07_probe(
        r"""
    const removed = [_]u64{ __REMOVED__ };
    const added = [_]u64{ __ADDED__ };
    const with0 = [_]u64{ __WITH0__ };
    var bm = try buildFrom(allocator, &with0);
    defer bm.deinit();
    for (removed) |v| _ = bm.remove(v);
    const only0 = bm.contains(0) and bm.getCardinality() == 1 and containsNone(&bm, &removed);
    bm.cleanup();
    const still0 = bm.contains(0) and bm.getCardinality() == 1 and containsNone(&bm, &removed);
    const opened0 = try openedIs(allocator, &bm, &[_]u64{0});
    var all_new = true;
    for (added) |v| {
        const was = try bm.set(v);
        if (!was or !bm.contains(v)) all_new = false;
    }
    const final_sorted = [_]u64{ __FINAL__ };
    const card = bm.getCardinality() == 801;
    const min0 = bm.minimum() == 0;
    const members = bm.contains(0) and containsAll(&bm, &added) and containsNone(&bm, &removed);
    const seq = valuesMatch(&bm, &final_sorted);
    const zero_first = zeroThenRest(&bm, final_sorted[1..]);
    try emitJson(init, init.gpa,
        "{{\"only0\":{s},\"still0\":{s},\"opened0\":{s},\"all_new\":{s},\"card\":{s},\"min0\":{s},\"members\":{s},\"seq\":{s},\"zero_first\":{s}}}",
        .{
            jsonBool(only0), jsonBool(still0), jsonBool(opened0), jsonBool(all_new),
            jsonBool(card), jsonBool(min0), jsonBool(members), jsonBool(seq), jsonBool(zero_first),
        },
    );
""",
        removed=_body(removed),
        added=_body(added),
        with0=_ins([0, *removed]),
        final=_body(_sorted([0, *added])),
    )
    require_probe_true(
        report, "only0", "still0", "opened0", "all_new", "card", "min0", "members", "seq", "zero_first"
    )


def test_cleanup_after_hundreds_of_emptied_prefixes_still_accepts_a_set():
    values, survivor, fresh = hundreds_prefixes_f07()
    dropped = [value for value in values if value != survivor]
    report = run_f07_probe(
        r"""
    const l_ins = [_]u64{ __L_INS__ };
    const r_ins = [_]u64{ __R_INS__ };
    const r_sorted = [_]u64{ __R_SORTED__ };
    const dropped = [_]u64{ __DROPPED__ };
    const survivor: u64 = __SURVIVOR__;
    const fresh: u64 = __FRESH__;
    var left = try buildFrom(allocator, &l_ins);
    defer left.deinit();
    var right = try buildFrom(allocator, &r_ins);
    defer right.deinit();
    const before = left.toBuffer().len;
    left.andInPlace(&right);
    const after_op = left.toBuffer().len;
    const held = after_op == before and left.getCardinality() == 1 and left.contains(survivor) and operandIntact(&right, &r_sorted);
    left.cleanup();
    const after_clean = left.toBuffer().len;
    const still = left.contains(survivor) and left.getCardinality() == 1;
    const opened = try openedIs(allocator, &left, &[_]u64{survivor});
    const added = try left.set(fresh);
    const both = left.contains(fresh) and left.contains(survivor) and left.getCardinality() == 2 and containsNone(&left, &dropped);
    try emitJson(init, init.gpa,
        "{{\"before\":{d},\"after_op\":{d},\"after_clean\":{d},\"held\":{s},\"still\":{s},\"opened\":{s},\"added\":{s},\"both\":{s}}}",
        .{
            before, after_op, after_clean,
            jsonBool(held), jsonBool(still), jsonBool(opened), jsonBool(added), jsonBool(both),
        },
    );
""",
        l_ins=_ins(values),
        r_ins=_body([survivor]),
        r_sorted=_body([survivor]),
        dropped=_body(dropped),
        survivor=survivor,
        fresh=fresh,
    )
    require_probe_true(report, "held", "still", "opened", "added", "both")
    _assert_same_len(report, "before", "after_op")
    _assert_shorter(report, "before", "after_clean")


def _dense_once(run: list[int], sparse: list[int], *, run_on_left: bool) -> dict:
    left = run if run_on_left else sparse
    right = sparse if run_on_left else run
    absent = unpublished_u64_f07(set(run) | set(sparse), above=1 << 32)
    report = _pair_probe(left, right, absent)
    _assert_inplace_pair(report)
    return report


def test_inplace_ops_on_dense_run_below_2_pow_16_against_sparse_values():
    run, sparse = dense_against_sparse_f07()
    inside = [value for value in sparse if value < (1 << 16) and value in set(run)]
    outside = [value for value in sparse if value < (1 << 16) and value not in set(run)]
    mid = [value for value in sparse if (1 << 16) <= value < (1 << 32)]
    if not inside or not outside or not mid:
        raise HarnessError("sparse handful is missing a required kind of value")
    if len(run) < 1000:
        raise HarnessError("dense run is under 1000")
    dense_left = _dense_once(run, sparse, run_on_left=True)
    sparse_left = _dense_once(run, sparse, run_on_left=False)
    for report in (dense_left, sparse_left):
        assert require_bool_field(report, "i_lr") is True
        assert require_bool_field(report, "i_rl") is True
        assert require_bool_field(report, "u_lr") is True
        assert require_bool_field(report, "u_rl") is True
        assert require_bool_field(report, "d_lr") is True
        assert require_bool_field(report, "d_rl") is True


def test_inplace_union_grows_consecutive_run_to_thousands_and_matches_reference_union():
    left, right, union = union_thousands_f07()
    if len(union) < 5000:
        raise HarnessError("union is under five thousand")
    absent = unpublished_u64_f07(set(union), above=1 << 32)
    report = run_f07_probe(
        r"""
    const l_ins = [_]u64{ __L_INS__ };
    const r_ins = [_]u64{ __R_INS__ };
    const r_sorted = [_]u64{ __R_SORTED__ };
    const expected = [_]u64{ __EXPECTED__ };
    const absent = [_]u64{ __ABSENT__ };
    var left = try buildFrom(allocator, &l_ins);
    defer left.deinit();
    var right = try buildFrom(allocator, &r_ins);
    defer right.deinit();
    try left.orInPlace(&right);
    const seq = valuesMatch(&left, &expected);
    const card = left.getCardinality() == expected.len;
    const ext_ok = left.minimum() == expected[0] and left.maximum() == expected[expected.len - 1];
    const members = containsAll(&left, &expected) and containsNone(&left, &absent);
    const right_ok = operandIntact(&right, &r_sorted);
    try emitJson(init, init.gpa,
        "{{\"seq\":{s},\"card\":{s},\"ext_ok\":{s},\"members\":{s},\"right_ok\":{s},\"card_n\":{d}}}",
        .{ jsonBool(seq), jsonBool(card), jsonBool(ext_ok), jsonBool(members), jsonBool(right_ok), left.getCardinality() },
    );
""",
        l_ins=_ins(left),
        r_ins=_ins(right),
        r_sorted=_body(_sorted(right)),
        expected=_body(union),
        absent=_body([absent]),
    )
    require_probe_true(report, "seq", "card", "ext_ok", "members", "right_ok")
    if require_int_field(report, "card_n") != len(union):
        raise AssertionError("union cardinality is not the reference run")


def test_after_cleanup_set_2_pow_60_and_3_reopens_as_those_three_values():
    left, survivor, right_only = spread_3000_f07()
    dropped = [value for value in left if value != survivor]
    right = [survivor, *right_only]
    absent = unpublished_u64_f07(set(left) | {1 << 60, 3})
    report = run_f07_probe(
        r"""
    const l_ins = [_]u64{ __L_INS__ };
    const r_ins = [_]u64{ __R_INS__ };
    const survivor: u64 = __SURVIVOR__;
    const absent: u64 = __ABSENT__;
    const three = [_]u64{ __THREE__ };
    var left = try buildFrom(allocator, &l_ins);
    defer left.deinit();
    var right = try buildFrom(allocator, &r_ins);
    defer right.deinit();
    left.andInPlace(&right);
    left.cleanup();
    const window = try openedIs(allocator, &left, &[_]u64{survivor});
    const add_hi = try left.set(__POW60__);
    const add_3 = try left.set(3);
    const card3 = left.getCardinality() == 3;
    const has = left.contains(survivor) and left.contains(__POW60__) and left.contains(3) and !left.contains(absent);
    const view = left.toBuffer();
    var opened = try klyvmap.Bitmap.fromBuffer(allocator, view, .borrow);
    defer opened.deinit();
    const seq = valuesMatch(&opened, &three);
    const open_card = opened.getCardinality() == 3;
    const open_has = opened.contains(survivor) and opened.contains(__POW60__) and opened.contains(3) and !opened.contains(absent);
    try emitJson(init, init.gpa,
        "{{\"window\":{s},\"add_hi\":{s},\"add_3\":{s},\"card3\":{s},\"has\":{s},\"seq\":{s},\"open_card\":{s},\"open_has\":{s}}}",
        .{
            jsonBool(window), jsonBool(add_hi), jsonBool(add_3), jsonBool(card3), jsonBool(has),
            jsonBool(seq), jsonBool(open_card), jsonBool(open_has),
        },
    );
""",
        l_ins=_ins(left),
        r_ins=_ins(right),
        survivor=survivor,
        absent=absent,
        three=_body(_sorted([survivor, 1 << 60, 3])),
        pow60=1 << 60,
    )
    require_probe_true(report, "window", "add_hi", "add_3", "card3", "has", "seq", "open_card", "open_has")
    _ = dropped


def test_emit_after_cleanup_is_version_one_even_length_at_least_64_and_aligned():
    left, survivor, right_only = spread_3000_f07()
    if survivor in (3, 1 << 60):
        raise HarnessError("survivor is named")
    right = [survivor, *right_only]
    three = _sorted([survivor, 1 << 60, 3])
    report = run_f07_probe(
        r"""
    const l_ins = [_]u64{ __L_INS__ };
    const r_ins = [_]u64{ __R_INS__ };
    const three = [_]u64{ __THREE__ };
    var left = try buildFrom(allocator, &l_ins);
    defer left.deinit();
    var right = try buildFrom(allocator, &r_ins);
    defer right.deinit();
    left.andInPlace(&right);
    left.cleanup();
    _ = try left.set(__POW60__);
    _ = try left.set(3);
    const view = left.toBuffer();
    const res = @intFromPtr(view.ptr) % 8;
    const opened = try openedIs(allocator, &left, &three);
    try emitJson(init, init.gpa,
        "{{\"res\":{d},\"opened\":{s}}}",
        .{ res, jsonBool(opened) },
    );
""",
        l_ins=_ins(left),
        r_ins=_ins(right),
        three=_body(three),
        pow60=1 << 60,
    )
    require_probe_true(report, "opened")
    if require_int_field(report, "res") != 0:
        raise AssertionError(
            f"emitted buffer address mod 8 is {report.get('res')!r}, not 0"
        )


def test_inplace_union_on_borrowed_bitmap_leaves_caller_buffer_untouched_and_updates_membership():
    caller, right, absent = borrow_sides_f07()
    union = _sorted(sorted(set(caller) | set(right)))
    report = run_f07_probe(
        r"""
    const c_ins = [_]u64{ __C_INS__ };
    const r_ins = [_]u64{ __R_INS__ };
    const c_sorted = [_]u64{ __C_SORTED__ };
    const r_sorted = [_]u64{ __R_SORTED__ };
    const uni = [_]u64{ __UNI__ };
    const absent = [_]u64{ __ABSENT__ };
    var owned = try buildFrom(allocator, &c_ins);
    const caller = try owned.toBufferCopy(allocator);
    defer allocator.free(caller);
    owned.deinit();
    const snap = try init.gpa.dupe(u8, caller);
    defer init.gpa.free(snap);
    var left = try klyvmap.Bitmap.fromBuffer(allocator, caller, .borrow);
    defer left.deinit();
    var right = try buildFrom(allocator, &r_ins);
    defer right.deinit();
    try left.orInPlace(&right);
    const bytes_same = std.mem.eql(u8, caller, snap);
    var again = try klyvmap.Bitmap.fromBuffer(allocator, caller, .borrow);
    defer again.deinit();
    const reopened = operandIntact(&again, &c_sorted) and containsNone(&again, &r_sorted);
    const left_ok = operandIntact(&left, &uni) and containsNone(&left, &absent);
    const right_ok = operandIntact(&right, &r_sorted);
    var scribbled = try init.gpa.dupe(u8, snap);
    defer init.gpa.free(scribbled);
    scribbled[0] ^= 0x5a;
    const saw_change = !std.mem.eql(u8, scribbled, snap);
    if (!saw_change) return error.ObserverSilent;
    try emitJson(init, init.gpa,
        "{{\"bytes_same\":{s},\"reopened\":{s},\"left_ok\":{s},\"right_ok\":{s},\"saw_change\":{s}}}",
        .{ jsonBool(bytes_same), jsonBool(reopened), jsonBool(left_ok), jsonBool(right_ok), jsonBool(saw_change) },
    );
""",
        c_ins=_ins(caller),
        r_ins=_ins(right),
        c_sorted=_body(_sorted(caller)),
        r_sorted=_body(_sorted(right)),
        uni=_body(union),
        absent=_body([absent]),
    )
    require_probe_true(report, "bytes_same", "reopened", "left_ok", "right_ok", "saw_change")


_REFUSE_OP = r"""
    const l_ins = [_]u64{ __L_INS__ };
    const r_ins = [_]u64{ __R_INS__ };
    const r_sorted = [_]u64{ __R_SORTED__ };
    const kept = [_]u64{ __KEPT__ };
    const dropped = [_]u64{ __DROPPED__ };
    var left_w = try buildFrom(allocator, &l_ins);
    defer left_w.deinit();
    var right_w = try buildFrom(allocator, &r_ins);
    defer right_w.deinit();
    var left_r = try buildFrom(allocator, &l_ins);
    defer left_r.deinit();
    var right_r = try buildFrom(allocator, &r_ins);
    defer right_r.deinit();
    const before_w = left_w.toBuffer().len;
    const before_r = left_r.toBuffer().len;
    __WILLING__
    const after_w = left_w.toBuffer().len;
    const willing_set = leftIs(&left_w, &kept, &dropped) and left_w.getCardinality() == kept.len and operandIntact(&right_w, &r_sorted) and after_w == before_w;
    next.hold = true;
    try proveNextAllocFails(allocator, next);
    __REFUSE__
    const completed = true;
    const after_r = left_r.toBuffer().len;
    const refuse_set = leftIs(&left_r, &kept, &dropped) and left_r.getCardinality() == kept.len and operandIntact(&right_r, &r_sorted) and after_r == before_r;
    const high_emptied = dropped.len > 0 and containsNone(&left_r, &dropped) and containsAll(&left_r, &kept);
    next.hold = false;
    try emitJson(init, init.gpa,
        "{{\"before_w\":{d},\"after_w\":{d},\"before_r\":{d},\"after_r\":{d},\"willing_set\":{s},\"completed\":{s},\"refuse_set\":{s},\"high_emptied\":{s}}}",
        .{
            before_w, after_w, before_r, after_r,
            jsonBool(willing_set), jsonBool(completed), jsonBool(refuse_set), jsonBool(high_emptied),
        },
    );
"""


def _refuse_sets() -> dict[str, str]:
    left, survivor, dropped = refuse_population_f07()
    return {
        "l_ins": _ins(left),
        "r_ins": _body([survivor]),
        "r_sorted": _body([survivor]),
        "kept": _body([survivor]),
        "dropped": _body(dropped),
    }


def test_inplace_intersection_succeeds_when_next_allocation_is_refused():
    report = run_f07_refuse(
        _REFUSE_OP.replace("__WILLING__", "left_w.andInPlace(&right_w);").replace(
            "__REFUSE__", "left_r.andInPlace(&right_r);"
        ),
        **_refuse_sets(),
    )
    require_probe_true(report, "willing_set", "completed", "refuse_set", "high_emptied")
    _assert_same_len(report, "before_w", "after_w")
    _assert_same_len(report, "before_r", "after_r")


def test_inplace_difference_succeeds_when_next_allocation_is_refused():
    left, _survivor, dropped = refuse_population_f07()
    # Difference must empty a high prefix and leave a value: right holds the dropped values.
    kept = [value for value in left if value not in set(dropped)]
    report = run_f07_refuse(
        _REFUSE_OP.replace("__WILLING__", "left_w.andNotInPlace(&right_w);").replace(
            "__REFUSE__", "left_r.andNotInPlace(&right_r);"
        ),
        l_ins=_ins(left),
        r_ins=_ins(dropped),
        r_sorted=_body(_sorted(dropped)),
        kept=_body(_sorted(kept)),
        dropped=_body(_sorted(dropped)),
    )
    require_probe_true(report, "willing_set", "completed", "refuse_set", "high_emptied")
    _assert_same_len(report, "before_w", "after_w")
    _assert_same_len(report, "before_r", "after_r")


def test_cleanup_shortens_when_next_allocation_is_refused():
    left, survivor, dropped = refuse_population_f07()
    report = run_f07_refuse(
        r"""
    const l_ins = [_]u64{ __L_INS__ };
    const r_ins = [_]u64{ __R_INS__ };
    const kept = [_]u64{ __KEPT__ };
    const dropped = [_]u64{ __DROPPED__ };
    var left_w = try buildFrom(allocator, &l_ins);
    defer left_w.deinit();
    var right_w = try buildFrom(allocator, &r_ins);
    defer right_w.deinit();
    var left_r = try buildFrom(allocator, &l_ins);
    defer left_r.deinit();
    var right_r = try buildFrom(allocator, &r_ins);
    defer right_r.deinit();
    const before_w = left_w.toBuffer().len;
    const before_r = left_r.toBuffer().len;
    left_w.andInPlace(&right_w);
    left_r.andInPlace(&right_r);
    const after_inter_w = left_w.toBuffer().len;
    const after_inter_r = left_r.toBuffer().len;
    const inter_ok = after_inter_w == before_w and after_inter_r == before_r
        and after_inter_w == after_inter_r
        and leftIs(&left_w, &kept, &dropped) and leftIs(&left_r, &kept, &dropped)
        and containsNone(&left_w, &dropped) and containsAll(&left_w, &kept);
    left_w.cleanup();
    const clean_w = left_w.toBuffer().len;
    const open_w = try openedIs(allocator, &left_w, &kept);
    const members_w = operandIntact(&left_w, &kept);
    next.hold = true;
    try proveNextAllocFails(allocator, next);
    left_r.cleanup();
    const completed = true;
    const clean_r = left_r.toBuffer().len;
    const members_r = operandIntact(&left_r, &kept);
    const open_r = try openedIs(allocator, &left_r, &kept);
    next.hold = false;
    try emitJson(init, init.gpa,
        "{{\"before_w\":{d},\"after_inter_w\":{d},\"clean_w\":{d},\"before_r\":{d},\"after_inter_r\":{d},\"clean_r\":{d},\"inter_ok\":{s},\"open_w\":{s},\"members_w\":{s},\"completed\":{s},\"members_r\":{s},\"open_r\":{s}}}",
        .{
            before_w, after_inter_w, clean_w, before_r, after_inter_r, clean_r,
            jsonBool(inter_ok), jsonBool(open_w), jsonBool(members_w),
            jsonBool(completed), jsonBool(members_r), jsonBool(open_r),
        },
    );
""",
        l_ins=_ins(left),
        r_ins=_body([survivor]),
        kept=_body([survivor]),
        dropped=_body(dropped),
    )
    require_probe_true(report, "inter_ok", "open_w", "members_w", "completed", "members_r", "open_r")
    _assert_shorter(report, "after_inter_w", "clean_w")
    _assert_shorter(report, "after_inter_r", "clean_r")


def test_inplace_set_algebra_and_cleanup_path_performs_no_file_or_network_io():
    left: list[int] = []
    while len(left) < 4:
        left.append(unpublished_u64_f07(set(left), above=1 << 32))
    right: list[int] = []
    while len(right) < 4:
        right.append(unpublished_u64_f07(set(left) | set(right), above=1 << 32))
    honest = wrap_f07_probe(
        fill_u64(
            r"""
    const l_ins = [_]u64{ __LEFT__ };
    const r_ins = [_]u64{ __RIGHT__ };
    var a = try buildFrom(allocator, &l_ins);
    defer a.deinit();
    var b = try buildFrom(allocator, &r_ins);
    defer b.deinit();
    var inter = try a.clone();
    defer inter.deinit();
    inter.andInPlace(&b);
    var uni = try a.clone();
    defer uni.deinit();
    try uni.orInPlace(&b);
    var diff = try a.clone();
    defer diff.deinit();
    diff.andNotInPlace(&b);
    diff.cleanup();
    const view = diff.toBuffer();
    if (view.len < 2) return error.ShortEmit;
    _ = view[0];
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
""",
            left=zig_u64_list(shuffle_not_sorted(left)),
            right=zig_u64_list(shuffle_not_sorted(right)),
        )
    )
    vandal = wrap_f07_probe(
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
    net_vandal = wrap_f07_probe(
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
            raise HarnessError(f"in-place I/O probe exited {run.returncode}\n{run.stderr_text}")
        created = product_created_files(before=before, roots=roots, ignore_names=harness_names)
        assert created == set(), f"in-place path wrote files: {created}"

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
            raise HarnessError(f"traced in-place probe exited {run_w.returncode}\n{run_w.stderr_text}")
        assert file_write_syscalls_in_trace(writes) == []
        from F04_helpers import unexpected_file_reads_in_trace

        assert unexpected_file_reads_in_trace(reads) == []

        run_n, hits = run_traced_arch_network(ws, [str(ws.resolve("honest"))], timeout=DEFAULT_TIMEOUT)
        if run_n.returncode != 0:
            raise HarnessError(f"traced in-place network probe exited {run_n.returncode}\n{run_n.stderr_text}")
        assert network_syscalls_in_trace(hits) == []

        run_nv, vandal_hits = run_traced_network(ws, [str(ws.resolve("net"))], timeout=DEFAULT_TIMEOUT)
        if run_nv.returncode != 0:
            raise HarnessError(f"network positive control exited {run_nv.returncode}\n{run_nv.stderr_text}")
        assert network_syscalls_in_trace(vandal_hits), "network positive control observed nothing"


# ---------------------------------------------------------------------------
# In-place results that hold 2^k - 1, 2^k or 2^k + 1 values of one prefix
# ---------------------------------------------------------------------------


def test_in_place_intersection_difference_and_union_are_exact_at_every_population_of_one_prefix():
    # For each population c, in-place intersection and in-place difference
    # leave exactly c values of one prefix on the left, in-place union grows
    # the left to exactly c, cleanup keeps each result, and the right operand
    # is unchanged. Checked against the arithmetic oracle.
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
    var andnot_ok = true;
    var or_ok = true;
    var seen: u64 = 0;
    for (checkpoints) |c| {
        const x: u64 = @min(c, (65536 - c) / 2);
        {
            var l = try Build.range(block, allocator, 0, c + x, true);
            defer l.deinit();
            var r = try Build.range(block, allocator, x, c + 2 * x, true);
            defer r.deinit();
            l.andInPlace(&r);
            and_ok = and_ok and l.getCardinality() == c + 2 and block.walk(&l, x, c + x, true);
            l.cleanup();
            and_ok = and_ok and l.getCardinality() == c + 2 and block.walk(&l, x, c + x, true);
            and_ok = and_ok and r.getCardinality() == c + x + 2 and block.walk(&r, x, c + 2 * x, true);
        }
        {
            var l = try Build.range(block, allocator, 0, c + x, true);
            defer l.deinit();
            var r = try Build.range(block, allocator, 0, x, false);
            defer r.deinit();
            _ = try block.setRange(&r, c + x, c + 2 * x);
            l.andNotInPlace(&r);
            andnot_ok = andnot_ok and l.getCardinality() == c + 2 and block.walk(&l, x, c + x, true);
            l.cleanup();
            andnot_ok = andnot_ok and l.getCardinality() == c + 2 and block.walk(&l, x, c + x, true);
            andnot_ok = andnot_ok and r.getCardinality() == 2 * x;
            var i: u64 = 0;
            while (i < 65536) : (i += 1) {
                const want = i < x or (i >= c + x and i < c + 2 * x);
                if (r.contains(block.val(i)) != want) andnot_ok = false;
            }
        }
        {
            const a = c - c / 3;
            const bb = c / 3;
            var l = try Build.range(block, allocator, 0, a, true);
            defer l.deinit();
            var r = try Build.range(block, allocator, bb, c, false);
            defer r.deinit();
            try l.orInPlace(&r);
            or_ok = or_ok and l.getCardinality() == c + 2 and block.walk(&l, 0, c, true);
            or_ok = or_ok and r.getCardinality() == c - bb and block.walk(&r, bb, c, false);
        }
        seen += 1;
    }
    try emitJson(init, init.gpa,
        "{{\"and_ok\":{s},\"andnot_ok\":{s},\"or_ok\":{s},\"seen\":{d}}}",
        .{ jsonBool(and_ok), jsonBool(andnot_ok), jsonBool(or_ok), seen },
    );
"""
    )
    require_sweep_true(report, "and_ok", "andnot_ok", "or_ok")

    require_sweep_seen(report, "seen", len(block_checkpoints()))
