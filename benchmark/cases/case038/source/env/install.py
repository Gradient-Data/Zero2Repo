"""Acquire hash-locked registry wheels and install isolated schema dependencies."""
import email
import hashlib
from html.parser import HTMLParser
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from urllib.parse import unquote, urljoin, urlsplit
import zipfile

from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import parse_wheel_filename
from pip._vendor.packaging.version import Version

ASSETS = Path('/env-assets')
STORE = Path('/opt/schema-dependencies')
TARGET = Path(sysconfig.get_path('purelib'))
LOCK = json.loads((ASSETS / 'dependencies.json').read_text())
TAGS = set(sys_tags())

for relative, expected in LOCK['asset_sha256'].items():
    if hashlib.sha256((ASSETS / relative).read_bytes()).hexdigest() != expected:
        raise ValueError(f'Adapter integrity mismatch: {relative}')



def download(url, destination):
    subprocess.run(['curl', '--fail', '--location', '--retry', '3',
                    '--connect-timeout', '30', '--max-time', '300',
                    '--speed-limit', '1024', '--speed-time', '30',
                    '--output', str(destination), url], check=True)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            values = dict(attrs)
            if 'href' in values:
                self.links.append(values['href'])


def acquire(name, entry, work):
    candidates = []
    for registry in LOCK['registries']:
        index = registry + name.lower().replace('_', '-') + '/'
        page = work / 'index.html'
        download(index, page)
        links = Links()
        links.feed(page.read_text())
        for link in links.links:
            url = urljoin(index, link)
            filename = unquote(urlsplit(url).path.rsplit('/', 1)[-1])
            if not filename.endswith('.whl'):
                continue
            _, version, _, tags = parse_wheel_filename(filename)
            if str(version) != entry['version'] or not TAGS.intersection(tags):
                continue
            expected = urlsplit(url).fragment.removeprefix('sha256=')
            if expected in entry['sha256']:
                candidates.append((filename, url, expected))
        if candidates:
            break
    if not candidates:
        raise RuntimeError(f'No compatible locked wheel for {name}')
    filename, url, expected = sorted(candidates)[0]
    wheel = STORE / 'wheels' / filename
    download(url, wheel)
    actual = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f'Dependency integrity mismatch: {filename}')
    with zipfile.ZipFile(wheel) as archive:
        metadata_names = [n for n in archive.namelist() if n.count('/') == 1 and n.endswith('.dist-info/METADATA')]
        if len(metadata_names) != 1:
            raise ValueError(f'Ambiguous wheel metadata: {filename}')
        metadata = email.message_from_bytes(archive.read(metadata_names[0]))
        if metadata['Name'].lower().replace('_', '-') != name.lower().replace('_', '-'):
            raise ValueError(f'Unexpected wheel identity: {filename}')
        requirements = [Requirement(r) for r in metadata.get_all('Requires-Dist', [])]
        active = [r for r in requirements if r.marker is None or r.marker.evaluate({'extra': ''})]
        children = entry.get('dependencies', [])
        if len(active) != len(children):
            raise ValueError(f'Unlocked runtime dependencies: {filename}')
        resolved = []
        for requirement in active:
            matches = [child for child in children
                       if Version(child['version']) in requirement.specifier]
            if len(matches) != 1:
                raise ValueError(f'Ambiguous dependency lock: {requirement}')
            resolved.append(acquire(requirement.name, matches[0], work))
    provenance.append({'name': name, 'version': entry['version'], 'url': url,
                       'sha256': actual, 'filename': filename})
    return wheel, entry, resolved


def flatten(node):
    yield node
    for child in node[2]:
        yield from flatten(child)


STORE.mkdir(mode=0o755, parents=True, exist_ok=True)
(STORE / 'wheels').mkdir(exist_ok=True)
provenance = []
with tempfile.TemporaryDirectory(prefix='schema-registry-') as temporary:
    work = Path(temporary)
    roots = [acquire(entry['name'], entry, work) for entry in LOCK['packages']]
    nodes = [node for root in roots for node in flatten(root)]
    regular = [str(wheel) for wheel, entry, _ in nodes if 'isolate' not in entry]
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps',
                    '--no-build-isolation', *regular], check=True)
    isolated = [(wheel, entry) for wheel, entry, _ in nodes if 'isolate' in entry]
    replacements = {}
    for wheel, entry in isolated:
        with zipfile.ZipFile(wheel) as archive:
            metadata = next(n for n in archive.namelist() if n.count('/') == 1 and n.endswith('.dist-info/METADATA'))
            name = email.message_from_bytes(archive.read(metadata))['Name'].replace('-', '_')
            replacements[name] = '_schema_fixture.' + entry['isolate']
    fixture = TARGET / '_schema_fixture'
    fixture.mkdir(exist_ok=True)
    (fixture / '__init__.py').write_text('"""Isolated schema dependencies."""\n')
    for wheel, entry in isolated:
        unpacked = work / entry['isolate']
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(unpacked)
        package = next(name for name, destination in replacements.items()
                       if destination.endswith('.' + entry['isolate']))
        destination = fixture / entry['isolate']
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(unpacked / package, destination)
        for path in destination.rglob('*'):
            if path.is_file() and path.suffix in ('.py', '.pyi'):
                text = path.read_text()
                for original, relocated in replacements.items():
                    text = re.sub(r'(?<!\w)' + re.escape(original) + r'(?!\w)',
                                  lambda match: relocated, text)
                compile(text.encode('utf-8'), str(path), 'exec')
                path.write_text(text)
        # Original distribution metadata, licenses and notices remain unmodified.
        legal = STORE / 'distributions' / entry['isolate']
        legal.mkdir(parents=True, exist_ok=True)
        for metadata in unpacked.glob('*.dist-info'):
            shutil.copytree(metadata, legal / metadata.name, dirs_exist_ok=True)
    adapter = TARGET / 'xmlschema'
    if adapter.exists():
        shutil.rmtree(adapter)
    shutil.copytree(ASSETS / 'xmlschema', adapter)
(STORE / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
shutil.copy2(ASSETS / 'build.py', STORE / 'build.py')
subprocess.run([sys.executable, '-I', '-c',
                'from _schema_fixture import processor; '
                'print("Isolated schema processor: " + processor.__version__)'], check=True)
print('Installed verified dependencies; public caller binding occurs in its runtime context.')
