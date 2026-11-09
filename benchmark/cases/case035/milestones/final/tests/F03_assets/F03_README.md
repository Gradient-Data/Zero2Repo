# Offline Secret Service fixture

These unmodified Ubuntu binary packages provide a real GNOME Keyring service and its otherwise missing shared libraries. The acceptance image already supplies D-Bus and the Python SecretStorage client. Source URLs and SHA-256 digests are recorded in F03_manifest.json. Package copyright and license notices remain inside the archives under usr/share/doc.

F03_helpers.py verifies and extracts the archives into a temporary directory, starts a private session bus and a foreground secrets-only daemon as the current test user, then stops both owned processes. No system installation or network access occurs during acceptance runs. All keyring collections, sockets and encrypted storage are temporary and isolated.

The service is test infrastructure, independent of the product. It is not a replacement keyring backend, product patch or generated fake secret store. Secret entries are observed through the public Secret Service API, without assuming product service names or account attributes.
