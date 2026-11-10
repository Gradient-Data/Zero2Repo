# Byte-pattern Search Product Requirements

This regular-expression engine supports patterns that combine intersection, complement and surrounding-text constraints.

### FP-01: Pattern matching and match selection

- Callers can search byte input with patterns composed of literal text, escaped literal characters, positive character classes, inclusive character ranges, concatenation, grouping, alternation and repetition. Concatenation requires consecutive matches of its operands; alternation accepts any operand. A positive character class accepts one member of its specified set of literals and inclusive ranges. Repetition supports zero or more, one or more, optional, exact-count, lower-bounded and inclusive bounded-count occurrences. Counts are nonnegative integers; a finite upper count must not be smaller than the lower count. An empty expression accepts an empty span. Grouping determines the extent of an operand; repetition binds more tightly than concatenation, and concatenation binds more tightly than alternation.

- An existence query reports whether the input contains a match. Collecting matches returns non-overlapping occurrences in increasing input position, choosing the earliest available start and the longest accepted span at that start. After a nonempty match, the next search begins at its end.

- Empty matches are retained. After an empty match, searching advances by one byte; the input-end position is considered once. An empty match at the end of a preceding nonempty match is retained when the pattern accepts it.

- For expressions without lookbehind, word-boundary or multiline line-start assertions, callers can request the longest match beginning at the start of the input, or ask whether a match covers the entire input. A successful search with no occurrence is distinct from a refused operation.

- Input may contain arbitrary bytes, including zero bytes and malformed UTF-8. Match positions and lengths are measured in bytes of the original input; searching does not replace or normalize the input.

- Unterminated groups or classes, reversed character ranges, missing repetition operands, invalid repetition bounds, malformed escapes, unknown Unicode properties and invalid flag syntax are refused as invalid patterns. Lazy repetition, backreferences and reversal of quantifier greediness are refused as unsupported pattern syntax. Pattern text supplied as bytes must be well-formed UTF-8; malformed text is refused with a diagnostic, without requiring its refusal to be distinguished from other compilation failures. Callers can retrieve the full diagnostic for a refused byte-pattern compilation without knowing its size in advance.

- By default, every explicitly written repetition bound must be at most 500. A syntactically valid larger bound is refused as an unsupported pattern. The size-limit override permits larger bounds, while preserving their repetition meaning.

- By default, patterns nested more than 1,000 group levels are refused as unsupported patterns. Nesting counts simultaneously enclosing pattern groups, not the number of groups next to each other. The size-limit override removes this nesting restriction.

- When a caller supplies space for only part of the collected match results, the product returns the total number of matches and delivers the longest prefix of complete results that fits. If another result remains, any leftover space too small to hold that complete result retains the caller's original contents.

- Reusing a pattern on new input produces results independent of earlier searches with that pattern.

### FP-02: Literal pattern escaping

- Callers can turn arbitrary literal text into a pattern fragment that matches that text literally under the default matching options, including characters that otherwise introduce pattern operators. The append form adds the escaped fragment after the caller's existing text without changing that prefix.

### FP-03: Character interpretation and matching options

- The four character-coverage modes are ASCII-only, limited Unicode, full Unicode and JavaScript-oriented, with limited Unicode selected initially. In ASCII-only and limited Unicode modes, the dot wildcard consumes one byte. In full Unicode and JavaScript-oriented modes, it consumes one Unicode scalar value on well-formed UTF-8 input. In every mode, the separate any-byte wildcard consumes exactly one byte, including a line feed.

- Standalone word, digit and whitespace shorthand atoms in ASCII-only and JavaScript-oriented modes use ASCII membership: word characters are Latin letters, decimal digits and underscore; digits are decimal digits; whitespace is space, tab, line feed, vertical tab, form feed and carriage return. In limited Unicode, digits and whitespace retain those memberships, while word membership uses the Unicode 16.0.0 word set restricted to scalar values from zero through 2047. That word set consists of the Alphabetic and Join_Control properties and the Mark, Decimal_Number and Connector_Punctuation general categories in the Unicode 16.0.0 character database.

- Full Unicode mode removes the limited Unicode word shorthand's scalar-value restriction. Its standalone digit and whitespace shorthand atoms use the Decimal_Number category and White_Space property, respectively, from the Unicode 16.0.0 character database. Membership is applied to the scalar values in the supplied UTF-8 text.

- On well-formed UTF-8 text, negated standalone shorthand atoms consume one scalar value outside the corresponding mode-specific positive shorthand set in every mode. Explicit negated character classes consume one excluded-set complement byte in ASCII-only mode and one excluded-set complement scalar value in the other modes.

- In limited Unicode, full Unicode and JavaScript-oriented modes, Unicode literals and explicit scalar-value ranges match the UTF-8 encodings of their scalar values as defined by Unicode 16.0.0. Named Unicode property classes select characters by the requested general category, script or binary property from the Unicode 16.0.0 character database, without the limited Unicode mode's word-shorthand range restriction. Negated properties select the complement among Unicode scalar values. The provided `regex-syntax` crate may be used as the source of this Unicode data: its tables are data, and depending on it for them is not a dependency on another regular-expression product.

- The special ASCII property matches a byte from zero through 127. The special hexadecimal-digit property matches an ASCII decimal digit or a Latin letter from A through F in either case. On well-formed UTF-8 text, the special UTF-8 property matches one complete Unicode scalar value.

- Matching is case-sensitive by default. Enabling case-insensitive matching makes literals and explicit character classes accept their simple case-fold equivalents: ASCII letter pairs in ASCII-only mode, and the Unicode 16.0.0 default simple case-fold equivalence classes of the supplied pattern characters in limited Unicode, full Unicode and JavaScript-oriented modes. For an explicit negated class, the excluded set is widened by these equivalents, so the class rejects every case-fold equivalent of its listed members.

- The dot wildcard excludes line feed by default. Enabling dot-all matching includes line feed.

- Pattern whitespace is significant by default. Extended mode ignores unescaped spacing and comments beginning with an unescaped number sign through the end of the pattern line; escaped spacing and escaped number signs remain literal.

- Callers can set case sensitivity, dot-all behavior, multiline behavior and extended mode globally. For patterns whose inline settings change only one of these options, callers can enable or disable that option from a position to the end of the enclosing group, or for a scoped group only. The inline setting takes precedence over the global setting for that option; leaving the group restores the enclosing setting.

- A positive character class may combine positive word, digit or whitespace shorthand atoms with literal members, ranges or other positive shorthand atoms; it accepts the union of their memberships. In ASCII-only and JavaScript-oriented modes, the shorthand members use their ASCII sets. In limited Unicode and full Unicode modes, these combined shorthand members use the full Unicode 16.0.0 word, decimal-number and whitespace sets, without the standalone limited Unicode restrictions. A class containing only one shorthand atom retains that atom's standalone membership.

- A positive character class consisting of a shorthand atom and its negation accepts any one byte in ASCII-only and limited Unicode modes, including line feed. In full Unicode and JavaScript-oriented modes, on well-formed UTF-8 input it accepts one complete scalar value, including line feed.

### FP-04: Boolean pattern constraints

- Intersection accepts a candidate span only when every operand accepts that same span. Callers can intersect more than two operands and combine intersection with concatenation, alternation and repetition. Concatenation binds more tightly than intersection, and intersection binds more tightly than alternation.

- Complement of a grouped expression without contextual assertions accepts precisely the byte strings that the operand does not accept. Its universe includes arbitrary byte strings. Complement can be nested and combined with intersection, alternation, concatenation and repetition.

### FP-05: Input anchors and word boundaries

- Input-start and input-end assertions require their positions to be at the corresponding boundary of the complete input and consume no bytes. An expression requiring consumption before an input-start assertion or after an input-end assertion cannot match any input; it may instead be refused as unsupported.

- Line-start and line-end assertions use multiline behavior by default: line start holds at input start or immediately after line feed, and line end holds at input end or immediately before line feed. With multiline behavior disabled, they require input start and input end respectively. These assertions consume no bytes.

- At scalar boundaries in well-formed UTF-8 text, a word-boundary assertion holds exactly when one adjacent character is a word character and the other is not; missing characters outside the input count as non-word. The non-word-boundary assertion requires the opposite condition. In ASCII-only mode, adjacency is measured in bytes. Word classification follows the selected mode's standalone word shorthand. These assertions consume no input and can constrain literal text and positive-count repetitions of atoms whose members are all word characters or all non-word characters in the selected mode.

- Applying finite counted repetition with a maximum count greater than one directly to a word-boundary or non-word-boundary assertion is refused as an unsupported pattern.

### FP-06: Surrounding-text constraints

- Positive lookahead requires an occurrence of its context expression beginning at the assertion position; negative lookahead requires that no such occurrence exist. Positive lookbehind requires a context occurrence ending at the assertion position; negative lookbehind requires that none exist. Context text is outside the consumed extent of the assertion. A failed context condition prevents that candidate from matching rather than making the input invalid.

- Callers can place non-nested lookbehind before a consuming expression and non-nested lookahead before or after it, including both constraints on the same expression. Context expressions can contain literals, character classes, alternation and fixed, bounded or unbounded repetition. Multiple surrounding constraints and intersection with an additional consuming expression retain all the asserted conditions on the selected span.

- Alternation supports branches with different leading bounded lookbehinds when the consuming branches have equal fixed byte length or disjoint possible first bytes. For branches with unequal fixed lengths whose possible first bytes overlap, distinct required literal lookbehinds are refused as an unsupported combination.

- A lookbehind placed after a mandatory consuming prefix is refused as an unsupported pattern.

### FP-07: Hardened matching growth

- The hardened-matching option is off by default. Callers can enable it for collection of whole-match spans. It retains the ordinary matching and selection semantics for literal, character-class, repetition, Boolean and supported surrounding-text expressions, including empty matches.

- For a fixed accepted pattern and fixed options in hardened mode, successful collection of whole-match spans must avoid quadratic growth with input length. On the same machine with enough memory for both input and results, growing an input by repeating the same fixed nonempty byte block from at least 20,000 bytes to ten times its length must take less than thirty times the median elapsed search time. The comparison uses repeated complete searches after pattern construction, holds the pattern and all product settings fixed, and includes workloads with densely occurring short matches and workloads with no matches.

- Existence queries satisfy the same input-growth bound with hardened mode either enabled or disabled; each measurement keeps that choice fixed.

### FP-08: Captured submatches

- The optional capture facility returns the whole match and the participating groups' byte spans for each collected occurrence. Named and explicitly unnamed capture groups are supported, including nested groups and groups separated by literal delimiters. When a group's extent is uniquely determined by the accepted whole-match decomposition, its span covers exactly that extent.

- Ordinary grouping does not capture by default. Enabling implicit captures makes ordinary groups capture without names; explicitly non-capturing groups remain non-capturing. Capture declarations retain their source order, and callers can discover declared names and retrieve a named group's span. Unknown names, out-of-range group requests and groups that did not participate return absence.

- A participating group that matches empty input reports an empty span, distinct from absence.

- For consecutive mandatory capture groups consisting of repetitions of the same character class, earlier groups receive the longest extent that permits the remaining groups to complete the selected whole match. In an alternation between a capture-free branch and a captured branch accepting exactly the same whole span, the captured branch participates regardless of branch order.

- A capturing group around a fixed-width nonempty consuming expression supports finite repetition with a positive maximum count; its reported span is the final participating repetition. Unbounded repetition of a nonempty capturing group, including repetition of an enclosing group containing it, is refused as unsupported capturing repetition. Captures beneath complement or inside lookaround are refused as unsupported captures.

- A pattern can declare up to 63 capturing groups, excluding the whole match. More declarations are refused as unsupported capture capacity. This limit counts named and unnamed captures together.

- When the caller supplies limited space for capture results, the longest prefix of complete per-match results that fits is delivered, while the total number of matched occurrences is still returned. If another occurrence remains, any leftover space too small for its complete capture result retains the caller's original contents.

- Capture names must be nonempty and unique within a pattern. Empty or duplicate names are refused as invalid patterns.

### FP-09: Multiple-pattern search and classification

- The optional multiple-pattern facility accepts an ordered collection of patterns under shared character-coverage, case, dot-all, multiline and extended-mode settings. Callers can ask whether any member matches and obtain every member that has a match anywhere in the input, once per member and in declaration order.

- Collecting occurrences from a pattern collection uses the union of its members. Classifying these occurrences attributes each selected span to the earliest declared member accepting that exact span, including its trailing context conditions.

- An empty pattern collection is accepted.

- Collection members can include input-start anchors, trailing line-end anchors, trailing word boundaries and trailing lookahead. Members with capturing groups or leading lookbehind, including leading word boundaries and multiline line-start anchors, are refused as unusable collection members, with the offending member's position identified. Malformed member patterns are refused as invalid patterns.

### FP-10: Saving and restoring reusable patterns

- With hardened matching disabled, the optional save-and-restore facility supports literal patterns, alternations of nonempty literals, repetitions of a single character class, and sequences of literals and fixed-count character classes. This support excludes standalone fixed-count repetitions of a single-character expression. Restoring successfully saved data makes the pattern reusable for collection of matches on new inputs, preserving its match spans and its selected character and case behavior without requiring the original pattern text.

- Saving and restoring a sequence of literals and fixed-count character classes with capturing groups preserves the groups' names and byte spans when their boundaries are fixed relative to the whole match. Saving two variable-length capture groups separated by a literal delimiter is refused when their interior boundaries are not fixed relative to either end of the whole match.

- Saving a pattern collection's combined matcher is refused as unsupported for saving. Loading empty data, or data truncated before all required saved information is present, is refused as invalid saved data.
