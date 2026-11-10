# feature: F11
"""Installation fixtures and observations outside the project's source directory."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

from packaging.utils import canonicalize_name, parse_wheel_filename

from _helpers import make_environment, parse_json, run_cli, run_python
from F01_helpers import project_cli, succeeded
from F04_helpers import dependency_project
from F09_helpers import reported_environment


def installation_python(project, env):
    return reported_environment(project, env) / 'bin' / 'python'


def installation_probe(project, env, source):
    clean = make_environment(env, remove=('PYTHONPATH',))
    return parse_json(succeeded(run_python(str(installation_python(project, env)), source,
        cwd=project.parent, env=clean)).stdout)


def installation_state(project, env, names=()):
    source = '''import importlib, importlib.metadata as m, json
print(json.dumps({'installed': {d.metadata['Name']: d.version for d in m.distributions()},
    'values': {n: importlib.import_module(n.replace('-', '_')).value() for n in NAMES}}))
'''.replace('NAMES', repr(list(names)))
    result = installation_probe(project, env, source)
    result['installed'] = {canonicalize_name(k): v for k, v in result['installed'].items()}
    return result


def seed_installation(project, env, wheels):
    # pip is an independent fixture installer, not the operation being judged.
    succeeded(project_cli(project, env, 'env', 'use', sys.executable))
    locations = sorted({str(w.parent) for w in wheels})
    requirements = [str(name) + '==' + str(version)
                    for name, version, _, _ in (parse_wheel_filename(w.name) for w in wheels)]
    succeeded(run_cli((sys.executable, '-m', 'pip', '--python', str(installation_python(project, env))),
        ('install', '--no-index', '--no-deps', '--no-compile',
         *(arg for location in locations for arg in ('--find-links', location)), *requirements),
        cwd=project.parent, env=env, timeout=120))


def installation_clone(project, destination):
    return Path(shutil.copytree(project, destination,
        ignore=shutil.ignore_patterns('.venv', 'velnora.toml')))


def publish_source(index_root, artifact, name):
    target = index_root / 'files' / artifact.name
    shutil.copyfile(artifact, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    directory = index_root / 'simple' / canonicalize_name(name)
    directory.mkdir(parents=True, exist_ok=True)
    page = directory / 'index.html'
    previous = page.read_text() if page.exists() else ''
    page.write_text(previous + '\n<a href="/files/' + target.name + '#sha256=' + digest
                    + '">' + target.name + '</a>')
    return target


def install_failure(result, package):
    assert result.returncode == 1, result
    # Installer operation failures are reported on stdout, unlike command validation.
    assert result.stdout.strip() and package in result.stdout, result
    return result


def generated_dependency(path, index):
    project = dependency_project(path, index, name='generated-dependency')
    (project / 'sample_project').rename(project / 'generated_dependency')
    declaration = project / 'pyproject.toml'
    text = declaration.read_text().replace('requires = ["poetry-core>=2.0"]',
        'requires = ["poetry-core>=2.0", "build-seed>=1"]')
    text = text.replace('build-backend = "poetry.core.masonry.api"',
        'build-backend = "custom_backend"\nbackend-path = ["."]')
    declaration.write_text(text)
    (project / 'custom_backend.py').write_text('''from pathlib import Path
from poetry.core.masonry import api

def get_requires_for_build_wheel(config_settings=None):
    return ["build-extra>=1"]

def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    import build_seed, build_extra
    settings = config_settings or {}
    if settings.get("fail"):
        raise RuntimeError("Requested dependency build failure")
    values = [build_seed.value(), build_extra.value(), settings.get("flavour")]
    Path("generated_dependency/__init__.py").write_text("def value():\\n    return " + repr(values) + "\\n")
    return api.build_wheel(wheel_directory, config_settings, metadata_directory)
''')
    return project
