# feature: F09
"""Search server: automatic refresh (auto/native and poll), fallback, no-watch, queue cap."""

from __future__ import annotations

from _helpers import lf_lines
import os
import threading
import time
from pathlib import Path

import pytest

from _helpers import git, git_add, git_init, hermetic_env, make_tree, unique_token
from F09_helpers import (
    ServerProcess,
    rpc_reload,
    rpc_search,
    rpc_status,
    row_files,
    wait_ready,
    wait_reflected,
    wait_status,
    wait_poll_completion,
)

#: Bound for a change to be reflected while the active mode is native (FP-09.05).
NATIVE_BOUND = 60.0
#: Slack for sampling (status polling cadence, timestamp resolution).
SAMPLING = 1.5


def _files(srv, token, **params):
    return row_files(srv.search(token, **params))


def _expect(srv, token, want, bound, what, **params):
    check = lambda: _files(srv, token, **params) == want
    if bound == "poll":
        return wait_poll_completion(srv, time.time(), check=check, what=what)
    return wait_reflected(check, timeout=bound, what=what, server=srv)


def _settle_poll(srv):
    """Wait until the poll server has completed at least one reconciliation."""
    return wait_status(srv.port, lambda s: s["last_reconcile_duration_ms"] is not None,
                       timeout=60, process=srv, message="first reconciliation completed")


def _marker_round(srv, root, bound, what):
    """Create a fresh marker file and wait until it is reflected.

    Used as a live baseline: once the marker shows, a reconciliation (or
    event batch) that started after every earlier change has completed.
    """
    mark = unique_token()
    (Path(root) / f"marker_{mark}.txt").write_text(f"{mark}\n")
    _expect(srv, mark, {f"marker_{mark}.txt"}, bound, f"{what}: marker")


def _refresh_scenario(srv, root, bound, outside):
    """Run every listed change kind and check it is reflected within ``bound`` seconds."""
    a1, a2, b1, created, deep, ign2 = (unique_token() for _ in range(6))
    root = Path(root)
    # create
    (root / "new.txt").write_text(f"{created}\n")
    _expect(srv, created, {"new.txt"}, bound, "create")
    # modify
    a_old = (root / "a.txt").read_text().split()[0]
    original_stat = (root / "a.txt").stat()
    (root / "a.txt").write_text(f"{a1}\n")
    os.utime(root / "a.txt", ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    _expect(srv, a1, {"a.txt"}, bound, "modify (new content)")
    assert _files(srv, a_old) == set(), "modify: old content still returned"
    # rename
    b_tok = (root / "sub/b.txt").read_text().split()[0]
    os.rename(root / "sub/b.txt", root / "sub/b2.txt")
    _expect(srv, b_tok, {"sub/b2.txt"}, bound, "rename")
    # delete
    (root / "new.txt").unlink()
    _expect(srv, created, set(), bound, "delete")
    # file in a directory that did not exist at startup
    (root / "nd/deeper").mkdir(parents=True)
    (root / "nd/deeper/f.txt").write_text(f"{deep}\n")
    _expect(srv, deep, {"nd/deeper/f.txt"}, bound, "new directory")
    # file under an ignored directory, and one matched by an ignore rule: never indexed
    (root / "ign/y.txt").write_text(f"{ign2}\n")
    (root / "rule_ignored.log").write_text(f"{ign2}\n")
    _marker_round(srv, root, bound, "ignored")
    assert _files(srv, ign2) == set() and _files(srv, ign2, hidden=True) == set()
    # .gitignore edit: content newly ignored stops, newly unignored becomes searchable
    ign_tok = (root / "ign/x.txt").read_text().split()[0]
    (root / ".gitignore").write_text("sub/\n*.log\n")
    _expect(srv, b_tok, set(), bound, ".gitignore newly ignores sub/")
    _expect(srv, ign_tok, {"ign/x.txt"}, bound, ".gitignore unignores ign/")
    # .ignore edit
    (root / ".ignore").write_text("nd/\n")
    _expect(srv, deep, set(), bound, ".ignore newly ignores nd/")
    (root / ".ignore").unlink()
    _expect(srv, deep, {"nd/deeper/f.txt"}, bound, ".ignore removal unignores nd/")
    # symbolic links are never followed into content
    out_tok = (Path(outside) / "s.txt").read_text().split()[0]
    os.symlink(Path(outside) / "s.txt", root / "link.txt")
    os.symlink(outside, root / "linkdir")
    _marker_round(srv, root, bound, "symlink")
    assert _files(srv, out_tok) == set() and _files(srv, out_tok, hidden=True) == set()


def _refresh_tree(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    make_tree(outside, {"s.txt": f"{unique_token()}\n"})
    make_tree(root, {
        "a.txt": f"{unique_token()}\n",
        "sub/b.txt": f"{unique_token()}\n",
        "ign/x.txt": f"{unique_token()}\n",
        ".gitignore": "ign/\n*.log\n",
    })
    env = hermetic_env(tmp_path / "home")
    git_init(root, env=env)
    return root, outside, env


# F09.T08
def test_poll_mode_reflects_every_change_kind(tmp_path):
    root, outside, env = _refresh_tree(tmp_path)
    interval = 1
    with ServerProcess(root, ["--watch-mode", "poll", "--poll-interval", str(interval)], env=env) as srv:
        wait_ready(srv)
        st = _settle_poll(srv)
        assert st["watch_mode_active"] == "poll" and st["watch_mode_requested"] == "poll"
        assert st["watcher_active"] is False
        bound = "poll"
        _refresh_scenario(srv, root, bound, outside)
        assert rpc_status(srv.port)["watch_mode_active"] == "poll"


# F09.T09
def test_auto_mode_native_reflects_changes_within_bound(tmp_path):
    root, outside, env = _refresh_tree(tmp_path)
    with ServerProcess(root, [], env=env) as srv:
        wait_ready(srv)
        st = wait_status(srv.port, lambda s: s["watch_mode_active"] == "native", timeout=NATIVE_BOUND,
                         process=srv, message="active mode native")
        assert st["watch_mode_requested"] == "auto" and st["watch_fallback_reason"] is None
        assert st["watcher_active"] is True
        _refresh_scenario(srv, root, NATIVE_BOUND, outside)
        st = rpc_status(srv.port)
        assert st["watch_mode_active"] == "native", f"left native mode during the scenario: {st}"


# F09.T10
@pytest.mark.parametrize("mode", [["--watch-mode", "poll", "--poll-interval", "1"], []], ids=["poll", "auto"])
def test_git_index_changes_under_ignorecase_are_reflected(tmp_path, mode):
    root = tmp_path / "repo"
    env = hermetic_env(tmp_path / "home")
    forced, seed = unique_token(), unique_token()
    make_tree(root, {
        ".gitignore": "IGNORED/\n",
        "src/lib.txt": f"{seed}\n",
        "ignored/t.txt": f"{forced}\n",
    })
    git_init(root, {"core.ignorecase": "true"}, env=env)
    git_add(root, [".gitignore", "src/lib.txt"], env=env)
    with ServerProcess(root, mode, env=env) as srv:
        wait_ready(srv)
        if mode:
            st = _settle_poll(srv)
            bound = "poll"
        else:
            st = wait_status(srv.port, lambda s: s["watch_mode_active"] == "native",
                             timeout=NATIVE_BOUND, process=srv, message="active mode native")
            bound = NATIVE_BOUND
        assert _files(srv, seed) == {"src/lib.txt"}
        assert _files(srv, forced) == set(), "a case-insensitively ignored file was indexed"
        git_add(root, ["ignored/t.txt"], force=True, env=env)
        _expect(srv, forced, {"ignored/t.txt"}, bound, "git add -f under an ignored directory")
        git(root, "rm", "--cached", "--quiet", "--", "ignored/t.txt", env=env)
        _expect(srv, forced, set(), bound, "git rm --cached under an ignored directory")


# F09.T11
def test_poll_cadence_holds_under_continuous_queries(tmp_path):
    root = tmp_path / "root"
    files = {f"sub/f{i}.txt": f"content {unique_token()}\n" for i in range(50)}
    make_tree(root, files)
    interval = 2
    with ServerProcess(root, ["--watch-mode", "poll", "--poll-interval", str(interval)]) as srv:
        wait_ready(srv)
        _settle_poll(srv)
        stop = threading.Event()
        errors = []

        def hammer():
            while not stop.is_set():
                try:
                    rpc_search(srv.port, "content")
                except BaseException as exc:
                    errors.append(exc)
                    return

        threads = [threading.Thread(target=hammer) for _ in range(4)]
        for t in threads:
            t.start()
        try:
            tok = unique_token()
            (root / "fresh.txt").write_text(f"{tok}\n")
            changed_at = time.time()
            seen = wait_poll_completion(
                srv, changed_at, check=lambda: row_files(rpc_search(srv.port, tok)) == {"fresh.txt"},
                what="polling under continuous queries", count=4)
            assert len(seen) == 4
        finally:
            stop.set()
            for t in threads:
                t.join(30)
                assert not t.is_alive(), "query worker did not stop"
        assert not errors, errors


def _several_dirs(tmp_path):
    root = tmp_path / "root"
    make_tree(root, {f"d{i}/f.txt": f"{unique_token()}\n" for i in range(6)})
    return root


# F09.T12
def test_tiny_watch_budget_falls_back_to_polling(tmp_path):
    root = _several_dirs(tmp_path)
    with ServerProcess(root, ["--watch-budget", "1", "--poll-interval", "1"]) as srv:
        wait_ready(srv)
        st = wait_status(srv.port, lambda s: s["watch_mode_active"] == "poll", timeout=NATIVE_BOUND,
                         process=srv, message="active mode poll after fallback")
        assert st["watch_mode_requested"] == "auto"
        assert isinstance(st["watch_fallback_reason"], str) and st["watch_fallback_reason"].strip()
        assert st["watcher_active"] is False
        _settle_poll(srv)
        bound = "poll"
        tok = unique_token()
        (root / "d3/new.txt").write_text(f"{tok}\n")
        _expect(srv, tok, {"d3/new.txt"}, bound, "create after fallback")
        (root / "d3/new.txt").unlink()
        _expect(srv, tok, set(), bound, "delete after fallback")
        st = rpc_status(srv.port)
        assert st["watch_mode_active"] == "poll" and st["watch_fallback_reason"], st


# F09.T12
def test_large_watch_budget_stays_native(tmp_path):
    root = _several_dirs(tmp_path)
    with ServerProcess(root, ["--watch-budget", "4096"]) as srv:
        wait_ready(srv)
        st = wait_status(srv.port, lambda s: s["watch_mode_active"] == "native", timeout=NATIVE_BOUND,
                         process=srv, message="active mode native")
        assert st["watch_mode_requested"] == "auto" and st["watch_fallback_reason"] is None
        assert st["watch_budget"] == 4096


# F09.T13
def test_no_watch_disables_refresh_until_reload(tmp_path):
    root = tmp_path / "root"
    old, new, created = unique_token(), unique_token(), unique_token()
    make_tree(root, {"a.txt": f"{old}\n", "b.txt": "keep\n"})
    with ServerProcess(root, ["--no-watch"]) as srv:
        st = wait_ready(srv)
        assert st["watch_mode_active"] == "disabled" and st["watch_mode_requested"] == "disabled"
        assert st["watcher_active"] is False
        (root / "a.txt").write_text(f"{new}\n")
        (root / "c.txt").write_text(f"{created}\n")
        time.sleep(4)
        # Selection stays stale, but indexed candidates use current contents.
        assert _files(srv, old) == set()
        assert _files(srv, new) == set() and _files(srv, created) == set()
        assert _files(srv, "keep") == {"b.txt"}
        assert rpc_status(srv.port)["watch_mode_active"] == "disabled"
        rpc_reload(srv.port)
        assert _files(srv, old) == set()
        assert _files(srv, new) == {"a.txt"} and _files(srv, created) == {"c.txt"}


# F09.T15
def test_watcher_queue_overflow_loses_no_change(tmp_path):
    root = tmp_path / "root"
    make_tree(root, {"a.txt": "alpha\n", "d/keep.txt": "keep\n"})
    with ServerProcess(root, ["--watcher-queue-cap", "1"]) as srv:
        wait_ready(srv)
        st = wait_status(srv.port, lambda s: s["watch_mode_active"] == "native", timeout=NATIVE_BOUND,
                         process=srv, message="active mode native")
        assert st["watch_fallback_reason"] is None
        import re
        cap = re.search(rb"Watcher queue cap: ([0-9]+)\.", srv.proc.read_stderr())
        assert cap and int(cap[1]) == 1, srv.proc.read_stderr()
        mark = unique_token()
        n = 400
        # Pause delivery so a burst is already waiting when the watcher resumes.
        import signal
        os.kill(srv.pid, signal.SIGSTOP)
        try:
            for i in range(n):
                (root / "d" / f"f{i}.txt").write_text(f"{mark} n{i}\n")
        finally:
            os.kill(srv.pid, signal.SIGCONT)
        want = {f"d/f{i}.txt" for i in range(n)}
        _expect(srv, mark, want, NATIVE_BOUND, "burst of creations with a one-event queue")
        # An implementation may drain the burst without overflow. If it reports
        # overflow, its diagnostic must carry the same configured capacity.
        for line in lf_lines(srv.proc.read_stderr()):
            if b"watcher queue overflowed" in line:
                capacities = re.findall(rb"\(cap ([0-9]+)\)", line)
                assert len(capacities) == 1 and int(capacities[0]) == 1, line
        st = rpc_status(srv.port)
        assert st["watch_mode_active"] == "native" and st["watch_fallback_reason"] is None, st


# F09.T11 regression — FP-09.06, FP-09.10

def test_default_poll_interval(tmp_path):
    root = make_tree(tmp_path / "w", {"file.txt": "orchard\n"})
    with ServerProcess(root, ["--watch-mode", "poll"]) as srv:
        wait_ready(srv)
        assert rpc_status(srv.port)["poll_interval_secs"] == 120
        import re
        cap = re.search(rb"Watcher queue cap: ([0-9]+)\.", srv.proc.read_stderr())
        assert cap and int(cap[1]) == 16384, srv.proc.read_stderr()


# F09.T12 regression — FP-09.05, FP-09.07

def test_native_watch_budget_applies_to_new_directories(tmp_path):
    root = make_tree(tmp_path / "watched", {"file.txt": "before\n"})
    with ServerProcess(root, ["--watch-budget", "2", "--poll-interval", "1"]) as srv:
        wait_ready(srv)
        wait_status(srv.port, lambda s: s["watch_mode_active"] == "native", timeout=NATIVE_BOUND,
                    process=srv, message="initial native watch")
        make_tree(root, {f"new{i}/file.txt": "aftergrowth\n" for i in range(4)})
        status = wait_status(srv.port, lambda s: s["watch_mode_active"] == "poll", timeout=NATIVE_BOUND,
                             process=srv, message="watch-budget fallback after directory growth")
        assert status["watch_fallback_reason"] and status["watcher_active"] is False
        _expect(srv, "aftergrowth", {f"new{i}/file.txt" for i in range(4)}, "poll",
                "complete results after watch-budget fallback")
