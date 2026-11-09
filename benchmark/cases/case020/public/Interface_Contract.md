# Interface Contract

Invoke the client with `python -m velmoras.velmora <command> <arguments>` from the caller's working directory, with the product root on `PYTHONPATH`. Python recipes import from `velmora`; the launch module is `velmoras.velmora`.

`VELMORA_HOME` names the client home. `NO_COLOR` controls colored output. Text inputs and outputs use UTF-8. `--format=json` writes one complete JSON document to stdout. Diagnostics go to stderr, using the labels `ERROR:` and `WARN:`; initialization diagnostics use `Error in Velmora initialization:`. Diagnostic text carries the affected reference, file, extension, or caller-supplied cause where applicable. The `ERROR:` line for a recipe callback failure carries its callback name as `<callback>()`; the diagnostic includes the caller-supplied error payload, with continuation details on indented following lines.

Exit status `0` denotes success, `1` a reported command failure, `6` an invalid package configuration, and `7` an unexpected exception from a custom deployer.

Recipe references have the form `<name>/<version>[@<user>/<channel>][#<recipe-revision>]`. Binary references append `:<package-id>[#<package-revision>]`. Revisions and package identities are strings. A version is dot-separated components optionally followed by `-<prerelease>` and then `+<build>` qualifiers. In a requirement, the version position also accepts a range `[<expression>]` or `[<expression>, include_prerelease]`; an expression is one or more `||`-separated alternatives, each a space-separated conjunction of terms `>VERSION`, `>=VERSION`, `<VERSION`, `<=VERSION`, `<prefix>*`, `^VERSION` (compatible-major) or `~VERSION` (compatible-minor), where `VERSION` denotes a version string.

Recipe operations accept repeated profile selectors `-pr <profile>`, `-pr:h <profile>`, `-pr:b <profile>`; setting assignments `-s <key=value>`, `-s:h <key=value>`, `-s:b <key=value>`, `-s:a <key=value>`; option assignments `-o <selector:option=value>`, `-o:b <selector:option=value>`, `-o:a <selector:option=value>`; configuration assignments `-c <key=value>`, `-c:b <key=value>`, `-c:a <key=value>`; and core configuration `-cc <key=value>`. Package-specific assignments use `<pattern>:<key>=<value>`.

Repository selection uses `-nr`, or `-r <remote>`. Graph operations accept `--requires=<reference>`, `--tool-requires=<reference>`, `--update`, repeated `--build=<policy-or-pattern>` (policy values `never`, `missing`, `missing:<pattern>`, `compatible:<pattern>`, `cascade`, a reference pattern `<pattern>` where `*` matches every package, and an exclusion `!<pattern>`), `--lockfile <path>`, `--lockfile=`, `--lockfile-partial`, `--lockfile-clean`, and `--lockfile-out <path>`.

The service launches with `python -m velmoras.server.server_launcher`; `VELMORA_SERVER_HOME` names its home. Its address comes from `server.conf`.

## `config install`

`config install <source> [--type <type>] [-sf <source-folder>] [-tf <target-folder>]` accepts a directory, archive, URL, or Git location as a string. Configuration files appear beneath the selected client home, at the supplied relative destination paths. `<type>` is one of `git`, `dir`, `file`, or `url`. A `.velmoraignore` file in the supplied configuration holds one glob pattern per line, matched against paths relative to the selected source folder.

## `config home`

`config home` writes the selected client-home path as one line on stdout.

## `config show`

`config show <key> --format=json` writes a JSON object on stdout whose keys are configuration names and whose values retain their JSON types.

## `profile list`

`profile list --format=json` writes a JSON array of stored profile-name strings on stdout.

## `profile path`

`profile path <name>` writes the absolute path of the selected profile as one line on stdout.

## `profile detect`

`profile detect --name <name> [--force]` writes the named profile under `profiles/<name>` in the selected home.

## `profile show`

`profile show` accepts profile, setting, option, and configuration assignments and `--context <context>`. With `--format=json`, stdout is an object with `host` and `build` profile records. Each record has `settings` and `options` objects mapping names to strings, a `conf` object of typed configuration values, and `build_env`, a string of newline-delimited environment assignments.

Text output for a selected context uses INI sections, including `[runenv]` with `<name>=<value>` lines on stdout. Context headings are diagnostics on stderr.

## `global.conf`

The client home contains `global.conf`, a UTF-8 text file of `<configuration-name>=<value>` assignments. Typed values can be booleans, numbers, strings, lists, or dictionaries.

Configuration names exchanged through this file or CLI assignments are `core:required_velmora_version`, `core:default_profile`, `core:default_build_profile`, `core.version_ranges:resolve_prereleases`, `core:non_interactive`, `core.net.http:cacert_path`, `core.sources:download_cache`, `tools.graph:skip_binaries`, `tools.build:jobs`, `tools.build:sysroot`, `tools.build:cflags`, `tools.build:cxxflags`, `tools.build:exelinkflags`, `tools.build:compiler_executables`, `tools.cmake.cmaketoolchain:generator`, `tools.cmake.cmaketoolchain:extra_variables`, `tools.system.package_manager:tool`, and `tools.system.package_manager:mode`. The compiler-executable dictionary uses `c` and `cpp` keys with executable-path strings.

## `profiles`

Profiles are UTF-8 files at `profiles/<name>` under the client home; profile arguments also accept file paths. Sections are `[settings]`, `[options]`, `[conf]`, `[buildenv]`, `[runenv]`, `[tool_requires]`, `[replace_requires]`, `[replace_tool_requires]`, `[platform_requires]`, and `[platform_tool_requires]`.

Setting dimensions are named `os`, `arch`, and `build_type`. Settings, options, and configuration use `<key>=<value>` lines; package selectors use `<pattern>:<key>=<value>`. `include(<profile>)` names an included profile. Template expressions use `{{ ... }}`, including `os.getenv(...)`. `VELMORA_DEFAULT_PROFILE` and `VELMORA_DEFAULT_BUILD_PROFILE` are profile-selection environment variables.

Environment entries use `NAME=value`, `NAME=!`, `NAME=+value`, or `NAME+=value`; `(path)` annotates a path value. Tool requirements are reference lines. Replacement entries use `<pattern>: <reference>` or `<pattern>: !`. Platform requirements are reference lines.

The standard default-profile filename is `profiles/default` in the client home.

## `settings_user.yml`

`settings_user.yml` is a YAML document in the client home. Setting names map to lists of value spellings or nested mappings of subsettings and their domains.

## `.velmoraignore`

A configuration source can contain `.velmoraignore`, a UTF-8 file with one relative file pattern per line.

## `graph`

Graph JSON is an object with a `graph` object containing `nodes` and `error`. `nodes` maps opaque string node identifiers to records. Dependency keys refer to these identifiers.

Node fields are:
- `name`, `version`, `user`, `channel`, `description`: declared metadata strings or null.
- `context`: the `host` or `build` context label.
- `ref`: recipe reference including recipe revision; `rrev`: recipe revision string; `package_id`: binary identity string; `prev`: package revision string or null.
- `package_type`: package-kind string; `settings`: setting-name to string mapping; `options`: option-name to string-or-null mapping.
- `remote` and `binary_remote`: repository-name strings or null; `package_folder`: artifact path string or null.
- `binary`: binary state label, using `Cache`, `Download`, `Build`, `Missing`, `Invalid`, `Skip`, or `Editable` for locally available, remotely available, selected build, unavailable, invalid configuration, omitted binary, or editable working tree respectively.
- `recipe`: recipe state label, including `Cache` for a locally available recipe, `Downloaded` for a recipe retrieved from a repository, and `Editable` for a working-tree recipe.
- `info_invalid`: configuration rejection reason string or null.
- `python_requires`: object keyed by reusable recipe references.
- `dependencies`: object keyed by target node identifier. Edge records expose `ref` and `require` reference strings and boolean usage traits `headers`, `libs`, `run`, `visible`, `build`, and `test`.

`error` is null or a failure record. Its `type` is `missing`, `conflict`, or `loop`; missing and loop records expose `require.ref` identifying the requirement, while conflict records expose `name` identifying the package.

## `graph info`

`graph info [<recipe-path>] [--requires=<reference>] [--tool-requires=<reference>] [--format=json]` accepts the shared recipe-operation arguments. JSON stdout uses the graph document, including its error record on graph resolution failure.

## `graph explain`

`graph explain [<recipe-path>] [--requires=<reference>] [-nr] --format=json` accepts shared recipe-operation arguments. Stdout contains `closest_binaries`, an object keyed by recipe reference. Each entry has `revisions`, keyed by recipe revision. A revision with candidates contains `packages`, keyed by binary identity.

A package record's `diff` object has `settings`, `options`, and `dependencies` categories. A category with differences has `existing` and `expected` string arrays; a category without differences has those arrays empty or omits them. Settings and options entries use `<name>=<value>`; dependency entries are contributed reference strings. A revision without candidates omits `packages`.

## `export`

`export <recipe-path> [-nr] [--user <user>] [--channel <channel>] [--format=json]` accepts a recipe directory or Python recipe path. JSON stdout is `{"reference":"<name>/<version>[@<user>/<channel>]#<recipe-revision>"}`.

## `create`

`create <recipe-path> [-tf <test-package-path-or-empty-string>] [--format=json]` accepts shared recipe-operation arguments. The associated consumer recipe path is `test_package/velmorafile.py`. JSON stdout uses the graph document.

## `install`

`install [<recipe-path>] [-g <generator>] [-of <output-folder>] [--format=json]` accepts shared recipe-operation arguments, repeatable generator names, and a caller-selected output directory. JSON stdout uses the graph document.

Deployment arguments are repeated `--deployer <name-or-path>`, `--deployer-folder <destination>`, and repeated `--deployer-package <reference-pattern>`, where a `!` prefix marks an exclusion pattern. Built-in deployer names are `full_deploy`, `direct_deploy`, and `runtime_deploy`. Deployment results are files under the selected destination, preserving package-relative file names; runtime deployment uses runtime-relative paths. Runtime diagnostics carry the label `runtime_deploy: WARN:` and the affected package reference.

Missing-binary configuration diagnostics on stderr use a `<reference>: WARN:` line immediately followed by INI configuration sections beginning with `[settings]` and setting assignments. The configuration block ends at an empty line.

## `inspect`

`inspect <recipe-path> --format=json` writes a JSON object on stdout. `name`, `version`, `description`, `license`, `author`, and `url` carry declared metadata; `topics` and `settings` are arrays of strings; `options_definitions` maps option names to arrays of string spellings; `default_options` maps option names to declared values with their JSON types. Loading diagnostics carry the recipe path and original caller-supplied cause.

## `source`

`source <recipe-path>` invokes the recipe's source entry; materialized files use the recipe-selected source paths. Failure diagnostics identify the recipe and supplied cause, acquisition location, or patch path.

## `build`

`build <recipe-path> [-of <output-folder>]` accepts the shared recipe-operation arguments. Source, build, and generated material use the recipe's declared folder locations; external command output uses its selected files or inherited streams.

## `export-pkg`

`export-pkg <recipe-path> [--format=json]` accepts shared recipe-operation arguments and writes the graph document on JSON stdout. Packaged files are located through the resulting binary reference.

## `test`

`test <consumer-path> <recipe-reference> [-nr]` accepts shared recipe-operation arguments. The supplied consumer is a Python recipe; diagnostics identify the consumer phase and supplied failure cause.

## `run`

`run [<recipe-path>] <command> [--context <context>]` accepts shared recipe-operation arguments, including direct `--requires` and `--tool-requires` inputs. The command is one string argument and executes in the caller's current working directory. External command streams and caller-selected files carry its output. Execution failures use the client failure status and stderr diagnostic channel.

## `new`

`new [<template-name-or-directory>] -d <key=value> ... -o <output-folder> [--force]` accepts repeatable template definitions. The output contains rendered files at their template-relative paths.

Template names exposed by the command are `basic`, `header_lib`, `cmake_lib`, `cmake_exe`, `meson_lib`, `meson_exe`, `msbuild_lib`, `msbuild_exe`, `bazel_lib`, `bazel_exe`, `autotools_lib`, `autotools_exe`, `premake_lib`, `premake_exe`, `qbs_lib`, `local_recipes_index`, and `workspace`. A template can also be a directory in the working directory or under `templates/command/new/<name>` in the client home. Template placeholders use `{{<key>}}`; `not_templates` contains paths or glob patterns for files exchanged without rendering.

Generated Python recipes are named `velmorafile.py`. A workspace project contains `velmoraws.yml` and a `liba` directory with its `velmorafile.py` recipe.

The local-recipes-index template uses `recipes/<name>/all/velmorafile.py`, `recipes/<name>/config.yml` with the version mapped to folder `all`, and `recipes/<name>/all/velmoradata.yml` for the supplied source URL and checksum.

## `velmorafile.py`

The recipe file is `velmorafile.py`, containing a Python subclass of `velmora.VelmoraFile`. A module-level `required_velmora_version` declaration is a version-expression string. Exported files and exported sources retain the relative names selected by recipe declarations.

## `velmorafile.txt`

`velmorafile.txt` is a UTF-8 INI-style consumer recipe. `[requires]`, `[tool_requires]`, and `[generators]` contain one reference or generator name per line. `[options]` contains `<selector>:<option>=<value>` assignments.

## `local-recipes-index`

A `local-recipes-index` repository is a directory with `recipes/<name>/config.yml`. This YAML file has a `versions` mapping from version strings to records with a `folder` string. The recipe resides at `recipes/<name>/<folder>/velmorafile.py`.

`velmoradata.yml` alongside that recipe has `sources` keyed by version. A source record has `url`, an array of URL strings, and `sha256`, a digest string.

## `velmora.VelmoraFile`

Import `VelmoraFile` from `velmora` and subclass it in a Python recipe.

### Declarations and callbacks

Metadata attributes `name`, `version`, `user`, `channel`, `description`, `author`, and `url` are strings; `license` is a string or sequence of strings; `topics` is a sequence of strings. `package_type`, `revision_mode`, `build_policy`, and `upload_policy` are string declarations. `package_type` values are spelled `library`, `static-library`, `shared-library`, `header-library`, `application`, `build-scripts`, `python-require`, `configuration`, and `unknown`. `build_policy` values are spelled `missing`, `never`, and `always`. The `upload_policy` value that withholds binary uploads is spelled `skip`. `settings` names setting dimensions as a string or sequence. `options` maps names to sequences of declared values; `default_options` maps option selectors to values. `requires`, `tool_requires`, `test_requires`, `python_requires`, `python_requires_extend`, `exports`, `exports_sources`, `generators`, and `implements` accept string or sequence declarations. The `implements` entry for automatically configured header-only packages is `auto_header_only`. Export selection accepts glob patterns with `!` exclusion prefixes.

Recipe callbacks take only `self`: `set_name`, `set_version`, `configure`, `requirements`, `build_requirements`, `layout`, `source`, `generate`, `build`, `package`, `package_info`, `package_id`, `validate`, `compatibility`, `system_requirements`, `build_system_requirements`, `test`, and `deploy`. A compatibility callback returns a list of dictionaries whose `settings` or `options` fields contain `(name, value)` pairs.

### Recipe context

`settings`, `settings_build`, and `options` support dotted attribute access, string conversion, comparisons, and `get_safe(name)`. `conf.get(name)` returns the configured typed value.

`folders.source`, `folders.build`, and `folders.generators` are writable relative-path strings. With `-of <output-folder>` on a local `install` or `build`, `build_folder` is `<output-folder>/<folders.build>` and `generators_folder` is `<output-folder>/<folders.generators>`; `source_folder` stays beneath the recipe directory. `source_folder`, `build_folder`, `package_folder`, `generators_folder`, and `deploy_folder` expose resolved directory strings. `tested_reference_str` exposes the tested recipe reference.

`cpp_info` has string-list fields `includedirs`, `libdirs`, `bindirs`, `resdirs`, `libs`, `system_libs`, `defines`, `cflags`, `cxxflags`, `sharedlinkflags`, `exelinkflags`, `frameworkdirs`, and `frameworks`. `components` is a mapping supporting keyed access and `items()` pairs; `components[name]` exposes component metadata with those fields and a `requires` list of component-reference strings. Editable metadata is writable through `cpp.source` and `cpp.build`, including their `components`. `buildenv_info` and `runenv_info` expose the environment-definition interface.

### Requirements and dependencies

`requires(reference, **traits)` accepts a reference string and keyword traits `override`, `headers`, `libs`, `run`, `visible`, `transitive_headers`, `transitive_libs`, and `package_id_mode`; usage and override traits are booleans and the identity mode is a string. `tool_requires(reference)` and `test_requires(reference)` accept reference strings.

`dependencies[name]` returns dependency information. `dependencies.values()` and `dependencies.direct_host.values()` yield dependency objects. `dependencies.items()` yields `(requirement, dependency)` pairs; requirement objects expose boolean `build`, `test`, `headers`, `libs`, `run`, and `visible` traits. Dependency objects expose `ref.name`, `ref.version`, `context`, `package_folder`, and `cpp_info`; `set_deploy_folder(path)` accepts a replacement package-location string. `python_requires[name].path` is the reusable recipe's exported directory.

### Identity and commands

`info.settings` supports attribute assignment and deletion. `info.requires.full_recipe_mode()` is a callable identity-mode entry. The `package_id_mode` argument accepts the named modes `unrelated_mode`, `semver_mode`, `major_mode`, `minor_mode`, `patch_mode`, `micro_mode`, `full_recipe_mode`, `revision_mode`, `full_package_mode`, and `full_mode`.

`run(command, env=<script-basename>, cwd=<directory>, ignore_errors=<bool>)` accepts a command string, optional environment-script name and directory string. Its handled result is the external command's integer status. Unhandled command failures use the client failure status and diagnostic channel.

The `revision_mode` spellings are `hash` for content-based revision selection and `scm` for source-control revision selection. The explicit consumer-test declaration is `test_type = "explicit"`. The options convention uses `header_only` and `shared`. The consumer-only option selector is `&`.

`python_requires_extend` entries have the form `<reusable-recipe-name>.<class-name>` and select an exported Python base class.

The default package layout names are `include`, `lib`, and `bin` for `cpp_info.includedirs`, `cpp_info.libdirs`, and `cpp_info.bindirs`, respectively; recipe assignments replace those locations.

## `velmora.errors.VelmoraException`

`from velmora.errors import VelmoraException` exposes `VelmoraException(reason)`, an exception initialized with a caller-supplied reason string. The reason appears in the CLI diagnostic when raised from a recipe or extension.

## `velmora.errors.VelmoraInvalidConfiguration`

`from velmora.errors import VelmoraInvalidConfiguration` exposes `VelmoraInvalidConfiguration(reason)`, an exception initialized with a caller-supplied reason string. The reason appears in the CLI diagnostic when raised from a recipe or extension.

## `velmora.tools.files.save`

`from velmora.tools.files import save` exposes `save(velmorafile, path, content)`. `path` is a filesystem path string and `content` is text or bytes; the output file is at that path.

## `velmora.tools.files.load`

`from velmora.tools.files import load` exposes `load(velmorafile, path)`, returning the selected file's text as a string.

## `velmora.tools.files.copy`

`from velmora.tools.files import copy` exposes `copy(velmorafile, pattern, src, dst, keep_path=<bool>)`. `pattern`, `src`, and `dst` are strings; destination paths use the source-relative path when `keep_path` is true and the basename when it is false. The optional argument can be omitted.

## `velmora.tools.files.get`

`from velmora.tools.files import get` exposes `get(velmorafile, url, retry=<integer>)`. The URL is a string; extracted archive members are files beneath the recipe's current source directory.

## `velmora.tools.files.download`

`from velmora.tools.files import download` exposes `download(velmorafile, url, filename, md5=<digest>, sha1=<digest>, sha256=<digest>, retry=<integer>)`. URL, filename, and supplied digest values are strings. The output is the file named by `filename`.

## `velmora.tools.files.patch`

`from velmora.tools.files import patch` exposes `patch(velmorafile, patch_file=<path>)`. The patch is a unified-diff file; affected files are in the current source directory. Failure diagnostics on stderr identify the patch or recipe.

## `velmora.tools.scm.Git`

`from velmora.tools.scm import Git` exposes `Git(velmorafile, folder=<path>)`. `clone(url, target=<directory>)` accepts repository and destination strings. `checkout(commit)` accepts a commit, branch, or tag string. `get_url_and_commit()` returns a two-element tuple `(url, commit)` of strings. Failure diagnostics on stderr carry the recipe identity and affected capture path or cause.

## `velmora.tools.system.package_manager.Apt`

`from velmora.tools.system.package_manager import Apt` exposes `Apt(velmorafile).install(packages)`, where `packages` is a list of package-name strings. Failure diagnostics on stderr identify the requested prerequisite.

## `velmora.tools.env.Environment`

`from velmora.tools.env import Environment` exposes `Environment()`. It provides `define(name, value)`, `unset(name)`, `prepend(name, value)`, `append(name, value)`, `prepend_path(name, value)`, and `append_path(name, value)`. Names and ordinary values are strings; path-operation values are strings or string lists.

`vars(velmorafile, scope=<scope-or-None>)` returns an environment-variable object. Its `save_script(basename)` writes a sourceable `<basename>.sh` script. Its `apply()` returns a Python context manager for the environment.

## `velmora.tools.env.VirtualBuildEnv`

`from velmora.tools.env import VirtualBuildEnv` exposes `VirtualBuildEnv(velmorafile)`. `vars()` returns an environment-variable object whose `apply()` is a Python context manager.

`VirtualBuildEnv` is also a generator selector accepted through `-g` or a recipe `generators` declaration.

## `velmora.tools.env.VirtualRunEnv`

`from velmora.tools.env import VirtualRunEnv` exposes `VirtualRunEnv(velmorafile)`. `vars()` returns an environment-variable object whose `apply()` is a Python context manager.

`VirtualRunEnv` is also a generator selector accepted through `-g` or a recipe `generators` declaration.

## `velmorabuild.sh`

Generated Bash activation files are `velmorabuild.sh` for build environments and `velmorarun.sh` for runtime environments, beneath the selected generators directory. They are consumed with shell `source`.

Configuration-specific build activation uses `velmorabuildenv-<lowercase-build-type>-<lowercase-arch>.sh`; the paired deactivation name prepends `deactivate_`. Environment values are strings; `PATH` and `LD_LIBRARY_PATH` carry colon-separated path lists.

## `remote add`

`remote add <name> <url> [--index=<integer>] [--force] [--type=local-recipes-index] [--recipes-only] [--allowed-packages <pattern> ...] [--insecure]` accepts a remote-name string and URL or local index directory. Package filters are repeatable reference patterns; a `!` prefix marks an exclusion pattern.

## `remote update`

`remote update <name> [--url <url>] [--index=<integer>] [--recipes-only] [--allowed-packages <pattern> ...] [--insecure | --secure]` accepts a stored remote name and supplied replacement properties. Package filters are repeatable reference patterns; a `!` prefix marks an exclusion pattern.

## `remote rename`

`remote rename <name> <new-name>` accepts two remote-name strings.

## `remote remove`

`remote remove <pattern>` accepts a remote-name pattern string.

## `remote enable`

`remote enable <pattern>` accepts a remote-name pattern string.

## `remote disable`

`remote disable <pattern>` accepts a remote-name pattern string.

## `remote logout`

`remote logout <pattern>` accepts a remote-name pattern string.

## `remote login`

`remote login <remote> <username> -p <password>` accepts remote, user, and password strings. Credentials can also be supplied through `VELMORA_LOGIN_USERNAME` and `VELMORA_PASSWORD`, or remote-specific environment names formed by appending `_<UPPERCASE-REMOTE-NAME>`.

## `remote list`

`remote list --format=json` writes a JSON array on stdout. Records contain `name` and `url` strings, `enabled` indicating whether the remote is enabled, and `verify_ssl` indicating certificate verification.

## `remote list-users`

`remote list-users --format=json` writes a JSON array on stdout. Each record has `name`, the remote-name string; `user_name`, the authenticated or recorded username string or null; and `authenticated`, a boolean authentication state.

## `list`

`list [<reference-pattern>] [-r <remote>] [-p <query>] [--lru <duration>] [-g <graph-json-path>] [-gb <status>] [-gr <status>] --format=json` writes a repository selection on stdout.

A reference pattern has the form `<name>[/<version>][#<recipe-revision>][:<package-id>[#<package-revision>]]`. Any component accepts `*` as a wildcard, and a revision component accepts `latest`. A query combines `<setting>=<value>` and `options.<option>=<value>` conditions with `AND`, `OR` and parentheses. A duration is an integer followed by a unit letter, `s` for seconds or `h` for hours. A `-gb` status is the lower-case form of a graph node `binary` label, and a `-gr` status the lower-case form of its `recipe` label.

The JSON root maps repository names to selection objects. The local repository label is `Local Cache`. A successful empty repository selection is `{}`; a repository error is an object with an `error` diagnostic string.

Each selected recipe reference maps to a record. Recipe-revision selections have `revisions`, keyed by recipe revision strings. Revision records can carry a numeric `timestamp` and `packages`, keyed by package identity strings. Package records expose `info`, with `settings` and `options` mappings, and `revisions` keyed by package revision strings. Recipe-only selections omit `packages`. Recipe-name-only selections have empty recipe records.

The complete JSON document is also the saved-list input format for selection-consuming commands; its path is caller-selected. Graph inputs are complete graph JSON documents.

## `search`

`search <pattern> -r <remote-pattern> --format=json` writes repository selection JSON on stdout. Its root keys identify repositories; each matched recipe reference maps to `{}`. A repository failure is carried by its `error` string.

## `pkglist merge`

`pkglist merge -l <list-path> [-l <list-path> ...] --format=json` reads saved repository selection documents and writes a repository selection JSON document on stdout. `--list` is the long spelling of `-l`.

## `pkglist find-remote`

`pkglist find-remote <list-path> -r <remote-pattern> --format=json` reads a saved repository selection. Stdout is repository selection JSON keyed by the matching remote names; no found artifacts is `{}`.

## `require add`

`require add --folder <recipe-directory> [<requirement> ...] [--tool <requirement> ...] [--test <requirement> ...]` accepts `-nr` or `-r <remote>`. The command writes `velmorafile.py`. Positional values identify ordinary requirements; `--tool` and `--test` identify build-tool and test requirements.

Reporting uses stderr lines labeled `WARN:` with a dependency category (`requires`, `tool_requires`, or `test_requires`) and bare package name, or `ERROR:` with a bare package name. A report can accompany exit status `0`.

## `require remove`

`require remove --folder <recipe-directory> [<requirement> ...] [--tool <requirement> ...] [--test <requirement> ...]`. The command writes `velmorafile.py`. Positional values identify ordinary requirements; `--tool` and `--test` identify build-tool and test requirements.

Reporting uses stderr lines with `WARN:`, carrying the dependency category (`requires`, `tool_requires`, or `test_requires`) and bare package name.

## `upload`

`upload [<pattern>] [-l <list-path>] [--list <list-path>] -r <remote> [-c] [-p <query>] [--only-recipe] [--force] [--check] [--dry-run] [--metadata <pattern> ...] [--format=json]` accepts an artifact selection pattern or saved repository selection JSON.

JSON stdout uses repository selection form, keyed by the destination remote. Recipe- and package-revision records expose `upload`, a boolean transfer decision. Prepared records expose `files`, mapping artifact filenames to local file-path strings. Saved prepared documents are accepted through the list argument.

Artifact upload bodies are the selected file bytes. Artifact filenames exposed by HTTP paths include `velmorafile.py`, `velmora_sources.tgz`, and `velmora_package.tgz`. Metadata paths contain `/metadata/<relative-path>`. An empty-selection diagnostic is a `WARN:` line on stderr.

## `download`

`download [<reference>] [--list <list-path>] -r <remote> [--only-recipe] [--metadata <pattern> ...]` accepts a recipe or binary reference or a saved repository selection JSON file. Artifacts and selected metadata are readable at paths returned by `cache path`. Failure diagnostics identify the affected reference.

## `cache path`

`cache path <reference> [--folder <folder>] --format=json` writes `{"cache_path":"<filesystem-path>"}` on stdout. The field names the selected artifact directory. Folder selectors are `export_source`, `source`, `build`, and `metadata`.

The recipe directory contains `velmorafile.py` and exported caller files; the package directory contains packaged caller files and `velmorainfo.txt`. `velmoramanifest.txt` is the integrity-information filename. Selected metadata files use their relative names under the metadata directory.

## `cache check-integrity`

`cache check-integrity <pattern> --format=json` writes a repository selection identifying damaged artifacts on stdout. A damaged recipe-revision record omits `packages`; binary damage is identified by its package identity and package revision. The local repository key is `Local Cache`. Integrity failure uses status `1` and an `ERROR:` line on stderr.

## `cache clean`

`cache clean <pattern> [--source] [--build] [--download] [--backup-sources]` accepts artifact-reference patterns and material selectors.

## `cache save`

`cache save <pattern> --file <archive-path> --format=json` writes an archive at the supplied path and a repository selection JSON document on stdout identifying its artifacts.

## `cache restore`

`cache restore <archive-path> [--format=json]` reads an archive produced by `cache save`. JSON stdout is a repository selection identifying the restored artifacts.

## `cache sign`

`cache sign <pattern>` accepts recipe and binary reference patterns. Signing diagnostics use the common stderr failure form.

## `remove`

`remove <pattern> [-r <remote>] [-c] [--dry-run] [--format=json]` accepts reference patterns. Without supplied confirmation, stdin accepts a `yes` or `no` line followed by a newline. JSON stdout is repository selection form identifying the selected removal; a declined local removal has an empty `Local Cache` object.

## `config install-pkg`

`config install-pkg <reference> [--lockfile <path>] [--lockfile-out <path>]` accepts a configuration recipe reference and lockfile paths. Installed configuration files reside beneath the selected client home; the installation record is `config_version.json`.

## `lock create`

`lock create [<recipe-path>] [-nr]` accepts shared recipe-operation arguments. `--lockfile-out <path>` names the JSON lockfile output.

## `lock merge`

`lock merge --lockfile <path> [--lockfile <path> ...]` accepts repeated lockfile paths. `--lockfile-out <path>` names the JSON lockfile output.

## `lock add`

`lock add [--requires <reference>] [--build-requires <reference>] [--python-requires <reference>] [--config-requires <reference>]` accepts repeated category arguments and `--lockfile <path>` or `--lockfile=`. `--lockfile-out <path>` names the JSON lockfile output.

## `lock remove`

`lock remove [--requires <reference>] [--build-requires <reference>] [--python-requires <reference>] [--config-requires <reference>]` accepts repeated category arguments and `--lockfile <path>` or `--lockfile=`. `--lockfile-out <path>` names the JSON lockfile output.

## `velmora.lock`

`velmora.lock`, or a caller-selected lockfile path, is a JSON object with optional `requires`, `build_requires`, `python_requires`, and `config_requires` arrays. An omitted category represents an empty array. Entries are strings in the form `<name>/<version>[@<user>/<channel>][#<recipe-revision>][%<timestamp>]`, where the timestamp suffix is numeric text.

## `config_version.json`

`config_version.json` is a JSON file under the client home. Its `config_version` field is an array of installed configuration-reference strings with recipe revisions: `<reference>#<recipe-revision>`.

## `velmora.api.velmora_api.VelmoraAPI`

`from velmora.api.velmora_api import VelmoraAPI` exposes `VelmoraAPI()`. Its `cache` attribute is the cache API object.

## `velmora.api.subapi.cache.CacheAPI`

The cache API returned by `VelmoraAPI().cache` exposes `get_backup_sources(exclude=<bool>, only_upload=<bool>)`. It returns a list of filesystem-path strings naming source-backup files.

## `MakeDeps`

`MakeDeps` is a generator selector accepted by `-g MakeDeps` or the recipe's `generators` declaration. Its output is `velmoradeps.mk` beneath the recipe's selected generators directory.

## `PkgConfigDeps`

`PkgConfigDeps` is a generator selector accepted by `-g PkgConfigDeps` or the recipe's `generators` declaration. Its output is named `<package>.pc` beneath the recipe's selected generators directory.

## `CMakeDeps`

`CMakeDeps` is a generator selector accepted by `-g CMakeDeps` or the recipe's `generators` declaration. Its output is named `<package>-config.cmake` beneath the recipe's selected generators directory.

## `CMakeToolchain`

`CMakeToolchain` is a generator selector accepted by `-g CMakeToolchain` or the recipe's `generators` declaration. Its output is `velmora_toolchain.cmake` beneath the recipe's selected generators directory.

`from velmora.tools.cmake import CMakeToolchain` exposes `CMakeToolchain(velmorafile)` with a `generate()` method.

## `MesonToolchain`

`MesonToolchain` is a generator selector accepted by `-g MesonToolchain` or the recipe's `generators` declaration, and a recipe callable imported from `velmora.tools.meson`: `MesonToolchain(self).generate()`. Native-file output is `velmora_meson_native.ini` and cross-file output is `velmora_meson_cross.ini`, beneath the selected generators directory.

## `SConsDeps`

`SConsDeps` is a generator selector accepted by `-g SConsDeps` or the recipe's `generators` declaration. Its output is `SConscript_velmoradeps` beneath the recipe's selected generators directory.

## `PremakeDeps`

`PremakeDeps` is a generator selector accepted by `-g PremakeDeps` or the recipe's `generators` declaration. Its output is `velmoradeps.premake5.lua` beneath the recipe's selected generators directory.

## `PremakeToolchain`

`PremakeToolchain` is a generator selector accepted by `-g PremakeToolchain` or the recipe's `generators` declaration. Its output is `velmoratoolchain.premake5.lua` beneath the recipe's selected generators directory.

## `AutotoolsDeps`

`AutotoolsDeps` is a generator selector accepted by `-g AutotoolsDeps` or the recipe's `generators` declaration. Its output is build-environment scripts beneath the recipe's selected generators directory.

## `AutotoolsToolchain`

`AutotoolsToolchain` is a generator selector accepted by `-g AutotoolsToolchain` or the recipe's `generators` declaration, and a recipe callable imported from `velmora.tools.gnu`: `AutotoolsToolchain(self).generate()`. Its output is `velmorabuild.conf` beneath the selected generators directory.

## `BazelDeps`

`BazelDeps` is a generator selector accepted by `-g BazelDeps` or the recipe's `generators` declaration. Its output is `dependencies.bzl` beneath the recipe's selected generators directory.

`from velmora.tools.google import BazelDeps` exposes `BazelDeps(velmorafile)` with a `generate()` method.

## `BazelToolchain`

`BazelToolchain` is a generator selector accepted by `-g BazelToolchain` or the recipe's `generators` declaration. Its output is `velmora_bzl.rc` beneath the recipe's selected generators directory.

`from velmora.tools.google import BazelToolchain` exposes `BazelToolchain(velmorafile)` with a `generate()` method. Writable attributes `compiler`, `cpu`, and `crosstool_top` accept the native toolchain selection strings.

## `QbsDeps`

`QbsDeps` is a generator selector accepted by `-g QbsDeps` or the recipe's `generators` declaration. Its output is Qbs dependency modules beneath the recipe's selected generators directory.

## `QbsProfile`

`QbsProfile` is a generator selector accepted by `-g QbsProfile` or the recipe's `generators` declaration. Its output is `qbs_settings.txt` beneath the recipe's selected generators directory.

## `MSBuildDeps`

`MSBuildDeps` is a generator selector accepted by `-g MSBuildDeps` or the recipe's `generators` declaration. Its output is `velmora_<dependency>_vars_<configuration>_<architecture>.props` beneath the recipe's selected generators directory.

## `velmoradeps.mk`

`velmoradeps.mk` is a Make include file. It defines `VELMORA_INCLUDE_DIRS`, `VELMORA_DEFINES`, `VELMORA_CFLAGS`, `VELMORA_LIB_DIRS`, `VELMORA_LIBS`, `VELMORA_SYSTEM_LIBS`, and `VELMORA_EXELINKFLAGS` as native compiler or linker argument lists.

Caller-defined prefix variables are `VELMORA_INCLUDE_DIR_FLAG`, `VELMORA_LIB_DIR_FLAG`, `VELMORA_LIB_FLAG`, `VELMORA_SYSTEM_LIB_FLAG`, and `VELMORA_DEFINE_FLAG`.

## `pkg-config files`

Generated `<package>.pc` and `<package>-<component>.pc` files are native pkg-config modules. They are loadable through `PKG_CONFIG_PATH` and `PKG_CONFIG_LIBDIR` by module name `<package>` or `<package>-<component>`. Native `pkg-config --cflags --libs <module>` returns shell-escaped compiler and linker argument strings.

## `CMake package files`

Generated `<package>-config.cmake` files are native CMake package configurations consumed by `find_package(<package> REQUIRED)`. Imported targets use `<package>::<package>` and `<package>::<component>`. Their target properties expose the declared dependency usage to a linked consumer.

## `velmora_toolchain.cmake`

`velmora_toolchain.cmake` is a native CMake toolchain file, accepted by `CMAKE_TOOLCHAIN_FILE`. Its native configuration exposes `CMAKE_BUILD_TYPE`, `CMAKE_SYSTEM_NAME`, and `CMAKE_SIZEOF_VOID_P`, and carries the selected compiler, sysroot, compile flags, linker flags, and caller-supplied CMake variables.

## `CMakeUserPresets.json`

`CMakeUserPresets.json` at the consumer source directory is a native CMake preset document including the generated `CMakePresets.json` from the generators directory.

## `velmora_meson_native.ini`

`velmora_meson_native.ini` is a Meson native file accepted by `meson setup --native-file`. Dependency declarations are consumed by Meson `dependency(<package>, method: 'pkg-config')`; native `buildtype`, `host_machine.system()` and `host_machine.cpu_family()` expose the selected configuration and platform.

## `SConscript_velmoradeps`

`SConscript_velmoradeps` is a native SCons script. `SConscript(...)` returns a mapping with the `velmoradeps` field, a dependency flag mapping accepted by `Environment.MergeFlags`.

## `velmoradeps.premake5.lua`

`velmoradeps.premake5.lua` is a Premake Lua input. The `velmoradeps[<lowercase-configuration>_<architecture>][<package>]` record contains `cflags` and `exelinkflags` string arrays accepted by Premake `buildoptions` and `linkoptions`.

## `velmoratoolchain.premake5.lua`

`velmoratoolchain.premake5.lua` is a native Premake Lua input loaded by the consumer's project file. It provides native configuration for that workspace and its projects.

## `velmora.tools.gnu.Autotools`

`from velmora.tools.gnu import Autotools` exposes `Autotools(velmorafile)` with `configure()` and `make()` methods. The helper consumes generated `velmorabuild.conf` and build-environment scripts. Native configure inputs include `CC`, `CPPFLAGS`, `CFLAGS`, `LDFLAGS`, and `LIBS`.

## `velmorabuild.conf`

`velmorabuild.conf` in the generators directory is the configuration file consumed by the `Autotools` build helper alongside generated build-environment scripts.

## `dependencies.bzl`

`dependencies.bzl` is a native Bazel Starlark input loaded from the generators directory. It exports `load_velmora_dependencies()`. Dependency labels have the form `@<package>//:<package>`.

## `velmora_bzl.rc`

`velmora_bzl.rc` is a native Bazel rc file consumed with `--bazelrc=<path>`. It defines `velmora-config`, selected by `--config=velmora-config`; native `compilation_mode`, `compiler`, and `cpu` carry the selected configuration and toolchain, with the selected `crosstool_top` toolchain label.

## `qbs_settings.txt`

`qbs_settings.txt` is a Qbs settings-import document consumed by `qbs config --import`. Dependency modules are loaded with the external Qbs dependency provider's `installDirectory` property set to the generators directory. Native `qbs.buildVariant`, `qbs.architecture`, and `qbs.targetOS` expose configuration and platform values.

## `MSBuild dependency props`

Generated `velmora_<dependency>_vars_<lowercase-build-type>_<architecture>.props` files are XML in the namespace `http://schemas.microsoft.com/developer/msbuild/2003`. Properties `Velmora<dependency>IncludeDirectories`, `Velmora<dependency>Libraries`, and `Velmora<dependency>BinaryDirectories` contain semicolon-terminated lists, or empty XML elements. Package-relative paths use `$(Velmora<dependency>RootFolder)/<relative-path>`.

## `graph build-order`

`graph build-order [<recipe-path>] [--requires=<reference>] [--order-by=<grouping>] [--reduce] --format=json` accepts shared recipe-operation arguments.

Stdout is a JSON plan with `order_by`, the grouping string `recipe` or `configuration`; `reduced`, a boolean reduction marker; and `order`, an array of levels, each an array of entries. In recipe grouping, entries have `ref`, a recipe-revision reference; `depends`, an array of prerequisite recipe references; and `packages`, an array of arrays of binary records. In configuration grouping, level entries are binary records and also have `ref`, `pref` (binary reference), and `depends` (prerequisite binary references).

Binary records contain `package_id` (identity string), `binary` (state label), and `info.settings` (setting-name to string mapping).

## `graph build-order-merge`

`graph build-order-merge --file <plan-path> [--file <plan-path> ...] --format=json` accepts saved JSON build plans. Stdout uses the same JSON plan form as `graph build-order`.

## `editable add`

`editable add <recipe-path> [-of <output-folder>] [-nr] [--ref=<reference>]` accepts a Python recipe file or its directory and a caller-selected output area.

## `editable remove`

`editable remove <recipe-directory>` or `editable remove -r <reference>` addresses a registered editable mapping.

## `editable list`

`editable list --format=json` writes a JSON object on stdout keyed by recipe reference. Each value has `path`, the absolute Python recipe-file path, and `output_folder`, an absolute output-directory string or null.

## `workspace init`

`workspace init [<path>]` creates the workspace definition `velmoraws.yml` in the selected directory.

## `workspace root`

`workspace root` writes the absolute workspace root as one line on stdout.

## `workspace info`

`workspace info --format=json` writes a JSON object on stdout with `folder`, the workspace-root string, and `packages`, an array of member records. Members have `path`, a relative recipe-directory string, `ref`, the recipe-reference string, and optional `output_folder`, a relative output-directory string.

## `workspace add`

`workspace add <recipe-directory> [-of <output-folder>] [-nr]` accepts a local recipe location and optional output area. A member's declared generators and build locations are relative to its recorded output area, or to its recipe directory when it has none.

## `workspace remove`

`workspace remove <recipe-directory>` accepts a member location.

## `workspace source`

`workspace source [--pkg=<pattern> ...]` accepts repeated package-reference selection patterns. Source outputs use member recipe-selected paths.

## `workspace install`

`workspace install [--pkg=<pattern> ...] [-nr] [--build=<policy>] [--lockfile <path>]` accepts shared recipe-operation assignments and repeated package selectors. Member-generated files use their declared generators directories.

## `workspace build`

`workspace build [--pkg=<pattern> ...] [-nr] [--lockfile <path>]` accepts shared recipe-operation assignments and repeated package selectors. Build files use the member recipe's selected locations.

## `workspace create`

`workspace create [--pkg=<pattern> ...] [-nr]` accepts shared recipe-operation assignments and repeated package selectors. Created artifacts are addressed by recipe and binary references. A refused creation exits with a nonzero status and an `ERROR:` line on stderr.

## `workspace super-install`

`workspace super-install [-nr] [-g <generator> ...] [-of <output-folder>] [--lockfile <path>] [--lockfile-out <path>] [--format=json]` accepts shared recipe-operation assignments. JSON stdout uses the graph document. Selected generators write under the supplied output folder, and a requested lock output uses lockfile JSON.

## `workspace open`

`workspace open <reference> [-nr]` accepts a package reference. The resulting recipe source directory has the package-name spelling beneath the working directory.

## `workspace complete`

`workspace complete [-nr]` uses the current workspace definition. Resulting membership is exposed by `workspace info`; member sources use their recorded local paths.

## `velmoraws.yml`

`velmoraws.yml` is a YAML workspace definition. `packages` is an array of records with `path`, a recipe location relative to the workspace root; optional `ref`, a recipe-reference string; and optional `output_folder`, a relative output-directory string.

## `deploy`

A caller-supplied deployer is a Python file selected with `--deployer <path>`, exporting `deploy(graph, output_folder, **kwargs)`. `output_folder` is the selected destination string.

`graph.root.velmorafile.dependencies.values()` yields dependencies with `context`, `ref.name`, and `package_folder`. Dependency `set_deploy_folder(path)` accepts a replacement artifact location. The deployer writes its selected relative deliverables under the destination.

## `extensions hooks`

Installed hook modules reside at `extensions/hooks/hook_<name>.py` under the client home. Callback names are `post_export`, `pre_validate`, `pre_source`, `pre_build`, and `post_package`; each receives `velmorafile`. The recipe object exposes its public declarations and folders, including `description` and `package_folder`. Hook rejections use the client failure form, with the extension identity and supplied reason in the diagnostic.

## `extensions profile.py`

`extensions/plugins/profile.py` under the client home exports `profile_plugin(profile)`. `profile.settings` is a mutable mapping from setting names to values. A raised `VelmoraException` supplies the failure reason.

## `extensions commands`

Command modules reside at `extensions/commands/cmd_<command>.py` under the client home. Top-level callbacks use `(velmora_api, parser, *args)`; subcommand callbacks use `(velmora_api, parser, subparser, *args)`. The corresponding command functions carry the command name and `<command>_<subcommand>` name.

Parser objects provide `add_argument` and `parse_args(*args)`; parsed values are available as named attributes. Custom formatters receive the command's returned value and write its selected representation. Load diagnostics identify the unavailable module filename.

## `velmora.cli.command.velmora_command`

`from velmora.cli.command import velmora_command` exposes `velmora_command(formatters=<mapping>)` and `velmora_command()`, used as command decorators. The formatters mapping associates a format-name string such as `json` with a function accepting the command result. `--format=json` selects that registered formatter.

## `velmora.cli.command.velmora_subcommand`

`from velmora.cli.command import velmora_subcommand` exposes `velmora_subcommand(formatters=<mapping>)`, used as a subcommand decorator. A formatter accepts the subcommand result.

## `velmora.api.output.cli_out_write`

`from velmora.api.output import cli_out_write` exposes `cli_out_write(text)`. The supplied text is written to stdout with a trailing newline.

## `extensions generators`

Installed generator modules reside at `extensions/generators/<module>.py`. An exported generator class has a constructor taking `velmorafile` and a `generate()` method. Its recipe object exposes `dependencies.direct_host.values()` and `generators_folder`; dependency objects provide `ref.name`, `ref.version`, and `package_folder`. Generator-written files use their declared paths beneath the generators folder.

## `extensions cmd_wrapper.py`

`extensions/plugins/cmd_wrapper.py` exports `cmd_wrapper(cmd, velmorafile, **kwargs)`. `cmd` is a command string and the return value is a command string; `velmorafile` is the calling recipe object. Wrapper failures use the common client diagnostic form.

## `extensions compatibility.py`

`extensions/plugins/compatibility/compatibility.py` exports `compatibility(velmorafile)`. The result is a list of dictionaries whose `settings` or `options` values are lists of `(name, value)` pairs.

## `extensions sign.py`

`extensions/plugins/sign/sign.py` exports `sign(ref, artifacts_folder, signature_folder, **kwargs)` and `verify(ref, artifacts_folder, signature_folder, files, **kwargs)`. Reference objects convert to the strings `<name>/<version>` for a recipe and `<name>/<version>:<package-id>` for a binary; folder arguments are path strings. `files` identifies artifact filenames and their local paths.

The signing return value is an array of records with `method` and `provider` strings and `sign_artifacts`, an object whose `signature` value is the extension-produced filename. Signature files are exposed under `sign/<filename>` in the artifact's metadata directory. Verification refusal raises `VelmoraException` with the supplied reason.

## `velmora.tools.sbom.cyclonedx_1_4`

`from velmora.tools.sbom import cyclonedx_1_4` exposes `cyclonedx_1_4(velmorafile, add_build=<bool>, add_tests=<bool>, extra_info=<mapping>)`. Optional arguments can be omitted. `extra_info` maps component `name` values to JSON component-field objects. The return value is a JSON-serializable CycloneDX document object.

## `velmora.tools.sbom.cyclonedx_1_6`

`from velmora.tools.sbom import cyclonedx_1_6` exposes `cyclonedx_1_6(velmorafile, add_build=<bool>, add_tests=<bool>, extra_info=<mapping>)`. Optional arguments can be omitted. `extra_info` maps component `name` values to JSON component-field objects. The return value is a JSON-serializable CycloneDX document object.

## `CycloneDX`

The CycloneDX JSON document exposes `bomFormat`, the format label `CycloneDX`; `specVersion`, the schema-version string; and `components`, an array of component records.

A component has `name` and `version` strings, `purl` in the form `pkg:velmora/<name>@<version>`, and `bom-ref`, a package URI including the `rrev` query qualifier for a recipe revision. Declared metadata appears in `description` and `licenses`, the latter an array with `license.id` string fields. Component augmentation can provide `supplier.name` as a string.

`metadata.component.bom-ref` identifies the document's root component. `dependencies` is an array of records with `ref`, a component identifier, and optional `dependsOn`, an array of component identifiers. Absence of `dependsOn` represents an empty outgoing-reference list.

## `report diff`

`report diff --old-reference <reference> --new-reference <reference> [--old-path <directory>] [--new-path <directory>] --format=json` writes a JSON object on stdout. Keys are absolute file paths and values are arrays of unified-diff line strings.

Path suffixes identify the material category and relative file: `e/<relative-file>` for recipe exports, `es/<relative-file>` for exported sources, and `s/<relative-file>` for acquired sources. Diff file headers begin `---` and `+++`, with `/dev/null` for an absent side; content removal and addition lines begin `-` and `+`. An empty comparison report is `{}`. Comparison failure uses status `1` and the common stderr diagnostic form.

## `server.conf`

The service reads `server.conf` from `VELMORA_SERVER_HOME`. It is an INI document with `[server]`, `[read_permissions]`, `[write_permissions]`, and `[users]`.

The `server` section exposes `jwt_secret` and `updown_secret` strings; `jwt_expire_minutes`, `authorize_timeout`, and `disk_authorize_timeout` numeric settings; `ssl_enabled` as a boolean; `port` and `public_port` as integer ports; `host_name` as the advertised host; `disk_storage_path` as the artifact-storage directory; and `custom_authenticator` and `custom_authorizer` as plugin-name strings.

Permission sections contain ordered `<name>/<version>@<user>/<channel>: <audience>` entries, with patterns in identity components and comma-separated audience names. The audience marker `?` names authenticated users and `*` names anonymous-inclusive access. The users section maps username strings to password strings.

Configuration refusal is exposed either by nonzero startup status and nonempty diagnostic stdout or stderr, or by HTTP `500` with a nonempty diagnostic response body from a started service.

## `GET /v1/ping`

`GET /v1/ping` is the service availability endpoint; a ready service responds with HTTP `200`.

## `GET /v2/users/authenticate`

`GET /v2/users/authenticate` accepts an `Authorization: Basic <credentials>` header containing HTTP Basic credentials. HTTP `200` carries a token as response-body text; authentication refusal has HTTP `401`. Subsequent authenticated requests carry `Authorization: Bearer <token>`.

## `GET /v2/users/check_credentials`

`GET /v2/users/check_credentials` accepts `Authorization: Bearer <token>`. Missing or rejected identity is signaled by HTTP `401`.

## `artifact protocol`

Recipe revision URLs have the form `/v2/velmoras/<name>/<version>/<user-or-_>/<channel-or-_>/revisions/<recipe-revision>`; binary revision URLs have the form `/v2/velmoras/<name>/<version>/<user-or-_>/<channel-or-_>/revisions/<recipe-revision>/packages/<package-id>/revisions/<package-revision>`. A missing user or channel uses `_`. Authenticated requests use `Authorization: Bearer <token>`.

`GET <revision-url>/files` addresses the revision's file listing. `GET <revision-url>/files/<relative-path>` returns a file's bytes in the response body. `PUT <revision-url>/files/<relative-path>` takes the file's bytes as the request body. `DELETE <revision-url>` addresses revision removal. Artifact names observed through these paths include `velmorafile.py`, `velmora_sources.tgz`, and `velmora_package.tgz`; metadata uses `/metadata/<relative-path>`.

HTTP status `200` signals successful requests, `401` an authentication-required or rejected-credentials outcome, `403` a permission refusal, `404` an unavailable exact revision or file, and `500` server configuration failure. Error response bodies are diagnostic text.

## `server authenticator`

The service home contains `plugins/authenticator/<name>.py`, named by `custom_authenticator`. Its `get_class()` returns the authenticator object. The object exposes `valid_user(username, plain_password)`, taking credential strings and returning a boolean authentication decision.

## `server authorizer`

The service home contains `plugins/authorizer/<name>.py`, named by `custom_authorizer`. Its `get_class()` returns an authorizer object.

The object provides `check_read_velmora(username, ref)`, `check_write_velmora(username, ref)`, `check_delete_velmora(username, ref)`, `check_read_package(username, pref)`, `check_write_package(username, pref)`, and `check_delete_package(username, pref)`. `username` is a string or null, `ref` is the recipe-reference object, and `pref.ref` supplies the corresponding recipe reference.

Returning permits the operation. Raising `velmora.internal.errors.AuthenticationException` or `velmora.internal.errors.ForbiddenException` gives the corresponding authentication or permission failure.

## `velmora.internal.errors.AuthenticationException`

`from velmora.internal.errors import AuthenticationException` exposes `AuthenticationException()` for service extensions. The externally visible authentication-required form is HTTP `401`.

## `velmora.internal.errors.ForbiddenException`

`from velmora.internal.errors import ForbiddenException` exposes `ForbiddenException()` for service extensions. The externally visible permission-refused form is HTTP `403`.

## `CMakePresets.json`

`CMakePresets.json` in the generators directory is a native CMake preset document. Configure and build preset names have the form `velmora-<lowercase-build-type>`. CMake accepts those names through `--preset` and `--build --preset`.

## `velmora_meson_cross.ini`

`velmora_meson_cross.ini` is a Meson cross file accepted by `meson setup <build-directory> --cross-file <generators-directory>/velmora_meson_cross.ini`. Meson `host_machine.system()` and `host_machine.cpu_family()` expose the target platform. `meson compile -C <build-directory>` builds the configured project.
