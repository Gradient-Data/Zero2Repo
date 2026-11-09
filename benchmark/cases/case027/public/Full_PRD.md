# trisift — Full Product Requirements Document

## Product overview

**trisift** is a trigram-indexed grep with a client/server architecture for fast regex search in large codebases. Its command line follows ripgrep: the common ripgrep search options exist with the same meaning, and the exit-status convention is ripgrep's. Where trisift deliberately differs from ripgrep (a default file-size cap, skipping known binary extensions, searching decoded text instead of raw bytes), this document says so.

A search can be answered in three ways, and the caller uses the same command for all of them:

1. **Server.** A long-running server process for the tree keeps an index warm and refreshes it as the filesystem changes. Searches find it automatically and query it over loopback TCP.
2. **On-disk index.** An index build (or a server's saved index) is read directly when no server is reachable. It is a snapshot as of its last build.
3. **Filesystem scan.** With no usable index, or when the caller asks for it, every eligible file is read from disk.

Whichever way answers, a search over the same files with the same options returns the same results. The index only narrows which files are read. It never decides what matches.

This document describes behavior a user or integrator can observe. The exact spelling of options, subcommands, output fields, exit-status values and message text belongs to the Interface Contract.

## Terminology

- **Search root**: a path argument to a search. It is either a directory, which is walked, or a file the user named explicitly.
- **Index directory**: where an index is stored. Its default location is directly inside the indexed root, at the name stated in the Interface Contract. A custom-index-path option on every subcommand selects another location. The index directory, including any staging or retired generations inside it, is never indexed and is never walked by a query scan, even when it lies inside the source tree.
- **Admitted file**: a file that survives traversal rules: ignore rules, hidden-file visibility, the file-size cap and, for content searches, the binary-extension list.
- **Binary file**: a file whose decoded content contains a NUL byte.
- **Index coverage**: whether an on-disk index is complete, in the current format, and records hidden-file visibility. Only an index with full coverage answers queries. Anything else makes the query scan. FP-07.11 states the rule that decides which index directories lack full coverage.
- **Discovery record**: a discovery file that a running server writes into its index directory. It holds the server's process id and loopback TCP port. Clients use it to find the server.
- **Server lock**: an exclusive lock in the index directory. A server holds it exclusively for as long as it runs.

## Statuses and streams

- A search ends with one of three distinguishable exit statuses, following ripgrep's convention: **match** (at least one match), **no match**, and **error**. If a match is found and an error is also reported, the status is error, unless quiet mode is on, in which case it is match.
- A command-line usage problem (unknown option, malformed value, conflicting options) ends with the error status, prints nothing on standard output, and explains the problem on standard error.

## Non-goals

- Searching inside compressed archives. The search-zip option is refused (FP-01). trisift does not quietly report no matches for it.
- Matching raw bytes. Content is always decoded to text before matching (FP-05).
- Full PCRE2 syntax. The backtracking engine is a PCRE-style engine, not the PCRE2 library (FP-02).
- Configurable colors or a configuration file. The options for them are accepted and ignored (FP-01).
- The agent-integration installer, benchmarks, fuzzing, packaging and release tooling. These are developer tooling, not product surface.

---

## Feature points

### FP-01: Regex search over files and directories

**Scope:** Searching with a pattern and zero or more paths, through either equivalent search entry. Content searches in this feature point are answered by a filesystem scan; FP-07 adds indexed answering under the same rules.

**Normal behavior:**

- trisift searches every admitted file under each directory argument, plus every file named explicitly. It prints each matching line, and the exit status is match. When nothing matches, nothing is printed and the exit status is no match. With no path argument, the current directory is searched.
- Several path arguments may be given in one invocation. Results cover all of them.
- Pattern and paths are split the way ripgrep splits them. Without an explicit-pattern or pattern-file option, the first positional argument is the pattern and the rest are paths. Once a pattern comes from an explicit-pattern option or a pattern file, every positional argument is a path.
- A double-dash argument ends option parsing. Everything after it is read as pattern and paths. A pattern that starts with a dash, or that spells a command name, is searched for as text when it follows the double dash.
- A path argument wrapped in matching single or double quotes is searched as the unquoted path. Leading and trailing whitespace around a path argument, and around the text inside each quote pair, is removed, and the unwrapping repeats while the remaining text is still wrapped in matching quotes.
- Quiet mode prints nothing on standard output. Its exit status is match as soon as any file matches, even if an error is reported for another path argument. Otherwise it is no match or error, as for a normal search.
- The pcre2-version option prints a line naming the backtracking engine in use, which is fancy-regex, and saying that PCRE2 is not linked. It then exits successfully without searching.
- These ripgrep options are accepted and have no effect on results, so ripgrep command lines keep working: mmap / no-mmap, crlf / no-crlf, no-config, colors, and threads. A trailing carriage return is always stripped from a line before matching and printing. The debug and trace options turn on the statistics report of FP-07.

**Boundary / error behavior:**

- A path argument that does not exist is reported on standard error, and the report names the path. The remaining path arguments are still searched and their results printed. The exit status is error unless quiet mode applies (FP-01.06). The no-messages option suppresses the report but not the error status.
- A search invocation with no pattern, no explicit-pattern or pattern-file option, and no file-listing or type-listing request prints usage on standard error and exits with the error status.
- The search-zip option is refused with the error status and an explanation on standard error. Nothing is searched.
- A pattern the selected regex engine cannot compile ends the search with the error status and a regex error on standard error.

### FP-02: Pattern matching controls

**Scope:** Matching options on any search invocation.

**Normal behavior:**

- **Case.** Case-sensitive matching is the default. The ignore-case option makes matching case-insensitive. The smart-case option makes matching case-insensitive only when the positional pattern contains no uppercase character. When patterns come only from explicit-pattern or pattern-file options, smart case is case-insensitive even if those patterns contain uppercase characters. The case-sensitive option overrides smart case. Ignore-case still wins over case-sensitive when both are given.
- **Inline flags.** Inline case flags inside the pattern, both whole-pattern and group-scoped, behave exactly as the regex engine defines them. They give the same results whether the search is answered by a scan, the local index, or the server.
- **Fixed strings.** The fixed-strings option matches every pattern literally, so regex metacharacters match only themselves.
- **Word and line.** The word-regexp option requires each match to be bounded by word boundaries. The line-regexp option requires the pattern to match a whole line. When both are given, line-regexp wins.
- **Invert.** The invert-match option selects the lines that do not match.
- **Multiple patterns.** The explicit-pattern option can be repeated, and the pattern-file option reads one pattern per non-empty line, trimmed. A line is selected when any of the patterns matches it. Patterns from a pattern file are honored on every answering path, including the server. When a supplied pattern file contributes no non-empty patterns and no other pattern is supplied, every line is selected.
- **Multiline.** Without the multiline option, a match never crosses a line boundary, and the start and end anchors apply to each line. With the multiline option, a match may span lines, and every line the match covers is printed. A dot still does not match a newline unless the multiline-dotall option is given. Multiline-dotall implies multiline.
- **Engines.** The standard regex engine accepts the pattern syntax of ripgrep's default regex engine, with that engine's meaning for every construct, including character classes and inline flags. The backtracking engine accepts that syntax extended with lookaround and backreferences. The engine option takes one of exactly three values: `auto` (the default), `default`, and `pcre2`. `default` uses the standard regex engine only, which rejects lookaround and backreferences. `pcre2`, and the pcre2 option, use the PCRE-style backtracking engine, which supports lookaround and backreferences. `auto` uses the standard engine and falls back to the backtracking engine for patterns that need it. Lookaround and backreference patterns give the same matches through the index and the server as through a scan.
- **No-unicode.** The no-unicode option turns off Unicode-aware character classes.
- **Replace.** The replace option prints each match replaced by the given text. Capture groups expand by number and by name. Combined with only-matching, only the replacement texts are printed. The files are never modified.

**Boundary / error behavior:**

- An engine value outside the three listed is rejected with the error status.
- The regex-size-limit and DFA-size-limit options take a byte size with an optional K, M or G suffix (powers of 1024, either case). A malformed size value, or one too large for the platform, is rejected with the error status, and the message names the option it came from.
  - **Regex size limit.** The limit applies to patterns compiled by the standard engine, that is under engine `auto` or `default` for patterns without lookaround or backreferences. With a limit of 1 byte, every such pattern that contains an unbounded repetition operator (star, plus, or a counted repetition with no upper bound) fails, whatever other matching options are given: the search ends with the error status, a size-limit error on standard error, and no results. This holds on every answering path. Under `auto` this failure is final, and trisift does not retry the pattern on the backtracking engine. Under fixed-strings these characters are literal, so they are not repetition operators. Any limit of at least 1 GiB that the platform accepts admits every pattern that compiles without the option. Where the cut-off lies between those two points, and whether patterns without an unbounded repetition fit a small limit, is the implementer's choice. Patterns compiled by the backtracking engine (engine `pcre2`, or `auto` falling back for lookaround or backreferences) are not subject to the limit.
  - **DFA size limit.** Any accepted DFA-size-limit value leaves the printed results and exit status unchanged from the same search without it.

### FP-03: Result output and formatting

**Scope:** Output-mode and formatting options on any search invocation.

**Normal behavior:**

- **Terminal-dependent defaults** follow ripgrep. Line numbers are shown only when standard output is a terminal. The line-number, column, vimgrep and pretty options turn them on in any case. The byte-offset and context options do not. The no-line-number option turns them off. Matches are grouped under a per-file heading only when standard output is a terminal, unless the heading or no-heading option forces the choice. Color follows the color option: `auto` colors only on a terminal, `always` colors, `never` does not. `always` highlights each matched span. The pretty option means color always, plus heading, plus line numbers.
- **Filenames** are shown on every result line, except when exactly one path argument was given and it is a file. A directory argument always shows filenames. The with-filename and no-filename options override this, and when both are given, no-filename wins.
- **Printed paths** are built by appending to the path argument exactly as typed. The typed text is kept verbatim. When it lacks a trailing separator, the platform separator is added, and the remainder of the path uses the platform separator. A file named explicitly prints exactly as typed. With no path argument, paths print relative to the current directory with no prefix. The path-separator option replaces every separator in printed paths.
- **Listing modes.** The files-with-matches option prints each matching file once. The files-without-match option prints each searched file that has no match. In this mode the exit status is match when at least one such file is printed and no match otherwise. The null option selects the alternative filename terminator stated in the Interface Contract.
- **Counts.** The count option prints, per matching file, the number of matching lines. The count-matches option prints the number of individual matches. The include-zero option adds files with a count of zero. Without a filename prefix (FP-03.02), only the number is printed.
- **Match limit.** The max-count option limits the number of matching lines per file. Every match on an admitted line is still reported. In multiline mode, the unit is a block formed by matches sharing or overlapping source lines. Matches on adjacent but separate lines consume separate units. A match spanning lines is never cut short. A limit of zero reports nothing and the exit status is no match.
- **Only-matching** prints each match on its own output line instead of the whole line.
- **Context.** The after-context, before-context and context options print that many non-matching lines around each match. Context lines are marked apart from matching lines by a different field separator. A separator line is printed between groups that are not contiguous, and between files in flat output. No separator is printed when no context was requested. The context-separator option replaces the separator text, and the no-context-separator option suppresses it. The field-match-separator and field-context-separator options replace the separators between the path, line, column and offset fields.
- **Positions.** The column option prefixes each matching line with the 1-based byte column of its first match. Context lines get no column. The no-column option turns the column off, and between column and no-column the later one wins. The byte-offset option prefixes each line with the 0-based byte offset of that line in the file, or of the match itself under only-matching.
- **Long lines.** The max-columns option replaces any line longer than the given number of bytes with a placeholder. The length counts the line's terminator: one byte for a newline, two for a carriage-return newline, none for an unterminated final line. Matching and context placeholders are distinguishable. The max-columns-preview option prints the first part of the line followed by an omission marker instead.
- **Trim** removes leading and trailing Unicode whitespace from printed lines.
- **Passthru** prints every line of each searched text file, matching or not. The exit status still reflects whether anything matched. Passthru prints nothing for binary files that do not match, and nothing at all when the max-count is zero.
- **Stop-on-nonmatch** stops reading a file at the first non-matching line after a match.
- **Vimgrep** prints one row per match: path, line number, 1-based byte column, and line content. A line with several matches gives several rows. In multiline mode, each match gives one row, on its starting line. The path is always shown.
- **Structured output** reports files, selected lines, matching spans and statistics. Each file that produces output has its selected lines, matching spans and per-file statistics reported. An invocation has exactly one overall summary, covering every path searched. Line information includes source positions and matching spans within the reported text; the Interface Contract states their record forms. Per-file output-byte statistics count the serialized begin, match and context records, including their line terminators; invocation output-byte statistics also include end records and exclude the summary record itself. Under JSON, only-matching has no effect. JSON is not produced at all, not even a summary, when a count, count-matches, files-with-matches, files-without-match or file-listing option is also given. Instead the plain output of that mode is printed.
- **Sorting.** The sort and sortr options take one of exactly five keys: `path`, `modified`, `accessed`, `created`, `none`. Within each path argument, results are ordered by file in ascending or descending order of that key. When several path arguments are given, their result groups follow argument order; sorting does not reorder or interleave those groups. With no path argument, the current directory forms one group. `none` leaves the file order within each group unspecified. The sort-files option means sort by path. Results come out in the same order whether answered by a scan, the local index, or the server.
- **Buffering.** The line-buffered option flushes output after every line, making each completed result line available to a pipe reader without waiting for later lines or process termination. The block-buffered option is accepted and does not change what is printed. When both are given, the later one decides, and naming both is not an error. Without line-buffered, how output is grouped into writes, and in what block size, is the implementer's choice.

**Boundary / error behavior:**

- A sort key outside the five listed is rejected with the error status.
- A color value other than `auto`, `always` or `never` falls back to `auto`.

### FP-04: File selection — ignore rules, hidden files, globs, types, depth and size

**Scope:** File-selection options on any search invocation. The same traversal rules govern admission during index builds and server operation (FP-06, FP-09), and govern file listings (FP-08).

**Normal behavior:**

- **Ignore sources.** These ignore sources are honored, using gitignore syntax and precedence:
  - `.gitignore` files, only inside a Git repository (a `.git` entry in the root or any ancestor) unless the no-require-git option is given;
  - `.ignore` files, everywhere, taking precedence over `.gitignore`;
  - the repository's info/exclude file;
  - the global gitignore;
  - ignore files in parent directories of the search root;
  - a `p4ignore.ini` file in the root, whose rules may use either slash or backslash as the separator;
  - any ignore-file options, where later files take precedence.

  The ignore-file-case-insensitive option makes rules in automatically discovered ignore files case-insensitive. It does not change rules from explicitly supplied ignore files.
- **Disabling ignore sources.** The no-ignore option disables automatically discovered ignore sources, while explicitly supplied ignore files still apply. These options each disable a single source: no-ignore-dot (all discovered `.ignore` files, including those in parent directories), no-ignore-vcs (`.gitignore`), no-ignore-exclude (info/exclude), no-ignore-global, no-ignore-parent (all ignore files from ancestors of the search root), and no-ignore-files (ignore-file options).
- **Case-insensitive Git repositories.** When the repository's Git configuration enables core.ignorecase, the rules of the root `.gitignore` and of info/exclude also exclude paths that match them regardless of case. Paths Git tracks in its index are exempt from this extra exclusion. Nested `.gitignore` files and global rules get no case-insensitive pass. The no-ignore option disables the pass.
- **Hidden files.** A file or directory is hidden when its name starts with a dot, or when it carries the Windows hidden attribute. Searches skip hidden files and everything under hidden directories unless the hidden option is given. Hiddenness is judged relative to the search root, so a hidden directory named as the search root exposes its non-hidden children. The hidden option never disables ignore rules. A file named explicitly is searched even when it is hidden.
- **Unrestricted.** The unrestricted option is cumulative: given once it means no-ignore, twice it adds hidden, three times it also adds the binary option of FP-05.
- **Globs.** The glob option, which can be repeated, admits only paths matching any positive glob and excludes paths matching a glob prefixed with `!`. Globs match the path relative to the search root and are case-sensitive. The iglob option, and the glob-case-insensitive option applied to all globs, make them case-insensitive. A negative glob that matches a directory excludes that directory's whole subtree.
- **Types.** The type option admits only files of the named types, and repeated uses combine. The type-not option excludes the named types and takes precedence over type. A type's globs match the file name only. Type and path-glob restrictions both apply when combined. The built-in type table includes at least these types: rust for `*.rs` files, py and its alias python for `*.py` files, js for `*.js` files, c for `*.c` and `*.h` files, and cpp for `*.cpp` and `*.h` files. Among the extensions `.rs`, `.py`, `.js`, `.c`, `.cpp`, `.h` and `.txt`, each of these types selects exactly the ones listed for it. Further built-in types and their globs are the implementer's choice. The type-add option adds a glob to a type, creating the type if needed. The type-clear option removes a type's definitions before any additions are applied, regardless of their relative positions. Additions are applied in their given order. An inclusion copies the named types' definitions as they stand after all clears and earlier additions.
- **Type list.** The type-list option prints every defined type with its globs, one type per line, ordered by name. The listing reflects type-add and type-clear. It exits successfully without searching.
- **Depth.** The max-depth option limits recursion. A depth of 1 admits only files directly inside the search root. Each further level admits one more directory level.
- **File size.** Files reached by walking a directory are skipped when they are larger than 64 MiB (67,108,864 bytes). This is a deliberate difference from ripgrep. The max-filesize option sets another limit, as a byte count with an optional K, M or G suffix (powers of 1024). A file whose size exceeds the limit is skipped, and a file exactly at the limit is searched. The no-max-filesize option removes the limit. When both options are given, the later one wins. A file named explicitly is searched whatever its size under the inherited 64 MiB default, but an explicitly given max-filesize still applies to it.
- **Symlinks and filesystems.** The follow option follows symbolic links during a scan. The one-file-system option keeps a scan from crossing filesystem boundaries.

**Boundary / error behavior:**

- An unknown type name in type or type-not ends the search with the error status. So does a malformed type-add value: missing name or definition, or an include list naming an unknown type or naming none.
- A malformed max-filesize value is rejected with the error status. trisift never silently searches with a different limit.
- **Malformed ignore rules.** Ignore globs support Git ignore syntax extended with brace alternation. Bracket ranges require ascending code-point order, brace alternations outside bracket expressions require balanced opening and closing braces, and an escape must have a following character. Negation leaves these syntax rules unchanged. An unclosed bracket is accepted as literal text. Blank lines and comments contain no rule to validate. Each malformed rule is reported on standard error, naming the ignore file and the line number. That rule is skipped, every other rule in the same file still applies, the search carries on, and the exit status is decided by the search alone. This applies to ignore-file options and to ignore files found during the walk. The no-ignore-messages option suppresses the report, and so does the no-messages option.

### FP-05: Binary files and text encoding

**Scope:** Binary-handling options (text, binary) and encoding options (encoding, no-encoding) on any search invocation.

**Normal behavior:**

- **Binary files reached by walking** are skipped silently. A binary file is one whose decoded content contains a NUL byte anywhere. A skipped binary file appears in none of the outputs: matches, files-with-matches, counts, files-without-match.
- **A binary file named explicitly** that matches is summarized by a single note line instead of its lines. The note gives the byte offset, within the file, of the first NUL byte, and is prefixed by the path when filenames are shown. Files-with-matches lists it. The count options print its real count, which includes matches on both sides of the NUL.
- **The binary option** makes binary files reached by walking behave as if they were named explicitly. **The text option** turns off binary detection completely, takes precedence over the binary option, and searches and prints binary files as text.
- **Under JSON output**, a matching binary file that is shown (named explicitly or under the binary option) produces ordinary match messages and no note. Its end message carries the byte offset of the first NUL, and its bytes-searched statistic stops at that offset. For a text file, or under the text option, the binary offset is null. A binary file reached by walking without the binary option produces no JSON messages.
- **Known binary extensions.** During content searches over a directory, trisift skips files with the following extensions, compared case-insensitively, without reading them: png, jpg, jpeg, gif, bmp, ico, webp, tiff, tif, psd, mp3, mp4, avi, mkv, mov, wav, flac, ogg, wma, aac, m4a, webm, zip, tar, gz, bz2, xz, zst, 7z, rar, lz4, lzma, cab, exe, dll, so, dylib, obj, o, a, lib, pdb, wasm, class, jar, pyc, pyo, beam, pdf, doc, docx, xls, xlsx, ppt, pptx, ttf, otf, woff, woff2, eot, bin, dat, db, sqlite, sqlite3. Indexing skips them too (FP-06). Files with any other extension are classified by their content. The binary and text options lift the extension skip for searches. A file named explicitly is never skipped by extension.
- **Default decoding (`auto`).** A UTF-8, UTF-16LE or UTF-16BE byte-order mark selects that decoding, and the mark itself is not part of the searched text. A file without a mark is treated as UTF-8.
- **Named encodings.** The encoding option trims surrounding whitespace and takes an empty label as automatic decoding. It also takes `auto`, `none`, or any label defined by the WHATWG Encoding Standard. A label decodes files without a byte-order mark in that encoding, and a byte-order mark still overrides the label. `none` disables byte-order-mark sniffing and transcoding. The no-encoding option restores `auto`. Between encoding and no-encoding, the later one wins.
- **Invalid UTF-8** is repaired: each invalid sequence is searched as U+FFFD, and a pattern can match those replacement characters. This applies under `none` too. For repaired UTF-8, the columns, byte offsets and binary offsets in text output are positions in the original file bytes. JSON line text carries the replacement characters, and JSON submatch offsets index that text. For transcoded encodings, offsets are positions in the decoded text and exclude the byte-order mark.

**Boundary / error behavior:**

- A nonempty trimmed encoding label that is not `auto`, `none`, or a WHATWG label is rejected with the error status.
- Any encoding other than `auto`, and the text and binary options, always give the same results as a filesystem scan, whether or not an index or server is available (FP-07).

### FP-06: Building the on-disk index

**Scope:** Building an index. The root defaults to the current directory. Controls: custom index path, exclude (repeatable directory name), no-ignore (and unrestricted), no-require-git, max-filesize / no-max-filesize, hidden (accepted, redundant), force (accepted), index strategy, and index buffer size.

**Normal behavior:**

- A build walks the root under the traversal rules of FP-04 and indexes every admitted text file, then publishes a complete index into the index directory. It reports success on standard error, naming the index directory. It also reports the elapsed time and the strategy used. On Linux, macOS and Windows the report also gives the build's peak memory. On other platforms, whether it does is the implementer's choice. The exit status is success.
- **What is indexed.** Hidden files and directories that are not ignored are always indexed, so the hidden option is redundant here. Ignored files, binary files (by extension or by content), and files over the size limit are not indexed. One exception is left open: whether a file whose first NUL byte lies beyond the first 8 KiB of its decoded content is counted among the indexed files is the implementer's choice, and searches treat such a file as binary either way (FP-05). Every `.git` directory subtree is excluded by default, including those of nested repositories, even with the hidden option. The no-ignore option includes them, along with ignored files. Each exclude option skips every directory with that name at any depth.
- **Size limit.** The build uses the same file-size limit as a search: the 64 MiB default, or the max-filesize / no-max-filesize setting. A file excluded by the build's limit is absent from the index and from its filename listing.
- **Ignore files outside Git.** When the root is not inside a Git repository, has a root `.gitignore`, and neither no-ignore nor no-require-git is given, the build prints a warning on standard error identifying the root and saying that the `.gitignore` is not applied. Under no-require-git the `.gitignore` rules are applied, and the files they ignore are not indexed.
- **Strategies.** The index-strategy option takes exactly two values: `external` (the default) and `memory`. The success report names the strategy that ran. Both strategies produce indexes that answer every query identically. The index-buffer option sets the external strategy's buffer in MiB, with a default of 64 MiB. Under `external`, an explicitly given index-buffer is confirmed on standard error with the buffer size in MiB. Under `memory` the option is accepted and ignored, and no such confirmation is printed. A build without the option prints no confirmation either. How each strategy uses memory and temporary disk space, and how peak memory changes with the buffer, is the implementer's choice.
- **Rebuild.** Running the build again over an existing index replaces it with one that reflects the tree at that moment.
- **Persistence.** A publication contains the searchable index, admitted paths without searchable content and their visibility, index metadata, and indexed files' byte sizes and modification times recorded to whole seconds. Metadata records the format version, counts, creation and update times, root and coverage. A running server additionally publishes its discovery record and holds the exclusive lock. The Interface Contract names these artifacts and states their forms. An index without its lookup artifact counts as absent.

**Boundary / error behavior:**

- These traversal options are refused with the error status and a message naming them, and no index is built: follow, max-depth, one-file-system, ignore-file, ignore-file-case-insensitive, no-ignore-dot, no-ignore-exclude, no-ignore-files, no-ignore-global, no-ignore-parent, no-ignore-vcs.
- An index directory that contains the source root is refused with the error status.
- The index-buffer option rejects zero, non-numeric values, and values too large for the platform, with the error status. An index-strategy value outside the two listed is rejected with the error status.

### FP-07: Indexed search and automatic fallback

**Scope:** Any content search (FP-01–FP-05) when an index or server exists for the searched tree. This refines FP-01: the same results, answered through the index. Options: custom index path, no-index, stats (and debug / trace).

**Normal behavior:**

- **Order of preference.** A search uses a running server when the index directory has a reachable server with full coverage. A search using passthru, files-without-match or include-zero may instead use an on-disk index with full coverage. Otherwise it uses the on-disk index when it has full coverage. Otherwise it scans the filesystem. The default index location is the one defined in the terminology. Under the custom index-path option, that directory is used instead.
- **Same results everywhere.** For any combination of FP-02–FP-05 options that keeps the index in use, the printed output and exit status of an indexed search equal those of a filesystem scan over the files the index contains. This includes match lines, counts, context, JSON, vimgrep, sort order, binary notes and passthru. In server-answered JSON, line absolute byte offsets and searched-byte statistics are zero; the scan and local-index paths report their actual values. Timing and output-byte totals may differ across runs. Invocation statistics count only files actually searched, so indexed searches may report fewer searched files and bytes than scans.
- **Subtrees.** A search root that is a subdirectory of the indexed root is answered from the index, restricted to that subtree. Paths print as FP-03 specifies for that argument. A search root outside the indexed root is answered by a scan of that root, and never with results from the unrelated index.
- **Filters on the index.** Globs (positive and negative, iglob), types, hidden, max-depth and sort filter the indexed corpus without leaving the index. A positive glob never brings back a file the index excludes as ignored. With no-index, or under a scan, positive globs keep ripgrep's override behavior and can bring back ignored files. The hidden option shows indexed hidden files under the same ignore rules.
- **Options that force a scan.** These always make a search scan, even when a server is running: no-index; no-ignore and its single-source variants (no-ignore-dot, no-ignore-vcs, no-ignore-exclude, no-ignore-global, no-ignore-parent) and unrestricted; text; binary; any encoding other than `auto`; and naming a single file as the search root. A scan reads current file contents and applies every traversal option.
- **Options an indexed search ignores.** In an indexed content search, follow, one-file-system, ignore-file and ignore-file-case-insensitive have no effect. Combined with no-index, they apply.
- **Snapshot freshness.** Without a server, an indexed search reflects the last published index. A file created after that is not reported until the index is rebuilt or a server refreshes it, while a scan with no-index does report it.
- **Narrowing.** For literal patterns at least three bytes long, including alternatives of such literals, an indexed file is a raw candidate only if it contains every three-byte sequence of at least one alternative. ASCII letter case may be ignored for this bound even in a case-sensitive search; the final matches still obey the requested case rules. Case-insensitive patterns whose letters have non-ASCII case equivalents, and more complex patterns, may retain additional candidates, up to the whole index. A file containing a match is always a raw candidate.
- **Stats.** With the stats option, a report on standard error, after the matches when both streams are combined, shows:
  - which path answered: server, local index, or filesystem scan;
  - the total number of matches and of matched lines;
  - for indexed answers, three counts: raw candidates (before path, visibility, glob and type filters), candidates (after those filters but before size checks, reads and matching), and the number of indexed files;
  - a no-narrowing marker, exactly when the nonempty index's raw candidates are all of its files.

  An indexed answer's report may also describe the query plan. Whether it does, and what that description says, is the implementer's choice. Without the stats option, an indexed search writes nothing to standard error.

**Boundary / error behavior:**

- **No index.** When no index exists at the index directory, the search scans. It prints a warning on standard error naming that directory and suggesting how to build or point at an index. Quiet mode suppresses the warning. The results are those of the scan.
- **Incomplete coverage.** An index directory that holds an index (its lookup artifact is present, see FP-06.07) lacks full coverage when any of the following holds:
  - the index metadata is missing, or cannot be read or parsed;
  - the supplemental filename and coverage artifact is missing, or cannot be read, or is not in the form trisift writes, because it does not represent a complete valid artifact;
  - the index metadata or the supplemental filename and coverage artifact comes from a build whose set of indexed paths differs from that of the index's other files, regardless of whether the mismatched artifacts have the same file count;
  - the index was published by a server that stopped before its initial build finished (FP-09.02);
  - the index build that published it could not read a file or directory it would otherwise have admitted.

  An index lacking full coverage is not used. The search scans, prints a warning on standard error unless quiet or no-messages is set, and returns the scan's results with the scan's exit status. An index whose files have not been altered since it was published has full coverage when either an index build read everything it admitted, or a server published it after its status reported indexing complete and coverage complete.
- **Server not usable.** A discovery record whose server is unreachable, or a server that is still building or lacks full coverage, makes the client print a fallback notice on standard error. The client then answers from the local index or a scan. The results are never partial.

### FP-08: File listing and file counting

**Scope:** Listing eligible paths and counting eligible files.

**Normal behavior:**

- **Listing.** The file-listing option prints, one per line, every path a search would admit under FP-04's traversal rules, with no content checks. Binary files are included, including files with the binary extensions of FP-05. Globs, types, hidden, max-depth, sort, null and path-separator apply. Positional arguments are all paths, and paths print as in FP-03. A completed listing is successful even when no paths are admitted; the content-search no-match outcome does not apply to file listings.
- **Single file.** A path argument that is a file lists that file when it passes the glob and type filters, printed as typed.
- **Indexed listing.** With default traversal rules, the listing comes from the running server or the on-disk index. It includes indexed paths that have no searchable content, such as binary files. Without a server it is a snapshot as of the last build, so files created afterwards are absent until rebuilt, while the no-index option lists the filesystem as it is now. These options make the listing walk the filesystem instead: no-index, no-ignore, no-ignore-dot, no-ignore-vcs, no-ignore-exclude, no-ignore-global, no-ignore-parent, unrestricted, no-require-git, follow, one-file-system, ignore-file, ignore-file-case-insensitive, and an explicit max-filesize or no-max-filesize. Disabling explicitly supplied ignore files alone does not force a walk. With the stats option, standard error names which path answered: server, local index, or filesystem walk.
- **JSON.** The JSON option has no effect on a listing.
- **Counting.** The file-counting operation walks the root under the ignore rules, hidden-file visibility (hidden files only with the hidden option; no-ignore and unrestricted lift the ignore rules), the binary-extension list, and the 64 MiB default size limit. It does not read file contents, so a file with a NUL byte but no binary extension is counted. It prints the number of admitted files on standard output. On standard error it prints that number together with the number skipped by binary extension, the number skipped as too large, the number of errors, and the elapsed time. The exit status is success.
  - Symbolic links are neither counted nor errors, whether or not their target exists.
  - The error count is the number of directories the walk reaches but cannot list. The root itself counts when it cannot be listed. Such a directory's contents are not counted.
  - A directory the walk does not enter adds no error. This covers a directory excluded by the ignore rules, and a hidden one without the hidden option.
  - A regular file the user cannot read is still counted and is not an error, because contents are not read.
  - Errors do not change the exit status.

**Boundary / error behavior:**

- A listing path argument that does not exist is reported on standard error, naming the path. The other arguments are still listed, and the listing ends with success.
- The file-counting operation on a root that does not exist ends with the error status.

### FP-09: Search server with automatic refresh

**Scope:** Running a search server. The root defaults to the current directory. The server runs in the foreground until interrupted. Options:
- custom index path, exclude, no-ignore, no-require-git, max-filesize / no-max-filesize, and hidden (accepted, redundant);
- watch-mode, poll-interval, watch-budget, no-watch;
- max-memory, max-cpu, auto-save-mutations, watcher-queue-cap.

Clients reach the server through the search, listing and status commands (FP-07, FP-08, FP-10), or directly over its loopback protocol.

**Normal behavior:**

- **Startup.** On startup the server takes the server lock and writes the discovery record with its process id and a loopback TCP port. It then accepts connections. Searches from FP-07 find it with no extra option, as long as they use the same index directory.
- **Building in the background.** If the index directory holds no index, holds an incomplete one, or holds one that fails to load, the server builds a complete index in the background. While that build runs, clients fall back as FP-07.12 describes, and their results are still complete. Once the build finishes, searches are answered by the server and find every admitted file. The index the server builds has the same content rules as FP-06, including hidden files, `.git` exclusion, exclude, no-ignore, no-require-git and the size limit. Its memory and CPU settings (max-memory in MiB, at least 1; max-cpu as a percentage of logical cores, with at least one worker) change only resource use, never the resulting index. Any accepted value still produces a complete, fully searchable index. Their defaults and their effect on resource use are the implementer's choice.
- **Startup reconciliation.** When the server starts on an existing index, it reconciles that index with the tree. Files added, changed or deleted while no server was running are reflected. Indexed files that the server's own settings exclude (ignore rules, exclude, size limit) are removed. When the existing index lacks full coverage under FP-07.11's rule, the server brings it to full coverage. Once status reports indexing complete and coverage complete (FP-10.01), searches are answered by the server. After the server stops, searches without a server answer from the saved index rather than scanning.
- **Protocol.** The server offers four operations over its loopback protocol:
  - search, which takes the same matching and filtering parameters a client sends and returns matching rows;
  - file listing;
  - status;
  - reload, which rebuilds the index from the current tree and responds once the rebuilt index is in use.

  Direct protocol searches use the matching and filtering rules of FP-02 through FP-07. They default to an empty pattern, no additional patterns, no replacement, no extra path or type filters, the whole served root, no context, automatic engine and encoding selection, and no optional count, depth, file-size or compilation-size limits. Optional matching and filtering switches are off by default. Source-position and match-span details are included by default; callers may omit either category. Per-file and candidate statistics, filename-only projection and inclusion of binary matching lines are off by default. Filename-only projection with statistics returns file identifiers and totals; without statistics, ordinary matching rows remain available. Binary results identify the first NUL position and matching-line count; their matching lines are included only when requested and not using filename-only projection with statistics.

  Direct protocol file listings default to the whole served root, hidden files excluded and no depth limit.

  Several clients may be connected at once, and one connection may carry several requests in turn. Concurrent searches return the same results each would return alone.
- **Automatic refresh.** In `auto` mode (the default) the server prefers native filesystem notifications. In `poll` mode it uses polling only and creates no native subscriptions. Either way, after the initial build:
  - a file created, modified, renamed or deleted under the root is reflected in later search results;
  - a file created in a directory that did not exist at startup is picked up;
  - a file under an ignored directory, or matched by an ignore rule, is never indexed;
  - a change to a `.gitignore` or `.ignore` file takes effect: content newly ignored stops being returned, and content newly unignored becomes searchable;
  - a symbolic link is never followed into content;
  - in a repository with core.ignorecase, adding a file to Git's index, or removing it, under a case-insensitively ignored directory is reflected.

  When a change counts as reflected: a change counts as reflected once every search that starts later shows it. Time is measured from the moment the change is complete on disk, with no further changes to the tree in the meantime.
  - While status reports the active mode as native, each listed change is reflected within 60 seconds. FP-10.01 states when an `auto` server reports native rather than starting.
  - While the active mode is poll, each listed change is reflected once a reconciliation that started after the change has completed. Given the cadence below, that is at most poll-interval seconds plus the duration of one reconciliation.

  Reflecting a change sooner is always allowed.
- **Polling cadence.** In polling, each reconciliation detects additions, modifications and deletions, including modifications that preserve file size and modification time. The next one starts at most poll-interval seconds after the previous one completes. The default is 120, and the accepted range is 1 to 86,400. Ongoing queries do not postpone polling.
- **Fallback to polling.** In `auto` mode, if the native watch budget would be exceeded or native registration fails, the server releases its native watches and switches to polling until restart. Status then reports polling as the active mode, `auto` as the requested mode, and a fallback reason. The watch budget is the most native watches this process may use. Its default is 8192 and the accepted range is 1 to 4,294,967,295. On Linux and Android each admitted, non-ignored directory uses one watch, so a budget smaller than the number of such directories forces the fallback.
- **No-watch.** With no-watch, the server performs the initial build or startup reconciliation, and no automatic refresh after that. New files and newly introduced searchable content are not added until a reload. Files already selected by the existing index are read from their current contents, so removed or changed content may stop matching before a reload. Status reports the mode as disabled.
- **Persistence.** The server saves index changes to the index directory. "The saved index" means what a search without a server (FP-07) answers from after the server has stopped. The following changes must be in the saved index from the stated point on, even if the server is then stopped by an interrupt:
  - changes reflected by startup reconciliation (FP-09.03): saved from the moment the reconciliation fields report that reconciliation's successful completion;
  - files created, modified or deleted under the root while the active mode is poll: saved once the change counts as reflected under FP-09.05's poll bound;
  - the rebuilt index from a reload over the protocol (FP-09.04): saved by the time the reload has responded.

  Changes reflected only through native notifications are also saved in the background. When they are saved is the implementer's choice, and that includes the effect of the auto-save-mutations threshold (default 5000, at least 1). Changes not yet saved when the server is interrupted need not reach the saved index. After the server stops, the saved index is usable by searches without a server and by a server started later. Stopping the server with an interrupt removes the discovery record.
- **Watcher queue.** The watcher-queue-cap option bounds buffered filesystem events, and startup reports the configured capacity. Its default is 16,384, and the accepted range is 1 up to the platform's maximum size. Overflow never loses a change permanently: it triggers a reconciliation and a standard-error diagnostic identifying the overflow and queue capacity.

**Boundary / error behavior:**

- A second server for an index directory whose server lock is held fails with the error status. Its diagnostic identifies the occupied index directory and the lock conflict. The running server is unaffected.
- The following combinations are usage errors with the error status:
  - no-watch together with an explicitly given watch-mode, poll-interval or watch-budget, even when the given value equals the default, and whatever the order;
  - watch-mode `poll` together with an explicit watch-budget;
  - a watch-mode other than `auto` or `poll`;
  - a poll-interval outside 1 to 86,400 or not a whole number;
  - a watch-budget outside 1 to 4,294,967,295 or not a whole number;
  - a zero or non-numeric max-memory, auto-save-mutations or watcher-queue-cap.
- The traversal options refused by an index build (FP-06.08) are refused by the server in the same way. An index directory that contains the source root is refused with the error status.
- An unparsable protocol request receives a parse-error outcome. An unknown operation gets a method-not-found response. Invalid search parameters get an invalid-params response. A search or file listing sent while the index lacks full coverage, including during the initial build, gets an error response rather than partial results. Each of these is an error response, and the connection stays usable.

### FP-10: Index and server status

**Scope:** Reporting index and server status. The root defaults to the current directory. Accepts the custom index path option.

**Normal behavior:**

- **With a reachable server** for the index directory, status prints a server-status report naming the root. The report gives:
  - the server's process id and port;
  - the number of indexed files;
  - whether native watching is active;
  - the active refresh mode (one of native, poll, starting, disabled) together with the requested mode (one of auto, poll, disabled);
  - any fallback reason;
  - the watch budget, and the poll interval;
  - whether a reconciliation is running or idle;
  - when the last successful reconciliation happened, or that none has;
  - whether a reconciliation is pending, and whether one is overdue;
  - the duration of the last completed reconciliation, and an error when that reconciliation failed;
  - indexing progress as files done out of total, or complete; the total may be unknown and reported as zero until enumeration determines it;
  - hidden-file coverage as complete or unavailable.

  **Active mode.** Under no-watch the active mode is disabled, and with watch-mode `poll` it is poll from startup. An `auto` server that has fallen back to polling (FP-09.07) reports poll from then on. An `auto` server that has not fallen back reports starting until its native watching covers the tree, and native after that. Once it reports native, it never again reports starting. It reports native, not starting, no later than these points:
  - for a server that builds its index in the background (FP-09.02): from the moment status reports indexing complete;
  - for a server started on an existing complete index (FP-09.03): from the moment the report first gives a last-reconciliation duration, that is, once its first reconciliation has completed, whether it succeeded or failed.

  How long before those points the switch to native happens is the implementer's choice.

  **Reconciliation fields.** A reconciliation is one full comparison of the tree against the server's index. It can be the startup reconciliation (FP-09.03), the pass that ends a background build (FP-09.02), a polling pass (FP-09.06), or the periodic safety pass the server also runs while native watching is active. The schedule of that safety pass is the implementer's choice. These rules decide the reconciliation fields:
  - **Pending** is yes from startup when the requested mode is poll. It is also yes from the moment an `auto` server falls back to polling (FP-09.07). In both cases it stays yes until the next reconciliation starts, including while that reconciliation is held back by a background build or save still in progress. At all other times it is no. It is always no under no-watch, and always no while an `auto` server keeps native watching.
  - **Overdue** is always no under no-watch. Otherwise it is yes when pending is yes. It is also yes once enough time has passed since the last reconciliation completed, whether it succeeded or failed. If none has completed yet, the time counts from server startup. "Enough time" is the poll interval while the active mode is poll, and 4 hours while the active mode is native or starting. In every other case overdue is no.
  - **Failure.** A reconciliation fails when it cannot read a file or directory under the root that it would otherwise admit. It also fails when it cannot save its result to the index directory. After a failed reconciliation, the report shows an error, and the last-success time is unchanged: it is still the earlier success, or none. After a successful reconciliation, no error is shown and the last-success time moves to that reconciliation. The duration appears once any reconciliation has completed, whether it succeeded or failed. The error's wording is not fixed.

  Reported ages are elapsed whole units, rounded down; the choice of seconds, minutes, hours or days is free. The report may also carry index and cache statistics such as a trigram count or content-cache use. Whether these appear, and their values, is the implementer's choice. The exit status is success.
- **Without a server, with an on-disk index,** status prints an index-status report naming the root. It gives the number of indexed files, how long ago the index was created and last updated, that no server is running, and hidden-file coverage. Coverage is reported complete exactly when the index has full coverage under FP-07.11's rule, so a search without a server would answer from it. Otherwise coverage is reported unavailable. As in FP-10.01, a trigram count may also appear, and its value is the implementer's choice. The exit status is success.
- **With neither,** status says that no index exists at the index directory and suggests the command to build one. The same report is given when the index directory's the index metadata is missing or cannot be parsed. The exit status is success.
- **Readiness agrees with searching.** While no reload is in progress, when a server's status reports indexing complete and coverage complete, a search eligible for server preference under FP-07.01 sent next is answered by the server rather than falling back (FP-07.12). These two fields describe readiness, not freshness: the reconciliation fields of FP-10.01 report whether the server has caught up with the tree.

**Boundary / error behavior:**

- A status root that does not exist ends with the error status.
- **Unreadable coverage metadata.** For status, the coverage metadata is the index directory's the supplemental filename and coverage artifact (FP-06.07). When the index metadata is readable but the supplemental filename and coverage artifact exists and cannot be read, or is not in the form trisift writes (including empty or truncated), status reports coverage unavailable. It also prints a warning on standard error, and still prints the rest of the index-status report, with the success status. When the supplemental filename and coverage artifact is simply missing, coverage is reported unavailable without that warning.
