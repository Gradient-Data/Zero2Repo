"""Load the delivered product before acceptance module collection."""
import sys
from pathlib import Path

import pytest_asyncio.plugin


def pytest_addoption(pluginmanager):
    """Load async execution support even when plugin autoload is disabled."""
    if not pluginmanager.is_registered(pytest_asyncio.plugin):
        pluginmanager.register(pytest_asyncio.plugin, "asyncio")


_source = Path.cwd() / "src"
if not (_source / "velmora" / "__init__.py").is_file():
    raise FileNotFoundError(f"Delivered product package is missing: {_source / 'velmora'}")
sys.path.insert(0, str(_source))
