# feature: F08
"""Real authored work and durable independent execution observations."""
import json
import os
from pathlib import Path

import velnora
from velnora import task
from _helpers import run_python
from F02_helpers import run_value_workflow
from F06_helpers import history_scheduler, prepare_repository


def audit(path, label):
    with Path(path).open('a', encoding='utf-8') as stream:
        stream.write(label + '\n')


@task(namespace='f08.durable')
def durable(value, audit_path):
    audit(audit_path, 'work')
    return value * 7 + 3


def fresh_reuse(repository, audit_path, value):
    source = '''import sys, json
from F08_helpers import durable
from F06_helpers import history_scheduler
from F02_helpers import run_value_workflow
answer = run_value_workflow(history_scheduler(sys.argv[1]), durable(int(sys.argv[3]), sys.argv[2]))
open(sys.argv[4], 'w').write(json.dumps(answer))
'''
    target = repository / 'answer.json'
    result = run_python(source, cwd=repository.parent,
                        args=[str(repository), str(audit_path), str(value), str(target)],
                        env={'PYTHONPATH': os.pathsep.join([
                            str(Path(__file__).parent),
                            str(Path(velnora.__file__).resolve().parent.parent)])}, timeout=90)
    assert result.returncode == 0, result
    return json.loads(target.read_text())


def repository_scheduler(path):
    prepare_repository(path)
    return history_scheduler(path)


def affine_first(value, audit_path, setting=2):
    audit(audit_path, 'first')
    return value * setting + 1


def affine_second(value, audit_path, setting=2):
    audit(audit_path, 'second')
    return value * setting + 5


def dependency_first(value):
    return value + 1


def dependency_second(value):
    return value + 5
