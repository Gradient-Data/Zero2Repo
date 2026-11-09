# feature: F06
"""Real SSH peers and bounded transport observations."""
import asyncio
import getpass
import socket
import struct
from contextlib import asynccontextmanager

import velnora

from _helpers import bounded, managed_service
from F02_helpers import certificate_identity
from F04_helpers import ConfigPeer


class TransportPeer(ConfigPeer):
    """Permit the listener used to observe connection-owned resources."""
    def server_requested(self, listen_host, listen_port):
        return True


async def echo_session(process):
    data = await process.stdin.read()
    process.stdout.write(b'received:' + data)
    process.exit(0)


@asynccontextmanager
async def transport_listener(**options):
    key, _ = certificate_identity()
    options.setdefault('server_host_keys', [key])
    options.setdefault('server_factory', TransportPeer)
    options.setdefault('process_factory', echo_session)
    async with velnora.listen('127.0.0.1', 0, config=None, encoding=None,
                               **options) as listener:
        yield listener, key


def client_options(**options):
    return dict(config=None, known_hosts=None, agent_path=None,
                client_keys=[], username='member', **options)


async def checked_exchange(conn, payload=b'\x00SSH application\xff\n' * 257):
    result = await bounded(conn.run('receive', input=payload, encoding=None))
    assert result.exit_status == 0, result.stderr
    assert result.stdout == b'received:' + payload
    return result


async def openssh_exchange(port, *, options=(), payload=b'\x00independent peer\xff\n' * 257,
                           expect_success=True, delay_before_eof=0):
    argv = ['ssh', '-F', '/dev/null', '-T', '-v', '-p', str(port),
            '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null',
            '-o', 'GlobalKnownHostsFile=/dev/null', '-o', 'BatchMode=yes',
            '-o', 'ConnectTimeout=5']
    for option in options:
        argv += ['-o', option]
    proc = await asyncio.create_subprocess_exec(
        *argv, 'member@127.0.0.1', 'receive', stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    output, diagnostics = bytearray(), bytearray()
    async def collect(stream, target):
        while chunk := await stream.read(65536):
            target.extend(chunk)

    async def send():
        # A peer which ends early may close the pipe first; the exit status
        # and the received output below decide the verdict either way.
        try:
            proc.stdin.write(payload)
            await proc.stdin.drain()
            if delay_before_eof:
                await asyncio.sleep(delay_before_eof)
            proc.stdin.close()
            await proc.stdin.wait_closed()
        except (BrokenPipeError, ConnectionResetError):
            pass

    tasks = [asyncio.create_task(collect(proc.stdout, output)),
             asyncio.create_task(collect(proc.stderr, diagnostics)),
             asyncio.create_task(send()), asyncio.create_task(proc.wait())]
    try:
        try:
            await bounded(asyncio.gather(*tasks), timeout=20)
        except TimeoutError as exc:
            raise AssertionError('Independent SSH exchange timed out: ' +
                                 diagnostics.decode(errors='replace')) from exc
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    out, err = bytes(output), bytes(diagnostics)
    if expect_success:
        assert proc.returncode == 0, err.decode(errors='replace')
        assert out == b'received:' + payload
    else:
        assert proc.returncode == 255, (out, err)
    return out, err


@asynccontextmanager
async def openssh_daemon(directory, *, host_keys=None, extra=''):
    """An independent non-root OpenSSH server with real key authentication."""
    user_key, _ = certificate_identity()
    keys = host_keys or [certificate_identity()[0]]
    directory.mkdir(parents=True, exist_ok=True)
    auth = directory / 'authorized_keys'
    user_key.write_public_key(auth)
    paths = []
    for index, key in enumerate(keys):
        path = directory / ('host-' + str(index))
        key.write_private_key(path)
        path.chmod(0o600)
        paths.append(path)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    config = directory / 'sshd_config'
    config.write_text(
        f'Port {port}\nListenAddress 127.0.0.1\nPidFile {directory}/pid\n' +
        ''.join(f'HostKey {p}\n' for p in paths) +
        f'AuthorizedKeysFile {auth}\nStrictModes no\nUsePAM no\n'
        'PasswordAuthentication no\nKbdInteractiveAuthentication no\n'
        'PermitRootLogin yes\nLogLevel DEBUG3\n' + extra)

    async def ready(service):
        try:
            reader, writer = await asyncio.open_connection('127.0.0.1', port)
        except ConnectionRefusedError:
            return False
        banner = await bounded(reader.readline())
        writer.close()
        await writer.wait_closed()
        assert banner.startswith(b'SSH-2.0-OpenSSH'), banner
        return True

    async with managed_service(['/usr/sbin/sshd', '-D', '-e', '-f', str(config)],
                               ready=ready) as service:
        yield port, user_key, keys, service


async def daemon_connect(port, user_key, **options):
    return await velnora.connect('127.0.0.1', port, config=None, known_hosts=None,
                                  agent_path=None, client_keys=[user_key],
                                  username=getpass.getuser(), **options)


@asynccontextmanager
async def wire_proxy(port):
    """Forward real ciphertext, optionally corrupting the next server record."""
    state = {'corrupt': False, 'corrupt_client': False, 'flipped': False,
             'drop_client': False, 'drop_server': False}
    tasks, writers = [], []

    async def handler(reader, writer):
        upstream, sender = await asyncio.open_connection('127.0.0.1', port)
        writers.extend([writer, sender])

        async def pump(source, target, incoming):
            while True:
                data = await source.read(65536)
                if not data:
                    target.close()
                    return
                if state['drop_server' if incoming else 'drop_client']:
                    continue
                flag = 'corrupt' if incoming else 'corrupt_client'
                if state[flag]:
                    state[flag] = False
                    state['flipped'] = True
                    index = min(8, len(data) - 1)
                    data = data[:index] + bytes([data[index] ^ 1]) + data[index+1:]
                target.write(data)
                await target.drain()
        tasks.extend([asyncio.create_task(pump(reader, sender, False)),
                      asyncio.create_task(pump(upstream, writer, True))])

    server = await asyncio.start_server(handler, '127.0.0.1', 0)
    try:
        yield server.sockets[0].getsockname()[1], state
    finally:
        server.close()
        await server.wait_closed()
        for writer in writers:
            writer.close()
        for task in tasks:
            task.cancel()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException) and not isinstance(
                    result, (asyncio.CancelledError, ConnectionResetError, BrokenPipeError)):
                raise result


class ClientClosure(velnora.SSHClient):
    """Record the public closure callback without classifying exceptions."""
    def __init__(self, closed):
        self.closed = closed

    def connection_lost(self, exc):
        self.closed.set_result(exc)


class ServerClosure(TransportPeer):
    """Record public authentication and closure callbacks."""
    def __init__(self, authenticated, closed):
        super().__init__()
        self.authenticated = authenticated
        self.closed = closed

    def auth_completed(self):
        self.authenticated.set_result(True)

    def connection_lost(self, exc):
        self.closed.set_result(exc)


async def volume_session(process):
    """Return caller-selected amounts of caller-selected channel content."""
    while True:
        header = await process.stdin.readexactly(4)
        size = struct.unpack('>I', header)[0]
        if not size:
            process.exit(0)
            return
        block = await process.stdin.readexactly(32)
        process.stdout.write((block * ((size + len(block) - 1) // len(block)))[:size])
        await process.stdout.drain()


def independent_default_rekey_peer(port, mode="bytes"):
    import time
    import json
    import os
    from pathlib import Path
    import sys
    import tempfile
    import zipfile
    with tempfile.TemporaryDirectory() as directory:
        for name in ('F06_paramiko.whl', 'F06_pynacl.whl'):
            with zipfile.ZipFile(Path(__file__).with_name(name)) as archive:
                archive.extractall(directory)
        sys.path.insert(0, directory)
        import paramiko

        class MeasuredPackets(paramiko.Packetizer):
            # Only the independent peer's own automatic rekey is disabled.
            REKEY_BYTES = 1 << 40
            REKEY_PACKETS = 1 << 40

            def __init__(self, sock):
                super().__init__(sock)
                self.records = []
                self.order = []
                self.times = []
                self.capture = None

            def read_all(self, size, check_rekey=False):
                data = super().read_all(size, check_rekey)
                if self.capture is not None:
                    self.capture.extend(data)
                return data

            def read_message(self):
                self.capture = bytearray()
                kind, message = super().read_message()
                length = struct.unpack('>I', self.capture[:4])[0]
                self.capture = None
                self.records.append((length, kind))
                self.times.append((time.monotonic(), kind))
                self.order.append(('receive', kind))
                return kind, message

            def send_message(self, message):
                self.order.append(('send', message.asbytes()[0]))
                return super().send_message(message)

        with socket.create_connection(('127.0.0.1', port), timeout=10) as sock:
            with paramiko.Transport(sock, packetizer_class=MeasuredPackets) as transport:
                security = transport.get_security_options()
                security.kex = ('curve25519-sha256@libssh.org',)
                security.ciphers = ('aes128-ctr',)
                security.digests = ('hmac-sha2-256-etm@openssh.com',)
                security.compression = ('none',)
                transport.start_client(timeout=10)
                transport.auth_none('member')
                channel = transport.open_session(timeout=10)
                channel.settimeout(30)
                channel.exec_command('volume')
                if mode == 'time':
                    # Probe actual elapsed time; never advance the product clock.
                    origin = time.monotonic()
                    schedule = list(range(0, 3571, 30)) + [3597, 3602]
                    sizes = [257] * len(schedule)
                else:
                    schedule = None
                    sizes = [1024 * 1024] * 1026 + [257]
                for index, size in enumerate(sizes):
                    if schedule is not None:
                        remaining = origin + schedule[index] - time.monotonic()
                        if remaining > 0:
                            time.sleep(remaining)
                    probe_started = time.monotonic()
                    block = os.urandom(32)
                    channel.sendall(struct.pack('>I', size) + block)
                    data = bytearray()
                    while len(data) < size:
                        part = channel.recv(size - len(data))
                        assert part, 'Unexpected channel EOF'
                        data.extend(part)
                    assert data == (block * ((size + 31) // 32))[:size]
                    if mode == 'time':
                        first = next(stamp for stamp, kind in transport.packetizer.times if kind == 20)
                        finished = time.monotonic()
                        count = sum(kind == 20 for _, kind in transport.packetizer.records)
                        if finished - first < 3599:
                            assert count == 1, transport.packetizer.times
                        if probe_started - first >= 3602:
                            assert count >= 2, transport.packetizer.times
                channel.sendall(struct.pack('>I', 0))
                channel.shutdown_write()
                assert channel.recv(1) == b''
                assert channel.recv_exit_status() == 0
                channel.close()
                result = {'records': transport.packetizer.records,
                          'order': transport.packetizer.order,
                          'times': transport.packetizer.times}
                print(json.dumps(result))


if __name__ == '__main__':
    import sys
    independent_default_rekey_peer(int(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else 'bytes')


async def independent_exchange(port, **options):
    """Run an external SSH implementation; its failures remain test failures."""
    import json
    import sys
    from pathlib import Path
    proc = await asyncio.create_subprocess_exec(sys.executable,
        str(Path(__file__).with_name('F06_peer.py')), 'client',
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await bounded(proc.communicate(json.dumps(
            dict(port=port, **options)).encode() + b'\n'), timeout=30)
        assert proc.returncode == 0, err.decode(errors='replace')
        return json.loads(out)
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.communicate()


@asynccontextmanager
async def independent_hostkeys(retained, added, invalid):
    import json
    import sys
    from pathlib import Path
    proc = await asyncio.create_subprocess_exec(sys.executable,
        str(Path(__file__).with_name('F06_peer.py')), 'server',
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    try:
        spec = dict(retained=retained.export_private_key('pkcs1-pem').decode(),
                    added=added.export_private_key('pkcs1-pem').decode(), invalid=invalid)
        proc.stdin.write(json.dumps(spec).encode() + b'\n')
        await proc.stdin.drain()
        line = await bounded(proc.stdout.readline(), timeout=15)
        if not line:
            raise AssertionError((await proc.stderr.read()).decode(errors='replace'))
        yield json.loads(line)['port']
        out, err = await bounded(proc.communicate(), timeout=20)
        assert proc.returncode == 0, err.decode(errors='replace')
        assert json.loads(out)['completed']
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.communicate()


def assert_rekey_boundary(result, threshold):
    """Check every measured product-initiated exchange against packet lengths."""
    records = result['records']
    starts = [i for i, row in enumerate(records) if row[1] == 20]
    assert len(starts) >= 2, 'No renewed key exchange observed'
    for left, right in zip(starts, starts[1:]):
        begin = next(i for i in range(left, right) if records[i][1] == 21) + 1
        if records[begin][1] == 7:
            begin += 1
        lengths = [row[0] for row in records[begin:right]]
        assert sum(lengths[:-1]) < threshold <= sum(lengths), (threshold, lengths)
    directions = [direction for direction, kind in result['order'] if kind == 20]
    assert directions[:2] == ['send', 'receive']
    assert directions[2:] == ['receive', 'send'] * (len(starts) - 1), directions


async def expect_connection_timeout(awaitable):
    """An outer bound must never impersonate the product's timeout result."""
    import pytest
    task = asyncio.ensure_future(awaitable)
    try:
        done, _ = await asyncio.wait([task], timeout=3)
        assert task in done, 'The product did not enforce the connection deadline'
        with pytest.raises(TimeoutError):
            await task
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@asynccontextmanager
async def independent_selection(algorithms, host_key=None, **options):
    import json
    import sys
    from pathlib import Path
    key = host_key or certificate_identity('ssh-rsa')[0]
    proc = await asyncio.create_subprocess_exec(sys.executable,
        str(Path(__file__).with_name('F06_peer.py')), 'selection',
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    result = {}
    try:
        proc.stdin.write(json.dumps(dict(algorithms=algorithms, **options,
            key=key.export_private_key('pkcs1-pem').decode())).encode() + b'\n')
        await proc.stdin.drain()
        line = await bounded(proc.stdout.readline(), timeout=15)
        if not line:
            raise AssertionError((await proc.stderr.read()).decode(errors='replace'))
        yield json.loads(line)['port'], result
        out, err = await bounded(proc.communicate(), timeout=20)
        assert proc.returncode == 0, err.decode(errors='replace')
        result.update(json.loads(out))
    except BaseException as exc:
        if proc.returncode is None:
            proc.kill()
        _, err = await proc.communicate()
        exc.add_note('Independent server diagnostics: ' + err.decode(errors='replace'))
        raise
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.communicate()
