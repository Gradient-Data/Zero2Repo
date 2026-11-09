# feature: F17
"""Acceptance of grid-aware coordinate projection and coverage."""
from itertools import product

import numpy as np
import pytest
from F17_helpers import assert_projected_coordinates, projected_rows
from velnora_indexing import (
    ArrayMap, ConstantMap, DimensionMap, IndexDomain, IndexTransform,
    dimension_grids_from_chunks,
)


def test_f17_t01():
    # A translated request, reversed axis and output permutation on a uniform grid.
    transform = IndexTransform(IndexDomain((4, -2), (7, 2)),
                               (DimensionMap(1, offset=2), DimensionMap(0, offset=6, stride=-1)))
    expected = {(i, j): (j+2, 6-i) for i, j in product(range(4, 7), range(-2, 2))}
    assert_projected_coordinates(
        projected_rows(transform, dimension_grids_from_chunks((3, 2), (4, 3))),
        ((0, 3, 4), (0, 2, 3)), expected)

    # Orthogonal explicit coordinates retain each occurrence at its own destination.
    first, second = [5, 0, 5, 2], [6, 1, 1]
    transform = IndexTransform(IndexDomain.from_shape((4, 3)),
                               (ArrayMap(np.array(first)[:, None]),
                                ArrayMap(np.array(second)[None, :])))
    expected = {(i, j): (a, b) for i, a in enumerate(first) for j, b in enumerate(second)}
    assert_projected_coordinates(
        projected_rows(transform, dimension_grids_from_chunks(((2, 1, 3), (1, 4, 2)), (6, 7))),
        ((0, 2, 3, 6), (0, 1, 5, 7)), expected)

    # Correlated coordinates with repeated points and a residual affine axis.
    first, second = [4, 0, 4, 1], [1, 5, 1, 3]
    transform = IndexTransform(IndexDomain.from_shape((4, 2)),
                               (ArrayMap(np.array(first)[:, None]),
                                ArrayMap(np.array(second)[:, None]), DimensionMap(1)))
    expected = {(i, j): (a, b, j) for i, (a, b) in enumerate(zip(first, second))
                for j in range(2)}
    assert_projected_coordinates(
        projected_rows(transform, dimension_grids_from_chunks((2, 4, 1), (5, 6, 2))),
        ((0, 2, 4, 5), (0, 4, 6), (0, 1, 2)), expected)


def test_f17_t02():
    grids = dimension_grids_from_chunks((3,), (5,))
    valid = IndexTransform(IndexDomain.from_shape((2,)), (DimensionMap(0, offset=3),))
    assert_projected_coordinates(projected_rows(valid, grids), ((0, 3, 5),),
                                 {(0,): (3,), (1,): (4,)})
    # Empty requests, including a zero-length source axis, have no contributions.
    for shape, chunks in [((0,), (3,)), ((2, 0), (1, 2))]:
        assert projected_rows(IndexTransform.from_shape(shape),
                              dimension_grids_from_chunks(chunks, shape)) == []
    for grid_spec in [(3,), ((2, 3),)]:
        bounded = dimension_grids_from_chunks(grid_spec, (5,))
        for output in [ConstantMap(-1), ConstantMap(5), DimensionMap(0, offset=4),
                       ArrayMap(np.array([1, 5]))]:
            invalid = IndexTransform(IndexDomain.from_shape((2,)), (output,))
            with pytest.raises(IndexError):
                projected_rows(invalid, bounded)
    pair = dimension_grids_from_chunks((2, 2), (4, 4))
    independent = IndexTransform.from_shape((4, 4))
    assert_projected_coordinates(projected_rows(independent, pair),
                                 ((0, 2, 4), (0, 2, 4)),
                                 {(i, j): (i, j) for i, j in product(range(4), repeat=2)})
    diagonal = IndexTransform(IndexDomain.from_shape((4,)), (DimensionMap(0), DimensionMap(0)))
    with pytest.raises(ValueError):
        projected_rows(diagonal, pair)
    mixed = IndexTransform(IndexDomain.from_shape((4,)),
                           (DimensionMap(0), ArrayMap(np.array([3, 2, 1, 0]))))
    with pytest.raises(NotImplementedError):
        projected_rows(mixed, pair)


def test_f17_t03():
    grids = dimension_grids_from_chunks((3,), (5,))
    # Basic coverage must be exact, including clipped boundary chunks and reversal.
    for values, output in [([0, 1, 2, 3, 4], DimensionMap(0)),
                           ([4, 3, 2, 1, 0], DimensionMap(0, offset=4, stride=-1)),
                           ([0, 2, 4], DimensionMap(0, stride=2)),
                           ([1], ConstantMap(1)),
                           ([4, 4], DimensionMap(0, offset=4, stride=0))]:
        transform = IndexTransform(IndexDomain.from_shape((len(values),)), (output,))
        rows = projected_rows(transform, grids)
        assert_projected_coordinates(rows, ((0, 3, 5),),
                                     {(i,): (v,) for i, v in enumerate(values)})
        for row in rows:
            lo, = row.chunk_domain.inclusive_min
            hi, = row.chunk_domain.exclusive_max
            covered = [v for v in values if lo <= v < hi]
            if sorted(covered) == list(range(lo, hi)):
                assert row.coverage == 'full'
            else:
                assert row.coverage != 'full'
    for transform, spec, shape, complete, incomplete in (
        (IndexTransform.from_shape((5,)), ((1, 2, 2),), (5,), {(0,), (1,), (2,)}, set()),
        (IndexTransform(IndexDomain((0,), (5,)), (DimensionMap(0, offset=6, stride=-1),)), (3,), (7,),
         {(1,), (2,)}, {(0,)}),
        (IndexTransform(IndexDomain((0, 0), (3, 4)), (DimensionMap(0), DimensionMap(1, offset=1))), (3, 2), (5, 5),
         {(0, 1), (0, 2)}, {(0, 0)}),
        (IndexTransform(IndexDomain((), ()), (ConstantMap(4),)), (3,), (5,), set(), {(1,)}),
    ):
        rows = projected_rows(transform, dimension_grids_from_chunks(spec, shape))
        assert {row.chunk_coords for row in rows} == complete | incomplete
        for row in rows:
            assert (row.coverage == 'full') == (row.chunk_coords in complete)
    # Explicit coverage can be conservative, but partial/repeated data cannot be full.
    for values in [[0, 1, 2, 3, 4], [0, 2, 3], [0, 1, 1, 2, 3, 4, 4]]:
        transform = IndexTransform(IndexDomain.from_shape((len(values),)), (ArrayMap(np.array(values)),))
        rows = projected_rows(transform, grids)
        assert_projected_coordinates(rows, ((0, 3, 5),),
                                     {(i,): (v,) for i, v in enumerate(values)})
        for row in rows:
            lo, = row.chunk_domain.inclusive_min
            hi, = row.chunk_domain.exclusive_max
            covered = [v for v in values if lo <= v < hi]
            allowed = {'full', 'partial', 'unknown'} if sorted(covered) == list(range(lo, hi)) else {'partial', 'unknown'}
            assert row.coverage in allowed
