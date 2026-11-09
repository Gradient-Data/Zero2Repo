# feature: F09
"""Acceptance coverage for restored resources and tracked state transitions."""
import json
import os
from pathlib import Path

import velnora
from velnora import merge_handles, task

from _helpers import run_python
from F02_helpers import run_value_workflow
from F06_helpers import prepare_repository
from F08_helpers import repository_scheduler
from F09_helpers import (DatabaseHandle, create_resource, resource_snapshot,
                         transition_first, transition_second)


def test_f09_t01(tmp_path):
    repository, database = tmp_path / 'repo', tmp_path / 'resource.db'
    prepare_repository(repository)
    create_resource(database)
    audit_path, answer = tmp_path / 'audit', tmp_path / 'answer.json'
    source = '''import json, sys
from F06_helpers import history_scheduler
from F02_helpers import run_value_workflow
from F09_helpers import open_resource, use_resource
expression = open_resource(sys.argv[2], sys.argv[3])
if sys.argv[5] == 'use':
    expression = use_resource(expression, int(sys.argv[6]))
result = run_value_workflow(history_scheduler(sys.argv[1]), expression)
if sys.argv[5] == 'use':
    with open(sys.argv[4], 'w') as stream:
        json.dump(result, stream)
'''
    environment = {'PYTHONPATH': os.pathsep.join([
        str(Path(__file__).parent), str(Path(velnora.__file__).resolve().parent.parent)])}
    # Each invocation is a new interpreter: a live connection cannot survive it.
    for mode, increment in [('save', 0), ('use', 6), ('use', 14)]:
        result = run_python(source, cwd=tmp_path, env=environment, timeout=90,
                             args=[repository, database, audit_path, answer, mode, str(increment)])
        assert result.returncode == 0, result
        if mode == 'use':
            assert json.loads(answer.read_text()) == 31 + increment
    assert audit_path.read_text().splitlines() == ['open']
    assert resource_snapshot(database) == (
        {'seed': 31, 'used': 45}, [('seed', 31), ('used', 37), ('used', 45)])


def test_f09_t02(tmp_path):
    scheduler = repository_scheduler(tmp_path / 'repo')
    database = tmp_path / 'resource.db'
    create_resource(database)

    @task(namespace='f09.transitions')
    def initialize():
        handle = DatabaseHandle('resource', str(database))
        handle.put('seed', 4)
        return handle

    @task(namespace='f09.transitions')
    def dependent(handle):
        handle.put('total', handle.get('changed') + 1)
        return handle

    current = task(name='change', namespace='f09.transitions')(transition_first)

    @task(namespace='f09.transitions')
    def workflow(factor):
        return dependent(current(initialize(), factor))

    expected_effects = [('seed', 4), ('changed', 12), ('total', 13)]
    for _ in range(2):
        run_value_workflow(scheduler, workflow(3))
        assert resource_snapshot(database) == (
            {'seed': 4, 'changed': 12, 'total': 13}, expected_effects)
    run_value_workflow(scheduler, workflow(5))
    expected_effects += [('changed', 20), ('total', 21)]
    assert resource_snapshot(database) == (
        {'seed': 4, 'changed': 20, 'total': 21}, expected_effects)
    current = task(name='change', namespace='f09.transitions')(transition_second)
    run_value_workflow(scheduler, workflow(5))
    expected_effects += [('changed', 27), ('total', 28)]
    assert resource_snapshot(database) == (
        {'seed': 4, 'changed': 27, 'total': 28}, expected_effects)
    run_value_workflow(scheduler, workflow(5))
    assert resource_snapshot(database)[1] == expected_effects


def test_f09_t03(tmp_path):
    scheduler = repository_scheduler(tmp_path / 'repo')
    database = tmp_path / 'resource.db'
    create_resource(database)

    @task(namespace='f09.revert')
    def initialize():
        handle = DatabaseHandle('resource', str(database))
        handle.put('seed', 4)
        return handle

    @task(namespace='f09.revert')
    def dependent(handle):
        handle.put('total', handle.get('changed') + 1)
        return handle

    @task(namespace='f09.revert')
    def workflow():
        return dependent(current(initialize(), 3))

    effects = [('seed', 4)]
    for version, implementation, changed in [
            ('first', transition_first, 12), ('second', transition_second, 19),
            ('first', transition_first, 12)]:
        current = task(name='change', namespace='f09.revert', version=version)(implementation)
        run_value_workflow(scheduler, workflow())
        effects += [('changed', changed), ('total', changed + 1)]
        assert resource_snapshot(database) == (
            {'seed': 4, 'changed': changed, 'total': changed + 1}, effects)
    run_value_workflow(scheduler, workflow())
    assert resource_snapshot(database)[1] == effects


def test_f09_t04(tmp_path):
    scheduler = repository_scheduler(tmp_path / 'repo')
    database = tmp_path / 'resource.db'
    create_resource(database)

    @task(namespace='f09.branches')
    def initialize():
        handle = DatabaseHandle('resource', str(database))
        handle.put('seed', 2)
        return handle

    @task(namespace='f09.branches')
    def branch(handle, label, value):
        handle.put(label, handle.get('seed') + value)
        return handle

    @task(namespace='f09.branches')
    def dependent(handle, label):
        handle.put(label + '_done', handle.get(label) * 2)
        return handle

    @task(namespace='f09.branches')
    def finish(handle):
        handle.put('merged', handle.get('left_done') + handle.get('right_done'))
        return handle

    @task(namespace='f09.branches')
    def workflow(left):
        handle = initialize()
        return finish(merge_handles([
            dependent(branch(handle.fork('left'), 'left', left), 'left'),
            dependent(branch(handle.fork('right'), 'right', 11), 'right')]))

    run_value_workflow(scheduler, workflow(5))
    state, effects = resource_snapshot(database)
    assert state == {'seed': 2, 'left': 7, 'right': 13, 'left_done': 14,
                     'right_done': 26, 'merged': 40}
    # Branches may interleave, but each branch and the merge must respect dependencies.
    assert sorted(effects) == sorted(state.items())
    assert effects.index(('left', 7)) < effects.index(('left_done', 14))
    assert effects.index(('right', 13)) < effects.index(('right_done', 26))
    assert effects[-1] == ('merged', 40)
    run_value_workflow(scheduler, workflow(5))
    assert resource_snapshot(database) == (state, effects)
    run_value_workflow(scheduler, workflow(9))
    state, updated = resource_snapshot(database)
    assert state == {'seed': 2, 'left': 11, 'right': 13, 'left_done': 22,
                     'right_done': 26, 'merged': 48}
    assert updated == effects + [('left', 11), ('left_done', 22), ('merged', 48)]
    run_value_workflow(scheduler, workflow(9))
    assert resource_snapshot(database) == (state, updated)
