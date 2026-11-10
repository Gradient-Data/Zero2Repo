# feature: F15
"""Framework observations through public array and table interfaces."""
from functools import wraps
from pathlib import Path
import os

from _helpers import run_python


def framework_source_test(function):
    @wraps(function)
    def execute():
        source = '''
import importlib
import sys
from pathlib import Path
root = Path('/app/src')
if not (root / 'velnora/__init__.py').is_file():
    raise RuntimeError('Mounted product source is missing')
sys.path.insert(0, str(root))
sys.path.insert(0, sys.argv[1])
getattr(importlib.import_module(sys.argv[2]), sys.argv[3]).__wrapped__()
'''
        environment = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                           TF_NUM_INTRAOP_THREADS='1', TF_NUM_INTEROP_THREADS='1',
                           JAX_PLATFORMS='cpu', POLARS_MAX_THREADS='1')
        result = run_python(source, timeout=240, env=environment,
                            args=(str(Path(__file__).parent), function.__module__, function.__name__))
        assert result.returncode == 0, result.stdout + result.stderr
    return execute


def assert_framework_batch(batch, representation, expected):
    """Check actual public container types and independently supplied content."""
    import numpy as np
    if representation == 'arrow':
        import pyarrow as pa
        assert isinstance(batch, pa.Table)
        assert batch.to_pydict() == expected
    elif representation == 'pandas':
        import pandas as pd
        assert isinstance(batch, pd.DataFrame)
        assert set(batch.columns) == set(expected)
        for name, values in expected.items():
            actual = batch[name].tolist()
            assert len(actual) == len(values)
            for item, expected in zip(actual, values):
                np.testing.assert_array_equal(np.asarray(item).tolist(), expected)
    elif representation == 'polars':
        import polars as pl
        assert isinstance(batch, pl.DataFrame)
        assert batch.to_dict(as_series=False) == expected
    else:
        assert set(batch) == set(expected)
        for name, values in expected.items():
            array = batch[name]
            if representation is None:
                assert isinstance(array, list)
                assert array == values
                continue
            if representation == 'numpy':
                assert isinstance(array, np.ndarray)
            elif representation == 'torch':
                import torch
                assert isinstance(array, torch.Tensor)
                array = array.detach().cpu().numpy()
            elif representation == 'tensorflow':
                import tensorflow as tf
                assert isinstance(array, tf.Tensor)
                array = array.numpy()
            elif representation == 'jax':
                import jax
                assert isinstance(array, jax.Array)
            else:
                raise AssertionError('Unknown representation')
            assert tuple(array.shape) == np.asarray(values).shape
            np.testing.assert_array_equal(np.asarray(array), values)


def framework_records():
    from F04_helpers import endless_records
    for row in endless_records():
        yield {'number': row['number']}


def check_without_polars():
    """Run with real dependency isolation, retaining all other installed packages."""
    import site
    import sys
    from tempfile import TemporaryDirectory
    from _helpers import run_command

    with TemporaryDirectory(prefix='F15-no-polars-') as directory:
        paths = []
        for index, original in enumerate(site.getsitepackages()):
            isolated = Path(directory) / str(index)
            isolated.mkdir()
            for entry in Path(original).iterdir():
                if entry.name != 'polars':
                    (isolated / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
            paths.append(str(isolated))
        source = '''
import sys
from pathlib import Path
sys.path[:] = sys.argv[1:] + [path for path in sys.path if 'site-packages' not in Path(path).parts]
import importlib.util
assert importlib.util.find_spec('polars') is None, 'Dependency isolation failed'
from velnora import Dataset
from F04_helpers import iterable_records

for source in (Dataset.from_dict({'number': [17]}), iterable_records([{'number': 17}])):
    try:
        formatted = source.with_format('polars')
        if isinstance(source, Dataset):
            batch = formatted[:]
        else:
            batch = next(iter(formatted.iter(batch_size=1)))
    except ValueError:
        pass
    else:
        # A genuinely independent backend remains acceptable if it supplies
        # the same public table contents, rather than ordinary row mappings.
        assert batch.to_dict(as_series=False) == {'number': [17]}
'''
        environment = dict(os.environ)
        environment.pop('PYTHONPATH', None)
        result = run_command((sys.executable, '-c', source, '/app/src', str(Path(__file__).parent), *paths),
                             timeout=60, env=environment)
        assert result.returncode == 0, result.stdout + result.stderr
