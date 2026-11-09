# feature: F17
"""Real POSIX tty input through the public direct-screen lifecycle."""
import contextlib
from concurrent.futures import ThreadPoolExecutor
import fcntl
import os
import pty
import re
import select
import subprocess
import sys
import signal
import struct
import termios
import time

import velnora
from velnora.display.raw import Screen

from _helpers import deadline
from F01_helpers import encoding_state


@contextlib.contextmanager
def tty_screen(**screen_options):
    """Yield a started screen and its real tty peer; restore owned resources."""
    master, slave = pty.openpty()
    try:
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
        with os.fdopen(os.dup(slave), 'r', encoding='utf-8') as source, \
             os.fdopen(os.dup(slave), 'w', encoding='utf-8') as target, encoding_state():
            velnora.set_encoding('utf-8')
            screen = Screen(input=source, output=target,
                            bracketed_paste_mode=False, focus_reporting=False,
                            **screen_options)
            screen.set_input_timeouts(max_wait=0.02)
            screen.start()
            try:
                yield screen, master, slave
            finally:
                screen.stop()
    finally:
        os.close(slave)
        os.close(master)


def tty_keys(screen, count):
    """Collect a known number of public events without assuming read batches."""
    result = []
    with deadline(3):
        while len(result) < count:
            result.extend(screen.get_input())
    assert len(result) == count, result
    return result


def tty_resize(slave, columns, rows):
    """Change kernel tty dimensions and deliver the normal resize signal."""
    fcntl.ioctl(slave, termios.TIOCSWINSZ,
                struct.pack('HHHH', rows, columns, 0, 0))
    os.kill(os.getpid(), signal.SIGWINCH)


def tty_fragment(screen, peer, prefix, suffix):
    """Read genuinely separated writes; propagate writer and reader failures."""
    def finish():
        time.sleep(0.03)
        os.write(peer, suffix)

    os.write(peer, prefix)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(finish)
        try:
            return tty_keys(screen, 1)
        finally:
            pending.result(timeout=1)


def tty_output(peer):
    """Drain available tty output without treating read failures as absence."""
    chunks = []
    with deadline(3):
        while select.select([peer], [], [], 0.03)[0]:
            data = os.read(peer, 65536)
            if not data:
                raise RuntimeError("Terminal output closed while observing it")
            chunks.append(data)
    return b"".join(chunks).decode("utf-8")


def emitted_glyphs(data):
    """Read VT printable output and OSC 8 URI scope, not cursor placement.

    CSI parameters and OSC termination are parsed structurally. This is an
    output observer, not a terminal emulator or evidence of displayed layout.
    All unsupported/truncated control strings fail rather than disappearing.
    """
    glyphs = []
    active_uri = None
    i = 0
    while i < len(data):
        c = data[i]
        i += 1
        if c == "\x1b":
            assert i < len(data), "Truncated terminal escape"
            introducer = data[i]
            i += 1
            if introducer == "[":
                while i < len(data) and not "@" <= data[i] <= "~":
                    assert " " <= data[i] <= "?", "Invalid CSI byte"
                    i += 1
                assert i < len(data), "Truncated CSI"
                i += 1
            elif introducer == "]":
                start = i
                while i < len(data) and data[i] != "\x07" and data[i:i+2] != "\x1b\\":
                    i += 1
                assert i < len(data), "Truncated OSC"
                body = data[start:i]
                i += 1 if data[i] == "\x07" else 2
                fields = body.split(";", 2)
                if fields[0] == "8":
                    assert len(fields) == 3, "Invalid OSC 8"
                    active_uri = fields[2] or None
            elif " " <= introducer <= "/":
                while i < len(data) and " " <= data[i] <= "/":
                    i += 1
                assert i < len(data) and "0" <= data[i] <= "~", "Invalid escape"
                i += 1
            else:
                assert "0" <= introducer <= "~", "Invalid escape final"
        elif c >= " " and c != "\x7f":
            glyphs.append((c, active_uri))
    return glyphs


def basic_tty_frame(markup, *, hyperlink=None, term="xterm-256color",
                    foreground="dark red", background="default", cursor=None):
    """Run the real curses backend in an isolated tty subprocess.

    Return dimension observations, tty states and actual output. The child
    reports results through a separate pipe; its stderr and exit remain errors.
    """
    import json
    master, slave = pty.openpty()
    read_result, write_result = os.pipe()
    read_continue, write_continue = os.pipe()
    try:
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
        before = termios.tcgetattr(slave)
        code = r"""
import json, os, termios
import velnora
from velnora.display.curses import Screen
screen = Screen()
with screen.start():
    active = termios.tcgetattr(0)
    size = screen.get_cols_rows()
    attr = velnora.AttrSpec(os.environ['F17_FOREGROUND'], os.environ['F17_BACKGROUND'],
                          hyperlink=json.loads(os.environ['F17_HYPERLINK']))
    position = json.loads(os.environ['F17_CURSOR'])
    content = json.loads(os.environ['F17_MARKUP'])
    text = velnora.Text(content) if position is None else velnora.Edit('', content, edit_pos=position)
    canvas = velnora.Filler(velnora.AttrMap(text, attr), valign='top').render(size, focus=position is not None)
    screen.draw_screen(size, canvas)
    os.write(int(os.environ['F17_RESULT_FD']), (json.dumps([size, active[:6]]) + '\n').encode())
    assert os.read(int(os.environ['F17_CONTINUE_FD']), 1) == b'x'
"""
        env = dict(os.environ, TERM=term, F17_MARKUP=json.dumps(markup),
                   F17_HYPERLINK=json.dumps(hyperlink),
                   F17_RESULT_FD=str(write_result), F17_CONTINUE_FD=str(read_continue),
                   F17_FOREGROUND=foreground, F17_BACKGROUND=background,
                   F17_CURSOR=json.dumps(cursor))
        process = subprocess.Popen([sys.executable, '-c', code], stdin=slave, stdout=slave,
                                   stderr=subprocess.PIPE, pass_fds=(write_result, read_continue), env=env)
        try:
            os.close(write_result)
            write_result = None
            with deadline(10):
                observed = json.loads(os.read(read_result, 65536))
            output = tty_output(master)
            os.write(write_continue, b'x')
            _, errors = process.communicate(timeout=10)
            assert process.returncode == 0, errors.decode()
            return observed[0], observed[1], before, termios.tcgetattr(slave), output
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            process.stderr.close()
    finally:
        if write_result is not None:
            os.close(write_result)
        os.close(read_result)
        os.close(read_continue)
        os.close(write_continue)
        os.close(slave)
        os.close(master)


class VTModel:
    """Small independent VT/ECMA-48 interpreter for observing drawn output.

    It interprets printable text, cursor motion, erasure, insertion, SGR colour
    and effects, DEC private modes and alternate screens. Each cell records its
    character and the SGR state that wrote it. Colours are kept as
    ('default',), ('index', n) or ('rgb', r, g, b); basic SGR 30-37/40-47 map
    to indices 0-7 and 90-97/100-107 to 8-15. Unknown control sequences that
    cannot move text are ignored; feeding is incremental across writes.
    """

    def __init__(self, columns, rows):
        self.columns, self.rows = columns, rows
        self.main = self._blank_screen()
        self.alternate = None
        self.x = self.y = 0
        self.saved = (0, 0)
        self.modes = set()
        self.insert = False
        self.cursor_visible = True
        self.sgr = self._default_sgr()
        self.pending = ''
        self.left_alternate = None

    @staticmethod
    def _default_sgr():
        return {'fg': ('default',), 'bg': ('default',), 'bold': False,
                'underline': False, 'reverse': False}

    def _blank(self):
        return (' ', dict(self.sgr, bold=False, underline=False, reverse=False))

    def _blank_screen(self):
        return [[(' ', self._default_sgr()) for _ in range(self.columns)]
                for _ in range(self.rows)]

    @property
    def screen(self):
        return self.main if self.alternate is None else self.alternate

    def resize(self, columns, rows):
        for name in ('main', 'alternate'):
            grid = getattr(self, name)
            if grid is None:
                continue
            grid = [row[:columns] + [(' ', self._default_sgr())] * (columns - len(row))
                    for row in grid[:rows]]
            grid += [[(' ', self._default_sgr())] * columns for _ in range(rows - len(grid))]
            setattr(self, name, grid)
        self.columns, self.rows = columns, rows
        self._clamp()

    def _clamp(self):
        self.x = max(0, min(self.x, self.columns - 1))
        self.y = max(0, min(self.y, self.rows - 1))

    def text(self, row):
        return ''.join(c for c, a in self.screen[row])

    def cell(self, column, row):
        return self.screen[row][column]

    def find(self, word):
        """Return (column, row) of the single on-screen occurrence of word."""
        hits = [(row.index(word), y) for y, row in enumerate(
            self.text(y) for y in range(self.rows)) if word in row]
        assert len(hits) == 1, (word, hits)
        return hits[0]

    def feed(self, data):
        data = self.pending + data
        self.pending = ''
        i = 0
        while i < len(data):
            c = data[i]
            if c == '\x1b':
                end = self._escape(data, i)
                if end is None:
                    self.pending = data[i:]
                    return
                i = end
                continue
            i += 1
            if c == '\r':
                self.x = 0
            elif c == '\n' or c in '\x0b\x0c':
                self._linefeed()
            elif c == '\b':
                self.x = max(0, min(self.x, self.columns - 1) - 1)
            elif c == '\t':
                self.x = min(self.columns - 1, (self.x // 8 + 1) * 8)
            elif c >= ' ' and c != '\x7f':
                self._put(c)

    def _linefeed(self):
        if self.y == self.rows - 1:
            del self.screen[0]
            self.screen.append([self._blank() for _ in range(self.columns)])
        else:
            self.y += 1

    def _put(self, c):
        row = self.screen[self.y]
        if self.x >= self.columns:
            self.x = 0
            self._linefeed()
            row = self.screen[self.y]
        if self.insert:
            row.insert(self.x, (c, dict(self.sgr)))
            del row[self.columns:]
        else:
            row[self.x] = (c, dict(self.sgr))
        self.x += 1
        if self.x >= self.columns and 'no-wrap' in self.modes:
            self.x = self.columns - 1

    def _escape(self, data, i):
        if i + 1 >= len(data):
            return None
        kind = data[i + 1]
        if kind == '[':
            j = i + 2
            while j < len(data) and not '@' <= data[j] <= '~':
                j += 1
            if j >= len(data):
                return None
            self._csi(data[i + 2:j], data[j])
            return j + 1
        if kind in ']PX^_':
            j = i + 2
            while j < len(data) and data[j] != '\x07' and data[j:j + 2] != '\x1b\\':
                j += 1
            if j >= len(data) or (data[j] == '\x1b' and j + 1 >= len(data)):
                return None
            return j + (1 if data[j] == '\x07' else 2)
        if ' ' <= kind <= '/':
            j = i + 2
            while j < len(data) and ' ' <= data[j] <= '/':
                j += 1
            return None if j >= len(data) else j + 1
        if kind == '7':
            self.saved = (self.x, self.y)
        elif kind == '8':
            self.x, self.y = self.saved
        elif kind == 'E':
            self.x = 0
            self._linefeed()
        elif kind == 'D':
            self._linefeed()
        elif kind == 'M':
            if self.y == 0:
                self.screen.insert(0, [self._blank() for _ in range(self.columns)])
                del self.screen[self.rows:]
            else:
                self.y -= 1
        elif kind == 'c':
            self.__init__(self.columns, self.rows)
        return i + 2

    def _csi(self, body, final):
        private = body[:1] if body[:1] in '?<=>' else ''
        params = body[len(private):]
        if any(not ('0' <= ch <= '9' or ch in ';:') for ch in params):
            return  # intermediate bytes: not a sequence this model draws with
        fields = params.split(';') if params else []
        if private:
            if final in 'hl' and private == '?':
                for field in fields:
                    self._private_mode(int(field or 0), final == 'h')
            return
        nums = [int(f.split(':')[0]) if f.split(':')[0] else None for f in fields]
        def n(k=0, default=1):
            value = nums[k] if k < len(nums) else None
            return default if value is None or (value == 0 and default == 1) else value
        row = self.screen[self.y]
        if final in 'Hf':
            self.y, self.x = n(0) - 1, n(1) - 1
            self._clamp()
        elif final == 'A':
            self.y -= n(); self._clamp()
        elif final in 'Be':
            self.y += n(); self._clamp()
        elif final in 'Ca':
            self.x += n(); self._clamp()
        elif final == 'D':
            self.x = min(self.x, self.columns - 1) - n(); self._clamp()
        elif final == 'E':
            self.y += n(); self.x = 0; self._clamp()
        elif final == 'F':
            self.y -= n(); self.x = 0; self._clamp()
        elif final in 'G`':
            self.x = n() - 1; self._clamp()
        elif final == 'd':
            self.y = n() - 1; self._clamp()
        elif final == 'K':
            x = min(self.x, self.columns - 1)
            span = {0: range(x, self.columns), 1: range(0, x + 1),
                    2: range(self.columns)}.get(n(0, 0), ())
            for k in span:
                row[k] = self._blank()
        elif final == 'J':
            mode = n(0, 0)
            rows = {0: range(self.y + 1, self.rows), 1: range(0, self.y),
                    2: range(self.rows), 3: ()}.get(mode, ())
            for r in rows:
                self.screen[r] = [self._blank() for _ in range(self.columns)]
            if mode in (0, 1):
                self._csi(str(mode), 'K')
        elif final == 'X':
            for k in range(self.x, min(self.columns, self.x + n())):
                row[k] = self._blank()
        elif final == '@':
            for _ in range(n()):
                row.insert(min(self.x, self.columns), self._blank())
            del row[self.columns:]
        elif final == 'P':
            x = min(self.x, self.columns - 1)
            del row[x:x + n()]
            row.extend(self._blank() for _ in range(self.columns - len(row)))
        elif final == 'b' and self.x > 0:
            last = row[self.x - 1][0]
            for _ in range(n()):
                self._put(last)
        elif final in 'hl':
            if 4 in nums:
                self.insert = final == 'h'
        elif final == 'm':
            self._sgr(fields or ['0'])
        elif final == 's':
            self.saved = (self.x, self.y)
        elif final == 'u':
            self.x, self.y = self.saved
        elif final == 'r':
            self.x = self.y = 0
        # Reports, queries and window operations do not draw.

    def _private_mode(self, mode, enable):
        if mode == 25:
            self.cursor_visible = enable
        elif mode == 7:
            (self.modes.discard if enable else self.modes.add)('no-wrap')
        elif mode in (47, 1047, 1049):
            if mode == 1049 and enable:
                self.saved = (self.x, self.y)
            if enable and self.alternate is None:
                self.alternate = self._blank_screen()
            elif enable and mode != 47:
                self.alternate = self._blank_screen()
            elif not enable and self.alternate is not None:
                self.left_alternate = self.alternate
                self.alternate = None
                if mode == 1049:
                    self.x, self.y = self.saved
        if enable:
            self.modes.add(mode)
        else:
            self.modes.discard(mode)

    def _sgr(self, fields):
        parts = []
        for field in fields:
            sub = field.split(':')
            if len(sub) > 1 and sub[0] in ('38', '48'):
                # ITU colon form: 38:2:<colourspace>:r:g:b or 38:2:r:g:b, 38:5:n
                values = [int(v) if v else 0 for v in sub[1:]]
                if values and values[0] == 2 and len(values) == 5:
                    values = values[:1] + values[2:]
                parts.append((int(sub[0]), values))
            else:
                parts.append(int(sub[0]) if sub[0] else 0)
        k = 0
        while k < len(parts):
            p = parts[k]
            k += 1
            if isinstance(p, tuple):
                target = 'fg' if p[0] == 38 else 'bg'
                values = p[1]
                self.sgr[target] = (('index', values[1]) if values[0] == 5 else
                                    ('rgb', *values[1:4]))
                continue
            if p == 0:
                self.sgr = self._default_sgr()
            elif p == 1:
                self.sgr['bold'] = True
            elif p == 22:
                self.sgr['bold'] = False
            elif p == 4:
                self.sgr['underline'] = True
            elif p == 24:
                self.sgr['underline'] = False
            elif p == 7:
                self.sgr['reverse'] = True
            elif p == 27:
                self.sgr['reverse'] = False
            elif 30 <= p <= 37:
                self.sgr['fg'] = ('index', p - 30)
            elif 90 <= p <= 97:
                self.sgr['fg'] = ('index', p - 82)
            elif p == 39:
                self.sgr['fg'] = ('default',)
            elif 40 <= p <= 47:
                self.sgr['bg'] = ('index', p - 40)
            elif 100 <= p <= 107:
                self.sgr['bg'] = ('index', p - 92)
            elif p == 49:
                self.sgr['bg'] = ('default',)
            elif p in (38, 48):
                target = 'fg' if p == 38 else 'bg'
                if k < len(parts) and parts[k] == 5:
                    self.sgr[target] = ('index', parts[k + 1])
                    k += 2
                elif k < len(parts) and parts[k] == 2:
                    self.sgr[target] = ('rgb', *parts[k + 1:k + 4])
                    k += 4

    def mouse_modes(self):
        return self.modes & {9, 1000, 1001, 1002, 1003}




_KEYBOARD_CONTROL = re.compile(r'\x1b\[([<>=])([0-9;]*)([um])')


def keyboard_controls(data):
    """Keyboard-reporting changes in display output, in order.

    Returns ('push', flags) for ESC [ > flags u, ('pop', count) for ESC [ < u,
    ('set', flags) for ESC [ = flags u, and ('modify', value or None) for the
    modifyOtherKeys resource ESC [ > 4 ; value m. Queries are not changes.
    """
    found = []
    for introducer, body, final in _KEYBOARD_CONTROL.findall(data):
        fields = [int(field) if field else None for field in body.split(';')] if body else []
        if final == 'u':
            kind = {'>': 'push', '<': 'pop', '=': 'set'}[introducer]
            found.append((kind, fields[0] if fields else None))
        elif introducer == '>' and fields and fields[0] == 4:
            found.append(('modify', fields[1] if len(fields) > 1 else None))
    return found


@contextlib.contextmanager
def basic_tty_session():
    """Run a real basic screen with an independent application control channel."""
    import json
    import socket
    master, slave = pty.openpty()
    parent, child = socket.socketpair()
    parent.settimeout(10)
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
    code = r"""
import json, os, socket
import velnora
from velnora.display.curses import Screen
channel = socket.socket(fileno=int(os.environ['F17_CHANNEL']))
f = channel.makefile('rwb', buffering=0)
velnora.set_encoding('utf-8')
screen = Screen()
with screen.start():
    f.write(b'{"ready": true}\n')
    for line in f:
        request = json.loads(line)
        if request == 'read':
            answer = screen.get_input()
        elif request == 'size':
            answer = screen.get_cols_rows()
        elif request == 'mouse':
            screen.set_mouse_tracking(True)
            answer = True
        elif request == 'disable':
            try:
                screen.set_mouse_tracking(False)
            except NotImplementedError:
                answer = 'unsupported'
            else:
                answer = 'disabled'
        elif request == 'stop':
            break
        else:
            raise ValueError(request)
        f.write((json.dumps(answer) + '\n').encode())
"""
    process = subprocess.Popen([sys.executable, '-c', code], stdin=slave, stdout=slave,
                               stderr=subprocess.PIPE, pass_fds=(child.fileno(),),
                               env=dict(os.environ, TERM='xterm-256color', F17_CHANNEL=str(child.fileno())))
    child.close()
    stream = parent.makefile('rwb', buffering=0)
    def request(command):
        stream.write((json.dumps(command) + '\n').encode())
        answer = stream.readline()
        assert answer, 'Basic screen closed its control channel'
        return json.loads(answer)
    try:
        assert json.loads(stream.readline()) == {'ready': True}
        yield request, master, slave, process
        stream.write(b'"stop"\n')
        _, errors = process.communicate(timeout=10)
        assert process.returncode == 0, errors.decode()
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        process.stderr.close()
        stream.close()
        parent.close()
        os.close(slave)
        os.close(master)


def keyboard_reporting_state(data, state, *, initial_modify):
    """Apply public reporting controls as a terminal, accepting equivalent changes."""
    stack, modify = list(state[0]), state[1]
    for introducer, body, final in _KEYBOARD_CONTROL.findall(data):
        fields = [int(field) if field else 0 for field in body.split(';')] if body else []
        if final == 'm':
            if introducer == '>' and fields and fields[0] == 4:
                modify = fields[1] if len(fields) > 1 else initial_modify
        elif introducer == '>':
            stack.append(fields[0] if fields else 0)
        elif introducer == '<':
            count = fields[0] if fields else 1
            del stack[max(1, len(stack) - count):]
        elif introducer == '=':
            flags = fields[0] if fields else 0
            mode = fields[1] if len(fields) > 1 else 1
            assert mode in (1, 2, 3), 'Unsupported keyboard flag update mode'
            stack[-1] = flags if mode == 1 else stack[-1] | flags if mode == 2 else stack[-1] & ~flags
    return tuple(stack), modify
