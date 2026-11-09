"""Supply store, proxy and preparation, checked against a fake upstream.

The fake upstream serves every hostname from one local server (plain HTTP and
TLS with certificates from its own test CA) and counts the requests it gets,
so "fetched once" is observed at the source rather than inferred.
"""

from __future__ import annotations

import http.client
import shutil
import socket
import ssl
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from cbrun import supply
from cbrun.denylist import CODE_HOST_BLOCK_HOSTS
from cbrun.supply_ca import ProxyCA
from cbrun.supply_proxy import CA_HOST, Entry, ProxyHub, SupplyViolation
from cbrun.supply_store import Store, StoreError

pytestmark = pytest.mark.skipif(shutil.which("openssl") is None, reason="needs openssl")


class Origin:
    """One local server answering for every hostname, HTTP and HTTPS."""

    def __init__(self, tmp: Path) -> None:
        self.files: dict[str, bytes] = {}
        # Replies to cut off halfway, by key, and how many more times to do so.
        self.cut_off: dict[str, int] = {}
        self.stream_chunks: list[bytes] = []
        self.stream_delay = 0.0
        self.counts: dict[str, int] = {}
        self.lock = threading.Lock()
        self.ca = ProxyCA(tmp / "origin-ca")
        origin = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args) -> None:
                pass

            def _count(self) -> str:
                key = f"{self.headers.get('Host', '').split(':')[0]}{self.path}"
                with origin.lock:
                    origin.counts[key] = origin.counts.get(key, 0) + 1
                return key

            def do_POST(self) -> None:  # noqa: N802 - http.server hook
                # A git-like endpoint answers per request body; any other POST is served like a GET.
                if not self.path.endswith("/git-upload-pack"):
                    return self.do_GET()
                key = self._count()
                sent = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                body = b"pack for " + sent
                self.send_response(200)
                self.send_header("Content-Type", "application/x-git-upload-pack-result")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802 - http.server hook
                key = self._count()
                if self.path == "/stream":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    for chunk in origin.stream_chunks:
                        self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                        self.wfile.flush()
                        time.sleep(origin.stream_delay)
                    self.wfile.write(b"0\r\n\r\n")
                    return
                body = origin.files.get(key)
                if body is None:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                with origin.lock:
                    cut = origin.cut_off.get(key, 0) > 0
                    if cut:
                        origin.cut_off[key] -= 1
                if cut:
                    self.wfile.write(body[: len(body) // 2])
                    self.close_connection = True
                    return
                self.wfile.write(body)


        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.https = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.sni_callback = lambda sock, name, _ctx: setattr(
            sock, "context", origin.ca.server_context(name or "localhost")
        )
        ctx.load_cert_chain(str(self.ca._host_cert("localhost")), str(self.ca.host_key))
        self.https.socket = ctx.wrap_socket(self.https.socket, server_side=True)
        for server in (self.http, self.https):
            threading.Thread(target=server.serve_forever, daemon=True).start()

    def connect(self, host: str, port: int, tls: bool) -> socket.socket:
        """Upstream connector for the proxy: every host resolves to this origin.

        Port 443 reaches the TLS server; *tls* says whether the proxy itself
        speaks TLS (it does not for a tunnel, where the client does).
        """
        target = self.https if port == 443 else self.http
        sock = socket.create_connection(("127.0.0.1", target.server_address[1]), timeout=10)
        if tls:
            ctx = ssl.create_default_context(cafile=str(self.ca.ca_cert))
            sock = ctx.wrap_socket(sock, server_hostname=host)
        return sock

    def count(self, host: str, path: str) -> int:
        return self.counts.get(f"{host}{path}", 0)

    def close(self) -> None:
        for server in (self.http, self.https):
            server.shutdown()
            server.server_close()


@pytest.fixture()
def origin(tmp_path: Path):
    server = Origin(tmp_path)
    yield server
    server.close()


@pytest.fixture()
def hub(tmp_path: Path, origin: Origin) -> ProxyHub:
    return ProxyHub(Store(tmp_path / "store"), connect=origin.connect)


def _get_http(port: int, url: str, accept: str = "") -> tuple[int, bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Accept": accept} if accept else {}
    conn.request("GET", url, headers=headers)
    resp = conn.getresponse()
    return resp.status, resp.read()


def _get_https(hub: ProxyHub, port: int, host: str, path: str) -> tuple[int, bytes]:
    ctx = ssl.create_default_context(cafile=str(hub.ca.ca_cert))
    conn = http.client.HTTPSConnection("127.0.0.1", port, timeout=10, context=ctx)
    conn.set_tunnel(host, 443)
    conn.request("GET", path)
    resp = conn.getresponse()
    return resp.status, resp.read()


def _entry_for(hub: ProxyHub, url: str, body: bytes) -> Entry:
    import hashlib

    return Entry("GET", url, "", 200, hashlib.sha256(body).hexdigest(), len(body))


# Fetch once ----------------------------------------------------------------


def test_two_cases_locking_the_same_file_fetch_it_from_upstream_once(origin, hub) -> None:
    body = b"go toolchain" * 1000
    origin.files["go.dev/dl/go.tar.gz"] = body
    url = "https://go.dev/dl/go.tar.gz"
    case_a = [_entry_for(hub, url, body)]
    case_b = [_entry_for(hub, url, body)]

    # Two runs prepare at the same time, then a third prepares again later.
    threads = [
        threading.Thread(target=supply._fetch_all, args=(hub.store, hub, lock))
        for lock in (case_a, case_b)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    fetched, errors = supply._fetch_all(hub.store, hub, case_a + case_b)

    assert errors == [] and fetched == 0
    assert origin.count("go.dev", "/dl/go.tar.gz") == 1
    assert hub.store.has(case_a[0].sha256, len(body))


def test_recording_two_cases_fetches_a_fixed_file_once(origin, hub) -> None:
    origin.files["files.pythonhosted.org/packages/aa/pytest.whl"] = b"wheel"
    for owner in ("case001", "case002"):
        session = hub.session("record", owner)
        try:
            status, body = _get_https(hub, session.port, "files.pythonhosted.org", "/packages/aa/pytest.whl")
        finally:
            session.close()
        assert (status, body) == (200, b"wheel")
        assert [e.url for e in session.recorded.values()] == [
            "https://files.pythonhosted.org/packages/aa/pytest.whl"
        ]
    assert origin.count("files.pythonhosted.org", "/packages/aa/pytest.whl") == 1


def test_a_prepared_file_is_installed_without_contacting_upstream(origin, hub) -> None:
    origin.files["archive.ubuntu.com/ubuntu/pool/main/p/pip.deb"] = b"deb"
    url = "http://archive.ubuntu.com/ubuntu/pool/main/p/pip.deb"
    record = hub.session("record", "case001")
    try:
        assert _get_http(record.port, url) == (200, b"deb")
    finally:
        record.close()
    assert origin.count("archive.ubuntu.com", "/ubuntu/pool/main/p/pip.deb") == 1

    for _ in range(2):
        with hub.session("locked", "case001", entries=record.recorded.values()) as locked:
            assert _get_http(locked.port, url) == (200, b"deb")
            locked.raise_for_violations()
    assert origin.count("archive.ubuntu.com", "/ubuntu/pool/main/p/pip.deb") == 1


def test_indexes_are_locked_per_accept_header(origin, hub) -> None:
    origin.files["pypi.org/simple/pytest/"] = b"index"
    record = hub.session("record", "case001")
    try:
        status, _ = _get_https_accept(hub, record.port, "pypi.org", "/simple/pytest/", "application/json")
    finally:
        record.close()
    assert status == 200
    with hub.session("locked", "case001", entries=record.recorded.values()) as locked:
        status, _ = _get_https_accept(hub, locked.port, "pypi.org", "/simple/pytest/", "text/html")
        assert status == 403
        with pytest.raises(SupplyViolation, match="recorded with Accept 'application/json'"):
            locked.raise_for_violations()


def _get_https_accept(hub, port, host, path, accept):
    ctx = ssl.create_default_context(cafile=str(hub.ca.ca_cert))
    conn = http.client.HTTPSConnection("127.0.0.1", port, timeout=10, context=ctx)
    conn.set_tunnel(host, 443)
    conn.request("GET", path, headers={"Accept": accept})
    resp = conn.getresponse()
    return resp.status, resp.read()


# Locked mode ---------------------------------------------------------------


def test_install_asking_for_a_url_outside_the_lock_fails_naming_it(origin, hub) -> None:
    origin.files["registry.npmjs.org/left-pad"] = b"{}"
    with hub.session("locked", "case012", entries=()) as session:
        status, _ = _get_https(hub, session.port, "registry.npmjs.org", "/left-pad")
        assert status == 403
        with pytest.raises(SupplyViolation) as info:
            session.raise_for_violations()
    message = str(info.value)
    assert "https://registry.npmjs.org/left-pad" in message
    assert "case012" in message
    assert origin.count("registry.npmjs.org", "/left-pad") == 0


def test_a_resized_stored_file_is_reported_with_its_url(origin, hub) -> None:
    body = b"node tarball"
    url = "https://nodejs.org/dist/v1/node.tar.gz"
    entry = _entry_for(hub, url, body)
    origin.files["nodejs.org/dist/v1/node.tar.gz"] = body
    supply.fetch_entry(hub.store, entry, hub)
    hub.store.blob_path(entry.sha256).write_bytes(b"node")
    with hub.session("locked", "base", entries=[entry]) as session:
        status, _ = _get_https(hub, session.port, "nodejs.org", "/dist/v1/node.tar.gz")
        assert status == 502
        with pytest.raises(SupplyViolation, match=r"nodejs.org/dist/v1/node.tar.gz.*size 4"):
            session.raise_for_violations()


# Cut-off downloads ---------------------------------------------------------


def test_a_cut_off_download_is_retried_until_whole(origin, hub) -> None:
    body = b"go toolchain" * 1000
    origin.files["go.dev/dl/go.tar.gz"] = body
    origin.cut_off["go.dev/dl/go.tar.gz"] = 1
    entry = _entry_for(hub, "https://go.dev/dl/go.tar.gz", body)

    assert supply.fetch_entry(hub.store, entry, hub) is True
    assert origin.count("go.dev", "/dl/go.tar.gz") == 2
    assert hub.store.blob_path(entry.sha256).read_bytes() == body


def test_a_cut_off_reply_is_not_recorded_and_the_client_sees_it(origin, hub) -> None:
    key = "files.pythonhosted.org/packages/aa/pytest.whl"
    url = "/packages/aa/pytest.whl"
    origin.files[key] = b"wheel" * 1000
    origin.cut_off[key] = 1
    session = hub.session("record", "case001")
    try:
        with pytest.raises(http.client.IncompleteRead):
            _get_https(hub, session.port, "files.pythonhosted.org", url)
        assert session.recorded == {}
        assert hub.store.lookup_url(f"https://{key}") is None
        # The client's retry fetches it again and records the whole file.
        assert _get_https(hub, session.port, "files.pythonhosted.org", url) == (200, b"wheel" * 1000)
    finally:
        session.close()
    assert [e.size for e in session.recorded.values()] == [5000]
    assert session.violations == []
    assert origin.count("files.pythonhosted.org", url) == 2


def test_store_rejects_a_download_whose_digest_differs(tmp_path: Path) -> None:
    store = Store(tmp_path / "store")
    with pytest.raises(StoreError, match="sha256"):
        with store.writer(expect_sha256="0" * 64, label="u") as writer:
            writer.write(b"x")
    assert list((tmp_path / "store" / "tmp").iterdir()) == []


# Solve mode ----------------------------------------------------------------


def test_recording_a_declared_file_reads_the_store_and_fetches_it_once(origin, hub) -> None:
    """A checksum-declared file on a code host is fetched once, then read from the store."""
    path = "/repos/o/r/tarball/abc"
    origin.files["api.github.com" + path] = b"tarball"
    url = "https://api.github.com" + path
    for owner in ("case001", "case002"):
        session = hub.session("record", owner, declared_urls=[url])
        try:
            assert _get_https(hub, session.port, "api.github.com", path) == (200, b"tarball")
        finally:
            session.close()
        assert session.violations == []
        assert [e.url for e in session.recorded.values()] == [url]
    assert origin.count("api.github.com", path) == 1


def test_recording_serves_a_seeded_declared_file_without_upstream(origin, hub) -> None:
    import hashlib

    body = b"seeded artifact"
    url = "https://api.github.com/repos/o/r/tarball/def"
    digest = hashlib.sha256(body).hexdigest()
    with hub.store.writer(expect_sha256=digest, expect_size=len(body)) as out:
        out.write(body)
    hub.store.remember_url(url, Entry("GET", url, "", 200, digest, len(body)).to_dict())
    session = hub.session("record", "case001", declared_urls=[url])
    try:
        assert _get_https(hub, session.port, "api.github.com", "/repos/o/r/tarball/def") == (200, body)
    finally:
        session.close()
    assert origin.counts == {}


def test_solve_caches_aliyun_package_files_and_passes_its_indexes_fresh(origin, hub) -> None:
    origin.files["mirrors.aliyun.com/pypi/packages/aa/numpy.whl"] = b"numpy"
    origin.files["mirrors.aliyun.com/pypi/simple/numpy/"] = b"index"
    for owner in ("case001/codex", "case002/codex"):
        with hub.session("solve", owner, block_hosts=CODE_HOST_BLOCK_HOSTS) as session:
            assert _get_https(hub, session.port, "mirrors.aliyun.com", "/pypi/packages/aa/numpy.whl") == (
                200,
                b"numpy",
            )
            assert _get_https(hub, session.port, "mirrors.aliyun.com", "/pypi/simple/numpy/") == (200, b"index")
    assert origin.count("mirrors.aliyun.com", "/pypi/packages/aa/numpy.whl") == 1
    assert origin.count("mirrors.aliyun.com", "/pypi/simple/numpy/") == 2


def test_apt_gets_the_merged_bundle_through_an_extra_config_file(hub) -> None:
    from cbrun.supply_proxy import APT_CONF_NAME, CONTAINER_CA_BUNDLE, CONTAINER_CA_DIR

    with hub.session("record", "case001") as session:
        env = session.container_env()
    assert env["APT_CONFIG"] == f"{CONTAINER_CA_DIR}/{APT_CONF_NAME}"
    text = (hub.ca.mount_dir / APT_CONF_NAME).read_text()
    assert text == f'Acquire::https::CaInfo "{CONTAINER_CA_BUNDLE}";\n'


def test_a_stored_file_is_served_by_byte_range(origin, hub) -> None:
    """Downloaders that fetch large files in parallel ranges get 206 slices of the stored copy."""
    import hashlib

    body = bytes(range(256)) * 40
    url = "https://static.crates.io/crates/big/big-1.0.0.crate"
    digest = hashlib.sha256(body).hexdigest()
    with hub.store.writer(expect_sha256=digest, expect_size=len(body)) as out:
        out.write(body)
    hub.store.remember_url(url, Entry("GET", url, "", 200, digest, len(body)).to_dict())
    session = hub.session("record", "case001")
    try:
        ctx = ssl.create_default_context(cafile=str(hub.ca.ca_cert))

        def get(range_value: str) -> tuple[int, str, bytes]:
            conn = http.client.HTTPSConnection("127.0.0.1", session.port, timeout=10, context=ctx)
            conn.set_tunnel("static.crates.io", 443)
            conn.request("GET", "/crates/big/big-1.0.0.crate", headers={"Range": range_value})
            resp = conn.getresponse()
            return resp.status, resp.getheader("Content-Range") or "", resp.read()

        assert get("bytes=100-199") == (206, f"bytes 100-199/{len(body)}", body[100:200])
        assert get("bytes=10000-") == (206, f"bytes 10000-{len(body) - 1}/{len(body)}", body[10000:])
        assert get("bytes=-5") == (206, f"bytes {len(body) - 5}-{len(body) - 1}/{len(body)}", body[-5:])
        assert get("bytes=99999-") == (416, f"bytes */{len(body)}", b"")
    finally:
        session.close()
    assert origin.counts == {}


def test_a_case_flagged_for_it_records_undeclared_code_host_files_and_replays_them(origin, hub) -> None:
    path = "/o/r/abc/src/lib.rs"
    origin.files["raw.githubusercontent.com" + path] = b"source"
    url = "https://raw.githubusercontent.com" + path
    with hub.session("record", "case001") as plain:
        assert _get_https(hub, plain.port, "raw.githubusercontent.com", path)[0] == 403
    with hub.session("record", "case001", record_code_hosts=True) as session:
        assert _get_https(hub, session.port, "raw.githubusercontent.com", path) == (200, b"source")
    assert session.violations == []
    assert [e.url for e in session.recorded.values()] == [url]
    with hub.session("locked", "case001", entries=session.recorded.values()) as replay:
        assert _get_https(hub, replay.port, "raw.githubusercontent.com", path) == (200, b"source")
    assert origin.count("raw.githubusercontent.com", path) == 1
    # The flag means nothing outside recording.
    with hub.session("solve", "case001/codex", block_hosts=CODE_HOST_BLOCK_HOSTS, record_code_hosts=True) as solve:
        conn = http.client.HTTPConnection("127.0.0.1", solve.port, timeout=10)
        conn.request("CONNECT", "raw.githubusercontent.com:443")
        assert conn.getresponse().status == 403


def test_a_first_ranged_fetch_stores_the_whole_file_and_answers_the_range(origin, hub) -> None:
    """Chunked downloaders (with a cache-busting query) get 206 slices; upstream is fetched once."""
    body = bytes(range(256)) * 64
    # Only the first chunk's URL exists upstream: the second must come from the store.
    origin.files["files.pythonhosted.org/packages/aa/torch.whl?range=0-99"] = body
    ctx = ssl.create_default_context(cafile=str(hub.ca.ca_cert))
    session = hub.session("record", "case001")
    try:
        def get(path, rng):
            conn = http.client.HTTPSConnection("127.0.0.1", session.port, timeout=10, context=ctx)
            conn.set_tunnel("files.pythonhosted.org", 443)
            conn.request("GET", path, headers={"Range": rng})
            resp = conn.getresponse()
            return resp.status, resp.read()

        assert get("/packages/aa/torch.whl?range=0-99", "bytes=0-99") == (206, body[:100])
        assert get("/packages/aa/torch.whl?range=100-16383", "bytes=100-16383") == (206, body[100:])
    finally:
        session.close()
    assert sum(v for k, v in origin.counts.items() if "torch.whl" in k) == 1


def test_a_git_fetch_is_recorded_by_its_body_and_replayed_without_upstream(origin, hub) -> None:
    path = "/o/repo.git/git-upload-pack"
    ctx = ssl.create_default_context(cafile=str(hub.ca.ca_cert))

    def post(session, body: bytes, target: str = path) -> tuple[int, bytes, str]:
        conn = http.client.HTTPSConnection("127.0.0.1", session.port, timeout=10, context=ctx)
        conn.set_tunnel("github.com", 443)
        conn.request("POST", target, body=body, headers={"Content-Type": "application/x-git-upload-pack-request"})
        resp = conn.getresponse()
        return resp.status, resp.read(), resp.getheader("Content-Type") or ""

    with hub.session("record", "case037", record_code_hosts=True) as rec:
        assert post(rec, b"want abc") == (200, b"pack for want abc", "application/x-git-upload-pack-result")
        assert post(rec, b"want abc")[1] == b"pack for want abc"
        # Any other POST is still refused.
        assert post(rec, b"x", "/o/repo.git/git-receive-pack")[0] == 403
    assert origin.count("github.com", path) == 1
    entries = list(rec.recorded.values())
    assert [(e.method, e.body_sha256 != "") for e in entries] == [("POST", True)]
    with hub.session("locked", "case037", entries=[supply_entry_roundtrip(e) for e in entries]) as replay:
        assert post(replay, b"want abc")[:2] == (200, b"pack for want abc")
        assert post(replay, b"want other")[0] == 403
    assert origin.count("github.com", path) == 1


def supply_entry_roundtrip(entry: Entry) -> Entry:
    """An entry as a lock file stores and reads it back."""
    return Entry.from_dict(entry.to_dict())


def test_code_hosts_are_refused_through_the_proxy(origin, hub) -> None:
    with hub.session("solve", "case001/codex", block_hosts=CODE_HOST_BLOCK_HOSTS) as session:
        conn = http.client.HTTPConnection("127.0.0.1", session.port, timeout=10)
        conn.request("CONNECT", "github.com:443")
        assert conn.getresponse().status == 403
        status, _ = _get_http(session.port, "http://raw.githubusercontent.com/x/y")
        assert status == 403
    assert origin.counts == {}
    assert any("github.com" in e for e in session.events)


def test_solve_caches_fixed_package_files_and_passes_indexes_fresh(origin, hub) -> None:
    origin.files["files.pythonhosted.org/packages/aa/numpy.whl"] = b"numpy"
    origin.files["pypi.org/simple/numpy/"] = b"index"
    for owner in ("case001/codex", "case002/codex"):
        with hub.session("solve", owner, block_hosts=CODE_HOST_BLOCK_HOSTS) as session:
            assert _get_https(hub, session.port, "files.pythonhosted.org", "/packages/aa/numpy.whl") == (
                200,
                b"numpy",
            )
            # pypi.org has no fixed-content rule: it is tunnelled, not decrypted.
            ctx = ssl.create_default_context(cafile=str(origin.ca.ca_cert))
            conn = http.client.HTTPSConnection("127.0.0.1", session.port, timeout=10, context=ctx)
            conn.set_tunnel("pypi.org", 443)
            conn.request("GET", "/simple/numpy/")
            assert conn.getresponse().read() == b"index"
    assert origin.count("files.pythonhosted.org", "/packages/aa/numpy.whl") == 1
    assert origin.count("pypi.org", "/simple/numpy/") == 2


@pytest.mark.parametrize("tunnel", [True, False])
def test_model_api_stream_arrives_chunk_by_chunk(origin, hub, tunnel: bool) -> None:
    origin.stream_chunks = [f"data: {i}\n\n".encode() for i in range(4)]
    origin.stream_delay = 0.4
    with hub.session("solve", "case001/claude-code", block_hosts=CODE_HOST_BLOCK_HOSTS) as session:
        if tunnel:
            ctx = ssl.create_default_context(cafile=str(origin.ca.ca_cert))
            conn = http.client.HTTPSConnection("127.0.0.1", session.port, timeout=10, context=ctx)
            conn.set_tunnel("api.anthropic.com", 443)
            conn.request("POST", "/stream", body=b"{}")
        else:
            conn = http.client.HTTPConnection("127.0.0.1", session.port, timeout=10)
            conn.request("POST", "http://gateway.example.test/stream", body=b"{}")
        start = time.monotonic()
        resp = conn.getresponse()
        arrivals = []
        received = b""
        while chunk := resp.read1(65536):
            arrivals.append(time.monotonic() - start)
            received += chunk
    assert received == b"".join(origin.stream_chunks)
    # The first event is delivered long before the upstream finishes sending.
    assert arrivals[0] < 0.3
    assert arrivals[-1] > 1.0
    assert len(arrivals) >= 3


def test_image_builds_get_the_ca_bundle_from_the_proxy(hub) -> None:
    with hub.session("locked", "base", entries=()) as session:
        status, body = _get_http(session.port, f"http://{CA_HOST}/ca-bundle.pem")
        session.raise_for_violations()
    assert status == 200
    assert body.endswith(hub.ca.pem())


# Proxy settings never reach an image ----------------------------------------


def test_build_args_are_only_dockers_predefined_proxy_args(hub) -> None:
    with hub.session("locked", "x", entries=()) as session:
        args = session.build_args()
    names = {a.split("=", 1)[0] for a in args[3::2]}
    assert args[:2] == ["--network", "host"]
    assert names == {"HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy"}


def test_agent_image_dockerfile_is_the_same_with_and_without_the_supply(hub, tmp_path) -> None:
    from cbrun import images

    def dockerfiles() -> list[str]:
        return [
            images._build_dockerfile("deliverable", {}, backend=b, cli_image="cli")
            for b in ("codex", "claude-code", "dsh", None)
        ]

    supply.deactivate()
    before = dockerfiles()
    supply.activate(supply.SupplyRun(store=hub.store, hub=hub, manifest=supply.load_manifest()))
    try:
        after = dockerfiles()
    finally:
        supply.deactivate()
    assert before == after
    assert all("cbrun-proxy" not in text for text in after)


def test_an_agent_image_built_before_the_proxy_still_matches_its_fingerprint(hub, monkeypatch) -> None:
    """cbrun reuses an image while its fingerprint label matches; the proxy is not part of it."""
    from cbrun import images

    seen: list[str] = []

    def fake_digest(payload: dict) -> str:
        seen.append(repr(sorted(payload.items())))
        return "fp"

    monkeypatch.setattr(images, "digest", fake_digest)
    payload = {
        "deliverable_id": "d",
        "dockerfile": images._build_dockerfile("d", {}, backend="dsh", cli_image="cli"),
        "platform": "linux/amd64",
        "backend": "dsh",
        "shim_assets": {},
        "cli_image_id": "c",
    }
    supply.deactivate()
    images.digest(payload)
    supply.activate(supply.SupplyRun(store=hub.store, hub=hub, manifest=supply.load_manifest()))
    try:
        images.digest(payload)
    finally:
        supply.deactivate()
    assert seen[0] == seen[1]
    assert "127.0.0.1" not in seen[0]


@pytest.mark.skipif(shutil.which("docker") is None, reason="needs docker")
def test_a_build_through_the_proxy_keeps_no_proxy_settings(hub, tmp_path) -> None:
    probe = subprocess.run(["docker", "image", "inspect", "ubuntu:24.04"], capture_output=True)
    if probe.returncode != 0:
        pytest.skip("ubuntu:24.04 not present locally")
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "Dockerfile").write_text(
        "FROM ubuntu:24.04\n"
        "RUN set -eux; test -n \"$https_proxy\"; echo built > /marker\n"
    )
    tag = f"cbrun-supply-test:{tmp_path.name.lower()}"
    try:
        with hub.session("locked", "agent image", entries=()) as session:
            build = subprocess.run(
                ["docker", "build", "-q", *session.build_args(), "-t", tag, str(ctx)],
                capture_output=True,
                text=True,
            )
            session.raise_for_violations()
        assert build.returncode == 0, build.stderr
        config = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{json .Config}}", tag],
            capture_output=True, text=True,
        ).stdout
        history = subprocess.run(
            ["docker", "history", "--no-trunc", tag], capture_output=True, text=True
        ).stdout
        for text in (config, history):
            assert "127.0.0.1" not in text and "cbrun-proxy" not in text
        env = subprocess.run(
            ["docker", "run", "--rm", tag, "env"], capture_output=True, text=True
        ).stdout
        assert "PROXY" not in env.upper()
    finally:
        subprocess.run(["docker", "rmi", "-f", tag], capture_output=True)


@pytest.mark.skipif(shutil.which("docker") is None, reason="needs docker")
def test_committed_env_install_keeps_no_proxy_settings_or_ca(hub, tmp_path) -> None:
    from cbrun.supply_proxy import CONTAINER_CA_DIR

    probe = subprocess.run(["docker", "image", "inspect", "ubuntu:24.04"], capture_output=True)
    if probe.returncode != 0:
        pytest.skip("ubuntu:24.04 not present locally")
    name = f"cbrun-supply-commit-{tmp_path.name.lower()}"
    tag = f"cbrun-supply-commit:{tmp_path.name.lower()}"
    with hub.session("locked", "case-x", entries=()) as session:
        argv = [
            "docker", "run", "--name", name, "--network", "host",
            *session.docker_run_args(),
            "ubuntu:24.04", "bash", "-lc",
            session.shell_exports() + f'test -s "$SSL_CERT_FILE" && test -n "$HTTPS_PROXY"',
        ]
        try:
            run = subprocess.run(argv, capture_output=True, text=True)
            assert run.returncode == 0, run.stderr
            commit = subprocess.run(
                ["docker", "commit", "-c", 'CMD ["/bin/bash"]', name, tag],
                capture_output=True, text=True,
            )
            assert commit.returncode == 0, commit.stderr
            env = subprocess.run(
                ["docker", "image", "inspect", "--format", "{{json .Config}}", tag],
                capture_output=True, text=True,
            ).stdout
            assert "PROXY" not in env.upper() and "127.0.0.1" not in env
            listing = subprocess.run(
                ["docker", "run", "--rm", tag, "bash", "-c", f"ls -A {CONTAINER_CA_DIR} 2>/dev/null"],
                capture_output=True, text=True,
            )
            assert listing.stdout.strip() == ""
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
            subprocess.run(["docker", "rmi", "-f", tag], capture_output=True)


def test_a_client_without_the_ca_fails_the_build_naming_the_host(hub) -> None:
    with hub.session("locked", "case001", entries=()) as session:
        ctx = ssl.create_default_context()
        conn = http.client.HTTPSConnection("127.0.0.1", session.port, timeout=10, context=ctx)
        conn.set_tunnel("files.pythonhosted.org", 443)
        with pytest.raises(ssl.SSLError):
            conn.request("GET", "/packages/x.whl")
        time.sleep(0.2)
        with pytest.raises(SupplyViolation, match="files.pythonhosted.org rejected the proxy certificate"):
            session.raise_for_violations()


def test_a_client_hanging_up_mid_handshake_is_not_a_violation(hub) -> None:
    with hub.session("locked", "case003", entries=()) as session:
        sock = socket.create_connection(("127.0.0.1", session.port), timeout=10)
        sock.sendall(b"CONNECT registry.npmjs.org:443 HTTP/1.1\r\nHost: registry.npmjs.org:443\r\n\r\n")
        assert sock.recv(1024).startswith(b"HTTP/1.1 200")
        sock.close()
        time.sleep(0.2)
        session.raise_for_violations()
    assert any("closed during the TLS handshake" in e for e in session.events)


# Preparation -----------------------------------------------------------------


def test_a_case_without_a_recipe_lock_is_a_supply_error(tmp_path: Path) -> None:
    from cbrun.case_checks import check_case_supply

    case_dir = tmp_path / "case999"
    (case_dir / "source").mkdir(parents=True)
    with pytest.raises(supply.SupplyError, match=r"case999: missing .*recipe"):
        supply.case_inputs_digest(case_dir)
    assert check_case_supply(case_dir) != []


def test_cursor_lock_is_needed_only_when_a_cursor_agent_image_is_missing(hub, monkeypatch) -> None:
    from cbrun import docker_env

    built: set[str] = set()
    monkeypatch.setattr(docker_env, "image_exists", lambda tag: tag in built)
    asked: list[str] = []

    def harness_lock(self, backend: str) -> supply.Lock:
        asked.append(backend)
        raise supply.SupplyError(f"no supply lock for {backend}")

    monkeypatch.setattr(supply.SupplyRun, "harness_lock", harness_lock)
    run = supply.SupplyRun(environ={}, hub=hub, store=hub.store, manifest={"base": {"image": "base"}})
    cases = [Path("/cases/case001"), Path("/cases/case002")]
    from cbrun.images import agent_tag
    from cbrun.recipe import env_recipe_tag

    built.update(env_recipe_tag(c.name) for c in cases)
    built.update(agent_tag(c.name, "cursor") for c in cases)
    built.add("base")
    run.prepare(cases, ["cursor"])
    assert asked == []

    built.discard(agent_tag("case002", "cursor"))
    with pytest.raises(supply.SupplyError, match="no supply lock for cursor"):
        run.prepare(cases, ["cursor"])
    assert asked == ["cursor"]
