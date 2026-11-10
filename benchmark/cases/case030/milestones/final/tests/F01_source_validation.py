# feature: F01
"""Acceptance checks for typed source validation through public entries."""

import sys
from pathlib import Path

# The acceptance runner uses importlib collection for these standalone files.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from F00_oracle import host_numpy as np

from _helpers import run_command
from F00_candidate import require_native_program
from F01_helpers import (
    compile_source, require_no_runnable_artifact, require_source_error,
    translate_and_observe,
)


def test_annotation_and_inference(tmp_path):
    source = '''
from typing import TypeAlias
from zelvori.decorators import inline, private
Real: TypeAlias = float
Vector: TypeAlias = 'float[:]'

@inline
@private
def hidden(x):
    return x + x

def inferred(x: int):
    local = x + 3
    return local

def declared(x: 'Real') -> float:
    local: float = x
    return local

def vector(x: Vector):
    local = x[0]
    return local

def calls_hidden(x: int):
    return hidden(x)

def recursive(x: int) -> int:
    if x <= 0:
        return 1
    return x * recursive(x - 1)
'''
    def consume(module):
        return [(module.inferred(x), module.declared(float(x)),
                 module.calls_hidden(x)) for x in (-7, 4)], module.vector(
                     np.array([2.5, -1.0])), module.recursive(5)

    for language in ("c", "fortran"):
        result = translate_and_observe(source, language, tmp_path / language, consume)
        assert result.value == ([(-4, -7.0, -14), (7, 4.0, 8)], 2.5, 120)


def test_required_annotations(tmp_path):
    cases = [
        ("ordinary", "def f(x: int):\n    y = x\n    return y\n", None),
        ("recursive", "def f(x: int) -> int:\n    if x <= 0:\n        return 0\n    return f(x-1)\n", None),
        ("argument", "def f(x):\n    return x\n", {1}),
        ("result", "def f(x: int):\n    if x <= 0:\n        return 0\n    return f(x-1)\n", set()),
    ]
    for name, source, error_lines in cases:
        result, path = compile_source(tmp_path / name, source)
        if error_lines is None:
            assert result.returncode == 0, result
        else:
            require_source_error(result, path, "semantic", error_lines or None)
        require_no_runnable_artifact(path.parent)


def test_scalar_kinds_and_precisions(tmp_path):
    declarations = ["bool", "int8", "int16", "int32", "int64", "float32",
                    "float64", "complex64", "complex128", "int", "float", "complex"]
    source = "from numpy import array, int8, int16, int32, int64, float32, float64, complex64, complex128\n"
    for index, declaration in enumerate(declarations):
        source += (f"\ndef scalar_{index}(x: '{declaration}'):\n"
                   "    local = x\n    return array([local])\n")
    values = [True, -101, -30001, -2000000001, -4000000001,
              1.25, -2.5, 1.5-2.25j, -3.5+4.25j, 71, -6.25, 7.5-8.5j]
    dtypes = [np.bool_, np.int8, np.int16, np.int32, np.int64, np.float32,
              np.float64, np.complex64, np.complex128, np.int_, np.float64, np.complex128]
    converters = [bool, np.int8, np.int16, np.int32, np.int64, np.float32,
                  np.float64, np.complex64, np.complex128, int, float, complex]
    samples = [(value, not value if index == 0 else -value)
               for index, value in enumerate(values)]
    def consume(module):
        return [[getattr(module, f"scalar_{index}")(convert(value))
                 for value in pair]
                for index, (convert, pair) in enumerate(zip(converters, samples))]

    for language in ("c", "fortran"):
        result = translate_and_observe(source, language, tmp_path / language, consume)
        for actual_pair, dtype, pair in zip(result.value, dtypes, samples):
            for actual, value in zip(actual_pair, pair):
                assert actual.dtype == np.dtype(dtype)
                np.testing.assert_array_equal(actual, np.array([value], dtype=dtype))


def test_string_values_and_output(tmp_path):
    source = '''
def literal():
    text = 'spectral sample'
    return text

def echo(text: str):
    local = text
    return local

def compare(left: str, right: str):
    return left == right, left != right
'''
    def consume(module):
        return (module.literal(), module.echo("first sample"),
                module.echo("other value"), module.compare("equal", "equal"),
                module.compare("left", "right"))

    for language in ("c", "fortran"):
        result = translate_and_observe(source, language, tmp_path / language, consume)
        assert result.value == ("spectral sample", "first sample", "other value",
                                (True, False), (False, True))
        directory = tmp_path / (language + "_print")
        result, path = compile_source(directory, "if __name__ == '__main__':\n    text = 'visible  sample'\n    print(text)\n", mode=None, language=language)
        assert result.returncode == 0, result
        require_native_program(directory / "submitted")
        printed = run_command([str(directory / "submitted")], cwd=directory)
        assert printed.returncode == 0, printed
        assert printed.stdout.splitlines() == ["visible  sample"]
    result = translate_and_observe('''
def join():
    left = 'spectrum'
    right = ' sample'
    return left + right
''', "fortran", tmp_path / "join", lambda module: module.join())
    assert result.value == "spectrum sample"


def test_fixed_types_and_read_only_values(tmp_path):
    cases = [
        ("valid", "def f(x: int):\n    y = x\n    y = x + 1\n    return y\n", None),
        ("type", "def f(x: int):\n    y = x\n    y = 1.5\n    return y\n", {3}),
        ("rank", "from numpy import ones\ndef f():\n    a = ones(3)\n    a = ones((2, 3))\n    return a\n", {4}),
        ("branch", "def f(flag: bool):\n    if flag:\n        y = 1\n    else:\n        y = 1.5\n    return y\n", {5}),
        ("constant", "from typing import Final\ndef f():\n    x: Final[int] = 3\n    x = 4\n    return x\n", {4}),
        ("readonly", "from typing import Final\ndef f(x: 'Final[float[:]]', y: 'float[:]'):\n    x[:] += y\n", {3}),
        ("valid_mutation", "def f(x: 'float[:]', y: 'float[:]'):\n    x[:] += y\n", None),
        ("valid_constant", "from typing import Final\ndef f():\n    x: Final[int] = 3\n    return x\n", None),
        ("valid_readonly", "from typing import Final\ndef f(x: 'Final[float[:]]'):\n    y = x[0]\n    return y\n", None),
    ]
    for name, source, error_lines in cases:
        result, path = compile_source(tmp_path / name, source)
        if error_lines is None:
            assert result.returncode == 0, result
        else:
            require_source_error(result, path, "semantic", error_lines or None)


def test_validation_modes_and_source_errors(tmp_path):
    valid = "def f(x: int):\n    return x\n"
    for mode in ("--semantic-only",):
        result, path = compile_source(tmp_path / mode[2:], valid, mode=mode)
        assert result.returncode == 0, result
        require_no_runnable_artifact(path.parent)
    cases = [
        ("syntax", "def f(x: int):\n    return (x + )\n", "None", None, "--syntax-only"),
        ("name", "def f(x: int):\n    return undefined_value\n", "semantic", {2}, "--semantic-only"),
        ("import", "from unavailable_scientific_package import value\ndef f():\n    return value\n", "syntactic", None, "--semantic-only"),
        ("call", "def f(x: int):\n    return x\n\ndef g():\n    return f(1.5)\n", "semantic", {5}, "--semantic-only"),
    ]
    for name, source, stage, lines, mode in cases:
        result, path = compile_source(tmp_path / name, source, mode=mode)
        require_source_error(result, path, stage, lines)
        require_no_runnable_artifact(path.parent)
