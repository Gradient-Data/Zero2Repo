# feature: F09
"""Acceptance: archive dump and Ogg page listing."""

from __future__ import annotations

from F01_helpers import (
    place_non_ogg,
    place_placeholder,
    place_vorbis,
    require_bytes_unchanged,
    require_file_access,
    require_refusal,
    require_stderr_identifies_path_failure,
    run_expect_usage_no_archive,
    run_product,
    unique_name,
)
from F02_helpers import parse_ogg_pages, place_vorbis_without_ogg_suffix
from F03_helpers import (
    dump_stdout,
    dump_stored_stage,
    place_opus_classified,
    require_codec_mode_field,
)
from F04_helpers import (
    _SCALE_FILES,
    _prove_family0,
    _read_fixture,
    _vorbis_comment_variant,
    archive_bytes,
    vorbis_with_runtime_comment,
)
from F05_helpers import (
    foreign_generation_values,
    place_bytes_without_codec_suffix,
    with_generation_value,
    written_generation,
)
from F06_helpers import concat_bitstreams
from F09_helpers import (
    lossless_compress,
    pages_stdout,
    require_every_page_reconstructs,
    require_page_listing,
    still_parseable_one_page_checksum_sibling,
)
from _harness import workspace


# ---------------------------------------------------------------------------
# A. Codec-mode field: two classified Opus kinds share; Vorbis differs
# ---------------------------------------------------------------------------


def test_dump_codec_mode_field_two_opus_share_vorbis_differs():
    with workspace() as ws:
        require_codec_mode_field(ws, "-1", what="F09 A effort 1")


# ---------------------------------------------------------------------------
# B. Stored-stage field follows the effort, not the input
# ---------------------------------------------------------------------------


def test_dump_stored_stage_field_follows_effort_not_input():
    with workspace() as ws:
        src_x = vorbis_with_runtime_comment(ws)
        y_bytes = _vorbis_comment_variant(_read_fixture(_SCALE_FILES[2]))
        src_y = unique_name("vorbis-y") + ".ogg"
        ws.write(src_y, y_bytes)
        assert ws.read_bytes(src_x) != y_bytes, (
            "stored-stage inputs X and Y are not distinct Vorbis files"
        )
        arc_1x = unique_name("e1-x")
        arc_1y = unique_name("e1-y")
        arc_3x = unique_name("e3-x")
        arc_3y = unique_name("e3-y")
        lossless_compress(ws, src_x, arc_1x, "-1")
        lossless_compress(ws, src_y, arc_1y, "-1")
        lossless_compress(ws, src_x, arc_3x, "-3")
        lossless_compress(ws, src_y, arc_3y, "-3")
        text_1x = dump_stdout(ws, arc_1x)
        text_1y = dump_stdout(ws, arc_1y)
        text_3x = dump_stdout(ws, arc_3x)
        text_3y = dump_stdout(ws, arc_3y)
        stage_1x = dump_stored_stage(text_1x)
        stage_1y = dump_stored_stage(text_1y)
        stage_3x = dump_stored_stage(text_3x)
        stage_3y = dump_stored_stage(text_3y)
        print(
            f"[F09] B stages e1=({stage_1x},{stage_1y}) e3=({stage_3x},{stage_3y})",
            flush=True,
        )
        assert stage_1x == stage_1y and stage_3x == stage_3y, (
            "the stored stage of a Vorbis archive follows the effort, not the "
            f"input: effort 1 gave {stage_1x}/{stage_1y}, effort 3 gave "
            f"{stage_3x}/{stage_3y}"
        )


# ---------------------------------------------------------------------------
# C. pages of valid Vorbis, no codec suffix: countable, unmodified
# ---------------------------------------------------------------------------


def test_pages_lists_valid_vorbis_countable_unmodified():
    with workspace() as ws:
        path_a = place_vorbis_without_ogg_suffix(ws, "a")
        path_b = place_vorbis_without_ogg_suffix(ws, "b")
        bytes_a = ws.read_bytes(path_a)
        bytes_b = ws.read_bytes(path_b)
        n_a = len(parse_ogg_pages(bytes_a))
        n_b = len(parse_ogg_pages(bytes_b))
        if n_a == n_b:
            chained = concat_bitstreams([bytes_a, bytes_b])
            path_n, path_m = path_a, place_bytes_without_codec_suffix(
                ws, chained, "vorbis-m"
            )
            n_pages, m_pages = n_a, len(parse_ogg_pages(chained))
        elif n_a < n_b:
            path_n, path_m = path_a, path_b
            n_pages, m_pages = n_a, n_b
        else:
            path_n, path_m = path_b, path_a
            n_pages, m_pages = n_b, n_a
        assert n_pages < m_pages, (
            f"Vorbis page-count pair is not N < M: N={n_pages} M={m_pages}"
        )
        snap_n = ws.read_bytes(path_n)
        snap_m = ws.read_bytes(path_m)
        require_every_page_reconstructs(snap_n)
        require_every_page_reconstructs(snap_m)
        text_n = pages_stdout(ws, path_n)
        text_m = pages_stdout(ws, path_m)
        require_bytes_unchanged(ws, path_n, snap_n)
        require_bytes_unchanged(ws, path_m, snap_m)
        probe = unique_name("probe")
        ws.write(probe, snap_n)
        ws.write(probe, snap_n + b"\x00")
        assert ws.read_bytes(probe) != snap_n, (
            "the outside observer did not report a one-byte write to a copy"
        )
        flip_n = still_parseable_one_page_checksum_sibling(snap_n)
        flip_m = still_parseable_one_page_checksum_sibling(snap_m)
        path_flip_n = place_bytes_without_codec_suffix(ws, flip_n, "vorbis-flip-n")
        path_flip_m = place_bytes_without_codec_suffix(ws, flip_m, "vorbis-flip-m")
        text_flip_n = pages_stdout(ws, path_flip_n)
        text_flip_m = pages_stdout(ws, path_flip_m)
        require_page_listing(text_n, n_pages, frozenset(), what="Vorbis N well-formed")
        require_page_listing(text_m, m_pages, frozenset(), what="Vorbis M well-formed")
        require_page_listing(
            text_flip_n, n_pages, frozenset({0}), what="Vorbis N one checksum flipped"
        )
        require_page_listing(
            text_flip_m, m_pages, frozenset({0}), what="Vorbis M one checksum flipped"
        )


# ---------------------------------------------------------------------------
# D. pages of valid family-0 Opus, no codec suffix: countable, unmodified
# ---------------------------------------------------------------------------


def test_pages_lists_valid_opus_countable_unmodified():
    with workspace() as ws:
        path_a = place_opus_classified(ws, "silk", suffix="")
        path_b = place_opus_classified(ws, "celt", suffix="")
        _prove_family0(ws.read_bytes(path_a), what="silk pages host")
        _prove_family0(ws.read_bytes(path_b), what="celt pages host")
        bytes_a = ws.read_bytes(path_a)
        bytes_b = ws.read_bytes(path_b)
        n_a = len(parse_ogg_pages(bytes_a))
        n_b = len(parse_ogg_pages(bytes_b))
        if n_a == n_b:
            chained = concat_bitstreams([bytes_a, bytes_b])
            path_n, path_m = path_a, place_bytes_without_codec_suffix(
                ws, chained, "opus-m"
            )
            n_pages, m_pages = n_a, len(parse_ogg_pages(chained))
        elif n_a < n_b:
            path_n, path_m = path_a, path_b
            n_pages, m_pages = n_a, n_b
        else:
            path_n, path_m = path_b, path_a
            n_pages, m_pages = n_b, n_a
        assert n_pages < m_pages, (
            f"Opus page-count pair is not N < M: N={n_pages} M={m_pages}"
        )
        snap_n = ws.read_bytes(path_n)
        snap_m = ws.read_bytes(path_m)
        require_every_page_reconstructs(snap_n)
        require_every_page_reconstructs(snap_m)
        text_n = pages_stdout(ws, path_n)
        text_m = pages_stdout(ws, path_m)
        require_bytes_unchanged(ws, path_n, snap_n)
        require_bytes_unchanged(ws, path_m, snap_m)
        probe = unique_name("probe")
        ws.write(probe, snap_n)
        ws.write(probe, snap_n + b"\x00")
        assert ws.read_bytes(probe) != snap_n, (
            "the outside observer did not report a one-byte write to a copy"
        )
        flip_n = still_parseable_one_page_checksum_sibling(snap_n)
        flip_m = still_parseable_one_page_checksum_sibling(snap_m)
        path_flip_n = place_bytes_without_codec_suffix(ws, flip_n, "opus-flip-n")
        path_flip_m = place_bytes_without_codec_suffix(ws, flip_m, "opus-flip-m")
        text_flip_n = pages_stdout(ws, path_flip_n)
        text_flip_m = pages_stdout(ws, path_flip_m)
        require_page_listing(text_n, n_pages, frozenset(), what="Opus N well-formed")
        require_page_listing(text_m, m_pages, frozenset(), what="Opus M well-formed")
        require_page_listing(
            text_flip_n, n_pages, frozenset({0}), what="Opus N one checksum flipped"
        )
        require_page_listing(
            text_flip_m, m_pages, frozenset({0}), what="Opus M one checksum flipped"
        )


# ---------------------------------------------------------------------------
# E. dump / pages of a missing path is a file-access error
# ---------------------------------------------------------------------------


def test_dump_and_pages_missing_path_is_file_access():
    with workspace() as ws:
        src = vorbis_with_runtime_comment(ws)
        arc = unique_name("ok-arc")
        lossless_compress(ws, src, arc, "-1")
        dump_stdout(ws, arc)
        pages_stdout(ws, src)
        missing_dump = unique_name("missing-dump")
        missing_pages = unique_name("missing-pages")
        dump_miss = run_product(ws, ["dump", missing_dump])
        require_file_access(dump_miss)
        require_stderr_identifies_path_failure(dump_miss, missing_dump)
        pages_miss = run_product(ws, ["pages", missing_pages])
        require_file_access(pages_miss)
        require_stderr_identifies_path_failure(pages_miss, missing_pages)
        print(
            f"[F09] E dump_missing exit={dump_miss.returncode} "
            f"pages_missing exit={pages_miss.returncode}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# F. pages of a non-Ogg file (including an archive) is refused
# ---------------------------------------------------------------------------


def test_pages_of_non_ogg_is_refused():
    with workspace() as ws:
        src = vorbis_with_runtime_comment(ws)
        baseline = pages_stdout(ws, src)
        assert baseline, (
            "pages of a well-formed Ogg file writes a listing to standard "
            "output (live baseline: the product is not always refuse)"
        )
        arc = unique_name("arc-not-ogg")
        lossless_compress(ws, src, arc, "-1")
        of_archive = run_product(ws, ["pages", arc])
        require_refusal(of_archive)
        assert of_archive.returncode == 1, (
            "pages of an archive file (not Ogg) exits 1; "
            f"got {of_archive.returncode}; stderr={of_archive.stderr!r}"
        )
        assert of_archive.stderr, (
            "a refusal writes a diagnostic to standard error; "
            f"stdout={of_archive.stdout!r}"
        )
        non_ogg = place_non_ogg(ws)
        of_random = run_product(ws, ["pages", non_ogg])
        require_refusal(of_random)
        assert of_random.returncode == 1, (
            "pages on a file that is not Ogg is refused (exit 1); "
            f"got {of_random.returncode}; stderr={of_random.stderr!r}"
        )
        assert of_random.stderr, (
            "a refusal writes a diagnostic to standard error; "
            f"stdout={of_random.stdout!r}"
        )
        print(
            f"[F09] F pages-archive exit={of_archive.returncode} "
            f"pages-nonogg exit={of_random.returncode}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# G. dump of a non-archive and of a foreign generation is refused
# ---------------------------------------------------------------------------


def test_dump_of_non_archive_and_foreign_generation_is_refused():
    with workspace() as ws:
        src_a = vorbis_with_runtime_comment(ws)
        y_bytes = _vorbis_comment_variant(_read_fixture(_SCALE_FILES[1]))
        src_b = unique_name("vorbis-b") + ".ogg"
        ws.write(src_b, y_bytes)
        arc_a = unique_name("gen-a")
        arc_b = unique_name("gen-b")
        lossless_compress(ws, src_a, arc_a, "-1")
        lossless_compress(ws, src_b, arc_b, "-1")
        dump_stdout(ws, arc_a)
        ogg = place_vorbis(ws, "a")
        of_ogg = run_product(ws, ["dump", ogg])
        require_refusal(of_ogg)
        non_ogg = place_non_ogg(ws)
        of_random = run_product(ws, ["dump", non_ogg])
        require_refusal(of_random)
        bytes_a = archive_bytes(ws, arc_a)
        bytes_b = archive_bytes(ws, arc_b)
        written = written_generation(ws, src_a, bytes_a, bytes_b)
        non_dest = unique_name("gen-nonarc-out")
        require_refusal(run_product(ws, ["d", ogg, non_dest]))
        older_val, newer_val = foreign_generation_values(written)
        older_path = unique_name("gen-older")
        newer_path = unique_name("gen-newer")
        ws.write(older_path, with_generation_value(bytes_a, older_val))
        ws.write(newer_path, with_generation_value(bytes_a, newer_val))
        for path in (older_path, newer_path):
            out = unique_name("gen-exp-out")
            require_refusal(run_product(ws, ["d", path, out]))
        older_run = run_product(ws, ["dump", older_path])
        newer_run = run_product(ws, ["dump", newer_path])
        require_refusal(older_run)
        require_refusal(newer_run)
        print(
            f"[F09] G written={written} older={older_val} newer={newer_val} "
            f"dump-ogg exit={of_ogg.returncode} "
            f"dump-nonogg exit={of_random.returncode} "
            f"dump-older exit={older_run.returncode} "
            f"dump-newer exit={newer_run.returncode}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# H. Extra operand beyond one path is a usage error; no new archive
# ---------------------------------------------------------------------------


def test_dump_and_pages_extra_operand_is_usage():
    with workspace() as ws:
        src = vorbis_with_runtime_comment(ws)
        arc = unique_name("ok-arc")
        lossless_compress(ws, src, arc, "-1")
        dump_stdout(ws, arc)
        pages_stdout(ws, src)
        extra = place_placeholder(ws)
        dump_extra = run_expect_usage_no_archive(ws, ["dump", arc, extra])
        pages_extra = run_expect_usage_no_archive(ws, ["pages", src, extra])
        print(
            f"[F09] H dump-extra exit={dump_extra.returncode} "
            f"pages-extra exit={pages_extra.returncode}",
            flush=True,
        )
