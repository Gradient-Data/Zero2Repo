# Pinned product build version

`product-version.json` records the missing build input for source copies that
intentionally omit Git metadata. It is a lock for the clean commit in both
`source/manifest.json` and `source/recipe.lock.json`, not a fallback version.

At commit `e210f9245faa716248d8f0d698aef4e12bf68507`, the repository's configured
`git describe --dirty --tags --long --match v*` gives
`v3.4.1-23-ge210f924`. The locked setuptools-scm backend derives the clean PEP 440
version `3.4.2.dev23+ge210f924`. Reproduce in an intact clean checkout with:

```sh
git describe --dirty --tags --long --match 'v*'
python3 -c 'from setuptools_scm import get_version; print(get_version(root=".", git_describe_command="git describe --dirty --tags --long --match v*"))'
```

The installer writes an interpreter startup `.pth` file into the PATH interpreter's
site-packages. This supplies the SCM input to subsequent pip
processes, including the harness's warm installation, whose environment cannot
inherit exports made by the installer subprocess. The environment is dedicated to the pinned product; the
override also reaches backend subprocesses that do not provide a distribution
name to setuptools-scm. Dependencies are installed as locked wheels before this
startup configuration is written. Both recorded offline build commands invoke the installed build helper, which
reads the same lock and explicitly supplies that input for a fresh metadata-free
source copy. No product source or installed product is needed to provision it.

When changing the pinned commit, rederive this version with the locked backend
from that clean commit, update the version lock,
and rebuild the environment. Do not use the working tree's dirty version.

# Standalone runtime dependencies and submitted product builds

`dependencies.json` also locks Pydantic and JSON Schema validation, and the
Starlette/Uvicorn HTTP runtime, including their transitive dependencies. The
additional wheel URLs, versions and SHA-256 hashes come from the pinned
repository's root and independent-package `uv.lock` files. These dependencies
are installed by the same hash-verifying installer from the base image; no
product implementation is installed by that step. Existing dependency locks
are unchanged.

The independent distributions have their own VCS tags and use the
`no-local-version` scheme. At the pinned clean commit their describe outputs are
`velnora_metadata-v0.5.0-148-ge210f924` and
`velnora_http_server-v0.1.0-163-ge210f924`; the locked backend yields
`0.5.1.dev148` and `0.1.1.dev163`. Their versions are recorded by project suffix in `product-version.json`. The
installer copies this lock and `build_product.py` into `/opt/runtime`, without
reading or installing product source. At build time the helper reads the root
project name and discovers child projects from `packages/*/pyproject.toml`. Each
required suffix must match exactly one declared distribution named after the
root project; missing or duplicate projects fail the build. It derives each
distribution-specific SCM variable from that actual name, so the shared recipe
works with both the original source layout and the neutral source layout. Only
the root SCM input is installed at interpreter startup; child inputs belong to
the build subprocess and are never tied to one tree's spelling. The startup
input preserves explicit subprocess inputs. Because Hatch's VCS backend may
call setuptools-scm without a distribution name, each project builds in a
separate pip subprocess with both the generic and distribution-specific input
set to that project's locked version. Neither layout
requires changing the read-only original or installing placeholder projects.

Both recipe build commands build the root distribution and the metadata and
HTTP distributions from the supplied product tree into `.codingbench-site`.
This target is inside the built product, so it survives the separate build
and read-only test containers. Installing into the build container's global
site-packages alone would lose those installations when that container exits.
The test command sets `PYTHONPATH=/app/.codingbench-site`, where the harness
mounts the built product. The same absolute path is inherited by Python
subprocesses, including ones with a different working directory. Thus tests
load the current submission and its distribution metadata rather than any
product previously installed in the environment image. Build failures remain
fatal; there is no import fallback.

The existing HTTP acceptance tests also exercise Unix-domain sockets through
HTTPX. `dependencies.json` locks `httpx==0.28.1` and `httpcore==1.0.9` using the
wheel records in `packages/velnora-http-server/uv.lock`. Their required dependencies
AnyIO, certifi, h11 and idna are already locked in the shared environment. The
installer provisions this complete client dependency closure before offline
tests, without relying on pip's dependency resolution or an image preinstall.

# Real local S3 runtime

The normal environment installation also runs `install_s3.py`. It installs
MinIO `RELEASE.2025-04-22T22-12-26Z` from its official GitHub release into
`/usr/local/bin/minio`, on the judge user's PATH. `s3-server.lock.json` pins
the artifact URL, version, architecture and SHA-256 from the publisher's
checksum file. Downloads and integrity failures abort installation. The locked
Linux x86_64 Go executable is statically linked: it needs no dynamic libraries,
service manager, root privileges, external account or nested container at run
time. Python S3 clients remain locked in `dependencies.json`. Installation
fetches dependencies with network access; tests use only the installed assets
offline. No product distribution is supplied by the S3 installer.

Tests start their own foreground server as `cbagent`. Choose an available
unprivileged loopback port, a writable temporary data directory, and explicit
local credentials (at least 3 characters for the user and 8 for the password).
For example, with caller-supplied `S3_TEST_PORT`, `S3_TEST_ACCESS_KEY` and
`S3_TEST_SECRET_KEY`:

```python
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

port = int(os.environ["S3_TEST_PORT"])
assert 1024 <= port <= 65535
endpoint = f"http://127.0.0.1:{port}"
env = dict(os.environ, MINIO_ROOT_USER=os.environ["S3_TEST_ACCESS_KEY"],
           MINIO_ROOT_PASSWORD=os.environ["S3_TEST_SECRET_KEY"], MINIO_BROWSER="off")
with tempfile.TemporaryDirectory() as data, tempfile.TemporaryFile() as log:
    process = subprocess.Popen(
        ["minio", "server", data, "--address", f"127.0.0.1:{port}"],
        env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 30
        while True:
            if process.poll() is not None:
                raise RuntimeError("MinIO exited during startup")
            try:
                with urllib.request.urlopen(endpoint + "/minio/health/ready", timeout=1) as reply:
                    assert reply.status == 200
                break
            except urllib.error.URLError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)
        # Perform client operations here, before the finally block stops MinIO.
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        log.seek(0)
        print(log.read().decode("utf-8", errors="replace"))
```

Use that loopback URL as the clients' explicit endpoint, the same credentials,
region `us-east-1`, and path-style bucket addressing. Create buckets through an
S3 client before using them. A process-based fixture should poll readiness for
at most 30 seconds, preserve server output on failure, and in `finally` send
SIGTERM and wait up to 10 seconds (then SIGKILL and wait if needed). Delete its
temporary storage only after the process exits. Each test owns its process,
port and storage; there is no shared daemon or preseeded object data.

# Judge interpreter alignment

The judge launches its isolated pytest process with `python3` from PATH.
Installation and both offline commands therefore use that same interpreter,
without creating a separate virtual environment. The complete hash-locked
third-party closure is installed into its system site-packages, including
JSON Schema validation and Pydantic. The pip configuration is written under
that interpreter's prefix so subsequent offline builds cannot use an index.
`/opt/runtime` holds only portable build helpers and version inputs.
Installation still downloads and verifies every selected wheel before
installing; no existing image package is accepted as proof of provisioning.
