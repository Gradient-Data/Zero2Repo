# feature: F00
"""Language-floor and host-lint helpers for the F00 acceptance module.

The acceptance module is the collected test. This module has no tests.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from _harness import (
    GENERIC_PLUGIN_NAME,
    HarnessError,
    diagnostics,
    generic_plugin,
    generic_plugin_path,
    node_executable,
    node_modules_path,
    rule_key,
    workspace,
)

# PRD language floor: Node.js 24.
_NODE_MAJOR = 24
_PLUGIN_WRAP = re.compile(r"(lint-policy|lint-policy-effect)\(([^()\s]+)\)")
_SNIPPET = "[].filter(active).map(email);\n"
_RULE_NAME = "no-array-filter-map"
_PLUGINS_SCOPE = "@oxlint"
_PLUGINS_NAME = "plugins"

__test__ = False


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


def _read_manifest(root: Path) -> dict:
    path = root / "package.json"
    if not path.is_file():
        raise AssertionError(f"package.json is missing at {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssertionError(f"package.json at {path} is not readable JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise AssertionError(f"package.json at {path} is not an object")
    return payload


def _version_token(text: str) -> str:
    token = text.strip().split()[0] if text.strip() else ""
    if len(token) >= 2 and token[0] == "v" and token[1].isdigit():
        return token[1:]
    return token


def _documented_manager(manifest: dict) -> tuple[str, str]:
    """Name and version from the repository's packageManager field."""
    field = manifest.get("packageManager")
    if not isinstance(field, str) or "@" not in field:
        raise AssertionError(
            f"documented package manager is missing from package.json: {field!r}"
        )
    name, rest = field.split("@", 1)
    name = name.strip()
    version = _version_token(rest.split("+", 1)[0])
    if not name or not version or any(char.isspace() for char in name):
        raise AssertionError(
            f"documented package manager is missing from package.json: {field!r}"
        )
    return name, version


def _command_version(executable: str) -> str:
    try:
        completed = subprocess.run(
            [executable, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AssertionError(f"cannot run {executable} --version: {exc}") from exc
    if completed.returncode != 0:
        raise AssertionError(
            f"{executable} --version exited {completed.returncode}: {completed.stderr!r}"
        )
    return _version_token(completed.stdout)


def assert_documented_package_manager(root: Path) -> None:
    """The running tool is the package manager the repository documents."""
    # TEST-FIX(F00): upstream package.json:28 shows packageManager naming the
    # tool and the version the repository documents.
    manifest = _read_manifest(root)
    name, documented = _documented_manager(manifest)
    executable = shutil.which(name)
    if not executable:
        raise AssertionError(f"documented package manager {name!r} is not installed")
    running = _command_version(executable)
    if running != documented:
        raise AssertionError(
            f"documented package manager {name} {running} does not match "
            f"package.json packageManager {documented}"
        )


def _node_version() -> str:
    try:
        node = node_executable()
    except FileNotFoundError as exc:
        raise AssertionError(f"Node.js is not installed: {exc}") from exc
    try:
        completed = subprocess.run(
            [node, "-p", "process.versions.node"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AssertionError(f"cannot read the Node.js version: {exc}") from exc
    if completed.returncode != 0:
        raise AssertionError(
            f"node -p process.versions.node exited {completed.returncode}: "
            f"{completed.stderr!r}"
        )
    return completed.stdout.strip()


def assert_node_language_floor() -> None:
    """The interpreter major is the language floor."""
    # TEST-FIX(F00): Full_PRD.md:51 states the language floor is Node.js 24.
    node_version = _node_version()
    major_text = node_version.split(".", 1)[0]
    try:
        major = int(major_text)
    except ValueError as exc:
        raise AssertionError(f"Node.js version {node_version!r} is not numeric") from exc
    if major != _NODE_MAJOR:
        raise AssertionError(
            f"language floor requires Node.js {_NODE_MAJOR}, got {node_version}"
        )


def _attach_plugins(tree: Path, modules: Path) -> None:
    """Point the copied plugin at the host plugins package so Oxlint can load it."""
    package = modules / _PLUGINS_SCOPE / _PLUGINS_NAME
    link_parent = tree / "node_modules" / _PLUGINS_SCOPE
    link_parent.mkdir(parents=True, exist_ok=True)
    link = link_parent / _PLUGINS_NAME
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(package, target_is_directory=True)


def assert_host_reports_one_rule(root: Path) -> None:
    """Load the generic plugin into Oxlint and require one rule to report."""
    # TEST-FIX(F00): upstream src/rules/no-array-filter-map.test.ts:27 shows
    # `[].filter(active).map(email)` is reported when the rule is enabled.
    expected = rule_key(GENERIC_PLUGIN_NAME, _RULE_NAME)
    returncode: int | None = None
    rules: tuple[str, ...] = ()
    try:
        source_entry = generic_plugin_path(root=root)
        modules = node_modules_path(root=root)
        with workspace(root=root) as ws:
            dest_tree = ws.path / "shipped-generic"
            shutil.copytree(source_entry.parent, dest_tree, symlinks=False)
            _attach_plugins(dest_tree, modules)
            snippet = ws.write("snippet.js", _SNIPPET)
            plugin = generic_plugin(specifier=dest_tree / source_entry.name, root=root)
            result = ws.lint(
                [snippet],
                plugins=[plugin],
                rules={expected: "error"},
            )
            found = diagnostics(result)
            returncode = result.returncode
        prefix = f"{GENERIC_PLUGIN_NAME}/"
        rules = tuple(
            published
            for item in found
            if (published := published_rule_id(item.rule)).startswith(prefix)
        )
    except (HarnessError, FileNotFoundError, OSError) as exc:
        raise AssertionError(
            f"host did not report {expected} on the snippet: {exc}"
        ) from exc
    print(
        f"f00-snippet exit={returncode} rules={rules} expected={expected}",
        flush=True,
    )
    if returncode == 0 or expected not in rules:
        raise AssertionError(
            f"host did not report {expected} on the snippet; "
            f"exit={returncode} rules={rules}"
        )
