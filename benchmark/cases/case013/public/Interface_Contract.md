# Interface Contract

## Product overview

**MEMBUNDLE Agent Memory** is a domain-neutral, Git-native persistent project memory for AI agents, based on the Open Bundle Format (MEMBUNDLE) v0.2. This document states the product's whole outer shell: how a caller reaches each capability, what it passes in, and the form of everything the product puts out. What each capability does is stated in the Full PRD. Every part of the shell is either stated here or declared the implementer's choice.

The product is one self-contained executable named `membundle`. The same executable also runs as a Model Context Protocol server over standard input and standard output. The product is that executable plus the on-disk Markdown/YAML bundle layout it reads and writes. It is not an importable library, a network daemon, or an HTTP server, and it has no configuration file of its own.

## Shape of the public surface

**Build.** The repository root is a Go module (`go.mod` at the root) with a `Makefile` whose `build` target, run as `make build` at the repository root, writes the executable `bin/membundle` under that root. The rest of the Makefile is the implementer's choice.

**Executable.** A caller runs `bin/membundle` as `membundle` followed by a command token and that command's arguments.

**Commands.** The command tokens are `validate`, `search`, `show`, `create`, `update`, `relate`, `init`, `bootstrap`, `agents`, `mcp`, `version`, and `help`. The tokens after `agents` are `lint`, `init`, `link`, and `check`. All are lowercase. How `version` and `help` are spelled beyond their command token, and what they print, is the implementer's choice.

**Argument conventions.** In the signatures below, `<x>` is a value the caller supplies, `[ ... ]` is optional, and every flag is written exactly as shown. A flag shown with `<value>` takes one following value token. A flag shown without a value takes no value token. Positional arguments keep the order shown, and flags follow them, as shown.

**Bundle path.** `[path]` on a bundle command names a bundle directory. When it is omitted, the default bundle path of the PRD ("Bundle layout a caller can construct") applies; in the output forms below, `<path>` and `<bundle>` stand for the path as the caller named it, or for that default (`knowledge` or `.`) when omitted, unless a form says otherwise.

### Command signatures

```
membundle init [path]
membundle bootstrap [path] [--name <name>] [--no-bundle] [--no-skill] [--no-agents-md] [--no-makefile] [--overwrite-agents-md]
membundle show <identity> [path] [--json] [--raw]
membundle search [query] [path] [--for-path <source-path>] [--limit=<n> | --limit <n>] [--json]
membundle create <identity> [path] [--type <type>] [--title <title>] [--desc <description>] [--body <body>] [--tags <tags>] [--actor <actor>] [--no-log] [--no-index] [--json]
membundle update <identity> [path] [--title <title>] [--desc <description>] [--body <body>] [--actor <actor>] [--no-log] [--no-index] [--json]
membundle relate <source> <target> [path] [--desc <prose>] [--actor <actor>] [--json]
membundle validate [path] [--strict] [--stale] [--drift] [--agents] [--json]
membundle agents lint [--budget=<n>] [--json] [path]
membundle agents init [--domain <profile>] [--name <project>] [--root <dir>]
membundle agents link [--root <dir>] [--check] [--force]
membundle agents check [--root <dir>]
membundle mcp [path]
```

- `bootstrap`: `[path]` is the target project directory. `--name` is the project name. `--no-bundle`, `--no-skill`, `--no-agents-md`, `--no-makefile` skip the `knowledge` bundle, the skill tree, `AGENTS.md`, and `Makefile` respectively. `--overwrite-agents-md` requests overwrite of an existing `AGENTS.md`.
- `show`: `--json` selects the structured concept record, `--raw` the verbatim file; with neither, human output.
- `search`: `[query]` is the query string; an empty string as the first positional is an omitted query, also when a path filter is given. `--for-path` is the source-path filter. The cap is accepted both as the single token `--limit=<n>` and as `--limit` followed by a separate value token; `<n>` may be `0` or negative.
- `create` / `update`: `--desc` is the description (there is no `--description` flag). `--tags` is a comma-separated list. `--no-log` skips the log entry and `--no-index` skips parent-index bookkeeping. `--json` selects structured success output.
- `relate`: `--desc` is the relationship prose. `--json` selects structured success output.
- `validate`: `--strict` is the strict producer gate, `--stale` the stale-date gate, `--drift` the drift audit, `--agents` the agents governance check, `--json` structured output.
- `agents lint`: the cap is accepted as the single token `--budget=<n>`; `<n>` may be `0` or negative. `[path]` is the `AGENTS.md` file to lint and comes after the flags; when omitted, it is `AGENTS.md` in the current directory.
- `agents init`, `agents link`, `agents check`: `--root` is the target root directory; when omitted, it is the current directory. `--domain` is the profile name and `--name` the project name. `--check` is check-only and `--force` is the overwrite request.
- `mcp`: `[path]` is the started bundle path. The environment variable `MEMBUNDLE_MCP_ROOT`, when set, names the workspace root.

### Model Context Protocol tools

The server's tools are exactly `membundle_search`, `membundle_show`, `membundle_create`, `membundle_update`, `membundle_relate`, and `membundle_validate`. A `tools/call` request names the tool in `params.name` and passes its arguments as the object `params.arguments`. Arguments per tool (every key is a JSON string unless stated):

- `membundle_search` — `query`, `for_path`, `bundle`, `limit` (integer). All optional.
- `membundle_show` — `concept_id` (required), `bundle`.
- `membundle_create` — `concept_id`, `type`, `title` (required); `description`, `body`, `bundle`.
- `membundle_update` — `concept_id` (required); `title`, `description`, `body`, `bundle`.
- `membundle_relate` — `source_id`, `target_id` (required); `description` (relationship prose), `bundle`.
- `membundle_validate` — `bundle`; `strict`, `stale` (booleans).

No tool takes an actor, skip-log, skip-index, drift, or agents argument. Command-line flags are not argument keys.

## Names a caller exchanges with the product

- **Bundle files.** Root `index.md`, root `log.md`, nested `index.md`; concept files `<identity>.md`; a bundle-root `AGENTS.md`. The conventional bundle directory name is `knowledge`.
- **Root index version key.** `membundle_version`, with the scalar `0.2`, in the root `index.md` frontmatter.
- **Frontmatter.** A YAML block at the start of a file between two lines `---`. Field names: `type`, `title`, `description`, `tags`, `generated` (keys `by`, `at`), `verified` (one entry, or a list of entries, each with keys `by`, `at`), `status`, `governance`, `code_refs`, `stale_after`, `sources` (a list of entries with keys `id`, `resource`, `last_modified`, `author`), `resource`, and the legacy `timestamp`.
- **Log date headings.** `YYYY-MM-DD`.
- **Working-memory delimiters.** `<!-- BEGIN MEMBUNDLE AGENT MEMORY -->` and `<!-- END MEMBUNDLE AGENT MEMORY -->`.
- **Skill documents.** `.agents/skills/membundle-memory/` holding `SKILL.md`, `discovery.md`, `remember.md`, `update.md`, `relationships.md`, `examples.md`.
- **SSoT link paths.** `CLAUDE.md`, `.cursorrules`, `.windsurfrules` (each a symbolic link whose target is `AGENTS.md`) and `.github/copilot-instructions.md` (a symbolic link whose target is `../AGENTS.md`).
- **Project files.** `AGENTS.md` and `Makefile` at the project root.
- **Closed vocabularies.** Governance `constraint`, `hold`, `context`; status `draft`, `stable`, `deprecated`; MBG rule identifiers `MBG-001` … `MBG-005`; domain profiles `software`, `research`, `legal`, `coaching`, `books`; the matched-field tokens `title`, `tags`, `description`, `id`, `body`, `code_refs`.

The content of each file the product writes is stated in the PRD, apart from the bookkeeping lines stated under Output forms; everything else in those files is the implementer's choice.

## Output forms

`<placeholders>` stand for values the product fills in; text in backticks outside placeholders is literal. "Line" means one line of UTF-8 text ending in a newline. Standard output and standard error are UTF-8. Unless a form says otherwise, a command writes its success output on standard output, writes nothing on standard error, and ends with status `0`. Any text a form does not state is the implementer's choice.

**Tool result text.** The tool result text of a `tools/call` reply is the `text` of the first item of `result.content`; that item's `type` is `text`. A tool result text may carry one trailing newline.

**Failure classes (command line).** A command that does not succeed uses one of these forms. Text after a stated prefix or marker is free.

- **Usage failure** — a required positional argument is missing, or command-line `search` has neither a query nor a path filter. Status `1`. The usage text contains `Usage:`, on either stream.
- **Load failure** — the bundle of `show`, `search`, `update`, or `validate` cannot be loaded. Status `2`. Standard error carries a line that begins `Error loading bundle: `.
- **Not found** — `show` or `update` of a well-formed identity that is not a loaded concept. Status `1`. Standard error carries a line that begins `Concept '<identity>' not found`, where `<identity>` is the identity with a trailing `.md` stripped.
- **Relate endpoint not found** — `relate` whose source or target is not a concept. Status `1`. Standard error carries a line that begins `Error: <role> concept '<identity>' not found`, where `<role>` is `source` or `target`.
- **Rejected input or refused write** — `show`, `create`, `update`, or `relate` with a rejected identity or field value, source equal to target, a write that would resolve outside the bundle, an I/O failure, or (for `relate` only) a bundle that cannot be loaded. Status `1`. Standard error carries a line that begins `Error: `.
- **`init` failure** — status `1`. Standard error carries a line that begins `Error initializing bundle: `.
- **`bootstrap` failure** — status `1`. Standard error carries a line that begins `Bootstrap error: `.
- **`agents` failure** — every `agents` subcommand that does not succeed. Status `1`. Standard error carries a line that begins `Error: `.

**`init`.** Success prints exactly one line, which contains `'<path>'` (the path between single quotes), the product name `MEMBUNDLE` (any letter case), and `0.2`; its other wording is free.

**`bootstrap`.** Success prints, in this order: a first line that contains `'<path>'` (`<path>` as named, `.` when omitted), other wording free; a line `Created:`; then one line per component that was not skipped, in the order knowledge, skill, `AGENTS.md`, `Makefile`. A component line is two spaces, `- `, then the component token `knowledge/`, `.agents/skills/membundle-memory/`, `AGENTS.md`, or `Makefile`; text after the token is free. A skipped component has no component line. Any later lines are free, and none of them begins with two spaces and `- `.

**`show` (human).** Standard output is, in this order: a line `ID:` then the identity; `Type:` then the type; `Title:` then the title; `Description:` then the description; `Tags:` then the tags joined by `, ` (only when there are tags); `Generated:` then `<at> by <by>` (only when there is generated provenance); `Inbound:` then the inbound identities joined by `, ` (only when there are any); `Outbound:` then the outbound identities joined by `, ` (only when there are any); an empty line; a line `--- Body ---`; then the body with leading and trailing whitespace removed. On each labeled line the label is followed by one or more spaces and the value. The order of identities within a list is free.

**`show --json` and `membundle_show`.** Standard output (or the tool result text) is one JSON object:

- `id` — string, the identity with a trailing `.md` stripped.
- `path` — string, `<identity>.md`.
- `type` — string.
- `title`, `description` — strings, present when non-empty.
- `tags` — array of strings, present when there are tags.
- `generated` — object with string keys `by` and `at`, present when there is generated provenance.
- `body` — string, the text after the closing frontmatter fence; its leading and trailing whitespace is free.

Other keys are free. The record has no inbound or outbound keys.

**`show --raw`.** Standard output is the file's bytes as stored.

**`search --json` and `membundle_search`.** Standard output (or the tool result text) is one JSON array of hit objects in rank order. Zero hits is `[]` or `null` on the command line and `[]` from `membundle_search`. Each hit object has:

- `concept_id` — string, the identity.
- `title`, `type`, `description` — strings; the empty string when the concept has none.
- `governance` — string, the effective governance.
- `score` — number; its value is free apart from the rank order.
- `matched_on` — array of matched-field tokens, any order.
- `code_refs`, `tags` — arrays of strings, present when the concept has any.
- `inbound`, `outbound` — arrays of identities, present when there are any.

Other keys are free.

**`search` (human).** With hits, standard output is a first line (free text), an empty line, then one block per hit in rank order. A block is three lines and an empty line:

1. `<rank>. [<governance>] [<score>] <identity> (<type>)` — `<rank>` is the 1-based rank, optionally preceded by spaces; one or more spaces separate the `.`, the badge, the score, and the identity; `<score>` is free text without `]`; the line ends with one space, `(`, the type as stored, and `)`.
2. Four spaces, then free text.
3. Four spaces, `Matches: `, then the matched-field tokens joined by `, `.

With zero hits, standard output is exactly one non-empty line, wording free, that does not have the form of a block's first line.

**`create`, `update`, `relate` (human).** Success prints exactly one line, wording free, which contains:

- `create` and `update`: `'<identity>.md'` and `'<bundle>'`;
- `relate`: `'<source>'`, `'<target>'`, and `'<bundle>'`, where `<source>` and `<target>` are the identities with a trailing `.md` stripped.

**`create --json`, `update --json`.** One JSON object with `status` (the string `success`), `concept_id` (the identity), and `path` (`<identity>.md`). **`relate --json`.** One JSON object with `status` (the string `success`), `source`, and `target`. Other keys are free.

**`membundle_create`, `membundle_update`, `membundle_relate` success.** The tool result text is exactly one line, wording free, that ends with ` <bundle>` and contains:

- `membundle_create` and `membundle_update`: `<identity>.md`;
- `membundle_relate`: `'<source>'` and `'<target>'`, the `source_id` and `target_id` values as given.

Here `<bundle>` is the absolute path of the bundle directory written, with symbolic links resolved.

**Tool-level failures.** `isError` is `true`, and the tool result text begins:

- `Concept '<identity>' not found` — `membundle_show` or `membundle_update` of an identity that is not a loaded concept.
- `Path traversal denied: ` — a `bundle` argument that resolves outside the workspace root.
- `Failed to load bundle from ` — a named `bundle` that cannot be loaded.
- `Invalid concept_id: ` — a rejected identity. A `membundle_show` without `concept_id` gives either this failure or the JSON-RPC invalid-params error.
- `Unknown tool: <name>` — a tool name outside the six.

Any other tool-level failure text is free.

**`validate --json` and `membundle_validate`.** Standard output (or the tool result text) is one JSON object:

- `bundle_path` — string. On the command line, `<path>`, with `/knowledge` appended when loading resolved into a nested `knowledge` bundle; for `membundle_validate`, the absolute bundle directory loaded.
- `declared_version` — string, absent when the root index declares none.
- `concept_count` — integer.
- `errors`, `warnings`, `gate_findings` — arrays of strings: hard errors, warnings (drift and stale warnings included), and gate findings. Each string begins with the bundle-relative path of the file it concerns, then `: `; the rest is free. The file a string concerns is the index file holding the listing for a drift warning about a listing (`index.md` for the root index), `log.md` for a log heading warning, the nested index for nested index frontmatter, and the concept file `<identity>.md` for every other finding.
- `broken_links` — array of objects with string keys `source_concept` (`<identity>.md` of the linking concept), `target_href` (the link target as written), and `reason` (free); `null` or `[]` when there are none.
- `orphans` — array of orphan identities; `null` or `[]` when there are none.
- `stale_count` — integer.
- `is_conformant` — boolean.
- `gate_passed` — boolean, always false when not conformant.

Other keys are free. On the command line, `validate --json` ends with status `0` when `gate_passed` is true and `1` otherwise; a load failure is the load-failure form.

**`validate` (human).** Standard output is zero or more finding lines, an empty line, and one summary line (free text). Finding lines, in this order:

- `warn  <warning>` for each warning (two spaces after `warn`);
- `<label>  <finding>` for each gate finding;
- `<label>  <identity>.md: ` then free text, for each broken link, where `<identity>` is the linking concept;
- `<label>  <identity>.md: ` then free text containing `orphan`, for each orphan;
- `error <error>` for each hard error;

where `<label>` is `gate` under `--strict` and `warn` otherwise, and `<warning>`, `<finding>`, `<error>` are the strings of the structured report. With `--agents`, the `agents check` output comes first.

**`agents lint --json`.** Standard output is one JSON object, whether or not the lint passes; the status is `0` whenever the file was read.

- `path` — string, the linted path as given.
- `passed` — boolean.
- `error_count`, `warn_count` — integers: the number of findings whose `severity` is `error`, and of those whose `severity` is `warning`.
- `findings` — array of objects with `rule_id` (an MBG rule identifier), `severity` (`error` or `warning`), `line` (1-based integer), `message` (free), and optionally `snippet` (free).
- `token_stats` — object with `estimated_tokens` (integer, the token estimate; its value is the implementer's choice), `budget_limit` (integer, the in-force cap), and `budget_exceeded` (boolean, the exceeded mark).

Other keys are free.

**`agents lint` (human).** Standard output starts with a line that begins `MBG Linter: ` and a line that begins `Token Stats: ` and contains `Budget: <cap>`, where `<cap>` is the in-force cap as a decimal integer. Then one line per finding that begins `[ERROR] <rule-id>` (or `[WARN] <rule-id>`), each optionally followed by lines that begin with spaces. The rest is free. A failing lint ends as an `agents` failure.

**`agents init`.** Success output is free.

**`agents link`.** The first line is free text; then one line per mapping that begins `✓ ` (linked, overwritten, or already valid) or `✗ ` (not linked), and contains the mapping's link path. Text after the marker and link path is free, and other lines are free. A `✗ ` line makes the run an `agents` failure. With `--check`, the same holds with `✓ ` for a valid mapping and `✗ ` for an invalid one.

**`agents check`.** Standard output is the `agents lint` human report for `<root>/AGENTS.md`, then the `agents link --check` report for `<root>`. Other lines are free.

**Bookkeeping lines in bundle files.**

- *Init log entry.* The list item `init` writes under today's date heading of a new root `log.md` contains `MEMBUNDLE` (any letter case) and `0.2`; the rest is free.
- *Log entry.* Each `create`, `update`, and `relate` that writes a log entry adds one Markdown list item (marker free) in the section under the heading whose text is today's UTC date. Its text begins `**Creation**: ` for `create` and `**Update**: ` for `update` and `relate`. For `create` and `update` the rest contains `<identity>.md`; for `relate` it contains `<source>.md` and `<target>.md`. The rest is free.
- *Parent listing.* One Markdown list item (marker free) containing the inline link `[<title>](<filename>)`, where `<filename>` is the final identity segment plus `.md`, and, when the description is non-empty, the description. Other text on the item is free.
- *Related item.* Without prose, the item's text is exactly `Related to [<link text>](<href>)`. With prose, its text begins `[<link text>](<href>)` and ends with the prose, leading and trailing whitespace removed; the text between is free. `<href>` is `/`-separated and may be preceded by `./`.

**MCP replies.** Each reply line is one JSON-RPC 2.0 object with `jsonrpc` (`"2.0"`), the request's `id`, and either `result` or `error`.

- `initialize`: `result` has `protocolVersion` (`2024-11-05`), `serverInfo` (an object whose `name` is `membundle-agent-memory`; other members free), and `capabilities` (an object with members `tools`, `resources`, `prompts`, each an object whose members are free). Other members free.
- `ping`: `result` is `{}`.
- `tools/list`: `result.tools` is an array of six objects, each with `name` (each tool name once); other members free.
- `resources/list`: `result.resources` is `[]`. `prompts/list`: `result.prompts` is `[]`. Other members free.
- `tools/call`: `result.content` is an array whose first item is an object with `type` (`text`) and `text`; `isError` is `true` on a tool-level failure and absent or `false` otherwise. Further items free.
- A protocol error reply has `error`, an object with `code` (integer) and `message` (free). The reply to a line that is not JSON has `id` `null`.
