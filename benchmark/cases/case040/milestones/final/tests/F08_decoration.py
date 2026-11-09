# feature: F08
"""Acceptance checks for decoration geometry and child interaction."""
import pytest
import velnora

from _helpers import canvas_snapshot
from F01_helpers import encoding_state
from F02_helpers import ActionRow, assert_rectangle


def test_padding_filling_and_box_adaptation():
    # Explicitly chosen spans make these proportions integral, without a tie rule.
    for align, start in [('left', 1), ('center', 5), ('right', 9), (('relative', 25), 3)]:
        widget = velnora.Padding(velnora.SolidFill('#'), align=align, width=4, left=1, right=1)
        row = b' ' * start + b'####' + b' ' * (10 - start)
        assert_rectangle(widget.render((14, 2)), [row, row], [[None] * 14] * 2)
    default = velnora.Padding(velnora.Text('ab cd ef'))
    assert_rectangle(default.render((5,)), [b'ab cd', b'ef   '], [[None] * 5] * 2)
    assert default.rows((5,)) == 2
    assert default.pack((5,)) == (5, 2)
    natural = velnora.Padding(velnora.Text('word'), width='pack', align='right', left=1, right=2)
    assert natural.pack(()) == (7, 1)
    assert_rectangle(natural.render((10,)), [b'    word  '], [[None] * 10])
    for width, minimum, count in [(('relative', 50), None, 6),
                                   (('relative', 25), 8, 8), (4, 9, 4)]:
        widget = velnora.Padding(velnora.SolidFill('#'), width=width, min_width=minimum, left=1, right=1)
        row = b' ' + b'#' * count + b' ' * (13 - count)
        assert_rectangle(widget.render((14, 1)), [row], [[None] * 14])
    fractional = velnora.Padding(velnora.SolidFill('#'), width=('relative', 50))
    assert tuple(fractional.render((7, 1)).text) in ((b'###    ',), (b'####   ',))

    for valign, start in [('top', 1), ('middle', 5), ('bottom', 9), (('relative', 25), 3)]:
        widget = velnora.Filler(velnora.SolidFill('#'), valign=valign, height=2, top=1, bottom=1)
        lines = [b'   '] * start + [b'###'] * 2 + [b'   '] * (10 - start)
        assert_rectangle(widget.render((3, 12)), lines, [[None] * 3] * 12)
    natural = velnora.Filler(velnora.Text('xy\nzz'))
    assert natural.rows((3,)) == 2
    assert natural.pack((3,)) == (3, 2)
    assert_rectangle(natural.render((3, 6)), [b'   ', b'   ', b'xy ', b'zz ', b'   ', b'   '], [[None] * 3] * 6)
    for height, minimum, count in [(('relative', 50), None, 4),
                                    (('relative', 25), 6, 6), (2, 7, 2)]:
        widget = velnora.Filler(velnora.SolidFill('@'), valign='top', height=height,
                              min_height=minimum, top=1, bottom=1)
        assert_rectangle(widget.render((2, 10)), [b'  '] + [b'@@'] * count + [b'  '] * (9 - count), [[None] * 2] * 10)
    fractional = velnora.Filler(velnora.SolidFill('#'), valign='top', height=('relative', 50))
    assert tuple(fractional.render((1, 7)).text) in ((b'#',) * 3 + (b' ',) * 4,
                                                  (b'#',) * 4 + (b' ',) * 3)
    adapted = velnora.BoxAdapter(velnora.SolidFill('%'), 3)
    for width in (4, 7):
        assert adapted.rows((width,)) == 3
        assert adapted.pack((width,)) == (width, 3)
        assert_rectangle(adapted.render((width,)), [b'%' * width] * 3, [[None] * width] * 3)

    for options in [dict(align='diagonal'), dict(align=('unknown', 25)),
                    dict(width='unknown'), dict(width=('unknown', 50))]:
        with pytest.raises(velnora.PaddingError):
            velnora.Padding(velnora.Text('ok'), **options)
    for options in [dict(valign='diagonal'), dict(valign=('unknown', 25)),
                    dict(height='unknown'), dict(height=('unknown', 50))]:
        with pytest.raises((velnora.FillerError, ValueError)):
            velnora.Filler(velnora.Text('ok'), **options)
    for width, size in [('pack', (8, 2)), ('clip', (8,))]:
        with pytest.raises(velnora.WidgetError):
            velnora.Padding(velnora.SolidFill('#'), width=width).render(size)


def test_clipping_preserves_columns_attributes_and_focused_cursor():
    with encoding_state():
        velnora.set_encoding('utf-8')
        for align, expected in [('left', 'A界BC'), ('right', 'BC界D')]:
            widget = velnora.Padding(velnora.Text(('ink', 'A界BC界D')), width='clip', align=align)
            snap = canvas_snapshot(widget.render((5,)))
            assert (snap['cols'], snap['rows']) == (5, 1)
            assert snap['text'] == (expected.encode('utf-8'),)
            assert snap['attributes'] == (('ink',) * len(expected.encode('utf-8')),)
        # The first retained cell is half of a wide character: preserve its column.
        widget = velnora.Padding(velnora.Text(('ink', '界ABCD')), width='clip', align='right')
        snap = canvas_snapshot(widget.render((5,)))
        assert (snap['cols'], snap['rows']) == (5, 1)
        assert snap['text'] == (b' ABCD',)
        assert snap['attributes'][0][1:] == ('ink',) * 4
        widget = velnora.Padding(velnora.Text(('ink', 'ABCD界')), width='clip', align='left')
        snap = canvas_snapshot(widget.render((5,)))
        assert (snap['cols'], snap['rows']) == (5, 1)
        assert snap['text'] == (b'ABCD ',)
        assert snap['attributes'][0][:4] == ('ink',) * 4
        centered = velnora.Padding(velnora.Text('ABCDEFGH'), width='clip', align='center')
        assert_rectangle(centered.render((4,)), [b'CDEF'], [[None] * 4])

        edit = velnora.Edit('', 'aa\nbb\ncc\ndd\nee', multiline=True)
        filler = velnora.Filler(velnora.AttrMap(edit, 'body'))
        for position, marker in [(0, b'aa'), (7, b'cc'), (14, b'ee')]:
            edit.set_edit_pos(position)
            snap = canvas_snapshot(filler.render((4, 2), focus=True))
            assert (snap['cols'], snap['rows']) == (4, 2)
            assert snap['cursor'] is not None
            col, row = snap['cursor']
            assert 0 <= col < 4 and 0 <= row < 2
            assert snap['text'][row] == marker + b'  '
            assert col == position % 3
            assert snap['attributes'] == (('body',) * 4,) * 2
            # Do not prescribe which surrounding rows an alternative crop retains.
            assert all(line in (b'aa  ', b'bb  ', b'cc  ', b'dd  ', b'ee  ') for line in snap['text'])
        plain = velnora.Filler(velnora.Text('aa\nbb\ncc\ndd'))
        snap = canvas_snapshot(plain.render((4, 2)))
        assert (snap['cols'], snap['rows']) == (4, 2)
        assert all(line in (b'aa  ', b'bb  ', b'cc  ', b'dd  ') for line in snap['text'])


def test_borders_dividers_and_fills_follow_assigned_rectangle():
    border = velnora.LineBox(velnora.SolidFill('.'), title='Hi', tlcorner='1', trcorner='2',
                           blcorner='3', brcorner='4', tline='-', bline='=', lline='[', rline=']')
    for width, height in [(12, 4), (16, 6)]:
        snap = canvas_snapshot(border.render((width, height)))
        assert (snap['cols'], snap['rows']) == (width, height)
        top, *middle, bottom = snap['text']
        assert top[:1] == b'1' and top[-1:] == b'2'
        assert top.count(b'Hi') == 1
        before, after = top[1:-1].split(b'Hi')
        assert before.strip(b'- ') == after.strip(b'- ') == b''
        assert b'-' in before and b'-' in after
        assert middle == [b'[' + b'.' * (width - 2) + b']'] * (height - 2)
        assert bottom == b'3' + b'=' * (width - 2) + b'4'
    # Left and right titles sit against their edge of the top border; a later
    # title replaces the shown one, and a title needs a top border.
    def top_row(widget):
        return canvas_snapshot(widget.render((14, 3)))['text'][0]

    for align, check in [('left', lambda before, after: before == b''),
                         ('right', lambda before, after: after == b''),
                         ('center', lambda before, after: abs(len(before) - len(after)) <= 1 and before)]:
        aligned = velnora.LineBox(velnora.SolidFill('.'), title='Ab', title_align=align, tline='-',
                                tlcorner='+', trcorner='+')
        inner = top_row(aligned)[1:-1]
        assert inner.count(b'Ab') == 1
        before, after = inner.split(b'Ab')
        assert not before.strip(b' -') and not after.strip(b' -')
        assert check(before.strip(b' '), after.strip(b' ')), (align, inner)
        aligned.set_title('Zq')
        replaced = top_row(aligned)
        assert b'Ab' not in replaced and replaced.count(b'Zq') == 1
    for make in (lambda: velnora.LineBox(velnora.SolidFill('.'), title='Hi', tline=''),
                 lambda: velnora.LineBox(velnora.SolidFill('.'), tline='').set_title('Hi')):
        with pytest.raises(ValueError):
            make()
    # Omitting a side (with its corners) removes its reserved row or column and
    # gives that space to the child; the remaining sides keep theirs.
    for omitted, expected in [
            (dict(tline='', tlcorner='', trcorner=''), [b'[....]'] * 3 + [b'3====4']),
            (dict(bline='', blcorner='', brcorner=''), [b'1----2'] + [b'[....]'] * 3),
            (dict(lline='', tlcorner='', blcorner=''), [b'-----2'] + [b'.....]'] * 2 + [b'=====4']),
            (dict(rline='', trcorner='', brcorner=''), [b'1-----'] + [b'[.....'] * 2 + [b'3=====']),
            (dict(lline='', rline='', tlcorner='', trcorner='', blcorner='', brcorner=''),
             [b'------'] + [b'......'] * 2 + [b'======'])]:
        sides = dict(tlcorner='1', trcorner='2', blcorner='3', brcorner='4',
                     tline='-', bline='=', lline='[', rline=']')
        sides.update(omitted)
        assert_rectangle(velnora.LineBox(velnora.SolidFill('.'), **sides).render((6, 4)),
                         expected, [[None] * 6] * 4)
    for width in (3, 9):
        assert_rectangle(velnora.Divider().render((width,)), [b' ' * width], [[None] * width])
        assert velnora.Divider('~').rows((width,)) == 1
        assert_rectangle(velnora.Divider('~').render((width,)), [b'~' * width], [[None] * width])
        assert velnora.Divider('=', bottom=2).rows((width,)) == 3
        assert velnora.Divider('=', top=2).rows((width,)) == 3
        assert_rectangle(velnora.Divider('=', top=2).render((width,)), [b' ' * width] * 2 + [b'=' * width],
                         [[None] * width] * 3)
    divider = velnora.Divider('~', top=1, bottom=2)
    for width in (3, 9):
        assert divider.rows((width,)) == 4
        assert divider.pack((width,)) == (width, 4)
        assert_rectangle(divider.render((width,)), [b' ' * width, b'~' * width, b' ' * width, b' ' * width], [[None] * width] * 4)
    for char, size in [('+', (5, 2)), ('x', (2, 5))]:
        width, height = size
        assert_rectangle(velnora.SolidFill(char).render(size), [char.encode() * width] * height, [[None] * width] * height)


def test_disabling_and_placeholder_replacement_control_real_interaction():
    live = ActionRow()
    assert live.selectable()
    assert live.keypress((8,), 'enter') is None
    assert live.mouse_event((8,), 'mouse press', 1, 3, 0, True) is True
    assert_rectangle(live.render((8,), True), [b'ARMED   '], [[None] * 8], (3, 0))

    child = ActionRow()
    disabled = velnora.WidgetDisable(child)
    assert disabled.selectable() is False
    assert disabled.keypress((8,), 'enter') == 'enter'
    assert disabled.mouse_event((8,), 'mouse press', 1, 3, 0, True) is False
    assert child.received == []
    assert child.label == 'ready' and child.column == 1
    assert_rectangle(disabled.render((8,), True), [b'ready   '], [[None] * 8])

    first, second = ActionRow(), ActionRow()
    placeholder = velnora.WidgetPlaceholder(first)
    enclosing = velnora.Padding(placeholder, left=1, right=1)
    assert placeholder.selectable()
    assert enclosing.keypress((10,), 'enter') is None
    assert first.received == [('key', (8,), 'enter')]
    assert_rectangle(enclosing.render((10,), True), [b' ARMED    '], [[None] * 10], (2, 0))
    placeholder.original_widget = velnora.Text('passive')
    assert placeholder.selectable() is False
    assert_rectangle(enclosing.render((10,)), [b' passive  '], [[None] * 10])
    placeholder.original_widget = second
    assert placeholder.selectable()
    assert_rectangle(enclosing.render((10,), True), [b' READY    '], [[None] * 10], (2, 0))
    assert enclosing.keypress((10,), 'enter') is None
    assert enclosing.mouse_event((10,), 'mouse press', 1, 4, 0, True) is True
    assert second.received == [('key', (8,), 'enter'), ('mouse', (8,), 'mouse press', 1, 3, 0, True)]
    assert first.received == [('key', (8,), 'enter')]
    assert_rectangle(enclosing.render((10,), True), [b' ARMED    '], [[None] * 10], (4, 0))
