# feature: F04
"""Native delivery observations and independent source consumers."""
import importlib.machinery
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import run_command, run_python, write_text
from F03_helpers import require_success
from F00_candidate import require_native_extension, require_native_program

DELIVERY_SOURCE = '''def calculate(x: int, y: int) -> int:
    return x * x - 3 * y + 7

if __name__ == '__main__':
    print(calculate(9, 4))
    print(calculate(-5, 8))
'''


def delivery_source(root):
    return write_text(root, 'submitted.py', DELIVERY_SOURCE)


def delivered_extension(root, name='submitted'):
    # Use ordinary Python module selection. Multiple compatible extension
    # suffixes may coexist; the public import still has to select native code.
    spec = importlib.machinery.PathFinder.find_spec(name, [str(root)])
    assert spec is not None, (root, name)
    assert isinstance(spec.loader, importlib.machinery.ExtensionFileLoader), spec
    require_native_extension(spec.origin)
    return Path(spec.origin)


def call_delivered(root, session):
    extension = delivered_extension(root)
    result = run_python(f'''
import importlib.util, json
spec = importlib.util.spec_from_file_location('submitted', {str(extension)!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(json.dumps([module.calculate(x, y) for x, y in [(9, 4), (-5, 8), (2, -7)]]))
''', cwd=root, env=session.env)
    require_success(result)
    assert json.loads(result.stdout) == [76, 8, 32]


def run_delivered_program(root, session):
    require_native_program(root / 'submitted')
    result = run_command([root / 'submitted'], cwd=root, env=session.env)
    require_success(result)
    # Integer print whitespace differs between the native targets.
    assert [int(line) for line in result.stdout.splitlines()] == [76, 8]


def target_source(root, target):
    suffix = {'c': '.c', 'fortran': '.f90', 'c++': '.cpp'}[target]
    return root / ('__zelvori__' + os.environ.get('PYTEST_XDIST_WORKER', '')) / ('submitted' + suffix)


def consume_translation(root, target, session):
    """Compile the delivered program, without asking the product to build it."""
    source = target_source(root, target)
    assert source.is_file(), source
    program = source.with_name('prog_submitted' + source.suffix)
    compiler = {'c': 'gcc', 'fortran': 'gfortran'}[target]
    executable = root / 'independent_program'
    libraries = ['-lm'] if target == 'c' else []
    require_success(run_command([compiler, source, program, '-o', executable, *libraries], cwd=source.parent))
    result = run_command([executable], cwd=root, env=session.env)
    require_success(result)
    assert [int(line) for line in result.stdout.splitlines()] == [76, 8]


def require_invocation_error(result):
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert any(line.startswith('usage:') for line in result.stderr.splitlines()), result


def require_native_failure(result):
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert result.stdout.strip() or result.stderr.strip(), result
