# feature: F19
"""Acceptance checks for management of the product's own runtime."""
from F00_documents import legacy_key
from pathlib import Path

from packaging.version import Version
from _helpers import read_toml, snapshot_tree
from F01_helpers import refused, succeeded
from F12_helpers import plugin_contribution
from F15_helpers import equivalent_constraint
from F13_helpers import maintenance_requirements
from F19_helpers import (managed_runtime, self_cli, runtime_packages, runtime_lock,
                         runtime_rows, plugin_records, operation_lines, fixture_pip, active_runtime_lock)


def test_runtime_add_remove_lock_and_project_isolation(tmp_path, current_product_wheel):
    with managed_runtime(tmp_path / 'runtime', current_product_wheel) as (project, env, config, wheels):
        before = snapshot_tree(project)
        succeeded(self_cli(project, env, 'add', 'runtime-extension==1.0.0'))
        doc = read_toml(config / 'pyproject.toml')
        declared = maintenance_requirements(doc['dependency-groups']['additional'])
        assert Version('1.0.0') in declared['runtime-extension'].specifier
        assert Version('2.0.0') not in declared['runtime-extension'].specifier
        lock = runtime_lock(config)
        assert Version(lock['runtime-extension']['version']) == Version('1.0.0')
        assert Version(lock['runtime-leaf']['version']) == Version('1.0')
        versions, values = runtime_packages(project, env, ['runtime-leaf'])
        assert values == {'runtime-leaf': 'runtime-leaf:1.0'}
        assert Version(versions['runtime-extension']) == Version('1.0.0')
        plugin_contribution(project, env, '1.0.0')
        refused(self_cli(project, env, 'add', 'runtime-conflict==1.0'), 'runtime-conflict', 'velnora')
        before_lock = runtime_packages(project, env)[0]
        (config / 'velnora.lock').unlink()
        succeeded(self_cli(project, env, 'lock'))
        assert runtime_packages(project, env)[0] == before_lock
        assert Version(runtime_lock(config)['runtime-extension']['version']) == Version('1.0.0')
        succeeded(self_cli(project, env, 'install'))
        shown = runtime_rows(project, env, '--addons')
        assert set(shown) == {'runtime-extension', 'runtime-leaf'}
        assert Version(shown['runtime-extension']['version']) == Version('1.0.0')
        succeeded(self_cli(project, env, 'remove', 'runtime-extension'))
        assert 'runtime-extension' not in runtime_lock(config)
        assert 'runtime-extension' not in maintenance_requirements(read_toml(config / 'pyproject.toml').get('dependency-groups', {}).get('additional', []))
        assert 'runtime-extension' not in runtime_packages(project, env)[0]
        assert plugin_records(succeeded(self_cli(project, env, 'show', 'plugins')).stdout) == {}
        assert snapshot_tree(project) == before


def test_runtime_install_sync_preserve_product_and_requirements(tmp_path, current_product_wheel):
    with managed_runtime(tmp_path / 'runtime', current_product_wheel) as (project, env, config, wheels):
        succeeded(self_cli(project, env, 'add', 'runtime-extension==1.0.0'))
        fixture_pip(project, env, 'uninstall', '-y', 'runtime-extension', 'runtime-leaf')
        extra = next(w for w in wheels if w.name.startswith('runtime_extra-'))
        fixture_pip(project, env, 'install', '--no-index', '--no-deps', str(extra))
        succeeded(self_cli(project, env, 'install'))
        installed, values = runtime_packages(project, env, ['runtime-leaf', 'runtime-extra'])
        assert values == {'runtime-leaf': 'runtime-leaf:1.0', 'runtime-extra': 'runtime-extra:1.0'}
        assert 'runtime-extension' in installed
        plugin_contribution(project, env, '1.0.0')
        succeeded(self_cli(project, env, 'sync'))
        after, values = runtime_packages(project, env, ['runtime-leaf'])
        assert values == {'runtime-leaf': 'runtime-leaf:1.0'}
        assert after == {name: version for name, version in installed.items() if name != 'runtime-extra'}
        for name, row in active_runtime_lock(config).items():
            assert name in after and Version(after[name]) == Version(row['version']), (name, after)
        assert 'velnora' in after
        plugin_contribution(project, env, '1.0.0')
        succeeded(self_cli(project, env, 'show', '--format=json'))


def test_runtime_inspection_plugins_and_missing_lock(tmp_path, current_product_wheel):
    with managed_runtime(tmp_path / 'runtime', current_product_wheel) as (project, env, config, wheels):
        refused(self_cli(project, env, 'show', '--format=json'), 'velnora.lock')
        assert plugin_records(succeeded(self_cli(project, env, 'show', 'plugins')).stdout) == {}
        succeeded(self_cli(project, env, 'add', 'runtime-extension==2.0.0'))
        succeeded(self_cli(project, env, 'add', 'runtime-extra==1.0'))
        rows = runtime_rows(project, env)
        lock = active_runtime_lock(config)
        installed = runtime_packages(project, env)[0]
        assert set(rows) == set(lock) == set(installed)
        for name, row in rows.items():
            assert Version(row['version']) == Version(lock[name]['version']) == Version(installed[name])
        addons = runtime_rows(project, env, '--addons')
        assert set(addons) == {'runtime-extension', 'runtime-leaf', 'runtime-extra'}
        assert Version(addons['runtime-extension']['version']) == Version('2.0.0')
        plugins = plugin_records(succeeded(self_cli(project, env, 'show', 'plugins')).stdout)
        assert set(plugins) == {'runtime-extension'}
        assert Version(plugins['runtime-extension']['version']) == Version('2.0.0')
        requirements = plugins['runtime-extension']['requirements']
        assert set(requirements) == {'runtime-leaf'}
        equivalent_constraint(requirements['runtime-leaf'], ['1.0'], ['2.0'])
        succeeded(self_cli(project, env, 'remove', 'runtime-extension'))
        assert plugin_records(succeeded(self_cli(project, env, 'show', 'plugins')).stdout) == {}
        (config / 'velnora.lock').unlink()
        refused(self_cli(project, env, 'show', '--format=json'), 'velnora.lock')


def test_runtime_previews_report_operations_without_installing(tmp_path, current_product_wheel):
    from F19_helpers import published_runtime_releases
    releases = published_runtime_releases(tmp_path / 'releases')
    with managed_runtime(tmp_path / 'runtime', current_product_wheel, releases) as (project, env, config, wheels):
        succeeded(self_cli(project, env, 'add', 'runtime-extension==1.0.0'))
        before = runtime_packages(project, env)[0]
        runtime_path = Path(env['F12_RUNTIME_PYTHON']).parent.parent
        files_before = snapshot_tree(runtime_path)
        target = Version('2.5.0')
        current_version = Version(before['velnora'])
        action = 'Updating' if target > current_version else 'Downgrading'
        update = (action, 'velnora', (Version(before['velnora']), target), False)
        if target == current_version:
            update = ('Installing', 'velnora', (Version(before['velnora']),), True)
        cases = [
            (('update', '>=2.5.0,<2.5.1'), update),
            (('add', 'runtime-extra==1.0'), ('Installing', 'runtime-extra', (Version('1.0'),), False)),
            (('remove', 'runtime-extension'), ('Removing', 'runtime-extension', (Version('1.0.0'),), False)),
            (('add', 'runtime-extension==2.0.0'), ('Updating', 'runtime-extension', (Version('1.0.0'), Version('2.0.0')), False)),
        ]
        for arguments, record in cases:
            report = succeeded(self_cli(project, env, *arguments, '--dry-run'))
            assert record in operation_lines(report.stdout), report.stdout
            assert runtime_packages(project, env)[0] == before
            assert snapshot_tree(runtime_path) == files_before
        current = before['velnora']
        report = succeeded(self_cli(project, env, 'update', current, '--dry-run'))
        assert ('Installing', 'velnora', (Version(current),), True) in operation_lines(report.stdout), report.stdout
        assert not [r for r in operation_lines(report.stdout) if r[1] == 'velnora' and not r[3]], report.stdout
        assert runtime_packages(project, env)[0] == before
        assert snapshot_tree(runtime_path) == files_before


def test_runtime_update_constraint_release_and_source_isolation(tmp_path, current_product_wheel):
    import hashlib
    import re
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from _helpers import read_zip
    from F01_helpers import project_cli
    from F19_helpers import published_runtime_releases, installed_release

    releases = published_runtime_releases(tmp_path / 'releases')
    with managed_runtime(tmp_path / 'runtime', current_product_wheel, releases) as (project, env, config, wheels):
        from packaging.utils import parse_wheel_filename
        from packaging.specifiers import SpecifierSet
        from _helpers import parse_metadata
        import platform
        available = [*releases, *(config.parent / 'runtime-wheels').glob('*.whl'),
                     *Path('/opt/offline-wheels').glob('*.whl')]
        candidates = {}
        for artifact in available:
            name, version, _, _ = parse_wheel_filename(artifact.name)
            if name != 'velnora' or version.is_prerelease:
                continue
            contents = read_zip(artifact)
            metadata, = [parse_metadata(data) for name, data in contents.items()
                         if name.endswith('.dist-info/METADATA')]
            if Version(platform.python_version()) in SpecifierSet(metadata.get('Requires-Python', '')):
                candidates[version] = {name: hashlib.sha256(data).hexdigest()
                                      for name, data in contents.items()
                                      if name.startswith('velnora/') and name.endswith('.py')}
        latest = max(candidates)
        # Update to a stored stable release other than the one already installed.
        # The documents never fix the product's own version, so it may be any of them.
        installed_now = Version(runtime_packages(project, env)[0]['velnora'])
        release_wheel = next(w for w in releases
                             if parse_wheel_filename(w.name)[0] == 'velnora'
                             and not parse_wheel_filename(w.name)[1].is_prerelease
                             and parse_wheel_filename(w.name)[1] != installed_now)
        chosen = parse_wheel_filename(release_wheel.name)[1]
        payload = {name: hashlib.sha256(data).hexdigest()
                   for name, data in read_zip(release_wheel).items()
                   if name.startswith('velnora/') and name.endswith('.py')}
        major, minor, micro = chosen.release[:3]
        project_before = snapshot_tree(project)
        sources = read_toml(config / 'pyproject.toml')['tool'][legacy_key()]['source']
        report = succeeded(self_cli(project, env, 'update',
                                    f'>={chosen},<{major}.{minor}.{micro + 1}'))
        observed = installed_release(project, env)
        assert Version(observed['version']) == chosen
        assert observed['files'] == payload
        startup = succeeded(project_cli(project, env, '--version'))
        match = re.fullmatch(r'Velnora \(version ([^)]+)\)\n?', startup.stdout)
        assert match and Version(match[1]) == chosen, startup
        installed = runtime_packages(project, env)[0]
        for text in observed['requirements']:
            requirement = Requirement(text)
            if requirement.marker is None or requirement.marker.evaluate({**default_environment(), 'extra': ''}):
                from packaging.utils import canonicalize_name
                assert Version(installed[canonicalize_name(requirement.name)]) in requirement.specifier
        assert read_toml(config / 'pyproject.toml')['tool'][legacy_key()]['source'] == sources
        assert snapshot_tree(project) == project_before
        # An unconstrained update selects the repository's newest stable release.
        succeeded(self_cli(project, env, 'update'))
        updated = installed_release(project, env)
        assert Version(updated['version']) == latest
        assert updated['files'] == candidates[latest]
        assert read_toml(config / 'pyproject.toml')['tool'][legacy_key()]['source'] == sources
        assert snapshot_tree(project) == project_before

        # The same available releases and constraint differ only in prerelease permission.
        constraint = SpecifierSet('>=1.1,<2')
        release_versions = {parse_wheel_filename(w.name)[1] for w in releases
                            if parse_wheel_filename(w.name)[0] == 'velnora'}
        eligible = {v for v in release_versions if constraint.contains(v, prereleases=True)}
        assert any(v.is_prerelease for v in eligible)
        stable = max(v for v in eligible if not v.is_prerelease)
        preview = max(eligible)
        assert preview > stable and preview.is_prerelease
        before_preview = runtime_packages(project, env)[0]
        for options, target in [((), stable), (('--preview',), preview)]:
            report = succeeded(self_cli(project, env, 'update', str(constraint), '--dry-run', *options))
            current_version = Version(before_preview['velnora'])
            action = 'Updating' if target > current_version else 'Downgrading'
            expected = (action, 'velnora', (Version(before_preview['velnora']), target), False)
            assert expected in operation_lines(report.stdout), report.stdout
            assert runtime_packages(project, env)[0] == before_preview
        assert read_toml(config / 'pyproject.toml')['tool'][legacy_key()]['source'] == sources
        assert snapshot_tree(project) == project_before
