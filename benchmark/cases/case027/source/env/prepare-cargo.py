#!/usr/bin/env python3
"""Prepare a Cargo directory source from checksum-pinned registry archives."""

import concurrent.futures
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile


CARGO_HOME = Path('/usr/local/cargo')
VENDOR = CARGO_HOME / 'vendor'
DOWNLOAD_ROOT = 'https://static.crates.io/crates'


def prepare(package):
    name, version, checksum = (package[key] for key in ('name', 'version', 'checksum'))
    directory = f'{name}-{version}'
    with tempfile.TemporaryDirectory(prefix='cargo-dependency-') as temporary:
        temporary = Path(temporary)
        archive = temporary / 'download.crate'
        subprocess.run([
            'curl', '-fsSL', '--retry', '5', '--retry-delay', '3',
            '--connect-timeout', '20', '--speed-limit', '1024', '--speed-time', '30',
            '-o', str(archive), f'{DOWNLOAD_ROOT}/{name}/{name}-{version}.crate',
        ], check=True)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != checksum:
            raise ValueError(f'Archive checksum mismatch: {directory}')
        with tarfile.open(archive, 'r:gz') as tar:
            for member in tar:
                path = PurePosixPath(member.name)
                if path.is_absolute() or '..' in path.parts or path.parts[0] != directory:
                    raise ValueError(f'Invalid archive path: {member.name}')
                destination = temporary.joinpath(*path.parts)
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with tar.extractfile(member) as source, destination.open('wb') as output:
                        shutil.copyfileobj(source, output)
                    destination.chmod(0o755 if member.mode & 0o111 else 0o644)
                else:
                    raise ValueError(f'Unsupported archive entry: {member.name}')
        extracted = temporary / directory
        files = {
            str(path.relative_to(extracted)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(extracted.rglob('*')) if path.is_file()
            and path.name != '.cargo-checksum.json'
        }
        (extracted / '.cargo-checksum.json').write_text(
            json.dumps({'package': checksum, 'files': files}) + '\n', encoding='utf-8'
        )
        target = VENDOR / directory
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(extracted), target)
    print(f'Prepared {directory}', flush=True)


def main():
    packages = json.loads(Path('/env-assets/crates.lock.json').read_text(encoding='utf-8'))
    VENDOR.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(prepare, packages))
    (CARGO_HOME / 'config.toml').write_text(
        '[source.crates-io]\nreplace-with = "prepared-dependencies"\n\n'
        '[source.prepared-dependencies]\ndirectory = "/usr/local/cargo/vendor"\n',
        encoding='utf-8',
    )
    subprocess.run(['chmod', '-R', 'a+rwX', str(CARGO_HOME)], check=True)


if __name__ == '__main__':
    main()
