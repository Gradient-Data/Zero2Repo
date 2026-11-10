# feature: F05
"""Acceptance tests for configurable keyboard commands."""
import pytest
import velnora


def test_default_bindings_and_unmapped_keys():
    commands = velnora.CommandMap()
    expected = {
        'up': 'cursor up', 'down': 'cursor down',
        'left': 'cursor left', 'right': 'cursor right',
        'page up': 'cursor page up', 'page down': 'cursor page down',
        'home': 'cursor max left', 'end': 'cursor max right',
        ' ': 'activate', 'enter': 'activate',
        'tab': 'next selectable', 'ctrl n': 'next selectable',
        'shift tab': 'prev selectable', 'ctrl p': 'prev selectable',
        'esc': 'menu', 'ctrl l': 'redraw screen',
    }
    enumerated = dict(commands)
    for key, action in expected.items():
        assert commands[key] == action
        assert enumerated[key] == action
    for key in ('f8', 'ctrl x'):
        assert commands[key] is None


def test_single_key_changes_action_clear_copy_and_restore():
    commands = velnora.CommandMap()
    defaults = dict(commands)
    expected = defaults.copy()
    for key, action in (('s', 'save document'), ('ctrl s', 'save document'),
                        ('f8', 'preview document'), ('up', 'preview document')):
        commands[key] = action
        expected[key] = action
        assert dict(commands) == expected

    independent = commands.copy()
    assert dict(independent) == expected
    independent['s'] = 'publish document'
    del independent['down']
    copy_expected = {**expected, 's': 'publish document'}
    del copy_expected['down']
    assert dict(independent) == copy_expected
    assert independent['down'] is None
    assert dict(commands) == expected

    del commands['s']
    del expected['s']
    assert commands['s'] is None
    assert dict(commands) == expected
    commands['f8'] = None
    del expected['f8']
    assert commands['f8'] is None
    assert dict(commands) == expected
    # Clear multiple aliases, retaining unrelated bindings.
    commands.clear_command('activate')
    expected = {key: action for key, action in expected.items() if action != 'activate'}
    assert dict(commands) == expected
    assert commands[' '] is None
    assert commands['enter'] is None
    commands.clear_command('save document')
    del expected['ctrl s']
    assert commands['ctrl s'] is None
    assert dict(commands) == expected
    assert dict(independent) == copy_expected

    commands.restore_defaults()
    assert dict(commands) == defaults
    for key in ('s', 'ctrl s', 'f8'):
        assert commands[key] is None
    assert dict(independent) == copy_expected
    independent.restore_defaults()
    assert dict(independent) == defaults

    # Restored mappings stay independent of each other and of later new maps.
    commands['up'] = 'preview document'
    del commands['down']
    commands['f7'] = 'save document'
    commands.clear_command('menu')
    assert commands['up'] == 'preview document'
    assert commands['down'] is None and commands['esc'] is None
    assert dict(independent) == defaults
    assert dict(velnora.CommandMap()) == defaults
    commands.restore_defaults()
    assert dict(commands) == defaults
    assert commands['f7'] is None


def test_batch_binding_conflicts_are_atomic_and_reassignment_is_explicit():
    commands = velnora.CommandMap()
    expected = dict(commands)
    commands.bind('save document', 's', 'ctrl s')
    expected.update({'s': 'save document', 'ctrl s': 'save document'})
    assert dict(commands) == expected
    commands.bind('save document', 's', 'f8')
    expected['f8'] = 'save document'
    assert dict(commands) == expected
    commands.bind('cursor up', 'up', 'k')
    expected['k'] = 'cursor up'
    assert dict(commands) == expected

    # Put unbound keys before and after the conflict to expose partial writes.
    with pytest.raises(ValueError):
        commands.bind('save document', 'f9', 'up', 'f10')
    assert dict(commands) == expected
    assert commands['f9'] is None
    assert commands['f10'] is None
    with pytest.raises(ValueError):
        commands.bind('preview document', 'p', 'ctrl s', 'ctrl p')
    assert dict(commands) == expected
    assert commands['p'] is None

    for key in ('f9', 'up', 'f10'):
        commands[key] = 'save document'
        expected[key] = 'save document'
        assert dict(commands) == expected
    commands.bind('save document', 'up', 'f9', 'f10')
    assert dict(commands) == expected
