# feature: F11
"""Real terminal sessions and an independent VT display observer."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import sys

import velnora

from _helpers import bounded
from F02_helpers import certificate_identity
from F07_helpers import AccessPolicy, access_connect
from F09_helpers import SessionApplication, finish_session

# Pure Python upstream wheels are read directly; no install or network at runtime.
for asset in ('F11_wcwidth.whl', 'F11_pyte.whl'):
    path = Path(__file__).with_name(asset)
    if not path.is_file():
        raise FileNotFoundError(path)
    sys.path.insert(0, str(path))
import pyte


class EditingApplication(SessionApplication):
    def __init__(self, ready):
        super().__init__(ready)
        self.input = asyncio.Queue()
        self.pending = ''

    def data_received(self, data, datatype):
        assert datatype is None
        self.input.put_nowait(data)

    def signal_received(self, signal):
        if signal == 'FENCE':
            self.channel.write_stderr('!')
        else:
            super().signal_received(signal)


class EditingClient(velnora.SSHClientSession):
    def __init__(self, width):
        self.output = ''
        self.fences = asyncio.Queue()
        self.screen = pyte.Screen(width, 24)
        self.terminal = pyte.Stream(self.screen)

    def data_received(self, data, datatype):
        if datatype == velnora.EXTENDED_DATA_STDERR:
            for char in data:
                self.fences.put_nowait(char)
        else:
            assert datatype is None
            self.output += data
            self.terminal.feed(data)


@asynccontextmanager
async def editing_session(*, width=80, **options):
    ready = asyncio.Queue()
    key, _ = certificate_identity()
    class Peer(AccessPolicy):
        def session_requested(self):
            return EditingApplication(ready)
    async with velnora.listen(
            '127.0.0.1', 0, config=None, server_host_keys=[key],
            server_factory=lambda: Peer(anonymous=True), **options) as listener:
        async with access_connect(listener.get_port()) as conn:
            client = EditingClient(width)
            channel, _ = await bounded(conn.create_session(
                lambda: client, term_type='ansi', term_size=(width, 24)))
            app = await bounded(ready.get())
            try:
                yield channel, client, app
            finally:
                await finish_session(channel, app)


async def edit_send(channel, client, text=''):
    """Fence all preceding input/output using ordered requests on the same channel."""
    if text:
        channel.write(text)
    channel.send_signal('FENCE')
    assert await bounded(client.fences.get()) == '!'


async def submitted(app, size=None):
    while (len(app.pending) < size if size is not None else '\n' not in app.pending):
        app.pending += await bounded(app.input.get())
    end = size if size is not None else app.pending.index('\n') + 1
    result, app.pending = app.pending[:end], app.pending[end:]
    return result
