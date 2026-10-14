# feature: F01
"""FP-01: create, clone, and release a bitmap.

Covers FP-01 together with the product-wide rules it touches: the
in-memory form is the buffer, the library performs no file or network I/O,
big-endian targets do not compile, and values span the 64-bit domain.
"""

from __future__ import annotations

from pathlib import Path

from F01_helpers import (
    BIG_ENDIAN_TARGET,
    compile_product_source,
    network_syscalls_in_trace,
    product_created_files,
    require_borrowed_buffer_intact,
    require_empty_snapshot,
    require_extrema_absent_not_zero,
    require_positive_buffer_length,
    run_bitmap_probe,
    run_traced_network,
    unpublished_u64,
    wrap_probe_body,
    fill_u64,
    _walk_regular_files,
)
from _helpers import (
    DEFAULT_TIMEOUT,
    HarnessError,
    workspace,
)

# ---------------------------------------------------------------------------
# A. Fresh bitmap is empty
# ---------------------------------------------------------------------------


def test_fresh_bitmap_reports_empty_cardinality_zero_extrema_absent_not_contains_zero():
    source = wrap_probe_body(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    const min_j = try optU64Json(init.gpa, bm.minimum());
    defer init.gpa.free(min_j);
    const max_j = try optU64Json(init.gpa, bm.maximum());
    defer init.gpa.free(max_j);
    try emitJson(init, init.gpa,
        "{{\"empty\":{s},\"cardinality\":{d},\"contains0\":{s},\"min\":{s},\"max\":{s}}}",
        .{ jsonBool(bm.isEmpty()), bm.getCardinality(), jsonBool(bm.contains(0)), min_j, max_j },
    );
"""
    )
    report = run_bitmap_probe(source)
    require_empty_snapshot(report)


def test_zero_is_legal_once_set():
    source = wrap_probe_body(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    const min0 = try optU64Json(init.gpa, bm.minimum());
    defer init.gpa.free(min0);
    const max0 = try optU64Json(init.gpa, bm.maximum());
    defer init.gpa.free(max0);
    const empty0 = bm.isEmpty();
    const card0 = bm.getCardinality();
    const c0_before = bm.contains(0);
    _ = try bm.set(0);
    try emitJson(init, init.gpa,
        "{{\"empty\":{s},\"cardinality\":{d},\"contains0\":{s},\"min\":{s},\"max\":{s},\"after_empty\":{s},\"after_contains0\":{s}}}",
        .{
            jsonBool(empty0), card0, jsonBool(c0_before), min0, max0,
            jsonBool(bm.isEmpty()), jsonBool(bm.contains(0)),
        },
    );
"""
    )
    report = run_bitmap_probe(source)
    empty = {
        "empty": report["empty"],
        "cardinality": report["cardinality"],
        "contains0": report["contains0"],
        "min": report["min"],
        "max": report["max"],
    }
    after = {
        "empty": report["after_empty"],
        "contains0": report["after_contains0"],
    }
    require_extrema_absent_not_zero(empty, after)


def test_emptiness_differs_after_unpublished_set():
    value = unpublished_u64()
    source = wrap_probe_body(
        fill_u64(
            r"""
    const value: u64 = __VALUE__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    const empty_before = bm.isEmpty();
    _ = try bm.set(value);
    const empty_after = bm.isEmpty();
    try emitJson(init, init.gpa,
        "{{\"empty_before\":{s},\"empty_after\":{s},\"contains\":{s}}}",
        .{ jsonBool(empty_before), jsonBool(empty_after), jsonBool(bm.contains(value)) },
    );
""",
            value=value,
        )
    )
    report = run_bitmap_probe(source)
    assert report["empty_before"] is True
    assert report["empty_after"] is False
    assert report["contains"] is True
    assert report["empty_before"] != report["empty_after"]


def test_second_constructor_stays_empty_while_first_holds_values():
    value = unpublished_u64()
    source = wrap_probe_body(
        fill_u64(
            r"""
    const value: u64 = __VALUE__;
    var first = try klyvmap.Bitmap.init(allocator);
    defer first.deinit();
    _ = try first.set(value);
    var second = try klyvmap.Bitmap.init(allocator);
    defer second.deinit();
    const min_j = try optU64Json(init.gpa, second.minimum());
    defer init.gpa.free(min_j);
    const max_j = try optU64Json(init.gpa, second.maximum());
    defer init.gpa.free(max_j);
    try emitJson(init, init.gpa,
        "{{\"first_contains\":{s},\"empty\":{s},\"cardinality\":{d},\"contains0\":{s},\"min\":{s},\"max\":{s},\"second_contains_first_value\":{s}}}",
        .{
            jsonBool(first.contains(value)),
            jsonBool(second.isEmpty()),
            second.getCardinality(),
            jsonBool(second.contains(0)),
            min_j,
            max_j,
            jsonBool(second.contains(value)),
        },
    );
""",
            value=value,
        )
    )
    report = run_bitmap_probe(source)
    assert report["first_contains"] is True
    require_empty_snapshot(report)
    assert report["second_contains_first_value"] is False


# ---------------------------------------------------------------------------
# B. Empty emit / reopen / set 42
# ---------------------------------------------------------------------------


def test_empty_bitmap_emits_positive_length_buffer_reopens_empty_set_42_present():
    source = wrap_probe_body(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    const copy = try bm.toBufferCopy(allocator);
    defer allocator.free(copy);
    const blen = copy.len;
    var opened = try klyvmap.Bitmap.fromBuffer(allocator, copy, .borrow);
    defer opened.deinit();
    const min_j = try optU64Json(init.gpa, opened.minimum());
    defer init.gpa.free(min_j);
    const max_j = try optU64Json(init.gpa, opened.maximum());
    defer init.gpa.free(max_j);
    const empty = opened.isEmpty();
    const card = opened.getCardinality();
    const c0 = opened.contains(0);
    _ = try opened.set(42);
    try emitJson(init, init.gpa,
        "{{\"blen\":{d},\"empty\":{s},\"cardinality\":{d},\"contains0\":{s},\"min\":{s},\"max\":{s},\"contains42\":{s}}}",
        .{ blen, jsonBool(empty), card, jsonBool(c0), min_j, max_j, jsonBool(opened.contains(42)) },
    );
"""
    )
    report = run_bitmap_probe(source)
    require_positive_buffer_length(report["blen"])
    require_empty_snapshot(report)
    assert report["contains42"] is True


def test_reopened_empty_buffer_accepts_unpublished_value():
    value = unpublished_u64()
    source = wrap_probe_body(
        fill_u64(
            r"""
    const value: u64 = __VALUE__;
    var bm = try klyvmap.Bitmap.init(allocator);
    defer bm.deinit();
    const copy = try bm.toBufferCopy(allocator);
    defer allocator.free(copy);
    var opened = try klyvmap.Bitmap.fromBuffer(allocator, copy, .borrow);
    defer opened.deinit();
    _ = try opened.set(value);
    try emitJson(init, init.gpa,
        "{{\"contains\":{s},\"empty\":{s}}}",
        .{ jsonBool(opened.contains(value)), jsonBool(opened.isEmpty()) },
    );
""",
            value=value,
        )
    )
    report = run_bitmap_probe(source)
    assert report["contains"] is True
    assert report["empty"] is False


def test_empty_and_populated_emitted_buffers_reopen_as_distinct_sets():
    """L101 / L112: empty emit has positive length and reopens empty.

    A sibling bitmap that holds an unpublished value must not leak into
    that empty reopen. Restoring membership by opening a populated emit
    is FP-04 (L182) and is not asserted here.
    """
    value = unpublished_u64()
    source = wrap_probe_body(
        fill_u64(
            r"""
    const value: u64 = __VALUE__;
    var empty_bm = try klyvmap.Bitmap.init(allocator);
    defer empty_bm.deinit();
    const empty_buf = try empty_bm.toBufferCopy(allocator);
    defer allocator.free(empty_buf);
    var populated = try klyvmap.Bitmap.init(allocator);
    defer populated.deinit();
    _ = try populated.set(value);
    const pop_buf = try populated.toBufferCopy(allocator);
    defer allocator.free(pop_buf);
    var opened_empty = try klyvmap.Bitmap.fromBuffer(allocator, empty_buf, .borrow);
    defer opened_empty.deinit();
    const min_j = try optU64Json(init.gpa, opened_empty.minimum());
    defer init.gpa.free(min_j);
    const max_j = try optU64Json(init.gpa, opened_empty.maximum());
    defer init.gpa.free(max_j);
    try emitJson(init, init.gpa,
        "{{\"empty\":{s},\"cardinality\":{d},\"contains0\":{s},\"min\":{s},\"max\":{s},\"empty_has_value\":{s},\"empty_len\":{d},\"pop_len\":{d}}}",
        .{
            jsonBool(opened_empty.isEmpty()), opened_empty.getCardinality(),
            jsonBool(opened_empty.contains(0)), min_j, max_j,
            jsonBool(opened_empty.contains(value)),
            empty_buf.len, pop_buf.len,
        },
    );
""",
            value=value,
        )
    )
    report = run_bitmap_probe(source)
    require_positive_buffer_length(report["empty_len"])
    require_positive_buffer_length(report["pop_len"])
    require_empty_snapshot(report)
    assert report["empty_has_value"] is False


# ---------------------------------------------------------------------------
# C. Clone independence
# ---------------------------------------------------------------------------


def test_clone_of_zero_through_2999_and_2_pow_40_is_independent_under_set_2_pow_50_and_remove_zero():
    source = wrap_probe_body(
        r"""
    var original = try klyvmap.Bitmap.init(allocator);
    defer original.deinit();
    var x: u64 = 0;
    while (x <= 2999) : (x += 1) {
        _ = try original.set(x);
    }
    _ = try original.set(1 << 40);
    var cloned = try original.clone();
    defer cloned.deinit();
    const before_orig_range = allPresent(&original, 0, 2999);
    const before_clone_range = allPresent(&cloned, 0, 2999);
    const before_orig_p40 = original.contains(1 << 40);
    const before_clone_p40 = cloned.contains(1 << 40);
    const before_orig_p50 = original.contains(1 << 50);
    const before_clone_p50 = cloned.contains(1 << 50);
    _ = try cloned.set(1 << 50);
    _ = original.remove(0);
    try emitJson(init, init.gpa,
        "{{\"before_orig_range\":{s},\"before_clone_range\":{s},\"before_orig_p40\":{s},\"before_clone_p40\":{s},\"before_orig_p50\":{s},\"before_clone_p50\":{s},\"clone_has_0\":{s},\"clone_has_2_50\":{s},\"clone_range\":{s},\"clone_has_2999\":{s},\"clone_has_2_40\":{s},\"clone_has_1500\":{s},\"orig_has_0\":{s},\"orig_has_2_50\":{s},\"orig_has_2999\":{s},\"orig_has_2_40\":{s},\"orig_range_1_2999\":{s}}}",
        .{
            jsonBool(before_orig_range), jsonBool(before_clone_range),
            jsonBool(before_orig_p40), jsonBool(before_clone_p40),
            jsonBool(before_orig_p50), jsonBool(before_clone_p50),
            jsonBool(cloned.contains(0)), jsonBool(cloned.contains(1 << 50)),
            jsonBool(allPresent(&cloned, 0, 2999)), jsonBool(cloned.contains(2999)),
            jsonBool(cloned.contains(1 << 40)), jsonBool(cloned.contains(1500)),
            jsonBool(original.contains(0)), jsonBool(original.contains(1 << 50)),
            jsonBool(original.contains(2999)), jsonBool(original.contains(1 << 40)),
            jsonBool(allPresent(&original, 1, 2999)),
        },
    );
"""
    )
    report = run_bitmap_probe(source)
    assert report["before_orig_range"] is True
    assert report["before_clone_range"] is True
    assert report["before_orig_p40"] is True
    assert report["before_clone_p40"] is True
    assert report["before_orig_p50"] is False
    assert report["before_clone_p50"] is False
    assert report["clone_has_0"] is True
    assert report["clone_has_2_50"] is True
    assert report["clone_range"] is True
    assert report["clone_has_2999"] is True
    assert report["clone_has_2_40"] is True
    assert report["clone_has_1500"] is True
    assert report["orig_has_0"] is False
    assert report["orig_has_2_50"] is False
    assert report["orig_has_2999"] is True
    assert report["orig_has_2_40"] is True
    assert report["orig_range_1_2999"] is True


def test_clone_of_empty_is_empty_and_set_on_clone_leaves_original_empty():
    value = unpublished_u64()
    source = wrap_probe_body(
        fill_u64(
            r"""
    const value: u64 = __VALUE__;
    var original = try klyvmap.Bitmap.init(allocator);
    defer original.deinit();
    var cloned = try original.clone();
    defer cloned.deinit();
    const min_j = try optU64Json(init.gpa, cloned.minimum());
    defer init.gpa.free(min_j);
    const max_j = try optU64Json(init.gpa, cloned.maximum());
    defer init.gpa.free(max_j);
    const clone_empty = cloned.isEmpty();
    const clone_card = cloned.getCardinality();
    const clone_c0 = cloned.contains(0);
    _ = try cloned.set(value);
    const orig_min = try optU64Json(init.gpa, original.minimum());
    defer init.gpa.free(orig_min);
    const orig_max = try optU64Json(init.gpa, original.maximum());
    defer init.gpa.free(orig_max);
    try emitJson(init, init.gpa,
        "{{\"empty\":{s},\"cardinality\":{d},\"contains0\":{s},\"min\":{s},\"max\":{s},\"orig_empty\":{s},\"orig_cardinality\":{d},\"orig_contains0\":{s},\"orig_min\":{s},\"orig_max\":{s},\"clone_contains\":{s},\"orig_contains\":{s}}}",
        .{
            jsonBool(clone_empty), clone_card, jsonBool(clone_c0), min_j, max_j,
            jsonBool(original.isEmpty()), original.getCardinality(), jsonBool(original.contains(0)),
            orig_min, orig_max,
            jsonBool(cloned.contains(value)), jsonBool(original.contains(value)),
        },
    );
""",
            value=value,
        )
    )
    report = run_bitmap_probe(source)
    require_empty_snapshot(report)
    orig = {
        "empty": report["orig_empty"],
        "cardinality": report["orig_cardinality"],
        "contains0": report["orig_contains0"],
        "min": report["orig_min"],
        "max": report["orig_max"],
    }
    require_empty_snapshot(orig)
    assert report["clone_contains"] is True
    assert report["orig_contains"] is False


def test_clone_unpublished_values_above_2_pow_32_stay_independent():
    a = unpublished_u64()
    b = unpublished_u64({a})
    extra = unpublished_u64({a, b})
    assert a > (1 << 32) and b > (1 << 32)
    source = wrap_probe_body(
        fill_u64(
            r"""
    const a: u64 = __A__;
    const b: u64 = __B__;
    const extra: u64 = __EXTRA__;
    var original = try klyvmap.Bitmap.init(allocator);
    defer original.deinit();
    _ = try original.set(a);
    _ = try original.set(b);
    var cloned = try original.clone();
    defer cloned.deinit();
    const both_a = original.contains(a) and cloned.contains(a);
    const both_b = original.contains(b) and cloned.contains(b);
    _ = try cloned.set(extra);
    try emitJson(init, init.gpa,
        "{{\"both_a\":{s},\"both_b\":{s},\"clone_extra\":{s},\"orig_extra\":{s},\"orig_a\":{s},\"orig_b\":{s},\"clone_a\":{s},\"clone_b\":{s}}}",
        .{
            jsonBool(both_a), jsonBool(both_b),
            jsonBool(cloned.contains(extra)), jsonBool(original.contains(extra)),
            jsonBool(original.contains(a)), jsonBool(original.contains(b)),
            jsonBool(cloned.contains(a)), jsonBool(cloned.contains(b)),
        },
    );
""",
            a=a,
            b=b,
            extra=extra,
        )
    )
    report = run_bitmap_probe(source)
    assert report["both_a"] is True
    assert report["both_b"] is True
    assert report["clone_extra"] is True
    assert report["orig_extra"] is False
    assert report["orig_a"] is True
    assert report["orig_b"] is True
    assert report["clone_a"] is True
    assert report["clone_b"] is True


def test_releasing_one_clone_side_leaves_the_other_populated():
    value = unpublished_u64()
    high = unpublished_u64({value})
    source = wrap_probe_body(
        fill_u64(
            r"""
    const value: u64 = __VALUE__;
    const high: u64 = __HIGH__;
    const before = track.live;
    var original = try klyvmap.Bitmap.init(allocator);
    _ = try original.set(value);
    _ = try original.set(high);
    var cloned = try original.clone();
    const after_clone = track.live;
    cloned.deinit();
    const after_one = track.live;
    const orig_value = original.contains(value);
    const orig_high = original.contains(high);
    original.deinit();
    const after_both = track.live;
    try emitJson(init, init.gpa,
        "{{\"before\":{d},\"after_clone\":{d},\"after_one\":{d},\"after_both\":{d},\"orig_value\":{s},\"orig_high\":{s}}}",
        .{ before, after_clone, after_one, after_both, jsonBool(orig_value), jsonBool(orig_high) },
    );
""",
            value=value,
            high=high,
        )
    )
    report = run_bitmap_probe(source)
    assert report["orig_value"] is True
    assert report["orig_high"] is True
    assert report["after_clone"] > report["before"]
    assert report["after_one"] < report["after_clone"]
    assert report["after_one"] > report["before"]
    assert report["after_both"] == report["before"]


# ---------------------------------------------------------------------------
# D. Owned / borrowed release
# ---------------------------------------------------------------------------


def test_owned_release_returns_buffer_to_the_caller_allocator():
    value = unpublished_u64()
    source = wrap_probe_body(
        fill_u64(
            r"""
    const value: u64 = __VALUE__;
    const before = track.live;
    var bm = try klyvmap.Bitmap.init(allocator);
    const after_init = track.live;
    const empty_len = bm.toBuffer().len;
    _ = try bm.set(value);
    const grown_len = bm.toBuffer().len;
    const after_set = track.live;
    bm.deinit();
    const after_free = track.live;
    try emitJson(init, init.gpa,
        "{{\"before\":{d},\"after_init\":{d},\"after_set\":{d},\"after_free\":{d},\"empty_len\":{d},\"grown_len\":{d}}}",
        .{ before, after_init, after_set, after_free, empty_len, grown_len },
    );
""",
            value=value,
        )
    )
    report = run_bitmap_probe(source)
    require_positive_buffer_length(report["empty_len"])
    require_positive_buffer_length(report["grown_len"])
    assert report["after_init"] > report["before"], (
        "constructor did not take memory from the caller allocator"
    )
    assert report["after_free"] == report["before"], (
        "owned release did not return live bytes to the pre-construct baseline"
    )


def test_borrowed_release_leaves_caller_buffer_intact_for_a_second_open():
    """L103 / L112: borrowed release does not free or overwrite caller bytes.

    Second open is driven from the empty-buffer path FP-01 already names
    (emit empty, reopen empty, set 42). Restoring membership by opening a
    populated emit is FP-04 (L182) and is not asserted here.
    """
    source = wrap_probe_body(
        r"""
    var src = try klyvmap.Bitmap.init(allocator);
    const copy = try src.toBufferCopy(allocator);
    src.deinit();
    const snap = try allocator.alloc(u8, copy.len);
    @memcpy(snap, copy);
    const live_before_open = track.live;
    var opened = try klyvmap.Bitmap.fromBuffer(allocator, copy, .borrow);
    const first_empty = opened.isEmpty();
    opened.deinit();
    const live_after_release = track.live;
    const bytes_same = std.mem.eql(u8, snap, copy);
    var opened2 = try klyvmap.Bitmap.fromBuffer(allocator, copy, .borrow);
    const second_empty = opened2.isEmpty();
    _ = try opened2.set(42);
    const contains42 = opened2.contains(42);
    opened2.deinit();

    const control_copy = try allocator.alloc(u8, snap.len);
    @memcpy(control_copy, snap);
    @memset(control_copy, 0);
    const overwrite_same = std.mem.eql(u8, snap, control_copy);

    const live_before_free = track.live;
    allocator.free(copy);
    const live_after_free = track.live;

    allocator.free(snap);
    allocator.free(control_copy);

    try emitJson(init, init.gpa,
        "{{\"first_empty\":{s},\"second_empty\":{s},\"contains42\":{s},\"bytes_same\":{s},\"live_before_open\":{d},\"live_after_release\":{d},\"overwrite_same\":{s},\"live_before_free\":{d},\"live_after_free\":{d}}}",
        .{
            jsonBool(first_empty), jsonBool(second_empty), jsonBool(contains42),
            jsonBool(bytes_same), live_before_open, live_after_release,
            jsonBool(overwrite_same), live_before_free, live_after_free,
        },
    );
"""
    )
    report = run_bitmap_probe(source)
    assert report["first_empty"] is True
    assert report["second_empty"] is True
    assert report["contains42"] is True
    require_borrowed_buffer_intact(report)


# ---------------------------------------------------------------------------
# E. No file / network I/O at runtime
# ---------------------------------------------------------------------------


def test_create_clone_release_write_no_files():
    value = unpublished_u64()
    honest = wrap_probe_body(
        fill_u64(
            r"""
    const value: u64 = __VALUE__;
    var bm = try klyvmap.Bitmap.init(allocator);
    _ = try bm.set(value);
    var cloned = try bm.clone();
    cloned.deinit();
    const copy = try bm.toBufferCopy(allocator);
    bm.deinit();
    var opened = try klyvmap.Bitmap.fromBuffer(allocator, copy, .borrow);
    opened.deinit();
    allocator.free(copy);
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
""",
            value=value,
        )
    )

    with workspace() as ws:
        tmp = ws.mkdir("tmp")
        ws.env["TMPDIR"] = str(tmp)
        ws.env["TEMP"] = str(tmp)
        ws.env["TMP"] = str(tmp)
        home_file = (Path(ws.home) / "home_side.txt").resolve()
        tmp_file = (tmp / "tmp_side.txt").resolve()

        compiled = compile_product_source(ws, honest, timeout=DEFAULT_TIMEOUT)
        if compiled.returncode != 0:
            raise HarnessError(
                f"honest I/O probe failed to compile\n{compiled.stderr_text}"
            )
        roots = (ws.path, ws.home, tmp)
        before = set()
        for root in roots:
            before |= _walk_regular_files(root)
        run = ws.run_command([str(ws.resolve("probe"))], timeout=DEFAULT_TIMEOUT)
        if run.returncode != 0:
            raise HarnessError(f"honest I/O probe exited {run.returncode}\n{run.stderr_text}")
        created = product_created_files(before=before, roots=roots)
        assert created == set(), f"create/clone/release wrote files: {created}"

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
        compiled_v = compile_product_source(
            ws, vandal, relpath="vandal.zig", output="vandal", timeout=DEFAULT_TIMEOUT
        )
        if compiled_v.returncode != 0:
            raise HarnessError(
                f"file-I/O positive control failed to compile\n{compiled_v.stderr_text}"
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


def test_create_clone_release_open_no_sockets():
    honest = wrap_probe_body(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    var cloned = try bm.clone();
    cloned.deinit();
    bm.deinit();
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
        compiled = compile_product_source(ws, honest, timeout=DEFAULT_TIMEOUT)
        if compiled.returncode != 0:
            raise HarnessError(
                f"honest network probe failed to compile\n{compiled.stderr_text}"
            )
        run, hits = run_traced_network(
            ws, [str(ws.resolve("probe"))], timeout=DEFAULT_TIMEOUT
        )
        if run.returncode != 0:
            raise HarnessError(
                f"honest network probe exited {run.returncode}\n{run.stderr_text}"
            )
        hits = network_syscalls_in_trace(hits)
        assert hits == [], f"create/clone/release issued network syscalls: {hits}"

        compiled_v = compile_product_source(
            ws, vandal, relpath="vandal.zig", output="vandal", timeout=DEFAULT_TIMEOUT
        )
        if compiled_v.returncode != 0:
            raise HarnessError(
                f"network positive control failed to compile\n{compiled_v.stderr_text}"
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
# F. Big-endian refused at compile time
# ---------------------------------------------------------------------------


def test_big_endian_target_is_refused_at_compile_time():
    hello = "pub fn main() void {}\n"
    probe = wrap_probe_body(
        r"""
    var bm = try klyvmap.Bitmap.init(allocator);
    bm.deinit();
    try emitJson(init, init.gpa, "{{\"ok\":true}}", .{});
"""
    )
    with workspace() as ws:
        native = compile_product_source(ws, probe, output="probe-native")
        if native.returncode != 0:
            raise HarnessError(
                "native little-endian compile of the constructor probe failed "
                f"(live baseline)\n{native.stderr_text}"
            )

        hello_be = compile_product_source(
            ws,
            hello,
            relpath="hello.zig",
            output="hello-be",
            target=BIG_ENDIAN_TARGET,
            include_product=False,
        )
        if hello_be.returncode != 0:
            raise HarnessError(
                f"trivial program failed to compile for {BIG_ENDIAN_TARGET}; "
                "the triple is not a usable contrast\n"
                f"{hello_be.stderr_text}"
            )

        product_be = compile_product_source(
            ws,
            probe,
            relpath="probe-be.zig",
            output="probe-be",
            target=BIG_ENDIAN_TARGET,
            include_product=True,
        )
        assert product_be.returncode != 0, (
            f"constructor probe compiled for big-endian target {BIG_ENDIAN_TARGET}"
        )


