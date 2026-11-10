# feature: F10
"""Authored computations and external effects for workflow controls."""
import time
from pathlib import Path

from velnora import task
from velnora.functools import force
from velnora.scheduler import join_thread
from velnora.task import wraps_task
from F01_helpers import identity
from F08_helpers import audit
from F06_helpers import increment


class ControlFailure(ValueError):
    pass


class HandlerFailure(RuntimeError):
    pass


@task(namespace='f10', cache=False)
def effect(value, path, label, required=None):
    if required is not None:
        assert Path(required).read_text() == 'done'
    audit(path, label)
    return value


@task(namespace='f10', cache=False)
def reject(kind=ControlFailure):
    raise kind('Authored failure')


@task(namespace='f10', cache=False)
def recover(error, path):
    audit(path, 'handled')
    assert isinstance(error, (ControlFailure, KeyError))
    return identity(73)


@task(namespace='f10', cache=False)
def broken_handler(error):
    raise HandlerFailure('Handler failed')


@task(namespace='f10', cache=False)
def group_handler(values, path):
    audit(path, 'handled')
    assert values['ok'] == (19,)
    assert isinstance(values['bad'][0], ControlFailure)
    assert isinstance(values['bad'][1], KeyError)
    assert Path(path + '.settled').read_text() == 'done'
    return identity({'recovered': 47})


@task(namespace='f10', cache=False)
def finish(path, duration=.1):
    time.sleep(duration)
    Path(path).write_text('done')
    return 19


@task(namespace='f10', cache=False)
def describe(error):
    # The handler's answer is derived only from the failure object it received.
    return identity((type(error).__name__, error.args[0]))


@task(namespace='f10', cache=False)
def observe_settled(error, required):
    # Runs as soon as the failure surfaces; the slow member must already be done.
    assert Path(required).read_text() == 'done'
    return identity((type(error).__name__, 'settled'))


@task(namespace='f10', cache=False)
def pause(value):
    time.sleep(value)
    return value


@task(namespace='f10')
def arithmetic(a, b=2, c=3):
    return 100 * a + 10 * b + c


@task(namespace='f10')
def invoke(function, *args, **kwargs):
    return function(*args, **kwargs)


@task(namespace='f10')
def pieces(value):
    return [value, -value] if value else []


@task(namespace='f10')
def double(value):
    return 2 * value


def plain(a, b, scale=1):
    return (a - b) * scale


def plain_failure(value):
    raise ControlFailure(value)


@task(namespace='f10', cache=False)
def evaluate_later(value, path):
    assert not Path(path).exists()
    return force(value)


def additive_wrapper(offset=1):
    @wraps_task(wrapper_hash_includes=[offset])
    def add(inner):
        def wrapped(*args, **kwargs):
            return inner.func(*args, **kwargs) + offset
        return wrapped
    return add


def multiplicative_wrapper(offset=1):
    @wraps_task(wrapper_hash_includes=[offset])
    def add(inner):
        def wrapped(*args, **kwargs):
            return inner.func(*args, **kwargs) * 3 + offset
        return wrapped
    return add


@wraps_task(use_wrapper_signature=True)
def extra_argument(inner):
    def wrapped(value: int, offset: int):
        return inner.func(value) + offset
    return wrapped


def original_body(value, path):
    audit(path, 'body')
    return value + 2


def changed_body(value, path):
    audit(path, 'body')
    return value + 9


@task(namespace='f10', cache=False)
def background(path, fail=False):
    Path(path + '.started').write_text('started')
    deadline = time.monotonic() + 8
    while not Path(path + '.release').exists():
        if time.monotonic() >= deadline:
            raise AssertionError('Consumer did not release background work')
        time.sleep(.01)
    if fail:
        raise ControlFailure('Background failed')
    Path(path + '.done').write_text('done')
    return 61


@task(namespace='f10', cache=False)
def consumer(reference, path):
    deadline = time.monotonic() + 8
    while not Path(path + '.started').exists():
        if time.monotonic() >= deadline:
            raise AssertionError('Background work did not start before join')
        time.sleep(.01)
    assert not Path(path + '.done').exists()
    Path(path + '.release').write_text('release')
    return [join_thread(reference), join_thread(reference)]
