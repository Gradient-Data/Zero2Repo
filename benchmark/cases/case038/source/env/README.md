# Registry-backed schema environment

Only this installer, a dependency lock and the public schema adapter are shipped.
No upstream package trees, archives, licenses or executable binaries are expanded
into the public inputs. The install command runs with this directory read-only
at `/env-assets`, network enabled, and no product checkout or host package cache.

`dependencies.json` pins the schema processor at 4.2.0 and its runtime dependency
at 5.1.4, the XML tree library at 6.0.2, setuptools at 77.0.3 and wheel at 0.45.1.
Every acceptable wheel has an immutable SHA-256 digest. The schema runtime edge
is resolved from the hash-verified processor wheel's standard `Requires-Dist`
metadata. It is a genuine upstream dependency graph, not a renamed registry
package or a replacement implementation. Every active runtime dependency must
match exactly one locked child; missing or ambiguous edges fail installation.
Names and download URLs discovered from that metadata are recorded in the
installed provenance, together with versions and verified digests.

The installer explicitly checks the Alibaba Cloud PyPI index first for the
locked compatible artifact, then the official PyPI index only if the exact
artifact is absent. Download or integrity errors fail directly. Transfers have
connection and total timeouts, retries and minimum-speed limits. The locked
portable wheels cover the platform tags published upstream; unsupported Python
or platform combinations fail rather than switching versions or compiling an
unlocked source release. The XML tree wheel includes its native runtime
libraries, so no separately fetched system XML libraries are required.

Registry artifacts are retained under `/opt/schema-dependencies/wheels` in the
built image. The schema processor and its evaluator are installed only inside
`_schema_fixture`, using the existing module relocation boundary. Neither is
installed as the contestant's public evaluator or registered through import
hooks. Original wheel metadata, licenses and copyright notices remain intact
under `/opt/schema-dependencies/distributions`, and in the original wheels.
Other installed dependencies retain their standard distribution metadata and
licenses. `/opt/schema-dependencies/provenance.json` records the actual registry
sources and verified artifacts. No identity or license text is rewritten to
make the public scan pass.

The public schema adapter and offline build entry are hash-verified before installation.
The adapter uses the pinned build backend to expand the current product's
package declarations and requires one public package. Its actual import origin
must match the declared source file or have unique ownership in the current
project's distribution metadata on the interpreter search path. A source import
does not require installed metadata. Missing or ambiguous identities fail
explicitly; native metadata and import errors propagate. The offline build
validates an installed import in a separate isolated interpreter and prints its
identity evidence. Each judge process resolves its own caller; no binding file
is written or reused across builds or renaming. Installation verifies only the
isolated processor, since no product exists yet. All conversion and validation
behavior remains unchanged, without a second public evaluator or import alias.
It preserves real schema validation, bidirectional atomic conversion, declaration
identity, public parser binding and the separation between public expression
evaluation and processor-internal schema preparation. Runtime resources,
including compiled locale catalogs, come from the verified upstream wheels.
The adapter does not substitute fabricated schema results or suppress failures.

The subsequent product build uses `--no-index --no-deps --no-build-isolation`.
All build dependencies and runtime resources are installed in system locations
before that offline step. Tests run with the image's `python3`, without network,
and do not require writable product files or access to `/env-assets`.
