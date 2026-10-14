# Interface Contract

### Product form

pathsel is an importable Python library: the package `pathsel`. It has no command-line program that is part of this surface, no `python -m` entry, no network service, and no configuration file. Outcomes are returned or raised from library calls; library calls do not exit the host process.

### Layout

- The importable package is the single top-level directory `pathsel` at the repository root (flat layout), importable with the repository root on the import path. The installable distribution name is `pathsel`.
- Importing `pathsel` or `pathsel.functions` performs no I/O against caller files, starts no processes, and opens no sockets.

## `pathsel`

Names importable from the package root (`import pathsel`, `from pathsel import …`):

- `search` — callable.
- `compile` — callable. (This is the published name on the package even though it coincides with the host builtin of the same spelling.)

Other names on the package root are the implementer's choice.

## `pathsel.search`

```
search(expression, data, options=None)
```

- `expression` — the PathSel expression, a Python `str`, first positional argument.
- `data` — the document: ordinary Python data (mappings, sequences, `str`, `int`, `float`, `bool`, `None`, and any other host value), second positional argument.
- `options` — an evaluation-options object (see **Evaluation options**) or `None`; third positional argument.

Returns the selected or constructed value as ordinary Python data: objects as mappings, arrays as `list`, strings as `str`, numbers as `int` / `float` (or the host value selected from the document), booleans as `bool`, null as `None`. On refusal it raises (see **Failure carriers**) and returns nothing.

## `pathsel.compile`

```
compile(expression)
```

- `expression` — the PathSel expression, a Python `str`, positional.

Returns a parsed-expression object (never `None`) or raises (see **Failure carriers**). The parsed-expression object's type is the implementer's choice. It exposes:

```
<parsed>.search(value, options=None)
```

- `value` — the document, first positional argument.
- `options` — an evaluation-options object or `None`, second positional argument.

Returns or raises exactly as `pathsel.search`.

## Evaluation options

Any object carrying these two attributes (for example a simple namespace); the library reads them and does not require a particular class:

- `dict_cls` — a mapping type (a class whose instances are created with no arguments and filled by item assignment), or `None`.
- `custom_functions` — a provider instance (see `pathsel.functions.Functions`), or `None`.

Whether the library also publishes its own options class is the implementer's choice.

## `pathsel.functions`

Names importable from the submodule (`from pathsel.functions import …`):

- `Functions` — class.
- `signature` — callable.

### `pathsel.functions.Functions`

```
Functions()
```

No arguments. An instance is a provider implementing the built-in functions. A caller extends it by subclassing:

```
class <Provider>(Functions):
    @signature(<arg-spec>, <arg-spec>, …)
    def _func_<name>(self, <arg>, <arg>, …):
        return <value>
```

- Each attribute whose name is `_func_` followed by `<name>`, and whose value has passed through `signature`, defines the language function `<name>`.
- The implementation receives the provider instance first, then one already-evaluated argument per `<arg-spec>`, in order; its return value is the call's value.
- `<Provider>()` is instantiated with no arguments and attached as `custom_functions`.

### `pathsel.functions.signature`

```
signature(*arguments)
```

- `arguments` — zero or more positional mappings, one per parameter, in call order: `{"types": [<type-name>, …]}`.
- `<type-name>` — one of `"number"`, `"string"`, `"array"`, `"object"`, `"null"`.
- Returns a decorator; applying it to an implementation callable `(provider, *args) -> value` returns a callable suitable as a `_func_<name>` attribute. The decorator does not call the implementation.

## Failure carriers

- Every refusal (empty, incomplete, syntax, zero slice step, unknown function, invalid arity, invalid type) raises an exception that is an instance of `ValueError`.
- The kind of a refusal is carried by the **type of the raised exception**. Type names, and whether the types are importable, are the implementer's choice. The report text is the implementer's choice.
  - Empty-expression: every such refusal raises the same type `<Empty>`.
  - Incomplete-expression: every such refusal raises the same type `<Incomplete>`.
  - Syntax, grammar-level: every such refusal raises the same type `<Syntax>`.
  - Syntax, token-level: raises a type that is a subclass of `<Syntax>` and not `<Syntax>` itself.
  - `<Empty>`, `<Incomplete>` and `<Syntax>` are three different types; a token-level syntax refusal is not an instance of `<Empty>` or of `<Incomplete>`.
  - Zero slice step: every such refusal raises the same type, which is not `<Syntax>`.
  - Unknown-function, invalid-arity, invalid-type: each kind has its own type `<Unknown>`, `<Arity>`, `<Type>`; a refusal of that kind raises that type or a subclass of it, and is not an instance of `<Empty>` or `<Incomplete>`, and its type is not `<Syntax>` itself.
  - No refusal of any other kind (including the other two function-call kinds) is an instance of `<Unknown>`, `<Arity>` or `<Type>`.
- Position: a syntax refusal (grammar-level or token-level) and an incomplete-expression refusal carry an `int` attribute `lex_position` — the position defined in the PRD, between 0 and the expression's length.

## Expression reference value

Searching an expression that is a bare expression reference returns a non-`None` value of the implementer's choice.
