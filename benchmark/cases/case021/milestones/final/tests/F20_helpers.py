# feature: F20
"""Build real embedded executables using the active Python development files."""
import shlex
import sysconfig
from pathlib import Path
from textwrap import dedent

from _helpers import build_native, tool_path
from F01_helpers import translate_source


def build_embedded_application(project, source, *, modules=None):
    """Translate public sources, link their native code, then remove those sources.

    Build and toolchain failures remain failures with their original streams.
    No interpreter execution is substituted for the resulting executable.
    """
    modules = {} if modules is None else modules
    native_sources = []
    inputs = []
    for name, text in [*modules.items(), ('embedded_main', source)]:
        path = project.write(name + '.pyx', dedent(text))
        options = ()
        if name == 'embedded_main':
            options = ('--embed',)
            if modules:
                options += ('--embed-modules', ','.join(modules))
        translated = translate_source(project, path, options=options)
        assert translated.returncode == 0, translated.text('stderr')
        inputs.append(path)
        native_sources.append(path.with_suffix('.c'))

    compiler, *compiler_options = shlex.split(sysconfig.get_config_var('CC'))
    library_dir = Path(sysconfig.get_config_var('LIBDIR'))
    # Link the installed shared runtime explicitly. The image's conda Python
    # advertises an absent static archive in LDLIBRARY.
    python_library = library_dir / ('libpython' + sysconfig.get_config_var('LDVERSION')
                                      + sysconfig.get_config_var('SHLIB_SUFFIX'))
    assert python_library.is_file(), str(python_library)
    executable = project.path('embedded_application')
    built = build_native(tool_path(compiler), native_sources, executable,
        before=[*compiler_options, '-I' + sysconfig.get_path('include')],
        after=[str(python_library), '-Wl,-rpath,' + str(library_dir),
               *shlex.split(sysconfig.get_config_var('LIBS')),
               *shlex.split(sysconfig.get_config_var('SYSLIBS'))],
        env=project.environment())
    assert built.returncode == 0, built.text() + built.text('stderr')
    for path in [*inputs, *native_sources]:
        path.unlink()
    return executable
