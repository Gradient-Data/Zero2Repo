"""Install pinned Node.js, Rust and checksum-verified Cargo dependencies."""

import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import platform
import pwd
import re
import shutil
import subprocess
import tarfile
import tempfile
import time


ASSETS = Path('/env-assets')
VENDOR = Path('/opt/cargo-vendor')
CARGO_HOME = Path('/opt/offline-cargo')
REGISTRY = 'registry+https://github.com/rust-lang/crates.io-index'
CURL = [
    'curl', '--fail', '--location', '--show-error', '--silent',
    '--retry', '3', '--retry-delay', '2', '--connect-timeout', '20',
    '--speed-limit', '1024', '--speed-time', '60', '--max-time', '900',
]


def fetch(url, destination):
    subprocess.run([*CURL, '--output', str(destination), url], check=True)



def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def install_node(work):
    provision = json.loads((ASSETS / 'node.json').read_text())
    version = provision['version']
    architecture = {'x86_64': 'x64', 'aarch64': 'arm64'}[platform.machine()]
    stem = f'node-v{version}-linux-{architecture}'
    filename = stem + '.tar.xz'
    archive = work / filename
    fetch(f'{provision["official"]}/v{version}/{filename}', archive)
    if sha256(archive) != provision['sha256'][architecture]:
        raise ValueError(f'Node.js archive checksum mismatch: {filename}')
    with tarfile.open(archive) as source:
        for member in source.getmembers():
            if member.name.split('/')[0] != stem:
                raise ValueError(f'Unexpected Node.js archive member: {member.name}')
        source.extractall('/opt', filter='data')
    installed = Path('/opt') / stem
    subprocess.run(['chmod', '-R', 'a+rX', str(installed)], check=True)
    # Keep the pinned runtime discoverable through both standard system PATH
    # locations. The publication filter may inspect /usr/local/bin entries,
    # while the judge inherits /usr/bin as well.
    for entry in (Path('/usr/local/bin/node'), Path('/usr/bin/node')):
        if entry.exists() or entry.is_symlink():
            entry.unlink()
        entry.symlink_to(installed / 'bin/node')
    validation = installed / 'validate-node.mjs'
    shutil.copyfile(ASSETS / 'validate-node.mjs', validation)
    validation.chmod(0o644)
    # A clean environment and unrelated working directory must work without root.
    account = pwd.getpwnam('nobody')
    with tempfile.TemporaryDirectory(prefix='node-runtime-validation-') as temporary:
        Path(temporary).chmod(0o755)
        subprocess.run(
            ['node', str(validation), version], cwd=temporary,
            env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': temporary},
            user=account.pw_uid, group=account.pw_gid, extra_groups=[], check=True,
        )


def fetch_range(url, destination, start, end, size):
    """Retry only a bounded byte range when a transfer is interrupted."""
    headers = destination.with_name(destination.name + '.headers')
    for attempt in range(1, 5):
        print(f'Downloading {url}: bytes {start}-{end}, attempt {attempt}/4', flush=True)
        try:
            # Do not combine curl's internal retries with this bounded retry loop.
            subprocess.run([
                'curl', '--fail', '--location', '--show-error', '--silent',
                '--connect-timeout', '20', '--speed-limit', '1024',
                '--speed-time', '60', '--max-time', '300',
                '--range', f'{start}-{end}', '--dump-header', str(headers),
                '--output', str(destination), url,
            ], check=True, timeout=330)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            print(f'Download bytes {start}-{end} attempt {attempt}/4 failed: {error}', flush=True)
            if attempt == 4:
                raise
            time.sleep(2)
            continue
        responses = [block for block in headers.read_text().split('\n\n')
                     if block.startswith('HTTP/')]
        response = responses[-1].splitlines()
        fields = dict(line.lower().split(':', 1) for line in response[1:] if ':' in line)
        expected_range = f'bytes {start}-{end}/{size}'
        if (response[0].split()[1] != '206'
                or fields.get('content-range', '').strip() != expected_range
                or destination.stat().st_size != end - start + 1):
            raise ValueError(f'Invalid range response for {url}: expected {expected_range}; '
                             f'headers={response}, bytes={destination.stat().st_size}')
        print(f'Received {url}: {expected_range}', flush=True)
        return destination


def fetch_verified(url, destination, expected, size):
    """Assemble bounded parallel ranges; verify the entire archive before use."""
    if not re.fullmatch(r'[0-9a-f]{64}', expected) or not isinstance(size, int) or size <= 0:
        raise ValueError(f'Invalid artifact integrity metadata for {url}')
    # Small independent requests limit the cost of slow or interrupted streams.
    # Completed ranges survive retries of other ranges in this acquisition.
    chunk_size = 2 * 1024 * 1024
    with tempfile.TemporaryDirectory(prefix=destination.name + '-', dir=destination.parent) as temporary:
        work = Path(temporary)
        starts = range(0, size, chunk_size)

        def download(start):
            return fetch_range(url, work / str(start), start, min(start + chunk_size, size) - 1, size)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            chunks = list(pool.map(download, starts))
        partial = work / 'assembled.part'
        with partial.open('wb') as output:
            for chunk in chunks:
                with chunk.open('rb') as source:
                    shutil.copyfileobj(source, output)
        actual = sha256(partial)
        if actual != expected:
            raise ValueError(
                f'Archive checksum mismatch for {url}: expected {expected}, got {actual}'
            )
        partial.replace(destination)
        print(f'Verified SHA-256 {expected}: {destination.name}', flush=True)
        return


def install_toolchain(work):
    provision = json.loads((ASSETS / 'rust.json').read_text())
    architecture = platform.machine()
    components = provision['architectures'][architecture]
    version = provision['version']
    target = architecture + '-unknown-linux-gnu'
    # Dated official release URLs and hashes recorded from the release
    # manifest in rust.json.
    for component in ('rustc', 'cargo', 'rust-std'):
        artifact = components[component]
        stem = f'{component}-{version}-{target}'
        archive = work / f'{stem}.tar.xz'
        fetch_verified(artifact['url'], archive, artifact['sha256'], artifact['size'])
        with tarfile.open(archive) as source:
            for member in source.getmembers():
                if member.name.split('/')[0] != stem:
                    raise ValueError(f'Unexpected Rust archive member: {member.name}')
            source.extractall(work, filter='data')
        subprocess.run([
            'sh', str(work / stem / 'install.sh'), '--prefix=/usr/local',
            '--disable-ldconfig',
        ], check=True)
        archive.unlink()
        shutil.rmtree(work / stem)
    for executable in ('rustc', 'cargo'):
        output = subprocess.check_output(
            [f'/usr/local/bin/{executable}', '--version'], text=True,
        ).strip()
        if output.split()[1] != version:
            raise ValueError(f'Installed {executable} version mismatch: {output}')
        print(f'Installed {output}', flush=True)
    install_wasm_toolchain(work, provision, version, architecture)


def install_wasm_toolchain(work, provision, version, architecture):
    """Offline WebAssembly builds: the wasm32 standard library and the
    wasm-bindgen CLI whose version matches the vendored wasm-bindgen crate."""
    wasm = provision['wasm32']
    stem = f'rust-std-{version}-wasm32-unknown-unknown'
    archive = work / f'{stem}.tar.xz'
    artifact = wasm['rust-std']
    fetch_verified(artifact['url'], archive, artifact['sha256'], artifact['size'])
    with tarfile.open(archive) as source:
        for member in source.getmembers():
            if member.name.split('/')[0] != stem:
                raise ValueError(f'Unexpected Rust archive member: {member.name}')
        source.extractall(work, filter='data')
    subprocess.run([
        'sh', str(work / stem / 'install.sh'), '--prefix=/usr/local',
        '--disable-ldconfig',
    ], check=True)
    archive.unlink()
    shutil.rmtree(work / stem)
    if not Path('/usr/local/lib/rustlib/wasm32-unknown-unknown/lib').is_dir():
        raise ValueError('wasm32-unknown-unknown standard library is not installed')
    bindgen = wasm['wasm-bindgen']
    artifact = bindgen['architectures'][architecture]
    stem = f"wasm-bindgen-{bindgen['version']}-{architecture}-unknown-linux-musl"
    archive = work / f'{stem}.tar.gz'
    fetch(artifact['url'], archive)
    actual = sha256(archive)
    if archive.stat().st_size != artifact['size'] or actual != artifact['sha256']:
        raise ValueError(
            f"Archive checksum mismatch for {artifact['url']}: expected {artifact['sha256']} "
            f"({artifact['size']} bytes), got {actual} ({archive.stat().st_size} bytes)"
        )
    with tarfile.open(archive) as source:
        for member in source.getmembers():
            if member.name.split('/')[0] != stem:
                raise ValueError(f'Unexpected wasm-bindgen archive member: {member.name}')
        source.extractall(work, filter='data')
    shutil.copy(work / stem / 'wasm-bindgen', '/usr/local/bin/wasm-bindgen')
    os.chmod('/usr/local/bin/wasm-bindgen', 0o755)
    archive.unlink()
    shutil.rmtree(work / stem)
    output = subprocess.check_output(['/usr/local/bin/wasm-bindgen', '--version'], text=True).strip()
    if output != f"wasm-bindgen {bindgen['version']}":
        raise ValueError(f'Installed wasm-bindgen version mismatch: {output}')
    print(f'Installed {output} and the wasm32-unknown-unknown standard library', flush=True)



def fetch_index(repository, arguments, objects=None):
    command = [
        'git', '-C', str(repository), '-c', 'http.version=HTTP/1.1',
        '-c', 'http.lowSpeedLimit=1024', '-c', 'http.lowSpeedTime=60',
        '-c', 'fetch.fsckObjects=true', 'fetch', '--no-tags',
        '--recurse-submodules=no', '--filter=blob:none', *arguments,
    ]
    for attempt in range(1, 4):
        try:
            subprocess.run(command, input=objects, text=True, check=True, timeout=900)
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            print(f'Registry fetch attempt {attempt} failed: {error}', flush=True)
            if attempt == 3:
                raise
            time.sleep(2)


def resolve_packages(provision, work):
    """Read pinned versions from native, content-addressed registry Git objects."""
    if provision['schema_version'] != 1 or provision['source'] != REGISTRY:
        raise ValueError('Unsupported registry provisioning format')
    index = provision['index']
    records = provision['records']
    if index['url'] != 'https://github.com/rust-lang/crates.io-index.git':
        raise ValueError('Unsupported registry Git source')
    if not re.fullmatch(r'[0-9a-f]{40}', index['commit']) or not records:
        raise ValueError('Invalid registry snapshot or empty request set')
    objects = []
    checksums = set()
    for record in records:
        oid = record['git_blob']
        if not re.fullmatch(r'[0-9a-f]{40}', oid) or oid in objects:
            raise ValueError(f'Invalid or duplicate registry object: {oid}')
        if not re.fullmatch(r'[0-9a-f]{64}', record['sha256']) or not record['packages']:
            raise ValueError(f'Invalid registry integrity record: {oid}')
        objects.append(oid)
        for package in record['packages']:
            checksum = package['checksum']
            if not re.fullmatch(r'[0-9a-f]{64}', checksum) or checksum in checksums:
                raise ValueError(f'Invalid or duplicate package checksum: {checksum}')
            if not re.fullmatch(r'[0-9A-Za-z.+-]+', package['version']):
                raise ValueError(f'Invalid package version: {package["version"]}')
            checksums.add(checksum)
    repository = work / 'registry.git'
    subprocess.run(['git', 'init', '--bare', str(repository)], check=True)
    git = ['git', '-C', str(repository)]
    subprocess.run([*git, 'remote', 'add', 'origin', index['url']], check=True)
    subprocess.run([*git, 'config', 'remote.origin.promisor', 'true'], check=True)
    # Alibaba's sparse registry has no immutable Git object endpoint.
    fetch_index(repository, ['--depth=1', 'origin', index['commit']])
    tree = subprocess.check_output([*git, 'ls-tree', '-r', index['commit']], text=True)
    reachable = {line.split(None, 3)[2] for line in tree.splitlines()}
    if set(objects) - reachable:
        raise ValueError('Requested registry objects are absent from the pinned snapshot')
    fetch_index(repository, ['--no-write-fetch-head', '--stdin', 'origin'],
                '\n'.join(objects) + '\n')
    # All reads below must use objects that the explicit fetch supplied.
    subprocess.run([*git, 'config', 'remote.origin.promisor', 'false'], check=True)
    packages = []
    for record in records:
        data = subprocess.check_output([*git, 'cat-file', 'blob', record['git_blob']])
        if hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError(f'Registry object checksum mismatch: {record["git_blob"]}')
        entries = [json.loads(line) for line in data.splitlines()]
        for request in record['packages']:
            matches = [entry for entry in entries
                       if entry['vers'] == request['version'] and entry['cksum'] == request['checksum']]
            if len(matches) != 1:
                raise ValueError(f'Pinned package missing or ambiguous in registry: {request}')
            entry = matches[0]
            if not re.fullmatch(r'[A-Za-z0-9_-]+', entry['name']):
                raise ValueError(f'Invalid registry package name: {entry["name"]}')
            packages.append({'name': entry['name'], 'version': entry['vers'],
                             'source': REGISTRY, 'checksum': entry['cksum']})
    packages.sort(key=lambda package: (package['name'], package['version']))
    print(f'Resolved all {len(packages)} pinned registry packages', flush=True)
    return packages


def install_package(package, work):
    if package['source'] != REGISTRY:
        raise ValueError(f'Unsupported registry: {package["source"]}')
    stem = f'{package["name"]}-{package["version"]}'
    archive = work / f'{stem}.crate'
    official = f'https://static.crates.io/crates/{package["name"]}/{stem}.crate'
    fetch(official, archive)
    if sha256(archive) != package['checksum']:
        raise ValueError(f'Crate archive checksum mismatch: {stem}')
    with tarfile.open(archive) as source:
        for member in source.getmembers():
            if member.name.split('/')[0] != stem:
                raise ValueError(f'Unexpected crate archive member: {member.name}')
        source.extractall(VENDOR, filter='data')
    directory = VENDOR / stem
    files = {
        str(path.relative_to(directory)): sha256(path)
        for path in sorted(directory.rglob('*'))
        if path.is_file() and path.name != '.cargo-checksum.json'
    }
    (directory / '.cargo-checksum.json').write_text(
        json.dumps({'files': files, 'package': package['checksum']}) + '\n'
    )
    archive.unlink()
    print(f'Verified {stem}', flush=True)


def main():
    if os.geteuid() != 0:
        raise PermissionError('Installation must run as root')
    VENDOR.mkdir(parents=True, exist_ok=True)
    CARGO_HOME.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='environment-install-') as temporary:
        work = Path(temporary)
        install_node(work)
        install_toolchain(work)
        provision = json.loads((ASSETS / 'dependencies.json').read_text())
        packages = resolve_packages(provision, work)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda package: install_package(package, work), packages))
    (CARGO_HOME / 'resolved-packages.json').write_text(json.dumps(packages, indent=2) + '\n')
    (CARGO_HOME / 'config.toml').write_text(
        '[source.crates-io]\nreplace-with = "offline-vendor"\n\n'
        '[source.offline-vendor]\ndirectory = "/opt/cargo-vendor"\n\n'
        '[net]\noffline = true\n\n[build]\njobs = 4\n'
    )
    # Users may need Cargo's cache lock even when package sources are read-only.
    for filename in ('.package-cache', '.package-cache-mutate'):
        lock = CARGO_HOME / filename
        lock.touch()
        lock.chmod(0o666)
    subprocess.run(['chmod', '-R', 'a+rX', str(VENDOR), str(CARGO_HOME)], check=True)
    # Cargo searches .cargo/config.toml in every ancestor of the working
    # directory, including /. This also covers external clients with fresh
    # homes, without requiring a caller-provided CARGO_HOME or --config.
    discovery = Path('/.cargo')
    discovery.mkdir(exist_ok=True)
    discovery.chmod(0o755)
    (discovery / 'config.toml').symlink_to(CARGO_HOME / 'config.toml')


if __name__ == '__main__':
    main()
