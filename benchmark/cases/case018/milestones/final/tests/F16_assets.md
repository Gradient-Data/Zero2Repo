# feature: F16

F16 corpus provenance

These are real upstream inputs referenced by the original repository public decompiler tests. They are shipped with the suite so test execution never downloads inputs or signatures.

The Go examples cover strings, slices, error interfaces, multiple results and a receiver. The Rust fmt function covers references, aggregate literals, Option/Result alternatives and formatting. Compiler metadata for the Rust artifact identifies rustc 1.88.0. The selected function address comes from the original public test for this exact artifact.

| Asset | Upstream URL | SHA-256 |
| --- | --- | --- |
| F16_go_basics.elf | https://raw.githubusercontent.com/angr/binaries/master/tests/x86_64/go/go1.22.5/basics | b0c5144b05517c764da886a30b5eeca5709b6b655e93b55ae4967042943db50f |
| F16_go_recv.elf | https://raw.githubusercontent.com/angr/binaries/master/tests/i386/go/go1.27.1/recv | 458a0366f746f867464e185c76d874a69371bea43c067eacc7957c7772e67412 |
| F16_rust_fmt.elf | https://raw.githubusercontent.com/angr/binaries/master/tests/x86_64/rust/coreutils/nightly-2025-05-22-O3/fmt | 236a96c8188b5ac75e93615118526b14b91a4aef0aca12d18f9c2a4ef91fce8a |
| F16_rust_O0.sig | https://raw.githubusercontent.com/angr/flirt_signatures/master/x86_64/linux/rust/inline/1.88.0-O0.sig | dcd7244a5f3332709c9767c1d853856cd8ace49161e863f8c5cc637e009cf215 |
| F16_rust_O1.sig | https://raw.githubusercontent.com/angr/flirt_signatures/master/x86_64/linux/rust/inline/1.88.0-O1.sig | 9ef529582f66f2da3f6df90e3bc482ac734aeaa9894dea4e34301b56f0e1b8ef |
| F16_rust_O2.sig | https://raw.githubusercontent.com/angr/flirt_signatures/master/x86_64/linux/rust/inline/1.88.0-O2.sig | b2f9e45f624d425952b07565a858fb924235bc59cd9ef8c4761946d1317aeeb9 |
| F16_rust_O3.sig | https://raw.githubusercontent.com/angr/flirt_signatures/master/x86_64/linux/rust/inline/1.88.0-O3.sig | 76bff800bf6d3f038a839f2ddf8c4a4b089011e06c94f3fec74aaa30251366c8 |
