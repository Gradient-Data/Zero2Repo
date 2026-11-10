# feature: F02
"""Scalar oracles and observations through compiled public entries."""
import math
import numbers
import sys
from pathlib import Path

# The acceptance runner also collects helper modules independently.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from F01_helpers import compile_source, require_native_program
from _helpers import run_command


def python_namespace(source):
    namespace = {}
    exec(source, namespace)
    return namespace


def require_scalar(actual, expected, bits=64):
    if isinstance(expected, (tuple, list)):
        assert len(actual) == len(expected)
        for value, reference in zip(actual, expected):
            require_scalar(value, reference, bits)
    elif isinstance(expected, numbers.Complex) and not isinstance(expected, numbers.Real):
        require_scalar(actual.real, expected.real, bits)
        require_scalar(actual.imag, expected.imag, bits)
    elif isinstance(expected, numbers.Real) and not isinstance(expected, numbers.Integral):
        absolute, relative = (1e-14, 1e-13) if bits == 64 else (1e-6, 1e-5)
        assert math.isfinite(actual)
        assert abs(actual - expected) <= absolute + relative * abs(expected), (actual, expected)
    else:
        assert actual == expected, (actual, expected)


def execute_script(directory, body, language, *, debug=False):
    source = "if __name__ == '__main__':\n" + "\n".join(
        "    " + line for line in body.splitlines()) + "\n"
    built, _ = compile_source(directory, source,
                              mode="--debug" if debug else None, language=language)
    assert built.returncode == 0, built
    require_native_program(directory / "submitted")
    return run_command([str(directory / "submitted")], cwd=directory)
