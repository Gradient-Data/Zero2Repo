# feature: F14
"""Real routed SSH peers and a byte-transparent subprocess proxy."""
import sys
from contextlib import asynccontextmanager

import velnora

from _helpers import bounded
from F07_helpers import AccessPolicy
from F04_helpers import report_session


class RoutedPeer(AccessPolicy):
    """Only explicitly provisioned next-hop routes can be forwarded."""
    def __init__(self, key, routes):
        super().__init__(key=key)
        self.routes = routes
        self.connections = []

    def connection_made(self, conn):
        super().connection_made(conn)
        self.connections.append(conn)

    def connection_requested(self, dest_host, dest_port, orig_host, orig_port):
        endpoint = self.routes.get((dest_host, dest_port))
        if endpoint is None:
            return False
        return self.conn.forward_connection(*endpoint)


@asynccontextmanager
async def routed_listener(host_key, user_key, routes):
    policy = RoutedPeer(user_key, routes)
    async with velnora.listen(
            '127.0.0.1', 0, config=None, server_host_keys=[host_key],
            server_factory=lambda: policy, process_factory=report_session) as listener:
        try:
            yield listener, policy
        finally:
            for conn in policy.connections:
                conn.close()
            for conn in policy.connections:
                await bounded(conn.wait_closed())


def topology_options(host_key, user_key, **options):
    result = dict(config=None, known_hosts=([host_key.convert_to_public()], [], []),
                  username='member', client_keys=[user_key], agent_path=None)
    result.update(options)
    return result


# The proxy uses only OS sockets and pipes, never the product's transport code.
_PROXY = '''
import os, select, socket, sys
with socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=10) as sock:
    sock.settimeout(None)
    inputs = [sock, sys.stdin.buffer]
    while True:
        if os.path.exists(sys.argv[3]):
            break
        ready, _, _ = select.select(inputs, [], [], 0.05)
        for source in ready:
            data = os.read(source.fileno(), 65536)
            if not data:
                if source is sock:
                    sys.exit(0)
                sock.shutdown(socket.SHUT_WR)
                inputs.remove(source)
            elif source is sock:
                while data:
                    data = data[os.write(1, data):]
            else:
                sock.sendall(data)
'''


def socket_proxy(port, stop_path):
    return [sys.executable, '-c', _PROXY, '127.0.0.1', str(port), str(stop_path)]
