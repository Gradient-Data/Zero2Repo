# feature: F16
"""Editable registration, resolution, layouts and real native consumption."""
from _helpers import file_bytes, write_file
from F01_helpers import cli_rejection, cli_success
from F02_helpers import recipe_client, recipe_file
from F16_helpers import (editable_mappings, working_library, update_working_library,
                         build_working_library, native_editable_consumer)


def test_editable_registration_identity_and_revision_refusal(tmp_path):
    # F16.T01
    client = recipe_client(tmp_path)
    first = recipe_file(tmp_path / 'first', '', name='first', version='1.2')
    second = recipe_file(tmp_path / 'second', '', name='second', version='3.4')
    cli_success(client, 'editable', 'add', first, '-nr')
    # An unpinned reference is an accepted spelling of the same identity.
    cli_success(client, 'editable', 'add', second, '--ref=second/3.4', '-nr')
    mappings = editable_mappings(client)
    assert set(mappings) == {'first/1.2', 'second/3.4'}
    assert mappings['first/1.2']['path'] == str(first)
    assert mappings['second/3.4']['path'] == str(second)
    for missing in ('name', 'version', 'both'):
        body = 'from velmora import VelmoraFile\nclass Incomplete(VelmoraFile):\n'
        body += {'name': '    version = "1.0"\n',
                 'version': '    name = "incomplete"\n', 'both': '    pass\n'}[missing]
        path = write_file(tmp_path / missing / 'velmorafile.py', body)
        cli_rejection(client, 'editable', 'add', path, '-nr')
        assert editable_mappings(client) == mappings
    cli_rejection(client, 'editable', 'add', first, '--ref=first/1.2#pinned', '-nr')
    assert editable_mappings(client) == mappings
    cli_success(client, 'editable', 'remove', '-r', 'first/1.2')
    assert editable_mappings(client) == {'second/3.4': mappings['second/3.4']}
    cli_success(client, 'editable', 'remove', second.parent)
    assert editable_mappings(client) == {}


def test_exact_editable_consumes_live_headers_libraries_and_components(tmp_path):
    # F16.T02: a stored binary remains present as a competing exact reference.
    client = recipe_client(tmp_path)
    root = working_library(tmp_path / 'library')
    cli_success(client, 'create', root, '-nr')
    update_working_library(root / 'sources', header=17, generated=19, library=41)
    build_working_library(client, root)
    cli_success(client, 'editable', 'add', root, '-nr')
    node, output = native_editable_consumer(client, tmp_path / 'consumer-one', 'worklib/1.0')
    assert node['binary'] == 'Editable'
    assert output == '17 19 46\n'
    # Only the exact registered reference is redirected to the working tree.
    for other in ('worklib/1.0@team/stable', 'worklib/1.1'):
        cli_rejection(client, 'install', '--requires=' + other, '-nr')
    # A header edit is consumed immediately, without rebuilding or packaging the dependency.
    write_file(root / 'sources/public/work.h', '#define SOURCE_VALUE 29\nint api(void);\n')
    _, output = native_editable_consumer(client, tmp_path / 'consumer-two', 'worklib/1.0')
    assert output == '29 19 46\n'
    update_working_library(root / 'sources', header=29, generated=31, library=53)
    build_working_library(client, root)
    _, output = native_editable_consumer(client, tmp_path / 'consumer-three', 'worklib/1.0')
    assert output == '29 31 58\n'


def test_editable_ranges_select_highest_satisfying_local_candidate(tmp_path):
    # F16.T03: each candidate has distinguishable real content.
    client = recipe_client(tmp_path)
    stored = working_library(tmp_path / 'stored', version='2.0')
    cli_success(client, 'create', stored, '-nr')
    editable = working_library(tmp_path / 'editable', version='1.0')
    update_working_library(editable / 'sources', header=13, generated=17, library=37)
    build_working_library(client, editable)
    cli_success(client, 'editable', 'add', editable, '-nr')
    node, output = native_editable_consumer(client, tmp_path / 'higher-cache', 'worklib/[>=1 <4]')
    assert node['version'] == '2.0'
    assert output == '7 11 28\n'
    newer = working_library(tmp_path / 'newer', version='3.0')
    update_working_library(newer / 'sources', header=43, generated=47, library=61)
    build_working_library(client, newer)
    cli_success(client, 'editable', 'add', newer, '-nr')
    node, output = native_editable_consumer(client, tmp_path / 'higher-editable', 'worklib/[>=1 <4]')
    assert node['version'] == '3.0'
    assert node['binary'] == 'Editable'
    assert output == '43 47 66\n'
    node, output = native_editable_consumer(client, tmp_path / 'bounded', 'worklib/[>=1 <2]')
    assert node['version'] == '1.0'
    assert output == '13 17 42\n'


def test_editable_output_area_and_declared_component_layout(tmp_path):
    # F16.T04: no artifacts are put under conventional source/build directories.
    client = recipe_client(tmp_path)
    root = working_library(tmp_path / 'library', source='code/input', build='products/native')
    output_area = tmp_path / 'selected-output'
    build_working_library(client, root, output=output_area)
    cli_success(client, 'editable', 'add', root, '-nr', '-of', output_area)
    mapping = editable_mappings(client)['worklib/1.0']
    assert mapping['path'] == str(root / 'velmorafile.py')
    assert mapping['output_folder'] == str(output_area)
    node, result = native_editable_consumer(client, tmp_path / 'consumer', 'worklib/1.0')
    assert node['binary'] == 'Editable'
    assert result == '7 11 28\n'
    update_working_library(root / 'code/input', header=67, generated=71, library=73)
    build_working_library(client, root, output=output_area)
    _, result = native_editable_consumer(client, tmp_path / 'changed-consumer', 'worklib/1.0')
    assert result == '67 71 78\n'


def test_editable_removal_restores_stored_binary_and_preserves_tree(tmp_path):
    # F16.T05
    client = recipe_client(tmp_path)
    root = working_library(tmp_path / 'library')
    cli_success(client, 'create', root, '-nr')
    update_working_library(root / 'sources', header=79, generated=83, library=89)
    build_working_library(client, root)
    cli_success(client, 'editable', 'add', root, '-nr')
    node, result = native_editable_consumer(client, tmp_path / 'before', 'worklib/1.0')
    assert node['binary'] == 'Editable'
    assert result == '79 83 94\n'
    paths = [str(path.relative_to(root)) for path in root.rglob('*') if path.is_file()]
    before = file_bytes(root, paths)
    cli_success(client, 'editable', 'remove', '-r', 'worklib/1.0')
    assert editable_mappings(client) == {}
    node, result = native_editable_consumer(client, tmp_path / 'after', 'worklib/1.0')
    assert node['binary'] == 'Cache'
    assert result == '7 11 28\n'
    assert file_bytes(root, paths) == before
