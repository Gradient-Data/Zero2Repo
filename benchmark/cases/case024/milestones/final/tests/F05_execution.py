# feature: F05
"""Acceptance tests for local execution and synchronous resource capacity."""
from pathlib import Path

from velnora import Scheduler, catch, task
from velnora.scheduler import SchedulerError

from _helpers import capture_call, memory_scheduler, run_workflow
from F01_helpers import AuthoredFailure, fail, identity
from F04_helpers import execution_place, execution_state
from F05_helpers import (consume_input, deliver_input, occupancy_run,
                         wait_for_input)


def test_f05_t01():
    execution_state.clear()
    shared = run_workflow(memory_scheduler(), execution_place(8))
    assert shared.exception is None, shared.exception
    assert shared.value == 56
    assert execution_state == [8]
    execution_state.clear()
    isolated = run_workflow(memory_scheduler(), execution_place.options(mode='process')(8))
    assert isolated.exception is None, isolated.exception
    assert isolated.value == 56
    assert execution_state == []
    for mode in ['thread', 'process']:
        result = run_workflow(memory_scheduler(), fail.options(mode=mode)('authored cause'))
        assert isinstance(result.exception, AuthoredFailure)
        assert result.exception.args == ('authored cause',)
    # Rejection may occur while applying options or while running the call.
    invalid_mode = capture_call(
        lambda: memory_scheduler().run(identity.options(mode='invalid-mode')(3)))
    assert isinstance(invalid_mode.exception, ValueError)
    unknown_executor = capture_call(
        lambda: memory_scheduler().run(identity.options(executor='absent-executor')(3)))
    assert isinstance(unknown_executor.exception, SchedulerError)


def test_f05_t02(tmp_path):
    for mode in ['thread', 'process']:
        directory = tmp_path / mode
        directory.mkdir()
        filename = str(directory)
        config = {'executors.default': {'type': 'local', 'mode': mode, 'max_workers': '2'}}
        result = run_workflow(memory_scheduler(config),
                              [consume_input(wait_for_input(filename), filename),
                               deliver_input(filename)], timeout=80)
        assert result.exception is None, result.exception
        assert result.value == [45, 19]
        assert (directory / 'consumed').read_text() == '45'
        assert (directory / 'input').read_text() == '37'


def test_f05_t03(tmp_path):
    # These are capacity observations over real blocking synchronous bodies,
    # not counts of threads, processes, or executor-reported occupancy.
    for capacity in [None, 3]:
        maximum = 20 if capacity is None else capacity
        settings = {'type': 'local'}
        if capacity is not None:
            settings['max_workers'] = str(capacity)
        config = {'executors.default': settings,
                  'executors.alternate': {'type': 'alias', 'target': 'default'}}
        specs = []
        for mode in ['thread', 'process']:
            specs.extend(({'mode': mode, 'executor': 'alternate' if i % 2 else 'default'},
                          {mode: 1}) for i in range(maximum + 2))
        # Capacity is an upper bound, not a promise to fill every slot.
        # Independent progress is exercised separately by the external-input test.
        peaks = occupancy_run(tmp_path / str(maximum), config, specs, 1)
        assert set(peaks) == {'thread', 'process'}
        assert all(0 < peak <= maximum for peak in peaks.values())


def test_f05_t04(tmp_path):
    # (capacities, request, charged amounts)
    workloads = [
        ({'api': '3', 'memory': '4'}, {'api': 2, 'memory': 1}, {'api': 2, 'memory': 1}),
        ({'api': '4', 'memory': '3'}, {'api': 1, 'memory': 2}, {'api': 1, 'memory': 2}),
        ({'api': '5', 'memory': '9'}, {'api': 2, 'memory': 3}, {'api': 2, 'memory': 3}),
        ({'api': '2'}, ['api'], {'api': 1}),
        ({'api': '3'}, ['api'], {'api': 1}),
        ({}, ['unconfigured'], {'unconfigured': 1}),
    ]
    for index, (capacities, request, amounts) in enumerate(workloads):
        # Same bodies and inputs apart from the resource condition: the live
        # baseline proves real overlap, so a never-executing body cannot pass.
        baseline = occupancy_run(tmp_path / f'free-{index}', {},
                                 [({}, amounts) for _ in range(4)], 2)
        assert set(baseline) == set(amounts)
        assert all(2 * amount <= baseline[name] <= 4 * amount
                   for name, amount in amounts.items())
        # Observe live allocations while the external gate is closed. A lawful
        # scheduler may leave slots unused; every allocation must still fit.
        peaks = occupancy_run(tmp_path / f'limited-{index}', {'limits': capacities},
                              [({'limits': request}, amounts) for _ in range(4)], 1)
        for name, peak in peaks.items():
            assert 0 < peak <= int(capacities.get(name, '1'))


def test_f05_t05(tmp_path):
    @task(namespace='f05.release', cache=False)
    def finish(filename, value):
        Path(filename).write_text(str(value))
        return value * 3

    @task(namespace='f05.release', cache=False)
    def further(filename, value):
        return finish.options(limits=['slot'])(filename, value)

    @task(namespace='f05.release', cache=False)
    def recover(error, filename):
        assert isinstance(error, AuthoredFailure)
        assert error.args == ('release cause',)
        return finish.options(limits=['slot'])(filename, 17)

    config = {'limits': {'slot': '1'}}
    # All paths must actually produce subsequent work using the same capacity.
    for kind in ['success', 'failure', 'expression']:
        filename = str(tmp_path / kind)
        if kind == 'success':
            expression = finish.options(limits=['slot'])(
                filename, identity.options(limits=['slot'])(11))
            expected = 33
        elif kind == 'failure':
            expression = catch(fail.options(limits=['slot'])('release cause'),
                               AuthoredFailure, recover.partial(filename=filename))
            expected = 51
        else:
            expression = further.options(limits=['slot'])(filename, 23)
            expected = 69
        result = run_workflow(memory_scheduler(config), expression, timeout=45)
        assert result.exception is None, result.exception
        assert result.value == expected
        assert Path(filename).read_text() == str(expected // 3)
