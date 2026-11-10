# feature: F02
"""Installed extensions exercised through ordinary public product commands."""
import json

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

from F00_reports import local_file_path

from _helpers import make_environment, parse_json, read_toml
from F01_helpers import (
    BUILD_SYSTEM, local_dependency, project_cli, project_environment,
    refused, succeeded, write_project,
)
from F02_helpers import (
    APPLICATION_EXTENSION, INVALID_EXTENSION, PROJECT_EXTENSION, installed_plugin,
    extension_wheel_metadata,
)


PROJECT = '''[project]
name = "sample-project"
dynamic = ["version", "description", "dependencies"]
requires-python = ">=3.9"
[tool.<legacy>]
version = "1.2.3"
description = "Metadata from the project document"
''' + BUILD_SYSTEM


def test_project_plugin_contributions_and_disabling(tmp_path):
    env = project_environment(tmp_path)
    addon = local_dependency(tmp_path / "addon")
    env = make_environment(env, updates={"ACCEPTANCE_ADDON": str(addon)})
    env = installed_plugin(tmp_path, env, PROJECT_EXTENSION, group="velnora.plugin")
    # Fresh, equivalent projects prevent earlier command state from forming the contrast.
    for disabled in (False, True):
        project = write_project(tmp_path / ("disabled" if disabled else "enabled"), PROJECT)
        flags = ("--no-plugins",) if disabled else ()
        result = succeeded(project_cli(project, env, *flags, "version", "--short"))
        assert Version(result.stdout.strip()) == Version("1.2.3" if disabled else "4.7.2")
        succeeded(project_cli(project, env, *flags, "lock"))
        locked = read_toml(project / "velnora.lock")
        assert {(canonicalize_name(p["name"]), Version(p["version"])) for p in locked.get("package", [])} == (
            set() if disabled else {("local-addon", Version("1.4.0"))})
        # Build directly with the same invocation option; inspect standard artifact metadata.
        metadata = extension_wheel_metadata(project, env, *flags)
        assert Version(metadata["Version"]) == Version("1.2.3" if disabled else "4.7.2")
        assert metadata["Summary"] == ("Metadata from the project document" if disabled else
            "Metadata supplied by an installed extension")
        requirements = [Requirement(value) for value in metadata.get_all("Requires-Dist", [])]
        assert {canonicalize_name(r.name) for r in requirements} == (set() if disabled else {"local-addon"})
        if not disabled:
            assert local_file_path(requirements[0].url) == addon.resolve()


def test_application_commands_events_and_disabling(tmp_path):
    env = project_environment(tmp_path)
    input_path = tmp_path / "input.json"
    env = make_environment(env, updates={"ACCEPTANCE_INPUT": str(input_path)})
    env = installed_plugin(tmp_path, env, APPLICATION_EXTENSION, group="velnora.application.plugin")
    # Different inputs require execution of the contributed command, not a registration log.
    project = write_project(tmp_path / "command", PROJECT)
    for values in ([3, 8, -2], [14, 0]):
        input_path.write_text(json.dumps(values), encoding="utf-8")
        result = succeeded(project_cli(project, env, "extension-count"))
        assert parse_json(result.stdout) == {"total": sum(values), "count": len(values)}
    refused(project_cli(project, env, "--no-plugins", "extension-count"), "extension-count")
    # The event changes the built long description, not merely an event counter.
    for disabled in (False, True):
        path = write_project(tmp_path / ("event-off" if disabled else "event-on"),
            PROJECT.replace('requires-python = ">=3.9"', 'requires-python = ">=3.9"\nreadme = "README.md"'))
        (path / "README.md").write_text("Initial project description", encoding="utf-8")
        input_path.write_text("Description supplied by a command event", encoding="utf-8")
        flags = ("--no-plugins",) if disabled else ()
        metadata = extension_wheel_metadata(path, env, *flags)
        assert metadata.get_payload().strip() == ("Initial project description" if disabled else
            "Description supplied by a command event")


def test_unsupported_plugin_registration_is_refused(tmp_path):
    env = project_environment(tmp_path)
    # Establish a live supported-registration baseline before the refusal.
    valid_root = tmp_path / "valid"
    valid_root.mkdir()
    input_path = tmp_path / "values.json"
    input_path.write_text("[7, 6]", encoding="utf-8")
    env = make_environment(env, updates={"ACCEPTANCE_INPUT": str(input_path)})
    valid_env = installed_plugin(valid_root, env, APPLICATION_EXTENSION, group="velnora.application.plugin")
    project = write_project(tmp_path / "project", PROJECT)
    assert parse_json(succeeded(project_cli(project, valid_env, "extension-count")).stdout) == {"total": 13, "count": 2}
    for group in ("velnora.plugin", "velnora.application.plugin"):
        root = tmp_path / group
        root.mkdir()
        invalid_env = installed_plugin(root, env, INVALID_EXTENSION, group=group)
        invalid = refused(project_cli(project, invalid_env, "version", "--short"))
        # The refusal prevents the ordinary operation rather than following it.
        # Disabling this same registration restores an ordinary working operation.
        result = succeeded(project_cli(project, invalid_env, "--no-plugins", "version", "--short"))
        assert Version(result.stdout.strip()) == Version("1.2.3")
