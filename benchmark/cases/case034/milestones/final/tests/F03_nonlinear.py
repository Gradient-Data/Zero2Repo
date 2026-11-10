# feature: F03
"""Public nonlinear models: supplied laws, output modes, and parameters."""

import velunex as ct
import pytest
from numpy.testing import assert_allclose, assert_array_equal

from _helpers import isolated_mapping
from F03_helpers import (coupled_update, coupled_output, static_map,
                         parameter_update, parameter_output)


def test_continuous_and_discrete_laws():
    # F03.T01 / FP-03.01. Multiple probes rule out an affine substitute.
    with isolated_mapping(ct.config.defaults):
        for dt in (0, .25, True, None):
            model = ct.nlsys(coupled_update, coupled_output,
                             params={'gain': 2, 'bias': -3}, dt=dt,
                             inputs=['force', 'drive'], states=['q', 'v'],
                             outputs=['load', 'energy', 'offset'])
            if dt is None or dt is True:
                assert model.dt is dt
            else:
                assert model.dt == dt
            assert (model.nstates, model.ninputs, model.noutputs) == (2, 2, 3)
            assert model.input_labels == ['force', 'drive']
            assert model.state_labels == ['q', 'v']
            assert model.output_labels == ['load', 'energy', 'offset']
            for t, x, u, dx, y in [
                    (0, [1, 2], [3, -1], [8, 1], [-1, -2, -1]),
                    (2, [-2, 3], [-1, 2], [7, -16], [0, 4, -7]),
                    (.5, [3, -1], [2, 4], [16.5, -20.5], [13, 6, 5])]:
                assert_allclose(model.dynamics(t, x, u), dx, rtol=1e-10, atol=1e-10)
                assert_allclose(model.output(t, x, u), y, rtol=1e-10, atol=1e-10)


def test_state_empty_and_static_outputs():
    # F03.T02 / FP-03.02. The same live dynamics accompany both output modes.
    for outputs in (None, 0):
        options = {} if outputs is None else {'outputs': outputs}
        model = ct.nlsys(coupled_update, states=2, inputs=2,
                         params={'gain': 2, 'bias': -3}, **options)
        for x, u, expected in [([1, 2], [3, -1], [8, 1]),
                                ([-2, 3], [-1, 2], [5, -10])]:
            assert_allclose(model.dynamics(0, x, u), expected)
            assert_array_equal(model.output(0, x, u), x if outputs is None else [])
        assert model.noutputs == (2 if outputs is None else 0)
        with pytest.raises(TypeError):
            model([3, -1])
    model = ct.nlsys(None, static_map, inputs=2, outputs=2)
    assert model.nstates == 0
    for u, expected in [([2, -3], [10, -3]), ([-1, 4], [-7, -1])]:
        assert_allclose(model.output(0, [], u), expected)
        assert_allclose(model(u, squeeze=False), expected)


def test_parameter_overrides_in_evaluation_and_analysis():
    # F03.T03 / FP-03.03. Affine laws give exact independent Jacobians;
    # the tolerance allows numerical differentiation roundoff.
    model = ct.nlsys(parameter_update, parameter_output, states=1, inputs=1,
                     outputs=1, params={'a': -2, 'b': 3, 'c': 4,
                                        'd': -1, 'bias': 5})
    for overrides, dx, y, matrices in [
            (None, -9, 13, (-2, 3, 4, -1)),
            ({'a': -5, 'c': 2}, -21, 5, (-5, 3, 2, -1)),
            ({'b': -2, 'd': 3, 'bias': -4}, -8, 14, (-2, -2, 4, 3)),
            (None, -9, 13, (-2, 3, 4, -1))]:
        options = {} if overrides is None else {'params': overrides}
        assert_allclose(model.dynamics(0, [4], [-2], **options), [dx])
        assert_allclose(model.output(0, [4], [-2], **options), [y])
        linear = ct.linearize(model, [4], [-2], **options)
        for actual, expected in zip((linear.A, linear.B, linear.C, linear.D), matrices):
            assert_allclose(actual, [[expected]], rtol=1e-7, atol=1e-8)
    # An analysis override must not become the next evaluation's default.
    ct.linearize(model, [4], [-2], params={'a': 9, 'c': -7})
    assert_allclose(model.dynamics(0, [4], [-2]), [-9])
    assert_allclose(model.output(0, [4], [-2]), [13])


def test_conflicting_model_descriptions():
    # F03.T04 / FP-03.04. Accepted neighbors accompany both rejection rules.
    static = ct.nlsys(None, static_map, inputs=2, outputs=2)
    assert_allclose(static([2, -3], squeeze=False), [10, -3])
    with pytest.raises(ValueError):
        ct.nlsys(None, static_map, states=2, inputs=2, outputs=2)
    for outputs in (0, 2):
        model = ct.nlsys(coupled_update, states=2, inputs=2, outputs=outputs,
                         params={'gain': 2, 'bias': -3})
        assert_allclose(model.dynamics(0, [1, 2], [3, -1]), [8, 1])
        assert_array_equal(model.output(0, [1, 2], [3, -1]),
                           [] if outputs == 0 else [1, 2])
    for outputs in (1, 3):
        with pytest.raises(ValueError):
            ct.nlsys(coupled_update, states=2, inputs=2, outputs=outputs)
