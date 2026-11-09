# feature: F15
"""Caller-owned maintenance artifacts and public cache observations."""
from pathlib import Path

from _helpers import PRODUCT_PYTHON, read_bytes, run, write_file
from F01_helpers import cli_success, named_node
from F02_helpers import recipe_file
from F06_helpers import binary_reference
from F12_helpers import selection, selected_artifacts


def maintenance_package(client, root, *, name='maintained', revision='one',
                        payload='package one', build_type='Release', url=None, digest=None):
    source = '' if url is None else f'''    def source(self):
        from velmora.tools.files import download
        download(self, {url!r}, "downloaded.txt", sha256={digest!r})
'''
    recipe = recipe_file(root, f'''    description = {revision!r}
    settings = "build_type"
    exports = "recipe-data.txt"
    exports_sources = "source.txt"
    def build(self):
        import os
        from velmora.tools.files import save
        save(self, os.path.join(self.build_folder, "built.txt"), "built material")
    def package(self):
        import os
        from velmora.tools.files import save, copy
        copy(self, "source.txt", self.source_folder, self.package_folder)
        save(self, os.path.join(self.package_folder, "payload.txt"), os.environ["F15_PAYLOAD"])
''' + source, name=name, version='1.0')
    write_file(recipe.parent / 'recipe-data.txt', name + ' recipe ' + revision)
    write_file(recipe.parent / 'source.txt', name + ' source ' + revision)
    client.env['F15_PAYLOAD'] = payload
    report = cli_success(client, 'create', recipe.parent, '-nr', '-s',
                         'build_type=' + build_type, '--format=json').json('stdout')
    return named_node(report, name)


def maintenance_inventory(client, remote=None):
    args = () if remote is None else ('-r', remote)
    return selected_artifacts(selection(client, '*#*:*#*', *args), remote or 'Local Cache')


def recipe_revisions(client, remote=None):
    """Every stored (recipe, recipe revision), including those with no binaries."""
    args = () if remote is None else ('-r', remote)
    recipes = selection(client, '*#*', *args)[remote or 'Local Cache']
    assert 'error' not in recipes, recipes
    return {(ref, rrev) for ref, recipe in recipes.items() for rrev in recipe.get('revisions', {})}


def maintenance_content(client, node, payload, revision='one'):
    assert read_bytes(client.cache_path(binary_reference(node)) / 'payload.txt') == payload.encode()
    assert read_bytes(client.cache_path(binary_reference(node)) / 'source.txt') == (
        node['name'] + ' source ' + revision).encode()
    assert read_bytes(client.cache_path(node['ref']) / 'recipe-data.txt') == (
        node['name'] + ' recipe ' + revision).encode()


def backup_source_files(client):
    """Consume the public cache API's list of backup file paths in full."""
    result = run((PRODUCT_PYTHON, '-c',
                  'import json; from velmora.api.velmora_api import VelmoraAPI; '
                  'print(json.dumps(VelmoraAPI().cache.get_backup_sources('
                  'exclude=False, only_upload=False)))'), cwd=client.cwd, env=client.env)
    assert result.returncode == 0, result
    return {Path(path): read_bytes(path) for path in result.json('stdout')}


def prepared_download_files(report, node, remote):
    ref, rev = node['ref'].split('#')
    bundle = report[remote][ref]['revisions'][rev]
    package = bundle['packages'][node['package_id']]['revisions'][node['prev']]
    return {Path(path) for files in (bundle['files'], package['files']) for path in files.values()}
