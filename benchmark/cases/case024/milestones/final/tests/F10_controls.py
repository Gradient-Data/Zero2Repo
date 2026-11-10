# feature: F10
"""Acceptance checks for workflow control, composition, and recovery."""
from pathlib import Path
import time

import pytest
from velnora import catch, cond, task
from velnora.cli import VelnoraClient
from _helpers import execute_client, write_text
from velnora.functools import (apply_func, compose, const, delay, flat_map, flatten,
                             map_, seq, starmap, zip_, eval_)
from velnora.scheduler import catch_all, fork_thread
from F01_helpers import identity, resolved
from F02_helpers import run_value_workflow
from F08_helpers import repository_scheduler
from F10_helpers import (ControlFailure, HandlerFailure, effect, reject, recover,
                         broken_handler, group_handler, finish, arithmetic, invoke,
                         pieces, double, increment, plain, plain_failure,
                         evaluate_later, additive_wrapper, multiplicative_wrapper,
                         extra_argument, original_body, changed_body, background, consumer,
                         describe, observe_settled, pause)


def test_f10_t01(tmp_path):
    path = str(tmp_path / 'trace')
    assert resolved(cond(effect(False, path, 'p1'), effect(1, path, 'unused'),
                         effect(True, path, 'p2'), effect(29, path, 'chosen'),
                         reject(), reject(), effect(3, path, 'else'))) == 29
    assert Path(path).read_text().splitlines() == ['p1', 'p2', 'chosen']
    assert resolved(cond(False, reject(), False, reject(), identity(41))) == 41
    assert resolved(cond(True, identity(13), reject(), reject(), reject())) == 13
    # Truthiness, not identity with the boolean constants, selects a branch.
    assert resolved(cond(identity(5), identity('number'), reject())) == 'number'
    assert resolved(cond(identity(['x']), identity('list'), reject())) == 'list'
    assert resolved(cond(identity(0), reject(), identity(''), reject(),
                         identity([]), reject(), identity('final'))) == 'final'
    with pytest.raises(ControlFailure):
        resolved(cond(reject(), identity(1), identity(2)))
    # A later predicate is evaluated only after earlier false ones, and its
    # failure propagates instead of counting as false.
    later = str(tmp_path / 'later')
    with pytest.raises(ControlFailure):
        resolved(cond(identity(False), effect(1, later, 'unused'), reject(),
                      effect(2, later, 'unused'), effect(3, later, 'else')))
    assert not Path(later).exists()


def test_f10_t02(tmp_path):
    path = str(tmp_path / 'handler')
    handler = recover.partial(path=path)
    assert resolved(catch(identity(23), ValueError, handler)) == 23
    assert not Path(path).exists()
    assert resolved(catch(reject(), ValueError, handler, Exception, broken_handler)) == 73
    assert resolved(catch(reject(KeyError), (ControlFailure, KeyError), handler)) == 73
    assert Path(path).read_text().splitlines() == ['handled', 'handled']
    # Selection walks the pairs: a non-matching first pair is skipped, and the
    # first match wins even when it names only a parent type.
    assert resolved(catch(reject(), KeyError, broken_handler, ValueError, describe)) == (
        'ControlFailure', 'Authored failure')
    assert resolved(catch(reject(KeyError), ValueError, broken_handler,
                          (TypeError, LookupError), describe, Exception, broken_handler)) == (
        'KeyError', "Authored failure")
    assert resolved(catch(reject(), Exception, describe, ControlFailure, broken_handler)) == (
        'ControlFailure', 'Authored failure')
    with pytest.raises(ControlFailure):
        resolved(catch(reject(), KeyError, handler))
    with pytest.raises(HandlerFailure):
        resolved(catch(reject(), ValueError, broken_handler))
    # A handler's failure is not recovered by a later pair.
    with pytest.raises(HandlerFailure):
        resolved(catch(reject(), ValueError, broken_handler, RuntimeError, describe))
    assert Path(path).read_text().splitlines() == ['handled', 'handled']


def test_f10_t03(tmp_path):
    path = str(tmp_path / 'group')
    handler = group_handler.partial(path=path)
    assert resolved(catch_all({'ok': [identity(17), 5]}, Exception, handler)) == {'ok': [17, 5]}
    assert resolved(catch_all([identity(2), (identity(3),)])) == [2, (3,)]
    assert not Path(path).exists()
    values = {'ok': (finish(path + '.settled'),), 'bad': [reject(), reject(KeyError)]}
    assert resolved(catch_all(values, (ValueError, KeyError), handler)) == {'recovered': 47}
    assert Path(path).read_text().splitlines() == ['handled']
    # One unmatched failure decides, wherever it sits among the matching ones.
    for members in ([reject(), reject(KeyError)], [reject(KeyError), reject()]):
        with pytest.raises(KeyError):
            resolved(catch_all(members, ValueError, handler))
    with pytest.raises(ControlFailure):
        resolved(catch_all([reject()]))
    with pytest.raises(ControlFailure):
        resolved(catch_all([reject()], ValueError))
    with pytest.raises(HandlerFailure):
        resolved(catch_all([reject()], ValueError, broken_handler))
    assert Path(path).read_text().splitlines() == ['handled']
    # Settling is observed inside the workflow: a run drains running work, so
    # a file check after run() cannot tell a waiting group from a failing-fast one.
    unhandled = str(tmp_path / 'unhandled')
    assert resolved(catch(catch_all([reject(), finish(unhandled, .5)]), ValueError,
                          observe_settled.partial(required=unhandled))) == (
        'ControlFailure', 'settled')
    unmatched = str(tmp_path / 'unmatched')
    assert resolved(catch(catch_all([reject(KeyError), finish(unmatched, .5)], ValueError, handler),
                          KeyError, observe_settled.partial(required=unmatched))) == (
        'KeyError', 'settled')


def test_f10_t04(tmp_path):
    path = str(tmp_path / 'ordered')
    @task(namespace='f10.sequence', cache=False)
    def step(index):
        file = Path(path)
        prior = file.read_text().splitlines() if file.exists() else []
        assert prior == [str(i) for i in range(index)]
        time.sleep(.1)
        with file.open('a') as stream:
            stream.write(str(index) + '\n')
        return index * 7
    assert resolved(seq([step(0), step(1), step(2)])) == [0, 7, 14]
    assert Path(path).read_text().splitlines() == ['0', '1', '2']
    assert resolved(seq([])) == []


def test_f10_t05():
    assert resolved(invoke(identity(arithmetic), 4, c=8)) == 428
    partial = arithmetic.partial(4, c=1).partial(5, c=6)
    assert resolved(invoke(identity(partial), c=9)) == 459
    assert resolved(invoke(identity(partial))) == 456
    # Positional arguments supplied at the call follow the partial bindings.
    assert resolved(arithmetic.partial(7)(6)) == 763
    assert resolved(invoke(identity(arithmetic.partial(7, c=1)), 6)) == 761
    with pytest.raises(TypeError):
        resolved(partial(8))
    with pytest.raises(TypeError):
        resolved(arithmetic.partial(1)(a=2))
    with pytest.raises(TypeError):
        resolved(arithmetic.partial(b=1)())
    with pytest.raises(TypeError):
        resolved(arithmetic.partial(1)(unknown=2))


def test_f10_t06():
    assert resolved(map_(double, identity([5, -2, 9]))) == [10, -4, 18]
    assert resolved(map_(double, identity([]))) == []
    assert resolved(map_(double, [3, 1])) == [6, 2]
    # Input order holds even when earlier items finish last.
    assert resolved(map_(pause, identity([.4, 0, .2]))) == [.4, 0, .2]
    # Mapping over a mapped collection applies the inner task first.
    assert resolved(map_(double, map_(increment, identity([1, 4])))) == [20, 26]
    assert resolved(starmap(arithmetic, identity([{'a': 2, 'c': 7}, {'b': 8, 'a': 4}]))) == [227, 483]
    assert resolved(starmap(arithmetic, identity([]))) == []
    assert resolved(starmap(arithmetic, [{'c': 1, 'a': 3}])) == [321]


def test_f10_t07():
    assert resolved(flatten(identity([[8, 3], [], [5], [1, 9]]))) == [8, 3, 5, 1, 9]
    assert resolved(flat_map(pieces, identity([4, 0, -2]))) == [4, -4, -2, 2]
    assert resolved(compose(double, increment)(5)) == 28
    assert resolved(compose(increment, double)(5)) == 19
    assert resolved(compose(double, increment, double)(5)) == 38
    assert resolved(compose(increment)(5)) == 14
    # Every input reaches the last task; only its result moves on.
    assert resolved(compose(double, arithmetic)(1, c=4)) == 248


def test_f10_t08(tmp_path):
    path = str(tmp_path / 'delayed')
    delayed = resolved(identity(delay(effect(37, path, 'forced'))))
    assert not Path(path).exists()
    assert resolved(evaluate_later(delayed, path)) == 37
    assert Path(path).read_text().splitlines() == ['forced']
    prerequisite = str(tmp_path / 'prerequisite')
    assert resolved(const(identity(43), finish(prerequisite))) == 43
    assert Path(prerequisite).read_text() == 'done'
    # Observed downstream of the barrier: a run drains running work, so a
    # file check after run() cannot show the result waited for the prerequisite.
    barrier = str(tmp_path / 'barrier')
    trace = str(tmp_path / 'after-barrier')
    assert resolved(effect(const(identity(43), finish(barrier, .5)), trace, 'after',
                           required=barrier)) == 43
    assert Path(trace).read_text().splitlines() == ['after']
    with pytest.raises(ControlFailure):
        resolved(const(identity(43), reject()))
    unused = str(tmp_path / 'unused')
    with pytest.raises(ControlFailure):
        resolved(evaluate_later(delay(reject()), unused))


def test_f10_t09():
    assert resolved(zip_(identity([8, 4, 9]), identity(['a', 'b']), identity([True, False, True, False]))) == [(8, 'a', True), (4, 'b', False)]
    assert resolved(zip_(identity([1]), identity([]))) == []
    assert resolved(zip_(identity([]), identity([1]))) == []
    assert resolved(zip_([1, 2, 3], identity(['a', 'b', 'c']), [True])) == [(1, 'a', True)]
    assert resolved(zip_([6], identity(['a', 'b']))) == [(6, 'a')]


def test_f10_t10():
    assert resolved(apply_func(plain, identity(13), identity(4), scale=identity(3))) == 27
    # Not symmetric in its names, so each value must reach its own name.
    assert resolved(eval_('left * 10 + right - offset', identity(7), identity(6),
                          pos_args=['left', 'right'], offset=identity(5))) == 71
    assert resolved(eval_('a + b', a=identity(4), b=identity(9))) == 13
    with pytest.raises(ControlFailure):
        resolved(apply_func(plain_failure, identity(8)))
    for names in ([], ['a', 'b']):
        with pytest.raises(TypeError):
            resolved(eval_('a', identity(4), pos_args=names))
    with pytest.raises(TypeError):
        resolved(eval_('3', pos_args=['a']))


def test_f10_t11(tmp_path):
    @additive_wrapper(5)
    @multiplicative_wrapper(1)
    @task(namespace='f10.wrappers')
    def base(value, other=2):
        return value * other
    assert resolved(base(3)) == 24
    assert resolved(base(value=4, other=3)) == 42
    with pytest.raises(TypeError):
        resolved(base())
    with pytest.raises(TypeError):
        resolved(base(1, unknown=2))
    @extra_argument
    @task(namespace='f10.wrappers')
    def expanded(value):
        return value * 2
    assert resolved(expanded(4, 7)) == 15
    assert resolved(expanded(value=3, offset=8)) == 14
    with pytest.raises(TypeError):
        resolved(expanded(3))


    workflow = write_text(tmp_path / 'wrapped_workflow.py', """from velnora import catch, cond, task
from F10_helpers import additive_wrapper, extra_argument

@additive_wrapper(3)
@task(namespace='f10.cli')
def inner(value: int, factor: int = 2):
    return value * factor

@extra_argument
@task(namespace='f10.cli')
def outer(value: int):
    return value * 2

@additive_wrapper(3)
@additive_wrapper(2)
@task(namespace='f10.cli')
def layered(value: int, factor: int = 2):
    return value * factor
""")
    prefix = ['velnora', '--config', str(tmp_path / 'repo')]
    initialized = execute_client(VelnoraClient(), prefix + ['init'], cwd=tmp_path)
    assert initialized.exception is None, initialized
    for name, arguments, expected in [
        ('f10.cli.inner', ['--value=4', '--factor=5'], 23),
        ('f10.cli.outer', ['--value=4', '--offset=7'], 15),
        ('f10.cli.layered', ['--value=4', '--factor=5'], 25),
    ]:
        result = execute_client(VelnoraClient(), prefix + ['run', str(workflow), name] + arguments, cwd=tmp_path)
        assert result.exception is None, result
        assert result.value == expected


def test_f10_t12(tmp_path):
    scheduler = repository_scheduler(tmp_path / 'repository')
    path = str(tmp_path / 'audit')
    def define(body, wrapper, offset):
        return wrapper(offset)(task(name='reused', namespace='f10.reuse')(body))
    wrapped = define(original_body, additive_wrapper, 1)
    assert run_value_workflow(scheduler, wrapped(4, path)) == 7
    assert run_value_workflow(scheduler, wrapped(4, path)) == 7
    assert Path(path).read_text().splitlines() == ['body']
    wrapped = define(changed_body, additive_wrapper, 1)
    assert run_value_workflow(scheduler, wrapped(4, path)) == 14
    wrapped = define(changed_body, multiplicative_wrapper, 1)
    assert run_value_workflow(scheduler, wrapped(4, path)) == 40
    wrapped = define(changed_body, multiplicative_wrapper, 6)
    assert run_value_workflow(scheduler, wrapped(4, path)) == 45
    assert Path(path).read_text().splitlines() == ['body'] * 4
    # An identical redefinition is not a change.
    wrapped = define(changed_body, multiplicative_wrapper, 6)
    assert run_value_workflow(scheduler, wrapped(4, path)) == 45
    assert Path(path).read_text().splitlines() == ['body'] * 4
    # A change beneath several wrappers still invalidates the outermost call.
    layers = str(tmp_path / 'layers')
    def layer(body):
        return additive_wrapper(1)(additive_wrapper(2)(
            task(name='layered', namespace='f10.reuse')(body)))
    assert run_value_workflow(scheduler, layer(original_body)(4, layers)) == 9
    assert run_value_workflow(scheduler, layer(original_body)(4, layers)) == 9
    assert Path(layers).read_text().splitlines() == ['body']
    assert run_value_workflow(scheduler, layer(changed_body)(4, layers)) == 16
    assert Path(layers).read_text().splitlines() == ['body'] * 2


def test_f10_t13(tmp_path):
    path = str(tmp_path / 'background')
    assert resolved(consumer(fork_thread(background(path)), path)) == [61, 61]
    assert Path(path + '.started').read_text() == 'started'
    assert Path(path + '.done').read_text() == 'done'
    failed = str(tmp_path / 'failed')
    with pytest.raises(ControlFailure):
        resolved(consumer(fork_thread(background(failed, True)), failed))
    assert Path(failed + '.release').read_text() == 'release'
