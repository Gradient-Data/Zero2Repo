# Hardware Requirements

- **Processor:** CPU only. No GPU or other accelerator is required or used.
- **Byte order:** little-endian hosts only. Big-endian targets are not supported.
- **Platforms:** Linux on x86-64 or ARM64.
- **Toolchain:** Zig 0.16 (minimum Zig version 0.16.0). No other runtime dependency.
- **Build:** the library is a Zig module named `klyvmap` with root source `src/klyvmap.zig`. A program builds against it by attaching that module at compile time (for example `zig build-exe --dep klyvmap -Mroot=<program>.zig -Mklyvmap=<repository root>/src/klyvmap.zig`). `zig build` at the repository root builds the package.
