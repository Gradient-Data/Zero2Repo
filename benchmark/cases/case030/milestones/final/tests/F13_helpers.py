# feature: F13
"""Cooperating source projects and public artifact consumers."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import run_command, run_python, write_text
from F03_helpers import require_success
from F04_helpers import delivered_extension
from F00_candidate import require_native_program


def module_project(root):
    root.mkdir(parents=True)
    sources = {
        'parcel/__init__.py': '',
        'parcel/base.py': '''
OFFSET = 13
factor = 2
factor += 3
print(271)

def scale(x: int):
    return x * factor + OFFSET

class Box:
    def __init__(self, value: int):
        self.value = value

    def read(self):
        return self.value * 2 + 1
''',
        'parcel/left.py': '''
from .base import scale as transform
from .base import OFFSET
from .base import Box

def left(x: int):
    item = Box(transform(x))
    return item.read() - OFFSET
''',
        'parcel/right.py': '''
import parcel.base as origin

def right(x: int):
    return origin.scale(x) + origin.OFFSET
''',
        'submitted.py': '''
from parcel.left import left as first
from parcel.right import right as second

def calculate(x: int, y: int):
    return first(x) - second(y)

if __name__ == '__main__':
    print(calculate(7, 2))
    print(calculate(-3, 5))
''',
    }
    for name, source in sources.items():
        write_text(root, name, source)
    return root / 'submitted.py'


def selected_project(root):
    root.mkdir(parents=True)
    write_text(root, 'chosen/kernel.py', '''
def calculate(x: int, y: int):
    return x * x - 3 * y + 7
''')
    write_text(root, 'chosen/runner.py', '''
from kernel import calculate

if __name__ == '__main__':
    print(calculate(9, 4))
    print(calculate(-5, 8))
''')
    # Unselected, unimported source is valid Python but invalid typed input.
    write_text(root, 'excluded.py', '''
def invalid(x: int):
    return nonexistent_name + x
''')
    files = ['chosen/kernel.py', 'chosen/runner.py']
    write_text(root, 'selection.txt', '\n'.join(files) + '\n')
    return files


def integer_program(path, session):
    require_native_program(path)
    result = run_command([path], cwd=path.parent, env=session.env)
    require_success(result)
    return [int(line) for line in result.stdout.splitlines()]


def extension_values(root, name, expressions, session):
    """Load the exact extension, never an uncompiled Python namesake."""
    extension = delivered_extension(root, name)
    result = run_python(f'''
import importlib.util, json
from pathlib import Path
spec = importlib.util.spec_from_file_location({name!r}, {str(extension)!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Path('observed.json').write_text(json.dumps([{', '.join(expressions)}]))
''', cwd=root, env=session.env)
    require_success(result)
    return ([int(line) for line in result.stdout.splitlines()],
            json.loads((root / 'observed.json').read_text()))


def check_selected_delivery(output, session):
    assert integer_program(output / 'chosen/runner', session) == [76, 8]
    assert extension_values(output / 'chosen', 'kernel',
        ['module.calculate(9, 4)', 'module.calculate(-5, 8)',
         'module.calculate(2, -7)'], session) == ([], [76, 8, 32])


def directory_project(root, *, cycle=False):
    root.mkdir(parents=True)
    write_text(root, 'pkg/__init__.py', '')
    write_text(root, 'pkg/one/__init__.py', '')
    write_text(root, 'pkg/two/__init__.py', '')
    write_text(root, 'pkg/one/base.py', 'def base():\n    return 17\n')
    write_text(root, 'pkg/two/middle.py',
        'from ..one.base import base\n\ndef middle():\n    return base() + 4\n')
    final_dir = 'one' if cycle else 'three'
    write_text(root, f'pkg/{final_dir}/__init__.py', '')
    write_text(root, f'pkg/{final_dir}/final.py',
        'from ..two.middle import middle\n\ndef final():\n    return middle() * 3\n')
    write_text(root, 'main.py',
        f"from pkg.{final_dir}.final import final\n\nif __name__ == '__main__':\n    print(final())\n")
    return ['main.py', 'pkg/one/base.py', 'pkg/two/middle.py',
            f'pkg/{final_dir}/final.py']
