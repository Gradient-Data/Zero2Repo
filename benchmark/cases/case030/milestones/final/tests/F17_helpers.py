# feature: F17
"""Python delivery consumers and an isolated ordinary-Python runtime."""
import importlib.machinery
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import make_environment, run_command, write_text
from F00_candidate import PRODUCT_ROOT
from F03_helpers import require_success


PYTHON_PROGRAM = '''
from numpy import array, int64

def adjust(x: int):
    return x * x - 3

def calculate(n: int):
    values = [2, -5]
    total = 0
    for i in range(n):
        if i == 2:
            continue
        values.append(adjust(i))
        total += values[-1]
    a = array(values, dtype=int64)
    a[0] += n
    if n > 3:
        total -= a[0]
    else:
        total += a[1]
    return total, a, values
'''


def require_python_only(root):
    """Check delivery trees, excluding the sibling installation copy."""
    import os
    for path in root.rglob('*'):
        if path.is_file():
            assert not any(path.name.endswith(s) for s in importlib.machinery.EXTENSION_SUFFIXES), path
            assert not os.access(path, os.X_OK), path


def read_python_calls(root, module, expression, *, runtime=None):
    """Execute the delivered file in a fresh interpreter and read driver JSON."""
    driver = f'''
import sys, json
sys.path[:0] = {[str(root)] + ([str(runtime)] if runtime else [])!r}
import {module} as delivered
import numpy as np
values = {expression}
def encode(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)
print(json.dumps(values, default=encode))
'''
    result = run_command([sys.executable, *(['-I', '-S'] if runtime else []), '-c', driver],
                         cwd=root, env=make_environment({'PYTHONPATH': None}), timeout=120)
    require_success(result)
    return json.loads(result.stdout)


def isolated_python_support(root):
    """Expose NumPy and the real public decorator module, without Zelvori runtime."""
    import numpy
    root.mkdir()
    numpy_package = Path(numpy.__file__).parent
    (root / 'numpy').symlink_to(numpy_package, target_is_directory=True)
    libraries = numpy_package.parent / 'numpy.libs'
    if libraries.exists():
        (root / 'numpy.libs').symlink_to(libraries, target_is_directory=True)
    package = root / 'zelvori'
    package.mkdir()
    # Namespace package containing only the original annotation support, not
    # the translator, OpenMP extensions, or any generated native artifacts.
    shutil.copyfile(PRODUCT_ROOT / 'zelvori/decorators.py', package / 'decorators.py')
    return root
