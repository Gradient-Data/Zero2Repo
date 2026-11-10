# navor runtime — Full Product Requirements Document

navor runtime runs WebAssembly core modules, components, and ahead-of-time artifacts through command-line and embedding interfaces.

### FP-01: Load, validate, and inspect core modules

- A Zig or C embedder can submit WebAssembly binary bytes for validation and loading, then inspect a successfully loaded module without running an exported function.

- Valid core modules are accepted for the enabled WebAssembly version: WebAssembly Core Specification 1.0, 2.0, or 3.0. Acceptance is determined from the supplied binary's declarations, types, instruction bodies, and feature requirements.

- Module inspection identifies every declared import and export in declaration order, distinguishing functions, memories, tables, globals, and exception tags. Import inspection preserves the requested namespace and name. For scalar numeric, vector, function-reference, and external-reference declarations, function and tag inspection exposes the declared value categories. For memories and tables with 32-bit limits, type inspection preserves the declared limits and table element category; global inspection preserves the value category and mutability. Detailed GC subtype inspection is outside this capability.

- A C embedder can serialize a loaded module and restore it. The restored module preserves the original declarations and, for the same import bindings, initial state, and invocation inputs, its execution behavior.

- A C embedder can share a loaded module and obtain it in another store. The obtained module preserves the original declarations and, for the same import bindings, initial state, and invocation inputs, its execution behavior.

- A binary with an invalid WebAssembly preamble, truncated declared contents, invalid section ordering, nonexistent referenced declarations, incompatible instruction operand types, or invalid declared limits is rejected. The applicable WebAssembly Core Specification determines these conditions from the submitted bytes; rejection does not yield a usable module.

- Validation and loading refuse modules declaring 64-bit memory or table addressing when WebAssembly Core 1.0 or 2.0 is enabled. General refusal of other later-version instructions is outside this version-selection guarantee.

### FP-02: Execute WebAssembly computations

- An embedder can instantiate a valid core module and call a named exported function with typed arguments. The caller can select an enabled interpreter or JIT mode and receive the function's ordered results or a failed invocation. Each mode's execution guarantees below apply to builds enabling that mode. Across the host-to-guest JIT boundary, multiple scalar results are guaranteed for two integer results; signatures with floating-point results among multiple results, or more than two results, are outside this guarantee. This boundary applies both to named calls and calls through guest function references.

- Scalar computation follows the enabled WebAssembly Core Specification 1.0, 2.0, or 3.0 for the supplied module, ordered arguments, initial instance state, and host-call results. Interpreter rounding of exact halfway values to the nearest integer, and interpreter minimum/maximum selection between oppositely signed zeros, are outside this guarantee; JIT computation retains the standard results for those inputs.

- WebAssembly 2.0 execution supports multiple function results, multiple block values, sign extension, non-trapping floating-point-to-integer conversion, reference types, and bulk memory and table operations. Mutable imported globals are supported through the interpreter; JIT instantiation of modules importing globals, memories, or tables is outside scope. Given the guest instructions, operands, initial memory and table contents, and data and element segments, results and state changes follow WebAssembly Core Specification 2.0 within these execution and embedding boundaries.

- JIT execution supports SIMD-128 and relaxed-simd inside guest functions, with results observable through scalar exports or memory. The supplied instruction sequence, vector operands, lane selections, and memory contents determine results according to WebAssembly Core Specification 2.0 SIMD and WebAssembly Core Specification 3.0 relaxed-simd respectively.

- WebAssembly 3.0 execution supports GC structs and arrays, typed function references, reference equality, null tests, subtype tests, casts, and reference conversions. The module's declared types, supplied references, field and element values, and subsequent guest operations determine the results under WebAssembly Core Specification 3.0. References still reachable by the guest retain their identity and values during ordinary struct and array operations. Preservation during sustained allocation stress is guaranteed for JIT execution; interpreter allocation-stress workloads are outside scope.

- The interpreter executes direct, indirect, and reference-based tail calls according to WebAssembly Core Specification 3.0, using the declared target signatures and supplied arguments. The JIT guarantee covers argument-free tail calls with scalar integer results; broader JIT tail-call signatures are outside this guarantee.

- Guest exception handling follows WebAssembly Core Specification 3.0 for the module's exception tags, thrown values, and enclosing handlers. The interpreter supports integer, floating-point, and reference payloads; the JIT guarantee covers integer payloads and integer-valued handler results.

- WebAssembly 3.0 extended constant expressions initialize globals, memories, and tables according to the supplied expression. With the interpreter, imported immutable values can participate in global initializer arithmetic and can directly supply a data-segment offset. Arithmetic combining imported globals with other operands in segment offsets, and imported-global element-segment offsets, are outside scope.

- A declared module start function executes as part of creating a usable instance. Its changes to guest state and host-visible effects precede a subsequent exported-function call, and repeated calls on one instance retain that instance's prior state.

- Executing an explicit unreachable instruction, integer division by zero, overflowing signed division, an invalid trapping numeric conversion, an out-of-bounds memory or table access, an invalid indirect-call target, or a failing reference cast ends the invocation unsuccessfully. The applicable WebAssembly Core Specification defines each condition from the operands and current state; instructions after the failing operation do not complete that invocation.

- An exception with no matching guest handler ends the invocation unsuccessfully. A trap in the module's start function prevents creation of a usable instance.

- Calling a nonexistent export, treating a non-function export as callable, or supplying an argument or result count that disagrees with the function declaration fails. The caller can distinguish these binding failures from a guest arithmetic fault.

- Interpreter execution of a SIMD instruction fails rather than returning a computed SIMD result. A forced JIT call whose public boundary contains a vector argument is refused with an unsupported-call outcome, distinct from a wrong argument count.

### FP-03: Bind host services and compose core modules

- Zig and C embedders can supply host functions and external state for a module's imports. They can also supply another instance's exports as imports, allowing one guest module to call another.

- A guest call to a bound host function delivers the guest's ordered scalar arguments and receives the host's returned values. The host callback can inspect or modify the calling guest's memory, and subsequent guest instructions observe those modifications. The C interpreter supports scalar arguments and ordered scalar results. The JIT host-callback guarantee covers up to four integer arguments, or up to two scalar arguments when a floating-point argument is present, and zero or one scalar result; wider signatures are outside this guarantee. Native Zig callbacks support all four scalar argument types and integer results; floating-point return callbacks are outside scope.

- Core modules in the same C store can call one another's scalar function exports when both use the interpreter or both use the JIT. The receiving function observes the supplied arguments and its own instance state, and its returned values reach the importing guest.

- Through the interpreter, imported memories, tables, and globals preserve shared state with the provided external entities. A write through one participant is visible to another participant using that same entity, while separately created entities remain distinct.

- For function, memory, table, and global imports, compatibility follows WebAssembly Core Specification 3.0 using the importing declaration and supplied external's kind, function signature, global mutability, reference type, and memory or table limits. Compatible bindings satisfy the corresponding imports within each execution mode's supported import kinds. For immutable reference globals, compatible binding is guaranteed when the declared reference types match; covariance between distinct reference types is outside scope.

- C imports continue to work after the embedder releases the original host-created function, memory, table, or global handle, while the owning store remains alive. A C guest-to-guest function binding likewise remains callable after the original exporter handles are released.

- A C embedder can call a host-created function directly without instantiating a guest. The callback receives the supplied ordered scalar arguments and its attached host context, and the caller receives the callback's ordered results and observes its host-side effects.

- A C embedder can attach a host context and a cleanup action when creating a host function. The callback receives that same context whether called by a guest or directly by the host. Releasing the function's handle does not invoke the cleanup while the owning store remains alive; releasing the store invokes the cleanup once with that context, whether or not the original handle was released earlier.

- A missing ordinary import or a supplied external with an incompatible kind or type prevents successful instantiation. A C external or module belonging to a different store is refused as a binding failure.

- A host callback that reports failure ends the affected guest call unsuccessfully. In a C guest-to-host call, a failure returned by the host callback is distinguishable from a guest arithmetic or memory fault.

- A direct C call to a host-created function with an argument or result count that disagrees with its declaration fails. A failure reported by the directly called callback reaches the caller with the host-supplied explanation, rather than being reported as a successful return.

### FP-04: Inspect and update live guest state

- An embedder can obtain an instance's memory and exported globals and tables, inspect their current contents, and request supported mutations or growth while the instance remains alive. Growth of imported host-created tables and host mutation of JIT function-reference tables are outside this capability.

- Host reads and writes of guest linear memory address the same bytes used by guest instructions. Numeric access supports signed and unsigned 8-bit, 16-bit, 32-bit, and 64-bit integers and 32-bit and 64-bit floating-point values. For the supplied address, type, value, and current bytes, numeric access follows the memory representation in WebAssembly Core Specification 3.0; byte-range access preserves the exact supplied bytes.

- A host can grow module-defined linear memory within its declared maximum and host ceiling when the host has storage for the requested allocation. The Zig growth operation reports the previous size. The contents and guest growth result follow WebAssembly Core Specification 3.0 for the original memory and requested growth.

- Module-defined external-reference tables can grow within their declared maximum and host ceiling when the host has storage for the requested allocation. The interpreter covers the declared range, and the JIT guarantee covers tables with an explicit maximum of at most 65,536 elements. One element is one reference entry, measured by the publicly reported table size. Successful growth follows WebAssembly Core Specification 3.0 for the original table, requested growth, and supplied initialization reference. Growth beyond this JIT success coverage is outside scope.

- Reading an exported global returns its current value. Writing a mutable global with a value of its declared type changes the value subsequently observed by the guest.

- Table reads and writes preserve null references and supplied external-reference identities. Subsequent host and guest reads observe an accepted table write.

- A C embedder can obtain a non-null guest function reference from a table entry or function result and invoke the referenced function while its instance remains alive. The invocation uses that function's declared scalar arguments, returns its ordered results, and observes the state of its originating instance. A null reference does not yield a callable function.

- Guest memory64 operations follow WebAssembly Core Specification 3.0 for the module's declared address types, selected memory, offsets, data segments, and supported operation operands. Interpreter scalar loads and stores are covered for dynamic addresses below 2^32 bytes; larger dynamic addresses are outside that mode's guarantee. JIT memory64 growth is covered for requested page counts below 2^32; larger growth operands are outside that mode's guarantee. Immediate offsets and interpreter bulk-memory operands retain their declared width. Multi-memory execution is supported through the interpreter: the selected memory follows the same specification. JIT multi-memory execution is outside scope.

- Checked host memory access beyond the current memory extent and host table access beyond the current element count fail without changing memory or table contents.

- A write to an immutable global fails and leaves its value unchanged. Looking up an absent exported global or table yields no usable accessor.

- Within the supported growth-operand ranges, guest growth, Zig host growth, and C JIT host growth beyond a declared memory or table maximum are refused without changing the existing contents or size. C interpreter host table growth also enforces its declared maximum; C interpreter host memory growth beyond the declared maximum is outside scope. The guest receives the growth-failure result defined by WebAssembly Core Specification 3.0, rather than a successful larger allocation.

### FP-05: Bound and cancel guest execution

- An embedder can assign fuel, memory ceilings, and table ceilings to guest instances, adjust live-instance budgets, and request cancellation.

- A finite fuel allowance terminates an otherwise unending guest loop with a fuel-exhaustion failure on both the interpreter and JIT. Fuel is an abstract allowance for guest execution. For identical deterministic guest work, initial state, allowance, execution mode, and host architecture, the completion or exhaustion outcome and remaining allowance are repeatable.

- A deterministic guest loop that repeats a fixed nonempty scalar computation, with no imports or early exit, can complete a finite requested repetition count under fuel metering and produce the same results as unmetered execution. For successful executions starting in the same state except for the requested repetition count, more repetitions consume more allowance on the same execution mode and host architecture. Consumption is the assigned allowance minus the publicly reported remainder. Increasing an allowance that already permits completion preserves the results and state changes.

- An embedder can read whether fuel metering is active and how much allowance remains. Assigning a replacement budget starts exactly the new allowance, without carrying over the prior remainder or subtracting earlier consumption. Guest execution does not increase the remainder, and exhaustion leaves no remaining allowance.

- Repeating a completed deterministic metered invocation from the same initial state, in the same execution mode and on the same host architecture, with exactly its consumed amount completes with no fuel remaining; an allowance below that amount produces exhaustion.

- Replacing an exhausted allowance permits a new invocation that fits the replacement budget; it does not resume the interrupted invocation. Disabling metering removes fuel exhaustion as a stopping condition and makes the remaining-allowance query report that metering is inactive.

- A host memory ceiling prevents growth of an interpreter instance's individual linear memories beyond that ceiling; on JIT instances this guarantee covers the first linear memory. A host table ceiling prevents an individual table from growing beyond that ceiling. Both restrictions apply even when the guest declaration permits a larger size. Raising or removing a ceiling permits growth again within the successful-growth coverage in FP-04. A refused growth leaves the prior size and contents intact.

- Requesting cancellation from another host thread stops a running guest loop with an interruption failure. Clearing the request permits later invocations to run.

- When creation-time limits are supplied, a module whose declared initial memory size or table element count exceeds the corresponding host ceiling does not yield a usable instance. The failure distinguishes the exceeded resource from a start-function trap.

- Fuel exhaustion and interruption remain distinguishable from one another and from ordinary guest arithmetic and memory faults. Neither outcome is reported as a normal function return.

### FP-06: Select and inspect execution modes

- By default, both execution modes are enabled. With both modes enabled, a caller can request automatic mode selection for a core module and query the resulting instance's selected mode. The caller can instead explicitly select an enabled interpreter or JIT mode.

- With both execution modes enabled, for a valid import-free core module whose declared value types and instructions belong to WebAssembly Core Specification 1.0, automatic selection reports JIT selection and provides the JIT behavior described in FP-02. For a valid module with compatible supplied import bindings that include a host-created memory, table, or global, automatic selection reports interpreter selection and preserves the supplied external state.

- The selected-mode query distinguishes interpreter selection from JIT selection. An explicit interpreter request is reported as interpreter selection; an explicit JIT request either succeeds and is reported as JIT selection or fails.

- Automatic selection does not turn an invalid core module into a successful execution. A failed invocation returns failure to the caller; host calls and guest-visible state changes completed before the fault are not duplicated.

### FP-07: Observe runtime activity and diagnose failures

- Zig and C embedders can register notifications for module acceptance, successful instance creation, traps, fuel exhaustion, and successful memory growth. Each registered notification is delivered once per corresponding submission, creation, trap, exhaustion, or growth event. Notifications caused by a public operation are observable before that operation returns. C embedders can inspect a returned trap and obtain the guest-call trace for interpreter faults.

- Module notifications distinguish accepted from rejected submissions.

- Instance notifications identify successful instances, and subsequent notifications for one instance remain attributable to it. Instances observed through the same notification registration receive distinct identities, including when an earlier instance has been released.

- A reported runtime trap identifies its category and affected instance. Fuel exhaustion produces both its exhaustion notification and its trap notification.

- Successful host-requested or guest-requested memory growth reports the affected memory and its size before and after growth.

- Registering observational callbacks that only record events leaves guest results, guest state changes, and failure outcomes unchanged. Removing a notification registration stops delivery of that notification for subsequent operations.

- For an interpreter invocation using ordinary guest calls, an explicit unreachable instruction, arithmetic fault, invalid trapping numeric conversion, memory or table bounds fault, invalid indirect-call target, null dereference, or failed reference cast produces a trace starting with the faulting guest function and continuing through active enclosing guest callers in innermost-first order. This coverage includes recursive calls, indirect calls, calls between interpreter instances, and calls from a declared module start function. A trace contains the whole chain when it has at most 64 locations and at least its innermost 64 locations when the chain is longer; one location represents one active guest function call. Locations identify the faulting instruction and each enclosing call instruction in the supplied WebAssembly binaries, according to WebAssembly Core Specification 3.0 and the executed guest call sequence.

- Refused memory growth produces no successful-growth notification. A trap created independently by the embedder produces no runtime-trap notification merely because the trap was created.

### FP-08: Supply WASI execution context and standard I/O

- An embedder can configure a WASI 0.1 host for a core module with program arguments and environment entries. The C embedding surface provides inherited standard output and standard error; input delivery and output capture are supplied through the native Zig runner. A CLI user can supply guest arguments and environment entries and use process standard input and output while running a WASI core module.

- A guest retrieves the supplied arguments in order and the configured environment entries according to WASI 0.1 preview1, using the host's supplied argument strings and environment names and values.

- Guest reads from a configured input consume its bytes in order and expose end of input after it is exhausted. Guest writes deliver their bytes to the configured standard-output or standard-error destination, preserving the distinction between those destinations.

- A guest's explicit WASI termination ends the call and preserves its requested exit status. The embedder can distinguish that termination from a runtime fault, and the status describes the most recent guest call rather than an earlier exit.

- Replacing a C store's WASI argument, environment, or preopened-directory configuration affects newly created instances. An existing instance continues to observe the configuration with which it was created, and its later exit status remains attributable to the guest that actually exited.

- An explicitly supplied, type-compatible C import overrides automatic WASI service binding for that import. The guest observes the supplied function's behavior on both the interpreter and JIT.

- For preview1 I/O, a guest buffer or buffer descriptor extending beyond guest memory produces a guest-visible memory-access error. An invalid descriptor and an operation disallowed on an existing descriptor produce distinguishable failures under WASI 0.1 preview1.

- When captured output would exceed an explicitly configured capture allowance, further output is refused with a space-related failure rather than being reported as successfully captured.

### FP-09: Access files through preopened directories

- A host or CLI user can grant a guest access to selected host directories under guest-visible names. A WASI 0.1 guest can enumerate these grants and operate on files and directories beneath them.

- Guest file creation, opening, reading, writing, seeking, positional reading and writing, resizing, synchronization, closing, and metadata inspection operate on the granted host files. For the initial file contents, granted rights, requested offsets, and supplied bytes, contents and positions follow WASI 0.1 preview1. Synchronization exposes successful completion or a host filesystem failure; persistence after host power loss is outside this guarantee.

- Guest directory creation, directory listing, removal, renaming, hard-link creation, symbolic-link creation and reading, and timestamp updates are reflected in the granted host directory. The requested paths, existing directory entries, link targets, and timestamp requests determine the results under WASI 0.1 preview1.

- Rights restrict descriptor operations and the rights of subsequently opened children. When a child is opened, its granted rights are the requested rights limited by the parent’s inheritable rights, so requesting excess rights does not grant them. A guest can reduce granted rights but cannot restore a removed right on the same descriptor. A later operation requiring a removed right is denied even when the host operating system would permit it.

- A preopened host path that cannot be opened prevents successful setup of the affected guest. Opening a nonexistent path without creation, exclusively creating an existing path, or using a file as a directory produces the corresponding distinguishable filesystem failure.

- Absolute guest paths are refused. For paths whose directory components are not symbolic links, parent-directory traversal that leaves the granted directory is refused, while traversal that stays within it remains usable. A requested symbolic-link target that lexically leaves the grant is refused.

- Empty paths and paths containing an embedded null character fail. A filesystem failure is returned to the guest without being represented as a successful file operation.

### FP-10: Read clocks and randomness and wait for I/O

- A WASI 0.1 guest can request clock values and resolutions, random data, and readiness notifications for configured input, output, files, and timers through its host services.

- Clock selections are realtime, monotonic, process CPU time, and thread CPU time. Realtime observations track host wall time; monotonic observations do not move backward; CPU-time observations describe CPU time consumed by the host process or thread. Clock values and resolutions follow WASI 0.1 preview1 for the selected clock and its host observation. A resolution query for a clock unavailable from the embedding host returns a failure indicating that the clock or service is unavailable instead of a resolution. This includes an embedding host configured without an I/O service, where clock-value queries also fail instead of returning readings.

- A random-byte request fills only the requested guest region. Across repeated requests, results are statistically consistent with independent uniform draws over all byte values.

- For supplied standard-input bytes and regular files, readiness observations distinguish remaining data from end of input. Polling identifies writable standard output and standard error. Given the subscribed descriptors, their current data and positions, and supplied realtime or monotonic timers, event meaning follows WASI 0.1 preview1.

- For subscriptions containing only realtime or monotonic clocks, the wait completes when the earliest subscribed deadline is reached and identifies an expired subscription. The supplied durations, absolute deadlines and selected clocks have the meanings defined by WASI 0.1 preview1. This applies while the host clock runs without adjustment and the host has not cancelled the wait.

- An unknown clock selection in a direct clock query or absolute timer, an unknown subscription kind, a nonexistent subscribed descriptor, insufficient polling rights, or a guest output region outside memory produces a distinguishable failure rather than a fabricated clock reading or readiness event.

### FP-11: Run core modules from the command line

- A user can run a WebAssembly core-module file from the CLI, supplying guest arguments, WASI configuration, an execution-mode choice, execution limits, or the name and scalar arguments of an exported function. For WASI runs of core modules, AOT artifacts, or components, the CLI prepends the input file's basename or supplied path to the supplied guest arguments; core-module and AOT runs use the basename. With no supplied environment entries or directory grants, the guest receives neither.

- Without an explicit function selection, the CLI chooses the module's WASI command entry when present, otherwise its conventional main entry. With an explicit selection, it invokes that function instead. The automatic entry must require no function arguments.

- Named invocation interprets each supplied scalar argument according to the selected function's declared 32-bit or 64-bit integer or floating-point type. Integer invocation supports decimal values within the declared width's signed range. An integer outside both that width's signed and unsigned ranges is refused. Finite floating-point input and results are interpreted at their declared precision; reading a printed finite result at that precision recovers the guest's value. The user receives all returned scalar values in result order. Interpreter execution supports mixed scalar multiple results. JIT multiple-result support covers two integer results with scalar arguments and three integer results without arguments.

- For core modules without a declared start function, supplied fuel limits enforce the execution allowance, with exhaustion reported as a fuel-exhaustion failure. A guest loop that continues past a supplied elapsed-time deadline terminates with an interruption failure.

- For a module with one declared linear memory, a supplied memory ceiling prevents growth above that ceiling and preserves the existing contents and size on refusal. Refusal of an already larger declared initial memory is outside this CLI guarantee.

- With explicit JIT selection, a module whose combined declared initial table sizes exceed the supplied table ceiling is refused, and subsequent table growth obeys the supplied ceiling.

- A version request, or invoking the application without a command, reports the release version and the enabled WebAssembly level, WASI level, and execution modes, allowing builds with different enabled capabilities to be distinguished without running a guest. A version request additionally reports the build mode.

- A C embedder can query the linked runtime's release version without loading a guest. Builds of the same release report the same release version even when their enabled WebAssembly, WASI, or execution modes differ.

- A normal return completes the command successfully; explicit guest WASI termination supplies the command's exit status. Returned function values remain observable independently of that status, so an integer function result does not become a guest exit request.

- A module without an automatic entry is refused unless the user selects an exported function. An automatic entry requiring arguments, an absent selected function, an argument-count mismatch, or a scalar argument that cannot be parsed for its declared type fails without a successful function result.

- An unreadable input, invalid module, guest trap, or invalid command request makes the command unsuccessful. The user can distinguish a usage failure from a guest execution failure, and guest traps remain distinct from successful WASI termination.

### FP-12: Produce and execute AOT artifacts

- A user can submit a valid core-module file within the JIT execution coverage and an output destination to the CLI's artifact-production capability, obtaining an AOT artifact that can subsequently be supplied to the CLI's execution capability.

- The produced artifact executes after the original input file is removed when execution uses the same runtime executable on the same supported host used for artifact production, including execution in a separate process. Compatibility with another host or a different runtime executable is outside scope. For the same guest-visible program name and arguments, named invocation, initial host files, environment, standard input, and host services, its function results and guest-visible state changes match execution of the source module through the JIT.

- An artifact run supports the WASI I/O, explicit guest exit status, named scalar invocation, cancellation deadlines, memory-growth ceiling, and initial-table ceiling described in FP-11, with its explicit-JIT conditions applying to the artifact run.

- For identical deterministic guest work and initial state on the same host, an artifact run and a source-module JIT run given the same fuel allowance have the same completion or exhaustion outcome.

- Invalid source WebAssembly, an unreadable source file, or an unwritable artifact destination makes compilation unsuccessful. An artifact with an incompatible artifact-format version, a different CPU architecture, or truncated declared contents is refused.

- Requesting interpreter execution of an AOT artifact is rejected as a contradictory execution request.

### FP-13: Inspect and invoke typed components

- With Component Model support enabled, a Zig embedder can open a WebAssembly component binary, discover its callable exports and types, and invoke an export with component-level values. No separate WIT source file is needed for this discovery.

- Export discovery includes both top-level functions and functions exported through interfaces, preserving the distinction between functions belonging to different interfaces. Type discovery resolves declared parameter and result types and retains record field names, variant cases, enum labels, and flags labels.

- Typed invocation supports booleans; signed and unsigned 8-bit, 16-bit, 32-bit, and 64-bit integers; 32-bit and 64-bit floating-point values; Unicode characters; strings; variable-length lists; records; tuples; variants; enums; flags; options; and success-or-error results. For the supplied component binary, its WIT declarations, ordered argument values, and UTF-8 string setting, typed arguments reach the guest with their declared values within the following boundary: negative signed 8-bit and 16-bit arguments preserve their declared-width value, but sign extension into a wider core argument is outside the guarantee. Guest computation that interprets these arguments at their declared width is supported. The caller observes the guest's computed result, including nested compound values and the selected result alternative. A function without a declared result completes without supplying a result. When a component declares return cleanup for a successful invocation, its guest-visible effects are observable by the next invocation; the returned value retains the value computed before cleanup.

- An opened component remains usable after the caller releases the original input-byte buffer. String and compound-value results retain their contents across subsequent calls while the caller retains the returned values and the component remains alive.

- A core module supplied to the component-opening entry is rejected. Component declarations with nonexistent type indices are rejected. Function-export names, parameter names within a signature, record-field names, variant-case names, enumeration labels, and flags labels must be unique within their respective declarations; duplicates are rejected. Complete validation of canonical-lift signatures against embedded core function signatures is outside scope. Components without an embedded executable core module are outside the opening guarantee.

- An unknown export, incorrect argument count, or argument whose scalar or compound shape disagrees with the declared WIT type fails. The failure distinguishes unresolved exports, argument-count mismatches, and value-shape mismatches, and supplies a human-readable diagnostic for the failed call.

- The typed invocation surface refuses component functions using a non-UTF-8 string setting and refuses stream or future values as ordinary typed host arguments or results. Asynchronous execution is a separate capability below.

### FP-14: Execute composed component graphs

- A Zig embedder can instantiate a component binary containing nested components and declared connections between their imported and exported functions, then invoke a function exposed by the composed graph.

- Function connections follow the supplied component's direct function imports, instance exports, and re-export declarations. A call from one component reaches the selected provider, and its computed return value reaches the caller. Function export names come from the component. Importing an interface instance as a connection is outside scope.

- Synchronous component connections support nonempty parameter sequences of booleans, signed or unsigned integers no wider than 32 bits, Unicode characters, and records or tuples recursively containing those values, with a result from that same scalar set. This guarantee covers parameter sequences that use the Canonical ABI's direct parameter form; indirect parameter sequences are outside scope. The receiving component obtains the supplied ordered values with their declared types, and its returned scalar value reaches the caller.

- UTF-8 component connections additionally support a single string or a single list of numeric, boolean, or character values returning a scalar from the preceding set. A function with no arguments can return a record containing strings or lists, or a record containing multiple scalar values. A single record argument containing strings or lists can return a scalar from the preceding set. These records contain numeric, boolean, character, string, list, or nested record values; numeric fields in record arguments are restricted to integers no wider than 32 bits, while numeric list elements and result-record fields retain their declared widths. Standalone string results are outside scope. Received values retain their declared types and contents across the component boundary.

- A missing provider for a declared component function prevents a usable composed graph. A synchronous connection with a standalone 64-bit integer or floating-point argument, or a non-UTF-8 string setting, is refused rather than producing a substituted result.

- A guest string or list argument whose referenced contents extend beyond the sending component's memory fails the call without delivering that argument or producing effects in the receiving component.

### FP-15: Use guest-defined component resources

- Through the component embedding surface, a host can invoke an exported guest resource constructor, retain its owning resource handle, pass a borrowed resource to a guest operation, and explicitly release the owning resource.

- Resource state and borrowed operations are supported for resource types exported through a component instance; top-level exported resource-type aliases are outside this guarantee. Repeated operations on one live resource observe that resource's guest-defined state. Distinct constructor results identify distinct resources, and a borrowed operation addresses the resource represented by the supplied live handle.

- For resource types exported through a component instance, explicitly releasing an owning guest resource invokes its declared guest destructor. Destruction through top-level exported resource-type aliases is outside this guarantee. Destructor effects on guest state or host-visible output are observable once for that successful release.

- Releasing the same resource again without an intervening allocation, using a never-created handle, or using a handle with the wrong resource type fails. A component without resource support does not report successful resource release. A refused resource operation leaves other live resources usable and unchanged.

### FP-16: Run WASI 0.2 components

- With WASI 0.2 enabled, a user can run a WASI component command through the CLI or a Zig host configured with arguments, environment entries, standard I/O, and preopened directories.

- A WASI 0.2 component obtains its configured arguments and environment, reads standard input, writes standard output and standard error, and completes with a distinguishable successful or unsuccessful command outcome. Values and command outcomes follow WASI 0.2 preview2 for the supplied component and host configuration.

- WASI 0.2 component file and directory operations expose the granted host filesystem through descriptors. Supported operations are opening, creation, direct reading and writing, directory listing, type and metadata inspection, synchronization, renaming, removal, hard links, symbolic links, and reading symbolic-link targets. Resizing and explicit timestamp updates through WASI 0.2 are outside scope. The initial host filesystem, supplied paths, offsets, bytes, and rights determine outcomes under WASI 0.2 preview2.

- For one unchanged host file, metadata-identity queries through its open descriptor and through a path to that file return equal values. Queries for distinct files on the same granted filesystem distinguish their identities. This includes files reached through different hard links to the same object; opening the same object through another link retains its identity.

- Component clock reads expose wall time and nondecreasing monotonic time, according to WASI 0.2 preview2 for the requested clock and host clock observation. Component polling identifies readiness of subscribed standard input and output for the supplied stream contents and host state under WASI 0.2 preview2. Waiting for a future clock deadline through preview2 polling is outside scope.

- Terminal detection distinguishes an attached terminal from supplied input bytes or captured output.

- Secure and insecure random-byte requests return the requested amount of data with a distribution statistically consistent with independent uniform byte draws. Repeated insecure-seed requests within one component instance return the same seed.

- Opening a nonexistent file without creation or attempting exclusive creation of an existing file returns a component filesystem error, preserving the distinction between those conditions. Passing a non-pollable resource as a polling resource or referencing bytes outside guest memory fails the guest operation.

- Component execution is refused when Component Model support is absent. A CLI component run combined with the core-module fuel, deadline, memory, or table-limit controls is refused rather than accepted with those requested controls ignored.

### FP-17: Execute native async components and WASI 0.3 commands

- With WASI 0.3 enabled, a caller can run a component using the Component Model's callback form of async exports. Guests can use futures, streams, waitable sets, and asynchronous calls between components. The CLI can run WASI 0.3 commands with configured arguments, environment entries, standard input and output, and preopened directories.

- An async command that yields and later completes delivers its declared successful or unsuccessful command outcome. Direct host retrieval of an arbitrary main-task integer result is outside scope. When one component asynchronously calls a function with no arguments and a 32-bit integer result in another component, the caller receives the callee's returned value.

- Across connected components, a future whose value is written before reading transfers a single scalar value, and a stream transfers ordered scalar elements whether the reader or writer waits first. Both support booleans, signed and unsigned 8-bit, 16-bit, 32-bit, and 64-bit integers, and 32-bit and 64-bit floating-point values. Futures also support Unicode characters. Readers receive the corresponding written values with the declared scalar types.

- Completion of a waited-on read or write becomes observable through the guest's waitable set and allows dependent guest work to finish. Closing a stream peer wakes the pending reader or writer so that dependent guest work can finish. Dropping a future reader makes its writer observe that the receiver is gone.

- Within a single component, cancellation of a pending stream read ends that pending read without delivering subsequently written data into the cancelled destination. The stream remains usable for subsequent transfer to a host-backed receiver. Nonempty guest-to-guest stream copying within a single component is outside scope.

- WASI 0.3 commands receive configured arguments and environment entries, exchange ordered bytes with standard input, standard output, and standard error, and report command success or failure. These outcomes follow WASI 0.3.0 for the supplied host configuration and stream contents.

- Relative clock waits and absolute monotonic deadlines complete when their requested interval or deadline has elapsed, following WASI 0.3.0 for the supplied clock requests and host clock observations.

- WASI 0.3 filesystem services provide file reading, writing, and appending through streams, and expose preopened directories, file and directory opening, creation, directory listing, descriptor flags and type, metadata inspection, resizing, synchronization, timestamp updates, renaming, removal, hard links, symbolic links, and reading symbolic-link targets. For the initial host files, granted descriptors and rights, supplied paths, offsets, and stream bytes, contents and completion results follow WASI 0.3.0. Completion failures are observable through the file operation's result as well as termination of its data transfer.

- WASI 0.3 file-identity comparison distinguishes two descriptors referring to the same host object from descriptors referring to distinct host objects, including when hard links provide different paths to one object. For an unchanged object, metadata-identity queries by descriptor and by path agree; distinct files on the same granted filesystem have distinguishable identities. A missing path yields a filesystem failure rather than an identity for a nonexistent file.

- WASI 0.3 wall-clock and system-clock reads reflect host wall time, and monotonic-clock reads do not move backward; their values and resolutions follow WASI 0.3.0 for the requested clock and host clock observation.

- WASI 0.3 secure and insecure random-byte requests return the requested amount of data, statistically consistent with independent uniform byte draws. Repeated insecure-seed requests within one component instance return the same seed.

- An async export declaring a result but completing without supplying it fails. A future writer dropped before providing its required value fails. Invalid stream or waitable-set handles and stream operations attempted after that endpoint has finished fail rather than reporting successful transfer.

- In a component graph whose tasks are all waiting on guest-owned streams with no remaining operation that can supply data or close a peer, execution reports deadlock rather than successful completion. A component attempting to use another component's ungranted stream handle fails. Passing a live endpoint as a stream argument or as its unchanged scalar handle grants the receiving component access; passing an encoded scalar does not grant access to the recovered handle.

- Async exports without the callback form and cross-component stream or future cancellation operations are outside the supported execution surface and are refused.

### FP-18: Exchange data over WASI sockets

- WASI 0.2 and WASI 0.3 components can use TCP host services, and WASI 0.3 components can additionally use UDP host services, when host networking is available.

- A guest TCP client can connect to a reachable peer and exchange bytes in order. A guest TCP listener can bind an available local address, accept a peer, and exchange bytes with that peer. For supplied IPv4 or IPv6 endpoints and sent bytes, network behavior follows TCP and the applicable WASI 0.2 preview2 or WASI 0.3.0 socket semantics.

- TCP address queries report the actual local endpoint after listening or connecting and the connected peer. WASI 0.3 connections from an explicitly bound local socket preserve that binding; WASI 0.2 client connections are supported without a prior explicit bind. A completed peer close becomes distinguishable from additional received data.

- A WASI 0.3 UDP socket can bind, select or clear a default peer, send datagrams, and receive datagrams with their sender addresses. Selecting a default peer without a prior explicit bind supplies a usable local endpoint, and subsequent sends use that endpoint. For supplied IPv4 or IPv6 endpoints and datagram contents, delivered messages preserve their contents and message boundaries according to UDP and WASI 0.3.0.

- WASI 0.3 socket inspection reports the address family used when the socket was created. TCP inspection distinguishes a listening socket from a socket that has not begun listening. A bound WASI 0.3 UDP socket reports its actual local address; a UDP socket with a default peer reports that peer, and clearing the default peer makes a subsequent peer query fail as unconnected.

- WASI 0.3 socket address resolution accepts IPv4 and IPv6 literals and resolves hostnames through the configured host networking environment. A literal produces its corresponding address, preserving its address family. A successfully resolved hostname produces addresses reported by that host environment; a successful result is nonempty. These outcomes follow WASI 0.3.0 for the supplied name and the host resolver's results.

- Connecting to a closed local TCP port reports connection refusal. Establishing a listener on a local endpoint already held by an active listener fails. Accepting on a socket that is not listening, receiving on an unbound UDP socket, and querying a peer on an unconnected socket produce socket-state failures.

- An invalid address or an address-family mismatch is refused. Failure to resolve a hostname through WASI 0.3 returns a resolution failure rather than an invented address.

### FP-19: Exchange HTTP requests and responses through WASI 0.3

- A WASI 0.3 component can construct HTTP request and response resources and issue a plain HTTP client request. Host invocation of an incoming HTTP component handler is outside scope.

- Header resources preserve repeated values and their order, and lookup is case-insensitive. Querying an absent name returns no values and reports absence.

- A header collection created independently, initialized from supplied header pairs, or copied from another collection is mutable until it is supplied when constructing a request or response. Replacement on a mutable collection removes the previous values for the named header and installs the supplied values in order; append adds the supplied value after the existing entries; deletion removes the named header's values. Retrieving and deleting together returns the removed values in their previous order and leaves that name absent.

- A copied header collection starts with the source's contents and can be modified independently, even when its source is immutable.

- Request resources allow assigning and reading their method, scheme, authority, and path with query; response resources allow assigning and reading their status. The most recently assigned value is observable. Methods include GET, HEAD, POST, PUT, DELETE, CONNECT, OPTIONS, TRACE, PATCH, and extension methods satisfying the RFC 9110 token grammar. Schemes include HTTP, HTTPS, and extension schemes satisfying RFC 3986. Retaining HTTPS metadata does not provide HTTPS transport.

- Optional scheme, authority, and path values can be cleared and are then observed as absent. An explicitly assigned empty path denotes the root path. Requests and responses retain their supplied headers and body, with an absent body observed as empty content.

- Request options created independently or copied from another options resource permit assigning and clearing optional timeouts for connection establishment, the first response byte, and the interval between response bytes until supplied when constructing a request. Reads return the assigned optional values independently. A copy initially contains its source's timeout values, and modifying the copy leaves the source unchanged. Transport enforcement of these timeouts is outside scope.

- For a plain HTTP endpoint, the client sends the selected method, authority, path with query, headers, and completed request-body bytes, and makes the peer's response status, headers, and body available to the guest. Client transport supports POST, PUT, and PATCH; transport of other methods is outside scope. HTTP meaning follows RFC 9110 and WASI 0.3.0 for these supplied request values and the peer's response.

- Creating or changing a header with a name outside the RFC 9110 token grammar fails. A header value containing characters outside the RFC 9110 field-value character alphabet fails. Refusal for an invalid name or value leaves existing header values unchanged. These checks apply to the supplied name and value; preservation of original header-name capitalization and rejection of leading or trailing whitespace are outside this requirement.

- Headers obtained from a guest-constructed request or response, or from a response received from an HTTP peer, are immutable. Supplying headers when constructing a request or response ends their independent mutable ownership; subsequently obtained header views reject replacement, append, and deletion without changing the observed values.

- Options obtained from a request are immutable, and attempted changes fail without changing their observed timeout values.

- Assigning a method outside the RFC 9110 token grammar, a scheme outside the RFC 3986 scheme grammar, or a response status outside the RFC 9110 status-code range fails without changing that metadata.

- Assigning a path or query containing an unescaped ASCII space or control character fails. Assigning an empty authority or an authority whose explicit port is empty or contains a nondecimal character fails. These refusal rules apply to the supplied metadata; general URI validation beyond them is outside scope.

- A client request lacking an authority, or a connection attempt to an unavailable plain HTTP endpoint, returns a failed request outcome rather than a successful response.
