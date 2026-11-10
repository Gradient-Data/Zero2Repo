# feature: F07
"""Public fixtures for storage and carrier conversion."""
from velmora import Network
from F06_helpers import dispatch_bus


def storage_dispatch(component, demand=(0, 8, 8), **attrs):
    n = dispatch_bus(list(demand), tuple(range(len(demand))))
    n.add('Generator', 'supply', bus='sink', p_nom=100,
          marginal_cost=[1] + [20]*(len(demand)-1))
    rating = {'p_nom': 10} if component == 'StorageUnit' else {'e_nom': 10}
    n.add(component, 'buffer', bus='sink', **(rating | attrs))
    return n


def storage_fields(n, component):
    c = n.components[component]
    return c.dynamic.p['buffer'], c.dynamic[
        'state_of_charge' if component == 'StorageUnit' else 'e']['buffer']


def port_network(snapshots=(0, 1)):
    n = Network()
    n.set_snapshots(snapshots)
    n.add('Carrier', 'AC')
    n.add('Bus', ['fuel', 'product', 'heat', 'aux'], carrier='AC')
    n.add('Generator', 'fuel', bus='fuel', p_nom=100, marginal_cost=2)
    n.add('Generator', 'aux', bus='aux', p_nom=100, marginal_cost=3)
    return n
