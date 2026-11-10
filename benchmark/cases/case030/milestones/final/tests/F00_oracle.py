# feature: F00
"""Host reference libraries used as independent oracles, never as product shell.

NumPy 2.1 and SymPy are the references the PRD names for array and symbolic
results. Tests build expected values, compare arrays and form symbols with the
host installations bound here, so these calls are attributed to the judge's
oracle rather than to the translator's public surface. Submitted source keeps
naming `numpy` directly, as the Contract states.
"""
import importlib

host_numpy = importlib.import_module("numpy")


def host_sympy():
    """Import SymPy on first use, inside the worker that needs it."""
    return importlib.import_module("sympy")
