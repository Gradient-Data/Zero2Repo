# feature: F02
"""Feature-local helpers for lossless Ogg Vorbis compress and expand.

Ogg page construction follows RFC 3533. Vorbis identification, comment,
setup, Floor1 classwords, and codebook lookup fields follow the Vorbis I
specification. These helpers build suite inputs and read destination
files; they are not a substitute public entry.
"""

from __future__ import annotations

import os
import secrets
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from F01_helpers import (
    _opus_bytes,
    _vorbis_bytes,
    require_ok,
    run_product,
    unique_name,
)
from _harness import HarnessError, RunResult, Workspace, files_identical, stored_copy

OGG_CAPTURE = b"OggS"
OGG_HDRMIN = 27
OGG_MAXSEG = 255
VORBIS_IDENT = b"\x01vorbis"
VORBIS_COMMENT = b"\x03vorbis"
VORBIS_SETUP = b"\x05vorbis"
OPUS_HEAD = b"OpusHead"
BOOK_SYNC = 0x564342
QUANT = (256, 128, 86, 64)


def _crc_table() -> tuple[int, ...]:
    table = []
    for i in range(256):
        c = i << 24
        for _ in range(8):
            if c & 0x80000000:
                c = ((c << 1) ^ 0x04C11DB7) & 0xFFFFFFFF
            else:
                c = (c << 1) & 0xFFFFFFFF
        table.append(c)
    return tuple(table)


_CRC = _crc_table()


def ogg_crc32(data: bytes) -> int:
    """RFC 3533 CRC-32: unreflected, zero seed, polynomial 0x04c11db7."""
    crc = 0
    for byte in data:
        crc = ((crc << 8) ^ _CRC[((crc >> 24) ^ byte) & 0xFF]) & 0xFFFFFFFF
    return crc


def ogg_crc_page(page: bytes) -> int:
    if len(page) < 26:
        raise HarnessError("Ogg page shorter than the checksum field")
    return ogg_crc32(page[:22] + b"\x00\x00\x00\x00" + page[26:])


def _u32le(buf: bytes, at: int) -> int:
    return int.from_bytes(buf[at : at + 4], "little")


def _put_u32le(buf: bytearray, at: int, value: int) -> None:
    buf[at : at + 4] = int(value & 0xFFFFFFFF).to_bytes(4, "little")


def _unpack_packets(laces: Sequence[int]) -> tuple[list[int], bool]:
    lengths: list[int] = []
    run = 0
    tail = False
    for value in laces:
        run += value
        if value != OGG_MAXSEG:
            lengths.append(run)
            run = 0
    if laces and laces[-1] == OGG_MAXSEG:
        lengths.append(run)
        tail = True
    return lengths, tail


def _pack_laces(lengths: Sequence[int], *, tail: bool) -> list[int]:
    laces: list[int] = []
    for i, raw in enumerate(lengths):
        remaining = int(raw)
        if remaining < 0:
            raise HarnessError(f"negative packet length {remaining}")
        while remaining >= OGG_MAXSEG:
            if len(laces) >= OGG_MAXSEG:
                raise HarnessError("Ogg page needs more than 255 segments")
            laces.append(OGG_MAXSEG)
            remaining -= OGG_MAXSEG
        if not (tail and i == len(lengths) - 1):
            if len(laces) >= OGG_MAXSEG:
                raise HarnessError("Ogg page needs more than 255 segments")
            laces.append(remaining)
    if not laces:
        raise HarnessError("Ogg page has no segments")
    return laces


@dataclass
class OggPage:
    offset: int
    header_type: int
    granule: int
    serial: int
    sequence: int
    laces: list[int]
    packet_lens: list[int]
    tail: bool
    body: bytes
    raw: bytes

    @property
    def size(self) -> int:
        return len(self.raw)

    @property
    def continued(self) -> bool:
        return bool(self.header_type & 1)


def parse_ogg_pages(data: bytes) -> list[OggPage]:
    """Parse a complete RFC 3533 bitstream. Truncation or a bad capture raises."""
    pages: list[OggPage] = []
    i = 0
    n = len(data)
    while i < n:
        if i + OGG_HDRMIN > n:
            raise HarnessError(f"truncated Ogg page header at {i}")
        if data[i : i + 4] != OGG_CAPTURE:
            raise HarnessError(f"missing OggS capture at {i}")
        if data[i + 4] != 0:
            raise HarnessError(f"nonzero Ogg version at {i}")
        nseg = data[i + 26]
        header_len = OGG_HDRMIN + nseg
        if i + header_len > n:
            raise HarnessError(f"truncated segment table at {i}")
        laces = list(data[i + OGG_HDRMIN : i + header_len])
        body_len = sum(laces)
        end = header_len + body_len
        if i + end > n:
            raise HarnessError(f"truncated Ogg page body at {i}")
        raw = data[i : i + end]
        stored = _u32le(raw, 22)
        expect = ogg_crc_page(raw)
        if stored != expect:
            raise HarnessError(
                f"RFC 3533 checksum mismatch at {i}: stored={stored} expect={expect}"
            )
        packet_lens, tail = _unpack_packets(laces)
        granule = int.from_bytes(raw[6:14], "little")
        pages.append(
            OggPage(
                offset=i,
                header_type=raw[5],
                granule=granule,
                serial=_u32le(raw, 14),
                sequence=_u32le(raw, 18),
                laces=laces,
                packet_lens=packet_lens,
                tail=tail,
                body=raw[header_len:],
                raw=raw,
            )
        )
        i += end
    if not pages:
        raise HarnessError("no Ogg pages in input")
    return pages


def emit_ogg_page(
    *,
    header_type: int,
    granule: int,
    serial: int,
    sequence: int,
    packets: Sequence[bytes],
    tail: bool = False,
) -> bytes:
    """Serialize one Ogg page with a computed RFC 3533 checksum."""
    if not packets:
        raise HarnessError("cannot emit an empty Ogg page")
    lengths = [len(p) for p in packets]
    laces = _pack_laces(lengths, tail=tail)
    body = b"".join(packets)
    raw = bytearray(OGG_HDRMIN + len(laces) + len(body))
    raw[0:4] = OGG_CAPTURE
    raw[4] = 0
    raw[5] = header_type & 0xFF
    raw[6:14] = int(granule & ((1 << 64) - 1)).to_bytes(8, "little")
    _put_u32le(raw, 14, serial)
    _put_u32le(raw, 18, sequence)
    raw[26] = len(laces)
    raw[OGG_HDRMIN : OGG_HDRMIN + len(laces)] = bytes(laces)
    raw[OGG_HDRMIN + len(laces) :] = body
    _put_u32le(raw, 22, ogg_crc_page(bytes(raw)))
    return bytes(raw)


def emit_ogg_pages(pages: Sequence[bytes]) -> bytes:
    if not pages:
        raise HarnessError("no pages to emit")
    return b"".join(pages)


def page_packet_bytes(page: OggPage) -> list[bytes]:
    chunks: list[bytes] = []
    off = 0
    for length in page.packet_lens:
        chunks.append(page.body[off : off + length])
        off += length
    if off != len(page.body):
        raise HarnessError("page body length does not match packet lengths")
    return chunks


def first_complete_packet(data: bytes) -> bytes:
    page = parse_ogg_pages(data)[0]
    chunks = page_packet_bytes(page)
    if not chunks:
        raise HarnessError("first Ogg page has no packets")
    if page.continued:
        raise HarnessError("first Ogg page continues a packet")
    if page.tail and len(chunks) == 1:
        raise HarnessError("first Ogg page has no complete packet")
    if page.tail:
        return chunks[0]
    return chunks[0]


def is_vorbis_ident(packet: bytes) -> bool:
    return packet.startswith(VORBIS_IDENT)


def is_opus_head(packet: bytes) -> bool:
    return packet.startswith(OPUS_HEAD)


def rewrite_first_page_packet(data: bytes, packet: bytes) -> bytes:
    pages = parse_ogg_pages(data)
    first = pages[0]
    chunks = page_packet_bytes(first)
    if not chunks:
        raise HarnessError("first page has no packets to rewrite")
    if first.continued:
        raise HarnessError("cannot rewrite a continued first packet")
    chunks[0] = packet
    rebuilt = emit_ogg_page(
        header_type=first.header_type,
        granule=first.granule,
        serial=first.serial,
        sequence=first.sequence,
        packets=chunks,
        tail=first.tail,
    )
    return rebuilt + data[first.offset + first.size :]


def append_trailing_pages(first_page: bytes, following: bytes) -> bytes:
    parse_ogg_pages(first_page)
    parse_ogg_pages(following)
    return first_page + following


def complete_packets(data: bytes) -> list[bytes]:
    """Return every complete packet in *data*. An unfinished tail raises."""
    pages = parse_ogg_pages(data)
    buf = b""
    out: list[bytes] = []
    for page in pages:
        chunks = page_packet_bytes(page)
        for i, chunk in enumerate(chunks):
            continued_head = page.continued and i == 0
            is_tail = page.tail and i == len(chunks) - 1
            if continued_head:
                buf += chunk
                if not is_tail:
                    out.append(buf)
                    buf = b""
            elif is_tail:
                buf = chunk
            else:
                out.append(chunk)
    if buf:
        raise HarnessError("bitstream ends on an incomplete packet")
    return out


def _replace_page_packet(
    data: bytes, page_index: int, packet_index: int, new_packet: bytes
) -> bytes:
    pages = parse_ogg_pages(data)
    if page_index >= len(pages):
        raise HarnessError(f"page index {page_index} out of range")
    page = pages[page_index]
    chunks = page_packet_bytes(page)
    if packet_index >= len(chunks):
        raise HarnessError(f"packet index {packet_index} out of range")
    if page.continued and packet_index == 0:
        raise HarnessError("cannot replace a continued packet in place")
    if page.tail and packet_index == len(chunks) - 1:
        raise HarnessError("cannot replace a continuing packet in place")
    chunks[packet_index] = new_packet
    rebuilt = emit_ogg_page(
        header_type=page.header_type,
        granule=page.granule,
        serial=page.serial,
        sequence=page.sequence,
        packets=chunks,
        tail=page.tail,
    )
    return data[: page.offset] + rebuilt + data[page.offset + page.size :]


def _find_interior_audio(data: bytes) -> tuple[int, int, bytes]:
    """Locate a complete interior audio packet (not first/last on its page)."""
    pages = parse_ogg_pages(data)
    for pi, page in enumerate(pages):
        chunks = page_packet_bytes(page)
        n = len(chunks)
        for ji, chunk in enumerate(chunks):
            continued = page.continued and ji == 0
            continuing = page.tail and ji == n - 1
            if continued or continuing:
                continue
            if ji <= 0 or ji + 1 >= n:
                continue
            if not chunk or (chunk[0] & 1):
                continue
            return pi, ji, chunk
    raise HarnessError(
        "fixture has no interior complete audio packet "
        "(not continued, not continuing, not first or last on its page)"
    )


def with_interior_unused_zero_padding(data: bytes, extra_bytes: int | None = None) -> bytes:
    """Append a runtime-chosen count of unused zero bytes to an interior audio packet."""
    if extra_bytes is None:
        extra_bytes = 2 + secrets.randbelow(7)
    if extra_bytes < 1:
        raise HarnessError("extra padding count must be positive")
    page_i, pkt_i, packet = _find_interior_audio(data)
    padded = packet + (b"\x00" * extra_bytes)
    if padded == packet:
        raise HarnessError("padded packet equals the baseline")
    return _replace_page_packet(data, page_i, pkt_i, padded)


def with_shortened_unused_zero_padding(data: bytes) -> tuple[bytes, bytes]:
    """Return (shortened, extra-padding sibling) sharing one interior packet.

    Extra padding appends N unused zero bytes. Shortened keeps a proper
    nonempty subset of those bytes so the coded payload is intact and the
    two files differ.
    """
    extra_n = 2 + secrets.randbelow(7)
    short_n = 1 + secrets.randbelow(extra_n - 1)
    extra = with_interior_unused_zero_padding(data, extra_n)
    shortened = with_interior_unused_zero_padding(data, short_n)
    if extra == shortened:
        raise HarnessError("shortened file equals the extra-padding sibling")
    if shortened == data:
        raise HarnessError("shortened file equals the baseline")
    return shortened, extra


# ---------------------------------------------------------------------------
# Vorbis I bitstream (LSB-first within each byte)
# ---------------------------------------------------------------------------


class _BitReader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def remaining(self) -> int:
        return len(self.data) * 8 - self.pos

    def read(self, n: int) -> int:
        if n < 0 or self.pos + n > len(self.data) * 8:
            raise HarnessError(
                f"Vorbis packet ends inside a field at bit {self.pos} (need {n})"
            )
        value = 0
        for i in range(n):
            value |= ((self.data[self.pos >> 3] >> (self.pos & 7)) & 1) << i
            self.pos += 1
        return value


class _ImplicitZeroReader(_BitReader):
    """Bit reader that supplies zero for bits past the packet.

    Vorbis I reads a short packet as the same symbols when the omitted
    tail of the canonical bitstream is zero. A read that cannot be
    classified still raises from the caller; this reader only defines
    the missing-bit case.
    """

    def read(self, n: int) -> int:
        if n < 0:
            raise HarnessError(f"cannot read {n} bits")
        value = 0
        for i in range(n):
            if self.pos < len(self.data) * 8:
                bit = (self.data[self.pos >> 3] >> (self.pos & 7)) & 1
            else:
                bit = 0
            value |= bit << i
            self.pos += 1
        return value


class _BitWriter:
    def __init__(self) -> None:
        self._bits: list[int] = []

    def write(self, n: int, value: int) -> None:
        for i in range(n):
            self._bits.append((value >> i) & 1)

    def extend_from(self, data: bytes, start: int, end: int) -> None:
        if start < 0 or end < start or end > len(data) * 8:
            raise HarnessError("cannot copy bits outside the packet")
        for pos in range(start, end):
            self._bits.append((data[pos >> 3] >> (pos & 7)) & 1)

    def to_bytes(self) -> bytes:
        if not self._bits:
            return b""
        out = bytearray((len(self._bits) + 7) // 8)
        for i, bit in enumerate(self._bits):
            if bit:
                out[i >> 3] |= 1 << (i & 7)
        return bytes(out)


def _ilog(v: int) -> int:
    n = 0
    while v:
        n += 1
        v >>= 1
    return n


def _lookup1_values(entries: int, dim: int) -> int:
    v = 0
    while True:
        prod = 1
        overflow = False
        for _ in range(dim):
            if v + 1 == 0 or prod > entries // (v + 1):
                overflow = True
                break
            prod *= v + 1
        if overflow or prod > entries:
            return v
        v += 1


def _make_words(lengths: Sequence[int]) -> list[int]:
    marker = [0] * 33
    codes = [0] * len(lengths)
    for i, length in enumerate(lengths):
        if not length:
            continue
        entry = marker[length]
        if length < 32 and (entry >> length):
            raise HarnessError("over-populated Vorbis codebook")
        codes[i] = entry
        for j in range(length, 0, -1):
            if marker[j] & 1:
                marker[j] = marker[1] + 1 if j == 1 else (marker[j - 1] << 1)
                break
            marker[j] += 1
        for j in range(length + 1, 33):
            if (marker[j] >> 1) != entry:
                break
            entry = marker[j]
            marker[j] = marker[j - 1] << 1
    return codes


def _build_tree(lengths: Sequence[int], codes: Sequence[int]) -> list[int]:
    used = sum(1 for length in lengths if length)
    cap = used + 2
    nodes = [0] * (2 * cap)
    next_node = 1
    for i, length in enumerate(lengths):
        if not length:
            continue
        idx = 0
        for k in range(length, 1, -1):
            child = 2 * idx + ((codes[i] >> (k - 1)) & 1)
            node = nodes[child]
            if node == 0:
                node = next_node
                next_node += 1
                if next_node > cap:
                    raise HarnessError("Vorbis codebook tree overflows")
                nodes[child] = node
            if node <= 0:
                raise HarnessError("Vorbis codebook is not prefix-free")
            idx = node
        leaf = 2 * idx + (codes[i] & 1)
        if nodes[leaf]:
            raise HarnessError("Vorbis codebook is not prefix-free")
        nodes[leaf] = -(i + 1)
    return nodes


@dataclass
class _Book:
    dim: int = 0
    ent: int = 0
    look: int = 0
    look_pos: int = 0
    value_bits: int = 0
    mult_pos: int = 0
    nmult: int = 0
    lengths: list[int] = field(default_factory=list)
    codes: list[int] = field(default_factory=list)
    tree: list[int] = field(default_factory=list)


@dataclass
class _Floor1:
    parts: int = 0
    pcls: list[int] = field(default_factory=list)
    cdim: list[int] = field(default_factory=list)
    csub: list[int] = field(default_factory=list)
    cbook: list[int] = field(default_factory=list)
    csb: list[list[int]] = field(default_factory=list)
    mult: int = 1
    quant: int = 256
    posts: int = 2


@dataclass
class _Residue:
    rtype: int = 0
    begin: int = 0
    end: int = 0
    psz: int = 1
    ncl: int = 1
    cbook: int = 0
    books: list[list[int]] = field(default_factory=list)


@dataclass
class _Setup:
    books: list[_Book]
    floors: list[_Floor1]
    floor_type_pos: list[int]
    mux: list[list[int]]
    floor_of_sub: list[list[int]]
    blockflag: list[int]
    mdmap: list[int]
    channels: int
    residue_pos: int = 0
    mag: list[list[int]] = field(default_factory=list)
    ang: list[list[int]] = field(default_factory=list)
    res_of_sub: list[list[int]] = field(default_factory=list)
    residues: list[_Residue] = field(default_factory=list)
    bs0: int = 0
    bs1: int = 0


def _parse_book(br: _BitReader) -> _Book:
    sync = br.read(24)
    if sync != BOOK_SYNC:
        raise HarnessError(f"codebook sync is not 0x564342 (got {sync:#x})")
    book = _Book()
    book.dim = br.read(16)
    book.ent = br.read(24)
    if book.dim == 0:
        raise HarnessError("codebook dimension is 0")
    book.lengths = [0] * book.ent
    if br.read(1):
        got = 0
        current = br.read(5) + 1
        while got < book.ent:
            run = br.read(_ilog(book.ent - got))
            if got + run > book.ent:
                raise HarnessError("ordered codebook run overruns the book")
            for i in range(got, got + run):
                book.lengths[i] = current
            got += run
            current += 1
    else:
        sparse = br.read(1)
        if not sparse:
            for i in range(book.ent):
                book.lengths[i] = br.read(5) + 1
        else:
            for i in range(book.ent):
                if br.read(1):
                    book.lengths[i] = br.read(5) + 1
    book.look_pos = br.pos
    book.look = br.read(4)
    if book.look:
        br.read(32)
        br.read(32)
        value_bits = br.read(4) + 1
        br.read(1)
        book.value_bits = value_bits
        book.mult_pos = br.pos
        if book.look == 1:
            book.nmult = _lookup1_values(book.ent, book.dim)
        elif book.look == 2:
            book.nmult = book.ent * book.dim
        else:
            raise HarnessError(f"codebook lookup type {book.look} is not 0–2")
        for _ in range(book.nmult):
            br.read(value_bits)
    book.codes = _make_words(book.lengths)
    book.tree = _build_tree(book.lengths, book.codes)
    return book


def _bk_get(br: _BitReader, book: _Book) -> int:
    idx = 0
    while True:
        bit = br.read(1)
        node = book.tree[2 * idx + bit]
        if node == 0:
            raise HarnessError("packet holds no such codebook word")
        if node < 0:
            return -node - 1
        idx = node


def _bk_put(bw: _BitWriter, book: _Book, entry: int) -> None:
    if entry >= book.ent or not book.lengths[entry]:
        raise HarnessError(f"codebook has no entry {entry}")
    length = book.lengths[entry]
    code = book.codes[entry]
    for k in range(length, 0, -1):
        bw.write(1, (code >> (k - 1)) & 1)


def _book_encodes(book: _Book, entry: int) -> bool:
    return 0 <= entry < book.ent and bool(book.lengths[entry])


def _subclass_encodes(floor: _Floor1, books: Sequence[_Book], cls: int, sub: int, y_val: int) -> bool:
    sub_book = floor.csb[cls][sub]
    if sub_book < 0:
        return y_val == 0
    if sub_book >= len(books):
        return False
    return _book_encodes(books[sub_book], y_val)


def _parse_ident_info(packet: bytes) -> tuple[int, int, int]:
    """Return (channels, blocksize_0, blocksize_1) from a Vorbis I ident packet."""
    if not is_vorbis_ident(packet):
        raise HarnessError("first complete packet is not a Vorbis identification header")
    br = _BitReader(packet)
    br.read(8 * 7)
    if br.read(32) != 0:
        raise HarnessError("Vorbis identification version is not 0")
    channels = br.read(8)
    if channels < 1:
        raise HarnessError("Vorbis identification names no channels")
    br.read(32)
    br.read(32)
    br.read(32)
    br.read(32)
    sizes = br.read(8)
    bs0 = 1 << (sizes & 15)
    bs1 = 1 << (sizes >> 4)
    if bs0 < 64 or bs1 < bs0 or bs1 > 8192:
        raise HarnessError(f"Vorbis block sizes {bs0} and {bs1} are not valid")
    return channels, bs0, bs1


def _parse_ident_channels(packet: bytes) -> int:
    return _parse_ident_info(packet)[0]


def parse_vorbis_setup(setup: bytes, channels: int) -> _Setup:
    br = _BitReader(setup)
    if bytes([br.read(8) for _ in range(7)]) != VORBIS_SETUP:
        raise HarnessError("packet is not a Vorbis setup header")
    nbooks = br.read(8) + 1
    books = [_parse_book(br) for _ in range(nbooks)]
    ntime = br.read(6) + 1
    for _ in range(ntime):
        if br.read(16) != 0:
            raise HarnessError("nonzero Vorbis time-domain type")
    nfloors = br.read(6) + 1
    floors: list[_Floor1] = []
    floor_type_pos: list[int] = []
    for _ in range(nfloors):
        floor_type_pos.append(br.pos)
        ftype = br.read(16)
        if ftype != 1:
            raise HarnessError(f"setup floor type {ftype} is not Floor1")
        fl = _Floor1()
        fl.parts = br.read(5)
        fl.pcls = [br.read(4) for _ in range(fl.parts)]
        nclass = (max(fl.pcls) + 1) if fl.pcls else 0
        fl.cdim = [0] * 16
        fl.csub = [0] * 16
        fl.cbook = [-1] * 16
        fl.csb = [[-1] * 8 for _ in range(16)]
        for i in range(nclass):
            fl.cdim[i] = br.read(3) + 1
            subclasses = br.read(2)
            fl.csub[i] = subclasses
            if subclasses:
                fl.cbook[i] = br.read(8)
            for j in range(1 << subclasses):
                fl.csb[i][j] = br.read(8) - 1
        fl.mult = br.read(2) + 1
        fl.quant = QUANT[fl.mult - 1]
        rangebits = br.read(4)
        posts = 2
        for i in range(fl.parts):
            for _ in range(fl.cdim[fl.pcls[i]]):
                br.read(rangebits)
                posts += 1
        fl.posts = posts
        floors.append(fl)
    residue_pos = br.pos
    nres = br.read(6) + 1
    residues: list[_Residue] = []
    for _ in range(nres):
        res = _Residue()
        res.rtype = br.read(16)
        res.begin = br.read(24)
        res.end = br.read(24)
        res.psz = br.read(24) + 1
        res.ncl = br.read(6) + 1
        res.cbook = br.read(8)
        cascade = []
        for _cls in range(res.ncl):
            low = br.read(3)
            if br.read(1):
                low |= br.read(5) << 3
            cascade.append(low)
        res.books = [[-1] * 8 for _ in range(res.ncl)]
        for i in range(res.ncl):
            for j in range(8):
                if cascade[i] & (1 << j):
                    res.books[i][j] = br.read(8)
        residues.append(res)
    nmaps = br.read(6) + 1
    mux: list[list[int]] = []
    floor_of_sub: list[list[int]] = []
    res_of_sub: list[list[int]] = []
    mag: list[list[int]] = []
    ang: list[list[int]] = []
    for _ in range(nmaps):
        if br.read(16) != 0:
            raise HarnessError("nonzero Vorbis mapping type")
        flag = br.read(1)
        submaps = (br.read(4) + 1) if flag else 1
        coup = br.read(1)
        steps = (br.read(8) + 1) if coup else 0
        mag_ch: list[int] = []
        ang_ch: list[int] = []
        ilog_ch = _ilog(channels - 1) if channels > 1 else 0
        for _step in range(steps):
            mag_ch.append(br.read(ilog_ch))
            ang_ch.append(br.read(ilog_ch))
        br.read(2)
        ch_mux = [0] * channels
        if submaps > 1:
            ch_mux = [br.read(4) for _ in range(channels)]
        fls = []
        rss = []
        for _sub in range(submaps):
            br.read(8)
            fls.append(br.read(8))
            rss.append(br.read(8))
        mux.append(ch_mux)
        floor_of_sub.append(fls)
        res_of_sub.append(rss)
        mag.append(mag_ch)
        ang.append(ang_ch)
    nmodes = br.read(6) + 1
    blockflag = []
    mdmap = []
    for _ in range(nmodes):
        blockflag.append(br.read(1))
        br.read(16)
        br.read(16)
        mdmap.append(br.read(8))
    if br.read(1) != 1:
        raise HarnessError("Vorbis setup framing bit is not set")
    return _Setup(
        books=books,
        floors=floors,
        floor_type_pos=floor_type_pos,
        mux=mux,
        floor_of_sub=floor_of_sub,
        blockflag=blockflag,
        mdmap=mdmap,
        channels=channels,
        mag=mag,
        ang=ang,
        res_of_sub=res_of_sub,
        residues=residues,
        residue_pos=residue_pos,
    )


def _load_setup(data: bytes) -> tuple[_Setup, list[bytes]]:
    packets = complete_packets(data)
    if len(packets) < 3:
        raise HarnessError("Vorbis file is missing identification, comment, or setup")
    channels, bs0, bs1 = _parse_ident_info(packets[0])
    setup_pkt = next((p for p in packets if p.startswith(VORBIS_SETUP)), None)
    if setup_pkt is None:
        raise HarnessError("Vorbis file has no setup header")
    setup = parse_vorbis_setup(setup_pkt, channels)
    setup.bs0 = bs0
    setup.bs1 = bs1
    return setup, packets


def _decode_floor1(
    br: _BitReader, floor: _Floor1, books: Sequence[_Book]
) -> tuple[int | None, list[int], list[int]]:
    used = br.read(1)
    if not used:
        return 0, [], []
    pbits = _ilog(floor.quant - 1)
    y_vals = [br.read(pbits), br.read(pbits)]
    classes: list[int] = []
    for i in range(floor.parts):
        cls = floor.pcls[i]
        dim = floor.cdim[cls]
        bits = floor.csub[cls]
        classword = 0
        if bits:
            book_i = floor.cbook[cls]
            if book_i < 0 or book_i >= len(books):
                raise HarnessError("Floor1 master book is out of range")
            classword = _bk_get(br, books[book_i])
        classes.append(classword)
        shifted = classword
        for _ in range(dim):
            sub = shifted & ((1 << bits) - 1) if bits else 0
            shifted >>= bits
            sub_book = floor.csb[cls][sub]
            if sub_book >= 0:
                if sub_book >= len(books):
                    raise HarnessError("Floor1 subclass book is out of range")
                y_vals.append(_bk_get(br, books[sub_book]))
            else:
                y_vals.append(0)
    return 1, y_vals, classes


def _encode_floor1(
    bw: _BitWriter,
    floor: _Floor1,
    books: Sequence[_Book],
    used: int,
    y_vals: Sequence[int],
    classes: Sequence[int],
) -> None:
    bw.write(1, used)
    if not used:
        return
    pbits = _ilog(floor.quant - 1)
    bw.write(pbits, y_vals[0])
    bw.write(pbits, y_vals[1])
    post = 2
    for i in range(floor.parts):
        cls = floor.pcls[i]
        dim = floor.cdim[cls]
        bits = floor.csub[cls]
        classword = classes[i]
        if bits:
            _bk_put(bw, books[floor.cbook[cls]], classword)
        shifted = classword
        for _ in range(dim):
            sub = shifted & ((1 << bits) - 1) if bits else 0
            shifted >>= bits
            sub_book = floor.csb[cls][sub]
            if sub_book >= 0:
                _bk_put(bw, books[sub_book], y_vals[post])
            post += 1


def _audio_preamble(br: _BitReader, setup: _Setup) -> int:
    if br.read(1) != 0:
        raise HarnessError("header packet on the audio path")
    nmodes = len(setup.blockflag)
    mode = br.read(_ilog(nmodes - 1)) if nmodes > 1 else 0
    if mode >= nmodes:
        raise HarnessError("audio mode is out of range")
    if setup.blockflag[mode]:
        br.read(1)
        br.read(1)
    return mode


def _consume_residue(
    br: _BitReader,
    res: _Residue,
    books: Sequence[_Book],
    nz: Sequence[int],
    n: int,
) -> None:
    """Consume Vorbis I residue codebook words; do not reconstruct PCM."""
    nch = len(nz)
    nc = sum(1 for flag in nz if flag)
    if nc == 0:
        return
    if res.rtype == 2:
        vch = 1
        end = min(res.end, n * nch)
    else:
        vch = nc
        end = min(res.end, n)
    if end <= res.begin:
        return
    if res.psz < 1:
        raise HarnessError("residue partition size is 0")
    np = (end - res.begin) // res.psz
    if np == 0:
        return
    if res.cbook < 0 or res.cbook >= len(books):
        raise HarnessError("residue classbook is out of range")
    classbook = books[res.cbook]
    pv = classbook.dim
    if pv < 1:
        raise HarnessError("residue classbook dimension is 0")
    width = np + pv
    cl = [[0] * width for _ in range(vch)]
    for pass_i in range(8):
        pc = 0
        while pc < np:
            if pass_i == 0:
                for ch in range(vch):
                    cw = _bk_get(br, classbook)
                    tmp = cw
                    for k in range(pv, 0, -1):
                        cl[ch][pc + k - 1] = tmp % res.ncl
                        tmp //= res.ncl
                    if tmp:
                        raise HarnessError(
                            "residue classword exceeds its partitions"
                        )
            for _part in range(pv):
                if pc >= np:
                    break
                for ch in range(vch):
                    cls = cl[ch][pc]
                    if cls < 0 or cls >= res.ncl:
                        raise HarnessError("residue class is out of range")
                    bn = res.books[cls][pass_i]
                    if bn < 0:
                        continue
                    if bn >= len(books):
                        raise HarnessError("residue book is out of range")
                    book = books[bn]
                    if book.dim < 1:
                        raise HarnessError("residue book dimension is 0")
                    if res.psz % book.dim:
                        raise HarnessError(
                            "residue partition size is not a multiple of book dimension"
                        )
                    for _ in range(res.psz // book.dim):
                        _bk_get(br, book)
                pc += 1


def _used_bits_audio(packet: bytes, setup: _Setup) -> int:
    """Vorbis I used-bit walk: mode, optional window flags, floor, residue."""
    if setup.bs0 < 64 or setup.bs1 < setup.bs0:
        raise HarnessError("Vorbis identification block sizes are missing")
    br = _BitReader(packet)
    mode = _audio_preamble(br, setup)
    mapping = setup.mdmap[mode]
    n = (setup.bs1 if setup.blockflag[mode] else setup.bs0) // 2
    books = setup.books
    nz = [0] * setup.channels
    for ch in range(setup.channels):
        sub = setup.mux[mapping][ch] if len(setup.floor_of_sub[mapping]) > 1 else 0
        floor_no = setup.floor_of_sub[mapping][sub]
        floor = setup.floors[floor_no]
        used, _y_vals, _classes = _decode_floor1(br, floor, books)
        nz[ch] = 1 if used else 0
    for mag, ang in zip(setup.mag[mapping], setup.ang[mapping]):
        if mag >= setup.channels or ang >= setup.channels:
            raise HarnessError("coupling channel is out of range")
        if nz[mag] or nz[ang]:
            nz[mag] = nz[ang] = 1
    nsub = len(setup.res_of_sub[mapping])
    for sub_i in range(nsub):
        packed: list[int] = []
        for ch in range(setup.channels):
            mux = setup.mux[mapping][ch] if nsub > 1 else 0
            if mux == sub_i:
                packed.append(nz[ch])
        if not packed:
            continue
        res_no = setup.res_of_sub[mapping][sub_i]
        if res_no < 0 or res_no >= len(setup.residues):
            raise HarnessError("submap residue is out of range")
        _consume_residue(br, setup.residues[res_no], books, packed, n)
    return br.pos


def _unused_trailing_zero_bytes(packet: bytes, used_bits: int) -> int:
    """Count whole unused zero bytes after the last coded symbol.

    Leftover bits in the last used byte must be zero (a legal packet ending).
    Extra whole bytes after that byte must also be zero.
    """
    if used_bits < 0:
        raise HarnessError("used-bit walk returned a negative position")
    used_bytes = (used_bits + 7) // 8
    if used_bytes > len(packet):
        raise HarnessError("used-bit walk walked past the packet")
    leftover = used_bytes * 8 - used_bits
    if leftover and used_bytes:
        last = packet[used_bytes - 1]
        start = used_bits & 7
        mask = 0
        for i in range(start, 8):
            mask |= 1 << i
        if last & mask:
            raise HarnessError(
                "nonzero bits remain after the last coded symbol "
                "(not a legal unused-zero packet ending)"
            )
    tail = packet[used_bytes:]
    if any(byte != 0 for byte in tail):
        raise HarnessError("nonzero trailing bytes after the coded payload")
    return len(tail)


def interior_audio_packet(data: bytes) -> bytes:
    """Return the interior complete audio packet used for packet-boundary mutants."""
    _page_i, _pkt_i, packet = _find_interior_audio(data)
    return packet


def canonical_interior_byte_length(data: bytes) -> int:
    """Byte length of the explicit canonical encoding of the interior packet.

    That length is the used-bit walk (mode, floor, residue) rounded up to
    a whole byte. Unused trailing zeros after that walk are not included.
    A walk that fails raises; it is not reported as length zero.
    """
    setup, _packets = _load_setup(data)
    _page_i, _pkt_i, packet = _find_interior_audio(data)
    used_bits = _used_bits_audio(packet, setup)
    if used_bits < 1:
        raise HarnessError("interior audio packet encodes no bits")
    return (used_bits + 7) // 8


def _audio_symbol_key(packet: bytes, setup: _Setup, *, zero_fill: bool) -> tuple:
    """Codebook symbols of one audio packet.

    ``zero_fill`` supplies zeros past the packet so a tail of canonical
    zero bits can be omitted. The strict reader raises if the packet ends
    inside a field. Either failure is a harness error, not an empty key.
    """
    global _bk_get
    reader = _ImplicitZeroReader(packet) if zero_fill else _BitReader(packet)
    mode = _audio_preamble(reader, setup)
    mapping = setup.mdmap[mode]
    n = (setup.bs1 if setup.blockflag[mode] else setup.bs0) // 2
    books = setup.books
    floors: list[tuple] = []
    nz = [0] * setup.channels
    for ch in range(setup.channels):
        sub = setup.mux[mapping][ch] if len(setup.floor_of_sub[mapping]) > 1 else 0
        floor_no = setup.floor_of_sub[mapping][sub]
        used, y_vals, classes = _decode_floor1(reader, setup.floors[floor_no], books)
        floors.append((used, tuple(y_vals), tuple(classes)))
        nz[ch] = 1 if used else 0
    for mag, ang in zip(setup.mag[mapping], setup.ang[mapping]):
        if mag >= setup.channels or ang >= setup.channels:
            raise HarnessError("coupling channel is out of range")
        if nz[mag] or nz[ang]:
            nz[mag] = nz[ang] = 1
    residue: list[int] = []
    original_get = _bk_get

    def _record(br: _BitReader, book: _Book) -> int:
        entry = original_get(br, book)
        residue.append(entry)
        return entry

    _bk_get = _record
    try:
        nsub = len(setup.res_of_sub[mapping])
        for sub_i in range(nsub):
            packed: list[int] = []
            for ch in range(setup.channels):
                mux = setup.mux[mapping][ch] if nsub > 1 else 0
                if mux == sub_i:
                    packed.append(nz[ch])
            if not packed:
                continue
            res_no = setup.res_of_sub[mapping][sub_i]
            if res_no < 0 or res_no >= len(setup.residues):
                raise HarnessError("submap residue is out of range")
            _consume_residue(reader, setup.residues[res_no], books, packed, n)
    finally:
        _bk_get = original_get
    return (mode, tuple(floors), tuple(residue))


def interior_audio_symbol_key(data: bytes) -> tuple:
    """Strict symbol key of the interior audio packet. A short packet raises."""
    setup, _packets = _load_setup(data)
    _page_i, _pkt_i, packet = _find_interior_audio(data)
    return _audio_symbol_key(packet, setup, zero_fill=False)


def interior_audio_symbol_key_implicit_zeros(data: bytes) -> tuple:
    """Symbol key of the interior packet, reading missing tail bits as zero."""
    setup, _packets = _load_setup(data)
    _page_i, _pkt_i, packet = _find_interior_audio(data)
    return _audio_symbol_key(packet, setup, zero_fill=True)


def with_shorter_than_canonical_interior_packet(data: bytes) -> bytes:
    """Replace one interior audio packet with a shorter encoding of its symbols.

    The canonical encoding is the used-bit walk through mode, floor, and
    residue, in whole bytes. Unused zero bytes after that walk are padding,
    not a shorter encoding. A prefix that drops a nonzero residue suffix
    drops symbols. This keeps only a runtime-chosen shorter prefix of the
    canonical bytes whose omitted tail is entirely zero, and it checks that
    reading the missing bits as zero recovers the same symbols. If no such
    tail exists, this raises.
    """
    setup, _packets = _load_setup(data)
    page_i, pkt_i, packet = _find_interior_audio(data)
    used_bits = _used_bits_audio(packet, setup)
    canon = (used_bits + 7) // 8
    if canon < 1 or canon > len(packet):
        raise HarnessError(
            "canonical encoding does not fit the interior audio packet"
        )
    body = packet[:canon]
    zero_suffix = 0
    for byte in reversed(body):
        if byte != 0:
            break
        zero_suffix += 1
    if zero_suffix < 1:
        raise HarnessError(
            "interior audio packet has no trailing zero byte inside its "
            "canonical encoding"
        )
    drop = 1 + secrets.randbelow(zero_suffix)
    shortened = body[: canon - drop]
    if len(shortened) >= canon:
        raise HarnessError("shortened packet is not below the canonical length")
    if not shortened or (shortened[0] & 1):
        raise HarnessError("shortened packet is not a Vorbis audio packet")
    strict = _audio_symbol_key(packet, setup, zero_fill=False)
    filled = _audio_symbol_key(shortened, setup, zero_fill=True)
    if strict != filled:
        raise HarnessError(
            "shorter packet does not encode the same Vorbis symbols"
        )
    try:
        explicit = _audio_symbol_key(shortened, setup, zero_fill=False)
    except HarnessError:
        explicit = None
    if explicit == strict:
        raise HarnessError(
            "shorter packet still holds an explicit canonical encoding"
        )
    return _replace_page_packet(data, page_i, pkt_i, shortened)


def _subclass_index_tuple(classword: int, bits: int, dim: int) -> tuple[int, ...]:
    """Subclass indices stored in one Floor1 classword. No subclasses is empty."""
    if bits <= 0:
        return ()
    mask = (1 << bits) - 1
    return tuple((classword >> (k * bits)) & mask for k in range(dim))


def _packet_floor_subclass_choices(
    packet: bytes, setup: _Setup
) -> tuple[tuple[int, ...], ...]:
    """Subclass-index tuples for every subclassed partition of one audio packet."""
    br = _BitReader(packet)
    mode = _audio_preamble(br, setup)
    mapping = setup.mdmap[mode]
    books = setup.books
    choices: list[tuple[int, ...]] = []
    for ch in range(setup.channels):
        sub = setup.mux[mapping][ch] if len(setup.floor_of_sub[mapping]) > 1 else 0
        floor_no = setup.floor_of_sub[mapping][sub]
        floor = setup.floors[floor_no]
        used, _y_vals, classes = _decode_floor1(br, floor, books)
        if not used:
            continue
        for part in range(floor.parts):
            cls = floor.pcls[part]
            bits = floor.csub[cls]
            if bits == 0:
                continue
            if part >= len(classes):
                raise HarnessError("floor classword list is short")
            choices.append(_subclass_index_tuple(classes[part], bits, floor.cdim[cls]))
    if not choices:
        raise HarnessError("audio packet has no floor subclass choice")
    return tuple(choices)


def interior_floor_subclass_choices(data: bytes) -> tuple[tuple[int, ...], ...]:
    """Subclass choices of the interior audio packet. Absence raises."""
    setup, _packets = _load_setup(data)
    _page_i, _pkt_i, packet = _find_interior_audio(data)
    return _packet_floor_subclass_choices(packet, setup)


def with_alternative_floor1_subclass(data: bytes) -> bytes:
    """Rewrite one interior Floor1 classword to a different subclass.

    Another codebook entry that keeps the same subclass indices is not an
    alternative subclass. If no in-range subclass change decodes back to a
    different subclass-index tuple, this raises.
    """
    setup, _packets = _load_setup(data)
    page_i, pkt_i, packet = _find_interior_audio(data)
    original_choices = _packet_floor_subclass_choices(packet, setup)
    br = _BitReader(packet)
    mode = _audio_preamble(br, setup)
    mapping = setup.mdmap[mode]
    books = setup.books
    recorded: list[tuple[int, int, list[int], list[int], int, int]] = []
    candidates: list[tuple[int, int, int]] = []
    for ch in range(setup.channels):
        sub = setup.mux[mapping][ch] if len(setup.floor_of_sub[mapping]) > 1 else 0
        floor_no = setup.floor_of_sub[mapping][sub]
        floor = setup.floors[floor_no]
        start = br.pos
        used, y_vals, classes = _decode_floor1(br, floor, books)
        end = br.pos
        recorded.append((used or 0, floor_no, y_vals, classes, start, end))
        if not used:
            continue
        post = 2
        for part in range(floor.parts):
            cls = floor.pcls[part]
            dim = floor.cdim[cls]
            bits = floor.csub[cls]
            classword = classes[part]
            if bits == 0:
                post += dim
                continue
            master = books[floor.cbook[cls]]
            mask = (1 << (bits * dim)) - 1
            current_idx = _subclass_index_tuple(classword, bits, dim)
            for k in range(dim):
                current = (classword >> (k * bits)) & ((1 << bits) - 1)
                y_val = y_vals[post + k]
                for sub_i in range(1 << bits):
                    if sub_i == current:
                        continue
                    if not _subclass_encodes(floor, books, cls, sub_i, y_val):
                        continue
                    new_low = 0
                    ok = True
                    for k2 in range(dim):
                        idx = sub_i if k2 == k else (
                            (classword >> (k2 * bits)) & ((1 << bits) - 1)
                        )
                        new_low |= idx << (k2 * bits)
                        if not _subclass_encodes(
                            floor, books, cls, idx, y_vals[post + k2]
                        ):
                            ok = False
                            break
                    if not ok:
                        continue
                    if _subclass_index_tuple(new_low, bits, dim) == current_idx:
                        continue
                    for entry, length in enumerate(master.lengths):
                        if (
                            length
                            and (entry & mask) == new_low
                            and _subclass_index_tuple(entry, bits, dim) != current_idx
                        ):
                            candidates.append((ch, part, entry))
                            break
            post += dim
    viable: list[bytes] = []
    for channel, part, new_word in candidates:
        used, floor_no, y_vals, classes, start, end = recorded[channel]
        trial = list(classes)
        trial[part] = new_word
        bw = _BitWriter()
        try:
            bw.extend_from(packet, 0, start)
            _encode_floor1(bw, setup.floors[floor_no], books, used, y_vals, trial)
            bw.extend_from(packet, end, len(packet) * 8)
            rebuilt = bw.to_bytes()
        except HarnessError:
            continue
        if rebuilt == packet:
            continue
        try:
            got = _packet_floor_subclass_choices(rebuilt, setup)
        except HarnessError:
            continue
        if got != original_choices:
            viable.append(rebuilt)
    if not viable:
        raise HarnessError(
            "walker cannot prove an alternative valid Floor1 subclass "
            "on an interior classword of this stream"
        )
    return _replace_page_packet(data, page_i, pkt_i, secrets.choice(viable))


def _overwrite_bits(buf: bytearray, bitpos: int, nbits: int, value: int) -> None:
    for i in range(nbits):
        byte_i = (bitpos + i) >> 3
        shift = (bitpos + i) & 7
        if byte_i >= len(buf):
            raise HarnessError("bit overwrite walked off the packet")
        bit = (value >> i) & 1
        buf[byte_i] = (buf[byte_i] & ~(1 << shift)) | (bit << shift)


def _rewrite_setup_bits(
    data: bytes, mutator: Callable[[_Setup, bytearray], None]
) -> bytes:
    pages = parse_ogg_pages(data)
    packets = complete_packets(data)
    channels = _parse_ident_channels(packets[0])
    for page_i, page in enumerate(pages):
        if page.continued:
            continue
        chunks = page_packet_bytes(page)
        for pkt_i, chunk in enumerate(chunks):
            continuing = page.tail and pkt_i == len(chunks) - 1
            if continuing:
                continue
            if not chunk.startswith(VORBIS_SETUP):
                continue
            setup = parse_vorbis_setup(chunk, channels)
            buf = bytearray(chunk)
            mutator(setup, buf)
            return _replace_page_packet(data, page_i, pkt_i, bytes(buf))
    raise HarnessError("no complete Vorbis setup packet to mutate")


def _locate_setup_packet(data: bytes) -> tuple[int, int, bytes]:
    pages = parse_ogg_pages(data)
    for page_i, page in enumerate(pages):
        if page.continued:
            continue
        chunks = page_packet_bytes(page)
        for pkt_i, chunk in enumerate(chunks):
            if page.tail and pkt_i == len(chunks) - 1:
                continue
            if chunk.startswith(VORBIS_SETUP):
                return page_i, pkt_i, chunk
    raise HarnessError("no complete Vorbis setup packet to mutate")


def _skip_codebooks_and_time(br: _BitReader) -> int:
    if bytes([br.read(8) for _ in range(7)]) != VORBIS_SETUP:
        raise HarnessError("packet is not a Vorbis setup header")
    nbooks = br.read(8) + 1
    for _ in range(nbooks):
        _parse_book(br)
    ntime = br.read(6) + 1
    for _ in range(ntime):
        if br.read(16) != 0:
            raise HarnessError("nonzero Vorbis time-domain type")
    return nbooks


def _consume_floor1_body(br: _BitReader) -> None:
    """Consume one Floor1 configuration after its 16-bit type field."""
    parts = br.read(5)
    pcls = [br.read(4) for _ in range(parts)]
    nclass = (max(pcls) + 1) if pcls else 0
    cdim: list[int] = []
    for _ in range(nclass):
        cdim.append(br.read(3) + 1)
        subclasses = br.read(2)
        if subclasses:
            br.read(8)
        for _j in range(1 << subclasses):
            br.read(8)
    br.read(2)
    rangebits = br.read(4)
    for i in range(parts):
        for _ in range(cdim[pcls[i]]):
            br.read(rangebits)


def _bitpos_after_floor1(packet: bytes) -> int:
    br = _BitReader(packet)
    _skip_codebooks_and_time(br)
    nfloors = br.read(6) + 1
    if nfloors < 1:
        raise HarnessError("setup names no floors")
    for _ in range(nfloors):
        ftype = br.read(16)
        if ftype != 1:
            raise HarnessError(f"floor walk expected Floor1, got type {ftype}")
        _consume_floor1_body(br)
    return br.pos


def _require_setup_tail(br: _BitReader, channels: int) -> None:
    """Consume residues, mappings, and modes. Framing other than 1 raises."""
    nres = br.read(6) + 1
    for _ in range(nres):
        br.read(16)
        br.read(24)
        br.read(24)
        br.read(24)
        ncl = br.read(6) + 1
        br.read(8)
        cascade = []
        for _cls in range(ncl):
            low = br.read(3)
            if br.read(1):
                low |= br.read(5) << 3
            cascade.append(low)
        for i in range(ncl):
            for j in range(8):
                if cascade[i] & (1 << j):
                    br.read(8)
    nmaps = br.read(6) + 1
    for _ in range(nmaps):
        if br.read(16) != 0:
            raise HarnessError("nonzero Vorbis mapping type")
        flag = br.read(1)
        submaps = (br.read(4) + 1) if flag else 1
        coup = br.read(1)
        steps = (br.read(8) + 1) if coup else 0
        ilog_ch = _ilog(channels - 1) if channels > 1 else 0
        for _step in range(steps):
            br.read(ilog_ch)
            br.read(ilog_ch)
        br.read(2)
        if submaps > 1:
            for _ch in range(channels):
                br.read(4)
        for _sub in range(submaps):
            br.read(8)
            br.read(8)
            br.read(8)
    nmodes = br.read(6) + 1
    for _ in range(nmodes):
        br.read(1)
        br.read(16)
        br.read(16)
        br.read(8)
    if br.read(1) != 1:
        raise HarnessError("Vorbis setup framing bit is not set")


def _read_floor0_header(
    br: _BitReader, nbooks: int
) -> tuple[int, int, int, tuple[int, ...]]:
    """Read one Vorbis I floor 0 header after the 16-bit type field.

    Field widths are the Vorbis I floor 0 header: 8-bit order, 16-bit
    rate, 16-bit bark map size, 6-bit amplitude bits, 8-bit amplitude
    offset, 4-bit book count minus one, then that many 8-bit book indices.
    A zero order, rate, or bark map size, or a book index outside the
    codebook list, is not that header.
    """
    order = br.read(8)
    rate = br.read(16)
    bark = br.read(16)
    br.read(6)
    br.read(8)
    nlist = br.read(4) + 1
    books = tuple(br.read(8) for _ in range(nlist))
    if order < 1 or rate < 1 or bark < 1:
        raise HarnessError(
            "floor type 0 header is not a Vorbis I floor "
            f"(order={order}, rate={rate}, bark_map_size={bark})"
        )
    for book in books:
        if book >= nbooks:
            raise HarnessError(
                f"floor type 0 book {book} is outside the {nbooks} codebooks"
            )
    return order, rate, bark, books


def _write_floor0_header(bw: _BitWriter, *, rate: int, nbooks: int) -> None:
    """Write a floor type 0 configuration, including the 16-bit type field."""
    if rate < 1:
        raise HarnessError(f"floor type 0 rate {rate} is not positive")
    if nbooks < 1:
        raise HarnessError("floor type 0 header has no codebook to name")
    bw.write(16, 0)
    bw.write(8, 1)
    bw.write(16, rate)
    bw.write(16, 256)
    bw.write(6, 8)
    bw.write(8, 0)
    bw.write(4, 0)
    bw.write(8, 0)


def _ident_sample_rate(packet: bytes) -> int:
    br = _BitReader(packet)
    br.read(8 * 7)
    if br.read(32) != 0:
        raise HarnessError("Vorbis identification version is not 0")
    br.read(8)
    rate = br.read(32)
    if rate < 1:
        raise HarnessError(f"Vorbis sample rate {rate} is not positive")
    return rate


def floor0_headers(
    data: bytes,
) -> list[tuple[int, int, int, tuple[int, ...]]]:
    """Every floor of *data*, read as a Vorbis I floor 0 header.

    Returns ``(order, rate, bark_map_size, book_indices)`` per floor.
    Raises when a floor is not type 0, a header field is not the Vorbis I
    floor 0 header, or the setup does not still frame after those headers.
    """
    packets = complete_packets(data)
    if not packets:
        raise HarnessError("Vorbis file has no packets")
    channels = _parse_ident_channels(packets[0])
    setup_pkt = next((p for p in packets if p.startswith(VORBIS_SETUP)), None)
    if setup_pkt is None:
        raise HarnessError("Vorbis file has no setup header")
    br = _BitReader(setup_pkt)
    nbooks = _skip_codebooks_and_time(br)
    nfloors = br.read(6) + 1
    headers: list[tuple[int, int, int, tuple[int, ...]]] = []
    for _ in range(nfloors):
        ftype = br.read(16)
        if ftype != 0:
            raise HarnessError(
                f"setup floor type {ftype} is not a Vorbis I floor 0 header"
            )
        headers.append(_read_floor0_header(br, nbooks))
    if not headers:
        raise HarnessError("setup names no floors")
    _require_setup_tail(br, channels)
    return headers


def _replace_floors_with_type0(packet: bytes, *, rate: int, channels: int) -> bytes:
    br_check = _BitReader(packet)
    _skip_codebooks_and_time(br_check)
    nbooks_pos = br_check.pos
    probe = parse_vorbis_setup(packet, channels)
    if _bitpos_after_floor1(packet) != probe.residue_pos:
        raise HarnessError(
            "Floor1 walk does not end where the setup parser starts residues"
        )
    tail_reader = _BitReader(packet)
    tail_reader.pos = probe.residue_pos
    _require_setup_tail(tail_reader, channels)
    br = _BitReader(packet)
    nbooks = _skip_codebooks_and_time(br)
    if br.pos != nbooks_pos:
        raise HarnessError("codebook walk disagreed with itself")
    nfloors = br.read(6) + 1
    spans: list[tuple[int, int]] = []
    for _ in range(nfloors):
        start = br.pos
        ftype = br.read(16)
        if ftype != 1:
            raise HarnessError(f"fixture floor type {ftype} is not Floor1")
        _consume_floor1_body(br)
        spans.append((start, br.pos))
    if br.pos != probe.residue_pos:
        raise HarnessError("floor spans do not cover the Floor1 section")
    bw = _BitWriter()
    cursor = 0
    for start, end in spans:
        bw.extend_from(packet, cursor, start)
        _write_floor0_header(bw, rate=rate, nbooks=nbooks)
        cursor = end
    bw.extend_from(packet, cursor, len(packet) * 8)
    return bw.to_bytes()


def set_setup_floor_type(data: bytes, floor_type: int) -> bytes:
    """Return *data* with every floor rewritten as a Vorbis I floor 0 header.

    The type field and the header after it are both floor 0. A Floor1 body
    with only the type field changed is not that file. *floor_type* other
    than 0 is not a Vorbis I floor 0 header.
    """
    if floor_type != 0:
        raise HarnessError(
            f"floor type {floor_type} is not a Vorbis I floor 0 header"
        )
    packets = complete_packets(data)
    if not packets:
        raise HarnessError("Vorbis file has no packets")
    channels = _parse_ident_channels(packets[0])
    rate = _ident_sample_rate(packets[0])
    page_i, pkt_i, packet = _locate_setup_packet(data)
    new_packet = _replace_floors_with_type0(packet, rate=rate, channels=channels)
    rebuilt = _replace_page_packet(data, page_i, pkt_i, new_packet)
    headers = floor0_headers(rebuilt)
    if not headers:
        raise HarnessError("floor type 0 rebuild produced no floor header")
    return rebuilt


def first_type2_lookup(data: bytes) -> tuple[int, int, int, int]:
    """First lookup-type-2 codebook as Vorbis I defines the value vector.

    Returns ``(dimensions, entries, multiplicand_count, type1_count)``.
    The multiplicand count is one value per entry per dimension. Raises
    when no such book is present, when that count still equals the type-1
    ``lookup1_values`` length, or when reading that vector leaves a setup
    that does not frame.
    """
    packets = complete_packets(data)
    if not packets:
        raise HarnessError("Vorbis file has no packets")
    channels = _parse_ident_channels(packets[0])
    setup_pkt = next((p for p in packets if p.startswith(VORBIS_SETUP)), None)
    if setup_pkt is None:
        raise HarnessError("Vorbis file has no setup header")
    parsed = parse_vorbis_setup(setup_pkt, channels)
    for book in parsed.books:
        if book.look != 2:
            continue
        type1 = _lookup1_values(book.ent, book.dim)
        if book.nmult != book.ent * book.dim:
            raise HarnessError(
                "lookup type 2 multiplicand count "
                f"{book.nmult} is not one per entry per dimension "
                f"({book.ent} entries, {book.dim} dimensions)"
            )
        if book.nmult == type1:
            raise HarnessError(
                "lookup type 2 vector still has the type-1 length "
                f"{type1}"
            )
        return book.dim, book.ent, book.nmult, type1
    raise HarnessError("setup has no codebook lookup type 2")


def _replace_lookup_with_type2(packet: bytes) -> bytes:
    br = _BitReader(packet)
    _skip_codebooks_and_time(br)
    br = _BitReader(packet)
    if bytes([br.read(8) for _ in range(7)]) != VORBIS_SETUP:
        raise HarnessError("packet is not a Vorbis setup header")
    nbooks = br.read(8) + 1
    chosen: _Book | None = None
    for _ in range(nbooks):
        book = _parse_book(br)
        if (
            chosen is None
            and book.look == 1
            and book.nmult != book.ent * book.dim
        ):
            chosen = book
    if chosen is None:
        raise HarnessError(
            "no lookup-type-1 codebook whose type-2 multiplicand count differs"
        )
    src = _BitReader(packet)
    src.pos = chosen.mult_pos
    values = [src.read(chosen.value_bits) for _ in range(chosen.nmult)]
    if src.pos != chosen.mult_pos + chosen.nmult * chosen.value_bits:
        raise HarnessError("type-1 multiplicand walk did not consume its vector")
    extra = chosen.ent * chosen.dim - chosen.nmult
    if extra < 1:
        raise HarnessError(
            "type-2 multiplicand vector is not longer than the type-1 vector"
        )
    bw = _BitWriter()
    bw.extend_from(packet, 0, chosen.look_pos)
    bw.write(4, 2)
    bw.extend_from(packet, chosen.look_pos + 4, chosen.mult_pos)
    for value in values:
        bw.write(chosen.value_bits, value)
    for _ in range(extra):
        bw.write(chosen.value_bits, 0)
    bw.extend_from(packet, src.pos, len(packet) * 8)
    return bw.to_bytes()


def set_codebook_lookup_type(data: bytes, lookup_type: int) -> bytes:
    """Return *data* with one codebook rebuilt as Vorbis I lookup type 2.

    Lookup type 2 carries one multiplicand per entry per dimension. Changing
    only the 4-bit type field and leaving the type-1 vector is not that
    book. *lookup_type* other than 2 is not this vector.
    """
    if lookup_type != 2:
        raise HarnessError(
            f"lookup type {lookup_type} is not a Vorbis I lookup type 2 vector"
        )
    packets = complete_packets(data)
    if not packets:
        raise HarnessError("Vorbis file has no packets")
    channels = _parse_ident_channels(packets[0])
    page_i, pkt_i, packet = _locate_setup_packet(data)
    new_packet = _replace_lookup_with_type2(packet)
    if parse_vorbis_setup(new_packet, channels).residue_pos <= 0:
        raise HarnessError("lookup type 2 rebuild did not leave a framed setup")
    rebuilt = _replace_page_packet(data, page_i, pkt_i, new_packet)
    dim, ent, count, type1 = first_type2_lookup(rebuilt)
    if count != ent * dim or count == type1:
        raise HarnessError(
            "lookup type 2 rebuild did not write one multiplicand "
            "per entry per dimension"
        )
    return rebuilt


def _setup_packet_of(data: bytes) -> tuple[bytes, int]:
    packets = complete_packets(data)
    if not packets:
        raise HarnessError("Vorbis file has no packets")
    channels = _parse_ident_channels(packets[0])
    setup_pkt = next((p for p in packets if p.startswith(VORBIS_SETUP)), None)
    if setup_pkt is None:
        raise HarnessError("Vorbis file has no setup header")
    return setup_pkt, channels


def prove_floor_type_code_over_floor1(data: bytes) -> int:
    """Prove one floor type code is 0 and the body after it is still Floor1.

    Walking that body as Floor1 must end where the original Floor1 section
    ended, and the setup after it must still frame. Raises otherwise.
    Returns how many floors the setup names.
    """
    mutated, channels = _setup_packet_of(data)
    br = _BitReader(mutated)
    _skip_codebooks_and_time(br)
    nfloors = br.read(6) + 1
    if nfloors < 1:
        raise HarnessError("setup names no floors")
    ftype = br.read(16)
    if ftype != 0:
        raise HarnessError(
            f"floor type code is {ftype}, not 0 over a Floor1 body"
        )
    _consume_floor1_body(br)
    for i in range(1, nfloors):
        later = br.read(16)
        if later != 1:
            raise HarnessError(
                f"floor {i} type {later} is not Floor1 beside the type-0 code"
            )
        _consume_floor1_body(br)
    floor_end = br.pos
    _require_setup_tail(br, channels)
    restored = bytearray(mutated)
    probe = _BitReader(mutated)
    _skip_codebooks_and_time(probe)
    probe.read(6)
    _overwrite_bits(restored, probe.pos, 16, 1)
    restored_end = _bitpos_after_floor1(bytes(restored))
    if floor_end != restored_end:
        raise HarnessError(
            "Floor1 body after type code 0 does not end where Floor1 ends "
            f"({floor_end} vs {restored_end})"
        )
    return nfloors


def with_floor_type_code_over_floor1(data: bytes) -> bytes:
    """Return *data* with one floor type code set to 0 and the Floor1 body kept.

    Only the 16-bit type field changes. A Vorbis I floor 0 header is not
    this file. A parser that ignores the type field and reads Floor1 can
    still frame the setup.
    """
    page_i, pkt_i, packet = _locate_setup_packet(data)
    channels = _parse_ident_channels(complete_packets(data)[0])
    before = parse_vorbis_setup(packet, channels)
    if not before.floor_type_pos:
        raise HarnessError("setup names no floors")
    buf = bytearray(packet)
    _overwrite_bits(buf, before.floor_type_pos[0], 16, 0)
    rebuilt = _replace_page_packet(data, page_i, pkt_i, bytes(buf))
    nfloors = prove_floor_type_code_over_floor1(rebuilt)
    if nfloors < 1:
        raise HarnessError("floor type code 0 over Floor1 named no floors")
    return rebuilt


def prove_lookup_type_code_over_type1(data: bytes) -> tuple[int, int, int, int]:
    """Prove one lookup type code is 2 and the vector is still the type-1 length.

    Returns ``(dimensions, entries, type1_count, type2_count)``. Reading the
    stored vector as type 1 must leave a setup that still frames. The type-1
    length must differ from one value per entry per dimension. Raises
    otherwise.
    """
    mutated, channels = _setup_packet_of(data)
    br = _BitReader(mutated)
    if bytes([br.read(8) for _ in range(7)]) != VORBIS_SETUP:
        raise HarnessError("packet is not a Vorbis setup header")
    nbooks = br.read(8) + 1
    chosen: tuple[int, int, int, int] | None = None
    for _ in range(nbooks):
        sync = br.read(24)
        if sync != BOOK_SYNC:
            raise HarnessError(f"codebook sync is not 0x564342 (got {sync:#x})")
        dim = br.read(16)
        ent = br.read(24)
        if dim == 0:
            raise HarnessError("codebook dimension is 0")
        if br.read(1):
            got = 0
            br.read(5)
            while got < ent:
                run = br.read(_ilog(ent - got))
                if got + run > ent:
                    raise HarnessError("ordered codebook run overruns the book")
                got += run
        else:
            if br.read(1):
                for _i in range(ent):
                    if br.read(1):
                        br.read(5)
            else:
                for _i in range(ent):
                    br.read(5)
        look = br.read(4)
        if look == 0:
            continue
        br.read(32)
        br.read(32)
        value_bits = br.read(4) + 1
        br.read(1)
        type1 = _lookup1_values(ent, dim)
        type2 = ent * dim
        if look == 2 and chosen is None:
            if type1 < 1:
                raise HarnessError("type-1 multiplicand length is empty")
            if type1 == type2:
                raise HarnessError(
                    "lookup type code 2 still has a type-2-length vector "
                    f"({type2})"
                )
            for _v in range(type1):
                br.read(value_bits)
            chosen = (dim, ent, type1, type2)
            continue
        if look == 1:
            nmult = type1
        elif look == 2:
            nmult = type2
        else:
            raise HarnessError(f"codebook lookup type {look} is not 0–2")
        for _v in range(nmult):
            br.read(value_bits)
    if chosen is None:
        raise HarnessError("setup has no lookup type code 2 over a type-1 vector")
    _require_setup_tail_from_books_done(br, channels, mutated)
    return chosen


def _require_setup_tail_from_books_done(
    br: _BitReader, channels: int, packet: bytes
) -> None:
    """Finish a setup whose codebooks were already consumed. Framing must hold."""
    ntime = br.read(6) + 1
    for _ in range(ntime):
        if br.read(16) != 0:
            raise HarnessError("nonzero Vorbis time-domain type")
    nfloors = br.read(6) + 1
    for _ in range(nfloors):
        ftype = br.read(16)
        if ftype != 1:
            raise HarnessError(
                f"lookup-type probe expected Floor1 after the books, got {ftype}"
            )
        _consume_floor1_body(br)
    _require_setup_tail(br, channels)
    if br.pos > len(packet) * 8:
        raise HarnessError("type-1 vector walk ran past the setup packet")


def with_lookup_type_code_over_type1(data: bytes) -> bytes:
    """Return *data* with one lookup type code set to 2 and the type-1 vector kept.

    Only the 4-bit type field changes. One multiplicand per entry per
    dimension is not this book. A parser that treats any nonzero lookup
    type as type 1 and reads the type-1 vector can still frame the setup.
    """
    page_i, pkt_i, packet = _locate_setup_packet(data)
    channels = _parse_ident_channels(complete_packets(data)[0])
    before = parse_vorbis_setup(packet, channels)
    chosen = next(
        (
            book
            for book in before.books
            if book.look == 1
            and book.nmult != book.ent * book.dim
            and book.nmult == _lookup1_values(book.ent, book.dim)
        ),
        None,
    )
    if chosen is None:
        raise HarnessError(
            "no lookup-type-1 codebook whose type-1 vector is shorter "
            "than one value per entry per dimension"
        )
    buf = bytearray(packet)
    _overwrite_bits(buf, chosen.look_pos, 4, 2)
    rebuilt = _replace_page_packet(data, page_i, pkt_i, bytes(buf))
    dim, ent, type1, type2 = prove_lookup_type_code_over_type1(rebuilt)
    if type1 != chosen.nmult or dim != chosen.dim or ent != chosen.ent:
        raise HarnessError(
            "lookup type code 2 did not keep the type-1 multiplicand vector"
        )
    if type1 == type2:
        raise HarnessError("lookup type code 2 vector grew to the type-2 length")
    return rebuilt


def replace_vorbis_comment(
    data: bytes,
    *,
    vendor: bytes,
    fields: Sequence[bytes],
) -> bytes:
    """Replace the comment packet using Vorbis I layout; re-page the stream."""
    packets = complete_packets(data)
    pages = parse_ogg_pages(data)
    serial = pages[0].serial
    idx = next(
        (i for i, pkt in enumerate(packets) if pkt.startswith(VORBIS_COMMENT)),
        None,
    )
    if idx is None:
        raise HarnessError("Vorbis file has no comment packet")
    original = packets[idx]
    payload = bytearray(VORBIS_COMMENT)
    payload += len(vendor).to_bytes(4, "little")
    payload += vendor
    payload += len(fields).to_bytes(4, "little")
    for field in fields:
        payload += len(field).to_bytes(4, "little")
        payload += field
    # Framing bit: 1, remaining bits of that byte unused zeros.
    payload.append(0x01)
    new_comment = bytes(payload)
    if len(new_comment) <= len(original):
        raise HarnessError("constructed comment packet is not strictly larger")
    packets[idx] = new_comment
    out = bytearray()
    seq = 0
    for i, pkt in enumerate(packets):
        header_type = 0
        granule = 0
        if i == 0:
            header_type |= 0x02
        if i == len(packets) - 1:
            header_type |= 0x04
            granule = pages[-1].granule
        elif i >= 3:
            granule = pages[-1].granule
        out += emit_ogg_page(
            header_type=header_type,
            granule=granule,
            serial=serial,
            sequence=seq,
            packets=[pkt],
        )
        seq += 1
    rebuilt = bytes(out)
    if len(complete_packets(rebuilt)[idx]) <= len(original):
        raise HarnessError("re-paged comment is not larger than the original")
    return rebuilt


def neither_ident_page(*, serial: int | None = None) -> bytes:
    """BOS page whose first complete packet is Ogg but neither ident nor OpusHead."""
    if serial is None:
        serial = int.from_bytes(secrets.token_bytes(4), "little")
    packet = b"\x01" + b"xxxxxx" + secrets.token_bytes(8)
    if is_vorbis_ident(packet) or is_opus_head(packet):
        raise HarnessError("neither-ident packet collided with a named header")
    return emit_ogg_page(
        header_type=0x02,
        granule=0,
        serial=serial,
        sequence=0,
        packets=[packet],
    )


# ---------------------------------------------------------------------------
# Workspace placement and product observation
# ---------------------------------------------------------------------------


_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
_FLOOR_SOURCES = (
    _FIXTURE_DIR / "vorbis_floor_a.ogg",
    _FIXTURE_DIR / "vorbis_floor_b.ogg",
)


def place_floor_source(ws: Workspace) -> str:
    """Copy a suite-owned Vorbis file that carries an alternative Floor1 subclass.

    The short public Vorbis pair used by A has no provable alternative
    classword. These suite fixtures are the source stream; the test still
    applies a runtime-chosen subclass so the bytes under compress are not
    a memorized dump.
    """
    path = secrets.choice(_FLOOR_SOURCES)
    if path.is_file():
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise HarnessError(f"cannot read suite fixture {path}: {exc}") from exc
    else:
        raise HarnessError(f"suite fixture missing: {path}")
    if not data:
        raise HarnessError(f"suite fixture is empty: {path}")
    rel = unique_name("floor-src") + ".ogg"
    ws.write(rel, data)
    return rel


def place_vorbis_without_ogg_suffix(ws: Workspace, which: str) -> str:
    data = _vorbis_bytes(which)
    rel = unique_name(f"vorbis-{which}-nosuf")
    if rel.endswith(".ogg") or rel.endswith(".opus"):
        raise HarnessError(f"unnamed Vorbis path still has a codec suffix: {rel}")
    ws.write(rel, data)
    return rel


def place_opus_without_opus_suffix(ws: Workspace) -> str:
    data = _opus_bytes()
    rel = unique_name("opus-nosuf")
    if rel.endswith(".ogg") or rel.endswith(".opus"):
        raise HarnessError(f"unnamed Opus path still has a codec suffix: {rel}")
    ws.write(rel, data)
    return rel


def feed_fifo(path: os.PathLike[str] | str, data: bytes) -> threading.Thread:
    """Serve *data* to a FIFO across multiple opens (peek, then a later open).

    The product reads a non-seekable input twice: a short peek, then a full
    open. A single write-and-close leaves the second open blocked. This
    feeder loops until :func:`stop_fifo_feeder` sets the stop event.
    """
    stop = threading.Event()

    def _run() -> None:
        while not stop.is_set():
            fd = None
            try:
                fd = os.open(path, os.O_WRONLY)
            except OSError:
                if stop.is_set():
                    return
                continue
            try:
                view = memoryview(data)
                while view and not stop.is_set():
                    try:
                        n = os.write(fd, view)
                    except BrokenPipeError:
                        break
                    if n <= 0:
                        break
                    view = view[n:]
            finally:
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass

    thread = threading.Thread(target=_run, daemon=True)
    thread._stop_event = stop  # type: ignore[attr-defined]
    thread.start()
    return thread


def stop_fifo_feeder(
    thread: threading.Thread, path: os.PathLike[str] | str
) -> None:
    """Unblock a looping FIFO writer after the product has exited."""
    stop = getattr(thread, "_stop_event", None)
    if isinstance(stop, threading.Event):
        stop.set()
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        fd = None
    else:
        try:
            os.close(fd)
        except OSError:
            pass
    thread.join(timeout=1.0)


def roundtrip(
    ws: Workspace,
    src: str,
    *,
    effort: str | None = None,
    no_mmap: bool = False,
    dest: str | None = None,
    recovered: str | None = None,
) -> str:
    """Compress then expand. Require exit 0 both times, dest≠src, recovered==src."""
    dest = dest or unique_name("arc")
    recovered = recovered or unique_name("out")
    enc_args: list[str] = []
    if effort is not None:
        enc_args.append(effort)
    if no_mmap:
        enc_args.append("--no-mmap")
    enc_args.extend(["e", src, dest])
    enc = run_product(ws, enc_args)
    require_ok(enc)
    if not ws.path_is_file(dest):
        raise HarnessError(f"compress did not write destination {dest}")
    src_bytes = ws.read_bytes(src)
    dest_bytes = ws.read_bytes(dest)
    assert not stored_copy(dest_bytes, src_bytes), (
        "compress destination bytes carry the source verbatim (copy stub)"
    )
    dec_args: list[str] = []
    if no_mmap:
        dec_args.append("--no-mmap")
    dec_args.extend(["d", dest, recovered])
    dec = run_product(ws, dec_args)
    require_ok(dec)
    if not files_identical(ws.resolve(src), ws.resolve(recovered)):
        raise AssertionError("expand did not restore the original bytes")
    print(
        f"[F02] round-trip src={len(src_bytes)} dest={len(dest_bytes)} "
        f"effort={effort!r} no_mmap={no_mmap}",
        flush=True,
    )
    return dest


def _stderr_without_paths(result: RunResult, paths: Sequence[str]) -> str:
    """Caller-typed paths removed from stderr. A decode failure raises."""
    text = result.stderr_text
    if not isinstance(text, str):
        raise HarnessError(f"stderr text expected str, got {type(text)!r}")
    stripped = text
    for path in paths:
        if not isinstance(path, str) or not path:
            raise HarnessError(f"input path expected a non-empty str, got {path!r}")
        name = Path(path).name
        if not name:
            raise HarnessError(f"input path has no final component: {path!r}")
        stripped = stripped.replace(path, " ")
        if name != path:
            stripped = stripped.replace(name, " ")
    return stripped


def require_refusal_distinct_from(
    result: RunResult,
    path: str,
    other: RunResult,
    other_path: str,
    *extra_paths: str,
) -> None:
    """Assert two construct refusals stay distinct after caller paths are gone.

    The two inputs differ, so echoing a path is not the distinction. What
    remains must still differ. Wording of either diagnostic stays open.
    A decode failure raises.
    """
    paths = (path, other_path, *extra_paths)
    left = _stderr_without_paths(result, paths).casefold()
    right = _stderr_without_paths(other, paths).casefold()
    assert left != right, (
        "refusal diagnostic is not distinguishable from the other construct "
        f"refusal after the input paths are removed; stderr={result.stderr_text!r} "
        f"other={other.stderr_text!r}"
    )


def require_refusal_names_input(result: RunResult, path: str) -> None:
    """Assert the refusal diagnostic identifies the caller-typed input path.

    The wording of the diagnostic is open. The path the caller passed, or
    its final component, is the identification. A decode failure raises.
    """
    if not isinstance(path, str) or not path:
        raise HarnessError(f"offending input path expected a non-empty str, got {path!r}")
    text = result.stderr_text
    name = Path(path).name
    if not name:
        raise HarnessError(f"offending input path has no final component: {path!r}")
    assert path in text or name in text, (
        f"refusal diagnostic does not identify the offending input {path!r}; "
        f"stderr={text!r}"
    )


def require_no_usable_compress_dest(ws: Workspace, dest: str) -> None:
    """Dest is absent, or expand of dest does not exit 0. Lookup failures raise."""
    found = ws.read_bytes_if_present(dest)
    expand_ok = False
    if found is None:
        print(f"[F02] compress dest {dest!r} is absent", flush=True)
    else:
        recovered = unique_name("probe-out")
        result = run_product(ws, ["d", dest, recovered])
        expand_ok = result.returncode == 0
        print(
            f"[F02] compress dest {dest!r} present but expand "
            f"exit={result.returncode}",
            flush=True,
        )
    assert not expand_ok, (
        "compress refusal left a destination that expand accepts (exit 0)"
    )


def require_no_usable_expand_dest(ws: Workspace, dest: str, ogg_input: bytes) -> None:
    """Dest is absent, or dest bytes are not the raw Ogg input."""
    found = ws.read_bytes_if_present(dest)
    restored = found is not None and found == ogg_input
    if found is None:
        print(f"[F02] expand dest {dest!r} is absent", flush=True)
    else:
        print(
            f"[F02] expand dest {dest!r} present ({len(found)} bytes) "
            f"restored={restored}",
            flush=True,
        )
    assert not restored, (
        "expand of a raw Ogg file delivered the Ogg bytes as a restore"
    )


__all__ = (
    "append_trailing_pages",
    "complete_packets",
    "emit_ogg_page",
    "emit_ogg_pages",
    "feed_fifo",
    "first_complete_packet",
    "first_type2_lookup",
    "floor0_headers",
    "canonical_interior_byte_length",
    "interior_audio_packet",
    "interior_audio_symbol_key",
    "interior_audio_symbol_key_implicit_zeros",
    "interior_floor_subclass_choices",
    "is_opus_head",
    "is_vorbis_ident",
    "neither_ident_page",
    "ogg_crc32",
    "ogg_crc_page",
    "parse_ogg_pages",
    "parse_vorbis_setup",
    "place_floor_source",
    "place_opus_without_opus_suffix",
    "place_vorbis_without_ogg_suffix",
    "replace_vorbis_comment",
    "require_no_usable_compress_dest",
    "require_refusal_distinct_from",
    "require_refusal_names_input",
    "require_no_usable_expand_dest",
    "rewrite_first_page_packet",
    "roundtrip",
    "prove_floor_type_code_over_floor1",
    "prove_lookup_type_code_over_type1",
    "set_codebook_lookup_type",
    "set_setup_floor_type",
    "with_floor_type_code_over_floor1",
    "with_lookup_type_code_over_type1",
    "stop_fifo_feeder",
    "with_alternative_floor1_subclass",
    "with_interior_unused_zero_padding",
    "with_shortened_unused_zero_padding",
    "with_shorter_than_canonical_interior_packet",
)
