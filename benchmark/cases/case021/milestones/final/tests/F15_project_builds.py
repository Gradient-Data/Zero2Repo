# feature: F15
"""Project selection, native configuration, regeneration and source distribution."""
import os
from pathlib import Path
from _helpers import (temporary_project, run_module, run_python, parse_json,
                      parse_make_dependencies, build_extensions, build_native,
                      tool_path, environment, run_command)
from F01_helpers import translate_source, execute_native
from F15_helpers import (fresh_project_build, fresh_project_translation,
                         read_built_values, make_native_only_target, rebuild_current_native)


def test_f15_t01():
    # The same selections exercise both documented build entry points. An invalid
    # excluded source makes ignoring exclusions fail rather than merely add work.
    for frontend in ('command', 'python'):
        with temporary_project() as project:
            project.write('collection/__init__.py', '')
            project.write('collection/alpha.pyx', 'def value(int x):\n    return x * 3 + 2\n')
            project.write('collection/beta.pyx', 'def value(int x):\n    return x * x - 4\n')
            excluded = project.write('collection/omit.pyx', 'def invalid(:\n')
            pattern = str(project.path('collection/*.pyx'))
            if frontend == 'command':
                result = run_module('Velora.Build.Veloraize',
                                    ['-i', '-x', str(excluded), pattern],
                                    env=project.environment(), timeout=180)
            else:
                result = fresh_project_build(project, [], selections=[pattern],
                                             options={'exclude': [str(excluded)]})
            assert result.returncode == 0, result.text('stderr') + result.text()
            assert read_built_values(project, '''
from collection import alpha, beta
print(json.dumps([alpha.__name__, beta.__name__,
                  [alpha.value(x) for x in (-3, 0, 8)],
                  [beta.value(x) for x in (-3, 0, 8)]]))
''') == ['collection.alpha', 'collection.beta', [-7, 2, 26], [5, -4, 60]]
            if frontend == 'command':
                result = run_module('Velora.Build.Veloraize',
                                    ['-i', str(project.path('missing/*.pyx'))],
                                    env=project.environment())
                assert result.returncode == 1, result.text('stderr')
                assert result.stderr, 'Missing selections must be reported on stderr'
                continue
            # Python integration has a public missing-pattern ValueError carrier.
            result = run_python('''
import json, sys
from Velora.Build import veloraize
try:
    veloraize(sys.argv[1], quiet=True)
except ValueError:
    print(json.dumps('missing-input'))
else:
    print(json.dumps('accepted'))
''', args=[str(project.path('missing/*.pyx'))], env=project.environment())
            assert result.returncode == 0, result.text('stderr')
            assert parse_json(result.stdout) == 'missing-input'


def test_f15_t02():
    with temporary_project() as project:
        header = project.write('headers/native_api.h', '''
int native_calc(int);
''')
        project.write('decls/native_api.pxd', '''
cdef extern from "native_api.h":
    int native_calc(int)
''')
        native = project.write('native.c', '''
#include "native_api.h"
#ifndef COMPILE_FACTOR
#error Missing compiler setting
#endif
#ifndef MACRO_OFFSET
#error Missing macro setting
#endif
int library_value(void);
int __real_library_value(void);
int __wrap_library_value(void) { return __real_library_value() + 7; }
int native_calc(int x) { return x * COMPILE_FACTOR + MACRO_OFFSET + library_value(); }
''')
        library = project.write('library.c', 'int library_value(void) { return 13; }\n')
        obj = project.path('library.o')
        result = build_native(tool_path('cc'), [library], obj, before=['-c', '-fPIC'])
        assert result.returncode == 0, result.text('stderr')
        archive = project.path('libs/libauthored.a')
        archive.parent.mkdir()
        result = run_command([tool_path('ar'), 'rcs', archive, obj])
        assert result.returncode == 0, result.text('stderr')
        source = project.write('configured.pyx', '''
from native_api cimport native_calc
def value(int x):
    return native_calc(x)
''')
        spec = {'name': 'configured', 'sources': [str(source), str(native)],
                'include_dirs': [str(header.parent)],
                'library_dirs': [str(archive.parent)], 'libraries': ['authored'],
                'define_macros': [('MACRO_OFFSET', '5')],
                'extra_compile_args': ['-DCOMPILE_FACTOR=4'],
                'extra_link_args': ['-Wl,--wrap=library_value']}
        options = {'include_path': [str(project.path('decls'))]}
        result = fresh_project_build(project, [spec], options=options)
        assert result.returncode == 0, result.text('stderr') + result.text()
        assert read_built_values(project, 'import configured\nprint(json.dumps('
                                 '[configured.value(x) for x in (-2, 0, 9)]))') == [17, 25, 61]
        # Each fault starts from the same real successful build description.
        for fault in ('header', 'library', 'compilation'):
            bad = dict(spec)
            if fault == 'header':
                header.rename(header.with_suffix('.saved'))
            elif fault == 'library':
                bad['libraries'] = ['absent_authored_library']
            else:
                bad['extra_compile_args'] = ['-DCOMPILE_FACTOR=invalid_native_token']
            try:
                result = fresh_project_build(project, [bad], options=options)
                assert result.returncode != 0, result.text() + result.text('stderr')
                assert result.stderr, 'Native build failure must be reported on stderr'
            finally:
                if fault == 'header':
                    header.with_suffix('.saved').rename(header)


def test_f15_t03():
    with temporary_project() as project:
        source = project.write('incremental.pyx', '''
from middle cimport compute
def value(int x):
    return compute(x) + 2
''')
        middle = project.write('middle.pxd', 'from leaf cimport compute\n')
        leaf_text = ('include "leaf_body.pxi"\n'
                     'cdef inline int compute(int x):\n    return fragment_compute(x) + 0\n')
        leaf = project.write('leaf.pxd', leaf_text)
        fragment = project.write('leaf_body.pxi',
                                 'cdef inline int fragment_compute(int x):\n    return x * 3\n')
        generated = source.with_suffix('.c')
        result = fresh_project_translation(project, [str(source)])
        assert result.returncode == 0, result.text('stderr')
        expression = '[subject.value(x) for x in (-3, 0, 8)]'
        assert rebuild_current_native(project, source.stem, generated, expression) == [-7, 2, 26]
        changes = [
            (source, source.read_text().replace('+ 2', '+ 5'), [-4, 5, 29]),
            (leaf, leaf_text.replace('+ 0', '+ 4'), [0, 9, 33]),
            (fragment, 'cdef inline int fragment_compute(int x):\n    return x * 7\n', [-12, 9, 65]),
        ]
        for changed, text, expected in changes:
            changed.write_text(text)
            newer = max(generated.stat().st_mtime,
                        *(path.stat().st_mtime for path in (source, middle, leaf, fragment))) + 2
            os.utime(changed, (newer, newer))
            result = fresh_project_translation(project, [str(source)])
            assert result.returncode == 0, result.text('stderr')
            assert rebuild_current_native(project, source.stem, generated, expression) == expected
            # A later update must be the only input newer than the output.
            # Future input times avoid sleeps; normalize the generated file so
            # earlier updates cannot accidentally retrigger subsequent builds.
            up_to_date = max(path.stat().st_mtime for path in (source, middle, leaf, fragment)) + 1
            os.utime(generated, (up_to_date, up_to_date))
        # Translate a second genuine module with the SAME import identity.
        with temporary_project() as replacement:
            alternate = replacement.write('incremental.pyx',
                                          'def value(int x):\n    return x * 2 - 9\n')
            result = translate_source(replacement, alternate)
            assert result.returncode == 0, result.text('stderr')
            generated.write_bytes(alternate.with_suffix('.c').read_bytes())
        inputs = [source, middle, leaf, fragment]
        newer = max(path.stat().st_mtime for path in inputs) + 10
        os.utime(generated, (newer, newer))
        snapshot = [(path.read_bytes(), path.stat().st_mtime_ns) for path in inputs]
        # Native rebuilds explicitly force the native compiler, not translation.
        assert rebuild_current_native(project, source.stem, generated, expression) == [-15, -9, 7]
        result = fresh_project_translation(project, [str(source)], force=True)
        assert result.returncode == 0, result.text('stderr')
        assert snapshot == [(path.read_bytes(), path.stat().st_mtime_ns) for path in inputs]
        assert rebuild_current_native(project, source.stem, generated, expression) == [-12, 9, 65]


def test_f15_t04():
    with temporary_project() as project:
        source = project.write('dependencies.pyx', '''
from middle cimport compute
include "application body.pxi"
''')
        middle = project.write('middle.pxd', 'from leaf cimport compute\n')
        leaf = project.write('leaf.pxd', 'include "native body.pxi"\n')
        fragment = project.write('native body.pxi',
                                 'cdef inline int compute(int x):\n    return x * 6\n')
        body = project.write('application body.pxi',
                             'def value(int x):\n    return compute(x) - 1\n')
        result = fresh_project_translation(project, [str(source)], depfile=True)
        assert result.returncode == 0, result.text('stderr')
        generated = source.with_suffix('.c')
        rules = parse_make_dependencies(Path(str(generated) + '.dep').read_bytes(), base=Path.cwd())
        dependencies = set()
        for rule in rules:
            if generated in rule.targets:
                dependencies.update(rule.prerequisites)
        assert {source, middle, leaf, fragment, body} <= dependencies
        assert execute_native(project, source.stem, generated,
                              '[subject.value(x) for x in (-2, 0, 7)]') == [-13, -1, 41]


def test_f15_t05():
    with temporary_project() as project:
        specs = []
        for name, suffix, options in [('distributed_c', '.c', ()),
                                      ('distributed_cpp', '.cpp', ('--cplus',))]:
            source = project.write(name + '.pyx', '''
def evaluate(int x, int y):
    return x * y + x - 2 * y
''')
            result = translate_source(project, source, options=options)
            assert result.returncode == 0, result.text('stderr')
            source.unlink()
            specs.append({'name': name, 'sources': [str(source.with_suffix(suffix))]})
        python = make_native_only_target(project)
        env = environment({'PYTHONNOUSERSITE': '1'}, import_paths=[project.root])
        assert read_built_values(project, '''
import importlib.util
print(json.dumps([importlib.util.find_spec(name) is None for name in ('Velora', 'velora')]))
''', python=python, env=env) == [True, True]
        result = build_extensions(project, specs, python=python, env=env, product_dir=project.root)
        assert result.returncode == 0, result.text('stderr') + result.text()
        assert read_built_values(project, '''
import distributed_c, distributed_cpp
print(json.dumps([[module.evaluate(x, y) for x, y in ((3, 7), (-4, 2), (9, -3))]
                  for module in (distributed_c, distributed_cpp)]))
''', python=python, env=env) == [[10, -16, -12], [10, -16, -12]]
