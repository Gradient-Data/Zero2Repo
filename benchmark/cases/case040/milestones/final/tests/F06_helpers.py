# feature: F06
"""Public canvas observations and an application-provided text layout."""
import velnora
from _helpers import canvas_snapshot


def label_lines(widget, width, focus=False):
    snapshot = canvas_snapshot(widget.render((width,), focus=focus))
    assert snapshot['cols'] == width
    assert snapshot['rows'] == len(snapshot['text'])
    return tuple(line.decode('utf-8') for line in snapshot['text'])


class VerticalLabelLayout(velnora.TextLayout):
    """Place each ASCII character on its own row, indented two columns."""
    def layout(self, text, width, align, wrap):
        lines = [[(2, None), (1, offset, offset + 1)]
                 for offset in range(len(text))]
        if not lines:
            lines = [[(2, None)]]
        lines[-1].append((0, len(text)))
        return lines
