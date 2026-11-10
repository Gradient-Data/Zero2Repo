# feature: F15
"""Small connected outage problems and independent circuit equations."""
import numpy as np
import pandas as pd
from _helpers import invoke
from F05_helpers import capture_circuit
from F06_helpers import assert_close, dispatch_bus
from F08_helpers import transmission_triangle


def outage_mesh():
    n = transmission_triangle()
    n.c.lines.static.loc[:, 's_nom_extendable'] = False
    n.c.lines.static.loc[:, 's_nom'] = 100
    n.c.lines.static.loc[:, 'r'] = 0
    n.add('Transformer', 'parallel', bus0='a', bus1='c',
          s_nom=100, x=20, r=0)
    n.c.generators.static.loc['supply', 'p_set'] = 30
    return n


def parallel_security(periods=False):
    n = dispatch_bus(90)
    n.add('Bus', 'source', v_nom=1)
    n.add('Generator', 'remote', bus='source', p_nom=100, marginal_cost=1)
    n.add('Generator', 'local', bus='sink', p_nom=100, marginal_cost=10)
    n.add('Line', ['small', 'medium', 'large'], bus0='source', bus1='sink',
          x=1, r=0, s_nom=[30, 50, 100])
    if periods:
        n.set_investment_periods([2020, 2030])
        n.c.lines.static.loc['small', ['build_year', 'lifetime']] = [2000, 25]
        n.add('Line', 'future', bus0='source', bus1='sink', x=1,
              s_nom=100, build_year=2040)
    return n


def solve_security(n, **kwargs):
    result = invoke(n.optimize.optimize_security_constrained, kwargs={
        'solver_name': 'highs', 'solver_options': {'threads': 1}, **kwargs},)
    assert result.value == ('ok', 'optimal'), result
    return n


def physical_flows(circuit, injections, branches, outage=None):
    """Solve Kirchhoff's lossless circuit equations from original user data.

    No product flows, admittance matrices or outage distribution factors enter
    this independent node-voltage calculation. All buses have unit base voltage;
    transformers use unit taps, no phase shift and their supplied power base.
    """
    buses = list(circuit['Bus'].index)
    live = [key for key in branches if key != outage]
    incidence = np.zeros((len(buses), len(live)))
    admittance = []
    for col, (component, name) in enumerate(live):
        row = circuit[component].loc[name]
        incidence[buses.index(row.bus0), col] = 1
        incidence[buses.index(row.bus1), col] = -1
        reactance = row.x if component == 'Line' else row.x / row.s_nom
        admittance.append(1 / reactance)
    admittance = np.asarray(admittance)
    laplacian = (incidence * admittance) @ incidence.T
    assert_close(sum(injections.values()), 0)
    theta = np.zeros(len(buses))
    theta[1:] = np.linalg.solve(laplacian[1:, 1:],
                               [injections[b] for b in buses[1:]])
    powers = admittance * (incidence.T @ theta)
    result = pd.Series(0., index=pd.MultiIndex.from_tuples(branches))
    for key, power in zip(live, powers):
        result.at[key] = power
    return result


def check_mesh_cases(n, result, outages, injections=None):
    circuit = capture_circuit(n)
    branches = [(c, name) for c in ('Line', 'Transformer')
                for name in circuit[c].index]
    assert set(result.index) == set(branches)
    assert set(result.columns) == {'base', *outages}
    if injections is None:
        injections = {'a': 30, 'b': 0, 'c': -30}
    for column, outage in [('base', None), *((key, key) for key in outages)]:
        expected = physical_flows(circuit, injections, branches, outage)
        assert_close(result[column].loc[expected.index], expected)


def isle_security(n):
    """Add a second, separate secure-transfer island to a parallel case.

    Equal reactances split transfer equally. Losing either larger line leaves
    the 20 MVA line carrying half the transfer, capping secure transfer at 40;
    with no outage selected there the same rating allows 60.
    """
    n.add('Bus', ['isle-sink', 'isle-source'], v_nom=1)
    n.add('Load', 'isle-demand', bus='isle-sink', p_set=90)
    n.add('Generator', 'isle-remote', bus='isle-source', p_nom=100, marginal_cost=1)
    n.add('Generator', 'isle-local', bus='isle-sink', p_nom=100, marginal_cost=10)
    n.add('Line', ['i1', 'i2', 'i3'], bus0='isle-source', bus1='isle-sink',
          x=1, r=0, s_nom=[20, 40, 100])
    return n


def check_parallel_dispatch(n, active, expected_remote, outages):
    circuit = capture_circuit(n)
    costs = 0
    for snapshot, names, maximum in zip(n.snapshots, active, expected_remote):
        remote = n.c.generators.dynamic.p.at[snapshot, 'remote']
        local = n.c.generators.dynamic.p.at[snapshot, 'local']
        assert 0 <= remote <= 100
        assert 0 <= local <= 100
        assert_close(remote + local, 90)
        # Positive remote cost advantage makes the maximum secure transfer the
        # unique optimal transfer; no particular internal optimisation is used.
        assert_close(remote, maximum)
        costs += remote + 10 * local
        branches = [('Line', name) for name in names]
        for outage in [None, *(('Line', name) for name in outages if name in names)]:
            flows = physical_flows(circuit, {'source': remote, 'sink': -remote},
                                   branches, outage)
            for key in branches:
                assert abs(flows.at[key]) <= circuit['Line'].at[key[1], 's_nom'] + 1e-5
            if outage is None:
                assert_close(n.c.lines.dynamic.p0.loc[snapshot, names],
                             [flows.at[('Line', name)] for name in names])
                assert_close(n.c.lines.dynamic.p1.loc[snapshot, names],
                             [-flows.at[('Line', name)] for name in names])
        inactive = set(circuit['Line'].index) - set(names)
        for name in inactive:
            assert_close(n.c.lines.dynamic.p0.at[snapshot, name], 0)
    assert_close(n.objective, costs)


def transformer_security():
    n = outage_mesh()
    n.c.lines.static.loc[['asset', 'bc'], 's_nom'] = 30
    n.c.lines.static.loc['ac', 's_nom'] = 50
    n.c.transformers.static.loc['parallel', 'x'] = 10
    n.c.loads.static.loc['demand', 'p_set'] = 90
    n.remove('Generator', 'supply')
    n.add('Generator', 'supply', bus='a', p_nom=100, marginal_cost=1)
    n.add('Generator', 'local', bus='c', p_nom=100, marginal_cost=10)
    return n


def check_transformer_dispatch(n, maximum, outages):
    circuit = capture_circuit(n)
    branches = [(c, name) for c in ('Line', 'Transformer')
                for name in circuit[c].index]
    remote = n.c.generators.dynamic.p.at['now', 'supply']
    local = n.c.generators.dynamic.p.at['now', 'local']
    assert_close(remote, maximum)
    assert_close(local, 90 - remote)
    assert_close(n.objective, remote + 10 * local)
    for outage in [None, *outages]:
        flows = physical_flows(circuit, {'a': remote, 'b': 0, 'c': -remote},
                               branches, outage)
        for component, name in branches:
            assert abs(flows.at[(component, name)]) <= circuit[component].at[name, 's_nom'] + 1e-5
            if outage is None:
                dynamic = n.components[component].dynamic
                assert_close(dynamic.p0.at['now', name], flows.at[(component, name)])
                assert_close(dynamic.p1.at['now', name], -flows.at[(component, name)])
