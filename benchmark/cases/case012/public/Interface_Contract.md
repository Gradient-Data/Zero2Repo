### Product overview

**`lint-policy`** is a vendored pair of Oxlint JavaScript plugins (a generic plugin and an opt-in Effect plugin) plus a copy entry that places them in a consuming repository. This document is the product’s shell: the copy entry and its outputs, the plugin names and entries, the rule names and option forms, and the form in which the host linter shows the plugins’ findings. What each rule reports and leaves silent, and what the copy does, are stated in the PRD; this document does not restate them.

The product is not an importable Python package, not a network service, not a wire protocol, and not an end-user command of `lint-policy`’s own. It is TypeScript source loaded by Node.js and the host linter; there is no compiled native extension and no bundled binary.

### Shape of the public surface

The public surfaces are the **copy entry**, the **generic plugin**, and the **opt-in Effect plugin**. There is no product-owned configuration-file format and no official registry package.

**Copy entry.** The skill copy is the Node script `skills/install-lint-policy/scripts/install.mjs`, run from a consuming repository as `node <script> [<dest>] [--force]`. `<dest>` is an optional destination path relative to the current working directory; `--force` is an optional flag; the two may appear in either order. The current working directory is the consuming tree. With `<dest>` omitted the destination is `tools/oxlint/lint-policy`. Its exit statuses, printed output, and files are stated under “Copy entry outputs” below.

**Generic plugin.** Published plugin name `lint-policy`. In the product tree its entry is `src/index.ts`. After skill copy its entry is `<dest>/index.ts`. The integrator registers that name and entry as the plugin’s specifier with the host linter.

**Effect plugin.** Published plugin name `lint-policy-effect`. In the product tree its entry is `src/effect/index.ts`. After skill copy its entry is `<dest>/effect/index.ts`. It is registered with the host linter as a second, independent plugin.

**Host configuration.** The host loads each plugin as a JavaScript plugin by published name and specifier. A rule is addressed in host configuration as `lint-policy/<rule>` or `lint-policy-effect/<rule>`, with a severity such as `"error"`. The host’s own configuration field names are not a product surface.

**Manual copy.** The generic plugin may also be vendored by copying the product tree’s `src` directory by hand; its entry is then `index.ts` in that copy.

**Repository manifest.** The product tree’s root holds `package.json`. Its `packageManager` field is a string `<name>@<version>`, optionally followed by `+<hash>`, naming the package manager and the version of it that the repository is installed with.

### Naming conventions

**Plugins.** The generic plugin’s published name is exactly `lint-policy`; the Effect plugin’s published name is exactly `lint-policy-effect`.

**Copy entry.** Script `skills/install-lint-policy/scripts/install.mjs`; default destination `tools/oxlint/lint-policy`; overwrite flag `--force`; bundled skill name `install-lint-policy`.

**Entries.** Product tree: generic `src/index.ts`, Effect `src/effect/index.ts`. Copied tree, relative to the destination directory `<dest>` (default or caller-chosen): generic `<dest>/index.ts`, Effect `<dest>/effect/index.ts`.

**Generic rule catalog.** The generic plugin publishes exactly these eighteen rule names:

- `no-array-filter-map`
- `no-reduce-accumulator-copy`
- `no-chained-type-assertions`
- `no-conditional-empty-object-spread`
- `no-known-value-widening`
- `no-module-mocking`
- `no-object-parameters`
- `no-reflect-apply`
- `no-reflect-get`
- `no-runtime-typeof`
- `no-shape-in-symbol-names`
- `no-unknown-parameters`
- `no-unknown-returns`
- `no-unknown-type-aliases`
- `no-unsafe-dictionary-type`
- `no-widen-then-assert`
- `require-readable-spacing`
- `require-safety-comment-for-type-assertion`

**Effect rule catalog.** The Effect plugin publishes exactly these five rule names:

- `no-manual-effect-error-tag`
- `no-manual-tag-comparison`
- `no-manual-tagged-construction`
- `no-service-constructor-imports`
- `prefer-effect-match`

**Rule options.** Two generic rules take an options object, passed in host configuration as the second element of the rule’s entry, after the severity:

- `no-runtime-typeof`: `["error", { "allowInTypeGuards": <boolean> }]`.
- `require-safety-comment-for-type-assertion`: `["error", { "markers": [<marker>, …] }]`, a list of one or more distinct, non-empty marker strings.

Either options object may be omitted (the rule entry is then just the severity). No other rule takes options.

**Fix mode.** The host’s fix mode is `--fix`; a fix a rule offers is written back to the linted file in place.

### Copy entry outputs

A path the copy prints is either absolute or relative to the working directory the copy ran in; which of the two is the implementer’s choice.

**Success.** Exit status `0`. Standard output names the destination directory `<dest-path>` and the generic plugin entry `<generic-entry-path>` (the file `<dest>/index.ts`, the specifier to register `lint-policy` with). Each named path is written as one whitespace-free word, optionally followed directly by `.`, `,`, `;` or `:`. The rest of the wording, the number and order of lines, and anything on standard error are the implementer’s choice.

**Refusal (destination exists, no `--force`).** Exit status `1`. Standard error names the destination directory `<dest-path>`, written as one whitespace-free word, optionally followed directly by `.`, `,`, `;` or `:`. The rest of the wording and any other output are the implementer’s choice.

**Files.** The destination contains the generic entry `index.ts` and the Effect entry `effect/index.ts`, both directly relative to the destination directory, and, at any depth, a non-empty file named `LICENSE` holding the license terms of the vendored third-party code the plugins carry and a non-empty file named `UPSTREAM.md` recording where that code came from. The wording of those two files, and which other files the destination holds, are the implementer’s choice.

### Observing findings

**The report.** The host linter is run with `--format json`. Its standard output is then exactly one JSON object, the report; the plugins write nothing to standard output. The report’s `diagnostics` field is a list holding one object per finding. For a finding from a plugin rule:

- `code` is the string `<plugin>(<rule>)`: the published plugin name and rule name.
- `labels` is a list whose first element’s `span` carries `line` and `column`: the 1-based line and column where the finding’s reported position starts.
- `message` and every other field are the implementer’s choice.

**Exit status.** The host exits `0` when no rule enabled at `error` reported a finding, and non-zero when one did. The plugins define no exit codes of their own.

**Host refusals.** A configuration the host refuses, and source the host cannot parse, end the run with a non-zero exit status; the wording of the host’s own text is the host’s.
