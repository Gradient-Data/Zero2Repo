# feature: F04
"""Acceptance of persistent remote selection, credentials and transport trust."""
import contextlib

from _helpers import Client
from F01_helpers import cli_rejection, cli_success, install_bundle, named_node
from F02_helpers import recipe_client, recipe_file
from F03_helpers import attach_repositories, recipe_repository, revision_publisher
from F04_helpers import (assert_remote_install, missing_remote_recipe, protected_repository,
                         publish_remote_package, remote_graph, remote_rows, remote_users,
                         repository_observer, tls_certificate)


def test_remote_management_persists(tmp_path):
    # F04.T01
    client = recipe_client(tmp_path)
    attach_repositories(client, [])
    cli_success(client, 'remote', 'add', 'west', 'https://west.example.invalid')
    cli_success(client, 'remote', 'add', 'east', 'https://east.example.invalid', '--index=0')
    assert [(r['name'], r['url'], r['enabled']) for r in remote_rows(client)] == [
        ('east', 'https://east.example.invalid', True),
        ('west', 'https://west.example.invalid', True)]
    before = remote_rows(client)
    cli_rejection(client, 'remote', 'add', 'east', 'https://new.example.invalid')
    cli_rejection(client, 'remote', 'rename', 'east', 'west')
    assert remote_rows(client) == before
    cli_success(client, 'remote', 'add', 'east', 'https://new.example.invalid', '--force')
    cli_success(client, 'remote', 'rename', 'west', 'central')
    cli_success(client, 'remote', 'update', 'central', '--url', 'https://central.example.invalid', '--index=0')
    cli_success(client, 'remote', 'disable', 'central')
    assert [(r['name'], r['url'], r['enabled']) for r in remote_rows(client)] == [
        ('central', 'https://central.example.invalid', False),
        ('east', 'https://new.example.invalid', True)]
    cli_success(client, 'remote', 'enable', 'central')
    assert remote_rows(client)[0]['enabled'] is True
    cli_success(client, 'remote', 'remove', 'east')
    assert [r['name'] for r in remote_rows(client)] == ['central']
    before = remote_rows(client)
    for command in (('rename', 'absent', 'other'), ('update', 'absent', '--url', 'https://other.example.invalid'),
                    ('remove', 'absent'), ('enable', 'absent'), ('disable', 'absent')):
        cli_rejection(client, 'remote', *command)
    assert remote_rows(client) == before
    # The recipe is available locally, so only the selection itself can cause this refusal.
    recipe_file(tmp_path / 'local', '', name='cargo', version='1.0')
    cli_success(client, 'export', tmp_path / 'local', '-nr')
    assert remote_graph(client, 'cargo/1.0', '-nr')['graph']['error'] is None
    cli_rejection(client, 'graph', 'info', '--requires=cargo/1.0', '-r', 'absent')


def test_remote_order_disabled_and_local_only(tmp_path):
    # F04.T02
    seed = recipe_client(tmp_path / 'seed')
    with contextlib.ExitStack() as stack:
        urls = [stack.enter_context(recipe_repository(tmp_path / name, seed.env))
                for name in ('west-server', 'east-server')]
        repos = list(zip(('west', 'east'), urls))
        publisher = revision_publisher(tmp_path / 'publisher', repos)
        for name, marker in (('west', 'western artifact'), ('east', 'eastern artifact')):
            publish_remote_package(publisher, tmp_path / name, name, marker=marker)
        for index, (preferred, disabled) in enumerate((('west', None), ('east', None), ('east', 'west'))):
            client = recipe_client(tmp_path / f'consumer-{index}')
            attach_repositories(client, repos)
            if disabled:
                cli_success(client, 'remote', 'disable', disabled)
            else:
                cli_success(client, 'remote', 'update', preferred, '--index=0')
            marker = 'western artifact' if preferred == 'west' else 'eastern artifact'
            node = assert_remote_install(client, 'cargo/1.0', marker)
            assert node['remote'] == preferred and node['binary_remote'] == preferred
            if disabled:
                assert {r['name']: r['enabled'] for r in remote_rows(client)} == {'west': False, 'east': True}
                # With nothing held locally, naming the disabled remote cannot obtain the recipe.
                cli_success(client, 'remove', '*', '-c')
                cli_rejection(client, 'graph', 'info', '--requires=cargo/1.0', '-r', disabled)
        # A first remote made ineligible by its filter passes the choice to the next one.
        filtered = recipe_client(tmp_path / 'filtered')
        attach_repositories(filtered, repos)
        cli_success(filtered, 'remote', 'update', 'west', '--allowed-packages', '!cargo/*')
        node = assert_remote_install(filtered, 'cargo/1.0', 'eastern artifact')
        assert node['remote'] == 'east' and node['binary_remote'] == 'east'
        offline = recipe_client(tmp_path / 'offline')
        attach_repositories(offline, repos)
        missing_remote_recipe(offline, 'cargo/1.0', '-nr')
        # A local recipe with no binary must not acquire the remote binary in local-only mode.
        cli_success(offline, 'download', 'cargo/1.0', '-r', 'west', '--only-recipe')
        report = remote_graph(offline, 'cargo/1.0', '-nr')
        cli_rejection(offline, 'install', '--requires=cargo/1.0', '-nr')
        assert named_node(report, 'cargo')['binary'] == 'Missing'
        assert named_node(report, 'cargo')['binary_remote'] is None
        assert_remote_install(offline, 'cargo/1.0', 'western artifact')
    # Both actual repositories have stopped; local-only installation still works.
    assert_remote_install(offline, 'cargo/1.0', 'western artifact', '-nr')


def test_recipes_only_excludes_binary_installation(tmp_path):
    # F04.T03
    seed = recipe_client(tmp_path / 'seed')
    with recipe_repository(tmp_path / 'server', seed.env) as url:
        publisher = revision_publisher(tmp_path / 'publisher', [('store', url)])
        publish_remote_package(publisher, tmp_path / 'source', 'store', marker='recipe and binary')
        for limited in (False, True):
            client = recipe_client(tmp_path / str(limited))
            attach_repositories(client, [('store', url)])
            if limited:
                cli_success(client, 'remote', 'update', 'store', '--recipes-only')
                report = remote_graph(client, 'cargo/1.0')
                cli_rejection(client, 'install', '--requires=cargo/1.0')
                node = named_node(report, 'cargo')
                assert node['remote'] == 'store'
                assert node['description'] == 'recipe and binary'
                assert node['binary'] == 'Missing'
                assert node['binary_remote'] is None
            else:
                assert_remote_install(client, 'cargo/1.0', 'recipe and binary')
        # The same restrictions can be declared when the remote is added.
        client = recipe_client(tmp_path / 'added')
        attach_repositories(client, [])
        cli_success(client, 'remote', 'add', 'store', url, '--allowed-packages', 'other/*')
        missing_remote_recipe(client, 'cargo/1.0')
        cli_success(client, 'remote', 'add', 'store', url, '--force', '--recipes-only')
        node = named_node(remote_graph(client, 'cargo/1.0'), 'cargo')
        assert node['remote'] == 'store' and node['binary'] == 'Missing'


def test_remote_package_filters_apply_all_patterns(tmp_path):
    # F04.T04
    seed = recipe_client(tmp_path / 'seed')
    with recipe_repository(tmp_path / 'server', seed.env) as url:
        publisher = revision_publisher(tmp_path / 'publisher', [('store', url)])
        for name in ('alpha', 'beta', 'gamma'):
            publish_remote_package(publisher, tmp_path / name, 'store', name=name, marker=name + ' contents')
        # These are distinct set rules, not a Cartesian product of spelling variants.
        scenarios = [(['alpha/*', 'beta/*'], {'alpha', 'beta'}),
                     (['!alpha/*', '!beta/*'], {'gamma'}),
                     (['*', '!beta/*'], {'alpha', 'gamma'}),
                     (['!beta/*', '*'], {'alpha', 'gamma'})]
        for index, (patterns, eligible) in enumerate(scenarios):
            for name in ('alpha', 'beta', 'gamma'):
                client = recipe_client(tmp_path / f'filter-{index}-{name}')
                attach_repositories(client, [('store', url)])
                flags = [item for pattern in patterns for item in ('--allowed-packages', pattern)]
                cli_success(client, 'remote', 'update', 'store', *flags)
                if name in eligible:
                    if index == 0:
                        # Nothing is held locally yet, so the remote itself must supply the range.
                        ranged = named_node(remote_graph(client, name + '/[>=1.0]'), name)
                        assert ranged['version'] == '1.0' and ranged['remote'] == 'store'
                        cli_success(client, 'remove', '*', '-c')
                    node = assert_remote_install(client, name + '/1.0', name + ' contents')
                    assert node['remote'] == 'store'
                else:
                    missing_remote_recipe(client, name + '/1.0')
                    if index == 0:
                        # The filter governs a version-range requirement as well.
                        error = remote_graph(client, name + '/[>=1.0]', rejected=True)['graph']['error']
                        assert error['type'] == 'missing', error


def test_remote_credentials_persist_and_remain_isolated(tmp_path):
    # F04.T05
    seed = recipe_client(tmp_path / 'seed')
    with contextlib.ExitStack() as stack:
        upstreams = [stack.enter_context(protected_repository(tmp_path / f'server-{i}', seed.env)) for i in range(2)]
        observed = [stack.enter_context(repository_observer(url)) for url in upstreams]
        repos = list(zip(('west', 'east'), [entry[0] for entry in observed]))
        publisher = revision_publisher(tmp_path / 'publisher', list(zip(('west', 'east'), upstreams)))
        for name in ('west', 'east'):
            publish_remote_package(publisher, tmp_path / name, name, marker=name + ' protected')
        client = recipe_client(tmp_path / 'consumer')
        attach_repositories(client, repos)
        cli_success(client, 'remote', 'login', 'west', 'publisher', '-p', 'acceptance-password')
        assert remote_users(client)['west']['user_name'] == 'publisher'
        assert remote_users(client)['west']['authenticated'] is True
        assert remote_users(client)['east']['authenticated'] is False
        cli_success(client, 'remote', 'add', 'west-alias', repos[0][1], '--force')
        assert remote_users(client)['west-alias']['user_name'] == 'publisher'
        assert remote_users(client)['west-alias']['authenticated'] is True
        assert_remote_install(client, 'cargo/1.0', 'west protected', '-r', 'west')
        cli_success(client, 'remove', '*', '-c')
        cli_rejection(client, 'install', '--requires=cargo/1.0', '-r', 'east')
        assert any(r['status'] == 401 for r in observed[1][1])
        observed[1][1].clear()
        cli_rejection(client, 'remote', 'login', 'east', 'publisher', '-p', 'incorrect-password')
        assert any(r['path'].endswith('/users/authenticate') and r['status'] == 401 for r in observed[1][1])
        cli_success(client, 'remote', 'login', 'east', 'outsider', '-p', 'outsider-password')
        assert remote_users(client)['east']['user_name'] == 'outsider'
        observed[1][1].clear()
        cli_rejection(client, 'install', '--requires=cargo/1.0', '-r', 'east')
        assert any(r['status'] == 403 for r in observed[1][1])
        cli_success(client, 'remote', 'logout', 'west')
        assert remote_users(client)['west']['authenticated'] is False
        assert remote_users(client)['west-alias']['authenticated'] is False
        observed[0][1].clear()
        cli_rejection(client, 'install', '--requires=cargo/1.0', '-r', 'west')
        assert any(r['status'] == 401 for r in observed[0][1])
        cli_success(client, 'remote', 'login', 'east', 'publisher', '-p', 'acceptance-password')
        assert_remote_install(client, 'cargo/1.0', 'east protected', '-r', 'east')


def test_noninteractive_environment_credential_precedence(tmp_path):
    # F04.T06
    seed = recipe_client(tmp_path / 'seed')
    with protected_repository(tmp_path / 'server', seed.env) as url:
        publisher = revision_publisher(tmp_path / 'publisher', [('store', url)])
        publish_remote_package(publisher, tmp_path / 'source', 'store', marker='private artifact')
        with repository_observer(url) as (observed_url, records):
            choices = [({'VELMORA_LOGIN_USERNAME': 'publisher', 'VELMORA_PASSWORD': 'acceptance-password'}, True),
                       ({'VELMORA_LOGIN_USERNAME': 'outsider', 'VELMORA_PASSWORD': 'outsider-password',
                         'VELMORA_LOGIN_USERNAME_STORE': 'publisher',
                         'VELMORA_PASSWORD_STORE': 'acceptance-password'}, True),
                       ({}, False)]
            for index, (credentials, allowed) in enumerate(choices):
                base = recipe_client(tmp_path / f'consumer-{index}')
                attach_repositories(base, [('store', observed_url)])
                assert remote_users(base)['store']['authenticated'] is False
                client = Client(base.command, base.cwd, dict(base.env, **credentials))
                records.clear()
                if allowed:
                    assert_remote_install(client, 'cargo/1.0', 'private artifact')
                    assert remote_users(client)['store']['user_name'] == 'publisher'
                    assert remote_users(client)['store']['authenticated'] is True
                    assert any(r['path'].endswith('/users/authenticate') and r['status'] == 200 for r in records)
                else:
                    cli_rejection(client, 'install', '--requires=cargo/1.0')
                    assert any(r['status'] == 401 for r in records)
            # Valid credentials wait on stdin, so only non-interactive selection can refuse them.
            base = recipe_client(tmp_path / 'consumer-selected')
            attach_repositories(base, [('store', observed_url)])
            records.clear()
            refused = base.run('install', '--requires=cargo/1.0', '-cc', 'core:non_interactive=True',
                               stdin='publisher\nacceptance-password\n')
            assert refused.returncode == 1, refused
            assert any(line.startswith('ERROR:') for line in refused.text('stderr').splitlines()), refused
            assert any(r['status'] == 401 for r in records)
            assert remote_users(base)['store']['authenticated'] is False


def test_remote_tls_trust_and_per_remote_opt_out(tmp_path):
    # F04.T07
    seed = recipe_client(tmp_path / 'seed')
    cert, key = tls_certificate(tmp_path / 'tls', seed.env)
    with recipe_repository(tmp_path / 'server', seed.env) as upstream:
        publisher = revision_publisher(tmp_path / 'publisher', [('store', upstream)])
        publish_remote_package(publisher, tmp_path / 'source', 'store', marker='TLS artifact')
        with contextlib.ExitStack() as stack:
            endpoints = [stack.enter_context(repository_observer(upstream, certificate=cert, key=key)) for _ in range(2)]
            repos = list(zip(('west', 'east'), [entry[0] for entry in endpoints]))
            trusted = recipe_client(tmp_path / 'trusted')
            attach_repositories(trusted, repos)
            # Explicit caller trust keeps verification enabled for a genuine TLS baseline.
            install_bundle(trusted, tmp_path / 'trust-config', {'global.conf': f'core.net.http:cacert_path={cert}\n'})
            assert all(r['verify_ssl'] is True for r in remote_rows(trusted))
            assert_remote_install(trusted, 'cargo/1.0', 'TLS artifact', '-r', 'west')
            untrusted = recipe_client(tmp_path / 'untrusted')
            attach_repositories(untrusted, repos)
            cli_rejection(untrusted, 'install', '--requires=cargo/1.0', '-r', 'west')
            cli_success(untrusted, 'remote', 'update', 'west', '--insecure')
            assert {r['name']: r['verify_ssl'] for r in remote_rows(untrusted)} == {'west': False, 'east': True}
            assert_remote_install(untrusted, 'cargo/1.0', 'TLS artifact', '-r', 'west')
            cli_success(untrusted, 'remove', '*', '-c')
            cli_rejection(untrusted, 'install', '--requires=cargo/1.0', '-r', 'east')
            cli_success(untrusted, 'remote', 'update', 'west', '--secure')
            cli_rejection(untrusted, 'install', '--requires=cargo/1.0', '-r', 'west')
            # The opt-out can also be chosen when the remote is added.
            cli_success(untrusted, 'remote', 'add', 'west', repos[0][1], '--force', '--insecure')
            assert_remote_install(untrusted, 'cargo/1.0', 'TLS artifact', '-r', 'west')
