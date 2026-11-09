# feature: F10
"""Acceptance of distribution builds through the real public command."""
from F00_documents import legacy_document
import json
import shutil
from email.utils import getaddresses

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version

from _helpers import parse_entry_points, read_toml
from F00_reports import project_links
from F01_helpers import project_cli, project_environment, refused, succeeded
from F04_helpers import DistributionFactory, dependency_lock, dependency_project, distribution_index, git_command
from F10_helpers import (BUILD_PROJECT, CUSTOM_BACKEND, NATIVE_BACKEND, NATIVE_SOURCE,
    archive_files, archive_metadata, backend_project, build_archives, build_project,
    core_requirement, installed_wheel_result, put_file)


def test_formats_metadata_and_failed_build(tmp_path):
    env = project_environment(tmp_path / "environment")
    extra = '''description = "Distribution build specimen"
authors = [{name="Build Author", email="build@example.org"}]
license = "MIT"
keywords = ["packing", "science"]
classifiers = ["Topic :: Utilities"]
dependencies = ["runtime-addon>=1.2,<3"]
[project.optional-dependencies]
report = ["report-addon>=2,<5"]
[project.urls]
Homepage = "https://example.org/build"
[project.scripts]
build-cli = "build_subject:main"
[project.gui-scripts]
build-gui = "build_subject:main"
[project.entry-points."build.plugins"]
worker = "build_subject:main"
'''
    for label, options, formats in (("default", (), ("sdist", "wheel")),
            ("source", ("--format", "sdist"), ("sdist",)),
            ("binary", ("--format", "wheel"), ("wheel",))):
        project = build_project(tmp_path / label, extra)
        for fmt, artifact in build_archives(project, env, *options, formats=formats).items():
            files = archive_files(artifact)
            assert files["build_subject/__init__.py"] == (project / "build_subject/__init__.py").read_bytes()
            metadata = archive_metadata(files, fmt)
            assert canonicalize_name(metadata["Name"]) == "build-subject"
            assert Version(metadata["Version"]) == Version("2.3.1")
            assert metadata["Summary"] == "Distribution build specimen"
            assert metadata["License-Expression"] == "MIT"
            addresses = getaddresses(metadata.get_all("Author-email", []))
            assert len(addresses) == 1
            display, address = addresses[0]
            assert address == "build@example.org"
            assert (display if display else metadata["Author"]) == "Build Author"
            assert {word.strip() for word in metadata["Keywords"].split(",")} == {"packing", "science"}
            assert "Topic :: Utilities" in metadata.get_all("Classifier", [])
            assert project_links(metadata)['Homepage'] == 'https://example.org/build'
            assert set(metadata.get_all("Provides-Extra", [])) == {"report"}
            requirements = {canonicalize_name(r.name): r for r in map(Requirement, metadata.get_all("Requires-Dist", []))}
            assert set(requirements) == {"runtime-addon", "report-addon"}
            for name, allowed, denied in (("runtime-addon", "1.7", "3"), ("report-addon", "2.8", "5")):
                assert allowed in requirements[name].specifier
                assert denied not in requirements[name].specifier
            assert requirements["report-addon"].marker.evaluate({"extra": "report"})
            assert not requirements["report-addon"].marker.evaluate({"extra": ""})
            if fmt == "wheel":
                entry_name, = [n for n in files if n.endswith(".dist-info/entry_points.txt")]
                assert parse_entry_points(files[entry_name].decode()) == {
                    "console_scripts": {"build-cli": "build_subject:main"},
                    "gui_scripts": {"build-gui": "build_subject:main"},
                    "build.plugins": {"worker": "build_subject:main"}}
    project = build_project(tmp_path / "invalid")
    refused(project_cli(project, env, "build", "--format", "unsupported"), "unsupported")
    assert not list((project / "dist").glob("*"))
    broken = build_project(tmp_path / "broken", 'readme="missing.md"\n')
    refused(project_cli(broken, env, "build"), "missing.md")
    assert not list((broken / "dist").glob("*"))


def test_automatic_layout_precedence_and_source_rejections(tmp_path):
    env = project_environment(tmp_path / "environment")
    # Each layout has distinct source bytes, so selection must preserve the winner.
    for label, chosen, shadow in (("root", "build_subject/__init__.py", "src/build_subject/__init__.py"),
            ("src-package", "src/build_subject/__init__.py", None),
            ("src-module", "src/build_subject.py", None),
            ("root-module", "build_subject.py", "src/build_subject/__init__.py")):
        project = build_project(tmp_path / label, header=BUILD_PROJECT.replace('build-subject', 'Build.Subject'))
        shutil.rmtree(project / "build_subject")
        put_file(project / chosen, 'VALUE = "chosen source"\n')
        if shadow:
            put_file(project / shadow, 'VALUE = "shadow source"\n')
        for fmt, artifact in build_archives(project, env).items():
            files = archive_files(artifact)
            output_name = chosen.removeprefix("src/") if fmt == "wheel" else chosen
            assert files[output_name] == b'VALUE = "chosen source"\n'
            assert b'VALUE = "shadow source"\n' not in files.values()
    for layout in ("", "src/"):
        project = build_project(tmp_path / ("ambiguous-" + ("src" if layout else "root")))
        shutil.rmtree(project / "build_subject")
        put_file(project / (layout + "build_subject/__init__.py"), "value = 1\n")
        put_file(project / (layout + "build_subject.py"), "value = 2\n")
        refused(project_cli(project, env, "build", "--format", "wheel"), "build_subject.py")
        assert not list((project / "dist").glob("*.whl"))
    for label, extra in (("automatic", ""), ("explicit", '[tool.<legacy>]\npackages=[{include="absent_package"}]\n')):
        project = build_project(tmp_path / ("missing-" + label), extra)
        shutil.rmtree(project / "build_subject")
        subject = "absent_package" if label == "explicit" else "build-subject"
        refused(project_cli(project, env, "build", "--format", "wheel"), subject)
        assert not list((project / "dist").glob("*.whl"))


def test_explicit_packages_relocation_and_format_scope(tmp_path):
    env = project_environment(tmp_path / "environment")
    project = build_project(tmp_path / "project", '''[tool.<legacy>]
packages = [
 {include="alpha", from="lib", to="destination"},
 {include="beta", from="other"},
 {include="source_only", from="other", format="sdist"},
 {include="wheel_only", from="other", format="wheel"}
]
''')
    sources = {"lib/alpha/__init__.py": "VALUE=17\n", "lib/alpha/nested/__init__.py": "VALUE=29\n",
        "other/beta/__init__.py": "VALUE=41\n", "other/source_only/__init__.py": "VALUE=53\n",
        "other/wheel_only/__init__.py": "VALUE=67\n"}
    for name, content in sources.items():
        put_file(project / name, content)
    artifacts = build_archives(project, env)
    source = archive_files(artifacts["sdist"])
    wheel = archive_files(artifacts["wheel"])
    for name in ("lib/alpha/__init__.py", "lib/alpha/nested/__init__.py", "other/beta/__init__.py", "other/source_only/__init__.py"):
        assert source[name] == sources[name].encode()
    assert "other/wheel_only/__init__.py" not in source
    for name, original in (("destination/alpha/__init__.py", "lib/alpha/__init__.py"),
            ("destination/alpha/nested/__init__.py", "lib/alpha/nested/__init__.py"),
            ("beta/__init__.py", "other/beta/__init__.py"), ("wheel_only/__init__.py", "other/wheel_only/__init__.py")):
        assert wheel[name] == sources[original].encode()
    assert "source_only/__init__.py" not in wheel
    assert "build_subject/__init__.py" not in wheel
    assert "build_subject/__init__.py" not in source
    result = installed_wheel_result(artifacts["wheel"], tmp_path / "installed", env,
        'import destination.alpha, destination.alpha.nested, beta, wheel_only, json\n'
        'print(json.dumps([destination.alpha.VALUE, destination.alpha.nested.VALUE, beta.VALUE, wheel_only.VALUE]))')
    assert result == [17, 29, 41, 67]


def test_exclusions_git_and_include_precedence(tmp_path):
    env = project_environment(tmp_path / "environment")
    project = build_project(tmp_path / "project", '''[tool.<legacy>]
exclude = ["build_subject/excluded.txt", "build_subject/restored.txt"]
include = [
 {path="build_subject/restored.txt", format=["sdist", "wheel"]},
 {path="build_subject/ignored_restored.txt", format=["sdist", "wheel"]},
 "build_subject/default_include.txt",
 {path="extras/wheel.txt", format="wheel"}
]
''')
    payloads = {name: (name + " payload\n").encode() for name in (
        "build_subject/plain.txt", "build_subject/excluded.txt", "build_subject/restored.txt",
        "build_subject/ignored.txt", "build_subject/ignored_restored.txt",
        "build_subject/default_include.txt", "extras/wheel.txt")}
    for name, payload in payloads.items():
        put_file(project / name, payload.decode())
    put_file(project / ".gitignore", "build_subject/ignored.txt\nbuild_subject/ignored_restored.txt\nbuild_subject/default_include.txt\n")
    git_command(project, env, "init", "-q")
    for fmt, artifact in build_archives(project, env).items():
        files = archive_files(artifact)
        for name in ("build_subject/plain.txt", "build_subject/restored.txt", "build_subject/ignored_restored.txt"):
            assert files[name] == payloads[name]
        for name in ("build_subject/excluded.txt", "build_subject/ignored.txt"):
            assert name not in files
        assert ("build_subject/default_include.txt" in files) == (fmt == "sdist")
        if fmt == "sdist":
            assert files["build_subject/default_include.txt"] == payloads["build_subject/default_include.txt"]
        assert ("extras/wheel.txt" in files) == (fmt == "wheel")
        if fmt == "wheel":
            assert files["extras/wheel.txt"] == payloads["extras/wheel.txt"]


def test_license_readmes_and_declared_requirements(tmp_path):
    env = project_environment(tmp_path / "environment")
    factory = DistributionFactory(tmp_path / "dependencies")
    _, dep = factory.create("runtime-addon", "1.7")
    with distribution_index(tmp_path / "index", [dep]) as index:
        for label, license_files in (("selected", '["legal/*.txt"]'), ("empty", "[]")):
            project = dependency_project(tmp_path / label, index,
                standard=["runtime-addon>=1.2,<3"], name="build-subject", extra='dynamic=["readme"]\nlicense-files=' + license_files + '\n')
            (project / "sample_project").rename(project / "build_subject")
            document = (project / "pyproject.toml").read_text()
            document += '\n[tool.<legacy>]\nreadme=["intro.md", "details.md"]\n'
            (project / "pyproject.toml").write_text(legacy_document(document))
            put_file(project / "intro.md", "Introductory content.\n")
            put_file(project / "details.md", "Detailed content.\n")
            put_file(project / "legal/NOTICE.txt", "Selected permission material.\n")
            put_file(project / "LICENSE", "Unselected permission material.\n")
            records = dependency_lock(project, env)
            record, = [r for r in records if canonicalize_name(r["name"]) == "runtime-addon"]
            assert Version(record["version"]) == Version("1.7")
            for fmt, artifact in build_archives(project, env).items():
                files = archive_files(artifact)
                metadata = archive_metadata(files, fmt)
                description = metadata.get_payload()
                first, second = "Introductory content.", "Detailed content."
                assert description.count(first) == description.count(second) == 1
                assert description.index(first) < description.index(second)
                assert not description.replace(first, "").replace(second, "").strip()
                python = SpecifierSet(metadata["Requires-Python"])
                assert "3.8" not in python and "3.9" in python and "3.13" in python
                requirement, = map(Requirement, metadata.get_all("Requires-Dist", []))
                assert canonicalize_name(requirement.name) == "runtime-addon"
                assert "1.2" in requirement.specifier and "2.9" in requirement.specifier
                assert "1.1" not in requirement.specifier and "3" not in requirement.specifier
                license_members = {n: b for n, b in files.items() if n.endswith("NOTICE.txt") or n.endswith("LICENSE")}
                if label == "selected":
                    assert list(license_members.values()) == [b"Selected permission material.\n"]
                else:
                    assert license_members == {}


def test_custom_backend_requirements_settings_and_failures(tmp_path):
    env = project_environment(tmp_path / "environment")
    factory = DistributionFactory(tmp_path / "requirements")
    _, seed = factory.create("build-seed", "1.6")
    _, extra = factory.create("build-extra", "3.2")
    core = core_requirement(tmp_path)
    source = 'EXTRA_REQUIREMENTS = ' + repr(["build-extra @ " + extra.as_uri()]) + '\n' + CUSTOM_BACKEND
    for flavour in ("ocean", "forest"):
        project = backend_project(tmp_path / flavour, [core, "build-seed @ " + seed.as_uri()], source)
        artifacts = build_archives(project, env, "--config-settings", "flavour=" + flavour)
        expected = ["build-seed:1.6", "build-extra:3.2", flavour]
        for artifact in artifacts.values():
            files = archive_files(artifact)
            assert files["build_subject/generated.py"] == ("VALUES = " + repr(expected) + "\n").encode()
        assert installed_wheel_result(artifacts["wheel"], tmp_path / ("installed-" + flavour), env,
            'from build_subject.generated import VALUES\nimport json\nprint(json.dumps(VALUES))') == expected
    failed = backend_project(tmp_path / "failed-backend", [core, "build-seed @ " + seed.as_uri()], source)
    result = refused(project_cli(failed, env, "build", "--format", "wheel", "-c", "flavour=ocean", "-c", "fail=yes"))
    # The diagnostic identifies the affected project, by its location or its name.
    assert str(failed) in result.stderr or "build-subject" in result.stderr.replace("_", "-"), result
    assert not list((failed / "dist").glob("*.whl"))
    for label, requirements, backend_source in (
            ("declared", [core, "build-seed @ " + (tmp_path / "absent/build_seed-1.6-py3-none-any.whl").as_uri()], source),
            ("additional", [core, "build-seed @ " + seed.as_uri()],
             source.replace(extra.as_uri(), (tmp_path / "absent/build_extra-3.2-py3-none-any.whl").as_uri()))):
        project = backend_project(tmp_path / ("missing-" + label), requirements, backend_source)
        missing = "build_seed-1.6-py3-none-any.whl" if label == "declared" else "build_extra-3.2-py3-none-any.whl"
        refused(project_cli(project, env, "build", "--format", "wheel", "-c", "flavour=ocean"), missing)
        assert not list((project / "dist").glob("*.whl"))


def test_native_extension_build_and_execution(tmp_path):
    env = project_environment(tmp_path / "environment")
    project = backend_project(tmp_path / "native", [core_requirement(tmp_path)], NATIVE_BACKEND)
    put_file(project / "arithmetic.c", NATIVE_SOURCE)
    artifacts = build_archives(project, env)
    files = archive_files(artifacts["wheel"])
    assert any(n.startswith("build_subject/_arithmetic.") and n.endswith(".so") for n in files)
    result = installed_wheel_result(artifacts["wheel"], tmp_path / "installed", env,
        'import importlib.machinery, json\nfrom build_subject import _arithmetic as a\n'
        'print(json.dumps({"native": isinstance(a.__loader__, importlib.machinery.ExtensionFileLoader), '
        '"values": [a.multiply(6, 7), a.multiply(-9, 4), a.multiply(0, 71)]}))')
    assert result == {"native": True, "values": [42, -36, 0]}


def test_output_cleanup_and_local_version(tmp_path):
    env = project_environment(tmp_path / "environment")
    for clean in (False, True):
        project = build_project(tmp_path / ("clean" if clean else "retain"))
        output = project / "release artifacts"
        put_file(output / "nested/unrelated.txt", "Keep unless cleaning.\n")
        put_file(project / "dist/unrelated.txt", "Outside chosen output.\n")
        original = (project / "pyproject.toml").read_bytes()
        options = ["--output", str(output), "--config-settings", "local-version=lab.4"]
        if clean:
            options += ["--clean"]
        artifacts = build_archives(project, env, *options, output=output)
        if clean:
            assert not (output / "nested/unrelated.txt").exists()
        else:
            assert (output / "nested/unrelated.txt").read_text() == "Keep unless cleaning.\n"
        assert (project / "dist/unrelated.txt").read_text() == "Outside chosen output.\n"
        for fmt, artifact in artifacts.items():
            assert Version(archive_metadata(archive_files(artifact), fmt)["Version"]) == Version("2.3.1+lab.4")
            assert "2.3.1+lab.4" in artifact.name
        assert (project / "pyproject.toml").read_bytes() == original
        assert read_toml(project / "pyproject.toml")["project"]["version"] == "2.3.1"
