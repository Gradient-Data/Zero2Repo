# feature: F15
"""Fresh-process project builds and isolated native-only target preparation."""
from _helpers import run_python, parse_json, build_extensions


def fresh_project_build(project, extensions, *, selections=None, options=None):
    """Run public build integration in a new interpreter; retain failures verbatim."""
    source = '''
from setuptools import Extension, setup
from Velora.Build import veloraize
extensions = [Extension(**spec) for spec in SPECS]
setup(ext_modules=veloraize(SELECTIONS, **OPTIONS), script_args=ARGS)
'''.replace('SPECS', repr(extensions)).replace(
        'SELECTIONS', 'extensions' if selections is None else repr(selections)).replace(
        'OPTIONS', repr(dict(quiet=True, **(options or {})))).replace('ARGS', repr([
            'build_ext', '--force', '--build-lib', str(project.root),
            '--build-temp', str(project.path('.integrated-build'))]))
    return run_python(source, env=project.environment(), timeout=180)


def fresh_project_translation(project, sources, **options):
    return run_python(
        'from Velora.Build import veloraize\n'
        f'veloraize({sources!r}, quiet=True, **{options!r})\n',
        env=project.environment(), timeout=180)


def read_built_values(project, source, *, python=None, env=None):
    result = run_python('import json\n' + source, python=python,
                        product_dir=project.root if python is not None else None,
                        env=project.environment() if env is None else env)
    assert result.returncode == 0, result.text('stderr') + result.text()
    return parse_json(result.stdout)


def make_native_only_target(project):
    """Create a real venv containing setuptools but no translator installation."""
    target = project.path('target-env')
    result = run_python('''
import pathlib, shutil, sys, venv
import setuptools, _distutils_hack
venv.EnvBuilder(with_pip=False).create(sys.argv[1])
root = pathlib.Path(sys.argv[1])
site = root / 'lib' / ('python%d.%d' % sys.version_info[:2]) / 'site-packages'
for module in (setuptools, _distutils_hack):
    origin = pathlib.Path(module.__file__).parent
    shutil.copytree(origin, site / origin.name)
''', args=[str(target)], env=project.environment())
    assert result.returncode == 0, result.text('stderr')
    return target / 'bin' / 'python'


def rebuild_current_native(project, name, generated, expression):
    """Recompile only the current native file, even if its timestamp moved back."""
    result = build_extensions(project, [{'name': name, 'sources': [str(generated)]}],
                              env=project.environment(), args=['--force'])
    assert result.returncode == 0, result.text('stderr') + result.text()
    return read_built_values(project, f'import {name} as subject\nprint(json.dumps({expression}))')
