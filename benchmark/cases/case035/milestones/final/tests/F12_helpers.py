# feature: F12
"""Real project-plugin packages and public command observations."""
from F00_documents import legacy_document
import json
from contextlib import contextmanager
import hashlib
import shutil
from pathlib import Path
import os
import sys
import traceback

from filelock import FileLock

from packaging.utils import canonicalize_name

from _helpers import make_environment, parse_json, run_cli, snapshot_installed
from F01_helpers import BUILD_SYSTEM, project_cli, project_environment, succeeded, write_project
from F02_helpers import APPLICATION_EXTENSION, installed_plugin
from F05_helpers import source_project
from F04_helpers import distribution_index


def provisioning_source(version):
    return APPLICATION_EXTENSION.replace('"total": sum(values)',
        '"release": ' + repr(version) + ', "total": sum(values) * ' + str(int(version.split('.')[0])))


def provisioning_wheel(root, env, version, *, dependencies=(),
                       name="acceptance-extension", command="extension-count"):
    module = canonicalize_name(name).replace("-", "_")
    project = write_project(root, '[project]\nname=' + json.dumps(name) + '\nversion='
        + json.dumps(version) + '\nrequires-python=">=3.9"\ndependencies='
        + json.dumps(list(dependencies)) + '\n[project.entry-points."velnora.application.plugin"]\n'
        'acceptance="' + module + ':Extension"\n' + BUILD_SYSTEM,
        module=module)
    (project / module / '__init__.py').write_text(
        provisioning_source(version).replace('extension-count', command))
    succeeded(project_cli(project, env, '--no-plugins', 'build', '--format', 'wheel'))
    wheel, = (project / 'dist').glob('*.whl')
    return wheel


def global_extension(root, env):
    root.mkdir()
    return installed_plugin(root, env, provisioning_source('1.0.0'),
                            group='velnora.application.plugin')


def provisioning_project(path, url, requirements):
    project = source_project(path, [('plugins', url + '/simple/', 'primary')])
    with (project / 'pyproject.toml').open('a') as stream:
        stream.write(legacy_document('\n[tool.<legacy>.requires-plugins]\n' + requirements + '\n'))
    return project


def plugin_contribution(project, env, version):
    input_path = project.parent / (project.name + '-values.json')
    active = make_environment(env, updates={'ACCEPTANCE_INPUT': str(input_path)})
    for values in ([6, -4, 9], [2, 15]):
        input_path.write_text(json.dumps(values))
        result = succeeded(project_cli(project, active, 'extension-count'))
        assert parse_json(result.stdout) == {'release': version,
            'total': sum(values) * int(version.split('.')[0]), 'count': len(values)}


def runtime_inventory(project, env):
    records = snapshot_installed(env['F12_RUNTIME_PYTHON'], cwd=project.parent, env=env)
    return sorted((d['name'], d['version']) for d in records)


def shared_product_wheel(directory, build_python, env):
    """Publish one completed current-run build for all concurrent consumers.

    The caller supplies a fresh pytest-session directory, shared by xdist
    workers. /app and the build interpreter are immutable for that session.
    Only the wheel is shared, never an installed environment or product cache.
    A failed builder leaves its original traceback for every waiting consumer.
    """
    directory.mkdir(parents=True, exist_ok=True)
    with FileLock(str(directory / 'build.lock')):
        completed = directory / 'completed.json'
        failed = directory / 'failed.txt'
        if failed.exists():
            raise AssertionError('Current-run product build failed:\n' + failed.read_text())
        if not completed.exists():
            try:
                wheels = directory / 'wheels'
                wheels.mkdir()
                succeeded(run_cli((build_python, '-m', 'pip'),
                    ('wheel', '--no-index', '--no-deps', '--no-build-isolation',
                     '--wheel-dir', str(wheels), '/app'),
                    cwd=directory, env=env, timeout=120))
                wheel, = wheels.glob('*.whl')
                wheel.chmod(0o444)
                pending = directory / 'completed.tmp'
                pending.write_text(json.dumps({'filename': wheel.name,
                    'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest()}))
                pending.replace(completed)
            except Exception:
                failed.write_text(traceback.format_exc())
                raise
        record = json.loads(completed.read_text())
        wheel = directory / 'wheels' / record['filename']
        assert hashlib.sha256(wheel.read_bytes()).hexdigest() == record['sha256'], wheel
        return wheel


def provisioning_environment(root, product_wheel):
    """Run the real product source with its dependencies in a clean offline runtime.

    The image's unrelated Conda distributions contain unavailable build origins;
    they must not become pinned dependencies of a project-plugin installation.
    """
    env = project_environment(root)
    runtime = root / 'tool-runtime'
    succeeded(run_cli((env['F01_BUILD_PYTHON'], '-m', 'venv'), ('--without-pip', str(runtime)),
                      cwd=root, env=env))
    python = runtime / 'bin' / 'python'
    pip = (env['F01_BUILD_PYTHON'], '-m', 'pip', '--python', str(python))
    options = ('install', '--no-index', '--find-links', '/opt/offline-wheels')
    wheels = root / 'runtime-wheels'
    wheels.mkdir()
    # A private repository copy preserves callers' existing layout; installed
    # files, entry points, configuration and caches remain independent.
    shutil.copyfile(product_wheel, wheels / product_wheel.name)
    succeeded(run_cli(pip, (*options, '--find-links', str(wheels),
        str(wheels / product_wheel.name)), cwd=root, env=env, timeout=120))
    return make_environment(env, updates={'PATH': str(runtime / 'bin') + os.pathsep + env['PATH'],
                                         'F12_RUNTIME_PYTHON': str(python),
                                         'F01_PRODUCT_PYTHON': str(python)})


def provisioning_artifacts(root, env, wheels):
    """Supply genuine runtime releases, including foreign-platform metadata."""
    artifacts = [*wheels, *(root / 'runtime-wheels').glob('*.whl'),
                 *Path('/opt/offline-wheels').glob('*.whl')]
    assets = Path(__file__).with_name('F12_assets')
    destination = root / 'foreign-releases'
    destination.mkdir()
    for record in json.loads((assets / 'F12_manifest.json').read_text()):
        source = assets / record['asset']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == record['sha256']
        artifact = destination / record['filename']
        shutil.copyfile(source, artifact)
        artifacts.append(artifact)
    return artifacts


@contextmanager
def provisioning_repository(root, env, wheels):
    artifacts = provisioning_artifacts(root, env, wheels)
    index = root / 'index'
    with distribution_index(index, artifacts) as url:
        yield url
