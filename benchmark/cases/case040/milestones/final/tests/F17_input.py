# feature: F17
"""Public direct-screen input observations using a kernel pseudoterminal."""
import os
import time

import velnora
from _helpers import deadline

from F17_helpers import (VTModel, basic_tty_session, tty_fragment, tty_keys, tty_output, tty_resize,
                         tty_screen)


def test_terminal_keys_resize_and_mouse():
    with tty_screen() as (screen, peer, slave):
        vectors = [
            (b'A', 'A'), ('界'.encode(), '界'),
            (b'\x1b[A', 'up'), (b'\x1b[B', 'down'),
            (b'\x1b[C', 'right'), (b'\x1b[D', 'left'),
            (b'\x1b[5~', 'page up'), (b'\x1b[6~', 'page down'),
            (b'\x1b[H', 'home'), (b'\x1b[F', 'end'),
            (b'\x1b[2~', 'insert'), (b'\x1b[3~', 'delete'),
            (b'\x7f', 'backspace'), (b'\t', 'tab'), (b'\r', 'enter'),
            (b'\x1b[1;2A', 'shift up'), (b'\x1b[1;5D', 'ctrl left'),
            (b'\x1ba', 'meta a'), (b'\x02', 'ctrl b'),
        ]
        function_codes = (11, 12, 13, 14, 15, 17, 18, 19, 20, 21,
                          23, 24, 25, 26, 28, 29, 31, 32, 33, 34)
        vectors.extend((f'\x1b[{code}~'.encode(), f'f{number}')
                       for number, code in enumerate(function_codes, 1))
        os.write(peer, b''.join(data for data, key in vectors))
        assert tty_keys(screen, len(vectors)) == [key for data, key in vectors]
        tty_resize(slave, 93, 31)
        assert tty_keys(screen, 1) == ['window resize']
        assert screen.get_cols_rows() == (93, 31)
        vt = VTModel(93, 31)
        vt.feed(tty_output(peer))
        assert not vt.mouse_modes()
        screen.set_mouse_tracking(True)
        screen.flush()
        vt.feed(tty_output(peer))
        # Enabled tracking asks the terminal for presses, releases and drags.
        assert vt.mouse_modes() & {1002, 1003}, vt.mouse_modes()
        mouse = [
            (b'\x1b[<0;8;5M', ('mouse press', 1, 7, 4)),
            (b'\x1b[<0;8;5m', ('mouse release', 1, 7, 4)),
            (b'\x1b[<64;9;6M', ('mouse press', 4, 8, 5)),
            (b'\x1b[<65;9;6M', ('mouse press', 5, 8, 5)),
            (b'\x1b[<32;10;7M', ('mouse drag', 1, 9, 6)),
        ]
        os.write(peer, b''.join(data for data, event in mouse))
        assert tty_keys(screen, len(mouse)) == [event for data, event in mouse]
        screen.set_mouse_tracking(False)
        screen.flush()
        vt.feed(tty_output(peer))
        assert not vt.mouse_modes()
        os.write(peer, b'z')
        assert tty_keys(screen, 1) == ['z']
        screen.set_mouse_tracking(True)
        screen.flush()
        vt.feed(tty_output(peer))
        assert vt.mouse_modes()
        screen.stop()
        vt.feed(tty_output(peer))
        assert not vt.mouse_modes()


def test_fragmented_terminal_input():
    with tty_screen() as (screen, peer, slave):
        # Complete each prefix within a generous completion wait, allowing
        # either blocking or nonblocking public reads and any event batching.
        screen.set_input_timeouts(complete_wait=5)
        for prefix, suffix, expected in [
            (b'\x1b[', b'A', 'up'),
            (b'\xe7', b'\x95\x8c', '界'),
            (b'\x1b[1;', b'5D', 'ctrl left'),
        ]:
            assert tty_fragment(screen, peer, prefix, suffix) == [expected]
        screen.set_input_timeouts(max_wait=0.02, complete_wait=0.4)
        assert tty_fragment(screen, peer, b'\x1b[', b'B') == ['down']

    # Completion expiry is supported by the event-loop path, including its default.
    for configured, expected_wait in ((None, 0.125), (0.3, 0.3)):
        with tty_screen() as (screen, peer, slave):
            if configured is not None:
                screen.set_input_timeouts(complete_wait=configured)
            loop = velnora.SelectEventLoop()
            delivered = []
            escape_times = []
            def ready(keys, raw):
                delivered.extend(keys)
                if 'esc' in keys:
                    escape_times.append(time.monotonic())
                    raise velnora.ExitMainLoop()
            screen.hook_event_loop(loop, ready)
            start = time.monotonic()
            os.write(peer, b'A\x1b')
            try:
                with deadline(5):
                    loop.run()
            finally:
                screen.unhook_event_loop(loop)
            assert delivered == ['A', 'esc']
            assert len(escape_times) == 1
            # Timer semantics, with broad scheduling reserve rather than a speed claim.
            assert expected_wait <= escape_times[0] - start


def test_basic_terminal_keys_mouse_and_resize():
    import fcntl
    import signal
    import struct
    import termios
    with basic_tty_session() as (request, peer, slave, process):
        vectors = [(b'A', 'A'), ('界'.encode(), '界'), (b'\x1b[A', 'up'),
                   (b'\x1b[B', 'down'), (b'\x1b[C', 'right'), (b'\x1b[D', 'left'),
                   (b'\x1b[5~', 'page up'), (b'\x1b[6~', 'page down'),
                   (b'\x1b[H', 'home'), (b'\x1b[F', 'end'), (b'\x1b[2~', 'insert'),
                   (b'\x1b[3~', 'delete'), (b'\x7f', 'backspace'), (b'\t', 'tab'),
                   (b'\r', 'enter'), (b'\x1b[1;5D', 'ctrl left'), (b'\x1ba', 'meta a')]
        codes = (11, 12, 13, 14, 15, 17, 18, 19, 20, 21, 23, 24, 25, 26, 28, 29, 31, 32, 33, 34)
        vectors.extend((f'\x1b[{code}~'.encode(), f'f{number}') for number, code in enumerate(codes, 1))
        os.write(peer, b''.join(wire for wire, _ in vectors))
        observed = []
        with deadline(10):
            while len(observed) < len(vectors):
                observed.extend(request('read'))
        assert observed == [key for _, key in vectors]
        assert request('mouse') is True
        for wire, expected in [(b'\x1b[<0;8;5M', ['mouse press', 1, 7, 4]),
                               (b'\x1b[<0;8;5m', ['mouse release', 1, 7, 4]),
                               (b'\x1b[<64;9;6M', ['mouse press', 4, 8, 5]),
                               (b'\x1b[<65;9;6M', ['mouse press', 5, 8, 5])]:
            os.write(peer, wire)
            observed = []
            with deadline(10):
                while not observed:
                    observed.extend(request('read'))
            assert observed == [expected]
        assert request('disable') == 'unsupported'
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 29, 91, 0, 0))
        os.kill(process.pid, signal.SIGWINCH)
        observed = []
        with deadline(10):
            while 'window resize' not in observed:
                observed.extend(request('read'))
        assert observed == ['window resize']
        assert request('size') == [91, 29]
