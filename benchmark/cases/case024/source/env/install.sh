#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
judge_python=$(command -v python3)
# Ubuntu packages come from Canonical's official archive snapshot 20261107T055532Z
# (the time this environment was recorded), so apt resolves the same versions
# on any host.
SNAPSHOT=20261107T055532Z
apt-get --snapshot "$SNAPSHOT" update -o Acquire::Retries=3
apt-get --snapshot "$SNAPSHOT" install -y --no-install-recommends python3.12-venv python3.12-dev libpq-dev postgresql openjdk-17-jre-headless
/usr/bin/python3.12 -m venv /opt/runtime
/opt/runtime/bin/python /env-assets/fetch.py
/opt/runtime/bin/python -m pip install --no-index --find-links=/opt/packages setuptools==80.9.0 uv_build==0.9.22
/opt/runtime/bin/python -m pip install --no-index --find-links=/opt/packages --no-build-isolation --require-hashes -r /env-assets/requirements.txt
/opt/runtime/bin/python /env-assets/install_glue.py
# Keep product console scripts on the standard PATH, while its packages remain
# visible to the prepared interpreter. The product is installed only at build.
/opt/runtime/bin/python - <<'PYTHON'
from pathlib import Path
import sysconfig

runtime_site = Path(sysconfig.get_path("purelib"))
product_paths = sysconfig.get_paths(
    scheme="posix_prefix", vars={"base": "/usr/local", "platbase": "/usr/local"}
)
paths = dict.fromkeys(product_paths[key] for key in ("purelib", "platlib"))
(runtime_site / "product-prefix.pth").write_text("".join(path + "\n" for path in paths))
PYTHON
chmod -R a+rX /opt/runtime /opt/packages /opt/glue
# A launcher preserves virtual-environment discovery; a symlink outside the
# environment would select the base interpreter without its site-packages.
install -T -m 0755 /env-assets/python3 "$judge_python"
python3 -c 'import sys, dateutil.parser, pytest; assert sys.prefix == "/opt/runtime", sys.prefix; print(sys.executable, sys.version, dateutil.parser.__file__, pytest.__file__)'
