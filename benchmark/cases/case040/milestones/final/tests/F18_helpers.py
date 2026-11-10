# feature: F18
"""Bounded observations of real scheduling and tty output."""
import contextlib
import socket
import time
import velnora
from _helpers import deadline
from F17_helpers import emitted_glyphs, tty_output


def exit_loop(*args):
    raise velnora.ExitMainLoop


def run_to(loop, predicate):
    """Run until a positive application result exists, with bounded failure."""
    until = time.monotonic() + 3
    def check():
        if predicate():
            raise velnora.ExitMainLoop
        assert time.monotonic() < until, 'Expected callback result was not delivered'
        loop.alarm(0.01, check)
    loop.alarm(0.01, check)
    with deadline(5):
        loop.run()


def watch_lifecycle(loop):
    """Observe repeated readiness, replacement and removal without private state."""
    seen = []
    with socket_pair() as (reader, writer):
        reader.settimeout(1)
        def replacement():
            seen.append(('replacement', reader.recv(1)))
            loop.remove_watch_file(handle[0])
            writer.sendall(b'd')
            loop.alarm(0.03, exit_loop)
        handle = [None]
        def original():
            assert len(seen) < 2, 'Replaced receiver was called again'
            seen.append(('original', reader.recv(1)))
            if len(seen) == 1:
                writer.sendall(b'b')
            else:
                handle[0] = loop.watch_file(reader.fileno(), replacement)
                writer.sendall(b'c')
        handle[0] = loop.watch_file(reader.fileno(), original)
        writer.sendall(b'a')
        with deadline(5):
            loop.run()
        assert seen == [('original', b'a'), ('original', b'b'), ('replacement', b'c')]
        assert reader.recv(1) == b'd'
    idle = []
    def on_idle():
        idle.append('idle')
        loop.remove_enter_idle(idle_handle)
    idle_handle = loop.enter_idle(on_idle)
    ticks = []
    loop.alarm(0.02, lambda: ticks.append('live'))
    loop.alarm(0.04, exit_loop)
    with deadline(5):
        loop.run()
    assert ticks == ['live']
    assert idle == ['idle']


def terminal_letters(screen, peer):
    screen.flush()
    return ''.join(char for char, uri in emitted_glyphs(tty_output(peer)))


def adapter_scenario():
    """Each service lives in an isolated process, including single-use reactors."""
    import sys
    import asyncio
    service = sys.argv[1]
    cleanup = lambda: None
    if service == 'asyncio':
        native = asyncio.new_event_loop()
        loop = velnora.AsyncioEventLoop(loop=native)
        cleanup = native.close
    elif service == 'tornado':
        from tornado.ioloop import IOLoop
        native = IOLoop()
        loop = velnora.TornadoEventLoop(native)
        cleanup = native.close
    elif service == 'twisted':
        from twisted.internet.selectreactor import SelectReactor
        native = SelectReactor()
        loop = velnora.TwistedEventLoop(native)
    elif service == 'glib':
        from gi.repository import GLib
        loop = velnora.GLibEventLoop()
    elif service == 'trio':
        import trio
        loop = velnora.TrioEventLoop()
    elif service == 'zmq':
        loop = velnora.ZMQEventLoop()
    else:
        raise ValueError(service)
    if len(sys.argv) > 2 and sys.argv[2] in ('error', 'sync-error'):
        failure = ArithmeticError('application failure')
        def fail_now():
            raise failure
        async def fail_after_suspend():
            if service == 'trio':
                await trio.sleep(0.01)
            else:
                await asyncio.sleep(0.01)
            raise failure
        # An ordinary callback failure must be exposed by every integration.
        loop.alarm(0, fail_after_suspend if sys.argv[2] == 'error' else fail_now)
        # A guard turns a swallowed failure into a normal return, not a hang.
        loop.alarm(3, exit_loop)
        try:
            with deadline(5):
                loop.run()
        except ArithmeticError as error:
            assert error is failure
        else:
            raise AssertionError('Async callback failure was not exposed')
        finally:
            cleanup()
        return
    seen = []
    with socket_pair() as (reader, writer):
        reader.settimeout(1)
        handles = {}
        def old():
            raise AssertionError('Replaced watch was dispatched')
        def readable():
            seen.append(reader.recv(1))
            if seen.count(b'a') == 1 and b'b' not in seen:
                writer.sendall(b'b')
            else:
                loop.remove_watch_file(handles['file'])
                writer.sendall(b'c')
        loop.watch_file(reader.fileno(), old)
        handles['file'] = loop.watch_file(reader.fileno(), readable)
        def idle():
            seen.append('idle')
            loop.remove_enter_idle(handles['idle'])
        handles['idle'] = loop.enter_idle(idle)
        cancelled = loop.alarm(0.01, lambda: seen.append('cancelled'))
        loop.remove_alarm(cancelled)
        loop.alarm(0.02, lambda: seen.append('timer'))
        if service in ('asyncio', 'tornado', 'trio', 'zmq'):
            # Every async source must suspend and complete using its real service.
            async def suspend():
                if service == 'trio':
                    await trio.sleep(0.01)
                else:
                    future = asyncio.get_running_loop().create_future()
                    if service == 'asyncio':
                        native.call_later(0.01, future.set_result, None)
                    elif service == 'tornado':
                        native.call_later(0.01, future.set_result, None)
                    else:
                        asyncio.get_running_loop().call_later(0.01, future.set_result, None)
                    await future
            async def async_timer():
                await suspend()
                seen.append('async timer')
            idle_started = []
            async def async_idle():
                if idle_started:
                    return
                idle_started.append(True)
                loop.remove_enter_idle(handles['async idle'])
                await suspend()
                seen.append('async idle')
            async def async_readable():
                try:
                    data = extra_reader.recv(1)
                except BlockingIOError:
                    return
                loop.remove_watch_file(handles['async file'])
                await suspend()
                seen.append(('async file', data))
            expected = {'idle', 'timer', 'async timer', 'async idle', ('async file', b'z'), b'a', b'b'}
        else:
            expected = {'idle', 'timer', b'a', b'b'}
        with socket_pair() as (extra_reader, extra_writer):
            extra_reader.setblocking(False)
            if service in ('asyncio', 'tornado', 'trio', 'zmq'):
                loop.alarm(0, async_timer)
                handles['async idle'] = loop.enter_idle(async_idle)
                handles['async file'] = loop.watch_file(extra_reader.fileno(), async_readable)
                extra_writer.sendall(b'z')
            # Native service scheduling must join the same adapter run.
            if service == 'asyncio':
                native.call_later(0.01, seen.append, 'native')
            elif service == 'tornado':
                native.call_later(0.01, seen.append, 'native')
            elif service == 'twisted':
                native.callLater(0.01, seen.append, 'native')
            elif service == 'glib':
                def native_callback():
                    seen.append('native')
                    return False
                GLib.timeout_add(10, native_callback)
            writer.sendall(b'a')
            completed_at = []
            def completed():
                if not expected.issubset(seen):
                    return False
                if service not in ('trio', 'zmq') and 'native' not in seen:
                    return False
                if not completed_at:
                    completed_at.append(time.monotonic())
                return time.monotonic() >= completed_at[0] + 0.05
            run_to(loop, completed)
            assert expected.issubset(seen), seen
            assert seen.count('idle') == seen.count('timer') == 1
            assert 'cancelled' not in seen
            assert seen.count(b'a') == seen.count(b'b') == 1
            assert reader.recv(1) == b'c'
    cleanup()
    if service == 'zmq':
        zmq_message_delivery()


@contextlib.contextmanager
def socket_pair():
    reader, writer = socket.socketpair()
    try:
        yield reader, writer
    finally:
        reader.close()
        writer.close()


class ApplicationDriver:
    """Keep assertion failures visible even where application alarms log errors."""
    def __init__(self, app):
        self.app = app
        self.errors = []

    def alarm(self, delay, callback, data=None):
        def checked(app, payload):
            try:
                callback(app, payload)
            except velnora.ExitMainLoop:
                raise
            except Exception as error:
                self.errors.append(error)
                raise velnora.ExitMainLoop from error
        return self.app.set_alarm_in(delay, checked, data)

    def run(self):
        def expired():
            raise AssertionError('Application did not reach its expected completion')
        guard = self.app.event_loop.alarm(4, expired)
        try:
            self.app.run()
        finally:
            self.app.event_loop.remove_alarm(guard)
        if self.errors:
            raise self.errors[0]


def zmq_message_delivery():
    """Read actual ZeroMQ messages through the message-socket public entry."""
    import asyncio
    import zmq
    loop = velnora.ZMQEventLoop()
    received = []
    with zmq.Context() as context:
        with context.socket(zmq.PAIR) as reader, context.socket(zmq.PAIR) as writer:
            reader.bind('inproc://acceptance-messages')
            writer.connect('inproc://acceptance-messages')
            async def deliver():
                try:
                    message = reader.recv(zmq.NOBLOCK)
                except zmq.Again:
                    return
                loop.remove_watch_queue(handle)
                await asyncio.sleep(0.01)
                received.append(message)
            handle = loop.watch_queue(reader, deliver)
            writer.send(b'message payload')
            run_to(loop, lambda: bool(received))
            assert received == [b'message payload']


def terminal_mouse_modes(output, initial=()):
    """Observe standard DEC private mouse tracking mode transitions."""
    import re
    active = set(initial)
    for match in re.finditer(r'\x1b\[\?([0-9;]+)([hl])', output):
        for parameter in match[1].split(';'):
            mode = int(parameter)
            if mode in (1000, 1002, 1003):
                if match[2] == 'h':
                    active.add(mode)
                else:
                    active.discard(mode)
    return active
