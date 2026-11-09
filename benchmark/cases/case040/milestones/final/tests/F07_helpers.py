# feature: F07
"""Observe attributes while allowing omitted trailing unstyled runs."""
from F01_helpers import expanded_runs
from F03_helpers import is_default_attr


def ansi_attribute_cells(value):
    cells = tuple(None if is_default_attr(attribute) else attribute
                  for attribute in expanded_runs(value.attrib))
    assert len(cells) <= len(value.text)
    return cells + (None,) * (len(value.text) - len(cells))
