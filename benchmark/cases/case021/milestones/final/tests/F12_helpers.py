# feature: F12
"""Bounded native work and application-thread observations."""
from _helpers import run_python

PROGRESS_NATIVE = r'''
#include <stdatomic.h>
#include <stdlib.h>
#include <time.h>
static atomic_int active = 0, acknowledged = 0;
static double deadline;
static double now(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) abort();
    return t.tv_sec + t.tv_nsec * 1e-9;
}
static void begin_work(void) {
    atomic_store(&acknowledged, 0);
    deadline = now() + 0.25;
    atomic_store(&active, 1);
}
static int more_work(void) { return now() < deadline; }
static int end_work(void) {
    atomic_store(&active, 0);
    return atomic_load(&acknowledged);
}
static int is_active(void) { return atomic_load(&active); }
static void acknowledge(void) { atomic_store(&acknowledged, 1); }
static long transform(long x) { return x * 3 + 1; }
'''

PROGRESS_SOURCE = '''
cimport velora
cdef extern from "progress.h" nogil:
    void begin_work() noexcept
    int more_work() noexcept
    int end_work() noexcept
    int is_active() noexcept
    void acknowledge() noexcept
    long transform(long) noexcept

def active():
    return is_active()
def ack():
    acknowledge()

@velora.boundscheck(False)
@velora.wraparound(False)
cdef long calculate(const int[:] data) noexcept nogil:
    cdef Py_ssize_t i
    cdef long total = 0
    for i in range(data.shape[0]):
        total += transform(data[i])
    return total
'''

PROGRESS_DRIVER = '''
from array import array
import threading
import time

def measure(call, values):
    ready, stop = threading.Event(), threading.Event()
    application = []
    def worker():
        ready.set()
        while not stop.is_set():
            if subject.active():
                application.append(sum(values))
                subject.ack()
            time.sleep(0)
    thread = threading.Thread(target=worker)
    thread.start()
    assert ready.wait(5), "Application worker did not start"
    try:
        result, passes, acknowledged = call(array('i', values))
    finally:
        stop.set()
        thread.join(5)
    assert not thread.is_alive(), "Application worker did not finish"
    assert passes > 0
    assert result == sum(3 * x + 1 for x in values)
    if acknowledged:
        assert application and all(x == sum(values) for x in application)
    return acknowledged
'''


def run_thread_application(project, name, driver):
    result = run_python(f'import {name} as subject\n' + driver,
                        env=project.environment(), timeout=60)
    assert result.returncode == 0, result.text('stderr') + result.text()


def progress_entry(name, context):
    """Create source with identical work and only the permission region varied."""
    return f'''
def {name}(const int[:] data):
    cdef long result = 0
    cdef long passes = 0
    cdef int acknowledged
    {context}
        begin_work()
        while more_work():
            result = calculate(data)
            passes += 1
        acknowledged = end_work()
    return result, passes, acknowledged
'''
