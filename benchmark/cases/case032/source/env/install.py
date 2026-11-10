"""Install the pinned third-party environment without a product checkout."""

from concurrent.futures import ThreadPoolExecutor
import ast
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile


ASSETS = Path('/env-assets')
ROOT = Path('/opt/third-party')
WHEELS = ROOT / 'wheels'


def run(*args):
    subprocess.run(args, check=True)


def download(entry):
    if ('asset' in entry) == ('url' in entry):
        raise ValueError(f'Expected exactly one asset or URL for {entry["filename"]}')
    target = ROOT / entry['filename']
    if entry['filename'].endswith('.whl'):
        target = WHEELS / entry['filename']
    if 'asset' in entry:
        relative = Path(entry['asset'])
        if relative.is_absolute():
            raise ValueError(f'Asset path must be relative: {relative}')
        asset = (ASSETS / relative).resolve(strict=True)
        asset.relative_to(ASSETS.resolve(strict=True))
        if entry['encoding'] != 'base64':
            raise ValueError(f'Unsupported asset encoding: {entry["encoding"]}')
        encoded = asset.read_text(encoding='ascii')
        target.write_bytes(base64.b64decode(''.join(encoded.split()), validate=True))
    else:
        run('curl', '--fail', '--location', '--retry', '5', '--retry-all-errors',
            '--connect-timeout', '30', '--speed-limit', '1024', '--speed-time', '30',
            '--silent', '--show-error', entry['url'], '--output', str(target))
    with target.open('rb') as source:
        actual = hashlib.file_digest(source, 'sha256').hexdigest()
    if actual != entry['sha256']:
        raise RuntimeError(f'Checksum mismatch for {target.name}: {actual}')
    return target


def bind_product_module(folder, binding):
    """Retarget a dependency's product imports before building its wheel."""
    adapter = folder / binding['path']
    imports = [node.name for node in ast.walk(ast.parse(adapter.read_text()))
               if isinstance(node, ast.alias) and node.asname == binding['alias']]
    if len(imports) != 1:
        raise RuntimeError(f'Expected one backend import in {adapter}: {imports}')
    source, _, suffix = imports[0].partition('.')
    target, _, target_suffix = binding['module'].partition('.')
    if not suffix or suffix != target_suffix or source == target:
        raise RuntimeError(f'Invalid module binding for {adapter}: {binding}')
    pattern = re.compile(r'\b' + re.escape(source) + r'\b')
    for path in sorted(folder.rglob('*')):
        if path.is_file() and path.suffix in {'.py', '.toml'}:
            original = path.read_text()
            adapted = pattern.sub(target, original)
            if adapted != original:
                path.write_text(adapted)
                print(f'Bound product module in {path.relative_to(folder)}', flush=True)


def main():
    WHEELS.mkdir(parents=True, exist_ok=True)
    entries = json.loads((ASSETS / 'dependencies.json').read_text())
    with ThreadPoolExecutor(max_workers=8) as pool:
        paths = list(pool.map(download, entries))
    wheels = [str(path) for path in paths if path.suffix == '.whl']
    run('python3', '-m', 'pip', 'install', '--no-index', '--no-deps',
        '--upgrade', *wheels)
    for archive in (path for path in paths if path.suffix != '.whl'):
        with tarfile.open(archive) as source:
            source.extractall(ROOT, filter='data')
            folder = ROOT / source.getmembers()[0].name.split('/')[0]
        entry = next(item for item in entries if item['filename'] == archive.name)
        for binding in entry.get('module_bindings', []):
            bind_product_module(folder, binding)
        run('python3', '-m', 'pip', 'wheel', '--no-index', '--no-deps',
            '--no-build-isolation', '--wheel-dir', str(WHEELS), str(folder))
        built = [str(path) for path in WHEELS.glob('*.whl')
                 if path.name not in {item.name for item in paths}]
        run('python3', '-m', 'pip', 'install', '--no-index', '--no-deps', *built)
    Path('/etc/pip.conf').write_text(
        '[global]\nno-index = true\nfind-links = /opt/third-party/wheels\n'
        'disable-pip-version-check = true\n'
    )
    run('chmod', '-R', 'a+rX', str(ROOT))


if __name__ == '__main__':
    main()
