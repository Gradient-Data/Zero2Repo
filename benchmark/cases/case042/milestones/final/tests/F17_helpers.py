# feature: F17
"""Observe paired projections against caller-owned finite coordinate tables."""
from collections import Counter

from F16_helpers import coordinate_points
from _helpers import invoke
from velnora_indexing import plan_chunks


def projected_rows(transform, grids):
    """Consume planning in the same bounded capture as its construction."""
    return invoke(plan_chunks, transform, grids, consume=True, max_items=1000).value


def assert_projected_coordinates(rows, edges, expected):
    """Check all destinations and sources, retaining repeated source positions."""
    expected_chunks = set()
    for source in expected.values():
        chunk = []
        for value, boundaries in zip(source, edges, strict=True):
            matches = [i for i in range(len(boundaries)-1)
                       if boundaries[i] <= value < boundaries[i+1]]
            assert len(matches) == 1
            chunk.append(matches[0])
        expected_chunks.add(tuple(chunk))
    assert {row.chunk_coords for row in rows} == expected_chunks
    assert len(rows) == len(expected_chunks)
    observed = []
    for row in rows:
        lower = tuple(axis[c] for axis, c in zip(edges, row.chunk_coords, strict=True))
        upper = tuple(axis[c+1] for axis, c in zip(edges, row.chunk_coords, strict=True))
        assert row.chunk_domain.inclusive_min == lower
        assert row.chunk_domain.exclusive_max == upper
        assert row.chunk_domain.shape == tuple(b-a for a, b in zip(lower, upper, strict=True))
        domain = row.cell_transform.domain
        assert row.chunk_transform.domain.inclusive_min == domain.inclusive_min
        assert row.chunk_transform.domain.exclusive_max == domain.exclusive_max
        for cell in coordinate_points(domain.inclusive_min, domain.exclusive_max):
            destination = tuple(invoke(row.cell_transform.apply, cell).value)
            local = tuple(invoke(row.chunk_transform.apply, cell).value)
            assert len(local) == len(lower)
            assert all(0 <= v < b-a for v, a, b in zip(local, lower, upper, strict=True))
            source = tuple(v+a for v, a in zip(local, lower, strict=True))
            observed.append((destination, source))
    assert Counter(observed) == Counter(expected.items())
