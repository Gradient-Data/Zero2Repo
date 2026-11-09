# feature: F03
"""Caller-supplied laws for nonlinear model acceptance tests."""


def coupled_update(t, x, u, p):
    return [p['gain'] * x[0] ** 2 + x[1] * u[0] + t,
            x[0] * x[1] - u[1] ** 2 + p['bias'] * t]


def coupled_output(t, x, u, p):
    return [x[0] * u[1] + p['gain'] * t,
            x[1] ** 2 + u[0] * u[1] + p['bias'],
            x[0] - x[1] + t * u[0]]


def static_map(t, x, u, p):
    return [u[0] ** 2 - 2 * u[1], u[0] * u[1] + 3]


def parameter_update(t, x, u, p):
    return [p['a'] * x[0] + p['b'] * u[0] + p['bias']]


def parameter_output(t, x, u, p):
    return [p['c'] * x[0] + p['d'] * u[0] - p['bias']]
