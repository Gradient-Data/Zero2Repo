# feature: F13
"""Parallel loop results, controlled scaling, configurations and failures."""
from textwrap import dedent
from _helpers import temporary_project, build_native, run_command, parse_json
from F01_helpers import translate_source, source_diagnostics
from F13_helpers import build_openmp, run_parallel_application


def test_f13_t01():
    with temporary_project() as project:
        build_openmp(project, 'parallel_reductions', '''
            from velora.parallel cimport prange
            cimport velora
            @velora.boundscheck(False)
            @velora.wraparound(False)
            def calculate(const int[:] values, long long[:] output):
                cdef Py_ssize_t i
                cdef long long add = 19, sub = -23, mul = 3
                cdef long long band = 6, bor = 256, bxor = 341
                cdef double floating = 1.25
                for i in prange(values.shape[0], nogil=True, num_threads=4):
                    output[i] = values[i] * values[i] + 3 * values[i]
                    add += values[i]
                    sub -= values[i]
                    mul *= values[i]
                    band &= values[i]
                    bor |= values[i]
                    bxor ^= values[i]
                    floating += values[i] * 0.125
                return add, sub, mul, band, bor, bxor, floating
        ''')
        run_parallel_application(project, 'parallel_reductions', '''
            from array import array
            import functools, operator
            for values in ([], [7, 3, 15, 11, 7, 3], [-2, 1, 3, -1, 2]):
                output = array('q', [-999] * len(values))
                actual = subject.calculate(array('i', values), output)
                assert list(output) == [x*x + 3*x for x in values]
                expected = (19 + sum(values), -23 - sum(values),
                            functools.reduce(operator.mul, values, 3),
                            functools.reduce(operator.and_, values, 6),
                            functools.reduce(operator.or_, values, 256),
                            functools.reduce(operator.xor, values, 341))
                assert actual[:6] == expected, (actual, expected)
                # Dyadic terms are exact here under every reduction order.
                assert actual[6] == 1.25 + sum(x*0.125 for x in values)
        ''')


def test_f13_t02(capfd):
    # The native resource probe is independent of the product. Only complete
    # pairs bracketed by usable CPU capacity contribute to the median; product
    # durations never decide which observations are retained.
    # casebox, 2026-11-04: original median ratio 0.277; reference 0.273.
    # Each uses five qualified pairs, versus the unchanged public bound 0.8.
    with temporary_project() as project:
        project.write('work.h', r'''
#include <stdint.h>
uint64_t work(uint64_t x, int rounds);
''')
        # A separate translation unit prevents call-site vectorisation from
        # giving the resource probe a shorter workload than the extension.
        work_source = project.write('work.c', r'''
#include "work.h"
uint64_t work(uint64_t x, int rounds) {
    for (int j = 0; j < rounds; ++j) {
        x ^= x << 13; x ^= x >> 7; x ^= x << 17;
    }
    return x;
}
''')
        oracle_source = project.write('oracle.c', r'''
#include <stdio.h>
#include <time.h>
#include "work.h"
int main(void) {
    uint64_t output[128];
    struct timespec started, stopped;
    if (clock_gettime(CLOCK_MONOTONIC, &started)) {
        perror("clock_gettime");
        return 2;
    }
    clock_t cpu_started = clock();
#ifdef _OPENMP
    #pragma omp parallel for num_threads(4) schedule(static)
#endif
    for (int i = 0; i < 128; ++i)
        output[i] = work(i + 1, 4000000);
    clock_t cpu_stopped = clock();
    if (clock_gettime(CLOCK_MONOTONIC, &stopped)) {
        perror("clock_gettime");
        return 2;
    }
    if (cpu_started == (clock_t)-1 || cpu_stopped == (clock_t)-1) {
        fputs("Process CPU clock unavailable\n", stderr);
        return 2;
    }
    double seconds = stopped.tv_sec - started.tv_sec
                   + (stopped.tv_nsec - started.tv_nsec) / 1e9;
    printf("{\"seconds\":%.9f,\"cpu_seconds\":%.9f,\"output\":[",
           seconds, (double)(cpu_stopped - cpu_started) / CLOCKS_PER_SEC);
    for (int i = 0; i < 128; ++i)
        printf("%s%llu", i ? "," : "", (unsigned long long)output[i]);
    puts("]}");
    return 0;
}
''')
        oracle = project.path('oracle')
        compiled = build_native('cc', [oracle_source, work_source], oracle, before=['-O3'])
        compiled.check_returncode()
        observed = run_command([oracle], timeout=60)
        observed.check_returncode()
        expected = parse_json(observed.stdout)['output']
        capacity_probe = project.path('capacity_probe')
        build_native('cc', [oracle_source, work_source], capacity_probe,
                     before=['-O3', '-fopenmp']).check_returncode()
        build_openmp(project, 'parallel_scaling', '''
            from velora.parallel cimport prange
            cimport velora
            cdef extern from "work.h" nogil:
                unsigned long long work(unsigned long long, int) noexcept
            @velora.boundscheck(False)
            @velora.wraparound(False)
            def calculate(unsigned long long[:] output, int rounds):
                cdef Py_ssize_t i
                for i in prange(output.shape[0], nogil=True, num_threads=4, schedule='static'):
                    output[i] = work(i + 1, rounds)
        ''', extra_sources=[work_source])
        application = dedent('''
            import json, time
            from array import array
            import parallel_scaling as subject
            output = array('Q', [0] * 128)
            subject.calculate(output, 4000000)
            assert list(output) == EXPECTED
            started = time.perf_counter()
            cpu_started = time.process_time()
            subject.calculate(output, 4000000)
            cpu_seconds = time.process_time() - cpu_started
            seconds = time.perf_counter() - started
            print(json.dumps({'seconds': seconds, 'cpu_seconds': cpu_seconds,
                              'output': list(output)}))
        ''').replace('EXPECTED', repr(expected))
        result = run_parallel_application(project, 'parallel_scaling', '''
            import os, time, statistics, json, subprocess, sys
            from pathlib import Path
            original = os.sched_getaffinity(0)
            cores = {}
            for cpu in sorted(original):
                root = Path('/sys/devices/system/cpu') / ('cpu' + str(cpu)) / 'topology'
                key = ((root / 'physical_package_id').read_text().strip(),
                       (root / 'core_id').read_text().strip())
                cores.setdefault(key, []).append(cpu)
            assert len(cores) >= 4, 'Four available physical CPU cores are required'
            quota, period = Path('/sys/fs/cgroup/cpu.max').read_text().split()
            assert quota == 'max' or int(quota) >= 4 * int(period), \
                'CPU quota must permit four physical cores'
            def cpu_times():
                times = {}
                for line in Path('/proc/stat').read_text().splitlines():
                    fields = line.split()
                    if fields[0].startswith('cpu') and fields[0][3:].isdigit():
                        # Linux counts guest time within user/nice already.
                        ticks = list(map(int, fields[1:9]))
                        times[int(fields[0][3:])] = (sum(ticks), ticks[3] + ticks[4])
                return times
            before = cpu_times()
            time.sleep(1)
            after = cpu_times()
            def busy(cpu):
                total = after[cpu][0] - before[cpu][0]
                idle = after[cpu][1] - before[cpu][1]
                assert total > 0, 'CPU accounting must advance during resource probe'
                return 1 - idle / total
            ranked = sorted(cores.values(), key=lambda siblings: max(map(busy, siblings)))
            representatives = [min(siblings, key=busy) for siblings in ranked]
            candidates = [representatives[i:i+4]
                          for i in range(0, len(representatives)-3, 4)]
            if len(representatives) % 4:
                candidates.append(representatives[-4:])
            expected = EXPECTED
            capacity_probe = CAPACITY_PROBE
            serial_probe = SERIAL_PROBE
            application = APPLICATION
            def invoke(command, allowed):
                # Fresh children and all their descendants inherit the resource
                # limit. No knowledge of runtime tasks or worker persistence is
                # needed, and every product setting is identical in both arms.
                try:
                    os.sched_setaffinity(0, set(allowed))
                    completed = subprocess.run(command, capture_output=True,
                                               text=True, timeout=60)
                finally:
                    os.sched_setaffinity(0, original)
                assert completed.returncode == 0, completed.stderr + completed.stdout
                record = json.loads(completed.stdout)
                assert record.pop('output') == expected
                assert record['seconds'] > 0, record
                return record
            def capacity(cpus, order):
                return {count: invoke([capacity_probe], cpus[:count]) for count in order}
            def usable(probes):
                # This is an independent prerequisite, not evidence that the
                # product parallelizes. Check actual delivered capacity instead
                # of assuming that low /proc/stat utilisation implies it.
                return (probes[1]['cpu_seconds'] / probes[1]['seconds'] >= 0.85
                        and probes[4]['cpu_seconds'] / probes[4]['seconds'] >= 2.5
                        and probes[4]['seconds'] / probes[1]['seconds'] <= 0.5)
            selection = []
            cpus = None
            # Host contention is transient. Retry the independent capacity
            # measurement across several scheduling windows, while retaining
            # the same four-core CPU-time and wall-time requirements.
            for attempt in range(6):
                for candidate in candidates:
                    # Use the fastest independently observed core for the
                    # one-core baseline, rather than making serial execution
                    # benefit just by migrating to a faster or less busy core.
                    serial = {cpu: invoke([serial_probe], [cpu]) for cpu in candidate}
                    candidate = sorted(candidate, key=lambda cpu: serial[cpu]['seconds'])
                    probes = capacity(candidate, (1, 4))
                    selection.append({'cpus': candidate, 'serial': serial, 'capacity': probes})
                    if usable(probes):
                        cpus = candidate
                        break
                if cpus is not None:
                    break
            assert cpus is not None, (
                'Insufficient uncontended CPU capacity for the four-core comparison',
                selection)
            samples = {1: [], 4: []}
            cpu_samples = {1: [], 4: []}
            observations = []
            for trial in range(64):
                order = (1, 4) if trial % 2 == 0 else (4, 1)
                preceding = capacity(cpus, order)
                record = {'before': preceding}
                if not usable(preceding):
                    record['excluded'] = 'CPU resource prerequisite unavailable before pair'
                    observations.append(record)
                    continue
                measured = {count: invoke([sys.executable, '-c', application], cpus[:count])
                            for count in order}
                following = capacity(cpus, tuple(reversed(order)))
                record.update({'product': measured, 'after': following})
                if not usable(following):
                    record['excluded'] = 'CPU resource prerequisite unavailable after pair'
                else:
                    for count in (1, 4):
                        samples[count].append(measured[count]['seconds'])
                        cpu_samples[count].append(measured[count]['cpu_seconds'])
                observations.append(record)
                if len(samples[1]) == 5:
                    break
            diagnostics = {'cpus': cpus, 'selection': selection,
                           'samples': samples, 'cpu_samples': cpu_samples,
                           'observations': observations}
            print(json.dumps(diagnostics), flush=True)
            assert len(samples[1]) == 5, (
                'Insufficient stable CPU capacity for five measured pairs', diagnostics)
            ratio = statistics.median(samples[4]) / statistics.median(samples[1])
            print(json.dumps({'ratio': ratio}), flush=True)
            assert ratio <= 0.8, diagnostics
        '''.replace('EXPECTED', repr(expected))
           .replace('CAPACITY_PROBE', repr(str(capacity_probe)))
           .replace('SERIAL_PROBE', repr(str(oracle)))
           .replace('APPLICATION', repr(application)), timeout=600)
        with capfd.disabled():
            print(result.text())


def test_f13_t03():
    with temporary_project() as project:
        source = 'from velora.parallel cimport prange\ncimport velora\n'
        configurations = [
            ('static', "schedule='static', chunksize=3", '4', 'True'),
            ('dynamic', "schedule='dynamic', chunksize=2", '4', 'True'),
            ('guided', "schedule='guided', chunksize=3", '4', 'True'),
            ('runtime', "schedule='runtime'", '4', 'True'),
            ('default_workers', "schedule='static'", '0', 'True'),
            ('conditional', "schedule='static'", '4', 'condition'),
        ]
        for name, schedule, workers, condition in configurations:
            source += f'''
@velora.boundscheck(False)
@velora.wraparound(False)
def {name}(const int[:] values, long long[:] output, bint condition=True):
    cdef Py_ssize_t i
    cdef long long total = 31
    for i in prange(values.shape[0], nogil=True, {schedule}, num_threads={workers}, use_threads_if={condition}):
        output[i] = values[i] * 7 - i
        total += values[i]
    return total
'''
        build_openmp(project, 'parallel_options', source)
        run_parallel_application(project, 'parallel_options', '''
            from array import array
            values = [i*3 - 41 for i in range(97)]
            for name in ('static', 'dynamic', 'guided', 'runtime', 'default_workers', 'conditional'):
                for condition in ((False, True) if name == 'conditional' else (True,)):
                    output = array('q', [-999] * len(values))
                    total = getattr(subject, name)(array('i', values), output, condition)
                    assert total == 31 + sum(values)
                    assert list(output) == [x*7-i for i, x in enumerate(values)]
        ''')
        for index, settings in enumerate((
                'num_threads=-1', "schedule='static', chunksize=0",
                "schedule='dynamic', chunksize=-2", 'chunksize=2',
                "schedule='runtime', chunksize=2")):
            path = project.write(f'invalid_options_{index}.pyx',
                'from velora.parallel cimport prange\n'
                'def invalid():\n    cdef int i\n'
                f'    for i in prange(10, nogil=True, {settings}):\n        pass\n')
            rejected = translate_source(project, path)
            assert rejected.returncode != 0
            assert source_diagnostics(rejected, path), rejected.text('stderr')


def test_f13_t04():
    with temporary_project() as project:
        build_openmp(project, 'parallel_regions', '''
            from velora.parallel cimport parallel, prange
            from libc.stdlib cimport malloc, free, abort
            cimport velora
            @velora.boundscheck(False)
            @velora.wraparound(False)
            def calculate(const int[:] values, long long[:] output, events):
                cdef long long *scratch
                cdef Py_ssize_t i
                cdef int j
                with nogil, parallel(num_threads=4):
                    scratch = <long long*>malloc(64 * sizeof(long long))
                    if scratch == NULL:
                        abort()
                    for i in prange(values.shape[0], schedule='dynamic', chunksize=1):
                        for j in range(64):
                            scratch[j] = values[i] * (j + 1)
                        output[i] = scratch[3] + scratch[61]
                        with gil:
                            events.append((i, output[i]))
                    free(scratch)
            def can_fail(int n, int failing, failure):
                cdef int i
                cdef long total = 17
                for i in prange(n, nogil=True, num_threads=4):
                    if i == failing:
                        with gil:
                            raise failure
                    total += i
                return total
        ''')
        run_parallel_application(project, 'parallel_regions', '''
            from array import array
            for values in ([7, -2, 13], [i-100 for i in range(211)]):
                events = []
                output = array('q', [-999] * len(values))
                subject.calculate(array('i', values), output, events)
                expected = [66*x for x in values]
                assert list(output) == expected
                assert sorted(events) == list(enumerate(expected))
            assert subject.can_fail(71, -1, ValueError()) == 17 + sum(range(71))
            for index in (0, 37, 70):
                failure = ValueError('iteration', index)
                try:
                    subject.can_fail(71, index, failure)
                except ValueError as caught:
                    assert caught is failure
                else:
                    raise AssertionError('Iteration exception did not reach caller')
        ''')
        path = project.write('unprotected_parallel.pyx', dedent('''
            from velora.parallel cimport parallel
            def invalid(events):
                with nogil, parallel(num_threads=4):
                    events.append(1)
        '''))
        rejected = translate_source(project, path)
        assert rejected.returncode != 0
        assert source_diagnostics(rejected, path), rejected.text('stderr')
