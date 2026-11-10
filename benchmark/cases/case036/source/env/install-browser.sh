#!/bin/sh
set -eu

# Ubuntu's chromium-browser package is a Snap launcher, not an offline browser.
# Install pinned native Chromium packages and resolve runtime libraries on Ubuntu.
# Ubuntu packages come from Canonical's official archive snapshot 20261107T060747Z
# (the time this environment was recorded), so apt resolves the same versions
# on any host.
SNAPSHOT=20261107T060747Z
apt-get --snapshot "$SNAPSHOT" -o Acquire::Retries=5 -o Acquire::http::Timeout=60 update
SNAPSHOT="$SNAPSHOT" python3 /env-assets/install-browser.py
chromium --version
