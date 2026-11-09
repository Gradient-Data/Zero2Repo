"""Fetch locked artifacts, failing on download errors or digest mismatches."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse

manifest = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/env-assets/packages.json')
root = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('/opt/wheels')
root.mkdir(parents=True, exist_ok=True)


def download(url, target):
    command = [
        'curl', '--silent', '--show-error', '--fail', '--location',
        '--retry', '5', '--retry-all-errors', '--connect-timeout', '30',
        '--max-time', '1800', '--speed-limit', '1024', '--speed-time', '60',
        '--output', str(target),
    ]
    subprocess.run([*command, url], check=True)


def fetch(package):
    target = root / Path(urlparse(package['url']).path).name
    size = package.get('size')
    download(package['url'], target)
    if size is not None and target.stat().st_size != size:
        raise ValueError(f'Size mismatch for {target.name}')
    with target.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != package['sha256']:
        raise ValueError(f'SHA256 mismatch for {target.name}: {actual}')


with ThreadPoolExecutor(max_workers=4) as workers:
    list(workers.map(fetch, json.loads(manifest.read_text())))
