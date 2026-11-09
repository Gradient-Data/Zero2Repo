# feature: F09
"""Six planned acceptance measurements of preview1 filesystem behavior.

Oracle: WASI snapshot-01 filesystem semantics, checked against real host files.
Expected byte vectors below were also observed on the original implementation.
No test asserts host fd/inode numbers, directory order, or diagnostic prose.
"""
import os
import struct

from F09_helpers import (
    F09Guest, F09_READ, F09_WRITE, F09_FILE_RIGHTS, F09_DIR_RIGHTS,
    f09_driver, f01_driver, f09_memory, f09_uint, f09_statuses, f09_dirents,
)


def test_named_preopens_and_host_mapping(f09_driver, tmp_path):
    # F09.T01: zero, one and multiple grants; names and storage both matter.
    left, right = tmp_path / 'left', tmp_path / 'right'
    left.mkdir()
    right.mkdir()
    (left / 'identity').write_bytes(b'left\x00map')
    (right / 'identity').write_bytes(b'right\xffmap')
    for grants in ([], [(right, '/one')], [(right, 'nested/right'), (left, '/two')]):
        guest = F09Guest()
        table, count, final = guest.enumerate()
        reads = []
        for i, (host, name) in enumerate(grants):
            guest.grant(name)
            guest.open(f'open-{i}', 'identity', rights=F09_READ)
            buf, used = guest.io(f'read-{i}', 'fd_read', 32)
            reads.append((buf, used, (host / 'identity').read_bytes()))
            guest.call(f'close-{i}', 'fd_close', 'local.get $file')
        mem = f09_memory(f09_driver.filesystem(guest, grants))
        f09_statuses(guest, mem)
        assert f09_uint(mem, final) == 8  # preview1 BADF terminates enumeration.
        assert f09_uint(mem, count) == len(grants)
        names = []
        for i in range(f09_uint(mem, count)):
            record = table + i * 264
            size = f09_uint(mem, record + 4)
            assert size <= 256
            names.append(mem[record+8:record+8+size])
        assert sorted(names) == sorted(name.encode() for _, name in grants)
        for buf, used, expected in reads:
            assert f09_uint(mem, used) == len(expected)
            assert mem[buf:buf+len(expected)] == expected


def test_file_io_positions_resize_sync_and_close(f09_driver, tmp_path):
    # F09.T02: independent native filesystem oracle for preview1 file semantics.
    root = tmp_path / 'grant'
    root.mkdir()
    initial = b'0123456789abcdef'
    (root / 'existing').write_bytes(initial)
    (root / 'truncate').write_bytes(initial)
    # This file is outside the grant. Native POSIX operations supply the oracle,
    # independently of guest execution and the implementation under test.
    oracle = tmp_path / 'native-reference'
    oracle.write_bytes(initial)
    expected_reads, expected_positions, expected_counts = [], [], []
    with oracle.open('r+b', buffering=0) as native:
        expected_reads.append(native.read(5))
        expected_reads.append(os.pread(native.fileno(), 4, 9))
        expected_positions.append(native.tell())
        expected_counts.append(os.pwrite(native.fileno(), b'XYZ', 1))
        expected_positions.append(native.tell())
        expected_counts.append(native.write(b'!?'))
        expected_positions.append(native.seek(-3, os.SEEK_END))
        expected_reads.append(native.read(3))
        expected_positions.append(native.seek(-6, os.SEEK_CUR))
        expected_reads.append(native.read(2))
        expected_positions.append(native.seek(2, os.SEEK_SET))
        expected_reads.append(native.read(3))
        native.truncate(7)
        os.fdatasync(native.fileno())
        os.fsync(native.fileno())
    expected_existing = oracle.read_bytes()
    expected_reads.append(expected_existing)
    with oracle.open('w+b', buffering=0) as native:
        expected_counts.append(native.write(b'\x00new\xff'))
        native.truncate(9)
        expected_created = os.pread(native.fileno(), 16, 0)
    expected_reads.append(expected_created)
    guest = F09Guest()
    guest.grant()
    guest.open('open', 'existing')
    first, first_n = guest.io('read', 'fd_read', 5)
    positional, positional_n = guest.io('pread', 'fd_pread', 4, offset=9)
    tell_read = guest.alloc(8)
    guest.call('tell-after-pread', 'fd_tell', 'local.get $file', tell_read)
    _, pwritten = guest.io('pwrite', 'fd_pwrite', [b'X', b'YZ'], offset=1)
    tell_write = guest.alloc(8)
    guest.call('tell-after-pwrite', 'fd_tell', 'local.get $file', tell_write)
    _, written = guest.io('write', 'fd_write', b'!?')
    endpos = guest.alloc(8)
    guest.call('seek-end', 'fd_seek', 'local.get $file', -3, 2, endpos)
    tail, tail_n = guest.io('read-tail', 'fd_read', 3)
    curpos = guest.alloc(8)
    guest.call('seek-current', 'fd_seek', 'local.get $file', -6, 1, curpos)
    middle, middle_n = guest.io('read-middle', 'fd_read', 2)
    setpos = guest.alloc(8)
    guest.call('seek-start', 'fd_seek', 'local.get $file', 2, 0, setpos)
    changed, changed_n = guest.io('read-changed', 'fd_read', 3)
    guest.call('shrink', 'fd_filestat_set_size', 'local.get $file', 7)
    stat = guest.alloc(64)
    guest.call('stat', 'fd_filestat_get', 'local.get $file', stat)
    guest.call('datasync', 'fd_datasync', 'local.get $file')
    guest.call('sync', 'fd_sync', 'local.get $file')
    guest.call('close', 'fd_close', 'local.get $file')
    # No intervening open/reuse: close must invalidate this ordinary file fd.
    vec = guest.alloc(8, struct.pack('<II', first, 1))
    unused = guest.alloc(4)
    guest.call('closed-read', 'fd_read', 'local.get $file', vec, 1, unused, required=False)
    guest.open('reopen', 'existing', rights=F09_READ)
    reopened, reopened_n = guest.io('read-reopened', 'fd_read', 32)
    guest.call('close-reopened', 'fd_close', 'local.get $file')
    guest.open('truncate-existing', 'truncate', flags=8)
    empty_stat = guest.alloc(64)
    guest.call('empty-stat', 'fd_filestat_get', 'local.get $file', empty_stat)
    guest.call('close-truncate', 'fd_close', 'local.get $file')
    guest.open('create', 'created', flags=1 | 4)
    _, created_n = guest.io('write-created', 'fd_write', b'\x00new\xff')
    guest.call('grow', 'fd_filestat_set_size', 'local.get $file', 9)
    grown, grown_n = guest.io('pread-grown', 'fd_pread', 16, offset=0)
    guest.call('close-created', 'fd_close', 'local.get $file')
    mem = f09_memory(f09_driver.filesystem(guest, [(root, '/sandbox')]))
    f09_statuses(guest, mem, {'closed-read': 8})
    for (buf, used), expected in zip([
            (first, first_n), (positional, positional_n), (tail, tail_n),
            (middle, middle_n), (changed, changed_n), (reopened, reopened_n),
            (grown, grown_n)], expected_reads, strict=True):
        assert f09_uint(mem, used) == len(expected)
        assert mem[buf:buf+len(expected)] == expected
    assert [f09_uint(mem, x, 64) for x in (tell_read, tell_write, endpos, curpos, setpos)] == expected_positions
    assert [f09_uint(mem, x) for x in (pwritten, written, created_n)] == expected_counts
    assert mem[stat+16] == 4  # FILETYPE_REGULAR_FILE
    assert f09_uint(mem, stat+32, 64) == len(expected_existing)
    assert f09_uint(mem, empty_stat+32, 64) == 0
    assert (root / 'truncate').read_bytes() == b''
    assert (root / 'existing').read_bytes() == expected_existing
    assert (root / 'created').read_bytes() == expected_created


def test_directory_links_rename_removal_and_timestamps(f09_driver, tmp_path):
    # F09.T03: host hard-link identity and guest contents independently checked.
    root = tmp_path / 'grant'
    root.mkdir()
    (root / 'source').write_bytes(b'link content\x00end')
    (root / 'remove-me').write_bytes(b'delete')
    (root / 'empty').mkdir()
    # A same-filesystem control captures the filesystem's actual time resolution.
    control = tmp_path / 'time-control'
    control.write_bytes(b'time')
    requested = (1_610_000_123_123_456_789, 1_620_000_456_987_654_321)
    os.utime(control, ns=requested)
    expected_times = (control.stat().st_atime_ns, control.stat().st_mtime_ns)
    guest = F09Guest()
    guest.grant()
    made = guest.path('made')
    guest.call('mkdir', 'path_create_directory', 'local.get $root', *made)
    source, renamed = guest.path('source'), guest.path('made/renamed')
    guest.call('rename', 'path_rename', 'local.get $root', *source, 'local.get $root', *renamed)
    hard = guest.path('hard')
    guest.call('link', 'path_link', 'local.get $root', 0, *renamed, 'local.get $root', *hard)
    target, sym = guest.path('made/renamed'), guest.path('symbolic')
    guest.call('symlink', 'path_symlink', *target, 'local.get $root', *sym)
    readlink = guest.alloc(256)
    readlink_n = guest.alloc(4)
    guest.call('readlink', 'path_readlink', 'local.get $root', *sym, readlink, 256, readlink_n)
    guest.call('path-times', 'path_filestat_set_times', 'local.get $root', 1, *renamed, *requested, 1 | 4)
    path_stat = guest.alloc(64)
    guest.call('path-stat', 'path_filestat_get', 'local.get $root', 1, *renamed, path_stat)
    guest.open('open-link', 'symbolic')
    contents, contents_n = guest.io('read-link', 'fd_read', 32)
    # Set via the fd after reading, which may have changed access time.
    fd_times = (requested[0] + 30_000_000_000, requested[1] + 60_000_000_000)
    os.utime(control, ns=fd_times)
    expected_fd_times = (control.stat().st_atime_ns, control.stat().st_mtime_ns)
    guest.call('fd-times', 'fd_filestat_set_times', 'local.get $file', *fd_times, 1 | 4)
    fd_stat = guest.alloc(64)
    guest.call('fd-stat', 'fd_filestat_get', 'local.get $file', fd_stat)
    final_times = (fd_times[0]+10_000_000_000,fd_times[1])
    os.utime(control, ns=final_times)
    expected_final_times = (control.stat().st_atime_ns,control.stat().st_mtime_ns)
    guest.call('atime-only', 'fd_filestat_set_times', 'local.get $file', final_times[0], 0, 1)
    final_stat = guest.alloc(64)
    guest.call('final-stat', 'fd_filestat_get', 'local.get $file', final_stat)
    guest.call('close', 'fd_close', 'local.get $file')
    directory, used = guest.readdir('readdir')
    guest.call('unlink', 'path_unlink_file', 'local.get $root', *guest.path('remove-me'))
    guest.call('rmdir', 'path_remove_directory', 'local.get $root', *guest.path('empty'))
    guest.call('nonempty-rmdir', 'path_remove_directory', 'local.get $root', *made, required=False)
    mem = f09_memory(f09_driver.filesystem(guest, [(root, '/sandbox')]))
    f09_statuses(guest, mem, {'nonempty-rmdir':55})
    assert f09_uint(mem, readlink_n) == len(b'made/renamed')
    assert mem[readlink:readlink+f09_uint(mem, readlink_n)] == b'made/renamed'
    assert f09_uint(mem, contents_n) == len(b'link content\x00end')
    assert mem[contents:contents+f09_uint(mem, contents_n)] == b'link content\x00end'
    entries = f09_dirents(mem, directory, f09_uint(mem, used))
    # Dot entries are not required; order, inode and cookie values are free.
    assert {k: v for k, v in entries.items() if k not in (b'.', b'..')} == {
        b'made': 3, b'hard': 4, b'symbolic': 7, b'remove-me': 4, b'empty': 3}
    assert set(p.name for p in root.iterdir()) == {'made', 'hard', 'symbolic'}
    assert set(p.name for p in (root / 'made').iterdir()) == {'renamed'}
    assert os.path.samefile(root / 'hard', root / 'made/renamed')
    assert (root / 'symbolic').is_symlink()
    assert os.readlink(root / 'symbolic') == 'made/renamed'
    assert (f09_uint(mem, path_stat+40, 64), f09_uint(mem, path_stat+48, 64)) == expected_times
    assert (f09_uint(mem, fd_stat+40, 64), f09_uint(mem, fd_stat+48, 64)) == expected_fd_times
    actual = (root / 'hard').stat()
    assert (actual.st_atime_ns, actual.st_mtime_ns) == expected_final_times
    assert (f09_uint(mem, final_stat+40,64),f09_uint(mem, final_stat+48,64)) == expected_final_times
    assert f09_uint(mem, path_stat+24,64) == actual.st_nlink
    assert f09_uint(mem, fd_stat+24,64) == actual.st_nlink
    assert (root / 'hard').read_bytes() == b'link content\x00end'


def test_reduced_and_inherited_descriptor_rights(f09_driver, tmp_path):
    # F09.T04: every denied write has the same working host/file baseline.
    root = tmp_path / 'grant'
    root.mkdir()
    (root / 'child').mkdir()
    (root / 'file').write_bytes(b'abcdefgh')
    (root / 'child/data').write_bytes(b'child-data')
    guest = F09Guest()
    guest.grant()
    guest.open('open', 'file')
    _, baseline_n = guest.io('baseline-write', 'fd_pwrite', b'OK', offset=2)
    guest.call('reduce', 'fd_fdstat_set_rights', 'local.get $file', F09_READ, 0)
    fdstat = guest.alloc(24)
    guest.call('rights-view', 'fd_fdstat_get', 'local.get $file', fdstat)
    data = guest.alloc(2, b'NO')
    vec = guest.alloc(8, struct.pack('<II', data, 2))
    count = guest.alloc(4)
    guest.call('denied-write', 'fd_write', 'local.get $file', vec, 1, count, required=False)
    guest.call('cannot-restore', 'fd_fdstat_set_rights', 'local.get $file', F09_READ | F09_WRITE, 0, required=False)
    read, read_n = guest.io('retained-read', 'fd_read', 8)
    guest.call('close', 'fd_close', 'local.get $file')
    # A separately opened directory grants children only its inheritable rights.
    guest.open('open-directory', 'child', target='child', flags=2,
               rights=F09_DIR_RIGHTS, inheriting=F09_FILE_RIGHTS)
    guest.open('open-child-baseline', 'data', parent='child')
    _, child_n = guest.io('child-baseline', 'fd_pwrite', b'XY', offset=0)
    guest.call('close-child-baseline', 'fd_close', 'local.get $file')
    guest.call('reduce-inheriting', 'fd_fdstat_set_rights', 'local.get $child', F09_DIR_RIGHTS, F09_READ)
    guest.open('open-child-reduced', 'data', parent='child', rights=F09_READ | F09_WRITE)
    childstat = guest.alloc(24)
    guest.call('child-rights', 'fd_fdstat_get', 'local.get $file', childstat)
    guest.call('child-denied-write', 'fd_write', 'local.get $file', vec, 1, count, required=False)
    child_read, child_read_n = guest.io('child-retained-read', 'fd_read', 32)
    guest.call('close-child', 'fd_close', 'local.get $file')
    # Removing PATH_OPEN must also affect subsequent opens on the directory.
    guest.call('reduce-path', 'fd_fdstat_set_rights', 'local.get $child', 0, F09_READ)
    guest.open('denied-open', 'data', parent='child', rights=F09_READ, required=False)
    mem = f09_memory(f09_driver.filesystem(guest, [(root, '/sandbox')]))
    f09_statuses(guest, mem, {name: 76 for name in (
        'denied-write', 'cannot-restore', 'child-denied-write', 'denied-open')})
    assert f09_uint(mem, baseline_n) == 2 and f09_uint(mem, child_n) == 2
    assert f09_uint(mem, fdstat+8, 64) == F09_READ
    assert f09_uint(mem, childstat+8, 64) & F09_WRITE == 0
    assert f09_uint(mem, read_n) == 8 and mem[read:read+8] == b'abOKefgh'
    assert f09_uint(mem, child_read_n) == 10 and mem[child_read:child_read+10] == b'XYild-data'
    assert (root / 'file').read_bytes() == b'abOKefgh'
    assert (root / 'child/data').read_bytes() == b'XYild-data'


def test_setup_and_distinguishable_filesystem_failures(f09_driver, tmp_path):
    # F09.T05: setup refusal is an unavailable instance, not an adapter failure.
    root = tmp_path / 'grant'
    root.mkdir()
    (root / 'file').write_bytes(b'preserved')
    guest = F09Guest()
    guest.grant()
    guest.open('baseline', 'file', rights=F09_READ)
    buf, used = guest.io('baseline-read', 'fd_read', 32)
    guest.call('close', 'fd_close', 'local.get $file')
    cases = [('missing', b'absent', 0, 44), ('exclusive', b'file', 1 | 4, 20),
             ('not-directory', b'file/child', 0, 54), ('empty', b'', 0, None),
             ('nul', b'file\0suffix', 0, None)]
    for label, path, flags, _ in cases:
        guest.open(label, path, flags=flags, required=False)
    mem = f09_memory(f09_driver.filesystem(guest, [(root, '/sandbox')]))
    expected = {}
    for label, _, _, code in cases:
        actual = f09_uint(mem, guest.statuses[label])
        if code is None:
            assert actual > 0, (label, actual)
            expected[label] = actual
        else:
            expected[label] = code
    f09_statuses(guest, mem, expected)
    assert f09_uint(mem, used) == 9 and mem[buf:buf+9] == b'preserved'
    assert set(p.name for p in root.iterdir()) == {'file'}
    assert (root / 'file').read_bytes() == b'preserved'
    for invalid in (tmp_path / 'missing-grant', root / 'file'):
        observed = f09_driver.filesystem(guest, [(invalid, '/sandbox')])
        assert observed['instantiated'] is False, observed


def test_path_confinement_and_legal_parent_traversal(f09_driver, tmp_path):
    # F09.T06: no symlink directory components; only promised lexical scope.
    root = tmp_path / 'grant'
    root.mkdir()
    (root / 'sub').mkdir()
    (root / 'inside').write_bytes(b'allowed\x00bytes')
    outside = tmp_path / 'outside'
    outside.write_bytes(b'outside-unchanged')
    guest = F09Guest()
    guest.grant()
    guest.open('legal-parent', 'sub/../inside', rights=F09_READ)
    buf, used = guest.io('legal-read', 'fd_read', 32)
    guest.call('close', 'fd_close', 'local.get $file')
    # Truncation makes an accidental success observable in host storage too.
    rejected = [('absolute', str(outside)), ('parent', '../outside'),
                ('nested-parent', 'sub/../../outside')]
    for label, path in rejected:
        guest.open(label, path, flags=8, required=False)
    bad_targets = [('symlink-parent', '../outside', 'bad-parent'),
                   ('symlink-absolute', str(outside), 'bad-absolute'),
                   ('symlink-nested', '../../outside', 'sub/bad')]
    for label, target, link in bad_targets:
        guest.call(label, 'path_symlink', *guest.path(target), 'local.get $root', *guest.path(link), required=False)
    guest.call('legal-symlink', 'path_symlink', *guest.path('../inside'),
               'local.get $root', *guest.path('sub/good'))
    guest.open('legal-symlink-open', 'sub/good', rights=F09_READ)
    linked, linked_n = guest.io('legal-symlink-read', 'fd_read', 32)
    guest.call('close-link', 'fd_close', 'local.get $file')
    mem = f09_memory(f09_driver.filesystem(guest, [(root, '/sandbox')]))
    f09_statuses(guest, mem, {label: 76 for label, *_ in rejected + bad_targets})
    for ptr, count in [(buf, used), (linked, linked_n)]:
        assert f09_uint(mem, count) == len(b'allowed\x00bytes')
        assert mem[ptr:ptr+f09_uint(mem, count)] == b'allowed\x00bytes'
    assert outside.read_bytes() == b'outside-unchanged'
    assert (root / 'inside').read_bytes() == b'allowed\x00bytes'
    assert set(p.name for p in root.iterdir()) == {'inside', 'sub'}
    assert set(p.name for p in (root / 'sub').iterdir()) == {'good'}
    assert (root / 'sub/good').is_symlink()
    assert os.readlink(root / 'sub/good') == '../inside'
