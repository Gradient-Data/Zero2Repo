# feature: F03
"""Native value semantics through compiled, Python-visible application routines."""
from textwrap import dedent
from _helpers import temporary_project
from F01_helpers import translate_source, source_diagnostics
from F02_helpers import check_python_execution
from F03_helpers import c_observation, REJECTIONS, AGGREGATES


INTEGER_TYPES = [('char', 'char'), ('signed char', 'byte'),
                 ('unsigned char', 'ubyte'), ('short', 'short'),
                 ('unsigned short', 'ushort'), ('int', 'int'),
                 ('unsigned int', 'uint'), ('long', 'long'),
                 ('unsigned long', 'ulong'), ('long long', 'longlong'),
                 ('unsigned long long', 'ulonglong'), ('size_t', 'size_t'),
                 ('Py_ssize_t', 'ssize_t'), ('Py_hash_t', 'ssize_t'),
                 ('Py_UCS4', 'uint32')]


def test_f03_t01():
    source = 'from libc.stddef cimport size_t\n'
    expected = []
    for index, (native, _) in enumerate(INTEGER_TYPES):
        ctype = {'Py_ssize_t': 'ptrdiff_t', 'Py_hash_t': 'ptrdiff_t',
                 'Py_UCS4': 'uint32_t'}.get(native, native)
        expected.append(c_observation(
            f'{ctype} a=19, b=4; printf("[%lld,%d]", '
            '(long long)(a*b+a-b), a>b);'))
        source += (f'def op{index}({native} a, {native} b):\n' +
                   ('    return (<unsigned int>a)*(<unsigned int>b)+(<unsigned int>a)-(<unsigned int>b), a>b\n'
                    if native == 'Py_UCS4' else '    return a*b+a-b, a>b\n'))
    # (a + c) - a separates the declared floating types: on the target, c = 2**-30
    # survives in double but not single precision, and c = 2**-60 survives
    # only in extended precision. Computing at a wider or narrower precision
    # than declared therefore changes the result.
    floating_inputs = [(1.25, -2.5, 0.5), (1.0, 2.0, 2**-30), (1.0, 2.0, 2**-60)]
    floating_expected = []
    for i, native in enumerate(('float', 'double', 'long double')):
        observations = []
        for a, b, c in floating_inputs:
            observations.append(tuple(c_observation(
                f'{native} a={a.hex()},b={b.hex()},c={c.hex()}; '
                f'{native} complex z=1.25-2.5*I; '
                'printf("[%.17g,%d,%.17g,%.17g,%.17g]",(double)(a*b+a),a>b,'
                '(double)creall(z*z),(double)cimagl(z*z),(double)((a+c)-a));')))
        floating_expected.append(observations)
        source += (f'def floating{i}({native} a, {native} b, {native} c, {native} complex z):\n'
                   '    w = z*z\n    return a*b+a, a>b, w.real, w.imag, (a+c)-a\n')
    source += '''
def mixed(int a, unsigned int b, double c):
    return a < b, a + c

def truth(bint value):
    return value
'''
    mixed = c_observation('int a=-1; unsigned int b=1; double c=0.5; '
                          'printf("[%d,%.17g]",a<b,a+c);')
    result = check_python_execution(source, '''
        def exercise(s):
            values = [getattr(s, 'op'+str(i))(19,4) for i in range(15)]
            assert all(type(v[0]) is int for v in values)
            assert all(type(s.truth(x)) is bool for x in ([], [1], 0, 3))
            return (values, s.mixed(-1,1,0.5), [s.truth(x) for x in ([],[1],0,3)],
                    [[getattr(s,'floating'+str(i))(a,b,c,1.25-2.5j) for a,b,c in INPUTS]
                     for i in range(3)])
    '''.replace('INPUTS', repr(floating_inputs)), reference=False)
    assert result == ([tuple(x) for x in expected], tuple(mixed), [False,True,False,True],
                      floating_expected)


def test_f03_t02():
    source = 'from libc.stddef cimport size_t\n'
    for index, (native, _) in enumerate(INTEGER_TYPES):
        source += (f'def argument{index}({native} value):\n    return value\n'
                   f'def assignment{index}(value):\n    cdef {native} item = value\n    return item\n'
                   f'def width{index}():\n    return sizeof({native})\n')
    char_signed = c_observation('printf("%d", (char)-1 < 0);')
    check_python_execution(source, 'CHAR_SIGNED = ' + repr(char_signed) + '\n' + REJECTIONS + dedent('''
import ctypes
class Integer:
    def __int__(self):
        return 23
class Index:
    def __index__(self):
        return 23

def exercise(s):
    for i in range(15):
        names = ('c_char','c_byte','c_ubyte','c_short','c_ushort','c_int',
                 'c_uint','c_long','c_ulong','c_longlong','c_ulonglong',
                 'c_size_t','c_ssize_t','c_ssize_t','c_uint32')
        bits = ctypes.sizeof(getattr(ctypes,names[i])) * 8
        assert getattr(s, 'width'+str(i))() * 8 == bits
        unsigned = i in (2,4,6,8,10,11,14)
        if i == 0:
            unsigned = not CHAR_SIGNED
        low = 0 if unsigned else -(1 << (bits-1))
        high = (1 << (bits if unsigned else bits-1)) - 1
        if i == 14:
            high = 0x10ffff
        for prefix in ('argument', 'assignment'):
            fn = getattr(s, prefix+str(i))
            values = (low,high,0,31,Index()) if i in (12,13) else (low,high,0,31,12.875,Integer())
            for value in values:
                expected = int(value) if not isinstance(value,Index) else 23
                if i == 14:
                    expected = chr(expected)
                assert fn(value) == expected, (i, value)
            if i in (12,13):
                rejects(TypeError,fn,12.875)
                rejects(TypeError,fn,Integer())
            if i == 14:
                assert fn('Q') == 'Q'
            rejects(OverflowError, fn, low-1)
            rejects(OverflowError, fn, high+1)
            for value in ((b'23',object(),None) if i == 14 else ('23',b'23',object(),None)):
                rejects(TypeError, fn, value)
            if not unsigned and i not in (12,13):
                assert fn(-12.875) == -12
    return True
'''), reference=False)


def test_f03_t03():
    source = ''
    body = ''
    for i, native in enumerate(('float', 'double', 'long double')):
        source += (f'def real{i}({native} x):\n    return x\n'
                   f'def complex{i}({native} complex x):\n    return x\n')
        body += (f'{native} x{i}=1.000000059604644775390625; '
                 f'{native} complex z{i}=1.000000059604644775390625 - 1.000000059604644775390625*I; '
                 f'printf("%s[%.17g,%.17g,%.17g]", "{"," if i else ""}", '
                 f'(double)x{i}, (double)creall(z{i}), (double)cimagl(z{i}));\n')
    expected = c_observation('printf("[");\n' + body + 'printf("]");')
    result = check_python_execution(source, '''
        def exercise(s):
            x = 1.000000059604644775390625
            values = []
            for i in range(3):
                real = getattr(s, 'real'+str(i))
                complex_ = getattr(s, 'complex'+str(i))
                z = complex_(complex(x,-x))
                assert type(real(x)) is float
                assert type(z) is complex
                assert real(17) == 17.0
                assert complex_(9) == 9+0j
                values.append([real(x),z.real,z.imag])
            return values
    ''', reference=False)
    assert result == expected


def test_f03_t04():
    check_python_execution('''
        def calculate(x):
            total = 1
            for i in range(90):
                total = total * 3 + i
            return total, x*x+x, 2**257 - 17
    ''', '''
        def exercise(s):
            return [s.calculate(x) for x in (2**150+7, -2**180+3)]
    ''')


def test_f03_t05():
    result = check_python_execution('''
        ctypedef long Count
        cdef struct Pair:
            Count number
            double weight
        cdef union Storage:
            long number
            double weight
        cdef enum Offset:
            STEP = 5
        def operate(Count value):
            cdef Count items[3]
            cdef Count *pointer = &items[1]
            cdef Pair pair
            cdef Storage store
            cdef (Count, double) packed
            items[0], items[1], items[2] = value, value+1, value+2
            pointer[0] += STEP
            pair.number, pair.weight = items[1], 2.5
            store.number = pair.number * 2
            packed = (store.number, pair.weight)
            first = store.number
            store.weight = pair.weight + 1.25
            return items, pair.number, first, store.weight, packed
    ''', '''
        def exercise(s):
            return [s.operate(x) for x in (7,-11)]
    ''', reference=False)
    assert result == [([7,13,9],13,26,3.75,(26,2.5)),
                      ([-11,-5,-9],-5,-10,3.75,(-10,2.5))]
    with temporary_project() as project:
        path = project.write('variable.pyx', 'def invalid(int n):\n    cdef int values[n]\n    return 1\n')
        rejected = translate_source(project, path)
        assert rejected.returncode != 0
        assert source_diagnostics(rejected, path), rejected.text('stderr')


def test_f03_t06():
    check_python_execution(AGGREGATES, '''
        def exercise(s):
            for count, weight in ((11,2.25),(-9,-0.5)):
                result = s.record({'weight':weight,'count':count})
                assert type(result) is dict
                assert result == {'count':count+7,'weight':weight*2}
                assert s.packed([count,weight]) == (count+7,weight*2)
                assert type(s.packed((count,weight))) is tuple
            for make in (list, tuple, iter, lambda x:(v for v in x)):
                assert s.array(make([11,-4,8])) == [11,3,8]
                assert type(s.array(make([2,5,9]))) is list
            return True
    ''', reference=False)


def test_f03_t07():
    check_python_execution(AGGREGATES, REJECTIONS + dedent('''
        def exercise(s):
            assert s.record({'count':2,'weight':1.5}) == {'count':9,'weight':3.0}
            assert s.array([2,3,4]) == [2,10,4]
            assert s.packed((2,1.5)) == (9,3.0)
            for value in ({'count':2},{'weight':1.5},{}):
                rejects(ValueError, s.record, value)
            for fn, kind, values in ((s.array, IndexError, ([],[1,2],[1,2,3,4])),
                                     (s.packed, TypeError, ((),(1,),(1,2,3)))):
                for value in values:
                    rejects(kind, fn, value)
            for fn, value in ((s.record, {'count':2**200,'weight':1}),
                              (s.array, [1,2**200,3]),
                              (s.packed, (2**200,1))):
                rejects(OverflowError, fn, value)
            for fn, value in ((s.record, {'count':object(),'weight':1}),
                              (s.array, [1,object(),3]),
                              (s.packed, (object(),1))):
                rejects(TypeError, fn, value)
            return True
    '''), reference=False)


def test_f03_t08():
    source = 'from typing import Optional\n'
    types = ('list','tuple','dict','set','frozenset','str','bytes','bytearray')
    for name in types:
        for prefix, declaration in (('native',f'{name} value'),
                                    ('nonnull',f'{name} value not None'),
                                    ('annotation',f'value: {name}'),
                                    ('optional',f'value: Optional[{name}]'),
                                    ('default',f'value: {name} = None')):
            source += f'def {prefix}_{name}({declaration}):\n    return value\n'
    check_python_execution(source, REJECTIONS + dedent('''
        def exercise(s):
            values = ([1],(2,),{'a':3},{4},frozenset([5]),'six',b'seven',bytearray(b'eight'))
            for value in values:
                name = type(value).__name__
                subtype = type('Child', (type(value),), {})
                for prefix in ('native','nonnull','annotation','optional','default'):
                    fn = getattr(s,prefix+'_'+name)
                    assert fn(value) == value
                    rejects(TypeError, fn, subtype(value))
                    rejects(TypeError, fn, 42)
                    if prefix in ('native','optional','default'):
                        assert fn(None) is None
                    else:
                        rejects(TypeError, fn, None)
                assert getattr(s,'default_'+name)() is None
            return True
    '''), reference=False)


def test_f03_t09():
    expected = c_observation('enum E { FIRST, SECOND, RESET=-7, NEXT, JUMP=31, LAST }; '
        'printf("[%d,%d,%d,%d,%d,%d]",FIRST,SECOND,RESET,NEXT,JUMP,LAST);')
    result = check_python_execution('''
        cpdef enum Named:
            FIRST
            SECOND
            RESET = -7
            NEXT
            JUMP = 31
            LAST
        cpdef enum:
            EXPOSED = 14
            FOLLOWING
        cdef enum Private:
            START
            AFTER = 23
            FINAL
        def native():
            return FIRST, SECOND, RESET, NEXT, JUMP, LAST
        def private():
            return START, AFTER, FINAL
    ''', '''
        def exercise(s):
            names = ('FIRST','SECOND','RESET','NEXT','JUMP','LAST')
            assert all(not hasattr(s,n) for n in names)
            assert s.private() == (0,23,24)
            assert (s.EXPOSED,s.FOLLOWING) == (14,15)
            return [int(x) for x in s.native()], [int(getattr(s.Named,n)) for n in names]
    ''', reference=False)
    assert result == (expected, expected)


def test_f03_t10():
    source = '''
        def add(int a, int b):
            return a+b
        def subtract(int a, int b):
            return a-b
        def multiply(int a, int b):
            return a*b
        def unsigned_add(unsigned int a, unsigned int b):
            return a+b
        def width():
            return sizeof(int)*8
    '''
    driver = REJECTIONS + dedent('''
        def exercise(s):
            assert s.add(19,-7) == 12
            assert s.subtract(-19,7) == -26
            assert s.multiply(-19,7) == -133
            return True
    ''')
    # Unsigned wrap is defined by C; signed overflow is never used with checking off.
    for options in ((), ('-X','overflowcheck=False')):
        check_python_execution(source, driver.replace('    return True',
            '    assert s.unsigned_add((1 << s.width())-1,1) == 0\n    return True'),
            options=options, reference=False)
    check_python_execution(source, driver.replace('    return True', '''    high = (1 << (s.width()-1))-1
    low = -high-1
    for fn,a,b in ((s.add,high,1),(s.add,low,-1),
                   (s.subtract,low,1),(s.subtract,high,-1),
                   (s.multiply,high,2),(s.multiply,low,2)):
        rejects(OverflowError,fn,a,b)
    rejects(OverflowError,s.unsigned_add,(1 << s.width())-1,1)
    return True'''), options=('-X','overflowcheck=True'), reference=False)


def test_f03_t11():
    for level, cdivision in ((3,False),(2,False),(3,True),(2,True)):
        check_python_execution('''
            def divide(int a, int b):
                return a / b, a // b, a % b
        ''', REJECTIONS + dedent(f'''
            def exercise(s):
                for a,b in ((17,5),(-17,5),(17,-5),(-17,-5),(0,5)):
                    if {cdivision!r}:
                        q = (abs(a)//abs(b)) * (-1 if (a<0)!=(b<0) else 1)
                        expected = q,q,a-q*b
                    else:
                        expected = (a/b if {level} == 3 else a//b),a//b,a%b
                    assert s.divide(a,b) == expected
                if not {cdivision!r}:
                    rejects(ZeroDivisionError,s.divide,5,0)
                return True
        '''), options=('-X',f'language_level={level}') +
                     (('-X','cdivision=True') if cdivision else ()), reference=False)


def test_f03_t12():
    result = check_python_execution('''
        cdef int number
        cdef double real
        cdef double complex imaginary
        cdef bint flag
        cdef int *pointer
        cdef object item
        cdef int initial = -29
        cdef double fraction = 2.75
        cdef double complex z = 3-4j
        cdef bint yes = True
        cdef int *address = &initial
        cdef object label = {'payload':17}
        def state():
            return (number,real,imaginary,flag,pointer == NULL,item,
                    initial,fraction,z,yes,address[0],label)
    ''', '''
        def exercise(s):
            return s.state()
    ''', reference=False)
    assert result == (0,0.0,0j,False,True,None,-29,2.75,3-4j,True,-29,{'payload':17})
