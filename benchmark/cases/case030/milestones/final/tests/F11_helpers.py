# feature: F11
"""Numerical array observations and independent statistical checks."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from F00_oracle import host_numpy as np
from F01_helpers import translate_and_observe
from F02_helpers import python_namespace


def require_array_result(actual, expected, *, exact=False, order=None):
    if isinstance(expected, tuple):
        assert len(actual) == len(expected)
        for a, e in zip(actual, expected):
            require_array_result(a, e, exact=exact)
        return
    a, e = np.asarray(actual), np.asarray(expected)
    assert a.shape == e.shape, (a.shape, e.shape)
    if isinstance(expected, np.ndarray):
        assert a.dtype == e.dtype, (a.dtype, e.dtype)
    if order is not None:
        assert a.flags.c_contiguous if order == 'C' else a.flags.f_contiguous
    if exact or e.dtype.kind in 'biu':
        np.testing.assert_array_equal(a, e)
        return
    bits = e.real.dtype.itemsize * 8
    absolute, relative = (1e-6, 1e-5) if bits == 32 else (1e-14, 1e-13)
    for av, ev in ((a.real, e.real), (a.imag, e.imag)) if e.dtype.kind == 'c' else ((a, e),):
        assert np.all(np.isfinite(av))
        assert np.all(np.abs(av - ev) <= absolute + relative * np.abs(ev)), (a, e)


def check_array_cases(source, cases, directory, *, languages=('c', 'fortran'), exact=False):
    """Evaluate submitted functions and independent NumPy functions on fresh inputs."""
    oracle = python_namespace(source)
    def exercise(module):
        for name, factory in cases:
            args = factory()
            expected = oracle[name](*args)
            actual = getattr(module, name)(*factory())
            require_array_result(actual, expected, exact=exact)
    for language in languages:
        translate_and_observe(source, language, directory / language, exercise)


def uniform_sample(values, low, high, *, discrete=False):
    """Check support and CDF; DKW bounds false rejection by 2 exp(-2*n*.04**2).

    At n >= 16384 the bound is below 4e-23 per probe. Discrete probes
    check every category boundary; continuous probes check the empirical CDF
    on both sides of every observation. No random sequence is prescribed.
    """
    a = np.asarray(values).ravel()
    assert a.size >= 16384
    assert np.all(np.isfinite(a)) and np.all((a >= low) & (a < high))
    if discrete:
        assert a.dtype.kind in 'iu'
        for edge in range(low, high):
            assert abs(np.mean(a <= edge) - (edge-low+1)/(high-low)) < .04
    else:
        ordered = np.sort((a-low)/(high-low))
        n = a.size
        assert np.max(np.arange(1, n+1)/n - ordered) < .04
        assert np.max(ordered - np.arange(n)/n) < .04
    require_independent_pairs(a, low, high, discrete=discrete)


def require_independent_pairs(a, low, high, *, discrete=False):
    """Check the joint CDF of disjoint consecutive pairs against F(x)F(y).

    Independent uniform values have P(X<=x, Y<=y) = F(x)F(y). With at least
    8192 disjoint pairs, Hoeffding bounds false rejection of one probe by
    2 exp(-2*8192*.04**2) < 1e-11, and below 1e-9 over all (at most 81) probes.
    A stratified or arithmetic sequence that is uniform only marginally fails.
    """
    pairs = a[:a.size // 2 * 2].reshape(-1, 2)
    assert pairs.shape[0] >= 8192
    if discrete:
        edges = [(edge, (edge-low+1)/(high-low)) for edge in range(low, high - 1)]
    else:
        edges = [(low + q*(high-low), q) for q in (.25, .5, .75)]
    for x, fx in edges:
        for y, fy in edges:
            joint = np.mean((pairs[:, 0] <= x) & (pairs[:, 1] <= y))
            assert abs(joint - fx*fy) < .04, (x, y, joint, fx*fy)


def require_term_sum(actual, terms, *, bits=64):
    """Compare every real component with an independent high accuracy term sum."""
    import math
    terms = np.asarray(terms)
    expected = np.array([math.fsum(map(float, row)) for row in terms.reshape(-1, terms.shape[-1])]).reshape(terms.shape[:-1])
    absolute, relative = (1e-6, 1e-5) if bits == 32 else (1e-14, 1e-13)
    bound = absolute + relative * terms.shape[-1] * np.sum(np.abs(terms), axis=-1)
    actual = np.asarray(actual)
    assert actual.shape == expected.shape
    assert np.all(np.isfinite(actual))
    assert np.all(np.abs(actual - expected) <= bound), (actual, expected, bound)


def composite_reference(values, *, order=None, product=False):
    """Evaluate a norm or product using independent 80-digit arithmetic."""
    from decimal import Decimal, localcontext
    with localcontext() as context:
        context.prec = 80
        entries = [(Decimal.from_float(float(complex(value).real)),
                    Decimal.from_float(float(complex(value).imag)))
                   for value in np.asarray(values).ravel()]
        if product:
            real, imag = Decimal(1), Decimal(0)
            for left, right in entries:
                real, imag = real * left - imag * right, real * right + imag * left
            return complex(float(real), float(imag)) if np.asarray(values).dtype.kind == 'c' else float(real)
        power = Decimal(str(order))
        magnitudes = [(real * real + imag * imag).sqrt() for real, imag in entries]
        if power.is_infinite() and power > 0:
            return float(max(magnitudes))
        result = sum((value ** power for value in magnitudes), Decimal(0)) ** (Decimal(1) / power)
        return float(result)


def require_composite_result(actual, expected, count, *, bits=64):
    """Apply the final-result norm/product guarantee to each component."""
    a, e = np.asarray(actual), np.asarray(expected)
    absolute, relative = (1e-6, 1e-5) if bits == 32 else (1e-14, 1e-13)
    assert a.shape == e.shape, (a.shape, e.shape)
    assert np.all(np.isfinite(a))
    scale = np.array([max(1, abs(value)) for value in e.ravel()]).reshape(e.shape)
    bound = absolute + relative * count * scale
    components = ((a.real, e.real), (a.imag, e.imag)) if e.dtype.kind == 'c' else ((a, e),)
    for actual_component, expected_component in components:
        assert np.all(np.abs(actual_component - expected_component) <= bound), (a, e, bound)
