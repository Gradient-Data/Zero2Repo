"""Build the local projects using their declared distribution identities."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib


def project_name(path):
    return tomllib.loads((path / 'pyproject.toml').read_text())['project']['name']


def build():
    versions = json.loads(Path(__file__).with_name('product-version.json').read_text())
    root = Path.cwd()
    root_name = project_name(root)
    projects = [(root, root_name, versions['version'])]
    environment = os.environ.copy()
    environment[versions['environment_variable']] = versions['version']
    candidates = [(path.parent, project_name(path.parent))
                  for path in sorted((root / 'packages').glob('*/pyproject.toml'))]
    for suffix, version in versions['independent_distributions'].items():
        expected_name = root_name + '-' + suffix
        matches = [path for path, name in candidates if name == expected_name]
        if len(matches) != 1:
            raise RuntimeError(f'Expected one local project named {expected_name!r}, found {len(matches)}')
        projects.append((matches[0], expected_name, version['version']))
    # Hatch's VCS backend may call setuptools-scm without a distribution name.
    # Build each project in its own subprocess so both SCM inputs are exact.
    for path, name, version in projects:
        environment[versions['environment_variable']] = version
        normalized = re.sub(r'[-_.]+', '_', name).upper()
        environment['SETUPTOOLS_SCM_PRETEND_VERSION_FOR_' + normalized] = version
        subprocess.run([
            sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps',
            '--no-build-isolation', '--no-cache-dir', '--upgrade', '--target',
            '.codingbench-site', str(path),
        ], env=environment, check=True)


if __name__ == '__main__':
    build()
