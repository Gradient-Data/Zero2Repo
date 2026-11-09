# feature: F19
"""Real PTY child with an independent, bounded JSON control channel."""
import json
import os
import socket
import sys
import time
from contextlib import contextmanager

import velnora
from _helpers import canvas_snapshot, temporary_directory, run_process, environment
from F01_helpers import encoding_state

CHILD = r'''
import json, os, select, socket, sys, termios, tty
s = socket.socket(socket.AF_UNIX)
s.connect(os.environ['F19_CHANNEL'])
f = s.makefile('rwb', buffering=0)
tty.setraw(0)
f.write(b'{"ready": true}\n')
for line in f:
    q = json.loads(line)
    op = q['op']
    if op == 'emit':
        data = bytes.fromhex(q['data'])
        while data:
            data = data[os.write(1, data):]
        answer = True
    elif op == 'input':
        data = b''
        while select.select([0], [], [], 0.08)[0]:
            data += os.read(0, 65536)
        answer = data.hex()
    elif op == 'info':
        size = os.get_terminal_size(0)
        answer = {'env': dict(os.environ), 'size': [size.columns, size.lines], 'pid': os.getpid()}
    elif op == 'exit':
        break
    else:
        raise ValueError(op)
    f.write(json.dumps(answer).encode() + b'\n')
'''


class ChildTerminal:
    """Drive public Terminal entries; never inject directly into its canvas."""
    def __init__(self, terminal, connection, size):
        self.terminal = terminal
        self.connection = connection
        self.file = connection.makefile('rwb', buffering=0)
        self.size = size
        self.titles = []
        self.serial = 0
        velnora.connect_signal(terminal, 'title', lambda source, title: self.titles.append(title))
        assert json.loads(self.file.readline()) == {'ready': True}

    def request(self, op, **fields):
        self.file.write(json.dumps(dict(op=op, **fields)).encode() + b'\n')
        line = self.file.readline()
        assert line, 'Child control channel closed without a reply'
        return json.loads(line)

    def snapshot(self):
        return canvas_snapshot(self.terminal.render(self.size))

    def rows(self):
        return tuple(b''.join(cell[2] for cell in row) for row in self.snapshot()['content'])

    def visible_rows(self):
        """Decode public canvas carriers to the characters a terminal displays."""
        graphics = dict(zip('_`abcdefghijklmnopqrstuvwxyz{|}~',
                            '▮◆▒␉␌␍␊°±␤␋┘┐┌└┼⎺⎻─⎼⎽├┤┴┬│≤≥π≠£·'))
        translation = str.maketrans(graphics)
        # Attribute boundaries may split a multibyte UTF-8 character.
        return tuple(b''.join(data.decode('ascii').translate(translation).encode('utf-8')
                              if charset == '0' else data
                              for _, charset, data in row).decode('utf-8')
                     for row in self.snapshot()['content'])

    def emit(self, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        self.serial += 1
        marker = 'f19-barrier-' + str(self.serial)
        self.file.write(json.dumps(dict(op='emit', data=(data + b'\x1b]2;' + marker.encode() + b'\x07').hex())).encode() + b'\n')
        end = time.monotonic() + 8
        while marker not in self.titles:
            assert time.monotonic() < end, 'Child output did not reach the terminal'
            self.terminal.wait_and_feed(0.05)
        assert json.loads(self.file.readline()) is True
        return self.rows()

    def keys(self, *keys):
        return tuple(self.terminal.keypress(self.size, key) for key in keys)

    def received(self):
        return bytes.fromhex(self.request('input'))

    def resize(self, size):
        self.size = size
        self.terminal.render(size)
        return self.rows()


@contextmanager
def child_terminal(size=(16, 5), *, kind='command', env=None):
    with temporary_directory() as directory, encoding_state():
        velnora.set_encoding('utf-8')
        listener = socket.socket(socket.AF_UNIX)
        listener.settimeout(8)
        channel = str(directory / 'control')
        listener.bind(channel)
        listener.listen(1)
        previous = os.environ.get('F19_CHANNEL')
        os.environ['F19_CHANNEL'] = channel
        supplied = None if env is None else dict(env, F19_CHANNEL=channel)
        if kind == 'callable':
            def command():
                exec(CHILD, {'__name__': '__main__'})
        elif kind == 'shell':
            script = directory / 'application-shell'
            script.write_text('#!' + sys.executable + '\n' + CHILD)
            script.chmod(0o700)
            supplied = dict(os.environ if supplied is None else supplied, SHELL=str(script))
            command = None
        else:
            command = [sys.executable, '-c', CHILD]
        terminal = velnora.Terminal(command, env=supplied)
        connection = driver = None
        try:
            terminal.render(size)
            connection, _ = listener.accept()
            connection.settimeout(8)
            driver = ChildTerminal(terminal, connection, size)
            yield driver
        finally:
            terminal.terminate()
            if driver is not None:
                driver.file.close()
            if connection is not None:
                connection.close()
            listener.close()
            if previous is None:
                del os.environ['F19_CHANNEL']
            else:
                os.environ['F19_CHANNEL'] = previous


def assert_terminal_screen(driver, rows, cursor=None):
    """Compare caller-authored visible rows, including their trailing blanks."""
    expected = tuple(row.encode() if isinstance(row, str) else row for row in rows)
    actual = driver.rows()
    assert actual == tuple(row.ljust(driver.size[0], b' ') for row in expected), actual
    if cursor is not None:
        assert driver.terminal.get_cursor_coords(driver.size) == cursor


def focused_terminal_probe():
    """Use real stdin in a subprocess rather than pytest's stdin pseudofile."""
    code = """
from F19_helpers import child_terminal
with child_terminal((6, 5)) as child:
    assert child.terminal.render(child.size, focus=True).cursor == (0, 0)
"""
    return run_process([sys.executable, '-c', code],
                       env=environment({'PYTHONPATH': os.path.dirname(__file__)}),
                       timeout=12)
