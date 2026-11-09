# Interface Contract

The product is available from the Python import root as `Velora`, `velora`, and `veximport`. Commands are invoked with the selected Python interpreter using `-m velora` or `-m Velora.Build.Veloraize`. Source and output arguments can name absolute paths; invocation does not require changing into the source directory.

Source files and generated annotation and native-source text use UTF-8. Imported extensions use ordinary Python module imports and the source-declared names, argument lists, attributes, and return objects. Application output goes to `stdout`; compilation diagnostics and uncaught exception reports go to `stderr`.

Native extensions are importable under their module name, including a package-qualified `__name__`, from the requested build directory. The extension filename uses the active Python platform extension suffix.

## `python -m velora`

Invocation: `<python> -m velora [<options>] <source-path>`. The source path names a `.py` or `.pyx` input. The generated native source is adjacent to that input and has the same stem, with suffix `.c` or `.cpp` according to the requested output mode.

The used options are `--cplus` (C++ output), `-3` (language selection), `-I <directory>` (declaration and include search location; repeatable), and `-X <name>=<value>` (directive assignment; repeatable). A directive argument can contain comma-separated assignments. Boolean directive values are written `True` or `False`.

`--warning-errors` selects the fatal-warning interface. `--annotate`, `--annotate-fullc`, and `--annotate-coverage <XML-path>` request annotation files. `--gdb-outdir <directory>` selects the debug-information output directory. `--embed` requests executable entry support; `--embed-modules <module-list>` supplies additional module names separated by commas.

Exit status `0` denotes successful translation, `1` denotes translation failure, missing compilation input, or invalid directive configuration, and `2` denotes an unrecognised command option. Diagnostics are text on `stderr`. A location-bearing diagnostic contains a line of the form `<source-path>:<line>:<column>: <explanation>`; a warning uses `warning: <source-path>:<line>:<column>: <explanation>`. The source line is one-based and the column is a nonnegative integer. Explanations are nonempty human-readable text. A missing-input diagnostic carries the missing source, declaration, or inclusion name. A successful invocation with no emitted diagnostics has empty `stderr`.

Directive names passed through `-X` are `binding`, `language_level`, `cdivision`, `overflowcheck`, `warn.unreachable`, `profile`, and `linetrace`. `language_level` uses `2` for the legacy level and `3` or `3str` for the Python 3 levels. The Python build interface accepts numeric selectors as integers or strings and `3str` as a string; the other listed settings use Boolean values.

## `Velora.Build.veloraize`

Import with `from Velora.Build import veloraize`. Used call shape: `veloraize(module_list, exclude=<patterns>, quiet=<bool>, force=<bool>, compiler_directives=<mapping>, include_path=<directories>, depfile=<bool>)`, with only the needed keyword arguments supplied. `module_list` is a source-path string, a list of source-path or glob-pattern strings, or a list of `setuptools.Extension` objects. `exclude` is a list of pattern strings, `compiler_directives` maps directive names to Python values, and `include_path` is a list of declaration-directory strings.

The return is a list of extension descriptions accepted as `ext_modules` by `setuptools.setup`. Generated native sources are named beside their source inputs with `.c` or `.cpp` suffixes. `quiet` is the Boolean quiet-mode selector. Compilation progress reports use `stdout`.

Invalid build configuration and missing source-pattern selections raise `ValueError`.

## `python -m Velora.Build.Veloraize`

Invocation: `<python> -m Velora.Build.Veloraize -i [-x <excluded-pattern>] <source-pattern> ...`. `-i` requests extensions beside the selected sources. `-x` supplies an exclusion pattern. Source selection accepts glob-pattern arguments.

Successful project compilation exits `0`. A missing source selection exits `1` and reports the missing selection on `stderr`.

## `setuptools.Extension`

`from setuptools import Extension`. Used constructor: `Extension(name, sources=<paths>, include_dirs=<paths>, library_dirs=<paths>, libraries=<names>, define_macros=<pairs>, extra_compile_args=<arguments>, extra_link_args=<arguments>, language=<language>)`; keyword construction with `name` is also used. `name` is the module import name, `sources` lists source filenames, directory and library fields are lists of strings, `define_macros` contains `(name, value)` string pairs, and compiler/linker fields contain argument strings. `language` is the native-source language selector, including `c++`. Only the needed keywords are passed.

## `setuptools.setup`

`from setuptools import setup`. Used call: `setup(ext_modules=<extensions>, script_args=<arguments>)`, or `setup(ext_modules=<extensions>)` with command arguments supplied to the Python script. The command is `build_ext --build-lib <directory> --build-temp <directory>`, optionally with `--force`. `ext_modules` is a list of extension descriptions; `--build-lib` names the importable output root and `--build-temp` names the native intermediate-output directory.

The build process exits `0` on success. A native build failure exits nonzero and emits diagnostic text on `stderr`.

## `.pyx`

A `<module>.pyx` file contains Python source and native declarations. Native syntax includes `cdef <type> <name>`, `ctypedef <type> <name>`, pointer declarators `*`, address expressions `&`, fixed array declarators `<name>[<size>]`, `struct`, `union`, `enum`, `cpdef enum`, typed tuples `(<type>, ...)`, `sizeof(<type>)`, `NULL`, casts `<type><expression>`, and checked object casts `<type?><expression>`. Identifiers, member names, dimensions, and initialisers are supplied by the source author.

Callable declarations use `def <name>(<parameters>):`, `cdef <result-type> <name>(<parameters>):`, or `cpdef <result-type> <name>(<parameters>):`. Parameter declarations may use `<type> <name>`, `<type> <name> not None`, Python annotations, and source-defined defaults. Native function-pointer syntax is `<result-type> (*<name>)(<parameter-types>)`. Exception annotations are `except <value>`, `except? <value>`, `except *`, and `noexcept`. Native declarations and blocks use `nogil`, `with nogil:`, `with gil:`, `with nogil(<condition>):`, and `with gil(<condition>):`; a native callback declaration may end in `with gil`.

Extension declarations use `cdef class <name>[(<base>)]:`. Attribute forms are `cdef <type> <name>`, `cdef public <type> <name>`, `cdef readonly <type> <name>`, and `cdef dict __dict__`. A legacy property is `property <name>:` containing `def __get__(self)`, `def __set__(self, value)`, or `def __del__(self)`. Python attribute access uses the declared attribute name; unavailable attribute access raises `AttributeError`. An unavailable property deletion may instead raise `NotImplementedError`. Incompatible extension-type inheritance is signalled by `TypeError` at Python class construction.

Native integration declarations use `cdef extern from "<header>":` or `cdef extern from *:` with an embedded native-source string. External declarations can include native variables, callable prototypes, enums, structs, and `cppclass <name>[(<base>)]` with overloaded constructors, methods, members, operators, and template parameters `[<type-parameters>]`. Native aliases use `<local-name> "<external-name>"`. C++ construction and destruction syntax includes `new <type>(<arguments>)` and `del <pointer>`. Exception translation declarations use `except +` or `except +<translator>`.

Fused declarations use `ctypedef fused <name>:` followed by type declarations. Fused arguments use the declared type name, including pointer and memoryview forms; type tests use `<fused-name> is <type>`.

File directives are header comments of the form `# velora: <name>=<value>[, ...]`. Boolean values use `True` and `False`. Local directives are decorators `@velora.<name>(<value>)` or scoped statements `with velora.<name>(<value>):`.

Native scalar spellings include `bint`, `char`, `signed char`, `unsigned char`, `short`, `unsigned short`, `int`, `unsigned int`, `long`, `unsigned long`, `long long`, `unsigned long long`, `float`, `double`, `long double`, and the corresponding real-type spellings followed by `complex`. Python-related native names include `Py_ssize_t`, `Py_hash_t`, and `Py_UCS4`; Python-object declarations include `object`, `unicode`, and builtin container types.

Python collection interaction uses `gc.collect()` from the `gc` module. A Python weak reference is constructed as `weakref.ref(<object>)`; calling the reference returns `<object>` or `None`.

## `.py`

A `<module>.py` file is Python source. Pure-mode declarations use ordinary Python argument, return, and attribute annotations, including `velora.int`, builtin type names, `typing.Optional[<type>]`, and parameterised builtin container annotations. Native decorators use the imported `velora` module. A companion declaration file is `<module>.pxd`.

## `.pxd`

A `<module>.pxd` file supplies native declarations. Cross-module declaration imports use `cimport <module>` or `from <module> cimport <names>`. A companion file shares its basename with a `.pyx` or `.py` implementation. Declaration syntax includes aliases, variables, callable signatures, extension classes and attributes, and `cdef inline` callable definitions. Optional arguments in declaration signatures use `=*`.

Declaration locations are module and package paths under the supplied search directories, with dotted names corresponding to directories and a final `.pxd` basename. Version-labelled declarations use `<module>.velora-<tag>.pxd`, where the decimal tag concatenates the major and minor version numbers.

An unavailable source-name failure is carried by translation exit status `1` with a location-bearing diagnostic, or by `NameError` when the source reference executes.

## `.pxi`

An inclusion file is named by `include "<path>"` in the including source. The `.pxi` file contains source text in the same language as its including file. The path is a filename resolved through the source location and supplied inclusion-search locations.

## `.c`

The generated `<source-stem>.c` file is a UTF-8 C translation unit accepted by a native extension build for the active Python ABI. The built module exposes source-declared Python names through ordinary module attributes. Calls return Python objects: native Boolean, integer, real, and complex results use `bool`, `int`, `float`, and `complex`; native structures use `dict` keyed by source-declared member names, ordinary numeric arrays use `list`, and typed native tuples use `tuple`.

The Python null-object carrier is `None`.

Python-visible failures are catchable exception objects. `TypeError` denotes invalid calls or incompatible conversion; `OverflowError` denotes numeric conversion or checked-arithmetic overflow; `ValueError` denotes an incomplete native structure; `IndexError` denotes an incorrect native-array element count; typed-tuple count errors use `TypeError`; division failures use `ZeroDivisionError`. Text conversion failures use `UnicodeDecodeError` or `UnicodeEncodeError`. Application exceptions retain their exception class and `args` tuple.

A traceback extracted from an application exception exposes the original source path as `filename`, the source line as `lineno`, and the routine identity as `name`.

An unraisable exception is delivered to `sys.unraisablehook` as a report exposing `exc_type` and `exc_value`. The latter is the exception object, including its `args`.

A source-declared enumeration is read through `<module>.<enum>.<member>` for a named Python-visible enum, or `<module>.<member>` for a Python-visible anonymous enum. Members support conversion with `int(...)`.

## `.cpp`

The generated `<source-stem>.cpp` file is a UTF-8 C++ translation unit accepted by a native C++ extension build for the active Python ABI. The imported module exposes Python-visible definitions under their source-declared names. C++ string values cross the Python boundary as `bytes`; vector and list values as Python `list`; set and unordered-set values as Python `set`; map and unordered-map values as Python `dict`; pair values as Python `tuple`; complex values as Python `complex`.

Translated native failures use these Python carriers: `MemoryError` for allocation, `ValueError` for argument or domain, `IndexError` for out-of-range access, `OverflowError` for numeric overflow, `ArithmeticError` for numeric range or underflow, `TypeError` for type conversion, `OSError` for I/O, and `RuntimeError` for other native failures. A pair-count conversion failure uses `ValueError`. A native explanatory payload is exposed by `str(error)`. A source-supplied translator raises its chosen Python exception class and payload.

Native standard-library declarations are imported with `from libcpp.<module> cimport <type>`, optionally using `as <local-name>`. The module/type pairs are `string/string`, `vector/vector`, `list/list`, `set/set`, `unordered_set/unordered_set`, `map/map`, `unordered_map/unordered_map`, `utility/pair`, `complex/complex`, and `deque/deque`. Template declarations use `<type>[<element-type>]` or `<type>[<key-type>, <value-type>]`, including nested templates.

The native string forms are `string(<bytes>)`, `string(<bytes>, <length>)`, and `.append(<string>)`. The collection interfaces include `.push_back(<element>)` for vector and deque, `.push_front(<element>)` for list and deque, `.insert(<element>)` for sets, integer indexing for vector, key indexing and assignment for maps, and iteration over each collection. Pair fields are `.first` and `.second`, including map iteration entries. Complex construction is `complex[<real-type>](<real>, <imaginary>)`.

## `velora`

`import velora` supplies pure-mode declaration names and native type objects. The native scalar names used here are `int` and `double`, referenced as `velora.int` and `velora.double`; they can also be passed as explicit fused-specialisation selectors.

## `Velora.__version__`

`import Velora` exposes `Velora.__version__` as a version string whose first two dot-separated components are decimal major and minor text.

## `Velora.Compiler.Errors.CompileError`

`from Velora.Compiler.Errors import CompileError` imports the exception class used for interactive source-compilation failures.

## `velora.cfunc`

`velora.cfunc` is a decorator on a Python function declaration.

## `velora.ccall`

`velora.ccall` is a decorator on a Python function or method declaration.

## `velora.cclass`

`velora.cclass` is a decorator on a Python class declaration.

## `velora.locals`

`velora.locals(**arg_types)` is a function decorator. Keyword names identify source-local variables and values are native type objects.

## `velora.compiled`

`velora.compiled` is a Boolean compilation-status value available in Python and compiled source.

## `velora.annotation_typing`

`velora.annotation_typing(<bool>)` is a decorator on a source-defined routine. The corresponding directive name is `annotation_typing`.

## `velora.cdivision`

`velora.cdivision(<bool>)` is used as a routine decorator or a `with` context in source. The corresponding directive name is `cdivision`.

## `velora.boundscheck`

`velora.boundscheck(<bool>)` is a routine decorator in source. The corresponding directive name is `boundscheck`.

## `velora.wraparound`

`velora.wraparound(<bool>)` is a routine decorator in source. The corresponding directive name is `wraparound`.

## `velora.initializedcheck`

`velora.initializedcheck(<bool>)` is a routine decorator in source. The corresponding directive name is `initializedcheck`.

## `velora.profile`

`velora.profile(<bool>)` is a routine decorator in source. The corresponding directive name is `profile`.

## `velora.inline`

`velora.inline(<code-string>, quiet=<bool>, **<values>)` accepts a source fragment and keyword arguments whose names bind fragment inputs. The return type is a fragment-selected Python object or a `dict` keyed by source-local variable names with their Python values.

## `velora.compile`

`velora.compile(<python-function>)` returns a callable accepting the supplied function's positional arguments. Calling it delivers the function result as a Python object. Companion declaration inputs use `<module>.pxd` files at module-relative paths under the process working directory.

## `velora.integral`

`velora.integral` is a predefined fused type available to compiled source through `cimport velora`. It is used in argument declarations and type tests.

## `velora.floating`

`velora.floating` is a predefined fused type available to compiled source through `cimport velora`. It is used in argument declarations and type tests.

## `velora.numeric`

`velora.numeric` is a predefined fused type available to compiled source through `cimport velora`. It is used in argument declarations and type tests.

## `__signatures__`

A Python-visible fused routine exposes `__signatures__`, a `dict` mapping type-signature strings to callable specialisations. A signature uses the declared type spelling; independent fused parameters are separated by `|`. An explicit selector is `<routine>[<type-name>]`, `<routine>[<type-name>, ...]`, or the corresponding `velora` type objects. The resulting object is callable with the routine's arguments.

An unavailable explicit specialisation raises `KeyError`; incompatible Python dispatch arguments raise `TypeError`; incompatible element specialisations across arguments sharing a typed-memoryview declaration raise `ValueError`.

## `velora.view`

Compiled source can use `from velora cimport view`. The dimension-layout names are `view.contiguous`, `view.indirect`, `view.indirect_contiguous`, and `view.generic`, placed after `::` in a memoryview dimension declaration.

## `velora.view.memoryview`

A typed-memoryview declaration has form `<element-type>[<dimensions>]`, with `:` for a strided dimension and `::1` for a contiguous dimension specification. `const <element-type>` declares read-only element access. Python-facing view objects support integer and tuple indexing, slice indexing, slice assignment, `None` axes, iteration, the `.T` transpose attribute, `.copy()`, and `.copy_fortran()`. The copy methods return Python-facing typed-memoryview objects.

Read attributes are `shape` (tuple of dimension lengths), `strides` (tuple of byte strides), `itemsize` (integer element byte size), `size` (integer element count), `nbytes` (integer byte count), and `base` (exporting Python object). A Python `memoryview(<view>)` consumer exposes `shape`, `strides`, `format`, `itemsize`, `nbytes`, `readonly`, indexed access, assignment, and `tolist()`. `format` is a buffer-format string and `readonly` is Boolean.

Buffer type or rank incompatibility is reported with `ValueError`. Layout incompatibility uses `ValueError` or `BufferError`. Writable-buffer incompatibility uses `BufferError`. Bounds failures use `IndexError`; uninitialised view access uses `UnboundLocalError`; incompatible view assignment uses `ValueError`.

## `velora.view.array`

`from velora.view cimport array`. Used construction: `array(shape=<tuple>, itemsize=<int>, format=<str>, mode=<str>)`, with `mode` optionally omitted. Layout selectors are `c` for C layout and `fortran` for Fortran layout. The result is an owning Python buffer exporter usable through a typed memoryview and `memoryview(...)`. Its buffer descriptor carries shape, byte strides, element format and size, and writability. Invalid buffer configuration raises `ValueError`.

## `velora.parallel.prange`

`from velora.parallel cimport prange`. Used loop expression: `prange(stop, nogil=<bool>, num_threads=<integer>, schedule=<string>, chunksize=<integer>, use_threads_if=<condition>)`, with only the needed keyword arguments supplied. `schedule` spellings are `static`, `dynamic`, `guided`, and `runtime`. Iteration yields native integer indices. The loop body is authored source. Runtime configuration uses the environment names `OMP_NUM_THREADS`, `OMP_DYNAMIC`, `OMP_SCHEDULE`, `OMP_PROC_BIND`, and `OMP_WAIT_POLICY`.

For parallel native builds on the Linux GCC-compatible toolchain, pass `-fopenmp` in both the extension description's `extra_compile_args` and `extra_link_args`.

## `velora.parallel.parallel`

`from velora.parallel cimport parallel`. Used context: `with nogil, parallel(num_threads=<integer>):`. The context contains source-authored native statements and `prange` loops.

## `velora.ufunc`

`velora.ufunc` is a decorator on a native scalar routine in source, including a fused scalar routine. The published Python name is the decorated source name. Calling that name accepts positional NumPy array operands. A single scalar result is returned as a NumPy array; a typed tuple result is returned as a Python tuple of NumPy arrays. Arrays expose `.shape`, their indexed elements, and the declared numeric or object element type. Incompatible operand shapes raise `ValueError`.

## `veximport.install`

`import veximport`. Used call: `veximport.install(build_dir=<path-string>, language_level=<language-selector>)`. The return is a two-item tuple `(py_importer, pyx_importer)` that can be unpacked into `veximport.uninstall`. Discoverable source modules use `<module>.pyx` on the Python module search path; the supplied `build_dir` is the build-output root.

Source-compilation, native-build, and module-execution import failures are raised as `ImportError`. The raised exception exposes the standard `__cause__` and `__context__` links; exception objects expose their class and `args`.

## `veximport.uninstall`

`veximport.uninstall(py_importer, pyx_importer)` accepts the two objects returned by `veximport.install`. Normal Python import refusal is exposed as `ModuleNotFoundError`, whose `name` is the requested module name.

## `.pyxbld`

A custom build description is the Python source file `<module>.pyxbld` beside `<module>.pyx`. It exports `make_ext(modname, pyxfilename)`, accepting the module import name and source filename as strings and returning a `setuptools.Extension`. The used extension fields are `sources`, `include_dirs`, and `define_macros`.

## `.pyxdep`

An import-compilation dependency file is `<module>.pyxdep` beside the module source. It is text with one dependency path per line; relative dependency paths are relative to the source file's directory.

## `%%velora`

Enable the IPython extension with `extension_manager.load_extension('velora')`. Invoke a cell through `run_cell_magic('velora', <option-line>, <source-cell>)`, the programmatic form of `%%velora`. The option line and cell are strings. Published Python objects are available under their source-defined names in the session's `user_ns` mapping.

Used cell options are `--cplus`, `-I <native-header-directory>`, `-S <native-source-file>`, `-L <library-directory>`, and `-l <library-name>`. Compilation and native-build failures report diagnostic text on `stderr`. A missing external Python name can instead appear as `NameError` when the module or its callable executes.

## `.h`

A source declaration `cdef public` exports a native type, variable, or routine through the adjacent `<module>.h` header. A C consumer includes that header after `Python.h`; it names exported types, members, variables, and routines by the names supplied in the declarations. Function parameters and results have their declared native C types.

## `_api.h`

A native `cdef api` routine and a `cdef public api class` expose a generated `<module>_api.h` header. The class declaration can supply C names using `[object <object-name>, type <type-name>]`. The header exposes the supplied object struct name, Python type-object name, and routine names with their declared native types. A C consumer includes `Python.h` and this header. Its `import_<module>()` entry returns a C integer, with a negative value indicating failure and a Python exception set.

## `.dep`

Dependency output is UTF-8 text named `<generated-native-path>.dep`. Its Make rule has form `<target-path>: <prerequisite-path> ...`, with the generated native-source path as the target and source/declaration/inclusion filenames as prerequisites. A backslash followed by a newline continues a rule; a space inside a path is escaped as `\ `. Relative paths are relative to the compilation process working directory.

## `.html`

Annotation output is the UTF-8 file `<source-stem>.html` beside the generated native source. Source-line records are `pre` elements inside a `div` with class `velora`. A record has classes `velora line score-<integer>`. Its first child element is a `span` carrying the one-based decimal line number, followed by the text separator `: ` and the highlighted source-line text. Text is read after HTML entity decoding.

The `score-` class encodes Python interaction: `score-0` is the native-only category and a positive integer denotes Python interaction. An expandable source record carries an `onclick` attribute and is immediately followed by a `pre` with classes `velora code`. That element's decoded text is the corresponding generated native source; a source-position comment can be abbreviated as `/* … */`.

The complete native-source section is identified by a `pre` with classes `velora line`, without a `score-` class, whose decoded label is `+ Complete veloraized code`. The next element is `pre` with classes `velora code` carrying the complete native translation unit as decoded text.

Coverage annotation is encoded by a class on the line-number `span` and the associated native-code `pre`: `run` denotes recorded execution and `mis` denotes no recorded execution.

## `coverage`

The file supplied to `--annotate-coverage` is XML with a `coverage` root and `packages/package/classes/class` records. Each `class` carries a `filename` attribute identifying its source file and contains `lines/line` records. A `line` carries decimal integer attributes `number` (one-based source line) and `hits` (recorded execution count).

## `velora_debug`

Debug information is written under `<debug-output-directory>/velora_debug/`. The per-module file is `velora_debug_info_<module>`. The path is supplied to the debugger's `ve import` command; its contents are exchanged through that command.

## `Velora.Debugger`

Within GNU Debugger's Python interpreter, `from Velora.Debugger import libvelora, libpython` makes the product's `ve` commands and convenience functions available. Command text can be submitted through `gdb.execute(<command>, to_string=True)`, which returns the command output as text. Debugger command failures raise a GDB error.

## `ve import`

`ve import <debug-information-path>` accepts the generated per-module debug-information filename.

## `ve break`

`ve break <module>:<line>` names a source breakpoint by module import name and one-based line number.

## `ve step`

`ve step` is a source-level execution-control command issued at a stopped location.

## `ve next`

`ve next` is a source-level execution-control command issued at a stopped location.

## `ve finish`

`ve finish` is an execution-control command issued in the selected compiled frame.

## `ve select`

`ve select <frame-number>` accepts the decimal frame number carried by a `ve bt` record.

## `ve set`

`ve set <local-name> = <native-expression>` accepts a native local variable name and assignment expression in the selected frame.

## `ve_colorize_code`

The GDB setting `set ve_colorize_code off` selects plain source-listing text.

## `$ve_lineno()`

The GDB expression `$ve_lineno()` returns the stopped source line number as an integer, readable with `gdb.parse_and_eval`.

## `ve bt`

`ve bt` emits stack records of the form `#<frame-number> 0x<hex-address> in <routine>() at <source-path>:<line>`. The frame number and source line are decimal integers; the address is hexadecimal. Whitespace separates fields. The routine and source path identify the compiled frame.

## `ve list`

`ve list` emits source-listing records. The current source line has form `> <line-number> <source-text>`, with whitespace separating the marker, decimal line number, and source text.

## `ve locals`

`ve locals` emits native scalar records with form `<local-name><spaces>= (<native-type>) <scalar-value>`. For integer locals, the value is signed decimal text. The local name and native type identify the selected frame's variable.

## `ve exec`

`ve exec <Python-code>` evaluates supplied Python code in the selected compiled frame. Code can perform application output and file writes using the ordinary Python interfaces it invokes. Evaluation failure emits a Python traceback on debugger `stderr`, ending in `<exception-class>: <explanation>`; the explanation is human-readable text.

## `profile`

On CPython 3.11, source-profile records are readable through `pstats.Stats(<profile>).stats`. Keys are `(filename, first_line, routine_name)`. Each value is a five-item tuple with the integer total call count at index `1` and a caller mapping at index `4`. Caller keys have the same `(filename, line, name)` shape and caller values carry their integer call count at index `1`.

## `linetrace`

Native build support is selected using `define_macros` pairs `VELORA_TRACE=1` or `VELORA_TRACE_NOGIL=1`. On CPython 3.11, a `sys.settrace` callback receives `(frame, event, arg)`. Source line events use the string `line`; the frame exposes `f_code.co_filename` for the original source path and `f_lineno` for its one-based line number.

## `main`

Native source generated with `--embed` can be linked as an executable with the active Python development headers and runtime library. Invocation is `<executable> <arguments> ...`. Application command-line arguments are exposed through `sys.argv`; the module execution name is exposed through `__name__`.

Successful execution exits `0`; an uncaught application exception exits `1` with a nonempty exception report on `stderr`.

## `cpython.buffer`

Compiled source imports `Py_buffer` with `from cpython.buffer cimport Py_buffer`. The exchanged descriptor fields are `buf` (data pointer), `obj` (exporting object), `len` (byte length), `itemsize` (element byte size), `readonly` (integer Boolean), `ndim` (dimension count), `format` (native buffer-format string), `shape` (dimension-length pointer), `strides` (byte-stride pointer), `suboffsets` (indirection-offset pointer), and `internal` (exporter-owned pointer). Integer dimension and byte-size fields use Python-sized native integers. Native `int` elements use the buffer-format spelling `i`.

Extension buffer hooks have signatures `def __getbuffer__(self, Py_buffer* view, int flags)` and `def __releasebuffer__(self, Py_buffer* view)`. The acquisition hook receives the consumer flags and fills the descriptor. Python consumers use `memoryview(<exporter>)`, including `.format`, `.itemsize`, `.shape`, `.strides`, `.readonly`, `.tolist()`, indexing, assignment, and `.release()`. A refusal from buffer acquisition is exposed as `BufferError`; assignment through a read-only Python consumer is refused as `TypeError`.

## `__richcmp__`

Extension comparison hook signature: `def __richcmp__(self, other, int op)`. The integer `op` uses the Python comparison-operation codes: `0` for `<`, `1` for `<=`, `2` for `==`, `3` for `!=`, `4` for `>`, and `5` for `>=`. Its result is returned as a Python object.

## `__cinit__`

An extension type can declare `def __cinit__(self, <arguments>):` as its native initialisation hook. The supplied arguments use the source-defined constructor signature. Explicit allocation is reached as `<Type>.__new__(<Type>, <arguments>)`.

## `__dealloc__`

An extension type can declare `def __dealloc__(self):` as its native cleanup hook.

## `libc.math.sqrt`

Native declaration import: `from libc.math cimport sqrt`. The callable interface is `double sqrt(double)`.

## `libc.math.sin`

Native declaration import: `from libc.math cimport sin`. The callable interface is `double sin(double)`.

## `libc.math.cos`

Native declaration import: `from libc.math cimport cos`. The callable interface is `double cos(double)`.

## `libc.stdlib.malloc`

Native declaration import: `from libc.stdlib cimport malloc`. The callable interface is `void* malloc(size_t)`.

## `libc.stdlib.free`

Native declaration import: `from libc.stdlib cimport free`. The callable interface is `void free(void*)`.

## `libc.stdlib.abort`

Native declaration import: `from libc.stdlib cimport abort`. The callable interface is `void abort()`.

## `libc.string.memcpy`

Native declaration import: `from libc.string cimport memcpy`. The callable interface is `void* memcpy(void*, const void*, size_t)`.

## `libc.string.memmove`

Native declaration import: `from libc.string cimport memmove`. The callable interface is `void* memmove(void*, const void*, size_t)`.

## `libc.string.memset`

Native declaration import: `from libc.string cimport memset`. The callable interface is `void* memset(void*, int, size_t)`.

## `libc.string.memcmp`

Native declaration import: `from libc.string cimport memcmp`. The callable interface is `int memcmp(const void*, const void*, size_t)`.

## `libc.string.strlen`

Native declaration import: `from libc.string cimport strlen`. The callable interface is `size_t strlen(const char*)`.

## `libc.stdio.fopen`

Native declaration import: `from libc.stdio cimport fopen`. The callable interface is `FILE* fopen(const char*, const char*)`.

## `libc.stdio.fclose`

Native declaration import: `from libc.stdio cimport fclose`. The callable interface is `int fclose(FILE*)`.

## `libc.stdio.tmpfile`

Native declaration import: `from libc.stdio cimport tmpfile`. The callable interface is `FILE* tmpfile()`.

## `libc.stdio.fread`

Native declaration import: `from libc.stdio cimport fread`. The callable interface is `size_t fread(void*, size_t, size_t, FILE*)`.

## `libc.stdio.fwrite`

Native declaration import: `from libc.stdio cimport fwrite`. The callable interface is `size_t fwrite(const void*, size_t, size_t, FILE*)`.

## `libc.stdio.fseek`

Native declaration import: `from libc.stdio cimport fseek`. The callable interface is `int fseek(FILE*, long, int)`.

## `posix.stdio.fileno`

Native declaration import: `from posix.stdio cimport fileno`. The callable interface is `int fileno(FILE*)`.

## `posix.unistd.pipe`

Native declaration import: `from posix.unistd cimport pipe`. The callable interface is `int pipe(int[2])`.

## `posix.unistd.read`

Native declaration import: `from posix.unistd cimport read`. The callable interface is `ssize_t read(int, void*, size_t)`.

## `posix.unistd.write`

Native declaration import: `from posix.unistd cimport write`. The callable interface is `ssize_t write(int, const void*, size_t)`.

## `posix.unistd.close`

Native declaration import: `from posix.unistd cimport close`. The callable interface is `int close(int)`.

## `posix.unistd.getpid`

Native declaration import: `from posix.unistd cimport getpid`. The callable interface is `pid_t getpid()`.

## `posix.unistd.getppid`

Native declaration import: `from posix.unistd cimport getppid`. The callable interface is `pid_t getppid()`.

## `posix.unistd.getuid`

Native declaration import: `from posix.unistd cimport getuid`. The callable interface is `uid_t getuid()`.

## `posix.unistd.getgid`

Native declaration import: `from posix.unistd cimport getgid`. The callable interface is `gid_t getgid()`.

## `cpython.long.PyLong_FromLong`

Native declaration import: `from cpython.long cimport PyLong_FromLong`. The callable interface is `object PyLong_FromLong(long)`.

## `cpython.long.PyLong_AsLong`

Native declaration import: `from cpython.long cimport PyLong_AsLong`. The callable interface is `long PyLong_AsLong(object)`.

## `cpython.float.PyFloat_FromDouble`

Native declaration import: `from cpython.float cimport PyFloat_FromDouble`. The callable interface is `object PyFloat_FromDouble(double)`.

## `cpython.float.PyFloat_AsDouble`

Native declaration import: `from cpython.float cimport PyFloat_AsDouble`. The callable interface is `double PyFloat_AsDouble(object)`.

## `cpython.list.PyList_New`

Native declaration import: `from cpython.list cimport PyList_New`. The callable interface is `list PyList_New(Py_ssize_t)`.

## `cpython.list.PyList_Append`

Native declaration import: `from cpython.list cimport PyList_Append`. The callable interface is `int PyList_Append(object, object)`.

## `cpython.list.PyList_GetItem`

Native declaration import: `from cpython.list cimport PyList_GetItem`. The callable interface is `PyObject* PyList_GetItem(object, Py_ssize_t)`.

## `cpython.dict.PyDict_New`

Native declaration import: `from cpython.dict cimport PyDict_New`. The callable interface is `dict PyDict_New()`.

## `cpython.dict.PyDict_SetItem`

Native declaration import: `from cpython.dict cimport PyDict_SetItem`. The callable interface is `int PyDict_SetItem(object, object, object)`.

## `cpython.dict.PyDict_GetItem`

Native declaration import: `from cpython.dict cimport PyDict_GetItem`. The callable interface is `PyObject* PyDict_GetItem(object, object)`.

## `libc.stddef.size_t`

`from libc.stddef cimport size_t` imports the platform C size type for native declarations.

## `libc.stdio.FILE`

`from libc.stdio cimport FILE` imports the C file-stream type. Source declarations use `FILE*` for stream handles.

## `libc.stdio.SEEK_SET`

`from libc.stdio cimport SEEK_SET` imports the native file-position origin constant, usable as the origin argument to `fseek`.

## `numpy.ndarray`

Compiled NumPy declarations use `cimport numpy as <alias>`. A typed array argument has form `<alias>.ndarray[<alias>.float64_t, ndim=<rank>]`; `float64_t` denotes the NumPy double-precision element type. The array exposes `.shape[<axis>]` and element reads and writes through `[<indices>]`. Type or rank incompatibility raises `ValueError`.

The Python import is `import numpy as <alias>`. `<alias>.get_include()` returns the native-header directory for the build description. Python arrays expose `.shape`, `.dtype`, indexed access and assignment; numeric dtype names include `intc`, `int32`, `float64`, and `complex128`, and object arrays use `object`.
