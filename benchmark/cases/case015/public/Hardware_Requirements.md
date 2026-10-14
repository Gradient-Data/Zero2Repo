# Hardware Requirements

This document lists the hardware and toolchain the product must build and run under.

## Summary

This is a CPU-only C99 command-line tool that losslessly recompresses Ogg Vorbis and Ogg Opus bitstreams. It has no GPU or accelerator requirement and no runtime third-party libraries beyond the C and math libraries. A standard Linux x86_64 host with a C99 compiler, GNU make, and Autotools (autoconf and automake) for a git checkout is sufficient to compile the tool from this repository's sources and run it.

## Execution profiles

### CPU baseline (**mandatory**)

Build the recompressor CLI from this repository's Autotools sources and run it on the host CPU.

- **Profile id:** `cpu_baseline`
- **Platforms:** linux, darwin, windows
- **Required on:** linux
- **Setup:** C99 compiler and GNU make; link against the C and math libraries only. A git checkout additionally needs autoconf and automake to generate the configure script. Optional configure flags enable sanitizers or a portable build without CPU-specific code paths.
- **Build:** From the repository root, generate the configure script if it is missing, run configure, then make. The default target produces the command-line tool.
