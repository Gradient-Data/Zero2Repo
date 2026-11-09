# feature: F14
"""Public composition sources and source-bound acceptance execution."""
from functools import wraps
from pathlib import Path

from velnora import Dataset

from _helpers import run_python
from F04_helpers import iterable_records


def composition_source_test(function):
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
        result = run_python(source, timeout=240, args=(
            str(Path(__file__).parent), function.__module__, function.__name__))
        assert result.returncode == 0, result.stdout + result.stderr
    return execute


def composition_sources(lengths, streaming):
    records = [[{'source': source, 'index': index} for index in range(length)]
               for source, length in enumerate(lengths)]
    return [iterable_records(rows) if streaming else Dataset.from_list(rows)
            for rows in records]


def assert_source_progression(rows, lengths, repeating=False):
    counts = [0] * len(lengths)
    for row in rows:
        source = row['source']
        assert source in range(len(lengths))
        index = counts[source] % lengths[source] if repeating else counts[source]
        assert row == {'source': source, 'index': index}
        counts[source] += 1
    return counts
