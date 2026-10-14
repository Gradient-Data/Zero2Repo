# feature: F01
"""Observation helpers for vendoring and registering the generic plugin.

Import side effects: none. Process spawn and filesystem writes happen only
when a caller invokes a function below.
"""

from __future__ import annotations

import re
import secrets
import shutil
import socket
from pathlib import Path
from typing import Mapping, Sequence

from _harness import (
    EFFECT_PLUGIN_NAME,
    GENERIC_PLUGIN_NAME,
    HarnessError,
    RunResult,
    Workspace,
    diagnostics,
    effect_plugin,
    generic_plugin,
    generic_plugin_path,
    list_files,
    node_modules_path,
    rule_key,
    snapshot_files,
)

GENERIC_RULE_NAMES: tuple[str, ...] = (
    "no-array-filter-map",
    "no-reduce-accumulator-copy",
    "no-chained-type-assertions",
    "no-conditional-empty-object-spread",
    "no-known-value-widening",
    "no-module-mocking",
    "no-object-parameters",
    "no-reflect-apply",
    "no-reflect-get",
    "no-runtime-typeof",
    "no-shape-in-symbol-names",
    "no-unknown-parameters",
    "no-unknown-returns",
    "no-unknown-type-aliases",
    "no-unsafe-dictionary-type",
    "no-widen-then-assert",
    "require-readable-spacing",
    "require-safety-comment-for-type-assertion",
)

EFFECT_RULE_NAMES: tuple[str, ...] = (
    "no-manual-effect-error-tag",
    "no-manual-tag-comparison",
    "no-manual-tagged-construction",
    "no-service-constructor-imports",
    "prefer-effect-match",
)

_JS_RULES = frozenset(
    {
        "no-array-filter-map",
        "no-reduce-accumulator-copy",
        "no-conditional-empty-object-spread",
        "no-module-mocking",
        "no-reflect-apply",
        "no-reflect-get",
        "no-runtime-typeof",
        "no-shape-in-symbol-names",
        "require-readable-spacing",
    }
)

# Stated copy-report forms (Interface Contract, "Copy entry outputs").
COPY_EXIT_REFUSED = 1
# A printed path is one whitespace-free word, optionally followed directly by
# one of these punctuation marks (Interface Contract, "Copy entry outputs").
_PATH_WORD_TRAILERS = ".,;:"
# Copied layout (Interface Contract, "Naming conventions", Entries): both
# entries sit at these paths relative to the destination directory.
COPIED_GENERIC_REL = Path("index.ts")
COPIED_EFFECT_REL = Path("effect") / "index.ts"
# License and provenance files: exact basenames, at any depth under dest.
LICENSE_BASENAME = "LICENSE"
PROVENANCE_BASENAME = "UPSTREAM.md"
_PLUGIN_WRAP = re.compile(r"(lint-policy|lint-policy-effect)\(([^()\s]+)\)")
_PLUGIN_SUFFIXES = {".ts", ".js", ".mjs", ".cjs", ".mts", ".cts"}
_SAFETY_COMMENT = "// SAFETY: parsed before branding."


def published_rule_id(rule: str) -> str:
    """Read a host finding code ``<plugin>(<rule>)`` as ``<plugin>/<rule>``.

    The Interface Contract states that a plugin finding's ``code`` in the
    host's JSON report is exactly ``<plugin>(<rule>)``. Any other code (a
    host parse failure has none) is returned unchanged, so it never reads
    as a ``<plugin>/<rule>`` id.
    """
    matched = _PLUGIN_WRAP.fullmatch(rule)
    if not matched:
        return rule
    return f"{matched.group(1)}/{matched.group(2)}"


def fresh_ident(prefix: str = "id") -> str:
    """Return a runtime identifier that does not contain ``shape``."""
    while True:
        name = f"{prefix}{secrets.token_hex(4)}"
        if name.isidentifier() and "shape" not in name.lower():
            return name


def snippet_extension(rule_name: str) -> str:
    return "js" if rule_name in _JS_RULES else "ts"


def next_generic_rule(rule_name: str) -> str:
    index = GENERIC_RULE_NAMES.index(rule_name)
    return GENERIC_RULE_NAMES[(index + 1) % len(GENERIC_RULE_NAMES)]


def _dest_on_disk(dest: str | Path, cwd: str | Path | None = None) -> Path:
    """Locate dest from the path the suite passed."""
    dest_path = Path(dest)
    if dest_path.is_absolute():
        return dest_path.resolve()
    if cwd is not None:
        return (Path(cwd) / dest_path).resolve()
    return dest_path.resolve()


def _reported_path(text: str, cwd: str | Path | None) -> Path:
    """A path the copy report printed: absolute, or relative to the copy cwd."""
    path = Path(text)
    if not path.is_absolute():
        base = Path(cwd) if cwd is not None else Path.cwd()
        path = base / path
    return path.resolve()


def _path_word(word: str) -> str:
    """A printed path word without one trailing stated punctuation mark."""
    if len(word) > 1 and word[-1] in _PATH_WORD_TRAILERS:
        return word[:-1]
    return word


def _names_path(text: str, target: Path, cwd: str | Path | None) -> bool:
    """True when some whitespace-free word of ``text`` is a path to ``target``."""
    for word in text.split():
        candidate = _path_word(word)
        if not candidate:
            continue
        try:
            if _reported_path(candidate, cwd) == target:
                return True
        except (OSError, ValueError):
            continue
    return False


def reported_generic_specifier(
    result: RunResult,
    dest: str | Path,
    cwd: str | Path | None = None,
) -> str:
    """Read the success report on standard output.

    The Interface Contract states that standard output names the
    destination directory and the generic entry ``<dest>/index.ts``, each as
    a whitespace-free path word (absolute or relative to the copy's working
    directory, optionally followed by one of ``.,;:``). Returns the entry.

    Raises:
        HarnessError: if stdout cannot be decoded.
        AssertionError: if the destination or the generic entry is not named.
    """
    dest_path = _dest_on_disk(dest, cwd)
    stdout = result.stdout_text
    if not _names_path(stdout, dest_path, cwd):
        raise AssertionError(
            f"copy success stdout must name the destination {dest_path}; "
            f"stdout={stdout!r}"
        )
    entry = (dest_path / COPIED_GENERIC_REL).resolve()
    if not _names_path(stdout, entry, cwd):
        raise AssertionError(
            f"copy success stdout must name the generic entry {entry}; "
            f"stdout={stdout!r}"
        )
    print(f"reported generic specifier={entry}", flush=True)
    return str(entry)


def copied_generic_entry(dest: str | Path, cwd: str | Path | None = None) -> Path:
    """The generic entry at its stated place: ``<dest>/index.ts``."""
    return _dest_on_disk(dest, cwd) / COPIED_GENERIC_REL


def copied_effect_entry(dest: str | Path, cwd: str | Path | None = None) -> Path:
    """The Effect entry at its stated place: ``<dest>/effect/index.ts``."""
    return _dest_on_disk(dest, cwd) / COPIED_EFFECT_REL


def require_copied_layout(
    result: RunResult,
    dest: str | Path,
    cwd: str | Path | None = None,
) -> str:
    """Assert a successful copy and return the generic entry from the layout.

    Setup for tests whose subject is not the copy report: exit 0, the dest
    directory, and the generic entry at ``<dest>/index.ts``. The report's
    wording is not read here; the copy feature's own tests check it.
    """
    dest_path = _dest_on_disk(dest, cwd)
    print(
        f"copy layout probe exit={result.returncode} dest={dest_path}",
        flush=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            "copy must succeed; "
            f"exit={result.returncode}; stderr={result.stderr_text!r}"
        )
    if not dest_path.is_dir():
        raise AssertionError(f"copy did not create dest directory {dest_path}")
    entry = copied_generic_entry(dest, cwd)
    if not entry.is_file():
        raise AssertionError(f"no generic entry at {entry} (<dest>/index.ts)")
    return str(entry.resolve())


def require_copy_success(
    result: RunResult,
    dest: str | Path,
    cwd: str | Path | None = None,
) -> str:
    """Assert a successful copy, its stated report, and return the entry.

    The success report must name the generic entry at its
    stated place, ``<dest>/index.ts``.
    """
    entry = require_copied_layout(result, dest, cwd)
    specifier = reported_generic_specifier(result, dest, cwd)
    if Path(specifier).resolve() != Path(entry):
        raise AssertionError(
            f"copy report names generic entry {specifier}, not {entry}"
        )
    return entry


def assert_generic_configure_target(
    specifier: str | Path,
    dest: str | Path,
    effect_specifier: str | Path | None = None,
) -> None:
    """Generic configure target is under dest, not dest, not the Effect entry."""
    dest_path = Path(dest).resolve()
    spec_path = Path(specifier).resolve()
    try:
        rel = spec_path.relative_to(dest_path)
    except ValueError as exc:
        raise AssertionError(
            f"generic-entry configure target {spec_path} is not under dest "
            f"{dest_path}"
        ) from exc
    if rel.as_posix() in ("", "."):
        raise AssertionError(
            "generic-entry configure target must be more specific than dest"
        )
    if effect_specifier is None:
        return
    effect_path = Path(effect_specifier).resolve()
    if spec_path == effect_path:
        raise AssertionError(
            "generic-entry configure target must not be the nested Effect entry"
        )


def require_copy_refusal(
    result: RunResult,
    dest: str | Path,
    *,
    before: Mapping[str, bytes],
    cwd: str | Path | None = None,
) -> None:
    """Assert occupied-dest refusal: exit 1, stderr names dest, bytes kept.

    The Interface Contract states the refusal: exit status 1, and standard
    error names the destination directory as a whitespace-free path word
    (absolute or relative to the copy's working directory, optionally
    followed by one of ``.,;:``); the rest of the wording is free.
    """
    dest_path = _dest_on_disk(dest, cwd)
    print(
        f"copy refusal probe exit={result.returncode} dest={dest_path}",
        flush=True,
    )
    if result.returncode != COPY_EXIT_REFUSED:
        raise AssertionError(
            "copy must refuse to overwrite an occupied dest without --force "
            f"with exit status {COPY_EXIT_REFUSED}; "
            f"exit={result.returncode}; stdout={result.stdout_text!r}"
        )
    stderr = result.stderr_text
    if not _names_path(stderr, dest_path, cwd):
        raise AssertionError(
            f"refusal stderr must name the destination {dest_path}; "
            f"stderr={stderr!r}"
        )
    after = snapshot_files(dest_path)
    if dict(after) != dict(before):
        raise AssertionError(
            "occupied dest bytes changed despite refusal without --force"
        )


def require_unpublished_name_host_refusal(
    result: RunResult,
    unpublished_names: Sequence[str],
) -> None:
    """Assert unclassified host output is the unpublished-name host refusal.

    An unpublished lint-policy rule name listed with a known enabled rule is a
    host-configuration concern. The allowed unclassified carrier is a host
    refusal that identifies those unpublished names and the loaded generic
    plugin. Any other non-zero unclassified output is not that carrier.

    Raises:
        HarnessError: if stdout/stderr cannot be decoded.
        AssertionError: if the invocation succeeded, or the report does not
            identify every unpublished name and the loaded generic plugin.
    """
    names = tuple(unpublished_names)
    print(
        f"unpublished-name host refusal exit={result.returncode} names={list(names)}",
        flush=True,
    )
    if result.returncode == 0:
        raise AssertionError(
            "listing unpublished lint-policy rule names must not succeed; "
            f"exit={result.returncode}; stdout={result.stdout_text!r}"
        )
    text = result.combined_text
    missing = [name for name in names if name not in text]
    if missing:
        raise AssertionError(
            "host-configuration refusal must identify the unpublished rule "
            f"names {missing}; report={text!r}"
        )
    if GENERIC_PLUGIN_NAME not in text:
        raise AssertionError(
            "host-configuration refusal must name the loaded plugin "
            f"{GENERIC_PLUGIN_NAME}; report={text!r}"
        )


def occupy_copied_plugin_paths(dest: str | Path, placeholder: str) -> tuple[Path, ...]:
    """Overwrite dest plugin-suffix files with *placeholder*.

    Occupies source-overlapping plugin paths left by a prior copy. The
    paths come from dest on disk, not from a pinned generic-entry
    basename. Destination-only extras that are not plugin-suffix files
    are not touched.
    """
    dest_path = Path(dest).resolve()
    if not dest_path.is_dir():
        raise AssertionError(f"dest is not a directory: {dest_path}")
    occupied: list[Path] = []
    for rel in list_files(dest_path):
        if rel.endswith(".d.ts"):
            continue
        path = dest_path / rel
        if path.suffix.lower() not in _PLUGIN_SUFFIXES:
            continue
        path.write_text(placeholder, encoding="utf-8")
        written = path.read_text(encoding="utf-8")
        if written != placeholder:
            raise AssertionError(
                f"failed to occupy source-overlapping plugin path {path}"
            )
        occupied.append(path)
    if not occupied:
        raise AssertionError(
            "copy left no plugin-suffix files under dest to occupy as "
            "source-overlapping plugin paths"
        )
    print(
        "occupied plugin paths="
        f"{[path.relative_to(dest_path).as_posix() for path in occupied]}",
        flush=True,
    )
    return tuple(occupied)


def assert_occupied_plugin_paths_overwritten(
    occupied: Sequence[str | Path],
    placeholder: str,
) -> None:
    """Source-overlapping plugin paths must not still hold the occupy bytes."""
    leftover: list[str] = []
    missing: list[str] = []
    for raw in occupied:
        path = Path(raw)
        if not path.is_file():
            missing.append(str(path))
            continue
        if path.read_text(encoding="utf-8") == placeholder:
            leftover.append(str(path))
    print(
        f"force-overwrite leftover={leftover} missing={missing}",
        flush=True,
    )
    if leftover:
        raise AssertionError(
            "--force must overwrite source-overlapping plugin paths so dest "
            "contains the copied plugin files; still placeholder: "
            f"{leftover}"
        )
    if missing:
        raise AssertionError(
            "--force must overwrite source-overlapping plugin paths; "
            f"occupied plugin files missing after copy: {missing}"
        )


def _named_files(dest_path: Path, basename: str) -> list[str]:
    return [rel for rel in list_files(dest_path) if Path(rel).name == basename]


def assert_license_and_provenance_material(dest: str | Path) -> None:
    """Dest holds a non-empty ``LICENSE`` and a non-empty ``UPSTREAM.md``.

    The Interface Contract states both basenames exactly; where under dest
    they sit, and their wording, are free.
    """
    dest_path = Path(dest).resolve()
    for role, basename in (
        ("license", LICENSE_BASENAME),
        ("provenance", PROVENANCE_BASENAME),
    ):
        found = _named_files(dest_path, basename)
        print(f"{role} files named {basename}: {found}", flush=True)
        if not found:
            raise AssertionError(
                f"dest contains no {role} file named {basename}"
            )
        if not any((dest_path / rel).read_bytes().strip() for rel in found):
            raise AssertionError(
                f"every {role} file named {basename} under dest is empty: {found}"
            )


def assert_tree_unchanged_outside_dest(
    before: Mapping[str, bytes],
    after: Mapping[str, bytes],
    dest: str | Path,
) -> None:
    """Consuming-tree snapshot minus dest is equal."""
    dest_rel = Path(dest).as_posix().rstrip("/")
    prefix = dest_rel + "/"

    def outside(snapshot: Mapping[str, bytes]) -> dict[str, bytes]:
        return {
            key: value
            for key, value in snapshot.items()
            if key != dest_rel and not key.startswith(prefix)
        }

    before_out = outside(before)
    after_out = outside(after)
    extra = sorted(set(after_out) - set(before_out))
    missing = sorted(set(before_out) - set(after_out))
    changed = sorted(
        key
        for key in before_out
        if key in after_out and before_out[key] != after_out[key]
    )
    print(
        f"outside-dest extra={extra} missing={missing} changed={changed}",
        flush=True,
    )
    if extra or missing or changed:
        raise AssertionError(
            "copy must not create, delete, or edit files outside dest; "
            f"extra={extra} missing={missing} changed={changed}"
        )


def _tree_resolves_host_plugins(tree: Path) -> bool:
    """True when a file under *tree* can resolve the host plugins package."""
    pkg = tree / "node_modules" / "@oxlint" / "plugins"
    try:
        return pkg.is_dir()
    except OSError as exc:
        raise HarnessError(
            f"cannot inspect host plugins package at {pkg}: {exc}"
        ) from exc


def _attach_host_plugin_modules(tree: Path, source: Path) -> None:
    """Expose the host plugins package under *tree* for Node ESM lookup.

    A directory named ``node_modules`` that does not contain the host
    plugins package is not "already attached". Raises HarnessError when
    the path cannot be inspected or the attach cannot be created. Never
    returns a sentinel that would look like the package was present.
    """
    if _tree_resolves_host_plugins(tree):
        return
    dest = tree / "node_modules"
    try:
        dest_exists = dest.exists() or dest.is_symlink()
    except OSError as exc:
        raise HarnessError(
            f"cannot inspect host plugin modules path {dest}: {exc}"
        ) from exc
    if not dest_exists:
        try:
            dest.symlink_to(source, target_is_directory=True)
        except OSError as exc:
            raise HarnessError(
                f"cannot attach host plugin modules {source} -> {dest}: {exc}"
            ) from exc
        print(f"attached host plugin modules {dest} -> {source}", flush=True)
        return
    source_pkg = source / "@oxlint" / "plugins"
    try:
        source_ok = source_pkg.is_dir()
    except OSError as exc:
        raise HarnessError(
            f"cannot inspect host plugins package at {source_pkg}: {exc}"
        ) from exc
    if not source_ok:
        raise HarnessError(
            f"host plugins package is not a directory at {source_pkg}"
        )
    scoped = dest / "@oxlint"
    pkg = scoped / "plugins"
    try:
        scoped.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HarnessError(
            f"cannot create host plugins scope {scoped}: {exc}"
        ) from exc
    try:
        pkg_present = pkg.exists() or pkg.is_symlink()
    except OSError as exc:
        raise HarnessError(
            f"cannot inspect host plugins path {pkg}: {exc}"
        ) from exc
    if pkg_present:
        raise HarnessError(
            f"host plugins path exists but is not a usable package: {pkg}"
        )
    try:
        pkg.symlink_to(source_pkg, target_is_directory=True)
    except OSError as exc:
        raise HarnessError(
            f"cannot attach host plugins package {source_pkg} -> {pkg}: {exc}"
        ) from exc
    print(f"attached host plugins package {pkg} -> {source_pkg}", flush=True)


def _plugin_module_trees(
    ws: Workspace, specifier: str | Path | None = None
) -> tuple[Path, ...]:
    """Package roots from which Node ESM will look up the host plugins package.

    Copied plugins resolve from the consuming cwd. Isolated overlays copy
    product source without host modules and treat that tree as the product
    under test, so this helper does not attach onto the product root. A
    shipped in-tree specifier is made loadable by copying that tree into
    the consuming cwd (see ``materialize_shipped_generic_entry``).
    """
    work = ws.path.resolve()
    trees: list[Path] = [work]
    if specifier is None:
        return tuple(trees)
    spec = Path(specifier).resolve()
    try:
        spec.relative_to(work)
    except ValueError:
        return tuple(trees)
    parent = spec.parent
    if parent != work:
        trees.append(parent)
    return tuple(dict.fromkeys(trees))


def ensure_host_plugin_modules(
    ws: Workspace, specifier: str | Path | None = None
) -> None:
    """Expose the host plugins package where Node ESM will resolve it.

    The PRD assumes a consuming repository already has Oxlint (and its
    plugins-host package). Copy must not install that package. Node ESM
    plugin loads resolve from the importing file, not NODE_PATH.

    A dest under an empty consuming cwd cannot see the host plugins
    package unless those modules are present in that tree. Attach onto
    the consuming cwd (and the specifier's directory when it lives
    there). Do not mutate the product tree.
    """
    source = node_modules_path(root=ws.root)
    if not source.is_dir():
        raise HarnessError(f"host plugins package is not available at {source}")
    for tree in _plugin_module_trees(ws, specifier):
        _attach_host_plugin_modules(tree, source)


def materialize_shipped_generic_entry(ws: Workspace) -> str:
    """Return a specifier for the shipped generic catalog without skill-copy.

    L89 names a manual copy of the plugin tree as a public entry. Isolated
    overlays copy product source without host modules; Node ESM resolves
    the host plugins package from the importing file, so a specifier under
    the product root cannot see modules attached only onto the temp
    workspace. Copy the shipped generic tree (the product's plugin source,
    not a skill-copy destination) into the consuming cwd, attach host
    modules there, and return that entry. Does not mutate the product.

    Raises:
        HarnessError: if the shipped entry is missing, the copy fails, or
            the copied entry is not a file.
    """
    source_entry = generic_plugin_path(root=ws.root)
    source_tree = source_entry.parent
    dest_tree = ws.path / f"shipped-generic-{fresh_ident('g')}"
    try:
        shutil.copytree(source_tree, dest_tree, symlinks=False)
    except OSError as exc:
        raise HarnessError(
            f"cannot manually copy shipped generic plugin {source_tree} "
            f"-> {dest_tree}: {exc}"
        ) from exc
    dest_entry = dest_tree / source_entry.name
    try:
        present = dest_entry.is_file()
    except OSError as exc:
        raise HarnessError(
            f"cannot inspect copied shipped generic entry {dest_entry}: {exc}"
        ) from exc
    if not present:
        raise HarnessError(
            "manual copy of shipped generic plugin did not produce an "
            f"entry at {dest_entry}"
        )
    ensure_host_plugin_modules(ws, dest_entry)
    print(
        f"manual-copied shipped generic {source_entry} -> {dest_entry}",
        flush=True,
    )
    return str(dest_entry.resolve())


def copied_effect_specifier(
    ws: Workspace,
    dest: str | Path,
    generic_specifier: str | Path,
) -> str:
    """Return the Effect entry at its stated place and prove its identity.

    The Interface Contract states the Effect plugin entry is
    ``<dest>/effect/index.ts``. That file must then be the Effect plugin:
    registered as lint-policy-effect, an enabled Effect rule fires on its
    violating construct and fails lint.
    """
    dest_path = Path(dest).resolve()
    if not dest_path.is_dir():
        raise HarnessError(f"dest is not a directory: {dest_path}")
    candidate = dest_path / COPIED_EFFECT_REL
    print(f"stated effect entry={candidate}", flush=True)
    if not candidate.is_file():
        raise AssertionError(
            f"no Effect entry at {candidate} (<dest>/effect/index.ts)"
        )
    ensure_host_plugin_modules(ws, generic_specifier)
    probe = ws.write(f"effect-id-{fresh_ident('p')}.js", snippet_manual_tag_comparison())
    expected = rule_key(EFFECT_PLUGIN_NAME, "no-manual-tag-comparison")
    plugin = effect_plugin(specifier=candidate, root=ws.root)
    result = ws.lint([probe], plugins=[plugin], rules={expected: "error"})
    findings = effect_plugin_findings(result)
    print(
        f"effect-identity probe {candidate} exit={result.returncode} "
        f"findings={findings}",
        flush=True,
    )
    if expected not in findings or result.returncode == 0:
        raise AssertionError(
            f"{candidate} registered as {EFFECT_PLUGIN_NAME} must report "
            f"{expected} and fail lint; exit={result.returncode} "
            f"findings={findings}"
        )
    return str(candidate.resolve())


def lint_generic(
    ws: Workspace,
    files: Sequence[str | Path],
    rules: Sequence[str],
    specifier: str | Path,
) -> RunResult:
    """Register lint-policy only and enable *rules* at error."""
    ensure_host_plugin_modules(ws, specifier)
    plugin = generic_plugin(specifier=specifier, root=ws.root)
    mapping = {rule_key(GENERIC_PLUGIN_NAME, name): "error" for name in rules}
    print(
        f"lint-generic specifier={specifier} rules={list(rules)} files={list(files)}",
        flush=True,
    )
    return ws.lint(files, plugins=[plugin], rules=mapping)


def _ids_for_plugin(result: RunResult, plugin: str) -> tuple[str, ...]:
    """Published ``plugin/rule`` ids from classified lint JSON."""
    prefix = f"{plugin}/"
    ids: list[str] = []
    for item in diagnostics(result):
        published = published_rule_id(item.rule)
        if published.startswith(prefix):
            ids.append(published)
    return tuple(ids)


def lint_policy_findings(result: RunResult) -> tuple[str, ...]:
    """Published lint-policy rule ids (lint-policy-effect does not match)."""
    return _ids_for_plugin(result, GENERIC_PLUGIN_NAME)


def effect_plugin_findings(result: RunResult) -> tuple[str, ...]:
    return _ids_for_plugin(result, EFFECT_PLUGIN_NAME)


def rule_fired(findings: Sequence[str], rule_name: str) -> bool:
    expected = rule_key(GENERIC_PLUGIN_NAME, rule_name)
    return expected in findings


def assert_fired(result: RunResult, rule_name: str) -> None:
    generic = lint_policy_findings(result)
    effect = effect_plugin_findings(result)
    print(
        f"assert-fired {rule_name} exit={result.returncode} "
        f"generic={generic} effect={effect}",
        flush=True,
    )
    if result.returncode == 0:
        raise AssertionError(
            f"enabled rule {rule_name} at error must fail lint; "
            f"exit={result.returncode}"
        )
    expected = rule_key(GENERIC_PLUGIN_NAME, rule_name)
    if expected not in generic:
        raise AssertionError(f"expected diagnostic {expected}; got {generic}")
    if effect:
        raise AssertionError(
            f"unexpected {EFFECT_PLUGIN_NAME} findings {effect}"
        )


def assert_only_rule(result: RunResult, rule_name: str) -> None:
    generic = lint_policy_findings(result)
    effect = effect_plugin_findings(result)
    expected = rule_key(GENERIC_PLUGIN_NAME, rule_name)
    print(
        f"assert-only {rule_name} exit={result.returncode} ids={generic} "
        f"effect={effect}",
        flush=True,
    )
    if result.returncode == 0:
        raise AssertionError(
            f"enabled rule {rule_name} at error must fail lint; exit=0"
        )
    unique = tuple(dict.fromkeys(generic))
    if unique != (expected,):
        raise AssertionError(f"expected only {expected}; got {generic}")
    if effect:
        raise AssertionError(
            f"unexpected {EFFECT_PLUGIN_NAME} findings {effect}"
        )


def assert_not_fired(result: RunResult, rule_name: str) -> None:
    generic = lint_policy_findings(result)
    print(
        f"assert-not-fired {rule_name} exit={result.returncode} generic={generic}",
        flush=True,
    )
    if rule_fired(generic, rule_name):
        raise AssertionError(f"rule {rule_name} must not fire; got {generic}")


def assert_no_plugin_findings(result: RunResult) -> None:
    generic = lint_policy_findings(result)
    effect = effect_plugin_findings(result)
    print(
        f"assert-no-plugin-findings exit={result.returncode} "
        f"generic={generic} effect={effect}",
        flush=True,
    )
    if generic or effect:
        raise AssertionError(
            "expected no lint-policy or lint-policy-effect diagnostics; "
            f"generic={generic} effect={effect}"
        )


def snippet_no_array_filter_map(*, twin: bool = False) -> str:
    if not twin:
        return "[].filter(active).map(email);\n"
    keep = fresh_ident("keep")
    pick = fresh_ident("pick")
    return f"[].filter({keep}).map({pick});\n"


def snippet_no_reduce_accumulator_copy(*, twin: bool = False) -> str:
    key = "id" if not twin else fresh_ident("key")
    return (
        f"void [].reduce((acc, item) => Object.assign({{}}, acc, {{ {key}: item }}), {{}});\n"
    )


def snippet_no_conditional_empty_object_spread(*, twin: bool = False) -> str:
    field = "payload" if not twin else fresh_ident("field")
    cond = "ready" if not twin else fresh_ident("cond")
    return f"void ({{ ...({cond} ? {{ {field}: 1 }} : {{}}) }});\n"


def snippet_no_chained_type_assertions(*, twin: bool = False) -> str:
    target = "User" if not twin else fresh_ident("Target")
    value = "input" if not twin else fresh_ident("val")
    return f"{_SAFETY_COMMENT}\nvoid ({value} as unknown as {target});\n"


def snippet_no_known_value_widening(*, twin: bool = False) -> str:
    command = "Command" if not twin else fresh_ident("Cmd")
    binding = "commands" if not twin else fresh_ident("table")
    key = "start" if not twin else fresh_ident("go")
    starter = "startCommand" if not twin else fresh_ident("run")
    return (
        f"type {command} = () => void;\n"
        f"\n"
        f"const {binding}: Record<string, {command}> = {{ {key}: {starter} }};\n"
    )


def snippet_no_widen_then_assert(*, twin: bool = False) -> str:
    type_name = "UserId" if not twin else fresh_ident("Parsed")
    source = "source" if not twin else fresh_ident("src")
    wide = "widened" if not twin else fresh_ident("wide")
    parsed = "parsed" if not twin else fresh_ident("got")
    return (
        f"type {type_name} = {{ readonly id: string }};\n"
        f"\n"
        f"function load() {{\n"
        f"  const {source} = {{ id: \"second\" }};\n"
        f"  const {wide}: any = {source};\n"
        f"  {_SAFETY_COMMENT}\n"
        f"  const {parsed} = {wide} as {type_name};\n"
        f"\n"
        f"  return {parsed};\n"
        f"}}\n"
    )


def snippet_require_safety_comment_for_type_assertion(*, twin: bool = False) -> str:
    target = "User" if not twin else fresh_ident("Target")
    value = "input" if not twin else fresh_ident("val")
    return f"void ({value} as {target});\n"


def snippet_no_object_parameters(*, twin: bool = False) -> str:
    name = "accept" if not twin else fresh_ident("take")
    param = "value" if not twin else fresh_ident("arg")
    return f"function {name}({param}: object) {{}}\n"


def snippet_no_unknown_parameters(*, twin: bool = False) -> str:
    name = "parse" if not twin else fresh_ident("read")
    param = "value" if not twin else fresh_ident("arg")
    return f"function {name}({param}: unknown) {{}}\n"


def snippet_no_unknown_returns(*, twin: bool = False) -> str:
    name = "load" if not twin else fresh_ident("fetch")
    return f"function {name}(): unknown {{ return input; }}\n"


def snippet_no_unknown_type_aliases(*, twin: bool = False) -> str:
    alias = "UnusedAlias" if not twin else fresh_ident("Alias")
    return f"type {alias} = unknown;\n"


def snippet_no_unsafe_dictionary_type(*, twin: bool = False) -> str:
    alias = "OpenDict" if not twin else fresh_ident("Dict")
    return f"type {alias} = Record<string, unknown>;\n"


def snippet_no_runtime_typeof(*, twin: bool = False) -> str:
    name = "parseInput" if not twin else fresh_ident("check")
    param = "input" if not twin else fresh_ident("arg")
    return f"function {name}({param}) {{ return typeof {param} === \"string\"; }}\n"


def snippet_no_reflect_apply(*, twin: bool = False) -> str:
    op = "operation" if not twin else fresh_ident("op")
    owner = "owner" if not twin else fresh_ident("own")
    args = "args" if not twin else fresh_ident("argv")
    return f"Reflect.apply({op}, {owner}, {args});\n"


def snippet_no_reflect_get(*, twin: bool = False) -> str:
    owner = "owner" if not twin else fresh_ident("own")
    key = "key" if not twin else fresh_ident("slot")
    return f"Reflect.get({owner}, {key});\n"


def snippet_no_module_mocking(*, twin: bool = False) -> str:
    module = "./user-store" if not twin else f"./{fresh_ident('mod')}"
    return f"vi.mock(\"{module}\");\n"


def snippet_no_shape_in_symbol_names(*, twin: bool = False) -> str:
    if not twin:
        return "const shape = 1;\n"
    return f"const {fresh_ident('payload')}Shape = 1;\n"


def snippet_require_readable_spacing(*, twin: bool = False) -> str:
    first = "firstValue" if not twin else fresh_ident("one")
    second = "secondValue" if not twin else fresh_ident("two")
    return f"const {first} = 1;\nconst {second} = 2;\n"


def snippet_manual_tag_comparison() -> str:
    return 'void (value._tag === "Ready");\n'


def snippet_same_file_unknown_alias(*, twin: bool = False) -> str:
    alias = "UnknownValue" if not twin else fresh_ident("Alias")
    name = "load" if not twin else fresh_ident("fetch")
    return (
        f"type {alias} = unknown;\n"
        f"\n"
        f"function {name}(): {alias} {{\n"
        f"  return input;\n"
        f"}}\n"
    )


_SNIPPETS = {
    "no-array-filter-map": snippet_no_array_filter_map,
    "no-reduce-accumulator-copy": snippet_no_reduce_accumulator_copy,
    "no-chained-type-assertions": snippet_no_chained_type_assertions,
    "no-conditional-empty-object-spread": snippet_no_conditional_empty_object_spread,
    "no-known-value-widening": snippet_no_known_value_widening,
    "no-module-mocking": snippet_no_module_mocking,
    "no-object-parameters": snippet_no_object_parameters,
    "no-reflect-apply": snippet_no_reflect_apply,
    "no-reflect-get": snippet_no_reflect_get,
    "no-runtime-typeof": snippet_no_runtime_typeof,
    "no-shape-in-symbol-names": snippet_no_shape_in_symbol_names,
    "no-unknown-parameters": snippet_no_unknown_parameters,
    "no-unknown-returns": snippet_no_unknown_returns,
    "no-unknown-type-aliases": snippet_no_unknown_type_aliases,
    "no-unsafe-dictionary-type": snippet_no_unsafe_dictionary_type,
    "no-widen-then-assert": snippet_no_widen_then_assert,
    "require-readable-spacing": snippet_require_readable_spacing,
    "require-safety-comment-for-type-assertion": (
        snippet_require_safety_comment_for_type_assertion
    ),
}


def unique_source(rule_name: str, *, twin: bool = False) -> str:
    try:
        builder = _SNIPPETS[rule_name]
    except KeyError as exc:
        raise HarnessError(f"no unique snippet for {rule_name}") from exc
    return builder(twin=twin)


def write_cross_file_call_signature_filter_map(ws: Workspace) -> Path:
    """Write a file under lint whose only array evidence is a cross-file call.

    The other file exports a function with an explicit array return
    annotation (the call signature). The file under lint imports that
    function and chains adjacent filter then map on the call. Same-file
    array literals, annotations, and const aliases are absent from the
    file under lint.
    """
    factory = fresh_ident("make")
    keep = fresh_ident("keep")
    pick = fresh_ident("pick")
    mod_stem = fresh_ident("mod")
    mod_rel = f"{mod_stem}.ts"
    ws.write(
        mod_rel,
        f"export function {factory}(): string[] {{\n  return [];\n}}\n",
    )
    source = (
        f'import {{ {factory} }} from "./{mod_rel}";\n'
        f"\n"
        f"{factory}().filter({keep}).map({pick});\n"
    )
    path = ws.write(f"cross-sig-{fresh_ident('h')}.ts", source)
    print(
        f"cross-file call signature factory={mod_rel} consumer={path.name}",
        flush=True,
    )
    return path


def write_unique_snippet(
    ws: Workspace,
    rule_name: str,
    *,
    twin: bool = False,
    prefix: str = "",
) -> Path:
    token = fresh_ident("s")
    ext = snippet_extension(rule_name)
    rel = f"{prefix}{rule_name}-{token}.{ext}"
    source = unique_source(rule_name, twin=twin)
    print(f"write snippet {rel} for {rule_name} twin={twin}", flush=True)
    return ws.write(rel, source)


def assert_outbound_connect_blocked() -> None:
    """Positive control: a deliberate outbound connect from this process fails."""
    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=2):
            raise AssertionError(
                "network observer is silent: outbound connect to 1.1.1.1:53 succeeded"
            )
    except OSError as exc:
        print(f"outbound connect blocked as required: {exc}", flush=True)


def run_copy_without_network(
    ws: Workspace,
    args: Sequence[str] | None = None,
) -> RunResult:
    """Run skill copy in the live network-less environment.

    The observer is this process: a deliberate outbound connect must fail
    (positive control). The copy then runs in the same environment. A silent
    observer (connect succeeds) fails the test. The copy child is the skill
    copy entry; dest population is asserted by the caller.
    """
    assert_outbound_connect_blocked()
    result = ws.copy(args)
    print(
        f"network-less copy exit={result.returncode} argv={list(result.argv)!r}",
        flush=True,
    )
    return result
