# feature: F17
"""Workspace membership, orchestration and usable combined integration."""
from pathlib import Path

from _helpers import read_json, write_file
from F01_helpers import cli_rejection, cli_success, graph_document, named_node
from F02_helpers import recipe_client, recipe_file
from F07_helpers import CMAKE_SETTINGS, cmake_command, native_command
from F09_helpers import capture_lock, lock_records
from F12_helpers import selection, selected_artifacts
from F16_helpers import (editable_mappings, working_library, update_working_library,
                         build_working_library, native_editable_consumer)
from F17_helpers import (workspace_client, workspace_members, workspace_paths,
                         workspace_add_members, text_development_package)


def test_workspace_membership_persists_paths_and_output_areas(tmp_path):
    # F17.T01
    client = recipe_client(tmp_path)
    b = recipe_file(tmp_path / 'elsewhere/beta', '', name='beta', version='3.4').parent
    # Adding a member does not define a workspace that does not exist.
    cli_rejection(client, 'workspace', 'add', b, '-nr')
    cli_rejection(client, 'workspace', 'root')
    cli_rejection(client, 'workspace', 'info', '--format=json')
    root = tmp_path / 'development'
    cli_success(client, 'workspace', 'init', root)
    inside = workspace_client(client, root / 'nested/deeper')
    assert cli_success(inside, 'workspace', 'root').text('stdout').strip() == str(root)
    a = recipe_file(root / 'libraries/alpha', '', name='alpha', version='1.2').parent
    output = root / 'outputs/alpha'
    cli_success(inside, 'workspace', 'add', a, '-of', output, '-nr')
    cli_success(inside, 'workspace', 'add', b, '-nr')
    members = workspace_paths(inside)
    assert set(members) == {str(a), str(b)}
    assert members[str(a)]['ref'] == 'alpha/1.2'
    assert members[str(b)]['ref'] == 'beta/3.4'
    assert (root / members[str(a)]['output_folder']).resolve() == output
    cli_success(inside, 'workspace', 'remove', a)
    assert set(workspace_paths(inside)) == {str(b)}
    cli_success(inside, 'workspace', 'remove', b)
    assert workspace_members(inside)['packages'] == []


def test_workspace_editables_resolve_locally_without_global_registration(tmp_path):
    # F17.T02
    client = recipe_client(tmp_path)
    library = working_library(tmp_path / 'library')
    cli_success(client, 'create', library, '-nr')
    update_working_library(library / 'sources', header=17, generated=19, library=41)
    build_working_library(client, library)
    ws = workspace_client(client, tmp_path / 'workspace')
    cli_success(ws, 'workspace', 'init')
    workspace_add_members(ws, library)
    assert set(workspace_paths(ws)) == {str(library)}
    assert editable_mappings(ws) == {}
    node, output = native_editable_consumer(ws, Path(ws.cwd) / 'consumer', 'worklib/1.0')
    assert node['binary'] == 'Editable'
    assert output == '17 19 46\n'
    assert editable_mappings(client) == {}
    node, output = native_editable_consumer(client, tmp_path / 'outside', 'worklib/1.0')
    assert node['binary'] == 'Cache'
    assert output == '7 11 28\n'


def test_workspace_derives_recipe_identity_and_refuses_invalid_members(tmp_path):
    # F17.T03
    client = recipe_client(tmp_path)
    write_file(tmp_path / 'velmoraws.yml', 'packages:\n  - path: dynamic\n  - path: fixed\n'
               '  - path: anonymous\n    ref: given/7.8\n')
    # This recipe declares no identity; its definition entry supplies it.
    write_file(tmp_path / 'anonymous/velmorafile.py',
               'from velmora import VelmoraFile\nclass Anonymous(VelmoraFile):\n    pass\n')
    write_file(tmp_path / 'dynamic/velmorafile.py', '''from velmora import VelmoraFile
class Dynamic(VelmoraFile):
    def set_name(self):
        self.name = "derived"
    def set_version(self):
        self.version = "2.3"
''')
    recipe_file(tmp_path / 'fixed', '', name='fixed', version='4.5')
    consumer = recipe_file(tmp_path / 'consumer',
                           '    requires = "derived/2.3", "fixed/4.5", "given/7.8"\n')
    report = graph_document(client, consumer)
    for name, version in (('derived', '2.3'), ('fixed', '4.5'), ('given', '7.8')):
        node = named_node(report, name)
        assert node['version'] == version
        assert node['recipe'] == 'Editable'
    for body in (
            'from velmora import VelmoraFile\nclass Duplicate(VelmoraFile):\n    name = "fixed"\n    version = "4.5"\n',
            'from velmora import VelmoraFile\nclass Unknown(VelmoraFile):\n    pass\n',
            'raise RuntimeError("Recipe cannot load")\n'):
        write_file(tmp_path / 'dynamic/velmorafile.py', body)
        cli_rejection(client, 'workspace', 'install', '-nr')


def test_workspace_selected_source_install_build_and_create(tmp_path):
    # F17.T04: declaration order is deliberately opposite dependency order.
    client = recipe_client(tmp_path)
    cli_success(client, 'workspace', 'init')
    leaf = text_development_package(tmp_path / 'leaf', 'leaf', 'foundation\n')
    top = text_development_package(tmp_path / 'top', 'top', 'application\n', requires=('leaf/1.0',))
    other = text_development_package(tmp_path / 'other', 'other', 'independent\n')
    # The prerequisite's generated and build material goes to its recorded output area.
    area = tmp_path / 'leaf-output'
    workspace_add_members(client, top, other)
    cli_success(client, 'workspace', 'add', leaf, '-of', area, '-nr')
    cli_success(client, 'workspace', 'source', '--pkg=top/*', '--pkg=leaf/*')
    assert (top / 'source.txt').read_text() == 'application\n'
    assert (leaf / 'source.txt').read_text() == 'foundation\n'
    assert not (other / 'source.txt').exists()
    cli_success(client, 'workspace', 'install', '--pkg=top/*', '-nr')
    assert read_json(top / 'integration/dependencies.json') == {'leaf': '1.0'}
    assert read_json(area / 'integration/dependencies.json') == {}
    assert not (leaf / 'integration').exists()
    assert not (other / 'integration/dependencies.json').exists()
    cli_success(client, 'workspace', 'build', '--pkg=top/*', '-nr')
    assert (top / 'products/built.txt').read_text() == 'application\nfoundation\n'
    assert (area / 'products/built.txt').read_text() == 'foundation\n'
    assert not (leaf / 'products').exists()
    assert not (other / 'products/built.txt').exists()
    # Creating a package without its prerequisite that needs creation is refused
    # and creates no binary.
    refused = client.run('workspace', 'create', '--pkg=top/*', '-nr')
    assert refused.returncode != 0, refused
    assert any(line.startswith('ERROR:') for line in refused.text('stderr').splitlines()), refused
    assert selected_artifacts(selection(client, '*#*:*#*')) == set()
    cli_success(client, 'workspace', 'create', '--pkg=top/*', '--pkg=leaf/*', '-nr')
    # Only the selected members are created.
    assert {ref for ref, _, _, _ in selected_artifacts(selection(client, '*#*:*#*'))} == {
        'top/1.0', 'leaf/1.0'}
    outside = workspace_client(client, tmp_path.parent / (tmp_path.name + '-outside'))
    report = cli_success(outside, 'install', '--requires=top/1.0', '-nr', '--format=json').json('stdout')
    assert (Path(named_node(report, 'top')['package_folder']) / 'built.txt').read_text() == 'application\nfoundation\n'


def test_workspace_aggregate_propagates_dependency_build_failure(tmp_path):
    # F17.T05: prove a usable build before injecting a real recipe failure.
    client = recipe_client(tmp_path)
    cli_success(client, 'workspace', 'init')
    leaf = text_development_package(tmp_path / 'leaf', 'leaf', 'ok\n')
    top = text_development_package(tmp_path / 'top', 'top', 'top\n', requires=('leaf/1.0',))
    workspace_add_members(client, top, leaf)
    cli_success(client, 'workspace', 'source')
    cli_success(client, 'workspace', 'build', '-nr')
    assert (top / 'products/built.txt').read_text() == 'top\nok\n'
    (top / 'products/built.txt').unlink()
    text_development_package(leaf, 'leaf', 'ok\n', extra='''    def build(self):
        raise RuntimeError("Deliberate prerequisite build failure")
''')
    for operation in ('build', 'create'):
        failure = cli_rejection(client, 'workspace', operation, '-nr')
        assert any('build()' in line for line in failure.text('stderr').splitlines()
                   if line.startswith('ERROR:')), failure
        assert 'Deliberate prerequisite build failure' in failure.text('stderr')
        assert not (top / 'products/built.txt').exists()
    # The install path must also propagate an external prerequisite build failure.
    outside = workspace_client(client, tmp_path.parent / (tmp_path.name + '-export'))
    external = text_development_package(Path(outside.cwd) / 'external', 'external', 'x', extra='''    def build(self):
        raise RuntimeError("Deliberate external build failure")
''')
    cli_success(outside, 'export', external)
    recipe_file(top, '    requires = "external/1.0"\n', name='top', version='1.0')
    cli_success(client, 'workspace', 'remove', leaf)
    failure = cli_rejection(client, 'workspace', 'install', '-nr', '--build=missing')
    assert any('build()' in line for line in failure.text('stderr').splitlines()
               if line.startswith('ERROR:')), failure
    assert 'Deliberate external build failure' in failure.text('stderr')


def test_workspace_shared_lock_overrides_member_automatic_lock(tmp_path):
    # F17.T06
    client = recipe_client(tmp_path)
    external = text_development_package(tmp_path / 'external-one', 'external', 'locked\n')
    cli_success(client, 'create', external, '-nr')
    top = text_development_package(tmp_path / 'workspace/top', 'top', 'top\n', requires=('external/[>=1 <4]',))
    shared = capture_lock(client, top, tmp_path / 'workspace/shared.lock')
    old_records = lock_records(shared, 'requires')
    newer = text_development_package(tmp_path / 'external-two', 'external', 'new\n', version='2.0')
    cli_success(client, 'create', newer, '-nr')
    capture_lock(client, top, top / 'velmora.lock')
    newest = text_development_package(tmp_path / 'external-three', 'external', 'latest\n', version='3.0')
    cli_success(client, 'create', newest, '-nr')
    ws = workspace_client(client, top.parent)
    cli_success(ws, 'workspace', 'init')
    workspace_add_members(ws, top)
    cli_success(ws, 'workspace', 'source')
    for operation in ('install', 'build'):
        cli_success(ws, 'workspace', operation, '-nr', '--lockfile', shared, '--lockfile-partial')
        assert read_json(top / 'integration/dependencies.json') == {'external': '1.0'}
    assert (top / 'products/built.txt').read_text() == 'top\nlocked\n'
    assert lock_records(shared, 'requires') == old_records
    cli_success(ws, 'workspace', 'super-install', '-nr', '--lockfile', shared,
                '--lockfile-out', top.parent / 'result.lock', '--format=json', '--lockfile-partial')
    assert {ref for ref in lock_records(top.parent / 'result.lock', 'requires')
            if ref.split('/')[0] == 'external'} == set(old_records)
    # With no workspace lock, the member's automatic lock is still not adopted.
    cli_success(ws, 'workspace', 'build', '-nr')
    assert read_json(top / 'integration/dependencies.json') == {'external': '3.0'}
    assert (top / 'products/built.txt').read_text() == 'top\nlatest\n'


def test_workspace_combined_install_exposes_only_external_usable_integration(tmp_path):
    # F17.T07
    client = recipe_client(tmp_path)
    library = working_library(tmp_path / 'stored')
    cli_success(client, 'create', library, '-nr')
    ws = workspace_client(client, tmp_path / 'workspace')
    cli_success(ws, 'workspace', 'init')
    a = recipe_file(Path(ws.cwd) / 'alpha', '    requires = "worklib/1.0"\n', name='alpha', version='1.0').parent
    b = recipe_file(Path(ws.cwd) / 'beta', '    requires = "alpha/1.0", "worklib/1.0"\n', name='beta', version='1.0').parent
    workspace_add_members(ws, b, a)
    out = Path(ws.cwd) / 'combined'
    report = cli_success(ws, 'workspace', 'super-install', '-nr', '-g', 'CMakeDeps',
                         '-of', out, '--format=json', *CMAKE_SETTINGS).json('stdout')
    assert {n['name'] for n in report['graph']['nodes'].values() if n['name'] is not None} == {'worklib'}
    assert named_node(report, 'worklib')['binary'] == 'Cache'
    write_file(out / 'main.c', '''#include <stdio.h>
#include <work.h>
#include <built.h>
int main(void) { printf("%d %d %d\\n", SOURCE_VALUE, BUILD_VALUE, api()); return 0; }
''')
    write_file(out / 'CMakeLists.txt', '''cmake_minimum_required(VERSION 3.23)
project(CombinedConsumer C)
find_package(worklib REQUIRED)
add_executable(app main.c)
target_link_libraries(app PRIVATE worklib::api)
''')
    cmake_command(ws, out, '-S', str(out), '-B', str(out / 'native'),
                  '-DCMAKE_PREFIX_PATH=' + str(out), '-DCMAKE_BUILD_TYPE=Release')
    cmake_command(ws, out, '--build', str(out / 'native'))
    assert native_command(ws, out, str(out / 'native/app')).text('stdout') == '7 11 28\n'


def test_workspace_open_and_complete_produce_editable_source_chain(tmp_path):
    # F17.T08
    client = recipe_client(tmp_path)
    leaf = text_development_package(tmp_path / 'original-leaf', 'leaf', 'old\n')
    middle = text_development_package(tmp_path / 'original-middle', 'middle', 'bridge\n', requires=('leaf/1.0',))
    unrelated = text_development_package(tmp_path / 'unrelated', 'unrelated', 'unused\n')
    for path in (leaf, middle, unrelated):
        cli_success(client, 'export', path)
    ws = workspace_client(client, tmp_path / 'workspace')
    cli_success(ws, 'workspace', 'init')
    cli_success(ws, 'workspace', 'open', 'leaf/1.0', '-nr')
    opened = Path(ws.cwd) / 'leaf'
    assert (opened / 'input.txt').read_text() == 'old\n'
    workspace_add_members(ws, opened)
    write_file(opened / 'input.txt', 'edited\n')
    top = text_development_package(Path(ws.cwd) / 'top', 'top', 'top\n', requires=('middle/1.0',))
    workspace_add_members(ws, top)
    cli_success(ws, 'workspace', 'complete', '-nr')
    members = workspace_paths(ws)
    locations = {item['ref']: Path(path) for path, item in members.items()}
    assert len(members) == len(locations) == 3
    assert set(locations) == {'leaf/1.0', 'middle/1.0', 'top/1.0'}
    assert locations['leaf/1.0'] == opened
    assert locations['top/1.0'] == top
    assert (locations['middle/1.0'] / 'input.txt').read_text() == 'bridge\n'
    cli_success(ws, 'workspace', 'source')
    cli_success(ws, 'workspace', 'build', '--pkg=top/*', '-nr')
    assert (top / 'products/built.txt').read_text() == 'top\nbridge\nedited\n'
