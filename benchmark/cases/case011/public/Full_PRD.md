# PathSel — Full Product Requirements Document

## Product overview

**PathSel** (pronounced "path sel") lets a caller declaratively specify how to extract values from a JSON document. The **pathsel.py** library evaluates a PathSel expression against ordinary Python data — mappings, sequences, strings, numbers, booleans, and null — and returns the selected value.

A first-time integrator evaluates a dotted path against a nested mapping and receives the nested value the path names; a path that is absent yields null rather than failing.

The library exposes two complementary ways to evaluate an expression: a one-shot search that takes the expression text and the document together, and a compile-then-search path that parses the expression once and applies the same parsed expression to many documents. Both paths produce the same result for the same expression and document. Optional evaluation options control how constructed mappings are built and let the caller attach extra language functions.

This document specifies **user- and integrator-observable behavior only**. Exact published symbol names, import paths, call spellings and the carriers of failure kinds belong in the Interface Contract, not here. Every feature point below corresponds to behavior that exists in the finished pathsel.py product. Feature points are ordered so foundational capabilities come first; a later feature point may depend on an earlier one, never the reverse.

## Terminology

| Term | Meaning in this PRD |
| --- | --- |
| **PathSel expression** | A Unicode text in the PathSel language. One expression is evaluated against one current value at a time. |
| **Document** | The Python value supplied as the starting current value: typically a mapping or sequence that came from JSON, but any nested combination of the six data types below is accepted. |
| **Search entry** | The one-shot library entry: the caller supplies an expression and a document (and optionally evaluation options) and receives the selected value, or the call does not succeed. Specified in FP-01. |
| **Compile entry** | The library entry that parses an expression once and returns a parsed expression. Specified in FP-01. |
| **Parsed expression** | The successful result of the compile entry. It can be searched against many documents without re-supplying the expression text. |
| **Current value** | The value the expression is looking at. Search starts with the document. Pipe, projection, and function argument evaluation change the current value for a subexpression. |
| **Null** | The language’s missing or empty result. It is Python’s none. A missing field, an out-of-range index, and a selector applied to the wrong kind of value all yield null; they do not fail. |
| **Object** | A mapping (JSON object). Keys are strings. |
| **Array** | A sequence (JSON array). |
| **Number** | An integer or a floating-point value. Host decimal values participate as numbers in comparisons. A boolean is not a number. |
| **String** | A Unicode text value. |
| **Boolean** | The values true and false. They are not the numbers 1 and 0. |
| **Expression reference** | A deferred subexpression, written with a leading ampersand, that a built-in function later applies to each element. Specified in FP-05 and used in FP-07. |
| **False value** | A value the language treats as false for the and operator, the or operator, the not operator, and filter predicates. The finite set is: false, null, the empty string, the empty array, and the empty object. The number 0 and the number 0.0 are not false values. |
| **True value** | Any value that is not a false value. |
| **Projection** | An expression that walks every element of an array (or every value of an object) and collects the non-null results of a right-hand subexpression into a new array. Null results are dropped, not stored. Which following steps form the right-hand subexpression is specified in FP-04. |
| **Evaluation options** | An optional object the caller attaches to a search. It may supply a mapping type for constructed objects and a custom function provider. Specified in FP-08. |
| **Built-in function** | One of the finite set of language functions listed in FP-07. A function is invoked by name with parentheses. |
| **Failure kind** | A category of refusal. Every refusal is a kind of value error, and every refusal belongs to exactly one kind: empty expression, incomplete expression, syntax, zero slice step, unknown function, invalid arity, or invalid type. A caller can tell the kinds apart through the carrier the Interface Contract states; the wording of a failure report is informational. |
| **Token-level syntax failure** | A syntax failure detected while the text is being split into tokens: a character that begins no token, an unterminated quoted identifier, raw string or JSON literal, or the content of a quoted identifier or JSON literal that cannot be read. |
| **Grammar-level syntax failure** | A syntax failure on text that splits into valid tokens which do not form a well-formed expression. |
| **Position** | The zero-based character offset in the expression text at which a syntax or incomplete-expression failure was detected (see FP-01). |

## Public surface inventory

pathsel.py is a **library**. Integrators reach it by installing the package and calling the search entry or the compile entry. Any command-line program is outside the required product (see Non-goals).

The public surfaces, grouped the way later feature points describe them, are:

- Evaluate a PathSel expression against a document, either in one shot or by compiling first and searching the parsed expression; missing paths yield null; empty or ill-formed expression text does not succeed (FP-01).
- Select fields by unquoted and quoted identifiers, including dotted subexpressions and whitespace between tokens (FP-02).
- Select array elements by index (including negative indices), by slice, and by one-level flatten (FP-03).
- Project through list wildcards, object wildcards, and filter predicates (FP-04).
- Build new arrays and objects with multiselect, chain results with pipe, name the current value, write JSON literals and raw strings, and form expression references (FP-05).
- Compare values and combine them with and, or, not, and parentheses (FP-06).
- Call the finite set of built-in functions, including those that consume expression references (FP-07).
- Control constructed-object type and attach custom language functions through evaluation options (FP-08).

## Non-functional constraints

- **Form factor:** A pure-Python library with zero declared runtime third-party dependencies. No compiled extensions, native code, GPU, or accelerator are required.
- **Language:** Python 3.9 or newer, CPython and PyPy.
- **Platforms:** Linux, macOS, and Windows.
- **Hardware:** CPU-only. The package is imported from the repository's own source tree.
- **Data model:** The six JSON types — object, array, string, number, boolean, null — plus expression references as function arguments. Host decimal numbers are numbers for comparison (FP-06), not for built-in functions: a function argument that requires a number refuses a host decimal as the invalid-type kind, on either entry. Host values that are not one of those types are accepted as current values and can be selected and returned; a built-in function argument that requires a particular JSON type refuses them as the invalid-type kind unless a conversion function defines another outcome (FP-07).
- **Missing is null:** A path that does not exist yields null. That is success with a null result, not a search failure.
- **Failure reports:** The wording of failure messages is informational. What is required is success versus failure, that every failure is a kind of value error, that each failure belongs to its kind as defined in this document, and, for syntax and incomplete failures, the position.
- **Evaluation:** Results come from evaluating the expression against the supplied document.

## Non-goals

- A command-line program. Whether the package ships one, and what it does, is not specified here.
- Being a JSON encoder or decoder. The library evaluates expressions against already-loaded Python values. How a caller reads JSON text into those values is outside this product.
- Mutating the input document. Evaluation returns a selected or constructed value; it does not write back into the caller’s document.
- A particular evaluation-throughput figure.
- Development tooling, packaging scripts, and internal caching; none of these is observable through the library entries.
- A later official language revision that this library does not implement. The language is the expression surface documented here.

---

## Feature points

### FP-01: Search an expression and compile it for reuse

**Public entry:** The search entry and the compile entry of the pathsel.py library. The caller supplies expression text. The search entry also supplies a document and may supply evaluation options (FP-08). The compile entry returns a parsed expression; searching that parsed expression against a document (with optional evaluation options) is the second path. Field selection, indexing, projections, constructors, logic, and functions are specified in FP-02 through FP-07. This feature point is the two entries, the missing-path-is-null rule, and the failures that prevent any evaluation.

**Normal behavior:**

- A dotted path selects the nested field it names and returns that field's value (not the document, not an enclosing mapping).
- A parsed expression can be searched any number of times, against any documents; each search evaluates against the document it is given, without a new compile.
- For every expression, document and options, the one-shot search and compile-then-search return equal values, and they refuse the same expression texts with the same failure kinds.
- A path that does not exist on the document yields null, at whatever depth the path stops matching. An identifier applied to anything other than an object (including an array) yields null: an identifier selects a field of an object, never an array element.
- Compiling a well-formed expression succeeds even when every later search of it yields null.

**Boundary / error behavior:**

- **Empty expression:** the zero-length text does not succeed on either entry; it is the empty-expression kind. It is distinct from a successful null and from every other kind.
- **Incomplete expression:** text that ends (with only whitespace, or nothing, remaining) at a place where an operand expression must still begin or where a closing parenthesis, bracket or brace is still required does not succeed; it is the incomplete-expression kind. A text consisting only of spaces, tabs, line feeds and carriage returns is this kind (an operand is required), never the empty-expression kind.
- **Syntax:** any other text that is not a well-formed expression does not succeed; it is the syntax kind. This includes: a dot that is not followed by an identifier, a wildcard, a multiselect list or a multiselect hash — whatever follows it, including another dot, a number, a literal, or the end of the text; a dot where an operand must begin; a closing bracket, brace or parenthesis without a matching opener; a token left over after a complete expression; a projection-starting form (FP-04) followed directly by anything other than a dot, a bracket, a filter, a flatten, a pipe, a binary operator, a comma, a closing bracket, brace or parenthesis, or the end of the text; a slice with more than three colon-separated parts or with a part that is not an integer; and every token-level failure.
- Grammar-level and token-level syntax failures are one family. Grammar-level failures all present exactly the syntax kind. Each token-level failure presents a more specific form of the syntax kind: a caller that handles the syntax kind handles it, yet it is distinguishable from the plain syntax kind. Neither form is the empty-expression or incomplete-expression kind.
- **Position:** a syntax or incomplete-expression failure reports its position — the offset at which the token where the expression stopped being well-formed begins. The end of the text counts as a token whose offset equals the text's length; a token-level failure reports the offset where the token that could not be read begins. Two syntax failures detected at different offsets report different positions.
- Every one of those failures is a kind of value error and yields no search result; each is distinguishable from a successful search that returns null.

---

### FP-02: Select fields with identifiers and subexpressions

**Public entry:** The search entry and the compile-then-search path of FP-01. This feature point is how an identifier names a field and how a dot chains selections. Indexing is FP-03. Wildcards are FP-04.

**Normal behavior:**

- An unquoted identifier starts with a Latin letter (`A`–`Z`, `a`–`z`) or an underscore and continues with Latin letters, decimal digits, or underscores. It selects the field of the current object whose key equals it.
- A dot chains selections: the identifier after a dot selects a field of the value selected before it, for any number of segments.
- Spaces, tabs, line feeds, and carriage returns may appear between any two tokens and do not change meaning.
- A quoted identifier is a JSON string literal in double quotes. Its content is decoded exactly as JSON decodes a string (every JSON escape, including `\uXXXX`), and it selects the key equal to the decoded text. It can therefore name any key, including keys with spaces, dots, hyphens, quotes, control characters, non-ASCII characters, or a leading digit. A quoted identifier containing a dot names one key; it never walks two levels. The quote characters are not part of the key.
- Applying a field identifier to a value that is not an object yields null; in particular a field identifier on an array yields null and does not project (projections are FP-04).

**Boundary / error behavior:**

- A number cannot be used as an identifier: a dot followed by a number (with or without a leading minus) is a grammar-level syntax failure. A key that looks like a number is selected with a quoted identifier.
- A hyphen is not an identifier character: an unquoted identifier followed by a hyphen that does not begin a number is a token-level syntax failure (a lone hyphen begins no token). A hyphenated key is selected with a quoted identifier.
- A dot at the start, at the end, or doubled is a grammar-level syntax failure (FP-01).
- An unterminated double-quoted identifier, or one whose content is not a legal JSON string (for example an illegal escape), is a token-level syntax failure.
- A missing field yields null, not a failure, at any depth.

---

### FP-03: Index, slice, and flatten arrays

**Public entry:** The search and compile entries of FP-01. This feature point is bracket selection on arrays: a single index, a slice, and the flatten operator. Wildcards and filters are FP-04.

**Normal behavior:**

- An integer in square brackets selects one element, zero-based. A negative index counts from the end (minus one is the last element). An index outside the array, at either end, yields null.
- Indexing a value that is not an array — including an object and a string — yields null.
- A slice is `[start:stop]` or `[start:stop:step]`; any of the three parts may be omitted. It selects a new array as follows:
  - The step defaults to 1. A step may be negative.
  - A negative start or stop has the array length added to it.
  - With a positive step, an omitted start means the beginning and an omitted stop means the end; start and stop are then clamped to the range from 0 to the length. The selection is start, start+step, … while the index is below stop.
  - With a negative step, an omitted start means the last element and an omitted stop means past the beginning; start and stop are then clamped to the range from -1 to length-1. The selection is start, start+step, … while the index is above stop.
  - A slice that selects nothing is the empty array, not null and not a failure.
- A slice on a value that is not an array yields null.
- A slice is a projection: an expression after the slice is applied to each selected element, and null results are dropped.
- The flatten operator is empty square brackets `[]`, written with nothing between them. If the current value is an array, each element that is itself an array is spliced in one level (only one level per `[]`); each element that is not an array is kept as a single item. Flatten of a value that is not an array yields null.
- Flatten is a projection: an expression after `[]` is applied to each element of the flattened array, and null results are dropped. Flatten applies to the whole result of everything to its left, including the result of a preceding projection.
- Index, slice and flatten may be the whole expression or the start of one, applying to the document itself.

**Boundary / error behavior:**

- A slice whose step is 0 does not succeed on either entry (for compile-then-search, either the compile or the later search refuses). That failure is the zero-slice-step kind: a kind of value error, not a successful empty array, and distinct from the syntax kind.
- A slice with more than three colon-separated parts, or with a part that is not an integer (an identifier, an operator), is a grammar-level syntax failure.
- Out-of-range indices and slices do not fail: they yield null or a (possibly empty) array as specified above.

---

### FP-04: Wildcard and filter projections

**Public entry:** The search and compile entries of FP-01. This feature point is the star wildcard on arrays and on objects, and the filter projection `[?...]`. Flatten and slices are FP-03. Filter predicates use the comparators and truthiness of FP-06; the collection rule is specified here.

**Normal behavior:**

- A list wildcard is `[*]`. It requires an array: it projects over the array's elements, applying the expression to its right to each element and collecting the non-null results in order. With nothing to its right, it collects the non-null elements. A list wildcard on a value that is not an array (including a missing value) yields null.
- An object wildcard is a star in a field position: `*` or `<expr>.*`. It requires an object and projects over that object's **values**, in the object's iteration order, collecting the non-null results. An object wildcard on a value that is not an object yields null.
- A projection inside the right-hand side of another projection yields one inner array per outer element; an inner result that is null (for example an inner wildcard on a non-array) is dropped from the outer array.
- A filter is `[?predicate]`. Its left-hand value must be an array; otherwise the result is null. For each element, the predicate is evaluated with that element as the current value; elements whose predicate is a true value are kept in order, others are omitted. An expression after the filter is a projection over the kept elements, dropping nulls.
- A predicate may be any expression: a bare field (its truthiness decides; the number 0 is a true value and null is a false value), a comparison with field paths or literals on either side, or a combination with the logic operators of FP-06.
- Equality in a predicate is JSON value equality (FP-06): it never treats the number 0 as false or the number 1 as true.
- **Reach of a projection.** The projection-starting forms are the list wildcard, the slice (FP-03), the object wildcard, the filter, and flatten (FP-03). The steps after such a form divide into its right-hand side, which is applied to each element, and the steps that apply to the collected array:
  - The step written directly after the form (a dot step; a bracket step, which is an index, a slice, a list wildcard or a multiselect list; or a filter) begins the right-hand side. When anything else follows the form, the right-hand side is empty.
  - Steps and projections are ranked, from loosest to tightest: (1) flatten; (2) a list wildcard, a slice, and an object wildcard that begins an operand or is itself the first step of another projection's right-hand side; (3) a filter; (4) a dot step, including every other object wildcard; (5) an index, slice or list-wildcard bracket written as a step.
  - Each later step joins the right-hand side only when it ranks tighter than the projection. The first step that does not, and every step after it, applies to the projection's collected array.
  - A projection that starts inside a right-hand side has its own right-hand side by the same rule. When that right-hand side ends, the next step is tested against the enclosing projection.
  - A comparison, `&&`, `||`, a pipe, a comma, and a closing bracket, brace or parenthesis end every open projection: the projection's whole result array becomes the operand. A comparison after a list wildcard therefore compares the whole projected array, not each element.
  - Two placements are the implementer's choice: whether a slice written directly after an index, or directly after such a slice, starts a projection; and, when a right-hand side begins with a dot followed by a multiselect list or hash, whether later steps join it.

**Boundary / error behavior:**

- A wildcard followed directly by an identifier, a star, or a number (without a dot or bracket) is a grammar-level syntax failure. A star directly after an identifier is a syntax failure.
- A filter on a non-array yields null, not an empty array and not a failure. A filter whose predicate is ill-formed or missing does not succeed.
- Projected nulls are dropped, never stored.

---

### FP-05: Construct results, pipe, current value, and literals

**Public entry:** The search and compile entries of FP-01. This feature point is multiselect lists and hashes, the pipe operator, the current-value token, JSON literals, raw string literals, and expression references. Functions that consume expression references are FP-07.

**Normal behavior:**

- A multiselect hash is curly braces of comma-separated `key: expression` pairs. It builds a new object with one entry per pair, in declaration order; each value is the expression evaluated against the current value. A right-hand expression that yields null stores null under its key (the key is not omitted). Keys are unquoted or quoted identifiers; a quoted key is decoded as in FP-02.
- A multiselect list is square brackets of comma-separated expressions. It builds a new array with one element per expression, in order, storing nulls.
- A multiselect list or hash may appear at the top level, after a dot, or as the right-hand side of a projection (one constructed value per projected element). A multiselect list written directly after an operand, without a dot, is allowed only as the first step of a projection's right-hand side; anywhere else a bracket directly after an operand is an index, a slice, a list wildcard, a filter or a flatten, and any other bracket content there is a grammar-level syntax failure. A multiselect list or hash whose current value is null yields null.
- Pipe `|` evaluates the left-hand expression, then evaluates the right-hand expression with that result as the current value. Spaces around `|` are optional. Pipe stops a projection: the right-hand side sees the whole left-hand result, not one element at a time. Pipe binds more loosely than every other operator.
- The current-value token `@` is the current value itself (the document at the top level, the element inside a projection or function argument).
- A JSON literal is text between backticks. A backtick inside the literal is written as a backslash then a backtick. The text, with those escapes replaced, is read as JSON and the result is the literal's value, regardless of the document. Leading and trailing whitespace inside the backticks is allowed. If the text is not valid JSON, it is read as the content of a JSON string after removing leading whitespace (the literal is then that string). A literal may start a subexpression (field, index, and so on applied to the literal value).
- A raw string literal is text between single quotes; its value is a string. No JSON escapes are processed. A backslash and the character after it are read together: the pair backslash-quote stands for a single quote, and every other pair is kept exactly as written (both characters). Whitespace is kept. A raw string of digits is a string, not a number.
- An expression reference is an ampersand followed by an expression, which extends to the end of the enclosing function argument, multiselect element, parenthesized expression, or whole expression. It does not evaluate the expression: its value is a reference that FP-07 functions apply later. Searching an expression reference on its own succeeds and yields a non-null value that is neither the document nor the result of evaluating the referenced expression. Passing a non-reference where a function requires a reference is invalid-type (FP-07).

**Boundary / error behavior:**

- An unclosed backtick literal, an unclosed raw string, and a literal whose text is neither valid JSON nor valid JSON string content are token-level syntax failures.
- A literal is not an identifier: a literal directly after a dot is a grammar-level syntax failure.
- A multiselect list or hash missing its closing bracket or brace, missing a key, a colon or a value, or having a trailing comma does not succeed.
- A pipe with a missing side does not succeed.

---

### FP-06: Compare values and combine them with logic

**Public entry:** The search and compile entries of FP-01. This feature point is `==`, `!=`, `<`, `<=`, `>`, `>=`, `&&`, `||`, `!`, and parentheses. Filters in FP-04 use these operators. Truthiness is the false-value set in Terminology.

**Normal behavior:**

- `==` is true when the two sides are the same JSON value (deep equality of arrays and objects; integers and floating-point numbers compare by value); `!=` is its negation. A number is never equal to a boolean: 0 is not equal to false and 1 is not equal to true.
- `<`, `<=`, `>`, `>=` compare two numbers numerically, or two strings in Unicode code-point order. Host decimals participate as numbers.
- An ordering comparison in which either side is an array, an object, a boolean, or null yields null — not false and not a failure.
- `||` returns its left operand if that operand is a true value; otherwise it returns its right operand. `&&` returns its left operand if that operand is a false value; otherwise it returns its right operand. Both return operands, not booleans. Spaces around them are optional.
- `!` returns true for a false value and false for a true value. The numbers 0 and 0.0 are true values.
- Binding, from loosest to tightest: pipe, `||`, `&&`, comparators, `!`. `!` applies to the operand immediately after it together with any index, slice or list-wildcard brackets written directly after that operand (and the right-hand side of a projection those brackets start); a following dot step, filter, flatten or binary operator applies to the result of `!`. A negated path or comparison is written in parentheses. Parentheses group and override binding.
- The same operators apply inside a filter predicate (FP-04).

**Boundary / error behavior:**

- A lone `=` is a token-level syntax failure; equality is the two-character token `==`.
- A lone `&` that is neither `&&` nor followed by an expression, or a `||` or `&&` with a missing side, does not succeed.
- Ordering involving a boolean, an array, an object or null is null, not a failure.

---

### FP-07: Call built-in functions

**Public entry:** The search and compile entries of FP-01. A function call is an unquoted identifier followed by a parenthesized, comma-separated argument list. Arguments are expressions evaluated against the current value before the function runs; an `@` argument is the current value. Custom functions are FP-08. This feature point is the finite built-in set and the three function-call failure kinds.

The built-in function names are exactly: `abs`, `avg`, `ceil`, `contains`, `ends_with`, `floor`, `join`, `keys`, `length`, `map`, `max`, `max_by`, `merge`, `min`, `min_by`, `not_null`, `reverse`, `sort`, `sort_by`, `starts_with`, `sum`, `to_array`, `to_number`, `to_string`, `type`, `values`.

A call is checked before the function runs: first the name, then the argument count, then each argument's type. A name that is neither built-in nor supplied by an attached provider (FP-08) is the **unknown-function** kind. A wrong argument count is the **invalid-arity** kind. An argument outside its accepted types is the **invalid-type** kind. These three kinds are value errors, distinct from each other, from a successful null, and from the FP-01 kinds; a more specific form of one of them still counts as that kind. The check happens when the call is evaluated, so compiling a call with a wrong name, count or type succeeds and the search refuses. A function that has nothing to compute returns the result its definition states; that is not a failure.

**Normal behavior** (argument types in parentheses; "any" accepts every value; an argument that requires an "object" accepts a host ordinary mapping or a `collections.OrderedDict`; whether it accepts other mapping types is the implementer's choice; "array of numbers" requires every element to be a number; "array of numbers or array of strings" requires every element to be a number, or every element to be a string):

- `abs(number)` — the absolute value.
- `avg(array of numbers)` — the arithmetic mean; the empty array yields null.
- `ceil(number)` — the smallest integer not less than the argument, as an integer.
- `floor(number)` — the largest integer not greater than the argument, as an integer.
- `contains(array or string, any)` — for an array, whether the second argument is one of its elements; for a string, whether the second argument (a string) occurs in it.
- `ends_with(string, string)` / `starts_with(string, string)` — whether the first string ends / starts with the second.
- `length(string, array or object)` — the number of Unicode characters (not bytes) of a string, elements of an array, or keys of an object.
- `reverse(array or string)` — a new array, or string, in reverse order.
- `join(string, array of strings)` — the elements concatenated with the first argument between them; the empty array yields the empty string.
- `keys(object)` / `values(object)` — an array of the object's keys / values in the object's iteration order.
- `type(any)` — one of the strings `string`, `number`, `boolean`, `array`, `object`, `null`.
- `to_array(any)` — an array unchanged; any other value wrapped in a one-element array.
- `to_string(any)` — a string unchanged; any other JSON value as compact JSON text (no space after `,` or `:`, non-ASCII characters written as `\uXXXX` escapes, numbers written as the host writes them). A host value that is not a JSON type is converted with the host's ordinary text conversion, and that text is returned as a JSON string encoding (in double quotes).
- `to_number(any)` — a number unchanged; a string that is an integer numeral becomes that integer, otherwise a string that is a decimal or exponent numeral becomes that floating-point number; anything else (a non-numeric string, a boolean, null, an array, an object) yields null.
- `max(array of numbers or array of strings)` / `min(...)` — the greatest / least element; the empty array yields null.
- `sort(array of numbers or array of strings)` — a new array in ascending order (numbers numerically, strings by code point); the empty array yields the empty array.
- `sum(array of numbers)` — the sum; the empty array yields 0.
- `merge(object, object, …)` — one or more objects; a new host ordinary mapping with each argument's entries applied in order, so a later key overwrites an earlier one.
- `not_null(any, any, …)` — one or more arguments; the first that is not null, or null if all are null (an empty array or empty string is not null).
- `map(expression reference, array)` — the array of the referenced expression's results for each element, in order, **including** nulls (unlike a projection).
- `sort_by(array, expression reference)` — a new array ordered ascending by the referenced key. The key of every element must be a number, or of every element a string. The sort is stable: elements with equal keys keep their input order. The empty array yields the empty array.
- `max_by(array, expression reference)` / `min_by(array, expression reference)` — the element whose key (a number or a string, as for `sort_by`) is greatest / least, the first such element on ties; the empty array yields null.
- A function call may be the right-hand side of a projection (applied to each element, dropping nulls), and a projection may be a function argument.

**Boundary / error behavior:**

- Argument counts: `not_null` and `merge` take one or more arguments; every other built-in takes exactly the number of arguments listed above. Any other count is invalid-arity.
- Argument types: a value outside the types listed above is invalid-type. This includes a host decimal or boolean where a number is required, an array whose elements are not all of the required element type (mixed types where one element type is required), a non-reference where an expression reference is required, a non-array where an array is required (including null from a missing field), and a `sort_by` / `max_by` / `min_by` key that is not a number or string, or whose type differs between elements.
- A quoted identifier cannot be a function name: a quoted identifier followed by an argument list is a grammar-level syntax failure, not any function-call kind.

---

### FP-08: Evaluation options for constructed objects and custom functions

**Public entry:** The search entry and the parsed-expression search of FP-01, when the caller supplies evaluation options. Without options, constructed objects use the host’s ordinary mapping type and only the built-in functions of FP-07 are available. **This feature point refines FP-01 and FP-07:** the no-options path is unchanged; options add a mapping type and an extra function set.

**Normal behavior:**

- The caller may supply a mapping type. Every **multiselect hash** the evaluation constructs — at any nesting depth — is built as an instance of exactly that type, with its keys inserted in declaration order. Field selection, wildcards, filters, comparisons and truthiness treat such a hash as an object whatever the supplied type. When the supplied type is `collections.OrderedDict`, such a hash is also accepted wherever a function argument requires an object (FP-07); whether hashes of other supplied types are accepted there is the implementer's choice. Built-in functions that return a new object, including `merge`, still return the host’s ordinary mapping. Without a mapping type, constructed hashes are host ordinary mappings.
- The caller may supply a custom function provider. A custom function is a named language function with a declared argument count and declared accepted types per argument; it is called with its already-evaluated arguments, in order, after the count and type checks, and its return value is the call's value (whatever value it returns, including 0 or an empty container).
- A provider extends the built-in set; every FP-07 function remains available with unchanged behavior on a search that uses it.
- Options apply to the search they are attached to and to nothing else: a later search without options, with options lacking a provider or mapping type, or with a different provider, sees only what its own options supply. One options object may carry a mapping type and a provider together; both apply.
- The same options give the same results through the one-shot search and through compile-then-search. Compiling an expression that names a custom function succeeds without a provider.

**Boundary / error behavior:**

- A name that is neither built-in nor declared on the attached provider is the unknown-function kind (including a name declared only on some other provider).
- A custom function given a different number of arguments than it declares is the invalid-arity kind; an argument outside its declared types — including a host value that is not a JSON type — is the invalid-type kind. These are the same kinds the built-ins use.

