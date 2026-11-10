# feature: F20
"""Acceptance checks for repository cache inspection, clearing and bypass."""
from pathlib import Path
from packaging.version import Version

from F01_helpers import project_environment, refused, succeeded
from F04_helpers import DistributionFactory, distribution_index
from F20_helpers import (cache_command, cache_consumer, cached_selection, cache_scopes,
                         populated_caches, replace_index_wheel)


def stored_files(directory):
    return {path.relative_to(directory): path.read_bytes()
            for path in directory.rglob('*') if path.is_file()} if directory.exists() else {}


def test_cache_listing(tmp_path):
    empty_env = project_environment(tmp_path / 'empty-env')
    empty = succeeded(cache_command(tmp_path, empty_env, 'list'))
    assert empty.stdout == ''
    assert empty.stderr.strip()
    with populated_caches(tmp_path / 'populated') as (env, _):
        shown = succeeded(cache_command(tmp_path, env, 'list'))
        assert set(shown.stdout.splitlines()) == {'north', 'south'}


def test_cache_clearing_scopes_and_confirmation(tmp_path):
    with populated_caches(tmp_path) as (env, url):
        expected = {('north', 'cache-widget', '1.0'), ('north', 'cache-widget', '2.0'),
                    ('north', 'cache-companion', '1.0'), ('south', 'cache-widget', '1.0')}
        selections = {':'.join(key) for key in expected}
        def observe():
            return {key for key in selections if cached_selection(
                tmp_path, env, url, key, dependency='cache-proof-leaf')}
        assert observe() == selections
        saved = set(selections)
        for selection in [(), ('north',), ('north:cache-widget',)]:
            refused(cache_command(tmp_path, env, 'clear', *selection))
            assert observe() == saved
        for selection in [('--all',), ('north', '--all'), ('north:cache-widget:1.0',)]:
            succeeded(cache_command(tmp_path, env, 'clear', *selection, answer='no\n'))
            assert observe() == saved
        for selection, subject in [(('unknown', '--all'), 'unknown'),
                                    (('north:cache-widget:9.0',), 'cache-widget:9.0')]:
            absent = succeeded(cache_command(tmp_path, env, 'clear', *selection))
            assert absent.stdout.strip() and subject in absent.stdout
            assert observe() == saved
        succeeded(cache_command(tmp_path, env, 'clear', 'north:cache-widget:1.0', answer='yes\n'))
        expected.remove(('north', 'cache-widget', '1.0'))
        assert observe() == {':'.join(key) for key in expected}
        repositories = Path(env['VELNORA_CACHE_DIR']) / 'cache' / 'repositories'
        south_files = stored_files(repositories / 'south')
        assert south_files and stored_files(repositories / 'north')
        succeeded(cache_command(tmp_path, env, 'clear', 'north', '--all', answer='yes\n'))
        # The stored repository cache itself is gone; the other repository's is untouched.
        assert not stored_files(repositories / 'north')
        assert stored_files(repositories / 'south') == south_files
        expected = {key for key in expected if key[0] != 'north'}
        assert observe() == {':'.join(key) for key in expected}
        assert 'south' in cache_scopes(tmp_path, env)
        # Repopulate from the original release metadata, then change the origin again.
        factory = DistributionFactory(tmp_path / 'repopulation-build')
        original = factory.create('cache-widget', '2.0')[1]
        replacement = factory.create('cache-widget', '2.0', dependencies=['cache-proof-leaf==1.0'])[1]
        replace_index_wheel(tmp_path / 'index', original)
        cache_consumer(tmp_path / 'repopulate', env, url, 'north', ['cache-widget==2.0'])
        replace_index_wheel(tmp_path / 'index', replacement)
        expected.add(('north', 'cache-widget', '2.0'))
        assert observe() == {':'.join(key) for key in expected}
        succeeded(cache_command(tmp_path, env, 'clear', '--all', answer='yes\n'))
        assert not stored_files(repositories)
        assert observe() == set()
        assert cache_scopes(tmp_path, env) == set()
        absent = succeeded(cache_command(tmp_path, env, 'clear', '--all'))
        assert absent.stdout.strip()


def test_no_cache_obtains_current_metadata_without_deleting_cache(tmp_path):
    factory = DistributionFactory(tmp_path / 'build')
    old = factory.create('changing-widget', '1.0')[1]
    dependency = factory.create('fresh-companion', '3.0')[1]
    replacement = factory.create('changing-widget', '1.0', dependencies=['fresh-companion==3.0'])[1]
    env = project_environment(tmp_path / 'env')
    index = tmp_path / 'index'
    with distribution_index(index, [old, dependency]) as url:
        baseline = cache_consumer(tmp_path / 'baseline', env, url, 'live', ['changing-widget==1.0'])
        assert set(baseline) == {'changing-widget'}
        cache_consumer(tmp_path / 'reserve', env, url, 'reserve', ['fresh-companion==3.0'])
        repositories = Path(env['VELNORA_CACHE_DIR']) / 'cache' / 'repositories'
        reserve_files = stored_files(repositories / 'reserve')
        assert reserve_files
        scopes = cache_scopes(tmp_path, env)
        replace_index_wheel(index, replacement)
        assert cached_selection(tmp_path, env, url, 'live:changing-widget:1.0',
                                dependency='fresh-companion')
        current = cache_consumer(tmp_path / 'current', env, url, 'live',
                                 ['changing-widget==1.0'], bypass=True)
        assert set(current) == {'changing-widget', 'fresh-companion'}
        assert set(current['changing-widget']['dependencies']) == {'fresh-companion'}
        assert Version(current['fresh-companion']['version']) == Version('3.0')
        assert scopes <= cache_scopes(tmp_path, env)
        assert cached_selection(tmp_path, env, url, 'live:changing-widget:1.0',
                                dependency='fresh-companion')
        assert stored_files(repositories / 'reserve') == reserve_files
