# Environment installation

Run `sh /env-assets/install.sh` as root in the Ubuntu 24.04 pipeline base.
Installation needs only this directory mounted read-only at `/env-assets`;
no product checkout or host cache is used. Python dependency hashes are
preserved in `requirements.txt`.

## Browser runtime

`browser.json` pins native Debian bookworm amd64 Chromium packages and their
SHA-256 digests from the distribution's package index. The product does not
pin a browser version; this is independent test-runtime tooling. The two
additional Debian codec libraries provide the browser's required library
ABIs alongside Ubuntu's native libraries. No Debian package repository is
added to APT. Other runtime dependencies and fonts are resolved through the
Ubuntu 24.04 repository, explicitly using the Alibaba Cloud mirror.

`install-browser.py` downloads and verifies all four pinned packages from
the Alibaba Cloud Debian mirror before installing them. Download failures,
checksum mismatches, and package installation failures stop installation.
Only text metadata and installers are shipped here; downloaded third-party
binaries remain in the environment image, not in these assets.

The browser is discoverable as `chromium` on PATH. Headless callers should
provide temporary writable profile storage with `--user-data-dir`, and use
`--headless --no-sandbox --disable-dev-shm-usage` in the judge container.
The browser requires no desktop session, external service, credentials,
or network access to execute local or data-URL JavaScript pages.
