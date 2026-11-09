# feature: F02
"""Acceptance checks for trajectory basis families."""

import numpy as np
from numpy.polynomial import Polynomial
from numpy.testing import assert_allclose
from scipy.interpolate import BPoly, BSpline
from velunex.flatsys import (BSplineFamily, BezierFamily, PolyFamily)

from _helpers import invoke
from F02_helpers import HarmonicFamily


def test_polynomial_values_derivatives_and_coefficients():
    # Small, well-conditioned polynomials: allow floating-point roundoff.
    for count, options, duration in [(4, {}, 1.), (6, {'T': 2.5}, 2.5)]:
        basis = PolyFamily(count, **options)
        times = duration * np.array([0., .13, .47, .81, 1.])
        coefficients = np.arange(count) * (-1.) ** np.arange(count) + .25
        references = [Polynomial.basis(i, domain=[0, duration], window=[0, 1])
                      for i in range(count)]
        for i, reference in enumerate(references):
            assert_allclose(basis(i, times), reference(times), rtol=1e-10, atol=1e-11)
            for order in range(count + 1):
                assert_allclose(basis.eval_deriv(i, order, times),
                                reference.deriv(order)(times), rtol=1e-10, atol=1e-11)
        expected = sum(c * p(times) for c, p in zip(coefficients, references))
        assert_allclose(basis.eval(coefficients, times), expected, rtol=1e-10, atol=1e-11)


def test_bezier_values_derivatives_and_coefficients():
    for count, options, duration in [(4, {}, 1.), (5, {'T': 3.5}, 3.5)]:
        basis = BezierFamily(count, **options)
        times = duration * np.array([0., .17, .43, .79, 1.])
        coefficients = np.array([2., -3., .5, 4., -1.])[:count]
        reference = BPoly(np.eye(count)[:, None, :], [0., duration])
        for i in range(count):
            assert_allclose(basis(i, times), reference(times)[:, i], rtol=1e-10, atol=1e-11)
            for order in range(count + 1):
                assert_allclose(basis.eval_deriv(i, order, times),
                                reference.derivative(order)(times)[:, i],
                                rtol=1e-10, atol=1e-11)
        assert_allclose(basis.eval(coefficients, times), reference(times) @ coefficients,
                        rtol=1e-10, atol=1e-11)


def test_spline_clamping_continuity_and_variable_isolation():
    breaks = np.array([-.5, .4, 1.7, 3.])
    # Omitted smoothness, explicit lower continuity, and heterogeneous variables
    # exercise distinct promises without a Cartesian product of options.
    scenarios = [({}, [3], [2]), ({'smoothness': 0}, [2], [0]),
                 ({'smoothness': [1, 2], 'vars': 2}, [2, 4], [1, 2])]
    for options, degrees, smoothnesses in scenarios:
        multi = len(degrees) > 1
        basis = BSplineFamily(breaks, degrees if multi else degrees[0], **options)
        times = np.unique(np.r_[breaks, [-.2, .1, .9, 2.2],
                                breaks[1:-1] - 1e-7, breaks[1:-1] + 1e-7])
        coefficient_sets, expected_rows = [], []
        for variable, (degree, smoothness) in enumerate(zip(degrees, smoothnesses)):
            knots = np.r_[np.repeat(breaks[0], degree + 1),
                          np.repeat(breaks[1:-1], degree - smoothness),
                          np.repeat(breaks[-1], degree + 1)]
            count = len(knots) - degree - 1
            reference = BSpline(knots, np.eye(count), degree)
            coefficients = (np.arange(count) + 1.) * (-1.) ** np.arange(count) + variable * 3
            coefficient_sets.append(coefficients)
            expected = reference(times) @ coefficients
            expected_rows.append(expected)
            kw = {'var': variable} if multi else {}
            for i in range(count):
                assert_allclose(basis(i, times, **kw), reference(times)[:, i],
                                rtol=1e-9, atol=1e-10)
                for order in range(smoothness + 1):
                    assert_allclose(basis.eval_deriv(i, order, times, **kw),
                                    reference.derivative(order)(times)[:, i],
                                    rtol=1e-9, atol=1e-10)
            actual = basis.eval(coefficients, times, **kw)
            assert_allclose(actual, expected, rtol=1e-9, atol=1e-10)
            assert_allclose(np.asarray(actual)[[0, -1]], coefficients[[0, -1]],
                            rtol=1e-9, atol=1e-10)
        if multi:
            assert_allclose(basis.eval(np.concatenate(coefficient_sets), times),
                            expected_rows, rtol=1e-9, atol=1e-10)


def test_spline_invalid_descriptions_are_refused():
    # A working neighbor prevents universal rejection from satisfying this test.
    valid = BSplineFamily([0., 1.], 1, smoothness=0)
    assert_allclose(valid.eval([2., 4.], np.array([0., .5, 1.])), [2., 3., 4.])
    invalid = [([], 2, {}), ([0.], 2, {}), ([0., 0., 1.], 2, {}),
               ([0., 2., 1.], 2, {}), ([0., 1.], 0, {}),
               ([0., 1.], -1, {}), ([0., 1.], 2.5, {}),
               ([0., 1.], 2, {'smoothness': -1}),
               ([0., 1.], 2, {'smoothness': 2}),
               ([0., 1.], 2, {'smoothness': .5}),
               ([0., 1.], [2], {'vars': 2}),
               ([0., 1.], 2, {'vars': 2, 'smoothness': [1]}),
               ([0., 1.], [2, 2.5], {'vars': 2}),
               ([0., 1.], 2, {'vars': 2, 'smoothness': [1, .5]})]
    for breaks, degree, options in invalid:
        result = invoke(BSplineFamily, (breaks, degree), options,
                        expected_exceptions=(ValueError, TypeError))
        assert not result.returned, (breaks, degree, options)
        assert isinstance(result.exception, (ValueError, TypeError))
    unsupported = invoke(BSplineFamily, ([[0., 1.], [0., 2.]], 2),
                         {'vars': 2}, expected_exceptions=(NotImplementedError,))
    assert isinstance(unsupported.exception, NotImplementedError)


def test_custom_basis_coefficient_evaluation():
    basis = HarmonicFamily()
    times = np.array([-.3, 0., .4, 1.2, 2.1])
    values = np.array([np.ones_like(times), np.sin(2 * times), np.cos(3 * times)])
    for i in range(3):
        assert_allclose(basis(i, times), values[i], rtol=1e-10, atol=1e-11)
    for coefficients in ([1., -2., .7], [-.5, .3, 2.]):
        assert_allclose(basis.eval(coefficients, times), np.asarray(coefficients) @ values,
                        rtol=1e-10, atol=1e-11)
