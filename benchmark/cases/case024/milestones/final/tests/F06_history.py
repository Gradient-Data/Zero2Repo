# feature: F06
"""Acceptance coverage of durable execution history and saved values."""
import ast
import base64
import inspect

import pytest
from velnora.backends.db import VelnoraDatabaseError
from velnora.value import get_type_registry

from F01_helpers import AuthoredFailure
from F06_helpers import (BytePayload, decoded_record, fresh_history,
                         history_scheduler, prepare_repository, records_of,
                         increment, multiply, pipeline, postgres_repository, job_task_name)


def test_f06_t01(tmp_path):
    # No database service or URI is supplied: exercise the default repository.
    repo = tmp_path / "default"
    assert fresh_history(repo, "default", 7) == 64
    before = fresh_history(repo, "snapshot")
    assert fresh_history(repo, "default", 12) == 84
    after = fresh_history(repo, "snapshot")
    old = {row["id"] for row in records_of(before, "Execution")}
    new = {row["id"] for row in records_of(after, "Execution")}
    assert len(old) == 1
    assert len(new) == 2
    assert old < new
    values = [decoded_record(row) for row in records_of(after, "Value")]
    assert 64 in values and 84 in values

    with postgres_repository(tmp_path / "postgres") as repo:
        assert fresh_history(repo, "run", 7) == 64
        before = fresh_history(repo, "snapshot")
        assert fresh_history(repo, "run", 12) == 84
        after = fresh_history(repo, "snapshot")
        old = {row["id"] for row in records_of(before, "Execution")}
        new = {row["id"] for row in records_of(after, "Execution")}
        assert len(old) == 1
        assert len(new) == 2
        assert old < new
        values = [decoded_record(row) for row in records_of(after, "Value")]
        assert 64 in values and 84 in values


def test_f06_t02(tmp_path):
    repo = tmp_path / "provenance"
    prepare_repository(repo)
    assert fresh_history(repo, "run", 7) == 64
    assert fresh_history(repo, "run", 7) == 64
    assert fresh_history(repo, "version", "release-two") == 64
    snapshot = fresh_history(repo, "snapshot")
    executions = records_of(snapshot, "Execution")
    assert len(executions) == 3
    assert len({row["id"] for row in executions}) == 3
    jobs = {row["id"]: row for row in records_of(snapshot, "Job")}
    calls = {row["call_hash"]: row for row in records_of(snapshot, "CallNode")}
    values = {row["value_hash"]: row for row in records_of(snapshot, "Value")}
    for execution in executions:
        root = jobs[execution["job_id"]]
        assert root["execution_id"] == execution["id"]
        assert root["parent_id"] is None
        by_name = {calls[row["call_hash"]]["task_name"]: row
                   for row in jobs.values() if row["execution_id"] == execution["id"]}
        assert set(by_name) == {"f06.history.pipeline", "f06.history.increment", "f06.history.multiply"}
        parent = by_name["f06.history.pipeline"]
        children = [by_name["f06.history." + name] for name in ("increment", "multiply")]
        assert set(parent["children"]) == {row["id"] for row in children}
        assert all(row["parent_id"] == parent["id"] for row in children)
        parent_call = calls[parent["call_hash"]]
        first, second = [calls[row["call_hash"]] for row in children]
        assert set(parent_call["children"]) == {first["call_hash"], second["call_hash"]}
        assert first["call_hash"] in second["args"]["0"]["upstream"]
        for call, argument, output in [(parent_call, 7, 64), (first, 7, 16), (second, 16, 64)]:
            assert decoded_record(values[call["args"]["0"]["value_hash"]]) == argument
            assert decoded_record(values[call["value_hash"]]) == output
            task_record = values[call["task_hash"]]
            assert task_record["subtype"]["namespace"] == "f06.history"
            assert task_record["subtype"]["name"] == call["task_name"].rsplit(".", 1)[1]
            # Source is code, not a pinned pretty-printing choice.
            tree = ast.parse(task_record["subtype"]["source"])
            definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
            assert len(definitions) == 1
            authored = {task.name: task for task in (pipeline, increment, multiply)}
            expected = ast.parse(inspect.getsource(authored[task_record["subtype"]["name"]].func))
            for syntax in (tree, expected):
                syntax.body[0].decorator_list = []
            assert ast.dump(tree) == ast.dump(expected)
    versions = [decoded_record(row) for row in values.values()
                if row["subtype"] is not None and row["subtype"]["_type"] == "Task"
                and row["subtype"]["name"] == "multiply"]
    assert {value.version for value in versions} == {None, "release-two"}
    assert len({row["task_hash"] for row in calls.values()
                if row["task_name"] == "f06.history.multiply"}) == 2
    logged_ids = {row["id"] for row in records_of(snapshot, "Job", "log")}
    assert logged_ids == set(jobs)


def test_f06_t03(tmp_path):
    repo = tmp_path / "failures"
    prepare_repository(repo)
    assert fresh_history(repo, "run", 12) == 84
    assert fresh_history(repo, "fail", "authored failure cause") == "failed"
    snapshot = fresh_history(repo, "snapshot")
    jobs = records_of(snapshot, "Job", "log")
    values = {row["value_hash"]: row for row in records_of(snapshot, "Value")}
    by_name = {job_task_name(row, values): row for row in jobs}
    for name in ("pipeline", "increment", "multiply"):
        assert by_name["f06.history." + name]["status"] == "DONE"
    for name in ("failing_parent", "broken"):
        job = by_name["f06.history." + name]
        assert job["status"] == "FAILED"
        diagnostic = fresh_history(repo, "failure_diagnostic", job["id"])
        assert diagnostic["type"] == AuthoredFailure.__name__
        assert diagnostic["args"] == ["authored failure cause"]
        assert "broken" in diagnostic["frames"]
    parent = by_name["f06.history.failing_parent"]
    child = by_name["f06.history.broken"]
    assert child["parent_id"] == parent["id"]
    assert child["id"] in parent["children"]


def test_f06_t04(tmp_path):
    repo = tmp_path / "external"
    store = tmp_path / "values"
    prepare_repository(repo, value_store_path=store, value_store_min_size=0)
    assert fresh_history(repo, "run", 7) == 64
    snapshot = fresh_history(repo, "snapshot")
    values = records_of(snapshot, "Value")
    assert values
    # Empty data is the export carrier for external placement, for every value.
    assert all(base64.b64decode(row["data"], validate=True) == b"" for row in values)
    scheduler = history_scheduler(repo)
    recovered = {row["value_hash"]: scheduler.backend.get_value(row["value_hash"])
                 for row in values}
    assert all(present is True for value, present in recovered.values())
    key = next(key for key, (value, present) in recovered.items() if value == 64)
    assert fresh_history(repo, "recover", key) == 256
    # Read actual external data independently, without depending on shard paths.
    expected = get_type_registry().serialize(64)
    files = [path for path in store.rglob("*") if path.is_file()]
    assert files
    assert any(path.read_bytes() == expected for path in files)
    for path in files:
        path.unlink()
    assert fresh_history(repo, "missing", key) == "missing"
    # Missing external data must not be reused as a prior successful result.
    assert fresh_history(repo, "run", 7) == 64


def test_f06_t05(tmp_path):
    registry = get_type_registry()
    # Two lawful representations expose byte length vs character count or size in memory.
    for index, value in enumerate(("é" * 37, BytePayload(bytes(range(97))))):
        data = registry.serialize(value)
        length = len(data)
        for offset in (0, -1, 1):
            repo = tmp_path / ("limit-{}-{}".format(index, offset))
            prepare_repository(repo, max_value_size=length + offset)
            backend = history_scheduler(repo).backend
            if offset < 0:
                with pytest.raises(VelnoraDatabaseError):
                    backend.record_value(value)
            else:
                key = backend.record_value(value)
                restored, present = history_scheduler(repo).backend.get_value(key)
                assert present is True
                if isinstance(value, BytePayload):
                    assert isinstance(restored, BytePayload)
                    assert restored.data == value.data
                else:
                    assert restored == value


def test_f06_t06(tmp_path):
    repo = tmp_path / "default-limit"
    # External placement avoids the database driver's own large-blob limits.
    prepare_repository(repo, value_store_path=tmp_path / "large-values", value_store_min_size=0)
    assert fresh_history(repo, "default_limit", timeout=240) == "boundary enforced"


def test_f06_t07(tmp_path):
    repo = tmp_path / "identity"
    prepare_repository(repo)
    runs = [fresh_history(repo, "identity") for _ in range(2)]
    snapshot = fresh_history(repo, "snapshot")
    jobs = {row["id"]: row for row in records_of(snapshot, "Job", "log")}
    executions = {row["id"]: row for row in records_of(snapshot, "Execution")}
    seen = set()
    execution_ids = []
    for observations in runs:
        assert [row["label"] for row in observations] == ["left", "right"]
        assert [row["priority"] for row in observations] == [13, 29]
        assert observations[0]["execution"] == observations[1]["execution"]
        execution_ids.append(observations[0]["execution"])
        for row in observations:
            assert row["job"] not in seen
            seen.add(row["job"])
            job = jobs[row["job"]]
            assert job["execution_id"] == row["execution"]
            assert job["parent_id"] == executions[row["execution"]]["job_id"]
            assert job["status"] == "DONE"
    assert execution_ids[0] != execution_ids[1]
