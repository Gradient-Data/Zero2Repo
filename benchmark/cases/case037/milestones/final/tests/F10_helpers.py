# feature: F10
"""Real process peers and subprocess observations for process acceptance tests."""
import asyncio
from contextlib import asynccontextmanager

import velnora

from _helpers import bounded
from F02_helpers import certificate_identity
from F07_helpers import AccessPolicy, access_connect


@asynccontextmanager
async def process_connection():
    ready = asyncio.Queue()
    host, _ = certificate_identity()

    def accepted(process):
        ready.put_nowait(process)

    async with velnora.listen(
            '127.0.0.1', 0, config=None, server_host_keys=[host],
            server_factory=lambda: AccessPolicy(anonymous=True),
            process_factory=accepted, encoding=None, line_editor=False) as listener:
        async with access_connect(listener.get_port()) as connection:
            yield connection, ready


class ProcessProtocol(velnora.SSHSubprocessProtocol):
    def __init__(self):
        self.output = {1: bytearray(), 2: bytearray()}
        self.done = asyncio.get_running_loop().create_future()
        self.closed = set()

    def pipe_data_received(self, fd, data):
        self.output[fd].extend(data)

    def pipe_connection_lost(self, fd, exc):
        self.closed.add(fd)
        if not self.done.done():
            if exc is not None:
                self.done.set_exception(exc)
            elif self.closed == {1, 2}:
                self.done.set_result(None)


async def server_exchange(ready, expected, out, err, status=0):
    process = await bounded(ready.get())
    assert await bounded(process.stdin.read()) == expected
    process.stdout.write(out)
    process.stderr.write(err)
    process.exit(status)


@asynccontextmanager
async def asyncio_socket_stream(sock):
    """Expose a real socket through the standard asyncio stream API."""
    reader, writer = await bounded(asyncio.open_connection(sock=sock))
    try:
        yield reader, writer
    finally:
        writer.close()
        await bounded(writer.wait_closed())
