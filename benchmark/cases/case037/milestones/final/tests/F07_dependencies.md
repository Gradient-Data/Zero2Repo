# feature: F07

F07_kerberos.tar.gz contains unmodified Ubuntu 24.04 amd64 MIT Kerberos tools,
KDC database plugin, dependency libraries, and upstream license notices. Packages
were downloaded from https://archive.ubuntu.com/ubuntu/pool/ and extracted with
dpkg-deb -x, then archived with tar. No product code, realm database, keys,
tickets, expected answers, or test responses are included. The fixture generates
fresh identities and credentials in a temporary directory, runs an unprivileged
loopback KDC, and shuts it down after use. Execution needs no network, root,
installation, or image modification. Missing dependencies fail directly.

The tools use the original image's existing MIT Kerberos libraries and standard
system libraries. The bundled database plugin directory and dependency library
directory are explicitly selected for the isolated KDC processes.

Upstream packages and SHA-256:

- krb5-admin-server_1.20.1-6ubuntu2.10_amd64.deb: 091d2d13ec52da92233920b275a67bc289c9ceddcb0812ea79f7192b70c7720b
- krb5-kdc_1.20.1-6ubuntu2.10_amd64.deb: 478584ff77c02b3f14eee9a89449946742b6647550e2a9ba583eec0934edc100
- krb5-user_1.20.1-6ubuntu2.10_amd64.deb: 2bc9c849f4f9c425eae7c438b9e56546d97e346c328e4d651d9624f8cfa18d23
- libevent-2.1-7t64_2.1.12-stable-9ubuntu2.2_amd64.deb: 083ced6efb23476cb4de4e441b741af02db5653e67fa7fcd6cf7e5f7b78f6101
- liblmdb0_0.9.31-1build1_amd64.deb: 3439a5b9fd358df1619f7dca2d611195f22a7d7d83a3a968428ac1440f713b4e
- libverto-libevent1t64_0.3.1-1.2ubuntu3_amd64.deb: c831b05794c3c8210a2138fc833248d5d28974e9da62d7df19f9df8b0eaf9c3d
- libverto1t64_0.3.1-1.2ubuntu3_amd64.deb: 42ef3987828f5aa245778c1567cd3bd6aa9a2932cd3e8785fe8801d596d141ed

Archive SHA-256: 83bfd3bc6b234cd251668fc6a9833e36cecb03244c33243deeb71e7673ac352d
