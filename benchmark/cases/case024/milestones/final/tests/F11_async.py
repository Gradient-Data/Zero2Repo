# feature: F11
"""Acceptance tests for eager evaluation in asynchronous workflow tasks."""
from pathlib import Path

from velnora import task
from velnora.scheduler import SchedulerError

from _helpers import memory_scheduler, capture_call, run_workflow
from F01_helpers import AuthoredFailure
from F02_helpers import run_value_workflow
from F08_helpers import repository_scheduler
from F11_helpers import audited_body, failure_entry, policy_body, synchronous_entry

# Contract: declaration failures are TypeError or ValueError. KeyError is what the
# original raises when reuse is enabled and the validity selection is left to its
# default; see the coordinator note in the hardening report.
DECLARATION_REFUSALS = (TypeError, ValueError, KeyError)


def test_f11_t01():
    scheduler = memory_scheduler()
    assert run_value_workflow(scheduler, synchronous_entry([1, 4, -2])) == {
        'total': 13, 'selected': [8]}
    assert run_value_workflow(scheduler, synchronous_entry([5, 0, 3])) == {
        'total': 19, 'selected': [10, 6]}


def test_f11_t02():
    for kind in ('sync', 'async'):
        message = 'authored ' + kind + ' cause'
        recovered = run_workflow(memory_scheduler(), failure_entry(kind, message, True))
        assert recovered.exception is None, recovered.exception
        assert recovered.value == ('recovered', message)
        propagated = run_workflow(memory_scheduler(), failure_entry(kind, message, False))
        assert isinstance(propagated.exception, AuthoredFailure)
        assert propagated.exception.args == (message,)


def test_f11_t03(tmp_path):
    for name, options in [('disabled', {'cache': False}),
                          ('disabled_scope', {'cache_scope': 'NONE'}),
                          ('shallow', {'cache': True, 'check_valid': 'shallow'}),
                          ('shallow_scope', {'cache_scope': 'BACKEND', 'check_valid': 'shallow'})]:
        eager = task(namespace='f11.policy', name=name, **options)(policy_body)
        assert run_value_workflow(memory_scheduler(), eager(7)) == 23
        assert run_value_workflow(memory_scheduler(), eager(-4)) == -10

    # Full checking is the default, so enabling reuse alone selects it.
    for name, options in [('omitted', {}),
                          ('full', {'cache': True, 'check_valid': 'full'}),
                          ('default_full', {'cache': True}),
                          ('full_scope', {'cache_scope': 'BACKEND', 'check_valid': 'full'})]:
        refused = capture_call(task(namespace='f11.policy', name=name, **options),
                               (policy_body,))
        assert isinstance(refused.exception, DECLARATION_REFUSALS), refused

    # The same policy applies when the selection is changed through task options.
    adjustable = task(namespace='f11.policy', name='adjustable', cache=False)(policy_body)
    assert run_value_workflow(
        memory_scheduler(), adjustable.options(cache=True, check_valid='shallow')(7)) == 23
    audit_path = tmp_path / 'adjusted'
    guarded = task(namespace='f11.policy', name='guarded', cache=False)(audited_body)
    def run_adjusted(**options):
        return memory_scheduler().run(guarded.options(**options)(7, str(audit_path)))
    for options in ({'cache': True, 'check_valid': 'full'}, {'cache': True}):
        refused = capture_call(run_adjusted, kwargs=options)
        assert isinstance(refused.exception, DECLARATION_REFUSALS + (SchedulerError,)), refused
    assert not audit_path.exists()

    # The selection is honoured across executions of one repository.
    scheduler = repository_scheduler(tmp_path / 'repository')
    for name, options, executions in [
        ('reused', {'cache': True, 'check_valid': 'shallow'}, 1),
        ('repeated', {'cache': False}, 2),
    ]:
        trace = tmp_path / name
        chosen = task(namespace='f11.reuse', name=name, **options)(audited_body)
        for _ in range(2):
            assert run_value_workflow(scheduler, chosen(5, str(trace))) == 17
        assert trace.read_text().splitlines() == ['body'] * executions

    # A named local executor without state isolation stays allowed.
    nearby = {'executors.nearby': {'type': 'local', 'mode': 'thread'}}
    eager = task(namespace='f11.policy', name='local', cache=False)(policy_body)
    assert run_value_workflow(memory_scheduler(nearby), eager.options(executor='nearby')(7)) == 23

    # Select a real remote executor. The scheduler refuses the asynchronous
    # task before cloud submission, so no service or simulated executor is used.
    remote = {
        'executors.batch': {
            'type': 'aws_batch', 'image': 'velnora', 'queue': 'acceptance',
            's3_scratch': 's3://acceptance/scratch', 'aws_region': 'us-east-1'},
        'executors.container': {
            'type': 'docker', 'image': 'velnora', 'scratch': str(tmp_path / 'scratch')},
    }
    eager = task(namespace='f11.policy', name='remote', cache=False)(audited_body)
    for executor in ('batch', 'container'):
        trace = Path(tmp_path / ('remote-' + executor))
        refused = run_workflow(memory_scheduler(remote),
                               eager.options(executor=executor)(7, str(trace)))
        assert isinstance(refused.exception, SchedulerError), refused
        assert not trace.exists()
    # Isolated-local refusal is not asserted: the original executes async work
    # on its shared async thread even when process mode was selected. See ledger.
