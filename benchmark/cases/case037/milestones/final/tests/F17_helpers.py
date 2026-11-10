# feature: F17
"""Application packet endpoints on real SSH connections, without devices."""
import asyncio
from contextlib import asynccontextmanager

import velnora

from _helpers import bounded
from F02_helpers import certificate_identity
from F07_helpers import access_connect
from F08_helpers import ChannelPeer


class PacketEndpoint(velnora.SSHTunTapSession):
    def __init__(self):
        self.packets = asyncio.Queue()
        self.started = asyncio.Event()
        self.closed = asyncio.Event()

    def connection_made(self, channel):
        self.channel = channel

    def session_started(self):
        self.started.set()

    def data_received(self, data, datatype):
        self.packets.put_nowait(data)

    def connection_lost(self, exc):
        self.closed.set()


class PacketPolicy(ChannelPeer):
    def __init__(self, ready):
        super().__init__(ready)
        self.requests = asyncio.Queue()
        self.allowed = True

    def packet_requested(self, kind, unit):
        application = PacketEndpoint() if self.allowed else None
        self.requests.put_nowait((kind, unit, application))
        return application if self.allowed else False

    def tun_requested(self, unit):
        return self.packet_requested('tun', unit)

    def tap_requested(self, unit):
        return self.packet_requested('tap', unit)


@asynccontextmanager
async def packet_connection():
    ready = asyncio.Queue()
    policy = PacketPolicy(ready)
    host, _ = certificate_identity()
    async with velnora.listen(
            '127.0.0.1', 0, config=None, server_host_keys=[host],
            server_factory=lambda: policy, encoding=None) as listener:
        async with access_connect(listener.get_port()) as connection:
            yield connection, policy, ready


async def packet_transfer(sender, receiver, packets):
    """Write a burst, then observe each application-level packet separately."""
    for packet in packets:
        sender.write(packet)
    received = [await bounded(receiver.packets.get()) for _ in packets]
    assert received == packets
    assert receiver.packets.empty()


def packet_material():
    """Opaque input packets; no product encoder or decoder supplies an oracle."""
    ipv4 = bytes.fromhex(
        '4500001b0007000040fd8da8c0000201c6336402666972737400ff')
    ipv4_long = bytes.fromhex('450000540007000040fd8d6fc0000201c6336402') + bytes(range(64))
    source = bytes.fromhex('20010db8000000000000000000000001')
    target = bytes.fromhex('20010db8000000000000000000000002')
    ipv6 = bytes.fromhex('600000000008fd40') + source + target + b'v6\x00\xffdata'
    ipv6_long = (bytes.fromhex('600000000100fd40') + target + source + bytes(range(256)))
    ethernet4 = bytes.fromhex('0200000000020200000000010800') + ipv4 + bytes(19)
    ethernet6 = bytes.fromhex('02000000000102000000000286dd') + ipv6_long
    return [ipv4, ipv6, ipv4_long, ipv6_long], [ethernet4, ethernet6]
