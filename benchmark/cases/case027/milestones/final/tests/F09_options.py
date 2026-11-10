# feature: F09
"""Search server: option validation at startup."""

from __future__ import annotations

import pytest

from _helpers import BackgroundProcess, make_tree, run_trisift
from F01_helpers import assert_exit
from F09_helpers import INDEX_DIR_NAME, ServerProcess, wait_ready

# Each row is the serve options of one usage error (FP-09.12).
USAGE_ERRORS = [
    # no-watch with an explicit refresh option, at default values, in both orders
    ["--no-watch", "--watch-mode", "auto"],
    ["--watch-mode", "auto", "--no-watch"],
    ["--no-watch", "--watch-mode", "poll"],
    ["--no-watch", "--poll-interval", "120"],
    ["--poll-interval", "120", "--no-watch"],
    ["--no-watch", "--watch-budget", "8192"],
    ["--watch-budget", "8192", "--no-watch"],
    # poll mode with an explicit watch budget
    ["--watch-mode", "poll", "--watch-budget", "8192"],
    ["--watch-budget", "8192", "--watch-mode", "poll"],
    # watch mode other than auto or poll
    ["--watch-mode", "native"],
    ["--watch-mode", "disabled"],
    ["--watch-mode", "polling"],
    # poll interval out of range or not a whole number
    ["--poll-interval", "0"],
    ["--poll-interval", "86401"],
    ["--poll-interval", "1.5"],
    ["--poll-interval", "-1"],
    ["--poll-interval", "abc"],
    # watch budget out of range or not a whole number
    ["--watch-budget", "0"],
    ["--watch-budget", "4294967296"],
    ["--watch-budget", "2.5"],
    ["--watch-budget", "many"],
    # zero or non-numeric resource values
    ["--max-memory", "0"],
    ["--max-memory", "lots"],
    ["--auto-save-mutations", "0"],
    ["--auto-save-mutations", "x"],
    ["--watcher-queue-cap", "0"],
    ["--watcher-queue-cap", "big"],
]


@pytest.fixture
def small_root(tmp_path):
    root = tmp_path / "root"
    make_tree(root, {"a.txt": "alpha\n"})
    return root


# F09.T17
@pytest.mark.parametrize("opts", USAGE_ERRORS, ids=lambda o: " ".join(o))
def test_invalid_refresh_and_resource_options_are_usage_errors(small_root, opts):
    r = run_trisift(["serve", *opts, str(small_root)], cwd=small_root.parent, timeout=30)
    assert_exit(r, "error")
    assert r.stdout == b"", r.describe()
    assert r.err.strip(), r.describe()
    assert not (small_root / INDEX_DIR_NAME / "serve.json").exists()


# F09.T17
@pytest.mark.parametrize("opts, field, value", [
    (["--poll-interval", "1"], "poll_interval_secs", 1),
    (["--poll-interval", "86400"], "poll_interval_secs", 86400),
    (["--watch-mode", "poll", "--poll-interval", "86400"], "poll_interval_secs", 86400),
    (["--watch-budget", "1"], "watch_budget", 1),
    (["--watch-budget", "4294967295"], "watch_budget", 4294967295),
    (["--max-memory", "1", "--auto-save-mutations", "1", "--watcher-queue-cap", "1"], None, None),
], ids=lambda v: " ".join(v) if isinstance(v, list) else str(v))
def test_boundary_option_values_are_accepted(small_root, opts, field, value):
    with ServerProcess(small_root, opts) as srv:
        st = wait_ready(srv)
        if field is not None:
            assert st[field] == value, st
        assert st["num_files"] == 1


# Traversal options refused by `trisift index` (FP-06.08), each with its spelling.
REFUSED = [
    (["--follow"], "--follow"),
    (["--max-depth", "2"], "--max-depth"),
    (["--one-file-system"], "--one-file-system"),
    (["--ignore-file", "IGNFILE"], "--ignore-file"),
    (["--ignore-file-case-insensitive"], "--ignore-file-case-insensitive"),
    (["--no-ignore-dot"], "--no-ignore-dot"),
    (["--no-ignore-exclude"], "--no-ignore-exclude"),
    (["--no-ignore-files"], "--no-ignore-files"),
    (["--no-ignore-global"], "--no-ignore-global"),
    (["--no-ignore-parent"], "--no-ignore-parent"),
    (["--no-ignore-vcs"], "--no-ignore-vcs"),
]


# F09.T18
@pytest.mark.parametrize("opts, name", REFUSED, ids=[n for _, n in REFUSED])
def test_traversal_options_refused_by_index_are_refused_by_serve(tmp_path, opts, name):
    root = tmp_path / "root"
    make_tree(root, {"a.txt": "alpha\n"})
    ign = tmp_path / "rules.ignore"
    ign.write_text("nothing\n")
    opts = [str(ign) if o == "IGNFILE" else o for o in opts]
    r = run_trisift(["serve", *opts, str(root)], cwd=tmp_path, timeout=30)
    assert_exit(r, "error")
    assert name in r.err, f"refusal does not name {name}\n{r.describe()}"
    assert not (root / INDEX_DIR_NAME / "serve.json").exists()
    assert not (root / INDEX_DIR_NAME / "lookup.bin").exists()


# F09.T18
@pytest.mark.parametrize("where", ["root_itself", "parent_of_root"])
def test_index_directory_containing_root_is_refused(tmp_path, where):
    root = tmp_path / "outer" / "root"
    make_tree(root, {"a.txt": "alpha\n"})
    idx = root if where == "root_itself" else root.parent
    proc = BackgroundProcess(["serve", "--no-watch", "--index-path", str(idx), str(root)], cwd=tmp_path)
    with proc:
        result = proc.wait(30)
    assert_exit(result, "error")
    assert result.err.strip(), result.describe()
    assert not (idx / "serve.json").exists()
