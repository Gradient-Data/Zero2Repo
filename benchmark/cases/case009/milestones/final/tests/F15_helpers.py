# feature: F15
"""F15 observation helpers: scheme contrast, leftover pointers, timeout peers.

Import sealed names from ``_helpers`` / ``_harness``. Do not redefine a
name those modules already export.
"""

from __future__ import annotations

import ctypes
import json
import socket
import ssl
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator, Sequence
from urllib.parse import urlparse

from _harness import RunResult, token
from _helpers import (
    RecordedHttpExchange,
    _is_objects_batch_path,
    _media_type_named,
    _read_handler_body,
    _request_path,
    _rewrite_placeholder_hrefs,
    _send_bytes,
    conforming_batch_server,
    contract_basic_adapter_name,
    contract_git_orbulk_json_media_type,
    pointer_matches_digest_and_size,
    require_git_config_set,
    require_invalid_unlike_success,
    require_success,
    sha256_hex,
)


def dedicated_indication_scheme(indication: str) -> str:
    """Return the HTTP scheme of a dedicated endpoint indication.

    Missing scheme is unclassified, not 'no scheme'. Does not pin a
    prefix spelling.
    """
    assert indication, "dedicated indication is empty"
    parsed = urlparse(indication)
    assert parsed.scheme, (
        "dedicated indication has no scheme to compare: "
        f"{indication!r}"
    )
    return parsed.scheme.casefold()


def require_secure_http_scheme_matches(
    git_protocol_indication: str, ssh_style_indication: str
) -> str:
    """Unset Git-protocol derivation uses the same scheme as SSH-style HTTPS.

    The SSH-style indication is the secure-HTTP reference (FP-06).
    Does not name scheme prefixes.
    """
    git_scheme = dedicated_indication_scheme(git_protocol_indication)
    ssh_scheme = dedicated_indication_scheme(ssh_style_indication)
    assert git_scheme == ssh_scheme, (
        "unset Git-protocol dedicated indication did not use the secure "
        "HTTP scheme used for SSH-style remotes: "
        f"git-protocol={git_protocol_indication!r} "
        f"ssh-style={ssh_style_indication!r}"
    )
    return git_scheme


def require_git_protocol_scheme_changed(
    unset_indication: str, set_indication: str
) -> None:
    """A different accepted Git-protocol value must change the dedicated scheme.

    An echo among related environment facts is not this check: only the
    dedicated indications are compared. Does not pin prefixes or the
    accepted value token.
    """
    unset_scheme = dedicated_indication_scheme(unset_indication)
    set_scheme = dedicated_indication_scheme(set_indication)
    assert set_scheme != unset_scheme, (
        "accepted Git-protocol setting left the dedicated indication "
        "scheme unchanged: "
        f"unset={unset_indication!r} set={set_indication!r}"
    )


def require_ssh_style_scheme_unchanged(
    unset_indication: str, set_indication: str
) -> None:
    """SSH-style remotes do not use the Git-protocol setting (FP-06/FP-15)."""
    unset_scheme = dedicated_indication_scheme(unset_indication)
    set_scheme = dedicated_indication_scheme(set_indication)
    assert set_scheme == unset_scheme, (
        "Git-protocol setting changed an SSH-style remote's dedicated "
        "scheme: "
        f"unset={unset_indication!r} set={set_indication!r}"
    )


def alternate_accepted_git_protocol_value(secure_scheme: str) -> str:
    """Return a different accepted Git-protocol value than *secure_scheme*.

    Fixture SET only. Does not assert that token appears in product output.
    """
    assert secure_scheme, "secure HTTP scheme is empty"
    other = "http" if secure_scheme != "http" else "https"
    assert other != secure_scheme, (
        "cannot choose a different accepted Git-protocol value from "
        f"{secure_scheme!r}"
    )
    return other


def require_cannot_download_skipped_unlike_failed(
    skipped: RunResult, failed: RunResult
) -> None:
    """Skip-download-errors on succeeds a cannot-download that fails when off.

    Does not pin exit numbers. Pointer encoding is asserted by the caller.
    """
    require_success(skipped)
    assert failed.returncode != 0, (
        "cannot-download checkout succeeded while skip-download-errors was off"
    )
    require_invalid_unlike_success(skipped, failed)


def require_leftover_pointer_text(
    ws, relpath: str, *, digest: str, size: int, unlike: bytes
) -> bytes:
    """Require leftover pointer text naming *digest*/*size*, not *unlike* bytes.

    Missing file is a hard failure. Does not pin canonical encoding, version
    identifier spelling, or key order.
    """
    try:
        data = ws.read_bytes(relpath)
    except FileNotFoundError:
        raise AssertionError(
            f"working-tree file {relpath!r} is missing; no leftover pointer text"
        ) from None
    assert data != unlike, (
        f"working-tree file {relpath!r} still holds original object bytes"
    )
    assert pointer_matches_digest_and_size(
        data, digest=digest, size=size
    ), (
        "working-tree leftover is not pointer text naming digest "
        f"{digest!r} size={size}: {relpath!r} bytes={data!r}"
    )
    return data


def require_object_bytes_uploaded(
    records: list[RecordedHttpExchange] | None, content: bytes
) -> None:
    """Require *content* reached the endpoint in some request body.

    Does not pin an HTTP verb.
    """
    assert records is not None, (
        "HTTP request log is missing; cannot classify an LFS upload"
    )
    matched = [
        rec
        for rec in records
        if rec.body == content or (content and content in rec.body)
    ]
    assert matched, (
        "no LFS upload of the object bytes "
        f"(n={len(records)} methods={[rec.method for rec in records]!r})"
    )


def require_no_object_bytes_uploaded(
    records: list[RecordedHttpExchange] | None, content: bytes
) -> None:
    """Require *content* did not reach the endpoint in any request body."""
    assert records is not None, (
        "HTTP request log is missing; cannot classify absence of an LFS upload"
    )
    matched = [
        rec
        for rec in records
        if rec.body == content or (content and content in rec.body)
    ]
    assert not matched, (
        "LFS upload of the object bytes was not omitted: "
        f"{[(rec.method, rec.path, len(rec.body)) for rec in matched]!r}"
    )


def disable_http_ssl_verify(ws) -> None:
    """Setup: skip TLS certificate verification on loopback HTTPS fixtures."""
    require_git_config_set(ws, "http.sslverify", "false", local=True)


class _FrontedBatch:
    """Loopback frontend URL in front of a sealed batch fixture."""

    def __init__(self, url: str, records: list[RecordedHttpExchange]) -> None:
        self.url = url
        self.records = records


class _ArmableFrontedBatch(_FrontedBatch):
    """Loopback frontend that can delay TCP handshake until the caller arms it."""

    def __init__(self, url: str, records: list[RecordedHttpExchange], arm, host: str, port: int):
        super().__init__(url, records)
        self._arm = arm
        self._host = host
        self._port = port

    def arm_connection_delay(self) -> None:
        """Start the handshake-delay clock. Call immediately before the transfer."""
        self._arm()

    def require_handshake_blocked(self) -> None:
        """Fail if TCP connect completes while the delay is still holding."""
        _require_handshake_still_blocked(self._host, self._port)


def _self_signed_loopback_tls(directory: Path) -> tuple[Path, Path]:
    cert = directory / "cert.pem"
    key = directory / "key.pem"
    result = subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-nodes",
            "-subj",
            "/CN=127.0.0.1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "openssl failed to mint a loopback TLS fixture certificate: "
        f"{result.stderr}"
    )
    assert cert.is_file() and key.is_file(), (
        f"openssl did not write cert/key under {directory}"
    )
    return cert, key


class _DelayedTLSServer(ThreadingHTTPServer):
    def __init__(self, addr, handler, *, context: ssl.SSLContext, delay: float):
        super().__init__(addr, handler)
        self._tls_ctx = context
        self._tls_delay = delay

    def get_request(self):
        sock, addr = self.socket.accept()
        try:
            time.sleep(self._tls_delay)
            wrapped = self._tls_ctx.wrap_socket(sock, server_side=True)
        except OSError:
            try:
                sock.close()
            except OSError:
                pass
            raise
        return wrapped, addr


@contextmanager
def delayed_tls_handshake_download(
    *, delay_seconds: float, payloads: Sequence[bytes]
) -> Iterator[_FrontedBatch]:
    """HTTPS download fixture that delays the TLS handshake after TCP accept.

    A too-short TLS-handshake bound fails; a longer bound completes the
    handshake and the download. Durations are fixture values, not fixed
    by the PRD.
    """
    assert delay_seconds > 0, (
        f"delay_seconds must be positive, got {delay_seconds!r}"
    )
    payload_list = list(payloads)
    assert payload_list, "delayed_tls_handshake_download needs payloads"
    by_oid: dict[str, bytes] = {}
    action_paths: dict[str, str] = {}
    path_to_oid: dict[str, str] = {}
    for data in payload_list:
        oid = sha256_hex(data)
        assert oid not in by_oid, f"duplicate payload oid {oid}"
        by_oid[oid] = data
        action = f"/obj_{token()}"
        action_paths[oid] = action
        path_to_oid[action] = oid
    hdr_name = f"X-T{token()}"
    hdr_value = f"v{token()}"
    records: list[RecordedHttpExchange] = []
    lock = threading.Lock()
    media = contract_git_orbulk_json_media_type()

    class Handler(BaseHTTPRequestHandler):
        def _handle(self) -> None:
            body = _read_handler_body(self)
            path = _request_path(self.path)
            headers = {str(key): str(value) for key, value in self.headers.items()}
            rec = RecordedHttpExchange(
                method=self.command,
                path=path,
                headers=headers,
                body=body,
            )
            with lock:
                records.append(rec)
            if _is_objects_batch_path(path) and self.command == "POST":
                self._serve_batch(body, headers)
                return
            if path in path_to_oid and self.command in ("GET", "HEAD"):
                self._serve_get(path)
                return
            _send_bytes(self, 404, b"")

        def _serve_batch(self, body: bytes, headers: dict[str, str]) -> None:
            accept = headers.get("Accept") or headers.get("accept")
            content_type = headers.get("Content-Type") or headers.get(
                "content-type"
            )
            if accept is None or content_type is None:
                _send_bytes(self, 406, b"")
                return
            if not (
                _media_type_named(accept, media)
                and _media_type_named(content_type, media)
            ):
                _send_bytes(self, 406, b"")
                return
            try:
                parsed = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                _send_bytes(self, 400, b"")
                return
            if not isinstance(parsed, dict):
                _send_bytes(self, 400, b"")
                return
            operation = str(parsed.get("operation") or "")
            raw_objects = parsed.get("objects")
            if not isinstance(raw_objects, list):
                _send_bytes(self, 400, b"")
                return
            reply_objects: list[dict[str, object]] = []
            for item in raw_objects:
                if not isinstance(item, dict):
                    continue
                oid = str(item.get("oid") or "")
                try:
                    size = int(item.get("size") or 0)
                except (TypeError, ValueError):
                    continue
                out: dict[str, object] = {"oid": oid, "size": size}
                href_oid = oid if oid in action_paths else None
                if href_oid is None and action_paths:
                    href_oid = next(iter(action_paths))
                if href_oid is not None and operation == "download":
                    out["actions"] = {
                        "download": {
                            "href": "http://placeholder" + action_paths[href_oid],
                            "header": {hdr_name: hdr_value},
                        }
                    }
                reply_objects.append(out)
            host = self.headers.get("Host") or "127.0.0.1"
            origin = f"https://{host}"
            _rewrite_placeholder_hrefs(reply_objects, origin)
            payload = json.dumps(
                {
                    "transfer": contract_basic_adapter_name(),
                    "objects": reply_objects,
                }
            ).encode("utf-8")
            _send_bytes(self, 200, payload, content_type=media)

        def _serve_get(self, path: str) -> None:
            if self.headers.get(hdr_name) != hdr_value:
                _send_bytes(self, 403, b"")
                return
            oid = path_to_oid[path]
            data = by_oid[oid]
            if self.command == "HEAD":
                _send_bytes(
                    self, 200, b"", content_type="application/octet-stream"
                )
                return
            _send_bytes(
                self, 200, data, content_type="application/octet-stream"
            )

        def do_GET(self) -> None:
            self._handle()

        def do_HEAD(self) -> None:
            self._handle()

        def do_POST(self) -> None:
            self._handle()

        def log_message(self, format: str, *args: object) -> None:
            return

    with tempfile.TemporaryDirectory(prefix="f15-tls-") as tmp:
        cert, key = _self_signed_loopback_tls(Path(tmp))
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))
        httpd = _DelayedTLSServer(
            ("127.0.0.1", 0),
            Handler,
            context=ctx,
            delay=delay_seconds,
        )
        thread = threading.Thread(
            target=httpd.serve_forever, name="f15-delayed-tls", daemon=True
        )
        thread.start()
        host, port = httpd.server_address[:2]
        try:
            yield _FrontedBatch(f"https://{host}:{port}", records)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5.0)


class _SockFilter(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_ushort),
        ("jt", ctypes.c_ubyte),
        ("jf", ctypes.c_ubyte),
        ("k", ctypes.c_uint32),
    ]


class _SockFprog(ctypes.Structure):
    _fields_ = [
        ("len", ctypes.c_ushort),
        ("filter", ctypes.POINTER(_SockFilter)),
    ]


_SO_ATTACH_FILTER = getattr(socket, "SO_ATTACH_FILTER", 26)
_SO_DETACH_FILTER = getattr(socket, "SO_DETACH_FILTER", 27)
_BPF_RET = 0x06
_BPF_K = 0x00


def _attach_listen_drop(sock: socket.socket) -> tuple[object, object]:
    """Drop incoming packets on a listening socket until detach.

    Keeps the filter objects alive for the kernel pointer in sock_fprog.
    """
    arr = (_SockFilter * 1)(_SockFilter(_BPF_RET | _BPF_K, 0, 0, 0))
    prog = _SockFprog(1, arr)
    blob = ctypes.string_at(ctypes.addressof(prog), ctypes.sizeof(prog))
    try:
        sock.setsockopt(socket.SOL_SOCKET, _SO_ATTACH_FILTER, blob)
    except OSError as exc:
        raise AssertionError(
            "could not attach a listen-socket drop filter for the "
            f"connection-initiation delay fixture: {exc!r}"
        ) from exc
    return arr, prog


def _detach_listen_drop(sock: socket.socket) -> None:
    try:
        sock.setsockopt(socket.SOL_SOCKET, _SO_DETACH_FILTER, 0)
    except OSError:
        pass


def _require_handshake_still_blocked(host: str, port: int) -> None:
    """Fail if TCP connect completes before the delay is armed."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(0.5)
    try:
        probe.connect((host, int(port)))
    except (TimeoutError, socket.timeout):
        return
    except OSError as exc:
        raise AssertionError(
            "connection-initiation delay fixture did not hold the TCP "
            f"handshake (connect error {exc!r})"
        ) from exc
    else:
        raise AssertionError(
            "connection-initiation delay fixture accepted a TCP handshake "
            "before arm_connection_delay"
        )
    finally:
        probe.close()


class _DelayedDialServer(ThreadingHTTPServer):
    """Listen immediately, but complete TCP handshake only after arm+delay."""

    def __init__(self, addr, handler, *, delay: float):
        self._dial_delay = delay
        self._filter_keep: tuple[object, object] | None = None
        self._armed = False
        super().__init__(addr, handler)

    def server_activate(self):
        super().server_activate()
        self._filter_keep = _attach_listen_drop(self.socket)

    def arm(self) -> None:
        if self._armed:
            return
        self._armed = True
        threading.Thread(
            target=self._release_handshake,
            name="f15-delayed-dial-release",
            daemon=True,
        ).start()

    def _release_handshake(self) -> None:
        time.sleep(self._dial_delay)
        _detach_listen_drop(self.socket)


@contextmanager
def delayed_connection_initiation_download(
    *, delay_seconds: float, payloads: Sequence[bytes]
) -> Iterator[_FrontedBatch]:
    """HTTP download fixture that delays TCP handshake completion.

    Incoming SYNs are dropped until *delay_seconds* after
    ``arm_connection_delay()``, so a too-short connection-initiation bound
    fails while a longer bound is allowed to connect and complete the
    download. The caller must arm immediately before the transfer so
    repository setup does not consume the delay. Durations are fixture
    values, not fixed by the PRD. HTTP, not TLS: this is not the
    handshake-timeout arm.
    """
    assert delay_seconds > 0, (
        f"delay_seconds must be positive, got {delay_seconds!r}"
    )
    payload_list = list(payloads)
    assert payload_list, "delayed_connection_initiation_download needs payloads"
    by_oid: dict[str, bytes] = {}
    action_paths: dict[str, str] = {}
    path_to_oid: dict[str, str] = {}
    for data in payload_list:
        oid = sha256_hex(data)
        assert oid not in by_oid, f"duplicate payload oid {oid}"
        by_oid[oid] = data
        action = f"/obj_{token()}"
        action_paths[oid] = action
        path_to_oid[action] = oid
    hdr_name = f"X-T{token()}"
    hdr_value = f"v{token()}"
    records: list[RecordedHttpExchange] = []
    lock = threading.Lock()
    media = contract_git_orbulk_json_media_type()

    class Handler(BaseHTTPRequestHandler):
        def _handle(self) -> None:
            body = _read_handler_body(self)
            path = _request_path(self.path)
            headers = {str(key): str(value) for key, value in self.headers.items()}
            rec = RecordedHttpExchange(
                method=self.command,
                path=path,
                headers=headers,
                body=body,
            )
            with lock:
                records.append(rec)
            if _is_objects_batch_path(path) and self.command == "POST":
                self._serve_batch(body, headers)
                return
            if path in path_to_oid and self.command in ("GET", "HEAD"):
                self._serve_get(path)
                return
            _send_bytes(self, 404, b"")

        def _serve_batch(self, body: bytes, headers: dict[str, str]) -> None:
            accept = headers.get("Accept") or headers.get("accept")
            content_type = headers.get("Content-Type") or headers.get(
                "content-type"
            )
            if accept is None or content_type is None:
                _send_bytes(self, 406, b"")
                return
            if not (
                _media_type_named(accept, media)
                and _media_type_named(content_type, media)
            ):
                _send_bytes(self, 406, b"")
                return
            try:
                parsed = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                _send_bytes(self, 400, b"")
                return
            if not isinstance(parsed, dict):
                _send_bytes(self, 400, b"")
                return
            operation = str(parsed.get("operation") or "")
            raw_objects = parsed.get("objects")
            if not isinstance(raw_objects, list):
                _send_bytes(self, 400, b"")
                return
            reply_objects: list[dict[str, object]] = []
            for item in raw_objects:
                if not isinstance(item, dict):
                    continue
                oid = str(item.get("oid") or "")
                try:
                    size = int(item.get("size") or 0)
                except (TypeError, ValueError):
                    continue
                out: dict[str, object] = {"oid": oid, "size": size}
                href_oid = oid if oid in action_paths else None
                if href_oid is None and action_paths:
                    href_oid = next(iter(action_paths))
                if href_oid is not None and operation == "download":
                    out["actions"] = {
                        "download": {
                            "href": "http://placeholder" + action_paths[href_oid],
                            "header": {hdr_name: hdr_value},
                        }
                    }
                reply_objects.append(out)
            host = self.headers.get("Host") or "127.0.0.1"
            origin = f"http://{host}"
            _rewrite_placeholder_hrefs(reply_objects, origin)
            payload = json.dumps(
                {
                    "transfer": contract_basic_adapter_name(),
                    "objects": reply_objects,
                }
            ).encode("utf-8")
            _send_bytes(self, 200, payload, content_type=media)

        def _serve_get(self, path: str) -> None:
            if self.headers.get(hdr_name) != hdr_value:
                _send_bytes(self, 403, b"")
                return
            oid = path_to_oid[path]
            data = by_oid[oid]
            if self.command == "HEAD":
                _send_bytes(
                    self, 200, b"", content_type="application/octet-stream"
                )
                return
            _send_bytes(
                self, 200, data, content_type="application/octet-stream"
            )

        def do_GET(self) -> None:
            self._handle()

        def do_HEAD(self) -> None:
            self._handle()

        def do_POST(self) -> None:
            self._handle()

        def log_message(self, format: str, *args: object) -> None:
            return

    httpd = _DelayedDialServer(
        ("127.0.0.1", 0),
        Handler,
        delay=delay_seconds,
    )
    thread = threading.Thread(
        target=httpd.serve_forever, name="f15-delayed-dial", daemon=True
    )
    thread.start()
    host, port = httpd.server_address[:2]
    _require_handshake_still_blocked(str(host), int(port))
    try:
        yield _ArmableFrontedBatch(
            f"http://{host}:{port}",
            records,
            httpd.arm,
            str(host),
            int(port),
        )
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5.0)
