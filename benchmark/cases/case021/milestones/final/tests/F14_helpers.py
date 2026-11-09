# feature: F14
"""Build NumPy-backed native extensions with the installed development headers."""
from textwrap import dedent
from _helpers import build_extensions, run_python
from F01_helpers import translate_source


def build_numpy(project, name, source):
    path = project.write(name + '.pyx', dedent(source))
    translated = translate_source(project, path)
    assert translated.returncode == 0, translated.text('stderr')
    headers = run_python('import numpy; print(numpy.get_include())',
                         env=project.environment())
    headers.check_returncode()
    built = build_extensions(project, [{'name': name,
        'sources': [str(path.with_suffix('.c'))],
        'include_dirs': [headers.text().strip(), str(project.root)]}])
    assert built.returncode == 0, built.text('stderr') + built.text()
