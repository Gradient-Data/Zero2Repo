# feature: F18
"""Acceptance tests for inference over discovered stochastic model paths."""
import pytest
from F18_helpers import (jax, np, dist, call_public, read_array, close, softmax,
    support_method, equal_dimension_model, run_support, normalized_weights, path_oracle,
    check_path_posterior, independent_guide_bound)
import velnora
from F10_helpers import ag
from velnora.infer import (Trace_ELBO, TraceMeanField_ELBO, TraceGraph_ELBO,
                           TraceEnum_ELBO, RenyiELBO)


def test_f18_t01():
    for seed, y in [(1801, 1.4), (1802, -.4)]:
        result = run_support(support_method('dcc', model=equal_dimension_model), seed, y)
        paths = list(result.samples)
        assert 1 <= len(paths) <= 2
        weights = normalized_weights(result, paths)
        for path in paths:
            check_path_posterior(result, 'dcc', path, y, varying=False)
        expected = softmax([path_oracle(p, y, varying=False)[3] for p in paths])
        # Approximate posterior-mass estimates, not a pinned random sequence.
        np.testing.assert_allclose(weights, expected, atol=.08, rtol=0)


def test_f18_t02():
    for seed, y in [(1811, 1.4), (1812, -.4)]:
        result = run_support(support_method('sdvi'), seed, y)
        paths = list(result.guides)
        assert 1 <= len(paths) <= 2
        weights = normalized_weights(result, paths)
        bounds = []
        for path in paths:
            check_path_posterior(result, 'sdvi', path, y)
            guide, params = result.guides[path]
            bounds.append(independent_guide_bound(guide, params, path, y))
        np.testing.assert_allclose(weights, softmax(bounds), atol=.04, rtol=0)


def test_f18_t03():
    for kind in ('dcc', 'sdvi'):
        # A single exploratory execution can only discover one path. A larger
        # budget still cannot override the caller's cap. No full-discovery claim.
        for explore, cap in [(1, 2), (128, 1), (128, 2)]:
            result = run_support(support_method(kind, explore=explore, cap=cap), 1820)
            paths = list(result.samples if kind == 'dcc' else result.guides)
            assert 1 <= len(paths) <= min(explore, cap)
            normalized_weights(result, paths)
            for path in paths:
                check_path_posterior(result, kind, path, 1.4)


def test_f18_t04():
    # Every listed compatible objective must perform useful local inference.
    for objective in (Trace_ELBO, TraceMeanField_ELBO, TraceGraph_ELBO, TraceEnum_ELBO):
        result = run_support(support_method('sdvi', cap=1, guide_init=ag.AutoNormal,
                             loss=objective(num_particles=16)), 1830)
        assert len(result.guides) == 1
        normalized_weights(result, result.guides)
        for path in result.guides:
            check_path_posterior(result, 'sdvi', path, 1.4)
    with pytest.raises(ValueError):
        method = support_method('sdvi', loss=RenyiELBO())
        run_support(method, 1831)

    def continuous_branch(y):
        velnora.sample('branch', dist.Normal(0., 1.), infer={'branching': True})
        velnora.sample('x', dist.Normal(0., 1.))
    for kind in ('dcc', 'sdvi'):
        # The valid counterparts run above and in T01; inspect the explicit
        # public failure carrier, never incidental exception prose.
        with pytest.raises(RuntimeError):
            run_support(support_method(kind, model=continuous_branch), 1832)
