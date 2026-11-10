# Interface Contract

The executable is `trisift`, available on `PATH`. Invoke it from the caller's working directory. Relative path arguments are relative to that directory. The public interfaces are commands, files, and a loopback TCP service; no importable API is required.

Commands are `trisift`, `trisift search`, `trisift index`, `trisift serve`, `trisift status`, and `trisift count-files`; `help` is also a command name. Search and its explicit `search` spelling share the `trisift` page. Command options listed there are global options; command-specific options appear on their command pages. `--` ends option parsing. Value-taking long options accept `--<option> <value>` and `--<option>=<value>`; short value-taking options also accept an attached value. Flag combinations and acceptance conditions are defined in the PRD.

Results use stdout; diagnostics, warnings, progress and statistics use stderr. Text is UTF-8. Text records end in LF (`\n`), except filename records selected with `--null` or `-0`, which end in NUL (`\0`). JSON object member order, insignificant whitespace and equivalent string escaping are free. Extra JSON members are permitted unless a page expressly closes an object. Free diagnostic text is the implementer's choice; a fixed marker never fixes the remainder of its sentence. Additional progress diagnostics and their order are free where the PRD permits them.

Exit statuses are `0` for a successful command or the search match outcome, `1` for the search no-match outcome, and `2` for an error. Usage/value rejection carries no stdout and a nonempty stderr explanation. Other failures carry an explanation on stderr; any result output and status precedence follow the PRD. No Python exception is an interface of the executable.

The index directory is `<root>/.trisift` unless selected with `--index-path <directory>`. Its named files have separate pages. Directory contents beyond the named files are free. The server endpoint is `127.0.0.1:<port>`, with the port read from `serve.json`. `trisift serve` accepts `SIGINT` as its interrupt input. The lock file's contents and its presence after shutdown are free.

The TCP interface uses JSON-RPC `2.0`. Each request and response is one UTF-8 JSON object terminated by LF. Request fields are `jsonrpc` (the string `2.0`), `id` (integer or string), `method` (string), and optional `params` (object). The method names are `search`, `files`, `status`, and `reload`. A success response has `jsonrpc`, the echoed `id`, and `result`; an error response has `jsonrpc`, `id`, and `error`, with no `result`. `error` contains integer `code` and string `message`; the message is free text explaining the failure. The error identifiers are `-32700` for a parse error, `-32601` for an unknown method, and `-32602` for invalid parameters. An unparseable request has null response `id`. An unavailable query has an error response whose numeric code is free. Responses travel on the TCP connection, not stdout.

Source files are caller-supplied filesystem inputs. The product accesses them through ordinary filesystem interfaces; the PRD governs which source files it reads.

`trisift -h`, `trisift --help`, `trisift help`, `trisift <command> --help`, and `trisift help <command>` write help to stdout and exit `0`. Help contains `Usage:` and describes the selected command's arguments and options; its other labels, wording, and layout are free. `trisift -V` and `trisift --version` write one stdout line `trisift <version>` and exit `0`; the version string is free. Successful help and version requests have empty stderr.

## `trisift`

### Invocation and arguments

`trisift [options] [--] <pattern> [<path> ...]`

`trisift search [options] [--] <pattern> [<path> ...]`

`trisift [search] [options] -e <pattern> [-e <pattern> ...] [--] [<path> ...]`

`trisift [search] [options] -f <pattern-file> [-e <pattern> ...] [--] [<path> ...]`

`trisift --files [options] [<path> ...]`

`trisift --type-list [options]`

A pattern is text; a path names a file or directory. With an explicit `-e`/`--regexp` or `-f`/`--file`, every positional argument is a path for either search entry. Paths may be omitted; a default exists. The pattern file is UTF-8 text with one pattern per line. Pattern syntax and replacement expansion are defined by the PRD. Replacement text accepts capture references by number or name, using `$<number>`, `${<number>}`, and `${<name>}` notation.

The optional `[search]` is the literal subcommand name. The pattern-source options may be combined; their long spellings are interchangeable with their short spellings. Without a pattern-source option, a positional pattern is required for either search entry.

Every option in the following tables takes no argument unless one is shown. `integer` means a decimal whole-number argument; its accepted bounds belong to the PRD. `size` is a decimal byte-size argument with an optional `K`, `M`, or `G` suffix, also accepted in lowercase. Numeric defaults and limits belong to the PRD.

| Option spelling | Argument form |
|---|---|
| `-i`, `--ignore-case` | none |
| `-s`, `--case-sensitive` | none |
| `-S`, `--smart-case` | none |
| `-F`, `--fixed-strings` | none |
| `-w`, `--word-regexp` | none |
| `-x`, `--line-regexp` | none |
| `-v`, `--invert-match` | none |
| `-e`, `--regexp` | pattern string; repeatable |
| `-f`, `--file` | pattern-file path |
| `-U`, `--multiline` | none |
| `--multiline-dotall` | none |
| `-P`, `--pcre2` | none |
| `--engine` | `auto`, `default`, or `pcre2`; a default exists |
| `--no-unicode` | none |
| `--regex-size-limit` | size; a default exists |
| `--dfa-size-limit` | size; a default exists |
| `-r`, `--replace` | replacement string |
| `--passthru` | none |
| `--stop-on-nonmatch` | none |
| `-E`, `--encoding` | encoding label string, including `auto` and `none`; a default exists |
| `--no-encoding` | none |
| `-a`, `--text` | none |
| `--binary` | none |

| Option spelling | Argument form |
|---|---|
| `-l`, `--files-with-matches` | none |
| `--files-without-match` | none |
| `-c`, `--count` | none |
| `--count-matches` | none |
| `--include-zero` | none |
| `-o`, `--only-matching` | none |
| `-m`, `--max-count` | integer |
| `--files` | none |
| `-q`, `--quiet` | none |
| `-A`, `--after-context` | integer |
| `-B`, `--before-context` | integer |
| `-C`, `--context` | integer |
| `-H`, `--with-filename` | none |
| `-I`, `--no-filename` | none |
| `-n`, `--line-number` | none |
| `-N`, `--no-line-number` | none |
| `--heading`, `--no-heading` | none |
| `--column`, `--no-column` | none |
| `-b`, `--byte-offset` | none |
| `-M`, `--max-columns` | integer |
| `--max-columns-preview` | none |
| `--json`, `--vimgrep` | none |
| `--color` | string; named modes `auto`, `always`, `never`; a default exists |
| `-p`, `--pretty` | none |
| `-0`, `--null` | none |
| `--trim` | none |
| `--context-separator` | separator string, including an empty string |
| `--no-context-separator` | none |
| `--field-match-separator` | separator string |
| `--field-context-separator` | separator string |
| `--path-separator` | separator string |
| `--sort`, `--sortr` | `none`, `path`, `modified`, `accessed`, or `created` |
| `--sort-files` | none |
| `--line-buffered`, `--block-buffered` | none |

| Option spelling | Argument form |
|---|---|
| `-g`, `--glob` | glob string; repeatable |
| `--iglob` | glob string; repeatable |
| `--glob-case-insensitive` | none |
| `-t`, `--type` | type-name string; repeatable |
| `-T`, `--type-not` | type-name string; repeatable |
| `--type-add` | `<name>:<glob>` or `<name>:include:<type-name>[,<type-name>...]`; repeatable |
| `--type-clear` | type-name string; repeatable |
| `--type-list` | none |
| `--max-filesize` | size; a default exists |
| `--no-max-filesize` | none |
| `--max-depth` | integer |
| `-.`, `--hidden` | none |
| `-L`, `--follow` | none |
| `--one-file-system` | none |
| `-u`, `--unrestricted` | none; repeatable, including combined `-uu` and `-uuu` |
| `--ignore-file` | ignore-file path; repeatable; file contains gitignore-format text |
| `--ignore-file-case-insensitive` | none |
| `--no-ignore` | none |
| `--no-ignore-dot` | none |
| `--no-ignore-exclude` | none |
| `--no-ignore-files` | none |
| `--no-ignore-global` | none |
| `--no-ignore-parent` | none |
| `--no-ignore-vcs` | none |
| `--no-require-git` | none |
| `--no-ignore-messages`, `--no-messages` | none |
| `--index-path` | directory path; a default exists |
| `--no-index` | none |
| `--stats`, `--debug`, `--trace` | none |
| `-j`, `--threads` | integer |
| `--mmap`, `--no-mmap` | none |
| `--crlf`, `--no-crlf` | none |
| `--no-config` | none |
| `--colors` | color specification string; repeatable |
| `--pcre2-version` | none |
| `-z`, `--search-zip` | none; rejection uses the error interface |

### Plain stdout

A matching text row has the fields, in order, optional path, optional line number, optional column, optional byte offset, and content. Each enabled prefix field is followed by `:`. A context row uses `-` in place of `:` and has no column field. The content field contains the selected line, match, or replacement text, as determined by the PRD. Decimal line numbers and byte columns are one-based; byte offsets are zero-based in the PRD's coordinate space. Under `--only-matching`, a byte offset identifies the match. Under `--vimgrep`, the fixed form is `<path>:<line>:<column>:<content>`.

`--field-match-separator` and `--field-context-separator` supply the respective separators. `--context-separator` supplies the entire group-separator line; its ordinary marker is `--`. A suppressed group separator produces no line. In heading output the filename occupies its own line, subsequent rows omit the path field, and a blank line separates file groups. File order follows the requested ordering; absent an ordering guarantee in the PRD it is any order. Rows within a file follow their source positions.

A displayed path consists of an optional caller-supplied root prefix and a relative filename, with separators selected by the path-separator option or the platform separator. The PRD specifies preservation of the caller's spelling and omission of the prefix. These same path forms apply to listings, counts, headings, and JSON path text.

Filename-only modes (`--files`, `-l`/`--files-with-matches`, `--files-without-match`) emit `<path>` records, with LF or the selected NUL terminator. Count modes emit `<path>:<count>` with filenames enabled, or `<count>` without them. The field separator option applies to the count prefix too. The count is a nonnegative decimal integer; its meaning is defined by the selected counting mode. Quiet stdout is empty.

A substituted long matching line has the marker `[Omitted long matching line]`; a substituted long context line has `[Omitted long context line]`. A preview consists of a retained content prefix followed by the fixed omission marker ` [... omitted end of long line]`.

Color is ANSI SGR: ESC followed by `[` and semicolon-separated decimal parameters, then `m`. In source escape notation the shape is `\x1b\[[0-9;]*m`; a reset is `\x1b[0m`. Highlighted spans have opening SGR sequence(s), the span text, then reset. Parameter choices and colors are free; removing SGR sequences leaves the corresponding plain layout. Terminal versus pipe layout selection is defined by the PRD.

Binary-result notes use one stdout line, with `<path>: ` when the filename is displayed, then the marker `binary file matches` and free text containing one field in any of the forms `offset <integer>`, `offset: <integer>`, or `byte <integer>`, the first NUL's zero-based byte position. The precise sentence around that field is free.

`--type-list` emits `<name>: <glob>[, <glob>...]` per line. Type names appear in ascending order, one line per name and alias; the types and their globs are those of the table in use (built-in types per the PRD, after type-add and type-clear); the separators are fixed. `--pcre2-version` emits one stdout line identifying the engine and its PCRE2 linkage status. It carries the engine identifier and `PCRE2`, with the linkage status marker `not linked`. The surrounding explanation is free text.

### JSON stdout

`--json` uses JSON Lines. Each object contains string `type` and object `data`. The record types are `begin`, `match`, `context`, `end`, and `summary`. A file's records are contiguous: `begin`, its line records in source order, then `end`. The final record is `summary`. Which modes select this stream is defined by the PRD.

| `type` | `data` fields |
|---|---|
| `begin` | `path: {"text": <string>}` |
| `match`, `context` | `path: {"text": <string>}`, `lines: {"text": <string>}`, `line_number: <integer>`, `absolute_offset: <integer>`, `submatches: <array>` |
| `end` | `path: {"text": <string>}`, `binary_offset: <integer or null>`, `stats: <object>` |
| `summary` | `elapsed_total: <duration object>`, `stats: <object>` |

`path.text` is the displayed path. `lines.text` is the reported line text with its LF terminator. `line_number` is one-based. `absolute_offset` is the zero-based byte position of the line in the PRD's coordinate space. `binary_offset` is the first reported NUL's byte offset or null when none is reported.

A submatch is `{"match":{"text":<string>},"start":<integer>,"end":<integer>}`. `start` is inclusive and `end` exclusive, both zero-based UTF-8 byte positions within `lines.text`. Submatches are in increasing position order. A context record has the same submatch-array form.

The `stats` fields are nonnegative integers `searches` (files searched), `searches_with_match` (files with selected matching lines), `bytes_searched` (searched bytes), `bytes_printed` (reported output bytes), `matched_lines` (selected matching lines), and `matches` (individual matches), plus `elapsed` (duration object). An `end` record's statistics describe that file; a `summary` describes the invocation. A duration object has integer `secs` and `nanos`, meaning whole seconds and the fractional nanosecond component, and `human`, a string with a seconds value followed by `s`; its precision is free.

### Stderr and failures

A regex failure contains `regex error:` followed by free explanatory text and exits with the error status. A compilation size failure additionally carries the marker `size limit`; surrounding explanation is free text. Usage output carries `Usage:` with free explanatory text. A path diagnostic has `trisift: <path>: <free text>`. A rejected option's diagnostic identifies its long spelling. An ignore-rule report carries `<ignore-file-path>: line <line-number>:` followed by free text, with a one-based decimal line number.

Warnings use `warning:`; an absent-index warning has the directory field `at <index-directory> - <free explanation>`, and a `note:` gives build guidance containing `trisift index`. A coverage warning identifies unavailable coverage and the filesystem fallback. A server fallback notice begins `Server unavailable` and explains the fallback in free text. Other diagnostic wording is free.

Statistics go to stderr after result output. The scan report carries the label `Brute-force search completed`; the local-index report carries `Search completed`; the server report carries `(via server)`. Each report is one line and carries elapsed milliseconds as `<number>ms` and the fixed count fragment `<matches> matches (<matched-lines> matched lines)`. A scan also carries `<files> file` or `<files> files`. Connecting prose and the placement of elapsed time relative to these fragments are free.

An indexed report carries a line ending `(candidates: <candidates>/<indexed-files>; raw candidates: <raw-candidates>/<indexed-files>)`. The prefix, including any query-plan description, is free text. These are nonnegative integer counts of candidates after filtering, raw candidates, and indexed files. The no-narrowing marker is `(no index narrowing)`.

A filename-listing statistics report carries elapsed milliseconds and one of `(via server)`, `(via local index)`, or `(via filesystem walk)`. Its remaining text is free. Statistics precision is free. No extra stdout prose accompanies result records.

For `--files`, a completed listing exits `0`, including an empty listing after filtering or from an empty root or index. It emits no filename records when no paths are admitted. This outcome is the same for filesystem, local-index and server listings; content-search no-match status `1` does not apply. Missing path arguments retain the successful-listing outcome described in the PRD.

## `trisift index`

`trisift index [options] [<path>]` accepts a directory path; a default exists. Global options are listed on the `trisift` page. The command-specific options are:

| Option | Argument |
|---|---|
| `--force` | none |
| `--exclude` | directory-name string; repeatable |
| `--index-strategy` | `memory` or `external`; a default exists |
| `--index-buffer` | decimal integer in MiB; a default exists |

Successful publication exits `0`, with empty stdout. It writes the named index files in the selected index directory. On stderr, a success line begins `Index`, contains free announcement text, and ends with the field `at <index-directory>`. A separate report line begins `Indexed` and carries elapsed seconds (`<number>s`) and the selected strategy, as `<strategy> strategy` or `strategy: <strategy>`, where `<strategy>` is `memory` or `external`. The report may carry `peak memory <amount>` or `peak memory: <amount>`, where the amount is a decimal number and a byte unit (`B`, `bytes`, or a K/M/G/T unit, with optional `i`, ending in `B`). The success announcement contains an absolute directory path or a path relative to the caller's working directory. These report markers identify their respective lines. The remaining sentences and labels are free text. Buffer confirmation contains the labelled fragment `arena <integer> MB`, with the amount in MiB; surrounding prose is free. The PRD specifies when each report is present.

Rejection exits `2` with a nonempty stderr explanation and no stdout. A traversal-option rejection names that option by its long spelling. Failure reasons and publication conditions belong to the PRD; no particular explanatory sentence is fixed.

An unapplied-ignore warning uses a stderr line beginning `warning: <root> ` followed by a free explanation. Other progress diagnostics use free text.

## `trisift serve`

`trisift serve [options] [<path>]` accepts a directory path; a default exists. It is a foreground command. Global options are listed on the `trisift` page. Its command-specific options are:

| Option | Argument |
|---|---|
| `--exclude` | directory-name string; repeatable |
| `--no-watch` | none |
| `--watch-mode` | `auto` or `poll`; a default exists |
| `--poll-interval` | decimal integer seconds; a default exists |
| `--watch-budget` | decimal integer watch count; a default exists |
| `--max-memory` | decimal integer MiB; a default exists |
| `--max-cpu` | decimal integer percentage; a default exists |
| `--auto-save-mutations` | decimal integer mutation count; a default exists |
| `--watcher-queue-cap` | decimal integer event count; a default exists |

The selected directory receives `serve.lock`, `serve.json`, and the persisted index files. `serve.json` identifies the TCP endpoint. Result messages use that endpoint, not stdout; normal stdout is empty. Progress and diagnostics use stderr, with free wording and order. Progress lines may carry `[trace]`.

`SIGINT` is the interrupt/shutdown input. Exit status on signal termination is not otherwise fixed here. Startup rejection exits `2`, produces no stdout, and provides a nonempty stderr explanation. An option refusal names the long option spelling. A lock refusal identifies the index-directory path as supplied and explains that another server holds it; its words are free text. The PRD determines accepted combinations, limits, persistence, and file lifecycle.

A queue-overflow diagnostic on stderr carries the marker `watcher queue overflowed` and the field `(cap <integer>)`, the event capacity. Its remaining wording and any diagnostic prefix are free.

The startup diagnostic includes `Watcher queue cap: <integer>.`, the configured event capacity. Surrounding diagnostic text is free.

## `trisift count-files`

`trisift count-files [options] [<path>]` takes a directory path; a default exists. The global options are on the `trisift` page.

stdout is one LF-terminated nonnegative decimal integer, the admitted-file count. stderr carries a report with the count fragments `<admitted> text files`, `<binary-count> binary skipped`, `<large-count> too large`, `<error-count> errors`, and elapsed milliseconds `<integer>ms`. Their meanings are admitted files, files skipped for binary extension, files skipped for size, traversal errors, and elapsed time. Surrounding punctuation and connecting prose are free text. The PRD determines the counts.

Success exits `0`; rejection or command failure exits `2` and carries a nonempty stderr explanation in free text. A completed count report carries no additional stdout text.

## `trisift status`

`trisift status [--index-path <directory>] [<path>]` takes a directory path; defaults exist for omitted paths. A completed status report exits `0`. A rejected invocation or command failure exits `2` with a stderr explanation in free text.

stdout has a header followed by report lines. The headers are `Server status for <canonical-root>`, `Index status for <canonical-root>`, or `No index found at <index-directory>`. These are fixed header labels with a path value. The no-index report also carries build guidance naming `trisift index <canonical-root>`; the guidance wording is free text.

The server and index reports use field lines `  <Label>: <value>`. Exactly two leading spaces and the colon are fixed; alignment whitespace after the colon is free but nonempty. Each label appears at most once. Field order is any order. Additional labelled fields are allowed and their contents are free.

The server report fields are:

| Label | Value form and meaning |
|---|---|
| `PID` | decimal process id |
| `Port` | decimal TCP port |
| `Files` | nonnegative decimal indexed-file count |
| `Watcher` | `active` or `inactive`, native-watcher state |
| `Watch mode` | `<active> (requested: <requested>)`; active is `native`, `poll`, `starting`, or `disabled`; requested is `auto`, `poll`, or `disabled` |
| `Fallback` | reason, free nonempty text; omitted when no reason exists |
| `Watch budget` | decimal watch count |
| `Poll interval` | `<integer>s`, optionally followed by a space and a free note |
| `Reconcile` | `idle` or `running` |
| `Last successful reconcile` | age or `never` |
| `Reconcile pending` | `yes` or `no` |
| `Reconcile overdue` | `yes` or `no` |
| `Last reconcile duration` | `<integer>ms`; omitted before any completed reconciliation |
| `Last reconcile error` | free nonempty explanatory text; omitted without a current error |
| `Indexing` | `complete` or `<done>/<total> files`, decimal file counts |
| `Hidden coverage` | `complete` or `unavailable`, optionally followed by ` (<free note>)` |

The index report fields are `Files`, `Created`, `Updated`, `Server`, and `Hidden coverage`. `Files` and `Hidden coverage` have the forms above; `Server` is `not running`; `Created` and `Updated` are ages of the index's creation and update. An age is `<integer><unit> ago`, with unit `s`, `m`, `h`, or `d` for seconds, minutes, hours, or days. Unit selection and rounding belong to the PRD.

Optional fields include `Trigrams` with a decimal count and `Cache` with `<used>/<capacity>` integer counts; their presence and values are free. Any coverage diagnostic goes to stderr with `warning:` and free explanatory text. The PRD determines which report and values apply.

## `search`

The JSON-RPC method is `search`. Its `params` object accepts the following optional members; defaults and selection semantics belong to the PRD.

| Members | Input forms |
|---|---|
| `pattern`, `replace` | text strings |
| `scope` | root-relative directory string with forward-slash separators |
| `extra_patterns`, `glob`, `iglob`, `types`, `types_not`, `type_add`, `type_clear` | arrays of strings, using the corresponding CLI option's argument forms |
| `case_insensitive`, `fixed_string`, `word_boundary`, `glob_case_insensitive`, `invert_match`, `only_matching`, `multiline`, `multiline_dotall`, `files_only`, `text`, `binary_lines`, `line_regexp`, `no_unicode`, `passthru`, `stop_on_nonmatch`, `vimgrep`, `detail`, `positions`, `stats`, `hidden` | booleans |
| `max_count`, `max_depth`, `before_context`, `after_context`, `max_filesize`, `regex_size_limit`, `dfa_size_limit` | nonnegative integers; counts or byte amounts corresponding to their CLI options |
| `engine` | `auto`, `default`, or `pcre2` |
| `encoding` | encoding label string |

The matching and filtering members correspond to CLI inputs as follows: `pattern` is the pattern argument; `extra_patterns` supplies additional patterns; `case_insensitive` corresponds to `--ignore-case`, `fixed_string` to `--fixed-strings`, `word_boundary` to `--word-regexp`, `files_only` to filename-only projection, `types` to `--type`, and `types_not` to `--type-not`. Other matching and filtering names use underscores in place of the corresponding long option's hyphens. `max_filesize`, `regex_size_limit` and `dfa_size_limit` are byte amounts; `max_count`, `max_depth`, `before_context` and `after_context` are counts. `scope` is a relative directory prefix using `/`, without an initial slash or dot path components; an empty string denotes the served root and a trailing slash is accepted. `binary_lines` selects binary matching-line rows, `detail` selects matching-span and column fields, `positions` selects byte-position and terminator fields, and `stats` selects per-file and candidate statistics. The PRD specifies defaults and projection semantics.

The common envelope is on the product-wide page. The success `result` is an object containing `matches`, an array of row objects. File order is any order; line rows of a file use source order.

| Row | Fields |
|---|---|
| Text | `type`: `match` or `context`; `file`: path string; `line`: one-based integer source line number; `content`: reported text without its terminator |
| Binary | `type`: `binary`; `file`: path string; `offset`: nonnegative integer first-NUL byte position; `lines`: nonnegative integer matching-line count |
| Filename projection | `type`: `match`; `file`: path string; `line` and `content` may be omitted |

Paths are relative to the served root with `/` separators. The filename projection form is available with both `files_only` and `stats`; otherwise text rows carry their line and content fields. The PRD defines which rows and information are selected.

Selected detail fields on matching text rows are `spans`, an array of `[<start>, <end>]` pairs of zero-based UTF-8 byte positions in `content` with exclusive ends, and `columns`, an array of one-based source byte columns. Selected position fields on text rows are `offset`, the zero-based source byte offset, and `term`, the source line terminator's byte count. These numeric fields are nonnegative integers, except that columns are positive integers.

The result may also carry `num_matches` (integer row count), `searches` (integer searched-file count), `elapsed_ms` (number of elapsed milliseconds), and `hidden_complete` (boolean coverage state). A statistics result may carry `file_stats`, an array of objects with `file` (path), `matches` and `matched_lines` (nonnegative integer per-file totals), and `index_stats`, an object with nonnegative integer `raw_candidates`, `candidates`, and `total_files`, whose meanings are the candidate and indexed-file counts in the PRD. A `query_plan` member is free text. Additional row and result fields remain allowed and free.

Failures use the common JSON-RPC error response. This method writes no result to process stdout.

## `files`

The JSON-RPC method is `files`. `params` may be omitted or be an object with optional `scope` (relative directory string), `hidden` (boolean), and `max_depth` (nonnegative integer). Their forms are those of the same members on the `search` page. The success `result` contains `files`, an array of strings naming paths relative to the served root with `/` separators. Array order is any order. Additional result fields are allowed and free. An unavailable listing uses the common JSON-RPC error response. Results are on the TCP connection.

## `status`

The JSON-RPC method is `status`; no parameters are required. Its success `result` is an object with the following fields. Fields are always present; nullable values use JSON null. Additional fields are permitted and free.

| Field | Type and meaning |
|---|---|
| `num_files` | nonnegative integer indexed-file count |
| `watcher_active` | boolean native-watcher activity |
| `watch_mode_active` | string `native`, `poll`, `starting`, or `disabled` |
| `watch_mode_requested` | string `auto`, `poll`, or `disabled` |
| `watch_fallback_reason` | nonempty string reason or null; free wording |
| `watch_budget` | integer maximum native-watch count |
| `poll_interval_secs` | integer polling interval in seconds |
| `reconcile_running` | boolean reconciliation-running state |
| `last_reconcile_at` | integer Unix timestamp in seconds of completion of the last successful reconciliation, or null |
| `reconcile_pending` | boolean pending-reconciliation state |
| `reconcile_overdue` | boolean overdue-reconciliation state |
| `last_reconcile_duration_ms` | nonnegative integer duration in milliseconds or null |
| `last_reconcile_error` | nonempty error string or null; free wording |
| `indexing` | boolean indexing-in-progress state |
| `index_progress` | nonnegative integer files processed |
| `index_total` | nonnegative integer total file count for progress |
| `hidden_complete` | boolean complete hidden-file coverage |

The PRD defines the state meanings and transitions. The common JSON-RPC envelope and error form apply. Results are on the TCP connection.

## `reload`

The JSON-RPC method is `reload`; no parameters are required. It returns a success `result` object acknowledging completion, with `status` equal to `reloaded`. Other result fields are allowed and free. Failures use the common JSON-RPC error envelope. Responses use the TCP connection. The externally visible side effect is an updated persisted index in the selected index directory; the PRD defines its contents and completion conditions.

## `.trisift`

The index-directory naming rule is `<root>/.trisift`, or the directory supplied with `--index-path`. A published directory contains `lookup.bin`, `index.bin`, `files.bin`, `files-extra.bin`, `meta.json`, and `filestamps.json`. It may also contain `serve.json` and `serve.lock`. Each has a separate page. Other entries, including temporary entries, have free names and formats. Source file contents are not an output of index publication.

## `lookup.bin`

`<index-directory>/lookup.bin` is a product-written binary file containing index lookup data. Its contents and binary layout are opaque and free to the implementer. Callers exchange the entire file through the selected index directory; there is no public byte-field schema. The product's index, search, serve and status commands are the interfaces to its information. The PRD specifies publication and availability outcomes.

## `index.bin`

`<index-directory>/index.bin` is a product-written binary file containing search index data. Its contents and binary layout are opaque and free to the implementer. Callers exchange the entire file through the selected index directory; there is no public byte-field schema. The product's index, search, serve and status commands are the interfaces to its information. The PRD specifies publication and availability outcomes.

## `files.bin`

`<index-directory>/files.bin` is a product-written binary file containing indexed-file data. Its contents and binary layout are opaque and free to the implementer. Callers exchange the entire file through the selected index directory; there is no public byte-field schema. The product's index, search, serve and status commands are the interfaces to its information. The PRD specifies publication and availability outcomes.

## `files-extra.bin`

`<index-directory>/files-extra.bin` is a product-written binary file containing filename and coverage data. Its contents and binary layout are opaque and free to the implementer. Callers exchange the entire file through the selected index directory; there is no public byte-field schema. The product's index, search, serve and status commands are the interfaces to its information. The PRD specifies publication and availability outcomes.

## `meta.json`

`<index-directory>/meta.json` is a product-written UTF-8 JSON file containing index metadata. Its JSON schema, member order and whitespace are free; callers need not construct its fields. The file is part of the persisted index consumed by later commands. The PRD specifies publication and availability outcomes.

## `filestamps.json`

`<index-directory>/filestamps.json` is a product-written UTF-8 JSON object. Each key is an indexed path relative to the indexed root. Each value is an object with nonnegative integer `mtime` (Unix time in seconds) and `size` (file size in bytes). Additional members are free; JSON member order and whitespace are free. The file is consumed by later commands through the selected index directory.

## `serve.json`

`<index-directory>/serve.json` is the UTF-8 JSON discovery file. Its object contains integer `pid` (server process id) and integer `port` (the listening TCP port on `127.0.0.1`). Additional members, member order, whitespace and a trailing newline are free. The PRD defines publication and removal of this file.

## `serve.lock`

`<index-directory>/serve.lock` is the server's lock file. Its presence and exclusive ownership expose the running server's lock on that index directory. Its contents are opaque and free. Its presence after shutdown is free. Lock acquisition failures use the `trisift serve` error interface.

## `.gitignore`

`<directory>/.ignore` and `<directory>/.gitignore` are caller-supplied text files, with one gitignore-format rule per line. Blank lines and comments are accepted input forms. A rule contains a glob and may carry the gitignore negation prefix. The PRD defines applicability and precedence. These files are inputs; diagnostics use the command stderr form `<ignore-file-path>: line <line-number>: <free explanation>`.

## `.ignore`

Stated under `.gitignore`.

## `.git/info/exclude`

`.git/info/exclude` is an input text file containing gitignore-format rules, one per line. Blank lines and comments are permitted; the rules themselves are input data, not fixed contents. Its location and precedence are defined by the PRD. No output is written to this file. Ignore-rule diagnostics use the command's stderr interface, including the file path and rule line number.

## `p4ignore.ini`

`<root>/p4ignore.ini` is an input text file of gitignore-format rules, one per line. Path separators in those rules may be `/` or `\`. Its contents are supplied by the caller. No output is written to the file. Diagnostics use the command's stderr interface.

## `.gitconfig`

The user's `.gitconfig` is a Git-format input configuration file. In the `[core]` section, `excludesFile = <path>` identifies a global ignore file, whose text uses gitignore rules. The user home is selected by `HOME`; `XDG_CONFIG_HOME` names the configuration directory. These are path-valued environment variables. Other Git configuration entries are outside this interface and free. The product does not write this file.

## `core.ignorecase`

`core.ignorecase` is a boolean Git repository configuration entry in the `[core]` section under the name `ignorecase`. It accepts Git boolean values, including `true` and `false`. The repository is identified by its `.git` entry. The product also consumes the repository's Git tracking information. Git file formats remain Git's; no product-specific layout is imposed. These inputs have no direct output; their results use the search, index, and server interfaces described elsewhere. The PRD defines their effect.

## `core.excludesFile`

Git configuration is supplied in Git configuration-file syntax. `core.excludesFile` is a path-valued entry named `excludesFile` in the `[core]` section; its target is a caller-supplied gitignore-format text file. `HOME` is a directory-valued environment input locating the user home, including `<home>/.gitconfig`. `XDG_CONFIG_HOME` is a directory-valued environment input locating XDG configuration. Git configuration discovery otherwise uses Git's standard locations. These inputs have no direct output; their effects appear through the command result interfaces, with applicability defined by the PRD. The boolean `core.ignorecase` entry has its own page.

## `HOME`

Stated under `core.excludesFile`.

## `XDG_CONFIG_HOME`

Stated under `core.excludesFile`.
