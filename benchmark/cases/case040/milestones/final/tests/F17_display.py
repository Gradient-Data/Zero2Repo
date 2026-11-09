# feature: F17
"""Real tty lifecycle and output observations; remaining facilities are ledgered."""
import os
import termios

import velnora

from _helpers import deadline
from F17_helpers import (VTModel, basic_tty_frame, emitted_glyphs, keyboard_reporting_state, tty_keys,
                         tty_output, tty_resize, tty_screen)


def test_direct_terminal_lifecycle_drawing_and_dimensions():
    # Observe kernel settings as well as product results: a no-op start fails.
    with tty_screen() as (screen, peer, slave):
        # An independent VT interpreter reads the drawn text, SGR state and cursor.
        vt = VTModel(80, 24)
        vt.feed(tty_output(peer))
        active = termios.tcgetattr(slave)
        assert not active[3] & termios.ECHO
        assert not active[3] & termios.ICANON
        assert screen.get_cols_rows() == (80, 24)
        for colors, foreground, background, expected_fg, expected_bg, position in [
                (16, 'dark red', 'dark blue', ('index', 1), ('index', 4), 3),
                (88, 'h34', 'h20', ('index', 34), ('index', 20), 1),
                (256, 'h172', 'h17', ('index', 172), ('index', 17), 4),
                (16777216, '#123456', '#abcdef', ('rgb', 18, 52, 86),
                 ('rgb', 171, 205, 239), 2)]:
            screen.set_terminal_properties(colors=colors)
            size = screen.get_cols_rows()
            word = f'Paint{colors}'
            edit = velnora.Edit('', word, edit_pos=position)
            attr = velnora.AttrSpec(foreground + ',bold,underline', background, colors)
            canvas = velnora.Filler(velnora.Pile([
                velnora.Text('Header'),
                velnora.Padding(velnora.AttrMap(edit, attr), left=4)]),
                valign='top').render(size, focus=True)
            screen.draw_screen(size, canvas)
            screen.flush()
            vt.feed(tty_output(peer))
            assert vt.find('Header') == (0, 0)
            assert vt.find(word) == (4, 1)
            for column in range(4, 4 + len(word)):
                char, sgr = vt.cell(column, 1)
                assert (sgr['fg'], sgr['bg'], sgr['bold'], sgr['underline']) == \
                    (expected_fg, expected_bg, True, True), (colors, column, sgr)
            # Unstyled neighbours stay unstyled; the cursor is where the canvas puts it.
            assert vt.cell(3, 1)[1]['bg'] == ('default',)
            assert vt.cell(0, 0)[1]['fg'] == ('default',)
            assert canvas.cursor == (4 + position, 1)
            assert vt.cursor_visible and (vt.x, vt.y) == canvas.cursor
        tty_resize(slave, 97, 28)
        assert tty_keys(screen, 1) == ['window resize']
        assert screen.get_cols_rows() == (97, 28)
        vt.resize(97, 28)
        # A full frame at the new size, including its bottom-right cell.
        rows = [chr(ord('A') + k) * 97 for k in range(28)]
        canvas = velnora.Pile([velnora.Text(row) for row in rows]).render((97,))
        screen.draw_screen((97, 28), canvas)
        screen.flush()
        vt.feed(tty_output(peer))
        assert [vt.text(y) for y in range(28)] == rows
        screen.stop()
        restored = termios.tcgetattr(slave)
        assert restored[3] & termios.ECHO
        assert restored[3] & termios.ICANON
        # Restart is a second real lifecycle; the scope still owns final stop.
        screen.start()
        assert not termios.tcgetattr(slave)[3] & termios.ICANON


def test_basic_terminal_lifecycle_and_frame():
    for term in ('vt100', 'xterm-256color'):
        size, active, before, after, output = basic_tty_frame('Basic frame', term=term)
        assert size == [80, 24]
        assert not active[3] & termios.ECHO
        assert not active[3] & termios.ICANON
        assert after == before
        assert 'Basic frame' in ''.join(c for c, uri in emitted_glyphs(output))
        if term == 'xterm-256color':
            # Interpreted output: the frame shows the requested basic colour.
            vt = VTModel(80, 24)
            vt.feed(output)
            grid = vt.screen
            rows = [''.join(c for c, a in row) for row in grid]
            y = next(k for k, row in enumerate(rows) if 'Basic frame' in row)
            x = rows[y].index('Basic frame')
            assert (x, y) == (0, 0)
            assert {grid[y][k][1]['fg'] for k in range(x, x + 11)} == {('index', 1)}


def test_extended_keyboard_opt_in_and_unconfirmed_legacy_input():
    # Before any confirmation both sessions decode legacy input.
    for options in ({}, {'extended_keys': True}):
        with tty_screen(**options) as (screen, peer, slave):
            assert screen.extended_keys is bool(options)
            os.write(peer, b'\t\r\x1b[P\x1b[1;5D')
            assert tty_keys(screen, 4) == ['tab', 'enter', 'delete', 'ctrl left']
            if options:
                # Play a kitty-keyboard terminal on the tty peer: report its
                # keyboard flags (contract form ESC [ ? <flags> u) followed by a
                # primary device-attributes reply, as such a terminal answers
                # capability queries. The answers are not key presses; a legacy
                # sentinel marks their end.
                tty_output(peer)
                os.write(peer, b'\x1b[?0u\x1b[?62;22c' + b'z')
                seen = []
                with deadline(3):
                    while 'z' not in seen:
                        seen.extend(screen.get_input())
                assert seen == ['z']
                # Kitty key reports: Ctrl-I and Ctrl-M differ from Tab and Enter.
                os.write(peer, b'\x1b[105;5u\t\x1b[109;5u\r')
                assert tty_keys(screen, 4) == ['ctrl i', 'tab', 'ctrl m', 'enter']
            screen.stop()
            assert termios.tcgetattr(slave)[3] & termios.ICANON

    # A terminal offering both protocols gets kitty reporting; one offering only
    # modifyOtherKeys gets that. Stopping restores what the terminal reported.
    for replies, expect_kitty in ((b'\x1b[?0u\x1b[>4;1m', True), (b'\x1b[>4;1m', False)):
        with tty_screen(extended_keys=True) as (screen, peer, slave):
            tty_output(peer)
            os.write(peer, replies + b'\x1b[?62;22c' + b'z')
            seen = []
            with deadline(3):
                while 'z' not in seen:
                    seen.extend(screen.get_input())
            assert seen == ['z']
            enabled = keyboard_reporting_state(tty_output(peer), ((0,), 1), initial_modify=1)
            flags, modify = enabled[0][-1], enabled[1]
            if expect_kitty:
                assert flags & 1 and modify == 1, enabled
                if flags & 2:
                    # Release reports were requested: a release alone is no key press.
                    os.write(peer, b'\x1b[105;5:3u')
                os.write(peer, b'\x1b[105;5u\t')
            else:
                assert flags == 0 and modify == 2, enabled
                os.write(peer, b'\x1b[27;5;105~\t')
            assert tty_keys(screen, 2) == ['ctrl i', 'tab']
            screen.stop()
            restored = keyboard_reporting_state(tty_output(peer), enabled, initial_modify=1)
            assert restored == ((0,), 1), restored


def test_hyperlink_output_opt_in_and_plain_basic_text():
    target = 'https://example.org/document'
    for options in ({}, {'hyperlinks': True}, {'hyperlinks': False}):
        with tty_screen() as (screen, peer, slave):
            screen.set_terminal_properties(colors=16, **options)
            # The same styled content in fresh sessions differs only in opt-in.
            attr = velnora.AttrSpec('dark red', 'default', 16, hyperlink=target)
            canvas = velnora.Filler(velnora.Text([(attr, 'Linked'), ' Plain']),
                                  valign='top').render((80, 24))
            tty_output(peer)
            screen.draw_screen((80, 24), canvas)
            screen.flush()
            glyphs = emitted_glyphs(tty_output(peer))
            text = ''.join(c for c, uri in glyphs)
            assert 'Linked Plain' in text
            start = text.index('Linked Plain')
            expected = target if options.get('hyperlinks') else None
            assert [uri for c, uri in glyphs[start:start+6]] == [expected] * 6
            assert all(uri is None for c, uri in glyphs[start+6:start+12])
    # Use the real curses backend, not an alternative rendering of its input.
    size, active, before, after, output = basic_tty_frame('Linked Plain', hyperlink=target)
    glyphs = emitted_glyphs(output)
    assert 'Linked Plain' in ''.join(c for c, uri in glyphs)
    assert all(uri is None for c, uri in glyphs)
    assert after == before


def test_basic_terminal_attributes_cursor_and_monochrome():
    for term in ('xterm-256color', 'vt100'):
        size, active, before, after, output = basic_tty_frame(
            'StyledFrame', term=term, foreground='dark green,bold,underline',
            background='dark blue', cursor=4)
        assert after == before
        vt = VTModel(80, 24)
        vt.feed(output)
        assert vt.find('StyledFrame') == (0, 0)
        for column in range(len('StyledFrame')):
            style = vt.cell(column, 0)[1]
            assert style['bold'] and style['underline'], (term, style)
            if term == 'xterm-256color':
                assert (style['fg'], style['bg']) == (('index', 2), ('index', 4))
            else:
                assert style['fg'] == style['bg'] == ('default',)
        assert vt.cursor_visible and (vt.x, vt.y) == (4, 0)
