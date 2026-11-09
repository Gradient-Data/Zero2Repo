# feature: F06

The independent transport observers run Paramiko in separate Python processes.
F06_peer.py extends only that external peer with documented SSH algorithm and
GSSAPI carriers backed by cryptography and a real local MIT Kerberos realm.
Protocol inputs, independent exchange hashes and external signature verification
never come from the product implementation.
Its peer-only packet observer records verified incoming SSH message types and
clear EtM packet lengths. It never reads or patches the product's implementation,
clock, key material, or counters. The peer's own rekey thresholds are raised above
the workload so it cannot initiate the exchange being measured.

These unmodified upstream wheels are extracted to a temporary directory at run
time. Their licenses and distribution metadata are inside the archives. Tests
require no network and do not install packages into the judge environment.

| Asset | Upstream distribution | SHA-256 |
| --- | --- | --- |
| F06_paramiko.whl | paramiko-3.5.1-py3-none-any.whl from PyPI | 43b9a0501fc2b5e70680388d9346cf252cfb7d00b0667c39e80eb43a408b8f61 |
| F06_pynacl.whl | pynacl-1.6.2-cp38-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.whl from PyPI | 22de65bb9010a725b0dac248f353bb072969c94fa8d6b1f34b87d7953cf7bbe4 |

Cryptography, bcrypt, cffi, and their dependencies are supplied by the existing
original image. Missing dependencies or invalid archives fail visibly.

SNTRUP observations require the original image's liboqs.so.5 and its real
OQS_KEM_sntrup761 keypair, encapsulation and decapsulation functions. The
independent peer uses these through ctypes, with cryptography's X25519 and
SHA-512, to authenticate and exchange application bytes under both wire names
in both product roles. An absent library or failed operation raises directly.
