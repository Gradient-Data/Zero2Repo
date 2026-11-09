# feature: F09
"""C++ selection layered over the shared translation and build drivers."""
from textwrap import dedent
from _helpers import build_extensions
from F01_helpers import translate_source


def build_cpp_binding(project, name, source):
    path = project.write(name + '.pyx', dedent(source))
    translated = translate_source(project, path, options=('--cplus',))
    assert translated.returncode == 0, translated.text('stderr')
    built = build_extensions(project, [{
        'name': name, 'sources': [str(path.with_suffix('.cpp'))],
        'include_dirs': [str(project.root)], 'language': 'c++',
        'extra_compile_args': ['-std=c++11'],
    }], env=project.environment())
    assert built.returncode == 0, built.text('stderr') + built.text()
    return path
