# feature: F05
"""Package-source management and real resolution through offline repositories."""
from F00_documents import legacy_key
from contextlib import ExitStack

from packaging.version import Version
from packaging.specifiers import SpecifierSet

from _helpers import read_toml
from F01_helpers import project_cli, project_environment, refused, succeeded
from F04_helpers import DistributionFactory, distribution_index, installed_values
from F05_helpers import (pypi_transport, source_lock, source_project,
                         source_repository, source_rows)


def test_source_management_and_invalid_changes(tmp_path):
    env = project_environment(tmp_path / 'env')
    path = source_project(tmp_path / 'project')
    with distribution_index(tmp_path / 'index-a', []) as a, distribution_index(tmp_path / 'index-b', []) as b:
        succeeded(project_cli(path, env, 'source', 'add', '--priority=primary', 'general', a + '/simple/'))
        succeeded(project_cli(path, env, 'source', 'add', '--priority=supplemental', 'reserve', b + '/simple/'))
        succeeded(project_cli(path, env, 'source', 'add', '--priority=explicit', 'general', b + '/simple/'))
        records = {r['name']: {key: r[key] for key in ('name', 'url', 'priority')}
                   for r in read_toml(path / 'pyproject.toml')['tool'][legacy_key()]['source']}
        assert records == {'general': {'name': 'general', 'url': b + '/simple/', 'priority': 'explicit'},
                           'reserve': {'name': 'reserve', 'url': b + '/simple/', 'priority': 'supplemental'}}
        shown = succeeded(project_cli(path, env, 'source', 'show'))
        assert {r['name']: r for r in source_rows(shown.stdout)} == records
        assert source_rows(succeeded(project_cli(path, env, 'source', 'show', 'general')).stdout) == [records['general']]
        refused(project_cli(path, env, 'source', 'show', 'missing-source'), 'missing-source')
        for args in [('custom-without-url',), ('PyPI', a + '/simple/')]:
            before = read_toml(path / 'pyproject.toml')
            refused(project_cli(path, env, 'source', 'add', *args))
            assert read_toml(path / 'pyproject.toml') == before
        succeeded(project_cli(path, env, 'source', 'remove', 'general'))
        assert source_rows(succeeded(project_cli(path, env, 'source', 'show')).stdout) == [records['reserve']]
        saved = read_toml(path / 'pyproject.toml')['tool'][legacy_key()]['source']
        assert [{key: r[key] for key in ('name', 'url', 'priority')} for r in saved] == [records['reserve']]
        before = read_toml(path / 'pyproject.toml')
        refused(project_cli(path, env, 'source', 'remove', 'missing-source'), 'missing-source')
        assert read_toml(path / 'pyproject.toml') == before


def test_default_priority_and_pypi_activation(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    _, public = factory.create('activation-package', '2.0')
    _, custom = factory.create('activation-package', '1.0')
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', [custom]) as url, pypi_transport(tmp_path / 'tls', env, [public]) as (routed, _):
        configurations = [
            ('implicit', [], '2.0', None),
            ('supplemental', [('local', url + '/simple/', 'supplemental')], '2.0', None),
            ('default', [('local', url + '/simple/', None)], '1.0', 'local'),
            ('primary', [('local', url + '/simple/', 'primary')], '1.0', 'local'),
            ('explicit-pypi', [('local', url + '/simple/', 'primary'), ('PyPI', None, 'primary')], '2.0', None),
        ]
        for name, sources, version, origin in configurations:
            path = source_project(tmp_path / name, [] if name == 'default' else sources, dependencies=['activation-package>=1'])
            if name == 'default':
                succeeded(project_cli(path, routed, 'source', 'add', 'local', url + '/simple/'))
                assert read_toml(path / 'pyproject.toml')['tool'][legacy_key()]['source'][0].get('priority', 'primary') == 'primary'
            record = source_lock(path, routed)['activation-package']
            assert Version(record['version']) == Version(version)
            if origin is None:
                assert 'source' not in record
            else:
                assert record['source']['reference'] == origin
            rows = source_rows(succeeded(project_cli(path, routed, 'source', 'show')).stdout)
            assert {r['name']: r['priority'] for r in rows} == {
                n: p or 'primary' for n, _, p in sources}
        path = source_project(tmp_path / 'invalid', [('local', url + '/simple/', 'explicit'), ('PyPI', None, 'explicit')])
        refused(project_cli(path, routed, 'lock'))
        assert not (path / 'velnora.lock').exists()
        path = source_project(tmp_path / 'invalid-proposed',
            [('local', url + '/simple/', 'primary'), ('PyPI', None, 'explicit')])
        before = read_toml(path / 'pyproject.toml')
        refused(project_cli(path, routed, 'source', 'add', '--priority=explicit', 'local', url + '/simple/'))
        assert read_toml(path / 'pyproject.toml') == before


def test_primary_candidates_and_source_precedence(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    _, lower = factory.create('combined-package', '1.0')
    _, higher = factory.create('combined-package', '2.0')
    _, shared = factory.create('shared-release', '1.0')
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'a', [lower, shared]) as a, distribution_index(tmp_path / 'b', [higher, shared]) as b:
        # Reverse the order from identical initial states to measure precedence.
        for name, sources, shared_origin in [
            ('ab', [('first', a + '/simple/', 'primary'), ('second', b + '/simple/', 'primary')], 'first'),
            ('ba', [('second', b + '/simple/', 'primary'), ('first', a + '/simple/', 'primary')], 'second'),
        ]:
            path = source_project(tmp_path / name, sources, dependencies=['combined-package>=1', 'shared-release==1.0'])
            records = source_lock(path, env)
            assert Version(records['combined-package']['version']) == Version('2.0')
            assert records['combined-package']['source']['reference'] == 'second'
            assert records['shared-release']['source']['reference'] == shared_origin


def test_supplemental_candidate_gating_and_transitive_conflict(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    _, primary = factory.create('gated-package', '1.0')
    _, reserve = factory.create('gated-package', '2.0')
    _, later = factory.create('gated-package', '3.0')
    _, prerelease = factory.create('release-filtered', '4.0rc1')
    _, stable = factory.create('release-filtered', '3.0')
    _, conflict = factory.create('conflict-package', '2.0', dependencies=['conflict-leaf==1.0'])
    _, alternative = factory.create('conflict-package', '2.0', dependencies=['conflict-leaf==2.0'])
    _, leaf1 = factory.create('conflict-leaf', '1.0')
    _, leaf2 = factory.create('conflict-leaf', '2.0')
    # The narrowing comes from another package's requirement, not the declaration.
    _, narrowing = factory.create('narrow-parent', '1.0', dependencies=['gated-package>=2'])
    env = project_environment(tmp_path / 'env')
    with ExitStack() as stack:
        urls = [stack.enter_context(distribution_index(tmp_path / str(i), wheels))
                for i, wheels in enumerate(([primary, prerelease, conflict, leaf1, leaf2, narrowing], [reserve, stable, alternative], [later]))]
        sources = [(name, url + '/simple/', priority) for name, url, priority in
                   zip(('main', 'reserve', 'last'), urls, ('primary', 'supplemental', 'supplemental'))]
        for name, requirement, version, origin in [
            ('primary-wins', 'gated-package>=1', '1.0', 'main'),
            ('version-filter', 'gated-package>=2', '2.0', 'reserve'),
            ('later-source', 'gated-package>=3', '3.0', 'last'),
            ('release-filter', 'release-filtered>=1', '3.0', 'reserve'),
            ('combined-filter', 'gated-package>=1', '2.0', 'reserve'),
        ]:
            extra = ['narrow-parent==1.0'] if name == 'combined-filter' else []
            path = source_project(tmp_path / name, sources, dependencies=[requirement, *extra],
                bindings='release-filtered={version=">=1",allow-prereleases=false}' if name == 'release-filter' else '')
            record = source_lock(path, env)[requirement.split('>')[0]]
            assert Version(record['version']) == Version(version)
            assert record['source']['reference'] == origin
        path = source_project(tmp_path / 'conflict', sources, dependencies=['conflict-package>=1', 'conflict-leaf==2.0'])
        refused(project_cli(path, env, 'lock'), 'conflict-package', 'conflict-leaf')
        assert not (path / 'velnora.lock').exists()


def test_explicit_sources_and_noninherited_constraints(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    _, ordinary = factory.create('ordinary-package', '1.0')
    _, private = factory.create('ordinary-package', '9.0')
    _, parent = factory.create('private-parent', dependencies=['shared-child>=1'])
    _, public_child = factory.create('shared-child', '1.0')
    _, private_child = factory.create('shared-child', '9.0')
    _, outside = factory.create('outside-only', '1.0')
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'public', [ordinary, public_child, outside]) as a, distribution_index(tmp_path / 'private', [private, parent, private_child]) as b:
        sources = [('general', a + '/simple/', 'primary'), ('named', b + '/simple/', 'explicit')]
        path = source_project(tmp_path / 'unbound', sources, dependencies=['ordinary-package>=1'])
        record = source_lock(path, env)['ordinary-package']
        assert Version(record['version']) == Version('1.0')
        assert record['source']['reference'] == 'general'
        for priority in ('primary', 'supplemental', 'explicit'):
            path = source_project(tmp_path / priority,
                [sources[0], ('named', b + '/simple/', priority)],
                bindings='private-parent={version="*",source="named"}\nordinary-package={version="*",source="named"}')
            records = source_lock(path, env)
            assert records['private-parent']['source']['reference'] == 'named'
            assert Version(records['ordinary-package']['version']) == Version('9.0')
            assert records['ordinary-package']['source']['reference'] == 'named'
            # With two primaries, the unconstrained child may come from either;
            # supplemental and explicit cases expose non-inheritance unambiguously.
            if priority != 'primary':
                assert Version(records['shared-child']['version']) == Version('1.0')
                assert records['shared-child']['source']['reference'] == 'general'
        path = source_project(tmp_path / 'no-cross-source', sources,
                              bindings='outside-only={version="*",source="named"}')
        refused(project_cli(path, env, 'lock'), 'outside-only')
        assert not (path / 'velnora.lock').exists()


def test_invalid_reference_and_unavailable_package_or_release(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    _, wheel = factory.create('available-package', '1.0')
    env = project_environment(tmp_path / 'env')
    with distribution_index(tmp_path / 'index', [wheel]) as url:
        sources = [('known', url + '/simple/', 'primary')]
        valid = source_project(tmp_path / 'valid', sources, bindings='available-package={version="1.0",source="known"}')
        succeeded(project_cli(valid, env, 'check'))
        assert Version(source_lock(valid, env)['available-package']['version']) == Version('1.0')
        unknown = source_project(tmp_path / 'unknown', sources, bindings='available-package={version="1.0",source="unknown-repository"}')
        result = refused(project_cli(unknown, env, 'check'), 'unknown-repository')
        assert any(line.startswith('Error:') for line in result.stderr.splitlines()), result.stderr
        for name, binding, subject in [
            ('missing-package', 'absent-package={version="*",source="known"}', 'absent-package'),
            ('missing-release', 'available-package={version="7.0",source="known"}', 'available-package'),
        ]:
            path = source_project(tmp_path / name, sources, bindings=binding)
            succeeded(project_cli(path, env, 'check'))
            refused(project_cli(path, env, 'lock'), subject)
            assert not (path / 'velnora.lock').exists()


def test_supported_repository_protocols_and_installed_metadata(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    _, leaf = factory.create('protocol-leaf', '1.0')
    _, extra = factory.create('protocol-extra', '1.0')
    _, compatible = factory.create('protocol-root', '1.0', dependencies=['protocol-leaf==1.0'], extras={'speed': ['protocol-extra==1.0']})
    # Publish a real wheel with a Python condition the project cannot satisfy.
    source, _ = factory.create('python-limited', '1.0')
    document = (source / 'pyproject.toml').read_text().replace('>=3.9', '>=3.10')
    (source / 'pyproject.toml').write_text(document)
    # Rebuild using the public command; keep metadata and listing consistent.
    succeeded(project_cli(source, factory.env, 'build', '--format', 'wheel'))
    limited, = (source / 'dist').glob('*.whl')
    env = project_environment(tmp_path / 'env')
    for style in ('html', 'json', 'single', 'pypi'):
        with ExitStack() as stack:
            if style == 'pypi':
                routed, _ = stack.enter_context(pypi_transport(tmp_path / 'tls', env, [compatible, leaf, extra, limited]))
                sources = []
            else:
                repository = stack.enter_context(source_repository([compatible, leaf, extra, limited], style='json' if style == 'json' else 'html'))
                suffix = '/links.html' if style == 'single' else '/simple/'
                sources = [('protocol', repository['url'] + suffix, 'primary')]
                routed = env
            for selection, requirement, names in [
                ('base', 'protocol-root==1.0', ['protocol-root', 'protocol-leaf']),
                ('extra', 'protocol-root[speed]==1.0', ['protocol-root', 'protocol-leaf', 'protocol-extra']),
            ]:
                path = source_project(tmp_path / (style + '-' + selection), sources, dependencies=[requirement])
                records = source_lock(path, routed)
                assert set(records) == set(names)
                assert {Version(r['version']) for r in records.values()} == {Version('1.0')}
                assert SpecifierSet(records['protocol-root']['python-versions']) == SpecifierSet('>=3.9')
                assert 'protocol-leaf' in records['protocol-root']['dependencies']
                succeeded(project_cli(path, routed, 'install', '--no-root'))
                observed = installed_values(path, routed, names)
                assert observed['values'] == {name: name + ':1.0' for name in names}
                assert set(observed['installed']) & {'protocol-root', 'protocol-leaf', 'protocol-extra'} == set(names)
            rejected = source_project(tmp_path / (style + '-python'), sources, dependencies=['python-limited==1.0'])
            refused(project_cli(rejected, routed, 'lock'), 'python-limited')
            missing = source_project(tmp_path / (style + '-unpublished'), sources, dependencies=['protocol-root==3.0'])
            refused(project_cli(missing, routed, 'lock'), 'protocol-root')
