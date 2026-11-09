# feature: F01
"""Author values and bounded workflow invocation for dynamic task tests."""
from collections import namedtuple
from dataclasses import dataclass

from velnora import task
from _helpers import memory_scheduler, run_workflow

Pair = namedtuple("Pair", "left right")


@dataclass
class Bundle:
    value: object
    other: object


class AuthoredFailure(Exception):
    pass


@task(namespace="f01.common")
def identity(value):
    return value


@task(namespace="f01.common")
def fail(value):
    raise AuthoredFailure(value)


def resolved(expression):
    """Run real work in a fresh scheduler and preserve original failures."""
    result = run_workflow(memory_scheduler(), expression)
    if result.exception is not None:
        raise result.exception
    return result.value
