# Tomlparse — Full Product Requirements Document

## Product overview

**Tomlparse** is a Python library that reads TOML text and returns ordinary Python values. It is a parser only: it does not write TOML, and it does not preserve comments, ordering of presentation, or other style. Version 2.4.0 and later of Tomlparse are compatible with **TOML v1.1.0**, the published TOML language specification (toml.io, version 1.1.0). That is the language this product implements, and that specification is the authority for the grammar and for which documents are valid.

An integrator hands Tomlparse a TOML document and receives plain Python mappings, sequences and scalars that carry the document's data with native types.

This document specifies **user- and integrator-observable behavior only**. Exact published symbol names, import paths, and call spellings belong in the Interface Contract, not here. Every feature point below corresponds to behavior that exists in the finished Tomlparse product. Feature points are ordered so foundational capabilities come first; a later feature point may depend on an earlier one, never the reverse.

## Terminology

| Term | Meaning in this PRD |
| --- | --- |
| **TOML document** | A Unicode text that the caller treats as one TOML v1.1.0 document. The product parses one document per call. |
| **String-parse entry** | The library entry that accepts TOML as a Python text string and returns a mapping, or fails. |
| **Binary-file parse entry** | The library entry that reads TOML from a binary file object and returns a mapping, or fails. Specified in FP-03. |
| **Document mapping** | The successful result: a Python mapping whose keys are strings and whose values are the native types in FP-01 and FP-02. |
| **Table** | A TOML table. Constructed as a mapping. Includes tables declared with square-bracket headers, tables implied by dotted keys, and inline tables. |
| **Array** | A TOML array. Constructed as a sequence. |
| **Array of tables** | A sequence of mappings built by repeating a double-square-bracket header. |
| **Bare key** | An unquoted key made only of Latin letters, decimal digits, underscores, and hyphens. |
| **Dotted key** | Two or more key parts joined by dots. Each part may be bare or quoted. Dots inside a quoted part are part of that part’s name, not separators. |
| **Inline table** | A table written with curly braces as a value. After it is built, that namespace is frozen. |
| **Offset date-time** | A TOML date-time with a `Z` / `z` suffix or a numeric offset. Constructed as a timezone-aware datetime. |
| **Local date-time** | A TOML date-time with no offset. Constructed as a timezone-naive datetime. |
| **Local date** | A TOML calendar date with no time. Constructed as a date. |
| **Local time** | A TOML clock time with no date. Constructed as a time. |
| **Float converter** | An optional callable the caller supplies so TOML floats (including `inf` and `nan` spellings) are built as something other than a Python float. Specified in FP-05. |
| **Decode error** | The product’s documented parse-failure exception. It is a kind of value error. Specified in FP-04. |

## Public surface inventory

Tomlparse is a **library**. Integrators reach it by installing the Tomlparse package. There is no command-line product, no writer, and no configuration file of Tomlparse’s own.

The public surfaces, grouped by feature point, are:

- Parse one TOML v1.1.0 document from a Python text string into a document mapping: keys, comments, tables, arrays, arrays of tables, inline tables (FP-01).
- Construct TOML scalars as native Python values: the four string forms, integers in four bases, floats, booleans, and the four date-time kinds (FP-02).
- Parse the same language from a binary file object whose bytes are interpreted as UTF-8 (FP-03).
- Refuse invalid TOML and refuse the wrong Python input type, without returning a document mapping (FP-04).
- Optionally build TOML floats through a caller-supplied converter, with dictionaries and lists forbidden as conversion results (FP-05).

Feature points below group these entries by capability. They do not invent additional product surfaces.

## Non-functional constraints

- **Form factor:** A pure-Python library with zero runtime third-party dependencies. Optional compiled wheels exist on some platforms for speed; they are not required. The pure-Python parser is the product.
- **Language:** Python 3.8 or newer, including the CPython and PyPy implementations.
- **Platforms:** Linux, macOS, and Windows. Linux is the reference platform.
- **Hardware:** CPU-only. No GPU or accelerator is required or claimed. The product imports from this repository’s source tree on an ordinary host.
- **TOML dialect:** TOML v1.1.0. Behaviors that exist only in older Tomlparse releases (TOML v1.0.0-only, text-mode file objects as parse input) are not this product.
- **Result types:** Successful parses return plain mappings, sequences, and scalars from Python and its standard library. The product does not return custom node types in order to keep comments or layout.
- **Error text:** Wording of decode-error messages is informational and free. What the product promises on failure is success versus failure, the exception kind, and (when a parse fails) the location of the failure as specified in FP-04 — not a particular sentence.

## Real parser (global)

Every feature point below is a capability of a real TOML v1.1.0 parser written as part of this product. It parses the whole language itself and does not delegate parsing to another TOML parser, including the standard library's TOML module. There is only a CPU baseline: no GPU, accelerator, or extra service is part of the product.

## Non-goals

- Encoding or writing TOML. There is no dump, write, or encode entry. A separate write-only companion project exists for that job; it is not this product.
- Comment-preserving or style-preserving round-trip parsing. A successful parse is a plain mapping of builtin and standard-library values.
- Being a TOML v1.0.0-only parser. This product accepts TOML v1.1.0 documents that v1.0.0 forbids, including newlines and trailing commas in inline tables, the `\e` and `\x` string escapes, and date-times whose seconds are omitted.
- Shipping a command-line program, a web server, or a configuration framework.
- Guaranteeing a particular parse throughput. Speed is a design goal, not a requirement.
- Treating the repository's speed-measurement scripts, fuzzer, profiler, or packaging scripts as product capabilities.
- Treating a fallback import of the standard library's TOML module on Python 3.11+ as a Tomlparse feature. That pattern is integrator guidance for dependency selection, not part of the product.

---

## Feature points

### FP-01: Parse TOML document structure from text

**Public entry:** Tomlparse’s string-parse entry. The caller supplies a Python text string. Scalar construction is specified in FP-02. Invalid documents are specified in FP-04. The binary-file entry in FP-03 yields the same document mapping for the same TOML text after UTF-8 decoding. The optional float converter in FP-05 does not change table or array structure.

**Normal behavior:**

- The structure of a document is the one TOML v1.1.0 defines; every document that specification allows is accepted and built as described here.
- Empty text, text that is only whitespace, and text that is only comments (with or without a final line feed) parse to an empty mapping.
- Each key/value pair at the root becomes an entry of the document mapping; each pair after a table header becomes an entry of that table until the next header.
- Keys are always strings, including keys that look like numbers or like the words `true`, `false`, `inf`, and `nan`; such a key never becomes a number, a boolean or a float. Bare keys use letters, digits, underscores, and hyphens, and each distinct spelling is a distinct key. Letter case is significant in keys and in table names.
- A key may be written as a basic string or as a literal string. A quoted key may be empty and may contain any character TOML allows, including `#`, spaces, dots, and non-ASCII letters; a dot inside a quoted key is part of that key, not a separator. A literal quoted key is its interior text unchanged.
- Dotted keys and dotted table headers create nested mappings, one level per part. Whitespace around the dots is insignificant in both. A table created implicitly by dotted keys may receive further dotted keys under the same prefix.
- A table header creates any missing parent tables. Super-tables may be omitted and declared later by their own header. After dotted keys have created a nested table, a sub-table of it that has not itself been defined may still be declared by a header, as TOML v1.1.0 allows.
- Each array-of-tables header appends one new mapping to that array. Nested array-of-tables headers and sub-table headers whose path runs through an array of tables attach to the most recently appended item of that array. An array-of-tables header implies any missing parent tables as plain tables (mappings, not sequences); such a parent may be declared later by its own header and may then receive other keys.
- Inline tables are mappings, may be empty, may contain dotted keys, and (as TOML v1.1.0 allows) may span lines, contain comments, and end with a trailing comma after the last pair.
- Arrays are sequences in document order. They may be empty, mix value types, nest, span lines, contain comments between elements, and end with a trailing comma.
- A comment runs from a `#` that is not inside a string to the end of the line, wherever TOML allows one, with or without whitespace before the `#`. Comment text never becomes a key, a value, or an element. Non-ASCII text is allowed in comments.
- Indentation by spaces or tabs is insignificant.
- A carriage-return/line-feed pair in the input is treated as a single line feed everywhere, including inside string values: a multiline string written with carriage-return/line-feed line endings holds line feeds only.

**Boundary / error behavior:**

- Every structural construct TOML v1.1.0 forbids is refused with the decode error in FP-04, including: duplicate keys in one table of any kind; defining a table twice; reopening a table already defined by a header, or by dotted keys, through a later header or later dotted keys; replacing a value with a table or an array of tables; adding to an inline table after it is written; extending an array of tables through a dotted key; a pair with no key or no value; a multiline string used as a key or as a table name; a header that is not closed on its own line or that shares its line with a following pair.
- Nesting depth: a document whose arrays are nested inline 470 levels deep parses successfully, as does a document whose inline tables are nested 310 levels deep and a document with a dotted key of 310 parts; every shallower nesting parses as well. Behaviour beyond those depths is unspecified.

---

### FP-02: Map TOML scalar types to native values

**Public entry:** The same string-parse entry as FP-01 (and the binary-file entry in FP-03). This feature point is the type each TOML scalar becomes in the document mapping. Structure of tables and arrays is FP-01. Default float construction uses Python’s float; a replacement converter is FP-05.

**Normal behavior:**

- **Booleans.** The tokens `true` and `false`, all lowercase, are Boolean true and Boolean false. They are not the integers 1 and 0, and they are not strings.
- **Strings — four forms.** Basic, literal, multiline basic and multiline literal strings are built as Python strings with the content TOML v1.1.0 defines for them:
  - Escapes are processed in basic and multiline basic strings and never in literal or multiline literal strings, whose interior is taken as written (backslashes included).
  - In both multiline forms a line feed immediately after the opening delimiter is discarded; later line feeds are kept.
  - In a multiline basic string, a backslash that is the last non-whitespace character on a line removes the line ending and all whitespace (spaces, tabs, line feeds) up to the next non-whitespace character or the closing delimiter.
  - Both multiline forms may contain one or two of their own quote characters next to each other, including directly before the closing delimiter, so that the value ends in one or two quote characters.
- **Basic-string escapes (finite set).** In basic and multiline-basic strings the following two-character escapes are replaced: backslash-b (backspace), backslash-t (tab), backslash-n (line feed), backslash-f (form feed), backslash-r (carriage return), backslash-e (escape, code point 27), backslash-double-quote, and backslash-backslash. A backslash-x followed by two hex digits, a backslash-u followed by four hex digits, and a backslash-U followed by eight hex digits each insert the Unicode scalar value with that code point. Hex digits are case-insensitive. A quoted key written as a basic string undergoes the same escape processing; a key written as a literal string does not, so the two spellings of the same characters can be different keys.
- **Integers.** Decimal integers (optionally signed; a signed zero is the integer 0) and unsigned hexadecimal (`0x`), octal (`0o`) and binary (`0b`) integers become Python integers of the value they denote. Prefix letters are lowercase only; hex digits may be either case. A single underscore may separate two digits in every base.
- **Floats (default converter).** A number with a fractional part, an exponent, or both (optionally signed, with single underscores between digits) becomes the Python float of that value. The special spellings `inf`, `+inf`, `-inf`, `nan`, `+nan`, and `-nan` are floats: positive infinity, negative infinity, and a not-a-number value (a signed NaN token still constructs a NaN).
- **Date-time values.** An offset date-time is a timezone-aware datetime whose UTC offset is the written offset (`Z` or `z` is UTC, a numeric `±HH:MM` offset is that many hours and minutes ahead of or behind UTC). A local date-time is a timezone-naive datetime. A local date is a date. A local time is a time. The separator between date and time may be `T`, `t`, or a space.
- **Seconds and fractions.** In any value with a time part, seconds may be omitted, in which case the second is 0. A fractional second becomes the microsecond field: the fraction's first six digits are read as microseconds after padding the fraction on the right with zeros to six digits, and any digits after the sixth are dropped (truncated, not rounded). A value without a fraction has microsecond 0.
- Valid calendar dates, including February 29 in leap years, are accepted.
- Parsed date-times, dates, and times are ordinary standard-library values: they copy, deep-copy, and compare as such values do.

**Boundary / error behavior:**

- Any scalar that TOML v1.1.0 does not allow is refused. The parse does not yield a document mapping. The failure is the decode error in FP-04, not a type error and not some other exception kind. This includes:
  - booleans other than the lowercase `true` and `false`;
  - decimal integers, and integer parts of floats, with a leading zero (other than a lone `0`); uppercase base prefixes; leading, trailing or doubled underscores; signs on hexadecimal, octal or binary integers; digits that do not belong to the base;
  - floats without a digit on both sides of the decimal point, including a token that is only a dot;
  - escapes outside the set above, incomplete or non-hex `\x`, `\u` or `\U` runs, and escaped code points that are not Unicode scalar values (surrogates);
  - raw control characters other than tab inside any string form; a carriage return that is not part of a carriage-return/line-feed pair inside a multiline basic string; a line-ending backslash in a multiline basic string that is not followed by a line ending (only whitespace allowed in between); an unclosed string of any form;
  - date-shaped values that are not real calendar dates (including February 29 in a non-leap year), and times whose hour is not 0–23, minute not 0–59, or second not 0–59.

---

### FP-03: Parse TOML from a binary file

**Public entry:** Tomlparse’s binary-file parse entry. The caller passes a file object opened for **binary** reading. The optional float converter in FP-05 applies to this entry the same way it applies to the string-parse entry. Invalid TOML inside the file is specified in FP-04.

**Normal behavior:**

- The entry reads the file object's contents, decodes the bytes as UTF-8, and then behaves exactly as the string-parse entry on the decoded text: every structural and scalar rule of FP-01 and FP-02 applies, a carriage-return/line-feed pair is one line feed, and the result equals the string-parse result for the same characters. A file with no bytes yields an empty mapping.
- Files on disk opened in binary mode and in-memory binary buffers are both accepted.

**Boundary / error behavior:**

- A file object opened in **text** mode (on disk or in memory) is refused with a type error, whatever text it holds. The call does not return a document mapping. This is not a decode error.
- Bytes that are not valid UTF-8 do not yield a document mapping and the call does not succeed. They are never reinterpreted in another 8-bit encoding, even when that reading would be valid TOML.
- When the bytes are valid UTF-8 but the decoded text is not valid TOML v1.1.0, the failure is the decode error of FP-04, whose recoverable document is the decoded text and whose location is the one the string-parse entry reports for that text.
- The string-parse entry does not accept a file object or a bytes object; that refusal is FP-04. This feature point is only the binary-file entry.

---

### FP-04: Reject invalid TOML

**Public entry:** Both parse entries (FP-01 and FP-03), and the decode error itself. This feature point is what a caller observes when the input is not valid TOML v1.1.0, or is not the Python type that entry accepts. Structural conflicts in FP-01 and scalar conflicts in FP-02 fail in the same way described here.

**Normal behavior:**

- When the document is not valid TOML v1.1.0 (for any reason that specification gives) the parse does not succeed. Nothing is delivered as a document mapping, not even a partial one. The failure is the product’s decode error, which is a kind of value error: a caller who handles value errors also handles parse failures, and a caller who handles only the decode error does not catch unrelated type errors.
- **Location.** Every decode error carries the unformatted reason, the document text, and a 0-based character offset into that text, each recoverable separately from the formatted report, together with a 1-based line and a 1-based column derived from that offset:
  - the line is 1 plus the number of line feeds in the document before the offset;
  - the column is 1 plus the number of characters between the last line feed before the offset (or the start of the document, when there is none) and the offset.
- When the parser detects the problem at a character inside the document, the offset is the index of that character (an offset smaller than the document's length). When the document ends where more input is required (an unfinished pair, string, array, inline table or header), the offset is the document's length, which marks the end of the document rather than an interior line and column. The formatted report includes the location: the line and column for an interior offset, or an indication of the end of the document for an offset at or past the end.
- A table header or array-of-tables header that conflicts with what the document already defines (it would overwrite a value, declare a table a second time, or open a table that may not be opened) fails at a character within that header. Its offset is therefore inside the document, even when that header is the last thing in the document and nothing follows it.
- A caller can also produce the decode error by supplying a reason, a document text, and a 0-based offset. The resulting error carries exactly those three values and the line and column the rules above derive from them, and its formatted report includes that location, the same as for a parse failure.

**Boundary / error behavior:**

- The string-parse entry accepts a Python text string only. Passing any other value (bytes, a boolean, a file object, …) fails with a **type error**, not a decode error. A wrong Python type is always a type error, distinct from the decode error.
- The binary-file entry’s refusal of a text-mode file is a type error (FP-03), not a decode error.
- A decode error is not a recursion error and not a type error.
- The wording of the decode-error report is free; the exception kind and the location rules above are fixed.

---

### FP-05: Construct TOML floats with a caller-supplied converter

**Public entry:** The optional float converter on both the string-parse entry and the binary-file parse entry. When the caller does not supply a converter, FP-02’s default (Python float) applies. This feature point does not change integers, strings, booleans, date-times, tables, or arrays.

**Normal behavior:**

- When a converter is supplied, it is called for every TOML float in the document — wherever the float appears (at the root, in a table, in an array, in an inline table) and including the special spellings `inf`, `+inf`, `-inf`, `nan`, `+nan`, and `-nan` — with the float's characters exactly as written in the document (sign, underscores and exponent included) as a text string. Its return value is stored in the document mapping in place of the float, unchanged.
- Integers, strings, booleans, date-times, and the structure of tables and arrays are never passed to the converter and are built exactly as without it.
- Any callable that accepts the token text and returns a value that is not a dictionary or a list (and not an instance of a subclass of either) is allowed; such a value is bound as returned.

**Boundary / error behavior:**

- If the converter returns a dictionary or a list (or an instance of a subclass of either) for any float of the document, the parse fails with a **value error** that is not the decode error, and no mapping is returned. An illegal converter result is always this value error, distinct from the decode error.

