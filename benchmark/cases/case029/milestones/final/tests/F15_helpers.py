# feature: F15
"""Real local workspace lifecycle and complete public observations."""
from contextlib import asynccontextmanager
from pathlib import Path

from _helpers import bounded
from velmora.sandbox.sandboxes.unix_local import UnixLocalSandboxClient
from velmora.sandbox.entries import File


@asynccontextmanager
async def local_workspace(manifest, *, client=None):
    client = client if client is not None else UnixLocalSandboxClient()
    session = await bounded(client.create(manifest=manifest))
    try:
        await bounded(session.start())
        yield session
    finally:
        await bounded(session.aclose())
        await bounded(client.delete(session))


async def workspace_bytes(session, path, **options):
    async def read_all():
        stream = await session.read(Path(path), **options)
        with stream:
            return stream.read()
    return await bounded(read_all())


async def workspace_command(session, *command, **options):
    return await bounded(session.exec(*command, timeout=15, **options))


class ApplicationWorkspaceClient(UnixLocalSandboxClient):
    """An application provider using real Unix-local files and execution."""

    def __init__(self, path, content):
        super().__init__()
        self.path = path
        self.content = content

    async def create(self, *, manifest, snapshot=None, options=None):
        manifest = manifest.model_copy(update={"entries": {
            **manifest.entries, self.path: File(content=self.content)}})
        return await super().create(manifest=manifest, snapshot=snapshot, options=options)
