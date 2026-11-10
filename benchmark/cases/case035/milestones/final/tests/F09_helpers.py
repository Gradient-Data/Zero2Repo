# feature: F09
"""Project environment scenarios and independent interpreter observations."""
import json
from pathlib import Path
import sys

from _helpers import make_environment, parse_json, run_python
from F01_helpers import project_cli, succeeded, write_project
from F03_helpers import configuration_environment, save_setting


ENVIRONMENT_PROBE = '''import importlib.metadata as m, importlib.util, json, platform, sys
print(json.dumps({"prefix": sys.prefix, "base_prefix": sys.base_prefix,
    "executable": sys.executable, "version": platform.python_version(),
    "implementation": platform.python_implementation(),
    "packages": {d.metadata["Name"].lower(): d.version for d in m.distributions()},
    "packaging_importable": importlib.util.find_spec("packaging") is not None}))
'''


def environment_project(path, requirement=">=3.9"):
    return write_project(path, '[project]\nname = "environment-subject"\nversion = "1.0"\n'
        f'requires-python = {json.dumps(requirement)}\n[tool.<legacy>]\npackage-mode = false\n')


def environment_settings(root):
    root.mkdir(parents=True, exist_ok=True)
    env = make_environment(configuration_environment(root / "settings"),
        remove=("CONDA_PREFIX", "CONDA_DEFAULT_ENV", "CONDA_SHLVL"))
    storage = root / "shared environments"
    save_setting(root, env, "virtualenvs.path", str(storage))
    return env, storage


def project_observation(path, env):
    return parse_json(succeeded(project_cli(path, env, "run", "python", "-B", "-c",
                                           ENVIRONMENT_PROBE)).stdout)


def direct_observation(executable, path, env):
    return parse_json(succeeded(run_python(str(executable), ENVIRONMENT_PROBE,
                                          cwd=path, env=env)).stdout)


def reported_environment(path, env):
    result = succeeded(project_cli(path, env, "env", "info", "--path"))
    value = Path(result.stdout.strip())
    assert value.is_absolute(), result
    return value


def external_environment(path, env, executable=sys.executable):
    succeeded(run_python(str(executable), 'import sys, venv; venv.create(sys.argv[1], with_pip=False)',
                         (str(path),), cwd=path.parent, env=env))
    return path


def with_external(env, path):
    return make_environment(env, updates={"VIRTUAL_ENV": str(path),
                                         "PATH": str(path / "bin") + ":" + env["PATH"]})


def environment_listing(path, env):
    lines = succeeded(project_cli(path, env, "env", "list", "--full-path")).stdout.splitlines()
    rows = {}
    for line in lines:
        selected = line.endswith(" (Activated)")
        value = line.removesuffix(" (Activated)") if selected else line
        location = Path(value)
        assert location.is_absolute() and location not in rows, lines
        rows[location] = selected
    return rows


def environment_report(path, env):
    text = succeeded(project_cli(path, env, "env", "info")).stdout
    section = None
    sections = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        if line in ("Virtualenv", "Base"):
            section = line
            sections[section] = {}
        else:
            label, separator, value = line.partition(":")
            assert section is not None and separator, text
            assert label not in sections[section], text
            sections[section][label] = value.strip()
    return sections


def activation_shells(root, env):
    """Extract genuine offline shell distributions without installing system files."""
    import hashlib
    import tarfile
    from _helpers import run_cli
    assets = Path(__file__).with_name('F09_assets')
    root.mkdir()
    for record in json.loads((assets / 'F09_manifest.json').read_text()):
        artifact = assets / record['asset']
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == record['sha256']
        succeeded(run_cli(('dpkg-deb',), ('-x', str(artifact), str(root)), cwd=root, env=env))
    for shell in ('nu', 'pwsh'):
        record = json.loads((assets / ('F09_' + shell + '_manifest.json')).read_text())
        artifact = assets / record['asset']
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == record['sha256']
        with tarfile.open(artifact) as archive:
            archive.extractall(root, filter='data')
    csh = root / 'bin/csh'
    csh.symlink_to(next(root.rglob('bsd-csh')))
    binaries = {name: next(path for path in root.rglob(name) if path.is_file())
                for name in ('zsh', 'mksh', 'csh', 'tcsh', 'fish', 'nu', 'pwsh')}
    binaries['pwsh'].chmod(binaries['pwsh'].stat().st_mode | 0o100)
    active = make_environment(env, updates={'DOTNET_SYSTEM_GLOBALIZATION_INVARIANT': '1', 'LD_LIBRARY_PATH': str(root / 'usr/lib/x86_64-linux-gnu') + ':' + str(root / 'lib/x86_64-linux-gnu')})
    return binaries, active
