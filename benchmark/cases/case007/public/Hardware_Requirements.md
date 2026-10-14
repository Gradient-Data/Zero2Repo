# Hardware Requirements

This document lists the hardware and toolchain the product must run under.

## Summary

This is a pure-Python library that generates, accepts and rejects HMAC-based and time-based one-time passwords. It has no compiled extensions, native code, or GPU/accelerator requirements, and zero declared runtime dependencies. The interpreter floor is Python 3.8 or newer. Any standard x86_64 or arm64 Linux, macOS, or Windows host with a supported interpreter is sufficient to install the library from source and use it.

## Execution profiles

### CPU baseline (**mandatory**)

Standard CPU-only Python execution path: the library is imported from this repository and used to emit and accept one-time passwords.

- **Profile id:** `cpu_baseline`
- **Platforms:** linux, darwin, windows
- **Required on:** linux
- **Runs as:** the package imports from this repository's `src` layout (not from a separately published wheel), and its helpers emit and accept codes in a normal CPU-only interpreter.
- **Setup:** Python 3.8 or newer. Zero runtime third-party dependencies. No extra system libraries are required beyond a normal interpreter.
- **Build:** No native compile step. The package uses the src layout; an editable install from the project root, or putting the source directory on the import path, is enough to import from this tree.
