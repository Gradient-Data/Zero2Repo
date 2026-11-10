# feature: F20
"""Acceptance checks for geographic maps and statistical charts."""
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba, Normalize
from matplotlib import colormaps
from matplotlib.collections import PatchCollection
from matplotlib.legend import Legend
import numpy as np
import pandas as pd
from velmora.consistency import ConsistencyError
from _helpers import invoke
from F06_helpers import assert_close
from F20_helpers import (
    styled_solution, expanded_solution, geographic_solution,
    styled_network, geographic_input, labeled_collection, capacity_values,
    chart_table, public_layers, colored_paths, sector_share, polygon_centroid, marker_area,
    distribution_points, histogram_regions,
)


def test_static_geographic_map(geographic_input):
    n = geographic_input
    for snapshot in n.snapshots:
        fig, ax = plt.subplots()
        kwargs = {}
        for component, prefix, width, color in [
            ('Line', 'line', 2., '#e04020'),
            ('Transformer', 'transformer', 3., '#208040'),
            ('Link', 'link', 4., '#2060d0'),
        ]:
            kwargs.update({prefix+'_flow': snapshot, prefix+'_width': width, prefix+'_color': color})
        result = n.plot(ax=ax, geomap=False, bus_size=pd.Series([.04,.09,.16,.25], index=n.c.buses.static.index),
                        auto_scale_branches=True, **kwargs)
        for component, prefix, width, color in [
            ('Line', 'line', 2., '#e04020'), ('Transformer', 'transformer', 3., '#208040'),
            ('Link', 'link', 4., '#2060d0'),
        ]:
            branch = result['branches'][component]
            row = n.components[component].static.loc[prefix]
            coords = n.c.buses.static.loc[[row.bus0,row.bus1], ['x','y']].to_numpy()
            assert_close(branch.get_segments(), [coords])
            assert_close(branch.get_linewidths(), [width])
            assert_close(branch.get_colors(), [to_rgba(color)])
            flow = n.components[component].dynamic.p0.at[snapshot,prefix]
            assert abs(flow) > 0
            vertices = result['flows'][component].get_paths()[0].vertices
            # All three branches are horizontal: the arrow tip is the furthest
            # point from its tail along the direction of actual solved flow.
            start, end = coords[:,0]
            if flow < 0:
                start, end = end, start
            tip = vertices[:,0].max() if flow > 0 else vertices[:,0].min()
            assert min(start,end) < tip < max(start,end)
            assert abs(tip-start) > abs(polygon_centroid(vertices)[0]-start)
        buses = result['nodes']['Bus'].get_paths()
        centers = {(round(p.vertices[:,0].min()+p.vertices[:,0].max(),6)/2,
                    round(p.vertices[:,1].min()+p.vertices[:,1].max(),6)/2):
                   marker_area(p) for p in buses}
        # Filled area is proportional to quantity independently of marker shape.
        areas = []
        for bus in n.c.buses.static.index:
            xy = tuple(n.c.buses.static.loc[bus,['x','y']])
            areas.append(centers[xy])
        assert_close(np.asarray(areas)/areas[0], np.array([.04,.09,.16,.25])/.04)
        plt.close(fig)
    # A zero quantity has zero filled area; other markers retain positive area.
    fig,ax=plt.subplots()
    result=n.plot(ax=ax,geomap=False,bus_size=pd.Series([0.,.09,.16,.25],index=n.c.buses.static.index))
    zero_areas = [marker_area(p) for p in result['nodes']['Bus'].get_paths()
                  if np.isclose(p.vertices[:,0].min()+p.vertices[:,0].max(), 0)]
    assert all(area < 1e-9 for area in zero_areas)
    assert sum(marker_area(p) > 0 for p in result['nodes']['Bus'].get_paths()) == 3
    plt.close(fig)
    # Composition uses real capacities; compare angular shares by colour.
    sizes = pd.Series([3.,9.],index=pd.MultiIndex.from_tuples([('a','AC'),('a','dc')]))
    fig,ax=plt.subplots()
    result=n.plot(ax=ax,geomap=False,bus_size=sizes)
    sectors = colored_paths(result['nodes']['Bus'])
    assert len(sectors) == 2
    assert {tuple(color) for _, color in sectors} == {to_rgba(n.c.carriers.static.at[carrier, 'color']) for carrier in ['AC', 'dc']}
    for vertices,color in sectors:
        fraction = sector_share(vertices, [0., 45.])
        expected=.25 if np.allclose(color,to_rgba('#e04020')) else .75
        assert_close(fraction,expected)
    plt.close(fig)
    fig,ax=plt.subplots()
    numeric=pd.Series([0.,.25,.75,1.],index=n.c.buses.static.index)
    result=n.plot(ax=ax,geomap=False,bus_color=numeric,bus_cmap='viridis',
                  bus_cmap_norm=Normalize(0,1))
    expected = {tuple(n.c.buses.static.loc[bus, ['x', 'y']]): colormaps['viridis'](value)
                for bus, value in numeric.items()}
    observed = set()
    for vertices, color in colored_paths(result['nodes']['Bus']):
        center = tuple(np.round((vertices[:, :2].min(axis=0) + vertices[:, :2].max(axis=0)) / 2, 6))
        assert center in expected and center not in observed
        observed.add(center)
        assert_close(color, expected[center])
    assert observed == set(expected)
    plt.close(fig)


def test_interactive_geographic_map(geographic_input):
    n=geographic_input
    for snapshot in n.snapshots:
        opts={}
        for component,prefix in [('Line','line'),('Transformer','transformer'),('Link','link')]:
            opts[prefix+'_flow']=n.components[component].dynamic.p0.loc[snapshot]
            opts[prefix+'_width']=pd.Series(3.,index=[prefix])
            opts[prefix+'_color']='#2060d0'
        deck=n.explore(tooltip=False,bus_size=pd.Series([1.,4.,9.,16.],index=n.c.buses.static.index),
                       bus_alpha=1, bus_color='#e04020', **opts)
        records=[r for layer in public_layers(deck,'PathLayer') for r in layer.data]
        assert {r['name'] for r in records}=={'line','transformer','link'}
        for r in records:
            coords=n.c.buses.static.loc[[r['bus0'],r['bus1']],['x','y']].to_numpy()
            assert_close(r['path'],coords)
            assert_close(r['width'],3.)
            assert_close(r['rgba'][:3],[32,96,208])
        busrecords=[r for layer in public_layers(deck,'ScatterplotLayer') for r in layer.data]
        assert {(r['x'],r['y'],r['size']) for r in busrecords}=={(0.,45.,1.),(5.,45.,4.),(10.,45.,9.),(15.,45.,16.)}
        arrows=[r for layer in public_layers(deck,'PolygonLayer') for r in layer.data]
        assert {r['name'] for r in arrows}=={'line','transformer','link'}
        for r in arrows:
            component={'line':'Line','transformer':'Transformer','link':'Link'}[r['name']]
            flow=n.components[component].dynamic.p0.at[snapshot,r['name']]
            assert np.sign(r['flow_pdk'])==np.sign(flow)
            arrow=np.asarray(r['arrow'])
            assert np.ptp(arrow[:,0])>0
            # For a triangular arrow, the tip lies beyond the centroid in the
            # directed half of its bounding box; vertex order is irrelevant.
            midpoint=(arrow[:,0].min()+arrow[:,0].max())/2
            assert np.sign(midpoint-polygon_centroid(arrow)[0])==np.sign(flow)
    sizes=pd.Series([3.,9.],index=pd.MultiIndex.from_tuples([('a','AC'),('a','dc')]))
    deck=n.explore(tooltip=False,bus_size=sizes,bus_alpha=1)
    pies=[r for layer in public_layers(deck,'PolygonLayer') for r in layer.data if 'label' in r]
    assert {(r['label'],r['size']) for r in pies}=={('AC',3.),('dc',9.)}
    for r in pies:
        assert_close(r['color'],[round(v*255) for v in to_rgba(n.c.carriers.static.at[r['label'],'color'])])
        assert len(r['polygon'])>3
        # Sector polygon: centre, arc vertices, centre; its angular span in local
        # metric coordinates around the centre is the carrier's share (3/12, 9/12).
        polygon=np.asarray(r['polygon'],dtype=float)
        center=polygon[0]; arc=polygon[1:-1]-center
        arc[:,0]*=np.cos(np.radians(center[1]))
        angles=np.unwrap(np.arctan2(arc[:,1],arc[:,0]))
        assert_close(abs(angles[-1]-angles[0])/(2*np.pi),r['size']/12.,atol=1e-3)


def test_static_statistical_charts(styled_network, labeled_collection):
    n=styled_network
    collection=labeled_collection
    for product in [n,collection]:
        for kind in ['bar','line','scatter','box','violin','histogram']:
            opts=dict(components=['Generator','Link'],x='carrier',y='value',color='carrier')
            if product is collection:
                opts['facet_col']='case'
            fig,axes,grid=getattr(product.statistics.installed_capacity.plot,kind)(**opts)
            expected=capacity_values()
            keys=['carrier']
            if product is collection:
                expected={(case,carrier):value for case in ['base','expanded']
                          for carrier,value in capacity_values(case=='expanded').items()}
                keys=['case','carrier']
            chart_table(grid,expected,keys)
            assert 'Installed Capacity [MW]' in {ax.get_ylabel() for ax in np.asarray(axes).reshape(-1)}
            for ax in np.asarray(axes).reshape(-1):
                assert len(ax.lines)+len(ax.patches)+len(ax.collections)>0
            if kind=='line':
                for case,ax in (grid.axes_dict.items() if product is collection else [('base',axes)]):
                    points=sorted(float(y) for line in ax.lines for y in line.get_ydata())
                    assert_close(points,sorted(capacity_values(case=='expanded').values()))
                    palette={to_rgba(n.c.carriers.static.at[c,'color']) for c in ['fuel','wire','convert']}
                    used={to_rgba(line.get_color()) for line in ax.lines if len(line.get_ydata())}
                    assert used==palette
            if kind=='scatter':
                for case,ax in (grid.axes_dict.items() if product is collection else [('base',axes)]):
                    points=sorted(float(row[1]) for artist in ax.collections for row in artist.get_offsets())
                    assert_close(points,sorted(capacity_values(case=='expanded').values()))
            if kind in ['box', 'violin']:
                for case, ax in (grid.axes_dict.items() if product is collection else [('base', axes)]):
                    # Each category has one observation, so every distribution
                    # collapses at its input value regardless of its styling.
                    points = distribution_points(ax)
                    expected_values = capacity_values(case == 'expanded')
                    labels = [tick.get_text() for tick in ax.get_xticklabels()]
                    positions = ax.get_xticks()
                    observed = set()
                    assert len(points)
                    for x, value in points:
                        label = labels[int(np.argmin(np.abs(positions - x)))]
                        assert label in expected_values
                        assert_close(value, expected_values[label])
                        observed.add(label)
                    assert observed == set(expected_values)
            if kind == 'histogram':
                for case, ax in (grid.axes_dict.items() if product is collection else [('base', axes)]):
                    labels = [tick.get_text() for tick in ax.get_xticklabels()]
                    positions = ax.get_xticks()
                    observed = {}
                    for vertices, count in histogram_regions(ax):
                        center = (vertices[:, 0].min() + vertices[:, 0].max()) / 2
                        label = labels[int(np.argmin(np.abs(positions - center)))]
                        value = capacity_values(case == 'expanded')[label]
                        assert vertices[:, 1].min() <= value <= vertices[:, 1].max()
                        if count is not None:
                            assert_close(count, 1.)
                        observed[label] = observed.get(label, 0) + 1
                    assert observed == {label: 1. for label in capacity_values()}
            if kind=='bar':
                for case,ax in (grid.axes_dict.items() if product is collection else [('base',axes)]):
                    labels = [tick.get_text() for tick in ax.get_xticklabels()]
                    positions = ax.get_xticks()
                    observed = {}
                    for patch in ax.patches:
                        center = patch.get_x() + patch.get_width() / 2
                        label = labels[int(np.argmin(np.abs(positions - center)))]
                        assert label not in observed
                        observed[label] = patch.get_height()
                    assert set(observed) == set(capacity_values())
                    for label, expected_height in capacity_values(case == 'expanded').items():
                        assert_close(observed[label], expected_height)
            plt.close(fig)
        fig,axes,grid=product.statistics.supply.plot.area(components=['Generator'],**({'facet_col':'case'} if product is collection else {}))
        expected={('Fuel display','first'):10.,('Fuel display','second'):12.,('Fuel display','third'):13.,
                  ('Wire display','first'):5.,('Wire display','second'):6.,('Wire display','third'):3.}
        keys=['carrier','snapshot']
        if product is collection:
            expected={(case,*key):value*(2 if case=='expanded' and key[0]=='Fuel display' else 1)
                      for case in ['base','expanded'] for key,value in expected.items()}
            keys=['case','carrier','snapshot']
        chart_table(grid,expected,keys)
        for case,ax in (grid.axes_dict.items() if product is collection else [('base',axes)]):
            assert len(ax.collections)>0
            # Supplied carrier colours fill the stacked areas.
            fills={tuple(np.round(color,6)) for artist in ax.collections for color in artist.get_facecolors()}
            assert fills=={tuple(np.round(to_rgba(n.c.carriers.static.at[c,'color']),6)) for c in ['fuel','wire']}
            positions=dict(zip([t.get_text() for t in ax.get_xticklabels()],ax.get_xticks(),strict=True))
            paths=[path.vertices for artist in ax.collections for path in artist.get_paths()]
            for snapshot,total in zip(n.snapshots,([25.,30.,29.] if case=='expanded' else [15.,18.,16.]),strict=True):
                x=positions[snapshot]
                tops=[vertices[np.isclose(vertices[:,0],x),1] for vertices in paths]
                assert_close(max(np.max(values) for values in tops if len(values)),total)
        plt.close(fig)
    # A real query must change both the data and the plotted categories.
    fig,ax,grid=n.statistics.installed_capacity.plot.bar(components=['Generator','Link'],query='value > 40')
    chart_table(grid,{'Fuel display':60.,'Wire display':54.},['carrier'])
    assert {t.get_text() for t in ax.get_yticklabels()}=={'Fuel display','Wire display'}
    plt.close(fig)
    n.c.generators.static.loc['gb','carrier']='heat'
    fig,ax=n.statistics.installed_capacity.plot.map(geomap=False,carrier=['fuel','heat'],bus_carrier='AC')
    legends=[a for a in fig.get_children() if isinstance(a,Legend)]
    labels={t.get_text() for legend in legends for t in legend.get_texts()}
    assert {'Fuel display','Heat display'} <= labels
    areas={}
    for artist in ax.collections:
        if isinstance(artist,PatchCollection):
            paths, colors = artist.get_paths(), artist.get_facecolors()
            for path, color in zip(paths, colors, strict=True):
                for carrier in ['fuel','heat']:
                    if np.allclose(color,to_rgba(n.c.carriers.static.at[carrier,'color'])):
                        areas[carrier] = marker_area(path)
    assert set(areas)=={'fuel','heat'}
    assert_close(areas['fuel']/areas['heat'], 60./50.)
    plt.close(fig)


def test_interactive_statistical_charts(styled_network, labeled_collection):
    n=styled_network
    collection=labeled_collection
    for product in [n,collection]:
        for kind in ['bar','line']:
            opts=dict(components=['Generator','Link'],x='carrier',y='value',color='carrier')
            if product is collection:
                # Explicit order makes facet identity part of the requested shell.
                opts.update(facet_col='case',col_order=['base','expanded'])
            fig=getattr(product.statistics.installed_capacity.iplot,kind)(**opts)
            actual={}
            for trace in fig.data:
                assert trace.type==('bar' if kind=='bar' else 'scatter')
                for category,value in zip(trace.x,trace.y,strict=True):
                    actual[(trace.xaxis,category)]=value
            expected={('x',label):value for label,value in capacity_values().items()}
            if product is collection:
                expected.update({('x2',label):value for label,value in capacity_values(True).items()})
                assert {a.text for a in fig.layout.annotations}=={'case=base','case=expanded'}
            assert set(actual)==set(expected)
            for key,value in expected.items():
                assert_close(actual[key],value)
            assert fig.layout.yaxis.title.text=='Installed Capacity [MW]'
        fig=product.statistics.supply.iplot.area(components=['Generator'],x='snapshot',y='value',color='carrier',
                   **({'facet_col':'case','col_order':['base','expanded']} if product is collection else {}))
        actual={}
        for trace in fig.data:
            assert trace.type=='scatter'
            for snapshot,value in zip(trace.x,trace.y,strict=True):
                if np.isfinite(value):
                    actual[(trace.xaxis,trace.name,snapshot)]=value
                    assert trace.stackgroup=='positive'
        expected={}
        for axis,factor in ([('x',1),('x2',2)] if product is collection else [('x',1)]):
            for carrier,values in [('Fuel display',[10.,12.,13.]),('Wire display',[5.,6.,3.])]:
                for snapshot,value in zip(n.snapshots,values,strict=True):
                    expected[(axis,carrier,snapshot)]=value*(factor if carrier=='Fuel display' else 1)
        assert actual==expected


def test_strict_missing_carrier_colors(styled_network):
    n=styled_network
    n.c.carriers.static.loc[['fuel','wire'],'color']=''
    for entry,kwargs in [(n.consistency_check_plots,{'strict':['missing_carrier_colors']}),
                         (n.statistics.installed_capacity.plot.bar,{'components':['Generator']})]:
        result=invoke(entry,kwargs=kwargs,expected_exceptions=(ConsistencyError,))
        assert isinstance(result.exception,ConsistencyError)
    # Supplying only some of the missing colours is still refused.
    n.c.carriers.static.loc['fuel','color']='#117733'
    result=invoke(n.consistency_check_plots,kwargs={'strict':['missing_carrier_colors']},
                  expected_exceptions=(ConsistencyError,))
    assert isinstance(result.exception,ConsistencyError)
    n.c.carriers.static.loc[['fuel','wire'],'color']=['#117733','#ee9900']
    n.consistency_check_plots(strict=['missing_carrier_colors'])
    fig,ax,grid=n.statistics.installed_capacity.plot.bar(components=['Generator'],x='carrier',y='value')
    chart_table(grid,{'Fuel display':60.,'Wire display':50.},['carrier'])
    tick_positions = ax.get_xticks()
    tick_labels = [tick.get_text() for tick in ax.get_xticklabels()]
    heights_by_label = {}
    for patch in ax.patches:
        center = patch.get_x() + patch.get_width() / 2
        label_index = int(np.argmin(np.abs(tick_positions - center)))
        heights_by_label[tick_labels[label_index]] = patch.get_height()
    assert set(heights_by_label) == {'Fuel display', 'Wire display'}
    for label, expected_height in {'Fuel display': 60., 'Wire display': 50.}.items():
        assert_close(heights_by_label[label], expected_height)
    plt.close(fig)
