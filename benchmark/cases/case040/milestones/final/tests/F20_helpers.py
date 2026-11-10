# feature: F20
"""Real CGI processes, FIFOs, a real browser and a serial-attached display peer."""
import contextlib
import http.server
import json
import os
import pty
import select
import signal
import subprocess
import sys
import threading
import time
import tty

from _helpers import environment, run_process, temporary_directory


CGI_INPUT = r'''
import os
from velnora.display import web
web.set_preferences('Acceptance application', pipe_dir=os.environ['F20_PIPE_DIR'])
handled = web.handle_short_request()
assert handled is True
'''


WEB_INPUT_SESSION = r'''
import json, os, subprocess, sys
from pathlib import Path
from email.parser import Parser
from velnora.display import web

directory = Path(sys.argv[1])
scenario = json.loads((directory / 'scenario.json').read_text())
web.set_preferences('Acceptance application', pipe_dir=str(directory))
screen = web.Screen()
observed = []
try:
    screen.start()
    initial_size = screen.get_cols_rows()
    for request in scenario['requests']:
        env = dict(os.environ, REQUEST_METHOD='POST',
                   HTTP_X_VELNORA_ID=Path(screen.pipe_name).name.removeprefix('velnora_'),
                   HTTP_X_VELNORA_METHOD='multipart',
                   CONTENT_TYPE='text/plain; charset=' + request['encoding'],
                   F20_PIPE_DIR=str(directory))
        response = subprocess.run([sys.executable, '-c', scenario['cgi']],
                                  input=bytes.fromhex(request['body']),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env=env, timeout=5)
        assert response.returncode == 0, response.stderr.decode('utf-8', 'replace')
        headers = Parser().parsestr(response.stdout.decode('ascii'))
        keys = screen.get_input()
        observed.append(dict(headers={key.lower(): value for key, value in headers.items()}, keys=keys,
                             size=screen.get_cols_rows()))
    (directory / 'result.json').write_text(json.dumps(
        dict(initial_size=initial_size, requests=observed)))
finally:
    screen.stop()
'''


def cgi_input_session(initial_size, requests):
    """Return actual CGI headers, delivered keys and dimensions for each request.

    Requests carry byte bodies and declared codecs. The application receives
    each request through the FIFO created by Screen.start, never a supplied
    descriptor or a patched reader. Child failures and timeouts fail the probe.
    The JSON file is the probe's own carrier, not a product output format.
    """
    with temporary_directory() as directory:
        scenario = dict(cgi=CGI_INPUT, requests=[
            dict(encoding=encoding, body=body.hex()) for encoding, body in requests])
        (directory / 'scenario.json').write_text(json.dumps(scenario))
        result = run_process(
            [sys.executable, '-c', WEB_INPUT_SESSION, str(directory)],
            input=('window resize %d %d\n' % initial_size).encode('ascii'),
            env=environment({'HTTP_X_VELNORA_METHOD': 'multipart'}), timeout=20)
        assert result.returncode == 0, result.stderr.decode('utf-8', 'replace')
        return json.loads((directory / 'result.json').read_text())


@contextlib.contextmanager
def browser_page(width=900, height=600):
    """Yield a page of a real headless browser; launch failures fail the probe."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as driver:
        browser = driver.chromium.launch()
        try:
            yield browser.new_page(viewport={'width': width, 'height': height})
        finally:
            browser.close()


def load_fragment(page, fragment):
    page.set_content(f'<!DOCTYPE html><html><body>{fragment}</body></html>')


# Per-character geometry and computed style, independent of the markup used.
_CELLS = r"""
() => {
    const cells = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let node; (node = walker.nextNode());) {
        const parent = node.parentElement;
        if (['SCRIPT', 'STYLE', 'TITLE'].includes(parent.tagName)) continue;
        const style = getComputedStyle(parent);
        let background = 'rgba(0, 0, 0, 0)';
        for (let at = parent; at; at = at.parentElement) {
            const value = getComputedStyle(at).backgroundColor;
            if (value !== 'rgba(0, 0, 0, 0)' && value !== 'transparent') {
                background = value;
                break;
            }
        }
        for (let i = 0; i < node.data.length;) {
            const size = node.data.codePointAt(i) > 0xffff ? 2 : 1;
            const range = document.createRange();
            range.setStart(node, i);
            range.setEnd(node, i + size);
            const box = range.getBoundingClientRect();
            if (box.width > 0 && box.height > 0 && style.visibility !== 'hidden') {
                cells.push({ch: node.data.slice(i, i + size), x: box.x, y: box.y,
                            width: box.width, height: box.height,
                            color: style.color, background});
            }
            i += size;
        }
    }
    return cells;
}
"""


def page_rows(page):
    """Return displayed rows of cells, ordered by screen position."""
    rows = {}
    for cell in page.evaluate(_CELLS):
        cell['ch'] = cell['ch'].replace('\xa0', ' ')
        rows.setdefault(round(cell['y']), []).append(cell)
    return [sorted(rows[y], key=lambda cell: cell['x']) for y in sorted(rows)]


def row_text(row):
    return ''.join(cell['ch'] for cell in row)


def visible_lines(page):
    """Displayed nonblank rows without their trailing blanks."""
    lines = (row_text(row).rstrip() for row in page_rows(page))
    return [line for line in lines if line]


def selected_lines(page):
    """Text a user obtains by selecting the page with the keyboard."""
    page.keyboard.press('Control+A')
    text = page.evaluate('() => window.getSelection().toString()')
    lines = (line.replace('\xa0', ' ').rstrip() for line in text.split('\n'))
    return [line for line in lines if line]


def cell_pixels(page, cell):
    """PNG bytes of one displayed cell, so frames can be compared visually."""
    return page.screenshot(animations='disabled', clip={
        'x': cell['x'], 'y': cell['y'], 'width': cell['width'], 'height': cell['height']})


# The browser's own view of what a click follows.
_LINKS = r"""
() => Array.from(document.links).map(a => [a.href, a.textContent])
"""


def page_links(page):
    """Return {destination: text}, joining a link drawn in several adjacent pieces."""
    links = {}
    for href, text in page.evaluate(_LINKS):
        links[href] = links.get(href, '') + text
    return links


WEB_APPLICATION = r"""
import json, os, sys
import velnora
from velnora.display import web

web.set_preferences('Acceptance application', pipe_dir=os.environ['F20_PIPE_DIR'])
if web.handle_short_request():
    sys.exit(0)

velnora.set_encoding('utf-8')
size = velnora.Text('')
pressed = velnora.Text('PRESSED')
editor = velnora.Edit('TYPED ')
links = [velnora.Text((velnora.AttrSpec('default', 'default', hyperlink=target), label))
         for label, target in json.loads(os.environ['F20_LINKS'])]


class Root(velnora.Filler):
    def render(self, dimensions, focus=False):
        size.set_text('SIZE %d %d' % dimensions)
        return super().render(dimensions, focus)


def unhandled(key):
    if key != 'window resize':
        pressed.set_text(pressed.text + ' ' + key)


pile = velnora.Pile([editor, size, pressed, *links])
pile.focus_position = 0
velnora.MainLoop(Root(pile, valign='top'), screen=web.Screen(), unhandled_input=unhandled).run()
"""


@contextlib.contextmanager
def cgi_gateway(links):
    """Serve the application through a plain CGI gateway on the loopback address.

    Each request runs one CGI process with the standard request variables, and
    its stdout is forwarded as it is produced. Yields the page URL.
    """
    with temporary_directory() as directory:
        processes = []
        lock = threading.Lock()

        class Gateway(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def handle_cgi(self):
                body = self.rfile.read(int(self.headers.get('Content-Length') or 0))
                env = environment({'REQUEST_METHOD': self.command,
                                   'F20_PIPE_DIR': str(directory),
                                   'F20_LINKS': json.dumps(links),
                                   'CONTENT_TYPE': self.headers.get('Content-Type', ''),
                                   'CONTENT_LENGTH': str(len(body))})
                for name, value in self.headers.items():
                    env['HTTP_' + name.upper().replace('-', '_')] = value
                process = subprocess.Popen(
                    [sys.executable, '-c', WEB_APPLICATION], env=env, stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=None, start_new_session=True)
                with lock:
                    processes.append(process)
                with contextlib.suppress(BrokenPipeError):
                    process.stdin.write(body)
                    process.stdin.close()
                try:
                    self.forward(process.stdout.fileno())
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    process.stdout.close()

            def forward(self, source):
                head = b''
                while b'\r\n\r\n' not in head:
                    data = os.read(source, 65536)
                    if not data:
                        break
                    head += data
                head, _, rest = head.partition(b'\r\n\r\n')
                status, fields = 200, []
                for line in head.decode('latin-1').split('\r\n'):
                    name, _, value = line.partition(':')
                    if name.lower() == 'status':
                        status = int(value.split()[0])
                    elif name:
                        fields.append((name, value.strip()))
                self.send_response(status)
                for name, value in fields:
                    self.send_header(name, value)
                self.send_header('Transfer-Encoding', 'chunked')
                self.send_header('Connection', 'close')
                self.end_headers()
                self.close_connection = True
                while True:
                    if rest:
                        self.wfile.write(b'%x\r\n%s\r\n' % (len(rest), rest))
                        self.wfile.flush()
                    rest = os.read(source, 65536)
                    if not rest:
                        break
                self.wfile.write(b'0\r\n\r\n')

            do_GET = do_POST = handle_cgi

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Gateway)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}/application'
        finally:
            server.shutdown()
            server.server_close()
            with lock:
                running = list(processes)
            for process in running:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            thread.join(timeout=5)


def wait_for_text(page, needle, timeout=15000):
    page.wait_for_function('text => document.body.innerText.includes(text)',
                           arg=needle, timeout=timeout)


def crc16(data):
    """CRC-16/X-25, the checksum the device's serial packets carry."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return (crc ^ 0xFFFF).to_bytes(2, 'little')


def device_packet(command, data=b''):
    head = bytes([command, len(data)]) + bytes(data)
    return head + crc16(head)


class DisplayPeer:
    """Device end of a serial line: applies packets to a 20x4 character screen."""

    UNWRITTEN = '?'

    def __init__(self, auto_ack=True):
        self.auto_ack = auto_ack
        self.pending_ack = []
        self.master, self.slave = pty.openpty()
        tty.setraw(self.slave)
        self.path = os.ttyname(self.slave)
        self.buffer = b''
        self.rejected = []
        self.commands = 0
        self.rows = [[self.UNWRITTEN] * 20 for _ in range(4)]
        self.cursor = None
        self.cursor_style = None

    def close(self):
        os.close(self.master)
        os.close(self.slave)

    def lines(self):
        return [''.join(row) for row in self.rows]

    def visible_cursor(self):
        return self.cursor if self.cursor_style else None

    def apply(self, command, data):
        if command == 6:
            self.rows = [[' '] * 20 for _ in range(4)]
        elif command == 11 and len(data) == 2:
            self.cursor = (data[0], data[1])
        elif command == 12 and len(data) == 1:
            self.cursor_style = data[0]
        elif command == 31 and len(data) >= 2:
            column, row = data[0], data[1]
            for offset, byte in enumerate(data[2:]):
                if row < 4 and column + offset < 20:
                    self.rows[row][column + offset] = chr(byte)

    def service(self):
        """Apply and acknowledge complete packets; return whether any traffic occurred."""
        traffic = False
        while select.select([self.master], [], [], 0)[0]:
            self.buffer += os.read(self.master, 4096)
            traffic = True
        while len(self.buffer) >= 4 and len(self.buffer) >= self.buffer[1] + 4:
            end = self.buffer[1] + 2
            head, check = self.buffer[:end], self.buffer[end:end + 2]
            self.buffer = self.buffer[end + 2:]
            if crc16(head) != check:
                self.rejected.append(head)
                continue
            self.commands += 1
            self.apply(head[0], head[2:])
            self.pending_ack.append(head[0])
            if self.auto_ack:
                self.acknowledge()
        return traffic

    def acknowledge(self):
        command = self.pending_ack.pop(0)
        os.write(self.master, device_packet(0x40 | command))

    def report_key(self, *codes):
        os.write(self.master, b''.join(device_packet(0x80, [code]) for code in codes))


def settle(peer, screen, *, quiet=60, timeout=5.0):
    """Serve the device and poll the screen until traffic stops; return polled keys."""
    keys = []
    idle = 0
    limit = time.monotonic() + timeout
    while idle < quiet:
        assert time.monotonic() < limit, 'Serial exchange did not settle'
        traffic = peer.service()
        polled = screen.get_input_nonblocking()[1]
        keys.extend(polled)
        idle = 0 if traffic or polled else idle + 1
        time.sleep(0.001)
    return keys
