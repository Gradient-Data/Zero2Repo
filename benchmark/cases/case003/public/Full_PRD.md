# YMLCODEC — Full Product Requirements Document

## Product overview

**YMLCODEC** is a YAML parser and writer for JavaScript. It reads YAML text into ordinary JavaScript values and writes JavaScript values back as YAML text. It supports the YAML 1.2 specification as the default loading dialect and the YAML 1.1 type set when the caller asks for that dialect. The required behavior is the parse, type-resolution, and dump outcomes stated in the feature points below.

This document specifies **user- and integrator-observable behavior only**. Exact published symbol names and other Interface Contract details are out of scope here. Every feature point below corresponds to behavior that exists in the finished YMLCODEC library. Feature points are ordered so foundational capabilities come first; a later feature point may depend on an earlier one, never the reverse.

## Terminology

| Term | Meaning in this PRD |
| --- | --- |
| **YAML text** | A Unicode string that the caller treats as a YAML stream (one document or several, possibly empty). |
| **Document** | One YAML document inside a stream. Documents may be separated by the document-start marker `---` and the document-end marker `...`. |
| **Single-document parse** | The library entry that accepts a stream and returns exactly one constructed value. |
| **Multi-document parse** | The library entry that accepts a stream and returns every constructed document, in order, as a list. An empty stream yields an empty list. |
| **Dump** | The library entry that serializes one JavaScript value as YAML text. |
| **Schema** | The finite set of tags that decide how a node is constructed on load and how a JavaScript value is identified on dump. The four built-in schemas are **Failsafe**, **JSON**, **Core**, and **YAML 1.1**. |
| **Tag** | A YAML type name such as `!!null`, `!!bool`, `!!int`, `!!float`, `!!str`, `!!seq`, `!!map`, or a local tag written with a single `!`. An explicit tag is written on the node; an implicit tag is inferred from plain scalar text. |
| **Failsafe schema** | Only strings, sequences, and mappings. Plain scalars stay strings. |
| **JSON schema** | Failsafe plus the JSON subset of null, boolean, integer, and float. |
| **Core schema** | Failsafe plus the YAML 1.2 Core notations for null, boolean, integer, and float. This is the default schema for both parse entries. |
| **YAML 1.1 schema** | Failsafe plus the YAML 1.1 scalar notations and the extra YAML 1.1 types: `!!binary`, `!!timestamp`, `!!set`, `!!omap`, `!!pairs`, and merge keys. |
| **Plain object map** | The default `!!map` container: a plain JavaScript object. Keys that are not strings are converted to strings. Complex keys (sequences and mappings used as keys) are rejected. |
| **Real map** | An alternative `!!map` container: a JavaScript `Map` that stores each key exactly as constructed. |
| **Legacy map** | An alternative `!!map` container: a plain object that stringifies complex keys instead of rejecting them. |
| **Merge key** | The YAML 1.1 mapping key `<<`. Its value is one mapping, or a sequence of mappings, whose pairs are copied into the surrounding mapping. The Core schema does not include merge keys. |
| **Anchor / alias** | An `&name` label on a node and a later `*name` reference to that same constructed value. |

## Public surface inventory

YMLCODEC is a **library**. Integrators reach it by installing the ymlcodec package and calling the published parse and dump entries. A command-line convenience ships alongside; it is not a feature point.

The library’s public, independently usable surfaces are:

- Parse one YAML document from a string, or fail when the stream is empty or contains more than one document.
- Parse every document in a multi-document stream, including an empty stream.
- Choose among the four built-in schemas, or a schema the caller has extended with extra tags.
- Construct the YAML 1.2 Failsafe / JSON / Core types, and (when that schema is selected) the YAML 1.1 extra types including merge keys.
- Choose how mappings are stored: plain object, real `Map`, or legacy stringified keys.
- Serialize a JavaScript value to YAML text, with schema-aware quoting and the documented presentation choices.
- Register custom scalar, sequence, and mapping tags and use them on both load and dump.
- Cap collection nesting, alias count, and merge-key work so compact hostile documents cannot expand without bound.

Feature points below group these entries by capability. They do not invent additional products.

## Non-functional constraints

- **Form factor:** A TypeScript/JavaScript library with no compiled native extensions. A current Node.js LTS interpreter and npm are sufficient to install from this repository, run the documented bundle step, and parse with the locally built artifact.
- **Layout.** The package manifest is `package.json` at the built repository root.
- **Platforms:** Linux, macOS, and Windows. Documented execution is Linux with Node.js.
- **Hardware:** CPU-only. No GPU or accelerator is required or claimed.
- **Default load dialect:** YAML 1.2 Core. Merge keys and the YAML 1.1-only types are off until the caller selects the YAML 1.1 schema or adds those tags.
- **Default dump dialect:** Dump identifies values with the YAML 1.1 type set, and decides whether a string can be written plain by the quoting rule in FP-05.
- **Untrusted input:** The YAML design allows a tiny document to expand into a huge object graph. The library exposes the limits in FP-07. Walking a constructed value after a successful parse (for example by converting it to JSON) is the caller’s responsibility; the library does not automatically refuse a graph that is cheap to construct but expensive to walk.
- **JavaScript-specific tags:** Tags that construct functions, regular expressions, or other JavaScript-only values are not part of this library. They live in a separate optional package and are out of scope here.

## Non-goals

- Being a JSON-only parser, or treating YAML as a thin skin over JSON.
- Shipping JavaScript-specific tags (functions, regular expressions, and similar) inside this library.
- Guaranteeing a particular nanosecond-per-document speed (speed is a design goal, not a requirement).
- Treating the command-line convenience, the online demo, the speed-measurement scripts, the distribution bundler, or the runner for the external YAML conformance corpus as independent product capabilities.
- Treating the low-level event stream, document tree, and tree visitor as a separate product. Those layers exist so advanced callers can build their own pipeline; the parse and dump entries already cover the outcomes a first-time integrator needs.

---

## Feature points

### FP-01: Parse YAML documents

**Public entry:** The YMLCODEC library’s single-document parse entry and multi-document parse entry. The caller supplies YAML text and may supply a schema (FP-02), a source-path label for failure reports, and a JSON-parse compatibility switch for duplicate keys. Nesting, alias, and merge-key limits are specified in FP-07. Mapping-container choice is specified in FP-03.

**Normal behavior:**

- Plain scalars are resolved by the active schema (FP-02); under the default Core schema a plain scalar written in Core integer or float notation is constructed as a number, not a string.
- A single-document parse of a stream that contains exactly one document returns that document’s constructed value, whether the document is a scalar, a sequence, or a mapping.
- A leading byte-order mark is ignored: it does not change the constructed value.
- The multi-document parse returns one list element per document, in stream order. A document with no content constructs null.
- The multi-document parse of a stream with zero documents (empty text, or text that is only whitespace and comments) returns an empty list.
- An alias is the same constructed value as its anchor (same identity, not a separately constructed copy). A collection may contain an alias to itself under the default sequence and mapping tags; the constructed collection then contains itself.
- Duplicate keys in one mapping are rejected by default. When JSON-parse compatibility is enabled, duplicates are accepted and the last occurrence of a key wins. The switch applies to every document of a multi-document parse.
- In double-quoted and single-quoted scalars, a carriage-return/line-feed line break folds exactly as a line-feed break does (a single break between two non-empty lines becomes one space). In a double-quoted scalar a backslash immediately before a line break joins the lines without a space; single-quoted scalars have no backslash-join form.
- Every YAML 1.2 double-quoted escape is decoded, including the eight-hex-digit `\U` escape for code points outside the Basic Multilingual Plane.
- `%TAG` directives follow the YAML 1.2 grammar: a named tag handle consists of word characters (letters, digits, `-`) between two `!`, and a tag written with a declared handle expands to the declared prefix.

**Boundary / error behavior:**

- The single-document parse fails on a stream with zero documents (empty, or whitespace and comments only), and on a stream with more than one document. The multi-document parse succeeds on both. The caller can tell these two entries apart on such input.
- An explicit tag that the active schema does not define is rejected and the parse fails. (Catch-all prefix tags in FP-06 are the way to accept unknown tags.) A tag handle that no `%TAG` directive of that document declares is also a failure.
- An explicit tag on a node of a kind the tag does not construct is rejected and the parse fails.
- Input that is not a well-formed YAML 1.2 stream fails on both parse entries and yields no value.
- When a source-path label is supplied and a parse fails, the failure report includes that label, and the error position it carries includes the line of the error site, given as the number of line breaks that precede the error site (a carriage-return/line-feed pair counts as one break, the same way it folds in quoted scalars). This count is neither a byte offset nor a column.
- A failed parse does not yield a usable document (and, for the multi-document entry, no prefix of the list). The caller can tell success from failure before reading any constructed value.

---

### FP-02: Built-in schemas and YAML 1.2 type resolution

**Public entry:** The schema selection on both parse entries (FP-01) and on dump (FP-05). The four built-in schemas are exactly Failsafe, JSON, Core, and YAML 1.1. Single-document and multi-document parse use Core when the caller does not choose a schema. YAML 1.1 extra types beyond these Core/JSON/Failsafe scalars are specified in FP-04.

Notation in this feature point: patterns are written as regular expressions that must match the whole plain scalar text; `[-+]?` is an optional sign.

**Normal behavior:**

- **Failsafe.** Every scalar, plain or quoted, is a string. Sequences and mappings still construct as arrays and plain objects.
- **JSON** (the YAML 1.2 JSON schema), implicit resolution of plain scalars:
  - null: exactly `null`. Booleans: exactly `true` and `false`.
  - integer: `-?(0|[1-9][0-9]*)`.
  - float: `-?(0|[1-9][0-9]*)(\.[0-9]*)?([eE][-+]?[0-9]+)?` (when not already an integer).
  - Everything else, including an empty plain value, is a string.
- **Core** (the YAML 1.2 Core schema, the parse default), implicit resolution of plain scalars:
  - null: the empty scalar, `~`, `null`, `Null`, `NULL`.
  - booleans: `true`, `True`, `TRUE`, `false`, `False`, `FALSE`.
  - integer: `[-+]?[0-9]+` read as decimal (leading zeros allowed and still decimal), or `0o[0-7]+` read as octal, or `0x[0-9a-fA-F]+` read as hexadecimal. The prefixed forms take no sign. There is no binary form, no underscore, and no base-60 form.
  - float: `[-+]?[0-9]+(\.[0-9]*)?([eE][-+]?[0-9]+)?`, `[-+]?\.[0-9]+([eE][-+]?[0-9]+)?`, infinity `[-+]?\.(inf|Inf|INF)`, and not-a-number `\.(nan|NaN|NAN)` (when not already an integer). No underscores.
  - Everything else is a string.
- **YAML 1.1** (the YAML 1.1 type repository), implicit resolution of plain scalars:
  - null: as Core.
  - booleans: true is `true|True|TRUE|y|Y|yes|Yes|YES|on|On|ON`; false is `false|False|FALSE|n|N|no|No|NO|off|Off|OFF`.
  - integer: binary `[-+]?0b[01_]+`; octal `[-+]?0[0-7_]+` (a leading zero means octal); hexadecimal `[-+]?0x[0-9a-fA-F_]+`; base 60 `[-+]?[0-9][0-9_]*(:[0-5]?[0-9])+`; decimal `[-+]?(0|[1-9][0-9_]*)`. Underscores are ignored when computing the value.
  - float: `[-+]?([0-9][0-9_]*)?\.[0-9_]*([eE][-+][0-9]+)?` (the exponent sign is required); base 60 `[-+]?[0-9][0-9_]*(:[0-5]?[0-9])+\.[0-9_]*`; infinity and not-a-number as Core. Underscores are ignored when computing the value. Text that matches but has no digits is a string.
  - The YAML 1.2 `0o` octal prefix is not YAML 1.1 notation.
- **Explicit `!!int` and `!!float`.** Under JSON and Core an explicit `!!int` accepts an optional sign on every integer form: `[-+]?0b[01]+`, `[-+]?0o[0-7]+`, `[-+]?0x[0-9a-fA-F]+`, `[-+]?[0-9]+`; an explicit `!!float` accepts the Core float notation (including a leading `+`, a leading dot, and the infinity / not-a-number spellings) under both. Under YAML 1.1 an explicit tag accepts exactly the YAML 1.1 notation above. An explicit `!!bool` or `!!null` accepts the active schema’s spellings.
- **Numbers outside the JavaScript range.** An integer or float text whose value does not convert to a finite JavaScript number (it would overflow to an infinity) is not a number: implicitly it stays a string, and under an explicit `!!int` / `!!float` tag the parse fails. The infinity spellings are the only way to obtain an infinite value.
- An explicit empty `!!str` is the empty string. An explicit empty `!!seq` is an empty array. An explicit empty `!!map` is an empty mapping (plain object under the default map). An explicit empty `!!null` is null on every typed schema.
- An explicit tag whose text does not match that tag’s notation fails and does not yield a value.

**Boundary / error behavior:**

- Switching schema is the only way these implicit rules change; the same text may be a string under one schema and a number or boolean under another.
- Base-60, underscore, leading-zero-octal, binary, and the YAML 1.1 boolean words are not Core behavior.

---

### FP-03: Mapping containers and key policies

**Public entry:** The default `!!map` tag on every built-in schema, and the two replacement mapping tags the caller may attach to a schema (FP-02 / FP-06): the real-map tag and the legacy-map tag. This feature point depends on a successful parse (FP-01) and on schema selection (FP-02).

**Normal behavior:**

- Under the default plain-object map, each scalar key becomes a property name by JavaScript string conversion of the constructed key. String keys and values are kept as is.
- A key whose string form is `__proto__` is always stored as an **own** data property of the result, with its constructed value. It never changes the result’s prototype, and nothing becomes inherited through it. This holds for the default map and the legacy map.
- When the real-map tag replaces the default map, every mapping is a JavaScript `Map` whose keys are the constructed keys, unconverted: keys of different type or identity stay distinct even when their string forms are equal, and sequence or mapping keys are kept as constructed values. Under that schema, dump writes such keys back so that a dump-then-parse round trip restores them, and a plain object dumped under that schema parses back as a `Map` with the same string keys.
- When the legacy-map tag replaces the default map, a key that is a sequence becomes a property name by JavaScript string conversion of the array (items joined by commas, a plain-object item rendered as the ordinary object string), and a key that is a mapping becomes the ordinary JavaScript object string. Scalar keys behave as under the default map.

**Boundary / error behavior:**

- The default plain-object map rejects a sequence or a mapping used as a key; the parse fails.
- The legacy map rejects a sequence key that has a sequence among its items, however the key is reached (written directly or through an alias); the parse fails.
- These three mapping tags share the `!!map` name: attaching the real-map tag or the legacy-map tag replaces the default map for that schema. They are not three simultaneous containers in one schema.

---

### FP-04: YAML 1.1 types and merge keys

**Public entry:** The YAML 1.1 schema on both parse entries, and the merge tag the caller may attach to the Core schema when merge keys are needed without the rest of YAML 1.1. This feature point depends on FP-01, FP-02, and (for complex keys inside `!!pairs`) FP-03. Dump of binary, timestamp, and set values is specified here for those types; general dump presentation is FP-05.

**Normal behavior:**

- **`!!binary`.** An explicit `!!binary` scalar is RFC 4648 Base64 text (standard alphabet, `=` padding required so the length is a multiple of four); whitespace inside it is ignored. It constructs a `Uint8Array` of the decoded bytes; empty text is an empty `Uint8Array`. A `Uint8Array` dumps as `!!binary` and parses back to the same bytes.
- **`!!timestamp`.** Implicit and explicit timestamps follow the YAML 1.1 timestamp format: a date-only form `YYYY-MM-DD` (four-digit year, two-digit month and day), or a date-time form `YYYY-M[M]-D[D]` then `T`, `t`, or one or more spaces/tabs, then `h[h]:mm:ss`, an optional fraction `.` digits, and an optional zone (spaces or tabs may precede it) that is `Z` or a sign with a one- or two-digit hour and optional `:mm`. A timestamp constructs a JavaScript `Date` for that instant; a date-only form is midnight UTC, and a date-time without a zone is UTC. Text that matches the shape but names an impossible calendar date, an hour above 23, a minute or second above 59, a zone hour above 23, or a zone minute above 59 is not a timestamp: implicitly it stays a string, and as an explicit `!!timestamp` it fails. An empty `!!timestamp` fails. A `Date` dumps as a timestamp that parses back to the same instant.
- **`!!set`.** A `!!set` mapping constructs a JavaScript `Set` of its keys; every value must be null. An empty `!!set` is an empty `Set`. A `Set` dumps with an explicit `!!set` tag and parses back as a `Set` with the same members.
- **`!!omap`.** A `!!omap` sequence of single-key mappings constructs an array of those mappings, in order (plain objects; one-entry `Map`s when the real-map tag is attached). Keys must be unique across items. An empty `!!omap` is an empty array.
- **`!!pairs`.** A `!!pairs` sequence of single-key mappings constructs an array of two-element `[key, value]` arrays, in order. Repeated keys are allowed. An empty `!!pairs` is an empty array. A complex key follows the active map’s key policy: rejected under the default map, kept as the constructed value under the real-map tag.
- `!!omap` and `!!pairs` are load-only compatibility types: they are not identified on dump, so a dumped result is a plain sequence, not an `!!omap` / `!!pairs` node.
- **Merge keys.** Under Core without the merge tag, `<<` is an ordinary key and nothing is merged. Under the YAML 1.1 schema, or under Core with the merge tag attached, a `<<` key whose value is a mapping (or a sequence of mappings) copies each pair of the source into the enclosing mapping, and no `<<` property appears. Several `<<` keys in one mapping all apply. A pair written explicitly in the enclosing mapping wins over a merged pair with the same key, wherever it is written. Within one sequence of sources, an earlier source wins over a later one for the same key. Merged pairs are added through the enclosing mapping’s own tag, so a merge into a mapping whose tag rejects the incoming pair fails.

**Boundary / error behavior:**

- `!!omap` on a mapping (not a sequence) fails. An `!!omap` item that is not a mapping, an item with more than one key, or a repeated key across items fails. The same item rules apply to `!!pairs`, except that repeated keys are allowed.
- `!!binary` rejects text with characters outside the Base64 alphabet and text whose length (whitespace removed) is not a multiple of four.
- A merge source that is not a mapping, or a merge sequence that contains a non-mapping, fails.
- Merge-key processing is counted against the merge-key budget in FP-07.

---

### FP-05: Serialize JavaScript values to YAML

**Public entry:** The YMLCODEC library’s dump entry. The caller supplies one JavaScript value and may supply a schema (FP-02), the presentation choices listed below, a switch that skips unrepresentable values instead of failing, and a switch that disables anchor/alias reuse. This feature point depends on FP-02 for quoting rules and on FP-03 / FP-04 when the value uses a `Map`, a `Set`, a date, or an 8-bit byte array.

**Normal behavior:**

- Dump writes YAML text that the selected schema (and, under the default dump schema, both the Core and the YAML 1.1 parse) reads back as the same value. The text ends with a newline unless it is empty.
- **Quoting rule.** A string is written as a plain scalar when all of the following hold; otherwise it is quoted. An implementation may additionally quote a string whose first character YAML 1.1 reserves as an indicator of a type of its own.
  - Read back, the plain text resolves to a string: no implicit tag of the dump schema resolves it to another type. Under the default dump schema this means neither the YAML 1.1 schema nor the YAML 1.2 Core schema (FP-02) resolves it to null, a boolean, an integer, a float, a timestamp, or a merge key. Under an explicitly chosen schema, only that schema’s implicit tags count.
  - It is a valid YAML 1.2 plain scalar in its context (block or flow): written unquoted at that position, the YAML 1.2 grammar reads it back as one plain scalar with exactly that content.
  - It is a single line of printable characters no longer than the line width (see below).
- When quotes are required, the default quote style is single quotes; the caller may choose double quotes. A string containing characters outside the YAML printable set is written double-quoted with escapes. A multi-line string is written in a block scalar style. A “quote every non-key string” switch quotes every string value while leaving keys unquoted unless the quoting rule requires quotes.
- **Numbers.** An integer whose JavaScript decimal string uses exponential notation (magnitude at or above `1e21`) is written in a float form that parses back to the same number; smaller integers are written as decimal integers. Under the default dump schema, every finite number is written in a notation that the JSON, Core, and YAML 1.1 schemas all read back as the same number. Not-a-number, the infinities, negative zero, and small exponents are written in forms the selected schema reads back to the same value.
- **References.** By default, a second occurrence of the same object (including a cycle) becomes an alias to an anchor placed on the first occurrence. A “do not reuse references” switch writes each occurrence in full with no anchors.
- **Presentation defaults.** Indentation is two spaces per level; the caller may choose another width. The line width is 80 columns: a plain or folded scalar longer than the width is folded at spaces onto several lines (the width is counted from the scalar’s indentation), and a scalar within the width stays on one line. Block style is used at every depth.
- Sequences under a mapping key are indented under that key by default; a “no extra sequence indent” switch aligns the dash with the key. A sequence nested directly in a sequence starts on its parent’s dash line by default (`- - <item>`); a switch puts the nested sequence on the next line.
- A flow-style depth makes every node at that nesting depth and below use flow style; depth 0 writes the whole value in flow style. The default never switches to flow. Optional flow presentation switches pad inside brackets and braces with one space, drop the space after commas, drop the space after colons, and write flow keys double-quoted.
- When a node has both an anchor and an explicit tag, the default order is the anchor then the tag; a switch reverses that order to the tag then the anchor.
- Keys keep insertion order by default. When a comparator-less key sort is requested, scalar keys are emitted in ascending order of their written text (plain string comparison); complex keys are not reordered relative to each other.
- Unrepresentable values (a function, a regular expression) cause dump to fail by default. When the skip-unrepresentable switch is on, such a value is omitted: a mapping pair whose key or value is unrepresentable is dropped, and such a sequence item is dropped. An `undefined` sequence item is written as null even without that switch; an `undefined` mapping value omits that pair; an `undefined` root dumps as empty text.

**Boundary / error behavior:**

- Dump of a function or regular expression without the skip-unrepresentable switch fails and produces no YAML text.
- A value that no tag of the dump schema identifies fails; the default plain-object map does not identify a `Map`.

---

### FP-06: Custom tags

**Public entry:** The library’s tag-description entries for a scalar tag, a sequence tag, and a mapping tag, and the schema operation that attaches one or more tags to an existing schema (Failsafe, JSON, Core, YAML 1.1, or an already extended schema). This feature point depends on FP-01, FP-02, and FP-05. Built-in tags from FP-02 and FP-04 stay available; a newly attached tag with the same name, the same node kind, and the same exact-versus-prefix matching replaces the earlier one and leaves every other tag in place.

**Normal behavior:**

- A **scalar** custom tag turns the tagged text into the value its resolve step returns, whether the tag and the text are on one line or the text is on the next line. On dump, a value that the tag’s identify step accepts is written with that tag and the text its represent step returns.
- A **sequence** custom tag creates a container and receives each item in document order, with its zero-based index. A **mapping** custom tag creates a container and receives each key/value pair in document order. When the tag has a finalize step, its result is the constructed value (and the value an alias to that node refers to); otherwise the container is. On dump, a value that the tag’s identify step accepts is written with that tag and the items or pairs its represent step returns, in that order.
- On dump, a value is written with a custom tag only when that tag’s identify step accepts it; values the step does not accept (including plain numbers, arrays, or objects of the same shape) are written as ordinary YAML.
- The same tag name may be registered once for each node kind (scalar, sequence, mapping); a node uses the registration for its own kind.
- Tag lookup: an exact-name tag wins over prefix-matching tags; among prefix-matching tags, the longest matching prefix wins. A prefix-matching tag receives the node’s full tag name, so it can remember it, and may supply the tag name to write on dump.
- Prefix-matching tags are the supported way to accept unknown local tags of every node kind and write them back with their original names.
- A schema must include the default string tag (`!!str`). Attaching tags to Core, JSON, Failsafe, or YAML 1.1 preserves that tag and every other built-in tag of that schema, so built-in resolution is unchanged by the attach.
- A schema created from a tag list consists of exactly those tags; it is not an extension of a built-in schema.
- Attaching tags yields a new schema and leaves the schema it was attached to unchanged.
- Each parse or dump call uses only the schema and tags passed to it; a schema or tag passed to one call has no effect on any other call.

**Boundary / error behavior:**

- A recursive alias (a node containing an alias to itself) into a tag that has a finalize step fails, because the final value does not exist while its items are collected. A recursive alias into a default sequence or mapping still succeeds (FP-01).
- A tag step that refuses the collected items or a pair (by throwing, or by returning a rejection) fails the parse and does not yield a document.
- A node carrying a local tag that no attached tag matches fails (FP-01).
- An implicit scalar tag that also matches by tag prefix cannot be used: the schema operation that would attach that combination fails, and the caller does not obtain a usable schema.
- A tag list that does not include the default string tag cannot form a schema: the schema operation that would create it fails, whether the list is empty or holds only other tags.

---

### FP-07: Resource limits for untrusted input

**Public entry:** The three numeric limits on both parse entries (FP-01): collection nesting depth, alias count per document, and total merge-key work across the whole parse call. This feature point depends on FP-01 and, for the merge-key budget, on FP-04. It does not change type resolution.

**Normal behavior:**

- **Nesting depth.** The nesting depth of a node is the number of nodes on the chain from the document’s root node down to it, inclusive (a collection inside a collection adds one; a scalar inside the innermost collection adds one more). A document in which some chain reaches the nesting limit fails as a parse failure, never as an uncaught host stack overflow, however deep the input. Aliases do not count: an alias contributes no nesting of the node it refers to. When the limit is omitted, a fixed default applies; it is the implementer’s choice, greater than 10 and less than 200.
- **Alias count.** The alias budget is the number of alias nodes allowed in one document; a document with more aliases than the budget fails. The budget is applied **per document** of a multi-document parse. When omitted, the budget is unlimited; the caller may also request unlimited explicitly, and a budget of 0 rejects every alias.
- **Merge-key work.** The merge-key budget is the number of keys processed by `<<` across one parse call, shared by every document of a multi-document parse. Each key of a merge source counts every time that source is applied, whether or not the key is copied (a key already present still counts, and applying the same source twice counts twice). A call that processes more keys than the budget fails. When omitted, the budget is 10000; the caller may disable it. Merge keys that do not apply (Core without the merge tag) do no merge work and do not count.

**Boundary / error behavior:**

- Crossing a limit fails the whole parse call and yields no document (and no prefix of the multi-document list). The same text succeeds under a larger limit.
- These limits do not, by themselves, cap the cost of walking a constructed graph after a successful parse. A document that stays under the alias budget may still be expensive to convert to JSON if aliases repeat a large subgraph; that follow-on walk is outside this feature point (see the untrusted-input note in Non-functional constraints).

