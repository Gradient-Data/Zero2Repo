# feature: F05
"""Feature-local helpers for exact-reproduction refusals.

These helpers build defective Ogg inputs (RFC 3533 pages, Vorbis I setup
fields) and observe compress/expand destinations. They are not a
substitute public entry.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from F01_helpers import place_vorbis, require_ok, require_refusal, run_product, unique_name
from F02_helpers import (
    BOOK_SYNC,
    VORBIS_SETUP,
    _BitReader,
    _BitWriter,
    _audio_preamble,
    _bk_get,
    _ilog,
    _load_setup,
    _overwrite_bits,
    _parse_book,
    _rewrite_setup_bits,
    complete_packets,
    emit_ogg_page,
    is_opus_head,
    is_vorbis_ident,
    ogg_crc_page,
    parse_ogg_pages,
    replace_vorbis_comment,
    require_no_usable_compress_dest,
    require_no_usable_expand_dest,
)
from F03_helpers import place_opus_classified, replace_opus_tags
from _harness import HarnessError, RunResult, Workspace, stored_copy

_OGG_CAPTURE = b"OggS"
_SPAN_TAKE = 255
_GRANULE_NONE = (1 << 64) - 1


def _setup_packet(data: bytes) -> bytes:
    packets = complete_packets(data)
    pkt = next((p for p in packets if p.startswith(VORBIS_SETUP)), None)
    if pkt is None:
        raise HarnessError("Vorbis file has no setup header")
    return pkt


def _skip_floor1(br: _BitReader) -> None:
    parts = br.read(5)
    pcls = [br.read(4) for _ in range(parts)]
    nclass = (max(pcls) + 1) if pcls else 0
    cdim = [0] * 16
    for i in range(nclass):
        cdim[i] = br.read(3) + 1
        subclasses = br.read(2)
        if subclasses:
            br.read(8)
        for _ in range(1 << subclasses):
            br.read(8)
    br.read(2)
    rangebits = br.read(4)
    for i in range(parts):
        for _ in range(cdim[pcls[i]]):
            br.read(rangebits)


def _read_lookup_field(br: _BitReader) -> int:
    """Read a codebook through its 4-bit lookup type; do not consume VQ data."""
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
        sparse = br.read(1)
        if not sparse:
            for _ in range(ent):
                br.read(5)
        else:
            for _ in range(ent):
                if br.read(1):
                    br.read(5)
    return br.read(4)


def _book_bit_span(
    setup_pkt: bytes, book_index: int
) -> tuple[int, int, int, int, int]:
    br = _BitReader(setup_pkt)
    hdr = bytes(br.read(8) for _ in range(7))
    if hdr != VORBIS_SETUP:
        raise HarnessError("packet is not a Vorbis setup header")
    nbooks = br.read(8) + 1
    if not 0 <= book_index < nbooks:
        raise HarnessError(
            f"codebook index {book_index} out of range ({nbooks} books)"
        )
    for i in range(nbooks):
        start = br.pos
        book = _parse_book(br)
        if i == book_index:
            return start, br.pos, book.dim, book.ent, book.look_pos
    raise HarnessError(f"codebook index {book_index} was not reached")


def _ensure_spannable(data: bytes) -> bytes:
    packets = complete_packets(data)
    if any(i >= 1 and len(pkt) >= _SPAN_TAKE + 1 for i, pkt in enumerate(packets)):
        return data
    pad = (b"SPAN" + data[:16]) * 20
    if not packets:
        raise HarnessError("bitstream has no complete packets to span")
    if is_vorbis_ident(packets[0]):
        return replace_vorbis_comment(
            data, vendor=b"span-host", fields=(b"PAD=" + pad,)
        )
    if is_opus_head(packets[0]):
        return replace_opus_tags(
            data, vendor=b"span-host", fields=(b"PAD=" + pad,)
        )
    raise HarnessError("cannot enlarge a non-Vorbis/Opus stream for spanning")


def _emit_spanned_stream(
    data: bytes, *, continued: bool
) -> bytes:
    host = _ensure_spannable(data)
    packets = complete_packets(host)
    pages = parse_ogg_pages(host)
    serial = pages[0].serial
    last_granule = pages[-1].granule
    idx = next(
        (i for i, pkt in enumerate(packets) if i >= 1 and len(pkt) >= _SPAN_TAKE + 1),
        None,
    )
    if idx is None:
        raise HarnessError("no packet after ident is long enough to span pages")
    first_chunk = packets[idx][:_SPAN_TAKE]
    rest = packets[idx][_SPAN_TAKE:]
    if not rest:
        raise HarnessError("packet split left no remainder")
    out = bytearray()
    seq = 0
    n = len(packets)
    for i, pkt in enumerate(packets):
        bos = i == 0
        eos = i + 1 == n
        if i != idx:
            ht = (0x02 if bos else 0) | (0x04 if eos else 0)
            gran = last_granule if (eos or i >= 3) else 0
            out += emit_ogg_page(
                header_type=ht,
                granule=gran,
                serial=serial,
                sequence=seq,
                packets=[pkt],
            )
            seq += 1
            continue
        ht1 = 0x02 if bos else 0
        out += emit_ogg_page(
            header_type=ht1,
            granule=_GRANULE_NONE,
            serial=serial,
            sequence=seq,
            packets=[first_chunk],
            tail=True,
        )
        seq += 1
        ht2 = (0x01 if continued else 0) | (0x04 if eos else 0)
        gran2 = last_granule if (eos or i >= 3) else 0
        out += emit_ogg_page(
            header_type=ht2,
            granule=gran2,
            serial=serial,
            sequence=seq,
            packets=[rest],
        )
        seq += 1
    rebuilt = bytes(out)
    pages = parse_ogg_pages(rebuilt)
    found = False
    for i in range(len(pages) - 1):
        if pages[i].tail and bool(pages[i + 1].continued) == continued:
            found = True
            break
    if not found:
        raise HarnessError(
            "constructed span does not have the requested continuation mark"
        )
    if continued:
        recovered = complete_packets(rebuilt)
        if recovered != list(packets):
            raise HarnessError("marked span did not reconstruct the original packets")
    return rebuilt


def corrupt_stored_page_checksum(data: bytes, page_index: int) -> bytes:
    """Flip one bit of the stored RFC 3533 checksum field of one page."""
    pages = parse_ogg_pages(data)
    if not 0 <= page_index < len(pages):
        raise HarnessError(
            f"page index {page_index} out of range ({len(pages)} pages)"
        )
    page = pages[page_index]
    raw = bytearray(page.raw)
    if len(raw) < 26:
        raise HarnessError("Ogg page shorter than the checksum field")
    stored = int.from_bytes(raw[22:26], "little")
    expect = ogg_crc_page(bytes(raw))
    if stored != expect:
        raise HarnessError(
            f"page {page_index} already mismatches RFC 3533 "
            f"(stored={stored} expect={expect})"
        )
    bit = secrets.randbelow(32)
    raw[22 + (bit // 8)] ^= 1 << (bit % 8)
    new_stored = int.from_bytes(raw[22:26], "little")
    new_expect = ogg_crc_page(bytes(raw))
    if new_stored == new_expect:
        raise HarnessError("checksum-field flip did not create an RFC 3533 mismatch")
    print(
        f"[F05] checksum mismatch page={page_index} bit={bit} "
        f"stored={new_stored} rfc3533={new_expect}",
        flush=True,
    )
    return data[: page.offset] + bytes(raw) + data[page.offset + page.size :]


def with_page_after_eos(data: bytes) -> bytes:
    """Append a non-BOS page after a finished end-of-stream page of the same serial."""
    pages = parse_ogg_pages(data)
    last = pages[-1]
    body = data
    if not (last.header_type & 0x04):
        raw = bytearray(last.raw)
        raw[5] = raw[5] | 0x04
        crc = ogg_crc_page(bytes(raw))
        raw[22:26] = int(crc).to_bytes(4, "little")
        body = data[: last.offset] + bytes(raw) + data[last.offset + last.size :]
        last_seq = last.sequence
        last_serial = last.serial
        last_granule = last.granule
    else:
        last_seq = last.sequence
        last_serial = last.serial
        last_granule = last.granule
    extra = emit_ogg_page(
        header_type=0,
        granule=last_granule,
        serial=last_serial,
        sequence=last_seq + 1,
        packets=[b"\x00" + secrets.token_bytes(8)],
    )
    if extra[5] & 0x02:
        raise HarnessError("extra page must not be beginning-of-stream")
    if extra[5] & 0x01:
        raise HarnessError("extra page must not be marked continued")
    return body + extra


def with_marked_packet_span(data: bytes) -> bytes:
    """Split one complete packet across two pages; set the continuation mark."""
    return _emit_spanned_stream(data, continued=True)


def with_unmarked_packet_span(data: bytes) -> bytes:
    """Same split as the marked span, with the continuation mark cleared."""
    return _emit_spanned_stream(data, continued=False)


def prove_page_after_eos(data: bytes) -> None:
    """Prove last page follows a finished same-serial EOS page and is not BOS."""
    pages = parse_ogg_pages(data)
    if len(pages) < 2:
        raise HarnessError("page-after-eos construction has fewer than two pages")
    last = pages[-1]
    prev = pages[-2]
    if last.serial != prev.serial:
        raise HarnessError(
            f"last page serial {last.serial} differs from previous {prev.serial}"
        )
    if not (prev.header_type & 0x04):
        raise HarnessError("page before the extra page is not end-of-stream")
    if last.header_type & 0x02:
        raise HarnessError("extra page is beginning-of-stream")
    print(
        f"[F05] proved page-after-eos serial={last.serial} "
        f"prev_seq={prev.sequence} last_seq={last.sequence}",
        flush=True,
    )


def _prove_packet_span(data: bytes, *, continued: bool) -> None:
    pages = parse_ogg_pages(data)
    found = False
    for i in range(len(pages) - 1):
        if pages[i].tail and bool(pages[i + 1].continued) == continued:
            found = True
            break
    label = "marked" if continued else "unmarked"
    if not found:
        raise HarnessError(
            f"{label} span does not have a tail page followed by a "
            f"{'continued' if continued else 'non-continued'} page"
        )
    print(f"[F05] proved {label} packet span pages={len(pages)}", flush=True)


def prove_marked_span(data: bytes) -> None:
    """Prove a packet is split onto a following page marked as a continuation."""
    _prove_packet_span(data, continued=True)


def prove_unmarked_span(data: bytes) -> None:
    """Prove a packet is split onto a following page not marked as a continuation."""
    _prove_packet_span(data, continued=False)


def with_trailing_non_page(data: bytes, junk: bytes) -> bytes:
    """Append bytes that are not an Ogg capture after the last page."""
    if not isinstance(junk, (bytes, bytearray)):
        raise HarnessError(f"trailing junk expected bytes, got {type(junk)!r}")
    if len(junk) < 16:
        raise HarnessError("trailing non-page payload is shorter than 16 bytes")
    if bytes(junk).startswith(_OGG_CAPTURE):
        raise HarnessError("trailing payload starts with an Ogg capture")
    parse_ogg_pages(data)
    return data + bytes(junk)


def with_sparse_empty_book(data: bytes, book_index: int) -> bytes:
    """Rewrite codebook *book_index* to Vorbis I sparse with every used bit 0."""

    def mutate(setup, buf: bytearray) -> None:
        nbooks = len(setup.books)
        if not 0 <= book_index < nbooks:
            raise HarnessError(
                f"codebook index {book_index} out of range ({nbooks} books)"
            )
        start, end, dim, ent, look_pos = _book_bit_span(bytes(buf), book_index)
        bw = _BitWriter()
        bw.extend_from(bytes(buf), 0, start)
        bw.write(24, BOOK_SYNC)
        bw.write(16, dim)
        bw.write(24, ent)
        bw.write(1, 0)
        bw.write(1, 1)
        for _ in range(ent):
            bw.write(1, 0)
        bw.extend_from(bytes(buf), look_pos, end)
        bw.extend_from(bytes(buf), end, len(buf) * 8)
        rebuilt = bw.to_bytes()
        buf.clear()
        buf.extend(rebuilt)

    return _rewrite_setup_bits(data, mutate)


def set_floor_type_at(data: bytes, slot: int, floor_type: int) -> bytes:
    """Overwrite the Vorbis I floor-type field at *slot* (16 bits)."""

    def mutate(setup, buf: bytearray) -> None:
        n = len(setup.floor_type_pos)
        if not 0 <= slot < n:
            raise HarnessError(f"floor slot {slot} out of range ({n} floors)")
        _overwrite_bits(buf, setup.floor_type_pos[slot], 16, floor_type)

    return _rewrite_setup_bits(data, mutate)


def set_lookup_type_at(data: bytes, slot: int, lookup_type: int) -> bytes:
    """Overwrite the Vorbis I codebook lookup-type field at *slot* (4 bits)."""

    def mutate(setup, buf: bytearray) -> None:
        n = len(setup.books)
        if not 0 <= slot < n:
            raise HarnessError(f"codebook slot {slot} out of range ({n} books)")
        _overwrite_bits(buf, setup.books[slot].look_pos, 4, lookup_type)

    return _rewrite_setup_bits(data, mutate)


def prove_floor_type(data: bytes, slot: int, expected: int) -> None:
    """Prove the Vorbis I floor-type field at *slot* equals *expected*. Raises."""
    setup_pkt = _setup_packet(data)
    br = _BitReader(setup_pkt)
    hdr = bytes(br.read(8) for _ in range(7))
    if hdr != VORBIS_SETUP:
        raise HarnessError("packet is not a Vorbis setup header")
    nbooks = br.read(8) + 1
    for _ in range(nbooks):
        _parse_book(br)
    ntime = br.read(6) + 1
    for _ in range(ntime):
        if br.read(16) != 0:
            raise HarnessError("nonzero Vorbis time-domain type")
    nfloors = br.read(6) + 1
    if not 0 <= slot < nfloors:
        raise HarnessError(f"floor slot {slot} out of range ({nfloors} floors)")
    for i in range(slot):
        ftype = br.read(16)
        if ftype != 1:
            raise HarnessError(
                f"cannot skip floor {i} of type {ftype} to reach slot {slot}"
            )
        _skip_floor1(br)
    got = br.read(16)
    if got != expected:
        raise HarnessError(f"floor slot {slot} type is {got}, not {expected}")
    print(f"[F05] proved floor slot={slot} type={got}", flush=True)


def prove_lookup_type(data: bytes, slot: int, expected: int) -> None:
    """Prove the Vorbis I codebook lookup-type field at *slot*. Raises."""
    setup_pkt = _setup_packet(data)
    br = _BitReader(setup_pkt)
    hdr = bytes(br.read(8) for _ in range(7))
    if hdr != VORBIS_SETUP:
        raise HarnessError("packet is not a Vorbis setup header")
    nbooks = br.read(8) + 1
    if not 0 <= slot < nbooks:
        raise HarnessError(f"codebook slot {slot} out of range ({nbooks} books)")
    for _ in range(slot):
        _parse_book(br)
    got = _read_lookup_field(br)
    if got != expected:
        raise HarnessError(
            f"codebook slot {slot} lookup type is {got}, not {expected}"
        )
    print(f"[F05] proved codebook slot={slot} lookup={got}", flush=True)


def prove_sparse_empty_book(data: bytes, slot: int) -> None:
    """Prove codebook *slot* is sparse with every used bit 0. Raises."""
    setup_pkt = _setup_packet(data)
    br = _BitReader(setup_pkt)
    hdr = bytes(br.read(8) for _ in range(7))
    if hdr != VORBIS_SETUP:
        raise HarnessError("packet is not a Vorbis setup header")
    nbooks = br.read(8) + 1
    if not 0 <= slot < nbooks:
        raise HarnessError(f"codebook slot {slot} out of range ({nbooks} books)")
    for i in range(slot):
        _parse_book(br)
    sync = br.read(24)
    if sync != BOOK_SYNC:
        raise HarnessError(f"codebook sync is not 0x564342 (got {sync:#x})")
    dim = br.read(16)
    ent = br.read(24)
    if dim == 0:
        raise HarnessError("codebook dimension is 0")
    if br.read(1):
        raise HarnessError(f"codebook slot {slot} is ordered, not sparse")
    if not br.read(1):
        raise HarnessError(f"codebook slot {slot} is not marked sparse")
    for i in range(ent):
        if br.read(1):
            raise HarnessError(f"codebook slot {slot} entry {i} is still used")
    look = br.read(4)
    _load_setup(data)
    print(
        f"[F05] proved sparse empty book slot={slot} entries={ent} lookup={look}",
        flush=True,
    )


def floor_slot(data: bytes) -> int:
    """Return a floor index: non-first when more than one floor exists."""
    setup, _packets = _load_setup(data)
    n = len(setup.floor_type_pos)
    if n < 1:
        raise HarnessError("setup has no floor list")
    if n == 1:
        print("[F05] host has a single floor slot", flush=True)
        return 0
    slot = secrets.choice(range(1, n))
    print(f"[F05] chose non-first floor slot={slot} of {n}", flush=True)
    return slot


def lookup_slot(data: bytes) -> int:
    """Return a codebook with lookup type 1; non-first when several exist."""
    setup, _packets = _load_setup(data)
    indices = [i for i, book in enumerate(setup.books) if book.look == 1]
    if not indices:
        raise HarnessError("no codebook with lookup type 1")
    if len(indices) == 1:
        print(f"[F05] host has a single lookup-1 codebook slot={indices[0]}", flush=True)
        return indices[0]
    slot = secrets.choice(indices[1:])
    print(
        f"[F05] chose non-first lookup-1 slot={slot} from {indices}",
        flush=True,
    )
    return slot


def _used_codebook_indices(data: bytes) -> list[int]:
    """Codebook indices from which this file's audio packets read a word."""
    setup, packets = _load_setup(data)
    nbooks = len(setup.books)
    found: list[int] = []
    seen: set[int] = set()

    def add(index: int) -> None:
        if not isinstance(index, int):
            raise HarnessError(f"codebook index is not an integer: {index!r}")
        if index < 0:
            return
        if index >= nbooks:
            raise HarnessError(
                f"audio names codebook {index} but only {nbooks} books exist"
            )
        if index in seen:
            return
        seen.add(index)
        found.append(index)

    for pkt in packets:
        if not pkt or (pkt[0] & 1):
            continue
        br = _BitReader(pkt)
        mode = _audio_preamble(br, setup)
        mapping = setup.mdmap[mode]
        n = (setup.bs1 if setup.blockflag[mode] else setup.bs0) // 2
        books = setup.books
        nz = [0] * setup.channels
        for ch in range(setup.channels):
            sub = (
                setup.mux[mapping][ch]
                if len(setup.floor_of_sub[mapping]) > 1
                else 0
            )
            floor = setup.floors[setup.floor_of_sub[mapping][sub]]
            used = br.read(1)
            if not used:
                continue
            pbits = _ilog(floor.quant - 1)
            br.read(pbits)
            br.read(pbits)
            for i in range(floor.parts):
                cls = floor.pcls[i]
                dim = floor.cdim[cls]
                bits = floor.csub[cls]
                classword = 0
                if bits:
                    add(floor.cbook[cls])
                    classword = _bk_get(br, books[floor.cbook[cls]])
                shifted = classword
                for _ in range(dim):
                    subc = shifted & ((1 << bits) - 1) if bits else 0
                    shifted >>= bits
                    sub_book = floor.csb[cls][subc]
                    if sub_book >= 0:
                        add(sub_book)
                        _bk_get(br, books[sub_book])
            nz[ch] = 1
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
            res = setup.residues[setup.res_of_sub[mapping][sub_i]]
            nc = sum(1 for flag in packed if flag)
            if nc == 0:
                continue
            if res.rtype == 2:
                vch = 1
                end = min(res.end, n * len(packed))
            else:
                vch = nc
                end = min(res.end, n)
            if end <= res.begin or res.psz < 1:
                continue
            np = (end - res.begin) // res.psz
            if np == 0:
                continue
            add(res.cbook)
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
                    for _part in range(pv):
                        if pc >= np:
                            break
                        for ch in range(vch):
                            cls = cl[ch][pc]
                            bn = res.books[cls][pass_i]
                            if bn < 0:
                                continue
                            add(bn)
                            book = books[bn]
                            if book.dim < 1:
                                raise HarnessError("residue book dimension is 0")
                            for _ in range(res.psz // book.dim):
                                _bk_get(br, book)
                        pc += 1

    if not found:
        raise HarnessError("audio packets use no codebook words")
    return found


def sparse_book_slot(data: bytes) -> int:
    """Return a codebook this file's audio actually reads; non-first if several."""
    indices = _used_codebook_indices(data)
    if len(indices) == 1:
        print(
            f"[F05] host audio uses a single codebook slot={indices[0]}",
            flush=True,
        )
        return indices[0]
    slot = secrets.choice(indices[1:])
    print(
        f"[F05] chose non-first audio-used codebook slot={slot} from {indices}",
        flush=True,
    )
    return slot


# Interface Contract, archive file: the byte at offset 9 is the format
# generation, an unsigned 8-bit integer from 1 through 254.
GENERATION_OFFSET = 9
GENERATION_MIN = 1
GENERATION_MAX = 254


def archive_generation(archive: bytes) -> int:
    """Read the format generation byte the Contract places in every archive."""
    if not isinstance(archive, (bytes, bytearray)):
        raise HarnessError(f"archive expected bytes, got {type(archive)!r}")
    assert len(archive) > GENERATION_OFFSET, (
        f"archive of {len(archive)} bytes has no generation byte at offset "
        f"{GENERATION_OFFSET}"
    )
    value = archive[GENERATION_OFFSET]
    assert GENERATION_MIN <= value <= GENERATION_MAX, (
        f"archive generation {value} at offset {GENERATION_OFFSET} is not "
        f"in {GENERATION_MIN}..{GENERATION_MAX}"
    )
    return value


def written_generation(
    ws: Workspace, src_a: str, bytes_a: bytes, bytes_b: bytes
) -> int:
    """The generation every archive carries, across inputs, codecs, efforts.

    Reads the stated generation byte of the two given archives and of
    archives of *src_a* at effort 9 and of an input of the other codec at
    efforts 1 and 9; all must carry the same value.
    """
    first = complete_packets(bytes(ws.read_bytes(src_a)))[0]
    if is_opus_head(first):
        other = place_vorbis(ws, "a")
    else:
        other = place_opus_classified(ws, "hybrid")
    archives = [bytes(bytes_a), bytes(bytes_b)]
    for src, effort in ((src_a, "-9"), (other, "-1"), (other, "-9")):
        dest = unique_name("gen-across")
        result = run_product(ws, [effort, "e", src, dest])
        require_ok(result)
        archives.append(ws.read_bytes(dest))
    values = [archive_generation(a) for a in archives]
    print(f"[F05] archive generations={values}", flush=True)
    assert len(set(values)) == 1, (
        "every archive this product writes carries the same generation "
        f"value; got {values}"
    )
    return values[0]


def with_generation_value(archive: bytes, value: int) -> bytes:
    """Rewrite only the stated generation byte of *archive* to *value*."""
    if not isinstance(archive, (bytes, bytearray)):
        raise HarnessError(f"archive expected bytes, got {type(archive)!r}")
    if not 0 <= value <= 255:
        raise HarnessError(f"generation value {value} does not fit one byte")
    if len(archive) <= GENERATION_OFFSET:
        raise HarnessError("archive has no generation byte")
    out = bytearray(archive)
    out[GENERATION_OFFSET] = value
    return bytes(out)


def foreign_generation_values(written: int) -> tuple[int, int]:
    """A runtime older (lower) and newer (higher) one-byte generation."""
    older = secrets.choice(range(0, written))
    newer = secrets.choice(range(written + 1, 256))
    if not older < written < newer:
        raise HarnessError(f"relative order failed: {older} < {written} < {newer}")
    return older, newer


def stderr_names_input(text: str, path: str) -> None:
    """Assert *text* still names the caller-typed input path. Type errors raise."""
    if not isinstance(text, str):
        raise HarnessError(f"stderr_names_input expected str, got {type(text)!r}")
    if not isinstance(path, str):
        raise HarnessError(f"input path expected str, got {type(path)!r}")
    name = Path(path).name
    present = path in text or (name and name in text)
    assert present, (
        f"stderr does not identify the offending input {path!r}; stderr={text!r}"
    )


def live_compress(ws: Workspace, src: str) -> str:
    """Compress *src* at effort 1. Require exit 0, dest present, dest≠src."""
    dest = unique_name("live-arc")
    result = run_product(ws, ["-1", "e", src, dest])
    require_ok(result)
    if not ws.path_is_file(dest):
        raise HarnessError(f"compress did not write a regular file at {dest}")
    src_bytes = ws.read_bytes(src)
    dest_bytes = ws.read_bytes(dest)
    assert not stored_copy(dest_bytes, src_bytes), (
        "compress destination bytes carry the source verbatim (copy stub)"
    )
    print(
        f"[F05] live compress src={src!r} dest={dest!r} "
        f"src_len={len(src_bytes)} dest_len={len(dest_bytes)}",
        flush=True,
    )
    return dest


def refuse_compress(ws: Workspace, src: str, dest: str) -> RunResult:
    """Compress *src* and require a refusal with no usable archive dest."""
    result = run_product(ws, ["e", src, dest])
    require_refusal(result)
    assert result.returncode == 1, (
        f"compress refusal exited {result.returncode}; stderr={result.stderr!r}"
    )
    assert result.stderr, (
        f"compress refusal left stderr empty; stdout={result.stdout!r}"
    )
    require_no_usable_compress_dest(ws, dest)
    print(
        f"[F05] compress refusal src={src!r} dest={dest!r} "
        f"stderr_len={len(result.stderr)}",
        flush=True,
    )
    return result


def refuse_expand(
    ws: Workspace, src: str, dest: str, original: bytes
) -> RunResult:
    """Expand *src* and require a refusal that does not deliver *original*."""
    result = run_product(ws, ["d", src, dest])
    require_refusal(result)
    assert result.returncode == 1, (
        f"expand refusal exited {result.returncode}; stderr={result.stderr!r}"
    )
    assert result.stderr, (
        f"expand refusal left stderr empty; stdout={result.stdout!r}"
    )
    require_no_usable_expand_dest(ws, dest, original)
    print(
        f"[F05] expand refusal src={src!r} dest={dest!r} "
        f"stderr_len={len(result.stderr)}",
        flush=True,
    )
    return result


def place_bytes_without_codec_suffix(
    ws: Workspace, data: bytes, prefix: str
) -> str:
    """Write *data* to a unique path that does not end in ``.ogg`` or ``.opus``."""
    rel = unique_name(prefix)
    if rel.endswith(".ogg") or rel.endswith(".opus"):
        raise HarnessError(f"path still has a codec suffix: {rel}")
    ws.write(rel, data)
    return rel


def truncation_lengths(n: int) -> tuple[int, ...]:
    """Runtime-derived distinct truncation lengths in ``[1, n)``. At least two."""
    if n < 3:
        raise HarnessError(f"archive length {n} is too short to derive two truncations")
    raw = (1, max(1, n // 4), max(1, n // 2), n - 1)
    pts = tuple(sorted({p for p in raw if 1 <= p < n}))
    if len(pts) < 2:
        raise HarnessError(f"could not derive two distinct truncation lengths from {n}")
    print(f"[F05] truncation lengths={pts} archive_len={n}", flush=True)
    return pts


def page_bytes_unchecked(data: bytes, page_index: int) -> bytes:
    """Return one Ogg page by capture walk. Does not require a matching checksum."""
    if not isinstance(data, (bytes, bytearray)):
        raise HarnessError(f"page walk expected bytes, got {type(data)!r}")
    offset = 0
    seen = 0
    n = len(data)
    while offset + 27 <= n:
        if data[offset : offset + 4] != _OGG_CAPTURE:
            raise HarnessError(f"missing OggS capture at {offset}")
        nseg = data[offset + 26]
        header_len = 27 + nseg
        if offset + header_len > n:
            raise HarnessError(f"truncated segment table at {offset}")
        body_len = sum(data[offset + 27 : offset + header_len])
        end = offset + header_len + body_len
        if end > n:
            raise HarnessError(f"truncated Ogg page body at {offset}")
        if seen == page_index:
            return bytes(data[offset:end])
        seen += 1
        offset = end
    raise HarnessError(f"page index {page_index} out of range ({seen} pages)")


def prove_checksum_mismatch(data: bytes, page_index: int) -> None:
    """Prove the stored checksum field is not the RFC 3533 value. Raises."""
    page = page_bytes_unchecked(data, page_index)
    stored = int.from_bytes(page[22:26], "little")
    expect = ogg_crc_page(page)
    if stored == expect:
        raise HarnessError(
            f"page {page_index} stored checksum still matches RFC 3533"
        )
    print(
        f"[F05] RFC 3533 mismatch page={page_index} stored={stored} expect={expect}",
        flush=True,
    )


def later_page_index(data: bytes) -> int:
    """Return a runtime-chosen index that is not the first page. Raises if none."""
    pages = parse_ogg_pages(data)
    if len(pages) < 2:
        raise HarnessError("host bitstream has no later page")
    index = secrets.choice(range(1, len(pages)))
    print(f"[F05] later page index={index} of {len(pages)}", flush=True)
    return index


def shared_prefix_len(left: bytes, right: bytes) -> int:
    """Byte length of the longest shared prefix. Type errors raise."""
    if not isinstance(left, (bytes, bytearray)):
        raise HarnessError(f"left expected bytes, got {type(left)!r}")
    if not isinstance(right, (bytes, bytearray)):
        raise HarnessError(f"right expected bytes, got {type(right)!r}")
    n = min(len(left), len(right))
    i = 0
    while i < n and left[i] == right[i]:
        i += 1
    return i


__all__ = (
    "GENERATION_OFFSET",
    "archive_generation",
    "corrupt_stored_page_checksum",
    "floor_slot",
    "foreign_generation_values",
    "later_page_index",
    "live_compress",
    "lookup_slot",
    "place_bytes_without_codec_suffix",
    "prove_checksum_mismatch",
    "prove_floor_type",
    "prove_lookup_type",
    "prove_marked_span",
    "prove_page_after_eos",
    "prove_sparse_empty_book",
    "prove_unmarked_span",
    "refuse_compress",
    "refuse_expand",
    "set_floor_type_at",
    "set_lookup_type_at",
    "shared_prefix_len",
    "sparse_book_slot",
    "stderr_names_input",
    "truncation_lengths",
    "with_generation_value",
    "with_marked_packet_span",
    "with_page_after_eos",
    "with_sparse_empty_book",
    "with_trailing_non_page",
    "with_unmarked_packet_span",
    "written_generation",
)
