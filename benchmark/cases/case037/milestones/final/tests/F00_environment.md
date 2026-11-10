# feature: F00

F00_proot.tar.gz contains unmodified Ubuntu amd64 package payloads for PRoot
5.1.0 and libtalloc 2.4.2, including licenses and a provenance manifest. It
contains no identities, resolver records, expected answers or product code.
The manifest records package URLs, SHA-256 hashes and extraction commands.

PRoot supplies an unprivileged filesystem view for real libc hosts-file
resolution and the real installed OpenSSH ssh-keysign. Per-call temporary files
are mapped to the normal system paths in child processes only. The host files,
judge image and product remain unchanged. It does not replace any resolver or
cryptographic function. Runtime needs no network or installation; unavailable
ptrace or dependencies fail visibly.

The hosts-view runner returns the real child process result to its caller.
The outer test checks its exit status and retains stdout/stderr on failure;
the child runs the complete capability assertions before successful exit.
