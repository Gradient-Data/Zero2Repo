# feature: F01
"""Acceptance checks for project interpretation through public commands."""
import sys
from email.utils import getaddresses
from F00_documents import legacy_key

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version

from _helpers import parse_json, read_toml, snapshot_installed, run_python
from F00_reports import project_links
from F01_helpers import (
    BUILD_SYSTEM, local_dependency, project_cli, project_environment,
    refused, succeeded, wheel_observation, write_project,
)


STANDARD = '''[project]
name = "sample-project"
version = "2.4.1"
description = "A project metadata acceptance specimen"
authors = [{name = "Ada Example", email = "ada@example.org"}]
maintainers = [{name = "Max Example", email = "max@example.org"}]
license = "MIT"
license-files = ["legal/*.txt"]
readme = "README.md"
keywords = ["analysis", "widgets"]
classifiers = ["Topic :: Utilities"]
requires-python = ">=3.9,<4"
dependencies = ["runtime-addon>=1.2,<3"]
[project.optional-dependencies]
report = ["report-addon>=2,<5"]
[project.urls]
Homepage = "https://example.org/home"
Repository = "https://example.org/source"
Documentation = "https://example.org/docs"
Tracker = "https://example.org/issues"
[project.scripts]
sample-cli = "sample_project:main"
[project.gui-scripts]
sample-gui = "sample_project:main"
[project.entry-points."sample.plugins"]
widget = "sample_project:main"
'''
LEGACY = '''[tool.<legacy>]
name = "sample-project"
version = "2.4.1"
description = "A project metadata acceptance specimen"
authors = ["Ada Example <ada@example.org>"]
maintainers = ["Max Example <max@example.org>"]
license = "MIT"
readme = "README.md"
keywords = ["analysis", "widgets"]
classifiers = ["Topic :: Utilities"]
homepage = "https://example.org/home"
repository = "https://example.org/source"
documentation = "https://example.org/docs"
[tool.<legacy>.urls]
Tracker = "https://example.org/issues"
[tool.<legacy>.dependencies]
python = ">=3.9,<4"
runtime-addon = ">=1.2,<3"
report-addon = {version = ">=2,<5", optional = true}
[tool.<legacy>.extras]
report = ["report-addon"]
[tool.<legacy>.scripts]
sample-cli = "sample_project:main"
[tool.<legacy>.plugins."gui_scripts"]
sample-gui = "sample_project:main"
[tool.<legacy>.plugins."sample.plugins"]
widget = "sample_project:main"
'''


def test_metadata_declarations_precedence_and_dynamic(tmp_path):
    env = project_environment(tmp_path / "environment")
    dynamic = '''[project]
name = "sample-project"
license-files = ["legal/*.txt"]
dynamic = ["version", "description", "authors", "maintainers", "license", "readme", "keywords", "classifiers", "urls", "requires-python", "dependencies", "optional-dependencies", "scripts", "gui-scripts", "entry-points"]
'''
    # Conflicting values make precedence observable, including individual containers.
    shadow = LEGACY.replace('sample-project', 'shadow-project').replace('2.4.1', '9.9.0').replace(
        'A project metadata acceptance specimen', 'Shadow description').replace(
        'Ada Example', 'Other Author').replace('ada@example.org', 'other@example.org').replace(
        'Max Example', 'Other Maintainer').replace('max@example.org', 'maint@example.org').replace(
        '"MIT"', '"BSD-3-Clause"').replace('"README.md"', '"SHADOW.md"').replace(
        '"analysis", "widgets"', '"shadow"').replace('Topic :: Utilities', 'Topic :: Games/Entertainment').replace(
        'https://example.org/', 'https://shadow.example.org/').replace('sample_project:main', 'sample_project:other')
    for label, document in (("standard", STANDARD), ("legacy", LEGACY),
                            ("dynamic", dynamic + LEGACY), ("precedence", STANDARD + shadow)):
        path = write_project(tmp_path / label, document + BUILD_SYSTEM)
        (path / "README.md").write_text("# Project overview\n\nReadable metadata content.\n")
        (path / "SHADOW.md").write_text("Shadow README must not win.\n")
        (path / "legal").mkdir()
        (path / "legal" / "NOTICE.txt").write_text("Permission notice\n")
        (path / "LICENSE").write_text("Legacy permission notice\n")
        succeeded(project_cli(path, env, "check"))
        metadata, entries, members = wheel_observation(path, env)
        assert canonicalize_name(metadata["Name"]) == "sample-project"
        assert Version(metadata["Version"]) == Version("2.4.1")
        assert metadata["Summary"] == "A project metadata acceptance specimen"
        for role, name, email in (("Author", "Ada Example", "ada@example.org"),
                                  ("Maintainer", "Max Example", "max@example.org")):
            addresses = getaddresses(metadata.get_all(role + "-email", []))
            assert len(addresses) == 1
            display, address = addresses[0]
            assert address == email
            if display:
                assert display == name
                if metadata[role] is not None:
                    assert metadata[role] == name
            else:
                assert metadata[role] == name
        if label in ("legacy", "dynamic"):
            assert metadata["License"] == "MIT"
        else:
            assert metadata["License-Expression"] == "MIT"
        assert {word.strip() for word in metadata["Keywords"].split(",")} == {"analysis", "widgets"}
        assert "Topic :: Utilities" in metadata.get_all("Classifier", [])
        assert "Topic :: Games/Entertainment" not in metadata.get_all("Classifier", [])
        links = project_links(metadata)
        assert links == {"Homepage": "https://example.org/home", "Repository": "https://example.org/source",
                         "Documentation": "https://example.org/docs", "Tracker": "https://example.org/issues"}
        python = SpecifierSet(metadata["Requires-Python"])
        assert all((v in python) == expected for v, expected in [("3.8", False), ("3.9", True), ("3.13", True), ("4.0", False)])
        assert metadata["Description-Content-Type"] == "text/markdown"
        assert metadata.get_payload().strip() == "# Project overview\n\nReadable metadata content."
        requirements = {canonicalize_name(r.name): r for r in map(Requirement, metadata.get_all("Requires-Dist", []))}
        assert set(requirements) == {"runtime-addon", "report-addon"}
        for name, accepted, rejected in (("runtime-addon", "1.8", "3.0"), ("report-addon", "2.1", "5.0")):
            assert accepted in requirements[name].specifier
            assert rejected not in requirements[name].specifier
        assert requirements["runtime-addon"].marker is None
        assert requirements["report-addon"].marker.evaluate({"extra": "report"})
        assert not requirements["report-addon"].marker.evaluate({"extra": ""})
        assert set(metadata.get_all("Provides-Extra", [])) == {"report"}
        assert entries == {"console_scripts": {"sample-cli": "sample_project:main"},
                           "gui_scripts": {"sample-gui": "sample_project:main"},
                           "sample.plugins": {"widget": "sample_project:main"}}
        if label != "legacy":
            assert set(metadata.get_all("License-File", [])) == {"legal/NOTICE.txt"}
            assert any(name.endswith("/licenses/legal/NOTICE.txt") and content == b"Permission notice\n"
                       for name, content in members.items())


def test_lock_enrichment_preserves_published_dependency(tmp_path):
    env = project_environment(tmp_path / "environment")
    local_dependency(tmp_path / "addon")
    path = write_project(tmp_path / "project", '''[project]
name = "sample-project"
version = "1.0"
requires-python = ">=3.9"
dependencies = ["local-addon>=1,<3"]
[tool.<legacy>.dependencies]
local-addon = {path = "../addon"}
''' + BUILD_SYSTEM)
    succeeded(project_cli(path, env, "lock"))
    packages = read_toml(path / "velnora.lock")["package"]
    assert {(canonicalize_name(p["name"]), Version(p["version"])) for p in packages} == {("local-addon", Version("1.4.0"))}
    assert packages[0]["source"]["type"] == "directory"
    assert (path / packages[0]["source"]["url"]).resolve() == (tmp_path / "addon").resolve()
    metadata, _, _ = wheel_observation(path, env)
    requirements = list(map(Requirement, metadata.get_all("Requires-Dist", [])))
    assert len(requirements) == 1
    requirement = requirements[0]
    assert canonicalize_name(requirement.name) == "local-addon"
    assert requirement.url is None
    assert all((v in requirement.specifier) == expected for v, expected in [("0.9", False), ("1.0", True), ("2.5", True), ("3.0", False)])


def test_package_modes_and_dependency_only_installation(tmp_path):
    env = project_environment(tmp_path / "environment")
    addon = local_dependency(tmp_path / "addon")
    succeeded(project_cli(addon, env, "build", "--format", "wheel"))
    wheel = next((addon / "dist").glob("*.whl"))
    for label, identity, setting in (("package", '[project]\nname="sample-project"\nversion="1.0"\n', ''),
                                     ("nonpackage", '', 'package-mode=false\n')):
        path = write_project(tmp_path / label, identity + '[tool.<legacy>]\n' + setting + '''[tool.<legacy>.dependencies]
python = ">=3.9"
local-addon = {path = "../addon"}
''' + BUILD_SYSTEM)
        succeeded(project_cli(path, env, "check"))
        succeeded(project_cli(path, env, "env", "use", sys.executable))
        executable = succeeded(project_cli(path, env, "env", "info", "--executable")).stdout.strip()
        before = {canonicalize_name(p["name"]) for p in snapshot_installed(executable, cwd=path, env=env)}
        (path / "pyproject.toml").write_text((path / "pyproject.toml").read_text().replace("../addon", str(wheel)))
        succeeded(project_cli(path, env, "install"))
        executable = succeeded(project_cli(path, env, "env", "info", "--executable")).stdout.strip()
        installed = {canonicalize_name(p["name"]): p["version"] for p in snapshot_installed(executable, cwd=path, env=env)}
        assert Version(installed["local-addon"]) == Version("1.4.0")
        if label == "package":
            assert Version(installed["sample-project"]) == Version("1.0")
            assert set(installed) - before == {"local-addon", "sample-project"}
            wheel_observation(path, env)
        else:
            assert set(installed) - before == {"local-addon"}
            refused(project_cli(path, env, "build"))
            refused(project_cli(path, env, "publish", "--dry-run"))
    missing = write_project(tmp_path / "missing", "[tool.<legacy>]\n")
    refused(project_cli(missing, env, "check"), "name", "version")


def test_invalid_project_definitions_identify_declarations(tmp_path):
    env = project_environment(tmp_path / "environment")
    valid = '[project]\nname="valid.Project_7"\nversion="1!2.0rc1.post2+local.3"\n'
    path = write_project(tmp_path / "project", valid)
    succeeded(project_cli(path, env, "check"))
    cases = [("[project\n", "pyproject.toml"),
             ('[project]\nversion="1.0"\n', "name"),
             ('[project]\nname="sample-project"\n', "version"),
             (valid + "description=42\n", "description"),
             (valid.replace('"valid.Project_7"', '42'), None),
             (valid.replace('"1!2.0rc1.post2+local.3"', '[]'), "version"),
             (valid.replace('valid.Project_7', 'bad name!'), "name"),
             (valid.replace('1!2.0rc1.post2+local.3', 'not-a-version'), "version"),
             (valid + 'dependencies=["bad name>=1"]\n', "bad name")]
    for document, subject in cases:
        write_project(path, document)
        refused(project_cli(path, env, "check"), *(() if subject is None else (subject,)))


def test_python_ranges_and_running_product_requirement(tmp_path):
    env = project_environment(tmp_path / "environment")
    document = '''[project]
name="sample-project"
version="1.0"
requires-python=">=3.9,<4"
[tool.<legacy>]
requires-velnora="*"
[tool.<legacy>.dependencies]
python=">=3.11,<4"
'''
    path = write_project(tmp_path / "project", document)
    succeeded(project_cli(path, env, "check"))
    succeeded(project_cli(path, env, "lock"))
    bound = SpecifierSet(read_toml(path / "velnora.lock")["metadata"]["python-versions"])
    assert "3.10" not in bound and "3.11" in bound and "3.13" in bound and "4.0" not in bound
    for lower in (">=3.8,<4", ">=3.11,<5"):
        write_project(path, document.replace(">=3.11,<4", lower))
        refused(project_cli(path, env, "check"), "python")
        refused(project_cli(path, env, "lock"), "python")
    # Read the running version from installed distribution metadata, not prose.
    running = succeeded(run_python(env['F01_PRODUCT_PYTHON'],
        "import importlib.metadata; print(importlib.metadata.version('velnora'))",
        cwd=path, env=env)).stdout.strip()
    for requirement, accepted in (("==" + running, True), ("!=" + running, False)):
        write_project(path, document.replace('requires-velnora="*"', 'requires-velnora="' + requirement + '"'))
        for command in ("check", "lock"):
            result = project_cli(path, env, command)
            if accepted:
                succeeded(result)
            else:
                refused(result, "Velnora", running)


def test_readme_validation_and_self_dependency(tmp_path):
    env = project_environment(tmp_path / "environment")
    base = '[project]\nname="sample-project"\nversion="1.0"\n'
    path = write_project(tmp_path / "project", base + 'readme={text="Inline documentation", content-type="text/plain"}\n')
    succeeded(project_cli(path, env, "check"))
    for declaration, subjects, names in [
            ('readme="missing-guide.md"', ("missing-guide.md",), ()),
            ('readme=""', ("README",), ()),
            ('[tool.<legacy>.dependencies]\nSample_Project=">=1"', (), ("sample-project",)),
            ('[tool.<legacy>.group.audit.dependencies]\nSample_Project=">=1"', (), ("sample-project",))]:
        write_project(path, base + declaration + '\n')
        refused(project_cli(path, env, "check"), *subjects, names=names)
    write_project(path, base + '[tool.<legacy>.group.audit.dependencies]\nother-project=">=1"\n')
    succeeded(project_cli(path, env, "check", "--strict"))
    (path / "guide.md").write_text("Real documentation\n")
    write_project(path, base + 'readme="guide.md"\n')
    succeeded(project_cli(path, env, "check", "--strict"))


def test_legacy_warnings_and_strict_validation(tmp_path):
    env = project_environment(tmp_path / "environment")
    path = write_project(tmp_path / "project", LEGACY)
    (path / "README.md").write_text("Documentation\n")
    ordinary = succeeded(project_cli(path, env, "check"))
    strict = refused(project_cli(path, env, "check", "--strict"))
    fields = ["name", "version", "description", "readme", "license", "authors", "maintainers", "keywords", "classifiers", "homepage", "repository", "documentation", "urls", "plugins", "extras", "scripts"]
    for result in (ordinary, strict):
        warning_lines = [line for line in result.stderr.splitlines() if line.startswith("Warning:")]
        for field in fields:
            assert any(f"[tool.{legacy_key()}.{field}]" in line for line in warning_lines), (field, result.stderr)
    dynamic = '[project]\nname="sample-project"\ndynamic=["version", "readme", "classifiers"]\n[tool.<legacy>]\nversion="1.0"\nreadme="README.md"\nclassifiers=["Topic :: Utilities"]\n'
    write_project(path, dynamic)
    clean = succeeded(project_cli(path, env, "check", "--strict"))
    assert "Warning:" not in clean.stderr
    # Static declarations also warn when the legacy values are present.
    static = dynamic.replace('dynamic=["version", "readme", "classifiers"]', 'version="2.0"\nreadme="README.md"\nclassifiers=["Topic :: Utilities"]')
    write_project(path, static)
    for args, status in (((), 0), (("--strict",), 1)):
        result = project_cli(path, env, "check", *args)
        assert result.returncode == status, result
        for field in ("version", "readme", "classifiers"):
            assert any(line.startswith("Warning:") and f"[tool.{legacy_key()}.{field}]" in line
                       for line in result.stderr.splitlines()), result.stderr


def test_project_discovery_and_directory_selection(tmp_path):
    env = project_environment(tmp_path / "environment")
    first = write_project(tmp_path / "first", '[project]\nname="sample-project"\nversion="1.2.3"\n')
    second = write_project(tmp_path / "second", '[project]\nname="sample-project"\nversion="4.5.6"\n')
    nested = first / "nested" / "deep"
    nested.mkdir(parents=True)
    source = "import json,os; print(json.dumps({'cwd': os.getcwd()}))"
    for cwd, options, version, child_cwd in (
        (nested, (), "1.2.3", nested),
        (nested, ("--project", str(second)), "4.5.6", nested),
        (nested, ("--directory", str(second)), "4.5.6", second),
        (nested, ("--directory", str(first), "--project", str(second)), "4.5.6", first),
    ):
        result = succeeded(project_cli(cwd, env, *options, "version", "--short"))
        assert Version(result.stdout.strip()) == Version(version)
        result = succeeded(project_cli(cwd, env, *options, "run", "python", "-c", source))
        assert parse_json(result.stdout) == {"cwd": str(child_cwd)}
    absent = tmp_path / "absent"
    absent.mkdir()
    refused(project_cli(absent, env, "version", "--short"), "pyproject.toml")
