"""Fetch the pinned public Maven artifacts into the system offline repository."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess

ASSETS = Path('/env-assets')
DESTINATION = Path('/opt/maven-repository')


def fetch(entry):
    relative = entry['path']
    destination = DESTINATION / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        'curl', '-fsSL', '--retry', '3', '--connect-timeout', '20',
        '--speed-limit', '1024', '--speed-time', '30', '--max-time', '300',
    ]
    subprocess.run(command + [entry['source'] + relative, '-o', str(destination)], check=True)
    actual = hashlib.sha256(destination.read_bytes()).hexdigest()
    if actual != entry['sha256']:
        raise ValueError(f'SHA-256 mismatch for {relative}: {actual}')
    destination.chmod(0o644)


# Login shells are used for both image probes and benchmark commands.
subprocess.run([
    'install', '-m', '644', str(ASSETS / 'python-safe-path.sh'),
    '/etc/profile.d/python-safe-path.sh',
], check=True)
subprocess.run(['bash', str(ASSETS / 'toolchain.sh')], check=True)
entries = json.loads((ASSETS / 'artifacts.json').read_text())
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    for _ in pool.map(fetch, entries):
        pass
print(f'Installed and verified {len(entries)} Maven artifacts.', flush=True)
