# Hardware Requirements

This document lists the hardware and toolchain the product must run under.
The mandatory profile below is the environment the plugins are installed and
used in; it cannot be replaced by a fallback.

## Summary

This is a CPU-only TypeScript lint-plugin library that registers custom static-analysis rules with a JavaScript linter and reports diagnostics on TypeScript and JavaScript source. It has no compiled native extensions, no GPU or accelerator requirement, and is consumed as TypeScript source rather than a separately bundled binary. A standard Linux, macOS, or Windows host with Node.js 24 and pnpm 10.33.0 is sufficient to install from this repository and lint source with its rules.

## Execution profiles

### CPU baseline (**mandatory**)

Load the lint rules from this repository's TypeScript sources into the host linter and lint TypeScript and JavaScript source with them.

- **Profile id:** `cpu_baseline`
- **Platforms:** linux, darwin, windows
- **Required on:** linux
- **Use:** the rules load from this repository's TypeScript sources (not from a separately published registry package) into the host linter.
- **Setup:** Node.js 24 and pnpm 10.33.0, the package manager the repository declares in its `packageManager` field, installing from the committed lockfile. No extra system libraries beyond a normal JavaScript toolchain; no GPU or accelerator.
- **Build:** No native compile step. The package exports TypeScript source directly.
