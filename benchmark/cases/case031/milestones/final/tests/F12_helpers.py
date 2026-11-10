# feature: F12
"""Independent physical LP oracle for small near-optimal planning problems."""
import numpy as np
import pytest
from scipy.optimize import linprog
from F06_helpers import dispatch_bus, solve_dispatch, assert_close, detached_solution
from _helpers import invoke


# Variables: two capacities, followed by cheap/backup power at each snapshot.
MGA_COST = np.array([2., 4., 2., 6., 3., 9.])
MGA_BALANCE = np.array([[0, 0, 1, 1, 0, 0], [0, 0, 0, 0, 1, 1]])
MGA_LIMITS = np.array([[-1, 0, 1, 0, 0, 0],
                       [0, -1, 0, 1, 0, 0],
                       [-.5, 0, 0, 0, 1, 0],
                       [0, -1, 0, 0, 0, 1]])
MGA_PROJECTION = np.array([[2, 1, 0, 0, 0, 0],
                           [0, 3, 0, 0, 0, 0]])


def alternative_problem(solved=True):
    n = dispatch_bus([6, 10], ('offpeak', 'peak'))
    n.snapshot_weightings.loc[:, 'objective'] = [2, 3]
    n.add('Generator', 'cheap', bus='sink', p_nom=0,
          p_nom_extendable=True, p_nom_max=20, capital_cost=2,
          marginal_cost=1, p_max_pu=[1, .5])
    n.add('Generator', 'backup', bus='sink', p_nom=0,
          p_nom_extendable=True, p_nom_max=20, capital_cost=4,
          marginal_cost=3)
    if solved:
        solve_dispatch(n)
        assert_close(n.objective, alternative_oracle(MGA_COST).fun)
    return n


def alternative_oracle(objective, budget=None, coordinates=None):
    limits = MGA_LIMITS
    rhs = np.zeros(4)
    if budget is not None:
        limits = np.vstack([limits, MGA_COST])
        rhs = np.r_[rhs, budget]
    balance, demand = MGA_BALANCE, np.array([6., 10.])
    if coordinates is not None:
        balance = np.vstack([balance, MGA_PROJECTION])
        demand = np.r_[demand, coordinates]
    result = linprog(objective, A_ub=limits, b_ub=rhs,
                     A_eq=balance, b_eq=demand,
                     bounds=[(0, 20), (0, 20)]+[(0, None)]*4,
                     method='highs', options={'dual_feasibility_tolerance': 1e-7})
    assert result.success, result.message
    return result


def alternative_decisions(n, budget):
    capacity = n.c.generators.static.loc[['cheap', 'backup'], 'p_nom_opt'].to_numpy()
    power = n.c.generators.dynamic.p.loc[
        ['offpeak', 'peak'], ['cheap', 'backup']].to_numpy().ravel()
    x = np.r_[capacity, power]
    assert np.isfinite(x).all()
    assert (x >= -1e-5).all()
    assert (capacity <= 20+1e-5).all()
    assert_close(MGA_BALANCE @ x, [6, 10])
    assert (MGA_LIMITS @ x <= 1e-5).all()
    assert MGA_COST @ x <= budget+1e-5
    return x


def alternative_call(entry, **kwargs):
    result = invoke(entry, kwargs={'solver_name': 'highs',
                    'solver_options': {'threads': 1}, **kwargs})
    return result.value


def alternative_dimensions():
    return {
        'cheap_build': {'Generator': {'p_nom': {'cheap': 2, 'backup': 1}}},
        'backup_build': {'Generator': {'p_nom': {'backup': 3}}},
    }


@pytest.fixture(scope='module')
def alternative_solution(tmp_path_factory):
    return detached_solution(alternative_problem(),
                             tmp_path_factory.mktemp('alternatives') / 'solved.nc')


@pytest.fixture
def alternative_input():
    """A fresh member for each mutating alternative solve, even inside loops."""
    def fresh(solved=True):
        if not solved:
            return alternative_problem(solved=False)
        return alternative_problem()
    return fresh
