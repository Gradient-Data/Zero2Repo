# feature: F10
"""Scalar library results against independent Python mathematical references."""
import cmath
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from F01_helpers import translate_and_observe
from F02_helpers import require_scalar
from F10_helpers import mathematical_source


def test_real_mathematical_operations(tmp_path):
    signed = [(-2.25,), (-0.375,), (0.0,), (0.625,), (2.75,)]
    positive = [(0.125,), (0.75,), (1.5,), (5.25,)]
    unit = [(-0.875,), (-0.25,), (0.0,), (0.625,)]
    cases = {name: signed for name in (
        'fabs', 'exp', 'sin', 'cos', 'tan', 'atan', 'sinh', 'cosh',
        'tanh', 'asinh', 'floor', 'ceil', 'trunc', 'erf', 'erfc')}
    cases.update({name: positive for name in ('sqrt', 'log', 'log10')})
    cases.update({name: unit for name in ('asin', 'acos', 'atanh')})
    cases['acosh'] = [(1.0,), (1.125,), (3.5,)]
    for name in ('gamma', 'lgamma'):
        cases[name] = [(-2.25,), (-0.375,), (0.125,), (1.5,), (5.25,)]
    cases['atan2'] = [(1.25, 2.5), (1.25, -2.5), (-1.25, -2.5), (-1.25, 2.5)]
    cases['copysign'] = [(2.5, -3.0), (-2.5, 3.0), (2.5, 3.0), (-2.5, -3.0)]
    cases['hypot'] = [(3.0, 4.0), (-2.25, 5.5), (0.0, -7.0)]
    c_only = {
        'log2': positive,
        'log1p': [(-0.75,), (-1e-10,), (1e-10,), (2.25,)],
        'expm1': [(-2.25,), (-1e-10,), (1e-10,), (0.625,)],
        'ldexp': [(1.25, -7), (-0.375, 5), (2.5, 0)],
        'remainder': [(5.0, 2.0), (7.0, 2.0), (-7.0, 2.0), (8.25, -3.0)],
    }
    for language in ('c', 'fortran'):
        selected = dict(cases)
        if language == 'c':
            selected.update(c_only)
        signatures = {name: ('float',) * len(values[0]) for name, values in selected.items()}
        if language == 'c':
            signatures['ldexp'] = ('float', 'int')
        source = mathematical_source('math', signatures)

        def exercise(module):
            for name, operands in selected.items():
                for args in operands:
                    expected = getattr(math, name)(*args)
                    actual = getattr(module, 'evaluate_' + name)(*args)
                    require_scalar(actual, expected)

        translate_and_observe(source, language, tmp_path / language, exercise)


def test_complex_mathematical_operations(tmp_path):
    names = ('sqrt', 'exp', 'sin', 'cos', 'tan', 'asin', 'acos',
             'atan', 'sinh', 'cosh', 'tanh', 'asinh', 'acosh', 'atanh',
             'phase', 'polar')
    signatures = {name: ('complex',) for name in names}
    signatures['rect'] = ('float', 'float')
    del signatures['polar']
    source = mathematical_source('cmath', signatures) + '''
def evaluate_polar(z: complex):
    from cmath import polar
    radius, phase = polar(z)
    return radius, phase
'''

    def exercise(module):
        for name in names:
            for z in (0.375 + 0.625j, -1.25 + 0.75j, 2.5 - 0.375j, -0.5 - 1.25j):
                require_scalar(getattr(module, 'evaluate_' + name)(z), getattr(cmath, name)(z))
        # Reconstruction has its own oracle, independent of product polar output.
        for radius, phase in ((0.0, 0.75), (2.25, -1.375), (0.625, 2.5)):
            require_scalar(module.evaluate_rect(radius, phase), cmath.rect(radius, phase))

    for language in ('c', 'fortran'):
        translate_and_observe(source, language, tmp_path / language, exercise)


def test_constants_integer_math_and_angles(tmp_path):
    source = mathematical_source('math', {
        'factorial': ('int',), 'gcd': ('int', 'int'), 'lcm': ('int', 'int'),
        'degrees': ('float',), 'radians': ('float',),
    }) + '''
def constants():
    from math import pi, e, tau
    return pi, e, tau
'''

    def exercise(module):
        require_scalar(module.constants(), (math.pi, math.e, math.tau))
        for n in (0, 1, 2, 7, 12):
            assert module.evaluate_factorial(n) == math.factorial(n)
        for a, b in ((0, 0), (0, -18), (-24, 0), (18, 24), (-18, 24),
                     (18, -24), (-18, -24), (17, 31)):
            assert module.evaluate_gcd(a, b) == math.gcd(a, b)
        for a, b in ((0, -18), (-24, 0), (18, 24), (-18, 24),
                     (18, -24), (-18, -24), (17, 31)):
            assert module.evaluate_lcm(a, b) == math.lcm(a, b)
        for angle in (-450.25, -1.25, 0.0, 0.625, 270.5):
            require_scalar(module.evaluate_degrees(angle), math.degrees(angle))
            require_scalar(module.evaluate_radians(angle), math.radians(angle))

    for language in ('c', 'fortran'):
        translate_and_observe(source, language, tmp_path / language, exercise)


def test_real_special_value_classification(tmp_path):
    for language in ('c', 'fortran'):
        names = ('isfinite', 'isinf', 'isnan') if language == 'c' else ('isnan',)
        source = mathematical_source('math', {name: ('float',) for name in names})

        def exercise(module):
            for x in (0.0, -0.0, -3.75, 1e300, float('inf'), -float('inf'), float('nan')):
                for name in names:
                    actual = getattr(module, 'evaluate_' + name)(x)
                    assert isinstance(actual, bool)
                    assert actual == getattr(math, name)(x)

        translate_and_observe(source, language, tmp_path / language, exercise)
