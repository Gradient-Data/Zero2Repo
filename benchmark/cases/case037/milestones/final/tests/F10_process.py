# feature: F10
"""Acceptance of completion, live interaction, and process I/O routing."""
import asyncio
import io
import os
import socket

import velnora
import pytest

from _helpers import bounded, run_async, wait_until, socket_pair, opened_connection
from F09_helpers import session_connection
from F10_helpers import process_connection, ProcessProtocol, server_exchange, asyncio_socket_stream


def test_run_completion_and_checked_failure(tmp_path):
    async def exercise():
        async with process_connection() as (conn, ready):
            for options in ({}, {'command': 'calculate'}, {'subsystem': 'worker'}):
                peer = asyncio.create_task(server_exchange(
                    ready, b'input\x00\xff', b'ordinary\x00', b'error\xff', 7))
                result = await bounded(conn.run(input=b'input\x00\xff',
                                               encoding=None, **options))
                await bounded(peer)
                assert (result.stdout, result.stderr, result.exit_status,
                        result.exit_signal, result.returncode) == (
                            b'ordinary\x00', b'error\xff', 7, None, 7)
            peer = asyncio.create_task(server_exchange(ready, b'', b'ok', b'', 0))
            result = await bounded(conn.run('success', stdin=velnora.DEVNULL, check=True,
                                           encoding=None))
            await bounded(peer)
            assert (result.stdout, result.stderr, result.exit_status) == (b'ok', b'', 0)
            for signal in (False, True):
                async def finish():
                    server = await bounded(ready.get())
                    assert await bounded(server.stdin.read()) == b'checked input'
                    server.stdout.write(b'kept output')
                    server.stderr.write(b'kept error')
                    if signal:
                        server.exit_with_signal('TERM')
                    else:
                        server.exit(9)
                peer = asyncio.create_task(finish())
                with pytest.raises(velnora.ProcessError) as caught:
                    await bounded(conn.run('checked', input=b'checked input',
                                           encoding=None, check=True))
                await bounded(peer)
                failure = caught.value
                assert failure.command == 'checked'
                assert (failure.stdout, failure.stderr) == (b'kept output', b'kept error')
                if signal:
                    assert failure.exit_signal[0] == 'TERM'
                    assert failure.exit_status == -1
                    assert failure.returncode == -15
                else:
                    assert failure.exit_status == 9
                    assert failure.exit_signal is None
                    assert failure.returncode == 9
            async def signal_exit():
                server = await bounded(ready.get())
                assert await bounded(server.stdin.read()) == b'signal input'
                server.stdout.write(b'signal output')
                server.stderr.write(b'signal error')
                server.exit_with_signal('TERM')
            peer = asyncio.create_task(signal_exit())
            result = await bounded(conn.run('signal', input=b'signal input', encoding=None))
            await bounded(peer)
            assert (result.stdout, result.stderr, result.exit_status, result.returncode) == (
                b'signal output', b'signal error', -1, -15)
            assert result.exit_signal[0] == 'TERM'
        # An independent OpenSSH server reports real process outcomes.
        from F06_helpers import openssh_daemon, daemon_connect
        async with openssh_daemon(tmp_path / 'daemon') as (port, user_key, _, _):
            async with opened_connection(daemon_connect(port, user_key)) as conn:
                result = await bounded(conn.run('printf out; printf err >&2; exit 7'))
                assert (result.stdout, result.stderr, result.exit_status,
                        result.exit_signal, result.returncode) == ('out', 'err', 7, None, 7)
                result = await bounded(conn.run('printf before; kill -TERM $$'))
                assert result.stdout == 'before'
                assert result.exit_signal is not None and result.exit_signal[0] == 'TERM'
                assert (result.exit_status, result.returncode) == (-1, -15)
        return 'test_run_completion_and_checked_failure'
    assert run_async(exercise(), timeout=30) == 'test_run_completion_and_checked_failure'


def test_live_interaction_controls_and_timeout():
    async def exercise():
        async with process_connection() as (conn, ready):
            async with conn.create_process('interactive', encoding=None) as client:
                server = await bounded(ready.get())
                for data in (b'first\n', b'second\x00\n'):
                    client.stdin.write(data)
                    assert await bounded(server.stdin.readexactly(len(data))) == data
                    server.stdout.write(data.upper())
                    server.stderr.write(b'notice:' + data)
                    assert await bounded(client.stdout.readexactly(len(data))) == data.upper()
                    assert await bounded(client.stderr.readexactly(7 + len(data))) == b'notice:' + data
                client.stdin.write_eof()
                assert await bounded(server.stdin.read()) == b''
                server.stdout.write(b'after eof')
                server.exit(0)
                result = await bounded(client.wait())
                assert (result.stdout, result.stderr, result.exit_status) == (b'after eof', b'', 0)
            async with conn.create_process('deadline', encoding=None) as client:
                server = await bounded(ready.get())
                server.stdout.write(b'partial output')
                server.stderr.write(b'partial error')
                await bounded(server.stdout.drain())
                with pytest.raises(velnora.TimeoutError) as caught:
                    await client.wait(timeout=0.05)
                assert caught.value.command == 'deadline'
                captured = caught.value.stdout, caught.value.stderr
                assert b'partial output'.startswith(captured[0])
                assert b'partial error'.startswith(captured[1])
                server.exit(0)
                result = await bounded(client.wait())
                assert captured[0] + result.stdout == b'partial output'
                assert captured[1] + result.stderr == b'partial error'
                assert result.exit_status == 0
        async with session_connection(encoding=None) as (conn, ready):
            for operation, expected in ((lambda p: p.send_signal('USR1'), 'USR1'),
                                        (lambda p: p.terminate(), 'TERM'),
                                        (lambda p: p.kill(), 'KILL')):
                async with conn.create_process('control', encoding=None) as client:
                    server = await bounded(ready.get())
                    operation(client)
                    assert await bounded(server.events.get()) == ('signal', expected)
                    server.channel.exit_with_signal(expected)
                    result = await bounded(client.wait())
                    assert result.exit_signal[0] == expected
                    assert result.exit_status == -1
        return 'test_live_interaction_controls_and_timeout'
    assert run_async(exercise()) == 'test_live_interaction_controls_and_timeout'


def test_redirection_carriers_and_special_destinations(tmp_path):
    async def exercise():
        payload = b'route\x00\xff\n' * 23
        async with process_connection() as (conn, ready):
            source = tmp_path / 'source'
            source.write_bytes(payload)
            # File names and file-like streams are distinct supported carriers.
            for kind in ('path', 'open', 'memory'):
                destination = tmp_path / ('destination-' + kind)
                with source.open('rb') as opened, destination.open('wb') as target:
                    src = source if kind == 'path' else opened if kind == 'open' else io.BytesIO(payload)
                    dst = destination if kind == 'path' else target if kind == 'open' else io.BytesIO()
                    peer = asyncio.create_task(server_exchange(ready, payload, payload[::-1], b'err'))
                    result = await bounded(conn.run('route', stdin=src, stdout=dst,
                                                   recv_eof=False, encoding=None))
                    await bounded(peer)
                    target.flush()
                    actual = dst.getvalue() if kind == 'memory' else destination.read_bytes()
                    assert actual == payload[::-1]
                    assert (result.stdout, result.stderr, result.exit_status) == (b'', b'err', 0)
            # Actual OS pipe descriptors and connected sockets carry data and EOF.
            for kind in ('pipe', 'socket'):
                if kind == 'pipe':
                    incoming, producer = os.pipe()
                    consumer, outgoing = os.pipe()
                    os.write(producer, payload)
                    os.close(producer)
                    peer = asyncio.create_task(server_exchange(ready, payload, payload[::-1], b'pipe error'))
                    result = await bounded(conn.run('pipe', stdin=incoming, stdout=outgoing, encoding=None))
                    await bounded(peer)
                    reader = asyncio.StreamReader()
                    pipe_transport, _ = await asyncio.get_running_loop().connect_read_pipe(
                        lambda: asyncio.StreamReaderProtocol(reader), os.fdopen(consumer, 'rb'))
                    try:
                        assert await bounded(reader.read()) == payload[::-1]
                    finally:
                        pipe_transport.close()
                else:
                    with socket_pair() as (incoming, producer), socket_pair() as (outgoing, consumer):
                        loop = asyncio.get_running_loop()
                        await loop.sock_sendall(producer, payload)
                        producer.shutdown(socket.SHUT_WR)
                        peer = asyncio.create_task(server_exchange(ready, payload, payload[::-1], b'pipe error'))
                        result = await bounded(conn.run('socket', stdin=incoming, stdout=outgoing, encoding=None))
                        await bounded(peer)
                        chunks = []
                        while True:
                            chunk = await bounded(loop.sock_recv(consumer, 4096))
                            if not chunk:
                                break
                            chunks.append(chunk)
                        assert b''.join(chunks) == payload[::-1]
                assert (result.stderr, result.exit_status) == (b'pipe error', 0)
            peer = asyncio.create_task(server_exchange(ready, b'', b'O' * 11, b'E' * 7))
            result = await bounded(conn.run('merge', stdin=velnora.DEVNULL,
                                           stderr=velnora.STDOUT, encoding=None))
            await bounded(peer)
            assert len(result.stdout) == 18
            assert result.stdout.count(b'O') == 11
            assert result.stdout.count(b'E') == 7
            assert (result.stderr, result.exit_status) == (b'', 0)
            peer = asyncio.create_task(server_exchange(ready, payload, b'discard', b'retained'))
            result = await bounded(conn.run('discard', input=payload, stdout=velnora.DEVNULL,
                                           encoding=None))
            await bounded(peer)
            assert (result.stdout, result.stderr, result.exit_status) == (b'', b'retained', 0)
            peer = asyncio.create_task(server_exchange(ready, payload, b'retained', b'discard'))
            result = await bounded(conn.run('discard-error', input=payload, stderr=velnora.DEVNULL,
                                           encoding=None))
            await bounded(peer)
            assert (result.stdout, result.stderr, result.exit_status) == (b'retained', b'', 0)
            # Server-side source and target directions are the reverse of the client.
            for kind in ('path', 'open', 'memory'):
                destination = tmp_path / ('server-' + kind)
                with source.open('rb') as opened, destination.open('wb', buffering=0) as target:
                    src = source if kind == 'path' else opened if kind == 'open' else io.BytesIO(payload)
                    dst = destination if kind == 'path' else target if kind == 'open' else io.BytesIO()
                    async with conn.create_process('server-route', encoding=None) as client:
                        server = await bounded(ready.get())
                        await server.redirect(stdin=dst, stdout=src, recv_eof=(kind == 'path'), send_eof=False)
                        await server.redirect_stderr(io.BytesIO(b'server redirected error'), send_eof=False)
                        client.stdin.write(payload[::-1])
                        client.stdin.write_eof()
                        assert await bounded(client.stdout.readexactly(len(payload))) == payload
                        if kind == 'memory':
                            await wait_until(lambda: dst.getvalue() == payload[::-1])
                        else:
                            await wait_until(lambda: destination.read_bytes() == payload[::-1])
                        server.exit(0)
                        result = await bounded(client.wait())
                        assert (result.stdout, result.stderr, result.exit_status) == (
                            b'', b'server redirected error', 0)
            # Pipe EOF is observed through a bounded asynchronous reader.
            incoming, producer_fd = os.pipe()
            consumer_fd, outgoing = os.pipe()
            os.write(producer_fd, payload)
            os.close(producer_fd)
            reader = asyncio.StreamReader()
            pipe_transport, _ = await asyncio.get_running_loop().connect_read_pipe(
                lambda: asyncio.StreamReaderProtocol(reader), os.fdopen(consumer_fd, 'rb'))
            try:
                async with conn.create_process('server-pipe', encoding=None) as client:
                    server = await bounded(ready.get())
                    await server.redirect(stdin=outgoing, stdout=incoming)
                    client.stdin.write(payload[::-1])
                    client.stdin.write_eof()
                    assert await bounded(client.stdout.read()) == payload
                    assert await bounded(reader.read()) == payload[::-1]
                    server.exit(0)
                    assert (await bounded(client.wait())).exit_status == 0
            finally:
                pipe_transport.close()
            with socket_pair() as (incoming, producer), socket_pair() as (outgoing, consumer):
                loop = asyncio.get_running_loop()
                await loop.sock_sendall(producer, payload)
                producer.shutdown(socket.SHUT_WR)
                async with conn.create_process('server-socket', encoding=None) as client:
                    server = await bounded(ready.get())
                    await server.redirect(stdin=outgoing, stdout=incoming)
                    client.stdin.write(payload[::-1])
                    client.stdin.write_eof()
                    assert await bounded(client.stdout.read()) == payload
                    chunks = []
                    while True:
                        chunk = await bounded(loop.sock_recv(consumer, 4096))
                        if not chunk:
                            break
                        chunks.append(chunk)
                    assert b''.join(chunks) == payload[::-1]
                    server.exit(0)
                    assert (await bounded(client.wait())).exit_status == 0
            for side in ('client', 'server'):
                with socket_pair() as (incoming, producer), socket_pair() as (outgoing, consumer):
                    loop = asyncio.get_running_loop()
                    await loop.sock_sendall(producer, payload)
                    producer.shutdown(socket.SHUT_WR)
                    async with asyncio_socket_stream(incoming) as (stream_reader, _), \
                            asyncio_socket_stream(outgoing) as (_, stream_writer):
                        src, dst = stream_reader, stream_writer
                        if side == 'client':
                            peer = asyncio.create_task(server_exchange(ready, payload, payload[::-1], b'stream err'))
                            result = await bounded(conn.run('stream-route', stdin=src, stdout=dst, encoding=None))
                            await bounded(peer)
                            assert (result.stderr, result.exit_status) == (b'stream err', 0)
                        else:
                            async with conn.create_process('server-stream', encoding=None) as client:
                                server = await bounded(ready.get())
                                await server.redirect(stdin=dst, stdout=src)
                                client.stdin.write(payload[::-1])
                                client.stdin.write_eof()
                                assert await bounded(client.stdout.read()) == payload
                                chunks = []
                                while True:
                                    chunk = await bounded(loop.sock_recv(consumer, 4096))
                                    if not chunk:
                                        break
                                    chunks.append(chunk)
                                assert b''.join(chunks) == payload[::-1]
                                server.exit(0)
                                assert (await bounded(client.wait())).exit_status == 0
                                continue
                        chunks = []
                        while True:
                            chunk = await bounded(loop.sock_recv(consumer, 4096))
                            if not chunk:
                                break
                            chunks.append(chunk)
                        assert b''.join(chunks) == payload[::-1]
        return 'test_redirection_carriers_and_special_destinations'
    assert run_async(exercise()) == 'test_redirection_carriers_and_special_destinations'


def test_replace_running_redirection(tmp_path):
    async def exercise():
        async with process_connection() as (conn, ready):
            old, new = tmp_path / 'old', tmp_path / 'new'
            with old.open('wb', buffering=0) as old_file, new.open('wb', buffering=0) as new_file:
                async with conn.create_process('replace', stdout=old_file, encoding=None) as client:
                    server = await bounded(ready.get())
                    server.stdout.write(b'old destination')
                    await wait_until(lambda: old.read_bytes() == b'old destination')
                    await client.redirect_stdout(new_file)
                    server.stdout.write(b'new destination')
                    await wait_until(lambda: new.read_bytes() == b'new destination')
                    await client.redirect_stdout(velnora.PIPE)
                    server.stdout.write(b'interactive again')
                    server.exit(0)
                    result = await bounded(client.wait())
                    assert (old.read_bytes(), new.read_bytes(), result.stdout, result.exit_status) == (
                        b'old destination', b'new destination', b'interactive again', 0)
            async with conn.create_process('replace-input', encoding=None) as client:
                server = await bounded(ready.get())
                await client.redirect_stdin(io.BytesIO(b'first source'), send_eof=False)
                assert await bounded(server.stdin.readexactly(12)) == b'first source'
                await client.redirect_stdin(io.BytesIO(b'second source'))
                assert await bounded(server.stdin.read()) == b'second source'
                server.exit(0)
                assert (await bounded(client.wait())).exit_status == 0
        return 'test_replace_running_redirection'
    assert run_async(exercise()) == 'test_replace_running_redirection'


def test_stream_subprocess_and_cross_connection():
    async def exercise():
        async with process_connection() as (conn, ready):
            writer, reader, errors = await bounded(conn.open_session('streams', encoding=None))
            server = await bounded(ready.get())
            writer.write(b'stream input')
            writer.write_eof()
            assert await bounded(server.stdin.read()) == b'stream input'
            server.stdout.write(b'stream output')
            server.stderr.write(b'stream error')
            server.exit(4)
            assert await bounded(reader.read()) == b'stream output'
            assert await bounded(errors.read()) == b'stream error'
            await bounded(writer.wait_closed())
            assert writer.channel.get_exit_status() == 4
            transport, protocol = await bounded(conn.create_subprocess(ProcessProtocol, 'subprocess'))
            server = await bounded(ready.get())
            transport.get_pipe_transport(0).write(b'protocol input')
            transport.get_pipe_transport(0).write_eof()
            assert await bounded(server.stdin.read()) == b'protocol input'
            server.stdout.write(b'protocol output')
            server.stderr.write(b'protocol error')
            server.exit(6)
            await bounded(protocol.done)
            assert bytes(protocol.output[1]) == b'protocol output'
            assert bytes(protocol.output[2]) == b'protocol error'
            assert transport.get_returncode() == 6
            transport.close()
            async with process_connection() as (other, other_ready):
                async with conn.create_process('producer', encoding=None) as producer:
                    source = await bounded(ready.get())
                    async with other.create_process('consumer', stdin=producer.stdout,
                                                    encoding=None) as consumer:
                        target = await bounded(other_ready.get())
                        source.stdout.write(b'across connections\x00\xff')
                        source.stderr.write(b'source error')
                        source.exit(0)
                        assert await bounded(target.stdin.read()) == b'across connections\x00\xff'
                        target.stdout.write(b'consumer output')
                        target.stderr.write(b'consumer error')
                        target.exit(3)
                        result = await bounded(consumer.wait())
                        assert (result.stdout, result.stderr, result.exit_status) == (
                            b'consumer output', b'consumer error', 3)
                    result = await bounded(producer.wait())
                    assert (result.stderr, result.exit_status) == (b'source error', 0)
        return 'test_stream_subprocess_and_cross_connection'
    assert run_async(exercise()) == 'test_stream_subprocess_and_cross_connection'
