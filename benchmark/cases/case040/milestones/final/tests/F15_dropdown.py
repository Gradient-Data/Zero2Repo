# feature: F15
"""Acceptance tests for ordered, styled drop-down selection."""
import pytest
import velnora

from _helpers import canvas_snapshot, send_keys, send_mouse
from F01_helpers import encoding_state
from F15_helpers import selection_scene, selection_view, assert_closed_selection


def test_configuration_order_selection_and_rejection():
    options = [('warm', 'Amber'), 'Birch', [('cool', 'Cobalt'), ' stone']]
    labels = ['Amber', 'Birch', 'Cobalt stone']
    control = velnora.DropDown(iter(options))
    assert list(control.options) == options
    assert control.selected == 0
    assert canvas_snapshot(control.render(()))['text'][0].startswith(b'Amber')
    explicit = velnora.DropDown(options, selected=2, max_visible_items=1)
    assert explicit.selected == 2
    assert canvas_snapshot(explicit.render(()))['text'][0].startswith(b'Cobalt stone')
    for index in (1, 2, 0):
        control.selected = index
        assert control.selected == index
        assert canvas_snapshot(control.render(()))['text'][0].startswith(labels[index].encode())
    refused = []
    velnora.connect_signal(control, 'change', lambda widget, index: refused.append(index))
    for invalid in (-1, len(options)):
        with pytest.raises(IndexError):
            velnora.DropDown(options, selected=invalid)
        before = canvas_snapshot(control.render(()))['text']
        with pytest.raises(IndexError):
            control.selected = invalid
        assert control.selected == 0
        assert canvas_snapshot(control.render(()))['text'] == before
        assert refused == []
    with pytest.raises(ValueError):
        velnora.DropDown([])
    for limit in (0, -2):
        with pytest.raises(ValueError):
            velnora.DropDown(options, max_visible_items=limit)
    singleton = velnora.DropDown(['Only'], max_visible_items=1)
    assert singleton.selected == 0
    assert canvas_snapshot(singleton.render(()))['text'][0].startswith(b'Only')


def test_open_focus_scrolling_limits_and_anchored_placement():
    options = [f'choice-{index:02d}' for index in range(17)]
    size = (24, 23)
    # The omitted limit measures the default; explicit limits measure both a
    # shorter viewport and its smallest valid boundary, without a cross product.
    for config, limit in (({}, 10), ({'max_visible_items': 4}, 4),
                          ({'max_visible_items': 1}, 1)):
        control = velnora.DropDown(options, selected=12, **config)
        target = selection_scene(control, column=2, row=2)
        assert_closed_selection(target, size, options[12], column=2, row=2)
        assert send_keys(target, size, ['enter']) == (None,)
        opened = selection_view(target, size)
        visible = [line[2:11] for line in opened['text'][3:3 + limit]]
        assert len(visible) == limit
        assert all(label in [item.encode() for item in options] for label in visible)
        assert options[12].encode() in visible
        assert all(line == b' ' * size[0] for line in opened['text'][3 + limit:])
        # Activating immediately proves the original selection had focus.
        assert send_keys(target, size, ['enter']) == (None,)
        assert control.selected == 12
        assert_closed_selection(target, size, options[12], column=2, row=2)
        assert send_mouse(target, size, [('mouse press', 1, 3, 2)], focus=True) == (True,)
        selection_view(target, size)
        for _ in range(4):
            assert send_keys(target, size, ['down']) == (None,)
            scrolled = selection_view(target, size)
        assert options[-1].encode() in [line[2:11] for line in scrolled['text'][3:3 + limit]]
        assert send_keys(target, size, ['enter']) == (None,)
        assert control.selected == len(options) - 1
        assert_closed_selection(target, size, options[-1], column=2, row=2)
        assert send_keys(target, size, ['enter']) == (None,)
        for _ in range(len(options) - 1):
            send_keys(target, size, ['up'])
            selection_view(target, size)
        assert send_keys(target, size, ['enter']) == (None,)
        assert control.selected == 0
        assert_closed_selection(target, size, options[0], column=2, row=2)
        # A click means the option shown on that row, wherever the list has scrolled to.
        control.selected = 12
        send_keys(target, size, ['enter'])
        opened = selection_view(target, size)
        row = 3 + limit - 1
        if opened['text'][row][2:11] == options[12].encode():
            row = 3
        shown = opened['text'][row][2:11].decode()
        if limit > 1:
            assert shown != options[12]
        assert send_mouse(target, size, [('mouse press', 1, 3, row)], focus=True) == (True,)
        assert control.selected == options.index(shown)
        assert_closed_selection(target, size, shown, column=2, row=2)

    # Only a primary click opens the list.
    control = velnora.DropDown(['place-0', 'place-1'])
    target = selection_scene(control)
    size = (24, 6)
    closed = assert_closed_selection(target, size, 'place-0')
    send_mouse(target, size, [('mouse press', 3, 1, 0)], focus=True)
    assert selection_view(target, size)['text'] == closed['text']

    # Below fits, above fits, and neither side fits: exercise the drop-down's
    # own anchoring through the containing target, not geometry helpers.
    for height, row, count, top, shown in ((11, 1, 4, 2, 4),
                                          (11, 9, 4, 5, 4),
                                          (9, 3, 8, 4, 5),
                                          (9, 6, 8, 0, 6)):
        labels = [f'place-{index}' for index in range(count)]
        control = velnora.DropDown(labels)
        target = selection_scene(control, column=2, row=row)
        size = (24, height)
        closed = assert_closed_selection(target, size, labels[0], column=2, row=row)
        send_keys(target, size, ['enter'])
        opened = selection_view(target, size)
        assert [line[2:9] for line in opened['text'][top:top + shown]] == [
            label.encode() for label in labels[:shown]]
        assert opened['text'][row] == closed['text'][row]
        for y in set(range(height)) - set(range(top, top + shown)) - {row}:
            assert opened['text'][y] == closed['text'][y]
        send_keys(target, size, ['esc'])
        assert selection_view(target, size)['text'] == closed['text']


def test_commit_cancel_and_change_notification_timing():
    labels = ['Aspen', 'Beech', 'Cedar', 'Dogwood']
    control = velnora.DropDown(labels)
    target = selection_scene(control)
    size = (22, 9)
    events = []

    def changed(widget, new_index):
        events.append((widget is control, widget.selected, new_index))

    velnora.connect_signal(control, 'change', changed)
    assert_closed_selection(target, size, labels[0])
    send_keys(target, size, [' '])
    opened = selection_view(target, size)
    assert opened['text'][1].startswith(b'Aspen')
    send_keys(target, size, ['down', 'down', 'enter'])
    assert control.selected == 2
    assert events == [(True, 0, 2)]
    assert_closed_selection(target, size, labels[2])

    send_keys(target, size, ['enter'])
    assert selection_view(target, size)['text'][4].startswith(b'Dogwood')
    send_keys(target, size, ['up', 'esc'])
    assert control.selected == 2
    assert events == [(True, 0, 2)]
    assert_closed_selection(target, size, labels[2])

    send_mouse(target, size, [('mouse press', 1, 1, 0)], focus=True)
    assert selection_view(target, size)['text'][2].startswith(b'Beech')
    assert send_mouse(target, size, [('mouse press', 1, 1, 2)], focus=True) == (True,)
    assert control.selected == 1
    assert events == [(True, 0, 2), (True, 2, 1)]
    assert_closed_selection(target, size, labels[1])

    control.selected = 3
    assert control.selected == 3
    assert events == [(True, 0, 2), (True, 2, 1), (True, 1, 3)]
    assert_closed_selection(target, size, labels[3])
    control.selected = 3
    assert events == [(True, 0, 2), (True, 2, 1), (True, 1, 3)]
    assert_closed_selection(target, size, labels[3])
    # A programmatic change is what the next opening focuses.
    control.selected = 1
    send_keys(target, size, ['enter'])
    selection_view(target, size)
    send_keys(target, size, ['down', 'enter'])
    assert control.selected == 2
    assert_closed_selection(target, size, labels[2])
    events.clear()
    # The list opens on the current selection, whatever earlier openings did.
    def interact(*keys):
        for key in keys:
            assert send_keys(target, size, [key]) == (None,)
            selection_view(target, size)

    interact('enter', 'up', 'up', 'esc', 'enter', 'enter')
    assert control.selected == 2
    assert events == []
    assert_closed_selection(target, size, labels[2])
    interact('enter', 'down', 'enter')
    assert control.selected == 3
    interact('enter', 'up', 'enter')
    assert control.selected == 2
    assert events == [(True, 2, 3), (True, 3, 2)]
    # Choosing the option already selected closes the list and sends nothing.
    send_keys(target, size, ['enter'])
    selection_view(target, size)
    send_mouse(target, size, [('mouse press', 1, 1, 3)], focus=True)
    assert control.selected == 2
    assert events == [(True, 2, 3), (True, 3, 2)]
    assert_closed_selection(target, size, labels[2])


def test_stable_natural_width_ellipsis_and_option_attributes():
    with encoding_state():
        velnora.set_encoding('utf-8')
        options = [('short', 'Oak'), [('first', 'Extra'), ('second', 'ordinary branch')],
                   ('last', 'Pine')]
        labels = ['Oak', 'Extraordinary branch', 'Pine']
        control = velnora.DropDown(options)
        natural = control.pack()
        indicator = canvas_snapshot(control.drop_down_indicator.render(()))
        assert any(line.strip() for line in indicator['text'])
        assert natural[1] == 1
        assert natural[0] >= len(labels[1]) + indicator['cols']
        for index, attributes in ((0, ['short'] * 3),
                                  (1, ['first'] * 5 + ['second'] * 15),
                                  (2, ['last'] * 4)):
            control.selected = index
            assert control.pack() == natural
            view = canvas_snapshot(control.render(()))
            assert (view['cols'], view['rows']) == natural
            assert view['text'][0].startswith(labels[index].encode())
            assert view['text'][0][len(labels[index]):].strip()
            assert view['text'][0].endswith(indicator['text'][0])
            assert list(view['attributes'][0][:len(labels[index])]) == attributes
            assert view['text'][0][len(labels[index]):].strip()
        control.selected = 1
        narrow = canvas_snapshot(control.render((10,)))
        assert (narrow['cols'], narrow['rows']) == (10, 1)
        text = narrow['text'][0].decode('utf-8')
        assert text.startswith(labels[1][0])
        # Both common omission-marker spellings express the promised ellipsis;
        # the opening indicator's glyph is deliberately not specified.
        assert '…' in text or '...' in text
        assert labels[1] not in text
        assert narrow['attributes'][0][0] == 'first'
        # A label that fits the narrower width has nothing to omit.
        control.selected = 0
        fitting = canvas_snapshot(control.render((10,)))['text'][0].decode('utf-8')
        assert fitting.startswith(labels[0])
        # The indicator's own glyph is unspecified, so only the label area is read.
        label_area = fitting.removesuffix(indicator['text'][0].decode('utf-8'))
        assert '…' not in label_area and '...' not in label_area
        control.selected = 1
        assert control.pack() == natural
        assert canvas_snapshot(control.render(()))['text'][0].startswith(labels[1].encode())

        target = selection_scene(control, width=natural[0])
        size = (natural[0] + 3, 8)
        send_keys(target, size, ['enter'])
        opened = selection_view(target, size)
        for y, label, attrs in ((1, labels[0], ['short'] * 3),
                                (2, labels[1], ['first'] * 5 + ['second'] * 15),
                                (3, labels[2], ['last'] * 4)):
            assert opened['text'][y].startswith(label.encode())
            assert list(opened['attributes'][y][:len(label)]) == attrs
        send_keys(target, size, ['down', 'enter'])
        assert control.selected == 2
        closed = assert_closed_selection(target, size, labels[2])
        assert closed['attributes'][0][:4] == ('last',) * 4
