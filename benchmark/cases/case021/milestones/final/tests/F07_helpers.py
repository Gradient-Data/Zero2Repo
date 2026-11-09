# feature: F07
"""Compile Python-valid sources and drive native or explicit source execution."""
import textwrap
from _helpers import build_extensions
from F01_helpers import translate_source
from F06_helpers import run_cooperating_application


def build_pure_module(project, name, source, *, companion=None):
    path = project.write(name + '.py', textwrap.dedent(source))
    if companion is not None:
        project.write(name + '.pxd', textwrap.dedent(companion))
    result = translate_source(project, path, options=('-3',))
    assert result.returncode == 0, result.text('stderr')
    result = build_extensions(project, [{'name': name, 'sources': [str(path.with_suffix('.c'))]}],
                              env=project.environment())
    assert result.returncode == 0, result.text('stderr') + result.text()
    return path


def run_pure_application(project, name, driver, *, interpreted=False):
    if interpreted:
        prefix = ('import types\nsubject = types.ModuleType("interpreted_subject")\n'
                  f'exec(compile(open({str(project.path(name + ".py"))!r}).read(), '
                  f'{str(project.path(name + ".py"))!r}, "exec"), subject.__dict__)\n')
    else:
        prefix = f'import {name} as subject\n'
    run_cooperating_application(project, prefix + textwrap.dedent(driver))
