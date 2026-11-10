#!/bin/sh
set -eu

python3 -m pip install --disable-pip-version-check --no-cache-dir --retries 5 --timeout 60 --index-url https://pypi.org/simple/ --require-hashes -r /env-assets/requirements.txt
sh /env-assets/install-browser.sh
