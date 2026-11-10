"""Fetch the pinned third-party artifacts and verify their SHA-256 digests."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import unquote, urlsplit

DEST = Path('/opt/dependency-archives')
DEST.mkdir(parents=True, exist_ok=True)
CURL = ['curl', '--fail', '--location', '--silent', '--show-error',
        '--retry', '5', '--retry-all-errors', '--connect-timeout', '30',
        '--speed-limit', '10000', '--speed-time', '60', '--max-time', '1800']


def fetch(item):
    url = item['url']
    path = DEST / unquote(urlsplit(url).path.rsplit('/', 1)[1])
    size = item.get('size', 0)
    if size > 32 * 1024 * 1024:
        chunks = [(start, min(start + 8 * 1024 * 1024, size) - 1)
                  for start in range(0, size, 8 * 1024 * 1024)]

        def part(bounds):
            start, end = bounds
            target = path.with_name(path.name + '.part-' + str(start))
            subprocess.run(CURL + ['--range', f'{start}-{end}',
                                  '-o', str(target), url + f'?range={start}-{end}'], check=True)
            if target.stat().st_size != end - start + 1:
                raise RuntimeError(f'Incorrect range size: {target}')
            return target

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            parts = list(pool.map(part, chunks))
        with path.open('wb') as out:
            for chunk in parts:
                out.write(chunk.read_bytes())
                chunk.unlink()
    else:
        subprocess.run(CURL + ['-o', str(path), url], check=True)
    digest = hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()
    if digest != item['sha256']:
        raise RuntimeError(f'SHA-256 mismatch: {path}')
    print(f"Verified {item['name']}=={item['version']}", flush=True)


items = json.loads(Path('/env-assets/artifacts.json').read_text())
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    list(pool.map(fetch, items))
