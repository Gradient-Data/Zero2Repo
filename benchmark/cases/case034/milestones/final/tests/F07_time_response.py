# feature: F07
"""Acceptance of simulated histories and their public summaries."""

import numpy as np
import pytest
import velunex as ct
from numpy.testing import assert_allclose, assert_array_equal
from _helpers import headless_figures, invoke, user_warnings
from F03_helpers import parameter_update, parameter_output


def test_standard_linear_excitations():
    t = np.linspace(0, 2, 21)
    model = ct.ss([[-2]], [[1, 3]], [[1], [-2]], np.zeros((2, 2)))
    decay = np.exp(-2*t)
    initial = ct.initial_response(model, t, X0=2, squeeze=False)
    assert_allclose(initial.states, [2*decay], atol=1e-9)
    assert_allclose(initial.outputs, [2*decay, -4*decay], atol=1e-9)
    for entry, wave in [(ct.step_response, (1-decay)/2),
                        (ct.impulse_response, decay)]:
        response = entry(model, t, squeeze=False)
        assert_array_equal(response.time, t)
        for j, gain in enumerate([1, 3]):
            assert_allclose(response.states[:, j], [gain*wave], atol=1e-9)
            assert_allclose(response.outputs[:, j], [gain*wave, -2*gain*wave], atol=1e-9)
        selected = entry(model, t, input=1, output=1, squeeze=False)
        assert_allclose(selected.outputs, [[-6*wave]], atol=1e-9)
    forced = ct.forced_response(model, t, np.array([t, 2*t]), squeeze=False)
    x = 7*(t/2-(1-decay)/4)
    assert_allclose(forced.states, [x], atol=1e-9)
    assert_allclose(forced.outputs, [x, -2*x], atol=1e-9)
    discrete = ct.ss([[.5]], [[2]], [[3]], [[1]], dt=.25)
    impulse = ct.impulse_response(discrete, np.arange(5)*.25, squeeze=False)
    assert_allclose(np.asarray(impulse.inputs, dtype=float), [[[4, 0, 0, 0, 0]]])
    assert_allclose(impulse.states, [[[0, 8, 4, 2, 1]]])
    assert_allclose(impulse.outputs, [[[4, 24, 12, 6, 3]]])


def test_continuous_interpolation_and_invalid_dimensions():
    model = ct.ss([[0]], [[1]], [[2]], [[3]])
    t = np.linspace(0, 2, 5)
    r = ct.forced_response(model, t, t, X0=4, squeeze=False)
    assert_array_equal(r.time, t)
    assert_allclose(r.inputs, [t])
    assert_allclose(r.states, [4+t*t/2], atol=1e-9)
    assert_allclose(r.outputs, [8+t*t+3*t], atol=1e-9)
    for times, inputs, initial in [([0, .2, 1], [0, 1, 2], 0),
                                    (t, [1, 2], 0),
                                    (t, np.zeros((2, 5)), 0),
                                    (t, t, [1, 2])]:
        with pytest.raises(ValueError):
            ct.forced_response(model, times, inputs, X0=initial)


def test_discrete_sampling_and_unspecified_period():
    model = ct.ss([[1]], [[1]], [[2]], [[1]], dt=.5)
    for interpolate, t, u, x in [
            (False, [0, 1, 2], [0, 2, 4], [3, 4, 9]),
            (True, [0, .5, 1, 1.5, 2], [0, 1, 2, 3, 4], [3, 3, 4, 6, 9])]:
        r = ct.forced_response(model, [0, 1, 2], [0, 2, 4], X0=3,
                               interpolate=interpolate, squeeze=False)
        assert_allclose(r.time, t)
        assert_allclose(r.inputs, [u])
        assert_allclose(r.states, [x])
        assert_allclose(r.outputs, [2*np.array(x)+u])
    for t in ([0, .25, .5], [0, .75, 1.5]):
        with pytest.raises(ValueError):
            ct.forced_response(model, t, [0, 2, 4])
    unspecified = ct.ss([[1]], [[1]], [[2]], [[1]], dt=True)
    for supplied, expected in [(None, [0, 1, 2]), ([0, .3, .6], [0, .3, .6])]:
        r = ct.forced_response(unspecified, supplied, [1, 3, 2], X0=2, squeeze=False)
        assert_allclose(r.time, expected)
        assert_allclose(r.inputs, [[1, 3, 2]])
        assert_allclose(r.states, [[2, 3, 6]])
        assert_allclose(r.outputs, [[5, 9, 14]])


def test_nonlinear_and_connected_simulation():
    # A ramp squared in the derivative makes a linearized substitute wrong.
    square = ct.nlsys(lambda t, x, u, p: [p['gain']*u[0]**2],
                      lambda t, x, u, p: [x[0]**2+u[0]],
                      states=1, inputs='u', outputs='y', params={'gain': 1}, name='plant')
    net = ct.interconnect([square], connections=False,
                          inplist=['plant.u'], outlist=['plant.y'])
    times = np.linspace(0, 2, 9)
    for system in (square, net):
        for gain in (1, 3):
            r = ct.input_output_response(system, [0, 1, 2], [0, 1, 2], X0=1,
                    params={'gain': gain}, t_eval=times, squeeze=False,
                    solve_ivp_kwargs={'rtol': 1e-9, 'atol': 1e-11})
            x = 1+gain*times**3/3
            assert_allclose(r.time, times)
            assert_allclose(r.inputs, [times])
            assert_allclose(r.states, [x], rtol=1e-6, atol=1e-8)
            assert_allclose(r.outputs, [x*x+times], rtol=1e-6, atol=1e-8)
    discrete = ct.nlsys(parameter_update, parameter_output, states=1, inputs=1,
            outputs=1, dt=.2, params={'a': 2, 'b': 1, 'c': 3, 'd': -1, 'bias': 0})
    r = ct.input_output_response(discrete, np.array([0, .2, .4, .6]), [1, 2, 3, 4], X0=1,
                                squeeze=False)
    assert_allclose(r.time, [0, .2, .4, .6])
    assert_allclose(r.inputs, [[1, 2, 3, 4]])
    assert_allclose(r.states, [[1, 3, 8, 19]])
    assert_allclose(r.outputs, [[2, 7, 21, 53]])


def test_simulation_failure_reporting():
    # x'=x^2 has a finite-time singularity at t=1 for x(0)=1.
    model = ct.nlsys(lambda t, x, u, p: [x[0]**2], states=1, inputs=0)
    good = ct.input_output_response(model, np.linspace(0, .5, 6), X0=1,
                    solve_ivp_kwargs={'rtol': 1e-8, 'atol': 1e-10})
    assert good.success
    assert_allclose(good.states, [1/(1-good.time)], rtol=1e-6)
    with pytest.raises(RuntimeError):
        ct.input_output_response(model, np.linspace(0, 2, 21), X0=1)
    failed = ct.input_output_response(model, np.linspace(0, 2, 21), X0=1,
                                      ignore_errors=True)
    assert not failed.success
    assert isinstance(failed.message, str) and failed.message.strip()
    discrete = ct.nlsys(lambda t, x, u, p: [x[0]+1], states=1, inputs=0, dt=.2)
    valid = ct.input_output_response(discrete, np.array([0, .2, .4]), X0=1)
    assert_allclose(valid.states, [[1, 2, 3]])
    for t in ([0, .1, .2], [0, .2, .5]):
        with pytest.raises(ValueError):
            ct.input_output_response(discrete, np.asarray(t), X0=1)


def test_automatic_grids_collections_and_feedthrough_warning():
    models = [ct.ss([[-rate]], [[1]], [[2]], [[0]], name=name)
              for rate, name in [(1, 'slow'), (3, 'fast')]]
    for entry in (ct.step_response, ct.impulse_response, ct.initial_response):
        options = {'X0': 2} if entry is ct.initial_response else {}
        results = entry(models, squeeze=False, **options)
        assert len(results) == 2
        for rate, r in zip([1, 3], results):
            t = np.asarray(r.time)
            assert len(t) > 1 and np.all(np.diff(t) > 0)
            assert_allclose(t, results[0].time)
            if entry is ct.step_response:
                x = (1-np.exp(-rate*t))/rate
            else:
                x = np.exp(-rate*t)*(2 if entry is ct.initial_response else 1)
            assert_allclose(np.asarray(r.states).reshape(-1), x, atol=1e-8)
            assert_allclose(np.asarray(r.outputs).reshape(-1), 2*x, atol=1e-8)
    feedthrough = ct.ss([[-2]], [[1]], [[3]], [[4]])
    t = np.linspace(0, 1, 11)
    result = invoke(ct.impulse_response, (feedthrough, t), {'squeeze': False})
    assert result.returned
    assert user_warnings(result, UserWarning)
    assert_allclose(result.value.outputs, [[3*np.exp(-2*t)]], atol=1e-9)
    # The same dynamics without direct feedthrough lose no impulse component.
    quiet = invoke(ct.impulse_response, (ct.ss([[-2]], [[1]], [[3]], [[0]]), t),
                   {'squeeze': False})
    assert quiet.returned and not user_warnings(quiet, UserWarning)
    assert_allclose(quiet.value.outputs, [[3*np.exp(-2*t)]], atol=1e-9)


def test_response_combination_and_plot_coordinates():
    t = np.linspace(0, 2, 11)
    model = ct.ss([[-1]], [[1]], [[2]], [[0]],
                  inputs=['drive'], outputs=['position'], name='plant')
    responses = [ct.forced_response(model, t, k*np.ones(len(t)), squeeze=False)
                 for k in [1, 3]]
    combined = ct.combine_time_responses(responses, trace_labels=['low', 'high'])
    assert combined.input_labels == ['drive']
    assert combined.output_labels == ['position']
    assert combined.trace_labels == ['low', 'high']
    assert combined.sysname == 'plant'
    assert_allclose(combined.time, t)
    for j, k in enumerate([1, 3]):
        assert_allclose(combined.inputs[:, j], [k*np.ones(len(t))])
        assert_allclose(combined.states[:, j], [k*(1-np.exp(-t))], atol=1e-9)
        assert_allclose(combined.outputs[:, j], [2*k*(1-np.exp(-t))], atol=1e-9)
    with headless_figures() as plt:
        for overlay in (False, True):
            plt.figure()
            plot = ct.time_response_plot(combined, plot_inputs=True,
                        overlay_traces=overlay, add_initial_zero=False)
            lines = [line for group in plot.lines.flat for line in group]
            expected = [combined.outputs[0, j] for j in range(2)] + [combined.inputs[0, j] for j in range(2)]
            assert len(lines) == len(expected)
            # Coordinate matching is unordered; subplot layout and style are free.
            remaining = list(lines)
            for y in expected:
                matches = [line for line in remaining if np.allclose(line.get_ydata(), y)]
                assert len(matches) == 1
                assert_allclose(matches[0].get_xdata(), t)
                remaining.remove(matches[0])
            if overlay:
                for group in plot.lines.flat:
                    assert len({line.get_label() for line in group}) == len(group)
        plt.figure()
        outputs_only = ct.time_response_plot(combined, plot_inputs=False,
                                            overlay_traces=True)
        selected_lines = [line for group in outputs_only.lines.flat for line in group]
        assert len(selected_lines) == 2
        for line, j in zip(selected_lines, range(2)):
            assert_allclose(line.get_xdata(), t)
            assert_allclose(line.get_ydata(), combined.outputs[0, j])
        plt.figure()
        second_model = ct.ss([[-2]], [[1]], [[3]], [[0]], name='second')
        first_plot = ct.time_response_plot(responses[0], plot_inputs=False)
        second_response = ct.forced_response(second_model, t, np.ones(len(t)), squeeze=False)
        second_plot = ct.time_response_plot(second_response, plot_inputs=False, ax=first_plot.axes)
        first_line = first_plot.lines[0, 0][0]
        second_line = second_plot.lines[0, 0][0]
        assert first_line.get_label() != second_line.get_label()
        assert_allclose(first_line.get_ydata(), 2*(1-np.exp(-t)))
        assert_allclose(second_line.get_ydata(), 1.5*(1-np.exp(-2*t)))
        assert_allclose(second_line.get_xdata(), t)
    other_time = ct.forced_response(model, t*2, np.ones(len(t)))
    other_shape = ct.forced_response(ct.ss([[-1]], [[1]], [[1], [2]], [[0], [0]]), t, np.ones(len(t)))
    for other in (other_time, other_shape):
        with pytest.raises(ValueError):
            ct.combine_time_responses([responses[0], other])


def test_step_transient_characteristics():
    t = np.arange(11, dtype=float)
    wave = np.array([0, -.2, .1, .2, .8, .9, 1.2, 1.2, .97, 1.01, 1])
    # Cover thresholds both on samples and between samples without interpolation.
    for scale in (2, -3):
        for options, rise, settle, lower in [({}, 3, 9, .9),
                ({'RiseTimeLimits': (.15, .75), 'SettlingTimeThreshold': .05}, 1, 8, .8)]:
            info = ct.step_info(scale*wave, t, **options)
            expected = dict(RiseTime=rise, SettlingTime=settle,
                SettlingMin=min(scale*lower, scale*1.2),
                SettlingMax=max(scale*lower, scale*1.2), Overshoot=20,
                Undershoot=20, Peak=abs(scale)*1.2, PeakTime=6, SteadyStateValue=scale)
            for key, value in expected.items():
                assert_allclose(info[key], value, atol=1e-9)
    # Explicit final values take precedence over the last data sample.
    data = np.array([wave, -2*wave, 3*wave, -4*wave]).reshape(2, 2, -1)
    data[:, :, -1] *= 1.01
    finals = np.array([[1, -2], [3, -4]])
    info = ct.step_info(data, t, final_output=finals.tolist())
    for i in range(2):
        for j in range(2):
            assert_allclose(info[i][j]['SteadyStateValue'], finals[i, j])
            assert_allclose(info[i][j]['Peak'], abs(finals[i, j])*1.2)
            assert_allclose(info[i][j]['RiseTime'], 3)
    model_info = ct.step_info(ct.tf([2], [1, 1]), np.linspace(0, 8, 801))
    assert_allclose(model_info['SteadyStateValue'], 2)
