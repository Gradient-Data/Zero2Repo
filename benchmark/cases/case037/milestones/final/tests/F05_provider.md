# Real PKCS#11 provider fixture

F05_softhsm.tar.gz contains the SoftHSMv2 2.7.0 provider, its token initialization utility, license, provenance, and a source patch. It contains no token database, keys, certificates, expected product answers, or product code. The fixture is extracted into a fresh writable temporary directory; all identity material is generated during execution. Missing or incompatible assets fail directly.

Upstream source: https://codeload.github.com/softhsm/SoftHSMv2/tar.gz/refs/tags/2.7.0 . The archive's PROVENANCE.json records its source checksum and build commands. Binaries were built for the case's Ubuntu 24.04 x86_64 original image, using its OpenSSL backend. They depend on the image's existing standard system libraries. Execution needs no network, package installation, root privileges, or image change.

The provider patch exposes CKA_EC_POINT on imported private EC objects, alongside the usual private EC attributes. This allows the reference public loader to read a provider-supplied public point from the private object. The patch is general to imported EC identities, contains no scenario values, and does not alter token selection, PIN validation, cryptographic signing, or key-ID attributes. Signing remains the upstream SoftHSM/OpenSSL implementation and is independently verified using cryptography. The provider remains a real cryptographic service, not a stub or prerecorded response source.

The reference loader uses CKA_OBJECT_ID rather than CKA_ID for its key-ID selector. The fixture does not alias those attributes or hide that bug. Successful standard key-ID matching is outside the retained selector promise; the Stage B report records the baseline limitation and prospective source fix. Token label, serial, key label, absent identifiers, certificate selection, and signing are exercised against the real provider.


F05_p11kit.tar.gz contains unmodified Ubuntu 24.04 p11-kit 0.25.3 binaries,
client module, library, licenses and package checksums. Its foreground RPC
service exposes URI-selected initialized SoftHSM tokens over a temporary UNIX
socket. Selection is the real service's public token-sharing capability; token
operations, PIN validation and signing still execute in SoftHSM. This supplies a
provider whose advertised slots all contain usable tokens, without changing the
product's handling of uninitialized slots. No network or root access is needed.
