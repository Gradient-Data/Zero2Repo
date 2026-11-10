# feature: F03
"""Public trust and authenticated-connection observations for F03."""
import asyncio

import velnora

from _helpers import bounded


def authorized_line(key, options=''):
    return (options + ' ' if options else '') + key.export_public_key().decode()


def host_line(pattern, identity, marker=''):
    data = (identity.export_public_key() if hasattr(identity, 'export_public_key')
            else identity.export_certificate('openssh'))
    return (marker + ' ' if marker else '') + pattern + ' ' + data.decode()


def matched_trust(text, host='node.example', addr='192.0.2.17', port=None):
    return velnora.match_known_hosts(velnora.import_known_hosts(text), host, addr, port)


async def authenticated_options(client_key, host_key, authorization, permissions):
    """Read restrictions only after a real public-key SSH authentication."""
    observed = asyncio.get_running_loop().create_future()

    class Observer(velnora.SSHServer):
        def connection_made(self, conn):
            self.conn = conn

        def auth_completed(self):
            observed.set_result((
                {name: self.conn.check_key_permission(name) for name in permissions},
                {name: self.conn.get_key_option(name)
                 for name in ('command', 'environment', 'permitopen')}))

    async with velnora.listen(
            '127.0.0.1', 0, server_factory=Observer, server_host_keys=[host_key],
            authorized_client_keys=authorization, config=None) as listener:
        async with velnora.connect(
                '127.0.0.1', listener.get_port(), username='member',
                client_keys=[client_key], known_hosts=None, agent_path=None,
                config=None):
            return await bounded(observed)
