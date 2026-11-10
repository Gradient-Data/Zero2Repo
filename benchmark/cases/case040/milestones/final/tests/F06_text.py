# feature: F06
"""Acceptance tests for attributed labels and text layout."""
from os.path import commonprefix

import pytest
import velnora
from velnora.display.raw import Screen
from velnora import TagMarkupException
from velnora import TextError

from _helpers import canvas_snapshot
from F01_helpers import encoding_state, expanded_runs
from F03_helpers import resolved_render
from F06_helpers import VerticalLabelLayout, label_lines


def test_attributed_content_replacement_and_invalid_markup():
    with encoding_state():
        velnora.set_encoding('utf-8')
        screen = Screen()
        screen.register_palette([('outer', 'dark red', 'default'),
                                 ('inner', 'dark green', 'default')])
        label = velnora.Text('plain')
        assert label.get_text()[0] == 'plain'
        assert all(a is None for a in expanded_runs(label.get_text()[1]))
        assert label_lines(label, 7) == ('plain  ',)
        label.set_text(('outer', ['A', '', ('inner', ['BC', '', ('outer', 'D')]), [], 'E']))
        text, spans = label.get_text()
        assert text == 'ABCDE'
        attributes = expanded_runs(spans)
        assert len(attributes) == len(text)
        assert tuple(screen.resolve_attr(a, 0).foreground_number for a in attributes) == (1, 2, 2, 1, 1)
        text, attrs = resolved_render(screen, label, 5)
        assert text == (b'ABCDE',)
        assert tuple(a.foreground_number for a in attrs[0]) == (1, 2, 2, 1, 1)
        label.set_text(['', [], ('inner', ''), 'new'])
        assert label.get_text()[0] == 'new'
        assert all(a is None for a in expanded_runs(label.get_text()[1]))
        assert label_lines(label, 5) == ('new  ',)
        for control in ('\a', '\r', '\x7f'):
            for byte_text in (False, True):
                source = 'A' + control + 'B' + control + 'C'
                fragments = [('outer', source[:3]), ('inner', source[3:])]
                if byte_text:
                    fragments = [(attr, content.encode('utf-8')) for attr, content in fragments]
                label.set_text(fragments)
                original, spans = label.get_text()
                assert original == (source.encode('utf-8') if byte_text else source)
                assert expanded_runs(spans) == ('outer',) * 3 + ('inner',) * 2
                observed = canvas_snapshot(label.render((6,)))
                assert observed['text'] == (b'ABC   ',)
                assert observed['attributes'] == (('outer', 'outer', 'inner', None, None, None),)
        label.set_text([('outer', 'keep'), '!'])
        for malformed in [('outer',), (), ('outer', 'x', 'extra'), 23, ['ok', {'bad': 'value'}],
                          ('outer', ['ok', ('inner',)]), ('outer', ['ok', ('inner', 7)]),
                          ['ok', ['deep', 3.5]], ('outer', None)]:
            with pytest.raises(TagMarkupException):
                velnora.Text(malformed)
            with pytest.raises(TagMarkupException):
                label.set_text(malformed)
            # A refused replacement leaves the previous content and spans in place.
            text, spans = label.get_text()
            assert text == 'keep!'
            cells = expanded_runs(spans)
            assert len(cells) <= len(text)
            assert cells + (None,) * (len(text) - len(cells)) == ('outer',) * 4 + (None,)
            observed = canvas_snapshot(label.render((6,)))
            assert observed['text'] == (b'keep! ',)
            assert observed['attributes'] == (('outer',) * 4 + (None, None),)


def test_alignment_wrapping_and_width_changes():
    with encoding_state():
        velnora.set_encoding('utf-8')
        label = velnora.Text('red blue')
        assert label_lines(label, 6) == ('red   ', 'blue  ')
        assert label_lines(label, 9) == ('red blue ',)
        assert label_lines(label, 6) == ('red   ', 'blue  ')
        for align, expected in [('left', 'cat    '), ('center', '  cat  '), ('right', '    cat')]:
            assert label_lines(velnora.Text('cat', align=align), 7) == (expected,)
        centered = label_lines(velnora.Text('cat', align='center'), 6)[0]
        assert centered.strip(' ') == 'cat'
        assert abs(len(centered) - len(centered.lstrip(' ')) - (len(centered) - len(centered.rstrip(' ')))) <= 1
        for content, width, options, expected in [
            ('red blue', 6, {'wrap': 'space'}, ('red   ', 'blue  ')),
            # Words that fit together share a row; a space-break is not shown.
            ('a bb ccc dddd', 6, {}, ('a bb  ', 'ccc   ', 'dddd  ')),
            # Alignment applies to every displayed row, not only the first.
            ('red blue', 6, {'align': 'right'}, ('   red', '  blue')),
            ('a\nbb', 3, {'align': 'right'}, ('  a', ' bb')),
            ('red blue', 6, {'wrap': 'any'}, ('red bl', 'ue    ')),
            ('abcdefgh', 3, {'wrap': 'space'}, ('abc', 'def', 'gh ')),
            ('e\u0301界Z', 3, {'wrap': 'any'}, ('e\u0301界', 'Z  ')),
            ('a\n\nb\n', 3, {}, ('a  ', '   ', 'b  ', '   ')),
            ('abcdefgh', 4, {'wrap': 'clip'}, ('abcd',)),
            ('abcdefgh', 4, {'wrap': 'clip', 'align': 'right'}, ('efgh',)),
            ('abcdefgh', 4, {'wrap': 'clip', 'align': 'center'}, ('cdef',)),
            ('A界BC', 2, {'wrap': 'clip'}, ('A ',)),
            ('AB界C', 2, {'wrap': 'clip', 'align': 'right'}, (' C',)),
        ]:
            assert label_lines(velnora.Text(content, **options), width) == expected
        source = 'abcdefgh'
        ellipsis = velnora.Text(source, wrap='ellipsis')
        assert label_lines(ellipsis, 9) == (source + ' ',)
        clipped = label_lines(ellipsis, 4)
        assert len(clipped) == 1
        # The omission marker's spelling is not prescribed; require retained
        # source content followed by a visible replacement for the omitted suffix.
        shown = clipped[0].rstrip(' ')
        prefix = commonprefix([source, shown])
        assert 0 < len(prefix) < len(source)
        assert shown[len(prefix):]


def test_tabs_bound_to_labels_and_validation():
    with encoding_state():
        velnora.set_encoding('utf-8')
        assert label_lines(velnora.Text('A\tB'), 12) == ('A       B   ',)
        for stops, interval, content, width, wrap, expected in [
            ((3, 10), 4, 'a\tb\tc\td', 16, 'clip', ('a  b      c d   ',)),
            ((3,), 0, 'a\tb\tc', 10, 'clip', ('a  bc     ',)),
            ((), 0, 'a\tb', 5, 'clip', ('ab   ',)),
            ((), 4, '界\tX', 8, 'clip', ('界  X   ',)),
            ((), 8, 'ab\tZ', 5, 'clip', ('ab   ',)),
            ((), 8, 'a\tbcd', 5, 'any', ('a    ', 'bcd  ')),
            ((), 4, 'a\tword', 6, 'space', ('a     ', 'word  ')),
            ((), 4, 'a\tb\nc\td', 7, 'clip', ('a   b  ', 'c   d  ')),
        ]:
            layout = velnora.StandardTextLayout(tab_stops=stops, tab_stop_every=interval)
            assert label_lines(velnora.Text(content, wrap=wrap, layout=layout), width) == expected
        for options in [{'tab_stop_every': -1}, {'tab_stops': [0]}, {'tab_stops': [3, -2]}]:
            with pytest.raises(ValueError):
                velnora.StandardTextLayout(**options)


def test_custom_layout_rendering_and_editor_correspondence():
    layout = VerticalLabelLayout()
    label = velnora.Text('MOP', layout=layout)
    assert label_lines(label, 6) == ('  M   ', '  O   ', '  P   ')
    editor = velnora.Edit('', 'MOP', layout=layout)
    for position, expected in [(0, (2, 0)), (1, (2, 1)), (2, (2, 2)), (3, (3, 2))]:
        editor.set_edit_pos(position)
        assert editor.get_cursor_coords((6,)) == expected
        rendered = canvas_snapshot(editor.render((6,), focus=True))
        assert rendered['text'] == (b'  M   ', b'  O   ', b'  P   ')
        assert rendered['cursor'] == expected
    assert editor.mouse_event((6,), 'mouse press', 1, 2, 1, True)
    assert editor.edit_pos == 1
    assert editor.get_cursor_coords((6,)) == (2, 1)
    assert editor.keypress((6,), 'X') is None
    assert editor.edit_text == 'MXOP'
    assert label_lines(editor, 6, True) == ('  M   ', '  X   ', '  O   ', '  P   ')


def test_unsupported_layout_choices_are_refused():
    label = velnora.Text('valid')
    assert label_lines(label, 7) == ('valid  ',)
    for option, method in [('align', 'set_align_mode'), ('wrap', 'set_wrap_mode')]:
        with pytest.raises(TextError):
            velnora.Text('valid', **{option: 'unsupported'})
        with pytest.raises(TextError):
            getattr(label, method)('unsupported')
        # The refused choice leaves the label's previous layout in force.
        assert label_lines(label, 7) == ('valid  ',)
        assert label_lines(label, 3) == ('val', 'id ')
    label.set_align_mode('right')
    label.set_wrap_mode('clip')
    assert label_lines(label, 7) == ('  valid',)
    assert label_lines(label, 3) == ('lid',)
