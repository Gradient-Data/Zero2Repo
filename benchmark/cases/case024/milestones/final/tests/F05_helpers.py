# feature: F05
"""Authored synchronous I/O workloads and independent occupancy observations."""
import json
import os
import threading
import time
from pathlib import Path

from velnora import task
from _helpers import memory_scheduler, run_workflow


def occupancy_event(database, label, amounts, delta):
    # One short O_APPEND write per event: atomic and ordered on a local file, and safe in
    # forked workers (no lock state is inherited across fork, unlike SQLite connections).
    line = (json.dumps([label, amounts, delta]) + '\n').encode()
    descriptor = os.open(database, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        assert os.write(descriptor, line) == len(line)
    finally:
        os.close(descriptor)


def occupancy_events(database):
    with open(database, 'rb') as source:
        data = source.read()
    complete = data[:data.rfind(b'\n') + 1]
    return [tuple(json.loads(line)) for line in complete.decode().splitlines()]


@task(namespace="f05.io", cache=False)
def occupied(database, label, amounts, release):
    occupancy_event(database, label, amounts, 1)
    deadline = time.monotonic() + 40
    try:
        while not Path(release).exists():
            if time.monotonic() > deadline:
                raise TimeoutError('External release was not delivered')
            time.sleep(0.01)
        return label * 13 + 5
    finally:
        occupancy_event(database, label, amounts, -1)


def occupancy_run(directory, config, specifications, threshold):
    """Hold real bodies on external I/O; observe all starts and completions.

    Deadlines only bound deadlocks, not product speed. A controller releases
    input after enough work is live, allowing excess allocations to be seen.
    """
    directory.mkdir()
    database = str(directory / 'occupancy.log')
    release = str(directory / 'release')
    Path(database).touch()
    errors = []
    stop = threading.Event()

    def controller():
        try:
            deadline = time.monotonic() + 30
            while True:
                live = sum(delta for _, _, delta in occupancy_events(database))
                if live >= threshold:
                    # Allow already-ready competing work to reach the same gate.
                    stop.wait(0.4)
                    break
                if stop.wait(0.01):
                    break
                if time.monotonic() > deadline:
                    raise AssertionError('Ready work did not reach the external I/O gate')
        except Exception as error:
            errors.append(error)
        finally:
            Path(release).touch()

    thread = threading.Thread(target=controller)
    thread.start()
    try:
        expression = [occupied.options(**options)(database, i, amounts, release)
                      for i, (options, amounts) in enumerate(specifications)]
        result = run_workflow(memory_scheduler(config), expression, timeout=100)
    finally:
        stop.set()
        thread.join(timeout=45)
    assert not thread.is_alive(), 'External I/O controller did not finish'
    if errors:
        raise errors[0]
    assert result.exception is None, result.exception
    assert result.value == [i * 13 + 5 for i in range(len(specifications))]
    events = occupancy_events(database)
    active, peaks, running = {}, {}, set()
    for label, amounts, delta in events:
        if delta == 1:
            assert label not in running
            running.add(label)
        else:
            assert label in running
            running.remove(label)
        for name, amount in amounts.items():
            active[name] = active.get(name, 0) + delta * amount
            assert active[name] >= 0
            peaks[name] = max(peaks.get(name, 0), active[name])
    assert not running
    assert len(events) == 2 * len(specifications)
    return peaks


@task(namespace="f05.dependencies", cache=False)
def wait_for_input(directory):
    root = Path(directory)
    (root / 'waiting').touch()
    deadline = time.monotonic() + 30
    while not (root / 'input').exists():
        if time.monotonic() > deadline:
            raise TimeoutError('Independent work did not deliver input')
        time.sleep(0.01)
    return int((root / 'input').read_text())


@task(namespace="f05.dependencies", cache=False)
def deliver_input(directory):
    root = Path(directory)
    deadline = time.monotonic() + 30
    while not (root / 'waiting').exists():
        if time.monotonic() > deadline:
            raise TimeoutError('Waiting body did not start')
        time.sleep(0.01)
    (root / 'input').write_text('37')
    return 19


@task(namespace="f05.dependencies", cache=False)
def consume_input(value, directory):
    (Path(directory) / 'consumed').write_text(str(value + 8))
    return value + 8
