# feature: F10
"""Public canvas observations and independent response references."""
import re
from decimal import Decimal
import numpy as np
from numpy.testing import assert_allclose
from matplotlib.backend_bases import MouseEvent
from scipy.signal import TransferFunction, step
from _helpers import labeled_artists
from F01_helpers import assert_unordered_roots
from F08_helpers import assert_phase_coordinates


def complex_coordinates(lines):
    return np.concatenate([np.asarray(line.get_xdata()) +
                           1j*np.asarray(line.get_ydata()) for line in lines])


def design_axis(figure, title):
    matches = [axis for axis in figure.axes if axis.get_title() == title]
    assert len(matches) == 1
    return matches[0]


def response_line(axis):
    # Data-coordinate curves exclude axis-spanning reference lines.
    matches = [line for line in axis.lines if line.get_transform() == axis.transData]
    assert len(matches) == 1
    return matches[0]


def release_at(axis, point):
    canvas = axis.figure.canvas
    canvas.draw()
    x, y = axis.transData.transform((point.real, point.imag))
    event = MouseEvent('button_release_event', canvas, x, y, button=1)
    assert event.inaxes is axis
    canvas.callbacks.process('button_release_event', event)
    return complex(event.xdata, event.ydata)


def assert_selected_gain(axis, texts, expected_gain, expected_roots):
    # Only the published numeric gain field is parsed; surrounding prose is free.
    fields = [m.group(1) for text in texts for m in
              re.finditer(r'\bgain\s*=\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)', text)]
    assert len(fields) == 1
    quantum = float(Decimal(fields[0]).as_tuple().exponent)
    assert abs(float(fields[0])-expected_gain) <= .5*10**quantum + 1e-9
    markers = labeled_artists(axis, '_gain_point')
    assert markers
    assert_unordered_roots(complex_coordinates(markers), np.asarray(expected_roots))


def assert_design_response(figure, loop_value, step_num, step_den):
    mag = response_line(design_axis(figure, 'Bode magnitude'))
    phase = response_line(design_axis(figure, 'Bode phase'))
    assert_allclose(mag.get_ydata(), abs(loop_value(np.asarray(mag.get_xdata()))),
                    rtol=1e-6, atol=1e-9)
    assert_phase_coordinates(phase.get_ydata(), loop_value(np.asarray(phase.get_xdata())),
                             degrees=True)
    assert_step_display(figure, step_num, step_den)


def assert_step_display(figure, numerator, denominator):
    line = response_line(design_axis(figure, 'Step response'))
    times = np.asarray(line.get_xdata())
    assert len(times) > 2 and times[-1] > times[0]
    _, expected = step(TransferFunction(numerator, denominator), T=times)
    assert_allclose(line.get_ydata(), expected, rtol=2e-6, atol=2e-8)
