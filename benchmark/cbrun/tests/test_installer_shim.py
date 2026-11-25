"""The PATH shims run the package manager they were called as, after a check of its command line.

The fault this pins: every shim used to run pip, so ``uv venv`` became ``pip venv`` and failed.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from cbrun.denylist import (
    SHIMMED_INSTALLERS,
    denylist_hashes_from_payload,
    render_install_check,
    render_installer_shim,
    write_shim_assets,
)

BAN = {"install_ban": ["tomli", "hukkin/tomli"], "import_ban": ["tomli"]}


@pytest.fixture()
def hashes(tmp_path: Path) -> Path:
    path = tmp_path / "denylist.hashes"
    path.write_text("\n".join(denylist_hashes_from_payload(BAN)) + "\n", encoding="utf-8")
    return path


def _check(hashes: Path, tool: str, args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-I", "-c", render_install_check(), str(hashes), tool, *args],
        capture_output=True, text=True, cwd=cwd,
    )


# ---- command lines ------------------------------------------------------------------------

@pytest.mark.parametrize(
    "tool,args,blocked",
    [
        # uv: only what installs or runs a package is read.
        ("uv", ["venv", "x"], False),
        ("uv", ["--version"], False),
        ("uv", ["run", "pytest", "-k", "tomli"], False),
        ("uv", ["sync"], False),
        ("uv", ["pip", "list"], False),
        ("uv", ["pip", "install", "tomli"], True),
        ("uv", ["pip", "install", "tomli==2.0"], True),
        ("uv", ["pip", "install", "Tomli[extra]>=2"], True),
        ("uv", ["pip", "install", "git+https://github.com/hukkin/tomli.git"], True),
        ("uv", ["pip", "install", "--python", "/v/bin/python", "black"], False),
        ("uv", ["pip", "install", "--python", "tomli", "black"], False),
        ("uv", ["pip", "install", "./tomli"], False),
        ("uv", ["--directory", "/w", "pip", "install", "tomli"], True),
        ("uv", ["pip", "download", "tomli"], True),
        ("uv", ["add", "black"], False),
        ("uv", ["add", "--dev", "tomli"], True),
        ("uv", ["tool", "install", "tomli"], True),
        ("uv", ["tool", "install", "black", "--with", "tomli"], True),
        ("uv", ["tool", "run", "tomli"], True),
        ("uv", ["run", "--with", "tomli", "pytest"], True),
        ("uv", ["run", "--with=tomli", "pytest"], True),
        ("uvx", ["tomli"], True),
        ("uvx", ["tomli@latest"], True),
        ("uvx", ["--python", "3.12", "tomli"], True),
        ("uvx", ["ruff", "check", "tomli"], False),
        ("uvx", ["--from", "tomli>=2", "tomli-cli"], True),
        ("uvx", ["--with", "tomli", "black"], True),
        # pip reads its own command line the same way.
        ("pip", ["install", "tomli"], True),
        ("pip", ["install", "tomli>=2"], True),
        ("pip", ["install", "git+https://github.com/hukkin/tomli"], True),
        ("pip", ["--proxy", "http://p:3128", "install", "tomli"], True),
        ("pip3", ["install", "-i", "https://mirror/simple", "black"], False),
        ("pip", ["install", "--python", "tomli", "black"], False),
        ("pip", ["install", "-e", "./tomli"], False),
        ("pip", ["install", "."], False),
        ("pip3", ["install", "--upgrade", "tomli"], True),
        ("pip", ["download", "tomli"], True),
        ("pip", ["show", "tomli"], False),
        ("pip", ["install", "black"], False),
        # conda and the npm family keep the rules they had.
        ("conda", ["install", "tomli"], True),
        ("mamba", ["create", "-n", "x", "tomli"], True),
        ("conda", ["list", "tomli"], False),
        ("npm", ["install", "tomli@1.2.0"], True),
        ("pnpm", ["add", "tomli"], True),
        ("yarn", ["add", "-D", "tomli"], True),
        ("npm", ["run", "tomli"], False),
    ],
)
def test_check_reads_each_tools_command_line(hashes, tool, args, blocked) -> None:
    res = _check(hashes, tool, args)
    assert res.returncode == (1 if blocked else 0), res.stderr
    assert ("blocked install" in res.stderr) == blocked


def test_check_reads_requirement_files(hashes, tmp_path: Path) -> None:
    (tmp_path / "base.txt").write_text("# pinned\ntomli>=2 ; python_version < '3.11'\n")
    (tmp_path / "req.txt").write_text("black\n-r base.txt\n")
    (tmp_path / "ok.txt").write_text("black\n")
    for tool, args in (
        ("uv", ["pip", "install", "-r", "req.txt"]),
        ("uv", ["pip", "sync", "req.txt"]),
        ("uv", ["add", "-r", "req.txt"]),
        ("uvx", ["--with-requirements", "req.txt", "black"]),
        ("pip", ["install", "-r", "base.txt"]),
    ):
        res = _check(hashes, tool, args, cwd=tmp_path)
        assert res.returncode == 1 and "blocked install" in res.stderr, (tool, args, res.stderr)
    assert _check(hashes, "uv", ["pip", "install", "-r", "ok.txt"], cwd=tmp_path).returncode == 0


def test_check_refuses_an_unknown_tool(hashes) -> None:
    res = _check(hashes, "poetry", ["add", "black"])
    assert res.returncode == 1 and "does not know the package manager 'poetry'" in res.stderr


def test_every_shimmed_installer_is_written_into_the_image(hashes, tmp_path: Path) -> None:
    denylist = tmp_path / "denylist.json"
    denylist.write_text('{"install_ban": ["tomli"], "import_ban": ["tomli"]}')
    snippet = write_shim_assets(tmp_path / "ctx", denylist)
    assert {p.name for p in (tmp_path / "ctx" / "shims").iterdir()} == set(SHIMMED_INSTALLERS)
    for name in SHIMMED_INSTALLERS:
        assert (tmp_path / "ctx" / "shims" / name).read_text() == render_installer_shim()
        assert f"/opt/cbrun/bin/{name}" in snippet


# ---- in a container ------------------------------------------------------------------------

TEST_IMAGE = "python:3.13-slim-bookworm"


def _wheel(dest: Path, name: str, version: str) -> None:
    tag = f"{name}-{version}"
    files = {
        f"{name}/__init__.py": "VALUE = 1\n",
        f"{tag}.dist-info/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
        f"{tag}.dist-info/WHEEL": "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    record = "".join(f"{path},,\n" for path in files) + f"{tag}.dist-info/RECORD,,\n"
    with zipfile.ZipFile(dest / f"{tag}-py3-none-any.whl", "w") as zf:
        for path, text in files.items():
            zf.writestr(path, text)
        zf.writestr(f"{tag}.dist-info/RECORD", record)


def _docker() -> str:
    docker = shutil.which("docker")
    if not docker or subprocess.run([docker, "info"], capture_output=True).returncode != 0:
        pytest.skip("docker not available")
    if subprocess.run([docker, "image", "inspect", TEST_IMAGE], capture_output=True).returncode != 0:
        pytest.skip(f"{TEST_IMAGE} not present locally")
    return docker


def _linux_uv() -> Path:
    """A uv binary that runs in the test container: CBRUN_TEST_UV, else the one on PATH."""
    found = os.environ.get("CBRUN_TEST_UV") or shutil.which("uv")
    if not found:
        pytest.fail("this test needs a Linux uv binary: install uv or set CBRUN_TEST_UV=/path/to/uv")
    return Path(found).resolve()


def test_shims_run_the_tool_they_were_called_as(tmp_path: Path, hashes: Path) -> None:
    docker = _docker()
    uv = _linux_uv()
    src = tmp_path / "src"
    (src / "shims").mkdir(parents=True)
    (src / "wheels").mkdir()
    shutil.copy(hashes, src / "denylist.hashes")
    for name in SHIMMED_INSTALLERS:
        (src / "shims" / name).write_text(render_installer_shim())
    _wheel(src / "wheels", "tomli", "2.0.0")
    _wheel(src / "wheels", "plainpkg", "1.0")
    cid = subprocess.run(
        [docker, "run", "-d", "--rm", "--pull", "never", "--network", "none",
         "-v", f"{src.resolve()}:/src:ro", "-v", f"{uv.parent}:/uvbin:ro",
         TEST_IMAGE, "sleep", "infinity"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    def sh(command: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [docker, "exec", "-e", "PATH=/opt/cbrun/bin:/usr/local/bin:/usr/bin:/bin:/uvbin",
             "-e", "UV_CACHE_DIR=/tmp/uvcache", cid, "bash", "-c", command],
            capture_output=True, text=True, timeout=300,
        )

    offline = "--no-index --find-links /src/wheels"
    try:
        setup = sh("set -e; mkdir -p /opt/cbrun/bin && cp /src/denylist.hashes /opt/cbrun/ && "
                   "cp /src/shims/* /opt/cbrun/bin/ && chmod +x /opt/cbrun/bin/*")
        assert setup.returncode == 0, setup.stderr
        runs = sh(f"/uvbin/{uv.name} --version")
        if runs.returncode != 0:
            pytest.fail(f"{uv} does not run in {TEST_IMAGE}; set CBRUN_TEST_UV to a Linux uv "
                        f"binary: {runs.stderr.strip()}")

        # uv runs as uv.
        version = sh("uv --version")
        assert version.returncode == 0 and version.stdout.startswith("uv "), version.stdout + version.stderr
        made = sh("uv venv /tmp/uvenv")
        assert made.returncode == 0, made.stdout + made.stderr
        target = "--python /tmp/uvenv/bin/python"

        plain = sh(f"uv pip install {target} {offline} plainpkg")
        assert plain.returncode == 0, plain.stdout + plain.stderr
        assert sh("/tmp/uvenv/bin/python -c 'import plainpkg'").returncode == 0

        named = sh(f"uv pip install {target} {offline} tomli==2.0.0")
        assert named.returncode == 1 and "blocked install" in named.stderr, named.stderr
        assert sh("/tmp/uvenv/bin/python -c 'import tomli'").returncode != 0

        run = sh(f"uvx {offline} tomli")
        assert run.returncode == 1 and "blocked install" in run.stderr, run.stderr

        # pip runs as pip, with the same check as before.
        pip_plain = sh(f"pip install {offline} plainpkg")
        assert pip_plain.returncode == 0, pip_plain.stdout + pip_plain.stderr
        pip_named = sh(f"pip install {offline} tomli")
        assert pip_named.returncode == 1 and "blocked install" in pip_named.stderr, pip_named.stderr
        assert sh("python3 -c 'import tomli'").returncode != 0

        # A shimmed tool the image lacks is missing, not replaced by another.
        missing = sh("conda --version")
        assert missing.returncode == 127 and "conda: command not found" in missing.stderr, missing.stderr
    finally:
        subprocess.run([docker, "rm", "-f", cid], capture_output=True)
