# feature: F11
"""Installation scenarios and public build-plan observations."""
from pathlib import Path

from _helpers import read_json
from F01_helpers import cli_success, named_node
from F02_helpers import recipe_file
from F05_helpers import dependency_recipe, dependency_graph


INSTALL_PAYLOAD = '''    settings = "build_type"
    def build(self):
        import os, json
        from velmora.tools.files import save, load
        dependencies = {dep.ref.name: json.loads(load(self, os.path.join(dep.package_folder, "artifact.json")))
                        for dep in self.dependencies.values()}
        save(self, os.path.join(self.build_folder, "artifact.json"),
             json.dumps(dict(token=os.environ["F11_TOKEN"], configuration=str(self.settings.build_type),
                             dependencies=dependencies)))
    def package(self):
        from velmora.tools.files import copy
        copy(self, "artifact.json", self.build_folder, self.package_folder)
'''


def installation_package(client, root, name='item', *, body='', create=False, token='initial'):
    client.env['F11_TOKEN'] = token
    return dependency_recipe(client, root, name, body=body + INSTALL_PAYLOAD, create=create)


def installation_graph(client, reference='item/1.0', *args, install=False, local=True):
    return dependency_graph(client, None, '--requires=' + reference, *args, install=install, local=local)


def installed_artifact(report, name='item'):
    return read_json(Path(named_node(report, name)['package_folder']) / 'artifact.json')


def installation_chain(client, root, *, create=False):
    root = Path(root)
    installation_package(client, root / 'base', 'base', create=create)
    # Stable dependency identity isolates cascade policy from package-ID changes.
    installation_package(client, root / 'top', 'top', create=create, body='''    def requirements(self):
        self.requires("base/1.0", package_id_mode="unrelated_mode")
''')


def build_plan(client, *args, grouping='recipe', reduced=False, reference='top/1.0'):
    return cli_success(client, 'graph', 'build-order', '--requires=' + reference,
                       '-nr', '--build=missing', '--order-by=' + grouping, '--format=json',
                       *(('--reduce',) if reduced else ()), *args).json('stdout')


def plan_work(plan):
    """Flatten the documented two plan shapes without imposing same-level order."""
    rows = []
    for level, group in enumerate(plan['order']):
        for entry in group:
            if plan['order_by'] == 'recipe':
                for packages in entry['packages']:
                    for package in packages:
                        rows.append((level, entry['ref'], package))
            else:
                rows.append((level, entry['ref'], entry))
    return rows


def assert_chain_plan(plan, expected_names):
    rows = plan_work(plan)
    assert {ref.split('/')[0] for _, ref, _ in rows} == set(expected_names), plan
    # Each recipe (recipe grouping) or binary configuration (configuration grouping) is one entry.
    keys = [entry['ref' if plan['order_by'] == 'recipe' else 'pref'] for group in plan['order'] for entry in group]
    assert len(keys) == len(set(keys)), plan
    if {'base', 'top'} <= set(expected_names):
        levels = {ref.split('/')[0]: level for level, ref, _ in rows}
        assert levels['base'] < levels['top'], plan
        if plan['order_by'] == 'recipe':
            entries = {entry['ref'].split('/')[0]: entry for group in plan['order'] for entry in group}
            assert entries['base']['ref'] in entries['top']['depends'], plan
        else:
            entries = {row['ref'].split('/')[0]: row for group in plan['order'] for row in group}
            assert entries['base']['pref'] in entries['top']['depends'], plan
    for _, _, package in rows:
        assert package['package_id'], package
        if plan['reduced']:
            assert package['binary'] == 'Build', package
    return rows


def runnable_package(client, root, name, value, *, variable, build_tool=False):
    """An installed executable and declared environment consumed by real commands."""
    body = '''    package_type = "application"
    def package(self):
        import os
        from velmora.tools.files import save
        path = os.path.join(self.package_folder, "bin", "f11-command")
        save(self, path, %r)
        os.chmod(path, 0o755)
    def package_info(self):
        self.%s.define(%r, %r)
''' % ('#!/bin/sh\nprintf "%s\\n" ' + value + '\n', 'buildenv_info' if build_tool else 'runenv_info', variable, value)
    dependency_recipe(client, root, name, body=body, create=True)


def error_diagnostic(result):
    """The text of each ERROR: line together with its indented continuation lines."""
    kept, inside = [], False
    for line in result.text('stderr').splitlines():
        inside = line.startswith('ERROR:') or (inside and line[:1] in (' ', '\t'))
        if inside:
            kept.append(line)
    return '\n'.join(kept)


def reported_missing_configuration(result, reference):
    """Read the package-qualified warning's immediately following INI block."""
    import configparser
    lines = result.text('stderr').splitlines()
    markers = [index for index, line in enumerate(lines[:-1])
               if line.startswith(reference + ': WARN:') and lines[index + 1] == '[settings]']
    assert markers, result
    block = []
    for line in lines[markers[0] + 1:]:
        if not line:
            break
        block.append(line)
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string('\n'.join(block))
    return dict(parser['settings'])
