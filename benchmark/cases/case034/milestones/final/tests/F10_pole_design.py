# feature: F10
"""Acceptance checks for pole analysis and interactive PI design."""
import numpy as np
import pytest
import velunex as ct
from numpy.testing import assert_allclose
from _helpers import headless_figures, isolated_mapping
from F01_helpers import assert_unordered_roots
from F10_helpers import (complex_coordinates, design_axis, release_at,
                         assert_selected_gain, assert_design_response,
                         assert_step_display)


def test_poles_zeros_damping_and_maps():
    systems = [ct.tf([2, 6], [1, 4, 13], name='oscillator'),
               ct.ss(np.diag([-2., -5.]), np.eye(2), np.diag([3., 4.]),
                     np.eye(2), name='square')]
    roots = [np.array([-2+3j, -2-3j]), np.array([-2., -5.])]
    zeros = [np.array([-3.]), np.array([-5., -9.])]
    for system, poles, zero in zip(systems, roots, zeros):
        assert_unordered_roots(ct.poles(system), poles)
        assert_unordered_roots(ct.zeros(system), zero)
        wn, damping, returned = ct.damp(system, doprint=False)
        assert_unordered_roots(returned, poles)
        assert_allclose(wn, abs(returned))
        assert_allclose(damping, -returned.real/abs(returned))
    for dt in (.2, True):
        poles = np.array([1., -.4, .5+.3j, .5-.3j])
        system = ct.tf([1], np.poly(poles).real, dt)
        wn, damping, returned = ct.damp(system, doprint=False)
        assert_unordered_roots(returned, poles)
        equivalent = np.log(returned.astype(complex))/(1 if dt is True else dt)
        nonzero = abs(returned-1) > 1e-10
        assert_allclose(wn, abs(equivalent), atol=1e-12)
        assert_allclose(damping[nonzero], -equivalent[nonzero].real/abs(equivalent[nonzero]))
        # Use an exact unit pole separately to avoid numerical polynomial root noise.
        _, d0, _ = ct.damp(ct.tf([1], [1, -1], dt), doprint=False)
        assert np.isnan(d0[0])
    _, d0, _ = ct.damp(ct.tf([1], [1, 0]), doprint=False)
    assert np.isnan(d0[0])
    data = ct.pole_zero_map(systems)
    with headless_figures():
        plot = ct.pole_zero_plot(data, grid=False, label=['oscillator', 'square'])
        for i in range(2):
            assert_unordered_roots(data[i].poles, roots[i])
            assert_unordered_roots(data[i].zeros, zeros[i])
            assert_unordered_roots(complex_coordinates(plot.lines[i, 0]), roots[i])
            assert_unordered_roots(complex_coordinates(plot.lines[i, 1]), zeros[i])
            assert plot.lines[i, 0][0].get_label() == ['oscillator', 'square'][i]


def test_root_locus_data_plots_and_rejection():
    system = ct.tf([1, 3], [1, 5, 4])
    with headless_figures() as plt:
        for gains in ([0, .4, 2, 7], None):
            data = ct.root_locus_map(system, gains=gains)
            if gains is not None:
                assert_allclose(data.gains, gains)
            else:
                assert len(np.unique(data.gains)) > 1
            assert data.loci.shape == (len(data.gains), 2)
            assert_unordered_roots(data.poles, np.array([-1., -4.]))
            assert_unordered_roots(data.zeros, np.array([-3.]))
            for gain, row in zip(data.gains, data.loci):
                assert_unordered_roots(row, np.roots([1, 5+gain, 4+3*gain]))
            plt.figure()
            plot = ct.root_locus_plot(data, grid=False)
            assert_unordered_roots(complex_coordinates(plot.lines[0, 0]), data.poles)
            assert_unordered_roots(complex_coordinates(plot.lines[0, 1]), data.zeros)
            curves = plot.lines[0, 2]
            assert len(curves) == 2
            plotted = np.array([line.get_xdata()+1j*line.get_ydata() for line in curves]).T
            assert plotted.shape == data.loci.shape
            for row, expected in zip(plotted, data.loci):
                assert_unordered_roots(row, expected)
        multi = ct.ss([[-2]], [[1, 2]], [[1]], [[0, 0]])
        for entry in (ct.root_locus_map, ct.root_locus_plot):
            with pytest.raises(ct.VelunexMIMONotImplemented):
                entry(multi)


def test_canvas_gain_selection_and_linked_responses():
    system = ct.tf([2], [1, 3])
    with headless_figures() as plt:
        plot = ct.root_locus_plot(system, grid=False, interactive=True, xlim=(-10, 0), ylim=(-2, 2))
        axis = plot.axes[0, 0]
        for point in (-5., -8.):
            clicked = release_at(axis, complex(point))
            gain = (-clicked.real-3)/2
            assert_selected_gain(axis, [axis.get_title()], gain, [-3-2*gain])
        plt.close('all')
        for two_channel in (False, True):
            # G11=2/(s+3), G12=6/(s+3), G21=5/(s+3), G22=15/(s+3).
            model = ct.ss([[-3]], [[1, 3]], [[2], [5]], np.zeros((2, 2))) if two_channel else system
            ct.sisotool(model, initial_gain=.5, dB=False, deg=True, Hz=False,
                        margins_bode=False, xlim_rlocus=(-10, 0), ylim_rlocus=(-2, 2))
            figure = plt.gcf()
            assert_design_response(figure, lambda w: 1/(3+1j*w),
                                   [15] if two_channel else [1], [1, 4])
            axis = design_axis(figure, 'Root locus')
            for point in (() if two_channel else (-5., -8.)):
                clicked = release_at(axis, complex(point))
                gain = (-clicked.real-3)/2
                assert_selected_gain(axis, [t.get_text() for t in figure.texts], gain, [-3-2*gain])
                assert_design_response(figure, lambda w: 2*gain/(3+1j*w),
                                       [15] if two_channel else [2*gain], [1, 3+2*gain])
            plt.close('all')
            if two_channel:
                ct.sisotool(model, initial_gain=2, dB=False, deg=True, Hz=False,
                            margins_bode=False)
                assert_design_response(plt.gcf(), lambda w: 4/(3+1j*w), [15], [1, 7])
                plt.close('all')
        for inputs, outputs in ((2, 1), (1, 2), (3, 3)):
            invalid = ct.ss([[-1]], np.ones((1, inputs)), np.ones((outputs, 1)),
                            np.zeros((outputs, inputs)))
            with pytest.raises(ct.VelunexMIMONotImplemented):
                ct.sisotool(invalid)


def test_nominal_pi_models_and_routing():
    points = np.array([.4+.7j, 1.3+2j, 2.1+.3j])
    for dt, term, channel, two_inputs, ff in [
            (0, 'P', 'r', False, .4), (0, 'I', 'd', False, 0),
            (0, 'I', 'd', True, .7), (.2, 'I', 'r', False, .3),
            (.2, 'P', 'd', True, 0)]:
        a = -2 if dt == 0 else .4
        plant = ct.ss([[a]], [[2, 5]] if two_inputs else [[2]], [[1]],
                      [[0, 0]] if two_inputs else [[0]], dt)
        model = ct.rootlocus_pid_designer(plant, gain=term, input_signal=channel,
                    Kp0=.7, Ki0=.3, C_ff=ff, deltaK=.6, plot=False)
        p = 2/(points-a)
        integral = 1/points if dt == 0 else dt/2*(points+1)/(points-1)
        controller = .7+.3*integral
        numerator = p*(controller+ff) if channel == 'r' else (5 if two_inputs else 2)/(points-a)
        assert_allclose(model(points), numerator/(1+p*controller), rtol=1e-7, atol=1e-9)
    plant = ct.tf([2], [1, 2])
    default = ct.rootlocus_pid_designer(plant, plot=False)
    assert_allclose(default(points), np.zeros(len(points)), atol=1e-12)
    disturbance = ct.rootlocus_pid_designer(plant, input_signal='d', plot=False)
    assert_allclose(disturbance(points), 2/(points+2))


def test_pi_display_perturbation_and_nominal_return():
    points = np.array([.5+.8j, 1.1+1.7j])
    plant = ct.tf([2], [1, 2])
    with headless_figures() as plt, isolated_mapping(ct.config.defaults,
            {'freqplot.dB': False, 'freqplot.deg': True, 'freqplot.Hz': False}):
        for options, kp, ki, delta, term in [({}, 0, 0, .001, 'P'),
                ({'Kp0': .6, 'Ki0': .2, 'deltaK': .8}, .6, .2, .8, 'P'),
                ({'gain': 'I', 'Kp0': .6, 'Ki0': .2, 'deltaK': .4}, .6, .2, .4, 'I')]:
            returned = ct.rootlocus_pid_designer(plant, **options)
            controller = kp+ki/points
            assert_allclose(returned(points), 2*controller/(points+2+2*controller), atol=1e-9)
            varied_p = kp+(delta if term == 'P' else 0)
            varied_i = ki+(delta if term == 'I' else 0)
            assert_step_display(plt.gcf(), [2*varied_p, 2*varied_i],
                                [1, 2+2*varied_p, 2*varied_i])
            axis = design_axis(plt.gcf(), 'Root locus')
            # The initial selection is observable through the marked locus poles.
            from _helpers import labeled_artists
            markers = labeled_artists(axis, '_gain_point')
            assert markers
            # Zero integral action has no integral pole in the minimal loop.
            marked = complex_coordinates(markers)
            wanted = (np.roots([1, 2+2*varied_p, 2*varied_i]) if varied_i
                      else np.array([-2-2*varied_p]))
            for root in wanted:
                assert np.min(abs(marked-root)) < 1e-6
            plt.close('all')
