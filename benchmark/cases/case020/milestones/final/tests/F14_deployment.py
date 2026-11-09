# feature: F14
"""Acceptance of artifact selection, recipe deployment and relocated consumers."""
from collections import Counter
from pathlib import Path

from _helpers import write_file
from F01_helpers import cli_success, cli_rejection
from F02_helpers import recipe_client, recipe_file
from F07_helpers import (compiled_usage_package, cmake_command, native_command,
                         NATIVE_SOURCE, CMAKE_SETTINGS)
from F14_helpers import (artifact_package, deployment_install, deployed_tree,
                         graph_copy_deployer, retains_relative_path)


def test_full_and_direct_artifact_selection(tmp_path):
    client = recipe_client(tmp_path / 'client')
    artifacts = {
        'leaf': {'include/leaf.h': 'leaf header', 'share/leaf.dat': 'leaf data'},
        'top': {'include/top.h': 'top header', 'share/top.dat': 'top data'},
        'tool': {'bin/tool': '#!/bin/sh\necho build-tool\n', 'share/tool.dat': 'tool data'}}
    artifact_package(client, tmp_path / 'leaf', 'leaf', artifacts['leaf'])
    artifact_package(client, tmp_path / 'tool', 'tool', artifacts['tool'],
                     body='    package_type = "application"\n')
    artifact_package(client, tmp_path / 'top', 'top', artifacts['top'],
                     body='    requires = "leaf/1.0"\n')
    consumer = recipe_file(tmp_path / 'consumer', '''    requires = "top/1.0"
    tool_requires = "tool/1.0"
''').parent
    for mode, names in [('full_deploy', ('leaf', 'top', 'tool')),
                        ('direct_deploy', ('top', 'tool'))]:
        destination = tmp_path / mode
        deployment_install(client, consumer, destination, '--deployer=' + mode,
                           '-c:b', 'tools.graph:skip_binaries=False')
        # Package placement is deliberately unpinned; all delivered bytes count.
        actual = deployed_tree(destination)
        material_paths = {relative for package in artifacts.values() for relative in package}
        actual = {p: value for p, value in actual.items()
                  if any(retains_relative_path(p, relative) for relative in material_paths)}
        assert Counter(actual.values()) == Counter(
            content.encode() for name in names for content in artifacts[name].values()), actual
        for name in names:
            for relative, content in artifacts[name].items():
                assert any(retains_relative_path(p, relative) and value == content.encode()
                           for p, value in actual.items()), actual


def test_runtime_subset_and_unavailable_artifacts(tmp_path):
    client = recipe_client(tmp_path / 'client')
    files = {'executables/launch': '#!/bin/sh\necho runtime\n',
             'executables/plugins/helper': '#!/bin/sh\necho helper\n',
             'libraries/liborbit.so': 'shared artifact',
             'libraries/plugins/libextra.so.2': 'versioned shared artifact',
             'libraries/liborbit.a': 'static artifact', 'include/orbit.h': 'header',
             'extras/second-tool': 'second location executable',
             'extralibs/libsecond.so': 'second location shared'}
    body = '''    package_type = "shared-library"
    def package_info(self):
        self.cpp_info.bindirs = ["executables", "extras"]
        self.cpp_info.libdirs = ["libraries", "extralibs"]
'''
    # A runtime-enabled dependency reached only through another one.
    artifact_package(client, tmp_path / 'deep', 'deep',
                     {'deepbin/deep-tool': 'transitive executable', 'deeplib/libdeep.so': 'transitive shared'},
                     body='''    package_type = "shared-library"
    def package_info(self):
        self.cpp_info.bindirs = ["deepbin"]
        self.cpp_info.libdirs = ["deeplib"]
''')
    artifact_package(client, tmp_path / 'live', 'live', files, body='''    def requirements(self):
        self.requires("deep/1.0", run=True)
''' + body)
    artifact_package(client, tmp_path / 'disabled', 'disabled', {'bin/disabled': 'not runtime'},
                     body='    package_type = "application"\n')
    artifact_package(client, tmp_path / 'tool', 'tool', {'bin/build-only': 'build context'},
                     body='    package_type = "application"\n')
    absent = recipe_file(tmp_path / 'editable', '    package_type = "application"\n',
                         name='unpackaged', version='1.0')
    cli_success(client, 'editable', 'add', absent.parent)
    consumer = recipe_file(tmp_path / 'consumer', '''    tool_requires = "tool/1.0"
    def requirements(self):
        self.requires("live/1.0", run=True)
        self.requires("disabled/1.0", run=False)
        self.requires("unpackaged/1.0", run=True)
''').parent
    destination = tmp_path / 'runtime'
    result = deployment_install(client, consumer, destination, '--deployer=runtime_deploy')
    assert deployed_tree(destination) == {
        'launch': files['executables/launch'].encode(),
        'plugins/helper': files['executables/plugins/helper'].encode(),
        'liborbit.so': b'shared artifact',
        'plugins/libextra.so.2': b'versioned shared artifact',
        'deep-tool': b'transitive executable',
        'second-tool': b'second location executable',
        'libsecond.so': b'second location shared',
        'libdeep.so': b'transitive shared'}
    warnings = [line for line in result.text('stderr').splitlines()
                if line.startswith('runtime_deploy: WARN:')]
    assert any('unpackaged/1.0' in line for line in warnings), result


def test_recipe_deployment_patterns_and_exclusion(tmp_path):
    client = recipe_client(tmp_path / 'client')
    artifact_package(client, tmp_path / 'leaf', 'leaf', {'leaf.txt': 'leaf delivery'}, deploy=True)
    artifact_package(client, tmp_path / 'top', 'top', {'top.txt': 'top delivery'},
                     body='    requires = "leaf/1.0"\n', deploy=True)
    consumer = recipe_file(tmp_path / 'consumer', '    requires = "top/1.0"\n').parent
    arms = [(('*',), {'leaf/leaf.txt': b'leaf delivery', 'top/top.txt': b'top delivery'}),
            (('top/*',), {'top/top.txt': b'top delivery'}),
            (('leaf/*', 'top/*'), {'leaf/leaf.txt': b'leaf delivery', 'top/top.txt': b'top delivery'}),
            (('unmatched/*',), {}),
            (('*', '!top/*'), {'leaf/leaf.txt': b'leaf delivery'}),
            (('!top/*', '*'), {'leaf/leaf.txt': b'leaf delivery'})]
    for index, (patterns, expected) in enumerate(arms):
        destination = tmp_path / ('delivery-' + str(index))
        deployment_install(client, consumer, destination,
                           *('--deployer-package=' + p for p in patterns))
        assert deployed_tree(destination) == expected


def test_cmake_consumer_uses_replacement_locations(tmp_path):
    client = recipe_client(tmp_path / 'client')
    compiled_usage_package(client, tmp_path / 'package')
    consumer = tmp_path / 'consumer'
    recipe_file(consumer, '    requires = "nativeusage/1.0"\n    settings = "os", "arch", "compiler", "build_type"\n')
    write_file(consumer / 'main.c', NATIVE_SOURCE)
    write_file(consumer / 'CMakeLists.txt', '''cmake_minimum_required(VERSION 3.23)
project(DeployedConsumer C)
find_package(nativeusage REQUIRED)
add_executable(app main.c)
target_link_libraries(app PRIVATE nativeusage::nativeusage)
''')
    deployer = graph_copy_deployer(tmp_path / 'relocate.py', relocate=True)
    destination = tmp_path / 'chosen artifacts'
    generated = tmp_path / 'generated'
    deployment_install(client, consumer, destination, '--deployer', deployer,
                       '-of', generated, '-g', 'CMakeDeps', '-g', 'CMakeToolchain', *CMAKE_SETTINGS)
    assert (destination / 'host/nativeusage/include/usage.h').read_bytes() == b'int usage(void);\n'
    cli_success(client, 'remove', 'nativeusage/*', '-c')
    build = tmp_path / 'build'
    cmake_command(client, consumer, '-S', str(consumer), '-B', str(build),
                  '-DCMAKE_TOOLCHAIN_FILE=' + str(generated / 'velmora_toolchain.cmake'),
                  '-DCMAKE_BUILD_TYPE=Release')
    cmake_command(client, consumer, '--build', str(build))
    assert native_command(client, consumer, str(build / 'app')).text('stdout') == '81\n'


def test_supplied_deployer_receives_actual_graph(tmp_path):
    client = recipe_client(tmp_path / 'client')
    artifact_package(client, tmp_path / 'leaf', 'leaf', {'leaf.txt': 'nested delivery'})
    artifact_package(client, tmp_path / 'top', 'top', {'top.txt': 'root delivery'},
                     body='    requires = "leaf/1.0"\n')
    deployer = graph_copy_deployer(tmp_path / 'deliver.py')
    # Every selected deployer runs, each seeing the graph of this install.
    names = write_file(tmp_path / 'names.py', '''import os

def deploy(graph, output_folder, **kwargs):
    deps = graph.root.velmorafile.dependencies.values()
    with open(os.path.join(output_folder, "names.list"), "w") as stream:
        stream.write(",".join(sorted(dep.ref.name for dep in deps)))
''')
    for index, reference in enumerate(('leaf/1.0', 'top/1.0')):
        destination = tmp_path / ('custom-' + str(index))
        deployment_install(client, '--requires=' + reference, destination, '--deployer', deployer,
                           '--deployer', names)
        expected = {'host/leaf/leaf.txt': b'nested delivery'}
        if index:
            expected['host/top/top.txt'] = b'root delivery'
        actual = deployed_tree(destination)
        assert actual['names.list'] == (b'leaf,top' if index else b'leaf')
        materials = {p: value for p, value in actual.items()
                     if Path(p).name in ('leaf.txt', 'top.txt')}
        assert materials == expected


def test_deployment_failures_report_affected_cause(tmp_path):
    client = recipe_client(tmp_path / 'client')
    artifact_package(client, tmp_path / 'package', 'item', {'item.txt': 'deployable bytes'})
    # A live successful arm demonstrates that the same package is deployable.
    good = tmp_path / 'good'
    deployment_install(client, '--requires=item/1.0', good, '--deployer=direct_deploy')
    assert [v for p, v in deployed_tree(good).items() if retains_relative_path(p, 'item.txt')] == [b'deployable bytes']
    missing = str(tmp_path / 'unavailable.py')
    result = cli_rejection(client, 'install', '--requires=item/1.0', '-nr', '--deployer', missing)
    assert missing in result.text('stderr'), result
    destination = tmp_path / 'forbidden'
    destination.mkdir()
    destination.chmod(0o555)
    try:
        result = cli_rejection(client, 'install', '--requires=item/1.0', '-nr',
                               '--deployer=direct_deploy', '--deployer-folder', destination)
        assert str(destination) in result.text('stderr'), result
        assert deployed_tree(destination) == {}
    finally:
        destination.chmod(0o755)
    failing = write_file(tmp_path / 'failing.py', '''def deploy(graph, output_folder, **kwargs):
    raise RuntimeError("deployment-policy-rejected")
''')
    result = cli_rejection(client, 'install', '--requires=item/1.0', '-nr', '--deployer', failing, status=7)
    assert 'deployment-policy-rejected' in result.text('stderr'), result
    broken = recipe_file(tmp_path / 'broken', '''    def deploy(self):
        raise RuntimeError("recipe-delivery-rejected")
''', name='broken', version='1.0')
    cli_success(client, 'create', broken.parent, '-nr')
    result = cli_rejection(client, 'install', '--requires=broken/1.0', '-nr', '--deployer-package=*')
    assert 'broken/1.0' in result.text('stderr'), result
    assert 'recipe-delivery-rejected' in result.text('stderr'), result
