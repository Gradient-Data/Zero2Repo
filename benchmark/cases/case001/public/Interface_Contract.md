# Interface Contract

## Product overview

**Tomlparse** is a Python library that reads TOML text and returns ordinary Python values. It is a parser only: it does not write TOML, and it does not preserve comments, ordering of presentation, or other style. The language this product implements is **TOML v1.1.0**. What each entry does with a document is specified in the PRD; this Contract states the shell only: the package, its entries, what each accepts, and the form of every result and failure.

The finished product is an **importable Python library**, not a command-line program, not a network service, and not a wire protocol. There is no dump, write, or encode entry, no console script, no `python -m` program, and no product-owned configuration file. Parse entries return or raise; they do not print, read or write files of their own, mutate the process environment, or exit the host process.

The product is a pure-Python library with zero runtime third-party dependencies, for Python 3.8 or newer (CPython and PyPy), on Linux, macOS, and Windows, CPU-only.

## Shape of the public surface

The public surface is the importable package `tomlparse`, a single top-level directory named `tomlparse` under `src` (src layout). The installable distribution name is also `tomlparse`. Importing the package performs no I/O against caller files, starts no processes, and opens no sockets.

These names are importable from the package root, as `tomlparse.<name>` and as `from tomlparse import <name>`:

- `loads` — parse a document from a Python text string.
- `load` — parse a document from a binary file object.
- `TOMLDecodeError` — the parse-failure exception class.

Any other module, name, or internal layout inside the package is the implementer's choice.

## `tomlparse.loads`

### Signature

```
loads(s, *, parse_float=float) -> dict
```

- `s` — the TOML document, a Python `str`, passed positionally.
- `parse_float` — keyword-only, optional. A callable taking one `str` (a float's characters as written in the document) and returning the value to store for that float. Default: the builtin `float`.

### Return shape

On success, a `dict` (the document mapping), never `None`:

- keys: `str`;
- tables and inline tables: `dict` with `str` keys;
- arrays and arrays of tables: `list`, elements in document order;
- strings: `str`; integers: `int` (never `bool`); booleans: `bool`;
- floats: `float` by default, or the value `parse_float` returned for that float;
- offset date-time: `datetime.datetime` with a `tzinfo` whose `utcoffset()` is the written offset;
- local date-time: `datetime.datetime` with `tzinfo` `None`;
- local date: `datetime.date`;
- local time: `datetime.time` with `tzinfo` `None`.

An empty document yields an empty `dict`.

### Failures

| Condition | What is raised |
| --- | --- |
| `s` is not a `str` | `TypeError` (not a `TOMLDecodeError`) |
| `s` is not a valid TOML v1.1.0 document | `TOMLDecodeError` |
| `parse_float` returned a `dict` or `list` (or a subclass instance) | `ValueError` that is not a `TOMLDecodeError` |

In every failure no mapping is returned. Message wording of `TypeError` and `ValueError` is the implementer's choice.

## `tomlparse.load`

### Signature

```
load(fp, *, parse_float=float) -> dict
```

- `fp` — an already-open file object for binary reading (an on-disk file opened in binary mode or an in-memory binary buffer), passed positionally. The entry reads its contents; it never takes a filesystem path.
- `parse_float` — as for `loads`.

### Return shape

The same `dict` form as `loads` for the decoded text. A file with no bytes yields an empty `dict`.

### Failures

| Condition | What is raised |
| --- | --- |
| `fp` is a text-mode file object | `TypeError` (not a `TOMLDecodeError`) |
| the bytes are not valid UTF-8 | an exception (its type is the implementer's choice); no mapping is returned |
| the decoded text is not valid TOML v1.1.0 | `TOMLDecodeError`, with `doc` the decoded text (not bytes) |
| `parse_float` returned a `dict` or `list` (or a subclass instance) | `ValueError` that is not a `TOMLDecodeError` |

## `tomlparse.TOMLDecodeError`

An exception class (a type, not a factory function), a subclass of `ValueError`. It is not a subclass of `TypeError` or `RecursionError`.

### Constructor

```
TOMLDecodeError(msg, doc, pos)
```

- `msg` — `str`, the unformatted reason.
- `doc` — `str`, the document text.
- `pos` — `int`, a 0-based character offset into `doc`.

Callers may construct an instance themselves with these three arguments; the parse entries raise instances built the same way.

### Attributes

Every instance, constructed or raised, exposes:

| Attribute | Type | Meaning |
| --- | --- | --- |
| `msg` | `str` | the unformatted reason (wording is the implementer's choice for raised instances) |
| `doc` | `str` | the document text |
| `pos` | `int` | the 0-based character offset into `doc` |
| `lineno` | `int` | the 1-based line of `pos` in `doc` |
| `colno` | `int` | the 1-based column of `pos` in `doc` |

### Formatted report

`str(err)` is a text report that contains the reason and the location (`lineno` and `colno` for an offset inside `doc`, or a mention of the end of the document for an offset at or past its end). Its wording and layout are the implementer's choice.
