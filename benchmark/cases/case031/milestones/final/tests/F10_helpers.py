# feature: F10
"""Public-entry fixtures for system-wide policy constraints."""
from velmora import Network
from F06_helpers import dispatch_bus


def resource_supply(kind, sense, constant, *, expensive=False):
    n = dispatch_bus(4, ('a', 'b'))
    n.snapshot_weightings.loc[:, 'generators'] = [2, 3]
    n.snapshot_weightings.loc[:, 'objective'] = [2, 3]
    n.add('Carrier', 'fuel', co2_emissions=.3)
    n.add('Carrier', 'other', co2_emissions=0)
    n.add('Generator', 'fuel', bus='sink', carrier='fuel', p_nom=10,
          efficiency=.5, marginal_cost=20 if expensive else 1)
    n.add('Generator', 'other', bus='sink', carrier='other', p_nom=10,
          efficiency=.25, marginal_cost=1 if expensive else 20)
    n.add('GlobalConstraint', 'policy', type=kind, sense=sense,
          carrier_attribute='co2_emissions' if kind == 'primary_energy' else 'fuel',
          constant=constant)
    return n


def transmission_policy(kind, sense):
    n = Network()
    n.set_snapshots(['now'])
    n.add('Carrier', ['AC', 'DC', 'other'])
    for component, carrier, length, cost in [('Line', 'AC', 2, 5),
                                             ('Link', 'DC', 3, 7),
                                             ('Link', 'other', 11, 13)]:
        name = carrier
        n.add('Bus', [name+'-a', name+'-b'], v_nom=1)
        nominal = 's_nom' if component == 'Line' else 'p_nom'
        attrs = {nominal+'_extendable': True, nominal+'_max': 10,
                 'capital_cost': cost, 'length': length, 'carrier': carrier}
        if component == 'Line':
            attrs.update(x=.1, r=.01)
        n.add(component, name, bus0=name+'-a', bus1=name+'-b', **attrs)
        n.add('Generator', name+'-source', bus=name+'-a', p_nom=100, marginal_cost=1)
        n.add('Generator', name+'-backup', bus=name+'-b', p_nom=100, marginal_cost=100)
        n.add('Load', name, bus=name+'-b', p_set=6)
    # A fixed selected-carrier asset must not consume the expansion allowance.
    n.add('Bus', ['fixed-a', 'fixed-b'], v_nom=1)
    n.add('Link', 'fixed', bus0='fixed-a', bus1='fixed-b', carrier='DC',
          p_nom=50, length=17, capital_cost=19)
    n.add('Generator', 'fixed-source', bus='fixed-a', p_nom=1, marginal_cost=1)
    n.add('Load', 'fixed-load', bus='fixed-b', p_set=1)
    n.add('GlobalConstraint', 'policy', type=kind, carrier_attribute='AC, DC',
          sense=sense, constant=15 if kind == 'transmission_volume_expansion_limit' else 36)
    return n


def technology_policy(sense, limit, *, period=False):
    n = Network()
    n.set_snapshots(['now'])
    n.add('Carrier', ['target', 'other'])
    n.add('Bus', ['a', 'b'])
    if period:
        n.set_investment_periods([2030, 2040])
    for bus in ('a', 'b'):
        n.add('Load', bus, bus=bus, p_set=10)
        n.add('Generator', bus+'-backup', bus=bus, carrier='other',
              p_nom=100, marginal_cost=20)
        n.add('Generator', bus+'-fixed', bus=bus, carrier='target',
              p_nom=1, marginal_cost=0)
        if period:
            for year in (2030, 2040):
                n.add('Generator', f'{bus}-{year}', bus=bus, carrier='target',
                      p_nom_extendable=True, capital_cost=2, marginal_cost=1,
                      build_year=year, lifetime=10)
        else:
            n.add('Generator', bus+'-new', bus=bus, carrier='target',
                  p_nom_extendable=True, capital_cost=2,
                  marginal_cost=30 if sense == '>=' else 1)
    attrs = {'investment_period': 2040} if period else {}
    n.add('GlobalConstraint', 'policy', type='tech_capacity_expansion_limit',
          carrier_attribute='target', bus='a', sense=sense, constant=limit, **attrs)
    return n


def growth_policy(absolute, relative):
    n = dispatch_bus(30)
    n.set_investment_periods([2030, 2040, 2050])
    n.add('Carrier', 'limited', max_growth=absolute, max_relative_growth=relative)
    n.add('Carrier', 'free')
    n.add('Generator', 'backup', bus='sink', carrier='free', p_nom=100,
          marginal_cost=100)
    for name, year in [('early', 2025), ('middle', 2035), ('last', 2050)]:
        n.add('Generator', name, bus='sink', carrier='limited',
              build_year=year, lifetime=100, p_nom_extendable=True,
              capital_cost=1, marginal_cost=1)
    return n
