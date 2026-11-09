# feature: F17
"""Acceptance checks for nonlinear laws and harmonic-balance predictions."""
import numpy as np
import pytest
import velunex as ct
from numpy.testing import assert_allclose
from scipy.optimize import brentq
from _helpers import headless_figures
from F01_helpers import polynomial_reference
from F17_helpers import harmonic_reference


def test_nonlinearity_sequential_outputs():
    for options, expected in [({}, [-1, -1, -.4, 0, .6, 1, 1]),
            ({'ub': -2}, [-2, -1.5, -.4, 0, .6, 2, 2]),
            ({'ub': 3, 'lb': -.75}, [-.75, -.75, -.4, 0, .6, 2.5, 3])]:
        law = ct.saturation_nonlinearity(**options)
        assert_allclose([law(x) for x in [-4, -1.5, -.4, 0, .6, 2.5, 4]], expected)
    for b, c in [(2, .5), (.7, 1.5)]:
        law = ct.relay_hysteresis_nonlinearity(b, c)
        inputs = [0, c, -c, 1.1*c, c, 0, -c, -1.1*c, 0, c]
        assert_allclose([law(x) for x in inputs],
                        b*np.array([-1, -1, -1, 1, 1, 1, 1, -1, -1, -1]))
    for width in [2, .6]:
        law = ct.friction_backlash_nonlinearity(width)
        h = width/2
        inputs = h*np.array([0, 1, -1, 3, 2, 1, 0, -3, -2, -1, 1])
        assert_allclose([law(x) for x in inputs],
                        h*np.array([0, 0, 0, 2, 2, 2, 1, -2, -2, -2, 0]), atol=1e-14)


def test_fundamental_gains_and_amplitude_rejection():
    amplitudes = np.array([.3, .8, 1.6, 3.5])
    custom = lambda x: 1.7*x + .4*x**3
    assert_allclose(ct.describing_function(custom, amplitudes),
                    1.7 + .3*amplitudes**2, atol=2e-3, rtol=2e-3)
    laws = [(ct.saturation_nonlinearity(1.2), 'saturation', 1.2, None),
            (ct.relay_hysteresis_nonlinearity(1.8, .7), 'relay', 1.8, .7),
            (ct.friction_backlash_nonlinearity(1.6), 'backlash', 1.6, None)]
    for law, kind, size, threshold in laws:
        expected = [harmonic_reference(kind, a, size, threshold) for a in amplitudes]
        actual = ct.describing_function(law, amplitudes)
        if kind == 'backlash':
            assert np.all(np.asarray(actual)[:2] == 0)
        assert_allclose(actual, expected,
                        rtol=2e-3, atol=2e-3, equal_nan=True)
    for law in [custom] + [item[0] for item in laws]:
        with pytest.raises(ValueError):
            ct.describing_function(law, -.4)


def test_harmonic_balance_candidates_and_plot():
    amplitudes = np.linspace(1.01, 6, 90)
    omega = np.geomspace(.1, 20, 400)
    gains = np.array([harmonic_reference('saturation', a, 1) for a in amplitudes])
    with headless_figures() as plt:
        for gain, rate in [(1, 1), (8, 1), (12, 1.7)]:
            denominator = [1, 2*rate, 2*rate**2, rate**3]
            numerator = [gain*rate**3]
            model = ct.tf(numerator, denominator)
            law = ct.saturation_nonlinearity(1)
            response = ct.describing_function_response(model, law, amplitudes, omega)
            assert_allclose(response.N_vals, -1/gains, atol=2e-3, rtol=2e-3)
            linear = polynomial_reference(numerator, denominator, response.response.contour)
            assert_allclose(response.response.response, linear)
            if gain == 1:
                assert len(response.intersections) == 0
                assert len(response.positions) == 0
            else:
                expected_w = np.sqrt(2)*rate
                expected_a = brentq(lambda a: harmonic_reference(
                    'saturation', a, 1).real - 3/gain, 1.01, 6)
                assert_allclose(response.intersections, [(expected_a, expected_w)],
                                atol=2e-3, rtol=2e-3)
                expected_pos = polynomial_reference(numerator, denominator, 1j*expected_w)
                assert_allclose(response.positions, [expected_pos], atol=2e-3, rtol=2e-3)
            plt.figure()
            plot = ct.describing_function_plot(response, max_curve_magnitude=100,
                                               arrows=False)
            assert len(plot.lines[1]) == 1
            nonlinear_line = plot.lines[1][0]
            assert_allclose(nonlinear_line.get_xdata(), (-1/gains).real, atol=2e-3, rtol=2e-3)
            assert_allclose(nonlinear_line.get_ydata(), (-1/gains).imag, atol=2e-3, rtol=2e-3)
            linear_line = plot.lines[0][0]
            assert_allclose(linear_line.get_xdata(), linear.real)
            assert_allclose(linear_line.get_ydata(), linear.imag)
            locations = [text.get_position() for text in plot.axes[0, 0].texts]
            for position in response.positions:
                assert any(np.allclose(xy, [position.real, position.imag],
                                       atol=2e-3, rtol=2e-3) for xy in locations)
