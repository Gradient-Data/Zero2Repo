# Interface Contract

## Product overview

**ymlcodec** is a YAML parser and writer for JavaScript, published as a library. This Contract states its shell: the package, the named exports, their call shapes and options, and the forms of what they return or throw. What the entries compute is stated in the PRD.

The finished product is a **library**, not a network service and not an importable Python package. A command-line convenience also named ymlcodec may ship with it; it is not part of this surface.

## Shape of the public surface

**Distribution and import.** The installable package name and the import specifier are both ymlcodec. The library is an ES module with named exports; callers write `import { load } from 'ymlcodec'` (and the same form for the other named exports below). It is not a default-export singleton.

The package manifest is `package.json` at the built repository root. The ESM library artifact is the file named by `exports["."].import`, or, if that field is absent, by `module`. That file must exist and must be importable as an ES module. A CommonJS build, a browser export, and a `bin` entry may ship alongside; they are not part of this surface.

Importing the module performs no I/O against caller files, starts no processes, and opens no sockets.

**Named exports used by callers:** `load`, `loadAll`, `dump`, `Schema`, `FAILSAFE_SCHEMA`, `JSON_SCHEMA`, `CORE_SCHEMA`, `YAML11_SCHEMA`, `defineScalarTag`, `defineSequenceTag`, `defineMappingTag`, `mapTag`, `realMapTag`, `legacyMapTag`, `mergeTag`. Further exports are the implementer’s choice.

**Outcome channel.** `load`, `loadAll`, and `dump` report outcomes by returning a value or throwing. They do not print and do not exit the host process. There is no product configuration file.

## Naming conventions

**Product and package.** The package name and the import specifier are spelled ymlcodec.

**YAML type names.** The Failsafe / JSON / Core tags are `!!null`, `!!bool`, `!!int`, `!!float`, `!!str`, `!!seq`, `!!map`. The YAML 1.1 extras are `!!binary`, `!!timestamp`, `!!set`, `!!omap`, `!!pairs`, and the merge key `<<`. The long form of the standard prefix is `tag:yaml.org,2002:`. A local tag is written with a single `!` followed by its name (`!<name>`).

**Constructed JavaScript types.** `!!map` is a plain object (a `Map` when `realMapTag` is attached). `!!seq` is an array. `!!str` is a string. `!!null` is `null`. `!!bool` is a boolean. `!!int` and `!!float` are numbers. `!!set` is a `Set`. `!!binary` is a `Uint8Array`. `!!timestamp` is a `Date`. `!!omap` and `!!pairs` are arrays. A text that the active schema does not resolve to another type is a string.

## Parse and dump entries

Named exports. The single-document parse entry is `load`. The multi-document parse entry is `loadAll`. The serialize entry is `dump`.

```
load(input, options?)
loadAll(input, options?)
dump(value, options?)
```

- `load` — `input` is YAML text. Returns exactly one constructed value, or throws.
- `loadAll` — `input` is YAML text. Returns an array of the constructed documents, in stream order (possibly empty), or throws.
- `dump` — `value` is any JavaScript value. Returns YAML text (a string, possibly empty), or throws.

### Thrown failure form

A failed `load`, `loadAll`, or `dump` throws an `Error` object and returns nothing (no partial value, no prefix of a document list). The error class name and the wording of `message` are the implementer’s choice, with these parts fixed for a failed parse:

- `message` — text. When the `filename` option was given, it contains that label.
- `mark` — an object describing the error site, with:
  - `name` — text: the `filename` label given to the call, or the empty string when none was given.
  - `line` — an integer: the number of line breaks in the input before the error site (counted from zero; a carriage-return/line-feed pair is one break).
  - Further fields on `mark` and on the error are the implementer’s choice.

### Parse option keys

The options object accepted by `load` and `loadAll` uses these keys; every key may be omitted:

- `schema` — a `Schema` value (a built-in schema export or the result of `withTags` / `new Schema`). When omitted, `CORE_SCHEMA` is used.
- `filename` — text, the source-path label carried by a failure.
- `json` — boolean, the JSON-parse compatibility switch for duplicate keys. Default `false`.
- `maxDepth` — a positive integer, the collection nesting limit. Has a default when omitted.
- `maxAliases` — an integer, the alias budget per document. `-1` means unlimited; `0` allows none. Has a default when omitted.
- `maxTotalMergeKeys` — an integer, the merge-key budget per call. `-1` disables the budget. Has a default when omitted.

### Dump option keys

The options object accepted by `dump` uses these keys; every key may be omitted, and each omitted key takes its default:

- `schema` — a `Schema` value. When omitted, the default dump schema is used.
- `indent` — integer, spaces per indentation level.
- `lineWidth` — integer, the line width in columns; `-1` means unlimited.
- `flowLevel` — integer, the nesting depth from which nodes are written in flow style (`0` is the root); `-1` means never. Default `-1`.
- `seqNoIndent` — boolean; `true` is the “no extra sequence indent” switch. Default `false`.
- `seqInlineFirst` — boolean; `true` starts a nested sequence on its parent’s dash line, `false` puts it on the next line. Default `true`.
- `quoteStyle` — `'single'` or `'double'`, the quote style used when quotes are required. Default `'single'`.
- `forceQuotes` — boolean; `true` is the “quote every non-key string” switch. Default `false`.
- `noRefs` — boolean; `true` is the “do not reuse references” switch. Default `false`.
- `skipInvalid` — boolean; `true` is the skip-unrepresentable switch. Default `false`.
- `sortKeys` — boolean, or a comparator function `(a, b) => number`; `true` is the comparator-less key sort. Default `false`.
- `tagBeforeAnchor` — boolean; `true` writes the tag before the anchor. Default `false`.
- `flowBracketPadding`, `flowSkipCommaSpace`, `flowSkipColonSpace`, `quoteFlowKeys` — booleans, the four optional flow presentation switches (pad inside brackets, drop the space after commas, drop the space after colons, double-quote flow keys). Default `false`.

## `Schema`

Named export. Constructor / type name for a schema. The four built-in schemas `FAILSAFE_SCHEMA`, `JSON_SCHEMA`, `CORE_SCHEMA`, and `YAML11_SCHEMA` are values of `Schema`.

### Create call

`new Schema(tagArray)`: one argument, the complete tag list as an array of tag objects. On success it returns a `Schema` value that has `withTags`. When the list cannot form a schema (PRD FP-06), the call throws.

## `defineScalarTag`

Named export. `defineScalarTag(name, options)` returns a tag object (not a schema), attached with `withTags` or included in the list given to `Schema`.

- `name` — text: the tag name (`!<name>` for a local tag, or a full tag name).
- `options` — an object with these keys (keys a tag does not use may be omitted):
  - `matchByTagPrefix` — boolean. `false` (default): the tag matches exactly `name`. `true`: the tag matches any tag name that begins with `name`.
  - `implicit` — boolean. `true` marks an implicit scalar tag (tried on untagged plain scalars). Default `false`.
  - `resolve(source, isExplicit, tagName)` — `source` is the scalar text, `isExplicit` a boolean (`true` when the node carries an explicit tag), `tagName` the node’s full tag name. Returns the constructed value.
  - `identify(value)` — returns a boolean: `true` when this tag writes `value` on dump.
  - `represent(value)` — returns the scalar text to write.
  - `representTagName(value)` — returns the tag name to write; when absent, `name` is written.

## `defineSequenceTag`

Named export. `defineSequenceTag(name, options)` returns a tag object, attached with `withTags` or included in the list given to `Schema`.

- `name` — text, as for `defineScalarTag`.
- `options` — an object with these keys (keys a tag does not use may be omitted):
  - `matchByTagPrefix` — boolean, as for `defineScalarTag`.
  - `create(tagName)` — returns a new container; `tagName` is the node’s full tag name.
  - `addItem(container, item, index)` — receives each constructed item and its zero-based index. Returns nothing (or an empty string) to accept, or a non-empty string to reject the item.
  - `finalize(container)` — optional. Returns the final constructed value; throwing rejects the collection.
  - `identify(value)` — returns a boolean, as for `defineScalarTag`.
  - `represent(value)` — returns an array (or array-like) of the items to write, in order.
  - `representTagName(value)` — as for `defineScalarTag`.

## `defineMappingTag`

Named export. `defineMappingTag(name, options)` returns a tag object, attached with `withTags` or included in the list given to `Schema`.

- `name` — text, as for `defineScalarTag`.
- `options` — an object with these keys (keys a tag does not use may be omitted):
  - `matchByTagPrefix` — boolean, as for `defineScalarTag`.
  - `create(tagName)` — returns a new container; `tagName` is the node’s full tag name.
  - `addPair(container, key, value)` — receives each constructed pair. Returns an empty string to accept, or a non-empty string to reject the pair.
  - `has(container, key)` — returns a boolean: whether the container already holds `key`.
  - `keys(value)` — returns an iterable of the keys held by a constructed value.
  - `get(value, key)` — returns the value held for `key`.
  - `finalize(container)` — optional. Returns the final constructed value; throwing rejects the collection.
  - `identify(value)` — returns a boolean, as for `defineScalarTag`.
  - `represent(value)` — returns a `Map` of the pairs to write, in order.
  - `representTagName(value)` — as for `defineScalarTag`.

## `withTags`

A method on every `Schema` value (not a free function). It accepts tag objects either as one array, `schema.withTags([tag, ...])`, or as separate arguments, `schema.withTags(tag, ...)`; both shapes are supported. It returns a new `Schema` value (which itself has `withTags`). When a tag cannot be attached (PRD FP-06), the call throws.

**Attachable built-in tags.** `mapTag` is the default plain-object `!!map`; `realMapTag` is the `!!map` that constructs a `Map`; `legacyMapTag` is the `!!map` that stringifies complex keys; `mergeTag` is the YAML 1.1 merge key `<<`. Each is a tag object for `withTags`.

The returned schema is passed to the entries as the `schema` option: `load(text, { schema })`, `loadAll(text, { schema })`, `dump(value, { schema })`.
