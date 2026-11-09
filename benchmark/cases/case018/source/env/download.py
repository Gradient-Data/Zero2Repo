"""Bounded, retrying downloads; parallel byte ranges for large archives."""
import concurrent.futures
import pathlib
import subprocess
import urllib.request
import urllib.error
import time

def run_network(command):
    for attempt in range(4):
        try:
            return subprocess.run(command, check=True)
        except subprocess.CalledProcessError:
            if attempt == 3:
                raise
            print(f'Retrying failed network command (attempt {attempt + 2}/4)', flush=True)
            time.sleep(2 ** attempt)

def headers(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method='HEAD'), timeout=60) as response:
                return response.headers
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if isinstance(exc, urllib.error.HTTPError) and exc.code < 500:
                raise
            if attempt == 3:
                raise
            print(f'Retrying HEAD {url}: {exc}', flush=True)
            time.sleep(2 ** attempt)

def fetch(url, target, *, force_ranges=False):
    target = pathlib.Path(target)
    response_headers = headers(url)
    length = response_headers.get('Content-Length')
    size = int(length) if length is not None else None
    ranges = response_headers.get('Accept-Ranges') == 'bytes'
    command = ['curl', '--silent', '--show-error', '--fail', '--location', '--retry', '8', '--retry-all-errors', '--connect-timeout', '20', '--max-time', '180', '--speed-limit', '128', '--speed-time', '60']
    if size is None or size == 0 or not ranges or (size < 4 * 1024 * 1024 and not force_ranges):
        subprocess.run(command + ['--output', str(target), url], check=True)
    else:
        workers = 12
        # Keep each range small enough to finish through slow public endpoints.
        chunk = 64 * 1024
        def part(i):
            start, end = i * chunk, min(size, (i + 1) * chunk) - 1
            path = target.with_name(target.name + f'.part{i}')
            received = bytearray()
            for attempt in range(16):
                first = start + len(received)
                body = path.with_name(path.name + '.response')
                header = path.with_name(path.name + '.headers')
                result = subprocess.run([
                    'curl', '--silent', '--show-error', '--fail', '--location',
                    '--connect-timeout', '10', '--max-time', '30',
                    '--speed-limit', '128', '--speed-time', '10',
                    '--range', f'{first}-{end}', '--dump-header', str(header),
                    '--output', str(body), url,
                ])
                blocks = header.read_text().replace('\r\n', '\n').strip().split('\n\n')
                fields = {}
                status = None
                for block in blocks:
                    lines = block.splitlines()
                    if lines and lines[0].startswith('HTTP/'):
                        status = int(lines[0].split()[1])
                        fields = dict(line.split(':', 1) for line in lines[1:] if ':' in line)
                        fields = {key.lower(): value.strip() for key, value in fields.items()}
                if body.exists() and body.stat().st_size:
                    expected = f'bytes {first}-{end}/{size}'
                    if status != 206 or fields.get('content-range') != expected:
                        raise ValueError(f'Incorrect range headers for {url}: {fields}')
                    content = body.read_bytes()
                    if len(content) > end - first + 1:
                        raise ValueError(f'Oversized range response for {url}')
                    received.extend(content)
                body.unlink(missing_ok=True)
                header.unlink(missing_ok=True)
                if len(received) == end - start + 1:
                    path.write_bytes(received)
                    break
                print(f'Retrying range at {start + len(received)} for {url}; curl exit {result.returncode}', flush=True)
                if attempt == 15:
                    raise RuntimeError(f'Incomplete range {start}-{end} for {url}; curl exit {result.returncode}')
            
            return path
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            parts = list(pool.map(part, range((size + chunk - 1) // chunk)))
        with target.open('wb') as out:
            for path in parts:
                out.write(path.read_bytes())
                path.unlink()
    if size is not None and target.stat().st_size != size:
        raise ValueError(f'Incorrect response size for {url}')
    print(f'Downloaded {target.name}: {target.stat().st_size} bytes', flush=True)
