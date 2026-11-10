"""Install the integrity-locked, standalone MinIO runtime; never start a daemon."""

import hashlib
import json
from pathlib import Path
import platform
import subprocess
import tempfile


def install():
    lock = json.loads(Path(__file__).with_name("s3-server.lock.json").read_text())
    if platform.system().lower() != lock["platform"] or platform.machine() != lock["machine"]:
        raise RuntimeError("The locked MinIO artifact requires Linux x86_64")
    destination = Path("/usr/local/bin/minio")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as staging:
        binary = Path(staging) / "minio"
        subprocess.run(
            ["curl", "--fail", "--location", "--silent", "--show-error",
             "--retry", "3", "--connect-timeout", "20", "--max-time", "900",
             "--speed-limit", "1024", "--speed-time", "30",
             lock["url"], "--output", str(binary)],
            check=True,
        )
        with binary.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != lock["sha256"]:
            raise RuntimeError(f"MinIO checksum mismatch: {digest}")
        binary.chmod(0o755)
        subprocess.run([str(binary), "--version"], check=True)
        binary.replace(destination)
    print(f"Verified and installed MinIO {lock['version']} at {destination}", flush=True)


if __name__ == "__main__":
    install()
