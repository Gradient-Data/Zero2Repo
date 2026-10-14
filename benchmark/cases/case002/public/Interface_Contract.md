# Interface Contract

This contract is the complete outside shell of python-envfile: what a caller imports or invokes, what each entry accepts, and the form of everything the product puts out. What the product does, and under which conditions, is in the PRD; the feature point that governs each entry is named next to it. Every part of an output that this contract does not fix is declared the implementer’s choice where it appears.

## Distribution, package, layout

- Installable distribution: `python-envfile`. Optional extra that enables the command-line program: `cli` (install as `python-envfile[cli]`).
- Importable top-level package: `envfile`, a single directory under `src` (`src/envfile`). Importing it performs no I/O against caller files, starts no processes, and opens no sockets.
- Version: the module `envfile.version` has the attribute `__version__`, a `str` holding `<version>` (the implementer’s choice).
- Module invocation: `python -m envfile` runs the command-line program (see “Command-line program”).

These names are importable from the package root (`from envfile import <name>` and `envfile.<name>`):

- `envfile_values` — values mapping (PRD FP-04).
- `find_envfile` — file location (PRD FP-02).
- `load_envfile` — load into the process environment (PRD FP-03).
- `get_key` — read one binding (PRD FP-06).
- `set_key` — write one binding (PRD FP-06).
- `unset_key` — delete one binding (PRD FP-06).

All of them read the `.env` format of PRD FP-01, and the loading entries expand values as in PRD FP-05.

**Process-environment variable.** `PYTHON_ENVFILE_DISABLED` is the disable switch read by `load_envfile` (PRD FP-03).

## Common forms

**Paths** are accepted as text or as path-like objects. **Streams** are in-memory text streams (for example `io.StringIO`) holding `.env` text.

**Library entries never exit the host process.** They report outcomes by returning a value; where this contract says an entry may raise, the exception class and message are the implementer’s choice.

**Diagnostics.** A diagnostic is one line of human-readable text emitted without aborting the caller, on any of these channels (the choice of channel is the implementer’s): a record through Python’s standard `logging` module (any logger name, any level; one record per diagnostic), a Python warning (`warnings`; one per diagnostic), or one line written to the process’s standard error or standard output. Wording is the implementer’s choice. When the PRD says an entry emits no diagnostic in a situation, nothing is emitted on any of these channels in that situation. Diagnostic kinds, and what each line contains (`<PATH>` is the path as the caller passed it, `<KEY>` the key as passed):

| Kind | Line contains | Line does not contain |
| --- | --- | --- |
| *file-not-found* | `<PATH>` | `<KEY>` |
| *key-not-found* | `<KEY>` | — |
| *path-missing* | `<PATH>` | `<KEY>` |
| *key-not-removed* | `<KEY>` | — |

Each situation the PRD names emits its kinds, one line each; an entry that succeeds emits no line containing `<KEY>` or `<PATH>`. Other diagnostics (for example about a line that could not be parsed) are the implementer’s choice and contain neither `<KEY>` nor `<PATH>`.

## `envfile_values`

```
envfile_values(envfile_path=None, stream=None, verbose=False, interpolate=True, encoding="utf-8")
```

- `envfile_path` — path of a `.env` file or Unix FIFO, or `None` (no path given).
- `stream` — `.env` text stream, or `None` (no stream given).
- `verbose` — extra reporting: emits the *file-not-found* diagnostic when no source is selected (PRD FP-03).
- `interpolate` — expansion on (`True`) or off (`False`).
- `encoding` — codec name used to decode a file or FIFO.

**Returns** a mapping (`collections.abc.Mapping`, for example a `dict`) from binding name (`str`) to recorded value. Membership is `name in mapping`. A value is a `str` (possibly `""`) or, for a no-value binding, a no-value marker that is not a `str`; the marker is the implementer’s choice. A name that is not a binding of the source is not a key. An empty source gives a mapping with no keys. The call does not raise for a missing path.

## `find_envfile`

```
find_envfile(filename=".env", raise_error_if_not_found=False, usecwd=False)
```

- `filename` — base name searched for.
- `raise_error_if_not_found` — when true, finding nothing raises instead of returning empty text.
- `usecwd` — when true, the walk starts at the current working directory.

A *frozen packaged executable* (PRD FP-02) is a process in which `sys.frozen` is true.

**Returns** a `str`: the path of the match (absolute or relative, resolving to the matched file or FIFO), or `""` when nothing matches and `raise_error_if_not_found` is false. Finding nothing with `raise_error_if_not_found` true raises. A working directory that no longer exists, when the walk starts there, raises.

## `load_envfile`

```
load_envfile(envfile_path=None, stream=None, verbose=False, override=False, interpolate=True, encoding="utf-8")
```

- `envfile_path`, `stream`, `verbose`, `interpolate`, `encoding` — as for `envfile_values`.
- `override` — whether source values replace names already in the process environment.

**Returns** a report value: one value for success and a different value for failure (PRD FP-03). The two values are the implementer’s choice; the call does not raise for a missing path, an empty source, or a disabled load. **Side effect:** writes names into `os.environ` of the running process.

## `get_key`

```
get_key(envfile_path, key_to_get, encoding="utf-8")
```

The first two arguments are positional: path, name.

**Returns** the value as a `str` (possibly `""`), or the no-value outcome: a value that is not a `str`, of the implementer’s choice. Does not raise for a missing name, a no-value line, or a missing path. **Diagnostics:** *key-not-found* for a name missing from an existing file; *file-not-found* and *key-not-found* for a missing path.

## `set_key`

```
set_key(envfile_path, key_to_set, value_to_set, quote_mode="always", export=False, encoding="utf-8", follow_symlinks=False)
```

The first three arguments are positional: path, name, value.

- `quote_mode` — one of `"always"`, `"never"`, `"auto"`. Refusal form: raises, or returns a report different from the success report.
- `export` — whether the stored line carries the `export` directive.
- `encoding` — codec used to read and write the file.
- `follow_symlinks` — whether a symbolic link at the path is followed.

**Returns** a success report; its value is the implementer’s choice. **On-disk form** of the stored line, followed by one line feed:

```
[export ]<NAME>=<STORED>
```

where `export ` (the word and one space) is present only when `export` is true, `<NAME>` is the name as given, and `<STORED>` is either `<VALUE>` as given (unquoted) or `'<VALUE’>'`, where `<VALUE’>` is the value with a backslash inserted before each single quote. Which of the two is used follows the quote mode (PRD FP-06). The file is text in the named encoding.

## `unset_key`

```
unset_key(envfile_path, key_to_unset, quote_mode="always", encoding="utf-8", follow_symlinks=False)
```

The first two arguments are positional: path, name. `quote_mode` is accepted and does not change any stored line. `encoding` and `follow_symlinks` are as for `set_key`.

**Returns** a success report, or for a delete that does not succeed either a report different from the success report or a raised exception (the implementer’s choice). **Diagnostics:** *path-missing* for a missing path; *key-not-removed* for a name not in an existing file.

## Command-line program

**Invocation.** `envfile [GLOBAL OPTIONS] SUBCOMMAND [ARGS]`, or equivalently `python -m envfile [GLOBAL OPTIONS] SUBCOMMAND [ARGS]`. Global options come before the subcommand.

**Global options.**

- `--file PATH` / `-f PATH` — the `.env` file (default: `.env` in the current working directory).
- `--quote MODE` / `-q MODE` — `always`, `never`, or `auto`.
- `--export BOOL` / `-e BOOL` — whether `set` writes the `export` directive; `BOOL` is `true` or `false`; whether other spellings are accepted is the implementer’s choice.
- `--version` — prints one line on stdout that ends with `<version>` (`envfile.version.__version__`), and exits 0 without running any subcommand. The text before `<version>` on that line is the implementer’s choice.

**Exit statuses.** `0` success; `1` an operation failure (missing key, failed `unset`, no command, command not found, CLI extra not installed); `2` a usage failure (missing argument, invalid option value, env file that cannot be opened, invalid `--file` for `run`). For `run` with a started child, the status is the child’s.

**Reports.** Wording of every report is the implementer’s choice; each report kind is told apart by its exit status, its channel, and the **usage label**: a line that starts with `Usage:`. *Usage reports* (missing argument, invalid option value, invalid `--file` for `run`) are written on stderr, contain a line with the usage label, and write nothing on stdout. No other report contains a line starting with the usage label.

**Subcommands.**

| Command | Success: stdout | Failure forms |
| --- | --- | --- |
| `list [--format FORMAT]` | see “List formats” | env file cannot be opened: exit 2, *could-not-open* report |
| `get NAME` | `<VALUE>` and a line feed | env file cannot be opened: exit 2, *could-not-open* report. *missing-key*: exit 1, nothing on stdout or stderr |
| `set NAME VALUE` | `<NAME>=<VALUE>` and a line feed, with the name and value as given | missing `NAME` or `VALUE`: exit 2, usage report |
| `unset NAME` | one line that contains `<NAME>` (rest of the line: the implementer’s choice) | name not in the file, or missing file: exit 1; diagnostics as for `unset_key` may appear |
| `run [--override \| --no-override] [--] COMMAND [ARGS...]` | the child’s own stdout and stderr | see `run` below |

Report forms (`<PATH>` is the path as given to `--file`, or the default path; `<PROGRAM>` is the child program name as given):

| Report | Exit | Channel | Contains |
| --- | --- | --- | --- |
| *could-not-open* (env file cannot be opened by `list` / `get`) | 2 | stderr, nothing on stdout | `<PATH>`; no usage label |
| *invalid-file* (`run` with a `--file` / default `.env` that is not an existing regular file) | 2 | usage report | `<PATH>` |
| *no-command* (`run` without `COMMAND`) | 1 | stdout | no usage label |
| *command-not-found* (`run` whose `COMMAND` cannot be found) | 1 | stderr | `<PROGRAM>`; no usage label |
| *cli-extra* (the `cli` extra is not installed) | 1 | stderr, nothing on stdout | the extra’s name `cli`; the same text for every subcommand and argument list; no usage label |

**List formats** (`FORMAT` is `simple`, `json`, `shell`, or `export`; names in sorted order):

- `simple` — one line per name, except names with no value (a name whose value is the empty string is included): `<NAME>=<VALUE>`, value as parsed, no added quoting.
- `json` — one JSON object whose keys are all names, in sorted order, each mapped to its value as a JSON string or to `null` for a no-value name. It is pretty-printed: spread over several lines with indentation (indent width is the implementer’s choice), never the compact single-line encoding.
- `shell` — one line per name, except names with no value (a name whose value is the empty string is included): `<NAME>=<QUOTED>`, where `<QUOTED>` is the value quoted for a POSIX shell (the quoting style is the implementer’s choice, so long as a POSIX `sh` assignment of that line yields exactly the value).
- `export` — the `shell` line prefixed with `export ` (the word and one space).

**`run`.** `--override` / `--no-override` and an optional `--` come before `COMMAND`; every token from `COMMAND` on is passed to the child unchanged. The child is started with the program’s environment plus the selected bindings, and `envfile` exits with the child’s status. Failure forms:

- `--file` (or the default `.env`) is not an existing regular file: *invalid-file* report; no child starts.
- No `COMMAND`: *no-command* report.
- `COMMAND` not found: *command-not-found* report.

**Without the `cli` extra** (its command-line library not importable), any invocation runs no subcommand, writes the *cli-extra* report.
