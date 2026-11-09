# feature: F09
"""Application observations of public session requests and control events."""
import asyncio
from contextlib import asynccontextmanager

import velnora

from _helpers import bounded
from F02_helpers import certificate_identity
from F07_helpers import AccessPolicy, access_connect


class SessionApplication(velnora.SSHServerSession):
    def __init__(self, ready, *, accept=True, accept_terminal=True):
        self.ready = ready
        self.accept = accept
        self.accept_terminal = accept_terminal
        self.events = asyncio.Queue()
        self.terminal_request = None

    def connection_made(self, channel):
        self.channel = channel

    def shell_requested(self):
        self.activity = ('shell', None)
        return self.accept

    def exec_requested(self, command):
        self.activity = ('command', command)
        return self.accept

    def subsystem_requested(self, subsystem):
        self.activity = ('subsystem', subsystem)
        return self.accept

    def pty_requested(self, term_type, term_size, term_modes):
        self.terminal_request = (term_type, term_size, dict(term_modes))
        return self.accept_terminal

    def session_started(self):
        self.ready.put_nowait(self)

    def terminal_size_changed(self, width, height, pixwidth, pixheight):
        self.events.put_nowait(('size', (width, height, pixwidth, pixheight)))

    def break_received(self, msec):
        self.events.put_nowait(('break', msec))
        return True

    def signal_received(self, signal):
        self.events.put_nowait(('signal', signal))


class SessionPeer(AccessPolicy):
    def __init__(self, ready, *, authenticated, handler, application_options):
        super().__init__(anonymous=not authenticated)
        self.ready = ready
        self.handler = handler
        self.application_options = application_options

    def session_requested(self):
        if not self.handler:
            return False
        return SessionApplication(self.ready, **self.application_options)


@asynccontextmanager
async def session_connection(*, authorization=None, client_keys=(), handler=True,
                             application_options=None, **server_options):
    ready = asyncio.Queue()
    host, _ = certificate_identity()
    async with velnora.listen(
            '127.0.0.1', 0, config=None, server_host_keys=[host],
            authorized_client_keys=authorization, line_editor=False,
            server_factory=lambda: SessionPeer(
                ready, authenticated=authorization is not None, handler=handler,
                application_options=application_options or {}),
            **server_options) as listener:
        async with access_connect(listener.get_port(), client_keys=list(client_keys)) as conn:
            yield conn, ready


async def observed_session(conn, ready, **options):
    streams = await bounded(conn.open_session(**options))
    application = await bounded(ready.get())
    return (*streams, application)


async def finish_session(writer, application, status=0):
    application.channel.exit(status)
    await bounded(writer.wait_closed())
