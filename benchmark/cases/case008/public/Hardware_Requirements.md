# Hardware Requirements

This document lists the hardware and toolchain the product must run under.
The mandatory profile below is the environment the library is built and used
in; it cannot be replaced by a fallback.

## Summary

This is a CPU-only C++20 library for WHATWG-compliant URL parsing, normalization, and component access. It has no GPU or accelerator requirement and no runtime third-party dependencies. A standard Linux x86_64 host with a C++20 compiler (GCC 12 or newer, LLVM 14 or newer, or MSVC 2022 or newer) and CMake 3.16 or newer is sufficient to compile the library from this repository's sources and link programs against it.

## Execution profiles

### CPU baseline (**mandatory**)

Build the URL-parser library from this repository's CMake sources and link C++ and C programs against the locally built artifact.

- **Profile id:** `cpu_baseline`
- **Platforms:** linux, darwin, windows
- **Required on:** linux
- **Use:** configure and compile this repository's library target from source with CMake in Release mode; programs include the public headers and link the just-built library.
- **Setup:** C++20 compiler at the documented floors (GCC 12 or newer, LLVM 14 or newer, or MSVC 2022 or newer) and CMake 3.16 or newer. The library is self-contained at runtime. Optional Ninja generator.
- **Build:** Configure from the repository root with CMake and build the library target. When the build type is left unset, the project defaults to Release.
