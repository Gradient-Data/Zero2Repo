# feature: F13
"""Semantic declaration, lock and environment observations for maintenance."""
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

from _helpers import read_toml, snapshot_files
from F01_helpers import project_cli, succeeded
from F04_helpers import locked_by_name
from F11_helpers import installation_state


def maintenance_document(project):
    return read_toml(project / 'pyproject.toml')


def maintenance_requirements(entries):
    result = {}
    for entry in entries:
        requirement = Requirement(entry)
        name = canonicalize_name(requirement.name)
        assert name not in result, entries
        result[name] = requirement
    return result


def maintenance_lock(project):
    return locked_by_name(read_toml(project / 'velnora.lock').get('package', []))


def maintenance_versions(project):
    return {n: Version(p['version']) for n, p in maintenance_lock(project).items()}


def maintenance_files(project):
    return snapshot_files([project / 'pyproject.toml', project / 'velnora.lock'])


def maintenance_installed(project, env, expected, absent=()):
    observed = installation_state(project, env, expected)
    assert observed['values'] == {n: n + ':' + v for n, v in expected.items()}, observed
    for name, version in expected.items():
        assert Version(observed['installed'][name]) == Version(version), observed
    assert not set(absent) & observed['installed'].keys(), observed
    return observed['installed']


def maintenance_install(project, env):
    succeeded(project_cli(project, env, 'install', '--no-root'))
