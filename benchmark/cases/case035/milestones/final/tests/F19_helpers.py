# feature: F19
"""Disposable real runtimes, local releases and direct runtime observations."""
from F00_documents import legacy_document
from contextlib import contextmanager
import json
from pathlib import Path
import re

from packaging.utils import canonicalize_name
from F00_reports import operation_lines
from _helpers import make_environment, parse_json, read_toml, run_cli, run_python, snapshot_installed
from F01_helpers import project_cli, succeeded
from F04_helpers import DistributionFactory, dependency_project, locked_by_name
from F06_helpers import applicable_records
from packaging.markers import default_environment
from F12_helpers import (provisioning_environment, provisioning_repository,
                         provisioning_wheel)


@contextmanager
def managed_runtime(root, product_wheel, extra_wheels=()):
    root.mkdir()
    env = provisioning_environment(root, product_wheel)
    # Execute the installed distribution, including after a real self update.
    env = make_environment(env, remove=('PYTHONPATH',), updates={'PYTHONDONTWRITEBYTECODE': '1'})
    factory = DistributionFactory(root / 'packages')
    wheels = [factory.create('runtime-leaf')[1],
              factory.create('runtime-extra')[1],
              factory.create('runtime-conflict', dependencies=['velnora<1'])[1]]
    wheels += [provisioning_wheel(root / ('plugin-' + v), factory.env, v,
                  dependencies=['runtime-leaf==1.0'],
                  name='runtime-extension') for v in ('1.0.0', '2.0.0')]
    with provisioning_repository(root, env, [*wheels, *extra_wheels]) as url:
        project = dependency_project(root / 'project', 'http://127.0.0.1:1',
                                     standard=['project-only==9.0'])
        succeeded(project_cli(project, env, 'self', 'show', 'plugins'))
        declaration = Path(env['VELNORA_CONFIG_DIR']) / 'pyproject.toml'
        declaration.parent.mkdir(parents=True, exist_ok=True)
        with declaration.open('a') as stream:
            stream.write(legacy_document('\n[[tool.<legacy>.source]]\nname="runtime"\nurl='
                         + json.dumps(url + '/simple/') + '\npriority="primary"\n'))
        yield project, env, declaration.parent, wheels


def self_cli(project, env, *args):
    return project_cli(project, env, 'self', *args)


def runtime_packages(project, env, names=()):
    records = snapshot_installed(env['F12_RUNTIME_PYTHON'], cwd=project, env=env)
    versions = {canonicalize_name(r['name']): r['version'] for r in records}
    source = '''import importlib, json, sys
print(json.dumps({n: importlib.import_module(n.replace('-', '_')).value()
                  for n in json.loads(sys.argv[1])}))'''
    values = parse_json(succeeded(run_python(env['F12_RUNTIME_PYTHON'], source,
        (json.dumps(list(names)),), cwd=project, env=env)).stdout)
    return versions, values


def runtime_lock(directory):
    return locked_by_name(read_toml(directory / 'velnora.lock')['package'])


def active_runtime_lock(directory):
    records = list(runtime_lock(directory).values())
    python = default_environment()['python_version']
    return {**applicable_records(records, python=python),
            **applicable_records(records, python=python, group='additional')}


def runtime_rows(project, env, *options):
    rows = parse_json(succeeded(self_cli(project, env, 'show', '--format=json', *options)).stdout)
    result = {canonicalize_name(r['name']): r for r in rows}
    assert len(result) == len(rows), rows
    return result


def plugin_records(text):
    """Read package heading records and their labeled dependency blocks."""
    records = {}
    current = None
    dependencies = False
    for line in text.splitlines():
        if not line.strip():
            continue
        heading = re.fullmatch(r'  - (\S+) \(([^)]+)\)(?: .*)?', line)
        if heading:
            current = canonicalize_name(heading[1])
            assert current not in records, text
            records[current] = {'version': heading[2], 'requirements': {}}
            dependencies = False
        elif line == '      Dependencies':
            assert current is not None, text
            dependencies = True
        elif dependencies:
            requirement = re.fullmatch(r'        - (\S+) \(([^)]+)\)', line)
            assert requirement, text
            records[current]['requirements'][canonicalize_name(requirement[1])] = requirement[2]
        else:
            assert current is not None, text
            assert re.fullmatch(r'\s+\d+ (?:application )?plugins?(?: and \d+ application plugins?)?', line), text
    return records


def fixture_pip(project, env, *arguments):
    # Independent setup only; never used for the self operation under test.
    import sys
    return succeeded(run_cli((sys.executable, '-m', 'pip', '--python', env['F12_RUNTIME_PYTHON']),
        arguments, cwd=project, env=env, timeout=120))


def published_runtime_releases(root):
    import hashlib
    import shutil
    assets = Path(__file__).with_name('F19_assets')
    root.mkdir()
    wheels = []
    for row in json.loads((assets / 'F19_manifest.json').read_text()):
        source = assets / row['asset']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == row['sha256']
        target = root / row['filename']
        shutil.copyfile(source, target)
        wheels.append(target)
    return wheels


def installed_release(project, env):
    source = '''import hashlib, importlib.metadata as m, json
p = m.distribution('velnora')
print(json.dumps({'version': p.version, 'requirements': p.requires,
    'files': {str(f): hashlib.sha256(p.locate_file(f).read_bytes()).hexdigest()
              for f in p.files if str(f).startswith('velnora/') and str(f).endswith('.py')}}))'''
    return parse_json(succeeded(run_python(env['F12_RUNTIME_PYTHON'], source,
                                          cwd=project, env=env)).stdout)
