# feature: F07
"""Acceptance: batch compress and expand with derived names and continuation."""

from __future__ import annotations

from pathlib import Path

from F01_helpers import (
    derived_batch_archive,
    jobs_trailing_value,
    place_vorbis,
    require_file_access,
    require_ok,
    require_path_absent,
    require_refusal,
    run_expect_usage_no_archive,
    run_product,
    unique_name,
    unknown_verb,
)
from F02_helpers import (
    complete_packets,
    place_vorbis_without_ogg_suffix,
    require_no_usable_compress_dest,
    require_no_usable_expand_dest,
)
from F03_helpers import opus_head_fields, place_opus_classified
from F04_helpers import _prove_family0
from F05_helpers import stderr_names_input
from F07_helpers import (
    derived_batch_expand,
    place_non_ogg_sized,
    place_runtime_vorbis,
    place_vorbis_in_subdir,
    prepare_batch_archive,
    require_batch_summary,
    require_compress_member,
    require_expand_restored,
    require_no_batch_summary,
    scramble_or_remove,
    stderr_path_index,
    unrelated_pair,
)
from _harness import HarnessError, workspace

_REFUSE_LARGE = 65536
_REFUSE_SMALL = 64
_REFUSE_MID = 4096


# ---------------------------------------------------------------------------
# A. Three distinct Vorbis, --jobs=2, three .orp, exit 0
# ---------------------------------------------------------------------------


def test_batch_compress_three_vorbis_with_jobs_two():
    with workspace() as ws:
        f1 = place_vorbis(ws, "a")
        f2 = place_vorbis(ws, "b")
        f3 = place_runtime_vorbis(ws)
        result = run_product(ws, ["-1", "--jobs=2", "-b", "e", f1, f2, f3])
        require_ok(result)
        for src in (f1, f2, f3):
            dest = derived_batch_archive(src)
            assert dest == f"{src}.orp", (
                f"batch compress dest for {src!r} is not input-plus-.orp: {dest!r}"
            )
            require_compress_member(ws, src)
        print("[F07] A three Vorbis --jobs=2 wrote three .orp", flush=True)


# ---------------------------------------------------------------------------
# B. Batch expand those .orp after scrambling the stripped paths
# ---------------------------------------------------------------------------


def test_batch_expand_strips_orp_and_restores():
    with workspace() as ws:
        sources = [
            place_vorbis(ws, "a"),
            place_vorbis(ws, "b"),
            place_runtime_vorbis(ws),
        ]
        saved = {src: ws.read_bytes(src) for src in sources}
        packed = run_product(ws, ["-1", "-b", "e", *sources])
        require_ok(packed)
        archives = [derived_batch_archive(src) for src in sources]
        for src in sources:
            scramble_or_remove(ws, src, saved[src])
        result = run_product(ws, ["--batch", "d", *archives])
        require_ok(result)
        for src, arc in zip(sources, archives):
            dest = derived_batch_expand(arc)
            assert dest == src, (
                f"batch expand of {arc!r} must strip trailing .orp to {src!r}, "
                f"got {dest!r}"
            )
            require_expand_restored(ws, dest, saved[src])
        print("[F07] B batch expand restored three scrambled sources", flush=True)


# ---------------------------------------------------------------------------
# C. No trailing .orp → append .out; mid-name .orp is not stripped
# ---------------------------------------------------------------------------


def test_batch_expand_without_orp_suffix_appends_out():
    with workspace() as ws:
        src = place_vorbis(ws, "a")
        src_bytes = ws.read_bytes(src)
        arc = unique_name("arc-plain")
        assert not arc.endswith(".orp"), f"plain archive name ends with .orp: {arc!r}"
        written = run_product(ws, ["-1", "e", src, arc])
        require_ok(written)
        result = run_product(ws, ["-b", "d", arc])
        require_ok(result)
        dest = derived_batch_expand(arc)
        assert dest == f"{arc}.out", (
            f"expand of a name without trailing .orp must append .out, got {dest!r}"
        )
        require_expand_restored(ws, dest, src_bytes)

        src2 = place_runtime_vorbis(ws)
        src2_bytes = ws.read_bytes(src2)
        ident = unique_name("id")
        arc2 = f"{ident}.orp.bak"
        assert not arc2.endswith(".orp"), (
            f".orp.bak archive name still has a trailing .orp: {arc2!r}"
        )
        written2 = run_product(ws, ["-1", "e", src2, arc2])
        require_ok(written2)
        result2 = run_product(ws, ["-b", "d", arc2])
        require_ok(result2)
        dest2 = derived_batch_expand(arc2)
        assert dest2 == f"{arc2}.out", (
            f"expand of {arc2!r} must append .out, not strip a mid-name .orp; "
            f"got {dest2!r}"
        )
        assert dest2.endswith(".orp.bak.out"), (
            f"expected trailing .orp.bak.out, got {dest2!r}"
        )
        require_expand_restored(ws, dest2, src2_bytes)
        print("[F07] C append .out; mid .orp not stripped", flush=True)


# ---------------------------------------------------------------------------
# D. Append .orp (no extension replace); multi-file subdir dest lives beside
#    the input; nested .orp batch-expands back to the nested original path
# ---------------------------------------------------------------------------


def test_batch_compress_appends_orp_beside_input():
    with workspace() as ws:
        src = place_vorbis_without_ogg_suffix(ws, "a")
        assert not src.endswith(".ogg") and not src.endswith(".opus"), (
            f"no-suffix Vorbis still has a codec suffix: {src!r}"
        )
        result = run_product(ws, ["-1", "-b", "e", src])
        require_ok(result)
        dest = derived_batch_archive(src)
        assert dest == f"{src}.orp", (
            f"no-suffix compress dest must be input-plus-.orp, got {dest!r}"
        )
        require_compress_member(ws, src)

        root = place_vorbis(ws, "a")
        nested = place_vorbis_in_subdir(ws, "b")
        root_saved = ws.read_bytes(root)
        nested_saved = ws.read_bytes(nested)
        assert "/" in nested, f"subdir member is not nested: {nested!r}"
        multi = run_product(ws, ["-1", "-b", "e", root, nested])
        require_ok(multi)
        nested_dest = derived_batch_archive(nested)
        root_dest = derived_batch_archive(root)
        assert nested_dest == f"{nested}.orp", (
            f"subdir dest must be dir/src.orp, got {nested_dest!r}"
        )
        assert root_dest == f"{root}.orp", (
            f"root dest must be input-plus-.orp, got {root_dest!r}"
        )
        require_compress_member(ws, root)
        require_compress_member(ws, nested)

        scramble_or_remove(ws, nested, nested_saved)
        scramble_or_remove(ws, root, root_saved)
        expanded = run_product(ws, ["-b", "d", nested_dest, root_dest])
        require_ok(expanded)
        nested_out = derived_batch_expand(nested_dest)
        root_out = derived_batch_expand(root_dest)
        assert nested_out == nested, (
            f"nested batch expand must recover {nested!r}, not cwd/basename; "
            f"got {nested_out!r}"
        )
        assert nested_out != Path(nested).name, (
            f"nested expand dest collapsed to a cwd basename: {nested_out!r}"
        )
        assert root_out == root, (
            f"root batch expand must recover {root!r}, got {root_out!r}"
        )
        require_expand_restored(ws, nested_out, nested_saved)
        require_expand_restored(ws, root_out, root_saved)
        print(
            "[F07] D append .orp beside input; nested -b d restores dir/src",
            flush=True,
        )


# ---------------------------------------------------------------------------
# E. Omitted --jobs still processes every file; -j N is accepted;
#    --jobs=2 is accepted on batch expand
# ---------------------------------------------------------------------------


def test_omitted_jobs_and_short_j_are_accepted():
    with workspace() as ws:
        a = place_vorbis(ws, "a")
        b = place_vorbis(ws, "b")
        omitted = run_product(ws, ["-1", "-b", "e", a, b])
        require_ok(omitted)
        require_compress_member(ws, a)
        require_compress_member(ws, b)

        c = place_runtime_vorbis(ws)
        d = place_vorbis(ws, "a")
        short_j = run_product(ws, ["-1", "-j", "2", "-b", "e", c, d])
        require_ok(short_j)
        require_compress_member(ws, c)
        require_compress_member(ws, d)

        src_e, saved_e, arc_e = prepare_batch_archive(ws)
        src_f, saved_f, arc_f = prepare_batch_archive(ws)
        scramble_or_remove(ws, src_e, saved_e)
        scramble_or_remove(ws, src_f, saved_f)
        jobs_expand = run_product(ws, ["--jobs=2", "-b", "d", arc_e, arc_f])
        require_ok(jobs_expand)
        require_expand_restored(ws, derived_batch_expand(arc_e), saved_e)
        require_expand_restored(ws, derived_batch_expand(arc_f), saved_f)
        print(
            "[F07] E omitted --jobs, -j 2 compress, and --jobs=2 expand",
            flush=True,
        )


# ---------------------------------------------------------------------------
# F. --jobs=1 compress of two non-Ogg: larger path appears on stderr first
# ---------------------------------------------------------------------------


def test_larger_input_appears_on_stderr_before_smaller_when_jobs_is_one():
    with workspace() as ws:
        small_name, large_name = unrelated_pair("sm", "lg")
        small = place_non_ogg_sized(ws, _REFUSE_SMALL, rel=f"{small_name}.bin")
        large = place_non_ogg_sized(ws, _REFUSE_MID, rel=f"{large_name}.bin")
        assert small not in large and large not in small
        compress = run_product(ws, ["--jobs=1", "-b", "e", small, large])
        require_refusal(compress)
        err = compress.stderr_text
        stderr_names_input(err, large)
        stderr_names_input(err, small)
        large_at = stderr_path_index(err, large)
        small_at = stderr_path_index(err, small)
        assert large_at < small_at, (
            f"with --jobs=1 the larger path must appear on stderr before the "
            f"smaller; large_at={large_at} small_at={small_at}; stderr={err!r}"
        )
        require_no_usable_compress_dest(ws, derived_batch_archive(small))
        require_no_usable_compress_dest(ws, derived_batch_archive(large))
        print(
            "[F07] F larger path precedes smaller on stderr at jobs=1 compress",
            flush=True,
        )


# ---------------------------------------------------------------------------
# G. Continue after a refusal; mixed refusal exits 1; success dest is valid
# ---------------------------------------------------------------------------


def test_batch_continues_after_refusal_and_exits_one():
    with workspace() as ws:
        refuse = place_non_ogg_sized(ws, _REFUSE_LARGE)
        valid = place_vorbis(ws, "a")
        assert ws.file_size(refuse) > ws.file_size(valid)
        result = run_product(ws, ["--jobs=1", "-1", "-b", "e", refuse, valid])
        require_refusal(result)
        require_compress_member(ws, valid)
        require_no_usable_compress_dest(ws, derived_batch_archive(refuse))
        print("[F07] G compress continues after refusal and exits 1", flush=True)


def test_batch_expand_continues_after_refusal():
    with workspace() as ws:
        src, saved, arc = prepare_batch_archive(ws)
        scramble_or_remove(ws, src, saved)
        refuse = place_non_ogg_sized(ws, _REFUSE_LARGE)
        result = run_product(ws, ["--jobs=1", "-b", "d", refuse, arc])
        require_refusal(result)
        require_expand_restored(ws, derived_batch_expand(arc), saved)
        require_no_usable_expand_dest(
            ws, derived_batch_expand(refuse), ws.read_bytes(refuse)
        )
        print("[F07] G expand continues after refusal and exits 1", flush=True)


# ---------------------------------------------------------------------------
# G2. After a file-access error, remaining files still run (compress + expand)
# ---------------------------------------------------------------------------


def test_batch_continues_after_file_access_error():
    with workspace() as ws:
        missing = unique_name("missing")
        valid_a = place_vorbis(ws, "a")
        valid_b = place_runtime_vorbis(ws)
        result = run_product(
            ws, ["--jobs=1", "-1", "-b", "e", missing, valid_a, valid_b]
        )
        require_file_access(result)
        require_compress_member(ws, valid_a)
        require_compress_member(ws, valid_b)
        print(
            "[F07] G2 compress continues after file-access; remaining dests written",
            flush=True,
        )


def test_batch_expand_continues_after_file_access_error():
    with workspace() as ws:
        src_a, saved_a, arc_a = prepare_batch_archive(ws)
        src_b, saved_b, arc_b = prepare_batch_archive(ws)
        scramble_or_remove(ws, src_a, saved_a)
        scramble_or_remove(ws, src_b, saved_b)
        missing = unique_name("missing")
        result = run_product(ws, ["--jobs=1", "-b", "d", missing, arc_a, arc_b])
        require_file_access(result)
        require_expand_restored(ws, derived_batch_expand(arc_a), saved_a)
        require_expand_restored(ws, derived_batch_expand(arc_b), saved_b)
        print(
            "[F07] G2 expand continues after file-access; remaining dests restored",
            flush=True,
        )


# ---------------------------------------------------------------------------
# H. Mixed-failure stderr distinguishable from all-success (three groups)
# ---------------------------------------------------------------------------


def test_mixed_failure_stderr_counts_differ_from_all_success():
    with workspace() as ws:
        # --- compress refusal group ---
        ok_a = place_vorbis(ws, "a")
        ok_b = place_vorbis(ws, "b")
        ok_run = run_product(ws, ["--jobs=1", "-1", "-b", "e", ok_a, ok_b])
        require_ok(ok_run)
        require_compress_member(ws, ok_a)
        require_compress_member(ws, ok_b)
        print(
            f"[F07] compress all-success stderr={ok_run.stderr_text!r}",
            flush=True,
        )

        ok3_a = place_vorbis(ws, "a")
        ok3_b = place_vorbis(ws, "b")
        ok3_c = place_runtime_vorbis(ws)
        ok3_run = run_product(
            ws, ["--jobs=1", "-1", "-b", "e", ok3_a, ok3_b, ok3_c]
        )
        require_ok(ok3_run)
        require_compress_member(ws, ok3_a)
        require_compress_member(ws, ok3_b)
        require_compress_member(ws, ok3_c)

        ref_2a = place_non_ogg_sized(ws, _REFUSE_MID)
        ref_2b = place_non_ogg_sized(ws, _REFUSE_MID)
        mix_2of2 = run_product(ws, ["--jobs=1", "-1", "-b", "e", ref_2a, ref_2b])
        require_refusal(mix_2of2)
        require_no_usable_compress_dest(ws, derived_batch_archive(ref_2a))
        require_no_usable_compress_dest(ws, derived_batch_archive(ref_2b))

        ref_3 = place_non_ogg_sized(ws, _REFUSE_MID)
        mix_v2 = place_vorbis(ws, "a")
        mix_v3 = place_runtime_vorbis(ws)
        mix_1of3 = run_product(
            ws, ["--jobs=1", "-1", "-b", "e", ref_3, mix_v2, mix_v3]
        )
        require_refusal(mix_1of3)
        require_compress_member(ws, mix_v2)
        require_compress_member(ws, mix_v3)
        require_no_usable_compress_dest(ws, derived_batch_archive(ref_3))

        ref_1 = place_non_ogg_sized(ws, _REFUSE_MID)
        mix_v = place_runtime_vorbis(ws)
        mix_1of2 = run_product(ws, ["--jobs=1", "-1", "-b", "e", ref_1, mix_v])
        require_refusal(mix_1of2)
        require_compress_member(ws, mix_v)
        require_no_usable_compress_dest(ws, derived_batch_archive(ref_1))
        print(
            f"[F07] compress mixed 1-of-2 stderr={mix_1of2.stderr_text!r}",
            flush=True,
        )
        print(
            f"[F07] compress 2-of-2 stderr={mix_2of2.stderr_text!r} "
            f"1-of-3 stderr={mix_1of3.stderr_text!r}",
            flush=True,
        )
        assert mix_1of2.stderr_text != ok_run.stderr_text, (
            "when at least one file fails, standard error must distinguish "
            "the mixed run from all-success"
        )
        require_no_batch_summary(ok_run, what="compress refusal all-success 2")
        require_no_batch_summary(ok3_run, what="compress refusal all-success 3")
        require_batch_summary(mix_1of2, 1, 2, what="compress refusal 1 of 2")
        require_batch_summary(mix_2of2, 2, 2, what="compress refusal 2 of 2")
        require_batch_summary(mix_1of3, 1, 3, what="compress refusal 1 of 3")

        # --- missing-path group (status 3) ---
        miss_ok_a = place_vorbis(ws, "a")
        miss_ok_b = place_vorbis(ws, "b")
        miss_ok = run_product(ws, ["--jobs=1", "-1", "-b", "e", miss_ok_a, miss_ok_b])
        require_ok(miss_ok)
        require_compress_member(ws, miss_ok_a)
        require_compress_member(ws, miss_ok_b)
        print(
            f"[F07] missing all-success stderr={miss_ok.stderr_text!r}",
            flush=True,
        )

        miss_ok3_a = place_vorbis(ws, "a")
        miss_ok3_b = place_vorbis(ws, "b")
        miss_ok3_c = place_runtime_vorbis(ws)
        miss_ok3 = run_product(
            ws, ["--jobs=1", "-1", "-b", "e", miss_ok3_a, miss_ok3_b, miss_ok3_c]
        )
        require_ok(miss_ok3)
        require_compress_member(ws, miss_ok3_a)
        require_compress_member(ws, miss_ok3_b)
        require_compress_member(ws, miss_ok3_c)

        miss_2a = unique_name("missing")
        miss_2b = unique_name("missing")
        miss_2of2 = run_product(ws, ["--jobs=1", "-1", "-b", "e", miss_2a, miss_2b])
        require_file_access(miss_2of2)

        miss_3 = unique_name("missing")
        miss_v2 = place_vorbis(ws, "a")
        miss_v3 = place_runtime_vorbis(ws)
        miss_1of3 = run_product(
            ws, ["--jobs=1", "-1", "-b", "e", miss_3, miss_v2, miss_v3]
        )
        require_file_access(miss_1of3)
        require_compress_member(ws, miss_v2)
        require_compress_member(ws, miss_v3)

        miss_1 = unique_name("missing")
        miss_v = place_runtime_vorbis(ws)
        miss_1of2 = run_product(ws, ["--jobs=1", "-1", "-b", "e", miss_1, miss_v])
        require_file_access(miss_1of2)
        assert miss_1of2.returncode == 3, (
            "a batch of a missing path and a valid file exits 3; "
            f"got {miss_1of2.returncode}; stderr={miss_1of2.stderr!r}"
        )
        require_compress_member(ws, miss_v)
        print(
            f"[F07] missing mixed 1-of-2 stderr={miss_1of2.stderr_text!r} "
            f"2-of-2 stderr={miss_2of2.stderr_text!r} "
            f"1-of-3 stderr={miss_1of3.stderr_text!r}",
            flush=True,
        )
        assert miss_1of2.stderr_text != miss_ok.stderr_text, (
            "when at least one file fails, standard error must distinguish "
            "the mixed run from all-success"
        )
        require_no_batch_summary(miss_ok, what="missing path all-success 2")
        require_no_batch_summary(miss_ok3, what="missing path all-success 3")
        require_batch_summary(miss_1of2, 1, 2, what="missing path 1 of 2")
        require_batch_summary(miss_2of2, 2, 2, what="missing path 2 of 2")
        require_batch_summary(miss_1of3, 1, 3, what="missing path 1 of 3")

        # --- expand refusal group ---
        exp_src_a, exp_saved_a, exp_arc_a = prepare_batch_archive(ws)
        exp_src_b, exp_saved_b, exp_arc_b = prepare_batch_archive(ws)
        scramble_or_remove(ws, exp_src_a, exp_saved_a)
        scramble_or_remove(ws, exp_src_b, exp_saved_b)
        exp_ok = run_product(ws, ["--jobs=1", "-b", "d", exp_arc_a, exp_arc_b])
        require_ok(exp_ok)
        require_expand_restored(ws, derived_batch_expand(exp_arc_a), exp_saved_a)
        require_expand_restored(ws, derived_batch_expand(exp_arc_b), exp_saved_b)
        print(
            f"[F07] expand all-success stderr={exp_ok.stderr_text!r}",
            flush=True,
        )

        exp_src_ok3a, exp_saved_ok3a, exp_arc_ok3a = prepare_batch_archive(ws)
        exp_src_ok3b, exp_saved_ok3b, exp_arc_ok3b = prepare_batch_archive(ws)
        exp_src_ok3c, exp_saved_ok3c, exp_arc_ok3c = prepare_batch_archive(ws)
        scramble_or_remove(ws, exp_src_ok3a, exp_saved_ok3a)
        scramble_or_remove(ws, exp_src_ok3b, exp_saved_ok3b)
        scramble_or_remove(ws, exp_src_ok3c, exp_saved_ok3c)
        exp_ok3 = run_product(
            ws, ["--jobs=1", "-b", "d", exp_arc_ok3a, exp_arc_ok3b, exp_arc_ok3c]
        )
        require_ok(exp_ok3)
        require_expand_restored(
            ws, derived_batch_expand(exp_arc_ok3a), exp_saved_ok3a
        )
        require_expand_restored(
            ws, derived_batch_expand(exp_arc_ok3b), exp_saved_ok3b
        )
        require_expand_restored(
            ws, derived_batch_expand(exp_arc_ok3c), exp_saved_ok3c
        )

        exp_r2a = place_non_ogg_sized(ws, _REFUSE_MID)
        exp_r2b = place_non_ogg_sized(ws, _REFUSE_MID)
        exp_2of2 = run_product(ws, ["--jobs=1", "-b", "d", exp_r2a, exp_r2b])
        require_refusal(exp_2of2)
        require_no_usable_expand_dest(
            ws, derived_batch_expand(exp_r2a), ws.read_bytes(exp_r2a)
        )
        require_no_usable_expand_dest(
            ws, derived_batch_expand(exp_r2b), ws.read_bytes(exp_r2b)
        )

        exp_r3 = place_non_ogg_sized(ws, _REFUSE_MID)
        exp_src_d, exp_saved_d, exp_arc_d = prepare_batch_archive(ws)
        exp_src_e, exp_saved_e, exp_arc_e = prepare_batch_archive(ws)
        scramble_or_remove(ws, exp_src_d, exp_saved_d)
        scramble_or_remove(ws, exp_src_e, exp_saved_e)
        exp_1of3 = run_product(
            ws, ["--jobs=1", "-b", "d", exp_r3, exp_arc_d, exp_arc_e]
        )
        require_refusal(exp_1of3)
        require_expand_restored(ws, derived_batch_expand(exp_arc_d), exp_saved_d)
        require_expand_restored(ws, derived_batch_expand(exp_arc_e), exp_saved_e)
        require_no_usable_expand_dest(
            ws, derived_batch_expand(exp_r3), ws.read_bytes(exp_r3)
        )

        exp_refuse = place_non_ogg_sized(ws, _REFUSE_MID)
        exp_src_c, exp_saved_c, exp_arc_c = prepare_batch_archive(ws)
        scramble_or_remove(ws, exp_src_c, exp_saved_c)
        exp_1of2 = run_product(ws, ["--jobs=1", "-b", "d", exp_refuse, exp_arc_c])
        require_refusal(exp_1of2)
        require_expand_restored(ws, derived_batch_expand(exp_arc_c), exp_saved_c)
        require_no_usable_expand_dest(
            ws, derived_batch_expand(exp_refuse), ws.read_bytes(exp_refuse)
        )
        print(
            f"[F07] expand mixed 1-of-2 stderr={exp_1of2.stderr_text!r} "
            f"2-of-2 stderr={exp_2of2.stderr_text!r} "
            f"1-of-3 stderr={exp_1of3.stderr_text!r}",
            flush=True,
        )
        assert exp_1of2.stderr_text != exp_ok.stderr_text, (
            "when at least one file fails, standard error must distinguish "
            "the mixed run from all-success"
        )
        require_no_batch_summary(exp_ok, what="expand refusal all-success 2")
        require_no_batch_summary(exp_ok3, what="expand refusal all-success 3")
        require_batch_summary(exp_1of2, 1, 2, what="expand refusal 1 of 2")
        require_batch_summary(exp_2of2, 2, 2, what="expand refusal 2 of 2")
        require_batch_summary(exp_1of3, 1, 3, what="expand refusal 1 of 3")
        print(
            "[F07] H mixed stderr distinguishable from all-success; "
            "dedicated summary field answers failed and attempted counts",
            flush=True,
        )


# ---------------------------------------------------------------------------
# I. Missing path + valid file: exit 3; valid member still processed
# ---------------------------------------------------------------------------


def test_missing_path_in_batch_exits_three_and_still_encodes_valid():
    with workspace() as ws:
        missing = unique_name("missing")
        valid = place_vorbis(ws, "a")
        result = run_product(ws, ["-1", "-b", "e", missing, valid])
        require_file_access(result)
        assert result.returncode == 3, (
            "a batch of a missing path and a valid file exits 3; "
            f"got {result.returncode}; stderr={result.stderr!r}"
        )
        require_compress_member(ws, valid)
        print("[F07] I compress missing+valid exits 3 and encodes valid", flush=True)


def test_missing_path_on_batch_expand_exits_three_and_still_expands():
    with workspace() as ws:
        src, saved, arc = prepare_batch_archive(ws)
        scramble_or_remove(ws, src, saved)
        missing = unique_name("missing")
        result = run_product(ws, ["--jobs=1", "-b", "d", missing, arc])
        require_file_access(result)
        assert result.returncode == 3, (
            "a batch of a missing path and a valid file exits 3; "
            f"got {result.returncode}; stderr={result.stderr!r}"
        )
        require_expand_restored(ws, derived_batch_expand(arc), saved)
        print("[F07] I expand missing+valid exits 3 and expands valid", flush=True)


# ---------------------------------------------------------------------------
# J. Exit status is the highest nonzero (refusal 1 + missing 3 → 3)
# ---------------------------------------------------------------------------


def test_batch_exit_is_highest_nonzero_status():
    with workspace() as ws:
        refuse = place_non_ogg_sized(ws, _REFUSE_MID)
        missing = unique_name("missing")
        valid = place_vorbis(ws, "a")
        result = run_product(ws, ["-1", "-b", "e", refuse, missing, valid])
        require_file_access(result)
        require_compress_member(ws, valid)
        require_no_usable_compress_dest(ws, derived_batch_archive(refuse))
        print("[F07] J refuse+missing+valid exits 3", flush=True)


# ---------------------------------------------------------------------------
# K. Batch with a verb other than e/d is a usage error
# ---------------------------------------------------------------------------


def test_batch_with_verb_other_than_e_or_d_is_usage_error():
    with workspace() as ws:
        baseline = place_vorbis(ws, "a")
        live = run_product(ws, ["-1", "-b", "e", baseline])
        assert live.returncode != 2, (
            f"live baseline -b e must not be a usage error; exit={live.returncode}"
        )
        require_ok(live)
        require_compress_member(ws, baseline)

        run_expect_usage_no_archive(ws, ["-b", "e"])
        run_expect_usage_no_archive(ws, ["--batch", "d"])

        dump_src = place_vorbis(ws, "b")
        run_expect_usage_no_archive(ws, ["-b", "dump", dump_src])
        require_path_absent(ws, derived_batch_archive(dump_src))

        pages_src = place_runtime_vorbis(ws)
        run_expect_usage_no_archive(ws, ["-b", "pages", pages_src])
        require_path_absent(ws, derived_batch_archive(pages_src))

        unknown_src = place_vorbis(ws, "a")
        run_expect_usage_no_archive(ws, ["-b", unknown_verb(), unknown_src])
        require_path_absent(ws, derived_batch_archive(unknown_src))
        print("[F07] K no-path batch and -b dump / pages / unknown verb are usage errors", flush=True)


# ---------------------------------------------------------------------------
# L. Non-integer --jobs on a batch shape is a usage error
# ---------------------------------------------------------------------------


def test_non_integer_jobs_on_batch_is_usage_error():
    with workspace() as ws:
        baseline = place_vorbis(ws, "a")
        live = run_product(ws, ["--jobs=1", "-1", "-b", "e", baseline])
        assert live.returncode != 2, (
            f"live baseline --jobs=1 -b e must not be a usage error; "
            f"exit={live.returncode}"
        )
        require_ok(live)
        require_compress_member(ws, baseline)

        zero_src = place_vorbis(ws, "b")
        run_expect_usage_no_archive(ws, ["--jobs=0", "-b", "e", zero_src])
        require_path_absent(ws, derived_batch_archive(zero_src))

        victim = place_runtime_vorbis(ws)
        trailer = jobs_trailing_value()
        run_expect_usage_no_archive(ws, [f"--jobs={trailer}", "-b", "e", victim])
        require_path_absent(ws, derived_batch_archive(victim))
        print(
            f"[F07] L --jobs=0 and --jobs={trailer} on batch are usage errors",
            flush=True,
        )


# ---------------------------------------------------------------------------
# M. --no-mmap on the whole batch; Vorbis+Opus members are lossless
# ---------------------------------------------------------------------------


def test_no_mmap_and_mixed_codec_batch_are_lossless():
    with workspace() as ws:
        v1 = place_vorbis(ws, "a")
        v2 = place_vorbis(ws, "b")
        mapped = run_product(ws, ["--no-mmap", "-1", "-b", "e", v1, v2])
        require_ok(mapped)
        require_compress_member(ws, v1)
        require_compress_member(ws, v2)

        vorbis = place_runtime_vorbis(ws)
        opus = place_opus_classified(ws, "silk")
        opus_bytes = ws.read_bytes(opus)
        packets = complete_packets(opus_bytes)
        if not packets:
            raise HarnessError("classified Opus fixture has no complete packets")
        channels, family = opus_head_fields(packets[0])
        if family != 0:
            raise HarnessError(f"Opus member mapping family is {family}, not 0")
        if channels not in (1, 2):
            raise HarnessError(
                f"Opus member channel count is {channels}, not 1 or 2"
            )
        _prove_family0(opus_bytes, what="batch Opus member")
        mixed = run_product(ws, ["--no-mmap", "-1", "-b", "e", vorbis, opus])
        require_ok(mixed)
        require_compress_member(ws, vorbis)
        require_compress_member(ws, opus)
        print(
            "[F07] M --no-mmap batch and --no-mmap Vorbis+Opus batch are lossless",
            flush=True,
        )


# ---------------------------------------------------------------------------
# N. The Opus archive from a mixed batch must expand through -b d
# ---------------------------------------------------------------------------


def test_batch_expand_includes_opus_archive():
    with workspace() as ws:
        vorbis = place_runtime_vorbis(ws)
        opus = place_opus_classified(ws, "silk")
        opus_bytes = ws.read_bytes(opus)
        packets = complete_packets(opus_bytes)
        if not packets:
            raise HarnessError("classified Opus fixture has no complete packets")
        channels, family = opus_head_fields(packets[0])
        if family != 0 or channels not in (1, 2):
            raise HarnessError(
                f"Opus member family={family} channels={channels}, expected family 0 "
                f"and channels 1 or 2"
            )
        _prove_family0(opus_bytes, what="batch-expand Opus member")
        vorbis_saved = ws.read_bytes(vorbis)
        opus_saved = opus_bytes
        packed = run_product(ws, ["--no-mmap", "-1", "-b", "e", vorbis, opus])
        require_ok(packed)
        vorbis_arc = derived_batch_archive(vorbis)
        opus_arc = derived_batch_archive(opus)
        scramble_or_remove(ws, vorbis, vorbis_saved)
        scramble_or_remove(ws, opus, opus_saved)
        result = run_product(ws, ["--no-mmap", "-b", "d", vorbis_arc, opus_arc])
        require_ok(result)
        vorbis_dest = derived_batch_expand(vorbis_arc)
        opus_dest = derived_batch_expand(opus_arc)
        assert vorbis_dest == vorbis
        assert opus_dest == opus
        require_expand_restored(ws, vorbis_dest, vorbis_saved)
        require_expand_restored(ws, opus_dest, opus_saved)
        print(
            "[F07] N --no-mmap -b d restored the mixed batch including Opus",
            flush=True,
        )
