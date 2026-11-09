"""Fetch apt's authenticated package selection with bounded, verified transfers."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
from urllib.parse import quote, unquote, urlsplit, urlunsplit

PACKAGES = [
    'openjdk-17-jdk-headless=17.0.20.1+1-1~24.04',
    'openjdk-17-jre-headless=17.0.20.1+1-1~24.04',
]
# Official Ubuntu archive snapshot; toolchain.sh updated the index from it.
SNAPSHOT = '20261107T052315Z'
ARCHIVE = f'https://snapshot.ubuntu.com/ubuntu/{SNAPSHOT}/'
CHUNK_SIZE = 2 * 1024 * 1024
selection = subprocess.run(
    ['apt-get', '--snapshot', SNAPSHOT, '--print-uris', '--yes', '--no-install-recommends', 'install', *PACKAGES],
    check=True, text=True, stdout=subprocess.PIPE,
).stdout
entries = [shlex.split(line) for line in selection.splitlines() if line.startswith("'")]


def fetch(job):
    url, total, start, end, part, ranged = job
    expected = end - start + 1
    part.write_bytes(b'')
    errors = []
    for source in (url,):
        for attempt in range(3):
            received = part.stat().st_size
            offset = start + received
            header = part.with_suffix('.headers')
            fragment = part.with_suffix('.fragment')
            header.write_bytes(b'')
            fragment.write_bytes(b'')
            command = [
                'curl', '-fsSL', '--connect-timeout', '20',
                '--speed-limit', '1024', '--speed-time', '30', '--max-time', '120',
                '-D', str(header), '-o', str(fragment), '-w', '%{http_code}',
            ]
            if ranged:
                command += ['--range', f'{offset}-{end}']
            result = subprocess.run(command + [source], text=True, stdout=subprocess.PIPE)
            size = fragment.stat().st_size
            if ranged:
                ranges = [line.split(':', 1)[1].strip() for line in header.read_text().splitlines()
                          if line.lower().startswith('content-range:')]
                valid_prefix = (result.stdout == '206' and bool(ranges)
                                and ranges[-1] == f'bytes {offset}-{end}/{total}'
                                and 0 < size <= expected - received)
            else:
                valid_prefix = result.returncode == 0 and result.stdout == '200' and size == expected
            if valid_prefix:
                with part.open('ab') as output, fragment.open('rb') as content:
                    shutil.copyfileobj(content, output)
                if part.stat().st_size == expected:
                    print(f'Received {url.rsplit("/", 1)[-1]} bytes {start}-{end}', flush=True)
                    return
                print(f'Preserved {part.stat().st_size}/{expected} bytes for range {start}-{end}; resuming.', flush=True)
            reason = (f'{source}, bytes {offset}-{end}, attempt {attempt + 1}: '
                      f'curl={result.returncode}, HTTP={result.stdout}, received={size}')
            errors.append(reason)
            print(f'Incomplete package transfer: {reason}', flush=True)
    raise RuntimeError('Package download failed:\n' + '\n'.join(errors))


with tempfile.TemporaryDirectory(prefix='system-packages-') as temporary:
    root = Path(temporary)
    jobs = []
    outputs = []
    for index, (url, name, size_text, digest) in enumerate(entries):
        parsed = urlsplit(url)
        url = urlunsplit(parsed._replace(path=quote(unquote(parsed.path), safe='/+@:')))
        if not url.startswith(ARCHIVE):
            raise ValueError(f'Unexpected apt package source: {url}')
        size = int(size_text)
        ranged = size > CHUNK_SIZE
        step = CHUNK_SIZE if ranged else size
        parts = []
        for start in range(0, size, step):
            part = root / f'{index}-{start}.part'
            parts.append(part)
            jobs.append((url, size, start, min(size, start + step) - 1, part, ranged))
        outputs.append((name, size, digest, parts))
        print(f'Downloading {name}: {size} bytes in {len(parts)} verified transfer(s)', flush=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(fetch, jobs))
    for name, size, digest, parts in outputs:
        target = Path('/var/cache/apt/archives') / name
        with target.open('wb') as output:
            for part in parts:
                with part.open('rb') as source:
                    shutil.copyfileobj(source, output)
        algorithm, expected = digest.split(':', 1)
        actual = hashlib.new(algorithm.lower().replace('sum', ''), target.read_bytes()).hexdigest()
        if target.stat().st_size != size or actual != expected:
            raise ValueError(f'Package size or checksum mismatch: {name}')
        print(f'Verified {name}', flush=True)
subprocess.run([
    'apt-get', '--snapshot', SNAPSHOT, '--no-download', '--yes', '--no-install-recommends', 'install', *PACKAGES,
], check=True)
