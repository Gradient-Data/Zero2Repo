"""Fetch hash-verified wheels, then install only third-party dependencies."""
import concurrent.futures
import hashlib
import html.parser
import json
from pathlib import Path
import subprocess
import sys
import urllib.parse
import urllib.request

from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import parse_wheel_filename

subprocess.run([sys.executable, '/env-assets/authorize_self.py'], check=True)

# Ubuntu packages come from Canonical's official archive snapshot 20261107T063422Z
# (the time this environment was recorded), so apt resolves the same versions
# on any host.
SNAPSHOT = '20261107T063422Z'
subprocess.run(['apt-get', '--snapshot', SNAPSHOT, '-o', 'Acquire::Retries=3', 'update'], check=True)
subprocess.run(['apt-get', '--snapshot', SNAPSHOT, 'install', '-y', '--no-install-recommends', 'graphviz=2.42.2-9ubuntu0.1'], check=True)

ASSETS = Path('/env-assets')
WHEELS = Path('/opt/dependency-wheels')
WHEELS.mkdir(parents=True, exist_ok=True)
TAGS = {tag: rank for rank, tag in enumerate(sys_tags())}

class Links(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.extend(value for key, value in attrs if key == 'href')

def fetch(package):
    candidates = []
    for wheel in package['wheels']:
        filename = urllib.parse.unquote(urllib.parse.urlsplit(wheel['url']).path.rsplit('/', 1)[1])
        tags = parse_wheel_filename(filename)[3]
        ranks = [TAGS[tag] for tag in tags if tag in TAGS]
        if ranks:
            candidates.append((min(ranks), filename, wheel))
    if not candidates:
        raise RuntimeError(f"No compatible locked wheel: {package['name']}=={package['version']}")
    _, filename, wheel = min(candidates, key=lambda entry: entry[0])
    destination = WHEELS / filename
    urls = [wheel['url']]
    for url in urls:
        result = subprocess.run(['curl', '--fail', '--location', '--retry', '3',
                                 '--connect-timeout', '20', '--max-time', '300',
                                 '--speed-limit', '1024', '--speed-time', '30',
                                 '--silent', '--show-error', '--output', str(destination), url])
        if result.returncode == 0:
            digest = hashlib.sha256(destination.read_bytes()).hexdigest()
            if 'sha256:' + digest != wheel['hash']:
                raise RuntimeError(f'Checksum mismatch: {filename}')
            print(f"Verified {filename} from {urllib.parse.urlsplit(url).netloc}", flush=True)
            return f"{package['name']}=={package['version']} --hash=sha256:{digest}"
        print(f'Download failed: {url} (exit {result.returncode})', flush=True)
    raise RuntimeError(f'All declared sources failed: {filename}')

packages = json.loads((ASSETS / 'dependencies.json').read_text())
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
    requirements = list(pool.map(fetch, packages))
requirements_path = Path('/opt/dependency-requirements.txt')
requirements_path.write_text('\n'.join(requirements) + '\n')
subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index',
                '--find-links', str(WHEELS), '--require-hashes', '--no-deps',
                '-r', str(requirements_path)], check=True)
Path('/etc/pip.conf').write_text('[global]\nno-index = true\nfind-links = /opt/dependency-wheels\n')
# Tokenization data is pinned and hash-checked by the installed tokenizer.
# These data files have no Alibaba Cloud mirror; use their upstream URLs.
subprocess.run([sys.executable, '/env-assets/tokenizer_data.py'], check=True)
subprocess.run(['chmod', '-R', 'a+rX', sys.prefix, '/opt/dependency-wheels', '/opt/tokenizer-data'], check=True)
