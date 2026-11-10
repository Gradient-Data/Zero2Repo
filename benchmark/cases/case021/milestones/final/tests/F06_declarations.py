# feature: F06
"""Reusable declarations observed through independently built extensions."""
from _helpers import temporary_project, run_python, parse_json, build_extensions
from F01_helpers import translate_source, source_diagnostics
from F03_helpers import REJECTIONS
from F06_helpers import build_cooperating_module, run_cooperating_application


def test_f06_t01():
    with temporary_project() as project:
        project.write('provider.pxd', '''
ctypedef long Count
cdef Count shared
cdef Count adjust(Count value)
cdef class Record:
    cdef Count number
    cdef Count compute(self, Count value)
''')
        build_cooperating_module(project, 'provider', '''
            shared = 13
            cdef Count adjust(Count value):
                return value * 3 + shared
            cdef class Record:
                def __init__(self, number): self.number = number
                cdef Count compute(self, Count value): return self.number + value
                def visible(self, value): return self.compute(value)
            def snapshot(Record item): return shared, item.number
        ''')
        build_cooperating_module(project, 'consumer', '''
            cimport provider
            from provider cimport Count, Record, adjust
            cdef class Derived(Record):
                cdef Count compute(self, Count value): return self.number * value
            def use(Record item, Count value):
                provider.shared += value
                item.number += value
                return adjust(value), item.compute(value), provider.shared
        ''')
        run_cooperating_application(project, '''
            import provider, consumer
            base = provider.Record(7)
            derived = consumer.Derived(-4)
            assert base.visible(5) == 12
            assert derived.visible(5) == -20
            assert consumer.use(base, 3) == (25, 13, 16)
            assert provider.snapshot(base) == (16, 10)
            assert consumer.use(derived, -2) == (8, 12, 14)
            assert provider.snapshot(derived) == (14, -6)
            assert base.visible(1) == 11
            assert derived.visible(2) == -12
        ''')


def test_f06_t02():
    with temporary_project() as project:
        project.write('native_ops.h', 'static int triple(int value) { return 3 * value; }\n')
        project.write('only_native.pxd', 'cdef extern from "native_ops.h":\n    int triple(int value)\n')
        project.write('python_side.pxd', 'cdef extern from "native_ops.h":\n    int triple(int value)\n')
        project.write('python_side.py', 'token = {"number": 29}\n')
        build_cooperating_module(project, 'imports', '''
            from only_native cimport triple
            cimport python_side
            def native(value): return triple(value) + python_side.triple(value + 1)
            def explicit():
                import python_side
                return python_side.token
        ''')
        run_cooperating_application(project, REJECTIONS + '''
import imports
for value in (4, -7):
    assert imports.native(value) == 3 * value + 3 * (value + 1)
rejects(ModuleNotFoundError, __import__, 'only_native')
import python_side
assert imports.explicit() is python_side.token
assert imports.explicit() == {'number': 29}
''')
        # Declaration import alone does not provide the declaring module's Python
        # objects. Refusal may happen at translation (with a source location) or
        # as NameError when the reference executes; it must never yield the
        # Python module's object.
        path = project.write('unimported.pyx', 'from python_side cimport triple\n'
                             'def native(value): return triple(value)\n'
                             'def read(): return token\n')
        result = translate_source(project, path)
        if result.returncode == 0:
            built = build_extensions(project, [{'name': path.stem,
                                     'sources': [str(path.with_suffix('.c'))]}],
                                     env=project.environment())
            assert built.returncode == 0, built.text('stderr') + built.text()
            run_cooperating_application(project, REJECTIONS + '''
import python_side, unimported
assert unimported.native(5) == 15
rejects(NameError, unimported.read)
''')
        else:
            assert result.returncode == 1, result.text('stderr')
            assert any(int(record['line']) == 3 for record in source_diagnostics(result, path)), \
                result.text('stderr')


def test_f06_t03():
    with temporary_project() as project:
        project.write('compatible.pxd', 'cdef int transform(int value)\n')
        build_cooperating_module(project, 'compatible', '''
            cdef int transform(int value): return value + 9
            def invoke(value): return transform(value)
        ''')
        run_cooperating_application(project, '''
            import compatible
            assert compatible.invoke(-4) == 5
            assert compatible.invoke(8) == 17
        ''')
        project.write('signature.pxd', 'cdef long transform(int value)\n')
        project.write('attributes.pxd', 'cdef class Record:\n    cdef int declared\n')
        # Leading lines make the responsible lines differ from the first one;
        # each case lists the source lines (definition or offending member)
        # that are responsible for it.
        padding = 'import sys\nscale = 3\n\n'
        cases = [
            ('signature', 'cdef double transform(int value):\n    return value\n', {4}),
            ('attributes', 'cdef class Record:\n    cdef int extra\n', {4, 5}),
            ('missing', 'from absent_declarations cimport absent_type\ncdef absent_type item\n', {4, 5}),
        ]
        for name, source, responsible in cases:
            path = project.write(name + '.pyx', padding + source)
            result = translate_source(project, path)
            assert result.returncode == 1, result.text('stderr')
            records = source_diagnostics(result, path)
            assert records, result.text('stderr')
            assert all(int(record['line']) > 0 and int(record['column']) >= 0
                       and record['explanation'].strip() for record in records)
            assert any(int(record['line']) in responsible for record in records), \
                result.text('stderr')


def test_f06_t04():
    with temporary_project() as project:
        project.write('declarations/regular/__init__.py', '')
        project.write('declarations/regular/values.pxd', '''
cdef inline int scale(int value):
    return value * 4
''')
        project.write('declarations/namespace/values.pxd', '''
cdef inline int shift(int value):
    return value - 7
''')
        project.write('fragments/behavior.pxi', '''
state = [11]
state.append(23)
def included(value):
    state.append(value)
    return scale(value) + shift(value), list(state)
''')
        build_cooperating_module(project, 'searched', '''
            from regular.values cimport scale
            from namespace.values cimport shift
            include "behavior.pxi"
        ''', search=(project.path('declarations'), project.path('fragments')))
        run_cooperating_application(project, '''
            import searched
            assert searched.included(6) == (23, [11, 23, 6])
            assert searched.included(-3) == (-22, [11, 23, 6, -3])
        ''')


def test_f06_t05():
    with temporary_project() as project:
        result = run_python('import Velora, json\nprint(json.dumps(Velora.__version__))',
                            env=project.environment())
        assert result.returncode == 0, result.text('stderr')
        version = parse_json(result.stdout)
        # Public tags concatenate major and minor numbers; patch/prerelease
        # suffixes do not participate. Derive inputs from the running version.
        major, minor = version.split('.')[:2]
        current = int(major + minor)
        def declaration(location, tag, marker):
            project.write(f'{location}/choice.velora-{tag}.pxd',
                          f'cdef inline int selected(int value):\n    return value + {marker}\n')
        declaration('future_only', current + 2, 900)
        first_tags = sorted({0, max(0, current - 2), max(0, current - 1)})
        for index, tag in enumerate(first_tags, 1):
            declaration('first', tag, 100 * index)
        declaration('first', current + 1, 800)
        declaration('second', current, 400)
        # Both orders are needed: they separate location priority from globally
        # highest-version selection and prove each location is usable.
        for name, locations, marker in (
                ('first_order', ('future_only', 'first', 'second'), 100 * len(first_tags)),
                ('second_order', ('future_only', 'second', 'first'), 400)):
            build_cooperating_module(project, name, '''
                from choice cimport selected
                def evaluate(int value): return selected(value)
            ''', search=tuple(project.path(location) for location in locations))
            run_cooperating_application(project, f'''
                import {name} as subject
                assert subject.evaluate(9) == {marker + 9}
                assert subject.evaluate(-5) == {marker - 5}
            ''')
