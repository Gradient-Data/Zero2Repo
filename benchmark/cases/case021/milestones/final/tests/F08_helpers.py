# feature: F08
"""Build translated modules together with supplied native implementation files."""
from textwrap import dedent
from _helpers import build_extensions
from F01_helpers import translate_source


def build_native_binding(project, name, source, *, native_sources=(), libraries=()):
    path = project.write(name + '.pyx', dedent(source))
    translated = translate_source(project, path)
    assert translated.returncode == 0, translated.text('stderr')
    built = build_extensions(project, [{
        'name': name, 'sources': [str(path.with_suffix('.c')), *native_sources],
        'include_dirs': [str(project.root)], 'libraries': list(libraries),
    }], env=project.environment())
    assert built.returncode == 0, built.text('stderr') + built.text()
    return path
