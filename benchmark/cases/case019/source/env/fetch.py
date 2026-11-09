"""Fetch locked wheels with bounded transfers and verify their original hashes."""
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import shlex
import subprocess
from urllib.parse import unquote, urljoin, urlsplit

from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import parse_wheel_filename, canonicalize_name


class Index(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])


def curl(url, destination):
    subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                    '--retry', '3', '--connect-timeout', '30',
                    '--speed-limit', '1024', '--speed-time', '30',
                    '--max-time', '300', '--output', str(destination), url],
                   check=True)


tags = {tag: rank for rank, tag in enumerate(sys_tags())}
resolved = []
for line in Path('/env-assets/requirements.txt').read_text().splitlines():
    spec, *hash_options = shlex.split(line)
    if spec.startswith('https://'):
        # A locked wheel recorded by its official file URL.
        version_option, *hash_options = hash_options
        if not version_option.startswith('--version=') or not spec.endswith('.whl'):
            raise ValueError(f'Invalid artifact file record: {line}')
        name = None
        version = version_option.removeprefix('--version=')
        indexes = ()
    else:
        name, version = spec.split('==')
        indexes = ('https://pypi.org/simple/' + canonicalize_name(name) + '/',)
    if not hash_options or any(not item.startswith('--hash=sha256:')
                               for item in hash_options):
        raise ValueError(f'Missing or invalid SHA-256 pins: {line}')
    allowed = {item.removeprefix('--hash=sha256:') for item in hash_options}
    candidates = []
    if not indexes:
        filename = unquote(urlsplit(spec).path.rsplit('/', 1)[-1])
        _, wheel_version, _, wheel_tags = parse_wheel_filename(filename)
        ranks = [tags[tag] for tag in wheel_tags if tag in tags]
        if str(wheel_version) == version and ranks:
            candidates.append((min(ranks), filename, spec))
    for index_url in indexes:
        curl(index_url, '/tmp/package-index.html')
        index = Index()
        index.feed(Path('/tmp/package-index.html').read_text())
        for href in index.links:
            filename = unquote(urlsplit(href).path.rsplit('/', 1)[-1])
            if not filename.endswith('.whl'):
                continue
            wheel_name, wheel_version, _, wheel_tags = parse_wheel_filename(filename)
            ranks = [tags[tag] for tag in wheel_tags if tag in tags]
            if ((name is None or wheel_name == canonicalize_name(name))
                    and str(wheel_version) == version and ranks):
                candidates.append((min(ranks), filename, urljoin(index_url, href)))
        if candidates:
            break
        print(f'No compatible locked wheel for {spec} at {index_url}', flush=True)
    if not candidates:
        raise RuntimeError(f'No compatible locked wheel for {spec}')
    _, filename, url = min(candidates)
    target = Path('/opt/wheels') / filename
    print(f'Fetching {spec} from {url}', flush=True)
    curl(url, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest not in allowed:
        raise RuntimeError(f'Lock hash mismatch: {filename}: {digest}')
    wheel_name, wheel_version, _, _ = parse_wheel_filename(filename)
    resolved.append(f'{wheel_name}=={wheel_version} ' + ' '.join(hash_options))

Path('/opt/wheels/requirements.txt').write_text('\n'.join(resolved) + '\n')
