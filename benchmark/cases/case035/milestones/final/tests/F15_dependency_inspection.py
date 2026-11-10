# feature: F15
"""Dependency inspection through real CLI commands and local repositories."""
from collections import Counter
import sys
import re
from pathlib import Path

from packaging.utils import canonicalize_name
from packaging.version import Version
from packaging.tags import sys_tags

from _helpers import parse_json
from F01_helpers import project_cli, project_environment, refused, succeeded
from F04_helpers import DistributionFactory, dependency_project, dependency_lock, distribution_index
from F09_helpers import project_observation
from F13_helpers import maintenance_files
from F15_helpers import (inspection_rows, described_wheel, equivalent_constraint,
                         inspection_tree, search_rows, listing_page, resolution_rows,
                         diagnostic_sections)


def test_locked_listing_filters_and_installed_status(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    wheels = [described_wheel(factory, 'inspect-root', dependencies=['inspect-leaf==1.0'])]
    wheels += [described_wheel(factory, n) for n in ('inspect-leaf', 'inspect-other', 'inspect-audit')]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', wheels) as url:
        path = dependency_project(tmp_path / 'project', url, standard=[
            'inspect-root==1.0', 'inspect-other==1.0; sys_platform == "win32"'], extra='''
[tool.<legacy>.group.audit]
optional=true
[tool.<legacy>.group.audit.dependencies]
inspect-audit="1.0"
''')
        refused(project_cli(path, env, 'show', '--format=json'), 'velnora.lock')
        dependency_lock(path, env)
        before = maintenance_files(path)
        rows = inspection_rows(path, env)
        assert set(rows) == {'inspect-root', 'inspect-leaf'}
        for name, row in rows.items():
            assert Version(row['version']) == Version('1.0')
            assert row['description'] == 'Inspection metadata for ' + name
            assert row['installed_status'] == 'not-installed'
        assert set(inspection_rows(path, env, '--all')) == {'inspect-root', 'inspect-leaf', 'inspect-other', 'inspect-audit'}
        assert set(inspection_rows(path, env, '--top-level')) == {'inspect-root'}
        assert set(inspection_rows(path, env, '--only=audit')) == {'inspect-audit'}
        assert set(inspection_rows(path, env, '--with=audit')) == {'inspect-root', 'inspect-leaf', 'inspect-audit'}
        succeeded(project_cli(path, env, 'install', '--no-root'))
        installed = inspection_rows(path, env)
        assert set(installed) == set(rows)
        assert all(r['installed_status'] == 'installed' for r in installed.values())
        assert maintenance_files(path) == before


def test_named_dependency_requirements_and_reverse_references(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    wheels = [described_wheel(factory, 'detail-root', dependencies=['detail-middle>=1,<2']),
              described_wheel(factory, 'detail-peer', dependencies=['detail-middle>=1,<3']),
              described_wheel(factory, 'detail-middle', dependencies=['detail-leaf==1.0']),
              described_wheel(factory, 'detail-leaf')]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', wheels) as url:
        path = dependency_project(tmp_path / 'project', url, standard=['detail-root==1.0', 'detail-peer==1.0'])
        dependency_lock(path, env)
        row = parse_json(succeeded(project_cli(path, env, 'show', 'detail-middle', '--format=json')).stdout)
        assert canonicalize_name(row['name']) == 'detail-middle'
        assert Version(row['version']) == Version('1.0')
        assert row['description'] == 'Inspection metadata for detail-middle'
        row['dependencies'] = {canonicalize_name(n): v for n, v in row['dependencies'].items()}
        row['required_by'] = {canonicalize_name(n): v for n, v in row['required_by'].items()}
        assert set(row['dependencies']) == {'detail-leaf'}
        equivalent_constraint(row['dependencies']['detail-leaf'], ['1.0'], ['0.9', '1.1'])
        assert set(row['required_by']) == {'detail-root', 'detail-peer'}
        equivalent_constraint(row['required_by']['detail-root'], ['1.0', '1.9'], ['0.9', '2.0'])
        equivalent_constraint(row['required_by']['detail-peer'], ['1.0', '2.9'], ['0.9', '3.0'])
        refused(project_cli(path, env, 'show', 'detail-missing', '--format=json'), 'detail-missing')


def test_tree_reasons_shared_dependencies_and_cycles(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    graph = {'tree-root': ['tree-left', 'tree-right', 'cycle-a'],
             'tree-left': ['tree-shared'], 'tree-right': ['tree-shared'],
             'tree-shared': ['tree-end'], 'tree-end': [],
             'cycle-a': ['cycle-b'], 'cycle-b': ['cycle-a']}
    wheels = [factory.create(n, dependencies=[d + '==1.0' for d in deps])[1]
              for n, deps in graph.items()]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', wheels) as url:
        path = dependency_project(tmp_path / 'project', url, standard=['tree-root==1.0'])
        dependency_lock(path, env)
        expected = Counter({(p, cycle): 1 for p, cycle in [
            (('tree-root',), False),
            (('tree-root', 'tree-left'), False),
            (('tree-root', 'tree-left', 'tree-shared'), False),
            (('tree-root', 'tree-left', 'tree-shared', 'tree-end'), False),
            (('tree-root', 'tree-right'), False),
            (('tree-root', 'tree-right', 'tree-shared'), False),
            (('tree-root', 'tree-right', 'tree-shared', 'tree-end'), False),
            (('tree-root', 'cycle-a'), False),
            (('tree-root', 'cycle-a', 'cycle-b'), False),
            (('tree-root', 'cycle-a', 'cycle-b', 'cycle-a'), True)]})
        assert inspection_tree(succeeded(project_cli(path, env, 'show', '--tree')).stdout) == expected
        assert inspection_tree(succeeded(project_cli(path, env, 'show', 'tree-root', '--tree')).stdout) == expected
        reasons = inspection_rows(path, env, '--why')
        assert set(reasons['tree-shared']['required_by']) == {'tree-left', 'tree-right'}
        assert set(reasons['tree-end']['required_by']) == {'tree-shared'}
        why = inspection_tree(succeeded(project_cli(path, env, 'show', 'tree-shared', '--tree', '--why')).stdout)
        assert why == Counter({(p, False): 1 for p in [
            ('tree-left',), ('tree-left', 'tree-shared'), ('tree-left', 'tree-shared', 'tree-end'),
            ('tree-right',), ('tree-right', 'tree-shared'), ('tree-right', 'tree-shared', 'tree-end')]})


def test_latest_and_outdated_use_locked_source_without_writes(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    wheels = [factory.create('upgrade-subject', v)[1] for v in ('1.0', '2.0')]
    wheels += [factory.create('current-subject', '3.0')[1]]
    decoy = factory.create('upgrade-subject', '9.0')[1]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', wheels) as url, distribution_index(tmp_path / 'decoy', [decoy]) as other:
        path = dependency_project(tmp_path / 'project', url, standard=['upgrade-subject==1.0', 'current-subject==3.0'],
            legacy='upgrade-subject={version="1.0",source="acceptance"}', extra='''
[[tool.<legacy>.source]]
name="decoy"
url="''' + other + '''/simple/"
priority="primary"
''')
        dependency_lock(path, env)
        before = maintenance_files(path)
        latest = inspection_rows(path, env, '--latest')
        outdated = inspection_rows(path, env, '--outdated')
        assert set(latest) == {'upgrade-subject', 'current-subject'}
        assert set(outdated) == {'upgrade-subject'}
        for name, current, newest in [('upgrade-subject', '1.0', '2.0'), ('current-subject', '3.0', '3.0')]:
            assert Version(latest[name]['version']) == Version(current)
            assert Version(latest[name]['latest_version']) == Version(newest)
        assert Version(outdated['upgrade-subject']['version']) == Version('1.0')
        assert Version(outdated['upgrade-subject']['latest_version']) == Version('2.0')
        assert maintenance_files(path) == before


def test_diagnostic_resolution_target_conflicts_environment_and_tags(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    wheels = [factory.create('target-leaf', v)[1] for v in ('1.0', '2.0')]
    wheels += [factory.create('target-root', dependencies=[
        'target-leaf==1.0; python_version < "3.10"',
        'target-leaf==2.0; python_version >= "3.10"'])[1]]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', wheels) as url:
        path = dependency_project(tmp_path / 'project', url, standard=['target-root==1.0'])
        dependency_lock(path, env)
        environment = project_observation(path, env)
        before = maintenance_files(path)
        for python, version in [('3.9', '1.0'), ('3.12', '2.0')]:
            report = resolution_rows(succeeded(project_cli(path, env, 'debug', 'resolve', '--python', python)).stdout)
            assert report == {'target-root': Version('1.0'), 'target-leaf': Version(version)}
        refused(project_cli(path, env, 'debug', 'resolve', 'target-root==1.0', 'target-leaf==3.0'), 'target-leaf')
        report = diagnostic_sections(succeeded(project_cli(path, env, 'debug', 'info')).stdout)
        assert report['Virtualenv']['Python'] == environment['version']
        assert report['Virtualenv']['Implementation'] == environment['implementation']
        assert Path(report['Virtualenv']['Path']) == Path(environment['prefix'])
        assert report['Base']['Platform'] == sys.platform
        assert Path(report['Virtualenv']['Executable']) == Path(environment['executable'])
        tags = succeeded(project_cli(path, env, 'debug', 'tags')).stdout.splitlines()
        assert len(tags) == len(set(tags))
        assert set(tags) == {str(t) for t in sys_tags()}
        assert maintenance_files(path) == before
        assert project_observation(path, env)['packages'] == environment['packages']


def test_search_any_term_versions_deduplication_and_sources(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    common = [factory.create('amber-widget', v)[1] for v in ('1.0', '2.0')]
    blue = factory.create('blue-widget')[1]
    unrelated = factory.create('unrelated')[1]
    env = project_environment(tmp_path / 'env')
    first, second = tmp_path / 'primary', tmp_path / 'supplemental'
    with distribution_index(first, common + [unrelated]) as url, distribution_index(second, [common[0], blue]) as other:
        listing_page(first, ['amber-widget', 'amber-widget', 'unrelated'])
        listing_page(second, ['amber-widget', 'blue-widget'])
        path = dependency_project(tmp_path / 'project', url, extra='''
[[tool.<legacy>.source]]
name="supplemental"
url="''' + other + '''/simple/"
priority="supplemental"
''')
        rows = search_rows(succeeded(project_cli(path, env, 'search', 'amber', 'blue')).stdout)
        assert rows == Counter({('amber-widget', Version('1.0'), 'acceptance'): 1,
                                ('amber-widget', Version('2.0'), 'acceptance'): 1,
                                ('amber-widget', Version('1.0'), 'supplemental'): 1,
                                ('blue-widget', Version('1.0'), 'supplemental'): 1})
        empty = succeeded(project_cli(path, env, 'search', 'no-such-name'))
        assert empty.stdout.strip()
        assert not re.search(r"(?m)^\s*Package\s+Version\s+Source\s+Description\s*$", empty.stdout)
        assert not empty.stderr.strip()
