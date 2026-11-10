# feature: F04
"""Acceptance checks for network persistence and external electrical cases."""

import json
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import CRS
from shapely import from_wkt
from shapely.geometry import Polygon
from velmora import Network

from _helpers import invoke, run_command, isolated_site
from F04_helpers import (FORMATS, persistence_network, export_network, import_network,
                         read_persistence, independent_source, storage_static,
                         storage_curve, ppc_case)
from F04_helpers import distribution_network


def test_deterministic_formats_and_independent_default_sources(tmp_path):
    n = persistence_network()
    # Excel supports dictionaries and scalar metadata; see the ledger for lists.
    n.meta = {'study': {'label': 'persistence', 'revision': 3}, 'label': 'run'}
    for fmt, extension in FORMATS.items():
        path = tmp_path / ('export_' + fmt + extension)
        export_network(n, fmt, path)
        raw = read_persistence(path, fmt)
        represented = {
            'buses': {'west': {'v_nom': 110}, 'east': {'v_nom': 110}},
            'generators': {'supply': {'bus': 'west', 'p_nom': 37, 'efficiency': .75,
                                      'description': 'retained description'},
                           'curved': {'bus': 'west', 'p_nom': 19}},
            'loads': {'demand': {'bus': 'east', 'q_set': 2}},
            'lines': {'circuit': {'bus0': 'west', 'bus1': 'east', 'r': .2, 'x': .4, 's_nom': 100}},
            'transformers': {'coupler': {'bus0': 'west', 'bus1': 'east', 'x': .1, 's_nom': 23}},
            'links': {'converter': {'bus0': 'west', 'bus1': 'east', 'p_nom': 17, 'efficiency': .8}},
            'stores': {'reservoir': {'bus': 'west', 'e_nom': 29}},
            'storage_units': {'battery': {'bus': 'east', 'p_nom': 11, 'max_hours': 3}},
        }
        for component, assets in represented.items():
            stored = storage_static(raw, fmt, component)
            assert set(stored.index) == set(assets)
            for name, fields in assets.items():
                for field, expected in fields.items():
                    assert stored.at[name, field] == expected
        assert sorted(map(tuple, storage_curve(raw, fmt)[['p_pu', 'marginal_cost']].to_numpy())) == [
            (0.0, 0.0), (0.4, 12.0), (1.0, 31.0)]
        if fmt == 'netcdf':
            assert raw['loads_t_p_set'].sel(loads_t_p_set_i='demand').values.tolist() == [4, 9, 4, 9]
            assert raw['snapshots_period'].values.tolist() == [2030, 2030, 2040, 2040]
            assert raw['snapshots_objective'].values.tolist() == [2, 5, 2, 5]
            assert raw['investment_periods_years'].values.tolist() == [10, 12]
            assert json.loads(raw.attrs['meta']) == n.meta
        else:
            prefix = '/' if fmt == 'hdf5' else ''
            times = raw[prefix + 'snapshots']
            named = [level for level in times.index.names if level is not None]
            if named:
                times = times.reset_index(level=named)
            assert times['period'].tolist() == [2030, 2030, 2040, 2040]
            for field, values in [('objective', [2, 5, 2, 5]),
                                  ('generators', [3, 6, 3, 6]), ('stores', [4, 7, 4, 7])]:
                assert times[field].tolist() == values
            key = '/loads_t/p_set' if fmt == 'hdf5' else 'loads-p_set'
            column = 0 if fmt == 'hdf5' else 'demand'
            assert raw[key][column].tolist() == [4, 9, 4, 9]
        m = import_network(fmt, path)
        assert m.name == n.name
        assert m.meta == n.meta
        assert m.snapshots.tolist() == n.snapshots.tolist()
        pd.testing.assert_frame_equal(m.snapshot_weightings, n.snapshot_weightings,
                                       check_dtype=False, check_index_type=False, check_column_type=False, check_names=False, check_like=True, check_freq=False, check_frame_type=False)
        pd.testing.assert_frame_equal(m.investment_period_weightings,
                                       n.investment_period_weightings, check_dtype=False, check_index_type=False, check_column_type=False, check_names=False, check_like=True, check_freq=False, check_frame_type=False)
        for component, assets in represented.items():
            table = m.c[component].static
            assert set(table.index) == set(assets)
            for name, fields in assets.items():
                for field, expected in fields.items():
                    assert table.at[name, field] == expected
        assert m.c.loads.dynamic.p_set['demand'].tolist() == [4, 9, 4, 9]
        assert sorted(map(tuple, m.c.generators.piecewise['marginal_cost']['curved'][
            ['p_pu', 'marginal_cost']].to_numpy())) == [(0, 0), (.4, 12), (1, 31)]
        source = tmp_path / ('independent_' + fmt + extension)
        independent_source(source, fmt)
        imported = import_network(fmt, source)
        assert imported.c.buses.static.at['source', 'v_nom'] == 66
        assert imported.c.generators.static.at['plant', 'p_nom'] == 43
        assert imported.c.generators.static.at['plant', 'efficiency'] == 1
        assert imported.c.generators.static.at['plant', 'q_set'] == 0
        assert imported.c.generators.static.at['plant', 'active']
        assert not imported.c.generators.static.at['plant', 'p_nom_extendable']
        assert imported.c.loads.static.at['sink', 'q_set'] == 0
        assert imported.c.loads.static.at['sink', 'p_set'] == 0
        assert imported.c.loads.dynamic.p_set['sink'].tolist() == [6, 8]
        assert imported.snapshot_weightings['objective'].tolist() == [2, 3]


def test_netcdf_scenarios_shapes_and_separate_curves(tmp_path):
    n = persistence_network(curves=False)
    # Non-default CRS reload is broken in the baseline; see the ledger.
    polygon = Polygon([(0, 0), (2, 0), (2, 3), (0, 0)])
    n.add('Shape', 'region', geometry=polygon, component='Bus', idx='west')
    n.set_scenarios({'calm': .25, 'storm': .75})
    n.c.generators.static.at[('storm', 'supply'), 'p_nom'] = 51
    n.c.loads.dynamic.p_set.loc[:, ('storm', 'demand')] = [8, 13, 21, 34]
    path = tmp_path / 'scenarios.nc'
    n.export_to_netcdf(path)
    raw = read_persistence(path, 'netcdf')
    assert raw['scenario_weight'].sel(scenario=['calm', 'storm']).values.tolist() == [.25, .75]
    assert raw['generators_p_nom'].sel(scenario='storm', generators_i='supply').item() == 51
    for scenario, values in [('calm', [4, 9, 4, 9]), ('storm', [8, 13, 21, 34])]:
        assert raw['loads_t_p_set'].sel(scenario=scenario, loads_t_p_set_i='demand').values.tolist() == values
    assert CRS.from_wkt(json.loads(raw.attrs['crs'])['_crs']) == n.crs
    assert from_wkt(raw['shapes_geometry'].sel(scenario='calm', shapes_i='region').item()).equals(polygon)
    m = import_network('netcdf', path)
    assert m.crs == n.crs
    assert m.snapshots.tolist() == n.snapshots.tolist()
    pd.testing.assert_frame_equal(m.investment_period_weightings, n.investment_period_weightings,
                                   check_dtype=False, check_index_type=False, check_column_type=False, check_names=False, check_like=True, check_freq=False, check_frame_type=False)
    assert m.scenario_weightings.loc[['calm', 'storm'], 'weight'].tolist() == [.25, .75]
    assert m.c.generators.static.at[('storm', 'supply'), 'p_nom'] == 51
    for scenario, values in [('calm', [4, 9, 4, 9]), ('storm', [8, 13, 21, 34])]:
        assert m.c.loads.dynamic.p_set[(scenario, 'demand')].tolist() == values
        assert m.c.shapes.static.at[(scenario, 'region'), 'geometry'].equals(polygon)
    # Curves and scenarios are mutually exclusive; persist curves separately.
    curves = persistence_network()
    curve_path = tmp_path / 'curves.nc'
    curves.export_to_netcdf(curve_path)
    raw_curves = read_persistence(curve_path, 'netcdf')
    assert sorted(map(tuple, storage_curve(raw_curves, 'netcdf')[['p_pu', 'marginal_cost']].to_numpy())) == [(0, 0), (.4, 12), (1, 31)]
    restored = import_network('netcdf', curve_path)
    result = invoke(restored.set_scenarios, ['a', 'b'], expected_exceptions=(NotImplementedError,))
    assert isinstance(result.exception, NotImplementedError)
    result = invoke(m.add, 'Generator', 'new_curve', kwargs={
        'bus': 'west', 'marginal_cost': {0: 0, 1: 12}}, expected_exceptions=(NotImplementedError,))
    assert isinstance(result.exception, NotImplementedError)


def test_stochastic_export_refusal_after_live_deterministic_export(tmp_path):
    for fmt in ['csv_folder', 'hdf5', 'excel']:
        n = persistence_network(curves=False)
        path = tmp_path / ('valid_' + fmt + FORMATS[fmt])
        export_network(n, fmt, path)
        assert import_network(fmt, path).c.loads.dynamic.p_set['demand'].tolist() == [4, 9, 4, 9]
        stochastic = persistence_network(curves=False)
        stochastic.set_scenarios({'a': .2, 'b': .8})
        result = invoke(export_network, stochastic, fmt,
                        tmp_path / ('refused_' + fmt + FORMATS[fmt]),
                        expected_exceptions=(NotImplementedError,))
        assert isinstance(result.exception, NotImplementedError)


def test_optional_excel_support_in_isolated_interpreter(tmp_path):
    baseline = Network()
    baseline.add('Bus', 'independent', v_nom=66)
    valid = tmp_path / 'with_support.xlsx'
    baseline.export_to_excel(valid)
    assert pd.read_excel(valid, sheet_name='buses', index_col=0).at['independent', 'v_nom'] == 66
    # A real filesystem environment without the optional package; no import mocks.
    isolated = isolated_site(tmp_path / 'site', excluded={'openpyxl'},
                             product_spec=importlib.util.find_spec('velmora'))
    destination = tmp_path / 'optional.xlsx'
    observation = tmp_path / 'observation.json'
    script = '''
import sys, json, importlib.util
from pathlib import Path
sys.path = [sys.argv[1]] + [p for p in sys.path if 'site-packages' not in p and 'dist-packages' not in p]
assert importlib.util.find_spec('openpyxl') is None
from velmora import Network
n = Network()
n.add('Bus', 'independent', v_nom=66)
try:
    n.export_to_excel(sys.argv[2])
except ImportError as error:
    outcome = {'outcome': 'missing-support', 'message': str(error)}
else:
    outcome = {'outcome': 'written'}
Path(sys.argv[3]).write_text(json.dumps(outcome))
'''
    result = run_command([sys.executable, '-S', '-c', script, str(isolated), str(destination), str(observation)],
                         cwd=tmp_path, env={'PYTHONPATH': None})
    assert result.returncode == 0, result.stderr
    observed = json.loads(observation.read_text())
    if observed['outcome'] == 'written':
        # Implementations using another writer must still produce the real format.
        table = pd.read_excel(destination, sheet_name='buses', index_col=0, engine='openpyxl')
        assert table.at['independent', 'v_nom'] == 66
    else:
        assert observed['outcome'] == 'missing-support'
        assert observed['message']


def test_pypower_import_units_controls_and_power_flow():
    n = Network()
    n.import_from_pypower_ppc(ppc_case())
    assert n.c.buses.static.loc[['1', '2', '3'], 'v_nom'].tolist() == [110, 110, 20]
    assert n.c.buses.static.loc[['1', '2', '3'], 'control'].tolist() == ['Slack', 'PV', 'PQ']
    assert n.c.generators.static.loc[['G0', 'G1'], 'control'].tolist() == ['Slack', 'PV']
    assert n.c.generators.static.loc[['G0', 'G1'], 'p_nom'].tolist() == [80, 20]
    assert n.c.generators.static.loc[['G0', 'G1'], 'p_set'].tolist() == [0, 5]
    assert n.c.generators.static.loc[['G0', 'G1'], 'q_set'].tolist() == [0, 2]
    assert n.c.buses.static.loc[['1', '2'], 'v_mag_pu_set'].tolist() == [1.02, 1.01]
    assert n.c.loads.static.loc[['L0', 'L1'], 'p_set'].tolist() == [3, 12]
    assert n.c.loads.static.loc[['L0', 'L1'], 'q_set'].tolist() == [1, 4]
    line = n.c.lines.static.loc['L0']
    np.testing.assert_allclose(line[['r', 'x', 'b', 's_nom']].to_numpy(dtype=float),
                               [1.21, 4.84, .0001652892561983471, 70])
    transformer = n.c.transformers.static.loc['T0']
    np.testing.assert_allclose(transformer[['r', 'x', 'b', 's_nom', 'tap_ratio', 'phase_shift']].to_numpy(dtype=float),
                               [.002, .032, .025, 40, 1.05, 3])
    assert (line['bus0'], line['bus1']) == ('1', '2')
    assert (transformer['bus0'], transformer['bus1']) == ('2', '3')
    n.lpf()
    np.testing.assert_allclose(n.c.lines.dynamic.p0['L0'], [10])
    np.testing.assert_allclose(n.c.transformers.dynamic.p0['T0'], [12])
    np.testing.assert_allclose(n.c.generators.dynamic.p['G0'], [10])

    # Separate the classification predicates, which overlap in the first case.
    source = ppc_case()
    source['baseMVA'] = 50
    source['bus'][1, 2:6] = [0, 7, 2, -3]
    source['gen'][1, 0] = 3
    source['gen'][:, 7] = 0
    source['branch'] = np.array([
        [1, 2, .01, .04, .02, 0, 0, 0, 1, 0, 0, -360, 360],
        [1, 3, .01, .04, .02, 25, 25, 25, 0, 0, 0, -360, 360],
        [1, 2, .01, .04, .02, 30, 30, 30, 1.1, 0, 0, -360, 360],
        [1, 2, .01, .04, .02, 35, 35, 35, 1, 5, 0, -360, 360],
    ], dtype=float)
    converted = Network()
    converted.import_from_pypower_ppc(source)
    assert set(converted.c.lines.static.index) == {'L0'}
    assert set(converted.c.transformers.static.index) == {'T0', 'T1', 'T2'}
    np.testing.assert_allclose(
        converted.c.lines.static.loc['L0', ['r', 'x', 'b', 's_nom']].to_numpy(dtype=float),
        [2.42, 9.68, .00008264462809917356, 0])
    for name, expected in [
        ('T0', [.005, .02, .04, 25, 1, 0]),
        ('T1', [.006, .024, .03333333333333333, 30, 1.1, 0]),
        ('T2', [.007, .028, .02857142857142857, 35, 1, 5]),
    ]:
        np.testing.assert_allclose(converted.c.transformers.static.loc[
            name, ['r', 'x', 'b', 's_nom', 'tap_ratio', 'phase_shift']].to_numpy(dtype=float),
            expected)
    assert converted.c.transformers.static.loc['T0', ['bus0', 'bus1']].tolist() == ['1', '3']
    assert converted.c.generators.static.loc[['G0', 'G1'], 'control'].tolist() == ['Slack', 'PQ']
    assert converted.c.generators.static['active'].all()
    assert converted.c.lines.static['active'].all()
    assert converted.c.transformers.static['active'].all()
    assert converted.c.buses.static.at['3', 'v_mag_pu_set'] == 1.01
    assert converted.c.loads.static.loc[['L0', 'L1'], 'bus'].tolist() == ['2', '3']
    assert converted.c.loads.static.loc[['L0', 'L1'], 'p_set'].tolist() == [0, 12]
    assert converted.c.loads.static.loc[['L0', 'L1'], 'q_set'].tolist() == [7, 4]
    assert converted.c.shunt_impedances.static.at['S0', 'bus'] == '2'
    np.testing.assert_allclose(converted.c.shunt_impedances.static.loc['S0', ['g', 'b']].to_numpy(dtype=float),
                               [.00016528925619834712, -.00024793388429752067])
    replacement = Network()
    replacement.import_from_pypower_ppc(source, overwrite_zero_s_nom=91)
    assert replacement.c.lines.static.at['L0', 's_nom'] == 91
    assert replacement.c.transformers.static.loc[['T0', 'T1', 'T2'], 's_nom'].tolist() == [25, 30, 35]


def test_distribution_import_scaled_connected_typed_components(tmp_path):
    net = distribution_network(tmp_path / 'dependencies')
    n = Network()
    n.import_from_pandapower_net(net)
    assert set(n.c.buses.static.index) == {'high', 'low', 'demand'}
    np.testing.assert_allclose(n.c.buses.static.loc[
        ['high', 'low', 'demand'], 'v_nom'], [20, .4, .4])
    assert set(n.c.loads.static.index) == {'load'}
    assert n.c.loads.static.at['load', 'bus'] == 'demand'
    np.testing.assert_allclose(n.c.loads.static.loc['load', ['p_set', 'q_set']].to_numpy(dtype=float),
                               [.06, .03])
    assert set(n.c.generators.static.index) == {'regulated', 'injection', 'grid'}
    assert n.c.generators.static.loc[['regulated', 'injection', 'grid'], 'bus'].tolist() == [
        'high', 'demand', 'high']
    assert n.c.generators.static.loc[['regulated', 'injection', 'grid'], 'control'].tolist() == [
        'PV', 'PQ', 'Slack']
    np.testing.assert_allclose(n.c.generators.static.loc[
        ['regulated', 'injection'], ['p_set', 'q_set']], [[.005, 0], [.005, .001]])
    assert n.c.buses.static.at['high', 'v_mag_pu_set'] == 1.02
    assert set(n.c.shunt_impedances.static.index) == {'shunt'}
    assert n.c.shunt_impedances.static.at['shunt', 'bus'] == 'demand'
    np.testing.assert_allclose(n.c.shunt_impedances.static.loc[
        'shunt', ['g', 'b']].to_numpy(dtype=float), [.0125, -.0625])
    assert set(n.c.lines.static.index) == {'line'}
    assert n.c.lines.static.loc['line', ['bus0', 'bus1', 'type']].tolist() == [
        'low', 'demand', 'NAYY 4x50 SE']
    np.testing.assert_allclose(n.c.lines.static.loc[
        'line', ['length', 'num_parallel']].to_numpy(dtype=float), [.1, 2])
    assert set(n.c.transformers.static.index) == {'transformer'}
    assert n.c.transformers.static.loc['transformer', ['bus0', 'bus1', 'type']].tolist() == [
        'high', 'low', '0.4 MVA 20/0.4 kV']
    # A generator target survives when no external grid overrides it.
    net.gen.loc[:, 'bus'] = net.bus.index[1]
    target_only = Network()
    target_only.import_from_pandapower_net(net)
    assert target_only.c.buses.static.at['low', 'v_mag_pu_set'] == 1.04
    n.lpf()
    np.testing.assert_allclose(n.c.lines.dynamic.p0['line'], [.057], rtol=1e-7, atol=1e-10)
    np.testing.assert_allclose(n.c.transformers.dynamic.p0['transformer'], [.057], rtol=1e-7, atol=1e-10)
    np.testing.assert_allclose(n.c.generators.dynamic.p['grid'], [.052], rtol=1e-7, atol=1e-10)


def test_excel_import_ignores_unrelated_worksheets(tmp_path):
    path = tmp_path / 'independent.xlsx'
    independent_source(path, 'excel')
    with pd.ExcelWriter(path, engine='openpyxl', mode='a') as writer:
        pd.DataFrame({'remark': ['unrelated', 'not a component'], 'value': [17, 23]}).to_excel(
            writer, sheet_name='study_notes', index=False)
        pd.DataFrame({'entry': ['metadata for an analyst']}).to_excel(
            writer, sheet_name='overview', index=False)
    n = import_network('excel', path)
    assert set(n.c.buses.static.index) == {'source'}
    assert set(n.c.generators.static.index) == {'plant'}
    assert set(n.c.loads.static.index) == {'sink'}
    assert n.c.generators.static.at['plant', 'p_nom'] == 43
    assert n.c.buses.static.at['source', 'v_nom'] == 66
    assert n.snapshots.tolist() == [0, 1]
    assert n.c.loads.dynamic.p_set['sink'].tolist() == [6, 8]
    assert n.snapshot_weightings['objective'].tolist() == [2, 3]


def test_optional_hdf5_support_in_isolated_interpreter(tmp_path):
    baseline = Network()
    baseline.add('Bus', 'independent', v_nom=66)
    valid = tmp_path / 'with_support.h5'
    baseline.export_to_hdf5(valid)
    with pd.HDFStore(valid, mode='r') as stored:
        assert stored['/buses'].set_index('name').at['independent', 'v_nom'] == 66
    isolated = isolated_site(tmp_path / 'site', excluded={'tables'},
                             product_spec=importlib.util.find_spec('velmora'))
    destination = tmp_path / 'optional.h5'
    observation = tmp_path / 'observation.json'
    script = """
import sys, json, importlib.util
from pathlib import Path
sys.path = [sys.argv[1]] + [p for p in sys.path if 'site-packages' not in p and 'dist-packages' not in p]
assert importlib.util.find_spec('tables') is None
from velmora import Network
n = Network()
n.add('Bus', 'independent', v_nom=66)
try:
    n.export_to_hdf5(sys.argv[2])
except ImportError as error:
    outcome = {'outcome': 'missing-support', 'message': str(error)}
else:
    outcome = {'outcome': 'written'}
Path(sys.argv[3]).write_text(json.dumps(outcome))
"""
    result = run_command([sys.executable, '-S', '-c', script, str(isolated),
                          str(destination), str(observation)], cwd=tmp_path,
                         env={'PYTHONPATH': None})
    assert result.returncode == 0, result.stderr
    observed = json.loads(observation.read_text())
    if observed['outcome'] == 'written':
        with pd.HDFStore(destination, mode='r') as stored:
            assert stored['/buses'].set_index('name').at['independent', 'v_nom'] == 66
    else:
        assert observed['outcome'] == 'missing-support'
        assert observed['message']
