# Interface Contract

## Product overview

**`prosecheck`** is a local detector for AI-writing patterns. It is a command-line tool and an agent plugin. There is no website and no hosted version. Nothing the user writes is uploaded; there is no account; no text leaves the machine.

A first-time user installs the `prosecheck` plugin into a coding agent, restarts, and runs `/prosecheck doctor`. When the install is sound and the tool is on, the doctor answers with four successful-check lines. From then on, two layers work together. A writing contract is placed in the session (and into any subagent) so prose deliverables are shaped as they are written. After a supported file-edit tool saves a prose file, a saved-file guard scores the scan-window prefix of extracted prose (the window the PRD states) against the PRD's catalogue of documented patterns and, when the score is above the active threshold, names the flagged spans and asks for them to be fixed. The same detector can be run by hand on a file path or on standard input.

The finished product is a **Python standard-library detector command** plus **Node.js plugin hooks**. There is no installable Python package, no compiled extension, and no runtime third-party dependency. The detector needs Python 3.9 or newer. The plugin’s saved-file and command hooks need Node.js. Analysis is local: the runtime contains no network client and no telemetry. There is no model and no random component in the default scan. Prose only, never code.

The score is a triage heuristic on the writing in front of the detector, not a calibrated authorship classifier. A score, a band, and a hook phrase describe prose; they do not name a person or a model as the author.

Exact argv spellings of detector switches, the report's member names, per-hook JSON field names, and per-subcommand reply shapes belong with those symbols in the entries below (`scripts/detect.py`, the hook entries, and the `/prosecheck` subcommands).

**Layout.** Callers do not import a Python module to reach the product. They spawn the host Python interpreter against `scripts/detect.py`, and they fire plugin hooks by spawning Node against the shipped files under `hooks/`. When a hook runs the detector, it finds the host Python interpreter by looking up the names `python3`, `python`, and `py` on the `PATH` it was given, not by a fixed absolute path; the order in which it tries those names is free.

## Shape of the public surface

The public surfaces are a **command-line detector** and a companion **agent plugin**. There is no network service and no wire protocol of the product’s own.

**Detector command.** Invocation is the host Python interpreter followed by `scripts/detect.py`, then optional switches and at most one file operand. A file path or empty argv (standard input) in; a structured report, scrubbed text, a usage message, or a structured error out.

- Readable non-empty extracted prose prints a structured report on standard output and exits 0. The report has two kinds of content: **findings** and **metrics**. The report is one JSON object whose members are stated under `scripts/detect.py` below.
- No path means the detector reads standard input. Standard input and standard output use UTF-8. A leading UTF-8 byte-order mark is not part of the prose. UTF-16 with a byte-order mark is decoded as text. A buffer that is not UTF-16 and contains a NUL byte is not text.
- Optional switches: `--clean` (cleanup: prints scrubbed text instead of the report) and `--ci` (resampled interval: adds a low/high interval on the score when the document has enough sentences). The end-of-options token `--` stops option parsing so a file name may begin with a dash.
- `--help`, or its short alias `-h`, prints the usage message to standard output and exits 0. The usage message's first line is exactly `usage: detect.py [--clean] [--ci] [--] [FILE]`; every later line is free text, the implementer's choice.
- Cleanup of document files prints extracted plain text, not a rebuilt archive. Redirecting that output onto the original path would replace the document with loose text.

**Twenty supported formats.** Plain text: `.md`, `.mdx`, `.markdown`, `.txt`, `.text`, `.rst`, `.tex`, `.org`, `.adoc`. Zip-based documents: `.docx`, `.docm`, `.pptx`, `.pptm`, `.xlsx`, `.xlsm`, `.odt`, `.odp`, `.ods`, `.epub`. Notebook: `.ipynb`. Plain text, and zip-based documents with notebooks, each have the size cap the PRD states (file size on disk, in binary units, enforced by the plugin). The detector command itself reads a path it is given. `.pdf` and `.rtf` are not among the twenty; they yield no extracted prose. How prose is extracted from each format is the PRD’s rule (FP-02).

**Plugin hooks.** Host events send JSON on standard input. Named entries and the shipped files under `hooks/`:

- session-start — `prosecheck-activate.js`
- prompt-submit — `prosecheck-tracker.js`
- subagent-start — `prosecheck-subagent.js`
- post-tool-use — `prosecheck-guard.js`
- stats — `prosecheck-stats.js`

The prompt-submit hook is also the `/prosecheck` command router. A marketplace install namespaces the command as `/prosecheck:prosecheck`; both forms behave the same. When the doctor's closing line points at `show`, when that closing line points at turning the tool on, and when `init` replies that it is switched off, that follow-up uses the form the user typed. The help list, the mode line's pointer at `on`, and the doctor's request to run `doctor` again after a fault keep the non-namespaced spelling `/prosecheck`. Subcommands are exactly: `lite`, `full`, `strict`, `off`, `on`, `status`, `show`, `check`, `doctor`, `stats`, `init`, `help`. A bare `/prosecheck` (or `/prosecheck:prosecheck`) is help.

**Exported contract files.** `/prosecheck init` writes the writing contract into `AGENTS.md` in the current working directory and copies the shipped Cursor rule to `.cursor/rules/prosecheck.mdc` when that file does not yet exist. The Cursor rule’s front matter limits it to prose globs (`*.md`, `*.mdx`, `*.markdown`, `*.txt`, `*.rst`, `*.tex`, `*.org`, `*.adoc`) and does not include `*.py`, `*.js`, `*.ts`, or `*.json`.

**Not in this surface.** A website, account, or hosted API. An installable Python distribution. A compiled native extension. Rewriting a `.docx`, `.epub`, `.odt`, or `.ipynb` in place when cleanup is requested. The bundled skill’s rewrite instructions as a detector obligation. The recorded-session demo, the documentation checker, the bundled evaluation script, and the status-line helper.

## Naming conventions

**Product.** The product identity is `prosecheck`. The detector script path from the working-directory root is `scripts/detect.py`. Plugin hooks live under `hooks/` with the filenames listed above.

**Bands.** Five named ranges of the 0–100 score, each describing the prose, never an author: `clean`, `light tells`, `mixed`, `heavy tells`, `pervasive tells`, in rising order of score. The range each band covers is the PRD's.

**Hook phrases.** The plugin’s plain-language rendering of a band: `reads clean`, `reads mostly clean`, `reads with some AI tells`, `reads with heavy AI tells`, `reads with pervasive AI tells`. User-visible phrases use “reads …” rather than “was written by …”.

**Confidence.** Closed set: `none`, `low`, `moderate`, `high`. When confidence is not `high`, metrics carry a reason a caller can read (`confidence_reason`, under `scripts/detect.py`). Wording of that reason is free text, the implementer's choice.

**Operating level.** The one-word mode stored for the install: `lite`, `full`, `strict`, or `off`. Which level applies when nothing valid is stored is the PRD’s rule (FP-04); the environment may supply one of those four words as `PROSECHECK_DEFAULT_MODE`.

**Catalogue.** The documented patterns are numbered from 1 as the PRD's catalogue numbers them. When a machine-checked pattern fires, its finding is keyed by that catalogue number (the key form is under `scripts/detect.py`); the finding's label wording is free text, the implementer's choice. Which numbers have no detector, and which are writing advice that does not move the score, is the PRD's.

**Host environment.** Each variable below governs exactly the behaviours listed; nothing else reads it.

- `CLAUDE_CONFIG_DIR` — the plugin config directory: where the level flag and the session ledgers are read and written, and whose `projects` folder `stats` searches. Unset: the `.claude` folder in the user's home directory.
- `CLAUDE_PLUGIN_ROOT` — the plugin root. Set: the directory it names is the plugin root, whether or not that directory holds the `hooks/` files. Unset: the directory that contains the running hook's `hooks/` directory. The plugin root governs (a) where the hooks look for the bundled detector — `scripts/detect.py` under the plugin root, else `skills/prosecheck/scripts/detect.py` under it — and therefore what the doctor's detector check reports; (b) the post-tool-use skip rule for files that live inside the plugin's own install tree, which is the plugin root; (c) where `init` looks for the shipped Cursor rule (`.cursor/rules/prosecheck.mdc` under the plugin root). The hooks themselves run from wherever the host started them.
- `PROSECHECK_DEFAULT_MODE` — a level word (`lite`, `full`, `strict`, or `off`) the environment may supply; when it applies is the PRD’s rule (FP-04).

**Config filenames** under the plugin config directory: the one-word level flag `.prosecheck-active`; session ledger files whose names are `.prosecheck-ledger` or start with that prefix followed by a hyphen.

## Global observables an implementer must reproduce

**Process exits (detector).**

- Readable non-empty extracted prose, help that prints usage, cleanup that prints scrubbed text, and a two-or-more-file run that still scans the first file: exit 0.
- Empty extracted prose, from any source (PRD FP-01): exit 1, the `empty input` error object on the error stream, no traceback, and nothing on standard output.
- An unreadable path, or a file whose extension is a supported archive type but whose bytes are not a readable zip: exit 1, the `cannot read input:` error object, no traceback, nothing on standard output.
- An unknown option: exit 2, the unknown-option error object, no traceback, nothing on standard output.

The error objects are stated under `scripts/detect.py`.

**Streams and encoding.**

- Standard input and standard output are UTF-8. A successful report’s standard output decodes as UTF-8.
- Failure does not print a traceback or other multi-frame dump on the error stream.
- Two or more file operands: the first file is scanned (exit 0, its report on standard output), and the error stream carries the multi-file notice stated under `scripts/detect.py`.

**Structured success report.** A successful scan prints the report object stated under `scripts/detect.py`: one member per fired finding and the `_metrics` member. Which findings fire, the window they are computed on, the band a score falls in, and when the interval is a pair are the PRD’s rules (FP-01).

**Cleanup output.** With the cleanup switch, standard output is the scrubbed text, not the structured report, and the process exits 0 (form under `scripts/detect.py`).

**Plugin config and ledger.**

- The one-word level is stored as `.prosecheck-active` under `CLAUDE_CONFIG_DIR`. Its content is exactly one of `lite`, `full`, `strict`, and `off`.
- Session ledgers are files under `CLAUDE_CONFIG_DIR` named as stated under Config filenames. What a ledger records, how long it is kept, and its file permissions are the PRD’s rules (FP-05, FP-06, non-functional constraints).
- Every hook process exits 0.

## `scripts/detect.py`

The detector command. Callers run it with the host Python interpreter from the plugin root.

### Signature

```
python3 scripts/detect.py [--clean] [--ci] [--] [FILE]
python3 scripts/detect.py --help
python3 scripts/detect.py -h
```

`FILE` is one path operand; with no operand the detector reads standard input. `--clean` is the cleanup switch, `--ci` the interval switch, `--` ends option parsing. Any other argument that begins with `-` before `--` is an unknown option. Switch order is free.

### Usage

`--help` and `-h` write the usage message to standard output and exit 0. Its first line is exactly:

```
usage: detect.py [--clean] [--ci] [--] [FILE]
```

Every later line is free text, the implementer's choice.

### Report

On success standard output is exactly one JSON object (indentation and member order free) and the exit status is 0.

```
{
  "<N>_<slug>": {
    "label": string,
    "count": integer,
    "samples": [string, ...]
  },
  ...,
  "_metrics": {
    "scanned_chars": integer,
    "truncated": boolean,
    "ai_tell_score": integer,
    "ai_tell_band": string,
    "confidence": string,
    "confidence_reason": string,
    "patterns_flagged": integer,
    "invisible_chars": integer,
    "nonstandard_spaces": integer,
    "homoglyphs": integer,
    "score_ci": [number, number] | null,
    "score_ci_note": string,
    ...
  }
}
```

**Findings.** Every top-level member other than `_metrics` is one fired finding. Its key is `<N>_<slug>`: `<N>` is the catalogue number in decimal without leading zeros, then one underscore, then a slug (free text, the implementer's choice). Several members may share one catalogue number; their slugs are free, except for catalogue 17, whose two forms are reported as separate members keyed exactly `17_negative_parallelism` (the parallelism form) and `17_tailing_negation` (the tailing-negation form). Both may appear in one report. `label` is the human-readable title of that pattern (wording free). `count` is the hit count, a positive integer. `samples` is an array of at most three short strings. A sample of a catalogue-1 (AI vocabulary) finding is a contiguous excerpt of the scanned text: line breaks may appear as spaces, and either end may carry `...` or `…` to mark a cut. Samples of every other kind are free text, the implementer's choice. Two different catalogue numbers never carry the same `label`.

**Metrics.** `_metrics` is always present.

- `scanned_chars`: the number of characters of extracted prose that were scanned (never more than the scan window).
- `truncated`: `false` when the extracted prose is not longer than the scan window, `true` when it is longer.
- `ai_tell_score`: the integer score, 0 through 100.
- `ai_tell_band`: the band name of that score, one of the five band names.
- `confidence`: one of `none`, `low`, `moderate`, `high`.
- `confidence_reason`: a readable non-empty reason when `confidence` is not `high`; when it is `high` the value is free (an empty string is fine). Wording free.
- `patterns_flagged`: the number of finding members in this report.
- `invisible_chars`, `nonstandard_spaces`, `homoglyphs`: the character-layer counts of invisible / zero-width characters, non-standard spaces, and mixed-script lookalikes in the scanned text.
- `score_ci`: present only when `--ci` was given. A two-element array `[low, high]` of numbers from 0 through 100, `low` not above `high`, when the document has enough sentences for an interval (the PRD's minimum); `null` when it has too few. `score_ci_note`, present with it, is free text, the implementer's choice.

Any other member of `_metrics` is free (the implementer's choice).

### Cleanup output

With `--clean`, standard output is the scrubbed text itself (no JSON, no label) and the exit status is 0.

### Errors

On failure standard output is empty, and the last non-empty line of standard error is one JSON object `{"error": string}`. No traceback.

| Condition | Exit | `error` value |
| --- | --- | --- |
| Empty extracted prose | 1 | exactly `empty input` |
| Unreadable path; archive extension whose bytes are not a readable zip | 1 | begins with `cannot read input:`; the rest is free text |
| Unknown option | 2 | contains `unknown option`, the option exactly as typed, and `--help`; the rest is free text |

### Several file operands

With two or more operands the first is scanned and its report printed (exit 0). Standard error carries one notice line that contains the first operand exactly as given; the rest of that line is free text. That line is not a JSON object. A run with a single operand prints no such line.

## `hooks/prosecheck-activate.js`

The session-start hook.

### Signature

```
node hooks/prosecheck-activate.js   < host JSON object on standard input
```

The hook exits 0. Malformed or empty standard input is treated as an empty object.

### Output

Standard output is plain text, not JSON.

- Stored level `off`: standard output is empty.
- Any other level: the writing contract for that level. On the first start of an install whose level flag can be written, the welcome block comes first, then the writing contract. A later start, or a start whose flag cannot be written, prints only the writing contract.

**Welcome block.** Free text that names each of these, in any order: the number of documented patterns, the plain-text cap and the archive cap, and the scan window, as the PRD gives them; and the four commands written exactly `/prosecheck doctor`, `/prosecheck check`, `/prosecheck off`, `/prosecheck help`. Numbers are written as standalone decimal integers (the window may be grouped with commas); the plain-text cap is written in kilobytes and the archive cap as the digit followed by `MB` (a space between them is optional). A delivery without the welcome names none of those facts.

**Writing contract.** Its content is the PRD's. Its shell parts:

- Every word of the PRD's banned-vocabulary list appears as a standalone word.
- Wherever the text names `source code` (any letter case; the two words joined by a space or a hyphen), the standalone word `never` or `not` (any letter case) comes earlier in the same sentence. A sentence ends at `.`, `!`, `?`, or a line break.
- At `full`: the full-level target score appears as a standalone integer, together with the band word `clean` or the band name `light tells`. The text does not contain `--clean`.
- At `strict`: the strict-level target score appears as a standalone integer; the band word `clean` appears apart from the switch spelling; and the text asks for a finish through `--clean`, written exactly so.
- At `lite`: neither the full-level target integer nor `light tells` appears.
- A live delivery may name this machine's detector path; that path is free text, the implementer's choice.

## `hooks/prosecheck-subagent.js`

The subagent-start hook. Exits 0; malformed input is an empty object.

- Stored level `off`: standard output is empty.
- Any other level: standard output is one JSON object:

```
{
  "hookSpecificOutput": {
    "hookEventName": "SubagentStart",
    "additionalContext": string
  }
}
```

`additionalContext` is the writing contract for the stored level, with the same shell parts as under `hooks/prosecheck-activate.js`. No other member is read.

## Post-tool-use reply

Output of the post-tool-use hook (`prosecheck-guard.js`). The process always exits successfully.

When no saved file is flagged (which saves are scored and which are flagged is the PRD’s rule, FP-05), standard output is empty.

When a file is flagged, standard output is one JSON object:

```
{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": string
  }
}
```

Other members of either object are free (the implementer's choice).

`additionalContext` holds one line per flagged file:

```
prosecheck: <base> <phrase> (score <score>, band <band><coverage>). Flagged: <labels>. <ask>
```

- `<base>` is the file's base name; `<phrase>` is the hook phrase for `<band>`; `<score>` is the detector's integer score; `<band>` is the detector's band name.
- `<coverage>` is exactly `, first <window> characters only`, with `<window>` the PRD’s scan window written with a thousands comma, when extracted prose is longer than the scan window, and empty otherwise.
- `<labels>` is one or more of the detector's fired finding `label` strings, separated by `; `, at most the guard label cap the PRD gives. Which of them are listed, and their order, are free.
- `<ask>` is free text that asks for the flagged spans to be fixed and contains the word `fix` (any letter case).

When an `apply_patch` payload flags several files, their lines are joined by a newline, in any order. A file that is not flagged contributes no line.

## `content`

Request field nested under `tool_input` on the post-tool-use hook (`prosecheck-guard.js`). Host JSON on a `Write` request includes a content string beside the saved path.

### Signature

```
{
  "tool_name": "Write",
  "tool_input": {
    "file_path": string,
    "content": string
  },
  "cwd": string
}
```

`content` is a string member of `tool_input`, next to `file_path`. It is part of the request object. The guard scores the saved file named by `file_path`; this string does not replace that path.

## `cwd`

Request field on the post-tool-use hook (`prosecheck-guard.js`). Host JSON on standard input places the working directory beside the tool name and the tool-input object.

### Signature

```
{
  "tool_name": "Write",
  "tool_input": {
    "file_path": string,
    "content": string
  },
  "cwd": string
}
```

`cwd` is a string at the top level of that object, beside `tool_name` and `tool_input` — not nested inside `tool_input`. When it is supplied, a relative `file_path` is resolved against it.

## `file_path`

Request field nested under `tool_input` on the post-tool-use hook (`prosecheck-guard.js`). It is the saved file’s path.

### Signature

```
{
  "tool_name": "Write",
  "tool_input": {
    "file_path": string,
    "content": string
  },
  "cwd": string
}
```

`file_path` is a string member of `tool_input`, not a top-level field. The guard scores the just-saved file at that path (eligible prose only). When the value is relative and `cwd` is supplied on the same request, the path is resolved against that directory.

## `prompt`

Request field on the prompt-submit hook (`prosecheck-tracker.js`). Host JSON on standard input names the submitted text as `prompt`. When the host supplies a session, the same object names it as `session_id`.

### Signature

```
{
  "prompt": string,
  "session_id": string
}
```

`prompt` is a string. For operator commands the value is the slash command, including `/prosecheck check` followed by a file path, and `/prosecheck show`.

`session_id` is a string beside `prompt`, not nested inside the prompt text. `/prosecheck show` with that value reads the ledger recorded for that session. A different `session_id` is a different ledger; rows from one session are not listed for the other.

The hook reads those fields from the JSON object on standard input. A command reply is the `reason` of the block decision stated under `/prosecheck`; its lines are stated under each subcommand. The process exits successfully.

## `tool_input`

Request field on the post-tool-use hook (`prosecheck-guard.js`). Host JSON on standard input nests the tool’s arguments under `tool_input`.

### Signature

```
{
  "tool_name": "Write",
  "tool_input": {
    "file_path": string,
    "content": string
  },
  "session_id": string,
  "cwd": string
}
```

`tool_input` is an object, not a string, and not a top-level path. It sits beside `tool_name`, `session_id`, and `cwd`. Its members on a `Write` request are `file_path` and `content`.

A `NotebookEdit` request names the notebook with `notebook_path`, a string member of this same object. An `apply_patch` request names the patch body with `command`, a string member of this same object. That `command` member is the patch-body field. It is not the slash command carried by `prompt`.

## `tool_name`

Request field on the post-tool-use hook (`prosecheck-guard.js`). Host JSON on standard input names the file-edit tool as `tool_name`. When the host supplies a session, the same object names it as `session_id`.

### Signature

```
{
  "tool_name": "Write",
  "tool_input": { ... },
  "session_id": string,
  "cwd": string
}
```

`tool_name` is a string at the top level of that object, beside `tool_input`, `session_id`, and `cwd`. For a saved-file Write the value is `Write`. `session_id` is a string sibling of `tool_name`, not a member of `tool_input`. The ledger written for that attempt is the one `/prosecheck show` reads when the same `session_id` is supplied beside `prompt`.

## `/prosecheck`

Operator command on the prompt-submit hook (`prosecheck-tracker.js`). The submitted text is the `prompt` string. A marketplace install also accepts the namespaced spelling. Both spellings run the same router, and a follow-up that echoes the command uses the spelling the user typed, except where a line below keeps the non-namespaced spelling.

### Signature

```
/prosecheck
/prosecheck <subcommand> [argument]
/prosecheck:prosecheck
/prosecheck:prosecheck <subcommand> [argument]
```

Subcommands are exactly `lite`, `full`, `strict`, `off`, `on`, `status`, `show`, `check`, `doctor`, `stats`, `init`, `help`. A bare invocation, with no subcommand, is `help`.

### Block decision

A command prompt is not sent on as an ordinary message. Standard output is one JSON object and the process exits successfully:

```
{
  "decision": "block",
  "reason": string
}
```

`reason` is the command reply. A prompt that is not a command does not use `"decision": "block"`. In the reply forms below, a quoted phrase is matched without regard to letter case unless it is shown inside a line template; a line template is matched exactly, with `<...>` standing for the value named; "a line" means one line of `reason`; any text not stated is free (the implementer's choice).

### Unknown word

An unknown subcommand word is reported on one line that carries both the word `unknown` and the typed word. The reply names each of the twelve subcommands as a standalone word (anywhere in the reply). The stored level does not change.

### Stop phrases

The entire prompt `stop prosecheck`, or the entire prompt `prosecheck off`, is matched without regard to letter case, stores `off`, and is answered with a block decision whose reply names `off` as a standalone word. Which prompts are these phrases is the PRD’s rule (FP-06).

### Ordinary prompts

A prompt that is not a command and not one of those two stop phrases falls through to the writing-contract reminder. When the stored level is `off`, standard output is empty. Otherwise standard output is one JSON object, not a block decision:

```
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": string
  }
}
```

`additionalContext` names the stored level as a standalone word; the rest of its text is free.

### Shipped menu document

The slash command is also a host menu document, not a program. It ships in the plugin tree at `install/prosecheck-command.md`, at `commands/prosecheck.md`, or at both; every file at those two paths is such a document. After an optional front-matter block — a leading line that is only `---`, closed by a later line that is only `---` — the body is a prompt template. That body begins with `/prosecheck` followed by whitespace. The next token is `$ARGUMENTS`, not one of the twelve subcommands. The host replaces `$ARGUMENTS` with the user's full argument string and submits the resulting prompt to this router. A level word in that string changes the stored level. A body that does not contain `$ARGUMENTS` does not forward: those arguments are not in the prompt the router parses, so the stored level stays as it was.

### Stored level

`lite`, `full`, and `strict` store that word. `off` stores `off`. `on` stores `full`. The word is the one-word mode flag `.prosecheck-active`. When no valid word is stored, the level is `full`. `check`, `doctor`, `show`, `stats`, and `init` do not open a network connection.

## `help`

Subcommand of `/prosecheck` and of `/prosecheck:prosecheck`. A bare invocation of either form is this same reply. The reply is the block `reason`.

### Signature

```
/prosecheck
/prosecheck help
/prosecheck:prosecheck
/prosecheck:prosecheck help
```

### Reply lines

The first non-empty line names the live stored level as a standalone word and names no other stored level.

One line carries the four standalone words `code`, `commits`, `config`, and `chat` and the word `never`.

The reply contains the two natural-language request phrases the PRD names for a deep rewrite, `prosecheck this` and `humanize this` (they are user inputs to the host agent, written exactly so).

Every subcommand except `help` is listed on its own command line: a line that contains the non-namespaced `/prosecheck` followed by a space and that word. A namespaced help reply keeps that non-namespaced spelling. `off` and `on` may share one line (`/prosecheck off | on`); every other listed word has exactly one such line. No line starts with `/prosecheck help`. Each command line carries, in any wording around them:

- `lite`: the words `contract` and `scoring`; it shows neither the full-level nor the strict-level guard threshold as an integer.
- `full`: the words `contract` and `guard`, the full-level guard threshold (the number the PRD gives) as a standalone integer, and `(default)`.
- `strict`: the word `guard`, the strict-level guard threshold (the number the PRD gives) as a standalone integer, and the word `scrub`.
- `off`: the word `disable`. `on`: the word `re-enable`. When they share one line, that line carries both.
- `check`: the words `score` and `rewrite`.
- `doctor`: the word `health`.
- `stats`: the words `token` and `prose`.
- `init`: `AGENTS.md` and the word `contract`.
- `status`, `show`: free text.

## `status`

Subcommand of `/prosecheck` and of `/prosecheck:prosecheck`. The reply is the block `reason`.

### Signature

```
/prosecheck status
/prosecheck:prosecheck status
```

The reply is one line. That line names the stored level as a standalone word and names no other stored level (`lite`, `full`, `strict`, `off`). Nothing else on standard output names a stored level. A level stored by either command spelling is what the other spelling's `status` reports.

## `lite`, `full`, `strict`, `off`, `on`

Subcommands of `/prosecheck` and of `/prosecheck:prosecheck`. The reply is the block `reason`; it is not empty.

### Signature

```
/prosecheck lite | full | strict | off | on
/prosecheck:prosecheck lite | full | strict | off | on
```

`lite`, `full`, `strict`, and `off` store that word, and the reply names it as a standalone word. `on` stores `full`; its reply names both `on` and `full` as standalone words. A later `status`, on either spelling, reports the stored word. After `off`, an ordinary non-command prompt produces empty standard output. The entire-prompt stop phrases store `off` too; extra tokens around them do not.

## `check`

Subcommand of `/prosecheck` and of `/prosecheck:prosecheck`. It scores one file and does not rewrite it. The reply is the block `reason`. The file's bytes are unchanged on every outcome below.

### Signature

```
/prosecheck check [path]
/prosecheck:prosecheck check [path]
```

The path argument is one token. It may be written inside one pair of single or double quotes, and may carry one leading `@` outside those quotes; quotes and `@` are not part of the path.

### Scored reply

A readable file inside its size cap is scored by the same detector the command line runs, and the reply is these lines, in this order:

```
<base> - <phrase> (score <score>/100, band: <band>)
confidence: <confidence>[ - <reason>]
coverage: first <window> characters only
tells: <label> (x<count>)[; <label> (x<count>)]...
<free text containing "report only">
```

`<base>` is the file's base name (text before it on that line is free). `<phrase>` is the hook phrase for `<band>`; `<score>` is the detector's integer score; `<band>` and `<confidence>` are the detector's band and confidence words. ` - <reason>` follows when confidence is not `high` and the detector supplied a reason, and `<reason>` is that reason text exactly; when confidence is `high` it may be absent. The `coverage:` line is present only when extracted prose is longer than the scan window; `<window>` is the scan window from the PRD, written with or without a thousands comma. When extracted prose is exactly the window length, no `coverage:` line appears and the window figure appears nowhere in the reply. The `tells:` line lists fired findings by their detector `label`, each with its detector hit count, separated by `; `, at least one and at most the check label cap the PRD gives, when any fired; when no pattern fired it is exactly `tells: none`. The reply does not contain `was written by`.

### Without a path

`check` with no path returns a non-empty reply that contains no standalone integer from 0 through 100 and does not contain the word `unknown`. Its wording is free.

### Not scored

Each of these replies names the file only by the path as typed (quotes and the leading `@` removed) or by its base name. Each contains no standalone integer from 0 through 100 once the path and base name it names are removed, and carries exactly one of the marks `not a file`, `cannot read`, `no readable text`, `detector unavailable`, `no report` as listed (never another of those marks):

- A directory: `not a file`.
- A path that is not on disk: `cannot read`, and the path string as typed is in the reply.
- `.pdf` and `.rtf`: `no readable text`, with the base name. The two formats give the same reply apart from the base name.
- Plain text over its cap: `over <KB> KB`, where `<KB>` is the plain-text cap in kilobytes as the PRD gives it. A `.docx`, `.pptx`, or notebook over its cap: `over <KB> KB`, where `<KB>` is the archive cap in kilobytes as the PRD gives it.
- Python cannot be launched: `detector unavailable`.
- The detector exits without failure and prints nothing: the base name and `no report`.
- The detector exits without failure and prints text that is not a report: `no report`, and not the base name.
- The detector exits with a failure: the base name and the word `failed`, and not `no report`; when that run wrote text on its error stream, that text is in the reply. The exit status is not required.

## `doctor`

Subcommand of `/prosecheck` and of `/prosecheck:prosecheck`. It is a health check. The reply is the block `reason`. Its Python check line reports the outcome of running the bundled detector.

### Signature

```
/prosecheck doctor
/prosecheck:prosecheck doctor
```

### Shape

The first non-empty line is a title (free text). The last non-empty line is the closer. Exactly four non-empty lines sit between them, in any order: the mode check, the detector check, the Python check, the settings check. A successful check line carries the marker `[OK]`; a check line that is not successful does not carry `[OK]` (its marker is free); the closer does not carry `[OK]`. Each check line is identified by one label word, and only one check's label appears on a line:

- Mode: `mode: <level>` with the stored level. Successful when the level is not `off`. When the level is `off`, the line is not successful, and it carries the non-namespaced `/prosecheck on` (with `on` a standalone word); `off` is not a fault of the install.
- Detector: the check line, other than the Python line, that contains the word `detector`. Successful when the bundled detector is in the plugin tree; otherwise not successful. This line never contains `python`, and it stays successful when Python cannot be launched.
- Python (the only check line that contains the word `python`, in any letter case): successful when Python ran the bundled detector and the run produced a numeric score. When Python cannot be launched: not successful, and the line contains `python not found` and `not re-scored` and also says, in free wording that contains the word `prose`, that prose is still shaped. When the run returns text that is not a numeric score: not successful, and the line does not contain `python not found`.
- Settings (the only check line that contains the word `settings`): successful when the settings folder is writable, otherwise not successful; it does not contain `python`.

### Closers

All four checks successful and mode not `off`: the closer contains the plain-text cap as `<KB> KB`, the archive cap as `<MB> MB` (a space before `MB` is optional), the scan window written with or without a thousands comma (sizes as the PRD gives them), and the show command in the form the user typed (`/prosecheck show` or `/prosecheck:prosecheck show`); it does not contain `/prosecheck doctor`. The rest of its wording is free.

Any check not successful (other than the mode line at `off`): the closer contains the non-namespaced `/prosecheck doctor` and the word `fix`, and contains neither the show command nor the on command in either spelling. The rest of its wording is free.

Only the mode is `off` (the other three successful): the closer contains the on command in the form the user typed (`/prosecheck on` or `/prosecheck:prosecheck on`) and the word `scored`, and contains neither `/prosecheck doctor` nor `not re-scored`. The rest of its wording is free.

## `show`

Subcommand of `/prosecheck` and of `/prosecheck:prosecheck`. It lists this session's ledger, newest first. The reply is the block `reason`. The session is the `session_id` on the same prompt-submit object. A different `session_id` is a different ledger.

### Signature

```
/prosecheck show
/prosecheck:prosecheck show
```

The ledger holds base names only. The reply does not contain a parent-directory name and does not contain the document body.

### Empty ledger

The reply contains the phrase `nothing scored yet`, and contains `.docx` and `.pdf`. It contains no standalone integer from 0 through 100 and does not name a file that was not saved; the rest of its wording is free. A ledger older than the ledger age limit the PRD gives is not listed after a later session starts; that later `show` is the empty-ledger reply.

### Rows

A non-empty ledger reply has one row line per ledger entry, newest first by save time. A row line is optional leading whitespace, then `<base> - <body>`. Other lines (such as a heading) are free and do not begin with a listed base name followed by ` - `.

A scored row's body is:

```
<phrase> (score <score>/<band>[, first <window> characters only])[ - <state>: <labels>]
```

`<phrase>`, `<score>`, and `<band>` are the hook phrase, score, and band the guard recorded. `, first <window> characters only` is present only when the scan was truncated (`<window>` as in `check`). When the row has pattern labels, the clause ` - <state>: <labels>` follows: `<state>` is free text without a colon that contains the word `flagged` when the file was flagged, and contains the word `under` (and not `flagged`) when it was under the threshold; `<labels>` is between one and the show label cap the PRD gives of the recorded labels, separated by `; `. A scored row with no labels ends at the closing parenthesis. The row does not contain `was written by`.

Other row bodies:

- Size skip: `not scored: ` followed by free text that contains `<KB> KB`, where `<KB>` is the plain-text cap in kilobytes for plain text, and the archive cap in kilobytes for an archive or notebook (caps as the PRD gives them).
- Binary file (such as `.pdf`): contains `not re-scored` and does not contain `not scored:`.
- Failed: `not scored: <reason>`, where `<reason>` is free readable text that contains no `<number> KB` figure.

None of these three contains a standalone integer from 0 through 100 other than the size-skip figure, and none begins with a hook phrase.

## `init`

Subcommand of `/prosecheck` and of `/prosecheck:prosecheck`. It writes the writing contract into the project that is the process's current working directory. The reply is the block `reason`. It opens no network connection.

### Signature

```
/prosecheck init
/prosecheck:prosecheck init
```

### When the level is off

No files are written: not `AGENTS.md`, and not `.cursor/rules/prosecheck.mdc`. Files that already exist are left byte for byte. The reply contains `switched off` and the on command `<form> on`, where `<form>` is the spelling the user typed (`/prosecheck` or `/prosecheck:prosecheck`).

### When the level is not off

Two writes, independent of each other.

`AGENTS.md` in the working directory receives the writing contract, appended after any text already in the file. Those earlier bytes stay as the prefix of the file. The contract is one section, so a second `init` does not add another copy. The section is recognised by that single copy of the contract, not by a required marker spelling. If the section is already present, a line of the reply contains the word `already` and names `AGENTS.md`, and the file is not changed.

The exported contract does not contain this machine's detector path and does not contain the user name. At `full` and at `strict` exactly one line of the export names `CLAUDE_PLUGIN_ROOT` together with the standalone words `skills` and `plugins`: it tells the other agent to use `CLAUDE_PLUGIN_ROOT` when that variable is set and otherwise to locate the detector in installed skills and plugins. At `lite` the export names none of `skills`, `plugins`, `CLAUDE_PLUGIN_ROOT`, shows no full-level threshold integer, and does not name the band `light tells`. At `full` the export shows the full-level threshold and the full scoring target, and does not name the cleanup switch. At `strict` the export names the cleanup switch `--clean`, and names the band `clean` (as a standalone word outside `--clean`) on a line the lite export does not contain.

`.cursor/rules/prosecheck.mdc` is copied from the shipped Cursor rule when that file does not yet exist. If it exists, a line of the reply contains the word `already` and names `prosecheck.mdc`, and the bytes are not overwritten.

The rule opens with a front-matter block delimited by lines that are only `---`. Inside that block the glob list is exactly the eight prose globs `*.md`, `*.mdx`, `*.markdown`, `*.txt`, `*.rst`, `*.tex`, `*.org`, and `*.adoc` (each may carry a leading directory pattern). It does not include `*.py`, `*.js`, `*.ts`, or `*.json`. The body after the block contains the phrase `prose deliverables only` and the banned-vocabulary list from the writing contract. The rule does not show the full-level threshold integer, does not name `light tells`, and contains neither `detect.py` nor any word beginning with `detect`.

### Cannot read or write

If `AGENTS.md` cannot be read, the reply contains `cannot read` or `cannot write`; if it cannot be written, the reply contains `cannot write`; in both cases the file is not given the contract. If the Cursor rule cannot be written, the reply contains `cannot write` and the rule file is not created. A failed write is not reported with the successful export reply.

## `stats`

Subcommand of `/prosecheck` and of `/prosecheck:prosecheck`. It prints session token use and, when the scored slice is long enough, an own-prose score. The reply is the block `reason`. It opens no network connection.

### Signature

```
/prosecheck stats
/prosecheck:prosecheck stats
```

The transcript is the host-named `transcript_path` on the same prompt-submit object when that member is supplied. Otherwise it is a `.jsonl` file under the `projects` folder of `CLAUDE_CONFIG_DIR`, selected by the PRD’s rule (FP-06).

### Transcript rows

The file is JSON lines. An assistant row has `"type": "assistant"` and a `message` object. Token totals are the sums of `output_tokens` and `cache_read_input_tokens` on that message's `usage` object. Text is taken from `content` entries whose `type` is `text`. A message’s identifier is its `id`. Which rows count, and how, is the PRD’s rule (FP-06).

### Reply

When a transcript can be read, the reply contains these lines, each once (each line may carry leading whitespace; `<n>` is a decimal integer, optionally grouped with commas):

```
assistant turns: <n>
output tokens: <n>
cache-read input tokens: <n>
```

They carry the assistant-turn count, the output-token total, and the cache-read input-token total. The reply also contains `level: <level>` once, with the stored level. When the scored slice is longer than the PRD's threshold, the reply contains `session prose ai_tell_score: <score>` once, `<score>` being the detector's score of that slice; otherwise that phrase is absent. All other text is free.

### Missing transcript

A path that is not a readable transcript yields a non-empty reply that contains none of the three labelled count lines. The rest of its wording is free.

## `transcript_path`

Request field on the prompt-submit hook (`prosecheck-tracker.js`). Host JSON on standard input may name the session transcript beside `prompt`.

### Signature

```
{
  "prompt": "/prosecheck stats",
  "transcript_path": string
}
```

`transcript_path` is a string at the top level of that object, beside `prompt`. It is not nested inside the prompt text. `/prosecheck stats` and `/prosecheck:prosecheck stats` read the transcript at that path. When the member is absent, `stats` uses the newest transcript under the config directory's `projects` folder instead.
