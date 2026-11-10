# feature: F10
"""``trisift status``: server, index and no-index reports, and readiness."""

from __future__ import annotations

from _helpers import lf_lines
import json
import os
import shutil
import time
from pathlib import Path

import pytest

from _helpers import make_tree, run_trisift, unique_token
from F07_helpers import read_stats, FALLBACK_NOTICE
from F01_helpers import assert_exit
from F09_helpers import (
    DISCOVERY_FILE,
    INDEX_DIR_NAME,
    ServerProcess,
    probe_denied,
    rpc_status,
    wait_ready,
    wait_status,
    wide_build_tree,
)
from F10_helpers import (
    COVERAGE_WARNING_LABEL,
    age_value,
    coverage_word,
    indexing_progress,
    parse_status_report,
    run_status,
    seconds_value,
    split_watch_mode,
)

NATIVE_BOUND = 60.0


def _real(p) -> str:
    return os.path.realpath(p)


def _status(root, **kw):
    r = run_status(root, cwd=Path(root).parent, **kw)
    assert_exit(r, "match")  # the success status
    return r, parse_status_report(r.out)


def _counted_fixture(root):
    """A tree whose admitted text files are known independently; returns their count.

    Admitted and indexed: two visible text files and one hidden text file.
    Not indexed: a binary-extension file, a file with a NUL byte, and a file
    inside ``.git``.
    """
    make_tree(root, {
        "a.txt": "alpha\n",
        "sub/b.txt": "beta\n",
        ".hidden.txt": "hidden\n",
        "pic.png": "not really an image\n",
        "nul.txt": b"zero\0byte\n",
        ".git/inside.txt": "git internals\n",
    })
    return 3


def _index(root):
    r = run_trisift(["index", str(root)], cwd=root, timeout=300)
    assert r.code == 0, r.describe()


# F10.T01
def test_server_status_report_fields(tmp_path):
    root = tmp_path / "root"
    n = _counted_fixture(root)
    # Started on an existing index, so the startup reconciliation completes
    # and the report carries a last success and a duration.
    _index(root)
    with ServerProcess(root, ["--watch-budget", "777", "--poll-interval", "33"]) as srv:
        wait_ready(srv)
        wait_status(srv.port, lambda s: s["watch_mode_active"] == "native" and s["last_reconcile_at"] is not None,
                    timeout=NATIVE_BOUND, process=srv, message="native with a completed reconciliation")
        r, rep = _status(root)
        assert rep.kind == "server" and rep.subject == _real(root), rep.raw
        record = json.loads((root / INDEX_DIR_NAME / DISCOVERY_FILE).read_text())
        assert int(rep["PID"]) == record["pid"] == srv.proc.pid
        assert int(rep["Port"]) == record["port"] == srv.port
        assert int(rep["Files"]) == n
        assert rep["Watcher"] == "active"
        assert split_watch_mode(rep["Watch mode"]) == ("native", "auto")
        assert rep.get("Fallback") is None
        assert int(rep["Watch budget"]) == 777
        assert seconds_value(rep["Poll interval"]) == 33
        assert rep["Reconcile"] in ("idle", "running")
        age_value(rep["Last successful reconcile"])
        assert rep["Reconcile pending"] == "no"
        assert rep["Reconcile overdue"] == "no"
        assert rep["Last reconcile duration"].endswith("ms") and int(rep["Last reconcile duration"][:-2]) >= 0
        assert rep.get("Last reconcile error") is None
        assert indexing_progress(rep["Indexing"]) == "complete"
        assert coverage_word(rep["Hidden coverage"]) == "complete"
    other = tmp_path / "other"
    make_tree(other, {"x.txt": "x\n"})
    with ServerProcess(other, []) as srv2:
        wait_ready(srv2)
        _, rep2 = _status(other)
        assert rep2.kind == "server"
        assert seconds_value(rep2["Poll interval"]) == 120
        assert int(rep2["Watch budget"]) == 8192
    with ServerProcess(other, ["--watch-mode", "poll"]) as srv3:
        wait_ready(srv3)
        st = rpc_status(srv3.port)
        assert st["poll_interval_secs"] == 120


def _sample_until(srv, stop, timeout, interval=0.01):
    """Collect status samples until ``stop(samples)`` is true; fail after ``timeout``."""
    samples = []
    t0 = time.monotonic()
    while True:
        samples.append(rpc_status(srv.port))
        if stop(samples):
            return samples
        assert srv.alive() and time.monotonic() - t0 < timeout, f"no end condition; last={samples[-1]}"
        time.sleep(interval)


def _assert_no_starting_after_native(samples):
    seen_native = False
    for s in samples:
        if s["watch_mode_active"] == "native":
            seen_native = True
        assert not (seen_native and s["watch_mode_active"] == "starting"), "starting reported after native"
        assert s["watch_mode_active"] in ("native", "starting"), s


# F10.T02
def test_active_mode_disabled_and_poll(tmp_path):
    root = tmp_path / "root"
    make_tree(root, {"a.txt": "alpha\n"})
    with ServerProcess(root, ["--no-watch"]) as srv:
        st = rpc_status(srv.port)
        assert (st["watch_mode_active"], st["watch_mode_requested"]) == ("disabled", "disabled")
        wait_ready(srv)
        _, rep = _status(root)
        assert split_watch_mode(rep["Watch mode"]) == ("disabled", "disabled")
        assert rep["Watcher"] == "inactive"
    with ServerProcess(root, ["--watch-mode", "poll"]) as srv:
        st = rpc_status(srv.port)
        assert (st["watch_mode_active"], st["watch_mode_requested"]) == ("poll", "poll")
        wait_ready(srv)
        _, rep = _status(root)
        assert split_watch_mode(rep["Watch mode"]) == ("poll", "poll")


# F10.T02
def test_active_mode_after_fallback_reports_poll_and_reason(tmp_path):
    root = tmp_path / "root"
    make_tree(root, {f"d{i}/f.txt": f"{unique_token()}\n" for i in range(5)})
    with ServerProcess(root, ["--watch-budget", "1"]) as srv:
        wait_ready(srv)
        wait_status(srv.port, lambda s: s["watch_mode_active"] == "poll", timeout=NATIVE_BOUND,
                    process=srv, message="poll after fallback")
        _, rep = _status(root)
        assert split_watch_mode(rep["Watch mode"]) == ("poll", "auto")
        assert rep["Fallback"].strip()
        samples = _sample_until(srv, lambda s: len(s) >= 30, 30, 0.05)
        assert all(s["watch_mode_active"] == "poll" and s["watch_fallback_reason"] for s in samples)


# F10.T02
def test_auto_background_build_is_native_by_indexing_complete(tmp_path):
    root = tmp_path / "wide"
    wide_build_tree(root, n_dirs=12, files_per_dir=100, size=5000)
    with ServerProcess(root, ["--max-cpu", "1"]) as srv:
        samples = _sample_until(
            srv, lambda ss: not ss[-1]["indexing"] and ss[-1]["hidden_complete"], 300)
        assert samples[-1]["watch_mode_active"] == "native", samples[-1]
        samples += _sample_until(srv, lambda ss: len(ss) >= 100, 30, 0.02)
        _assert_no_starting_after_native(samples)
        assert samples[-1]["watch_mode_active"] == "native"


# F10.T02
def test_auto_on_existing_index_is_native_by_first_reconcile(tmp_path):
    root = tmp_path / "wide"
    wide_build_tree(root, n_dirs=10, files_per_dir=100, size=5000)
    _index(root)
    with ServerProcess(root, []) as srv:
        samples = _sample_until(srv, lambda ss: ss[-1]["last_reconcile_duration_ms"] is not None, 120, 0.002)
        assert samples[-1]["watch_mode_active"] == "native", samples[-1]
        samples += _sample_until(srv, lambda ss: len(ss) >= 100, 30, 0.02)
        _assert_no_starting_after_native(samples)


# F10.T03
def test_pending_and_overdue_while_a_poll_build_holds_reconciliation(tmp_path):
    root = tmp_path / "wide"
    wide_build_tree(root, n_dirs=12, files_per_dir=100, size=5000)
    from F00_observations import ReadGate
    gate_path = next(root.rglob("*.txt"))
    with ReadGate(gate_path) as gate, ServerProcess(root, ["--watch-mode", "poll", "--poll-interval", "1", "--max-cpu", "1"]) as srv:
        try:
            gate.wait_blocked(srv.proc)
            initial = rpc_status(srv.port)
            _, cli = _status(root)
            check = rpc_status(srv.port)
            assert check["indexing"], "build window ended before CLI observation"
            # A lease establishes unfinished input, not the implementation's
            # phase assignment. A closing pass may already have started.
            for sample in (initial, check):
                if not sample["reconcile_running"] and sample["last_reconcile_duration_ms"] is None:
                    assert sample["reconcile_pending"] is True and sample["reconcile_overdue"] is True
                if sample["reconcile_pending"]:
                    assert sample["reconcile_overdue"] is True
            if all(not s["reconcile_running"] and s["last_reconcile_duration_ms"] is None
                   for s in (initial, check)):
                assert cli["Reconcile pending"] == cli["Reconcile overdue"] == "yes"
        finally:
            gate.release()
        samples = _sample_until(srv, lambda ss: ss[-1]["last_reconcile_duration_ms"] is not None, 300)
        samples.insert(0, initial)
        # Indexing can overlap the closing reconciliation. Pending ends at
        # reconciliation start, not at the implementation's indexing boundary.
        for s in samples:
            if s["reconcile_running"] or s["last_reconcile_duration_ms"] is not None:
                break
            assert s["reconcile_pending"] is True and s["reconcile_overdue"] is True, s
        # Before any reconciliation completed: no last success, no duration.
        first = samples[0]
        assert first["last_reconcile_at"] is None and first["last_reconcile_duration_ms"] is None
        for s in samples:
            if s["reconcile_pending"]:
                assert s["reconcile_overdue"] is True, s
        assert samples[-1]["last_reconcile_duration_ms"] is not None


# F10.T03
def test_cli_reports_never_and_no_duration_before_first_reconcile(tmp_path):
    root = tmp_path / "wide"
    rels = wide_build_tree(root, n_dirs=12, files_per_dir=100, size=6000)
    from F00_observations import ReadGate
    gate_path = next(root.rglob("*.txt"))
    with ReadGate(gate_path) as gate, ServerProcess(root, ["--no-watch", "--max-cpu", "1"]) as srv:
        try:
            gate.wait_blocked(srv.proc)
            assert rpc_status(srv.port)["indexing"] is True, "build window not observed"
            _, rep = _status(root)
            after = rpc_status(srv.port)
            assert after["indexing"] is True and after["last_reconcile_duration_ms"] is None, (
                f"the build ended before the report was taken: {after}"
            )
            assert rep["Last successful reconcile"] == "never"
            assert rep.get("Last reconcile duration") is None
            done, total = indexing_progress(rep["Indexing"])
            assert done >= 0 and (total == 0 or done <= total == len(rels))
            assert coverage_word(rep["Hidden coverage"]) == "unavailable"
        finally:
            gate.release()
        st = wait_ready(srv, timeout=300)
        st = wait_status(srv.port, lambda s: s["last_reconcile_duration_ms"] is not None, timeout=60,
                         process=srv, message="first reconciliation")
        _, rep = _status(root)
        assert rep["Last reconcile duration"].endswith("ms")
        age_value(rep["Last successful reconcile"])


# F10.T03
def test_fallback_sets_pending_until_next_reconcile(tmp_path):
    root = tmp_path / "root"
    make_tree(root, {f"d{i}/f.txt": f"{unique_token()}\n" for i in range(30)})
    _index(root)
    with ServerProcess(root, ["--watch-budget", "1", "--poll-interval", "3"]) as srv:
        samples = _sample_until(srv, lambda ss: len(ss) >= 2 and ss[-1]["watch_mode_active"] == "poll"
                                and ss[-1]["reconcile_pending"] is False and not ss[-1]["reconcile_running"], 60, 0.002)
        poll = [s for s in samples if s["watch_mode_active"] == "poll"]
        assert poll and all(s["watch_fallback_reason"] for s in poll)
        for s in samples:
            if s["reconcile_pending"]:
                assert s["reconcile_overdue"] is True, s
        # Until a reconciliation is seen to start (running) or to complete
        # (last success / duration change) after the first poll-mode sample,
        # every poll-mode sample must report pending.
        mark = (poll[0]["last_reconcile_at"], poll[0]["last_reconcile_duration_ms"])
        if poll[0]["reconcile_pending"]:
            for s in poll:
                if s["reconcile_running"] or (s["last_reconcile_at"], s["last_reconcile_duration_ms"]) != mark:
                    break
                assert s["reconcile_pending"] is True, f"pending dropped before any reconciliation: {s}"
        # Existing-index startup may finish reconciliation before accepting requests.



# F10.T03
def test_pending_never_under_no_watch_or_native(tmp_path):
    root = tmp_path / "root"
    make_tree(root, {"a.txt": "alpha\n", "s/b.txt": "beta\n"})
    with ServerProcess(root, ["--no-watch"]) as srv:
        samples = _sample_until(srv, lambda ss: len(ss) >= 60, 30, 0.02)
        for s in samples:
            assert s["reconcile_pending"] is False and s["reconcile_overdue"] is False, s
        wait_ready(srv)
    with ServerProcess(root, []) as srv:
        wait_status(srv.port, lambda s: s["watch_mode_active"] == "native", timeout=NATIVE_BOUND,
                    process=srv, message="native")
        for i in range(5):
            (root / f"n{i}.txt").write_text("new\n")
        samples = _sample_until(srv, lambda ss: len(ss) >= 60, 30, 0.02)
        for s in samples:
            assert s["watch_mode_active"] == "native" and s["reconcile_pending"] is False, s
            assert s["reconcile_overdue"] is False, s


def _reconcile_failure_cycle(srv, root, break_it, restore):
    """Break reconciliation, check error with unchanged last success, then restore."""
    base = wait_status(srv.port, lambda s: s["last_reconcile_at"] is not None and s["last_reconcile_error"] is None,
                       timeout=60, process=srv, message="a successful reconciliation")
    break_it()
    try:
        failed = wait_status(srv.port, lambda s: s["last_reconcile_error"] is not None, timeout=30,
                             process=srv, message="a failed reconciliation")
        assert failed["last_reconcile_duration_ms"] is not None
        last_ok = failed["last_reconcile_at"]
        assert last_ok is not None and last_ok >= base["last_reconcile_at"]
        _, rep = _status(root)
        assert rep["Last reconcile error"].strip()
        t_end = time.monotonic() + 3.5
        while time.monotonic() < t_end:
            s = rpc_status(srv.port)
            assert s["last_reconcile_at"] == last_ok, f"last success moved during failures: {s}"
            if not s["reconcile_running"]:
                assert s["last_reconcile_error"] is not None, s
            time.sleep(0.1)
    finally:
        restore()
    healed = wait_status(srv.port, lambda s: s["last_reconcile_error"] is None and not s["reconcile_running"],
                         timeout=30, process=srv, message="a successful reconciliation after repair")
    assert healed["last_reconcile_at"] > last_ok
    _, rep = _status(root)
    assert rep.get("Last reconcile error") is None


# F10.T04
def test_reconcile_failure_on_unreadable_directory(tmp_path):
    root = tmp_path / "root"
    make_tree(root, {"a.txt": "alpha\n", "locked/l.txt": "locked\n"})
    locked = root / "locked"
    with ServerProcess(root, ["--watch-mode", "poll", "--poll-interval", "1"], drop_dac=True) as srv:
        wait_ready(srv)

        def break_it():
            os.chmod(locked, 0)
            probe_denied(locked)

        _reconcile_failure_cycle(srv, root, break_it, lambda: os.chmod(locked, 0o755))


# F10.T04
def test_reconcile_failure_when_index_directory_is_not_writable(tmp_path):
    root = tmp_path / "root"
    make_tree(root, {"a.txt": "alpha\n"})
    idx = root / INDEX_DIR_NAME
    with ServerProcess(root, ["--watch-mode", "poll", "--poll-interval", "1"], drop_dac=True) as srv:
        wait_ready(srv)

        def break_it():
            os.chmod(idx, 0o555)
            probe_denied(idx, write=True)
            (root / f"pending_{unique_token()}.txt").write_text("pending change\n")

        _reconcile_failure_cycle(srv, root, break_it, lambda: os.chmod(idx, 0o755))


# F10.T05
def test_index_status_report_without_server(tmp_path):
    root = tmp_path / "root"
    n = _counted_fixture(root)
    before = time.time()
    _index(root)
    after = time.time()
    time.sleep(2.2)
    r, rep = _status(root)
    assert rep.kind == "index" and rep.subject == _real(root), rep.raw
    assert int(rep["Files"]) == n
    for field in ("Created", "Updated"):
        value = rep[field]
        unit = {"s": 1, "m": 60, "h": 3600, "d": 86400}[value.split()[0][-1]]
        assert age_value(value) <= time.time() - before + 1
        assert age_value(value) + unit > time.time() - after - 1
    default = run_trisift(["status"], cwd=root)
    assert parse_status_report(default.out).kind == "index"
    assert rep["Server"] == "not running"
    assert coverage_word(rep["Hidden coverage"]) == "complete"
    # files-extra.bin copied from an index of another tree: not full coverage.
    other = tmp_path / "other"
    make_tree(other, {"zz.txt": "zz\n", "yy.txt": "yy\n"})
    _index(other)
    shutil.copy(other / INDEX_DIR_NAME / "files-extra.bin", root / INDEX_DIR_NAME / "files-extra.bin")
    r, rep = _status(root)
    assert rep.kind == "index"
    assert coverage_word(rep["Hidden coverage"]) == "unavailable"
    assert int(rep["Files"]) == n


# F10.T05
def test_index_status_uses_custom_index_path(tmp_path):
    root = tmp_path / "root"
    n = _counted_fixture(root)
    idx = tmp_path / "elsewhere"
    r = run_trisift(["index", "--index-path", str(idx), str(root)], cwd=tmp_path, timeout=300)
    assert r.code == 0, r.describe()
    _, rep = _status(root, index_path=idx)
    assert rep.kind == "index" and int(rep["Files"]) == n
    _, rep = _status(root)
    assert rep.kind == "none"
    with ServerProcess(root, ["--no-watch", "--index-path", str(idx)], index_dir=idx) as srv:
        wait_ready(srv)
        _, rep = _status(root, index_path=idx)
        assert rep.kind == "server" and int(rep["PID"]) == srv.proc.pid


# F10.T06
@pytest.mark.parametrize("state", ["no_index", "meta_missing", "meta_garbled", "custom_path_missing"])
def test_no_index_report(tmp_path, state):
    root = tmp_path / "root"
    make_tree(root, {"a.txt": "alpha\n"})
    idx = root / INDEX_DIR_NAME
    kw = {}
    if state in ("meta_missing", "meta_garbled"):
        _index(root)
        if state == "meta_missing":
            (idx / "meta.json").unlink()
        else:
            (idx / "meta.json").write_text("{not json")
    elif state == "custom_path_missing":
        idx = tmp_path / "nowhere"
        kw["index_path"] = idx
    r, rep = _status(root, **kw)
    assert rep.kind == "none", rep.raw
    assert _real(rep.subject) == _real(idx)
    assert f"trisift index {_real(root)}" in rep.hint


# F10.T07
def test_ready_status_means_next_search_is_answered_by_server(tmp_path):
    root = tmp_path / "wide"
    rels = wide_build_tree(root, n_dirs=12, files_per_dir=100, size=5000)
    tok = unique_token()
    marked = set(rels[::611])
    for rel in marked:
        with open(root / rel, "a") as f:
            f.write(f"{tok}\n")
    with ServerProcess(root, ["--no-watch", "--max-cpu", "1"]) as srv:
        saw_building = False
        deadline = time.monotonic() + 300
        while True:
            _, rep = _status(root)
            assert rep.kind == "server"
            ind = indexing_progress(rep["Indexing"])
            if ind == "complete" and coverage_word(rep["Hidden coverage"]) == "complete":
                break
            saw_building = True
            assert time.monotonic() < deadline
            time.sleep(0.05)
        r = run_trisift(["--stats", "-l", tok], cwd=root)
        assert r.code == 0, r.describe()
        assert read_stats(r)["path"] == "server" and not any(FALLBACK_NOTICE.search(l) for l in lf_lines(r.err)), r.describe()
        assert set(lf_lines(r.out)) == marked
        # A file the --no-watch server has not seen proves the answer was not a scan.
        (root / "late.txt").write_text(f"{tok}\n")
        r = run_trisift(["-l", tok], cwd=root)
        assert set(lf_lines(r.out)) == marked, r.describe()


# F10.T08
def test_status_on_missing_root_is_an_error(tmp_path):
    r = run_trisift(["status", str(tmp_path / "does-not-exist")], cwd=tmp_path, timeout=60)
    assert_exit(r, "error")


def _truncate(path, how):
    data = path.read_bytes()
    if how == "empty":
        path.write_bytes(b"")
    elif how == "half":
        path.write_bytes(data[: len(data) // 2])
    else:
        path.write_bytes(data[:-1])


# F10.T09
@pytest.mark.parametrize("how", ["empty", "half", "last_byte"])
def test_malformed_coverage_metadata_warns_and_reports_unavailable(tmp_path, how):
    root = tmp_path / "root"
    n = _counted_fixture(root)
    _index(root)
    _truncate(root / INDEX_DIR_NAME / "files-extra.bin", how)
    r, rep = _status(root)
    assert any(line.startswith(COVERAGE_WARNING_LABEL) for line in lf_lines(r.err)), r.describe()
    assert rep.kind == "index" and int(rep["Files"]) == n
    assert rep["Server"] == "not running"
    age_value(rep["Created"])
    age_value(rep["Updated"])
    assert coverage_word(rep["Hidden coverage"]) == "unavailable"


# F10.T09
def test_missing_coverage_metadata_reports_unavailable_without_warning(tmp_path):
    root = tmp_path / "root"
    n = _counted_fixture(root)
    _index(root)
    (root / INDEX_DIR_NAME / "files-extra.bin").unlink()
    r, rep = _status(root)
    assert not any(line.startswith(COVERAGE_WARNING_LABEL) for line in lf_lines(r.err)), r.describe()
    assert rep.kind == "index" and int(rep["Files"]) == n
    assert coverage_word(rep["Hidden coverage"]) == "unavailable"


# F10.T04 regression — FP-10.01

def test_first_reconciliation_failure_has_duration(tmp_path):
    from _helpers import make_unreadable
    root = make_tree(tmp_path / "w", {"a.txt": "visible\n", "locked/x.txt": "inside\n"})
    _index(root)
    with make_unreadable(root / "locked"):
        with ServerProcess(root, ["--no-watch"]) as srv:
            st = wait_status(srv.port, lambda s: s["last_reconcile_error"] is not None,
                             timeout=60, process=srv, message="failed initial reconciliation")
            assert st["last_reconcile_at"] is None
            assert st["last_reconcile_duration_ms"] is not None
            _, rep = _status(root)
            assert rep["Last successful reconcile"] == "never"
            assert int(rep["Last reconcile duration"][:-2]) >= 0
            assert rep["Last reconcile error"]


# F10.T09 regression — FP-10.02, FP-10.06

def test_coverage_checks_actual_index_and_permission_failures(tmp_path):
    from _helpers import make_unreadable
    root = make_tree(tmp_path / "w", {"a.txt": "alpha\n", "locked/b.txt": "beta\n"})
    other = make_tree(tmp_path / "other", {"c.txt": "gamma\n", "d.txt": "delta\n"})
    _index(root)
    _index(other)
    idx = root / INDEX_DIR_NAME
    with make_unreadable(idx / "files-extra.bin"):
        r, rep = _status(root)
        assert coverage_word(rep["Hidden coverage"]) == "unavailable"
        assert any(l.startswith("warning:") for l in lf_lines(r.err))
    for filename in ("files.bin", "meta.json"):
        old = (idx / filename).read_bytes()
        try:
            shutil.copy(other / INDEX_DIR_NAME / filename, idx / filename)
            _, rep = _status(root)
            assert coverage_word(rep["Hidden coverage"]) == "unavailable"
        finally:
            (idx / filename).write_bytes(old)
    with make_unreadable(root / "locked"):
        _index(root)
    _, rep = _status(root)
    assert coverage_word(rep["Hidden coverage"]) == "unavailable"
