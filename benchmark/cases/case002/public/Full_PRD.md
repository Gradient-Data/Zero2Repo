# python-envfile — Full Product Requirements Document

## Product overview

**python-envfile** reads key-value pairs from a `.env` file and can set them as environment variables. It exists so an application that follows the [12-factor](https://12factor.net/) pattern — configuration from the process environment — can still be launched in development without the operator exporting every name by hand. When a `.env` file is present, python-envfile loads it; when a name is already in the process environment, that live value stays in control unless the caller asks to override.

A first-time integrator adds a `.env` next to the application, asks python-envfile to load it, and then reads configuration from the process environment as if those names had been exported by the shell. A second, equally supported path is to parse the same file into an in-memory mapping and leave the process environment untouched, so several files (shared settings, secrets) can be merged under caller control.

A command-line program named `envfile` is included so operators can list, get, set, and unset bindings in a `.env` file, and so they can run another program with those bindings present in that program’s environment.

This document specifies **user- and integrator-observable behavior only**. Exact published symbol names, import paths, call spellings, and output forms belong in the Interface Contract, not here. Every feature point below corresponds to behavior that exists in the finished python-envfile product. Feature points are ordered so foundational capabilities come first; a later feature point may refine an earlier one only when it says so explicitly.

## Terminology

| Term | Meaning in this PRD |
| --- | --- |
| **`.env` file** | A text file of environment bindings. The default file name is `.env`. The product also reads the same format from an in-memory text stream, and on Unix from a FIFO (named pipe) in place of a regular file. |
| **Binding** | One recognized name, with either a text value, an empty string, or no value. |
| **Name / key** | The left-hand side of a binding. |
| **Value** | The right-hand side of a binding after quoting and escapes are applied. Distinct from **no value** (a name with no equals sign) and from the **empty string** (a name followed by an equals sign and nothing else). |
| **Process environment** | The environment mapping of the running Python process. Load writes here. The mapping-without-mutation entry does not. |
| **Load** | Parse a `.env` source and write recognized values into the process environment. |
| **Values mapping** | Parse a `.env` source and return the bindings as a mapping, without writing them into the process environment. |
| **Override** | When on, a value from the `.env` source replaces a name that is already in the process environment. When off, an already-present process-environment name is left unchanged. |
| **Expansion** | Replacing `${NAME}` and `${NAME:-default}` inside a value with another binding’s value, a process-environment value, the given default, or empty text. Bare `$NAME` (no braces) is not expansion. Specified in FP-05. |
| **`envfile`** | The command-line program shipped with python-envfile. Also reachable as a Python module invocation of the installed package. |
| **Quote mode** | How `envfile set` (and the library write entry) writes values: `always`, `never`, or `auto`. |
| **List format** | How `envfile list` prints bindings: `simple`, `json`, `shell`, or `export`. |
| **Diagnostic** | A human-readable report the library emits without aborting the caller (its channel and form are in the Interface Contract). |

## Public surface inventory

python-envfile is a **library** with an optional **command-line program**. Integrators reach the library by installing the python-envfile package. Operators reach the CLI by installing python-envfile with the `cli` extra (the CLI depends on a third-party command-line library declared by that extra).

The public surfaces, grouped the way the feature points below describe them, are:

- The `.env` file format: names, values, quoting, escapes, comments, `export`, multiline quoted values, empty versus missing values, UTF-8 byte-order mark, Unix FIFOs, and in-memory streams (FP-01).
- Locating a `.env` file by walking from a starting directory up to the filesystem root (FP-02).
- Loading recognized values into the process environment, including the default “do not override” policy, an explicit override, a dedicated disable switch, and streams (FP-03).
- Parsing the same sources into a mapping without mutating the process environment (FP-04).
- POSIX-style `${NAME}` / `${NAME:-default}` expansion, including the different resolution order used when override is on versus off (FP-05).
- Reading, writing, and deleting a named binding in a `.env` file, including quote modes, an optional `export` prefix, and the default of not following symbolic links (FP-06).
- The `envfile` command’s list / get / set / unset subcommands and global file, quote, export, and version flags (FP-07).
- The `envfile run` subcommand, which starts another program with `.env` values in that program’s environment (FP-08).

Feature points below group these entries by capability. They do not invent additional product surfaces.

## Non-functional constraints

- **Form factor:** A pure-Python library. No compiled extensions, native code, GPU, or accelerator are required or claimed.
- **Layout.** The importable package directory is `envfile` under `src`.
- **Language:** Python 3.10 or newer, including the CPython and PyPy implementations.
- **Platforms:** Intended to work on Linux, macOS, and Windows. Unix FIFOs are a Unix-only source.
- **Hardware:** CPU-only.
- **Default file name:** `.env`.
- **Default load policy:** Do not override names already present in the process environment.
- **Default CLI file:** `.env` in the current working directory.
- **Default CLI quote mode:** `always`.
- **Default CLI list format:** `simple`.
- **Character encoding:** Unless the caller names a different encoding, `.env` files are read and written as UTF-8.
- **CLI extra:** The `envfile` program requires the `cli` extra. Without that extra, invoking the program does not run subcommands.

## Non-goals

- Being a general-purpose configuration framework (typed settings objects, layered YAML/TOML, remote secret stores). python-envfile reads `.env` text and optionally writes the process environment.
- Shipping a web server, GUI, or cloud control plane.
- The IPython line magic (`%envfile`). That integration exists so a notebook can load a `.env` file; it is not a feature point below.
- The helper that renders a `envfile …` shell string for remote task runners.
- Guaranteeing a particular parse throughput.
- Formal compatibility with every Bash or POSIX shell quirk. The format is similar to Bash and is specified by FP-01 and FP-05, not by a shell standard.

---

## Feature points

### FP-01: `.env` file format

**Public entry:** Any python-envfile parse of a `.env` file, FIFO, or in-memory text stream — the load entry (FP-03), the values-mapping entry (FP-04), the file read/write entries (FP-06), and the `envfile` command (FP-07, FP-08). This feature point is the shared format those entries consume. Expansion of `${…}` inside values is specified in FP-05; until expansion runs, a dollar-brace sequence is ordinary text in the parsed value.

**Normal behavior:**

- A source is a sequence of lines. A line ends at a line feed, a carriage return, or a carriage-return/line-feed pair; all three separate bindings equally. A leading UTF-8 byte-order mark is not part of the source text.
- Whitespace (including empty lines) before a binding is skipped. A blank line is never a binding.
- A line whose first non-whitespace character is `#` is a comment and contributes nothing.
- A binding line has, in order: an optional `export` directive, a name, optional spaces or tabs, then optionally an equals sign followed by optional spaces or tabs and a value, then an optional comment, then the end of the line.
- **`export` directive:** the word `export` followed by at least one space or tab, at the start of the line (after leading whitespace). It is not part of the name and does not change how the rest of the line is read.
- **Names** are unquoted or single-quoted. An unquoted name is a run of one or more characters other than `=`, `#`, and whitespace; every other character is part of it. A single-quoted name is one or more characters other than a single quote between two single quotes; the quotes are not part of the name.
- **No value versus empty string:** a name with no equals sign is a binding with **no value**. A name followed by an equals sign and then only spaces or tabs up to the end of the line has the **empty string** as its value. No value, empty string, and absence of the name are three distinct outcomes.
- **Unquoted values** run from the first character after the equals sign and the spaces or tabs after it, to the end of the line. Within that text, everything from the first `#` that is preceded by whitespace (space or tab) is a comment and is removed; then trailing whitespace is removed. Interior whitespace, including tabs, is kept. A `#` not preceded by whitespace is value text.
- **Quoted values** start with a single or double quote right after the equals sign (and optional spaces or tabs) and end at the next quote of the same kind that is not preceded by a backslash. Everything between the quotes is kept, including leading, interior and trailing whitespace, `#`, and real line breaks, so a quoted value may span several lines. Text that looks like a binding inside a still-open quoted value is value text. After the closing quote only spaces or tabs, an optional comment, and the end of the line may follow.
- A comment that follows a no-value name or the closing quote of a quoted value starts at `#`, with or without whitespace before it.
- **Single-quoted escapes:** a backslash followed by a backslash is one backslash; a backslash followed by a single quote is a single quote. Every other backslash in a single-quoted value is an ordinary character.
- **Double-quoted escapes:** a backslash followed by a backslash, a single quote, a double quote, or one of the letters `a`, `b`, `f`, `n`, `r`, `t`, `v` decodes to the single character that escape denotes in C and Python string literals (backslash, single quote, double quote, bell, backspace, form feed, line feed, carriage return, horizontal tab, vertical tab). A backslash followed by any other character is not an escape: the backslash and that character are both kept as written, and the text around them is unchanged.
- Characters outside ASCII, in names and in values, are preserved unchanged.
- When the same name is bound more than once in one source, the last binding is the one recorded.
- On Unix, a FIFO (named pipe) whose contents are bindings in this format is a valid `.env` source for load and for file location (FP-02, FP-03), read the same way as a regular file of the same text. An in-memory text stream and a UTF-8 file of the same text also yield the same bindings.

**Boundary / error behavior:**

- A line that does not have the binding shape above contributes no name, and the rest of that line is skipped; parsing resumes at the next line, where later valid bindings are still recognized. An opening quote with no matching closing quote later in the source makes only its own line invalid.
- An empty source, a source of only blank lines, or a source of only comments yields no bindings.
- An empty-string value is not an error.

---

### FP-02: Locate a `.env` file by walking ancestors

**Public entry:** The library’s file-location entry, and the default of the load entry and the values-mapping entry when the caller supplies neither a path nor a stream (FP-03, FP-04). The caller may name a file other than `.env`. The `envfile` command does **not** walk ancestors: it uses `.env` in the current working directory unless `--file` names another path (FP-07).

**Normal behavior:**

- Location walks from a starting directory toward the filesystem root, one parent at a time, and returns the first path that is a regular file or (on Unix) a FIFO whose base name is the requested name (default `.env`). A nearer match wins over a farther one. A directory with that name is not a match.
- In ordinary script execution (the main program is a script file, the session is not an interactive interpreter, no debugger is attached, and the process is not a frozen packaged executable), the starting directory is the directory that contains the file of the nearest calling code whose file exists on disk, not the process working directory. Calling code whose file does not exist on disk is passed over in favor of the next caller up the call chain.
- When the caller asks to start from the working directory, when the session is an interactive interpreter (including a session whose main program has no script file path), when a debugger is attached, or when the process is a frozen packaged executable, the starting directory is the current working directory.
- When a matching file exists, the result is the path to that file. When none exists after walking to the root, the result is empty text (no path), unless the caller asked to fail if not found, in which case the operation does not succeed and no path is delivered. A match is returned in both modes.
- A custom file name is searched under that name only.

**Boundary / error behavior:**

- When the start is the working directory and that directory no longer exists, location does not succeed.

---

### FP-03: Load `.env` values into the process environment

**Public entry:** The library’s load entry. The caller may pass a file path, an in-memory text stream, or neither (in which case FP-02 locates a `.env` file). The IPython magic, when used, calls this same load (see Non-goals). The `envfile run` command applies values to a **child** process and is specified in FP-08; it does not replace this entry.

**Normal behavior:**

- **Source selection** (shared with FP-04): if a path is given and names an existing regular file or Unix FIFO (an empty file included), that path is the source, even when a stream is also given. Otherwise, if a stream is given, the stream is the source (an empty stream included). Otherwise, if a path was given, the source is empty: a given path never falls back to location. Only when neither a path nor a stream is given is a file located with FP-02’s default parameters; if none is found the source is empty.
- Load writes every recognized name that has a value (including the empty string) into the process environment. A name with **no value** is not written.
- By default, load does **not** override: a name already present in the process environment keeps its value, and names not yet present are still written. When the caller asks to override, the source’s values replace present names.
- When the caller names an encoding, a file or FIFO source is decoded with that encoding.
- Load reports **success** when the source produced at least one recognized name, even if every name was left unchanged because override was off, and even if the only names had no value. Load reports **failure** when the source produced no recognized names (no source found, missing path, empty source, comments only) or when loading is disabled. Neither outcome aborts the caller.
- When the caller asks for extra reporting and no source was selected (a given path that is not an existing file with no stream, or location that found nothing), load emits a diagnostic that the configuration file was not found, naming that path. Without extra reporting it emits no diagnostic for that case.
- When expansion is left on (the default), the strings written are the expanded strings of FP-05. Turning expansion off leaves dollar-brace text literal.

**Disable switch:**

- When the process environment already contains `PYTHON_ENVFILE_DISABLED` with a value that, after folding letter case, is one of `1`, `true`, `t`, `yes`, or `y`, load does **not** read the file or stream and does **not** write any names from that source. It reports failure. The process environment is left as it was (including the disable variable itself). This holds for both a file path and a stream.
- Any other value of that variable, or its absence, leaves loading enabled.
- Only a disable variable already present in the process environment before the load turns loading off. A binding of that name inside the source being loaded is an ordinary binding and does not gate that load.
- The values-mapping entry (FP-04) is not gated by this switch.

**Boundary / error behavior:**

- A path that does not exist: load reports failure, writes nothing, and the call completes.
- A source whose parsed mapping is empty reports failure.

---

### FP-04: Read `.env` bindings as a mapping without mutating the process environment

**Public entry:** The library’s values-mapping entry. The caller may pass a file path, a stream, or neither (FP-02 locates a `.env` file). Source selection and encoding follow FP-03.

**Normal behavior:**

- The mapping holds every recognized name of the one selected source, with its value, the empty string, or a no-value marker distinct from both the empty string and absence. A name that is not a recognized binding is absent.
- The process environment is not modified: a name that was absent stays absent; a name that was present keeps its previous value.
- An empty or missing source yields an empty mapping. The call completes.
- One call returns one source’s bindings; combining several files is left to the caller.
- Expansion, when left on (the default), uses the override-on resolution order in FP-05. Turning expansion off leaves dollar-brace text literal.

**Boundary / error behavior:**

- A missing path yields an empty mapping; the caller is not aborted and no other file is located.
- The disable switch in FP-03 does not apply to this entry: bindings and expansion are the same whether it is set or not, and the process environment is still not written.

---

### FP-05: Variable expansion

**Public entry:** The load entry (FP-03) and the values-mapping entry (FP-04), both of which expand by default. The caller can turn expansion off on either entry. **This feature point refines FP-03 and FP-04:** when expansion is on, the values those entries apply or return are the expanded strings specified here, not the raw parsed text.

**Normal behavior:**

- Only the braced forms are expanded: a dollar sign, an opening brace, a name (any characters other than `}` and `:`), and a closing brace (`${NAME}`), optionally with a default introduced by `:-` before the closing brace (`${NAME:-default}`, the default being any characters other than `}`). Bare `$NAME` without braces is ordinary text whether expansion is on or off.
- Each reference is replaced in place; text around it is kept, and several references (including repeats of the same name) in one value are each replaced. The replacement text is not expanded again.
- Expansion applies to the value after quoting and escapes, whatever the quote kind: quotes do **not** suppress expansion (unlike Bash single quotes).
- A reference resolves to the first of these that is **defined**, in the order given below: a binding of that name that appears **earlier** in the same source (its own expanded value), the process environment, the written default, and finally empty text. A name is defined when it is present, even with the empty string as value; the default is used only when the name is absent from both the earlier bindings and the process environment. A name bound earlier with **no value** is defined and resolves to empty text.
- **Resolution order when override is on** (the values-mapping entry, and load when the caller asked to override): earlier binding in the source, then process environment, then default, then empty text.
- **Resolution order when override is off** (load’s default): process environment, then earlier binding in the source, then default, then empty text. Together with FP-03’s no-override rule, the process environment then wins both the write of a name and the expansion of references to it.
- A binding that appears later in the source, and the binding currently being defined, are never “earlier” bindings: a self-reference resolves through the process environment, the default, or empty text.
- A binding with no value is not expanded (it stays no-value in the mapping; load still does not write it).

**Boundary / error behavior:**

- Expansion off: every dollar-brace sequence is returned or written literally, including the default form, even when the name is set.
- An unknown name without a default becomes empty text, not a failure and not the raw reference.

---

### FP-06: Get, set, and unset a binding in a `.env` file

**Public entry:** The library’s three file-editing entries: read one name, write one name, and delete one name. The `envfile` command’s `get` / `set` / `unset` subcommands (FP-07) use this same behavior; CLI output and exit status are specified there. Quote modes and the `export` prefix apply to write.

**Normal behavior:**

- **Read** of a present name with a text value (including the empty string) returns that value as FP-01 parses it. A name with no value, a name absent from an existing file, and a path that does not exist all return the no-value outcome, which is distinct from the empty string. A missing name emits a key-not-found diagnostic naming the key; a missing path emits a configuration-file-not-found diagnostic naming the path, and the key-not-found diagnostic. A present name emits neither.
- **Write** stores the binding as one line in the file, creating the file if the path does not exist, and reports success. A later read of that name returns the written value, and a parse of the file sees it.
- **Quote mode** is one of `always`, `never`, or `auto` (default `always`):
  - `always`: the value is stored single-quoted, with every single quote inside it preceded by a backslash, so that FP-01 reads back exactly the written value.
  - `never`: the value is stored as given, without added quotes.
  - `auto`: a non-empty value made only of letters and digits is stored as under `never`; any other value is stored as under `always`.
- With `export` on, the stored line starts with the `export` directive; with it off (the default), it does not.
- Writing a name that already has bindings replaces each line that binds that name with the new line, in place. The text of every other binding, comment and invalid line is kept byte for byte, as are blank lines that follow the replaced binding (blank lines directly before it may be dropped). When the name is not yet present, the new line is appended at the end; if the existing text does not end with a line break, one is added first so the new binding starts on its own line. Every stored line ends with a line break.
- **Delete** of a present name removes each line that binds it (a no-value line included) and keeps the rest of the text as write does; a later read returns the no-value outcome.
- When the caller names an encoding, read, write and delete decode and encode the file with it.
- On Unix, rewriting an existing regular file keeps that file’s permission bits. When a new regular file must be created, or when the path was not a regular file (including the default handling of a symbolic link, below), the new file has owner read/write permission only.

**Symbolic links (default: do not follow):**

- By default, write and delete do **not** follow a symbolic link at the path: the result is stored in a new regular file that replaces the link, and the link’s target is left unchanged. The new content is computed from the target’s current content when the target exists.
- If the link’s target does not exist, write creates a regular file at the path and does not create the target; delete does not succeed and leaves the link in place.
- When the caller asks to follow symbolic links, write and delete modify the target file and leave the link in place.

**Boundary / error behavior:**

- A quote mode other than `always`, `never`, or `auto` is refused before anything is written: an existing file is unchanged and a missing path is not created.
- Delete of a path that does not exist does not succeed, does not create the file, and emits a diagnostic, naming the path, that it does not exist.
- Delete of a name that is not in an existing file (including one already deleted) does not succeed, leaves the file unchanged, and emits a diagnostic, naming the key, that it was not removed.
- None of these outcomes aborts the caller except the refused quote mode, which may.

---

### FP-07: `envfile` command — list, get, set, and unset

**Public entry:** The `envfile` command-line program, also reachable as a Python module invocation of the installed package. Global options apply to every subcommand: the file path (default `.env` in the current working directory), the quote mode (default `always`), whether written lines carry the `export` directive (default off), and a version flag. Subcommands specified here: `list`, `get`, `set`, `unset`. `run` is FP-08.

Installing python-envfile **without** the `cli` extra leaves this program unable to run subcommands: it runs none, reports (the same way for every subcommand) that python-envfile was not installed with the `cli` extra, naming that extra, and exits unsuccessfully. With the extra present, the subcommands below run.

**Normal behavior:**

- `list` and `get` read the selected file with FP-04’s values-mapping rules (expansion on). They never walk ancestors.
- **`set NAME VALUE`** writes that binding with FP-06 (creating the file if needed) under the chosen quote mode and export flag, then reports the requested name and value (not the quoted on-disk form) and exits successfully.
- **`get NAME`** prints the stored value and exits successfully when the name is present with a non-empty value.
- **`unset NAME`** removes the binding with FP-06, confirms the removal in one line naming the removed name, and exits successfully.
- **`list`** shows every name of the file in sorted name order in the selected list format (default `simple`). In `simple`, values are shown as parsed, without added quotes. In `shell` and `export`, each value is quoted so that pasting the line into a POSIX shell assigns exactly that value. In `json`, names with no value are present with a null; in the other three formats they are omitted. A name whose value is the empty string is not a no-value name: it is shown in every format, with the empty string as its value.
- The version flag shows the installed python-envfile version and exits successfully without running any subcommand, including when it appears before `run`. A version flag that belongs to the **child** command after `run` is not this flag (FP-08).

**Boundary / error behavior:**

- `list` or `get` against a path that cannot be opened as a file fails with the usage-style failure class and a report that the env file could not be opened, naming the path. This report is not a usage message: it is distinct from the report for a missing argument.
- `get` of a name that is missing from an existing file, has no value, or whose value is the empty string exits with the missing-key failure class and no output. The missing-key class differs from the usage-style class.
- `unset` of a name missing from an existing file exits unsuccessfully and leaves the file unchanged.
- `set` without both a name and a value is a usage failure (missing argument).
- `set` and `unset` use FP-06’s default of not following symbolic links.

---

### FP-08: `envfile run` — run a program with `.env` values in its environment

**Public entry:** The `envfile run` subcommand of the `envfile` program (FP-07). The global file option selects the `.env` file. This entry starts another program with the selected bindings in that program’s environment. It is not the load entry (FP-03): it does not write those names into the calling process’s environment.

**Normal behavior:**

- The child receives the inherited environment plus every binding of the selected file that has a value (values as FP-04 returns them). Names with no value are not passed.
- By default, file values **override** names already present in the inherited environment. With `--no-override`, inherited names keep their inherited values; `--override` restores the default.
- Every token after `run` (after `run`’s own override options, and after an optional `--` separator, which is not passed on) belongs to the child command line, including tokens that look like `envfile` options. A version flag placed before `run` is `envfile`’s own (FP-07) and no child starts.
- The child’s standard output reaches the operator, and `envfile`’s exit status is the child’s exit status.

**Boundary / error behavior:**

- If the selected path is not an existing regular file, `run` fails as an invalid file option (usage-style failure, naming the path) before anything else is checked, and starts no child.
- If the file exists but no child command is given, `run` reports that no command was given and exits unsuccessfully.
- If the file exists and the child program cannot be found, `run` reports that the command was not found, naming the program, and exits unsuccessfully.
- `run` never creates a `.env` file.

---

## Information completeness notes

- **Quote modes (finite):** `always`, `never`, `auto`.
- **List formats (finite):** `simple`, `json`, `shell`, `export`.
- **Disable-switch truthy values (finite, after folding letter case):** `1`, `true`, `t`, `yes`, `y`. Any other value leaves loading enabled.
- **Default file name:** `.env`. **CLI default path:** `.env` in the current working directory.
- **Load default:** override off. **`envfile run` default:** override on. Those two defaults differ.
- **Expansion forms (finite):** `${NAME}` and `${NAME:-default}`. Bare `$NAME` is not expanded.
- **Single-quote escapes (finite):** `\\`, `\'`. **Double-quote escapes (finite):** `\\`, `\'`, `\"`, `\a`, `\b`, `\f`, `\n`, `\r`, `\t`, `\v`.
- **CLI extra name:** `cli` (install as `python-envfile[cli]`).
