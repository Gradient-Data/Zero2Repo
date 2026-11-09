"""Install locked native packages on the registered Ubuntu base image."""

import hashlib
import json
import os
import pathlib
import subprocess
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse


def installed_versions():
    result = subprocess.check_output(
        ["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\n"], text=True)
    return dict(line.split("\t") for line in result.splitlines())


def require_versions(expected):
    installed = installed_versions()
    for name, version in expected.items():
        if installed.get(name) != version:
            raise RuntimeError(
                f"Native package version mismatch for {name}: "
                f"expected {version}, found {installed.get(name)!r}")


def install_native():
    lock = json.loads(pathlib.Path(__file__).with_name("native-packages.json").read_text())
    architecture = subprocess.check_output(["dpkg", "--print-architecture"], text=True).strip()
    if architecture != lock["architecture"]:
        raise RuntimeError(f"Unsupported native architecture: {architecture}")
    # These dependencies are supplied by the registered base, not by a mutable apt index.
    require_versions(lock["base_packages"])
    cache = pathlib.Path("/opt/dependency-archives/native")
    cache.mkdir(parents=True, exist_ok=True)

    def fetch(entry):
        target = cache / pathlib.Path(urlparse(entry["url"]).path).name
        subprocess.run(
            ["curl", "--fail", "--location", "--retry", "5", "--connect-timeout", "30",
             "--speed-limit", "1024", "--speed-time", "60", "--output", str(target), entry["url"]],
            check=True)
        if hashlib.sha256(target.read_bytes()).hexdigest() != entry["sha256"]:
            raise RuntimeError("SHA256 mismatch: " + target.name)
        return str(target)

    with ThreadPoolExecutor(max_workers=4) as executor:
        archives = list(executor.map(fetch, lock["packages"]))
    # dpkg installs complete distributions (macros, headers, libraries and support files).
    # It cannot fetch unpinned dependencies; an incomplete lock fails here.
    subprocess.run(["dpkg", "--install", *archives], check=True,
                   env=dict(os.environ, DEBIAN_FRONTEND="noninteractive"))
    for entry in lock["packages"]:
        name = entry["name"] + ":" + entry["architecture"]
        version = subprocess.check_output(
            ["dpkg-query", "-W", "-f=${Version}", name], text=True)
        if version != entry["version"]:
            raise RuntimeError(f"Installed version mismatch for {name}: {version}")



if __name__ == "__main__":
    install_native()
