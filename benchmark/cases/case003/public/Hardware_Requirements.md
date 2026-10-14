# Hardware Requirements

This document lists the hardware and toolchain the product must run under.
The product provides the capabilities below itself on every mandatory profile;
a fallback that skips a mandatory profile is not a substitute.

## Summary

This is a CPU-only TypeScript/JavaScript library that parses and serializes YAML 1.2 (with optional YAML 1.1 types). It has no compiled native extensions, no GPU or accelerator requirement, and one declared runtime dependency used only by the command-line entry. A standard Linux, macOS, or Windows host with a current Node.js LTS interpreter and npm is sufficient to install from this repository, run the documented bundle step, and load the locally built artifact.

## Execution profiles

### CPU baseline (**mandatory**)

Standard CPU-only Node.js execution path: the YAML parser/serializer built from this repository's TypeScript sources and loaded as the locally produced ESM artifact.

- **Profile id:** `cpu_baseline`
- **Platforms:** linux, darwin, windows
- **Required on:** linux
- **Capability on this profile:** the library is imported from the locally built ESM artifact in the distribution directory (not a separately published registry package), parses YAML text, and serializes JavaScript values.
- **Setup:** A current Node.js LTS interpreter and npm. The only declared runtime dependency is a command-line argument parser used by the CLI entry, not by the library load/dump path. No extra system libraries beyond a normal JavaScript toolchain; no GPU or accelerator.
- **Build:** TypeScript sources are bundled into ESM, CommonJS, and browser artifacts plus type declarations under the distribution directory. There is no native compile step.
