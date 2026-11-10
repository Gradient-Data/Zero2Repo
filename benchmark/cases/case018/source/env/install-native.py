"""Install pinned toolchain and checksum-verified third-party Cargo sources."""
import concurrent.futures
import hashlib
import json
import pathlib
import shutil
import subprocess
import tarfile
import tomllib
import urllib.request

ASSETS = pathlib.Path('/env-assets')
ROOT = pathlib.Path('/opt/offline')
ROOT.mkdir(exist_ok=True)
VENDOR = ROOT / 'vendor'
VENDOR.mkdir(exist_ok=True)

from download import fetch, run_network

def verify(path, expected):
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f'SHA256 mismatch for {path}: {actual} != {expected}')

for artifact in json.loads((ASSETS / 'toolchain.json').read_text()):
    archive = ROOT / artifact['filename']
    fetch(artifact['url'], archive)
    verify(archive, artifact['sha256'])
    with tarfile.open(archive) as tar:
        tar.extractall(ROOT, filter='data')
    unpacked = ROOT / artifact['filename'].removesuffix('.tar.xz')
    subprocess.run(['bash', str(unpacked / 'install.sh'), '--prefix=/opt/rust', '--disable-ldconfig'], check=True)
    shutil.rmtree(unpacked)
    archive.unlink()

packages = json.loads((ASSETS / 'crates.json').read_text())

def registry_package(pkg):
    name, version = pkg['name'], pkg['version']
    url = f'https://static.crates.io/crates/{name}/{name}-{version}.crate'
    archive = ROOT / f'{name}-{version}.crate'
    fetch(url, archive)
    verify(archive, pkg['checksum'])
    with tarfile.open(archive) as tar:
        tar.extractall(VENDOR, filter='data')
    directory = VENDOR / f'{name}-{version}'
    files = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    (directory / '.cargo-checksum.json').write_text(json.dumps({'files': files, 'package': pkg['checksum']}))
    archive.unlink()

with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    list(pool.map(registry_package, [p for p in packages if p['source'].startswith('registry+')]))

# Git dependencies retain their entire pinned source tree, including submodules.
# Normalize inherited dependency declarations when exporting Cargo directory sources.
import toml
sources = sorted({p['source'] for p in packages if p['source'].startswith('git+')})
config = ['[net]', 'offline = true', '[source.crates-io]', 'replace-with = "offline-vendor"', '[source.offline-vendor]', f'directory = "{VENDOR}"']
for index, source in enumerate(sources):
    url, revision = source[4:].split('#')
    url, query = url.split('?')
    checkout = ROOT / f'git-source-{index}'
    tree = json.loads((ASSETS / 'cargo-git-files.json').read_text())[source]
    checkout.mkdir(parents=True)
    def git_file(entry):
        relative = pathlib.PurePosixPath(entry['path'])
        if relative.is_absolute() or '..' in relative.parts or entry['mode'] not in ('100644', '100755'):
            raise ValueError(f'Unsupported Git entry: {entry}')
        path = checkout / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        fetch(f"https://raw.githubusercontent.com/{tree['repository']}/{revision}/{entry['path']}", path, force_ranges=True)
        content = path.read_bytes()
        digest = hashlib.sha1(f'blob {len(content)}\0'.encode() + content).hexdigest()
        if len(content) != entry['size'] or digest != entry['sha']:
            raise ValueError(f'Git blob integrity mismatch: {path}')
        path.chmod(int(entry['mode'][-3:], 8))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(git_file, tree['files']))
    wanted = {p['name'] for p in packages if p['source'] == source}
    for manifest in list(checkout.rglob('Cargo.toml')):
        data = tomllib.loads(manifest.read_text())
        if data.get('package', {}).get('name') not in wanted:
            continue
        directory = VENDOR / (data['package']['name'] + '-' + data['package']['version'])
        shutil.copytree(manifest.parent, directory)
        ancestor = manifest.parent
        while 'workspace' not in (workspace := tomllib.loads((ancestor / 'Cargo.toml').read_text()) if (ancestor / 'Cargo.toml').exists() else {}):
            ancestor = ancestor.parent
            if ancestor == ancestor.parent:
                raise RuntimeError(f'Workspace not found for {manifest}')
        workspace = workspace['workspace']
        for key, value in list(data['package'].items()):
            if isinstance(value, dict) and value.get('workspace'):
                data['package'][key] = workspace['package'][key]
        def normalize(table):
            for key in ('dependencies', 'build-dependencies', 'dev-dependencies'):
                for name, dep in table.get(key, {}).items():
                    if not isinstance(dep, dict):
                        continue
                    if dep.pop('workspace', False):
                        inherited = workspace['dependencies'][name]
                        inherited = {'version': inherited} if isinstance(inherited, str) else dict(inherited)
                        features = inherited.pop('features', []) + dep.pop('features', [])
                        inherited.update(dep)
                        dep.clear()
                        dep.update(inherited)
                        if features:
                            dep['features'] = features
                    if 'path' in dep:
                        dep.pop('path')
                        target = dep.get('package', name)
                        version = next(p['version'] for p in packages if p['name'] == target and p['source'] == source)
                        dep.setdefault('version', version)
                        # Keep the edge within the same Git source; removing its path
                        # would turn it into a registry dependency and invalidate the lock.
                        dep['path'] = f'../{target}-{version}'
            for child in table.get('target', {}).values():
                normalize(child)
        normalize(data)
        data.pop('workspace', None)
        (directory / 'Cargo.toml').write_text(toml.dumps(data))
        files = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
        (directory / '.cargo-checksum.json').write_text(json.dumps({'files': files, 'package': None}))
    config += [f'[source."{source.split("#")[0]}"]', f'git = "{url}"', f'rev = "{revision}"', 'replace-with = "offline-vendor"']
pathlib.Path('/opt/cargo').mkdir(exist_ok=True)
pathlib.Path('/opt/cargo/config.toml').write_text('\n'.join(config) + '\n')
