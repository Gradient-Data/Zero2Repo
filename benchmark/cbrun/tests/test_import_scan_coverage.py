"""The import scan finds every way a file loads banned code, and nothing else.

Each case is a way an agent could reuse the upstream product without writing a plain import.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BENCHMARK = str(Path(__file__).resolve().parents[2])
for _name in [n for n in list(sys.modules) if n == "cbrun" or n.startswith("cbrun.")]:
    del sys.modules[_name]
sys.path.insert(0, _BENCHMARK)

from cbrun.denylist import scan_text_imports  # noqa: E402


def hits(text: str, suffix: str, token: str = "velqora") -> list[int]:
    return [line for line, _token in scan_text_imports(text, suffix, (token,))]


# Python: a name reached without an import statement ------------------------------------------

def test_python_import_by_name_counts() -> None:
    assert hits("import importlib\nmod = importlib.import_module('velqora')\n", ".py") == [2]
    assert hits("mod = __import__('velqora')\n", ".py") == [1]
    assert hits("from importlib import import_module\nm = import_module('velqora.core')\n", ".py") == [2]


def test_python_a_name_only_asked_about_counts() -> None:
    """Checking the product is installed and then loading it by hand is still loading it."""
    assert hits("import importlib.util\nspec = importlib.util.find_spec('velqora')\n", ".py") == [2]


def test_python_an_unrelated_literal_is_not_an_import() -> None:
    assert hits("name = 'velqora'\nprint('velqora')\n", ".py") == []
    assert hits("import importlib\nmod = importlib.import_module(name)\n", ".py") == []


def test_python_a_module_of_our_own_named_like_the_product_is_not_a_hit() -> None:
    assert hits("import velqora_helpers\nfrom velqoraish import x\n", ".py") == []


# Rust: a crate used by its path, with no use statement ---------------------------------------

def test_rust_a_fully_qualified_crate_path_counts() -> None:
    assert hits("fn main() { let v = velqora::parse(\"x\"); }\n", ".rs") == [1]
    assert hits("fn main() { let v = ::velqora::parse(\"x\"); }\n", ".rs") == [1]


def test_rust_use_still_counts_and_a_neighbour_does_not() -> None:
    assert hits("use velqora::parse;\n", ".rs") == [1]
    assert hits("use velqora_derive::Parse;\nfn f() { velqora_extra::go(); }\n", ".rs") == []


def test_rust_a_local_module_or_comment_is_not_a_crate_use() -> None:
    assert hits("// velqora::parse is what we must not use\n", ".rs") == []
    assert hits("let s = \"velqora::parse\";\n", ".rs") == []
    assert hits("mod velqora;\n", ".rs") == []


# Notebooks: code cells are code ---------------------------------------------------------------

NOTEBOOK = """{
 "cells": [
  {"cell_type": "markdown", "source": ["# velqora notes\\n"]},
  {"cell_type": "code", "source": ["import velqora\\n", "velqora.run()\\n"]}
 ],
 "metadata": {"kernelspec": {"language": "python"}},
 "nbformat": 4
}
"""


def test_a_notebook_code_cell_counts() -> None:
    # The line of the notebook file that holds the cell, so a reader can open it there.
    assert hits(NOTEBOOK, ".ipynb") == [4]


def test_a_notebook_without_the_product_is_clean() -> None:
    assert hits(NOTEBOOK.replace("velqora", "pandas"), ".ipynb") == []


# Cython: its own import syntax ----------------------------------------------------------------

def test_cython_cimport_counts() -> None:
    assert hits("cimport velqora\n", ".pyx") == [1]
    assert hits("from velqora cimport parse\n", ".pxd") == [1]
    assert hits("import velqora\n", ".pyx") == [1]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
