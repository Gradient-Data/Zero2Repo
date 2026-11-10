# feature: F09
"""Search server: the loopback JSON-RPC protocol."""

from __future__ import annotations

import json
import threading
import time

from _helpers import LineConnection, jsonrpc_request, make_tree, unique_token
from F09_helpers import (
    STATUS_FIELDS,
    ServerProcess,
    rpc_files,
    rpc_ok,
    rpc_reload,
    rpc_search,
    rpc_status,
    row_files,
    wait_ready,
    wide_build_tree,
)

#: JSON-RPC 2.0 standard error codes.
PARSE_ERROR = -32700
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602


def _raw_line(conn: LineConnection, message) -> dict:
    """Send one message and return the single reply line parsed, checking it is one JSON object."""
    conn.send(message)
    line = conn.recv_line()
    doc = json.loads(line)
    assert isinstance(doc, dict) and doc.get("jsonrpc") == "2.0", f"reply is not a JSON-RPC 2.0 object: {line!r}"
    return doc


def _error_code(doc: dict, want_id) -> int:
    assert "error" in doc and "result" not in doc, f"expected an error response: {doc!r}"
    assert doc.get("id") == want_id, f"error response id {doc.get('id')!r} != {want_id!r}"
    err = doc["error"]
    assert isinstance(err, dict) and isinstance(err.get("code"), int) and isinstance(err.get("message"), str), doc
    return err["code"]


# F09.T06
def test_protocol_methods_on_one_connection(tmp_path):
    root = tmp_path / "root"
    tok, other = unique_token(), unique_token()
    make_tree(root, {
        "a.txt": f"zero\n{tok} first\n",
        "sub/b.txt": f"{other} {tok}\n",
        "c.txt": f"{other}\n",
    })
    with ServerProcess(root, ["--no-watch"]) as srv:
        wait_ready(srv)
        with LineConnection(srv.port, timeout=120) as conn:
            # Several requests in turn on one connection, each with its own id.
            for i, (method, params) in enumerate([
                ("search", {"pattern": tok}), ("files", None), ("status", None),
            ], start=11):
                conn.send(jsonrpc_request(method, params, id=i))
                line = conn.recv_line()
                doc = json.loads(line)
                assert doc.get("jsonrpc") == "2.0" and doc.get("id") == i and "result" in doc, line
                if method == "search":
                    rows = doc["result"]["matches"]
                    got = sorted((r["type"], r["file"], r["line"], r["content"]) for r in rows)
                    assert got == [("match", "a.txt", 2, f"{tok} first"),
                                   ("match", "sub/b.txt", 1, f"{other} {tok}")]
                elif method == "files":
                    assert sorted(doc["result"]["files"]) == ["a.txt", "c.txt", "sub/b.txt"]
                else:
                    st = doc["result"]
                    assert all(f in st for f in STATUS_FIELDS), st
                    assert st["num_files"] == 3
                    assert st["indexing"] is False and st["hidden_complete"] is True
            # A string id is echoed too.
            assert rpc_ok(conn, "status", id="s-1")["num_files"] == 3
            # Reload: the new file is absent before, present right after the response.
            new = unique_token()
            (root / "late.txt").write_text(f"{new} {tok}\n")
            (root / "c.txt").unlink()
            assert row_files(rpc_search(conn, new)) == set()
            assert rpc_reload(conn)["status"] == "reloaded"
            assert row_files(rpc_search(conn, new)) == {"late.txt"}
            assert row_files(rpc_search(conn, other)) == {"sub/b.txt"}
            assert sorted(rpc_files(conn)) == ["a.txt", "late.txt", "sub/b.txt"]


# F09.T07
def test_concurrent_clients_get_the_same_answers_as_alone(tmp_path):
    root = tmp_path / "root"
    rels = wide_build_tree(root, n_dirs=10, files_per_dir=40, size=4000)
    toks = [unique_token() for _ in range(4)]
    for i, rel in enumerate(rels):
        if i % 5 == 0:
            with open(root / rel, "a") as f:
                f.write(f"{toks[i % 4]} row {i}\n")
    patterns = toks + ["[a-z]{8} [a-z]{8}"]

    def canon(rows):
        return sorted((r["type"], r["file"], r["line"], r["content"]) for r in rows)

    with ServerProcess(root, ["--no-watch"]) as srv:
        wait_ready(srv)
        alone = {p: canon(rpc_search(srv.port, p)) for p in patterns}
        assert all(alone[t] for t in toks)
        conns = [LineConnection(srv.port, timeout=120) for _ in patterns]
        try:
            # Every connection is open before any request; one request is left
            # in flight on the first connection while the others run.
            conns[0].send(jsonrpc_request("search", {"pattern": patterns[0]}, id=100))
            results = {}
            errors = []

            def run(i):
                try:
                    results[i] = canon(rpc_search(conns[i], patterns[i]))
                except BaseException as exc:  # reported below with its cause
                    errors.append((i, exc))

            threads = [threading.Thread(target=run, args=(i,)) for i in range(1, len(patterns))]
            for t in threads:
                t.start()
            for t in threads:
                t.join(120)
                assert not t.is_alive(), "a concurrent search did not answer within 120s"
            assert not errors, errors
            first = json.loads(conns[0].recv_line())
            assert first.get("id") == 100 and "result" in first, first
            results[0] = canon(first["result"]["matches"])
        finally:
            for c in conns:
                c.close()
        for i, p in enumerate(patterns):
            assert results[i] == alone[p], p


# F09.T19
def test_protocol_errors_keep_the_connection_usable(tmp_path):
    root = tmp_path / "root"
    make_tree(root, {"a.txt": "alpha\n"})
    with ServerProcess(root, ["--no-watch"]) as srv:
        wait_ready(srv)
        with LineConnection(srv.port, timeout=60) as conn:
            cases = [
                (b"this is not json", None, PARSE_ERROR),
                ('{"jsonrpc":"2.0","id":5,"method":', None, PARSE_ERROR),
                (jsonrpc_request("no_such_method", None, id=6), 6, METHOD_NOT_FOUND),
                (jsonrpc_request("search", {"pattern": "(unclosed"}, id=7), 7, INVALID_PARAMS),
                (jsonrpc_request("search", {"pattern": "a", "glob": ["[z-a]"]}, id=8), 8, INVALID_PARAMS),
                (jsonrpc_request("search", {"pattern": "a", "types": ["nosuchtypename"]}, id=9), 9, INVALID_PARAMS),
            ]
            for n, (msg, want_id, want_code) in enumerate(cases):
                doc = _raw_line(conn, msg)
                assert _error_code(doc, want_id) == want_code, (msg, doc)
                # The same connection still answers a valid request.
                st = rpc_ok(conn, "status", id=1000 + n)
                assert st["num_files"] == 1


# F09.T19
def test_search_and_files_during_initial_build_get_errors_not_partial_rows(tmp_path):
    root = tmp_path / "wide"
    rels = wide_build_tree(root, n_dirs=12, files_per_dir=100, size=6000)
    tok = unique_token()
    for rel in rels[::500]:
        with open(root / rel, "a") as f:
            f.write(f"{tok}\n")
    from F00_observations import ReadGate
    with ReadGate(root / rels[-1]) as gate, ServerProcess(root, ["--no-watch", "--max-cpu", "1"]) as srv:
        with LineConnection(srv.port, timeout=120) as conn:
            try:
                gate.wait_blocked(srv.proc)
                before = rpc_status(conn)
                assert before["indexing"] is True, f"build window not observed: {before}"
                s_doc = _raw_line(conn, jsonrpc_request("search", {"pattern": tok}, id=21))
                f_doc = _raw_line(conn, jsonrpc_request("files", None, id=22))
                after = rpc_status(conn)
                assert after["indexing"] is True, f"build finished before the probes returned: {after}"
                for doc, want_id in ((s_doc, 21), (f_doc, 22)):
                    assert "result" not in doc, f"answer with rows during the build: {str(doc)[:500]}"
                    _error_code(doc, want_id)
            finally:
                gate.release()
            # The connection is still usable, and after readiness the answers are full.
            deadline = time.monotonic() + 300
            while True:
                st = rpc_status(conn)
                if not st["indexing"] and st["hidden_complete"]:
                    break
                assert time.monotonic() < deadline, st
                time.sleep(0.05)
            assert row_files(rpc_search(conn, tok)) == set(rels[::500])
            assert len(rpc_files(conn)) == len(rels)


# F09.T06 regression — FP-09.04, FP-02.01, FP-02.06, FP-02.08, FP-04.06

def test_rpc_search_parameters_and_regex_results(tmp_path):
    root = make_tree(tmp_path / "w", {"a.txt": "prefix\nORCHARD42\nsuffix\n", "sub/b.rs": "orchard7\n",
                                     "c.md": "meadow9\n"})
    with ServerProcess(root, ["--no-watch"]) as srv:
        wait_ready(srv)
        with LineConnection(srv.port) as conn:
            rows = rpc_search(conn, r"orchard[0-9]+", case_insensitive=True)
            assert sorted((r["file"], r["content"]) for r in rows) == [("a.txt", "ORCHARD42"), ("sub/b.rs", "orchard7")]
            assert row_files(rpc_search(conn, r"[a-z]+[0-9]", glob=["*.md"])) == {"c.md"}
            assert row_files(rpc_search(conn, "orchard", types=["rust"])) == {"sub/b.rs"}
            assert row_files(rpc_search(conn, "missing", extra_patterns=["meadow9"])) == {"c.md"}
            rows = rpc_search(conn, "ORCHARD42", before_context=1, after_context=1)
            assert [(r["type"], r["line"], r["content"]) for r in rows] == [
                ("context", 1, "prefix"), ("match", 2, "ORCHARD42"), ("context", 3, "suffix")]
