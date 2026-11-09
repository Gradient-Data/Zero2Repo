# feature: F18
"""Acceptance observations of SFTP file access and transfer."""
import os
import stat
import time
import pytest
import velnora
from _helpers import run_async
from F09_helpers import session_connection
from F18_helpers import (file_service, remote_bytes, SeparatedNames,
                         ApplicationMapping, DiskWireService, wire_connection, transfer_scenarios)


def test_negotiation(tmp_path):
    async def exercise():
        async with file_service(tmp_path) as conn:
            async with conn.start_sftp_client() as client:
                assert client.version == 3
            for version in (4, 5, 6):
                async with conn.start_sftp_client(sftp_version=version) as client:
                    assert client.version == version
        async with file_service(tmp_path, version=3) as conn:
            async with conn.start_sftp_client(sftp_version=6) as client:
                assert client.version == 3
        # The server's default version is 3, so a client asking for 6 agrees on 3.
        async with file_service(tmp_path, version=None) as conn:
            async with conn.start_sftp_client(sftp_version=6) as client:
                assert client.version == 3
        async with session_connection(handler=False) as (conn, _):
            with pytest.raises(velnora.ChannelOpenError):
                await conn.start_sftp_client()
        async with wire_connection(DiskWireService(tmp_path, bad_version=True)) as conn:
            with pytest.raises(velnora.SFTPBadMessage):
                await conn.start_sftp_client()
        return 'test_negotiation'
    assert run_async(exercise()) == 'test_negotiation'


def test_file_modes_offsets_and_encoding(tmp_path):
    async def exercise():
        async with file_service(tmp_path) as conn:
            for version in (3, 4, 5, 6):
                async with conn.start_sftp_client(sftp_version=version) as client:
                    path = 'data' + str(version)
                    async with client.open(path, 'xb') as file:
                        assert await file.write(b'abcdef') == 6
                        assert await file.tell() == 6
                    with pytest.raises(velnora.SFTPFailure if version == 3 else velnora.SFTPFileAlreadyExists):
                        await client.open(path, 'xb')
                    async with client.open(path, 'r+b') as file:
                        assert await file.read(2) == b'ab'
                        assert await file.tell() == 2
                        assert await file.seek(1, os.SEEK_CUR) == 3
                        assert await file.read(1) == b'd'
                        assert await file.seek(-2, os.SEEK_END) == 4
                        assert await file.read() == b'ef'
                        assert await file.read(1) == b''
                        await file.seek(0)
                        await file.write(b'XY', 2)
                        assert await file.read(6, 0) == b'abXYef'
                        await file.truncate(4)
                    async with client.open(path, 'ab') as file:
                        await file.write(b'!')
                    assert (tmp_path / path).read_bytes() == b'abXY!'
                    async with client.open(path, 'wb') as file:
                        await file.write(b'Z', 5)
                    assert (tmp_path / path).read_bytes() == b'\0' * 5 + b'Z'
            async with conn.start_sftp_client() as client:
                for path, options, text, encoded in [
                    ('utf', {}, '雪 café', '雪 café'.encode()),
                    ('latin', {'encoding': 'latin-1'}, 'café', b'caf\xe9')]:
                    async with client.open(path, 'w', **options) as file:
                        await file.write(text)
                    assert (tmp_path / path).read_bytes() == encoded
                    async with client.open(path, 'r', **options) as file:
                        assert await file.read() == text
        return 'test_file_modes_offsets_and_encoding'
    assert run_async(exercise()) == 'test_file_modes_offsets_and_encoding'


def test_metadata(tmp_path):
    path = tmp_path / 'data'
    path.write_bytes(b'abcdefgh')
    (tmp_path / 'link').symlink_to('data')
    async def exercise():
        async with file_service(tmp_path) as conn:
            async with conn.start_sftp_client() as client:
                await client.chmod('data', 0o640)
                await client.utime('data', (1600000000, 1600000100))
                await client.chown('data', os.getuid(), os.getgid())
                with pytest.raises((velnora.SFTPPermissionDenied, velnora.SFTPFailure)):
                    await client.chown('data', os.getuid() + 1, os.getgid())
                attrs = await client.stat('link')
                assert (attrs.size, stat.S_IMODE(attrs.permissions), attrs.uid, attrs.gid,
                        attrs.atime, attrs.mtime) == (8, 0o640, os.getuid(), os.getgid(),
                                                    1600000000, 1600000100)
                assert stat.S_ISLNK((await client.lstat('link')).permissions)
                await client.truncate('data', 6)
                assert (await client.stat('data')).size == 6
                async with client.open('data', 'r+b') as file:
                    await file.truncate(3)
                    await file.chmod(0o600)
                    await file.chown(os.getuid(), os.getgid())
                    with pytest.raises((velnora.SFTPPermissionDenied, velnora.SFTPFailure)):
                        await file.chown(os.getuid() + 1, os.getgid())
                    await file.utime((1600000200, 1600000300))
                    attrs = await file.stat()
                    assert (attrs.size, stat.S_IMODE(attrs.permissions), attrs.uid, attrs.gid,
                            attrs.atime, attrs.mtime) == (3, 0o600, os.getuid(), os.getgid(),
                                                        1600000200, 1600000300)
                assert os.utime in os.supports_follow_symlinks, 'Link timestamps require filesystem support'
                os.utime(tmp_path / 'link', (1500000000, 1500000100), follow_symlinks=False)
                before = path.stat()
                await client.utime('link', (1500000200, 1500000300), follow_symlinks=False)
                link = (tmp_path / 'link').lstat()
                assert (int(link.st_atime), int(link.st_mtime)) == (1500000200, 1500000300)
                observed_link = await client.lstat('link')
                assert (observed_link.atime, observed_link.mtime) == (1500000200, 1500000300)
                after = path.stat()
                assert (after.st_atime_ns, after.st_mtime_ns) == (before.st_atime_ns, before.st_mtime_ns)
        observed = path.stat()
        assert (path.read_bytes(), stat.S_IMODE(observed.st_mode), int(observed.st_mtime)) == (b'abc', 0o600, 1600000300)
        return 'test_metadata'
    assert run_async(exercise()) == 'test_metadata'


def test_extensions_and_commit(tmp_path):
    (tmp_path / 'data').write_bytes(b'first')
    (tmp_path / 'other').write_bytes(b'old')
    async def exercise():
        async with file_service(tmp_path) as conn:
            async with conn.start_sftp_client() as client:
                attrs = await client.statvfs('/')
                local = os.statvfs(tmp_path)
                assert (attrs.bsize, attrs.frsize, attrs.blocks) == (local.f_bsize, local.f_frsize, local.f_blocks)
                await client.link('data', 'hard')
                (tmp_path / 'hard').write_bytes(b'shared update')
                assert (tmp_path / 'data').read_bytes() == b'shared update'
                await client.posix_rename('data', 'other')
                assert (tmp_path / 'other').read_bytes() == b'shared update'
                await client.symlink('other', 'link')
                # Linux has no symlink chmod support; unavailable metadata must fail.
                with pytest.raises(velnora.SFTPOpUnsupported):
                    await client.chmod('link', 0o600, follow_symlinks=False)
        async with wire_connection(DiskWireService(tmp_path)) as conn:
            async with conn.start_sftp_client() as client:
                async with client.open('pending', 'wb', block_size=0) as file:
                    await file.write(b'committed through independent service')
                    assert not (tmp_path / 'committed').exists()
                    await file.fsync()
                    assert (tmp_path / 'committed').read_bytes() == b'committed through independent service'
        async with wire_connection(DiskWireService(tmp_path, extensions=False)) as conn:
            async with conn.start_sftp_client() as client:
                async with client.open('pending', 'rb') as file:
                    with pytest.raises(velnora.SFTPOpUnsupported):
                        await file.fsync()
        return 'test_extensions_and_commit'
    assert run_async(exercise()) == 'test_extensions_and_commit'


def test_directories_paths_and_links(tmp_path):
    (tmp_path / 'kept').mkdir()
    (tmp_path / 'kept' / 'data').write_bytes(b'keep target')
    async def exercise():
        async with file_service(tmp_path) as conn:
            async with conn.start_sftp_client() as client:
                await client.makedirs('tree/a/b')
                await client.chdir('tree/a')
                assert await client.getcwd() == '/tree/a'
                assert await client.realpath('b/..') == '/tree/a'
                async with client.open('item', 'wb') as file:
                    await file.write(b'listing payload')
                names = {entry.filename: entry.attrs for entry in await client.readdir('.')}
                assert {'b', 'item'} <= names.keys()
                assert names['item'].size == len(b'listing payload')
                await client.rename('item', 'renamed')
                async with client.open('existing', 'wb') as file:
                    await file.write(b'original')
                with pytest.raises(velnora.SFTPFailure):
                    await client.rename('renamed', 'existing')
                assert await remote_bytes(client, 'existing') == b'original'
                await client.remove('existing')
                assert not os.path.lexists(tmp_path / 'tree' / 'a' / 'existing')
                assert (tmp_path / 'tree' / 'a' / 'renamed').read_bytes() == b'listing payload'
                await client.rmdir('b')
                assert not os.path.lexists(tmp_path / 'tree' / 'a' / 'b')
                # Only empty directories are removed; a v3 refusal is a failure.
                await client.makedirs('full/inner')
                with pytest.raises(velnora.SFTPFailure):
                    await client.rmdir('full')
                assert (tmp_path / 'tree' / 'a' / 'full' / 'inner').is_dir()
                await client.symlink('/kept', 'alias')
                assert await client.readlink('alias') == '/kept'
                await client.chdir('/')
                await client.rmtree('tree')
                assert not (tmp_path / 'tree').exists()
                assert (tmp_path / 'kept' / 'data').read_bytes() == b'keep target'
        return 'test_directories_paths_and_links'
    assert run_async(exercise()) == 'test_directories_paths_and_links'


def test_search_patterns(tmp_path):
    (tmp_path / 'nested').mkdir()
    for path in ('apple.txt', 'berry.txt', 'nested/apple.txt'):
        (tmp_path / path).write_bytes(path.encode())
    async def exercise():
        async with file_service(tmp_path) as conn:
            async with conn.start_sftp_client() as client:
                for pattern, expected in [('*', {'apple.txt', 'berry.txt', 'nested'}),
                    ('?pple.txt', {'apple.txt'}), ('[ab]*.txt', {'apple.txt', 'berry.txt'}),
                    ('**/*.txt', {'apple.txt', 'berry.txt', 'nested/apple.txt'})]:
                    assert set(await client.glob(pattern)) == expected
                (tmp_path / '.hidden.txt').write_bytes(b'explicit hidden match')
                assert set(await client.glob('.*.txt')) == {'.hidden.txt'}
                with pytest.raises(velnora.SFTPNoSuchFile):
                    await client.glob('absent*')
                errors = []
                assert await client.glob('absent*', error_handler=errors.append) == []
                assert len(errors) == 1 and isinstance(errors[0], velnora.SFTPNoSuchFile)
        return 'test_search_patterns'
    assert run_async(exercise()) == 'test_search_patterns'


def test_failure_categories(tmp_path):
    (tmp_path / 'denied').write_bytes(b'secret')
    (tmp_path / 'denied').chmod(0)
    (tmp_path / 'data').write_bytes(b'ok')
    async def exercise():
        async with file_service(tmp_path) as conn:
            async with conn.start_sftp_client(sftp_version=6) as client:
                assert await remote_bytes(client, 'data') == b'ok'
                with pytest.raises(velnora.SFTPNoSuchFile):
                    await client.stat('missing')
                with pytest.raises(velnora.SFTPPermissionDenied):
                    await client.open('denied', 'rb')
                async with client.open('data', 'rb') as file:
                    with pytest.raises(velnora.SFTPOpUnsupported):
                        await file.lock(0, 1, 0)
                with pytest.raises(ValueError):
                    await file.read()
                file = await client.open('data', 'rb')
                conn.abort()
                with pytest.raises(velnora.SFTPConnectionLost):
                    await file.read()
        async with wire_connection(DiskWireService(tmp_path, revoke_handle=True)) as conn:
            async with conn.start_sftp_client() as client:
                file = await client.open('data', 'rb', block_size=0)
                with pytest.raises(velnora.SFTPInvalidHandle):
                    await file.read(1)
                with pytest.raises(velnora.SFTPInvalidHandle):
                    await file.close()
        async with wire_connection(DiskWireService(tmp_path, malformed=True)) as conn:
            async with conn.start_sftp_client() as client:
                with pytest.raises(velnora.SFTPBadMessage):
                    await client.stat('data')
        return 'test_failure_categories'
    assert run_async(exercise()) == 'test_failure_categories'


def test_download_selection_and_recursion(tmp_path):
    run_async(transfer_scenarios(tmp_path, 'get'))


def test_upload_selection_and_recursion(tmp_path):
    run_async(transfer_scenarios(tmp_path, 'put'))


def test_copy_selection_and_recursion(tmp_path):
    run_async(transfer_scenarios(tmp_path, 'copy'))



def test_transfer_preservation_and_links(tmp_path):
    remote, local = tmp_path / 'remote', tmp_path / 'local'
    remote.mkdir(); local.mkdir()
    for base in (remote, local):
        (base / 'tree').mkdir()
        (base / 'tree' / 'file').write_bytes(b'linked payload')
        (base / 'tree' / 'link').symlink_to('file')
        (base / 'tree' / 'file').chmod(0o640)
    async def exercise():
        async with file_service(remote, chroot=False) as conn:
            async with conn.start_sftp_client() as client:
                await client.chdir(str(remote))
                for operation in ('get', 'put', 'copy'):
                    source = local if operation == 'put' else remote
                    target = local if operation == 'get' else remote
                    (source / 'metadata').write_bytes(b'metadata transfer')
                    (source / 'metadata').chmod(0o640)
                    # A future access time is newer than the modification and
                    # change times, so reading the source during transfer does
                    # not normally replace it (relatime); where a mount updates
                    # it on every read, the source's later value is accepted.
                    access = int(time.time()) + 2 * 86400
                    os.utime(source / 'metadata', (access, 1600000500))
                    metadata_dest = target / (operation + '-metadata')
                    await getattr(client, operation)(str(source / 'metadata'),
                                                      str(metadata_dest), preserve=True)
                    metadata = metadata_dest.stat()
                    assert (stat.S_IMODE(metadata.st_mode), int(metadata.st_mtime)) == (0o640, 1600000500)
                    assert int(metadata.st_atime) in {access, int((source / 'metadata').stat().st_atime)}
                    assert metadata_dest.read_bytes() == b'metadata transfer'
                    for follow in (False, True):
                        os.utime(source / 'tree' / 'file', (1600000400, 1600000500))
                        dest = target / (operation + str(follow))
                        await getattr(client, operation)(
                            str(source / 'tree'), str(dest), recurse=True,
                            preserve=True, follow_symlinks=follow)
                        metadata = (dest / 'file').stat()
                        assert (stat.S_IMODE(metadata.st_mode), int(metadata.st_mtime)) == (0o640, 1600000500)
                        assert (dest / 'file').read_bytes() == b'linked payload'
                        if follow:
                            assert stat.S_ISREG((dest / 'link').lstat().st_mode)
                            assert (dest / 'link').read_bytes() == b'linked payload'
                        else:
                            assert os.readlink(dest / 'link') == 'file'
                (local / 'links').mkdir()
                await client.get('tree/link', local / 'links')
                assert os.readlink(local / 'links' / 'link') == 'file'
        return 'test_transfer_preservation_and_links'
    assert run_async(exercise()) == 'test_transfer_preservation_and_links'


def test_download_link_confinement(tmp_path):
    remote, local = tmp_path / 'remote', tmp_path / 'local'
    remote.mkdir(); local.mkdir()
    (remote / 'tree' / 'sub').mkdir(parents=True)
    (remote / 'tree' / 'file').write_bytes(b'inside root')
    (remote / 'tree' / 'simple').symlink_to('file')
    (remote / 'tree' / 'sub' / 'parent').symlink_to('../file')
    async def exercise():
        async with file_service(remote, chroot=False) as conn:
            async with conn.start_sftp_client() as client:
                await client.chdir(str(remote))
                await client.get('tree', local / 'safe', recurse=True)
                for link, target in [('simple', 'file'), ('sub/parent', '../file')]:
                    assert os.readlink(local / 'safe' / link) == target
                    assert (local / 'safe' / link).read_bytes() == b'inside root'
                # The supplied destination directory is the root, so a target
                # leaving it is refused even when it stays inside its parent.
                for name, target in [('absolute', '/outside'), ('escape', '../../outside'),
                                     ('escape1', '../outside')]:
                    (remote / name).symlink_to(target)
                    with pytest.raises(velnora.SFTPBadMessage):
                        await client.get(name, local)
                    assert not os.path.lexists(local / name)
                # A directory newly created by recursive transfer is the root.
                (remote / 'hostile' / 'sub').mkdir(parents=True)
                (remote / 'hostile' / 'sub' / 'inner').symlink_to('../file')
                (remote / 'hostile' / 'sub' / 'out').symlink_to('../../outside')
                with pytest.raises(velnora.SFTPBadMessage):
                    await client.get('hostile', local / 'fresh', recurse=True)
                assert not os.path.lexists(local / 'fresh' / 'sub' / 'out')
                # Without a destination, the local working directory is the root.
                (remote / 'staying').symlink_to('safe/file')
                (remote / 'escape2').symlink_to('../outside')
                previous = os.getcwd()
                try:
                    os.chdir(local)
                    await client.get('staying')
                    assert os.readlink(local / 'staying') == 'safe/file'
                    assert (local / 'staying').read_bytes() == b'inside root'
                    with pytest.raises(velnora.SFTPBadMessage):
                        await client.get('escape2')
                    assert not os.path.lexists(local / 'escape2')
                finally:
                    os.chdir(previous)
        return 'test_download_link_confinement'
    assert run_async(exercise()) == 'test_download_link_confinement'


def test_download_child_names(tmp_path):
    remote, local = tmp_path / 'remote', tmp_path / 'local'
    remote.mkdir(); local.mkdir()
    (remote / 'tree').mkdir()
    (remote / 'tree' / 'child').write_bytes(b'legal child')
    outside = tmp_path / 'child'
    outside.write_bytes(b'outside sentinel')
    async def exercise():
        async with file_service(remote) as conn:
            async with conn.start_sftp_client() as client:
                await client.get('tree', local / 'good', recurse=True)
                assert set(p.name for p in (local / 'good').iterdir()) == {'child'}
                assert (local / 'good' / 'child').read_bytes() == b'legal child'
        async with file_service(remote, factory=SeparatedNames) as conn:
            async with conn.start_sftp_client() as client:
                with pytest.raises(velnora.SFTPBadMessage):
                    await client.get('tree', local / 'bad', recurse=True)
        assert outside.read_bytes() == b'outside sentinel'
        assert not (local / 'child').exists()
        return 'test_download_child_names'
    assert run_async(exercise()) == 'test_download_child_names'


def test_progress_and_error_handlers(tmp_path):
    remote, local = tmp_path / 'remote', tmp_path / 'local'
    remote.mkdir(); local.mkdir()
    payload = bytes(range(256)) * 300
    (remote / 'data').write_bytes(payload)
    (remote / 'tree').mkdir()
    async def exercise():
        async with file_service(remote) as conn:
            async with conn.start_sftp_client(sftp_version=6) as client:
                progress = []
                await client.get('data', local / 'data', block_size=4096,
                                 progress_handler=lambda *args: progress.append(args))
                assert (local / 'data').read_bytes() == payload
                assert progress
                for src, dst, done, total in progress:
                    assert (src, dst, total) == (b'data', os.fsencode(local / 'data'), len(payload))
                    assert 0 <= done <= total
                assert progress[-1][2] == len(payload)
                # Uploads and remote copies report the same per-file progress.
                for operation, source, target, stored in [
                        ('put', local / 'data', 'uploaded', remote / 'uploaded'),
                        ('copy', 'data', 'copied', remote / 'copied')]:
                    progress = []
                    await getattr(client, operation)(
                        source, target, block_size=4096,
                        progress_handler=lambda *args: progress.append(args))
                    assert stored.read_bytes() == payload
                    assert progress
                    for src, dst, done, total in progress:
                        assert (src, dst, total) == (os.fsencode(source), target.encode(), len(payload))
                        assert 0 <= done <= total
                    assert progress[-1][2] == len(payload)
                (local / 'abort').mkdir()
                with pytest.raises(velnora.SFTPFileIsADirectory):
                    await client.get(['tree', 'data'], local / 'abort')
                errors = []
                (local / 'continued').mkdir()
                await client.get(['tree', 'data'], local / 'continued', error_handler=errors.append)
                assert len(errors) == 1 and isinstance(errors[0], velnora.SFTPFileIsADirectory)
                assert (local / 'continued' / 'data').read_bytes() == payload
                class HandlerFailure(Exception): pass
                def reject(error):
                    assert isinstance(error, velnora.SFTPFileIsADirectory)
                    raise HandlerFailure()
                with pytest.raises(HandlerFailure):
                    await client.get('tree', local / 'rejected', error_handler=reject)
        return 'test_progress_and_error_handlers'
    assert run_async(exercise()) == 'test_progress_and_error_handlers'


def test_remote_copy_ranges(tmp_path):
    source = b'0123456789abcdefghij'
    (tmp_path / 'source').write_bytes(source)
    async def exercise():
        async with wire_connection(DiskWireService(tmp_path, copy_only=True)) as conn:
            async with conn.start_sftp_client() as client:
                await client.copy('source', 'required', remote_only=True)
                assert (tmp_path / 'required').read_bytes() == source
                async with client.open('source', 'rb', block_size=0) as src:
                    with pytest.raises(velnora.SFTPPermissionDenied):
                        await src.read(1)
                    for name, options, expected in [
                        ('whole', {}, source),
                        ('range', {'src_offset': 3, 'src_length': 7, 'dst_offset': 2}, b'\0\0' + source[3:10]),
                        ('tail', {'src_offset': 12, 'src_length': 0}, source[12:])]:
                        async with client.open(name, 'wb', block_size=0) as dst:
                            await client.remote_copy(src, dst, **options)
                        assert (tmp_path / name).read_bytes() == expected
        async with wire_connection(DiskWireService(tmp_path, extensions=False)) as conn:
            async with conn.start_sftp_client() as client:
                with pytest.raises(velnora.SFTPOpUnsupported):
                    await client.copy('source', 'unavailable', remote_only=True)
                await client.copy('source', 'without-extension')
                assert (tmp_path / 'without-extension').read_bytes() == source
        async with file_service(tmp_path) as conn:
            async with conn.start_sftp_client() as client:
                await client.copy('source', 'ordinary')
                assert (tmp_path / 'ordinary').read_bytes() == source
                # The product's own server offers remote copying; the same
                # offset and length table holds against it.
                await client.copy('source', 'served', remote_only=True)
                assert (tmp_path / 'served').read_bytes() == source
                async with client.open('source', 'rb') as src:
                    for name, options, expected in [
                        ('served-whole', {}, source),
                        ('served-range', {'src_offset': 3, 'src_length': 7, 'dst_offset': 2}, b'\0\0' + source[3:10]),
                        ('served-tail', {'src_offset': 12, 'src_length': 0}, source[12:])]:
                        async with client.open(name, 'wb') as dst:
                            await client.remote_copy(src, dst, **options)
                        assert (tmp_path / name).read_bytes() == expected
        return 'test_remote_copy_ranges'
    assert run_async(exercise()) == 'test_remote_copy_ranges'


def test_virtual_root_and_application_mapping(tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    (tmp_path / 'outside').write_bytes(b'outside sentinel')
    (root / 'actual').write_bytes(b'application mapped payload')
    async def exercise():
        async with file_service(root) as conn:
            async with conn.start_sftp_client() as client:
                assert await client.realpath('/') == '/'
                assert await client.realpath('../../') == '/'
                await client.makedirs('/dir/sub')
                await client.chdir('/dir/sub')
                async with client.open('../../created', 'wb') as file:
                    await file.write(b'within virtual root')
                await client.symlink('/actual', '/alias')
                assert await client.readlink('/alias') == '/actual'
                assert await remote_bytes(client, '/alias') == b'application mapped payload'
                await client.symlink('../../../actual', '/dir/sub/up')
                assert await remote_bytes(client, '/dir/sub/up') == b'application mapped payload'
                with pytest.raises(velnora.SFTPNoSuchFile):
                    await client.open('/../../outside', 'rb')
        assert (root / 'created').read_bytes() == b'within virtual root'
        assert (tmp_path / 'outside').read_bytes() == b'outside sentinel'
        async with file_service(root, factory=ApplicationMapping) as conn:
            async with conn.start_sftp_client() as client:
                assert await remote_bytes(client, '/published') == b'application mapped payload'
                assert (await client.stat('/published')).size == len(b'application mapped payload')
                with pytest.raises(velnora.SFTPPermissionDenied):
                    await client.open('/actual', 'rb')
        return 'test_virtual_root_and_application_mapping'
    assert run_async(exercise()) == 'test_virtual_root_and_application_mapping'
