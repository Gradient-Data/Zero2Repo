"""Certificate authority for the supply proxy.

The proxy reads HTTPS requests to package hosts by presenting a certificate
for that host signed by its own CA. The CA is generated once per store with
the ``openssl`` command and then never changes, so containers that trust it
keep trusting it across runs. Host certificates are issued on demand and
cached next to it.

Nothing here is baked into an image. Containers get the CA at run time:
``ca.pem`` alone (for ``NODE_EXTRA_CA_CERTS``) and ``ca-bundle.pem``, the
host's public roots followed by the CA (for clients that take one bundle).
"""

from __future__ import annotations

import fcntl
import os
import re
import ssl
import subprocess
import tempfile
from pathlib import Path

__all__ = ["ProxyCA", "CAError"]

_CA_SUBJECT = "/CN=cbrun supply proxy CA"
_HOST_RE = re.compile(r"[A-Za-z0-9.-]{1,253}")


class CAError(RuntimeError):
    """The CA or a host certificate cannot be created or loaded."""


class ProxyCA:
    def __init__(self, directory: Path, *, roots_file: Path | None = None) -> None:
        self.dir = Path(directory)
        self.hosts_dir = self.dir / "hosts"
        self.ca_cert = self.dir / "ca.pem"
        self.ca_key = self.dir / "ca.key"
        self.host_key = self.dir / "host.key"
        # Mounted into containers as one read-only directory.
        self.mount_dir = self.dir / "mount"
        self.bundle = self.mount_dir / "ca-bundle.pem"
        self.hosts_dir.mkdir(parents=True, exist_ok=True)
        self.mount_dir.mkdir(parents=True, exist_ok=True)
        self._roots_file = roots_file
        with self._locked("ca"):
            if not self.ca_cert.is_file() or not self.ca_key.is_file():
                self._create_ca()
            if not self.host_key.is_file():
                _openssl("genrsa", "-out", str(self.host_key), "2048")
                os.chmod(self.host_key, 0o640)
            self._write_mount()

    # Public ----------------------------------------------------------------

    def server_context(self, host: str) -> ssl.SSLContext:
        """TLS server context presenting a certificate for *host*."""
        cert = self._host_cert(host)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(cert), str(self.host_key))
        # One request at a time per connection: never negotiate HTTP/2.
        ctx.set_alpn_protocols(["http/1.1"])
        return ctx

    def pem(self) -> bytes:
        return self.ca_cert.read_bytes()

    def bundle_pem(self) -> bytes:
        return self.bundle.read_bytes()

    # Internals -------------------------------------------------------------

    def _locked(self, name: str):
        return _FileLock(self.dir / f".{name}.lock")

    def _create_ca(self) -> None:
        _openssl("genrsa", "-out", str(self.ca_key), "2048")
        os.chmod(self.ca_key, 0o640)
        with tempfile.NamedTemporaryFile("w", suffix=".cnf", delete=False) as cnf:
            cnf.write(
                "[req]\ndistinguished_name=dn\n[dn]\n"
                "[ext]\n"
                "basicConstraints=critical,CA:TRUE\n"
                "keyUsage=critical,keyCertSign,cRLSign\n"
                "subjectKeyIdentifier=hash\n"
            )
        try:
            _openssl(
                "req", "-x509", "-new", "-key", str(self.ca_key), "-sha256",
                "-days", "7300", "-subj", _CA_SUBJECT,
                "-config", cnf.name, "-extensions", "ext",
                "-out", str(self.ca_cert),
            )
        finally:
            os.unlink(cnf.name)

    def _write_mount(self) -> None:
        roots = self._roots_file or _host_roots_file()
        bundle = roots.read_bytes().rstrip(b"\n") + b"\n" + self.pem()
        (self.mount_dir / "ca.pem").write_bytes(self.pem())
        if not self.bundle.is_file() or self.bundle.read_bytes() != bundle:
            tmp = self.bundle.with_suffix(".tmp")
            tmp.write_bytes(bundle)
            os.replace(tmp, self.bundle)
        for path in (self.mount_dir / "ca.pem", self.bundle):
            os.chmod(path, 0o644)

    def _host_cert(self, host: str) -> Path:
        if not _HOST_RE.fullmatch(host):
            raise CAError(f"refusing to issue a certificate for {host!r}")
        cert = self.hosts_dir / f"{host}.pem"
        if cert.is_file():
            return cert
        with self._locked(f"host-{host}"):
            if cert.is_file():
                return cert
            # Work next to the destination: the final rename must not cross
            # filesystems (the store usually is not on /tmp's).
            with tempfile.TemporaryDirectory(dir=self.hosts_dir) as tmp:
                csr = Path(tmp) / "host.csr"
                ext = Path(tmp) / "ext.cnf"
                ext.write_text(
                    "basicConstraints=CA:FALSE\n"
                    "keyUsage=critical,digitalSignature,keyEncipherment\n"
                    "extendedKeyUsage=serverAuth\n"
                    f"subjectAltName=DNS:{host}\n"
                    "subjectKeyIdentifier=hash\n"
                    "authorityKeyIdentifier=keyid\n",
                    encoding="utf-8",
                )
                _openssl(
                    "req", "-new", "-key", str(self.host_key),
                    "-subj", f"/CN={host}", "-out", str(csr),
                )
                out = Path(tmp) / "host.pem"
                _openssl(
                    "x509", "-req", "-in", str(csr), "-CA", str(self.ca_cert),
                    "-CAkey", str(self.ca_key), "-CAcreateserial",
                    "-CAserial", str(Path(tmp) / "ca.srl"),
                    "-days", "825", "-sha256", "-extfile", str(ext), "-out", str(out),
                )
                os.replace(out, cert)
        return cert


class _FileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self) -> None:
        self.handle = open(self.path, "a")
        fcntl.flock(self.handle, fcntl.LOCK_EX)

    def __exit__(self, *exc) -> None:
        assert self.handle is not None
        fcntl.flock(self.handle, fcntl.LOCK_UN)
        self.handle.close()


def _host_roots_file() -> Path:
    """The host's public root bundle; the proxy's CA is appended to it."""
    paths = ssl.get_default_verify_paths()
    for candidate in (paths.cafile, paths.openssl_cafile, "/etc/ssl/certs/ca-certificates.crt"):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise CAError(
        "cannot find the host's CA bundle to merge with the proxy CA "
        f"(checked {paths.cafile!r}, {paths.openssl_cafile!r})"
    )


def _openssl(*args: str) -> None:
    try:
        proc = subprocess.run(["openssl", *args], capture_output=True, text=True)
    except OSError as exc:
        raise CAError(f"cannot run openssl: {exc}") from exc
    if proc.returncode != 0:
        raise CAError(f"openssl {args[0]} failed: {proc.stderr.strip()}")
