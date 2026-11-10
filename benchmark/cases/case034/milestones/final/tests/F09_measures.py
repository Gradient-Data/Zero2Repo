# feature: F09
"""Acceptance coverage for gain, margins, norms, and passivity."""
import numpy as np
import pytest
import velunex as ct
from numpy.testing import assert_allclose
from _helpers import invoke, user_warnings
from F01_helpers import state_space_reference
from F09_helpers import assert_margin_pairs, disk_geometry, two_channel_scaled_gain


def test_gain_and_first_bandwidth():
    for dt, a in [(0, -2), (.25, .5)]:
        b, c, d = [[1, 2]], [[3], [-1]], [[.2, .1], [.3, -.4]]
        model = ct.ss([[a]], b, c, d, dt)
        assert_allclose(ct.dcgain(model), state_space_reference(
            [[a]], b, c, d, [0 if dt == 0 else 1])[..., 0])
    model = ct.tf([6], [1, 2])
    assert_allclose(ct.dcgain(model), 3)
    assert_allclose(ct.bandwidth(model), 2*np.sqrt(10**.3-1), rtol=1e-6)
    assert_allclose(ct.bandwidth(model, dbdrop=-6), 2*np.sqrt(10**.6-1), rtol=1e-6)
    # A notch crosses the threshold twice; bandwidth must select the first.
    notch = ct.tf([1, .04, 1], [1, .4, 1])
    assert_allclose(ct.bandwidth(notch), .8210386729072677, rtol=1e-6)
    assert np.isposinf(ct.bandwidth(ct.tf([2], [1])))
    assert np.isnan(ct.bandwidth(ct.tf([1], [1, 0])))
    for drop in (0, 3):
        with pytest.raises(ValueError):
            ct.bandwidth(model, dbdrop=drop)
    with pytest.raises(TypeError):
        ct.bandwidth(ct.ss([[-1]], [[1, 2]], [[1]], [[0, 0]]))


def test_classical_all_limiting_and_sampled_margins():
    s = ct.tf('s')
    model = 8.75*(4*s*s+.4*s+1)/((100*s+1)*(s*s+.22*s+1)*(s*s/100+.008*s+1))
    # Public reference run; paired values are insensitive to root enumeration.
    expected = ([2.271585870321], [97.593979137140, -157.784483214378, 134.732573653741],
                [1.038104066853, .559084939016], [10.005276366550],
                [.085045154992, .937253347097, 1.091918891517], [.406388516470, 9.991844224866])
    assert_margin_pairs(ct.stability_margins(model, returnall=True), expected)
    limiting = [expected[0][0], expected[1][0], expected[2][1],
                expected[3][0], expected[4][0], expected[5][1]]
    assert_allclose(ct.stability_margins(model), limiting, rtol=2e-5)
    for interval, wanted in [((.01, 100), expected), ((.5, 2),
            ([], expected[1][1:], [], [], expected[4][1:], []))]:
        response = ct.frd(model, np.geomspace(*interval, 5000))
        # The documents require a continuous interpolation that reproduces the
        # samples (affine between samples is allowed), not a particular order.
        # Linear interpolation of these samples is within 5.31e-4 of the exact
        # margins; reading crossings off the nearest sample is 2.2e-3 away.
        assert_margin_pairs(ct.stability_margins(response, returnall=True), wanted, rtol=6e-4)
    # The closest logarithmic gain factor is the second crossing, not the first.
    high_order = 2000/(s+1)**7
    full = ([.00103753203, 18.508613469779], [48.122279519110], [.644025231380],
            [.481574618808, 4.381286267535], [2.788021990809], [3.033639007562])
    assert_margin_pairs(ct.stability_margins(high_order, returnall=True), full)
    assert_allclose(ct.stability_margins(high_order),
                    [full[0][1], full[1][0], full[2][0], full[3][1], full[4][0], full[5][0]], rtol=2e-5)
    missing = ct.tf([.5], [1, 1])
    assert_margin_pairs(ct.stability_margins(missing, returnall=True), ([],)*6)
    result = ct.stability_margins(missing)
    assert np.all(np.isposinf(result[:3]))
    assert np.all(np.isnan(result[3:]))


def test_signed_real_axis_crossings():
    model = ct.tf([2], [1, 3, 3, 1])
    frequencies, gains = ct.phase_crossover_frequencies(model)
    order = np.argsort(frequencies)
    assert_allclose(np.asarray(frequencies)[order], [0, np.sqrt(3)], atol=1e-8)
    assert_allclose(np.asarray(gains)[order], [2, -.25], atol=1e-8)
    multi = ct.tf([[[1], [2]]], [[[1, 1], [1, 2]]])
    with pytest.raises(ct.VelunexMIMONotImplemented):
        ct.phase_crossover_frequencies(multi)


def test_disk_margins_geometry_and_coupling():
    w = np.array([2., 3., 5.])
    models = [ct.ss([[-1]], [[1]], [[1]], [[-.7]]),
              ct.ss(-np.eye(2), np.eye(2), [[.1, .02], [.06, .1]], [[-.6, .1], [.3, -.5]])]
    for model in models:
        loop = state_space_reference(model.A, model.B, model.C, model.D, 1j*w)
        for skew in (0., .3, -.4):
            expected = []
            for matrix in loop.transpose(2, 0, 1):
                identity = np.eye(len(matrix))
                sensitivity = np.linalg.inv(identity+matrix)+(skew-1)*identity/2
                gain = abs(sensitivity[0, 0]) if len(matrix) == 1 else two_channel_scaled_gain(sensitivity)
                alpha = 1/gain
                expected.append((alpha, *disk_geometry(alpha, skew)))
            expected = np.asarray(expected).T
            assert_allclose(ct.disk_margins(model, w, skew=skew, returnall=True), expected, rtol=2e-5, atol=1e-7)
            assert_allclose(ct.disk_margins(model, w, skew=skew), expected.min(axis=1), rtol=2e-5)
            if skew == 0:
                assert_allclose(ct.disk_margins(model, w), expected.min(axis=1), rtol=2e-5)
    with pytest.raises(ValueError):
        ct.disk_margins(ct.ss([[-1]], [[1, 2]], [[1]], [[0, 0]]), w)


def test_finite_energy_and_peak_norms():
    # The impulse matrix is an outer product times an exponential/geometric sequence.
    for dt, a, energy, peak in [(0, -1, 5., np.sqrt(50)),
                                (.2, .5, np.sqrt(50/.75), 2*np.sqrt(50)),
                                (.7, .5, np.sqrt(50/.75), 2*np.sqrt(50))]:
        model = ct.ss([[a]], [[1, 2]], [[1], [3]], np.zeros((2, 2)), dt)
        for order, value in [(2, energy), ('inf', peak)]:
            # Finite norms of stable systems carry no divergence notification.
            result = invoke(ct.system_norm, (model, order))
            assert result.returned and not user_warnings(result, UserWarning)
            assert_allclose(result.value, value, rtol=2e-5)
    resonant = ct.tf([4], [1, .4, 4])
    assert_allclose(ct.system_norm(resonant, 'inf'), 5.02518907629606, rtol=2e-5)
    # A discrete direct term contributes one unit-sample coefficient.
    assert_allclose(ct.system_norm(ct.ss([[.5]], [[1]], [[2]], [[3]], .2), 2), np.sqrt(9+4/.75), rtol=2e-5)
    for model, peak in [(ct.tf([3], [1, -2]), 1.5), (ct.tf([2], [1, -1.5], .2), 4.)]:
        assert_allclose(ct.system_norm(model, 'inf'), peak, rtol=2e-5)


def test_infinite_norms_warnings_and_unsupported_order():
    cases = [(ct.tf([1], [1, -1]), 2), (ct.tf([1], [1, -1.2], .2), 2),
             (ct.tf([1, 2], [1, 1]), 2)]
    for model in [ct.tf([1], [1, 0]), ct.tf([1], [1, -1], .2)]:
        cases.extend([(model, 2), (model, 'inf')])
    for model, order in cases:
        result = invoke(ct.system_norm, (model, order))
        assert result.returned and np.isposinf(result.value)
        assert user_warnings(result, UserWarning)
    with pytest.raises(ct.VelunexArgument):
        ct.system_norm(ct.tf([1], [1, 1]), 3)


def test_passivity_supply_bound():
    # Positive-real scalar channels admit quadratic storage; sign reversal
    # preserves poles but makes a constant-input supply negative.
    for dt, a, direct, rho in [(0, -1, 1, .5), (.2, .5, 2, .25)]:
        model = ct.ss([[a]], [[1]], [[1]], [[direct]], dt)
        assert ct.ispassive(model)
        assert not ct.ispassive(-model)
        assert ct.ispassive(model, ifp_index=.2, ofp_index=.2)
        assert ct.ispassive(model, ifp_index=.8, ofp_index=.9*rho)
        assert not ct.ispassive(model, ifp_index=.2, ofp_index=rho+.1)
        # A square coupled model, orthogonally equivalent to positive channels.
        coupled = ct.ss(a*np.eye(2), np.eye(2), [[1, .2], [.2, 1]], direct*np.eye(2), dt)
        assert ct.ispassive(coupled)
        assert not ct.ispassive(-coupled)


def test_limiting_passivity_indices_and_rejections():
    # For these scalar models the extrema of Re(G) and Re(1/G)
    # occur at zero or infinite/Nyquist frequency and give finite limits.
    for dt, a, direct, nu, rho in [(0, -1, 1, 1., .5), (.2, .5, 2, 4/3, .25)]:
        model = ct.ss([[a]], [[1]], [[1]], [[direct]], dt)
        assert_allclose(ct.get_input_ff_index(model), nu, atol=2e-5)
        assert_allclose(ct.get_output_fb_index(model), rho, atol=2e-5)
        for index, limit in [('ifp_index', nu), ('ofp_index', rho)]:
            assert ct.ispassive(model, **{index: limit-.02})
            assert not ct.ispassive(model, **{index: limit+.02})
    with pytest.raises(ct.VelunexArgument):
        ct.solve_passivity_LMI(model, rho=None, nu=None)
    multi = ct.ss([[-1]], [[1, 2]], [[1]], [[0, 0]])
    with pytest.raises(ct.VelunexDimension):
        ct.solve_passivity_LMI(multi, rho=0, nu=0)
