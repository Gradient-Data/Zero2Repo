# feature: F20
"""Real plotting workloads and public graphical observations."""
import matplotlib
matplotlib.use('Agg')
import numpy as np
import pandas as pd
import pytest
from velmora import Network, NetworkCollection
from matplotlib.path import Path
from matplotlib.collections import PathCollection
from F06_helpers import solve_dispatch, assert_close, detached_solution
from F19_helpers import statistics_grid


def styled_statistics(expanded=False):
    n = statistics_grid(solve=False)
    n.c.generators.static.loc['gb', 'carrier'] = 'wire'
    colors = ['#123456', '#654321', '#556677', '#ee9900', '#2299aa', '#779922']
    for carrier, color in zip(n.c.carriers.static.index, colors, strict=True):
        n.c.carriers.static.loc[carrier, ['color', 'nice_name']] = [color, carrier.title() + ' display']
    n.c.buses.static.loc[:, 'x'] = [10., 13., 13.]
    n.c.buses.static.loc[:, 'y'] = [50., 50., 53.]
    if expanded:
        n.c.generators.static.loc['ga', 'p_nom'] = 90.
        # Changed demand and capacity require their own real optimisation.
        n.c.loads.dynamic.p_set.loc[:, 'la'] += [10., 12., 13.]
    solve_dispatch(n)
    return n


def geographic_network():
    n = Network()
    n.set_snapshots(['forward', 'reverse'])
    n.add('Carrier', ['AC', 'dc'], color=['#e04020', '#2060d0'],
          nice_name=['Alternating supply', 'Direct transfer'])
    n.add('Bus', ['a', 'b', 'c', 'd'], x=[0., 5., 10., 15.],
          y=[45., 45., 45., 45.], v_nom=1, carrier='AC')
    n.add('Line', 'line', bus0='a', bus1='b', x=.1, s_nom=100)
    n.add('Transformer', 'transformer', bus0='b', bus1='c', x=.1, s_nom=100)
    n.add('Link', 'link', bus0='c', bus1='d', p_nom=100, p_min_pu=-1,
          efficiency=1, carrier='dc')
    n.add('Generator', 'west', bus='a', carrier='AC', p_nom=100, marginal_cost=[1., 20.])
    n.add('Generator', 'east', bus='d', carrier='AC', p_nom=100, marginal_cost=[20., 1.])
    n.add('Load', 'west demand', bus='a', carrier='AC', p_set=2.)
    n.add('Load', 'east demand', bus='d', carrier='AC', p_set=3.)
    n.add('Load', 'middle', bus='b', carrier='AC', p_set=[8., 12.])
    n.add('Load', 'other', bus='c', carrier='AC', p_set=[4., 6.])
    solve_dispatch(n)
    return n


@pytest.fixture(scope='module')
def styled_solution(tmp_path_factory):
    return detached_solution(styled_statistics(),
                             tmp_path_factory.mktemp('styled') / 'solved.nc')


@pytest.fixture(scope='module')
def expanded_solution(tmp_path_factory):
    return detached_solution(styled_statistics(expanded=True),
                             tmp_path_factory.mktemp('expanded') / 'solved.nc')


@pytest.fixture(scope='module')
def geographic_solution(tmp_path_factory):
    return detached_solution(geographic_network(),
                             tmp_path_factory.mktemp('geographic') / 'solved.nc')


@pytest.fixture
def styled_network(styled_solution):
    return styled_solution.copy()


@pytest.fixture
def geographic_input(geographic_solution):
    return geographic_solution.copy()


@pytest.fixture
def labeled_collection(styled_network, expanded_solution):
    # Preserve member identity inside each test, while isolating other tests.
    return NetworkCollection([styled_network, expanded_solution.copy()],
                             index=pd.Index(['base', 'expanded'], name='case'))


def capacity_values(expanded=False):
    return {'Fuel display': 90. if expanded else 60., 'Wire display': 54., 'Convert display': 30.}


def chart_table(grid, expected, keys):
    table = grid.data
    actual = table.set_index(keys)['value'].to_dict()
    assert set(actual) == set(expected)
    for key, value in expected.items():
        assert_close(actual[key], value)


def path_in_data(ax, artist, path):
    """Read drawn vertices in axis data coordinates, excluding close sentinels."""
    mask = np.ones(len(path.vertices), dtype=bool) if path.codes is None else ~np.isin(
        path.codes, [Path.STOP, Path.CLOSEPOLY])
    return (artist.get_transform() - ax.transData).transform(path.vertices[mask])


def distribution_points(ax):
    """Observe distribution geometry, including marker centres and transforms."""
    points = []
    for artist in [*ax.lines, *ax.patches]:
        if not artist.get_visible() or artist.get_alpha() == 0:
            continue
        points.extend(path_in_data(ax, artist, artist.get_path()))
    for artist in ax.collections:
        if not artist.get_visible() or artist.get_alpha() == 0:
            continue
        if isinstance(artist, PathCollection):
            centers = (artist.get_offset_transform() - ax.transData).transform(artist.get_offsets())
            points.extend(centers)
        else:
            for path in artist.get_paths():
                points.extend(path_in_data(ax, artist, path))
    points = np.asarray(points).reshape(-1, 2)
    return points[np.isfinite(points).all(axis=1)]


def histogram_regions(ax):
    """Observe occupied filled bins across rectangle and collection renderers."""
    ax.figure.canvas.draw()
    for patch in ax.patches:
        if patch.get_visible() and patch.get_facecolor()[3] > 0:
            yield path_in_data(ax, patch, patch.get_path()), None
    for artist in ax.collections:
        paths = artist.get_paths()
        counts = artist.get_array()
        colors = artist.get_facecolors()
        assert len(colors) in (1, len(paths))
        if counts is not None:
            counts = np.ma.asarray(counts).ravel()
            assert len(paths) == len(counts)
        for index, path in enumerate(paths):
            count = None if counts is None else counts[index]
            if count is not None and (np.ma.is_masked(count) or count == 0):
                continue
            color = colors[0 if len(colors) == 1 else index]
            if count is None and color[3] == 0:
                continue
            assert artist.get_visible() and color[3] > 0
            if count is not None:
                assert_close(color, artist.to_rgba(count))
            yield path_in_data(ax, artist, path), count


def public_layers(deck, layer_type):
    return [layer for layer in deck.layers if layer.type == layer_type]


def colored_paths(collection):
    """Pair the public path and facecolor arrays of one returned collection."""
    paths, colors = collection.get_paths(), collection.get_facecolors()
    assert len(paths) == len(colors)
    return [(path.vertices, color) for path, color in zip(paths, colors, strict=True)]


def sector_share(vertices, center):
    """Measure an arc's angular extent without depending on vertex ordering."""
    offsets = np.asarray(vertices, dtype=float)[:, :2] - np.asarray(center)
    radii = np.linalg.norm(offsets, axis=1)
    assert radii.max() > 0
    arc = offsets[radii > radii.max() * 1e-10]
    angles = np.unique(np.mod(np.arctan2(arc[:, 1], arc[:, 0]), 2 * np.pi))
    assert len(angles) >= 2
    gaps = np.diff(np.r_[angles, angles[0] + 2 * np.pi])
    return 1 - gaps.max() / (2 * np.pi)


def polygon_centroid(vertices):
    """Return the geometric centroid, unaffected by repeated closing vertices."""
    points = np.asarray(vertices, dtype=float)[:, :2]
    following = np.roll(points, -1, axis=0)
    cross = points[:, 0] * following[:, 1] - following[:, 0] * points[:, 1]
    assert abs(cross.sum()) > 0
    return ((points + following) * cross[:, None]).sum(axis=0) / (3 * cross.sum())


def marker_area(path):
    """Integrate the filled path boundary, including its Bezier segments."""
    vertices = np.asarray(path.vertices, dtype=float)
    if not len(vertices):
        return 0.
    # Translation avoids cancellation at large geographic coordinates.
    boundary = Path(vertices - vertices.mean(axis=0), path.codes)
    total = 0.
    first = last = None
    for curve, code in boundary.iter_bezier():
        if code == Path.MOVETO:
            if last is not None:
                total += last[0]*first[1] - first[0]*last[1]
            first = last = curve(0)
            continue
        coefficients = curve.polynomial_coefficients
        x, y = coefficients[:, 0], coefficients[:, 1]
        integrand = np.polynomial.polynomial.polysub(
            np.polynomial.polynomial.polymul(x, np.polynomial.polynomial.polyder(y)),
            np.polynomial.polynomial.polymul(y, np.polynomial.polynomial.polyder(x)))
        total += sum(integrand / np.arange(1, len(integrand) + 1))
        last = curve(1)
    if last is not None:
        total += last[0]*first[1] - first[0]*last[1]
    return abs(total) / 2
