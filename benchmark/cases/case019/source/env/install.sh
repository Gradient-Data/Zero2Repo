#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
# Ubuntu packages come from Canonical's official archive snapshot 20261107T013054Z
# (the time this environment was recorded), so apt resolves the same versions
# on any host.
SNAPSHOT=20261107T013054Z
apt-get --snapshot "$SNAPSHOT" update -o Acquire::Retries=3
apt-get --snapshot "$SNAPSHOT" install -y --no-install-recommends python3-venv libcairo2
python3 -m venv /opt/venv
mkdir -p /opt/wheels
/opt/venv/bin/python /env-assets/fetch.py
/opt/venv/bin/python -m pip install --no-deps --no-index --find-links=/opt/wheels --require-hashes -r /opt/wheels/requirements.txt
printf '[global]\nno-index = true\nfind-links = /opt/wheels\ndisable-pip-version-check = true\n' > /opt/venv/pip.conf
