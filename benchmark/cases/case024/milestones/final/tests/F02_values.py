# feature: F02
"""Acceptance tests for extensible workflow values through public entries."""
import importlib
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from velnora import task
from velnora.cli import VelnoraClient
from velnora.value import InvalidValueError, get_type_registry

from _helpers import memory_scheduler, execute_client, write_text
from F01_helpers import Bundle, Pair, identity, resolved
from F02_helpers import (Amount, BoundaryAmount, RawAmount, Snapshot, affine, halve,
                         restored_in_fresh_process, restored_value, run_value_workflow)


def test_f02_t01(tmp_path):
    original = {
        "record": Bundle(Decimal("12.375"), Pair("café", b"\x00\xff")),
        "sequence": [None, True, -8, 2.5, (3, 6)],
        "members": {2, 11, 5},
        "instant": datetime(2024, 6, 2, 8, 30),
    }

    @task(namespace="f02.serializable")
    def use(value):
        return (value["record"].value * 8,
                value["record"].other.left.upper(),
                value["record"].other.right.hex(),
                sum(value["members"]) + sum(value["sequence"][-1]),
                value["instant"] + timedelta(hours=2))

    # Restoration in another interpreter shows the saved bytes carry the data.
    for restored in [restored_value(original),
                     restored_in_fresh_process(original, tmp_path / "fresh")]:
        assert restored == original
        assert type(restored["record"]) is Bundle and type(restored["record"].other) is Pair
        assert type(restored["members"]) is set
        assert resolved(identity(restored)) == original
        assert resolved(use(identity(restored))) == (
            Decimal("99"), "CAFÉ", "00ff", 27, datetime(2024, 6, 2, 10, 30))

    # A live generator is ordinary Python state that cannot be serialized.
    generator = (number for number in range(3))
    # Contract: serialization failures include TypeError and InvalidValueError.
    unsupported = (TypeError, InvalidValueError)
    try:
        with pytest.raises(unsupported):
            get_type_registry().serialize(generator)
        with pytest.raises(unsupported):
            resolved(identity(generator))

        @task(namespace="f02.serializable")
        def return_generator():
            return (number for number in range(3))

        with pytest.raises(unsupported):
            resolved(return_generator())
    finally:
        generator.close()


def test_f02_t02(tmp_path):
    registry = get_type_registry()
    # Each adaptation has its own task and scheduler, so both exercise real work.
    for index, kind in enumerate((Amount, RawAmount)):
        effects = []

        @task(name="consume", namespace="f02.equivalence" + str(index))
        def consume(value):
            assert type(value) is kind
            effects.append(value.number)
            return value.number * 6 + 1

        first, equivalent, different = kind("0007"), kind("7"), kind("12")
        copies = [restored_value(value) for value in (first, equivalent)]
        # The nonequivalent value is restored in another interpreter from saved bytes.
        copies.append(restored_in_fresh_process(different, tmp_path / str(index)))
        assert [type(value) for value in copies] == [kind, kind, kind]
        assert [value.number for value in copies] == [7, 7, 12]
        assert registry.get_hash(first) == registry.get_hash(equivalent)
        assert registry.get_hash(first) != registry.get_hash(different)
        assert [registry.get_hash(value) for value in copies] == [
            registry.get_hash(value) for value in (first, equivalent, different)]

        scheduler = memory_scheduler()
        assert run_value_workflow(scheduler, consume(first)) == 43
        assert effects == [7]
        assert run_value_workflow(scheduler, consume(copies[1])) == 43
        assert effects == [7]
        assert run_value_workflow(scheduler, consume(copies[2])) == 73
        assert effects == [7, 12]
        returned = run_value_workflow(scheduler, identity(different))
        assert type(returned) is kind
        assert returned.number == 12


def test_f02_t03(tmp_path):
    source = write_text(tmp_path / "state.txt", "first state")
    effects = []

    @task(namespace="f02.validity")
    def read_state(path):
        text = Path(path).read_text(encoding="utf-8")
        effects.append(text)
        return Snapshot(path, text)

    @task(namespace="f02.validity")
    def use_state(snapshot):
        return snapshot.text.upper()

    registry = get_type_registry()
    scheduler = memory_scheduler()
    first = run_value_workflow(scheduler, read_state(str(source)))
    restored = restored_value(first)
    assert restored.text == "first state"
    assert registry.is_valid(restored) is True
    assert run_value_workflow(scheduler, use_state(read_state(str(source)))) == "FIRST STATE"
    assert effects == ["first state"]

    source.write_text("replacement state", encoding="utf-8")
    assert registry.is_valid(restored) is False
    assert run_value_workflow(scheduler, use_state(read_state(str(source)))) == "REPLACEMENT STATE"
    assert effects == ["first state", "replacement state"]
    latest = restored_value(run_value_workflow(scheduler, read_state(str(source))))
    assert registry.is_valid(latest) is True
    source.unlink()
    assert registry.is_valid(latest) is False


def test_f02_t04(tmp_path):
    workflow = write_text(tmp_path / "f02_cli_workflow.py", '''from velnora import task
from F02_helpers import Interval

@task(namespace="f02.cli")
def calculate(window: Interval):
    assert type(window) is Interval
    return sum(range(window.start, window.stop))
''')
    prefix = ["velnora", "--config", str(tmp_path / "repo")]
    initialized = execute_client(VelnoraClient(), prefix + ["init"], cwd=tmp_path)
    assert initialized.exception is None, initialized
    for text, expected in [("2:6", 14), ("-3:2", -5)]:
        result = execute_client(VelnoraClient(), prefix + [
            "run", str(workflow), "f02.cli.calculate", "--window=" + text], cwd=tmp_path)
        assert result.exception is None, result
        assert result.value == expected
    for text in ("not-an-interval", "8:3"):
        result = execute_client(VelnoraClient(), prefix + [
            "run", str(workflow), "f02.cli.calculate", "--window=" + text], cwd=tmp_path)
        assert isinstance(result.exception, SystemExit), result
        assert result.exit_code == 2
        assert result.stderr.strip(), result


def test_f02_t05():
    @task(namespace="f02.boundaries")
    def double(value):
        return BoundaryAmount(str(value.number * 2))

    @task(namespace="f02.boundaries")
    def number(value):
        return value.number

    # Noncommuting input/body/output transformations expose skipped or swapped stages.
    for initial, output, downstream in [(4, 70, 73), (9, 120, 123)]:
        value = BoundaryAmount(str(initial))
        result = resolved(double(value))
        assert type(result) is BoundaryAmount
        assert result.number == output
        assert resolved(number(double(value))) == downstream

    @task(namespace="f02.boundaries")
    def double_all(values, extra=None):
        return {"doubled": [BoundaryAmount(str(item.number * 2)) for item in values],
                "extra": extra.number}

    # Custom values nested in list and named arguments and in a dict result also cross
    # the task boundary, so each stage applies to every embedded value.
    nested = resolved(double_all([BoundaryAmount("4"), BoundaryAmount("9")],
                                 extra=BoundaryAmount("1")))
    assert [type(item) for item in nested["doubled"]] == [BoundaryAmount, BoundaryAmount]
    assert [item.number for item in nested["doubled"]] == [70, 120]
    assert nested["extra"] == 4


def test_f02_t06(tmp_path, monkeypatch):
    @task(namespace="f02.functions")
    def invoke(function, argument):
        return function(argument)

    registry = get_type_registry()
    restored = restored_value(affine)
    assert registry.is_valid(restored) is True
    assert resolved([invoke(identity(restored), 5), invoke(affine, -2)]) == [13, -15]
    # Distinct functions remain distinct values: same argument, different results.
    assert resolved([invoke(affine, 6), invoke(halve, 6), invoke(identity(halve), 6)]) == [
        17, 3.0, 3.0]
    fresh = restored_in_fresh_process(halve, tmp_path / "fresh")
    assert registry.is_valid(fresh) is True
    assert resolved([invoke(identity(fresh), 10), invoke(affine, 10)]) == [5.0, 33]

    def local_function(value):
        return value + 1

    with pytest.raises(InvalidValueError):
        registry.serialize(local_function)
    with pytest.raises(InvalidValueError):
        resolved(invoke(local_function, 3))

    @task(namespace="f02.functions")
    def return_local():
        return local_function

    with pytest.raises(InvalidValueError):
        resolved(return_local())

    # Remove real author definitions, never rewrite the serialized product bytes.
    monkeypatch.syspath_prepend(str(tmp_path))
    for module_name, remove_module in [("f02_removed_name", False),
                                       ("f02_removed_module", True)]:
        path = write_text(tmp_path / (module_name + ".py"),
                          "def scale(value):\n    return value * 9\n")
        module = importlib.import_module(module_name)
        try:
            type_name = registry.get_type_name(type(module.scale))
            saved = registry.serialize(module.scale)
            live = registry.deserialize(type_name, saved)
            assert registry.is_valid(live) is True
            assert resolved(invoke(live, 4)) == 36
            if remove_module:
                path.unlink()
                del sys.modules[module_name]
                importlib.invalidate_caches()
            else:
                del module.scale
            missing = registry.deserialize(type_name, saved)
            assert registry.is_valid(missing) is False
        finally:
            sys.modules.pop(module_name, None)
