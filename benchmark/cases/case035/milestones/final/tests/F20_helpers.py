# feature: F20
"""Real repository consumption and public cache-scope observations."""
from contextlib import contextmanager
import hashlib
from pathlib import Path
import shutil
import tempfile

from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

from _helpers import make_environment, read_toml, run_cli
from F01_helpers import project_environment, project_cli, succeeded
from F04_helpers import DistributionFactory, distribution_index, locked_by_name
from F05_helpers import source_project


def cached_selection(path, env, url, selection, *, dependency):
    """Consume candidate-produced metadata without repopulating the tested cache."""
    repository, package, version = selection.split(':')
    with tempfile.TemporaryDirectory(prefix='cache-observation-', dir=path) as directory:
        root = Path(directory)
        cache = root / 'cache'
        repositories = Path(env['VELNORA_CACHE_DIR']) / 'cache' / 'repositories'
        if repositories.exists():
            shutil.copytree(repositories, cache / 'cache' / 'repositories')
        observed_env = make_environment(env, updates={'VELNORA_CACHE_DIR': str(cache)})
        records = cache_consumer(root / 'consumer', observed_env, url, repository,
                                 [package + '==' + version])
        assert Version(records[package]['version']) == Version(version), records
        assert set(records) in ({package}, {package, dependency}), records
        return dependency not in records


def cache_scopes(path, env):
    result = succeeded(cache_command(path, env, 'list'))
    if not result.stdout:
        assert result.stderr.strip(), result
        return set()
    return set(result.stdout.splitlines())


def cache_command(path, env, *args, answer=''):
    interactive = make_environment(env, remove=('VELNORA_NO_INTERACTION',))
    return run_cli(('velnora',), ('--no-ansi', 'cache', *args),
                   cwd=path, env=interactive, stdin=answer, timeout=60)


def cache_consumer(path, env, url, repository, dependencies, *, bypass=False):
    source_project(path, [(repository, url + '/simple/', 'primary')],
                   dependencies=dependencies)
    flags = ('--no-cache',) if bypass else ()
    succeeded(project_cli(path, env, *flags, 'lock', '--regenerate'))
    return locked_by_name(read_toml(path / 'velnora.lock')['package'])


@contextmanager
def populated_caches(root):
    factory = DistributionFactory(root / 'build')
    wheels = [factory.create(name, version)[1] for name, version in
              [('cache-widget', '1.0'), ('cache-widget', '2.0'), ('cache-companion', '1.0')]]
    witness = factory.create('cache-proof-leaf')[1]
    replacements = [factory.create(name, version, dependencies=['cache-proof-leaf==1.0'])[1]
                    for name, version in [('cache-widget', '1.0'), ('cache-widget', '2.0'),
                                          ('cache-companion', '1.0')]]
    env = project_environment(root / 'env')
    with distribution_index(root / 'index', [*wheels, witness]) as url:
        for i, (repository, dependencies) in enumerate([
                ('north', ['cache-widget==1.0', 'cache-companion==1.0']),
                ('north', ['cache-widget==2.0']),
                ('south', ['cache-widget==1.0'])]):
            cache_consumer(root / ('consumer-' + str(i)), env, url, repository, dependencies)
        for replacement in replacements:
            replace_index_wheel(root / 'index', replacement)
        yield env, url


def replace_index_wheel(index, wheel):
    """Publish a newly built artifact at the same repository URL."""
    name, _, _, _ = parse_wheel_filename(wheel.name)
    shutil.copyfile(wheel, index / 'files' / wheel.name)
    links = []
    for artifact in sorted((index / 'files').glob('*.whl')):
        artifact_name, _, _, _ = parse_wheel_filename(artifact.name)
        if artifact_name == name:
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            links.append(f'<a href="/files/{artifact.name}#sha256={digest}">{artifact.name}</a>')
    (index / 'simple' / name / 'index.html').write_text('\n'.join(links), encoding='utf-8')
