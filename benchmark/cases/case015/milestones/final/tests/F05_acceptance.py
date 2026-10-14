# feature: F05
"""Acceptance: refuse inputs this product cannot reproduce exactly."""

from __future__ import annotations

import secrets

from F01_helpers import (
    _vorbis_bytes,
    place_non_ogg,
    require_file_access,
    require_ok,
    require_refusal,
    run_product,
    token,
    unique_name,
)
from F02_helpers import (
    parse_ogg_pages,
    replace_vorbis_comment,
    require_no_usable_expand_dest,
    roundtrip,
)
from F03_helpers import states_decimal, without_paths
from F04_helpers import _prove_family0, opus_with_runtime_tags, vorbis_with_runtime_comment
from F05_helpers import (
    corrupt_stored_page_checksum,
    floor_slot,
    foreign_generation_values,
    later_page_index,
    live_compress,
    lookup_slot,
    place_bytes_without_codec_suffix,
    prove_checksum_mismatch,
    prove_floor_type,
    prove_lookup_type,
    prove_marked_span,
    prove_page_after_eos,
    prove_sparse_empty_book,
    prove_unmarked_span,
    refuse_compress,
    refuse_expand,
    set_floor_type_at,
    set_lookup_type_at,
    shared_prefix_len,
    sparse_book_slot,
    stderr_names_input,
    truncation_lengths,
    with_generation_value,
    with_marked_packet_span,
    with_page_after_eos,
    with_sparse_empty_book,
    with_trailing_non_page,
    with_unmarked_packet_span,
    written_generation,
)
from _harness import HarnessError, workspace


def _runtime_vorbis_bytes() -> bytes:
    mark = token().encode("ascii")
    return replace_vorbis_comment(
        _vorbis_bytes("a"),
        vendor=b"suite-vendor-" + mark,
        fields=(b"TITLE=" + mark, b"NOTE=" + mark),
    )


def _runtime_vorbis_bytes_b() -> bytes:
    mark = token().encode("ascii")
    return replace_vorbis_comment(
        _vorbis_bytes("b"),
        vendor=b"suite-vendor-" + mark,
        fields=(b"TITLE=" + mark, b"NOTE=" + mark, b"EXTRA=" + mark),
    )


def _place_runtime_vorbis(ws, *, which: str = "a") -> str:
    data = _runtime_vorbis_bytes() if which == "a" else _runtime_vorbis_bytes_b()
    rel = unique_name(f"vorbis-rt-{which}") + ".ogg"
    ws.write(rel, data)
    return rel


def _place_runtime_opus(ws) -> str:
    return opus_with_runtime_tags(ws, "silk")


# ---------------------------------------------------------------------------
# A. Wrong page checksum is refused (RFC 3533)
# ---------------------------------------------------------------------------


def test_wrong_page_checksum_is_refused():
    with workspace() as ws:
        src = _place_runtime_vorbis(ws)
        live_compress(ws, src)
        original = ws.read_bytes(src)
        pages = parse_ogg_pages(original)
        assert pages, "host Vorbis has no Ogg pages"
        mutated = corrupt_stored_page_checksum(original, 0)
        prove_checksum_mismatch(mutated, 0)
        bad = unique_name("crc0") + ".ogg"
        ws.write(bad, mutated)
        result = refuse_compress(ws, bad, unique_name("crc0-arc"))
        assert result.returncode == 1
        assert result.stderr


def test_later_page_wrong_checksum_is_refused():
    with workspace() as ws:
        src = _place_runtime_vorbis(ws)
        live_compress(ws, src)
        original = ws.read_bytes(src)
        later = later_page_index(original)
        mutated = corrupt_stored_page_checksum(original, later)
        prove_checksum_mismatch(mutated, later)
        bad = unique_name("crc-later") + ".ogg"
        ws.write(bad, mutated)
        result = refuse_compress(ws, bad, unique_name("crc-later-arc"))
        assert result.returncode == 1
        assert result.stderr


def test_opus_wrong_page_checksum_is_refused():
    with workspace() as ws:
        src = _place_runtime_opus(ws)
        original = ws.read_bytes(src)
        _prove_family0(original, what="Opus checksum host")
        live_compress(ws, src)
        mutated = corrupt_stored_page_checksum(original, 0)
        prove_checksum_mismatch(mutated, 0)
        bad = unique_name("opus-crc0") + ".opus"
        ws.write(bad, mutated)
        result = refuse_compress(ws, bad, unique_name("opus-crc0-arc"))
        assert result.returncode == 1
        assert result.stderr


def test_opus_later_page_wrong_checksum_is_refused():
    with workspace() as ws:
        src = _place_runtime_opus(ws)
        original = ws.read_bytes(src)
        _prove_family0(original, what="Opus later-checksum host")
        live_compress(ws, src)
        later = later_page_index(original)
        mutated = corrupt_stored_page_checksum(original, later)
        prove_checksum_mismatch(mutated, later)
        bad = unique_name("opus-crc-later") + ".opus"
        ws.write(bad, mutated)
        result = refuse_compress(ws, bad, unique_name("opus-crc-later-arc"))
        assert result.returncode == 1
        assert result.stderr


# ---------------------------------------------------------------------------
# B. Page after end-of-stream of the same stream
# ---------------------------------------------------------------------------


def test_page_after_end_of_stream_is_refused():
    with workspace() as ws:
        src = _place_runtime_vorbis(ws)
        live_compress(ws, src)
        mutated = with_page_after_eos(ws.read_bytes(src))
        prove_page_after_eos(mutated)
        bad = unique_name("after-eos") + ".ogg"
        ws.write(bad, mutated)
        result = refuse_compress(ws, bad, unique_name("after-eos-arc"))
        assert result.returncode == 1
        assert result.stderr


def test_opus_page_after_end_of_stream_round_trips():
    with workspace() as ws:
        src = _place_runtime_opus(ws)
        host = ws.read_bytes(src)
        _prove_family0(host, what="Opus after-eos host")
        live_compress(ws, src)
        mutated = with_page_after_eos(host)
        prove_page_after_eos(mutated)
        constructed = unique_name("opus-after-eos") + ".opus"
        ws.write(constructed, mutated)
        dest = roundtrip(ws, constructed, effort="-1")
        constructed_bytes = ws.read_bytes(constructed)
        assert constructed_bytes == mutated
        assert constructed_bytes != host, "after-eos construction equals the unmodified host"
        assert ws.read_bytes(dest) != host, "compress dest equals the unmodified host"
        print(
            f"[F05] opus after-eos constructed_len={len(mutated)} "
            f"host_len={len(host)} dest={dest!r}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# C. Packet continues onto a page not marked as a continuation
# ---------------------------------------------------------------------------


def test_continued_packet_without_continuation_mark_is_refused():
    with workspace() as ws:
        src = _place_runtime_vorbis(ws)
        host = ws.read_bytes(src)
        marked = with_marked_packet_span(host)
        unmarked = with_unmarked_packet_span(host)
        prove_marked_span(marked)
        prove_unmarked_span(unmarked)
        marked_src = unique_name("span-ok") + ".ogg"
        ws.write(marked_src, marked)
        dest = roundtrip(ws, marked_src, effort="-1")
        assert ws.read_bytes(marked_src) == marked
        assert ws.read_bytes(dest) != host
        bad = unique_name("span-bad") + ".ogg"
        ws.write(bad, unmarked)
        result = refuse_compress(ws, bad, unique_name("span-bad-arc"))
        assert result.returncode == 1
        assert result.stderr


def test_opus_continued_packet_without_continuation_mark_round_trips():
    with workspace() as ws:
        src = _place_runtime_opus(ws)
        host = ws.read_bytes(src)
        _prove_family0(host, what="Opus span host")
        marked = with_marked_packet_span(host)
        unmarked = with_unmarked_packet_span(host)
        prove_marked_span(marked)
        prove_unmarked_span(unmarked)
        marked_src = unique_name("opus-span-ok") + ".opus"
        ws.write(marked_src, marked)
        marked_dest = roundtrip(ws, marked_src, effort="-1")
        assert ws.read_bytes(marked_src) == marked
        assert marked != host
        assert ws.read_bytes(marked_dest) != host
        unmarked_src = unique_name("opus-span-unmarked") + ".opus"
        ws.write(unmarked_src, unmarked)
        unmarked_dest = roundtrip(ws, unmarked_src, effort="-1")
        assert ws.read_bytes(unmarked_src) == unmarked
        assert unmarked != host
        assert unmarked != marked
        assert ws.read_bytes(unmarked_dest) != host
        print(
            f"[F05] opus unmarked span constructed_len={len(unmarked)} "
            f"marked_len={len(marked)} host_len={len(host)}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# D. Trailing non-page data after the last Ogg page
# ---------------------------------------------------------------------------


def test_trailing_non_page_data_is_refused():
    with workspace() as ws:
        src = _place_runtime_vorbis(ws)
        live_compress(ws, src)
        junk = (token() * 4).encode("ascii")
        mutated = with_trailing_non_page(ws.read_bytes(src), junk)
        bad = unique_name("trail") + ".ogg"
        ws.write(bad, mutated)
        result = refuse_compress(ws, bad, unique_name("trail-arc"))
        assert result.returncode == 1
        assert result.stderr


def test_opus_trailing_non_page_data_is_refused():
    with workspace() as ws:
        src = _place_runtime_opus(ws)
        _prove_family0(ws.read_bytes(src), what="Opus trailing-host")
        live_compress(ws, src)
        junk = (token() * 4).encode("ascii")
        mutated = with_trailing_non_page(ws.read_bytes(src), junk)
        bad = unique_name("opus-trail") + ".opus"
        ws.write(bad, mutated)
        result = refuse_compress(ws, bad, unique_name("opus-trail-arc"))
        assert result.returncode == 1
        assert result.stderr


# ---------------------------------------------------------------------------
# E. Unsupported Vorbis: floor 0, lookup type 2, sparse empty book
# ---------------------------------------------------------------------------


def test_floor_type_0_is_refused():
    with workspace() as ws:
        src = vorbis_with_runtime_comment(ws)
        host = ws.read_bytes(src)
        live_compress(ws, src)
        slot = floor_slot(host)
        mutated = set_floor_type_at(host, slot, 0)
        prove_floor_type(mutated, slot, 0)
        bad = unique_name("floor0") + ".ogg"
        ws.write(bad, mutated)
        result = refuse_compress(ws, bad, unique_name("floor0-arc"))
        assert result.returncode == 1
        assert result.stderr


def test_codebook_lookup_type_2_is_refused():
    with workspace() as ws:
        src = vorbis_with_runtime_comment(ws)
        host = ws.read_bytes(src)
        live_compress(ws, src)
        slot = lookup_slot(host)
        mutated = set_lookup_type_at(host, slot, 2)
        prove_lookup_type(mutated, slot, 2)
        bad = unique_name("lookup2") + ".ogg"
        ws.write(bad, mutated)
        result = refuse_compress(ws, bad, unique_name("lookup2-arc"))
        assert result.returncode == 1
        assert result.stderr


def test_sparse_empty_codebook_is_refused_or_reproduced_exactly():
    with workspace() as ws:
        src = vorbis_with_runtime_comment(ws)
        host = ws.read_bytes(src)
        live_compress(ws, src)
        slot = sparse_book_slot(host)
        mutated = with_sparse_empty_book(host, slot)
        prove_sparse_empty_book(mutated, slot)
        bad = unique_name("sparse") + ".ogg"
        ws.write(bad, mutated)
        arc = unique_name("sparse-arc")
        result = run_product(ws, ["e", bad, arc])
        print(f"[F05] sparse-empty-book compress exit={result.returncode}", flush=True)
        if result.returncode == 0:
            # An accepted compress promises an exact expand (PRD FP-05).
            roundtrip(ws, bad, dest=unique_name("sparse-arc2"))
        else:
            refuse_compress(ws, bad, unique_name("sparse-arc3"))


# ---------------------------------------------------------------------------
# F. Wrong-type expand-of-Ogg versus compress-of-archive
# ---------------------------------------------------------------------------


def test_expand_of_ogg_versus_compress_of_archive_are_distinguishable():
    with workspace() as ws:
        src = _place_runtime_vorbis(ws)
        live_compress(ws, src)

        ogg_a = _runtime_vorbis_bytes()
        ogg_b = _runtime_vorbis_bytes_b()
        if len(ogg_a) == len(ogg_b):
            ogg_b = replace_vorbis_comment(
                _vorbis_bytes("b"),
                vendor=b"suite-vendor-" + token().encode("ascii"),
                fields=(b"PAD=" + token().encode("ascii") * 8,),
            )
        assert len(ogg_a) != len(ogg_b), "two expand-of-Ogg inputs must differ in size"
        path_a = place_bytes_without_codec_suffix(ws, ogg_a, "ogg-a")
        path_b = place_bytes_without_codec_suffix(ws, ogg_b, "ogg-b")
        dest_a = unique_name("from-ogg-a")
        dest_b = unique_name("from-ogg-b")
        exp_a = refuse_expand(ws, path_a, dest_a, ogg_a)
        exp_b = refuse_expand(ws, path_b, dest_b, ogg_b)

        vorbis_x = _place_runtime_vorbis(ws, which="a")
        vorbis_y = _place_runtime_vorbis(ws, which="b")
        arc_x = live_compress(ws, vorbis_x)
        arc_y = live_compress(ws, vorbis_y)
        if ws.file_size(arc_x) == ws.file_size(arc_y):
            raise HarnessError("two successful archives have the same size")
        dest_x = unique_name("from-arc-x")
        dest_y = unique_name("from-arc-y")
        cmp_x = refuse_compress(ws, arc_x, dest_x)
        cmp_y = refuse_compress(ws, arc_y, dest_y)

        every_path = (
            path_a, path_b, dest_a, dest_b, arc_x, arc_y, dest_x, dest_y,
            vorbis_x, vorbis_y,
        )
        expand_texts = [
            without_paths(r.stderr_text, every_path).strip() for r in (exp_a, exp_b)
        ]
        compress_texts = [
            without_paths(r.stderr_text, every_path).strip() for r in (cmp_x, cmp_y)
        ]
        print(
            f"[F05] wrong-type expand={expand_texts!r} compress={compress_texts!r}",
            flush=True,
        )
        for e_text in expand_texts:
            for c_text in compress_texts:
                assert e_text != c_text, (
                    "the diagnostics of expand-of-Ogg and compress-of-archive "
                    "differ in no more than the paths they name: "
                    f"{e_text!r} vs {c_text!r}"
                )


def test_non_ogg_compress_is_distinguishable_from_missing_path():
    with workspace() as ws:
        src = place_non_ogg(ws)
        dest = unique_name("nonogg-out")
        refused = run_product(ws, ["e", src, dest])
        require_refusal(refused)
        assert refused.returncode == 1, (
            f"non-Ogg compress exited {refused.returncode}, not 1; "
            f"stderr={refused.stderr!r}"
        )
        missing = unique_name("missing-in")
        miss_dest = unique_name("missing-out")
        missing_run = run_product(ws, ["e", missing, miss_dest])
        require_file_access(missing_run)
        assert missing_run.returncode == 3, (
            f"missing path exited {missing_run.returncode}, not 3; "
            f"stderr={missing_run.stderr!r}"
        )
        assert refused.returncode != missing_run.returncode, (
            "non-Ogg compress is not distinguishable by status from a missing path"
        )
        print(
            f"[F05] non-Ogg exit={refused.returncode} "
            f"missing exit={missing_run.returncode}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# G. Foreign generation, older and newer, distinguishable from not-an-archive
# ---------------------------------------------------------------------------


def _foreign_generation_case(ws, src_a: str, src_b: str, non_archive: str, original_a: bytes):
    arc_b = live_compress(ws, src_b)
    arc_a = live_compress(ws, src_a)
    bytes_a = ws.read_bytes(arc_a)
    bytes_b = ws.read_bytes(arc_b)
    recovered = unique_name("gen-ok")
    dec = run_product(ws, ["d", arc_a, recovered])
    require_ok(dec)
    assert ws.read_bytes(recovered) == original_a, (
        "baseline expand did not restore the original bytes"
    )

    written = written_generation(ws, src_a, bytes_a, bytes_b)
    non_bytes = ws.read_bytes(non_archive)
    non_dest = unique_name("gen-nonarc")
    refuse_expand(ws, non_archive, non_dest, non_bytes)

    older_val, newer_val = foreign_generation_values(written)
    for label, value in (("older", older_val), ("newer", newer_val)):
        foreign = with_generation_value(bytes_a, value)
        path = unique_name(f"gen-{label}")
        dest = unique_name(f"gen-{label}-out")
        ws.write(path, foreign)
        run = run_product(ws, ["d", path, dest])
        print(
            f"[F05] generation written={written} {label}={value} "
            f"exit={run.returncode} stderr={run.stderr_text!r}",
            flush=True,
        )
        require_refusal(run)
        require_no_usable_expand_dest(ws, dest, original_a)
        assert states_decimal(without_paths(run.stderr_text, (path, dest)), value), (
            f"the diagnostic of a foreign-generation ({label}) expand does not "
            f"state the archive's generation value {value} as a decimal number; "
            f"stderr={run.stderr_text!r}"
        )


def test_foreign_generation_older_and_newer_is_refused():
    with workspace() as ws:
        src_a = _place_runtime_vorbis(ws, which="a")
        src_b = _place_runtime_vorbis(ws, which="b")
        ogg = _runtime_vorbis_bytes()
        non_archive = place_bytes_without_codec_suffix(ws, ogg, "not-arc")
        _foreign_generation_case(ws, src_a, src_b, non_archive, ws.read_bytes(src_a))


def test_opus_archive_foreign_generation_is_refused():
    with workspace() as ws:
        src_a = opus_with_runtime_tags(ws, "silk")
        src_b = opus_with_runtime_tags(ws, "celt")
        _prove_family0(ws.read_bytes(src_a), what="Opus generation host a")
        _prove_family0(ws.read_bytes(src_b), what="Opus generation host b")
        ogg = _runtime_vorbis_bytes()
        non_archive = place_bytes_without_codec_suffix(ws, ogg, "opus-not-arc")
        _foreign_generation_case(ws, src_a, src_b, non_archive, ws.read_bytes(src_a))


# ---------------------------------------------------------------------------
# H. Truncated archive stays in exit {0, 1}
# ---------------------------------------------------------------------------


def _truncated_archive_case(ws, src: str):
    original = ws.read_bytes(src)
    archive = live_compress(ws, src)
    recovered = unique_name("trunc-ok")
    dec = run_product(ws, ["d", archive, recovered])
    require_ok(dec)
    assert ws.read_bytes(recovered) == original, (
        "baseline expand of the intact archive did not restore the original"
    )
    blob = ws.read_bytes(archive)
    lengths = truncation_lengths(len(blob))
    for length in lengths:
        cut = unique_name("trunc")
        dest = unique_name("trunc-out")
        ws.write(cut, blob[:length])
        result = run_product(ws, ["d", cut, dest])
        print(
            f"[F05] truncated len={length}/{len(blob)} exit={result.returncode} "
            f"stderr_len={len(result.stderr)} dest_present={ws.path_is_file(dest)}",
            flush=True,
        )
        assert result.returncode in (0, 1), (
            f"truncated archive exited {result.returncode} (not 0 or 1); "
            f"stderr={result.stderr!r}"
        )
        if result.returncode == 0:
            assert ws.path_is_file(dest), (
                "truncated expand exited 0 but wrote no regular destination"
            )
            assert ws.read_bytes(dest) == original, (
                "truncated expand exited 0 with a destination that is not "
                "the original source of that archive"
            )
        else:
            assert result.stderr, (
                f"truncated expand exited 1 with empty stderr; stdout={result.stdout!r}"
            )
    return len(lengths)


def test_truncated_archive_stays_in_exit_0_or_1():
    with workspace() as ws:
        src = _place_runtime_vorbis(ws)
        n = _truncated_archive_case(ws, src)
        assert n >= 2


def test_opus_truncated_archive_stays_in_exit_0_or_1():
    with workspace() as ws:
        src = _place_runtime_opus(ws)
        _prove_family0(ws.read_bytes(src), what="Opus truncation host")
        n = _truncated_archive_case(ws, src)
        assert n >= 2


# ---------------------------------------------------------------------------
# I. Interior-flipped archive stays in exit {0, 1}
# ---------------------------------------------------------------------------


def _flipped_archive_case(ws, src_a: str, src_b: str):
    original = ws.read_bytes(src_a)
    arc_b = live_compress(ws, src_b)
    archive = live_compress(ws, src_a)
    recovered = unique_name("flip-ok")
    dec = run_product(ws, ["d", archive, recovered])
    require_ok(dec)
    assert ws.read_bytes(recovered) == original, (
        "baseline expand of the intact archive did not restore the original"
    )
    blob = ws.read_bytes(archive)
    prefix = shared_prefix_len(blob, ws.read_bytes(arc_b))
    if prefix >= len(blob):
        raise HarnessError("archives share every byte; no payload offset to flip")
    payload = list(range(prefix, len(blob)))
    if not payload:
        raise HarnessError("no payload byte after the shared prefix")
    offsets = [secrets.choice(payload)]
    if len(payload) > 1:
        extra = secrets.choice(payload)
        if extra != offsets[0]:
            offsets.append(extra)
    seen = 0
    for offset in offsets:
        xor_val = secrets.randbelow(255) + 1
        flipped = bytearray(blob)
        flipped[offset] ^= xor_val
        cut = unique_name("flip")
        dest = unique_name("flip-out")
        ws.write(cut, bytes(flipped))
        result = run_product(ws, ["d", cut, dest])
        print(
            f"[F05] flipped offset={offset} xor={xor_val} exit={result.returncode} "
            f"stderr_len={len(result.stderr)} dest_present={ws.path_is_file(dest)}",
            flush=True,
        )
        assert result.returncode in (0, 1), (
            f"interior-flipped archive exited {result.returncode} (not 0 or 1); "
            f"stderr={result.stderr!r}"
        )
        if result.returncode == 0:
            assert ws.path_is_file(dest), (
                "interior-flipped expand exited 0 but wrote no regular destination"
            )
        else:
            assert result.stderr, (
                f"interior-flipped expand exited 1 with empty stderr; "
                f"stdout={result.stdout!r}"
            )
        seen += 1
    return seen


def test_interior_flipped_archive_stays_in_exit_0_or_1():
    with workspace() as ws:
        src_a = _place_runtime_vorbis(ws, which="a")
        src_b = _place_runtime_vorbis(ws, which="b")
        n = _flipped_archive_case(ws, src_a, src_b)
        assert n >= 1


def test_opus_interior_flipped_archive_stays_in_exit_0_or_1():
    with workspace() as ws:
        src_a = opus_with_runtime_tags(ws, "silk")
        src_b = opus_with_runtime_tags(ws, "celt")
        _prove_family0(ws.read_bytes(src_a), what="Opus flip host a")
        _prove_family0(ws.read_bytes(src_b), what="Opus flip host b")
        n = _flipped_archive_case(ws, src_a, src_b)
        assert n >= 1


# ---------------------------------------------------------------------------
# J. Refusal stderr identifies the offending input
# ---------------------------------------------------------------------------


def test_refusal_stderr_identifies_the_offending_input():
    with workspace() as ws:
        host = _place_runtime_vorbis(ws)
        live_compress(ws, host)
        original = ws.read_bytes(host)
        mutated = corrupt_stored_page_checksum(original, 0)
        prove_checksum_mismatch(mutated, 0)
        path_a = unique_name("named-a") + ".ogg"
        path_b = unique_name("named-b") + ".ogg"
        assert path_a != path_b
        ws.write(path_a, mutated)
        mutated_b = corrupt_stored_page_checksum(original, 0)
        ws.write(path_b, mutated_b)
        dest_a = unique_name("named-a-arc")
        dest_b = unique_name("named-b-arc")
        run_a = refuse_compress(ws, path_a, dest_a)
        run_b = refuse_compress(ws, path_b, dest_b)
        name_a = path_a
        name_b = path_b
        base_a = name_a.rsplit("/", 1)[-1]
        base_b = name_b.rsplit("/", 1)[-1]
        text_a = run_a.stderr_text
        text_b = run_b.stderr_text
        assert base_a in text_a, (
            f"stderr for {path_a!r} does not name that input; stderr={text_a!r}"
        )
        assert base_b not in text_a, (
            f"stderr for {path_a!r} names the other input {path_b!r}; stderr={text_a!r}"
        )
        assert base_b in text_b, (
            f"stderr for {path_b!r} does not name that input; stderr={text_b!r}"
        )
        assert base_a not in text_b, (
            f"stderr for {path_b!r} names the other input {path_a!r}; stderr={text_b!r}"
        )
        print(
            f"[F05] named-input a={base_a!r} b={base_b!r} "
            f"stderr_a_len={len(text_a)} stderr_b_len={len(text_b)}",
            flush=True,
        )
