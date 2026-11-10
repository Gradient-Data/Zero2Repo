# feature: F13
"""Application content and public canvas observations for scrolling."""
import velnora
from _helpers import canvas_snapshot


class FixedLines(velnora.Text):
    """Application text that advertises only its natural fixed size."""
    def sizing(self):
        return frozenset((velnora.Sizing.FIXED,))


class ClaimingLines(velnora.Text):
    """Application flow content that handles wheel input itself."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.received = []

    def mouse_event(self, size, event, button, col, row, focus):
        if button in (4, 5):
            self.received.append((event, button))
            return True
        return False


def numbered_content(count):
    return '\n'.join(f'row {i:02}' for i in range(count))


def assert_viewport(widget, size, start, *, focus=False, side=None, width=0):
    """Check actual visible application rows, independently of reported position."""
    observed = canvas_snapshot(widget.render(size, focus=focus))
    assert (observed['cols'], observed['rows']) == size
    content_width = size[0] - width
    expected = tuple(f'row {i:02}'.encode().ljust(content_width)
                     for i in range(start, start + size[1]))
    actual = observed['text']
    if width:
        actual = tuple(row[width:] if side == 'left' else row[:-width] for row in actual)
    assert actual == expected
    return observed


def bar_cells(observed, *, side='right', width=1):
    """Read the caller-configured scrollbar columns; preserve every cell."""
    return tuple(row[:width] if side == 'left' else row[-width:]
                 for row in observed['text'])


def thumb_rows(observed, *, side='right', thumb=b'#'):
    """Rows of the caller-configured thumb character, top first."""
    return [row for row, cell in enumerate(bar_cells(observed, side=side)) if thumb in cell]
