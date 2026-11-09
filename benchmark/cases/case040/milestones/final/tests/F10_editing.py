# feature: F10
"""Acceptance tests for text and numeric editing through public widgets."""
from decimal import Decimal, InvalidOperation, localcontext, ROUND_DOWN, ROUND_UP

import pytest
import velnora
from velnora.numedit import IntegerEdit, FloatEdit

from _helpers import canvas_snapshot, send_keys
from F01_helpers import encoding_state
from F06_helpers import label_lines, VerticalLabelLayout


def test_text_editing_clusters_and_displayed_cursor():
    with encoding_state():
        velnora.set_encoding('utf-8')
        editor = velnora.Edit('ID: ', 'abc')
        assert editor.edit_pos == 3
        assert label_lines(editor, 12, True) == ('ID: abc     ',)
        assert canvas_snapshot(editor.render((12,), focus=True))['cursor'] == (7, 0)
        editor = velnora.Edit('ID: ', 'ab', edit_pos=1)
        assert editor.keypress((12,), 'X') is None
        assert (editor.caption, editor.edit_text, editor.edit_pos) == ('ID: ', 'aXb', 2)
        # Each sequence is one cluster, not merely one code point.
        for cluster in ['e\u0301', '界', '👩\u200d💻', '🇨🇦']:
            editor = velnora.Edit('ID: ', 'A' + cluster + 'Z', edit_pos=1)
            assert editor.keypress((20,), 'right') is None
            assert editor.edit_pos == 1 + len(cluster)
            assert editor.keypress((20,), 'left') is None
            assert editor.edit_pos == 1
            assert editor.keypress((20,), 'delete') is None
            assert (editor.caption, editor.edit_text, editor.edit_pos) == ('ID: ', 'AZ', 1)
            editor.set_edit_text('A' + cluster + 'Z')
            editor.set_edit_pos(1 + len(cluster))
            assert editor.keypress((20,), 'backspace') is None
            assert (editor.edit_text, editor.edit_pos) == ('AZ', 1)
        editor = velnora.Edit('', 'abcdefghij', wrap='any', edit_pos=1)
        assert editor.get_cursor_coords((4,)) == (1, 0)
        assert editor.keypress((4,), 'down') is None
        assert (editor.edit_pos, editor.get_cursor_coords((4,))) == (5, (1, 1))
        assert editor.keypress((4,), 'home') is None
        assert editor.edit_pos == 4
        assert editor.keypress((4,), 'end') is None
        assert editor.edit_pos == 7
        assert editor.keypress((4,), 'up') is None
        assert editor.get_cursor_coords((4,)) == (3, 0)
        assert editor.mouse_event((4,), 'mouse press', 1, 2, 2, True)
        assert (editor.edit_pos, editor.get_cursor_coords((4,))) == (10, (2, 2))
        editor = velnora.Edit('ID: ', 'ab', edit_pos=0)
        assert editor.keypress((12,), 'backspace') == 'backspace'
        assert (editor.caption, editor.edit_text) == ('ID: ', 'ab')
        # Clicks are measured on the display, so the caption width is not text.
        editor = velnora.Edit('ID: ', 'abcdef', edit_pos=0)
        assert editor.mouse_event((20,), 'mouse press', 1, 6, 0, True)
        assert editor.edit_pos == 2
        assert editor.get_cursor_coords((20,)) == (6, 0)


def test_multiline_tabs_and_masking():
    editor = velnora.Edit('P: ', 'ab')
    assert send_keys(editor, (20,), ['enter', 'tab']) == ('enter', 'tab')
    assert editor.edit_text == 'ab'
    editor = velnora.Edit('P: ', 'ab', multiline=True, allow_tab=True)
    assert send_keys(editor, (20,), ['enter', 'x', 'tab']) == (None, None, None)
    assert (editor.edit_text, editor.edit_pos) == ('ab\nx       ', 11)
    literal = velnora.Edit('', 'ab', allow_tab=True, expand_tabs=False)
    assert literal.keypress((20,), 'tab') is None
    assert (literal.edit_text, literal.edit_pos) == ('ab\t', 3)
    masked = velnora.Edit('P: ', 'secret', mask='*')
    assert label_lines(masked, 12, True) == ('P: ******   ',)
    assert masked.edit_text == 'secret'
    assert masked.keypress((12,), 'X') is None
    assert masked.edit_text == 'secretX'
    assert label_lines(masked, 12, True) == ('P: *******  ',)
    masked.set_mask(None)
    assert label_lines(masked, 12, True) == ('P: secretX  ',)


def test_change_notifications_and_programmatic_redraw():
    editor = velnora.Edit('P: ', 'old')
    events = []
    velnora.connect_signal(editor, 'change', lambda source, proposed: events.append(('before', source, proposed, source.edit_text)))
    velnora.connect_signal(editor, 'postchange', lambda source, previous: events.append(('after', source, previous, source.edit_text)))
    assert label_lines(editor, 12) == ('P: old      ',)
    assert editor.keypress((12,), '!') is None
    assert events == [('before', editor, 'old!', 'old'), ('after', editor, 'old', 'old!')]
    assert label_lines(editor, 12) == ('P: old!     ',)
    events.clear()
    # Deletions are text changes too and notify with the same ordering.
    assert editor.keypress((12,), 'backspace') is None
    assert events == [('before', editor, 'old', 'old!'), ('after', editor, 'old!', 'old')]
    events.clear()
    editor.set_edit_pos(0)
    assert editor.keypress((12,), 'delete') is None
    assert events == [('before', editor, 'ld', 'old'), ('after', editor, 'old', 'ld')]
    assert label_lines(editor, 12) == ('P: ld       ',)
    events.clear()
    editor.set_edit_text('old!')
    events.clear()
    editor.set_edit_text('new')
    assert events == [('before', editor, 'new', 'old!'), ('after', editor, 'old!', 'new')]
    assert editor.edit_text == 'new'
    assert label_lines(editor, 12) == ('P: new      ',)


def test_numeric_typed_alphabets_and_signs():
    for factory in [velnora.IntEdit, IntegerEdit, FloatEdit]:
        editor = factory()
        assert send_keys(editor, (30,), '39') == (None, None)
        assert editor.value() == 39
        for key in ['a', '-', '/']:
            before = editor.edit_text
            assert editor.keypress((30,), key) == key
            assert editor.edit_text == before
    for factory in [velnora.IntEdit, FloatEdit]:
        for ch in '0123456789':
            editor = factory()
            editor.set_edit_text('1')
            editor.set_edit_pos(1)
            assert editor.keypress((30,), ch) is None
            assert editor.edit_text == '1' + ch
            assert editor.value() == int('1' + ch)
    digits = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    for base in range(2, 37):
        editor = IntegerEdit(base=base)
        for ch in digits[:base] + digits[10:base].lower():
            editor.set_edit_text('1')
            editor.set_edit_pos(1)
            assert editor.keypress((30,), ch) is None
            assert editor.edit_text == '1' + ch
            assert editor.value() == Decimal(base + int(ch, 36))
        for ch in digits[base:] + '?':
            before = editor.edit_text
            assert editor.keypress((30,), ch) == ch
            assert editor.edit_text == before
    for options, separator in [({}, '.'), ({'decimal_separator': ','}, ',')]:
        editor = FloatEdit(**options)
        assert send_keys(editor, (30,), ['2', separator, '5']) == (None, None, None)
        assert editor.value() == Decimal('2.5')
        for key in [separator, ',' if separator == '.' else '.']:
            assert editor.keypress((30,), key) == key
            assert editor.edit_text == '2' + separator + '5'
    for factory in [IntegerEdit, FloatEdit]:
        editor = factory(allow_negative=True)
        assert send_keys(editor, (30,), ['-', '4']) == (None, None)
        assert editor.value() == -4
        assert editor.keypress((30,), '-') == '-'
        editor.set_edit_pos(0)
        assert editor.keypress((30,), '-') == '-'
        assert editor.edit_text == '-4'
        editor.set_edit_text('4')
        editor.set_edit_pos(1)
        assert editor.keypress((30,), '-') == '-'
        assert editor.edit_text == '4'
        # At the beginning of existing unsigned digits the sign is accepted.
        editor.set_edit_pos(0)
        assert editor.keypress((30,), '-') is None
        assert editor.edit_text == '-4' and editor.value() == -4
    for factory in [IntegerEdit, FloatEdit]:
        editor = factory('', '4')
        editor.set_edit_pos(0)
        assert editor.keypress((30,), '-') == '-'
        assert editor.edit_text == '4' and editor.value() == 4
    # A decimal initial value in a comma field already holds its one separator.
    editor = FloatEdit('', Decimal('3.25'), decimal_separator=',')
    assert editor.value() == Decimal('3.25')
    for key in [',', '.']:
        assert editor.keypress((30,), key) == key
        assert editor.value() == Decimal('3.25')


def test_numeric_initial_values_empty_and_invalid_conversions():
    assert velnora.IntEdit().value() == 0
    assert velnora.IntEdit('', '').value() == 0
    for factory in [IntegerEdit, FloatEdit]:
        assert factory().value() is None
        assert factory('', '').value() is None
    for text, base, expected in [('10101', 2, 21), ('aF', 16, 175), ('Z', 36, 35), ('-21', 10, -21)]:
        assert IntegerEdit('', text, base=base, allow_negative=True).value() == expected
    for initial in [42, Decimal('42')]:
        assert IntegerEdit('', initial).value() == 42
    for text, options in [('2', {'base': 2}), ('-2', {}), ('-', {'allow_negative': True}), ('hello', {}), ('1.5', {})]:
        with pytest.raises(ValueError):
            IntegerEdit('', text, **options)
    for initial, options in [('3.25', {}), ('3,25', {'decimal_separator': ','}), (Decimal('3.25'), {}), (3, {})]:
        assert FloatEdit('', initial, **options).value() == Decimal(str(initial).replace(',', '.'))
    for initial, options in [('bad', {}), ('1,2', {}), ('1.2', {'decimal_separator': ','}), (Decimal('NaN'), {}), (Decimal('Infinity'), {}), ('-Infinity', {}), ('NaN', {})]:
        with pytest.raises(ValueError):
            FloatEdit('', initial, **options)
    with pytest.raises(ValueError):
        FloatEdit(decimal_separator=':')
    basic = velnora.IntEdit('', 'bad')
    assert basic.edit_text == 'bad'
    with pytest.raises(ValueError):
        basic.value()
    for factory, failure in [(velnora.IntEdit, ValueError), (IntegerEdit, ValueError), (FloatEdit, InvalidOperation)]:
        editor = factory()
        editor.set_edit_text('bad')
        assert editor.edit_text == 'bad'
        with pytest.raises(failure):
            editor.value()
    for factory, key, failure in [(IntegerEdit, '-', ValueError), (FloatEdit, '-', InvalidOperation), (FloatEdit, '.', InvalidOperation)]:
        editor = factory(allow_negative=True)
        assert editor.keypress((20,), key) is None
        assert editor.edit_text == key
        with pytest.raises(failure):
            editor.value()


def test_decimal_significance_and_active_rounding():
    for initial in ['1.20', Decimal('1.20')]:
        for rounding in [ROUND_DOWN, ROUND_UP]:
            editor = FloatEdit('', initial)
            assert send_keys(editor, (30,), '17') == (None, None)
            with localcontext() as context:
                context.rounding = rounding
                expected = Decimal('1.2017').quantize(Decimal('0.01'))
                actual = editor.value()
                assert isinstance(actual, Decimal)
                assert actual == expected
                assert actual.as_tuple().exponent == -2
            editor.set_edit_text('7')
            assert editor.value().as_tuple() == Decimal('7.00').as_tuple()
    # Significance also comes from comma-separated initial text and other exponents.
    for initial, options, text, exponent in [('1,20', {'decimal_separator': ','}, '7,555', '0.01'),
                                             ('3.125', {}, '7.5', '0.001'),
                                             (Decimal('2.5'), {}, '7.55', '0.1')]:
        for rounding in [ROUND_DOWN, ROUND_UP]:
            editor = FloatEdit('', initial, **options)
            editor.set_edit_text(text)
            with localcontext() as context:
                context.rounding = rounding
                expected = Decimal(text.replace(',', '.')).quantize(Decimal(exponent))
                assert editor.value().as_tuple() == expected.as_tuple()
    for initial, options in [(2, {}), (None, {}), ('1.20', {'preserve_significance': False}), (Decimal('1.2000'), {'preserve_significance': False})]:
        editor = FloatEdit('', initial, **options)
        editor.set_edit_text('9.87600')
        assert editor.value().as_tuple() == Decimal('9.87600').as_tuple()


def test_leading_zeros_clamping_and_unhandled_boundaries():
    for factory in [velnora.IntEdit, IntegerEdit, FloatEdit]:
        editor = factory('', '5002')
        assert send_keys(editor, (20,), ['home', 'delete']) == (None, None)
        assert (editor.edit_text, editor.edit_pos) == ('002', 0)
        assert editor.keypress((20,), 'end') is None
        assert (editor.edit_text, editor.edit_pos) == ('2', 1)
        editor.set_edit_text('00')
        editor.set_edit_pos(2)
        assert editor.keypress((20,), 'left') is None
        assert (editor.edit_text, editor.edit_pos) == ('0', 0)
        editor.set_edit_text('00')
        editor.set_edit_pos(2)
        assert editor.keypress((20,), '4') is None
        assert (editor.edit_text, editor.edit_pos) == ('4', 1)
    for separator in ['.', ',']:
        editor = FloatEdit('', '00' + separator + '5', decimal_separator=separator)
        assert editor.keypress((20,), 'end') is None
        assert editor.edit_text == '0' + separator + '5'
    editor = IntegerEdit('', '000A', base=16)
    assert editor.keypress((20,), 'end') is None
    assert (editor.edit_text, editor.edit_pos) == ('000A', 4)
    for base, text in [(2, '0011'), (8, '0017'), (36, '00Z')]:
        editor = IntegerEdit('', text, base=base)
        assert send_keys(editor, (20,), ['home', 'end']) == (None, None)
        assert (editor.edit_text, editor.edit_pos) == (text, len(text))
        assert editor.value() == int(text, base)
    # Only leading zeros before the cursor are redundant; inner zeros stay.
    for factory in [velnora.IntEdit, IntegerEdit, FloatEdit]:
        editor = factory('', '1002')
        assert send_keys(editor, (20,), ['home', 'end']) == (None, None)
        assert editor.edit_text == '1002'
    for factory in [velnora.IntEdit, IntegerEdit]:
        editor = factory('', '0012')
        editor.set_edit_pos(2)
        assert editor.keypress((20,), 'left') is None
        assert (editor.edit_text, editor.edit_pos) == ('012', 0)
    # Zeros between a sign and the digits are the number's leading zeros.
    editor = IntegerEdit('', '-007', allow_negative=True)
    assert editor.keypress((20,), 'left') is None
    assert (editor.edit_text, editor.value()) == ('-7', -7)
    editor = velnora.Edit('P: ', 'abc')
    for position, expected in [(-50, 0), (50, 3)]:
        editor.set_edit_pos(position)
        assert editor.edit_pos == expected
        assert editor.get_cursor_coords((20,)) == (3 + expected, 0)
    for position, keys in [(0, ['left', 'backspace', 'up']), (3, ['right', 'delete', 'down'])]:
        for key in keys:
            editor.set_edit_pos(position)
            assert editor.keypress((20,), key) == key
            assert (editor.caption, editor.edit_text, editor.edit_pos) == ('P: ', 'abc', position)


def test_tab_insertion_bound_to_editable_explicit_line():
    with encoding_state():
        velnora.set_encoding('utf-8')
        for text, position, stops, interval, expected, final_pos in [
            ('ab', 2, (), 8, 'ab      ', 8),
            ('long\nx', 6, (4, 9), 0, 'long\nx   ', 9),
            ('界\txZ', 3, (4, 9), 0, '界\tx    Z', 7),
            ('abcdef', 6, (), 8, 'abcdef  ', 8),
            ('abcd', 4, (4,), 0, 'abcd', 4),
        ]:
            layout = velnora.StandardTextLayout(tab_stops=stops, tab_stop_every=interval)
            editor = velnora.Edit('CAPTION: ', text, edit_pos=position, allow_tab=True, multiline=True, layout=layout)
            assert editor.keypress((5,), 'tab') is None
            assert (editor.edit_text, editor.edit_pos) == (expected, final_pos)
        editor = velnora.Edit('CAP: ', 'ab', allow_tab=True, layout=VerticalLabelLayout())
        assert editor.keypress((20,), 'tab') is None
        assert (editor.edit_text, editor.edit_pos) == ('ab      ', 8)
        editor = velnora.Edit('CAP: ', '界', allow_tab=True, expand_tabs=False,
                            layout=velnora.StandardTextLayout(tab_stops=(), tab_stop_every=0))
        assert editor.keypress((20,), 'tab') is None
        assert (editor.edit_text, editor.edit_pos) == ('界\t', 2)
