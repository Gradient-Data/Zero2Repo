# feature: F15
"""Real SSH session setup with independently selected forwarding options."""
import asyncio
from contextlib import asynccontextmanager

import velnora

from F02_helpers import certificate_identity
from F07_helpers import access_connect
from F09_helpers import SessionPeer


@asynccontextmanager
async def forwarding_session(*, client_options, authorization=None,
                             client_keys=(), server_forwarding=True):
    ready = asyncio.Queue()
    host, _ = certificate_identity()
    async with velnora.listen(
            '127.0.0.1', 0, config=None, server_host_keys=[host],
            authorized_client_keys=authorization, line_editor=False,
            agent_forwarding=server_forwarding,
            server_factory=lambda: SessionPeer(
                ready, authenticated=authorization is not None, handler=True,
                application_options={})) as listener:
        async with access_connect(listener.get_port(), client_keys=list(client_keys),
                                  **client_options) as conn:
            yield conn, ready
