# feature: F14
"""Caller-owned deployment inputs and direct filesystem observations."""
from pathlib import Path

from _helpers import write_file
from F01_helpers import cli_success
from F02_helpers import recipe_file


def artifact_package(client, root, name, files, *, body='', deploy=False):
    source = '''    def package(self):
        import os
        from velmora.tools.files import save
        for path, content in %r.items():
            save(self, os.path.join(self.package_folder, path), content)
''' % files
    if deploy:
        source += f'''    def deploy(self):
        import os
        from velmora.tools.files import copy
        for path in {list(files)!r}:
            copy(self, path, self.package_folder, os.path.join(self.deploy_folder, str(self.name)))
'''
    path = recipe_file(root, body + source, name=name, version='1.0')
    cli_success(client, 'create', path.parent, '-nr')
    return path


def deployment_install(client, consumer, destination, *args):
    return cli_success(client, 'install', consumer, '-nr', '--deployer-folder', destination, *args)


def deployed_tree(root):
    root = Path(root)
    assert root.is_dir(), root
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def retains_relative_path(path, relative):
    """Accept package material at the destination root or below a package directory."""
    return path == relative or path.endswith("/" + relative)


def graph_copy_deployer(path, *, relocate=False):
    return write_file(path, '''import os, shutil

def deploy(graph, output_folder, **kwargs):
    for dep in graph.root.velmorafile.dependencies.values():
        if dep.package_folder is None:
            continue
        target = os.path.join(output_folder, dep.context, dep.ref.name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copytree(dep.package_folder, target)
''' + ('        dep.set_deploy_folder(target)\n' if relocate else ''))
