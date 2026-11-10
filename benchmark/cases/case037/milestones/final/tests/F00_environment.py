# feature: F00
"""Unprivileged filesystem views backed by real files and upstream PRoot.

Only pathname lookup is isolated. libc, DNS/hosts parsing, OpenSSH, sockets,
cryptography and the product execute unchanged. No resolver result or signature
is intercepted. Missing tools, denied ptrace and child failures are fatal.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tarfile

from _helpers import environment, run_command


@contextmanager
def filesystem_view(directory, bindings):
    root = directory / 'file-view-tools'
    root.mkdir()
    with tarfile.open(Path(__file__).with_name('F00_proot.tar.gz')) as archive:
        archive.extractall(root, filter='data')
    argv = [str(root / 'usr/bin/proot')]
    for source, target in bindings:
        argv += ['-b', str(source) + ':' + target]
    library = str(root / 'usr/lib/x86_64-linux-gnu')
    inherited = os.environ.get('LD_LIBRARY_PATH')
    env = environment({'LD_LIBRARY_PATH': library + (':' + inherited if inherited else ''),
                       'PROOT_NO_SECCOMP': '1'})
    yield argv, env


def in_hosts_view(test, directory, hosts):
    """Run a test under libc's real hosts-file resolver, once per child."""
    if os.environ.get('F00_HOSTS_VIEW') == test.__name__:
        return None
    path = directory / 'hosts'
    path.write_text(hosts)
    with filesystem_view(directory, [(path, '/etc/hosts')]) as (argv, env):
        env['F00_HOSTS_VIEW'] = test.__name__
        result = run_command([*argv, sys.executable, test.__code__.co_filename,
                              test.__name__, str(directory)], env=env, timeout=180)
    return result
