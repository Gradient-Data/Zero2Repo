# feature: F20
"""Persistent real service lifecycle and public remote protocol observations."""
import base64
import configparser
import contextlib
import http.client
import socket
from pathlib import Path
from urllib.parse import urlsplit

from _helpers import PRODUCT_PYTHON, environment, HelperError, ServiceProcess, write_file
from F01_helpers import cli_success
from F02_helpers import recipe_client
from F03_helpers import recipe_repository, attach_repositories
from F06_helpers import binary_reference
from F13_helpers import transfer_package, assert_transferred, upload_report


def server_configuration(root, env, *, read=(('*/*@*/*', '*'),),
                         write=(('*/*@*/*', 'publisher'),), extensions=False,
                         authentication_secret=None):
    root = Path(root)
    if not (root / 'server.conf').exists():
        with recipe_repository(root, env):
            pass
    parser = configparser.ConfigParser()
    parser.read(root / 'server.conf')
    for section, rules in [('read_permissions', read), ('write_permissions', write)]:
        parser[section] = dict(rules)
    parser['users'] = {'publisher': 'acceptance-password', 'reader': 'reader-password',
                       'outsider': 'outsider-password'}
    if authentication_secret is not None:
        parser['server']['jwt_secret'] = authentication_secret
    if extensions:
        parser['server']['custom_authenticator'] = 'external'
        parser['server']['custom_authorizer'] = 'external'
    with (root / 'server.conf').open('w') as stream:
        parser.write(stream)
    return 'http://127.0.0.1:' + parser['server']['port']


@contextlib.contextmanager
def running_service(root, env, *, configuration_rejection=False):
    root = Path(root)
    parser = configparser.ConfigParser()
    parser.read(root / 'server.conf')
    port = int(parser['server']['port'])
    def ready(remaining):
        with socket.socket() as probe:
            probe.settimeout(min(remaining, 1))
            try:
                probe.connect(('127.0.0.1', port))
            except (ConnectionRefusedError, TimeoutError):
                return False
        return True
    service = ServiceProcess('F20-service-' + root.name,
                             (PRODUCT_PYTHON, '-m', 'velmoras.server.server_launcher'),
                             cwd=root, env=environment(env, updates={'VELMORA_SERVER_HOME': str(root)}))
    try:
        try:
            service.wait_ready(ready)
        except HelperError:
            observed = service.snapshot()
            if not configuration_rejection or observed['returncode'] is None:
                raise
            assert observed['returncode'] != 0, observed
            assert observed['stderr'] or observed['stdout'], observed
            yield None
        else:
            yield 'http://127.0.0.1:' + str(port)
    finally:
        service.close()


def protocol_request(url, method, path, *, token=None, credentials=None, body=None):
    address = urlsplit(url)
    headers = {}
    if token is not None:
        headers['Authorization'] = 'Bearer ' + token
    if credentials is not None:
        headers['Authorization'] = 'Basic ' + base64.b64encode(':'.join(credentials).encode()).decode()
    connection = http.client.HTTPConnection(address.hostname, address.port, timeout=120)
    try:
        connection.request(method, '/v2/' + path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def authenticated_token(url, user='publisher', password='acceptance-password'):
    status, body = protocol_request(url, 'GET', 'users/authenticate', credentials=(user, password))
    assert status == 200, (status, body)
    return body.decode()


def artifact_routes(node):
    ref, revision = node['ref'].split('#')
    name, version = ref.split('/')
    recipe = f'velmoras/{name}/{version}/_/_/revisions/{revision}'
    package = recipe + f"/packages/{node['package_id']}/revisions/{node['prev']}"
    return recipe, package


def service_client(root, url, *, user=None):
    client = recipe_client(root)
    attach_repositories(client, [('store0', url)])
    if user:
        password = 'acceptance-password' if user == 'publisher' else user + '-password'
        cli_success(client, 'remote', 'login', 'store0', user, '-p', password)
    return client


def seed_artifact(client, root, *, name='freight', marker='first'):
    node = transfer_package(client, root, name=name, extra=f'    description = {marker!r}\n')
    upload_report(client, binary_reference(node))
    return node


def assert_protocol_status(url, method, path, expected, **kwargs):
    status, body = protocol_request(url, method, path, **kwargs)
    assert status == expected, (method, path, status, body)
    return body
