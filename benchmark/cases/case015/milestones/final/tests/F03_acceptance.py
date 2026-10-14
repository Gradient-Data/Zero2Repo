# feature: F03
"""Acceptance: lossless Ogg Opus compress and expand."""

from __future__ import annotations

from F01_helpers import (
    require_ok,
    require_refusal,
    run_product,
    token,
    unique_name,
)
from F02_helpers import (
    append_trailing_pages,
    complete_packets,
    first_complete_packet,
    is_opus_head,
    is_vorbis_ident,
    neither_ident_page,
    parse_ogg_pages,
    require_no_usable_compress_dest,
    require_no_usable_expand_dest,
    roundtrip,
)
from F03_helpers import (
    OPUS_MAX_PACKET,
    OPUS_TAGS_MAX,
    opus_head_fields,
    place_opus_classified,
    replace_opus_tags,
    require_codec_mode_field,
    rfc6716_config_kind,
    run_product_long,
    runtime_code3_target_below_cap,
    runtime_family0_illegal_channels,
    runtime_mapping_family,
    runtime_ogg_version,
    set_opus_head_channels,
    set_opus_head_family,
    states_decimal,
    with_first_audio_code3_padding,
    with_later_audio_code3_padding,
    with_ogg_version,
    with_opus_head_padded,
    without_paths,
)
from _harness import files_identical, stored_copy, workspace


# ---------------------------------------------------------------------------
# A. Family-0 SILK / CELT / hybrid lossless round-trip
# ---------------------------------------------------------------------------


def test_family0_silk_celt_hybrid_round_trip_byte_identical():
    with workspace() as ws:
        seen: list[bytes] = []
        kind_channels = {"silk": (1,), "celt": (2,), "hybrid": (1, 2)}
        for kind in ("silk", "celt", "hybrid"):
            src = place_opus_classified(ws, kind)
            src_bytes = ws.read_bytes(src)
            seen.append(src_bytes)
            packets = complete_packets(src_bytes)
            channels, family = opus_head_fields(packets[0])
            audio_kind = rfc6716_config_kind(packets[2])
            assert family == 0, (
                "supported streams are logical bitstreams with channel "
                "mapping family 0, as those terms are used in RFC 7845: "
                f"{kind} family is {family}, not 0"
            )
            assert channels in (1, 2), (
                "supported streams have one or two channels (mono or stereo), "
                "as those terms are used in RFC 7845: "
                f"{kind} channel count is {channels}"
            )
            assert channels in kind_channels[kind], (
                f"{kind} stream channel count is {channels}, "
                f"not {kind_channels[kind]}"
            )
            assert audio_kind == kind, (
                "SILK, CELT, and hybrid packets that appear in such a "
                f"stream are all in scope, as those terms are used in "
                f"RFC 7845: first audio TOC kind is {audio_kind!r}, "
                f"not {kind!r}"
            )
            dest = unique_name(f"arc-{kind}")
            recovered = unique_name(f"out-{kind}")
            enc = run_product(ws, ["-1", "e", src, dest])
            require_ok(enc)
            assert enc.returncode == 0, (
                f"{kind} compress exited {enc.returncode}, not 0; "
                f"stderr={enc.stderr!r}"
            )
            assert ws.path_is_file(dest), (
                f"{kind} compress did not write a destination"
            )
            dest_bytes = ws.read_bytes(dest)
            assert not stored_copy(dest_bytes, src_bytes), (
                f"{kind} compress destination bytes carry the source verbatim (copy stub)"
            )
            dec = run_product(ws, ["d", dest, recovered])
            require_ok(dec)
            assert dec.returncode == 0, (
                f"{kind} expand exited {dec.returncode}, not 0; "
                f"stderr={dec.stderr!r}"
            )
            assert files_identical(ws.resolve(src), ws.resolve(recovered)), (
                f"supported streams are logical bitstreams with channel "
                f"mapping family 0 and one or two channels: {kind} expand "
                "did not restore the original bytes"
            )
            recovered_bytes = ws.read_bytes(recovered)
            rec_packets = complete_packets(recovered_bytes)
            rec_channels, rec_family = opus_head_fields(rec_packets[0])
            rec_kind = rfc6716_config_kind(rec_packets[2])
            assert rec_family == 0, (
                "supported streams are logical bitstreams with channel "
                "mapping family 0, as those terms are used in RFC 7845: "
                f"recovered {kind} family is {rec_family}"
            )
            assert rec_channels in (1, 2), (
                "supported streams have one or two channels (mono or stereo), "
                "as those terms are used in RFC 7845: recovered "
                f"{kind} channel count is {rec_channels}"
            )
            assert rec_kind == kind, (
                "SILK, CELT, and hybrid packets that appear in such a "
                "stream are all in scope, as those terms are used in "
                f"RFC 7845: recovered {kind} first audio kind is {rec_kind!r}"
            )
            print(
                f"[F03] A {kind} family={family} channels={channels} "
                f"src={len(src_bytes)} dest={len(dest_bytes)}",
                flush=True,
            )
        assert seen[0] != seen[1] and seen[1] != seen[2] and seen[0] != seen[2], (
            "suite Opus fixtures were not three distinct byte strings"
        )
        print(
            "[F03] A in-scope: family-0 logical bitstreams, one or two "
            "channels (mono or stereo), SILK / CELT / hybrid packets",
            flush=True,
        )


# ---------------------------------------------------------------------------
# B. First-page OpusHead; expand from archive header
# ---------------------------------------------------------------------------


def test_opus_round_trip_without_codec_suffix():
    with workspace() as ws:
        src = place_opus_classified(ws, "silk", suffix="")
        assert not src.endswith(".opus") and not src.endswith(".ogg")
        roundtrip(ws, src, effort="-1")


def test_expand_opus_archive_named_ogg_recovers():
    with workspace() as ws:
        src = place_opus_classified(ws, "silk")
        dest = unique_name("arc") + ".ogg"
        assert dest.endswith(".ogg")
        roundtrip(ws, src, effort="-1", dest=dest)


def test_expand_opus_archive_named_opus_recovers():
    with workspace() as ws:
        src = place_opus_classified(ws, "silk")
        dest = unique_name("arc") + ".opus"
        assert dest.endswith(".opus")
        roundtrip(ws, src, effort="-1", dest=dest)


def test_opushead_on_later_page_is_refused():
    with workspace() as ws:
        baseline = place_opus_classified(ws, "silk")
        opus = ws.read_bytes(baseline)
        roundtrip(ws, baseline, effort="-1", dest=unique_name("base-arc"))
        src = unique_name("later-head")
        ws.write(src, append_trailing_pages(neither_ident_page(), opus))
        pkt = first_complete_packet(ws.read_bytes(src))
        assert not is_opus_head(pkt) and not is_vorbis_ident(pkt), (
            "later-page fixture named a Vorbis or Opus identification header "
            "on the first complete packet"
        )
        dest = unique_name("later-arc")
        enc = run_product(ws, ["e", src, dest])
        require_refusal(enc)
        require_no_usable_compress_dest(ws, dest)


# ---------------------------------------------------------------------------
# C. Expand of raw Opus is not an archive
# ---------------------------------------------------------------------------


def test_expand_raw_opus_is_refused():
    with workspace() as ws:
        named = place_opus_classified(ws, "silk")
        opus = ws.read_bytes(named)
        unnamed = unique_name("raw-opus")
        assert not unnamed.endswith(".opus") and not unnamed.endswith(".ogg")
        ws.write(unnamed, opus)
        for src, dest in (
            (unnamed, unique_name("from-raw")),
            (unnamed, unique_name("from-raw") + ".ogg"),
            (named, unique_name("from-opus")),
        ):
            result = run_product(ws, ["d", src, dest])
            require_refusal(result)
            require_no_usable_expand_dest(ws, dest, opus)
            print(f"[F03] C expand raw src={src!r} dest={dest!r}", flush=True)


# ---------------------------------------------------------------------------
# D. Determinism and --no-mmap
# ---------------------------------------------------------------------------


def test_two_opus_compress_invocations_write_identical_archives():
    for effort in ("-1", "-9"):
        with workspace() as ws:
            src = place_opus_classified(ws, "silk")
            src_bytes = ws.read_bytes(src)
            dest_a = unique_name("arc-a")
            dest_b = unique_name("arc-b")
            enc_a = run_product(ws, [effort, "e", src, dest_a])
            require_ok(enc_a)
            enc_b = run_product(ws, [effort, "e", src, dest_b])
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
            assert files_identical(ws.resolve(dest_a), ws.resolve(dest_b)), (
                "the same input compressed twice at the same effort, including "
                "in two process invocations, produces byte-identical archives"
            )
            dest_c = unique_name("arc-c")
            dest_d = unique_name("arc-d")
            enc_c = run_product(ws, [effort, "--no-mmap", "e", src, dest_c])
            require_ok(enc_c)
            enc_d = run_product(ws, [effort, "--no-mmap", "e", src, dest_d])
            require_ok(enc_d)
            assert ws.path_is_file(dest_c), (
                "first --no-mmap compress did not write a destination"
            )
            assert ws.path_is_file(dest_d), (
                "second --no-mmap compress did not write a destination"
            )
            dest_c_bytes = ws.read_bytes(dest_c)
            dest_d_bytes = ws.read_bytes(dest_d)
            assert not stored_copy(dest_c_bytes, src_bytes), (
                "first --no-mmap compress destination bytes carry the source verbatim"
            )
            assert not stored_copy(dest_d_bytes, src_bytes), (
                "second --no-mmap compress destination bytes carry the source verbatim"
            )
            assert files_identical(ws.resolve(dest_c), ws.resolve(dest_d)), (
                "the same input compressed twice at the same effort, including "
                "in two process invocations and with --no-mmap, produces "
                "byte-identical archives"
            )
            assert files_identical(ws.resolve(dest_a), ws.resolve(dest_c)), (
                "the same input compressed twice at the same effort, including "
                "in two process invocations and with --no-mmap, produces "
                "byte-identical archives versus two process invocations without "
                "that option"
            )


def test_opus_no_mmap_compress_matches_mapped_archive():
    for effort in ("-1", "-9"):
        with workspace() as ws:
            src = place_opus_classified(ws, "silk")
            src_bytes = ws.read_bytes(src)
            mapped = unique_name("mapped")
            unmapped = unique_name("unmapped")
            enc_m = run_product(ws, [effort, "e", src, mapped])
            require_ok(enc_m)
            assert ws.path_is_file(mapped), "mapped compress did not write a destination"
            mapped_bytes = ws.read_bytes(mapped)
            assert not stored_copy(mapped_bytes, src_bytes), (
                "mapped compress destination bytes carry the source verbatim (copy stub)"
            )
            enc_u = run_product(ws, [effort, "--no-mmap", "e", src, unmapped])
            require_ok(enc_u)
            assert ws.path_is_file(unmapped), (
                "--no-mmap compress did not write a destination"
            )
            unmapped_bytes = ws.read_bytes(unmapped)
            assert not stored_copy(unmapped_bytes, src_bytes), (
                "--no-mmap compress destination bytes carry the source verbatim (copy stub)"
            )
            assert files_identical(ws.resolve(mapped), ws.resolve(unmapped)), (
                "the same input compressed twice at the same effort, including "
                "with --no-mmap, produces byte-identical archives versus the "
                "mapped invocation"
            )


def test_opus_no_mmap_expand_recovers_original():
    with workspace() as ws:
        src = place_opus_classified(ws, "silk")
        src_bytes = ws.read_bytes(src)
        dest = unique_name("arc")
        enc = run_product(ws, ["-1", "e", src, dest])
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
            "the same input compressed twice at the same effort, including "
            "with --no-mmap on expand, recovered the original Opus bytes"
        )


# ---------------------------------------------------------------------------
# E. RFC 6716 code-3 padding within 61,440
# ---------------------------------------------------------------------------


def test_code3_padding_within_61440_round_trips_at_effort_1_and_9():
    with workspace() as ws:
        baseline = place_opus_classified(ws, "silk")
        original = ws.read_bytes(baseline)
        roundtrip(ws, baseline, effort="-1", dest=unique_name("base-arc"))
        first_audio = complete_packets(original)[2]
        below = runtime_code3_target_below_cap(len(first_audio))
        padded_below = with_first_audio_code3_padding(original, below)
        padded_cap = with_first_audio_code3_padding(original, OPUS_MAX_PACKET)
        assert padded_below != original and padded_cap != original
        assert padded_below != padded_cap
        below_audio = complete_packets(padded_below)[2]
        cap_audio = complete_packets(padded_cap)[2]
        assert (below_audio[0] & 3) == 3, (
            "below-cap first audio packet is not RFC 6716 code 3"
        )
        assert (cap_audio[0] & 3) == 3, (
            "at-cap first audio packet is not RFC 6716 code 3"
        )
        assert len(below_audio) < OPUS_MAX_PACKET, (
            f"below-cap audio packet length {len(below_audio)} is not under 61440"
        )
        assert len(cap_audio) == OPUS_MAX_PACKET, (
            "audio packets and the OpusHead packet are limited to 61,440 "
            "bytes, the maximum Opus packet size in RFC 7845 section 6: "
            f"at-cap audio packet length {len(cap_audio)} is not 61440"
        )
        print(
            f"[F03] E code-3 targets below={below} cap={OPUS_MAX_PACKET} "
            f"first_audio={len(first_audio)}",
            flush=True,
        )
        for label, blob in (("below", padded_below), ("cap", padded_cap)):
            src = unique_name(f"pad-{label}") + ".opus"
            ws.write(src, blob)
            src_bytes = blob
            for effort in ("-1", "-9"):
                dest = unique_name(f"{label}-{effort}")
                recovered = unique_name(f"{label}-{effort}-out")
                enc = run_product(ws, [effort, "e", src, dest])
                require_ok(enc)
                assert enc.returncode == 0, (
                    f"code-3 {label} compress at {effort} exited "
                    f"{enc.returncode}, not 0; stderr={enc.stderr!r}"
                )
                assert ws.path_is_file(dest), (
                    f"code-3 {label} compress at {effort} did not write dest"
                )
                assert not stored_copy(ws.read_bytes(dest), src_bytes), (
                    f"code-3 {label} compress at {effort} destination equals source"
                )
                dec = run_product(ws, ["d", dest, recovered])
                require_ok(dec)
                assert dec.returncode == 0, (
                    f"code-3 {label} expand at {effort} exited "
                    f"{dec.returncode}, not 0; stderr={dec.stderr!r}"
                )
                assert files_identical(ws.resolve(src), ws.resolve(recovered)), (
                    f"code-3 {label} expand at {effort} did not restore the "
                    "padded original bytes limited to 61,440 bytes"
                )


# ---------------------------------------------------------------------------
# F. OpusTags, including the 120 MiB cap
# ---------------------------------------------------------------------------


def test_opustags_constructed_comment_round_trips():
    with workspace() as ws:
        baseline = place_opus_classified(ws, "silk")
        original = ws.read_bytes(baseline)
        roundtrip(ws, baseline, effort="-1", dest=unique_name("base-arc"))
        vendor = f"suite-vendor-{token()}".encode("ascii")
        field = f"TITLE={token()}".encode("ascii")
        constructed = replace_opus_tags(original, vendor=vendor, fields=(field,))
        assert constructed != original, "constructed OpusTags file equals the baseline"
        src = unique_name("tags") + ".opus"
        ws.write(src, constructed)
        roundtrip(ws, src, effort="-1")


def test_opustags_at_120_mib_round_trips():
    with workspace() as ws:
        baseline = place_opus_classified(ws, "silk")
        original = ws.read_bytes(baseline)
        roundtrip(ws, baseline, effort="-1", dest=unique_name("base-arc"))
        vendor = f"suite-vendor-{token()}".encode("ascii")
        print("[F03] F 120 MiB OpusTags construction begin", flush=True)
        constructed = replace_opus_tags(
            original, vendor=vendor, fields=(), packet_size=OPUS_TAGS_MAX
        )
        tags = next(
            pkt
            for pkt in complete_packets(constructed)
            if pkt.startswith(b"OpusTags")
        )
        assert len(tags) == OPUS_TAGS_MAX, (
            "OpusTags comment packets may be up to 120 MiB and are still "
            f"part of the byte-identical round-trip: constructed packet is "
            f"{len(tags)} bytes, not 120 MiB"
        )
        print(
            f"[F03] F 120 MiB OpusTags constructed bytes={len(constructed)}",
            flush=True,
        )
        src = unique_name("tags-cap") + ".opus"
        ws.write(src, constructed)
        dest = unique_name("arc-cap")
        recovered = unique_name("out-cap")
        enc = run_product_long(ws, ["-1", "e", src, dest])
        require_ok(enc)
        assert enc.returncode == 0, (
            f"120 MiB OpusTags compress exited {enc.returncode}, not 0; "
            f"stderr={enc.stderr!r}"
        )
        assert ws.path_is_file(dest), "120 MiB OpusTags compress did not write dest"
        assert ws.read_bytes(dest) != constructed, (
            "120 MiB OpusTags compress destination bytes equal the source"
        )
        dec = run_product_long(ws, ["d", dest, recovered])
        require_ok(dec)
        assert dec.returncode == 0, (
            f"120 MiB OpusTags expand exited {dec.returncode}, not 0; "
            f"stderr={dec.stderr!r}"
        )
        assert files_identical(ws.resolve(src), ws.resolve(recovered)), (
            "OpusTags comment packets may be up to 120 MiB and are still "
            "part of the byte-identical round-trip: expand did not restore "
            "the constructed file"
        )
        print(
            "[F03] F 120 MiB OpusTags round-trip recovered original bytes",
            flush=True,
        )


def test_opustags_over_120_mib_is_refused():
    with workspace() as ws:
        baseline = place_opus_classified(ws, "silk")
        original = ws.read_bytes(baseline)
        roundtrip(ws, baseline, effort="-1", dest=unique_name("base-arc"))
        vendor = f"suite-vendor-{token()}".encode("ascii")
        print("[F03] F 120 MiB+1 OpusTags construction begin", flush=True)
        constructed = replace_opus_tags(
            original,
            vendor=vendor,
            fields=(),
            packet_size=OPUS_TAGS_MAX + 1,
        )
        print(
            f"[F03] F 120 MiB+1 OpusTags constructed bytes={len(constructed)}",
            flush=True,
        )
        src = unique_name("tags-over") + ".opus"
        ws.write(src, constructed)
        dest = unique_name("arc-over")
        enc = run_product_long(ws, ["-1", "e", src, dest])
        require_refusal(enc)
        assert enc.returncode == 1, (
            f"OpusTags larger than 120 MiB exited {enc.returncode}, not refusal 1; "
            f"stderr={enc.stderr!r}"
        )
        assert enc.stderr, (
            f"OpusTags larger than 120 MiB left stderr empty; stdout={enc.stdout!r}"
        )
        require_no_usable_compress_dest(ws, dest)


# ---------------------------------------------------------------------------
# G. Mapping family and family-0 channel count
# ---------------------------------------------------------------------------


def test_channel_mapping_family_nonzero_is_refused():
    with workspace() as ws:
        baseline = place_opus_classified(ws, "silk")
        original = ws.read_bytes(baseline)
        roundtrip(ws, baseline, effort="-1", dest=unique_name("base-arc"))
        family = runtime_mapping_family()
        mutated_a = set_opus_head_family(original, family)
        vendor = f"suite-vendor-{token()}".encode("ascii")
        field = f"NOTE={token()}".encode("ascii")
        rewritten = replace_opus_tags(original, vendor=vendor, fields=(field,))
        mutated_b = set_opus_head_family(rewritten, family)
        _, got_a = opus_head_fields(first_complete_packet(mutated_a))
        _, got_b = opus_head_fields(first_complete_packet(mutated_b))
        assert got_a == family and got_b == family and family != 0, (
            f"mutated mapping families are {got_a} and {got_b}, "
            f"not the runtime nonzero {family}"
        )
        src_a = unique_name("family-a") + ".opus"
        src_b = unique_name("family-b") + ".opus"
        ws.write(src_a, mutated_a)
        ws.write(src_b, mutated_b)
        dest_a = unique_name("family-arc-a")
        dest_b = unique_name("family-arc-b")
        neither_src = unique_name("neither")
        ws.write(neither_src, neither_ident_page())
        neither_dest = unique_name("neither-arc")
        paths = [
            src_a,
            dest_a,
            src_b,
            dest_b,
            neither_src,
            neither_dest,
            str(ws.path),
        ]
        enc_a = run_product(ws, ["e", src_a, dest_a])
        require_refusal(enc_a)
        assert enc_a.returncode == 1, (
            f"mapping family {family} exited {enc_a.returncode}, not refusal 1; "
            f"stderr={enc_a.stderr!r}"
        )
        assert enc_a.stderr, (
            f"mapping family {family} left stderr empty; stdout={enc_a.stdout!r}"
        )
        require_no_usable_compress_dest(ws, dest_a)
        enc_b = run_product(ws, ["e", src_b, dest_b])
        require_refusal(enc_b)
        assert enc_b.returncode == 1, (
            f"second mapping family {family} exited {enc_b.returncode}, "
            f"not refusal 1; stderr={enc_b.stderr!r}"
        )
        assert enc_b.stderr, (
            f"second mapping family {family} left stderr empty; "
            f"stdout={enc_b.stdout!r}"
        )
        require_no_usable_compress_dest(ws, dest_b)
        neither_enc = run_product(ws, ["e", neither_src, neither_dest])
        require_refusal(neither_enc)
        assert neither_enc.returncode == 1, (
            f"neither-ident compress exited {neither_enc.returncode}, not 1; "
            f"stderr={neither_enc.stderr!r}"
        )
        assert neither_enc.stderr, (
            f"neither-ident compress left stderr empty; stdout={neither_enc.stdout!r}"
        )
        require_no_usable_compress_dest(ws, neither_dest)
        said_a = states_decimal(without_paths(enc_a.stderr_text, paths), family)
        said_b = states_decimal(without_paths(enc_b.stderr_text, paths), family)
        print(
            f"[F03] G family={family} stated_a={said_a} stated_b={said_b}",
            flush=True,
        )
        assert said_a and said_b, (
            "the diagnostic of a mapping-family refusal states the rejected "
            f"family value as a decimal number; family={family} "
            f"stderr_a={enc_a.stderr_text!r} stderr_b={enc_b.stderr_text!r}"
        )


def test_family0_channel_count_other_than_1_or_2_is_refused():
    with workspace() as ws:
        baseline = place_opus_classified(ws, "silk")
        original = ws.read_bytes(baseline)
        roundtrip(ws, baseline, effort="-1", dest=unique_name("base-arc"))
        count = runtime_family0_illegal_channels()
        mutated_a = set_opus_head_channels(original, count)
        vendor = f"suite-vendor-{token()}".encode("ascii")
        field = f"NOTE={token()}".encode("ascii")
        rewritten = replace_opus_tags(original, vendor=vendor, fields=(field,))
        mutated_b = set_opus_head_channels(rewritten, count)
        got_a, family_a = opus_head_fields(first_complete_packet(mutated_a))
        got_b, family_b = opus_head_fields(first_complete_packet(mutated_b))
        assert family_a == 0 and family_b == 0, (
            f"channel-count mutant mapping families are {family_a} and "
            f"{family_b}, not 0"
        )
        assert (
            got_a == count
            and got_b == count
            and got_a not in (1, 2)
        ), (
            f"mutated channel counts are {got_a} and {got_b}, not the runtime "
            f"unsupported {count}"
        )
        src_a = unique_name("ch-a") + ".opus"
        src_b = unique_name("ch-b") + ".opus"
        ws.write(src_a, mutated_a)
        ws.write(src_b, mutated_b)
        dest_a = unique_name("ch-arc-a")
        dest_b = unique_name("ch-arc-b")
        neither_src = unique_name("neither")
        ws.write(neither_src, neither_ident_page())
        neither_dest = unique_name("neither-arc")
        paths = [
            src_a,
            dest_a,
            src_b,
            dest_b,
            neither_src,
            neither_dest,
            str(ws.path),
        ]
        enc_a = run_product(ws, ["e", src_a, dest_a])
        require_refusal(enc_a)
        assert enc_a.returncode == 1, (
            f"family-0 channel count {count} exited {enc_a.returncode}, "
            f"not refusal 1; stderr={enc_a.stderr!r}"
        )
        assert enc_a.stderr, (
            f"family-0 channel count {count} left stderr empty; "
            f"stdout={enc_a.stdout!r}"
        )
        require_no_usable_compress_dest(ws, dest_a)
        enc_b = run_product(ws, ["e", src_b, dest_b])
        require_refusal(enc_b)
        assert enc_b.returncode == 1, (
            f"second family-0 channel count {count} exited {enc_b.returncode}, "
            f"not refusal 1; stderr={enc_b.stderr!r}"
        )
        assert enc_b.stderr, (
            f"second family-0 channel count {count} left stderr empty; "
            f"stdout={enc_b.stdout!r}"
        )
        require_no_usable_compress_dest(ws, dest_b)
        neither_enc = run_product(ws, ["e", neither_src, neither_dest])
        require_refusal(neither_enc)
        assert neither_enc.returncode == 1, (
            f"neither-ident compress exited {neither_enc.returncode}, not 1; "
            f"stderr={neither_enc.stderr!r}"
        )
        assert neither_enc.stderr, (
            f"neither-ident compress left stderr empty; stdout={neither_enc.stdout!r}"
        )
        require_no_usable_compress_dest(ws, neither_dest)
        said_a = states_decimal(without_paths(enc_a.stderr_text, paths), count)
        said_b = states_decimal(without_paths(enc_b.stderr_text, paths), count)
        print(
            f"[F03] G count={count} stated_a={said_a} stated_b={said_b}",
            flush=True,
        )
        assert said_a and said_b, (
            "the diagnostic of a channel-count refusal states the rejected "
            f"channel count as a decimal number; count={count} "
            f"stderr_a={enc_a.stderr_text!r} stderr_b={enc_b.stderr_text!r}"
        )


# ---------------------------------------------------------------------------
# H. Packets larger than 61,440
# ---------------------------------------------------------------------------


def test_audio_packet_over_61440_is_refused():
    with workspace() as ws:
        baseline = place_opus_classified(ws, "silk")
        original = ws.read_bytes(baseline)
        roundtrip(ws, baseline, effort="-1", dest=unique_name("base-arc"))
        at_cap = with_first_audio_code3_padding(original, OPUS_MAX_PACKET)
        assert len(complete_packets(at_cap)[2]) == OPUS_MAX_PACKET, (
            "audio packets are limited to 61,440 bytes: at-cap first audio "
            "packet is not 61440 bytes"
        )
        cap_src = unique_name("at-cap") + ".opus"
        ws.write(cap_src, at_cap)
        cap_dest = unique_name("cap-arc")
        cap_out = unique_name("cap-out")
        cap_enc = run_product(ws, ["-1", "e", cap_src, cap_dest])
        require_ok(cap_enc)
        assert cap_enc.returncode == 0, (
            f"at-cap audio compress exited {cap_enc.returncode}, not 0; "
            f"stderr={cap_enc.stderr!r}"
        )
        assert ws.path_is_file(cap_dest), "at-cap audio compress did not write dest"
        assert ws.read_bytes(cap_dest) != at_cap, (
            "at-cap audio compress destination bytes equal the source"
        )
        cap_dec = run_product(ws, ["d", cap_dest, cap_out])
        require_ok(cap_dec)
        assert cap_dec.returncode == 0, (
            f"at-cap audio expand exited {cap_dec.returncode}, not 0; "
            f"stderr={cap_dec.stderr!r}"
        )
        assert files_identical(ws.resolve(cap_src), ws.resolve(cap_out)), (
            "audio packets are limited to 61,440 bytes: expand did not "
            "restore the 61440-byte packet file"
        )
        over = with_first_audio_code3_padding(original, OPUS_MAX_PACKET + 1)
        assert len(complete_packets(over)[2]) == OPUS_MAX_PACKET + 1, (
            "over-cap first audio packet is not 61441 bytes"
        )
        src = unique_name("over-audio") + ".opus"
        ws.write(src, over)
        dest = unique_name("over-audio-arc")
        enc = run_product(ws, ["e", src, dest])
        require_refusal(enc)
        assert enc.returncode == 1, (
            f"first audio packet larger than 61440 exited {enc.returncode}, "
            f"not refusal 1; stderr={enc.stderr!r}"
        )
        assert enc.stderr, (
            f"first audio packet larger than 61440 left stderr empty; "
            f"stdout={enc.stdout!r}"
        )
        require_no_usable_compress_dest(ws, dest)


def test_later_audio_packet_over_61440_is_refused():
    with workspace() as ws:
        baseline = place_opus_classified(ws, "silk")
        original = ws.read_bytes(baseline)
        roundtrip(ws, baseline, effort="-1", dest=unique_name("base-arc"))
        over = with_later_audio_code3_padding(original, OPUS_MAX_PACKET + 1)
        src = unique_name("over-later") + ".opus"
        ws.write(src, over)
        dest = unique_name("over-later-arc")
        enc = run_product(ws, ["e", src, dest])
        require_refusal(enc)
        assert enc.returncode == 1, (
            f"later audio packet larger than 61440 exited {enc.returncode}, "
            f"not refusal 1; stderr={enc.stderr!r}"
        )
        assert enc.stderr, (
            f"later audio packet larger than 61440 left stderr empty; "
            f"stdout={enc.stdout!r}"
        )
        require_no_usable_compress_dest(ws, dest)


def test_opushead_of_exactly_61440_bytes_round_trips():
    with workspace() as ws:
        baseline = place_opus_classified(ws, "silk")
        original = ws.read_bytes(baseline)
        roundtrip(ws, baseline, effort="-1", dest=unique_name("base-arc"))
        at_cap = with_opus_head_padded(original, OPUS_MAX_PACKET)
        head = first_complete_packet(at_cap)
        assert is_opus_head(head), "padded packet is not OpusHead"
        assert len(head) == OPUS_MAX_PACKET, (
            "audio packets and the OpusHead packet are limited to 61,440 "
            "bytes, the maximum Opus packet size in RFC 7845 section 6: "
            f"at-cap OpusHead length is {len(head)}, not 61440"
        )
        src = unique_name("head-cap") + ".opus"
        ws.write(src, at_cap)
        dest = unique_name("head-cap-arc")
        recovered = unique_name("head-cap-out")
        enc = run_product(ws, ["-1", "e", src, dest])
        require_ok(enc)
        assert enc.returncode == 0, (
            f"OpusHead of exactly 61,440 bytes compress exited "
            f"{enc.returncode}, not 0; stderr={enc.stderr!r}"
        )
        assert ws.path_is_file(dest), (
            "OpusHead of exactly 61,440 bytes compress did not write dest"
        )
        assert ws.read_bytes(dest) != at_cap, (
            "OpusHead of exactly 61,440 bytes compress destination equals source"
        )
        dec = run_product(ws, ["d", dest, recovered])
        require_ok(dec)
        assert dec.returncode == 0, (
            f"OpusHead of exactly 61,440 bytes expand exited "
            f"{dec.returncode}, not 0; stderr={dec.stderr!r}"
        )
        assert files_identical(ws.resolve(src), ws.resolve(recovered)), (
            "the OpusHead packet is limited to 61,440 bytes: an OpusHead "
            "packet of exactly 61,440 bytes still compresses and expands "
            "to the original bytes"
        )
        print(
            f"[F03] H OpusHead at-cap bytes={len(head)} round-trip ok",
            flush=True,
        )


def test_opushead_over_61440_is_refused():
    with workspace() as ws:
        baseline = place_opus_classified(ws, "silk")
        original = ws.read_bytes(baseline)
        roundtrip(ws, baseline, effort="-1", dest=unique_name("base-arc"))
        at_cap = with_opus_head_padded(original, OPUS_MAX_PACKET)
        assert len(first_complete_packet(at_cap)) == OPUS_MAX_PACKET, (
            "the OpusHead packet is limited to 61,440 bytes: at-cap "
            "OpusHead packet is not 61440 bytes"
        )
        cap_src = unique_name("at-cap-head") + ".opus"
        ws.write(cap_src, at_cap)
        cap_dest = unique_name("cap-head-arc")
        cap_out = unique_name("cap-head-out")
        cap_enc = run_product(ws, ["-1", "e", cap_src, cap_dest])
        require_ok(cap_enc)
        assert cap_enc.returncode == 0, (
            f"at-cap OpusHead compress exited {cap_enc.returncode}, not 0; "
            f"stderr={cap_enc.stderr!r}"
        )
        assert ws.path_is_file(cap_dest), (
            "at-cap OpusHead compress did not write dest"
        )
        assert ws.read_bytes(cap_dest) != at_cap, (
            "at-cap OpusHead compress destination bytes equal the source"
        )
        cap_dec = run_product(ws, ["d", cap_dest, cap_out])
        require_ok(cap_dec)
        assert cap_dec.returncode == 0, (
            f"at-cap OpusHead expand exited {cap_dec.returncode}, not 0; "
            f"stderr={cap_dec.stderr!r}"
        )
        assert files_identical(ws.resolve(cap_src), ws.resolve(cap_out)), (
            "the OpusHead packet is limited to 61,440 bytes: an OpusHead "
            "packet of exactly 61,440 bytes did not compress and expand "
            "to the original bytes"
        )
        over = with_opus_head_padded(original, OPUS_MAX_PACKET + 1)
        assert len(first_complete_packet(over)) == OPUS_MAX_PACKET + 1, (
            "over-cap OpusHead packet is not 61441 bytes"
        )
        src = unique_name("over-head") + ".opus"
        ws.write(src, over)
        dest = unique_name("over-head-arc")
        enc = run_product(ws, ["e", src, dest])
        require_refusal(enc)
        assert enc.returncode == 1, (
            f"OpusHead larger than 61440 exited {enc.returncode}, not refusal 1; "
            f"stderr={enc.stderr!r}"
        )
        assert enc.stderr, (
            f"OpusHead larger than 61440 left stderr empty; stdout={enc.stdout!r}"
        )
        require_no_usable_compress_dest(ws, dest)


# ---------------------------------------------------------------------------
# I. Nonzero Ogg version
# ---------------------------------------------------------------------------


def test_nonzero_ogg_version_is_refused():
    with workspace() as ws:
        baseline = place_opus_classified(ws, "silk")
        original = ws.read_bytes(baseline)
        roundtrip(ws, baseline, effort="-1", dest=unique_name("base-arc"))
        version = runtime_ogg_version()
        mutated = with_ogg_version(original, version, page_index=0)
        src = unique_name("ver0") + ".opus"
        ws.write(src, mutated)
        dest = unique_name("ver0-arc")
        enc = run_product(ws, ["e", src, dest])
        require_refusal(enc)
        assert enc.returncode == 1, (
            f"nonzero Ogg version {version} on the first page exited "
            f"{enc.returncode}, not refusal 1; stderr={enc.stderr!r}"
        )
        assert enc.stderr, (
            f"nonzero Ogg version {version} on the first page left stderr empty; "
            f"stdout={enc.stdout!r}"
        )
        require_no_usable_compress_dest(ws, dest)
        print(f"[F03] I first-page version={version}", flush=True)


def test_nonzero_ogg_version_on_later_page_is_refused():
    with workspace() as ws:
        baseline = place_opus_classified(ws, "silk")
        original = ws.read_bytes(baseline)
        roundtrip(ws, baseline, effort="-1", dest=unique_name("base-arc"))
        pages = parse_ogg_pages(original)
        if len(pages) < 2:
            raise AssertionError("fixture has no later page")
        page_index = 1 + (runtime_ogg_version() % (len(pages) - 1))
        version = runtime_ogg_version()
        mutated = with_ogg_version(original, version, page_index=page_index)
        src = unique_name("ver-later") + ".opus"
        ws.write(src, mutated)
        dest = unique_name("ver-later-arc")
        enc = run_product(ws, ["e", src, dest])
        require_refusal(enc)
        assert enc.returncode == 1, (
            f"nonzero Ogg version {version} on later page {page_index} exited "
            f"{enc.returncode}, not refusal 1; stderr={enc.stderr!r}"
        )
        assert enc.stderr, (
            f"nonzero Ogg version {version} on later page {page_index} left "
            f"stderr empty; stdout={enc.stdout!r}"
        )
        require_no_usable_compress_dest(ws, dest)
        print(
            f"[F03] I later-page index={page_index} version={version}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# J. dump Opus vs dump Vorbis as codec
# ---------------------------------------------------------------------------


def test_dump_opus_archive_distinguishable_from_vorbis_as_codec():
    with workspace() as ws:
        require_codec_mode_field(ws, "-9", what="F03 J effort 9")


# ---------------------------------------------------------------------------
# Expand needs only the archive (Opus)
# ---------------------------------------------------------------------------


def test_opus_archive_alone_expands_after_every_compress_trace_is_gone():
    from F04_helpers import _opus_tags_variant, expand_from_archive_alone

    for kind in ("silk", "hybrid"):
        with workspace() as ws:
            original = ws.read_bytes(place_opus_classified(ws, kind))
        src_bytes = _opus_tags_variant(original)
        for effort in ("-1", "-9"):
            expand_from_archive_alone(
                src_bytes, effort, ".opus", what=f"Opus {kind} {effort}"
            )
