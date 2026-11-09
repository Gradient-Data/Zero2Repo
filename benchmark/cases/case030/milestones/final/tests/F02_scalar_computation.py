# feature: F02
"""Scalar computation acceptance checks using Python's independent semantics."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from F00_oracle import host_numpy as np
from F01_helpers import translate_and_observe
from F02_helpers import execute_script, python_namespace, require_scalar


def test_scalar_operators(tmp_path):
    source = '''
def integers(a: int, b: int, s: int):
    return a+b, a-b, a*b, a/b, a//b, a%b, a**s, +a, -a, ~a, a&b, a|b, a^b, a<<s, a>>s

def predicates(a: int, b: int, p: bool, q: bool):
    return a==b, a!=b, a<b, a<=b, a>b, a>=b, p and q, p or q, not p

def grouped(a: int, b: int, c: int):
    return (a+b)*c, a+b*c, a-(b-c), (a-b)-c

def touch(x: 'int[:]'):
    x[0] += 1
    return True

def short(x: 'int[:]', p: bool):
    a = p and touch(x)
    b = p or touch(x)
    return a, b
'''
    operations = ['a+b', 'a-b', 'a*b', 'a/b', 'a**b']
    for kind in ('float', 'complex', 'float32', 'complex64'):
        source += '\nfrom numpy import float32, complex64\n' if kind == 'float32' else ''
        for index, expression in enumerate(operations):
            source += f"\ndef {kind}_{index}(a: '{kind}', b: '{kind}'):\n    return {expression}\n"
    source += '\ndef real_mod(a: float, b: float):\n    return a//b, a%b\n'
    reference = python_namespace(source)
    integer_args = [(-17, 5, 2), (17, -5, 3), (-17, -5, 1), (0, 3, 0)]
    predicate_args = [(a, b, p, q) for a, b, p, q in
                      [(2, 2, True, True), (1, 3, True, False),
                       (3, 1, False, True), (1, 1, False, False)]]
    calls = [('integers', args, 64) for args in integer_args]
    calls += [('predicates', args, 64) for args in predicate_args]
    calls += [('grouped', args, 64) for args in [(7, 3, 2), (-4, 5, -2)]]
    calls += [('real_mod', args, 64) for args in [(-7.5, 2.0), (7.5, -2.0), (-7.5, -2.0)]]
    for kind, convert, bits in [('float', float, 64), ('complex', complex, 64),
                                 ('float32', np.float32, 32), ('complex64', np.complex64, 32)]:
        pairs = [(1.25, 2.5), (-2.25, 3.0)] if 'complex' not in kind else [(1.25+0.5j, 0.75-0.25j), (-2+0.5j, 1.5+0.25j)]
        for index in range(len(operations)):
            for a, b in pairs:
                calls.append((f'{kind}_{index}', (convert(a), convert(b)), bits))
    def consume(module):
        values = [getattr(module, name)(*args) for name, args, _ in calls]
        updates = []
        for flag in (True, False):
            array = np.array([0], dtype=int)
            updates.append((module.short(array, flag), array.copy()))
        return values, updates
    for language in ('c', 'fortran'):
        actual, updates = translate_and_observe(source, language, tmp_path/language, consume).value
        for value, (name, args, bits) in zip(actual, calls):
            expected = reference[name](*args)
            require_scalar(value, expected, bits)
        for flag, (value, array) in zip((True, False), updates):
            original = np.array([0], dtype=int)
            assert value == reference['short'](original, flag)
            np.testing.assert_array_equal(array, original)


def test_assignments_and_control_flow(tmp_path):
    source = '''
def flow(x: 'int[:]', n: int, step: int, choice: int):
    a = n
    b = 3
    a, b = b, a
    a += 2
    a -= 1
    a *= 3
    a //= 2
    a %= 5
    a = a ** 2
    a <<= 1
    a >>= 1
    a |= 8
    a &= 15
    a = a ^ 3
    r = 2.0
    r /= 4.0
    selected = a if choice > 0 else b
    if choice < 0:
        selected += 10
    elif choice == 0:
        selected += 20
    else:
        selected += 30
    total = 0
    for i in range(0, n, step):
        if i == 2:
            continue
        if i == 6:
            break
        for j in range(3):
            total += i + j
    k = 0
    while k < 4:
        k += 1
        if k == 2:
            continue
        total += k
    x[0] = selected
    x[1] += total
    if choice < 0:
        return selected, total, r
    x[2] = k
    return selected+1, total+2, r
'''
    reference = python_namespace(source)['flow']
    args = [(9, 2, -1), (9, 1, 0), (-7, -2, 1), (0, 1, 1)]
    def consume(module):
        observed = []
        for values in args:
            array = np.array([4, 7, 9], dtype=int)
            result = module.flow(array, *values)
            observed.append((result, array.copy()))
        return observed
    for language in ('c', 'fortran'):
        actual = translate_and_observe(source, language, tmp_path/language, consume).value
        for values, (result, array) in zip(args, actual):
            original = np.array([4, 7, 9], dtype=int)
            require_scalar(result, reference(original, *values))
            np.testing.assert_array_equal(array, original)


def test_conversions_rounding_and_type_queries(tmp_path):
    source = '''
def convert_real(x: float):
    return bool(x), int(x), float(x), complex(x), abs(x), round(x), round(x, 1), round(x, -1)

def convert_int(x: int):
    return bool(x), int(x), float(x), complex(x), abs(x), round(x)

def convert_bool(x: bool):
    return bool(x), int(x), float(x), complex(x)

def convert_complex(x: complex):
    return bool(x), complex(x), abs(x)

def construct_complex(x: float, y: float):
    return complex(x, y)
'''
    for kind in ('bool', 'int', 'float', 'complex'):
        source += f"\ndef query_{kind}(x: {kind}):\n    return isinstance(x, bool), isinstance(x, int), isinstance(x, float), isinstance(x, complex)\n"
    reference = python_namespace(source)
    calls = [('convert_real', (x,)) for x in (-12.75, -3.5, -2.5, 0.0, 2.5, 3.5, 18.125)]
    calls += [('convert_int', (x,)) for x in (-19, 0, 23)]
    calls += [('convert_bool', (x,)) for x in (False, True)]
    calls += [('convert_complex', (x,)) for x in (0j, 3-4j, -5+12j)]
    calls += [('construct_complex', (-1.25, 2.5))]
    calls += [('query_'+kind, (x,)) for kind, x in [('bool', True), ('int', -7), ('float', 1.25), ('complex', 2-3j)]]
    def consume(module):
        return [getattr(module, name)(*args) for name, args in calls]
    for language in ('c', 'fortran'):
        actual = translate_and_observe(source, language, tmp_path/language, consume).value
        for value, (name, args) in zip(actual, calls):
            require_scalar(value, reference[name](*args))


def test_printed_scalar_values_and_separators(tmp_path):
    body = '''a = -13
b = 2.75
c = True
d = 1.5 + 2.25j
print(a, b, c)
print(d)
print(a, b, c, sep='|', end=';')
print(29, end='!')
print()
'''
    for language in ('c', 'fortran'):
        result = execute_script(tmp_path/language, body, language)
        assert result.returncode == 0, result
        lines = result.stdout.splitlines()
        assert len(lines) == 3, result
        fields = lines[0].split()
        assert len(fields) == 3
        assert int(fields[0]) == -13
        assert float(fields[1]) == 2.75
        assert fields[2] == 'True'
        # Native complex scalar grammar is parenthesized real + imaginary j.
        assert complex(lines[1].replace(' ', '')) == 1.5+2.25j
        fields = lines[2].split('|')
        assert len(fields) == 3
        assert int(fields[0]) == -13
        assert float(fields[1]) == 2.75
        tail = fields[2].split(';')
        assert len(tail) == 2
        assert tail[0].strip() == 'True'
        assert tail[1] == '29!'


def test_debug_assertions_and_explicit_exit(tmp_path):
    cases = [('true', 'x = 3\nassert x > 0', True, True, None),
             ('false', 'x = 3\nassert x < 0', False, False, None),
             ('omitted', 'from sys import exit\nexit()', True, False, None),
             ('zero', 'from sys import exit\nexit(0)', True, False, None),
             ('nonzero', 'from sys import exit\nexit(7)', False, False, None),
             ('text', "from sys import exit\nexit('requested termination')", False, False, 'requested termination')]
    for language in ('c', 'fortran'):
        for name, operation, success, continues, reason in cases:
            # A complete line is flushed by the normal runtime on exit.
            body = "print('before')\n" + operation + "\nprint('after')"
            result = execute_script(tmp_path/language/name, body, language, debug=True)
            assert (result.returncode == 0) == success, result
            # C assert abort may discard buffered stdout; continuation is still forbidden.
            if name != 'false':
                assert result.stdout.splitlines() == (['before', 'after'] if continues else ['before']), result
            else:
                assert 'after' not in result.stdout.splitlines(), result
            if reason is not None:
                assert reason in result.stderr.splitlines(), result
