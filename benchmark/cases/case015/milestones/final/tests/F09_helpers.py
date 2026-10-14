# feature: F09
"""Feature-local helpers for archive dump and Ogg page listing.

These helpers drive the public ``dump`` / ``pages`` verbs and read
standard output in the forms the Interface Contract states: the dump
``stage: <stage>`` and ``codec: <codec>`` lines, and one ``pages`` line
per page beginning ``page <index>`` and ending in ``ok`` or ``mismatch``.
"""

from __future__ import annotations

import re

from F01_helpers import require_ok, require_stdout_text, run_product, unique_name
from F02_helpers import (
    OGG_CAPTURE,
    OGG_HDRMIN,
    OggPage,
    ogg_crc_page,
    parse_ogg_pages,
)
from F04_helpers import (
    archive_bytes,
    compress_to,
    expand_to,
    require_lossless_archive,
)
from F05_helpers import corrupt_stored_page_checksum, prove_checksum_mismatch
from _harness import HarnessError, Workspace, stored_copy


def lossless_compress(ws: Workspace, src: str, dest: str, *effort_tokens: str) -> bytes:
    """Compress *src* to *dest*, expand, and require dest≠src and recovered==src."""
    src_bytes = ws.read_bytes(src)
    compress_to(ws, src, dest, *effort_tokens)
    dest_bytes = archive_bytes(ws, dest)
    recovered = unique_name("rec")
    expand_to(ws, dest, recovered)
    rec_bytes = ws.read_bytes(recovered)
    require_lossless_archive(dest_bytes, rec_bytes, src_bytes, what=dest)
    assert not stored_copy(dest_bytes, src_bytes), (
        f"{dest}: compress destination bytes carry the source verbatim (copy stub)"
    )
    assert rec_bytes == src_bytes, (
        f"{dest}: expand did not restore the original bytes"
    )
    return dest_bytes


def pages_stdout(ws: Workspace, path: str) -> str:
    """Run ``pages`` on *path*. Non-zero exit or empty stdout raises/asserts."""
    result = run_product(ws, ["pages", path])
    require_ok(result)
    text = require_stdout_text(result)
    assert result.returncode == 0, (
        f"pages expected exit 0, got {result.returncode}; "
        f"stderr={result.stderr!r} stdout={result.stdout!r}"
    )
    assert text, f"pages expected non-empty stdout; stderr={result.stderr!r}"
    return text


def reconstructed_from_parsed_header_and_body(page: OggPage) -> bytes:
    """RFC 3533 serialize of one page's parsed header fields and body."""
    if not isinstance(page, OggPage):
        raise HarnessError(
            f"page expected OggPage, got {type(page)!r}"
        )
    laces = bytes(page.laces)
    body = bytes(page.body)
    header_len = OGG_HDRMIN + len(laces)
    out = bytearray(header_len + len(body))
    out[0:4] = OGG_CAPTURE
    out[4] = 0
    out[5] = int(page.header_type) & 0xFF
    out[6:14] = int(page.granule).to_bytes(8, "little")
    out[14:18] = int(page.serial).to_bytes(4, "little")
    out[18:22] = int(page.sequence).to_bytes(4, "little")
    out[26] = len(laces)
    out[OGG_HDRMIN : header_len] = laces
    out[header_len:] = body
    crc = ogg_crc_page(bytes(out))
    out[22:26] = crc.to_bytes(4, "little")
    return bytes(out)


def require_every_page_reconstructs(data: bytes) -> None:
    """Every stored page equals reconstruction from its parsed header and body."""
    if not isinstance(data, (bytes, bytearray)):
        raise HarnessError(
            f"require_every_page_reconstructs expected bytes, got {type(data)!r}"
        )
    pages = parse_ogg_pages(bytes(data))
    for page in pages:
        rebuilt = reconstructed_from_parsed_header_and_body(page)
        if rebuilt != page.raw:
            raise HarnessError(
                f"page at {page.offset} does not reconstruct from parsed "
                "header and body"
            )


_PAGE_LINE = re.compile(r"^ *page (\d+)(?![0-9]).*?(?<![A-Za-z0-9_-])(ok|mismatch)\s*$")
_PAGE_START = re.compile(r"^ *page \d+(?![0-9])")


def page_statuses(text: str) -> list[tuple[int, str]]:
    """``(index, status)`` of every page line of ``pages`` stdout, in order.

    Status is ``"ok"`` for ``ok`` and ``"mismatch"`` for ``mismatch``. A line that starts like a page line but does not
    end in a stated status asserts.
    """
    if not isinstance(text, str):
        raise HarnessError(f"text expected str, got {type(text)!r}")
    out: list[tuple[int, str]] = []
    for line in text.splitlines():
        if not _PAGE_START.match(line):
            continue
        m = _PAGE_LINE.match(line)
        assert m, (
            "a pages line does not end in the reconstruction status "
            f"`ok` or `mismatch`: {line!r}"
        )
        out.append((int(m.group(1)), m.group(2)))
    return out


def require_page_listing(text: str, n_pages: int, mismatched: frozenset[int], *, what: str) -> None:
    """One line per page, indexes 0..n-1 in order, statuses as expected."""
    if isinstance(n_pages, bool) or not isinstance(n_pages, int) or n_pages < 1:
        raise HarnessError(f"n_pages expected a positive int, got {n_pages!r}")
    got = page_statuses(text)
    print(f"[F09] {what} pages={got!r}", flush=True)
    assert [i for i, _ in got] == list(range(n_pages)), (
        f"{what}: pages lists every page once, in order, as `page <index>` "
        f"lines; expected {n_pages} pages, got indexes {[i for i, _ in got]!r}"
    )
    for index, status in got:
        want = "mismatch" if index in mismatched else "ok"
        assert status == want, (
            f"{what}: page {index} reports {status!r}, expected {want!r} "
            "(reconstruction as RFC 3533 serialization of its parsed header "
            "and body, CRC computed with the checksum field zero)"
        )


def still_parseable_one_page_checksum_sibling(data: bytes) -> bytes:
    """Same-codec sibling that differs only by one page's stored RFC 3533 checksum.

    The stored checksum of page 0 is flipped so it no longer matches the
    CRC computed with that field treated as zero. The file stays a
    parseable Ogg sequence with the same page count. Type errors raise.
    A lookup that cannot classify the pages raises; it does not return
    the original bytes.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise HarnessError(
            "still_parseable_one_page_checksum_sibling expected bytes, "
            f"got {type(data)!r}"
        )
    host = bytes(data)
    out = corrupt_stored_page_checksum(host, 0)
    prove_checksum_mismatch(out, 0)
    return out
