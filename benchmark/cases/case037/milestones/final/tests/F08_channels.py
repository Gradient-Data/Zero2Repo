# feature: F08
"""Acceptance checks for multiplexed channel data and public streams."""
import asyncio
import re

import velnora
import pytest

from _helpers import bounded, consume, run_async, tcp_server, wait_until
from F08_helpers import (InputCollector, application_stream, channel_connection,
                         delivery_fence)


def test_multiplexed_channel_lifetimes():
    async def scenario():
        async with channel_connection() as (conn, ready):
            first = await application_stream(conn, ready, 'echo', encoding=None)
            second = await application_stream(conn, ready, 'echo', encoding=None)
            a, ar, _, app_a = first
            b, br, _, app_b = second
            a.write(b'first\x00channel')
            b.write(b'second\xffchannel')
            assert await bounded(br.readexactly(14)) == b'second\xffchannel'
            assert await bounded(ar.readexactly(13)) == b'first\x00channel'
            a.write_eof()
            assert await bounded(ar.read()) == b''
            app_a.channel.close()
            await bounded(a.wait_closed())
            with pytest.raises(velnora.ChannelOpenError):
                await bounded(conn.open_session('reject'))
            b.write(b'still alive')
            assert await bounded(br.readexactly(11)) == b'still alive'
            b.write_eof()
            assert await bounded(br.read()) == b''
            app_b.channel.close()
            await bounded(b.wait_closed())
        return 'test_multiplexed_channel_lifetimes'
    assert run_async(scenario()) == 'test_multiplexed_channel_lifetimes'


def test_binary_text_encodings_and_errors():
    async def scenario():
        async with channel_connection() as (conn, ready):
            fw, fr, _, _ = await application_stream(conn, ready, 'echo', encoding=None)
            writer, reader, _, app = await application_stream(conn, ready)
            # A second-channel round trip ensures the first fragment has crossed
            # the transport before the remaining bytes are sent.
            app.channel.write(b'A\xe2')
            await delivery_fence(fw, fr)
            app.channel.write(b'\x82')
            await delivery_fence(fw, fr)
            app.channel.write(b'\xacZ')
            assert await bounded(reader.readexactly(3)) == 'A€Z'
            writer.write('雪é')
            await bounded(writer.drain())
            expected = '雪é'.encode('utf-8')
            await wait_until(lambda: len(app.received) == len(expected))
            assert bytes(app.received) == expected
            latin, lr, _, la = await application_stream(conn, ready, encoding='latin-1')
            la.channel.write(b'\xe9\xa3')
            assert await bounded(lr.readexactly(2)) == 'é£'
            latin.write('ñø')
            await bounded(latin.drain())
            await wait_until(lambda: len(la.received) == 2)
            assert bytes(la.received) == b'\xf1\xf8'
            raw, rr, _, ra = await application_stream(conn, ready, encoding=None)
            payload = bytes(range(256))
            ra.channel.write(payload)
            assert await bounded(rr.readexactly(len(payload))) == payload
            raw.write(payload)
            await bounded(raw.drain())
            await wait_until(lambda: len(ra.received) == len(payload))
            assert bytes(ra.received) == payload
            for policy in ('replace', 'ignore'):
                _, r, _, peer = await application_stream(conn, ready, errors=policy)
                peer.channel.write(b'a\xffb')
                peer.channel.write_eof()
                converted = await bounded(r.read())
                if policy == 'replace':
                    assert converted.startswith('a') and converted.endswith('b')
                    assert len(converted) > 2
                else:
                    assert converted == 'ab'

            async def endpoint(r, w):
                w.write(b'\x00\xffnetwork')
                await w.drain()
                w.close()
                await w.wait_closed()
            async with tcp_server(endpoint, host='127.0.0.1') as server:
                r, w = await bounded(conn.open_connection(
                    '127.0.0.1', server.sockets[0].getsockname()[1]))
                assert await bounded(r.read()) == b'\x00\xffnetwork'
                w.close()
                await bounded(w.wait_closed())
        # Strict conversion is a protocol failure and may close the transport.
        async with channel_connection() as (conn, ready):
            _, r, _, peer = await application_stream(conn, ready)
            peer.channel.write(b'\xff')
            with pytest.raises(velnora.ProtocolError):
                await bounded(r.read())
        return 'test_binary_text_encodings_and_errors'
    assert run_async(scenario()) == 'test_binary_text_encodings_and_errors'


def test_reader_boundaries_and_remainders():
    async def scenario():
        async with channel_connection() as (conn, ready):
            fw, fr, _, _ = await application_stream(conn, ready, 'echo', encoding=None)
            _, r, _, peer = await application_stream(conn, ready)
            peer.channel.write(b'available')
            await delivery_fence(fw, fr)
            available = ''
            while len(available) < len('available'):
                part = await bounded(r.read(100))
                assert part
                available += part
            assert available == 'available'
            peer.channel.write(b'line\nXYZbefore::after+next-END!tail')
            peer.channel.write_eof()
            assert await bounded(r.readline()) == 'line\n'
            assert await bounded(r.readexactly(3)) == 'XYZ'
            assert await bounded(r.readuntil('::')) == 'before::'
            # The earliest match wins even when it is not the first-listed choice.
            assert await bounded(r.readuntil(('-END!', '+'))) == 'after+'
            assert await bounded(r.readuntil(('-END!', '+'))) == 'next-END!'
            assert await bounded(r.read()) == 'tail'
            # A fixed delimiter whose bytes arrive in separate deliveries.
            _, split_reader, _, split_peer = await application_stream(conn, ready)
            split_peer.channel.write(b'abc:')
            await delivery_fence(fw, fr)
            pending = asyncio.create_task(split_reader.readuntil('::'))
            await delivery_fence(fw, fr)
            assert not pending.done()
            split_peer.channel.write(b':rest')
            await delivery_fence(fw, fr)
            assert await bounded(pending) == 'abc::'
            split_peer.channel.write_eof()
            assert await bounded(split_reader.read()) == 'rest'
            _, regex_reader, _, regex_peer = await application_stream(conn, ready)
            regex_peer.channel.write(b'prefix<1')
            await delivery_fence(fw, fr)
            regex_peer.channel.write(b'2>middle<34>rest')
            regex_peer.channel.write_eof()
            pattern = re.compile(r'<[0-9]{2}>')
            assert await bounded(regex_reader.readuntil(pattern, 4)) == 'prefix<12>'
            assert await bounded(regex_reader.readuntil(pattern, 4)) == 'middle<34>'
            assert await bounded(regex_reader.read()) == 'rest'
            _, iterator, _, ip = await application_stream(conn, ready)
            ip.channel.write(b'one\ntwo\nlast')
            ip.channel.write_eof()
            assert await consume(iterator) == ['one\n', 'two\n', 'last']
        return 'test_reader_boundaries_and_remainders'
    assert run_async(scenario()) == 'test_reader_boundaries_and_remainders'


def test_incomplete_reads_and_final_lines():
    async def scenario():
        async with channel_connection() as (conn, ready):
            for method, argument in [('readexactly', 8), ('readuntil', '::')]:
                _, reader, _, peer = await application_stream(conn, ready)
                peer.channel.write(b'short')
                peer.channel.write_eof()
                with pytest.raises(asyncio.IncompleteReadError) as failure:
                    await bounded(getattr(reader, method)(argument))
                assert failure.value.partial == 'short'
                assert await bounded(reader.read()) == ''
            _, reader, _, peer = await application_stream(conn, ready)
            for separator in ('', ()):
                with pytest.raises(ValueError):
                    await bounded(reader.readuntil(separator))
            peer.channel.write(b'complete\nfinal')
            peer.channel.write_eof()
            assert await bounded(reader.readline()) == 'complete\n'
            assert await bounded(reader.readline()) == 'final'
            assert await bounded(reader.readline()) == ''
            assert await bounded(reader.read()) == ''
        return 'test_incomplete_reads_and_final_lines'
    assert run_async(scenario()) == 'test_incomplete_reads_and_final_lines'


def test_pause_flow_control_and_half_close():
    async def scenario():
        async with channel_connection() as (conn, ready):
            fw, fr, _, _ = await application_stream(conn, ready, 'echo', encoding=None)
            collector = InputCollector()
            channel, _ = await bounded(conn.create_session(
                lambda: collector, 'hold', encoding=None))
            peer = await bounded(ready.get())
            peer.channel.write(b'baseline')
            await wait_until(lambda: len(b''.join(collector.pieces)) >= len(b'baseline'))
            assert b''.join(collector.pieces) == b'baseline'
            channel.pause_reading()
            peer.channel.write(b'paused-one')
            peer.channel.write(b'paused-two')
            await delivery_fence(fw, fr)
            assert b''.join(collector.pieces) == b'baseline'
            channel.resume_reading()
            await wait_until(lambda: len(b''.join(collector.pieces)) == 28)
            assert b''.join(collector.pieces) == b'baselinepaused-onepaused-two'

            writer, reader, _, blocked_peer = await application_stream(
                conn, ready, 'half', encoding=None)
            blocked_peer.channel.pause_reading()
            # Drain may complete once output is accepted for onward delivery.
            # Eventual delivery and half-close remain observable independently.
            payload = bytes(range(256)) * 4096
            writer.write(payload)
            draining = asyncio.create_task(writer.drain())
            await delivery_fence(fw, fr)
            blocked_peer.channel.resume_reading()
            await bounded(draining)
            await wait_until(lambda: len(blocked_peer.received) == len(payload))
            assert bytes(blocked_peer.received) == payload
            assert writer.can_write_eof()
            writer.write_eof()
            assert await bounded(reader.read()) == b'after-input-eof'

            writer, _, _, closed_peer = await application_stream(conn, ready, encoding=None)
            closed_peer.channel.pause_reading()
            writer.write(payload)
            draining = asyncio.create_task(writer.drain())
            await delivery_fence(fw, fr)
            pending = not draining.done()
            closed_peer.channel.close()
            if pending:
                with pytest.raises((ConnectionError, velnora.ConnectionLost)):
                    await bounded(draining)
            else:
                await draining
        return 'test_pause_flow_control_and_half_close'
    assert run_async(scenario(), timeout=30) == 'test_pause_flow_control_and_half_close'
