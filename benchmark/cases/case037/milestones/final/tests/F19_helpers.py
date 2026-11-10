# feature: F19
"""SCP services backed by real files and protocol fault injection peers."""
from contextlib import asynccontextmanager
import asyncio
import velnora
from F09_helpers import session_connection
from _helpers import bounded


@asynccontextmanager
async def scp_service(root, *, enabled=True, factory=velnora.SFTPServer):
    options = dict(sftp_factory=lambda channel: factory(channel, chroot=root))
    if enabled:
        options['allow_scp'] = True
    async with session_connection(handler=False, **options) as (connection, _):
        yield connection


@asynccontextmanager
async def scp_source_peer(name, data=b'', *, declared_size=None, directory=False):
    """Send caller-selected SCP wire data on a real SSH exec channel.

    With directory=True a single empty directory record is sent instead of a
    file record, followed by its end-of-directory record if it is accepted.
    """
    tasks = []
    async def source(process):
        tasks.append(asyncio.current_task())
        assert await bounded(process.stdin.readexactly(1)) == b'\0'
        size = len(data) if declared_size is None else declared_size
        if directory:
            process.stdout.write(b'D0755 0 ' + name + b'\n')
        else:
            process.stdout.write(b'C0644 ' + str(size).encode() + b' ' + name + b'\n')
        await bounded(process.stdout.drain())
        response = await bounded(process.stdin.read(1))
        if response == b'\0' and directory:
            process.stdout.write(b'E\n')
            await bounded(process.stdout.drain())
            assert await bounded(process.stdin.readexactly(1)) == b'\0'
        elif response == b'\0':
            process.stdout.write(data)
            if len(data) == size:
                process.stdout.write(b'\0')
                await bounded(process.stdout.drain())
                assert await bounded(process.stdin.readexactly(1)) == b'\0'
        elif response:
            assert response in (b'\1', b'\2')
            await bounded(process.stdin.readline())
        process.exit(0)
    try:
        async with session_connection(handler=False, process_factory=source,
                                      encoding=None) as (connection, _):
            yield connection
    finally:
        if tasks:
            await bounded(asyncio.gather(*tasks))
