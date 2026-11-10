#!/bin/sh
set -eu
export DEBIAN_FRONTEND=noninteractive
# Ubuntu packages come from Canonical's official archive snapshot 20261107T033703Z
# (the time this environment was recorded), so apt resolves the same versions
# on any host.
SNAPSHOT=20261107T033703Z
apt-get --snapshot "$SNAPSHOT" -o Acquire::Retries=5 -o Acquire::https::Timeout=60 update
apt-get --snapshot "$SNAPSHOT" -o Acquire::Retries=5 -o Acquire::https::Timeout=60 install -y --no-install-recommends libgirepository1.0-dev=1.80.1-1 libcairo2-dev=1.18.0-3build1 ninja-build=1.11.1-2 gir1.2-glib-2.0=2.80.0-6ubuntu3.10
# Install into the same PATH-selected interpreter used by the isolated judge.
python3 /env-assets/fetch.py
python3 -m pip install --no-index --find-links=/opt/wheels --require-hashes --no-deps -r /env-assets/requirements.txt
# Build bindings for the selected Python ABI. GLib metadata needs Cairo first.
python3 -m pip install --no-index --find-links=/opt/wheels --require-hashes --no-deps --no-build-isolation -r /env-assets/cairo-requirements.txt
python3 -m pip install --no-index --find-links=/opt/wheels --require-hashes --no-deps --no-build-isolation -r /env-assets/native-requirements.txt
python3 -m pip check
chmod -R a+rX /opt/wheels
# Fetch SHA-256-locked runtime libraries and browsers only during image creation.
python3 /env-assets/fetch.py /env-assets/browser-native.json /opt/browser-debs
dpkg --unpack /opt/browser-debs/*.deb
dpkg --configure --pending
python3 /env-assets/fetch.py /env-assets/browsers.json /opt/browser-archives
python3 /env-assets/install-browser.py
chmod -R a+rX /opt/ms-playwright
