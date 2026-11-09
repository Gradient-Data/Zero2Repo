# feature: F08
"""Controlled application sessions carried over real SSH channels."""
import asyncio
from contextlib import asynccontextmanager

import velnora

from _helpers import bounded
from F02_helpers import certificate_identity
from F04_helpers import ConfigPeer
from F07_helpers import access_connect


class ChannelApplication(velnora.SSHServerSession):
    def __init__(self, ready):
        self.ready = ready
        self.received = bytearray()

    def connection_made(self, channel):
        self.channel = channel

    def exec_requested(self, command):
        self.command = command
        return command != 'reject'

    def session_started(self):
        self.ready.put_nowait(self)

    def data_received(self, data, datatype):
        self.received.extend(data)
        if self.command == 'echo':
            self.channel.write(data)

    def eof_received(self):
        if self.command == 'half':
            self.channel.write(b'after-input-eof')
        self.channel.write_eof()
        return True


class ChannelPeer(ConfigPeer):
    def __init__(self, ready):
        super().__init__()
        self.ready = ready

    def session_requested(self):
        return ChannelApplication(self.ready)


@asynccontextmanager
async def channel_connection():
    ready = asyncio.Queue()
    host, _ = certificate_identity()
    async with velnora.listen(
            '127.0.0.1', 0, config=None, server_host_keys=[host],
            server_factory=lambda: ChannelPeer(ready), encoding=None,
            window=1024) as listener:
        async with access_connect(listener.get_port()) as connection:
            yield connection, ready


async def application_stream(connection, ready, command='hold', **options):
    streams = await bounded(connection.open_session(command, **options))
    application = await bounded(ready.get())
    return (*streams, application)


async def delivery_fence(writer, reader):
    """Wait for an echo on another channel after earlier peer writes."""
    writer.write(b'fence')
    await bounded(writer.drain())
    assert await bounded(reader.readexactly(5)) == b'fence'


class InputCollector(velnora.SSHClientSession):
    def __init__(self):
        self.pieces = []

    def data_received(self, data, datatype):
        self.pieces.append(data)
