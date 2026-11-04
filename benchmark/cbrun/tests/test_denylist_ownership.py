"""The denylist cleanup removes what a ban names, and nothing a neighbour still needs."""

from __future__ import annotations

import hashlib
import sys
import types
from pathlib import Path

import pytest

# Another checkout of cbrun may be on the path or already imported; this test is about the
# module beside it, so that one is dropped and the local tree goes first.
_BENCHMARK = str(Path(__file__).resolve().parents[2])
for _name in [n for n in list(sys.modules) if n == "cbrun" or n.startswith("cbrun.")]:
    del sys.modules[_name]
sys.path.insert(0, _BENCHMARK)

from cbrun.denylist import (  # noqa: E402
    denylist_hashes_from_payload,
    install_ban_hashes,
    render_strip_script,
)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _strip_module(tmp_path: Path, hash_lines: list[str], monkeypatch) -> types.ModuleType:
    """The strip script as it runs inside an image, with its own hash file."""
    hashes = tmp_path / "denylist.hashes"
    hashes.write_text("\n".join(hash_lines) + "\n", encoding="utf-8")
    monkeypatch.setenv("CBRUN_DENYLIST_HASHES", str(hashes))
    module = types.ModuleType("strip_banned")
    module.__dict__["__name__"] = "strip_banned"
    exec(compile(render_strip_script(), "strip_banned.py", "exec"), module.__dict__)
    return module


def test_a_ban_is_recorded_as_a_distribution_or_an_import_root() -> None:
    lines = denylist_hashes_from_payload({"install_ban": ["pdm"], "import_ban": ["pdm/cli/main.py"]})
    kinds = {line.split()[0] for line in lines}
    assert kinds == {"dist", "import"}
    assert f"dist {_digest('pdm')}" in lines
    assert f"import {_digest('pdm')}" not in lines
    assert install_ban_hashes(["pdm"]) == [f"dist {_digest('pdm')}"]


def test_a_name_never_matches_on_the_part_before_a_hyphen(tmp_path: Path, monkeypatch) -> None:
    """A plugin, a derive macro and a build backend all carry a banned tool's name as a prefix."""
    strip = _strip_module(tmp_path, [f"dist {_digest('pdm')}", f"dist {_digest('eslint')}"], monkeypatch)
    assert strip._banned("pdm")
    for neighbour in ("pdm-backend", "pdm_backend-2.5.0.dist-info", "eslint-plugin-import",
                      "eslint-config-airbnb"):
        assert not any(strip._banned(item) for item in strip._name_candidates(neighbour)), neighbour
    # A version suffix is still taken off, so the package itself is found.
    assert any(strip._banned(item) for item in strip._name_candidates("pdm-2.26.0.dist-info"))
    assert any(strip._banned(item) for item in strip._name_candidates("pdm"))


def test_a_legacy_hash_file_without_kinds_still_bans_both_ways(tmp_path: Path, monkeypatch) -> None:
    strip = _strip_module(tmp_path, [_digest("pdm")], monkeypatch)
    assert strip._banned_dist("pdm") and strip._banned_import("pdm")


def test_a_shared_directory_loses_only_the_banned_package_files(tmp_path: Path, monkeypatch) -> None:
    """pdm and pdm-backend both fill one pdm/ namespace; removing one must leave the other."""
    strip = _strip_module(tmp_path, [f"dist {_digest('pdm')}"], monkeypatch)
    site = tmp_path / "site-packages"
    namespace = site / "pdm"
    (namespace / "backend").mkdir(parents=True)
    backend = namespace / "backend" / "base.py"
    backend.write_text("# owned by pdm-backend\n", encoding="utf-8")
    product = namespace / "core.py"
    product.write_text("# owned by pdm\n", encoding="utf-8")
    strip._keep_surviving({str(backend): ["pdm-backend"], str(product): ["pdm"]}, {"pdm"})
    strip._maybe_rm(namespace)
    assert backend.is_file()
    assert not product.exists()
    assert namespace.is_dir()


def test_an_empty_directory_of_a_banned_package_goes_away(tmp_path: Path, monkeypatch) -> None:
    strip = _strip_module(tmp_path, [f"dist {_digest('pdm')}"], monkeypatch)
    site = tmp_path / "site-packages"
    (site / "pdm" / "cli").mkdir(parents=True)
    (site / "pdm" / "cli" / "main.py").write_text("x\n", encoding="utf-8")
    strip._keep_surviving({}, {"pdm"})
    strip._maybe_rm(site / "pdm")
    assert not (site / "pdm").exists()


def test_a_file_the_system_package_database_owns_is_reported_not_removed(tmp_path: Path, monkeypatch) -> None:
    strip = _strip_module(tmp_path, [f"dist {_digest('zlib')}"], monkeypatch)
    library = tmp_path / "lib" / "libzlib.so"
    library.parent.mkdir(parents=True)
    library.write_text("binary\n", encoding="utf-8")
    monkeypatch.setitem(strip.__dict__, "_dpkg_owner", lambda path: "zlib1g")
    strip._maybe_rm(library)
    assert library.is_file()
    assert strip.CONFLICTS and "system package" in strip.CONFLICTS[0]


def _fake_python_world(strip, *, installed: dict[str, list[str]], mapping: dict[str, list[str]],
                       owners: dict[str, list[str]], uninstalled: list[list[str]]):
    """One interpreter whose packages, import roots and file owners are given."""
    strip.__dict__["_pythons"] = lambda: ["/usr/bin/python3"]
    strip.__dict__["_all_pythons"] = lambda: ["/usr/bin/python3"]
    strip.__dict__["_python_owners"] = lambda py: owners
    strip.__dict__["_uninstall"] = lambda py, dists: uninstalled.append(list(dists))
    strip.__dict__["_sourceless_pass"] = lambda: None
    strip.__dict__["_check_python"] = lambda py, before: None
    strip.__dict__["_pip_check"] = lambda py: set()
    strip.__dict__["_scan_dir"] = lambda path: None
    strip.shutil.which = lambda name: None

    def run_json(argv, env=None):
        source = argv[-1]
        if "distributions()" in source and "packages_distributions" not in source:
            return list(installed)
        if "packages_distributions" in source:
            return mapping
        if "getsitepackages" in source:
            return []
        return None

    strip.__dict__["_run_json"] = run_json


def test_sharing_an_import_root_with_a_banned_package_is_not_being_banned(tmp_path: Path, monkeypatch) -> None:
    """The pdm failure: uninstalling the namespace's other distribution took away a build backend."""
    strip = _strip_module(tmp_path, [f"dist {_digest('pdm')}"], monkeypatch)
    uninstalled: list[list[str]] = []
    _fake_python_world(
        strip,
        installed={"pdm": [], "pdm-backend": [], "pip": []},
        mapping={"pdm": ["pdm", "pdm-backend"], "pip": ["pip"]},
        owners={"/s/pdm/core.py": ["pdm"], "/s/pdm/backend/base.py": ["pdm-backend"]},
        uninstalled=uninstalled,
    )
    assert strip.main() == 0
    assert uninstalled == [["pdm"]]


def test_a_banned_import_root_another_package_provides_stops_the_cleanup(tmp_path: Path, monkeypatch) -> None:
    """Nothing shared is deleted on a guess: the run fails and names what the ban collides with."""
    strip = _strip_module(tmp_path, [f"import {_digest('pdm')}"], monkeypatch)
    uninstalled: list[list[str]] = []
    _fake_python_world(
        strip,
        installed={"pdm-backend": []},
        mapping={"pdm": ["pdm-backend"]},
        owners={"/s/pdm/backend/base.py": ["pdm-backend"]},
        uninstalled=uninstalled,
    )
    assert strip.main() == 2
    assert uninstalled == []
    assert any("import root" in message for message in strip.CONFLICTS)


def test_python_packages_left_inconsistent_fail_the_cleanup(tmp_path: Path, monkeypatch) -> None:
    strip = _strip_module(tmp_path, [f"dist {_digest('pdm')}"], monkeypatch)
    uninstalled: list[list[str]] = []
    _fake_python_world(
        strip,
        installed={"pdm": []},
        mapping={"pdm": ["pdm"]},
        owners={"/s/pdm/core.py": ["pdm"]},
        uninstalled=uninstalled,
    )
    strip.__dict__["_check_python"] = lambda py, before: strip.CONFLICTS.append(
        "python packages left inconsistent: velqora 1.0 requires pdm, which is not installed"
    )
    assert strip.main() == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_without_file_ownership_nothing_is_removed(tmp_path: Path, monkeypatch) -> None:
    """Deleting by name from here is the guess the whole mechanism exists to avoid."""
    strip = _strip_module(tmp_path, [f"dist {_digest('pdm')}"], monkeypatch)
    uninstalled: list[list[str]] = []
    _fake_python_world(
        strip,
        installed={"pdm": [], "pip": []},
        mapping={"pdm": ["pdm"]},
        owners={},
        uninstalled=uninstalled,
    )
    assert strip.main() == 2
    assert uninstalled == []
    assert any("file ownership" in message for message in strip.CONFLICTS)


def test_breakage_the_image_already_had_is_not_blamed_on_the_cleanup(tmp_path: Path, monkeypatch) -> None:
    strip = _strip_module(tmp_path, [f"dist {_digest('pdm')}"], monkeypatch)
    uninstalled: list[list[str]] = []
    _fake_python_world(
        strip,
        installed={"pdm": []},
        mapping={"pdm": ["pdm"]},
        owners={"/s/pdm/core.py": ["pdm"]},
        uninstalled=uninstalled,
    )
    standing = {"velmora 2.0 requires numpy, which is not installed"}
    strip.__dict__["_pip_check"] = lambda py: standing
    strip.__dict__["_check_python"] = strip._check_python
    assert strip.main() == 0
    assert strip.CONFLICTS == []
