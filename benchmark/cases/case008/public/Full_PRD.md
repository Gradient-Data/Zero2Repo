# Hrefparse — Full Product Requirements Document

## Product overview

**Hrefparse** is a C++ library that parses, validates, normalizes, and mutates URLs according to the WHATWG URL Standard. It also implements URLPattern matching according to the WHATWG URLPattern Standard and URL Search Params query-string handling from the same family of web platform APIs. Internationalized domain names follow Unicode Technical Standard #46 (ToASCII / ToUnicode), including Punycode for non-ASCII labels.

A common use is to take a URL string and produce its WHATWG-normalized href. That is a different contract from RFC 3986 parsers (for example curl): Hrefparse rewrites hosts and paths: it always applies WHATWG normalization (it does not merely copy the input) and never applies RFC 3986 encoding alone.

**Normative references.** The WHATWG URL Standard (URL parsing, host parsing, serialization, the URL API getters and setters, `application/x-www-form-urlencoded`, and `URLSearchParams`), the WHATWG URLPattern Standard, and UTS #46 are binding wherever this document does not state a product-specific rule. Where this document states a product-specific rule (the length cap, standalone IDNA input bounds, the accept/refuse report of writers, host kinds, origin of `file:` URLs), that rule governs.

This document specifies **user- and integrator-observable behavior only**. Exact published symbol names, header paths, and other Interface Contract details are out of scope here. Every feature point below corresponds to behavior that exists in the finished Hrefparse library. Feature points are ordered so foundational capabilities come first; a later feature point may depend on an earlier one, never the reverse.

## Terminology

| Term | Meaning in this PRD |
| --- | --- |
| **href** | The full serialized URL after WHATWG parsing or mutation (the URL Standard’s href). |
| **Base URL** | An already-parsed absolute URL used to resolve a relative input. |
| **Special scheme** | One of the WHATWG special schemes: `ftp`, `file`, `http`, `https`, `ws`, `wss`. These schemes have dedicated parsing rules and (except `file`) a default port. |
| **Non-special scheme** | Any other scheme. |
| **Opaque path** | A non-hierarchical path (the URL Standard’s opaque path). Host mutation is refused; path shortening with `..` does not apply. |
| **Host** | Hostname plus port when a non-default port is present (WHATWG host). |
| **Hostname** | The host without a port (WHATWG hostname). Domain names, IPv4 addresses, and IPv6 addresses are the three host kinds. |
| **Origin** | The WHATWG serialized origin (scheme, host, and port for tuple origins; the Standard’s opaque-origin serialization for opaque origins). Credentials, path, query, and fragment are not part of the origin. |
| **IDNA** | Internationalized Domain Names in Applications: ToASCII / ToUnicode per UTS #46, with Punycode (`xn--`) labels in ASCII hosts. UTS #46 CheckBidi and CheckJoiners validity checks are not part of this product's obligations. |
| **URL Search Params** | The WHATWG query-string list of key/value pairs (the search parameters API), independent of a full URL object. |
| **URLPattern** | The WHATWG URLPattern matcher: patterns over URL components, with named groups, wildcards, and optional custom regular expressions. |
| **Length cap** | A process-wide maximum byte length for a URL’s raw input and serialized href (and for related search-parameter input). Default is the maximum 32-bit unsigned integer. The caller may lower it. |

## Public surface inventory

Hrefparse is a **library**. Integrators reach it by compiling and linking the Hrefparse C++ library (including the documented single-header amalgamation) or by using the matching **C interface**. An optional command-line tool may exist; it is not part of the required product.

The library’s public surfaces are:

- Parse a URL string (ASCII or valid UTF-8), optionally against a base URL; report success or failure; serialize the href.
- Answer whether a string (optionally with a base) would parse successfully, in agreement with an actual parse of the same input, including length-cap rejections.
- Convert a filesystem path to a `file:` URL.
- Convert a domain with ToASCII and ToUnicode (IDNA), including as a standalone conversion on the C interface.
- Read and write WHATWG URL components on a successfully parsed URL: href, origin, protocol, username, password, host, hostname, port, pathname, search, hash; query presence of credentials, hostname, port, search, and hash; distinguish host kind (domain, IPv4, IPv6).
- Configure and read the length cap; rejected parse and rejected mutation never leave a longer href.
- Parse, mutate, sort, iterate, and serialize URL Search Params.
- Compile and match URLPattern patterns (C++ library; the caller supplies a regular-expression engine).

Feature points below group these entries by capability. They do not invent additional products.

## Non-functional constraints

- **Form factor:** An embeddable C++20 library with a C interface. No runtime third-party dependency. A recent C++ compiler is required (GCC 12 or newer, LLVM 14 or newer, or Microsoft Visual Studio 2022). CMake 3.16 or newer builds the library from this repository.
- **Platforms:** Windows, Linux, and macOS are first-class. The documented execution target is Linux x86_64 with a C++20 toolchain and CMake.
- **Hardware:** CPU-only. No GPU or accelerator is required or claimed.
- **Input encoding:** Public string inputs are ASCII or valid UTF-8. The caller is responsible for UTF-8 validity.
- **Default length cap:** The maximum 32-bit unsigned integer until the caller lowers it. The cap is inclusive: a length equal to the cap is accepted, a greater length is rejected. For URLs it applies to both the raw input and the **normalized** href (percent-encoding expansion counts). The same cap applies to filesystem-path conversion and to URL Search Params construction and reset (measured on the query string after a leading `?` is dropped). Individual search-parameter append/set calls are not length-capped.
- **Standalone IDNA input bound:** Standalone ToASCII and ToUnicode share one fixed input bound in bytes. Its value is the implementer's choice, at least 1024 and less than 20000. Standalone ToASCII accepts inputs up to the bound; a longer input fails and yields no usable domain, whatever its content. Standalone ToUnicode never fails; an input longer than the bound is returned unchanged.
- **URLPattern regular expressions:** Hrefparse does not ship a regular-expression engine. The caller supplies an engine that can compile a pattern (with or without case folding), search (yielding capture groups), and match (yes or no). That is a security boundary: the C++ standard library’s regular expressions are not treated as a safe default for untrusted patterns.
- **Two in-memory layouts:** Callers may request a compact form backed by one serialized string, or a form that stores components as separate strings. Both expose the same parse, inspect, and mutate outcomes described here. Choosing a layout is not a separate feature point.

## Required substance (global)

Every feature point below is implemented in the compiled Hrefparse library file; the public headers declare the API and programs obtain its behavior by linking that library.

## Non-goals

- Being an RFC 3986 parser, or matching curl’s “leave the string unchanged” behavior.
- Shipping a regular-expression engine for URLPattern.
- Parts of the cited standards outside the surfaces this document describes: reporting non-fatal validation errors (a parse or a write reports only success or failure and the resulting components), the JavaScript binding surface (thrown exceptions, static members), and URLPattern pattern lists, pattern comparison, and generating a URL from a pattern.
- Guaranteeing a particular nanosecond-per-URL speed (speed is a design goal, not a requirement).
- Language bindings maintained outside this repository (Rust, Go, Python, and others).
- Treating build options, amalgamation scripts, release automation, fuzzers, or benchmarks as user-facing product capabilities.

---

## Feature points

### FP-01: Parse, validate, and serialize URLs

**Public entry:** The Hrefparse C++ library parse entry and the matching C interface parse entry, each taking an ASCII or UTF-8 URL string and optionally a base URL; the dedicated “can this parse” entry (string, optionally with a base string); filesystem-path conversion to a `file:` URL; standalone IDNA ToASCII and ToUnicode on the C interface; the process-wide length cap configuration.

**Normal behavior:**

- Parsing follows the URL Standard’s basic URL parser and the href is the Standard’s URL serializer output, which may differ from the input. Leading and trailing C0 controls and spaces are stripped. ASCII tab, line feed, and carriage return are then removed wherever they remain; they are never percent-encoded. Code points in the path, query, and fragment are percent-encoded with the Standard’s percent-encode sets (UTF-8 bytes, so a remaining space becomes `%20` in path and query; `+` is literal and never means a space). A `%` that does not start a valid percent-sequence is kept verbatim in path, query, and fragment.
- Special schemes are exactly `ftp`, `file`, `http`, `https`, `ws`, and `wss`. Default ports used in parsing and serialization are: `http` and `ws` → 80; `https` and `wss` → 443; `ftp` → 21; `file` has none. A default port is omitted from the href; a non-default port is kept.
- Relative inputs resolve against a successfully parsed base per the URL Standard, including `.` and `..` segment handling. A relative input with no base fails.
- Scheme and host of special-scheme URLs are ASCII-case-insensitive and serialize lowercased.
- Hosts go through the WHATWG host parser. For special schemes the host is percent-decoded, converted with the Standard’s domain-to-ASCII (UTS #46 ToASCII with Unicode Normalization Form C, Punycode `xn--` labels for non-ASCII labels, mapping of Unicode look-alike punctuation), and checked for forbidden domain code points. A host that the Standard reads as an IPv4 address (decimal, octal with a `0` prefix, or hexadecimal with a `0x` prefix parts) serializes as dotted decimal; IPv6 hosts serialize in brackets in the Standard’s compressed form. Non-special schemes use the Standard’s opaque-host parser.
- Windows drive letters are handled as the URL Standard specifies for `file:` URLs; no other scheme receives drive-letter treatment.
- Filesystem-path conversion returns the href obtained by parsing `file://` and then setting the given path as the pathname with the URL Standard’s pathname setter.
- The “can this parse” entry returns yes if and only if parse of the same input (and base, when given) would succeed — including when the length cap rejects a normalized href that is longer than the input. It does not require the caller to keep the URL object.
- Standalone ToASCII follows the Standard’s domain-to-ASCII with beStrict false: an all-ASCII input within the IDNA input bound succeeds and yields the input ASCII-lowercased, with no further validation; forbidden host code points are a host-parser failure, not a standalone ToASCII failure. An input with non-ASCII code points is processed with UTS #46 (UseSTD3ASCIIRules false, Transitional_Processing false, VerifyDnsLength false) and yields an ASCII domain with Punycode labels, or fails when a label is invalid. Host parsing of a special-scheme URL yields the same ASCII domain as standalone ToASCII of the same host.
- Standalone ToUnicode decodes Punycode labels back to Unicode per UTS #46 (labels that cannot be decoded are kept as they are); ToASCII of that result returns the original ASCII domain.
- When the caller lowers the length cap to N bytes, any parse whose raw input or normalized href is longer than N fails, and “can this parse” agrees; percent-encoding expansion counts toward the normalized length.

**Boundary / error behavior:**

- Every input that the URL Standard’s basic URL parser rejects (with the given base, or with no base) fails.
- When the length cap would be exceeded, parse fails, filesystem-path conversion yields an empty string, and no URL is produced. Raising the cap back to the default restores acceptance of ordinary-length URLs.
- Standalone ToASCII of an input longer than the IDNA input bound fails and yields no usable domain.
- A failed parse does not yield a usable URL. The caller can tell success from failure before reading href or any component.


---

### FP-02: Inspect and mutate URL components

**Public entry:** Component readers and writers on a successfully parsed Hrefparse URL, through the C++ library and the C interface: href, origin, protocol, username, password, host, hostname, port, pathname, search, hash; presence queries for credentials, hostname (including empty hostname), port, search, and hash; host-kind distinction; clearing port, search, and hash; replacing the entire href. The length cap from FP-01 also governs these mutations. This feature point depends on a successful parse (FP-01).

**Normal behavior:**

- Readers return the URL Standard’s URL API getter values: protocol is the scheme followed by `:`; username and password are the stored credentials (empty when absent); host is the serialized host followed by `:` and the port when a port is present; hostname is the serialized host without a port; port is the decimal port without a colon, empty when absent (a default port is never stored); pathname of a hierarchical URL of a special scheme is at least `/`; search and hash include their leading `?` or `#` when the component is present and non-empty, and are empty otherwise.
- Origin of a URL whose scheme is special and not `file` is the tuple-origin serialization: scheme, `://`, host, and `:port` only for a non-default port — never credentials, path, query, or fragment. Every other URL, including every `file:` URL (with or without a host), has an opaque origin and returns the Standard’s opaque-origin serialization; that string is the same for all such URLs.
- Writers apply the URL Standard’s setter algorithms for href, protocol, username, password, host, hostname, port, pathname, search, and hash. Search and hash writers accept values with or without a leading `?` or `#`. A host value that carries a port sets hostname and port together; a hostname write never changes the port.
- Each writer except search and hash reports whether the write was accepted or refused. A write is refused exactly when the Standard’s setter rejects the value or ignores the write; a refused write leaves the URL unchanged (same href, same components). An accepted write leaves the URL exactly as the Standard’s setter would.
- Replacing the href parses the new value exactly as FP-01 parse does and rebuilds every component from it; a value FP-01 would reject is refused.
- Setting an empty host or hostname on a URL with a non-special scheme and a hierarchical path but no authority inserts an empty authority, as the Standard’s setter does; the URL then has a hostname (an empty one).
- A non-special scheme has no default port, so a port is kept across a protocol change between non-special schemes.
- Clearing port, search, or hash removes only that component; the other components, including the other two of these three, are unchanged, and the origin loses a cleared port.
- Host kind distinguishes domain, IPv4, and IPv6 hosts: three distinct values, the same value for every host of one kind.
- “Has credentials” is true when username or password is non-empty. “Has hostname” is true when a host is present (including an empty host). “Has port”, “has search”, and “has hash” are true exactly when that component is present, independently of the others.

**Boundary / error behavior:**

- Every write that the Standard’s setter algorithm rejects or ignores is refused, as is every value the component’s parser rejects. A refused host or hostname write never inserts an authority.
- Host and hostname writes use the host parser of the URL’s scheme: the WHATWG host parser for special schemes and the opaque-host parser, which does not validate percent-sequences, for non-special schemes.
- Setting port to the empty string removes the port.
- When a write would make the serialized href exceed the length cap, the URL is left unchanged. Host, hostname, protocol, username, password, port, pathname, and href writes that overrun are refused. Search and hash writes that overrun also leave search, hash, and href unchanged (there is no separate success report; the URL simply does not change). Percent-encoding expansion counts toward the cap.


---

### FP-03: URL Search Params

**Public entry:** The Hrefparse URL Search Params type through the C++ library and the C interface: construct from a query string (with or without a leading `?`); append; set; get the first value; get all values for a key; has (by key, or by key and value); remove (by key, or by key and value); sort; serialize to a query string; iterate keys, values, and entries; reset from a new query string; report the number of pairs. Construction and reset honor the length cap from FP-01. This capability is independent of a full URL object; a caller may also take a URL’s search component (FP-02) and feed it here.

**Normal behavior:**

- Construction and reset parse the input with the `application/x-www-form-urlencoded` parser: a leading `?` is dropped and is never part of the first key; pairs are split on `&`, empty pieces are skipped, a piece without `=` has an empty value, and `+` and percent-sequences in names and values are decoded.
- The object is an ordered list of pairs. Append adds a pair at the end; the same key may appear several times. Get returns the first value for a key; get-all returns every value for a key in list order; has-by-key is true if any pair has that key; has-by-key-and-value is true if any pair matches both. Size counts every pair, duplicates included.
- Set replaces the value of the first pair with that key, removes every later pair with that key, and keeps the first pair’s position; when the key is absent it appends a new pair.
- Remove-by-key deletes every pair with that key. Remove-by-key-and-value deletes only pairs that match both.
- Sort is a stable sort of the pairs by key, comparing keys as sequences of UTF-16 code units (not UTF-8 bytes); pairs with equal keys keep their relative order.
- Serialize applies the `application/x-www-form-urlencoded` serializer and has no leading `?`: a space becomes `+`; bytes outside the urlencoded set (including `+`, `&`, `=`, and the UTF-8 bytes of non-ASCII code points) are percent-encoded with uppercase hex; an empty key or value serializes as the empty string around `=`. Readers return the decoded values (a space, not `+`; the original Unicode, not percent-sequences).
- Iterators over keys, values, and entries walk the current list in order, once per pair. After a mutation of the list, previously obtained iterators are not required to remain valid.
- Reset replaces the list from a new query string, subject to the length cap.

**Boundary / error behavior:**

- Construction or reset with a query string longer than the length cap leaves the object empty (size 0, serialize empty, no key present); a query string exactly at the cap is accepted. Append and set of individual pairs are not rejected for length.
- Get of a missing key yields no value, distinguishable from a present key whose value is the empty string. Has is false for a missing key. Get-all of a missing key is an empty list.


---

### FP-04: URLPattern matching

**Public entry:** The Hrefparse C++ library URLPattern parse entry (not the C interface). The caller supplies a regular-expression engine with compile, search, and match. Input is either a pattern string or a per-component initializer covering the finite component set: protocol, username, password, hostname, port, pathname, search, hash. An optional base URL string resolves relative patterns. An optional ignore-case flag folds case in the compiled expressions. After a successful compile, the caller may test (yes/no), execute/match (structured result), and read each compiled component’s pattern string.

**Normal behavior:**

- Compiling and matching follow the URLPattern Standard: a pattern string is split into components, resolved against the base URL when one is given (components the base fixes must then match as well); an initializer compiles only the components it sets, the others matching anything. Named groups `:name` match one segment up to the next separator of the component; a full wildcard `*` matches the rest of the component, separators included; a `?` modifier makes a group optional, and an optional group that does not participate has no captured value, distinguishable from a bound group; a parenthesized regular expression after a group name restricts what the group matches; literal text matches exactly.
- Each component is compiled to a regular expression in ECMAScript syntax as the URLPattern Standard generates it, and handed to the caller’s engine together with the ignore-case choice. Ignore-case is a compile-time choice applied to every component.
- Test returns yes exactly when execute/match produces a match. On a match, execute/match returns one sub-result for each of the eight components, each with the component input string and a map from every group name of that component to its captured string (or no value for a group that did not participate).
- Each compiled component’s pattern string is readable and is the URLPattern Standard’s normalized pattern string for that component.
- The library reports whether the compiled pattern contains regular-expression groups: true exactly when some group carries a custom regular expression; false for patterns made only of literals, named groups without a custom expression (optional or not), and full wildcards.

**Boundary / error behavior:**

- Compile fails (no usable URLPattern) for a syntactically invalid pattern, for a custom regular expression that the supplied engine cannot compile, and whenever the engine reports that it cannot create an expression. That failure is distinguishable from a compiled pattern that simply matches nothing.
- Test or execute/match of an input that does not match — including an input that cannot be parsed as a URL — returns no-match (test is false; execute/match has no match payload), not an error.
- URLPattern is not available through the C interface.

