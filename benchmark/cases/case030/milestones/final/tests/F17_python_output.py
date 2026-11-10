# feature: F17
"""Executable Python delivery through each public translation entry."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import write_text, observe_call
from F01_helpers import translate_and_observe, require_source_error
from F02_helpers import python_namespace, require_scalar
from F03_helpers import ConfigurationSession, require_success
from F11_helpers import require_array_result
from F17_helpers import (PYTHON_PROGRAM, require_python_only, read_python_calls,
                         isolated_python_support)


def test_explicit_python_delivery(tmp_path):
    reference = python_namespace(PYTHON_PROGRAM)
    inputs = (0, 3, 7)
    expected = [reference['calculate'](n) for n in inputs]

    def exercise(module):
        for n, (total, array, values) in zip(inputs, expected):
            actual = module.calculate(n)
            require_scalar(actual[0], total)
            require_array_result(actual[1], array, exact=True)
            assert actual[2] == values

    interactive = tmp_path / 'interactive'
    translate_and_observe(PYTHON_PROGRAM, 'python', interactive, exercise)
    require_python_only(interactive)

    session = ConfigurationSession(tmp_path / 'commands')
    for command in ('compile', 'make'):
        root = session.root / command
        root.mkdir()
        source = write_text(root, 'kernel.py', PYTHON_PROGRAM)
        destination = root / 'delivery'
        args = [source] if command == 'compile' else ['-f', source]
        require_success(session.command(command, *args, '--language', 'python',
                                        '--output', destination, cwd=root))
        require_python_only(destination)
        observed = read_python_calls(destination, 'kernel',
                                     f'[delivered.calculate(n) for n in {inputs!r}]')
        assert len(observed) == len(expected)
        for actual, (total, array, values) in zip(observed, expected):
            assert actual == [total, array.tolist(), values]


def test_python_imports_annotations_and_validation(tmp_path):
    source = '''
import numpy as np
from math import sqrt as root
from zelvori.decorators import pure, inline, stack_array

@pure
@inline
def transform(x: float):
    return root(x)

@stack_array('a')
def calculate(x: float):
    a = np.array([x, 2.0, -3.0])
    a[1] = transform(x)
    #$ omp parallel for
    for i in range(3):
        a[i] = a[i] * 2.0
    return a
'''
    session = ConfigurationSession(tmp_path / 'annotations')
    submitted = write_text(session.root, 'annotated.py', source)
    delivery = session.root / 'delivery'
    require_success(session.command('compile', submitted, '--language', 'python',
                                    '--output', delivery))
    require_python_only(delivery)
    runtime = isolated_python_support(tmp_path / 'runtime')
    # Only the delivered Python file crosses into the runtime directory.
    import shutil
    isolated = tmp_path / 'isolated'
    isolated.mkdir()
    shutil.copyfile(delivery / 'annotated.py', isolated / 'annotated.py')
    observed = read_python_calls(isolated, 'annotated',
        '[delivered.calculate(x) for x in (4.0, 9.0, 25.0)]', runtime=runtime)
    assert len(observed) == 3
    expected = observe_call(
        python_namespace, source, cwd=session.root,
        consume=lambda namespace: [namespace['calculate'](x) for x in (4.0, 9.0, 25.0)],
    ).value
    for actual, reference in zip(observed, expected):
        from F00_oracle import host_numpy as np
        actual = np.asarray(actual)
        assert actual.shape == reference.shape
        assert np.all(np.isfinite(actual))
        # The middle value includes a square root followed by scaling; the
        # other values include scaling only. Propagate the stated individual
        # operation bounds instead of demanding bitwise floating equality.
        root_error = 1e-14 + 1e-13 * abs(reference[1] / 2)
        bound = 1e-14 + 1e-13 * np.abs(reference)
        bound[1] += 2 * root_error * (1 + 1e-13)
        assert np.all(np.abs(actual - reference) <= bound), (actual, reference, bound)

    invalid = 'def invalid(x: int):\n    x = 2.5\n    return x\n'
    path = write_text(session.root, 'invalid.py', invalid)
    failed = session.command('compile', path, '--language', 'python',
                             '--output', session.root / 'invalid_delivery')
    require_source_error(failed, path, 'semantic', {2})
