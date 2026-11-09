# feature: F16
"""Independent observations for model identification."""
import numpy as np


def impulse_samples(a, b, c, d, count, period=1):
    """Evaluate the discrete state equations for a unit-area impulse."""
    samples = [np.asarray(d) / period]
    state = np.asarray(b) / period
    for _ in range(count - 1):
        samples.append(c @ state)
        state = a @ state
    return np.stack(samples, axis=-1)


def causal_design(inputs, count):
    """Represent causal convolution as sample rows and lag/channel columns."""
    inputs = np.atleast_2d(inputs)
    return np.array([[inputs[j, k-lag] if k >= lag else 0
                      for lag in range(count) for j in range(len(inputs))]
                     for k in range(inputs.shape[1])])
