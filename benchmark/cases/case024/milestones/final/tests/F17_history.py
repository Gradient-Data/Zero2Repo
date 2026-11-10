# feature: F17
"""Acceptance tests for history selection, inspection and interactive exploration."""
import ast
import asyncio
import inspect
import json
import re
import sys

from velnora import File

from _helpers import run_workflow
from F01_helpers import AuthoredFailure
from F02_helpers import run_value_workflow
from F06_helpers import (decoded_record, failing_parent, fresh_history, history_scheduler,
                         history_snapshot, prepare_repository, records_of, job_task_name)
from F07_helpers import tag_command
from F17_helpers import (adjust_left, adjust_right, consume, file_flow, history_console,
                         history_log, inspection_process, pair, produce, record_key, running_history, screen_text)


def test_f17_t01(tmp_path):
    repo = tmp_path / "selectors"
    prepare_repository(repo)
    scheduler = history_scheduler(repo)
    for name, text in [("first", "cobalt"), ("second", "amber")]:
        assert run_value_workflow(scheduler, file_flow(str(tmp_path / name), text)) == text.upper() + "!"
    snapshot = history_snapshot(repo)
    # Task and File records are Value carriers, with their public subtype fields.
    selections = [
        ("--exec", records_of(snapshot, "Execution")),
        ("--job", records_of(snapshot, "Job")),
        ("--task", [r for r in records_of(snapshot, "Value") if r["subtype"] and r["subtype"]["_type"] == "Task"]),
        ("--value", [r for r in records_of(snapshot, "Value") if r["type"] == "builtins.str"]),
        ("--value", [r for r in records_of(snapshot, "Value") if r["subtype"] and r["subtype"]["_type"] == "File"]),
    ]
    universe = {record_key(r) for r in snapshot["log"]}
    for flag, rows in selections:
        assert rows
        if flag != "--value":
            assert {record_key(r) for r in history_log(repo, flag)} == {record_key(r) for r in rows}
        for row in rows:
            identifier = record_key(row)
            selectors = [identifier]
            for size in range(1, len(identifier)):
                prefix = identifier[:size]
                if sum(key.startswith(prefix) for key in universe) == 1:
                    selectors.append(prefix)
                    break
            for selector in selectors:
                selected = history_log(repo, flag, selector)
                assert len(selected) == 1
                assert record_key(selected[0]) == identifier
                assert selected[0]["_type"] == row["_type"]
    for flag in ("--exec", "--job", "--task", "--value"):
        # The public log command reports a missing selector as successful empty JSONL.
        assert history_log(repo, flag, "no-such-history-record") == []
    files = [r for r in records_of(snapshot, "Value") if r["subtype"] and r["subtype"]["_type"] == "File"]
    for row in files:
        assert {record_key(r) for r in history_log(repo, "--file-path", row["subtype"]["path"])} == {record_key(row)}


def test_f17_t02(tmp_path):
    repo = tmp_path / "filters"
    prepare_repository(repo)
    scheduler = history_scheduler(repo)
    assert run_value_workflow(scheduler, pair(8)) == [14, 40]
    first_jobs = history_log(repo, "--job")
    assert first_jobs and all(r["status"] == "DONE" for r in first_jobs)
    first_ids = {r["id"] for r in first_jobs}
    assert run_value_workflow(scheduler, pair(8)) == [14, 40]
    reused_jobs = [r for r in history_log(repo, "--job") if r["id"] not in first_ids]
    assert reused_jobs and all(r["status"] == "CACHED" for r in reused_jobs)
    completed_ids = first_ids | {r["id"] for r in reused_jobs}
    failure = run_workflow(scheduler, failing_parent("filter failure"))
    assert isinstance(failure.exception, AuthoredFailure), failure
    failed_jobs = [r for r in history_log(repo, "--job") if r["id"] not in completed_ids]
    assert failed_jobs and all(r["status"] == "FAILED" for r in failed_jobs)
    assert fresh_history(repo, "run", 7) == 64
    assert fresh_history(repo, "version", "filter-edition") == 64
    settled_ids = {r["id"] for r in history_log(repo, "--job")}
    with running_history(repo):
        jobs = history_log(repo, "--job")
        live_jobs = [r for r in jobs if r["id"] not in settled_ids]
        assert live_jobs and all(r["status"] == "RUNNING" for r in live_jobs)
        executions = history_log(repo, "--exec")
        job_index = {r["id"]: r for r in jobs}
        executions = [dict(r, status=("DONE" if job_index[r["job_id"]]["status"] == "CACHED"
                                    else job_index[r["job_id"]]["status"])) for r in executions]
        assert {r["status"] for r in jobs} == {"RUNNING", "FAILED", "DONE", "CACHED"}
        for flag, rows, statuses in [("--job-status", jobs, ("RUNNING", "FAILED", "DONE", "CACHED")),
                                      ("--exec-status", executions, ("RUNNING", "FAILED", "DONE"))]:
            for status in statuses:
                selected = history_log(repo, "--job" if flag == "--job-status" else "--exec", flag, status)
                assert selected
                assert {record_key(r) for r in selected} == {record_key(r) for r in rows if r["status"] == status}
            assert {record_key(r) for r in history_log(repo, "--job" if flag == "--job-status" else "--exec", flag, "FAILED,DONE")} == {
                record_key(r) for r in rows if r["status"] in ("FAILED", "DONE")}
    snapshot = history_snapshot(repo)
    values = {r["value_hash"]: r for r in records_of(snapshot, "Value")}
    jobs = history_log(repo, "--job")
    task_rows = history_log(repo, "--task")
    for flag, rows in [("--job", jobs), ("--task", task_rows)]:
        names = {record_key(r): (job_task_name(r, values) if flag == "--job"
                 else ".".join([r["subtype"]["namespace"], r["subtype"]["name"]])) for r in rows}
        for names_in, allowed in [(["adjust"], {"f17.alpha.adjust", "f17.beta.adjust"}),
                                  (["f17.alpha.adjust"], {"f17.alpha.adjust"}),
                                  (["f17.alpha.adjust", "f17.beta.adjust"], {"f17.alpha.adjust", "f17.beta.adjust"})]:
            args = [flag]
            for name in names_in:
                args += ["--task-name", name]
            assert {record_key(r) for r in history_log(repo, *args)} == {key for key, name in names.items() if name in allowed}
        for task_row in task_rows:
            key = record_key(task_row)
            expected = {record_key(r) for r in rows if
                        (r["task_hash"] if flag == "--job" else record_key(r)) == key}
            assert {record_key(r) for r in history_log(repo, flag, "--task-hash", key)} == expected
        alternatives = [r for r in task_rows if r["subtype"]["name"] == "adjust"]
        options = [flag]
        for row in alternatives:
            options += ["--task-hash", record_key(row)]
        assert {record_key(r) for r in history_log(repo, *options)} == {
            key for key, name in names.items() if name in {"f17.alpha.adjust", "f17.beta.adjust"}}
    # Cross-category intersections, including conjunctive tag restrictions.
    left = next(r for r in jobs if job_task_name(r, values) == "f17.alpha.adjust" and r["status"] == "DONE")
    right = next(r for r in jobs if job_task_name(r, values) == "f17.beta.adjust" and r["status"] == "DONE")
    for row in (left, right):
        tag_command(repo, "add", row["id"], "f17.group=shared")
    tag_command(repo, "add", left["id"], "f17.region=east")
    assert {r["id"] for r in history_log(repo, "--job", "--tag", "f17.group=shared")} == {left["id"], right["id"]}
    assert {r["id"] for r in history_log(repo, "--job", "--tag", "f17.group=shared", "--tag", "f17.region=east",
        "--task-name", "adjust", "--job-status", "DONE")} == {left["id"]}
    assert history_log(repo, "--job", "--tag", "f17.group=shared", "--job-status", "FAILED") == []
    for flag in ("--exec", "--value"):
        target = next(r for r in history_log(repo, flag) if flag == "--exec" or r["type"] == "builtins.int")
        restriction = "f17.selected." + flag[2:] + "=yes"
        tag_command(repo, "add", record_key(target), restriction)
        assert {record_key(r) for r in history_log(repo, flag, "--tag", restriction)} == {record_key(target)}
    for label, task in [("left", adjust_left), ("right", adjust_right)]:
        assert {record_key(r) for r in history_log(repo, "--task", "--tag", "f17.task.selection=" + label)} == {task.hash}
    assert history_log(repo, "--job", "--task-name", "f17.absent") == []


def test_f17_t03(tmp_path):
    repo = tmp_path / "inspection"
    prepare_repository(repo)
    scheduler = history_scheduler(repo)
    path = tmp_path / "artifact.txt"
    assert run_value_workflow(scheduler, file_flow(str(path), "jade")) == "JADE!"
    failed = run_workflow(scheduler, failing_parent("inspection cause"))
    assert isinstance(failed.exception, AuthoredFailure), failed
    snapshot = history_snapshot(repo)
    jobs = {r["id"]: r for r in history_log(repo, "--job")}
    calls = {r["call_hash"]: r for r in records_of(snapshot, "CallNode")}
    values = {r["value_hash"]: r for r in records_of(snapshot, "Value")}
    executions = {r["id"]: r for r in history_log(repo, "--exec")}
    by_name = {job_task_name(j, values): j for j in jobs.values()}
    expected = [(file_flow, [str(path), "jade"], "JADE!"),
                (produce, [str(path), "jade"], None), (consume, None, "JADE!")]
    for task, arguments, output in expected:
        job = by_name[task.fullname]
        assert history_log(repo, "--job", job["id"]) == [job]
        call = calls[job["call_hash"]]
        task_value = decoded_record(values[call["task_hash"]])
        assert task_value.version == task.version
        source = ast.parse(values[call["task_hash"]]["subtype"]["source"])
        authored = ast.parse(inspect.getsource(task.func))
        for tree in (source, authored):
            tree.body[0].decorator_list = []
        assert ast.dump(source) == ast.dump(authored)
        args = [decoded_record(values[call["args"][str(i)]["value_hash"]]) for i in range(len(call["args"]))]
        result = decoded_record(values[call["value_hash"]])
        if arguments is not None:
            assert args == arguments
        else:
            assert args[0].path == str(path)
        if output is not None:
            assert result == output
        else:
            assert result.path == str(path)
        if task == file_flow:
            assert job["parent_id"] is None
            assert executions[job["execution_id"]]["job_id"] == job["id"]
        else:
            parent = by_name[file_flow.fullname]
            assert job["parent_id"] == parent["id"]
            assert job["id"] in parent["children"]
            assert job["execution_id"] == parent["execution_id"]
    producer = calls[by_name[produce.fullname]["call_hash"]]
    consumer = calls[by_name[consume.fullname]["call_hash"]]
    file_key = producer["value_hash"]
    assert consumer["args"]["0"]["value_hash"] == file_key
    assert producer["call_hash"] in consumer["args"]["0"]["upstream"]
    assert decoded_record(values[file_key]).path == str(path)
    upstream = history_log(repo, "--value", consumer["value_hash"], json_output=False)
    assert "Upstream dataflow:" in upstream
    links = re.findall(r"^\s*(\S+) <-- <([^>]+)> ([^(]+)\(([^)]*)\)", upstream,
                       re.MULTILINE)
    assert any(consumer["call_hash"].startswith(prefix) and prefix
               and name in (consume.name, consume.fullname) and arguments == "file"
               for variable, prefix, name, arguments in links)
    for name in ("f06.history.broken", "f06.history.failing_parent"):
        job = by_name[name]
        assert job["status"] == "FAILED"
        diagnostic = fresh_history(repo, "failure_diagnostic", job["id"])
        assert diagnostic["type"] == AuthoredFailure.__name__
        assert diagnostic["args"] == ["inspection cause"]

    producing_view = history_log(repo, str(path), json_output=False)
    def related_jobs(text, label):
        prefixes = re.findall(re.escape(label) + r" (\S+)", text)
        selected = set()
        for prefix in prefixes:
            matches = {identifier for identifier in jobs if identifier.startswith(prefix)}
            assert len(matches) == 1, (prefix, matches)
            selected.update(matches)
        return selected

    assert by_name[produce.fullname]["id"] in related_jobs(producing_view, "Produced by Job")
    input_path = tmp_path / "external-input.txt"
    input_path.write_text("copper", encoding="utf-8")
    assert run_value_workflow(scheduler, consume(File(str(input_path)))) == "COPPER!"
    input_jobs = history_log(repo, "--job", "--task-name", consume.fullname)
    input_snapshot = history_snapshot(repo)
    input_calls = {r["call_hash"]: r for r in records_of(input_snapshot, "CallNode")}
    input_values = {r["value_hash"]: r for r in records_of(input_snapshot, "Value")}
    input_job = next(j for j in input_jobs if decoded_record(input_values[
        input_calls[j["call_hash"]]["args"]["0"]["value_hash"]]).path == str(input_path))
    consuming_view = history_log(repo, str(input_path), json_output=False)
    jobs.update({row["id"]: row for row in records_of(input_snapshot, "Job")})
    assert input_job["id"] in related_jobs(consuming_view, "Consumed by Job")


def test_f17_t04(tmp_path):
    repo = tmp_path / "console"
    prepare_repository(repo)
    assert run_value_workflow(history_scheduler(repo), pair(9)) == [15, 45]

    async def navigate():
        app = history_console(repo)
        async with app.run_test(size=(160, 70)) as pilot:
            await pilot.pause()
            assert " executions " in screen_text(app)
            await pilot.press("enter")
            await pilot.pause()
            baseline = screen_text(app)
            assert "f17.alpha.adjust" in baseline and "f17.beta.adjust" in baseline
            await pilot.press("/")
            await pilot.press(*list("--task f17.alpha.adjust --status DONE"), "enter")
            await pilot.pause()
            filtered = screen_text(app)
            assert "Jobs (" in filtered
            job_panel = filtered.split("Jobs (", 1)[1]
            assert "f17.alpha.adjust" in job_panel
            assert "f17.beta.adjust" not in job_panel
            await pilot.press("enter")
            await pilot.pause()
            job_text = screen_text(app)
            assert ast.literal_eval(next(line.partition("Result:")[2].strip() for line in job_text.splitlines()
                                         if line.startswith("Result:"))) == 15
            assert "f17.alpha.adjust" in job_text
            await app.run_action("screen.click_task")
            await pilot.pause()
            assert "Task" in screen_text(app) and "f17.alpha.adjust" in screen_text(app)
            await pilot.press("escape")
            assert "Result:" in screen_text(app)
            snapshot = history_snapshot(repo)
            call = next(r for r in records_of(snapshot, "CallNode") if r["task_name"] == "f17.alpha.adjust")
            await app.run_action("screen.click_value('{}')".format(call["value_hash"]))
            await pilot.pause()
            assert "Value" in screen_text(app) and "15" in [line.strip() for line in screen_text(app).splitlines()]
            await pilot.press("escape", "escape", "escape")
            await pilot.pause()
            assert " executions " in screen_text(app)
        # Start each status arm from the same unfiltered history. The original
        # UI can retain an empty rendered list when changing filters repeatedly.
        for status in ("DONE", "FAILED"):
            app = history_console(repo)
            async with app.run_test(size=(160, 70)) as pilot:
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                assert "f17.beta.adjust" in screen_text(app).split("Jobs (", 1)[1]
                await pilot.press("/")
                await pilot.press(*list("--task f17.beta.adjust --status " + status), "enter")
                await pilot.pause()
                panel = screen_text(app).split("Jobs (", 1)[1]
                assert "f17.alpha.adjust" not in panel
                if status == "DONE":
                    assert "f17.beta.adjust" in panel
                    await pilot.press("enter")
                    await pilot.pause()
                    second = screen_text(app)
                    assert "f17.beta.adjust" in second
                    assert ast.literal_eval(next(line.partition("Result:")[2].strip() for line in second.splitlines()
                                                 if line.startswith("Result:"))) == 45
                else:
                    assert "--status FAILED" in screen_text(app)
                    assert "f17.beta.adjust" not in panel
    asyncio.run(navigate())


def test_f17_t05(tmp_path):
    repo = tmp_path / "repl"
    prepare_repository(repo)
    scheduler = history_scheduler(repo)
    assert run_value_workflow(scheduler, pair(12)) == [18, 60]
    assert run_value_workflow(scheduler, pair(17)) == [23, 85]
    snapshot = history_snapshot(repo)
    calls = {r["call_hash"]: r for r in records_of(snapshot, "CallNode")}
    jobs = [r for r in records_of(snapshot, "Job") if calls[r["call_hash"]]["task_name"] == pair.fullname]
    observed = []
    for index, job in enumerate(jobs):
        target = tmp_path / ("evaluated-{}.json".format(index))
        # Feed complete Python commands on stdin; no prompt or readiness inference.
        expression = "[obj.call_node.arguments[0].value.value_parsed * 7, sum(obj.call_node.value.value_parsed)]"
        commands = "!import json\n!open({!r}, 'w').write(json.dumps({}))\ncontinue\n".format(str(target), expression)
        result = inspection_process([sys.executable, "-c", "from velnora.cli import main; main()", "--config", str(repo), "repl", job["id"]],
                             cwd=tmp_path, stdin=commands, timeout=30)
        assert result.returncode == 0, result
        observed.append(json.loads(target.read_text(encoding="utf-8")))
    assert sorted(observed) == [[84, 78], [119, 108]]
