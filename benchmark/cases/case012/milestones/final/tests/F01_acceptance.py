# feature: F01
"""Acceptance tests: vendor and register the generic plugin."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest

from _harness import (
    DEFAULT_COPY_DEST,
    EFFECT_PLUGIN_NAME,
    GENERIC_PLUGIN_NAME,
    HarnessError,
    diagnostics,
    effect_plugin,
    rule_key,
    snapshot_files,
    workspace,
)
from F01_helpers import (
    EFFECT_RULE_NAMES,
    GENERIC_RULE_NAMES,
    lint_policy_findings,
    assert_fired,
    assert_generic_configure_target,
    assert_license_and_provenance_material,
    assert_no_plugin_findings,
    assert_not_fired,
    assert_occupied_plugin_paths_overwritten,
    assert_only_rule,
    assert_tree_unchanged_outside_dest,
    copied_effect_specifier,
    effect_plugin_findings,
    fresh_ident,
    lint_generic,
    materialize_shipped_generic_entry,
    next_generic_rule,
    occupy_copied_plugin_paths,
    published_rule_id,
    require_copy_refusal,
    require_copied_layout,
    require_copy_success,
    require_unpublished_name_host_refusal,
    run_copy_without_network,
    snippet_manual_tag_comparison,
    snippet_no_array_filter_map,
    snippet_require_readable_spacing,
    snippet_same_file_unknown_alias,
    write_cross_file_call_signature_filter_map,
    write_unique_snippet,
)


@pytest.fixture(scope="module")
def copied_plugin():
    with workspace() as ws:
        result = ws.copy()
        dest = ws.resolve(DEFAULT_COPY_DEST)
        specifier = require_copied_layout(result, DEFAULT_COPY_DEST, cwd=ws.path)
        yield ws, dest, specifier


def _write(ws, rel: str, source: str) -> Path:
    return ws.write(rel, source)


# ---------------------------------------------------------------------------
# A. Default copy destination
# ---------------------------------------------------------------------------


def test_copy_with_no_destination_creates_default_tree(isolated_ws):
    ws = isolated_ws
    result = ws.copy()
    dest = ws.resolve(DEFAULT_COPY_DEST)
    specifier = require_copy_success(result, DEFAULT_COPY_DEST, cwd=ws.path)
    print(f"default dest={dest} specifier={specifier}", flush=True)
    assert dest.is_dir(), f"default dest missing: {dest}"
    relative = dest.relative_to(ws.path).as_posix()
    assert relative == DEFAULT_COPY_DEST.as_posix(), relative
    assert_license_and_provenance_material(dest)
    effect_spec = copied_effect_specifier(ws, dest, specifier)
    assert_generic_configure_target(specifier, dest, effect_spec)


def test_default_copy_dest_is_loadable_as_generic_plugin(isolated_ws):
    ws = isolated_ws
    result = ws.copy()
    specifier = require_copied_layout(result, DEFAULT_COPY_DEST, cwd=ws.path)
    chain = _write(ws, f"chain-{fresh_ident('f')}.js", snippet_no_array_filter_map())
    fired = lint_generic(ws, [chain], ["no-array-filter-map"], specifier)
    assert_only_rule(fired, "no-array-filter-map")
    spacing = _write(
        ws, f"space-{fresh_ident('f')}.js", snippet_require_readable_spacing()
    )
    spaced = lint_generic(ws, [spacing], ["require-readable-spacing"], specifier)
    assert_only_rule(spaced, "require-readable-spacing")


def test_default_copy_nested_effect_entry_loads_as_lint_policy_effect(isolated_ws):
    ws = isolated_ws
    result = ws.copy()
    dest = ws.resolve(DEFAULT_COPY_DEST)
    specifier = require_copied_layout(result, DEFAULT_COPY_DEST, cwd=ws.path)
    effect_spec = copied_effect_specifier(ws, dest, specifier)
    generic_res = Path(specifier).resolve()
    effect_res = Path(effect_spec).resolve()
    assert effect_res != generic_res
    try:
        effect_res.relative_to(dest)
    except ValueError as exc:
        raise AssertionError(
            f"effect entry {effect_res} is not nested under dest {dest}"
        ) from exc
    probe = _write(
        ws, f"effect-id-{fresh_ident('n')}.js", snippet_manual_tag_comparison()
    )
    plugin = effect_plugin(specifier=effect_spec, root=ws.root)
    mapping = {rule_key(EFFECT_PLUGIN_NAME, "no-manual-tag-comparison"): "error"}
    identified = ws.lint([probe], plugins=[plugin], rules=mapping)
    effect_ids = effect_plugin_findings(identified)
    expected = rule_key(EFFECT_PLUGIN_NAME, "no-manual-tag-comparison")
    assert expected in effect_ids, (
        "nested dest file other than the generic entry must be the Effect "
        f"plugin ({EFFECT_PLUGIN_NAME}); findings={effect_ids}"
    )
    assert identified.returncode != 0
    print(f"nested effect specifier={effect_spec}", flush=True)


# ---------------------------------------------------------------------------
# B. Caller-chosen relative destination
# ---------------------------------------------------------------------------


def test_copy_with_relative_destination_uses_that_path_only(isolated_ws):
    ws = isolated_ws
    rel = Path("vendor") / "plugins" / fresh_ident("dest")
    result = ws.copy([str(rel)])
    dest = ws.resolve(rel)
    specifier = require_copy_success(result, rel, cwd=ws.path)
    assert dest.is_dir(), dest
    default_dest = ws.resolve(DEFAULT_COPY_DEST)
    assert not default_dest.exists(), (
        "caller-chosen dest must not also create the default dest "
        f"{default_dest}"
    )
    assert_license_and_provenance_material(dest)
    effect_spec = copied_effect_specifier(ws, dest, specifier)
    assert_generic_configure_target(specifier, dest, effect_spec)
    chain = _write(ws, f"chain-{fresh_ident('b')}.js", snippet_no_array_filter_map(twin=True))
    fired = lint_generic(ws, [chain], ["no-array-filter-map"], specifier)
    assert_only_rule(fired, "no-array-filter-map")


# ---------------------------------------------------------------------------
# C. Occupied dest without --force refuses; with --force replaces
# ---------------------------------------------------------------------------


def test_copy_without_force_refuses_occupied_dest_and_preserves_bytes(isolated_ws):
    ws = isolated_ws
    dest = ws.resolve(DEFAULT_COPY_DEST)
    dest.mkdir(parents=True, exist_ok=True)
    nonce = secrets.token_hex(16)
    marker = dest / f"marker-{fresh_ident('m')}.txt"
    marker.write_text(nonce, encoding="utf-8")
    before = snapshot_files(dest)
    refused = ws.copy()
    require_copy_refusal(refused, DEFAULT_COPY_DEST, before=before, cwd=ws.path)
    assert marker.read_text(encoding="utf-8") == nonce


def test_copy_with_force_replaces_occupied_plugin_tree(isolated_ws):
    ws = isolated_ws
    first = ws.copy()
    dest = ws.resolve(DEFAULT_COPY_DEST)
    first_spec = require_copied_layout(first, DEFAULT_COPY_DEST, cwd=ws.path)
    placeholder = f"export default {fresh_ident('ph')};\n"
    occupied = occupy_copied_plugin_paths(dest, placeholder)
    first_spec_path = Path(first_spec).resolve()
    assert first_spec_path in {path.resolve() for path in occupied}, (
        "reported generic entry must be among the occupied plugin paths"
    )
    nonce = secrets.token_hex(16)
    marker = dest / f"marker-{fresh_ident('m')}.txt"
    marker.write_text(nonce, encoding="utf-8")
    replaced = ws.copy(["--force"])
    specifier = require_copied_layout(replaced, DEFAULT_COPY_DEST, cwd=ws.path)
    spec_path = Path(specifier).resolve()
    assert spec_path.is_file(), spec_path
    assert spec_path != marker.resolve(), (
        "generic-entry configure target must be a path under dest other than "
        "a dest-only extra file"
    )
    assert_occupied_plugin_paths_overwritten(occupied, placeholder)
    print(
        f"force overwrite specifier={spec_path} dest-only marker remains="
        f"{marker.exists()}",
        flush=True,
    )
    assert_license_and_provenance_material(dest)
    effect_spec = copied_effect_specifier(ws, dest, specifier)
    assert_generic_configure_target(specifier, dest, effect_spec)
    chain = _write(ws, f"chain-{fresh_ident('c')}.js", snippet_no_array_filter_map(twin=True))
    fired = lint_generic(ws, [chain], ["no-array-filter-map"], specifier)
    assert_only_rule(fired, "no-array-filter-map")


# ---------------------------------------------------------------------------
# D. Copy does not configure, install, or fetch
# ---------------------------------------------------------------------------


def test_copy_does_not_edit_lint_config_or_install_packages(isolated_ws):
    ws = isolated_ws
    dest_rel = Path("vendor") / fresh_ident("plug")
    planted_pkg = f'{{"name":"{fresh_ident("pkg")}","private":true}}\n'
    planted_cfg = f'{{"token":"{secrets.token_hex(8)}"}}\n'
    ws.write("package.json", planted_pkg)
    ws.write("project.lint.json", planted_cfg)
    before = snapshot_files(ws.path)
    result = ws.copy([str(dest_rel)])
    dest = ws.resolve(dest_rel)
    specifier = require_copied_layout(result, dest_rel, cwd=ws.path)
    print(f"copy created specifier={specifier}", flush=True)
    after = snapshot_files(ws.path)
    assert_tree_unchanged_outside_dest(before, after, dest_rel)
    assert dest.is_dir()
    assert ws.read("package.json") == planted_pkg
    assert ws.read("project.lint.json") == planted_cfg
    assert not (ws.path / "node_modules").exists()


def test_copy_succeeds_without_network(isolated_ws):
    ws = isolated_ws
    dest_rel = Path("vendor") / fresh_ident("net")
    result = run_copy_without_network(ws, [str(dest_rel)])
    dest = ws.resolve(dest_rel)
    specifier = require_copied_layout(result, dest_rel, cwd=ws.path)
    assert Path(specifier).exists() or dest.is_dir()
    assert_license_and_provenance_material(dest)


# ---------------------------------------------------------------------------
# E. Enablement oracle: no-array-filter-map
# ---------------------------------------------------------------------------


def test_enabled_no_array_filter_map_reports_on_literal_filter_then_map(
    copied_plugin,
):
    ws, _dest, specifier = copied_plugin
    public = _write(
        ws, f"filter-prd-{fresh_ident('e')}.js", snippet_no_array_filter_map()
    )
    twin = _write(
        ws,
        f"filter-twin-{fresh_ident('e')}.js",
        snippet_no_array_filter_map(twin=True),
    )
    for path in (public, twin):
        result = lint_generic(ws, [path], ["no-array-filter-map"], specifier)
        assert_only_rule(result, "no-array-filter-map")
        assert not effect_plugin_findings(result)


def test_unregistered_plugin_emits_no_lint_policy_diagnostic_on_filter_then_map(
    copied_plugin,
):
    ws, _dest, specifier = copied_plugin
    path = _write(
        ws, f"filter-unreg-{fresh_ident('e')}.js", snippet_no_array_filter_map(twin=True)
    )
    baseline = lint_generic(ws, [path], ["no-array-filter-map"], specifier)
    assert_fired(baseline, "no-array-filter-map")
    silent = ws.lint([path], plugins=[], rules={})
    assert_no_plugin_findings(silent)


def test_omitted_no_array_filter_map_emits_no_diagnostic_on_filter_then_map(
    copied_plugin,
):
    ws, _dest, specifier = copied_plugin
    path = _write(
        ws, f"filter-omit-{fresh_ident('e')}.js", snippet_no_array_filter_map(twin=True)
    )
    baseline = lint_generic(ws, [path], ["no-array-filter-map"], specifier)
    assert_fired(baseline, "no-array-filter-map")
    empty = lint_generic(ws, [path], [], specifier)
    assert_not_fired(empty, "no-array-filter-map")
    assert_no_plugin_findings(empty)
    other = lint_generic(ws, [path], ["no-object-parameters"], specifier)
    assert_not_fired(other, "no-array-filter-map")
    assert_no_plugin_findings(other)


# ---------------------------------------------------------------------------
# F. Catalog: eighteen independently enableable rules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule_name", GENERIC_RULE_NAMES)
def test_each_generic_rule_fires_only_when_enabled_on_its_snippet(
    copied_plugin, rule_name
):
    ws, _dest, specifier = copied_plugin
    path = write_unique_snippet(ws, rule_name, twin=True, prefix="cat-")
    only = lint_generic(ws, [path], [rule_name], specifier)
    assert_only_rule(only, rule_name)
    other = next_generic_rule(rule_name)
    cross = lint_generic(ws, [path], [other], specifier)
    assert_not_fired(cross, rule_name)
    assert_not_fired(cross, other)
    assert_no_plugin_findings(cross)
    all_enabled = lint_generic(ws, [path], GENERIC_RULE_NAMES, specifier)
    assert_only_rule(all_enabled, rule_name)


@pytest.mark.parametrize("rule_name", GENERIC_RULE_NAMES)
def test_enabled_rule_plus_second_catalog_name_still_attributes_only_that_rule(
    copied_plugin, rule_name
):
    ws, _dest, specifier = copied_plugin
    path = write_unique_snippet(ws, rule_name, twin=True, prefix="plus-")
    second = next_generic_rule(rule_name)
    result = lint_generic(ws, [path], [rule_name, second], specifier)
    assert_only_rule(result, rule_name)
    assert_not_fired(result, second)


def test_all_eighteen_enabled_on_unique_snippet_attributes_only_that_rule(
    copied_plugin,
):
    ws, _dest, specifier = copied_plugin
    path = _write(
        ws,
        f"all-eighteen-{fresh_ident('f')}.js",
        snippet_no_array_filter_map(twin=True),
    )
    result = lint_generic(ws, [path], GENERIC_RULE_NAMES, specifier)
    assert_only_rule(result, "no-array-filter-map")
    assert len(GENERIC_RULE_NAMES) == 18


@pytest.mark.parametrize("rule_name", GENERIC_RULE_NAMES)
def test_plugin_registered_with_no_rules_emits_no_lint_policy_diagnostics(
    copied_plugin, rule_name
):
    ws, _dest, specifier = copied_plugin
    path = write_unique_snippet(ws, rule_name, twin=True, prefix="norule-")
    baseline = lint_generic(ws, [path], [rule_name], specifier)
    assert_fired(baseline, rule_name)
    silent = lint_generic(ws, [path], [], specifier)
    assert_no_plugin_findings(silent)


# ---------------------------------------------------------------------------
# G. Generic plugin does not publish Effect rules
# ---------------------------------------------------------------------------


def test_generic_plugin_alone_emits_no_effect_plugin_diagnostics(copied_plugin):
    ws, _dest, specifier = copied_plugin
    tag = _write(
        ws, f"tag-{fresh_ident('g')}.js", snippet_manual_tag_comparison()
    )
    chain = _write(
        ws, f"g-chain-{fresh_ident('g')}.js", snippet_no_array_filter_map(twin=True)
    )
    files = [tag, chain]
    none = lint_generic(ws, files, [], specifier)
    assert_no_plugin_findings(none)
    every = lint_generic(ws, files, GENERIC_RULE_NAMES, specifier)
    try:
        effect = effect_plugin_findings(every)
        generic = lint_policy_findings(every)
    except HarnessError as exc:
        print(f"generic-only tag lint unclassified: {exc}", flush=True)
        raise AssertionError(
            "enabling the eighteen generic rules on the generic specifier "
            "must produce classified lint with no Effect-plugin diagnostic "
            "and only no-array-filter-map; host output was not classified"
        ) from exc
    assert not effect, effect
    assert_only_rule(every, "no-array-filter-map")
    print(f"generic-only tag lint generic={generic}", flush=True)


def test_effect_rule_names_are_not_published_on_generic_plugin(copied_plugin):
    ws, _dest, specifier = copied_plugin
    chain = _write(
        ws, f"g-chain-{fresh_ident('g')}.js", snippet_no_array_filter_map(twin=True)
    )
    tag = _write(ws, f"g-tag-{fresh_ident('g')}.js", snippet_manual_tag_comparison())
    carrier = lint_generic(ws, [chain], ["no-array-filter-map"], specifier)
    assert_fired(carrier, "no-array-filter-map")
    names = ["no-array-filter-map", *EFFECT_RULE_NAMES]
    result = lint_generic(ws, [chain, tag], names, specifier)
    try:
        ids = lint_policy_findings(result)
    except HarnessError as exc:
        print(f"host rejected unpublished Effect names on generic plugin: {exc}", flush=True)
        require_unpublished_name_host_refusal(result, EFFECT_RULE_NAMES)
    else:
        for effect_name in EFFECT_RULE_NAMES:
            expected = rule_key(GENERIC_PLUGIN_NAME, effect_name)
            assert expected not in ids, ids
        assert not effect_plugin_findings(result)
        print(
            f"unpublished Effect names invented nothing; classified ids={ids}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# H. Same-file analysis boundary via no-unknown-returns
# ---------------------------------------------------------------------------


def test_no_unknown_returns_flags_same_file_unknown_alias(copied_plugin):
    ws, _dest, specifier = copied_plugin
    public = _write(
        ws, f"alias-prd-{fresh_ident('h')}.ts", snippet_same_file_unknown_alias()
    )
    twin = _write(
        ws,
        f"alias-twin-{fresh_ident('h')}.ts",
        snippet_same_file_unknown_alias(twin=True),
    )
    for path in (public, twin):
        result = lint_generic(ws, [path], ["no-unknown-returns"], specifier)
        assert_only_rule(result, "no-unknown-returns")


def test_no_unknown_returns_does_not_flag_undefined_or_imported_return_name(
    copied_plugin,
):
    ws, _dest, specifier = copied_plugin
    baseline = _write(
        ws,
        f"alias-base-{fresh_ident('h')}.ts",
        snippet_same_file_unknown_alias(twin=True),
    )
    fired = lint_generic(ws, [baseline], ["no-unknown-returns"], specifier)
    assert_fired(fired, "no-unknown-returns")

    missing = _write(
        ws,
        f"missing-{fresh_ident('h')}.ts",
        "function load(): MissingType {\n  return input;\n}\n",
    )
    silent_missing = lint_generic(ws, [missing], ["no-unknown-returns"], specifier)
    assert_not_fired(silent_missing, "no-unknown-returns")
    assert_no_plugin_findings(silent_missing)

    other = f"alias-mod-{fresh_ident('h')}.ts"
    ws.write(other, "export type ImportedValue = unknown;\n")
    imported = _write(
        ws,
        f"imported-{fresh_ident('h')}.ts",
        'import { ImportedValue } from "./'
        + Path(other).name
        + '";\n\n'
        "function load(): ImportedValue {\n  return input;\n}\n",
    )
    silent_imported = lint_generic(ws, [imported], ["no-unknown-returns"], specifier)
    assert_not_fired(silent_imported, "no-unknown-returns")
    assert_no_plugin_findings(silent_imported)


def test_cross_file_call_signatures_are_not_same_file_evidence(copied_plugin):
    ws, _dest, specifier = copied_plugin
    baseline = _write(
        ws,
        f"sig-base-{fresh_ident('h')}.js",
        snippet_no_array_filter_map(twin=True),
    )
    fired = lint_generic(ws, [baseline], ["no-array-filter-map"], specifier)
    assert_fired(fired, "no-array-filter-map")

    imported = write_cross_file_call_signature_filter_map(ws)
    silent = lint_generic(ws, [imported], ["no-array-filter-map"], specifier)
    print(f"cross-file call signature path={imported.name}", flush=True)
    assert_not_fired(silent, "no-array-filter-map")
    assert_no_plugin_findings(silent)


def test_no_unknown_returns_does_not_flag_unused_unknown_or_unknown_parameter(
    copied_plugin,
):
    ws, _dest, specifier = copied_plugin
    baseline = _write(
        ws,
        f"unused-base-{fresh_ident('h')}.ts",
        snippet_same_file_unknown_alias(twin=True),
    )
    fired = lint_generic(ws, [baseline], ["no-unknown-returns"], specifier)
    assert_fired(fired, "no-unknown-returns")
    unused = _write(
        ws,
        f"unused-{fresh_ident('h')}.ts",
        "type UnusedAlias = unknown;\n\n"
        "function load(): string {\n  return \"ok\";\n}\n",
    )
    param = _write(
        ws,
        f"param-{fresh_ident('h')}.ts",
        "function load(value: unknown): string {\n  return \"ok\";\n}\n",
    )
    for path in (unused, param):
        result = lint_generic(ws, [path], ["no-unknown-returns"], specifier)
        assert_not_fired(result, "no-unknown-returns")
        assert_no_plugin_findings(result)


def test_no_unknown_returns_resolves_block_scoped_forward_and_transparent_aliases(
    copied_plugin,
):
    ws, _dest, specifier = copied_plugin
    block = _write(
        ws,
        f"block-{fresh_ident('h')}.ts",
        "function outer() {\n"
        "  type NestedAlias = unknown;\n"
        "\n"
        "  function inner(): NestedAlias {\n"
        "    return input;\n"
        "  }\n"
        "\n"
        "  return inner;\n"
        "}\n",
    )
    forward = _write(
        ws,
        f"forward-{fresh_ident('h')}.ts",
        "function load(): LaterAlias {\n"
        "  return input;\n"
        "}\n"
        "\n"
        "type LaterAlias = unknown;\n",
    )
    transparent = _write(
        ws,
        f"identity-{fresh_ident('h')}.ts",
        "type Identity<T> = T;\n"
        "\n"
        "function load(): Identity<unknown> {\n"
        "  return input;\n"
        "}\n",
    )
    for path in (block, forward, transparent):
        result = lint_generic(ws, [path], ["no-unknown-returns"], specifier)
        assert_only_rule(result, "no-unknown-returns")


# ---------------------------------------------------------------------------
# I. Unknown rule name; unparsable source
# ---------------------------------------------------------------------------


def test_unknown_lint_policy_rule_name_does_not_prevent_plugin_load(copied_plugin):
    ws, _dest, specifier = copied_plugin
    invented = f"not-in-catalog-{fresh_ident('x')}"
    chain = _write(
        ws, f"invent-{fresh_ident('i')}.js", snippet_no_array_filter_map(twin=True)
    )
    clean = _write(ws, f"clean-{fresh_ident('i')}.js", "const okValue = 1;\n")
    loaded = lint_generic(ws, [chain], ["no-array-filter-map"], specifier)
    assert_fired(loaded, "no-array-filter-map")
    names = ["no-array-filter-map", invented]
    invented_id = rule_key(GENERIC_PLUGIN_NAME, invented)
    unknown_cfg = lint_generic(ws, [chain], names, specifier)
    try:
        ids = lint_policy_findings(unknown_cfg)
    except HarnessError as exc:
        print(f"unknown rule name is a host-configuration concern: {exc}", flush=True)
        text = unknown_cfg.combined_text
        assert unknown_cfg.returncode != 0
        assert invented in text, (
            "host-configuration refusal must identify the unknown rule name; "
            f"report={text!r}"
        )
        assert GENERIC_PLUGIN_NAME in text, (
            "host-configuration refusal must name the loaded plugin; "
            f"report={text!r}"
        )
    else:
        assert invented_id not in ids, ids
    other = lint_generic(ws, [clean], ["no-array-filter-map"], specifier)
    assert_not_fired(other, "no-array-filter-map")
    other_unknown = lint_generic(ws, [clean], names, specifier)
    try:
        other_ids = lint_policy_findings(other_unknown)
    except HarnessError as exc:
        print(f"unknown name on a clean file is still host-config: {exc}", flush=True)
        text = other_unknown.combined_text
        assert other_unknown.returncode != 0
        assert invented in text, (
            "host-configuration refusal must identify the unknown rule name; "
            f"report={text!r}"
        )
        assert GENERIC_PLUGIN_NAME in text, (
            "host-configuration refusal must name the loaded plugin; "
            f"report={text!r}"
        )
    else:
        assert invented_id not in other_ids, other_ids
        assert_not_fired(other_unknown, "no-array-filter-map")


def test_unparsable_source_is_not_an_lint_policy_diagnostic(copied_plugin):
    ws, _dest, specifier = copied_plugin
    valid = _write(ws, f"valid-{fresh_ident('i')}.js", "const okValue = 1;\n")
    broken = _write(ws, f"broken-{fresh_ident('i')}.js", "const x = {\n")
    baseline = lint_generic(
        ws,
        [_write(ws, f"base-{fresh_ident('i')}.js", snippet_no_array_filter_map(twin=True))],
        ["no-array-filter-map"],
        specifier,
    )
    assert_fired(baseline, "no-array-filter-map")
    ok = lint_generic(ws, [valid], ["no-array-filter-map"], specifier)
    assert_no_plugin_findings(ok)
    broken_result = lint_generic(ws, [broken], ["no-array-filter-map"], specifier)
    try:
        findings = diagnostics(broken_result)
    except HarnessError as exc:
        print(f"unparsable host produced no classified JSON: {exc}", flush=True)
        assert broken_result.returncode != 0
        assert ok.returncode == 0
    else:
        plugin_ids = tuple(published_rule_id(item.rule) for item in findings)
        anti = tuple(
            item_id
            for item_id in plugin_ids
            if item_id.startswith(f"{GENERIC_PLUGIN_NAME}/")
            or item_id.startswith(f"{EFFECT_PLUGIN_NAME}/")
        )
        assert not anti, anti
        distinguishable = broken_result.returncode != 0 or len(findings) > 0
        assert distinguishable, (
            "unparsable source must be distinguishable from a successful "
            "lint of a valid non-violating file"
        )
        assert ok.returncode == 0


# ---------------------------------------------------------------------------
# J. Determinism and both languages
# ---------------------------------------------------------------------------


def test_same_source_and_rules_yield_the_same_lint_policy_rule_ids(copied_plugin):
    ws, _dest, specifier = copied_plugin
    source = snippet_no_array_filter_map(twin=True)
    first_path = _write(ws, f"det-a-{fresh_ident('j')}.js", source)
    second_path = _write(ws, f"det-b-{fresh_ident('j')}.js", source)
    first = lint_generic(ws, [first_path], ["no-array-filter-map"], specifier)
    second = lint_generic(ws, [second_path], ["no-array-filter-map"], specifier)
    first_ids = tuple(sorted(set(lint_policy_findings(first))))
    second_ids = tuple(sorted(set(lint_policy_findings(second))))
    print(f"determinism ids {first_ids} vs {second_ids}", flush=True)
    assert first_ids == second_ids
    assert first_ids == (rule_key(GENERIC_PLUGIN_NAME, "no-array-filter-map"),)


# ---------------------------------------------------------------------------
# K. Manual copy / product-tree specifier
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule_name", GENERIC_RULE_NAMES)
def test_shipped_generic_entry_registers_catalog_without_skill_copy(
    isolated_ws, rule_name
):
    ws = isolated_ws
    specifier = materialize_shipped_generic_entry(ws)
    path = write_unique_snippet(ws, rule_name, twin=True, prefix="ship-")
    only = lint_generic(ws, [path], [rule_name], specifier)
    assert_only_rule(only, rule_name)
    other = next_generic_rule(rule_name)
    cross = lint_generic(ws, [path], [other], specifier)
    assert_not_fired(cross, rule_name)
    assert_not_fired(cross, other)
    assert_no_plugin_findings(cross)
    plus = lint_generic(ws, [path], [rule_name, other], specifier)
    assert_only_rule(plus, rule_name)
