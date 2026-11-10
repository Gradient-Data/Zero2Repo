# feature: F02
"""Acceptance tests for sizing, canvas operations and the widget protocol."""
import pytest
import velnora

from _helpers import canvas_snapshot, send_keys, send_mouse
from F01_helpers import encoding_state
from F02_helpers import ActionRow, assert_rectangle
from F16_helpers import MosaicFont


def test_declared_sizing_and_rendered_geometry():
    # Every declared built-in sizing family, including sizing-preserving wrappers.
    flow_fixed = [velnora.Text('label'), velnora.ANSIText('captured'), velnora.Button('button'),
                  velnora.CheckBox('check'), velnora.RadioButton([], 'radio'),
                  velnora.DropDown(['first', 'second']), velnora.TreeNode('leaf').get_widget(),
                  velnora.GridFlow([velnora.Text('cell')], 8, 1, 0, 'left')]
    flow = [velnora.Edit('', 'edit'), velnora.Divider('-'), velnora.ProgressBar('empty', 'full')]
    fixed = [velnora.BigText('AB', MosaicFont())]
    chart = velnora.BarGraph(['empty', 'bar'])
    chart.set_data([[1]], 2)
    box_widgets = [velnora.SolidFill('#'), chart, velnora.GraphVScale([(1, 'one')], 2)]
    for widgets, modes in ((flow_fixed, {velnora.FLOW, velnora.FIXED}),
                           (flow, {velnora.FLOW}), (fixed, {velnora.FIXED}),
                           (box_widgets, {velnora.BOX})):
        for widget in widgets:
            assert widget.sizing() == modes, type(widget).__name__
            for wrapper in (velnora.AttrMap(widget, None), velnora.LineBox(widget),
                            velnora.WidgetDisable(widget), velnora.WidgetPlaceholder(widget),
                            velnora.PopUpLauncher(widget)):
                assert wrapper.sizing() == modes, (type(wrapper).__name__, type(widget).__name__)
            for mode in modes:
                if mode == velnora.FIXED:
                    dimensions = widget.pack(())
                    canvas = widget.render(())
                elif mode == velnora.FLOW:
                    dimensions = (24, widget.rows((24,)))
                    canvas = widget.render((24,))
                else:
                    dimensions = (24, 4)
                    canvas = widget.render(dimensions)
                observed = canvas_snapshot(canvas)
                assert (observed['cols'], observed['rows']) == dimensions
    # Construction and declared sizing do not start a child process.
    terminal = velnora.Terminal(None)
    assert terminal.sizing() == {velnora.BOX}
    box = velnora.SolidFill('#')
    label = velnora.Text(('ink', 'abc\ndefgh'))
    assert box.sizing() == frozenset([velnora.Sizing.BOX])
    assert label.sizing() == frozenset([velnora.Sizing.FLOW, velnora.Sizing.FIXED])
    for size in [(5, 2), (3, 4)]:
        assert box.pack(size) == size
        assert_rectangle(box.render(size), [b'#' * size[0]] * size[1],
                         [[None] * size[0]] * size[1])
    assert label.pack(()) == (5, 2)
    assert_rectangle(label.render(()), [b'abc  ', b'defgh'],
                     [['ink'] * 3 + [None] * 2, ['ink'] * 5])
    for width, lines, attrs in [
        (4, [b'abc ', b'defg', b'h   '],
         [['ink'] * 3 + [None], ['ink'] * 4, ['ink'] + [None] * 3]),
        (6, [b'abc   ', b'defgh '],
         [['ink'] * 3 + [None] * 3, ['ink'] * 5 + [None]]),
    ]:
        assert label.rows((width,)) == len(lines)
        assert label.pack((width,)) == (min(width, 5), len(lines))
        assert_rectangle(label.render((width,)), lines, attrs)
    editor = velnora.Edit('>', 'xy')
    assert_rectangle(editor.render((5,), focus=True), [b'>xy  '], [[None] * 5], (3, 0))
    for widget, size in [(box, (5,)), (box, ()), (label, (5, 2))]:
        with pytest.raises(ValueError):
            widget.render(size)


def test_canvas_composition_crop_padding_and_cursor_translation():
    left = velnora.TextCanvas([b'abc', b'def'], attr=[[('L', 3)]] * 2, maxcol=3)
    right = velnora.TextCanvas([b'XY', b'Z!'], attr=[[('R', 2)]] * 2,
                             cursor=(1, 1), maxcol=2)
    joined = velnora.CanvasJoin([(left, 0, False, 3), (right, 1, True, 2)])
    assert_rectangle(joined, [b'abcXY', b'defZ!'], [['L'] * 3 + ['R'] * 2] * 2, (4, 1))
    lower = velnora.TextCanvas([b'123', b'456'], attr=[[('B', 3)]] * 2,
                             cursor=(1, 0), maxcol=3)
    stacked = velnora.CanvasCombine([(left, 0, False), (lower, 1, True)])
    assert_rectangle(stacked, [b'abc', b'def', b'123', b'456'],
                     [['L'] * 3] * 2 + [['B'] * 3] * 2, (1, 2))
    background = velnora.TextCanvas([b'abcdef', b'ghijkl', b'mnopqr'],
                                  attr=[[('base', 6)]] * 3, maxcol=6)
    overlaid = velnora.CanvasOverlay(velnora.CompositeCanvas(right),
                                   velnora.CompositeCanvas(background), 2, 1)
    assert_rectangle(overlaid, [b'abcdef', b'ghXYkl', b'mnZ!qr'],
                     [['base'] * 6] + [['base'] * 2 + ['R'] * 2 + ['base'] * 2] * 2, (3, 2))
    cropped = velnora.CompositeCanvas(overlaid)
    cropped.pad_trim_left_right(-1, -1)
    cropped.pad_trim_top_bottom(-1, 0)
    assert_rectangle(cropped, [b'hXYk', b'nZ!q'],
                     [['base', 'R', 'R', 'base']] * 2, (2, 1))
    cropped.pad_trim_left_right(2, 1)
    cropped.pad_trim_top_bottom(1, 1)
    assert_rectangle(cropped, [b'       ', b'  hXYk ', b'  nZ!q ', b'       '],
                     [[None] * 7] + [[None] * 2 + ['base', 'R', 'R', 'base', None]] * 2
                     + [[None] * 7], (4, 2))
    # All public vertical trim paths must drop removed cursors, not retain stale coordinates.
    for operation in ('trim', 'trim_end', 'pad_top', 'pad_bottom'):
        c = velnora.CompositeCanvas(stacked)
        if operation == 'trim':
            c.trim(3, 1)
            lines, attrs = [b'456'], [['B'] * 3]
        elif operation == 'trim_end':
            c.trim_end(2)
            lines, attrs = [b'abc', b'def'], [['L'] * 3] * 2
        elif operation == 'pad_top':
            c.pad_trim_top_bottom(-3, 0)
            lines, attrs = [b'456'], [['B'] * 3]
        else:
            c.pad_trim_top_bottom(0, -2)
            lines, attrs = [b'abc', b'def'], [['L'] * 3] * 2
        assert_rectangle(c, lines, attrs)
    # A cursor in a kept row survives every vertical trim, moved with its row.
    for operation in ('trim', 'trim_end', 'pad_top', 'pad_bottom'):
        c = velnora.CompositeCanvas(stacked)
        if operation == 'trim':
            c.trim(1, 2)
            lines, attrs, cursor = [b'def', b'123'], [['L'] * 3, ['B'] * 3], (1, 1)
        elif operation == 'trim_end':
            c.trim_end(1)
            lines, attrs, cursor = [b'abc', b'def', b'123'], [['L'] * 3] * 2 + [['B'] * 3], (1, 2)
        elif operation == 'pad_top':
            c.pad_trim_top_bottom(-2, 0)
            lines, attrs, cursor = [b'123', b'456'], [['B'] * 3] * 2, (1, 0)
        else:
            c.pad_trim_top_bottom(0, -1)
            lines, attrs, cursor = [b'abc', b'def', b'123'], [['L'] * 3] * 2 + [['B'] * 3], (1, 2)
        assert_rectangle(c, lines, attrs, cursor)
    with encoding_state():
        velnora.set_encoding('utf-8')
        wide = velnora.Text(('wide', 'A中BC')).render((5,))
        c = velnora.CompositeCanvas(wide)
        c.pad_trim_left_right(-2, 0)
        assert_rectangle(c, [b' BC'], [['wide'] * 3])
        c = velnora.CompositeCanvas(wide)
        c.pad_trim_left_right(0, -3)
        assert_rectangle(c, [b'A '], [['wide'] * 2])


def test_nested_render_reflects_content_appearance_and_focus():
    first, second = velnora.Edit('', 'one'), velnora.Edit('', 'two')
    a = velnora.AttrMap(first, 'normal', 'active')
    b = velnora.AttrMap(second, 'normal', 'active')
    pile = velnora.Pile([a, b])
    outer = velnora.Padding(pile, left=1, right=1)
    retained = []
    def observe():
        # Keep earlier canvases alive, as a real display can, without observing cache internals.
        canvas = outer.render((7,), focus=True)
        retained.append(canvas)
        return canvas
    assert_rectangle(observe(), [b' one   ', b' two   '],
                     [[None] + ['active'] * 5 + [None], [None] + ['normal'] * 5 + [None]], (4, 0))
    first.set_edit_text('oak')
    assert_rectangle(observe(), [b' oak   ', b' two   '],
                     [[None] + ['active'] * 5 + [None], [None] + ['normal'] * 5 + [None]], (4, 0))
    a.set_focus_map({None: 'changed'})
    b.set_attr_map({None: 'restyled'})
    assert_rectangle(observe(), [b' oak   ', b' two   '],
                     [[None] + ['changed'] * 5 + [None], [None] + ['restyled'] * 5 + [None]], (4, 0))
    pile.focus_position = 1
    assert_rectangle(observe(), [b' oak   ', b' two   '],
                     [[None] + ['normal'] * 5 + [None], [None] + ['active'] * 5 + [None]], (4, 1))
    second.set_edit_pos(1)
    assert canvas_snapshot(observe())['cursor'] == (2, 1)


def test_application_widget_render_input_and_cursor_protocol():
    control = ActionRow()
    columns = velnora.Columns([(2, velnora.Text('>>')), control])
    outer = velnora.Pile([velnora.Text('header'), columns])
    assert velnora.Sizing.FLOW in outer.sizing()
    assert outer.rows((8,), focus=True) == 2
    assert_rectangle(outer.render((8,), focus=False), [b'header  ', b'>>ready '], [[None] * 8] * 2)
    assert_rectangle(outer.render((8,), focus=True), [b'header  ', b'>>READY '], [[None] * 8] * 2, (3, 1))
    assert outer.get_cursor_coords((8,)) == (3, 1)
    assert send_keys(outer, (8,), ['enter', 'f8']) == (None, 'f8')
    assert control.received == [('key', (6,), 'enter'), ('key', (6,), 'f8')]
    assert_rectangle(outer.render((8,), focus=True), [b'header  ', b'>>ARMED '], [[None] * 8] * 2, (3, 1))
    assert send_mouse(outer, (8,), [('mouse press', 1, 5, 1)], focus=True) == (True,)
    assert control.received[-1] == ('mouse', (6,), 'mouse press', 1, 3, 0, True)
    assert outer.get_cursor_coords((8,)) == (5, 1)
    assert_rectangle(outer.render((8,), focus=True), [b'header  ', b'>>ARMED '], [[None] * 8] * 2, (5, 1))
