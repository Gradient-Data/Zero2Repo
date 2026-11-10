# feature: F09
"""Small public SVI workloads and independent objective distributions."""
from F01_helpers import jax, jnp, np, dist, call_public, read_array
import velnora
from velnora.infer import SVI, Trace_ELBO
from velnora import optim


def empty_guide(*args, **kwargs):
    pass


def location_model(target=2.3):
    location = velnora.param('location', -.7)
    velnora.sample('data', dist.Normal(location, 1.), obs=target)


def location_svi(optimizer=None, objective=None):
    return SVI(location_model, empty_guide,
               optim.Adam(.08) if optimizer is None else optimizer,
               Trace_ELBO() if objective is None else objective)


def objective_samples(objective, model, guide, count=8192):
    keys = jax.random.split(jax.random.key(937), count)
    return read_array(call_public(jax.jit(jax.vmap(
        lambda key: objective.loss(key, {}, model, guide))), keys, timeout=240))
