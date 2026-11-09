# feature: F08
"""Acceptance tests for incremental execution and reuse policies."""
from pathlib import Path
from threading import Event

import pytest
from velnora import File, catch, task
from velnora.functools import no_prov

from _helpers import memory_scheduler, run_workflow
from F01_helpers import identity, AuthoredFailure
from F02_helpers import run_value_workflow
from F04_helpers import context_branch, context_leaf
from F06_helpers import decoded_record, history_snapshot, records_of, prepare_repository
from F08_helpers import (audit, fresh_reuse, repository_scheduler, affine_first,
                         affine_second, dependency_first, dependency_second)


def test_f08_t01(tmp_path):
    calls = []
    started, released = Event(), Event()

    @task(namespace='f08.sharing')
    def work(value):
        calls.append(value)
        started.set()
        assert released.wait(10), 'Equivalent requester did not arrive'
        return value * 9

    @task(namespace='f08.sharing')
    def later(value):
        assert started.wait(10), 'Original work did not start'
        released.set()
        return work(value)

    expression = work(13)
    assert run_value_workflow(memory_scheduler(), [expression, expression, later(identity(13)),
                                          work(identity(13))]) == [117] * 4
    assert calls == [13]


def test_f08_t02(tmp_path):
    repo, effect = tmp_path / 'repo', tmp_path / 'audit'
    prepare_repository(repo)
    assert fresh_reuse(repo, effect, 17) == 122
    assert fresh_reuse(repo, effect, 17) == 122
    assert effect.read_text().splitlines() == ['work']
    assert fresh_reuse(repo, effect, 23) == 164
    assert effect.read_text().splitlines() == ['work', 'work']
    snapshot = history_snapshot(repo)
    jobs = records_of(snapshot, 'Job', 'log')
    calls = {row['call_hash']: row for row in records_of(snapshot, 'CallNode')}
    values = {row['value_hash']: decoded_record(row) for row in records_of(snapshot, 'Value')
              if row['value_hash'] in {call['value_hash'] for call in calls.values()}}
    # Each recorded job is identified by its independently computed result.
    observed = sorted((values[calls[job['call_hash']]['value_hash']], job['status'], job['cached'])
                      for job in jobs)
    assert observed == [(122, 'CACHED', True), (122, 'DONE', False), (164, 'DONE', False)]


def test_f08_t03(tmp_path):
    for change in ('source', 'name', 'namespace', 'argument'):
        scheduler = repository_scheduler(tmp_path / change)
        effect = str(tmp_path / (change + '.txt'))
        options = dict(name='compute', namespace='f08.' + change)
        current = task(**options)(affine_first)
        stable = task(name='stable', namespace='f08.' + change)(affine_first)
        assert run_value_workflow(scheduler, [current(6, effect), stable(8, effect)]) == [13, 17]
        if change == 'name':
            options['name'] = 'renamed'
        if change == 'namespace':
            options['namespace'] += '.renamed'
        current = task(**options)(affine_second if change == 'source' else affine_first)
        value = 9 if change == 'argument' else 6
        expected = 17 if change == 'source' else value * 2 + 1
        assert run_value_workflow(scheduler, [current(value, effect) + 10, stable(8, effect)]) == [expected + 10, 17]
        assert sorted(Path(effect).read_text().splitlines()) == sorted([
            'first', 'first', 'second' if change == 'source' else 'first'])


def test_f08_t04(tmp_path):
    scheduler = repository_scheduler(tmp_path / 'repo')
    effect = str(tmp_path / 'audit')
    options = dict(name='versioned', namespace='f08.version', version='z-release')
    current = task(**options)(affine_first)
    assert run_value_workflow(scheduler, current(4, effect)) == 9
    current = task(**options)(affine_second)
    assert run_value_workflow(scheduler, current(4, effect)) == 9
    options['version'] = 'a-release'
    current = task(**options)(affine_second)
    assert run_value_workflow(scheduler, current(4, effect)) == 13
    assert Path(effect).read_text().splitlines() == ['first', 'second']
    for includes in ([dependency_first, 'alpha'], [dependency_second, 'alpha'],
                     [dependency_second, 'beta']):
        current = task(name='included', namespace='f08.version', version='fixed',
                       hash_includes=includes)(affine_first)
        assert run_value_workflow(scheduler, current(5, effect)) == 11
        assert run_value_workflow(scheduler, current(5, effect)) == 11
    assert Path(effect).read_text().splitlines() == ['first', 'second'] + ['first'] * 3


def test_f08_t05(tmp_path):
    scheduler = repository_scheduler(tmp_path / 'repo')
    calls = []

    @task(namespace='f08.config', config_args=['workers'])
    def configured(value, workers=1, factor=3):
        calls.append((value, workers, factor))
        return value * factor

    assert run_value_workflow(scheduler, configured(7)) == 21
    assert run_value_workflow(scheduler, configured(7, workers=9)) == 21
    assert run_value_workflow(scheduler, configured(7, 5)) == 21
    assert calls == [(7, 1, 3)]
    assert run_value_workflow(scheduler, configured(7, workers=9, factor=4)) == 28
    assert calls == [(7, 1, 3), (7, 9, 4)]
    # A default change is meaningful even when task source has an explicit version.
    current = task(name='defaults', namespace='f08.config', version='same')(affine_first)
    path = str(tmp_path / 'default-audit')
    assert run_value_workflow(scheduler, current(7, path)) == 15
    def changed_default(value, audit_path, setting=6):
        return affine_first(value, audit_path, setting)
    current = task(name='defaults', namespace='f08.config', version='same')(changed_default)
    assert run_value_workflow(scheduler, current(7, path)) == 43
    assert Path(path).read_text().splitlines() == ['first', 'first']


def test_f08_t06(tmp_path):
    for mode in ('full', 'shallow'):
        root = tmp_path / mode
        root.mkdir()
        scheduler = repository_scheduler(root / 'repo')
        middle, final = root / 'middle', root / 'final'
        calls = []

        @task(name='produce', namespace='f08.' + mode)
        def produce():
            calls.append('produce')
            middle.write_text('intermediate payload')
            return File(str(middle))

        @task(name='finish', namespace='f08.' + mode)
        def finish(source):
            calls.append('finish')
            final.write_text(Path(source.path).read_text() + ' transformed')
            return File(str(final))

        @task(name='flow', namespace='f08.' + mode)
        def flow():
            return finish(produce())

        def execute():
            expression = flow() if mode == 'full' else flow.options(check_valid='shallow')()
            result = run_value_workflow(scheduler, expression)
            assert Path(result.path).read_text() == 'intermediate payload transformed'

        execute()
        assert calls == ['produce', 'finish']
        middle.unlink()
        execute()
        assert middle.exists() is (mode == 'full')
        assert calls.count('produce') == (2 if mode == 'full' else 1)
        finishes_before = calls.count('finish')
        final.unlink()
        execute()
        assert middle.read_text() == 'intermediate payload'
        assert calls.count('finish') == finishes_before + 1
        # A changed called task invalidates even a valid final result.
        @task(name='produce', namespace='f08.' + mode)
        def produce():
            calls.append('changed')
            middle.write_text('intermediate payload')
            return File(str(middle))
        execute()
        assert calls.count('changed') == 1


def test_f08_t07(tmp_path):
    for scope, per_run in [('BACKEND', 1), ('CSE', 1), ('NONE', 2)]:
        scheduler = repository_scheduler(tmp_path / scope)
        calls = []

        @task(namespace='f08.scope.' + scope, cache_scope=scope)
        def compute(value):
            calls.append(value)
            return value * 5

        for run in range(2):
            shared = compute(identity(11))
            assert run_value_workflow(scheduler, [shared, shared, compute(identity(12) - 1)]) == [55] * 3
            assert len(calls) == (1 if scope == 'BACKEND' else per_run * (run + 1))


def test_f08_t08(tmp_path):
    scheduler = repository_scheduler(tmp_path / 'repo')
    calls = []

    @task(namespace='f08.record')
    def compute(value):
        calls.append(value)
        return value * 6

    result = run_workflow(scheduler, compute(12), run_kwargs={'cache': False})
    assert result.exception is None, result
    assert result.value == 72
    assert calls == [12]
    snapshot = history_snapshot(tmp_path / 'repo')
    assert any(row['status'] == 'DONE' for row in records_of(snapshot, 'Job', 'log'))
    assert run_value_workflow(scheduler, compute(12)) == 72
    assert calls == [12]
    jobs = records_of(history_snapshot(tmp_path / 'repo'), 'Job', 'log')
    assert sorted((row['status'], row['cached']) for row in jobs) == [
        ('CACHED', True), ('DONE', False)]
    # A recorded result exists, yet disabled reads execute the body again.
    result = run_workflow(scheduler, compute(12), run_kwargs={'cache': False})
    assert result.exception is None, result
    assert result.value == 72
    assert calls == [12, 12]
    jobs = records_of(history_snapshot(tmp_path / 'repo'), 'Job', 'log')
    assert sorted((row['status'], row['cached']) for row in jobs) == [
        ('CACHED', True), ('DONE', False), ('DONE', False)]
    assert run_value_workflow(scheduler, compute(12)) == 72
    assert calls == [12, 12]


def test_f08_t09(tmp_path):
    scheduler = repository_scheduler(tmp_path / 'repo')
    calls = []

    @task(namespace='f08.recovery')
    def broken():
        calls.append('broken')
        raise AuthoredFailure('retryable')

    @task(namespace='f08.recovery')
    def recover(error):
        calls.append('recover')
        return 31

    for _ in range(2):
        with pytest.raises(AuthoredFailure):
            run_value_workflow(scheduler, broken())
    assert calls == ['broken', 'broken']
    assert run_value_workflow(scheduler, catch(broken(), AuthoredFailure, recover)) == 31
    assert run_value_workflow(scheduler, catch(broken(), AuthoredFailure, recover)) == 31
    assert calls == ['broken'] * 3 + ['recover']
    @task(namespace='f08.recovery')
    def recover(error):
        calls.append('new recovery')
        return 47
    assert run_value_workflow(scheduler, catch(broken(), AuthoredFailure, recover)) == 47
    assert calls[-2:] == ['broken', 'new recovery']


def test_f08_t10(tmp_path):
    for mode in ('full', 'shallow'):
        scheduler = repository_scheduler(tmp_path / mode)
        for values in [('hammer', 'saw'), ('drill', 'plane'), ('hammer', 'saw')]:
            expressions = [context_branch.options(check_valid=mode).update_context(tool=value)()
                           for value in values]
            assert run_value_workflow(scheduler, expressions) == [
                {'self': value, 'child': value} for value in values]

        # The execution context reaches work whose own arguments do not mention it.
        @task(name='context_parent', namespace='f08.context.' + mode)
        def context_parent():
            return {'child': context_leaf()}

        for value in ('chisel', 'file', 'chisel', 'file'):
            result = run_workflow(scheduler, context_parent.options(check_valid=mode)(),
                                  run_kwargs={'context': {'tool': value}})
            assert result.exception is None, result
            assert result.value == {'child': value}


def test_f08_t11(tmp_path):
    for policy in ('baseline', 'option', 'wrapper'):
        scheduler = repository_scheduler(tmp_path / policy)
        calls = []

        @task(namespace='f08.provenance.' + policy)
        def leaf(value):
            calls.append('leaf')
            return value * 3

        @task(namespace='f08.provenance.' + policy)
        def branch(value):
            calls.append('branch')
            return leaf(value) + 4

        @task(namespace='f08.provenance.' + policy)
        def outer(value):
            if policy == 'option':
                return branch.options(prov=False)(value) + 1
            if policy == 'wrapper':
                return no_prov(branch(value)) + 1
            return branch(value) + 1

        assert run_value_workflow(scheduler, branch(8)) == 28
        assert calls == ['branch', 'leaf']
        old_jobs = {row['id'] for row in records_of(
            history_snapshot(tmp_path / policy), 'Job')}
        calls.clear()
        # Bypass only the enclosing call's reuse; the scope remains identical.
        for _ in range(2):
            assert run_value_workflow(scheduler, outer.options(cache_scope='NONE')(8)) == 29
        assert calls.count('leaf') == {'baseline': 0, 'option': 2, 'wrapper': 1}[policy]
        snapshot = history_snapshot(tmp_path / policy)
        calls_by_hash = {row['call_hash']: row for row in records_of(snapshot, 'CallNode')}
        task_names = {calls_by_hash[row['call_hash']]['task_name']
                      for row in records_of(snapshot, 'Job') if row['id'] not in old_jobs}
        leaf_name = 'f08.provenance.' + policy + '.leaf'
        assert (leaf_name in task_names) is (policy == 'baseline')
        # A recorded wrapper can retain the final result without retaining descendants.
        assert run_value_workflow(scheduler, outer(8)) == 29
        before = list(calls)
        assert run_value_workflow(scheduler, outer(8)) == 29
        if policy == 'option':
            assert calls == before + ['branch', 'leaf']
        else:
            assert calls == before
