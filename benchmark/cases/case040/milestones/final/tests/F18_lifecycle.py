# feature: F18
"""Acceptance checks for scheduling and application lifecycle."""
import os
import socket
import sys
import termios
import time
from pathlib import Path

import pytest
import velnora
from _helpers import deadline, run_process, environment, capture_call
from F17_helpers import tty_screen, tty_resize, tty_output, VTModel
from F18_helpers import exit_loop, run_to, watch_lifecycle, terminal_letters, socket_pair, ApplicationDriver, terminal_mouse_modes


def test_select_scheduling_and_callback_failures():
    loop = velnora.SelectEventLoop()
    seen = []
    cancelled = loop.alarm(0.03, lambda: seen.append('cancelled'))
    loop.remove_alarm(cancelled)
    start = time.monotonic()
    loop.alarm(0.04, lambda: seen.append(('timer', time.monotonic())))
    idle_handle = loop.enter_idle(lambda: seen.append('idle'))
    with socket_pair() as (reader, writer):
        reader.settimeout(1)
        handle = loop.watch_file(reader.fileno(), lambda: seen.append(reader.recv(1)))
        writer.sendall(b'x')
        run_to(loop, lambda: any(isinstance(x, tuple) for x in seen) and b'x' in seen and 'idle' in seen)
        loop.remove_watch_file(handle)
    loop.remove_enter_idle(idle_handle)
    loop.alarm(0.04, exit_loop)
    with deadline(5):
        loop.run()
    timers = [item for item in seen if isinstance(item, tuple)]
    assert len(timers) == 1
    assert timers[0][1] >= start + 0.04
    assert 'cancelled' not in seen
    for source in ('alarm', 'idle', 'file'):
        loop = velnora.SelectEventLoop()
        failure = ArithmeticError('application callback failure')
        def fail():
            raise failure
        with socket_pair() as (reader, writer):
            if source == 'alarm':
                loop.alarm(0, fail)
            elif source == 'idle':
                loop.enter_idle(fail)
            else:
                loop.watch_file(reader.fileno(), fail)
                writer.sendall(b'x')
            with deadline(5), pytest.raises(ArithmeticError) as caught:
                loop.run()
            assert caught.value is failure


def test_watch_persistence_replacement_and_idle_removal():
    watch_lifecycle(velnora.SelectEventLoop())


def test_real_service_adapters_and_basic_screen_rejection():
    helper = Path(__file__).with_name('F18_helpers.py')
    for service in ('asyncio', 'twisted', 'glib', 'tornado', 'trio', 'zmq'):
        result = run_process([sys.executable, '-c',
            'from F18_helpers import adapter_scenario; adapter_scenario()', service],
            env=environment({'PYTHONPATH': str(helper.parent)}), timeout=20)
        assert result.returncode == 0, (service, result.stdout, result.stderr)
        modes = ['sync-error']
        if service in ('asyncio', 'tornado', 'trio', 'zmq'):
            modes.append('error')
        for mode in modes:
            result = run_process([sys.executable, '-c',
                'from F18_helpers import adapter_scenario; adapter_scenario()', service, mode],
                env=environment({'PYTHONPATH': str(helper.parent)}), timeout=20)
            assert result.returncode == 0, (service, mode, result.stdout, result.stderr)
    from velnora.display.curses import Screen
    with pytest.raises(NotImplementedError):
        velnora.MainLoop(velnora.SolidFill(), screen=Screen(), event_loop=velnora.SelectEventLoop())


@pytest.mark.timeout(10, method='thread')
def test_root_filter_focus_unhandled_and_resize():
    default = velnora.MainLoop(velnora.SolidFill())
    from velnora.display.raw import Screen
    assert isinstance(default.screen, Screen)
    with tty_screen() as (screen, peer, slave):
        first, second = velnora.Edit('', 'First'), velnora.Edit('', 'Second')
        root = velnora.Filler(velnora.Pile([first, second]), valign='top')
        unhandled, filtered = [], []
        def input_filter(keys, raw):
            filtered.append((list(keys), list(raw)))
            return ['Z' if key == 'a' else key for key in keys if key != 'b']
        app = velnora.MainLoop(root, screen=screen, input_filter=input_filter,
                             unhandled_input=unhandled.append)
        driver = ApplicationDriver(app)
        def inspect(loop, data):
            assert first.edit_text == 'FirstZ'
            assert second.edit_text == 'Second'
            root.base_widget.focus_position = 1
            app.process_input(['Y', 'f8'])
            assert second.edit_text == 'SecondY'
            assert unhandled == ['f8']
            replacement = velnora.Edit('', 'New')
            app.widget = velnora.Filler(replacement, valign='top')
            app.process_input(['Q'])
            assert replacement.edit_text == 'NewQ'
            assert first.edit_text == 'FirstZ'
            tty_output(peer)
            app.draw_screen()
            assert 'NewQ' in terminal_letters(screen, peer)
            tty_resize(slave, 93, 27)
            driver.alarm(0.05, finish)
        def finish(loop, data):
            assert screen.get_cols_rows() == (93, 27)
            assert app.screen_size == (93, 27)
            assert any('window resize' in keys for keys, raw in filtered)
            exit_loop()
        os.write(peer, b'ab')
        driver.alarm(0.1, inspect)
        driver.run()
        assert [key for keys, raw in filtered for key in keys if key in ('a', 'b')] == ['a', 'b']


def test_application_alarms_files_and_pipes():
    app = velnora.MainLoop(velnora.SolidFill())
    results = []
    start = time.monotonic()
    payload = {'work': [1, 3]}
    def relative(loop, data):
        assert loop is app and data is payload
        results.append(('relative', time.monotonic()))
    def absolute(loop, data):
        assert loop is app and data is payload
        results.append(('absolute', time.time()))
    app.set_alarm_in(0.04, relative, payload)
    target = time.time() + 0.08
    app.set_alarm_at(target, absolute, payload)
    cancelled = app.set_alarm_in(0.02, lambda *args: results.append('cancelled'))
    app.remove_alarm(cancelled)
    with socket_pair() as (reader, writer):
        reader.settimeout(1)
        handle = app.watch_file(reader.fileno(), lambda: results.append(reader.recv(4)))
        writer.sendall(b'file')
        run_to(app.event_loop, lambda: len(results) == 3)
        app.remove_watch_file(handle)
        writer.sendall(b'kept')
        app.event_loop.alarm(0.03, exit_loop)
        with deadline(5):
            app.event_loop.run()
        assert reader.recv(4) == b'kept'
    assert b'file' in results
    assert sorted(x[0] for x in results if isinstance(x, tuple)) == ['absolute', 'relative']
    assert dict(x for x in results if isinstance(x, tuple))['relative'] >= start + 0.04
    assert dict(x for x in results if isinstance(x, tuple))['absolute'] >= target
    delivered = []
    pipe = app.watch_pipe(lambda data: delivered.append(data))
    try:
        os.write(pipe, b'notification')
        run_to(app.event_loop, lambda: bool(delivered))
        assert delivered == [b'notification']
        app.remove_watch_pipe(pipe)
        late = capture_call(os.write, pipe, b'late notification', catch=(BrokenPipeError,))
        if late.error is None:
            assert late.value == len(b'late notification')
        # A separate surviving source proves the loop still dispatches after removal.
        app.event_loop.alarm(0, lambda: delivered.append(b'alive'))
        run_to(app.event_loop, lambda: len(delivered) == 2)
        assert delivered == [b'notification', b'alive']
    finally:
        os.close(pipe)


@pytest.mark.timeout(10, method='thread')
def test_exit_error_and_temporary_terminal_handoff():
    for raises in (False, True):
        with tty_screen() as (screen, peer, slave):
            screen.stop()
            before = termios.tcgetattr(slave)
            seen = []
            app = velnora.MainLoop(velnora.Filler(velnora.Text('Before'), valign='top'),
                                 screen=screen, unhandled_input=seen.append)
            driver = ApplicationDriver(app)
            with socket_pair() as (reader, writer):
                reader.settimeout(1)
                app.watch_file(reader.fileno(), lambda: seen.append(reader.recv(1)))
                def handoff(loop, data):
                    assert not termios.tcgetattr(slave)[3] & termios.ICANON
                    screen.flush()
                    modes = terminal_mouse_modes(tty_output(peer))
                    assert modes
                    driver.alarm(0, lambda *args: seen.append('timer'))
                    caught_handoff = []
                    try:
                        with app.paused():
                            assert termios.tcgetattr(slave) == before
                            assert not terminal_mouse_modes(tty_output(peer), modes)
                            os.write(peer, b'x')
                            writer.sendall(b'f')
                            time.sleep(0.03)
                            assert seen == []
                            tty_resize(slave, 91, 26)
                            if raises:
                                raise LookupError('handoff failure')
                    except LookupError as error:
                        if not raises:
                            raise
                        caught_handoff.append(error)
                    assert bool(caught_handoff) is raises
                    assert not termios.tcgetattr(slave)[3] & termios.ICANON
                    screen.flush()
                    returned = tty_output(peer)
                    assert terminal_mouse_modes(returned)
                    # The other work owned the terminal: an unchanged root must
                    # still be repainted in full at the current dimensions.
                    vt = VTModel(91, 26)
                    vt.feed('other program output\r\n' * 30 + returned)
                    app.draw_screen()
                    screen.flush()
                    vt.feed(tty_output(peer))
                    assert vt.find('Before') == (0, 0)
                    assert all('other' not in vt.text(row) for row in range(26))
                    app.widget = velnora.Filler(velnora.Text('Returned'), valign='top')
                    app.draw_screen()
                    assert 'Returned' in terminal_letters(screen, peer)
                    assert app.screen_size == (91, 26)
                    # A second handoff at unchanged dimensions: the display is
                    # repainted although neither root nor size changed.
                    with app.paused():
                        assert termios.tcgetattr(slave) == before
                    screen.flush()
                    vt = VTModel(91, 26)
                    vt.feed('other program output\r\n' * 30 + tty_output(peer))
                    app.draw_screen()
                    screen.flush()
                    vt.feed(tty_output(peer))
                    assert vt.find('Returned') == (0, 0)
                    assert all('other' not in vt.text(row) for row in range(26))
                    os.write(peer, b'y\x1b[<0;3;2M')
                    driver.alarm(0.08, finish)
                def finish(loop, data):
                    assert b'f' in seen and 'timer' in seen and 'y' in seen
                    assert ('mouse press', 1, 2, 1) in seen
                    if raises:
                        def failure():
                            reader.recv(1)
                            raise ValueError('execution failure')
                        app.watch_file(reader.fileno(), failure)
                        writer.sendall(b'e')
                        return
                    exit_loop()
                driver.alarm(0, handoff)
                if raises:
                    with pytest.raises(ValueError):
                        driver.run()
                else:
                    driver.run()
            assert termios.tcgetattr(slave) == before
            with app.paused():
                assert termios.tcgetattr(slave) == before
            assert termios.tcgetattr(slave) == before
            assert not screen.started


@pytest.mark.timeout(10, method='thread')
def test_callbacks_redraw_changed_widgets():
    with tty_screen() as (screen, peer, slave):
        text = velnora.Text('Initial')
        observed = []
        app = velnora.MainLoop(velnora.Filler(text, valign='top'), screen=screen)
        driver = ApplicationDriver(app)
        with socket_pair() as (reader, writer):
            reader.settimeout(1)
            def readable():
                text.set_text(reader.recv(32).decode('ascii'))
            app.watch_file(reader.fileno(), readable)
            def alarm(loop, data):
                tty_output(peer)
                text.set_text('AlarmUpdated')
                driver.alarm(0.06, after_alarm)
            def after_alarm(loop, data):
                assert 'AlarmUpdated' in terminal_letters(screen, peer)
                observed.append('alarm')
                tty_output(peer)
                writer.sendall(b'InputUpdated')
                driver.alarm(0.06, after_input)
            def after_input(loop, data):
                assert 'InputUpdated' in terminal_letters(screen, peer)
                observed.append('input')
                exit_loop()
            driver.alarm(0.04, alarm)
            driver.run()
        assert observed == ['alarm', 'input']


@pytest.mark.parametrize('source', ['filter', 'widget', 'unhandled'])
def test_input_failures_propagate_and_restore_terminal(source):
    with tty_screen() as (screen, peer, slave):
        screen.stop()
        before = termios.tcgetattr(slave)
        failure = ArithmeticError('input dispatch failure')
        class FailingEdit(velnora.Edit):
            def keypress(self, size, key):
                if source == 'widget' and key == 'x':
                    raise failure
                return super().keypress(size, key)
        def input_filter(keys, raw):
            if source == 'filter' and 'x' in keys:
                raise failure
            return keys
        def unhandled(key):
            if source == 'unhandled' and key == 'f8':
                raise failure
        app = velnora.MainLoop(velnora.Filler(FailingEdit()), screen=screen,
                             input_filter=input_filter, unhandled_input=unhandled)
        app.event_loop.alarm(0, lambda: os.write(peer, b'\x1b[19~' if source == 'unhandled' else b'x'))
        with deadline(5), pytest.raises(ArithmeticError) as caught:
            app.run()
        assert caught.value is failure
        assert termios.tcgetattr(slave) == before
        assert not screen.started
