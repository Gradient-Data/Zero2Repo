"""Fail preparation on missing imports and report their interpreter and locations."""
import importlib
import sys
import tomllib
from pathlib import Path

print("Interpreter:", sys.executable, sys.version, flush=True)
modules = ["numpy", "scipy", "pytest", "matplotlib", "slycot", "cvxopt", "pandas"]
if "--project" in sys.argv:
    project = tomllib.loads(Path("pyproject.toml").read_text())
    modules.extend(sorted({name.split(".")[0] for name in project["tool"]["setuptools"]["packages"]}))
for name in modules:
    module = importlib.import_module(name)
    print("Import:", name, module.__file__, flush=True)
