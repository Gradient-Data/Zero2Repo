# Full Product Requirements: Zelviro

Zelviro is a Go interpreter for running programs and scripts, interactive exploration, and embedding Go execution in Go and C applications.

### FP-01: Stateful Go evaluation

- A Go host can create an interpreter, supply source text with a source label, and evaluate expressions, declarations, statements, or a complete program. Evaluation returns the last produced value when one exists and distinguishes a failed evaluation from a successful evaluation with no value.

- Successive evaluations in one interpreter retain declared variables, functions, types, imports, and changes to program state. Newly introduced initialization functions execute once; subsequent unrelated evaluations do not repeat them. In sessions introducing globals, the first variable submission includes an explicit initializer. Repeated short-circuit computations across submissions are guaranteed when performed inside declared functions.

- Separately created interpreters keep their interpreted declarations and variables independent.

- Hosts can supply input, output, and diagnostic streams. Interpreted basic printing and formatted printing reach the configured output stream, including after the host replaces that stream between evaluations. Hosts can instead retain access to the host process's ordinary standard streams.

- Calls to undefined functions and variable initializers referring to undefined names fail with diagnostics identifying the supplied source and offending location. An unfinished delimited construct is distinguishable from a complete call that cannot be accepted.

### FP-02: Scalar expressions and bindings

- Programs can evaluate boolean, signed and unsigned integer, floating-point, complex, rune, and string expressions. For the supplied operands and their types, literal interpretation, operator precedence, arithmetic, logical operations, comparisons, bit operations, and conversions follow the corresponding rules of The Go Programming Language Specification, language version go1.26, using the host's integer word size.

- Typed and untyped constants, single-name repeated constant declarations, and declaration-position enumeration in parenthesized declaration groups follow The Go Programming Language Specification, language version go1.26. Evaluating integer division by zero as a value-producing expression fails; rejection of an unused constant declaration containing such a division is outside the guarantee.

- Variable declarations, zero initialization, short declarations, reassignment, simultaneous assignment, compound assignment, and lexical shadowing follow The Go Programming Language Specification, language version go1.26, for the supplied declarations and expressions.

- Programs can obtain the minimum or maximum of ordered scalar operands, construct a complex value from compatible real and imaginary operands, and extract either component of a complex value. Extrema are guaranteed for operands already sharing a scalar type. For these operands, results and result types follow The Go Programming Language Specification, language version go1.26.

### FP-03: Collections, structures, and pointers

- Programs can construct arrays, slices, maps, and structures through zero values, allocation, and composite literals. Indexing, keyed and positional initialization, slice bounds, length, capacity, appending, copying, deletion, and clearing follow The Go Programming Language Specification, language version go1.26, for the supplied container types, contents, indices, and requested sizes.

- Array, structure, slice, and map assignment and argument passing follow The Go Programming Language Specification, language version go1.26, for the supplied assignments and calls.

- Addresses of uncaptured variables, array or slice elements, and structure fields support indirect reads and writes to the addressed storage. Allocation, pointer equality, and recursive or mutually referential structure types follow The Go Programming Language Specification, language version go1.26, for the supplied types and references.

- Map lookup with presence results, nil-container comparisons, string indexing, slicing, and conversion to or from byte and rune sequences follow The Go Programming Language Specification, language version go1.26, for the supplied maps, slices, text, keys, and indices.

- Programs can inspect storage size, alignment, and field offsets and form pointer-based slices and strings over valid live storage. These operations follow the system-considerations provisions of The Go Programming Language Specification, language version go1.26, for the supplied types, addresses, offsets, lengths, and host memory layout.

### FP-04: Functions and control flow

- Programs can declare and call functions, recurse, pass functions as values, return multiple values, use named results, and accept or expand variadic arguments. Calls and returns follow The Go Programming Language Specification, language version go1.26, for the supplied function declarations and arguments.

- Closures retain access to captured variables after the declaring call returns. Reads and assignments through closures sharing a captured variable observe the same variable, following The Go Programming Language Specification, language version go1.26.

- Conditional statements, expression switches, counted and conditional loops, labeled and unlabeled loop exits, loop continuation, jumps, and returns select and execute statements according to The Go Programming Language Specification, language version go1.26, for the supplied program and condition values.

- Iteration over integers, arrays, slices, strings, maps, and iterator functions follows The Go Programming Language Specification, language version go1.26, for the supplied subject and iteration variables. Iterator functions yield one or two values per callback. An unsupported subject type is refused when an iteration variable is declared; an excessive number of iteration variables is refused.

### FP-05: Deferred calls and panic recovery

- Programs can defer calls, including calls that update named results, following The Go Programming Language Specification, language version go1.26, for the supplied calls and return paths.

- For a panic that is not replaced by another panic during deferred cleanup, deferred calls execute during unwinding and a directly invoked deferred recovery can stop the panic. The recovered value and subsequent return behavior follow The Go Programming Language Specification, language version go1.26, for the supplied panic value and deferred calls.

- Runtime integer division by zero, out-of-bounds indexing or slicing, nil-pointer dereference, calling a nil function, negative slice length, and negative channel capacity raise recoverable runtime panics. Requesting a slice length greater than its capacity also raises a recoverable runtime panic.

### FP-06: Methods and interfaces

- Defined types can have value-receiver and pointer-receiver methods. Direct method calls, captured method values, and method expressions using the defined receiver type name whose pointer form matches the declaration follow The Go Programming Language Specification, language version go1.26, for the supplied receiver and arguments.

- Embedded fields and embedded interfaces promote accessible members according to The Go Programming Language Specification, language version go1.26. Ambiguous promoted method selectors are refused. Field selection is guaranteed for unambiguous embeddings.

- Interface assignment and calls retain the concrete value's dynamic type and dispatch its methods. Type assertions and type switches follow The Go Programming Language Specification, language version go1.26, for the supplied dynamic value and requested types.

- Interfaces preserve typed nil values, and named types remain distinct from their underlying types and from same-named types in packages with distinct declared package names. Interface comparison and map keys already assigned to interface variables follow The Go Programming Language Specification, language version go1.26, for comparable dynamic values.

- Programs can declare non-generic type aliases. Assignment and type identity through the alias follow The Go Programming Language Specification, language version go1.26, for the supplied alias and target type.

### FP-07: Goroutines and channels

- Programs can launch independently progressing goroutines and exchange typed values through buffered and unbuffered channels. Sending, receiving, closing, and iterating over channels follow The Go Programming Language Specification, language version go1.26, for the supplied channel capacities, values, and operations.

- Programs can select channel communications with or without a default branch, following The Go Programming Language Specification, language version go1.26, for the supplied channels and selection cases. Assignment of received values to existing variables is supported within function bodies.

- Closing an already closed or nil channel and sending on a closed channel inside an interpreted callback invoked by a native function raise panics that interpreted deferred code surrounding the native call can recover.

### FP-08: Generic functions and types

- Programs can instantiate generic functions and types with explicit type arguments and invoke methods on instantiated generic receivers. Instantiations retain the chosen types in results, fields, and method behavior according to The Go Programming Language Specification, language version go1.26, for the supplied declarations, type arguments, and values.

- Calls can infer type arguments from explicitly typed arguments and untyped integer, floating-point, string and boolean constants, including arguments with declared pointer, slice, map, channel, and function types, and can combine an explicit leading portion of the type arguments with inference for the remainder. Inference follows The Go Programming Language Specification, language version go1.26, for the supplied parameter types, constraints, explicit type arguments, and actual arguments; unresolved type arguments are refused. Typed complex and rune arguments are supported; standalone untyped rune and imaginary constants and mixed-kind complex constant expressions are outside the inference guarantee. A slice produced directly by a generic iterator need not support inference in a subsequent generic call.

- Type arguments are checked against comparability constraints and unions of concrete or underlying types according to The Go Programming Language Specification, language version go1.26, for the supplied argument type and constraint. An argument outside such a constraint, or missing a method named by an interface constraint, is refused. Distinguishing a named scalar from its underlying type in a concrete union is guaranteed for native named scalar types.

### FP-09: Native Go interoperability and reflection

- A Go host can expose native functions, constants, variables, and types to interpreted code. Calls preserve supplied argument values and native results, including multiple results and variadic calls; writes to exposed mutable strings and structures and through native pointer parameters are visible to both sides. Exact native constants retain their supplied precision in ordinary expressions; redeclaring them as source constants is outside this precision guarantee.

- Native calls can invoke interpreted function values as callbacks. Callback arguments, results, and captured-state changes remain observable across nested calls between native and interpreted code. An ordinary panic raised by a native call participates in interpreted deferred recovery.

- Interpreted implementations of formatting, error, reader, writer, sorting, JSON customization, and XML customization interfaces can be consumed by the corresponding native Go operations. Those operations invoke the interpreted methods and use their returned values and mutations.

- Reflection over interpreted values exposes their kinds, names, defining package identity, fields, element types, and implemented methods. Reading values, changing addressable exported fields, checking interface membership, and invoking exposed methods follow the Go 1.26 standard-library reflection documentation for the supplied type, value, member, and arguments. Method enumeration and interface membership cover the native interface roles above, no-argument methods returning a string, and methods taking and returning an integer.

### FP-10: Bundled libraries and automatic imports

- Without fetching external modules, programs can format and scan text; search, compare, split, join, replace, trim, and change the case of strings and byte sequences; classify Unicode characters and convert UTF-8 and UTF-16; parse and format numeric text; quote and unquote text; match, search, and replace using regular expressions; perform real and complex mathematics and arbitrary-precision arithmetic; sort and search ordered collections; and use priority queues, doubly linked lists, and circular lists. Results and input errors follow the Go 1.26 standard-library documentation for the supplied operation, values, patterns, comparison functions, and options.

- Bundled generic operations provide ordered comparison and selection of the first nonzero value; slice equality, comparison, search, membership, insertion, deletion, replacement, cloning, adjacent-duplicate removal, capacity growth and clipping, concatenation, repetition, reversal, sorting, sortedness checks, minima and maxima, chunking, and iteration; and map equality, cloning, copying, conditional deletion, and iteration over keys, values, or entries. Slice and map operations can collect values from iteration, and slice iteration supports forward and backward order. Iterator sequence types carry either one value or a pair per iteration. Generic operations on values yielded by a generic iterator may require explicit type arguments. Concrete or inferred type arguments, supplied collections, predicates, comparison functions, and iterator functions determine results, mutations, and invalid-input failures according to the Go 1.26 standard-library documentation.

- Automatic imports make registered library packages available under their short names during inline command evaluation, interactive sessions, import-path program execution, and package testing. Ordinary source-file execution requires explicit imports. Embedded interpreters require the host to enable automatic imports.

- For automatic-import name collisions, the original pseudorandom-number API takes precedence over cryptographic randomness and the second-generation pseudorandom-number API, text templates over HTML templates, text scanning over Go-source scanning, and runtime profiling over HTTP profiling. Other collisions select the import path with the fewest segments, then alphabetical order. An explicit import overrides an automatic binding, and a user declaration can shadow it.

- Without fetching external modules, programs can buffer, read, write, copy, and scan streams; inspect, create, read, write, and remove files and directories; manipulate slash-separated and host-native paths; construct and inspect errors; parse command-line options; write ordinary and structured logs; measure, parse, format, and wait for times and durations; cancel work through contexts; and coordinate work with locks, wait groups, one-time execution, and atomic operations. Results, mutations, and failures follow the Go 1.26 standard-library documentation for the supplied values, options, streams, files, host resources, and synchronization operations.

- Without fetching external modules, programs can encode and decode JSON, XML, Gob, CSV, ASCII85, Base32, Base64, hexadecimal text, binary numbers with a chosen byte order, ASN.1 values, and PEM blocks, and can render text and HTML templates. Results and invalid-input handling follow the Go 1.26 standard-library documentation for the supplied data types, values, encoded input, byte order, template text, and options.

- Without fetching external modules, programs can compress and decompress DEFLATE, gzip, zlib, and LZW data, decompress bzip2 data, and create and read tar and ZIP archives. Results, supported options, metadata interpretation, and malformed-input failures follow the Go 1.26 standard-library documentation for the selected format, input, entry metadata, and options.

- Without fetching external modules, programs can parse and construct URLs and network addresses, read and construct HTTP requests and responses, perform HTTP client requests, and serve HTTP requests through interpreted handlers. Results and failures follow the Go 1.26 standard-library documentation for the supplied addresses, message contents, handler behavior, and reachable host resources.

- Without fetching external modules, programs can compute SHA-256 digests, HMAC with a caller-selected hash and key, CRC-32 and FNV checksums; encrypt and decrypt using AES in counter mode with the supplied key and initial counter; and derive Ed25519 keys from a seed, sign messages, and verify signatures. Values and invalid-input handling follow the Go 1.26 standard-library documentation for the selected operation and variant, message bytes in supplied order, keys, seed, initial counter, and signature.

- Without fetching external modules, programs can create raster images, inspect and change pixels, draw one image into another, and encode and decode PNG, JPEG, and GIF. Image bounds, pixel access, drawing, and option handling follow the Go 1.26 standard-library documentation for the supplied image, colors, regions, compositing operation, and codec options. PNG round trips preserve pixels; JPEG and GIF round trips preserve dimensions and yield decodable images that keep the drawn content, with the color and precision changes permitted by their selected encoding options.

### FP-11: Source packages and initialization

- Programs can import source packages from a host-supplied source location. Declarations across a package's files resolve together, including forward references and mutually referential types. Import aliases, import-for-initialization declarations, and unqualified imports of functions and types follow The Go Programming Language Specification, language version go1.26, for the supplied package sources and imports.

- Package initialization respects imported-package dependencies and dependencies between package variables; initialization functions run before the importing program's entry function. Shared transitive imports initialize once. These observable effects follow The Go Programming Language Specification, language version go1.26, for the supplied package graph, variable initializers, initialization functions, and source-file order.

- Package-directory loading selects source files whose operating-system and architecture filename suffixes match the selected target and whose build constraints are satisfied. The target platform defaults to the host and can be overridden; the language release is the host Go release. Boolean evaluation of modern and legacy build-constraint expressions follows the Go 1.26 build-constraint documentation; modern constraints take precedence when both forms are present. Target operating-system, architecture, applicable language-release, and Unix-family tags are satisfied, as are the tags purego, safe, and nethttpomithttp2 requesting pure Go, safe source, and omission of HTTP/2. Other tags are satisfied only when added by the caller. Ordinary imports exclude test sources.

- In a loaded source package, a file-embedding directive naming one existing file can initialize a package-level string, byte slice, or named variant of either with that file's exact contents. The file is interpreted relative to the package's source location.

- An import whose package cannot be found fails as an unavailable package. An unresolved cross-file reference in a call or variable initializer fails with the source location of the reference.

- When an imported package has both registered native exports and source files, the registered native package supplies the import. For imports without a registered native package, an available host-supplied package source location takes precedence over bundled library source, which takes precedence over remote module source.

### FP-12: Remote module resolution

- Imports can resolve external Go modules through a configured Go module proxy, including transitive imports and packages below a module root. With no preloaded or locally saved module, resolution obtains the proxy's latest version and evaluates the requested package from that version. Each newly resolved dependency uses its own latest version rather than a version pinned by the importing module.

- When multiple module roots are prefixes of an import path, resolution selects the shortest available prefix whose module contains the requested package. A shorter module that lacks that package does not prevent resolution from a longer module prefix.

- With no proxy preference, Zelviro uses the public Go module proxy at https://proxy.golang.org. In a configured proxy list, only the first non-empty entry is used; later entries are not tried. Selecting off for offline mode or direct for direct-source mode disables network retrieval; direct version-control fetching is not provided.

- If a module or requested package is unavailable and no locally supplied source applies, the import fails as unavailable. A transient proxy failure does not permanently prevent a later lookup in the same resolver from succeeding after service is restored.

### FP-13: Offline module reuse

- Hosts can supply a module archive together with its module identity and version. Files and package directories in that archive become readable without network retrieval; malformed archives are refused as invalid module input.

- Command-line module retrieval persists downloaded modules by default when the configured storage is writable. A later offline process can resolve those saved modules and obtain the same source contents. Users can choose the storage location or select off to disable persistent storage; disabling it prevents module-download writes and use of pre-existing Go module downloads as a secondary source.

- As a secondary source when network retrieval is disabled or version lookup fails, existing Go module downloads can supply a module. Among available ordinary release versions, the highest major, then minor, then patch version is selected. If a version was already saved by Zelviro, that saved choice is retained. Otherwise, a successful proxy version lookup takes precedence over this secondary source's version selection.

- Offline lookup makes no proxy requests.

### FP-14: Process exit and runtime diagnostics

- An interpreted request to exit the process stops evaluation and returns its requested status to an embedding host without terminating that host. Interpreted recovery cannot intercept this exit. Fatal logging likewise stops evaluation and reports an unsuccessful exit.

- An unrecovered panic in the evaluated call chain is reported as a runtime failure carrying the panic cause, offending source location, and interpreted call stack. Nested calls between interpreted and native code retain the interpreted caller locations in the diagnostic.

- An unrecovered panic in a program-created goroutine is reported with its source context and ends ordinary program evaluation as an unsuccessful process exit, including when the main execution is waiting on channel communication.

- Runtime caller and stack inspection from interpreted code exposes interpreted function identities and source locations. Frame sequence includes active interpreted calls. For caller inspection, nonnegative skip counts follow the Go 1.26 runtime documentation. For multi-frame inspection, positive skip counts follow that documentation.

- A goroutine that explicitly terminates itself runs its deferred calls and does not execute subsequent statements in that goroutine. Recovery during this termination observes no panic, following the Go 1.26 standard-library runtime documentation.

### FP-15: Command-line program execution

- Users can execute a local Go source file or a group of Go source files forming one program. A group shares declarations across files regardless of the order supplied. Trailing program arguments reach the interpreted program in their original order.

- A single source file may begin with a shebang line and may omit the package declaration, the entry function, or both. Without an entry function, initialization functions execute and top-level statements execute in source order; with an entry function, program initialization precedes its invocation.

- Inline evaluation accepts an expression or a sequence of declarations and statements. A final expression producing one value displays that value; declarations, assignments, calls returning no value, and calls returning multiple values do not produce an additional result display.

- Users can execute a main program identified by an import path and forward arguments to it. A resolved package with no entry function still performs its initialization and reports that no entry function was run.

- Unreadable local source, rejected source, unavailable imports, and unrecovered execution failures make the command unsuccessful. An interpreted process-exit request determines the command's exit status.

- When both non-empty inline source and a program target are supplied, the inline source is evaluated. Otherwise an existing local target is treated as a file rather than as a remote import path. With neither inline source nor a program target, execution opens an interactive session.

### FP-16: Interactive evaluation

- Interactive sessions accept successive lines from the input stream. Lines producing a value display it. In a fresh session before any global variable exists, declarations producing no value do not add a result display. Session declarations and mutations remain available on later lines.

- For source split between input lines after an opening delimiter, operator, comma, or explicit statement separator, an unfinished parenthesized, bracketed, or braced construct requests continuation. Completing the construct evaluates the accumulated expression or statements.

- A submission containing an undefined function call or an unrecovered ordinary runtime panic is reported as a failure and the session accepts another input. Input accumulated for the failed submission is discarded. End-of-input ends the session.

### FP-17: Package tests, benchmarks, and examples

- Users can run a package's tests from a local directory or a resolvable import path; the current directory is the default target. Local package files are loaded together with build constraints applied, and cross-file declarations resolve regardless of filename order. A local directory with no selected test source is refused as containing no tests.

- A loadable suite can run ordinary tests, subtests, benchmarks, and executable examples. Ordinary tests run in source-declaration order unless the caller selects on for test-order randomization. Randomization chooses a uniformly pseudorandom permutation of the selected top-level tests for each fresh run. Benchmarks run only when explicitly selected and ordinary tests have not failed. Example output is checked against its declared expectation, including unordered output expectations, according to the Go 1.26 testing documentation.

- Users can select or exclude tests by regular-expression name matching, select benchmarks and a fixed benchmark iteration count, request verbose output, repeat execution, choose short mode, and set the overall suite timeout. Without a name filter, all runnable ordinary tests and output-checked examples are selected; repetition defaults to one run. Verbose output identifies individual executed cases and their outcomes, including successful cases. Without verbose reporting, successful cases have no individual execution or outcome reports. Top-level inclusion and exclusion, subtest inclusion, repetition, and short-mode visibility follow the Go 1.26 testing documentation for the supplied options and suite. The default timeout is ten minutes of elapsed suite execution; an explicit timeout replaces it, and zero disables it.

- A package-level test entry function can perform setup, invoke the suite, and control its exit outcome. Tests can open data relative to their package directory, including for an import-path target. Assertions, fatal test failures, example mismatches, and failing benchmarks make the command unsuccessful; a suite with no matching runnable cases reports that distinction.

- Internal tests and a loadable separate external test package can exercise the same imported package. Dependencies are imported without their own test sources.

- For an import-path suite whose implementation loads, a test file directly within the target package containing a call or variable initializer that refers to an undefined name is omitted if the remaining test sources are independently loadable. The remaining suite runs and reports the omitted file and reason, so partial execution is distinguishable from execution of all selected test sources. A source package whose implementation cannot load with its tests excluded fails as an unavailable test target.

- During a package test run, an unrecovered goroutine panic is reported and makes the overall run unsuccessful while allowing other runnable tests to continue. This refines the ordinary program-evaluation behavior for test execution.

### FP-18: Execution tracing and interactive debugging

- Source-line tracing is disabled by default. Users can enable it during ordinary program execution, including nested interpreted calls. Tracing of function bodies invoked as native callbacks, including package-test bodies, is outside this guarantee. The trace identifies executed source locations and text in execution order and distinguishes nested call depths.

- Enabling source-line tracing preserves the program's results and side effects.

- A program can request an interactive debugging stop that identifies its source location. Inspection distinguishes different active call depths and exposes the scalar values held in the active calls. The association with parameter positions and variable names is outside the guarantee. Users can continue execution from the stop; unrecognized debugger input leaves the program stopped, and end-of-input resumes execution.

- During ordinary command-line execution, one interrupt requests an execution-state report while the program continues. A second interrupt less than one second after the previous interrupt terminates the command.

- Users can request execution statistics that distinguish elapsed source-processing and execution time, proxy request count and response bytes, locally reused module archives and their byte sizes, and newly persisted module archives. Each module version query or archive retrieval attempt counts once; response bytes count the data read from successful proxy replies. Local reuse counts each distinct module archive already available in persistent storage at invocation start and used during that invocation once, and sums its archive byte size; persistence counts each distinct downloaded module archive successfully saved during the invocation once. Archive byte sizes refer to the ZIP payload obtained from the proxy or supplied by the host, independent of its local storage representation. Elapsed times are wall-clock durations. Source-processing duration includes waits for dependencies needed by the supplied source; execution duration includes waits in its initialization and executed calls. Each reported duration must lie between the time independently observed waiting within its phase and the total invocation duration minus time independently observed waiting in the other phase, allowing only the rounding of its printed duration.

### FP-19: C host embedding

- A C host can create an interpreter, evaluate labeled Go source, and receive a printable result or a separate evaluation error. The host can reuse the interpreter across evaluations with retained program state.

### FP-20: Native package binding generation

- An embedder can select a native Go package and generate Go binding source that exposes its exported non-generic variables, types, functions, and constants representable as native Go values to interpreted imports. The generated bindings preserve typed constants, callable signatures, native type identity, and access to mutable native variables.

- Package selection accepts an import path or a local package selection and can use an explicitly supplied source directory. The result uses the package's canonical import identity and declared package name, including when that name differs from the final path component. Users can choose the generated source's destination and enclosing package.

- Discovery excludes unexported declarations and generic-only declarations that cannot be bound as native values. Source selection honors the requested operating system and architecture build constraints. An empty export set still produces compilable binding source.

- Users can request an inventory of exported constants, variables, types, and functions instead of generated bindings. Missing required input, a package selection resolving to multiple packages, an unresolvable package, or an unwritable output destination fails with a diagnostic identifying the failed selection or output operation.
