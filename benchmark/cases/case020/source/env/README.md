# Reproducible runtime installation

The manifest and recipe lock select `python3 /env-assets/install.py`. That
entry point first calls `native.install_native()`, then installs the existing
locked Python runtime and native CMake distribution. Native packages install
under `/usr`, so the existing judge PATH exposes them to non-root users.

`native-packages.json` locks Ubuntu 24.04 amd64 Autoconf, Automake, Libtool and
Clang 18 distributions, including their non-recommended package dependencies.
Each downloaded Debian archive has an exact version, URL and SHA256 from the
Ubuntu package indexes. The selected mirror is also used by the existing
Python dependency inputs. The libxml2 version comes from the noble-updates
main index; the other package versions come from the original image's Ubuntu
indexes. Installation never resolves versions from a live package index.

The `base_packages` map records the versions of transitive prerequisites
already supplied by the registered base environment, including Perl, GCC,
GNU binutils, libc development files and the C++ standard library. Installation
checks those versions before downloading. A base change requires reviewing and
regenerating this lock; a mismatch is an error. Missing packages, unavailable
archives, checksum mismatches and dpkg configuration errors remain fatal.

The installer downloads all archives, verifies SHA256, and invokes dpkg on the
complete set. It installs package support files and runs package configuration
rather than copying standalone binaries. This preserves Autotools macros,
Libtool support files, Clang resource headers, shared libraries and executable
links. dpkg has no network dependency resolution step, so an incomplete locked
closure fails instead of silently installing unlocked dependencies.
