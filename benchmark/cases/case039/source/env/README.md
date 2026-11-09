# Offline registry provisioning

## Pinned Rust acquisition repair (2026-10-26)

The three installation attempts in the original image-build log all failed
before product compilation. Alibaba returned HTTP 404 for the full Rust 1.88.0
archive; official-host transfers timed out, reset, or ended with curl exit 18.
These are three observations of one toolchain acquisition failure. Feature
behavior was unobserved in that run. The evidence does not establish the cause
of the external network failures.

`rust.json` pins Rust 1.88.0's separately published compiler, Cargo, and target
standard library for Linux x86_64 and aarch64. URLs and SHA-256 values come from
the official versioned release manifest dated 2025-06-26; its URL and verified
SHA-256 are recorded with the component metadata. Base-image probes found all
six Alibaba component URLs unavailable (404) and all six official URLs available
(200). Therefore Rust uses the dated official source directly. Other dependency
sources and versions are unchanged. The immutable crates.io Git objects still
use official GitHub because Alibaba has no matching Git-object endpoint.

Official byte-range GET probes returned HTTP 206 with the requested offsets.
The downloader splits each artifact into 2 MiB ranges, with at most eight concurrent
requests. Each range gets at most four attempts, with a 20-second connect timeout,
a 60-second minimum-speed window of 1024 bytes/second, a 300-second curl limit,
and a 330-second subprocess guard. An interrupted range is downloaded again;
completed ranges are retained while that range retries. There are two seconds
between attempts. Status 206, Content-Range, the pinned total size, and each range's
actual byte count must agree before assembly. The final range may be shorter.
The last transfer exception is re-raised, with curl's original stderr retained.
SHA-256 mismatch fails immediately with expected and actual digests. Only a
complete, checksum-verified assembly becomes an archive eligible for extraction.
The installer checks the final compiler and Cargo versions after installing all
three components under `/usr/local`.

The manifest and recipe lock retain their existing, identical install/build
entry points. No product source, archive, binary cache, host toolchain, or host
download cache is added to these portable inputs. Original metadata, dependency
pins, blacklist, denylist, tests, and acceptance criteria are unchanged.

### Fresh verification evidence

The prescribed `recipe_replay.py` returned **0**: a source-free installation
from `codingbench-base/ubuntu:24.04` succeeded, followed by the unchanged
`cargo build --frozen --release --features ffi,heap-profile` with networking
set to `none`. The release build completed in **4m 04s**. The install container
had exactly one mount, read-only `/env-assets`, and no repository, previous case
image, host toolchain, or host download cache. Its raw log records all three Rust
SHA-256 checks, installation, compiler/Cargo 1.88.0 version checks, and all **503**
pinned registry dependencies. The build log records actual compilation.

- Base image: `sha256:c2b1157f85698d3d3a3b4ed4e598315aea77c7e090be895eef18271af4e54ca7`.
- Fresh environment: `sha256:31b3370ad1d6d22dae931c1201ecbabfc745112e2c47b40eebabec83aad59f64`.

Real-network acquisition checks also returned **0**. They covered successful
range assembly, a deliberately interrupted real transfer, naturally occurring
connection/low-speed timeouts followed by recovery, four exhausted HTTP failures
with nonzero exit and original cause, and rejection of a real archive paired with
another component's checksum before extraction. All three aarch64 artifacts were
fully downloaded and SHA-256 verified. No mock data or server was used. Curl exit
18 uses the same bounded nonzero-exit handler; that exact exit was not forced in
the final checks. Native aarch64 execution remains unverified.

Evidence is retained separately under `milestones/v2/repair/hand_recipe_P024/`:
`original-build-images.log` preserves the original three failed installations;
`install-full.log`, `build-full.log`, `replay.log`, `replay-result.json`, and the
two container inspection records describe the successful fresh replay.
`parallel-acquisition-checks.log` and `parallel-acquisition-result.json` retain
the final positive and negative acquisition checks. `source-probes.log` and
`range-probes.log` retain public-source availability and range-response evidence.
Input hashes, protected-file hashes, cleanup records, and `summary.json` provide
the audit trail. Replay containers and images were discarded by the harness.

An intermediate serial-resume implementation was explicitly rejected after a
300-second compiler transfer retrieved only 7,041,525 of 80,014,172 bytes. Its
first diagnostic installation was intentionally stopped, and the same harness
retried from the fresh base using the final parallel implementation. The initial
serial aarch64 check later exhausted its bounded attempts. These observations
remain in `initial-resume-install.log`, `initial-replay-interruption.json`,
`acquisition-checks.log`, and `initial-acquisition-result.json`; they are not
success evidence for the final recipe. The successful installation is attempt 2
in the new replay log, distinct from all three historical failures.

No standalone `cbrun --build-images` rerun is claimed: this session exposes the
bound container entry and the prescribed replay, not an allowed bound entry for
that publishing CLI. Both unchanged runner commands passed through the prescribed
replay, but the publishing CLI's complete downstream workflow remains unverified.
No feature tests or collection run were performed during this repair. Protected
test/metadata files remained byte-for-byte unchanged; image-build success is not
feature-test success. Older observations below are separate historical evidence.

## Persistent Cargo discovery recheck (2026-10-25, 17:22 UTC)

The persistent repair was already present at the start of this recheck:
`install.py` links `/.cargo/config.toml` to `/opt/offline-cargo/config.toml`,
and the manifest and recipe lock no longer depend on a command-local
`CARGO_HOME`. Cargo's ancestor-directory search reaches this configuration
from temporary external-client directories. No installer, dependency pin or
runner command needed an additional change. This recheck changes only this
verification documentation; the manifest was written back byte-for-byte
unchanged. Original metadata, blacklist, denylist, tests and acceptance
criteria remain unchanged.

The prescribed `recipe_replay.py` passed. Installation ran from a fresh base
with only `/env-assets` mounted read-only, without a product checkout or host
cache. All 503 installed registry packages exactly match the original lock's
name, version, source and checksum tuples. The subsequent network-disabled
original-source build completed in 4 minutes. A separately copied, unbuilt
neutral reference also built offline in 4 minutes from the same source-free
environment image. Its 869 files match the supplied probe workspaces.

Recorded immutable image identities:

- Base: `sha256:c2b1157f85698d3d3a3b4ed4e598315aea77c7e090be895eef18271af4e54ca7`.
- Fresh source-free environment: `sha256:8afadeff7f89661187a7659f2f7975750e458c5baac3402c12f18c8d28273716`.
- Separately rechecked published image: `sha256:9456f690289db7bd81a2d899e8c9178259c6e61a7a8fe78c4ee5de23800f6a47`.

The unchanged trial `final_judge.py` invoked the unchanged isolated
`pytest_launcher.py` through its own `runuser` path. Each judge container
started with a fresh ordinary user's home (UID 1001), no Cargo or model cache,
no network, and a read-only `/app`. The actual launcher environment had neither
`CARGO_HOME` nor `F01_CARGO_CONFIG`. The discovery record shows only the loopback
network interface and the root-level configuration resolving to the installed
offline source. No configuration was injected through a shell prefix, login
script, Cargo command option or test modification.

All four original F17 cases passed in **176.44 seconds**, with every behavioral
call executed and no skips or collection issues. This includes the 384 finite
components, unit norm, independently computed published-model component accuracy
and repeatability within 0.0001, insertion and independently computed distance
ordering, numeric/text equivalence and null inputs, local offline execution,
disabled-operation rejection, and unavailable-model behavior with ordinary-data
controls. The unchanged F01 selection passed all nine cases in **2.26 seconds**.
The before/after collection identities match exactly.

The actual enabled client's lock resolved 377 external packages, all matching
the verified provisioned pins. Cargo metadata, run offline as the judge user
from that client's temporary directory, resolves every external package's
manifest under `/opt/cargo-vendor`. Recorded compiler fingerprints show
`semantic` enabled only for the temporary enabled client; the ordinary product
library remains non-semantic. The two metadata records refer to the same client
through its numbered directory and pytest's `current` symlink, not extra tests.
No missing pinned dependency was demonstrated, so `dependencies.json` is unchanged.

The historical failure remains **four setup errors in 1.49 seconds**, caused by
one shared enabled-client build failing to resolve `ahash`. None of those four
behavioral calls executed. Its raw log and report were recovered from earlier
recorded command outputs with provenance. The current supplied evidence path
instead contains a later **four-pass, 176.59-second** run; that result and this
recheck are separate observations. The historical image's immutable identity
is unavailable and is not inferred from a later image tag.

The independent P021 publication blocker remains. Against the current published
image, the same original F01 selection produced **eight passes and one failure
in 2.19 seconds**, with no skips or collection changes. Its WebAssembly test
could not launch `node`; the installed runtime's public entry is still absent.
Fresh recipe success does not repair the publisher's identity-matching and
cleanup defect described below. That publisher code is outside this repair's
scope; the denylist and tests were not weakened or bypassed.

Raw evidence is under `milestones/v2/repair/hand_recipe_P022/`: `replay.log`,
`install-full.log`, `build-full.log`, `neutral-build.log`, image and container
inspect records, `F17-results/`, `F01-results/`, `published-F01-results/`,
`historical-output-provenance.json`, `historical-four-setup-errors.log`,
`historical-four-setup-errors-report.json`, `collection-comparison.json`,
`semantic-closure.json`, input hashes and `summary.json`. The judge result
folders retain discovery evidence, complete reports and collection audits.
Only images and scratch product files created by this recheck are cleaned up.

Node.js and crate archives used Alibaba sources. The pinned Rust archive and
checksum used the official source after the mirror returned 404; immutable
registry Git objects have no Alibaba endpoint and used official GitHub.
Transient download retries remain visible in the installation log. No archives,
product source or binary caches were added to these portable text inputs.
Linux arm64 execution remains unverified.

## Publication delivery defect (2026-10-25, 09:42 UTC recheck)

The recipe already provisions Node.js. The current published image loses its
`/usr/local/bin/node` entry during publication, while the pinned executable at
`/opt/node-v22.14.0-linux-x64/bin/node` remains present and runs as v22.14.0.
This is a demonstrated delivery defect, not a missing download or a missing
WebAssembly artifact. No installer, runner command, dependency pin, blacklist,
denylist, product, or test was changed in this recheck.

The supplied probe inventory names the published `deliverable` tag but records
no immutable image ID. That tag currently resolves to
`sha256:b226333bfc70df1e18651e6ab0a08e4d847b62cc83119871f65d4b9ad191cb1c`.
Under that image, the unchanged in-container trial judge and isolated pytest
launcher reproduced eight passes and one missing-node failure in 2.56 seconds,
with the same nine collected identities, no skips, and no judge error. The
ordinary judge account (UID 1001) has `/usr/local/bin` on PATH, but `node` is not
discoverable. The preserved supplied failure was eight passes and one failure
in **2.18 seconds**; its historical image ID and effective PATH remain unknown.
The new reproduction does not retroactively identify the historical container.

The publisher's `cbrun/denylist.py`, in `denylist_hashes_from_payload`, adds
`Path(token).name` for import-ban entries. A scoped JavaScript binding package
therefore contributes the basename `node`, incorrectly treating the general
runtime as the prohibited product. The generated strip script scans
`/usr/local/bin` and removes the matching entry. The current published image's
history includes that stripping layer. The case's declared denylist allows
general toolchains; its scoped package restrictions must remain intact.

The required handoff is to correct identity matching in the publication tool,
preserving scoped package identities instead of interpreting their basenames
as unrelated executable identities, and then rebuild and judge the published
image. That tool is outside this repair's writable scope. Moving the runtime
entry, overriding test discovery, or weakening the denylist would not repair
the source of the defect. Fresh recipe success alone cannot close this
publication blocker. This is not hardware or installation infeasibility.

Evidence is retained under `milestones/v2/repair/hand_recipe_P021/` with the
`recheck-1737-` prefix: the supplied raw log and report, published-image inspect
and history, runtime discovery logs, strip diagnosis, unchanged judge and input
hashes, and `deliverable-judge-results/final_tests.log` and `final_report.json`.
The earlier checks below used a different image and are not proof that the
current published image passes.

## Fresh recipe and actual launcher verification (2026-10-25, 09:50 UTC)

The prescribed `recipe_replay.py` completed successfully in this call: installation
started from base image
`sha256:c2b1157f85698d3d3a3b4ed4e598315aea77c7e090be895eef18271af4e54ca7`
with only `/env-assets` mounted read-only, and the original source built offline
in 3 minutes 59 seconds. All 503 installed external package records match the
original Cargo lock's names, versions, sources and checksums exactly.

The replay's source-free environment image was retained temporarily, without
adding an installation layer, as
`sha256:1b6f39ddeac41d53451cf459f4170b8d54b8569ff80c5c6bb1bc5aca4bf4fb6d`.
Neither warm source location nor an application manifest was present in it.
A fresh, unbuilt copy of the neutral reference then built from that same image
with networking disabled in 3 minutes 59 seconds. Its 869 source files match
the supplied failure's reference workspace.

The unchanged `final_judge.py` and `pytest_launcher.py` were invoked through
the bound container entry, with the original F01 test manifest and unchanged
denylist-derived import restrictions. This used the trial judge's direct
`runuser` launch of isolated Python, not a substitute login-shell pytest run.
The product was mounted read-only and networking was disabled. All nine
original collected identities passed, with no skipped cases or collection
issues, in **2.26 seconds**. The original WebAssembly test initialized the
module and passed the existing query-ending and write-ending batch, retained
write, column-order, null-versus-empty, database-isolation and destruction
observations. No failed-statement batch behavior or new collected case was added.

Using the judge's launcher environment, UID 1001 discovered
`/usr/local/bin/node`, resolving to the pinned executable, from an unrelated
temporary directory. No `NODE` override or runtime shim was set, all shared
libraries resolved, and the retained runtime validation passed. The effective
PATH was `/opt/conda/condabin:/opt/conda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`.

The original failure (8/9, 2.18 seconds), current published-image reproduction
(8/9, 2.56 seconds), and fresh recipe environment (9/9, 2.26 seconds) retain the
same denominator and identities. These timings are not a speed comparison:
the failing runs never executed WebAssembly database behavior. The successful
image has not passed through the faulty publication cleanup, so publication
remains blocked pending the handoff described above.

The `recheck-1737-` evidence includes `input-sha256.json`,
`judge-input-sha256.json`, `isolation.json`, complete installation and build
logs, `fresh-judge.json`, `judge-results/runtime.log`, raw judge reports and
collection audits, and `summary.json`. Executable recipe inputs stayed
byte-for-byte unchanged; only this documentation changed. The manifest was
written back unchanged and its commands remain synchronized with the recipe
lock. Node.js and crate archives used Alibaba; pinned Rust archives and their
checksum file used the official source after Alibaba returned 404. Immutable
registry Git objects have no Alibaba endpoint and came from official GitHub.
Linux arm64 execution remains unverified.

The passing run used these execution inputs:

| Execution input | SHA-256 |
| --- | --- |
| `install.sh` | `102c87ec661251e27065ce833287be750715e690b809e7f0c04afcbcc862e6da` |
| `install.py` | `e9f32d0c455db071912d260a0962528c083f58aeee2225028b67b56269580c2b` |
| `dependencies.json` | `1383ff26c1720a2bb8798dc50ec604fb4c6052604b9be0916dd0154a52418ac2` |
| `node.json` | `9266524ba2712760d538b66cf491382b9d908dd8acb1b4c8da8a7909fd47e5df` |
| `validate-node.mjs` | `2cc4a69ff21a860d7df3665f33689d1bfe0b3c5883da5f94ee85e184e7e027d9` |
| Judge `final_judge.py` | `814f37eb3c23f8998bc488b8af1061c51dabeef4c5375a37ba5ae7fd43c82f06` |
| Judge `pytest_launcher.py` | `37c9eac585da04f2a467714f535f37df1aa2a1dda8e4d503b20c672df6a8f431` |

## JavaScript runtime

`node.json` pins Node.js 22.14.0 (LTS) and the official SHA-256 checksums for
Linux x64 and arm64 archives. The repository's getting-started Studio guide
requires Node.js 18 or later; no exact Node.js release is declared for its
WebAssembly interface. This explicit environment pin satisfies that documented
floor and supports ES modules, top-level await and WebAssembly. It is an
environment selection, not a version extracted from the Cargo lock.

Installation tries the exact version at Alibaba's Node.js release mirror first.
Its release checksum list was checked against
`https://nodejs.org/dist/v22.14.0/SHASUMS256.txt`; both list the recorded hashes.
If the mirror download fails, the installer reports the error and tries the
official release URL for the same version. Downloads have retries and a
minimum-speed timeout; a checksum mismatch is fatal, with no alternate version.
No third-party archives or host caches are shipped with these text inputs.

The runtime is extracted into `/opt/node-v22.14.0-linux-<architecture>` and exposed
as `/usr/local/bin/node`. The system package step explicitly installs its GNU C,
GCC and C++ runtime libraries (`libc6`, `libgcc-s1`, `libstdc++6`) from the Ubuntu
repositories, preferring Alibaba. These follow the selected Ubuntu distribution;
the Node.js archive itself is pinned by version and checksum.

Installation executes `validate-node.mjs` as the unprivileged `nobody` account
from a temporary directory with a clean environment and system PATH. It checks
the exact version, ES-module loading, top-level await and compilation and
instantiation of an empty WebAssembly module. Its log includes the resolved
executable, user ID and working directory. Any failure aborts installation.
The validation script is retained beside the runtime so it can also be run by
the judge user in a network-disabled container. This startup check does not
replace the nine original F01 tests or claim to validate database behavior.

## Rust and Cargo

`dependencies.json` requests native Git objects from the public crates.io index
at an immutable commit. Each object has its Git content address and a SHA-256
checksum. Its package requests retain the exact versions and archive SHA-256
checksums from the application's Cargo.lock, excluding local workspace members.
Package names are resolved from these authentic registry records during install;
there are no aliases, encoded names, fabricated manifests or replacement locks.

To regenerate the input, read the external registry entries from Cargo.lock,
locate each package's index file in `git ls-tree -r` at the chosen index commit,
and record that file's Git blob ID and SHA-256. Group the original version and
archive-checksum pairs by blob. Verify that resolving every request reproduces
the original name, version, source and checksum. Never include workspace members.

Installation fetches the commit's trees with Git's blob filter, verifies that all
requested objects belong to that snapshot, then fetches those objects explicitly.
It verifies each metadata SHA-256 before resolving versions, verifies downloaded
crate archives against the lock-derived SHA-256, and generates Cargo directory
source checksums. Missing objects, missing versions, download failures and
checksum mismatches are fatal. The complete resolved inventory is retained in
`/opt/offline-cargo/resolved-packages.json` for inspection inside the image.

Alibaba's sparse registry supplies the preferred crate download endpoint. Its
mirror does not provide an immutable Git object endpoint, so index metadata comes
from the official rust-lang registry repository on GitHub. Pinned Rust 1.88.0
archives are tried on Alibaba first and then on static.rust-lang.org if unavailable.
Archive downloads have retries and minimum-speed timeouts; registry Git transfers
also have retries, minimum-speed timeouts and per-attempt time limits.

Only text metadata and installer code ship here. Registry objects and package
sources are downloaded at installation, without the application checkout or a
host cache. Cargo uses `/opt/cargo-vendor` with networking disabled for the frozen
build. Installation links `/.cargo/config.toml` to the verified source configuration
at `/opt/offline-cargo/config.toml`. Cargo searches ancestor directories up to the
filesystem root, so this applies to external clients in arbitrary working
directories and fresh user homes. The build and test commands do not inject
`CARGO_HOME`; Cargo keeps its writable cache in the invoking user's home.
The installed vendor and configuration remain readable by ordinary users.
This provisions the environment independently of shell startup files or
per-test configuration.

## Earlier fresh-image verification (2026-10-25, 07:27 UTC)

The declared recipe was replayed on Linux x64 from a fresh
`codingbench-base/ubuntu:24.04` container. Installation mounted only these text
inputs read-only at `/env-assets`, without a checkout or host dependency cache.
Installation succeeded, and the subsequent network-disabled frozen release
build succeeded in 3 minutes 58 seconds. No installer or runner command changes
were needed for this recheck.

The environment-only image produced by that replay was separately exercised
with networking disabled. The actual judge account, `cbagent` (UID 1001), found
Node.js 22.14.0 from an unrelated temporary working directory through its normal
login-shell PATH. Every shared library reported by `ldd` resolved. The retained
validation module passed under that account. Neither warm source directory was
present in this environment image.

Using that same environment-only image, the harness's `casebox test` entry built
a copy of the reference offline and ran the unchanged original F01 selection as
the judge account against a read-only product tree. All nine original identities
passed, with no skipped cases, in 2.23 seconds. The WebAssembly case reached and
passed its database behavior assertions; startup validation alone was not used
as evidence of database correctness. Collection order matched the original audit.
Raw installation, offline-build, runtime, collection and test logs, input hashes,
and base/environment image identities were retained in the repair evidence.

The supplied historical result remains eight passed and one failed in 2.14
seconds: process creation could not find `node`, so WebAssembly initialization
and database behavior were unobserved in that run. Its report states that judging
skipped installation and build. At recheck time the currently recorded judge
image also supplied Node.js 22.14.0 and passed all nine tests in 2.24 seconds.
This establishes current runtime delivery and fresh recipe execution separately;
the historical evaluated image identity is unavailable, so its provenance cannot
be assigned retrospectively. Linux arm64 execution remains unverified.

## WebAssembly toolchain (2026-11-03)

The product ships a WebAssembly package (`docs/assets/wasm/velnora.js` and
`velnora_bg.wasm`). The solve and judge containers have no network, and the
environment previously held only the x86_64 standard library, so the package
could not be built from source. `rust.json` now also pins the Rust 1.88.0
`wasm32-unknown-unknown` standard library (official manifest hash) and the
wasm-bindgen 0.2.108 CLI release archive (matching the vendored wasm-bindgen
crate). `install.py` verifies both archives by SHA-256 and size and installs
them under `/usr/local`. Verified: the reference builds offline with
`cargo build --frozen --release --target wasm32-unknown-unknown --lib
--no-default-features --features wasm` followed by `wasm-bindgen --target web`.
