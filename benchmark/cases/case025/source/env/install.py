"""Install the lock-pinned third-party runtime and test dependencies."""
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import sys
from urllib.parse import unquote, urljoin, urlsplit

from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import parse_wheel_filename

ROOT = Path('/opt/offline-dependencies')
ROOT.mkdir(parents=True, exist_ok=True)
TAGS = {tag: rank for rank, tag in enumerate(sys_tags())}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.urls.extend(value for key, value in attrs if key == 'href')


def fetch(url, target):
    subprocess.run(['curl', '--fail', '--location', '--retry', '3',
                    '--connect-timeout', '20', '--max-time', '180',
                    '--speed-limit', '1024', '--speed-time', '30',
                    '--output', str(target), url], check=True)


artifacts = []
for package in json.loads(Path('/env-assets/dependencies.json').read_text()):
    candidates = []
    for wheel in package.get('wheels', []):
        filename = unquote(urlsplit(wheel['url']).path.rsplit('/', 1)[-1])
        tags = parse_wheel_filename(filename)[3]
        ranks = [TAGS[tag] for tag in tags if tag in TAGS]
        if ranks:
            candidates.append((min(ranks), wheel))
    artifact = min(candidates, key=lambda pair: pair[0])[1] if candidates else package['sdist']
    filename = unquote(urlsplit(artifact['url']).path.rsplit('/', 1)[-1])
    url = artifact['url']
    target = ROOT / filename
    fetch(url, target)
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if artifact['hash'] != 'sha256:' + actual:
        raise ValueError('Lock checksum mismatch: ' + filename)
    artifacts.append(str(target))

wheels = ROOT / 'wheels'
wheels.mkdir(exist_ok=True)
subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-index', '--no-deps',
                '--no-build-isolation', '--wheel-dir', str(wheels), *artifacts], check=True)
subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps',
                *map(str, sorted(wheels.glob('*.whl')))], check=True)
