# feature: F07
"""Acceptance tests for provenance metadata, editing and selection."""
from _helpers import run_workflow
from F02_helpers import run_value_workflow
from F06_helpers import history_scheduler, prepare_repository
from F07_helpers import (METADATA_VALUES, canonical_tag, entity_carrier, historical_associations,
                         root_entities, selected_entities, tag_argument,
                         tag_command, tag_history, tagged_value)


def test_f07_t01(tmp_path):
    repo = tmp_path / "metadata"
    prepare_repository(repo)
    scheduler = history_scheduler(repo)
    result = run_workflow(scheduler, tagged_value.options(tags=[])(13),
        run_kwargs={"tags": [("f07.execution", "authored")]})
    assert result.exception is None, result
    assert result.value == {"answer": 39, "items": [13, None, True]}
    entities = root_entities(repo)
    assert selected_entities(repo, "f07.execution=authored") == {entity_carrier("Execution", entities["Execution"])}
    # Every JSON kind is independently retained under the same key on every entity.
    values = METADATA_VALUES
    for kind, identifier in entities.items():
        key = "f07.typed." + kind.lower()
        if kind != "Task":
            tag_command(repo, "add", identifier, *(tag_argument(key, value) for value in values))
        assert historical_associations(repo, identifier, key) == {canonical_tag(value) for value in values}
        assert {row["entity_type"] for row in tag_history(repo)
                if row["key"] == key} == {kind}
        # Null associations are checked in export; SQLite exact-null lookup is broken.
        for value in [item for item in values if item is not None]:
            assert selected_entities(repo, tag_argument(key, value)) == {entity_carrier(kind, identifier)}, (kind, value)


def test_f07_t02(tmp_path):
    repo = tmp_path / "effective"
    prepare_repository(repo)
    scheduler = history_scheduler(repo)
    # Declared task tags remain on the task; call options replace effective job tags.
    results = [run_value_workflow(scheduler, tagged_value(11)),
               run_value_workflow(scheduler, tagged_value.options(tags=[("f07.call", "selected")])(19))]
    assert results == [{"answer": 33, "items": [11, None, True]},
                       {"answer": 57, "items": [19, None, True]}]
    from F06_helpers import history_snapshot, records_of
    snapshot = history_snapshot(repo)
    jobs = records_of(snapshot, "Job")
    calls = {row["call_hash"]: row for row in records_of(snapshot, "CallNode")}
    assert len(jobs) == 2
    task_ids = {calls[job["call_hash"]]["task_hash"] for job in jobs}
    expected_declared = {("Value", identifier) for identifier in task_ids}
    expected_call = set()
    for job in jobs:
        call = calls[job["call_hash"]]
        # Identify runs by independently authored inputs in their result values.
        from F06_helpers import decoded_record
        value_row = next(row for row in records_of(snapshot, "Value") if row["value_hash"] == call["value_hash"])
        number = decoded_record(value_row)["items"][0]
        assert number in (11, 19)
        if number == 11:
            expected_declared.add(("Job", job["id"]))
        else:
            expected_call.add(("Job", job["id"]))
        assert selected_entities(repo, tag_argument("f07.runtime.job", number)) == {("Job", job["id"])}
        assert selected_entities(repo, tag_argument("f07.runtime.value", [number, "result"])) == {("Value", call["value_hash"])}
        assert selected_entities(repo, tag_argument("f07.runtime.execution", {"input": number})) == {("Execution", job["execution_id"])}
    assert selected_entities(repo, "f07.declared=definition") == expected_declared
    assert selected_entities(repo, "f07.call=selected") == expected_call


def test_f07_t03(tmp_path):
    repo = tmp_path / "edits"
    prepare_repository(repo)
    assert run_value_workflow(history_scheduler(repo), tagged_value(7))["answer"] == 21
    entities = root_entities(repo)
    target, other = entities["Execution"], entities["Job"]
    carrier = {("Execution", target)}
    tag_command(repo, "add", target, "f07.edit=1", 'f07.edit="1"', "f07.keep=true")
    tag_command(repo, "add", other, "f07.edit=1")
    tag_command(repo, "add", target, "f07.edit=2")
    for value in (1, "1", 2):
        expected = carrier | ({("Job", other)} if value == 1 else set())
        assert selected_entities(repo, tag_argument("f07.edit", value)) == expected
    # Exact removal is typed: the number 1 is not the string "1".
    tag_command(repo, "rm", target, "f07.edit=1")
    for value in (1, "1", 2):
        expected = {("Job", other)} if value == 1 else carrier
        assert selected_entities(repo, tag_argument("f07.edit", value)) == expected
    tag_command(repo, "update", target, "f07.edit=3", "f07.edit=4")
    for value in (1, "1", 2, 3, 4):
        expected = carrier if value in (3, 4) else {("Job", other)} if value == 1 else set()
        assert selected_entities(repo, tag_argument("f07.edit", value)) == expected
    tag_command(repo, "rm", target, "f07.edit=3")
    assert selected_entities(repo, "f07.edit=3") == set()
    assert selected_entities(repo, "f07.edit=4") == carrier
    tag_command(repo, "rm", target, "--", "f07.edit")
    assert selected_entities(repo, "f07.edit") == {("Job", other)}
    assert selected_entities(repo, "f07.keep=true") == carrier
    assert historical_associations(repo, target, "f07.edit") >= {canonical_tag(value) for value in (1, "1", 2, 3, 4)}


def test_f07_t04(tmp_path):
    repo = tmp_path / "selection"
    prepare_repository(repo)
    assert run_value_workflow(history_scheduler(repo), tagged_value(23))["answer"] == 69
    entities = root_entities(repo)
    execution, job, value = entities["Execution"], entities["Job"], entities["Value"]
    tag_command(repo, "add", execution, "f07.group=8", "f07.region=north")
    tag_command(repo, "add", job, 'f07.group="8"', "f07.region=south")
    tag_command(repo, "add", value, "f07.group=8", "f07.region=south")
    assert selected_entities(repo, "f07.group") == {("Execution", execution), ("Job", job), ("Value", value)}
    assert selected_entities(repo, "f07.group=8") == {("Execution", execution), ("Value", value)}
    assert selected_entities(repo, 'f07.group="8"') == {("Job", job)}
    assert selected_entities(repo, "f07.group=8", "f07.region=south") == {("Value", value)}
    assert selected_entities(repo, "f07.group", "f07.region=north") == {("Execution", execution)}
    assert selected_entities(repo, "f07.group=8", "f07.region=west") == set()
    assert selected_entities(repo, "f07.missing") == set()
