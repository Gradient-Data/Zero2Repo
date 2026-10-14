# feature: F04
"""Schemas that apply merge keys under FP-04.

Merge keys apply under YAML 1.1, or under Core with the merge tag.
Those two option bags are this slice's new name. The suite-named
several-merge document is a constant in the feature test file, not
assembled here. Runtime unique-key several-merge still uses the sealed assembler.
"""

from __future__ import annotations

from typing import Any

from _helpers import with_merge_on_core, with_yaml11_schema


def merge_on_schemas() -> tuple[tuple[dict[str, Any], str], ...]:
    """The two schemas L181 names as applying ``<<``.

    YAML 1.1 first, then Core with the merge tag. Order is stable so a
    live YAML 1.1 baseline is first when callers iterate.
    """
    return (
        (with_yaml11_schema(), "yaml11"),
        (with_merge_on_core(), "core+merge"),
    )
