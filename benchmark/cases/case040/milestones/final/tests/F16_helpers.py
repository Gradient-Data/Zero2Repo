# feature: F16
"""Caller-supplied glyphs, independent of the built-in font artwork."""
from _helpers import velnora


class MosaicFont(velnora.Font):
    """Two deliberately unequal-width ASCII glyphs with a common height."""
    height = 3
    data = ["\nAABBB\n/\\###\n||# #\n==###\n"]


class TwoBlockFont(velnora.Font):
    """Glyphs of unequal width spread over two data blocks."""
    height = 2
    data = ["\nPQ\n12\n34\n", "\nRRR\nabc\ndef\n"]


def _block_coverage():
    """Share of a cell inked by each Block Elements character, from the Unicode names."""
    table = {0x2580: 1 / 2, 0x2590: 1 / 2, 0x2591: 1 / 4, 0x2592: 1 / 2, 0x2593: 3 / 4,
             0x2594: 1 / 8, 0x2595: 1 / 8, 0x2596: 1 / 4, 0x2597: 1 / 4, 0x2598: 1 / 4,
             0x2599: 3 / 4, 0x259A: 1 / 2, 0x259B: 3 / 4, 0x259C: 3 / 4, 0x259D: 1 / 4,
             0x259E: 1 / 2, 0x259F: 3 / 4}
    for eighths in range(1, 9):
        table[0x2580 + eighths] = eighths / 8  # lower blocks through full block
    for eighths in range(1, 8):
        table[0x2590 - eighths] = eighths / 8  # left blocks, seven eighths at U+2589
    return table


BLOCK_COVERAGE = _block_coverage()
HALF_BLOCKS = frozenset('\u2580\u2584\u258c\u2590')


def is_line_drawing(character):
    return 0x2500 <= ord(character) <= 0x257F


def is_block_element(character):
    return 0x2580 <= ord(character) <= 0x259F


def is_sextant(character):
    return 0x1FB00 <= ord(character) <= 0x1FB3B


def artwork_cells(rows):
    """Nonblank characters of rendered glyph rows (UTF-8 output)."""
    return [cell for row in rows for cell in row.decode('utf-8') if cell != ' ']


def block_ink(cells):
    """Inked cell area of Block Elements artwork; other characters count for nothing."""
    return sum(BLOCK_COVERAGE.get(ord(cell), 0) for cell in cells)


def assert_digit_style(name, glyphs):
    """Broad character-class oracle for the style the PRD and the font's name promise.

    glyphs holds the rendered rows of digits 0 to 9, in order. Exact artwork, and how
    much of a cell a stroke covers, stay open; a few ASCII strokes in thin-line
    artwork are tolerated.
    """
    per_digit = [artwork_cells(glyph) for glyph in glyphs]
    assert all(per_digit), name
    if name.startswith('Thin'):
        for cells in per_digit:
            assert 2 * sum(map(is_line_drawing, cells)) >= len(cells), (name, cells)
            assert not any(is_block_element(c) or is_sextant(c) for c in cells), (name, cells)
    elif name.startswith('Sextant'):
        for cells in per_digit:
            assert all(is_sextant(c) or is_block_element(c) for c in cells), (name, cells)
        # A simple digit may need only whole half columns; the font as a whole uses sextants.
        assert 2 * sum(any(map(is_sextant, cells)) for cells in per_digit) >= len(per_digit), name
    else:
        for cells in per_digit:
            assert all(map(is_block_element, cells)), (name, cells)
        assert 2 * sum(bool(HALF_BLOCKS.intersection(cells)) for cells in per_digit) >= len(per_digit), name
