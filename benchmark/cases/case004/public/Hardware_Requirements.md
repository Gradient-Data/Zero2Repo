# Hardware Requirements

This document lists the hardware and toolchain the product must run under. A
mandatory profile is required; a fallback that skips it is not a substitute.

## Summary

This is a pure-Python library that cryptographically signs serialized payloads so they can be sent to untrusted environments and trusted again on return. It has no compiled extensions, native code, or GPU/accelerator requirements, and zero declared runtime dependencies. The documented interpreter floor is Python 3.10 or newer. Any standard x86_64 or arm64 Linux, macOS, or Windows host with a supported interpreter is sufficient to install and use it from source.

## Execution profiles

### CPU baseline (**mandatory**)

Standard CPU-only Python execution path. The core capability is signing a small mapping into a compact token and loading the token back to the original mapping.

- **Profile id:** `cpu_baseline`
- **Platforms:** linux, darwin, windows
- **Required on:** linux
- **Runs from source:** the library is importable from this repository's source tree (src layout) on a plain CPU interpreter.
- **Setup:** Python 3.10 or newer. No extra system libraries are required beyond a normal interpreter.
- **Build:** No native compile step. The package is src-layout, built with a PEP 517 backend. An editable install from the project root, or putting the source directory on the import path, is enough to import from this tree.
