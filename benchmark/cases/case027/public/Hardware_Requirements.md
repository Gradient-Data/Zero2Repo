# Hardware Requirements

This document lists the hardware and toolchain a submitted solution must run
under. The product must really use the capabilities below; a fallback that skips
a mandatory profile is not a substitute.

## Summary

A CPU-only Rust workspace made of an index library crate and a command-line
binary. Together they implement a trigram-indexed regular-expression search
tool with an on-disk index, a local client/server mode over loopback TCP, and
filesystem watching. No GPU or other accelerator is used. The machine needs a
current stable Rust toolchain that supports the 2024 edition. The project
documents 1.85 or newer, but the code uses let-chains, so a recent stable
release such as 1.88 or newer is needed. It also needs a C toolchain for
linking, `git` on `PATH` (the product works with Git repositories and their
ignore rules), a writable temporary directory, loopback networking on
`127.0.0.1`, and native filesystem change notifications (inotify on Linux).
The product starts background server processes and can memory-map files of
several MiB. Any modern x86_64 or aarch64 machine with about 4 GB of RAM and
a few GB of free disk for build output is enough.

## Execution profiles

### CPU baseline (**mandatory**)

The product is built from source with the language's standard build tool and
runs entirely on the CPU. It builds an on-disk trigram index for a directory
tree, then answers a regex search from that index and returns only the files
that actually match.

- **Profile id:** `cpu_baseline`
- **Platforms:** linux, darwin, windows
- **Required on:** linux
- **Use** (the real operation the product performs with this capability):
  - Compile the workspace from source to produce the search binary.
  - Use that binary to index a small directory holding one source file that
    contains a unique identifier and one unrelated text file. The index is
    written to the default hidden index directory under that root.
  - Run an indexed files-with-matches search for the identifier. Only the
    source file that contains it is listed; the unrelated file is not.
- **Setup:** Install a stable Rust toolchain through the standard toolchain
  installer: 2024 edition support, 1.85 or newer, and in practice a recent
  stable release. Add the formatter and linter components. Provide a system C
  compiler/linker and `git` on `PATH`. Allow loopback TCP connections on
  `127.0.0.1` and native filesystem notifications.
- **Build:** Build the whole workspace with the standard build tool, in debug
  or release profile. The search binary appears in that profile's output
  directory. The benchmark harnesses in the workspace must also compile.
