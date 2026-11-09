# feature: F06
"""Separate translation/build steps and fresh application execution."""
import textwrap
from _helpers import build_extensions, run_python
from F01_helpers import translate_source


def build_cooperating_module(project, name, source, *, search=()):
    path = project.write(name + '.pyx', textwrap.dedent(source))
    options = tuple(arg for directory in search for arg in ('-I', str(directory)))
    result = translate_source(project, path, options=options)
    assert result.returncode == 0, result.text('stderr')
    result = build_extensions(project, [{'name': name, 'sources': [str(path.with_suffix('.c'))]}],
                              env=project.environment())
    assert result.returncode == 0, result.text('stderr') + result.text()
    return path


def run_cooperating_application(project, source):
    result = run_python(textwrap.dedent(source), env=project.environment())
    assert result.returncode == 0, result.text('stderr') + result.text()
