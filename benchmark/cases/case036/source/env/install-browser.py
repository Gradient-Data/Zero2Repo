"""Install pinned native browser packages without a product checkout."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

metadata = json.loads(Path("/env-assets/browser.json").read_text())
architecture = subprocess.check_output(["dpkg", "--print-architecture"], text=True).strip()
if architecture != metadata["architecture"]:
    raise RuntimeError(f"Unsupported browser architecture: {architecture}")
with tempfile.TemporaryDirectory(prefix="browser-install-") as temporary:
    packages = []
    for package in metadata["packages"]:
        archive = Path(temporary) / Path(package["Filename"]).name
        subprocess.run([
            "curl", "--fail", "--silent", "--show-error", "--location",
            "--retry", "5", "--connect-timeout", "30",
            "--speed-limit", "10240", "--speed-time", "60",
            metadata["source"] + package["Filename"], "--output", str(archive),
        ], check=True)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != package["SHA256"]:
            raise ValueError(f"Browser package SHA-256 mismatch: {archive.name}: {digest}")
        packages.append(str(archive))
    subprocess.run([
        "apt-get", "--snapshot", os.environ["SNAPSHOT"],
        "-o", "Acquire::Retries=5", "-o", "Acquire::http::Timeout=60",
        "install", "-y", "--no-install-recommends", "fonts-liberation", *packages,
    ], check=True, env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"})
