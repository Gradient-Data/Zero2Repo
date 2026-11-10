# feature: F04
"""Dependency declarations exercised through lock, install, add and show."""
import json
import sys
from urllib.parse import unquote, urlsplit

from packaging.markers import Marker, default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version

from _helpers import read_toml
from F01_helpers import project_cli, project_environment, refused, succeeded, wheel_observation, write_project
from F04_helpers import (DistributionFactory, dependency_project, dependency_lock,
                         distribution_index, git_command, inspect_names, installed_values, locked_by_name,
                         lock_marker_applies)


def test_dependency_origins_and_editable_sources(tmp_path):
    factory = DistributionFactory(tmp_path / "build")
    indexed, index_wheel = factory.create("origin-index")
    directory, _ = factory.create("origin-directory")
    _, file_wheel = factory.create("origin-file")
    _, remote_wheel = factory.create("origin-remote")
    repository, _ = factory.create("origin-git", "1.0")
    env = project_environment(tmp_path / "env")
    git_command(repository, env, "init", "--initial-branch=trunk")
    git_command(repository, env, "config", "user.name", "Acceptance")
    git_command(repository, env, "config", "user.email", "acceptance@example.invalid")
    git_command(repository, env, "add", "pyproject.toml", "origin_git")
    git_command(repository, env, "commit", "-m", "Initial package")
    first = git_command(repository, env, "rev-parse", "HEAD")
    git_command(repository, env, "tag", "release-one")
    git_command(repository, env, "checkout", "-b", "feature")
    document = repository / "pyproject.toml"
    document.write_text(document.read_text().replace('version="1.0"', 'version="2.0"'))
    (repository / "origin_git" / "__init__.py").write_text('def value():\n    return "origin-git:2.0"\n')
    git_command(repository, env, "add", "pyproject.toml", "origin_git")
    git_command(repository, env, "commit", "-m", "Branch package")
    second = git_command(repository, env, "rev-parse", "HEAD")
    git_command(repository, env, "checkout", "trunk")
    # A separate repository has no package at its root, proving subdirectory selection.
    monorepo = tmp_path / "monorepo"
    monorepo.mkdir()
    import shutil
    shutil.copytree(indexed, monorepo / "component", ignore=shutil.ignore_patterns("dist", ".venv"))
    git_command(monorepo, env, "init", "--initial-branch=trunk")
    git_command(monorepo, env, "config", "user.name", "Acceptance")
    git_command(monorepo, env, "config", "user.email", "acceptance@example.invalid")
    git_command(monorepo, env, "add", "component")
    git_command(monorepo, env, "commit", "-m", "Nested package")
    with distribution_index(tmp_path / "index", [index_wheel, remote_wheel]) as url:
        legacy = ('origin-index="1.0"\norigin-directory={path=' + json.dumps(str(directory)) + ',develop=true}\n'
                  + 'origin-file={path=' + json.dumps(str(file_wheel)) + '}\n'
                  + 'origin-remote={url=' + json.dumps(url + '/files/' + remote_wheel.name) + '}\n')
        path = dependency_project(tmp_path / "origins", url, legacy=legacy)
        records = locked_by_name(dependency_lock(path, env))
        for name, kind in (("origin-index", "legacy"), ("origin-directory", "directory"),
                           ("origin-file", "file"), ("origin-remote", "url")):
            assert records[name]["source"]["type"] == kind
        assert records["origin-index"]["source"]["url"].rstrip("/") == url + "/simple"
        assert records["origin-remote"]["source"]["url"] == url + "/files/" + remote_wheel.name
        assert (path / records["origin-directory"]["source"]["url"]).resolve() == directory.resolve()
        assert (path / records["origin-file"]["source"]["url"]).resolve() == file_wheel.resolve()
        succeeded(project_cli(path, env, "install", "--no-root"))
        names = set(records)
        assert installed_values(path, env, names)["values"] == {name: name + ":1.0" for name in names}
        (directory / "origin_directory" / "__init__.py").write_text('def value():\n    return "edited source"\n')
        assert installed_values(path, env, ["origin-directory"])["values"] == {"origin-directory": "edited source"}
        for i, (control, version, commit) in enumerate((('', '1.0', first),
                (',branch="feature"', '2.0', second), (',tag="release-one"', '1.0', first),
                (',rev="' + second + '"', '2.0', second))):
            declaration = 'origin-git={git=' + json.dumps(repository.as_uri()) + control + '}\n'
            path = dependency_project(tmp_path / ("git-" + str(i)), url, legacy=declaration)
            record = locked_by_name(dependency_lock(path, env))["origin-git"]
            assert Version(record["version"]) == Version(version)
            assert record["source"]["type"] == "git"
            recorded_url = urlsplit(record["source"]["url"])
            assert recorded_url.scheme == "file"
            assert unquote(recorded_url.path) == str(repository)
            if control:
                requested = ("feature", "release-one", second)[i - 1]
                assert record["source"]["reference"] == requested
            assert record["source"]["resolved_reference"] == commit
            succeeded(project_cli(path, env, "install", "--no-root"))
            assert installed_values(path, env, ["origin-git"])["values"] == {"origin-git": "origin-git:" + version}
        path = dependency_project(tmp_path / "nested", url, legacy='origin-index={git=' + json.dumps(monorepo.as_uri()) + ',subdirectory="component"}')
        record = locked_by_name(dependency_lock(path, env))["origin-index"]
        assert record["source"]["subdirectory"] == "component"
        succeeded(project_cli(path, env, "install", "--no-root"))
        assert installed_values(path, env, ["origin-index"])["values"] == {"origin-index": "origin-index:1.0"}


def test_standard_constraints_intersection_and_alternatives(tmp_path):
    factory = DistributionFactory(tmp_path / "build")
    versions = ["1.2", "1.9", "1.10", "2.0", "2.1", "3.0"]
    wheels = [factory.create("version-probe", v)[1] for v in versions]
    wheels += [factory.create("version-guard", v, dependencies=["version-probe==" + v])[1] for v in versions]
    env = project_environment(tmp_path / "env")
    constraints = [">1.9", ">=1.10", "<1.10", "<=1.9", "==1.10", "!=2.1,>=2,<3",
                   "~=1.9", "==1.*", "!=1.*,<3", ">=1.9,<2,!=1.10"]
    with distribution_index(tmp_path / "index", wheels) as url:
        for i, constraint in enumerate(constraints + [">=1,<2 || >=3,<4"]):
            path = dependency_project(tmp_path / str(i), url,
                standard=["version-probe" + constraint] if "||" not in constraint else [],
                legacy='version-probe=' + json.dumps(constraint) if "||" in constraint else "")
            record = locked_by_name(dependency_lock(path, env))["version-probe"]
            alternatives = [SpecifierSet(part.strip()) for part in constraint.split("||")]
            assert Version(record["version"]) in {Version(v) for v in versions}
            assert any(Version(record["version"]) in specifier for specifier in alternatives)
            # A transitive exact requirement forces each candidate in turn. This
            # measures both acceptance and rejection, including lower bounds,
            # rather than only the highest permitted release.
            for candidate in versions:
                standard = ["version-guard==" + candidate]
                if "||" not in constraint:
                    standard.append("version-probe" + constraint)
                else:
                    standard.append("version-probe")
                forced = dependency_project(tmp_path / (str(i) + "-" + candidate), url,
                    standard=standard,
                    legacy='version-probe=' + json.dumps(constraint) if "||" in constraint else "")
                if any(Version(candidate) in specifier for specifier in alternatives):
                    locked = locked_by_name(dependency_lock(forced, env))
                    assert Version(locked["version-probe"]["version"]) == Version(candidate)
                else:
                    refused(project_cli(forced, env, "lock"))
        for i, declaration in enumerate(("version-probe=>1", "version-probe[", "version-probe (>=bad)")):
            path = dependency_project(tmp_path / ("bad-" + str(i)), url, standard=[declaration])
            refused(project_cli(path, env, "lock"))


def test_caret_tilde_boundaries_and_add_conversion(tmp_path):
    factory = DistributionFactory(tmp_path / "build")
    # Independent boundary vectors; no product constraint parser supplies the oracle.
    vectors = [("^1.2.3", ">=1.2.3,<2", ["1.2.2", "1.2.3", "1.9", "2.0"]),
               ("^0.2.3", ">=0.2.3,<0.3", ["0.2.2", "0.2.3", "0.2.9", "0.3"]),
               ("^0.0.3", ">=0.0.3,<0.0.4", ["0.0.2", "0.0.3", "0.0.4"]),
               ("^0", ">=0,<1", ["0", "0.9", "1"]),
               ("^0.0", ">=0,<0.1", ["0", "0.0.9", "0.1"]),
               ("^0.0.0", ">=0,<0.0.1", ["0", "0.0.0.9", "0.0.1"]),
               ("~1", ">=1,<2", ["0.9", "1", "1.9", "2"]),
               ("~1.2", ">=1.2,<1.3", ["1.1", "1.2", "1.2.9", "1.3"])]
    wheels = [factory.create("range-probe", v)[1] for v in sorted({v for _, _, vs in vectors for v in vs})]
    wheels += [factory.create("range-guard", v, dependencies=["range-probe==" + v])[1] for v in sorted({v for _, _, vs in vectors for v in vs})]
    env = project_environment(tmp_path / "env")
    with distribution_index(tmp_path / "index", wheels) as url:
        all_versions = {Version(v) for _, _, vs in vectors for v in vs}
        for i, (constraint, standard, boundaries) in enumerate(vectors):
            for mode in ("legacy", "add"):
                path = dependency_project(tmp_path / (str(i) + mode), url,
                    legacy='range-probe=' + json.dumps(constraint) if mode == "legacy" else "")
                if mode == "add":
                    succeeded(project_cli(path, env, "add", "range-probe@" + constraint, "--lock"))
                    requirement, = [Requirement(r) for r in read_toml(path / "pyproject.toml")["project"]["dependencies"]]
                    for v in all_versions:
                        assert (v in requirement.specifier) == (v in SpecifierSet(standard)), (constraint, v, requirement)
                    records = read_toml(path / "velnora.lock")["package"]
                else:
                    records = dependency_lock(path, env)
                selected = Version(locked_by_name(records)["range-probe"]["version"])
                assert selected in all_versions and selected in SpecifierSet(standard)
            for candidate in boundaries:
                forced = dependency_project(tmp_path / (str(i) + "-forced-" + candidate), url,
                    standard=["range-guard==" + candidate, "range-probe"], legacy='range-probe=' + json.dumps(constraint))
                if Version(candidate) in SpecifierSet(standard):
                    record = locked_by_name(dependency_lock(forced, env))["range-probe"]
                    assert Version(record["version"]) == Version(candidate)
                else:
                    refused(project_cli(forced, env, "lock"))


def test_markers_disjoint_requirements_and_recursive_extras(tmp_path):
    factory = DistributionFactory(tmp_path / "build")
    wheels = [factory.create("marker-choice", v)[1] for v in ("1.0", "2.0")]
    wheels += [factory.create(name)[1] for name in ("marker-python", "marker-platform", "marker-combined", "extra-leaf")]
    wheels += [factory.create("extra-parent", extras={"leaf": ["extra-leaf==1.0"],
                 "middle": ["extra-parent[leaf]"], "bundle": ["extra-parent[middle]"]})[1]]
    markers = {"marker-python": 'python_version >= "3.10"',
               "marker-platform": 'sys_platform == "linux"',
               "marker-combined": '(python_version >= "3.10" and sys_platform == "linux") or sys_platform == "win32"'}
    declarations = [name + '==1.0; ' + marker for name, marker in markers.items()]
    declarations += ['marker-choice==1.0; sys_platform == "win32"',
                     'marker-choice==2.0; sys_platform != "win32"', 'extra-parent[bundle]==1.0']
    env = project_environment(tmp_path / "env")
    with distribution_index(tmp_path / "index", wheels) as url:
        path = dependency_project(tmp_path / "consumer", url, standard=declarations)
        records = dependency_lock(path, env)
        choices = [r for r in records if canonicalize_name(r["name"]) == "marker-choice"]
        assert {Version(r["version"]) for r in choices} == {Version("1"), Version("2")}
        for record in choices:
            for platform in ("linux", "win32"):
                target = {**default_environment(), "sys_platform": platform}
                assert lock_marker_applies(record, target) == (Version(record["version"]) == Version("1" if platform == "win32" else "2"))
        for name, expression in markers.items():
            record, = [r for r in records if canonicalize_name(r["name"]) == name]
            for python in ("3.9", "3.13"):
                for platform in ("linux", "win32", "darwin"):
                    target = {**default_environment(), "python_version": python,
                              "python_full_version": python + ".0", "sys_platform": platform}
                    assert lock_marker_applies(record, target) == Marker(expression).evaluate(target)
        succeeded(project_cli(path, env, "install", "--no-root"))
        expected = {name for name, marker in markers.items() if Marker(marker).evaluate()}
        expected |= {"marker-choice", "extra-parent", "extra-leaf"}
        observation = installed_values(path, env, expected)
        assert set(observation["installed"]) & {canonicalize_name(r["name"]) for r in records} == expected
        assert observation["values"]["marker-choice"] == "marker-choice:" + ("1.0" if sys.platform == "win32" else "2.0")
        assert observation["values"]["extra-leaf"] == "extra-leaf:1.0"
        plain = dependency_project(tmp_path / "plain", url,
            standard=[r.replace("extra-parent[bundle]", "extra-parent") for r in declarations])
        dependency_lock(plain, env)
        succeeded(project_cli(plain, env, "install", "--no-root"))
        plain_expected = expected - {"extra-leaf"}
        plain_observation = installed_values(plain, env, plain_expected)
        assert set(plain_observation["installed"]) & {canonicalize_name(r["name"]) for r in records} == plain_expected
        assert plain_observation["values"]["extra-parent"] == "extra-parent:1.0"


def test_group_inclusions_and_runtime_extra_metadata(tmp_path):
    factory = DistributionFactory(tmp_path / "build")
    names = {"runtime-base", "runtime-extra", "standard-dev", "legacy-dev"}
    wheels = [factory.create(name)[1] for name in names]
    env = project_environment(tmp_path / "env")
    extra = '''[project.optional-dependencies]
feature=["runtime-extra==1.0"]
[dependency-groups]
base=["standard-dev==1.0"]
aggregate=[{include-group="base"}]
[tool.<legacy>.group.base]
optional=true
[tool.<legacy>.group.aggregate]
optional=true
[tool.<legacy>.group.legacy]
optional=true
include-groups=["aggregate"]
[tool.<legacy>.group.legacy.dependencies]
legacy-dev="1.0"
'''
    with distribution_index(tmp_path / "index", wheels) as url:
        for i, (options, expected) in enumerate((((), {"runtime-base"}),
                (("--with", "legacy"), {"runtime-base", "standard-dev", "legacy-dev"}),
                (("--extras", "feature"), {"runtime-base", "runtime-extra"}))):
            path = dependency_project(tmp_path / str(i), url, standard=["runtime-base==1.0"], extra=extra)
            records = locked_by_name(dependency_lock(path, env))
            assert set(records) == names
            assert set(records["runtime-base"]["groups"]) == {"main"}
            assert {"base", "aggregate", "legacy"} <= set(records["standard-dev"]["groups"])
            assert set(records["legacy-dev"]["groups"]) == {"legacy"}
            succeeded(project_cli(path, env, "install", "--no-root", *options))
            observation = installed_values(path, env, expected)
            assert set(observation["installed"]) & names == expected
            assert observation["values"] == {name: name + ":1.0" for name in expected}
        metadata, _, _ = wheel_observation(path, env)
        requirements = [Requirement(r) for r in metadata.get_all("Requires-Dist", [])]
        assert {canonicalize_name(r.name) for r in requirements} == {"runtime-base", "runtime-extra"}
        extra_requirement, = [r for r in requirements if canonicalize_name(r.name) == "runtime-extra"]
        assert extra_requirement.marker.evaluate({"extra": "feature"})
        assert not extra_requirement.marker.evaluate({"extra": ""})


def test_group_selection_and_precedence(tmp_path):
    factory = DistributionFactory(tmp_path / "build")
    names = {"group-main", "group-dev", "group-docs"}
    wheels = [factory.create(name)[1] for name in names]
    extra = '''[dependency-groups]
dev=["group-dev==1.0"]
docs=["group-docs==1.0"]
[tool.<legacy>.group.docs]
optional=true
'''
    env = project_environment(tmp_path / "env")
    scenarios = [((), {"group-main", "group-dev"}),
                 (("--with", "docs"), names),
                 (("--with", "docs", "--without", "docs,dev"), {"group-main"}),
                 (("--only", "docs", "--with", "dev", "--without", "docs"), {"group-docs"}),
                 (("--all-groups",), names)]
    with distribution_index(tmp_path / "index", wheels) as url:
        for i, (options, expected) in enumerate(scenarios):
            path = dependency_project(tmp_path / str(i), url, standard=["group-main==1.0"], extra=extra)
            dependency_lock(path, env)
            succeeded(project_cli(path, env, "install", "--no-root", *options))
            observation = installed_values(path, env, expected)
            assert set(observation["installed"]) & names == expected
            assert observation["values"] == {name: name + ":1.0" for name in expected}
            if "--all-groups" not in options:
                assert inspect_names(path, env, *options) == expected


def test_unknown_groups_and_conflicting_selection(tmp_path):
    env = project_environment(tmp_path / "env")
    path = write_project(tmp_path / "consumer", '''[project]
name="sample-project"
version="1.0"
[dependency-groups]
dev=[]
''')
    dependency_lock(path, env)
    assert inspect_names(path, env) == set()
    succeeded(project_cli(path, env, "install", "--no-root"))
    for command in ("install", "show"):
        for control in ("--with", "--without", "--only"):
            options = [control, "absent-group"]
            if control != "--only":
                options += ["--only", "dev"]
            refused(project_cli(path, env, command, *options), "absent-group")
    for control in ("--with", "--without", "--only"):
        refused(project_cli(path, env, "install", "--all-groups", control, "dev"))


def test_normalized_package_extra_and_group_identity(tmp_path):
    factory = DistributionFactory(tmp_path / "build")
    wheels = [factory.create("Mixed.Package")[1], factory.create("identity-leaf")[1],
              factory.create("identity-parent", extras={"Fast_Mode": ["identity-leaf==1.0"]})[1]]
    env = project_environment(tmp_path / "env")
    with distribution_index(tmp_path / "index", wheels) as url:
        path = dependency_project(tmp_path / "consumer", url,
            standard=["MIXED_package==1.0", "identity-parent[FAST.mode]==1.0"],
            extra='[dependency-groups]\n"Quality_Check"=["mixed.package==1.0"]\n[tool.<legacy>.group.Quality_Check]\noptional=true\n')
        records = locked_by_name(dependency_lock(path, env))
        assert set(records) == {"mixed-package", "identity-parent", "identity-leaf"}
        assert set(records["mixed-package"]["groups"]) == {"main", "quality-check"}
        succeeded(project_cli(path, env, "install", "--no-root", "--with", "QUALITY.check"))
        observation = installed_values(path, env, ["identity-leaf"])
        assert observation["values"] == {"identity-leaf": "identity-leaf:1.0"}
        assert set(observation["installed"]) & set(records) == set(records)
        assert inspect_names(path, env, "--only", "quality.check") == {"mixed-package"}


def test_duplicate_missing_and_cyclic_group_definitions(tmp_path):
    env = project_environment(tmp_path / "env")
    base = '[project]\nname="sample-project"\nversion="1.0"\n[dependency-groups]\n'
    valid = 'base=[]\nleft=[{include-group="base"}]\nright=[{include-group="base"}]\ntop=[{include-group="left"},{include-group="right"}]\n'
    path = write_project(tmp_path / "consumer", base + valid)
    succeeded(project_cli(path, env, "check"))
    succeeded(project_cli(path, env, "lock"))
    for declaration in ('"Quality_Check"=[]\n"quality.check"=[]\n',
                        'parent=[{include-group="absent"}]\n',
                        'left=[{include-group="right"}]\nright=[{include-group="left"}]\n'):
        write_project(path, base + declaration)
        refused(project_cli(path, env, "check"))
