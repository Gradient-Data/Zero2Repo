# feature: F09
"""Acceptance tests for responsive containers and public focus navigation."""
import pytest
import velnora

from _helpers import canvas_snapshot, deadline
from F02_helpers import ActionRow, assert_rectangle
from F06_helpers import label_lines
from F09_helpers import sequential_containers


def test_columns_piles_allocation_defaults_and_validation():
    for cls in (velnora.Columns, velnora.Pile):
        first, last = ActionRow(), ActionRow()
        container = cls([velnora.Text('-'), first, last])
        assert container.focus_position == 1
        assert container.focus is first
        passive = cls([velnora.Text('a'), velnora.Text('b')])
        assert passive.focus_position == 0

    columns = velnora.Columns([(4, velnora.SolidFill('A')), ('pack', velnora.Text('BB')),
                             ('weight', 1, velnora.SolidFill('C')),
                             ('weight', 3, velnora.SolidFill('D'))], dividechars=1)
    for width, c_count, d_count in [(24, 3.75, 11.25), (32, 5.75, 17.25)]:
        # Nonintegral shares admit either adjacent whole-cell allocation.
        snap = canvas_snapshot(columns.render((width, 2)))
        assert (snap['cols'], snap['rows']) == (width, 2)
        for row, prefix in zip(snap['text'], (b'AAAA BB ', b'AAAA    ')):
            assert row.startswith(prefix)
            remainder = row[len(prefix):]
            c = remainder.count(b'C')
            d = remainder.count(b'D')
            assert abs(c - c_count) < 1 and abs(d - d_count) < 1
            assert c + d == width - 9
            assert remainder == b'C' * c + b' ' + b'D' * d
    pile = velnora.Pile([(2, velnora.SolidFill('A')), ('pack', velnora.Text('BB\nBB')),
                       ('weight', 1, velnora.SolidFill('C')),
                       ('weight', 3, velnora.SolidFill('D'))])
    for height, c, d in [(12, 2, 6), (16, 3, 9)]:
        assert_rectangle(pile.render((3, height)),
                         [b'AAA'] * 2 + [b'BB '] * 2 + [b'CCC'] * c + [b'DDD'] * d,
                         [[None] * 3] * height)
    implicit = velnora.Columns([velnora.SolidFill('X'), ('weight', 2, velnora.SolidFill('Y'))])
    assert_rectangle(implicit.render((12, 2)), [b'XXXXYYYYYYYY'] * 2, [[None] * 12] * 2)
    implicit_pile = velnora.Pile([velnora.SolidFill('X'), ('weight', 2, velnora.SolidFill('Y'))])
    assert_rectangle(implicit_pile.render((2, 6)), [b'XX'] * 2 + [b'YY'] * 4, [[None] * 2] * 6)
    flow = velnora.Columns([velnora.Text('a\nb'), velnora.Text('c')])
    assert flow.rows((4,)) == 2
    assert label_lines(flow, 4) == ('a c ', 'b   ')
    stacked = velnora.Pile([velnora.Text('a\nb'), velnora.Text(''), velnora.Text('c')])
    assert stacked.rows((3,)) == 4
    assert label_lines(stacked, 3) == ('a  ', 'b  ', '   ', 'c  ')
    minimum = velnora.Columns([velnora.Text('A'), velnora.Text('B'), velnora.Text('C')])
    assert label_lines(minimum, 3) == ('ABC',)
    spaced = velnora.Columns([velnora.Text('A'), velnora.Text('B')], dividechars=2, min_width=3)
    assert label_lines(spaced, 8) == ('A    B  ',)
    assert label_lines(spaced, 7) == ('A      ',)

    for cls, error in ((velnora.Columns, velnora.ColumnsError), (velnora.Pile, velnora.PileError)):
        for kind, amount in [('given', -1), ('given', 1.5), ('weight', -0.5),
                             ('weight', float('inf')), ('weight', float('-inf')),
                             ('weight', float('nan'))]:
            with pytest.raises(error):
                cls([(kind, amount, velnora.Text('bad'))])
        for amount in (-1, 1.5):
            with pytest.raises(error):
                cls([(amount, velnora.Text('bad'))])
        valid = cls([velnora.Text('ok')])
        for kind in ('given', 'weight'):
            valid.contents.append((velnora.Text('zero'), valid.options(kind, 0)))
        assert len(valid.contents) == 3
        for kind, amount in [('given', -1), ('given', 2.5), ('weight', float('nan'))]:
            with pytest.raises(error):
                valid.contents.append((velnora.Text('bad'), valid.options(kind, amount)))
            assert len(valid.contents) == 3


def test_grid_reflow_alignment_gaps_and_initial_focus():
    initial = velnora.GridFlow([velnora.Text('-'), ActionRow(), ActionRow()], 8, 1, 1, 'left')
    assert initial.focus_position == 1
    for align, tail11, tail7 in [('left', 'D   E      ', 'E      '),
                                ('center', '  D   E    ', '  E    '),
                                ('right', '    D   E  ', '    E  ')]:
        grid = velnora.GridFlow([velnora.Text(x) for x in 'ABCDE'], 3, 1, 1, align)
        assert grid.focus_position == 0
        grid.focus_position = 3
        assert label_lines(grid, 11) == ('A   B   C  ', '           ', tail11)
        assert label_lines(grid, 7) == ('A   B  ', '       ', 'C   D  ', '       ', tail7)
        assert label_lines(grid, 2) == ('A ', '  ', 'B ', '  ', 'C ', '  ', 'D ', '  ', 'E ')
        assert grid.focus_position == 3
    # Caller-supplied gaps are honoured as amounts, not treated as on/off switches.
    for h_sep, v_sep, width, expected in [
            (0, 0, 6, ('ABCD  ',)),
            (2, 0, 8, ('A  B  C ', 'D       ')),
            (3, 2, 12, ('A   B   C   ', '            ', '            ', 'D           ')),
            (1, 3, 3, ('A B', '   ', '   ', '   ', 'C D'))]:
        grid = velnora.GridFlow([velnora.Text(x) for x in 'ABCD'], 1, h_sep, v_sep, 'left')
        assert label_lines(grid, width) == expected


    # Integral spare-column proportions avoid imposing a rounding convention.
    for percent in (0, 25, 50, 75, 100):
        grid = velnora.GridFlow([velnora.Text('XYZ')], 3, 1, 0, ('relative', percent))
        left = 12 * percent // 100
        assert label_lines(grid, 15) == (' ' * left + 'XYZ' + ' ' * (12 - left),)


def test_frame_regions_default_focus_and_shortage_priorities():
    frame = velnora.Frame(velnora.SolidFill('B'))
    assert frame.focus_position == 'body'
    assert_rectangle(frame.render((3, 2)), [b'BBB'] * 2, [[None] * 3] * 2)
    frame.header = velnora.Text('H')
    assert_rectangle(frame.render((3, 3)), [b'H  ', b'BBB', b'BBB'], [[None] * 3] * 3)
    frame.header = None
    frame.footer = velnora.Text('F')
    assert_rectangle(frame.render((3, 3)), [b'BBB', b'BBB', b'F  '], [[None] * 3] * 3)
    frame.header = velnora.Edit('', 'H\nH\nH', multiline=True, edit_pos=0)
    frame.footer = velnora.Edit('', 'F\nF', multiline=True, edit_pos=0)
    expected = {
        'header': {4: (b'H  ',) * 3 + (b'F  ',), 2: (b'H  ',) * 2, 1: (b'H  ',)},
        'body': {4: (b'H  ', b'BBB', b'F  ', b'F  '), 2: (b'BBB', b'F  '), 1: (b'BBB',)},
        'footer': {4: (b'H  ', b'H  ', b'F  ', b'F  '), 2: (b'F  ',) * 2, 1: (b'F  ',)},
    }
    for part, heights in expected.items():
        frame.focus_position = part
        assert frame.focus is {'header': frame.header, 'body': frame.body, 'footer': frame.footer}[part]
        full = canvas_snapshot(frame.render((3, 7), focus=True))
        assert full['text'] == (b'H  ',) * 3 + (b'BBB',) * 2 + (b'F  ',) * 2
        for height, text in heights.items():
            snap = canvas_snapshot(frame.render((3, height), focus=True))
            assert (snap['cols'], snap['rows']) == (3, height)
            assert snap['text'] == text


def test_runtime_contents_nested_focus_paths_and_invalid_positions():
    row = velnora.Columns([ActionRow(), ActionRow()])
    pile = velnora.Pile([velnora.Text('heading'), row, ActionRow()])
    frame = velnora.Frame(velnora.Filler(pile, valign='top'), footer=ActionRow())
    assert frame.get_focus_path() == ['body', 1, 0]
    frame.set_focus_path(['body', 1, 1])
    saved = frame.get_focus_path()
    assert saved == ['body', 1, 1]
    frame.set_focus_path(['footer'])
    assert frame.get_focus_path() == ['footer']
    frame.set_focus_path(['body'])
    assert frame.get_focus_path() == saved
    frame.set_focus_path(['body', 2])
    assert frame.get_focus_path() == ['body', 2]
    frame.set_focus_path(saved)
    assert frame.get_focus_path() == saved
    assert row.focus is row.contents[1][0]
    before = canvas_snapshot(frame.render((20, 5), True))
    row.contents[1] = (velnora.Edit('', 'new'), row.options())
    after = canvas_snapshot(frame.render((20, 5), True))
    assert before['text'][1] == b'ready     READY     '
    assert after['text'][1] == b'ready     new       '
    assert after['cursor'] == (13, 1)
    pile.contents.append((velnora.Text('tail'), pile.options('pack')))
    assert canvas_snapshot(frame.render((20, 6), True))['text'][3] == b'tail                '
    del pile.contents[-1]
    assert len(pile.contents) == 3
    grid = velnora.GridFlow([velnora.Text('A'), velnora.Text('B')], 3, 1, 0, 'left')
    grid.contents[1] = (velnora.Text('Z'), grid.options('given', 3))
    assert label_lines(grid, 7) == ('A   Z  ',)
    for container in (row, pile, grid):
        container.focus_position = 1
        assert container.focus_position == 1
        for bad in (-1, len(container.contents)):
            with pytest.raises(IndexError):
                container.focus_position = bad
            assert container.focus_position == 1
    with pytest.raises(IndexError):
        frame.set_focus_path(['body', 1, 20])
    with pytest.raises(IndexError):
        frame.focus_position = 'unknown'
    assert frame.focus_position == 'body'
    # Refusing an absent region leaves the existing focus in place.
    no_header = velnora.Frame(velnora.SolidFill('.'), footer=velnora.Text('f'))
    no_header.focus_position = 'footer'
    assert no_header.focus_position == 'footer'
    no_header.focus_position = 'body'
    with pytest.raises(IndexError):
        no_header.focus_position = 'header'
    assert no_header.focus_position == 'body' and no_header.focus is no_header.body
    frame.contents['header'] = (velnora.Text('top'), frame.options())
    assert frame.header is frame.contents['header'][0]
    assert canvas_snapshot(frame.render((20, 6)))['text'][0] == b'top                 '
    del frame.contents['header']
    for part in ('header', 'footer'):
        missing = velnora.Frame(velnora.SolidFill('.'), focus_part=part)
        assert missing.focus_position == part
        assert missing.focus is None
        assert missing.get_focus_path() == [part]
        with pytest.raises(IndexError):
            missing.focus_position = part
    with pytest.raises(ValueError):
        velnora.Frame(velnora.SolidFill(), focus_part='unknown')


def test_child_first_directional_navigation_and_mouse_coordinates():
    editor = velnora.Edit('', 'ab', edit_pos=0)
    row = velnora.Columns([editor, velnora.Text('-'), ActionRow()], dividechars=1)
    assert row.keypress((26,), 'right') is None
    assert row.focus_position == 0 and editor.edit_pos == 1
    assert row.keypress((26,), 'right') is None
    assert row.focus_position == 0 and editor.edit_pos == 2
    assert row.keypress((26,), 'right') is None
    assert row.focus_position == 2
    assert row.keypress((26,), 'right') == 'right'
    assert row.keypress((26,), 'left') is None
    assert row.focus_position == 0
    editor.set_edit_pos(0)
    assert row.keypress((26,), 'left') == 'left'
    vertical_edit = velnora.Edit('', 'aa\nbb', multiline=True, edit_pos=0)
    pile = velnora.Pile([vertical_edit, velnora.Text('-'), ActionRow()])
    assert pile.keypress((10,), 'down') is None
    assert pile.focus_position == 0 and vertical_edit.edit_pos == 3
    assert pile.keypress((10,), 'down') is None
    assert pile.focus_position == 2
    assert pile.keypress((10,), 'down') == 'down'
    assert pile.keypress((10,), 'up') is None
    assert pile.focus_position == 0
    vertical_edit.set_edit_pos(0)
    assert pile.keypress((10,), 'up') == 'up'
    grid = velnora.GridFlow([ActionRow() for _ in range(4)], 8, 1, 1, 'left')
    for key, destination in [('right', 1), ('down', 3), ('left', 2), ('up', 0)]:
        assert grid.keypress((17,), key) is None
        assert grid.focus_position == destination
    assert grid.keypress((17,), 'up') == 'up'
    skip = velnora.GridFlow([ActionRow(), velnora.Text('-'), ActionRow()], 8, 1, 0, 'left')
    assert skip.keypress((26,), 'right') is None
    assert skip.focus_position == 2
    frame = velnora.Frame(velnora.Filler(ActionRow(), valign='top'), header=ActionRow(), footer=ActionRow())
    for part in ('header', 'body', 'footer'):
        frame.focus_position = part
        assert frame.keypress((10, 6), 'enter') is None
        for key in ('left', 'right', 'up', 'down'):
            assert frame.keypress((10, 6), key) == key
            assert frame.focus_position == part

    target = ActionRow()
    columns = velnora.Columns([(8, ActionRow()), (8, target)], dividechars=2)
    assert columns.mouse_event((18,), 'mouse press', 1, 12, 0, True) is True
    assert columns.focus_position == 1
    assert target.column == 2
    assert target.received[-1][:6] == ('mouse', (8,), 'mouse press', 1, 2, 0)
    assert columns.render((18,), True).cursor == (12, 0)
    target = ActionRow()
    pile = velnora.Pile([velnora.Text('top\nline'), target])
    assert pile.mouse_event((10,), 'mouse press', 1, 4, 2, True) is True
    assert pile.focus_position == 1 and target.column == 4
    assert target.received[-1][1:6] == ((10,), 'mouse press', 1, 4, 0)
    assert pile.render((10,), True).cursor == (4, 2)
    cells = [ActionRow() for _ in range(4)]
    grid = velnora.GridFlow(cells, 8, 1, 1, 'left')
    assert grid.mouse_event((17,), 'mouse press', 1, 12, 2, True) is True
    assert grid.focus_position == 3 and cells[3].column == 3
    assert grid.render((17,), True).cursor == (12, 2)
    body, foot = ActionRow(), ActionRow()
    frame = velnora.Frame(velnora.Filler(body, valign='top'), header=velnora.Text('h\nh'), footer=foot)
    assert frame.mouse_event((10, 6), 'mouse press', 1, 4, 2, True) is True
    assert body.column == 4 and frame.focus_position == 'body'
    assert body.received[-1][1:6] == ((10,), 'mouse press', 1, 4, 0)
    assert frame.mouse_event((10, 6), 'mouse press', 1, 3, 5, True) is True
    assert frame.focus_position == 'footer' and foot.column == 3
    assert frame.render((10, 6), True).cursor == (3, 5)


def test_opt_in_sequential_navigation_and_active_command_rebinding():
    for container, size, first, last in sequential_containers():
        assert container.select_navigation is False
        assert container.focus_position == first
        assert container.keypress(size, 'tab') == 'tab'
        assert container.focus_position == first
        container.select_navigation = True
        assert container.keypress(size, 'tab') is None
        assert container.focus_position == last
        assert container.keypress(size, 'shift tab') is None
        assert container.focus_position == first

    inner = velnora.Columns([ActionRow(), ActionRow()], select_navigation=True)
    outer = velnora.Pile([ActionRow(), inner, ActionRow()], select_navigation=True)
    inner.focus_position = 1
    assert outer.keypress((20,), 'tab') is None
    assert outer.get_focus_path() == [1, 0]
    assert outer.keypress((20,), 'tab') is None
    assert outer.get_focus_path() == [1, 1]
    assert outer.keypress((20,), 'tab') is None
    assert outer.get_focus_path() == [2]
    assert outer.keypress((20,), 'shift tab') is None
    assert outer.get_focus_path() == [1, 1]
    inner.select_navigation = False
    outer.focus_position = 0
    assert outer.keypress((20,), 'tab') is None
    assert outer.get_focus_path() == [1, 1]
    assert outer.keypress((20,), 'tab') is None
    assert outer.get_focus_path() == [2]

    # Entry selects the first or last selectable descendant through every opted-in level.
    deepest = velnora.Columns([velnora.Text('-'), ActionRow(), ActionRow(), velnora.Text('-')],
                            select_navigation=True)
    middle = velnora.Pile([velnora.Text('-'), deepest, velnora.Text('-')], select_navigation=True)
    top = velnora.Pile([ActionRow(), middle, ActionRow()], select_navigation=True)
    middle.focus_position, deepest.focus_position = 2, 3
    assert top.keypress((30,), 'tab') is None
    assert top.get_focus_path() == [1, 1, 1]
    assert top.keypress((30,), 'tab') is None
    assert top.get_focus_path() == [1, 1, 2]
    assert top.keypress((30,), 'tab') is None
    assert top.get_focus_path() == [2]
    middle.focus_position, deepest.focus_position = 0, 0
    assert top.keypress((30,), 'shift tab') is None
    assert top.get_focus_path() == [1, 1, 2]
    assert top.keypress((30,), 'shift tab') is None
    assert top.get_focus_path() == [1, 1, 1]
    assert top.keypress((30,), 'shift tab') is None
    assert top.get_focus_path() == [0]

    saved = dict(velnora.command_map)
    try:
        velnora.command_map['f8'] = 'next selectable'
        velnora.command_map['f9'] = 'prev selectable'
        del velnora.command_map['tab']
        del velnora.command_map['shift tab']
        for container, size, first, last in sequential_containers():
            container.select_navigation = True
            assert container.keypress(size, 'tab') == 'tab'
            assert container.focus_position == first
            assert container.keypress(size, 'f8') is None
            assert container.focus_position == last
            assert container.keypress(size, 'shift tab') == 'shift tab'
            assert container.focus_position == last
            assert container.keypress(size, 'f9') is None
            assert container.focus_position == first
        velnora.command_map.restore_defaults()
        for container, size, first, last in sequential_containers():
            container.select_navigation = True
            assert container.keypress(size, 'f8') == 'f8'
            assert container.focus_position == first
            assert container.keypress(size, 'tab') is None
            assert container.focus_position == last
    finally:
        for key in dict(velnora.command_map):
            del velnora.command_map[key]
        for key, value in saved.items():
            velnora.command_map[key] = value


def test_sequential_edges_mutations_and_finite_wrapping_search():
    for container, size, first, last in sequential_containers():
        container.select_navigation = True
        container.focus_position = last
        assert container.keypress(size, 'tab') == 'tab'
        assert container.focus_position == first
        assert container.keypress(size, 'shift tab') == 'shift tab'
        assert container.focus_position == last
    inner = velnora.Columns([ActionRow(), ActionRow()], select_navigation=True)
    outer = velnora.Pile([inner, ActionRow()], select_navigation=True)
    inner.focus_position = 1
    assert outer.keypress((20,), 'tab') is None
    assert outer.get_focus_path() == [1]
    assert inner.focus_position == 0
    assert outer.keypress((20,), 'tab') == 'tab'
    assert outer.get_focus_path() == [0, 0]
    assert outer.keypress((20,), 'shift tab') == 'shift tab'
    assert outer.get_focus_path() == [1]
    assert outer.keypress((20,), 'shift tab') is None
    assert outer.get_focus_path() == [0, 1]

    placeholder = velnora.WidgetPlaceholder(velnora.Text('passive'))
    pile = velnora.Pile([ActionRow(), placeholder, ActionRow()], select_navigation=True)
    assert pile.keypress((10,), 'tab') is None
    assert pile.focus_position == 2
    placeholder.original_widget = ActionRow()
    assert pile.keypress((10,), 'shift tab') is None
    assert pile.focus_position == 1
    placeholder.original_widget = velnora.WidgetDisable(ActionRow())
    pile.focus_position = 0
    assert pile.keypress((10,), 'tab') is None
    assert pile.focus_position == 2
    pile.contents.append((ActionRow(), pile.options()))
    assert pile.keypress((10,), 'tab') is None
    assert pile.focus_position == 3
    del pile.contents[1]
    assert pile.keypress((10,), 'shift tab') is None
    assert pile.focus_position == 1
    for children in ([ActionRow(), velnora.Text('-'), velnora.WidgetDisable(ActionRow())],
                     [velnora.Text('-'), velnora.Text('passive')]):
        box = velnora.ListBox(velnora.SimpleFocusListWalker(children, wrap_around=True), select_navigation=True)
        for key in ('tab', 'shift tab'):
            with deadline():
                result = box.keypress((10, 4), key)
            assert result == key
            assert box.focus_position == 0


def test_short_containers_preserve_fitting_focus_and_viewport_bounds():
    columns = velnora.Columns([(4, velnora.Edit('', x)) for x in ('AA', 'BB', 'CC')], dividechars=1)
    for position, marker in [(0, b'AA'), (2, b'CC'), (1, b'BB')]:
        columns.focus_position = position
        full = canvas_snapshot(columns.render((14,), True))
        assert full['text'] == (b'AA   BB   CC  ',)
        assert full['cursor'] == (position * 5 + 2, 0)
        for width in (6, 4):
            snap = canvas_snapshot(columns.render((width,), True))
            assert (snap['cols'], snap['rows']) == (width, 1)
            assert snap['cursor'] is not None
            x, y = snap['cursor']
            assert 0 <= x < width and y == 0
            assert snap['text'][0][x - 2:x] == marker
            assert columns.focus_position == position
    for position in (0, 2, 1):
        items = [(2, velnora.SolidFill('A')), (2, velnora.SolidFill('B')), (2, velnora.SolidFill('C'))]
        items[position] = ('weight', 1, velnora.Filler(velnora.Edit('', 'XYZ'), valign='top'))
        pile = velnora.Pile(items, focus_item=position)
        full = canvas_snapshot(pile.render((4, 6), True))
        assert full['text'][position * 2] == b'XYZ '
        for height in (2, 1, 3):
            snap = canvas_snapshot(pile.render((4, height), True))
            assert (snap['cols'], snap['rows']) == (4, height)
            assert snap['cursor'] is not None
            x, y = snap['cursor']
            assert x == 3 and 0 <= y < height
            assert snap['text'][y] == b'XYZ '
            assert pile.focus_position == position
