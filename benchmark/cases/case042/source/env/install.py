"""Install hash-locked Python dependencies and the standalone S3 server."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import sysconfig
from urllib.parse import urlparse

from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import parse_wheel_filename

assets = Path('/env-assets')
wheelhouse = Path('/opt/offline-wheels')
wheelhouse.mkdir(parents=True, exist_ok=True)
tags = list(sys_tags())
rank = {tag: index for index, tag in enumerate(tags)}


def fetch(package):
    candidates = []
    for wheel in package['wheels']:
        filename = Path(urlparse(wheel['url']).path).name
        compatible = parse_wheel_filename(filename)[3].intersection(rank)
        if compatible:
            candidates.append((min(rank[tag] for tag in compatible), filename, wheel))
    if not candidates:
        raise RuntimeError(f"No compatible locked wheel: {package['name']}=={package['version']}")
    _, filename, wheel = min(candidates, key=lambda item: item[0])
    target = wheelhouse / filename
    official = wheel['url']
    args = ['curl', '--fail', '--location', '--silent', '--show-error', '--retry', '3',
            '--connect-timeout', '20', '--max-time', '300', '--speed-limit', '1024', '--speed-time', '30']
    subprocess.run([*args, official, '--output', str(target)], check=True)
    actual = 'sha256:' + hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != wheel['hash']:
        raise RuntimeError(f"Checksum mismatch for {filename}: {actual}")
    print(f"Verified {filename}", flush=True)
    return str(target)


packages = json.loads((assets / 'dependencies.json').read_text())
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    wheels = list(pool.map(fetch, packages))
subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps', *wheels], check=True)
(Path(sys.prefix) / 'pip.conf').write_text('[global]\nno-index = true\nfind-links = /opt/offline-wheels\ndisable-pip-version-check = true\n')

# The warm build starts in a separate process, without Git metadata or shell
# exports from this installer. Provision the pinned SCM input in the judge
# interpreter so pip and its backend subprocesses receive it on startup.
product_version = json.loads((assets / 'product-version.json').read_text())
site_packages = Path(sysconfig.get_path('purelib'))
version_inputs = [product_version]
(site_packages / 'codingbench_product_version.pth').write_text(
    'import os; ' + '; '.join(
        'os.environ.setdefault(' + repr(item['environment_variable']) + ', ' + repr(item['version']) + ')'
        for item in version_inputs
    ) + '\n'
)

# Keep build-time project discovery available when /env-assets is not mounted.
for filename in ('build_product.py', 'product-version.json'):
    (Path('/opt/runtime') / filename).write_bytes((assets / filename).read_bytes())

# Provision the real S3 runtime in the same reproducible installation step.
subprocess.run([sys.executable, str(assets / "install_s3.py")], check=True)
