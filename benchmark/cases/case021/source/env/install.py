import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit


assets = Path('/env-assets')
wheels = Path('/opt/offline-wheels')
wheels.mkdir(parents=True, exist_ok=True)
for artifact in json.loads((assets / 'dependencies.json').read_text()):
    target = wheels / Path(urlsplit(artifact['url']).path).name
    subprocess.run([
        'curl', '--fail', '--location', '--retry', '4', '--retry-all-errors',
        '--connect-timeout', '30', '--speed-limit', '1024', '--speed-time', '60',
        '--output', str(target), artifact['url'],
    ], check=True)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != artifact['sha256']:
        raise RuntimeError(f'Checksum mismatch: {target.name}')
subprocess.run([
    sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps',
    '--find-links', str(wheels), '--require-hashes',
    '--requirement', str(assets / 'requirements.txt'),
], check=True)

subprocess.run([sys.executable, str(assets / 'install_native.py')], check=True)
