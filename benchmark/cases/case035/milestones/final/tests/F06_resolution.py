# feature: F06
"""Acceptance of complete solutions and candidate policies through public locking."""
from datetime import datetime, timedelta, timezone
import json
import shutil

from packaging.version import Version

from _helpers import read_toml
from F01_helpers import project_cli, project_environment, refused, succeeded
from F04_helpers import (DistributionFactory, dependency_project, dependency_lock,
                         distribution_index, git_command, locked_by_name)
from F05_helpers import source_project, source_lock
from F06_helpers import applicable_records, configured_age, release_policy_repository


def test_complete_solution_across_python_range_and_groups(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    wheels = [factory.create('range-leaf', v)[1] for v in ('1.0', '2.0')]
    wheels += [factory.create('range-root', dependencies=[
        'range-leaf==1.0; python_version < "3.10"',
        'range-leaf==2.0; python_version >= "3.10"'], extras={'fast': ['extra-leaf==1.0']})[1]]
    wheels += [factory.create(n)[1] for n in ('extra-leaf', 'dev-root', 'optional-root')]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', wheels) as url:
        path = dependency_project(tmp_path / 'project', url, standard=['range-root[fast]==1.0'], extra='''
[tool.<legacy>.group.dev.dependencies]
dev-root="1.0"
[tool.<legacy>.group.audit]
optional=true
[tool.<legacy>.group.audit.dependencies]
optional-root="1.0"
''')
        records = dependency_lock(path, env)
        assert {r['name'] for r in records} == {'range-root', 'range-leaf', 'extra-leaf', 'dev-root', 'optional-root'}
        for python, version in [('3.9', '1.0'), ('3.13', '2.0')]:
            selected = applicable_records(records, python=python)
            assert set(selected) == {'range-root', 'range-leaf', 'extra-leaf'}
            assert Version(selected['range-leaf']['version']) == Version(version)
            assert {'range-leaf', 'extra-leaf'} <= selected['range-root']['dependencies'].keys()
        assert set(applicable_records(records, python='3.9', group='dev')) == {'dev-root'}
        assert set(applicable_records(records, python='3.13', group='audit')) == {'optional-root'}
        for record in records:
            if record['name'] != 'range-leaf':
                assert Version(record['version']) == Version('1.0')
            assert record['source']['reference'] == 'acceptance'
            assert record['source']['url'].rstrip('/') == url + '/simple'


def test_disjoint_alternatives_and_simultaneous_conflict(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    wheels = [factory.create('conditional-child', v)[1] for v in ('1.0', '2.0')]
    wheels += [factory.create('conflicting-parent', dependencies=['conditional-child==1.0'])[1]]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', wheels) as url:
        path = dependency_project(tmp_path / 'disjoint', url, standard=[
            'conditional-child==1.0; sys_platform == "win32"',
            'conditional-child==2.0; sys_platform != "win32"'])
        records = dependency_lock(path, env)
        assert len(records) == 2
        for platform, version in [('linux', '2.0'), ('win32', '1.0'), ('darwin', '2.0')]:
            selected = applicable_records(records, python='3.11', platform=platform)
            assert set(selected) == {'conditional-child'}
            assert Version(selected['conditional-child']['version']) == Version(version)
        conflict = dependency_project(tmp_path / 'conflict', url,
            standard=['conditional-child==2.0', 'conflicting-parent==1.0'])
        refused(project_cli(conflict, env, 'lock'), 'conditional-child', 'conflicting-parent')
        assert not (conflict / 'velnora.lock').exists()


def test_newest_pep440_release_and_consistent_backtracking(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    versions = ('1.9', '1.10', '1.10.post1')
    wheels = [factory.create('ordered-release', v)[1] for v in versions]
    wheels += [factory.create('choice-root', '1.0', dependencies=['choice-leaf==1.0'])[1],
               factory.create('choice-root', '2.0', dependencies=['choice-leaf==2.0'])[1]]
    wheels += [factory.create('choice-leaf', v)[1] for v in ('1.0', '2.0')]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', wheels) as url:
        for scenario, constraints, root_version, leaf_version in [
            ('fresh', ['choice-root>=1'], '2.0', '2.0'),
            ('constrained', ['choice-root>=1', 'choice-leaf<2'], '1.0', '1.0')]:
            path = dependency_project(tmp_path / scenario, url, standard=['ordered-release>=1', *constraints])
            records = locked_by_name(dependency_lock(path, env))
            assert set(records) == {'ordered-release', 'choice-root', 'choice-leaf'}
            assert Version(records['ordered-release']['version']) == max(map(Version, versions))
            assert Version(records['choice-root']['version']) == Version(root_version)
            assert Version(records['choice-leaf']['version']) == Version(leaf_version)
            assert 'choice-leaf' in records['choice-root']['dependencies']


def test_prerelease_default_permission_and_prohibition(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    wheels = [factory.create('release-policy', v)[1] for v in ('1.0', '2.0rc1')]
    wheels += [factory.create('preview-only', '2.0rc1')[1]]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', wheels) as url:
        for scenario, package, permission, expected, lower in [
            ('default-stable', 'release-policy', None, '1.0', '1'),
            # A stable release exists but does not satisfy the constraint.
            ('default-unsatisfied', 'release-policy', None, '2.0rc1', '1.5'),
            ('default-preview', 'preview-only', None, '2.0rc1', '1'),
            ('allow-preview', 'release-policy', True, '2.0rc1', '1'),
            ('forbid-preview', 'release-policy', False, '1.0', '1'),
            ('forbid-only', 'preview-only', False, None, '1')]:
            declaration = package + '={version=">=' + lower + '"' + (
                '' if permission is None else ',allow-prereleases=' + str(permission).lower()) + '}'
            path = dependency_project(tmp_path / scenario, url, legacy=declaration)
            if expected is None:
                refused(project_cli(path, env, 'lock'), package)
                assert not (path / 'velnora.lock').exists()
            else:
                records = locked_by_name(dependency_lock(path, env))
                assert set(records) == {package}
                assert Version(records[package]['version']) == Version(expected)


def test_withdrawn_release_exclusion_and_exact_pin_warning(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    stable = factory.create('withdrawn-package', '1.0')[1]
    withdrawn = factory.create('withdrawn-package', '2.0')[1]
    reason = 'Incorrect dependency metadata'
    env = project_environment(tmp_path / 'env')
    with release_policy_repository([(stable, {}), (withdrawn, {'yanked': reason})]) as url:
        sources = [('policy', url + '/simple/', 'primary')]
        path = source_project(tmp_path / 'unconstrained', sources, dependencies=['withdrawn-package>=1'])
        assert Version(source_lock(path, env)['withdrawn-package']['version']) == Version('1.0')
        # Only an exact pin admits the withdrawn release; a bound reaching it does not.
        bounded = source_project(tmp_path / 'bounded', sources, dependencies=['withdrawn-package>=2'])
        refused(project_cli(bounded, env, 'lock'), 'withdrawn-package')
        assert not (bounded / 'velnora.lock').exists()
        pinned = source_project(tmp_path / 'pinned', sources, dependencies=['withdrawn-package==2.0'])
        result = succeeded(project_cli(pinned, env, 'lock'))
        record, = read_toml(pinned / 'velnora.lock')['package']
        assert Version(record['version']) == Version('2.0')
        # Read the existing warning carrier, not the freely worded sentence.
        assert any(line.startswith('Warning:') and 'withdrawn-package' in line and reason in line
                   for line in result.stderr.splitlines()), result.stderr


def test_minimum_age_whole_days_all_files_missing_times_and_invalid_value(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    now = datetime.now(timezone.utc)
    def uploaded(hours):
        return {'upload-time': (now - timedelta(hours=hours)).isoformat()}
    old = factory.create('age-package', '1.0')[1]
    recent = factory.create('age-package', '2.0')[1]
    # A second valid wheel build tag denotes another distribution of this release.
    recent_build = recent.with_name(recent.name.replace('-py3-', '-1-py3-'))
    shutil.copyfile(recent, recent_build)
    missing = factory.create('unknown-age', '3.0')[1]
    env = project_environment(tmp_path / 'env')
    # Both listing orders: any newer upload excludes the release, not only the first or last.
    for order, recent_files in (('later', [(recent, uploaded(72)), (recent_build, uploaded(18))]),
                                ('earlier', [(recent_build, uploaded(18)), (recent, uploaded(72))])):
        entries = [(old, uploaded(30)), *recent_files, (missing, {})]
        with release_policy_repository(entries) as url:
            sources = [('policy', url + '/simple/', 'primary')]
            for scenario, days, expected in [('default', None, '2.0'), ('one-day', 1, '1.0'), ('two-days', 2, None)]:
                if order == 'earlier' and scenario != 'one-day':
                    continue
                path = source_project(tmp_path / (order + '-' + scenario), sources, dependencies=['age-package>=1', 'unknown-age>=1'])
                if days is None:
                    result = succeeded(project_cli(path, env, 'config', 'solver.min-release-age'))
                    assert int(result.stdout.strip()) == 0
                    records = source_lock(path, env)
                elif expected is None:
                    succeeded(project_cli(path, env, 'config', '--local', 'solver.min-release-age', str(days)))
                    refused(project_cli(path, env, 'lock'), 'age-package')
                    continue
                else:
                    records = configured_age(path, env, days)
                assert set(records) == {'age-package', 'unknown-age'}
                assert Version(records['age-package']['version']) == Version(expected)
                assert Version(records['unknown-age']['version']) == Version('3.0')
            if order == 'later':
                path = source_project(tmp_path / 'invalid', sources)
                refused(project_cli(path, env, 'config', '--local', 'solver.min-release-age', '-1'))
                # The refused value is not stored: the effective minimum remains the default.
                assert int(succeeded(project_cli(path, env, 'config', 'solver.min-release-age')).stdout.strip()) == 0
                assert not (path / 'velnora.toml').exists()


def test_age_exemptions_preserve_other_constraints(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    now = datetime.now(timezone.utc)
    old = {'upload-time': (now - timedelta(days=10)).isoformat()}
    recent = {'upload-time': (now - timedelta(hours=2)).isoformat()}
    entries = [(factory.create('exempt-package', '1.0')[1], old),
               (factory.create('exempt-package', '2.0')[1], recent)]
    # A package outside the name exemption, from a source outside the source exemption.
    other = [(factory.create('other-package', '1.0')[1], old),
             (factory.create('other-package', '2.0')[1], recent)]
    source, limited = factory.create('python-restricted', '1.0')
    (source / 'pyproject.toml').write_text((source / 'pyproject.toml').read_text().replace('>=3.9', '>=3.10'))
    succeeded(project_cli(source, factory.env, 'build', '--format', 'wheel'))
    entries.append((limited, {**recent, 'requires-python': '>=3.10'}))
    env = project_environment(tmp_path / 'env')
    with release_policy_repository(entries) as url, distribution_index(tmp_path / 'empty', []) as empty, \
            release_policy_repository(other) as other_url:
        sources = [('policy', url + '/simple/', 'primary'), ('empty', empty + '/simple/', 'explicit'),
                   ('unexempt', other_url + '/simple/', 'primary')]
        baseline = source_project(tmp_path / 'baseline', sources, dependencies=['exempt-package>=1'])
        assert Version(configured_age(baseline, env, 1)['exempt-package']['version']) == Version('1.0')
        for i, (setting, value) in enumerate([
            ('solver.min-release-age-exclude', 'exempt-package,python-restricted'),
            ('solver.min-release-age-exclude-source', 'policy'),
            ('solver.min-release-age-exclude-source', url + '/simple/')]):
            for scenario, binding, expected in [
                ('eligible', 'exempt-package=">=1"\nother-package=">=1"', '2.0'),
                ('version', 'exempt-package="<2"', '1.0'),
                ('python', 'python-restricted="*"', None),
                ('origin', 'exempt-package={version="*",source="empty"}', None)]:
                path = source_project(tmp_path / f'{i}-{scenario}', sources, bindings=binding)
                succeeded(project_cli(path, env, 'config', '--local', 'solver.min-release-age', '1'))
                succeeded(project_cli(path, env, 'config', '--local', setting, value))
                if expected is None:
                    refused(project_cli(path, env, 'lock'), 'python-restricted' if scenario == 'python' else 'exempt-package')
                else:
                    records = source_lock(path, env)
                    assert set(records) == ({'exempt-package', 'other-package'} if scenario == 'eligible'
                                            else {'exempt-package'})
                    assert Version(records['exempt-package']['version']) == Version(expected)
                    if scenario == 'eligible':
                        # The exemption bypasses the filter only for its own package or source.
                        assert Version(records['other-package']['version']) == Version('1.0')


def test_direct_origin_metadata_merging_and_source_failures(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    directory, archive = factory.create('actual-origin', '3.2', dependencies=['origin-leaf==1.0'])
    wheels = [factory.create('origin-leaf', '1.0')[1],
              factory.create('origin-parent', dependencies=['actual-origin>=3,<4'])[1]]
    env = project_environment(tmp_path / 'env')
    git_command(directory, env, 'init', '--initial-branch=main')
    git_command(directory, env, 'config', 'user.name', 'Acceptance')
    git_command(directory, env, 'config', 'user.email', 'acceptance@example.invalid')
    git_command(directory, env, 'add', 'pyproject.toml', 'actual_origin')
    git_command(directory, env, 'commit', '-m', 'Initial package')
    with distribution_index(tmp_path / 'index', wheels) as url:
        shutil.copyfile(archive, tmp_path / 'index' / 'files' / archive.name)
        for scenario, declaration, kind in [
            ('directory', 'actual-origin={path=' + json.dumps(str(directory)) + '}', 'directory'),
            ('archive', 'actual-origin={path=' + json.dumps(str(archive)) + '}', 'file'),
            ('remote', 'actual-origin={url=' + json.dumps(url + '/files/' + archive.name) + '}', 'url'),
            ('git', 'actual-origin={git=' + json.dumps(directory.as_uri()) + '}', 'git')]:
            path = dependency_project(tmp_path / scenario, url, legacy=declaration + '\norigin-parent="1.0"')
            records = locked_by_name(dependency_lock(path, env))
            assert set(records) == {'actual-origin', 'origin-parent', 'origin-leaf'}
            assert Version(records['actual-origin']['version']) == Version('3.2')
            assert records['actual-origin']['source']['type'] == kind
            assert 'origin-leaf' in records['actual-origin']['dependencies']
            assert 'actual-origin' in records['origin-parent']['dependencies']
        for scenario, declaration, subject in [
            ('missing', 'actual-origin={path=' + json.dumps(str(tmp_path / 'absent-project')) + '}', 'absent-project'),
            ('revision', 'actual-origin={git=' + json.dumps(directory.as_uri()) + ',rev="missing-revision"}', 'missing-revision'),
            ('identity', 'requested-other={path=' + json.dumps(str(directory)) + '}', 'requested-other')]:
            path = dependency_project(tmp_path / scenario, url, legacy=declaration)
            refused(project_cli(path, env, 'lock'), subject)
            assert not (path / 'velnora.lock').exists()
