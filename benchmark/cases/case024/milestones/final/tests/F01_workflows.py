# feature: F01
"""Acceptance checks for task declarations and dynamic workflows."""
import operator
from typing import Tuple

import pytest
from velnora import task
from velnora.namespace import get_current_namespace, namespace

from F01_helpers import AuthoredFailure, Bundle, Pair, fail, identity, resolved


def test_f01_t01():
    effects = []

    @task(name="calculate", namespace="f01.first")
    def first(value):
        effects.append("first")
        return value + 3

    @task(name="calculate", namespace="f01.second")
    def second(value):
        effects.append("second")
        return value * 4

    expression = [first(5), second(5)]
    assert effects == []
    assert resolved(expression) == [8, 20]
    assert set(effects) == {"first", "second"}


def test_f01_t02():
    @task(namespace="f01.dynamic")
    def descend(value, total=0):
        if value == 0:
            return identity(total)
        return descend(identity(value - 1), total=identity(total + value))

    assert resolved([descend(identity(5)), descend(identity(2), total=identity(7))]) == [15, 10]


def test_f01_t03():
    nested = {"items": [identity(3), (identity(8),)],
              "pair": Pair(identity(4), {identity(7), identity(2)}),
              "bundle": Bundle(identity(9), [identity("leaf")])}
    result = resolved(identity(nested))
    assert result == {"items": [3, (8,)], "pair": Pair(4, {7, 2}),
                      "bundle": Bundle(9, ["leaf"])}
    assert type(result["pair"]) is Pair
    assert type(result["bundle"]) is Bundle
    assert type(result["items"][1]) is tuple
    assert type(result["pair"].right) is set


def test_f01_t04():
    operations = [operator.add, operator.sub, operator.mul, operator.truediv,
                  operator.eq, operator.ne, operator.lt, operator.le, operator.gt, operator.ge]
    expressions, expected = [], []
    # Distinct and equal inputs distinguish strict from inclusive comparisons.
    for op in operations:
        for left, right in [(9, 4), (4, 9), (4, 4)]:
            expected.extend([op(left, right)] * 3)
            expressions.extend([op(identity(left), right), op(left, identity(right)),
                                op(identity(left), identity(right))])
    assert resolved(expressions) == expected
    assert resolved([identity(["oak", "elm"])[1], identity(Bundle(13, 2)).value]) == ["elm", 13]
    for build, error in [(lambda: identity(1) / 0, ZeroDivisionError),
                         (lambda: identity(1) + "text", TypeError),
                         (lambda: identity([])[0], IndexError),
                         (lambda: identity(Bundle(1, 2)).missing, AttributeError)]:
        with pytest.raises(error):
            resolved(build())


def test_f01_t05():
    @task(namespace="f01.outputs", nout=3)
    def explicit() -> Tuple[int, int]:
        return (2, 5, 9)

    @task(namespace="f01.outputs")
    def inferred() -> Tuple[int, str]:
        return (7, "branch")

    @task(namespace="f01.outputs", nout=0)
    def empty():
        return ()

    first, second, third = explicit()
    a, b = inferred()
    assert resolved([first, second, third, a, b]) == [2, 5, 9, 7, "branch"]
    assert resolved(list(explicit())) == [2, 5, 9]
    assert list(empty()) == []
    assert resolved(empty()) == ()


def test_f01_t06():
    def authored():
        return [1, 2]

    # Invalid counts are refused as declarations (Contract: TypeError or ValueError),
    # at the latest when the task is called, never only by a later iteration.
    for count in [-1, -4, 1.5, 0.5, "2"]:
        with pytest.raises((TypeError, ValueError)):
            declared = task(namespace="f01.invalid_outputs", nout=count)(authored)
            declared()
    for expression in [identity(True), identity(False)]:
        with pytest.raises(TypeError):
            bool(expression)
    with pytest.raises(TypeError):
        list(identity([1, 2]))

    @task(namespace="f01.outputs")
    def variable() -> Tuple[int, ...]:
        return (1, 2)

    with pytest.raises(TypeError):
        list(variable())
    assert resolved(variable()) == (1, 2)


def test_f01_t07():
    @task(namespace="f01.binding")
    def calculate(a, b=6, *, scale=2):
        return (a - b) * scale

    assert resolved([calculate(identity(10)), calculate(10, 3),
                     calculate(b=identity(2), a=9, scale=3)]) == [8, 14, 21]
    for args, kwargs in [((), {}), ((1,), {"a": 2}), ((1,), {"unknown": 3}),
                         ((1, 2, 3), {})]:
        with pytest.raises(TypeError):
            resolved(calculate(*args, **kwargs))


def test_f01_t08():
    effects = []

    @task(namespace="f01.failure")
    def dependent(value):
        effects.append(value)
        return value + 1

    assert resolved(dependent(dependent(identity(4)))) == 6
    assert effects == [4, 5]
    effects.clear()
    with pytest.raises(AuthoredFailure) as caught:
        resolved(dependent(dependent(fail("prerequisite"))))
    assert caught.value.args == ("prerequisite",)
    assert effects == []


def test_f01_t09():
    previous = get_current_namespace()
    try:
        namespace("f01.current")

        def authored(value):
            return value + 1

        current = task()(authored)
        globals()["velnora_namespace"] = "f01.module"
        module = task()(authored)
        explicit = task(namespace="f01.explicit")(authored)
        unqualified = task(namespace="")(authored)
        assert [item.name for item in [current, module, explicit, unqualified]] == ["authored"] * 4
        assert [item.namespace for item in [current, module, explicit, unqualified]] == [
            "f01.current", "f01.module", "f01.explicit", ""]
        assert resolved([current(1), module(2), explicit(3), unqualified(4)]) == [2, 3, 4, 5]
        del globals()["velnora_namespace"]
        namespace(None)
        bare = task()(authored)
        assert bare.namespace == ""
        assert resolved(bare(8)) == 9
    finally:
        globals().pop("velnora_namespace", None)
        namespace(previous)


def test_f01_t10():
    def authored(value):
        return value * 3

    # Namespaces permit dots anywhere after the first character.
    for name, ns in [("aZ_09", "scope.A_09"), ("_", "_"), ("Simple", ""),
                     ("trail", "scope."), ("double", "a..b"), ("digit", "_.9")]:
        declared = task(name=name, namespace=ns)(authored)
        assert declared.name == name
        assert declared.namespace == ns
        assert resolved(declared(7)) == 21
    # An explicitly empty name uses the authored function name.
    empty = task(name="", namespace="f01.empty")(authored)
    assert empty.name == "authored"
    assert resolved(empty(7)) == 21
    # Names containing line terminators are outside the validation guarantee.
    # Contract: declaration failures are raised as TypeError or ValueError.
    for name in ["9bad", "bad-name", "a.b", "bad name", "éclair"]:
        with pytest.raises((TypeError, ValueError)):
            task(name=name, namespace="f01.valid")(authored)
    for ns in ["9bad", ".bad", "bad-name", "bad name", "éclair"]:
        with pytest.raises((TypeError, ValueError)):
            task(name="valid", namespace=ns)(authored)
    # The namespace rule also governs namespaces taken from the module or author selection.
    previous = get_current_namespace()
    try:
        namespace("f01.current_ok")
        assert task()(authored).namespace == "f01.current_ok"
        with pytest.raises((TypeError, ValueError)):
            namespace("bad-current")
            task()(authored)
        namespace(None)
        globals()["velnora_namespace"] = "f01.module_ok"
        assert task()(authored).namespace == "f01.module_ok"
        with pytest.raises((TypeError, ValueError)):
            globals()["velnora_namespace"] = "9module"
            task()(authored)
    finally:
        globals().pop("velnora_namespace", None)
        namespace(previous)


def test_f01_t11():
    values = [11, 23, 37, 41, 59, 61]
    expression = identity(values)
    assert resolved([expression[:3], expression[1:6:2], expression[2:5],
                     expression[0:6], expression[3:3], expression[:0],
                     expression[6:6]]) == [
        [11, 23, 37], [23, 41, 61], [37, 41, 59], values, [], [], []]


def test_f01_t12():
    expressions, expected = [], []
    for left in [False, True]:
        for right in [False, True]:
            # Either operand may be deferred, so plain booleans appear on both sides.
            expressions.extend([identity(left) & identity(right), identity(left) | identity(right),
                                left & identity(right), identity(left) & right,
                                left | identity(right), identity(left) | right])
            expected.extend([left and right, left or right, left and right, left and right,
                             left or right, left or right])
    assert resolved(expressions) == expected
    for build in [lambda: identity(False) & fail("boolean"),
                  lambda: fail("boolean") & identity(False),
                  lambda: identity(True) | fail("boolean"),
                  lambda: fail("boolean") | identity(True),
                  lambda: False & fail("boolean"),
                  lambda: True | fail("boolean")]:
        with pytest.raises(AuthoredFailure) as caught:
            resolved(build())
        assert caught.value.args == ("boolean",)
