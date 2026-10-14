# Hardware Requirements

This document describes the hardware and toolchain the product needs to build and run.

## Summary

This is a CPU-only Go command-line Git extension. No GPU or specialized
accelerator is required. A standard Linux x86_64 machine with a Go
toolchain meeting the module minimum (Go 1.25 or newer), GNU make, and
Git is sufficient to compile the client from source and run its CLI
entry points.

## Execution profiles

### CPU baseline (**mandatory**)

The client is built from this repository's Go module and runs as the
locally built binary.

- **Profile id:** `cpu_baseline`
- **Platforms:** linux
- **Required on:** linux
- **Setup:** Go 1.25 or newer, GNU make, and Git. Module dependencies are
  fetched via the Go module proxy.
- **Build:** Compile the module-root main package into a CLI binary
  (`go build` at the repository root, or the equivalent `make` target that
  produces the same binary).
- **Run:** The built binary runs its subcommands, for example its version
  subcommand, which reports the client's version and exits successfully.
