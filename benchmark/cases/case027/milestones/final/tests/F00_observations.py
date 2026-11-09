# feature: F00
"""Independent operating-system observations of file access, not product internals."""
import ctypes
import os
import struct


class ReadEvents:
    """Observe reads of fixture files through Linux inotify; never infer them from product reports."""
    def __init__(self, paths):
        self.paths = list(paths)

    def __enter__(self):
        libc = ctypes.CDLL(None, use_errno=True)
        self.fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        assert self.fd >= 0, os.strerror(ctypes.get_errno())
        self.watches = {}
        for path in self.paths:
            wd = libc.inotify_add_watch(self.fd, os.fsencode(path), 0x1)  # IN_ACCESS
            assert wd >= 0, os.strerror(ctypes.get_errno())
            self.watches[wd] = path
        return self

    def accessed(self):
        found = set()
        while True:
            try:
                data = os.read(self.fd, 65536)
            except BlockingIOError:
                break
            pos = 0
            while pos < len(data):
                wd, mask, cookie, length = struct.unpack_from('iIII', data, pos)
                assert not mask & 0x4000, 'inotify observer overflowed'
                if mask & 0x1:
                    found.add(self.watches[wd])
                pos += 16 + length
        return found

    def __exit__(self, *args):
        os.close(self.fd)


class ReadGate:
    """Hold a regular fixture file's opens with an owner-held Linux write lease.

    The server can accept requests while a background build waits for content.
    Unlike a large or slow fixture, this makes the incomplete state observable
    regardless of implementation speed. No product code or thread is inspected.
    Always release before waiting for the server to finish.
    """
    def __init__(self, path):
        self.path = path
        self.fd = None
        self.requested = False

    def __enter__(self):
        import fcntl
        import signal
        self.old_handler = signal.signal(signal.SIGIO, self._on_open)
        try:
            self.fd = os.open(self.path, os.O_RDWR)
            fcntl.fcntl(self.fd, fcntl.F_SETLEASE, fcntl.F_WRLCK)
        except BaseException:
            self.release()
            signal.signal(signal.SIGIO, self.old_handler)
            raise
        return self

    def _on_open(self, *_):
        self.requested = True

    def wait_blocked(self, process):
        from _helpers import wait_until
        wait_until(lambda: self.requested, timeout=30, process=process,
                   message=f"no content open reached the fixture gate at {self.path}")

    def release(self):
        import fcntl
        if self.fd is not None:
            fcntl.fcntl(self.fd, fcntl.F_SETLEASE, fcntl.F_UNLCK)
            os.close(self.fd)
            self.fd = None

    def __exit__(self, *_):
        import signal
        self.release()
        signal.signal(signal.SIGIO, self.old_handler)


def birthtime_ns(path):
    """Read Linux statx birth time, retaining the filesystem's actual precision."""
    libc = ctypes.CDLL(None, use_errno=True)
    buf = ctypes.create_string_buffer(256)
    result = libc.statx(-100, os.fsencode(path), 0, 0x800, buf)
    assert result == 0, os.strerror(ctypes.get_errno())
    assert struct.unpack_from("=I", buf.raw, 0)[0] & 0x800, "judge filesystem lacks birth times"
    seconds, nanos = struct.unpack_from("=qI", buf.raw, 80)
    return seconds * 1_000_000_000 + nanos
