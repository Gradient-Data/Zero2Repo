# feature: F09
"""FP-09: build an owned bitmap from a non-decreasing list of 64-bit values.

The list the test holds, after dropping duplicates, is the reference set.
Setting each input element on a fresh bitmap is a second reference. Emitted
bytes are compared with themselves after a borrowed open, not with a second
construction and not with a layout recomputed in Python.
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
from F02_helpers import LARGE_PROBE_TIMEOUT, require_bool_field, require_int_field
from F03_helpers import (
    require_allocated_matches_independent,
    require_card_empty,
    require_no_integer,
    require_true,
)
from F04_helpers import (
    U64_MAX,
    file_write_syscalls_in_trace,
    require_emit_shape,
    run_traced_arch_network,
    run_traced_file_writes,
    trace_arch_network_syscalls,
    unexpected_file_reads_in_trace,
)
from F09_helpers import (
    absent_beside_prefix_series_f09,
    consecutive_thousands_list_f09,
    empty_list_source,
    five_thousand_prefix_values_f09,
    io_honest_source,
    mixed_unpublished_list_f09,
    repeated_maximum_list_f09,
    six_thousand_list_f09,
    sorted_build_source,
    trace_network_argv,
    unpublished_prefix_series_f09,
    unpublished_u64_f09,
    wrap_sorted_probe,
)
from F02_helpers import (
    block_checkpoints,
    require_sweep_seen,
    require_sweep_true,
    run_block_sweep,
)
from _helpers import DEFAULT_TIMEOUT, HarnessError, workspace


def _require_polarity(report, key: str, expected: bool) -> None:
    got = require_bool_field(report, key)
    if got is not expected:
        raise AssertionError(f"{key} is {got}, expected {expected}")


def _require_shape(report) -> None:
    require_emit_shape(report, length="len", b0="b0", b1="b1", residue="res")
    require_positive_buffer_length(require_int_field(report, "len"))
    if require_int_field(report, "copy_res") != 0:
        raise AssertionError("owning copy of the emitted buffer is not 8-byte aligned")


def _require_built(report, values, unique, *, contains0: bool, has_a: bool, has_b: bool, more: bool) -> None:
    """Common teeth for a non-empty sorted-list build.

    Cardinality is the distinct count. Membership, extrema, the iterator,
    the allocated array, the set-each reference, and the borrowed-open
    bytes are all read off the bitmap this entry returned.
    """
    if require_int_field(report, "nvals") != len(values):
        raise HarnessError("probe did not embed the generated list")
    if require_int_field(report, "unique_len") != len(unique):
        raise HarnessError("probe did not embed the held unique list")
    require_card_empty(report, card=len(unique), empty=False)
    if require_int_field(report, "opened_card") != len(unique):
        raise AssertionError("opened bitmap cardinality is not the distinct count")
    _require_polarity(report, "contains0", contains0)
    _require_polarity(report, "has_a", has_a)
    _require_polarity(report, "has_b", has_b)
    _require_polarity(report, "opened_has_a", has_a)
    _require_polarity(report, "opened_has_b", has_b)
    _require_polarity(report, "opened_contains0", contains0)
    _require_polarity(report, "more", more)
    _require_polarity(report, "hole_absent", True)
    _require_polarity(report, "opened_hole_absent", True)
    require_allocated_matches_independent(
        report,
        unique,
        want_key="array_ok",
        len_key="array_len",
        card_key="card",
    )
    require_true(
        report,
        "absent_out",
        "members",
        "extrema",
        "drained",
        "first_ok",
        "second_ok",
        "set_ok",
        "bytes_same",
        "untouched",
        "control",
        "opened_members",
        "opened_array",
        "opened_drain",
        "released",
    )
    _require_shape(report)


def test_mixed_unpublished_list_matches_unique_values_and_repeated_set():
    values, unique, absent = mixed_unpublished_list_f09()
    if unique[0] <= 0 or unique[-1] != U64_MAX or (U64_MAX - 1) not in unique:
        raise HarnessError("mixed list lost its required ends")
    if len(values) <= len(unique) or len(unique) < 3:
        raise HarnessError("mixed list has no duplicate or too few distinct values")
    report = run_bitmap_probe(
        sorted_build_source(
            values,
            unique,
            marker_a=U64_MAX,
            marker_b=U64_MAX - 1,
            absent=absent,
        ),
        timeout=LARGE_PROBE_TIMEOUT,
    )
    _require_built(
        report,
        values,
        unique,
        contains0=False,
        has_a=True,
        has_b=True,
        more=True,
    )
    if require_int_field(report, "card") >= len(values):
        raise AssertionError("a repeated value counted as an extra member")
    if require_int_field(report, "card") <= 1:
        raise AssertionError("a mixed list collapsed to a single member")


def test_repeated_maximum_counts_once():
    values, count = repeated_maximum_list_f09()
    unique = [U64_MAX]
    if count < 2 or count in (5000, 6000) or len(values) != count:
        raise HarnessError("repeat count is not an unpublished repeat of the maximum")
    report = run_bitmap_probe(
        sorted_build_source(
            values,
            unique,
            marker_a=U64_MAX,
            marker_b=U64_MAX - 1,
            absent=0,
        ),
        timeout=LARGE_PROBE_TIMEOUT,
    )
    _require_built(
        report,
        values,
        unique,
        contains0=False,
        has_a=True,
        has_b=False,
        more=False,
    )
    if require_int_field(report, "card") != 1:
        raise AssertionError("repeated maximum did not count once")
    if require_int_field(report, "card") == count:
        raise AssertionError("repeated maximum counted every copy")


def test_empty_list_matches_fresh_bitmap_and_accepts_a_later_set():
    fresh_a = unpublished_u64_f09(above=1 << 40)
    fresh_b = unpublished_u64_f09(forbidden={fresh_a}, above=1 << 40)
    if fresh_a <= (1 << 40) or fresh_b <= (1 << 40) or fresh_a == fresh_b:
        raise HarnessError("later-set values are not two distinct values above 2^40")
    report = run_bitmap_probe(
        empty_list_source(fresh_a, fresh_b),
        timeout=LARGE_PROBE_TIMEOUT,
    )
    require_empty_snapshot(report)
    require_empty_snapshot(report, prefix="opened_")
    require_no_integer(report, "min")
    require_no_integer(report, "max")
    require_no_integer(report, "opened_min")
    require_no_integer(report, "opened_max")
    require_true(
        report,
        "first_exhausted",
        "second_exhausted",
        "bytes_same",
        "untouched",
        "control",
        "orig_has",
        "orig_extrema",
        "orig_not_b",
        "open_has",
        "open_not_a",
        "open_extrema",
        "released",
    )
    _require_polarity(report, "first_was_zero", False)
    _require_polarity(report, "second_was_zero", False)
    _require_polarity(report, "orig_empty", False)
    _require_polarity(report, "orig_still0", False)
    _require_polarity(report, "open_empty", False)
    _require_polarity(report, "open_still0", False)
    if require_int_field(report, "array_len") != 0:
        raise AssertionError("empty list allocated a non-empty value array")
    if require_int_field(report, "orig_card") != 1 or require_int_field(report, "open_card") != 1:
        raise AssertionError("a later set on the empty bitmap did not raise cardinality to 1")
    _require_shape(report)


def test_one_element_list_of_u64_maximum_contains_only_that_value():
    values = [U64_MAX]
    unique = [U64_MAX]
    report = run_bitmap_probe(
        sorted_build_source(
            values,
            unique,
            marker_a=U64_MAX,
            marker_b=U64_MAX - 1,
            absent=0,
        ),
        timeout=LARGE_PROBE_TIMEOUT,
    )
    _require_built(
        report,
        values,
        unique,
        contains0=False,
        has_a=True,
        has_b=False,
        more=False,
    )
    if require_int_field(report, "card") != 1:
        raise AssertionError("one-element maximum list does not have cardinality 1")


def test_six_thousand_one_prefix_plus_scattered_matches_set_and_bytes():
    values, unique, hole = six_thousand_list_f09()
    window_lo = 1 << 32
    window_hi = window_lo + (1 << 16) - 1
    if len(values) != 6000 or unique[0] == 0:
        raise HarnessError("six-thousand input is not the required shape")
    if window_lo not in unique or window_hi not in unique or hole in unique:
        raise HarnessError("six-thousand window lost an endpoint or the hole is present")
    report = run_bitmap_probe(
        sorted_build_source(
            values,
            unique,
            marker_a=window_lo,
            marker_b=window_hi,
            absent=0,
            hole=hole,
            want_hole=True,
        ),
        timeout=LARGE_PROBE_TIMEOUT,
    )
    _require_built(
        report,
        values,
        unique,
        contains0=False,
        has_a=True,
        has_b=True,
        more=True,
    )
    if require_int_field(report, "card") == 6000:
        raise AssertionError("duplicates in the 6000-element list increased cardinality")
    if require_int_field(report, "card") != len(unique):
        raise AssertionError("cardinality is not the distinct count")


def test_five_thousand_prefix_distinct_values_cardinality_extrema_and_membership():
    values = five_thousand_prefix_values_f09()
    absent = absent_beside_prefix_series_f09(values, 1000)
    if values[0] != 0 or values[-1] != ((4999 << 32) + 999) or 1 in values:
        raise HarnessError("frozen 5000-value series does not match the named formula")
    if absent in values or absent == 1:
        raise HarnessError("absent high-prefix value is in the series or is 1")
    report = run_bitmap_probe(
        sorted_build_source(
            values,
            values,
            marker_a=1,
            marker_b=absent,
            absent=1,
            hole=absent,
            want_hole=True,
        ),
        timeout=LARGE_PROBE_TIMEOUT,
    )
    _require_built(
        report,
        values,
        values,
        contains0=True,
        has_a=False,
        has_b=False,
        more=True,
    )
    if require_int_field(report, "card") != 5000:
        raise AssertionError("5000 prefix-distinct values did not yield cardinality 5000")


def test_unpublished_prefix_distinct_count_and_modulus():
    count, modulus, values, absent = unpublished_prefix_series_f09()
    if count == 5000 or modulus == 1000 or values[0] != 0 or 1 in values:
        raise HarnessError("unpublished series reused the named count or modulus")
    if absent in values or absent == 1:
        raise HarnessError("absent value is in the unpublished series or is 1")
    report = run_bitmap_probe(
        sorted_build_source(
            values,
            values,
            marker_a=1,
            marker_b=absent,
            absent=1,
            hole=absent,
            want_hole=True,
        ),
        timeout=LARGE_PROBE_TIMEOUT,
    )
    _require_built(
        report,
        values,
        values,
        contains0=True,
        has_a=False,
        has_b=False,
        more=True,
    )
    if require_int_field(report, "card") != count:
        raise AssertionError("cardinality is not the unpublished count")


def test_unpublished_consecutive_thousands_beside_many_prefixes():
    values, unique, start, run_len, hole = consecutive_thousands_list_f09()
    tail = start + run_len - 1
    if unique[0] != start or start in (0, 1 << 32) or tail not in unique or hole in unique:
        raise HarnessError("consecutive input is not the required shape")
    if not run_len < len(unique) < len(values):
        raise HarnessError("consecutive duplicates do not change the distinct count")
    report = run_bitmap_probe(
        sorted_build_source(
            values,
            unique,
            marker_a=tail,
            marker_b=start,
            absent=0,
            hole=hole,
            want_hole=True,
        ),
        timeout=LARGE_PROBE_TIMEOUT,
    )
    _require_built(
        report,
        values,
        unique,
        contains0=False,
        has_a=True,
        has_b=True,
        more=True,
    )
    if require_int_field(report, "card") != len(unique):
        raise AssertionError("cardinality is not the distinct count")
    if require_int_field(report, "card") <= run_len:
        raise AssertionError("prefixes above the consecutive run were dropped")
    if require_int_field(report, "card") >= len(values):
        raise AssertionError("a duplicate increased cardinality")


def test_sorted_list_path_performs_no_file_or_network_io():
    values, unique, _absent = mixed_unpublished_list_f09()
    honest = io_honest_source(values, unique)
    vandal = wrap_sorted_probe(
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
    net_vandal = wrap_sorted_probe(
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
            raise HarnessError(f"sorted-list I/O probe exited {run.returncode}\n{run.stderr_text}")
        created = product_created_files(before=before, roots=roots, ignore_names=harness_names)
        if created != set():
            raise AssertionError(f"sorted-list path wrote files: {created}")

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
            raise HarnessError(
                f"traced sorted-list probe exited {run_w.returncode}\n{run_w.stderr_text}"
            )
        if file_write_syscalls_in_trace(writes) != []:
            raise AssertionError(f"sorted-list path wrote through syscalls: {writes}")
        if unexpected_file_reads_in_trace(reads) != []:
            raise AssertionError(f"sorted-list path read unexpected files: {reads}")

        honest_argv = [str(ws.resolve("honest"))]
        net_argv = [str(ws.resolve("net"))]
        run_n, hits = run_traced_arch_network(ws, honest_argv, timeout=DEFAULT_TIMEOUT)
        if run_n.returncode != 0:
            raise HarnessError(
                f"traced sorted-list network probe exited {run_n.returncode}\n{run_n.stderr_text}"
            )
        if network_syscalls_in_trace(hits) != []:
            raise AssertionError(f"sorted-list path opened a network syscall: {hits}")
        direct_n, direct_hits = trace_network_argv(
            honest_argv, cwd=ws.path, env=ws.env, timeout=DEFAULT_TIMEOUT
        )
        if direct_n.returncode != 0:
            raise HarnessError(
                f"direct network trace exited {direct_n.returncode}\n{direct_n.stderr_text}"
            )
        if network_syscalls_in_trace(direct_hits) != []:
            raise AssertionError(f"sorted-list path opened a network syscall: {direct_hits}")

        run_nv, vandal_hits = run_traced_arch_network(ws, net_argv, timeout=DEFAULT_TIMEOUT)
        if run_nv.returncode != 0:
            raise HarnessError(
                f"network positive control exited {run_nv.returncode}\n{run_nv.stderr_text}"
            )
        if not network_syscalls_in_trace(vandal_hits):
            raise AssertionError("network positive control observed nothing")
        direct_nv, direct_vandal = trace_arch_network_syscalls(
            net_argv, cwd=ws.path, env=ws.env, timeout=DEFAULT_TIMEOUT
        )
        if direct_nv.returncode != 0:
            raise HarnessError(
                f"direct network positive control exited {direct_nv.returncode}\n{direct_nv.stderr_text}"
            )
        if not network_syscalls_in_trace(direct_vandal):
            raise AssertionError("direct network positive control observed nothing")
        run_old, old_hits = run_traced_network(ws, net_argv, timeout=DEFAULT_TIMEOUT)
        if run_old.returncode != 0:
            raise HarnessError(
                f"legacy network positive control exited {run_old.returncode}\n{run_old.stderr_text}"
            )
        if not network_syscalls_in_trace(old_hits):
            raise AssertionError("legacy network positive control observed nothing")


# ---------------------------------------------------------------------------
# Sorted lists that give one prefix 2^k - 1, 2^k or 2^k + 1 distinct values
# ---------------------------------------------------------------------------


def test_sorted_list_giving_one_prefix_each_population_builds_exactly_those_values():
    # For each population c: a non-decreasing list holding c distinct values
    # of one prefix (some repeated) and the two values just outside it, with
    # the last one repeated. The built bitmap holds exactly the distinct
    # values, matches setting each element in turn, and round-trips through
    # its buffer.
    report = run_block_sweep(
        r"""
    const list = try init.gpa.alloc(u64, 65536 + 65536 / 3 + 4);
    defer init.gpa.free(list);
    var ok = true;
    var same_as_set = true;
    var round_trip = true;
    var seen: u64 = 0;
    for (checkpoints) |c| {
        var m: usize = 0;
        list[m] = block.below;
        m += 1;
        var i: u64 = 0;
        while (i < c) : (i += 1) {
            list[m] = block.val(i);
            m += 1;
            if (i % 3 == 1) {
                list[m] = block.val(i);
                m += 1;
            }
        }
        list[m] = block.above;
        list[m + 1] = block.above;
        m += 2;
        const vals = list[0..m];
        std.mem.sort(u64, vals, {}, std.sort.asc(u64));
        var bm = try klyvmap.Bitmap.fromSortedList(allocator, vals);
        defer bm.deinit();
        ok = ok and bm.getCardinality() == c + 2 and block.members(&bm, 0, c, true) and block.walk(&bm, 0, c, true);
        var by_set = try klyvmap.Bitmap.init(allocator);
        defer by_set.deinit();
        for (vals) |v| _ = try by_set.set(v);
        const a1 = try bm.toArray(allocator);
        defer allocator.free(a1);
        const a2 = try by_set.toArray(allocator);
        defer allocator.free(a2);
        same_as_set = same_as_set and std.mem.eql(u64, a1, a2);
        const copy = try bm.toBufferCopy(allocator);
        defer allocator.free(copy);
        var opened = klyvmap.Bitmap.fromBuffer(allocator, copy, .borrow) catch return error.OpenFailed;
        defer opened.deinit();
        round_trip = round_trip and std.mem.eql(u8, opened.toBuffer(), bm.toBuffer()) and block.walk(&opened, 0, c, true);
        seen += 1;
    }
    try emitJson(init, init.gpa,
        "{{\"ok\":{s},\"same_as_set\":{s},\"round_trip\":{s},\"seen\":{d}}}",
        .{ jsonBool(ok), jsonBool(same_as_set), jsonBool(round_trip), seen },
    );
"""
    )
    require_sweep_true(report, "ok", "same_as_set", "round_trip")
    require_sweep_seen(report, "seen", len(block_checkpoints()))
