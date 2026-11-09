# feature: F15
"""Authored subworkflows and a real HTTP launch consumer."""
import os
import pickle
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from velnora import Scheduler, task
from velnora.context import get_context
from velnora.config import Config
from velnora.federated_tasks import launch_federated_task
from velnora.scheduler import JobInfo, subrun

from _helpers import candidate_cli_environment, working_environment, write_text
from F08_helpers import audit


@contextmanager
def deployed_worker(directory, source_directory):
    """Deploy authored source through the public executor code-delivery entry.

    The service fixture runs the real product command in an empty worker
    directory. The configured executor packages source, and the worker loads it
    through the product's public execution boundary, independent of startup env.
    """
    from F13_helpers import docker_stand_in

    directory.mkdir()
    with docker_stand_in(directory) as runs, working_environment(cwd=source_directory):
        yield runs


@contextmanager
def completed_worker(runs, container_id):
    """Wait for command completion and retain worker logs on observation errors.

    A launch wrapper can finish successfully after recording a task failure.
    Callers must still check the workflow's history and authored result.
    """
    diagnostics = runs.wait(container_id)
    try:
        yield
    except Exception as error:
        error.add_note('Worker diagnostics:\n' + diagnostics)
        raise


@task(namespace='f15', cache=False)
def leaf(value, info=JobInfo(), context=get_context('factor', 1)):
    return {'answer': value * 7 + 3, 'pid': os.getpid(),
            'execution': info.execution_id, 'job': info.job_id,
            'context': context, 'exported': info.options.get('priority')}


@task(namespace='f15', cache=False)
def dynamic(value):
    return {'nested': [leaf(value), leaf(value + 2)]}


@task(namespace='f15', cache=False)
def parent(value, separate=False, config=None, info=JobInfo()):
    return {'pid': os.getpid(), 'execution': info.execution_id, 'child': subrun(
        dynamic(value), executor='process', new_execution=separate, config=config,
        load_modules=['F15_helpers'])}


@task(namespace='f15', cache=False)
def counted(value, audit_path):
    audit(audit_path, 'performed')
    return value * 7 + 3


@task(namespace='f15', cache=False)
def publication(value, audit_path=None, result_path=None):
    if audit_path is not None:
        audit(audit_path, 'performed')
    result = value * 7 + 3
    if result_path is not None:
        Path(result_path).write_text(str(result))
    return result


@task(namespace='f15', cache=False)
def duplicate_federation(value, audit_path):
    from velnora.federated_tasks import federated_task
    return [federated_task('published', value, audit_path=audit_path),
            federated_task('published', value, audit_path=audit_path)]


def f15_config(directory):
    return {'backend': {'db_uri': 'sqlite:///' + str(directory / 'history.db')},
            'executors.process': {'type': 'local', 'mode': 'process',
                                  'start_method': 'spawn', 'max_workers': '2'}}


def f15_scheduler(config):
    scheduler = Scheduler(Config(config))
    scheduler.load()
    return scheduler


def published_config(directory):
    directory.mkdir()
    remote = directory / 'remote'
    remote.mkdir()
    write_text(remote / 'velnora.ini', '[backend]\ndb_uri = sqlite:///' +
               str(directory / 'history.db') + '\n')
    config = f15_config(directory)
    config['federated_tasks.published'] = {
        'namespace': 'f15', 'task_name': 'publication', 'executor': 'process',
        'load_module': 'F15_helpers', 'config_dir': str(remote),
        'new_execution': 'True'}
    return config


def save_publication_config(directory, config):
    write_text(directory / 'velnora.ini', ''.join(
        '[' + section + ']\n' + ''.join(f'{k} = {v}\n' for k, v in values.items())
        for section, values in config.items()))


def saved_submission(description):
    with open(description['input_path'], 'rb') as stream:
        return pickle.load(stream)


@contextmanager
def launch_endpoint():
    """Consume real submissions using the public launch entry, recording errors."""
    records, failures = [], []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            data = {key: values[0] for key, values in parse_qs(
                self.rfile.read(int(self.headers['Content-Length'])).decode()).items()}
            records.append(data)
            if self.path.startswith('/reject/'):
                # Reject with the client-error status named by the path.
                self.send_response(int(self.path.rsplit('/', 1)[1]))
                self.end_headers()
                return
            try:
                launch_federated_task(
                    federated_config_path=data['config_name'], entrypoint=data['entrypoint'],
                    input_path=data['input_path'], execution_id=data['execution_id'],
                    cache=data['cache'] == 'True')
            except Exception as error:
                failures.append(error)
                self.send_response(500)
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        with candidate_cli_environment() as cli_env, working_environment(env=cli_env):
            yield f'http://127.0.0.1:{server.server_port}', records
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive(), 'HTTP consumer did not stop'
        if failures:
            raise failures[0]


@task(namespace='f15', cache=False)
def invoke_isolated_publication(value, offset, info=JobInfo()):
    from velnora.federated_tasks import federated_task
    return {'caller_execution': info.execution_id,
            'remote': federated_task('isolated', value, offset=offset)}
