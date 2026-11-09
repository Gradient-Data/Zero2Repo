# feature: F04
"""Persistence inputs and direct readers for the public storage formats."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from velmora import Network

from F03_helpers import electrical_pair

FORMATS = {'csv_folder': '', 'netcdf': '.nc', 'hdf5': '.h5', 'excel': '.xlsx'}


def persistence_network(*, curves=True):
    n = electrical_pair()
    n.name = 'retained network'
    n.meta = {'study': {'label': 'persistence', 'revision': 3}, 'tags': ['a', 'b']}
    n.set_snapshots(pd.date_range('2030-01-01', periods=2, freq='h'))
    n.add('Generator', 'supply', bus='west', p_nom=37, efficiency=0.75,
          description='retained description')
    n.add('Load', 'demand', bus='east', p_set=[4, 9], q_set=2)
    n.add('Store', 'reservoir', bus='west', e_nom=29)
    n.add('StorageUnit', 'battery', bus='east', p_nom=11, max_hours=3)
    n.add('Link', 'converter', bus0='west', bus1='east', p_nom=17, efficiency=0.8)
    n.add('Transformer', 'coupler', bus0='west', bus1='east', s_nom=23, x=0.1)
    if curves:
        n.add('Generator', 'curved', bus='west', p_nom=19,
              marginal_cost={0.0: 0, 0.4: 12, 1.0: 31})
    n.snapshot_weightings.loc[:, ['objective', 'generators', 'stores']] = [[2, 3, 4], [5, 6, 7]]
    n.set_investment_periods([2030, 2040])
    n.investment_period_weightings.loc[:, ['objective', 'years']] = [[0.9, 10], [0.7, 12]]
    return n


def export_network(n, fmt, path):
    getattr(n, 'export_to_' + fmt)(path)


def import_network(fmt, path):
    n = Network()
    getattr(n, 'import_from_' + fmt)(path)
    return n


def read_persistence(path, fmt):
    """Fully read named storage carriers with independent format libraries."""
    if fmt == 'netcdf':
        with xr.open_dataset(path) as ds:
            return ds.load()
    if fmt == 'csv_folder':
        result = {p.stem: pd.read_csv(p, index_col=0,
                  header=[0, 1] if p.stem.endswith('-pw') else 0)
                  for p in Path(path).glob('*.csv')}
        result['meta'] = json.loads((Path(path) / 'meta.json').read_text())
        return result
    if fmt == 'excel':
        return pd.read_excel(path, sheet_name=None, engine='openpyxl')
    with pd.HDFStore(path, mode='r') as store:
        return {key: store[key] for key in store.keys()}


def independent_source(path, fmt):
    """Write a small network directly, omitting all default-valued attributes."""
    buses = pd.DataFrame({'v_nom': [66.0]}, index=pd.Index(['source'], name='name'))
    gens = pd.DataFrame({'bus': ['source'], 'p_nom': [43.0]},
                        index=pd.Index(['plant'], name='name'))
    loads = pd.DataFrame({'bus': ['source']}, index=pd.Index(['sink'], name='name'))
    snapshots = pd.DataFrame({'snapshot': [0, 1], 'objective': [2.0, 3.0],
                              'generators': [1.0, 1.0], 'stores': [1.0, 1.0]})
    series = pd.DataFrame({'sink': [6.0, 8.0]})
    tables = {'buses': buses, 'generators': gens, 'loads': loads,
              'snapshots': snapshots, 'loads-p_set': series}
    if fmt == 'csv_folder':
        path.mkdir()
        for name, table in tables.items():
            table.to_csv(path / (name + '.csv'))
    elif fmt == 'excel':
        with pd.ExcelWriter(path, engine='openpyxl') as writer:
            for name, table in tables.items():
                table.to_excel(writer, sheet_name=name)
    elif fmt == 'hdf5':
        with pd.HDFStore(path, mode='w') as store:
            store.put('/network', pd.DataFrame(index=pd.Index(['independent'], name='name')).reset_index())
            for name, table in [('buses', buses), ('generators', gens), ('loads', loads)]:
                store.put('/' + name, table.reset_index(), format='table')
            store.put('/snapshots', snapshots, format='table')
            store.put('/loads_t/p_set', series.set_axis([0], axis=1), format='table')
    else:
        ds = xr.Dataset({
            'buses_v_nom': ('buses_i', [66.0]),
            'generators_bus': ('generators_i', ['source']),
            'generators_p_nom': ('generators_i', [43.0]),
            'loads_bus': ('loads_i', ['source']),
            'snapshots_snapshot': ('snapshots', [0, 1]),
            'snapshots_objective': ('snapshots', [2.0, 3.0]),
            'snapshots_generators': ('snapshots', [1.0, 1.0]),
            'snapshots_stores': ('snapshots', [1.0, 1.0]),
            'loads_t_p_set': (('snapshots', 'loads_t_p_set_i'), [[6.0], [8.0]]),
        }, coords={'buses_i': ['source'], 'generators_i': ['plant'],
                   'loads_i': ['sink'], 'loads_t_p_set_i': ['sink'], 'snapshots': [0, 1]})
        ds.to_netcdf(path)


def ppc_case():
    """Explicit PYPOWER v2 input with a line and a voltage-changing transformer."""
    gen = np.zeros((2, 21))
    gen[:, :10] = [[1, 0, 0, 100, -100, 1.02, 100, 1, 80, 0],
                   [2, 5, 2, 30, -30, 1.01, 100, 1, 20, 0]]
    return {'version': '2', 'baseMVA': 100.0, 'gen': gen,
            'bus': np.array([[1, 3, 0, 0, 0, 0, 1, 1, 0, 110, 1, 1.1, 0.9],
                             [2, 2, 3, 1, 0, 0, 1, 1, 0, 110, 1, 1.1, 0.9],
                             [3, 1, 12, 4, 0, 0, 1, 1, 0, 20, 1, 1.1, 0.9]], dtype=float),
            'branch': np.array([[1, 2, .01, .04, .02, 70, 70, 70, 0, 0, 1, -360, 360],
                                [2, 3, .005, .08, .01, 40, 40, 40, 1.05, 3, 1, -360, 360]], dtype=float)}


def storage_static(data, fmt, component):
    if fmt == 'netcdf':
        names = data.coords[component + '_i'].values
        prefix = component + '_'
        return pd.DataFrame({str(key)[len(prefix):]: value.values
                             for key, value in data.data_vars.items()
                             if value.dims == (component + '_i',)}, index=names)
    if fmt == 'csv_folder':
        return data[component]
    if fmt == 'hdf5':
        return data['/' + component].set_index('name')
    return data[component].set_index('name')


def storage_curve(data, fmt):
    if fmt == 'netcdf':
        array = data['generators_pw_marginal_cost'].sel(
            generators_pw_marginal_cost_i='curved')
        return pd.DataFrame({attr: array.sel(generators_pw_marginal_cost_attr_i=attr).values
                             for attr in ['p_pu', 'marginal_cost']})
    if fmt == 'csv_folder':
        return data['generators-marginal_cost-pw']['curved']
    if fmt == 'hdf5':
        return data['/generators_p/marginal_cost'].unstack('attribute').xs('curved', level='name')
    return data['generators-marginal_cost-pw'].pivot(
        index='breakpoint', columns='attribute', values='curved')


def distribution_network(dependency_directory):
    """Construct real external input using unmodified upstream PyPI wheels."""
    import subprocess
    import sys

    # The wheels are fetched from PyPI with the hidden tests (test_assets.json).
    wheels = sorted((Path(__file__).parent / 'F04_wheels').glob('*.whl'))
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps',
                    '--no-compile', '--disable-pip-version-check', '--target',
                    str(dependency_directory), *map(str, wheels)], check=True)
    sys.path.insert(0, str(dependency_directory))
    try:
        import pandapower as pp
        net = pp.create_empty_network()
        high = pp.create_bus(net, vn_kv=20, name='high')
        low = pp.create_bus(net, vn_kv=.4, name='low')
        demand = pp.create_bus(net, vn_kv=.4, name='demand')
        pp.create_ext_grid(net, high, vm_pu=1.02, name='grid')
        pp.create_gen(net, high, p_mw=.01, vm_pu=1.04, scaling=.5, name='regulated')
        pp.create_sgen(net, demand, p_mw=.02, q_mvar=.004, scaling=.25, name='injection')
        pp.create_load(net, demand, p_mw=.1, q_mvar=.05, scaling=.6, name='load')
        pp.create_shunt(net, demand, q_mvar=.01, p_mw=.002, vn_kv=.4, name='shunt')
        pp.create_transformer(net, high, low, std_type='0.4 MVA 20/0.4 kV', name='transformer')
        pp.create_line(net, low, demand, length_km=.1, std_type='NAYY 4x50 SE',
                       parallel=2, name='line')
        return net
    finally:
        sys.path.remove(str(dependency_directory))
