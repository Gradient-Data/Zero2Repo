# feature: F13
"""Acceptance checks through the public dynamic listener and SOCKS wire."""
import socket

from _helpers import bounded, run_async
from F12_helpers import forwarding_connection, forwarding_payload
from F13_helpers import (socks_destination, socks_client, socks_connect,
                         socks_negotiate, socks_request, socks_discard_rejection,
                         socks_failed_destination)


def test_versions_and_destination_forms():
    """F13.T01: each supported wire address reaches the selected real peer."""
    async def exercise():
        async with (socks_destination('127.0.0.1', b'first-peer\0') as first,
                    socks_destination('127.0.0.1', b'second-peer\0') as second,
                    socks_destination('::1', b'ipv6-peer\0') as ipv6,
                    forwarding_connection() as (conn, policy)):
            async with conn.forward_socks('127.0.0.1', 0) as listener:
                routes = [(4, '127.0.0.1', first, b'first-peer\0'),
                          ('4a', 'localhost', second, b'second-peer\0'),
                          (5, '127.0.0.1', second, b'second-peer\0'),
                          (5, '::1', ipv6, b'ipv6-peer\0'),
                          (5, 'localhost', first, b'first-peer\0')]
                for index, (version, host, destination, greeting) in enumerate(routes):
                    async with socks_client(listener.get_port()) as (reader, writer):
                        await socks_connect(reader, writer, version, host, destination[0])
                        await forwarding_payload(reader, writer, greeting=greeting,
                                                 payload=bytes(range(256)) * (index + 1))
                        # These are application-visible SSH server callbacks, not internals.
                        assert policy.tcp_requests[-1][:2] == (host, destination[0])
                assert len(first[1]) == 2
                assert len(second[1]) == 2
                assert len(ipv6[1]) == 1
        return 'test_versions_and_destination_forms'
    assert run_async(exercise(), timeout=30) == 'test_versions_and_destination_forms'


def test_invalid_requests_and_unusable_destinations():
    """F13.T02: invalid requests never reach a destination; denials carry no data."""
    async def exercise():
        async with (socks_destination('127.0.0.1', b'live-target\0') as target,
                    forwarding_connection() as (conn, policy)):
            port, visits = target
            async with conn.forward_socks('127.0.0.1', 0) as listener:
                # Establish a working destination on the same listener before refusals.
                async with socks_client(listener.get_port()) as (reader, writer):
                    await socks_connect(reader, writer, 5, '127.0.0.1', port)
                    await forwarding_payload(reader, writer, greeting=b'live-target\0')
                expected_requests = list(policy.tcp_requests)
                request4 = socks_request(4, '127.0.0.1', port)
                request5 = socks_request(5, '127.0.0.1', port)
                invalid = [
                    (False, b'\x06' + request4[1:]),
                    (False, request4[:1] + b'\x02' + request4[2:]),
                    (False, b'\x05\x02\x01\x02' + request5),
                    (True, request5[:1] + b'\x02' + request5[2:]),
                    (True, request5[:1] + b'\x03' + request5[2:]),
                    (True, request5[:3] + b'\x02' + request5[4:]),
                    (True, request5[:2] + b'\x01' + request5[3:]),
                    (True, b'\x05\x01\0\x03\x01\xff' + request5[-2:]),
                    (False, b'\x04\x01' + request4[2:4] + b'\0\0\0\x01client\0\xff\0')]
                for negotiate, request in invalid:
                    async with socks_client(listener.get_port()) as (reader, writer):
                        if negotiate:
                            await socks_negotiate(reader, writer)
                        writer.write(request)
                        await bounded(writer.drain())
                        # Invalid negotiation has no specified reply/closure form.
                        # Drain to terminal closure on the baseline, but accept silence.
                        await socks_discard_rejection(reader)
                        assert policy.tcp_requests == expected_requests
                        assert len(visits) == 1
                # Reserve rather than guess an unavailable destination port.
                with socket.socket() as unavailable:
                    unavailable.bind(('127.0.0.1', 0))
                    closed_port = unavailable.getsockname()[1]
                    for version in (4, '4a', 5):
                        for prohibited in (False, True):
                            policy.direct_allowed = not prohibited
                            destination = port if prohibited else closed_port
                            host = 'localhost' if version == '4a' else '127.0.0.1'
                            async with socks_client(listener.get_port()) as (reader, writer):
                                if version == 5:
                                    await socks_negotiate(reader, writer)
                                writer.write(socks_request(version, host, destination))
                                await bounded(writer.drain())
                                # The reference sends success before the SSH open completes.
                                await socks_failed_destination(reader, version)
                            assert policy.tcp_requests[-1][:2] == (host, destination)
                            assert len(visits) == 1
                # Refusals must not have disabled the listener or its SSH transport.
                policy.direct_allowed = True
                async with socks_client(listener.get_port()) as (reader, writer):
                    await socks_connect(reader, writer, 5, '127.0.0.1', port)
                    await forwarding_payload(reader, writer, greeting=b'live-target\0',
                                             payload=b'working-after-refusals\xff')
                assert len(visits) == 2
        return 'test_invalid_requests_and_unusable_destinations'
    assert run_async(exercise(), timeout=30) == 'test_invalid_requests_and_unusable_destinations'
