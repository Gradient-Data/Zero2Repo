# Velora — Full Product Requirements

Velora is an optimising Python compiler for creating native Python extensions and integrating Python applications with C and C++ code.

### FP-01: Source translation and compilation diagnostics

- Given Python source or Velora source, Velora produces C source by default and C++ source when requested. With the matching Python development files and native toolchain, the generated source can be built into a native extension that Python can import and execute without the original Python or Velora source being present.

- Malformed language syntax, references to undeclared native types, and assignments between incompatible native types make translation fail. The diagnostic identifies the source location responsible for the failure.

- A missing input source or unresolved requested declaration or source inclusion makes translation fail with an observable indication of the missing input. An unrecognised compilation option or invalid value for a recognised option is refused as invalid configuration.

- Compilation settings can be supplied for a build, a source file, and eligible local scopes. Explicit source-file settings override build defaults and conflicting command-line settings; command-line settings apply where the source file supplies no setting. Explicit local settings override enclosing settings, including command-line settings. A local override affects only its declared scope.

- Statements following an unconditional return in the same source block produce an unreachable-code warning by default. Disabling that warning allows otherwise valid source to translate without it. With the warning enabled, ordinary translation succeeds with a warning, while requesting warnings as errors makes the same source fail translation.

### FP-02: Python execution in native extensions

- For dynamically typed code using assignment, arithmetic, comparisons, Boolean operations, branching, loops, comprehensions, sequence unpacking, indexing, slicing, and imports, compiled execution preserves the values and mutations required by the Python 3.12 Language Reference and Library Reference for the supplied source, input objects, imported objects, and initial application state. Supported builtin values include integers, floating-point and complex numbers, Boolean values, Unicode text, immutable and mutable byte sequences, mutable lists, tuples, mappings, mutable sets, and immutable sets.

- Python-callable routines preserve positional arguments, keyword arguments, defaults, variable argument collections, positional-only restrictions, and keyword-only restrictions declared by the source. Calls with missing required arguments, duplicate arguments, unexpected arguments, or forbidden positional or keyword use fail as invalid calls, according to the Python 3.12 Language Reference for the supplied routine declaration and call.

- Compiled ordinary Python classes, closures, decorators, inheritance, and dynamic attribute access retain the behaviour specified by the Python 3.12 Language Reference for the supplied definitions, captured values, base classes, and operations. By default, a compiled Python routine attached to a Python class binds to the instance when accessed through that instance; disabling routine binding makes that attachment remain an unbound callable.

- Compiled generators, delegated generators, coroutines, asynchronous generators, and synchronous and asynchronous context managers preserve the behaviour specified by the Python 3.12 Language Reference for the supplied definitions and sequence of driving operations.

- Exceptions raised by Python operations or explicitly by the application reach matching application handlers, and cleanup clauses execute when control leaves their protected scope. An uncaught exception retains its meaning and identifies the original Velora or Python source location in its traceback.

- The default language level uses Python 3 division and Unicode text literals. The selectable legacy language level accepts the Python 2 print statement and gives division between statically declared native integer operands an integer result rounded down; the Python 3 level gives true division. Both Python 3 language-level selections have the same behaviour in this release.

### FP-03: Native values and checked Python conversions

- Callers can declare native Boolean values; ordinary, signed, and unsigned character values; signed and unsigned short, ordinary, long, and long long integers; single, double, and extended-precision floating-point values and corresponding complex values; and integers suitable for memory sizes, Python container sizes, Python hashes, and Unicode code points. For arithmetic and comparisons defined by the standard for the supplied operand types, with operands and results representable in the declared types, native operations follow ISO/IEC 9899:2018 on the target platform, except for the division, remainder, and checked-overflow policies stated below. Native Boolean conversion uses the input object's truth value. Native numeric results become the corresponding Python Boolean, integer, floating-point, or complex values at a Python-facing boundary. Unicode code-point values instead become single-character Unicode text. Numeric arithmetic on code-point values is covered after explicit conversion to an ordinary native integer type; direct operations on the character type are not covered by the numeric arithmetic guarantee.

- Converting a Python integer into a native integer preserves its value when it fits the target type's signedness and width. For ordinary native integers and memory-size integers, numeric objects with integer-conversion behaviour can supply that integer value; finite floating-point values lose their fractional part toward zero. Container-size and hash integers instead require integer-index behaviour and refuse floating-point values and objects offering only integer conversion. Unicode code-point inputs accept single-character Unicode text or numeric integer conversion, with the converted integer in the inclusive range 0..1114111; a numeric value outside this range fails as numeric overflow. Text and byte strings are not parsed as numbers. Values outside the target integer range fail as numeric overflow, and objects without integer-conversion behaviour fail as incompatible values. Python integers and floating-point numbers convert to native floating-point values at the target precision; Python complex values convert their real and imaginary components at the target complex precision. Untyped integer arithmetic retains arbitrary-size Python integer results by default.

- Callers can define type aliases, fixed-size native arrays, pointers, structures, unions, enumerations, and tuples with individually typed native elements. Assigning and reading valid array elements, pointed-to values, structure members, and typed tuple elements preserves the assigned values. A fixed-size native array requires a size known from the supplied declarations; a runtime-variable size is refused as an invalid declaration.

- Python mappings can supply structures when every declared member is present and its value is convertible to the member type; a missing member fails as an incomplete structure, and a member conversion failure retains its conversion meaning. Returning a native structure whose members have Python conversions preserves its members and converted values. Python iterables can supply fixed-size native arrays when their element count and element conversions match the declaration. Python sequences can supply typed native tuples when their length and element conversions match the declaration. An incompatible count fails as an incorrect element count; an element conversion failure retains its conversion meaning. Returning an ordinary numeric native array or a typed native tuple preserves its element order and converted values.

- For non-null values, assignment to a statically declared builtin mutable list, tuple, mapping, mutable set, immutable set, Unicode text, immutable byte sequence, or mutable byte sequence requires that exact builtin type rather than a subclass. A C-style declaration permits a null object unless explicitly forbidden; a plain Python argument annotation refuses a null object unless optionality or a null default permits it. These nullability rules take precedence over the exact-type restriction.

- Source-defined native enumeration member values follow ISO/IEC 9899:2018 for the supplied member declarations and declaration order. An enumeration requested for Python access preserves those member values. A named enumeration exposes its members through the enumeration without also creating global member constants; an anonymous enumeration exposes its members as global constants.

- Native integer arithmetic can be requested to detect overflow; enabled checking turns an out-of-range addition, subtraction, or multiplication result into a numeric-overflow failure. Overflow checking is disabled by default. With checking disabled, unsigned arithmetic also preserves the modular results specified by ISO/IEC 9899:2018 when the mathematical result exceeds the unsigned result type's range. By default, native integer floor division and remainder follow the Python 3.12 Language Reference for the supplied operands. For nonzero divisors and representable results, the selectable C-division behaviour follows ISO/IEC 9899:2018 integer division and remainder for the supplied native operands. Selecting C division takes precedence over language-level division rules for native integer operands.

- Source-defined numeric, pointer-valued, and Python-object module variables without explicit initial values start at numeric zero, a null pointer, or a null Python object respectively. Initial values explicitly supplied by the source replace those defaults.

### FP-04: Native callable boundaries and error propagation

- Source authors can define Python-callable routines, native-only routines, and routines callable through both boundaries. Native-only routines can be used by compiled callers without becoming Python module attributes. Python-facing calls perform the declared argument and return conversions; a native argument type without a Python conversion is refused on a Python-facing routine.

- Native routines support caller-declared optional arguments and calls through compatible native callable pointers. Omitted optional arguments use the defaults supplied by the defining source. Incompatible argument types, return types, or exception declarations make a native callable-pointer assignment fail as an incompatible declaration.

- A Python exception raised by a non-external native routine propagates to its caller by default. Authors can reserve a native return value for failure, designate a value that denotes failure only while a Python exception is present, or require exception propagation independently of the returned value. In the conditional case, an ordinary return of the designated value without an exception remains a successful result.

- If an author explicitly disables exception propagation for a native routine, an exception escaping that routine is reported as unraisable and does not become a catchable exception in its caller.

- A routine parameter or result without a declared type is a Python object. When a routine completes normally without an explicit return value and its default result is not unconditionally reserved for failure, a Python-object result is the null Python object, a native numeric result is zero, a native Boolean result is false, and a pointer result is a null pointer.

### FP-05: Python extension types

- Source authors can define Python-instantiable extension types with declared native and Python-valued attributes and callable behaviour. Declared attributes are hidden from Python attribute access by default; attributes exposed for reading and writing permit both operations, while attributes exposed only for reading refuse Python assignment. Compiled code with the declared instance type can read and write its native attributes. Unassigned numeric, pointer-valued, and Python-object attributes have zero, a null pointer, and a null Python object respectively.

- Extension instances refuse assignments that add undeclared attributes by default. Explicitly enabling dynamic attributes permits such assignments, and ordinary Python subclasses can have dynamic attributes.

- Extension properties execute the user-supplied behaviour for reads, writes, and deletions. Attempting an operation for which the property supplies no behaviour fails as unavailable attribute access.

- Extension types can inherit from another extension type and can be subclassed by ordinary Python classes. Overridden native methods dispatch to the derived extension implementation; methods exposed through both Python and native boundaries honour a Python subclass override even when called by compiled code. An extension type cannot combine two extension-type bases that would introduce incompatible native instance layouts.

- Extension types can implement Python arithmetic, reflected arithmetic, comparison, conversion, iteration, item access, and context-management protocols. The user-supplied protocol behaviour determines the values and side effects of the corresponding Python operations; ordinary and reflected arithmetic implementations receive their declared operand roles.

- Native instance initialisation runs once for an allocated extension instance, including when normal Python initialisation is bypassed. On ordinary instance destruction, user-supplied native cleanup runs. Python object references owned by extension instances remain valid while referenced. Once a cycle of such references is otherwise unreachable, an explicit full Python garbage collection releases it before collection returns, provided its objects do not resurrect themselves.

- Assigning a non-null object to a declared extension type accepts that type and its subclasses and refuses unrelated objects. An explicitly checked cast refuses unrelated objects and null objects. C-style declarations permit a null object unless explicitly forbidden; a plain Python argument annotation refuses null unless optionality or a null default permits it.

- Extension types can expose caller-supplied native storage through the Python buffer protocol. A consumer obtains the authored element type, shape, strides, and read-only or writable access; writes through a writable consumer change the original storage. Buffer acquisition and release invoke the corresponding authored behaviour, and a refusal raised by that behaviour reaches the requesting consumer.

### FP-06: Reusable declarations and cooperating extensions

- A caller can provide shared native type, variable, callable, and extension-type declarations for use by separately compiled Velora modules. Consumers can use the declared native values and call the declared routines, and can access or derive from shared extension types.

- A declaration collection containing only external declarations can be used without a corresponding importable Python implementation. Importing native declarations does not itself make unrelated Python objects from the declaring module available; ordinary Python object access requires its own Python import.

- Inconsistent native callable declarations and definitions, and undeclared additions to the native attributes of an extension type whose attributes are supplied by a companion declaration, make translation fail. These declaration failures identify the responsible source location, including when a requested shared declaration is missing.

- Callers can include reusable Velora source fragments and resolve declaration collections from their configured search locations, including Python packages and namespace packages. The included source contributes its definitions and executable behaviour to the including source. If a search location offers version-tagged declarations, the highest version not exceeding the running Velora version is selected within the first search location offering a compatible declaration.

### FP-07: Pure Python mode

- Authors can express native scalar declarations, native callable declarations, and extension types using valid Python source with Velora annotations and decorators. Compiling that source gives the declared Velora behaviour. For ordinary Python scalar, container, and callable operations that need no foreign declarations or native pointer access, the same source can also run under the Python interpreter with Velora's runtime support.

- Authors can add native declarations through a companion declaration file while leaving the Python implementation source unchanged. The compiled routine or extension type uses those declarations, including its declared Python visibility; incompatible declarations and implementations are refused.

- Code can distinguish compiled execution from interpreted execution through Velora's compilation-status indication. It indicates compiled execution in a native extension and interpreted execution when the original Python source is interpreted.

- Python type annotations are used for supported static argument types by default: Boolean, arbitrary-size integer, floating-point and complex numbers, Unicode text, immutable and mutable byte sequences, mutable lists, tuples, mappings, mutable and immutable sets, and declared extension types. Plain Boolean annotations apply truth-value conversion. Plain floating-point annotations accept real numeric conversion to double precision, and plain complex annotations accept real or complex numeric conversion to double-precision complex values; text, byte strings, and null objects are refused by these real or complex conversions. A Python integer annotation applies integer conversion without imposing a native fixed width, discards finite floating-point fractional parts toward zero, and refuses text, byte strings, and null objects. Passing a builtin container to an annotated argument does not validate or convert its individual elements according to the element annotation. Disabling annotation-based typing leaves these annotations from imposing argument type restrictions.

### FP-08: C interoperability and exported native APIs

- Given matching declarations, native headers, and linked C definitions, compiled Velora code can call external C routines, read and update external variables and structure members, use external constants, and pass native arrays and pointers. Python-visible results and mutations reflect execution of the supplied C implementation. Declarations may describe only the structure members used by the Velora source.

- Reusable native declarations allow callers to perform mathematical operations, allocate and release memory, operate on native byte strings and memory regions, and use standard file input and output as specified by ISO/IEC 9899:2018 for the supplied arguments and local resources. They also allow file-descriptor input and output and process-identity queries as specified by POSIX.1-2017 on Linux, and creation and manipulation of Python numeric and container objects through the CPython 3.12 C API Reference for the supplied objects and arguments. These uses require no user-written copy of the corresponding native declarations. Authors can also supply native source text alongside its declarations and use the definitions it contributes.

- Binary strings can cross Python and native character-string boundaries as bytes, without implicit text decoding by default. Explicitly length-delimited conversions preserve embedded zero characters; conversions requesting a zero-terminated string stop at the first zero character. For explicitly requested UTF-8 text conversion, encoding operates on the supplied Unicode text and decoding operates on the supplied byte sequence according to RFC 3629; malformed input is refused as an encoding or decoding failure.

- Authors can export native types, variables, and routines for use by C code linked with the generated extension, and can expose native routines and extension types to independently built C consumers after importing the defining Python extension. The exported declaration material lets those consumers execute the supplied behaviour with the declared native argument and result types.

### FP-09: C++ interoperability

- With C++ output selected and the required declarations and native definitions supplied, Velora code can construct and destroy C++ objects, access declared members, call overloaded routines, use declared operators and inheritance, and instantiate declared templates. The returned values and externally visible object state reflect the selected C++ operations. C++-only declarations used with C output are refused as requiring C++ support.

- Python immutable byte sequences convert to C++ strings and back without losing embedded zero characters. Python iterables convert to C++ vectors and linked lists preserving element order, and to ordered or unordered C++ sets preserving their distinct converted elements. Python mappings convert to ordered or unordered C++ maps preserving their converted keys and values. A Python iterable of exactly two convertible elements converts to a C++ pair, preserving the element order and converted values in either conversion direction. A pair input with a different element count fails as an incorrect element count. Python complex numbers convert to corresponding C++ complex numbers and back. Element, key, and value conversions apply recursively to nested containers; incompatible values fail as conversion errors. A converted container retains its converted contents independently of later source-container mutations, in either conversion direction.

- Declared C++ containers can be iterated in Velora, exposing the values supplied by their native iteration. C++ objects stored as extension-instance values remain alive for the owning instance's lifetime and are destroyed with it; explicitly allocated objects can be explicitly destroyed by the source author.

- For C++ calls explicitly declared to translate exceptions, native allocation failures, invalid arguments or domains, out-of-range access, numeric overflow, numeric range or underflow, type-conversion failures, and I/O failures become Python failures of the corresponding meaning. Other native exceptions become general runtime failures, preserving the native explanatory message when available. An explicitly supplied exception translator determines the Python failure instead.

### FP-10: Typed memoryviews and shared buffer access

- Typed memoryviews accept buffer-exporting Python objects with a matching declared element type, dimension count, access layout, and mutability. They also expose matching caller-owned native arrays. With default compilation limits, declarations with one through seven dimensions are supported and declarations with eight or more dimensions are refused as exceeding the dimension limit. Incompatible buffer element types or dimension counts are refused as incompatible buffers.

- Reading and writing a view's indexed elements observes and changes the corresponding original buffer elements. Slicing, reversing a slice, transposing direct-access dimensions, and inserting unit-length axes produce views of the corresponding data; writes through writable derived views remain visible in the original buffer. A view keeps its exporting Python object alive while that object is needed for access.

- Unconstrained view dimensions accept directly strided data by default. Authors can require C-contiguous, Fortran-contiguous, individually contiguous, indirect, or generic direct-or-indirect dimensions. A buffer that violates the requested contiguity or access layout is refused as an incompatible layout; pointer-valued buffer elements are outside the supported element types.

- A read-only view accepts either a writable or read-only buffer and refuses writes through that view. A writable view refuses a read-only exporter as an incompatible writable buffer.

- View indexing checks bounds and interprets negative indices relative to the end of their dimensions by default. An index outside its dimension is refused as out-of-range access. Access through an uninitialised view is refused as uninitialised access by default. Authors may explicitly disable these checks for code whose accesses satisfy their preconditions.

- Assigning a scalar to a writable direct-access view fills its selected elements. Assigning a direct-access view of the same declared element type copies corresponding values; trailing dimensions align, absent leading dimensions count as length one, and each source dimension must equal its destination dimension or have length one. A length-one source dimension repeats its element values along that destination dimension. Incompatible shapes are refused as incompatible assignment. If source and destination overlap, the assigned values are those selected from the source before the assignment. Requesting an independent C-contiguous or Fortran-contiguous copy preserves the selected values and produces storage independent of later source mutations.

- A Python-facing view exposes its dimension lengths, strides, element size, element count, total byte count, and original exporting object consistently with the data it selects. A Python consumer can obtain buffer access to the selected data with its declared shape, element type, and mutability.

- Callers can create an owning writable buffer for a supplied nonempty shape of positive dimension lengths and a positive element size with a matching element declaration. Its layout is C-contiguous by default or Fortran-contiguous when selected. Written elements can be read and shared through typed views without NumPy. An empty shape, nonpositive dimension length, nonpositive element size, or unsupported layout selection is refused as invalid buffer configuration.

### FP-11: Fused types and generic native routines

- Authors can declare a finite choice of native or Python types and write one routine over that fused type, including typed memoryviews and pointers whose element type is fused. Each supported type choice executes the behaviour authored for that type. Repeated occurrences of the same fused declaration share one type choice; distinct fused declarations permit independent choices.

- Callers can explicitly select an available specialisation and inspect which specialisations are available. Compiled calls with known native argument types use an exact match when offered, and accept a numeric conversion when there is only one declared alternative. For Python calls offering only native numeric alternatives, an integer, floating-point, or complex argument selects the widest declared alternative of that same numeric family when that family is offered. For buffer arguments whose alternatives have distinct element types, selection uses the buffer's element type. A call matching no declared alternative is refused as incompatible arguments, and an unavailable explicit selection is refused as an unavailable specialisation.

- The predefined integral choice comprises short, ordinary, and long signed integers; the predefined floating choice comprises single and double precision; the predefined numeric choice comprises those integral and floating alternatives plus single-precision and double-precision complex values.

- Source behaviour can depend on the selected type, allowing operations that are valid only for that type without requiring the operations belonging exclusively to unselected type branches to be valid. Using a fused type as an extension-instance attribute is refused as an unsupported declaration.

### FP-12: Cooperation with Python threads

- An explicitly declared region that releases the Python interpreter lock can perform native arithmetic, compatible native calls, and non-object typed memoryview access while other Python threads continue executing. During uninterrupted native work that retains the lock, other Python threads cannot execute Python operations. Declaring a routine safe for use without the lock does not itself release a lock held by its caller.

- Native code can explicitly regain permission to perform Python operations inside a region that otherwise runs without the interpreter lock, including callbacks entered by a native thread. The Python operations execute their normal application behaviour and exceptions can propagate through an exception-enabled native boundary.

- Python object manipulation and calls declared to require the interpreter lock are refused in an explicitly unlocked region unless the source explicitly restores permission. Explicit application exception raising is supported in such a region and reaches the caller as that Python failure.

- Authors can choose whether a region releases or acquires the interpreter lock using a condition fixed by the source declarations. The selected condition determines whether other Python threads can progress during uninterrupted native work in that region; a condition requiring a runtime value is refused as invalid configuration.

### FP-13: Parallel native computation

- With native parallel build support enabled, authors can request parallel execution of independent native loop iterations, including loops writing disjoint array elements. Each iteration contributes its authored result. Supported scalar reductions are addition, multiplication, subtraction, bitwise conjunction, bitwise disjunction, and bitwise exclusive disjunction, with the supplied initial accumulator contributing to the combined result.

- On a Linux host providing four otherwise idle physical CPU cores and a native toolchain supporting parallel builds, a fixed four-worker job of independent, compute-bound native arithmetic iterations with negligible I/O and sufficient work to dominate startup completes in no more than 80% of the elapsed execution time when the same process is restricted to one core. This relation concerns median elapsed computation time over repeated executions of the same built extension, input, and settings; only the CPUs available to the process differ.

- Parallel-loop configuration accepts scheduling selections, nonnegative worker counts, and a Boolean parallel-execution condition. Under each accepted configuration, including a false condition, complete independent iterations and reductions preserve their authored results. A source-constant negative worker count or nonpositive chunk size is refused as invalid parallel configuration. A chunk size is refused with runtime-controlled scheduling or without an explicit scheduling selection.

- Native intermediate values assigned within a parallel region do not let one independent computation overwrite another's values. Explicitly permitted Python operations within the region retain their authored effects. When one iteration raises an exception and no iteration requests a competing early exit, the loop does not report normal completion and the Python failure reaches the caller. An unprotected operation requiring the interpreter lock is refused inside the parallel region.

### FP-14: NumPy arrays and generated ufuncs

- With NumPy and its development headers available for native NumPy declarations, compiled code can accept typed NumPy arrays, inspect their dimensions, and read and write declared numeric elements while preserving changes in the original array. Arrays with an incompatible declared element type or number of dimensions are refused as incompatible arrays.

- Authors can expose a scalar native routine as a NumPy ufunc with numeric or Python-object inputs and outputs. Input shapes broadcast when corresponding trailing dimensions are equal or one, treating missing leading dimensions as length one. Equal lengths give that output dimension its shared length; unequal compatible lengths give it the non-one length. Each output element is the supplied scalar behaviour applied to the corresponding input elements, repeating an input along dimensions of length one. Incompatible shapes are refused. A native tuple return produces one output array for each tuple element. Fused scalar declarations provide the declared alternative element-type operations.

- A generated ufunc whose scalar routine is declared safe without the interpreter lock permits other Python threads to progress during substantial non-object numeric work, even when its caller holds the lock. Non-scalar array arguments in the defining scalar routine are refused as an unsupported ufunc declaration.

### FP-15: Project builds and dependency-aware regeneration

- A user can translate multiple selected sources, including selections by wildcard and exclusions, and build them as importable extensions using the command-line build frontend or Python build integration. Package-qualified modules retain their intended import identity. A selected source pattern matching no files is refused as a missing build input. Requesting quiet translation through Python build integration suppresses compilation progress reports.

- Build descriptions can supply native include locations, declaration search locations, additional C or C++ sources, native libraries, and native compiler and linker settings. Those inputs participate in the resulting extension build. Missing required native headers, missing required libraries, or native compilation failures prevent a successful build and expose the native build failure.

- An incremental build started in a fresh Python process regenerates an extension's native source when its Velora source or a transitively used declaration or included source becomes newer than the generated source. Explicitly forcing translation regenerates the source even when it is up to date. Requested dependency output identifies the source and declarations or included sources needed to regenerate each translation result.

- Generated C and C++ sources can be distributed and built into working Python extensions on a compatible target with Python development files and the required native dependencies, without Velora being installed on that target.

### FP-16: Import-time compilation

- After a user enables import-time compilation, importing a discoverable Velora source builds and loads its native extension for normal Python use. Source translation failures and native build failures prevent the import and remain distinguishable from successful loading. An exception raised by the module's own execution makes the import fail rather than returning a usable module, and the original application exception type and arguments remain accessible as exception information.

- Import-time compilation can use user-declared source dependencies and custom native build descriptions. A newer declared dependency makes a subsequent fresh import rebuild the extension; the imported behaviour reflects the changed source or dependency. Disabling the installed import support removes its source-compilation behaviour from subsequent imports.

### FP-17: Interactive native compilation

- A Python caller can compile a supplied fragment and execute it with explicitly supplied values and otherwise unbound values from the surrounding local and global scopes. Explicitly supplied values take precedence over surrounding locals, and surrounding locals take precedence over surrounding globals. An explicit return delivers the returned value; without an explicit return the caller receives the local values defined by the fragment. An invalid fragment fails as a compilation error and does not deliver a successful result.

- Callers can select an ordinary Python routine without explicit native argument declarations and call it with differing applicable argument types, preserving its Python-facing results and application side effects. When an argument is an extension instance with shared native declarations, the routine can access attributes supplied by those declarations, including attributes hidden from ordinary Python access, across successive calls with differing extension types.

- In an IPython session, including a session used by a local notebook, users can compile and execute a source cell and use its Python-visible definitions in the session. The cell has its own imported dependencies; an undeclared external name is refused rather than implicitly resolved from an earlier cell. Users can supply native include, source, library, and C++ build requirements for the cell. A failed compilation exposes the failure without publishing successful definitions from that failed build; previously published objects remain bound to their existing session names.

### FP-18: Source annotation for optimisation

- On request, translation produces an annotated view of the supplied source that distinguishes lines with Python runtime interaction from lines consisting of native operations. A user can inspect the generated C or C++ corresponding to a source line. A user can also request the complete generated native source.

- When source coverage results are supplied for annotation, the annotated source distinguishes executed source lines from source lines with no recorded execution according to those results.

### FP-19: Runtime profiling and source-level debugging

- On CPython 3.11, enabling profiling for compiled routines makes their executions visible to Python profiling tools with routine identity, call counts, and caller relationships. A routine explicitly excluded from profiling does not contribute its own profiled calls, even when its surrounding source enables profiling.

- On CPython 3.11, with line tracing and its native build support explicitly enabled, executed Velora source lines produce tracing events that allow source coverage tools to distinguish executed and unexecuted lines. Work performed without the interpreter lock is included only when tracing of such work is explicitly enabled. Profiling and tracing are disabled by default.

- On CPython 3.11, with an unoptimised native build, exported Velora debugging information, native debugging symbols, and GNU Debugger 7.2 or later built with Python support, a user can stop at Velora source locations, step into or over calls between compiled Velora routines, inspect the relevant stack and source location, and read native scalar local values at the stopped location.

- In a stopped debug session under these conditions, a user can select a relevant compiled frame, assign a type-compatible value to a native scalar local variable, or execute Python expressions using that frame's initialised Python-object locals and its module's Python globals. Expressions follow the Python 3.11 Language Reference for the supplied expression, these objects, and module state, with those locals taking precedence over module globals for an unqualified name. Resuming execution observes assignments made through the native-variable assignment facility and mutations of shared Python objects made by evaluated expressions. Evaluating an invalid expression exposes its evaluation failure.

### FP-20: Embedding compiled modules in native applications

- Given Python development files and the native toolchain, a user can request generated application entry support and build a Velora main module into a native executable. Running the executable executes that module as the main program with access to command-line arguments and the supplied Python runtime environment. An uncaught application exception is reported and makes execution unsuccessful.

- A main executable can include additional compiled Velora modules named by the user. When their native objects are linked into the executable, the main module can import and use them without separate extension files for those modules.

- Embedded execution uses an installed Python runtime and imports dependencies from the supplied runtime environment. An unavailable imported dependency causes an import failure.
