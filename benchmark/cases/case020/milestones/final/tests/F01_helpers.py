# feature: F01
"""Public CLI bindings and caller-owned inputs for configuration acceptance."""
import configparser
import contextlib
import functools
import http.server
import os
from pathlib import Path
import threading
import zipfile

from _helpers import (PRODUCT_PYTHON, NATIVE_TOOL_DIRECTORY, Client, environment,
                      field, run, write_file)


def configuration_client(root, *, home=None, updates=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    env = environment({k: v for k, v in os.environ.items() if not k.startswith('VELMORA_')},
                      updates={'VELMORA_HOME': str(home or root / 'home'),
                               'VELMORA_NON_INTERACTIVE': '1', 'NO_COLOR': '1',
                               'PYTHONPATH': str(Path.cwd())})
    env['PATH'] = NATIVE_TOOL_DIRECTORY + os.pathsep + env['PATH']
    if updates:
        env.update(updates)
    return Client((PRODUCT_PYTHON, '-m', 'velmoras.velmora'), root, env)


def cli_success(client, *args):
    result = client.run(*map(str, args))
    assert result.returncode == 0, result
    return result


def cli_rejection(client, *args, status=1, label='ERROR:'):
    result = client.run(*map(str, args))
    assert result.returncode == status, result
    assert any(line.startswith(label) for line in result.text('stderr').splitlines()), result
    return result


def configuration_bundle(root, files):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        write_file(root / name, content)
    return root


def zip_configuration(source, archive):
    with zipfile.ZipFile(archive, 'w') as output:
        for path in Path(source).rglob('*'):
            if path.is_file():
                output.write(path, path.relative_to(source))
    return archive


def install_bundle(client, root, files):
    source = configuration_bundle(root, files)
    cli_success(client, 'config', 'install', source)
    return source


def profile_document(client, *args):
    return cli_success(client, 'profile', 'show', *args, '--format=json').json('stdout')


def profile_sections(client, context, *args):
    result = cli_success(client, 'profile', 'show', '--context', context, *args)
    parser = configparser.ConfigParser(interpolation=None, delimiters=('=',))
    parser.optionxform = str
    parser.read_string(result.text('stdout'))
    return parser


def graph_document(client, path='.', *args):
    return cli_success(client, 'graph', 'info', path, '-nr', '--format=json', *args).json('stdout')


def named_node(report, name, context='host'):
    nodes = [n for n in field(report, 'graph', 'nodes').values()
             if field(n, 'name') == name and field(n, 'context') == context]
    assert len(nodes) == 1, (name, context, nodes)
    return nodes[0]


def settings_profile(os_name='Linux', build_type='Release', arch='x86_64'):
    return f'[settings]\nos={os_name}\narch={arch}\nbuild_type={build_type}\n'


def configuration_recipe(path, *, name=None, extra='', settings=('os', 'arch', 'build_type')):
    identity = '' if name is None else f'    name = {name!r}\n    version = "1.0"\n'
    return write_file(Path(path) / 'velmorafile.py',
                      'from velmora import VelmoraFile\nclass Package(VelmoraFile):\n'
                      + identity + f'    settings = {settings!r}\n' + extra)


def export_context_packages(client):
    for name in ('hostpkg', 'toolpkg'):
        configuration_recipe(Path(client.cwd) / name, name=name)
        cli_success(client, 'export', name)
    configuration_recipe(client.cwd, extra='    requires = "hostpkg/1.0"\n'
                         '    tool_requires = "toolpkg/1.0"\n')


@contextlib.contextmanager
def configuration_http(root):
    """Serve real caller-created files on loopback, with bounded shutdown."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive(), 'HTTP server failed to stop'


def git_configuration_commit(root, env):
    for args in [('init',), ('add', '.'),
                 ('-c', 'user.name=Acceptance', '-c', 'user.email=acceptance@example.invalid',
                  'commit', '-m', 'Configuration input')]:
        result = run(('git', *args), cwd=root, env=env)
        assert result.returncode == 0, result


def graph_context_systems(client):
    report = graph_document(client)
    return (named_node(report, 'hostpkg', 'host')['settings']['os'],
            named_node(report, 'toolpkg', 'build')['settings']['os'])
