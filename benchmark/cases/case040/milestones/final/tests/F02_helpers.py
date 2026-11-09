# feature: F02
"""Canvas assertions and a small real application widget."""
import velnora

from _helpers import canvas_snapshot


def assert_rectangle(canvas, text, attributes, cursor=None):
    """Compare visible bytes and attributes without pinning run boundaries."""
    observed = canvas_snapshot(canvas)
    assert observed['text'] == tuple(text)
    assert observed['attributes'] == tuple(tuple(row) for row in attributes)
    assert observed['rows'] == len(text)
    assert observed['cols'] == len(text[0])
    assert observed['cursor'] == cursor


class ActionRow(velnora.Widget):
    """Application control that activates by keyboard and positions by mouse."""
    _sizing = frozenset([velnora.Sizing.FLOW])
    _selectable = True

    def __init__(self):
        super().__init__()
        self.label = 'ready'
        self.column = 1
        self.received = []

    def rows(self, size, focus=False):
        return 1

    def render(self, size, focus=False):
        label = self.label.upper() if focus else self.label
        data = label.encode('ascii').ljust(size[0], b' ')
        return velnora.TextCanvas([data], cursor=self.get_cursor_coords(size) if focus else None,
                                maxcol=size[0])

    def get_cursor_coords(self, size):
        return self.column, 0

    def keypress(self, size, key):
        self.received.append(('key', size, key))
        if key != 'enter':
            return key
        self.label = 'armed'
        self._invalidate()
        return None

    def mouse_event(self, size, event, button, col, row, focus):
        self.received.append(('mouse', size, event, button, col, row, focus))
        if event == 'mouse press' and button == 1:
            self.column = col
            self._invalidate()
            return True
        return False
