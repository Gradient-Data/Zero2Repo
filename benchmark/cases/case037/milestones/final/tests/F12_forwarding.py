# feature: F12
"""Acceptance tests for direct and listener-based TCP/UNIX forwarding."""
import asyncio
import socket
from contextlib import AsyncExitStack

import velnora
import pytest

from _helpers import bounded, open_stream, run_async
from F02_helpers import certificate_identity
from F03_helpers import authorized_line
from F12_helpers import (forwarding_connection, forwarding_destination,
                         forwarding_payload, forwarding_half_close, rejected_socket)


def test_direct_destinations_and_application(tmp_path):
    """F12.T01: direct requests reach real sockets or application handlers."""
    async def exercise():
        path = tmp_path / 'destination'
        async with forwarding_destination() as port, forwarding_destination(path=path):
            async with forwarding_connection() as (conn, policy):
                for opener, args in [
                        (conn.open_connection, ('127.0.0.1', port, 'origin.example', 3917)),
                        (conn.open_unix_connection, (str(path),))]:
                    async with open_stream(opener, *args) as (reader, writer):
                        await forwarding_payload(reader, writer)
                        await forwarding_half_close(reader, writer)
                assert policy.tcp_requests == [('127.0.0.1', port, 'origin.example', 3917)]
                assert policy.unix_requests == [str(path)]
                policy.application = True
                for opener, args in [(conn.open_connection, ('application.example', 1234)),
                                     (conn.open_unix_connection, ('application-socket',))]:
                    async with open_stream(opener, *args) as (reader, writer):
                        await forwarding_payload(reader, writer, greeting=b'application-ready\x00')
                policy.direct_allowed = False
                for opener, args in [(conn.open_connection, ('127.0.0.1', port)),
                                     (conn.open_unix_connection, (str(path),))]:
                    with pytest.raises(velnora.ChannelOpenError):
                        async with open_stream(opener, *args):
                            pass
        # Reserve an unlistened port so another listener cannot acquire it.
        with socket.socket() as unavailable:
            unavailable.bind(('127.0.0.1', 0))
            closed_port = unavailable.getsockname()[1]
            async with forwarding_connection() as (conn, _):
                for opener, args in [(conn.open_connection, ('127.0.0.1', closed_port)),
                                     (conn.open_unix_connection, (str(tmp_path / 'missing'),))]:
                    with pytest.raises(velnora.ChannelOpenError):
                        async with open_stream(opener, *args):
                            pass
        return 'test_direct_destinations_and_application'
    assert run_async(exercise(), timeout=30) == 'test_direct_destinations_and_application'


def test_local_remote_and_mixed_listeners(tmp_path):
    """F12.T02: each endpoint direction transports destination bytes."""
    async def exercise():
        target = tmp_path / 'target'
        async with forwarding_destination() as port, forwarding_destination(path=target):
            async with forwarding_connection() as (conn, policy):
                # All eight public direction/type combinations are distinct capabilities.
                for remote in (False, True):
                    side = 'remote' if remote else 'local'
                    for source_unix, dest_unix in ((False, False), (False, True),
                                                  (True, False), (True, True)):
                        source = str(tmp_path / (side + str(source_unix) + str(dest_unix)))
                        if source_unix:
                            entry = getattr(conn, 'forward_' + side +
                                            ('_path' if dest_unix else '_path_to_port'))
                            args = (source, str(target)) if dest_unix else (source, '127.0.0.1', port)
                        else:
                            entry = getattr(conn, 'forward_' + side +
                                            ('_port_to_path' if dest_unix else '_port'))
                            args = ('127.0.0.1', 0, str(target)) if dest_unix else ('127.0.0.1', 0, '127.0.0.1', port)
                        async with entry(*args) as listener:
                            if source_unix:
                                opener, address = asyncio.open_unix_connection, (source,)
                            else:
                                allocated = listener.get_port()
                                assert 0 < allocated <= 65535
                                opener, address = asyncio.open_connection, ('127.0.0.1', allocated)
                            async with open_stream(opener, *address) as (reader, writer):
                                await forwarding_payload(reader, writer)
                assert policy.listen_requests == [('127.0.0.1', 0)] * 2
                assert len(policy.unix_listen_requests) == 2
        return 'test_local_remote_and_mixed_listeners'
    assert run_async(exercise(), timeout=30) == 'test_local_remote_and_mixed_listeners'


def test_listener_failures(tmp_path):
    """F12.T03: occupied binds and denied requests have listener failures."""
    async def exercise():
        async with forwarding_destination() as port:
            async with forwarding_connection() as (conn, policy):
                for entry in (conn.forward_local_port, conn.forward_remote_port):
                    async with entry('127.0.0.1', 0, '127.0.0.1', port) as listener:
                        async with open_stream(asyncio.open_connection, '127.0.0.1', listener.get_port()) as streams:
                            await forwarding_payload(*streams)
                    error = OSError if entry == conn.forward_local_port else velnora.ChannelListenError
                    with pytest.raises(error):
                        async with entry('127.0.0.1', port, '127.0.0.1', port):
                            pass
                blocked = tmp_path / 'occupied'
                blocked.write_bytes(b'not a socket')
                for entry, error in [(conn.forward_local_path, OSError),
                                     (conn.forward_remote_path, velnora.ChannelListenError)]:
                    with pytest.raises(error):
                        async with entry(str(blocked), str(tmp_path / 'destination')):
                            pass
                policy.listen_allowed = False
                for entry, args in [
                        (conn.forward_remote_port, ('127.0.0.1', 0, '127.0.0.1', port)),
                        (conn.forward_remote_path, (str(tmp_path / 'denied'), str(tmp_path / 'destination')))]:
                    with pytest.raises(velnora.ChannelListenError):
                        async with entry(*args):
                            pass
        return 'test_listener_failures'
    assert run_async(exercise(), timeout=30) == 'test_listener_failures'


def test_forwarding_policies_and_identity(tmp_path):
    """F12.T04: destination/origin policies and authenticated restrictions apply."""
    async def exercise():
        async with (forwarding_destination(greeting=b'first\x00') as first,
                    forwarding_destination(greeting=b'second\x00') as second,
                    forwarding_destination(path=tmp_path / 'identity-target')):
            async with forwarding_connection() as (conn, policy):
                observations = []
                destinations = iter((first, second, None))
                async def select_destination(host, port):
                    observations.append((host, port))
                    destination = next(destinations)
                    if destination is None:
                        raise velnora.ChannelOpenError(velnora.OPEN_ADMINISTRATIVELY_PROHIBITED, 'Rejected by application')
                    return await conn.forward_connection('127.0.0.1', destination)
                async with await conn.create_server(select_destination, '127.0.0.1', 0) as listener:
                    for greeting in (b'first\x00', b'second\x00'):
                        async with open_stream(asyncio.open_connection, '127.0.0.1', listener.get_port()) as (reader, writer):
                            origin = writer.get_extra_info('sockname')
                            await forwarding_payload(reader, writer, greeting=greeting)
                            assert observations[-1] == origin
                    reader, writer = await bounded(asyncio.open_connection('127.0.0.1', listener.get_port()))
                    origin = writer.get_extra_info('sockname')
                    await rejected_socket(reader, writer)
                    assert observations[-1] == origin
                    assert len(observations) == 3
                # Selective direct policy uses both destination and origin.
                original = policy.connection_requested
                def selective(dest_host, dest_port, orig_host, orig_port):
                    allowed = dest_port == first and orig_host == 'trusted.example'
                    policy.direct_allowed = allowed
                    return original(dest_host, dest_port, orig_host, orig_port)
                policy.connection_requested = selective
                for target, origin, allowed in [(first, 'trusted.example', True),
                                                (second, 'trusted.example', False),
                                                (first, 'other.example', False)]:
                    if allowed:
                        async with open_stream(conn.open_connection, '127.0.0.1', target, origin, 4132) as streams:
                            await forwarding_payload(*streams, greeting=b'first\x00')
                    else:
                        with pytest.raises(velnora.ChannelOpenError):
                            async with open_stream(conn.open_connection, '127.0.0.1', target, origin, 4132):
                                pass
                assert policy.tcp_requests == [('127.0.0.1', target, origin, 4132) for target, origin, _ in
                                               [(first, 'trusted.example', True), (second, 'trusted.example', False),
                                                (first, 'other.example', False)]]
            key, _ = certificate_identity()
            ca, _ = certificate_identity()
            identities = [
                ('', key, True, True),
                ('no-port-forwarding', key, False, False),
                ('permitopen="127.0.0.1:' + str(first) + '"', key, True, False),
                ('permitopen="127.0.0.1:*"', key, True, True),
                ('cert-authority', (key, ca.generate_user_certificate(
                    key, 'forwarding identity', principals=['member'],
                    permit_port_forwarding=False)), False, False)]
            for options, identity, allow_first, allow_second in identities:
                signer = ca if options == 'cert-authority' else key
                authorization = velnora.import_authorized_keys(authorized_line(signer, options))
                async with forwarding_connection(authorization=authorization, client_keys=[identity]) as (conn, _):
                    for target, greeting, allowed in [(first, b'first\x00', allow_first),
                                                      (second, b'second\x00', allow_second)]:
                        if allowed:
                            async with open_stream(conn.open_connection, '127.0.0.1', target) as streams:
                                await forwarding_payload(*streams, greeting=greeting)
                        else:
                            with pytest.raises(velnora.ChannelOpenError):
                                async with open_stream(conn.open_connection, '127.0.0.1', target):
                                    pass
                    if options in ('no-port-forwarding', 'cert-authority'):
                        with pytest.raises(velnora.ChannelOpenError):
                            async with open_stream(conn.open_unix_connection, str(tmp_path / 'identity-target')):
                                pass
                        with pytest.raises(velnora.ChannelListenError):
                            async with conn.forward_remote_path(str(tmp_path / 'restricted-listener'),
                                                                str(tmp_path / 'identity-target')):
                                pass
                    else:
                        async with open_stream(conn.open_unix_connection, str(tmp_path / 'identity-target')) as streams:
                            await forwarding_payload(*streams)
                    if not allow_first:
                        with pytest.raises(velnora.ChannelListenError):
                            async with conn.forward_remote_port('127.0.0.1', 0, '127.0.0.1', first):
                                pass
        return 'test_forwarding_policies_and_identity'
    assert run_async(exercise(), timeout=45) == 'test_forwarding_policies_and_identity'


def test_forwarded_half_close_and_lifetimes(tmp_path):
    """F12.T05: listener closure and owning transport closure differ."""
    async def exercise():
        target = tmp_path / 'lifetime-target'
        async with forwarding_destination() as port, forwarding_destination(path=target):
            for remote, unix in ((False, False), (True, False), (False, True), (True, True)):
                async with forwarding_connection() as (conn, _):
                    async with AsyncExitStack() as stack:
                        if unix:
                            entry = conn.forward_remote_path if remote else conn.forward_local_path
                            source = str(tmp_path / ('stopped-' + str(remote)))
                            other = str(tmp_path / ('live-' + str(remote)))
                            stopped = await stack.enter_async_context(entry(source, str(target)))
                            live = await stack.enter_async_context(entry(other, str(target)))
                            opener = asyncio.open_unix_connection
                            stopped_address, live_address = (source,), (other,)
                            refused = (FileNotFoundError, ConnectionRefusedError)
                        else:
                            entry = conn.forward_remote_port if remote else conn.forward_local_port
                            stopped = await stack.enter_async_context(entry('127.0.0.1', 0, '127.0.0.1', port))
                            live = await stack.enter_async_context(entry('127.0.0.1', 0, '127.0.0.1', port))
                            opener = asyncio.open_connection
                            stopped_address = ('127.0.0.1', stopped.get_port())
                            live_address = ('127.0.0.1', live.get_port())
                            refused = ConnectionRefusedError
                        reader, writer = await stack.enter_async_context(open_stream(opener, *stopped_address))
                        await forwarding_payload(reader, writer)
                        stopped.close()
                        # Local completion also waits for accepted sockets on Python 3.13.
                        if remote:
                            await bounded(stopped.wait_closed())
                        with pytest.raises(refused):
                            async with open_stream(opener, *stopped_address):
                                pass
                        payload = bytes(range(256)) * 1024
                        writer.write(payload)
                        await bounded(writer.drain())
                        assert await bounded(reader.readexactly(len(payload))) == payload
                        await forwarding_half_close(reader, writer)
                        writer.close()
                        await bounded(writer.wait_closed())
                        await bounded(stopped.wait_closed())
                        other_reader, other_writer = await stack.enter_async_context(open_stream(opener, *live_address))
                        await forwarding_payload(other_reader, other_writer)
                        conn.close()
                        await bounded(conn.wait_closed())
                        assert await bounded(other_reader.read()) == b''
                        await bounded(live.wait_closed())
                        with pytest.raises(refused):
                            async with open_stream(opener, *live_address):
                                pass
        return 'test_forwarded_half_close_and_lifetimes'
    assert run_async(exercise(), timeout=30) == 'test_forwarded_half_close_and_lifetimes'
