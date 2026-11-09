# feature: F00
"""Offline, bundled test dependencies, extracted only into evaluator scratch space."""
import hashlib
import importlib
import json
from pathlib import Path
import sys
import shutil
import tempfile
import zipfile

import pytest
from _helpers import run_command

ASSETS = Path(__file__).resolve().parent


def checked_asset(name):
    manifest = json.loads((ASSETS / "F00_manifest.json").read_text())
    path = ASSETS / name
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == manifest[name], (path, actual)
    return path


@pytest.fixture(scope="session")
def numerical_dependencies(tmp_path_factory):
    target = tmp_path_factory.mktemp("numerical-dependencies")
    for name in ("F00_numpy-2.2.6-cp313-cp313-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
                 "F00_tokenizers-0.21.4-cp39-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"):
        with zipfile.ZipFile(checked_asset(name)) as wheel:
            wheel.extractall(target)
    sys.path.insert(0, str(target))
    importlib.invalidate_caches()
    import numpy
    import tokenizers
    assert numpy.__version__ == "2.2.6"
    assert tokenizers.__version__ == "0.21.4"
    yield
    sys.path.remove(str(target))


@pytest.fixture(scope="session")
def openssl_environment(tmp_path_factory):
    target = tmp_path_factory.mktemp("openssl-build-dependency")
    for name in ("F00_libssl-dev_3.0.13-0ubuntu3.16_amd64.deb",
                 "F00_libssl3t64_3.0.13-0ubuntu3.16_amd64.deb"):
        result = run_command(["dpkg-deb", "-x", checked_asset(name), target], cwd=target, timeout=30)
        assert result.returncode == 0, (result.stdout, result.stderr)
    shutil.copytree(target / "usr/include/x86_64-linux-gnu/openssl",
                    target / "usr/include/openssl", dirs_exist_ok=True)
    return {"OPENSSL_INCLUDE_DIR": str(target / "usr/include"),
            "OPENSSL_LIB_DIR": str(target / "usr/lib/x86_64-linux-gnu"),
            "OPENSSL_STATIC": "1"}
