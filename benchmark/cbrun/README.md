# cbrun — zero2repo Solver Benchmark Runner

`cbrun` is a Harbor-independent benchmark runner for [zero2repo](https://zero2repo.ai/)
(formerly CodingBench). It evaluates an autonomous coding agent by giving it
only the public task specification and letting it build the project from
scratch, then scoring the result against hidden acceptance tests.

## Task model (solver-only)

The agent's job is to **write the implementation**. The test code is a hidden
benchmark asset, never an agent output.

* **Input** the agent sees: the PRD (`/environment/prd/Full_PRD.md`) and the
  Interface Contract (`/environment/Interface_Contract.md`) as files inside
  the container (the instruction prompt names those paths and does **not**
  inline the bodies), plus the case `build_command` (when non-empty) as the
  Build contract. The agent's workspace `/app` starts empty. Built-in Codex
  and OpenCode CLIs read the instruction file from stdin so a large prompt
  never becomes a single `execve` argument (Linux `MAX_ARG_STRLEN` is 128KiB).
* **Output** the agent produces: the implementation in `/app`. When the case
  has a `build_command`, leave the outputs that command would produce; the
  judge does not rebuild.
* **Scoring**: after a valid submit file is present, the runner copies only
  `/app` into a fresh judge container and injects the hidden suite. The judge
  does **not** execute `install_command` or `build_command`. Reward is 1
  only after the suite is collected and executed and every test passes. CLI
  exit 0 alone is not a submit and not a pass.

The guiding invariant is *information completeness*: the provided environment
(empty `/app` + PRD + Interface Contract + the declared `build_command` when
present) must be theoretically sufficient for an ideal agent to pass the hidden
tests. The runner must show `build_command` to the agent; it is public text and
must not contain recipe-only flags that only the original repository understands.
If that command still cannot imply a path the hidden harness hard-codes, that is
a **case spec defect** — fix the case, never patch a per-case path into the
runner.

## Fairness: visible checks vs hidden gates

* **Visible / dev checks**: the agent may write and run its own tests and any
  public sample checks as many times as it wants and read their full output.
  The prompt states context, the goal, the rules, and the submit/scoring
  protocol only; it does not prescribe a workflow.
* **Hidden gates**: the hidden acceptance tests are *physically absent* from the
  solve container. cbrun derives a per-case `:agent` image from the published
  `:deliverable` image and removes `/tests/final` in a new image layer (the
  tests are extracted to a host-side cache first). They are re-injected only for
  the judge phase, and judge output is not fed back to the agent.

## Free development, time-limited

There is **no** limit on steps, turns, edits or cost. The only hard ceilings are
wall-clock budgets:

* `max_agent_timeout_sec` — solve phase. Final-stage cases use a uniform **2h**
  (`7200s`).
* `max_test_timeout_sec` — judge phase. Default **2h** (`7200s`), the same
  wall clock as the solve phase. A case may widen this via
  `milestones/final/test_manifest.json` fields `judge_timeout_sec` (explicit)
  or `suite_wall_seconds × 2` (headroom). Per-case values never tighten a
  CLI `--test-timeout-sec`. Cases without those fields keep the 7200s default.
* `--timeout-multiplier` scales both wall clocks (mirrors Terminal-Bench's
  `global_timeout_multiplier`) and is applied once, including to a widened
  per-case judge budget.
* Each trial records `host_arch` and `emulated` (container platform ≠ host).
  Emulated runs require `--allow-emulated`. They are counted in
  `aggregate.emulated_trials` and excluded from `reward_mean_valid`.
  `suite_wall_measured_on.arch` must match the container platform.

A conservative stall watchdog stops a wedged CLI when both stdout and `/app`
stay quiet, without treating a long compile or a long model turn as a hang.

The shared instruction says only that a wall-clock budget exists. During the
solve, every built-in agent is also told how much of that budget remains: at
the start, then hourly; every 30 minutes in the last hour; every 10 minutes in
the last 30 minutes; every 5 minutes in the last 10 minutes; every minute in
the last 5 minutes; every 30 seconds in the last minute. The reminder is
delivered at the agent's next hook point, so a turn or a command that has not
returned yet delays it. It states the time left, that expiry kills the session
and records a timeout, and that scoring requires writing `/logs/agent/submit`
with the single line `CODINGBENCH_SUBMIT` and then finishing the session.

## Termination and submit

The agent submits by writing `/logs/agent/submit` with the single line
`CODINGBENCH_SUBMIT`. Ending the CLI session is **not** a submission. The
isolated judge runs only after that file is valid **and** the denylist scan
is clean. Missing submit or an unfixed denylist hit scores `reward=0` and
does not run hidden tests. A declared judge substrate that cannot be
prepared on the host is `judge_error` / `substrates_missing` and does not
count as a scored fail.

The solve terminal status is recorded as one of:

* `completed` — valid submit file and the CLI exited 0.
* `timeout` — the wall clock was hit.
* `error` — stall-killed, a non-zero CLI exit, setup failure, or no submit.

## Built-in backends

Five backends ship as built-in **AgentSpec** records:

| Backend | CLI | Notes |
|---------|-----|-------|
| `codex` | `@openai/codex` | Writes `~/.codex/auth.json` + `config.toml` from `OPENAI_*` env before solve. Default `model_prefix=keep` for OpenAI-compatible gateways. |
| `opencode` | `opencode-ai` | Forwards provider env based on `provider/model` id. |
| `claude-code` | `@anthropic-ai/claude-code` | Runs as root with `bypassPermissions`. Claude Code refuses that mode for a real root login, so the solve process sets `IS_SANDBOX=1`. Judge still runs as root. |
| `cursor` | Cursor CLI (`cursor-agent`) | Forwards `CURSOR_API_KEY`. Installed from the official Cursor install script into the `:agent` image. |
| `openhands` | OpenHands CLI 1.16.0 | Forwards `LLM_API_KEY` and `LLM_BASE_URL`. Model id is passed as `LLM_MODEL` (use `openai/<id>` for an OpenAI-compatible endpoint). The CLI is copied from a local `codingbench-agent/openhands:1.16.0` image, because it requires Python 3.12. |

Auth/provider env is selected centrally and forwarded into the container; only
**present** keys are injected (key names are recorded in results, never values).
CLI versions default to latest but should be pinned for reproducibility via
`CBRUN_CODEX_VERSION` / `CBRUN_OPENCODE_VERSION` / `CBRUN_CLAUDE_VERSION` /
`CBRUN_CURSOR_VERSION`.

### Codex + OpenAI-compatible gateway

Point standard env vars at any OpenAI-compatible endpoint:

```bash
export OPENAI_API_KEY=your-key
export OPENAI_BASE_URL=https://your-gateway.example/v1
cbrun --case case001 --backend codex --model openai/gpt-4o-mini
```

When `OPENAI_BASE_URL` is set, cbrun writes a named `gateway` provider into
`~/.codex/config.toml` (`base_url`, `env_key = "OPENAI_API_KEY"`,
`wire_api = "responses"`, `supports_websockets = false`) and selects it with
`model_provider = "gateway"`. It does **not** write `openai_base_url`: that only
re-points Codex's built-in `openai` provider, which tries the Responses
WebSocket transport first and cannot be overridden, so behind an HTTPS-only
gateway every turn burns the full `Reconnecting... 1/5 … 5/5` budget (about
75–120s) before falling back to HTTPS. Set
`CBRUN_CODEX_GATEWAY_WEBSOCKETS=1` only for a gateway known to carry WSS.
Without `OPENAI_BASE_URL` the built-in provider and `auth.json` are used
unchanged. Use `model_prefix: strip` in a custom spec if your Codex install
expects leaf model names only.

Codex reasoning effort is optional. Set `--reasoning-effort` or
`CBRUN_CODEX_REASONING_EFFORT` to `minimal|low|medium|high|xhigh`. When set,
cbrun writes `model_reasoning_effort` into the container `config.toml` (and
cats that file into `agent_setup.log`; it never prints `auth.json`). When
unset, Codex 0.153.x is observed to default to `low`; the CLI prints a
warning and `summary.json` records `reasoning_effort=null`.

### Claude Code root contract

* Agent deliverables **must** land in `/app` (hard contract; not overridable).
* Solve runs as root, same as the Cursor and Codex backends, so it can read root-only spec files baked into an image. `IS_SANDBOX=1` is set because Claude Code rejects `bypassPermissions` for an ordinary root login.
* Agent HOME (`/root`) holds CLI caches only; it is not scored.

## Bring your own agent

Pass a local **AgentSpec** file instead of `--backend`:

```bash
cbrun --case case001 --agent-spec ./my-agent.json --model my/model
```

Example `my-agent.json`:

```json
{
  "name": "my-agent",
  "env_passthrough": ["MY_API_KEY"],
  "setup_script": "mkdir -p \"$HOME/.myagent\" && echo ok > \"$HOME/.myagent/ready\"",
  "command": "my-cli --model {model_quoted} --workdir {workdir_quoted} < {instruction_quoted} 2>&1 | tee {log_quoted}",
  "run_as": "root",
  "model_prefix": "keep",
  "setup_timeout_sec": 120
}
```

### AgentSpec fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Identifier recorded in results. |
| `command` | yes | Shell command template for the solve phase. Workdir is always `/app`. |
| `env_passthrough` | no | Env var names to forward when present on the host. |
| `setup_script` | no | Shell run before solve (auth files, config). Do **not** use `set -x`. |
| `install_script` | no | Optional CLI install when not baked into the `:agent` image. |
| `run_as` | no | `root` (default) or `nonroot` (`cbagent` via `docker exec -u`). |
| `model_prefix` | no | `keep` (default) or `strip` the `provider/` prefix from `--model`. |
| `home` | no | Writable HOME/config directory (defaults by `run_as`). |
| `setup_timeout_sec` | no | Setup phase timeout (default 120s). |
| `python_hook` | no | Built-in hooks only (`cbrun.agent_hooks:*`); custom specs should use declarative fields. |

Placeholders in `command` / `setup_script`: `{model}`, `{model_quoted}`,
`{instruction_quoted}`, `{log_quoted}`, `{workdir}` (`/app`), `{workdir_quoted}`,
`{home}`. Redirect `{instruction_quoted}` into stdin (or pass the path as a
file argument). Do **not** expand the file with `$(cat …)`: that puts the
whole prompt into one argv slot and fails once it exceeds 128KiB.

### Security boundaries

* AgentSpec files are **local trusted configuration**. They can execute shell
  (`setup_script`, `install_script`, `command`). Do not run specs from untrusted
  sources.
* Specs are loaded from `--agent-spec PATH` only; cbrun does **not** fetch and
  execute remote spec URLs.
* The solve container never mounts the Docker socket.
* Hidden tests are absent during solve; logs must not contain secret values.

### Network policy and upstream denylist

* During **solve**, code-hosting hostnames are blocked via container
  `/etc/hosts` (`--add-host …:0.0.0.0`): GitHub and its download hosts,
  GitLab, Gitee, Bitbucket, Sourcegraph, Codeberg, sourcehut, and well-known
  GitHub mirrors/proxies (`CODE_HOST_BLOCK_HOSTS` in `denylist.py`). Model API
  calls, web search and package registries (PyPI, npm, Go proxy, crates.io)
  remain reachable, because ordinary dependency installs need them; source
  archives fetched from a registry are reported by the transcript scan below.
  `summary.json` records `blocked_hosts`. Disable with `--no-block-github`
  (alias `--no-block-code-hosts`).
* Each case ships `source/denylist.json` (install/import bans for the
  upstream product). It is tracked with the case. The file never enters the
  solve container: the `:agent` image carries only name hashes plus the
  install shims, and the plaintext is read on the host for the post-submit
  scan and in the judge container after the agent has exited. pip/conda
  install shims in the `:agent` image reject those packages inline (warning
  only, no scoring).
* After a valid submit, cbrun statically scans `/app` for real
  import/require/use of banned tokens (docstrings and string literals do not
  count). If found, the agent gets one fix retry (`--denylist-fix-retries`,
  default 1) and must write the submit file again; if violations remain, the
  trial scores `reward=0` without judging. `rejudge` (and therefore
  `run_controls`) applies the same scan to the host workspace before it
  starts a judge container and writes `denylist_scan.json` next to the judge
  artifacts, so a control or a re-scored trial is never judged more leniently
  than a live trial. The scan skips `dist/` / `build/` / `node_modules/`;
  what actually executes is covered by the judge-time import ban below.
* Judge-time import ban. The hidden tests run with a process-level ban on
  importing the upstream root from code under `/app`. For `pip` cases this is
  a `sys.meta_path` finder in the pytest launcher. For `npm` cases cbrun
  copies a CommonJS `--require` hook and an ESM `--import` hook into
  `/tests/`, writes `/tests/bin/node` (a wrapper that bakes the ban variables
  and both preload flags in front of the image's real `node`), and the
  launcher puts that directory first on `PATH`. Hidden harnesses routinely
  rebuild the child environment from a keep-list (`PATH` survives,
  `NODE_OPTIONS` does not), so the ban rides on the executable, not on an
  inherited variable. Before the judge starts, a canary asserts that both
  hooks refuse the first banned root on this image's Node and that the shim
  wins `PATH`; a failed canary is a hard `RuntimeError`, never a silent pass.
  Hidden harnesses must resolve `node` through `PATH`; a hardcoded
  interpreter path bypasses the gate.
* Solve-time access monitor. One invariant replaces per-technique checks:
  while the agent solves, only allowlisted toolchain processes may open the
  files of a banned implementation. Importing it as a dependency or oracle,
  reading, copying, grepping, or disassembling it all open those files first.
  Writing an implementation from memory is allowed and not detected.
  * Protected files are found in the container by name hash (no plaintext
    names in any shipped script): banned modules in every interpreter's
    stdlib and site-packages, vendored copies (`_vendor/`, `vendor/`, ...),
    and banned package directories in global and nested `node_modules`.
    Nothing under `/app` is protected. Banned modules the toolchain still
    imports stay as sourceless `.pyc` so plain reads remain useless.
  * `access_monitor.py` (baked into the `:agent` image) watches every
    protected file with inotify `IN_OPEN` and streams one JSON event per line
    over `docker exec`; the host reads it live and keeps the record in
    `access_monitor_<round>.jsonl`. It also sends a heartbeat and watches its
    own hook files and socket.
  * Attribution: every interpreter imports `cbrun_access_hook` from the end
    of stdlib `encodings/__init__.py` (read from disk even under `-S`/`-I`, and
    reached by venvs and pip's isolated build envs, unlike `.pth` or
    `sitecustomize`). A PEP 578 audit hook reports its own opens of protected
    files over a Unix socket; the monitor takes the sender pid from
    `SCM_CREDENTIALS` and argv from `/proc`.
  * The host (`cbrun/access_monitor.py`) matches each open with a report.
    Allowlisted openers are `-m pip`/pip entry scripts, pip's
    `__pip-runner__.py`, `pyproject_hooks` `_in_process.py`, `-m build`,
    ensurepip, uv's build-backend subprocesses, and the OpenHands runtime.
    Tools may also load a banned module for their own work (pytest reads
    `pyproject.toml` with the stdlib parser): that open is excused when the
    process entry is a tool (bin-dir script or installed package) and the
    code that caused the open is stdlib or installed-package code. The
    agent's own code (`/app`, `/tmp` scripts, `-c`, packages installed from a
    local path per `direct_url.json`) never qualifies.
    A report from any other process, or an open with no report within 3 s
    (a non-Python tool, or Python without the hook), is an access event.
    A lost heartbeat, a monitor exit, a forged report, or a changed hook file
    is interference and counts the same.
  * The first event stops the round (same stop path as the stall watchdog)
    and the next round's instruction states what was observed and why it is
    forbidden. A second event fails the trial (`denylist_violation`,
    `reward=0`). The count of allowed warnings is `--denylist-fix-retries`.
    `summary.json` records `access_events` and `access_rounds_stopped`.
  * If the monitor cannot start (no Python, no inotify, hook not installed),
    the trial errors before solving (`run_valid=false`); no round runs
    unmonitored.
  * Known limitations: single-file bundled CLIs (e.g. Claude Code's
    `cli.js`) and wheels such as ensurepip's bundled pip are not file-level
    artefacts; interpreters or packages fetched during the solve are not
    protected (downloading is already forbidden); a process that rewrites its
    own `/proc/<pid>/cmdline` and forges hook reports, or plants code in
    toolchain paths, can evade attribution. Once a tool has loaded a banned
    module in its own process, later code in that process (e.g. a test file
    pytest collects) can use it without a new open; tests in `/app` are
    still caught by the import scan and the judge-time ban. Setup code from
    `/app` running under pip is excused here and caught by the `/app` import
    scan.
* Post-trial transcript scan (`transcript_scan.py`). After every trial the
  agent's session files (`container_logs/usage/**/*.jsonl`, or the agent logs
  when there are none) are read for tool calls that try to obtain the upstream
  code at run time. Banned names come only from the case's `denylist.json`
  (`install_ban`, `import_ban`) and `manifest.json` (`sensitive_terms`,
  minus terms whose every word the public PRD/Contract already uses), and are
  matched as whole components (URL path segment, package spec or archive name
  without version, path segment), never as substrings. Rules:
  * `code_host_fetch`: clone/curl/wget/`gh`/VCS install/inline-script URL
    call/WebFetch to a code host or mirror (high with a banned name, else
    medium);
  * `registry_source_download`: an archive URL on a registry or mirror host,
    or `pip download`, `npm pack <pkg>`, `go mod download <mod>`,
    `apt-get source`, `gem fetch`, ... (high with a banned name, else medium);
  * `banned_name_fetch` (high): install/download/fetch of a banned name;
  * `banned_name_lookup` (medium): `pip show`/`npm view` of a banned name, a
    probed path outside `/app` (`ls`, `find -name`, Read tool), or an import
    of a banned root in `python -c`/`node -e`/interpreter heredocs;
  * `banned_name_in_output` (medium): a command that looked harmless printed
    "Cloning into / Saving to / Downloading / Collecting" a banned name;
  * `mention` (low, not flagged): a name in a web-search query or elsewhere
    in a command.
  Ordinary dependency installs, files the agent writes (heredocs to `cat`,
  Write/Edit tools) and its own `/app` paths are not flagged. Any high or
  medium hit sets `needs_review=true` on the trial; reward is never changed.
  Each hit records file, line, snippet, the tool result excerpt and whether
  the result shows a network failure. The full report is
  `<trial>/transcript_scan.json`; `summary.json` carries `needs_review`,
  `transcript_scan` (verdict, counts, flagged hits) and the aggregate
  `needs_review_trials`; the reward matrix marks the cell `*REVIEW`. Offline:
  `python -m cbrun.transcript_scan <trial-or-run-dir>... [--cases-root DIR]
  [--write] [--json FILE] [--show-low]` (exit 1 when any trial needs review).
* `--enforce-denylist` is on by default. Missing file or empty ban lists
  fail before any container starts. `--no-enforce-denylist` skips the scan
  and `summary.json` records `denylist_enforced=false` so a skipped scan is
  not mistaken for a clean scan.

## Step mode (architecture only)

cbrun currently treats each case as a single final acceptance suite. It
normalizes that shape into one step and exposes `steps.discover_steps` so
multi-step support can be added later. Multi-step development orchestration is
**not** implemented yet.

## Usage

```bash
# Rebuild :deliverable from recipe.lock + shared base (no model needed)
cbrun --case case001 --build-images

# One case, one backend
cbrun --case case001 --backend codex --model openai/gpt-5.5

# Several backends, reward matrix
cbrun --case case001 \
  --backend codex --backend opencode --backend claude-code --backend cursor \
  --model openai/gpt-5.5

# Custom agent spec
cbrun --case case001 --agent-spec ./agents/echo.json --model dummy/model

# Every case under the cases root
cbrun --all --backend codex --model openai/gpt-5.5
```

Outputs go to `--out` (default `benchmark/output/cbrun/`): per-trial `agent.log`,
`agent_setup.log` (when setup runs), `judge.log`, `final_report.json`,
`final_tests.log` (when the judge ran), plus an aggregate `summary.json` and a
printed reward matrix.

Each trial records reproducibility metadata: agent spec name/hash, resolved model,
`run_as`, `model_prefix`, setup status, forwarded env **key** list, CLI
version when available, `reasoning_effort`, judge/agent timeouts, `host_arch`,
`emulated`, `test_count`, `failed_tests`, and `infra_signals`.

`run_valid` is false only when there is **no** valid submit **and** the tail
of `agent.log` shows a terminating infra signal (`invalid_api_key` /
`Unauthorized` / `HTTP 401`, `exceeded retry limit`, `ECONNREFUSED`).
`content_filter` is counted but a recovered submit stays valid. Invalid
trials appear as `INFRA(<signal>)` in the matrix; `aggregate.invalid_runs`
and `reward_mean_valid` ignore them as model skill.

Asset and control checks:

```bash
python -m cbrun.case_checks                 # 11 cases; errors fail, warnings do not
python -m cbrun.rejudge --case case001 --workspace … --out …
```

`expect.json` may list `must_fail_tests` (nodeid or suffix). When that field
is absent, `rejudge` / `run_controls` still compare **reward only**. When it
is present, each name must appear in pytest `FAILED` (not `ERROR` / missing).
Collection / import-ban / judge_bans controls stay reward-only; do not
promote those reds into `must_fail_tests`. A control caught by the static
scan never reaches the judge, so `must_fail_tests` on it is reported as an
error rather than quietly satisfied. `controls/` is a maintainer-local
asset (gitignored, not published). A public clone without it is complete:
`run_controls` / `iter_controls` are empty and unit tests do not need it.

Privilege markers in hidden tests (`mount(`, `losetup`, …) are **errors**
unless `test_manifest.json` declares a known `judge_substrates` provider.

### Agent CLI runtime (default PATH)

Node used only to run Codex / Claude / OpenCode is installed under
`/opt/cbrun/runtime/node`. The CLI script shebang is rewritten to that
absolute `node`. The private prefix is **not** added to `ENV PATH`,
`/etc/profile.d`, or the CLI process PATH (Codex / Claude Bash inherit that
environment). `command -v node` in a login shell therefore fails unless the
case deliverable itself shipped Node.

This is **default-PATH invisibility**, not a root-proof hide. Codex
`run_as=root` can still walk `/opt/cbrun/runtime/`. The guarantee is that
`node -p process.versions.*` is not a zero-cost default-PATH oracle.
Install-ban npm shims remain on `PATH` at `/opt/cbrun/bin`; they block
installs, they do not expose `node`.

`source/denylist.json` may declare `runtime_equivalents`
(`import_root`, `runtime` ∈ `python3|node|system`, `evidence`). A
`runtime=="node"` row is what probes `typeof` / `process.versions.<name>`.
The runner does not special-case product names.

### Judge substrates

A case that needs a host filesystem the default `--network none` /
no-cap judge profile cannot provide lists names in
`test_manifest.json` `judge_substrates` (today: `cow_fs`). cbrun prepares
the provider on the host (reuse a writable FICLONE directory whose
`/proc/mounts` fstype is xfs/btrfs/bcachefs/ocfs2, otherwise
`loop` + `mkfs.xfs -m reflink=1`) and bind-mounts it at
`/mnt/cb-substrate/<name>`. The judge container is not given extra
capabilities. Solve containers do not receive the mount.

Preparation failure is `judge_error` with `substrates_missing` (and
`run_valid=false`), not a scored reward 0. `cow_fs` needs a Linux host
(FICLONE via `fcntl`); on other hosts it is reported unavailable with that
reason, and cases that declare no substrate are unaffected. Official 009
CoW scoring is **cbrun only**. Harbor starts its own verifier and this adapter only
copies `final_judge.py` into that image; it cannot attach substrates. A
bare Harbor run of a substrate case reports `substrates_missing`.

## Pipeline (per trial)

1. If `:deliverable` is missing, rebuild it from `source/recipe.lock.json`.
   The lock's `codingbench-base/<public>` tag is a local toolchain image
   built FROM the matching public image (Docker Hub `ubuntu:24.04` for the
   current suite) using `cbrun/base_image/Dockerfile`. cbrun pulls that
   public image and builds the toolchain tag when it is absent, then
   installs the case toolchain, copies public specs and hidden tests, and
   leaves `/app` empty. Then derive/reuse the `:agent` image (extract
   hidden tests to host cache, install pinned CLIs, create `cbagent` user,
   `rm -rf /tests/final`). Idempotent.
2. Start a GT-free container (`--gpus` only when the case needs it, host network
   for model APIs, **never** the Docker socket).
3. Inject the instruction; **setup** agent auth/config; **chown** `/app` (+ HOME
   for non-root agents); run the agent in `/app` under the wall clock + stall
   watchdog, tee'ing output to `agent.log`.
4. After the CLI stops, require a valid `/logs/agent/submit`; otherwise mark
   the attempt failed and skip hidden tests. Ensure no agent process lingers.
5. When submit is valid and denylist is clean: re-inject hidden tests + a
   synthesized `/task.toml`, run the shared `final_judge.py` as root, parse
   the binary reward (distinguishing `judge_error`).

## Reused components

* `coding_bench_harbor.adapter`: case discovery, `CaseAssets`,
  `build_contract_notes`, runner normalization. cbrun writes its own
  instruction preamble and points the agent at the spec files rather than
  inlining Harbor's `_INSTRUCTION_PREAMBLE` + PRD/Contract bodies.
* `coding_bench_harbor.final_judge`: the scoring engine (single source of truth,
  shared with the Harbor adapter).

### Test execution completeness

The trusted pytest launcher records each collected node before selection and
checks that the same nodes finish exactly once, including setup and teardown.
Skipped collection, deselection, skip/xfail/xpass outcomes, missing nodes,
duplicate execution, and interrupted phases are incomplete evaluations, not
successful submissions. Ordinary completed assertion failures remain test
failures. The collection receipt is retained in `final_tests.log` under
`CODING_BENCH_COLLECTION_AUDIT`; launcher exit 86 signals incompleteness to the
shared judge. This is execution accounting, not a sandbox against arbitrary
interpreter tampering by in-process solution code.

Historical logs without receipts are not silently upgraded to node-level
verification. Audit their recorded collection, execution counts, and outcomes
before deciding which saved submissions need rejudging. Rejudging uses the
original workspace and image without an agent run, and does not change the
original submission validity or timeout status.

## Local agent smoke

Your credentials, no source edits: [`../local_agents/README.md`](../local_agents/README.md).
Copy `*.env.example`, then run `./local_agents/run_smoke.sh`.
