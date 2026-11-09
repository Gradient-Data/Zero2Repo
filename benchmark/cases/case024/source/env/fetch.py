"""Fetch compatible locked distributions and verify their original hashes."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import parse_wheel_filename

assets = Path('/env-assets')
destination = Path('/opt/packages')
destination.mkdir(exist_ok=True)
requirements = [Requirement(line.split(' \\')[0]) for line in (assets / 'requirements.txt').read_text().splitlines() if line and not line[0].isspace()]
selected = {(r.name, next(iter(r.specifier)).version) for r in requirements if r.marker is None or r.marker.evaluate()}
selected.add(('uv-build', '0.9.22'))
ranks = {tag: index for index, tag in enumerate(sys_tags())}

def fetch(package):
    wheels = []
    for wheel in package.get('wheels', []):
        tags = parse_wheel_filename(Path(urlsplit(wheel['url']).path).name)[3]
        matches = [ranks[tag] for tag in tags if tag in ranks]
        if matches:
            wheels.append((min(matches), wheel))
    artifact = min(wheels, key=lambda item: item[0])[1] if wheels else package['sdist']
    url = artifact['url']
    target = destination / Path(urlsplit(url).path).name
    command = ['curl', '--fail', '--location', '--silent', '--show-error', '--retry', '3', '--connect-timeout', '20', '--speed-limit', '1024', '--speed-time', '60', '--output', str(target)]
    subprocess.run(command + [url], check=True)
    actual = hashlib.file_digest(target.open('rb'), 'sha256').hexdigest()
    if 'sha256:' + actual != artifact['hash']:
        raise ValueError(f'Checksum mismatch: {target.name}')
    print(f'Verified {target.name}', flush=True)

packages = [p for p in json.loads((assets / 'packages.json').read_text()) if (p['name'], p['version']) in selected]
if {(p['name'],p['version']) for p in packages} != selected:
    raise ValueError('Missing locked requirement')
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
    list(executor.map(fetch, packages))
