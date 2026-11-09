# Interface Contract

The installable Python distribution is named `velnora`. Its import package is `velnora`, located under `src/velnora`; `PYTHONPATH` can include `<product-root>/src`. The console executable is `velnora`, invoked with the caller's working directory and environment. The equivalent module command is `python -m velnora`, using the interpreter in which the product is installed. Installed distribution metadata exposes the product version as a string.

Invocation form: `velnora [<global-options>] <command> [<arguments-and-options>]`. Global switches are `--no-ansi`, `--no-plugins`, `--no-cache`, `--no-interaction`, and `-n`; `--project <path>` names a project root and `--directory <path>` names a working directory. `--` terminates option parsing where a command accepts trailing arguments. `--version` writes `Velnora (version <version>)` followed by a newline to stdout.

stdin supplies UTF-8 text to interactive commands; text output also uses UTF-8. stdout and stderr are separate channels. Successful commands exit `0`; refused commands exit `1`. Command diagnostics are nonempty stderr text carrying the affected declaration, dependency, source, command, version constraint, or filesystem path when identified. Diagnostic sentences are not fixed. Installer operation failures have their package diagnostic on stdout. The `run` entry exposes the invoked program's stdout, stderr and completion status.

Environment names used for configuration are `HOME`, `VELNORA_CONFIG_DIR`, `VELNORA_CACHE_DIR`, `VELNORA_VIRTUALENVS_IN_PROJECT`, `VELNORA_VIRTUALENVS_PATH`, `VELNORA_KEYRING_ENABLED`, and `VELNORA_NO_INTERACTION`. Directory-valued variables take filesystem paths; configuration-valued variables take textual setting values. Active Python environment inputs are `PATH`, `VIRTUAL_ENV`, `CONDA_PREFIX`, and `CONDA_DEFAULT_ENV`.

HTTP transport accepts `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`, and `no_proxy`. `REQUESTS_CA_BUNDLE` and `SSL_CERT_FILE` carry CA certificate paths for the corresponding HTTPS transports. Repository credentials can be supplied as `VELNORA_HTTP_BASIC_<NAME>_USERNAME`, `VELNORA_HTTP_BASIC_<NAME>_PASSWORD`, and `VELNORA_PYPI_TOKEN_<NAME>`, with the repository name uppercased and hyphens replaced by underscores.

System keyring access uses the available system service. On a Secret Service desktop, `DBUS_SESSION_BUS_ADDRESS`, `XDG_RUNTIME_DIR`, and `XDG_DATA_HOME` identify that service session and its storage locations.

## `velnora check`

Syntax: `velnora check [--strict] [--lock]`.

Validation records are on stderr: `Error: <diagnostic>` and `Warning: <diagnostic>`. A declaration warning carries its bracketed declaration subject as `[tool.<legacy>.<field>]`; a lock diagnostic identifies `velnora.lock`. Other project-definition diagnostics carry the affected field, declared name, compatibility constraint, or referenced path when identified; a generic failure diagnostic has no separate subject field. Only the labels and carried information are fixed.

`<legacy>` denotes the literal legacy table key identified under `pyproject.toml`.

## `velnora lock`

Syntax: `velnora lock [--regenerate]`. The output document is `velnora.lock` in the project root.

Resolution failures use exit `1` with a nonempty stderr diagnostic carrying the conflicting dependency names or source identifier. A repository withdrawal warning is a stderr record labelled `Warning:` carrying the package identity and the repository-supplied withdrawal reason when present.

## `velnora build`

Syntax: `velnora build [--format <format>] [--output <directory>] [--clean] [--config-settings <key>=<value>]...`. The short spelling `-c <key>=<value>` also supplies a build setting. The format selectors are `wheel` and `sdist`. `local-version=<label>` is the build setting syntax for a local version label.

Artifacts are files in `dist/` or the directory named by `--output`. A build refusal exits `1` and carries a nonempty stderr diagnostic identifying the rejected format, project, selected source, README path, or build requirement path as applicable.

## `velnora install`

Syntax: `velnora install [--no-root] [--only-root] [--no-directory] [--with <groups>] [--without <groups>] [--only <groups>] [--all-groups] [--extras <extras>]... [--all-extras] [--dry-run] [--compile]`. Group arguments use comma-separated names.

Installation exposes distributions through the selected environment's Python import system and standard distribution metadata, and executable entry points in that environment. Its project and lock documents are `pyproject.toml` and `velnora.lock`.

Preview operation records are stdout lines, with indentation before `- Installing <name> (<version>)`, `- Removing <name> (<version>)`, and `- Updating <name> (<old-version> -> <new-version>)`. Here the name identifies the affected distribution and the versions identify its selected or changed release.

Command validation and root-project installation refusals exit `1` with stderr diagnostics identifying the affected option, extra, group, project name, or `velnora.lock`; root-project installation diagnostics carry `Error:`. Dependency installation, artifact-integrity and build failures exit `1` with a nonempty stdout report carrying the affected package identity.

## `velnora sync`

Syntax: `velnora sync [--no-root] [--dry-run]`.

Results are installed distributions and commands in the selected project environment. Preview records are on stdout as indented `- Installing <name> (<version>)`, `- Removing <name> (<version>)`, and `- Updating <name> (<old-version> -> <new-version>)` lines. The name is a distribution identity and the versions identify the proposed releases. An installation-operation failure exits `1` and reports the affected package on stdout; a command refusal reports on stderr.

## `velnora add`

Syntax: `velnora add <requirement-or-path>... [--group <group>] [--optional <extra>] [--extras <extras>]... [--markers <expression>] [--source <name>] [--editable] [--lock] [--dry-run]`. A version-constrained package argument can be written `<name>@<constraint>`; the latest-selection spelling is `<name>@latest`.

The document carriers are `pyproject.toml` and `velnora.lock`; installed results are exposed in the project environment. A no-addition report is nonempty stdout identifying the dependency. Preview stdout records use indented `- Installing <name> (<version>)` or `- Updating <name> (<old-version> -> <new-version>)` lines. Refusals exit `1` with stderr identifying the rejected or incompatible dependency names. A dependency build failure exits `1` and identifies its package on stdout.

## `velnora remove`

Syntax: `velnora remove <package>... [--group <group>] [--lock] [--dry-run]`.

Outputs are `pyproject.toml`, `velnora.lock` and the selected environment's installed distributions. Preview stdout includes indented `- Removing <name> (<version>)` operation lines. Refusals exit `1` with a nonempty stderr diagnostic identifying the missing or incompatible dependency names.

## `velnora update`

Syntax: `velnora update [<package>...] [--only <groups>] [--lock] [--dry-run]`.

The output carriers are `velnora.lock` and installed distributions in the selected environment. Preview stdout includes indented `- Updating <name> (<old-version> -> <new-version>)` lines. A refused update exits `1` with stderr identifying the requested package or rejected argument.

## `velnora config`

Syntax: `velnora config [--local] <key> [<value>...]`, `velnora config [--local] --unset <key>`, and `velnora config --list`. `--` can separate a value from option parsing.

Queries write one newline-terminated value to stdout: strings are unquoted; Booleans, integers and lists are JSON; a package build-settings query is a JSON object. Listing records are `<dotted-key> = <rendered-value>` lines. String, Boolean and integer listing values use JSON representation. A nested build-setting member has a dotted member label.

Setting names and their value shapes are: `cache-dir`, `data-dir`, `python.installation-dir`, and `virtualenvs.path` take path strings; `virtualenvs.create`, `virtualenvs.in-project`, `virtualenvs.use-velnora-python`, `virtualenvs.options.system-site-packages`, `virtualenvs.options.no-pip`, and `keyring.enabled` take textual Booleans. `installer.no-binary` and `installer.only-binary` take comma-separated package names or the all-packages selector `:all:`. `installer.build-config-settings.<package>` takes a JSON object of named build-setting values. `solver.min-release-age` takes textual integer days; `solver.min-release-age-exclude` and `solver.min-release-age-exclude-source` take comma-separated package names or source names/URLs respectively.

Repository configuration keys are `repositories.<name>` or `repositories.<name>.url` with a URL value; `http-basic.<name>` with username and optional password arguments; `pypi-token.<name>` with a token argument; `certificates.<name>.cert` with a PEM CA path or a textual Boolean verification setting; and `certificates.<name>.client-cert` with a combined client certificate/private-key PEM path. Configuration refusals exit `1` with nonempty stderr.

## `velnora source add`

Syntax: `velnora source add [--priority <priority>] <name> [<url>]`; the valued form `--priority=<priority>` is also accepted.

The project document carrier is `pyproject.toml`, with source records under `tool.<legacy>.source`. Refusals use exit `1` and nonempty stderr.

`<legacy>` denotes the literal legacy table key identified under `pyproject.toml`.

## `velnora source remove`

Syntax: `velnora source remove <name>`.

The project document carrier is `pyproject.toml`. A refusal exits `1` and identifies the requested source on stderr.

## `velnora source show`

Syntax: `velnora source show [<name>...]`.

stdout contains blank-line-separated source records with colon-separated labels `name`, `url`, and `priority`. The values are the configured name, repository URL, and priority string; the URL line is absent for the built-in source. A missing-source refusal exits `1` and identifies the requested source on stderr.

## `velnora run`

Syntax: `velnora run <executable> [<arguments>...]` and `velnora run -- <executable> [<arguments>...]`.

An unavailable executable exits `1` with a nonempty stderr diagnostic carrying its name.

## `velnora version`

Syntax: `velnora version --short [<version-or-rule>] [--dry-run] [--next-phase]`.

Rule spellings are `major`, `minor`, `patch`, `premajor`, `preminor`, `prepatch`, and `prerelease`.

Success writes a single PEP 440 version string followed by a newline to stdout. Version declarations use `project.version` and `tool.<legacy>.version` in `pyproject.toml`. A version refusal exits `1` with nonempty stderr.

`<legacy>` denotes the literal legacy table key identified under `pyproject.toml`.

## `velnora python list`

Syntax: `velnora python list [<version>] [--all] [--implementation <name>] [--managed] [--free-threaded]`.

stdout is a compact, left-aligned text table. Its first line has the columns `Version`, `Implementation`, `Manager`, `Path`, in that order. Data cells occupy the spans beginning at their corresponding header positions; the final column includes the whole executable path, including embedded spaces. Version cells contain `<release>` with a trailing `t` for the free-threaded variant. Implementation cells use `CPython` or `PyPy`; manager cells use `Velnora` or `System`. A downloadable entry's Path cell carries the status marker `Available for download`. An empty result is a nonempty stdout notice in place of the table.

## `velnora python install`

Syntax: `velnora python install <release> [--implementation <name>] [--free-threaded] [--reinstall]`.

The installation result is an executable interpreter and its distribution files under the configured `python.installation-dir`. Interpreter paths are exposed through the Path column of `velnora python list`. An installation refusal or download failure exits `1` with a nonempty stderr diagnostic. A refused free-threaded request's diagnostic carries the minimum release for which free-threaded installation is supported; a refused malformed request's diagnostic carries the requested text.

Distribution download URLs use HTTPS origins `github.com` for Python Standalone Builds and `downloads.python.org` for PyPy. GitHub release resources are under `/astral-sh/python-build-standalone/releases/download/<build>/<archive>`. Release catalogue responses at `https://api.github.com/repos/astral-sh/python-build-standalone/releases` are JSON arrays of release objects, with individual objects also addressable through `/latest` and `/tags/<build>`; each object carries `tag_name` and `assets`, whose records carry `name`, `browser_download_url`, `size`, and `digest`. PyPy catalogue responses at `https://downloads.python.org/pypy/versions.json` are JSON arrays with `python_version`, `version`, `stable`, and `files`; each file record carries `download_url`, `filename`, `arch`, and `platform`. Distribution URLs return archive bytes and may redirect through HTTP `Location` headers.

## `velnora python remove`

Syntax: `velnora python remove <release>[t]... [--implementation <name>]`. The suffix `t` names the free-threaded variant.

Removal and absence reports are on stdout and exit `0`. A refused request exits `1` with nonempty stderr. Interpreter executable paths exposed by `velnora python list` are filesystem paths whose existence can be observed.

## `velnora env use`

Syntax: `velnora env use <python>`. The argument is an interpreter executable name or path, or the selection-clearing token `system`.

The selected environment and interpreter are exposed through `velnora env info`. A refusal exits `1` with a nonempty stderr diagnostic carrying the interpreter argument or Python compatibility constraint when identified.

## `velnora env info`

Syntax: `velnora env info [--path | --executable]`. `--path` writes one absolute environment directory path followed by a newline to stdout. `--executable` writes one absolute Python executable path followed by a newline.

The unqualified report is stdout text with section headings `Virtualenv` and `Base`, separated by blank lines. Records within a section are `<label>: <value>`. Virtualenv labels are `Python`, `Implementation`, `Path`, `Executable`, and `Valid`, carrying the Python release, implementation name, environment directory, interpreter executable path, and `True`/`False` validity text respectively.

## `velnora env list`

Syntax: `velnora env list --full-path`.

stdout has one absolute environment directory path per line, with the suffix ` (Activated)` on a selected environment. Empty stdout represents an empty listing.

## `velnora env remove`

Syntax: `velnora env remove <environment-name>` or `velnora env remove --all`.

The filesystem carriers are the environment directories previously exposed by `velnora env list --full-path`. A refusal exits `1` with nonempty stderr identifying the requested environment name.

## `velnora env activate`

Syntax: `velnora env activate`.

stdout contains one complete shell command followed by a newline, executable by the calling shell. Activation files are `<environment>/bin/activate` for POSIX shells, Bash, Zsh and mksh; `<environment>/bin/activate.csh` for Csh and Tcsh; `<environment>/bin/activate.fish` for Fish; `<environment>/bin/activate.nu` for Nushell; and `<environment>/bin/activate.ps1` for PowerShell on POSIX. For the Windows command shell, the activation file is `<environment>/Scripts/activate.bat`. An unavailable activation result exits `1` with nonempty stderr.

## `velnora new`

Syntax: `velnora new <destination> [--flat] [--interactive] [--name <name>] [--description <text>] [--author <name-and-email>] [--license <license>] [--python <constraint>] [--dependency <requirement-or-path>]... [--dev-dependency <requirement-or-path>]...`.

The project document is `pyproject.toml`. Its output fields are `project.name`, `project.version`, `project.description`, `project.license`, `project.requires-python`, `project.authors` as a list of objects with `name` and `email`, `project.dependencies` as requirement strings, and `dependency-groups.dev` as development requirement strings. Local requirements use PEP 508 file URLs. Build declarations are `build-system.requires` as a list of requirement strings and `build-system.build-backend` as an import string.

The destination contains a package source layout, a `tests` directory with Python source, and a README file at the path in `project.readme`. The source entry is `<package>/__init__.py` in the flat layout or `src/<package>/__init__.py` in the source layout. Namespace components are nested package directories. A destination refusal identifies its path on stderr.

Interactive input is newline-delimited stdin: project name, version, description, author, license, Python compatibility, main-dependency confirmation followed by dependency entries ending with an empty line, development-dependency confirmation followed by entries ending with an empty line, and generation confirmation. Prompts are human-readable text; their sentences are not fixed.

## `velnora init`

Syntax: `velnora init [-n] [--name <name>] [--description <text>] [--author <name-and-email>] [--license <license>] [--python <constraint>] [--dependency <requirement-or-path>]... [--dev-dependency <requirement-or-path>]...`.

The project document is `pyproject.toml`. Its output fields are `project.name`, `project.version`, `project.description`, `project.license`, `project.requires-python`, `project.authors` as a list of objects with `name` and `email`, `project.dependencies` as requirement strings, and `dependency-groups.dev` as development requirement strings. Local requirements use PEP 508 file URLs. Build declarations are `build-system.requires` as a list of requirement strings and `build-system.build-backend` as an import string.

The output document is in the current project directory. A referenced README path is the `project.readme` string. A declaration refusal identifies `pyproject.toml` on stderr.

Interactive input is newline-delimited stdin: project name, version, description, author, license, Python compatibility, main-dependency confirmation followed by dependency entries ending with an empty line, development-dependency confirmation followed by entries ending with an empty line, and generation confirmation. Prompts are human-readable text; their sentences are not fixed.

## `velnora show`

Syntax: `velnora show [<package>] [--format=json] [--with <groups>] [--without <groups>] [--only <groups>] [--all] [--top-level] [--latest] [--outdated] [--why] [--tree]`. Valued group controls also accept `--with=<groups>` and `--only=<groups>`; group values are comma-separated names.

With `--format=json` and no package argument, stdout is one JSON array of package objects. The read fields are `name` (distribution identity), `version` (locked version string), `description` (description string), and `installed_status` (`installed` or `not-installed`). The latest/outdated reports expose `latest_version` (candidate version string). The list reason view exposes `required_by` as an array of parent package names.

With a package argument and `--format=json`, stdout is one object with string fields `name`, `version`, and `description`. Its `dependencies` maps dependency names to constraint strings; `required_by` maps parent names to their constraint strings. Exact constraints can be bare release numbers; interval constraints use comparison operators.

The text tree is stdout. Root records are `<name> <version> [<description>]`. Each edge is `<indent><branch> <name> <constraint> [(<annotation>)]`. Each ancestor indentation segment occupies four columns, using `│   `, `|   `, or four spaces. Branches use `├──` or `└──`, or ASCII `|--` or backtick followed by `--`. An edge that closes a cycle carries a nonempty parenthesized annotation; other edges have no annotation.

A refused inspection exits `1` and writes a nonempty stderr diagnostic carrying the package, group, or `velnora.lock` prerequisite name.

## `velnora search`

Syntax: `velnora search <term>...`.

A nonempty result is a compact stdout table headed `Package`, `Version`, `Source`, `Description`, in that order. Data rows are whitespace-separated `<package-name> <version> <source-name> [<description>]`. An empty result is a nonempty stdout notice with no table header and empty stderr; the notice wording is not fixed.

## `velnora debug resolve`

Syntax: `velnora debug resolve [<requirement>...] [--python <version>]`.

stdout contains a section labelled `Resolution results:` followed by newline-separated, whitespace-separated `<name> <version> [<marker>]` rows. Names identify selected distributions and versions identify selected releases. A refused resolution exits `1` with a nonempty stderr diagnostic identifying the affected dependency.

## `velnora debug info`

Syntax: `velnora debug info`.

stdout is a text report with headings `Velnora`, `Virtualenv`, and `Base`, and colon-separated `<label>: <value>` records. The read Virtualenv labels are `Python`, `Implementation`, `Path`, and `Executable`, carrying the selected interpreter's release, implementation name, environment path, and executable path. The read Base label is `Platform`, carrying the platform string.

## `velnora debug tags`

Syntax: `velnora debug tags`.

stdout has one wheel compatibility tag per line, in `<interpreter>-<abi>-<platform>` form.

## `velnora publish`

Syntax: `velnora publish [--repository <name>] [--dist-dir <directory>] [--build] [--dry-run] [--username <username>] [--password <password>] [--cert <CA-path>] [--client-cert <PEM-path>] [--skip-existing]`. `--no-interaction` is accepted with this command.

The artifact input directory is `dist/` or the path in `--dist-dir`. The stdout preparation record is `Publishing <project-name> (<artifact-version>) to <destination-label>`, as a complete line. A configured destination label is its name. stderr upload progress carries the label `Uploading` followed by the artifact filename. Publication failures exit `1` and carry nonempty stderr diagnostics.

The built-in upload endpoint is `https://upload.pypi.org/legacy/`: HTTPS host `upload.pypi.org`, port `443`, and POST path `/legacy/`.

## `velnora self add`

Syntax: `velnora self add <requirement> [--dry-run]`.

Output declarations are under `VELNORA_CONFIG_DIR/pyproject.toml`; the runtime lock is `VELNORA_CONFIG_DIR/velnora.lock`.

Preview stdout contains indented operation records `- Installing <name> (<version>)` and `- Updating <name> (<old-version> -> <new-version>)`. Names identify affected distributions and versions identify their releases.

A refusal exits `1` with nonempty stderr identifying the dependency or prerequisite when reported.

## `velnora self remove`

Syntax: `velnora self remove <package> [--dry-run]`.

Output declarations are under `VELNORA_CONFIG_DIR/pyproject.toml`; the runtime lock is `VELNORA_CONFIG_DIR/velnora.lock`.

Preview stdout contains indented `- Removing <name> (<version>)` operation records, identifying the affected distribution and its version.

## `velnora self lock`

Syntax: `velnora self lock`.

The output document is `VELNORA_CONFIG_DIR/velnora.lock`.

## `velnora self install`

Syntax: `velnora self install`.

Installed distributions are exposed through the runtime interpreter and standard installed-distribution metadata.

## `velnora self sync`

Syntax: `velnora self sync`.

Installed distributions are exposed through the runtime interpreter and standard installed-distribution metadata.

## `velnora self update`

Syntax: `velnora self update [<constraint>] [--dry-run] [--preview]`.

The installed product is exposed through its `velnora` distribution metadata, installed Python module files and a fresh `velnora --version` invocation.

Preview stdout contains indented `- Installing <name> (<version>)` and `- Updating <name> (<old-version> -> <new-version>)` or `- Downgrading <name> (<old-version> -> <new-version>)` operation records. Names identify affected distributions and versions identify their releases. A skipped operation carries the suffix `: Skipped <explanation>`; only the `Skipped` status label is fixed.

## `velnora self show`

Syntax: `velnora self show --format=json [--addons]`.

stdout is one JSON array of runtime package objects. The read fields are `name` (distribution name string) and `version` (version string). A missing-lock refusal exits `1` with nonempty stderr identifying `velnora.lock`.

## `velnora self show plugins`

Syntax: `velnora self show plugins`.

stdout contains package heading records `  - <name> (<version>)[ <description>]`. A following indented provider-count record is `<count> plugin` or `<count> plugins`, `<count> application plugin` or `<count> application plugins`, or `<count> plugins and <count> application plugins`. A dependency block has the exact heading `      Dependencies` and records `        - <name> (<constraint>)`. Names identify distributions; the version is the provider's release and each constraint is its declared requirement. Blank stdout represents an empty plugin list.

## `velnora cache list`

Syntax: `velnora cache list`.

A populated stdout listing has one repository-cache name per line. An empty listing has empty stdout and a nonempty stderr notice. Completion exits `0`.

## `velnora cache clear`

Syntax: `velnora cache clear [<repository>[:<package>[:<version>]]] [--all]`.

Interactive confirmation is a stderr question carrying the package/version selection or the number of entries, followed by `(yes/no)` and a bracketed default response; it reads a yes/no line from stdin. Completion, absence and declined confirmation exit `0`. An absent selection carries a stdout notice identifying the repository or `<package>:<version>` when supplied. A selection refusal exits `1` with a nonempty stderr diagnostic.

## `pyproject.toml`

The project document is UTF-8 TOML at `<project-root>/pyproject.toml`.

The `[project]` table carries `name`, `version`, `description`, `license`, and `requires-python` as strings; `authors` and `maintainers` as arrays of objects containing `name` and `email`; `license-files`, `keywords`, `classifiers`, and `dynamic` as arrays of strings. `readme` is a relative file path string or an object with `text` and `content-type`. `[project.urls]` maps link labels to URLs. `[project.scripts]`, `[project.gui-scripts]`, and `[project.entry-points.<group>]` map entry names to `<module>:<callable>` strings.

`project.dependencies` is an array of PEP 508 requirement strings. `[project.optional-dependencies]` maps extra names to arrays of requirement strings. `[dependency-groups]` maps group names to arrays of requirement strings and `{include-group = <group-name>}` objects.

The legacy declaration carrier is the table directly below `tool` that contains `requires-velnora` in the supplied product-root `pyproject.toml`. In the forms below, `<legacy>` stands for that table's literal key, not a new namespace. The same key applies to project and runtime documents and to declaration subjects in diagnostics.

The `[tool.<legacy>]` metadata names are `name`, `version`, `description`, `authors`, `maintainers`, `license`, `readme`, `keywords`, `classifiers`, `homepage`, `repository`, `documentation`, `urls`, `scripts`, and `plugins`. Legacy author and maintainer values are arrays of name-and-email strings; legacy `readme` is a path string or array of paths. `urls` maps labels to URLs. `scripts` maps names to entry targets. `plugins` maps group names to tables of entry names and targets. `package-mode` is a Boolean, and `requires-velnora` is a version constraint string.

`[tool.<legacy>.dependencies]` maps package names to constraint strings, dependency objects, or arrays of conditional dependency objects. The `python` member is the locking Python constraint. Dependency object fields reached here are `version`, `python`, `markers`, `source`, `git`, `branch`, `tag`, `rev`, `subdirectory`, `path`, and `url` as strings, `extras` as a string array, and `optional`, `develop`, and `allow-prereleases` as Booleans. `[tool.<legacy>.extras]` maps extra names to dependency-name arrays. `[tool.<legacy>.group.<group>]` carries Boolean `optional`, string-array `include-groups`, and a `dependencies` table using the same dependency declaration shapes.

`[[tool.<legacy>.source]]` entries carry string fields `name`, `url`, and `priority`; the built-in source declaration has no `url` field. `[tool.<legacy>.requires-plugins]` maps distribution names to version strings, objects containing `version` and `markers`, or arrays of those objects. `[tool.<legacy>.build-constraints]` maps a dependency name to a table of build-requirement names and constraint strings.

`tool.<legacy>.packages` is an array of selection objects with `include`, `from`, and `to` path strings and `format` as a format string or string array. `tool.<legacy>.exclude` is an array of path patterns. `tool.<legacy>.include` is an array of path strings or objects containing `path` and `format`.

The `[build-system]` fields are `requires` (requirement-string array), `build-backend` (import string), and `backend-path` (relative directory array).

Interface-family inventory:

| Family | Carrier or interface |
| --- | --- |
| Standard metadata and dependencies | `project` and its subtables |
| Standard dependency groups | `dependency-groups` |
| Legacy metadata, version and file selections | `tool.<legacy>` |
| Legacy dependencies, extras and groups | `tool.<legacy>.dependencies`, `.extras`, `.group.<group>` |
| Sources, plugin requirements and build constraints | `tool.<legacy>.source`, `.requires-plugins`, `.build-constraints` |
| Validation declaration subjects | Bracketed paths under `tool.<legacy>` on stderr |
| Runtime sources | The same source-table form in `<VELNORA_CONFIG_DIR>/pyproject.toml` |
| Effective plugin project | `velnora.package`, with assignable metadata and `add_dependency` |
| Compatible external plugin objects | `Version` and `DirectoryDependency` in the external core package identified under External build API |
| Backend selection and delegation | `build-system` and External build API, with wheel, source-distribution and metadata callbacks |

## `config.toml`

Global functional configuration is UTF-8 TOML at `<VELNORA_CONFIG_DIR>/config.toml`. A dotted configuration key is represented by nested TOML tables and its final member; path settings are strings, Boolean settings are TOML Booleans, release age is an integer, and package/source policy collections are string arrays. `installer.build-config-settings.<package>` is a table of named string or string-array settings. Publishing destinations are `[repositories.<name>]` tables with a string `url` field.

## `velnora.toml`

Project configuration is UTF-8 TOML at `<project-root>/velnora.toml`. Dotted setting names are nested TOML tables with typed values: strings for paths, Booleans for Boolean settings, integers for release age, string arrays for package/source collections, and per-package tables for `installer.build-config-settings`. The in-project environment setting is `[virtualenvs]` with member `in-project`; project environment paths and creation settings are `virtualenvs.path` and `virtualenvs.create`.

## `auth.toml`

The file credential carrier is UTF-8 TOML at `<VELNORA_CONFIG_DIR>/auth.toml`. `[http-basic.<repository>]` carries string fields `username` and `password`; `[pypi-token]` maps repository names to token strings. `[certificates.<repository>]` carries `cert` as a CA path string or Boolean and `client-cert` as a PEM file path string. These are the storage fields for file-backed credentials and repository certificate settings.

## `velnora.lock`

The lock document is UTF-8 TOML at `<project-root>/velnora.lock`. Runtime operations use `<VELNORA_CONFIG_DIR>/velnora.lock` with the same document shape.

`[[package]]` records carry string `name` and `version`, Boolean `optional`, string-array `groups`, and string `python-versions`. `develop` is a Boolean field for editable source status when present. `markers`, when present, is either a PEP 508 marker string or a mapping of group names to marker strings. An omitted package/group marker represents unconditional applicability in that scope.

`package.dependencies` maps dependency names to constraint strings, conditional dependency records, or arrays of records. Records can carry `version`, `python`, and `markers` constraint strings and `extras` string arrays. `package.extras` maps extra names to arrays of requirement strings.

`package.source` carries string fields `type`, `url`, `reference`, `resolved_reference`, and `subdirectory` when applicable. The origin type spellings reached here are `legacy` for an indexed repository, `directory` for a local project, `file` for a local distribution, `url` for an archive URL, and `git` for a Git origin. `url` is the origin location, `reference` is the repository identity or requested Git reference, `resolved_reference` is the selected Git commit, and `subdirectory` is a package path inside that origin. Local file and directory URL fields can be project-relative paths. Built-in PyPI records omit the source table.

`package.files` is an array of objects with `file` (artifact filename) and `hash` (`<algorithm>:<hex-digest>`). `[metadata]` carries `lock-version` (format version string) and `python-versions` (locking Python constraint string). `package` is an array, including when it contains no records.

## `VELNORA_CONFIG_DIR/pyproject.toml`

The runtime project document is UTF-8 TOML at `<VELNORA_CONFIG_DIR>/pyproject.toml`. `dependency-groups.additional` is an array of PEP 508 strings declaring runtime add-ons. `tool.<legacy>.source` is an array of source tables with `name`, `url`, and `priority` string fields. Its companion document is `velnora.lock` in the same directory.

`<legacy>` denotes the literal legacy table key identified under `pyproject.toml`.

## `.venv`

An in-project environment resides at `<project-root>/.venv`. Environment directories reported by `velnora env info --path` have a `bin/python` interpreter on POSIX and installed commands under `bin/<script-name>`. The POSIX/Bash activation file is `bin/activate`.

Installed distributions expose their name, version, declared requirements and entry points through standard Python distribution metadata. Installed bytecode files use the `.pyc` suffix.

## `src`

Build input sources can also be module files `<module>.py` or package directories containing `__init__.py` at the project root, under `src`, or at explicitly selected source paths. Git exclusions are supplied by the project's `.gitignore` file, in Git ignore syntax.

## `wheel`

A wheel is a ZIP archive named `<distribution>-<version>-<python-tag>-<abi-tag>-<platform-tag>.whl`, stored in the artifact destination. Archive members include installable import files and `<distribution>-<version>.dist-info/METADATA`. The distribution metadata directory also carries `entry_points.txt` for declared entry points and standard installed-distribution file records.

`METADATA` uses Core Metadata email-style headers and a description body. Read fields are `Name`, `Version`, `Summary`, `Author`, `Author-email`, `Maintainer`, `Maintainer-email`, `License`, `License-Expression`, `License-File`, `Keywords`, `Classifier`, `Project-URL`, `Requires-Python`, `Description-Content-Type`, `Requires-Dist`, and `Provides-Extra`. Repeated headers retain multiple values. Name and version carry distribution identity; Summary carries its description; author and maintainer headers carry person names and email addresses; license headers carry license text, expression or file names; Keywords is comma-separated; Classifier is a classification string; Project-URL has comma-separated `<label>` and `<URL>` fields; Requires-Python is a Python version specifier; Requires-Dist is a PEP 508 requirement string; Provides-Extra is an extra name. Description-Content-Type is the body media type, and the body carries the long description.

`entry_points.txt` is UTF-8 INI: section names are entry-point groups, and each case-preserved `<entry-name> = <module>:<callable>` item carries a target. Console and graphical entry groups are `console_scripts` and `gui_scripts`. License file bytes are members under `<distribution>-<version>.dist-info/licenses/<relative-path>`. Python source and native extension members use their installable module paths; a native module's platform extension suffix is part of its member filename (`.so` on Linux).

## `sdist`

A source distribution is a gzip-compressed tar archive named `<distribution>-<version>.tar.gz`. It has one top-level directory containing project-relative source members and `PKG-INFO`. File members carry their selected source bytes. `PKG-INFO` uses Core Metadata headers and a description body, including `Name`, `Version`, `Summary`, `License-Expression`, `Author`, `Author-email`, `Keywords`, `Classifier`, `Project-URL`, `Provides-Extra`, `Requires-Dist`, and `Requires-Python`. Requirement headers carry PEP 508 strings, Python compatibility carries a version specifier, and the body is the long description.

## `simple`

A configured simple-repository URL addresses an HTTP or HTTPS package listing. For an index base, package pages are addressed by `<base>/<normalized-package-name>/`; the index root can contain HTML links to package pages. A single-page source carries distribution links directly at the configured URL.

HTML distribution links use `href` with the distribution location and optional `#sha256=<digest>` fragment, and can carry `data-requires-python`. JSON listings have Content-Type `application/vnd.pypi.simple.v1+json` and objects with `meta.api-version`, `name`, and `files`. Each file record carries `filename`, `url`, `hashes` mapping algorithm names to digest strings, `requires-python`, `yanked` as a Boolean or repository reason string, and `upload-time` as an ISO 8601 timestamp string when supplied. The nested `meta` object has an `api-version` string identifying the simple API format. Linked artifact URLs return distribution bytes.

HTTP Basic credentials use `Authorization: Basic <base64(username:password)>`. HTTPS connections exchange a server certificate and, when configured, the client's certificate material. Transport failures and access refusals surface through the invoking command's failure channels.

## `https://pypi.org`

The built-in PyPI HTTPS origin is `https://pypi.org`. Package listings are read at `/simple/<name>/` in simple-API JSON form. Release records are read at `/pypi/<name>/<version>/json`.

Release JSON exposes `info` with `name`, `version`, `summary`, `requires_python`, `requires_dist`, and `yanked`, plus a `urls` array of distribution records. Distribution fields reached here are `filename`, `url`, `hashes`, `digests`, `requires-python`, `yanked`, `packagetype`, and `size`; artifact links identify the actual archive locations. These fields carry distribution identity, metadata, requirements, integrity digests, kind and size.

## `multipart/form-data`

Publication sends HTTP `POST` to the configured repository URL, with Content-Type `multipart/form-data` and a matching boundary. An artifact part carries `filename=<artifact-name>` and the archive bytes. The filename is the distribution's basename.

Repository credentials use `Authorization: Basic <base64(username:password)>`. A token uses `__token__` as the username and the token as password. HTTPS uses the configured server-verification CA and client certificate material. HTTP `201` is a successful upload response; `409` denotes an existing artifact, and authentication or other rejection statuses are failure responses to the invoking publication command.

## `cache/repositories`

Repository-cache directories are under `<VELNORA_CACHE_DIR>/cache/repositories/<repository-name>/`. The directory name identifies the named repository cache.

## `velnora.plugins.plugin.Plugin`

Import: `from velnora.plugins.plugin import Plugin`.

A project plugin subclasses `Plugin` and supplies `activate(self, velnora, io) -> None`. Its distribution entry-point group is `velnora.plugin`, with entries mapping caller-chosen names to `<module>:<class>` targets. The activation argument exposes the effective project as `velnora.package`. An unsupported registration is reported by the invoking command as exit `1` with nonempty stderr.

## `velnora.plugins.application_plugin.ApplicationPlugin`

Import: `from velnora.plugins.application_plugin import ApplicationPlugin`.

An application plugin subclasses `ApplicationPlugin` and supplies `activate(self, application) -> None`. Its distribution entry-point group is `velnora.application.plugin`, with entries mapping caller-chosen names to `<module>:<class>` targets. Contributed commands are invoked as `velnora <registered-command-name>`; their output is the contributed command's output. An unavailable contributed command exits `1` with stderr identifying its name; an unsupported registration exits `1` with nonempty stderr.

## `velnora.velnora.Velnora`

The `velnora` argument supplied to a project plugin's `activate(self, velnora, io)` exposes `package`, the effective project-package object.

## `effective-project-package`

The effective `velnora.package` object exposes assignable `version` and `description` attributes and `add_dependency(dependency)`. `version` accepts a version object returned by `Version.parse(text)`; `description` accepts a string. `add_dependency` accepts a dependency object such as `DirectoryDependency(name, path)`.

## `external-version-object`

`Version` is exported by `constraints.version` relative to the external core package identified under External build API. This identifies the actual compatible external class, not a class in the product import package.

`Version.parse(text)` accepts a version string and returns a version object suitable for assignment to `velnora.package.version`.

## `external-directory-dependency`

`DirectoryDependency` is exported by `packages.directory_dependency` relative to the external core package identified under External build API.

`DirectoryDependency(name, path)` accepts a distribution-name string and a `pathlib.Path` identifying a project directory. It returns a dependency object accepted by the effective project package's `add_dependency` method.

## `velnora.console.application.Application`

The `application` argument of `ApplicationPlugin.activate` exposes the plugin-registration members `command_loader` and `event_dispatcher`.

## `velnora.console.command_loader.CommandLoader`

`application.command_loader.register_factory(command_name, factory) -> None` accepts a command-name string and a callable with no arguments returning a command object. A command class with a no-argument constructor is a valid factory.

## `cleo.commands.command.Command`

Import: `from cleo.commands.command import Command`.

A contributed command subclasses `Command`, has a no-argument constructor and a string `name` attribute, and implements `handle(self)` returning an integer completion status. `self.line(text)` accepts a string and writes it as a newline-terminated stdout line.

## `cleo.events.console_events`

Import: `from cleo.events.console_events import COMMAND`.

`COMMAND` is the event identifier accepted by `application.event_dispatcher.add_listener(COMMAND, listener)`. The listener receives `(event, event_name, dispatcher)`.

## `cleo.events.event_dispatcher.EventDispatcher`

`application.event_dispatcher.add_listener(event_name, listener) -> None` accepts an event identifier and a callable taking `(event, event_name, dispatcher)`. The same dispatcher is supplied as the callback's third argument.

## `cleo.events.console_command_event.ConsoleCommandEvent`

The command-event callback receives an `event` object with a `command` attribute. `event.command.name` is the string name of the command associated with the event.

## `build-backend`

A project's `[build-system]` supplies `requires`, `build-backend`, and `backend-path`. The declared Python backend module can expose these PEP 517 callbacks:

`get_requires_for_build_wheel(config_settings=None)` and `get_requires_for_build_sdist(config_settings=None)` return lists of requirement strings. `build_wheel(wheel_directory, config_settings=None, metadata_directory=None)` returns the generated wheel's filename. `build_sdist(sdist_directory, config_settings=None)` returns the generated source distribution's filename. The artifact file is in the supplied output directory. `prepare_metadata_for_build_wheel(metadata_directory, config_settings=None)` returns the generated metadata-directory name. Directory arguments are filesystem path strings. Build settings are a mapping of setting names to text or text-list values, or `None`.

A backend can delegate to the external backend module identified under External build API. Its distribution requirement and import target are the values of `build-system.requires` and `build-system.build-backend` in the supplied product-root `pyproject.toml`; these are actual external interfaces, separate from the product import package.

## `external-build-api`

The external build API is the backend module named by `build-system.build-backend` in the supplied product-root `pyproject.toml`. Its supplying distribution is declared in that document's `build-system.requires`; those declarations provide the actual requirement and import target for callers selecting this backend or importing it for delegation.

This module exports `build_wheel`, `build_sdist`, and `prepare_metadata_for_build_wheel`. A caller may bind the module as `api`. The external core package is the parent package of the `masonry` package containing this backend; it also exports the compatible plugin objects through the relative module paths stated below. These role descriptions refer to the supplied external package, without introducing replacement import names.

## `external-build-api.build_wheel`

`api.build_wheel(wheel_directory, config_settings, metadata_directory)` accepts an output-directory path, a build-settings mapping or `None`, and a metadata-directory path or `None`. The return value is the generated `.whl` filename, and that file resides in `wheel_directory`.

## `external-build-api.build_sdist`

`api.build_sdist(sdist_directory, config_settings)` accepts an output-directory path and a build-settings mapping or `None`. The return value is the generated `.tar.gz` filename, and that file resides in `sdist_directory`.

## `external-build-api.prepare_metadata_for_build_wheel`

`prepare_metadata_for_build_wheel` is exported by the external module identified under External build API and can be exposed by a declared PEP 517 backend as its metadata callback.

`prepare_metadata_for_build_wheel(metadata_directory, config_settings=None)` accepts a filesystem path string and a build-settings mapping or `None`. It returns the name of the generated `.dist-info` directory, located inside `metadata_directory`.
