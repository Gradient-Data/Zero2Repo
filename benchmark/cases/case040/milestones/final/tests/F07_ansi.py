# feature: F07
"""Acceptance observations for captured terminal text, through public entries."""
import velnora
from velnora.ansi_parser import AnsiParser, parse_ansi_line, parse_ansi_text
from F01_helpers import encoding_state
from F03_helpers import EFFECTS, effect_flags, is_default_attr, resolved_render
from F06_helpers import label_lines
from F07_helpers import ansi_attribute_cells
from _helpers import canvas_snapshot


def test_multirow_cursor_resolution():
    # Vectors observed on the original, not a second terminal implementation.
    vectors = [
        ('abcdef\rXY', 'XYcdef'),
        ('ab\ncd\x1b[A\x1b[CX', 'ab X\ncd'),
        ('abc\x1b[2DX', 'aXc'), ('abc\x1b[0GX', 'Xbc'),
        ('abc\x1b[2;4HZ', 'abc\n   Z'), ('a\x1b[BZ', 'a\n Z'),
        ('abc\nxy\x1b[FX', 'Xbc\nxy'),
        ('abc\x1b[99D\x1b[99AX', 'Xbc'), ('a\x1b[0CZ', 'a Z'),
        ('ab\x1b[2dZ', 'ab\n  Z'), ('a\x1b[2EZ', 'a\n\nZ'),
        ('a\x1b[2;3fZ', 'a\n  Z'), ('a\x1b[0H!', '!'),
        # Counts other than one are honoured for every relative move.
        ('ab\ncd\nef\x1b[2AX', 'abX\ncd\nef'), ('ab\ncd\nef\x1b[2FX', 'Xb\ncd\nef'),
        ('abc\x1b[DX', 'abX'), ('a\nb\x1b[0AX', 'aX\nb'), ('a\nb\x1b[0FX', 'X\nb'),
        ('a\x1b[0EX', 'a\nX'), ('ab\ncd\x1b[A\x1b[2CX\x1b[2CY', 'ab  X  Y\ncd'),
        ('\x1b[;3HX', '  X'), ('a\nb\x1b[2;HX', 'a\nX'), ('abcd\x1b[GX', 'Xbcd'),
        ('ab\ncd\x1b[A\rX\nY', 'Xb\nYd'),
    ]
    with encoding_state():
        velnora.set_encoding('utf-8')
        for source, expected in vectors:
            result = parse_ansi_text(source)
            parser = AnsiParser()
            parser.feed(source)
            assert parser.finalize()[0].text == expected
            assert result.text == expected
            assert ansi_attribute_cells(result) == (None,) * len(expected)
            assert label_lines(velnora.ANSIText(source), 12) == tuple(
                row.ljust(12) for row in expected.split('\n'))


def test_line_splitting_and_widgets():
    source = 'a\r\nb\n\rc\rd\n'
    assert [r.text for r in parse_ansi_line(source)] == ['a', 'b', 'c', 'd', '']
    assert [r.text for r in parse_ansi_line('')] == ['']
    assert parse_ansi_text('').text == ''
    source = 'a\x1b[2BZ\nb\x1b[Hc\n'
    results = parse_ansi_line(source)
    assert [r.text for r in results] == ['aZ', 'bc', '']
    assert [[(o.kind, o.raw) for o in r.skipped] for r in results] == [
        [('vertical-move', '\x1b[2B')], [('vertical-move', '\x1b[H')], []]
    with encoding_state():
        velnora.set_encoding('utf-8')
        assert label_lines(velnora.ANSIText(source, one_line=True), 4) == ('aZ  ',)
        widgets = list(velnora.ANSIText.from_lines([source], one_line=True))
        assert [w.text for w in widgets] == ['aZ', 'bc', '']
        assert [label_lines(w, 4) for w in widgets] == [('aZ  ',), ('bc  ',), ('    ',)]
        assert [w.text for w in velnora.ANSIText.from_lines([''], one_line=True)] == ['']


def test_incremental_controls_and_state():
    chunks = ['\x1b[3', '1mA\x1b]8;id=chunk;', 'https://example.org', '\x1b',
              '\\B\x1b(', '0q\r', '\nq\x1b[0', 'm', 'q\x1b]8;;\a\x1b(BZ']
    source = ''.join(chunks)
    for one_line, expected in [(False, ['AB─\n──Z']), (True, ['AB─', '──Z'])]:
        parser = AnsiParser(one_line=one_line)
        for chunk in chunks:
            parser.feed(chunk)
        actual = parser.finalize()
        complete = AnsiParser(one_line=one_line)
        complete.feed(source)
        together = complete.finalize()
        assert [r.text for r in actual] == expected
        assert [r.text for r in together] == expected
        widgets = list(velnora.ANSIText.from_lines(chunks, one_line=one_line))
        assert [w.text for w in widgets] == expected
        for left, right, widget in zip(actual, together, widgets):
            assert ansi_attribute_cells(left) == ansi_attribute_cells(right) == ansi_attribute_cells(widget)
        attrs = [a for r in actual for a in ansi_attribute_cells(r)]
        # Independent content and active-state checks prevent a closed-loop oracle.
        assert attrs[0].foreground_number == 1
        assert attrs[0].hyperlink is None
        assert attrs[1].hyperlink.uri == 'https://example.org'
        assert attrs[1].hyperlink.id == 'chunk'
        last_attrs = ansi_attribute_cells(actual[-1])
        assert last_attrs[-2].hyperlink.uri == 'https://example.org'
        assert not any(effect_flags(last_attrs[-2]))
        assert last_attrs[-1] is None


def test_controls_and_side_reports():
    assert parse_ansi_text('abc\bX').text == 'abX'
    # Backspace keeps the text it passes over; tabs stop at every eighth column.
    assert parse_ansi_text('abc\b\bX').text == 'aXc'
    assert parse_ansi_text('abc\b').text == 'abc'
    assert parse_ansi_text('abcdefghij\tX').text == 'abcdefghij      X'
    assert parse_ansi_text('        ij\r\tX').text == '        Xj'
    assert parse_ansi_text('a\tZ\tQ').text == 'a       Z       Q'
    for code, state in [(0, 'clear'), (1, 'scroll_lock'), (2, 'num_lock'), (3, 'caps_lock')]:
        assert parse_ansi_text(f'\x1b[{code}qZ').leds == state
    # An unrecognised request clears the LED observation.
    assert parse_ansi_text('\x1b[3q\x1b[99qZ').leds is None
    source = '\a\x1b]0;old\a\x1b]2;new\x1b\\\x1b[2qA\nB\n\a\a\x1b]2;\a\x1b[0qC'
    lines = parse_ansi_line(source)
    assert [(r.text, r.bel, r.title, r.leds) for r in lines] == [
        ('A', 1, 'new', 'num_lock'), ('B', 0, None, None), ('C', 2, '', 'clear')]
    result = parse_ansi_text(source)
    assert (result.text, result.bel, result.title, result.leds) == ('A\nB\nC', 3, '', 'clear')


def test_unsupported_and_unknown_operations():
    # Each required operation family is observed; no free-form explanation is pinned.
    controls = ['\x1b[2J', '\x1b[K', '\x1b[1;3r', '\x1b[s', '\x1b[u',
                '\x1b[?25h', '\x1b[?25l', '\x1b[@', '\x1b[L', '\x1b[M',
                '\x1b[P', '\x1b[X', '\x1b[c', '\x1b[6n', '\x1b[g',
                '\x1b7', '\x1b8', '\x1bH']
    source = 'abc' + ''.join(controls) + '\x1b[42zZ'
    for parse in (parse_ansi_line, lambda text: (parse_ansi_text(text),)):
        result = parse(source)[0]
        assert result.text == 'abcZ'
        assert all(isinstance(op.reason, str) and op.reason.strip() for op in result.skipped)
        assert [(o.kind, o.raw) for o in result.skipped] == [
            *(('terminal-setting', raw) for raw in controls), ('unknown', '\x1b[42z')]
    # With the cursor inside existing text, none of these operations mutates it:
    # no erase, deletion, insertion, scrolling or cursor restoration takes effect.
    base = 'abcd\nefgh\x1b[A\x1b[2D'
    for control in ['\x1b[K', '\x1b[1K', '\x1b[2K', '\x1b[J', '\x1b[1J', '\x1b[2J',
                    '\x1b[P', '\x1b[2P', '\x1b[X', '\x1b[3X', '\x1b[@', '\x1b[2@',
                    '\x1b[L', '\x1b[M']:
        result = parse_ansi_text(base + control + 'Z')
        assert result.text == 'abZd\nefgh'
        assert [(o.kind, o.raw) for o in result.skipped] == [('terminal-setting', control)]
        line = parse_ansi_line('abcd\x1b[2D' + control + 'Z')
        assert [r.text for r in line] == ['abZd']
        assert [(o.kind, o.raw) for o in line[0].skipped] == [('terminal-setting', control)]
    for source, expected, raws in [
            ('abcd\x1b[s\x1b[2DX\x1b[uY', 'abXY', ['\x1b[s', '\x1b[u']),
            ('abcd\x1b7\x1b[2DX\x1b8Y', 'abXY', ['\x1b7', '\x1b8']),
            ('  \x1bH\r\tZ', '        Z', ['\x1bH']),
            ('  \x1b[3g\r\tZ', '        Z', ['\x1b[3g']),
            ('ab\ncd\x1b[1;2r\x1b[3BZ', 'ab\ncd\n\n\n  Z', ['\x1b[1;2r'])]:
        result = parse_ansi_text(source)
        assert result.text == expected
        assert [(o.kind, o.raw) for o in result.skipped] == [('terminal-setting', raw) for raw in raws]


def test_movement_and_control_length_limits():
    for source, expected in [
        ('a\x1b[999999CX', 'a' + ' ' * 1024 + 'X'),
        ('\x1b[999999GX', ' ' * 1023 + 'X'),
        ('\x1b[999999dX', '\n' * 1023 + 'X'),
        ('\x1b[999999BX', '\n' * 1024 + 'X'),
        ('\x1b[999999;999999HX', '\n' * 1023 + ' ' * 1023 + 'X')]:
        assert parse_ansi_text(source).text == expected
    accepted = parse_ansi_text('\x1b[' + '0' * 253 + '31mX')
    assert ansi_attribute_cells(accepted)[0].foreground_number == 1
    assert accepted.skipped == []
    raw = '\x1b[' + '0' * 254 + '31m'
    rejected = parse_ansi_text(raw + 'X\x1b[32mY')
    assert rejected.text == 'XY'
    assert [(o.kind, o.raw) for o in rejected.skipped] == [('unknown', raw)]
    assert ansi_attribute_cells(rejected)[0] is None
    assert ansi_attribute_cells(rejected)[1].foreground_number == 2
    # The accepted OSC body boundary is inclusive.
    for size in (4095, 4096, 4097):
        body = '2;' + 't' * (size - 2)
        result = parse_ansi_text('A\x1b]' + body + '\aB\x1b[4mC')
        assert result.text == 'ABC'
        assert ansi_attribute_cells(result)[-1].underline
        if size <= 4096:
            assert result.title == body[2:]
            assert result.skipped == []
        else:
            assert result.title is None
            assert [o.kind for o in result.skipped] == ['unknown']


def test_report_retention_scope_and_order():
    controls = ['\x1b[2J'] + ['\x1b[K'] * 65534 + ['\x1b[6n', '\x1b[42z']
    source = ''.join(controls) + '\n\x1b[3gZ'
    lines = parse_ansi_line(source)
    assert [r.text for r in lines] == ['', 'Z']
    assert [o.raw for o in lines[0].skipped] == controls[:65536]
    assert [(o.kind, o.raw) for o in lines[1].skipped] == [('terminal-setting', '\x1b[3g')]
    block = parse_ansi_text(source)
    assert block.text == '\nZ'
    assert [o.raw for o in block.skipped] == controls[:65536]


def test_padding_allowance_and_curtailed_placement():
    # Reference-observed exact allowance: 1,048,576 + 8 * 7,588 = 1,109,280.
    # Both arms have the same length; only the requested gap differs by one.
    for tail, expected, reports in [(288, ' ' * 1109280 + 'X', []),
                                    (289, 'X', [('unknown', '\x1b[289C')])]:
        source = '\x1b[1024C' * 1083 + f'\x1b[{tail}CX'
        parser = AnsiParser()
        parser.feed(source)
        result = parser.finalize()[0]
        assert result.text == expected
        assert [(o.kind, o.raw) for o in result.skipped] == reports
    # Empty inserted rows consume eight cells; after exhaustion, later text stays
    # on the last existing row. Expected positions were recorded from the original.
    source = '\x1b[1024Bx' * 140
    result = parse_ansi_text(source)
    rows = result.text.split('\n')
    assert len(rows) == 131073
    assert [(i, row) for i, row in enumerate(rows) if row] == [
        *((1024 * i, ' ' * (i - 1) + 'x') for i in range(1, 128)),
        (131072, ' ' * 127 + 'x' * 13)]
    assert [(o.kind, o.raw) for o in result.skipped] == [('unknown', '\x1b[1024B')] * 12


def test_hyperlink_reset_rejection_and_unterminated_osc():
    source = '\x1b]8;id=page;https://example.org\aA\x1b[1mB\x1b[0mC\x1b]8;missing-uri\aD'
    result = parse_ansi_text(source)
    assert result.text == 'ABCD'
    attrs = ansi_attribute_cells(result)
    assert [(a.hyperlink.uri, a.hyperlink.id) for a in attrs[:3]] == [('https://example.org', 'page')] * 3
    assert attrs[1].bold and not attrs[2].bold
    assert attrs[3] is None
    assert [(o.kind, o.raw) for o in result.skipped] == [('unknown', '\x1b]8;missing-uri')]
    with encoding_state():
        velnora.set_encoding('utf-8')
        snapshot = canvas_snapshot(velnora.ANSIText(source).render((4,)))
        assert snapshot['text'] == (b'ABCD',)
        assert [a.hyperlink.uri for a in snapshot['attributes'][0][:3]] == ['https://example.org'] * 3
        assert is_default_attr(snapshot['attributes'][0][3])
    for parse in (parse_ansi_line, lambda text: (parse_ansi_text(text),)):
        result = parse('safe\x1b]2;hidden-more')[0]
        assert result.text == 'safe'
        assert [(o.kind, o.raw) for o in result.skipped] == [('unknown', '\x1b]2;hidden-more')]


def test_colors_effects_and_resets():
    # Basic and bright members are independently observable on both channels.
    for offset, fg_start, bg_start in [(0, 30, 40), (8, 90, 100)]:
        for index in range(8):
            result = parse_ansi_text(f'\x1b[{fg_start + index}mA\x1b[{bg_start + index}mB')
            first, second = ansi_attribute_cells(result)
            assert first.foreground_number == second.foreground_number == index + offset
            assert second.background_number == index + offset
            from velnora.display.raw import Screen
            screen = Screen()
            screen.register_palette([('outer', 'white', 'dark cyan')])
            _, rows = resolved_render(screen, velnora.AttrMap(velnora.ANSIText(
                f'\x1b[{fg_start + index}mA'), 'outer'), 1)
            assert rows[0][0].background_number == 6
    for source, rgb in [
        ('\x1b[38;5;196;48;5;21mX', (255, 0, 0, 0, 0, 255)),
        ('\x1b[38;2;0;127;255;48;2;255;64;0mX', (0, 127, 255, 255, 64, 0)),
        # Cube and grayscale members of the 256-color index (standard xterm values).
        ('\x1b[38;5;67;48;5;232mX', (95, 135, 175, 8, 8, 8)),
        ('\x1b[38;5;100;48;5;240mX', (135, 135, 0, 88, 88, 88))]:
        assert ansi_attribute_cells(parse_ansi_text(source))[0].get_rgb_values() == rgb
    for invalid in ['38;5;256', '48;5;999', '38;2;256;0;0', '48;2;0;0;256']:
        attrs = ansi_attribute_cells(parse_ansi_text('\x1b[31;44mA\x1b[' + invalid + ';4mB'))
        assert [(a.foreground_number, a.background_number) for a in attrs] == [(1, 4), (1, 4)]
        assert attrs[1].underline
    attrs = ansi_attribute_cells(parse_ansi_text('\x1b[31;44;1;2;3;4;5;7;9mA\x1b[22mB'))
    assert effect_flags(attrs[0]) == (True,) * len(EFFECTS)
    assert effect_flags(attrs[1]) == (False, False, True, True, True, True, True)
    assert (attrs[1].foreground_number, attrs[1].background_number) == (1, 4)
    for reset, effect in [(23, 'italics'), (24, 'underline'), (25, 'blink'), (27, 'standout'), (29, 'strikethrough')]:
        attr = ansi_attribute_cells(parse_ansi_text(f'\x1b[31;44;1;2;3;4;5;7;9mA\x1b[{reset}mB'))[1]
        assert effect_flags(attr) == tuple(name != effect for name in EFFECTS)
        assert (attr.foreground_number, attr.background_number) == (1, 4)
    reset = parse_ansi_text('\x1b[31;44;1;2;3;4;5;7;9mA\x1b[0mB')
    assert ansi_attribute_cells(reset)[1] is None
    attrs = ansi_attribute_cells(parse_ansi_text('\x1b[31;44;4mA\x1b[39mB\x1b[49mC\x1b[0mD'))
    assert attrs[1].underline
    assert attrs[1].background_number == 4
    assert attrs[2].underline
    assert attrs[3] is None
    with encoding_state():
        velnora.set_encoding('utf-8')
        from velnora.display.raw import Screen
        screen = Screen()
        screen.register_palette([('surrounding', 'yellow,bold', 'dark green')])
        source = '\x1b[31;44;4mA\x1b[39mB\x1b[49mC\x1b[0mD'
        text, rows = resolved_render(screen, velnora.AttrMap(velnora.ANSIText(source), 'surrounding'), 4)
        assert text == (b'ABCD',)
        assert [(a.foreground_number, a.background_number) for a in rows[0]] == [(1, 4), (11, 4), (11, 2), (11, 2)]
        assert [a.underline for a in rows[0]] == [True, True, True, False]
        assert rows[0][-1].bold


def test_character_set_selection_and_display():
    source = 'qx\x0eqx\x0fqx\x1b(0qx\x1b)B\x0eqx\x0fqx\x1b(Bqx'
    expected = 'qx─│qx─│qx─│qx'
    assert parse_ansi_text(source).text == expected
    with encoding_state():
        velnora.set_encoding('utf-8')
        assert label_lines(velnora.ANSIText(source), 14) == (expected,)
