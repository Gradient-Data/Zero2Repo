# feature: F08
"""C interoperability measured by native execution and independent consumers."""
from textwrap import dedent
from _helpers import temporary_project, build_extensions
from F02_helpers import check_python_execution
from F03_helpers import REJECTIONS
from F06_helpers import build_cooperating_module, run_cooperating_application
from F08_helpers import build_native_binding


def test_f08_t01():
    with temporary_project() as project:
        project.write('external.h', '''
#ifndef EXTERNAL_H
#define EXTERNAL_H
struct NativeRecord { double hidden; int value; char padding[7]; int other; };
extern int native_total;
extern struct NativeRecord native_record;
enum { NATIVE_STEP = 7 };
int update_native(int *values, int count, struct NativeRecord *record);
#endif
''')
        project.write('external.c', '''
#include "external.h"
int native_total = 11;
struct NativeRecord native_record = { 2.5, -3, {0}, 19 };
int update_native(int *values, int count, struct NativeRecord *record) {
    int sum = 0;
    for (int i = 0; i < count; ++i) {
        values[i] += record->value + i;
        sum += values[i];
    }
    record->value += count;
    native_total += sum;
    return sum * NATIVE_STEP;
}
''')
        build_native_binding(project, 'external_use', '''
            cdef extern from "external.h":
                struct NativeRecord:
                    int value
                int native_total
                NativeRecord native_record
                enum: NATIVE_STEP
                int update_native(int *, int, NativeRecord *)
            def apply(int x):
                global native_total
                cdef int values[3]
                values[:] = [x, x+2, x-1]
                native_total += NATIVE_STEP
                result = update_native(values, 3, &native_record)
                return result, values, native_total, native_record.value, NATIVE_STEP
        ''', native_sources=('external.c',))
        run_cooperating_application(project, '''
            import external_use as s
            assert s.apply(4) == (49, [1, 4, 2], 25, 0, 7)
            assert s.apply(-2) == (-14, [-2, 1, -1], 30, 3, 7)
        ''')


def test_f08_t02():
    with temporary_project() as project:
        build_native_binding(project, 'standard_use', '''
            from libc.math cimport sqrt, sin, cos
            from libc.stdlib cimport malloc, free
            from libc.string cimport memcpy, memmove, memset, memcmp, strlen
            from libc.stdio cimport FILE, tmpfile, fwrite, fread, fseek, fclose, SEEK_SET
            from posix.unistd cimport pipe, read, write, close, getpid, getppid, getuid, getgid
            def use(double x, bytes payload):
                cdef Py_ssize_t n = len(payload)
                cdef const char *data = payload
                cdef char *buffer = <char *>malloc(n+2)
                cdef FILE *stream = NULL
                cdef int descriptors[2]
                cdef char received[32]
                if buffer == NULL: raise MemoryError()
                try:
                    memcpy(buffer, data, n)
                    buffer[n] = 0
                    original = buffer[:n]
                    length = strlen(buffer)
                    equal = memcmp(buffer, data, n) == 0
                    memmove(buffer+1, buffer, n)
                    memset(buffer, 33, 1)
                    moved = buffer[:n+1]
                    stream = tmpfile()
                    if stream == NULL: raise OSError('tmpfile failed')
                    if fwrite(data, 1, n, stream) != n: raise OSError('fwrite failed')
                    if fseek(stream, 0, SEEK_SET) != 0: raise OSError('fseek failed')
                    if fread(buffer, 1, n, stream) != n: raise OSError('fread failed')
                    file_result = buffer[:n]
                    if pipe(descriptors) != 0: raise OSError('pipe failed')
                    try:
                        if write(descriptors[1], data, n) != n: raise OSError('write failed')
                        if read(descriptors[0], received, n) != n: raise OSError('read failed')
                        descriptor_result = received[:n]
                    finally:
                        close(descriptors[0])
                        close(descriptors[1])
                    return (sqrt(x), sin(x), cos(x), original, length, equal,
                            moved, file_result, descriptor_result,
                            getpid(), getppid(), getuid(), getgid())
                finally:
                    if stream != NULL: fclose(stream)
                    free(buffer)
        ''', libraries=('m',))
        run_cooperating_application(project, r'''
            import math, os
            import standard_use as s
            for x, payload in ((2.25, b'abc\x00xy'), (7.5, b'KLMN')):
                result = s.use(x, payload)
                for actual, expected in zip(result[:3], (math.sqrt(x), math.sin(x), math.cos(x))):
                    assert math.isclose(actual, expected, rel_tol=1e-14, abs_tol=1e-14)
                assert result[3:9] == (payload, len(payload.split(b'\x00')[0]), True,
                                       b'!' + payload, payload, payload)
                assert result[9:] == (os.getpid(), os.getppid(), os.getuid(), os.getgid())
        ''')


def test_f08_t03():
    check_python_execution('''
        from cpython.long cimport PyLong_FromLong, PyLong_AsLong
        from cpython.float cimport PyFloat_FromDouble, PyFloat_AsDouble
        from cpython.list cimport PyList_New, PyList_Append, PyList_GetItem
        from cpython.dict cimport PyDict_New, PyDict_SetItem, PyDict_GetItem
        cdef extern from *:
            """
            static long supplied_fold(long a, long b) { return a * 5 - b * 2; }
            """
            long supplied_fold(long, long)
        def operate(long value, double fraction):
            integer = PyLong_FromLong(value)
            real = PyFloat_FromDouble(fraction)
            items = PyList_New(0)
            PyList_Append(items, integer)
            PyList_Append(items, real)
            mapping = PyDict_New()
            PyDict_SetItem(mapping, 'items', items)
            return (supplied_fold(PyLong_AsLong(integer), 3),
                    PyFloat_AsDouble(real), <object>PyList_GetItem(items, 0),
                    <object>PyDict_GetItem(mapping, 'items'), mapping)
    ''', '''
        def exercise(s):
            for value, fraction in ((19, 2.5), (-8, -0.125)):
                assert s.operate(value, fraction) == (
                    value * 5 - 6, fraction, value, [value, fraction],
                    {'items': [value, fraction]})
            return True
    ''', reference=False)


def test_f08_t04():
    check_python_execution('''
        def binary(bytes value):
            cdef const char *pointer = value
            return <bytes>pointer, pointer[:len(value)]
        def decode(bytes value):
            cdef const char *pointer = value
            return pointer[:len(value)].decode('utf-8')
        def encode(unicode value):
            cdef bytes encoded = value.encode('utf-8')
            cdef const char *pointer = encoded
            return pointer[:len(encoded)]
    ''', REJECTIONS + dedent(r'''
        def exercise(s):
            for value in (b'alpha\x00omega\xff', b'\x00\x80tail', b'', b'plain'):
                terminated, counted = s.binary(value)
                assert type(terminated) is bytes and type(counted) is bytes
                assert terminated == value.split(b'\x00')[0]
                assert counted == value
            for text in ('A\x00é中🙂', '', 'plain'):
                encoded = text.encode('utf-8')
                assert s.encode(text) == encoded
                assert s.decode(encoded) == encoded.decode('utf-8')
            for value in (b'\xff', b'\xc0\xaf', b'\xed\xa0\x80', b'\xf4\x90\x80\x80', b'\xe2\x82'):
                rejects(UnicodeDecodeError, s.decode, value)
            rejects(UnicodeEncodeError, s.encode, '\ud800')
            return True
    '''), reference=False)


def test_f08_t05():
    with temporary_project() as project:
        project.write('linked.h', 'long linked_apply(long);\n')
        project.write('linked.c', '''
#include <Python.h>
#include "linked_provider.h"
long linked_apply(long value) {
    struct ExportedRecord record;
    record.value = value;
    exported_total += 4;
    exported_adjust(&record, 3);
    return record.value + exported_total;
}
''')
        build_native_binding(project, 'linked_provider', '''
            cdef public struct ExportedRecord:
                long value
            cdef public long exported_total = 13
            cdef public void exported_adjust(ExportedRecord *record, long step):
                record.value = record.value * 2 + step
                global exported_total
                exported_total += record.value
            cdef extern from "linked.h":
                long linked_apply(long)
            def use(long value):
                result = linked_apply(value)
                return result, exported_total
        ''', native_sources=('linked.c',))
        run_cooperating_application(project, '''
            import linked_provider as s
            assert s.use(5) == (43, 30)
            assert s.use(-4) == (24, 29)
        ''')


def test_f08_t06():
    with temporary_project() as project:
        build_cooperating_module(project, 'api_provider', '''
            cdef public api class Record [object RecordObject, type RecordType]:
                cdef public int value
                def __init__(self, int value): self.value = value
                def read(self): return self.value
            cdef api int adjust(Record record, int amount):
                record.value = record.value * 3 + amount
                return record.value - amount
        ''')
        project.write('api_consumer.c', '''
#include <Python.h>
#include "api_provider_api.h"
static PyObject *apply(PyObject *self, PyObject *args) {
    PyObject *item;
    int amount, result;
    if (!PyArg_ParseTuple(args, "Oi", &item, &amount)) return NULL;
    if (import_api_provider() < 0) return NULL;
    if (!PyObject_TypeCheck(item, &RecordType)) {
        PyErr_SetString(PyExc_TypeError, "Expected exported record");
        return NULL;
    }
    result = adjust((struct RecordObject *)item, amount);
    if (PyErr_Occurred()) return NULL;
    return PyLong_FromLong(result);
}
static PyMethodDef methods[] = {{"apply", apply, METH_VARARGS, NULL}, {NULL, NULL, 0, NULL}};
static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "api_consumer", NULL, -1, methods};
PyMODINIT_FUNC PyInit_api_consumer(void) { return PyModule_Create(&module); }
''')
        # Only the consumer's C source is linked: the provider is reached by import.
        result = build_extensions(project, [{'name': 'api_consumer',
                                  'sources': ['api_consumer.c'],
                                  'include_dirs': [str(project.root)]}],
                                  env=project.environment())
        assert result.returncode == 0, result.text('stderr') + result.text()
        run_cooperating_application(project, '''
            import api_consumer, api_provider
            class Derived(api_provider.Record): pass
            for record, amount, expected, state in (
                    (api_provider.Record(7), 2, 21, 23),
                    (Derived(-4), 5, -12, -7)):
                assert api_consumer.apply(record, amount) == expected
                assert record.read() == state
            record = api_provider.Record(2)
            assert api_consumer.apply(record, -1) == 6
            assert api_consumer.apply(record, 4) == 15
            assert record.read() == 19
        ''')
