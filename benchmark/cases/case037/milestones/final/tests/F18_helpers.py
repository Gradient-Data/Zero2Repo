# feature: F18
"""Real filesystem services and independent SFTP v3 wire peer."""
import os
import asyncio
from types import SimpleNamespace
import struct
from contextlib import asynccontextmanager
from pathlib import Path
import velnora
import pytest
from _helpers import bounded
from F09_helpers import session_connection
from F07_helpers import AccessPolicy, access_connect
from F02_helpers import certificate_identity


@asynccontextmanager
async def file_service(root, *, factory=velnora.SFTPServer, version=6, chroot=True):
    # version=None leaves the server's SFTP version at its default.
    options = {} if version is None else {'sftp_version': version}
    async with session_connection(sftp_factory=lambda chan: factory(chan, chroot=root if chroot else None),
                                  **options) as (conn, _):
        yield conn


async def remote_bytes(client, path):
    async with client.open(path, 'rb') as file:
        return await file.read()


class SeparatedNames(velnora.SFTPServer):
    async def scandir(self, path):
        async for name in super().scandir(path):
            if name.filename not in (b'.', b'..'):
                name.filename = b'../' + name.filename
            yield name


class ApplicationMapping(velnora.SFTPServer):
    def map_path(self, path):
        if path == b'/published':
            return super().map_path(b'/actual')
        raise velnora.SFTPPermissionDenied('Path is not published')


def wire_string(value):
    return struct.pack('>I', len(value)) + value


class WireFields:
    def __init__(self, data):
        self.data = data
        self.offset = 0

    def take(self, size):
        result = self.data[self.offset:self.offset + size]
        assert len(result) == size, 'Truncated SFTP request'
        self.offset += size
        return result

    def number(self, fmt='>I'):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]

    def string(self):
        return self.take(self.number())


class DiskWireService:
    """Independent v3 service, with real file handles and copy-data extension.

    Sync publishes a snapshot only after flushing data to storage. Copy mode
    refuses READ/WRITE packets, so copying must happen within this service.
    """
    def __init__(self, root, *, extensions=True, copy_only=False, bad_version=False,
                 malformed=False, revoke_handle=False):
        self.root = Path(root)
        self.extensions = extensions
        self.copy_only = copy_only
        self.bad_version = bad_version
        self.malformed = malformed
        self.revoke_handle = revoke_handle

    async def __call__(self, process):
        handles = {}
        async def send(kind, payload):
            data = bytes([kind]) + payload
            process.stdout.write(struct.pack('>I', len(data)) + data)
            await process.stdout.drain()
        def status(request, code):
            return struct.pack('>II', request, code) + wire_string(b'') * 2
        try:
            while True:
                prefix = await process.stdin.readexactly(4)
                fields = WireFields(await process.stdin.readexactly(struct.unpack('>I', prefix)[0]))
                kind = fields.number('>B')
                if kind == 1:
                    payload = struct.pack('>I', 99 if self.bad_version else 3)
                    if self.extensions:
                        payload += wire_string(b'copy-data') + wire_string(b'1')
                        payload += wire_string(b'fsync@openssh.com') + wire_string(b'1')
                    await send(2, payload)
                    continue
                request = fields.number()
                if self.malformed:
                    await send(103, struct.pack('>I', request) + wire_string(b'unexpected data response'))
                    continue
                if kind == 3:
                    path, flags = fields.string(), fields.number()
                    local = self.root / os.fsdecode(path).lstrip('/')
                    mode = os.O_RDWR if flags & 2 else os.O_RDONLY
                    if flags & 8: mode |= os.O_CREAT
                    if flags & 16: mode |= os.O_TRUNC
                    fd = os.open(local, mode, 0o600)
                    handle = str(fd).encode()
                    handles[handle] = fd
                    await send(102, struct.pack('>I', request) + wire_string(handle))
                elif kind == 4:
                    handle = fields.string()
                    if handle not in handles:
                        await send(101, status(request, 9))
                    else:
                        os.close(handles.pop(handle))
                        await send(101, status(request, 0))
                elif kind in (5, 6):
                    if self.revoke_handle:
                        handle = fields.string()
                        os.close(handles.pop(handle))
                        await send(101, status(request, 9))
                        continue
                    if self.copy_only:
                        await send(101, status(request, 3))
                        continue
                    fd = handles[fields.string()]
                    offset = fields.number('>Q')
                    if kind == 5:
                        data = os.pread(fd, fields.number(), offset)
                        if data:
                            await send(103, struct.pack('>I', request) + wire_string(data))
                        else:
                            await send(101, status(request, 1))
                    else:
                        os.pwrite(fd, fields.string(), offset)
                        await send(101, status(request, 0))
                elif kind in (7, 8, 17):
                    try:
                        metadata = (os.fstat(handles[fields.string()]) if kind == 8 else
                                    os.stat(self.root / os.fsdecode(fields.string()).lstrip('/')))
                    except FileNotFoundError:
                        await send(101, status(request, 2))
                        continue
                    attrs = struct.pack('>IQIIIII', 15, metadata.st_size,
                        metadata.st_uid, metadata.st_gid, metadata.st_mode,
                        int(metadata.st_atime), int(metadata.st_mtime))
                    await send(105, struct.pack('>I', request) + attrs)
                elif kind == 200:
                    extension = fields.string()
                    if extension == b'copy-data' and self.extensions:
                        src = handles[fields.string()]
                        offset, size = fields.number('>Q'), fields.number('>Q')
                        dst = handles[fields.string()]
                        dst_offset = fields.number('>Q')
                        if size == 0: size = os.fstat(src).st_size - offset
                        data = os.pread(src, size, offset)
                        assert os.pwrite(dst, data, dst_offset) == len(data)
                        await send(101, status(request, 0))
                    elif extension == b'fsync@openssh.com' and self.extensions:
                        fd = handles[fields.string()]
                        os.fsync(fd)
                        data = os.pread(fd, os.fstat(fd).st_size, 0)
                        with (self.root / 'committed').open('wb') as output:
                            output.write(data)
                            output.flush()
                            os.fsync(output.fileno())
                        await send(101, status(request, 0))
                    else:
                        await send(101, status(request, 8))
                else:
                    await send(101, status(request, 8))
        except asyncio.IncompleteReadError as exc:
            if exc.partial:
                raise
            # A clean channel EOF ends this service, not an observation.
        finally:
            for fd in handles.values(): os.close(fd)
            process.exit(0)


class WireSession(velnora.SSHServerSession):
    def __init__(self, service, tasks):
        self.service, self.tasks = service, tasks
        self.reader = asyncio.StreamReader()

    def connection_made(self, channel):
        self.channel = channel

    def subsystem_requested(self, subsystem):
        return subsystem == 'sftp'

    def session_started(self):
        async def drain():
            await asyncio.sleep(0)
        process = SimpleNamespace(stdin=self.reader,
            stdout=SimpleNamespace(write=self.channel.write, drain=drain),
            exit=self.channel.exit)
        self.tasks.append(asyncio.create_task(self.service(process)))

    def data_received(self, data, datatype):
        self.reader.feed_data(data)

    def eof_received(self):
        self.reader.feed_eof()
        return True

    def connection_lost(self, exc):
        if exc: self.reader.set_exception(exc)
        else: self.reader.feed_eof()


class WirePolicy(AccessPolicy):
    def __init__(self, service, tasks):
        super().__init__(anonymous=True)
        self.service, self.tasks = service, tasks

    def session_requested(self):
        return WireSession(self.service, self.tasks)


@asynccontextmanager
async def wire_connection(service):
    tasks = []
    host, _ = certificate_identity()
    try:
        async with velnora.listen('127.0.0.1', 0, config=None,
                server_host_keys=[host], encoding=None,
                server_factory=lambda: WirePolicy(service, tasks)) as listener:
            async with access_connect(listener.get_port()) as conn:
                yield conn
    finally:
        if tasks:
            await bounded(asyncio.gather(*tasks))


async def transfer_scenarios(root, operation):
    # Shared scenario is feature-owned, and exercises each public transfer entry.
    local, remote = root / 'local', root / 'remote'
    local.mkdir(); remote.mkdir()
    source = local if operation == 'put' else remote
    target = local if operation == 'get' else remote
    (source / 'one').write_bytes(b'first selection\0')
    (source / 'two').write_bytes(b'second selection')
    (source / 'tree' / 'inner').mkdir(parents=True)
    (source / 'tree' / 'inner' / 'leaf').write_bytes(b'recursive leaf')
    (target / 'out').mkdir()
    (target / 'not-dir').write_bytes(b'unchanged')
    async with file_service(remote) as conn:
        async with conn.start_sftp_client(sftp_version=6) as client:
            entry = getattr(client, operation)
            def src(name): return str(source / name) if operation == 'put' else name
            def dst(name): return str(target / name) if operation == 'get' else name
            await entry(src('one'), dst('single'))
            assert (target / 'single').read_bytes() == b'first selection\0'
            await entry(src('one'), dst('out'))
            assert (target / 'out' / 'one').read_bytes() == b'first selection\0'
            await entry([src('one'), src('two')], dst('out'))
            assert (target / 'out' / 'two').read_bytes() == b'second selection'
            with pytest.raises(velnora.SFTPNotADirectory):
                await entry([src('one'), src('two')], dst('absent-dir'))
            with pytest.raises((velnora.SFTPNotADirectory, NotADirectoryError)):
                await entry([src('one'), src('two')], dst('not-dir'))
            assert (target / 'not-dir').read_bytes() == b'unchanged'
            with pytest.raises(velnora.SFTPFileIsADirectory):
                await entry(src('tree'), dst('recursive'))
            await entry(src('tree'), dst('recursive'), recurse=True)
            assert (target / 'recursive' / 'inner' / 'leaf').read_bytes() == b'recursive leaf'
            # Default remote destination is the remote working directory.
            if operation != 'get':
                await client.chdir('out')
                await entry(str(source / 'two') if operation == 'put' else '/two')
                assert (target / 'out' / 'two').read_bytes() == b'second selection'
            else:
                previous = os.getcwd()
                try:
                    os.chdir(target / 'out')
                    await entry('two')
                    assert (target / 'out' / 'two').read_bytes() == b'second selection'
                finally:
                    os.chdir(previous)

