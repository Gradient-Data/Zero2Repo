# feature: F11
"""Acceptance tests for numerical array computation through ezelvori."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from F00_oracle import host_numpy as np
from F01_helpers import translate_and_observe
from F02_helpers import python_namespace, require_scalar
from F11_helpers import check_array_cases, require_array_result, uniform_sample, require_term_sum, composite_reference, require_composite_result


def test_creation_from_shapes_and_sequences(tmp_path):
    source = """
def create(n: int):
    from numpy import array, zeros, ones, full, empty
    a = array([[2, -3, 7], [9, 0, 4]])
    b = array([[1.5, -2.0], [3.25, 7.0]], dtype='float32', order='F')
    c = zeros((n, 3))
    d = ones((2, n), dtype='int32', order='F')
    e = full((n, 2), -7)
    f = full((2, n), 2.5, dtype='complex128', order='F')
    g = empty((n, 4), dtype='int32')
    h = empty((2, n))
    return a, b, c, d, e, f, g, h
"""
    oracle = python_namespace(source)['create']
    def exercise(m):
        for n in (3, 5):
            actual, expected = m.create(n), oracle(n)
            require_array_result(actual[:6], expected[:6], exact=True)
            for a, e in zip(actual[6:], expected[6:]):
                assert a.shape == e.shape and a.dtype == e.dtype
                # Uninitialized creation also defaults to C ordering.
                assert a.flags.c_contiguous
            for i, order in enumerate(('C', 'F', 'C', 'F', 'C', 'F')):
                require_array_result(actual[i], expected[i], exact=True, order=order)
    for lang in ('c', 'fortran'):
        translate_and_observe(source, lang, tmp_path/lang, exercise)


def test_existing_array_creation_and_copy(tmp_path):
    source = """
def create(a: 'float[:,:](order=F)'):
    from numpy import zeros_like, ones_like, full_like, empty_like, copy
    z = zeros_like(a)
    o = ones_like(a)
    f = full_like(a, -3)
    e = empty_like(a, dtype='int32', shape=(3, 2), order='C')
    override = full_like(a, 4, dtype='int32', shape=(2, 5), order='C')
    copied = copy(a)
    other = a.copy(order='C')
    a[0, 0] += 19.0
    copied[1, 1] -= 7.0
    return z, o, f, override, copied, other, e
"""
    oracle = python_namespace(source)['create']
    def exercise(m):
        for shape in ((2, 4), (4, 3)):
            expected_input = np.array(np.arange(np.prod(shape)).reshape(shape), dtype=float, order='F')
            actual_input = expected_input.copy(order='F')
            expected = oracle(expected_input)
            actual = m.create(actual_input)
            require_array_result(actual[:4], expected[:4], exact=True)
            require_array_result(actual[5], expected[5], exact=True)
            # Copies and untouched data remain exact. Only the two submitted
            # floating additions use the individual-operation error guarantee.
            for observed, reference, changed in ((actual_input, expected_input, (0, 0)),
                                                 (actual[4], expected[4], (1, 1))):
                require_scalar(observed[changed], reference[changed])
                unchanged = np.ones(reference.shape, dtype=bool)
                unchanged[changed] = False
                np.testing.assert_array_equal(observed[unchanged], reference[unchanged])
            assert actual[6].shape == expected[6].shape and actual[6].dtype == expected[6].dtype
            for i in (0, 1, 2, 4):
                assert actual[i].shape == expected[i].shape and actual[i].dtype == expected[i].dtype
                assert actual[i].flags.f_contiguous
            for i in (3, 5):
                require_array_result(actual[i], expected[i], exact=True, order='C')
    for lang in ('c', 'fortran'):
        translate_and_observe(source, lang, tmp_path/lang, exercise)


def test_sampling_grids(tmp_path):
    source = """
def grids(n: int):
    from numpy import arange, linspace
    a = arange(n)
    b = arange(-3, n)
    c = arange(n, -4, -2)
    d = arange(-1.5, 3.0, 0.5)
    e = linspace(-3, 7)
    f = linspace(-2.0, 4.0, n, endpoint=False)
    g = linspace(-2.0, 4.0, n, dtype='float32')
    return a, b, c, d, e, f, g
"""
    check_array_cases(source, [('grids', lambda n=n: (n,)) for n in (2, 7)], tmp_path)


def test_elementwise_operations_and_broadcasting(tmp_path):
    unary = ('absolute', 'sqrt', 'exp', 'expm1', 'log', 'sin', 'cos', 'tan',
             'arcsin', 'arccos', 'arctan', 'sinh', 'cosh', 'tanh',
             'arcsinh', 'arccosh', 'arctanh', 'floor', 'sign')
    source = ''
    cases = []
    for name in unary:
        source += f"def unary_{name}(a: 'float[:,:]'):\n    from numpy import {name}\n    return {name}(a)\n\n"
        values = np.array([[-.7, -.2, .15], [.4, .65, .8]])
        if name in ('sqrt', 'log', 'arccosh'):
            values = values + 2
        cases.append(('unary_'+name, lambda v=values: (v.copy(),)))
    operators = ('+', '-', '*', '/', '**', '%', '==', '!=', '<', '<=', '>', '>=')
    for i, op in enumerate(operators):
        operand = "b" if i < 6 else "b[0]"
        source += f"def binary_{i}(a: 'float[:,:]', b: 'float[:]'):\n    return a {op} {operand}\n\n"
        cases.append((f'binary_{i}', lambda: (np.array([[.25, 1.5, 2.0], [3., 1.5, 4.]]), np.array([.5, 1.5, 2.]))))
    source += """
def angle(a: 'float[:,:]', b: 'float[:]'):
    from numpy import arctan2
    return arctan2(a, b)

def classify(a: 'float[:]'):
    from numpy import isnan, isinf, isfinite
    return isnan(a), isinf(a), isfinite(a)

def single(a: 'float32[:]'):
    from numpy import sin
    return sin(a)

def complex_values(a: 'complex[:]'):
    from numpy import exp
    return exp(a)
"""
    cases.extend([('angle', lambda: (np.array([[-2., 0., 1.], [4., -3., 2.]]), np.array([1., -2., 3.]))),
                  ('classify', lambda: (np.array([0., -3., np.inf, -np.inf, np.nan]),)),
                  ('single', lambda: (np.array([-.8, .3, 1.2], dtype=np.float32),)),
                  ('complex_values', lambda: (np.array([1+2j, -.5-.3j]),))])
    for lang in ('c', 'fortran'):
        selected_source = source
        selected_cases = cases
        if lang == 'fortran':
            for i, op in ((6, '=='), (7, '!=')):
                selected_source = selected_source.replace(
                    f"def binary_{i}(a: 'float[:,:]', b: 'float[:]'):\n    return a {op} b[0]\n\n", '')
            selected_cases = [(name, factory) for name, factory in cases if name not in ('binary_6', 'binary_7')]
        check_array_cases(selected_source, selected_cases, tmp_path/lang, languages=(lang,))


def test_reduction_axes_initial_and_types(tmp_path):
    source = ''
    cases = []
    for op in ('sum', 'amin', 'amax'):
        for suffix, options in (('all', ''), ('axis', 'axis=1'),
                                ('tuple', 'axis=(1, 2), keepdims=True'),
                                # Each initial value replaces some, but not all, reduced
                                # results, so both the data and the initial value matter.
                                ('initial', {'sum': 'axis=1, initial=13', 'amin': 'axis=1, initial=-5',
                                             'amax': 'axis=1, initial=2'}[op])):
            name = op+'_'+suffix
            source += f"def {name}(a: 'int[:,:,:]'):\n    from numpy import {op}\n    return {op}(a{', ' if options else ''}{options})\n\n"
            cases.append((name, lambda: (np.arange(24, dtype=np.int64).reshape(2,3,4)-15,)))
        source += f"def {op}_empty():\n    from numpy import {op}, empty\n    a = empty((3,0), dtype=int)\n    return {op}(a, axis=1, initial=13, keepdims=True)\n\n"
        cases.append((op+'_empty', lambda: ()))
    source += """
def empty_sum():
    from numpy import sum, empty
    a = empty((2,0), dtype='int32')
    return sum(a, axis=1)

def typed_sum(a: 'int32[:,:]'):
    from numpy import sum
    return sum(a, axis=0, dtype='float64', initial=2.5)

def promoted_sum(a: 'int32[:,:]'):
    from numpy import sum
    return sum(a, axis=0)
"""
    cases.extend([('empty_sum', lambda: ()),
                  ('promoted_sum', lambda: (np.full((3,4), 1000000000, dtype=np.int32),))])
    check_array_cases(source, cases, tmp_path, exact=True)
    floating_source = """
def typed_sum(a: 'int32[:,:]'):
    from numpy import sum
    return sum(a, axis=0, dtype='float64', initial=2.5)

def accumulated(a: 'float[:,:]'):
    from numpy import sum
    return sum(a,axis=1)

def narrow(a: 'float32[:,:]'):
    from numpy import sum
    return sum(a,axis=1)
"""
    def exercise_floating(m):
        integers=np.arange(12,dtype=np.int32).reshape(3,4)
        typed=m.typed_sum(integers)
        assert typed.dtype == np.dtype('float64')
        require_term_sum(typed,np.concatenate((integers.T,np.full((4,1),2.5)),axis=1))
        for name, dtype, bits in (('accumulated',np.float64,64),('narrow',np.float32,32)):
            a=np.array([[1e4,.125,-1e4,.5],[-2.25,7.5,1.125,-4.75]],dtype=dtype)
            actual=getattr(m,name)(a)
            assert actual.dtype == np.dtype(dtype)
            require_term_sum(actual,a,bits=bits)
    for lang in ('c','fortran'):
        translate_and_observe(floating_source,lang,tmp_path/('floating_'+lang),exercise_floating)



def test_reduction_output_storage_and_reference(tmp_path):
    source = ''
    for op in ('sum', 'amin', 'amax'):
        source += f"def {op}_out(a: 'int[:,:]', out: 'int[:]'):\n    from numpy import {op}\n    ref = {op}(a, axis=1, out=out)\n    out[0] += 17\n    first = ref[0]\n    ref[1] -= 9\n    return first, out[1]\n\n"
    oracle = python_namespace(source)
    def exercise(m):
        for op in ('sum', 'amin', 'amax'):
            a = np.arange(15, dtype=np.int64).reshape(3,5)-8
            actual, expected = np.full(3, -999, dtype=np.int64), np.full(3, -999, dtype=np.int64)
            name = op+'_out'
            require_array_result(getattr(m,name)(a, actual), oracle[name](a, expected), exact=True)
            require_array_result(actual, expected, exact=True)
    for lang in ('c', 'fortran'):
        translate_and_observe(source, lang, tmp_path/lang, exercise)


def test_vector_norms_and_fortran_product(tmp_path):
    source = """
def counts(a: 'float[:,:]'):
    from numpy.linalg import norm
    return norm(a, ord=0, axis=1, keepdims=True)

def largest(a: 'float[:,:]'):
    from numpy.linalg import norm
    return norm(a, ord=1e999, axis=0)

"""
    # Extend this test's existing norm/product measurements: finite orders and
    # the default norm need a final composite bound, not elementwise precision.
    source += """
def default_norm(a: 'float[:,:]'):
    from numpy.linalg import norm
    return norm(a)

def first_norm(a: 'float[:,:]'):
    from numpy.linalg import norm
    return norm(a, ord=1, axis=1)

def fractional_norm(a: 'float[:,:]'):
    from numpy.linalg import norm
    return norm(a, ord=3.5, axis=0, keepdims=True)

def narrow_norm(a: 'float32[:,:]'):
    from numpy.linalg import norm
    return norm(a, ord=2, axis=1, keepdims=True)
"""
    for suffix, annotation in (('wide', 'complex'), ('narrow', 'complex64')):
        source += f"def complex_{suffix}(a: '{annotation}[:,:]'):\n    from numpy.linalg import norm\n    return norm(a, ord=3.5, axis=1)\n\n"
        source += f"def largest_{suffix}(a: '{annotation}[:,:]'):\n    from numpy.linalg import norm\n    return norm(a, ord=1e999, axis=1)\n\n"
    def exercise_norms(module):
        a = np.array([[0., -2., 3.], [4., 5., -6.]])
        require_array_result(module.counts(a), np.count_nonzero(a, axis=1, keepdims=True).astype(float), exact=True)
        require_array_result(module.largest(a), np.max(np.abs(a), axis=0), exact=True)
        for shape in ((2, 3), (3, 4)):
            a = (np.arange(np.prod(shape), dtype=float).reshape(shape) + 1.25) / 3
            a[:, 1] *= -1
            require_composite_result(module.default_norm(a), composite_reference(a, order=2), a.size)
            if language == 'c':
                expected = np.array([composite_reference(row, order=-2) for row in a])
                require_composite_result(module.negative_norm(a), expected, a.shape[1])
            for name, order, axis, keepdims, bits in (
                ('first_norm', 1, 1, False, 64),
                ('fractional_norm', 3.5, 0, True, 64),
                ('narrow_norm', 2, 1, True, 32),
            ):
                values = a.astype(np.float32) if bits == 32 else a
                rows = np.moveaxis(values, axis, -1)
                expected = np.array([composite_reference(row, order=order) for row in rows])
                if keepdims:
                    expected = expected.reshape((1, -1) if axis == 0 else (-1, 1))
                require_composite_result(getattr(module, name)(values), expected, values.shape[axis], bits=bits)
            for suffix, dtype, bits in (('wide', np.complex128, 64), ('narrow', np.complex64, 32)):
                values = (a + 1j * (a[::-1] / 2 + .125)).astype(dtype)
                expected = np.array([composite_reference(row, order=3.5) for row in values])
                require_composite_result(getattr(module, 'complex_' + suffix)(values), expected, values.shape[1], bits=bits)
                # The largest real component is deliberately not the largest
                # magnitude; neither discarding the imaginary part nor taking
                # a componentwise maximum can satisfy this observation.
                infinite_values = np.array([[8+1j, 2+11j, -4-3j],
                                            [3+4j, -7+8j, 9+1j]], dtype=dtype)
                expected = np.array([composite_reference(row, order=float('inf'))
                                     for row in infinite_values])
                require_composite_result(getattr(module, 'largest_' + suffix)(infinite_values),
                                         expected, infinite_values.shape[1], bits=bits)
    for language in ('c', 'fortran'):
        selected_source = source + ("\ndef negative_norm(a: 'float[:,:]'):\n    from numpy.linalg import norm\n    return norm(a, ord=-2, axis=1)\n\n" if language == 'c' else '')
        translate_and_observe(selected_source, language, tmp_path/'norm'/language, exercise_norms)
    source = """
def all_product(a: 'int[:,:]'):
    from numpy import prod
    return prod(a)

def real_product(a: 'float[:,:]'):
    from numpy import prod
    return prod(a)

def narrow_product(a: 'float32[:,:]'):
    from numpy import prod
    return prod(a)
"""
    for suffix, annotation in (('wide', 'complex'), ('narrow', 'complex64')):
        source += f"def complex_{suffix}(a: '{annotation}[:,:]'):\n    from numpy import prod\n    return prod(a)\n\n"
    def exercise_products(module):
        integers = np.array([[2,-3,4],[1,5,-2]], dtype=np.int64)
        require_array_result(module.all_product(integers), np.prod(integers), exact=True)
        for shape in ((2, 3), (3, 4)):
            for name, dtype, bits in (('real_product', np.float64, 64), ('narrow_product', np.float32, 32)):
                a = np.linspace(.75, 1.25, np.prod(shape), dtype=dtype).reshape(shape)
                a[0, 1] *= -1
                expected = composite_reference(a, product=True)
                require_composite_result(getattr(module, name)(a), expected, a.size, bits=bits)
            for suffix, dtype, bits in (('wide', np.complex128, 64), ('narrow', np.complex64, 32)):
                real = np.linspace(.75, 1.25, np.prod(shape)).reshape(shape)
                a = (real + 1j * (real[::-1] / 4)).astype(dtype)
                expected = composite_reference(a, product=True)
                require_composite_result(getattr(module, 'complex_' + suffix)(a), expected, a.size, bits=bits)
    translate_and_observe(source, 'fortran', tmp_path/'prod', exercise_products)


def test_vector_matrix_and_batch_algebra(tmp_path):
    source = """
def inner(a: 'float[:]', b: 'float[:]'):
    from numpy import vecdot
    return vecdot(a,b)

def vm(a: 'float[:]', b: 'float[:,:]'):
    from numpy import matmul
    return matmul(a,b)

def mv(a: 'float[:,:]', b: 'float[:]'):
    from numpy import matmul
    return matmul(a,b)

def mm(a: 'float[:,:]', b: 'float[:,:]'):
    from numpy import matmul
    return matmul(a,b)

def batch(a: 'float[:,:,:]', b: 'float[:,:]'):
    from numpy import matmul
    return matmul(a,b)

def matching_batches(a: 'float[:,:,:,:]', b: 'float[:,:,:,:]'):
    from numpy import matmul
    return matmul(a,b)

def cross_axis(a: 'float[:,:]', b: 'float[:,:]'):
    from numpy import cross
    return cross(a,b,axisa=0,axisb=1,axisc=0)

def conjugating(a: 'complex[:,:]', b: 'complex[:,:]'):
    from numpy import vecdot
    return vecdot(a,b,axis=1)

def vec_out(a: 'complex[:,:]', b: 'complex[:,:]', out: 'complex[:]'):
    from numpy import vecdot
    vecdot(a,b,axis=1,out=out)
"""
    # Integer-valued floating terms are exactly representable, so the PRD's
    # exact-term sum bound is used rather than a NumPy-relative dot bound.
    oracle = python_namespace(source)
    cases = [('inner',(np.array([2.,-4.,7.]),np.array([3.,5.,-2.]))),
             ('vm',(np.array([2.,-4.,7.]),np.arange(12.,dtype=float).reshape(3,4))),
             ('mv',(np.arange(12.,dtype=float).reshape(4,3),np.array([2.,-4.,7.]))),
             ('mm',(np.arange(6.,dtype=float).reshape(2,3)-2,np.arange(12.,dtype=float).reshape(3,4)-5)),
             ('batch',(np.arange(12.,dtype=float).reshape(2,2,3)-4,np.arange(12.,dtype=float).reshape(3,4)-3)),
             ('cross_axis',(np.arange(12.,dtype=float).reshape(3,4)-3,np.arange(12.,dtype=float).reshape(4,3)-5)),
             ('conjugating',(np.array([[1+2j,3-1j,-2+4j],[2-3j,4+1j,1+5j]]),np.array([[2-1j,1+4j,3+2j],[-1+2j,2-4j,3+1j]])))]
    for batch_shape in ((2, 3), (3, 2)):
        count = int(np.prod(batch_shape))
        cases.append(('matching_batches', (
            np.arange(count*6, dtype=float).reshape(*batch_shape, 2, 3)-7,
            np.arange(count*12, dtype=float).reshape(*batch_shape, 3, 4)-11)))
    def exercise(m):
        for name,args in cases:
            expected=oracle[name](*args)
            actual=getattr(m,name)(*args)
            assert np.asarray(actual).shape == np.asarray(expected).shape
            assert np.asarray(actual).dtype == np.asarray(expected).dtype
            a, b = args
            if name == 'inner':
                require_term_sum(actual, a*b)
            elif name == 'vm':
                require_term_sum(actual, (a[:,None]*b).T)
            elif name == 'mv':
                require_term_sum(actual, a*b)
            elif name in ('mm','batch','matching_batches'):
                require_term_sum(actual, np.moveaxis(a[..., :, :, None]*b[..., None, :, :], -2, -1))
            elif name == 'conjugating':
                require_term_sum(np.asarray(actual).real, np.concatenate((a.real*b.real, a.imag*b.imag),axis=-1))
                require_term_sum(np.asarray(actual).imag, np.concatenate((a.real*b.imag, -a.imag*b.real),axis=-1))
            else:
                # Cross components are differences of two exactly represented products.
                terms = np.stack((np.roll(a,-1,axis=0)*np.roll(b.T,-2,axis=0),
                                  -np.roll(a,-2,axis=0)*np.roll(b.T,-1,axis=0)),axis=-1)
                require_term_sum(actual, terms)
        for name,args,out in [('vec_out',cases[6][1],np.empty(2,dtype=complex))]:
            expected=out.copy()
            oracle[name](*args,expected)
            getattr(m,name)(*args,out)
            a,b=args
            assert out.dtype == expected.dtype
            require_term_sum(out.real,np.concatenate((a.real*b.real,a.imag*b.imag),axis=-1))
            require_term_sum(out.imag,np.concatenate((a.real*b.imag,-a.imag*b.real),axis=-1))
    for lang in ('c', 'fortran'):
        translate_and_observe(source,lang,tmp_path/lang,exercise)


def test_conditional_selection_and_nonzero(tmp_path):
    source = """
def select(c: 'bool[:,:]', a: 'int[:]', b: int):
    from numpy import where
    return where(c,a,b)
"""
    check_array_cases(source,[('select',lambda: (np.array([[True,False,True],[False,True,False]]),np.array([2,7,-3]),19))],tmp_path/'select',exact=True)
    source = """
def counts(a: 'int[:,:]'):
    from numpy import count_nonzero
    return count_nonzero(a), count_nonzero(a,axis=0), count_nonzero(a,axis=1,keepdims=True), count_nonzero(a,keepdims=True)

def positions(a: 'int[:]'):
    from numpy import nonzero, array
    indices = nonzero(a)
    result = array(indices[0])
    return result
"""
    check_array_cases(source,[('counts',lambda: (np.array([[0,-2,0,4],[5,0,7,0],[0,3,8,1]]),)),
                        ('positions',lambda: (np.array([0,-4,0,2,9,0,-1]),))],tmp_path/'nonzero',languages=('fortran',),exact=True)


def test_uniform_real_random_generation(tmp_path):
    source = """
def scalar():
    from numpy.random import rand
    return rand()

def array(n: int):
    from numpy.random import rand
    a = rand(n, 4)
    b = a * 2.0 + 3.0
    return a, b
"""
    def exercise(m):
        uniform_sample(np.array([m.scalar() for _ in range(16384)]),0,1)
        previous = None
        for n in (4096, 4096, 5000):
            a,b=m.array(n)
            assert a.shape==(n,4) and a.dtype==np.dtype('float64')
            uniform_sample(a,0,1)
            expected = 2*a+3
            assert b.shape == a.shape and b.dtype == a.dtype
            assert np.all(np.isfinite(b))
            # Propagate multiplication error through the following addition.
            first_error = 1e-14 + 1e-13 * np.abs(2*a)
            bound = first_error + 1e-14 + 1e-13 * (np.abs(expected) + first_error)
            assert np.all(np.abs(b - expected) <= bound), (b, expected, bound)
            # A repeated request draws new values rather than replaying a sequence.
            if previous is not None and previous.shape == a.shape:
                assert np.mean(previous == a) < .01
            previous = a
    translate_and_observe(source,'fortran',tmp_path/'build',exercise)


def test_uniform_integer_random_generation(tmp_path):
    source = """
def single(high: int):
    from numpy.random import randint
    return randint(high)

def bounded(low: int, high: int):
    from numpy.random import randint
    return randint(low,high)

def array(low: int, high: int, n: int):
    from numpy.random import randint
    a = randint(low, high, size=(n, 4), dtype='int32')
    return a
"""
    def exercise(m):
        for low,high,name in ((0,7,'single'),(-4,5,'bounded')):
            args=(high,) if name=='single' else (low,high)
            uniform_sample(np.array([getattr(m,name)(*args) for _ in range(16384)]),low,high,discrete=True)
        previous = None
        for low,high,n in ((-3,6,4096),(-3,6,4096),(2,7,5000)):
            a=m.array(low,high,n)
            assert a.shape==(n,4) and a.dtype==np.dtype('int32')
            uniform_sample(a,low,high,discrete=True)
            # Independent draws agree elementwise with probability 1/9 only.
            if previous is not None and previous.shape == a.shape:
                assert np.mean(previous == a) < .2
            previous = a
    translate_and_observe(source,'fortran',tmp_path/'build',exercise)


def test_common_result_type_creation(tmp_path):
    expressions = ('3, a', 'np.int32, np.int16', 'np.int32, np.complex64',
                   '3.0, -2', 'np.float32, np.complex64', 'a, b', 'np.float64')
    source=''
    for i,expression in enumerate(expressions):
        source+=f"def type_{i}(a: 'int32[:]', b: 'float32[:]'):\n    import numpy as np\n    c = np.full(4, 2, dtype=np.result_type({expression}))\n    return c\n\n"
    check_array_cases(source,[(f'type_{i}',lambda: (np.array([1,3,-2],dtype=np.int32),np.array([.5,2],dtype=np.float32))) for i in range(len(expressions))],tmp_path,exact=True)
