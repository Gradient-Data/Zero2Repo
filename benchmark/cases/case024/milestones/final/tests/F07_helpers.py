# feature: F07
"""Public tag operations and semantic observations, reusable by later features."""
import io
import json

from velnora import apply_tags, task
from velnora.cli import VelnoraClient

from _helpers import execute_client, read_log_json
from F06_helpers import history_snapshot, records_of


METADATA_VALUES = [17, 2.75, "17", True, False, None, [1, "x", False], {"nested": [3, None]}]


@task(namespace="f07.tags", tags=[("f07.declared", "definition")] +
      [("f07.typed.task", value) for value in METADATA_VALUES], cache=False)
def tagged_value(number):
    return apply_tags(
        {"answer": number * 3, "items": [number, None, True]},
        tags=[("f07.runtime.value", [number, "result"])],
        job_tags=[("f07.runtime.job", number)],
        execution_tags=[("f07.runtime.execution", {"input": number})])


def tag_command(directory, operation, entity, *associations):
    """Run a complete public tag command; an unclassified failure is fatal."""
    result = execute_client(VelnoraClient(), ["velnora", "--config", str(directory),
                            "tag", operation, entity, *associations])
    assert result.exception is None, result
    return result


def tag_argument(key, value):
    return key + "=" + json.dumps(value, allow_nan=False)


def selected_entities(directory, *restrictions):
    """Return typed identifiers from the documented log JSONL carrier."""
    output = io.StringIO()
    argv = ["velnora", "--config", str(directory), "log", "--all",
            "--format", "json", "--no-pager"]
    for restriction in restrictions:
        argv.extend(["--tag", restriction])
    result = execute_client(VelnoraClient(stdout=output), argv)
    assert result.exception is None, result
    fields = {"Execution": "id", "Job": "id", "Value": "value_hash"}
    answer = set()
    for row in read_log_json(output.getvalue()):
        # Tasks are carried as Value records in public serialization.
        answer.add((row["_type"], row[fields[row["_type"]]]))
    return answer


def tag_history(directory):
    """Read historical associations without prescribing edit graph structure."""
    return records_of(history_snapshot(directory), "Tag")


def canonical_tag(value):
    """Preserve JSON types, including booleans versus numbers, for comparisons."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def historical_associations(directory, entity, key):
    return {canonical_tag(row["value"]) for row in tag_history(directory)
            if row["entity_id"] == entity and row["key"] == key}


def root_entities(directory):
    snapshot = history_snapshot(directory)
    executions = records_of(snapshot, "Execution")
    assert len(executions) == 1
    execution = executions[0]
    job = next(row for row in records_of(snapshot, "Job") if row["id"] == execution["job_id"])
    call = next(row for row in records_of(snapshot, "CallNode") if row["call_hash"] == job["call_hash"])
    return {"Execution": execution["id"], "Job": job["id"],
            "Task": call["task_hash"], "Value": call["value_hash"]}


def entity_carrier(kind, identifier):
    return ("Value" if kind == "Task" else kind, identifier)
