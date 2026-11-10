# feature: F11
"""Dependency acquisition, build selection, integration and planning acceptance."""
import json
from pathlib import Path

from _helpers import read_json, write_file
from F01_helpers import cli_success, cli_rejection, named_node
from F02_helpers import recipe_client, recipe_file
from F03_helpers import recipe_repository, attach_repositories
from F04_helpers import publish_remote_package, assert_remote_install
from F05_helpers import dependency_graph, dependency_recipe
from F08_helpers import environment_dependency, environment_consumer, activated_observation
from F07_helpers import cmake_command
from F11_helpers import (installation_package, installation_graph, installed_artifact,
                         installation_chain, build_plan, plan_work, assert_chain_plan,
                         reported_missing_configuration, error_diagnostic)


def test_install_local_remote_and_missing_configuration(tmp_path):
    client = recipe_client(tmp_path / 'client')
    with recipe_repository(tmp_path / 'server', client.env) as url:
        attach_repositories(client, [('origin', url)], publish=True)
        reference = publish_remote_package(client, tmp_path / 'producer', 'origin', marker='remote material')
        local = assert_remote_install(client, reference, 'remote material', '-nr')
        assert local['binary'] == 'Cache'
        cli_success(client, 'remove', reference, '-c')
        remote = assert_remote_install(client, reference, 'remote material', '-r', 'origin')
        assert remote['binary'] == 'Download'
    installation_package(client, tmp_path / 'configured')
    report = installation_graph(client, 'item/1.0', '-s', 'build_type=Debug')
    node = named_node(report, 'item')
    assert node['binary'] == 'Missing'
    assert node['settings']['build_type'] == 'Debug'
    failure = cli_rejection(client, 'install', '--requires=item/1.0', '-nr', '-s', 'build_type=Debug')
    assert 'item/1.0' in error_diagnostic(failure), failure
    assert reported_missing_configuration(failure, 'item/1.0')['build_type'] == 'Debug'


def test_build_policies_select_and_materialize(tmp_path):
    # Independent arms differ only in the policy; dependency identity is stable.
    policies = [(('--build=never',), ('Cache', 'Cache')),
                # Dependency-triggered rebuilding applies only when a dependency is being built.
                (('--build=missing', '--build=cascade'), ('Cache', 'Cache')),
                (('--build=base/*',), ('Build', 'Cache')),
                (('--build=missing:base/*',), ('Cache', 'Cache')),
                (('--build=base/*', '--build=cascade'), ('Build', 'Build'))]
    for index, (policy, states) in enumerate(policies):
        root = tmp_path / str(index)
        client = recipe_client(root)
        installation_chain(client, root, create=True)
        client.env['F11_TOKEN'] = 'rebuilt'
        report = installation_graph(client, 'top/1.0', *policy)
        assert tuple(named_node(report, n)['binary'] for n in ('base', 'top')) == states
        installed = installation_graph(client, 'top/1.0', *policy, install=True)
        for name, state in zip(('base', 'top'), states):
            assert installed_artifact(installed, name)['token'] == ('rebuilt' if state == 'Build' else 'initial')
    missing_client = recipe_client(tmp_path / 'forbidden')
    installation_package(missing_client, tmp_path / 'forbidden-recipe')
    cli_rejection(missing_client, 'install', '--requires=item/1.0', '-nr', '--build=never')
    for index, policy in enumerate((('--build=missing',), ('--build=missing:item/*',))):
        client = recipe_client(tmp_path / ('missing' + str(index)))
        installation_package(client, tmp_path / ('recipe' + str(index)))
        result = installation_graph(client, 'item/1.0', *policy, install=True)
        assert installed_artifact(result)['token'] == 'initial'
        dependency_recipe(client, tmp_path / ('other' + str(index)), 'other')
        if index:
            assert named_node(installation_graph(client, 'other/1.0', *policy), 'other')['binary'] == 'Missing'
            cli_rejection(client, 'install', '--requires=other/1.0', '-nr', *policy)


def test_policy_exclusions_and_incompatible_selections(tmp_path):
    # The exclusion names only one package of the graph; the other remains forced.
    for index, flags in enumerate((('--build=*', '--build=!base/*'), ('--build=!base/*', '--build=*'))):
        root = tmp_path / str(index)
        client = recipe_client(root)
        installation_chain(client, root, create=True)
        client.env['F11_TOKEN'] = 'rebuilt'
        result = installation_graph(client, 'top/1.0', *flags, install=True)
        assert named_node(result, 'base')['binary'] == 'Cache'
        assert installed_artifact(result, 'base')['token'] == 'initial'
        assert named_node(result, 'top')['binary'] == 'Build'
        assert installed_artifact(result, 'top')['token'] == 'rebuilt'
    # top/1.0 is installable here, so each refusal comes from the policy combination, in either order.
    for positive in ('*', 'missing', 'cascade'):
        cli_rejection(client, 'install', '--requires=top/1.0', '-nr', '--build=never', '--build=' + positive)
    cli_rejection(client, 'install', '--requires=top/1.0', '-nr', '--build=*', '--build=never')


def test_recipe_build_permissions_and_prohibitions(tmp_path):
    for policy, caller, success in [('missing', (), True), ('missing', ('--build=never',), False),
                                     ('never', ('--build=*',), False), ('always', ('--build=missing',), False)]:
        root = tmp_path / (policy + str(bool(caller)))
        client = recipe_client(root)
        installation_package(client, root / 'recipe', body='    build_policy = %r\n' % policy)
        if success:
            assert installed_artifact(installation_graph(client, 'item/1.0', *caller, install=True))['token'] == 'initial'
            client.env['F11_TOKEN'] = 'should not rebuild'
            reused = installation_graph(client, 'item/1.0', install=True)
            assert named_node(reused, 'item')['binary'] == 'Cache'
            assert installed_artifact(reused)['token'] == 'initial'
        else:
            cli_rejection(client, 'install', '--requires=item/1.0', '-nr', *caller)
    # Prohibition is a source-build restriction, not a ban on consuming prebuilt data.
    client = recipe_client(tmp_path / 'prebuilt')
    source = recipe_file(tmp_path / 'prebuilt-source', '    build_policy = "never"\n    def package(self):\n        import os\n        from velmora.tools.files import save\n        save(self, os.path.join(self.package_folder, "value.txt"), "prebuilt material")\n', name='item', version='1.0')
    cli_success(client, 'export-pkg', source.parent, '-nr')
    result = installation_graph(client, 'item/1.0', '--build=*', install=True)
    assert (Path(named_node(result, 'item')['package_folder']) / 'value.txt').read_text() == 'prebuilt material'


def test_opt_in_declared_compatible_build(tmp_path):
    client = recipe_client(tmp_path)
    body = '''    def validate(self):
        from velmora.errors import VelmoraInvalidConfiguration
        if self.settings.build_type != "Release":
            raise VelmoraInvalidConfiguration("release configuration required")
    def compatibility(self):
        return [{"settings": [("build_type", "Release")]}]
'''
    installation_package(client, tmp_path / 'recipe', body=body)
    for flags in ((), ('--build=missing',)):
        cli_rejection(client, 'install', '--requires=item/1.0', '-nr', '-s', 'build_type=Debug', *flags, status=6)
    result = installation_graph(client, 'item/1.0', '-s', 'build_type=Debug', '--build=compatible:item/*', install=True)
    assert installed_artifact(result)['configuration'] == 'Release'
    # A compatibility candidate must itself validate, rather than bypassing validation.
    installation_package(client, tmp_path / 'disallowed', name='blocked', body=body.replace('"Release")]}', '"RelWithDebInfo")]}'))
    cli_rejection(client, 'install', '--requires=blocked/1.0', '-nr', '-s', 'build_type=Debug', '--build=compatible:blocked/*', status=6)


def test_install_build_consumes_prerequisites_and_reports_failures(tmp_path):
    client = recipe_client(tmp_path)
    installation_chain(client, tmp_path, create=False)
    result = installation_graph(client, 'top/1.0', '--build=missing', install=True)
    assert installed_artifact(result, 'top')['dependencies'] == {
        'base': dict(token='initial', configuration='Release', dependencies={})}
    dependency_recipe(client, tmp_path / 'unresolved', 'unresolved', body='    requires = "unavailable/1.0"\n')
    report = dependency_graph(client, None, '--requires=unresolved/1.0', rejected=True)
    assert report['graph']['error']['type'] == 'missing'
    assert report['graph']['error']['require']['ref'].partition('#')[0] == 'unavailable/1.0'
    unresolved = cli_rejection(client, 'install', '--requires=unresolved/1.0', '-nr', '--build=missing')
    assert 'unavailable/1.0' in error_diagnostic(unresolved), unresolved
    dependency_recipe(client, tmp_path / 'broken', 'broken', body='    def build(self):\n        raise RuntimeError("caller-build-cause")\n')
    failure = cli_rejection(client, 'install', '--requires=broken/1.0', '-nr', '--build=missing')
    assert 'broken/1.0' in error_diagnostic(failure), failure
    assert 'caller-build-cause' in failure.text('stderr')


def test_install_generates_usable_integration_and_environments(tmp_path):
    client = recipe_client(tmp_path)
    environment_dependency(client, tmp_path / 'runtime', 'runtime', 37)
    environment_dependency(client, tmp_path / 'tool', 'tool', 61)
    source = environment_consumer(tmp_path / 'consumer', declarations='    requires = "runtime/1.0"\n    tool_requires = "tool/1.0"\n', body='''    def layout(self):
        self.folders.build = "build-zone"
        self.folders.generators = "integration"
    def generate(self):
        import os
        from velmora.tools.files import save
        save(self, os.path.join(self.generators_folder, "dependency-path.txt"),
             self.dependencies["runtime"].package_folder)
''')
    output = tmp_path / 'output'
    cli_success(client, 'install', source.parent, '-nr', '-of', output, '-g', 'CMakeDeps')
    generated = output / 'integration'
    assert (generated / 'runtime-config.cmake').is_file()
    # Load the actual generated build-system inputs with the native tool.
    cmake = write_file(tmp_path / 'native/CMakeLists.txt', '''cmake_minimum_required(VERSION 3.15)
project(Consumer NONE)
find_package(runtime CONFIG REQUIRED)
if(NOT TARGET runtime::runtime)
  message(FATAL_ERROR "Dependency target missing")
endif()
''')
    cmake_command(client, tmp_path, '-S', str(cmake.parent), '-B', str(tmp_path / 'native-build'),
                  '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_PREFIX_PATH=' + str(generated))
    run_observation = activated_observation(client, generated, 'velmorarun.sh', commands=('f08-runtime',))
    assert run_observation['commands'] == {'f08-runtime': '37'}
    build_observation = activated_observation(client, generated, commands=('f08-tool',))
    assert build_observation['commands'] == {'f08-tool': '61'}
    assert run_observation['env']['F08_RUN_RUNTIME'] == 'run-runtime'
    assert build_observation['env']['F08_BUILD_TOOL'] == 'build-tool'


def test_prebuilt_private_binary_skip_and_rebuild_requirement(tmp_path):
    for rebuild in (False, True):
        root = tmp_path / str(rebuild)
        client = recipe_client(root)
        installation_package(client, root / 'private', 'private', create=True)
        installation_package(client, root / 'top', 'top', create=True, body='''    package_type = "static-library"
    def requirements(self):
        self.requires("private/1.0", headers=False, libs=False, run=False, visible=False)
''')
        cli_success(client, 'remove', 'private/1.0:*', '-c')
        if rebuild:
            report = installation_graph(client, 'top/1.0', '--build=top/*')
            assert named_node(report, 'private')['binary'] == 'Missing'
            cli_rejection(client, 'install', '--requires=top/1.0', '-nr', '--build=top/*')
        else:
            report = installation_graph(client, 'top/1.0', install=True)
            assert named_node(report, 'private')['binary'] == 'Skip'
            assert installed_artifact(report, 'top')['dependencies']['private']['token'] == 'initial'


def test_graph_binary_states_without_building(tmp_path):
    client = recipe_client(tmp_path / 'client')
    installation_package(client, tmp_path / 'local', create=True)
    assert named_node(installation_graph(client), 'item')['binary'] == 'Cache'
    cli_success(client, 'remove', 'item/1.0:*', '-c')
    for flags, expected in [((), 'Missing'), (('--build=missing',), 'Build')]:
        report = installation_graph(client, 'item/1.0', *flags)
        assert named_node(report, 'item')['binary'] == expected
        # Inspecting a selected build must not make that binary available.
        assert named_node(installation_graph(client), 'item')['binary'] == 'Missing'
        listing = cli_success(client, 'list', 'item/1.0:*', '--format=json').json('stdout')
        revisions = listing['Local Cache']['item/1.0']['revisions']
        assert revisions
        assert all(revision['packages'] == {} for revision in revisions.values()), listing
    installation_package(client, tmp_path / 'invalid', name='invalid', body='    def validate(self):\n        from velmora.errors import VelmoraInvalidConfiguration\n        raise VelmoraInvalidConfiguration("unsupported configuration")\n')
    assert named_node(installation_graph(client, 'invalid/1.0'), 'invalid')['binary'] == 'Invalid'
    with recipe_repository(tmp_path / 'server', client.env) as url:
        attach_repositories(client, [('origin', url)], publish=True)
        publish_remote_package(client, tmp_path / 'remote', 'origin')
        cli_success(client, 'remove', 'cargo/1.0:*', '-c')
        assert named_node(installation_graph(client, 'cargo/1.0', '-r', 'origin', local=False), 'cargo')['binary'] == 'Download'
        assert named_node(installation_graph(client, 'cargo/1.0'), 'cargo')['binary'] == 'Missing'


def test_build_order_grouping_prerequisites_and_reduction(tmp_path):
    client = recipe_client(tmp_path)
    installation_chain(client, tmp_path, create=False)
    cli_success(client, 'install', '--requires=base/1.0', '-nr', '--build=missing')
    for grouping in ('recipe', 'configuration'):
        full = build_plan(client, grouping=grouping)
        assert full['order_by'] == grouping
        assert full['reduced'] is False
        rows = assert_chain_plan(full, {'base', 'top'})
        assert {ref.split('/')[0]: package['binary'] for _, ref, package in rows} == {'base': 'Cache', 'top': 'Build'}
        reduced = build_plan(client, grouping=grouping, reduced=True)
        assert reduced['reduced'] is True
        assert_chain_plan(reduced, {'top'})
    # A reduced plan keeps a prerequisite that is built below an available intermediate binary.
    cli_success(client, 'install', '--requires=top/1.0', '-nr', '--build=missing')
    installation_package(client, tmp_path / 'apex', 'apex', body='''    def requirements(self):
        self.requires("top/1.0", package_id_mode="unrelated_mode")
''')
    for grouping in ('recipe', 'configuration'):
        reduced = build_plan(client, '--build=base/*', grouping=grouping, reduced=True, reference='apex/1.0')
        rows = assert_chain_plan(reduced, {'base', 'apex'})
        levels = {ref.split('/')[0]: level for level, ref, _ in rows}
        assert levels['base'] < levels['apex'], reduced
        key = 'ref' if grouping == 'recipe' else 'pref'
        entries = {entry['ref'].split('/')[0]: entry for group in reduced['order'] for entry in group}
        assert entries['base'][key] in entries['apex']['depends'], reduced


def test_merge_configuration_plans_and_reject_incompatible_inputs(tmp_path):
    client = recipe_client(tmp_path)
    installation_chain(client, tmp_path, create=False)
    for grouping in ('recipe', 'configuration'):
        files = []
        identities = set()
        for flavor in ('Debug', 'Release'):
            plan = build_plan(client, '-s', 'build_type=' + flavor, grouping=grouping)
            rows = assert_chain_plan(plan, {'base', 'top'})
            assert all(package['info']['settings']['build_type'] == flavor for _, _, package in rows)
            identities.update((ref, package['package_id']) for _, ref, package in plan_work(plan))
            files.append(write_file(tmp_path / (grouping + flavor + '.json'), json.dumps(plan)))
        merged = cli_success(client, 'graph', 'build-order-merge', '--file', files[0], '--file', files[1], '--format=json').json('stdout')
        rows = assert_chain_plan(merged, {'base', 'top'})
        assert {(ref, package['package_id']) for _, ref, package in rows} == identities
    # Configurations with different prerequisites: the merged entry keeps those of each input.
    installation_package(client, tmp_path / 'extra', 'extra')
    installation_package(client, tmp_path / 'conditional', 'conditional', body='''    def requirements(self):
        if self.settings.build_type == "Debug":
            self.requires("extra/1.0")
''')
    release, debug = (write_file(tmp_path / ('conditional' + flavor + '.json'), json.dumps(
        build_plan(client, '-s', 'build_type=' + flavor, reference='conditional/1.0'))) for flavor in ('Release', 'Debug'))
    for first, second in ((release, debug), (debug, release)):
        merged = cli_success(client, 'graph', 'build-order-merge', '--file', first, '--file', second, '--format=json').json('stdout')
        entries = {entry['ref'].split('/')[0]: (level, entry) for level, group in enumerate(merged['order']) for entry in group}
        assert entries['extra'][0] < entries['conditional'][0], merged
        assert entries['extra'][1]['ref'] in entries['conditional'][1]['depends'], merged
    cli_rejection(client, 'graph', 'build-order-merge', '--file', tmp_path / 'recipeDebug.json', '--file', tmp_path / 'configurationDebug.json')
    reduced = write_file(tmp_path / 'reduced.json', json.dumps(build_plan(client, reduced=True)))
    for first, second in [(reduced, tmp_path / 'recipeDebug.json'), (tmp_path / 'recipeDebug.json', reduced)]:
        cli_rejection(client, 'graph', 'build-order-merge', '--file', first, '--file', second)
