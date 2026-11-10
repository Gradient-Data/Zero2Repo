# feature: F16
"""Acceptance checks of command-line workflow lifecycle through public entries."""
import configparser
import pickle
import re

from velnora.cli import VelnoraClientError
from _helpers import write_saved_args, write_text
from F06_helpers import history_snapshot, prepare_repository, records_of
from F16_helpers import (invalid_arguments, lifecycle_call, lifecycle_run,
                         lifecycle_value, lifecycle_process)
import F16_helpers


def test_f16_t01(tmp_path):
    repo = tmp_path / "repo"
    lifecycle_value(lifecycle_call(repo, "init"))
    config = configparser.ConfigParser()
    assert config.read(repo / "velnora.ini")
    assert config.has_section("backend")
    assert lifecycle_value(lifecycle_run(repo, "combine", "--first", "6")) == 649
    assert lifecycle_value(lifecycle_run(repo, "combine", "--first", "2", "--third", "1")) == 241
    missing = lifecycle_run(repo, "not_declared", "--first", "6")
    assert isinstance(missing.exception, VelnoraClientError), missing
    # Missing bindings are rejected by task signature binding, rather than argparse.
    missing_arg = lifecycle_run(repo, "combine")
    assert isinstance(missing_arg.exception, TypeError), missing_arg
    invalid_arguments(lifecycle_run(repo, "combine", "--first", "six"))


def test_f16_t02(tmp_path):
    repo = tmp_path / "repo"
    prepare_repository(repo)
    saved = write_saved_args(tmp_path / "arguments.bin", (7,),
                             {"second": 6, "third": 2}, serializer=pickle.dump)
    assert lifecycle_value(lifecycle_run(repo, "combine", "--input", saved)) == 762
    assert lifecycle_value(lifecycle_run(repo, "combine", "--input", saved,
                                        "--second", "8")) == 782
    # An explicit value equal to the declared default still overrides the saved one.
    assert lifecycle_value(lifecycle_run(repo, "combine", "--input", saved,
                                        "--second", "4")) == 742
    # Every loaded positional argument keeps its own position.
    positional = write_saved_args(tmp_path / "positional.bin", (3, 1), {"third": 5},
                                  serializer=pickle.dump)
    assert lifecycle_value(lifecycle_run(repo, "combine", "--input", positional)) == 315
    assert lifecycle_value(lifecycle_run(repo, "combine", "--input", positional,
                                        "--third", "8")) == 318


def test_f16_t03(tmp_path):
    repo = tmp_path / "repo"
    prepare_repository(repo)
    assert lifecycle_value(lifecycle_run(repo, "parent", "--first", "7",
                                        "--second", "6", "--third", "2")) == 83
    snapshot = history_snapshot(repo)
    execution = records_of(snapshot, "Execution")[0]
    jobs = records_of(snapshot, "Job")
    for job in jobs:
        expected = 83 if job["parent_id"] is None else 21
        assert lifecycle_value(lifecycle_call(repo, "run", "--rerun",
                                             F16_helpers.__file__, job["id"])) == expected
    assert lifecycle_value(lifecycle_call(repo, "run", "--rerun",
                                         F16_helpers.__file__, execution["id"])) == 83
    assert lifecycle_value(lifecycle_call(repo, "run", "--rerun", F16_helpers.__file__,
                                         execution["id"], "--second", "8")) == 103
    changed = write_text(tmp_path / "f16_changed.py", '''from velnora import task
@task(namespace="f16", version="changed")
def parent(first: int, second: int = 4, third: int = 9):
    return first * 5 + second * 10 + third
''')
    assert lifecycle_value(lifecycle_call(repo, "run", "--rerun", changed,
                                         execution["id"])) == 97
    missing = lifecycle_call(repo, "run", "--rerun", F16_helpers.__file__, "no-such-record")
    assert isinstance(missing.exception, VelnoraClientError), missing
    # Recorded positional arguments are restored in their recorded positions.
    positional_repo = tmp_path / "positional"
    prepare_repository(positional_repo)
    saved = write_saved_args(tmp_path / "positional.bin", (2, 5), {"third": 1},
                             serializer=pickle.dump)
    assert lifecycle_value(lifecycle_run(positional_repo, "combine", "--input", saved)) == 251
    recorded = records_of(history_snapshot(positional_repo), "Execution")[0]["id"]
    assert lifecycle_value(lifecycle_call(positional_repo, "run", "--rerun",
                                         F16_helpers.__file__, recorded)) == 251
    assert lifecycle_value(lifecycle_call(positional_repo, "run", "--rerun",
                                         F16_helpers.__file__, recorded, "--third", "6")) == 256
    external_repo = tmp_path / "external"
    store = tmp_path / "store"
    prepare_repository(external_repo, value_store_path=store, value_store_min_size=0)
    assert lifecycle_value(lifecycle_run(external_repo, "combine", "--first", "5")) == 549
    recorded = records_of(history_snapshot(external_repo), "Execution")[0]["id"]
    files = [p for p in store.rglob("*") if p.is_file()]
    assert files
    for path in files:
        path.unlink()
    failed = lifecycle_call(external_repo, "run", "--rerun", F16_helpers.__file__, recorded)
    assert isinstance(failed.exception, VelnoraClientError), failed


def test_f16_t04(tmp_path):
    repo = tmp_path / "repo"
    prepare_repository(repo)
    effect = tmp_path / "effects"
    assert lifecycle_value(lifecycle_run(repo, "dynamic", "--value", "3", "--effect", effect)) == 4
    assert effect.read_text() == "3\n"
    def preview(value):
        result = lifecycle_process(["velnora", "-c", repo, "run", "--dryrun", F16_helpers.__file__,
                              "f16.dynamic", "--value", str(value), "--effect", effect], cwd=tmp_path)
        # Scheduler diagnostics have fixed action/Job/task-call fields. Ignore ids and prose.
        actions = re.findall(r"^\[velnora\] (Cached|Dryrun)\s+Job [^:]+:\s+(f16\.[\w]+)\(",
                             result.stderr, re.MULTILINE)
        return result, actions
    cached, actions = preview(3)
    assert cached.returncode == 0, cached
    assert ("Cached", "f16.dynamic") in actions
    new, actions = preview(8)
    assert new.returncode == 1, new
    assert ("Dryrun", "f16.dynamic") in actions
    assert all(name != "f16.unseen" for action, name in actions)
    assert effect.read_text() == "3\n"
    assert lifecycle_value(lifecycle_run(repo, "dynamic", "--value", "8", "--effect", effect)) == 9
    assert effect.read_text() == "3\n8\n"


def test_f16_t05(tmp_path):
    env = {"HOME": str(tmp_path), "VELNORA_CONFIG": None}
    def command(*args):
        return lifecycle_process(["velnora", *map(str, args)], cwd=tmp_path, env=env)
    default = command("run", F16_helpers.__file__, "f16.combine", "--first", "2")
    assert default.returncode == 0, default
    assert (tmp_path / ".velnora" / "velnora.ini").is_file()
    for operation in (["run", F16_helpers.__file__, "f16.combine", "--first", "2"], ["log"]):
        missing = tmp_path / "missing"
        rejected = command("-c", missing, *operation)
        assert rejected.returncode == 1, rejected
        assert any(line.startswith("VelnoraClientError:") for line in rejected.stdout.splitlines()), rejected
        assert not (missing / "velnora.ini").exists()
    selected = tmp_path / "selected"
    initialized = command("-c", selected, "init")
    assert initialized.returncode == 0, initialized
    assert (selected / "velnora.ini").is_file()
    result = command("-c", selected, "run", F16_helpers.__file__, "f16.combine", "--first", "2")
    assert result.returncode == 0, result
    assert command("-c", selected, "log", "--no-pager").returncode == 0


def test_f16_t06(tmp_path):
    repo = tmp_path / "repo"
    prepare_repository(repo)
    data = write_text(tmp_path / "payload", "location content")
    directory = tmp_path / "directory"
    directory.mkdir()
    write_text(directory / "member", "entry")
    arguments = ["--raw", "007", "--text", "tail", "--integer", "12", "--real", "2.5",
                 "--file", str(data), "--directory", str(directory),
                 "--func", "F16_helpers.transform"]
    for flag, shade, when, expected in [
        ("true", "amber", "2024-02-29", (False, 3, "2024-02-29T00:00:00")),
        ("false", "Shade.violet", "2024-02-29T13:24:05+02:00",
         (True, 8, "2024-02-29T13:24:05+02:00"))]:
        result = lifecycle_value(lifecycle_run(repo, "scalars", *arguments,
                                 "--flag", flag, "--shade", shade, "--when", when))
        assert result == ("007tail", 19, 1.25, expected[0], expected[1],
                          "location content", ["member"], expected[2], 58)
    valid = arguments + ["--flag", "true", "--shade", "amber", "--when", "2024-02-29"]
    # Members are selected by member name, optionally qualified by the
    # enumeration's own name; a qualifier naming another enumeration is not a member.
    for option, bad in [("--integer", "no"), ("--real", "no"), ("--flag", "no"),
                        ("--shade", "unknown"), ("--shade", "Hue.amber"),
                        ("--when", "not-a-date"),
                        ("--func", "missing_f16_module.transform"),
                        ("--func", "F16_helpers.missing_function")]:
        invalid_arguments(lifecycle_run(repo, "scalars", *valid, option, bad))


def test_f16_t07(tmp_path):
    repo = tmp_path / "repo"
    prepare_repository(repo)
    args = ["--numbers", "2", "-4", "7", "--flags", "true", "false",
            "--shades", "amber", "Shade.violet", "--words", "one", "007"]
    assert lifecycle_value(lifecycle_run(repo, "sequences", *args)) == (
        [6, -12, 21], [False, True], [3, 8], ["ONE", "007"], None)
    assert lifecycle_value(lifecycle_run(repo, "sequences", *args, "--maybe", "0"))[-1] == 11
    saved = write_saved_args(tmp_path / "saved", (), {"scale": 5, "maybe": 8}, serializer=pickle.dump)
    assert lifecycle_value(lifecycle_run(repo, "sequences", *args, "--input", saved)) == (
        [10, -20, 35], [False, True], [3, 8], ["ONE", "007"], 19)
    assert lifecycle_value(lifecycle_run(repo, "sequences", *args, "--input", saved,
                                        "--scale", "2", "--maybe", "3")) == (
        [4, -8, 14], [False, True], [3, 8], ["ONE", "007"], 14)
    # A single supplied item is still a one-element list of the element type.
    assert lifecycle_value(lifecycle_run(repo, "sequences", "--numbers", "5", "--flags", "false",
                                        "--shades", "violet", "--words", "ab")) == (
        [15], [True], [8], ["AB"], None)
    for option, values in [("--numbers", ["2", "bad"]), ("--flags", ["true", "bad"]),
                           ("--shades", ["amber", "bad"]), ("--maybe", ["bad"])]:
        invalid_arguments(lifecycle_run(repo, "sequences", *args, option, *values))
