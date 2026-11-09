# feature: F12
"""Execute transformation checks against the mounted public product source."""
import functools
from pathlib import Path

from _helpers import run_python


def transformation_source_test(function):
    @functools.wraps(function)
    def execute():
        source = '''
import sys
from pathlib import Path
root = Path('/app/src')
if not (root / 'velnora/__init__.py').is_file():
    raise RuntimeError('Mounted product source is missing')
sys.path.insert(0, str(root))
sys.path.insert(0, sys.argv[1])
from F12_transformations import FUNCTION
FUNCTION.__wrapped__()
'''.replace('FUNCTION', function.__name__)
        result = run_python(source, timeout=120, args=(str(Path(__file__).parent),))
        assert result.returncode == 0, result.stdout + result.stderr
    return execute


def cpu_mapping_effect():
    """Compare identical mapping requests under external CPU affinity limits.

    Final 256-record original calibration: medians 8.0170 / 2.1281 seconds,
    ratio 0.2654, with ample reserve below 0.75. The workload also passed the
    reference run and rejects a single-worker implementation
    (one/four-affinity medians 6.4369 / 6.7881 seconds). Absolute times are
    evidence only; the assertion always compares resources within this run.
    """
    import hashlib
    import json
    import os
    import statistics
    assert len(os.sched_getaffinity(0)) >= 4, 'CPU comparison requires at least four available cores'
    quota = Path('/sys/fs/cgroup/cpu.max')
    if quota.is_file():
        amount, period = quota.read_text().split()
        assert amount == 'max' or int(amount) >= 4 * int(period), 'CPU quota provides fewer than four cores'
    cpus = uncontended_cpus(4)
    expected = [hashlib.pbkdf2_hmac('sha256', str(i).encode(), b'computation', 100000).hex()
                for i in range(256)]
    source = '''
import hashlib, json, os, sys, time
os.sched_setaffinity(0, json.loads(sys.argv[1]))
from velnora import Dataset

def operation(row):
    return {'digest': hashlib.pbkdf2_hmac('sha256', str(row['id']).encode(), b'computation', 100000).hex()}

data = Dataset.from_dict({'id': list(range(256))})
started = time.perf_counter()
result = list(data.map(operation, num_proc=4, load_from_cache_file=False))
elapsed = time.perf_counter() - started
print(json.dumps({'elapsed': elapsed, 'rows': result}))
'''
    durations = [[], []]

    def compare():
        for repeat in range(3):
            for index in (repeat % 2, 1 - repeat % 2):
                result = run_python(source, args=(json.dumps(cpus[:1 if index == 0 else 4]),), timeout=90)
                assert result.returncode == 0, result.stdout + result.stderr
                observation = json.loads(result.stdout)
                assert observation['rows'] == [{'id': i, 'digest': value} for i, value in enumerate(expected)]
                durations[index].append(observation['elapsed'])
        medians = [statistics.median(group) for group in durations]
        print(json.dumps({'cpu_counts': [1, 4], 'seconds': durations, 'medians': medians}), flush=True)
        assert medians[1] <= 0.75 * medians[0], durations

    judged_on_idle_cpus(cpus, compare)


_CAPACITY_PROBE = (
    "import os, sys, time\n"
    "os.sched_setaffinity(0, {int(sys.argv[1])})\n"
    "wall0, cpu0 = time.perf_counter(), time.process_time()\n"
    "while time.perf_counter() - wall0 < 1.0:\n"
    "    pass\n"
    "print(time.process_time() - cpu0, time.perf_counter() - wall0)\n"
)


def cpu_capacity(cpus):
    """Share of one CPU a busy process gets on each of *cpus*, all probed at once."""
    import subprocess
    import sys
    probes = {cpu: subprocess.Popen([sys.executable, '-c', _CAPACITY_PROBE, str(cpu)],
                                    stdout=subprocess.PIPE, text=True) for cpu in cpus}
    shares = {}
    for cpu, process in probes.items():
        out, _ = process.communicate(timeout=60)
        used, wall = map(float, out.split())
        shares[cpu] = round(used / wall, 3)
    return shares


def uncontended_cpus(count, *, physical_same_package=False, attempts=6):
    """*count* CPUs of this process's affinity that each deliver at least 85% of a CPU.

    The documents condition the scaling comparison on an otherwise idle machine. A host
    that cannot provide that fails here, with a message naming the unmet condition and
    the measurements, before any product timing is attempted.
    """
    import os
    import time
    from pathlib import Path
    allowed = sorted(os.sched_getaffinity(0))
    pools = {}
    for cpu in allowed:
        topology = Path(f'/sys/devices/system/cpu/cpu{cpu}/topology')
        if physical_same_package:
            package = (topology / 'physical_package_id').read_text().strip()
            core = (topology / 'core_id').read_text().strip()
        else:
            package, core = '', str(cpu)
        pools.setdefault(package, {}).setdefault(core, []).append(cpu)
    pools = {key: cores for key, cores in pools.items() if len(cores) >= count}
    assert pools, (f'The comparison requires {count} available '
                   + ('physical cores on one processor package' if physical_same_package else 'processors'),
                   allowed)

    def ticks():
        stat = {}
        for line in Path('/proc/stat').read_text().splitlines():
            fields = line.split()
            if fields[0].startswith('cpu') and fields[0][3:].isdigit():
                values = list(map(int, fields[1:9]))
                stat[int(fields[0][3:])] = (sum(values), values[3] + values[4])
        return stat

    observed = []
    for attempt in range(attempts):
        before = ticks()
        time.sleep(1)
        after = ticks()

        def busy(cpu):
            total = after[cpu][0] - before[cpu][0]
            return 1 - (after[cpu][1] - before[cpu][1]) / total if total else 1.0

        for cores in pools.values():
            representatives = sorted((min(siblings, key=busy) for siblings in cores.values()), key=busy)
            chosen = representatives[:count]
            shares = cpu_capacity(chosen)
            observed.append({'attempt': attempt, 'cpus': chosen, 'shares': shares})
            if min(shares.values()) >= 0.85:
                return chosen
        time.sleep(2)
    raise AssertionError(f'Insufficient uncontended CPU capacity for the {count}-processor comparison: '
                         'the host is not otherwise idle', observed)


def judged_on_idle_cpus(cpus, run):
    """Run a scaling comparison on *cpus*; a failure on a host that lost its idle capacity says so."""
    try:
        return run()
    except AssertionError as failure:
        shares = cpu_capacity(cpus)
        if min(shares.values()) < 0.85:
            raise AssertionError('CPU capacity on the compared processors became contended during '
                                 'the comparison: the host is not otherwise idle', shares) from failure
        raise
