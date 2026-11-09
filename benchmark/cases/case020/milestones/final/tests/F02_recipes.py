# feature: F02
"""Acceptance of recipe loading, declarations and consumer choices."""
from collections import Counter
from pathlib import Path

from _helpers import read_json, run, write_file
from F01_helpers import (cli_success, cli_rejection, graph_document, named_node,
                         install_bundle)
from F02_helpers import (recipe_client, recipe_file, installed_graph,
                         inspected_recipe, consumer_dependency)


def test_python_and_text_recipe_inputs(tmp_path):
    # F02.T01
    client = recipe_client(tmp_path)
    for name in ('ingredient', 'tooling'):
        recipe_file(tmp_path / name, '    package_type = "header-library"\n' +
                    ('    options = {"flavor": ["plain", "tuned"]}\n'
                     '    default_options = {"flavor": "plain"}\n' if name == 'ingredient' else ''), name=name)
        cli_success(client, 'create', tmp_path / name, '-o', 'ingredient/*:flavor=tuned')
    recipe_file(tmp_path / 'python', '    settings = "os", "arch", "build_type"\n'
                '    requires = "ingredient/2.7"\n'
                '    tool_requires = "tooling/2.7"\n'
                '    default_options = {"ingredient/*:flavor": "tuned"}\n'
                '    generators = "CMakeDeps"\n')
    write_file(tmp_path / 'text/velmorafile.txt', '[requires]\ningredient/2.7\n'
               '[tool_requires]\ntooling/2.7\n[options]\ningredient/*:flavor=tuned\n'
               '[generators]\nCMakeDeps\n')
    for folder in ('python', 'text'):
        report = installed_graph(client, tmp_path / folder)
        assert named_node(report, 'ingredient')['options']['flavor'] == 'tuned'
        assert named_node(report, 'tooling', 'build')['context'] == 'build'
        assert (tmp_path / folder / 'ingredient-config.cmake').is_file()
    cli_rejection(client, 'graph', 'info', tmp_path / 'missing', '-nr')
    unreadable = tmp_path / 'python/velmorafile.py'
    unreadable.chmod(0)
    try:
        cli_rejection(client, 'graph', 'info', unreadable, '-nr')
    finally:
        unreadable.chmod(0o600)


def test_inspection_and_loading_cause(tmp_path):
    # F02.T02
    client = recipe_client(tmp_path)
    recipe_file(tmp_path, '    description = "Recipe inspection payload"\n'
                '    license = "MIT"\n    author = "Recipe author"\n'
                '    url = "https://example.invalid/recipe"\n'
                '    topics = ("geometry", "rendering")\n'
                '    settings = "os", "arch"\n'
                '    options = {"shared": [True, False], "mode": ["fast", "small"]}\n'
                '    default_options = {"shared": False, "mode": "small"}\n')
    result = inspected_recipe(client, tmp_path)
    for key, expected in {'name': 'specimen', 'version': '2.7',
                          'description': 'Recipe inspection payload', 'license': 'MIT',
                          'author': 'Recipe author', 'url': 'https://example.invalid/recipe',
                          'default_options': {'shared': False, 'mode': 'small'}}.items():
        assert result[key] == expected
    # Declaration membership does not impose presentation order.
    for key, expected in {'topics': ['geometry', 'rendering'], 'settings': ['os', 'arch']}.items():
        assert Counter(result[key]) == Counter(expected)
    assert {key: Counter(values) for key, values in result['options_definitions'].items()} == {
        'shared': Counter(['True', 'False']), 'mode': Counter(['fast', 'small'])}
    path = tmp_path / 'broken/velmorafile.py'
    cause = 'caller_supplied_loading_failure'
    write_file(path, f'raise ValueError({cause!r})\n')
    failure = cli_rejection(client, 'inspect', path)
    assert str(path) in failure.text('stderr')
    assert cause in failure.text('stderr')


def test_declared_package_kinds(tmp_path):
    # F02.T03: generic library is resolved rather than retained as an abstract kind.
    client = recipe_client(tmp_path)
    kinds = ('static-library', 'shared-library', 'header-library', 'application',
             'build-scripts', 'python-require', 'configuration', 'unknown')
    for kind in kinds:
        recipe_file(tmp_path, f'    package_type = {kind!r}\n'
                    '    options = {"header_only": [True, False]}\n'
                    '    default_options = {"header_only": True}\n')
        assert named_node(graph_document(client), 'specimen')['package_type'] == kind
    recipe_file(tmp_path, '    package_type = "library"\n'
                '    options = {"shared": [True, False]}\n'
                '    default_options = {"shared": False}\n')
    assert named_node(graph_document(client), 'specimen')['package_type'] == 'static-library'


def test_package_kind_inference_and_conflicts(tmp_path):
    # F02.T04
    client = recipe_client(tmp_path)
    for declaration in ('', '    package_type = "library"\n'):
        body = declaration + '    options = {"header_only": [True, False], "shared": [True, False]}\n'
        for header, shared, expected in ((True, True, 'header-library'),
                                         (False, True, 'shared-library'),
                                         (False, False, 'static-library')):
            recipe_file(tmp_path, body + f'    default_options = {{"header_only": {header}, "shared": {shared}}}\n')
            assert named_node(graph_document(client), 'specimen')['package_type'] == expected
        # An enabled header-only choice decides by itself, with no shared-library choice declared.
        recipe_file(tmp_path, declaration + '    options = {"header_only": [True, False]}\n'
                    '    default_options = {"header_only": True}\n')
        assert named_node(graph_document(client), 'specimen')['package_type'] == 'header-library'
    recipe_file(tmp_path, '')
    assert named_node(graph_document(client), 'specimen')['package_type'] == 'unknown'
    recipe_file(tmp_path, '    package_type = "library"\n')
    cli_rejection(client, 'graph', 'info', '.', '-nr')
    for kind, value in (('static-library', True), ('shared-library', False)):
        recipe_file(tmp_path, f'    package_type = {kind!r}\n'
                    '    options = {"shared": [True, False]}\n'
                    f'    default_options = {{"shared": {value}}}\n')
        cli_rejection(client, 'graph', 'info', '.', '-nr')
    # Only a contradiction is refused: an agreeing shared-library choice is accepted.
    for kind, value in (('static-library', False), ('shared-library', True)):
        recipe_file(tmp_path, f'    package_type = {kind!r}\n'
                    '    options = {"shared": [True, False]}\n'
                    f'    default_options = {{"shared": {value}}}\n')
        assert named_node(graph_document(client), 'specimen')['package_type'] == kind


def test_bound_option_precedence(tmp_path):
    # F02.T05: install the same dependency under each source of choice.
    for consumer, args, expected in (
            (False, (), 'base'), (True, (), 'consumer'),
            (True, ('-pr:h', 'default', '-pr:h', 'selection'), 'profile'),
            (True, ('-pr:h', 'default', '-pr:h', 'selection', '-o', 'choice/*:mode=command'), 'command')):
        root = tmp_path / expected
        client = recipe_client(root)
        recipe_file(root / 'dependency', '    package_type = "header-library"\n'
                    '    options = {"mode": ["base", "consumer", "profile", "command"]}\n'
                    '    default_options = {"mode": "base"}\n', name='choice')
        cli_success(client, 'export', root / 'dependency')
        install_bundle(client, root / 'profile-input', {
            'profiles/selection': '[options]\nchoice/*:mode=profile\n'})
        recipe_file(root / 'consumer', '    requires = "choice/2.7"\n' +
                    ('    default_options = {"choice/*:mode": "consumer"}\n' if consumer else ''))
        report = installed_graph(client, root / 'consumer', '--build=missing', *args)
        assert consumer_dependency(report)['options']['mode'] == expected


def test_option_validation_and_selector_scope(tmp_path):
    # F02.T06
    client = recipe_client(tmp_path)
    recipe_file(tmp_path / 'dependency', '    options = {"mode": ["compact", "wide"]}\n'
                '    default_options = {"mode": "compact"}\n', name='choice')
    cli_success(client, 'export', tmp_path / 'dependency')
    recipe_file(tmp_path, '    requires = "choice/2.7"\n')
    assert consumer_dependency(graph_document(client))['options']['mode'] == 'compact'
    for selector in ('*:absent=True', 'choice/*:absent=True'):
        assert consumer_dependency(graph_document(client, '.', '-o', selector))['options'] == {'mode': 'compact'}
    for selector in ('choice/2.7:absent=True', '&:absent=True', 'choice/*:mode=outside'):
        cli_rejection(client, 'graph', 'info', '.', '-nr', '-o', selector)
    for domain, allowed in ((['compact', None], True), (['compact'], False)):
        recipe_file(tmp_path, f'    options = {{"mode": {domain!r}}}\n')
        if allowed:
            assert named_node(graph_document(client), 'specimen')['options']['mode'] is None
        else:
            node = named_node(graph_document(client), 'specimen')
            assert node['info_invalid'] is not None
            cli_rejection(client, 'install', '.', '-nr', status=6)


def test_package_and_component_consumer_metadata(tmp_path):
    # F02.T07: read metadata through the installed dependency, not inspect.
    client = recipe_client(tmp_path)
    metadata = {
        'includedirs': ['api'], 'libdirs': ['libraries'], 'libs': ['geometry'],
        'system_libs': ['m'], 'defines': ['GEOMETRY_API=19'],
        'cflags': ['-O1'], 'cxxflags': ['-O2'],
        'sharedlinkflags': ['-Wl,--as-needed'], 'exelinkflags': ['-Wl,--as-needed'],
        'frameworkdirs': ['Frameworks'], 'frameworks': ['GeometryKit']}
    component = dict(metadata, libs=['primitive'], defines=['PRIMITIVE_API=23'])
    # Keep package-wide and component declarations in separate packages.
    whole_lines = ''.join(f'        self.cpp_info.{k} = {v!r}\n' for k, v in metadata.items())
    parts_lines = ''.join(f'        self.cpp_info.components["primitive"].{k} = {v!r}\n'
                          for k, v in component.items())
    parts_lines += '        self.cpp_info.components["facade"].requires = ["primitive"]\n'
    for name, lines in (('whole', whole_lines), ('parts', parts_lines)):
        library = 'geometry' if name == 'whole' else 'primitive'
        header = f'int {library}(void);\n'
        source = f'int {library}(void) {{ return 37; }}\n'
        package_body = (
            '    def package(self):\n'
            '        import os, subprocess\n'
            '        from velmora.tools.files import save\n'
            f'        library = {library!r}\n'
            '        root = self.package_folder\n'
            '        os.makedirs(os.path.join(root, "libraries"), exist_ok=True)\n'
            f'        save(self, os.path.join(root, "api", library + ".h"), {header!r})\n'
            f'        save(self, os.path.join(root, library + ".c"), {source!r})\n'
            '        obj = os.path.join(root, "libraries", library + ".o")\n'
            '        subprocess.run(["gcc", "-c", os.path.join(root, library + ".c"), "-o", obj], check=True)\n'
            '        subprocess.run(["ar", "rcs", os.path.join(root, "libraries", "lib" + library + ".a"), obj], check=True)\n')
        recipe_file(tmp_path / name, package_body + '    def package_info(self):\n' + lines, name=name)
        cli_success(client, 'create', tmp_path / name)
    recipe_file(tmp_path / 'consumer', '    requires = "whole/2.7", "parts/2.7"\n'
                '    def generate(self):\n'
                '        import json, os\n'
                '        keys = ' + repr(list(metadata)) + '\n'
                '        output = {}\n'
                '        for name in ("whole", "parts"):\n'
                '            info = self.dependencies[name].cpp_info\n'
                '            output[name] = {k: getattr(info, k) for k in keys}\n'
                '            output[name]["components"] = {n: {k: getattr(c, k) for k in keys + ["requires"]} for n, c in info.components.items()}\n'
                '        with open(os.path.join(self.generators_folder, "received.json"), "w") as f:\n'
                '            json.dump(output, f)\n')
    report = installed_graph(client, tmp_path / 'consumer')
    received = read_json(tmp_path / 'consumer/received.json')
    for name, values, actual in (('whole', metadata, received['whole']),
                                 ('parts', component, received['parts']['components']['primitive'])):
        package = named_node(report, name)
        for key, expected in values.items():
            if key in ('includedirs', 'libdirs', 'frameworkdirs'):
                expected = [str(Path(package['package_folder']) / value) for value in expected]
            assert actual[key] == expected
    assert received['parts']['components']['facade']['requires'] == ['primitive']
    for library, macro, value, actual in (
            ('geometry', 'GEOMETRY_API', 19, received['whole']),
            ('primitive', 'PRIMITIVE_API', 23, received['parts']['components']['primitive'])):
        source = tmp_path / (library + '-consumer.c')
        write_file(source, f'#include "{library}.h"\n'
                   f'#if {macro} != {value}\n#error Missing consumer definition\n#endif\n'
                   f'int main(void) {{ return {library}() == 37 ? 0 : 1; }}\n')
        executable = tmp_path / (library + '-consumer')
        command = ['gcc', str(source), '-o', str(executable)]
        command += ['-I' + path for path in actual['includedirs']]
        command += ['-L' + path for path in actual['libdirs']]
        command += ['-D' + value for value in actual['defines']]
        command += actual['cflags'] + actual['exelinkflags']
        command += ['-l' + library for library in actual['libs'] + actual['system_libs']]
        result = run(command, cwd=tmp_path, env=client.env)
        assert result.returncode == 0, result
        result = run((str(executable),), cwd=tmp_path, env=client.env)
        assert result.returncode == 0, result
