# lint-policy — Full Product Requirements Document

## Product overview

**lint-policy** is an opinionated Oxlint ruleset that rejects low-evidence and low-signal TypeScript and JavaScript patterns. It is the ruleset its author uses with work, projects, and a team. It reflects that taste rather than attempting to be a universal coding standard.

The product is **meant to be vendored**, not treated as a fixed registry package. There is no official published package. A consuming repository copies the plugin, reads it, and may change it to match local standards. After the initial copy, the vendored files belong to that repository.

lint-policy is first a **generic Oxlint JavaScript plugin** whose eighteen rules apply to ordinary TypeScript and JavaScript. Effect-specific architecture policy lives in a **second, opt-in plugin** so projects that do not use Effect do not inherit Effect rules. A consuming Oxlint (or Vite+) configuration registers one or both plugins, enables the desired rules, and runs the host linter against source files. Each enabled rule either reports a diagnostic on a violating construct or stays silent on an allowed construct.

A first-time integrator copies the plugin into the target repository (by hand, or by running the bundled skill copy), registers the generic plugin with Oxlint, enables every generic rule at error severity, and — only when the target depends on Effect directly, or the user asks — also registers the Effect plugin and enables its five rules. From then on, a lint run on owned source is the observable product: violating patterns fail the lint; allowed patterns do not.

This document specifies **user- and integrator-observable behavior only**. Exact published symbol names, import paths, and call spellings belong in the Interface Contract, not here. Every feature point below corresponds to behavior that exists in the finished lint-policy product. Feature points are ordered so foundational capabilities come first; a later feature point may refine an earlier one only when it says so explicitly.

## Terminology

| Term | Meaning in this PRD |
| --- | --- |
| **lint-policy** | The product: the generic Oxlint plugin, the opt-in Effect plugin, and the bundled skill that copies them into a consuming repository. |
| **Generic plugin** | The always-applicable plugin. Its published plugin name is lint-policy. It ships the eighteen generic rules listed in FP-01. |
| **Effect plugin** | The opt-in plugin. Its published plugin name is lint-policy-effect. It ships the five Effect rules listed in FP-07. It is not inherited merely because the generic plugin is registered. |
| **Host linter** | Oxlint, including the same plugin fields under lint in a Vite+ configuration. The plugins are JavaScript plugins the host loads by name and specifier. |
| **Rule** | One independently enableable check. A consuming configuration turns it on or off (and, for two generic rules, may pass options). When the rule is off, it reports nothing. |
| **Diagnostic** | A host-linter finding that identifies the offending construct and names the lint-policy or lint-policy-effect rule that fired. Its reported position starts within the construct the rule reports, not on a neighboring allowed construct; where a feature point names a narrower position, that position holds. The wording of the finding is the implementer’s choice. |
| **Enabled at error** | The rule is on at error severity. A diagnostic from that rule makes the lint invocation fail. |
| **Known array** | A receiver the generic plugin can treat as an array from **same-file** evidence: an array literal; a parameter or binding that is never reassigned after its declaration and whose own type annotation is written directly as an array or tuple type (array or tuple syntax, optionally `readonly`, or the global `Array` / `ReadonlyArray` generic, not a type alias of one), whatever its declaration keyword; an unannotated, never-reassigned `const` binding whose initializer is a known array; or the result of calling `map`, `filter`, `flatMap`, `slice`, `concat`, `toSorted`, `toReversed`, or `toSpliced` on a known array. Nothing else is a known array. |
| **Same-file analysis** | Alias, annotation, and binding evidence that appears in the file under lint. The product does not consult a TypeScript type checker, imported type definitions, or cross-file call signatures. |
| **Transparent generic alias** | A same-file generic type alias whose body is exactly its type parameter (an identity wrapper). Applying it to a forbidden type is the same as writing that type. |
| **Vendored copy** | The plugin files as they exist inside a consuming repository after copy. That repository owns subsequent edits. |
| **Skill copy** | The bundled install-lint-policy copy entry: it places a pristine plugin tree at a relative destination and does not fetch, merge, or configure. |

## Public surface inventory

lint-policy is a **pair of Oxlint JavaScript plugins** plus a **copy entry** that vendors them. There is no end-user command of lint-policy’s own, no network service, and no official registry package.

The public surfaces are:

- Copying the plugin tree into a consuming repository (default destination `tools/oxlint/lint-policy`), including refusal to proceed against an existing destination unless `--force` is passed (FP-01).
- Registering the generic plugin with the host linter and enabling any subset of its eighteen rules (FP-01). Linting TypeScript or JavaScript source then applies the rules of FP-02 through FP-06.
- Registering the Effect plugin independently and enabling any subset of its five rules (FP-07).
- Two rule-level options: whether runtime `typeof` is allowed inside type predicates and assertion functions (default off), and which safety-comment markers count as justification for a non-const type assertion (default the single marker `SAFETY`) (FP-03, FP-05).
- Autofix for missing readable spacing only (FP-06). No other generic or Effect rule offers a fix.

Feature points below group these entries by capability. They do not invent additional product surfaces.

The bundled skill also instructs a host coding agent how to merge the plugin into lint configuration, pin a matching Oxlint and plugins-host version pair, enable rules, optionally enable Effect rules when Effect is a direct dependency, validate, and later update a vendored copy while preserving local customizations. Those agent procedures are instructions for a human or coding agent, not an executable merge engine shipped by this product. They are not feature points below. The copy entry, the two plugins, and the rule diagnostics are the product.

## Non-functional constraints

- **Form factor:** TypeScript source consumed by Oxlint as JavaScript plugins. No compiled native extension, no bundled binary, no GPU or accelerator, and no runtime network client.
- **Language floor:** Node.js 24 and pnpm 10.33.0 (the package manager the repository declares) are sufficient to install from this repository and lint source with its rules. The plugins lint TypeScript and JavaScript.
- **Platforms:** Linux, macOS, and Windows. Linux with a supported Node.js interpreter is required.
- **Hardware:** CPU-only. The plugins run on a real host that loads them into Oxlint and lints source. There is no accelerator profile.
- **Distribution:** Vendored source, not a versioned registry dependency of lint-policy itself. A consuming repository that already uses Oxlint installs the Oxlint plugins-host package at **exactly** the resolved Oxlint version; otherwise it installs the same current version of both. Those versions stay exact so upgrades move together. That pairing is install guidance for the host; it is not a lint-policy rule.
- **Analysis:** Same-file evidence only, as defined above. A construct that is only known to be an array, an `unknown` alias, or an Effect tagged type because of another file must not be treated as if that fact were local.
- **Determinism:** The same source, with the same rules enabled and the same options, produces the same diagnostics. There is no model and no random component.
- **Opinionated scope:** lint-policy is not a general-purpose formatter, type checker, or Effect type verifier. Spacing autofix inserts blank lines only; it does not add braces, wrap expressions, sort imports, or infer every logical group.

## Non-goals

- Shipping an official npm package or treating the vendored tree as a locked third-party dependency.
- Inferring imported types, cross-file signatures, or running the TypeScript type checker.
- Autofixing semantic rewrites (array pipelines, reducer copies, conditional spreads, assertions, Effect tags). Only readable spacing inserts whitespace.
- Enabling the Effect plugin merely because Effect appears transitively in a lockfile. Direct manifest dependency or an explicit request is the install-skill policy; the Effect surface is the plugin when it is registered (FP-07).
- Implementing Oxlint’s native accumulating-spread check. The documentation pairs that native check with lint-policy’s reducer-copy rule; the native check is not a lint-policy rule, and lint-policy does not provide it.
- Broadly ignoring every dot-directory in the consuming project. Recommended ignores cover known agent-tooling directories and the vendored plugin path; they are configuration advice, not plugin diagnostics.
- Fetching or three-way-merging updates inside the copy entry. The copy only copies; update merge is an agent procedure.
- Guaranteeing that every quadratic reducer, every possible tagged value, or every Effect import alias is caught. Patterns the feature points below leave outside a rule are not reported by it.

---

## Feature points

### FP-01: Vendor and register the generic lint-policy plugin

**Public entry:** The skill copy (invoked from a consuming repository, optionally with a relative destination and optional `--force`), or a manual copy of the plugin tree. After copy, the host-linter configuration registers a JavaScript plugin whose published name is lint-policy and whose specifier points at the generic plugin entry in the copied tree, then enables any subset of the eighteen generic rules. This feature point is **getting the generic plugin into the host and making its catalog reachable**. Individual rule diagnostics are FP-02 through FP-06. The Effect plugin is FP-07.

**Normal behavior:**

- With no destination argument, the skill copy places the plugin tree at `tools/oxlint/lint-policy` relative to the current working directory. A destination argument uses that relative path instead; the copy then writes only there and does not also create the default destination. After a successful copy, the destination contains both the generic plugin entry and a nested Effect plugin entry, along with the vendored stylistic license and provenance files that travel with readable-spacing enforcement. No third-party stylistic plugin dependency is required.
- The product tree’s own generic plugin directory, copied by hand on its own to another directory, is a complete generic plugin: its entry loads as lint-policy and publishes the same eighteen rules, provided the host plugins package resolves from the copy’s location.
- A successful copy reports that the plugin was copied to the destination and names the generic entry to configure. It creates, changes, or deletes files only under the destination: it does not edit the consuming repository’s lint configuration or manifest, does not install packages (no `node_modules`), and does not fetch a remote revision or need network access.
- Once registered, the generic plugin publishes exactly these eighteen rules, each independently enableable under the lint-policy plugin name: `no-array-filter-map`, `no-reduce-accumulator-copy`, `no-chained-type-assertions`, `no-conditional-empty-object-spread`, `no-known-value-widening`, `no-module-mocking`, `no-object-parameters`, `no-reflect-apply`, `no-reflect-get`, `no-runtime-typeof`, `no-shape-in-symbol-names`, `no-unknown-parameters`, `no-unknown-returns`, `no-unknown-type-aliases`, `no-unsafe-dictionary-type`, `no-widen-then-assert`, `require-readable-spacing`, `require-safety-comment-for-type-assertion`.
- The generic plugin does **not** publish the five Effect rules. Those exist only on lint-policy-effect (FP-07).
- Enabling a generic rule at error severity makes source holding a construct that a later feature point says the rule reports fail lint with a diagnostic of that rule. Leaving that rule off (or not registering the plugin) makes the same source produce **no** lint-policy diagnostic from that rule.
- Each rule reports only the constructs it owns. Enabling further generic rules, up to all eighteen, on source that violates only one rule still yields findings from that rule alone.
- Same-file analysis applies to every generic rule that consults types, aliases, or bindings: block-scoped aliases, forward references in the same file, and transparent generic aliases are resolved; imported type definitions and cross-file signatures are not. Where a later feature point says a rule considers a type only as written (a keyword written as that keyword), a same-file alias in that position is not resolved into it.

**Boundary / error behavior:**

- If the destination already exists and `--force` is not passed, the copy refuses to overwrite, exits unsuccessfully, and leaves every file of the existing tree byte-for-byte unchanged. The error identifies the destination. `--force` is the only way this copy proceeds against an occupied destination: it overwrites source-overlapping plugin paths so the destination then contains the copied generic plugin entry and the nested Effect plugin entry, both loadable. Whether files already in the destination that are not part of the copy are kept or removed is the implementer’s choice. Updating a live vendored installation is an agent procedure, not this copy.
- An unpublished lint-policy rule name listed in host configuration together with a known enabled rule is a host-configuration concern, not a lint-policy diagnostic. The plugin publishes no rule under that name and reports no finding under it; how the host treats an unknown rule name is the host’s behaviour. The plugin does not invent extra rules beyond the eighteen.
- Registering the generic plugin does not enable any rule by itself. A configuration that lists the plugin but enables no lint-policy rules reports no lint-policy diagnostics.
- Source the host cannot parse is a host failure, not a lint-policy diagnostic. lint-policy does not claim to recover from broken syntax.

---

### FP-02: Reject eager array pipelines, reducer copies, and conditional empty spreads

**Public entry:** With the generic plugin registered (FP-01), enable `no-array-filter-map`, `no-reduce-accumulator-copy`, and `no-conditional-empty-object-spread` at error severity and lint TypeScript or JavaScript source. This feature point is those three collection-construction checks. None of them offers autofix.

**Normal behavior:**

- `no-array-filter-map` reports each adjacent pair of eager calls in one call chain that is `filter` then `map`, or `map` then `filter`, when the receiver of the pair is a **known array** (Terminology). Syntax-only wrappers in the chain (parentheses, optional chaining, non-null and type assertions) do not break it, each method may be named by an identifier or by a computed string literal, and in a longer chain every such adjacent pair is its own diagnostic.
- The same rule reports nothing else. Whether a receiver is a known array is decided only by that definition: a binding counts only while it is never reassigned; with its own annotation it counts exactly when that annotation is directly an array or tuple type, whether it is declared with `const`, `let`, or `var` or is a parameter; without an annotation only a `const` initialized with a known array counts. A value is not guessed to be an array from how it is used, from the names of its methods, or from types defined outside the file. Calls that are not an adjacent `filter`/`map` pair in one chain, and method names computed from anything other than a string literal, are not reported.
- `no-reduce-accumulator-copy` reports on an inline `reduce` or `reduceRight` callback (the method named by an identifier or a computed string literal; the accumulator is the callback’s first parameter, with or without a default value) when the callback copies accumulated state by: global `Object.assign` with an object-literal target and the accumulator as a source; global `Array.from` of the accumulator; or, when the initial value is a known array, accumulator calls to `concat`, `slice`, `toSpliced`, `toSorted`, `toReversed`, or `with`.
- The same rule reports only such a copy, and only when it is made directly in the inline callback’s own body (not in a function nested inside it, and not in a callback declared elsewhere and passed by name), of the callback’s accumulator binding itself or of a never-reassigned `const` alias of it, through the global `Object.assign` or `Array.from` reached by those names (not through an alias of them, and not when `Object` or `Array` is shadowed), or through the array methods above. Nothing else in a reducer is reported by it; in particular array and object **spreads** inside the reducer are owned by Oxlint’s native accumulating-spread check, not this rule.
- `no-conditional-empty-object-spread` reports an object spread whose operand is a conditional whose true branch or false branch is an empty object literal (used to omit a field).

**Boundary / error behavior:**

- None of these three rules rewrites the source under the host’s fix mode. A configuration that requests fix still leaves the violating construct in place and still reports it.
- Reducer method names are syntactic. The rule does not prove the receiver is a runtime array; it also does not claim every quadratic reduction is absent.

---

### FP-03: Keep type evidence; justify remaining assertions

**Public entry:** With the generic plugin registered (FP-01), enable `no-chained-type-assertions`, `no-known-value-widening`, `no-widen-then-assert`, and `require-safety-comment-for-type-assertion` at error severity and lint TypeScript source. The safety-comment rule accepts an optional list of marker strings; when omitted, the sole marker is `SAFETY`. This feature point is type-evidence discipline. Same-file analysis (FP-01) applies.

**Normal behavior:**

- `no-chained-type-assertions` reports a chain of type assertions (defined below) that contains a non-const assertion. A single assertion is allowed.
- `no-known-value-widening` reports a **known** value flowing into a broad **target** through one of five vehicles (a variable annotation, an assignment, a return annotation, a class field initializer, or an assertion), and a known argument passed to a local type predicate whose parameter is such a target. Known values and targets are defined in the details below.
- `no-widen-then-assert` reports an immutable local `const` that first stores a known value under the keyword `unknown`, `any`, or `object`, and later asserts that same binding to a narrower type in the same function (or at top level). A store annotated with a same-file alias of `unknown` or `object` instead of the keyword is not this store; that store still widens under `no-known-value-widening`. A broad record here is a written annotation that is the language dictionary utility `Record`, with key type argument `string` and value type argument `unknown` or `any`: storing a known value under that annotation and later asserting the same binding to a narrower type with named fields, in the same function or at top level, reports this rule, and the same store with no later narrower assertion does not. A dictionary whose value type is a named type is not this store, even though it is an open-dictionary target of `no-known-value-widening`. Widening without a later narrower assertion is allowed. Asserting a binding that was already `unknown` at the boundary (never a known value in this file) is allowed.
- `require-safety-comment-for-type-assertion` reports every non-const `as` or angle-bracket assertion, whatever expression or declaration contains it, that lacks a justification placed before it. A justification is a `//` or `/* */` comment whose text contains a configured marker followed by a colon and then at least one non-whitespace character; its wording and length are free. It counts in exactly these positions: on the line immediately above the assertion’s owning statement, or immediately above an `export` of that statement, with at most one blank line between the comment and the statement; or as an inline `/* */` comment placed directly in front of the assertion itself, before the assertion’s first token. A comment anywhere else (after the assertion, later in or after its statement, or before a different statement) does not count. `as const` and angle-bracket `const` assertions need no justification.
- A supplied markers list names one or more markers, and only those markers count. Multiple markers are alternatives: any one of them with a non-empty justification is enough. An omitted list is treated as the default: the single marker `SAFETY`. A configured marker is matched literally and as a whole: none of its characters has a special meaning, a part of it is not the marker, it is not preceded directly by a letter, digit, or underscore, and it is followed directly by its colon or by whitespace and then the colon. It may appear anywhere in the comment.
- `no-chained-type-assertions` details: a chain is two or more assertions (`as`, angle-bracket, or a mix) applied in turn to one expression; parentheses around a link do not break it. A chain reports when at least one of its assertions is not a const assertion, wherever it sits and whatever the asserted types; a justification comment does not silence it. A chain made only of const assertions stays silent, with or without a comment, and is also exempt from `require-safety-comment-for-type-assertion`. Being nested does not by itself make an assertion a `no-known-value-widening` or `no-widen-then-assert` finding; each non-const assertion in a chain is still subject to `require-safety-comment-for-type-assertion`.
- `no-known-value-widening` details: on the five non-predicate vehicles the known values are an object literal with at least one concrete key, a numeric literal, an array literal (including an empty one), and a `const` local that has no type annotation of its own and whose initializer is one of those literals; a `let` or `var` alias is never a known value. The targets are the keyword `unknown`, the keyword `object`, an inline object type with at least one member, and an open dictionary: `Record` whose key is `string` or a same-file alias of `string` (program or block scope), whatever its value type. An object type is a target only when its members are written in place as the type itself: a named interface, or a same-file alias whose body is an object type, is not a target, even when it declares the same members. The keyword `any` and a `Record` whose key is a finite union of string-literal types (written inline or through an alias) are not targets; whether an index-signature type literal is a target is the implementer’s choice. A local type predicate’s parameter is a target when written as the keyword `unknown` or as a union of that keyword with another type, in either order; the known arguments there are a string literal and a local whose only same-file evidence is a precise annotation without a literal initializer. An argument that is already `unknown` (a binding declared `unknown`, or the result of calling a function declared to return `unknown`) is not known. Any value, target, or position outside these definitions stays silent.
- `no-widen-then-assert` details: the later assertion is an `as` assertion of the same `const` binding. Store and assertion sit at top level, or in the same function, where the assertion may be anywhere later in that function’s body (nested blocks included) but not inside a nested function. The known values are those of `no-known-value-widening`. The asserted type is narrower when it is not itself broad (not `unknown`, `any`, `object`, or a broad record): after a store under `unknown` or `any`, every such type is narrower; after a store under `object`, it must be an object, array, tuple, or function type; after a store under a broad record, it must be an object type with at least one named member, or a `Record` whose value type is neither `unknown` nor `any`. A store under `unknown`, `object`, or `Record<string, unknown>` also reports `no-known-value-widening`; a store under `any` reports only this rule; a store under `Record<string, any>` reports this rule; whether it also reports `no-known-value-widening` is the implementer’s choice.

**Boundary / error behavior:**

- These rules do not offer autofix.
- Same-file non-generic aliases, including block-scoped aliases, that resolve to `unknown`, `object`, or an open dictionary are treated as those targets on the five non-predicate widening vehicles. They are not resolved into the keyword in the two keyword-only positions above: a type-predicate parameter of `no-known-value-widening`, and the store annotation of `no-widen-then-assert`. A same-file transparent generic identity application is treated as a widening target when it resolves to an open dictionary; whether applying it to `unknown` or `object` makes those targets is the implementer’s choice. Names not defined in the file are not.
- The safety-comment rule does not judge the **truth** of the justification, only that a configured marker and a non-empty justification are present before the assertion.

---

### FP-04: Reject unknown, object, and unsafe dictionary contracts

**Public entry:** With the generic plugin registered (FP-01), enable `no-object-parameters`, `no-unknown-parameters`, `no-unknown-returns`, `no-unknown-type-aliases`, and `no-unsafe-dictionary-type` at error severity and lint TypeScript source. This feature point is **explicit contracts** that erase structure. Same-file analysis (FP-01) applies. None of these rules offers autofix.

**Normal behavior:**

- `no-object-parameters` reports a function, method, or function-type contract parameter, defaulted or destructured included, whose same-file type is `object`, a union containing `object`, or a scoped or transparent generic alias that resolves to `object`. A generic type **parameter** is not `object`, whatever its constraint, and it shadows a same-file alias of the same name.
- `no-unknown-parameters` reports a parameter whose **written** type is `unknown` or a union containing `unknown`, except: a parameter literally named `cause` whose type is `unknown` or a union containing `unknown`; and the **exact subject** of a type predicate or assertion function (`value is T` or `asserts value is T`), in any function form. Additional `unknown` parameters on the same function are still reported. A same-file alias of `unknown`, or a transparent generic application of `unknown`, used as a parameter is not this rule’s concern.
- `no-unknown-returns` reports an **explicit** return type of a function, arrow, declared-function, method, or function-type contract whose same-file resolved type is `unknown`, `Promise<unknown>`, or `PromiseLike<unknown>`, including unions containing `unknown` and scoped or transparent generic aliases that resolve to those. Inferred returns (no annotation) are allowed. A return of the function’s own type parameter is that parameter, even if a same-file alias of the same name is `unknown`. A return type name that is not defined in the same file is not treated as `unknown`.
- `no-unknown-type-aliases` reports a same-file type alias whose resolved type is `unknown`, directly, as a member of a union, or through a transparent generic alias. An alias of a structured type that merely contains `unknown` (as a member, or as a type argument of a wrapper that is not transparent) is allowed.
- `no-unsafe-dictionary-type` reports a dictionary whose **value** type is unsafe, written as `Record`, an index signature, a mapped dictionary, or a `Readonly`/`Partial`/`Required`/`Pick`/`Omit` application to such a dictionary. A value type is unsafe when, after resolving same-file aliases, it is `unknown`, `any`, `object`, `{}`, an empty interface, a brand-only empty type, or a union or a `NonNullable` or `Readonly` application that still resolves to one of those. A brand-only empty type is an object type, a same-file interface (one declaration, extending nothing), or a same-file alias of such an object type, that has at least one member and whose every member is an optional property of type `never`, with or without `readonly`, whatever the property names. A type that also has any other member is an ordinary data type and is allowed as a dictionary value. A same-file alias of an unsafe dictionary is reported where that dictionary is written; whether a plain later use of the alias (such as a variable annotation) is reported again is the implementer’s choice. A `Readonly`, `Partial`, `Required`, `Pick`, or `Omit` application to an unsafe dictionary is itself reported, whether the dictionary is written as its argument or is a same-file alias of an unsafe dictionary, and also when those wrappers are nested: a diagnostic of this rule starts at the name of the outermost such wrapper. Whether a further finding also appears on the inner dictionary, an inner wrapper, or the alias is the implementer’s choice; the finding at the outermost wrapper name is always present. `Pick` and `Omit` of an unsafe dictionary are such wrappers whatever their key argument, and a wrapper of a dictionary whose value is a brand-only empty type is one too. A value type that is a named or structured data type is allowed, even when its own members are `unknown`. Only the language dictionary utility is `Record` (a `Record` defined in or imported into the file is not), and a dictionary used as a generic type-parameter constraint (on a function, class, or type alias) is not a value contract and is allowed.

**Boundary / error behavior:**

- Where these rules resolve aliases or wrappers, they do so only in the same file, including inner functions that declare an alias used by a nested function, and forward references. A later inner alias does not leak into an outer function that never declared it. `no-unknown-parameters` does not resolve aliases.
- An unsafe dictionary is diagnosed where it is written (for a wrapped dictionary, at the outermost wrapper name), and every wrapper application above is diagnosed at the outermost wrapper name, including when the wrapped dictionary is a same-file alias; reporting plain later uses of an alias again is the implementer’s choice.
- These rules do not rewrite source under fix mode.

---

### FP-05: Reject runtime typeof, Reflect apply/get, and module mocking

**Public entry:** With the generic plugin registered (FP-01), enable `no-runtime-typeof`, `no-reflect-apply`, `no-reflect-get`, and `no-module-mocking` at error severity and lint TypeScript or JavaScript source. `no-runtime-typeof` accepts an optional `allowInTypeGuards` flag; when omitted or false, the flag is off. This feature point is **runtime and test seams**. None of these rules offers autofix.

**Normal behavior:**

- `no-runtime-typeof` reports a `typeof` check that is not an **existence probe**. An existence probe compares `typeof` to the string `"undefined"` (either operand order, with `===`, `!==`, `==`, or `!=`). Every other `typeof` check is reported.
- When `allowInTypeGuards` is true, a `typeof` check that sits **directly** in a type predicate or assertion function (the function’s return type is `value is T` or `asserts value is T`) is allowed. Nested inner functions inside that predicate still report. Ordinary functions that are not predicates still report, even with the flag on. When the flag is false or absent, predicates report like any other function.
- `no-reflect-apply` reports a call of `apply` (named by an identifier or a computed string literal) on the global `Reflect`. A same-file binding named `Reflect`, of any kind, shadows the global.
- `no-reflect-get` reports a call of `get` (named by an identifier or a computed string literal) on the global `Reflect`, with the same shadowing rule.
- `no-module-mocking` reports a call of `mock`, `doMock`, or `unstable_mockModule` (named by an identifier or a computed string literal) on the real Vitest or Jest testing namespace: the global `vi` or `jest`, or a binding imported by name as `vi` from the `vitest` module or as `jest` from `@jest/globals`, whatever its local name. A same-named binding that is not one of those (a local object, a parameter, or an import from any other module) is not the testing namespace, and other methods of the namespace, including `spyOn`, are not reported.

**Boundary / error behavior:**

- These rules do not consult a type checker to prove that `Reflect` is the language global beyond same-file shadowing. A file that does not shadow `Reflect` treats `Reflect.apply` / `Reflect.get` as the global.
- `allowInTypeGuards` defaults to **false**: a configuration that omits the option behaves as false.
- Module mocking does not report `spyOn` and does not report non-mock APIs on the same namespaces.

---

### FP-06: Ban shape in locally owned names; require readable spacing

**Public entry:** With the generic plugin registered (FP-01), enable `no-shape-in-symbol-names` and `require-readable-spacing` at error severity and lint TypeScript or JavaScript source. Readable spacing is the only generic rule that autofixes. It takes **no** options; local taste is expressed by editing the vendored rule. This feature point is naming and whitespace.

**Normal behavior:**

- `no-shape-in-symbol-names` reports the case-insensitive substring `shape` in **locally owned** names: variable bindings, functions, classes, interfaces, type aliases, locally declared property names, private names, and JSX names (including properties declared on a local type, and a local binding’s name where it is used as a computed key). A member name read through property access on a value, at any depth of the access chain, is allowed, including on a local binding and on assignment, because that member name belongs to the value’s owner and cannot be renamed locally.
- `require-readable-spacing` reports missing blank lines in these situations, and under the host’s fix mode **inserts** those blank lines without otherwise rewriting the file. Where a blank line is missing, the fix inserts exactly one:
  - between any two adjacent top-level non-import statements, whatever their kinds (declarations, exported or not, and other statements);
  - after imports before the first non-import;
  - before `return`, `if`, `switch`, `try`, `for`, `while`, and `do` when they follow other statements in a block;
  - after a block-like statement before the next statement;
  - around multiline `const`, `let`, `var`, and `using` bindings;
  - around a nested `function`, `class`, `interface`, or `type` declaration and its neighboring statements.
- The same spacing rule **preserves**: adjacent import lines with no required blank line between them; adjacent short variable declarations inside a function (two one-line `const` bindings stay grouped); adjacent function overload signatures together with their implementation; documentation comments attached to the following declaration (the inserted blank line goes **before** that documentation, not between the documentation and the declaration); existing extra blank lines (the rule never removes blank lines). A compact function body written on one line that holds a single statement stays on one line; a one-line body with more than one statement still receives the blank lines above. Adjacent `switch` case clauses with no blank line between them stay compact.
- A lint run with only this rule enabled fails on a file that is missing a required blank line and succeeds on the same file after one fix pass. After a successful fix pass, a second lint or fix pass on the same files reports no spacing diagnostics and does not change the files further. The rule inserts whitespace only: it does not add braces, wrap expressions, sort imports, or enable a competing formatting preset.

**Boundary / error behavior:**

- `no-shape-in-symbol-names` does not offer autofix (renaming is a semantic choice).
- `require-readable-spacing` does not delete blank lines even when a team would prefer denser code.
- Host formatters may run after this fix; this rule does not claim to own indentation or wrapping.

---

### FP-07: Opt-in lint-policy-effect plugin

**Public entry:** Register a second JavaScript plugin whose published name is lint-policy-effect and whose specifier points at the Effect plugin entry (nested under the vendored tree’s `effect` entry). Enable any subset of its five rules at error severity and lint TypeScript or JavaScript source. This feature point is **Effect architecture policy**. It does not load unless this second plugin is registered (FP-01’s generic plugin alone is not enough). None of these rules offers autofix.

The five rules are exactly: `no-manual-effect-error-tag`, `no-manual-tag-comparison`, `no-manual-tagged-construction`, `no-service-constructor-imports`, `prefer-effect-match`.

**Normal behavior:**

- These checks are identifier-exact for Effect and Match. They recognize `Effect.catch`, `Effect.catchAll`, and `Effect.catchIf`, and `Match.when` / `Match.not`, when those names are written as such. They do not resolve import aliases of Effect or Match and do not prove that a similarly named object came from Effect.
- `no-manual-tag-comparison` reports a direct equality or inequality comparison (`==`, `===`, `!=`, `!==`, either operand order) of a `_tag` member (named directly or by computed `"_tag"`) against a string literal (a template literal is not one), and a `switch` whose discriminant is such a `_tag` member. `_tag` comparisons **inside** a broad Effect catch handler belong to the next rule, not this one.
- `no-manual-effect-error-tag` reports `_tag` comparisons against a string literal and `_tag` switches **in** an inline handler function passed as an argument of `Effect.catch`, `Effect.catchAll`, or `Effect.catchIf`. This covers a `_tag` read from the caught value itself and a `_tag` read through a member named `reason` (written as `.reason` or as computed `"reason"`); the finding’s message wording for each is the implementer’s choice. The finding identifies that comparison or switch, not the `Effect.catch…` call or the handler function around it. Whether a `_tag` comparison in a function nested inside that handler is reported by this rule is the implementer’s choice.
- `no-manual-tagged-construction` reports an object literal that assigns a **string literal** to `_tag` (named directly or by computed `"_tag"`). An object literal passed directly as a pattern to `Match.when` or `Match.not` is not such a construction.
- `prefer-effect-match` reports a chained ternary whose tests are equality or inequality comparisons (`==`, `===`, `!=`, `!==`) of **the same value** (the compared expressions match as written) against literals (including literal templates with no interpolations), in either operand order, when the false branch is another such ternary of that same value. The rule does not infer types or prove exhaustiveness.
- `no-service-constructor-imports` reports a **named** import whose imported name matches `make` immediately followed by an uppercase letter, when the module specifier is project-relative (`./` or `../`) and the file under lint is **not** a test or spec file. The finding identifies the offending imported name (its named import specifier), not the whole import declaration or its module specifier. Test or spec files are those whose path matches a `.test.` or `.spec.` suffix with a JavaScript or TypeScript (optionally JSX) extension, including the `c`/`m` module variants.

**Boundary / error behavior:**

- Registering only the generic plugin, or registering lint-policy-effect but enabling none of its rules, produces no lint-policy-effect diagnostics even on source that would violate them.
- Such relative imports in application files are reported; the rule does not rewrite them to Layer imports (no autofix).
- Package-alias imports of `make…` constructors are a documented limitation: they are not reported.
- Identifier spelling decides: `Effect.catch` written as such is a catch handler; a renamed binding is not.

