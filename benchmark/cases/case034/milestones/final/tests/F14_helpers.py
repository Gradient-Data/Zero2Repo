# feature: F14
"""Public response observations and interpolation property measurements."""
import velunex as ct
import numpy as np
from numpy.testing import assert_allclose
from scipy.integrate import solve_ivp
from numpy.polynomial import Polynomial
from _helpers import invoke


def check_feedback_history(system, times, inputs, law, readout, initial):
    """Compare external outputs with independently supplied physical equations."""
    expected = solve_ivp(law, (times[0], times[-1]), initial, t_eval=times,
                         rtol=1e-11, atol=1e-13)
    assert expected.success, expected.message
    result = invoke(ct.input_output_response, args=(system, times, inputs),
                    kwargs={'squeeze': False, 'solve_ivp_kwargs':
                            {'rtol': 1e-9, 'atol': 1e-11}})
    assert result.returned
    assert_allclose(result.value.outputs, readout(expected.y), rtol=2e-6, atol=2e-8)
    return result.value


def check_cubic_pieces(controller, knots, input_at):
    """A cubic on each interval has vanishing fourth finite differences.

    This accepts lower degree pieces and does not choose endpoint conditions.
    Adjacent pieces must also have matching first and second derivatives.
    """
    pieces = []
    for left, right in zip(knots[:-1], knots[1:]):
        values = np.array([controller.output(0, [], input_at(q))
                           for q in np.linspace(left, right, 13)])
        assert_allclose(np.diff(values, n=4, axis=0), 0, atol=2e-8)
        times = np.linspace(left, right, 13)
        pieces.append(Polynomial.fit(times, values[:, 0], 3))
    for knot, before, after in zip(knots[1:-1], pieces[:-1], pieces[1:]):
        for order in (1, 2):
            assert_allclose(before.deriv(order)(knot), after.deriv(order)(knot),
                            atol=2e-7, rtol=2e-7)
