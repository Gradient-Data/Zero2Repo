# feature: F10
"""Build ordinary source wrappers for individual public mathematical calls."""

def mathematical_source(library, signatures):
    """Return typed submitted source; each exported function evaluates one call."""
    pieces = []
    for name, types in signatures.items():
        arguments = [f'a{i}' for i in range(len(types))]
        declaration = ', '.join(f'{arg}: {kind}' for arg, kind in zip(arguments, types))
        pieces.append(f'def evaluate_{name}({declaration}):\n'
                      f'    from {library} import {name}\n'
                      f'    return {name}({", ".join(arguments)})\n')
    return '\n'.join(pieces)
