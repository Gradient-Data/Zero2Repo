# feature: F15
"""Drop-down scenes and observations through public widget and canvas APIs."""
import velnora

from _helpers import canvas_snapshot


def selection_scene(control, *, column=0, row=0, width=18):
    """Return a target placing a flow control at a caller-specified position."""
    placed = velnora.Padding(control, align='left', width=width, left=column)
    body = velnora.Filler(velnora.Pile([velnora.Text('')] * row + [placed]), valign='top')
    return velnora.PopUpTarget(body)


def selection_view(target, size):
    """Read fully materialized public canvas content; failures propagate."""
    return canvas_snapshot(target.render(size, focus=True))


def assert_closed_selection(target, size, label, *, column=0, row=0):
    """Check the selected label and the restored blank area around its row."""
    view = selection_view(target, size)
    assert (view['cols'], view['rows']) == size
    encoded = label.encode('utf-8')
    assert view['text'][row][column:column + len(encoded)] == encoded
    assert all(line == b' ' * size[0] for y, line in enumerate(view['text']) if y != row)
    return view
