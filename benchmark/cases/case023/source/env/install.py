"""Install a pinned Rust toolchain and checksum-verified offline crate sources."""

import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile


ASSETS = Path('/env-assets')
VENDOR = Path('/opt/cargo-vendor')


def fetch(url, destination, checksum, size=None):
    # A failed checksum is always fatal.
    for url in (url,):
        print(f'Downloading {url}', flush=True)
        options = [
            'curl', '--fail', '--location', '--silent', '--show-error',
            '--http1.1', '--retry', '3', '--connect-timeout', '20', '--max-time', '600',
            '--speed-limit', '1024', '--speed-time', '30',
        ]
        if size is None:
            result = subprocess.run(options + ['--output', str(destination), url])
        else:
            result = subprocess.run(options + ['--head', '--output', '/dev/null', url])
            if result.returncode == 0:
                # Short, independently retried requests avoid restarting a large
                # transfer when the public download connection stalls.
                chunk_size = 128 * 1024
                with tempfile.TemporaryDirectory(prefix='download-parts-') as temp:
                    def part(start):
                        end = min(start + chunk_size, size) - 1
                        path = Path(temp) / str(start)
                        subprocess.run(options + [
                            '--max-time', '120', '--retry', '8', '--retry-delay', '1', '--retry-all-errors',
                            '--range', f'{start}-{end}', '--output', str(path), url,
                        ], check=True)
                        if path.stat().st_size != end - start + 1:
                            raise RuntimeError(f'Incorrect range response for {url}: {start}-{end}')
                        if start % (8 * 1024 * 1024) == 0:
                            print(f'Completed range {start}-{end} of {size}', flush=True)
                        return path
                    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
                        paths = list(pool.map(part, range(0, size, chunk_size)))
                    with destination.open('wb') as output:
                        for path in paths:
                            output.write(path.read_bytes())
        if result.returncode == 0:
            actual = hashlib.sha256(destination.read_bytes()).hexdigest()
            if actual != checksum:
                raise RuntimeError(f'Checksum mismatch for {url}: {actual} != {checksum}')
            return
        print(f'Download failed with status {result.returncode}: {url}', flush=True)
    raise RuntimeError(f'Download failed for {destination.name}')


def unpack(archive, destination, expected_root):
    with tarfile.open(archive) as source:
        members = source.getmembers()
        for member in members:
            path = Path(member.name)
            if path.is_absolute() or '..' in path.parts or path.parts[0] != expected_root:
                raise RuntimeError(f'Unexpected archive path: {member.name}')
            if not (member.isdir() or member.isfile()):
                raise RuntimeError(f'Unexpected archive member type: {member.name}')
        source.extractall(destination, members=members)


def install_crate(package):
    name, version = package['name'], package['version']
    if package['source'] != 'registry+https://github.com/rust-lang/crates.io-index':
        raise RuntimeError(f'Unsupported package source: {package["source"]}')
    dirname = f'{name}-{version}'
    with tempfile.TemporaryDirectory(prefix='crate-install-') as temp:
        archive = Path(temp) / f'{dirname}.crate'
        fetch(
            f'https://static.crates.io/crates/{name}/{dirname}.crate',
            archive, package['checksum'],
        )
        unpack(archive, VENDOR, dirname)
    directory = VENDOR / dirname
    files = {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob('*'))
        if path.is_file() and path.name != '.cargo-checksum.json'
    }
    (directory / '.cargo-checksum.json').write_text(
        json.dumps({'package': package['checksum'], 'files': files}) + '\n'
    )


def main():
    for component in json.loads((ASSETS / 'toolchain.json').read_text()):
        with tempfile.TemporaryDirectory(prefix='rust-install-') as temp:
            directory = Path(temp)
            archive = directory / 'component.tar.xz'
            fetch(component['official'], archive, component['checksum'], component['size'])
            unpack(archive, directory, component['name'])
            subprocess.run([
                'sh', str(directory / component['name'] / 'install.sh'),
                '--prefix=/opt/rust', '--disable-ldconfig',
            ], check=True)
    VENDOR.mkdir(parents=True, exist_ok=True)
    packages = json.loads((ASSETS / 'crates.json').read_text())
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(install_crate, packages))
    Path('/opt/offline-cargo.toml').write_text(
        '[source.crates-io]\nreplace-with = "offline-vendor"\n'
        '[source.offline-vendor]\ndirectory = "/opt/cargo-vendor"\n'
        '[net]\noffline = true\n'
    )
    # An explicit config also works for external callers building in /tmp.
    Path('/usr/local/bin/cargo').write_text(
        '#!/bin/sh\nexec /opt/rust/bin/cargo --config /opt/offline-cargo.toml "$@"\n'
    )
    Path('/usr/local/bin/cargo').chmod(0o755)
    for name in ('rustc', 'rustdoc'):
        link = Path('/usr/local/bin') / name
        if link.is_symlink():
            link.unlink()
        link.symlink_to(Path('/opt/rust/bin') / name)
    subprocess.run(['chmod', '-R', 'a+rX', '/opt/rust', str(VENDOR)], check=True)


if __name__ == '__main__':
    main()
