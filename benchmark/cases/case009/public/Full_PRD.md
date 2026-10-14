# Git Orbulk — Full Product Requirements Document

## Product overview

**Git Orbulk** (VCS Large Object Store) is a command-line Git extension and accompanying client–server specification for versioning large files alongside an ordinary Git repository. Instead of storing large file bytes as Git blobs, Git Orbulk stores compact **pointer** blobs in Git and keeps the real content in a separate object store that is synchronized with a remote Git Orbulk endpoint when the user fetches or pushes.

The finished product is a single compiled command-line utility named `git-orbulk`. Users interact with it as a Git extension (`git orbulk <command>`): each capability is reached by choosing a Git Orbulk subcommand (and, for low-level filter and hook paths, by Git invoking those subcommands automatically). The client ships as a self-contained binary for Mac, Windows, Linux, and FreeBSD, and is intended to be used as that binary—not as a library API for other programs to import.

This document specifies **user- and integrator-observable behavior only**. Exact published symbol names, option tokens, configuration-key spellings, wire media-type tokens, output forms, and other Interface Contract details are out of scope here. Every feature point below corresponds to behavior that exists in the finished product. Feature points are ordered so foundational capabilities come first; a later feature point may refine an earlier one only when it says so explicitly.

## Terminology

| Term | Meaning in this PRD |
| --- | --- |
| **Pointer** | A small UTF-8 text blob stored in Git in place of a large file. It names the content hash algorithm, object id, and byte size of the real content. |
| **LFS object** | The full file bytes identified by a pointer’s object id, stored outside Git’s object database. |
| **Local object store** | On-disk cache under the repository’s Git directory (by default under `.git/lfs/objects`) where Git Orbulk keeps objects locally. |
| **Endpoint** | The remote Git Orbulk service URL used for batch negotiation, transfers, and locking for a given Git remote. |
| **Batch API** | The request/response exchange that asks the endpoint which objects need upload or download and how to transfer them. |
| **Basic transfer** | The default transfer style: download via HTTP GET and upload via HTTP PUT of raw object bytes at URLs supplied by batch negotiation. |
| **Clean** | Converting working-tree file bytes into a pointer (and storing the object locally) as Git stages content. |
| **Smudge** | Converting a pointer back into working-tree file bytes (fetching the object if needed) as Git checks content out. |
| **Track pattern** | A path pattern recorded in Git attributes so matching paths use the Git Orbulk filter. |
| **Lock** | A server-side exclusive claim on a repository-relative path that blocks other users from pushing changes to that path when lock verification is enabled. |
| **Porcelain command** | A user-facing Git Orbulk subcommand (track, fetch, push, and similar). |
| **Plumbing command** | A low-level Git Orbulk subcommand intended mainly for Git filters, hooks, or automation (clean, smudge, filter-process, pre-push, and similar). |
| **Unpushed** | An LFS object referenced by a commit that is not reachable from any remote-tracking ref of the relevant remote. Whether the endpoint happens to hold the bytes does not change this. |

## Public command inventory

The product exposes a fixed, finite set of subcommands. Porcelain commands: checkout, clone, completion, dedup, env, ext, fetch, fsck, install, lock, locks, logs, ls-files, migrate, prune, pull, push, status, track, uninstall, unlock, untrack, update, and version. Plumbing commands: clean, filter-process, merge-driver, pointer, post-checkout, post-commit, post-merge, pre-push, smudge, and standalone-file. Built-in help covers the product and those subcommands. Feature points below group these entries by capability; they do not invent additional commands. The direct binary and the Git-extension form accept the same subcommands, options, and arguments and behave identically.

## Non-functional constraints

- **Form factor:** One command-line binary that Git can locate and invoke; not a stable embeddable library API or ABI.
- **Layout.** The default make goal emits `git-orbulk` under the built tree’s `bin` directory.
- **Platforms:** Builds and runs on Linux, macOS, Windows, and FreeBSD-class systems, with a recent Go toolchain, GNU make, and a working Git installation (Git 2.0.0 or newer; recent Git recommended).
- **Hardware:** CPU-only. No GPU or accelerator is required.
- **Storage model:** Large content is never required to live as ordinary Git blobs for tracked paths; Git history holds pointers, and the local object store plus remotes hold objects.
- **Empty files:** An empty working-tree file maps to an empty pointer (passthrough); empty content is not forced through the hashed-object path.
- **Protocol hash:** Newly written pointers use SHA-256 object ids expressed as lowercase hexadecimal, prefixed by the protocol’s SHA-256 hash-method label (exact token lives in the Interface Contract). SHA-256 is the only hash method current clients write.
- **Protocol constants:** Exact version-identifier strings, JSON media-type tokens, hash-method labels, and similar wire literals are fixed by the Git Orbulk specification and appear in the Interface Contract. This PRD states their behavioral roles (exact string comparison, required headers).

## Core capabilities (global)

Every feature point below is real behavior of the CLI against real Git repositories and, where applicable, real HTTP/SSH endpoints. Filters store and restore real objects; fetch and push really contact the endpoint; lock commands really talk to the locking service; migrate really rewrites history and attributes.

The Git-extension form of every subcommand runs the `git-orbulk` binary that Git finds on the executable search path; when Git finds none, the invocation fails with a non-zero exit and changes nothing. A repository-bound command run where its Git repository prerequisites are absent fails with a non-zero exit.

## Non-goals

- Providing a stable Go (or other language) library API or ABI for third-party imports.
- Implementing the remote Git Orbulk **server**; this product is the client (plus protocol documentation the client obeys).
- Guaranteeing every forge already speaks every optional transfer style (custom agents, tus uploads, pure SSH); the client must implement the negotiation and built-in paths described here when the peer supports them.
- Automatic undo of history rewrite after migrate; users must validate and force-push carefully themselves.
- Enabling the text merge driver by default on every tracked path; track records the ordinary `lfs` merge attribute, and Git’s default merge of pointer text remains the default until a user separately configures a merge driver (FP-18).

---

## Feature points

### FP-01: Command-line entry, help, version, and environment report

**Public entry:** The `git-orbulk` binary as a Git extension top-level command (`git orbulk`), with nested subcommands; the version-reporting path (`git orbulk version`); the `git orbulk env` subcommand; and built-in help for the product and individual subcommands (`git orbulk help` and per-command help).

**Normal behavior:**

- Invoking Git Orbulk with no subcommand, or asking for help on the product or a subcommand, prints user-facing usage information and exits successfully. Help for a subcommand covers that subcommand and differs from the product-wide help.
- The version path reports that this build is Git Orbulk together with this build’s version identity. The identity is a fact of the build: it is the same in every repository and on both entry forms.
- The environment-report subcommand prints the effective Git Orbulk-related configuration a user needs to debug setup: this build’s version identity (the same identity the version path reports), the endpoint that would be used for each remote, the filter configuration summary, and related environment facts (local directories, transfer, fetch-recentness and prune settings, configured include/exclude patterns, storage location, configured agents). For each remote, the report names the Git Orbulk server URL that would be used for that remote, kept separate from the remote’s own Git URL and from every other remote’s endpoint. That endpoint reflects discovery and every override in effect (FP-06). The filter summary shows the effective values of the three `lfs` filter settings: a value that is configured appears, and a value that was never configured does not.

**Boundary / error behavior:**

- An option token that the invoked entry does not define — whether given at the top-level entry or after a known subcommand — fails with a non-zero exit and a clear error on standard error. Where a command defines mutually incompatible options, those combinations fail the same way. Unknown subcommands likewise fail with a non-zero exit and a clear error on standard error.
- The environment report works in a repository that has remotes but has never transferred objects: each remote’s endpoint is still the URL that would be used after derivation or override. With no remotes, the report still succeeds and still prints the effective configuration and version identity.

---

### FP-02: Install, uninstall, and repository hook update

**Public entry:** The `git orbulk install`, `git orbulk uninstall`, and `git orbulk update` subcommands.

**Normal behavior:**

- Install configures Git’s clean and smudge filters under the filter name `lfs` (and the long-running process-filter equivalent that modern Git prefers) in the chosen Git configuration scope so Git will invoke Git Orbulk for attributed paths. By default it writes to the user’s global Git configuration and does not overwrite an existing non-Git-Orbulk filter definition unless the user forces replacement. Git Orbulk’s own filter values — both the ordinary ones and the skip-smudge ones — are not foreign: install may replace one with the other without forcing.
- When install runs inside a repository (unless the user asks to skip repository changes), it installs Git Orbulk’s repository hooks into the repository’s hooks directory, or into the directory named by Git’s shared hooks-path setting when that setting is in effect and the installed Git is new enough to support it (Git 2.9.0 or newer). This holds for every scope, including an explicit configuration file. The installed hooks are: **pre-push** (uploads LFS objects before Git refs update), **post-checkout**, **post-commit**, and **post-merge** (enforce lockable working-tree permissions—see FP-10). Outside a repository, install writes the filters in the chosen scope and creates no hook files.
- Install supports scopes: global (default), local repository, worktree (when Git is at least 2.20.0 and worktree config is enabled), system, or an explicit configuration file path. Combining more than one of local, worktree, system, and explicit-file is invalid. It can install filters while skipping smudge downloads (so clones do not auto-download objects), and can install filters while skipping repository hook installation.
- When an existing hook body would block automatic installation, **manual mode** leaves that hook file unchanged and prints instructions telling the user how to add Git Orbulk’s hook invocations to their existing hooks themselves. Those instructions are hook-integration guidance, not a filter-install success message or an error; printing the integration instructions for all four hooks is acceptable.
- Uninstall reverses filter configuration in the chosen scope (global by default; a narrower scope leaves global values unchanged) and, when run in a repository context analogous to install (and not asked to skip repository changes), removes the Git Orbulk hooks for all four hook types above from the hooks directory in use. Skipping repository changes leaves the hook files in place.
- Update refreshes repository hooks for the current repository so Git Orbulk’s hook entry points remain installed after Git or repository layout changes. For each of the four hook types above:
  - If the hook file is missing, update installs the current standard Git Orbulk hook body for that type (a script that invokes Git Orbulk for that hook).
  - If the hook file exists and its body is empty, or is already exactly the current standard body, or is a body that an earlier version of this product installed for that hook type (which earlier bodies are recognized is the implementer's choice), a non-force update leaves an already-current body unchanged and silently replaces an empty or earlier body with the current standard body.
  - If the hook file exists and its body matches none of those upgradeable cases (a custom or foreign hook), a non-force update leaves that file unchanged and the update fails for that conflict. Force overwrites such a file with the current standard body. Manual mode on that same conflict leaves the foreign body unchanged and prints the hook-integration guidance described above instead of writing over the foreign body.

**Boundary / error behavior:**

- Install without force that encounters pre-existing non-Git-Orbulk filter settings leaves those settings intact and fails.
- A scope that cannot be used fails and writes nothing in any other scope: local or worktree scope outside a repository, worktree scope on a Git version that lacks the required worktree configuration support, and a system scope that cannot be written all fail without touching global filters.
- Uninstall outside a repository still reverses filter configuration in the non-repository scope it targets and does not create or modify any repository files. Update outside a repository fails and does not modify filters or hooks.
- Non-force install or update that encounters a custom or foreign hook body fails without modifying that hook file. Force overwrites as described above. Manual mode on that conflict path preserves the foreign body and prints the hook-integration guidance described above rather than rewriting the file.

---

### FP-03: Pointer format and pointer utility

**Public entry:** The `git orbulk pointer` plumbing subcommand, and every clean path that writes pointers into Git.

**Normal behavior:**

- A pointer is a UTF-8 text document of key/value lines. Each line is one key, one space, one value, and a Unix newline. Keys use only lowercase letters, digits, dot, and hyphen. Lines after the version line are sorted by key ascending. Values contain no carriage returns or newlines. The whole pointer must stay under 1024 bytes including any extension lines. There is exactly one canonical encoding for a given pointer payload.
- The first key is always the version key. Its value is a fixed protocol version identifier compared by exact string equality (no URL parsing or case folding). Newly written pointers use the current Git Orbulk v1 protocol version identifier, which is distinct from the still-readable legacy pre-release identifier. The Interface Contract names those two exact strings in those two roles.
- Required keys after version include: an object-id key whose value is the hash-method label, then a colon, then a lowercase hex digest (SHA-256 for current clients), and a size key giving the object size in bytes as a decimal integer.
- Empty file content corresponds to an empty pointer document (passthrough): empty working-tree bytes are not rewritten into a hashed pointer body. The empty document is the canonical pointer of empty content, a valid pointer without the keys a non-empty pointer requires: generating from an empty file writes it, and ordinary and strict check accept it.
- Pointer blobs stored in Git preserve the executable bit of the replaced working-tree file.
- Content-extension metadata lines (FP-16) are part of a valid pointer document and of its single canonical encoding, which places them in the product’s canonical key order relative to the required keys.
- The reader is tolerant where the writer is strict. Any document that satisfies the pointer grammar above is a valid pointer. The reader additionally accepts carriage-return line endings, a missing final newline, the legacy pre-release version identifier, and extension lines out of canonical order; such a document is a valid pointer but is not canonical. A document that is exactly what Git Orbulk itself would write is canonical.
- The pointer subcommand can generate a pointer from a local file; compare that generated pointer to another pointer supplied from a file or standard input; and check whether input is a valid pointer, with an optional strict mode that also requires the canonical encoding. A generated pointer is canonical.
- Compare reports one of three outcomes: match (the other pointer is a valid pointer equal to the one generated from the file), mismatch (the other pointer is valid but differs), or malformed (the other input is not a valid pointer). The outcome depends only on that relation, whatever the files contain, and the same three outcomes apply when the other pointer comes from standard input.

**Boundary / error behavior:**

- Ordinary check succeeds for every valid pointer and fails for any input that is not one. Strict check succeeds only for a canonical pointer; for a valid-but-not-canonical pointer it fails with a status distinct from the status for an invalid input.
- Input that breaks any rule of the pointer grammar above, other than the tolerated forms listed above, is not a pointer: check rejects it and filter smudge passes it through as ordinary content.
- Invoking check without exactly one of file-path or standard-input sources is invalid. Combining check with a compare-pointer file is invalid. Combining strict and non-strict check flags is invalid.

---

### FP-04: Track and untrack patterns

**Public entry:** The `git orbulk track` and `git orbulk untrack` porcelain subcommands.

**Normal behavior:**

- Track with one or more patterns appends Git Orbulk filter attributes for those patterns to the appropriate `.gitattributes` file (patterns follow Git attributes / gitignore glob rules). Track records the pattern text it is given and does not expand it into matching filenames. Existing unrelated attribute lines remain. After track or untrack, the user must commit attribute changes themselves; Git Orbulk does not create the Git commit.
- Each newly written tracking line names the filter, diff, and merge attributes as `lfs`, disables Git text conversion for the pattern, and may additionally mark the pattern lockable. Those four attribute roles (filter, diff, merge, text-disabled) are the finite set written for an ordinary track; lockable is the additional optional attribute and is written only when requested.
- Track with no patterns lists currently tracked patterns. An **excluded pattern** is an attributes line that names the filter attribute in a form that disables or unsets filtering for that pattern (Git’s attribute negation or unset forms for the filter attribute), rather than enabling the `lfs` filter value. When such excluded patterns are present alongside tracked `lfs` filter patterns, the default listing shows those excluded pattern texts in a portion of the listing separate from the tracked patterns. A mode that avoids listing excluded patterns still lists tracked patterns but omits that excluded-pattern portion. A machine-readable JSON listing mode is available when listing (and must not be combined with pattern arguments).
- Track can treat arguments as literal filenames (escaping glob metacharacters in the attributes file, so the recorded line matches exactly that path and no other path the same text would match as a glob), mark patterns lockable (working-tree files become read-only unless locked—see FP-10), clear lockable while keeping the `lfs` filter enabled, or dirty matching previously Git-tracked index entries without rewriting attributes so Git will re-clean files into Git Orbulk (also when the attributes already carry that pattern).
- Dry-run reports what would change without creating or modifying any file and implies detailed logging. Verbose still applies the track attribute mutation (unlike dry-run) and additionally names the matching previously Git-tracked files that would be touched.
- Untrack removes the matching Git Orbulk tracking lines (those that enable the `lfs` filter for the given patterns) from attributes and leaves other tracked patterns and unrelated lines in place. Untrack does not write excluded-pattern lines; excluded patterns are arranged by placing the disabling/unsetting filter attribute forms in attributes files directly.

**Boundary / error behavior:**

- Patterns must be quoted by the user in shells that expand globs; Git Orbulk records the pattern text it is given.
- JSON list mode combined with pattern arguments is invalid and writes nothing.
- Track/untrack outside a Git repository fails and creates no attributes file.

---

### FP-05: Clean, smudge, filter-process, and local object store

**Public entry:** The clean, smudge, and filter-process plumbing subcommands as configured by install (FP-02) and attributes (FP-04); Git add/checkout as the user-visible trigger.

**Normal behavior:**

- **Clean:** Git supplies file bytes on standard input. For non-empty content that is not already a pointer document, Git Orbulk computes the SHA-256 digest of those bytes, stores the object in the local object store when absent under the repository’s LFS objects directory using the content-addressed nested path derived from the object id (first two hex digits, next two hex digits, then the full object id), and writes a canonical pointer to standard output; an already-pointer input is written through without hashing or storing a nested object. Clean does not upload to a remote.
- **Smudge:** Git supplies blob bytes on standard input. If the content is recognized as a pointer, Git Orbulk loads the object from the local store or downloads it from the endpoint, then writes raw object bytes to standard output. Non-pointer content is copied through unchanged.
- **Filter-process:** Speaks Git’s long-running filter protocol and services clean and smudge requests with the same semantics; this is the preferred path when modern Git is configured to use it.
- Smudge and filter-process honor include/exclude path settings (configuration or `.lfsconfig`): when include is set, only matching paths are smudged to real content; when exclude is set, matching paths are left as pointers. Skip modes (command flag, skip-smudge environment setting, or install option) write the pointer through without downloading, even when the object is already in the local store, and succeed even when no endpoint is reachable.
- Local object store root defaults under the Git directory’s `lfs` namespace. A configured storage location replaces that default store root — the parent of the LFS objects directory — rather than replacing the objects directory itself. The LFS objects directory remains a child of the relocated root, so cleaned objects still appear under that root using the same objects-directory-plus-shard layout as the default and are not written at the default Git-directory objects path. Objects are content-addressed and shared across commits that reference the same oid.

**Boundary / error behavior:**

- If download fails during smudge, the default is to fail the filter operation; configuration or environment may instead allow checkout to succeed while leaving pointer text in the working tree (explicit skip-download-errors behavior).
- Modified working-tree files are never overwritten by checkout-style smudging of placeholders (see also FP-08).
- Missing local object without a reachable endpoint causes smudge failure unless skip/smudge-disable settings apply.

---

### FP-06: Endpoint discovery and authentication

**Public entry:** Implicit behavior of any transfer or lock command; visible via `git orbulk env` (FP-01); configuration keys that override discovery.

**Normal behavior:**

- By default the client derives the Git Orbulk endpoint from the Git remote URL by appending the conventional `.git/info/lfs` suffix (whether or not the remote URL already ended in `.git`), including translating SSH-style Git remotes into the corresponding HTTPS endpoint host/path form for HTTP API use. A Git-protocol remote is rewritten into an HTTP LFS endpoint under that same derivation: unset, the rewrite uses the secure HTTP scheme; the configured Git-protocol setting (FP-15) selects the scheme used for that rewrite. SSH-style remotes always derive an HTTPS endpoint and ignore that setting.
- Users may override the endpoint with repository or global LFS URL settings, per-remote LFS URL settings, and separate push URL overrides when upload must hit a different host than download. Precedence: a repository or global LFS URL replaces derivation for every remote, including a remote that also has a per-remote LFS URL; a per-remote LFS URL applies to that remote only and only when no repository or global LFS URL is set; otherwise the endpoint is derived. A push URL override changes only the endpoint used for upload: the download endpoint (and the endpoint the environment report shows for the remote) stays as it was, and uploads contact the push endpoint.
- Default remote selection: the current branch’s remote if set, otherwise a configured LFS default remote name, otherwise the single existing remote if there is only one, otherwise `origin`. Upload and lock operations use the current branch’s push remote if set, otherwise a configured LFS push-default remote name, then the same single-remote / `origin` fallback.
- For SSH Git remotes on the hybrid HTTPS API path (not the pure SSH transfer path of FP-17), the client runs the remote helper command **git-orbulk-authenticate** over SSH with the repository path and operation (`download` or `upload`). On success, the helper’s JSON supplies authorization headers and may supply an alternate endpoint URL and expiry hints. Those headers are attached to subsequent API requests; when that JSON names an alternate endpoint URL, subsequent API requests use that URL rather than the derived HTTPS form.
- Otherwise the client uses Git’s credential helpers and HTTP Basic authentication material, and may use credentials embedded in URLs when present (discouraged but supported). When the URL-scoped access setting for an endpoint is basic, the very first API request to that endpoint already carries HTTP Basic authorization; without it, the first request carries no authorization and credentials are supplied after the server asks for them. Kerberos is supported where the environment provides it. NTLM is not supported on current major versions (Git Orbulk 3.0 and later).

**Boundary / error behavior:**

- Failed SSH authentication helper invocation surfaces the helper’s error output and fails the operation.
- Invalid or missing credentials make the API requests, and the command, fail with a non-zero exit.
- When no endpoint can be determined (none configured and none derivable), a transfer or lock command fails before any transfer.

---

### FP-07: Batch negotiation and basic object transfer

**Public entry:** Used internally by fetch, push, pull, clone, smudge, and related commands; exercised whenever objects move to or from an HTTP(S) endpoint.

**Normal behavior:**

- The client posts a batch request to the endpoint’s objects batch path. Each batch request must send an Accept header that names the protocol’s designated Git Orbulk JSON media type, and must send a Content-Type header that carries that same media type; servers must accept an optional charset parameter on Content-Type. Batch responses are expected to use that media type as well.
- The request names the operation (`download` or `upload`), optionally advertises supported transfer adapters (servers must assume **basic** when the list is omitted), optionally includes the Git ref name for authorization schemes that need it, lists objects by oid and size (size at least zero), and may name the hash algorithm (default SHA-256).
- The response selects a transfer adapter and, per object, either indicates the object already exists on the server, returns transfer actions with href/header/expiry metadata, or returns per-object errors. An object the server already has is not uploaded again.
- **Basic download:** HTTP GET of the action href with supplied headers; response body is raw object bytes. Partial or resumable downloads may reuse HTTP range requests when applicable.
- **Basic upload:** HTTP PUT of raw bytes to the action href with supplied headers. A verify action, when present, is performed after upload as the protocol requires. Upload content typing may be auto-detected from the object or forced to a generic binary stream via configuration.
- When the tus transfer path is enabled in configuration and basic-transfers-only is not enabled, the client advertises the tus adapter in the batch request’s transfer list in addition to basic.
- When basic-transfers-only is enabled, the advertised transfer list contains no adapter other than basic (or is omitted), whatever else is configured.
- Object transfers run concurrently, bounded by configuration: when several objects need transferring, up to the configured number of object transfers are in flight at the same time, and never more (default 8). Failed transfers are retried up to the configured retry count with the configured delay between attempts. Progress may be shown on a terminal or forced via configuration/environment (FP-15), and may be mirrored to a progress file when requested.
- HTTP timeouts are configurable in whole seconds: the connection-initiation bound limits how long establishing a connection may take, the TLS-handshake bound limits the handshake, and the activity bound limits how long a transfer may make no progress; exceeding any of them fails that attempt. Keepalive is an ordinary HTTP-client setting. The client honors Git's own TLS certificate-verification setting on its endpoint requests: with verification turned off, an endpoint certificate that cannot be verified is accepted.

**Boundary / error behavior:**

- Per-object batch errors fail that object’s transfer and cause the overall command to fail when any required object cannot be transferred.
- Expired action URLs result in visible failure (and may trigger re-auth / retry according to client policy) rather than treating missing content as success.
- Servers that only understand basic transfer remain interoperable: a client that advertises basic (or omits the list) completes the transfer with basic GET/PUT.

---

### FP-08: Fetch, pull, checkout, and clone

**Public entry:** The `git orbulk fetch`, `git orbulk pull`, `git orbulk checkout`, and `git orbulk clone` porcelain subcommands.

**Normal behavior:**

- **Fetch** downloads Git Orbulk objects for the given remote and refs into the local object store without updating the working tree. With no remote and refs, it fetches the objects of the current checkout from the default remote (not other branches); a named remote and ref fetch that ref. It supports include/exclude path filters (command-line filters replace configured ones), fetching recent refs/commits per recentness settings, fetching all objects reachable from the given refs’ history, or from all refs when none are given (backup/migration mode that ignores configured include/exclude), reading refs from standard input in place of the default, pruning after fetch, refetching objects already present, dry-run, and JSON reporting of the transfer plan.
- Fetch’s prune option runs, after a successful fetch, the same retention and deletion as the prune command (FP-12); without it, fetch deletes nothing.
- Refetch downloads objects even when they are already in the local store; ordinary fetch does not download an object already present.
- Dry-run downloads nothing and writes nothing to the local store. With JSON reporting, the dry-run prints the transfer plan as a JSON document that reflects exactly what a real run would transfer: it is the same for the same repository state and options, and changes whenever the set of objects a real run would transfer changes.
- **Checkout** materializes working-tree files from local objects for the current ref when the working tree has missing files or pointer placeholders, without downloading. Path arguments (globs) restrict which paths are updated. Modified working-tree files are never overwritten. In merge conflicts, checkout can extract the base, ours, or theirs stage of an LFS path, writing that stage’s object bytes into a separate output file. On sufficiently new Git, attribute matching follows index/worktree attribute rules described in the product’s checkout documentation (including sparse/partial clone caveats).
- **Pull** is the composition of fetch for the current ref plus checkout into the working tree, with the same include/exclude handling: paths excluded by configuration or not selected by include stay pointers and are not downloaded.
- **Clone** wraps Git clone (forwarding Git clone’s own options) while deferring LFS downloads during the clone, then performs a pull-style batch download, and installs the four repository hooks unless asked to skip that installation. Include/exclude options and configured include/exclude apply to the download phase; a command-line include replaces the configured one.

**Boundary / error behavior:**

- Fetch/pull fail when the remote endpoint is unreachable or authentication fails (FP-06/FP-07), and then leave the local store and working tree unchanged.
- Checkout in a bare repository has no effect.
- All-mode fetch cannot be combined with recent or include/exclude flags; such an invocation fails and downloads nothing.
- When the LFS download phase of clone fails, the command exits non-zero, while the Git repository produced by the underlying clone may remain.
- When repository hook installation during clone fails and was not intentionally skipped, the command exits non-zero, while the Git repository produced by the underlying clone may remain.

---

### FP-09: Push and pre-push hook

**Public entry:** The `git orbulk push` porcelain subcommand; the `git orbulk pre-push` plumbing subcommand installed as a Git hook (FP-02); ordinary `git push` as the user-visible trigger.

**Normal behavior:**

- **Push** uploads locally referenced LFS objects for the given remote and refs. By default it considers only objects in commits not already reachable from that remote’s remote-tracking refs, and only for the refs given. **Push-all** considers every object reachable from the given refs’ history, or from all local refs when none are given (objects referenced only by remote-tracking refs are not local refs). **Object-id mode** uploads the named objects by oid to the remote’s upload endpoint, whatever the commit range would select. It also supports dry-run and reading refs (or, in object-id mode, oids) from standard input in place of the arguments.
- **Pre-push** reads Git’s pre-push stdin lines (local ref, local sha, remote ref, remote sha). For non-delete updates, it uploads LFS objects required by the commits being pushed. Branch deletion pushes do not upload objects.
- **Dry-run** (push and pre-push): the command prints a plan that names each object that would be uploaded (in a designation the implementer chooses) and transfers none of their bytes. The plan is the same for the same pending set and differs when the pending set differs; with nothing pending it names no object.
- An environment skip-push setting makes the pre-push hook upload nothing, allowing Git push to update refs without LFS uploads when explicitly requested.
- A missing local object normally makes the push fail without uploading it. When allow-incomplete-push is enabled, a push whose objects are missing locally still succeeds: Git refs advance and the missing objects are not uploaded.
- A successful push that uploaded the objects required for the pushed refs leaves those objects available at the endpoint so a subsequent clone or pull of those refs restores the corresponding tracked files as working-tree bytes.

**Boundary / error behavior:**

- If required uploads fail, pre-push fails and Git aborts the push.
- When lock verification is enabled (FP-10), pushes that would update paths locked by others are rejected and upload nothing.
- Push to a remote without a workable endpoint fails visibly.

---

### FP-10: File locking

**Public entry:** The `git orbulk lock`, `git orbulk unlock`, and `git orbulk locks` porcelain subcommands; the `git orbulk post-checkout`, `git orbulk post-commit`, and `git orbulk post-merge` plumbing commands installed as Git hooks (FP-02); lock verification during push/pre-push; lockable attributes from track (FP-04).

**Normal behavior:**

- **Lock** creates a server-side lock for a repository-relative path (nested paths included). The path need not already exist in the working tree (locking a locally missing path still requests creation of a server-side lock). JSON output mode is available on success and creates the same lock. A lock is visible to every client of the same endpoint.
- **Unlock** removes a lock by path or by lock id (exactly one of those two selectors); only the selected lock is removed. A force mode asks the server to remove the lock even when another user owns it, when the server permits that, and also skips the local clean-status check described below; without force, a lock owned by another user stays held. Optional remote selection chooses which endpoint’s locks are targeted; locks on other remotes’ endpoints are untouched.
- **Locks** lists locks from the server. Filters by path or by id restrict the listing to matching locks (no match lists none). A local mode lists the locks this repository itself created, from its local record, without contacting the server (it succeeds when the server is unreachable and does not show other users’ locks). That record belongs to the repository, not to the endpoint configured when the lock was taken, so it still lists those locks after the configured endpoint changes. A cached mode lists the result of the last successful server listing without contacting the server again, so locks created on the server since then do not appear. A verify mode asks the server which locks the current user owns and marks those locks in the listing; locks owned by others are not marked. A JSON mode prints the listing as JSON.
- Lockable-tracked files are set read-only in the working tree when not locked by the user (controllable via configuration / environment), and become writable when locked.
- After checkout, commit, or merge, the corresponding post-* hooks re-apply read-only permissions on lockable paths that the local user does not currently hold a lock for; non-lockable paths and paths the user holds a lock for are left as they are. Post-commit covers the paths changed in HEAD (especially newly added lockable files). Post-merge covers every lockable path in the working copy, including ones the merge did not touch. Post-checkout covers every lockable path in the working copy on a file checkout or on an initial checkout (previous revision all zeros); on an ordinary branch, tag, or commit checkout it covers only the lockable paths that changed between the previous and new revisions.
- Push paths consult the locking API’s verify capability when locks-verify is enabled for the endpoint, refusing pushes that violate foreign locks. Configuration can force verification on or off. When it is not configured, push still consults the verify capability; when the endpoint supports it, push prints an advisory that names the locks-verify setting and suggests enabling it, and goes on with the push. A forced-on or forced-off push prints no such advisory. A push that names objects by object id updates no refs and does not verify locks.

**Boundary / error behavior:**

- Locking a path that resolves to a directory in the working copy fails and creates no lock.
- Creating a lock when one already exists for that path fails with a conflict outcome from the server; the existing lock remains the only one.
- Unlock by path without force fails, leaving the lock held, when that path itself has uncommitted working-tree changes, or when the path was previously tracked and is now missing from the working tree (Git status can see the deletion). The check concerns only the path being unlocked: changes to other paths do not block it. Unlock by path of a path that has never entered the working tree or the index (no status entry) proceeds and still requests the server-side unlock. Unlock by lock id does not apply that local check. Force skips that local check and still requests the server-side unlock.
- Unlock invoked with both a path and a lock id, or with neither, is invalid and removes nothing.
- Lock commands fail when the endpoint lacks locking support or authentication fails.
- Local-only and cached listing modes never present locks they did not obtain from their local record or from the last successful server listing.
- Invoking a post-* plumbing command outside the Git hook context may warn that the user should run update to install hooks.

---

### FP-11: Status and ls-files inspection

**Public entry:** The `git orbulk status` and `git orbulk ls-files` porcelain subcommands.

**Normal behavior:**

- **Status** (non-bare repositories only) lists paths that are not yet pushed (Git Orbulk objects reachable from the current ref but not from the current branch’s remote-tracking ref), differ between index and HEAD, or differ between working tree and index—mirroring the intuition of what would be uploaded, committed, or staged. The unpushed listing names only Git Orbulk-related paths and is empty once the remote-tracking ref has caught up. Of the index/HEAD and working-tree/index listings, the default human listing and porcelain name ordinary Git paths that differ in those slots as well as Git Orbulk-related ones; JSON names only Git Orbulk-related paths. Porcelain and JSON scripting modes cover the index/HEAD and working-tree/index listings only, not the unpushed set.
- **Ls-files** lists Git Orbulk files at a ref (when no ref is given: the current branch including the index — a path present only in the index is listed, and for a path also in the tree the index version, with its object id, takes precedence; an explicit ref is that ref’s tree and ignores the index), or the Git Orbulk files changed between two refs (paths unchanged between them, and deletions, are omitted in the two-ref form). Options: the full object id instead of the abbreviated one; each object’s size; debug detail; entire-history listing (every Git Orbulk path in the history of all refs, including other branches); deleted listing (also paths deleted in the history of the selected ref — the current ref, or one explicit ref); include/exclude path filters; name-only (paths only); and JSON.
- On the default listing line, each entry shows whether the working-tree file is the full object or only a pointer. That indication depends only on the working-tree file: it differs between those two states and does not change with whether the object bytes exist in the local store.
- The JSON listing additionally indicates, on each entry, whether the object is present in the local store, in both working-tree states.

**Boundary / error behavior:**

- Status in a bare repository fails.
- Ls-files with an invalid ref fails; entire-history listing cannot be combined with an explicit ref; deleted listing cannot be combined with the two-ref form.
- When both machine-readable JSON and a mutually overriding human format are requested: status uses the porcelain format; ls-files uses the debug format, and when JSON is selected the full-id, size, and name-only options do not change the JSON listing.

---

### FP-12: Local object pruning

**Public entry:** The `git orbulk prune` porcelain subcommand (also invocable after fetch via fetch’s prune option).

**Normal behavior:**

- Prune deletes local objects that are not retained by: the current checkout, stashes, recent branches/commits per recentness configuration, unpushed commits, or other worktree checkouts. Objects only reachable from orphaned commits are deleted. The reflog is not a retention root.
- The recentness window has two parts: recent refs retain the objects at the tips of other refs whose tips are recent, and recent commits retain earlier versions of files on the current ref and on retained recent refs whose commits are recent relative to that ref’s tip (whether or not recent refs are enabled). A positive window of either part covers content committed just before prune runs; a window of zero days disables that part, so it retains nothing, however new the content.
- A stash retains the objects of the paths it changed relative to the commit it was made on (its staged and working-tree changes); paths it carries unchanged from that commit are not retained by the stash.
- Objects at paths matching the fetch-exclude patterns are retained only by stashes and unpushed commits: the current checkout, recent refs, and other worktrees do not retain them.
- Options:
  - dry-run reports the candidates and deletes nothing;
  - force also deletes objects retained only by the current checkout, recent refs, or other worktrees (it implies recent); it still never deletes unpushed or stashed objects;
  - recent removes the recentness window as a retention root while still keeping the current checkout;
  - verify-remote asks the endpoint whether it holds each candidate before deleting it: a candidate is held only when the endpoint offers to supply it for download, and a candidate the endpoint answers with an error or without a download offer is not held; the prune-verify-remote-always setting turns this on even when the option is not given;
  - verify-unreachable extends that verification to local objects not reachable from any ref; without it, unreachable objects are deleted without verification;
  - when-unverified (halt or continue) chooses what happens when verification fails;
  - verbose names each deleted object (under dry-run, each object that would be deleted) and no retained object.

**Boundary / error behavior:**

- Prune never deletes an unpushed object, even when the endpoint already holds its bytes.
- Users sharing one custom storage directory across multiple repositories are warned (via documentation and config notes) not to prune unsafely; prune applies the retention rules of the invoked repository only, so an object retained only by another repository sharing the store is deleted.
- When remote verification is enabled and at least one candidate (including an unreachable one under verify-unreachable) fails verification: under halt, no object is deleted in that run; under continue, only the candidates the endpoint holds are deleted and the rest remain. When every candidate verifies, all candidates are deleted.

---

### FP-13: Object and pointer integrity check

**Public entry:** The `git orbulk fsck` porcelain subcommand.

**Normal behavior:**

- Fsck checks Git Orbulk files for consistency for HEAD by default (and, for object checks, also the objects staged in the index in that omitted-revision default), or for a single committish, or for a two-dot range. An explicit revision checks only that revision. Object checks and pointer checks both run by default and may be requested independently; when one kind is requested alone, defects of the other kind are not findings.
- Object checks verify each object’s hash matches its oid and that the file exists on disk.
- Pointer checks verify pointers are canonical and that files that should be stored as Git Orbulk objects are actually stored that way.
- Hash-mismatched local object files are moved aside into the repository’s LFS `bad` quarantine directory unless dry-run is set; other objects stay in place. Missing objects and pointer defects are reported and nothing is moved for them.
- Fetch-exclude path patterns skip object checks for matching paths; they do not skip pointer checks.

**Boundary / error behavior:**

- Hash mismatches, missing objects, and pointer defects cause non-zero exit.
- A single revision argument that cannot be resolved as a committish or as both ends of a two-dot range is rejected with a non-zero exit before any check runs.
- Dry-run reports problems without moving files.

---

### FP-14: History migration

**Public entry:** The `git orbulk migrate` porcelain subcommand with modes info, import, and export.

**Normal behavior:**

- **Info** summarizes counts and sizes by file type for the selected ref set to help users decide what to migrate, without rewriting anything. Each file-type entry carries the number of matching files and their total size as separate figures. Pointer objects are handled by exactly one of three pointer modes: **follow** (default: report referenced object sizes separately), **ignore** (omit pointers), or **no-follow** (treat pointer documents as ordinary files, reporting the pointer blob size).
- **Import** rewrites local history so matching Git blobs become Git Orbulk pointers on every rewritten commit, stores objects locally, and updates `.gitattributes` on every rewritten commit as if track had been run for those patterns. Unmatched paths stay ordinary blobs. Fixup mode converts only files that attributes already say should be Git Orbulk but are not yet, and adds no new tracking lines. A no-rewrite import mode creates one new commit on top of the current HEAD that converts only the paths listed as arguments, leaves prior history and other refs untouched, and ignores the ordinary migrate rewrite options.
- **Export** rewrites local history in the reverse direction: matching Git Orbulk pointers become ordinary Git blobs again on every rewritten commit, fetching missing objects from a remote when needed (default remote `origin`), and inserts excluded-pattern attribute entries (FP-04 disabling/unsetting filter forms) for the exported patterns on every rewritten commit rather than removing tracking lines or deleting attribute files. Unmatched pointers stay pointers.
- By default migrate considers the current branch and commits not present on remotes. When include or exclude refs are given explicitly, the selection is the history of the included refs minus the history of the excluded refs: remote-tracking refs are no longer excluded automatically and the current branch is not added implicitly. An option instead selects everything. After rewrite, only local refs are updated even when everything was read—remote-tracking refs stay aligned with remotes until the user force-pushes.
- Migrate refuses (non-zero, nothing rewritten) when `.gitattributes` is a symbolic link; this applies to info as well. Attribute files it writes use non-executable permissions.

**Boundary / error behavior:**

- Export requires at least one include pathspec; without one it fails and rewrites nothing.
- Import/export are destructive history rewrites (except no-rewrite import, which adds a new commit instead of rewriting prior history); they do not update remotes automatically.
- Uncommitted work should be committed or stashed first. Without the confirmation option, import and export refuse a dirty working tree (uncommitted changes or untracked files that Git status reports). With confirmation, the same dirty or untracked working tree is accepted and the rewrite proceeds; uncommitted working-tree changes may be overridden. Users are still expected to validate before force-push.
- By default, when migrate selects the unpushed commit set using remote refs, it refreshes those remote refs over the network first. An unreachable configured remote makes that default path fail before any history rewrite.
- With skip-fetch, import does not contact the remote, so it succeeds under an unreachable remote when the objects are already local. Export or import may still need a reachable remote when objects themselves are missing locally.

---

### FP-15: Configuration surface and repository `.lfsconfig`

**Public entry:** Git configuration keys under the `lfs` namespace, per-remote overrides, the environment variables that skip smudge, skip push, skip download errors, force progress, or set lockable read-only behavior, and an optional `.lfsconfig` file at the repository root.

**Normal behavior:**

- Git Orbulk reads all files Git’s config machinery supports. A restricted subset of settings may also live in `.lfsconfig` at the repo root (same format as Git config files) so teams can ship endpoint and access defaults. Git config overrides `.lfsconfig`. If `.lfsconfig` is missing from the work tree, Git Orbulk looks in the index, then HEAD (bare repositories: HEAD only).
- The finite set of settings accepted from `.lfsconfig` is: the LFS URL, the LFS push URL, per-remote LFS URLs, the LFS default and push-default remote names, fetch include, fetch exclude, skip-download-errors, allow-incomplete-push, locks-verify, URL-scoped access, and the Git protocol setting used for LFS. Every other setting in that file is ignored for security, and ignoring it never makes the client fail.
- The Git-protocol setting selects the HTTP scheme used when deriving an endpoint from a Git-protocol remote (FP-06): unset, the secure scheme; the other accepted value, the plain scheme.
- Each setting takes effect on the behavior it names: endpoint and push endpoint URLs (FP-06), URL-scoped access (FP-06), allow-incomplete-push (FP-09), concurrent transfers, tus uploads, basic-transfers-only, retries and HTTP timeouts (FP-07), lock verification (FP-10), default remotes (FP-06), fetch include/exclude and recentness (FP-05, FP-08), storage location (FP-05), prune recentness offset and verify defaults (FP-12), custom and standalone transfer agents (FP-16), and pure SSH transfer mode (FP-17).
- Environment variables can skip smudge, skip push, and skip download errors, following the documented boolean conventions. Skip-smudge leaves pointer text in the working tree on checkout/filter instead of materializing, even for objects already local; skip-push makes the pre-push path perform no LFS uploads while Git still updates refs; skip-download-errors lets a checkout/smudge that cannot download leave pointers and succeed rather than failing the whole operation. Skip-download-errors may equally be set in Git configuration or `.lfsconfig`.
- Environment or Git configuration can force progress, following the documented boolean conventions. With progress forcing on, a transferring command reports in-progress transfer progress even when standard output is not a terminal; with it off, a command whose standard output is not a terminal reports no in-progress progress (a final summary line may appear either way).
- Environment or Git configuration can enable or disable lockable read-only behavior (default enabled). When enabled, the post-checkout, post-commit, and post-merge permission paths (FP-10) leave unlocked lockable working-tree files read-only; when disabled, they leave them writable.

**Boundary / error behavior:**

- A boolean value that is not a documented truthy token is falsey under those conventions: skip and progress-forcing stay off, and lockable read-only is disabled rather than left at its default-enabled state.
- Unknown keys in `.lfsconfig` do not crash the client; they are ignored.

---

### FP-16: Custom transfers, standalone file URLs, and clean/smudge extensions

**Public entry:** Custom transfer configuration; the standalone-file plumbing adapter; the `git orbulk ext` subcommand; extension registration in Git config.

**Normal behavior:**

- **Custom transfer agents:** Named agents registered in config specify a process path, arguments, whether concurrent instances are allowed, and direction (download, upload, or both). During batch negotiation the client advertises these transfer names; when the server selects one, Git Orbulk launches the process and speaks the documented JSON stdin/stdout protocol to move bytes via paths the agent understands (no file bytes on the control stream), instead of basic GET/PUT. When concurrent instances are not allowed for an agent, Git Orbulk runs a single agent process for all of that operation’s transfers. Built-in adapter names such as basic and ssh always override a custom agent registered under the same name.
- **Standalone transfer without API:** Configuration may name a standalone agent (including the built-in standalone file adapter) so Git Orbulk skips contacting the batch API and drives transfers directly when the endpoint URL matches.
- **Standalone file adapter:** Handles `file://` URLs / local paths as a transfer backend, speaking the standalone JSON transfer protocol. End users do not invoke it manually for routine workflows; the client selects it when appropriate. When that adapter uploads to a file:// or local-path Git remote that uses the default store location, the object appears in that destination Git directory’s LFS object store using the same objects-directory-plus-shard layout as the local store, and not at some other path beside the destination.
- **Content extensions (experimental):** Registered extensions supply clean and smudge external commands with a priority number. On clean, the registered extensions run in ascending priority-number order, each consuming the previous one’s output, and the final output is the stored object. The client records one metadata line per extension on the pointer, in clean order, each carrying the SHA-256 of the bytes that extension received as input, so smudge can reverse the pipeline: smudge runs the extensions recorded on the pointer in reverse order, each consuming the previous one’s output, to restore the working-tree bytes. Extensions do not edit the pointer directly. The ext subcommand lists registered extension details.

**Boundary / error behavior:**

- A selected custom agent whose process path cannot be launched fails that transfer. An unknown name selected as the standalone agent is ignored, so ordinary batch transfer still proceeds.
- Extension failures during clean/smudge fail the filter operation; buggy extensions can corrupt repositories—hence experimental status.

---

### FP-17: Pure SSH transfer protocol

**Public entry:** Automatic when talking to SSH remotes that implement the pure SSH Git Orbulk transfer service; controlled by the ssh-transfer configuration triad negotiate/always/never.

**Normal behavior:**

- The client attempts to run **git-orbulk-transfer** over SSH with the repository path and operation (`download` or `upload`). On success it speaks the pkt-line protocol described in the Interface Contract on that channel: it selects protocol version 1, negotiates objects with batch commands, downloads objects with get-object, uploads objects with put-object, and ends the session with quit. After uploading an object’s bytes, the client completes a verification round-trip for that object on the same channel; the upload counts as complete only when that verification succeeds. Further batch-like download/upload and optional locking commands proceed on the SSH channel without requiring HTTPS for the object bytes.
- Default mode is negotiate: try pure SSH first, then fall back to the hybrid git-orbulk-authenticate-plus-HTTPS approach (FP-06/FP-07). Always and never force only one family.

Background: some OpenSSH-family setups can reuse a shared SSH control connection for successive pure-SSH channels under configuration and platform defaults; that optimization is not required for correctness of pure SSH transfer.

**Boundary / error behavior:**

- If the git-orbulk-transfer session cannot be established in negotiate mode, the client falls back to the hybrid protocol rather than immediately aborting, unless configuration forbids fallback.
- In always mode, hybrid HTTPS transfer is not used; failure of pure SSH fails the operation. In never mode, pure SSH is not attempted.
- Server error replies fail the transfer they answer. An error reply to the post-upload verification fails the upload even though the peer already stored the bytes.

---

### FP-18: Logs, completion, dedup, and merge driver

**Public entry:** The `git orbulk logs`, `git orbulk completion`, `git orbulk dedup`, and `git orbulk merge-driver` subcommands; Git merge attribute integration when a user configures a merge driver that invokes the merge-driver plumbing command.

**Normal behavior:**

- **Logs:** Crash and unexpected-error details are written as log files under the repository’s LFS namespace. The logs command’s finite sub-entries are: list stored logs (default), show a named log or the most recent (`last`), clear stored logs, and intentionally trigger a diagnostic exception (which fails and writes a new log). Each new log is added without changing earlier ones; `last` shows the newest.
- **Completion:** Emits a non-empty tab-completion script for each of a fixed set of shells—**bash**, **fish**, and **zsh**. When that script is loaded in the corresponding shell, completing the standalone binary offers Git Orbulk porcelain subcommand names as candidates (and flag completion for those porcelain commands; not general Git remote/branch completion). The bash script, loaded together with Git’s own bash completion, also offers those porcelain subcommand candidates for the multi-word `git orbulk` entry. Candidates come from the script working in the shell.
- **Dedup:** On filesystems that support copy-on-write cloning, re-links working-tree LFS files as independently writable COW clones of the local store objects to save space. A support-check mode only checks support (filesystem and the extensions gate below) and re-links nothing. Dedup fails when unsupported or when content extensions are configured.
- **Merge driver:** Intended to be invoked by Git, not by end users by hand. Track records the ordinary `lfs` merge attribute, which leaves Git’s default merge of pointer text in effect and does **not** by itself select this driver. A user who knows some tracked files are text must separately set a merge attribute and point that attribute at this plumbing command. When so invoked, the driver materializes ancestor/current/other stages and merges them as text (using Git’s merge tooling or a configured external program). On a successful merge it writes a pointer document for the three-way-merged object bytes to the designated output, and — when that object is not already present — stores those merged bytes in the local object store under the same content-addressed nested path layout used by clean.

**Boundary / error behavior:**

- Dedup exits non-zero on platforms or filesystems without copy-on-write cloning, and re-links nothing.
- When content extensions are configured, both ordinary dedup and its support-check mode refuse and exit non-zero even on a copy-on-write-capable filesystem, because working-tree bytes may not match stored object bytes.
- Completion for an unknown shell name fails with a non-zero exit.
- Merge driver does not claim to handle arbitrary binary merges or all rename/copy cases Git itself cannot express in this hook shape.
- The diagnostic-exception logs entry deliberately fails; clear removes stored logs so a subsequent list is empty.

---

## Cross-cutting requirements

- **End-to-end path:** install → track pattern → add/commit large file → push uploads object → fresh clone/pull restores bytes works on a real Git repository and a conforming endpoint.
- **Pointer canonicality:** Two independent clean runs on identical bytes produce identical pointer documents and identical local object digests.
- **Filter name stability:** The Git filter/attribute/merge name `lfs` and the on-disk `.git/lfs` namespace are part of the protocol compatibility surface and must remain those names.
- **Hook set stability:** Repository install/update installs the four Git Orbulk hooks (pre-push, post-checkout, post-commit, post-merge); the lockable post-* hooks are never omitted.
- **Vocabulary:** This PRD uses the product’s own names (Git Orbulk, `git-orbulk`, git-orbulk-authenticate, git-orbulk-transfer, `.lfsconfig`, and related terms) exactly as the project spells them.
