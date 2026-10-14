# Hardware Requirements

This document lists the hardware and toolchain the product must run under.

## Summary

This is a pure-Python natural-language processing library with no compiled extensions, native code, or GPU/accelerator requirements. The documented interpreter floor is Python 3.10 or newer. Any standard x86_64 or arm64 Linux, macOS, or Windows host with a supported interpreter is sufficient to install from source and run the baseline tokenizer path. Optional extra groups add scientific-computing libraries for some classifiers and plot helpers; they are not required for the mandatory CPU profile.

## Execution profiles

### CPU baseline (**mandatory**)

Standard CPU-only Python execution path. Core capability is loading the library from this repository's source tree and running one real word/punctuation tokenization with no downloaded corpus or model.

- **Profile id:** `cpu_baseline`
- **Platforms:** linux, darwin, windows
- **Required on:** linux
- **Capability:** the library loads from this repository's source tree (not a separately published wheel) and its word/punctuation tokenizer runs with no downloaded corpus or model.
- **Setup:** Python 3.10 or newer. Runtime dependencies are a small set of pure-Python packages. Corpus downloads are not required for this profile. No extra system libraries beyond a normal interpreter.
- **Build:** No native compile step. The package is a flat layout built with the standard Python packaging backend. An editable install from the project root, or putting the project root on the import path, is enough to import from this tree.
