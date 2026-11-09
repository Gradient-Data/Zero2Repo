# feature: F08
"""Small investment problems using public network entries only."""
from velmora import Network
from _helpers import invoke
from F06_helpers import dispatch_bus
from F07_helpers import storage_dispatch


INVESTMENT_COMPONENTS = ('Generator', 'StorageUnit', 'Store', 'Link',
                         'Process', 'Line', 'Transformer')


def expansion_problem(component, **attributes):
    nominal = 'e_nom' if component == 'Store' else (
        's_nom' if component in ('Line', 'Transformer') else 'p_nom')
    attrs = {nominal: 30, nominal+'_extendable': True, 'capital_cost': 2}
    attrs.update(attributes)
    if component in ('StorageUnit', 'Store'):
        n = storage_dispatch(component, demand=(0, 7))
        n.remove(component, 'buffer')
        n.add(component, 'asset', bus='sink', **attrs)
    else:
        n = dispatch_bus(7)
        n.add('Generator', 'backup', bus='sink', p_nom=100, marginal_cost=20)
        if component == 'Generator':
            n.add(component, 'asset', bus='sink', marginal_cost=1, **attrs)
        else:
            n.add('Bus', 'source', v_nom=1)
            n.add('Generator', 'supply', bus='source', p_nom=100, marginal_cost=1)
            if component in ('Line', 'Transformer'):
                attrs.update(r=.01, x=.1)
            n.add(component, 'asset', bus0='source', bus1='sink', **attrs)
    return n, nominal


def investment_flow(n, component):
    return n.components[component].dynamic[
        'p' if component in ('Generator', 'Store', 'StorageUnit', 'Process') else 'p0']['asset']


def financed_supply(**attributes):
    n = dispatch_bus([4, 6], (0, 1))
    n.snapshot_weightings.loc[:, 'objective'] = [2190, 2190]
    n.add('Generator', 'asset', bus='sink', p_nom_extendable=True,
          marginal_cost=2, **attributes)
    return n


def transmission_triangle(carrier='AC'):
    n = Network()
    n.set_snapshots(['now'])
    n.add('Carrier', carrier)
    n.add('Bus', ['a', 'b', 'c'], v_nom=1, carrier=carrier)
    n.add('Line', 'asset', bus0='a', bus1='b', s_nom=10,
          s_nom_extendable=True, s_nom_min=20, capital_cost=1, x=.2, r=.2)
    n.add('Line', 'bc', bus0='b', bus1='c', s_nom=100, x=.1, r=.1)
    n.add('Line', 'ac', bus0='a', bus1='c', s_nom=100, x=.2, r=.2)
    n.add('Generator', 'supply', bus='a', p_nom=100, marginal_cost=1)
    n.add('Load', 'demand', bus='c', p_set=30)
    return n


def solve_transmission(n, **kwargs):
    result = invoke(n.optimize.optimize_transmission_expansion_iteratively,
                    kwargs={'solver_name': 'highs',
                            'solver_options': {'threads': 1},
                            'max_iterations': 10, **kwargs})
    assert result.value == ('ok', 'optimal'), result
    return n
