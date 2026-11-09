# feature: F07
"""Generic declarations and scalar bodies applied to numerical arrays."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _helpers import write_text
from F01_helpers import translate_and_observe
from F02_helpers import require_scalar
from F11_helpers import require_array_result
from F05_helpers import interactive_session, load_session_module, require_exception


def test_generic_alternatives_and_context(tmp_path):
    source = '''
from typing import TypeVar
T = TypeVar('T', int, float)

def independent(a: 'int | float', b: 'int | float'):
    return a - b

def coupled(a: T, b: T):
    return a - b

def arrays(a: 'int[:] | float[:] | complex[:] | float[:,:]'):
    return a + a

def make_context():
    P = TypeVar('P', 'float32', 'float64')
    def contextual(a: P, b: P):
        from numpy import array
        return array([a - b])
    return contextual
'''
    for language in ('c', 'fortran'):
        root = tmp_path / language
        root.mkdir()
        path = write_text(root, 'generic_input.py', source)

        def exercise(ezelvori):
            from F00_oracle import host_numpy as np
            original = load_session_module(path)
            # The context factory is Python session code, not submitted source.
            module = ezelvori(source.split('def make_context():')[0],
                             language=language, folder='unions')
            for integers, reals in (((-7, 3), (-2.5, 1.25)),
                                    ((11, -4), (6.25, -3.5))):
                for a in (integers[0], reals[0]):
                    for b in (integers[1], reals[1]):
                        require_scalar(module.independent(a, b), a - b)
                for a, b in (integers, reals):
                    require_scalar(module.coupled(a, b), a - b)
                for a, b in ((integers[0], reals[1]), (reals[0], integers[1])):
                    with require_exception(TypeError):
                        module.coupled(a, b)
            with require_exception(TypeError):
                module.independent(2j, 3)
            for dtype, shape in ((np.int64, (5,)), (np.float64, (7,)),
                                 (np.complex128, (4,)), (np.float64, (2, 3))):
                a = np.arange(np.prod(shape)).reshape(shape).astype(dtype) - 3
                if dtype == np.complex128:
                    a += 2j
                actual = module.arrays(a)
                assert actual.shape == a.shape
                assert actual.dtype == a.dtype
                require_array_result(actual, a + a)
            for a in (np.arange(3, dtype=np.float32), np.zeros((2, 2, 2))):
                with require_exception(TypeError):
                    module.arrays(a)
            contextual = ezelvori(original.make_context(), language=language,
                                 folder='context')
            for dtype in (np.float32, np.float64):
                for a, b in ((7.25, -1.5), (-3.5, 2.25)):
                    result = contextual(dtype(a), dtype(b))
                    assert result.dtype == np.dtype(dtype)
                    require_array_result(result, np.array([a - b], dtype=dtype))
            with require_exception(TypeError):
                contextual(np.float32(2), np.float64(1))
        interactive_session(root / 'session', exercise)


def test_type_and_optional_branch_selection(tmp_path):
    source = '''
def select(a: 'int | float', b: int = None):
    if isinstance(a, int):
        value = a * 3
    else:
        value = -a
    if b is None:
        return value - 4
    return value + b

def ranked(a: 'int[:] | int[:,:]'):
    if len(a.shape) == 1:
        return a[1] - a[0]
    else:
        return a[0, 1] + a[1, 0]
'''
    def exercise(module):
        from F00_oracle import host_numpy as np
        for a in (-5, 8, -2.5, 6.25):
            value = a * 3 if isinstance(a, int) else -a
            def require_selected(actual, expected):
                if isinstance(a, int):
                    assert actual == expected, (actual, expected)
                else:
                    # Unary negation followed by addition/subtraction has two
                    # individual-operation guarantees. Carry the first error
                    # into both the final value and its relative error bound.
                    first_error = 1e-14 + 1e-13 * abs(value)
                    bound = first_error + 1e-14 + 1e-13 * (abs(expected) + first_error)
                    assert np.isfinite(actual)
                    assert abs(actual - expected) <= bound, (actual, expected, bound)
            require_selected(module.select(a), value - 4)
            require_selected(module.select(a, None), value - 4)
            for b in (0, -7, 11):
                require_selected(module.select(a, b), value + b)
        for offset in (-4, 9):
            a = np.array([offset, 3, -8], dtype=int)
            b = np.array([[offset, 7], [-2, 13]], dtype=int)
            assert module.ranked(a) == a[1] - a[0]
            assert module.ranked(b) == b[0, 1] + b[1, 0]
    for language in ('c', 'fortran'):
        translate_and_observe(source, language, tmp_path / language, exercise)


def test_elementwise_scalar_body_on_arrays(tmp_path):
    source = '''
from zelvori.decorators import elemental

@elemental
def combine(a: float):
    return a * a - a

def vector(a: 'float[:]'):
    return combine(a)

def matrix(a: 'float[:,:]'):
    return combine(a)
'''
    def exercise(module):
        from F00_oracle import host_numpy as np
        for shape in ((7,), (2, 5), (3, 2)):
            a = (np.arange(np.prod(shape), dtype=float) - 4).reshape(shape)
            call = module.vector if len(shape) == 1 else module.matrix
            actual = call(a)
            expected = np.array([float(x) * float(x) - float(x)
                                 for x in a.flat]).reshape(shape)
            assert actual.shape == shape
            assert actual.dtype == expected.dtype
            assert np.all(np.isfinite(actual))
            # Propagate the two individual-operation guarantees through
            # multiplication followed by subtraction, retaining both terms.
            product_error = 1e-14 + 1e-13 * np.abs(a * a)
            bound = product_error + 1e-14 + 1e-13 * (np.abs(expected) + product_error)
            assert np.all(np.abs(actual - expected) <= bound), (actual, expected, bound)
    for language in ('c', 'fortran'):
        translate_and_observe(source, language, tmp_path / language, exercise)
