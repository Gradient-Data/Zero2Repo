# feature: F08
"""Collection workflows reuse the existing runner and independent value checks."""
from F07_helpers import utility_run


def collection_run(directory, cases, failures=()):
    names = [line for line in cases.splitlines() if line and not line[0].isspace()]
    root = utility_run(directory, cases,
                       {name: 'FAIL' if name in failures else 'PASS' for name in names},
                       settings='Library    Collections\n')
    # Every declared case was executed and recorded exactly once.
    assert sorted(t.attrib['name'] for t in root.findall('.//test')) == sorted(names)
    return root
