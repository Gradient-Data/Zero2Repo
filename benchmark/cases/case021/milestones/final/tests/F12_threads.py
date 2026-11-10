# feature: F12
"""Python application progress and permission boundaries in native execution."""
from textwrap import dedent
from _helpers import temporary_project
from F01_helpers import translate_source, source_diagnostics
from F02_helpers import check_python_execution
from F03_helpers import REJECTIONS
from F08_helpers import build_native_binding
from F12_helpers import (PROGRESS_NATIVE, PROGRESS_SOURCE, PROGRESS_DRIVER,
                         progress_entry, run_thread_application)


def test_f12_t01():
    with temporary_project() as project:
        project.write('progress.h', PROGRESS_NATIVE)
        source = PROGRESS_SOURCE
        source += progress_entry('released', 'with nogil:')
        # A nogil declaration is used by both arms; it does not release the GIL.
        source += progress_entry('retained', 'if True:')
        build_native_binding(project, 'thread_progress', source)
        run_thread_application(project, 'thread_progress', PROGRESS_DRIVER + '''
for values in ([2, -7, 11, 4], list(range(-30, 41))):
    assert measure(subject.released, values) == 1
    assert measure(subject.retained, values) == 0
''')


def test_f12_t02():
    with temporary_project() as project:
        project.write('callback.h', r'''
#include <Python.h>
#include <pthread.h>
#include <stdlib.h>
typedef int (*callback_t)(void *);
struct task {
    callback_t callback;
    void *context;
    int result;
    PyObject *kind, *value, *traceback;
};
static void *worker(void *arg) {
    struct task *t = arg;
    PyGILState_STATE state = PyGILState_Ensure();
    PyThreadState *saved = PyEval_SaveThread();
    t->result = t->callback(t->context);
    PyEval_RestoreThread(saved);
    if (t->result == -1) PyErr_Fetch(&t->kind, &t->value, &t->traceback);
    PyGILState_Release(state);
    return NULL;
}
static int invoke(callback_t callback, void *context) {
    struct task t = {callback, context, 0, NULL, NULL, NULL};
    pthread_t thread;
    if (pthread_create(&thread, NULL, worker, &t)) abort();
    if (pthread_join(thread, NULL)) abort();
    if (t.result == -1) {
        PyGILState_STATE state = PyGILState_Ensure();
        PyErr_Restore(t.kind, t.value, t.traceback);
        PyGILState_Release(state);
    }
    return t.result;
}
''')
        build_native_binding(project, 'thread_callbacks', '''
cdef extern from "callback.h":
    int invoke(int (*callback)(void*) except -1, void*) except -1 nogil

cdef int callback(void* context) except -1 with gil:
    cdef object operation = <object>context
    operation()
    return 0

def native_callback(operation):
    with nogil:
        invoke(callback, <void*>operation)

def nested(operation):
    with nogil:
        with gil:
            operation()
''', libraries=['pthread'])
        run_thread_application(project, 'thread_callbacks', '''
import threading
class ApplicationFailure(Exception):
    pass
main_thread = threading.get_ident()
for call in (subject.nested, subject.native_callback):
    events = []
    def operation():
        events.append((threading.get_ident(), {'answer': sum(range(17))}))
    call(operation)
    assert len(events) == 1 and events[0][1] == {'answer': 136}
    if call == subject.native_callback:
        assert events[0][0] != main_thread
    failure = ApplicationFailure('application payload')
    def failing():
        operation()
        raise failure
    try:
        call(failing)
    except ApplicationFailure as caught:
        assert caught is failure
    else:
        raise AssertionError('Application exception was lost')
    assert len(events) == 2
''')


def test_f12_t03():
    check_python_execution('''
        cdef int needs_lock(object values):
            values.append(9)
            return len(values)
        def restored(values):
            cdef int result
            with nogil:
                with gil:
                    result = needs_lock(values)
            return result
        def raised(int value):
            with nogil:
                if value < 0:
                    raise ValueError(value)
            return value * 2
    ''', REJECTIONS + '''
def exercise(s):
    values = [2, 4]
    assert s.restored(values) == 3 and values == [2, 4, 9]
    assert s.raised(12) == 24
    try:
        s.raised(-13)
    except ValueError as error:
        assert error.args == (-13,)
    else:
        raise AssertionError('Explicit failure was lost')
''', reference=False)
    with temporary_project() as project:
        for name, source in {
            'object_access': '''
                def invalid(object values):
                    with nogil:
                        values.append(9)
            ''',
            'locked_call': '''
                cdef int needs_lock(int x):
                    return x + 1
                def invalid(int x):
                    cdef int result
                    with nogil:
                        result = needs_lock(x)
                    return result
            ''',
        }.items():
            path = project.write(name + '.pyx', dedent(source))
            result = translate_source(project, path)
            assert result.returncode != 0
            assert source_diagnostics(result, path), result.text('stderr')


def test_f12_t04():
    with temporary_project() as project:
        project.write('progress.h', PROGRESS_NATIVE)
        source = PROGRESS_SOURCE
        source += progress_entry('release_yes', 'with nogil(True):')
        source += progress_entry('release_no', 'with nogil(False):')
        # Enter unlocked, then vary only the source-constant acquisition condition.
        for name, condition in [('acquire_yes', 'True'), ('acquire_no', 'False')]:
            entry = progress_entry(name, f'with gil({condition}):')
            before, body = entry.split(f'    with gil({condition}):', 1)
            source += before + '    with nogil:\n' + f'        with gil({condition}):' + body.replace('\n        ', '\n            ').replace('\n    return', '\n    return')
        build_native_binding(project, 'conditional_threads', source)
        run_thread_application(project, 'conditional_threads', PROGRESS_DRIVER + '''
values = [13, -5, 7, 19, -2]
assert measure(subject.release_yes, values) == 1
assert measure(subject.release_no, values) == 0
assert measure(subject.acquire_yes, values) == 0
assert measure(subject.acquire_no, values) == 1
''')
        for keyword in ('nogil', 'gil'):
            source = ('def invalid(bint condition):\n'
                      '    with nogil(condition):\n        pass\n')
            if keyword == 'gil':
                source = ('def invalid(bint condition):\n    with nogil:\n'
                          '        with gil(condition):\n            pass\n')
            path = project.write('runtime_' + keyword + '.pyx', source)
            result = translate_source(project, path)
            assert result.returncode != 0
            assert source_diagnostics(result, path), result.text('stderr')
