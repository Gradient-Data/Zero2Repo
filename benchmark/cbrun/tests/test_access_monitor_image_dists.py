"""The access monitor tells the image's own packages from code the agent installs.

Package builders such as conda record their build directory as a ``file:``
origin, so that origin alone must not mark a package as the agent's. The
snapshot taken when the agent image is built is the line between the two.
"""
from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from cbrun.access_monitor import allowlist_rule
from cbrun.denylist import render_access_monitor


def _monitor(tmp_path: Path, site: Path) -> types.ModuleType:
    mod = types.ModuleType("cbrun_monitor_under_test")
    mod.__dict__["__name__"] = "cbrun_monitor_under_test"
    exec(compile(render_access_monitor(), "access_monitor.py", "exec"), mod.__dict__)
    mod.IMAGE_DISTS = str(tmp_path / "image_dists.json")
    mod._all_pythons = lambda: ["/fake/python3"]
    mod._python_layout = lambda py: {"stdlib": str(tmp_path / "stdlib"), "sites": [str(site)]}
    return mod


def _install(site: Path, name: str, tops: list[str], url: str) -> None:
    info = site / f"{name}-1.0.dist-info"
    info.mkdir(parents=True, exist_ok=True)
    (info / "direct_url.json").write_text(json.dumps({"url": url, "dir_info": {}}))
    records = []
    for top in tops:
        pkg = site / top
        pkg.mkdir(exist_ok=True)
        (pkg / "__init__.py").write_text("")
        records.append(f"{top}/__init__.py,,")
    (info / "RECORD").write_text("\n".join(records) + "\n")


def _snapshot(mod: types.ModuleType) -> None:
    Path(mod.IMAGE_DISTS).write_text(json.dumps(mod._local_url_dists()))
    mod._LOCAL_DISTS.clear()


def test_image_package_with_builder_file_origin_is_toolchain(tmp_path):
    site = tmp_path / "site-packages"
    _install(site, "pytest", ["pytest", "_pytest"], "file:///home/task_1/croot/pytest_1/work")
    (site / "pytest" / "__main__.py").write_text("")
    (site / "_pytest" / "config").mkdir()
    (site / "_pytest" / "config" / "findpaths.py").write_text("")
    mod = _monitor(tmp_path, site)
    _snapshot(mod)

    entry = mod.toolchain_entry(str(site / "pytest" / "__main__.py"), [])
    importer = mod.toolchain_code(str(site / "_pytest" / "config" / "findpaths.py"), [])

    assert entry and importer
    # The event the case001 trial recorded: pytest reading pyproject.toml.
    argv = ["python3", "-m", "pytest", "-q", "tests"]
    assert allowlist_rule(argv, tool_entry=entry, tool_importer=importer) == "tool-internal import"


def test_package_installed_from_a_local_path_after_the_snapshot_is_the_agents(tmp_path):
    site = tmp_path / "site-packages"
    _install(site, "pytest", ["pytest"], "file:///home/task_1/croot/pytest_1/work")
    mod = _monitor(tmp_path, site)
    _snapshot(mod)
    _install(site, "mine", ["mine"], "file:///app")
    mod._LOCAL_DISTS.clear()

    assert not mod.toolchain_code(str(site / "mine" / "__init__.py"), [])
    assert mod.toolchain_code(str(site / "pytest" / "__init__.py"), [])


def test_reinstalling_an_image_package_from_a_local_path_is_the_agents(tmp_path):
    site = tmp_path / "site-packages"
    _install(site, "pytest", ["pytest"], "file:///home/task_1/croot/pytest_1/work")
    mod = _monitor(tmp_path, site)
    _snapshot(mod)
    record = site / "pytest-1.0.dist-info" / "RECORD"
    record.unlink()
    _install(site, "pytest", ["pytest", "extra"], "file:///tmp/mine")
    mod._LOCAL_DISTS.clear()

    assert not mod.toolchain_code(str(site / "pytest" / "__init__.py"), [])


def test_index_installed_package_is_toolchain_without_a_snapshot_entry(tmp_path):
    site = tmp_path / "site-packages"
    mod = _monitor(tmp_path, site)
    _install(site, "pytest", ["pytest"], "file:///home/task_1/croot/pytest_1/work")
    info = site / "pytest-1.0.dist-info" / "direct_url.json"
    info.unlink()
    _snapshot(mod)

    assert json.loads(Path(mod.IMAGE_DISTS).read_text()) == []
    assert mod.toolchain_code(str(site / "pytest" / "__init__.py"), [])


def test_missing_snapshot_is_an_error_not_a_pass(tmp_path):
    site = tmp_path / "site-packages"
    _install(site, "pytest", ["pytest"], "file:///home/task_1/croot/pytest_1/work")
    mod = _monitor(tmp_path, site)

    with pytest.raises(FileNotFoundError):
        mod.toolchain_code(str(site / "pytest" / "__init__.py"), [])


def test_snapshot_is_a_guarded_file():
    assert "IMAGE_DISTS]" in render_access_monitor().split("def guarded_files", 1)[1].split("\n", 3)[2]
