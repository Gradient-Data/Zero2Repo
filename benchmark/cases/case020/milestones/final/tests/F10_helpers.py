# feature: F10
"""Caller-owned source, production and consumer fixtures using public recipes."""
import hashlib
import io
from pathlib import Path
import tarfile
import zipfile

from _helpers import read_json, write_file
from F01_helpers import cli_success, cli_rejection, named_node
from F02_helpers import recipe_file
from F03_helpers import git_command


def production_failure(client, *args, cause=None, affected=None):
    result = cli_rejection(client, *args)
    diagnostic = result.text('stderr')
    if cause is not None:
        assert cause in diagnostic, result
    if affected is not None:
        assert affected in diagnostic, result
    return result


def source_recipe(root, body):
    return recipe_file(root, '''    def layout(self):
        self.folders.source = "selected-source"
    def source(self):
''' + body).parent


def archive_input(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    members = {'value.txt': b'copper\n', 'nested/keep.txt': b'unchanged\n'}
    with zipfile.ZipFile(root / 'sources.zip', 'w') as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    # The same members as a gzip-compressed tar archive, beside the zip archive.
    with tarfile.open(root / 'sources.tar.gz', 'w:gz') as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return root / 'sources.zip'


def digest_source(root, url, checks):
    return source_recipe(root, '''        from velmora.tools.files import download
        download(self, %r, "download.bin", retry=0, **%r)
''' % (url, checks))


def standard_digests(payload):
    return {name: hashlib.new(name, payload).hexdigest() for name in ('md5', 'sha1', 'sha256')}


def git_source_repository(root, env):
    root = Path(root)
    write_file(root / 'value.txt', 'first revision\n')
    git_command(root, env, 'init')
    git_command(root, env, 'add', '.')
    git_command(root, env, '-c', 'user.name=Acceptance', '-c', 'user.email=acceptance@example.invalid',
                'commit', '-m', 'First source revision')
    first = git_command(root, env, 'rev-parse', 'HEAD')
    git_command(root, env, 'tag', 'release-point')
    write_file(root / 'value.txt', 'second revision\n')
    git_command(root, env, 'add', '.')
    git_command(root, env, '-c', 'user.name=Acceptance', '-c', 'user.email=acceptance@example.invalid',
                'commit', '-m', 'Second source revision')
    git_command(root, env, 'branch', 'source-line')
    return first, git_command(root, env, 'rev-parse', 'HEAD')


PRODUCTION = '''    package_type = "static-library"
    settings = "os", "arch", "build_type"
    options = {"flavor": ["small", "large"]}
    default_options = {"flavor": "small"}
    def source(self):
        from velmora.tools.files import save
        save(self, "material.txt", "recipe source\\n")
    def build(self):
        import json, os
        from velmora.tools.files import load, save
        material = load(self, os.path.join(self.source_folder, "material.txt"))
        save(self, os.path.join(self.build_folder, "artifact.json"),
             json.dumps(dict(material=material, flavor=str(self.options.flavor),
                             build_type=str(self.settings.build_type))))
        save(self, os.path.join(self.build_folder, "unselected.txt"), "not packaged")
    def package(self):
        from velmora.tools.files import copy
        copy(self, "artifact.json", self.build_folder, self.package_folder)
'''


def production_recipe(root, *, name='produced', extra=''):
    return recipe_file(root, PRODUCTION + extra, name=name, version='1.0').parent


def create_production(client, root, *args):
    report = cli_success(client, 'create', root, '-nr', '--format=json', *args).json('stdout')
    return named_node(report, 'produced')


def consume_artifact(client, root, reference, *args):
    receipt = Path(root) / 'received.json'
    source = recipe_file(root, '''    def requirements(self):
        self.requires(%r)
    def generate(self):
        import os
        from velmora.tools.files import load, save
        dependency = self.dependencies["produced"]
        save(self, %r, load(self, os.path.join(dependency.package_folder, "artifact.json")))
''' % (reference, str(receipt)))
    report = cli_success(client, 'install', source.parent, '-nr', '--format=json', *args).json('stdout')
    return named_node(report, 'produced'), read_json(receipt)


def consumer_test_recipe(root, receipt, *, failure=None):
    build_body = '''        import os
        from velmora.tools.files import load, save
        dependency = self.dependencies["produced"]
        save(self, os.path.join(self.build_folder, "consumed.json"),
             load(self, os.path.join(dependency.package_folder, "artifact.json")))
'''
    if failure == 'build':
        build_body += '        raise RuntimeError("consumer-build-cause")\n'
    test_body = '''        import os
        from velmora.tools.files import load, save
        save(self, %r, load(self, os.path.join(self.build_folder, "consumed.json")))
''' % str(receipt)
    if failure == 'test':
        test_body += '        raise RuntimeError("consumer-test-cause")\n'
    # Both phases consume real package data; a test failure occurs after build succeeded.
    return recipe_file(root, '''    test_type = "explicit"
    def requirements(self):
        self.requires(self.tested_reference_str)
    def build(self):
''' + build_body + '    def test(self):\n' + test_body).parent
