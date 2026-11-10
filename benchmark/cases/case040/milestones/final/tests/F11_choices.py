# feature: F11
"""Acceptance tests for buttons, choice controls and selectable labels."""
import pytest
import velnora

from _helpers import CallbackRecorder, canvas_snapshot, send_keys
from F01_helpers import encoding_state
from F06_helpers import label_lines
from F11_helpers import ChoiceObserver


def test_button_activation_and_live_command_bindings():
    clicks = CallbackRecorder()
    button = velnora.Button('Upload', on_press=clicks, user_data='document')
    listener = CallbackRecorder()
    velnora.connect_signal(button, 'click', listener)
    assert button.get_label() == 'Upload'
    assert 'Upload' in ''.join(label_lines(button, 24))
    for key in ('enter', ' '):
        previous = len(clicks.calls)
        assert button.keypress((24,), key) is None
        assert clicks.calls[previous:] == [((button, 'document'), {})]
        assert listener.calls[previous:] == [((button,), {})]
    previous = len(clicks.calls)
    assert button.mouse_event((24,), 'mouse press', 1, 5, 0, True) is True
    assert clicks.calls[previous:] == [((button, 'document'), {})]
    assert listener.calls[previous:] == [((button,), {})]
    previous = list(clicks.calls)
    previous_listener = list(listener.calls)
    # Only the primary button activates.
    for other_button in (2, 3):
        button.mouse_event((24,), 'mouse press', other_button, 5, 0, True)
    assert button.keypress((24,), 'x') == 'x'
    assert clicks.calls == previous
    assert listener.calls == previous_listener

    saved = dict(velnora.command_map)
    try:
        velnora.command_map['f8'] = 'activate'
        del velnora.command_map['enter']
        del velnora.command_map[' ']
        previous = len(clicks.calls)
        assert send_keys(button, (24,), ('enter', ' ', 'f8')) == ('enter', ' ', None)
        assert clicks.calls[previous:] == [((button, 'document'), {})]
        assert listener.calls[previous:] == [((button,), {})]
        velnora.command_map.restore_defaults()
        previous = len(clicks.calls)
        assert send_keys(button, (24,), ('f8', 'enter', ' ')) == ('f8', None, None)
        assert clicks.calls[previous:] == [((button, 'document'), {})] * 2
        assert listener.calls[previous:] == [((button,), {})] * 2
    finally:
        for key in dict(velnora.command_map):
            del velnora.command_map[key]
        for key, action in saved.items():
            velnora.command_map[key] = action


def test_checkbox_cycles_display_assignment_and_notifications():
    checkbox = velnora.CheckBox('Archive')
    observer = ChoiceObserver(checkbox)
    assert checkbox.state is False
    displays = {}
    # Establish all three observable state displays without pinning mark glyphs.
    for state in (False, True, 'mixed'):
        checkbox.set_state(state)
        assert checkbox.get_state() == state
        displays[state] = label_lines(checkbox, 24)
        assert 'Archive' in ''.join(displays[state])
    assert len(set(displays.values())) == 3
    checkbox.set_state(False)
    observer.events.clear()
    for old, new, key in ((False, True, 'enter'), (True, False, ' ')):
        assert checkbox.keypress((24,), key) is None
        assert checkbox.state is new
        assert observer.events == [(checkbox, 'before', new, old),
                                   (checkbox, 'after', old, new)]
        assert label_lines(checkbox, 24) == displays[new]
        observer.events.clear()
    for old, new in ((False, True), (True, 'mixed'), ('mixed', False)):
        checkbox.state = new
        assert checkbox.get_state() == new
        assert observer.events == [(checkbox, 'before', new, old),
                                   (checkbox, 'after', old, new)]
        assert label_lines(checkbox, 24) == displays[new]
        observer.events.clear()
    checkbox.set_state('mixed')
    observer.events.clear()
    assert checkbox.keypress((24,), 'enter') is None
    assert checkbox.state is False
    assert observer.events == [(checkbox, 'before', False, 'mixed'),
                               (checkbox, 'after', 'mixed', False)]
    observer.events.clear()
    checkbox.set_state(False)
    assert checkbox.state is False
    assert observer.events == []
    checkbox.set_state(True, do_callback=False)
    assert checkbox.state is True
    assert label_lines(checkbox, 24) == displays[True]
    assert observer.events == []
    with pytest.raises(velnora.CheckBoxError):
        checkbox.set_state('invalid choice')
    assert checkbox.state is True
    assert observer.events == []
    checkbox.set_label('Retain')
    assert checkbox.get_label() == 'Retain'
    rendered = ''.join(label_lines(checkbox, 24))
    assert 'Retain' in rendered
    assert 'Archive' not in rendered
    assert checkbox.state is True

    three_state = velnora.CheckBox('Preview', has_mixed=True)
    three_observer = ChoiceObserver(three_state)
    assert three_state.state is False
    three_displays = [label_lines(three_state, 24)]
    for old, new in ((False, True), (True, 'mixed'), ('mixed', False)):
        assert three_state.keypress((24,), ' ') is None
        assert three_state.state == new
        assert three_observer.events == [(three_state, 'before', new, old),
                                         (three_state, 'after', old, new)]
        three_observer.events.clear()
        three_displays.append(label_lines(three_state, 24))
    assert len(set(three_displays[:3])) == 3
    assert three_displays[3] == three_displays[0]


def test_radio_group_exclusivity_and_choice_notifications():
    group = []
    first = velnora.RadioButton(group, 'Local')
    second = velnora.RadioButton(group, 'Remote')
    third = velnora.RadioButton(group, 'Mirror')
    assert [w.state for w in (first, second, third)] == [True, False, False]
    observer = ChoiceObserver(first, second, third)
    assert second.keypress((24,), 'enter') is None
    assert [w.state for w in (first, second, third)] == [False, True, False]
    # Per-control ordering is promised; inter-control callback ordering is not.
    for widget, old, new in ((first, True, False), (second, False, True)):
        assert [event for event in observer.events if event[0] is widget] == [
            (widget, 'before', new, old), (widget, 'after', old, new)]
    assert all(event[0] is not third for event in observer.events)
    observer.events.clear()
    assert second.keypress((24,), ' ') is None
    second.set_state(True)
    assert [w.state for w in (first, second, third)] == [False, True, False]
    assert observer.events == []

    third.state = True
    assert [w.state for w in (first, second, third)] == [False, False, True]
    for widget, old, new in ((second, True, False), (third, False, True)):
        assert [event for event in observer.events if event[0] is widget] == [
            (widget, 'before', new, old), (widget, 'after', old, new)]
    assert all(event[0] is not first for event in observer.events)
    later = velnora.RadioButton(group, 'Offline')
    assert [w.state for w in (first, second, third, later)] == [False, False, True, False]
    observer.events.clear()
    # Suppression is measured on the directly changed control; clearing it
    # does not trigger an indirect change in another member.
    third.set_state(False, do_callback=False)
    assert [w.state for w in (first, second, third, later)] == [False] * 4
    assert observer.events == []
    first.set_state(True)
    assert [w.state for w in (first, second, third, later)] == [True, False, False, False]
    assert observer.events == [(first, 'before', True, False),
                               (first, 'after', False, True)]
    separate = []
    other = velnora.RadioButton(separate, 'Independent')
    assert other.state is True
    assert [w.state for w in (first, second, third, later)] == [True, False, False, False]
    # Suppression affects only the directly assigned member, including indirect deselection.
    observer.events.clear()
    second.set_state(True, do_callback=False)
    assert [w.state for w in (first, second, third, later)] == [False, True, False, False]
    assert observer.events == [(first, 'before', False, True), (first, 'after', True, False)]
    first.set_state(True)
    # Selecting a member through a selection does not leave another member selected.
    observer.events.clear()
    later_observer = ChoiceObserver(later)
    assert later.keypress((24,), 'enter') is None
    assert [w.state for w in (first, second, third, later)] == [False, False, False, True]
    assert observer.events == [(first, 'before', False, True), (first, 'after', True, False)]
    assert later_observer.events == [(later, 'before', True, False), (later, 'after', False, True)]
    # Exclusivity holds whatever the members' order of addition.
    later_observer.events.clear()
    assert second.keypress((24,), 'enter') is None
    assert [w.state for w in (first, second, third, later)] == [False, True, False, False]
    assert later_observer.events == [(later, 'before', False, True), (later, 'after', True, False)]


def test_selectable_icon_attributes_cursor_visibility_and_unhandled_keys():
    icon = velnora.SelectableIcon([('accent', 'Orbit'), '!'], cursor_position=4, wrap='clip')
    assert icon.selectable() is True
    unfocused = canvas_snapshot(icon.render((10,), focus=False))
    focused = canvas_snapshot(icon.render((10,), focus=True))
    assert focused['text'] == unfocused['text'] == (b'Orbit!    ',)
    assert focused['attributes'][0][:6] == ('accent',) * 5 + (None,)
    assert unfocused['attributes'][0][:6] == focused['attributes'][0][:6]
    assert focused['cursor'] == (4, 0)
    assert unfocused['cursor'] is None
    clipped = canvas_snapshot(icon.render((3,), focus=True))
    assert clipped['text'] == (b'Orb',)
    assert clipped['attributes'][0] == ('accent',) * 3
    assert clipped['cursor'] is None
    # Re-render after clipping and focus changes to catch stale cursor results.
    assert canvas_snapshot(icon.render((10,), focus=True))['cursor'] == (4, 0)
    wrapped = velnora.SelectableIcon('abcdef', cursor_position=4, wrap='any')
    snapshot = canvas_snapshot(wrapped.render((3,), focus=True))
    assert snapshot['text'] == (b'abc', b'def')
    assert snapshot['cursor'] == (1, 1)
    # The position counts characters, so a preceding wide character shifts the column.
    with encoding_state():
        velnora.set_encoding('utf-8')
        wide = velnora.SelectableIcon('界a', cursor_position=1)
        assert canvas_snapshot(wide.render((6,), focus=True))['cursor'] == (2, 0)
    assert send_keys(icon, (10,), ('enter', ' ', 'left', 'x')) == ('enter', ' ', 'left', 'x')
