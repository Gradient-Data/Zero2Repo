# feature: F14
"""Acceptance coverage for foreground composition and nested pop-up targets."""
import velnora

from _helpers import canvas_snapshot, send_keys
from F02_helpers import ActionRow, assert_rectangle
from F14_helpers import ApplicationLauncher, located_launcher


def test_overlay_composition_and_input():
    # Even spare space avoids specifying a centering tie-break.
    scenarios = [
        (dict(align='left', width=6, valign='top', height=2, left=2, top=1), (2, 1, 6, 2)),
        (dict(align='right', width=7, valign='bottom', height=3, right=1, bottom=1), (8, 4, 7, 3)),
        (dict(align='center', width=('relative', 50), valign='middle', height=('relative', 50)), (4, 2, 8, 4)),
    ]
    for options, (left, top, width, height) in scenarios:
        front, back = ActionRow(), ActionRow()
        background = velnora.AttrMap(velnora.Filler(back, valign='top'), 'back')
        foreground = velnora.AttrMap(velnora.Filler(front, valign='top'), 'front')
        overlay = velnora.Overlay(foreground, background, **options)
        for label in (b'READY', b'ARMED'):
            rows = [b'ready'.ljust(16)] + [b' ' * 16 for _ in range(7)]
            attrs = [['back'] * 16 for _ in range(8)]
            for row in range(top, top + height):
                data = label.ljust(width) if row == top else b' ' * width
                rows[row] = rows[row][:left] + data + rows[row][left + width:]
                attrs[row][left:left + width] = ['front'] * width
            assert_rectangle(overlay.render((16, 8), focus=True), rows, attrs, (left + 1, top))
            if label == b'READY':
                assert send_keys(overlay, (16, 8), ['enter']) == (None,)
        assert back.label == 'ready'
        assert front.label == 'armed'
    # Blank foreground cells still obscure, and a cursorless foreground hides the background's.
    backdrop = velnora.Edit('', 'x' * 6, edit_pos=2)
    behind = velnora.AttrMap(velnora.Pile([backdrop, velnora.BoxAdapter(velnora.SolidFill('.'), 3)]), 'back')
    plain = velnora.AttrMap(velnora.Filler(velnora.Text('F'), valign='top'), 'front')
    overlay = velnora.Overlay(plain, velnora.Filler(behind, valign='top'),
                            align='left', width=3, valign='top', height=2, left=1, top=1)
    rows = [b'xxxxxx', b'.F  ..', b'.   ..', b'......']
    attrs = [['back'] * 6, ['back'] + ['front'] * 3 + ['back'] * 2,
             ['back'] + ['front'] * 3 + ['back'] * 2, ['back'] * 6]
    assert_rectangle(overlay.render((6, 4), focus=True), rows, attrs, None)


def test_launcher_target_relative_placement_and_fit():
    # Explicit expected rectangles cover offset, shift and reduction separately.
    cases = [
        ((14, 9), (2, 2), (1, 1, 4, 2), (3, 3, 4, 2)),
        ((14, 9), (10, 6), (1, 1, 5, 3), (9, 6, 5, 3)),
        ((5, 3), (1, 1), (1, 1, 9, 7), (0, 0, 5, 3)),
        ((14, 9), (2, 2), (-5, -5, 4, 2), (0, 0, 4, 2)),
    ]
    for size, (x, y), (dx, dy, width, height), (left, top, fitted_w, fitted_h) in cases:
        launcher = ApplicationLauncher(velnora.Text('L'), velnora.SolidFill('p'),
                                     dict(left=dx, top=dy, overlay_width=width, overlay_height=height))
        body = located_launcher(launcher, x, y)
        target = velnora.PopUpTarget(body)
        closed = canvas_snapshot(target.render(size))
        assert closed['text'][y][x:x + 1] == b'L'
        launcher.open_pop_up()
        # Opening without a target preserves the actual launcher canvas.
        assert canvas_snapshot(body.render(size))['text'] == closed['text']
        expected = list(closed['text'])
        for row in range(top, top + fitted_h):
            expected[row] = expected[row][:left] + b'p' * fitted_w + expected[row][left + fitted_w:]
        opened = canvas_snapshot(target.render(size))
        assert opened['text'] == tuple(expected)
        assert (opened['cols'], opened['rows']) == size
        # The same open pop-up on a larger screen is fitted anew, not left at its old rectangle.
        roomy = (size[0] + 8, size[1] + 8)
        left, top = max(0, x + dx), max(0, y + dy)
        grown = canvas_snapshot(target.render(roomy))['text']
        assert canvas_snapshot(target.render(size))['text'] == opened['text']
        launcher.close_pop_up()
        assert canvas_snapshot(target.render(size))['text'] == closed['text']
        expected = list(canvas_snapshot(target.render(roomy))['text'])
        for row in range(top, top + height):
            expected[row] = expected[row][:left] + b'p' * width + expected[row][left + width:]
        assert grown == tuple(expected)


def test_anchored_popup_side_and_height():
    cases = [
        # screen height, launcher row, requested height, resulting top and height, launcher rows
        (11, 2, 4, 3, 4, 1),   # below fits
        (11, 8, 4, 4, 4, 1),   # only above fits
        (11, 4, 10, 5, 6, 1),  # neither fits: below has more rows
        (11, 6, 10, 0, 6, 1),  # neither fits: above has more rows
        (11, 5, 10, 6, 5, 1),  # equal space prefers below
        (1, 0, 2, 0, 1, 1),    # no space off the launcher
        (11, 5, 4, 1, 4, 3),   # taller launcher: above starts over its first row
        (11, 4, 10, 7, 4, 3),  # taller launcher: both sides have four rows
        (11, 5, 10, 0, 5, 3),  # taller launcher: above has more rows
        (2, 0, 1, 1, 1, 2),    # no space: the requested offset stays on screen
    ]
    for screen_h, y, requested_h, top, height, anchor in cases:
        launcher = ApplicationLauncher(velnora.Text('\n'.join('L' * anchor)), velnora.SolidFill('p'),
                                     dict(left=0, top=anchor, overlay_width=3,
                                          overlay_height=requested_h, anchor_height=anchor))
        target = velnora.PopUpTarget(located_launcher(launcher, 0, y))
        before = canvas_snapshot(target.render((3, screen_h)))['text']
        assert before[y:y + anchor] == (b'L  ',) * anchor
        launcher.open_pop_up()
        expected = list(before)
        expected[top:top + height] = [b'ppp'] * height
        assert canvas_snapshot(target.render((3, screen_h)))['text'] == tuple(expected)


def test_nested_popup_input_close_and_focus():
    root_edit = velnora.Edit('R:')
    first, second, inner_edit = velnora.Edit('A:'), velnora.Edit('B:'), velnora.Edit('I:')
    choices = velnora.Pile([first, second])
    choices.focus_position = 1
    inner = ApplicationLauncher(velnora.Filler(choices, valign='top'),
                               velnora.Filler(inner_edit, valign='top'),
                               dict(left=2, top=1, overlay_width=6, overlay_height=2))
    outer = ApplicationLauncher(velnora.Filler(root_edit, valign='top'), inner,
                               dict(left=3, top=2, overlay_width=12, overlay_height=4))
    target = velnora.PopUpTarget(outer)
    size = (22, 9)
    assert send_keys(target, size, ['f2']) == (None,)
    for reverse in (False, True):
        target.enter_selectable(reverse=reverse)
        assert canvas_snapshot(target.render(size, focus=True))['cursor'] == (5, 3)
    assert send_keys(target, size, ['x']) == (None,)
    assert (first.edit_text, second.edit_text, root_edit.edit_text) == ('', 'x', '')
    outer_canvas = canvas_snapshot(target.render(size, focus=True))
    assert outer_canvas['text'][2][3:5] == b'A:'
    assert outer_canvas['text'][3][3:6] == b'B:x'
    assert send_keys(target, size, ['f2', 'z']) == (None, None)
    nested = canvas_snapshot(target.render(size, focus=True))
    assert nested['text'][3][3:11] == b'B:I:z   '
    assert nested['text'][2][3:5] == b'A:'
    assert nested['cursor'] == (8, 3)
    assert (inner_edit.edit_text, second.edit_text, root_edit.edit_text) == ('z', 'x', '')
    assert send_keys(target, size, ['esc']) == (None,)
    assert canvas_snapshot(target.render(size, focus=True))['text'] == outer_canvas['text']
    assert send_keys(target, size, ['y']) == (None,)
    assert second.edit_text == 'xy'
    # Close the ancestor while a descendant is visibly open.
    assert send_keys(target, size, ['f2']) == (None,)
    assert canvas_snapshot(target.render(size, focus=True))['text'][3][5:8] == b'I:z'
    outer.close_pop_up()
    assert send_keys(target, size, ['r']) == (None,)
    restored = canvas_snapshot(target.render(size, focus=True))
    assert restored['text'] == (b'R:r'.ljust(22),) + (b' ' * 22,) * 8
    assert restored['cursor'] == (3, 0)
    assert (root_edit.edit_text, second.edit_text, inner_edit.edit_text) == ('r', 'xy', 'z')

    # The inner launcher sits where its parent was actually placed, not where it was requested.
    inner_edit = velnora.Edit('I:')
    inner = ApplicationLauncher(velnora.Filler(velnora.Text('M'), valign='top'),
                               velnora.Filler(inner_edit, valign='top'),
                               dict(left=2, top=1, overlay_width=6, overlay_height=2))
    outer = ApplicationLauncher(velnora.Filler(velnora.Edit('R:'), valign='top'), inner,
                               dict(left=18, top=7, overlay_width=12, overlay_height=4))
    target = velnora.PopUpTarget(outer)
    size = (22, 9)
    assert send_keys(target, size, ['f2']) == (None,)
    fitted = canvas_snapshot(target.render(size, focus=True))
    assert fitted['text'][5][10:] == b'M'.ljust(12)
    assert send_keys(target, size, ['f2', 'z']) == (None, None)
    nested = canvas_snapshot(target.render(size, focus=True))
    assert nested['text'][6][12:] == b'I:z'.ljust(10)
    assert nested['cursor'] == (15, 6)
    assert inner_edit.edit_text == 'z'

    # Three open levels: input reaches the deepest, and each close restores its parent.
    deepest_edit, middle_edit, outer_edit = velnora.Edit('D:'), velnora.Edit('C:'), velnora.Edit('B:')
    deepest = ApplicationLauncher(velnora.Filler(middle_edit, valign='top'),
                                 velnora.Filler(deepest_edit, valign='top'),
                                 dict(left=1, top=1, overlay_width=6, overlay_height=1))
    middle = ApplicationLauncher(velnora.Filler(outer_edit, valign='top'), deepest,
                                dict(left=1, top=1, overlay_width=8, overlay_height=3))
    root = ApplicationLauncher(velnora.Filler(velnora.Edit('A:'), valign='top'), middle,
                              dict(left=1, top=1, overlay_width=10, overlay_height=4))
    target = velnora.PopUpTarget(root)
    size = (16, 8)
    views = [canvas_snapshot(target.render(size, focus=True))['text']]
    for _ in range(3):
        assert send_keys(target, size, ['f2']) == (None,)
        views.append(canvas_snapshot(target.render(size, focus=True))['text'])
    assert views[3][3][3:9] == b'D:    '
    assert send_keys(target, size, ['q']) == (None,)
    assert (deepest_edit.edit_text, middle_edit.edit_text, outer_edit.edit_text) == ('q', '', '')
    assert send_keys(target, size, ['esc']) == (None,)
    assert canvas_snapshot(target.render(size, focus=True))['text'] == views[2]
    assert send_keys(target, size, ['w']) == (None,)
    assert (deepest_edit.edit_text, middle_edit.edit_text, outer_edit.edit_text) == ('q', 'w', '')
