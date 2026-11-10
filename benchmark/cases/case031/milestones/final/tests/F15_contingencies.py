# feature: F15
"""Acceptance checks for linear outages and security-constrained dispatch."""
import pandas as pd
from _helpers import invoke
from F06_helpers import assert_close, solve_dispatch
from F15_helpers import (outage_mesh, parallel_security, solve_security,
                         check_mesh_cases, check_parallel_dispatch,
                         transformer_security, check_transformer_dispatch,
                         isle_security)


def test_outage_flows_redistribute_injections():
    n = outage_mesh()
    outages = [('Line', 'asset'), ('Line', 'bc'), ('Transformer', 'parallel')]
    result = invoke(n.lpf_contingency, ['now'], kwargs={'branch_outages': outages})
    check_mesh_cases(n, result.value, outages)
    # The selected snapshot, not the network's first one, supplies injections.
    n = outage_mesh()
    n.set_snapshots(['earlier', 'now'])
    n.add('Generator', 'middle', bus='b', p_set=pd.Series([0., 12.], index=n.snapshots))
    n.add('Load', 'extra', bus='c', p_set=pd.Series([0., 12.], index=n.snapshots))
    result = invoke(n.lpf_contingency, ['now'], kwargs={'branch_outages': outages})
    check_mesh_cases(n, result.value, outages, {'a': 30, 'b': 12, 'c': -42})


def test_security_dispatch_uses_each_period_topology():
    n = parallel_security(periods=True)
    solve_security(n, branch_outages=['small', 'medium', 'large'],
                   multi_investment_periods=True)
    # Equal reactances split transfers equally. In the first period the
    # smallest surviving rating limits two-line transfer to 60; after its
    # retirement the remaining single-line contingencies limit transfer to 50.
    check_parallel_dispatch(n, [['small', 'medium', 'large'], ['medium', 'large']],
                            [60, 50], ['small', 'medium', 'large'])
    ordinary = parallel_security(periods=True)
    solve_dispatch(ordinary, multi_investment_periods=True)
    assert_close(ordinary.c.generators.dynamic.p['remote'], [90, 90])
    # Every requested outage constrains dispatch, also those in a second,
    # separately connected subnetwork: there the 20 MVA line caps transfer at 40.
    for selection in ('default', 'explicit'):
        n = isle_security(parallel_security())
        kwargs = {} if selection == 'default' else {
            'branch_outages': ['small', 'medium', 'large', 'i1', 'i2', 'i3']}
        solve_security(n, **kwargs)
        p = n.c.generators.dynamic.p.loc['now']
        assert_close(p[['remote', 'local', 'isle-remote', 'isle-local']], [60, 30, 40, 50])
        assert_close(n.objective, 60 + 300 + 40 + 500)


def test_default_explicit_and_invalid_outage_selection():
    n = outage_mesh()
    all_outages = [('Line', name) for name in ['asset', 'bc', 'ac']]
    all_outages += [('Transformer', 'parallel')]
    check_mesh_cases(n, invoke(n.lpf_contingency, ['now']).value, all_outages)
    # Rotate which outage is uniquely binding: omitting any active line from
    # the default set then permits excess cheap supply. Each arm starts fresh.
    names = ['small', 'medium', 'large']
    for critical in names:
        for selection in ('default', 'explicit', 'excluded'):
            n = parallel_security()
            others = [name for name in names if name != critical]
            n.c.lines.static.loc[critical, ['x', 's_nom']] = [.1, 100]
            n.c.lines.static.loc[others, 's_nom'] = [30, 50]
            kwargs = {} if selection == 'default' else {'branch_outages':
                pd.MultiIndex.from_tuples([('Line', name) for name in
                                          (names if selection == 'explicit' else others)])}
            solve_security(n, **kwargs)
            maximum = 90 if selection == 'excluded' else 60
            check_parallel_dispatch(n, [names], [maximum],
                                    others if selection == 'excluded' else names)
    # A transformer outage must also constrain the default security set.
    # Its loss leaves a .3-reactance path in parallel with a .2-reactance line:
    # the path carries 2/5 of transfer and its rating bounds transfer to 75.
    for selection in ('default', 'excluded'):
        n = transformer_security()
        selected = all_outages if selection == 'default' else all_outages[:-1]
        kwargs = {} if selection == 'default' else {
            'branch_outages': pd.MultiIndex.from_tuples(selected)}
        solve_security(n, **kwargs)
        check_transformer_dispatch(n, 75 if selection == 'default' else 90, selected)
    # Default security selection ignores an asset outside every selected period.
    n = parallel_security(periods=True)
    solve_security(n, multi_investment_periods=True)
    check_parallel_dispatch(n, [names, ['medium', 'large']], [60, 50], names)
    for invalid in ['absent', 'future']:
        n = parallel_security(periods=True)
        result = invoke(n.optimize.optimize_security_constrained,
                        kwargs={'branch_outages': ['medium', invalid],
                                'multi_investment_periods': True,
                                'solver_name': 'highs', 'solver_options': {'threads': 1}},
                        expected_exceptions=(ValueError,))
        assert isinstance(result.exception, ValueError), result
    n = outage_mesh()
    result = invoke(n.lpf_contingency, ['now'],
                    kwargs={'branch_outages': [('Line', 'absent')]},
                    expected_exceptions=(KeyError,))
    assert isinstance(result.exception, KeyError), result
