# feature: F18
"""Public repository commands and semantic transfer observations."""
import io

from velnora.cli import VelnoraClient
from _helpers import execute_client, index_records
from F06_helpers import decoded_record, history_snapshot, records_of


def repository_command(directory, *arguments):
    output = io.StringIO()
    result = execute_client(VelnoraClient(stdout=output),
        ["velnora", "--config", str(directory), *map(str, arguments)])
    return result, output.getvalue()


def repository_success(directory, *arguments):
    result, output = repository_command(directory, *arguments)
    assert result.exception is None, result
    return output


def schema_info(directory):
    output = repository_success(directory, "db", "info")
    fields = dict(line.split(": ", 1) for line in output.splitlines() if ": " in line)
    return fields["db version"].split(" ", 1)[0], fields["CLI compatible with db"]


def transfer_facts(directory):
    """Compare data and edges, without ordering or encoding-byte assumptions."""
    rows = history_snapshot(directory)["export"]
    keys = {"Execution": "id", "Job": "id", "CallNode": "call_hash",
            "Value": "value_hash", "Tag": "tag_hash"}
    indexed = index_records(rows, key=lambda row: (row["_type"], row[keys[row["_type"]]]))
    facts = {}
    for key, row in indexed.items():
        kind = row["_type"]
        if kind == "Execution":
            value = {"job_id": row["job_id"]}
        elif kind == "Job":
            value = {name: row[name] for name in
                ("task_hash", "call_hash", "parent_id", "execution_id")}
            value["children"] = set(row["children"])
        elif kind == "CallNode":
            value = {name: row[name] for name in ("task_name", "task_hash", "value_hash")}
            value["children"] = set(row["children"])
            value["args"] = {name: (arg["value_hash"], set(arg["upstream"]))
                             for name, arg in row["args"].items()}
        elif kind == "Value":
            subtype = row["subtype"]
            value = {"subvalues": set(row["subvalues"]), "subtype": None}
            if subtype is None:
                value["decoded"] = decoded_record(row)
            else:
                fields = {"Task": ("_type", "name", "namespace", "source"),
                          "File": ("_type", "path")}[subtype["_type"]]
                value["subtype"] = {field: subtype[field] for field in fields}
                if subtype["_type"] == "Task":
                    value["version"] = decoded_record(row).version
        else:
            value = {name: row[name] for name in ("entity_type", "entity_id", "key", "value")}
        facts[key] = value
    return facts


def assert_live_history(directory, expected):
    """Prove a nonempty author computation before comparing transferred facts."""
    snapshot = history_snapshot(directory)
    executions = records_of(snapshot, "Execution")
    jobs = {row["id"]: row for row in records_of(snapshot, "Job")}
    calls = {row["call_hash"]: row for row in records_of(snapshot, "CallNode")}
    values = {row["value_hash"]: row for row in records_of(snapshot, "Value")}
    results = [decoded_record(values[calls[jobs[e["job_id"]]["call_hash"]]["value_hash"]])
               for e in executions]
    assert sorted(results) == sorted(expected)
    assert any(row["children"] for row in jobs.values())
    assert any(row["subtype"] and row["subtype"]["_type"] == "Task" for row in values.values())
