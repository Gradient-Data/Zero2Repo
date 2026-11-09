"""Validate installed third-party artifacts against the source checkout's lock."""
import hashlib
from importlib.metadata import version
from pathlib import Path
import tomllib
from packaging.utils import parse_wheel_filename

lock = tomllib.loads(Path('uv.lock').read_text())
constraints = []
for wheel in Path('/opt/dependency-wheels').glob('*.whl'):
    name, pinned, _, _ = parse_wheel_filename(wheel.name)
    packages = [p for p in lock['package'] if p['name'] == name]
    if not packages:
        # Build tools are declared by the build backend, outside the runtime lock.
        continue
    digest = 'sha256:' + hashlib.sha256(wheel.read_bytes()).hexdigest()
    matching = [p for p in packages if p.get('version') == str(pinned)
                and any(w['hash'] == digest for w in p.get('wheels', []))]
    if not matching or version(name) != str(pinned):
        raise RuntimeError(f'Installed artifact disagrees with source lock: {wheel.name}')
    constraints.append(f'{name}=={pinned}')
Path('/opt/locked-constraints.txt').write_text('\n'.join(sorted(constraints)) + '\n')
print(f'Validated {len(constraints)} installed dependencies against source lock')
