# Environment inputs

`install.py` preserves the existing checksum-locked wheels for the default
CPython 3.13 runtime, then invokes `install_native.py`.

`native.lock.json` declares native dependency versions, explicit download URLs
and SHA-256 digests. Only UTF-8 declarations and installation scripts are shipped;
no archives or package payloads are stored in these assets. During the networked
installation phase, `install_native.py` downloads each locked Ubuntu Noble package
and the upstream CPython 3.11.14 source into `/opt/native-downloads`, verifies every
digest before installing anything, then installs the packages and builds CPython.
It does not use apt dependency resolution or read project source. All acquisition
and installation finishes before the offline product build and judge execution.
The compiler, make, binutils and libc development files come from the existing
`codingbench-base/ubuntu:24.04` base image.

CPython is built at `/opt/src/Python-3.11.14` with `-Og -g3` and installed at
`/opt/cpython311`. Its executable is not stripped; its DWARF information and
retained source describe the exact executable used by `python3.11`, rather than
a separate debug interpreter. Matching headers, static library and
`python3.11-config` are installed alongside it. Versioned executable links in
`/usr/local/bin` leave the default interpreter unchanged. The existing locked
setuptools wheel is also installed for 3.11 without dependency resolution.
Standard-library SSL, compression, SQLite, ctypes and readline support have
explicit native build inputs. CPython's matching GDB helper is installed beside
the executable with a narrowly scoped system auto-load safe path.

Installation errors and checksum mismatches propagate. The judge needs no
network or package installation to compile 3.11 extensions or debug its own
children with GDB. Container policy must permit tracing a debugger's own child;
provisioning does not alter host ptrace policy or request privileged containers.
