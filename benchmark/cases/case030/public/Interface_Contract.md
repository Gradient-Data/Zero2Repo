# Interface Contract

The Python package is importable as `zelvori` from the package directory `zelvori`. The console executable is `zelvori`, available beside the Python executable; commands run with the caller-selected working directory. Python package lookup uses `PYTHONPATH`.

Command completion uses process exit status `0` for success, `1` for a reported source, configuration, dependency, or native-build failure, and `2` for an invalid command invocation. Invocation diagnostics are on `stderr` and include a line beginning `usage:`. Source diagnostics are on `stdout`. Native-build failures carry diagnostic text on `stdout` or `stderr`.

Source diagnostic lines have the form ` |<severity> [<stage>]: <source-path>[ <location>]| <message>`. The severity markers are `error` and `fatal`; the stage field is `None`, `syntactic`, or `semantic`. A location is `[<line>]` or `[<line>,<column>]`, with decimal integer coordinates; the location field can be absent. The path identifies the affected submitted source. The message carries the diagnostic explanation.

For malformed Python grammar the stage is `None`; unresolved imports use `syntactic`; missing required annotations, incompatible declarations or calls, and unresolved names use `semantic`.

## `zelvori`

`zelvori` exposes `ezelvori` and `lambdify` as importable callables.

## `zelvori.ezelvori`

`ezelvori(function_class_or_module, *, language=..., folder=..., openmp=..., comm=..., root=..., bcast=...)` is the callable imported from `zelvori`. The first positional argument is Python source text (`str`), a source-backed function, a source-backed class, or a module object. `language` is text; `folder` is a directory string, including a relative directory. `openmp` is Boolean. These keyword arguments may be omitted.

The return is a Python-callable function for a function input, a callable class for a class input, or a module for a module or source-text input. Module members, argument names, class names, methods, instance attributes, and properties use the names declared by the submitted source. Returned functions accept positional and named arguments, including declarations using `/` and `*`.

Function results are Python numerical or string scalars, numerical arrays exposed as `numpy.ndarray`, Python `list`, `set`, or `dict` values, translated class instances, or tuples for multiple results. No-result completion returns `None`. Caller-visible updates are read through the same supplied arrays, containers, or instance attributes.

Invalid calls to delivered functions raise `TypeError`. Unavailable public members and writes to read-only properties raise `AttributeError`. Source-meaning refusal is exposed by `zelvori.errors.errors.ZelvoriSemanticError`. A native compilation refusal is exposed by `RuntimeError`. Ownership refusal has either form: `ZelvoriSemanticError` from `ezelvori`, or `ValueError` from calling the delivered function.

Callable-declaration refusal from `ezelvori` may use either `ZelvoriSemanticError` or `RuntimeError`.

For collective calls, `comm` is an `mpi4py` communicator, `root` is an integer rank, and `bcast` is Boolean. A delivered result is the same function-or-module form described above; absence of a delivered object is represented by `None`.

The target selector is supplied using `language="c"`, `language="fortran"`, or `language="python"`.

## `zelvori.errors.errors`

`zelvori.errors.errors` exports the exception class `ZelvoriSemanticError`.

## `zelvori.errors.errors.ZelvoriSemanticError`

`ZelvoriSemanticError` is an exception class importable from `zelvori.errors.errors`; it is the Python carrier for a semantic source rejection.

## `zelvori.lambdify`

`lambdify(expr, args, *, result_type=..., use_out=..., language=..., folder=...)` is imported from `zelvori`. `expr` is a SymPy expression. `args` is an ordered Python dictionary with SymPy symbols as keys and string type annotations as values. `result_type` is an optional string type annotation; `use_out` is Boolean. `language` and `folder` are text keyword arguments. The keyword arguments shown may be omitted.

The return is callable with numerical scalar or `numpy.ndarray` arguments. Ordinary evaluation exposes its result directly as a numerical scalar or `numpy.ndarray`. The output-storage call form is `callable(<arguments>, out=<array>)` or `callable(<arguments>, <array>)`; the supplied array exposes the written values. Invalid expression-compilation requests raise `TypeError`.

## `zelvori compile`

`zelvori compile <source.py> [<options>]` accepts a relative or absolute source-file path. Options are `--language <target>`, `--syntax-only`, `--semantic-only`, `--convert-only`, `--output <directory>`, `--compiler-family <name>`, `--compiler-config <file.json>`, `--debug`, and `--no-debug`. The options without placeholders take no argument.

Native-build options are `--flags=<text>`, `--wrapper-flags=<text>`, `--include <directory> ...`, `--libdir <directory> ...`, and `--libs <library> ...`. The first two each take one string containing compiler arguments; the latter options take lists of text arguments. `ZELVORI_DEFAULT_COMPILER` names an environment-selected compiler configuration; `ZELVORI_DEBUG_MODE` carries the environment-selected debug mode as text.

Delivered files are placed in the selected output directory, or next to the input source when no output directory is supplied. A native extension is named `<source-stem><Python extension suffix>` and imported under the source stem; a script executable is named `<source-stem>` with executable permissions. Generated native source is under `__zelvori__<worker-suffix>/`. Python output is `<source-stem>.py` in the selected output directory.

The target selector values for `--language` are spelled `c`, `fortran`, `c++`, and `python`. Built-in compiler selectors supplied to `--compiler-family` are spelled `GNU`, `intel`, `nvidia`, and `LLVM`; caller-selected registration names use the same argument position. `ZELVORI_DEBUG_MODE` uses the text `1` for an enabled debug selection.

## `zelvori config export`

`zelvori config export <file.json> --compiler-family <family>` writes a compiler-configuration JSON document at the supplied path. A successful export exits `0`.

## `zelvori config check`

`zelvori config check <file.json>` reads a compiler-configuration JSON document. Successful completion exits `0`; configuration rejection exits `1` and includes an `stderr` line prefixed `|Error|:`. Advisory lines are on `stderr` and have the form `|Warning|: <explanation>`. An advisory explanation contains the affected setting identifier and language identifier as intact tokens; surrounding sentences are not fixed.

## `zelvori config register`

`zelvori config register <name> <file.json>` accepts a registration name and compiler-configuration file. `ZELVORI_CONFIG_HOME` supplies the registration-directory path. The externally visible registration directory is `<ZELVORI_CONFIG_HOME>/<name>`. Success exits `0`; refusal exits `1` with a `|Error|:` diagnostic line. Registration-name containment diagnostics use `stdout`; configuration and existing-registration diagnostics use `stderr`.

## `zelvori config remove`

`zelvori config remove <name>` addresses the registration directory `<ZELVORI_CONFIG_HOME>/<name>`. Success exits `0`; refusal exits `1` with an `stderr` line beginning `|Error|:`.

## `compiler configuration JSON`

A compiler-configuration file is a UTF-8 JSON object keyed by language. Exported language keys are `c`, `c++`, and `fortran`. Each language value is an object of named settings. `exec` and `mpi_exec` hold executable-description strings; `general_flags`, `release_flags`, and `debug_flags` hold lists of compiler-argument strings; `include`, `libdir`, `dependencies`, and `libs` hold lists of strings denoting include directories, library directories, dependency files, and libraries respectively. `openmp` is an object whose `flags` field is a list of compiler-argument strings.

## `zelvori make`

Project invocation is `zelvori make -f <source.py> ... [<options>]`, `zelvori make -g <pattern> [<options>]`, or `zelvori make -d <manifest> [<options>]`. The first selection takes a nonempty file list; the other selections each take one text argument. Options are `--language <target>`, `--build-system <system>`, and `--output <directory>`. Paths and patterns are interpreted from the invocation working directory.

Each delivered extension, executable, or Python file occupies `<output-root>/<source-relative-parent>/<source-stem><suffix>`. The suffix is a platform Python extension suffix, empty for an executable, or `.py` for Python source. Without an explicit output destination the output root is the project root. Reported dependency errors exit `1` and emit `fatal` source diagnostic records on `stdout`, using ` |fatal [<stage>]: <source-identifier>[ <location>]| <explanation>`. The stage field is `None`, `syntactic`, `semantic`, or `cwrapper`. A source-file attribution uses its path; a project-level attribution may use a module stem. The explanation contains involved directory paths or an unresolved module identifier as intact caller-supplied identifiers; surrounding sentences and separators are not fixed.

The `--language` target selector uses `c`, `fortran`, or `python`. The `--build-system` selector uses `meson` or `cmake`.

## `project manifest`

The file supplied to `zelvori make -d <manifest>` is UTF-8 text containing one relative or absolute source path per line.

## `zelvori wrap`

`zelvori wrap <interface.pyi> --language <language>` accepts a typed interface file. The delivered extension is `<interface-directory>/<interface-stem><Python extension suffix>`, importable under the interface stem. Module, function, class, method, attribute, and property names are those declared by the interface. Python calls expose scalars, tuples of scalar results, instance state, and mutations of supplied `numpy.ndarray` arguments. Incompatible calls raise `TypeError`; read-only property assignment raises `AttributeError`. Success exits `0`; native-build failure exits `1` and carries diagnostics on `stdout` or `stderr`.

The language selector is spelled `c` or `fortran`.

## `.pyi`

Interface paths end in `.pyi`. The content uses Python annotated function and class declarations with `...` bodies. Header metadata lines have the form `#$ header metavar <key>="<value>"`; the keys are `includes`, `libraries`, and `libdirs`, whose string values identify native include locations, libraries, and library locations. `from zelvori.decorators import low_level` introduces `@low_level(<native-name>)` on a function, class, or method. `from typing import overload` introduces `@overload` declarations. Class interfaces expose annotated attributes, `@property` getters, `__init__`, `__del__`, and `__imul__` declarations. Annotations include scalar types, `tuple[<type>, <type>]`, and string array annotations with `(order=F)`.

A C interface has a companion `<interface-stem>.h` in its include location. Its declarations name native functions and struct tags; an instance method's native signature takes a pointer to the declared struct as its first argument. Annotated attributes name struct fields. Scalar arguments and results use the corresponding C numerical types; a no-result declaration has a `void` result.

A Fortran interface stem names the native module. Scalar results correspond to function results; no-result declarations correspond to subroutines, and tuple results correspond to leading output arguments in result order. Class declarations name native derived types, and method mappings name their type-bound procedures. Annotated attributes name native components.

## `zelvori clean`

`zelvori clean [--not-recursive] [--remove-libs] [--remove-programs] [<directory> ...]` accepts directory paths; each listed option takes no argument. Cleanup is observed through directory entries, file bytes, and executable permissions in the selected filesystem scope.

## `__zelvori__`

The native translation directory is `<output-directory>/__zelvori__<worker-suffix>`. The suffix is the text value of `PYTEST_XDIST_WORKER`, or the empty string when that variable is absent. Source files in this directory are `<source-stem>.c`, `<source-stem>.f90`, or `<source-stem>.cpp` according to the selected native target. The script source companion is `prog_<source-stem>` with the same source suffix.

The standalone C or Fortran source-pair consumer form is `<native-compiler> <module-source> <script-source> -o <executable>`, invoked from the translation directory. Accompanying include files are resolved from that directory. This form addresses self-contained integer addition, subtraction, and multiplication programs with a script entry. Running the resulting executable exposes the submitted script's output on `stdout` and its process exit status.

## `__ezelvori__`

The interactive build directory is `<folder>/__ezelvori__<worker-suffix>`, where the suffix is the text value of `PYTEST_XDIST_WORKER`, or empty when absent.

## `.zelvori`

Saved translation files addressed by cleanup have names `<stem>.zelvori`. Cleanup observes their paths and file content as bytes.

## `Python extension files`

A delivered extension path is `<directory>/<module-name><suffix>`, where `<suffix>` is one of `importlib.machinery.EXTENSION_SUFFIXES`. It is loadable with an ordinary Python extension-module specification and importable by `<module-name>`. Public members use submitted declaration names.

## `.cpp`

C++ declaration output is a `.cpp` source file. Module-level declarations are exposed in the namespace named after the input module. A consumer can include this file and call `<module-name>::init()`; variables are read as `<module-name>::<declared-name>`, with integral, floating, and Boolean C++ types for the respective source declarations.

## `zelvori.extensions.gftl_install`

The installed Python package includes the resource directory `zelvori/extensions/gftl_install` under its installation root. It is a directory tree that can be copied intact with the package.

## `zelvori.decorators`

`zelvori.decorators` exposes the decorators `inline`, `private`, `elemental`, `allow_negative_index`, `pure`, `stack_array`, and `low_level`. The Python support module is available as `zelvori/decorators.py`.

## `zelvori.decorators.inline`

`inline(f)` is imported from `zelvori.decorators`. It is used as `@inline` on a function declaration; its Python return is a callable function.

## `zelvori.decorators.private`

`private(f)` is imported from `zelvori.decorators`. It is used as `@private` on a function declaration; its Python return is a callable function.

## `zelvori.decorators.elemental`

`elemental(f)` is imported from `zelvori.decorators`. It is used as `@elemental` on a function declaration; its Python return is a callable function.

## `zelvori.decorators.allow_negative_index`

`allow_negative_index(*args)` is imported from `zelvori.decorators`. Its positional arguments are strings naming source arrays. It returns a decorator used as `@allow_negative_index(<array-name>, ...)`.

## `zelvori.decorators.pure`

`pure(f)` is imported from `zelvori.decorators`. It is used as `@pure` on a function declaration; its Python return is a callable function.

## `zelvori.decorators.stack_array`

`stack_array(*args)` is imported from `zelvori.decorators`. Its positional arguments are strings naming source arrays. It returns a decorator used as `@stack_array(<array-name>, ...)`.

## `zelvori.decorators.low_level`

`low_level(low_level_name: str)` is imported from `zelvori.decorators`. It returns a decorator, used as `@low_level(<native-name>)`; the string argument names the native declaration.

## `.py`

Submitted and delivered Python source files use the `.py` suffix and Python source syntax. Function and local declarations use `<name>: <annotation>` and function results use `-> <annotation>`. An annotation can be a type name, a type alias, or a quoted annotation string. Scalar annotation names are `bool`, `int`, `float`, `complex`, `str`, `int8`, `int16`, `int32`, `int64`, `float32`, `float64`, `complex64`, and `complex128`.

An array annotation string has the form `<element-type>[<colon-list>]`, where `<colon-list>` consists of comma-separated `:` tokens. An explicit layout suffix has the form `(order=C)` or `(order=F)`. Container annotation forms are `tuple[<type>,...]`, `tuple[<type>, <type>, ...]`, `list[<type>]`, `set[<type>]`, and `dict[<key-type>, <value-type>]`. Union annotations separate alternatives with `|`. Type names may be qualified through imported module names.

Callable annotation strings use `(<result-type>)(<argument-types>)`, with comma-separated types inside the second pair of parentheses. Functions use ordinary Python declaration and call syntax, including argument defaults, `None`, positional-only `/`, and keyword-only `*`.

Module imports use Python `import` and `from ... import ...` syntax, including relative imports and `as` aliases. A script entry block is written `if __name__ == '__main__':`. Delivered Python source is importable as a module and executable by the Python interpreter.

## `numpy.ndarray`

Numerical array arguments and results are exposed as `numpy.ndarray`. `shape` is a tuple of integer dimension lengths; `dtype` is a NumPy data-type object. Integer and tuple indexing read or write elements, and slice indexing addresses array regions. `flags.c_contiguous` and `flags.f_contiguous` are Boolean layout indicators. The `flat` iterator provides flat element access.

Array properties in submitted source are `shape`, `size` (integer element count), `dtype`, `real`, `imag`, and `T` (array-valued properties). Methods are `conjugate()` and `copy(order=<layout>)`; `order` is an optional string keyword. Components of a returned complex scalar are exposed through its numerical `real` and `imag` attributes.

## `builtins.print`

Submitted source calls `print(<values>, sep=<text>, end=<text>)`, with optional `sep` and `end` string keywords, or `print()` with no values. Program output is on `stdout`. Integer tokens are signed decimal integers; real tokens use decimal notation with an optional exponent; Boolean tokens are `True` or `False`. Complex tokens have the form `(<real><sign><imaginary>j)`, with padding spaces permitted. Strings carry their contents. Caller-supplied separators and terminators delimit the printed fields.

## `sys.exit`

Submitted source imports `exit` from `sys` and calls `exit()` or `exit(<status-or-reason>)`, where the argument is an integer status or string reason. Program completion is exposed by the process exit status. A textual reason is carried as a line on `stderr`.

## `typing`

Source imports from `typing` expose `TypeAlias`, `Final`, `TypeVar`, and `overload` for annotations and declarations.

## `typing.TypeAlias`

A type alias declaration uses `<alias-name>: TypeAlias = <type-description>`, after importing `TypeAlias` from `typing`. The alias name is caller-selected.

## `typing.Final`

The annotation form is `Final[<type>]`, with `Final` imported from `typing`. It can appear in a string annotation or as an annotation object.

## `typing.TypeVar`

A constrained type declaration uses `<name> = TypeVar(<name-string>, <type>, <type>, ...)`, after importing `TypeVar` from `typing`. The declared object can be used as a function argument annotation, including in source-backed Python callables.

## `typing.overload`

`overload` is imported from `typing` and used as `@overload` on typed interface function declarations.

## `class declarations`

Submitted classes use `class <name>:` and `def __init__(self, <arguments>):`. Instances expose attributes and methods under their submitted names; a getter is declared with `@property`. Methods use ordinary call syntax with the instance as `self`; methods and functions can return translated instances and arrays.

Operator method declarations are `__add__`, `__sub__`, `__mul__`, `__truediv__`, `__pow__`, `__lshift__`, `__rshift__`, `__and__`, `__or__`, `__iadd__`, `__isub__`, `__imul__`, `__itruediv__`, `__ipow__`, `__ilshift__`, `__irshift__`, `__iand__`, `__ior__`, `__radd__`, `__rsub__`, `__rmul__`, `__rtruediv__`, `__rpow__`, `__rlshift__`, `__rrshift__`, `__rand__`, `__ror__`, `__len__`, `__getitem__`, and `__contains__`. Binary methods take `self` and an operand; length takes `self`; element lookup and membership take `self` and an element argument. Their results are instances or numerical and Boolean scalars, as declared by the submitted methods.

## `builtins.tuple`

Tuple construction uses `tuple(<iterable>)`. Tuple values use `(<elements>)`; homogeneous annotations use `tuple[<type>,...]`. Python tuple inputs, indexed elements, and iterable tuple results are exposed through ordinary Python sequence access.

## `builtins.list`

List values use `[<elements>]`; annotations use `list[<type>]`. The Python boundary exposes lists and indexed elements. Source member calls are `append(<value>)`, `insert(<index>, <value>)`, `extend(<values>)`, `pop()` or `pop(<index>)`, `clear()`, and `reverse()`. Mutation is read from the supplied list or a returned list; `pop` exposes the removed element.

## `builtins.set`

Set values use `{<elements>}`; annotations use `set[<type>]`. The Python boundary exposes sets and their elements. Source member calls are `add(<value>)`, `remove(<value>)`, `discard(<value>)`, `pop()`, `clear()`, `copy()`, `union(<set>)`, `intersection(<set>)`, `difference(<set>)`, `isdisjoint(<set>)`, `update(<set>)`, `intersection_update(<set>)`, and `difference_update(<set>)`. Query results are Boolean or integer scalars; set-valued results expose sets, and `pop` exposes a removed element.

## `builtins.dict`

Dictionary values use `{<key>: <value>, ...}`; annotations use `dict[<key-type>, <value-type>]`. The Python boundary exposes dictionaries and their key-value associations. Source member calls are `pop(<key>)`, `pop(<key>, <default>)`, `popitem()`, `clear()`, `keys()`, `values()`, `items()`, and `get(<key>, <default>)`. `popitem` exposes a key-value pair; `pop` and `get` expose a value; iterable members expose keys, values, or key-value pairs.

## `#$ omp`

OpenMP declarations are comment lines of the form `#$ omp <directive> [<clauses>]`. Directive spellings are `parallel`, `for`, `single`, `critical`, `barrier`, `atomic`, `task`, `taskwait`, `sections`, `section`, `simd`, `parallel for`, and `parallel for simd`. Block terminators use `end <directive>`. Clause forms are `num_threads(<count>)`, `private(<names>)`, `shared(<names>)`, `firstprivate(<names>)`, and `reduction(<operator>:<names>)`, where a names field is a comma-separated list of submitted identifiers.

Host OpenMP runtime environment inputs are `OMP_DYNAMIC`, `OMP_THREAD_LIMIT`, `OMP_NUM_THREADS`, and `OMP_MAX_ACTIVE_LEVELS`, supplied as text-valued environment variables.

## `zelvori.stdlib.internal.openmp`

Submitted source imports runtime callables from `zelvori.stdlib.internal.openmp`: `omp_set_num_threads`, `omp_get_num_threads`, `omp_get_max_threads`, `omp_get_thread_num`, `omp_in_parallel`, `omp_get_level`, `omp_get_ancestor_thread_num`, `omp_get_team_size`.

## `zelvori.stdlib.internal.openmp.omp_set_num_threads`

`omp_set_num_threads(num_threads: int32)` is a callable imported inside submitted source from `zelvori.stdlib.internal.openmp`. The argument is a NumPy `int32` scalar.

## `zelvori.stdlib.internal.openmp.omp_get_num_threads`

`omp_get_num_threads()` is a callable imported inside submitted source from `zelvori.stdlib.internal.openmp`. Returns an integer team-size value.

## `zelvori.stdlib.internal.openmp.omp_get_max_threads`

`omp_get_max_threads()` is a callable imported inside submitted source from `zelvori.stdlib.internal.openmp`. Returns an integer maximum-team-size value.

## `zelvori.stdlib.internal.openmp.omp_get_thread_num`

`omp_get_thread_num()` is a callable imported inside submitted source from `zelvori.stdlib.internal.openmp`. Returns an integer thread identifier.

## `zelvori.stdlib.internal.openmp.omp_in_parallel`

`omp_in_parallel()` is a callable imported inside submitted source from `zelvori.stdlib.internal.openmp`. Returns a Boolean region-state value.

## `zelvori.stdlib.internal.openmp.omp_get_level`

`omp_get_level()` is a callable imported inside submitted source from `zelvori.stdlib.internal.openmp`. Returns an integer nesting-level value.

## `zelvori.stdlib.internal.openmp.omp_get_ancestor_thread_num`

`omp_get_ancestor_thread_num(level: int32)` is a callable imported inside submitted source from `zelvori.stdlib.internal.openmp`. The argument is a NumPy `int32` scalar. Returns an integer ancestor thread identifier.

## `zelvori.stdlib.internal.openmp.omp_get_team_size`

`omp_get_team_size(level: int32)` is a callable imported inside submitted source from `zelvori.stdlib.internal.openmp`. The argument is a NumPy `int32` scalar. Returns an integer team-size value for the supplied level.

## `numpy`

Submitted source names the numerical module `numpy`, using ordinary module imports, renamed imports, or imported member names. Callable members are `array`, `zeros`, `ones`, `empty`, `full`, `arange`, `linspace`, `zeros_like`, `ones_like`, `full_like`, `empty_like`, `copy`, `sum`, `amin`, `amax`, `prod`, `matmul`, `vecdot`, `cross`, `where`, `count_nonzero`, `nonzero`, `transpose`, `result_type`, `arctan2`, `absolute`, `sqrt`, `exp`, `expm1`, `log`, `sin`, `cos`, `tan`, `arcsin`, `arccos`, `arctan`, `sinh`, `cosh`, `tanh`, `arcsinh`, `arccosh`, `arctanh`, `floor`, `sign`, `isnan`, `isinf`, `isfinite`. Numerical type names are `int8`, `int16`, `int32`, `int64`, `float32`, `float64`, `complex64`, and `complex128`.

## `numpy.array`

In submitted source, `array(<data>, dtype=..., order=...)` is imported from `numpy`. An ndarray result. Keywords shown with `...` are optional; these markers denote omitted keyword values, not literal arguments.

## `numpy.zeros`

In submitted source, `zeros(<shape>, dtype=..., order=...)` is imported from `numpy`. An ndarray result. Keywords shown with `...` are optional; these markers denote omitted keyword values, not literal arguments.

## `numpy.ones`

In submitted source, `ones(<shape>, dtype=..., order=...)` is imported from `numpy`. An ndarray result. Keywords shown with `...` are optional; these markers denote omitted keyword values, not literal arguments.

## `numpy.empty`

In submitted source, `empty(<shape>, dtype=..., order=...)` is imported from `numpy`. An ndarray result. Keywords shown with `...` are optional; these markers denote omitted keyword values, not literal arguments.

## `numpy.full`

In submitted source, `full(<shape>, <fill-value>, dtype=..., order=...)` is imported from `numpy`. An ndarray result. Keywords shown with `...` are optional; these markers denote omitted keyword values, not literal arguments.

## `numpy.arange`

In submitted source, `arange(<stop>)`, `arange(<start>, <stop>)`, or `arange(<start>, <stop>, <step>)` is imported from `numpy`. An ndarray result.

## `numpy.linspace`

In submitted source, `linspace(<start>, <stop>, <num>, endpoint=..., dtype=...)` is imported from `numpy`. An ndarray result; the third positional argument is optional. Keywords shown with `...` are optional; these markers denote omitted keyword values, not literal arguments.

## `numpy.zeros_like`

In submitted source, `zeros_like(<array>)` is imported from `numpy`. An ndarray result.

## `numpy.ones_like`

In submitted source, `ones_like(<array>)` is imported from `numpy`. An ndarray result.

## `numpy.full_like`

In submitted source, `full_like(<array>, <fill-value>, dtype=..., shape=..., order=...)` is imported from `numpy`. An ndarray result. Keywords shown with `...` are optional; these markers denote omitted keyword values, not literal arguments.

## `numpy.empty_like`

In submitted source, `empty_like(<array>, dtype=..., shape=..., order=...)` is imported from `numpy`. An ndarray result. Keywords shown with `...` are optional; these markers denote omitted keyword values, not literal arguments.

## `numpy.copy`

In submitted source, `copy(<array>)` is imported from `numpy`. An ndarray result.

## `numpy.sum`

In submitted source, `sum(<array>, axis=..., dtype=..., initial=..., keepdims=..., out=...)` is imported from `numpy`. A numerical scalar or ndarray result; out supplies an ndarray result destination. Keywords shown with `...` are optional; these markers denote omitted keyword values, not literal arguments.

## `numpy.amin`

In submitted source, `amin(<array>, axis=..., initial=..., keepdims=..., out=...)` is imported from `numpy`. A numerical scalar or ndarray result; out supplies an ndarray result destination. Keywords shown with `...` are optional; these markers denote omitted keyword values, not literal arguments.

## `numpy.amax`

In submitted source, `amax(<array>, axis=..., initial=..., keepdims=..., out=...)` is imported from `numpy`. A numerical scalar or ndarray result; out supplies an ndarray result destination. Keywords shown with `...` are optional; these markers denote omitted keyword values, not literal arguments.

## `numpy.prod`

In submitted source, `prod(<array>)` is imported from `numpy`. A numerical scalar result.

## `numpy.matmul`

In submitted source, `matmul(<left>, <right>)` is imported from `numpy`. An ndarray result.

## `numpy.vecdot`

In submitted source, `vecdot(<left>, <right>, axis=..., out=...)` is imported from `numpy`. A numerical scalar or ndarray result; out supplies an ndarray result destination. Keywords shown with `...` are optional; these markers denote omitted keyword values, not literal arguments.

## `numpy.cross`

In submitted source, `cross(<left>, <right>, axisa=..., axisb=..., axisc=...)` is imported from `numpy`. An ndarray result. Keywords shown with `...` are optional; these markers denote omitted keyword values, not literal arguments.

## `numpy.where`

In submitted source, `where(<condition>, <left>, <right>)` is imported from `numpy`. An ndarray result.

## `numpy.count_nonzero`

In submitted source, `count_nonzero(<array>, axis=..., keepdims=...)` is imported from `numpy`. An integer scalar or integer ndarray result. Keywords shown with `...` are optional; these markers denote omitted keyword values, not literal arguments.

## `numpy.nonzero`

In submitted source, `nonzero(<array>)` is imported from `numpy`. A tuple with an integer-index ndarray component.

## `numpy.transpose`

In submitted source, `transpose(<array>)` is imported from `numpy`. An ndarray result.

## `numpy.result_type`

In submitted source, `result_type(<values-or-types> ...)` is imported from `numpy`. A NumPy data-type result usable in the dtype keyword of an array-creation call.

## `numpy.arctan2`

In submitted source, `arctan2(<left>, <right>)` is imported from `numpy`. A numerical scalar or ndarray result.

## `numpy.absolute`

In submitted source, `absolute(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.sqrt`

In submitted source, `sqrt(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.exp`

In submitted source, `exp(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.expm1`

In submitted source, `expm1(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.log`

In submitted source, `log(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.sin`

In submitted source, `sin(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.cos`

In submitted source, `cos(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.tan`

In submitted source, `tan(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.arcsin`

In submitted source, `arcsin(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.arccos`

In submitted source, `arccos(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.arctan`

In submitted source, `arctan(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.sinh`

In submitted source, `sinh(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.cosh`

In submitted source, `cosh(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.tanh`

In submitted source, `tanh(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.arcsinh`

In submitted source, `arcsinh(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.arccosh`

In submitted source, `arccosh(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.arctanh`

In submitted source, `arctanh(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.floor`

In submitted source, `floor(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.sign`

In submitted source, `sign(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.isnan`

In submitted source, `isnan(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.isinf`

In submitted source, `isinf(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.isfinite`

In submitted source, `isfinite(<value>)` is imported from `numpy`. A numerical or Boolean scalar or ndarray result.

## `numpy.int8`

`int8` is a numerical type name imported from `numpy`, used in submitted annotations and array `dtype` descriptions.

## `numpy.int16`

`int16` is a numerical type name imported from `numpy`, used in submitted annotations and array `dtype` descriptions.

## `numpy.int32`

`int32` is a numerical type name imported from `numpy`, used in submitted annotations and array `dtype` descriptions.

## `numpy.int64`

`int64` is a numerical type name imported from `numpy`, used in submitted annotations and array `dtype` descriptions.

## `numpy.float32`

`float32` is a numerical type name imported from `numpy`, used in submitted annotations and array `dtype` descriptions.

## `numpy.float64`

`float64` is a numerical type name imported from `numpy`, used in submitted annotations and array `dtype` descriptions.

## `numpy.complex64`

`complex64` is a numerical type name imported from `numpy`, used in submitted annotations and array `dtype` descriptions.

## `numpy.complex128`

`complex128` is a numerical type name imported from `numpy`, used in submitted annotations and array `dtype` descriptions.

## `numpy.linalg`

Submitted source imports `norm` from `numpy.linalg`.

## `numpy.linalg.norm`

In submitted source, `norm(<array>, ord=..., axis=..., keepdims=...)` is imported from `numpy.linalg`. The shown keywords are optional; `ord` is a real or infinite order, `axis` is an integer axis, and `keepdims` is Boolean. The result is a numerical scalar or ndarray.

## `numpy.random`

Submitted source imports `rand` and `randint` from `numpy.random`.

## `numpy.random.rand`

In submitted source, `rand()` or `rand(<dimension>, ...)` is imported from `numpy.random`. Dimensions are integer scalars. The result is a numerical scalar or ndarray.

## `numpy.random.randint`

In submitted source, `randint(<high>)` or `randint(<low>, <high>, size=..., dtype=...)` is imported from `numpy.random`. Bounds are integer scalars; optional `size` is a shape tuple and optional `dtype` is a numerical type description. The result is an integer scalar or ndarray.

## `math`

Submitted source imports mathematical callables from `math`: `fabs`, `exp`, `sin`, `cos`, `tan`, `atan`, `sinh`, `cosh`, `tanh`, `asinh`, `floor`, `ceil`, `trunc`, `erf`, `erfc`, `sqrt`, `log`, `log10`, `asin`, `acos`, `atanh`, `acosh`, `gamma`, `lgamma`, `atan2`, `copysign`, `hypot`, `log2`, `log1p`, `expm1`, `ldexp`, `remainder`, `factorial`, `gcd`, `lcm`, `degrees`, `radians`, `isfinite`, `isinf`, `isnan`. Named numerical constants are `pi`, `e`, and `tau`.

## `math.fabs`

In submitted source, `fabs(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.exp`

In submitted source, `exp(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.sin`

In submitted source, `sin(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.cos`

In submitted source, `cos(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.tan`

In submitted source, `tan(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.atan`

In submitted source, `atan(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.sinh`

In submitted source, `sinh(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.cosh`

In submitted source, `cosh(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.tanh`

In submitted source, `tanh(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.asinh`

In submitted source, `asinh(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.floor`

In submitted source, `floor(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.ceil`

In submitted source, `ceil(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.trunc`

In submitted source, `trunc(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.erf`

In submitted source, `erf(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.erfc`

In submitted source, `erfc(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.sqrt`

In submitted source, `sqrt(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.log`

In submitted source, `log(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.log10`

In submitted source, `log10(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.asin`

In submitted source, `asin(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.acos`

In submitted source, `acos(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.atanh`

In submitted source, `atanh(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.acosh`

In submitted source, `acosh(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.gamma`

In submitted source, `gamma(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.lgamma`

In submitted source, `lgamma(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.atan2`

In submitted source, `atan2(<real>, <real>)` is imported from `math`. Its result is a numerical scalar.

## `math.copysign`

In submitted source, `copysign(<real>, <real>)` is imported from `math`. Its result is a numerical scalar.

## `math.hypot`

In submitted source, `hypot(<real>, <real>)` is imported from `math`. Its result is a numerical scalar.

## `math.log2`

In submitted source, `log2(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.log1p`

In submitted source, `log1p(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.expm1`

In submitted source, `expm1(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.ldexp`

In submitted source, `ldexp(<real>, <integer>)` is imported from `math`. Its result is a numerical scalar.

## `math.remainder`

In submitted source, `remainder(<real>, <real>)` is imported from `math`. Its result is a numerical scalar.

## `math.factorial`

In submitted source, `factorial(<integer>)` is imported from `math`. Its result is a numerical scalar.

## `math.gcd`

In submitted source, `gcd(<integer>, <integer>)` is imported from `math`. Its result is a numerical scalar.

## `math.lcm`

In submitted source, `lcm(<integer>, <integer>)` is imported from `math`. Its result is a numerical scalar.

## `math.degrees`

In submitted source, `degrees(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.radians`

In submitted source, `radians(<real>)` is imported from `math`. Its result is a numerical scalar.

## `math.isfinite`

In submitted source, `isfinite(<real>)` is imported from `math`. Its result is a Python Boolean scalar.

## `math.isinf`

In submitted source, `isinf(<real>)` is imported from `math`. Its result is a Python Boolean scalar.

## `math.isnan`

In submitted source, `isnan(<real>)` is imported from `math`. Its result is a Python Boolean scalar.

## `math.pi`

`pi` is a named numerical scalar constant imported from `math` in submitted source.

## `math.e`

`e` is a named numerical scalar constant imported from `math` in submitted source.

## `math.tau`

`tau` is a named numerical scalar constant imported from `math` in submitted source.

## `cmath`

Submitted source imports mathematical callables from `cmath`: `sqrt`, `exp`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `sinh`, `cosh`, `tanh`, `asinh`, `acosh`, `atanh`, `phase`, `polar`, `rect`.

## `cmath.sqrt`

In submitted source, `sqrt(<complex>)` is imported from `cmath`. Its result is a complex scalar.

## `cmath.exp`

In submitted source, `exp(<complex>)` is imported from `cmath`. Its result is a complex scalar.

## `cmath.sin`

In submitted source, `sin(<complex>)` is imported from `cmath`. Its result is a complex scalar.

## `cmath.cos`

In submitted source, `cos(<complex>)` is imported from `cmath`. Its result is a complex scalar.

## `cmath.tan`

In submitted source, `tan(<complex>)` is imported from `cmath`. Its result is a complex scalar.

## `cmath.asin`

In submitted source, `asin(<complex>)` is imported from `cmath`. Its result is a complex scalar.

## `cmath.acos`

In submitted source, `acos(<complex>)` is imported from `cmath`. Its result is a complex scalar.

## `cmath.atan`

In submitted source, `atan(<complex>)` is imported from `cmath`. Its result is a complex scalar.

## `cmath.sinh`

In submitted source, `sinh(<complex>)` is imported from `cmath`. Its result is a complex scalar.

## `cmath.cosh`

In submitted source, `cosh(<complex>)` is imported from `cmath`. Its result is a complex scalar.

## `cmath.tanh`

In submitted source, `tanh(<complex>)` is imported from `cmath`. Its result is a complex scalar.

## `cmath.asinh`

In submitted source, `asinh(<complex>)` is imported from `cmath`. Its result is a complex scalar.

## `cmath.acosh`

In submitted source, `acosh(<complex>)` is imported from `cmath`. Its result is a complex scalar.

## `cmath.atanh`

In submitted source, `atanh(<complex>)` is imported from `cmath`. Its result is a complex scalar.

## `cmath.phase`

In submitted source, `phase(<complex>)` is imported from `cmath`. Its result is a real scalar.

## `cmath.polar`

In submitted source, `polar(<complex>)` is imported from `cmath`. Its result is a tuple `(<magnitude-real>, <phase-real>)`.

## `cmath.rect`

In submitted source, `rect(<real>, <real>)` is imported from `cmath`. Its result is a complex scalar.

## `builtins.bool`

Submitted source uses the built-in call form `bool(<value>)`. The result is a Boolean scalar.

## `builtins.int`

Submitted source uses the built-in call form `int(<value>)`. The result is an integer scalar.

## `builtins.float`

Submitted source uses the built-in call form `float(<value>)`. The result is a real scalar.

## `builtins.complex`

Submitted source uses the built-in call form `complex(<real>)` or `complex(<real>, <imaginary>)` or `complex(<complex>)`. The result is a complex scalar with numerical real and imag attributes.

## `builtins.abs`

Submitted source uses the built-in call form `abs(<number>)`. The result is a numerical scalar.

## `builtins.round`

Submitted source uses the built-in call form `round(<number>)` or `round(<number>, <digits>)`. The result is a numerical scalar.

## `builtins.isinstance`

Submitted source uses the built-in call form `isinstance(<value>, <type>)`. The result is a Boolean scalar.

## `builtins.len`

Submitted source uses the built-in call form `len(<sequence-or-set>)`. The result is an integer scalar.

## `builtins.sum`

Submitted source uses the built-in call form `sum(<iterable>)`. The result is a numerical scalar.

## `builtins.min`

Submitted source uses the built-in call form `min(<values> ...)` or `min(<generator>)`. The result is a numerical scalar.

## `builtins.max`

Submitted source uses the built-in call form `max(<values> ...)` or `max(<generator>)`. The result is a numerical scalar.

## `builtins.range`

Submitted source uses the built-in call form `range(<stop>)`, `range(<start>, <stop>)`, or `range(<start>, <stop>, <step>)`. The result is an integer iterable in submitted loop syntax.

## `builtins.enumerate`

Submitted source uses the built-in call form `enumerate(<iterable>)`. The result is an iterable of `(index, value)` pairs in submitted loops.

## `builtins.zip`

Submitted source uses the built-in call form `zip(<iterable>, <iterable>, ...)`. The result is an iterable of tuples in submitted loops.

## `builtins.map`

Submitted source uses the built-in call form `map(<function>, <iterable>)`. The result is an iterable of function results in submitted loops.

## `itertools`

Submitted source imports `product` from `itertools`.

## `itertools.product`

In submitted source, `product(<iterable>, <iterable>, ...)` is imported from `itertools`. It is an iterable whose entries are tuples, used in submitted loops.
