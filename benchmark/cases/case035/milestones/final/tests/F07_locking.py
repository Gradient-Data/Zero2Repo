# feature: F07
"""Durable resolutions observed through locking, checking and real installation."""
import hashlib
import json
import shutil
from urllib.parse import unquote, urlsplit

from packaging.utils import canonicalize_name
from packaging.version import Version
from packaging.requirements import Requirement
from tomlkit import dumps

from _helpers import read_toml
from F01_helpers import project_cli, project_environment, refused, succeeded
from F04_helpers import (DistributionFactory, dependency_project, dependency_lock,
                         distribution_index, git_command, installed_values, locked_by_name)
from F06_helpers import applicable_records


def test_lock_records_solution_without_installing_and_pins_git(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    origin, _ = factory.create('fixed-origin', '1.0')
    env = project_environment(tmp_path / 'env')
    for args in [('init', '--initial-branch=main'), ('config', 'user.name', 'Acceptance'),
                 ('config', 'user.email', 'acceptance@example.invalid'),
                 ('add', 'pyproject.toml', 'fixed_origin'), ('commit', '-m', 'Initial package')]:
        git_command(origin, env, *args)
    commit = git_command(origin, env, 'rev-parse', 'HEAD')
    origin_url = 'file://localhost' + str(origin)
    wheels = [factory.create('conditional-leaf', v)[1] for v in ('1.0', '2.0')]
    wheels += [factory.create('extra-leaf')[1], factory.create('audit-leaf')[1]]
    wheels += [factory.create('record-root', dependencies=[
        'conditional-leaf==1.0; python_version < "3.10"',
        'conditional-leaf==2.0; python_version >= "3.10"'],
        extras={'fast': ['extra-leaf==1.0']})[1]]
    with distribution_index(tmp_path / 'index', wheels) as url:
        path = dependency_project(tmp_path / 'project', url, standard=['record-root[fast]==1.0', 'fixed-origin==1.0'],
            legacy='fixed-origin={git=' + json.dumps(origin_url) + ',branch="main"}', extra='''
[tool.<legacy>.group.audit]
optional=true
[tool.<legacy>.group.audit.dependencies]
audit-leaf="1.0"
''')
        before = installed_values(path, env, [])['installed']
        records = dependency_lock(path, env)
        assert installed_values(path, env, [])['installed'] == before
        assert not {'fixed-origin', 'record-root', 'conditional-leaf', 'extra-leaf', 'audit-leaf'} & before.keys()
        for python, version in [('3.9', '1.0'), ('3.13', '2.0')]:
            selected = applicable_records(records, python=python)
            assert set(selected) == {'fixed-origin', 'record-root', 'conditional-leaf', 'extra-leaf'}
            assert Version(selected['conditional-leaf']['version']) == Version(version)
            assert {'conditional-leaf', 'extra-leaf'} == {canonicalize_name(n) for n in selected['record-root']['dependencies']}
            for name in ('fixed-origin', 'record-root', 'extra-leaf'):
                assert Version(selected[name]['version']) == Version('1.0')
            assert {canonicalize_name(Requirement(r).name) for r in selected['record-root']['extras']['fast']} == {'extra-leaf'}
            assert selected['record-root']['source']['reference'] == 'acceptance'
            assert selected['record-root']['source']['url'].rstrip('/') == url + '/simple'
        audit = applicable_records(records, python='3.11', group='audit')
        assert set(audit) == {'audit-leaf'}
        assert Version(audit['audit-leaf']['version']) == Version('1.0')
        git = next(r for r in records if canonicalize_name(r['name']) == 'fixed-origin')['source']
        assert git['type'] == 'git'
        location = urlsplit(git['url'])
        assert location.scheme == 'file' and location.netloc in ('', 'localhost')
        assert unquote(location.path) == str(origin)
        assert git['reference'] == 'main'
        assert git['resolved_reference'] == commit
        (origin / 'fixed_origin' / '__init__.py').write_text('def value():\n    return "moved branch"\n')
        git_command(origin, env, 'add', 'fixed_origin')
        git_command(origin, env, 'commit', '-m', 'Move branch')
        assert git_command(origin, env, 'rev-parse', 'HEAD') != commit
        installation = tmp_path / 'installation'
        shutil.copytree(path, installation, ignore=shutil.ignore_patterns('.venv'))
        installation_env = project_environment(tmp_path / 'installation-environment')
        succeeded(project_cli(installation, installation_env, 'install', '--no-root'))
        observation = installed_values(installation, installation_env, ['fixed-origin', 'record-root', 'extra-leaf'])
        assert observation['values'] == {n: n + ':1.0' for n in ('fixed-origin', 'record-root', 'extra-leaf')}


def test_refresh_preserves_compatible_releases_and_regeneration_resolves_fresh(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    wheels = [factory.create('retained-release', v)[1] for v in ('1.0', '2.0')]
    wheels += [factory.create('added-release')[1]]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', wheels) as url:
        path = dependency_project(tmp_path / 'project', url, standard=['retained-release==1.0'])
        assert Version(locked_by_name(dependency_lock(path, env))['retained-release']['version']) == Version('1.0')
        declaration = path / 'pyproject.toml'
        declaration.write_text(declaration.read_text().replace('retained-release==1.0', 'retained-release>=1').replace(
            'dependencies=["retained-release>=1"]', 'dependencies=["retained-release>=1", "added-release==1.0"]'))
        refreshed = locked_by_name(dependency_lock(path, env))
        assert set(refreshed) == {'retained-release', 'added-release'}
        assert Version(refreshed['retained-release']['version']) == Version('1.0')
        assert Version(refreshed['added-release']['version']) == Version('1.0')
        succeeded(project_cli(path, env, 'lock', '--regenerate'))
        regenerated = locked_by_name(read_toml(path / 'velnora.lock')['package'])
        assert set(regenerated) == {'retained-release', 'added-release'}
        assert Version(regenerated['retained-release']['version']) == Version('2.0')
        declaration.write_text(declaration.read_text().replace('retained-release>=1', 'retained-release<2'))
        assert Version(locked_by_name(dependency_lock(path, env))['retained-release']['version']) == Version('1.0')


def test_directory_refresh_rereads_requirements_at_same_version(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    directory, _ = factory.create('changing-directory', dependencies=['old-leaf==1.0'])
    wheels = [factory.create(n)[1] for n in ('old-leaf', 'new-leaf')]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', wheels) as url:
        path = dependency_project(tmp_path / 'project', url,
            legacy='changing-directory={path=' + json.dumps(str(directory)) + '}')
        old = locked_by_name(dependency_lock(path, env))
        assert set(old) == {'changing-directory', 'old-leaf'}
        assert set(old['changing-directory']['dependencies']) == {'old-leaf'}
        declaration = directory / 'pyproject.toml'
        declaration.write_text(declaration.read_text().replace('old-leaf', 'new-leaf'))
        new = locked_by_name(dependency_lock(path, env))
        assert set(new) == {'changing-directory', 'new-leaf'}
        assert set(new['changing-directory']['dependencies']) == {'new-leaf'}
        assert Version(new['changing-directory']['version']) == Version('1.0')
        assert Version(new['new-leaf']['version']) == Version('1.0')


def test_lock_freshness_tracks_dependency_declarations_not_description(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    wheels = [factory.create(n)[1] for n in ('fresh-leaf', 'group-leaf')]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', wheels) as url:
        path = dependency_project(tmp_path / 'baseline', url, standard=['fresh-leaf>=1'], extra='''
[project.optional-dependencies]
speed=["group-leaf>=1"]
[dependency-groups]
test=["group-leaf>=1"]
qa=[{include-group="test"}]
''')
        dependency_lock(path, env)
        document = (path / 'pyproject.toml').read_text()
        lock = (path / 'velnora.lock').read_bytes()
        for command in [('check',), ('check', '--lock')]:
            succeeded(project_cli(path, env, *command))
        changes = [
            ('python', '>=3.9', '>=3.10'),
            ('runtime', 'fresh-leaf>=1', 'fresh-leaf>=1,<2'),
            ('optional', 'speed=["group-leaf>=1"]', 'speed=["group-leaf>=1,<2"]'),
            ('extras', 'speed=', 'accelerate='),
            ('group', 'test=["group-leaf>=1"]', 'test=["group-leaf>=1,<2"]'),
            ('inclusion', 'qa=[{include-group="test"}]', 'qa=[]'),
            ('source', '/simple/', '/other-simple/')]
        for label, old, new in changes:
            target = tmp_path / label
            shutil.copytree(path, target, ignore=shutil.ignore_patterns('.venv'))
            (target / 'pyproject.toml').write_text(document.replace(old, new))
            for command in [('check',), ('check', '--lock')]:
                result = refused(project_cli(target, env, *command), 'velnora.lock')
                assert any(line.startswith('Error:') for line in result.stderr.splitlines()), result.stderr
            assert (target / 'velnora.lock').read_bytes() == lock
        (path / 'pyproject.toml').write_text(document.replace('version="1.0"', 'version="1.0"\ndescription="New description"'
            '\nkeywords=["refreshed"]\nauthors=[{name="Changed Author"}]\nclassifiers=["Topic :: Utilities"]'))
        succeeded(project_cli(path, env, 'check', '--lock'))
        (path / 'velnora.lock').unlink()
        succeeded(project_cli(path, env, 'check'))
        refused(project_cli(path, env, 'check', '--lock'), 'velnora.lock')


def test_integrity_and_unusable_locks_require_explicit_regeneration(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    _, wheel = factory.create('integrity-package')
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', [wheel]) as url:
        path = dependency_project(tmp_path / 'baseline', url, standard=['integrity-package==1.0'])
        record, = dependency_lock(path, env)
        artifact, = record['files']
        assert artifact['file'] == wheel.name
        algorithm, digest = artifact['hash'].split(':', 1)
        assert hashlib.new(algorithm, wheel.read_bytes()).hexdigest() == digest
        succeeded(project_cli(path, env, 'install', '--no-root'))
        assert installed_values(path, env, ['integrity-package'])['values'] == {'integrity-package': 'integrity-package:1.0'}
        valid = (path / 'velnora.lock').read_text()
        def relabelled(version):
            document = read_toml(path / 'velnora.lock')
            document['metadata']['lock-version'] = version
            return dumps(document)
        # The served artifact is intact; only the recorded content identity differs.
        recorded = read_toml(path / 'velnora.lock')
        recorded['package'][0]['files'][0]['hash'] = algorithm + ':' + '0' * len(digest)
        # Consume earlier supported formats in fresh environments, rather than
        # merely accepting their version labels during project validation.
        for version in ('1.0', '2.0'):
            supported = tmp_path / ('supported-format-' + version)
            shutil.copytree(path, supported, ignore=shutil.ignore_patterns('.venv'))
            (supported / 'velnora.lock').write_text(relabelled(version))
            supported_env = project_environment(tmp_path / ('supported-format-environment-' + version))
            succeeded(project_cli(supported, supported_env, 'install', '--no-root'))
            assert installed_values(supported, supported_env, ['integrity-package'])['values'] == {
                'integrity-package': 'integrity-package:1.0'}
        for label, broken in [
            ('integrity', valid),
            ('recorded-identity', dumps(recorded)),
            ('unreadable', '[metadata\n'),
            ('unsupported', relabelled('3.0'))]:
            target = tmp_path / label
            shutil.copytree(path, target, ignore=shutil.ignore_patterns('.venv'))
            (target / 'velnora.lock').write_text(broken)
            target_env = project_environment(tmp_path / (label + '-environment'))
            served_artifact = tmp_path / 'index' / 'files' / wheel.name
            if label == 'integrity':
                # A ZIP permits a trailer; the artifact stays installable but its
                # content identity differs from the bytes selected during locking.
                served_artifact.write_bytes(wheel.read_bytes() + b'changed artifact\n')
            before = installed_values(target, target_env, [])['installed']
            assert 'integrity-package' not in before
            result = project_cli(target, target_env, 'install', '--no-root')
            if label in ('integrity', 'recorded-identity'):
                assert result.returncode == 1, result
                assert result.stdout.strip(), result
                assert 'integrity-package' in result.stdout, result
            else:
                refused(result)
            assert installed_values(target, target_env, [])['installed'] == before
            if label == 'integrity':
                served_artifact.write_bytes(wheel.read_bytes())
            elif label == 'recorded-identity':
                # Restoring the recorded identity makes the same artifact installable.
                (target / 'velnora.lock').write_text(valid)
                succeeded(project_cli(target, target_env, 'install', '--no-root'))
                assert installed_values(target, target_env, ['integrity-package'])['values'] == {
                    'integrity-package': 'integrity-package:1.0'}
            else:
                succeeded(project_cli(target, target_env, 'lock', '--regenerate'))
                regenerated, = read_toml(target / 'velnora.lock')['package']
                assert Version(regenerated['version']) == Version('1.0')
                succeeded(project_cli(target, target_env, 'install', '--no-root'))
                assert installed_values(target, target_env, ['integrity-package'])['values'] == {'integrity-package': 'integrity-package:1.0'}
