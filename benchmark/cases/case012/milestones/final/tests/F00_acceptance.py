# feature: F00
"""Language floor and one host lint of a short snippet.

Collected by the F00 group. ``_harness.py`` and ``conftest.py`` stay
uncollected. This module does not grade an Oxlint / plugins-host version
pair and does not remove the package, the interpreter, or the standard
library.
"""

from __future__ import annotations

from F00_helpers import (
    assert_documented_package_manager,
    assert_host_reports_one_rule,
    assert_node_language_floor,
)
from _harness import repo_root


def test_node24_documented_package_manager_host_reports_rule() -> None:
    """Node.js 24, the documented package manager, and one reported rule."""
    root = repo_root()
    assert_documented_package_manager(root)
    assert_node_language_floor()
    assert_host_reports_one_rule(root)
