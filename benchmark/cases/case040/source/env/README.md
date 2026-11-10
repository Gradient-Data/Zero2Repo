# Interpreter alignment

Installation, offline builds and the judge use the first `python3` on PATH.
The declared base currently provides CPython 3.13 in `/opt/conda`. Dependencies
are installed into its normal site-packages, visible under isolated mode (`-I`)
and to the unprivileged test user. No alternate virtual environment is created.

`packages.json` records artifact URLs and SHA-256 digests. The requirement files
pin those same artifacts. Coverage and zope.interface use CPython 3.13 wheels;
PyZMQ 26.2.1 provides a compatible wheel and satisfies the product's minimum.
Cairo and GLib Python bindings are built for the selected interpreter from pinned
sources, using pinned Meson tools and Ubuntu development/runtime libraries.
Cairo must be installed before GLib binding metadata generation. Distribution
Python 3.12 bindings are not injected into Python 3.13's search path.

Installation fetches declared artifacts with network access, verifies their
hashes and installs without dependency resolution. Native binding builds disable
build isolation. Subsequent product builds disable indexes, dependency resolution
and build isolation. The pytest template explicitly loads the installed plugins
because the judge disables autoload; it clears the product's default coverage
and doctest options for the supplied benchmark tests. The revision-derived
version is documented in `version-provenance.md`.

# Offline browser automation

Playwright 1.51.0 uses Chromium 134.0.6998.35 (revision 1161), including
its headless shell, and FFmpeg revision 1011. The Playwright wheel's bundled
`browsers.json` defines these revisions. `browsers.json` here pins the exact
Linux x86-64 upstream archive URLs, byte sizes and SHA-256 digests. Only text
dependency declarations and installer scripts are shipped as environment inputs.
During network-enabled image installation, `fetch.py` downloads these versioned
archives from the browser CDN and verifies both size and SHA-256 before
`install-browser.py` extracts them. No vendored or encoded browser payload is
required. `browser-native.json` pins the
Ubuntu runtime packages and the additional dependency closure relative to the
declared base and existing binding installation, with archive hashes from
Ubuntu package metadata. The runtime packages are fetched and checked at installation time,
then dpkg unpacks and configures only these verified local archives. No network
resolver runs for the browser runtime libraries. Existing
Python, Cairo and GLib provisioning remains in place.

Browser archives are extracted to `/opt/ms-playwright` with executable modes
preserved and resources readable by every user. A system site-packages `.pth`
file sets `PLAYWRIGHT_BROWSERS_PATH` to this directory if the caller has not
specified one. This applies to the PATH-selected Python without a login shell,
without a user cache and under Python isolated mode. It does not alter browser
or automation code. No browser downloads occur at test time. The supported
launcher also declares this path explicitly in the manifest and recipe lock.

The container probe launches real Chromium with `--no-sandbox` as the
unprivileged judge user; it does not require a display server or GPU. This
provisions browser observation only, not physical LCD hardware or other
platform runtimes.
