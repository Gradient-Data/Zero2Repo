# feature: F14
"""Small scenario investment problems through public network entries."""
from F08_helpers import expansion_problem
from F06_helpers import assert_close


def scenario_investment(probabilities, demands, availability, capital_cost):
    n, _ = expansion_problem('Generator', p_nom=0, capital_cost=capital_cost)
    n.c.generators.static.loc['backup', 'marginal_cost'] = 11
    n.set_scenarios(probabilities)
    for scenario, demand, available in zip(probabilities, demands, availability):
        n.c.loads.static.loc[(scenario, 'demand'), 'p_set'] = demand
        n.c.generators.static.loc[(scenario, 'asset'), 'p_max_pu'] = available
    return n


def observe_scenario_supply(n, scenarios, demands, availability, capacity, *, economic_dispatch=True):
    """Check common investment and every scenario's real operating result."""
    costs = []
    for scenario, demand, available in zip(scenarios, demands, availability):
        installed = n.c.generators.static.at[(scenario, 'asset'), 'p_nom_opt']
        assert_close(installed, capacity)
        cheap = n.c.generators.dynamic.p.at['now', (scenario, 'asset')]
        backup = n.c.generators.dynamic.p.at['now', (scenario, 'backup')]
        assert_close(cheap + backup, demand)
        assert cheap >= -1e-5 and backup >= -1e-5
        assert cheap <= available * installed + 1e-5
        if economic_dispatch:
            assert_close(cheap, min(demand, available * capacity))
        costs.append(cheap + 11 * backup)
    return costs


def bind_risk_and_optimize(n, alpha, omega):
    n.set_risk_preference(alpha=alpha, omega=omega)
    return n.optimize(solver_name='highs', solver_options={'threads': 1})
