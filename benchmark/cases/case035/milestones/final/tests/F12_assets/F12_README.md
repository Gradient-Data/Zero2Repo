# Offline runtime metadata

These unmodified PyPI wheels supply metadata for dependencies that the
product resolver considers across platforms, even when the running interpreter
does not install those dependencies. The manifest records upstream URLs and
SHA-256 hashes. Tests verify each hash before serving the original wheel.
Runtime wheels come from the acceptance image's offline wheel directory; the
product wheel is built from the product tree supplied by the harness.

The wheels retain their upstream license files. No wheel is a substitute
implementation of the product or its plugin provisioning.
