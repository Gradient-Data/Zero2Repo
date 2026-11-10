# feature: F17
"""Interactive fragments, call-dependent routines and local IPython cells."""
from _helpers import temporary_project, build_native, tool_path, run_command, run_python
from F06_helpers import run_cooperating_application, build_cooperating_module


def test_f17_t01():
    with temporary_project() as project:
        run_cooperating_application(project, '''
import velora
selected = 101
local_first = 103
global_only = 7

def execute():
    selected = 11
    local_first = 13
    events = []
    source = """
cdef long answer = selected * local_first + global_only
events.append(answer)
return answer
"""
    first = velora.inline(source, selected=3, quiet=True)
    second = velora.inline(source, selected=-2, quiet=True)
    assert [first, second] == [46, -19]
    assert events == [46, -19]
execute()
''')


def test_f17_t02():
    with temporary_project() as project:
        run_cooperating_application(project, '''
import velora
from Velora.Compiler.Errors import CompileError
assert velora.inline("cdef long result = x * x - 2\\nreturn result", x=5, quiet=True) == 23
values = velora.inline("""
cdef long squared = x * x
cdef double scaled = x / 2.0
cdef float tenth = x / 10.0
items = [squared, x + 1]
""", x=6, quiet=True)
assert values['squared'] == 36
assert values['scaled'] == 3.0
# A native single-precision local holds the value rounded to that precision;
# executing the fragment as plain Python would keep the double 0.6.
import struct
assert values['tenth'] == struct.unpack('f', struct.pack('f', 0.6))[0] != 0.6
assert values['items'] == [36, 7]
try:
    velora.inline("cdef long broken =", quiet=True)
except CompileError:
    pass
else:
    raise AssertionError('Invalid fragment delivered a successful result')
''')


def test_f17_t03():
    with temporary_project() as project:
        # A real source file is needed by the public routine-selection entry.
        project.write('ordinary.py', '''
def combine(left, right, events):
    result = left * 2 + right
    events.append(result)
    return result
''')
        run_cooperating_application(project, '''
import velora
from ordinary import combine
compiled = velora.compile(combine)
actual_events, expected_events = [], []
for left, right in [(4, -3), (1.5, 0.25), ('ab', 'z'), (-6, 8)]:
    expected = combine(left, right, expected_events)
    actual = compiled(left, right, actual_events)
    assert actual == expected
    assert type(actual) is type(expected)
    assert actual_events == expected_events
assert actual_events == [5, 3.25, 'ababz', -4]
''')
        # Shared native declarations supply an observable use for argument typing:
        # direct interpretation cannot access these hidden declared attributes.
        project.write('native_records.pxd', '''
cdef class IntegerRecord:
    cdef long number
cdef class RealRecord:
    cdef double number
''')
        build_cooperating_module(project, 'native_records', '''
            cdef class IntegerRecord:
                def __init__(self, number): self.number = number
            cdef class RealRecord:
                def __init__(self, number): self.number = number
        ''')
        project.write('native_reader.py', '''
def read(record, events):
    result = record.number * 2 + 1
    events.append(result)
    return result
''')
        result = run_python('''
import velora
from native_reader import read
from native_records import IntegerRecord, RealRecord
compiled = velora.compile(read)
events = []
for record, expected in [(IntegerRecord(7), 15), (RealRecord(1.25), 3.5), (IntegerRecord(-4), -7)]:
    try:
        record.number
    except AttributeError:
        pass
    else:
        raise AssertionError('Native attribute unexpectedly visible')
    actual = compiled(record, events)
    assert actual == expected
    assert type(actual) is type(expected)
assert events == [15, 3.5, -7]
''', product_dir=project.root, env=project.environment())
        assert result.returncode == 0, result.text('stderr') + result.text()


def test_f17_t04():
    with temporary_project() as project:
        run_cooperating_application(project, '''
import contextlib
import io
from IPython.core.interactiveshell import InteractiveShell
ip = InteractiveShell.instance()
ip.extension_manager.load_extension('velora')
ip.run_cell_magic('velora', '', """
import math
def root_sum(double x, double y):
    return math.sqrt(x) + math.sqrt(y)
""")
assert ip.user_ns['root_sum'](9, 16) == 7.0
assert ip.user_ns['root_sum'](25, 144) == 17.0
# The earlier cell publishes math, but a new module must import it itself.
assert ip.user_ns['math'].sqrt(81) == 9.0
errors = io.StringIO()
rejected = False
with contextlib.redirect_stderr(errors):
    try:
        ip.run_cell_magic('velora', '', """
def needs_external(double x):
    return math.sqrt(x)
""")
        if 'needs_external' in ip.user_ns:
            ip.user_ns['needs_external'](49)
    except NameError:
        rejected = True
if not rejected:
    assert errors.getvalue().strip(), 'Missing compilation failure report'
    assert 'needs_external' not in ip.user_ns
# An explicit import in this cell makes the same dependency usable.
ip.run_cell_magic('velora', '', """
import math
def declared_external(double x):
    return math.sqrt(x)
""")
assert ip.user_ns['declared_external'](49) == 7.0
''')


def test_f17_t05():
    with temporary_project() as project:
        library_source = project.write('provider.c', 'int provided(int x) { return x * 7; }\n')
        obj = project.path('provider.o')
        result = build_native(tool_path('cc'), [library_source], obj, before=['-c', '-fPIC'])
        assert result.returncode == 0, result.text('stderr')
        archive = project.path('libcellprovider.a')
        result = run_command([tool_path('ar'), 'rcs', archive, obj])
        assert result.returncode == 0, result.text('stderr')
        headers = project.path('headers')
        project.write('headers/cell_api.h', '''
#ifdef __cplusplus
extern "C" {
#endif
int provided(int);
int external_value(int);
#ifdef __cplusplus
}
#endif
#define CELL_OFFSET 5
''')
        native_source = project.write('cell_source.cpp', '''
#include "cell_api.h"
#include <vector>
extern "C" int external_value(int x) {
    std::vector<int> parts = {provided(x), CELL_OFFSET};
    return parts[0] + parts[1];
}
''')
        options = f'--cplus -I {headers} -S {native_source} -L {project.root} -l cellprovider'
        run_cooperating_application(project, f'''
import contextlib
import io
from IPython.core.interactiveshell import InteractiveShell
ip = InteractiveShell.instance()
ip.extension_manager.load_extension('velora')
ip.run_cell_magic('velora', {options!r}, """
cdef extern from "cell_api.h":
    int external_value(int)
def native_cell(int x):
    return external_value(x)
""")
assert [ip.user_ns['native_cell'](x) for x in (-4, 0, 9)] == [-23, 5, 68]
# A compiler-stage failure must be reported and must not overwrite a live
# definition or publish a fresh one from the failed module.
previous = ip.user_ns['native_cell']
errors = io.StringIO()
with contextlib.redirect_stderr(errors):
    ip.run_cell_magic('velora', '', \'\'\'
cdef extern from *:
    """
    #error Authored cell compilation failure
    """
def native_cell(int x):
    return -100
def failed_cell_definition():
    return 10
\'\'\')
assert errors.getvalue().strip(), 'Missing native build failure report'
assert 'failed_cell_definition' not in ip.user_ns
assert ip.user_ns['native_cell'] is previous
assert ip.user_ns['native_cell'](2) == 19
''')
