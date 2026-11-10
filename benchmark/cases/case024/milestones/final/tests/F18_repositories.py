# feature: F18
"""Acceptance tests for repository sharing and schema management."""
from velnora.cli import VelnoraClientError
from velnora.backends.db import VelnoraVersionError

from _helpers import capture_call
from F02_helpers import run_value_workflow
from F06_helpers import (history_scheduler, prepare_repository, pipeline,
                         history_snapshot, records_of, postgres_repository)
from F07_helpers import tag_command
from F18_helpers import (repository_command, repository_success, schema_info,
                         transfer_facts, assert_live_history)


def test_f18_t01(tmp_path):
    local, remote = tmp_path / "local", tmp_path / "remote"
    for repo, number in ((local, 2), (remote, 17)):
        prepare_repository(repo)
        assert run_value_workflow(history_scheduler(repo), pipeline(number)) == (number + 9) * 4
    repository_success(local, "repo", "add", "archive", remote)
    listing = repository_success(local, "repo", "list")
    entries = dict(line.strip().split(": ", 1) for line in listing.splitlines()
                   if line.startswith("  "))
    assert entries["archive"] == str(remote)
    remote_ids = {row["id"] for row in records_of(history_snapshot(remote), "Execution")}
    result, output = repository_command(local, "--repo", "archive", "log", "--exec", "--format", "json", "--no-pager")
    assert result.exception is None, result
    from _helpers import read_log_json
    assert {row["id"] for row in read_log_json(output)} == remote_ids
    assert remote_ids.isdisjoint({row["id"] for row in records_of(history_snapshot(local), "Execution")})
    for name in ("archive", "default"):
        result, _ = repository_command(local, "repo", "add", name, remote)
        assert isinstance(result.exception, VelnoraClientError), result
    result, _ = repository_command(local, "--repo", "unknown", "log")
    assert isinstance(result.exception, VelnoraClientError), result
    missing = tmp_path / "unconfigured"
    missing.mkdir()
    result, _ = repository_command(local, "repo", "add", "missing", missing)
    assert isinstance(result.exception, FileNotFoundError), result
    # Selecting a configured location whose configuration disappears must fail.
    repository_success(local, "repo", "add", "vanishing", remote)
    (remote / "velnora.ini").unlink()
    result, _ = repository_command(local, "--repo", "vanishing", "log")
    assert isinstance(result.exception, VelnoraClientError), result


def test_f18_t02(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    for repo in (source, target):
        prepare_repository(repo)
    assert run_value_workflow(history_scheduler(source), pipeline(8)) == 68
    root = records_of(history_snapshot(source), "Execution")[0]["id"]
    tag_command(source, "add", root, 'transfer.note={"reviewed":true,"round":2}')
    assert_live_history(source, [68])
    before = transfer_facts(source)
    assert any(key[0] == "Tag" and value["key"] == "transfer.note" for key, value in before.items())
    repository_success(target, "db", "upgrade", "latest")
    archive = tmp_path / "transfer.jsonl"
    repository_success(source, "export", "--file", archive)
    for _ in range(2):
        repository_success(target, "import", "--file", archive)
        assert_live_history(target, [68])
        assert transfer_facts(target) == before


def test_f18_t03(tmp_path):
    local, remote = tmp_path / "local", tmp_path / "remote"
    for repo in (local, remote):
        prepare_repository(repo)
    repository_success(local, "repo", "add", "peer", remote)
    assert run_value_workflow(history_scheduler(local), pipeline(3)) == 48
    repository_success(local, "push", "peer")
    common = transfer_facts(local)
    assert transfer_facts(remote) == common
    assert run_value_workflow(history_scheduler(local), pipeline(10)) == 76
    assert run_value_workflow(history_scheduler(remote), pipeline(22)) == 124
    left, right = transfer_facts(local), transfer_facts(remote)
    expected = {**left, **right}
    assert set(common) < set(left) and set(common) < set(right)
    for _ in range(2):
        repository_success(local, "push", "peer")
        assert_live_history(remote, [48, 76, 124])
        assert transfer_facts(remote) == expected
        repository_success(local, "pull", "peer")
        assert_live_history(local, [48, 76, 124])
        assert transfer_facts(local) == expected


def test_f18_t04(tmp_path):
    repo = tmp_path / "schema"
    prepare_repository(repo)
    assert run_value_workflow(history_scheduler(repo), pipeline(4)) == 52
    revisions = ["1.0", "2.0", "2.1", "2.2", "2.3", "3.0", "3.1", "3.2", "3.3", "3.4", "3.5"]
    output = repository_success(repo, "db", "versions")
    # Version is the first column of the published Version/Migration/Description table.
    assert {line.split()[0] for line in output.splitlines() if line.strip()} >= set(revisions)
    assert schema_info(repo) == ("3.5", "True")
    for revision in reversed(revisions[:-1]):
        repository_success(repo, "db", "downgrade", revision)
        assert schema_info(repo) == (revision, "False")
    for revision in revisions[1:]:
        repository_success(repo, "db", "upgrade", revision)
        assert schema_info(repo) == (revision, str(revision == "3.5"))
    # Reopen and execute: a cosmetic change to the info display is insufficient.
    assert run_value_workflow(history_scheduler(repo), pipeline(15)) == 96
    assert_live_history(repo, [52, 96])
    result, _ = repository_command(repo, "db", "upgrade", "8.7")
    assert isinstance(result.exception, VelnoraClientError), result
    assert schema_info(repo) == ("3.5", "True")


def _record_future_revision(repo, major):
    """Leave the repository as a newer client would: a schema revision this
    client has no migration for, recorded under the given major version."""
    import sqlite3
    import uuid
    database = sqlite3.connect(repo / "history.db")
    try:
        database.execute("UPDATE alembic_version SET version_num = ?",
                         ("f" + uuid.uuid4().hex[:11],))
        database.execute("INSERT INTO velnora_version (id, version, timestamp) "
                         "VALUES (?, ?, '2099-01-01 00:00:00')", (str(uuid.uuid4()), major))
        database.commit()
    finally:
        database.close()


def test_f18_t05(tmp_path):
    # Both current storage engines run the upgrade rules; repositories left by a
    # newer client exercise the compatibility ceiling.
    def check_migration(repo, option, upgrades_by_default):
        repository_success(repo, "db", "upgrade", "3.5")
        assert run_value_workflow(history_scheduler(repo), pipeline(6)) == 60
        repository_success(repo, "db", "downgrade", "3.4")
        assert schema_info(repo) == ("3.4", "False")
        result = capture_call(history_scheduler, (repo,))
        if option == "False" or (option is None and not upgrades_by_default):
            assert isinstance(result.exception, VelnoraVersionError), result
            assert schema_info(repo) == ("3.4", "False")
            repository_success(repo, "db", "upgrade", "latest")
            scheduler = history_scheduler(repo)
        else:
            assert result.exception is None, result
            scheduler = result.value
        assert schema_info(repo) == ("3.5", "True")
        assert run_value_workflow(scheduler, pipeline(14)) == 92
        assert_live_history(repo, [60, 92])

    for option in (None, "True", "False"):
        name = "default" if option is None else option
        repo = tmp_path / ("sqlite-" + name)
        prepare_repository(repo, **({} if option is None else {"automigrate": option}))
        check_migration(repo, option, upgrades_by_default=True)

        with postgres_repository(tmp_path / ("postgres-" + name)) as repo:
            if option is not None:
                configuration = repo / "velnora.ini"
                with configuration.open("a", encoding="utf-8") as stream:
                    stream.write("automigrate = " + option + "\n")
            check_migration(repo, option, upgrades_by_default=False)

    # A newer compatible revision (3.x beyond 3.5) is used as is, with automatic
    # upgrades enabled, and is never moved back to an older revision; a revision
    # above 3.99 is refused and left unchanged.
    for major, compatible in ((3, True), (4, False)):
        repo = tmp_path / ("future-%d" % major)
        prepare_repository(repo, automigrate="True")
        assert run_value_workflow(history_scheduler(repo), pipeline(6)) == 60
        assert schema_info(repo) == ("3.5", "True")
        _record_future_revision(repo, major)
        recorded = schema_info(repo)
        assert recorded[0] != "3.5" and recorded[0].startswith(str(major) + ".")
        result = capture_call(history_scheduler, (repo,))
        if compatible:
            assert result.exception is None, result
            assert run_value_workflow(result.value, pipeline(14)) == 92
            assert_live_history(repo, [60, 92])
        else:
            assert isinstance(result.exception, VelnoraVersionError), result
        assert schema_info(repo) == recorded
