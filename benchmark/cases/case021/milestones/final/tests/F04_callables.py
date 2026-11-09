# feature: F04
"""Observable callable boundaries, native signatures and exception policies."""
from textwrap import dedent
from _helpers import temporary_project
from F01_helpers import translate_source, execute_native, source_diagnostics
from F02_helpers import check_python_execution
from F03_helpers import REJECTIONS


def test_f04_t01():
    check_python_execution('''
        def python_call(int x):
            return x * 3
        cdef int native_call(int x):
            return x * 5
        cpdef double dual_call(int x):
            return x / 2.0
        def compiled(int x):
            return python_call(x), native_call(x), dual_call(x)
    ''', REJECTIONS + '''
def exercise(s):
    for value in (-8, 0, 13):
        assert s.python_call(value) == value * 3
        assert s.dual_call(value) == value / 2.0
        assert type(s.dual_call(value)) is float
        assert s.compiled(value) == (value*3, value*5, value/2.0)
    assert not hasattr(s, 'native_call')
    rejects(TypeError, s.python_call, object())
    rejects(TypeError, s.dual_call, object())
''', reference=False)
    with temporary_project() as project:
        for kind in ('def', 'cpdef'):
            path = project.write('bad_boundary.pyx', f'{kind} bad(int *value):\n    pass\n')
            result = translate_source(project, path)
            assert result.returncode != 0
            assert source_diagnostics(result, path), result.text('stderr')


def test_f04_t02():
    with temporary_project() as project:
        project.write('optional.pxd', 'cdef int combine(int x, int y=*, int z=*)\n')
        path = project.write('optional.pyx', dedent('''
            cdef int combine(int x, int y=7, int z=11):
                return x + 10*y + 100*z
            cdef int plain(int x, int y):
                return x - 3*y
            def exercise(int x):
                cdef int (*call)(int, int) except? -1
                call = plain
                return combine(x), combine(x, 4), combine(x, 4, 2), call(x, 6)
        '''))
        translated = translate_source(project, path)
        assert translated.returncode == 0, translated.text('stderr')
        assert execute_native(project, 'optional', path.with_suffix('.c'),
                              '[subject.exercise(x) for x in (-9, 18)]') == [
                                  [1161, 1131, 231, -27], [1188, 1158, 258, 0]]


def test_f04_t03():
    with temporary_project() as project:
        template = '''
cdef int target(int x) except? -1:
    return x + 9
def invoke(int x):
    cdef {signature}
    pointer = target
    return pointer(x)
'''
        path = project.write('compatible.pyx', template.format(
            signature='int (*pointer)(int) except? -1'))
        translated = translate_source(project, path)
        assert translated.returncode == 0, translated.text('stderr')
        assert execute_native(project, path.stem, path.with_suffix('.c'),
                              '[subject.invoke(3), subject.invoke(-20)]') == [12, -11]
        for signature in ('int (*pointer)(double) except? -1',
                          'double (*pointer)(int) except? -1',
                          'int (*pointer)(int) noexcept'):
            path = project.write('incompatible.pyx', template.format(signature=signature))
            result = translate_source(project, path)
            assert result.returncode != 0
            assert source_diagnostics(result, path), result.text('stderr')


def test_f04_t04():
    check_python_execution('''
        cdef int implicit(int x):
            if x: raise LookupError(x)
            return 17
        cdef int reserved(int x) except -1:
            if x: raise LookupError(x)
            return 23
        cdef int conditional(int x) except? -7:
            if x: raise LookupError(x)
            return -7
        cdef void independent(int x) except *:
            if x: raise LookupError(x)
        def invoke(int mode, int x):
            if mode == 0: return implicit(x)
            if mode == 1: return reserved(x)
            if mode == 2: return conditional(x)
            independent(x)
            return 31
    ''', '''
def exercise(s):
    for mode, expected in enumerate((17, 23, -7, 31)):
        assert s.invoke(mode, 0) == expected
        for token in (4, -19):
            try:
                s.invoke(mode, token)
            except LookupError as error:
                assert error.args == (token,)
            else:
                raise AssertionError('Native exception was lost')
''', reference=False)


def test_f04_t05():
    check_python_execution('''
        cdef void quiet(object value) noexcept:
            raise ValueError(value)
        def invoke(value):
            quiet(value)
            return value + ['continued']
    ''', '''
import sys

def exercise(s):
    reports = []
    previous = sys.unraisablehook
    sys.unraisablehook = reports.append
    try:
        for value in (['first'], ['second', 'payload']):
            assert s.invoke(value) == value + ['continued']
    finally:
        sys.unraisablehook = previous
    assert len(reports) == 2
    for report, value in zip(reports, (['first'], ['second', 'payload'])):
        assert report.exc_type is ValueError
        assert report.exc_value.args == (value,)
''', reference=False)


def test_f04_t06():
    check_python_execution('''
        cdef identity(value):
            return value
        def python_empty(value):
            pass
        cdef object object_empty():
            pass
        cdef int integer_empty():
            pass
        cdef double floating_empty():
            pass
        cdef bint boolean_empty():
            pass
        cdef int* pointer_empty():
            pass
        def exercise(value):
            return (identity(value) is value, python_empty(value), object_empty(),
                    integer_empty(), floating_empty(), boolean_empty(), pointer_empty() == NULL)
    ''', '''
def exercise(s):
    for value in (object(), {'key': [2, 5]}, 'text'):
        result = s.exercise(value)
        assert result == (True, None, None, 0, 0.0, False, True)
        assert type(result[3]) is int
        assert type(result[4]) is float
        assert type(result[5]) is bool
''', reference=False)
