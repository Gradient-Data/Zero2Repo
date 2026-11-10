"""Provision the interpreter used by the offline judge with pinned wheels."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import shutil

assets = Path("/env-assets")
wheelhouse = Path("/opt/offline-wheels")
wheelhouse.mkdir(parents=True, exist_ok=True)
packages = json.loads((assets / "packages.json").read_text())
python = "/opt/conda/bin/python"
subprocess.run([
    python, "-c",
    "import sys; assert sys.version_info[:2] == (3, 13), sys.version; print(sys.executable, sys.version)",
], check=True)

def fetch(package):
    target = wheelhouse / package["filename"]
    for source in ("official_url",):
        print("Downloading " + package["name"] + " from " + package[source], flush=True)
        result = subprocess.run([
            "curl", "--fail", "--location", "--silent", "--show-error",
            "--retry", "2", "--connect-timeout", "15", "--max-time", "180",
            "--speed-limit", "100000", "--speed-time", "20",
            "--output", str(target), package[source],
        ])
        if result.returncode == 0:
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
            if actual != package["sha256"]:
                raise RuntimeError("SHA256 mismatch for " + package["filename"])
            return
        print("Download failed with exit status " + str(result.returncode), flush=True)
    raise RuntimeError("Both public sources failed for " + package["filename"])

with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    list(pool.map(fetch, packages))
subprocess.run([
    python, "-m", "pip", "install", "--no-index",
    "--find-links", str(wheelhouse),
    *[p["name"] + "==" + p["version"] for p in packages],
], check=True)
Path("/opt/conda/pip.conf").write_text(
    "[global]\nno-index = true\nfind-links = /opt/offline-wheels\n")
shutil.copyfile(assets / "check-environment.py", "/opt/check-environment.py")
subprocess.run([python, "/opt/check-environment.py"], check=True)
