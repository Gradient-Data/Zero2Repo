# feature: F01
"""Encoding state isolation and public run-length carrier observations."""
from contextlib import contextmanager

import velnora
from velnora import apply_target_encoding, calc_text_pos, calc_width, move_next_char, move_prev_char
from velnora.util import get_encoding, trim_text_attr_cs


@contextmanager
def encoding_state():
    encoding = get_encoding()
    replacements = dict(velnora.get_ascii_fallbacks())
    try:
        velnora.set_ascii_fallbacks({})
        yield
    finally:
        velnora.set_ascii_fallbacks(replacements)
        velnora.set_encoding(encoding)


def expanded_runs(runs):
    return tuple(value for value, length in runs for _ in range(length))


def encoded_observation(text):
    data, runs = apply_target_encoding(text)
    return data, expanded_runs(runs)


def assert_cluster_sequence(clusters):
    """Check boundaries, column lookup and all clipping windows for (cluster, width) pairs.

    Requires a UTF-8 selection. The oracle is the cell model: a cluster is shown whole
    when the window covers all its cells, otherwise each exposed cell is one blank.
    """
    for encoded in (False, True):
        pieces = [c.encode('utf-8') if encoded else c for c, _ in clusters]
        text = (b'' if encoded else '').join(pieces)
        bounds = [0]
        for piece in pieces:
            bounds.append(bounds[-1] + len(piece))
        columns = [0]
        for _, width in clusters:
            columns.append(columns[-1] + width)
        assert calc_width(text, 0, len(text)) == columns[-1]
        for left, right in zip(bounds, bounds[1:]):
            assert move_next_char(text, left, len(text)) == right
            assert move_prev_char(text, 0, right) == left
        for index, (left, right) in enumerate(zip(bounds, bounds[1:])):
            assert calc_width(text, left, right) == clusters[index][1]
        for wanted in range(columns[-1] + 1):
            index = max(i for i, column in enumerate(columns) if column <= wanted)
            assert calc_text_pos(text, 0, len(text), wanted) == (bounds[index], columns[index])
    raw = ''.join(c for c, _ in clusters).encode('utf-8')
    for start in range(columns[-1]):
        for end in range(start + 1, columns[-1] + 1):
            expected = b''
            for (cluster, width), column in zip(clusters, columns):
                overlap = min(end, column + width) - max(start, column)
                if overlap == width:
                    expected += cluster.encode('utf-8')
                elif overlap > 0:
                    expected += b' ' * overlap
            assert trim_text_attr_cs(raw, [], [], start, end)[0] == expected, (start, end)
