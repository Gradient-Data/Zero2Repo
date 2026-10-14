# feature: F02
"""Acceptance: lossless Ogg Vorbis compress and expand."""

from __future__ import annotations

import secrets

# Load this feature's helpers first so a mount that ships helpers but not
# the shared harness can still import the predecessor.
import F02_helpers  # noqa: F401

from F01_helpers import (
    place_non_ogg,
    place_opus,
    place_vorbis,
    require_bytes_unchanged,
    require_file_access,
    require_ok,
    require_refusal,
    run_product,
    token,
    unique_name,
)
from F02_helpers import (
    append_trailing_pages,
    canonical_interior_byte_length,
    complete_packets,
    feed_fifo,
    first_complete_packet,
    first_type2_lookup,
    floor0_headers,
    interior_audio_packet,
    interior_audio_symbol_key,
    interior_audio_symbol_key_implicit_zeros,
    interior_floor_subclass_choices,
    is_opus_head,
    is_vorbis_ident,
    neither_ident_page,
    place_floor_source,
    place_opus_without_opus_suffix,
    place_vorbis_without_ogg_suffix,
    replace_vorbis_comment,
    require_no_usable_compress_dest,
    require_no_usable_expand_dest,
    require_refusal_distinct_from,
    require_refusal_names_input,
    roundtrip,
    prove_floor_type_code_over_floor1,
    prove_lookup_type_code_over_type1,
    set_codebook_lookup_type,
    set_setup_floor_type,
    with_floor_type_code_over_floor1,
    with_lookup_type_code_over_type1,
    stop_fifo_feeder,
    with_alternative_floor1_subclass,
    with_interior_unused_zero_padding,
    with_shorter_than_canonical_interior_packet,
)
from _harness import files_identical, stored_copy, workspace


# ---------------------------------------------------------------------------
# A. Single-file lossless round-trip
# ---------------------------------------------------------------------------


def test_two_distinct_vorbis_files_round_trip_byte_identical():
    with workspace() as ws:
        seen: list[bytes] = []
        for which in ("a", "b"):
            src = place_vorbis(ws, which)
            src_bytes = ws.read_bytes(src)
            seen.append(src_bytes)
            dest = roundtrip(ws, src)
            dest_bytes = ws.read_bytes(dest)
            print(
                f"[F02] A {which} src={len(src_bytes)} dest={len(dest_bytes)}",
                flush=True,
            )
        assert seen[0] != seen[1], "suite Vorbis fixtures were not distinct"


# ---------------------------------------------------------------------------
# B. Compress detects Vorbis from the first Ogg page
# ---------------------------------------------------------------------------


def test_opushead_first_page_is_not_vorbis_refusal():
    with workspace() as ws:
        baseline = place_vorbis(ws, "a")
        roundtrip(ws, baseline, dest=unique_name("base-arc"))
        src = place_opus(ws)
        src_bytes = ws.read_bytes(src)
        dest = unique_name("opus-arc")
        enc = run_product(ws, ["e", src, dest])
        require_ok(enc)
        assert ws.path_is_file(dest), "OpusHead compress did not write a destination"
        dest_bytes = ws.read_bytes(dest)
        assert not stored_copy(dest_bytes, src_bytes), (
            "OpusHead compress destination bytes carry the source verbatim"
        )
        recovered = unique_name("opus-out")
        dec = run_product(ws, ["d", dest, recovered])
        require_ok(dec)
        assert ws.path_is_file(recovered), (
            "expand of the OpusHead archive did not write a destination"
        )
        assert files_identical(ws.resolve(src), ws.resolve(recovered)), (
            "expand of the OpusHead archive did not restore the original bytes"
        )
        print(
            f"[F02] OpusHead first page compress src={len(src_bytes)} "
            f"dest={len(dest_bytes)} recovered={ws.file_size(recovered)}",
            flush=True,
        )


def test_ogg_first_page_neither_ident_is_refused():
    with workspace() as ws:
        baseline = place_vorbis(ws, "a")
        roundtrip(ws, baseline, dest=unique_name("base-arc"))
        src = unique_name("neither") + ".ogg"
        assert src.endswith(".ogg") and baseline.endswith(".ogg"), (
            f"neither-ident paths do not share an .ogg suffix: {baseline!r} {src!r}"
        )
        ws.write(src, neither_ident_page())
        pkt = first_complete_packet(ws.read_bytes(src))
        assert not is_vorbis_ident(pkt) and not is_opus_head(pkt), (
            "neither-ident fixture named a Vorbis or Opus identification header"
        )
        dest = unique_name("neither-arc")
        enc = run_product(ws, ["e", src, dest])
        require_refusal(enc)
        require_refusal_names_input(enc, src)
        require_no_usable_compress_dest(ws, dest)


def test_vorbis_ident_on_a_later_page_is_refused():
    with workspace() as ws:
        baseline = place_vorbis(ws, "a")
        vorbis = ws.read_bytes(baseline)
        roundtrip(ws, baseline, dest=unique_name("base-arc"))
        src = unique_name("later-ident") + ".ogg"
        assert src.endswith(".ogg") and baseline.endswith(".ogg"), (
            f"later-page paths do not share an .ogg suffix: {baseline!r} {src!r}"
        )
        ws.write(src, append_trailing_pages(neither_ident_page(), vorbis))
        dest = unique_name("later-arc")
        enc = run_product(ws, ["e", src, dest])
        require_refusal(enc)
        assert enc.returncode == 1, (
            f"later-page ident compress exited {enc.returncode}; "
            f"stderr={enc.stderr!r}"
        )
        assert enc.stderr, (
            f"later-page ident compress left stderr empty; stdout={enc.stdout!r}"
        )
        require_refusal_names_input(enc, src)
        require_no_usable_compress_dest(ws, dest)


def test_vorbis_round_trip_without_ogg_suffix():
    with workspace() as ws:
        src = place_vorbis_without_ogg_suffix(ws, "a")
        assert not src.endswith(".ogg") and not src.endswith(".opus")
        roundtrip(ws, src)


def test_opushead_without_opus_suffix_compresses():
    with workspace() as ws:
        src = place_opus_without_opus_suffix(ws)
        assert not src.endswith(".ogg") and not src.endswith(".opus")
        src_bytes = ws.read_bytes(src)
        dest = unique_name("opus-nosuf-arc")
        enc = run_product(ws, ["e", src, dest])
        require_ok(enc)
        assert ws.path_is_file(dest), "unnamed OpusHead compress did not write dest"
        dest_bytes = ws.read_bytes(dest)
        assert not stored_copy(dest_bytes, src_bytes), (
            "unnamed OpusHead compress destination bytes carry the source verbatim"
        )
        recovered = unique_name("opus-nosuf-out")
        dec = run_product(ws, ["d", dest, recovered])
        require_ok(dec)
        assert ws.path_is_file(recovered), (
            "expand of the unsuffixed OpusHead archive did not write a destination"
        )
        assert files_identical(ws.resolve(src), ws.resolve(recovered)), (
            "expand of the unsuffixed OpusHead archive did not restore the source"
        )
        print(
            f"[F02] OpusHead without suffix src={len(src_bytes)} "
            f"dest={len(dest_bytes)} recovered={ws.file_size(recovered)}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# C. Expand detects a Vorbis archive from the archive header
# ---------------------------------------------------------------------------


def test_expand_archive_named_ogg_recovers():
    with workspace() as ws:
        src = place_vorbis(ws, "a")
        dest = unique_name("arc") + ".ogg"
        assert dest.endswith(".ogg")
        roundtrip(ws, src, dest=dest)


def test_expand_raw_vorbis_is_refused():
    with workspace() as ws:
        src = place_vorbis(ws, "a")
        ogg = ws.read_bytes(src)
        for dest in (unique_name("from-ogg") + ".ogg", unique_name("from-ogg")):
            result = run_product(ws, ["d", src, dest])
            require_refusal(result)
            assert result.returncode == 1, (
                f"expand of raw Vorbis to {dest!r} exited {result.returncode}; "
                f"stderr={result.stderr!r}"
            )
            assert result.stderr, (
                f"expand of raw Vorbis to {dest!r} left stderr empty; "
                f"stdout={result.stdout!r}"
            )
            require_no_usable_expand_dest(ws, dest, ogg)


# ---------------------------------------------------------------------------
# D. Determinism and --no-mmap
# ---------------------------------------------------------------------------


def test_two_compress_invocations_write_identical_archives():
    for effort in ((), ("-1",)):
        with workspace() as ws:
            src = place_vorbis(ws, "a")
            src_bytes = ws.read_bytes(src)
            dest_a = unique_name("arc-a")
            dest_b = unique_name("arc-b")
            enc_a = run_product(ws, [*effort, "e", src, dest_a])
            require_ok(enc_a)
            enc_b = run_product(ws, [*effort, "e", src, dest_b])
            require_ok(enc_b)
            assert ws.path_is_file(dest_a), "first compress did not write a destination"
            assert ws.path_is_file(dest_b), "second compress did not write a destination"
            dest_a_bytes = ws.read_bytes(dest_a)
            dest_b_bytes = ws.read_bytes(dest_b)
            assert not stored_copy(dest_a_bytes, src_bytes), (
                "first compress destination bytes carry the source verbatim (copy stub)"
            )
            assert not stored_copy(dest_b_bytes, src_bytes), (
                "second compress destination bytes carry the source verbatim (copy stub)"
            )
            recovered = unique_name("from-a")
            dec = run_product(ws, ["d", dest_a, recovered])
            require_ok(dec)
            assert ws.path_is_file(recovered), (
                "expand of the first archive did not write a destination"
            )
            assert files_identical(ws.resolve(src), ws.resolve(recovered)), (
                "expand of the first archive did not restore the original bytes"
            )
            assert files_identical(ws.resolve(dest_a), ws.resolve(dest_b)), (
                f"two compressions of the same input, effort {effort!r}, and options differed"
            )
            print(
                f"[F02] two compressions src={len(src_bytes)} "
                f"arc={len(dest_a_bytes)} recovered={ws.file_size(recovered)}",
                flush=True,
            )


def test_no_mmap_compress_matches_mapped_archive():
    for effort in ((), ("-1",)):
        with workspace() as ws:
            src = place_vorbis(ws, "a")
            src_bytes = ws.read_bytes(src)
            mapped = unique_name("mapped")
            unmapped = unique_name("unmapped")
            enc_m = run_product(ws, [*effort, "e", src, mapped])
            require_ok(enc_m)
            assert ws.path_is_file(mapped), "mapped compress did not write a destination"
            mapped_bytes = ws.read_bytes(mapped)
            assert not stored_copy(mapped_bytes, src_bytes), (
                "mapped compress destination bytes carry the source verbatim (copy stub)"
            )
            recovered = unique_name("mapped-out")
            dec = run_product(ws, ["d", mapped, recovered])
            require_ok(dec)
            assert ws.path_is_file(recovered), (
                "expand of the mapped archive did not write a destination"
            )
            assert files_identical(ws.resolve(src), ws.resolve(recovered)), (
                "expand of the mapped archive did not restore the original bytes"
            )
            enc_u = run_product(ws, ["--no-mmap", *effort, "e", src, unmapped])
            require_ok(enc_u)
            assert ws.path_is_file(unmapped), (
                "--no-mmap compress did not write a destination"
            )
            assert files_identical(ws.resolve(mapped), ws.resolve(unmapped)), (
                f"--no-mmap changed archive bytes versus effort {effort!r} without it"
            )
            print(
                f"[F02] no-mmap compress src={len(src_bytes)} "
                f"mapped={len(mapped_bytes)} recovered={ws.file_size(recovered)}",
                flush=True,
            )


def test_no_mmap_expand_recovers_original():
    with workspace() as ws:
        src = place_vorbis(ws, "a")
        src_bytes = ws.read_bytes(src)
        dest = unique_name("arc")
        enc = run_product(ws, ["e", src, dest])
        require_ok(enc)
        assert ws.path_is_file(dest), "compress did not write a destination"
        dest_bytes = ws.read_bytes(dest)
        assert not stored_copy(dest_bytes, src_bytes), (
            "compress destination bytes carry the source verbatim (copy stub)"
        )
        recovered = unique_name("out")
        dec = run_product(ws, ["--no-mmap", "d", dest, recovered])
        require_ok(dec)
        assert files_identical(ws.resolve(src), ws.resolve(recovered)), (
            "--no-mmap expand did not restore the original bytes"
        )


# ---------------------------------------------------------------------------
# E. Extra unused-zero padding and shortened unused padding
# ---------------------------------------------------------------------------


def test_extra_interior_audio_padding_round_trips_at_effort_1_and_9():
    with workspace() as ws:
        baseline = place_vorbis(ws, "b")
        original = ws.read_bytes(baseline)
        roundtrip(ws, baseline, effort="-1", dest=unique_name("base-arc"))
        padded = with_interior_unused_zero_padding(original)
        assert padded != original, "extra padding left the file unchanged"
        src = unique_name("padded") + ".ogg"
        ws.write(src, padded)
        for effort in ("-1", "-9"):
            roundtrip(ws, src, effort=effort, dest=unique_name(f"pad-{effort}"))


def test_shortened_interior_audio_packet_round_trips_at_effort_1_and_9():
    with workspace() as ws:
        baseline = place_vorbis(ws, "b")
        original = ws.read_bytes(baseline)
        roundtrip(ws, baseline, dest=unique_name("base-arc"))
        shortened = with_shorter_than_canonical_interior_packet(original)
        orig_pkt = interior_audio_packet(original)
        short_pkt = interior_audio_packet(shortened)
        canon = canonical_interior_byte_length(original)
        assert len(short_pkt) < canon, (
            "interior audio packet is not shorter than a canonical encoding "
            f"({len(short_pkt)} >= {canon})"
        )
        assert short_pkt == orig_pkt[: len(short_pkt)], (
            "shortened packet is not a prefix of the original canonical bytes"
        )
        omitted = orig_pkt[len(short_pkt) : canon]
        assert omitted and all(byte == 0 for byte in omitted), (
            "bytes omitted from the canonical encoding are not a zero tail"
        )
        assert interior_audio_symbol_key(original) == (
            interior_audio_symbol_key_implicit_zeros(shortened)
        ), "shortened packet does not encode the same symbols"
        orig_payloads = complete_packets(original)
        short_payloads = complete_packets(shortened)
        assert len(orig_payloads) == len(short_payloads), (
            "shortened file changed the packet count"
        )
        changed = [
            i
            for i, (left, right) in enumerate(zip(orig_payloads, short_payloads))
            if left != right
        ]
        assert changed == [orig_payloads.index(orig_pkt)], (
            f"shortened file changed packets {changed}, not only the interior audio packet"
        )
        assert shortened != original, "shortened file equals the baseline"
        print(
            f"[F02] shorter-than-canonical interior packet "
            f"canonical={canon} short={len(short_pkt)}",
            flush=True,
        )
        src = unique_name("short") + ".ogg"
        ws.write(src, shortened)
        for effort in ("-1", "-9"):
            roundtrip(ws, src, effort=effort, dest=unique_name(f"short-{effort}"))


# ---------------------------------------------------------------------------
# F. Alternative floor subclass
# ---------------------------------------------------------------------------


def test_alternative_floor_subclass_round_trips_at_effort_1_and_9():
    with workspace() as ws:
        baseline = place_floor_source(ws)
        original = ws.read_bytes(baseline)
        roundtrip(ws, baseline, dest=unique_name("base-arc"))
        variant = with_alternative_floor1_subclass(original)
        assert variant != original, "floor subclass mutant equals the baseline"
        assert interior_floor_subclass_choices(variant) != (
            interior_floor_subclass_choices(original)
        ), "interior floor subclass choice did not change"
        orig_payloads = complete_packets(original)
        var_payloads = complete_packets(variant)
        assert len(orig_payloads) == len(var_payloads), (
            "floor-subclass file changed the packet count"
        )
        changed = [
            i
            for i, (left, right) in enumerate(zip(orig_payloads, var_payloads))
            if left != right
        ]
        assert len(changed) == 1, (
            f"floor-subclass file changed packets {changed}, not one interior packet"
        )
        src = unique_name("floor-alt") + ".ogg"
        ws.write(src, variant)
        roundtrip(ws, src, dest=unique_name("floor-arc"))


# ---------------------------------------------------------------------------
# G. Comment packets are original bytes
# ---------------------------------------------------------------------------


def test_larger_comment_with_vendor_repeats_and_picture_round_trips():
    with workspace() as ws:
        baseline = place_vorbis(ws, "a")
        original = ws.read_bytes(baseline)
        roundtrip(ws, baseline, dest=unique_name("base-arc"))
        vendor = f"suite-vendor-{token()}".encode("ascii")
        title_a = f"TITLE={token()}".encode("ascii")
        title_b = f"TITLE={token()}".encode("ascii")
        assert title_a != title_b, "repeated TITLE values were not distinct"
        picture = b"METADATA_BLOCK_PICTURE=" + secrets.token_bytes(48)
        extra = (f"NOTE={token()}".encode("ascii")) * 32
        constructed = replace_vorbis_comment(
            original, vendor=vendor, fields=(title_a, title_b, picture, extra)
        )
        assert len(constructed) > len(original), "constructed file is not larger"
        src = unique_name("comment") + ".ogg"
        ws.write(src, constructed)
        roundtrip(ws, src)


# ---------------------------------------------------------------------------
# H. Wrong-type refusals this slice owns
# ---------------------------------------------------------------------------


def test_compress_of_non_ogg_is_refused():
    with workspace() as ws:
        baseline = place_vorbis(ws, "a")
        roundtrip(ws, baseline, dest=unique_name("base-arc"))
        src = place_non_ogg(ws)
        dest = unique_name("nonogg-arc")
        enc = run_product(ws, ["e", src, dest])
        require_refusal(enc)
        assert enc.returncode == 1, (
            f"non-Ogg compress exited {enc.returncode}; stderr={enc.stderr!r}"
        )
        assert enc.stderr, (
            f"non-Ogg compress left stderr empty; stdout={enc.stdout!r}"
        )
        require_refusal_names_input(enc, src)
        require_no_usable_compress_dest(ws, dest)


def test_compress_of_archive_is_refused():
    with workspace() as ws:
        src = place_vorbis(ws, "a")
        arc = roundtrip(ws, src, dest=unique_name("ok-arc"))
        dest2 = unique_name("from-arc")
        enc = run_product(ws, ["e", arc, dest2])
        require_refusal(enc)
        assert enc.returncode == 1, (
            f"compress of archive exited {enc.returncode}; stderr={enc.stderr!r}"
        )
        assert enc.stderr, (
            f"compress of archive left stderr empty; stdout={enc.stdout!r}"
        )
        require_refusal_names_input(enc, arc)
        require_no_usable_compress_dest(ws, dest2)
        ogg = ws.read_bytes(src)
        expand_dest = unique_name("from-ogg")
        expanded = run_product(ws, ["d", src, expand_dest])
        require_refusal(expanded)
        assert expanded.returncode == 1, (
            f"expand of raw Vorbis exited {expanded.returncode}; "
            f"stderr={expanded.stderr!r}"
        )
        assert expanded.stderr, (
            f"expand of raw Vorbis left stderr empty; stdout={expanded.stdout!r}"
        )
        require_no_usable_expand_dest(ws, expand_dest, ogg)
        require_refusal_distinct_from(
            expanded, src, enc, arc, expand_dest, dest2
        )


# ---------------------------------------------------------------------------
# I. Unsupported Vorbis: floor type 0 and codebook lookup type 2
# ---------------------------------------------------------------------------


def test_floor_type_0_is_refused():
    with workspace() as ws:
        baseline = place_vorbis(ws, "a")
        original = ws.read_bytes(baseline)
        roundtrip(ws, baseline, dest=unique_name("base-arc"))
        mutated = set_setup_floor_type(original, 0)
        headers = floor0_headers(mutated)
        assert headers, "floor type 0 file has no floor header"
        for order, rate, bark, books in headers:
            assert order >= 1 and rate >= 1 and bark >= 1, (
                "floor type 0 header is not a Vorbis I floor header "
                f"(order={order}, rate={rate}, bark_map_size={bark})"
            )
            assert books, "floor type 0 header names no codebook"
        print(
            f"[F02] floor0 headers={len(headers)} "
            f"order={headers[0][0]} rate={headers[0][1]} bark={headers[0][2]}",
            flush=True,
        )
        src = unique_name("floor0") + ".ogg"
        ws.write(src, mutated)
        dest = unique_name("floor0-arc")
        enc = run_product(ws, ["e", src, dest])
        require_refusal(enc)
        assert enc.returncode == 1, (
            f"floor type 0 compress exited {enc.returncode}; stderr={enc.stderr!r}"
        )
        assert enc.stderr, (
            f"floor type 0 compress left stderr empty; stdout={enc.stdout!r}"
        )
        require_no_usable_compress_dest(ws, dest)


def test_codebook_lookup_type_2_is_refused():
    with workspace() as ws:
        baseline = place_vorbis(ws, "a")
        original = ws.read_bytes(baseline)
        roundtrip(ws, baseline, dest=unique_name("base-arc"))
        mutated = set_codebook_lookup_type(original, 2)
        dim, ent, count, type1 = first_type2_lookup(mutated)
        assert count == ent * dim, (
            "lookup type 2 does not carry one multiplicand per entry "
            f"per dimension ({ent} entries, {dim} dimensions, {count} values)"
        )
        assert count != type1, (
            "lookup type 2 multiplicand vector still has the type-1 length "
            f"{type1}"
        )
        print(
            f"[F02] lookup2 dim={dim} entries={ent} "
            f"multiplicands={count} type1={type1}",
            flush=True,
        )
        src = unique_name("lookup2") + ".ogg"
        ws.write(src, mutated)
        dest = unique_name("lookup2-arc")
        enc = run_product(ws, ["e", src, dest])
        require_refusal(enc)
        assert enc.returncode == 1, (
            f"lookup type 2 compress exited {enc.returncode}; stderr={enc.stderr!r}"
        )
        assert enc.stderr, (
            f"lookup type 2 compress left stderr empty; stdout={enc.stdout!r}"
        )
        floor_src = unique_name("floor0") + ".ogg"
        ws.write(floor_src, set_setup_floor_type(original, 0))
        floor_dest = unique_name("floor0-arc")
        floor_enc = run_product(ws, ["e", floor_src, floor_dest])
        require_refusal(floor_enc)
        require_no_usable_compress_dest(ws, dest)
        require_no_usable_compress_dest(ws, floor_dest)


def test_floor_type_code_0_over_floor1_body_is_refused():
    with workspace() as ws:
        baseline = place_vorbis(ws, "a")
        original = ws.read_bytes(baseline)
        roundtrip(ws, baseline, dest=unique_name("base-arc"))
        mutated = with_floor_type_code_over_floor1(original)
        nfloors = prove_floor_type_code_over_floor1(mutated)
        assert nfloors >= 1, "floor type code 0 file names no floors"
        print(f"[F02] floor type code 0 over Floor1 floors={nfloors}", flush=True)
        src = unique_name("floor-code0") + ".ogg"
        ws.write(src, mutated)
        dest = unique_name("floor-code0-arc")
        enc = run_product(ws, ["e", src, dest])
        require_refusal(enc)
        assert enc.returncode == 1, (
            f"floor type code 0 over Floor1 exited {enc.returncode}; "
            f"stderr={enc.stderr!r}"
        )
        assert enc.stderr, (
            f"floor type code 0 over Floor1 left stderr empty; "
            f"stdout={enc.stdout!r}"
        )
        other = with_lookup_type_code_over_type1(original)
        dim, ent_n, type1, type2 = prove_lookup_type_code_over_type1(other)
        assert type1 != type2, (
            "lookup type code 2 vector is not the type-1 length "
            f"({type1} vs one-per-entry {type2})"
        )
        print(
            f"[F02] lookup type code 2 over type-1 dim={dim} "
            f"entries={ent_n} type1={type1} type2={type2}",
            flush=True,
        )
        other_src = unique_name("look-code2") + ".ogg"
        ws.write(other_src, other)
        other_dest = unique_name("look-code2-arc")
        other_enc = run_product(ws, ["e", other_src, other_dest])
        require_refusal(other_enc)
        assert other_enc.returncode == 1, (
            f"lookup type code 2 over type-1 exited {other_enc.returncode}; "
            f"stderr={other_enc.stderr!r}"
        )
        assert other_enc.stderr, (
            f"lookup type code 2 over type-1 left stderr empty; "
            f"stdout={other_enc.stdout!r}"
        )
        require_no_usable_compress_dest(ws, dest)
        require_no_usable_compress_dest(ws, other_dest)


# ---------------------------------------------------------------------------
# J. Non-seekable operand is file-access, not silent truncation
# ---------------------------------------------------------------------------


def test_nonseekable_compress_input_is_file_access():
    with workspace() as ws:
        regular = place_vorbis_without_ogg_suffix(ws, "a")
        assert not regular.endswith(".ogg") and not regular.endswith(".opus"), (
            f"seekable compress input still has a codec suffix: {regular!r}"
        )
        vorbis = ws.read_bytes(regular)
        roundtrip(ws, regular, dest=unique_name("base-arc"))
        fifo = unique_name("in-fifo")
        assert not fifo.endswith(".ogg") and not fifo.endswith(".opus"), (
            f"non-seekable compress input has a codec suffix: {fifo!r}"
        )
        ws.make_fifo(fifo)
        dest = unique_name("fifo-arc")
        writer = feed_fifo(ws.resolve(fifo), vorbis)
        result = run_product(ws, ["e", fifo, dest])
        stop_fifo_feeder(writer, ws.resolve(fifo))
        require_file_access(result)
        assert result.returncode == 3, (
            f"non-seekable compress input exited {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert result.stderr, (
            f"non-seekable compress input left stderr empty; "
            f"stdout={result.stdout!r}"
        )


def test_nonseekable_compress_output_is_file_access():
    with workspace() as ws:
        src = place_vorbis(ws, "a")
        seek_out = unique_name("seek-out")
        ws.write(seek_out, b"preexisting")
        assert seek_out != src
        assert ws.path_is_file(seek_out), (
            "seekable compress output was not an existing regular file"
        )
        roundtrip(ws, src, dest=seek_out)
        fifo = unique_name("out-fifo")
        ws.make_fifo(fifo)
        assert not ws.path_is_file(fifo), (
            "non-seekable compress output is a regular file"
        )
        result = run_product(ws, ["e", src, fifo])
        require_file_access(result)
        assert result.returncode == 3, (
            f"non-seekable compress output exited {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert result.stderr, (
            f"non-seekable compress output left stderr empty; "
            f"stdout={result.stdout!r}"
        )


def test_nonseekable_expand_input_is_file_access():
    with workspace() as ws:
        src = place_vorbis(ws, "a")
        arc = unique_name("arc")
        enc = run_product(ws, ["e", src, arc])
        require_ok(enc)
        recovered = unique_name("seekable-out")
        baseline = run_product(ws, ["d", arc, recovered])
        require_ok(baseline)
        assert files_identical(ws.resolve(src), ws.resolve(recovered)), (
            "expand of the archive to a seekable dest did not restore the original"
        )
        archive = ws.read_bytes(arc)
        print(
            f"[F02] J expand-in archive={len(archive)} "
            f"recovered={ws.file_size(recovered)}",
            flush=True,
        )
        fifo = unique_name("exp-in-fifo")
        ws.make_fifo(fifo)
        dest = unique_name("from-fifo")
        writer = feed_fifo(ws.resolve(fifo), archive)
        result = run_product(ws, ["d", fifo, dest])
        stop_fifo_feeder(writer, ws.resolve(fifo))
        require_file_access(result)
        assert result.returncode == 3, (
            f"non-seekable expand input exited {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert result.stderr, (
            f"non-seekable expand input left stderr empty; "
            f"stdout={result.stdout!r}"
        )


def test_nonseekable_expand_output_is_file_access():
    with workspace() as ws:
        src = place_vorbis(ws, "a")
        arc = unique_name("arc")
        enc = run_product(ws, ["e", src, arc])
        require_ok(enc)
        archive = ws.read_bytes(arc)
        recovered = unique_name("seekable-out")
        ws.write(recovered, b"preexisting")
        assert recovered != arc
        assert ws.path_is_file(recovered), (
            "seekable expand output was not an existing regular file"
        )
        baseline = run_product(ws, ["d", arc, recovered])
        require_ok(baseline)
        assert files_identical(ws.resolve(src), ws.resolve(recovered)), (
            "expand of the archive to a seekable dest did not restore the original"
        )
        print(
            f"[F02] J expand-out archive={len(archive)} "
            f"recovered={ws.file_size(recovered)}",
            flush=True,
        )
        fifo = unique_name("exp-out-fifo")
        ws.make_fifo(fifo)
        assert not ws.path_is_file(fifo), (
            "non-seekable expand output is a regular file"
        )
        result = run_product(ws, ["d", arc, fifo])
        require_file_access(result)
        assert result.returncode == 3, (
            f"non-seekable expand output exited {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert result.stderr, (
            f"non-seekable expand output left stderr empty; "
            f"stdout={result.stdout!r}"
        )


# ---------------------------------------------------------------------------
# K. Same path as input and output is file-access; bytes stay
# ---------------------------------------------------------------------------


def test_compress_same_path_is_file_access_and_preserves_bytes():
    with workspace() as ws:
        src = place_vorbis(ws, "a")
        original = ws.read_bytes(src)
        distinct = unique_name("other-arc")
        enc = run_product(ws, ["e", src, distinct])
        require_ok(enc)
        assert ws.path_is_file(distinct), (
            "distinct-path compress did not write a destination"
        )
        recovered = unique_name("from-distinct")
        dec = run_product(ws, ["d", distinct, recovered])
        require_ok(dec)
        assert ws.read_bytes(recovered) == original, (
            "expand of the distinct-path archive did not restore the original"
        )
        before = ws.read_bytes(src)
        result = run_product(ws, ["e", src, src])
        require_file_access(result)
        require_bytes_unchanged(ws, src, before)
        assert result.returncode == 3, (
            f"compress same-path exited {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert result.stderr, (
            f"compress same-path left stderr empty; stdout={result.stdout!r}"
        )
        assert ws.read_bytes(src) == before, (
            f"compress same-path changed input bytes of {src!r}"
        )
        print(f"[F02] K compress same-path bytes={len(before)}", flush=True)


def test_expand_same_path_is_file_access_and_preserves_bytes():
    with workspace() as ws:
        src = place_vorbis(ws, "a")
        archive = unique_name("same-arc")
        enc = run_product(ws, ["e", src, archive])
        require_ok(enc)
        recovered = unique_name("seekable-out")
        baseline = run_product(ws, ["d", archive, recovered])
        require_ok(baseline)
        assert files_identical(ws.resolve(src), ws.resolve(recovered)), (
            "expand of the archive to a distinct dest did not restore the original"
        )
        before = ws.read_bytes(archive)
        result = run_product(ws, ["d", archive, archive])
        require_file_access(result)
        require_bytes_unchanged(ws, archive, before)
        assert result.returncode == 3, (
            f"expand same-path exited {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert result.stderr, (
            f"expand same-path left stderr empty; stdout={result.stdout!r}"
        )
        assert ws.read_bytes(archive) == before, (
            f"expand same-path changed archive bytes of {archive!r}"
        )
        print(f"[F02] K expand same-path bytes={len(before)}", flush=True)


# ---------------------------------------------------------------------------
# Expand needs only the archive (Vorbis)
# ---------------------------------------------------------------------------


def test_vorbis_archive_alone_expands_after_every_compress_trace_is_gone():
    from F04_helpers import (
        _SCALE_FILES,
        _read_fixture,
        _vorbis_comment_variant,
        expand_from_archive_alone,
    )

    for fixture in (_SCALE_FILES[1], _SCALE_FILES[2]):
        src_bytes = _vorbis_comment_variant(_read_fixture(fixture))
        for effort in ("-1", "-9"):
            expand_from_archive_alone(
                src_bytes, effort, ".ogg", what=f"Vorbis {fixture.name} {effort}"
            )
