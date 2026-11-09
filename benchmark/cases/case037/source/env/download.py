"""Fetch the pinned third-party artifacts, verifying their published hashes."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess


destination = Path('/opt/offline-packages')
destination.mkdir(parents=True, exist_ok=True)


def fetch(package):
    path = destination / package['filename']
    subprocess.run([
        'curl', '--fail', '--location', '--show-error', '--silent',
        '--retry', '5', '--retry-all-errors', '--connect-timeout', '20',
        '--speed-limit', '1024', '--speed-time', '30', '--max-time', '600',
        '--output', str(path), package['url'],
    ], check=True)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != package['sha256']:
        raise ValueError(f"SHA256 mismatch for {path.name}: {actual}")
    print(f"Verified {path.name}", flush=True)


packages = json.loads(Path('/env-assets/packages.json').read_text())
with ThreadPoolExecutor(max_workers=6) as pool:
    list(pool.map(fetch, packages))
