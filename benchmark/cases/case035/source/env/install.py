"""Fetch locked third-party wheels and install them into the system interpreter."""
import base64
import concurrent.futures
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import sys
from urllib.parse import unquote, urlencode, urljoin, urlsplit

from pip._vendor.packaging.markers import Marker
from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import parse_wheel_filename

DEST = Path('/opt/offline-wheels')
TAGS = {tag: rank for rank, tag in enumerate(sys_tags())}


def curl(url, output=None):
    cmd = ['curl', '--fail', '--show-error', '--silent', '--location', '--retry', '3',
           '--connect-timeout', '20', '--max-time', '180', '--speed-limit', '1024', '--speed-time', '30', url]
    if output:
        cmd += ['--output', str(output)]
    return subprocess.check_output(cmd)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.urls.extend(value for key, value in attrs if key == 'href')


def resolve_artifacts(package):
    """Resolve content-addressed PyPI references through the public metadata API.

    Only metadata comes from deps.dev; artifact downloads use official PyPI. Never infer a distribution name from
    a local alias or replace a locked hash with registry metadata.
    """
    if package['registry'] != 'pypi':
        raise ValueError('Unsupported registry: ' + package['registry'])
    names = set()
    files = []
    for entry in package['files']:
        if entry['kind'] != 'wheel':
            continue
        algorithm, digest = entry['hash'].split(':', 1)
        if algorithm != 'sha256':
            raise ValueError('Expected a SHA-256 artifact reference')
        query = urlencode({'hash.type': 'SHA256',
                           'hash.value': base64.b64encode(bytes.fromhex(digest)).decode()})
        metadata = json.loads(curl('https://api.deps.dev/v3alpha/query?' + query))
        matches = set()
        for result in metadata['results']:
            key = result['version']['versionKey']
            if key['system'] != 'PYPI' or key['version'] != package['version']:
                continue
            for artifact in result['artifacts']:
                url = urlsplit(artifact['url'])
                if url.scheme != 'https' or url.netloc != 'files.pythonhosted.org':
                    raise ValueError('Unexpected artifact origin: ' + artifact['url'])
                filename = unquote(url.path.rsplit('/', 1)[-1])
                if filename.endswith('.whl'):
                    name, version, _, _ = parse_wheel_filename(filename)
                    if str(version) != package['version'] or name != key['name']:
                        raise ValueError('Artifact metadata disagrees with locked version')
                    matches.add((key['name'], filename))
        if len(matches) != 1:
            raise RuntimeError('Cannot locate unique locked artifact: ' + entry['hash'])
        name, filename = matches.pop()
        names.add(name)
        files.append({'file': filename, 'hash': entry['hash']})
    if len(names) != 1:
        raise RuntimeError('Content references must identify one distribution')
    return {**package, 'name': names.pop(), 'files': files}


def fetch(package):
    markers = package.get('markers')
    if isinstance(markers, dict):
        markers = ' or '.join('(' + markers.get(group, '') + ')' for group in package['groups'] if markers.get(group)) if all(group in markers for group in package['groups']) else None
    if markers and not Marker(markers).evaluate():
        return None
    if 'registry' in package:
        package = resolve_artifacts(package)
    candidates = []
    for entry in package['files']:
        if entry['file'].endswith('.whl'):
            tags = parse_wheel_filename(entry['file'])[3]
            ranks = [TAGS[t] for t in tags if t in TAGS]
            if ranks:
                candidates.append((min(ranks), entry))
    if not candidates:
        raise RuntimeError('No compatible locked wheel: ' + package['name'])
    entry = min(candidates, key=lambda item: item[0])[1]
    metadata = json.loads(curl('https://pypi.org/pypi/' + package['name'] + '/' + package['version'] + '/json'))
    urls = [u['url'] for u in metadata['urls'] if u['filename'] == entry['file']]
    if len(urls) != 1:
        raise RuntimeError('Cannot locate unique locked artifact: ' + entry['file'])
    target = DEST / entry['file']
    curl(urls[0], target)
    if 'sha256:' + hashlib.sha256(target.read_bytes()).hexdigest() != entry['hash']:
        raise RuntimeError('Checksum mismatch: ' + entry['file'])
    print('Verified ' + entry['file'], flush=True)
    return str(target)


if __name__ == '__main__':
    DEST.mkdir(parents=True, exist_ok=True)
    packages = json.loads(Path('/env-assets/dependencies.json').read_text())
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        wheels = [path for path in pool.map(fetch, packages) if path]
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps', *wheels], check=True)
    Path('/etc/pip.conf').write_text('[global]\nno-index = true\nfind-links = /opt/offline-wheels\ndisable-pip-version-check = true\n')
