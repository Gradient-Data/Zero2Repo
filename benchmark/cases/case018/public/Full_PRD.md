# Velnora Full Product Requirements

Velnora is a binary analysis framework for inspecting programs, exploring their execution with symbolic inputs, recovering program relationships, and producing editable decompilations.

### FP-01: Symbolic expressions and constraint solving

- Callers can construct concrete and symbolic fixed-width bitvectors and Boolean values and evaluate expressions under constraints. Bitvectors support addition, subtraction, multiplication, negation, signed and unsigned division and remainder with nonzero divisors, bitwise conjunction, disjunction, exclusive-or and complement, left shifts, arithmetic and logical right shifts, left and right rotations, equality, and signed and unsigned order comparisons. Integer arithmetic wraps at the selected bit width; signed division truncates toward zero and its remainder has the dividend's sign when nonzero. Ordinary order comparisons and division use unsigned interpretation; ordinary right shifts preserve the sign bit. Boolean values support conjunction, disjunction, negation, and selecting one of two supplied values according to a Boolean condition.

- Callers can concatenate, extract, reverse bytes in, and extend bitvectors. Zero extension preserves the unsigned value, sign extension preserves the signed value, and extracting or concatenating portions preserves their supplied order. Combining incompatible bit widths in an operation requiring equal widths is refused as a type mismatch.

- Adding Boolean constraints restricts subsequent solutions to assignments satisfying every constraint. Satisfiability queries distinguish satisfiable from contradictory constraints, and requesting a solution from contradictory constraints fails as unsatisfiable.

- Callers can request one solution, distinct solutions up to a positive requested count, a unique solution, a minimum solution, or a maximum solution. Up-to-count requests return fewer results when the solution set is smaller. A unique-solution request fails when more than one result is possible; a minimum-count request returns the requested number of distinct results or fails when fewer exist; an exact-count request fails when fewer or more exist. Bitvector minima and maxima use unsigned order by default and accept explicit signed order. Joint evaluation of multiple expressions returns assignments that satisfy their constraints together.

- Constraints supplied only for an individual query affect that query without becoming permanent constraints. Copying a constraint context lets callers restrict the copy without restricting the original.

- Callers can construct concrete and symbolic strings and constrain equality, concatenation, length, substring extraction, containment, prefixes, and suffixes. Lengths and substring positions count characters rather than encoded bytes; substring positions start at zero. A substring takes a supplied starting position and length, stops at the end of the source, and is empty when its starting position is at or beyond the end or its requested length is zero.

- Callers can construct concrete and symbolic binary32 and binary64 floating-point values, perform addition, subtraction, multiplication, and division, and solve comparisons involving them. For finite operands and finite nonzero results under round-to-nearest with ties to even, results follow IEEE 754-2008 for the supplied operand values, selected binary format, and caller-specified order of operations.

- For finite binary32 and binary64 values, reinterpretation between floating-point values and equal-width bitvectors preserves the represented bits; numeric conversion instead preserves the numerical value subject to the selected destination format and round-to-nearest with ties to even under IEEE 754-2008. Callers supply the source value, source format, destination width or format, and integer signedness for numeric conversions whose result is representable.

### FP-02: Binary image loading and patching

- Callers can load ELF, PE, Mach-O, CGC, ELF core dumps, and raw binary images for analysis on Linux. Loaded images expose their architecture, bit width, byte order, entry point, mapped address ranges, sections, segments, and mapped bytes. A missing input file fails as unavailable input; a negative native entry address is refused as an invalid address.

- For raw images and supplied machine-code bytes, callers provide an architecture and can choose the load address and starting location. For headered images, callers can override the load base and entry point. Image inspection and symbol addresses use the selected mapping. A raw image without an architecture is refused as missing architecture information. For supplied machine-code bytes loaded at address zero, the selected starting location is a zero-based byte offset and becomes the entry address.

- Callers can include or exclude shared libraries, provide local library search locations, and inspect the loaded objects, imports, exports, and import resolutions. An address lookup identifies its containing object or indicates that no loaded object contains it. When strict missing-library handling is requested, an unavailable dependency fails as a missing dependency.

- With local Java loading support present, callers can load JAR files and, with the matching local Android platform support, APK files containing DEX bytecode. Callers can select the application entry method and supply associated native libraries for mixed Java and native analysis.

- Callers can register, replace, inspect, and remove byte replacements at mapped addresses. For non-overlapping replacements within file-backed regions that end strictly before the end of the input file, exporting the patched image changes those bytes and preserves every byte outside the replacements. Registered replacements are visible in subsequent instruction inspection and can be applied to an execution state.

- For a Mach-O image containing multiple architectures, callers can inspect the available architectures and select one for analysis. Selecting an architecture absent from the image is refused as an unavailable architecture.

### FP-03: Types and calling conventions

- Callers can describe scalar integers, floating-point values, pointers, arrays, structures, unions, enumerations, and function types through C type declarations. The resulting descriptions retain member names, element types, argument order, and return types, and can be reused in later declarations. For enumerations whose explicit values are integer literals, member values follow ISO/IEC 9899:1999, section 6.7.2.2, for the caller's enumerator declarations. Malformed declarations are refused as invalid type descriptions.

- Attaching an architecture to a type description supplies architecture-dependent sizes and member offsets while preserving the declared member and element types. Layout queries requiring architecture information are refused before an architecture is attached. On X86 and AMD64, a byte has eight bits; character, short integer, integer, single-precision float, and double-precision float widths are respectively 8, 16, 32, 32, and 64 bits. Long integers and pointers are 32 bits on X86 and 64 bits on AMD64. Long long integers are 64 bits on both architectures. For ordinary unpacked structures containing these scalars, pointers, and fixed-length arrays, members retain declaration order without overlapping, each starts at the earliest available multiple of its alignment, and size ends at the final member without additional tail padding. Scalar and pointer alignments equal their byte widths, and an array has its element alignment. Arrays preserve their declared cardinality and occupy contiguous element extents.

- Callers can describe function arguments and return values in registers and on the stack, or select a built-in convention. Built-in native conventions cover X86 cdecl, stdcall, fastcall, and Microsoft thiscall; System V and Microsoft AMD64; ARM soft-float and hard-float; AArch64; MIPS O32, N32, and N64; PowerPC 32-bit and 64-bit; S390X; and RISCV64. Given a convention and prototype, callers can obtain argument locations in declaration order and the return-value location. For scalar long-integer arguments and returns, sizes and stack positions are in bytes; stack positions are relative to the stack pointer at function entry. Registers below are used in order, followed by stack arguments at the stated first position and stride. The return uses the stated register.
  - X86 cdecl and stdcall use no argument registers, stack position 4 with stride 4, and eax return, with 4-byte values. Microsoft fastcall first uses ecx and edx; Microsoft thiscall first uses ecx; their remaining placement and widths are the same.
  - System V AMD64 uses rdi, rsi, rdx, rcx, r8, r9, stack position 8 with stride 8, and rax return. Microsoft AMD64 uses rcx, rdx, r8, r9, stack position 40 with stride 8, and rax return. Values are 8 bytes.
  - ARM soft-float and hard-float use r0 through r3, stack position 0 with stride 4, and r0 return, with 4-byte integer values. For scalar single-precision floating-point arguments and returns, soft-float uses the same integer locations, while hard-float uses s0 through s15 followed by stack position 0 with stride 4, and s0 return. Scalar single-precision values are 4 bytes.
  - AArch64 uses x0 through x7, stack position 0 with stride 8, and x0 return, with 8-byte values.
  - MIPS O32 uses a0 through a3, stack position 16 with stride 4, and v0 return, with 4-byte values. MIPS N32 uses a0 through a7 and v0 return with 4-byte values in 8-byte argument slots; on big-endian targets the first overflow value is at position 36 and successive values are 8 bytes apart. MIPS N64 uses a0 through a7, stack position 32 with stride 8, and v0 return, with 8-byte values.
  - PowerPC 32-bit uses r3 through r10, stack position 8 with stride 4, and r3 return, with 4-byte values. PowerPC 64-bit uses r3 through r10, stack position 112 with stride 8, and r3 return, with 8-byte values.
  - S390X uses r2 through r6, stack position 160 with stride 8, and r2 return, with 8-byte values. RISCV64 uses a0 through a7, stack position 0 with stride 8, and a0 return, with 8-byte values.

### FP-04: Execution states and memory

- Callers can create a minimally initialized state at a selected address, a state at the program entry, a state that runs program initializers before the entry, or a state prepared to call a selected function. Process-entry states accept concrete or symbolic command-line arguments and environment values and expose them to the simulated program.

- Callers can read and write concrete or symbolic register values and byte-addressed memory regions, including overlapping regions and regions crossing memory-page boundaries. Reading a stored region preserves its values; overlapping writes replace the covered bytes. Raw multi-byte memory access defaults to big-endian interpretation; raw register access defaults to the target register byte order. Both accept explicit big-endian or little-endian interpretation.

- In a minimally initialized symbolic state, reads of uninitialized memory or registers produce unconstrained symbolic values of the requested width. Callers can instead request zero initialization for uninitialized memory or registers, with those reads then returning zero.

- Copying a state preserves its current memory, registers, and constraints while allowing independent changes to each copy. Merging states with the same execution location and matching memory, file, and process-environment configuration preserves the alternatives in their memory, registers, and path conditions, and exposes conditions selecting the contributing alternatives.

- Callers can map and unmap memory regions and assign read, write, and execute permissions. With strict permission checking enabled, a read or write to unmapped memory or a read or write violating its required permission fails as an invalid memory access. With strict permission checking and non-executable-memory enforcement both enabled, instruction execution from mapped memory without execute permission fails as an invalid execution access. Under strict checking, ordinary permission reassignment is guaranteed for pages that are writable before the change.

- Callers can use symbolic memory addresses. With all-address access explicitly requested, and the difference between the greatest and least permitted byte addresses strictly smaller than the caller-selected span in bytes, reads and writes retain the values conditional on every feasible address. With an explicitly selected single-address policy, the access uses a feasible address and exposes the restriction through the state's constraints.

- Typed access to scalar values, array elements, structure members, and pointed-to values reads or writes the corresponding part of a supplied execution state's memory using the architecture-bound type's size, member offsets, and byte order.

### FP-05: Program files, streams, and operating environment

- Callers can supply simulated files containing concrete bytes, symbolic bytes, or mixtures of both, with concrete or symbolic sizes. For files with an end, the actual read length is limited by the requested length and bytes remaining; reads at the end return no available bytes. Files without a declared end can provide additional symbolic content beyond the content already supplied.

- Callers can read and write sequential streams whose successive input portions do not overlap. When short reads are enabled, the supplied read-length bound permits a symbolic actual length from zero through that bound, subject also to a caller-selectable maximum portion size. That maximum is 256 bytes by default. Callers can recover concrete stream content satisfying the resulting execution constraints.

- Simulated file descriptors support opening, reading, writing, closing, and seeking in seekable files. Reads and writes update the descriptor position and file content; seeking on a non-seekable stream and operating through an invalid or closed descriptor return simulated I/O failure.

- Callers can insert, retrieve, and remove files in a simulated filesystem and mount a selected local host directory into it. Relative paths use the simulated working directory. Changing the simulated root resolves the new root inside the existing simulated filesystem. Parent-directory traversal cannot move above that root, and changing the root does not itself mount a host directory. A working directory inside the new root keeps its relative location; one outside it becomes the new root.

- A program can consume supplied standard input and produce separately recoverable standard output and standard error. Callers can provide modeled pipe or socket input and inspect the resulting output without opening a connection to an external service.

- Process environment lookup exposes the environment values supplied by the caller and distinguishes a missing environment name from an existing value. Simulated process termination retains the process's termination status for inspection.

- When a simulated program requests a root-directory change, an empty path fails as a missing path and a path identifying an existing regular file fails as not a directory. A path resolved through a local host mount must identify an existing directory; an absent path fails as missing and an existing non-directory fails as not a directory. These failures preserve the previous simulated root. In an entirely simulated filesystem, a nonempty path with no file at that location can identify an implicit directory without a separate directory entry.

### FP-06: Instruction inspection and intermediate representations

- Given a mapped address or supplied machine-code bytes and an architecture, callers can obtain instruction disassembly with instruction addresses, decoded operations, operands, and instruction boundaries. Callers can restrict the requested byte extent or instruction count; the returned block describes only the decoded extent. Undecodable input exposes a decoding failure or a block ending at the undecodable portion rather than invented instructions.

- Callers can inspect intermediate representations of native instructions. These representations expose register and memory effects, operand widths, conditional exits, and control-transfer destinations and distinguish calls, returns, and system calls from ordinary continuation. For Java methods, callers can inspect the loaded Java statement representation and its statement locations.

- Native instruction analysis covers X86, AMD64, ARM including Thumb, AArch64, MIPS32, MIPS64, PowerPC 32-bit and 64-bit, S390X, and RISCV64 machine code. The selected architecture and byte order determine the interpretation of the supplied bytes. Inspection of one loaded image does not change how another image's bytes are interpreted.

### FP-07: Symbolic program execution and function invocation

- Starting from a supplied state, callers can execute native arithmetic, bitwise operations, comparisons, memory loads and stores, branches, calls, and returns. Result states expose the resulting register values, memory changes, and execution locations. A caller can restrict an execution request to a selected number of instructions or a selected stopping address.

- A conditional branch with symbolic input produces separately constrained feasible continuations for its true and false outcomes. Infeasible continuations remain distinguishable from executable continuations.

- For a computed branch whose destination expression has no more than 256 feasible addresses, default symbolic execution exposes concrete-address continuations for its feasible targets. Callers can choose a different destination bound. A computed destination exceeding that bound is retained separately as an unconstrained continuation without concrete-address continuations.

- Callers can invoke a binary function with concrete or symbolic arguments, a prototype, and a calling convention, and recover its return expression and result states. In single-path-only invocation, a call that branches into multiple feasible execution states is refused as a multiple-path result; a call whose feasible execution is exhausted into unresolved destinations or execution errors fails as no callable result.

- With local Java support present, execution handles method calls, object fields, arrays, integer computations, and branches over symbolic input. For loaded JNI libraries, Java-to-native calls and their returns preserve arguments, object references, and visible field or array updates across the language boundary.

- Without an explicitly enabled permissive execution option or caller replacement, an unsupported instruction or an instruction fetch from unavailable memory fails as an execution error. Such a failure does not produce a successful continuation for the failing step.

- Callers can place and extract function arguments and return values in a state according to a supplied prototype and calling convention. Strings, arrays, and structures can be supplied as argument values, with explicit pointer arguments referring to initialized memory containing those values. Placement respects caller-supplied stack and allocation locations. With allocation toward higher addresses selected, argument storage is placed at or above the supplied allocation origin.

### FP-08: Procedure replacement and modeled calls

- Callers can replace execution at a selected address or named symbol with caller-supplied behavior, inspect the installed replacement, and remove it. Reaching a replaced location applies the supplied state changes instead of the replaced instructions. At locations backed by original instructions, removing the replacement restores execution of those instructions.

- A function replacement receives arguments and supplies a return value according to the selected prototype and calling convention. A replacement can return to the caller, transfer to another address, terminate execution, or call a binary function and continue with its returned state.

- A replacement for an instruction region can specify a continuation after a caller-chosen number of bytes. Execution resumes at that continuation after the replacement's effects.

- Built-in byte models provide copying, overlapping movement, filling, and comparison. For concrete addresses and concrete nonnegative byte counts, copying, movement, and filling accept a destination and a source or fill byte, while comparison accepts two source regions. Copying and overlapping movement copy the original source bytes into exactly the destination extent and return the destination address; filling writes the supplied byte throughout that extent and returns its address. Byte comparison returns zero for equal extents and otherwise a result whose sign follows the first differing pair interpreted as unsigned bytes. Symbolic byte contents remain constrainable through the modeled effects and results.

- Built-in process and system-call models connect file operations, standard streams, environment lookup, memory allocation, and process termination to the simulated state. Callers can disable built-in replacements for selected library functions so that execution uses their loaded machine code instead.

- Built-in null-terminated string models provide length, copying, comparison, and length-limited comparison. For concrete addresses, concrete byte contents with readable terminators, and concrete comparison limits, length counts bytes before the first terminator; copying includes that terminator and returns the destination address. Comparison returns zero for equal strings and otherwise a sign determined by the first differing unsigned bytes, stopping at a terminator or, for length-limited comparison, the supplied byte limit. Symbolic string bytes remain constrainable through the modeled length or comparison result.

### FP-09: Control-flow recovery and program knowledge

- Callers can recover native control flow from an image entry, function symbols, or supplied starting addresses. For code connected by direct branches and calls, the result identifies basic blocks, branch and call relationships, function membership, call sites, and returning functions. Callers can query predecessors, successors, callers, callees, and the function containing an address.

- Static recovery can be restricted to supplied address regions and function starts, and callers can disable scanning of unreferenced executable contents. Recovery still follows direct control transfers within the selected analysis scope. An image with no executable regions yields no recovered executable blocks rather than fabricated code.

- Execution-based control-flow recovery accepts an initial execution state and a call-depth bound. It can preserve separate calling contexts so that returns from the same callee distinguish the callers represented by the selected context depth. Saved states and recorded data accesses can be retained for subsequent analysis.

- Recovery of bounded indirect branches through constant-address tables identifies the table entries and their destinations. Indirect calls or jumps without recovered targets remain identifiable as unresolved, so callers can distinguish them from transfers with a known destination.

- Callers can request normalized control-flow results in which an edge entering an existing block's interior refers to a block beginning at that destination. Function graphs distinguish local transitions, outgoing calls, returns, and tail transfers; a known non-returning call does not imply a return continuation.

- With data-reference collection enabled, callers can inspect referenced data and strings and query references to or from an address, distinguishing the referenced destination from its referring instruction. Function names and address labels can be changed, and subsequent name lookup reflects the change. Callers can attach, retrieve, and remove address comments and bookmarks.

- For loaded Java methods, control-flow recovery identifies method-local basic blocks, branches, and calls using Java statement locations, allowing callers to inspect the recovered method relationships without native instruction addresses. Analyzed call destinations on Java control-flow recovery requests must have Java bytecode bodies.

- Callers can inspect disassembly for recovered functions, selecting functions by name or address. Selection restricts the output to those functions; a selection that identifies no recovered function produces no disassembly for that selection and identifies the missing function.

### FP-10: Execution instrumentation and history

- Callers can observe memory reads and writes, register reads and writes, instruction execution, calls, returns, system calls, branch exits, constraint additions, and symbolic-variable creation through event callbacks. Each callback exposes the state and the event's relevant address, value, or condition, allowing the caller to distinguish different accesses and transfers. Instruction addresses are guaranteed for observations before instruction execution. Call and return notifications are available when the caller has requested call-frame information before executing the program.

- Callers can restrict callbacks by an event address or a state predicate and choose observation before or after the corresponding event. A callback requested before a memory write can change the value or address that will be written; a callback requested before a branch exit can change its destination. Callbacks that have been removed no longer receive events.

- A result state retains the ordered block addresses, transfer conditions, and transfer kinds from its executed path, including replaced procedure locations. With access recording enabled, it also exposes the memory and register accesses made by the program. Histories of different symbolic continuations retain their common past and their distinct later paths.

- Callers can inspect active call frames, identifying the current function, its call site, return destination, and entry stack position. Calls add a current frame and returns expose the caller's frame again.

### FP-11: Path exploration and execution control

- Callers can advance a selected group of execution states, select individual states to advance, and move, filter, or discard states among caller-named groups. States in an unselected group remain available without being advanced. Compatible states at a shared location can be merged while retaining their feasible alternatives.

- Exploration distinguishes states available for further execution, states that have terminated, states found to be unsatisfiable, states with unconstrained destinations, and states whose execution failed. Callers can request retention of unsatisfiable and unconstrained states. An execution failure retains the failing state and its cause for inspection without advancing that state as successful.

- Callers can search for instruction addresses or caller-defined state predicates while excluding addresses or predicates. Matching states are retained as found or avoided, and exploration stops after the requested number of found states or exhaustion of available states. The default requested found count is one. When both conditions match the same state, finding takes precedence by default; callers can explicitly give avoidance precedence instead.

- Callers can keep one path active while retaining alternative paths for later exploration. A path-length limit counts executed basic blocks and separates or discards a state when that count exceeds the caller's limit. For recovered loops, a caller-selected bound separates a state when its loop count exceeds the bound. The default loop count counts returns to the loop entry along a loop continuation edge, starting at zero on entry; callers can instead count visits to the loop entry, including the initial visit.

- Callers can guide execution with a supplied concrete block trace. Matching execution follows the supplied trace in order, and execution that cannot be reconciled with the trace fails as a trace mismatch rather than being reported as a completed match.

- For branching regions that rejoin at a shared continuation, callers can request combined symbolic exploration and recover a combined result state whose values and path conditions retain all feasible alternatives across that region.

### FP-12: Language and library recognition

- Callers can obtain language attribution for C, Rust, Go, and Swift. When loaded compilation-unit information identifies a single one of these languages and the image supplies no other language evidence, attribution identifies that language and exposes the identifying evidence. A raw image with no compilation units, compiler identification, symbols, named sections, dependencies, or nonzero content has unknown language attribution.

- Given a local FLIRT signature file and recovered functions, callers can recognize signature-matching library functions and assign their signature names. Recognition uses the supplied signature's byte constraints and referenced-function conditions; functions that do not satisfy those conditions do not acquire a signature-derived name.

- Callers can request behavioral identification of byte comparison, null-terminated string comparison, bounded string comparison, and case-insensitive string comparison in recovered X86 CGC leaf functions that compare contiguous readable byte buffers through byte loads, integer comparisons, and forward loops. Callers can include functions without known callers or restrict identification to functions with known callers. Identifications associate the matching operation with the function address; functions for which no operation is identified remain unmatched.

- Behavioral library identification is limited to 400 functions, counting all recovered functions in the supplied control-flow results; larger results produce no identifications.

### FP-13: Variable, prototype, and debug-information recovery

- For a recovered native function, callers can recover accessed stack and register variables, their locations and sizes, and the program locations that read, write, or reference them. Accesses to the same recovered variable can be queried together, while accesses to distinct non-overlapping stack variables remain distinguishable. For X86 and AMD64 recovery, signed stack displacements use a logical frame origin one machine word below the stack pointer at function entry.

- For X86 cdecl and System V AMD64 leaf functions whose scalar integer arguments are read before being overwritten and whose return value is explicitly assigned, callers can recover argument locations, a return-value location, and an integer function prototype. Recovered prototypes can be inspected and used by subsequent function invocation or decompilation. A caller-supplied prototype can replace an inferred prototype.

- Callers can infer variable types from supplied or recovered type constraints covering scalar widths, pointers, loads, stores, and structure-field accesses. Results preserve known scalar widths and distinguish a pointer with accessed fields from an unrelated integer. Explicit caller-assigned variable types remain available after further type inference.

- When loaded DWARF information describes a variable's address or stack-relative location at the current execution point, callers can resolve that source variable into the execution state's memory and inspect its value, pointer target, structure members, or array elements. For names shadowed in nested lexical scopes, resolution uses the nearest visible scope. Global-address resolution is guaranteed for position-independent ELF address descriptions or descriptions already relative to the loaded object; already-linked absolute global addresses in non-position-independent ELF images are outside this guarantee.

### FP-14: Data flow, dependencies, and program slicing

- Given a native function or block and selected observation locations, callers can obtain reaching definitions and uses of registers, stack locations, and concrete-address memory. A write replaces earlier definitions of the overwritten portion; a join retains definitions arriving along the incoming paths. Dependencies identify the defining locations contributing to a use and distinguish them from overwritten definitions.

- Callers can propagate known constants through register computations, obtain concrete-address load values from initial or caller-supplied base memory, and inspect constant replacements for concrete-address stores at program locations. Store replacements do not imply forwarding those stores into later loads. An overwritten value is not reported as the value of a later use unless a control-flow path still supplies that definition.

- Given execution-based control flow with saved states and recorded accesses, callers can obtain data dependencies among program locations, distinguishing dependencies on stored data from dependencies on the address used to access it.

- Given a control-flow graph, callers can obtain control dependencies identifying blocks whose execution depends on a branch outcome.

- Given a control-flow graph with one node per block address and a selected reachable target block, control-flow-only backward slicing identifies predecessor blocks and transitions that can lead to the target and excludes blocks with no path to it.

### FP-15: Abstract value-flow analysis

- Callers can represent sets of fixed-width integer values through lower and upper bounds and a stride, query membership and extrema, and combine them through arithmetic, bitwise operations, union, and intersection. A singleton represents its one concrete value; an empty intersection represents no possible value. Results may include additional possible values but do not exclude feasible values of the represented operation. For exclusive-or, this soundness guarantee is limited to one operand being a constant high bit and the other containing only values strictly below that bit.

- Given a recovered control-flow graph, a starting function, and a call-depth scope, callers can obtain a value-flow graph with abstract states at reached locations and function exits. For straight-line arithmetic and finite branches over known integer sets, the states retain the possible register and memory values rather than selecting one execution's value.

- For finite bounded iteration sets, with caller-supplied iteration and precision budgets exceeding the largest permitted iteration count, for integer loops that increment an initially zero accumulator by one and reset it to zero whenever it exceeds a fixed positive bound below signed overflow, abstract values of that accumulator at the loop exit remain between zero and that bound. Callers can inspect those lower and upper bounds. The result must also retain every feasible accumulator exit value, rather than merely choosing a narrower in-range constant.

- For addition or subtraction of bounded contiguous integer intervals whose concrete results all stay within the selected unsigned bit width, the abstract result's minimum and maximum equal the smallest and largest results over all combinations of values from the supplied intervals.

### FP-16: Decompilation and user refinement

- Callers can decompile selected recovered native functions into C-like pseudocode. For functions composed of scalar arithmetic, direct memory accesses, calls, conditionals, and loops, the output expresses the calculations, memory effects, calls, returns, and control conditions represented by the function. Structured conditionals and loops remain identifiable in the output; jumps can represent control transfers that are not structured.

- Callers can select C-like, Rust, or Go output, with C-like output as the default. Rust output represents recovered Rust references, aggregate values, alternatives, and formatting operations in Rust-style pseudocode. Go output represents recovered Go strings, slices, interfaces, multiple results, and method receivers in Go-style pseudocode.

- Callers can map rendered expressions and statements to their originating instruction addresses and locate rendered code corresponding to a selected instruction. Calls use known function names and supplied prototypes, and explicit names and types assigned by the caller are reflected in regenerated output.

- Callers can rename functions, local variables, arguments, and globals; change variable types, argument types, function prototypes, and return types; and attach or clear function and statement comments. Renames and explicit types survive re-decompilation, including re-decompilation caused by a prototype change. Default name validation accepts nonempty names formed from ASCII letters, digits, and underscores, with no initial digit. An empty name, an initial digit, or punctuation other than underscore is refused as an invalid name. Callers can instead request relaxed validation accepting any nonempty name without whitespace. Name collisions are permitted by default; callers can request refusal when another function or a variable in the edited function already has the requested name. Assigning the target's existing name leaves it unchanged.

- Editing a decompilation variable requires a decompilation of its function or an explicit request to obtain one. An unknown variable or an ambiguous function name is refused as an unresolved or ambiguous editing target, and malformed types are refused as invalid type descriptions. A global rename at a function's entry is refused as a function/global target conflict.

- Decompilation refuses a function exceeding the selected basic-block count limit, identifying the exceeded limit and measured count, and produces no successful decompilation for that request. The default is 50,000 recovered basic blocks per function. A count equal to its limit is permitted; callers can change the limit or disable it by selecting zero.

- Callers can decompile functions selected by name or address through the command line. Missing functions fail as unknown selections by default; with per-function error handling explicitly enabled, unavailable or failing selections are identified and other selected functions can still produce output. Selecting a raw image through the command line requires an architecture, load base, and entry point, and missing any of them is refused as an incomplete raw-image request.

- Function selection for edits accepts a name or an address. When both are supplied, the address takes precedence; an unresolved address does not select a different function merely because its name was supplied. An address within a recovered function's contiguous address extent selects that function.

### FP-17: Binary and function comparison

- Given two loaded native binaries and their recovered functions, callers can obtain function correspondences and distinguish matched functions from functions unmatched on either side. For corresponding functions whose instruction operations and local control-flow structure are unchanged apart from their load addresses and relocated call targets, comparison identifies them as unchanged.

- For a matched pair of functions, callers can inspect corresponding basic blocks and distinguish blocks with changed operations from unchanged blocks.

### FP-18: Editable assembly reconstruction

- For X86 and AMD64 ELF or CGC images whose code and data references have been recovered, callers can obtain assembly representing recovered procedures and data with named code and data references. For direct control flow and references to recovered static data, assembling and linking this output on Linux preserves the represented program's calculations, output, and termination behavior.

- Callers can insert assembly at an existing instruction boundary, remove selected instructions, append named procedures, and append writable or read-only data. The generated assembly includes these changes and redirects symbolic references to their named destinations. Appended data retains its supplied content and provides at least the requested byte capacity.

- Distinct reconstructed code or data labels remain independently referenceable when their original names collide. Requesting an assembly syntax for reconstruction does not alter later instruction inspection of the loaded image.

### FP-19: Saving and restoring analysis work

- Callers can save a loaded project and its analysis knowledge and restore it later. Restored image bytes, architecture, entry point, recovered functions, control-flow and call relationships, and collected data references preserve their saved meaning. Restoration uses the saved image content even when the original file is missing or has been replaced with different content.

- Saved names, prototypes, variable information, comments, and bookmarks survive restoration and remain usable for further lookup and analysis. Restoration makes previously rendered C-like and Go decompilation content available without another decompilation request. Rust output can be regenerated with its output-language association and editing metadata retained.

- Callers can serialize and restore execution states and program-analysis results for reuse. A restored state's memory, register values, and constraints preserve their meaning, and restored control-flow results preserve their nodes and transitions.

- Callers can take an analysis-knowledge snapshot and restore the selected saved information after subsequent edits or decompilation. Repeated restoration reinstates the saved comments, variables, and prototypes rather than preserving changes made after the snapshot; information explicitly excluded from the snapshot retains its later changes.

### FP-20: Local MCP analysis sessions

- A local MCP client can open multiple binary-analysis sessions, list their loaded images and analysis availability, and close individual sessions. Operations on one session retain that session's analysis and edits without modifying another session. Analysis and editing requests using an unknown or closed session are refused. Closing an unknown or already closed session instead reports that no session was closed.

- Within a session, clients can request control-flow recovery, function and block inspection, disassembly, calling-convention recovery, decompilation, strings, imports, exports, cross-references, and call relationships. Requests for discovered-function information before control-flow recovery fail as missing-analysis requests. An unknown function or a function request with neither a name nor an address is refused as an unresolved or incomplete target.

- Function listing supports a case-insensitive name substring and independent inclusion or exclusion of import trampolines and system-call functions. Without those filters, both categories are included. Matching functions are ordered by increasing address, then the caller's nonnegative skip count and positive page size select a page; the total counts all matches before pagination. The default skips no functions and returns up to 100. Function-name searches support containment, prefix, suffix, and regular-expression matching, all case-insensitive, with containment as the default. With recovered functions present, an invalid regular expression or unsupported search mode is refused as an invalid search. After control-flow recovery with data-reference collection, string listing returns referenced ASCII strings meeting the caller-selected minimum length, with a default minimum of four characters and a default result limit of 100.

- A session has a caller-selectable C-like, Rust, or Go decompilation language, defaulting to C-like. A one-request language override changes only that request. Variable and type edits apply to the selected output-language view of the function. Parameter type edits are observable after explicitly requesting re-decompilation. A type assigned in one language view does not replace the types in other views. An unknown language choice is refused as an invalid selection.

- Clients can submit batches of rename, type, and comment edits and obtain an individual success, unchanged, failure, or skipped result for each item. Validation-only requests do not apply the requested edits. Rename batches reject existing conflicting names by default and can explicitly permit name replacement. By default an invalid item does not prevent later valid items; when stopping on the first error is requested, earlier applied edits remain and later items are skipped. An empty batch or a batch containing a non-object item is refused as malformed input.

- Local sessions can be reached through standard input/output, server-sent events, or HTTP, with standard input/output as the default. Analysis output does not corrupt the client protocol exchange. Session loading excludes automatic shared-library loading by default. A raw-image session requires an architecture; a 16-bit DOS executable is refused as unsupported input.
