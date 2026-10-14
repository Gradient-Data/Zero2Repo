# feature: F06
"""Feature-local helpers for chained bitstreams and missing-final-EOS Vorbis.

These helpers build suite inputs (RFC 3533 pages, RFC 7845 OpusHead fields,
RFC 6716 TOC kinds) and prove those constructions. They are not a
substitute public entry.
"""

from __future__ import annotations

import secrets
from typing import Sequence

from F01_helpers import _vorbis_bytes, token, unique_name
from F02_helpers import (
    VORBIS_COMMENT,
    VORBIS_SETUP,
    complete_packets,
    emit_ogg_page,
    is_opus_head,
    is_vorbis_ident,
    ogg_crc_page,
    page_packet_bytes,
    parse_ogg_pages,
    replace_vorbis_comment,
)
from F03_helpers import (
    OPUS_TAGS_MAGIC,
    opus_head_fields,
    rfc6716_config_kind,
    set_opus_head_channels,
    set_opus_head_family,
)
from F04_helpers import (
    _SCALE_FILES,
    _read_fixture,
    _vorbis_comment_variant,
    opus_with_runtime_tags,
)
from F05_helpers import with_marked_packet_span
from _harness import HarnessError, Workspace


def concat_bitstreams(parts: Sequence[bytes]) -> bytes:
    """Concatenate complete Ogg files in order. Each part must start at BOS."""
    if not parts:
        raise HarnessError("no bitstreams to concatenate")
    out = bytearray()
    for i, part in enumerate(parts):
        if not isinstance(part, (bytes, bytearray)):
            raise HarnessError(f"part {i} expected bytes, got {type(part)!r}")
        pages = parse_ogg_pages(part)
        if not (pages[0].header_type & 0x02):
            raise HarnessError(
                f"part {i} does not start with a beginning-of-stream page"
            )
        out += bytes(part)
    return bytes(out)


def ogg_links(data: bytes) -> list[bytes]:
    """Split *data* into links at beginning-of-stream pages. Raises on failure."""
    pages = parse_ogg_pages(data)
    starts = [i for i, page in enumerate(pages) if page.header_type & 0x02]
    if not starts:
        raise HarnessError("bitstream has no beginning-of-stream page")
    if starts[0] != 0:
        raise HarnessError(
            "bitstream does not start with a beginning-of-stream page "
            f"(first BOS at page {starts[0]})"
        )
    links: list[bytes] = []
    for i, start in enumerate(starts):
        stop = starts[i + 1] if i + 1 < len(starts) else len(pages)
        begin = pages[start].offset
        end = pages[stop - 1].offset + pages[stop - 1].size
        blob = bytes(data[begin:end])
        if not blob:
            raise HarnessError(f"link {i} is empty")
        links.append(blob)
    return links


def prove_link_count(data: bytes, expected: int) -> list[bytes]:
    """Return links after proving there are exactly *expected* BOS pages."""
    if expected < 1:
        raise HarnessError(f"expected link count {expected} is not positive")
    links = ogg_links(data)
    if len(links) != expected:
        raise HarnessError(f"expected {expected} links, got {len(links)}")
    print(f"[F06] proved link count={expected}", flush=True)
    return links


def prove_complete_packets(data: bytes) -> list[bytes]:
    """Return complete packets. An unfinished tail raises; never a sentinel."""
    packets = complete_packets(data)
    if not packets:
        raise HarnessError("bitstream has no complete packets")
    print(f"[F06] proved complete packets n={len(packets)}", flush=True)
    return packets


def prove_stored_crc(data: bytes, page_index: int = -1) -> None:
    """Prove stored checksum equals RFC 3533 with the field treated as zero."""
    pages = parse_ogg_pages(data)
    if not pages:
        raise HarnessError("no Ogg pages to prove checksum")
    if page_index < 0:
        page_index = len(pages) + page_index
    if not 0 <= page_index < len(pages):
        raise HarnessError(
            f"page index {page_index} out of range ({len(pages)} pages)"
        )
    page = pages[page_index]
    stored = int.from_bytes(page.raw[22:26], "little")
    expect = ogg_crc_page(page.raw)
    if stored != expect:
        raise HarnessError(
            f"page {page_index} stored checksum {stored} != RFC 3533 {expect}"
        )
    print(
        f"[F06] proved RFC 3533 checksum page={page_index} crc={stored}",
        flush=True,
    )


def without_final_eos(data: bytes) -> bytes:
    """Clear the last page's end-of-stream flag and rewrite the RFC 3533 CRC."""
    pages = parse_ogg_pages(data)
    last = pages[-1]
    if not (last.header_type & 0x04):
        raise HarnessError("last page already lacks the end-of-stream flag")
    raw = bytearray(last.raw)
    raw[5] = raw[5] & ~0x04
    crc = ogg_crc_page(bytes(raw))
    raw[22:26] = int(crc).to_bytes(4, "little")
    out = bytes(data[: last.offset] + bytes(raw))
    proved = parse_ogg_pages(out)
    if proved[-1].header_type & 0x04:
        raise HarnessError("last page still has the end-of-stream flag")
    prove_stored_crc(out, -1)
    prove_complete_packets(out)
    print(
        f"[F06] cleared final EOS pages={len(proved)} bytes={len(out)}",
        flush=True,
    )
    return out


def prove_only_last_link_lacks_eos(data: bytes, expected_links: int) -> None:
    """Prove every link but the last ends with EOS, and the last does not."""
    links = prove_link_count(data, expected_links)
    for i, link in enumerate(links):
        pages = parse_ogg_pages(link)
        has_eos = bool(pages[-1].header_type & 0x04)
        if i + 1 == expected_links:
            if has_eos:
                raise HarnessError(f"last link {i} still has the end-of-stream flag")
        elif not has_eos:
            raise HarnessError(f"prefix link {i} lacks the end-of-stream flag")
    print(
        f"[F06] proved only last of {expected_links} links lacks EOS",
        flush=True,
    )


def _vorbis_header_triple(link: bytes) -> tuple[bytes, bytes, bytes]:
    packets = prove_complete_packets(link)
    ident = next((p for p in packets if is_vorbis_ident(p)), None)
    comment = next((p for p in packets if p.startswith(VORBIS_COMMENT)), None)
    setup = next((p for p in packets if p.startswith(VORBIS_SETUP)), None)
    if ident is None or comment is None or setup is None:
        raise HarnessError("Vorbis link is missing ident, comment, or setup")
    return ident, comment, setup


def prove_later_link_replays_headers(first: bytes, later: bytes) -> None:
    """Prove *later* ident/comment/setup bytes equal *first*."""
    if _vorbis_header_triple(first) != _vorbis_header_triple(later):
        raise HarnessError(
            "later link ident/comment/setup packets do not replay the first link"
        )
    print("[F06] proved later link replays first-link headers", flush=True)


def two_distinct_vorbis_links() -> tuple[bytes, bytes]:
    """Two runtime-comment Vorbis files of different byte lengths. Raises."""
    first = _vorbis_comment_variant(_vorbis_bytes("a"))
    second = _vorbis_comment_variant(_vorbis_bytes("b"))
    if len(first) == len(second):
        mark = token().encode("ascii")
        second = replace_vorbis_comment(
            _vorbis_bytes("b"),
            vendor=b"suite-vendor-" + mark,
            fields=(
                b"TITLE=" + mark,
                b"NOTE=" + mark,
                b"EXTRA=" + mark,
                b"PAD=" + mark,
            ),
        )
    if len(first) == len(second):
        raise HarnessError("could not construct Vorbis links of different lengths")
    if first == second:
        raise HarnessError("Vorbis links are byte-identical")
    print(
        f"[F06] distinct Vorbis links len={len(first)} vs {len(second)}",
        flush=True,
    )
    return first, second


def _is_vorbis_later_header(packet: bytes) -> bool:
    return packet.startswith(VORBIS_COMMENT) or packet.startswith(VORBIS_SETUP)


def _is_vorbis_audio(packet: bytes) -> bool:
    if not packet:
        return False
    if is_vorbis_ident(packet) or _is_vorbis_later_header(packet):
        return False
    return True


def _split_vorbis_packets(
    packets: Sequence[bytes],
) -> tuple[bytes, list[bytes], list[bytes]]:
    if not packets:
        raise HarnessError("Vorbis stream has no packets")
    if not is_vorbis_ident(packets[0]):
        raise HarnessError("first packet is not a Vorbis identification header")
    ident = packets[0]
    later_headers: list[bytes] = []
    audio: list[bytes] = []
    seen_audio = False
    for pkt in packets[1:]:
        if not seen_audio and _is_vorbis_later_header(pkt):
            later_headers.append(pkt)
            continue
        seen_audio = True
        audio.append(pkt)
    if not later_headers:
        raise HarnessError("Vorbis stream has no later header packets")
    if not audio:
        raise HarnessError("Vorbis stream has no audio packet")
    return ident, later_headers, audio


def _vorbis_audio_count(data: bytes) -> int:
    _ident, _headers, audio = _split_vorbis_packets(complete_packets(data))
    return len(audio)


def vorbis_merge_host() -> bytes:
    """Runtime-comment Vorbis with at least three audio packets. Raises."""
    candidates = [
        _vorbis_comment_variant(_vorbis_bytes("a")),
        _vorbis_comment_variant(_vorbis_bytes("b")),
    ]
    for path in _SCALE_FILES:
        candidates.append(_vorbis_comment_variant(_read_fixture(path)))
    seen: list[int] = []
    for data in candidates:
        n = _vorbis_audio_count(data)
        seen.append(n)
        if n >= 3:
            print(f"[F06] merge host audio_packets={n} bytes={len(data)}", flush=True)
            return data
    raise HarnessError(
        "no suite Vorbis host has 3 audio packets "
        f"(counts={seen})"
    )


def distinct_serials() -> tuple[int, int]:
    """Two runtime-chosen distinct 32-bit serial numbers."""
    first = secrets.randbelow(2**32)
    second = secrets.randbelow(2**32)
    while second == first:
        second = secrets.randbelow(2**32)
    print(f"[F06] distinct serials {first} {second}", flush=True)
    return first, second


def merged_header_audio_link(
    data: bytes, *, serial: int, extra_audio_pages: int
) -> bytes:
    """One Vorbis link: ident BOS, then later headers plus first audio together.

    *extra_audio_pages* further audio pages follow the merged page. Zero means
    the merged page is the last page and carries end-of-stream.
    """
    if extra_audio_pages < 0:
        raise HarnessError(f"extra_audio_pages {extra_audio_pages} is negative")
    packets = prove_complete_packets(data)
    ident, later_headers, audio = _split_vorbis_packets(packets)
    needed = 1 + extra_audio_pages
    if len(audio) < needed:
        raise HarnessError(
            f"Vorbis host has {len(audio)} audio packets, need {needed}"
        )
    last_granule = parse_ogg_pages(data)[-1].granule
    out = bytearray()
    seq = 0
    out += emit_ogg_page(
        header_type=0x02,
        granule=0,
        serial=serial,
        sequence=seq,
        packets=[ident],
    )
    seq += 1
    merged_packets = list(later_headers) + [audio[0]]
    merged_eos = extra_audio_pages == 0
    out += emit_ogg_page(
        header_type=0x04 if merged_eos else 0,
        granule=last_granule if merged_eos else 0,
        serial=serial,
        sequence=seq,
        packets=merged_packets,
    )
    seq += 1
    for i in range(extra_audio_pages):
        last = i + 1 == extra_audio_pages
        out += emit_ogg_page(
            header_type=0x04 if last else 0,
            granule=last_granule if last else 0,
            serial=serial,
            sequence=seq,
            packets=[audio[1 + i]],
        )
        seq += 1
    rebuilt = bytes(out)
    prove_merged_header_audio_page(rebuilt)
    remaining = _audio_pages_after_merge(rebuilt)
    if remaining != extra_audio_pages:
        raise HarnessError(
            f"merged link kept {remaining} audio pages after the merge, "
            f"not {extra_audio_pages}"
        )
    print(
        f"[F06] merged link serial={serial} extra_audio_pages={extra_audio_pages} "
        f"bytes={len(rebuilt)}",
        flush=True,
    )
    return rebuilt


def _page_has_merged_header_audio(page) -> bool:
    chunks = page_packet_bytes(page)
    has_later_header = False
    has_audio = False
    n = len(chunks)
    for i, chunk in enumerate(chunks):
        continued_head = page.continued and i == 0
        is_tail = page.tail and i == n - 1
        if continued_head or is_tail:
            continue
        if _is_vorbis_later_header(chunk):
            has_later_header = True
        elif _is_vorbis_audio(chunk):
            has_audio = True
    return has_later_header and has_audio


def prove_merged_header_audio_page(data: bytes) -> None:
    """Prove some page holds a later header packet and an audio packet."""
    pages = parse_ogg_pages(data)
    for page in pages:
        if _page_has_merged_header_audio(page):
            print(
                f"[F06] proved merged header+audio page seq={page.sequence}",
                flush=True,
            )
            return
    raise HarnessError(
        "no page contains both a later header packet and an audio packet"
    )


def _audio_pages_after_merge(data: bytes) -> int:
    pages = parse_ogg_pages(data)
    for i, page in enumerate(pages):
        if _page_has_merged_header_audio(page):
            return len(pages) - i - 1
    raise HarnessError("no merged header+audio page")


def with_incomplete_final_packet(data: bytes) -> bytes:
    """Cut after the first unfinished packet fragment; drop its continuation.

    The last remaining page is a complete Ogg page whose last lace is 255.
    This is not "drop the file's last page".
    """
    spanned = with_marked_packet_span(data)
    pages = parse_ogg_pages(spanned)
    cut_at = None
    for i in range(len(pages) - 1):
        if pages[i].tail and pages[i + 1].continued:
            cut_at = i
            break
    if cut_at is None:
        raise HarnessError(
            "marked span has no tail page followed by a continuation page"
        )
    dropped = pages[cut_at + 1]
    if not dropped.continued:
        raise HarnessError("page after the cut is not a continuation")
    end = pages[cut_at].offset + pages[cut_at].size
    truncated = bytes(spanned[:end])
    prove_incomplete_final_packet(truncated)
    print(
        f"[F06] incomplete final packet kept_pages={cut_at + 1} "
        f"dropped_from={cut_at + 1} of {len(pages)} bytes={len(truncated)}",
        flush=True,
    )
    return truncated


def prove_incomplete_final_packet(data: bytes) -> None:
    """Prove a legal page sequence whose last packet has not ended."""
    pages = parse_ogg_pages(data)
    if not pages[-1].tail:
        raise HarnessError(
            "last page does not continue a packet (last lace is not 255)"
        )
    try:
        complete_packets(data)
    except HarnessError as exc:
        if "incomplete packet" not in str(exc):
            raise
        print(
            f"[F06] proved incomplete final packet pages={len(pages)} "
            f"last_tail={pages[-1].tail}",
            flush=True,
        )
        return
    raise HarnessError("complete_packets succeeded; the final packet is finished")


def _first_opus_audio(packets: Sequence[bytes]) -> bytes:
    if not packets:
        raise HarnessError("Opus link has no packets")
    if not is_opus_head(packets[0]):
        raise HarnessError("first packet is not OpusHead")
    for pkt in packets[1:]:
        if pkt.startswith(OPUS_TAGS_MAGIC):
            continue
        return pkt
    raise HarnessError("Opus link has no audio packet")


def prove_opus_mode_link(
    link: bytes,
    kind: str,
    *,
    channels: int | tuple[int, ...] | None = None,
) -> None:
    """Prove family 0, TOC kind, and channel count. Failure raises."""
    packets = prove_complete_packets(link)
    ch, family = opus_head_fields(packets[0])
    if family != 0:
        raise HarnessError(f"{kind} link mapping family is {family}, not 0")
    got = rfc6716_config_kind(_first_opus_audio(packets))
    if got != kind:
        raise HarnessError(
            f"{kind} link first audio TOC kind is {got!r}, not {kind!r}"
        )
    if channels is None:
        if kind == "silk":
            allowed: tuple[int, ...] = (1,)
        elif kind == "celt":
            allowed = (2,)
        else:
            allowed = (1, 2)
    elif isinstance(channels, int):
        allowed = (channels,)
    else:
        allowed = tuple(channels)
    if ch not in allowed:
        raise HarnessError(
            f"{kind} link channel count is {ch}, not {allowed}"
        )
    print(
        f"[F06] proved {kind} family=0 channels={ch} toc={got}",
        flush=True,
    )


def family0_chain_bytes(ws: Workspace, kinds: Sequence[str]) -> bytes:
    """Runtime-tagged classified family-0 files concatenated in *kinds* order."""
    if len(kinds) < 2:
        raise HarnessError("a chain needs at least two links")
    parts: list[bytes] = []
    for kind in kinds:
        rel = opus_with_runtime_tags(ws, kind)
        data = ws.read_bytes(rel)
        prove_opus_mode_link(data, kind)
        parts.append(data)
    chained = concat_bitstreams(parts)
    prove_link_count(chained, len(kinds))
    print(
        f"[F06] family-0 chain kinds={list(kinds)} bytes={len(chained)}",
        flush=True,
    )
    return chained


def with_link_opus_family(data: bytes, link_index: int, family: int) -> bytes:
    """Rewrite one link's OpusHead mapping family. Proof failure raises."""
    links = ogg_links(data)
    if not 0 <= link_index < len(links):
        raise HarnessError(
            f"link index {link_index} out of range ({len(links)} links)"
        )
    mutated = set_opus_head_family(links[link_index], family)
    parts = [mutated if i == link_index else links[i] for i in range(len(links))]
    out = concat_bitstreams(parts)
    prove_link_opus_family(out, link_index, family=family)
    return out


def with_link_opus_channels(data: bytes, link_index: int, channels: int) -> bytes:
    """Rewrite one link's OpusHead channel count. Proof failure raises."""
    links = ogg_links(data)
    if not 0 <= link_index < len(links):
        raise HarnessError(
            f"link index {link_index} out of range ({len(links)} links)"
        )
    mutated = set_opus_head_channels(links[link_index], channels)
    parts = [mutated if i == link_index else links[i] for i in range(len(links))]
    out = concat_bitstreams(parts)
    prove_link_opus_channels(out, link_index, channels=channels)
    return out


def prove_link_opus_family(
    data: bytes, link_index: int, *, family: int | None = None, nonzero: bool = False
) -> None:
    """Prove one link's OpusHead mapping family. Failure raises."""
    links = ogg_links(data)
    if not 0 <= link_index < len(links):
        raise HarnessError(
            f"link index {link_index} out of range ({len(links)} links)"
        )
    packets = prove_complete_packets(links[link_index])
    _ch, got = opus_head_fields(packets[0])
    if nonzero:
        if got == 0:
            raise HarnessError(f"link {link_index} mapping family is still 0")
    elif family is not None and got != family:
        raise HarnessError(
            f"link {link_index} mapping family is {got}, not {family}"
        )
    pages = parse_ogg_pages(links[link_index])
    if not (pages[0].header_type & 0x02):
        raise HarnessError(f"link {link_index} does not start at BOS")
    print(
        f"[F06] proved link {link_index} family={got} nonzero={nonzero}",
        flush=True,
    )


def prove_link_opus_channels(
    data: bytes,
    link_index: int,
    *,
    channels: int | None = None,
    allowed: tuple[int, ...] | None = None,
    illegal: bool = False,
) -> None:
    """Prove one link's OpusHead channel count. Failure raises."""
    links = ogg_links(data)
    if not 0 <= link_index < len(links):
        raise HarnessError(
            f"link index {link_index} out of range ({len(links)} links)"
        )
    packets = prove_complete_packets(links[link_index])
    got, family = opus_head_fields(packets[0])
    if illegal:
        if family != 0:
            raise HarnessError(
                f"link {link_index} mapping family is {family}, not 0"
            )
        if got in (1, 2):
            raise HarnessError(
                f"link {link_index} channel count {got} is still 1 or 2"
            )
    elif channels is not None and got != channels:
        raise HarnessError(
            f"link {link_index} channel count is {got}, not {channels}"
        )
    elif allowed is not None and got not in allowed:
        raise HarnessError(
            f"link {link_index} channel count is {got}, not in {allowed}"
        )
    print(
        f"[F06] proved link {link_index} channels={got} family={family} "
        f"illegal={illegal}",
        flush=True,
    )


def prove_family0_supported_link(data: bytes, link_index: int) -> None:
    """Prove one link is family 0 with channel count 1 or 2."""
    prove_link_opus_family(data, link_index, family=0)
    prove_link_opus_channels(data, link_index, allowed=(1, 2))


def place_bytes(ws: Workspace, data: bytes, prefix: str, suffix: str) -> str:
    """Write *data* to a unique workspace path."""
    if not isinstance(data, (bytes, bytearray)):
        raise HarnessError(f"place_bytes expected bytes, got {type(data)!r}")
    rel = unique_name(prefix) + suffix
    ws.write(rel, bytes(data))
    return rel


__all__ = (
    "concat_bitstreams",
    "distinct_serials",
    "family0_chain_bytes",
    "merged_header_audio_link",
    "ogg_links",
    "place_bytes",
    "prove_complete_packets",
    "prove_family0_supported_link",
    "prove_incomplete_final_packet",
    "prove_later_link_replays_headers",
    "prove_link_count",
    "prove_link_opus_channels",
    "prove_link_opus_family",
    "prove_merged_header_audio_page",
    "prove_only_last_link_lacks_eos",
    "prove_opus_mode_link",
    "prove_stored_crc",
    "two_distinct_vorbis_links",
    "vorbis_merge_host",
    "with_incomplete_final_packet",
    "with_link_opus_channels",
    "with_link_opus_family",
    "without_final_eos",
)
