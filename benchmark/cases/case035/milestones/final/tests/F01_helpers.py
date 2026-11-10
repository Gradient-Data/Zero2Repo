# feature: F01
"""Real project setup and CLI observations for project-definition tests."""
import os
import re
import sys
from pathlib import Path

from packaging.utils import canonicalize_name

from F00_documents import legacy_document
from _helpers import make_environment, run_cli, read_zip, parse_metadata, parse_entry_points, read_toml


_SESSION_RUNTIME = None


def prepare_product_runtime(root, wheel_directory):
    """Build and install this candidate using only the image's offline artifacts."""
    from F12_helpers import shared_product_wheel

    root.mkdir(parents=True)
    env = make_environment(os.environ, remove=("VIRTUAL_ENV", "PYTHONPATH"),
        remove_prefixes=("VELNORA_", "PIP_"), updates={
            "PIP_CONFIG_FILE": os.devnull, "PIP_NO_INDEX": "1",
            "PIP_FIND_LINKS": "/opt/offline-wheels", "PIP_NO_CACHE_DIR": "1",
        })
    runtime = root / "runtime"
    succeeded(run_cli((sys.executable, "-m", "venv"), (str(runtime),), cwd=root, env=env))
    python = str(runtime / "bin" / "python")
    pip = (python, "-m", "pip")
    declaration = read_toml(Path('/app/pyproject.toml'))
    build_requirements = declaration["build-system"]["requires"]
    if build_requirements:
        succeeded(run_cli(pip, ("install", "--no-index", *build_requirements),
                          cwd=root, env=env, timeout=120))
    wheel = shared_product_wheel(wheel_directory, python, env)
    succeeded(run_cli(pip, ("install", "--no-index", str(wheel)),
                      cwd=root, env=env, timeout=120))
    succeeded(run_cli(pip, ("check",), cwd=root, env=env))
    version = succeeded(run_cli((python,), ("-c",
        "import importlib.metadata; print(importlib.metadata.version('velnora'))"),
        cwd=root, env=env)).stdout.strip()
    metadata, = (parse_metadata(data) for name, data in read_zip(wheel).items()
                 if name.endswith('.dist-info/METADATA'))
    assert version == metadata['Version'], (version, metadata['Version'])
    command = str(runtime / "bin" / "velnora")
    report = succeeded(run_cli((command,), ("--version",), cwd=root, env=env))
    assert report.stdout == f"Velnora (version {version})\n", report
    return {"python": python, "command": command, "wheel": wheel, "env": env}


def bind_product_runtime(runtime):
    global _SESSION_RUNTIME
    _SESSION_RUNTIME = runtime


def project_environment(root):
    if _SESSION_RUNTIME is None:
        raise RuntimeError("The pytest session has not prepared the candidate runtime")
    root.mkdir(parents=True, exist_ok=True)
    return make_environment(_SESSION_RUNTIME['env'], remove=("VIRTUAL_ENV", "PYTHONPATH"),
        remove_prefixes=("VELNORA_",), updates={
            "PYTHONPATH": "",
            "PATH": str(Path(_SESSION_RUNTIME['command']).parent) + os.pathsep + _SESSION_RUNTIME['env']['PATH'],
            "F01_PRODUCT_PYTHON": _SESSION_RUNTIME['python'],
            "F01_BUILD_PYTHON": _SESSION_RUNTIME['python'],
            "HOME": str(root / "home"),
            "VELNORA_CONFIG_DIR": str(root / "config"),
            "VELNORA_CACHE_DIR": str(root / "cache"),
            "VELNORA_VIRTUALENVS_IN_PROJECT": "true",
            "VELNORA_KEYRING_ENABLED": "false",
            "VELNORA_NO_INTERACTION": "1",
        })


def write_project(path, document, *, module="sample_project"):
    path.mkdir(parents=True, exist_ok=True)
    (path / "pyproject.toml").write_text(legacy_document(document), encoding="utf-8")
    (path / module).mkdir(exist_ok=True)
    (path / module / "__init__.py").write_text(
        'def main():\n    return 0\n', encoding="utf-8")
    return path


def project_cli(path, env, *args):
    return run_cli(("velnora",), ("--no-ansi", *args), cwd=path, env=env, timeout=120)


def succeeded(result):
    assert result.returncode == 0, (result.args, result.stdout, result.stderr)
    return result


def refused(result, *subjects, names=()):
    assert result.returncode == 1, (result.args, result.stdout, result.stderr)
    assert result.stderr.strip(), result
    for subject in subjects:
        assert subject.casefold() in result.stderr.casefold(), result.stderr
    for name in names:
        # A dependency diagnostic may retain its declared spelling or normalize it.
        spelling = r"[-_.]+".join(re.escape(part) for part in canonicalize_name(name).split("-"))
        assert re.search(r"(?<![A-Za-z0-9_-])" + spelling + r"(?![A-Za-z0-9_-]|\.[A-Za-z0-9_-])",
                         result.stderr, re.IGNORECASE), result.stderr
    return result


def wheel_observation(path, env):
    succeeded(project_cli(path, env, "build", "--format", "wheel"))
    wheels = list((path / "dist").glob("*.whl"))
    assert len(wheels) == 1, wheels
    members = read_zip(wheels[0])
    metadata_names = [name for name in members if name.endswith(".dist-info/METADATA")]
    assert len(metadata_names) == 1, metadata_names
    prefix = metadata_names[0].removesuffix("METADATA")
    entries = parse_entry_points(members[prefix + "entry_points.txt"].decode()) if prefix + "entry_points.txt" in members else {}
    return parse_metadata(members[metadata_names[0]]), entries, members


BUILD_SYSTEM = '''
[build-system]
requires = ["poetry-core>=2.0"]
build-backend = "poetry.core.masonry.api"
'''


def local_dependency(path):
    return write_project(path, '''[project]
name = "local-addon"
version = "1.4.0"
requires-python = ">=3.9"
''' + BUILD_SYSTEM, module="local_addon")
