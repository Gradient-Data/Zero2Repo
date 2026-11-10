"""Fetch exact third-party artifacts and verify their recorded SHA-256 digests."""
import hashlib
import json
import pathlib
import subprocess
from urllib.parse import urlsplit

assets = pathlib.Path('/env-assets')

def fetch(entry, target):
    print(f"Fetching {entry['name']}: {entry['url']}", flush=True)
    subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                    '--retry', '4', '--connect-timeout', '30',
                    '--speed-limit', '1024', '--speed-time', '60',
                    entry['url'], '--output', str(target)], check=True)
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != entry['sha256']:
        raise ValueError(f"SHA-256 mismatch for {entry['name']}: {actual}")

for entry in json.loads((assets / 'packages.json').read_text()):
    target = pathlib.Path('/opt/offline/wheels') / pathlib.Path(urlsplit(entry['url']).path).name
    fetch(entry, target)
for entry in json.loads((assets / 'modules.json').read_text()):
    archive = pathlib.Path('/opt/offline') / (entry['name'] + '.tar.gz')
    fetch(entry, archive)
    target = pathlib.Path('/opt/offline/modules') / entry['name']
    target.mkdir()
    subprocess.run(['tar', '-xzf', str(archive), '--strip-components=1', '-C', str(target)], check=True)
    archive.unlink()
