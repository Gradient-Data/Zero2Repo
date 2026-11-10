# feature: F11
"""Executable specialisations and dispatch through authored generic routines."""
from _helpers import temporary_project
from F01_helpers import translate_source, source_diagnostics
from F02_helpers import check_python_execution
from F03_helpers import REJECTIONS


def test_f11_t01():
    check_python_execution('''
        ctypedef fused Scalar:
            int
            double
            object
        cpdef scalar(Scalar value):
            if Scalar is int:
                return value * 3
            elif Scalar is double:
                return value / 2
            else:
                return value + ['object']
        ctypedef fused Element:
            int
            double
        ctypedef fused Other:
            int
            double
        cdef pointer(Element* value):
            value[0] += 2
            return value[0]
        def pointers(int x, double y):
            return pointer(&x), pointer(&y)
        def shared(Element[:] x, Element[:] y):
            return x[0] + y[0]
        def independent(Element[:] x, Other[:] y):
            return x[0] - y[0]
    ''', REJECTIONS + '''
from array import array

def exercise(s):
    for x in (-7, 12):
        assert s.scalar['int'](x) == x * 3
        assert s.scalar['double'](x + .5) == (x + .5) / 2
        assert s.scalar['object']([x]) == [x, 'object']
        assert s.scalar([x]) == [x, 'object']
        assert s.pointers(x, x + .5) == (x + 2, x + 2.5)
    left = {'int': array('i', [7, 3]), 'double': array('d', [2.5, 9.5])}
    right = {'int': array('i', [-4, 8]), 'double': array('d', [1.25, 6.5])}
    for kind, x in left.items():
        assert s.shared(x, right[kind]) == x[0] + right[kind][0]
        for other, y in right.items():
            assert s.independent(x, y) == x[0] - y[0]
            if kind != other:
                rejects(ValueError, s.shared, x, y)
''', reference=False)


def test_f11_t02():
    check_python_execution('''
        ctypedef fused First:
            int
            double
        ctypedef fused Second:
            int
            double
        cpdef combine(First x, Second y):
            if First is int:
                a = x * 3
            else:
                a = x / 2
            if Second is int:
                b = y - 4
            else:
                b = y + .25
            return a, b
    ''', REJECTIONS + '''
import velora

def exercise(s):
    signatures = s.combine.__signatures__
    assert set(signatures) == {'int|int', 'int|double', 'double|int', 'double|double'}
    for first in ('int', 'double'):
        for second in ('int', 'double'):
            for x, y in ((6, -2), (-8, 10)):
                expected = (x * 3 if first == 'int' else x / 2,
                            y - 4 if second == 'int' else y + .25)
                assert signatures[first + '|' + second](x, y) == expected
                assert s.combine[first, second](x, y) == expected
    assert s.combine[velora.double, velora.int](5, 9) == (2.5, 5)
    rejects(KeyError, lambda: s.combine['short', 'int'])
''', reference=False)


def test_f11_t03():
    check_python_execution('''
        ctypedef float complex FloatComplex
        ctypedef fused Number:
            short
            long
            float
            double
            float complex
            double complex
        cpdef choose(Number x):
            if Number is short: return 'short', x + 2
            elif Number is long: return 'long', x + 3
            elif Number is float: return 'float', x + 4
            elif Number is double: return 'double', x + 5
            elif Number is FloatComplex: return 'float complex', x + 6
            else: return 'double complex', x + 7
        ctypedef fused Single:
            double
        cdef convert(Single x):
            return x / 2
        def native(short a, long b, float c, double d,
                   float complex e, double complex f):
            return choose(a), choose(b), choose(c), choose(d), choose(e), choose(f), convert(a)
        ctypedef fused Item:
            int
            float
            double
        def buffer(Item[:] x):
            if Item is int: return 'int', x[0] * 2
            elif Item is float: return 'float', x[0] * 3
            else: return 'double', x[0] * 4
    ''', REJECTIONS + '''
from array import array

def exercise(s):
    for n in (-3, 8):
        assert s.native(n, n, n + .5, n + .5, complex(n, 2), complex(n, 2)) == (
            ('short', n + 2), ('long', n + 3), ('float', n + 4.5),
            ('double', n + 5.5), ('float complex', complex(n + 6, 2)),
            ('double complex', complex(n + 7, 2)), n / 2)
        assert s.choose(n) == ('long', n + 3)
        assert s.choose(n + .5) == ('double', n + 5.5)
        assert s.choose(complex(n, 2)) == ('double complex', complex(n + 7, 2))
    for code, kind, scale in (('i', 'int', 2), ('f', 'float', 3), ('d', 'double', 4)):
        values = array(code, [7, -2])
        assert s.buffer(values) == (kind, 7 * scale)
    rejects(TypeError, s.choose, object())
    rejects(TypeError, s.buffer, array('h', [7, -2]))
''', reference=False)


def test_f11_t04():
    check_python_execution('''
        cimport velora
        ctypedef float complex FloatComplex
        def integers(velora.integral x):
            if velora.integral is short: return 'short', x * 3
            elif velora.integral is int: return 'int', x * 3
            else: return 'long', x * 3
        def reals(velora.floating x):
            if velora.floating is float: return 'float', x / 2
            else: return 'double', x / 2
        def numbers(velora.numeric x):
            if velora.numeric is short: name = 'short'
            elif velora.numeric is int: name = 'int'
            elif velora.numeric is long: name = 'long'
            elif velora.numeric is float: name = 'float'
            elif velora.numeric is double: name = 'double'
            elif velora.numeric is FloatComplex: name = 'float complex'
            else: name = 'double complex'
            return name, x * 2 + 1
    ''', '''
def exercise(s):
    integral = {'short', 'int', 'long'}
    floating = {'float', 'double'}
    numeric = integral | floating | {'float complex', 'double complex'}
    assert set(s.integers.__signatures__) == integral
    assert set(s.reals.__signatures__) == floating
    assert set(s.numbers.__signatures__) == numeric
    for name in integral:
        for x in (-9, 14):
            assert s.integers[name](x) == (name, x * 3)
    for name in floating:
        for x in (-2.5, 9.5):
            assert s.reals[name](x) == (name, x / 2)
    for name in numeric:
        values = (-3+2j, 4-1j) if 'complex' in name else (-6, 11)
        for x in values:
            assert s.numbers.__signatures__[name](x) == (name, x * 2 + 1)
''', reference=False)


def test_f11_t05():
    check_python_execution('''
        ctypedef fused Value:
            double
            bytes
        cpdef branch(Value x):
            if Value is bytes:
                return x.decode('ascii').upper()
            else:
                return x / 2
    ''', '''
def exercise(s):
    for value in (b'first', b'next'):
        assert s.branch(value) == value.decode('ascii').upper()
    for value in (-7.5, 12.5):
        assert s.branch(value) == value / 2
''', reference=False)
    with temporary_project() as project:
        source = project.write('unsupported_attribute.pyx', '''
ctypedef fused Value:
    int
    double
cdef class Unsupported:
    cdef Value member
''')
        result = translate_source(project, source)
        assert result.returncode != 0
        assert source_diagnostics(result, source), result.text('stderr')
