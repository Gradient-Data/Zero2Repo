"""Populate pinned external modules and install the supplied working tree offline."""
import argparse
import configparser
import hashlib
import importlib.metadata
import json
import pathlib
import shutil
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('tree', type=pathlib.Path, help='Working tree to build and install')
tree = parser.parse_args().tree.resolve(strict=True)
if not tree.is_dir():
    raise NotADirectoryError(tree)
if not (tree / 'pyproject.toml').is_file():
    raise FileNotFoundError(tree / 'pyproject.toml')
product = tree / '.product'
if product.exists():
    shutil.rmtree(product)
print(f'Building and installing working tree: {tree}', flush=True)

modules = configparser.ConfigParser()
with (tree / '.gitmodules').open(encoding='utf-8') as metadata:
    modules.read_file(metadata)
for section in modules.sections():
    destination = (tree / modules[section]['path']).resolve()
    destination.relative_to(tree)
    source = pathlib.Path('/opt/offline/modules') / destination.name
    if not source.is_dir():
        raise FileNotFoundError(source)
    shutil.copytree(source, destination, dirs_exist_ok=True)
subprocess.run([
    sys.executable, '-m', 'pip', 'install',
    '--no-index', '--no-deps', '--no-build-isolation', '--no-cache-dir',
    '--target', str(product), '--report', str(tree / '.installation.json'), str(tree),
], cwd=tree, check=True)

# Preserve evidence for the installation that crosses the /app-only handoff.
# Inspect the actual installed wheel, not a registry copy or the source package.
distributions = list(importlib.metadata.distributions(path=[str(product)]))
if len(distributions) != 1:
    raise RuntimeError(f'Expected one candidate distribution, found {len(distributions)}')
distribution = distributions[0]
commands = {}
for entry in distribution.entry_points:
    if entry.group == 'console_scripts':
        command = product / 'bin' / entry.name
        if not command.is_file():
            raise FileNotFoundError(command)
        commands[entry.name] = entry.value
files = {}
for installed in sorted(product.rglob('*')):
    path = installed.resolve(strict=True)
    relative = path.relative_to(product)
    if path.is_file():
        files[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
(tree / '.product-provenance.json').write_text(json.dumps({
    'source': str(tree),
    'interpreter': sys.executable,
    'distribution': distribution.metadata['Name'],
    'version': distribution.version,
    'console_scripts': commands,
    'files_sha256': files,
}, indent=2) + '\n', encoding='utf-8')
for path in product.rglob('*'):
    path.chmod(path.stat().st_mode | 0o444 | (0o111 if path.is_dir() else 0))
