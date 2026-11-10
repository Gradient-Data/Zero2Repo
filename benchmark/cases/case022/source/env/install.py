"""Fetch checksum-pinned third-party artifacts and install an offline runtime."""
import concurrent.futures
import hashlib
import json
import email.parser
import shutil
import tempfile
from pathlib import Path
import subprocess
import sys

assets = Path('/env-assets')
wheelhouse = Path('/opt/wheelhouse')
wheelhouse.mkdir(parents=True, exist_ok=True)
packages = json.loads((assets / 'packages.json').read_text())

CURL = [
    'curl', '--fail', '--location', '--retry', '5', '--retry-all-errors',
    '--connect-timeout', '30', '--max-time', '900',
    '--speed-limit', '1024', '--speed-time', '180',
    '--silent', '--show-error',
]


def fetch(package):
    target = wheelhouse / package['filename']
    headers = subprocess.run(
        CURL + ['--head', package['url']], check=True, stdout=subprocess.PIPE, text=True,
    ).stdout
    response = headers.strip().split('HTTP/')[-1].split('\n', 1)[1]
    metadata = email.parser.Parser().parsestr(response)
    length = metadata.get('Content-Length')
    if metadata.get('Accept-Ranges') == 'bytes' and length and int(length) >= 64 * 1024 * 1024:
        size = int(length)
        chunk_size = (size + 15) // 16
        with tempfile.TemporaryDirectory(dir=wheelhouse) as directory:
            def fetch_part(start):
                end = min(start + chunk_size, size) - 1
                part = Path(directory) / str(start)
                status = subprocess.run(
                    CURL + ['--range', f'{start}-{end}', '--output', str(part),
                            '--write-out', '%{http_code}', package['url']],
                    check=True, stdout=subprocess.PIPE, text=True,
                ).stdout
                if status != '206' or part.stat().st_size != end - start + 1:
                    raise ValueError(f'Invalid range response for {target.name}: {start}-{end}, HTTP {status}')
                return part

            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as parts_pool:
                parts = list(parts_pool.map(fetch_part, range(0, size, chunk_size)))
            with target.open('wb') as output:
                for part in parts:
                    with part.open('rb') as source:
                        shutil.copyfileobj(source, output)
    else:
        subprocess.run(CURL + ['--output', str(target), package['url']], check=True)
    digest = hashlib.file_digest(target.open('rb'), 'sha256').hexdigest()
    if digest != package['sha256']:
        raise ValueError(f'Checksum mismatch: {target.name}')
    print(f'Verified {target.name}', flush=True)

with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    list(pool.map(fetch, packages))
runtime = '/opt/conda/bin/python'
if Path(sys.executable).resolve() != Path(runtime).resolve():
    raise RuntimeError(f'Installer must run with {runtime}, got {sys.executable}')
# Source archives use the same pinned build tools as the product build.
bootstrap = [
    str(wheelhouse / package['filename']) for package in packages
    if package.get('name') in {'setuptools', 'wheel', 'packaging'}
]
subprocess.run([
    runtime, '-m', 'pip', 'install', '--no-index', '--no-deps',
    *bootstrap,
], check=True)
subprocess.run([
    runtime, '-m', 'pip', 'install', '--no-index', '--no-build-isolation',
    '--find-links=/opt/wheelhouse', '--require-hashes',
    '-r', str(assets / 'requirements.txt'),
], check=True)

# Retain the audit inputs in the image for offline verification by the judge.
audit = Path('/opt/env-recipe')
audit.mkdir(parents=True, exist_ok=True)
for name in ('packages.json', 'verify.py'):
    shutil.copyfile(assets / name, audit / name)
subprocess.run([runtime, '-m', 'pip', 'check'], check=True)
subprocess.run([runtime, str(audit / 'verify.py')], check=True)
