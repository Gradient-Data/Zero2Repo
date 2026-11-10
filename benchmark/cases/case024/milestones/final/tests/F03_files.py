# feature: F03
"""Acceptance tests for file IO, tracking, collections, and staging."""
import os
import sys
from pathlib import Path

import pytest
from velnora import Dir, File, task
from velnora.file import (FileSet, ContentFile, IFile,
                        ContentFileSet, ContentDir, IFileSet, IDir, glob_file)

from _helpers import write_text, run_python
from F01_helpers import resolved
from F02_helpers import restored_value
from velnora.value import get_type_registry
from F03_helpers import disk_contents, move_mtime, serve_files, create_tls_certificate
from F03_services import object_store


def test_f03_t01(tmp_path):
    path = tmp_path / 'new' / 'text.dat'
    file = File(str(path))
    assert file.exists() is False
    with pytest.raises(FileNotFoundError):
        file.read()
    text = 'café / 雪\nsecond line'
    file.write(text, encoding='utf-16')
    assert path.read_bytes() == text.encode('utf-16')
    assert file.read(encoding='utf-16') == text
    assert file.exists() is True
    assert file.size() == len(text.encode('utf-16'))
    binary = b'\x00\xff\x80\r\nraw'
    path.write_bytes(binary)
    assert file.read('rb') == binary
    # A shorter rewrite must replace, not overlay, the longer existing bytes.
    rewritten = b'\xfe\x00short'
    assert len(rewritten) < len(binary)
    file.write(rewritten, mode='wb')
    assert path.read_bytes() == rewritten
    assert file.size() == len(rewritten)
    assert file.read('rb') == rewritten
    destination = tmp_path / 'copied' / 'bytes.dat'
    result = file.copy_to(File(str(destination)))
    assert result.path == str(destination)
    assert destination.read_bytes() == rewritten
    for _ in range(2):
        file.remove()
        assert file.exists() is False
        assert not path.exists()
        with pytest.raises(FileNotFoundError):
            path.read_bytes()
        with pytest.raises(FileNotFoundError):
            file.read('rb')
    assert destination.read_bytes() == rewritten


def test_f03_t02(tmp_path):
    # Loopback S3 and GCS services speak the providers' protocols; every
    # expectation is read back through an independent provider SDK client.
    for index, scheme in enumerate(("s3", "gs")):
        with object_store(scheme) as store:
            keys = ["nested/dir/source.bin", "copy.bin"]
            source, destination = (File(store.url(key)) for key in keys)
            assert source.exists() is False
            with pytest.raises(FileNotFoundError):
                source.read('rb')
            # The selected single-byte encoding differs from UTF-8 for these characters.
            text = 'cloud café ±\nsecond line'
            source.write(text, encoding='latin-1')
            assert store.read(keys[0]) == text.encode('latin-1')
            assert store.exists(keys[0]) is True
            assert source.exists() is True
            assert source.read(encoding='latin-1') == text
            unicode_text = 'cloud café / 雪\nsecond line'
            source.write(unicode_text, encoding='utf-8')
            assert store.read(keys[0]) == unicode_text.encode('utf-8')
            assert source.read(encoding='utf-8') == unicode_text
            payload = b'\x00\xff\x80provider bytes ' + scheme.encode() + b'\r\n'
            # Provider-origin data prevents a product-only in-memory round trip.
            store.write(keys[0], payload)
            assert File(store.url(keys[0])).read('rb') == payload
            assert source.read('rb') == payload
            source.write(payload[::-1], mode='wb')
            assert store.read(keys[0]) == payload[::-1]
            # An existing, longer destination is replaced by default.
            store.write(keys[1], b'stale destination bytes that are longer than the payload')
            copied = source.copy_to(destination)
            assert copied.path == store.url(keys[1])
            assert store.read(keys[1]) == payload[::-1]
            local = tmp_path / ('download-' + str(index)) / 'copy.bin'
            downloaded = destination.copy_to(File(str(local)))
            assert downloaded.path == str(local)
            assert local.read_bytes() == payload[::-1]
            local.write_bytes(payload + b'uploaded')
            uploaded = File(str(local)).copy_to(destination)
            assert uploaded.path == store.url(keys[1])
            assert store.read(keys[1]) == payload + b'uploaded'
            assert store.keys() == sorted(keys)
            # Version tracking: S3 follows the object entity tag, so a same-size
            # rewrite through the provider invalidates; GCS follows size.
            tracked = restored_value(File(store.url(keys[1])))
            assert tracked.is_valid() is True
            current = store.read(keys[1])
            if scheme == 's3':
                store.write(keys[1], bytes(reversed(current)))
                assert tracked.is_valid() is False
                tracked = restored_value(File(store.url(keys[1])))
                assert tracked.is_valid() is True
            store.write(keys[1], current + b'grown')
            assert tracked.is_valid() is False
            tracked = restored_value(File(store.url(keys[1])))
            assert tracked.is_valid() is True
            store.remove(keys[1])
            assert tracked.is_valid() is False
            store.write(keys[1], current)
            for file, key in zip((source, destination), keys):
                file.remove()
                assert store.exists(key) is False
                assert file.exists() is False
                with pytest.raises(FileNotFoundError):
                    file.read('rb')
            assert store.keys() == []


def test_f03_t03(tmp_path):
    root = tmp_path / 'source'
    directory = Dir(str(root))
    directory.mkdir()
    assert root.is_dir()
    assert directory.exists() is True
    expected = {'a.txt': b'alpha', 'nested/b.txt': b'beta',
                'nested/deep/a.txt': b'gamma', 'nested/other.bin': b'\x00\xff'}
    for name, data in expected.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    assert {str(Path(f.path).relative_to(root)) for f in directory} == set(expected)
    pattern = str(root / '**' / '*.txt')
    selected = {name for name in expected if name.endswith('.txt')}
    assert {str(Path(f.path).relative_to(root)) for f in FileSet(pattern)} == selected
    assert {str(Path(p).relative_to(root)) for p in glob_file(pattern)} == selected
    destination = tmp_path / 'destination'
    result = directory.copy_to(Dir(str(destination)))
    assert result.path == str(destination)
    assert disk_contents(destination) == expected
    # Baseline: non-recursive removal works on an empty directory.
    empty = Dir(str(tmp_path / 'empty'))
    empty.mkdir()
    assert (tmp_path / 'empty').is_dir()
    empty.rmdir()
    assert not (tmp_path / 'empty').exists()
    assert empty.exists() is False
    with pytest.raises(OSError):
        directory.rmdir()
    assert disk_contents(root) == expected
    directory.rmdir(recursive=True)
    assert not root.exists()
    assert directory.exists() is False
    assert disk_contents(destination) == expected


def test_f03_t04(tmp_path):
    path = write_text(tmp_path / 'version', 'alpha')
    original_stat = path.stat()
    tracked = restored_value(File(str(path)))
    assert tracked.is_valid() is True
    original_hash = tracked.get_hash()
    assert original_hash == File(str(path)).get_hash()
    other = write_text(tmp_path / 'other', 'alpha')
    os.utime(other, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    assert original_hash != File(str(other)).get_hash()
    # Equal size and time intentionally leave an ordinary version unchanged.
    path.write_text('bravo')
    os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    assert tracked.is_valid() is True
    assert original_hash == File(str(path)).get_hash()
    move_mtime(path)
    assert tracked.is_valid() is False
    assert original_hash != File(str(path)).get_hash()
    os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    path.write_text('longer replacement')
    os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    assert tracked.is_valid() is False
    assert original_hash != File(str(path)).get_hash()
    current = restored_value(File(str(path)))
    assert current.is_valid() is True
    # The saved form keeps the version tracked when saved: restoring after a change is stale.
    registry = get_type_registry()
    saved = registry.serialize(File(str(path)))
    restored_now = registry.deserialize(registry.get_type_name(File), saved)
    assert restored_now.is_valid() is True
    move_mtime(path)
    assert registry.deserialize(registry.get_type_name(File), saved).is_valid() is False
    current = restored_value(File(str(path)))
    assert current.is_valid() is True
    path.unlink()
    assert current.is_valid() is False


def test_f03_t05(tmp_path):
    path = write_text(tmp_path / 'content', 'alpha')
    content = restored_value(ContentFile(str(path)))
    original_hash = content.get_hash()
    immutable = restored_value(IFile(str(path)))
    assert content.is_valid() is True
    assert immutable.is_valid() is True
    move_mtime(path)
    assert content.is_valid() is True
    assert original_hash == ContentFile(str(path)).get_hash()
    assert immutable.get_hash() == IFile(str(path)).get_hash()
    stat = path.stat()
    path.write_text('bravo')
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert content.is_valid() is False
    assert original_hash != ContentFile(str(path)).get_hash()
    assert immutable.is_valid() is True
    assert immutable.get_hash() == IFile(str(path)).get_hash()
    other = write_text(tmp_path / 'other-content', 'bravo')
    assert immutable.get_hash() != IFile(str(other)).get_hash()

    @task(namespace='f03.file_values')
    def consume(file):
        return file.read().upper()

    assert resolved(consume(restored_value(ContentFile(str(path))))) == 'BRAVO'
    assert resolved(consume(immutable)) == 'BRAVO'
    path.unlink()
    assert immutable.is_valid() is True
    assert immutable.get_hash() == IFile(str(path)).get_hash()


def test_f03_t06(tmp_path):
    for kind in (Dir, FileSet):
        root = tmp_path / kind.__name__
        path = write_text(root / 'a.txt', 'first')
        selection = str(root) if kind is Dir else str(root / '*.txt')
        initial = restored_value(kind(selection))
        assert initial.is_valid() is True
        added = write_text(root / 'b.txt', 'second')
        assert initial.is_valid() is False
        full = restored_value(kind(selection))
        assert full.is_valid() is True
        added.unlink()
        assert full.is_valid() is False
        before_rename = restored_value(kind(selection))
        renamed = path.with_name('renamed.txt')
        path.rename(renamed)
        assert before_rename.is_valid() is False
        before_edit = restored_value(kind(selection))
        assert before_edit.is_valid() is True
        move_mtime(renamed)
        assert before_edit.is_valid() is False
        current = restored_value(kind(selection))
        assert current.is_valid() is True
        renamed.write_text('changed length and content')
        assert current.is_valid() is False
        if kind is FileSet:
            selected = restored_value(kind(selection))
            write_text(root / 'unselected.bin', 'outside selection')
            assert selected.is_valid() is True
        if kind is Dir:
            # Directory membership and versions include files in nested directories.
            before_nested = restored_value(kind(selection))
            assert before_nested.is_valid() is True
            nested = write_text(root / 'sub' / 'deep' / 'nested.txt', 'nested member')
            assert before_nested.is_valid() is False
            with_nested = restored_value(kind(selection))
            assert with_nested.is_valid() is True
            move_mtime(nested)
            assert with_nested.is_valid() is False
            nested_current = restored_value(kind(selection))
            assert nested_current.is_valid() is True
            nested.unlink()
            assert nested_current.is_valid() is False


def test_f03_t07(tmp_path):
    @task(namespace='f03.collections')
    def read_collection(collection):
        return sorted(file.read() for file in collection)

    for kind in (ContentFileSet, ContentDir, IFileSet, IDir):
        root = tmp_path / kind.__name__
        path = write_text(root / 'a.txt', 'first')
        selection = str(root) if kind in (ContentDir, IDir) else str(root / '*.txt')
        snapshot = restored_value(kind(selection))
        assert snapshot.is_valid() is True
        assert resolved(read_collection(snapshot)) == ['first']
        move_mtime(path)
        # ContentDir's metadata-only bug is documented in the requirement ledger.
        if kind is not ContentDir:
            assert snapshot.is_valid() is True
        snapshot = restored_value(kind(selection))
        stat = path.stat()
        path.write_text('other')
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        if kind is ContentFileSet:
            assert snapshot.is_valid() is False
        elif kind in (IFileSet, IDir):
            assert snapshot.is_valid() is True
        sized = restored_value(kind(selection))
        assert sized.is_valid() is True
        path.write_text('other text of a different size')
        # A size change alters both content and the ordinary tracked version.
        assert sized.is_valid() is (kind in (IFileSet, IDir))
        path.write_text('other')
        fresh = restored_value(kind(selection))
        assert resolved(read_collection(fresh)) == ['other']
        added = write_text(root / 'b.txt', 'added')
        assert fresh.is_valid() is (kind in (IFileSet, IDir))
        full = restored_value(kind(selection))
        assert resolved(read_collection(full)) == ['added', 'other']
        added.unlink()
        assert full.is_valid() is (kind in (IFileSet, IDir))
        if kind in (IFileSet, IDir):
            path.unlink()
            assert full.is_valid() is True


def test_f03_t08(tmp_path):
    source = write_text(tmp_path / 'storage' / 'input.txt', 'input bytes')
    tree = tmp_path / 'storage' / 'tree'
    write_text(tree / 'sub' / 'data.txt', 'nested input')
    file_stage = File(str(source)).stage(str(tmp_path / 'work' / 'file.txt'))
    dir_stage = Dir(str(tree)).stage(str(tmp_path / 'work' / 'tree'))
    local_file = file_stage.stage()
    local_dir = dir_stage.stage()
    assert local_file.path == str(tmp_path / 'work' / 'file.txt')
    assert local_dir.path == str(tmp_path / 'work' / 'tree')
    assert Path(local_file.path).read_bytes() == b'input bytes'
    assert disk_contents(local_dir.path) == {'sub/data.txt': b'nested input'}
    Path(local_file.path).write_text('generated output')
    write_text(Path(local_dir.path) / 'sub' / 'result.txt', 'generated tree')
    write_text(Path(local_dir.path) / 'sub' / 'data.txt', 'regenerated member')

    @task(namespace='f03.staging')
    def publish():
        return {'artifacts': [file_stage.unstage(), (dir_stage.unstage(),)]}

    result = resolved(publish())
    assert isinstance(result, dict)
    assert isinstance(result['artifacts'], list)
    assert isinstance(result['artifacts'][1], tuple)
    assert result['artifacts'][0].path == str(source)
    assert result['artifacts'][1][0].path == str(tree)
    assert source.read_bytes() == b'generated output'
    assert disk_contents(tree) == {'sub/data.txt': b'regenerated member',
                                   'sub/result.txt': b'generated tree'}


def test_f03_t09(tmp_path):
    root = tmp_path / 'served'
    root.mkdir()
    payload = b'first line\n\x00\xffremote bytes'
    (root / 'data.bin').write_bytes(payload)
    certificate, key = create_tls_certificate(tmp_path)
    for tls in (False, True):
        with serve_files(root, certificate=certificate if tls else None,
                         key=key if tls else None) as base:
            # Configure trust before importing the HTTP client in a fresh process.
            result = run_python('''import sys
from pathlib import Path
import pytest
from velnora import File
base, root, destination = sys.argv[1:]
payload = (Path(root) / 'data.bin').read_bytes()
remote = File(base + '/data.bin')
assert remote.read('rb') == payload
result = remote.copy_to(File(destination))
assert result.path == destination
assert Path(destination).read_bytes() == payload
missing = File(base + '/missing.bin')
with pytest.raises(FileNotFoundError):
    missing.read('rb')
with pytest.raises(FileNotFoundError):
    missing.copy_to(File(destination + '.missing'))
''', cwd=tmp_path,
                args=(base, str(root), str(tmp_path / ('download-' + str(tls)))),
                env={'SSL_CERT_FILE': str(certificate),
                     'PYTHONPATH': os.pathsep.join(sys.path)})
            assert result.returncode == 0, result


def test_f03_t10(tmp_path):
    source = write_text(tmp_path / 'source', 'replacement bytes')
    for preserve in (False, True):
        # Existing bytes are longer than the source so a stale tail would remain visible.
        destination = write_text(tmp_path / ('dest-' + str(preserve)),
                                 'existing destination bytes, longer than source')
        file = File(str(source))
        if preserve:
            result = file.copy_to(File(str(destination)), skip_if_exists=True)
        else:
            result = file.copy_to(File(str(destination)))
        assert result.path == str(destination)
        assert destination.read_bytes() == (b'existing destination bytes, longer than source'
                                            if preserve else b'replacement bytes')
        assert source.read_bytes() == b'replacement bytes'
    missing = tmp_path / 'missing' / 'destination'
    result = File(str(source)).copy_to(File(str(missing)), skip_if_exists=True)
    assert result.path == str(missing)
    assert missing.read_bytes() == b'replacement bytes'
