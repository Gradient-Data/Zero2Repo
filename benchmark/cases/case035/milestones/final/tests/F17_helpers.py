# feature: F17
"""Project declarations and direct version-command observations."""
from F00_documents import legacy_key
from packaging.version import Version

from _helpers import read_toml
from F01_helpers import project_cli, succeeded, write_project


def version_project(path, version, layout="both"):
    standard = f'[project]\nname = "version-project"\nversion = "{version}"\n'
    legacy = f'[tool.<legacy>]\nname = "version-project"\nversion = "{version}"\n'
    document = {"standard": standard, "legacy": legacy,
                "both": standard + legacy}[layout]
    return write_project(path, document)


def version_output(project, env, *arguments):
    result = succeeded(project_cli(project, env, "version", "--short", *arguments))
    # --short reserves stdout for a single PEP 440 version, not prose.
    return Version(result.stdout.strip())


def declared_versions(project, layout="both"):
    document = read_toml(project / "pyproject.toml")
    if layout == "both":
        selected = [document["project"], document["tool"][legacy_key()]]
    elif layout == "standard":
        selected = [document["project"]]
    else:
        selected = [document["tool"][legacy_key()]]
    return [Version(table["version"]) for table in selected]


def check_version_change(project, env, rule, expected, *options):
    target = Version(expected)
    assert version_output(project, env, rule, *options) == target
    assert declared_versions(project) == [target, target]
