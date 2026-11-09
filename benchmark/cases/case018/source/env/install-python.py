"""Install a fixed, hash-verified third-party Python dependency closure."""
import concurrent.futures
import hashlib
import json
import pathlib
import subprocess
import sys
import sysconfig
from archive import unpack
from download import fetch

assets = pathlib.Path('/env-assets')
wheels = pathlib.Path('/opt/wheels')
wheels.mkdir(exist_ok=True)

def artifact(entry):
    path = wheels / entry['filename']
    fetch(entry['url'], path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
        raise ValueError(f'SHA256 mismatch for {path}')
    if entry.get('kind') == 'source':
        unpack(path, pathlib.Path('/opt/dependency-src') / entry['name'])

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    list(pool.map(artifact, json.loads((assets / 'python-artifacts.json').read_text())))
subprocess.run([sys.executable, '-m', 'venv', '/opt/product-env'], check=True)
pip = ['/opt/product-env/bin/python', '-m', 'pip', 'install', '--no-index', '--find-links=/opt/wheels', '--no-build-isolation']
subprocess.run(pip + ['setuptools==84.2.1', 'wheel==0.48.0', 'packaging==26.3'], check=True)
subprocess.run(pip + ['-r', str(assets / 'python-pins.txt')], check=True)

# The judge invokes the base interpreter directly. Process this environment's
# site directory at every startup, including editable-package .pth files written
# by the later offline product build. Prefer the verified dependency closure to
# unrelated packages bundled in the base image.
environment_site = subprocess.check_output(
    ['/opt/product-env/bin/python', '-c',
     'import sysconfig; print(sysconfig.get_path("purelib"))'], text=True
).strip()
judge_site = pathlib.Path(sysconfig.get_path('purelib'))
(judge_site / 'product-environment.pth').write_text(
    f'import sys, site; sys.path.insert(0, {environment_site!r}); '
    f'site.addsitedir({environment_site!r})\n', encoding='utf-8'
)
subprocess.run([sys.executable, '-c', 'import z3; import pytest'], check=True)
