# feature: F13
"""Remote task execution through stand-in container and AWS Batch services.

The stand-ins speak the interfaces the product uses (the `docker` command line;
the AWS Batch, STS and CloudWatch Logs HTTP APIs; S3 for shared working
storage) and run submitted container commands as separate local processes.
Each assertion reads what the service was asked for, or evidence written by the
task body itself, never a signal the product reports about its own work.

AWS Batch workflows run in fresh client processes so that SDK clients cached
by earlier work in the test process cannot carry another endpoint.
"""
import os

import pytest
from velnora import Scheduler
from velnora.config import Config

from F03_services import object_store
from F13_helpers import (batch_config, batch_stand_in, docker_stand_in, evidence_records,
                         local_sum, remote_area, remote_failure, run_in_client, start_client,
                         stop_client, wait_until)


def _s3_environment():
    names = ("AWS_ENDPOINT_URL_S3", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
             "AWS_DEFAULT_REGION")
    return {name: os.environ[name] for name in names}


def test_f13_t01(tmp_path, monkeypatch):
    # FP-13.01 and FP-13.03 through Docker and AWS Batch: the work runs in the
    # selected environment with the supplied arguments, its result feeds local
    # work, and a remote exception fails the workflow.
    monkeypatch.chdir(tmp_path)
    with docker_stand_in(tmp_path) as runs:
        config = Config({"executors.box": {
            "type": "docker", "image": "acceptance/box:3", "scratch": str(tmp_path / "scratch"),
            "job_monitor_interval": "0.1", "code_package": "False", "include_aws_env": "False"}})
        for width, height in ((6, 7), (5, 11)):
            evidence = tmp_path / "docker-{}x{}".format(width, height)
            result = Scheduler(config=config).run(local_sum(
                [remote_area.options(executor="box")(width, height, str(evidence))["area"], 1]))
            assert result == width * height + 1
            records = evidence_records(evidence)
            assert len(records) == 1
            assert records[0]["args"] == [width, height]
            assert records[0]["marker"] == "1" and records[0]["pid"] != os.getpid()
        assert len(runs()) == 2
        with pytest.raises(ValueError):
            Scheduler(config=config).run(remote_failure.options(executor="box")("docker"))

    with object_store("s3") as store, batch_stand_in(tmp_path, _s3_environment()) as (service, _):
        config = batch_config("batch", "acceptance-queue", store.url("scratch"))
        evidence = tmp_path / "batch"
        outcome = run_in_client(tmp_path, config, (
            "local_sum([remote_area.options(executor='batch')(4, 9, {!r})['area'], 2])"
        ).format(str(evidence)))
        assert outcome == ("RESULT", 38)
        records = evidence_records(evidence)
        assert len(records) == 1 and records[0]["args"] == [4, 9]
        assert records[0]["marker"] == "1" and records[0]["pid"] != os.getpid()
        assert [s["request"]["jobQueue"] for s in service.submissions] == ["acceptance-queue"]
        assert run_in_client(tmp_path, config,
                             "remote_failure.options(executor='batch')('batch')") == (
            "ERROR", "ValueError")


def test_f13_t02(tmp_path, monkeypatch):
    # FP-13.02: the selected image and requested resources reach the service;
    # per-call options override the configured defaults.
    monkeypatch.chdir(tmp_path)
    with docker_stand_in(tmp_path) as runs:
        config = Config({"executors.box": {
            "type": "docker", "image": "acceptance/box:3", "scratch": str(tmp_path / "scratch"),
            "vcpus": "3", "memory": "5", "job_monitor_interval": "0.1",
            "code_package": "False", "include_aws_env": "False"}})
        scheduler = Scheduler(config=config)
        assert scheduler.run(remote_area.options(executor="box")(2, 3, str(tmp_path / "a")))[
            "area"] == 6
        assert scheduler.run(remote_area.options(executor="box", image="acceptance/other:9",
                                                 memory=2, vcpus=1)(
            2, 4, str(tmp_path / "b")))["area"] == 8
        first, second = runs()
        assert first["image"] == "acceptance/box:3"
        assert {"--memory=5g", "--cpus=3"} <= set(first["flags"])
        assert second["image"] == "acceptance/other:9"
        assert {"--memory=2g", "--cpus=1"} <= set(second["flags"])

    with object_store("s3") as store, batch_stand_in(tmp_path, _s3_environment()) as (service, _):
        config = batch_config("batch", "q-resources", store.url("scratch"), vcpus=2, memory=3)
        assert run_in_client(tmp_path, config, "remote_area.options(executor='batch')(3, 3, {!r})"
                             .format(str(tmp_path / "c"))) == ("RESULT", {"area": 9, "node": None})
        assert run_in_client(tmp_path, config, (
            "remote_area.options(executor='batch', vcpus=4, memory=6)(3, 5, {!r})"
        ).format(str(tmp_path / "d"))) == ("RESULT", {"area": 15, "node": None})

        def resources(submission):
            requirements = submission["request"]["containerOverrides"]["resourceRequirements"]
            return {item["type"]: item["value"] for item in requirements}

        first, second = service.submissions
        assert first["definition"]["containerProperties"]["image"] == "acceptance/worker:7"
        assert resources(first) == {"VCPU": "2", "MEMORY": "3072"}
        assert resources(second) == {"VCPU": "4", "MEMORY": "6144"}


def test_f13_t05(tmp_path):
    # FP-13.04: after the client is killed while its AWS Batch job is still
    # running, a fresh client for the same task and arguments reconnects to that
    # job instead of submitting again, when cross-execution reuse is enabled.
    with object_store("s3") as store, batch_stand_in(tmp_path, _s3_environment()) as (service, _):
        outcomes = {}
        for scope in ("BACKEND", "CSE"):
            config = batch_config("batch", "q-" + scope, store.url("scratch-" + scope))
            config["backend"] = {"db_uri": "sqlite:///" + str(tmp_path / (scope + ".db"))}
            gate, evidence = tmp_path / ("gate-" + scope), tmp_path / ("evidence-" + scope)
            arguments = [3, 4, str(evidence), str(gate)]
            before = len(service.submissions)
            first = start_client(tmp_path, config, arguments, scope=scope)
            try:
                assert wait_until(lambda: len(evidence_records(evidence)) == 1, 60), \
                    first.communicate(timeout=5)[0] if first.poll() is not None else "no run"
            finally:
                stop_client(first)
            described_before = len(service.descriptions)
            second = start_client(tmp_path, config, arguments, scope=scope)
            try:
                # Open the gate only after the replacement client actually reaches
                # the service, instead of assuming it starts within a fixed delay.
                if scope == "BACKEND":
                    original_id = service.submissions[before]["jobId"]
                    assert wait_until(lambda: any(original_id in ids for ids in
                        service.descriptions[described_before:]), 60), "No reconnection observed"
                else:
                    assert wait_until(lambda: len(evidence_records(evidence)) == 2, 60), (
                        "Replacement execution did not start")
                gate.write_text("open")
                output, _ = second.communicate(timeout=120)
            finally:
                stop_client(second)
            assert second.returncode == 0, output[-2000:]
            assert "RESULT 13" in output.splitlines()
            outcomes[scope] = (len(service.submissions) - before, len(evidence_records(evidence)))
        assert outcomes["BACKEND"] == (1, 1)
        # Control: limiting reuse to one execution makes the new client submit again.
        assert outcomes["CSE"] == (2, 2)


def test_f13_t06(tmp_path):
    # FP-13.05: multi-node work runs the task with the same arguments on every
    # requested node and returns the main node's Python result.
    with object_store("s3") as store, batch_stand_in(tmp_path, _s3_environment()) as (service, _):
        for nodes, (width, height) in ((3, (2, 9)), (2, (5, 5))):
            config = batch_config("multi", "q-multi", store.url("scratch-%d" % nodes),
                                  num_nodes=nodes)
            evidence = tmp_path / ("nodes-%d" % nodes)
            outcome = run_in_client(tmp_path, config, (
                "remote_area.options(executor='multi')({}, {}, {!r})"
            ).format(width, height, str(evidence)))
            assert outcome == ("RESULT", {"area": width * height, "node": "0"})
            records = evidence_records(evidence)
            assert sorted(record["node"] for record in records) == [str(i) for i in range(nodes)]
            assert all(record["args"] == [width, height] for record in records)
            assert len({record["pid"] for record in records}) == nodes


def test_f13_t07(tmp_path):
    # FP-13.05: combining multi-node work with array submission is refused, while
    # the same multi-node calls without array grouping succeed.
    with object_store("s3") as store, batch_stand_in(tmp_path, _s3_environment()) as (service, _):
        baseline = batch_config("multi", "q-baseline", store.url("scratch-a"),
                                num_nodes=2, min_array_size=10)
        calls = "[remote_area.options(executor='multi')(index, 3, {!r}) for index in (1, 2, 3)]"
        status, value = run_in_client(tmp_path, baseline, calls.format(str(tmp_path / "base")))
        assert status == "RESULT" and [item["area"] for item in value] == [3, 6, 9]
        assert len(evidence_records(tmp_path / "base")) == 6
        submitted = len(service.submissions)

        grouped = batch_config("multi", "q-array", store.url("scratch-b"),
                               num_nodes=2, min_array_size=2, job_stale_time=1)
        calls = "[remote_area.options(executor='multi')(index, 7, {!r}) for index in (1, 2, 3)]"
        status, value = run_in_client(tmp_path, grouped, calls.format(str(tmp_path / "array")))
        assert status == "ERROR"
        assert evidence_records(tmp_path / "array") == []
        assert all("arrayProperties" not in s["request"]
                   for s in service.submissions[submitted:])


def test_f13_t08(tmp_path, monkeypatch):
    """Code delivery supplies selected code and data to an empty worker location."""
    import importlib
    import sys
    from _helpers import run_python, write_text
    from F13_helpers import _python_path

    source, worker = tmp_path / "source", tmp_path / "worker"
    source.mkdir()
    worker.mkdir()
    write_text(source / "delivered_support.py", "def combine(x, y):\n    return x * 11 - y\n")
    write_text(source / "weights.dat", "7\n19\n")
    write_text(source / "unused.dat", "This file must not be delivered.")
    write_text(source / "delivered_workflow.py", '''from pathlib import Path
from velnora import task
from delivered_support import combine

@task(namespace="delivery", cache=False)
def compute(value):
    root = Path(__file__).resolve().parent
    if (root / "unused.dat").exists():
        raise ValueError("Excluded support file was delivered")
    weights = [int(line) for line in (root / "weights.dat").read_text().splitlines()]
    return combine(value, sum(weights))
''')
    absent = run_python(
        "import importlib.util; assert importlib.util.find_spec('delivered_workflow') is None",
        cwd=worker, env={"PYTHONPATH": _python_path()})
    assert absent.returncode == 0, absent
    monkeypatch.chdir(source)
    monkeypatch.syspath_prepend(str(source))
    module = importlib.import_module("delivered_workflow")
    try:
        with docker_stand_in(worker):
            config = Config({"executors.box": {
                "type": "docker", "image": "acceptance/worker:delivery",
                "scratch": str(tmp_path / "scratch"), "job_monitor_interval": "0.1",
                "include_aws_env": "False", "code_package": "True",
                "code_includes": "*.py *.dat", "code_excludes": "unused.dat"}})
            for value in (5, -3):
                assert Scheduler(config=config).run(module.compute.options(executor="box")(
                    value)) == value * 11 - 26
    finally:
        sys.modules.pop("delivered_workflow", None)
        sys.modules.pop("delivered_support", None)


def test_f13_t09(tmp_path, monkeypatch):
    """Only explicitly forwarded credential values reach a container."""
    import hashlib
    import json
    from F13_helpers import remote_environment

    from urllib.error import URLError
    from urllib.request import urlopen

    try:
        with urlopen("http://169.254.169.254/latest/meta-data/", timeout=1) as response:
            assert response.status != 200, "Environment requires a client outside EC2"
    except URLError:
        # An unavailable metadata endpoint is the non-EC2 execution condition.
        pass
    monkeypatch.chdir(tmp_path)
    values = {"AWS_ACCESS_KEY_ID": "caller-access", "AWS_SECRET_ACCESS_KEY": "caller-secret",
              "AWS_SESSION_TOKEN": "caller-session", "AWS_DEFAULT_REGION": "eu-west-1"}
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    with docker_stand_in(tmp_path):
        for forward in (False, True):
            config = Config({"executors.box": {
                "type": "docker", "image": "acceptance/worker:env",
                "scratch": str(tmp_path / str(forward)), "job_monitor_interval": "0.1",
                "code_package": "False", "include_aws_env": str(forward)}})
            expected = list(values.values()) if forward else [None] * len(values)
            assert Scheduler(config=config).run(remote_environment.options(executor="box")()) == (
                hashlib.sha256(json.dumps(expected).encode()).hexdigest())


def test_f13_t10(tmp_path):
    """Legal arrays return each call's computed result; smaller groups stay single."""
    with object_store("s3") as store, batch_stand_in(tmp_path, _s3_environment()) as (service, _):
        for count in (2, 3):
            config = batch_config("batch", "q-grouping", store.url("scratch-" + str(count)),
                                  min_array_size=3, job_stale_time=3)
            before = len(service.submissions)
            evidence = tmp_path / str(count)
            outcome = run_in_client(tmp_path, config, (
                "[remote_area.options(executor='batch')(index, 7, {!r}) "
                "for index in range({})]"
            ).format(str(evidence), count))
            assert outcome == ("RESULT", [{"area": index * 7, "node": None}
                                           for index in range(count)])
            requests = [row["request"] for row in service.submissions[before:]]
            if count < 3:
                assert len(requests) == count
                assert all("arrayProperties" not in request for request in requests)
            else:
                assert len(requests) == 1
                assert requests[0]["arrayProperties"]["size"] == count
            assert sorted(row["args"] for row in evidence_records(evidence)) == [
                [index, 7] for index in range(count)]


def test_f13_t11(tmp_path, monkeypatch):
    """Remote script and service failures retain identifiable failed history."""
    import io
    from velnora import script
    from velnora.cli import VelnoraClient
    from velnora.scripting import ScriptError
    from _helpers import execute_client
    from F06_helpers import history_snapshot, records_of

    monkeypatch.chdir(tmp_path)
    diagnostic = "authored remote script diagnostic"
    command = "printf '%s\\n' '" + diagnostic + "' >&2\nexit 17"
    with docker_stand_in(tmp_path):
        config = Config({"executors.box": {
            "type": "docker", "image": "acceptance/worker:script",
            "scratch": str(tmp_path / "scratch"), "job_monitor_interval": "0.1",
            "code_package": "False", "include_aws_env": "False"}})
        with pytest.raises(ScriptError) as caught:
            Scheduler(config=config).run(script(command, executor="box"))
        assert diagnostic in caught.value.message

    with object_store("s3") as store, batch_stand_in(tmp_path, _s3_environment()) as (service, _):
        config = batch_config("batch", "q-failures", store.url("scratch"))
        # A script writes its own diagnostic; it is not provider message wording.
        status, value = run_in_client(tmp_path, config,
            "script({!r}, executor='batch')".format(command), error_details=True)
        assert status == "ERROR" and value["type"] == "ScriptError"
        assert diagnostic in value["message"]
        # The service refuses execution before a user body can produce output.
        # Query public job history to identify the failed work; no wrapper wording is fixed.
        repo = tmp_path / "repo"
        repo.mkdir()
        config["backend"] = {"db_uri": "sqlite:///" + str(repo / "history.db")}
        (repo / "velnora.ini").write_text("[backend]\ndb_uri = " + config["backend"]["db_uri"] + "\n")
        assert run_in_client(tmp_path, config,
            "remote_area.options(executor='batch')(8, 7, {!r})".format(
                str(tmp_path / "service-baseline"))) == ("RESULT", {"area": 56, "node": None})
        submitted_before = len(service.submissions)
        service.fail_before_start = True
        evidence = tmp_path / "not-started"
        status, value = run_in_client(tmp_path, config,
            "remote_area.options(executor='batch')(8, 9, {!r})".format(str(evidence)))
        assert status == "ERROR"
        assert len(service.submissions) == submitted_before + 1
        assert evidence_records(evidence) == []
        snapshot = history_snapshot(repo)
        jobs = records_of(snapshot, "Job", "log")
        tasks = {row["value_hash"]: row["subtype"] for row in records_of(snapshot, "Value")
                 if row["subtype"] is not None and row["subtype"]["_type"] == "Task"}
        failed = [job for job in jobs if job["status"] == "FAILED"
                  and tasks[job["task_hash"]]["name"] == "remote_area"]
        assert len(failed) == 1
        output = io.StringIO()
        shown = execute_client(VelnoraClient(stdout=output), ["velnora", "--config", str(repo),
            "log", "--no-pager", "--job", failed[0]["id"]])
        assert shown.exception is None, shown
        assert "Traceback:" in output.getvalue()
