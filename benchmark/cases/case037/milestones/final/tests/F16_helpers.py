# feature: F16
"""Independent Xauthority records and real, byte-observing X11 wire peers."""
import asyncio
import os
import struct
import socket
from contextlib import asynccontextmanager

from _helpers import bounded, close_stream
from F09_helpers import session_connection

X11_COOKIE_PROTOCOL = b'MIT-MAGIC-COOKIE-1'


def xauthority_record(display_number, cookie):
    fields = (b'', str(display_number).encode('ascii'), X11_COOKIE_PROTOCOL, cookie)
    return b'\xff\xff' + b''.join(struct.pack('>H', len(value)) + value
                                    for value in fields)


class ForwardedAuthorization(tuple):
    """Authorization paired with the real address its record selects."""
    def __new__(cls, protocol, cookie, address):
        result = super().__new__(cls, (protocol, cookie))
        result.address = address
        return result


def forwarded_authorization(path, display):
    """Select a usable address-specific record, independent of record count."""
    host, suffix = display.rsplit(':', 1)
    number = suffix.split('.')[0].encode('ascii')
    addresses = [(0 if family == socket.AF_INET else 6,
                  socket.inet_pton(family, address[0]), address[0])
                 for family, _, _, _, address in socket.getaddrinfo(
                     host.strip('[]'), None, type=socket.SOCK_STREAM)]
    data = memoryview(path.read_bytes())
    offset, records = 0, []
    while offset < len(data):
        family, = struct.unpack_from('>H', data, offset)
        offset += 2
        fields = []
        for _ in range(4):
            size, = struct.unpack_from('>H', data, offset)
            offset += 2
            assert offset + size <= len(data), 'Truncated Xauthority field'
            fields.append(bytes(data[offset:offset + size]))
            offset += size
        if fields[1] == number and fields[2] == X11_COOKIE_PROTOCOL:
            records.append((family, fields[0], fields[2], fields[3]))
    for family, packed, address in addresses:
        for record_family, record_address, protocol, cookie in records:
            if (record_family == 65535 or (record_family, record_address) == (family, packed) or
                    record_family == 256 and record_address in (b'', socket.gethostname().encode())):
                return ForwardedAuthorization(protocol, cookie, address)
    raise AssertionError('Forwarded display must have usable authorization')


def x11_setup(protocol, cookie, order=b'l'):
    endian = '<' if order == b'l' else '>'
    def padded(value):
        return value + b'\0' * (-len(value) % 4)
    return (order + b'\0' + struct.pack(endian + '5H', 11, 0,
                                       len(protocol), len(cookie), 0)
            + padded(protocol) + padded(cookie))


def read_x11_setup(data):
    """Read setup fields and following traffic without grading padding bytes."""
    assert data[:1] in (b'l', b'B')
    endian = '<' if data[:1] == b'l' else '>'
    major, minor, protocol_size, cookie_size, _ = struct.unpack(endian + '5H', data[2:12])
    protocol_end = 12 + protocol_size
    cookie_start = 12 + (protocol_size + 3) // 4 * 4
    cookie_end = cookie_start + cookie_size
    end = cookie_start + (cookie_size + 3) // 4 * 4
    assert len(data) >= end, 'Truncated X11 setup'
    return major, minor, data[12:protocol_end], data[cookie_start:cookie_end], data[end:]


class DisplayWirePeer(asyncio.Protocol):
    """A minimal display transport peer; all received bytes remain observable."""
    def __init__(self, display):
        self.display = display
        self.received = bytearray()
        self.forwarded = 0

    def connection_made(self, transport):
        self.transport = transport
        self.display.connections.append(self)

    def data_received(self, data):
        self.received.extend(data)
        size = len(x11_setup(X11_COOKIE_PROTOCOL, self.display.cookie))
        if len(self.received) >= size:
            if not self.forwarded:
                self.transport.write(self.display.greeting)
                self.forwarded = size
            self.transport.write(self.received[self.forwarded:])
            self.forwarded = len(self.received)

    def eof_received(self):
        self.transport.close()


class LocalDisplay:
    def __init__(self, greeting):
        self.cookie = os.urandom(16)
        self.greeting = greeting
        self.connections = []

    @property
    def delivered(self):
        return [bytes(peer.received) for peer in self.connections if peer.received]


@asynccontextmanager
async def local_display(path, greeting):
    display = LocalDisplay(greeting)
    loop = asyncio.get_running_loop()
    server = await loop.create_server(lambda: DisplayWirePeer(display), '127.0.0.1', 0)
    port = server.sockets[0].getsockname()[1]
    display.address = f'127.0.0.1:{port - 6000}.0'
    display.auth_path = path
    path.write_bytes(xauthority_record(port - 6000, display.cookie))
    try:
        yield display
    finally:
        for peer in display.connections:
            peer.transport.close()
        server.close()
        await bounded(server.wait_closed())


@asynccontextmanager
async def x11_connection(server_auth, *, enabled=True):
    # enabled=None leaves the server's X11 forwarding setting at its default.
    options = {} if enabled is None else {'x11_forwarding': enabled}
    async with session_connection(x11_auth_path=str(server_auth),
                                  **options) as connection:
        yield connection


def display_options(display, **overrides):
    options = dict(x11_forwarding=True, x11_display=display.address,
                   x11_auth_path=str(display.auth_path))
    options.update(overrides)
    return options


@asynccontextmanager
async def remote_display(display, address):
    host, suffix = display.rsplit(':', 1)
    number = int(suffix.split('.')[0])
    reader, writer = await bounded(asyncio.open_connection(address, 6000 + number))
    try:
        yield reader, writer
    finally:
        await close_stream(writer)


async def display_exchange(display, remote, authorization, payload, *, order=b'l'):
    async with remote_display(remote, authorization.address) as (reader, writer):
        writer.write(x11_setup(*authorization, order=order))
        await bounded(writer.drain())
        assert await bounded(reader.readexactly(len(display.greeting))) == display.greeting
        writer.write(payload)
        await bounded(writer.drain())
        assert await bounded(reader.readexactly(len(payload))) == payload
    expected = (11, 0, X11_COOKIE_PROTOCOL, display.cookie, payload)
    assert any(read_x11_setup(data) == expected for data in display.delivered)


async def rejected_x11(remote, authorization, payload):
    """Observe setup failure or clean EOF; never accept data or a timeout."""
    async with remote_display(remote, authorization.address) as (reader, writer):
        writer.write(x11_setup(*authorization) + payload)
        await bounded(writer.drain())
        first = await bounded(reader.read(1))
        if first == b'':
            return
        prefix = first + await bounded(reader.readexactly(7))
        status, reason_length, major, minor, extra = struct.unpack('<BBHHH', prefix)
        assert status == 0
        body = await bounded(reader.readexactly(extra * 4))
        assert reason_length <= len(body)
