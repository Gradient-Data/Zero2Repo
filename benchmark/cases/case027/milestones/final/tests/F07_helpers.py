# feature: F07
"""Helpers for the indexed-search suite.

* :func:`read_stats` reads the labelled fields of the statistics report.
* :class:`NoWatchServer` keeps a ``trisift serve --no-watch`` running and waits
  until its status reports indexing complete and coverage complete.
* :class:`TracedIndex` builds an index (or starts such a server) over a tree
  after taking a pristine copy, then adds tracer files to the live tree.  An
  answer that really came from the index cannot contain the tracers; a scan
  of the live tree does.
* :func:`assert_indexed_equals_scan` compares an indexed answer with a
  ``--no-index`` scan of the pristine copy.
"""

from __future__ import annotations

from _helpers import lf_lines
import json
import os
import re
import shutil
import signal
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from _helpers import (
    BackgroundProcess,
    fixture_random,
    RunResult,
    jsonrpc_request,
    line_request,
    run_trisift,
    wait_for_json_file,
    wait_until,
)
from F06_helpers import INDEX_DIR_NAME, build_index

__all__ = [
    "STATS_SCAN",
    "STATS_LOCAL",
    "STATS_SERVER",
    "STATS_INDEX_COUNTS",
    "NO_NARROWING",
    "LISTING_STATS",
    "NO_INDEX_WARNING",
    "BUILD_HINT",
    "COVERAGE_WARNING",
    "FALLBACK_NOTICE",
    "read_stats",
    "listing_path",
    "NoWatchServer",
    "rpc_status",
    "TracedIndex",
    "tracer_name",
    "assert_indexed_equals_scan",
    "normalise_json",
    "SERVER_JSON_GAPS",
    "wide_tree",
    "free_port",
]

# Short labels and independently stated numeric fragments; intervening prose is free.
STATS_SCAN = re.compile(r"\bBrute-force search completed\b")
STATS_LOCAL = re.compile(r"(?<!Brute-force )\bSearch completed\b")
STATS_SERVER = re.compile(r"\(via server\)")
MATCH_COUNTS = re.compile(r"(?P<matches>[0-9]+) matches \((?P<lines>[0-9]+) matched lines\)")
ELAPSED_MS = re.compile(r"(?<![\w.])([0-9]+(?:\.[0-9]+)?)ms\b")
STATS_INDEX_COUNTS = re.compile(
    r"\(candidates: (?P<cand>[0-9]+)/(?P<n1>[0-9]+); raw candidates: (?P<raw>[0-9]+)/(?P<n2>[0-9]+)\)$")
NO_NARROWING = "(no index narrowing)"
LISTING_STATS = re.compile(r"\(via (?P<via>server|local index|filesystem walk)\)")
NO_INDEX_WARNING = re.compile(r"^warning:")
BUILD_HINT = "trisift index"
COVERAGE_WARNING = re.compile(r"^warning:")
FALLBACK_NOTICE = re.compile(r"^Server unavailable\b")


def read_stats(result: RunResult) -> dict:
    lines = lf_lines(result.err)
    found = []
    for line in lines:
        if STATS_SERVER.search(line):
            found.append(("server", line))
        elif STATS_SCAN.search(line):
            found.append(("scan", line))
        elif STATS_LOCAL.search(line):
            found.append(("local", line))
    assert len(found) == 1, result.describe()
    path, line = found[0]
    m = MATCH_COUNTS.search(line)
    assert m and ELAPSED_MS.search(line), result.describe()
    if path == "scan":
        assert re.search(r"[0-9]+ files?\b", line), result.describe()
    out = dict(path=path, matches=int(m['matches']), matched_lines=int(m['lines']),
               raw=None, candidates=None, indexed=None, no_narrowing=NO_NARROWING in result.err)
    if path != "scan":
        counts = [c for c in (STATS_INDEX_COUNTS.search(l) for l in lines) if c]
        assert len(counts) == 1, result.describe()
        c = counts[0]
        out.update(raw=int(c['raw']), candidates=int(c['cand']), indexed=int(c['n1']), raw_indexed=int(c['n2']))
    return out


def listing_path(result: RunResult) -> str:
    lines = [l for l in lf_lines(result.err) if LISTING_STATS.search(l)]
    assert len(lines) == 1 and ELAPSED_MS.search(lines[0]), result.describe()
    via = LISTING_STATS.search(lines[0])['via']
    return {"server": "server", "local index": "local", "filesystem walk": "walk"}[via]


def rpc_status(port: int) -> dict:
    """Send the status method and return its ``result`` object (fails on an error reply)."""
    reply = line_request(port, jsonrpc_request("status"))
    assert "result" in reply, f"status returned {reply!r}"
    return reply["result"]


class NoWatchServer:
    """``trisift serve --no-watch <root>`` kept running for a test.

    ``start(ready=True)`` waits for the discovery record and, with ``ready``,
    until status reports indexing complete and hidden coverage complete.
    Stopped with SIGINT on exit; a server that died early raises.
    """

    def __init__(self, root, extra: Sequence[str] = (), index_path=None, timeout: float = 120.0):
        self.root = Path(root)
        self.index_dir = Path(index_path) if index_path is not None else self.root / INDEX_DIR_NAME
        args = ["serve", "--no-watch"]
        if index_path is not None:
            args += ["--index-path", os.fspath(index_path)]
        self.proc = BackgroundProcess(args + list(extra) + [os.fspath(self.root)], cwd=self.root)
        self.timeout = timeout
        self.port: Optional[int] = None

    def start(self, ready: bool = True) -> "NoWatchServer":
        self.proc.start()
        rec = wait_for_json_file(self.index_dir / "serve.json", timeout=self.timeout, process=self.proc)
        self.port = int(rec["port"])
        if ready:
            self.wait_ready()
        return self

    def status(self) -> dict:
        return rpc_status(self.port)

    def wait_ready(self) -> dict:
        def ready():
            s = self.status()
            return s if (s["indexing"] is False and s["hidden_complete"] is True) else None
        return wait_until(ready, timeout=self.timeout, interval=0.1, process=self.proc,
                          message="server never reported indexing and coverage complete",
                          retry_on=(OSError, ValueError))

    def wait_reconciled(self) -> dict:
        """Wait until a reconciliation has completed and none is running.

        Readiness says the server answers; it does not say the server has caught up with
        changes made while no server ran. The startup reconciliation does that, and status
        reports its completion through the last reconciliation duration.
        """
        def reconciled():
            s = self.status()
            return s if (s["last_reconcile_duration_ms"] is not None and s["reconcile_running"] is False) else None
        return wait_until(reconciled, timeout=self.timeout, interval=0.1, process=self.proc,
                          message="server never reported a completed reconciliation",
                          retry_on=(OSError, ValueError))

    def stop(self) -> RunResult:
        return self.proc.stop(signal.SIGINT)

    def __enter__(self) -> "NoWatchServer":
        try:
            return self.start()
        except BaseException:
            if self.proc.proc is not None and self.proc.result is None:
                self.proc.stop(signal.SIGKILL)
            raise

    def __exit__(self, exc_type, exc, tb) -> None:
        self.proc.__exit__(exc_type, exc, tb)


def tracer_name(rel: str) -> str:
    """Name of the tracer twin of ``rel``: same directory and extension."""
    d, base = os.path.split(rel)
    stem, ext = os.path.splitext(base)
    return os.path.join(d, f"{stem}_trc{ext}") if d else f"{stem}_trc{ext}"


class TracedIndex:
    """An indexed tree whose live content has moved on since the index was made.

    ``TracedIndex(tmp_path, files, mode)`` writes ``files`` under
    ``tmp_path/live/<name>`` and an identical pristine copy under
    ``tmp_path/pristine/<name>``; then builds the index (``mode='local'``) or
    starts a ready ``--no-watch`` server (``mode='server'``) over the live
    tree; then writes, next to every fixture file that has text content, a
    tracer twin with the same content (and ``extra_tracers``).  The pristine
    copy never gets tracers.  Use as a context manager.
    """

    def __init__(self, tmp_path, files: Dict[str, bytes], mode: str, name: str = "tree",
                 build_args: Sequence[str] = (), extra_tracers: Optional[Dict[str, bytes]] = None,
                 setup=None):
        from _helpers import make_tree
        assert mode in ("local", "server")
        self.mode = mode
        self.live = Path(tmp_path) / "live" / name
        self.pristine = Path(tmp_path) / "pristine" / name
        for base in (self.live, self.pristine):
            make_tree(base, files)
            if setup is not None:
                setup(base)
        self.files = dict(files)
        self.build_args = list(build_args)
        self.extra_tracers = dict(extra_tracers or {})
        self.server: Optional[NoWatchServer] = None
        self.tracers: List[str] = []

    def __enter__(self) -> "TracedIndex":
        if self.mode == "local":
            build_index(self.live, self.build_args)
        else:
            self.server = NoWatchServer(self.live, self.build_args).__enter__()
        tracers = {}
        for rel, data in self.files.items():
            b = data.encode() if isinstance(data, str) else data
            if rel.startswith(".git/") or "/.git/" in rel:
                continue
            tracers[tracer_name(rel)] = b
        tracers.update(self.extra_tracers)
        for rel, b in tracers.items():
            p = self.live / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b)
        self.tracers = sorted(tracers)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.server is not None:
            self.server.__exit__(exc_type, exc, tb)


#: JSON fields the reference server does not reproduce (it reports them as
#: 0); left out of server-path comparisons and reported as a PRD request.
SERVER_JSON_GAPS = ("absolute_offset", "bytes_searched")


def normalise_json(stdout: bytes, drop: Sequence[str] = ()) -> List[dict]:
    """JSON Lines output without timing, the summary's statistics and ``drop`` fields."""
    from F03_helpers import project_json
    result = []
    for line in lf_lines(stdout.decode("utf-8")):
        msg = json.loads(line)
        value = project_json(msg, drop)
        if msg["type"] == "summary":
            value["data"]["stats"].pop("searches", None)
            value["data"]["stats"].pop("bytes_searched", None)
        result.append(value)
    return result


def _comparable(stdout: bytes, ordered: bool, json_mode: bool, drop: Sequence[str] = (), null_filenames=False):
    if json_mode:
        return normalise_json(stdout, drop)
    lines = stdout.decode("utf-8").split("\0")[:-1] if null_filenames else lf_lines(stdout.decode("utf-8"))
    return lines if ordered else sorted(lines)


def assert_indexed_equals_scan(traced: TracedIndex, args: Sequence[str], cwd_rel: str = ".",
                               expect_path: str = "indexed", ordered: Optional[bool] = None,
                               require_live_differs: bool = True) -> RunResult:
    """Run ``args`` over the indexed tree and compare with a pristine scan.

    The indexed run adds ``--stats`` and must report ``expect_path``
    (``local``, ``server`` or ``indexed`` = either).  The scan runs the same
    arguments plus ``--no-index`` in the pristine copy from the same relative
    cwd.  Exit status and stdout must be equal (in order when ``--sort`` or
    ``--sortr`` is among ``args``, else as a multiset of lines; JSON output
    without timing or summary statistics).  With ``require_live_differs``, a
    ``--no-index`` scan of the live tree must differ from the pristine one
    whenever the pristine scan printed anything (the tracers are live).
    Returns the indexed run.
    """
    args = list(args)
    if ordered is None:
        ordered = any(a in ("--sort", "--sortr") or a.startswith("--sort") for a in args)
    json_mode = "--json" in args
    null_filenames = any(a in args for a in ("--null", "-0")) and any(a in args for a in ("-l", "--files-with-matches", "--files-without-match", "--files"))
    idx = run_trisift(["--stats"] + args, cwd=traced.live / cwd_rel)
    ref = run_trisift(["--no-index"] + args, cwd=traced.pristine / cwd_rel)
    st = read_stats(idx)
    if expect_path == "indexed":
        assert st["path"] in ("local", "server"), f"not answered by the index\n{idx.describe()}"
    else:
        assert st["path"] == expect_path, f"answered by {st['path']}, wanted {expect_path}\n{idx.describe()}"
    assert idx.code == ref.code, f"exit differs: indexed\n{idx.describe()}\nscan\n{ref.describe()}"
    drop = SERVER_JSON_GAPS if st["path"] == "server" else ()
    assert _comparable(idx.stdout, ordered, json_mode, drop, null_filenames) == _comparable(ref.stdout, ordered, json_mode, drop, null_filenames), (
        f"indexed answer differs from the scan\nindexed:\n{idx.describe()}\nscan:\n{ref.describe()}")
    for t in traced.tracers:
        assert os.path.basename(t).encode() not in idx.stdout, f"tracer {t} leaked\n{idx.describe()}"
    if require_live_differs and ref.stdout:
        live = run_trisift(["--no-index"] + args, cwd=traced.live / cwd_rel)
        assert _comparable(live.stdout, ordered, json_mode, null_filenames=null_filenames) != _comparable(ref.stdout, ordered, json_mode, null_filenames=null_filenames), (
            f"tracers do not show in a live scan; the probe proves nothing\n{live.describe()}")
    return idx


def wide_tree(root, n_files: int = 1200, per_dir: int = 100, lines: int = 60, seed: int = 7) -> Path:
    """Write a large tree of random hex text so a server's initial build takes a while.

    Callers must still prove, with status before and after the probed
    request, that indexing was incomplete; the size alone proves nothing.
    """
    import random
    rnd = fixture_random(f"wide-tree-{seed}")
    base = Path(root)
    for i in range(n_files):
        d = base / f"w{i // per_dir}"
        if i % per_dir == 0:
            d.mkdir(parents=True, exist_ok=True)
        body = "".join("%x %x %x\n" % (rnd.getrandbits(64), rnd.getrandbits(64), rnd.getrandbits(64))
                       for _ in range(lines))
        (d / f"f{i}.txt").write_text(body)
    return base


@contextmanager
def free_port():
    """Reserve an unlistening loopback port until the caller finishes probing."""
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        yield s.getsockname()[1]
