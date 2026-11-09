# feature: F16
"""Import-time native execution, failures, dependencies and hook removal."""
import os
from _helpers import temporary_project
from F16_helpers import import_time_values


def test_f16_t01():
    with temporary_project() as project:
        project.write('working.pyx', '''
cdef int transform(int x):
    return x * x - 3 * x
def values(xs):
    return [transform(x) for x in xs]
''')
        assert import_time_values(project, '''
import working
print(json.dumps(working.values([-4, 0, 7])))
''') == [28, 0, 28]
        project.write('invalid_source.pyx', 'def broken(:\n')
        project.write('invalid_native.pyx', '''
cdef extern from *:
    """
    #error Authored native compilation failure
    """
def value():
    return 12
''')
        assert import_time_values(project, '''
import importlib
outcomes = []
for name in ('invalid_source', 'invalid_native'):
    try:
        importlib.import_module(name)
    except ImportError:
        outcomes.append('refused')
    else:
        outcomes.append('loaded')
print(json.dumps(outcomes))
''') == ['refused', 'refused']


def test_f16_t02():
    with temporary_project() as project:
        project.write('execution_failure.pyx', '''
cdef int initial_value = 17
raise ValueError('authored execution failure', initial_value)
''')
        # Follow the exception chain without fixing the number of wrappers or
        # matching human-readable compiler diagnostics.
        outcome = import_time_values(project, '''
import importlib
try:
    importlib.import_module('execution_failure')
except ImportError as error:
    pending = [error]
    seen = set()
    original = []
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, ValueError):
            original.append(list(current.args))
        for linked in (current.__cause__, current.__context__):
            if linked is not None:
                pending.append(linked)
    outcome = ['refused', original]
else:
    outcome = ['loaded', []]
print(json.dumps(outcome))
''')
        assert outcome[0] == 'refused'
        assert ['authored execution failure', 17] in outcome[1], outcome


def test_f16_t03():
    with temporary_project() as project:
        source = project.write('configured.pyx', '''
cdef extern from "native_api.h":
    int native_value(int)
def values(xs):
    return [native_value(x) for x in xs]
''')
        header = project.write('headers/native_api.h', '''
#define HEADER_OFFSET 9
int native_value(int);
''')
        project.write('native.c', '''
#include "native_api.h"
#ifndef BUILD_FACTOR
#error Custom build macro is required
#endif
int native_value(int x) { return x * BUILD_FACTOR + HEADER_OFFSET; }
''')
        project.write('configured.pyxbld', '''
from pathlib import Path
from setuptools import Extension

def make_ext(modname, pyxfilename):
    root = Path(pyxfilename).parent
    return Extension(modname, sources=[pyxfilename, str(root / 'native.c')],
                     include_dirs=[str(root / 'headers')],
                     define_macros=[('BUILD_FACTOR', '6')])
''')
        project.write('configured.pyxdep', 'headers/native_api.h\n')
        observation = '''
import configured
print(json.dumps(configured.values([-3, 0, 8])))
'''
        assert import_time_values(project, observation) == [-9, 9, 57]
        # Only the declared dependency changes. A fresh interpreter shares the
        # build directory, so a stale extension cannot supply the new result.
        header.write_text('#define HEADER_OFFSET -4\nint native_value(int);\n')
        newer = max(source.stat().st_mtime, header.stat().st_mtime) + 5
        os.utime(header, (newer, newer))
        assert import_time_values(project, observation) == [-22, -4, 44]


def test_f16_t04():
    # Each arm gets identical sources and empty build state in a new process.
    for disable in (False, True):
        with temporary_project() as project:
            project.write('discoverable.pyx', '''
def value(int x):
    return x * 5 - 8
''')
            assert import_time_values(project, f'''
import importlib
if {disable!r}:
    veximport.uninstall(*hooks)
try:
    subject = importlib.import_module('discoverable')
except ModuleNotFoundError as error:
    outcome = ['missing', error.name]
else:
    outcome = ['loaded', [subject.value(x) for x in (-2, 0, 9)]]
print(json.dumps(outcome))
''') == (['missing', 'discoverable'] if disable else ['loaded', [-18, -8, 37]])
