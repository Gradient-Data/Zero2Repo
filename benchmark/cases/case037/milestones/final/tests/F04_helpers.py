# feature: F04
"""Real configuration-driven SSH peers and application observations."""
import json
from contextlib import asynccontextmanager

import velnora

from _helpers import bounded
from F02_helpers import certificate_identity


def config_file(directory, text, name='ssh_config'):
    path = directory / name
    path.write_text(text)
    return str(path)


class ConfigPeer(velnora.SSHServer):
    """An application peer accepting no credentials, a key, or a password."""
    def __init__(self, key=None, password=None):
        self.key = key
        self.password = password

    def begin_auth(self, username):
        return self.key is not None or self.password is not None

    def public_key_auth_supported(self):
        return self.key is not None

    def validate_public_key(self, username, key):
        return key == self.key.convert_to_public()

    def password_auth_supported(self):
        return self.password is not None

    def validate_password(self, username, password):
        return password == self.password

    def connection_requested(self, dest_host, dest_port, orig_host, orig_port):
        return True


async def report_session(process):
    """Expose the real request at the receiving application's public API."""
    process.stdout.write(json.dumps({
        'command': process.command,
        'username': process.get_extra_info('username'),
        'environment': dict(process.env),
        'terminal': process.term_type,
    }) + '\n')
    process.exit(0)


@asynccontextmanager
async def config_listener(*, key=None, password=None, host_key=None,
                          config=None, **kwargs):
    if host_key is None:
        host_key, _ = certificate_identity()
    async with velnora.listen(
            '127.0.0.1', 0, config=config,
            server_host_keys=[host_key],
            server_factory=lambda: ConfigPeer(key, password),
            process_factory=report_session, **kwargs) as listener:
        yield listener, host_key


async def session_report(conn, **kwargs):
    result = await bounded(conn.run(**kwargs))
    assert result.exit_status == 0, result.stderr
    return json.loads(result.stdout)


async def configured_report(path, *, host='target', **kwargs):
    async with velnora.connect(host, config=path, known_hosts=None,
                                agent_path=None, **kwargs) as conn:
        return await session_report(conn)


@asynccontextmanager
async def configuration_agent(directory, keys):
    """Run a real OpenSSH agent containing caller-supplied private keys."""
    from _helpers import managed_service, run_command, environment
    socket_path = directory / 'agent.sock'
    async with managed_service(['ssh-agent', '-D', '-a', str(socket_path)],
                               ready=lambda service: socket_path.exists()):
        for index, key in enumerate(keys):
            path = directory / ('agent-key-' + str(index))
            key.write_private_key(path)
            path.chmod(0o600)
            result = run_command(['ssh-add', str(path)],
                                 env=environment({'SSH_AUTH_SOCK': str(socket_path)}))
            assert result.returncode == 0, result.stderr
        yield str(socket_path)
