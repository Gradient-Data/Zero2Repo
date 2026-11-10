# feature: F13
"""OpenMP builds through the public translator and native toolchain."""
from textwrap import dedent
from _helpers import build_extensions, run_python
from F01_helpers import translate_source


def build_openmp(project, name, source, *, extra_sources=()):
    path = project.write(name + '.pyx', dedent(source))
    translated = translate_source(project, path)
    assert translated.returncode == 0, translated.text('stderr')
    built = build_extensions(project, [{
        'name': name, 'sources': [str(path.with_suffix('.c')),
                                  *map(str, extra_sources)],
        'include_dirs': [str(project.root)],
        'extra_compile_args': ['-O3', '-fopenmp'],
        'extra_link_args': ['-fopenmp'],
    }])
    assert built.returncode == 0, built.text('stderr') + built.text()
    return path


def run_parallel_application(project, name, driver, *, timeout=120):
    result = run_python(f'import {name} as subject\n' + dedent(driver),
                        env=project.environment(overrides={
                            'OMP_NUM_THREADS': '4', 'OMP_DYNAMIC': 'FALSE',
                            'OMP_SCHEDULE': 'dynamic,3', 'OMP_PROC_BIND': 'FALSE',
                            'OMP_WAIT_POLICY': 'PASSIVE',
                        }), timeout=timeout)
    assert result.returncode == 0, result.text('stderr') + result.text()
    return result
