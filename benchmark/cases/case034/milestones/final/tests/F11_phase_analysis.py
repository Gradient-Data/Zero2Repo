# feature: F11
"""Acceptance tests for operating points, linearization and phase planes."""
import numpy as np
import pytest
import velunex as ct
from velunex import phaseplot as pp
from numpy.testing import assert_allclose
from _helpers import headless_figures
from F03_helpers import parameter_update, parameter_output
from F11_helpers import (assert_point_set, phase_coordinates, shifted_saddle,
                         assert_flow_paths, covers_flow)


def test_operating_point_constraints():
    for dt, a, expected in [(0, -2, 3.5), (.2, .5, 14)]:
        model = ct.nlsys(parameter_update, parameter_output, states=1,
            inputs=1, outputs=1, dt=dt,
            params={'a': a, 'b': 3, 'bias': 1, 'c': 2, 'd': -1})
        fixed = ct.find_operating_point(model, [-4], [2])
        assert fixed.result.success
        assert_allclose(fixed.states, [expected], atol=1e-7)
        assert_allclose(fixed.inputs, [2], atol=1e-7)
        assert_allclose(fixed.outputs, [2*expected-3], atol=1e-7)
        desired = ct.find_operating_point(model, [-4], [0], [5])
        # Independent affine equations: (a-dt_flag)x+3u=-1, 2x-u=6.
        x, u = np.linalg.solve([[a-(dt != 0), 3], [2, -1]], [-1, 6])
        assert desired.result.success
        assert_allclose(desired.states, [x], atol=1e-7)
        assert_allclose(desired.inputs, [u], atol=1e-7)
        assert_allclose(desired.outputs, [5], atol=1e-7)
    model = ct.nlsys(lambda t, x, u, p: [-2*x[0]+u[0], x[0]-3*x[1]+u[1]],
        lambda t, x, u, p: [x[0]+x[1], x[1]+2*u[1]],
        states=2, inputs=2, outputs=2)
    op = ct.find_operating_point(model, [2, -8], [5, -7], [99, 11],
        state_indices=[0], input_indices=[0], output_indices=[1],
        deriv_indices=[1], derivs=[99, 4])
    assert op.result.success
    assert_allclose(op.states, [2, 1], atol=1e-7)
    assert_allclose(op.inputs, [5, 5], atol=1e-7)
    assert_allclose(op.outputs, [3, 11], atol=1e-7)


def test_unsuccessful_operating_point_candidate():
    model = ct.nlsys(lambda t, x, u, p: [x[0]**2+u[0]], states=1, inputs=1)
    good = ct.find_operating_point(model, [2], [-1])
    assert good.result.success
    assert_allclose(np.asarray(good.states)**2, [1], atol=1e-7)
    assert_allclose(good.inputs, [-1])
    for requested in (False, True):
        failed = ct.find_operating_point(model, [0], [1], return_result=requested)
        assert not failed.result.success
        if requested:
            assert np.asarray(failed.states).shape == (1,)
            assert np.all(np.isfinite(failed.states))
            assert_allclose(failed.inputs, [1])
            assert failed.states[0]**2 + failed.inputs[0] >= 1
        else:
            assert failed.states is None
            assert failed.inputs is None


def test_local_linearization():
    model = ct.nlsys(
        lambda t, x, u, p: [p['gain']*x[0]**2+(1+t)*x[1]+u[0]**2,
                             x[0]*x[1]+p['gain']*u[0]],
        lambda t, x, u, p: [x[0]**2+x[1]*u[0]+t*u[0]],
        states=2, inputs=1, outputs=1, params={'gain': 2})
    for dt, x, u, t, gain in [(0, [0, 0], 0, 0, 2),
                              (0, [2, -1], 3, .7, 4),
                              (.3, [-1, 2], -2, 1.5, 3)]:
        model.dt = dt
        local = ct.linearize(model, x, [u], t=t, params={'gain': gain})
        assert local.dt == dt
        # Derivatives of the user-supplied polynomial, independent of product code.
        assert_allclose(local.A, [[2*gain*x[0], 1+t], [x[1], x[0]]], atol=2e-5)
        assert_allclose(local.B, [[2*u], [gain]], atol=2e-5)
        assert_allclose(local.C, [[2*x[0], u]], atol=2e-5)
        assert_allclose(local.D, [[x[1]+t]], atol=2e-5)


def test_phase_vectors_grids_and_time_directions():
    xs, ys = [-2, 0, 2], [-1, 1, 3]
    mesh_expected = np.array([(x, y) for x in xs for y in ys])
    box_expected = np.array([(x, y) for x in xs for y in ys
                             if x in (-2, 2) or y in (-1, 3)])
    mesh, box = pp.meshgrid(xs, ys), pp.boxgrid(xs, ys)
    assert_point_set(mesh, mesh_expected)
    assert_point_set(box, box_expected)
    centers = np.array([[-2, -1], [2, 1]])
    circle = pp.circlegrid(centers, .4, 6)
    assert circle.shape == (12, 2)
    for center in centers:
        distances = np.linalg.norm(circle-center, axis=1)
        ring = circle[np.isclose(distances, .4)]
        assert len(ring) == 6
        assert_allclose(np.linalg.norm(ring-center, axis=1), .4, atol=1e-7)
    with headless_figures() as plt:
        field = ct.nlsys(lambda t, x, u, p: [x[1]+1, -2*x[0]+.5], states=2, inputs=0)
        for region in ([-2, 2, -1, 3], [-1, 3, -2, 2]):
            points = np.array([(x, y) for x in np.linspace(*region[:2], 3)
                               for y in np.linspace(*region[2:], 3)])
            _, ax = plt.subplots()
            plot = ct.phase_plane_plot(field, region, ax=ax, gridspec=[3, 3], plot_vectorfield=True,
                plot_streamlines=False, plot_streamplot=False,
                plot_equilpoints=False, plot_separatrices=False)
            q = plot.lines[1]
            assert_point_set(np.column_stack((q.X, q.Y)), points)
            expected = np.column_stack((q.Y+1, -2*q.X+.5))
            actual = np.column_stack((q.U, q.V))
            assert np.all(np.sum(actual*expected, axis=1) > 0)
            assert_allclose(actual[:, 0]*expected[:, 1]-actual[:, 1]*expected[:, 0], 0, atol=1e-7)
        flow = ct.nlsys(lambda t, x, u, p: [1, 2], states=2, inputs=0)
        starts = np.array([[0, 0], [1, -1]])
        scenarios = [(starts, None, None, starts),
            ([-2, 2, -1, 3], 'meshgrid', [3, 3], mesh),
            ([-2, 2, -1, 3], 'boxgrid', [3, 3], box),
            (centers, 'circlegrid', [.4, 6], circle)]
        for points, gridtype, gridspec, initial in scenarios:
            for direction in ('forward', 'reverse', 'both'):
                _, ax = plt.subplots()
                # An existing wide frame allows boundary seeds to evolve
                # in both directions without clipping at their starting box.
                ax.plot([-10, 10], [-10, 10], alpha=0)
                ax.set(xlim=(-10, 10), ylim=(-10, 10))
                plot = ct.phase_plane_plot(flow, points, timedata=.2, ax=ax,
                    gridtype=gridtype, gridspec=gridspec, dir=direction,
                    plot_streamlines=True, plot_vectorfield=False,
                    plot_streamplot=False, plot_equilpoints=False, plot_separatrices=False)
                paths = [phase_coordinates(line) for line in plot.lines[0]]
                if gridtype == 'circlegrid':
                    # Recover seeds from the actual rings; angular placement
                    # is free, while radius and count remain observable.
                    vertices = np.concatenate(paths)
                    distances = np.linalg.norm(vertices[:, None, :]-centers, axis=2)
                    ring_vertices = vertices[np.any(np.abs(
                        distances-gridspec[0]) <= 1e-7, axis=1)]
                    seeds = []
                    for point in ring_vertices:
                        if (not any(np.linalg.norm(point-other) <= 1e-7
                                    for other in seeds)
                                and covers_flow(paths, point, [1., 2.], .2,
                                                direction)):
                            seeds.append(point)
                    assert seeds, 'Circular trajectories are missing'
                    seeds = np.asarray(seeds)
                    distances = np.linalg.norm(seeds[:, None, :]-centers, axis=2)
                    on_ring = np.isclose(distances, gridspec[0], atol=1e-7)
                    assert np.all(np.sum(on_ring, axis=1) == 1)
                    assert np.all(np.sum(on_ring, axis=0) == gridspec[1])
                else:
                    seeds = initial
                assert_flow_paths(paths, seeds, [1., 2.], .2, direction)
        for dimension in (1, 3):
            invalid = ct.nlsys(lambda t, x, u, p: -np.asarray(x), states=dimension, inputs=0)
            with pytest.raises(ValueError):
                ct.phase_plane_plot(invalid, [-2, 2, -2, 2])


def test_equilibria_separatrices_and_layers():
    with headless_figures() as plt:
        for center in (np.array([.5, -.25]), np.array([-1, .75])):
            model = ct.nlsys(shifted_saddle, states=2, inputs=0, params={'center': center})
            region = [center[0]-2, center[0]+2, center[1]-2, center[1]+2]
            _, ax = plt.subplots()
            eq = pp.equilpoints(model, region, gridspec=[3, 3], ax=ax)
            assert_point_set(np.concatenate([phase_coordinates(line) for line in eq]), [center])
            _, ax = plt.subplots()
            branches = pp.separatrices(model, region, timedata=1, ax=ax)
            rays = {(unstable, positive): 0. for unstable in (False, True)
                    for positive in (False, True)}
            for line in branches:
                z = phase_coordinates(line)-center
                finite = np.all(np.isfinite(z), axis=1)
                # Accept split curves, whole invariant lines, either vertex
                # order, and explicit separators. Every drawn segment must
                # remain on one invariant line, including at the equilibrium.
                for left, right in zip(z[:-1], z[1:]):
                    if np.all(np.isfinite([left, right])):
                        pair = np.array([left, right])
                        unstable = np.max(abs(pair[:, 0]-pair[:, 1])) < 1e-6
                        stable = np.max(abs(pair[:, 0]+pair[:, 1])) < 1e-6
                        assert unstable or stable
                        lo, hi = sorted(pair[:, 0])
                        rays[(unstable, True)] += max(0., hi-max(lo, 0.))
                        rays[(unstable, False)] += max(0., min(hi, 0.)-lo)
                for point in z[finite]:
                    assert min(abs(point[0]-point[1]), abs(point[0]+point[1])) < 1e-6
            assert all(extent > 0 for extent in rays.values())
            for enabled in ('vectorfield', 'streamlines', 'equilpoints', 'separatrices', None):
                _, ax = plt.subplots()
                options = {f'plot_{name}': name == enabled for name in
                    ('vectorfield', 'streamlines', 'equilpoints', 'separatrices')}
                plot = ct.phase_plane_plot(model, region, timedata=.2, gridspec=[3, 3],
                    plot_streamplot=False, ax=ax, **options)
                assert bool(plot.lines[0]) == (enabled in ('streamlines', 'separatrices'))
                assert (plot.lines[1] is not None) == (enabled == 'vectorfield')
                assert bool(plot.lines[2]) == (enabled == 'equilpoints')
                if enabled == 'equilpoints':
                    assert_point_set(np.concatenate([phase_coordinates(line)
                        for line in plot.lines[2]]), [center])
                if enabled is not None:
                    assert_allclose(ax.get_xlim(), region[:2])
                    assert_allclose(ax.get_ylim(), region[2:])
