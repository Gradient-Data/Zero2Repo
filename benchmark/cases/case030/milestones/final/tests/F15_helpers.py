# feature: F15
"""Controlled OpenMP compilation and an independent host resource probe."""
import inspect
import textwrap
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import make_environment, run_python, run_command, write_text
from F00_candidate import materialize_candidate
from F03_helpers import require_success

# The default team size differs from every team size the submitted programs
# request, so a num_threads clause or omp_set_num_threads call that is ignored
# changes the observed participants.
OMP_ENV = {'OMP_DYNAMIC': 'FALSE', 'OMP_THREAD_LIMIT': '64',
           'OMP_NUM_THREADS': '3', 'OMP_MAX_ACTIVE_LEVELS': '2'}


def openmp_observation(directory, source, check):
    directory.mkdir(parents=True)
    env = make_environment(OMP_ENV)
    # This probe uses the host toolchain, never the submitted translator or
    # its runtime wrappers. Failure is an environment error, never a skip.
    probe = write_text(directory, 'capacity.c', '''#include <omp.h>
int main(void) {
    int count = 0;
    omp_set_dynamic(0);
    #pragma omp parallel num_threads(2) reduction(+:count)
    count += 1;
    return count == 2 ? 0 : 1;
}
''')
    built = run_command(['gcc', '-fopenmp', str(probe), '-o', str(directory / 'capacity')],
                        cwd=directory, env=env)
    require_success(built)
    capacity = run_command([directory / 'capacity'], cwd=directory, env=env)
    assert capacity.returncode == 0, ('Host cannot satisfy two participants', capacity)
    candidate = materialize_candidate(directory)

    driver = ("import sys\nimport numpy as np\n"
              + f"sys.path.insert(0, {str(candidate)!r})\n"
              + "from zelvori import ezelvori\n"
              + f"sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})\n"
              + "from F00_candidate import _checked\nezelvori = _checked(ezelvori)\n"
              + textwrap.dedent(inspect.getsource(check))
              + f"\nsource = {source!r}\n"
              + "for language in ('c', 'fortran'):\n"
              + "    module = ezelvori(source, language=language, openmp=True, folder=language)\n"
              + "    check(module)\n")
    result = run_python(driver, cwd=directory, env=env, timeout=480)
    require_success(result)
    return result


WORKSHARING = '''def work(a: 'int[:]', marks: 'int[:]', n: int, seed: int):
    from zelvori.stdlib.internal.openmp import omp_get_thread_num
    total = 0
    once = seed
    left = seed
    right = seed
    #$ omp parallel num_threads(2) private(t)
    t = omp_get_thread_num()
    marks[t] = seed * (t + 1)
    #$ omp for reduction(+:total)
    for i in range(n):
        a[i] += i * i + seed
        total += i * i + seed
    #$ omp single
    once += 7
    #$ omp end single
    #$ omp sections
    #$ omp section
    left += 11
    #$ omp end section
    #$ omp section
    right += 13
    #$ omp end section
    #$ omp end sections
    #$ omp end parallel
    marks[3] = once
    marks[4] = left
    marks[5] = right
    return total
'''

SYNCHRONIZATION = '''def sync(a: 'int[:]', seen: 'int[:]', n: int, seed: int):
    from zelvori.stdlib.internal.openmp import omp_get_thread_num
    critical_sum = seed
    atomic_sum = seed
    first = 0
    second = 0
    combined = 0
    #$ omp parallel num_threads(2) private(t, j)
    t = omp_get_thread_num()
    for j in range(n):
        #$ omp critical
        critical_sum += int(t) + j + 1
        #$ omp end critical
        #$ omp atomic
        atomic_sum += int(t) + j + 1
    a[t] = seed + t
    #$ omp barrier
    seen[t] = a[0] + a[1]
    #$ omp single
    #$ omp task shared(first) firstprivate(n, seed)
    for k in range(n):
        first += k + seed
    #$ omp end task
    #$ omp task shared(second) firstprivate(n, seed)
    for q in range(n):
        second += q * q + seed
    #$ omp end task
    #$ omp taskwait
    combined = first + second
    #$ omp end single
    #$ omp end parallel
    seen[2] = critical_sum
    seen[3] = atomic_sum
    return combined
'''

CONTEXT = '''from numpy import int32

def context(out: 'int[:,:]', a: 'int[:]', n: int, seed: int):
    from zelvori.stdlib.internal.openmp import omp_set_num_threads, omp_get_num_threads, omp_get_max_threads, omp_get_thread_num, omp_in_parallel, omp_get_level, omp_get_ancestor_thread_num, omp_get_team_size
    omp_set_num_threads(int32(2))
    outside = int(omp_in_parallel())
    maximum = omp_get_max_threads()
    #$ omp parallel private(t, personal)
    t = omp_get_thread_num()
    personal = seed + int(t) * 17
    #$ omp barrier
    out[t, 0] = personal
    out[t, 1] = omp_get_num_threads()
    out[t, 2] = int(omp_in_parallel())
    out[t, 3] = omp_get_level()
    #$ omp parallel num_threads(1)
    out[t, 4] = omp_get_ancestor_thread_num(int32(1))
    out[t, 5] = omp_get_team_size(int32(1))
    out[t, 6] = omp_get_level()
    #$ omp end parallel
    #$ omp for
    for i in range(n):
        a[i] += seed + i
    #$ omp end parallel
    out[0, 7] = outside
    out[1, 7] = int(omp_in_parallel())
    return maximum
'''

LOOPS = '''def loops(a: 'int[:]', b: 'int[:]', report: 'int[:]', n: int, seed: int):
    total = 0
    vector = 0
    mixed = 0
    #$ omp parallel for num_threads(2) reduction(+:total)
    for i in range(n):
        a[i] += seed + i * i
        total += seed + i * i
    #$ omp simd reduction(+:vector)
    for j in range(n):
        b[j] += seed - j
        vector += seed - j
    #$ omp parallel for simd num_threads(2) reduction(+:mixed)
    for k in range(n):
        a[k] += b[k]
        mixed += a[k]
    report[0] = vector
    report[1] = mixed
    return total
'''
