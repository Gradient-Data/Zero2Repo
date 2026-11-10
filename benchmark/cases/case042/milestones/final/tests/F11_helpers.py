# feature: F11
"""Read the existing public plain-text hierarchy display."""
import ast

import numpy as np

from _helpers import invoke


def read_group_tree(group, *, level=None):
    """Parse display rows into relative paths and kinds, without sorting rows.

    The public text shell has a root-name line, four-column ancestor prefixes,
    and a branch connector followed by a node name. Array rows additionally
    carry a tuple shape and a dtype. Branch orientation is not significant.
    """
    options = {'plain': True, 'level': level}
    text = invoke(lambda: repr(group.tree(**options))).value
    lines = text.splitlines()
    assert lines and lines[0] == group.name, 'Missing or incorrect tree root'
    result = {'': 'group'}
    ancestors = []
    for line in lines[1:]:
        prefix, connector, row = line.partition('── ')
        assert connector and prefix[-1:] in ('├', '└'), 'Invalid tree row'
        indentation = prefix[:-1]
        assert len(indentation) % 4 == 0, 'Invalid tree indentation'
        assert all(indentation[i:i + 4] in ('│   ', '    ')
                   for i in range(0, len(indentation), 4)), 'Invalid ancestor prefix'
        depth = len(indentation) // 4
        assert depth <= len(ancestors), 'Missing displayed ancestor'
        ancestors = ancestors[:depth]
        name, separator, annotation = row.partition(' ')
        assert name and '/' not in name, 'Invalid displayed node name'
        path = '/'.join([*ancestors, name])
        assert path not in result, 'Duplicate displayed path'
        if separator:
            shape_text, dtype_separator, dtype_text = annotation.rpartition(' ')
            assert dtype_separator, 'Missing array type descriptor'
            shape = ast.literal_eval(shape_text)
            assert isinstance(shape, tuple), 'Invalid displayed array shape'
            np.dtype(dtype_text)
            result[path] = 'array'
        else:
            result[path] = 'group'
        if ancestors:
            assert result['/'.join(ancestors)] == 'group', 'Array displayed as parent'
        ancestors.append(name)
    return result
