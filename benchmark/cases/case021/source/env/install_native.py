"""Acquire checksum-locked native inputs and install build/runtime tools."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

assets = Path(__file__).resolve().parent
lock = json.loads((assets / 'native.lock.json').read_text())
downloads = Path('/opt/native-downloads')
downloads.mkdir(parents=True, exist_ok=True)
for artifact in lock['artifacts']:
    target = downloads / artifact['file']
    subprocess.run([
        'curl', '--fail', '--location', '--retry', '4', '--retry-all-errors',
        '--connect-timeout', '30', '--speed-limit', '1024', '--speed-time', '60',
        '--output', str(target), artifact['url'],
    ], check=True)
    if hashlib.sha256(target.read_bytes()).hexdigest() != artifact['sha256']:
        raise RuntimeError(f'Checksum mismatch: {target.name}')

packages = [str(downloads / item['file'])
            for item in lock['artifacts'] if item['kind'] == 'deb']
env = dict(os.environ, DEBIAN_FRONTEND='noninteractive')
subprocess.run(['dpkg', '--install', *packages], check=True, env=env)
source = next(item for item in lock['artifacts'] if item['kind'] == 'cpython-source')
build = lock['cpython']
source_root = Path(build['source_root'])
source_root.parent.mkdir(parents=True, exist_ok=True)
subprocess.run(['tar', '-xJf', str(downloads / source['file']),
                '-C', str(source_root.parent)], check=True)
subprocess.run(['./configure', *build['configure']], cwd=source_root,
               env=dict(os.environ, CFLAGS=build['cflags']), check=True)
subprocess.run(['make', '-j2'], cwd=source_root, check=True)
# Keep both the build sources and unstripped executable for source-level debugging.
subprocess.run(['make', '-j2', 'altinstall'], cwd=source_root, check=True)
prefix = Path(build['prefix'])
for name in ('python3.11', 'python3.11-config'):
    Path('/usr/local/bin', name).symlink_to(prefix / 'bin' / name)
shutil.copy2(source_root / 'Tools/gdb/libpython.py',
             prefix / 'bin/python3.11-gdb.py')
Path('/etc/gdb/gdbinit.d').mkdir(parents=True, exist_ok=True)
Path('/etc/gdb/gdbinit.d/cpython311.gdb').write_text(
    f'add-auto-load-safe-path {prefix}/bin/python3.11-gdb.py\n')
# Reuse the already verified universal wheel, without resolving new dependencies.
setuptools = next(item for item in json.loads((assets / 'dependencies.json').read_text())
                  if item['name'] == 'setuptools')
subprocess.run([str(prefix / 'bin/python3.11'), '-m', 'pip', 'install',
                '--no-index', '--no-deps',
                str(Path('/opt/offline-wheels') / setuptools['url'].rsplit('/', 1)[1])],
               check=True)
