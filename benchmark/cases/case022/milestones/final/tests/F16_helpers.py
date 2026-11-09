# feature: F16
"""Sharded sources and actual framework-worker observations."""
from collections import defaultdict

from functools import wraps
from pathlib import Path

from _helpers import run_python


def distributed_source_test(function):
    @wraps(function)
    def execute():
        # Use the judge interpreter, as the framework-source launcher does.
        source = """
import sys
sys.path.insert(0, '/app/src')
sys.path.insert(0, sys.argv[1])
import importlib
from F15_helpers import framework_source_test
function = getattr(importlib.import_module(sys.argv[2]), sys.argv[3]).__wrapped__
framework_source_test(function)()
"""
        result = run_python(source, timeout=240,
                            args=(str(Path(__file__).parent), function.__module__, function.__name__))
        assert result.returncode == 0, result.stdout + result.stderr
    return execute


def emit_source_shards(chunks):
    from F04_helpers import produce_records
    for chunk in chunks:
        yield from produce_records(chunk)


def source_shards(chunks):
    from velnora import IterableDataset
    return IterableDataset.from_generator(emit_source_shards, gen_kwargs={'chunks': chunks})


def attribute_worker(row):
    from torch.utils.data import get_worker_info
    worker = get_worker_info()
    if worker is None:
        raise RuntimeError('Collation must run in a real loader worker')
    return worker.id, row


def worker_portions(dataset, workers=2):
    from torch.utils.data import DataLoader
    portions = defaultdict(list)
    loader = DataLoader(dataset, batch_size=None, num_workers=workers,
                        collate_fn=attribute_worker, timeout=30)
    for worker, row in loader:
        portions[worker].append(row)
    assert len(portions) == workers, 'Every worker must deliver source records'
    return list(portions.values())


def assert_local_first_exhaustion(rows, sources):
    """Accept either boundary turn while requiring real local exhaustion."""
    assert rows
    counts = []
    for source, expected in enumerate(sources):
        actual = [row for row in rows if row['source'] == source]
        assert actual == expected[:len(actual)]
        counts.append(len(actual))
    assert sum(counts) == len(rows)
    assert abs(counts[0] - counts[1]) <= 1
    assert any(count == len(expected) for count, expected in zip(counts, sources))
    # A complete extra turn after a source is exhausted is not first exhaustion.
    assert len(rows) <= 2 * min(map(len, sources))
