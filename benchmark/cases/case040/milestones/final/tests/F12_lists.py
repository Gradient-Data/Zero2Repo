# feature: F12
"""Acceptance tests for dynamic lists and hierarchical browsing."""
import pytest
import velnora

from _helpers import canvas_snapshot, send_keys, deadline
from F02_helpers import ActionRow
from F12_helpers import (TokenRows, EstimatedTokenRows, browsing_tree,
                         assert_tree_row, assert_tree_rows, assert_focused_row, CyclicRows)


def test_viewport_navigation_and_cursor():
    body = velnora.SimpleListWalker([velnora.Edit('', f'row {i}', edit_pos=0) for i in range(24)])
    box = velnora.ListBox(body)
    size = (12, 4)
    initial = assert_focused_row(box, size, 'row 0')
    assert initial['text'] == tuple(f'row {i}'.encode().ljust(12) for i in range(4))
    send_keys(box, size, ['down'])
    assert box.focus_position == 1
    assert_focused_row(box, size, 'row 1')
    send_keys(box, size, ['page down'])
    assert box.focus_position > 2
    assert_focused_row(box, size, f'row {box.focus_position}')
    later = box.focus_position
    send_keys(box, size, ['page up'])
    assert later - box.focus_position > 1
    send_keys(box, size, ['down'] * 15)
    assert box.focus_position >= 15
    assert_focused_row(box, size, f'row {box.focus_position}')
    box.set_focus(10)
    box.set_focus_valign('top')
    observed = assert_focused_row(box, size, 'row 10')
    assert observed['text'][0] == b'row 10      '
    box.set_focus_valign('bottom')
    observed = assert_focused_row(box, size, 'row 10')
    assert observed['text'][-1] == b'row 10      '
    tall = velnora.Edit('', 'abcdefghijklmnopqr', edit_pos=17)
    tall_box = velnora.ListBox([velnora.Text('heading'), tall, velnora.Text('tail')])
    tall_box.set_focus(1)
    observed = canvas_snapshot(tall_box.render((6, 2), focus=True))
    x, y = observed['cursor']
    assert x == 5 and 0 <= y < 2
    assert observed['text'][y] == b'mnopqr'
    empty = velnora.ListBox([])
    assert empty.focus is None
    assert empty.body.get_focus() == (None, None)
    observed = canvas_snapshot(empty.render((9, 3), focus=True))
    assert observed['text'] == (b' ' * 9,) * 3
    assert observed['cursor'] is None


def test_dynamic_tokens_and_wrapping():
    provider = TokenRows()
    box = velnora.ListBox(provider)
    size = (16, 3)
    assert_focused_row(box, size, 'item 0')
    send_keys(box, size, ['down'] * 37)
    assert box.focus_position == ('entry', 37)
    assert box.body.get_focus() == provider.get_focus()
    assert_focused_row(box, size, 'item 37')
    box.set_focus(('entry', 103))
    assert_focused_row(box, size, 'item 103')
    send_keys(box, size, ['up'])
    assert box.focus_position == ('entry', 102)
    assert provider.get_next(('entry', 102))[1] == ('entry', 103)
    assert provider.get_prev(('entry', 102))[1] == ('entry', 101)
    assert_focused_row(box, size, 'item 102')
    assert provider.overreach is None, (
        f'the list requested {provider.overreach} from an open-ended provider; '
        f'display and focus movement here reach no further than row {TokenRows.REACH}')
    for cls in (velnora.SimpleListWalker, velnora.SimpleFocusListWalker):
        items = [velnora.Edit('', label, edit_pos=0) for label in ('first', 'last')]
        plain = cls(items)
        plain_box = velnora.ListBox(plain)
        assert_focused_row(plain_box, size, 'first')
        plain.set_focus(1)
        for invalid in (-1, len(items)):
            with pytest.raises(IndexError):
                plain.set_focus(invalid)
            assert plain.get_focus() == (items[1], 1)
        plain.set_focus(0)
        assert plain.get_next(1) == (None, None)
        assert plain.get_prev(0) == (None, None)
        wrapping = cls(items, wrap_around=True)
        wrap_box = velnora.ListBox(wrapping)
        assert wrapping.get_prev(0) == (items[1], 1)
        assert wrapping.get_next(1) == (items[0], 0)
        assert_focused_row(wrap_box, size, 'first')
        send_keys(wrap_box, size, ['up'])
        assert wrap_box.focus_position == 1
        observed = assert_focused_row(wrap_box, size, 'last')
        assert sorted(row.rstrip() for row in observed['text']) == [b'', b'first', b'last']
        send_keys(wrap_box, size, ['down'])
        assert wrap_box.focus_position == 0
        assert_focused_row(wrap_box, size, 'first')

    # Sequential selection shares directional lists' real contents and child dispatch.
    first, last = ActionRow(), ActionRow()
    inner = velnora.Columns([ActionRow(), ActionRow()], select_navigation=True)
    placeholder = velnora.WidgetPlaceholder(velnora.Text('passive'))
    body = velnora.SimpleFocusListWalker([first, placeholder, inner, last])
    box = velnora.ListBox(body)
    assert box.select_navigation is False
    assert box.keypress(size, 'tab') == 'tab'
    assert box.focus_position == 0
    box.select_navigation = True
    assert box.keypress(size, 'tab') is None
    assert box.focus_position == 2 and inner.focus_position == 0
    assert box.keypress(size, 'tab') is None
    assert box.focus_position == 2 and inner.focus_position == 1
    assert box.keypress(size, 'tab') is None
    assert box.focus_position == 3
    assert box.keypress(size, 'tab') == 'tab'
    assert box.focus_position == 0
    assert box.keypress(size, 'shift tab') == 'shift tab'
    assert box.focus_position == 3
    assert box.keypress(size, 'shift tab') is None
    assert box.focus_position == 2 and inner.focus_position == 1
    placeholder.original_widget = ActionRow()
    assert box.keypress(size, 'shift tab') is None
    assert box.focus_position == 2 and inner.focus_position == 0
    assert box.keypress(size, 'shift tab') is None
    assert box.focus_position == 1
    placeholder.original_widget = velnora.WidgetDisable(ActionRow())
    box.focus_position = 0
    assert box.keypress(size, 'tab') is None
    assert box.focus_position == 2
    body.insert(1, ActionRow())
    box.focus_position = 0
    assert box.keypress(size, 'tab') is None
    assert box.focus_position == 1
    del body[1]
    box.focus_position = 0
    assert box.keypress(size, 'tab') is None
    assert box.focus_position == 2
    for provider in (velnora.SimpleListWalker, velnora.SimpleFocusListWalker):
        wrapping = provider([ActionRow(), velnora.Text('-'), ActionRow()], wrap_around=True)
        box = velnora.ListBox(wrapping, select_navigation=True)
        assert box.keypress(size, 'tab') is None
        assert box.focus_position == 2
        assert box.keypress(size, 'tab') == 'tab'
        assert box.focus_position == 0
        assert box.keypress(size, 'shift tab') == 'shift tab'
        assert box.focus_position == 2
    repeating = velnora.ListBox(CyclicRows([ActionRow(), velnora.Text('-'), velnora.Text('--')]),
                             select_navigation=True)
    for key in ('tab', 'shift tab'):
        with deadline():
            result = repeating.keypress(size, key)
        assert result == key
        assert repeating.focus_position == 0


def test_mutations_preserve_or_relocate_focus():
    items = [velnora.Edit('', label, edit_pos=0) for label in ('alpha', 'bravo', 'charlie', 'delta')]
    body = velnora.SimpleFocusListWalker(items)
    box = velnora.ListBox(body)
    box.set_focus(2)
    size = (12, 4)
    assert_focused_row(box, size, 'charlie')
    body.insert(0, velnora.Edit('', 'new', edit_pos=0))
    assert box.body.get_focus() == (items[2], 3)
    assert_focused_row(box, size, 'charlie')
    # Insertion at the focused index and after it also keep the focused item.
    at_focus, after = velnora.Edit('', 'mid', edit_pos=0), velnora.Edit('', 'late', edit_pos=0)
    body.insert(3, at_focus)
    assert box.body.get_focus() == (items[2], 4)
    body.insert(5, after)
    assert box.body.get_focus() == (items[2], 4)
    assert_focused_row(box, size, 'charlie')
    del body[5]
    assert box.body.get_focus() == (items[2], 4)
    del body[3]
    assert box.body.get_focus() == (items[2], 3)
    del body[:2]
    assert box.body.get_focus() == (items[2], 1)
    assert_focused_row(box, size, 'charlie')
    del body[1]
    assert box.body.get_focus() == (items[3], 1)
    assert_focused_row(box, size, 'delta')
    del body[-1]
    assert box.body.get_focus() == (items[1], 0)
    assert_focused_row(box, size, 'bravo')
    body.clear()
    assert box.body.get_focus() == (None, None)
    observed = canvas_snapshot(box.render(size, focus=True))
    assert observed['text'] == (b' ' * size[0],) * size[1]
    assert observed['cursor'] is None


def test_full_height_lists_and_trees():
    widgets = [velnora.Text('one two'), velnora.Text('x\ny\nz'), velnora.Text('tail')]
    finite = velnora.ListBox(velnora.SimpleListWalker(widgets))
    assert velnora.BOX in finite.sizing() and finite.sizing() <= {velnora.BOX, velnora.Sizing.FLOW}
    assert finite.rows((5,)) == 6
    observed = canvas_snapshot(finite.render((5,)))
    assert observed['text'] == (b'one  ', b'two  ', b'x    ', b'y    ', b'z    ', b'tail ')
    assert (observed['cols'], observed['rows']) == (5, 6)
    assert canvas_snapshot(finite.render((5, 2)))['text'] == (b'one  ', b'two  ')
    estimated = velnora.ListBox(EstimatedTokenRows(stop=7))
    assert estimated.rows((12,)) == 7
    observed = canvas_snapshot(estimated.render((12,)))
    assert observed['text'] == tuple(f'item {i}'.encode().ljust(12) for i in range(7))
    assert (observed['cols'], observed['rows']) == (12, 7)
    root = browsing_tree()
    tree = velnora.TreeListBox(velnora.TreeWalker(root))
    assert velnora.BOX in tree.sizing() and tree.sizing() <= {velnora.BOX, velnora.Sizing.FLOW}
    assert tree.rows((32,)) == 8
    observed = canvas_snapshot(tree.render((32,)))
    assert observed['rows'] == 8
    assert_tree_row(observed['text'][-1], root.get_child_node(1).get_child_node(1))
    root.get_child_node(0).get_widget().collapse()
    assert tree.rows((32,)) == 7
    assert canvas_snapshot(tree.render((32,)))['rows'] == 7


def test_tree_expansion_order_and_navigation():
    root = browsing_tree()
    alpha, omega = root.get_child_node(0), root.get_child_node(1)
    a_leaf = alpha.get_child_node(0)
    inner, hidden = omega.get_child_node(0), omega.get_child_node(1)
    deep_one, deep_two = inner.get_child_node(0), inner.get_child_node(1)
    secret = hidden.get_child_node(0)
    walker = velnora.TreeWalker(root)
    box = velnora.TreeListBox(walker)
    size = (32, 12)
    visible = [root, alpha, a_leaf, omega, inner, deep_one, deep_two, hidden]
    assert root.get_widget().expanded and alpha.get_widget().expanded and inner.get_widget().expanded
    assert not hidden.get_widget().expanded
    assert_tree_rows(box, visible)
    assert list(walker.positions()) == visible
    assert list(walker.positions(reverse=True)) == visible[::-1]
    assert walker.get_next(alpha) == (a_leaf.get_widget(), a_leaf)
    assert walker.get_prev(omega) == (a_leaf.get_widget(), a_leaf)
    box.focus_first_child()
    assert box.focus_position is alpha
    send_keys(box, size, ['-'])
    assert not alpha.get_widget().expanded
    assert_tree_rows(box, [root, alpha, omega, inner, deep_one, deep_two, hidden])
    send_keys(box, size, ['right'])
    assert alpha.get_widget().expanded
    send_keys(box, size, ['-','+'])
    assert alpha.get_widget().expanded
    assert_tree_rows(box, visible)
    # Click the application indicator at its public indentation column.
    assert box.mouse_event(size, 'mouse press', 1, alpha.get_widget().get_indent_cols(), 1, True)
    assert not alpha.get_widget().expanded
    assert_tree_rows(box, [root, alpha, omega, inner, deep_one, deep_two, hidden])
    assert box.mouse_event(size, 'mouse press', 1, alpha.get_widget().get_indent_cols(), 1, True)
    assert alpha.get_widget().expanded
    # Only the primary button toggles; the handled status of other buttons is not promised.
    box.mouse_event(size, 'mouse press', 3, alpha.get_widget().get_indent_cols(), 1, True)
    assert alpha.get_widget().expanded
    assert_tree_rows(box, visible)
    box.set_focus(inner)
    send_keys(box, size, ['left'])
    assert box.focus_position is omega
    box.focus_first_child()
    assert box.focus_position is inner
    box.focus_end(size)
    assert box.focus_position is hidden
    hidden.get_widget().expand()
    box.focus_end(size)
    assert box.focus_position is secret.get_child_node(0)
    hidden.get_widget().collapse()
    omega.get_widget().collapse()
    box.focus_home(size)
    box.focus_end(size)
    assert box.focus_position is omega
    omega.get_widget().expand()
    inner.get_widget().collapse()
    box.focus_home(size)
    box.focus_end(size)
    assert box.focus_position is omega.get_child_node(1)
    inner.get_widget().expand()
    box.set_focus(deep_two)
    inner.get_widget().collapse()
    assert box.focus_position is deep_two
    assert box.focus.get_node().get_value()[0] == 'deep-two'
    # Observe hiding independently from the retained, now hidden focus.
    assert_tree_rows(velnora.TreeListBox(velnora.TreeWalker(root)), [root, alpha, a_leaf, omega, inner, omega.get_child_node(1)])
