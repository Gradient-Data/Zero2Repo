# Interface Contract

### Product overview

**Git Orbulk** (VCS Large Object Store) is a compiled command-line Git extension. Git stores compact **pointer** blobs; the real bytes live in a local object store plus a remote Git Orbulk endpoint. The product is one executable named `git-orbulk` together with the on-disk, Git-config, environment, and HTTP/SSH protocol surfaces it speaks. It is not an importable library and it does not implement the server. This document is the product's outside shell: entry points, their inputs, and the form of everything the product puts out. What the product does with those inputs is stated in the PRD.

### Entry points

- **Build output.** The default `make` goal writes the executable at `bin/git-orbulk` under the built tree.
- **Direct entry.** `git-orbulk <subcommand> [<options>] [<arguments>]`.
- **Git-extension entry.** `git orbulk <subcommand> [<options>] [<arguments>]`: Git finds `git-orbulk` on `PATH`. Both entries accept exactly the same subcommands, options, and arguments.
- **Subcommands.** Porcelain: `checkout`, `clone`, `completion`, `dedup`, `env`, `ext`, `fetch`, `fsck`, `install`, `lock`, `locks`, `logs`, `ls-files`, `migrate`, `prune`, `pull`, `push`, `status`, `track`, `uninstall`, `unlock`, `untrack`, `update`, `version`. Plumbing: `clean`, `filter-process`, `merge-driver`, `pointer`, `post-checkout`, `post-commit`, `post-merge`, `pre-push`, `smudge`, `standalone-file`. Subcommand names are exactly these lowercase tokens.
- **Help.** No subcommand, `help`, `help <subcommand>`, and `<subcommand> --help`. Help for a subcommand contains that subcommand's name.
- **Option syntax.** An option documented as `--name=` takes its value attached after `=` with no space. An option documented as `--name <value>` takes its value as the following argument. Every other option is a switch.

### Process exits and streams

- Success exits 0. Failure exits non-zero; unless a section below states a number, which non-zero value is the implementer's choice.
- An error or refusal writes a non-empty message on standard error; its wording is free text, the implementer's choice.
- Usage text (no subcommand, `help`, `help <subcommand>`, `--help`) goes to standard output, names the product (`git-orbulk` / `git orbulk`; hyphen, space, and case free), and spans several lines. Its wording and layout are free.
- Unless a section below states otherwise, the text a command prints on success (progress, banners, summaries) is free text on standard output or standard error, the implementer's choice.

### `version` and `env`

- `version` writes on standard output a line that contains `git-orbulk/<version>`, where `<version>` is this build's version as dot-separated decimal components (at least `<major>.<minor>`). The rest of the line is free.
- `env` writes on standard output, one fact per line:
  - the same `git-orbulk/<version>` line that `version` prints;
  - for the default remote, a line carrying the endpoint URL that would be used for it; for every other remote, a line carrying that remote's name and its endpoint URL. The endpoint is an `http://` or `https://` URL. Apart from the remote's own Git URL, no other URL appears on that line, and apart from the remote’s name and its Git URL, the line does not carry the word `push` or `upload`. The label and layout of the line are free;
  - optionally, an upload (push) endpoint; any line that presents one or echoes a push-URL setting carries the word `push` or `upload` (case free; the word may also lead a camel-case or key spelling, such as `lfs.pushurl`);
  - a line for each of `filter.lfs.process`, `filter.lfs.smudge`, and `filter.lfs.clean` that carries the key's effective value verbatim (empty when the key is unset);
  - further facts (directories, transfer, recentness, prune, storage, and agent settings), in a layout the implementer chooses.

### Git configuration keys

Keys are read from every Git configuration file and, for the keys marked `.lfsconfig`, also from the `.lfsconfig` file at the repository root (Git-config syntax). Booleans take the tokens listed under **Boolean tokens**. Durations are integers counting seconds.

| Key | Value | Role (PRD) | `.lfsconfig` |
| --- | --- | --- | --- |
| `lfs.url` | URL | repository/global endpoint override (FP-06) | yes |
| `lfs.pushurl` | URL | upload endpoint override (FP-06) | yes |
| `remote.<remote>.lfsurl` | URL | per-remote endpoint override (FP-06) | yes |
| `remote.<remote>.lfspushurl` | URL | per-remote upload endpoint override (FP-06) | no |
| `remote.lfsdefault` | remote name | default remote (FP-06) | yes |
| `remote.lfspushdefault` | remote name | default push remote (FP-06) | yes |
| `lfs.<url>.access` | `basic`, `negotiate`, or `none` | URL-scoped access mode (FP-06) | yes |
| `lfs.gitprotocol` | URL scheme: `https` (default) or `http` | scheme for endpoints derived from `git://` remotes (FP-06) | yes |
| `lfs.fetchinclude` / `lfs.fetchexclude` | comma-separated path patterns | include/exclude filters (FP-05, FP-08, FP-12, FP-13) | yes |
| `lfs.skipdownloaderrors` | boolean | skip download errors (FP-05, FP-15) | yes |
| `lfs.allowincompletepush` | boolean | allow incomplete push (FP-09) | yes |
| `lfs.locksverify` / `lfs.<endpoint-url>.locksverify` | boolean (unset: not configured) | lock verification on push (FP-10) | yes |
| `lfs.storage` | directory path | store root (FP-05) | no |
| `lfs.concurrenttransfers` | positive integer | concurrent-transfer bound (FP-07) | no |
| `lfs.tustransfers` | boolean | tus adapter (FP-07) | no |
| `lfs.basictransfersonly` | boolean | basic transfers only (FP-07) | no |
| `lfs.transfer.maxretries` | integer | retry count (FP-07) | no |
| `lfs.transfer.maxretrydelay` | integer seconds | delay between retries (FP-07) | no |
| `lfs.dialtimeout` / `lfs.tlstimeout` / `lfs.activitytimeout` / `lfs.keepalive` | integer seconds | HTTP timeouts (FP-07) | no |
| `http.sslverify` | boolean (default `true`) | TLS certificate verification of endpoint requests (FP-07) | no |
| `lfs.fetchrecentrefsdays` / `lfs.fetchrecentcommitsdays` | integer days | recentness window (FP-08, FP-12) | no |
| `lfs.fetchrecentalways` | boolean | always fetch recent (FP-08) | no |
| `lfs.pruneoffsetdays` | integer days | prune offset (FP-12) | no |
| `lfs.pruneverifyremotealways` | boolean | verify-remote by default on prune (FP-12) | no |
| `lfs.forceprogress` | boolean | progress forcing (FP-15) | no |
| `lfs.setlockablereadonly` | boolean | lockable read-only (FP-15) | no |
| `lfs.sshtransfer` | `negotiate` (default), `always`, or `never` | pure SSH mode (FP-17) | no |
| `lfs.customtransfer.<name>.path` | executable path | custom agent process (FP-16) | no |
| `lfs.customtransfer.<name>.args` | argument string | custom agent arguments (FP-16) | no |
| `lfs.customtransfer.<name>.concurrent` | boolean (default `true`) | whether concurrent agent instances are allowed (FP-16) | no |
| `lfs.customtransfer.<name>.direction` | `download`, `upload`, or `both` | agent direction (FP-16) | no |
| `lfs.standalonetransferagent` | agent name | standalone agent (FP-16) | no |
| `lfs.extension.<name>.clean` / `.smudge` | command line | extension commands (FP-16) | no |
| `lfs.extension.<name>.priority` | non-negative integer | extension priority (FP-16) | no |

Keys `filter.lfs.clean`, `filter.lfs.smudge`, `filter.lfs.process`, and `filter.lfs.required` are the Git filter definition that `install` writes and `uninstall` removes. Their values are commands that run `git-orbulk` (exact argv free).

### Environment variables

| Variable | Value | Role (PRD) |
| --- | --- | --- |
| `GIT_ORBULK_SKIP_SMUDGE` | boolean | skip smudge (FP-05, FP-15) |
| `GIT_ORBULK_SKIP_PUSH` | boolean | skip push (FP-09, FP-15) |
| `GIT_ORBULK_SKIP_DOWNLOAD_ERRORS` | boolean | skip download errors (FP-15) |
| `GIT_ORBULK_FORCE_PROGRESS` | boolean | progress forcing (FP-15) |
| `GIT_ORBULK_SET_LOCKABLE_READONLY` | boolean | lockable read-only (FP-15) |

### Boolean tokens

Booleans are compared case-insensitively. Truthy: `true`, `1`, `on`, `yes`, `t`. Every other value, including `false`, is falsey. An unset key or variable takes its default.

### Files and directories

- **Local store.** Objects live at `<store-root>/objects/<h0h1>/<h2h3>/<oid>`, where `<oid>` is the 64-character lowercase hex object id and `<h0h1>`, `<h2h3>` are its first and second pairs of hex digits. `<store-root>` is `<git-dir>/lfs` by default, or the `lfs.storage` directory.
- **Quarantine.** `fsck` moves a hash-mismatched object file to `<git-dir>/lfs/bad/<oid>`.
- **Logs.** Stored logs are files under `<git-dir>/lfs/` (subdirectory free); each file's name is the log name that `logs` lists.
- **Hooks.** `pre-push`, `post-checkout`, `post-commit`, `post-merge` in the hooks directory in use (`<git-dir>/hooks`, or `core.hooksPath`). Each is an executable shell script that runs `git orbulk <hook-name> "$@"`; the remaining text is free.
- **`.gitattributes` tracking line.** `<pattern> filter=lfs diff=lfs merge=lfs -text`, followed by ` lockable` when lockable is requested. With `--filename`, glob metacharacters in `<pattern>` are escaped with a backslash. An excluded-pattern line is `<pattern> !filter`, `<pattern> -filter`, or `<pattern> filter=` (empty value) (other attributes on the line free). Attribute files are written without the executable bit.

### Pointer document

- A non-empty pointer is UTF-8 text made of lines `<key> <value>\n`. Keys use `a-z`, `0-9`, `.`, and `-`. The first line is `version <identifier>`; then the remaining lines in ascending key order, including `oid sha256:<64 lowercase hex>` and `size <decimal byte count>`. The whole document is under 1024 bytes.
- `<identifier>` written by this build: `https://git-orbulk.example.com/spec/v1`. Legacy pre-release identifier that the reader also accepts: `https://cordage.example.com/spec/v1`.
- Content-extension lines are `ext-<n>-<name> sha256:<64 lowercase hex>`, where `<n>` is the extension's position in the clean order, counted from 0, and `<name>` is the registered extension name; they sort with the other keys. What the digest covers is stated in PRD FP-16.
- Empty content is the empty document.

### HTTP batch and basic transfer

- Batch request: `POST <endpoint>/objects/batch` with headers `Accept: application/vnd.git-orbulk+json` and `Content-Type: application/vnd.git-orbulk+json` (an optional `; charset=…` parameter may follow; `Accept` may list more types). Responses use the same media type.
- Request body: a JSON object with `operation` (`download` or `upload`), `objects` (a list of `{"oid": <hex>, "size": <integer ≥ 0>}`), optional `transfers` (a list of adapter names; `basic`, `tus`, `ssh`, or a custom agent name), optional `ref` (`{"name": <ref>}`), and optional `hash_algo` (`sha256`). Omitting `transfers` means `basic`.
- Response body: a JSON object with `transfer` (the selected adapter name) and `objects`. Each response object carries `oid` and `size` and either an `actions` object or an `error` object (`code`, `message`); in an `upload` batch, a response object with neither means the server already has the object.
- `actions` keys are `download`, `upload`, and `verify`. Each action is `{"href": <url>, "header": {<name>: <value>}, "expires_at": <RFC 3339 time>}` with `header` and `expires_at` optional.
- Basic download: `GET <href>` with the `header` map; the body is the raw object bytes. Basic upload: `PUT <href>` with the `header` map and the raw object bytes as body. Verify: `POST <href>` with the `header` map and a JSON body `{"oid": <hex>, "size": <integer>}`.

### Locking API

- Create: `POST <endpoint>/locks` with body `{"path": <repository-relative path>}`; reply `{"lock": <lock>}`. A conflict is HTTP 409 with the existing `lock`.
- List: `GET <endpoint>/locks` (optional query `path`, `id`); reply `{"locks": [<lock>, …]}`.
- Unlock: `POST <endpoint>/locks/<id>/unlock` with body `{"force": <boolean>}`; reply `{"lock": <lock>}`.
- Verify: `POST <endpoint>/locks/verify`; reply `{"ours": [<lock>, …], "theirs": [<lock>, …]}`.
- `<lock>` is `{"id": <string>, "path": <string>, "locked_at": <RFC 3339 time>, "owner": {"name": <string>}}`.

### Custom transfer agent protocol

- The client starts the program from `lfs.customtransfer.<name>.path` (with `.args`) and exchanges one JSON object per line on the agent's standard input and standard output. Object bytes travel only through file paths, never on this stream.
- Client to agent: `{"event": "init", "operation": "download"|"upload", "remote": <name>, "concurrent": <boolean>, "concurrenttransfers": <integer>}`; `{"event": "upload", "oid": <hex>, "size": <integer>, "path": <file to read>, "action": <action>}`; `{"event": "download", "oid": <hex>, "size": <integer>, "action": <action>}`; `{"event": "terminate"}`.
- Agent to client: `{}` in reply to `init`; zero or more `{"event": "progress", "oid": <hex>, "bytesSoFar": <integer>, "bytesSinceLast": <integer>}`; then `{"event": "complete", "oid": <hex>}` for an upload, or `{"event": "complete", "oid": <hex>, "path": <file holding the downloaded bytes>}` for a download. A failure is `{"event": "complete", "oid": <hex>, "error": {"code": <integer>, "message": <string>}}`.

### SSH helpers

- **SSH program.** The client runs the program named by the `GIT_SSH_COMMAND` environment variable (a shell command line), else by `GIT_SSH` (a program path run directly, without a shell), else by Git's `core.sshCommand`, else `ssh`. In the forms below `ssh` stands for that program: it receives any SSH options, then `[<user>@]<host>`, then the remote command line as its arguments.
- **Authenticate.** `ssh [<user>@]<host> git-orbulk-authenticate <repository-path> <download|upload>`. On success the helper prints a JSON object with `header` (map of HTTP headers to attach), optional `href` (endpoint URL to use instead of the derived one), and optional `expires_in` / `expires_at`.
- **Pure SSH transfer.** `ssh [<user>@]<host> git-orbulk-transfer <repository-path> <download|upload>`, then pkt-lines on the channel:
  - A packet is four lowercase hex digits giving the total packet length including those four, then the payload. `0000` is a flush (ends a request or reply); `0001` is a delimiter (separates text packets from a following body).
  - The server first sends capability lines, including `version=1`, then a flush. The client sends `version 1` and a flush; the reply is `status 200` and a flush.
  - A request is a command packet, zero or more argument packets, optionally `0001` and a body, then a flush. A reply is `status <code>`, zero or more argument packets, optionally `0001` and a body, then a flush.
  - `batch` (arguments `transfer=<adapter>`, `hash-algo=<algo>`, `refname=<ref>`; body lines `<oid> <size>`) → `status 200`, argument `hash-algo=<algo>`, `0001`, body lines `<oid> <size> <download|upload|noop>`.
  - `get-object <oid>` with argument `size=<n>` → `status 200`, `size=<n>`, `0001`, the raw object bytes.
  - `put-object <oid>` with argument `size=<n>`, then `0001` and the raw object bytes → `status 200`.
  - `verify-object <oid>` with argument `size=<n>` → `status 200`.
  - `quit` → `status 200`, then the channel closes.
  - An error reply is `status <4xx|5xx>`, `0001`, a message line, then a flush.

### Command reference

Each entry lists its options and positional arguments. Every printed text not described here is free text, the implementer's choice.

#### `checkout [<path>…]`
- `--to <file>`: with one of `--base`, `--ours`, `--theirs`, write that conflict stage of the single named path to `<file>`.
- `--base`, `--ours`, `--theirs`: select the stage.

#### `clean [<path>]`, `smudge [<path>]`, `filter-process`
- Git filter entries. `clean` and `smudge` read standard input and write the result to standard output. `filter-process` speaks Git's long-running filter protocol (version 2) on standard input/output.
- `smudge --skip`: write the input pointer through unchanged.

#### `clone <git-clone-arguments>`
- `--include <patterns>`, `--exclude <patterns>`: path filters for the download phase.
- `--skip-repo`: do not install repository hooks.
- The `git clone` options it accepts (including `--template <dir>` and `--config <key>=<value>`) and the repository and directory arguments are passed to `git clone`.

#### `completion <bash|fish|zsh>`
- Writes the completion script for that shell on standard output.

#### `dedup`
- `--test`: check support only.

#### `env`, `version`
- No options. Output forms are given above.

#### `ext [list]`
- Writes each registered extension on its own block of lines that names the extension, its clean and smudge commands, and its priority (layout free).

#### `fetch [<remote> [<ref>…]]`
- `--include <patterns>`, `--exclude <patterns>`: path filters, replacing the configured ones.
- `--recent`, `--all`, `--stdin` (refs from standard input, one per line), `--prune`, `--refetch`, `--dry-run`.
- `--json`: with `--dry-run`, write the plan as one JSON document on standard output (field names free).

#### `fsck [<committish> | <a>..<b>]`
- `--objects`, `--pointers`: run only that kind of check.
- `--dry-run`: report without moving files.
- Each finding is reported on standard output; wording free. Exit is non-zero when there is any finding.

#### `install`, `uninstall`, `update`
- `install`: `--force`, `--local`, `--worktree`, `--system`, `--file=<path>`, `--skip-smudge`, `--skip-repo`, `--manual`.
- `uninstall`: `--local`, `--worktree`, `--system`, `--file=<path>`, `--skip-repo`.
- `update`: `--force`, `--manual`.
- `--manual` writes the hook-integration instructions on standard output. They name each hook they concern (`pre-push`, `post-checkout`, `post-commit`, `post-merge`), including the hook whose existing body blocked installation; the rest of their wording is free.

#### `lock <path>`
- `--json`: write the created lock as a JSON object (field names free) on standard output.
- `--remote <name>`: target that remote's endpoint.

#### `locks`
- `--path <path>`, `--id=<id>`: restrict the listing.
- `--local`, `--cached`, `--verify`, `--json`.
- `--remote <name>`: target that remote's endpoint.
- Human listing: one line per lock, `<path>\t<owner-name>\tID:<id>` (padding between fields free). With `--verify`, the line of each lock owned by the current user also carries an ownership mark that no other line carries (mark free).
- `--json`: one JSON document on standard output in which each lock is an object containing its path as a string value (field names free).

#### `logs [show <name> | last | clear | boomtown]`
- No mode: write each stored log's name on its own line on standard output (nothing when there are none).
- `show <name>`: write that log's contents on standard output. `last`: same for the newest log.
- `clear`: delete all stored logs.
- `boomtown`: the diagnostic exception; exits non-zero and writes a new log.

#### `ls-files [<ref> [<ref>]]`
- `--long`, `--size`, `--name-only`, `--debug`, `--all`, `--deleted`, `--json`.
- `--include=<patterns>`, `--exclude=<patterns>`: path filters.
- Default line: `<oid> <mark> <path>`, where `<oid>` is the first 10 hex digits of the object id (all 64 with `--long`) and `<mark>` is one character showing whether the working-tree file is the full object or a pointer (characters free, one fixed character per state). `--size` appends the object size to the line (form free). `--name-only` prints only `<path>`. `--debug` prints a free-form block of lines per file.
- `--json`: one JSON document on standard output in which each file is an object containing its path as a string value and a boolean field (name free) telling whether the object is in the local store.

#### `merge-driver`
- `--ancestor <file>`, `--current <file>`, `--other <file>`, `--marker-size <n>`, `--output <file>`.
- The Git merge-driver command line is `git orbulk merge-driver --ancestor %O --current %A --other %B --marker-size %L --output %A`. On success the pointer of the merged content is written to the `--output` file.

#### `migrate <info|import|export> [<path>…]`
- `--include=<patterns>`, `--exclude=<patterns>`, `--include-ref=<ref>`, `--exclude-ref=<ref>`, `--everything`, `--yes`. `<ref>` is a full ref name or a short local branch name.
- `info`: `--pointers=<follow|ignore|no-follow>`. Writes one line per file type on standard output naming the type (for example its extension pattern) and carrying the total size and the file count as separate figures (order, units, and layout free).
- `import`: `--fixup`, `--no-rewrite` (positional `<path>…` are the paths to convert), `--skip-fetch`.

#### `pointer`
- `--file=<path>`: the local file (payload to hash, or the document to check).
- `--pointer=<path>`: the other pointer, for compare.
- `--stdin`: read the pointer (to check, or the other pointer to compare) from standard input.
- `--check`, `--strict`, `--no-strict`.
- Generate: writes the pointer document on standard output (explanatory text on standard error).
- Check: exit 0 for a valid pointer, 1 for an input that is not a valid pointer, and, with `--strict`, 2 for a valid pointer that is not canonical. Nothing else is required on output.
- Compare: exit 0 for match; non-zero for mismatch and for malformed, with a message on standard error that differs between mismatch and malformed (wording free).

#### `post-checkout <previous-commit> <new-commit> <flag>`, `post-commit`, `post-merge <squash-flag>`
- Git hook entries. `<flag>` is `1` for a branch checkout and `0` for a file checkout. An initial checkout passes forty `0` characters as `<previous-commit>`. `<squash-flag>` is `0` or `1`.

#### `push` / `pre-push` lock-verification advisory
- The lock-verification advisory (PRD FP-10) is written on standard error and contains the URL-scoped key `lfs.<endpoint-url>.locksverify`; its wording is free.

#### `pre-push <remote> [<url>]`
- Reads Git's pre-push lines `<local-ref> <local-sha> <remote-ref> <remote-sha>` on standard input.
- `--dry-run`: write the plan, one object per line, on standard output (designation of each object free).

#### `prune`
- `--dry-run`, `--force`, `--recent`, `--verify-remote`, `--verify-unreachable`, `--when-unverified=<halt|continue>`, `--verbose`.
- `--verbose` writes on standard output one line per deleted object (with `--dry-run`, per object that would be deleted) carrying its 64-hex `<oid>`; the rest of each line (for example its size) is free.
- `--verify-remote` sends the prune remote a `download` batch request listing the candidates (request and reply forms as under **HTTP batch and basic transfer**).

#### `pull [<remote> [<ref>…]]`
- `--include <patterns>`, `--exclude <patterns>`.

#### `push <remote> [<ref>…]`
- `--all`, `--dry-run`, `--stdin` (refs, or oids with `--object-id`, one per line).
- `--object-id`: the arguments after `<remote>` are object ids.
- `--dry-run` writes the plan, one object per line, on standard output (designation of each object free).

#### `standalone-file`
- Standalone transfer agent for `file://` URLs; speaks the custom transfer agent protocol on standard input/output.

#### `status`
- `--porcelain`: one line per path, `<XY> <path>`, where `<XY>` is a two-character status code in the style of `git status --porcelain`.
- `--json`: one JSON document on standard output in which each listed path appears as a string value (field names free).
- Default human listing: free layout, with each listed path on its own line.

#### `track [<pattern>…]`, `untrack <pattern>…`
- `track`: `--lockable`, `--not-lockable`, `--filename`, `--no-modify-attrs`, `--dry-run`, `--verbose`, `--no-excluded`, `--json`.
- Listing (no patterns): the tracked patterns, then the excluded patterns, each part under its own heading line (heading wording free), one pattern per line. `--json` writes one JSON document in which each pattern appears as a string value (field names free).
- `--verbose` names each touched file on its own line.
- `--dry-run` writes on standard output a line for each pattern that would be tracked, carrying the pattern text; wording free. Nothing is written to disk.

#### `unlock <path>`
- `--id=<id>`: unlock by id instead of path.
- `--force`, `--remote <name>`.
