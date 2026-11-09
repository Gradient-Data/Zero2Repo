# feature: F11
"""Model-bound coordinate observations; independent numerical volume is reused."""
from F02_helpers import jax, jnp, np, dist, close, read_array, call_public, volume, numerical_jacobian
import velnora
from velnora import handlers as h
from velnora.infer.util import log_density


def latent_model(law, observed=None):
    def model():
        return velnora.sample('x', law, obs=observed)
    return model


def coordinate_run(model, config, supplied, seed=37):
    bound = h.reparam(model, config=config)
    density, record = call_public(log_density, h.seed(bound, seed), (), {}, supplied)
    return read_array(record['x']['value']), read_array(density), record


def recovered(model, config, supplied):
    return coordinate_run(model, config, supplied)[0]
