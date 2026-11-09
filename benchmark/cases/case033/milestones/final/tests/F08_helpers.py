# feature: F08
"""Small real-parameter optimization workloads."""
import torch
import velnora


def named_leaf(name, initial):
    velnora.param(name, torch.as_tensor(initial).clone())
    return dict(velnora.get_param_store().named_parameters())[name]


def apply_gradients(optimizer, entries):
    """Drive the public optimizer with explicitly supplied objective gradients."""
    for parameter, gradient in entries:
        parameter.grad = torch.as_tensor(gradient, dtype=parameter.dtype).clone()
    optimizer([parameter for parameter, _ in entries])


def quadratic(value, center, curvature):
    delta = value - center
    return .5 * (delta * (delta @ curvature)).sum()
