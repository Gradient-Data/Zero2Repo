# feature: F19
"""Acceptance checks for SCP through real SSH sessions and filesystem results."""
import os
import stat
import velnora
import pytest
from _helpers import run_async, bounded
from F19_helpers import scp_service, scp_source_peer
from F18_helpers import ApplicationMapping


def test_transfer_directions_and_connections(tmp_path):
    async def check():
        local, first, second = [tmp_path / name for name in ('local', 'first', 'second')]
        for directory in (local, first, second): directory.mkdir()
        payload = bytes(range(256)) * 19 + b'upload\0'
        (local / 'upload').write_bytes(payload)
        (first / 'remote').write_bytes(b'remote selection\xff')
        async with scp_service(first) as left, scp_service(second) as right:
            # A host/port endpoint opens its own connection; other arms reuse live ones.
            host, port = left.get_extra_info('peername')[:2]
            await velnora.scp(local / 'upload', ((host, port), '/new'),
                config=None, known_hosts=None, client_keys=[], agent_path=None,
                username='member')
            assert (first / 'new').read_bytes() == payload
            await velnora.scp((left, '/remote'), local / 'download')
            assert (local / 'download').read_bytes() == b'remote selection\xff'
            await velnora.scp((left, '/new'), (right, '/relay'))
            assert (second / 'relay').read_bytes() == payload
            (second / 'mixed').mkdir()
            await velnora.scp([local / 'upload', (left, '/remote')], (right, '/mixed'))
            assert (second / 'mixed' / 'upload').read_bytes() == payload
            assert (second / 'mixed' / 'remote').read_bytes() == b'remote selection\xff'
            with pytest.raises(ValueError):
                await velnora.scp(local / 'upload', local / 'unsupported')
    run_async(check())


def test_selection_and_destination_rules(tmp_path):
    async def check():
        local, remote = tmp_path / 'local', tmp_path / 'remote'
        local.mkdir(); remote.mkdir()
        contents = {'part-a.bin': b'alpha\0', 'part-b.bin': b'beta\xff'}
        for name, data in contents.items(): (local / name).write_bytes(data)
        (local / 'unselected.txt').write_bytes(b'not selected')
        (remote / 'out').mkdir()
        async with scp_service(remote) as conn:
            await velnora.scp(local / 'part-a.bin', (conn, '/renamed'))
            assert (remote / 'renamed').read_bytes() == contents['part-a.bin']
            await velnora.scp(local / 'part-a.bin', (conn, '/out'))
            assert (remote / 'out' / 'part-a.bin').read_bytes() == contents['part-a.bin']
            await velnora.scp([local / name for name in contents], (conn, '/out'))
            assert {p.name: p.read_bytes() for p in (remote / 'out').iterdir()} == contents
            (remote / 'pattern').mkdir()
            await velnora.scp(str(local / 'part-?.bin'), (conn, '/pattern'))
            assert {p.name: p.read_bytes() for p in (remote / 'pattern').iterdir()} == contents
            (local / 'back').mkdir()
            await velnora.scp((conn, '/pattern/part-*.bin'), local / 'back')
            assert {p.name: p.read_bytes() for p in (local / 'back').iterdir()} == contents
            for target in ('/absent', '/renamed'):
                with pytest.raises(velnora.SFTPFailure):
                    await velnora.scp([local / name for name in contents], (conn, target))
            assert (remote / 'renamed').read_bytes() == contents['part-a.bin']
    run_async(check())


def test_recursive_copy_and_preservation(tmp_path):
    async def check():
        local, remote = tmp_path / 'local', tmp_path / 'remote'
        (local / 'tree' / 'nested').mkdir(parents=True); remote.mkdir()
        (local / 'tree' / 'empty').mkdir()
        leaf = local / 'tree' / 'nested' / 'leaf'
        leaf.write_bytes(b'nested contents\0')
        expected = {}
        for index, path in enumerate((leaf, local / 'tree' / 'nested', local / 'tree' / 'empty', local / 'tree')):
            mode = 0o640 if path == leaf else 0o750
            os.chmod(path, mode)
            os.utime(path, (1200000000 + index * 20, 1300000000 + index * 20))
            expected[path.relative_to(local / 'tree')] = (mode, int(path.stat().st_atime), int(path.stat().st_mtime))
        async with scp_service(remote) as conn:
            with pytest.raises(velnora.SFTPFailure):
                await velnora.scp(local / 'tree', (conn, '/refused'))
            await velnora.scp(local / 'tree', (conn, '/copy'), recurse=True, preserve=True)
            for relative, (mode, atime, mtime) in expected.items():
                metadata = (remote / 'copy' / relative).stat()
                assert stat.S_IMODE(metadata.st_mode) == mode
                assert int(metadata.st_atime) == atime
                assert int(metadata.st_mtime) == mtime
            assert (remote / 'copy' / 'nested' / 'leaf').read_bytes() == b'nested contents\0'
            assert (remote / 'copy' / 'empty').is_dir()
            # Reset source access times before testing the opposite direction.
            for relative, (mode, atime, mtime) in expected.items():
                os.utime(remote / 'copy' / relative, (atime, mtime))
            await velnora.scp((conn, '/copy'), local / 'returned', recurse=True, preserve=True)
            for relative, (mode, atime, mtime) in expected.items():
                metadata = (local / 'returned' / relative).stat()
                assert (stat.S_IMODE(metadata.st_mode), int(metadata.st_atime), int(metadata.st_mtime)) == (mode, atime, mtime)
            assert (local / 'returned' / 'nested' / 'leaf').read_bytes() == b'nested contents\0'
    run_async(check())


def test_server_enablement_and_transfer_failures(tmp_path):
    async def check():
        remote = tmp_path / 'remote'; remote.mkdir()
        source = tmp_path / 'source'; source.write_bytes(b'service data')
        async with scp_service(remote, enabled=False) as conn:
            with pytest.raises(velnora.ChannelOpenError):
                await velnora.scp(source, (conn, '/disabled'))
        async with scp_service(remote) as conn:
            await velnora.scp(source, (conn, '/enabled'))
            assert (remote / 'enabled').read_bytes() == b'service data'
            with pytest.raises(velnora.SFTPFailure):
                await velnora.scp((conn, '/missing'), tmp_path / 'missing')
            with pytest.raises(velnora.SFTPFailure):
                await velnora.scp(source, (conn, '/missing-parent/file'))
            malformed = await bounded(conn.run('scp -t /bad', input=b'C\n', encoding=None))
            # An error record may use either error byte, 1 or 2.
            assert malformed.stdout[:1] == b'\0' and malformed.stdout[1:2] in (b'\1', b'\2')
            assert malformed.stdout.endswith(b'\n')
            bad_command = await bounded(conn.run('scp -f -x /enabled', encoding=None))
            assert bad_command.exit_status != 0
            assert bad_command.stderr
        (remote / 'actual').write_bytes(b'published data')
        async with scp_service(remote, factory=ApplicationMapping) as conn:
            await velnora.scp((conn, '/published'), tmp_path / 'published')
            assert (tmp_path / 'published').read_bytes() == b'published data'
            with pytest.raises(velnora.SFTPFailure):
                await velnora.scp((conn, '/blocked'), tmp_path / 'blocked')
        async with scp_source_peer(b'short', b'partial', declared_size=100) as conn:
            with pytest.raises(velnora.SFTPConnectionLost):
                await velnora.scp((conn, '/source'), tmp_path / 'short')
    run_async(check())


def test_peer_names_progress_and_error_handling(tmp_path):
    async def check():
        received = tmp_path / 'received'; received.mkdir()
        # Prove the same protocol peer can deliver real data before rejecting names.
        async with scp_source_peer(b'valid', b'peer content') as conn:
            await velnora.scp((conn, '/source'), received)
        assert (received / 'valid').read_bytes() == b'peer content'
        for name in (b'../escape', b'nested/child', b'nested\\child', b'.', b'..'):
            before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
            async with scp_source_peer(name) as conn:
                with pytest.raises(velnora.SFTPBadMessage):
                    await velnora.scp((conn, '/source'), received)
            assert {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()} == before
        # Directory records in a recursive download follow the same name rules.
        async with scp_source_peer(b'valid-dir', directory=True) as conn:
            await velnora.scp((conn, '/source'), received, recurse=True)
        assert (received / 'valid-dir').is_dir()
        for name in (b'../escape', b'nested/child', b'.', b'..'):
            before = set(tmp_path.rglob('*'))
            async with scp_source_peer(name, directory=True) as conn:
                with pytest.raises(velnora.SFTPBadMessage):
                    await velnora.scp((conn, '/source'), received, recurse=True)
            assert set(tmp_path.rglob('*')) == before
        local, remote = tmp_path / 'local', tmp_path / 'remote'
        local.mkdir(); remote.mkdir()
        contents = {'large': bytes(range(256)) * 1100, 'small': b'tail', 'empty': b''}
        for name, data in contents.items(): (local / name).write_bytes(data)
        async with scp_service(remote) as conn:
            events = []
            await velnora.scp([local / name for name in contents], (conn, '/'),
                progress_handler=lambda src, dst, done, total: events.append((src, dst, done, total)))
            for name, data in contents.items():
                assert (remote / name).read_bytes() == data
                observations = [(done, total) for src, dst, done, total in events if os.path.basename(src) == os.fsencode(name)]
                assert observations
                assert observations[-1] == (len(data), len(data))
                assert all(0 <= done <= total == len(data) for done, total in observations)
                assert [done for done, total in observations] == sorted(done for done, total in observations)
            (remote / 'continue').mkdir(); (remote / 'abort').mkdir()
            errors = []
            sources = [local / 'missing', local / 'small']
            await velnora.scp(sources, (conn, '/continue'), error_handler=errors.append)
            assert len(errors) == 1
            assert isinstance(errors[0], OSError)
            assert (remote / 'continue' / 'small').read_bytes() == b'tail'
            with pytest.raises(FileNotFoundError):
                await velnora.scp(sources, (conn, '/abort'))
            class StopTransfer(Exception): pass
            def stop(error):
                raise StopTransfer() from error
            with pytest.raises(StopTransfer):
                await velnora.scp(sources, (conn, '/abort'), error_handler=stop)
    run_async(check())
