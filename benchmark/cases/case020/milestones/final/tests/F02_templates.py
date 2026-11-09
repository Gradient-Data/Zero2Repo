# feature: F02
"""Acceptance of built-in and caller-owned project templates."""
from pathlib import Path

from _helpers import read_bytes, write_file
from F01_helpers import cli_success, cli_rejection, graph_document, install_bundle, named_node
from F02_helpers import recipe_client, inspected_recipe, yaml_document


def test_builtin_project_families(tmp_path):
    # F02.T08. Observe project creation through the recipe graph and the generated
    # workspace/index documents; one generated library project is built end to end.
    client = recipe_client(tmp_path)
    families = ('basic', 'header_lib', 'cmake_lib', 'cmake_exe', 'meson_lib',
                'meson_exe', 'msbuild_lib', 'msbuild_exe', 'bazel_lib', 'bazel_exe',
                'autotools_lib', 'autotools_exe', 'premake_lib', 'premake_exe', 'qbs_lib')
    cli_success(client, 'profile', 'detect', '--name', 'native')
    native = ('-pr:h', 'native', '-pr:b', 'native')
    for family in families:
        output = tmp_path / family
        name = 'project_' + family
        cli_success(client, 'new', family, '-d', 'name=' + name, '-d', 'version=8.4', '-o', output)
        node = named_node(graph_document(client, output, *native), name)
        assert node['version'] == '8.4'
        if family != 'basic':
            # A project family supplies project material beside its recipe.
            assert sum(path.is_file() for path in output.rglob('*')) > 1
        # Each family is the kind of project it names.
        kind = family.rpartition('_')[2]
        if kind == 'exe':
            assert node['package_type'] == 'application'
        elif family == 'header_lib':
            assert node['package_type'] == 'header-library'
        elif kind == 'lib':
            assert node['package_type'] in ('static-library', 'shared-library')
    # Generated project material really builds, here for one library family end to end.
    for family in ('cmake_lib',):
        name = 'project_' + family
        report = cli_success(client, 'create', tmp_path / family, '-nr', *native,
                             '--format=json').json('stdout')
        package = Path(named_node(report, name)['package_folder'])
        packaged = {path.name for path in package.rglob('*') if path.is_file()}
        assert packaged - {'velmorainfo.txt', 'velmoramanifest.txt'}, packaged
    output = tmp_path / 'index'
    cli_success(client, 'new', 'local_recipes_index', '-d', 'name=catalog_entry',
                '-d', 'version=6.3', '-d', 'url=https://example.invalid/source.tar.gz',
                '-d', 'sha256=caller-checksum', '-o', output)
    info = inspected_recipe(client, output / 'recipes/catalog_entry/all')
    assert info['name'] == 'catalog_entry'
    config = yaml_document(client, output / 'recipes/catalog_entry/config.yml')
    assert config['versions']['6.3']['folder'] == 'all'
    data = yaml_document(client, output / 'recipes/catalog_entry/all/velmoradata.yml')
    assert data['sources']['6.3']['url'] == ['https://example.invalid/source.tar.gz']
    assert data['sources']['6.3']['sha256'] == 'caller-checksum'
    output = tmp_path / 'workspace'
    cli_success(client, 'new', 'workspace', '-d', 'version=5.6', '-o', output)
    definition = yaml_document(client, output / 'velmoraws.yml')
    assert definition['packages']
    for package in definition['packages']:
        info = inspected_recipe(client, output / package['path'])
        assert info['name'] == package['ref'].split('/')[0]
        if package['path'] != 'liba':
            # The caller's version belongs to the library member only.
            assert info['version'] == package['ref'].split('/')[1]
    # Only the initial library member is rendered from the caller's version.
    assert inspected_recipe(client, output / 'liba')['version'] == '5.6'


def test_custom_template_substitution_and_protection(tmp_path):
    # F02.T09
    client = recipe_client(tmp_path)
    source = tmp_path / 'custom'
    write_file(source / '{{artifact}}.txt', 'Project {{artifact}} has value {{payload}}.\n')
    write_file(source / 'raw.bin', b'\x00{{payload}}\xff')
    write_file(source / 'matched.dat', b'{{payload}}\xfe')
    write_file(source / 'not_templates', 'raw.bin\n*.dat\n')
    destination = tmp_path / 'generated'
    cli_success(client, 'new', source, '-d', 'artifact=geometry', '-d', 'payload=first', '-o', destination)
    assert read_bytes(destination / 'geometry.txt') == b'Project geometry has value first.\n'
    assert read_bytes(destination / 'raw.bin') == b'\x00{{payload}}\xff'
    assert read_bytes(destination / 'matched.dat') == b'{{payload}}\xfe'
    cli_rejection(client, 'new', source, '-d', 'artifact=geometry', '-d', 'payload=second', '-o', destination)
    assert read_bytes(destination / 'geometry.txt') == b'Project geometry has value first.\n'
    cli_success(client, 'new', source, '-d', 'artifact=geometry', '-d', 'payload=second', '-o', destination, '--force')
    assert read_bytes(destination / 'geometry.txt') == b'Project geometry has value second.\n'
    assert read_bytes(destination / 'raw.bin') == b'\x00{{payload}}\xff'
    cli_rejection(client, 'new', source, '-d', 'artifact=geometry', '-o', tmp_path / 'undefined')
    # A value required only by a file name is as required as one in the contents.
    named_only = tmp_path / 'named-only'
    write_file(named_only / '{{chapter}}.txt', 'static contents\n')
    cli_rejection(client, 'new', named_only, '-o', tmp_path / 'undefined-name')
    cli_rejection(client, 'new', 'nonexistent-project-family', '-o', tmp_path / 'unknown')


def test_template_resolution_precedence_and_default(tmp_path):
    # F02.T10: each arm gets an independent home and output directory.
    for local, installed, expected in ((True, True, 'local'), (False, True, 'installed'),
                                       (False, False, 'builtin')):
        root = tmp_path / expected
        client = recipe_client(root)
        template = 'from velmora import VelmoraFile\nclass Recipe(VelmoraFile):\n    description = "{{origin}}"\n'
        if installed:
            install_bundle(client, root / 'bundle', {
                'templates/command/new/basic/velmorafile.py': template.replace('{{origin}}', 'installed')})
        if local:
            write_file(root / 'basic/velmorafile.py', template.replace('{{origin}}', 'local'))
        output = root / 'generated'
        cli_success(client, 'new', 'basic', '-d', 'name=resolution', '-d', 'version=4.9', '-o', output)
        info = inspected_recipe(client, output)
        if expected == 'builtin':
            assert (info['name'], info['version']) == ('resolution', '4.9')
        else:
            assert info['description'] == expected
    client = recipe_client(tmp_path / 'default')
    output = tmp_path / 'default/output'
    cli_success(client, 'new', '-o', output)
    inspected_recipe(client, output)
    # The default recipe also takes the caller's template values.
    output = tmp_path / 'default/valued'
    cli_success(client, 'new', '-d', 'name=resolution', '-d', 'version=4.9', '-o', output)
    info = inspected_recipe(client, output)
    assert (info['name'], info['version']) == ('resolution', '4.9')
