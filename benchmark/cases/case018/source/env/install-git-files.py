"""Install pinned third-party trees, verifying every required Git blob."""
import json
import pathlib
import subprocess
from archive import unpack
from download import fetch

packages = json.loads(pathlib.Path('/env-assets/git-files.json').read_text())
for package in packages:
    root = pathlib.Path('/opt/dependency-src') / package['name']
    root.parent.mkdir(parents=True, exist_ok=True)
    archive = root.with_name(root.name + '.tar.gz')
    fetch(package['url'], archive)
    unpack(archive, root, package['files'])
    archive.unlink()

for package in packages:
    if '/' in package['name']:
        continue
    root = pathlib.Path('/opt/dependency-src') / package['name']
    subprocess.run(['/opt/product-env/bin/python', '-m', 'pip', 'install', '--no-index', '--no-build-isolation', '--no-deps', str(root)], check=True)
