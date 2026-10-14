# Hardware Requirements

This document lists the hardware and toolchain the product must run under.

## Summary

This is a CPU-only portable C11 library for 3D inertial-navigation state estimation that fuses IMU specific-force and angular-rate samples with GNSS and other aiding sensors. It has no GPU or accelerator requirement and no runtime third-party dependencies beyond libm. A standard Linux x86_64 host with a C11 compiler and GNU make is sufficient to compile the library from this repository and run its navigation filters. Optional language bindings and dataset-replay helpers need CPython 3.8 or newer plus PyYAML and NumPy.

## Execution profiles

### CPU baseline (**mandatory**)

The library compiles from this repository and its filters run on the host CPU.

- **Profile id:** `cpu_baseline`
- **Platforms:** linux, darwin, windows
- **Required on:** linux
- **Setup:** C11 compiler and GNU make; link against libm. The core library has no other runtime third-party dependencies. Optional CPython 3.8 or newer, PyYAML, and NumPy for the language binding and dataset-replay helpers.
- **Build:** From the repository root, GNU make builds the shared library used by the language binding and the C replay program (targets named in the Interface Contract). There is no CMake (or other) extra build-system dependency.
