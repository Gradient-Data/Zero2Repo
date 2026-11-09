# feature: F06
"""Binary scenarios through public recipes, CLI JSON and located package files."""
from pathlib import Path

from _helpers import read_bytes
from F01_helpers import cli_success, named_node
from F02_helpers import recipe_file
from F05_helpers import dependency_graph


BINARY_CONFIG = '''    settings = "os", "arch", "build_type"
    options = {"flavor": ["plain", "rich", "extra"]}
    default_options = {"flavor": "plain"}
'''
BINARY_PAYLOAD = '''    def package(self):
        import os, json
        from velmora.tools.files import save
        save(self, os.path.join(self.package_folder, "payload.json"),
             json.dumps(dict(os=str(self.settings.get_safe("os")),
                             flavor=str(self.options.get_safe("flavor")),
                             material=os.environ["F06_MATERIAL"]), sort_keys=True))
'''


def binary_recipe(root, body='', *, name='binary', version='1.0', kind='static-library', config=True):
    return recipe_file(root, f'    package_type = {kind!r}\n' +
                       (BINARY_CONFIG if config else '') + body + BINARY_PAYLOAD,
                       name=name, version=version).parent


def create_binary(client, path, *args, name='binary', material='original'):
    client.env['F06_MATERIAL'] = material
    report = cli_success(client, 'create', path, '-nr', '--format=json', *args).json('stdout')
    return named_node(report, name)


def binary_node(client, path=None, *args, name='binary', install=False):
    return named_node(dependency_graph(client, path, *args, install=install), name)


def binary_payload(node):
    import json
    return json.loads(read_bytes(Path(node['package_folder']) / 'payload.json'))


def consumer_identity(client, root, reference, *, mode=None, kind='unknown', traits='', extra='', args=()):
    mode_arg = '' if mode is None else f', package_id_mode={mode!r}'
    path = recipe_file(root, f'''    package_type = {kind!r}
    def requirements(self):
        self.requires({reference!r}{mode_arg}{traits})
''' + extra, name='consumer', version='1.0').parent
    return binary_node(client, path, *args, name='consumer')['package_id']


def binary_reference(node):
    return f"{node['ref']}:{node['package_id']}#{node['prev']}"


def explained_packages(client, reference, *args):
    report = cli_success(client, 'graph', 'explain', '--requires=' + reference,
                         '-nr', '--format=json', *args).json('stdout')
    return report['closest_binaries'][reference]['revisions']
