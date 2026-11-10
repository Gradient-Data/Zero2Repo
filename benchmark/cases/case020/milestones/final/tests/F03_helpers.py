# feature: F03
"""Public recipe revision observations and real repository service fixtures."""
import contextlib
import socket
from pathlib import Path

from _helpers import PRODUCT_PYTHON, environment, run, service_process, write_file
from F01_helpers import cli_success, named_node
from F02_helpers import recipe_client, recipe_file


def exported_reference(client, path, *args):
    return cli_success(client, 'export', path, '-nr', '--format=json', *args).json('stdout')['reference']


def listed_revisions(client, reference, *, remote=None):
    args = ('-r', remote) if remote is not None else ()
    report = cli_success(client, 'list', reference + '#*', '--format=json', *args).json('stdout')
    return report[remote if remote is not None else 'Local Cache'][reference]['revisions']


def selected_recipe(client, reference, *args, local=False):
    flags = ('-nr',) if local else ()
    report = cli_success(client, 'graph', 'info', '--requires=' + reference,
                         '--format=json', *flags, *args).json('stdout')
    return named_node(report, reference.split('/')[0])


def git_command(root, env, *args):
    result = run(('git', *args), cwd=root, env=env)
    assert result.returncode == 0, result
    return result.text('stdout').strip()


@contextlib.contextmanager
def recipe_repository(root, env):
    """Run an actual product server with caller-owned storage and credentials."""
    root = Path(root)
    root.mkdir(parents=True)
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    write_file(root / 'server.conf', f'''[server]
jwt_secret: acceptance-repository-token-key
jwt_expire_minutes: 120
ssl_enabled: False
port: {port}
public_port: {port}
host_name: 127.0.0.1
authorize_timeout: 1800
disk_storage_path: {root / 'storage'}
disk_authorize_timeout: 1800
updown_secret: acceptance-repository-download-key
[write_permissions]
*/*@*/*: publisher
[read_permissions]
*/*@*/*: *
[users]
publisher: acceptance-password
''')
    server_env = environment(env, updates={'VELMORA_SERVER_HOME': str(root)})

    def ready(remaining):
        with socket.socket() as probe:
            probe.settimeout(min(remaining, 1))
            try:
                probe.connect(('127.0.0.1', port))
            except (ConnectionRefusedError, TimeoutError):
                return False
        return True

    with service_process('F03-repository-' + root.name,
                         (PRODUCT_PYTHON, '-m', 'velmoras.server.server_launcher'),
                         cwd=root, env=server_env, probe=ready):
        yield f'http://127.0.0.1:{port}'


def attach_repositories(client, repositories, *, publish=False):
    registered = cli_success(client, 'remote', 'list', '--format=json').json('stdout')
    assert isinstance(registered, list), registered
    if registered:
        cli_success(client, 'remote', 'remove', '*')
    assert cli_success(client, 'remote', 'list', '--format=json').json('stdout') == []
    for name, url in repositories:
        cli_success(client, 'remote', 'add', name, url)
        if publish:
            cli_success(client, 'remote', 'login', name, 'publisher', '-p', 'acceptance-password')


def revision_publisher(root, repositories):
    client = recipe_client(root)
    attach_repositories(client, repositories, publish=True)
    return client


def publish_revision(client, root, marker, remote):
    recipe_file(root, f'    description = {marker!r}\n', name='tracked')
    reference = exported_reference(client, root)
    cli_success(client, 'upload', reference, '-r', remote, '-c')
    return reference
