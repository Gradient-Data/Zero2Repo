# feature: F14
"""Project creation and initialization through real command invocations."""
from urllib.parse import unquote, urlsplit

from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version

from _helpers import (make_environment, parse_json, read_toml, run_cli,
                      run_python, snapshot_tree)
from F01_helpers import (BUILD_SYSTEM, project_cli, project_environment, refused,
                         succeeded, wheel_observation, write_project)
from F10_helpers import installed_wheel_result
from F13_helpers import maintenance_requirements


def test_new_layout_identity_and_nonempty_destination(tmp_path):
    env = project_environment(tmp_path / 'environment')
    # Separate the default, layout selection and namespace distinctions; no matrix.
    for destination, options, identity, source, module in (
        ('default-project', (), 'default-project', 'src/default_project', 'default_project'),
        ('different-folder', ('--flat', '--name', 'chosen-package'),
         'chosen-package', 'chosen_package', 'chosen_package'),
        ('namespace-folder', ('--name', 'observatory.instruments'),
         'observatory-instruments', 'src/observatory/instruments', 'observatory.instruments'),
    ):
        project = tmp_path / destination
        succeeded(project_cli(tmp_path, env, 'new', str(project), *options))
        document = read_toml(project / 'pyproject.toml')
        assert canonicalize_name(document['project']['name']) == identity
        assert (project / source / '__init__.py').is_file()
        assert (project / 'tests').is_dir()
        assert any((project / 'tests').rglob('*.py'))
        assert (project / document['project']['readme']).is_file()
        assert document['build-system']['requires']
        assert document['build-system']['build-backend']
        metadata, _, _ = wheel_observation(project, env)
        assert canonicalize_name(metadata['Name']) == identity
        wheel, = (project / 'dist').glob('*.whl')
        observed = installed_wheel_result(wheel, tmp_path / (destination + '-installed'), env,
            'import importlib, json\nprint(json.dumps(importlib.import_module('
            + repr(module) + ').__name__))')
        assert observed == module
        if '--flat' in options:
            assert not (project / 'src').exists()
    occupied = tmp_path / 'occupied'
    occupied.mkdir()
    (occupied / 'keep.txt').write_text('Existing user content\n', encoding='utf-8')
    before = snapshot_tree(occupied)
    refused(project_cli(tmp_path, env, 'new', str(occupied)), str(occupied))
    assert snapshot_tree(occupied) == before


def test_init_preserves_existing_content_and_refuses_build_system(tmp_path):
    env = project_environment(tmp_path / 'environment')
    project = tmp_path / 'existing-project'
    project.mkdir()
    (project / 'application.py').write_text('VALUE = 73\n', encoding='utf-8')
    (project / 'README.md').write_text('# Existing documentation\n', encoding='utf-8')
    (project / 'pyproject.toml').write_text(
        '[tool.linter]\nline-length = 91\n[workspace]\nmembers = ["component"]\n', encoding='utf-8')
    before = snapshot_tree(project)
    succeeded(project_cli(project, env, 'init', '-n', '--name', 'existing-project'))
    document = read_toml(project / 'pyproject.toml')
    assert document['tool']['linter'] == {'line-length': 91}
    assert document['workspace'] == {'members': ['component']}
    assert document['project']['name'] == 'existing-project'
    assert document['project']['readme'] == 'README.md'
    assert document['build-system']['requires']
    after = snapshot_tree(project)
    assert {p for p in after if p.endswith('.py')} == {p for p in before if p.endswith('.py')}
    for path in before.keys() - {'pyproject.toml'}:
        assert after[path] == before[path], path
    succeeded(project_cli(project, env, 'check'))

    empty = tmp_path / 'empty-existing'
    empty.mkdir()
    succeeded(project_cli(empty, env, 'init', '-n'))
    assert not any(empty.rglob('*.py'))
    metadata = read_toml(empty / 'pyproject.toml')['project']
    if 'readme' in metadata:
        readme = metadata['readme']
        if isinstance(readme, str):
            assert (empty / readme).is_file()
        else:
            assert isinstance(readme['text'], str)
            assert isinstance(readme['content-type'], str)
    succeeded(project_cli(empty, env, 'check'))

    initialized = tmp_path / 'build-system-present'
    initialized.mkdir()
    (initialized / 'pyproject.toml').write_text(BUILD_SYSTEM, encoding='utf-8')
    before = snapshot_tree(initialized)
    refused(project_cli(initialized, env, 'init', '-n'), 'pyproject.toml')
    assert snapshot_tree(initialized) == before


def test_creation_metadata_dependencies_interaction_and_invalid_requirements(tmp_path):
    env = project_environment(tmp_path / 'environment')
    runtime = write_project(tmp_path / 'runtime',
        '[project]\nname="creation-runtime"\nversion="1.2.0"\n' + BUILD_SYSTEM)
    development = write_project(tmp_path / 'development',
        '[project]\nname="creation-development"\nversion="3.1.0"\n' + BUILD_SYSTEM)
    interpreter = succeeded(run_python('python',
        'import sys,json; print(json.dumps(list(sys.version_info[:2])))', cwd=tmp_path, env=env))
    major, minor = parse_json(interpreter.stdout)
    for command in ('new', 'init'):
        project = tmp_path / (command + '-metadata')
        project.mkdir()
        options = ('--name', command + '-metadata', '--description', 'Command supplied metadata',
            '--author', 'Setup Author <setup@example.org>', '--license', 'MIT',
            '--dependency', str(runtime), '--dev-dependency', str(development))
        if command == 'init':
            options += ('--python', '>=3.11,<4')
        args = ('new', str(project), *options) if command == 'new' else ('init', '-n', *options)
        succeeded(project_cli(project if command == 'init' else tmp_path, env, *args))
        document = read_toml(project / 'pyproject.toml')
        metadata = document['project']
        assert metadata['description'] == 'Command supplied metadata'
        assert metadata['authors'] == [{'name': 'Setup Author', 'email': 'setup@example.org'}]
        assert metadata['license'] == 'MIT'
        assert Version(metadata['version']) == Version('0.1.0')
        expected_python = f'>={major}.{minor}' if command == 'new' else '>=3.11,<4'
        assert SpecifierSet(metadata['requires-python']) == SpecifierSet(expected_python)
        main = maintenance_requirements(metadata['dependencies'])
        dev = maintenance_requirements(document['dependency-groups']['dev'])
        assert set(main) == {'creation-runtime'}
        assert set(dev) == {'creation-development'}
        for requirement, target in ((main['creation-runtime'], runtime),
                                    (dev['creation-development'], development)):
            url = urlsplit(requirement.url)
            assert url.scheme == 'file'
            assert unquote(url.path) == str(target)
        succeeded(project_cli(project, env, 'check'))

        # Interactive answers travel through the same public command as metadata.
        interactive = tmp_path / (command + '-interactive')
        interactive.mkdir()
        answers = '\n'.join((command + '-answered', '2.7.3', 'Interactive metadata',
            'Answer Author <answer@example.org>', 'BSD-3-Clause', '>=3.10,<4',
            'yes', str(runtime), '', 'yes', str(development), '', 'yes', ''))
        interactive_env = make_environment(env, remove=('VELNORA_NO_INTERACTION',))
        args = ('new', '--interactive', str(interactive)) if command == 'new' else ('init',)
        succeeded(run_cli(('velnora',), ('--no-ansi', *args),
            cwd=interactive if command == 'init' else tmp_path,
            env=interactive_env, stdin=answers, timeout=120))
        document = read_toml(interactive / 'pyproject.toml')
        metadata = document['project']
        assert metadata['name'] == command + '-answered'
        assert Version(metadata['version']) == Version('2.7.3')
        assert metadata['description'] == 'Interactive metadata'
        assert metadata['authors'] == [{'name': 'Answer Author', 'email': 'answer@example.org'}]
        assert metadata['license'] == 'BSD-3-Clause'
        assert SpecifierSet(metadata['requires-python']) == SpecifierSet('>=3.10,<4')
        main = maintenance_requirements(metadata['dependencies'])
        dev = maintenance_requirements(document['dependency-groups']['dev'])
        assert set(main) == {'creation-runtime'}
        assert set(dev) == {'creation-development'}
        for requirement, target in ((main['creation-runtime'], runtime),
                                    (dev['creation-development'], development)):
            url = urlsplit(requirement.url)
            assert url.scheme == 'file'
            assert unquote(url.path) == str(target)
        succeeded(project_cli(interactive, env, 'check'))

        invalid = tmp_path / (command + '-invalid')
        invalid.mkdir()
        before = snapshot_tree(invalid)
        args = ('new', str(invalid)) if command == 'new' else ('init', '-n')
        for option in ('--dependency', '--dev-dependency'):
            refused(project_cli(invalid if command == 'init' else tmp_path, env,
                *args, option, 'creation-runtime@>=not-version'))
            assert snapshot_tree(invalid) == before
