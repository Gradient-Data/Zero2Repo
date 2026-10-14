# feature: F06
"""Acceptance: chained bitstreams and Vorbis files without a final EOS flag."""

from __future__ import annotations

from F01_helpers import unique_name
from F02_helpers import roundtrip
from F03_helpers import runtime_family0_illegal_channels, runtime_mapping_family
from F04_helpers import opus_with_runtime_tags, vorbis_with_runtime_comment
from F05_helpers import refuse_compress
from F06_helpers import (
    concat_bitstreams,
    distinct_serials,
    family0_chain_bytes,
    merged_header_audio_link,
    ogg_links,
    place_bytes,
    prove_complete_packets,
    prove_family0_supported_link,
    prove_incomplete_final_packet,
    prove_later_link_replays_headers,
    prove_link_count,
    prove_link_opus_channels,
    prove_link_opus_family,
    prove_merged_header_audio_page,
    prove_only_last_link_lacks_eos,
    prove_opus_mode_link,
    two_distinct_vorbis_links,
    vorbis_merge_host,
    with_incomplete_final_packet,
    with_link_opus_channels,
    with_link_opus_family,
    without_final_eos,
)
from _harness import workspace


# ---------------------------------------------------------------------------
# A. Three-link Vorbis chain, later link replays headers
# ---------------------------------------------------------------------------


def test_three_link_vorbis_chain_round_trips():
    with workspace() as ws:
        baseline = vorbis_with_runtime_comment(ws)
        roundtrip(ws, baseline, effort="-1")
        link1, link3 = two_distinct_vorbis_links()
        chained = concat_bitstreams([link1, link1, link3])
        links = prove_link_count(chained, 3)
        prove_later_link_replays_headers(links[0], links[1])
        if len(links[0]) == len(links[2]):
            raise AssertionError(
                "links may differ in length: link 1 and link 3 have the same "
                f"byte length {len(links[0])}"
            )
        src = place_bytes(ws, chained, "vorbis-3link", ".ogg")
        roundtrip(ws, src, effort="-1")
        print(
            f"[F06] A three-link Vorbis lens={[len(p) for p in links]}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# B. stereo CELT + mono SILK + mono hybrid
# ---------------------------------------------------------------------------


def test_concatenated_family0_opus_chain_round_trips():
    with workspace() as ws:
        silk = opus_with_runtime_tags(ws, "silk")
        roundtrip(ws, silk, effort="-1")
        chained = family0_chain_bytes(ws, ("celt", "silk", "hybrid"))
        links = prove_link_count(chained, 3)
        prove_opus_mode_link(links[0], "celt", channels=2)
        prove_opus_mode_link(links[1], "silk", channels=1)
        prove_opus_mode_link(links[2], "hybrid", channels=1)
        src = place_bytes(ws, chained, "opus-triple", ".opus")
        roundtrip(ws, src, effort="-1")
        print(
            f"[F06] B CELT/SILK/hybrid lens={[len(p) for p in links]}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# B2. SILK then CELT — not the L250 triple, not its prefix
# ---------------------------------------------------------------------------


def test_two_link_family0_opus_chain_round_trips():
    with workspace() as ws:
        chained = family0_chain_bytes(ws, ("silk", "celt"))
        links = prove_link_count(chained, 2)
        prove_opus_mode_link(links[0], "silk", channels=1)
        prove_opus_mode_link(links[1], "celt", channels=2)
        src = place_bytes(ws, chained, "opus-silk-celt", ".opus")
        roundtrip(ws, src, effort="-1")
        print(
            f"[F06] B2 SILK then CELT lens={[len(p) for p in links]}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# C. Vorbis last page lacks EOS; last packet complete
# ---------------------------------------------------------------------------


def test_vorbis_without_final_eos_round_trips():
    with workspace() as ws:
        host_rel = vorbis_with_runtime_comment(ws)
        host = ws.read_bytes(host_rel)
        roundtrip(ws, host_rel, effort="-1")
        cleared = without_final_eos(host)
        assert cleared != host, "cleared-EOS construction equals the unmodified host"
        src = place_bytes(ws, cleared, "vorbis-noeos", ".ogg")
        roundtrip(ws, src, effort="-1")
        print(f"[F06] C single-file no-EOS bytes={len(cleared)}", flush=True)


def test_vorbis_chain_without_final_eos_round_trips():
    with workspace() as ws:
        link1, link3 = two_distinct_vorbis_links()
        chained = concat_bitstreams([link1, link3])
        prove_link_count(chained, 2)
        prove_complete_packets(chained)
        base = place_bytes(ws, chained, "vorbis-2link", ".ogg")
        roundtrip(ws, base, effort="-1")
        cleared = without_final_eos(chained)
        prove_link_count(cleared, 2)
        prove_only_last_link_lacks_eos(cleared, 2)
        src = place_bytes(ws, cleared, "vorbis-2link-noeos", ".ogg")
        roundtrip(ws, src, effort="-1")
        print(f"[F06] C chain no-EOS bytes={len(cleared)}", flush=True)


def test_vorbis_prefixed_copies_without_final_eos_round_trips():
    with workspace() as ws:
        host_rel = vorbis_with_runtime_comment(ws)
        host = ws.read_bytes(host_rel)
        triple = concat_bitstreams([host, host, host])
        prove_link_count(triple, 3)
        base = place_bytes(ws, triple, "vorbis-3copy", ".ogg")
        roundtrip(ws, base, effort="-1")
        cleared = without_final_eos(triple)
        prove_only_last_link_lacks_eos(cleared, 3)
        src = place_bytes(ws, cleared, "vorbis-3copy-noeos", ".ogg")
        roundtrip(ws, src, effort="-1")
        print(f"[F06] C prefixed copies no-EOS bytes={len(cleared)}", flush=True)


# ---------------------------------------------------------------------------
# D. Two Vorbis links, each merging later headers with first audio
# ---------------------------------------------------------------------------


def test_vorbis_chain_merged_headers_with_first_audio_round_trips():
    with workspace() as ws:
        host = vorbis_merge_host()
        host_rel = place_bytes(ws, host, "vorbis-merge-host", ".ogg")
        roundtrip(ws, host_rel, effort="-1")
        serial_a, serial_b = distinct_serials()
        link_a = merged_header_audio_link(host, serial=serial_a, extra_audio_pages=0)
        link_b = merged_header_audio_link(host, serial=serial_b, extra_audio_pages=2)
        chained = concat_bitstreams([link_a, link_b])
        links = prove_link_count(chained, 2)
        prove_merged_header_audio_page(links[0])
        prove_merged_header_audio_page(links[1])
        if len(links[0]) == len(links[1]):
            raise AssertionError(
                "merged links have the same byte length "
                f"{len(links[0])}; remaining audio page counts must differ"
            )
        src = place_bytes(ws, chained, "vorbis-merged", ".ogg")
        roundtrip(ws, src, effort="-1")
        print(
            f"[F06] D merged-header chain lens={[len(p) for p in links]}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# E / F. Later link illegal mapping family or channel count
# ---------------------------------------------------------------------------


def test_opus_chain_later_link_nonzero_mapping_family_is_refused():
    with workspace() as ws:
        legal = family0_chain_bytes(ws, ("silk", "celt"))
        prove_link_count(legal, 2)
        prove_family0_supported_link(legal, 0)
        prove_family0_supported_link(legal, 1)
        base = place_bytes(ws, legal, "opus-2link-legal", ".opus")
        roundtrip(ws, base, effort="-1")
        family = runtime_mapping_family()
        illegal = with_link_opus_family(legal, 1, family)
        prove_family0_supported_link(illegal, 0)
        prove_link_opus_family(illegal, 1, nonzero=True)
        src = place_bytes(ws, illegal, "opus-2link-family", ".opus")
        result = refuse_compress(ws, src, unique_name("opus-2link-family-arc"))
        assert result.returncode == 1
        assert result.stderr
        print(f"[F06] E later-link family={family} refused", flush=True)


def test_opus_chain_later_link_illegal_channel_count_is_refused():
    with workspace() as ws:
        legal = family0_chain_bytes(ws, ("silk", "celt"))
        prove_link_count(legal, 2)
        prove_family0_supported_link(legal, 0)
        prove_family0_supported_link(legal, 1)
        base = place_bytes(ws, legal, "opus-2link-ch-legal", ".opus")
        roundtrip(ws, base, effort="-1")
        channels = runtime_family0_illegal_channels()
        illegal = with_link_opus_channels(legal, 1, channels)
        prove_family0_supported_link(illegal, 0)
        prove_link_opus_channels(illegal, 1, illegal=True)
        src = place_bytes(ws, illegal, "opus-2link-channels", ".opus")
        result = refuse_compress(ws, src, unique_name("opus-2link-channels-arc"))
        assert result.returncode == 1
        assert result.stderr
        print(f"[F06] F later-link channels={channels} refused", flush=True)


# ---------------------------------------------------------------------------
# E3 / F3. Third of three links illegal
# ---------------------------------------------------------------------------


def test_opus_chain_third_link_nonzero_mapping_family_is_refused():
    with workspace() as ws:
        legal = family0_chain_bytes(ws, ("silk", "celt", "hybrid"))
        prove_link_count(legal, 3)
        prove_family0_supported_link(legal, 0)
        prove_family0_supported_link(legal, 1)
        prove_family0_supported_link(legal, 2)
        base = place_bytes(ws, legal, "opus-3link-legal", ".opus")
        roundtrip(ws, base, effort="-1")
        family = runtime_mapping_family()
        illegal = with_link_opus_family(legal, 2, family)
        prove_family0_supported_link(illegal, 0)
        prove_family0_supported_link(illegal, 1)
        prove_link_opus_family(illegal, 2, nonzero=True)
        src = place_bytes(ws, illegal, "opus-3link-family", ".opus")
        result = refuse_compress(ws, src, unique_name("opus-3link-family-arc"))
        assert result.returncode == 1
        assert result.stderr
        print(f"[F06] E3 third-link family={family} refused", flush=True)


def test_opus_chain_third_link_illegal_channel_count_is_refused():
    with workspace() as ws:
        legal = family0_chain_bytes(ws, ("silk", "celt", "hybrid"))
        prove_link_count(legal, 3)
        prove_family0_supported_link(legal, 0)
        prove_family0_supported_link(legal, 1)
        prove_family0_supported_link(legal, 2)
        base = place_bytes(ws, legal, "opus-3link-ch-legal", ".opus")
        roundtrip(ws, base, effort="-1")
        channels = runtime_family0_illegal_channels()
        illegal = with_link_opus_channels(legal, 2, channels)
        prove_family0_supported_link(illegal, 0)
        prove_family0_supported_link(illegal, 1)
        prove_link_opus_channels(illegal, 2, illegal=True)
        src = place_bytes(ws, illegal, "opus-3link-channels", ".opus")
        result = refuse_compress(ws, src, unique_name("opus-3link-channels-arc"))
        assert result.returncode == 1
        assert result.stderr
        print(f"[F06] F3 third-link channels={channels} refused", flush=True)


# ---------------------------------------------------------------------------
# E-mid. Interior link illegal; last link still legal
# ---------------------------------------------------------------------------


def test_opus_chain_interior_link_nonzero_mapping_family_is_refused():
    with workspace() as ws:
        legal = family0_chain_bytes(ws, ("silk", "celt", "hybrid"))
        prove_link_count(legal, 3)
        prove_family0_supported_link(legal, 0)
        prove_family0_supported_link(legal, 1)
        prove_family0_supported_link(legal, 2)
        base = place_bytes(ws, legal, "opus-mid-legal", ".opus")
        roundtrip(ws, base, effort="-1")
        family = runtime_mapping_family()
        illegal = with_link_opus_family(legal, 1, family)
        prove_family0_supported_link(illegal, 0)
        prove_link_opus_family(illegal, 1, nonzero=True)
        prove_family0_supported_link(illegal, 2)
        src = place_bytes(ws, illegal, "opus-mid-family", ".opus")
        result = refuse_compress(ws, src, unique_name("opus-mid-family-arc"))
        assert result.returncode == 1
        assert result.stderr
        print(f"[F06] E-mid interior-link family={family} refused", flush=True)


# ---------------------------------------------------------------------------
# G. File ends in the middle of a packet
# ---------------------------------------------------------------------------


def test_vorbis_incomplete_final_packet_is_refused():
    with workspace() as ws:
        host_rel = vorbis_with_runtime_comment(ws)
        host = ws.read_bytes(host_rel)
        roundtrip(ws, host_rel, effort="-1")
        incomplete = with_incomplete_final_packet(host)
        prove_incomplete_final_packet(incomplete)
        src = place_bytes(ws, incomplete, "vorbis-incomp", ".ogg")
        result = refuse_compress(ws, src, unique_name("vorbis-incomp-arc"))
        assert result.returncode == 1
        assert result.stderr
        print("[F06] G Vorbis incomplete final packet refused", flush=True)


def test_opus_incomplete_final_packet_is_refused():
    with workspace() as ws:
        host_rel = opus_with_runtime_tags(ws, "silk")
        host = ws.read_bytes(host_rel)
        roundtrip(ws, host_rel, effort="-1")
        incomplete = with_incomplete_final_packet(host)
        prove_incomplete_final_packet(incomplete)
        src = place_bytes(ws, incomplete, "opus-incomp", ".opus")
        result = refuse_compress(ws, src, unique_name("opus-incomp-arc"))
        assert result.returncode == 1
        assert result.stderr
        print("[F06] G Opus incomplete final packet refused", flush=True)


def test_vorbis_chain_incomplete_final_packet_is_refused():
    with workspace() as ws:
        link1, link2 = two_distinct_vorbis_links()
        complete_chain = concat_bitstreams([link1, link2])
        prove_link_count(complete_chain, 2)
        base = place_bytes(ws, complete_chain, "vorbis-2link-comp", ".ogg")
        roundtrip(ws, base, effort="-1")
        incomplete_second = with_incomplete_final_packet(link2)
        chained = concat_bitstreams([link1, incomplete_second])
        links = prove_link_count(chained, 2)
        prove_complete_packets(links[0])
        prove_incomplete_final_packet(chained)
        src = place_bytes(ws, chained, "vorbis-2link-incomp", ".ogg")
        result = refuse_compress(ws, src, unique_name("vorbis-2link-incomp-arc"))
        assert result.returncode == 1
        assert result.stderr
        print("[F06] G Vorbis chain incomplete final packet refused", flush=True)


def test_opus_chain_incomplete_final_packet_is_refused():
    with workspace() as ws:
        legal = family0_chain_bytes(ws, ("silk", "celt"))
        prove_link_count(legal, 2)
        base = place_bytes(ws, legal, "opus-2link-comp", ".opus")
        roundtrip(ws, base, effort="-1")
        links = ogg_links(legal)
        incomplete_second = with_incomplete_final_packet(links[1])
        chained = concat_bitstreams([links[0], incomplete_second])
        proved = prove_link_count(chained, 2)
        prove_complete_packets(proved[0])
        prove_incomplete_final_packet(chained)
        src = place_bytes(ws, chained, "opus-2link-incomp", ".opus")
        result = refuse_compress(ws, src, unique_name("opus-2link-incomp-arc"))
        assert result.returncode == 1
        assert result.stderr
        print("[F06] G Opus chain incomplete final packet refused", flush=True)
