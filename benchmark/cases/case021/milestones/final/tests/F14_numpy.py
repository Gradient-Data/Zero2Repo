# feature: F14
"""Typed NumPy storage and executable scalar ufunc semantics."""
from textwrap import dedent
from _helpers import temporary_project
from F01_helpers import translate_source, source_diagnostics
from F03_helpers import REJECTIONS
from F12_helpers import PROGRESS_NATIVE, PROGRESS_SOURCE, run_thread_application
from F14_helpers import build_numpy


def test_f14_t01():
    with temporary_project() as project:
        build_numpy(project, 'typed_arrays', '''
            cimport numpy as np
            def update(np.ndarray[np.float64_t, ndim=2] values):
                cdef Py_ssize_t i, j
                cdef double total = 0
                for i in range(values.shape[0]):
                    for j in range(values.shape[1]):
                        total += values[i, j]
                        values[i, j] = values[i, j] * 2 + i - j
                return (values.shape[0], values.shape[1]), total
        ''')
        run_thread_application(project, 'typed_arrays', REJECTIONS + dedent('''
            import numpy as np
            for shape in ((2, 5), (4, 3)):
                values = np.arange(np.prod(shape), dtype=np.float64).reshape(shape) - 7.5
                before = values.copy()
                dimensions, total = subject.update(values)
                assert dimensions == shape
                assert total == sum(before.flat)
                expected = np.array([[2*before[i,j]+i-j for j in range(shape[1])]
                                     for i in range(shape[0])])
                np.testing.assert_array_equal(values, expected)
            rejects(ValueError, subject.update, np.ones((2, 3), dtype=np.int32))
            rejects(ValueError, subject.update, np.ones(6, dtype=np.float64))
        '''))


def test_f14_t02():
    with temporary_project() as project:
        build_numpy(project, 'broadcasting', '''
            cimport velora
            @velora.ufunc
            cdef double numeric(double x, double y):
                return x * 3 - y * 2
            @velora.ufunc
            cdef object objects(object x, object y):
                return (x, y)
        ''')
        run_thread_application(project, 'broadcasting', REJECTIONS + dedent('''
            import numpy as np
            left = np.arange(6, dtype=float).reshape(2, 1, 3) - 2
            right = np.arange(12, dtype=float).reshape(4, 3) + .5
            expected = np.array([[[3*left[i,0,k]-2*right[j,k] for k in range(3)]
                                  for j in range(4)] for i in range(2)])
            result = subject.numeric(left, right)
            assert result.shape == (2, 4, 3)
            np.testing.assert_array_equal(result, expected)
            a = np.array(['red', 'blue'], dtype=object).reshape(2, 1)
            b = np.array([7, None, 'end'], dtype=object)
            actual = subject.objects(a, b)
            assert actual.shape == (2, 3)
            for i in range(2):
                for j in range(3):
                    assert actual[i,j] == (a[i,0], b[j])
            rejects(ValueError, subject.numeric, np.ones((2, 3)), np.ones((4,)))
            rejects(ValueError, subject.objects, np.ones((2, 3), dtype=object),
                    np.ones((4,), dtype=object))
        '''))


def test_f14_t03():
    with temporary_project() as project:
        build_numpy(project, 'alternatives', '''
            cimport velora
            ctypedef fused Scalar:
                int
                double
                double complex
            @velora.ufunc
            cdef (double, int) pair(int x):
                return x * .5, x * 3 - 1
            @velora.ufunc
            cdef Scalar alternative(Scalar x):
                if Scalar is int:
                    return x * 2 + 1
                elif Scalar is double:
                    return x * .5 - 2
                else:
                    return x * 1j + 3
        ''')
        run_thread_application(project, 'alternatives', dedent('''
            import numpy as np
            values = np.array([[-8, 3, 12], [1, -5, 0]], dtype=np.intc)
            outputs = subject.pair(values)
            assert len(outputs) == 2
            np.testing.assert_array_equal(outputs[0], values * .5)
            np.testing.assert_array_equal(outputs[1], values * 3 - 1)
            for dtype, data, operation in (
                (np.intc, [-7, 2, 13], lambda x: x*2+1),
                (np.float64, [-3.5, 2.5, 11], lambda x: x*.5-2),
                (np.complex128, [-3+2j, 1-4j, 7j], lambda x: x*1j+3)):
                data = np.array(data, dtype=dtype)
                actual = subject.alternative(data)
                np.testing.assert_array_equal(actual, [operation(x) for x in data])
        '''))


def test_f14_t04():
    with temporary_project() as project:
        project.write('progress.h', PROGRESS_NATIVE)
        build_numpy(project, 'numeric_progress', PROGRESS_SOURCE + '''
@velora.ufunc
cdef (long, int) substantial(long x) noexcept nogil:
    cdef long result = 0
    if x < 0:
        begin_work()
        while more_work():
            result = transform(x)
        return result, end_work()
    return transform(x), -1
''')
        run_thread_application(project, 'numeric_progress', dedent('''
            import numpy as np
            import threading, time, sys
            ready, stop = threading.Event(), threading.Event()
            application = []
            def worker():
                ready.set()
                while not stop.is_set():
                    if subject.active():
                        application.append(sum(i*i for i in range(31)))
                        subject.ack()
                    time.sleep(0)
            thread = threading.Thread(target=worker)
            thread.start()
            assert ready.wait(5), 'Application worker did not start'
            previous = sys.getswitchinterval()
            try:
                # Prevent ordinary Python scheduling at the call boundary from
                # serving as evidence of progress during native work.
                sys.setswitchinterval(10)
                values = np.arange(600, dtype=np.dtype('l'))
                values[0] = -7
                result, acknowledged = subject.substantial(values)
            finally:
                sys.setswitchinterval(previous)
                stop.set()
                thread.join(5)
            assert not thread.is_alive(), 'Application worker did not finish'
            np.testing.assert_array_equal(result, [3*x+1 for x in values])
            assert acknowledged[0] == 1
            np.testing.assert_array_equal(acknowledged[1:], -np.ones(599, dtype=int))
            assert application and all(x == sum(i*i for i in range(31)) for x in application)
        '''))


def test_f14_t05():
    with temporary_project() as project:
        build_numpy(project, 'valid_scalar', '''
            cimport velora
            @velora.ufunc
            cdef double valid(double x):
                return x * 2 - 3
        ''')
        run_thread_application(project, 'valid_scalar', '''
import numpy as np
np.testing.assert_array_equal(subject.valid(np.array([-4., 1.5, 8.])), [-11., 0., 13.])
''')
        path = project.write('invalid_array_argument.pyx', dedent('''
            cimport velora
            @velora.ufunc
            cdef double invalid(double[:] values):
                return values[0]
        '''))
        rejected = translate_source(project, path)
        assert rejected.returncode != 0
        assert source_diagnostics(rejected, path), rejected.text('stderr')
