# Hardware Requirements

This document lists the hardware and toolchain the product must run under.

## Summary

This is a CPU-only Go command-line tool for Git-native project-memory bundles: it parses Markdown/YAML concepts, searches them in memory, validates the bundle graph, scaffolds a project, and serves a stdio tool-server. It has no GPU or accelerator requirement and no third-party Go module dependencies. A standard Linux x86_64 host with Go 1.22 or newer, GNU make, Git, and a C compiler for the race detector is sufficient to build and run it.

## Execution profiles

### CPU baseline (**mandatory**)

- **Profile id:** `cpu_baseline`
- **Platforms:** linux, darwin, windows
- **Required on:** linux
- **Setup:** Go 1.22 or newer, GNU make, and Git. The module has no third-party Go dependencies. A C compiler is required for race-enabled builds. No GPU or extra system libraries.
- **Build:** `make build` at the repository root compiles the command-line package into `bin/membundle` (see the Interface Contract, "Build"). The same binary also provides the stdio tool-server.
