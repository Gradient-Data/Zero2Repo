# feature: F13
"""Small public piecewise optimisation problems."""
from velmora import Network
from F06_helpers import dispatch_bus


OPERATING_COMPONENTS = ('Generator', 'Link', 'Process', 'StorageUnit', 'Store')


def curve_options(component, attribute, equality=False):
    if not equality:
        return {}
    return {'piecewise_options': [{'component': component, 'attribute': attribute,
                                  'sign': '==' if equality else '>=',
                                  'cumulative_attr': True}]}


def operating_curve_problem(component, curve, demand=8, capacity=10, **attrs):
    n = dispatch_bus(demand)
    n.add('Generator', 'backup', bus='sink', p_nom=100, marginal_cost=5)
    nominal = 'e_nom' if component == 'Store' else 'p_nom'
    attributes = {nominal: capacity, 'marginal_cost': curve, **attrs}
    if component in ('Generator', 'Store', 'StorageUnit'):
        attributes['bus'] = 'sink'
        if component == 'Store':
            attributes['e_initial'] = capacity
        elif component == 'StorageUnit':
            attributes['state_of_charge_initial'] = capacity
    else:
        n.add('Bus', 'source')
        n.add('Generator', 'fuel', bus='source', p_nom=100)
        attributes.update(bus0='source', bus1='sink')
    n.add(component, 'asset', **attributes)
    return n


def bind_and_solve(n, component, attributes):
    """Allow validation either during binding or first optimisation."""
    n.add(component, 'asset', **attributes)
    return n.optimize(solver_name='highs', solver_options={'threads': 1})
