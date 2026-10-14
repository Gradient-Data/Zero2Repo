# Hardware Requirements

This document lists the hardware and toolchain a submitted solution must run under.

## Summary

This is a pure-Python library that evaluates declarative path expressions against nested JSON-like mappings and sequences and returns the selected values. It has no compiled extensions, native code, or GPU/accelerator requirements, and zero declared runtime dependencies. The documented interpreter floor is Python 3.9 or newer. Any standard x86_64 or arm64 Linux, macOS, or Windows host with a supported interpreter is sufficient.

## Execution profiles

### CPU baseline (**mandatory**)

Standard CPU-only Python execution path.

- **Profile id:** `cpu_baseline`
- **Platforms:** linux, darwin, windows
- **Required on:** linux
- **Requirement:** the library is imported from this repository's own source tree (not a separately published wheel) and evaluates expressions in an ordinary interpreter process.
- **Setup:** Python 3.9 or newer. Zero runtime third-party dependencies. No extra system libraries are required beyond a normal interpreter.
- **Build:** No native compile step. The importable package uses a flat layout at the project root and is packaged with setuptools. An editable install from the project root, or putting the project root on the import path, is enough to import from this tree.
