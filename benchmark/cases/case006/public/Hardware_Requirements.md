# Hardware Requirements

This document lists the hardware and toolchain the product must run under.

## Summary

This is a pure-Python command-line interface toolkit with no compiled extensions, native code, or GPU/accelerator requirements. It has zero declared runtime dependencies and requires Python 3.10 or newer. Any standard x86_64 or arm64 Linux, macOS, or Windows host with a supported Python interpreter is sufficient to install it from source and use it.

## Execution profiles

### CPU baseline (**mandatory**)

Standard CPU-only Python execution path.

- **Profile id:** `cpu_baseline`
- **Platforms:** linux, darwin, windows
- **Required on:** linux
- **Setup:** Python 3.10 or newer. No extra system libraries are required beyond a normal interpreter; pager helpers may use the system pager if present.
- **Build:** No native compile step. The package is src-layout, built with a PEP 517 backend. An editable install from the project root, or putting the source directory on the import path, is enough to import it from the source tree.
