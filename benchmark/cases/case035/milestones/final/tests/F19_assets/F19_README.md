# feature: F19

These are unmodified public release wheels used as local repository inputs for
real, offline runtime maintenance. The manifests record original filenames,
public provenance and SHA-256 digests. Acceptance tests materialize the original
wheel filenames in a temporary directory and verify every digest before use.

The current product wheel is built from the supplied product by the reused
runtime provisioning helper. The historical product release allows an actual
version change with independent installed-file and startup observations.
All installations and updates occur in disposable virtual environments.

Historical stable and prerelease wheels and their genuine dependencies also
allow the same update constraint to distinguish default stable selection from
explicit preview selection without fabricating release metadata.
