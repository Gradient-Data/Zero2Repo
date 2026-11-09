# feature: F00
"""Bind legacy document templates to the product's published namespace."""
import json
from pathlib import Path

from _helpers import read_toml


def legacy_key(*, product_root=Path('/app')):
    """Read the unique legacy carrier declared by the actual product build."""
    document = read_toml(product_root / 'pyproject.toml')
    keys = [key for key, table in document.get('tool', {}).items()
            if isinstance(table, dict) and 'requires-velnora' in table]
    if len(keys) != 1:
        raise ValueError('Product must declare exactly one legacy configuration carrier')
    return keys[0]


def legacy_document(text, *, product_root=Path('/app')):
    """Render only explicit legacy table placeholders, preserving all values."""
    if 'tool.<legacy>' not in text:
        return text
    key = legacy_key(product_root=product_root)
    return text.replace('tool.<legacy>', 'tool.' + json.dumps(key, ensure_ascii=False))
