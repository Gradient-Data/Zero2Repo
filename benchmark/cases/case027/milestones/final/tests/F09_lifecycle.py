# feature: F09
"""Search server: startup, background build, startup reconciliation, persistence."""

from __future__ import annotations

from _helpers import lf_lines
import json
import os
import time
from pathlib import Path

import pytest

from _helpers import fixture_random, make_tree, pid_alive, run_trisift, unique_token
from F07_helpers import read_stats, FALLBACK_NOTICE
from F01_helpers import assert_exit
from F09_helpers import (
    DISCOVERY_FILE,
    INDEX_DIR_NAME,
    LOCK_FILE,
    ServerProcess,
    cli_listing,
    rpc_reload,
    rpc_search,
    rpc_status,
    row_files,
    wait_ready,
    wait_reconciled,
    wait_reflected,
    wait_poll_completion,
    wide_build_tree,
)
from F10_helpers import coverage_word, parse_status_report, run_status


def _index(root, *extra):
    r = run_trisift(["index", *extra, str(root)], cwd=root, timeout=300)
    assert r.code == 0, f"index build failed\n{r.describe()}"
    assert (Path(root) / INDEX_DIR_NAME / "lookup.bin").exists()
    return r


def _assert_record_removed(server: ServerProcess):
    assert not (server.index_dir / DISCOVERY_FILE).exists(), (
        f"discovery record still present after the interrupt; stderr={server.proc.read_stderr()[-800:]!r}"
    )


def _local_answer(root, token, tracer_dir=None):
    """Search ``token`` with no server running and prove the index (not a scan) answered.

    A tracer file holding ``token`` is written first; it was never indexed,
    so a scanning implementation prints it and an indexed answer does not.
    Returns the set of printed paths (relative, cwd = root) without the tracer.
    """
    root = Path(root)
    assert not (root / INDEX_DIR_NAME / DISCOVERY_FILE).exists()
    tracer = (Path(tracer_dir) if tracer_dir else root) / f"tracer_{unique_token()}.txt"
    tracer.write_text(f"{token} tracer\n")
    try:
        r, paths = cli_listing([token], cwd=root)
        rel_tracer = os.path.relpath(tracer, root)
        assert rel_tracer not in paths, (
            f"a file created after the index was saved was reported: the search scanned "
            f"instead of answering from the saved index\n{r.describe()}"
        )
        return r, paths
    finally:
        tracer.unlink()


# F09.T01
def test_startup_writes_lock_and_discovery_record_and_clients_find_it(tmp_path):
    root = tmp_path / "root"
    tok = unique_token()
    make_tree(root, {"a.txt": f"{tok} one\n", "sub/b.txt": f"x {tok}\n", "other.txt": "nothing\n"})
    with ServerProcess(root, ["--no-watch"]) as srv:
        idx = root / INDEX_DIR_NAME
        assert (idx / LOCK_FILE).exists(), "server lock file missing while the server runs"
        record = json.loads((idx / DISCOVERY_FILE).read_text())
        assert set(record) >= {"pid", "port"}
        assert record["pid"] == srv.proc.pid and pid_alive(record["pid"])
        # The recorded port is the server's: a status request over it is answered.
        rpc_status(record["port"])
        wait_ready(srv)
        # A file created now is unknown to the --no-watch server; a client that
        # scanned instead of asking the server would report it.
        (root / "late.txt").write_text(f"{tok} late\n")
        r = run_trisift(["--stats", "-l", tok], cwd=root)
        assert r.code == 0, r.describe()
        assert set(lf_lines(r.out)) == {"a.txt", "sub/b.txt"}, r.describe()
        assert read_stats(r)["path"] == "server", f"search was not answered by the server\n{r.describe()}"


def _content_fixture(root, tok):
    """Tree exercising every content rule of the build; returns admitted paths holding ``tok``."""
    make_tree(root, {
        "a.txt": f"{tok} a\n",
        "sub/b.txt": f"{tok} b\n",
        ".hidden.txt": f"{tok} hidden\n",
        ".hd/inner.txt": f"{tok} hidden dir\n",
        ".git/inside.txt": f"{tok} git\n",
        "nested/.git/deep.txt": f"{tok} nested git\n",
        "skipme/x.txt": f"{tok} excluded\n",
        "deep/skipme/y.txt": f"{tok} excluded deep\n",
        "secondskip/y.txt": f"{tok} excluded second\n",
        "pic.png": f"{tok} png\n",
        "nul.txt": f"{tok}\0 nul\n".encode(),
        "ign.txt": f"{tok} ignored\n",
        ".ignore": "ign.txt\n",
        "big.txt": f"{tok} big\n" + "y" * 4000 + "\n",
    })
    # visible (non-hidden) admitted files under --exclude skipme --max-filesize 2K
    return {"a.txt", "sub/b.txt"}, {".hidden.txt", ".hd/inner.txt"}


# F09.T02
@pytest.mark.parametrize("state", ["empty_dir", "truncated", "corrupted"])
def test_background_build_on_missing_or_broken_index(tmp_path, state):
    root = tmp_path / "root"
    tok = unique_token()
    visible, hidden = _content_fixture(root, tok)
    idx = root / INDEX_DIR_NAME
    if state == "empty_dir":
        idx.mkdir()
    else:
        _index(root)
        # The tree changes afterwards, so a server that reused the old index
        # without rebuilding would show the deleted file and miss the new one.
        (root / "sub/b.txt").unlink()
        (root / "sub/c.txt").write_text(f"{tok} c\n")
        visible = {"a.txt", "sub/c.txt"}
        if state == "truncated":
            data = (idx / "index.bin").read_bytes()
            (idx / "index.bin").write_bytes(data[: len(data) // 2])
        else:
            (idx / "lookup.bin").write_bytes(fixture_random("corrupt-index").randbytes(256))
    args = ["--no-watch", "--exclude", "skipme", "--exclude", "secondskip", "--max-filesize", "2K"]
    with ServerProcess(root, args) as srv:
        st = wait_ready(srv)
        assert st["num_files"] == len(visible | hidden) + 1  # + the .ignore file itself
        assert row_files(srv.search(tok)) == visible
        assert row_files(srv.search(tok, hidden=True)) == visible | hidden
        # The server answers the CLI with the same set.
        r = run_trisift(["--stats", "-l", tok], cwd=root)
        assert read_stats(r)["path"] == "server", r.describe()
        assert set(lf_lines(r.out)) == visible, r.describe()


# F09.T02
def test_background_build_no_ignore_includes_ignored_and_git(tmp_path):
    root = tmp_path / "root"
    tok = unique_token()
    _content_fixture(root, tok)
    with ServerProcess(root, ["--no-watch", "--no-ignore"]) as srv:
        wait_ready(srv)
        got = row_files(srv.search(tok, hidden=True))
        assert {"ign.txt", ".git/inside.txt", "nested/.git/deep.txt", "big.txt",
                "skipme/x.txt", "a.txt", "sub/b.txt"} <= got
        assert "pic.png" not in got and "nul.txt" not in got


# F09.T02
def test_background_build_progress_and_complete_fallback_meanwhile(tmp_path):
    root = tmp_path / "wide"
    rels = wide_build_tree(root, n_dirs=12, files_per_dir=100, size=6000)
    tok = unique_token()
    marked = set(rels[::997])
    for rel in marked:
        with open(root / rel, "a") as f:
            f.write(f"{tok}\n")
    from F00_observations import ReadGate
    with ReadGate(root / rels[-1]) as gate, ServerProcess(root, ["--no-watch", "--max-cpu", "1"]) as srv:
        try:
            gate.wait_blocked(srv.proc)
            before = rpc_status(srv.port)
            assert before["indexing"] is True, f"build window not observed: {before}"
            assert 0 <= before["index_progress"] <= before["index_total"] or before["index_total"] == 0
            # A search issued during the build falls back and is still complete.
            r = run_trisift(["-l", "-g", "!" + rels[-1], tok], cwd=root)
            after = rpc_status(srv.port)
            assert after["indexing"] is True, (
                f"the build finished before the client search returned; window too narrow: {after}"
            )
            assert r.code == 0, r.describe()
            assert set(lf_lines(r.out)) == marked, r.describe()
            assert any(FALLBACK_NOTICE.search(l) for l in lf_lines(r.err)), f"no fallback notice on stderr\n{r.describe()}"
        finally:
            gate.release()
        samples = [before, after]
        deadline = time.monotonic() + 300
        while True:
            s = rpc_status(srv.port)
            samples.append(s)
            if not s["indexing"] and s["hidden_complete"]:
                break
            assert srv.alive() and time.monotonic() < deadline, f"build never completed: {s}"
            time.sleep(0.05)
        for s in samples:
            if s["indexing"]:
                assert s["index_total"] == 0 or s["index_progress"] <= s["index_total"], s
        done = samples[-1]
        assert done["num_files"] == len(rels)
        assert row_files(srv.search(tok)) == marked


# F09.T03
@pytest.mark.parametrize("res_args", [["--max-memory", "1"], ["--max-cpu", "1"],
                                      ["--max-cpu", "100", "--max-memory", "1"]])
def test_resource_limits_do_not_change_the_index(tmp_path, res_args):
    root = tmp_path / "root"
    rels = wide_build_tree(root, n_dirs=20, files_per_dir=20, size=3000)
    toks = [unique_token() for _ in range(3)]
    for i, rel in enumerate(rels):
        with open(root / rel, "a") as f:
            f.write(f"{toks[i % 3]} line {i}\n")

    def answers(idx, extra):
        with ServerProcess(root, ["--no-watch", "--index-path", str(idx), *extra], index_dir=idx) as srv:
            st = wait_ready(srv)
            out = {"num_files": st["num_files"]}
            for t in toks:
                out[t] = sorted((m["file"], m["line"], m["content"]) for m in srv.search(t))
            out["common"] = len(srv.search("[a-z]{9}"))
            return out

    base = answers(tmp_path / "idx_default", [])
    limited = answers(tmp_path / "idx_limited", res_args)
    assert base["num_files"] == len(rels)
    for i, t in enumerate(toks):
        assert {f for f, _, _ in base[t]} == {r for j, r in enumerate(rels) if j % 3 == i}
    assert limited == base


# F09.T04
def test_startup_reconciliation_reflects_offline_changes(tmp_path):
    root = tmp_path / "root"
    keep, gone, old, new, add, ex, ign = (unique_token() for _ in range(7))
    make_tree(root, {
        "keep.txt": f"{keep}\n", "del.txt": f"{gone}\n", "mod.txt": f"{old}\n",
        "later_ex/e.txt": f"{ex}\n", "ign.txt": f"{ign}\n",
    })
    _index(root)
    (root / "del.txt").unlink()
    (root / "mod.txt").write_text(f"{new}\n")
    (root / "sub").mkdir()
    (root / "sub/add.txt").write_text(f"{add}\n")
    (root / ".ignore").write_text("ign.txt\n")
    expect = {keep: {"keep.txt"}, gone: set(), old: set(), new: {"mod.txt"},
              add: {"sub/add.txt"}, ex: set(), ign: set()}
    started = time.time()
    with ServerProcess(root, ["--no-watch", "--exclude", "later_ex"]) as srv:
        wait_ready(srv)
        wait_reconciled(srv, started)
        for t, files in expect.items():
            assert row_files(srv.search(t)) == files, t
        r = run_trisift(["--stats", "-l", keep], cwd=root)
        assert read_stats(r)["path"] == "server", r.describe()
        srv.stop()
    _assert_record_removed(srv)
    for t, files in expect.items():
        _, paths = _local_answer(root, t)
        assert paths == files, t


# F09.T05
def test_startup_reconciliation_repairs_missing_coverage(tmp_path):
    root = tmp_path / "root"
    tok = unique_token()
    make_tree(root, {"a.txt": f"{tok} a\n", "b.txt": "other\n"})
    _index(root)
    (root / INDEX_DIR_NAME / "files-extra.bin").unlink()
    (root / "later.txt").write_text(f"{tok} later\n")
    pre = parse_status_report(run_status(root, cwd=root).out)
    assert pre.kind == "index" and coverage_word(pre["Hidden coverage"]) == "unavailable"
    with ServerProcess(root, ["--no-watch"]) as srv:
        st = wait_ready(srv)
        assert st["hidden_complete"] is True
        srv.stop()
    post = parse_status_report(run_status(root, cwd=root).out)
    assert post.kind == "index" and coverage_word(post["Hidden coverage"]) == "complete", post.raw
    _, paths = _local_answer(root, tok)
    assert paths == {"a.txt", "later.txt"}


def _wait_rows(srv, token, want, timeout, what):
    wait_reflected(lambda: row_files(srv.search(token)) == want, timeout=timeout, what=what, server=srv)


# F09.T14
def test_startup_reconciliation_is_saved_once_ready(tmp_path):
    root = tmp_path / "root"
    a, b, c = unique_token(), unique_token(), unique_token()
    make_tree(root, {"a.txt": f"{a}\n", "b.txt": f"{b}\n"})
    _index(root)
    (root / "b.txt").unlink()
    (root / "c.txt").write_text(f"{c}\n")
    started = time.time()
    with ServerProcess(root, ["--no-watch"]) as srv:
        wait_ready(srv)
        wait_reconciled(srv, started)
        srv.stop()  # interrupt right at the stated point
    _assert_record_removed(srv)
    assert _local_answer(root, a)[1] == {"a.txt"}
    assert _local_answer(root, b)[1] == set()
    assert _local_answer(root, c)[1] == {"c.txt"}


# F09.T14
def test_poll_reflected_changes_are_saved(tmp_path):
    root = tmp_path / "root"
    keep, old, new, created, gone = (unique_token() for _ in range(5))
    make_tree(root, {"keep.txt": f"{keep}\n", "mod.txt": f"{old}\n", "del.txt": f"{gone}\n"})
    with ServerProcess(root, ["--watch-mode", "poll", "--poll-interval", "1"]) as srv:
        wait_ready(srv)
        (root / "new.txt").write_text(f"{created}\n")
        (root / "mod.txt").write_text(f"{new}\n")
        (root / "del.txt").unlink()
        wait_poll_completion(srv, time.time(), check=lambda: (
            row_files(srv.search(created)) == {"new.txt"}
            and row_files(srv.search(new)) == {"mod.txt"}
            and row_files(srv.search(gone)) == set()), what="persisted poll changes")
        srv.stop()
    _assert_record_removed(srv)
    assert _local_answer(root, created)[1] == {"new.txt"}
    assert _local_answer(root, new)[1] == {"mod.txt"}
    assert _local_answer(root, old)[1] == set()
    assert _local_answer(root, gone)[1] == set()
    assert _local_answer(root, keep)[1] == {"keep.txt"}
    # The saved index also serves a server started later.
    with ServerProcess(root, ["--no-watch"]) as srv2:
        wait_ready(srv2)
        assert row_files(srv2.search(created)) == {"new.txt"}
        assert row_files(srv2.search(gone)) == set()


# F09.T14
def test_reload_result_is_saved_when_reload_responds(tmp_path):
    root = tmp_path / "root"
    a, b = unique_token(), unique_token()
    make_tree(root, {"a.txt": f"{a}\n"})
    with ServerProcess(root, ["--no-watch"]) as srv:
        wait_ready(srv)
        (root / "a.txt").unlink()
        (root / "b.txt").write_text(f"{b}\n")
        rpc_reload(srv.port)
        srv.stop()
    _assert_record_removed(srv)
    assert _local_answer(root, a)[1] == set()
    assert _local_answer(root, b)[1] == {"b.txt"}


# F09.T16
@pytest.mark.parametrize("explicit", [False, True])
def test_second_server_for_locked_index_directory_is_refused(tmp_path, explicit):
    root = tmp_path / "root"
    make_tree(root, {"a.txt": "alpha\n"})
    idx = root / INDEX_DIR_NAME
    with ServerProcess(root, ["--no-watch"]) as first:
        wait_ready(first)
        args = ["serve", "--no-watch"] + (["--index-path", str(idx)] if explicit else []) + [str(root)]
        r = run_trisift(args, cwd=tmp_path, timeout=30)
        assert_exit(r, "error")
        assert str(idx) in r.err, r.describe()
        assert first.alive()
        assert json.loads((idx / DISCOVERY_FILE).read_text())["pid"] == first.proc.pid
        st = rpc_status(first.port)
        assert st["indexing"] is False and st["hidden_complete"] is True
        assert row_files(first.search("alpha")) == {"a.txt"}

