# feature: F00
"""Make public imports use the runtime candidate before collecting features.

The judge starts in the candidate product directory and mounts tests elsewhere.
Its isolated collecting interpreter does not implicitly import from that cwd.
"""

from importlib import import_module
from pathlib import Path
import sys


_PRODUCT_DIRECTORY = Path.cwd().resolve()
sys.path.insert(0, str(_PRODUCT_DIRECTORY))

# Leave import errors intact, including missing dependencies inside the product.
_product = import_module('cobaltform')
if not _product.__path__ or any(
    not Path(location).resolve().is_relative_to(_PRODUCT_DIRECTORY)
    for location in _product.__path__
):
    raise ImportError(
        'cobaltform must resolve inside the runtime candidate product directory: '
        + str(_PRODUCT_DIRECTORY)
    )
