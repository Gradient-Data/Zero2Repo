# feature: F06
"""Acceptance of typed numerical arrays and shared data."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from F01_helpers import translate_and_observe
from F02_helpers import python_namespace, require_scalar
from F05_helpers import interactive_session, require_exception


def test_typed_array_boundaries(tmp_path):
    source = '''
def default(a: 'float[:,:]'):
    a[0, 1] += 7.0
    return a.shape[0], a.shape[1], a[-1, -1]

def row_major(a: 'float[:,:](order=C)'):
    a[1, 0] -= 3.0
    return a.shape[0], a.shape[1], a[0, -1]

def column_major(a: 'float[:,:](order=F)'):
    a[1, 0] -= 3.0
    return a.shape[0], a.shape[1], a[0, -1]

def integers(a: 'int32[:]'):
    a[1] += 9
    return a[0], a[-1]
'''
    reference = python_namespace(source)

    def exercise(module):
        from F00_oracle import host_numpy as np
        for name, order in (('default', 'C'), ('row_major', 'C'), ('column_major', 'F')):
            function = getattr(module, name)
            for shape in ((3, 5), (4, 2)):
                initial = np.arange(np.prod(shape), dtype=np.float64).reshape(shape) - 8
                expected = initial.copy(order=order)
                actual = initial.copy(order=order)
                assert function(actual) == reference[name](expected)
                changed = (0, 1) if name == 'default' else (1, 0)
                require_scalar(actual[changed], expected[changed])
                unchanged = np.ones(shape, dtype=bool)
                unchanged[changed] = False
                np.testing.assert_array_equal(actual[unchanged], expected[unchanged])
            for invalid in (np.ones((3, 5), dtype=np.int64),
                            np.ones(15, dtype=np.float64),
                            np.ones((3, 5), order='F' if order == 'C' else 'C')):
                try:
                    function(invalid)
                except TypeError:
                    pass
                else:
                    raise AssertionError((name, invalid.dtype, invalid.shape, invalid.strides))
        values = np.array([-8, 2, 11], dtype=np.int32)
        assert module.integers(values) == (-8, 11)
        np.testing.assert_array_equal(values, [-8, 11, 11])
        with require_exception(TypeError):
            module.integers(np.array([-8, 2, 11], dtype=np.int64))

    for language in ('c', 'fortran'):
        translate_and_observe(source, language, tmp_path / language, exercise)


def test_indexing_and_positive_slices(tmp_path):
    source = '''
from zelvori.decorators import allow_negative_index

@allow_negative_index('a')
def indexed(a: 'int[:,:]', i: int, j: int):
    before = a[i, j]
    a[i, j] += 17
    a[1:, ::2] += 3
    a[:2, 1::2] -= 5
    a[0, -1] += 11
    return before, a[-1, 0], a[i, j], a.shape[0], a.shape[1]
'''
    def exercise(module):
        from F00_oracle import host_numpy as np
        reference = python_namespace(source)['indexed']
        for shape, indices in (((4, 7), (-2, -3)), ((3, 6), (1, 2))):
            expected = np.arange(np.prod(shape), dtype=int).reshape(shape) * 2 - 9
            actual = expected.copy()
            assert module.indexed(actual, *indices) == reference(expected, *indices)
            np.testing.assert_array_equal(actual, expected)
    for language in ('c', 'fortran'):
        translate_and_observe(source, language, tmp_path / language, exercise)


def test_local_views_and_independent_copies(tmp_path):
    source = '''
def shared(a: 'int[:,:]'):
    from numpy import array
    view = a[1:, ::2]
    copied = array(view)
    view[0, 1] += 31
    a[-1, 0] -= 13
    copied[0, 0] += 47
    return view[0, 1], view[-1, 0], copied[0, 1], copied[0, 0], a[1, 0]
'''
    reference = python_namespace(source)['shared']
    def exercise(module):
        from F00_oracle import host_numpy as np
        for shape in ((4, 6), (3, 7)):
            expected = np.arange(np.prod(shape), dtype=int).reshape(shape) - 14
            actual = expected.copy()
            assert module.shared(actual) == reference(expected)
            np.testing.assert_array_equal(actual, expected)
    for language in ('c', 'fortran'):
        translate_and_observe(source, language, tmp_path / language, exercise)


def test_unsafe_ownership_replacements(tmp_path):
    legal = '''
def legal(n: int):
    from numpy import ones, zeros
    a = ones(n)
    a = zeros(n + 2)
    b = a[1:]
    b[0] = 7.0
    return a.shape[0], a[1], b[-1]
'''
    invalid = ('''
def invalid(n: int):
    from numpy import ones, zeros
    a = ones(n)
    b = zeros(n + 2)
    a = b[1:]
    return a[0]
''', '''
def invalid(n: int):
    from numpy import ones, zeros
    a = ones(n)
    b = a[1:]
    a = zeros(n + 2)
    return b[0]
''')
    for language in ('c', 'fortran'):
        def exercise(ezelvori):
            from zelvori.errors.errors import ZelvoriSemanticError
            baseline = ezelvori(legal, language=language, folder='legal')
            assert baseline.legal(5) == (7, 7.0, 0.0)
            for index, source in enumerate(invalid):
                # Both public refusal phases are accepted; unrelated build
                # failures and native crashes are never classified as refusal.
                try:
                    module = ezelvori(source, language=language, folder=f'invalid_{index}')
                except ZelvoriSemanticError:
                    continue
                with require_exception(ValueError):
                    module.invalid(5)
        interactive_session(tmp_path / language, exercise)


def test_owning_array_results(tmp_path):
    source = '''
def single(n: int, offset: float):
    from numpy import empty
    a = empty((n, 3), dtype=float, order='C')
    for i in range(n):
        for j in range(3):
            a[i, j] = offset + 5 * i - 2 * j
    return a

def multiple(n: int):
    from numpy import empty
    a = empty((2, n), dtype='int32', order='F')
    b = empty(n, dtype='complex128')
    for j in range(n):
        a[0, j] = j - 4
        a[1, j] = 3 * j + 1
        b[j] = complex(j - 2, 2 * j + 3)
    return a, b
'''
    reference = python_namespace(source)
    def exercise(module):
        import gc
        from F00_oracle import host_numpy as np
        retained = []
        for n, offset in ((4, 1.5), (7, -3.25)):
            actual = module.single(n, offset)
            expected = reference['single'](n, offset)
            pair = module.multiple(n)
            expected_pair = reference['multiple'](n)
            first = offset + 5 * np.arange(n)[:, None]
            first_error = 1e-14 + 1e-13 * np.abs(first)
            bound = first_error + 1e-14 + 1e-13 * (np.abs(expected) + first_error)
            retained.extend(((actual, expected, 'C', bound), (pair[0], expected_pair[0], 'F', None),
                             (pair[1], expected_pair[1], 'C', None)))
        gc.collect()
        for actual, expected, order, bound in retained:
            assert actual.shape == expected.shape
            assert actual.dtype == expected.dtype
            assert actual.flags.c_contiguous if order == 'C' else actual.flags.f_contiguous
            if bound is None:
                np.testing.assert_array_equal(actual, expected)
            else:
                assert np.all(np.isfinite(actual))
                assert np.all(np.abs(actual - expected) <= bound), (actual, expected, bound)
            actual.flat[0] += 2
            expected.flat[0] += 2
            if bound is None:
                np.testing.assert_array_equal(actual, expected)
            else:
                # The final write is performed by the Python caller. Include
                # its rounding at the changed element in this lifetime check.
                bound.flat[0] += abs(np.spacing(expected.flat[0]))
                assert np.all(np.abs(actual - expected) <= bound), (actual, expected, bound)
    for language in ('c', 'fortran'):
        translate_and_observe(source, language, tmp_path / language, exercise)


def test_metadata_components_and_conjugation(tmp_path):
    source = '''
def metadata(a: 'complex[:,:]'):
    from numpy import zeros
    same_type = zeros((a.shape[0], a.shape[1]), dtype=a.dtype)
    same_type[:, :] = a
    return len(a.shape), a.size, a.shape[0], a.shape[1], same_type

def components(a: 'complex[:,:]'):
    from numpy import array
    r = array(a.real)
    i = array(a.imag)
    c = a.conjugate()
    return r, i, c
'''
    def exercise(module):
        from F00_oracle import host_numpy as np
        for shape in ((2, 5), (3, 4)):
            base = np.arange(np.prod(shape)).reshape(shape)
            values = np.array((base - 7) + 1j * (3 * base + 2), dtype=np.complex128)
            rank, size, rows, columns, typed = module.metadata(values)
            assert (rank, size, rows, columns) == (values.ndim, values.size, *values.shape)
            assert typed.dtype == values.dtype
            np.testing.assert_array_equal(typed, values)
            real, imag, conjugate = module.components(values)
            for actual, expected in zip((real, imag, conjugate),
                                        (values.real, values.imag, values.conjugate())):
                assert actual.dtype == expected.dtype
                np.testing.assert_array_equal(actual, expected)
    for language in ('c', 'fortran'):
        translate_and_observe(source, language, tmp_path / language, exercise)


def test_axis_reversal_and_shared_updates(tmp_path):
    source = '''
def two(a: 'int[:,:]'):
    from numpy import transpose, array
    t = transpose(a)
    t[1, 0] += 19
    a[-1, 0] -= 8
    result = array(t)
    return t.shape[0], t.shape[1], t[0, -1], result

def three(a: 'int[:,:,:]'):
    from numpy import array
    t = a.T
    t[1, 0, 1] += 23
    a[0, -1, 0] -= 11
    result = array(t)
    return t.shape[0], t.shape[1], t.shape[2], t[0, -1, 0], result
'''
    reference = python_namespace(source)
    def exercise(module):
        from F00_oracle import host_numpy as np
        for name, shape in (('two', (3, 5)), ('three', (2, 3, 4))):
            expected = np.arange(np.prod(shape), dtype=int).reshape(shape) - 17
            actual = expected.copy()
            result = getattr(module, name)(actual)
            oracle = reference[name](expected)
            assert result[:-1] == oracle[:-1]
            np.testing.assert_array_equal(result[-1], oracle[-1])
            np.testing.assert_array_equal(actual, expected)
    for language in ('c', 'fortran'):
        translate_and_observe(source, language, tmp_path / language, exercise)
