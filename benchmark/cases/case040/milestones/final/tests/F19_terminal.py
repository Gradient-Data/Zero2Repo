# feature: F19
"""Acceptance checks through actual child PTYs and public terminal rendering."""
import errno
import os
import time

import pytest
import velnora
from _helpers import CallbackRecorder
from F03_helpers import is_default_attr
from F19_helpers import child_terminal, assert_terminal_screen, focused_terminal_probe


def test_child_environment_input_and_resize(monkeypatch):
    monkeypatch.setenv('F19_VALUE', 'inherited-value')
    monkeypatch.setenv('TERM', 'parent-terminal')
    for kind, env, value in (
        ('command', None, 'inherited-value'),
        ('command', dict(os.environ, F19_VALUE='supplied-value', TERM='other'), 'supplied-value'),
        ('callable', None, 'inherited-value'),
        ('callable', dict(os.environ, F19_VALUE='supplied-value', TERM='other'), 'inherited-value'),
        ('shell', None, 'inherited-value'),
    ):
        with child_terminal((20, 4), kind=kind, env=env) as child:
            info = child.request('info')
            assert info['env']['F19_VALUE'] == value
            assert info['size'] == [20, 4]
            assert info['env']['TERM'] == ('parent-terminal' if kind == 'callable' else 'linux')
            assert info['pid'] != os.getpid()
            child.emit('ready')
            assert_terminal_screen(child, ['ready', '', '', ''], (5, 0))
            assert child.keys('x', 'enter') == (None, None)
            assert child.received() == b'x\r'
            child.resize((23, 6))
            assert child.request('info')['size'] == [23, 6]
            child.emit('\r\nresized')
            assert_terminal_screen(child, ['ready', 'resized', '', '', '', ''])


def test_cursor_wrapping_newline_and_scrolling_region():
    probe = focused_terminal_probe()
    assert probe.returncode == 0, probe.stderr
    with child_terminal((6, 5)) as child:
        child.emit('abcdefG\rZ\bY')
        assert_terminal_screen(child, ['abcdef', 'Y', '', '', ''], (1, 1))
        child.emit('\x1bcab\nC\x1b[20h\nD')
        assert_terminal_screen(child, ['ab', '  C', 'D', '', ''], (1, 2))
        child.emit('\x1bc\x1b[999;999HX\x1b[1;1HY\x1b[999AZ')
        assert_terminal_screen(child, ['YZ', '', '', '', '     X'], (2, 0))
        child.emit('\x1b[999D\x1b[999B')
        assert child.terminal.get_cursor_coords(child.size) == (0, 4)
        child.emit('\x1bc111\r\n222\r\n333\r\n444\r\n555\x1b[2;4r\x1b[4;1H\n')
        assert_terminal_screen(child, ['111', '333', '444', '', '555'], (0, 3))
        child.emit('\x1b[2;1H\x1bM')
        assert_terminal_screen(child, ['111', '', '333', '444', '555'], (0, 1))
        child.emit('\x1b[?6h\x1b[99;99H')
        assert child.terminal.get_cursor_coords(child.size) == (5, 3)
        child.emit('\x1b[1;1HQ\x1b[999A')
        assert_terminal_screen(child, ['111', 'Q', '333', '444', '555'], (1, 1))


def test_erasure_character_and_line_edits_remove_links():
    with child_terminal((8, 4)) as child:
        for mode, expected in ((0, 'abc'), (1, '    efgh'), (2, '')):
            child.emit('\x1bcabcdefgh\x1b[1;4H\x1b[' + str(mode) + 'K')
            assert_terminal_screen(child, [expected, '', '', ''], (3, 0))
        for mode, rows in ((0, ['aaaa', 'bb', '', '']),
                           (1, ['', '   b', 'cccc', 'dddd']),
                           (2, ['', '', '', ''])):
            child.emit('\x1bcaaaa\r\nbbbb\r\ncccc\r\ndddd\x1b[2;3H\x1b[' + str(mode) + 'J')
            assert_terminal_screen(child, rows, (2, 1))
        child.emit('\x1bcabcdefgh\x1b[1;3H\x1b[2@')
        assert_terminal_screen(child, ['ab  cdef', '', '', ''], (2, 0))
        child.emit('\x1b[3P')
        assert_terminal_screen(child, ['abdef', '', '', ''], (2, 0))
        child.emit('\x1bc111\r\n222\r\n333\r\n444\x1b[2;3r\x1b[2;1H\x1b[L')
        assert_terminal_screen(child, ['111', '', '222', '444'], (0, 1))
        child.emit('\x1b[M')
        assert_terminal_screen(child, ['111', '222', '', '444'], (0, 1))
        for operation in ('\x1b[2K', '\x1b[2J', '\x1b[2@', '\x1b[2P', '\x1b[L', '\x1b[M'):
            child.emit('\x1bc\x1b]8;id=doc;https://example.org/item\x1b\\ABCDEFGH\r\nIJKLMNOP\x1b[1;3H' + operation)
            snapshot = child.snapshot()
            for row in snapshot['content']:
                for attr, charset, data in row:
                    if data.strip(b' ') == b'':
                        assert attr is None or attr.hyperlink is None or attr.hyperlink.uri == ""
            # Surviving text keeps its target, so dropping all styles cannot pass.
            linked = [attr.hyperlink.uri for row in snapshot['content'] for attr, _, data in row
                      if data.strip(b' ') and attr is not None and attr.hyperlink is not None]
            if operation != '\x1b[2J':
                assert linked and set(linked) == {'https://example.org/item'}


def test_tabs_saved_attributes_charsets_utf8_and_insert_modes():
    with child_terminal((20, 4)) as child:
        child.emit('A\tB\tC\tD')
        assert_terminal_screen(child, ['A       B       C  D', '', '', ''], (19, 0))
        child.emit('\x1bc\x1b[3g\x1b[1;5H\x1bH\r\tX\r\x1b[1;5H\x1b[g\r\tY')
        assert_terminal_screen(child, ['    X              Y', '', '', ''], (19, 0))
        child.emit('\x1bcABCD\x1b[1;2H\x1b[4hxy\x1b[4lZ')
        assert_terminal_screen(child, ['AxyZCD', '', '', ''], (4, 0))
        child.emit('\x1bc\x1b[?7l' + 'a' * 22 + 'Z')
        assert_terminal_screen(child, ['a' * 19 + 'Z', '', '', ''], (19, 0))
        child.emit('\x1bc\x1b[31m\x1b(0\x1b7\x1b[0m\x1b(B\x1b[3;4Hq\x1b8q\x1b(Bé')
        snap = child.snapshot()
        assert child.visible_rows()[0].startswith('─é')
        assert snap['attributes'][0][0].foreground_number == 1
        assert child.rows()[2][3:4] == b'q'
        assert is_default_attr(snap['attributes'][2][3])
        # Indexed, 256-colour and direct-colour SGR keep their meaning; reset clears it.
        child.emit('\x1bc\x1b[4;35;46mX\x1b[0mY\x1b[38;5;172mP\x1b[38;2;18;52;86mQ'
                   '\x1b[48;5;17mR\x1b[0;1mS')
        cells = child.snapshot()['attributes'][0]
        assert child.rows()[0].startswith(b'XYPQRS')
        assert cells[0].underline and cells[0].background_number == 6
        assert cells[0].foreground_number == 5 and not cells[0].bold
        assert is_default_attr(cells[1])
        assert cells[2].get_rgb_values()[:3] == (215, 135, 0)
        assert cells[3].get_rgb_values()[:3] == (18, 52, 86)
        assert cells[4].get_rgb_values() == (18, 52, 86, 0, 0, 95)
        assert cells[5].bold and cells[5].get_rgb_values() == (None,) * 6
        child.emit('\x1bc\x1b[32m\x1b(0\x1b[s\x1b[34m\x1b(B\x1b[3;4H\x1b[uq')
        assert child.visible_rows() == ('q'.ljust(20),) + (' ' * 20,) * 3
        assert child.terminal.get_cursor_coords(child.size) == (1, 0)
        assert child.snapshot()['attributes'][0][0].foreground_number == 4


def test_alternate_screens_and_resize_preserve_rows():
    with child_terminal((8, 4)) as child:
        child.emit('main\x1b[?47h\x1b[Halt\x1b[?47l')
        assert_terminal_screen(child, ['main', '', '', ''])
        child.emit('\x1b[?47h')
        assert_terminal_screen(child, ['alt', '', '', ''])
        child.emit('\x1b[?1047l\x1b[?47h')
        assert_terminal_screen(child, ['', '', '', ''])
        child.emit('kept\x1b[?47l\x1b[2;3H\x1b[?1049h')
        assert_terminal_screen(child, ['', '', '', ''], (2, 1))
        child.emit('temp\x1b[4;1H\x1b[?1049l')
        assert_terminal_screen(child, ['main', '', '', ''], (2, 1))
        child.emit('\x1bcabcdefgh\r\nijklmnop\r\nqrstuvwx\r\nyz')
        child.resize((5, 2))
        assert_terminal_screen(child, ['qrstu', 'yz'])
        child.resize((9, 4))
        assert_terminal_screen(child, ['abcde', 'ijklm', 'qrstu', 'yz'])
        child.emit('\x1b[?47h')
        child.resize((6, 3))
        child.emit('\x1b[?47l')
        assert_terminal_screen(child, ['ijklm', 'qrstu', 'yz'])


def test_capture_scrollback_limit_and_half_page_browsing():
    with child_terminal((10, 4)) as child:
        assert child.keys('up') == ('up',)
        assert child.keys('z') == (None,)
        assert child.received() == b'z'
        assert child.keys('ctrl a', 'down') == (None, 'down')
        assert child.received() == b''
        assert child.keys('ctrl a', 'ctrl a') == (None, None)
        assert child.received() == b'\x01'
        child.keys('x', 'ctrl a')
        assert child.received() == b'x'
        child.emit('\x1bc' + '\r\n'.join(f'{i:05d}' for i in range(10009)))
        assert_terminal_screen(child, ['10005', '10006', '10007', '10008'])
        child.keys('page up')
        assert_terminal_screen(child, ['10003', '10004', '10005', '10006'])
        for _ in range(5001):
            child.keys('page up')
        assert_terminal_screen(child, ['00005', '00006', '00007', '00008'])
        child.keys('page down')
        assert_terminal_screen(child, ['00007', '00008', '00009', '00010'])
        child.keys('x')
        assert child.received() == b'x'
        assert_terminal_screen(child, ['10005', '10006', '10007', '10008'])
        child.keys('ctrl a')
        child.emit('\x1b[?47h\x1b[H' + '\r\n'.join(f'A{i:02d}' for i in range(12)))
        child.keys('page up')
        assert_terminal_screen(child, ['A08', 'A09', 'A10', 'A11'])
        child.emit('\x1b[?47l')
        child.keys('page up')
        assert_terminal_screen(child, ['10003', '10004', '10005', '10006'])
    # Half of an odd viewport height is rounded down.
    with child_terminal((10, 5)) as child:
        child.emit('\r\n'.join(f'{i:02d}' for i in range(20)))
        assert_terminal_screen(child, ['15', '16', '17', '18', '19'])
        child.keys('page up')
        assert_terminal_screen(child, ['13', '14', '15', '16', '17'])
        child.keys('page up')
        assert_terminal_screen(child, ['11', '12', '13', '14', '15'])
        child.keys('page down')
        assert_terminal_screen(child, ['13', '14', '15', '16', '17'])


def test_title_bell_and_led_notifications():
    with child_terminal((12, 3)) as child:
        title, bell, leds = CallbackRecorder(), CallbackRecorder(), CallbackRecorder()
        for signal, recorder in (('title', title), ('beep', bell), ('leds', leds)):
            velnora.connect_signal(child.terminal, signal, recorder)
        child.emit('visible\x1b]2;Application title\x07\x07\x1b[0q\x1b[1q\x1b[2q\x1b[3q')
        title.calls.remove(((child.terminal, 'f19-barrier-' + str(child.serial)), {}))
        assert title.calls == [((child.terminal, 'Application title'), {})]
        assert bell.calls == [((child.terminal,), {})]
        assert leds.calls == [((child.terminal, state), {}) for state in ('clear', 'scroll_lock', 'num_lock', 'caps_lock')]
        assert_terminal_screen(child, ['visible', '', ''])


def test_mouse_and_bracketed_paste_reach_child():
    with child_terminal() as child:
        child.keys('ctrl a')
        assert child.terminal.mouse_event(child.size, 'mouse press', 1, 2, 1, True) is False
        child.emit('\x1b[?1000h\x1b[?1006h')
        for event in ('mouse press', 'mouse release'):
            assert child.terminal.mouse_event(child.size, event, 1, 2, 1, True) is True
        assert child.received() == b'\x1b[<0;3;2M\x1b[<0;3;2m'
        child.emit('\x1b[?1002h')
        assert child.terminal.mouse_event(child.size, 'mouse drag', 1, 3, 2, True) is True
        assert child.terminal.mouse_event(child.size, 'mouse press', 4, 0, 0, True) is True
        assert child.received() == b'\x1b[<32;4;3M\x1b[<64;1;1M'
        child.emit('\x1b[?1002l')
        assert child.terminal.mouse_event(child.size, 'mouse press', 1, 2, 1, True) is False
        child.keys('begin paste', 'A', 'end paste')
        assert child.received() == b'A'
        child.emit('\x1b[?2004h\x1b[=31u')
        child.keys('begin paste', 'B', 'é', 'end paste')
        assert child.received() == b'\x1b[200~B\xc3\xa9\x1b[201~'
        child.emit('\x1b[?2004l')
        child.keys('begin paste', 'C', 'end paste')
        assert child.received() == b'C'


def test_extended_keyboard_flags_modifiers_and_legacy_refusal():
    with child_terminal() as child:
        child.keys('ctrl a')
        assert child.keys('shift up') == ('shift up',)
        assert child.received() == b''
        for stream, expected in (
            ('\x1b[?u', b'\x1b[?0u'),
            ('\x1b[>1u\x1b[>5u\x1b[?u', b'\x1b[?5u'),
            ('\x1b[<u\x1b[?u', b'\x1b[?1u'),
            ('\x1b[?47h\x1b[?u', b'\x1b[?0u'),
            ('\x1b[=8u\x1b[?47l\x1b[?u', b'\x1b[?1u'),
            ('\x1b[?47h\x1b[?u', b'\x1b[?8u'),
        ):
            child.emit(stream)
            assert child.received() == expected
        for flags, keys, expected in (
            (1, ('ctrl b', 'meta ctrl super hyper x', 'shift 1'), b'\x1b[98;5u\x1b[120;31u\x1b[49;2u'),
            (5, ('ctrl A',), b'\x1b[97:65;6u'),
            (28, ('A', 'a'), b'\x1b[97:65;2;65u\x1b[97;;97u'),
            (3, ('ctrl b',), b'\x1b[98;5u'),
            (8, ('enter', 'left shift'), b'\x1b[13u\x1b[57441u'),
        ):
            child.emit('\x1b[=' + str(flags) + 'u')
            assert child.keys(*keys) == (None,) * len(keys)
            assert child.received() == expected


def test_child_exit_and_terminate_release_real_resources():
    for natural in (True, False):
        with child_terminal() as child:
            closed = CallbackRecorder()
            velnora.connect_signal(child.terminal, 'closed', closed)
            info = child.request('info')
            pid, master = info['pid'], child.terminal.master
            os.kill(pid, 0)
            os.fstat(master)
            if natural:
                child.file.write(b'{"op":"exit"}\n')
                end = time.monotonic() + 8
                while not closed.calls:
                    assert time.monotonic() < end, 'Child exit was not delivered'
                    child.terminal.wait_and_feed(0.05)
                assert closed.calls == [((child.terminal,), {})]
            else:
                child.terminal.terminate()
            assert child.terminal.terminated is True
            with pytest.raises(ProcessLookupError):
                os.kill(pid, 0)
            with pytest.raises(OSError) as error:
                os.fstat(master)
            assert error.value.errno == errno.EBADF
            assert child.keys('x') == ('x',)
