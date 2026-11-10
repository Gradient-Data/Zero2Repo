# Interface Contract

The Python package is `velnora`, importable from the project root. Run `python -m velnora` from the source project's working directory; the package root can be supplied through `PYTHONPATH`. Source and report text, stdout and stderr use UTF-8 (`utf-8`).

An ordinary successful check exits `0` with empty `stderr`. An ordinary check with findings exits `1` and writes diagnostics to `stderr`. Source-input and configuration failures also exit `1`, with a failure report on `stderr`. Option inspection exits `0`, writes its result to `stdout`, and leaves `stderr` empty.

## `python -m velnora`

### Invocation

`python -m velnora [options] [<target> ...]`

Each positional target is a Python source file or directory path. `--code <source>` supplies Python source as one string argument.

| Option | Argument or mode |
| --- | --- |
| `--fail-after-first` | First-error mode; no argument |
| `--enable-all` | Collective enable switch; no argument |
| `--disable-all` | Collective disable switch; no argument |
| `--enable` | Diagnostic category name; repeatable |
| `--disable` | Diagnostic category name; repeatable |
| `--config-file` | TOML configuration path |
| `--json-output` | JSON report destination path |
| `--markdown-output` | Markdown report destination path |
| `--output-format` | `detailed` or `concise` |
| `--display-options` | Option inspection; no argument |
| `--import-paths` | Import-directory path; repeatable |
| `--stub-path` | Stub-directory path; repeatable |
| `--typeshed-path` | Standard-library stub-directory path |
| `--disallowed-imports` | Module name; repeatable |
| `--ignored-callees` | Dotted Python object name; repeatable |
| `--constructor-hooks` | Dotted Python callable name; repeatable |
| `--find-unused` | Unused-object search; no argument |
| `--find-unused-attributes` | Unused-member search; no argument |
| `--find-unused-call-patterns` | Unused-call-alternative search; no argument |
| `--autofix` | Automatic source editing; no argument |
| `-f` | Interactive source editing; no argument |
| `--add-ignores` | Suppression-comment edits in the editing workflow; no argument |

### Diagnostic text

Detailed diagnostics on stderr carry a line `<explanation> (code: <category>)`, a location line `In <filename> at line <line>`, and source context. Concise diagnostics carry `<filename>:<line>:<column>: <explanation> [<category>]`. Lines are one-based; columns are zero-based UTF-8 byte offsets. Inline source is named `<code>`.

Source-input failure reports on stderr identify the source path. Unreadable-source failures use a terminal exception line `[<module>.]FileNotFoundError: <explanation>`; source-syntax failures use `[<module>.]SyntaxError: <explanation>`. Execution-failure explanations carry the original exception class and cause. First-error termination has exit status `1` and uses the diagnostic presentation above.

### Option display

`--display-options` writes named blocks to stdout:

```text
Options:
    <setting> (value: <effective-value>)
        <configured-value> (from command line)
        <configured-value> (from config file)
        <configured-value> (module: <qualified-module>, from config file)
```

The indents are four spaces for a setting and eight for an override. Boolean displays are `True` and `False`. String sequences use Python list-literal syntax. Path sequences use `[PosixPath(<quoted-path>), ...]`. Callable sequence entries have the form `<function <name> at 0x<hex-address>>` inside a comma-separated list. Override lines identify their source and applicable module selector.

### Usage-search output

Unused-object search writes `<qualified-object>: <status>` lines to stdout. Status labels are `unused` and `used only in tests`. Its JSON records carry the same string in `description`; these findings produce exit status `1` without ordinary stderr diagnostics.

Unused-member search writes `Unused attribute: <class '<qualified-class>'>.<member>` and `Unused method: <class '<qualified-class>'>.<member>` lines to stdout. These lines alone leave the process at status `0` with empty stderr.

Unused-call-alternative findings carry `Unused call pattern: <qualified-callable> parameter '<parameter>' <explanation>` in JSON `description`, with diagnostics on stderr and status `1`.

The call-alternative detail ends with one of the following labeled payloads. `<explanation>` is nonempty explanatory text preceding the payload marker.

| Detail form | Payload meaning |
| --- | --- |
| `<explanation> omitted` | The parameter is supplied only by omission |
| `<explanation> literal <boolean>` | The observed Boolean value, written as a Python Boolean literal |
| `<explanation> receives <unobserved-types> (observed <observed-types>)` | The unobserved and observed members of the parameter's union |

Each type-list payload is a Python type expression consisting of built-in type names joined by `|`, or a single such name. The labels `omitted`, `literal`, `receives`, and `observed` delimit the payload; the preceding explanatory sentences are not fixed.


### Source editing

Edited output is UTF-8 Python source at the submitted source path. In a controlling terminal, the edit prompt has the prefix `Accept change (`. Input is `y` or `n` followed by a newline, for acceptance or rejection respectively. Interactive and automatic edit runs reporting a finding exit `1`.

## `--json-output`

When produced, a report at the path passed to `--json-output` is a JSON array of diagnostic objects, encoded as UTF-8.

| Field | Form and meaning |
| --- | --- |
| `filename` | String: source path, or `<code>` for inline source |
| `lineno` | Integer: one-based source line |
| `col_offset` | Integer: zero-based UTF-8 byte offset within the source line |
| `code` | String: diagnostic category |
| `description` | String: explanation of the finding |
| `message` | String: detailed diagnostic presentation |
| `concise_message` | String: concise diagnostic presentation and explanatory detail |

Located source findings expose the location and category fields above. Usage-search records expose the `description` forms specified with the command. The `concise_message` detail carries user-supplied rejection reasons and original exception class and cause where those constitute the explanation. Declarative call restrictions use detail labels `Argument <parameter> <explanation>` and `Platform (<actual-platform>) <explanation>`.

Annotation-suggestion records additionally carry `extra_metadata`, an object containing `suggested_type` (a Python annotation-expression string) and `imports` (a list of module-name strings). The expression's namespace includes built-in and typing names, the modules `builtins` and `typing`, and the top-level module bindings named by `imports`.

Diagnostic category strings are also category-selection arguments, Boolean configuration keys and suppression-comment categories. Their failure or observation meanings are:

| Category | Meaning |
| --- | --- |
| `attribute_is_never_set` | An attribute that is read on objects of a particular type is never set on that object. |
| `bad_async_yield` | Yield of an invalid value in an async function |
| `bad_evaluator` | Invalid declarative type-evaluation statement, condition or argument reference. |
| `bad_except_handler` | Invalid except clause |
| `bad_exception` | An object that is not an exception is raised |
| `bad_format_string` | Invalid percent-formatting pattern or operand binding. |
| `bad_match` | Invalid class-pattern attribute selection. |
| `bad_unpack` | Error in an unpacking assignment. |
| `bare_ignore` | Ignore comment without an error code |
| `deprecated` | Use of deprecated feature |
| `disallowed_import` | Disallowed import |
| `duplicate_dict_key` | Duplicate key in a dictionary. |
| `duplicate_enum_member` | Duplicate enum member |
| `duplicate_yield` | Duplicate yield of the same value in an async function |
| `generator_return` | Generator declaration with a non-iterable return annotation. |
| `import_failed` | Failed to import module |
| `impossible_pattern` | Pattern can never match |
| `impure_async_call` | Non-async call to an async function within another async function. |
| `incompatible_argument` | Argument-type incompatibility, including failure to match overload argument types; invalid typed-mapping value, required-field removal, or invalid known-key mapping removal. |
| `incompatible_assignment` | Assignment incompatibility, including forbidden attribute writes or deletions and writes outside closed slots. |
| `incompatible_call` | Call binding failure; invalid replacement-field format invocation or regular-expression operation; rejected approved evaluation or declarative call restriction; abstract construction, invalid functional named-tuple declaration, or fixed-tuple index outside its range. |
| `incompatible_default` | Default value incompatible with argument type |
| `incompatible_override` | Incompatible member override, final-member override, or data-class post-initialization contract. |
| `incompatible_return_value` | Incompatible return value |
| `incompatible_yield` | Generator yielded-value or delegated yield/send incompatibility. |
| `inconsistent_overload` | Overload signature is incompatible with its implementation. |
| `inference_failure` | Inferred-type assertion mismatch. |
| `invalid_annotation` | Invalid annotation expression or type-argument kind; incompatible annotated enumeration value. |
| `invalid_base` | Invalid base declaration, including final-class inheritance, repeated generic parameters or conflicting ancestor specializations. |
| `invalid_context_manager` | Invalid synchronous or asynchronous context-manager contract. |
| `invalid_dataclass` | Invalid dataclass definition |
| `invalid_literal` | Invalid argument to Literal[] |
| `invalid_metaclass` | Invalid metaclass declaration. |
| `invalid_namedtuple` | Invalid NamedTuple definition |
| `invalid_override_decorator` | @override decorator in invalid location |
| `invalid_qualifier` | Invalid use of an annotation qualifier |
| `invalid_regex` | Malformed pattern supplied to a valid-pattern annotation. |
| `invalid_self_usage` | Invalid use of Self in an annotation |
| `invalid_specialization` | Invalid generic specialization arity or bound/constraint satisfaction. |
| `invalid_type_alias` | Invalid type alias definition |
| `invalid_type_parameter_default` | Invalid type parameter default |
| `invalid_typeddict` | Invalid TypedDict definition |
| `invalid_typeddict_key` | Invalid key in TypedDict |
| `missing_asynq` | This function should have an @asynq() decorator |
| `missing_await` | Missing await in async code |
| `missing_f` | f missing from f-string |
| `missing_generic_parameters` | Missing type parameters for generic type |
| `missing_parameter_annotation` | Missing function parameter annotation |
| `missing_return` | Function may exit without returning a value |
| `missing_return_annotation` | Missing function return annotation |
| `multiple_dataclass_transform` | Multiple dataclass transforms on the same class |
| `must_use` | Value cannot be discarded |
| `no_return_may_return` | Normal return in a declaration that promises no normal return. |
| `not_callable` | Attempt to call an object that is not callable. |
| `override_does_not_override` | Method does not override any base method |
| `possibly_undefined_name` | Variable may be uninitialized |
| `private_import` | Use of a private object from another module |
| `readonly_typeddict` | TypedDict is read-only |
| `reveal_type` | Inferred expression or local-type revelation. |
| `suggested_parameter_type` | Suggested parameter type |
| `suggested_return_type` | Suggested return type |
| `task_needs_yield` | You probably forgot to yield an async task |
| `type_always_true` | Type will always evaluate to 'True' |
| `type_does_not_support_bool` | Type does not support bool() |
| `typeis_must_be_subtype` | TypeIs narrowed type must be a subtype of the input type |
| `undefined_attribute` | Usage of an attribute (e.g. a function in a module) that does not exist. |
| `undefined_name` | Usage of a variable that is never assigned to. |
| `unhashable_key` | Key cannot be inserted into a set or dictionary. |
| `unnecessary_yield` | Unnecessary yield in async function. |
| `unreachable` | Code is unreachable |
| `unsafe_comparison` | Disjoint equality comparison. |
| `unsupported_operation` | Usage of an operation such as subscripting on an object that does not support it. |
| `unused_assignment` | Assigned value is never used |
| `unused_ignore` | Unused '# static analysis: ignore' comment |
| `unused_variable` | Variable is not read after being written to |
| `use_fstrings` | Use f-strings instead of % formatting |
| `value_always_true` | Value will always evaluate to 'True' |
| `yield_without_value` | yield without a value in an async function |

Application-defined categories use the name supplied to `register_error_code`.

## `--markdown-output`

The path passed to `--markdown-output` receives a UTF-8 Markdown document. Each source section has the heading `### <filename-suffix> (<count> failures)`. The filename suffix is the source path after removal of the common path prefix; its leading separator is retained. Entries have the form:

```text
* line <line>: `<explanation> (code: <category>)`
```

`<line>` is the one-based source line. `<count>` is the number of findings in that source section.

## `pyproject.toml`

Configuration files, including `pyproject.toml`, are TOML supplied through `--config-file <path>`, with a `[tool.velnora]` table. `[[tool.velnora.overrides]]` entries contain a `module` string naming a module or package and settings in the same forms. `extend_config` is a configuration-path string.

| Setting | TOML value |
| --- | --- |
| `paths` | Array of source-file or source-directory path strings |
| `import_paths` | Array of import-directory path strings |
| `stub_path` | Array of stub-directory path strings |
| `typeshed_path` | Standard-library stub-directory path string |
| `disallowed_imports` | Array of module-name strings |
| `ignored_callees` | Array of dotted Python object names |
| `classes_checked_for_asynq` | Array of dotted class names |
| `methods_not_checked_for_asynq` | Array of method-name strings |
| `ignored_unused_attribute_paths` | Array of dotted attribute paths |

Diagnostic category names, including registered names, are Boolean setting keys.

Extension settings are arrays of dotted Python callable names:

| Setting | Callback exchange |
| --- | --- |
| `known_signatures` | One context argument; returns a mapping from callable objects to `Signature` objects |
| `constructor_hooks` | One class argument; returns an annotated callable with a receiver parameter, a `Signature` including that parameter, or `None` for no declaration |
| `class_attribute_transformers` | One attribute-object argument; returns a pair of read and write type values, or `None` |
| `known_attribute_hook` | An object and attribute-name string; returns a type value or `None` |
| `unwrap_class` | One class argument; returns a class |
| `functions_safe_to_call` | Names the callable objects approved for evaluation |
| `ignore_unused` | Module, name string, and object arguments; returns a Boolean exemption decision |

## `.pyi`

Stub inputs are Python declaration files. A module stub is `<module>.pyi`; a package stub is `<package>/__init__.pyi`. Stub roots also accept `<module>-stubs/__init__.pyi`. A selected standard-library stub root contains `VERSIONS` and module `.pyi` files. `VERSIONS` is a text mapping with lines `<module>: <major>.<minor>` for a module's starting Python version.

## `# static analysis: ignore`

Python source suppression comments use `# static analysis: ignore`, `# static analysis: ignore[<category>]`, and `# type: ignore`. Category-specific suppression edits are written as `# static analysis: ignore[<category>]` at the associated statement or its preceding line.

## `velnora.ast_annotator`

Importable module `velnora.ast_annotator` exposes `annotate_code` and `annotate_file`.

## `annotate_code`

Import `annotate_code` from `velnora.ast_annotator`. Call `annotate_code(code: str) -> ast.Module` with a source string. The returned tree is traversable using `ast.walk`; expression nodes retain their Python AST node classes and source coordinates. `ast.Constant`, `ast.Name`, and `ast.Attribute` nodes expose `inferred_value`; `str(node.inferred_value)` is a type display. Known scalar values have the display `Literal[<Python literal>]`, with Python literal quoting. `lineno` is one-based and `col_offset` is a zero-based UTF-8 byte offset.

## `annotate_file`

Import `annotate_file` from `velnora.ast_annotator`. Call `annotate_file(path: str | os.PathLike[str]) -> ast.AST` with a source-file path. The returned Python AST has the same expression-node, coordinate, and `inferred_value` interface described for `annotate_code`.

## `velnora.runtime`

Importable module `velnora.runtime` exposes `is_assignable` and `get_assignability_error`.

## `is_assignable`

Import `is_assignable` from `velnora.runtime`. The call `is_assignable(value: object, typ: object) -> bool` takes a runtime value and a Python type annotation. The Boolean result is the assignability decision. The same function name is usable in checked source as a guard.

## `get_assignability_error`

Import `get_assignability_error` from `velnora.runtime`. The call `get_assignability_error(value: object, typ: object) -> str | None` takes a runtime value and a Python type annotation. `None` represents compatibility; a nonempty string explains incompatibility.

Explanation lines use these labels with variable payloads:

```text
Cannot assign <explanation>
In element <index>
In key of key-value pair <pair>
In value of key-value pair <pair>
```

An element index is zero-based. The mapping labels identify whether the key or value is incompatible.

## `velnora.error_code`

Importable module `velnora.error_code` exposes `register_error_code`.

## `register_error_code`

Import `register_error_code` from `velnora.error_code`. `register_error_code(name: str, description: str)` returns a diagnostic-category object with string attributes `name` and `description`, carrying the supplied name and description. This object is accepted as the diagnostic-category argument to a custom call context's `show_error`. The name is the category's spelling in diagnostic output, Boolean configuration settings, and category-specific suppression comments.

## `velnora.extensions.CustomCheck`

`velnora.extensions.CustomCheck` is a subclassable annotation-metadata base. Instances are used in `Annotated[<type>, <check>]`.

The callback signatures are `can_assign(self, value, ctx)`, `can_be_assigned(self, value, ctx)`, `walk_values(self)`, and `substitute_typevars(self, typevars)`. Assignment callbacks receive a type value and an opaque context; acceptance is returned as `{}`, and rejection as `CanAssignError(<reason>)`. `walk_values` returns an iterable of referenced type values. `substitute_typevars` receives an object exposing `get_typevar(<parameter>)`, returning the corresponding type value or `None`; the callback returns a custom-check instance.

## `velnora.value.AnyValue`

`velnora.value.AnyValue` is the type-value class for unrestricted types. Custom annotation callbacks can distinguish it with `isinstance(value, AnyValue)`.

## `velnora.value.KnownValue`

`velnora.value.KnownValue(val)` represents a known Python value. It supports `isinstance(value, KnownValue)` and exposes the underlying object in `val`. Instances are also return values of application attribute hooks.

## `velnora.value.TypedValue`

`velnora.value.TypedValue(typ)` takes a Python class and returns a type value for instances of that class. It supports `isinstance(value, TypedValue)` and exposes the class in `typ`. These values are accepted as parameter and return annotations and as application callback results.

## `velnora.value.CanAssignError`

`velnora.value.CanAssignError(message: str)` constructs a custom annotation rejection result. `message` is the supplied explanation, carried in diagnostic detail.

## `velnora.value.TypeVarParam`

`velnora.value.TypeVarParam(typevar, owner=None)` constructs a parameter reference from a Python `TypeVar` and an explicit `owner=None` argument. The reference is accepted by `TypeVarValue` and by a substitution context's `get_typevar`.

## `velnora.value.TypeVarValue`

`velnora.value.TypeVarValue(typevar_param)` constructs a type value from a `TypeVarParam`, usable in the iterable returned by a custom check's `walk_values`.

## `velnora.signature.SigParameter`

`velnora.signature.SigParameter(name: str)` and `SigParameter(name: str, annotation=<type-value>)` construct callable parameter declarations. The resulting objects are accepted in the parameter iterable passed to `Signature.make`.

## `velnora.signature.Signature`

`velnora.signature.Signature.make(parameters, return_annotation)` and `Signature.make(parameters, *, impl=<callback>)` construct callable contracts. Both forms also accept the keyword `callable=<object>`. `parameters` is an iterable of `SigParameter` objects. The positional return annotation is a type value. The optional callable argument identifies the runtime callable. An `impl` callback accepts one custom call context and returns an inferred type value.

## `velnora.signature.CallContext`

An application call callback receives a `velnora.signature.CallContext`. Its `vars` member maps parameter-name strings to type values. `show_error(message: str, error_code)` accepts a supplied explanation and a registered diagnostic-category object. The explanation appears in the emitted diagnostic's `description`.

## `velnora.extensions.Intersection`

Import `Intersection` from `velnora.extensions`. The annotation form is `Intersection[<type>, <type>, ...]`.

## `velnora.extensions.Not`

Import `Not` from `velnora.extensions`. The annotation form is `Not[<type>]`.

## `velnora.extensions.Overlapping`

Import `Overlapping` from `velnora.extensions`. The annotation form is `Overlapping[<type>]`.

## `velnora.extensions.ExternalType`

Import `ExternalType` from `velnora.extensions`. The annotation form is `ExternalType[<dotted-type-path>]`, with a string path naming a Python type.

## `velnora.extensions.LiteralOnly`

Import `LiteralOnly` from `velnora.extensions`. `LiteralOnly()` constructs metadata for `Annotated[<type>, <metadata>]`.

## `velnora.extensions.NoAny`

Import `NoAny` from `velnora.extensions`. `NoAny()` and `NoAny(deep=<bool>)` construct metadata for `Annotated[<type>, <metadata>]`.

## `velnora.extensions.ValidRegex`

Import `ValidRegex` from `velnora.extensions`. `ValidRegex()` constructs metadata for `Annotated[<type>, <metadata>]`.

## `velnora.extensions.ParameterTypeGuard`

Import `ParameterTypeGuard` from `velnora.extensions`. `ParameterTypeGuard[<parameter-name>, <guarded-type>]` is metadata in an `Annotated` return annotation; the parameter name is a string.

## `velnora.extensions.AsynqCallable`

Import `AsynqCallable` from `velnora.extensions`. Its annotation form is `AsynqCallable[[<parameter-types>], <result-type>]`. An annotated callable is invoked as `<callable>(<arguments>)` or through its `.asynq(<arguments>)` member.

## `velnora.find_unused.used`

Import `used` from `velnora.find_unused`. `used(obj)` is usable as the decorator `@used` on an object declaration.

## `velnora.extensions.evaluated`

Import `evaluated` from `velnora.extensions`. Use `@evaluated` on a callable typing declaration. In Python source, the annotated declaration immediately precedes the runtime function implementation with the same name. In a `.pyi` file it is a declaration without that implementation. Declaration results are type expressions in `return` statements; diagnostics are delivered through the source-checking interface.

## `velnora.extensions.is_provided`

Import `is_provided` from `velnora.extensions`. Within an evaluated declaration, `is_provided(arg) -> bool` takes a declaration parameter reference.

## `velnora.extensions.is_positional`

Import `is_positional` from `velnora.extensions`. Within an evaluated declaration, `is_positional(arg) -> bool` takes a declaration parameter reference.

## `velnora.extensions.is_keyword`

Import `is_keyword` from `velnora.extensions`. Within an evaluated declaration, `is_keyword(arg) -> bool` takes a declaration parameter reference.

## `velnora.extensions.is_of_type`

Import `is_of_type` from `velnora.extensions`. Within an evaluated declaration, the call forms are `is_of_type(arg, type)` and `is_of_type(arg, type, exclude_any=<bool>)`, returning a Boolean condition. The arguments are a declaration parameter reference and a type expression.

## `velnora.extensions.show_error`

Import `show_error` from `velnora.extensions`. Within an evaluated declaration, use `show_error(message: str)` or `show_error(message: str, argument=<parameter>)`. The keyword argument names a declaration parameter. The resulting diagnostic carries the supplied explanation in `description` and the offending call or argument's source coordinates.

## `velnora.extensions.reveal_type`

Import `reveal_type` from `velnora.extensions`. Within an evaluated declaration, `reveal_type(value)` takes a declaration parameter reference. Its call-site diagnostic's `description` has the form `Type of <argument> is <quoted-type-display>`, where the display is a Python string literal.

## `velnora.extensions.reveal_locals`

Import `reveal_locals` from `velnora.extensions` and call `reveal_locals()` in checked source. The diagnostic's `message` contains `Revealed local types are: (code: reveal_type)` followed by a newline, four-space-indented `<name>: <type-display>` lines, and a blank-line terminator. Displays use a type name, `Literal[<Python literal>]`, `list[<type>]`, or union members separated by ` | `.

## `typing.reveal_type`

`typing.reveal_type(<expression>)` is a source-level type-revelation call. The diagnostic's `description` has the form `Revealed type is '<type-display>'`. Displays use a type name, `Literal[<Python literal>]`, `list[<type>]`, or union members separated by ` | `.

## `typing.assert_type`

`typing.assert_type(<expression>, <type-expression>)` is a source-level type assertion. Its diagnostic carrier is the source-checking report, using category `inference_failure` and the assertion's source location.

## `typing_extensions.assert_type`

`typing_extensions.assert_type(<expression>, <type-expression>)` is a source-level type assertion with the same diagnostic carrier as `typing.assert_type`.

## `_VALUES_TO_NAMES`

Generated integer-enumeration declarations expose class attributes `_VALUES_TO_NAMES: dict[int, str]` and `_NAMES_TO_VALUES: dict[str, int]`, pairing integer member values and member names.

## `annotated_types`

The importable `annotated_types` module supplies annotation metadata constructors `Gt`, `Ge`, `Lt`, `Le`, `MultipleOf`, `MinLen`, `MaxLen`, `Timezone`, and `Predicate`. Metadata instances appear in `typing.Annotated` or `typing_extensions.Annotated` annotations.

## `Gt`

`annotated_types.Gt(gt)` takes a comparison-bound value and returns annotation metadata.

## `Ge`

`annotated_types.Ge(ge)` takes a comparison-bound value and returns annotation metadata.

## `Lt`

`annotated_types.Lt(lt)` takes a comparison-bound value and returns annotation metadata.

## `Le`

`annotated_types.Le(le)` takes a comparison-bound value and returns annotation metadata.

## `MultipleOf`

`annotated_types.MultipleOf(multiple_of)` takes a numeric divisor and returns annotation metadata.

## `MinLen`

`annotated_types.MinLen(min_length)` takes an integer length bound and returns annotation metadata.

## `MaxLen`

`annotated_types.MaxLen(max_length)` takes an integer length bound and returns annotation metadata.

## `Timezone`

`annotated_types.Timezone(tz)` takes a timezone selector (`None`, `...`, or a timezone object) and returns annotation metadata.

## `Predicate`

`annotated_types.Predicate(func)` takes a callable predicate and returns annotation metadata.

## `asynq`

The importable `asynq` module exposes `asynq`, `AsyncTask`, `ConstFuture`, and `FutureBase`. Checked source uses `@asynq()` declarations, decorated callable invocations, and their `.asynq(<arguments>)` task-call member. `ConstFuture(<value>)` and `FutureBase()` are source-level future constructors.

## `velnora.extensions`

Importable module `velnora.extensions` exposes `CustomCheck`, `Intersection`, `Not`, `Overlapping`, `ExternalType`, `LiteralOnly`, `NoAny`, `ValidRegex`, `ParameterTypeGuard`, `AsynqCallable`, `evaluated`, `is_provided`, `is_positional`, `is_keyword`, `is_of_type`, `show_error`, `reveal_type`, `reveal_locals`.

## `velnora.signature`

Importable module `velnora.signature` exposes `SigParameter`, `Signature`, `CallContext`.

## `velnora.value`

Importable module `velnora.value` exposes `AnyValue`, `KnownValue`, `TypedValue`, `CanAssignError`, `TypeVarParam`, `TypeVarValue`.

## `velnora`

`velnora` provides importable modules `ast_annotator`, `runtime`, `error_code`, `extensions`, `signature`, `value`, and `find_unused`.
