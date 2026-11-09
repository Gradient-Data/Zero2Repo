# feature: F17
"""Acceptance coverage for project version replacement and progression."""
from packaging.version import Version

from F01_helpers import project_cli, project_environment, refused
from F17_helpers import (check_version_change, declared_versions, version_output,
                         version_project)


def test_read_replace_preview_and_invalid_version(tmp_path):
    env = project_environment(tmp_path / "environment")
    for layout in ("standard", "legacy", "both"):
        project = version_project(tmp_path / layout, "2.6.9", layout)
        document = project / "pyproject.toml"
        before = document.read_bytes()
        assert version_output(project, env) == Version("2.6.9")
        assert document.read_bytes() == before
        replacement = "2!4.8.1rc2.post3.dev4+build.7"
        assert version_output(project, env, replacement, "--dry-run") == Version(replacement)
        assert document.read_bytes() == before
        assert version_output(project, env, replacement) == Version(replacement)
        count = 2 if layout == "both" else 1
        assert declared_versions(project, layout) == [Version(replacement)] * count
        # A second replacement must overwrite the persisted value, not a startup default.
        assert version_output(project, env, "5.3.2") == Version("5.3.2")
        assert declared_versions(project, layout) == [Version("5.3.2")] * count
        before = document.read_bytes()
        assert version_output(project, env, "major", "--dry-run") == Version("6.0.0")
        assert document.read_bytes() == before
        refused(project_cli(project, env, "version", "--short", "not-a-version"))
        assert document.read_bytes() == before
        assert version_output(project, env) == Version("5.3.2")


def test_stable_release_and_initial_prerelease_increments(tmp_path):
    env = project_environment(tmp_path / "environment")
    for rule, expected in (
        ("major", "3.0.0"), ("minor", "2.7.0"), ("patch", "2.6.10"),
        ("premajor", "3.0.0a0"), ("preminor", "2.7.0a0"),
        ("prepatch", "2.6.10a0"),
    ):
        project = version_project(tmp_path / rule, "2.6.9")
        check_version_change(project, env, rule, expected)


def test_prerelease_number_phase_and_release_boundaries(tmp_path):
    env = project_environment(tmp_path / "environment")
    # Each arm starts independently; paired phase/number and boundary arms
    # differ only in the requested operation or the declared starting release.
    scenarios = (
        ("2.6.9", "prerelease", (), "2.6.10a0"),
        ("2.6.9", "prerelease", ("--next-phase",), "2.6.10a0"),
        ("2.6.9a4", "prerelease", (), "2.6.9a5"),
        ("2.6.9a4", "prerelease", ("--next-phase",), "2.6.9b0"),
        ("2.6.9b4", "prerelease", (), "2.6.9b5"),
        ("2.6.9b4", "prerelease", ("--next-phase",), "2.6.9rc0"),
        ("2.6.9rc4", "prerelease", (), "2.6.9rc5"),
        ("2.6.9rc4", "prerelease", ("--next-phase",), "2.6.9"),
        ("2.6.9b4", "patch", (), "2.6.9"),
        ("3.0.0b4", "major", (), "3.0.0"),
        ("2.7.0b4", "minor", (), "2.7.0"),
        ("2.6.9b4", "major", (), "3.0.0"),
        ("2.6.9b4", "minor", (), "2.7.0"),
    )
    for index, (initial, rule, options, expected) in enumerate(scenarios):
        project = version_project(tmp_path / str(index), initial)
        check_version_change(project, env, rule, expected, *options)
