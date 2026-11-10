# feature: F12
"""Real forwarding peers and bounded public stream observations."""
import asyncio
from contextlib import asynccontextmanager

import velnora

from _helpers import bounded, managed_resource
from F02_helpers import certificate_identity
from F07_helpers import AccessPolicy, access_connect


class SocketDestination(asyncio.Protocol):
    """Independent socket peer: greeting, byte echo, then an EOF response."""
    def __init__(self, greeting):
        self.greeting = greeting

    def connection_made(self, transport):
        self.transport = transport
        transport.write(self.greeting)

    def data_received(self, data):
        self.transport.write(data)

    def eof_received(self):
        self.transport.write(b'after-half-close')
        return False


@asynccontextmanager
async def forwarding_destination(*, path=None, greeting=b'destination-ready\x00'):
    loop = asyncio.get_running_loop()
    factory = lambda: SocketDestination(greeting)
    create = (lambda: loop.create_unix_server(factory, path)) if path else (
        lambda: loop.create_server(factory, '127.0.0.1', 0))
    async with managed_resource(create, close=lambda s: s.close(),
                                wait_closed=lambda s: s.wait_closed()) as server:
        yield str(path) if path else server.sockets[0].getsockname()[1]


class ForwardApplication(velnora.SSHTCPSession):
    def connection_made(self, channel):
        self.channel = channel

    def session_started(self):
        self.channel.write(b'application-ready\x00')

    def data_received(self, data, datatype):
        self.channel.write(data)

    def eof_received(self):
        self.channel.write(b'after-half-close')
        self.channel.write_eof()
        return True


class ForwardPolicy(AccessPolicy):
    def __init__(self, *, authenticated=False):
        super().__init__(anonymous=not authenticated)
        self.tcp_requests = []
        self.unix_requests = []
        self.listen_requests = []
        self.unix_listen_requests = []
        self.direct_allowed = True
        self.listen_allowed = True
        self.application = False

    def connection_requested(self, dest_host, dest_port, orig_host, orig_port):
        self.tcp_requests.append((dest_host, dest_port, orig_host, orig_port))
        if not self.direct_allowed:
            return False
        return ForwardApplication() if self.application else True

    def unix_connection_requested(self, dest_path):
        self.unix_requests.append(dest_path)
        if not self.direct_allowed:
            return False
        return ForwardApplication() if self.application else True

    def server_requested(self, listen_host, listen_port):
        self.listen_requests.append((listen_host, listen_port))
        return self.listen_allowed

    def unix_server_requested(self, listen_path):
        self.unix_listen_requests.append(listen_path)
        return self.listen_allowed


@asynccontextmanager
async def forwarding_connection(*, authorization=None, client_keys=()):
    policy = ForwardPolicy(authenticated=authorization is not None)
    host, _ = certificate_identity()
    async with velnora.listen(
            '127.0.0.1', 0, config=None, server_host_keys=[host],
            server_factory=lambda: policy, authorized_client_keys=authorization,
            encoding=None) as listener:
        async with access_connect(listener.get_port(), client_keys=list(client_keys)) as conn:
            yield conn, policy


async def forwarding_payload(reader, writer, *, greeting=b'destination-ready\x00',
                             payload=b'\x00forwarded\xff\r\nbytes'):
    assert await bounded(reader.readexactly(len(greeting))) == greeting
    writer.write(payload)
    await bounded(writer.drain())
    assert await bounded(reader.readexactly(len(payload))) == payload


async def forwarding_half_close(reader, writer):
    writer.write_eof()
    await bounded(writer.drain())
    assert await bounded(reader.read()) == b'after-half-close'


async def rejected_socket(reader, writer):
    """A rejected forwarded socket closes or resets, never supplies payload."""
    try:
        assert await bounded(reader.read(1)) == b''
    except ConnectionResetError:
        pass
    finally:
        writer.close()
        try:
            await bounded(writer.wait_closed())
        except ConnectionResetError:
            pass
