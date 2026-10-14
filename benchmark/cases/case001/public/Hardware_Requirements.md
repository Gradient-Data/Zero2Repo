# Hardware Requirements

This document lists the hardware and toolchain the product must run under.
The product provides the capabilities below itself on every mandatory profile;
a fallback that skips a mandatory profile is not a substitute.

## Summary

This is a pure-Python library that parses TOML documents into native mappings, sequences, and scalars. The default path has no compiled extensions, no runtime third-party dependencies, and no GPU or accelerator requirements. The documented interpreter floor is Python 3.8 or newer. Any standard x86_64 or arm64 Linux, macOS, or Windows host with a supported interpreter is sufficient to install and run the product from source. Optional compiled wheels exist for performance on some platforms; they are not required for the mandatory CPU profile.

## Execution profiles

### CPU baseline (**mandatory**)

Standard CPU-only Python execution path. Core capability is parsing a TOML document from this repository's source tree into native Python dict, list, and scalar values.

- **Profile id:** `cpu_baseline`
- **Platforms:** linux, darwin, windows
- **Required on:** linux
- **Capability on this profile:** the parser is imported from this repository's source tree (not a separately published wheel) and parses an in-memory TOML document into native Python values.
- **Setup:** Python 3.8 or newer. Zero runtime third-party dependencies. Optional compiled-extension wheels exist for performance on some platforms and are not required for this profile. No extra system libraries are required beyond a normal interpreter.
- **Build:** No native compile step for the default path. The package is src-layout, built with a PEP 517 backend. An editable install from the project root, or putting the source directory on the import path, is enough to import from this tree.
