# feature: F04
"""Acceptance checks for option precedence and scoped workflow context."""
import json

import pytest
from velnora import task
from velnora.context import get_context
from velnora.cli import VelnoraClient
from velnora.scheduler import SchedulerError

from _helpers import memory_scheduler, execute_client, run_workflow, write_json, write_text
from F01_helpers import identity, resolved
from F04_helpers import (context_branch, context_leaf, declared_place,
                         execution_place, execution_state, option_value)


def test_f04_t01(tmp_path):
    config = {"executors.default": {"type": "local", "mode": "process"}}
    scheduler = memory_scheduler(config)
    execution_state.clear()
    result = run_workflow(scheduler, execution_place(6))
    assert result.exception is None, result.exception
    assert result.value == 42
    assert execution_state == []
    result = run_workflow(scheduler, declared_place(6))
    assert result.exception is None, result.exception
    assert result.value == 42
    assert execution_state == [6]
    execution_state.clear()

    @task(namespace="f04.precedence")
    def parent():
        return [option_value(3), option_value.options(priority=23)(4)]

    assert resolved(option_value(3)) == (11, 33)
    assert resolved(parent.export_options(priority=17)()) == [(17, 51), (23, 92)]

    # Each arm begins with an independently populated cache and the same call.
    for use_cache in [True, False]:
        path = tmp_path / str(use_cache)
        path.write_text("first", encoding="utf-8")

        @task(namespace="f04.constraint", cache=True)
        def read_external(filename):
            with open(filename) as stream:
                return stream.read()

        @task(namespace="f04.constraint")
        def cached_parent(filename):
            return read_external.options(cache=True)(filename)

        sched = memory_scheduler()
        expr = cached_parent.export_options(cache=True)(str(path))
        first = run_workflow(sched, expr)
        assert first.exception is None, first.exception
        assert first.value == "first"
        path.write_text("second", encoding="utf-8")
        second = run_workflow(sched, expr, run_kwargs={"cache": use_cache})
        assert second.exception is None, second.exception
        assert second.value == ("first" if use_cache else "second")


def test_f04_t02():
    # Exported options must reach every descendant, not only direct children.
    @task(namespace="f04.scope")
    def inner(label):
        return option_value(label)

    @task(namespace="f04.scope")
    def middle(label):
        return inner(label)

    @task(namespace="f04.scope")
    def branches():
        return [middle.export_options(priority=identity(19))(2),
                middle(3), middle.options(priority=identity(29))(4),
                option_value.options(priority=identity(31))(5)]

    assert resolved(branches()) == [(19, 38), (11, 33), (11, 44), (31, 155)]


def test_f04_t03():
    @task(namespace="f04.lookup")
    def lookup():
        return [get_context("tool.deep.answer"), get_context("tool.zero", 9),
                get_context("missing", "absent"), get_context("tool.deep.missing", 13),
                get_context("tool.scalar.child", 17), get_context("tool.items.child", 21),
                get_context("missing"), get_context("tool.scalar.child"),
                get_context("tool.items.0", 25), get_context("tool.items.1")]

    @task(namespace="f04.lookup")
    def relay(depth):
        return relay(depth - 1) if depth else lookup()

    result = run_workflow(memory_scheduler(), relay(3), run_kwargs={"context": {
        "tool": {"deep": {"answer": 37}, "zero": 0, "scalar": 8, "items": [1, 2]}}})
    assert result.exception is None, result.exception
    # A sequence is a nonmapping value: positional-looking keys do not index it.
    assert result.value == [37, 0, "absent", 13, 17, 21, None, None, 25, None]


def test_f04_t04():
    # The override reaches the overriding task, its child and its grandchild.
    @task(namespace="f04.merge")
    def tree(value=get_context("tool")):
        return {"self": value, "child": context_branch()}

    @task(namespace="f04.merge")
    def branches():
        return [tree.update_context({"tool": {"deep": {"change": 23}}})(),
                tree(),
                tree.update_context(tool={"deep": {"change": 41}})
                .update_context(tool={"new": "added"})()]

    base = {"deep": {"change": 7, "keep": 11}, "other": [2, 5]}
    changed = {"deep": {"change": 23, "keep": 11}, "other": [2, 5]}
    twice = {"deep": {"change": 41, "keep": 11}, "other": [2, 5], "new": "added"}
    result = run_workflow(memory_scheduler(), branches(), run_kwargs={"context": {"tool": base}})
    assert result.exception is None, result.exception
    assert result.value == [{"self": x, "child": {"self": x, "child": x}}
                            for x in [changed, base, twice]]


def test_f04_t05(tmp_path):
    context = {"tool": {"deep": {"change": 5, "keep": 9}, "other": "retained"}}
    context_file = write_json(tmp_path / "configured.json", context)
    for source in [{"context": json.dumps(context)}, {"context_file": str(context_file)}]:
        scheduler = memory_scheduler({"scheduler": source})
        result = run_workflow(scheduler, context_leaf())
        assert result.exception is None, result.exception
        assert result.value == context["tool"]
        result = run_workflow(scheduler, context_leaf(), run_kwargs={
            "context": {"tool": {"deep": {"change": 27}}}})
        assert result.exception is None, result.exception
        assert result.value == {"deep": {"change": 27, "keep": 9}, "other": "retained"}
    with pytest.raises(SchedulerError):
        scheduler = memory_scheduler({"scheduler": {
            "context": json.dumps(context), "context_file": str(context_file)}})
        scheduler.run(context_leaf())


def test_f04_t06(tmp_path):
    configured = {"tool": {"deep": {"file": 1, "entry": 2, "scope": 3, "keep": 4},
                           "outside": "config"}}
    write_text(tmp_path / ".velnora" / "velnora.ini",
               "[scheduler]\ncontext = " + json.dumps(configured) + "\n")
    write_json(tmp_path / "run.json", {"tool": {
        "deep": {"file": 10, "entry": 20, "scope": 30}, "from_file": "file"}})
    workflow = write_text(tmp_path / "f04_cli_workflow.py", '''from velnora import task
from velnora.context import get_context

@task(namespace="f04.cli")
def leaf(value=get_context("tool")):
    return value

@task(namespace="f04.cli")
def main():
    return [leaf(), leaf.update_context(tool={"deep": {"scope": 300}})()]
''')
    result = execute_client(VelnoraClient(), ["velnora", "run", "--context-file", "run.json",
        "--context", "tool.deep.entry=entryvalue", "--context", "tool.deep.scope=scopevalue",
        "--context", "tool.from_entry=entry", str(workflow), "f04.cli.main"], cwd=tmp_path)
    assert result.exception is None, result.exception
    assert result.value == [
        {"deep": {"file": 10, "entry": "entryvalue", "scope": scope, "keep": 4},
         "outside": "config", "from_file": "file", "from_entry": "entry"}
        for scope in ["scopevalue", 300]]
