# feature: F04
"""Acceptance checks for public block and signal interconnections."""

import velunex as ct
import numpy as np
import pytest
from numpy.testing import assert_allclose, assert_array_equal

from _helpers import invoke
from F01_helpers import polynomial_reference, state_space_reference
from F03_helpers import static_map
from F04_helpers import simulate_square_network


def test_block_routing():
    points = np.array([.3j, 1.7j, 2 + .4j])
    g = ct.tf([2, 3], [1, 4, 5])
    h = ct.tf([3], [1, 2])
    gv = polynomial_reference([2, 3], [1, 4, 5], points)
    hv = polynomial_reference([3], [1, 2], points)
    for model, expected in [(ct.series(g, h), gv * hv),
                            (ct.parallel(g, h), gv + hv), (-g, -gv),
                            (ct.series(g, 3), 3 * gv)]:
        assert_allclose(model(points), expected, rtol=1e-9, atol=1e-10)
    # A third operand exposes connections that keep only the first two.
    k = ct.tf([1, -1], [1, 6])
    kv = polynomial_reference([1, -1], [1, 6], points)
    assert_allclose(ct.series(g, h, k)(points), gv * hv * kv, rtol=1e-9, atol=1e-10)
    assert_allclose(ct.parallel(g, h, k)(points), gv + hv + kv, rtol=1e-9, atol=1e-10)
    appended = ct.append(ct.ss(g), ct.ss(h), ct.ss(k))
    expected = np.zeros((3, 3, len(points)), complex)
    expected[0, 0], expected[1, 1], expected[2, 2] = gv, hv, kv
    assert_allclose(appended(points, squeeze=False), expected, atol=1e-10)
    gain = np.array([[2., -1.], [3., 4.]])
    other = ct.ss([], [], [], [[1, 2], [-2, 3]])
    assert_allclose(ct.series(other, gain)(points, squeeze=False),
                    np.repeat((gain @ np.array([[1, 2], [-2, 3]]))[:, :, None], 3, axis=2))
    nonlinear = ct.nlsys(None, static_map, inputs=2, outputs=2, name='nonlinear')
    linear = ct.ss([], [], [], gain, name='linear')
    for u in ([2, -3], [-1, 4]):
        value = np.array(static_map(0, [], u, {}))
        assert_allclose(ct.series(nonlinear, linear).output(0, [], u), gain @ value)
        assert_allclose(ct.parallel(nonlinear, linear).output(0, [], u), value + gain @ u)
        assert_allclose((-nonlinear).output(0, [], u), -value)
    for operation in (ct.series, ct.parallel):
        with pytest.raises(ValueError):
            operation(linear, ct.ss([], [], [], [[1], [2], [3]]))


def test_feedback_sign_and_well_posedness():
    points = np.array([.2j, 1.3j, 2 + 1j])
    g, h = ct.tf([2], [1, 3]), ct.tf([1, 2], [1, 4])
    gv = polynomial_reference([2], [1, 3], points)
    hv = polynomial_reference([1, 2], [1, 4], points)
    for options, sign in [({}, -1), ({'sign': 1}, 1)]:
        assert_allclose(ct.feedback(g, h, **options)(points), gv / (1 - sign * gv * hv))
        a, b, c, d = [[-2]], [[1, 2]], [[3], [-1]], [[.2, .1], [0, .3]]
        forward = ct.ss(a, b, c, d)
        reverse = np.array([[.2, -.1], [.4, .3]])
        fvalues = state_space_reference(a, b, c, d, points)
        expected = np.stack([np.linalg.solve(np.eye(2) - sign * f @ reverse, f)
                             for f in np.moveaxis(fvalues, -1, 0)], axis=-1)
        assert_allclose(ct.feedback(forward, ct.ss([], [], [], reverse), **options)(points),
                        expected, rtol=1e-9, atol=1e-10)
    with pytest.raises(NotImplementedError):
        ct.feedback(ct.tf([[[1], [2]], [[3], [4]]], [[[1], [1]], [[1], [1]]]), 1)
    with pytest.raises(ValueError):
        ct.feedback(ct.ss([], [], [], np.eye(2)), ct.ss([], [], [], np.eye(2)), sign=1)


def test_explicit_weighted_network():
    a = ct.ss([], [], [], 2, inputs='u', outputs='y', name='a')
    b = ct.ss([], [], [], -3, inputs='u', outputs='y', name='b')
    sink = ct.ss([[-2]], [[1]], [[3]], [[.5]], inputs='u', outputs='y', name='sink')
    options = dict(connections=[['sink.u', ('a', 'y', 2), ('b', 'y', -.5)]],
                   inplist=[['a.u', 'b.u']], outlist=['sink.y'])
    net = ct.interconnect([a, b, sink], **options)
    assert isinstance(net, ct.StateSpace)
    for x, u in [(2, 3), (-1, -2)]:
        assert_allclose(net.dynamics(0, [x], [u]), [-2*x + 5.5*u])
        assert_allclose(net.output(0, [x], [u]), [3*x + 2.75*u])
    nonlinear = ct.nlsys(lambda t, x, u, p: [-x[0]**3 + u[0]],
                          lambda t, x, u, p: [x[0]**2 + u[0]],
                          states=1, inputs='u', outputs='y', name='sink')
    net = ct.interconnect([a, b, nonlinear], **options)
    for x, u in [(2, 3), (-1, -2)]:
        assert_allclose(net.dynamics(0, [x], [u]), [-x**3 + 5.5*u])
        assert_allclose(net.output(0, [x], [u]), [x*x + 5.5*u])
    with pytest.raises(ValueError):
        ct.interconnect([a, sink], connections=[['sink.u', 'a.missing']],
                        inplist=['a.u'], outlist=['sink.y'])
    vector = ct.ss([], [], [], np.eye(2), inputs=['v[0]', 'v[1]'], outputs=2, name='vector')
    with pytest.raises(ValueError):
        ct.interconnect([a, vector], connections=[['vector.v', 'a.y']],
                        inplist=['a.u'], outlist=['vector.y[0]'])


def test_automatic_signal_routing():
    a = ct.ss([], [], [], 2, inputs='drive', outputs='shared', name='a')
    b = ct.ss([], [], [], -3, inputs='drive', outputs='shared', name='b')
    c = ct.ss([], [], [], [[4, 7]], inputs=['shared', 'unconnected'], outputs='left', name='c')
    d = ct.ss([], [], [], -2, inputs='shared', outputs='right', name='d')
    net = ct.interconnect([a, b, c, d], inplist=['drive'],
                          outlist=['c.left', 'd.right'], ignore_inputs=['c.unconnected'])
    for u in (3, -2):
        assert_allclose(net.output(0, [], [u]), [-4*u, 2*u])


def test_unused_signal_reports():
    for options, wanted in [({}, {'input', 'output'}),
                            ({'check_unused': False}, set()),
                            ({'ignore_inputs': ['unit.spare']}, {'output'}),
                            ({'ignore_outputs': ['unit.extra']}, {'input'}),
                            ({'ignore_inputs': ['unit.spare'], 'ignore_outputs': ['unit.extra']}, set())]:
        unit = ct.ss([], [], [], [[2, 7], [3, 5]], inputs=['drive', 'spare'],
                     outputs=['used', 'extra'], name='unit')
        result = invoke(ct.interconnect, args=([unit],), kwargs=dict(
            connections=None, inplist=['unit.drive'], outlist=['unit.used'], **options))
        assert result.returned
        assert_allclose(result.value.output(0, [], [4]), [8])
        found = set()
        for record in result.warnings:
            assert issubclass(record.category, UserWarning)
            message = str(record.message)
            for kind, signal, separator in [('input', 'unit.spare', '='), ('output', 'unit.extra', ' : ')]:
                label = f'Unused {kind}(s) in InterconnectedSystem: '
                if message.startswith(label):
                    entries = message[len(label):].split('; ')
                    identities = {entry.split(separator, 1)[1] for entry in entries}
                    assert identities == {signal}
                    found.add(kind)
                    break
            else:
                pytest.fail(f'Unexpected warning: {message}')
        assert found == wanted


def test_summing_and_transfer_matrix_arithmetic():
    for dimension in (1, 3):
        options = {} if dimension == 1 else {'dimension': dimension}
        junction = ct.summing_junction(inputs=['a', '-b', 'c'], output='sum', **options)
        u = np.arange(1, 3*dimension + 1)
        assert_allclose(junction.output(0, [], u), u[:dimension] - u[dimension:2*dimension] + u[2*dimension:])
    points = np.array([.4j, 1.5j, 2 + .7j])
    g, h = ct.tf([2, 1], [1, 3]), ct.tf([3], [1, 2])
    gv = polynomial_reference([2, 1], [1, 3], points)
    hv = polynomial_reference([3], [1, 2], points)
    assert_allclose((g/h)(points), gv/hv)
    for power in (-2, 0, 3):
        assert_allclose((g**power)(points), gv**power)
    matrix = ct.combine_tf([[g, h], [2*h, -g]])
    expected = np.array([[gv, hv], [2*hv, -gv]])
    assert_allclose(matrix(points, squeeze=False), expected)
    channels = ct.split_tf(matrix)
    assert channels.shape == (2, 2)
    for i in range(2):
        for j in range(2):
            assert_allclose(channels[i, j](points), expected[i, j])


def test_sampled_frequency_connections():
    omega = np.array([.2, .8, 2.5])
    data = np.array([2-1j, 1+.4j, -.3+.2j])
    other = np.array([.3+.2j, -.1+.1j, .4-.2j])
    g, h = ct.frd(data, omega), ct.frd(other, omega)
    linear = ct.tf([2], [1, 3])
    lv = polynomial_reference([2], [1, 3], 1j*omega)
    for model, expected in [(ct.series(g, h), data*other),
                            (ct.parallel(g, h), data+other),
                            (ct.feedback(g, h), data/(1+data*other)),
                            (ct.series(g, linear), data*lv),
                            (ct.parallel(g, linear), data+lv),
                            (ct.feedback(g, linear), data/(1+data*lv)),
                            (ct.series(g, 2), 2*data),
                            (ct.parallel(g, 2), data+2),
                            (ct.feedback(g, 2), data/(1+2*data))]:
        assert_array_equal(model.omega, omega)
        assert_allclose(model.frdata, expected.reshape(1, 1, -1))
    incompatible = ct.frd(other, [.3, .9, 3.])
    for operation in (ct.series, ct.parallel, ct.feedback):
        with pytest.raises(NotImplementedError):
            operation(g, incompatible)


def test_nonlinear_algebraic_loop_simulation():
    for loop in (False, True):
        result = invoke(simulate_square_network, args=(loop,),
                        expected_exceptions=(RuntimeError,))
        if loop:
            assert not result.returned
            assert isinstance(result.exception, RuntimeError)
        else:
            assert result.returned
            assert_allclose(result.value.outputs, [[2, 5, 10]])
