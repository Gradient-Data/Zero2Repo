# feature: F13
"""Source-bound row operations and independently recreated split requests."""
from collections import Counter
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from tempfile import TemporaryDirectory

from velnora import Dataset, load_dataset

from _helpers import run_python
from F05_helpers import write_records


def row_operation_source_test(function):
    @wraps(function)
    def execute():
        source = '''
import sys
from pathlib import Path
root = Path('/app/src')
if not (root / 'velnora/__init__.py').is_file():
    raise RuntimeError('Mounted product source is missing')
sys.path.insert(0, str(root))
sys.path.insert(0, sys.argv[1])
import F13_rows
getattr(F13_rows, sys.argv[2]).__wrapped__()
'''
        result = run_python(source, timeout=180,
                            args=(str(Path(__file__).parent), function.__name__))
        assert result.returncode == 0, result.stdout + result.stderr
    return execute


def independent_seeded_partitions(rows, **options):
    """Return actual rows from two equivalent, separately constructed sources."""
    results = []
    for _ in range(2):
        source = Dataset.from_list([dict(row) for row in rows])
        split = source.train_test_split(load_from_cache_file=False, **options)
        results.append({name: list(split[name]) for name in ('train', 'test')})
    return results


def assert_uniform_row_positions(permutations, rows):
    """Check contents and marginal positions without prescribing a PRNG."""
    counts = [Counter() for _ in rows]
    for permutation in permutations:
        assert sorted(permutation, key=lambda row: row['id']) == rows
        for position, row in enumerate(permutation):
            counts[row['id']][position] += 1
    samples = len(permutations)
    assert samples == 4096
    # Hoeffding + union bound for 16 cells: 32*exp(-2*4096*.055**2)
    # is below 6e-10 under independent uniform draws. No joint law is tested.
    for positions in counts:
        for position in range(len(rows)):
            assert abs(positions[position] / samples - 1 / len(rows)) <= .055


@contextmanager
def split_file_loader(training, testing):
    """Load real JSONL files using public split instructions in a fresh cache."""
    with TemporaryDirectory(prefix='F13-slices-') as directory:
        root = Path(directory)
        files = {'train': write_records(root, 'train.jsonl', training),
                 'test': write_records(root, 'test.jsonl', testing)}

        def load(instruction):
            return load_dataset('json', data_files=files, split=instruction,
                                cache_dir=str(root / 'cache'))
        yield load
