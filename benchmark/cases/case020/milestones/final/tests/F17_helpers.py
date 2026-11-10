# feature: F17
"""Workspace bindings and real file-transforming development packages."""
from pathlib import Path

from _helpers import Client, write_file
from F01_helpers import cli_success
from F02_helpers import recipe_file


def workspace_client(client, folder):
    Path(folder).mkdir(parents=True, exist_ok=True)
    return Client(client.command, folder, client.env)


def workspace_members(client):
    return cli_success(client, 'workspace', 'info', '--format=json').json('stdout')


def workspace_paths(client):
    info = workspace_members(client)
    return {str((Path(info['folder']) / item['path']).resolve()): item
            for item in info['packages']}


def workspace_add_members(client, *folders):
    for folder in folders:
        cli_success(client, 'workspace', 'add', folder, '-nr')


def text_development_package(root, name, text, *, requires=(), version='1.0', extra=''):
    """A package whose build combines real source and dependency file contents."""
    root = Path(root)
    recipe_file(root, '''    exports_sources = "input.txt"
    requires = %r
    def layout(self):
        self.folders.build = "products"
        self.folders.generators = "integration"
        self.cpp.build.resdirs = ["."]
    def source(self):
        import os
        from velmora.tools.files import load, save
        save(self, os.path.join(self.source_folder, "source.txt"),
             load(self, os.path.join(self.source_folder, "input.txt")))
    def generate(self):
        import os, json
        from velmora.tools.files import save
        save(self, os.path.join(self.generators_folder, "dependencies.json"),
             json.dumps({dep.ref.name: str(dep.ref.version) for dep in self.dependencies.direct_host.values()}))
    def build(self):
        import os
        from velmora.tools.files import load, save
        result = load(self, os.path.join(self.source_folder, "source.txt"))
        for dep in self.dependencies.direct_host.values():
            result += load(self, os.path.join(dep.cpp_info.resdirs[0], "built.txt"))
        save(self, os.path.join(self.build_folder, "built.txt"), result)
    def package(self):
        from velmora.tools.files import copy
        copy(self, "built.txt", self.build_folder, self.package_folder)
    def package_info(self):
        self.cpp_info.resdirs = ["."]
''' % (tuple(requires),) + extra, name=name, version=version)
    write_file(root / 'input.txt', text)
    return root
