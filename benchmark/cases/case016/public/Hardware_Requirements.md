# Hardware Requirements

This document lists the hardware and toolchain the product must run under.

## Summary

This is a CPU-only, standard-library prose-pattern detector with companion JavaScript hooks. It has no compiled extensions, native code, GPU or accelerator requirement, and no runtime third-party dependencies. The documented interpreter floor is Python 3.9 or newer; the saved-file hooks require Node.js. Any standard x86_64 or arm64 Linux, macOS, or Windows host with those interpreters is sufficient to run the detector from this repository's source tree and to run the hooks.

## Execution profiles

### CPU baseline (**mandatory**)

Standard CPU-only execution path: the detector script runs from this repository's source tree, scores prose given on standard input or as a file, and prints its JSON report.

- **Profile id:** `cpu_baseline`
- **Platforms:** linux, darwin, windows
- **Required on:** linux
- **Setup:** Python 3.9 or newer and Node.js. Zero runtime third-party dependencies. No extra system libraries are required beyond those interpreters.
- **Build:** No native compile step and no installable package. The detector is a Python script invoked from the source tree; the hooks are JavaScript files run with Node. Putting the repository root as the working directory is enough.
