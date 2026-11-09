# feature: F13
"""Independent SOCKS wire client and real, observable destination peers."""
import asyncio
import socket
import struct
from contextlib import asynccontextmanager

from _helpers import bounded, managed_resource
from F12_helpers import SocketDestination


@asynccontextmanager
async def socks_destination(host, greeting):
    connections = []

    class ObservedDestination(SocketDestination):
        def connection_made(self, transport):
            connections.append(transport.get_extra_info('peername'))
            super().connection_made(transport)

    loop = asyncio.get_running_loop()
    async with managed_resource(
            lambda: loop.create_server(lambda: ObservedDestination(greeting), host, 0),
            close=lambda server: server.close(),
            wait_closed=lambda server: server.wait_closed()) as server:
        yield server.sockets[0].getsockname()[1], connections


def socks_request(version, host, port):
    port_bytes = struct.pack('!H', port)
    if version == 4:
        return b'\x04\x01' + port_bytes + socket.inet_pton(socket.AF_INET, host) + b'client\0'
    if version == '4a':
        return b'\x04\x01' + port_bytes + b'\0\0\0\x01client\0' + host.encode('ascii') + b'\0'
    if ':' in host:
        address = b'\x04' + socket.inet_pton(socket.AF_INET6, host)
    elif host == 'localhost':
        encoded = host.encode('ascii')
        address = b'\x03' + bytes([len(encoded)]) + encoded
    else:
        address = b'\x01' + socket.inet_pton(socket.AF_INET, host)
    return b'\x05\x01\0' + address + port_bytes


async def socks_negotiate(reader, writer):
    # No-auth is deliberately not the first offered method.
    writer.write(b'\x05\x02\x02\x00')
    await bounded(writer.drain())
    assert await bounded(reader.readexactly(2)) == b'\x05\x00'


async def socks_reply(reader, version):
    """Parse protocol framing without pinning the selected bind address."""
    if version != 5:
        response = await bounded(reader.readexactly(8))
        assert response[0] == 0
        return response[1] == 90
    header = await bounded(reader.readexactly(4))
    assert header[0] == 5 and header[2] == 0
    if header[3] == 1:
        length = 4
    elif header[3] == 4:
        length = 16
    else:
        assert header[3] == 3
        length = (await bounded(reader.readexactly(1)))[0]
    await bounded(reader.readexactly(length + 2))
    return header[1] == 0


async def socks_connect(reader, writer, version, host, port):
    if version == 5:
        await socks_negotiate(reader, writer)
    writer.write(socks_request(version, host, port))
    await bounded(writer.drain())
    assert await socks_reply(reader, version)


async def socks_no_data(reader):
    """Observe data, EOF, reset, or silence; only data violates this promise.

    Silence is not treated as an EOF or as a successful probe of any state.
    The finite observation window is paired with destination-side state checks.
    """
    try:
        data = await asyncio.wait_for(reader.read(1), 0.5)
    except (asyncio.TimeoutError, ConnectionResetError):
        return
    assert data == b'', 'Rejected request supplied forwarded data'


@asynccontextmanager
async def socks_client(port):
    reader, writer = await bounded(asyncio.open_connection('127.0.0.1', port))
    try:
        yield reader, writer
    finally:
        writer.close()
        try:
            await bounded(writer.wait_closed())
        except ConnectionResetError:
            pass


async def socks_discard_rejection(reader):
    """Do not constrain invalid-request reply bytes; bound the entire drain."""
    async def drain():
        while await reader.read(4096):
            pass
    try:
        await bounded(drain(), timeout=0.5)
    except (asyncio.TimeoutError, ConnectionResetError):
        pass


async def socks_failed_destination(reader, version):
    """A valid request may be refused, closed, or acknowledged before failing."""
    try:
        await bounded(socks_reply(reader, version), timeout=0.5)
    except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionResetError):
        return
    await socks_no_data(reader)
