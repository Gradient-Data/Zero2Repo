#!/bin/sh
set -eu
export DEBIAN_FRONTEND=noninteractive
# Ubuntu packages come from Canonical's official archive snapshot 20261107T004914Z
# (the time this environment was recorded), so apt resolves the same versions
# on any host.
SNAPSHOT=20261107T004914Z
apt-get --snapshot "$SNAPSHOT" -o Acquire::Retries=5 -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60 update
apt-get --snapshot "$SNAPSHOT" -o Acquire::Retries=5 -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60 install -y --no-install-recommends ffmpeg=7:6.1.1-3ubuntu5 libsndfile1=1.2.2-1ubuntu5.24.04.1 libarchive-tools=3.7.2-2ubuntu0.9
/opt/conda/bin/python /env-assets/install.py
printf '[global]\nno-index = true\nfind-links = /opt/wheelhouse\n' > /opt/conda/pip.conf
chmod -R a+rX /opt/conda /opt/wheelhouse /opt/env-recipe
