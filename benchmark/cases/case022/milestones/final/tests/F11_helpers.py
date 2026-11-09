# feature: F11
"""Source-bound execution and independent snapshots for column transformations."""
from copy import deepcopy
import functools
from pathlib import Path

from velnora import Dataset, IterableDataset
from _helpers import run_python
from F04_helpers import produce_records


def column_source_test(function):
    @functools.wraps(function)
    def execute():
        source = '''
import sys
from pathlib import Path
source = Path('/app/src')
if not (source / 'velnora/__init__.py').is_file():
    raise RuntimeError('Mounted product source is missing')
sys.path.insert(0, str(source))
sys.path.insert(0, sys.argv[1])
from F11_columns import FUNCTION
FUNCTION.__wrapped__()
'''.replace('FUNCTION', function.__name__)
        result = run_python(source, timeout=120, args=(str(Path(__file__).parent),))
        assert result.returncode == 0, result.stdout + result.stderr
    return execute


def column_models(rows, features):
    return (Dataset.from_list(rows, features=features),
            IterableDataset.from_generator(produce_records,
                                           gen_kwargs={'records': tuple(rows)}, features=features))


def column_snapshot(dataset):
    return deepcopy(list(dataset)), deepcopy(dataset.features)


def assert_column_source(dataset, snapshot):
    assert list(dataset) == snapshot[0]
    assert dataset.features == snapshot[1]
