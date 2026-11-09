import hashlib
import json
import pathlib
import subprocess
import zipfile
from urllib.parse import urlparse

from native import install_native


def run(*args):
    subprocess.run(args, check=True)


install_native()

cache = pathlib.Path("/opt/dependency-archives")
cache.mkdir(parents=True, exist_ok=True)
entries = json.loads(pathlib.Path("/env-assets/dependencies.json").read_text())
tools = json.loads(pathlib.Path("/env-assets/tools.json").read_text())
for entry in entries + tools:
    target = cache / pathlib.Path(urlparse(entry["url"]).path).name
    run("curl", "--fail", "--location", "--retry", "5", "--connect-timeout", "30",
        "--speed-limit", "1024", "--speed-time", "60", "--output", str(target), entry["url"])
    if hashlib.sha256(target.read_bytes()).hexdigest() != entry["sha256"]:
        raise RuntimeError("SHA256 mismatch: " + target.name)
run("python3", "-m", "venv", "/opt/runtime")
python = "/opt/runtime/bin/python"
bootstrap = [str(cache / pathlib.Path(urlparse(e["url"]).path).name)
             for e in entries if e["name"].lower() in {"setuptools", "wheel", "packaging"}]
run(python, "-m", "pip", "install", "--no-index", "--no-deps", *bootstrap)
archives = [str(cache / pathlib.Path(urlparse(e["url"]).path).name) for e in entries]
run(python, "-m", "pip", "install", "--no-index", "--no-deps", "--no-build-isolation", *archives)

for tool in tools:
    archive = cache / pathlib.Path(urlparse(tool["url"]).path).name
    destination = pathlib.Path("/opt") / (tool["name"] + "-" + tool["version"])
    destination.mkdir(parents=True, exist_ok=True)
    # Deploy the native tool distribution, without its Python launcher package.
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            if not member.filename.startswith(tool["archive_prefix"]) or member.is_dir():
                continue
            relative = pathlib.PurePosixPath(member.filename).relative_to(tool["archive_prefix"])
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.read(member))
            target.chmod(0o755 if member.external_attr >> 16 & 0o111 else 0o644)
    for executable in (destination / "bin").iterdir():
        (pathlib.Path("/opt/runtime/bin") / executable.name).symlink_to(executable)
