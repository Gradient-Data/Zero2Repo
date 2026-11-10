"""Read public source archives without trusting archive paths or file types."""
import hashlib
import pathlib
import tarfile


def unpack(archive, target, entries=None):
    target = pathlib.Path(target)
    with tarfile.open(archive) as tree:
        files = {}
        roots = set()
        for member in tree:
            relative = pathlib.PurePosixPath(member.name)
            if relative.is_absolute() or '..' in relative.parts or not relative.parts:
                raise ValueError(f'Unsafe archive path: {member.name}')
            roots.add(relative.parts[0])
            if member.isdir():
                continue
            if not member.isfile() or len(relative.parts) < 2:
                raise ValueError(f'Unsupported archive entry: {member.name}')
            name = '/'.join(relative.parts[1:])
            if name in files:
                raise ValueError(f'Duplicate archive entry: {name}')
            files[name] = member
        if len(roots) != 1:
            raise ValueError('Expected exactly one archive root')
        expected = entries if entries is not None else [
            {'path': name, 'mode': '100755' if member.mode & 0o111 else '100644'}
            for name, member in files.items()
        ]
        for entry in expected:
            relative = pathlib.PurePosixPath(entry['path'])
            if relative.is_absolute() or '..' in relative.parts or entry['mode'] not in ('100644', '100755'):
                raise ValueError(f'Unsupported inventory entry: {entry}')
            content = tree.extractfile(files[entry['path']]).read()
            if entries is not None:
                digest = hashlib.sha1(f'blob {len(content)}\0'.encode() + content).hexdigest()
                if len(content) != entry['size'] or digest != entry['sha']:
                    raise ValueError(f"Git blob integrity mismatch: {entry['path']}")
            path = target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            path.chmod(int(entry['mode'][-3:], 8))
