# feature: F12
"""Package selection observations through public CLI JSON and recipe files."""
import json
import re
from pathlib import Path

from _helpers import read_bytes, write_file
from F01_helpers import cli_success
from F02_helpers import recipe_file
from F03_helpers import exported_reference
from F06_helpers import binary_recipe, create_binary


def selection(client, pattern=None, *args, operation='list'):
    return cli_success(client, operation, *((pattern,) if pattern is not None else ()),
                       '--format=json', *args).json('stdout')


def selected_artifacts(report, repository='Local Cache'):
    """Read complete identities; an error entry is never treated as absence."""
    result = set()
    recipes = report[repository]
    assert 'error' not in recipes, recipes
    for ref, recipe in recipes.items():
        for rrev, revision in recipe['revisions'].items():
            for pid, package in revision['packages'].items():
                for prev in package['revisions']:
                    result.add((ref, rrev, pid, prev))
    return result


def node_artifact(node):
    ref, rrev = node['ref'].split('#')
    return ref, rrev, node['package_id'], node['prev']


def saved_selection(path, report):
    return write_file(path, json.dumps(report))


def discovery_binary(client, root, *, name='parcel', version='1.0', marker='first',
                     build_type='Release', flavor='plain', material='first'):
    path = binary_recipe(root, f'    description = {marker!r}\n', name=name, version=version)
    return create_binary(client, path, '-s', 'build_type=' + build_type,
                         '-o', f'{name}/*:flavor={flavor}', name=name, material=material)


def export_versions(client, root, name, versions):
    for version in versions:
        path = recipe_file(Path(root) / name / version, '', name=name, version=version)
        exported_reference(client, path.parent)


def dependency_report(result, name, category=None, *, label='WARN:'):
    lines = [line for line in result.text('stderr').splitlines() if line.startswith(label)]
    assert any(all(re.search(r'(?<![\w])' + re.escape(value) + r'(?![\w])', line)
                   for value in ((name,) if category is None else (name, category))) for line in lines), result
