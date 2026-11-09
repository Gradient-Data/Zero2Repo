"""Install locked third-party dependencies into the judge interpreter."""
import concurrent.futures
import hashlib
import html.parser
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
import urllib.parse

from pip._vendor.packaging.markers import Marker, default_environment
from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import parse_wheel_filename
from pip._vendor.packaging.version import Version

assets = Path('/env-assets')
metadata = json.loads((assets / 'dependencies.json').read_text())
environment = default_environment()
tags = {tag: rank for rank, tag in enumerate(sys_tags())}
wheelhouse = Path('/opt/dependency-wheels')
wheelhouse.mkdir(parents=True, exist_ok=True)


def applies(expression, extra=''):
    return not expression or Marker(expression).evaluate({**environment, 'extra': extra})


selected = {}
visited = set()


def visit(name, version=None, extras=()):
    candidates = [p for p in metadata['packages'] if p['name'] == name
                  and (version is None or p['version'] == version)
                  and (not p.get('resolution-markers') or any(applies(m) for m in p['resolution-markers']))]
    if len(candidates) != 1:
        raise RuntimeError(f'Ambiguous or missing locked dependency: {name}: {candidates}')
    package = candidates[0]
    if name in selected and selected[name]['version'] != package['version']:
        raise RuntimeError(f'Conflicting versions for {name}')
    selected[name] = package
    key = (name, tuple(sorted(extras)))
    if key in visited:
        return
    visited.add(key)
    dependencies = list(package.get('dependencies', []))
    for extra in extras:
        dependencies.extend(package.get('optional-dependencies', {}).get(extra, []))
    for dep in dependencies:
        if any(applies(dep.get('marker'), e) for e in ('', *extras)):
            visit(dep['name'], dep.get('version'), dep.get('extra', []))


for entry in metadata['roots']:
    requirement = Requirement(entry)
    if requirement.marker is None or requirement.marker.evaluate(environment):
        visit(requirement.name, extras=requirement.extras)
        if Version(selected[requirement.name]['version']) not in requirement.specifier:
            raise RuntimeError(f'Locked version violates declaration: {entry}')


class Links(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.extend(value for key, value in attrs if key == 'href')


def curl(url, destination):
    subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                    '--retry', '3', '--connect-timeout', '20', '--max-time', '1800',
                    '--speed-limit', '1024', '--speed-time', '30',
                    '--output', str(destination), url], check=True)


def download_map(url, destination):
    headers = subprocess.check_output(['curl', '--fail', '--location', '--silent',
        '--show-error', '--head', '--retry', '3', '--connect-timeout', '20',
        '--max-time', '60', url], text=True)
    lengths = [int(line.split(':', 1)[1].strip()) for line in headers.splitlines()
               if line.lower().startswith('content-length:')]
    if not lengths:
        raise RuntimeError(f'Missing content length: {url}')
    size = lengths[-1]
    with tempfile.TemporaryDirectory() as temporary:
        def part(start):
            end = min(start + 262143, size - 1)
            target = Path(temporary) / str(start)
            subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                '--retry', '3', '--connect-timeout', '20', '--max-time', '180',
                '--speed-limit', '1024', '--speed-time', '30', '--range',
                f'{start}-{end}', '--output', str(target), url], check=True)
            if target.stat().st_size != end - start + 1:
                raise RuntimeError(f'Invalid range response: {url}')
            return target
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            pieces = list(pool.map(part, range(0, size, 262144)))
        with destination.open('wb') as output:
            for piece in pieces:
                output.write(piece.read_bytes())


def fetch(package):
    choices = []
    for artifact in package['wheels']:
        filename = urllib.parse.unquote(urllib.parse.urlparse(artifact['url']).path.split('/')[-1])
        _, _, _, wheel_tags = parse_wheel_filename(filename)
        ranks = [tags[tag] for tag in wheel_tags if tag in tags]
        if ranks:
            choices.append((min(ranks), filename, artifact))
    if not choices:
        raise RuntimeError(f'No compatible locked wheel: {package["name"]}')
    _, filename, artifact = min(choices, key=lambda c: c[0])
    url = artifact['url']
    destination = wheelhouse / filename
    curl(url, destination)
    expected = artifact['hash'].split(':', 1)[1]
    if hashlib.sha256(destination.read_bytes()).hexdigest() != expected:
        raise RuntimeError(f'Checksum mismatch: {filename}')
    print(f'Verified {filename}', flush=True)
    return destination


with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    wheels = list(pool.map(fetch, selected.values()))
subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index',
                '--no-deps', *map(str, wheels)], check=True)
(Path(sys.prefix) / 'pip.conf').write_text('[global]\nno-index = true\nfind-links = /opt/dependency-wheels\n')
subprocess.run(['chmod', '-R', 'a+rX', sys.prefix, '/opt/dependency-wheels'], check=True)

# Natural Earth has no Alibaba Cloud mirror. Fetch its pinned public release.
def fetch_map(entry):
    destination = Path('/opt/cartopy-data') / entry['directory']
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / 'map.zip'
        download_map(entry['url'], archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != entry['sha256']:
            raise RuntimeError(f'Checksum mismatch: {entry["url"]}')
        with zipfile.ZipFile(archive) as content:
            for member in content.infolist():
                if member.is_dir():
                    continue
                if Path(member.filename).name != member.filename:
                    raise RuntimeError(f'Unexpected archive path: {member.filename}')
                (destination / member.filename).write_bytes(content.read(member))
    print(f'Verified map data: {entry["url"]}', flush=True)


with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    list(pool.map(fetch_map, json.loads((assets / 'map-data.json').read_text())))
site = subprocess.check_output([sys.executable, '-c',
    'import sysconfig; print(sysconfig.get_path("purelib"))'], text=True).strip()
(Path(site) / 'cartopy' / 'siteconfig.py').write_text(
    'from pathlib import Path\n\ndef update_config(config):\n'
    '    config["pre_existing_data_dir"] = Path("/opt/cartopy-data")\n')
subprocess.run(['chmod', '-R', 'a+rX', '/opt/cartopy-data'], check=True)
Path('/opt/check-lock.py').write_text((assets / 'check-lock.py').read_text())

# Preserve pinned source version metadata for both warm and offline builds.
for name in ('product-version.json', 'with-product-version.py'):
    Path('/opt', name).write_bytes((assets / name).read_bytes())

# Check in a fresh process: pip may have replaced packages imported by this installer.
subprocess.run([sys.executable, '-c', """
import json
import sys
from importlib.metadata import version
import pandas
import pytest
from shapely.geometry import Point

expected = json.loads(sys.argv[1])
for name, pinned in expected.items():
    actual = version(name)
    if actual != pinned:
        raise RuntimeError(f'Installed version mismatch: {name}: {actual} != {pinned}')
print(json.dumps({'executable': sys.executable, 'prefix': sys.prefix,
                  'path': sys.path, 'versions': expected,
                  'pandas': pandas.__file__, 'pytest': pytest.__file__}, sort_keys=True))
""", json.dumps({name: package['version'] for name, package in selected.items()})], check=True)
