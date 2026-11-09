The dependency inventory contains every registry package from the workspace's
Cargo.lock, including development and platform-specific dependencies. Local
workspace members are excluded. Each entry preserves its exact version and
SHA-256 archive checksum; no project manifest or product source is included.

During environment installation, prepare-cargo.py downloads these archives from
crates.io (static.crates.io), verifies each locked checksum, and creates a
Cargo directory source with per-file checksums under /usr/local/cargo/vendor.
Cargo's source replacement is installed in /usr/local/cargo/config.toml.

The build command sets CARGO_HOME=/usr/local/cargo and uses --locked --offline,
so compilation resolves dependencies from that directory without registry
access, a host cache, or the portable inputs remaining mounted. Toolchain
versions are unchanged. All recipe downloads use the official upstream sources.
