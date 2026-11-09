# feature: F08
"""Acceptance tests for numerical and plotted frequency-domain analysis."""

import numpy as np
import pytest
import velunex as ct
from numpy.testing import assert_allclose, assert_array_equal
from _helpers import headless_figures, invoke, user_warnings
from F01_helpers import state_space_reference, polynomial_reference
from F08_helpers import assert_frequency_data, assert_phase_coordinates


def test_frequency_response_grids_and_timebases():
    b = [[1, 2], [-1, 3]]
    c = [[2, 1], [1, -2]]
    d = [[.2, .3], [-.4, .1]]
    for a, dt in [([[-2, 0], [0, -4]], 0), ([[.2, 0], [0, .6]], .25)]:
        model = ct.ss(a, b, c, d, dt=dt)
        for options in [dict(omega=[3, .1, 1, .5]),
                        dict(omega_limits=[.2, 4], omega_num=17), {}]:
            r = ct.frequency_response(model, squeeze=False, **options)
            w = r.omega
            assert len(w) > 1 and np.all(np.diff(w) > 0)
            if 'omega' in options:
                assert_array_equal(w, sorted(options['omega']))
            if 'omega_num' in options:
                assert len(w) == options['omega_num']
                assert_allclose(w[[0, -1]], options['omega_limits'])
            points = 1j*w if dt == 0 else np.exp(1j*w*dt)
            assert_frequency_data(r, w, state_space_reference(a, b, c, d, points))
        if dt:
            # Only the grid that passes the Nyquist frequency is notified.
            for scale, notified in [(.9, False), (1.1, True)]:
                w = np.array([1, scale*np.pi/dt])
                result = invoke(ct.frequency_response, (model, w), {'squeeze': False})
                assert result.returned
                assert bool(user_warnings(result, UserWarning)) == notified
                assert_frequency_data(result.value, w, state_space_reference(
                    a, b, c, d, np.exp(1j*w*dt)))


def test_bode_and_nichols_values_units_and_identity():
    w = np.array([.1, .4, 1, 3, 10])
    full = ct.ss([[-2]], [[1, 3]], [[2], [5]], [[0, 0], [0, 0]],
                 inputs=['force', 'drive'], outputs=['speed', 'position'])
    systems = [full['position', 'drive'], ct.tf([3], [1, 4], name='other')]
    expected = [15/(2+1j*w), 3/(4+1j*w)]
    with headless_figures() as plt:
        for db, deg, hz in [(False, False, False), (True, True, True)]:
            plt.figure()
            p = ct.bode_plot(systems, w, dB=db, deg=deg, Hz=hz,
                             label=['selected', 'other'])
            for index, value in enumerate(expected):
                for row in range(2):
                    line = p.lines[row, 0][index]
                    assert line.get_label() == ['selected', 'other'][index]
                    assert_allclose(line.get_xdata(), w/(2*np.pi) if hz else w)
                assert_allclose(p.lines[0, 0][index].get_ydata(),
                                20*np.log10(abs(value)) if db else abs(value))
                assert_phase_coordinates(p.lines[1, 0][index].get_ydata(), value, deg)
            assert p.axes[0, 0].get_ylabel() == ('Magnitude [dB]' if db else 'Magnitude')
            assert p.axes[1, 0].get_ylabel() == ('Phase [deg]' if deg else 'Phase [rad]')
            assert p.axes[1, 0].get_xlabel() == ('Frequency [Hz]' if hz else 'Frequency [rad/s]')
        plt.figure()
        p = ct.nichols_plot(systems, w, grid=False, label=['selected', 'other'])
        lines = [line for group in p.lines.flat for line in group]
        for line, value, label in zip(lines, expected, ['selected', 'other']):
            assert line.get_label() == label
            assert_phase_coordinates(line.get_xdata(), value, degrees=True)
            assert_allclose(line.get_ydata(), 20*np.log10(abs(value)))
        assert len(lines) == 2
        assert p.axes[0, 0].get_xlabel() == 'Phase [deg]'
        assert p.axes[0, 0].get_ylabel() == 'Magnitude [dB]'


def test_singular_value_response_and_plot():
    a, b = [[-1, 0], [0, -3]], [[1, 2], [2, -1]]
    c, d = [[2, 1], [1, -1], [3, 2]], [[.1, 0], [0, .2], [.3, -.1]]
    model = ct.ss(a, b, c, d)
    w = np.array([.05, .2, 1, 4, 20])
    matrix = state_space_reference(a, b, c, d, 1j*w)
    sigma = np.linalg.svd(matrix.transpose(2, 0, 1), compute_uv=False).T
    response = ct.singular_values_response(model, w)
    assert_allclose(response.omega, w)
    assert_allclose(response.frdata[:, 0, :], sigma, atol=1e-9)
    with headless_figures() as plt:
        for db, hz in [(False, False), (True, True)]:
            plt.figure()
            p = ct.singular_values_plot(response, dB=db, Hz=hz)
            lines = [line for group in p.lines.flat for line in group]
            assert len(lines) == len(sigma)
            for line, values in zip(lines, sigma):
                assert_allclose(line.get_xdata(), w/(2*np.pi) if hz else w)
                assert_allclose(line.get_ydata(), 20*np.log10(values) if db else values)


def test_nyquist_contours_counts_and_warnings():
    w = np.r_[0, np.geomspace(.001, 1e5, 1500)]
    # Closed-loop minus open-loop unstable pole counts: 0, -1, +1.
    with headless_figures() as plt:
        for numerator, denominator, count in [([2], [1, 1], 0),
                ([2], [1, -1], -1), ([-3], [1, 1], 1)]:
            model = ct.tf(numerator, denominator)
            # A contour supporting the count gives an unqualified conclusion.
            call = invoke(ct.nyquist_response, (model, w))
            assert call.returned and not user_warnings(call, UserWarning)
            r = call.value
            assert r.count == count
            assert_allclose(r.contour, 1j*w)
            expected = polynomial_reference(numerator, denominator, r.contour)
            assert_allclose(r.response, expected)
            plt.figure()
            p = ct.nyquist_plot(r, max_curve_magnitude=100, arrows=False)
            for slot, values in [(0, expected), (2, expected.conjugate())]:
                line = p.lines[0, slot][0]
                assert not np.any(np.ma.getmaskarray(line.get_xdata()))
                assert not np.any(np.ma.getmaskarray(line.get_ydata()))
                assert_allclose(line.get_xdata(), values.real)
                assert_allclose(line.get_ydata(), values.imag)
        r = ct.nyquist_response(ct.tf([1], [1, 0]), w)
        assert r.count == 0
        assert np.any(r.contour.real > 0)
        assert np.all(np.isfinite(r.response))
        assert_allclose(r.response, 1/r.contour)
        bad = invoke(ct.nyquist_response, (ct.tf([2], [1, -1]), np.linspace(1, 2, 30)))
        assert bad.returned
        assert user_warnings(bad, UserWarning)
        assert_allclose(bad.value.response, 2/(bad.value.contour-1))


def test_feedback_sensitivity_channels_and_plot():
    w = np.array([.1, .3, 1, 4, 15])
    plant, controller = ct.tf([2], [1, 3]), ct.tf([3, 1], [1, 2])
    pv, cv = 2/(1j*w+3), (3j*w+1)/(1j*w+2)
    sensitivity = 1/(1+pv*cv)
    expected = np.array([[pv*cv*sensitivity, pv*sensitivity],
                         [cv*sensitivity, sensitivity]])
    r = ct.gangof4_response(plant, controller, w)
    assert_frequency_data(r, w, expected)
    with headless_figures():
        p = ct.gangof4_plot(plant, controller, omega=w, dB=False, Hz=False)
        for i in range(2):
            for j in range(2):
                assert_allclose(p.lines[i, j][0].get_xdata(), w)
                assert_allclose(p.lines[i, j][0].get_ydata(), abs(expected[i, j]))
    multi = ct.ss([[-1]], [[1, 2]], [[1]], [[0, 0]])
    for args in [(multi, controller), (plant, multi)]:
        with pytest.raises(ct.VelunexMIMONotImplemented):
            ct.gangof4_response(*args, omega=w)


def test_measured_frequency_data_names_plots_and_rejection():
    w = np.array([.2, .7, 2, 9])
    data = np.array([[[1-2j, 2-1j, .5+.2j, .3-.4j],
                      [3-1j, 1-3j, 2+.4j, .7-.1j]],
                     [[2-4j, 3-2j, 1+.3j, .6-.2j],
                      [4-2j, 2-5j, 3+.6j, .9-.3j]]])
    r = ct.frd(data, w, inputs=['force', 'drive'], outputs=['speed', 'position'],
               name='measured', squeeze=False)
    assert_frequency_data(r, w, data)
    assert_allclose(r.eval(w, squeeze=False), data)
    assert r.input_labels == ['force', 'drive']
    assert r.output_labels == ['speed', 'position']
    with headless_figures() as plt:
        p = ct.bode_plot(r, dB=False, deg=False, Hz=False)
        for i in range(2):
            for j in range(2):
                assert_allclose(p.lines[2*i, j][0].get_xdata(), w)
                assert_allclose(p.lines[2*i, j][0].get_ydata(), abs(data[i, j]))
                assert_phase_coordinates(p.lines[2*i+1, j][0].get_ydata(), data[i, j])
                assert p.axes[0, j].get_title() == 'From ' + r.input_labels[j]
            assert 'To ' + r.output_labels[i] in {text.get_text().strip() for text in p.figure.texts}
        selected = r['position', 'force']
        assert_allclose(selected.frdata, data[1:2, 0:1])
        plt.figure()
        p = ct.nichols_plot(selected, grid=False)
        line = p.lines.flat[0][0]
        assert_phase_coordinates(line.get_xdata(), data[1, 0], degrees=True)
        assert_allclose(line.get_ydata(), 20*np.log10(abs(data[1, 0])))
        for entry in (ct.nichols_plot, ct.nyquist_plot):
            with pytest.raises(NotImplementedError):
                entry(r)


def test_discrete_nyquist_contours_and_boundary_poles():
    for period in (.2, .37):
        omega = np.linspace(0., np.pi/period, 2001)
        circle = np.exp(1j*omega*period)
        for pole, gain in ((.2, .4), (1.2, .5), (.2, 1.5)):
            call = invoke(ct.nyquist_response,
                          (ct.tf([gain], [1., -pole], period), omega))
            assert call.returned and not user_warnings(call, UserWarning)
            result = call.value
            assert_allclose(result.contour, circle, atol=1e-10)
            assert_allclose(result.response, gain/(result.contour-pole))
            # The scalar closed-loop pole is pole-gain under unity feedback.
            assert result.count == int(abs(pole-gain) > 1)-int(abs(pole) > 1)
        pole, gain = 1., .5
        call = invoke(ct.nyquist_response,
                      (ct.tf([gain], [1., -pole], period), omega))
        assert call.returned and not user_warnings(call, UserWarning)
        result = call.value
        assert np.all(np.isfinite(result.contour))
        assert np.all(np.isfinite(result.response))
        assert np.all(abs(result.contour-pole) > 0)
        assert np.any(abs(abs(result.contour)-1) > 1e-10)
        assert_allclose(result.response, gain/(result.contour-pole))
        # Either side of the boundary is valid; its pole inclusion determines
        # the count. Do not prescribe the indentation radius or vertex count.
        start = result.contour[0]
        assert abs(start.imag) < 1e-8 and start.real > 0
        assert result.count == -int(abs(start) < 1)
        assert_allclose(result.contour[-1], circle[-1], atol=1e-10)
