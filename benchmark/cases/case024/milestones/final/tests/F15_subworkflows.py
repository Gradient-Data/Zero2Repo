# feature: F15
"""Public subworkflow, publication, launch, and delegation acceptance checks."""
import copy
import io
import importlib
import sys
import secrets

import pytest
import os
from pathlib import Path

from requests import HTTPError
from _helpers import memory_scheduler
from velnora.cli import VelnoraClient, VelnoraClientError
from velnora.federated_tasks import (federated_task, lambda_federated_task,
                                   rest_federated_task)
from velnora.scheduler import SchedulerError, subrun
from velnora.scripting import ScriptError

from _helpers import (InvocationTimeout, candidate_cli_environment, execute_client, run_process, run_workflow,
                      working_environment, write_text)
from F01_helpers import AuthoredFailure, fail
from F02_helpers import run_value_workflow
from F06_helpers import history_snapshot, records_of
from F08_helpers import durable
from F15_helpers import (completed_worker, deployed_worker, counted, duplicate_federation, dynamic, f15_config,
                         f15_scheduler, launch_endpoint, leaf, parent,
                         published_config, save_publication_config,
                         saved_submission,
                         invoke_isolated_publication)


def test_f15_t01(tmp_path):
    config = f15_config(tmp_path)
    scheduler = f15_scheduler(config)
    result = run_value_workflow(scheduler, parent(11))
    assert [item['answer'] for item in result['child']['nested']] == [80, 94]
    assert all(item['pid'] != result['pid'] for item in result['child']['nested'])
    separate = tmp_path / 'separate'
    separate.mkdir()
    result = run_value_workflow(scheduler, subrun(
        dynamic(-4), executor='process', config=f15_config(separate),
        new_execution=True, load_modules=['F15_helpers']))
    assert [item['answer'] for item in result['nested']] == [-25, -11]
    failure = run_workflow(scheduler, subrun(
        fail('authored subworkflow failure'), executor='process',
        load_modules=['F01_helpers']))
    assert isinstance(failure.exception, AuthoredFailure), failure.exception
    assert failure.exception.args == ('authored subworkflow failure',)
    # A separately identifiable subworkflow execution also returns its failure.
    failing = tmp_path / 'separate-failure'
    failing.mkdir()
    failure = run_workflow(scheduler, subrun(
        fail('separate subworkflow failure'), executor='process',
        config=f15_config(failing), new_execution=True, load_modules=['F01_helpers']))
    assert isinstance(failure.exception, AuthoredFailure), failure.exception
    assert failure.exception.args == ('separate subworkflow failure',)


def test_f15_t02(tmp_path):
    for separate in (False, True):
        directory = tmp_path / str(separate)
        directory.mkdir()
        config = f15_config(directory)
        save_publication_config(directory, config)
        result = run_value_workflow(f15_scheduler(config),
            parent.update_context(factor=17).export_options(priority=37)(5, separate))
        children = result['child']['nested']
        assert [item['answer'] for item in children] == [38, 52]
        assert all(item['context'] == 17 and item['exported'] == 37
                   for item in children)
        snapshot = history_snapshot(directory)
        jobs = {row['id']: row for row in records_of(snapshot, 'Job')}
        calls = {row['call_hash']: row for row in records_of(snapshot, 'CallNode')}
        root = next(row for row in jobs.values()
                    if calls[row['call_hash']]['task_name'] == 'f15.parent')
        for child in children:
            job = jobs[child['job']]
            assert job['execution_id'] == child['execution']
            assert (job['execution_id'] != root['execution_id']) is separate
            chain = job
            visited = set()
            while chain['parent_id'] is not None:
                assert chain['id'] not in visited, 'Cyclic job ancestry'
                visited.add(chain['id'])
                chain = jobs[chain['parent_id']]
            if separate:
                assert chain['execution_id'] != root['execution_id']
            else:
                assert chain['id'] == root['id']
    directory = tmp_path / 'no-provenance'
    directory.mkdir()
    config = f15_config(directory)
    save_publication_config(directory, config)
    remote = tmp_path / 'no-provenance-child'
    remote.mkdir()
    child_config = f15_config(remote)
    save_publication_config(remote, child_config)
    result = run_value_workflow(f15_scheduler(config),
                                parent.options(prov=False)(9, config=child_config))
    answer = result['child']
    assert [item['answer'] for item in answer['nested']] == [66, 80]
    assert all(item['execution'] and item['execution'] != result['execution']
               for item in answer['nested'])
    assert answer['nested'][0]['execution'] == answer['nested'][1]['execution']


def test_f15_t03(tmp_path):
    # Explicitly deploy source only inside the configured worker interpreter.
    # The caller never gains that source directory on its own import path.
    source_directory = tmp_path / 'worker-source'
    source_directory.mkdir()
    module_name = 'f15_isolated_workflow'
    write_text(source_directory / (module_name + '.py'), """
import os
from velnora import task
from velnora.scheduler import JobInfo

@task(namespace='f15.isolated')
def transform(value, offset):
    return value * value + offset

@task(namespace='f15.isolated', cache=False)
def workflow(value, offset=0, info=JobInfo()):
    return {'values': [transform(value, offset), transform(value + 1, offset)],
            'pid': os.getpid(), 'execution': info.execution_id, 'job': info.job_id}
""")
    config = f15_config(tmp_path)
    # The publication's own configuration selects a repository distinct from
    # the caller's, so the remote execution must be recorded there.
    remote = tmp_path / 'remote'
    remote.mkdir()
    save_publication_config(remote, {'backend': {
        'db_uri': 'sqlite:///' + str(remote / 'history.db')}})
    config['executors.deployed'] = {
        'type': 'docker', 'image': 'acceptance/worker:deployment',
        'scratch': str(tmp_path / 'deployment-scratch'),
        'job_monitor_interval': '0.1', 'include_aws_env': 'False',
        'code_package': 'True', 'code_includes': '*.py'}
    config['federated_tasks.isolated'] = {
        'namespace': 'f15.isolated', 'task_name': 'workflow',
        'load_module': module_name, 'executor': 'deployed',
        'config_dir': str(remote), 'new_execution': 'True'}
    save_publication_config(tmp_path, config)
    assert module_name not in sys.modules
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)
    value, offset = -secrets.randbelow(100) - 2, secrets.randbelow(1000)
    with deployed_worker(tmp_path / 'worker', source_directory) as runs:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module_name)
        result = run_value_workflow(f15_scheduler(config),
                                    invoke_isolated_publication(value, offset=offset))
        submitted = runs()
        assert len(submitted) == 1
        runs.wait(submitted[0]['id'])
        assert module_name not in sys.modules
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module_name)
    assert result['remote']['values'] == [value * value + offset,
                                         (value + 1) * (value + 1) + offset]
    assert result['remote']['pid'] != os.getpid()
    assert result['remote']['execution'] != result['caller_execution']
    assert module_name not in sys.modules
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)
    snapshot = history_snapshot(remote)
    executions = {row['id']: row for row in records_of(snapshot, 'Execution')}
    jobs = {row['id']: row for row in records_of(snapshot, 'Job')}
    child = jobs[result['remote']['job']]
    assert child['execution_id'] == result['remote']['execution']
    assert child['parent_id'] is None
    assert executions[result['remote']['execution']]['job_id'] == child['id']
    caller = history_snapshot(tmp_path)
    caller_ids = {row['id'] for row in records_of(caller, 'Execution')}
    assert result['caller_execution'] in caller_ids
    assert result['remote']['execution'] not in caller_ids
    assert result['remote']['job'] not in {row['id'] for row in records_of(caller, 'Job')}


def test_f15_t04(tmp_path):
    config = published_config(tmp_path / 'publication')
    assert run_value_workflow(f15_scheduler(copy.deepcopy(config)),
                              federated_task('published', 12)) == 87
    rejected = run_workflow(f15_scheduler(copy.deepcopy(config)), federated_task('unknown', 12))
    assert isinstance(rejected.exception, AssertionError), rejected.exception
    for setting in ('namespace', 'task_name', 'load_module', 'executor', 'config_dir'):
        incomplete = copy.deepcopy(config)
        del incomplete['federated_tasks.published'][setting]
        rejected = run_workflow(f15_scheduler(incomplete), federated_task('published', 12))
        assert isinstance(rejected.exception, AssertionError), (setting, rejected.exception)
    invalid = copy.deepcopy(config)
    invalid['federated_tasks.published']['executor'] = 'unknown'
    rejected = run_workflow(f15_scheduler(invalid), federated_task('published', 12))
    assert isinstance(rejected.exception, SchedulerError), rejected.exception


def test_f15_t05(tmp_path):
    config = f15_config(tmp_path)
    save_publication_config(tmp_path, config)
    source = write_text(tmp_path / 'workflow.py',
        'from velnora import task\n@task()\ndef main(value: int):\n    return value * 9 - 2\n')
    command = ['velnora', '-c', str(tmp_path), 'run', str(source), 'main', '--value', '8']
    output = io.StringIO()
    with candidate_cli_environment() as cli_env, working_environment(cwd=tmp_path, env=cli_env):
        result = execute_client(VelnoraClient(stdout=output), ['velnora', '-c', str(tmp_path),
            'launch', '--executor', 'default', '--wait', *command])
        assert result.exception is None, result.exception
        # launch --wait displays the captured command stdout as a bytes repr.
        import ast
        command_stdout = ast.literal_eval(output.getvalue().strip())
        assert command_stdout.decode().strip() == '70'
        failure = execute_client(VelnoraClient(), ['velnora', '-c', str(tmp_path),
            'launch', '--executor', 'default', '--wait', 'bash', '-c', 'exit 23'])
        assert isinstance(failure.exception, ScriptError), failure.exception
        missing = execute_client(VelnoraClient(), ['velnora', '-c', str(tmp_path),
            'launch', '--wait', *command])
        assert isinstance(missing.exception, VelnoraClientError), missing.exception

    # Without --wait, Docker and AWS Batch submissions return before the command
    # completes and identify the submitted container or service job.
    _launch_without_wait(tmp_path)


def _launch_without_wait(tmp_path):
    from F03_services import object_store
    from F13_helpers import (_python_path, batch_config, batch_stand_in, docker_stand_in)

    def write_config(directory, sections):
        directory.mkdir()
        lines = ['[backend]', 'db_uri = sqlite:///' + str(directory / 'velnora.db')]
        for name, values in sections.items():
            lines.append('[' + name + ']')
            lines.extend('{} = {}'.format(key, value) for key, value in values.items())
        write_text(directory / 'velnora.ini', '\n'.join(lines) + '\n')
        return directory

    def launch(directory, executor, gate, done):
        command = 'while [ ! -e {0} ]; do sleep 0.1; done; echo finished > {1}'.format(gate, done)
        # The command cannot finish before the gate opens, and the gate opens
        # only after launch returns, so a launch that waits never returns here.
        try:
            result = run_process([sys.executable, '-c', 'from velnora.cli import main; main()',
                                  '-c', str(directory), 'launch', '--executor', executor,
                                  'bash', '-c', command], cwd=tmp_path, timeout=45,
                                 env={'PYTHONPATH': _python_path()})
        except InvocationTimeout:
            Path(gate).write_text('open')
            raise AssertionError('launch without --wait did not return before completion')
        assert result.returncode == 0, result
        # Submission returns while the command still waits for its gate.
        assert not Path(done).exists()
        return result.stderr

    with working_environment(cwd=tmp_path), docker_stand_in(tmp_path) as runs:
        directory = write_config(tmp_path / 'docker-launch', {'executors.box': {
            'type': 'docker', 'image': 'acceptance/launcher:5',
            'scratch': str(tmp_path / 'docker-scratch'), 'include_aws_env': 'False'}})
        gate, done = tmp_path / 'docker-gate', tmp_path / 'docker-done'
        stderr = launch(directory, 'box', gate, done)
        submitted = runs()
        assert len(submitted) == 1 and submitted[0]['image'] == 'acceptance/launcher:5'
        # The diagnostic stream names the container the service reported.
        assert submitted[0]['id'] in stderr
        gate.write_text('open')
        runs.wait(submitted[0]['id'])
        assert done.read_text() == 'finished\n'

    with object_store('s3') as store:
        environment = {name: os.environ[name] for name in (
            'AWS_ENDPOINT_URL_S3', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY',
            'AWS_DEFAULT_REGION')}
        with batch_stand_in(tmp_path, environment) as (service, _):
            directory = write_config(tmp_path / 'batch-launch', batch_config(
                'batch', 'q-launch', store.url('launch-scratch')))
            gate, done = tmp_path / 'batch-gate', tmp_path / 'batch-done'
            stderr = launch(directory, 'batch', gate, done)
            assert [s['request']['jobQueue'] for s in service.submissions] == ['q-launch']
            assert service.submissions[0]['jobId'] in stderr
            gate.write_text('open')
            service.wait(service.submissions[0]['jobId'])
            assert done.exists()


def test_f15_t06(tmp_path):
    config = f15_config(tmp_path)
    # The child explicitly needs an executor that exists only in the selected config.
    config['executors.inherited'] = {'type': 'local', 'mode': 'thread'}
    scheduler = f15_scheduler(config)
    answer = run_value_workflow(scheduler, subrun(
        leaf.options(executor='inherited')(6), executor='process',
        load_modules=['F15_helpers']))
    assert answer['answer'] == 45
    separate = tmp_path / 'explicit'
    separate.mkdir()
    supplied = f15_config(separate)
    supplied['executors.supplied'] = {'type': 'local', 'mode': 'thread'}
    save_publication_config(separate, supplied)
    # Only a nonempty explicit configuration conflicts with a location; an
    # empty mapping beside a location is not a conflicting selection.
    for source in ({'config': supplied}, {'config_dir': str(separate)},
                   {'config': {}, 'config_dir': str(separate)}):
        answer = run_value_workflow(scheduler, subrun(
            leaf.options(executor='supplied')(10), executor='process',
            new_execution=True, load_modules=['F15_helpers'], **source))
        assert answer['answer'] == 73
    failure = run_workflow(scheduler, subrun(leaf(10), executor='process',
        config=supplied, config_dir=str(separate), load_modules=['F15_helpers']))
    assert isinstance(failure.exception, AssertionError), failure.exception


def test_f15_t07(tmp_path):
    config = f15_config(tmp_path)
    save_publication_config(tmp_path, config)
    scheduler = f15_scheduler(config)
    ordinary_audit = tmp_path / 'ordinary.txt'
    expression = subrun(counted(7, str(ordinary_audit)), executor='process',
                        load_modules=['F15_helpers'])
    assert run_value_workflow(scheduler, [expression, expression]) == [52, 52]
    assert ordinary_audit.read_text().splitlines() == ['performed']
    first_history = history_snapshot(tmp_path)
    first_ids = {row['id'] for row in records_of(first_history, 'Job', 'log')}
    # The inner body is deliberately non-cacheable. Reusing the outer resolved
    # result must not re-enter it, even though deep checking would find it.
    assert run_value_workflow(scheduler, expression) == 52
    assert ordinary_audit.read_text().splitlines() == ['performed']
    repeat_history = history_snapshot(tmp_path)
    repeated = [row for row in records_of(repeat_history, 'Job', 'log')
                if row['id'] not in first_ids]
    cached = [row for row in repeated if row['status'] == 'CACHED']
    assert cached
    inner_audit = tmp_path / 'inner.txt'
    for invocation in range(2):
        assert run_value_workflow(scheduler, subrun(
            durable(7, str(inner_audit)), executor='process', cache_scope='CSE',
            load_modules=['F08_helpers'])) == 52
        assert inner_audit.read_text().splitlines() == ['work']
    publication_dir = tmp_path / 'federated'
    config = published_config(publication_dir)
    scheduler = f15_scheduler(config)
    federated_audit = tmp_path / 'federated.txt'
    for expected_count in (1, 2):
        assert run_value_workflow(scheduler,
            duplicate_federation(7, str(federated_audit))) == [52, 52]
        assert federated_audit.read_text().splitlines() == ['performed'] * expected_count


def test_f15_t08(tmp_path):
    from F13_helpers import docker_stand_in

    config = published_config(tmp_path / 'publication')
    # Use an executor supporting detached launch, with an external observer of
    # the actual command exit and stderr rather than the submission callback.
    config['executors.delegated'] = {
        'type': 'docker', 'image': 'acceptance/launcher:5',
        'scratch': str(tmp_path / 'delegated-scratch'),
        'include_aws_env': 'False', 'code_package': 'False'}
    config['federated_tasks.published']['executor'] = 'delegated'
    save_publication_config(tmp_path / 'publication', config)
    result_path = tmp_path / 'result'
    configuration = str(tmp_path / 'publication')
    with docker_stand_in(tmp_path) as runs, launch_endpoint() as (url, records), \
            working_environment(cwd=tmp_path):
        # Each preview uses a different reuse selection and both positional and
        # named task arguments, so the description and saved data must carry
        # the caller's own inputs rather than a fixed selection or only kwargs.
        for entry, target, cache, value in ((rest_federated_task, url, True, 14),
                                            (lambda_federated_task, 'not-contacted', False, 9)):
            execution, description = run_value_workflow(memory_scheduler(), entry(
                configuration, 'published', target, str(tmp_path / 'scratch'), True,
                value, cache=cache, result_path=str(result_path)))
            assert isinstance(execution, str) and execution
            assert Path(description['input_path']).is_relative_to(tmp_path / 'scratch')
            assert description == {'config_name': configuration, 'entrypoint': 'published',
                'input_path': description['input_path'], 'execution_id': execution, 'cache': cache}
            assert saved_submission(description) == [(value,), {'result_path': str(result_path)}]
            assert records == []
            assert runs() == []
            assert not result_path.exists()
        execution, description = run_value_workflow(memory_scheduler(), rest_federated_task(
            configuration, 'published', url, str(tmp_path / 'scratch'), False,
            14, cache=True, result_path=str(result_path)))
        submitted = runs()
        assert len(submitted) == 1
        with completed_worker(runs, submitted[0]['id']):
            snapshot = history_snapshot(tmp_path / 'publication' / 'remote')
            executions = {row['id']: row for row in records_of(snapshot, 'Execution')}
            assert execution in executions
            jobs = {row['id']: row for row in records_of(snapshot, 'Job', 'log')}
            root = jobs[executions[execution]['job_id']]
            assert root['status'] == 'DONE', root
            assert result_path.read_text() == '101'
            assert records == [{key: str(value) for key, value in description.items()}]
            assert description['execution_id'] == execution
            assert description['cache'] is True
            assert saved_submission(description) == [(14,), {'result_path': str(result_path)}]
        for submitted, status in enumerate((403, 422), start=2):
            rejected = run_workflow(memory_scheduler(), rest_federated_task(
                configuration, 'published', url + f'/reject/{status}',
                str(tmp_path / 'scratch'), False, 1))
            assert isinstance(rejected.exception, HTTPError), rejected.exception
            assert rejected.exception.response.status_code == status
            assert len(records) == submitted

    _lambda_delegation(tmp_path, configuration, result_path)


_LAMBDA_CLIENT = r'''
import json, sys
from _helpers import memory_scheduler
from velnora.federated_tasks import lambda_federated_task
settings = json.loads(sys.argv[1])
execution, description = memory_scheduler().run(lambda_federated_task(
    settings["config"], "published", settings["function"], settings["scratch"],
    settings["dryrun"], settings["value"], cache=settings["cache"],
    result_path=settings["result"]))
print("RESULT " + json.dumps([execution, description]))
'''


def _lambda_delegation(tmp_path, configuration, result_path):
    """Delegate to a stand-in Lambda Invoke API: a preview contacts nothing, a
    real request invokes the named function with the description as payload."""
    import json
    from F13_helpers import _python_path, batch_stand_in

    with batch_stand_in(tmp_path, {}) as (service, _):
        outcomes = []
        for dryrun, function, value, cache in ((True, 'preview-fn', 5, True),
                                               (False, 'launcher-fn', 11, False)):
            settings = {'config': configuration, 'function': function,
                        'scratch': str(tmp_path / 'lambda-scratch'), 'dryrun': dryrun,
                        'value': value, 'cache': cache, 'result': str(result_path)}
            result = run_process(
                [sys.executable, '-c', _LAMBDA_CLIENT, json.dumps(settings)], cwd=tmp_path,
                env={'PYTHONPATH': _python_path(), 'AWS_ACCESS_KEY_ID': 'loopback',
                     'AWS_SECRET_ACCESS_KEY': 'loopback', 'AWS_REGION': 'us-east-1',
                     'AWS_DEFAULT_REGION': 'us-east-1'}, timeout=120)
            assert result.returncode == 0, result
            line = [item for item in result.stdout.splitlines() if item.startswith('RESULT ')]
            execution, description = json.loads(line[-1][len('RESULT '):])
            assert description['execution_id'] == execution and description['cache'] is cache
            assert saved_submission(description) == [(value,), {'result_path': str(result_path)}]
            outcomes.append(description)
            if dryrun:
                assert service.invocations == []
        assert [invocation['function'] for invocation in service.invocations] == ['launcher-fn']
        assert service.invocations[0]['payload'] == outcomes[1]
