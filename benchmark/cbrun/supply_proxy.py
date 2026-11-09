"""Local HTTP(S) proxy that serves downloads from the host-wide store.

Containers reach the network through this proxy only during a full-suite run.
Each container (or image build) gets its own listener on 127.0.0.1, so the
listener knows which mode applies and whom a request belongs to:

``record``
    Generates a lock. Every GET goes upstream once, is stored by digest, and
    is recorded as a lock entry (indexes included). Code hosts are refused
    unless the URL is one the manifest or a case's resource file declares.
``locked``
    Base image build, case environment install, CLI and agent image builds.
    Only requests recorded in the lock are answered, from the store. Any
    other request is refused and kept as a violation that fails the build
    with its URL and owner; nothing is fetched to fill the gap.
``solve``
    The solve container. Code hosts are refused (the container's /etc/hosts
    block is bypassed once a client resolves through a proxy). On package
    hosts, files whose URL names fixed content are fetched once and then
    served from the store; indexes and everything else pass through fresh.
    Every other host, model APIs included, is a plain CONNECT tunnel: never
    decrypted, cached, or buffered, so streamed replies arrive as sent.

HTTPS requests are read by terminating TLS with a certificate from
:class:`~cbrun.supply_ca.ProxyCA`. Only HTTP/1.1 is offered.
"""

from __future__ import annotations

import hashlib
import http.client
import os
import re
import selectors
import socket
import socketserver
import ssl
import sys
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import asdict, dataclass, field
from typing import Literal
from urllib.parse import urlsplit

from .supply_ca import CAError, ProxyCA
from .supply_store import Store, StoreError

__all__ = [
    "CA_HOST",
    "TruncatedBody",
    "CONTAINER_CA_DIR",
    "Entry",
    "ProxyHub",
    "ProxySession",
    "SupplyViolation",
    "is_fixed_content",
    "iter_body",
    "request_key",
]

Mode = Literal["record", "locked", "solve"]
Connector = Callable[[str, int, bool], socket.socket]

# Plain-HTTP host the proxy answers itself; image builds fetch the CA from it.
CA_HOST = "cbrun-proxy.invalid"
CONTAINER_CA_DIR = "/run/cbrun-proxy"
CONTAINER_CA_BUNDLE = f"{CONTAINER_CA_DIR}/ca-bundle.pem"
CONTAINER_CA_CERT = f"{CONTAINER_CA_DIR}/ca.pem"
# apt keeps its own trust list and reads no certificate variable; APT_CONFIG names
# one extra config file that apt reads in addition to the image's own settings.
APT_CONF_NAME = "apt.conf"
APT_CONF_TEXT = f'Acquire::https::CaInfo "{CONTAINER_CA_BUNDLE}";\n'
NO_PROXY = "localhost,127.0.0.1,::1"

_HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "proxy-connection",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
# Headers a stored reply keeps; the body and its length come from the store.
_STORED_HEADERS = ("content-type", "content-encoding", "location", "last-modified", "etag")
# Request headers dropped when fetching a file to store: the store keeps whole,
# unencoded bodies and answers every later request the same way.
_FETCH_DROP = frozenset(
    {"accept-encoding", "range", "if-range", "if-none-match", "if-modified-since", "cache-control"}
)
_UPSTREAM_TIMEOUT_SEC = 300.0
_UPSTREAM_ATTEMPTS = 3


def _ends(*suffixes: str) -> Callable[[str], bool]:
    return lambda path: path.split("?", 1)[0].endswith(suffixes)


def _prefix(*prefixes: str) -> Callable[[str], bool]:
    return lambda path: path.startswith(prefixes)


def _apt(path: str) -> bool:
    return "/pool/" in path or "/by-hash/" in path


def _aliyun(path: str) -> bool:
    """Fixed-content paths on the Aliyun mirror; its indexes pass through fresh."""
    bare = path.split("?", 1)[0]
    if bare.startswith("/pypi/packages/"):
        return True
    if bare.startswith(("/ubuntu/", "/debian/")):
        return _apt(bare)
    if bare.startswith("/crates/api/v1/crates/") and bare.endswith("/download"):
        return True
    # Dated toolchain directories and versioned Node releases never change.
    if re.match(r"/rustup/dist/\d{4}-\d{2}-\d{2}/", bare):
        return True
    return bare.startswith("/nodejs-release/v")


# Package hosts and the URLs on them whose content never changes once
# published. A solve caches only these; the same host's indexes pass through.
FIXED_CONTENT_RULES: dict[str, Callable[[str], bool]] = {
    "files.pythonhosted.org": _prefix("/packages/"),
    "registry.npmjs.org": lambda p: "/-/" in p and p.split("?", 1)[0].endswith(".tgz"),
    "registry.yarnpkg.com": lambda p: "/-/" in p and p.split("?", 1)[0].endswith(".tgz"),
    "archive.ubuntu.com": _apt,
    "security.ubuntu.com": _apt,
    "ports.ubuntu.com": _apt,
    "repo.anaconda.com": _ends(".conda", ".tar.bz2"),
    "conda.anaconda.org": _ends(".conda", ".tar.bz2"),
    "proxy.golang.org": lambda p: "/@v/" in p and _ends(".zip", ".mod", ".info")(p),
    "nodejs.org": _prefix("/dist/v"),
    "dl.google.com": _prefix("/go/"),
    "ziglang.org": _prefix("/download/0.", "/download/1."),
    "static.crates.io": _prefix("/crates/"),
    "mirrors.aliyun.com": _aliyun,
}


def _byte_range(header: str, size: int) -> tuple[int, int] | str | None:
    """The one byte range a ``Range`` header asks of a *size*-byte body.

    Returns (first, last) inclusive, "unsatisfiable", or None for a header that
    asks for no single range (absent, malformed or several ranges): the whole
    body is served then, which HTTP allows.
    """
    m = re.fullmatch(r"\s*bytes\s*=\s*(\d*)\s*-\s*(\d*)\s*", header or "")
    if not m or (m.group(1) == "" and m.group(2) == ""):
        return None
    first, last = m.group(1), m.group(2)
    if first == "":
        suffix = int(last)
        if suffix == 0:
            return "unsatisfiable"
        return max(0, size - suffix), size - 1
    start = int(first)
    if start >= size:
        return "unsatisfiable"
    end = min(int(last), size - 1) if last else size - 1
    if end < start:
        return None
    return start, end


def _lookup_fixed(store: Store, url: str, fixed: bool) -> dict | None:
    """The stored reply for *url*; a fixed-content file is also found without its query."""
    for key in dict.fromkeys([url, url.split("?", 1)[0] if fixed else url]):
        known = store.lookup_url(key)
        if known is not None and store.has(known["sha256"], known["size"]):
            return known
    return None


def _remember_fixed(store: Store, url: str, entry: "Entry", fixed: bool) -> None:
    record = {**entry.to_dict(), "accept": ""}
    for key in dict.fromkeys([url, url.split("?", 1)[0] if fixed else url]):
        store.remember_url(key, {**record, "url": key})


def is_fixed_content(host: str, path: str) -> bool:
    rule = FIXED_CONTENT_RULES.get(host.lower())
    return bool(rule and rule(path))


def request_key(method: str, url: str, accept: str, body_sha256: str = "") -> str:
    """Lock key of a request. Indexes answer differently per ``Accept``; a POST per body."""
    method = "GET" if method in ("GET", "HEAD") else method
    key = f"{method} {url} accept={accept}"
    return f"{key} body={body_sha256}" if body_sha256 else key


def is_git_fetch(method: str, path: str) -> bool:
    """git's smart-HTTP fetch call: a read-only POST whose reply depends only on its body."""
    return method == "POST" and path.split("?", 1)[0].endswith("/git-upload-pack")


@dataclass(frozen=True)
class Entry:
    """One recorded reply: the request it answers and the stored body."""

    method: str
    url: str
    accept: str
    status: int
    sha256: str
    size: int
    headers: dict[str, str] = field(default_factory=dict)
    # SHA-256 of the request body, for a recorded POST (git fetch); empty for GET.
    body_sha256: str = ""

    @property
    def key(self) -> str:
        return request_key(self.method, self.url, self.accept, self.body_sha256)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Entry":
        return cls(
            method=str(data["method"]),
            url=str(data["url"]),
            accept=str(data.get("accept") or ""),
            status=int(data["status"]),
            sha256=str(data["sha256"]),
            size=int(data["size"]),
            headers={str(k): str(v) for k, v in (data.get("headers") or {}).items()},
            body_sha256=str(data.get("body_sha256") or ""),
        )


class SupplyViolation(RuntimeError):
    """A build asked for something outside its lock, or the store disagreed."""


def _default_connect(host: str, port: int, tls: bool) -> socket.socket:
    sock = socket.create_connection((host, port), timeout=60)
    if tls:
        ctx = ssl.create_default_context()
        sock = ctx.wrap_socket(sock, server_hostname=host)
    return sock


class ProxyHub:
    """The proxy of one cbrun process. Sessions are its per-container listeners."""

    def __init__(
        self,
        store: Store,
        *,
        ca: ProxyCA | None = None,
        connect: Connector = _default_connect,
    ) -> None:
        self.store = store
        self.ca = ca or ProxyCA(store.root / "ca")
        self.connect = connect
        apt_conf = self.ca.mount_dir / APT_CONF_NAME
        if not apt_conf.is_file() or apt_conf.read_text() != APT_CONF_TEXT:
            tmp = apt_conf.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(APT_CONF_TEXT)
            os.chmod(tmp, 0o644)
            os.replace(tmp, apt_conf)
        self._contexts: dict[str, ssl.SSLContext] = {}
        self._contexts_lock = threading.Lock()

    def session(
        self,
        mode: Mode,
        owner: str,
        *,
        entries: Iterable[Entry] = (),
        declared_urls: Iterable[str] = (),
        block_hosts: Iterable[str] = (),
        record_code_hosts: bool = False,
    ) -> "ProxySession":
        return ProxySession(
            self,
            mode,
            owner,
            entries=entries,
            declared_urls=declared_urls,
            block_hosts=block_hosts,
            record_code_hosts=record_code_hosts,
        )

    def server_context(self, host: str) -> ssl.SSLContext:
        with self._contexts_lock:
            ctx = self._contexts.get(host)
            if ctx is None:
                ctx = self.ca.server_context(host)
                self._contexts[host] = ctx
            return ctx


class ProxySession:
    """One listener: one mode and one owner (a case, an image, a trial)."""

    def __init__(
        self,
        hub: ProxyHub,
        mode: Mode,
        owner: str,
        *,
        entries: Iterable[Entry],
        declared_urls: Iterable[str],
        block_hosts: Iterable[str],
        record_code_hosts: bool = False,
    ) -> None:
        if mode not in ("record", "locked", "solve"):
            raise ValueError(f"unknown proxy mode {mode!r}")
        self.hub = hub
        self.mode = mode
        self.owner = owner
        self.entries = {entry.key: entry for entry in entries}
        self.declared_urls = frozenset(declared_urls)
        # Recording only: this install's own undeclared code-host files are allowed;
        # the lock then pins their bytes. A solve never gets this.
        self.record_code_hosts = record_code_hosts and mode == "record"
        self.block_hosts = frozenset(host.lower() for host in block_hosts)
        self.recorded: dict[str, Entry] = {}
        self.violations: list[str] = []
        self.events: list[str] = []
        self.upstream_requests = 0
        self._lock = threading.Lock()
        session = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self) -> None:  # noqa: D401 - socketserver hook
                _Connection(session, self.connection).serve()

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = True

        try:
            self._server = Server(("127.0.0.1", 0), Handler)
        except OSError as exc:
            raise SupplyViolation(f"cannot start the supply proxy for {owner}: {exc}") from exc
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever, name=f"supply-proxy-{owner}", daemon=True
        )
        self._thread.start()
        try:
            socket.create_connection(("127.0.0.1", self.port), timeout=5).close()
        except OSError as exc:
            self.close()
            raise SupplyViolation(f"supply proxy for {owner} is not reachable: {exc}") from exc

    # Wiring ----------------------------------------------------------------

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def proxy_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        for name in ("HTTP_PROXY", "HTTPS_PROXY"):
            env[name] = env[name.lower()] = self.url
        env["NO_PROXY"] = env["no_proxy"] = NO_PROXY
        return env

    def container_env(self) -> dict[str, str]:
        """Proxy and trust settings for a container that mounts :meth:`mounts`.

        pip, requests and conda carry their own CA bundles, so each is handed
        the merged bundle explicitly; Node adds the CA to its built-in roots;
        apt gets it through an extra config file.
        """
        env = self.proxy_env()
        for name in (
            "SSL_CERT_FILE",
            "REQUESTS_CA_BUNDLE",
            "CURL_CA_BUNDLE",
            "PIP_CERT",
            "GIT_SSL_CAINFO",
            "CONDA_SSL_VERIFY",
            "CARGO_HTTP_CAINFO",
        ):
            env[name] = CONTAINER_CA_BUNDLE
        env["NODE_EXTRA_CA_CERTS"] = CONTAINER_CA_CERT
        env["APT_CONFIG"] = f"{CONTAINER_CA_DIR}/{APT_CONF_NAME}"
        return env

    def shell_exports(self) -> str:
        """``export`` line carrying :meth:`container_env` inside a command.

        Containers that are committed into an image get the settings this way
        rather than as container env, which ``docker commit`` would keep.
        """
        import shlex

        pairs = " ".join(f"{k}={shlex.quote(v)}" for k, v in self.container_env().items())
        return f"export {pairs}; "

    def mounts(self) -> list[tuple[str, str]]:
        return [(str(self.hub.ca.mount_dir), f"{CONTAINER_CA_DIR}:ro")]

    def docker_run_args(self) -> list[str]:
        out: list[str] = []
        for host_path, container_path in self.mounts():
            out += ["-v", f"{host_path}:{container_path}"]
        return out

    def build_args(self) -> list[str]:
        """``docker build`` flags: host network plus Docker's predefined proxy args.

        Predefined proxy args are kept out of the build cache key and the image
        history, so an image's content and fingerprint do not depend on them.
        """
        out = ["--network", "host"]
        for key, value in self.proxy_env().items():
            out += ["--build-arg", f"{key}={value}"]
        return out

    # Outcome ---------------------------------------------------------------

    def violation(self, message: str) -> None:
        with self._lock:
            self.violations.append(message)
        print(f"[cbrun] supply proxy: {message}", file=sys.stderr, flush=True)

    def event(self, message: str) -> None:
        with self._lock:
            self.events.append(message)

    def raise_for_violations(self) -> None:
        if self.violations:
            listed = "\n  ".join(dict.fromkeys(self.violations))
            raise SupplyViolation(f"{self.owner}: requests outside the supply lock:\n  {listed}")

    def record(self, entry: Entry) -> None:
        with self._lock:
            self.recorded[entry.key] = entry

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def __enter__(self) -> "ProxySession":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


# Connection handling ------------------------------------------------------


class _ClientGone(Exception):
    pass


class TruncatedBody(OSError):
    """The upstream connection ended before the whole reply body arrived."""


def iter_body(resp: http.client.HTTPResponse, size: int) -> Iterator[bytes]:
    """Yield *resp*'s body; raise :class:`TruncatedBody` if it ends early.

    A body framed by Content-Length is complete only when that many bytes
    arrived; a chunked body only when its last chunk arrived. A body framed by
    the connection close has no length to check against.
    """
    try:
        while data := resp.read1(size):
            yield data
    except http.client.IncompleteRead as exc:
        raise TruncatedBody(f"chunked body ended early after {len(exc.partial)} bytes") from exc
    if resp.length:
        raise TruncatedBody(f"body ended {resp.length} bytes short of its Content-Length")


@dataclass
class _Request:
    method: str
    target: str
    version: str
    headers: list[tuple[str, str]]

    def header(self, name: str) -> str:
        name = name.lower()
        for key, value in self.headers:
            if key.lower() == name:
                return value
        return ""

    @property
    def keep_alive(self) -> bool:
        conn = (self.header("connection") or self.header("proxy-connection")).lower()
        if self.version == "HTTP/1.0":
            return conn == "keep-alive"
        return conn != "close"


class _Connection:
    def __init__(self, session: ProxySession, sock: socket.socket) -> None:
        self.session = session
        self.hub = session.hub
        self.sock = sock
        self.rfile = sock.makefile("rb")

    # Entry point ---------------------------------------------------------

    def serve(self) -> None:
        try:
            first = self._read_request()
            if first is None:
                return
            if first.method == "CONNECT":
                self._connect(first)
                return
            self._serve_plain(first)
        except (_ClientGone, ConnectionError, ssl.SSLError, TimeoutError):
            return
        except Exception as exc:  # noqa: BLE001 - the build must fail with this reason
            self._fail(f"supply proxy error: {type(exc).__name__}: {exc}")
            self._reply_text(502, f"cbrun supply proxy error: {type(exc).__name__}: {exc}")

    def _serve_plain(self, request: _Request | None) -> None:
        while request is not None:
            parts = urlsplit(request.target)
            if parts.scheme != "http" or not parts.hostname:
                self._reply_text(400, f"cbrun proxy expects an absolute http URL, got {request.target}")
                return
            path = parts.path or "/"
            if parts.query:
                path += "?" + parts.query
            keep = self._handle("http", parts.hostname.lower(), parts.port or 80, path, request)
            if not keep:
                return
            request = self._read_request()

    # CONNECT ---------------------------------------------------------------

    def _connect(self, request: _Request) -> None:
        host, _, port_text = request.target.rpartition(":")
        host = host.strip("[]").lower()
        try:
            port = int(port_text)
        except ValueError:
            self._reply_text(400, f"bad CONNECT target {request.target}")
            return
        session = self.session
        if session.mode == "solve" and host in session.block_hosts:
            session.event(f"refused code host {host}")
            self._reply_text(403, f"cbrun: {host} is a code host and is blocked during the solve")
            return
        decrypt = session.mode != "solve" or host in FIXED_CONTENT_RULES
        if not decrypt:
            self._tunnel(host, port)
            return
        try:
            ctx = self.hub.server_context(host)
        except CAError as exc:
            self._fail(f"cannot issue a certificate for {host}: {exc}")
            self._reply_text(502, str(exc))
            return
        self._write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        try:
            tls = ctx.wrap_socket(self.sock, server_side=True)
        except (ssl.SSLError, OSError) as exc:
            reason = str(getattr(exc, "reason", "") or "")
            if isinstance(exc, ssl.SSLError) and "ALERT" in reason.upper():
                # The client refused our certificate: it does not trust the CA.
                self._fail(f"the client for {host} rejected the proxy certificate: {exc}")
            else:
                # The client hung up before sending a request (npm drops its
                # background update check when the command exits). Nothing
                # was asked for, so there is nothing to supply.
                self.session.event(f"client for {host} closed during the TLS handshake: {exc}")
            return
        self.sock = tls
        self.rfile = tls.makefile("rb")
        request = self._read_request()
        while request is not None:
            path = request.target if request.target.startswith("/") else urlsplit(request.target).path
            if not self._handle("https", host, port, path or "/", request):
                return
            request = self._read_request()

    def _tunnel(self, host: str, port: int) -> None:
        try:
            upstream = self.hub.connect(host, port, False)
        except OSError as exc:
            self._reply_text(502, f"cbrun proxy cannot reach {host}:{port}: {exc}")
            return
        upstream.settimeout(None)
        self.sock.settimeout(None)
        # A client sends nothing after CONNECT until it reads this reply, so
        # the request reader holds no tunnel bytes and the raw socket is used.
        self._write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        sel = selectors.DefaultSelector()
        sel.register(self.sock, selectors.EVENT_READ, upstream)
        sel.register(upstream, selectors.EVENT_READ, self.sock)
        try:
            while True:
                for key, _ in sel.select():
                    data = key.fileobj.recv(65536)  # type: ignore[union-attr]
                    if not data:
                        return
                    key.data.sendall(data)
        except OSError:
            return
        finally:
            sel.close()
            upstream.close()

    # One request -----------------------------------------------------------

    def _handle(self, scheme: str, host: str, port: int, path: str, request: _Request) -> bool:
        """Answer one request; return whether the connection stays open."""
        session = self.session
        default_port = 443 if scheme == "https" else 80
        authority = host if port == default_port else f"{host}:{port}"
        url = f"{scheme}://{authority}{path}"
        body = self._read_body(request)
        keep = request.keep_alive

        if scheme == "http" and host == CA_HOST:
            return self._serve_ca(path, keep)

        if session.mode == "solve":
            if host in session.block_hosts:
                session.event(f"refused code host {url}")
                self._reply_text(403, f"cbrun: {host} is a code host and is blocked during the solve", keep)
                return keep
            if request.method == "GET" and is_fixed_content(host, path):
                return self._serve_cached_url(scheme, host, port, path, url, request, keep)
            return self._pass_through(scheme, host, port, path, request, body, keep)

        git_fetch = is_git_fetch(request.method, path)
        if request.method not in ("GET", "HEAD") and not git_fetch:
            session.violation(f"{request.method} {url} (only GET and git fetch are supplied)")
            self._reply_text(403, f"cbrun supply: {request.method} {url} is not supplied for {session.owner}", keep)
            return keep

        accept = request.header("accept")
        body_sha256 = hashlib.sha256(body).hexdigest() if git_fetch else ""
        key = request_key(request.method, url, accept, body_sha256)
        if session.mode == "locked":
            entry = session.entries.get(key)
            if entry is None:
                session.violation(_missing_message(session, request.method, url, accept))
                self._reply_text(403, f"cbrun supply: {url} is not in the lock for {session.owner}", keep)
                return keep
            return self._serve_entry(entry, request.method == "HEAD", keep, request.header("range"))

        # record
        from .denylist import CODE_HOST_BLOCK_HOSTS

        if host in CODE_HOST_BLOCK_HOSTS and url not in session.declared_urls and not session.record_code_hosts:
            session.violation(f"{url} is on a code host and no manifest or resource file declares it")
            self._reply_text(403, f"cbrun supply: {url} is on a code host", keep)
            return keep
        entry = session.recorded.get(key)
        if git_fetch:
            if entry is None:
                entry = self._record_post(scheme, host, port, path, request, body, url, accept, body_sha256)
                if entry is None:
                    return False
                session.record(entry)
            return self._serve_entry(entry, False, keep)
        fixed = is_fixed_content(host, path)
        cached = fixed or url in session.declared_urls
        store = self.hub.store
        if entry is None and cached:
            # A file whose URL names fixed content, or that a manifest or resource
            # file declares with its checksum, is fetched once per host, whichever
            # case or harness records it first.
            known = _lookup_fixed(store, url, fixed)
            if known is not None:
                entry = Entry.from_dict({**known, "url": url, "accept": accept})
                session.record(entry)
        range_header = request.header("range")
        if entry is None:
            # A ranged request is answered from the stored copy once the whole
            # file is in: the upstream fetch never forwards the range.
            ranged = _byte_range(range_header, 1 << 62) is not None
            with store.lock(key):
                entry = self._fetch_and_store(scheme, host, port, path, request, url, accept, tee=not ranged)
            if entry is None:
                return False
            session.record(entry)
            if entry.status == 200 and cached:
                _remember_fixed(store, url, entry, fixed)
            if not ranged:
                return keep
        return self._serve_entry(entry, request.method == "HEAD", keep, range_header)

    def _serve_ca(self, path: str, keep: bool) -> bool:
        ca = self.hub.ca
        if path == "/ca.pem":
            data = ca.pem()
        elif path == "/ca-bundle.pem":
            data = ca.bundle_pem()
        else:
            self._reply_text(404, f"unknown path {path}", keep)
            return keep
        self._send_head(200, [("Content-Type", "application/x-pem-file")], len(data), keep)
        self._write(data)
        return keep

    def _serve_entry(self, entry: Entry, head_only: bool, keep: bool, range_header: str = "") -> bool:
        try:
            path = self.hub.store.stored_path(entry.sha256, entry.size, label=entry.url)
        except StoreError as exc:
            self.session.violation(str(exc))
            self._reply_text(502, f"cbrun supply: {exc}", keep)
            return keep
        headers = [(k, v) for k, v in entry.headers.items() if k.lower() not in ("content-range", "accept-ranges")]
        status, start, length = entry.status, 0, entry.size
        if entry.status == 200:
            headers.append(("Accept-Ranges", "bytes"))
            span = _byte_range(range_header, entry.size)
            if span == "unsatisfiable":
                self._send_head(416, [("Content-Range", f"bytes */{entry.size}")], 0, keep)
                return keep
            if span is not None:
                start, end = span
                status, length = 206, end - start + 1
                headers.append(("Content-Range", f"bytes {start}-{end}/{entry.size}"))
        self._send_head(status, headers, length, keep)
        if not head_only:
            with open(path, "rb") as fh:
                fh.seek(start)
                left = length
                while left > 0 and (chunk := fh.read(min(1024 * 1024, left))):
                    self._write(chunk)
                    left -= len(chunk)
        return keep

    def _serve_cached_url(
        self, scheme: str, host: str, port: int, path: str, url: str, request: _Request, keep: bool
    ) -> bool:
        store = self.hub.store
        range_header = request.header("range")
        with store.lock(url):
            known = _lookup_fixed(store, url, True)
            if known is not None:
                entry = Entry.from_dict({**known, "url": url})
            else:
                ranged = _byte_range(range_header, 1 << 62) is not None
                entry = self._fetch_and_store(scheme, host, port, path, request, url, "", tee=not ranged)
                if entry is None:
                    return False
                if entry.status == 200:
                    _remember_fixed(store, url, entry, True)
                if not ranged:
                    return keep
        return self._serve_entry(entry, False, keep, range_header)

    # Upstream --------------------------------------------------------------

    def _upstream(self, scheme: str, host: str, port: int) -> http.client.HTTPConnection:
        connect = self.hub.connect
        tls = scheme == "https"

        class Upstream(http.client.HTTPConnection):
            def connect(self) -> None:  # noqa: D401 - http.client hook
                self.sock = connect(host, port, tls)
                self.sock.settimeout(self.timeout)

        return Upstream(host, port, timeout=_UPSTREAM_TIMEOUT_SEC)

    def _fetch_and_store(
        self,
        scheme: str,
        host: str,
        port: int,
        path: str,
        request: _Request,
        url: str,
        accept: str,
        *,
        tee: bool,
    ) -> Entry | None:
        """GET *url* upstream, store the whole body, and answer the client as it arrives.

        Returns None when the reply was not stored: a server error, passed
        through, or a body that ended early. A short body is not stored and the
        client connection is closed without completing it, so the client sees
        the failure and its own retry fetches the file again.
        """
        session = self.session
        headers = [
            (k, v)
            for k, v in request.headers
            if k.lower() not in _HOP_BY_HOP and k.lower() not in _FETCH_DROP
        ]
        headers.append(("Accept-Encoding", "identity"))
        # Nothing has reached the client before the reply head, so a dropped
        # connection up to there is retried here.
        for attempt in range(_UPSTREAM_ATTEMPTS):
            conn = self._upstream(scheme, host, port)
            try:
                conn.putrequest("GET", path, skip_host=True, skip_accept_encoding=True)
                if not any(k.lower() == "host" for k, _ in headers):
                    conn.putheader("Host", host if port in (80, 443) else f"{host}:{port}")
                for k, v in headers:
                    conn.putheader(k, v)
                conn.endheaders()
                resp = conn.getresponse()
                break
            except OSError as exc:
                conn.close()
                if attempt + 1 < _UPSTREAM_ATTEMPTS:
                    time.sleep(2 * (attempt + 1))
                    continue
                # The client sees the failure and may retry; the install's own
                # exit status decides whether the build failed.
                session.event(f"cannot fetch {url}: {exc}")
                self._reply_text(502, f"cbrun proxy cannot fetch {url}: {exc}", request.keep_alive)
                return None
        with session._lock:
            session.upstream_requests += 1
        try:
            if resp.status >= 500:
                self._relay_response(resp, request, request.keep_alive)
                return None
            kept = [(k, v) for k, v in resp.getheaders() if k.lower() in _STORED_HEADERS]
            length = resp.getheader("content-length")
            head_only = request.method == "HEAD"
            send = tee
            if send:
                if length is not None and not resp.getheader("transfer-encoding"):
                    self._send_head(resp.status, kept, int(length), request.keep_alive)
                    chunked = False
                else:
                    self._send_head(resp.status, kept, None, request.keep_alive)
                    chunked = True
            try:
                with self.hub.store.writer(label=url) as writer:
                    for data in iter_body(resp, 65536):
                        writer.write(data)
                        if send and not head_only:
                            try:
                                self._write(_chunk(data) if chunked else data)
                            except _ClientGone:
                                # Finish the download so the store still gets it.
                                send = False
            except TruncatedBody as exc:
                session.event(f"not stored {url}: {exc}")
                return None
            if send and not head_only and chunked:
                self._write(b"0\r\n\r\n")
            blob = writer.blob
            assert blob is not None
            return Entry(
                method="GET",
                url=url,
                accept=accept,
                status=resp.status,
                sha256=blob.sha256,
                size=blob.size,
                headers={k.lower(): v for k, v in kept},
            )
        finally:
            conn.close()

    def _record_post(
        self, scheme: str, host: str, port: int, path: str, request: _Request, body: bytes,
        url: str, accept: str, body_sha256: str,
    ) -> Entry | None:
        """Send a git fetch POST upstream and store its whole reply; None if it failed."""
        conn = self._upstream(scheme, host, port)
        conn.timeout = None
        try:
            conn.putrequest("POST", path, skip_host=True, skip_accept_encoding=True)
            if not request.header("host"):
                conn.putheader("Host", host if port in (80, 443) else f"{host}:{port}")
            for k, v in request.headers:
                if k.lower() in _HOP_BY_HOP or k.lower() in ("content-length", "accept-encoding"):
                    continue
                conn.putheader(k, v)
            conn.putheader("Accept-Encoding", "identity")
            conn.putheader("Content-Length", str(len(body)))
            conn.endheaders(body)
            resp = conn.getresponse()
            with self.session._lock:
                self.session.upstream_requests += 1
            if resp.status >= 400:
                self._relay_response(resp, request, request.keep_alive)
                return None
            kept = [(k, v) for k, v in resp.getheaders() if k.lower() in _STORED_HEADERS]
            with self.hub.store.writer(label=url) as writer:
                for data in iter_body(resp, 65536):
                    writer.write(data)
        except (OSError, TruncatedBody) as exc:
            self.session.event(f"git fetch {url} failed: {exc}")
            self._reply_text(502, f"cbrun proxy cannot fetch {url}: {exc}", request.keep_alive)
            return None
        finally:
            conn.close()
        blob = writer.blob
        assert blob is not None
        return Entry(
            method="POST", url=url, accept=accept, status=resp.status, sha256=blob.sha256,
            size=blob.size, headers={k.lower(): v for k, v in kept}, body_sha256=body_sha256,
        )

    def _pass_through(
        self, scheme: str, host: str, port: int, path: str, request: _Request, body: bytes, keep: bool
    ) -> bool:
        conn = self._upstream(scheme, host, port)
        conn.timeout = None
        try:
            conn.putrequest(request.method, path, skip_host=True, skip_accept_encoding=True)
            if not request.header("host"):
                conn.putheader("Host", host if port in (80, 443) else f"{host}:{port}")
            for k, v in request.headers:
                if k.lower() in _HOP_BY_HOP or k.lower() == "content-length":
                    continue
                conn.putheader(k, v)
            if body or request.method in ("POST", "PUT", "PATCH"):
                conn.putheader("Content-Length", str(len(body)))
            conn.endheaders(body or None)
            resp = conn.getresponse()
        except OSError as exc:
            conn.close()
            self._reply_text(502, f"cbrun proxy cannot reach {host}:{port}: {exc}", keep)
            return keep
        try:
            return self._relay_response(resp, request, keep)
        finally:
            conn.close()

    def _relay_response(self, resp: http.client.HTTPResponse, request: _Request, keep: bool) -> bool:
        """Forward an upstream reply chunk by chunk as it arrives."""
        headers = [(k, v) for k, v in resp.getheaders() if k.lower() not in _HOP_BY_HOP]
        no_body = request.method == "HEAD" or resp.status in (204, 304) or 100 <= resp.status < 200
        length = resp.getheader("content-length")
        if no_body:
            self._send_head(resp.status, [(k, v) for k, v in headers if k.lower() != "content-length"],
                            int(length) if length else 0, keep, reason=resp.reason)
            return keep
        chunked = length is None or bool(resp.getheader("transfer-encoding"))
        headers = [(k, v) for k, v in headers if k.lower() != "content-length"]
        self._send_head(resp.status, headers, None if chunked else int(length), keep, reason=resp.reason)
        try:
            for data in iter_body(resp, 65536):
                self._write(_chunk(data) if chunked else data)
        except TruncatedBody as exc:
            # Leave the reply incomplete so the client sees the failure.
            self.session.event(f"upstream reply cut off: {exc}")
            return False
        if chunked:
            self._write(b"0\r\n\r\n")
        return keep

    # Wire helpers ----------------------------------------------------------

    def _fail(self, message: str) -> None:
        if self.session.mode == "solve":
            self.session.event(message)
        else:
            self.session.violation(message)

    def _read_request(self) -> _Request | None:
        try:
            line = self.rfile.readline(65537)
        except (OSError, ssl.SSLError):
            return None
        if not line:
            return None
        while line in (b"\r\n", b"\n"):
            line = self.rfile.readline(65537)
            if not line:
                return None
        try:
            method, target, version = line.decode("latin-1").strip().split(" ", 2)
        except ValueError:
            self._reply_text(400, "malformed request line")
            return None
        headers: list[tuple[str, str]] = []
        while True:
            raw = self.rfile.readline(65537)
            if not raw or raw in (b"\r\n", b"\n"):
                break
            name, _, value = raw.decode("latin-1").partition(":")
            headers.append((name.strip(), value.strip()))
        return _Request(method.upper(), target, version.upper(), headers)

    def _read_body(self, request: _Request) -> bytes:
        if request.header("transfer-encoding").lower() == "chunked":
            parts = []
            while True:
                size_line = self.rfile.readline(65537)
                size = int(size_line.split(b";", 1)[0].strip() or b"0", 16)
                if size == 0:
                    while self.rfile.readline(65537) not in (b"\r\n", b"\n", b""):
                        pass
                    break
                parts.append(self.rfile.read(size))
                self.rfile.readline(65537)
            return b"".join(parts)
        length = request.header("content-length")
        if length:
            return self.rfile.read(int(length))
        return b""

    def _send_head(
        self,
        status: int,
        headers: list[tuple[str, str]],
        length: int | None,
        keep: bool = False,
        *,
        reason: str | None = None,
    ) -> None:
        reason = reason or http.client.responses.get(status, "")
        lines = [f"HTTP/1.1 {status} {reason}"]
        for k, v in headers:
            if k.lower() in ("content-length", "transfer-encoding", "connection"):
                continue
            lines.append(f"{k}: {v}")
        if length is None:
            lines.append("Transfer-Encoding: chunked")
        else:
            lines.append(f"Content-Length: {length}")
        lines.append("Connection: keep-alive" if keep else "Connection: close")
        self._write(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1"))

    def _reply_text(self, status: int, text: str, keep: bool = False) -> None:
        data = (text + "\n").encode("utf-8")
        try:
            self._send_head(status, [("Content-Type", "text/plain; charset=utf-8")], len(data), keep)
            self._write(data)
        except _ClientGone:
            pass

    def _write(self, data: bytes) -> None:
        try:
            self.sock.sendall(data)
        except (OSError, ssl.SSLError) as exc:
            raise _ClientGone from exc


def _chunk(data: bytes) -> bytes:
    return f"{len(data):x}\r\n".encode() + data + b"\r\n"


def _missing_message(session: ProxySession, method: str, url: str, accept: str) -> str:
    same_url = [e for e in session.entries.values() if e.url == url]
    if same_url:
        recorded = ", ".join(repr(e.accept) for e in same_url)
        return (
            f"{method} {url} with Accept {accept!r} is not in the lock for "
            f"{session.owner} (recorded with Accept {recorded})"
        )
    return f"{method} {url} is not in the lock for {session.owner}"


_HUB: ProxyHub | None = None
_HUB_LOCK = threading.Lock()


def process_hub(environ: dict[str, str] | None = None) -> ProxyHub:
    """The proxy hub of this process, started on first use."""
    global _HUB
    from .supply_store import default_store

    with _HUB_LOCK:
        if _HUB is None:
            _HUB = ProxyHub(default_store(os.environ if environ is None else environ))
        return _HUB
