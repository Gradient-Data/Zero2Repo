# feature: F08
"""Acceptance: opt-in progress on standard error."""

from __future__ import annotations

from F01_helpers import (
    derived_batch_archive,
    place_non_ogg,
    place_vorbis,
    require_ok,
    require_refusal,
    run_product,
    unique_name,
)
from F02_helpers import require_no_usable_compress_dest
from F03_helpers import run_product_long
from F04_helpers import (
    _prove_family0,
    archive_bytes,
    opus_with_runtime_tags,
    vorbis_with_runtime_comment,
)
from F05_helpers import stderr_names_input
from F07_helpers import (
    derived_batch_expand,
    place_runtime_vorbis,
    require_compress_member,
    require_expand_restored,
    scramble_or_remove,
)
from F08_helpers import (
    require_archive_roundtrip,
    require_completion_contrast,
    require_completion_indication,
    require_names_on_distinct_newline_lines,
    require_names_visible_on_newline_records,
    require_newline_oriented_records,
    require_ok_written,
    require_written_dest,
)
from _harness import workspace


# ---------------------------------------------------------------------------
# A. Default off; --progress completion; identical archive bytes
# ---------------------------------------------------------------------------


def test_progress_opt_in_completion_and_identical_archive():
    with workspace() as ws:
        src = vorbis_with_runtime_comment(ws)
        dest_off = unique_name("off")
        dest_on = unique_name("on")
        off = run_product(ws, ["-1", "e", src, dest_off])
        on = run_product(ws, ["-1", "--progress", "e", src, dest_on])
        require_ok_written(off, ws, src, dest_off)
        require_ok_written(on, ws, src, dest_on)
        on_bytes = require_archive_roundtrip(
            ws, src, dest_on, what="--progress compress"
        )
        off_bytes = archive_bytes(ws, dest_off)
        assert on_bytes == off_bytes, (
            "enabling progress must not change archive bytes at the same effort"
        )
        require_completion_contrast(off, on)
        print("[F08] A opt-in completion and identical archive", flush=True)


def test_progress_forms_leave_archive_bytes_unchanged_at_both_effort_ends():
    with workspace() as ws:
        sources = (
            ("vorbis", vorbis_with_runtime_comment(ws), ".ogg"),
            ("opus", opus_with_runtime_tags(ws, "hybrid"), ".opus"),
        )
        for codec, src, suffix in sources:
            if codec == "opus":
                _prove_family0(ws.read_bytes(src), what="progress identity Opus")
            for effort in ("-1", "-9"):
                base = unique_name(f"{codec}{effort}-off")
                require_ok_written(
                    run_product(ws, [effort, "e", src, base]), ws, src, base
                )
                base_bytes = archive_bytes(ws, base)
                for form in (["--progress"], ["-p"], ["--progress-lines"]):
                    dest = unique_name(f"{codec}{effort}-on")
                    result = run_product(ws, [effort, *form, "e", src, dest])
                    require_ok_written(result, ws, src, dest)
                    assert archive_bytes(ws, dest) == base_bytes, (
                        "enabling progress must not change archive bytes at the "
                        f"same effort: {codec} {effort} with {form[0]}"
                    )
                member = unique_name(f"{codec}{effort}-batch") + suffix
                ws.write(member, ws.read_bytes(src))
                batch = run_product_long(
                    ws, [effort, "-p", "--jobs=1", "-b", "e", member]
                )
                require_ok(batch)
                batch_bytes = archive_bytes(ws, derived_batch_archive(member))
                assert batch_bytes == base_bytes, (
                    "batch compress with progress must write the same archive "
                    f"as single-file compress without it: {codec} {effort}"
                )
                print(f"[F08] A2 {codec} {effort} progress forms identical", flush=True)


# ---------------------------------------------------------------------------
# B. Short -p on single-file compress and single-file expand
# ---------------------------------------------------------------------------


def test_short_p_enables_completion_indication():
    with workspace() as ws:
        src = vorbis_with_runtime_comment(ws)
        saved = ws.read_bytes(src)
        dest_off = unique_name("off")
        dest_p = unique_name("p")
        off = run_product(ws, ["-1", "e", src, dest_off])
        on = run_product(ws, ["-1", "-p", "e", src, dest_p])
        require_ok_written(off, ws, src, dest_off)
        require_ok_written(on, ws, src, dest_p)
        off_bytes = require_archive_roundtrip(ws, src, dest_off, what="-p baseline")
        on_bytes = require_archive_roundtrip(ws, src, dest_p, what="-p compress")
        assert on_bytes == off_bytes, (
            "-p compress must write the same archive bytes as the no-option arm"
        )
        require_completion_contrast(off, on)

        scramble_or_remove(ws, src, saved)
        rec_off = unique_name("rec-off")
        rec_p = unique_name("rec-p")
        exp_off = run_product(ws, ["d", dest_off, rec_off])
        exp_on = run_product(ws, ["-p", "d", dest_off, rec_p])
        require_ok(exp_off)
        require_ok(exp_on)
        require_written_dest(ws, dest_off, rec_off)
        require_written_dest(ws, dest_off, rec_p)
        assert ws.read_bytes(rec_off) == saved, (
            "expand without progress did not restore the saved original"
        )
        assert ws.read_bytes(rec_p) == saved, (
            "-p expand did not restore the saved original"
        )
        require_completion_contrast(exp_off, exp_on)
        print("[F08] B -p compress and expand completion", flush=True)


# ---------------------------------------------------------------------------
# C. Expand --progress recovers original and carries completion
# ---------------------------------------------------------------------------


def test_expand_with_progress_recovers_and_completes():
    with workspace() as ws:
        src = vorbis_with_runtime_comment(ws)
        saved = ws.read_bytes(src)
        arc = unique_name("arc")
        packed = run_product(ws, ["-1", "e", src, arc])
        require_ok_written(packed, ws, src, arc)
        require_archive_roundtrip(ws, src, arc, what="C baseline compress")
        scramble_or_remove(ws, src, saved)
        rec_off = unique_name("rec-off")
        rec_on = unique_name("rec-on")
        off = run_product(ws, ["d", arc, rec_off])
        on = run_product(ws, ["--progress", "d", arc, rec_on])
        require_ok(off)
        require_ok(on)
        require_written_dest(ws, arc, rec_off)
        require_written_dest(ws, arc, rec_on)
        assert ws.read_bytes(rec_off) == saved, (
            "expand without progress did not restore the saved original"
        )
        assert ws.read_bytes(rec_on) == saved, (
            "expand with --progress did not restore the saved original"
        )
        require_completion_contrast(off, on)
        print("[F08] C expand --progress recovers and completes", flush=True)


# ---------------------------------------------------------------------------
# D. --progress-lines accepted; newline-oriented at effort 9
# ---------------------------------------------------------------------------


def test_progress_lines_are_newline_oriented():
    with workspace() as ws:
        src = vorbis_with_runtime_comment(ws)
        saved = ws.read_bytes(src)
        dest_off = unique_name("off")
        dest_lines = unique_name("lines")
        dest9 = unique_name("lines9")
        off = run_product(ws, ["-1", "e", src, dest_off])
        on = run_product(ws, ["-1", "--progress-lines", "e", src, dest_lines])
        require_ok_written(off, ws, src, dest_off)
        require_ok_written(on, ws, src, dest_lines)
        off_bytes = archive_bytes(ws, dest_off)
        on_bytes = require_archive_roundtrip(
            ws, src, dest_lines, what="--progress-lines -1"
        )
        assert on_bytes == off_bytes, (
            "--progress-lines must not change archive bytes at the same effort"
        )

        on9 = run_product_long(ws, ["-9", "--progress-lines", "e", src, dest9])
        require_ok_written(on9, ws, src, dest9)
        require_archive_roundtrip(ws, src, dest9, what="--progress-lines -9")
        require_newline_oriented_records(on9.stderr_text)

        scramble_or_remove(ws, src, saved)
        rec_off = unique_name("rec-off")
        rec_on = unique_name("rec-on")
        exp_off = run_product(ws, ["d", dest_lines, rec_off])
        exp_on = run_product(ws, ["--progress-lines", "d", dest_lines, rec_on])
        require_ok(exp_off)
        require_ok(exp_on)
        require_written_dest(ws, dest_lines, rec_off)
        require_written_dest(ws, dest_lines, rec_on)
        assert ws.read_bytes(rec_off) == saved, (
            "expand without progress did not restore the saved original"
        )
        assert ws.read_bytes(rec_on) == saved, (
            "expand with --progress-lines did not restore the saved original"
        )
        print("[F08] D --progress-lines newline-oriented", flush=True)


# ---------------------------------------------------------------------------
# E. Opus compress and expand both reach completion
# ---------------------------------------------------------------------------


def test_opus_compress_and_expand_reach_completion():
    with workspace() as ws:
        src = opus_with_runtime_tags(ws, "silk")
        _prove_family0(ws.read_bytes(src), what="runtime family-0 Opus")
        saved = ws.read_bytes(src)
        dest_off = unique_name("opus-off")
        dest_on = unique_name("opus-on")
        off = run_product(ws, ["-1", "e", src, dest_off])
        on = run_product(ws, ["-1", "--progress", "e", src, dest_on])
        require_ok_written(off, ws, src, dest_off)
        require_ok_written(on, ws, src, dest_on)
        off_bytes = archive_bytes(ws, dest_off)
        on_bytes = require_archive_roundtrip(
            ws, src, dest_on, what="Opus --progress compress"
        )
        assert on_bytes == off_bytes, (
            "Opus archive bytes must not change when progress is enabled"
        )
        require_completion_contrast(off, on)

        rec_off = unique_name("opus-rec-off")
        rec_on = unique_name("opus-rec-on")
        exp_off = run_product(ws, ["d", dest_on, rec_off])
        exp_on = run_product(ws, ["--progress", "d", dest_on, rec_on])
        require_ok(exp_off)
        require_ok(exp_on)
        require_written_dest(ws, dest_on, rec_off)
        require_written_dest(ws, dest_on, rec_on)
        assert ws.read_bytes(rec_off) == saved
        assert ws.read_bytes(rec_on) == saved
        require_completion_contrast(exp_off, exp_on)
        print("[F08] E Opus compress and expand completion", flush=True)


# ---------------------------------------------------------------------------
# F. Batch --progress --jobs=2, three named files
# ---------------------------------------------------------------------------


def test_batch_progress_jobs_two_names_three_files():
    with workspace() as ws_off:
        off_files = (
            place_vorbis(ws_off, "a"),
            place_vorbis(ws_off, "b"),
            place_runtime_vorbis(ws_off),
        )
        off = run_product(
            ws_off, ["-1", "--jobs=2", "-b", "e", *off_files]
        )
        require_ok(off)
        for src in off_files:
            require_compress_member(ws_off, src)

    with workspace() as ws_on:
        on_files = (
            place_vorbis(ws_on, "a"),
            place_vorbis(ws_on, "b"),
            place_runtime_vorbis(ws_on),
        )
        on = run_product(
            ws_on,
            ["-1", "--progress", "--jobs=2", "-b", "e", *on_files],
        )
        require_ok(on)
        for src in on_files:
            require_compress_member(ws_on, src)
        require_completion_indication(on)
        require_names_visible_on_newline_records(on.stderr_text, on_files)
        print("[F08] F batch --jobs=2 three names on newline records", flush=True)


# ---------------------------------------------------------------------------
# G. --jobs=1 two files: names on distinct newline records
# ---------------------------------------------------------------------------


def test_batch_progress_jobs_one_names_on_distinct_lines():
    with workspace() as ws:
        a = place_vorbis(ws, "a")
        b = place_vorbis(ws, "b")
        result = run_product(
            ws, ["-1", "--progress", "--jobs=1", "-b", "e", a, b]
        )
        require_ok(result)
        require_compress_member(ws, a)
        require_compress_member(ws, b)
        require_names_on_distinct_newline_lines(result.stderr_text, (a, b))
        print("[F08] G --jobs=1 names on distinct newline lines", flush=True)


# ---------------------------------------------------------------------------
# H. Vorbis --progress completes at both effort ends
# ---------------------------------------------------------------------------


def test_vorbis_progress_completes_at_effort1_and_effort9():
    with workspace() as ws:
        src = vorbis_with_runtime_comment(ws)
        dest1 = unique_name("e1")
        dest9 = unique_name("e9")
        arm1 = run_product(ws, ["--progress", "-1", "e", src, dest1])
        arm9 = run_product_long(ws, ["--progress", "-9", "e", src, dest9])
        require_ok_written(arm1, ws, src, dest1)
        require_ok_written(arm9, ws, src, dest9)
        require_archive_roundtrip(ws, src, dest1, what="effort 1 --progress")
        require_archive_roundtrip(ws, src, dest9, what="effort 9 --progress")
        require_completion_indication(arm1)
        require_completion_indication(arm9)
        print("[F08] H effort 1 and effort 9 progress complete", flush=True)


# ---------------------------------------------------------------------------
# I. Refusal with progress: still exit 1, diagnostic not hidden, no dest
# ---------------------------------------------------------------------------


def test_refusal_with_progress_keeps_status_and_diagnostic():
    with workspace() as ws:
        good = vorbis_with_runtime_comment(ws)
        dest_ok = unique_name("ok")
        bad = place_non_ogg(ws)
        dest_off = unique_name("ref-off")
        dest_on = unique_name("ref-on")
        success = run_product(ws, ["--progress", "-1", "e", good, dest_ok])
        refuse_off = run_product(ws, ["e", bad, dest_off])
        refuse_on = run_product(ws, ["--progress", "e", bad, dest_on])
        require_ok_written(success, ws, good, dest_ok)
        require_refusal(refuse_off)
        require_refusal(refuse_on)
        require_no_usable_compress_dest(ws, dest_on)
        stderr_names_input(refuse_on.stderr_text, bad)
        assert refuse_on.returncode == refuse_off.returncode == 1
        print("[F08] I refusal with progress keeps status and diagnostic", flush=True)


# ---------------------------------------------------------------------------
# J. Batch expand with progress: archive names on newline records
# ---------------------------------------------------------------------------


def test_batch_expand_with_progress_names_inputs():
    with workspace() as ws:
        sources = (
            place_vorbis(ws, "a"),
            place_vorbis(ws, "b"),
        )
        saved = {src: ws.read_bytes(src) for src in sources}
        packed = run_product(ws, ["-1", "-b", "e", *sources])
        require_ok(packed)
        archives = [derived_batch_archive(src) for src in sources]
        for src in sources:
            require_compress_member(ws, src)
            scramble_or_remove(ws, src, saved[src])
        result = run_product(ws, ["--progress", "-b", "d", *archives])
        require_ok(result)
        for src, arc in zip(sources, archives):
            dest = derived_batch_expand(arc)
            require_expand_restored(ws, dest, saved[src])
        require_names_visible_on_newline_records(result.stderr_text, archives)
        print("[F08] J batch expand names on newline records", flush=True)


# ---------------------------------------------------------------------------
# K. -p and --progress-lines accepted on batch compress
# ---------------------------------------------------------------------------


def test_batch_accepts_short_p_and_progress_lines():
    with workspace() as ws:
        a_p = place_vorbis(ws, "a")
        b_p = place_vorbis(ws, "b")
        short = run_product(ws, ["-1", "-p", "-b", "e", a_p, b_p])
        require_ok(short)
        require_compress_member(ws, a_p)
        require_compress_member(ws, b_p)
        require_names_visible_on_newline_records(short.stderr_text, (a_p, b_p))

        a_l = place_runtime_vorbis(ws)
        b_l = place_vorbis(ws, "b")
        lines = run_product(
            ws, ["-1", "--progress-lines", "-b", "e", a_l, b_l]
        )
        require_ok(lines)
        require_compress_member(ws, a_l)
        require_compress_member(ws, b_l)
        require_names_visible_on_newline_records(lines.stderr_text, (a_l, b_l))
        print("[F08] K batch accepts -p and --progress-lines", flush=True)
