# Hardware Requirements

This document lists the hardware and toolchain the product must run under.

## Summary

This is a pure-Python library that encodes high-level HTTP request and response events into on-the-wire bytes and parses incoming bytes back into events, without performing any network I/O of its own. It has no compiled extensions, native code, or GPU/accelerator requirements, and zero declared runtime dependencies. The documented interpreter floor is Python 3.8 or newer. Any standard x86_64 or arm64 Linux, macOS, or Windows host with a supported interpreter is sufficient to install from source and use the library.

## Execution profiles

### CPU baseline (**mandatory**)

Standard CPU-only Python execution path. The product runs entirely on the CPU.

- **Profile id:** `cpu_baseline`
- **Platforms:** linux, darwin, windows
- **Required on:** linux
- **Runs from:** this repository's source tree (not a separately published wheel), on a supported interpreter.
- **Setup:** Python 3.8 or newer. Zero runtime third-party dependencies. No extra system libraries are required beyond a normal interpreter.
- **Build:** No native compile step. The package is a flat layout at the repository root, built with setuptools. An editable install from the project root, or putting the repository root on the import path, is enough to import from this tree.
