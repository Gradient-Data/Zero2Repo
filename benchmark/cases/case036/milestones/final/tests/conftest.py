# feature: F00
"""Use the current product's source tree before collecting product imports."""

import importlib.util
import os
from pathlib import Path
import sys


_PRODUCT_DIR = Path.cwd().resolve()
_PRODUCT_PATHS = [str(_PRODUCT_DIR), str(_PRODUCT_DIR / "src")]

# Keep directory packages first, while also supporting a source subdirectory.
# Export the same paths for shared helpers and direct Python subprocesses.
sys.path[:0] = _PRODUCT_PATHS
_inherited_path = os.environ.get("PYTHONPATH")
os.environ["PYTHONPATH"] = os.pathsep.join(
    _PRODUCT_PATHS + ([_inherited_path] if _inherited_path else [])
)

# An installed package must never stand in for a missing current product.
# Resolving the public package does not import it; its own errors propagate
# unchanged when the feature modules import their public entries.
_spec = importlib.util.find_spec("velun")
_locations = (
    [_spec.origin] if _spec is not None and _spec.origin is not None
    else list(_spec.submodule_search_locations or ()) if _spec is not None
    else []
)
if not _locations or any(
    not Path(location).resolve().is_relative_to(_PRODUCT_DIR)
    for location in _locations
):
    raise ModuleNotFoundError(
        f"The current product at {_PRODUCT_DIR} does not provide 'velun' "
        "from its working directory or source directory.",
        name="velun",
    )
