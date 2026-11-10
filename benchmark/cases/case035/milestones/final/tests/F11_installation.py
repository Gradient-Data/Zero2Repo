# feature: F11
"""Acceptance tests for real locked installation, synchronization and artifact policy."""
from F00_documents import legacy_document
from F00_documents import legacy_key
import importlib.util
import json
from pathlib import Path
import shutil
import sys

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version
from F00_reports import operation_lines

from _helpers import (make_environment, read_toml, run_cli, snapshot_files,
                      snapshot_tree)
from F01_helpers import (project_cli, project_environment, refused, succeeded,
                         wheel_observation)
from F03_helpers import save_setting
from F04_helpers import (DistributionFactory, dependency_project, dependency_lock,
                         distribution_index, locked_by_name)
from F09_helpers import with_external
from F10_helpers import build_archives
from F11_helpers import (generated_dependency, install_failure, installation_clone,
                         installation_probe, installation_python, installation_state,
                         publish_source, seed_installation)


def test_locked_selection_versions_imports_and_commands(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    command, command_wheel = factory.create('command-package')
    module = command / 'command_package' / '__init__.py'
    module.write_text(module.read_text() + '\ndef main():\n    print(value())\n')
    declaration = command / 'pyproject.toml'
    declaration.write_text(declaration.read_text() + '\n[project.scripts]\nlocked-command="command_package:main"\n')
    command_wheel.unlink()
    wheel_observation(command, factory.env)
    wheels = [command_wheel]
    wheels += [factory.create('versioned-package', v)[1] for v in ('1.0', '2.0')]
    wheels += [factory.create(n)[1] for n in ('selected-group', 'extra-member', 'wrong-target')]
    wheels += [factory.create('parent-package', extras={'fast': ['extra-member==1.0']})[1]]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', wheels) as url:
        project = dependency_project(tmp_path / 'project', url, standard=[
            'command-package==1.0', 'versioned-package==2.0', 'parent-package[fast]==1.0',
            'wrong-target==1.0; python_version < "3.0"'], extra='''
[tool.<legacy>.group.audit]
optional=true
[tool.<legacy>.group.audit.dependencies]
selected-group="1.0"
''')
        dependency_lock(project, env)
        seed_installation(project, env, [factory.create('versioned-package', '1.0')[1], command_wheel])
        succeeded(project_cli(project, env, 'install', '--no-root', '--with', 'audit'))
        names = ['command-package', 'versioned-package', 'parent-package', 'extra-member', 'selected-group']
        result = installation_state(project, env, names)
        assert result['values'] == {n: n + (':2.0' if n == 'versioned-package' else ':1.0') for n in names}
        assert 'wrong-target' not in result['installed']
        assert Version(result['installed']['versioned-package']) == Version('2.0')
        assert succeeded(run_cli((str(installation_python(project, env).parent / 'locked-command'),),
            cwd=tmp_path, env=make_environment(env, remove=('PYTHONPATH',)))).stdout.strip() == 'command-package:1.0'
        # Preserve a user edit to an already satisfied installed distribution.
        # Reinstalling the same cached wheel would restore the original value.
        edited = 'retained installed source'
        installation_probe(project, env, '''import command_package, json
from pathlib import Path
Path(command_package.__file__).write_text(SOURCE)
print(json.dumps(True))'''.replace('SOURCE', repr('def value():\n    return ' + repr(edited) + '\n\ndef main():\n    print(value())\n')))
        assert installation_state(project, env, ['command-package'])['values'] == {'command-package': edited}
        # Keep the existing unavailable-artifact check as an additional condition.
        (tmp_path / 'index' / 'files' / command_wheel.name).unlink()
        succeeded(project_cli(project, env, 'install', '--no-root', '--with', 'audit'))
        assert installation_state(project, env, names)['values'] == {**result['values'], 'command-package': edited}
        assert succeeded(project_cli(project, env, 'run', 'locked-command')).stdout.strip() == edited


def test_install_preserves_and_sync_removes_with_protected_packages(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    names = ('required-package', 'optional-group', 'optional-extra', 'unrelated-package')
    wheels = [factory.create(n)[1] for n in names]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', wheels) as url:
        template = dependency_project(tmp_path / 'template', url, standard=['required-package==1.0'], extra='''
[project.optional-dependencies]
feature=["optional-extra==1.0"]
[tool.<legacy>.group.audit]
optional=true
[tool.<legacy>.group.audit.dependencies]
optional-group="1.0"
''')
        dependency_lock(template, env)
        for action in ('install', 'sync'):
            project = installation_clone(template, tmp_path / action)
            seeded_env = project_environment(tmp_path / (action + '-env'))
            seed_installation(project, seeded_env, wheels)
            succeeded(project_cli(project, seeded_env, 'install', '--only-root'))
            before = installation_state(project, seeded_env, names)['installed']
            assert 'pip' in before and 'sample-project' in before
            succeeded(project_cli(project, seeded_env, action, '--no-root'))
            after = installation_state(project, seeded_env, ['required-package'])
            assert after['values'] == {'required-package': 'required-package:1.0'}
            assert after['installed']['pip'] == before['pip']
            assert after['installed']['sample-project'] == before['sample-project']
            for name in names[1:]:
                assert (name in after['installed']) == (action == 'install')
        # A real system-site environment exposes an external distribution. Sync
        # may remove local packages but must leave this external package intact.
        project = installation_clone(template, tmp_path / 'system-project')
        external = tmp_path / 'system-environment'
        succeeded(run_cli((sys.executable, '-m', 'venv'),
            ('--system-site-packages', '--without-pip', str(external)), cwd=tmp_path, env=env))
        active = with_external(env, external)
        before = installation_probe(project, active, '''import importlib.metadata as m, json, pathlib
p=m.distribution('packaging')
print(json.dumps({'version':p.version,'metadata':str(p.locate_file('packaging/__init__.py'))}))''')
        original = snapshot_files([Path(before['metadata'])])
        succeeded(project_cli(project, active, 'sync', '--no-root'))
        after = installation_probe(project, active, '''import importlib.metadata as m, json
p=m.distribution('packaging')
print(json.dumps({'version':p.version,'metadata':str(p.locate_file('packaging/__init__.py'))}))''')
        assert before == after
        assert snapshot_files([Path(before['metadata'])]) == original
        assert installation_state(project, active, ['required-package'])['values'] == {'required-package': 'required-package:1.0'}


def test_editable_root_scope_conflicts_and_missing_source(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    _, wheel = factory.create('root-dependency')
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', [wheel]) as url:
        template = dependency_project(tmp_path / 'template', url, standard=['root-dependency==1.0'])
        source = template / 'sample_project' / '__init__.py'
        source.write_text('def value():\n    return "original source"\n')
        dependency_lock(template, env)
        for label, flags in [('default', ()), ('no-root', ('--no-root',)), ('only-root', ('--only-root',))]:
            project = installation_clone(template, tmp_path / label)
            succeeded(project_cli(project, env, 'install', *flags))
            result = installation_state(project, env, [] if label == 'only-root' else ['root-dependency'])
            assert ('sample-project' in result['installed']) == (label != 'no-root')
            assert ('root-dependency' in result['installed']) == (label != 'only-root')
            root = installation_probe(project, env,
                'import importlib.util,json; print(json.dumps(importlib.util.find_spec("sample_project") is not None))')
            assert root == (label != 'no-root')
            if root:
                assert installation_state(project, env, ['sample-project'])['values'] == {'sample-project': 'original source'}
                (project / 'sample_project' / '__init__.py').write_text('def value():\n    return "edited source now"\n')
                assert installation_state(project, env, ['sample-project'])['values'] == {'sample-project': 'edited source now'}
        contradictory = installation_clone(template, tmp_path / 'contradictory')
        for flags in [('--only-root', '--no-root'), ('--only-root', '--only', 'main')]:
            refused(project_cli(contradictory, env, 'install', *flags), '--only-root')
            # The contradictory request is refused before anything is installed.
            assert not (contradictory / '.venv').exists() or not {'sample-project', 'root-dependency'} & set(
                installation_state(contradictory, env)['installed'])
        shutil.rmtree(template / 'sample_project')
        result = refused(project_cli(template, env, 'install', '--only-root'), 'sample-project')
        assert any(line.startswith('Error:') for line in result.stderr.splitlines()), result


def test_no_directory_excludes_direct_and_transitive_sources(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    leaf, _ = factory.create('directory-leaf')
    parent, _ = factory.create('directory-parent')
    document = parent / 'pyproject.toml'
    document.write_text(document.read_text().replace('dependencies=[]',
        'dependencies=' + json.dumps(['directory-leaf @ ' + leaf.as_uri()])))
    _, wheel = factory.create('ordinary-wheel')
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', [wheel]) as url:
        template = dependency_project(tmp_path / 'template', url, standard=['ordinary-wheel==1.0', 'directory-parent==1.0'],
            legacy='directory-parent={path=' + json.dumps(str(parent)) + '}')
        dependency_lock(template, env)
        for label, options in [('normal', ()), ('omit', ('--no-directory',))]:
            project = installation_clone(template, tmp_path / label)
            succeeded(project_cli(project, env, 'install', '--no-root', *options))
            names = ['ordinary-wheel'] + (['directory-parent', 'directory-leaf'] if not options else [])
            result = installation_state(project, env, names)
            assert result['values'] == {n: n + ':1.0' for n in names}
            for name in ('directory-parent', 'directory-leaf'):
                assert (name in result['installed']) == (not options)


def test_extra_selection_all_missing_and_conflict(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    names = ('always-package', 'speed-package', 'report-package')
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', [factory.create(n)[1] for n in names]) as url:
        template = dependency_project(tmp_path / 'template', url, standard=['always-package==1.0'], extra='''
[project.optional-dependencies]
speed=["speed-package==1.0"]
report=["report-package==1.0"]
''')
        dependency_lock(template, env)
        for label, options, selected in [
            ('none', (), names[:1]), ('one', ('--extras', 'speed'), names[:2]),
            ('report', ('--extras', 'report'), (names[0], names[2])),
            ('all', ('--all-extras',), names)]:
            project = installation_clone(template, tmp_path / label)
            succeeded(project_cli(project, env, 'install', '--no-root', *options))
            result = installation_state(project, env, selected)
            assert result['values'] == {n: n + ':1.0' for n in selected}
            assert set(result['installed']) & set(names) == set(selected)
        refused(project_cli(template, env, 'install', '--no-root', '--extras', 'absent-extra'), 'absent-extra')
        refused(project_cli(template, env, 'install', '--no-root', '--all-extras', '--extras', 'speed'), '--extras', '--all-extras')


def test_wheels_compatibility_and_real_source_builds(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    source, wheel = factory.create('source-package')
    sdist = build_archives(source, factory.env, '--format', 'sdist')['sdist']
    _, compatible = factory.create('compatible-wheel')
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', [compatible]) as url:
        publish_source(tmp_path / 'index', sdist, 'source-package')
        directory, _ = factory.create('source-directory')
        project = dependency_project(tmp_path / 'project', url,
            standard=['source-package==1.0', 'compatible-wheel==1.0', 'source-directory==1.0'],
            legacy='source-directory={path=' + json.dumps(str(directory)) + '}')
        succeeded(project_cli(project, env, 'install', '--no-root'))
        names = ['source-package', 'compatible-wheel', 'source-directory']
        assert installation_state(project, env, names)['values'] == {n: n + ':1.0' for n in names}
        # Change one compatibility dimension per artifact; each otherwise has
        # the same real wheel payload and declared package identity.
        _, original = factory.create('incompatible-wheel')
        for label, tag in [('python', 'py2-none-any'), ('os', 'py3-none-win32'),
                           ('architecture', 'py3-none-linux_s390x')]:
            bad = tmp_path / (original.name.removesuffix('py3-none-any.whl') + tag + '.whl')
            shutil.copyfile(original, bad)
            with distribution_index(tmp_path / ('index-' + label), [bad]) as bad_url:
                rejected = dependency_project(tmp_path / label, bad_url, standard=['incompatible-wheel==1.0'])
                dependency_lock(rejected, env)
                install_failure(project_cli(rejected, env, 'install', '--no-root'), 'incompatible-wheel')
                assert 'incompatible-wheel' not in installation_state(rejected, env)['installed']


def test_dependency_build_settings_requirements_and_constraints(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    wheels = [factory.create(n, v)[1] for n in ('build-seed', 'build-extra') for v in ('1.0', '2.0')]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', wheels) as url:
        directory = generated_dependency(tmp_path / 'dependency', url)
        template = dependency_project(tmp_path / 'template', url,
            legacy='generated-dependency={path=' + json.dumps(str(directory)) + '}')
        dependency_lock(template, env)
        for label, constraints, settings, expected in [
            ('latest', '', {'flavour': 'plain'}, ['build-seed:2.0', 'build-extra:2.0', 'plain']),
            ('constrained', 'build-seed="<2",build-extra="<2"', {'flavour': 'limited'}, ['build-seed:1.0', 'build-extra:1.0', 'limited']),
            ('unsatisfiable', 'build-seed="<1"', {'flavour': 'plain'}, None),
            ('failed-build', '', {'fail': 'yes'}, None)]:
            project = installation_clone(template, tmp_path / label)
            if constraints:
                document = project / 'pyproject.toml'
                document.write_text(legacy_document(document.read_text() + '\n[tool.<legacy>.build-constraints]\ngenerated-dependency={' + constraints + '}\n'))
            save_setting(project, env, 'installer.build-config-settings.generated-dependency', json.dumps(settings), local=True)
            seed_installation(project, env, [factory.create(n, '2.0')[1] for n in ('build-seed', 'build-extra')])
            result = project_cli(project, env, 'install', '--no-root')
            if expected is None:
                install_failure(result, 'generated-dependency')
                assert 'generated-dependency' not in installation_state(project, env)['installed']
            else:
                succeeded(result)
                built = installation_state(project, env, ['generated-dependency'])['values']['generated-dependency']
                if label == 'latest':
                    assert built[0] in {'build-seed:1.0', 'build-seed:2.0'}
                    assert built[1] in {'build-extra:1.0', 'build-extra:2.0'}
                    assert built[2] == 'plain'
                else:
                    assert built == expected
                metadata = installation_probe(project, env, '''import importlib.metadata as m,json
print(json.dumps(m.distribution('generated-dependency').requires or []))''')
                assert not {canonicalize_name(Requirement(r).name) for r in metadata} & {'build-seed', 'build-extra'}
                records = locked_by_name(read_toml(project / 'velnora.lock')['package'])
                assert set(records) == {'generated-dependency'}
                declaration = read_toml(project / 'pyproject.toml')
                assert declaration['project']['dependencies'] == []
                assert set(declaration['tool'][legacy_key()]['dependencies']) == {'generated-dependency'}


def test_binary_policy_precedence_conflicts_and_integrity(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    source, wheel = factory.create('policy-package')
    sdist = build_archives(source, factory.env, '--format', 'sdist')['sdist']
    env = project_environment(tmp_path / 'env')
    # Single-format repositories make policy effects observable without imposing
    # a preference between two permitted candidates.
    for label, binary, source_allowed, no_binary, only_binary, permitted in [
        ('default-wheel', True, False, None, None, True),
        ('default-source', False, True, None, None, True),
        ('no-wheel', True, False, ':all:', None, False),
        ('only-wheel', False, True, None, ':all:', False),
        ('named-no-wheel', True, False, 'policy-package', None, False),
        ('named-only-wheel', False, True, None, 'policy-package', False),
        ('named-binary-wins', True, False, ':all:', 'policy-package', True),
        ('named-source-wins', False, True, 'policy-package', ':all:', True),
        ('both-forbidden', True, True, 'policy-package', 'policy-package', False)]:
        index_root = tmp_path / ('index-' + label)
        with distribution_index(index_root, [wheel] if binary else []) as url:
            if source_allowed:
                publish_source(index_root, sdist, 'policy-package')
            project = dependency_project(tmp_path / label, url, standard=['policy-package==1.0'])
            local_env = project_environment(tmp_path / (label + '-env'))
            dependency_lock(project, local_env)
            for key, value in [('installer.no-binary', no_binary), ('installer.only-binary', only_binary)]:
                if value is not None:
                    save_setting(project, local_env, key, value, local=True)
            result = project_cli(project, local_env, 'install', '--no-root')
            if permitted:
                succeeded(result)
                assert installation_state(project, local_env, ['policy-package'])['values'] == {'policy-package': 'policy-package:1.0'}
            else:
                install_failure(result, 'policy-package')
                assert 'policy-package' not in installation_state(project, local_env)['installed']
    with distribution_index(tmp_path / 'integrity-index', [wheel]) as url:
        project = dependency_project(tmp_path / 'integrity', url, standard=['policy-package==1.0'])
        dependency_lock(project, env)
        target = tmp_path / 'integrity-index' / 'files' / wheel.name
        target.write_bytes(wheel.read_bytes() + b'altered archive identity\n')
        install_failure(project_cli(project, env, 'install', '--no-root'), 'policy-package')
        assert 'policy-package' not in installation_state(project, env)['installed']


def test_dry_run_reports_actions_without_applying_changes(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    wheels = [factory.create('preview-update', v)[1] for v in ('1.0', '2.0')]
    wheels += [factory.create(n)[1] for n in ('preview-install', 'preview-remove')]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', wheels) as url:
        template = dependency_project(tmp_path / 'template', url,
            standard=['preview-update==2.0', 'preview-install==1.0'])
        dependency_lock(template, env)
        for action in ('install', 'sync'):
            project = installation_clone(template, tmp_path / action)
            seed_installation(project, env, [wheels[0], wheels[-1]])
            before_packages = installation_state(project, env)['installed']
            before_files = snapshot_files([project / 'pyproject.toml', project / 'velnora.lock'])
            before_environment = snapshot_tree(project / '.venv')
            result = succeeded(project_cli(project, env, action, '--no-root', '--dry-run'))
            lines = operation_lines(result.stdout)
            assert ('Installing', 'preview-install', (Version('1.0'),), False) in lines, result.stdout
            assert ('Updating', 'preview-update', (Version('1.0'), Version('2.0')), False) in lines, result.stdout
            # Only synchronization proposes removing the unrelated installed package.
            assert (('Removing', 'preview-remove', (Version('1.0'),), False) in lines) == (action == 'sync'), result.stdout
            assert snapshot_files([project / 'pyproject.toml', project / 'velnora.lock']) == before_files
            assert snapshot_tree(project / '.venv') == before_environment
            assert installation_state(project, env)['installed'] == before_packages
            succeeded(project_cli(project, env, action, '--no-root'))
            actual = installation_state(project, env, ['preview-update', 'preview-install'])
            assert actual['values'] == {'preview-update': 'preview-update:2.0', 'preview-install': 'preview-install:1.0'}
            assert ('preview-remove' in actual['installed']) == (action == 'install')


def test_compilation_lock_creation_reuse_and_stale_refusal(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    wheels = [factory.create('compiled-package', v)[1] for v in ('1.0', '2.0')]
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', wheels) as url:
        template = dependency_project(tmp_path / 'template', url, standard=['compiled-package==1.0'])
        assert not (template / 'velnora.lock').exists()
        succeeded(project_cli(template, env, 'install', '--no-root'))
        record, = read_toml(template / 'velnora.lock')['package']
        assert Version(record['version']) == Version('1.0')
        assert record['source']['url'].rstrip('/') == url + '/simple'
        assert installation_state(template, env, ['compiled-package'])['values'] == {'compiled-package': 'compiled-package:1.0'}
        declaration = template / 'pyproject.toml'
        declaration.write_text(declaration.read_text().replace('compiled-package==1.0', 'compiled-package>=1'))
        records = dependency_lock(template, env)
        assert Version(records[0]['version']) == Version('1.0')
        for label, options in [('default', ()), ('compiled', ('--compile',))]:
            project = installation_clone(template, tmp_path / label)
            lock_document = read_toml(project / 'velnora.lock')
            succeeded(project_cli(project, env, 'install', '--no-root', *options))
            assert read_toml(project / 'velnora.lock') == lock_document
            observed = installation_probe(project, env, '''import importlib.util,json,pathlib
spec=importlib.util.find_spec('compiled_package')
source=pathlib.Path(spec.origin)
print(json.dumps({'source':str(source),'bytecode':[str(p) for p in source.parent.rglob('*.pyc')]}))''')
            bytecodes = observed['bytecode']
            assert bool(bytecodes) == bool(options)
            for bytecode in bytecodes:
                result = installation_probe(project, env, '''import importlib.machinery,importlib.util,json
loader=importlib.machinery.SourcelessFileLoader('bytecode_subject', BYTECODE)
spec=importlib.util.spec_from_loader(loader.name,loader)
module=importlib.util.module_from_spec(spec)
loader.exec_module(module)
print(json.dumps(module.value()))'''.replace('BYTECODE', repr(str(bytecode))))
                assert result == 'compiled-package:1.0'
            assert installation_state(project, env, ['compiled-package'])['values'] == {'compiled-package': 'compiled-package:1.0'}
        declaration = template / 'pyproject.toml'
        lock_document = read_toml(template / 'velnora.lock')
        declaration.write_text(declaration.read_text().replace('compiled-package>=1', 'compiled-package==2.0'))
        refused(project_cli(template, env, 'install', '--no-root'), 'velnora.lock', 'lock')
        assert read_toml(template / 'velnora.lock') == lock_document
        assert installation_state(template, env, ['compiled-package'])['values'] == {'compiled-package': 'compiled-package:1.0'}
