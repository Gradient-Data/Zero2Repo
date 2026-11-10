# Build version provenance

The source revision pinned by both manifest.json and recipe.lock.json is
9579be7de41a607edadaf5d43340aed6a7ad70a9. Its clean Git checkout produces
`4.2.6.dev94+g9579be7d` with the pinned setuptools-scm 8.1.0.

Both source packaging declarations retain a dynamic version. Each configures
setuptools-scm to write a generated version module inside its own package:
the original distribution uses its original package, and the renamed reference
uses its renamed package. Neither overrides setuptools-scm's default
`guess-next-dev` version scheme or `node-and-date` local scheme.

Reproduction on the unmodified checkout, with no SETUPTOOLS_SCM overrides:

```sh
git rev-parse HEAD
# 9579be7de41a607edadaf5d43340aed6a7ad70a9
git status --porcelain
# empty: clean checkout
git describe --tags --long --dirty
# 4.2.5-94-g9579be7d
git rev-parse '4.2.5^{}'
# 69907e4ed532e02014570ef0586d4418e3aac280
python3 -c 'from setuptools_scm import get_version; print(get_version(root="."))'
# 4.2.6.dev94+g9579be7d
```

The default scheme increments the last release component and includes the
94-commit distance; the local component records the abbreviated commit. A clean
checkout adds no dirty date. This is a version derived from the pinned revision,
not a fallback version.

Both canonical build commands supply that value through setuptools-scm's
package-independent `SETUPTOOLS_SCM_PRETEND_VERSION` input, scoped to the single
project installation command. The recipe warm-build selects the unchanged
original distribution through the manifest's repository selection; subsequent
offline builds use the renamed reference distribution. A distribution-specific
input for the renamed package cannot supply the original's dynamic version.
The package-independent input supplies the same revision-derived version to both
identities without changing either packaging declaration or product behavior.

The identical manifest and locked commands do not depend on Git metadata in
delivered source, an export from the installation shell, or a previously built
image. The install assets continue to provision the pinned packaging tools
without project source. No default version or error suppression is introduced.
If the pinned revision or setuptools-scm rules change, derive and update the
version and this provenance together in both commands.
