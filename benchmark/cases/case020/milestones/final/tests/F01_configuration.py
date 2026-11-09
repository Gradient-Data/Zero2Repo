# feature: F01
"""Acceptance for FP-01; each function retains its planned measurement identity."""
from pathlib import Path
import platform

from _helpers import Client, environment, read_bytes, run, write_file
from F01_helpers import (configuration_client, cli_success, cli_rejection,
                         configuration_bundle, install_bundle, profile_document,
                         profile_sections, graph_document, named_node, settings_profile,
                         configuration_recipe, export_context_packages, configuration_http,
                         git_configuration_commit, graph_context_systems, zip_configuration)


def test_home_persistence_and_isolation(tmp_path):
    # F01.T01 / FP-01.01
    clients = [configuration_client(tmp_path / name) for name in ('first', 'second')]
    for client, system, jobs in zip(clients, ('Linux', 'Windows'), (3, 7)):
        install_bundle(client, Path(client.cwd) / 'supplied', {
            'global.conf': f'tools.build:jobs={jobs}\n',
            'profiles/saved': settings_profile(system),
            'profiles/default': settings_profile(system)})
        configuration_recipe(client.cwd, extra='    def configure(self):\n'
                             '        self.description = str(self.conf.get("tools.build:jobs"))\n')
    for client, system, jobs in zip(clients, ('Linux', 'Windows'), (3, 7)):
        fresh = configuration_client(client.cwd)
        assert Path(cli_success(fresh, 'config', 'home').text('stdout').strip()) == Path(fresh.env['VELMORA_HOME'])
        assert cli_success(fresh, 'config', 'show', 'tools.build:jobs', '--format=json').json('stdout') == {'tools.build:jobs': jobs}
        assert 'saved' in cli_success(fresh, 'profile', 'list', '--format=json').json('stdout')
        assert profile_document(fresh, '-pr', 'saved')['host']['settings']['os'] == system
        node = named_node(graph_document(fresh, '.', '-pr', 'saved'), None)
        assert node['settings']['os'] == system
        assert node['description'] == str(jobs)


def test_configuration_acquisition_sources(tmp_path):
    # F01.T02 / FP-01.02: each transport must deliver usable content.
    for kind, system in zip(('directory', 'archive', 'http', 'git'),
                            ('Linux', 'Windows', 'FreeBSD', 'Macos')):
        client = configuration_client(tmp_path / kind)
        source = configuration_bundle(tmp_path / ('source-' + kind), {
            'profiles/default': settings_profile(system),
            'global.conf': 'tools.build:jobs=5\n',
            'notes/organization.txt': f'configuration from {kind}\n'})
        if kind in ('archive', 'http'):
            archive = zip_configuration(source, tmp_path / (kind + '.zip'))
            if kind == 'http':
                with configuration_http(tmp_path) as url:
                    cli_success(client, 'config', 'install', url + '/' + archive.name)
            else:
                cli_success(client, 'config', 'install', archive)
        elif kind == 'git':
            git_configuration_commit(source, client.env)
            cli_success(client, 'config', 'install', source, '--type=git')
        else:
            cli_success(client, 'config', 'install', source)
        assert profile_document(client)['host']['settings']['os'] == system
        assert cli_success(client, 'config', 'show', 'tools.build:jobs', '--format=json').json('stdout') == {'tools.build:jobs': 5}
        assert read_bytes(Path(client.env['VELMORA_HOME']) / 'notes/organization.txt') == f'configuration from {kind}\n'.encode()


def test_configuration_selection_exclusions_and_failure(tmp_path):
    # F01.T03 / FP-01.02
    client = configuration_client(tmp_path / 'client')
    source = configuration_bundle(tmp_path / 'distribution', {
        'selected/profiles/team': settings_profile('FreeBSD'),
        'selected/discard.txt': 'excluded payload',
        'selected/retain.txt': 'selected payload',
        'selected/scratch.tmp': 'excluded by pattern',
        'selected/.velmoraignore': 'discard.txt\n*.tmp\n',
        'outside.txt': 'unselected payload'})
    cli_success(client, 'config', 'install', source, '-sf', 'selected', '-tf', 'department')
    home = Path(cli_success(client, 'config', 'home').text('stdout').strip())
    assert read_bytes(home / 'department/retain.txt') == b'selected payload'
    assert read_bytes(home / 'department/profiles/team') == settings_profile('FreeBSD').encode()
    assert not (home / 'department/discard.txt').exists()
    assert not (home / 'department/scratch.tmp').exists()
    assert not (home / 'department/outside.txt').exists()
    assert not (home / 'retain.txt').exists()
    # Selection also applies to a supplied archive, not only to a directory.
    archive = zip_configuration(source, tmp_path / 'distribution.zip')
    cli_success(client, 'config', 'install', archive, '-sf', 'selected', '-tf', 'packed')
    assert read_bytes(home / 'packed/retain.txt') == b'selected payload'
    for name in ('packed/discard.txt', 'packed/scratch.tmp', 'packed/outside.txt', 'outside.txt'):
        assert not (home / name).exists()
    # Every source kind reports an unavailable source.
    cli_rejection(client, 'config', 'install', tmp_path / 'unavailable', '--type=dir')
    cli_rejection(client, 'config', 'install', tmp_path / 'unavailable', '--type=git')
    with configuration_http(tmp_path) as url:
        cli_rejection(client, 'config', 'install', url + '/unavailable.zip')
    assert read_bytes(home / 'department/retain.txt') == b'selected payload'


def test_profile_listing_location_and_context_inspection(tmp_path):
    # F01.T04 / FP-01.03
    client = configuration_client(tmp_path)
    host = settings_profile('Linux') + '[options]\n*:shared=True\n[conf]\ntools.build:jobs=2\n[buildenv]\nTEAM=host-team\n[runenv]\nRUNTIME=host-run\n'
    build = settings_profile('Windows', 'Debug') + '[options]\n*:shared=False\n[conf]\ntools.build:jobs=6\n[buildenv]\nTEAM=build-team\n[runenv]\nRUNTIME=build-run\n'
    install_bundle(client, tmp_path / 'supplied', {'profiles/consumer': host, 'profiles/tools': build})
    assert set(cli_success(client, 'profile', 'list', '--format=json').json('stdout')) == {'consumer', 'tools'}
    path = Path(cli_success(client, 'profile', 'path', 'consumer').text('stdout').strip())
    assert read_bytes(path) == host.encode()
    args = ('-pr:h', 'consumer', '-pr:b', 'tools')
    shown = profile_document(client, *args)
    for context, system, mode, shared, jobs, team, runtime in (
            ('host', 'Linux', 'Release', 'True', 2, 'host-team', 'host-run'),
            ('build', 'Windows', 'Debug', 'False', 6, 'build-team', 'build-run')):
        section = shown[context]
        assert section['settings']['os'] == system
        assert section['settings']['build_type'] == mode
        assert section['options']['*:shared'] == shared
        assert section['conf']['tools.build:jobs'] == jobs
        assert section['build_env'].splitlines() == ['TEAM=' + team]
        text = profile_sections(client, context, *args)
        assert text['runenv']['RUNTIME'] == runtime
    cli_rejection(client, 'profile', 'path', 'not-stored')
    cli_rejection(client, 'profile', 'show', '-pr:h', 'not-stored', '-pr:b', 'tools')


def test_profile_inclusion_environment_and_override_order(tmp_path):
    # F01.T05 / FP-01.04
    client = configuration_client(tmp_path, updates={'F01_TARGET_OS': 'FreeBSD'})
    install_bundle(client, tmp_path / 'supplied', {
        # arch reaches derived only through two levels; jobs only through its second include.
        'profiles/platform': '[settings]\narch=x86_64\n',
        'profiles/tuning': '[conf]\ntools.build:jobs=4\n',
        'profiles/base': 'include(platform)\n[settings]\nos=Linux\nbuild_type=Debug\n[options]\n*:flavor=base\n',
        'profiles/derived': 'include(base)\ninclude(tuning)\n[settings]\nos={{os.getenv("F01_TARGET_OS")}}\n[options]\n*:flavor=derived\n',
        'profiles/later': '[settings]\nbuild_type=Release\n[options]\n*:flavor=later\n',
        'profiles/default': settings_profile()})
    configuration_recipe(tmp_path, extra='    options = {"flavor": ["base", "derived", "later", "cli"]}\n'
                         '    default_options = {"flavor": "base"}\n')
    for profiles, mode, flavor in ((('derived',), 'Debug', 'derived'),
                                   (('derived', 'later'), 'Release', 'later'),
                                   (('later', 'derived'), 'Debug', 'derived')):
        args = tuple(part for profile in profiles for part in ('-pr:h', profile))
        shown = profile_document(client, *args)['host']
        assert shown['settings'] == {'os': 'FreeBSD', 'arch': 'x86_64', 'build_type': mode}
        assert shown['options']['*:flavor'] == flavor
        assert shown['conf']['tools.build:jobs'] == 4
        node = named_node(graph_document(client, '.', *args), None)
        assert node['settings'] == shown['settings']
        assert node['options']['flavor'] == flavor
    changed = Client(client.command, client.cwd, environment(client.env, updates={'F01_TARGET_OS': 'Macos'}))
    assert named_node(graph_document(changed, '.', '-pr:h', 'derived'), None)['settings']['os'] == 'Macos'
    node = named_node(graph_document(client, '.', '-pr:h', 'derived', '-pr:h', 'later',
                                    '-s', 'os=Macos', '-o', '*:flavor=cli'), None)
    assert node['settings']['os'] == 'Macos'
    assert node['settings']['arch'] == 'x86_64'
    assert node['options']['flavor'] == 'cli'


def test_host_build_and_all_context_assignments(tmp_path):
    # F01.T06 / FP-01.05
    client = configuration_client(tmp_path)
    install_bundle(client, tmp_path / 'supplied', {'profiles/default': settings_profile()})
    export_context_packages(client)
    for args, host_mode, build_mode in (((), 'Release', 'Release'),
                                        (('-s', 'build_type=Debug'), 'Debug', 'Release'),
                                        (('-s:b', 'build_type=Debug'), 'Release', 'Debug'),
                                        (('-s:a', 'build_type=Debug'), 'Debug', 'Debug')):
        report = graph_document(client, '.', *args)
        assert named_node(report, 'hostpkg', 'host')['settings']['build_type'] == host_mode
        assert named_node(report, 'toolpkg', 'build')['settings']['build_type'] == build_mode
    # The same context rule holds for option and configuration assignments.
    for args, in_host, in_build in ((('-o', '*:flavor=chosen', '-c', 'tools.build:jobs=3'), True, False),
                                    (('-o:b', '*:flavor=chosen', '-c:b', 'tools.build:jobs=3'), False, True),
                                    (('-o:a', '*:flavor=chosen', '-c:a', 'tools.build:jobs=3'), True, True)):
        shown = profile_document(client, *args)
        for context, applies in (('host', in_host), ('build', in_build)):
            assert shown[context]['options'].get('*:flavor') == ('chosen' if applies else None)
            assert shown[context]['conf'].get('tools.build:jobs') == (3 if applies else None)


def test_package_pattern_setting_precedence(tmp_path):
    # F01.T07 / FP-01.06
    client = configuration_client(tmp_path)
    install_bundle(client, tmp_path / 'supplied', {
        'profiles/default': settings_profile(),
        'profiles/scoped': settings_profile() + 'codec*:build_type=Debug\n'})
    for name in ('codec', 'codec_extra', 'unrelated'):
        configuration_recipe(tmp_path / name, name=name)
        cli_success(client, 'export', name)
    configuration_recipe(tmp_path, extra='    requires = "codec/1.0", "codec_extra/1.0", "unrelated/1.0"\n')
    for assignments, expected in ((('codec*:build_type=Debug',), ('Debug', 'Debug', 'Release')),
                                   (('codec*:build_type=Debug', 'codec/*:build_type=RelWithDebInfo'),
                                    ('RelWithDebInfo', 'Debug', 'Release')),
                                   (('codec/*:build_type=RelWithDebInfo', 'codec*:build_type=Debug'),
                                    ('Debug', 'Debug', 'Release'))):
        args = tuple(part for value in assignments for part in ('-s', value))
        report = graph_document(client, '.', *args, '-s', 'build_type=Release')
        for name, mode in zip(('codec', 'codec_extra', 'unrelated'), expected):
            assert named_node(report, name)['settings']['build_type'] == mode
    # A pattern stored in a profile follows the same rule as one on the command line.
    report = graph_document(client, '.', '-pr:h', 'scoped')
    for name, mode in zip(('codec', 'codec_extra', 'unrelated'), ('Debug', 'Debug', 'Release')):
        assert named_node(report, name)['settings']['build_type'] == mode


def test_setting_domains_extensions_and_required_values(tmp_path):
    # F01.T08 / FP-01.07
    client = configuration_client(tmp_path)
    install_bundle(client, tmp_path / 'supplied', {
        'profiles/default': settings_profile(),
        'settings_user.yml': 'deployment_tier: ["staging", "production"]\n'})
    configuration_recipe(tmp_path, settings=('os', 'arch', 'build_type', 'deployment_tier'))
    report = graph_document(client, '.', '-s', 'deployment_tier=staging')
    assert named_node(report, None)['settings'] == {
        'os': 'Linux', 'arch': 'x86_64', 'build_type': 'Release', 'deployment_tier': 'staging'}
    report = graph_document(client, '.', '-s', 'deployment_tier=production')
    assert named_node(report, None)['settings']['deployment_tier'] == 'production'
    assert named_node(report, None)['info_invalid'] is None
    cli_success(client, 'install', '.', '-nr', '-s', 'deployment_tier=production')
    for args in (('-s', 'unknown_axis=on', '-s', 'deployment_tier=staging'),
                 ('-s', 'deployment_tier=invalid'),
                 ('-s', 'os=InvalidPlatform', '-s', 'deployment_tier=staging')):
        cli_rejection(client, 'graph', 'info', '.', '-nr', '--format=json', *args)
    missing = named_node(graph_document(client), None)
    assert isinstance(missing['info_invalid'], str) and missing['info_invalid']
    cli_rejection(client, 'install', '.', '-nr', status=6)


def test_profile_detection_and_overwrite_protection(tmp_path):
    # F01.T09 / FP-01.08
    client = configuration_client(tmp_path, updates={'CC': 'gcc', 'CXX': 'g++'})
    cli_success(client, 'profile', 'detect', '--name', 'detected')
    args = ('-pr:h', 'detected', '-pr:b', 'detected')
    detected = profile_document(client, *args)['host']['settings']
    assert detected['os'] == platform.system()
    assert detected['arch'] == platform.machine()
    # The acceptance image supplies the real GNU compiler; compare its public version.
    compiler = run(('gcc', '-dumpfullversion'), cwd=tmp_path, env=client.env)
    assert compiler.returncode == 0, compiler
    assert detected['compiler'] == 'gcc'
    available_version = compiler.text('stdout').strip().split('.')
    reported_version = detected['compiler.version'].split('.')
    assert reported_version and reported_version == available_version[:len(reported_version)]
    install_bundle(client, tmp_path / 'supplied', {'profiles/detected': settings_profile('FreeBSD', 'Debug')})
    cli_rejection(client, 'profile', 'detect', '--name', 'detected')
    assert profile_document(client, *args)['host']['settings']['os'] == 'FreeBSD'
    cli_success(client, 'profile', 'detect', '--name', 'detected', '--force')
    restored = profile_document(client, *args)['host']['settings']
    for key in ('os', 'arch', 'compiler'):
        assert restored[key] == detected[key]
    restored_version = restored['compiler.version'].split('.')
    assert restored_version and restored_version == available_version[:len(restored_version)]
    # A real environment with no compiler on PATH must not reuse a compiler template.
    no_compiler_path = tmp_path / 'no-executables'
    no_compiler_path.mkdir()
    bare = configuration_client(tmp_path / 'compiler-free', updates={
        'PATH': str(no_compiler_path), 'CC': '', 'CXX': ''})
    cli_success(bare, 'profile', 'detect', '--name', 'detected')
    without = profile_document(bare, *args)['host']['settings']
    assert without['os'] == platform.system()
    assert without['arch'] == platform.machine()
    assert 'compiler' not in without


def test_required_client_version_in_configuration_and_recipe(tmp_path):
    # F01.T10 / FP-01.09
    client = configuration_client(tmp_path)
    install_bundle(client, tmp_path / 'supplied', {'profiles/default': settings_profile(),
                   'global.conf': 'core:required_velmora_version=>=0\n'})
    assert cli_success(client, 'config', 'show', 'core:required_velmora_version', '--format=json').json('stdout') == {'core:required_velmora_version': '>=0'}
    recipe = configuration_recipe(tmp_path)
    write_file(recipe, 'required_velmora_version = ">=0"\n' + read_bytes(recipe).decode())
    assert named_node(graph_document(client), None)['settings']['os'] == 'Linux'
    write_file(recipe, read_bytes(recipe).decode().replace('>=0', '<0'))
    cli_rejection(client, 'graph', 'info', '.', '-nr', '--format=json')
    # An executing version can fall outside the range on either side.
    write_file(recipe, read_bytes(recipe).decode().replace('<0', '>=100000'))
    cli_rejection(client, 'graph', 'info', '.', '-nr', '--format=json')
    below = configuration_client(tmp_path / 'below-range')
    cli_rejection(below, 'config', 'install', configuration_bundle(
        tmp_path / 'below-range-source', {'global.conf': 'core:required_velmora_version=>=100000\n'}))
    recipe = configuration_recipe(tmp_path)
    write_file(recipe, 'required_velmora_version = ">=0"\n' + read_bytes(recipe).decode())
    source = configuration_bundle(tmp_path / 'incompatible', {'global.conf': 'core:required_velmora_version=<0\n'})
    cli_rejection(client, 'config', 'install', source)
    write_file(tmp_path / 'home' / 'global.conf', 'core:required_velmora_version=<0\n')
    cli_rejection(client, 'config', 'home', label='Error in Velmora initialization:')
    cli_rejection(client, 'graph', 'info', '.', '-nr', '--format=json',
                  label='Error in Velmora initialization:')


def test_context_default_selection_and_missing_defaults(tmp_path):
    # F01.T11 / FP-01.10
    client = configuration_client(tmp_path)
    profiles = {'profiles/' + name: settings_profile(system) for name, system in (
        ('default', 'Linux'), ('stored-host', 'Windows'), ('stored-build', 'FreeBSD'),
        ('env-host', 'Macos'), ('env-build', 'Android'))}
    install_bundle(client, tmp_path / 'supplied', profiles)
    export_context_packages(client)
    assert graph_context_systems(client) == ('Linux', 'Linux')
    install_bundle(client, tmp_path / 'selection', {'global.conf':
        'core:default_profile=stored-host\ncore:default_build_profile=stored-build\n'})
    assert graph_context_systems(client) == ('Windows', 'FreeBSD')
    for updates, expected in (({'VELMORA_DEFAULT_PROFILE': 'env-host'}, ('Macos', 'FreeBSD')),
                              ({'VELMORA_DEFAULT_BUILD_PROFILE': 'env-build'}, ('Windows', 'Android')),
                              ({'VELMORA_DEFAULT_PROFILE': 'env-host', 'VELMORA_DEFAULT_BUILD_PROFILE': 'env-build'},
                               ('Macos', 'Android'))):
        bound = Client(client.command, client.cwd, environment(client.env, updates=updates))
        assert graph_context_systems(bound) == expected
    for key in ('VELMORA_DEFAULT_PROFILE', 'VELMORA_DEFAULT_BUILD_PROFILE'):
        bound = Client(client.command, client.cwd, environment(client.env, updates={key: 'absent-default'}))
        cli_rejection(bound, 'graph', 'info', '.', '-nr', '--format=json')
    empty = configuration_client(tmp_path / 'empty')
    configuration_recipe(empty.cwd)
    cli_rejection(empty, 'graph', 'info', '.', '-nr', '--format=json')
    assert cli_success(empty, 'profile', 'list', '--format=json').json('stdout') == []
