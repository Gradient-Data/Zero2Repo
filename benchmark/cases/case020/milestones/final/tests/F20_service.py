# feature: F20
"""Acceptance of persistent hosting and access policy through real clients."""
from _helpers import read_bytes, read_json, write_file
from F01_helpers import cli_success
from F02_helpers import recipe_client
from F06_helpers import binary_reference
from F12_helpers import selection, selected_artifacts, node_artifact, discovery_binary
from F13_helpers import assert_transferred, transfer_path, upload_report
from F20_helpers import (server_configuration, running_service, service_client, seed_artifact,
                         authenticated_token, artifact_routes,
                         assert_protocol_status)


def test_persistent_artifacts_across_restart(tmp_path):
    env = recipe_client(tmp_path / 'environment').env
    root = tmp_path / 'server'
    server_configuration(root, env)
    with running_service(root, env) as url:
        publisher = service_client(tmp_path / 'publisher', url, user='publisher')
        node = seed_artifact(publisher, tmp_path / 'recipe', marker='durable metadata')
        for reference in (node['ref'], binary_reference(node)):
            write_file(transfer_path(publisher, reference, 'metadata') / 'notes' / 'durable.txt',
                       'durable ' + reference)
        upload_report(publisher, binary_reference(node), '--metadata=notes/*')
        expected_recipe = read_bytes(tmp_path / 'recipe' / 'velmorafile.py')
        expected_info = read_bytes(transfer_path(publisher, binary_reference(node)) / 'velmorainfo.txt')
    with running_service(root, env) as url:
        reader = service_client(tmp_path / 'reader', url)
        assert selected_artifacts(selection(reader, '*#*:*#*', '-r', 'store0'), 'store0') == {node_artifact(node)}
        assert_transferred(reader, node)
        assert read_bytes(transfer_path(reader, node['ref']) / 'velmorafile.py') == expected_recipe
        assert read_bytes(transfer_path(reader, binary_reference(node)) / 'velmorainfo.txt') == expected_info
        cli_success(reader, 'download', binary_reference(node), '-r', 'store0', '--metadata=notes/*')
        for reference in (node['ref'], binary_reference(node)):
            assert read_bytes(transfer_path(reader, reference, 'metadata') / 'notes' / 'durable.txt') == (
                'durable ' + reference).encode()


def test_query_and_exact_artifact_retrieval(tmp_path):
    env = recipe_client(tmp_path / 'environment').env
    root = tmp_path / 'server'
    server_configuration(root, env)
    with running_service(root, env) as url:
        publisher = service_client(tmp_path / 'publisher', url, user='publisher')
        first = seed_artifact(publisher, tmp_path / 'first', marker='older')
        second = seed_artifact(publisher, tmp_path / 'second', marker='newer')
        seed_artifact(publisher, tmp_path / 'other', name='unrelated')
        reader = service_client(tmp_path / 'reader', url)
        found = selected_artifacts(selection(reader, 'freight/*#*:*#*', '-r', 'store0'), 'store0')
        assert found == {node_artifact(first), node_artifact(second)}
        for node, folder in [(first, 'first'), (second, 'second')]:
            assert_transferred(reader, node)
            assert read_bytes(transfer_path(reader, node['ref']) / 'velmorafile.py') == read_bytes(tmp_path / folder / 'velmorafile.py')
        changing = []
        for material in ('initial package', 'revised package'):
            changing_node = discovery_binary(publisher, tmp_path / 'changing', material=material)
            upload_report(publisher, binary_reference(changing_node))
            changing.append(changing_node)
        assert selected_artifacts(selection(reader, 'parcel/*#*:*#*', '-r', 'store0'), 'store0') == {node_artifact(n) for n in changing}
        for changing_node, material in zip(changing, ('initial package', 'revised package')):
            cli_success(reader, 'download', binary_reference(changing_node), '-r', 'store0')
            assert read_json(transfer_path(reader, binary_reference(changing_node)) / 'payload.json')['material'] == material
        recipe, package = artifact_routes(first)
        assert_protocol_status(url, 'GET', recipe + '/files/absent.txt', 404)
        assert_protocol_status(url, 'GET', package + '/files/absent.txt', 404)
        assert_protocol_status(url, 'GET', recipe.rsplit('/', 1)[0] + '/absent/files', 404)


def test_selected_revision_deletion(tmp_path):
    env = recipe_client(tmp_path / 'environment').env
    root = tmp_path / 'server'
    server_configuration(root, env)
    with running_service(root, env) as url:
        publisher = service_client(tmp_path / 'publisher', url, user='publisher')
        first = seed_artifact(publisher, tmp_path / 'first', marker='older')
        second = seed_artifact(publisher, tmp_path / 'second', marker='newer')
        # Remove a selected binary revision, then a selected recipe revision.
        cli_success(publisher, 'remove', binary_reference(first), '-r', 'store0', '-c')
        recipe, package = artifact_routes(first)
        assert_protocol_status(url, 'GET', package + '/files', 404)
        assert_protocol_status(url, 'GET', recipe + '/files/velmorafile.py', 200)
        reader = service_client(tmp_path / 'reader', url)
        assert selected_artifacts(selection(reader, '*#*:*#*', '-r', 'store0'), 'store0') == {node_artifact(second)}
        assert_transferred(reader, second)
        cli_success(publisher, 'remove', first['ref'], '-r', 'store0', '-c')
        assert_protocol_status(url, 'GET', recipe + '/files', 404)
        fresh = service_client(tmp_path / 'fresh', url)
        assert selected_artifacts(selection(fresh, '*#*:*#*', '-r', 'store0'), 'store0') == {node_artifact(second)}
        assert_transferred(fresh, second)
        changing = []
        for material in ('initial package', 'retained package'):
            changing_node = discovery_binary(publisher, tmp_path / 'changing', material=material)
            upload_report(publisher, binary_reference(changing_node))
            changing.append(changing_node)
        cli_success(publisher, 'remove', binary_reference(changing[0]), '-r', 'store0', '-c')
        assert_protocol_status(url, 'GET', artifact_routes(changing[0])[1] + '/files', 404)
        assert selected_artifacts(selection(fresh, 'parcel/*#*:*#*', '-r', 'store0'), 'store0') == {node_artifact(changing[1])}
        cli_success(fresh, 'download', binary_reference(changing[1]), '-r', 'store0')
        assert read_json(transfer_path(fresh, binary_reference(changing[1])) / 'payload.json')['material'] == 'retained package'


def test_separate_read_write_and_package_policy(tmp_path):
    env = recipe_client(tmp_path / 'environment').env
    root = tmp_path / 'server'
    server_configuration(root, env)
    with running_service(root, env) as url:
        node = seed_artifact(service_client(tmp_path / 'publisher', url, user='publisher'), tmp_path / 'recipe')
    server_configuration(root, env, read=(('*/*@*/*', 'reader'),))
    with running_service(root, env) as url:
        reader = authenticated_token(url, 'reader', 'reader-password')
        writer = authenticated_token(url)
        for route in artifact_routes(node):
            assert_protocol_status(url, 'GET', route + '/files', 200, token=reader)
            assert_protocol_status(url, 'GET', route + '/files', 403, token=writer)
            assert_protocol_status(url, 'PUT', route + '/files/policy.txt', 403, token=reader, body=b'rejected')
            assert_protocol_status(url, 'DELETE', route, 403, token=reader)
            assert_protocol_status(url, 'DELETE', route, 401)
            # A refused write stored nothing and a refused deletion removed nothing.
            assert_protocol_status(url, 'GET', route + '/files/policy.txt', 404, token=reader)
            assert_protocol_status(url, 'GET', route + '/files', 200, token=reader)
            assert_protocol_status(url, 'PUT', route + '/files/policy.txt', 200, token=writer, body=b'authorized material')
            assert assert_protocol_status(url, 'GET', route + '/files/policy.txt', 200, token=reader) == b'authorized material'
        for route in reversed(artifact_routes(node)):
            assert_protocol_status(url, 'DELETE', route, 200, token=writer)
            assert_protocol_status(url, 'GET', route + '/files', 404, token=reader)


def test_first_matching_permission_rule(tmp_path):
    env = recipe_client(tmp_path / 'environment').env
    root = tmp_path / 'server'
    server_configuration(root, env)
    with running_service(root, env) as url:
        node = seed_artifact(service_client(tmp_path / 'publisher', url, user='publisher'), tmp_path / 'recipe')
    narrow = ('freight/*@*/*', 'publisher')
    # Each rule differs from the stored identity in one component, so none of them matches it.
    foreign = (('unrelated/*@*/*', 'outsider'), ('freight/2.0@*/*', 'outsider'),
               ('freight/1.0@team/*', 'outsider'), ('freight/1.0@*/stable', 'outsider'))
    # The later rule of the first pair would admit everyone, had the first match not decided.
    for rules, expected in [((*foreign, narrow, ('*/*@*/*', '*')), 403),
                            ((*foreign, ('*/*@*/*', 'reader'), narrow), 200)]:
        server_configuration(root, env, read=rules, write=rules)
        with running_service(root, env) as url:
            token = authenticated_token(url, 'reader', 'reader-password')
            for route in artifact_routes(node):
                assert_protocol_status(url, 'GET', route + '/files', expected, token=token)
                assert_protocol_status(url, 'PUT', route + '/files/order.txt',
                                       200 if expected == 200 else 403, token=token, body=b'ordered permission')
                if expected == 200:
                    assert assert_protocol_status(url, 'GET', route + '/files/order.txt', 200, token=token) == b'ordered permission'
                else:
                    assert_protocol_status(url, 'GET', route + '/files', 401)
                    assert_protocol_status(url, 'PUT', route + '/files/order.txt', 401, body=b'ordered permission')


def test_named_authenticated_anonymous_and_unmatched_rules(tmp_path):
    env = recipe_client(tmp_path / 'environment').env
    root = tmp_path / 'server'
    server_configuration(root, env)
    with running_service(root, env) as url:
        node = seed_artifact(service_client(tmp_path / 'publisher', url, user='publisher'), tmp_path / 'recipe')
    for users in ['reader', 'publisher,reader', '?', '*', None]:
        rules = () if users is None else (('*/*@*/*', users),)
        server_configuration(root, env, read=rules, write=rules)
        with running_service(root, env) as url:
            tokens = [None, authenticated_token(url, 'reader', 'reader-password'),
                      authenticated_token(url, 'outsider', 'outsider-password')]
            for identity, token in enumerate(tokens):
                allowed = (users == '*' or users == '?' and identity > 0 or
                           users in ('reader', 'publisher,reader') and identity == 1)
                refusal = 401 if identity == 0 else 403
                for route in artifact_routes(node):
                    assert_protocol_status(url, 'GET', route + '/files', 200 if allowed else refusal, token=token)
                    path = route + f'/files/audience-{identity}.txt'
                    assert_protocol_status(url, 'PUT', path, 200 if allowed else refusal, token=token, body=b'audience payload')
                    if allowed:
                        assert assert_protocol_status(url, 'GET', path, 200, token=token) == b'audience payload'


def test_invalid_credentials_and_permission_configuration(tmp_path):
    env = recipe_client(tmp_path / 'environment').env
    root = tmp_path / 'server'
    server_configuration(root, env)
    with running_service(root, env) as url:
        node = seed_artifact(service_client(tmp_path / 'publisher', url, user='publisher'), tmp_path / 'recipe')
        previous_credential = authenticated_token(url)
    server_configuration(root, env, read=(('*/*@*/*', 'publisher'),),
                         authentication_secret='rotated-service-authentication-secret')
    with running_service(root, env) as url:
        assert_protocol_status(url, 'GET', 'users/authenticate', 401, credentials=('publisher', 'incorrect'))
        assert_protocol_status(url, 'GET', 'users/authenticate', 401, credentials=('unknown', 'incorrect'))
        assert_protocol_status(url, 'GET', 'users/authenticate', 401, credentials=('publisher', 'reader-password'))
        assert_protocol_status(url, 'GET', 'users/check_credentials', 401)
        assert_protocol_status(url, 'GET', 'users/check_credentials', 401, token=previous_credential)
        token = authenticated_token(url)
        assert_protocol_status(url, 'GET', 'users/check_credentials', 200, token=token)
        for route in artifact_routes(node):
            assert_protocol_status(url, 'GET', route + '/files', 401)
            assert_protocol_status(url, 'GET', route + '/files', 401, token=previous_credential)
            assert_protocol_status(url, 'GET', route + '/files', 200, token=token)
    server_configuration(root, env, read=(('invalid-rule', '*'),), write=(('invalid-rule', '*'),))
    with running_service(root, env, configuration_rejection=True) as url:
        if url is not None:
            token = authenticated_token(url)
            for route in artifact_routes(node):
                assert assert_protocol_status(url, 'GET', route + '/files', 500, token=token)
                assert assert_protocol_status(url, 'PUT', route + '/files/invalid.txt', 500, token=token, body=b'refused')
    server_configuration(root, env)
    with running_service(root, env) as url:
        for route in artifact_routes(node):
            assert_protocol_status(url, 'GET', route + '/files/invalid.txt', 404)
        assert_transferred(service_client(tmp_path / 'fresh', url), node)


def test_installed_authentication_and_authorization_extensions(tmp_path):
    env = recipe_client(tmp_path / 'environment').env
    root = tmp_path / 'server'
    server_configuration(root, env)
    with running_service(root, env) as url:
        node = seed_artifact(service_client(tmp_path / 'publisher', url, user='publisher'), tmp_path / 'recipe')
    write_file(root / 'plugins/authenticator/external.py', '''def get_class():
    return ExternalAuthentication()
class ExternalAuthentication:
    def valid_user(self, username, plain_password):
        return username in ('guest', 'curator') and plain_password == 'extension-password'
''')
    write_file(root / 'plugins/authorizer/external.py', '''from velmora.internal.errors import ForbiddenException, AuthenticationException

def get_class():
    return ExternalAuthorization()
class ExternalAuthorization:
    def check_read_velmora(self, username, ref):
        if username is None:
            raise AuthenticationException()
        if username not in ('guest', 'curator'):
            raise ForbiddenException()
    def check_write_velmora(self, username, ref):
        if username is None:
            raise AuthenticationException()
        if username != 'curator':
            raise ForbiddenException()
    check_delete_velmora = check_write_velmora
    def check_read_package(self, username, pref):
        self.check_read_velmora(username, pref.ref)
    def check_write_package(self, username, pref):
        self.check_write_velmora(username, pref.ref)
    check_delete_package = check_write_package
''')
    server_configuration(root, env, read=(), write=(), extensions=True)
    with running_service(root, env) as url:
        assert_protocol_status(url, 'GET', 'users/authenticate', 401, credentials=('publisher', 'acceptance-password'))
        guest = authenticated_token(url, 'guest', 'extension-password')
        curator = authenticated_token(url, 'curator', 'extension-password')
        for route in artifact_routes(node):
            assert_protocol_status(url, 'GET', route + '/files', 401)
            assert_protocol_status(url, 'GET', route + '/files', 200, token=guest)
            assert_protocol_status(url, 'PUT', route + '/files/extension.txt', 403, token=guest, body=b'not authorized')
            assert_protocol_status(url, 'DELETE', route, 403, token=guest)
            assert_protocol_status(url, 'PUT', route + '/files/extension.txt', 200, token=curator, body=b'extension authorized')
            assert assert_protocol_status(url, 'GET', route + '/files/extension.txt', 200, token=guest) == b'extension authorized'
        for route in reversed(artifact_routes(node)):
            assert_protocol_status(url, 'DELETE', route, 200, token=curator)
            assert_protocol_status(url, 'GET', route + '/files', 404, token=guest)
