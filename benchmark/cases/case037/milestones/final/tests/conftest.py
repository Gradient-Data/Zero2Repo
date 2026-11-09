# feature: F00
"""Load the candidate workspace before externally mounted tests are collected."""
import os
from pathlib import Path
import sys


# The judge starts in the candidate working directory, but its isolated Python
# launcher does not put that directory on sys.path. Installation is not required.
_candidate = Path.cwd().resolve()
sys.path.insert(0, str(_candidate))

import velnora

if not Path(velnora.__file__).resolve().is_relative_to(_candidate):
    raise ImportError(
        f"velnora must resolve inside the candidate workspace {_candidate}, "
        f"got {velnora.__file__}"
    )

# Existing hosts-view and transport checks launch Python scripts directly;
# those children do not load pytest's conftest. Give them the same source root.
_inherited = os.environ.get('PYTHONPATH')
os.environ['PYTHONPATH'] = str(_candidate) + (
    os.pathsep + _inherited if _inherited else ''
)


def pytest_report_header():
    """Retain the actual package origin in verbose collection/test reports."""
    return f"Candidate package: {velnora.__file__} (workspace: {_candidate})"
