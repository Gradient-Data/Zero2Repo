# feature: F00
"""Bind collection and child interpreters to the product supplied by casebox."""

import importlib.util
import os
from pathlib import Path
import sys


# The public package location is part of the case's execution shell. A wheel
# installed in the build container does not survive into the test container.
source_root = Path('/app/src')
package_file = source_root / 'velnora/__init__.py'
if not package_file.is_file():
    raise RuntimeError('The supplied product package is missing from /app/src')
if 'velnora' in sys.modules:
    raise RuntimeError('The product was imported before test source binding')

sys.path.insert(0, str(source_root))
spec = importlib.util.find_spec('velnora')
if spec is None or spec.origin is None or Path(spec.origin).resolve() != package_file.resolve():
    raise RuntimeError('Product imports do not resolve to the supplied source tree')

# Fresh interpreters, including framework workers, must observe the same tree.
paths = os.environ.get('PYTHONPATH', '').split(os.pathsep)
os.environ['PYTHONPATH'] = os.pathsep.join(
    [str(source_root), *(path for path in paths if path and path != str(source_root))]
)
