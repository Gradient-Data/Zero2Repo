# feature: F08
"""Acceptance checks for standalone Python discovery, installation and removal."""
from pathlib import Path
import sys
import tarfile

from F01_helpers import project_cli, refused, succeeded
from F08_helpers import (
    ASSETS, install_release, interpreter_identity, python_environment, python_rows,
    standalone_proxy, standalone_releases,
)


def test_installed_discovery_filters(tmp_path):
    releases = standalone_releases()
    env, storage = python_environment(tmp_path)
    with standalone_proxy(tmp_path / "proxy", env, releases) as (env, state):
        installed = [install_release(tmp_path, env, release) for release in releases]
        rows = python_rows(tmp_path, env)
        assert rows
        for executable in installed:
            assert any(Path(row["Path"]).resolve() == executable.resolve() for row in rows), rows
        system = interpreter_identity(sys.executable, tmp_path, env)
        assert any(Path(row["Path"]).resolve() == Path(system["executable"]).resolve()
                   and row["Manager"] == "System" for row in rows), rows
        for row in rows:
            actual = interpreter_identity(row["Path"], tmp_path, env)
            assert row["Version"] == actual["version"] + ("t" if actual["free_threaded"] else "")
            assert row["Implementation"].lower() == actual["implementation"].lower()
            expected_owner = "Velnora" if Path(row["Path"]).resolve().is_relative_to(storage) else "System"
            assert row["Manager"] == expected_owner
        # Each selector is measured against independently executed, live entries.
        selectors = [
            (("3",), lambda row: row["Version"].split(".")[0] == "3"),
            (("3.12",), lambda row: row["Version"].startswith("3.12.")),
            (("3.12.8",), lambda row: row["Version"].removesuffix("t") == "3.12.8"),
            (("4",), lambda row: row["Version"].split(".")[0] == "4"),
            (("--implementation", "cpython"), lambda row: row["Implementation"] == "CPython"),
            (("--implementation", "pypy"), lambda row: row["Implementation"] == "PyPy"),
            (("--managed",), lambda row: row["Manager"] == "Velnora"),
            (("--free-threaded",), lambda row: row["Version"].endswith("t")),
            # Selectors combine: every requested restriction applies at once.
            (("3.13", "--free-threaded"), lambda row: row["Version"].startswith("3.13.")
             and row["Version"].endswith("t")),
            (("3.12", "--managed", "--implementation", "cpython"), lambda row: row["Version"].startswith("3.12.")
             and row["Manager"] == "Velnora" and row["Implementation"] == "CPython"),
        ]
        key = lambda row: tuple(row[field] for field in ("Version", "Implementation", "Manager", "Path"))
        for options, predicate in selectors:
            assert {key(row) for row in python_rows(tmp_path, env, *options)} == {
                key(row) for row in rows if predicate(row)}, options


def test_downloadable_releases_and_implementations(tmp_path):
    releases = standalone_releases()
    env, storage = python_environment(tmp_path)
    with standalone_proxy(tmp_path / "proxy", env, releases) as (env, state):
        for selection in ("3", "3.12", "3.12.8"):
            rows = python_rows(tmp_path, env, selection, "--all")
            available = [row for row in rows if row["Path"] == "Available for download"]
            assert available, rows
            for row in rows:
                parts = row["Version"].removesuffix("t").split(".")
                assert parts[:len(selection.split("."))] == selection.split("."), row
            assert any(row["Version"] == "3.12.8" and row["Implementation"] == "CPython"
                       for row in available), available
            # Every release offered for this platform within the selection is listed.
            offered = {(row["Version"], row["Implementation"].lower()) for row in available}
            for record in releases:
                if record["version"].split(".")[:len(selection.split("."))] == selection.split("."):
                    variant = record["version"] + ("t" if record["free_threaded"] else "")
                    assert (variant, record["implementation"]) in offered, (record, available)
        # Default CPython, explicit CPython, and the distinct PyPy implementation.
        for record, explicit in ((releases[0], False), (releases[1], True), (releases[3], True)):
            available = python_rows(tmp_path, env, record["version"], "--all")
            assert any(row["Path"] == "Available for download"
                       and row["Version"] == record["version"]
                       and row["Implementation"].lower() == record["implementation"] for row in available)
            install_release(tmp_path, env, record, explicit=explicit)
        managed = python_rows(tmp_path, env, "--managed")
        stored = sorted(path.relative_to(storage) for path in storage.rglob("*"))
        for implementation in ("cpython", "pypy"):
            refused(project_cli(tmp_path, env, "python", "install", "99.1.1",
                                "--implementation", implementation))
            assert python_rows(tmp_path, env, "--managed") == managed
            assert sorted(path.relative_to(storage) for path in storage.rglob("*")) == stored


def test_free_threaded_release_and_invalid_requests(tmp_path):
    releases = standalone_releases()
    env, storage = python_environment(tmp_path)
    with standalone_proxy(tmp_path / "proxy", env, releases) as (env, state):
        install_release(tmp_path, env, releases[2])
        managed = python_rows(tmp_path, env, "--managed")
        downloads = list(state["requests"])
        # The refusal names the 3.13 threshold; a plain "unavailable" lookup does not.
        for request, subject in ((("3.12.8", "--free-threaded"), "3.13"),
                                 (("not-a-version",), "not-a-version")):
            refused(project_cli(tmp_path, env, "python", "install", *request), subject)
            assert state["requests"] == downloads
            assert python_rows(tmp_path, env, "--managed") == managed


def test_duplicate_preservation_and_explicit_replacement(tmp_path):
    releases = standalone_releases()
    record = releases[0]
    # The oracle is the independently read release archive, not a product round trip.
    with tarfile.open(ASSETS / record["asset"], "r:gz") as archive:
        member, = [m for m in archive.getmembers() if m.name.endswith("/lib/python3.12/this.py")]
        original = archive.extractfile(member).read()
    for replace in (False, True):
        path = tmp_path / ("replace" if replace else "preserve")
        path.mkdir()
        env, storage = python_environment(path)
        with standalone_proxy(path / "proxy", env, releases) as (env, state):
            executable = install_release(path, env, record)
            installation = storage / executable.relative_to(storage).parts[0]
            target, = installation.rglob("this.py")
            assert target.read_bytes() == original
            edited = b"# User-edited non-startup standard library module.\n"
            target.write_bytes(edited)
            interpreter_identity(executable, path, env)
            result = project_cli(path, env, "python", "install", record["version"],
                                 *(("--reinstall",) if replace else ()))
            if replace:
                succeeded(result)
                assert target.read_bytes() == original
            else:
                refused(result)
                assert target.read_bytes() == edited
            actual = interpreter_identity(executable, path, env)
            assert actual["version"] == record["version"]
            assert actual["implementation"] == "CPython"


def test_download_failure_reports_failure(tmp_path):
    releases = standalone_releases()
    # Rebuild both arms from the same empty managed state; only service health differs.
    for fail in (False, True):
        path = tmp_path / ("unavailable" if fail else "available")
        path.mkdir()
        env, storage = python_environment(path)
        with standalone_proxy(path / "proxy", env, releases) as (env, state):
            state["fail"] = fail
            if fail:
                refused(project_cli(path, env, "python", "install", releases[0]["version"]))
                assert python_rows(path, env, "--managed") == []
            else:
                install_release(path, env, releases[0])
            assert state["requests"]


def test_exact_removal_preserves_other_variants_and_system(tmp_path):
    releases = standalone_releases()
    env, storage = python_environment(tmp_path)
    with standalone_proxy(tmp_path / "proxy", env, releases) as (env, state):
        installed = [install_release(tmp_path, env, record) for record in releases]
        system = interpreter_identity(sys.executable, tmp_path, env)
        for incomplete in ("3", "3.12"):
            refused(project_cli(tmp_path, env, "python", "remove", incomplete))
            for executable, record in zip(installed, releases):
                assert interpreter_identity(executable, tmp_path, env)["version"] == record["version"]
        # A single release removal must preserve its neighbouring patch and variants.
        succeeded(project_cli(tmp_path, env, "python", "remove", releases[0]["version"]))
        assert not installed[0].exists()
        for executable, record in zip(installed[1:], releases[1:]):
            assert interpreter_identity(executable, tmp_path, env)["version"] == record["version"]
        # Implementation and threading selectors must preserve the other variant.
        succeeded(project_cli(tmp_path, env, "python", "remove", releases[3]["version"]))
        assert interpreter_identity(installed[3], tmp_path, env)["implementation"] == "PyPy"
        # Missing is a successful operation with a report on stdout.
        missing = succeeded(project_cli(tmp_path, env, "python", "remove", releases[0]["version"]))
        assert missing.stdout.strip()
        # Multiple exact releases in a single request, including the threaded suffix.
        succeeded(project_cli(tmp_path, env, "python", "remove", releases[1]["version"],
                              releases[2]["version"] + "t"))
        assert not installed[1].exists() and not installed[2].exists()
        assert interpreter_identity(installed[4], tmp_path, env)["version"] == releases[4]["version"]
        succeeded(project_cli(tmp_path, env, "python", "remove", releases[4]["version"]))
        assert not installed[4].exists()
        assert interpreter_identity(installed[3], tmp_path, env)["implementation"] == "PyPy"
        succeeded(project_cli(tmp_path, env, "python", "remove", releases[3]["version"],
                              "--implementation", "pypy"))
        assert not installed[3].exists()
        assert python_rows(tmp_path, env, "--managed") == []
        assert interpreter_identity(sys.executable, tmp_path, env) == system
        # Asking to remove a system release cannot remove its interpreter.
        succeeded(project_cli(tmp_path, env, "python", "remove", system["version"]))
        assert interpreter_identity(sys.executable, tmp_path, env) == system
