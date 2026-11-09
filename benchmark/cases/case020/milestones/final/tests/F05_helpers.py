# feature: F05
"""Dependency scenarios driven through recipe and command-line public entries."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from _helpers import write_file, read_json
from F01_helpers import cli_success, cli_rejection, named_node
from F02_helpers import recipe_file
from F03_helpers import exported_reference


def dependency_recipe(client, root, name, version='1.0', body='', *, create=False, qualifier=None):
    path = recipe_file(root, body or '    package_type = "static-library"\n', name=name, version=version)
    args = () if qualifier is None else ('--user', qualifier[0], '--channel', qualifier[1])
    reference = exported_reference(client, path.parent, *args)
    if create:
        cli_success(client, 'create', path.parent, '-nr', *args)
    return reference


def dependency_graph(client, path=None, *args, rejected=False, local=True, install=False):
    command = ('install',) if install else ('graph', 'info')
    invoke = cli_rejection if rejected else cli_success
    result = invoke(client, *command, *((str(path),) if path is not None else ()),
                    *(('-nr',) if local else ()), '--format=json', *args)
    return result.json('stdout')


def constraint_selection(client, root, versions, constraint, *, name='choice', args=(), rejected=False):
    for version in versions:
        dependency_recipe(client, Path(root) / version, name, version)
    return dependency_graph(client, None, '--requires=' + name + '/' + constraint,
                            *args, rejected=rejected)


def selected_version(report, name='choice', context='host'):
    return named_node(report, name, context)['version']


def dependency_edge(report, source, target, *, context='host', target_context=None):
    nodes = report['graph']['nodes']
    src = named_node(report, source, context) if source else next(
        n for n in nodes.values() if n['name'] is None and n['context'] == context)
    matches = [edge for key, edge in src['dependencies'].items()
               if nodes[str(key)]['name'] == target and
               nodes[str(key)]['context'] == (target_context or context)]
    assert len(matches) == 1, (source, target, matches)
    return matches[0]


def graph_failure(report, kind, requirement):
    error = report['graph']['error']
    assert error['type'] == kind, error
    if kind == 'conflict':
        assert error['name'] == requirement, error
    else:
        # Requirement identity is independent of an optional revision suffix.
        assert error['require']['ref'].partition('#')[0] == requirement.partition('#')[0], error
    return error


def usage_package(client, root, name, kind='static-library', body='', version='1.0'):
    return dependency_recipe(client, root, name, version,
        f'    package_type = {kind!r}\n    settings = "os", "arch", "build_type"\n' + body + '''    def package(self):
        import os
        from velmora.tools.files import save
        save(self, os.path.join(self.package_folder, "include", self.name + ".h"), self.name)
        save(self, os.path.join(self.package_folder, "bin", self.name + "-payload"), self.name)
    def package_info(self):
        self.cpp_info.includedirs = ["include"]
        self.cpp_info.libdirs = []
        self.cpp_info.bindirs = ["bin"]
        self.cpp_info.libs = [self.name + "_link.lib"]
''', create=True)


USAGE_OBSERVER = '''    settings = "os", "arch", "build_type"
    def generate(self):
        import json, os
        from velmora.tools.files import save
        from velmora.tools.env import VirtualRunEnv
        rows = []
        for requirement, dependency in self.dependencies.items():
            rows.append(dict(name=dependency.ref.name, version=str(dependency.ref.version),
                             build=requirement.build, test=requirement.test,
                             headers=requirement.headers, libs=requirement.libs,
                             run=requirement.run, visible=requirement.visible))
        with VirtualRunEnv(self).vars().apply():
            paths = os.environ.get("PATH", "").split(os.pathsep)
            payloads = {}
            for path in paths:
                if os.path.isdir(path):
                    for filename in os.listdir(path):
                        if filename.endswith("-payload"):
                            with open(os.path.join(path, filename)) as stream:
                                payloads[filename] = stream.read()
        save(self, os.path.join(self.generators_folder, "usage.json"),
             json.dumps(dict(dependencies=rows, payloads=payloads)))
'''


def usage_consumer(client, root, declarations, *args, name='observer', native=False):
    declarations += '    generators = "MSBuildDeps"\n' if native else ''
    path = recipe_file(root, declarations + USAGE_OBSERVER, name=name, version='1.0')
    report = dependency_graph(client, path.parent, '--build=missing', *args, install=True)
    return report, read_json(Path(root) / 'usage.json')


def usage_rows(observation):
    return {(r['name'], r['build']): r for r in observation['dependencies']}


def native_usage_fields(root, name):
    """Read the named MSBuild dependency variables using the XML namespace."""
    document = ET.parse(Path(root) / ('velmora_' + name + '_vars_release_x64.props'))
    fields = {}
    for suffix in ('IncludeDirectories', 'Libraries', 'BinaryDirectories'):
        elements = document.findall('.//{http://schemas.microsoft.com/developer/msbuild/2003}Velmora' + name + suffix)
        assert len(elements) == 1, (name, suffix)
        text = elements[0].text
        if text is None:
            fields[suffix] = []
        else:
            assert text.endswith(';'), (name, suffix, text)
            fields[suffix] = text[:-1].split(';')
    return fields
