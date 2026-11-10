# feature: F05
"""Public network fixtures and independent terminal circuit observations."""

import numpy as np
import pandas as pd

from F03_helpers import electrical_pair


def flow_network():
    n = electrical_pair()
    n.c.buses.static.loc[:, 'v_nom'] = 1.
    n.c.lines.static.loc['circuit', ['r', 'x', 'g', 'b']] = [.02, .15, .003, .02]
    n.add('Bus', 'tail', v_nom=1)
    n.add('Transformer', 'step', bus0='east', bus1='tail', s_nom=1,
          r=.025, x=.12, g=.006, b=-.025)
    n.set_snapshots(['light', 'heavy', 'unused'])
    n.add('Generator', 'reference', bus='west', control='Slack', p_set=.04)
    n.add('Generator', 'regulated', bus='east', control='PV', p_set=.06)
    n.add('Load', 'demand', bus='tail',
          p_set=pd.Series([.18, .27, .1], index=n.snapshots), q_set=.055)
    return n


def capture_circuit(n):
    """Freeze supplied physical data before the analysis can change any tables."""
    return {category: n.components[category].static.copy(deep=True)
            for category in ['Bus', 'Line', 'Transformer', 'ShuntImpedance']}


def circuit_observation(n, snapshot, circuit):
    """Compute complex bus withdrawals from voltages and physical branch inputs.

    The central-node transformer uses its original T circuit directly; no
    product admittance caches, dependent parameters, or solver are consulted.
    """
    voltage = (n.c.buses.dynamic.v_mag_pu.loc[snapshot]
               * np.exp(1j * n.c.buses.dynamic.v_ang.loc[snapshot]))
    balance = pd.Series(0j, index=circuit['Bus'].index)
    terminals = {}
    for category in ('Line', 'Transformer'):
        for name, row in circuit[category].iterrows():
            v0, v1 = voltage[row.bus0], voltage[row.bus1]
            if category == 'Line':
                scale = circuit['Bus'].at[row.bus0, 'v_nom'] ** 2
                z = complex(row.r, row.x) / scale
                y = complex(row.g, row.b) * scale
                a0 = a1 = 1
                model = 'pi'
            else:
                z = complex(row.r, row.x) / row.s_nom
                y = complex(row.g, row.b) * row.s_nom
                a0 = (row.tap_ratio if row.tap_side == 0 else 1) * np.exp(1j*np.deg2rad(row.phase_shift))
                a1 = row.tap_ratio if row.tap_side == 1 else 1
                model = row.model
            u0, u1 = v0/a0, v1/a1
            if model == 't':
                midpoint = (u0 + u1) / (2 + y*z/2)
                j0, j1 = (u0-midpoint)/(z/2), (u1-midpoint)/(z/2)
            else:
                j0 = (u0-u1)/z + u0*y/2
                j1 = (u1-u0)/z + u1*y/2
            s0, s1 = u0*np.conj(j0), u1*np.conj(j1)
            terminals[category, name] = (s0, s1)
            balance[row.bus0] += s0
            balance[row.bus1] += s1
    for name, row in circuit['ShuntImpedance'].iterrows():
        base = circuit['Bus'].at[row.bus, 'v_nom'] ** 2
        balance[row.bus] += abs(voltage[row.bus])**2 * base * complex(row.g, -row.b)
    return balance, terminals


def check_ac_balance(n, snapshot, circuit, *, atol=1e-6):
    balance, terminals = circuit_observation(n, snapshot, circuit)
    for (category, name), powers in terminals.items():
        dynamic = n.components[category].dynamic
        for end, expected in enumerate(powers):
            actual = (dynamic['p'+str(end)].at[snapshot, name]
                      + 1j*dynamic['q'+str(end)].at[snapshot, name])
            np.testing.assert_allclose(actual, expected, atol=atol, rtol=0)
    injections = n.c.buses.dynamic.p.loc[snapshot] + 1j*n.c.buses.dynamic.q.loc[snapshot]
    np.testing.assert_allclose(injections.loc[balance.index], balance, atol=atol, rtol=0)
    # Independent component accounting also checks that generator/load outputs
    # and reported bus injections represent the same physical solution.
    supply = pd.Series(0j, index=balance.index)
    for category, sign in [('Generator', 1), ('Load', -1)]:
        c = n.components[category]
        for name, row in c.static.iterrows():
            supply[row.bus] += sign * (c.dynamic.p.at[snapshot, name]
                                       + 1j*c.dynamic.q.at[snapshot, name])
    np.testing.assert_allclose(supply, balance, atol=atol, rtol=0)
    return balance, terminals
