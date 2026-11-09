#!/usr/bin/env bash
set -euo pipefail
umask 022

# Install the exact compiler version exercised by the MSRV CI job.
export DEBIAN_FRONTEND=noninteractive
# Ubuntu packages come from Canonical's official archive snapshot 20261107T063739Z
# (the time this environment was recorded), so apt resolves the same versions
# on any host.
SNAPSHOT=20261107T063739Z
apt-get --snapshot "$SNAPSHOT" -o Acquire::Retries=3 -o Acquire::http::Timeout=60 update
apt-get --snapshot "$SNAPSHOT" -o Acquire::Retries=3 -o Acquire::http::Timeout=60 install -y --no-install-recommends ca-certificates xz-utils autoconf automake libtool pkg-config libc6 libgcc-s1 libstdc++6

python3 /env-assets/install.py

test -x /usr/bin/node
test "$(/usr/bin/node --version)" = "v22.14.0"

# Operator 2026-11-05 (user decision): no SQLite implementation may be reachable from a
# solve. Remove the system library (system Python, which only it needs, goes with it;
# tests and the harness use /opt/conda), conda's sqlite package, and the SQLite C sources
# bundled inside vendored crates (the crates stay so the locked workspace still resolves).
apt-get purge -y libsqlite3-0
if [ -x /opt/conda/bin/conda ]; then /opt/conda/bin/conda remove --force -y sqlite; fi
for bundled in /opt/cargo-vendor/libsqlite3-sys-*/sqlite3 /opt/cargo-vendor/libsqlite3-sys-*/sqlcipher /opt/cargo-vendor/sqlite-wasm-rs-*/sqlite3 /opt/cargo-vendor/sqlite-wasm-rs-*/sqlite3mc; do
  case "$bundled" in /opt/cargo-vendor/*/sqlite3|/opt/cargo-vendor/*/sqlcipher|/opt/cargo-vendor/*/sqlite3mc) rm -r -- "$bundled" ;; esac
done
test -z "$(find / -xdev \( -name 'libsqlite3.so*' -o -name 'sqlite3.c' -o -name 'sqlite3mc_amalgamation.c' \) -print -quit 2>/dev/null)"
