# feature: F13
"""Acceptance tests for viewports and interactive scrollbars."""
import math
import pytest
import velnora

from _helpers import canvas_snapshot, send_keys, send_mouse
from F12_helpers import assert_focused_row
from F13_helpers import (ClaimingLines, FixedLines, assert_viewport, bar_cells, numbered_content,
                        thumb_rows)


def test_viewport_offsets_commands_and_cursor():
    size = (12, 6)
    for content in (velnora.Text(numbered_content(20)), FixedLines(numbered_content(20))):
        viewport = velnora.Scrollable(content)
        assert_viewport(viewport, size, 0)
        assert viewport.get_scrollpos() == 0
        # Commands also start from interior rows, so "to the boundary" cannot pass as a step.
        for key, start in [('down', 1), ('down', 2), ('up', 1), ('page down', 6),
                           ('page down', 11), ('page up', 6), ('up', 5), ('page up', 0),
                           ('end', 14), ('down', 14), ('page down', 14), ('page up', 9),
                           ('home', 0), ('up', 0), ('page up', 0)]:
            send_keys(viewport, size, [key])
            assert_viewport(viewport, size, start)
            assert viewport.get_scrollpos() == start
        for position, start in [(3, 3), (-1, 14), (-2, 13), (100, 14), (-100, 0)]:
            viewport.set_scrollpos(position)
            assert_viewport(viewport, size, start)
            assert viewport.get_scrollpos() == start
        # The scrollbar supplies wheel handling even when its bar is hidden.
        wheel = velnora.ScrollBar(viewport, visible=False)
        assert_viewport(wheel, size, 0)
        for button, start in [(5, 1), (4, 0), (4, 0)]:
            send_mouse(wheel, size, [('mouse press', button, 1, 2)], focus=True)
            assert_viewport(wheel, size, start)
            assert viewport.get_scrollpos() == start
    edit = velnora.Edit('', numbered_content(20), multiline=True, edit_pos=0)
    viewport = velnora.Scrollable(edit)
    observed = assert_viewport(viewport, size, 0, focus=True)
    assert observed['cursor'] == (0, 0)
    send_keys(viewport, size, ['down'])
    observed = assert_viewport(viewport, size, 0, focus=True)
    assert observed['cursor'] == (0, 1)
    assert viewport.get_scrollpos() == 0
    send_keys(viewport, size, ['x'])
    assert edit.edit_text.splitlines()[1] == 'xrow 01'
    edited = canvas_snapshot(viewport.render(size, focus=True))
    assert edited['text'][1] == b'xrow 01     '
    assert edited['cursor'] == (1, 1)
    # A visible cursor is reported at its viewport row, not its content row.
    viewport.set_scrollpos(1)
    assert canvas_snapshot(viewport.render(size, focus=True))['cursor'] == (1, 0)
    viewport.set_scrollpos(8)
    observed = assert_viewport(viewport, size, 8, focus=True)
    assert observed['cursor'] is None
    # The other side: the cursor lies below the viewport.
    below = velnora.Edit('', numbered_content(20), multiline=True,
                       edit_pos=numbered_content(20).index('row 15'))
    viewport = velnora.Scrollable(below)
    viewport.set_scrollpos(3)
    observed = assert_viewport(viewport, size, 3, focus=True)
    assert observed['cursor'] is None
    with pytest.raises(ValueError):
        velnora.Scrollable(velnora.SolidFill('x'))


def test_scrollbar_geometry_visibility_and_placement():
    size = (12, 6)
    for options, side, width in [({}, 'right', 1), ({'side': 'left', 'width': 2}, 'left', 2),
                                  ({'width': 0}, 'right', 1), ({'width': -3}, 'right', 1)]:
        viewport = velnora.Scrollable(velnora.Text(numbered_content(12)))
        bar = velnora.ScrollBar(viewport, thumb_char='#', trough_char='.', **options)
        observed = assert_viewport(bar, size, 0, side=side, width=width)
        assert bar_cells(observed, side=side, width=width) == (b'#' * width,) * 3 + (b'.' * width,) * 3
    with pytest.raises(ValueError):
        velnora.ScrollBar(velnora.Scrollable(velnora.Text('content')), side='above')
    # Exact ratios avoid forcing a rounding policy; fractional ratios accept adjacent integers.
    for count in (12, 24, 100):
        viewport = velnora.Scrollable(velnora.Text(numbered_content(count)))
        bar = velnora.ScrollBar(viewport, thumb_char='#', trough_char='.')
        for position, start in [(0, 0), (-1, count - size[1])]:
            viewport.set_scrollpos(position)
            observed = assert_viewport(bar, size, start, width=1)
            cells = bar_cells(observed)
            height = cells.count(b'#')
            ratio = size[1] * size[1] / count
            assert height in {max(1, math.floor(ratio)), max(1, math.ceil(ratio))}
            assert set(cells) <= {b'#', b'.'}
            expected = (b'#',) * height + (b'.',) * (size[1] - height)
            assert cells == (expected if position == 0 else expected[::-1])
    for options, width in [({}, 0), ({'visible': True}, 1), ({'visible': False}, 0)]:
        bar = velnora.ScrollBar(velnora.Scrollable(velnora.Text(numbered_content(6))),
                              thumb_char='#', trough_char='.', **options)
        observed = assert_viewport(bar, size, 0, width=width)
        if width:
            assert bar_cells(observed) == (b'#',) * size[1]
    # Interior positions: the thumb tracks position/range, accepting either adjacent row.
    viewport = velnora.Scrollable(velnora.Text(numbered_content(30)))
    bar = velnora.ScrollBar(viewport, thumb_char='#', trough_char='.')
    tops = []
    for position in range(25):
        viewport.set_scrollpos(position)
        rows = thumb_rows(assert_viewport(bar, size, position, width=1))
        assert len(rows) in (1, 2)
        ideal = position / 24 * (size[1] - len(rows))
        assert math.floor(ideal) <= rows[0] <= math.ceil(ideal)
        tops.append(rows[0])
    assert tops == sorted(tops) and len(set(tops)) >= 5
    viewport = velnora.Scrollable(velnora.Text(numbered_content(20)))
    bar = velnora.ScrollBar(viewport, visible=False)
    assert_viewport(bar, size, 0)
    send_keys(bar, size, ['page down'])
    assert_viewport(bar, size, 5)
    send_mouse(bar, size, [('mouse press', 5, 1, 2)], focus=True)
    assert_viewport(bar, size, 6)
    # Hidden mode shows no bar, so the last column is ordinary content.
    send_mouse(bar, size, [('mouse press', 1, 11, 5), ('mouse release', 1, 11, 5)], focus=True)
    assert_viewport(bar, size, 6)
    # Automatic visibility follows the current content, not the first rendering.
    content = velnora.Text(numbered_content(6))
    bar = velnora.ScrollBar(velnora.Scrollable(content), thumb_char='#', trough_char='.')
    assert_viewport(bar, size, 0)
    content.set_text(numbered_content(12))
    observed = assert_viewport(bar, size, 0, width=1)
    assert bar_cells(observed) == (b'#',) * 3 + (b'.',) * 3
    content.set_text(numbered_content(6))
    assert_viewport(bar, size, 0)
    # List views: the same three visibility modes around content that fits.
    for options, width in [({}, 0), ({'visible': True}, 1), ({'visible': False}, 0)]:
        box = velnora.ListBox(velnora.SimpleFocusListWalker([velnora.Edit('', f'row {i:02}') for i in range(6)]))
        bar = velnora.ScrollBar(box, thumb_char='#', trough_char='.', **options)
        observed = assert_viewport(bar, size, 0, width=width)
        if width:
            assert bar_cells(observed) == (b'#',) * size[1]


def test_pointer_markers_and_styles():
    size = (12, 6)
    for side, col in [('right', 11), ('left', 0)]:
        viewport = velnora.Scrollable(velnora.Text(numbered_content(30)))
        bar = velnora.ScrollBar(viewport, side=side, thumb_char='#', trough_char='.')
        assert_viewport(bar, size, 0, side=side, width=1)
        for row, start in [(5, 24), (0, 0)]:
            send_mouse(bar, size, [('mouse press', 1, col, row), ('mouse release', 1, col, row)], focus=True)
            assert_viewport(bar, size, start, side=side, width=1)
            assert viewport.get_scrollpos() == start
        send_mouse(bar, size, [('mouse press', 1, col, 2)], focus=True)
        observed = canvas_snapshot(bar.render(size))
        assert 0 < viewport.get_scrollpos() < 24
        assert_viewport(bar, size, viewport.get_scrollpos(), side=side, width=1)
        assert 2 in thumb_rows(observed, side=side)
        for row, start in [(5, 24), (0, 0)]:
            send_mouse(bar, size, [('mouse drag', 1, col, row)], focus=True)
            assert_viewport(bar, size, start, side=side, width=1)
            assert viewport.get_scrollpos() == start
        # A drag from the thumb stops at each interior row it passes through.
        send_mouse(bar, size, [('mouse press', 1, col, 0)], focus=True)
        positions = []
        # Row 4 is excluded: with a two-row thumb it is already the end of travel.
        for row in (1, 2, 3):
            send_mouse(bar, size, [('mouse drag', 1, col, row)], focus=True)
            positions.append(viewport.get_scrollpos())
            observed = assert_viewport(bar, size, positions[-1], side=side, width=1)
            # Position rounding may leave the thumb one row from the pointer.
            assert min(abs(row - thumb) for thumb in thumb_rows(observed, side=side)) <= 1
        assert 0 < positions[0] < positions[1] < positions[2] < 24
        send_mouse(bar, size, [('mouse release', 1, col, 3)], focus=True)
    # Every scrollbar column takes pointer and wheel input; wheels work over content too.
    for side, columns, content_col in [('right', (10, 11), 3), ('left', (0, 1), 6)]:
        for content in (velnora.Text(numbered_content(30)), FixedLines(numbered_content(30))):
            viewport = velnora.Scrollable(content)
            bar = velnora.ScrollBar(viewport, side=side, width=2, thumb_char='#', trough_char='.')
            assert_viewport(bar, size, 0, side=side, width=2)
            for col in columns:
                send_mouse(bar, size, [('mouse press', 1, col, 5), ('mouse release', 1, col, 5)], focus=True)
                assert_viewport(bar, size, 24, side=side, width=2)
                send_mouse(bar, size, [('mouse press', 1, col, 0), ('mouse release', 1, col, 0)], focus=True)
                assert_viewport(bar, size, 0, side=side, width=2)
            position = 0
            for col in (*columns, content_col):
                for button, step in [(5, 1), (5, 1), (4, -1)]:
                    send_mouse(bar, size, [('mouse press', button, col, 2)], focus=True)
                    position += step
                    assert_viewport(bar, size, position, side=side, width=2)
                    assert viewport.get_scrollpos() == position
    # A child that handles the wheel keeps it, with the bar shown or hidden.
    for visible, width in [(None, 1), (False, 0)]:
        child = ClaimingLines(numbered_content(20))
        viewport = velnora.Scrollable(child)
        bar = velnora.ScrollBar(viewport, visible=visible, thumb_char='#', trough_char='.')
        viewport.set_scrollpos(3)
        assert_viewport(bar, size, 3, width=width)
        for button in (5, 4):
            send_mouse(bar, size, [('mouse press', button, 2, 1)], focus=True)
            assert_viewport(bar, size, 3, width=width)
        assert [button for _, button in child.received] == [5, 4]
    viewport = velnora.Scrollable(velnora.Text(numbered_content(20)))
    bar = velnora.ScrollBar(viewport, thumb_char='#', trough_char='.', end_markers=('^', 'v'),
                          attr='track', focus_attr='focus-track', thumb_attr='thumb',
                          thumb_focus_attr='focus-thumb', marker_dim_attr='boundary')
    for position, start, boundary in [(0, 0, 0), (5, 5, None), (-1, 14, 5)]:
        viewport.set_scrollpos(position)
        for focus in (False, True):
            observed = assert_viewport(bar, size, start, focus=focus, width=1)
            cells = bar_cells(observed)
            assert cells[0] == b'^' and cells[-1] == b'v'
            assert b'#' in cells[1:-1]
            for row, cell in enumerate(cells):
                expected = ('focus-thumb' if focus else 'thumb') if cell == b'#' else ('focus-track' if focus else 'track')
                if row == boundary:
                    expected = 'boundary'
                assert observed['attributes'][row][-1] == expected
    viewport.set_scrollpos(5)
    assert_viewport(bar, size, 5, width=1)
    for row, start in [(0, 4), (5, 5)]:
        send_mouse(bar, size, [('mouse press', 1, 11, row), ('mouse release', 1, 11, row)], focus=True)
        assert_viewport(bar, size, start, width=1)
        assert viewport.get_scrollpos() == start
    # At a boundary the marker has no further step to make.
    for position, row, start in [(0, 0, 0), (-1, 5, 14)]:
        viewport.set_scrollpos(position)
        assert_viewport(bar, size, start, width=1)
        send_mouse(bar, size, [('mouse press', 1, 11, row), ('mouse release', 1, 11, row)], focus=True)
        assert_viewport(bar, size, start, width=1)
    # Markers take rows from the track; its own end rows still reach the boundaries.
    for row, start in [(4, 14), (1, 0)]:
        send_mouse(bar, size, [('mouse press', 1, 11, row), ('mouse release', 1, 11, row)], focus=True)
        assert_viewport(bar, size, start, width=1)
    for height in (1, 2, 3):
        short = velnora.ScrollBar(velnora.Scrollable(velnora.Text(numbered_content(20))),
                                thumb_char='#', trough_char='.', end_markers=('^', 'v'), attr='plain')
        observed = canvas_snapshot(short.render((12, height)))
        cells = bar_cells(observed)
        if height >= 3:
            assert cells == (b'^', b'#', b'v')
        else:
            assert set(cells) <= {b'#', b'.'} and b'#' in cells
        assert all(row[-1] == 'plain' for row in observed['attributes'])
    # Below three rows there is no marker: the last row is plain track, not a one-row step.
    short = velnora.Scrollable(velnora.Text(numbered_content(20)))
    bar = velnora.ScrollBar(short, thumb_char='#', trough_char='.', end_markers=('^', 'v'))
    assert_viewport(bar, (12, 2), 0, width=1)
    send_mouse(bar, (12, 2), [('mouse press', 1, 11, 1), ('mouse release', 1, 11, 1)], focus=True)
    assert_viewport(bar, (12, 2), 18, width=1)


def test_list_pointer_focus_permission_and_wheel():
    size = (12, 6)
    for options, allowed in [({}, False), ({'scroll_by_focus': False}, False),
                             ({'scroll_by_focus': True}, True)]:
        box = velnora.ListBox(velnora.SimpleFocusListWalker([
            velnora.Edit('', f'item {i:02}', edit_pos=0) for i in range(30)]))
        bar = velnora.ScrollBar(box, thumb_char='#', trough_char='.', **options)
        initial = canvas_snapshot(bar.render(size, focus=True))
        assert box.focus_position == 0
        assert tuple(row[:-1] for row in initial['text']) == tuple(f'item {i:02}'.encode().ljust(11) for i in range(6))
        cells = bar_cells(initial)
        height = cells.count(b'#')
        assert height in (1, 2)
        assert cells == (b'#',) * height + (b'.',) * (6 - height)
        send_mouse(bar, size, [('mouse press', 1, 11, 5)], focus=True)
        observed = canvas_snapshot(bar.render(size, focus=True))
        if allowed:
            assert 0 < box.focus_position < 30
            assert tuple(row[:-1] for row in observed['text']) == tuple(f'item {i:02}'.encode().ljust(11) for i in range(24, 30))
            assert_focused_row(box, (11, 6), f'item {box.focus_position:02}')
        else:
            assert box.focus_position == 0
            assert observed['text'] == initial['text']
        send_mouse(bar, size, [('mouse drag', 1, 11, 0), ('mouse release', 1, 11, 0)], focus=True)
        observed = canvas_snapshot(bar.render(size, focus=True))
        assert box.focus_position == 0
        assert observed['text'] == initial['text']
        send_mouse(bar, size, [('mouse press', 1, 11, 0), ('mouse drag', 1, 11, 5)], focus=True)
        dragged = canvas_snapshot(bar.render(size, focus=True))
        if allowed:
            assert box.focus_position > 0
            assert tuple(row[:-1] for row in dragged['text']) == tuple(f'item {i:02}'.encode().ljust(11) for i in range(24, 30))
            assert_focused_row(box, (11, 6), f'item {box.focus_position:02}')
        else:
            assert box.focus_position == 0
            assert dragged['text'] == initial['text']
        send_mouse(bar, size, [('mouse drag', 1, 11, 0), ('mouse release', 1, 11, 0)], focus=True)
        assert canvas_snapshot(bar.render(size, focus=True))['text'] == initial['text']
        assert box.focus_position == 0
        # Enough wheel actions to move both focus and the actual visible content,
        # over the scrollbar and over the list's own columns.
        for col in (11, 3):
            box.focus_position = 0
            view = canvas_snapshot(bar.render(size, focus=True))
            assert view['text'] == initial['text']
            for _ in range(8):
                send_mouse(bar, size, [('mouse press', 5, col, 2)], focus=True)
                bar.render(size, focus=True)
            after = canvas_snapshot(bar.render(size, focus=True))
            assert box.focus_position > 0
            assert after['text'] != initial['text']
            assert_focused_row(box, (11, 6), f'item {box.focus_position:02}')
            for _ in range(40):
                send_mouse(bar, size, [('mouse press', 4, col, 2)], focus=True)
                bar.render(size, focus=True)
            assert canvas_snapshot(bar.render(size, focus=True))['text'] == initial['text']
        # The thumb follows a list view however it got there.
        box.focus_position = 29
        last = canvas_snapshot(bar.render(size, focus=True))
        assert any(row.startswith(b'item 29') for row in last['text'])
        assert bar_cells(last)[0] == b'.' and b'#' in bar_cells(last)


def test_partially_omitted_scrollbar_styles():
    for options in ({}, {'focus_attr': 'focus-track'}, {'thumb_attr': 'thumb'},
                    {'focus_attr': 'focus-track', 'thumb_attr': 'thumb'},
                    {'thumb_focus_attr': 'focus-thumb'},
                    {'focus_attr': 'focus-track', 'thumb_focus_attr': 'focus-thumb'}):
        viewport = velnora.Scrollable(velnora.Text(numbered_content(30)))
        bar = velnora.ScrollBar(viewport, thumb_char='#', trough_char='.',
                              end_markers=('^', 'v'), attr='track', **options)
        viewport.set_scrollpos(7)
        normal_track = 'track'
        focus_track = options.get('focus_attr', normal_track)
        normal_thumb = options.get('thumb_attr', normal_track)
        focus_thumb = options.get('thumb_focus_attr', options.get('thumb_attr', focus_track))
        for focus in (False, True):
            observed = assert_viewport(bar, (12, 6), 7, focus=focus, width=1)
            cells = bar_cells(observed)
            assert cells[0] == b'^' and cells[-1] == b'v'
            assert b'#' in cells and b'.' in cells
            for row, cell in enumerate(cells):
                expected = (focus_thumb if focus else normal_thumb) if cell == b'#' else (focus_track if focus else normal_track)
                assert observed['attributes'][row][-1] == expected
