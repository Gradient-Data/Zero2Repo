# feature: F09
"""Helpers for the search-server suites.

Everything here drives the product from outside: it starts ``trisift serve``
as a background process, reads the discovery record the server writes, and
talks to the server's loopback JSON-RPC endpoint one line per message.  The
names below are the product's shell (subcommand, file names inside the index
directory, protocol method and field names, fixed stderr labels); no expected
result of any search lives here.
"""

from __future__ import annotations

from _helpers import lf_lines
import json
import os
import random
import shutil
import signal
import string
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from _helpers import (
    BackgroundProcess,
    fixture_random,
    LineConnection,
    ProcessExited,
    WaitTimeout,
    jsonrpc_request,
    make_tree,
    pid_alive,
    run_trisift,
    trisift_binary,
    wait_for_tcp,
    wait_until,
)

__all__ = [
    "INDEX_DIR_NAME",
    "DISCOVERY_FILE",
    "LOCK_FILE",
    "STATUS_FIELDS",
    "ServerProcess",
    "rpc_ok",
    "rpc_status",
    "rpc_search",
    "rpc_files",
    "rpc_reload",
    "row_files",
    "wait_status",
    "wait_ready",
    "wait_reflected",
    "wide_build_tree",
    "token_text",
    "cli_listing",
    "dac_drop_prefix",
    "probe_denied",
]

#: Default index directory name inside the indexed root.
INDEX_DIR_NAME = ".trisift"
#: Discovery record a running server writes into its index directory.
DISCOVERY_FILE = "serve.json"
#: Lock file a running server holds in its index directory.
LOCK_FILE = "serve.lock"

#: Fields of the ``status`` method's result object.
STATUS_FIELDS = (
    "num_files",
    "watcher_active",
    "watch_mode_active",
    "watch_mode_requested",
    "watch_fallback_reason",
    "watch_budget",
    "poll_interval_secs",
    "reconcile_running",
    "last_reconcile_at",
    "reconcile_pending",
    "reconcile_overdue",
    "last_reconcile_duration_ms",
    "last_reconcile_error",
    "indexing",
    "index_progress",
    "index_total",
    "hidden_complete",
)


# ---------------------------------------------------------------------------
# Server process
# ---------------------------------------------------------------------------


def dac_drop_prefix() -> List[str]:
    """Return the argv prefix that runs a process without file-permission overrides.

    As root, mode bits are not enforced, so a test that needs the *product*
    to be denied access runs it under ``setpriv`` with ``CAP_DAC_OVERRIDE``
    and ``CAP_DAC_READ_SEARCH`` removed from the bounding set.  As any other
    user the prefix is empty.  Raises ``RuntimeError`` when root has no
    ``setpriv``: the precondition cannot be built and the test must fail.
    """
    if os.geteuid() != 0:
        return []
    exe = shutil.which("setpriv")
    if exe is None:
        raise RuntimeError("running as root without setpriv: cannot deny file access to the product")
    return [exe, "--bounding-set=-dac_override,-dac_read_search", "--"]


def probe_denied(path, *, write: bool = False) -> None:
    """Prove a process started like the product is denied access to ``path``.

    Lists a directory (or, with ``write``, creates an entry in it) from a
    child process started with :func:`dac_drop_prefix`.  Raises
    ``AssertionError`` when the access succeeds, so a test never runs on a
    precondition that does not hold.
    """
    p = os.fspath(path)
    code = (
        "import os,sys\n"
        "p=sys.argv[1]\n"
        + ("open(os.path.join(p,'.probe-%d'%os.getpid()),'w').close()\n" if write else "os.listdir(p)\n")
    )
    import subprocess

    proc = subprocess.run(
        [*dac_drop_prefix(), sys.executable, "-c", code, p],
        capture_output=True, stdin=subprocess.DEVNULL, timeout=60,
    )
    assert proc.returncode != 0 and b"PermissionError" in proc.stderr, (
        f"{'write' if write else 'read'} access to {p} is not denied "
        f"(euid={os.geteuid()}, rc={proc.returncode}, stderr={proc.stderr[-400:]!r})"
    )


class ServerProcess:
    """``trisift serve`` running in the background for the duration of a ``with`` block.

    ``args`` are the serve options; the root is appended last.  The server
    is ready for connections once its discovery record at
    ``index_dir/serve.json`` names this child's pid and its port accepts a
    TCP connection.  Leaving the block sends SIGINT and waits for exit.
    ``drop_dac`` runs the server under :func:`dac_drop_prefix`.
    """

    def __init__(
        self,
        root,
        args: Sequence[str] = (),
        *,
        index_dir=None,
        cwd=None,
        drop_dac: bool = False,
        start_timeout: float = 60.0,
        env: Optional[Mapping[str, str]] = None,
    ):
        self.root = Path(root)
        self.index_dir = Path(index_dir) if index_dir is not None else self.root / INDEX_DIR_NAME
        self.args = list(args)
        self.cwd = Path(cwd) if cwd is not None else self.root.parent
        self.start_timeout = start_timeout
        prefix = dac_drop_prefix() if drop_dac else []
        argv = ["serve", *self.args, str(self.root)]
        if prefix:
            self.proc = BackgroundProcess(
                prefix[1:] + [trisift_binary(), *argv], cwd=self.cwd, env=env, binary=prefix[0],
            )
        else:
            self.proc = BackgroundProcess(argv, cwd=self.cwd, env=env)
        self.pid: Optional[int] = None
        self.port: Optional[int] = None
        self.record: Optional[dict] = None

    def start(self) -> "ServerProcess":
        self.proc.start()
        record_path = self.index_dir / DISCOVERY_FILE

        def own_record():
            try:
                doc = json.loads(record_path.read_bytes())
            except (FileNotFoundError, ValueError):
                return None
            if isinstance(doc, dict) and doc.get("pid") == self.proc.pid:
                return (doc,)
            return None

        self.record = wait_until(
            own_record, timeout=self.start_timeout, process=self.proc,
            message=f"no discovery record naming pid {self.proc.pid} at {record_path}",
        )[0]
        self.pid = self.record["pid"]
        self.port = self.record["port"]
        assert isinstance(self.port, int) and 0 < self.port < 65536, f"bad port in {self.record}"
        wait_for_tcp(self.port, timeout=self.start_timeout, process=self.proc)
        return self

    def stop(self):
        """Interrupt the server (SIGINT) and return its finished RunResult."""
        return self.proc.stop(signal.SIGINT)

    def alive(self) -> bool:
        return self.proc.poll() is None

    def __enter__(self) -> "ServerProcess":
        try:
            return self.start()
        except BaseException:
            self.proc.__exit__(None, None, None)
            raise

    def __exit__(self, exc_type, exc, tb) -> None:
        self.proc.__exit__(exc_type, exc, tb)

    # Convenience wrappers ------------------------------------------------
    def status(self) -> dict:
        return rpc_status(self.port)

    def search(self, pattern: str, **params) -> List[dict]:
        return rpc_search(self.port, pattern, **params)


# ---------------------------------------------------------------------------
# JSON-RPC
# ---------------------------------------------------------------------------


def _envelope_ok(resp: Any, want_id) -> None:
    assert isinstance(resp, dict), f"response is not a JSON object: {resp!r}"
    assert resp.get("jsonrpc") == "2.0", f"response lacks jsonrpc 2.0: {resp!r}"
    assert resp.get("id") == want_id, f"response id {resp.get('id')!r} != request id {want_id!r}: {resp!r}"


def rpc_ok(conn_or_port, method: str, params: Any = None, id=1) -> Any:
    """Send one request and return its ``result``; fail on an error response.

    ``conn_or_port`` is an open :class:`LineConnection` or a port (a fresh
    connection is used).  The envelope (``jsonrpc`` and echoed ``id``) is
    checked; an ``error`` member fails the test with the whole response.
    """
    req = jsonrpc_request(method, params, id=id)
    if isinstance(conn_or_port, LineConnection):
        resp = conn_or_port.request(req)
    else:
        with LineConnection(conn_or_port, timeout=120) as conn:
            resp = conn.request(req)
    _envelope_ok(resp, id)
    assert "error" not in resp and "result" in resp, f"{method} failed: {resp!r}"
    return resp["result"]


def rpc_status(conn_or_port) -> dict:
    """Return the ``status`` result object, checking every documented field is present."""
    result = rpc_ok(conn_or_port, "status")
    missing = [f for f in STATUS_FIELDS if f not in result]
    assert not missing, f"status result lacks {missing}: {result!r}"
    return result


def rpc_search(conn_or_port, pattern: str, **params) -> List[dict]:
    """Return the ``matches`` rows of a ``search`` request for ``pattern``."""
    result = rpc_ok(conn_or_port, "search", {"pattern": pattern, **params})
    rows = result.get("matches")
    assert isinstance(rows, list), f"search result has no matches list: {result!r}"
    return rows


def rpc_files(conn_or_port, **params) -> List[str]:
    """Return the path list of a ``files`` request."""
    result = rpc_ok(conn_or_port, "files", params or None)
    files = result.get("files")
    assert isinstance(files, list) and all(isinstance(f, str) for f in files), (
        f"files result has no list of paths: {result!r}"
    )
    return files


def rpc_reload(conn_or_port) -> Any:
    """Send ``reload`` and return its result once the server responds."""
    return rpc_ok(conn_or_port, "reload")


def row_files(rows: Iterable[dict], kind: str = "match") -> set:
    """Return the set of ``file`` values of rows whose ``type`` is ``kind``."""
    out = set()
    for row in rows:
        assert isinstance(row, dict) and "type" in row and "file" in row, f"malformed row {row!r}"
        if row["type"] == kind:
            out.add(row["file"])
    return out


def wait_status(port: int, predicate: Callable[[dict], bool], *, timeout: float,
                process: Optional[ServerProcess] = None, message: str = "status condition") -> dict:
    """Poll ``status`` until ``predicate(result)`` holds; return that result."""
    last: Dict[str, Any] = {}

    def probe():
        s = rpc_status(port)
        last["s"] = s
        return (s,) if predicate(s) else None

    try:
        return wait_until(probe, timeout=timeout, interval=0.05, message=message,
                          process=process.proc if process else None)[0]
    except WaitTimeout as exc:
        raise AssertionError(f"{message} not reached in {timeout}s; last status={last.get('s')!r}") from exc


def wait_ready(server: ServerProcess, timeout: float = 120.0) -> dict:
    """Wait until status reports indexing complete and coverage complete."""
    return wait_status(
        server.port, lambda s: s["indexing"] is False and s["hidden_complete"] is True,
        timeout=timeout, process=server, message="indexing complete and coverage complete",
    )


def wait_reconciled(server: ServerProcess, since: float, timeout: float = 120.0) -> dict:
    """Wait until the reconciliation fields report a successful reconciliation completed after ``since``."""
    floor = int(since)
    return wait_status(
        server.port, lambda s: s["reconcile_running"] is False and s["last_reconcile_error"] is None
        and isinstance(s["last_reconcile_at"], int) and s["last_reconcile_at"] >= floor
        and s["last_reconcile_duration_ms"] is not None,
        timeout=timeout, process=server, message="startup reconciliation completed successfully",
    )


def wait_reflected(check: Callable[[], bool], *, timeout: float, what: str,
                   server: Optional[ServerProcess] = None) -> float:
    """Poll ``check`` until it returns True; return the seconds it took.

    Fails the test with ``what`` when ``timeout`` passes first.
    """
    t0 = time.monotonic()
    while True:
        if server is not None and not server.alive():
            raise ProcessExited(server.proc.argv, server.proc.poll(), b"", server.proc.read_stderr())
        if check():
            return time.monotonic() - t0
        if time.monotonic() - t0 > timeout:
            raise AssertionError(f"{what}: not reflected within {timeout}s")
        time.sleep(0.05)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_LETTERS = string.ascii_lowercase


def token_text(rng: random.Random, size: int) -> bytes:
    """Return ``size`` bytes of random lowercase words separated by spaces and newlines."""
    out = bytearray()
    while len(out) < size:
        word = "".join(rng.choice(_LETTERS) for _ in range(rng.randint(3, 9)))
        out += word.encode("ascii")
        out += b"\n" if rng.random() < 0.08 else b" "
    out = out[:size]
    out[-1:] = b"\n"
    return bytes(out)


def wide_build_tree(root, n_dirs: int = 120, files_per_dir: int = 120, size: int = 5000) -> List[str]:
    """Write a large tree of text files whose initial build takes a visible time.

    Content is random lowercase text (no NUL bytes, every file far below any
    size cap), so every file is an admitted text file.  Returns the relative
    paths written.  Used with a low CPU budget on ``serve`` so the build
    window is wide; callers still prove the window with status calls.
    """
    rng = fixture_random("wide-build")
    # A pool of random lines keeps generation fast while files stay distinct.
    pool = [token_text(rng, 400) for _ in range(400)]
    base = Path(root)
    rels = []
    for d in range(n_dirs):
        dd = base / f"w{d:03d}"
        dd.mkdir(parents=True, exist_ok=True)
        for f in range(files_per_dir):
            rel = f"w{d:03d}/f{f:03d}.txt"
            chunks = []
            total = 0
            while total < size:
                c = pool[rng.randrange(len(pool))]
                chunks.append(c)
                total += len(c)
            (base / rel).write_bytes(b"".join(chunks)[:size - 1] + b"\n")
            rels.append(rel)
    return rels


def cli_listing(args: Sequence[str], cwd, env: Optional[Mapping[str, str]] = None) -> tuple:
    """Run a files-with-matches search and return ``(RunResult, set of printed paths)``.

    The exit status must be match or no match; anything else fails.
    """
    r = run_trisift(["-l", *args], cwd=cwd, env=env, timeout=120)
    assert r.code in (0, 1), f"search failed\n{r.describe()}"
    lines = lf_lines(r.out)
    return r, set(lines)


def wait_poll_completion(server, changed_at, *, check=None, what="poll refresh", count=1):
    """Observe completed passes using their own reported duration, then check freshness.

    Unix timestamps have whole-second precision. Only a pass whose earliest
    possible start is after the completed disk change establishes the bound.
    The watchdog is an execution limit, not a substitute reconciliation time.
    Consecutive observed completions also enforce the PRD's polling cadence.
    """
    from _helpers import DEFAULT_TIMEOUT
    deadline = time.monotonic() + DEFAULT_TIMEOUT
    previous = None
    completed = []
    last_probe = time.monotonic()
    while len(completed) < count:
        server.proc.raise_if_exited()
        st = rpc_status(server.port)
        now = time.monotonic()
        at, duration = st["last_reconcile_at"], st["last_reconcile_duration_ms"]
        assert st["last_reconcile_error"] is None, st
        if at is not None and duration is not None:
            assert isinstance(at, int) and isinstance(duration, int) and duration >= 0, st
            if previous is not None and at != previous:
                # Fractional timestamp truncation plus measured sampling delay.
                assert at - previous <= st["poll_interval_secs"] + duration / 1000 + 1 + (now - last_probe) + 1.5, st
            if at - duration / 1000 - .001 >= changed_at and at != previous:
                if check is not None:
                    assert check(), f"{what}: not reflected after a reconciliation begun after the change: {st}"
                completed.append(st)
            previous = at
        assert now < deadline, f"{what}: no completed post-change reconciliation within execution limit; last={st}"
        last_probe = now
        if len(completed) < count:
            time.sleep(.05)
    return completed
