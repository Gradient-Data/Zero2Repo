# feature: F12
"""Acceptance checks for cost-bounded alternative planning."""
import logging
import numpy as np
import pandas as pd
import pytest
from _helpers import invoke
from F06_helpers import assert_close
from F12_helpers import (
    MGA_COST, MGA_PROJECTION, alternative_solution, alternative_input, alternative_oracle,
    alternative_decisions, alternative_call, alternative_dimensions,
)


def test_weighted_alternatives_respect_cost_allowance(alternative_input):
    optimum = alternative_oracle(MGA_COST).fun
    # Separate observable distinctions: omitted slack with minimisation,
    # maximisation with a weighted investment objective, and operational minimisation.
    cases = [
        ({'Generator': {'p_nom': {'cheap': 1}}},
         np.array([1., 0, 0, 0, 0, 0]), {'sense': 'min'}, .05, 1),
        ({'Generator': {'p_nom': {'cheap': 1, 'backup': 2}}},
         np.array([1., 2, 0, 0, 0, 0]), {'sense': 'max', 'slack': .2}, .2, -1),
        ({'Generator': {'p': pd.DataFrame(
            {'cheap': [2., 3.], 'backup': [0., 0.]},
            index=['offpeak', 'peak'])}},
         np.array([0., 0, 2, 0, 3, 0]), {'sense': 'min', 'slack': .1}, .1, 1),
    ]
    for weights, objective, options, slack, sign in cases:
        n = alternative_input()
        assert alternative_call(n.optimize.optimize_mga, weights=weights,
                                **options) == ('ok', 'optimal')
        budget = optimum*(1+slack)
        x = alternative_decisions(n, budget)
        expected = alternative_oracle(sign*objective, budget).fun
        assert_close(sign*objective @ x, expected)
        assert_close(n.objective, expected)
        assert_close(n.meta['slack'], slack)


def test_named_dimensions_single_and_multiple_directions(alternative_input):
    dimensions = alternative_dimensions()
    names = list(dimensions)
    directions = [dict(zip(names, values)) for values in
                  [(1., -1.), (-1., 1.), (1., 1.)]]
    slack = .15
    budget = alternative_oracle(MGA_COST).fun*(1+slack)
    # The second direction omits slack: its optimum moves with the allowance,
    # so the five-percent default is observable rather than assumed.
    for direction, options in zip(directions, [{'slack': slack}, {}, {'slack': slack}]):
        n = alternative_input()
        status, condition, coordinates = alternative_call(
            n.optimize.optimize_mga_in_direction, direction=direction,
            dimensions=dimensions, **options)
        assert (status, condition) == ('ok', 'optimal')
        single_budget = alternative_oracle(MGA_COST).fun*(1+options.get('slack', .05))
        x = alternative_decisions(n, single_budget)
        assert set(coordinates.index) == set(names)
        assert_close(coordinates.loc[names], MGA_PROJECTION @ x)
        objective = -np.array([direction[name] for name in names]) @ MGA_PROJECTION
        expected = alternative_oracle(objective, single_budget).fun
        assert_close(objective @ x, expected)
        assert_close(n.objective, expected)

    n = alternative_input()
    returned, coordinates = alternative_call(
        n.optimize.optimize_mga_in_multiple_directions, directions=directions,
        dimensions=dimensions, slack=slack, max_parallel=1)
    assert set(returned.columns) == set(names)
    assert set(coordinates.columns) == set(names)
    assert len(returned) == len(coordinates) == len(directions)
    assert returned.index.equals(coordinates.index)
    remaining = {tuple(d[name] for name in names) for d in directions}
    for index, row in returned.iterrows():
        direction = tuple(row.loc[names])
        assert direction in remaining
        remaining.remove(direction)
        point = coordinates.loc[index, names].to_numpy(dtype=float)
        assert np.isfinite(point).all()
        objective = -np.array(direction) @ MGA_PROJECTION
        # Batch exposes projections, not network objects. Verify existence of
        # a physically feasible plan at each reported point independently.
        witness = alternative_oracle(np.zeros(6), budget, coordinates=point)
        assert_close(objective @ witness.x,
                     alternative_oracle(objective, budget).fun)
    assert not remaining


def test_invalid_baselines_senses_and_dimension_names_are_refused(alternative_input):
    dimensions = alternative_dimensions()
    direction = dict(zip(dimensions, [1., -1.]))
    # A valid solved counterpart shows these inputs work before changing only
    # the missing baseline or one invalid argument on fresh equivalent inputs.
    weights = {'Generator': {'p_nom': {'cheap': 1}}}
    n = alternative_input()
    assert alternative_call(n.optimize.optimize_mga, weights=weights) == ('ok', 'optimal')
    n = alternative_input()
    assert alternative_call(n.optimize.optimize_mga_in_direction,
                            direction=direction, dimensions=dimensions)[:2] == ('ok', 'optimal')
    for entry in ['optimize_mga', 'optimize_mga_in_direction']:
        n = alternative_input(solved=False)
        kwargs = dict(weights=weights) if entry == 'optimize_mga' else dict(
            direction=direction, dimensions=dimensions)
        with pytest.raises(ValueError):
            alternative_call(getattr(n.optimize, entry), **kwargs)
    n = alternative_input()
    with pytest.raises(ValueError):
        alternative_call(n.optimize.optimize_mga, weights=weights, sense='sideways')
    for wrong in [dict(cheap_build=1),
                  dict(direction, unrelated=1)]:
        n = alternative_input()
        with pytest.raises(ValueError):
            alternative_call(n.optimize.optimize_mga_in_direction,
                             direction=wrong, dimensions=dimensions)
    for solved, requested in [(False, direction), (True, {'cheap_build': 1.})]:
        n = alternative_input(solved=solved)
        result = invoke(n.optimize.optimize_mga_in_multiple_directions, kwargs={
            'directions': [requested], 'dimensions': dimensions,
            'max_parallel': 1, 'solver_name': 'highs',
            'solver_options': {'threads': 1}},
            logger=logging.getLogger('velmora.optimization.mga'))
        returned, coordinates = result.value
        assert returned.empty and coordinates.empty
        assert any(record.levelno >= logging.WARNING for record in result.logs)
