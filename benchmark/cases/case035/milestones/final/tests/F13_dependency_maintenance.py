# feature: F13
"""Dependency maintenance through real CLI operations and executable artifacts."""
from F00_documents import legacy_key
import json

from packaging.markers import Marker, default_environment
from packaging.version import Version
from F00_reports import operation_lines, local_file_path

from _helpers import read_toml, snapshot_tree, snapshot_toml
from F01_helpers import project_cli, project_environment, refused, succeeded
from F04_helpers import DistributionFactory, dependency_project, dependency_lock, distribution_index
from F11_helpers import (installation_clone, installation_state, install_failure,
                         publish_source)
from F13_helpers import (maintenance_document, maintenance_requirements, maintenance_lock,
                         maintenance_versions, maintenance_files, maintenance_installed,
                         maintenance_install)


def test_add_groups_optional_and_requirement_attributes(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    wheels = [factory.create(n)[1] for n in ('main-member', 'group-member', 'extra-member', 'legacy-member', 'child-member')]
    wheels += [factory.create('parent-member', extras={'fast': ['child-member==1.0']})[1]]
    editable, _ = factory.create('editable-member')
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', wheels) as url:
        project = dependency_project(tmp_path / 'project', url)
        succeeded(project_cli(project, env, 'add', 'main-member==1.0'))
        assert set(maintenance_requirements(maintenance_document(project)['project']['dependencies'])) == {'main-member'}
        assert maintenance_versions(project) == {'main-member': Version('1.0')}
        maintenance_installed(project, env, {'main-member': '1.0'})
        succeeded(project_cli(project, env, 'add', 'group-member==1.0', '--group', 'audit'))
        doc = maintenance_document(project)
        assert set(maintenance_requirements(doc['dependency-groups']['audit'])) == {'group-member'}
        assert 'group-member' not in maintenance_requirements(doc['project']['dependencies'])
        assert maintenance_lock(project)['group-member']['groups'] == ['audit']
        maintenance_installed(project, env, {'main-member': '1.0', 'group-member': '1.0'})
        succeeded(project_cli(project, env, 'add', 'extra-member==1.0', '--optional', 'speed'))
        doc = maintenance_document(project)
        assert set(maintenance_requirements(doc['project']['optional-dependencies']['speed'])) == {'extra-member'}
        assert maintenance_lock(project)['extra-member']['optional'] is True
        succeeded(project_cli(project, env, 'install', '--no-root', '--extras', 'speed'))
        maintenance_installed(project, env, {'extra-member': '1.0'})
        marker = 'python_version >= "3.9" and sys_platform != "unsupported"'
        succeeded(project_cli(project, env, 'add', 'parent-member==1.0', '--extras', 'fast', '--markers', marker, '--source', 'acceptance'))
        doc = maintenance_document(project)
        req = maintenance_requirements(doc['project']['dependencies'])['parent-member']
        assert req.extras == {'fast'}
        assert req.marker is not None
        for python, platform in [('3.8', 'linux'), ('3.11', 'linux'), ('3.11', 'unsupported')]:
            target = {**default_environment(), 'python_version': python, 'sys_platform': platform}
            assert req.marker.evaluate(target) == Marker(marker).evaluate(target)
        assert doc['tool'][legacy_key()]['dependencies']['parent-member']['source'] == 'acceptance'
        assert maintenance_lock(project)['parent-member']['source']['url'].rstrip('/') == url + '/simple'
        maintenance_installed(project, env, {'parent-member': '1.0', 'child-member': '1.0'})
        succeeded(project_cli(project, env, 'add', str(editable), '--editable'))
        doc = maintenance_document(project)
        assert doc['tool'][legacy_key()]['dependencies']['editable-member']['develop'] is True
        assert maintenance_lock(project)['editable-member']['develop'] is True
        assert local_file_path(maintenance_requirements(doc['project']['dependencies'])['editable-member'].url) == editable.resolve()
        maintenance_installed(project, env, {'editable-member': '1.0'})
        (editable / 'editable_member' / '__init__.py').write_text('def value():\n    return "edited live source"\n')
        assert installation_state(project, env, ['editable-member'])['values'] == {'editable-member': 'edited live source'}
        legacy = dependency_project(tmp_path / 'legacy', url, legacy='python=">=3.9"')
        declaration = legacy / 'pyproject.toml'
        declaration.write_text(declaration.read_text().replace('dependencies=[]\n', ''))
        succeeded(project_cli(legacy, env, 'add', 'legacy-member==1.0', '--optional', 'speed'))
        doc = maintenance_document(legacy)
        assert doc['tool'][legacy_key()]['dependencies']['legacy-member']['optional'] is True
        assert not doc['project'].get('optional-dependencies')
        assert not doc['tool'][legacy_key()].get('extras')
        assert maintenance_lock(legacy)['legacy-member']['optional'] is True


def test_add_selection_noop_replacement_latest_and_self_refusal(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    wheels = [factory.create('range-member', v)[1] for v in ('1.2', '1.8', '2.4')]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', wheels[:2]) as url:
        project = dependency_project(tmp_path / 'project', url)
        succeeded(project_cli(project, env, 'add', 'range-member'))
        req = maintenance_requirements(maintenance_document(project)['project']['dependencies'])['range-member']
        for version, accepted in [('1.7', False), ('1.8', True), ('1.9', True), ('2.0', False)]:
            assert (Version(version) in req.specifier) == accepted
        assert maintenance_versions(project) == {'range-member': Version('1.8')}
        maintenance_installed(project, env, {'range-member': '1.8'})
        before = snapshot_toml([project / 'pyproject.toml', project / 'velnora.lock'])
        result = succeeded(project_cli(project, env, 'add', 'range-member'))
        assert result.stdout.strip() and 'range-member' in result.stdout
        assert snapshot_toml([project / 'pyproject.toml', project / 'velnora.lock']) == before
        succeeded(project_cli(project, env, 'add', 'range-member==1.2'))
        reqs = maintenance_requirements(maintenance_document(project)['project']['dependencies'])
        assert set(reqs) == {'range-member'}
        assert Version('1.2') in reqs['range-member'].specifier
        assert Version('1.8') not in reqs['range-member'].specifier
        assert maintenance_versions(project) == {'range-member': Version('1.2')}
        maintenance_installed(project, env, {'range-member': '1.2'})
        publish_source(tmp_path / 'index', wheels[2], 'range-member')
        succeeded(project_cli(project, env, '--no-cache', 'add', 'range-member@latest'))
        req = maintenance_requirements(maintenance_document(project)['project']['dependencies'])['range-member']
        for version, accepted in [('1.8', False), ('2.3', False), ('2.4', True), ('2.9', True), ('3.0', False)]:
            assert (Version(version) in req.specifier) == accepted
        assert maintenance_versions(project) == {'range-member': Version('2.4')}
        maintenance_installed(project, env, {'range-member': '2.4'})
        before = snapshot_toml([project / 'pyproject.toml', project / 'velnora.lock'])
        refused(project_cli(project, env, 'add', 'sample-project==1.0'), 'sample-project')
        assert snapshot_toml([project / 'pyproject.toml', project / 'velnora.lock']) == before


def test_remove_scope_shared_requirements_cleanup_and_atomic_missing(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    wheels = [factory.create(n)[1] for n in ('shared-leaf', 'exclusive-leaf', 'duplicated-member', 'audit-member')]
    wheels += [factory.create('first-parent', dependencies=['shared-leaf==1.0', 'exclusive-leaf==1.0'])[1],
               factory.create('retained-parent', dependencies=['shared-leaf==1.0'])[1]]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', wheels) as url:
        project = dependency_project(tmp_path / 'project', url,
            standard=['first-parent==1.0', 'retained-parent==1.0', 'duplicated-member==1.0'], extra='''
[dependency-groups]
audit=["duplicated-member==1.0", "audit-member==1.0"]
bundle=[{include-group="audit"}]
[tool.<legacy>.group.legacy]
include-groups=["audit"]
''')
        maintenance_install(project, env)
        maintenance_installed(project, env, {n: '1.0' for n in ('first-parent', 'retained-parent', 'shared-leaf', 'exclusive-leaf', 'duplicated-member', 'audit-member')})
        before = snapshot_toml([project / 'pyproject.toml', project / 'velnora.lock'])
        refused(project_cli(project, env, 'remove', 'first-parent', 'missing-member'), 'missing-member')
        assert snapshot_toml([project / 'pyproject.toml', project / 'velnora.lock']) == before
        refused(project_cli(project, env, 'remove', 'retained-parent', '--group', 'audit'), 'retained-parent')
        assert snapshot_toml([project / 'pyproject.toml', project / 'velnora.lock']) == before
        succeeded(project_cli(project, env, 'remove', 'duplicated-member', '--group', 'audit'))
        doc = maintenance_document(project)
        assert 'duplicated-member' in maintenance_requirements(doc['project']['dependencies'])
        assert set(maintenance_requirements(doc['dependency-groups']['audit'])) == {'audit-member'}
        maintenance_installed(project, env, {'duplicated-member': '1.0'})
        succeeded(project_cli(project, env, 'remove', 'first-parent', 'duplicated-member'))
        assert set(maintenance_lock(project)) == {'retained-parent', 'shared-leaf', 'audit-member'}
        assert set(maintenance_requirements(maintenance_document(project)['project']['dependencies'])) == {'retained-parent'}
        maintenance_installed(project, env, {'shared-leaf': '1.0', 'retained-parent': '1.0', 'audit-member': '1.0'},
                              absent=('first-parent', 'exclusive-leaf', 'duplicated-member'))
        succeeded(project_cli(project, env, 'remove', 'audit-member', '--group', 'audit'))
        doc = maintenance_document(project)
        assert not doc.get('dependency-groups')
        assert 'legacy' not in doc.get('tool', {}).get(legacy_key(), {}).get('group', {})
        assert set(maintenance_lock(project)) == {'retained-parent', 'shared-leaf'}
        maintenance_installed(project, env, {'shared-leaf': '1.0', 'retained-parent': '1.0'}, absent=('audit-member',))
        # A dependency present in two declarations must be removed from both.
        both = dependency_project(tmp_path / 'both', url, standard=['duplicated-member==1.0'],
                                  extra='[dependency-groups]\naudit=["duplicated-member==1.0"]\n')
        maintenance_install(both, env)
        succeeded(project_cli(both, env, 'remove', 'duplicated-member'))
        assert maintenance_document(both)['project']['dependencies'] == []
        assert not maintenance_document(both).get('dependency-groups')
        assert maintenance_lock(both) == {}
        maintenance_installed(both, env, {}, absent=('duplicated-member',))


def test_update_all_direct_transitive_and_preserve_constraints(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    old = [factory.create(n, '1.0')[1] for n in ('update-leaf', 'independent-member')]
    old += [factory.create('update-parent', '1.0', dependencies=['update-leaf>=1,<2'])[1]]
    new = [factory.create(n, '1.5')[1] for n in ('update-leaf', 'independent-member')]
    new += [factory.create('update-parent', '1.5', dependencies=['update-leaf>=1,<2'])[1]]
    new += [factory.create(n, '2.0')[1] for n in ('update-leaf', 'independent-member', 'update-parent')]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', old) as url:
        template = dependency_project(tmp_path / 'template', url,
            standard=['update-parent>=1,<2', 'independent-member>=1,<2'])
        dependency_lock(template, env)
        for wheel in new:
            publish_source(tmp_path / 'index', wheel, wheel.name.split('-')[0])
        for label, selected, expected in [
            ('all', (), {'update-parent': '1.5', 'update-leaf': '1.5', 'independent-member': '1.5'}),
            ('direct', ('independent-member',), {'update-parent': '1.0', 'update-leaf': '1.0', 'independent-member': '1.5'}),
            ('transitive', ('update-leaf',), {'update-parent': '1.0', 'update-leaf': '1.5', 'independent-member': '1.0'})]:
            project = installation_clone(template, tmp_path / label)
            maintenance_install(project, env)
            maintenance_installed(project, env, {n: '1.0' for n in expected})
            before = read_toml(project / 'pyproject.toml')
            succeeded(project_cli(project, env, '--no-cache', 'update', *selected))
            assert read_toml(project / 'pyproject.toml') == before
            assert maintenance_versions(project) == {n: Version(v) for n, v in expected.items()}
            maintenance_installed(project, env, expected)


def test_update_group_install_scope_and_invalid_targets(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    old = [factory.create(n, '1.0')[1] for n in ('runtime-member', 'audit-member')]
    new = [factory.create(n, '1.5')[1] for n in ('runtime-member', 'audit-member')]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', old) as url:
        template = dependency_project(tmp_path / 'template', url, standard=['runtime-member>=1,<2'],
            extra='[dependency-groups]\naudit=["audit-member>=1,<2"]\n')
        dependency_lock(template, env)
        for wheel in new:
            publish_source(tmp_path / 'index', wheel, wheel.name.split('-')[0])
        for label, flags, selected in [('main', ('--only', 'main'), 'runtime-member'),
                                       ('audit', ('--only', 'audit'), 'audit-member')]:
            project = installation_clone(template, tmp_path / label)
            succeeded(project_cli(project, env, 'env', 'use', __import__('sys').executable))
            before = read_toml(project / 'pyproject.toml')
            succeeded(project_cli(project, env, '--no-cache', 'update', *flags))
            assert read_toml(project / 'pyproject.toml') == before
            assert maintenance_versions(project) == {n: Version('1.5') for n in ('runtime-member', 'audit-member')}
            other = 'audit-member' if selected == 'runtime-member' else 'runtime-member'
            maintenance_installed(project, env, {selected: '1.5'}, absent=(other,))
            files = snapshot_toml([project / 'pyproject.toml', project / 'velnora.lock'])
            for request in ('unknown-member', 'runtime-member>=1.1'):
                refused(project_cli(project, env, 'update', request), request)
                assert snapshot_toml([project / 'pyproject.toml', project / 'velnora.lock']) == files


def test_lock_only_and_preview_modes_preserve_their_scopes(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    old = factory.create('mode-member', '1.0')[1]
    new = factory.create('mode-member', '1.5')[1]
    added = factory.create('added-member')[1]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', [old, added]) as url:
        template = dependency_project(tmp_path / 'template', url, standard=['mode-member>=1,<2'])
        dependency_lock(template, env)
        publish_source(tmp_path / 'index', new, 'mode-member')
        for command, arguments, report, expected in [
            ('add', ('added-member==1.0',), '- Installing added-member (1.0)', {'mode-member': '1.0', 'added-member': '1.0'}),
            ('remove', ('mode-member',), '- Removing mode-member (1.0)', {}),
            ('update', ('mode-member',), '- Updating mode-member (1.0 -> 1.5)', {'mode-member': '1.5'})]:
            for mode in ('normal', 'lock', 'dry-run'):
                project = installation_clone(template, tmp_path / (command + '-' + mode))
                maintenance_install(project, env)
                installed = maintenance_installed(project, env, {'mode-member': '1.0'})
                before = maintenance_files(project)
                before_document = maintenance_document(project)
                environment = snapshot_tree(project / '.venv')
                flags = () if mode == 'normal' else ('--' + mode,)
                result = succeeded(project_cli(project, env, '--no-cache', command, *arguments, *flags))
                if mode == 'dry-run':
                    expected_record, = operation_lines(report)
                    assert expected_record in operation_lines(result.stdout), result.stdout
                    assert maintenance_files(project) == before
                else:
                    assert maintenance_versions(project) == {n: Version(v) for n, v in expected.items()}
                    requirements = maintenance_requirements(maintenance_document(project)['project']['dependencies'])
                    assert set(requirements) == set(expected)
                    if command == 'update':
                        assert maintenance_document(project) == before_document
                if mode in ('lock', 'dry-run'):
                    assert snapshot_tree(project / '.venv') == environment
                    assert installation_state(project, env)['installed'] == installed
                else:
                    maintenance_installed(project, env, expected, absent=set(['mode-member', 'added-member']) - set(expected))


def test_failed_add_remove_and_late_build_preserve_committed_files(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    wheels = [factory.create('conflict-leaf', v)[1] for v in ('1.0', '2.0')]
    wheels += [factory.create('retained-parent', dependencies=['conflict-leaf==1.0'])[1],
               factory.create('conflicting-parent', dependencies=['conflict-leaf==2.0'])[1],
               factory.create('removable-member')[1]]
    broken, _ = factory.create('broken-build')
    # Metadata is valid; a real PEP 517 backend fails only at wheel construction.
    document = broken / 'pyproject.toml'
    document.write_text(document.read_text().replace('build-backend = "poetry.core.masonry.api"',
        'build-backend = "failing_backend"\nbackend-path = ["."]'))
    (broken / 'failing_backend.py').write_text('''from poetry.core.masonry.api import prepare_metadata_for_build_wheel

def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    raise RuntimeError("Deliberate wheel construction failure")
''')
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', wheels) as url:
        template = dependency_project(tmp_path / 'template', url,
            standard=['retained-parent==1.0', 'removable-member==1.0'])
        maintenance_install(template, env)
        maintenance_installed(template, env, {'retained-parent': '1.0', 'conflict-leaf': '1.0', 'removable-member': '1.0'})
        before = snapshot_toml([template / 'pyproject.toml', template / 'velnora.lock'])
        refused(project_cli(template, env, 'add', 'conflicting-parent==1.0'), 'conflicting-parent', 'conflict-leaf')
        assert snapshot_toml([template / 'pyproject.toml', template / 'velnora.lock']) == before
        # A project edit can leave an existing lock stale; removal must not
        # commit another edit when the retained requirements cannot resolve.
        project = installation_clone(template, tmp_path / 'remove')
        declaration = project / 'pyproject.toml'
        declaration.write_text(declaration.read_text().replace('"removable-member==1.0"',
            '"removable-member==1.0", "conflicting-parent==1.0"'))
        before_remove = snapshot_toml([project / 'pyproject.toml', project / 'velnora.lock'])
        refused(project_cli(project, env, 'remove', 'removable-member'), 'conflicting-parent', 'conflict-leaf')
        assert snapshot_toml([project / 'pyproject.toml', project / 'velnora.lock']) == before_remove
        # First prove that this source can resolve and be committed without
        # installing, so the subsequent failure really is after resolution.
        resolvable = installation_clone(template, tmp_path / 'resolvable')
        succeeded(project_cli(resolvable, env, 'add', str(broken), '--lock'))
        assert 'broken-build' in maintenance_lock(resolvable)
        late = installation_clone(template, tmp_path / 'late')
        maintenance_install(late, env)
        before_late = snapshot_toml([late / 'pyproject.toml', late / 'velnora.lock'])
        install_failure(project_cli(late, env, 'add', str(broken)), 'broken-build')
        assert snapshot_toml([late / 'pyproject.toml', late / 'velnora.lock']) == before_late
