# Interface Contract

The product is a Cargo workspace with `Cargo.toml` at its root. Its workspace packages and Rust import roots are:

| Package | Import root or artifact |
| --- | --- |
| `rivexlib` | `rivexlib` |
| `rivexlib-parser` | `rivexlib_parser` |
| `rivexlib-algebra` | `rivexlib_algebra` |
| `rivexlib-ffi` | A `cdylib` exporting the C ABI functions below |

The `rivexlib` Cargo features are `experimental_capture_groups` for the capture API, `regex_set` for the collection API, and `serialize` for saving and loading. They can be enabled together. The `rivexlib-ffi` package also exposes `experimental_capture_groups` for its capture API.

Rust results and errors are returned directly by library calls. A fallible call returns `Result<T, Error>`: `Ok` contains its result and `Err` contains its failure. C calls exchange pointers, byte lengths, host-sized integer counts, and caller-owned output storage. C regex pointers are opaque handles.

## `rivexlib::Regex`

Public type at `rivexlib::Regex`.

### Construction and search

```rust
pub fn new(pattern: &str) -> Result<Regex, Error>;
pub fn with_options(pattern: &str, opts: RegexOptions) -> Result<Regex, Error>;
pub fn find_all(&self, input: &[u8]) -> Result<Vec<Match>, Error>;
pub fn is_match(&self, input: &[u8]) -> Result<bool, Error>;
pub fn find_anchored(&self, input: &[u8]) -> Result<Option<Match>, Error>;
pub fn is_full_match(&self, input: &[u8]) -> Result<bool, Error>;
```

`pattern` is pattern text; `input` is the searched byte slice. Construction returns a regex value. `find_all` returns a vector of whole-match spans; an empty vector represents no occurrence. `is_match` returns the existence result, and `is_full_match` returns the whole-input result. `find_anchored` returns `Some(Match)` for a prefix occurrence or `None` for its absence. These absence forms are successful `Ok` values, distinct from `Err`.

### Capture results

```rust
pub fn captures_all(&self, input: &[u8]) -> Result<Vec<Captures<'_>>, Error>;
pub fn capture_names(&self) -> &[Option<String>];
pub fn capture_index_for_name(&self, name: &str) -> Option<usize>;
```

`captures_all` returns one capture result per occurrence, or an empty vector for no occurrence. Capture indices are zero-based, with slot `0` representing the whole match. `capture_names` returns the optional name for each capture slot; the whole-match slot and unnamed slots contain `None`, and named slots contain `Some(String)`. Name lookup returns `Some(index)` or `None` for absence. Capture-operation failures may be returned by construction or by `captures_all`.

### Saved representation

```rust
pub fn dump(&self) -> Result<Vec<u8>, Error>;
pub fn load(bytes: &[u8]) -> Result<Regex, Error>;
```

`dump` returns an opaque byte vector. `load` accepts that byte representation and returns a regex value. Saving and loading failures use `Error::Serialize`.

### Pattern notation

In the notation below, angle-bracketed words stand for caller-supplied text or expressions, and `n` and `m` stand for written decimal counts.

| Construct | Written form |
| --- | --- |
| Literal text | `<text>` |
| Escaped literal | A backslash followed by the literal character |
| Hexadecimal escape | `\x<two hexadecimal digits>` or `\u{<hexadecimal digits>}` |
| Newline escape | `\n` |
| Positive and negated character classes | `[<members>]`, `[^<members>]` |
| Range within a class | `<first>-<last>` |
| Shorthand atoms | `\w`, `\d`, `\s`, `\W`, `\D`, `\S` |
| Named property and negated property | `\p{<property>}`, `\P{<property>}` |
| Special property names | `ascii`, `hex`, `utf8`, inside `\p{...}` |
| Wildcards | `.`, `_` |
| Concatenation | Adjacent expressions |
| Grouping | `(<expression>)` |
| Explicit non-capturing group | `(?:<expression>)` |
| Alternation | Expressions separated by `\|` |
| Repetition suffixes | `*`, `+`, `?`, `{n}`, `{n,}`, `{n,m}` |
| Lazy repetition suffixes | `*?`, `+?`, `??`, `{n,m}?` |
| Numeric backreference | `\<decimal capture number>` |
| Greediness-reversal flag | `(?U)`, `(?U:<expression>)` |
| Intersection | Expressions separated by `&` |
| Complement | `~(<expression>)` |
| Input anchors | `\A`, `\z` |
| Line anchors | `^`, `$` |
| Word assertions | `\b`, `\B` |
| Lookahead | `(?=<expression>)`, `(?!<expression>)` |
| Lookbehind | `(?<=<expression>)`, `(?<!<expression>)` |
| Named capture | `(?P<name><expression>)`, `(?<name><expression>)` |
| Explicit unnamed capture | `(??<expression>)` |

Inline option letters are `i` for case-insensitive matching, `s` for dot-all, `m` for multiline, and `x` for extended mode. Their positional forms are `(?<letter>)` and `(?-<letter>)`; their scoped forms are `(?<letter>:<expression>)` and `(?-<letter>:<expression>)`. Extended-mode comments use `#` as their opening marker.

## `rivexlib::RegexOptions`

Public type at `rivexlib::RegexOptions`, constructed with `RegexOptions::default() -> RegexOptions`.

Each builder consumes an options value and returns an options value:

```rust
pub fn unicode(self, mode: UnicodeMode) -> Self;
pub fn case_insensitive(self, yes: bool) -> Self;
pub fn dot_matches_new_line(self, yes: bool) -> Self;
pub fn multiline(self, yes: bool) -> Self;
pub fn ignore_whitespace(self, yes: bool) -> Self;
pub fn implicit_captures(self, yes: bool) -> Self;
pub fn hardened(self, yes: bool) -> Self;
pub fn unbounded_size(self, yes: bool) -> Self;
```

The option names respectively identify character coverage, case-insensitive matching, dot-all, multiline, extended mode, implicit captures, hardened matching, and the size-limit override. The public field `hardened: bool` exposes the hardened-matching setting.

## `rivexlib::UnicodeMode`

Public enum at `rivexlib::UnicodeMode` with unit variants:

| Variant | Mode name |
| --- | --- |
| `Ascii` | ASCII-only |
| `Default` | Limited Unicode |
| `Full` | Full Unicode |
| `Javascript` | JavaScript-oriented |

## `rivexlib::Match`

Public result type at `rivexlib::Match` with public fields:

```rust
pub start: usize;
pub end: usize;
```

`start` is the inclusive byte offset and `end` is the exclusive byte offset of a whole match or retrieved capture in the supplied input. Both offsets are zero-based.

## `rivexlib::Captures`

Public type `rivexlib::Captures<'r>` represents the captures of one occurrence and is borrowed from its regex.

```rust
pub fn spans(&self) -> &[Option<(usize, usize)>];
pub fn get(&self, i: usize) -> Option<Match>;
pub fn name(&self, name: &str) -> Option<Match>;
```

`spans` returns capture slots. Each present slot is `Some((start, end))`, using an inclusive byte start and exclusive byte end; an absent slot is `None`. Slot `0` is the whole match. `get` addresses a slot by its index; `name` addresses a group by its name. Both return `Some(Match)` for a present span or `None` for absence.

## `rivexlib::RegexSet`

Public type at `rivexlib::RegexSet`.

```rust
pub fn new<I, S>(patterns: I) -> Result<RegexSet, Error>
where I: IntoIterator<Item = S>, S: AsRef<str>;
pub fn with_options<I, S>(patterns: I, opts: RegexOptions) -> Result<RegexSet, Error>
where I: IntoIterator<Item = S>, S: AsRef<str>;
pub fn is_match(&self, input: &[u8]) -> Result<bool, Error>;
pub fn matched(&self, input: &[u8]) -> Result<Vec<usize>, Error>;
pub fn find_all(&self, input: &[u8]) -> Result<Vec<Match>, Error>;
pub fn categorize_all(&self, input: &[u8]) -> Result<Vec<TaggedMatch>, Error>;
pub fn regex(&self) -> &Regex;
```

The constructors accept an iterable of pattern text, including a borrowed `Vec<String>`. Member indices are zero-based positions in that iterable. `is_match` returns the collection's existence result. `matched` returns member indices. `find_all` returns whole-match spans, and `categorize_all` returns tagged spans. An empty result vector represents no members or occurrences, respectively. `regex` returns a borrowed regex representing the collection's combined matcher.

## `rivexlib::TaggedMatch`

Public result type at `rivexlib::TaggedMatch` with public fields:

```rust
pub start: usize;
pub end: usize;
pub tag: usize;
```

`start` and `end` are the inclusive start and exclusive end byte offsets of the occurrence. `tag` is its zero-based member index.

## `rivexlib::Error`

Public error enum at `rivexlib::Error`, supporting `Debug` formatting for diagnostic text.

| Variant and payload | Failure information |
| --- | --- |
| `Error::Parse(Box<rivexlib_parser::ParseError>)` | Pattern-text failure, with a public error kind |
| `Error::Algebra(rivexlib_algebra::RivexlibError)` | Pattern-operation failure |
| `Error::SetMember(usize, &'static str)` | Unusable collection member; the first payload is its zero-based position and the second is diagnostic text |
| `Error::Serialize(String)` | Saving or loading failure with diagnostic text |

Invalid-pattern refusals use `Error::Parse` with an invalid-pattern kind. Unsupported pattern-syntax refusals use `Error::Parse` with an unsupported kind. Assertion-related unsupported refusals can also use `Error::Algebra(RivexlibError::UnsupportedPattern)`. Capture-related unsupported refusals accept either of these error forms, including the capture-specific unsupported parse kind. Collection member refusal uses `Error::SetMember`; malformed collection-pattern syntax uses `Error::Parse`.

## `rivexlib_parser::ParseError`

Public type `rivexlib_parser::ParseError` exposes `pub kind: rivexlib_parser::ast::ErrorKind` through the payload of `Error::Parse`.

## `rivexlib_parser::ast::ErrorKind`

Public enum at `rivexlib_parser::ast::ErrorKind`.

The unsupported pattern-syntax markers are the unit variants `UnsupportedBackreference`, `UnsupportedLazyQuantifier`, and `UnsupportedRivexlibRegex`. The capture-specific unsupported marker is `CaptureGroupInLookaround`. Invalid-pattern failures use a kind distinct from these markers.

## `rivexlib_algebra::RivexlibError`

Public enum at `rivexlib_algebra::RivexlibError`. Its unit variant `UnsupportedPattern` identifies an unsupported pattern operation when carried by `Error::Algebra`.

## `rivexlib::escape`

Public function `rivexlib::escape`:

```rust
pub fn escape(text: &str) -> String;
```

The returned string is the escaped pattern fragment for the supplied literal text.

## `rivexlib::escape_into`

Public function `rivexlib::escape_into`:

```rust
pub fn escape_into(text: &str, buf: &mut String);
```

The output is the updated caller-owned string `buf`; the function returns `()`.

## `rivexlib_compile`

C ABI export with this Rust ABI declaration:

```rust
pub unsafe extern "C" fn rivexlib_compile(pat: *const u8, len: usize) -> *mut Regex;
```

`pat` points to `len` bytes of pattern text. The return value is an opaque regex handle on success or a null pointer on compilation refusal. Failure information is retrieved through `rivexlib_last_error`.

## `rivexlib_free`

C ABI export with this Rust ABI declaration:

```rust
pub unsafe extern "C" fn rivexlib_free(r: *mut Regex);
```

The caller supplies a live handle returned by `rivexlib_compile`. The call releases that handle and returns no value.

## `rivexlib_find_all`

C ABI export with this Rust ABI declaration:

```rust
pub unsafe extern "C" fn rivexlib_find_all(
    r: *const Regex,
    input: *const u8,
    len: usize,
    out: *mut usize,
    cap: usize,
) -> isize;
```

`r` is a live regex handle; `input` points to `len` input bytes. `out` is caller-owned storage of `cap` host-sized unsigned integer elements. Capacity is measured in elements, not bytes or matches. Each stored match occupies two consecutive elements, `(start, end)`, containing the inclusive start and exclusive end byte offsets. The signed return value is the total number of occurrences, or `-1` for failure. Failure information is retrieved through `rivexlib_last_error`.

## `rivexlib_last_error`

C ABI export with this Rust ABI declaration:

```rust
pub unsafe extern "C" fn rivexlib_last_error(buf: *mut u8, cap: usize) -> usize;
```

The return value is the diagnostic's full byte length. For a length query, pass `cap = 0`. For a text query, pass that length as `cap` and provide `buf` with that many writable bytes; it receives the diagnostic bytes without a terminating NUL. Both calls return the full byte length. The diagnostic has no machine-readable error-category field.

## `rivexlib_capture_slots`

C ABI export with this Rust ABI declaration:

```rust
pub unsafe extern "C" fn rivexlib_capture_slots(r: *const Regex) -> usize;
```

`r` is a live regex handle. The returned count is the number of capture slots in one occurrence, including the whole-match slot. A slot corresponds to one `(start, end)` pair in `rivexlib_captures_all` output.

## `rivexlib_captures_all`

C ABI export with this Rust ABI declaration:

```rust
pub unsafe extern "C" fn rivexlib_captures_all(
    r: *const Regex,
    input: *const u8,
    len: usize,
    out: *mut usize,
    cap: usize,
) -> isize;
```

`r` is a live regex handle; `input` points to `len` input bytes. `out` is caller-owned storage of `cap` host-sized unsigned integer elements. Capacity is measured in elements. Output consists of consecutive rows, one per occurrence, with `rivexlib_capture_slots(r)` pairs per row. Each pair is `(start, end)`, using inclusive and exclusive byte offsets. Pair `0` is the whole match. Absent slots are encoded as two maximum host-sized unsigned integers, `(SIZE_MAX, SIZE_MAX)`.

The signed return value is the total occurrence count, or `-1` for failure. Failure information is retrieved through `rivexlib_last_error`.
