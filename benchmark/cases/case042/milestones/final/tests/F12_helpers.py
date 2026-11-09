# feature: F12
"""Run attribute writes and independent persisted reads in fresh interpreters."""
from _helpers import run_python, run_python_report


_ATTRIBUTE_PROCESS = '''
import json
from pathlib import Path
import sys
import pytest
import velnora

location, version, kind = sys.argv[1:]
version = int(version)
open_node = velnora.open_array if kind == 'array' else velnora.open_group
if kind == 'array':
    node = velnora.create_array(location, shape=(2,), dtype='int16', zarr_format=version)
else:
    node = velnora.create_group(location, zarr_format=version)
'''


def check_attribute_changes(source, location, version, kind):
    """Execute assertions in a writer, then return attributes read after its exit."""
    completed = run_python(_ATTRIBUTE_PROCESS + source,
                           [str(location), str(version), kind])
    completed.check_returncode()
    _, attributes = run_python_report('''
import json
from pathlib import Path
import sys
import velnora
open_node = velnora.open_array if sys.argv[3] == 'array' else velnora.open_group
node = open_node(sys.argv[2], mode='r')
Path(sys.argv[1]).write_text(json.dumps(dict(node.attrs)), encoding='utf-8')
''', [str(location), kind])
    return attributes
