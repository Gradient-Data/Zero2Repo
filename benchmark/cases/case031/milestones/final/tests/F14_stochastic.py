# feature: F14
"""Acceptance checks for shared investment, expected costs and tail risk."""
import numpy as np
from _helpers import invoke
from F06_helpers import assert_close, dispatch_bus, solve_dispatch
from F14_helpers import (scenario_investment, observe_scenario_supply,
                         bind_risk_and_optimize)


def test_shared_investment_and_probability_weighted_recourse():
    # Only probabilities change. Common capacity must cover scenario recourse,
    # not an average load or independently financed scenario investments.
    for probabilities, capacity, objective in [
        ({'mild': .8, 'scarce': .2}, 4, 33.2),
        ({'mild': .2, 'scarce': .8}, 20, 68.8),
    ]:
        n = scenario_investment(probabilities, [4, 10], [1, .5], 3)
        solve_dispatch(n)
        costs = observe_scenario_supply(n, probabilities, [4, 10], [1, .5], capacity)
        assert_close(n.objective, 3 * capacity + np.dot(list(probabilities.values()), costs))
        assert_close(n.objective, objective)


def test_tail_probability_mass_and_risk_blend():
    probabilities = {'low': .6, 'middle': .3, 'high': .1}
    # For alpha=.75, the tail uses all of high plus half of middle.
    # These optima are the minima of the small piecewise-linear investment
    # problem, not quantities read from the product's risk auxiliary variables.
    for alpha, omega, capacity, objective in [
        (.75, 0, 2, 34), (.75, .5, 6, 45.8),
        (.75, 1, 6, 53.6), (.9, 1, 10, 60),
    ]:
        n = scenario_investment(probabilities, [2, 6, 10], [1, 1, 1], 5)
        result = invoke(bind_risk_and_optimize, n, alpha, omega)
        assert result.value == ('ok', 'optimal'), result
        costs = observe_scenario_supply(
            n, probabilities, [2, 6, 10], [1, 1, 1], capacity,
            economic_dispatch=omega < 1)
        expected = np.dot([.6, .3, .1], costs)
        tail = np.dot([0, .6, .4], costs) if alpha == .75 else costs[2]
        assert_close(n.objective, 5 * capacity + (1 - omega) * expected + omega * tail)
        assert_close(n.objective, objective)


def test_risk_preference_boundaries_and_unsupported_combinations():
    # The same public binding/solve path accepts both closed weight endpoints
    # and confidence levels close to either open endpoint.
    for alpha, omega in [(.01, 0), (.99, 1)]:
        n = scenario_investment({'a': .4, 'b': .6}, [4, 4], [1, 1], 3)
        result = invoke(bind_risk_and_optimize, n, alpha, omega)
        assert result.value == ('ok', 'optimal'), result
        observe_scenario_supply(n, ['a', 'b'], [4, 4], [1, 1], 4)
        assert_close(n.objective, 16)
    for alpha, omega in [(-.1, .5), (0, .5), (1, .5), (1.1, .5),
                         (.5, -.1), (.5, 1.1)]:
        n = scenario_investment({'a': .4, 'b': .6}, [4, 4], [1, 1], 3)
        result = invoke(bind_risk_and_optimize, n, alpha, omega,
                        expected_exceptions=(ValueError,))
        assert isinstance(result.exception, ValueError), result
    n = dispatch_bus(4)
    n.add('Generator', 'supply', bus='sink', p_nom=10, marginal_cost=1)
    result = invoke(bind_risk_and_optimize, n, .5, .5,
                    expected_exceptions=(ValueError,))
    assert isinstance(result.exception, ValueError), result
    # Ordinary quadratic dispatch works, but combining it with risk is refused.
    n = dispatch_bus(4)
    n.add('Generator', 'supply', bus='sink', p_nom=10,
          marginal_cost=1, marginal_cost_quadratic=.1)
    solve_dispatch(n)
    assert_close(n.c.generators.dynamic.p['supply'], 4)
    assert_close(n.objective, 5.6)
    n = dispatch_bus(4)
    n.add('Generator', 'supply', bus='sink', p_nom=10,
          marginal_cost=1, marginal_cost_quadratic=.1)
    n.set_scenarios({'a': .4, 'b': .6})
    result = invoke(bind_risk_and_optimize, n, .5, .5,
                    expected_exceptions=(ValueError,))
    assert isinstance(result.exception, ValueError), result
