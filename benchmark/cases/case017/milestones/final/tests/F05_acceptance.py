# feature: F05
"""FP-05: compact a bitmap to the smallest canonical buffer.

Assertions follow Full_PRD.original.md FP-05 (L202–L228) and the
pre-FP sentences a compact entry can trigger (L5, L7, L20–L24, L37,
L45, L55, L181).
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
    require_positive_buffer_length,
    run_bitmap_probe,
    run_traced_network,
)
from F02_helpers import (
    LARGE_PROBE_TIMEOUT,
    require_bool_field,
    require_int_field,
    shuffle_not_sorted,
    zig_u64_list,
)
from F03_helpers import compile_probe_or_raise, require_no_integer, require_strictly_ascending_once
from F04_helpers import (
    file_write_syscalls_in_trace,
    require_emit_shape,
    run_traced_arch_network,
    run_traced_file_writes,
    unexpected_file_reads_in_trace,
)
from F05_helpers import (
    fresh_high_prefix_values,
    shrink_search_inputs,
    slack_parts,
    two_routes,
    unpublished_u64_f05,
    wrap_f05_probe,
    wrap_f05_tracking,
)
from F02_helpers import (
    block_checkpoints,
    require_sweep_seen,
    require_sweep_true,
    run_block_sweep,
    shrink_checkpoints,
)
from _helpers import DEFAULT_TIMEOUT, HarnessError, workspace


def _sorted_pair(a: int, b: int) -> list[int]:
    return [a, b] if a < b else [b, a]


def _population_with_zero() -> tuple[list[int], int]:
    """More than two values, including 0 and one value above 2^32, plus an absent value."""
    high = unpublished_u64_f05(above=(1 << 32) + 1)
    others: list[int] = []
    forbidden = {0, high}
    prefixes = {0, high >> 16}
    while len(others) < 4:
        value = unpublished_u64_f05(forbidden)
        forbidden.add(value)
        others.append(value)
        prefixes.add(value >> 16)
    if len(prefixes) < 2:
        raise HarnessError("unpublished population collapsed onto one prefix")
    present = [0, high, *others]
    if len(present) == 2:
        raise HarnessError("unpublished population has the named sample size 2")
    absent = unpublished_u64_f05(set(present))
    return shuffle_not_sorted(present), absent


# ---------------------------------------------------------------------------
# A. Membership, cardinality, extrema, order survive compact
# ---------------------------------------------------------------------------


def test_compact_keeps_42_and_value_above_2_pow_40_through_emit_and_open():
    high = unpublished_u64_f05(above=1 << 40)
    absent = unpublished_u64_f05({42, high})
    ordered = _sorted_pair(42, high)
    require_strictly_ascending_once(ordered, cardinality=2)
    source = wrap_f05_tracking(
        fill_u64(
            r"""
    const high: u64 = __HIGH__;
    const absent: u64 = __ABSENT__;
    const ordered = [_]u64{ __ORDERED__ };
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    const new42 = try bm.set(42);
    const new_high = try bm.set(high);
    const absent_before = !bm.contains(absent);
    try bm.compact();
    const has42 = bm.contains(42);
    const has_high = bm.contains(high);
    const absent_after = !bm.contains(absent);
    const card = bm.getCardinality() == 2;
    const mn = bm.minimum() orelse return error.MinAbsent;
    const mx = bm.maximum() orelse return error.MaxAbsent;
    const extrema = mn == ordered[0] and mx == ordered[1];
    const seq = valuesMatch(&bm, &ordered);
    const view = bm.toBuffer();
    var opened = klyvmap.Bitmap.fromBuffer(allocator, view, .borrow) catch return error.OpenFailed;
    defer opened.deinit();
    const open_card = opened.getCardinality() == 2;
    const open_seq = valuesMatch(&opened, &ordered);
    try emitJson(init, init.gpa,
        "{{\"new42\":{s},\"new_high\":{s},\"absent_before\":{s},\"has42\":{s},\"has_high\":{s},\"absent_after\":{s},\"card\":{s},\"extrema\":{s},\"seq\":{s},\"open_card\":{s},\"open_seq\":{s}}}",
        .{
            jsonBool(new42), jsonBool(new_high), jsonBool(absent_before), jsonBool(has42),
            jsonBool(has_high), jsonBool(absent_after), jsonBool(card), jsonBool(extrema),
            jsonBool(seq), jsonBool(open_card), jsonBool(open_seq),
        },
    );
""",
            high=high,
            absent=absent,
            ordered=zig_u64_list(ordered),
        )
    )
    report = run_bitmap_probe(source)
    for key in (
        "new42",
        "new_high",
        "absent_before",
        "has42",
        "has_high",
        "absent_after",
        "card",
        "extrema",
        "seq",
        "open_card",
        "open_seq",
    ):
        assert require_bool_field(report, key) is True, key


def test_compact_keeps_unpublished_membership_cardinality_extrema_and_order():
    present, absent = _population_with_zero()
    ordered = sorted(present)
    require_strictly_ascending_once(ordered, cardinality=len(ordered))
    if 0 not in present:
        raise HarnessError("zero variant missing from the unpublished population")
    if not any(value > (1 << 32) for value in present):
        raise HarnessError("unpublished population has no value above 2^32")
    source = wrap_f05_tracking(
        fill_u64(
            r"""
    const inserted = [_]u64{ __INSERTED__ };
    const ordered = [_]u64{ __ORDERED__ };
    const absent: u64 = __ABSENT__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    for (inserted) |v| _ = try bm.set(v);
    const before_seq = valuesMatch(&bm, &ordered);
    const before_absent = !bm.contains(absent);
    const before_card = bm.getCardinality();
    const before_min = bm.minimum() orelse return error.MinAbsent;
    const before_max = bm.maximum() orelse return error.MaxAbsent;
    try bm.compact();
    const seq = valuesMatch(&bm, &ordered);
    const still_absent = !bm.contains(absent);
    const card_same = bm.getCardinality() == before_card and before_card == ordered.len;
    const mn = bm.minimum() orelse return error.MinGone;
    const mx = bm.maximum() orelse return error.MaxGone;
    const extrema = mn == before_min and mx == before_max and mn == ordered[0] and mx == ordered[ordered.len - 1];
    const has_zero = bm.contains(0);
    try emitJson(init, init.gpa,
        "{{\"before_seq\":{s},\"before_absent\":{s},\"seq\":{s},\"still_absent\":{s},\"card_same\":{s},\"extrema\":{s},\"has_zero\":{s},\"card\":{d}}}",
        .{
            jsonBool(before_seq), jsonBool(before_absent), jsonBool(seq), jsonBool(still_absent),
            jsonBool(card_same), jsonBool(extrema), jsonBool(has_zero), bm.getCardinality(),
        },
    );
""",
            inserted=zig_u64_list(present),
            ordered=zig_u64_list(ordered),
            absent=absent,
        )
    )
    report = run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
    for key in ("before_seq", "before_absent", "seq", "still_absent", "card_same", "extrema", "has_zero"):
        assert require_bool_field(report, key) is True, key
    assert require_int_field(report, "card") == len(ordered)


# ---------------------------------------------------------------------------
# B. Compact does not freeze the bitmap
# ---------------------------------------------------------------------------


def test_after_compact_second_set_of_present_value_is_not_new():
    present, _absent = _population_with_zero()
    ordered = sorted(present)
    again = ordered[len(ordered) // 2]
    source = wrap_f05_tracking(
        fill_u64(
            r"""
    const inserted = [_]u64{ __INSERTED__ };
    const ordered = [_]u64{ __ORDERED__ };
    const again: u64 = __AGAIN__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    for (inserted) |v| _ = try bm.set(v);
    try bm.compact();
    const card_at = bm.getCardinality();
    const was_there = bm.contains(again);
    const report_new = try bm.set(again);
    const still = bm.contains(again);
    const card_same = bm.getCardinality() == card_at and card_at == ordered.len;
    const seq = valuesMatch(&bm, &ordered);
    try emitJson(init, init.gpa,
        "{{\"was_there\":{s},\"report_new\":{s},\"still\":{s},\"card_same\":{s},\"seq\":{s}}}",
        .{ jsonBool(was_there), jsonBool(report_new), jsonBool(still), jsonBool(card_same), jsonBool(seq) },
    );
""",
            inserted=zig_u64_list(present),
            ordered=zig_u64_list(ordered),
            again=again,
        )
    )
    report = run_bitmap_probe(source)
    assert require_bool_field(report, "was_there") is True
    assert require_bool_field(report, "report_new") is False
    assert require_bool_field(report, "still") is True
    assert require_bool_field(report, "card_same") is True
    assert require_bool_field(report, "seq") is True


def test_after_compact_set_of_absent_value_is_new_and_present():
    present, absent = _population_with_zero()
    if absent == (1 << 40):
        raise HarnessError("absent draw landed on the named 2^40")
    ordered = sorted(present)
    grown = sorted([*present, absent])
    source = wrap_f05_tracking(
        fill_u64(
            r"""
    const inserted = [_]u64{ __INSERTED__ };
    const ordered = [_]u64{ __ORDERED__ };
    const grown = [_]u64{ __GROWN__ };
    const absent: u64 = __ABSENT__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    for (inserted) |v| _ = try bm.set(v);
    try bm.compact();
    const card_at = bm.getCardinality();
    const was_absent = !bm.contains(absent);
    const report_new = try bm.set(absent);
    const now = bm.contains(absent);
    const card_up = bm.getCardinality() == card_at + 1 and bm.getCardinality() == grown.len;
    const old_ok = containsAll(&bm, &ordered);
    const seq = valuesMatch(&bm, &grown);
    try emitJson(init, init.gpa,
        "{{\"was_absent\":{s},\"report_new\":{s},\"now\":{s},\"card_up\":{s},\"old_ok\":{s},\"seq\":{s}}}",
        .{
            jsonBool(was_absent), jsonBool(report_new), jsonBool(now), jsonBool(card_up),
            jsonBool(old_ok), jsonBool(seq),
        },
    );
""",
            inserted=zig_u64_list(present),
            ordered=zig_u64_list(ordered),
            grown=zig_u64_list(grown),
            absent=absent,
        )
    )
    report = run_bitmap_probe(source)
    for key in ("was_absent", "report_new", "now", "card_up", "old_ok", "seq"):
        assert require_bool_field(report, key) is True, key


def test_compact_empty_stays_empty_then_accepts_2_pow_40():
    source = wrap_f05_tracking(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    try bm.compact();
    const empty = bm.isEmpty();
    const card = bm.getCardinality();
    const contains0 = bm.contains(0);
    const min_j = try optU64Json(init.gpa, bm.minimum());
    defer init.gpa.free(min_j);
    const max_j = try optU64Json(init.gpa, bm.maximum());
    defer init.gpa.free(max_j);
    const added = try bm.set(1 << 40);
    const has = bm.contains(1 << 40);
    const card1 = bm.getCardinality() == 1;
    const mn = bm.minimum() orelse return error.MinAbsent;
    const mx = bm.maximum() orelse return error.MaxAbsent;
    const extrema = mn == (1 << 40) and mx == (1 << 40);
    const not_empty = !bm.isEmpty();
    try emitJson(init, init.gpa,
        "{{\"empty\":{s},\"cardinality\":{d},\"contains0\":{s},\"min\":{s},\"max\":{s},\"added\":{s},\"has\":{s},\"card1\":{s},\"extrema\":{s},\"not_empty\":{s}}}",
        .{
            jsonBool(empty), card, jsonBool(contains0), min_j, max_j,
            jsonBool(added), jsonBool(has), jsonBool(card1), jsonBool(extrema), jsonBool(not_empty),
        },
    );
"""
    )
    report = run_bitmap_probe(source)
    require_empty_snapshot(report)
    require_no_integer(report, "min")
    require_no_integer(report, "max")
    assert require_bool_field(report, "added") is True
    assert require_bool_field(report, "has") is True
    assert require_bool_field(report, "card1") is True
    assert require_bool_field(report, "extrema") is True
    assert require_bool_field(report, "not_empty") is True


# ---------------------------------------------------------------------------
# C. Two routes become byte-identical after compact
# ---------------------------------------------------------------------------


def _route_probe(union_vals: list[int], removed: list[int], final: list[int]) -> dict:
    require_strictly_ascending_once(final, cardinality=len(final))
    source = wrap_f05_tracking(
        fill_u64(
            r"""
    const union_vals = [_]u64{ __UNION__ };
    const removed = [_]u64{ __REMOVED__ };
    const final_vals = [_]u64{ __FINAL__ };
    var long = try buildFrom(allocator, &union_vals);
    defer long.deinit();
    for (removed) |v| _ = long.remove(v);
    var direct = try buildFrom(allocator, &final_vals);
    defer direct.deinit();
    try long.compact();
    try direct.compact();
    const same = bytesEqual(&long, &direct);
    const long_ok = valuesMatch(&long, &final_vals);
    const direct_ok = valuesMatch(&direct, &final_vals);
    var removed_gone = true;
    for (removed) |v| {
        if (long.contains(v) or direct.contains(v)) removed_gone = false;
    }
    try emitJson(init, init.gpa,
        "{{\"same\":{s},\"long_ok\":{s},\"direct_ok\":{s},\"removed_gone\":{s},\"card\":{d}}}",
        .{ jsonBool(same), jsonBool(long_ok), jsonBool(direct_ok), jsonBool(removed_gone), long.getCardinality() },
    );
""",
            union=zig_u64_list(union_vals),
            removed=zig_u64_list(removed),
            final=zig_u64_list(final),
        )
    )
    return run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)


def _assert_routes(report: dict, final: list[int]) -> None:
    assert require_bool_field(report, "same") is True
    assert require_bool_field(report, "long_ok") is True
    assert require_bool_field(report, "direct_ok") is True
    assert require_bool_field(report, "removed_gone") is True
    assert require_int_field(report, "card") == len(final)


def test_two_routes_to_the_same_set_match_in_use_bytes_after_compact():
    union_vals, removed, final = two_routes()
    _assert_routes(_route_probe(union_vals, removed, final), final)


def test_unpublished_second_pair_of_routes_match_after_compact():
    union_vals, removed, final = two_routes()
    _assert_routes(_route_probe(union_vals, removed, final), final)


# ---------------------------------------------------------------------------
# D. Shrink one value, compact again, match a direct remainder
# ---------------------------------------------------------------------------


def _shrink_probe(how: int) -> dict:
    inserted, remainders, widths, drops = shrink_search_inputs()
    source = wrap_f05_tracking(
        fill_u64(
            r"""
    const inserted = [_]u64{ __INSERTED__ };
    const remainders = [_]u64{ __REMAINDERS__ };
    const widths = [_]usize{ __WIDTHS__ };
    const drops = [_]usize{ __DROPS__ };
    const how: u8 = __HOW__;
    var in_off: usize = 0;
    var rest_off: usize = 0;
    var equal_hits: usize = 0;
    var bytes_ok = true;
    var values_ok = true;
    for (widths, drops) |n, drop_at| {
        const order = inserted[in_off..][0..n];
        in_off += n;
        const rest = remainders[rest_off..][0 .. n - 1];
        rest_off += n - 1;
        var bm = try buildFrom(allocator, order);
        try bm.compact();
        const dropped = order[drop_at];
        if (how == 0) {
            _ = bm.remove(dropped);
        } else if (how == 1) {
            var right = try klyvmap.Bitmap.init(allocator);
            _ = try right.set(dropped);
            bm.andNotInPlace(&right);
            right.deinit();
        } else {
            var right = try buildFrom(allocator, rest);
            bm.andInPlace(&right);
            right.deinit();
        }
        const mid_len = bm.toBuffer().len;
        var direct = try buildFrom(allocator, rest);
        try direct.compact();
        if (mid_len == direct.toBuffer().len) equal_hits += 1;
        try bm.compact();
        if (!bytesEqual(&bm, &direct)) bytes_ok = false;
        if (!valuesMatch(&bm, rest) or bm.contains(dropped)) values_ok = false;
        if (bm.getCardinality() != rest.len) values_ok = false;
        bm.deinit();
        direct.deinit();
    }
    try emitJson(init, init.gpa,
        "{{\"equal_hits\":{d},\"bytes_ok\":{s},\"values_ok\":{s},\"rounds\":{d}}}",
        .{ equal_hits, jsonBool(bytes_ok), jsonBool(values_ok), widths.len },
    );
""",
            inserted=zig_u64_list(inserted),
            remainders=zig_u64_list(remainders),
            widths=", ".join(str(n) for n in widths),
            drops=", ".join(str(n) for n in drops),
            how=how,
        )
    )
    return run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)


def _assert_shrink(report: dict) -> None:
    rounds = require_int_field(report, "rounds")
    if rounds < 2:
        raise HarnessError(f"shrink search ran {rounds} rounds")
    # Post-compact in-use bytes must match a direct remainder on every round,
    # including a round whose length already matched before that compact.
    # No round is required to already have that length.
    assert require_bool_field(report, "bytes_ok") is True
    assert require_bool_field(report, "values_ok") is True


def test_remove_one_then_compact_matches_direct_remainder():
    _assert_shrink(_shrink_probe(0))


def test_in_place_difference_of_one_then_compact_matches_direct_remainder():
    _assert_shrink(_shrink_probe(1))


def test_in_place_intersection_dropping_one_then_compact_matches_direct_remainder():
    _assert_shrink(_shrink_probe(2))


# ---------------------------------------------------------------------------
# E. Slack workload shortens, matches the direct set, second compact is stable
# ---------------------------------------------------------------------------


def _slack_source(parts: dict[str, list[int]], *, do_second: bool, do_new: bool) -> str:
    fresh: list[int] = []
    if do_new:
        fresh = fresh_high_prefix_values(parts["kept"], 2000)
    fresh_lit = zig_u64_list(fresh) if fresh else "0"
    return wrap_f05_probe(
        fill_u64(
            r"""
    const inserted = [_]u64{ __INSERTED__ };
    const removed = [_]u64{ __REMOVED__ };
    const kept = [_]u64{ __KEPT__ };
    const fresh = [_]u64{ __FRESH__ };
    const do_second = __DO_SECOND__;
    const do_new = __DO_NEW__;

    var built = try buildFrom(allocator, &inserted);
    for (removed) |v| _ = built.remove(v);
    const pre_len = built.toBuffer().len;
    const pre_seq = valuesMatch(&built, &kept);
    try built.compact();
    const post_len = built.toBuffer().len;
    const post_seq = valuesMatch(&built, &kept);
    const shortened = post_len < pre_len;

    var direct = try buildFrom(allocator, &kept);
    try direct.compact();
    const matched = bytesEqual(&built, &direct);
    direct.deinit();

    var willing_len: usize = post_len;
    var willing_seq = true;
    var willing_ok = true;
    if (do_second) {
        var again = try buildFrom(allocator, &inserted);
        for (removed) |v| _ = again.remove(v);
        try again.compact();
        const first_len = again.toBuffer().len;
        if (first_len != post_len) willing_ok = false;
        try again.compact();
        willing_len = again.toBuffer().len;
        willing_seq = valuesMatch(&again, &kept);
        if (willing_len != post_len) willing_ok = false;
        again.deinit();
    }

    const refuse_control = true;
    var refuse_ok = true;
    var refuse_len: usize = post_len;
    var refuse_seq = true;
    if (do_second) {
        var held = try buildFrom(allocator, &inserted);
        for (removed) |v| _ = held.remove(v);
        try held.compact();
        const first_len = held.toBuffer().len;
        gate.block = true;
        const live_before = gate.live;
        const refused_before = gate.refused;
        if (allocator.alignedAlloc(u8, .@"8", 64)) |_| {
            return error.RefuseReportedSuccess;
        } else |_| {}
        if (gate.live != live_before or gate.refused <= refused_before) return error.RefuseSilent;
        try held.compact();
        refuse_len = held.toBuffer().len;
        refuse_seq = valuesMatch(&held, &kept);
        if (first_len != post_len or refuse_len != willing_len) refuse_ok = false;
        gate.block = false;
        held.deinit();
    }

    var new_ok = true;
    if (do_new) {
        var host = try buildFrom(allocator, &inserted);
        for (removed) |v| _ = host.remove(v);
        try host.compact();
        try host.compact();
        const old_card = host.getCardinality();
        var added_all = true;
        for (fresh) |v| {
            const was = try host.set(v);
            if (!was or !host.contains(v)) added_all = false;
        }
        const old_kept = containsAll(&host, &kept);
        const card_up = host.getCardinality() == old_card + fresh.len and fresh.len == 2000;
        new_ok = added_all and old_kept and card_up;
        host.deinit();
    }
    built.deinit();

    try emitJson(init, init.gpa,
        "{{\"pre_len\":{d},\"post_len\":{d},\"shortened\":{s},\"pre_seq\":{s},\"post_seq\":{s},\"matched\":{s},\"willing_ok\":{s},\"willing_seq\":{s},\"willing_len\":{d},\"refuse_control\":{s},\"refuse_ok\":{s},\"refuse_seq\":{s},\"refuse_len\":{d},\"new_ok\":{s}}}",
        .{
            pre_len, post_len, jsonBool(shortened), jsonBool(pre_seq), jsonBool(post_seq), jsonBool(matched),
            jsonBool(willing_ok), jsonBool(willing_seq), willing_len,
            jsonBool(refuse_control), jsonBool(refuse_ok), jsonBool(refuse_seq), refuse_len,
            jsonBool(new_ok),
        },
    );
""",
            inserted=zig_u64_list(parts["inserted"]),
            removed=zig_u64_list(parts["removed"]),
            kept=zig_u64_list(parts["kept"]),
            fresh=fresh_lit,
            do_second="true" if do_second else "false",
            do_new="true" if do_new else "false",
        )
    )


def _run_slack(parts: dict[str, list[int]], *, do_second: bool, do_new: bool) -> dict:
    require_strictly_ascending_once(parts["kept"], cardinality=len(parts["kept"]))
    require_positive_buffer_length(len(parts["kept"]))
    return run_bitmap_probe(
        _slack_source(parts, do_second=do_second, do_new=do_new),
        timeout=LARGE_PROBE_TIMEOUT,
    )


def test_slack_workload_compact_shortens_keeps_values_and_matches_direct_remainder():
    report = _run_slack(slack_parts(), do_second=False, do_new=False)
    pre = require_int_field(report, "pre_len")
    post = require_int_field(report, "post_len")
    require_positive_buffer_length(pre)
    require_positive_buffer_length(post)
    assert post < pre
    assert require_bool_field(report, "shortened") is True
    assert require_bool_field(report, "pre_seq") is True
    assert require_bool_field(report, "post_seq") is True
    assert require_bool_field(report, "matched") is True


def test_second_compact_keeps_length_when_allocator_still_allocates():
    report = _run_slack(slack_parts(), do_second=True, do_new=False)
    pre = require_int_field(report, "pre_len")
    post = require_int_field(report, "post_len")
    require_positive_buffer_length(pre)
    require_positive_buffer_length(post)
    assert post < pre
    assert require_bool_field(report, "shortened") is True
    assert require_bool_field(report, "willing_ok") is True
    assert require_bool_field(report, "willing_seq") is True
    assert require_bool_field(report, "pre_seq") is True
    assert require_bool_field(report, "post_seq") is True
    assert require_int_field(report, "willing_len") == post


def test_second_compact_keeps_length_when_allocator_refuses_next_allocation():
    report = _run_slack(slack_parts(), do_second=True, do_new=False)
    pre = require_int_field(report, "pre_len")
    post = require_int_field(report, "post_len")
    require_positive_buffer_length(pre)
    require_positive_buffer_length(post)
    assert post < pre
    assert require_bool_field(report, "shortened") is True
    assert require_bool_field(report, "pre_seq") is True
    assert require_bool_field(report, "post_seq") is True
    assert require_bool_field(report, "refuse_control") is True
    assert require_bool_field(report, "refuse_ok") is True
    assert require_bool_field(report, "refuse_seq") is True
    assert require_int_field(report, "refuse_len") == require_int_field(report, "willing_len")
    assert require_int_field(report, "refuse_len") == post


def test_after_that_second_compact_two_thousand_new_high_prefix_values_keep_the_old_ones():
    report = _run_slack(slack_parts(), do_second=True, do_new=True)
    assert require_bool_field(report, "new_ok") is True
    assert require_bool_field(report, "post_seq") is True


def test_unpublished_slack_workload_shortens_and_matches_direct_remainder():
    report = _run_slack(slack_parts(), do_second=False, do_new=False)
    pre = require_int_field(report, "pre_len")
    post = require_int_field(report, "post_len")
    assert post < pre
    assert require_bool_field(report, "pre_seq") is True
    assert require_bool_field(report, "post_seq") is True
    assert require_bool_field(report, "matched") is True


# ---------------------------------------------------------------------------
# F. Borrowed canonical buffer
# ---------------------------------------------------------------------------


def _borrow_population() -> tuple[list[int], list[int]]:
    companions = [unpublished_u64_f05() for _ in range(4)]
    # Keep drawing until none collided with 99.
    forbidden = {99}
    companions = []
    while len(companions) < 4:
        value = unpublished_u64_f05(forbidden)
        forbidden.add(value)
        companions.append(value)
    present = shuffle_not_sorted([99, *companions])
    return present, sorted(present)


def test_compact_borrowed_canonical_buffer_owns_same_length_without_writing_caller():
    present, ordered = _borrow_population()
    source = wrap_f05_tracking(
        fill_u64(
            r"""
    const inserted = [_]u64{ __INSERTED__ };
    const ordered = [_]u64{ __ORDERED__ };
    var bm = try buildFrom(allocator, &inserted);
    try bm.compact();
    const caller = try bm.toBufferCopy(allocator);
    bm.deinit();
    const snap = try init.gpa.dupe(u8, caller);
    defer init.gpa.free(snap);
    var borrowed = klyvmap.Bitmap.fromBuffer(allocator, caller, .borrow) catch return error.BorrowFailed;
    const before = track.live;
    try borrowed.compact();
    const view = borrowed.toBuffer();
    const seq = valuesMatch(&borrowed, &ordered);
    const len_same = view.len == caller.len and view.len == snap.len;
    const caller_same = std.mem.eql(u8, caller, snap);
    const distinct = @intFromPtr(view.ptr) != @intFromPtr(caller.ptr);
    const grew = track.live >= before + view.len;
    const shaped = shapeOf(view) catch return error.Shape;
    borrowed.deinit();
    const released = track.live + view.len <= before + caller.len;
    // Owned compact storage is gone; the caller allocation is still outstanding.
    const live_back = track.live == before;
    const caller_after = std.mem.eql(u8, caller, snap);
    const scribble = try init.gpa.dupe(u8, snap);
    defer init.gpa.free(scribble);
    scribble[0] ^= 0x5a;
    const scribble_changed = !std.mem.eql(u8, scribble, snap);
    const base = track.live;
    const parked = try allocator.alignedAlloc(u8, .@"8", 48);
    const held = track.live > base;
    allocator.free(parked);
    const restored = track.live == base;
    if (!scribble_changed or !held or !restored) return error.ObserverSilent;
    allocator.free(caller);
    try emitJson(init, init.gpa,
        "{{\"len_same\":{s},\"caller_same\":{s},\"distinct\":{s},\"grew\":{s},\"caller_after\":{s},\"released\":{s},\"live_back\":{s},\"seq\":{s},\"len\":{d},\"b0\":{d},\"b1\":{d},\"res\":{d}}}",
        .{
            jsonBool(len_same), jsonBool(caller_same), jsonBool(distinct), jsonBool(grew),
            jsonBool(caller_after), jsonBool(released), jsonBool(live_back), jsonBool(seq),
            shaped.len, shaped.b0, shaped.b1, shaped.res,
        },
    );
""",
            inserted=zig_u64_list(present),
            ordered=zig_u64_list(ordered),
        )
    )
    report = run_bitmap_probe(source)
    for key in ("len_same", "caller_same", "distinct", "grew", "caller_after", "released", "live_back", "seq"):
        assert require_bool_field(report, key) is True, key
    require_emit_shape(report, length="len", b0="b0", b1="b1", residue="res")


def test_borrowed_compact_emit_opens_with_the_same_sequence():
    present, ordered = _borrow_population()
    require_strictly_ascending_once(ordered, cardinality=len(ordered))
    source = wrap_f05_tracking(
        fill_u64(
            r"""
    const inserted = [_]u64{ __INSERTED__ };
    const ordered = [_]u64{ __ORDERED__ };
    var bm = try buildFrom(allocator, &inserted);
    try bm.compact();
    const caller = try bm.toBufferCopy(allocator);
    defer allocator.free(caller);
    bm.deinit();
    var borrowed = klyvmap.Bitmap.fromBuffer(allocator, caller, .borrow) catch return error.BorrowFailed;
    defer borrowed.deinit();
    try borrowed.compact();
    const view = borrowed.toBuffer();
    var opened = klyvmap.Bitmap.fromBuffer(allocator, view, .borrow) catch return error.OpenFailed;
    defer opened.deinit();
    const seq = valuesMatch(&opened, &ordered);
    const card = opened.getCardinality() == ordered.len;
    const has99 = opened.contains(99);
    const distinct = @intFromPtr(view.ptr) != @intFromPtr(caller.ptr);
    try emitJson(init, init.gpa,
        "{{\"seq\":{s},\"card\":{s},\"has99\":{s},\"distinct\":{s},\"card_n\":{d}}}",
        .{ jsonBool(seq), jsonBool(card), jsonBool(has99), jsonBool(distinct), opened.getCardinality() },
    );
""",
            inserted=zig_u64_list(present),
            ordered=zig_u64_list(ordered),
        )
    )
    report = run_bitmap_probe(source)
    assert require_bool_field(report, "seq") is True
    assert require_bool_field(report, "card") is True
    assert require_bool_field(report, "has99") is True
    assert require_bool_field(report, "distinct") is True
    assert require_int_field(report, "card_n") == len(ordered)


def test_after_borrowed_compact_set_reports_and_round_trips_without_writing_caller():
    present, ordered = _borrow_population()
    again = ordered[0]
    fresh = unpublished_u64_f05(set(present))
    grown = sorted([*present, fresh])
    source = wrap_f05_tracking(
        fill_u64(
            r"""
    const inserted = [_]u64{ __INSERTED__ };
    const ordered = [_]u64{ __ORDERED__ };
    const grown = [_]u64{ __GROWN__ };
    const again: u64 = __AGAIN__;
    const fresh: u64 = __FRESH__;
    var bm = try buildFrom(allocator, &inserted);
    try bm.compact();
    const caller = try bm.toBufferCopy(allocator);
    defer allocator.free(caller);
    bm.deinit();
    const snap = try init.gpa.dupe(u8, caller);
    defer init.gpa.free(snap);
    var borrowed = klyvmap.Bitmap.fromBuffer(allocator, caller, .borrow) catch return error.BorrowFailed;
    defer borrowed.deinit();
    try borrowed.compact();
    const dup = try borrowed.set(again);
    const card_same = borrowed.getCardinality() == ordered.len;
    const added = try borrowed.set(fresh);
    const has_fresh = borrowed.contains(fresh);
    const card_up = borrowed.getCardinality() == ordered.len + 1;
    const old_ok = containsAll(&borrowed, &ordered);
    const caller_same = std.mem.eql(u8, caller, snap);
    const view = borrowed.toBuffer();
    var opened = klyvmap.Bitmap.fromBuffer(allocator, view, .borrow) catch return error.OpenFailed;
    defer opened.deinit();
    const seq = valuesMatch(&opened, &grown);
    const open_card = opened.getCardinality() == grown.len;
    try emitJson(init, init.gpa,
        "{{\"dup\":{s},\"card_same\":{s},\"added\":{s},\"has_fresh\":{s},\"card_up\":{s},\"old_ok\":{s},\"caller_same\":{s},\"seq\":{s},\"open_card\":{s}}}",
        .{
            jsonBool(dup), jsonBool(card_same), jsonBool(added), jsonBool(has_fresh), jsonBool(card_up),
            jsonBool(old_ok), jsonBool(caller_same), jsonBool(seq), jsonBool(open_card),
        },
    );
""",
            inserted=zig_u64_list(present),
            ordered=zig_u64_list(ordered),
            grown=zig_u64_list(grown),
            again=again,
            fresh=fresh,
        )
    )
    report = run_bitmap_probe(source)
    assert require_bool_field(report, "dup") is False
    for key in ("card_same", "added", "has_fresh", "card_up", "old_ok", "caller_same", "seq", "open_card"):
        assert require_bool_field(report, key) is True, key


def test_remove_99_after_borrowed_compact_is_legal_and_caller_bytes_stay():
    present, ordered = _borrow_population()
    rest = [value for value in ordered if value != 99]
    source = wrap_f05_tracking(
        fill_u64(
            r"""
    const inserted = [_]u64{ __INSERTED__ };
    const ordered = [_]u64{ __ORDERED__ };
    const rest = [_]u64{ __REST__ };
    var bm = try buildFrom(allocator, &inserted);
    try bm.compact();
    const caller = try bm.toBufferCopy(allocator);
    defer allocator.free(caller);
    bm.deinit();
    const snap = try init.gpa.dupe(u8, caller);
    defer init.gpa.free(snap);
    var borrowed = klyvmap.Bitmap.fromBuffer(allocator, caller, .borrow) catch return error.BorrowFailed;
    defer borrowed.deinit();
    try borrowed.compact();
    const was = borrowed.remove(99);
    const gone = !borrowed.contains(99);
    const kept = containsAll(&borrowed, &rest);
    const card = borrowed.getCardinality() == rest.len;
    const caller_same = std.mem.eql(u8, caller, snap);
    var reopened = klyvmap.Bitmap.fromBuffer(allocator, caller, .borrow) catch return error.ReopenFailed;
    const caller_still = valuesMatch(&reopened, &ordered) and reopened.contains(99);
    reopened.deinit();
    const view = borrowed.toBuffer();
    var opened = klyvmap.Bitmap.fromBuffer(allocator, view, .borrow) catch return error.OpenFailed;
    defer opened.deinit();
    const owned_seq = valuesMatch(&opened, &rest);
    const owned_omits = !opened.contains(99);
    try emitJson(init, init.gpa,
        "{{\"was\":{s},\"gone\":{s},\"kept\":{s},\"card\":{s},\"caller_same\":{s},\"caller_still\":{s},\"owned_seq\":{s},\"owned_omits\":{s}}}",
        .{
            jsonBool(was), jsonBool(gone), jsonBool(kept), jsonBool(card), jsonBool(caller_same),
            jsonBool(caller_still), jsonBool(owned_seq), jsonBool(owned_omits),
        },
    );
""",
            inserted=zig_u64_list(present),
            ordered=zig_u64_list(ordered),
            rest=zig_u64_list(rest),
        )
    )
    report = run_bitmap_probe(source)
    for key in ("was", "gone", "kept", "card", "caller_same", "caller_still", "owned_seq", "owned_omits"):
        assert require_bool_field(report, key) is True, key


def test_unpublished_companions_on_borrowed_canonical_compact_do_not_write_caller():
    present, ordered = _borrow_population()
    source = wrap_f05_tracking(
        fill_u64(
            r"""
    const inserted = [_]u64{ __INSERTED__ };
    const ordered = [_]u64{ __ORDERED__ };
    var bm = try buildFrom(allocator, &inserted);
    try bm.compact();
    const caller = try bm.toBufferCopy(allocator);
    defer allocator.free(caller);
    bm.deinit();
    const snap = try init.gpa.dupe(u8, caller);
    defer init.gpa.free(snap);
    var borrowed = klyvmap.Bitmap.fromBuffer(allocator, caller, .borrow) catch return error.BorrowFailed;
    defer borrowed.deinit();
    try borrowed.compact();
    const len_same = borrowed.toBuffer().len == caller.len;
    const caller_same = std.mem.eql(u8, caller, snap);
    var opened = klyvmap.Bitmap.fromBuffer(allocator, borrowed.toBuffer(), .borrow) catch return error.OpenFailed;
    defer opened.deinit();
    const seq = valuesMatch(&opened, &ordered);
    try emitJson(init, init.gpa,
        "{{\"len_same\":{s},\"caller_same\":{s},\"seq\":{s}}}",
        .{ jsonBool(len_same), jsonBool(caller_same), jsonBool(seq) },
    );
""",
            inserted=zig_u64_list(present),
            ordered=zig_u64_list(ordered),
        )
    )
    report = run_bitmap_probe(source)
    for key in ("len_same", "caller_same", "seq"):
        assert require_bool_field(report, key) is True, key


# ---------------------------------------------------------------------------
# G. Emit after compact opens, and is still a well-formed buffer
# ---------------------------------------------------------------------------


def test_emit_after_compact_opens_with_same_cardinality_and_value_sequence():
    parts = slack_parts()
    require_strictly_ascending_once(parts["kept"], cardinality=len(parts["kept"]))
    source = wrap_f05_tracking(
        fill_u64(
            r"""
    const inserted = [_]u64{ __INSERTED__ };
    const removed = [_]u64{ __REMOVED__ };
    const kept = [_]u64{ __KEPT__ };
    var bm = try buildFrom(allocator, &inserted);
    defer bm.deinit();
    for (removed) |v| _ = bm.remove(v);
    try bm.compact();
    const card = bm.getCardinality();
    var opened = klyvmap.Bitmap.fromBuffer(allocator, bm.toBuffer(), .borrow) catch return error.OpenFailed;
    defer opened.deinit();
    const open_card = opened.getCardinality() == card and card == kept.len;
    const seq = valuesMatch(&opened, &kept);
    const src_seq = valuesMatch(&bm, &kept);
    try emitJson(init, init.gpa,
        "{{\"open_card\":{s},\"seq\":{s},\"src_seq\":{s},\"card\":{d}}}",
        .{ jsonBool(open_card), jsonBool(seq), jsonBool(src_seq), card },
    );
""",
            inserted=zig_u64_list(parts["inserted"]),
            removed=zig_u64_list(parts["removed"]),
            kept=zig_u64_list(parts["kept"]),
        )
    )
    report = run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
    assert require_bool_field(report, "open_card") is True
    assert require_bool_field(report, "seq") is True
    assert require_bool_field(report, "src_seq") is True
    assert require_int_field(report, "card") == len(parts["kept"])


def test_compacted_emit_is_even_length_and_aligned():
    parts = slack_parts()
    present, _ordered = _borrow_population()
    source = wrap_f05_tracking(
        fill_u64(
            r"""
    const inserted = [_]u64{ __INSERTED__ };
    const removed = [_]u64{ __REMOVED__ };
    const borrow_vals = [_]u64{ __BORROW__ };
    var slack = try buildFrom(allocator, &inserted);
    defer slack.deinit();
    for (removed) |v| _ = slack.remove(v);
    try slack.compact();
    const slack_shape = try shapeOf(slack.toBuffer());
    var opened = klyvmap.Bitmap.fromBuffer(allocator, slack.toBuffer(), .borrow) catch return error.OpenFailed;
    const slack_card = opened.getCardinality() == slack.getCardinality();
    opened.deinit();

    var empty = try klyvmap.Bitmap.init(allocator);
    defer empty.deinit();
    try empty.compact();
    const empty_shape = try shapeOf(empty.toBuffer());
    const empty_still = empty.isEmpty() and empty.getCardinality() == 0 and empty.minimum() == null and empty.maximum() == null and !empty.contains(0);
    var empty_open = klyvmap.Bitmap.fromBuffer(allocator, empty.toBuffer(), .borrow) catch return error.EmptyOpen;
    defer empty_open.deinit();
    const empty_open_still = empty_open.isEmpty() and empty_open.getCardinality() == 0 and empty_open.minimum() == null;

    var owned_src = try buildFrom(allocator, &borrow_vals);
    try owned_src.compact();
    const caller = try owned_src.toBufferCopy(allocator);
    defer allocator.free(caller);
    owned_src.deinit();
    var borrowed = klyvmap.Bitmap.fromBuffer(allocator, caller, .borrow) catch return error.BorrowFailed;
    defer borrowed.deinit();
    try borrowed.compact();
    const borrow_shape = try shapeOf(borrowed.toBuffer());

    try emitJson(init, init.gpa,
        "{{\"s_len\":{d},\"s_b0\":{d},\"s_b1\":{d},\"s_res\":{d},\"slack_card\":{s},\"e_len\":{d},\"e_b0\":{d},\"e_b1\":{d},\"e_res\":{d},\"empty_still\":{s},\"empty_open_still\":{s},\"b_len\":{d},\"b_b0\":{d},\"b_b1\":{d},\"b_res\":{d}}}",
        .{
            slack_shape.len, slack_shape.b0, slack_shape.b1, slack_shape.res, jsonBool(slack_card),
            empty_shape.len, empty_shape.b0, empty_shape.b1, empty_shape.res,
            jsonBool(empty_still), jsonBool(empty_open_still),
            borrow_shape.len, borrow_shape.b0, borrow_shape.b1, borrow_shape.res,
        },
    );
""",
            inserted=zig_u64_list(parts["inserted"]),
            removed=zig_u64_list(parts["removed"]),
            borrow=zig_u64_list(present),
        )
    )
    report = run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
    require_emit_shape(report, length="s_len", b0="s_b0", b1="s_b1", residue="s_res")
    require_emit_shape(report, length="e_len", b0="e_b0", b1="e_b1", residue="e_res")
    require_emit_shape(report, length="b_len", b0="b_b0", b1="b_b1", residue="b_res")
    assert require_bool_field(report, "slack_card") is True
    assert require_bool_field(report, "empty_still") is True
    assert require_bool_field(report, "empty_open_still") is True


def test_open_unpublished_compacted_bitmap_matches_sequence():
    present, absent = _population_with_zero()
    ordered = sorted(present)
    source = wrap_f05_tracking(
        fill_u64(
            r"""
    const inserted = [_]u64{ __INSERTED__ };
    const ordered = [_]u64{ __ORDERED__ };
    const absent: u64 = __ABSENT__;
    var bm = try buildFrom(allocator, &inserted);
    defer bm.deinit();
    try bm.compact();
    var opened = klyvmap.Bitmap.fromBuffer(allocator, bm.toBuffer(), .borrow) catch return error.OpenFailed;
    defer opened.deinit();
    const seq = valuesMatch(&opened, &ordered);
    const card = opened.getCardinality() == ordered.len and opened.getCardinality() == bm.getCardinality();
    const still_absent = !opened.contains(absent);
    try emitJson(init, init.gpa,
        "{{\"seq\":{s},\"card\":{s},\"still_absent\":{s}}}",
        .{ jsonBool(seq), jsonBool(card), jsonBool(still_absent) },
    );
""",
            inserted=zig_u64_list(present),
            ordered=zig_u64_list(ordered),
            absent=absent,
        )
    )
    report = run_bitmap_probe(source)
    assert require_bool_field(report, "seq") is True
    assert require_bool_field(report, "card") is True
    assert require_bool_field(report, "still_absent") is True


# ---------------------------------------------------------------------------
# H. No file or network I/O on the compact path
# ---------------------------------------------------------------------------


def test_compact_path_performs_no_file_or_network_io():
    present, _absent = _population_with_zero()
    removed = present[0]
    kept = [value for value in present if value != removed]
    honest = wrap_f05_tracking(
        fill_u64(
            r"""
    const inserted = [_]u64{ __INSERTED__ };
    const removed: u64 = __REMOVED__;
    var bm = try buildFrom(allocator, &inserted);
    _ = bm.remove(removed);
    try bm.compact();
    const view = bm.toBuffer();
    if (view.len == 0) return error.ShortEmit;
    _ = view[0];
    bm.deinit();
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
""",
            inserted=zig_u64_list(shuffle_not_sorted(present)),
            removed=removed,
        )
    )
    _ = kept
    borrowed = wrap_f05_tracking(
        fill_u64(
            r"""
    const inserted = [_]u64{ __INSERTED__ };
    var bm = try buildFrom(allocator, &inserted);
    try bm.compact();
    const caller = try bm.toBufferCopy(allocator);
    bm.deinit();
    var borrowed = klyvmap.Bitmap.fromBuffer(allocator, caller, .borrow) catch return error.BorrowFailed;
    try borrowed.compact();
    const view = borrowed.toBuffer();
    if (view.len == 0) return error.ShortEmit;
    _ = view[0];
    borrowed.deinit();
    allocator.free(caller);
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
""",
            inserted=zig_u64_list(shuffle_not_sorted(present)),
        )
    )
    vandal = wrap_f05_tracking(
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
    net_vandal = wrap_f05_tracking(
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
        compile_probe_or_raise(ws, borrowed, relpath="borrowed.zig", output="borrowed")
        compile_probe_or_raise(ws, vandal_src, relpath="vandal.zig", output="vandal")
        compile_probe_or_raise(ws, net_vandal, relpath="net.zig", output="net")
        roots = (ws.path, ws.home, tmp)
        harness_names = {
            "honest.zig",
            "borrowed.zig",
            "vandal.zig",
            "net.zig",
            "honest",
            "borrowed",
            "vandal",
            "net",
        }
        before: set[Path] = set()
        for root in roots:
            before |= _walk_regular_files(root)
        run = ws.run_command([str(ws.resolve("honest"))], timeout=DEFAULT_TIMEOUT)
        if run.returncode != 0:
            raise HarnessError(f"compact I/O probe exited {run.returncode}\n{run.stderr_text}")
        created = product_created_files(
            before=before,
            roots=roots,
            ignore_names=harness_names,
        )
        assert created == set(), f"compact path wrote files: {created}"

        before_b: set[Path] = set()
        for root in roots:
            before_b |= _walk_regular_files(root)
        run_b = ws.run_command([str(ws.resolve("borrowed"))], timeout=DEFAULT_TIMEOUT)
        if run_b.returncode != 0:
            raise HarnessError(
                f"borrowed compact I/O probe exited {run_b.returncode}\n{run_b.stderr_text}"
            )
        created_b = product_created_files(
            before=before_b,
            roots=roots,
            ignore_names=harness_names,
        )
        assert created_b == set(), f"borrowed compact path wrote files: {created_b}"

        before_v: set[Path] = set()
        for root in roots:
            before_v |= _walk_regular_files(root)
        run_v = ws.run_command([str(ws.resolve("vandal"))], timeout=DEFAULT_TIMEOUT)
        if run_v.returncode != 0:
            raise HarnessError(f"file positive control exited {run_v.returncode}\n{run_v.stderr_text}")
        created_v = product_created_files(
            before=before_v,
            roots=roots,
            ignore_names=harness_names,
        )
        names = {path.name for path in created_v}
        assert "cwd_side.txt" in names, f"workspace write not observed: {created_v}"
        assert "home_side.txt" in names, f"HOME write not observed: {created_v}"
        assert "tmp_side.txt" in names, f"TMPDIR write not observed: {created_v}"

        run_w, writes, reads = run_traced_file_writes(
            ws, [str(ws.resolve("honest"))], timeout=DEFAULT_TIMEOUT
        )
        if run_w.returncode != 0:
            raise HarnessError(f"traced compact probe exited {run_w.returncode}\n{run_w.stderr_text}")
        assert file_write_syscalls_in_trace(writes) == []
        assert unexpected_file_reads_in_trace(reads) == [], (
            f"owned compact read a path it did not need: {reads}"
        )

        run_n, hits = run_traced_arch_network(
            ws, [str(ws.resolve("honest"))], timeout=DEFAULT_TIMEOUT
        )
        if run_n.returncode != 0:
            raise HarnessError(f"traced compact network probe exited {run_n.returncode}\n{run_n.stderr_text}")
        assert network_syscalls_in_trace(hits) == []

        run_bw, borrow_writes, borrow_reads = run_traced_file_writes(
            ws, [str(ws.resolve("borrowed"))], timeout=DEFAULT_TIMEOUT
        )
        if run_bw.returncode != 0:
            raise HarnessError(
                f"traced borrowed compact probe exited {run_bw.returncode}\n{run_bw.stderr_text}"
            )
        assert file_write_syscalls_in_trace(borrow_writes) == [], (
            f"borrowed compact issued file writes: {borrow_writes}"
        )
        assert unexpected_file_reads_in_trace(borrow_reads) == [], (
            f"borrowed compact read a path it did not need: {borrow_reads}"
        )

        run_bn, borrow_hits = run_traced_arch_network(
            ws, [str(ws.resolve("borrowed"))], timeout=DEFAULT_TIMEOUT
        )
        if run_bn.returncode != 0:
            raise HarnessError(
                f"traced borrowed compact network probe exited {run_bn.returncode}\n{run_bn.stderr_text}"
            )
        assert network_syscalls_in_trace(borrow_hits) == [], (
            f"borrowed compact issued network syscalls: {borrow_hits}"
        )

        run_nv, vandal_hits = run_traced_network(
            ws, [str(ws.resolve("net"))], timeout=DEFAULT_TIMEOUT
        )
        if run_nv.returncode != 0:
            raise HarnessError(
                f"network positive control exited {run_nv.returncode}\n{run_nv.stderr_text}"
            )
        assert network_syscalls_in_trace(vandal_hits), "network positive control observed nothing"


# ---------------------------------------------------------------------------
# Canonical bytes of one prefix at every population on the way to full and back
# ---------------------------------------------------------------------------


def test_one_prefix_compacts_to_the_same_bytes_by_three_routes_at_every_population():
    # Equal sets are byte-identical after compact, whatever number of values
    # share a high-48 prefix and whichever route built them: set in one order,
    # set in the opposite order with one more value set and removed, or grown
    # (and later shrunk) value by value on one long-lived bitmap that is
    # compacted at every observed population and then keeps changing.
    report = run_block_sweep(
        r"""
    const Route = struct {
        fn same(live: *klyvmap.Bitmap, b: Block, lo: u64, hi: u64, extra: ?u64, alloc: std.mem.Allocator) !bool {
            var up = try klyvmap.Bitmap.init(alloc);
            defer up.deinit();
            _ = try b.setEdges(&up);
            _ = try b.setRange(&up, lo, hi);
            try up.compact();
            var down = try klyvmap.Bitmap.init(alloc);
            defer down.deinit();
            _ = try b.setRangeDown(&down, lo, hi);
            if (extra) |e| {
                _ = try down.set(e);
                _ = down.remove(e);
            }
            _ = try b.setEdges(&down);
            try down.compact();
            try live.compact();
            var ok = std.mem.eql(u8, up.toBuffer(), down.toBuffer()) and std.mem.eql(u8, up.toBuffer(), live.toBuffer());
            ok = ok and up.getCardinality() == hi - lo + 2 and b.walk(&up, lo, hi, true) and b.walk(live, lo, hi, true);
            const len0 = up.toBuffer().len;
            try up.compact();
            ok = ok and up.toBuffer().len == len0 and std.mem.eql(u8, up.toBuffer(), down.toBuffer());
            var opened = klyvmap.Bitmap.fromBuffer(alloc, live.toBuffer(), .borrow) catch return false;
            defer opened.deinit();
            ok = ok and b.walk(&opened, lo, hi, true);
            return ok;
        }
    };
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    _ = try block.setEdges(&bm);
    var grow_ok = true;
    var grow_seen: u64 = 0;
    var n: u64 = 0;
    while (n < 65536) : (n += 1) {
        _ = try bm.set(block.val(n));
        const c = n + 1;
        if (Block.isCheckpoint(c, &checkpoints)) {
            const extra: ?u64 = if (c < 65536) block.val(c) else null;
            if (!try Route.same(&bm, block, 0, c, extra, allocator)) grow_ok = false;
            grow_seen += 1;
        }
    }
    var shrink_ok = true;
    var shrink_seen: u64 = 0;
    n = 0;
    while (n < 65536) : (n += 1) {
        _ = bm.remove(block.val(n));
        const left: u64 = 65536 - (n + 1);
        if (left == 0 or Block.isCheckpoint(left, &checkpoints)) {
            if (!try Route.same(&bm, block, n + 1, 65536, block.val(n), allocator)) shrink_ok = false;
            shrink_seen += 1;
        }
    }
    try emitJson(init, init.gpa,
        "{{\"grow_ok\":{s},\"grow_seen\":{d},\"shrink_ok\":{s},\"shrink_seen\":{d}}}",
        .{ jsonBool(grow_ok), grow_seen, jsonBool(shrink_ok), shrink_seen },
    );
"""
    )
    require_sweep_true(report, "grow_ok", "shrink_ok")
    require_sweep_seen(report, "grow_seen", len(block_checkpoints()))
    require_sweep_seen(report, "shrink_seen", len(shrink_checkpoints()))
