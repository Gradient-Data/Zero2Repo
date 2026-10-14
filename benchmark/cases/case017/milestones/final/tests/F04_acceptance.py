# feature: F04
"""FP-04: emit the buffer and open it (borrow, own, copying open).

Assertions follow Full_PRD.original.md FP-04 (L172–L201) and the
pre-FP sentences this feature's public entries can trigger (L5, L7,
L20–L23, L31, L37, L44, L55, L57).
"""

from __future__ import annotations

from F01_helpers import (
    fill_u64,
    network_syscalls_in_trace,
    require_empty_snapshot,
    run_bitmap_probe,
)
from F02_helpers import (
    LARGE_PROBE_TIMEOUT,
    require_bool_field,
    require_int_field,
    shuffle_not_sorted,
    zig_u64_list,
)
from F03_helpers import compile_probe_or_raise, require_strictly_ascending_once
from F04_helpers import (
    U64_MAX,
    fresh_high_prefix_f04,
    prefix_seed_f04,
    observe_declared_release_and_format_word,
    require_big_endian_compile_refused,
    require_calendar_release_form,
    require_emit_shape,
    require_false_fields,
    require_fresh_empty,
    require_true_fields,
    same_prefix_candidates_f04,
    unpublished_body_byte_f04,
    unpublished_count_f04,
    unpublished_odd_f04,
    unpublished_population_f04,
    unpublished_residue_f04,
    unpublished_short_even_f04,
    unpublished_u64_f04,
    unpublished_version_value_f04,
    format_version_offset,
    file_write_syscalls_in_trace,
    run_traced_arch_network,
    run_traced_file_writes,
    unexpected_file_reads_in_trace,
    wrap_f04_probe,
)
from F02_helpers import (
    block_checkpoints,
    block_sweep_zig,
    require_sweep_seen,
    require_sweep_true,
    run_block_sweep,
    shrink_checkpoints,
)
from F04_helpers import dense_and_sparse_f04
from _helpers import DEFAULT_TIMEOUT, HarnessError, workspace


def _modes_json(prefix: str) -> str:
    fields = (
        "borrow_yield",
        "own_yield",
        "copy_yield",
        "borrow_fresh",
        "own_fresh",
        "copy_fresh",
        "own_baseline",
        "borrow_caller_same",
        "borrow_held",
        "copy_source_same",
        "copy_owns",
        "copy_released",
    )
    return ",".join(f'\\"{prefix}{name}\\":{{s}}' for name in fields)


def _modes_args(prefix: str) -> str:
    names = (
        "borrow_yield",
        "own_yield",
        "copy_yield",
        "borrow_fresh",
        "own_fresh",
        "copy_fresh",
        "own_baseline",
        "borrow_caller_same",
        "borrow_held",
        "copy_source_same",
        "copy_owns",
        "copy_released",
    )
    return ", ".join(f"jsonBool({prefix}.{name})" for name in names)


def _assert_fresh_modes(report: dict, prefix: str) -> None:
    require_true_fields(
        report,
        f"{prefix}borrow_yield",
        f"{prefix}own_yield",
        f"{prefix}copy_yield",
        f"{prefix}borrow_fresh",
        f"{prefix}own_fresh",
        f"{prefix}copy_fresh",
        f"{prefix}own_baseline",
        f"{prefix}borrow_caller_same",
        f"{prefix}borrow_held",
        f"{prefix}copy_source_same",
        f"{prefix}copy_owns",
        f"{prefix}copy_released",
    )


def _assert_version_modes(report: dict, prefix: str) -> None:
    require_false_fields(
        report,
        f"{prefix}borrow_yield",
        f"{prefix}own_yield",
        f"{prefix}copy_yield",
    )
    require_true_fields(
        report,
        f"{prefix}own_baseline",
        f"{prefix}borrow_caller_same",
        f"{prefix}borrow_held",
    )


# ---------------------------------------------------------------------------
# A. Emit
# ---------------------------------------------------------------------------


def test_empty_emit_is_even_aligned_and_carries_version_one():
    voff = format_version_offset()
    source = wrap_f04_probe(
        fill_u64(
            r"""
    const voff: usize = __VOFF__;
    var bm = try klyvmap.Bitmap.init(allocator);
    const view = bm.toBuffer();
    const copy = try bm.toBufferCopy(allocator);
    const vh = try headerOf(view);
    const ch = try headerOf(copy);
    const same = std.mem.eql(u8, view, copy);
    if (view.len <= voff or copy.len <= voff) return error.ShortEmit;
    const vv = view[voff];
    const cv = copy[voff];
    bm.deinit();
    allocator.free(copy);
    try positiveControl(track, vh.len);
    try emitJson(init, init.gpa,
        "{{\"same\":{s},\"vlen\":{d},\"vver\":{d},\"vres\":{d},\"clen\":{d},\"cver\":{d},\"cres\":{d}}}",
        .{ jsonBool(same), vh.len, vv, vh.res, ch.len, cv, ch.res },
    );
""",
            voff=voff,
        )
    )
    report = run_bitmap_probe(source)
    require_true_fields(report, "same")
    require_emit_shape(report, length="vlen", residue="vres")
    require_emit_shape(report, length="clen", residue="cres")
    assert require_int_field(report, "vlen") == require_int_field(report, "clen")
    assert require_int_field(report, "vver") == 1, "view does not carry format version 1"
    assert require_int_field(report, "cver") == 1, "owning copy does not carry format version 1"


def test_open_empty_emit_three_modes_matches_in_use_bytes_and_stays_empty():
    source = wrap_f04_probe(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    const copy = try bm.toBufferCopy(allocator);
    const ch = try headerOf(copy);
    const template = try init.gpa.dupe(u8, copy);
    defer init.gpa.free(template);
    bm.deinit();
    allocator.free(copy);

    var borrowed = try openMode(track, template, false);
    if (!borrowed.yielded) return error.BorrowFailed;
    const bytes_match = std.mem.eql(u8, borrowed.bm.toBuffer(), template);
    const min_j = try optU64Json(init.gpa, borrowed.bm.minimum());
    defer init.gpa.free(min_j);
    const max_j = try optU64Json(init.gpa, borrowed.bm.maximum());
    defer init.gpa.free(max_j);
    const empty = borrowed.bm.isEmpty();
    const card = borrowed.bm.getCardinality();
    const contains0 = borrowed.bm.contains(0);
    const snap = try init.gpa.dupe(u8, borrowed.storage);
    defer init.gpa.free(snap);
    _ = try borrowed.bm.set(42);
    const has42 = borrowed.bm.contains(42) and borrowed.bm.getCardinality() == 1;
    const legal = shapeOk(borrowed.bm.toBuffer());
    const caller_same = std.mem.eql(u8, borrowed.storage, snap);
    const held = borrowed.held;
    const before = borrowed.before;
    releaseOpened(track, &borrowed);
    const still = track.live == held;
    callerFree(track, &borrowed);
    const borrow_back = still and track.live == before;

    const modes = try freshModes(track, init.gpa, template, 42, 0, false);
    try positiveControl(track, ch.len);
    try emitJson(init, init.gpa,
        "{{\"bytes_match\":{s},\"empty\":{s},\"cardinality\":{d},\"contains0\":{s},\"min\":{s},\"max\":{s},\"set_visible\":{s},\"legal_emit\":{s},\"caller_same\":{s},\"borrow_back\":{s},\"own_yield\":{s},\"own_fresh\":{s},\"own_baseline\":{s},\"copy_yield\":{s},\"copy_fresh\":{s},\"copy_owns\":{s},\"copy_source_same\":{s},\"copy_released\":{s},\"clen\":{d},\"cb0\":{d},\"cb1\":{d},\"cres\":{d}}}",
        .{
            jsonBool(bytes_match), jsonBool(empty), card, jsonBool(contains0), min_j, max_j,
            jsonBool(has42), jsonBool(legal), jsonBool(caller_same), jsonBool(borrow_back),
            jsonBool(modes.own_yield), jsonBool(modes.own_fresh), jsonBool(modes.own_baseline),
            jsonBool(modes.copy_yield), jsonBool(modes.copy_fresh), jsonBool(modes.copy_owns),
            jsonBool(modes.copy_source_same), jsonBool(modes.copy_released),
            ch.len, ch.b0, ch.b1, ch.res,
        },
    );
"""
    )
    report = run_bitmap_probe(source)
    require_true_fields(report, "bytes_match", "caller_same", "borrow_back", "set_visible")
    require_fresh_empty(report)
    require_emit_shape(report, length="clen", b0="cb0", b1="cb1", residue="cres")
    require_true_fields(
        report,
        "own_yield",
        "own_fresh",
        "own_baseline",
        "copy_yield",
        "copy_fresh",
        "copy_owns",
        "copy_source_same",
        "copy_released",
    )


def test_nonempty_view_and_copy_are_the_same_bytes_and_aligned():
    count = unpublished_count_f04()
    values = shuffle_not_sorted(unpublished_population_f04(count))
    source = wrap_f04_probe(
        fill_u64(
            r"""
    const vals = [_]u64{ __VALS__ };
    var bm = try klyvmap.Bitmap.init(allocator);
    for (vals) |v| _ = try bm.set(v);
    const view = bm.toBuffer();
    const copy = try bm.toBufferCopy(allocator);
    const vh = try headerOf(view);
    const ch = try headerOf(copy);
    const same = std.mem.eql(u8, view, copy);
    bm.deinit();
    allocator.free(copy);
    try emitJson(init, init.gpa,
        "{{\"same\":{s},\"vlen\":{d},\"vb0\":{d},\"vb1\":{d},\"vres\":{d},\"clen\":{d},\"cb0\":{d},\"cb1\":{d},\"cres\":{d}}}",
        .{ jsonBool(same), vh.len, vh.b0, vh.b1, vh.res, ch.len, ch.b0, ch.b1, ch.res },
    );
""",
            vals=zig_u64_list(values),
        )
    )
    report = run_bitmap_probe(source)
    require_true_fields(report, "same")
    require_emit_shape(report, length="vlen", b0="vb0", b1="vb1", residue="vres")
    require_emit_shape(report, length="clen", b0="cb0", b1="cb1", residue="cres")


def test_borrowed_view_of_live_bitmap_opens_without_a_prior_copy():
    values = unpublished_population_f04(unpublished_count_f04())
    absent = unpublished_u64_f04(forbidden=set(values))
    ordered = sorted(values)
    require_strictly_ascending_once(ordered, cardinality=len(ordered))
    source = wrap_f04_probe(
        fill_u64(
            r"""
    const vals = [_]u64{ __VALS__ };
    const ordered = [_]u64{ __ORDERED__ };
    const absent: u64 = __ABSENT__;
    var bm = try klyvmap.Bitmap.init(allocator);
    for (vals) |v| _ = try bm.set(v);
    const view = bm.toBuffer();
    const snap = try init.gpa.dupe(u8, view);
    defer init.gpa.free(snap);
    var opened = klyvmap.Bitmap.fromBuffer(allocator, view, .borrow) catch return error.BorrowFailed;
    const match = membersExact(&opened, &ordered, absent);
    const iter_ok = iterExact(&opened, &ordered);
    const same = std.mem.eql(u8, view, snap);
    const card = opened.getCardinality() == ordered.len;
    opened.deinit();
    bm.deinit();
    try emitJson(init, init.gpa,
        "{{\"match\":{s},\"iter_ok\":{s},\"same\":{s},\"card\":{s}}}",
        .{ jsonBool(match), jsonBool(iter_ok), jsonBool(same), jsonBool(card) },
    );
""",
            vals=zig_u64_list(shuffle_not_sorted(values)),
            ordered=zig_u64_list(ordered),
            absent=absent,
        )
    )
    report = run_bitmap_probe(source)
    require_true_fields(report, "match", "iter_ok", "same", "card")


def test_owning_copy_opens_after_source_bitmap_is_released():
    values = unpublished_population_f04(unpublished_count_f04())
    absent = unpublished_u64_f04(forbidden=set(values))
    ordered = sorted(values)
    require_strictly_ascending_once(ordered, cardinality=len(ordered))
    source = wrap_f04_probe(
        fill_u64(
            r"""
    const vals = [_]u64{ __VALS__ };
    const ordered = [_]u64{ __ORDERED__ };
    const absent: u64 = __ABSENT__;
    var bm = try klyvmap.Bitmap.init(allocator);
    for (vals) |v| _ = try bm.set(v);
    const copy = try bm.toBufferCopy(allocator);
    const hdr = try headerOf(copy);
    bm.deinit();
    var opened = klyvmap.Bitmap.fromBuffer(allocator, copy, .borrow) catch return error.BorrowFailed;
    const match = membersExact(&opened, &ordered, absent);
    const card = opened.getCardinality() == ordered.len;
    const same = std.mem.eql(u8, opened.toBuffer(), copy);
    opened.deinit();
    allocator.free(copy);
    try emitJson(init, init.gpa,
        "{{\"match\":{s},\"card\":{s},\"same\":{s},\"len\":{d},\"b0\":{d},\"b1\":{d},\"res\":{d}}}",
        .{ jsonBool(match), jsonBool(card), jsonBool(same), hdr.len, hdr.b0, hdr.b1, hdr.res },
    );
""",
            vals=zig_u64_list(shuffle_not_sorted(values)),
            ordered=zig_u64_list(ordered),
            absent=absent,
        )
    )
    report = run_bitmap_probe(source)
    require_true_fields(report, "match", "card", "same")
    require_emit_shape(report, length="len", b0="b0", b1="b1", residue="res")


def test_round_trip_42_and_value_above_2_pow_40_iterates_after_open():
    big = unpublished_u64_f04(above=1 << 40)
    ordered = sorted((42, big))
    require_strictly_ascending_once(ordered, cardinality=2)
    source = wrap_f04_probe(
        fill_u64(
            r"""
    const big: u64 = __BIG__;
    const ordered = [_]u64{ __ORDERED__ };
    var bm = try klyvmap.Bitmap.init(allocator);
    _ = try bm.set(42);
    _ = try bm.set(big);
    const copy = try bm.toBufferCopy(allocator);
    bm.deinit();
    var opened = klyvmap.Bitmap.fromBuffer(allocator, copy, .borrow) catch return error.BorrowFailed;
    const iter_ok = iterExact(&opened, &ordered);
    const card = opened.getCardinality() == 2;
    const has42 = opened.contains(42);
    const has_big = opened.contains(big);
    opened.deinit();
    allocator.free(copy);
    try emitJson(init, init.gpa,
        "{{\"iter_ok\":{s},\"card\":{s},\"has42\":{s},\"has_big\":{s}}}",
        .{ jsonBool(iter_ok), jsonBool(card), jsonBool(has42), jsonBool(has_big) },
    );
""",
            big=big,
            ordered=zig_u64_list(ordered),
        )
    )
    report = run_bitmap_probe(source)
    require_true_fields(report, "iter_ok", "card", "has42", "has_big")


# ---------------------------------------------------------------------------
# B. Borrow open
# ---------------------------------------------------------------------------


def _borrow_match_probe(values: list[int], absent: int, *, with_array: bool) -> str:
    ordered = sorted(values)
    require_strictly_ascending_once(ordered, cardinality=len(ordered))
    array_line = (
        "const array_ok = try arrayExact(&opened, allocator, &ordered);\n"
        if with_array
        else "const array_ok = true;\n"
    )
    return wrap_f04_probe(
        fill_u64(
            r"""
    const vals = [_]u64{ __VALS__ };
    const ordered = [_]u64{ __ORDERED__ };
    const absent: u64 = __ABSENT__;
    var bm = try klyvmap.Bitmap.init(allocator);
    for (vals) |v| _ = try bm.set(v);
    const view = bm.toBuffer();
    const copy = try bm.toBufferCopy(allocator);
    const same_emit = std.mem.eql(u8, view, copy);
    const hdr = try headerOf(copy);
    bm.deinit();
    var opened = klyvmap.Bitmap.fromBuffer(allocator, copy, .borrow) catch return error.BorrowFailed;
    const match = membersExact(&opened, &ordered, absent);
    const iter_ok = iterExact(&opened, &ordered);
    const extrema = extremaExact(&opened, ordered[0], ordered[ordered.len - 1]);
    const card = opened.getCardinality() == ordered.len;
    __ARRAY__
    const bytes_ok = std.mem.eql(u8, opened.toBuffer(), copy);
    opened.deinit();
    allocator.free(copy);
    try emitJson(init, init.gpa,
        "{{\"same_emit\":{s},\"match\":{s},\"iter_ok\":{s},\"extrema\":{s},\"card\":{s},\"array_ok\":{s},\"bytes_ok\":{s},\"len\":{d},\"b0\":{d},\"b1\":{d},\"res\":{d}}}",
        .{
            jsonBool(same_emit), jsonBool(match), jsonBool(iter_ok), jsonBool(extrema),
            jsonBool(card), jsonBool(array_ok), jsonBool(bytes_ok),
            hdr.len, hdr.b0, hdr.b1, hdr.res,
        },
    );
""",
            vals=zig_u64_list(shuffle_not_sorted(values)),
            ordered=zig_u64_list(ordered),
            absent=absent,
            array=array_line,
        )
    )


def test_borrow_open_3000_stride7_plus_u64_max_matches_set_and_in_use_bytes():
    values = [i * 7 for i in range(3000)]
    values.append(U64_MAX)
    absent = 1
    source = _borrow_match_probe(values, absent, with_array=True)
    report = run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
    require_true_fields(
        report, "same_emit", "match", "iter_ok", "extrema", "card", "array_ok", "bytes_ok"
    )
    require_emit_shape(report, length="len", b0="b0", b1="b1", residue="res")


def test_borrow_open_unpublished_set_matches_membership_order_and_in_use_bytes():
    values = unpublished_population_f04(unpublished_count_f04())
    if not any(value > (1 << 32) for value in values):
        raise HarnessError("unpublished population has no value above 2^32")
    absent = unpublished_u64_f04(forbidden=set(values))
    source = _borrow_match_probe(values, absent, with_array=True)
    report = run_bitmap_probe(source)
    require_true_fields(
        report, "same_emit", "match", "iter_ok", "extrema", "card", "array_ok", "bytes_ok"
    )
    require_emit_shape(report, length="len", b0="b0", b1="b1", residue="res")


def test_borrow_open_and_reads_of_100_values_allocate_nothing_buffer_sized():
    values = unpublished_population_f04(100)
    absent = unpublished_u64_f04(forbidden=set(values))
    ordered = sorted(values)
    require_strictly_ascending_once(ordered, cardinality=100)
    source = wrap_f04_probe(
        fill_u64(
            r"""
    const vals = [_]u64{ __VALS__ };
    const ordered = [_]u64{ __ORDERED__ };
    const absent: u64 = __ABSENT__;
    var bm = try klyvmap.Bitmap.init(allocator);
    for (vals) |v| _ = try bm.set(v);
    const copy = try bm.toBufferCopy(allocator);
    const snap = try init.gpa.dupe(u8, copy);
    defer init.gpa.free(snap);
    bm.deinit();
    beginWatch(track, copy.len);
    var opened = klyvmap.Bitmap.fromBuffer(allocator, copy, .borrow) catch return error.BorrowFailed;
    const match = membersExact(&opened, &ordered, absent);
    const iter_ok = iterExact(&opened, &ordered);
    const card = opened.getCardinality() == 100;
    const again = std.mem.eql(u8, opened.toBuffer(), copy);
    const caller_same = std.mem.eql(u8, copy, snap);
    const is_caller = viewIsHandedAllocation(&opened, @intFromPtr(copy.ptr), copy.len);
    const saw = track.saw_ge;
    const none = track.log_n == 0;
    try endWatch(track);
    opened.deinit();
    try positiveControl(track, copy.len);
    allocator.free(copy);
    try emitJson(init, init.gpa,
        "{{\"match\":{s},\"iter_ok\":{s},\"card\":{s},\"again\":{s},\"caller_same\":{s},\"saw\":{s},\"none\":{s},\"is_caller\":{s}}}",
        .{ jsonBool(match), jsonBool(iter_ok), jsonBool(card), jsonBool(again), jsonBool(caller_same), jsonBool(saw), jsonBool(none), jsonBool(is_caller) },
    );
""",
            vals=zig_u64_list(shuffle_not_sorted(values)),
            ordered=zig_u64_list(ordered),
            absent=absent,
        )
    )
    report = run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
    require_true_fields(report, "match", "iter_ok", "card", "again", "caller_same", "none", "is_caller")
    require_false_fields(report, "saw")


def test_borrow_open_live_view_reads_do_not_write_or_copy_the_buffer():
    values = unpublished_population_f04(unpublished_count_f04())
    absent = unpublished_u64_f04(forbidden=set(values))
    ordered = sorted(values)
    require_strictly_ascending_once(ordered, cardinality=len(ordered))
    source = wrap_f04_probe(
        fill_u64(
            r"""
    const vals = [_]u64{ __VALS__ };
    const ordered = [_]u64{ __ORDERED__ };
    const absent: u64 = __ABSENT__;
    var bm = try klyvmap.Bitmap.init(allocator);
    for (vals) |v| _ = try bm.set(v);
    const view = bm.toBuffer();
    const snap = try init.gpa.dupe(u8, view);
    defer init.gpa.free(snap);
    beginWatch(track, view.len);
    var opened = klyvmap.Bitmap.fromBuffer(allocator, view, .borrow) catch return error.BorrowFailed;
    const match = membersExact(&opened, &ordered, absent);
    const iter_ok = iterExact(&opened, &ordered);
    const same = std.mem.eql(u8, view, snap);
    const is_caller = viewIsHandedAllocation(&opened, @intFromPtr(view.ptr), view.len);
    const saw = track.saw_ge;
    const none = track.log_n == 0;
    try endWatch(track);
    opened.deinit();
    try positiveControl(track, view.len);
    bm.deinit();
    try emitJson(init, init.gpa,
        "{{\"match\":{s},\"iter_ok\":{s},\"same\":{s},\"saw\":{s},\"none\":{s},\"is_caller\":{s}}}",
        .{ jsonBool(match), jsonBool(iter_ok), jsonBool(same), jsonBool(saw), jsonBool(none), jsonBool(is_caller) },
    );
""",
            vals=zig_u64_list(shuffle_not_sorted(values)),
            ordered=zig_u64_list(ordered),
            absent=absent,
        )
    )
    report = run_bitmap_probe(source)
    require_true_fields(report, "match", "iter_ok", "same", "none", "is_caller")
    require_false_fields(report, "saw")


# ---------------------------------------------------------------------------
# C. First set on a borrow
# ---------------------------------------------------------------------------


def _seed_template_zig(values: list[int]) -> str:
    return fill_u64(
        r"""
    const originals = [_]u64{ __VALS__ };
    var built = try klyvmap.Bitmap.init(allocator);
    for (originals) |v| _ = try built.set(v);
    const template = try init.gpa.dupe(u8, built.toBuffer());
    defer init.gpa.free(template);
    built.deinit();
""",
        vals=zig_u64_list(values),
    )


def test_first_set_that_fits_is_on_the_borrowed_bitmap_but_not_in_the_caller_buffer():
    # A same-prefix value is only an input. Whether that set fits without
    # growing is the implementer's packing and is not required to exist.
    prefix, seed = prefix_seed_f04()
    witness = same_prefix_candidates_f04(prefix, seed, limit=1)[0]
    ordered = sorted(seed)
    require_strictly_ascending_once(ordered, cardinality=len(ordered))
    source = wrap_f04_probe(
        _seed_template_zig(seed)
        + fill_u64(
            r"""
    const ordered = [_]u64{ __ORDERED__ };
    const witness: u64 = __WITNESS__;
    var borrowed = try openMode(track, template, false);
    if (!borrowed.yielded) return error.BorrowFailed;
    const card0 = borrowed.bm.getCardinality();
    var opened_orig = true;
    for (ordered) |o| if (!borrowed.bm.contains(o)) { opened_orig = false; };
    if (!opened_orig) return error.SeedMismatch;
    const snap = try init.gpa.dupe(u8, borrowed.storage);
    defer init.gpa.free(snap);
    _ = try borrowed.bm.set(witness);
    const borrow_has = borrowed.bm.contains(witness);
    const borrow_card = borrowed.bm.getCardinality() == card0 + 1;
    const caller_same = std.mem.eql(u8, borrowed.storage, snap);
    const held = borrowed.held;
    const before = borrowed.before;
    releaseOpened(track, &borrowed);
    if (track.live != held) return error.BorrowFreedCaller;
    var again = klyvmap.Bitmap.fromBuffer(allocator, borrowed.storage, .borrow) catch return error.SecondOpenFailed;
    var second_orig = true;
    for (ordered) |o| if (!again.contains(o)) { second_orig = false; };
    const second_omits = !again.contains(witness);
    const second_card = again.getCardinality() == card0;
    again.deinit();
    callerFree(track, &borrowed);
    const borrow_back = track.live == before;
    try positiveControl(track, template.len);
    try emitJson(init, init.gpa,
        "{{\"borrow_has\":{s},\"borrow_card\":{s},\"caller_same\":{s},\"second_orig\":{s},\"second_omits\":{s},\"second_card\":{s},\"borrow_back\":{s}}}",
        .{
            jsonBool(borrow_has), jsonBool(borrow_card), jsonBool(caller_same),
            jsonBool(second_orig), jsonBool(second_omits), jsonBool(second_card), jsonBool(borrow_back),
        },
    );
""",
            ordered=zig_u64_list(ordered),
            witness=witness,
        )
    )
    report = run_bitmap_probe(source)
    require_true_fields(
        report,
        "borrow_has",
        "borrow_card",
        "caller_same",
        "second_orig",
        "second_omits",
        "second_card",
        "borrow_back",
    )

def test_first_set_of_new_high_prefix_is_on_the_bitmap_and_second_open_is_original():
    prefix, seed = prefix_seed_f04()
    fresh = fresh_high_prefix_f04([prefix])
    ordered = sorted(seed)
    require_strictly_ascending_once(ordered, cardinality=len(ordered))
    source = wrap_f04_probe(
        _seed_template_zig(seed)
        + fill_u64(
            r"""
    const ordered = [_]u64{ __ORDERED__ };
    const fresh: u64 = __FRESH__;
    var borrowed = try openMode(track, template, false);
    if (!borrowed.yielded) return error.BorrowFailed;
    const card0 = borrowed.bm.getCardinality();
    const snap = try init.gpa.dupe(u8, borrowed.storage);
    defer init.gpa.free(snap);
    _ = try borrowed.bm.set(fresh);
    const has = borrowed.bm.contains(fresh);
    const card_up = borrowed.bm.getCardinality() == card0 + 1;
    const caller_same = std.mem.eql(u8, borrowed.storage, snap);
    const held = borrowed.held;
    const before = borrowed.before;
    releaseOpened(track, &borrowed);
    if (track.live != held) return error.BorrowFreedCaller;
    var again = klyvmap.Bitmap.fromBuffer(allocator, borrowed.storage, .borrow) catch return error.SecondOpenFailed;
    var second_orig = true;
    for (ordered) |o| if (!again.contains(o)) { second_orig = false; };
    const second_omits = !again.contains(fresh);
    const second_card = again.getCardinality() == card0;
    again.deinit();
    callerFree(track, &borrowed);
    const back = track.live == before;
    try emitJson(init, init.gpa,
        "{{\"has\":{s},\"card_up\":{s},\"caller_same\":{s},\"second_orig\":{s},\"second_omits\":{s},\"second_card\":{s},\"back\":{s}}}",
        .{
            jsonBool(has), jsonBool(card_up), jsonBool(caller_same), jsonBool(second_orig),
            jsonBool(second_omits), jsonBool(second_card), jsonBool(back),
        },
    );
""",
            ordered=zig_u64_list(ordered),
            fresh=fresh,
        )
    )
    report = run_bitmap_probe(source)
    require_true_fields(
        report, "has", "card_up", "caller_same", "second_orig", "second_omits", "second_card", "back"
    )


def test_first_set_on_borrowed_3000_buffer_is_on_the_bitmap_and_second_open_omits_it():
    values = [i * 7 for i in range(3000)]
    values.append(U64_MAX)
    fresh = unpublished_u64_f04(forbidden=set(values))
    source = wrap_f04_probe(
        fill_u64(
            r"""
    const vals = [_]u64{ __VALS__ };
    const fresh: u64 = __FRESH__;
    var bm = try klyvmap.Bitmap.init(allocator);
    for (vals) |v| _ = try bm.set(v);
    const copy = try bm.toBufferCopy(allocator);
    bm.deinit();
    const template = try init.gpa.dupe(u8, copy);
    defer init.gpa.free(template);
    allocator.free(copy);
    var borrowed = try openMode(track, template, false);
    if (!borrowed.yielded) return error.BorrowFailed;
    const card0 = borrowed.bm.getCardinality();
    const has0 = borrowed.bm.contains(0);
    const has_max = borrowed.bm.contains(std.math.maxInt(u64));
    const snap = try init.gpa.dupe(u8, borrowed.storage);
    defer init.gpa.free(snap);
    _ = try borrowed.bm.set(fresh);
    const has = borrowed.bm.contains(fresh);
    const card_up = borrowed.bm.getCardinality() == card0 + 1;
    const caller_same = std.mem.eql(u8, borrowed.storage, snap);
    const held = borrowed.held;
    const before = borrowed.before;
    releaseOpened(track, &borrowed);
    if (track.live != held) return error.BorrowFreedCaller;
    var again = klyvmap.Bitmap.fromBuffer(allocator, borrowed.storage, .borrow) catch return error.SecondOpenFailed;
    const second_has0 = again.contains(0);
    const second_max = again.contains(std.math.maxInt(u64));
    const second_omits = !again.contains(fresh);
    const second_card = again.getCardinality() == card0;
    again.deinit();
    callerFree(track, &borrowed);
    const back = track.live == before;
    try emitJson(init, init.gpa,
        "{{\"has0\":{s},\"has_max\":{s},\"has\":{s},\"card_up\":{s},\"caller_same\":{s},\"second_has0\":{s},\"second_max\":{s},\"second_omits\":{s},\"second_card\":{s},\"back\":{s}}}",
        .{
            jsonBool(has0), jsonBool(has_max), jsonBool(has), jsonBool(card_up), jsonBool(caller_same),
            jsonBool(second_has0), jsonBool(second_max), jsonBool(second_omits), jsonBool(second_card), jsonBool(back),
        },
    );
""",
            vals=zig_u64_list(shuffle_not_sorted(values)),
            fresh=fresh,
        )
    )
    report = run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
    require_true_fields(
        report,
        "has0",
        "has_max",
        "has",
        "card_up",
        "caller_same",
        "second_has0",
        "second_max",
        "second_omits",
        "second_card",
        "back",
    )


# ---------------------------------------------------------------------------
# D. Own
# ---------------------------------------------------------------------------


def test_own_open_emits_handed_allocation_then_same_prefix_set_is_present_and_release_frees():
    # Before any set, the emitted view is the allocation the caller handed
    # over. A later set must make the new value present and raise cardinality
    # by one, and keep every original value. Whether that value fits in the
    # original allocation is the implementer's choice, so the handed bytes are
    # not compared and that pointer is not reopened. Release returns the allocator to the pre-open baseline.
    prefix, seed = prefix_seed_f04()
    extra = same_prefix_candidates_f04(prefix, seed, limit=1)[0]
    ordered = sorted(seed)
    source = wrap_f04_probe(
        _seed_template_zig(seed)
        + fill_u64(
            r"""
    const ordered = [_]u64{ __ORDERED__ };
    const extra: u64 = __EXTRA__;
    var owned = try openMode(track, template, true);
    if (!owned.yielded) return error.OwnOpenFailed;
    const view_is_alloc = viewIsHandedAllocation(&owned.bm, owned.ptr, template.len);
    const card0 = owned.bm.getCardinality();
    var originals_ok = true;
    for (ordered) |o| if (!owned.bm.contains(o)) { originals_ok = false; };
    const absent = !owned.bm.contains(extra);
    _ = try owned.bm.set(extra);
    const has = owned.bm.contains(extra);
    var still = true;
    for (ordered) |o| if (!owned.bm.contains(o)) { still = false; };
    const up = owned.bm.getCardinality() == card0 + 1;
    const before = owned.before;
    releaseOpened(track, &owned);
    const baseline = track.live == before;
    try positiveControl(track, template.len);
    try emitJson(init, init.gpa,
        "{{\"view_is_alloc\":{s},\"originals_ok\":{s},\"absent\":{s},\"has\":{s},\"still\":{s},\"up\":{s},\"baseline\":{s}}}",
        .{
            jsonBool(view_is_alloc), jsonBool(originals_ok), jsonBool(absent),
            jsonBool(has), jsonBool(still), jsonBool(up), jsonBool(baseline),
        },
    );
""",
            ordered=zig_u64_list(ordered),
            extra=extra,
        )
    )
    report = run_bitmap_probe(source)
    require_true_fields(
        report,
        "view_is_alloc",
        "originals_ok",
        "absent",
        "has",
        "still",
        "up",
        "baseline",
    )


def test_own_open_set_7_increases_cardinality_and_release_frees():
    values = unpublished_population_f04(3)
    if 7 in values:
        raise HarnessError("unpublished seed contains 7")
    source = wrap_f04_probe(
        _seed_template_zig(values)
        + r"""
    var owned = try openMode(track, template, true);
    if (!owned.yielded) return error.OwnOpenFailed;
    const card0 = owned.bm.getCardinality();
    const absent = !owned.bm.contains(7);
    _ = try owned.bm.set(7);
    const has = owned.bm.contains(7);
    const up = owned.bm.getCardinality() == card0 + 1;
    const before = owned.before;
    releaseOpened(track, &owned);
    const baseline = track.live == before;
    try positiveControl(track, template.len);
    try emitJson(init, init.gpa,
        "{{\"absent\":{s},\"has\":{s},\"up\":{s},\"baseline\":{s}}}",
        .{ jsonBool(absent), jsonBool(has), jsonBool(up), jsonBool(baseline) },
    );
"""
    )
    report = run_bitmap_probe(source)
    require_true_fields(report, "absent", "has", "up", "baseline")


def _emit_template_zig(values: list[int]) -> str:
    return _seed_template_zig(values)


def test_own_open_every_version_mismatch_frees_without_caller_free_and_yields_no_bitmap():
    values = unpublished_population_f04(unpublished_count_f04())
    voff = format_version_offset()
    other = unpublished_version_value_f04()
    source = wrap_f04_probe(
        _emit_template_zig(values)
        + fill_u64(
            r"""
    const voff: usize = __VOFF__;
    const patches = [_]u8{ 2, 0, 3, 255, __OTHER__ };
    var raw: [1024]u8 = undefined;
    var i: usize = 0;
    try app(&raw, &i, "{");
    for (patches, 0..) |value, n| {
        var patched = try init.gpa.dupe(u8, template);
        defer init.gpa.free(patched);
        if (patched.len <= voff) return error.ShortHeader;
        patched[voff] = value;
        const modes = try versionModes(track, patched);
        if (n != 0) try app(&raw, &i, ",");
        try appFmt(&raw, &i, init.gpa,
            "\"p{d}_borrow_yield\":{s},\"p{d}_own_yield\":{s},\"p{d}_copy_yield\":{s},\"p{d}_own_baseline\":{s},\"p{d}_borrow_caller_same\":{s},\"p{d}_borrow_held\":{s}",
            .{
                n, jsonBool(modes.borrow_yield), n, jsonBool(modes.own_yield), n, jsonBool(modes.copy_yield),
                n, jsonBool(modes.own_baseline), n, jsonBool(modes.borrow_caller_same), n, jsonBool(modes.borrow_held),
            },
        );
    }
    try app(&raw, &i, "}");
    try writeStdout(init, raw[0..i]);
""",
            voff=voff,
            other=other,
        )
    )
    report = run_bitmap_probe(source)
    for n in range(5):
        _assert_version_modes(report, f"p{n}_")


def test_own_open_too_small_or_odd_yields_empty_and_frees_without_caller_free():
    values = unpublished_population_f04(unpublished_count_f04())
    newv = unpublished_u64_f04(forbidden=set(values))
    banned = values[0]
    source = wrap_f04_probe(
        _emit_template_zig(values)
        + fill_u64(
            r"""
    const newv: u64 = __NEWV__;
    const banned: u64 = __BANNED__;
    const lens = [_]usize{ 2, 6, 65, 4, template.len - 1, template.len + 1 };
    var raw: [2048]u8 = undefined;
    var i: usize = 0;
    try app(&raw, &i, "{");
    for (lens, 0..) |nlen, n| {
        const buf = try init.gpa.alloc(u8, nlen);
        defer init.gpa.free(buf);
        copyPrefix(buf, template);
        if (nlen > template.len) buf[template.len] = 0x5a;
        const modes = try freshModes(track, init.gpa, buf, newv, banned, true);
        if (n != 0) try app(&raw, &i, ",");
        try appFmt(&raw, &i, init.gpa,
            "\"a{d}_own_yield\":{s},\"a{d}_own_fresh\":{s},\"a{d}_own_baseline\":{s}",
            .{ n, jsonBool(modes.own_yield), n, jsonBool(modes.own_fresh), n, jsonBool(modes.own_baseline) },
        );
    }
    try app(&raw, &i, "}");
    try positiveControl(track, 64);
    try writeStdout(init, raw[0..i]);
""",
            newv=newv,
            banned=banned,
        )
    )
    report = run_bitmap_probe(source)
    for n in range(6):
        require_true_fields(report, f"a{n}_own_yield", f"a{n}_own_fresh", f"a{n}_own_baseline")


def test_borrow_open_does_not_free_caller_buffer_on_version_mismatch_or_too_small():
    values = unpublished_population_f04(unpublished_count_f04())
    newv = unpublished_u64_f04(forbidden=set(values))
    voff = format_version_offset()
    source = wrap_f04_probe(
        _emit_template_zig(values)
        + fill_u64(
            r"""
    const newv: u64 = __NEWV__;
    const voff: usize = __VOFF__;
    var bad = try init.gpa.dupe(u8, template);
    defer init.gpa.free(bad);
    if (bad.len <= voff) return error.ShortHeader;
    bad[voff] = 2;
    const versioned = try versionModes(track, bad);
    const short_buf = try init.gpa.alloc(u8, 4);
    defer init.gpa.free(short_buf);
    copyPrefix(short_buf, template);
    const shortened = try freshModes(track, init.gpa, short_buf, newv, 0, false);
    try emitJson(init, init.gpa,
        "{{\"v_borrow_yield\":{s},\"v_borrow_caller_same\":{s},\"v_borrow_held\":{s},\"s_borrow_yield\":{s},\"s_borrow_fresh\":{s},\"s_borrow_caller_same\":{s},\"s_borrow_held\":{s}}}",
        .{
            jsonBool(versioned.borrow_yield), jsonBool(versioned.borrow_caller_same), jsonBool(versioned.borrow_held),
            jsonBool(shortened.borrow_yield), jsonBool(shortened.borrow_fresh),
            jsonBool(shortened.borrow_caller_same), jsonBool(shortened.borrow_held),
        },
    );
""",
            newv=newv,
            voff=voff,
        )
    )
    report = run_bitmap_probe(source)
    require_false_fields(report, "v_borrow_yield")
    require_true_fields(
        report,
        "v_borrow_caller_same",
        "v_borrow_held",
        "s_borrow_yield",
        "s_borrow_fresh",
        "s_borrow_caller_same",
        "s_borrow_held",
    )


# ---------------------------------------------------------------------------
# E. Too small / odd versus version
# ---------------------------------------------------------------------------


def _fresh_lengths_probe(lengths: list[int], values: list[int] | None, newv: int, banned: int, have_banned: bool) -> str:
    length_body = ", ".join(str(n) for n in lengths)
    template_setup = _emit_template_zig(values) if values is not None else "const template: []const u8 = &.{};\n"
    return wrap_f04_probe(
        template_setup
        + fill_u64(
            r"""
    const newv: u64 = __NEWV__;
    const banned: u64 = __BANNED__;
    const lens = [_]usize{ __LENS__ };
    var raw: [4096]u8 = undefined;
    var i: usize = 0;
    try app(&raw, &i, "{");
    for (lens, 0..) |nlen, n| {
        const buf = try init.gpa.alloc(u8, nlen);
        defer init.gpa.free(buf);
        copyPrefix(buf, template);
        const modes = try freshModes(track, init.gpa, buf, newv, banned, __BANNED_FLAG__);
        if (n != 0) try app(&raw, &i, ",");
        try appFmt(&raw, &i, init.gpa,
            "\"a{d}_borrow_yield\":{s},\"a{d}_own_yield\":{s},\"a{d}_copy_yield\":{s},\"a{d}_borrow_fresh\":{s},\"a{d}_own_fresh\":{s},\"a{d}_copy_fresh\":{s},\"a{d}_own_baseline\":{s},\"a{d}_borrow_caller_same\":{s},\"a{d}_borrow_held\":{s},\"a{d}_copy_source_same\":{s},\"a{d}_copy_owns\":{s},\"a{d}_copy_released\":{s}",
            .{
                n, jsonBool(modes.borrow_yield), n, jsonBool(modes.own_yield), n, jsonBool(modes.copy_yield),
                n, jsonBool(modes.borrow_fresh), n, jsonBool(modes.own_fresh), n, jsonBool(modes.copy_fresh),
                n, jsonBool(modes.own_baseline), n, jsonBool(modes.borrow_caller_same), n, jsonBool(modes.borrow_held),
                n, jsonBool(modes.copy_source_same), n, jsonBool(modes.copy_owns), n, jsonBool(modes.copy_released),
            },
        );
    }
    try app(&raw, &i, "}");
    try writeStdout(init, raw[0..i]);
""",
            newv=newv,
            banned=banned,
            lens=length_body,
            banned_flag="true" if have_banned else "false",
        )
    )


def test_short_or_odd_buffers_open_as_fresh_empty_in_borrow_own_and_copy():
    newv = unpublished_u64_f04()
    source = wrap_f04_probe(
        fill_u64(
            r"""
    const newv: u64 = __NEWV__;
    var fresh_src = try klyvmap.Bitmap.init(allocator);
    const template = try init.gpa.dupe(u8, fresh_src.toBuffer());
    defer init.gpa.free(template);
    fresh_src.deinit();
    const lens = [_]usize{ 0, 2, 6, 65 };
    var raw: [4096]u8 = undefined;
    var i: usize = 0;
    try app(&raw, &i, "{");
    for (lens, 0..) |nlen, n| {
        const buf = try init.gpa.alloc(u8, nlen);
        defer init.gpa.free(buf);
        copyPrefix(buf, template);
        const modes = try freshModes(track, init.gpa, buf, newv, 0, false);
        if (n != 0) try app(&raw, &i, ",");
        try appFmt(&raw, &i, init.gpa,
            "\"a{d}_borrow_yield\":{s},\"a{d}_own_yield\":{s},\"a{d}_copy_yield\":{s},\"a{d}_borrow_fresh\":{s},\"a{d}_own_fresh\":{s},\"a{d}_copy_fresh\":{s},\"a{d}_own_baseline\":{s},\"a{d}_borrow_caller_same\":{s},\"a{d}_borrow_held\":{s},\"a{d}_copy_source_same\":{s},\"a{d}_copy_owns\":{s},\"a{d}_copy_released\":{s}",
            .{
                n, jsonBool(modes.borrow_yield), n, jsonBool(modes.own_yield), n, jsonBool(modes.copy_yield),
                n, jsonBool(modes.borrow_fresh), n, jsonBool(modes.own_fresh), n, jsonBool(modes.copy_fresh),
                n, jsonBool(modes.own_baseline), n, jsonBool(modes.borrow_caller_same), n, jsonBool(modes.borrow_held),
                n, jsonBool(modes.copy_source_same), n, jsonBool(modes.copy_owns), n, jsonBool(modes.copy_released),
            },
        );
    }
    var zero = try openMode(track, "", false);
    if (!zero.yielded) return error.ZeroBorrowFailed;
    const min_j = try optU64Json(init.gpa, zero.bm.minimum());
    defer init.gpa.free(min_j);
    const max_j = try optU64Json(init.gpa, zero.bm.maximum());
    defer init.gpa.free(max_j);
    try app(&raw, &i, ",");
    try appFmt(&raw, &i, init.gpa,
        "\"empty\":{s},\"cardinality\":{d},\"contains0\":{s},\"min\":{s},\"max\":{s}",
        .{ jsonBool(zero.bm.isEmpty()), zero.bm.getCardinality(), jsonBool(zero.bm.contains(0)), min_j, max_j },
    );
    releaseOpened(track, &zero);
    if (zero.have_storage) callerFree(track, &zero);
    try app(&raw, &i, "}");
    try writeStdout(init, raw[0..i]);
""",
            newv=newv,
        )
    )
    report = run_bitmap_probe(source)
    for n in range(4):
        _assert_fresh_modes(report, f"a{n}_")
    require_empty_snapshot(report)


def test_prefix_of_real_emit_and_emit_plus_one_byte_open_as_empty():
    values = unpublished_population_f04(unpublished_count_f04())
    newv = unpublished_u64_f04(forbidden=set(values))
    # Tiny even prefixes (below the PRD's 8-byte floor), an odd-length
    # truncation, and the whole emit plus one byte.
    source = wrap_f04_probe(
        _emit_template_zig(values)
        + fill_u64(
            r"""
    const newv: u64 = __NEWV__;
    const banned: u64 = __BANNED__;
    const specs = [_]usize{ 2, 6, template.len - 1, template.len + 1 };
    var raw: [2048]u8 = undefined;
    var i: usize = 0;
    try app(&raw, &i, "{");
    for (specs, 0..) |nlen, n| {
        const buf = try init.gpa.alloc(u8, nlen);
        defer init.gpa.free(buf);
        copyPrefix(buf, template);
        if (nlen > template.len) buf[template.len] = 0x5a;
        const modes = try freshModes(track, init.gpa, buf, newv, banned, true);
        if (n != 0) try app(&raw, &i, ",");
        try appFmt(&raw, &i, init.gpa,
            "\"a{d}_borrow_yield\":{s},\"a{d}_own_yield\":{s},\"a{d}_copy_yield\":{s},\"a{d}_borrow_fresh\":{s},\"a{d}_own_fresh\":{s},\"a{d}_copy_fresh\":{s},\"a{d}_own_baseline\":{s},\"a{d}_borrow_caller_same\":{s},\"a{d}_borrow_held\":{s},\"a{d}_copy_source_same\":{s},\"a{d}_copy_owns\":{s},\"a{d}_copy_released\":{s}",
            .{
                n, jsonBool(modes.borrow_yield), n, jsonBool(modes.own_yield), n, jsonBool(modes.copy_yield),
                n, jsonBool(modes.borrow_fresh), n, jsonBool(modes.own_fresh), n, jsonBool(modes.copy_fresh),
                n, jsonBool(modes.own_baseline), n, jsonBool(modes.borrow_caller_same), n, jsonBool(modes.borrow_held),
                n, jsonBool(modes.copy_source_same), n, jsonBool(modes.copy_owns), n, jsonBool(modes.copy_released),
            },
        );
    }
    try app(&raw, &i, "}");
    try writeStdout(init, raw[0..i]);
""",
            newv=newv,
            banned=values[0],
        )
    )
    report = run_bitmap_probe(source)
    for n in range(4):
        _assert_fresh_modes(report, f"a{n}_")


def test_short_or_odd_buffers_holding_no_version_one_still_open_as_empty():
    newv = unpublished_u64_f04()
    source = wrap_f04_probe(
        fill_u64(
            r"""
    const newv: u64 = __NEWV__;
    const lens = [_]usize{ 2, 6, 65 };
    var raw: [4096]u8 = undefined;
    var i: usize = 0;
    try app(&raw, &i, "{");
    for (lens, 0..) |nlen, n| {
        const buf = try init.gpa.alloc(u8, nlen);
        defer init.gpa.free(buf);
        @memset(buf, 2);
        const modes = try freshModes(track, init.gpa, buf, newv, 0, false);
        if (n != 0) try app(&raw, &i, ",");
        try appFmt(&raw, &i, init.gpa,
            "\"a{d}_borrow_yield\":{s},\"a{d}_own_yield\":{s},\"a{d}_copy_yield\":{s},\"a{d}_borrow_fresh\":{s},\"a{d}_own_fresh\":{s},\"a{d}_copy_fresh\":{s},\"a{d}_own_baseline\":{s},\"a{d}_borrow_caller_same\":{s},\"a{d}_borrow_held\":{s},\"a{d}_copy_source_same\":{s},\"a{d}_copy_owns\":{s},\"a{d}_copy_released\":{s}",
            .{
                n, jsonBool(modes.borrow_yield), n, jsonBool(modes.own_yield), n, jsonBool(modes.copy_yield),
                n, jsonBool(modes.borrow_fresh), n, jsonBool(modes.own_fresh), n, jsonBool(modes.copy_fresh),
                n, jsonBool(modes.own_baseline), n, jsonBool(modes.borrow_caller_same), n, jsonBool(modes.borrow_held),
                n, jsonBool(modes.copy_source_same), n, jsonBool(modes.copy_owns), n, jsonBool(modes.copy_released),
            },
        );
    }
    try app(&raw, &i, "}");
    try writeStdout(init, raw[0..i]);
""",
            newv=newv,
        )
    )
    report = run_bitmap_probe(source)
    for n in range(3):
        _assert_fresh_modes(report, f"a{n}_")


def test_unpublished_short_even_and_odd_lengths_open_as_empty_not_version_failure():
    even = unpublished_short_even_f04()
    odd = unpublished_odd_f04(65)
    newv = unpublished_u64_f04()
    source = wrap_f04_probe(
        fill_u64(
            r"""
    const newv: u64 = __NEWV__;
    var fresh_src = try klyvmap.Bitmap.init(allocator);
    const template = try init.gpa.dupe(u8, fresh_src.toBuffer());
    defer init.gpa.free(template);
    fresh_src.deinit();
    const lens = [_]usize{ __EVEN__, __ODD__ };
    var raw: [2048]u8 = undefined;
    var i: usize = 0;
    try app(&raw, &i, "{");
    for (lens, 0..) |nlen, n| {
        const buf = try init.gpa.alloc(u8, nlen);
        defer init.gpa.free(buf);
        copyPrefix(buf, template);
        const modes = try freshModes(track, init.gpa, buf, newv, 0, false);
        if (n != 0) try app(&raw, &i, ",");
        try appFmt(&raw, &i, init.gpa,
            "\"a{d}_borrow_yield\":{s},\"a{d}_own_yield\":{s},\"a{d}_copy_yield\":{s},\"a{d}_borrow_fresh\":{s},\"a{d}_own_fresh\":{s},\"a{d}_copy_fresh\":{s},\"a{d}_own_baseline\":{s},\"a{d}_borrow_caller_same\":{s},\"a{d}_borrow_held\":{s},\"a{d}_copy_source_same\":{s},\"a{d}_copy_owns\":{s},\"a{d}_copy_released\":{s}",
            .{
                n, jsonBool(modes.borrow_yield), n, jsonBool(modes.own_yield), n, jsonBool(modes.copy_yield),
                n, jsonBool(modes.borrow_fresh), n, jsonBool(modes.own_fresh), n, jsonBool(modes.copy_fresh),
                n, jsonBool(modes.own_baseline), n, jsonBool(modes.borrow_caller_same), n, jsonBool(modes.borrow_held),
                n, jsonBool(modes.copy_source_same), n, jsonBool(modes.copy_owns), n, jsonBool(modes.copy_released),
            },
        );
    }
    try app(&raw, &i, "}");
    try writeStdout(init, raw[0..i]);
""",
            newv=newv,
            even=even,
            odd=odd,
        )
    )
    report = run_bitmap_probe(source)
    for n in range(2):
        _assert_fresh_modes(report, f"a{n}_")


def _version_patch_probe(patches: list[int], values: list[int], voff: int, *, compact: bool = False) -> str:
    """Open the emit of *values* with its format-version byte set to each patch.

    *voff* is the version position derived from the product's own emits
    (:func:`format_version_offset`); the field's width and place are the
    implementer's choice, so only that byte is changed.
    """
    literals = ", ".join(str(int(v)) for v in patches)
    if compact:
        body = fill_u64(
            r"""
    const originals = [_]u64{ __VALS__ };
    var built = try klyvmap.Bitmap.init(allocator);
    for (originals) |v| _ = try built.set(v);
    try built.compact();
    const template = try init.gpa.dupe(u8, built.toBuffer());
    defer init.gpa.free(template);
    built.deinit();
""",
            vals=zig_u64_list(values),
        )
    else:
        body = _emit_template_zig(values)
    return wrap_f04_probe(
        body
        + f"""
    const patches = [_]u8{{ {literals} }};
    const voff: usize = {voff};
    const ordered_one: u64 = {values[0]};
    if (template.len <= voff) return error.ShortHeader;
    var control = try openMode(track, template, false);
    if (!control.yielded) return error.ControlFailed;
    const control_has = control.bm.contains(ordered_one) and control.bm.getCardinality() == {len(values)};
    releaseOpened(track, &control);
    callerFree(track, &control);
    var raw: [2048]u8 = undefined;
    var i: usize = 0;
    try app(&raw, &i, "{{");
    try appFmt(&raw, &i, init.gpa, "\\"control_has\\":{{s}}", .{{jsonBool(control_has)}});
    for (patches, 0..) |value, n| {{
        var patched = try init.gpa.dupe(u8, template);
        defer init.gpa.free(patched);
        patched[voff] = value;
        const modes = try versionModes(track, patched);
        try app(&raw, &i, ",");
        try appFmt(&raw, &i, init.gpa,
            "\\"p{{d}}_borrow_yield\\":{{s}},\\"p{{d}}_own_yield\\":{{s}},\\"p{{d}}_copy_yield\\":{{s}},\\"p{{d}}_own_baseline\\":{{s}},\\"p{{d}}_borrow_caller_same\\":{{s}},\\"p{{d}}_borrow_held\\":{{s}}",
            .{{
                n, jsonBool(modes.borrow_yield), n, jsonBool(modes.own_yield), n, jsonBool(modes.copy_yield),
                n, jsonBool(modes.own_baseline), n, jsonBool(modes.borrow_caller_same), n, jsonBool(modes.borrow_held),
            }},
        );
    }}
    try app(&raw, &i, "}}");
    try writeStdout(init, raw[0..i]);
"""
    )


def test_version_field_holding_2_or_0_is_version_failure_on_all_three_opens():
    values = unpublished_population_f04(unpublished_count_f04())
    source = _version_patch_probe([2, 0], values, format_version_offset())
    report = run_bitmap_probe(source)
    require_true_fields(report, "control_has")
    for n in range(2):
        _assert_version_modes(report, f"p{n}_")


def test_version_mismatch_on_a_large_compacted_buffer_is_the_same_failure():
    values = unpublished_population_f04(unpublished_count_f04())
    seen = set(values)
    while len(values) < 600:
        value = unpublished_u64_f04(forbidden=seen)
        seen.add(value)
        values.append(value)
    source = _version_patch_probe([3, 255], values, format_version_offset(), compact=True)
    report = run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
    require_true_fields(report, "control_has")
    for n in range(2):
        _assert_version_modes(report, f"p{n}_")


def test_restoring_version_one_opens_the_original_set_again():
    # The refusal comes from the version field itself: the same buffer with
    # the field put back to 1 opens with the original set and bytes.
    values = unpublished_population_f04(unpublished_count_f04())
    voff = format_version_offset()
    source = wrap_f04_probe(
        _emit_template_zig(values)
        + fill_u64(
            r"""
    const ordered = [_]u64{ __ORDERED__ };
    const voff: usize = __VOFF__;
    if (template.len <= voff) return error.ShortHeader;
    var patched = try init.gpa.dupe(u8, template);
    defer init.gpa.free(patched);
    patched[voff] = 2;
    const refused = try versionModes(track, patched);
    patched[voff] = 1;
    const restored_same = std.mem.eql(u8, patched, template);
    var again = try openMode(track, patched, false);
    if (!again.yielded) return error.RestoredOpenFailed;
    var all = again.bm.getCardinality() == ordered.len;
    for (ordered) |v| {
        if (!again.bm.contains(v)) all = false;
    }
    const bytes_same = std.mem.eql(u8, again.bm.toBuffer(), template);
    releaseOpened(track, &again);
    callerFree(track, &again);
    try emitJson(init, init.gpa,
        "{{\"borrow_yield\":{s},\"own_yield\":{s},\"copy_yield\":{s},\"own_baseline\":{s},\"borrow_caller_same\":{s},\"borrow_held\":{s},\"restored_same\":{s},\"all\":{s},\"bytes_same\":{s}}}",
        .{
            jsonBool(refused.borrow_yield), jsonBool(refused.own_yield), jsonBool(refused.copy_yield),
            jsonBool(refused.own_baseline), jsonBool(refused.borrow_caller_same), jsonBool(refused.borrow_held),
            jsonBool(restored_same), jsonBool(all), jsonBool(bytes_same),
        },
    );
""",
            ordered=zig_u64_list(sorted(values)),
            voff=voff,
        )
    )
    report = run_bitmap_probe(source)
    _assert_version_modes(report, "")
    require_true_fields(report, "restored_same", "all", "bytes_same")


def test_unpublished_version_value_is_version_failure_on_all_three_opens():
    values = unpublished_population_f04(unpublished_count_f04())
    source = _version_patch_probe([unpublished_version_value_f04()], values, format_version_offset())
    report = run_bitmap_probe(source)
    require_true_fields(report, "control_has")
    _assert_version_modes(report, "p0_")


def test_non_emit_even_buffer_bad_version_refused_on_all_three_opens():
    # A buffer filled here, as long as an empty bitmap's emit (so not too
    # short), not copied from an emit and then patched. Its version field
    # holds 2. Same refusal as a patched emit: no bitmap on borrow, own, or
    # the copying open; own back to the pre-open total; borrow neither
    # writes nor frees the caller's buffer.
    filler = unpublished_body_byte_f04()
    voff = format_version_offset()
    source = wrap_f04_probe(
        fill_u64(
            r"""
    const filler: u8 = __FILLER__;
    const voff: usize = __VOFF__;
    var fresh_src = try klyvmap.Bitmap.init(allocator);
    const emit_len = fresh_src.toBuffer().len;
    fresh_src.deinit();
    if (emit_len <= voff) return error.ShortHeader;
    const buf = try init.gpa.alloc(u8, emit_len);
    defer init.gpa.free(buf);
    @memset(buf, filler);
    buf[voff] = 2;
    const modes = try versionModes(track, buf);
    const shaped = buf.len > 0 and buf.len % 2 == 0;
    const not_version = buf[voff] != 1;
    var body = true;
    for (buf, 0..) |b, k| {
        if (k != voff and b != filler) body = false;
    }
    try emitJson(init, init.gpa,
        "{{\"shaped\":{s},\"not_version\":{s},\"body\":{s},\"borrow_yield\":{s},\"own_yield\":{s},\"copy_yield\":{s},\"own_baseline\":{s},\"borrow_caller_same\":{s},\"borrow_held\":{s}}}",
        .{
            jsonBool(shaped), jsonBool(not_version), jsonBool(body),
            jsonBool(modes.borrow_yield), jsonBool(modes.own_yield), jsonBool(modes.copy_yield),
            jsonBool(modes.own_baseline), jsonBool(modes.borrow_caller_same), jsonBool(modes.borrow_held),
        },
    );
""",
            filler=filler,
            voff=voff,
        )
    )
    report = run_bitmap_probe(source)
    require_true_fields(report, "shaped", "not_version", "body")
    _assert_version_modes(report, "")


def test_library_release_version_is_calendar_form():
    """The package's declared release is 0.YYMM.patch; an emit's format word is 1."""
    version, format_word = observe_declared_release_and_format_word()
    require_calendar_release_form(version)
    assert format_word == 1
    assert version != str(format_word)


def test_big_endian_target_refuses_this_library_at_compile_time():
    source = wrap_f04_probe(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    const view = bm.toBuffer();
    const copy = try bm.toBufferCopy(allocator);
    var opened = klyvmap.Bitmap.fromBuffer(allocator, copy, .borrow) catch return error.BorrowFailed;
    const same = std.mem.eql(u8, opened.toBuffer(), view);
    opened.deinit();
    allocator.free(copy);
    bm.deinit();
    try emitJson(init, init.gpa, "{{\"same\":{s}}}", .{jsonBool(same)});
"""
    )
    with workspace() as ws:
        require_big_endian_compile_refused(ws, source)


# ---------------------------------------------------------------------------
# F. Copying open
# ---------------------------------------------------------------------------


def _copy_probe(offset: int, values: list[int], newv: int) -> str:
    ordered = sorted(values)
    absent = unpublished_u64_f04(forbidden=set(values) | {newv})
    require_strictly_ascending_once(ordered, cardinality=len(ordered))
    return wrap_f04_probe(
        fill_u64(
            r"""
    const vals = [_]u64{ __VALS__ };
    const ordered = [_]u64{ __ORDERED__ };
    const absent: u64 = __ABSENT__;
    const newv: u64 = __NEWV__;
    const offset: usize = __OFFSET__;
    var bm = try klyvmap.Bitmap.init(allocator);
    for (vals) |v| _ = try bm.set(v);
    const copy = try bm.toBufferCopy(allocator);
    bm.deinit();
    const host = try allocator.alignedAlloc(u8, .@"8", copy.len + offset + 8);
    @memset(host, 0x3c);
    @memcpy(host[offset..][0..copy.len], copy);
    const slice = host[offset..][0..copy.len];
    const before = track.live;
    var opened = klyvmap.Bitmap.fromBufferCopy(allocator, slice) catch return error.CopyFailed;
    const view = opened.toBuffer();
    const bytes_ok = std.mem.eql(u8, view, copy);
    const match = membersExact(&opened, &ordered, absent);
    const extrema = extremaExact(&opened, ordered[0], ordered[ordered.len - 1]);
    const card = opened.getCardinality() == ordered.len;
    const owns = track.live >= before + view.len;
    const result_snap = try init.gpa.dupe(u8, view);
    defer init.gpa.free(result_snap);
    const source_snap = try init.gpa.dupe(u8, slice);
    defer init.gpa.free(source_snap);
    @memset(slice, 0xa1);
    const after_scribble_bytes = std.mem.eql(u8, opened.toBuffer(), result_snap);
    const after_scribble_match = membersExact(&opened, &ordered, absent);
    const after_scribble_card = opened.getCardinality() == ordered.len;
    @memcpy(slice, source_snap);
    _ = try opened.set(newv);
    const has_new = opened.contains(newv);
    const source_spared = std.mem.eql(u8, slice, source_snap);
    var source_again = klyvmap.Bitmap.fromBufferCopy(init.gpa, slice) catch return error.SourceReopenFailed;
    const source_orig = membersExact(&source_again, &ordered, absent) and !source_again.contains(newv);
    source_again.deinit();
    opened.deinit();
    const released = track.live == before;
    const host_still = track.live >= before;
    allocator.free(host);
    allocator.free(copy);
    try positiveControl(track, 64);
    try emitJson(init, init.gpa,
        "{{\"bytes_ok\":{s},\"match\":{s},\"extrema\":{s},\"card\":{s},\"owns\":{s},\"scribble_bytes\":{s},\"scribble_match\":{s},\"scribble_card\":{s},\"has_new\":{s},\"source_spared\":{s},\"source_orig\":{s},\"released\":{s},\"host_still\":{s}}}",
        .{
            jsonBool(bytes_ok), jsonBool(match), jsonBool(extrema), jsonBool(card), jsonBool(owns),
            jsonBool(after_scribble_bytes), jsonBool(after_scribble_match), jsonBool(after_scribble_card),
            jsonBool(has_new), jsonBool(source_spared), jsonBool(source_orig), jsonBool(released), jsonBool(host_still),
        },
    );
""",
            vals=zig_u64_list(shuffle_not_sorted(values)),
            ordered=zig_u64_list(ordered),
            absent=absent,
            newv=newv,
            offset=offset,
        )
    )


def test_copying_open_aligned_bytes_owns_a_copy_and_mutation_spares_source():
    values = unpublished_population_f04(unpublished_count_f04())
    newv = unpublished_u64_f04(forbidden=set(values))
    report = run_bitmap_probe(_copy_probe(0, values, newv))
    require_true_fields(
        report,
        "bytes_ok",
        "match",
        "extrema",
        "card",
        "owns",
        "scribble_bytes",
        "scribble_match",
        "scribble_card",
        "has_new",
        "source_spared",
        "source_orig",
        "released",
        "host_still",
    )


def test_copying_open_at_offset_2_matches_source_and_set_does_not_change_source_slice():
    values = unpublished_population_f04(unpublished_count_f04())
    newv = unpublished_u64_f04(forbidden=set(values))
    report = run_bitmap_probe(_copy_probe(2, values, newv))
    require_true_fields(
        report,
        "bytes_ok",
        "match",
        "extrema",
        "card",
        "owns",
        "scribble_bytes",
        "scribble_match",
        "scribble_card",
        "has_new",
        "source_spared",
        "source_orig",
        "released",
        "host_still",
    )


def test_copying_open_at_unpublished_residue_matches_source_and_spares_source_slice():
    values = unpublished_population_f04(unpublished_count_f04())
    newv = unpublished_u64_f04(forbidden=set(values))
    offset = unpublished_residue_f04()
    report = run_bitmap_probe(_copy_probe(offset, values, newv))
    require_true_fields(
        report,
        "bytes_ok",
        "match",
        "extrema",
        "card",
        "owns",
        "scribble_bytes",
        "scribble_match",
        "scribble_card",
        "has_new",
        "source_spared",
        "source_orig",
        "released",
        "host_still",
    )


# ---------------------------------------------------------------------------
# G. Compact after borrow
# ---------------------------------------------------------------------------


def test_compact_after_borrow_open_owns_distinct_storage_and_does_not_write_caller():
    values = unpublished_population_f04(unpublished_count_f04())
    newv = unpublished_u64_f04(forbidden=set(values))
    ordered = sorted(values)
    source = wrap_f04_probe(
        fill_u64(
            r"""
    const vals = [_]u64{ __VALS__ };
    const ordered = [_]u64{ __ORDERED__ };
    const newv: u64 = __NEWV__;
    var bm = try klyvmap.Bitmap.init(allocator);
    for (vals) |v| _ = try bm.set(v);
    const copy = try bm.toBufferCopy(allocator);
    bm.deinit();
    const snap = try init.gpa.dupe(u8, copy);
    defer init.gpa.free(snap);
    var opened = klyvmap.Bitmap.fromBuffer(allocator, copy, .borrow) catch return error.BorrowFailed;
    const before_compact = track.live;
    try opened.compact();
    const caller_same = std.mem.eql(u8, copy, snap);
    const view = opened.toBuffer();
    const owns = view.len > 0 and track.live >= before_compact + view.len;
    const result_snap = try init.gpa.dupe(u8, view);
    defer init.gpa.free(result_snap);
    const card_before = opened.getCardinality();
    @memset(copy, 0xa1);
    const scribble_card = opened.getCardinality() == card_before;
    const scribble_bytes = std.mem.eql(u8, opened.toBuffer(), result_snap);
    @memcpy(copy, snap);
    _ = try opened.set(newv);
    const has = opened.contains(newv);
    const card_up = opened.getCardinality() == card_before + 1;
    opened.deinit();
    const released = track.live == before_compact;
    var again = klyvmap.Bitmap.fromBuffer(allocator, copy, .borrow) catch return error.SecondOpenFailed;
    var orig = true;
    for (ordered) |o| if (!again.contains(o)) { orig = false; };
    const omits = !again.contains(newv);
    again.deinit();
    const still = std.mem.eql(u8, copy, snap);
    allocator.free(copy);
    try positiveControl(track, 64);
    try emitJson(init, init.gpa,
        "{{\"caller_same\":{s},\"owns\":{s},\"scribble_card\":{s},\"scribble_bytes\":{s},\"has\":{s},\"card_up\":{s},\"released\":{s},\"orig\":{s},\"omits\":{s},\"still\":{s}}}",
        .{
            jsonBool(caller_same), jsonBool(owns), jsonBool(scribble_card), jsonBool(scribble_bytes),
            jsonBool(has), jsonBool(card_up), jsonBool(released), jsonBool(orig), jsonBool(omits), jsonBool(still),
        },
    );
""",
            vals=zig_u64_list(shuffle_not_sorted(values)),
            ordered=zig_u64_list(ordered),
            newv=newv,
        )
    )
    report = run_bitmap_probe(source)
    require_true_fields(
        report,
        "caller_same",
        "owns",
        "scribble_card",
        "scribble_bytes",
        "has",
        "card_up",
        "released",
        "orig",
        "omits",
        "still",
    )


# ---------------------------------------------------------------------------
# H. No file or network I/O
# ---------------------------------------------------------------------------


def _trace_file_io(ws, binary: str, *, what: str) -> tuple[list[str], list[str]]:
    run, writes, reads = run_traced_file_writes(
        ws, [str(ws.resolve(binary))], timeout=DEFAULT_TIMEOUT
    )
    if run.returncode != 0:
        raise HarnessError(f"{what} exited {run.returncode}\n{run.stderr_text}")
    return file_write_syscalls_in_trace(writes), unexpected_file_reads_in_trace(reads)


def _trace_network(ws, binary: str, *, what: str) -> list[str]:
    run, hits = run_traced_arch_network(
        ws, [str(ws.resolve(binary))], timeout=DEFAULT_TIMEOUT
    )
    if run.returncode != 0:
        raise HarnessError(f"{what} exited {run.returncode}\n{run.stderr_text}")
    return network_syscalls_in_trace(hits)


def test_emit_and_open_perform_no_file_io():
    value = unpublished_u64_f04()
    borrowed_view = wrap_f04_probe(
        fill_u64(
            r"""
    const value: u64 = __VALUE__;
    var bm = try klyvmap.Bitmap.init(allocator);
    _ = try bm.set(value);
    const view = bm.toBuffer();
    if (view.len == 0) return error.EmptyView;
    _ = view[0];
    bm.deinit();
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
""",
            value=value,
        )
    )
    own_open = wrap_f04_probe(
        fill_u64(
            r"""
    const value: u64 = __VALUE__;
    var bm = try klyvmap.Bitmap.init(allocator);
    _ = try bm.set(value);
    const copy = try bm.toBufferCopy(allocator);
    bm.deinit();
    var opened = klyvmap.Bitmap.fromBuffer(allocator, copy, .own) catch return error.OwnFailed;
    _ = opened.contains(value);
    _ = opened.getCardinality();
    opened.deinit();
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
""",
            value=value,
        )
    )
    borrow_open = wrap_f04_probe(
        fill_u64(
            r"""
    const value: u64 = __VALUE__;
    var bm = try klyvmap.Bitmap.init(allocator);
    _ = try bm.set(value);
    const copy = try bm.toBufferCopy(allocator);
    bm.deinit();
    var opened = klyvmap.Bitmap.fromBuffer(allocator, copy, .borrow) catch return error.BorrowFailed;
    _ = opened.contains(value);
    _ = opened.getCardinality();
    opened.deinit();
    allocator.free(copy);
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
""",
            value=value,
        )
    )
    copying_open = wrap_f04_probe(
        fill_u64(
            r"""
    const value: u64 = __VALUE__;
    var bm = try klyvmap.Bitmap.init(allocator);
    _ = try bm.set(value);
    const copy = try bm.toBufferCopy(allocator);
    bm.deinit();
    var opened = klyvmap.Bitmap.fromBufferCopy(allocator, copy) catch return error.CopyFailed;
    _ = opened.contains(value);
    _ = opened.getCardinality();
    opened.deinit();
    allocator.free(copy);
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
""",
            value=value,
        )
    )
    vandal = wrap_f04_probe(
        r"""
    var cwd = std.Io.Dir.cwd();
    var f = try cwd.createFile(init.io, "gone_side.txt", .{});
    try f.writeStreamingAll(init.io, "x");
    f.close(init.io);
    try cwd.deleteFile(init.io, "gone_side.txt");
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
"""
    )
    reader = wrap_f04_probe(
        r"""
    var cwd = std.Io.Dir.cwd();
    var f = try cwd.openFile(init.io, "planted_read.txt", .{});
    var buf: [8]u8 = undefined;
    _ = try f.readPositionalAll(init.io, &buf, 0);
    f.close(init.io);
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
"""
    )
    with workspace() as ws:
        compile_probe_or_raise(ws, borrowed_view, relpath="view.zig", output="view")
        compile_probe_or_raise(ws, own_open, relpath="own.zig", output="own")
        compile_probe_or_raise(ws, borrow_open, relpath="borrow.zig", output="borrow")
        compile_probe_or_raise(ws, copying_open, relpath="copy.zig", output="copy")
        compile_probe_or_raise(ws, vandal, relpath="vandal.zig", output="vandal")
        compile_probe_or_raise(ws, reader, relpath="reader.zig", output="reader")
        (ws.path / "planted_read.txt").write_bytes(b"planted!")

        view_writes, view_reads = _trace_file_io(ws, "view", what="borrowed view")
        assert view_writes == [], f"borrowed view issued file writes: {view_writes}"
        assert view_reads == [], f"borrowed view read a path it did not need: {view_reads}"
        own_writes, own_reads = _trace_file_io(ws, "own", what="own open")
        assert own_writes == [], f"own open issued file writes: {own_writes}"
        assert own_reads == [], f"own open read a path it did not need: {own_reads}"
        borrow_writes, borrow_reads = _trace_file_io(ws, "borrow", what="borrow open")
        assert borrow_writes == [], f"borrow open issued file writes: {borrow_writes}"
        assert borrow_reads == [], f"borrow open read a path it did not need: {borrow_reads}"
        copy_writes, copy_reads = _trace_file_io(ws, "copy", what="copying open")
        assert copy_writes == [], f"copying open issued file writes: {copy_writes}"
        assert copy_reads == [], f"copying open read a path it did not need: {copy_reads}"

        vandal_writes, _vandal_reads = _trace_file_io(ws, "vandal", what="file-I/O positive control")
        assert vandal_writes, "write-then-remove positive control did not observe a file write"
        assert not (ws.path / "gone_side.txt").exists(), (
            "write-then-remove positive control left the file behind"
        )
        reader_writes, reader_reads = _trace_file_io(ws, "reader", what="read-only positive control")
        assert reader_reads, "read-only positive control did not observe a file read"
        assert reader_writes == [], (
            f"read-only positive control was classified as a file write: {reader_writes}"
        )


def test_emit_and_open_perform_no_network_io():
    value = unpublished_u64_f04()
    borrowed_view = wrap_f04_probe(
        fill_u64(
            r"""
    const value: u64 = __VALUE__;
    var bm = try klyvmap.Bitmap.init(allocator);
    _ = try bm.set(value);
    const view = bm.toBuffer();
    if (view.len == 0) return error.EmptyView;
    _ = view[0];
    bm.deinit();
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
""",
            value=value,
        )
    )
    honest = wrap_f04_probe(
        fill_u64(
            r"""
    const value: u64 = __VALUE__;
    var bm = try klyvmap.Bitmap.init(allocator);
    _ = try bm.set(value);
    const copy = try bm.toBufferCopy(allocator);
    bm.deinit();
    var opened = klyvmap.Bitmap.fromBuffer(allocator, copy, .borrow) catch return error.BorrowFailed;
    _ = opened.contains(value);
    opened.deinit();
    allocator.free(copy);
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
""",
            value=value,
        )
    )
    own_open = wrap_f04_probe(
        fill_u64(
            r"""
    const value: u64 = __VALUE__;
    var bm = try klyvmap.Bitmap.init(allocator);
    _ = try bm.set(value);
    const copy = try bm.toBufferCopy(allocator);
    bm.deinit();
    var opened = klyvmap.Bitmap.fromBuffer(allocator, copy, .own) catch return error.OwnFailed;
    _ = opened.contains(value);
    _ = opened.getCardinality();
    opened.deinit();
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
""",
            value=value,
        )
    )
    copying_open = wrap_f04_probe(
        fill_u64(
            r"""
    const value: u64 = __VALUE__;
    var bm = try klyvmap.Bitmap.init(allocator);
    _ = try bm.set(value);
    const copy = try bm.toBufferCopy(allocator);
    bm.deinit();
    var opened = klyvmap.Bitmap.fromBufferCopy(allocator, copy) catch return error.CopyFailed;
    _ = opened.contains(value);
    _ = opened.getCardinality();
    opened.deinit();
    allocator.free(copy);
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
""",
            value=value,
        )
    )
    vandal = wrap_f04_probe(
        r"""
    const linux = std.os.linux;
    _ = linux.socket(linux.AF.INET, linux.SOCK.STREAM, 0);
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
"""
    )
    with workspace() as ws:
        compile_probe_or_raise(ws, borrowed_view, relpath="view.zig", output="view")
        compile_probe_or_raise(ws, honest, relpath="probe.zig", output="probe")
        compile_probe_or_raise(ws, own_open, relpath="own.zig", output="own")
        compile_probe_or_raise(ws, copying_open, relpath="copy.zig", output="copy")
        compile_probe_or_raise(ws, vandal, relpath="vandal.zig", output="vandal")

        view_hits = _trace_network(ws, "view", what="borrowed view")
        assert view_hits == [], f"borrowed view issued network syscalls: {view_hits}"
        hits = _trace_network(ws, "probe", what="honest network probe")
        assert hits == [], f"emit/open issued network syscalls: {hits}"
        own_hits = _trace_network(ws, "own", what="own open")
        assert own_hits == [], f"own open issued network syscalls: {own_hits}"
        copy_hits = _trace_network(ws, "copy", what="copying open")
        assert copy_hits == [], f"copying open issued network syscalls: {copy_hits}"

        vandal_hits = _trace_network(ws, "vandal", what="network positive control")
        assert vandal_hits, "network positive control did not observe a socket/connect"


# ---------------------------------------------------------------------------
# I. Own open before a set: no allocation, the view is the handed allocation
# ---------------------------------------------------------------------------


def test_own_open_and_reads_before_a_set_allocate_nothing_and_emit_the_handed_allocation():
    values = unpublished_population_f04(unpublished_count_f04())
    absent = unpublished_u64_f04(forbidden=set(values))
    ordered = sorted(values)
    require_strictly_ascending_once(ordered, cardinality=len(ordered))
    source = wrap_f04_probe(
        _seed_template_zig(values)
        + fill_u64(
            r"""
    const ordered = [_]u64{ __ORDERED__ };
    const absent: u64 = __ABSENT__;
    const before = track.live;
    const buf = try allocator.alignedAlloc(u8, .@"8", template.len);
    @memcpy(buf, template);
    const handed = @intFromPtr(buf.ptr);
    beginWatch(track, 1);
    var owned = klyvmap.Bitmap.fromBuffer(allocator, buf, .own) catch return error.OwnOpenFailed;
    const match = membersExact(&owned, &ordered, absent);
    const iter_ok = iterExact(&owned, &ordered);
    const extrema = extremaExact(&owned, ordered[0], ordered[ordered.len - 1]);
    const not_empty = !owned.isEmpty();
    const is_handed = viewIsHandedAllocation(&owned, handed, template.len);
    const none = track.log_n == 0;
    try endWatch(track);
    _ = try owned.set(absent);
    const has = owned.contains(absent) and owned.getCardinality() == ordered.len + 1;
    owned.deinit();
    const baseline = track.live == before;
    try positiveControl(track, template.len);
    try emitJson(init, init.gpa,
        "{{\"match\":{s},\"iter_ok\":{s},\"extrema\":{s},\"not_empty\":{s},\"is_handed\":{s},\"none\":{s},\"has\":{s},\"baseline\":{s}}}",
        .{
            jsonBool(match), jsonBool(iter_ok), jsonBool(extrema), jsonBool(not_empty),
            jsonBool(is_handed), jsonBool(none), jsonBool(has), jsonBool(baseline),
        },
    );
""",
            ordered=zig_u64_list(ordered),
            absent=absent,
        )
    )
    report = run_bitmap_probe(source)
    require_true_fields(
        report, "match", "iter_ok", "extrema", "not_empty", "is_handed", "none", "has", "baseline"
    )


# ---------------------------------------------------------------------------
# J. A borrow open builds no second form anywhere in memory
# ---------------------------------------------------------------------------


def test_borrow_open_and_reads_of_a_large_buffer_touch_no_new_memory_proportional_to_it():
    # The in-memory form is the buffer: a borrow open and reads on it do not
    # copy, index, or decode the contents into other memory, whichever
    # allocator such memory would come from. Every page of memory a process
    # touches for the first time is a minor page fault; with transparent huge
    # pages turned off for this process, a second form of this buffer would
    # cost at least one fault per page it occupies.
    dense_base, sparse, absent = dense_and_sparse_f04(dense_blocks=64, sparse_count=512)
    everything_min = min(dense_base << 16, *sparse)
    everything_max = max(((dense_base + 63) << 16) | 0xFFFF, *sparse)
    source = wrap_f04_probe(
        fill_u64(
            r"""
    const linux = std.os.linux;
    if (linux.errno(linux.prctl(@intFromEnum(linux.PR.SET_THP_DISABLE), 1, 0, 0, 0)) != .SUCCESS) return error.ThpControl;
    if (linux.prctl(@intFromEnum(linux.PR.GET_THP_DISABLE), 0, 0, 0, 0) != 1) return error.ThpControl;
    const dense_base: u64 = __DENSE_BASE__;
    const dense_blocks: u64 = 64;
    const sparse = [_]u64{ __SPARSE__ };
    const absent = [_]u64{ __ABSENT__ };
    const want_min: u64 = __WANT_MIN__;
    const want_max: u64 = __WANT_MAX__;
    const want_card: u64 = dense_blocks * 65536 + sparse.len;
    const Reads = struct {
        fn run(bm: *const klyvmap.Bitmap, base: u64, blocks: u64, sp: []const u64, ab: []const u64, card: u64, mn: u64, mx: u64) bool {
            var ok = bm.getCardinality() == card and !bm.isEmpty();
            ok = ok and (bm.minimum() orelse return false) == mn and (bm.maximum() orelse return false) == mx;
            for (sp) |v| ok = ok and bm.contains(v);
            for (ab) |v| ok = ok and !bm.contains(v);
            var p: u64 = 0;
            while (p < blocks) : (p += 1) {
                const hi = (base + p) << 16;
                ok = ok and bm.contains(hi) and bm.contains(hi | 0xFFFF) and bm.contains(hi | ((p *% 40503) & 0xFFFF));
            }
            var it = bm.iterator();
            var n: u64 = 0;
            var prev: ?u64 = null;
            while (it.next()) |x| {
                if (prev) |q| ok = ok and x > q;
                prev = x;
                n += 1;
            }
            return ok and n == card;
        }
        fn faults() isize {
            return std.posix.getrusage(std.posix.rusage.SELF).minflt;
        }
    };
    // Warm the same code path on a small bitmap so the window below does not
    // count the first execution of product code.
    {
        var w = try klyvmap.Bitmap.init(allocator);
        var low: u64 = 0;
        while (low < 65536) : (low += 1) _ = try w.set((dense_base << 16) | low);
        for (sparse[0..8]) |v| _ = try w.set(v);
        const wcopy = try w.toBufferCopy(allocator);
        w.deinit();
        var wo = klyvmap.Bitmap.fromBuffer(allocator, wcopy, .borrow) catch return error.BorrowFailed;
        _ = Reads.run(&wo, dense_base, 1, sparse[0..8], &absent, 65536 + 8, want_min, want_max);
        wo.deinit();
        allocator.free(wcopy);
    }
    var bm = try klyvmap.Bitmap.init(allocator);
    var p: u64 = 0;
    while (p < dense_blocks) : (p += 1) {
        var low: u64 = 0;
        while (low < 65536) : (low += 1) _ = try bm.set(((dense_base + p) << 16) | low);
    }
    for (sparse) |v| _ = try bm.set(v);
    const copy = try bm.toBufferCopy(allocator);
    bm.deinit();
    const pages: isize = @intCast(copy.len / 4096);
    beginWatch(track, 1);
    const f0 = Reads.faults();
    var opened = klyvmap.Bitmap.fromBuffer(allocator, copy, .borrow) catch return error.BorrowFailed;
    const reads_ok = Reads.run(&opened, dense_base, dense_blocks, &sparse, &absent, want_card, want_min, want_max);
    const is_caller = viewIsHandedAllocation(&opened, @intFromPtr(copy.ptr), copy.len);
    const f1 = Reads.faults();
    const none = track.log_n == 0;
    try endWatch(track);
    opened.deinit();
    allocator.free(copy);
    // Positive control: memory of the buffer's size, touched for the first
    // time, is visible to this observer.
    const c0 = Reads.faults();
    const fresh = try std.heap.page_allocator.alloc(u8, @intCast(pages * 4096));
    @memset(fresh, 0x5a);
    const c1 = Reads.faults();
    const touched = fresh[fresh.len - 1] == 0x5a;
    std.heap.page_allocator.free(fresh);
    try emitJson(init, init.gpa,
        "{{\"reads_ok\":{s},\"is_caller\":{s},\"none\":{s},\"touched\":{s},\"pages\":{d},\"faults\":{d},\"control\":{d}}}",
        .{ jsonBool(reads_ok), jsonBool(is_caller), jsonBool(none), jsonBool(touched), pages, f1 - f0, c1 - c0 },
    );
""",
            dense_base=dense_base,
            sparse=zig_u64_list(shuffle_not_sorted(sparse)),
            absent=zig_u64_list(absent),
            want_min=everything_min,
            want_max=everything_max,
        )
    )
    report = run_bitmap_probe(source, timeout=LARGE_PROBE_TIMEOUT)
    require_true_fields(report, "reads_ok", "is_caller", "none", "touched")
    pages = require_int_field(report, "pages")
    control = require_int_field(report, "control")
    faults = require_int_field(report, "faults")
    if pages < 64:
        raise HarnessError(f"buffer spans only {pages} pages; not a usable contrast")
    if control < pages // 2:
        raise HarnessError(
            f"touching {pages} fresh pages registered {control} faults; the observer is silent"
        )
    assert faults * 4 < pages, (
        f"borrow open and reads first-touched {faults} pages of memory for a {pages}-page buffer"
    )


# ---------------------------------------------------------------------------
# K. Emit and open one prefix at every population on the way to full and back
# ---------------------------------------------------------------------------


def test_one_prefix_opens_in_every_mode_at_every_population_while_filled_and_emptied():
    report = run_block_sweep(
        r"""
    const Open = struct {
        fn check(src: *const klyvmap.Bitmap, b: Block, lo: u64, hi: u64, alloc: std.mem.Allocator, gpa: std.mem.Allocator) !bool {
            const copy = try src.toBufferCopy(alloc);
            defer alloc.free(copy);
            const snap = try gpa.dupe(u8, copy);
            defer gpa.free(snap);
            var ok = copy.len > 0 and copy.len % 2 == 0;
            {
                var o = klyvmap.Bitmap.fromBuffer(alloc, copy, .borrow) catch return false;
                defer o.deinit();
                ok = ok and o.getCardinality() == hi - lo + 2 and b.walk(&o, lo, hi, true);
                ok = ok and std.mem.eql(u8, o.toBuffer(), src.toBuffer()) and std.mem.eql(u8, copy, snap);
            }
            {
                const raw = try gpa.alignedAlloc(u8, .@"8", copy.len + 8);
                defer gpa.free(raw);
                const odd = raw[2 .. 2 + copy.len];
                @memcpy(odd, copy);
                var o = klyvmap.Bitmap.fromBufferCopy(alloc, odd) catch return false;
                defer o.deinit();
                ok = ok and o.getCardinality() == hi - lo + 2 and b.walk(&o, lo, hi, true);
                ok = ok and std.mem.eql(u8, o.toBuffer(), copy) and std.mem.eql(u8, odd, copy);
            }
            {
                const handed = try alloc.alignedAlloc(u8, .@"8", copy.len);
                @memcpy(handed, copy);
                var o = klyvmap.Bitmap.fromBuffer(alloc, handed, .own) catch return false;
                defer o.deinit();
                const view = o.toBuffer();
                ok = ok and view.ptr == handed.ptr and view.len == handed.len;
                ok = ok and o.getCardinality() == hi - lo + 2 and b.walk(&o, lo, hi, true);
            }
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
        if (Block.isCheckpoint(n + 1, &checkpoints)) {
            if (!try Open.check(&bm, block, 0, n + 1, allocator, init.gpa)) grow_ok = false;
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
            if (!try Open.check(&bm, block, n + 1, 65536, allocator, init.gpa)) shrink_ok = false;
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
