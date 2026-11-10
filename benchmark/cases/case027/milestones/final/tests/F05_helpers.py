# feature: F05
"""Helpers for the binary-file and text-encoding suite.

Shell forms only: the binary note line and the binary-extension list the
PRD enumerates.  No expected search result lives here.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from _helpers import RunResult
from F01_helpers import out_lines

__all__ = [
    "BINARY_NOTE",
    "binary_note",
    "BINARY_EXTENSIONS",
    "first_nul",
    "notes_in",
]

#: One stdout line standing for a matching binary file:
#: Optional path prefix, fixed marker, then a declared numeric field:
#: ``offset <integer>``, ``offset: <integer>``, or ``byte <integer>``.
#: Surrounding prose is free; the integer is the first NUL byte offset.
BINARY_NOTE = re.compile(r'^(?:(?P<path>.+): )?binary file matches\b')
BINARY_OFFSET = re.compile(r'\b(?:offset:?|byte) (?P<offset>[0-9]+)\b')

#: The known binary extensions, exactly as FP-05.05 lists them.
BINARY_EXTENSIONS = (
    "png jpg jpeg gif bmp ico webp tiff tif psd mp3 mp4 avi mkv mov wav flac ogg wma aac "
    "m4a webm zip tar gz bz2 xz zst 7z rar lz4 lzma cab exe dll so dylib obj o a lib pdb "
    "wasm class jar pyc pyo beam pdf doc docx xls xlsx ppt pptx ttf otf woff woff2 eot bin "
    "dat db sqlite sqlite3"
).split()


def binary_note(line: str) -> Optional[Tuple[Optional[str], int]]:
    """Return ``(path or None, offset)`` when ``line`` is a binary note, else ``None``."""
    m = BINARY_NOTE.match(line)
    if m is None:
        return None
    offsets = list(BINARY_OFFSET.finditer(line, m.end()))
    assert len(offsets) == 1, f"binary note must carry one offset field: {line!r}"
    return m.group("path"), int(offsets[0].group("offset"))


def notes_in(result: RunResult) -> List[Tuple[Optional[str], int]]:
    """Return every binary note on stdout, in order."""
    return [n for n in (binary_note(l) for l in out_lines(result)) if n is not None]


def first_nul(data: bytes) -> int:
    """Byte offset of the first NUL in ``data`` (the test's own computation)."""
    i = data.find(b"\0")
    if i < 0:
        raise ValueError("fixture has no NUL byte")
    return i

