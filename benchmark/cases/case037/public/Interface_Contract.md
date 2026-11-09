# Interface Contract

The Python package is imported as `velnora`. Its package directory is `velnora/`. Public asynchronous calls are used from a running Python event loop; their results are obtained with `await` or an asynchronous context manager where specified.

Binary API results are Python `bytes`; text results are Python `str`. Files are named by caller-supplied paths. Session `stdout` and `stderr` denote remote streams, separate from the Python application's console. The notation `=...` marks an optional parameter.

SSH binary forms use network-byte-order unsigned 32-bit and 64-bit integers. An SSH string is a uint32 byte length followed by that many bytes; an SSH mpint is a length-prefixed signed big-endian integer. Text fields in SSH key, certificate and signature carriers use UTF-8. Public key blobs have the standard SSH algorithm field followed by the algorithm's public parameters; signature blobs have an algorithm SSH string followed by a signature SSH string.

TCP transport uses SSH identification lines `SSH-2.0-<software>\r\n` and RFC 4253 packets. Packet fields are `packet_length` (uint32), `padding_length` (byte), payload and padding, with the negotiated authentication tag. The payload starts with its message-number byte. KEXINIT (20) carries a 16-byte cookie, SSH name-lists for key exchange, host identity, client-to-server and server-to-client encryption, integrity and compression, two language name-lists, a boolean and reserved uint32. NEWKEYS is 21. User authentication request (50) carries SSH strings for username, service and method followed by method-specific fields; service is `ssh-connection`. Authentication failure (51) carries method name-list and partial-success boolean; success is 52; banner (53) carries message and language strings. GSSAPI method labels are `gssapi-keyex` and `gssapi-with-mic`; their MIC and mechanism/token carriers follow RFC 4462. Global request (80) carries request-name string, want-reply boolean and request data; success/failure message numbers are 81/82. `keepalive@openssh.com` has no request data. `hostkeys-00@openssh.com` and `hostkeys-prove-00@openssh.com` carry sequences of public-key SSH strings; proof success carries a sequence of signature SSH strings. Each possession-proof signature signs three concatenated SSH strings: `hostkeys-prove-00@openssh.com`, the transport session identifier, and the proved public-key blob. Compression labels are `none`, `zlib` and `zlib@openssh.com`; SSH public-key authentication signatures use the RFC 4252 signed-request carrier. X.509 SSH identity blobs use the RFC 6187 algorithm string, certificate count, DER certificate strings, OCSP response count and response strings.

Algorithm selector spellings include `3des-cbc`, `aes128-cbc`, `aes128-ctr`, `aes128-gcm@openssh.com`, `aes192-cbc`, `aes192-ctr`, `aes256-cbc`, `aes256-ctr`, `aes256-gcm@openssh.com`, `arcfour`, `arcfour128`, `arcfour256`, `blowfish-cbc`, `cast128-cbc`, `chacha20-poly1305@openssh.com`, `curve25519-sha256`, `curve25519-sha256@libssh.org`, `curve448-sha512`, `diffie-hellman-group-exchange-sha1`, `diffie-hellman-group-exchange-sha224@ssh.com`, `diffie-hellman-group-exchange-sha256`, `diffie-hellman-group-exchange-sha384@ssh.com`, `diffie-hellman-group-exchange-sha512@ssh.com`, `diffie-hellman-group1-sha1`, `diffie-hellman-group14-sha1`, `diffie-hellman-group14-sha224@ssh.com`, `diffie-hellman-group14-sha256`, `diffie-hellman-group15-sha256@ssh.com`, `diffie-hellman-group15-sha384@ssh.com`, `diffie-hellman-group15-sha512`, `diffie-hellman-group16-sha384@ssh.com`, `diffie-hellman-group16-sha512`, `diffie-hellman-group17-sha512`, `diffie-hellman-group18-sha512`, `ecdh-sha2-1.3.132.0.10`, `ecdh-sha2-nistp256`, `ecdh-sha2-nistp384`, `ecdh-sha2-nistp521`, `ecdsa-sha2-1.3.132.0.10`, `ecdsa-sha2-nistp256`, `ecdsa-sha2-nistp384`, `ecdsa-sha2-nistp521`, `gss-1.3.132.0.10-sha256`, `gss-curve25519-sha256`, `gss-curve448-sha512`, `gss-gex-sha1`, `gss-gex-sha256`, `gss-group1-sha1`, `gss-group14-sha1`, `gss-group14-sha256`, `gss-group15-sha512`, `gss-group16-sha512`, `gss-group17-sha512`, `gss-group18-sha512`, `gss-nistp256-sha256`, `gss-nistp384-sha384`, `gss-nistp521-sha512`, `hmac-md5`, `hmac-md5-96`, `hmac-md5-96-etm@openssh.com`, `hmac-md5-etm@openssh.com`, `hmac-sha1`, `hmac-sha1-96`, `hmac-sha1-96-etm@openssh.com`, `hmac-sha1-etm@openssh.com`, `hmac-sha2-256`, `hmac-sha2-256-96`, `hmac-sha2-256-96-etm@openssh.com`, `hmac-sha2-256-etm@openssh.com`, `hmac-sha2-512`, `hmac-sha2-512-96`, `hmac-sha2-512-96-etm@openssh.com`, `hmac-sha2-512-etm@openssh.com`, `hmac-sha224@ssh.com`, `hmac-sha384@ssh.com`, `mlkem1024nistp384-sha384`, `mlkem768nistp256-sha256`, `mlkem768x25519-sha256`, `rsa-sha2-256`, `rsa-sha2-512`, `rsa1024-sha1`, `rsa2048-sha256`, `seed-cbc@ssh.com`, `sntrup761x25519-sha512`, `sntrup761x25519-sha512@openssh.com`, `ssh-dss`, `ssh-ed25519`, `ssh-ed448`, `ssh-rsa`, `ssh-rsa-sha224@ssh.com`, `ssh-rsa-sha256@ssh.com`, `ssh-rsa-sha384@ssh.com`, `ssh-rsa-sha512@ssh.com`, `umac-128-etm@openssh.com`, `umac-128@openssh.com`, `umac-64-etm@openssh.com`, `umac-64@openssh.com`, `x509v3-rsa2048-sha256`. GSSAPI wire key-exchange names append `-<base64-mechanism-digest>` to the corresponding selector spelling.

## `velnora`

The `velnora` module exports `ChannelListenError`, `ChannelOpenError`, `ConfigParseError`, `ConnectionLost`, `DEVNULL`, `DISC_BY_APPLICATION`, `EXTENDED_DATA_STDERR`, `HostKeyNotVerifiable`, `IllegalUserName`, `KeyEncryptionError`, `KeyExchangeFailed`, `KeyExportError`, `KeyGenerationError`, `KeyImportError`, `MACError`, `OPEN_ADMINISTRATIVELY_PROHIBITED`, `OPEN_REQUEST_PTY_FAILED`, `OPEN_REQUEST_SESSION_FAILED`, `OPEN_REQUEST_X11_FORWARDING_FAILED`, `PIPE`, `PasswordChangeRequired`, `PermissionDenied`, `ProcessError`, `ProtocolError`, `ProtocolNotSupported`, `SFTPBadMessage`, `SFTPConnectionLost`, `SFTPFailure`, `SFTPFileAlreadyExists`, `SFTPFileIsADirectory`, `SFTPInvalidHandle`, `SFTPNoSuchFile`, `SFTPNotADirectory`, `SFTPOpUnsupported`, `SFTPPermissionDenied`, `SFTPServer`, `SSHClient`, `SSHClientConnectionOptions`, `SSHClientSession`, `SSHServer`, `SSHServerConnectionOptions`, `SSHServerSession`, `SSHSubprocessProtocol`, `SSHTCPSession`, `SSHTunTapSession`, `SSHUNIXSession`, `STDOUT`, `TimeoutError`, `connect`, `connect_agent`, `connect_reverse`, `create_sshsig`, `generate_private_key`, `get_server_auth_methods`, `get_server_host_key`, `import_allowed_signers`, `import_authorized_keys`, `import_certificate`, `import_known_hosts`, `import_private_key`, `import_public_key`, `listen`, `listen_reverse`, `load_certificates`, `load_keypairs`, `load_pkcs11_keys`, `match_known_hosts`, `read_allowed_signers`, `read_authorized_keys`, `read_certificate`, `read_certificate_list`, `read_known_hosts`, `read_private_key`, `read_private_key_list`, `read_public_key`, `read_public_key_list`, `run_client`, `run_server`, `scp`, `validate_sshsig`.

## `velnora.public_key`

The `velnora.public_key` module exposes `import_certificate_chain`.

## `velnora.generate_private_key`

`generate_private_key(alg_name, **kwargs)` returns an `SSHKey`. The algorithm selector is text; the generation keywords used here are `key_size` and `exponent`, both integers. Generation refusal is `KeyGenerationError`.

## `velnora.import_private_key`

`import_private_key(data, passphrase=...)` returns an SSHKey. Input `data` is serialized private-key `bytes` or `str`. `passphrase` is `str`, `bytes` or `None`. Key input failures use `KeyImportError` or `KeyEncryptionError`.

## `velnora.import_public_key`

`import_public_key(data)` returns an SSHKey. Input `data` is serialized public-key `bytes` or `str`. Input failure uses `KeyImportError`.

## `velnora.read_private_key`

`read_private_key(filename, passphrase=...)` returns an SSHKey. `filename` is a string or path-like file path. `passphrase` is `str`, `bytes` or `None`. Key input failures use `KeyImportError` or `KeyEncryptionError`.

## `velnora.read_public_key`

`read_public_key(filename)` returns an SSHKey. `filename` is a string or path-like file path.

## `velnora.read_private_key_list`

`read_private_key_list(filename)` returns a sequence of SSHKey objects. `filename` is a string or path-like file path.

## `velnora.read_public_key_list`

`read_public_key_list(filename)` returns a sequence of SSHKey objects. `filename` is a string or path-like file path.

## `velnora.import_certificate`

`import_certificate(data)` returns an SSHCertificate. Input `data` is serialized certificate `bytes` or `str`. Input failure uses `KeyImportError`.

## `velnora.read_certificate`

`read_certificate(filename)` returns an SSHCertificate. `filename` is a string or path-like file path.

## `velnora.read_certificate_list`

`read_certificate_list(filename)` returns a list of SSHCertificate objects. `filename` is a string or path-like file path.

## `velnora.load_certificates`

`load_certificates(certlist)` accepts a sequence of serialized certificate byte strings and returns a list of `SSHCertificate` objects.

## `velnora.public_key.import_certificate_chain`

`import_certificate_chain(data)` accepts concatenated PEM certificate `bytes` and returns an `SSHX509CertificateChain`.

## `velnora.load_keypairs`

`load_keypairs(keylist, certlist=...)` returns a sequence of `SSHKeyPair` objects. `keylist` accepts key objects and `(key, certificate)` pairs; `certlist` is a sequence of certificate objects. Association failure raises `ValueError`.

## `velnora.SSHKey`

Key import and generation return `SSHKey` objects. `convert_to_public()` returns a public SSHKey. Keys support equality comparison and use in sets; `get_algorithm()` returns the algorithm name as `str`.

`export_public_key(format_name=...)` and `export_private_key(format_name=..., passphrase=..., cipher_name=..., rounds=..., ignore_few_rounds=...)` return serialized `bytes`. Format selectors are `openssh`, `rfc4716`, `pkcs1-der`, `pkcs1-pem`, `pkcs8-der` and `pkcs8-pem`. The passphrase is text or bytes; cipher names are text, rounds integer, and the rounds-warning control boolean. Export refusal raises `KeyExportError`.

OpenSSH public bytes are `<algorithm> <base64-public-blob> [<comment>]` followed by a newline. RFC 4716 bytes have `---- BEGIN SSH2 PUBLIC KEY ----` and `---- END SSH2 PUBLIC KEY ----` lines around base64 public data, with a `Comment:` header when a comment is carried. DER is binary ASN.1; PEM is base64 armor with the relevant public/private key label. PKCS#8 public data is SubjectPublicKeyInfo; traditional public DER is the RSA public-key sequence or DSA integer sequence (public value, prime, subgroup order, generator). Unencrypted PKCS#8 private data is PrivateKeyInfo; traditional private data is the RSA, DSA or EC private-key sequence. An encrypted traditional PEM carries `Proc-Type: 4,ENCRYPTED` and `DEK-Info: <CIPHER>,<hex IV>` headers using OpenSSL cipher names (for example `AES-256-CBC`); encrypted PKCS#8 data is EncryptedPrivateKeyInfo using PBES2 with the selected cipher's standard object identifier.

OpenSSH private bytes use `-----BEGIN OPENSSH PRIVATE KEY-----` and matching END armor. The decoded container is the OpenSSH `openssh-key-v1` form: magic with terminal NUL, cipher string, KDF string, KDF-options string, uint32 key count, public-key string and private-block string. The private block carries equal uint32 check values, the algorithm and private fields, comment string and successive padding bytes starting at 1. RSA private fields are mpints (modulus, exponent, private exponent, inverse coefficient, primes); DSA fields are mpints (prime, subgroup order, generator, public value, private value); ECDSA fields are curve string, encoded-point string, private-scalar mpint; EdDSA fields are public bytes and private-plus-public bytes, each as an SSH string.

The protected OpenSSH carrier uses the `bcrypt` KDF name, whose KDF options contain a salt string and uint32 round count. Authenticator-reference private fields carry the algorithm, curve and public point or raw public key, application string, flags byte, opaque handle string and reserved string before the comment. Its public blob carries the algorithm, curve/point or raw public key and application string.

`sign(data, sig_algorithm)` accepts message bytes and algorithm bytes and returns an SSH signature blob. Its signature payload is raw RSA or EdDSA signature bytes, DSA's two 20-byte unsigned integers concatenated, or ECDSA's two SSH mpints.

`get_comment()` returns `str` or `None`; `set_comment(comment)` takes `str` or `None`.

`write_public_key(filename, format_name)`, `append_public_key(filename, format_name)`, `write_private_key(filename, format_name)` and `append_private_key(filename, format_name)` address a string or path-like filename. The file contains serialized key bytes in the selected form.

`get_fingerprint(hash_name=...)` returns `<digest-label>:<encoded-digest>` as text. The label matches the digest-selector spelling without regard to case. MD5 uses hexadecimal octets separated by colons, in either letter case; SHA uses base64 with optional terminal padding. Fingerprint-request failure is `ValueError`.

`generate_user_certificate(user_key, key_id, version=..., serial=..., principals=..., valid_after=..., valid_before=..., force_command=..., source_address=..., permit_x11_forwarding=..., permit_agent_forwarding=..., permit_port_forwarding=..., permit_pty=..., permit_user_rc=...)` returns an OpenSSH certificate. The subject is an SSHKey, identifier and command text, serial/version/validity integer values, principals and source addresses sequences of text, and permissions booleans. Certificate-generation failure uses `KeyGenerationError` or `ValueError`.

`generate_host_certificate(host_key, key_id, serial=..., principals=..., valid_after=..., valid_before=...)` returns an OpenSSH certificate; the subject is an SSHKey, identifier text, serial and validity endpoints integers, and principals a sequence of text.

`generate_x509_user_certificate(user_key, subject, issuer=..., serial=..., principals=..., valid_after=..., valid_before=..., purposes=..., hash_alg=...)` and `generate_x509_host_certificate(host_key, subject, issuer=..., serial=..., principals=..., valid_after=..., valid_before=..., purposes=..., hash_alg=...)` return X.509 certificates. Subject and issuer are distinguished-name text, serial and validity values integers, principals text sequences, and purposes an OID-text sequence or `None`.

`generate_x509_ca_certificate(ca_key, subject, issuer=..., serial=..., valid_after=..., valid_before=..., ca_path_len=..., hash_alg=...)` returns an X.509 CA certificate; `ca_path_len` is an integer.

The X.509 issuance argument `hash_alg` is digest-selector text; the empty-string selector denotes signing without a separately selected digest.

## `velnora.SSHCertificate`

Certificate import and issuance return `SSHCertificate` objects. Certificates support equality and use in sets. `export_certificate(format_name=...)` returns `bytes`; `write_certificate(filename, format_name)` and `append_certificate(filename, format_name)` name string or path-like output files containing that serialization.

The certificate format selectors are `openssh`, `rfc4716`, `der` and `pem`. OpenSSH form is `<certificate-algorithm> <base64-certificate-packet> [<comment>]` with a newline; RFC 4716 uses SSH2 PUBLIC KEY armor. X.509 DER contains the certificate's public key, subject, issuer, serial, validity, subject-alternative-name, extended-key-usage and basic-constraints fields; PEM uses CERTIFICATE armor.

An OpenSSH certificate packet contains: algorithm string, nonce string, subject-public-key fields, uint64 serial, uint32 role (1 user, 2 host), identifier string, string containing principal strings, uint64 validity start/end in Unix seconds (the all-ones uint64 end represents no expiration), critical-option string map, extension string map, reserved string, issuer-public-key string, and signature string. Map entries are name/value SSH string pairs. The option names `force-command` and `source-address` have a nested SSH string value; the latter contains comma-separated networks. Permission extensions are `permit-X11-forwarding`, `permit-agent-forwarding`, `permit-port-forwarding`, `permit-pty` and `permit-user-rc`.

X.509 certificate objects expose `subject` for use with subject-pattern `matches(subject)`.

## `velnora.SSHKeyPair`

`SSHKeyPair` objects returned by key-pair loaders expose `has_cert` (boolean), `public_data` (SSH public-key or certificate packet bytes), and `get_algorithm()` (algorithm-name text). `get_comment()` returns comment text or `None`.

`set_certificate(cert)` accepts a certificate; association refusal raises `ValueError`. `set_sig_algorithm(sig_algorithm)` takes algorithm-name bytes. `sign(data)` takes message bytes and returns an SSH signature blob.

## `velnora.connect_agent`

`connect_agent(agent_path=...)` is awaitable and an asynchronous context manager yielding `SSHAgentClient`. `agent_path` is a local UNIX socket path as text or an `SSHServerConnection` for forwarded access. The local environment location is named `SSH_AUTH_SOCK`. Unavailable local access uses `OSError`; failed forwarded access uses `ChannelOpenError`.

## `velnora.SSHAgentClient`

`get_keys()` is awaited and returns a sequence of agent keypairs.

`add_keys(keylist, lifetime=..., confirm=...)` accepts private SSHKey objects or `(key, certificate)` pairs, an integer lifetime in seconds and a boolean confirmation choice. `remove_keys(keylist)` accepts agent keypairs; `remove_all()` has no arguments. These are awaitable modifications returning `None`, with refusal signaled by `ValueError`.

`lock(passphrase)` and `unlock(passphrase)` are awaitable, take text, return `None`, and signal refusal with `ValueError`.

## `velnora.SSHAgentKeyPair`

Agent keypairs expose `public_data` bytes and `get_comment()` text. `set_sig_algorithm(sig_algorithm)` accepts bytes. Await `sign_async(data)` for SSH signature bytes, or `ValueError` on refusal. Await `remove()` for modification completion.

## `velnora.load_pkcs11_keys`

`load_pkcs11_keys(provider, pin, load_certs=..., token_label=..., token_serial=..., key_label=...)` returns a sequence of keypairs with `has_cert`, `public_data`, `set_sig_algorithm` and `sign`. Provider is a shared-library path; PIN and labels text; serial bytes or text; certificate-loading choice boolean. Provider/access failures propagate as `pkcs11.PKCS11Error` or `pkcs11.PinIncorrect`.

A certificate-bearing `public_data` value is an X.509 chain packet: algorithm SSH string, uint32 certificate count, DER-certificate SSH strings, uint32 OCSP-response count and OCSP-response SSH strings.

## `velnora.import_known_hosts`

`import_known_hosts(data)` returns an `SSHKnownHosts` object. Input is document `str` or `bytes`.

## `velnora.read_known_hosts`

`read_known_hosts(filelist)` returns an `SSHKnownHosts` object. Input is a caller-selected filename.

## `velnora.import_authorized_keys`

`import_authorized_keys(data)` returns an `SSHAuthorizedKeys` object. Input is document `str` or `bytes`. Document-configuration failure uses `ValueError`.

## `velnora.read_authorized_keys`

`read_authorized_keys(filelist)` returns an `SSHAuthorizedKeys` object. Input is a caller-selected filename. Document-configuration failure uses `ValueError`.

## `velnora.import_allowed_signers`

`import_allowed_signers(data)` returns an `SSHAllowedSigners` object. Input is document `str` or `bytes`. Document-configuration failure uses `ValueError`.

## `velnora.read_allowed_signers`

`read_allowed_signers(filelist)` returns an `SSHAllowedSigners` object. Input is a caller-selected filename. Document-configuration failure uses `ValueError`.

## `velnora.match_known_hosts`

`match_known_hosts(known_hosts, host, addr, port)` accepts a loaded host-trust object and host/address text with integer port or `None`. It returns a seven-element tuple of sequences: host keys, CA keys, revoked keys, trusted X.509 certificates, revoked X.509 certificates, trusted subject patterns, revoked subject patterns. Keys and certificates support equality and sets; subject-pattern objects expose `matches(subject)` returning boolean.

## `velnora.SSHAuthorizedKeys`

`validate(key, client_host, client_addr, cert_principals, ca)` takes an SSHKey, host/address text, principal-text sequence or `None`, and a boolean CA indicator. Its result is `None` for no authorization, or a restrictions mapping with `command` as text.

`validate_x509(cert, client_host, client_addr)` returns `(restrictions, trusted_certificate)`; each tuple element may be `None`. The restrictions mapping exposes `command` text.

## `velnora.SSHKnownHosts`

Host-trust loaders return `SSHKnownHosts` objects accepted by `match_known_hosts` and the `known_hosts` connection option.

## `velnora.SSHAllowedSigners`

Allowed-signers loaders return `SSHAllowedSigners` objects accepted by `validate_sshsig`.

## `velnora.create_sshsig`

`create_sshsig(key, data, is_hashed=..., hash_name=..., namespace=..., raw=...)` returns `bytes`. Key input is an SSHKey or `(key, certificate)` pair; data is bytes or a string/path-like filename; hash and namespace are text, and hashed-input/raw-output choices booleans. Invalid signing requests raise `ValueError`.

Binary SSHSIG is `SSHSIG` magic, uint32 version, then five SSH strings: signing identity, namespace, reserved bytes, hash-algorithm name and SSH signature blob. Armored output has `-----BEGIN SSH SIGNATURE-----` and `-----END SSH SIGNATURE-----` lines around base64 binary data. The omitted `raw` argument selects the armored output form.

## `velnora.validate_sshsig`

`validate_sshsig(data, sig, principal, allowed_signers, is_hashed=...)` returns a `bool` verification result; invalid request/configuration failures use `ValueError`. Data and signature accept bytes or string/path-like filenames; principal is text. Signer input accepts document bytes, a loaded SSHAllowedSigners object, a path-like filename, or a list of filename strings. The hashed-input choice is boolean.

## `velnora.connect`

`connect(host=..., port=..., **options)` is awaitable and supports `async with`, yielding an `SSHClientConnection`. Host is text and port an integer. A connected socket may be supplied as `sock`. `config` accepts a filename or `None`. Establishment failures are raised to the caller.

Identity options: `username` and `password` are text; `client_keys` is a sequence of keys, private-key paths, or key/certificate pairs; `agent_path` is a socket-path string or `None`; `agent_identities` is a sequence of keys. `known_hosts` accepts a loaded trust object, filename, `None`, or `(trusted_keys, ca_keys, revoked_keys)`. `host_key_alias` is text and `server_host_key_algs` a sequence of algorithm names.

Authentication options: `pkcs11_pin` is token PIN text; `preferred_auth` is a sequence of method-name strings; `public_key_auth`, `kbdint_auth`, `password_auth` and `disable_trivial_auth` are booleans. `client_factory` is a zero-argument callable returning an SSHClient. `client_host_keys` is a key or public-key-path sequence; `client_host` and `client_username` are text. `client_host_keysign` accepts a boolean or the path text of an OpenSSH ssh-keysign executable. `gss_host` is service-principal text, `gss_store` a string mapping with `ccache`, and `gss_kex`, `gss_auth` and `gss_delegate_creds` are booleans.

Transport options: `kex_algs`, `encryption_algs`, `mac_algs`, `compression_algs` and `signature_algs` accept algorithm-name sequences or selection-pattern text. `connect_timeout` accepts numeric seconds, quantity text or `None`; `login_timeout`, `rekey_seconds` and `keepalive_interval` numeric seconds or quantity text; `rekey_bytes` an integer or byte-quantity text; `keepalive_count_max` an integer. Invalid option failures use `ValueError`. An establishment deadline uses `asyncio.TimeoutError`; an incomplete-login timeout uses `ConnectionLost`.

`server_host_keys_handler` is a callback receiving four sequences of SSHKey objects in positional order: added, removed, retained, revoked.

Routing options: `tunnel` is an SSHClientConnection or comma-separated jump specification `[<user>@]<host>[:<port>],...`; `proxy_command` accepts an argument sequence for a subprocess whose stdin/stdout carry SSH bytes; `family` is a socket address-family value. `canonical_domains` is a text sequence; `canonicalize_hostname` and `canonicalize_fallback_local` are booleans. `canonicalize_max_dots` is an integer; `canonicalize_permitted_cnames` is a sequence of `(expanded_host_pattern, alias_pattern)` text pairs. `agent_forwarding` accepts a boolean or socket-path text. Session choices passed here are `command`, `env` and `term_type`, with the same argument types as session creation.

Host-verification failure uses `HostKeyNotVerifiable`, denied authentication `PermissionDenied`, algorithm negotiation failure `KeyExchangeFailed`, protocol-version refusal `ProtocolNotSupported`, invalid transport `ProtocolError`, transport loss `ConnectionLost`, configuration failure `ConfigParseError` and unsafe user identity `IllegalUserName`. Routing also exposes `OSError`, `FileNotFoundError` and `ChannelOpenError`.

The default user host-trust file is `$HOME/.ssh/known_hosts`, containing OpenSSH known-hosts records. `HOME` is the local user home-directory environment variable.

Time-quantity text uses a decimal number with optional suffix `s`, `m`, `h`, `d` or `w`; compound quantities concatenate these number/suffix terms. Byte-quantity text uses a decimal number with optional suffix `k`/`K`, `m`/`M` or `g`/`G`. Algorithm selection text uses comma-separated name patterns with `*` and `?`, optionally prefixed by `^` (prepend), `+` (append) or `-` (remove); an unprefixed pattern list is replacement selection.

## `velnora.listen`

`listen(host=..., port=..., **options)` is awaitable and an asynchronous context manager yielding `SSHAcceptor`. Host is text, port integer, and `config` a filename or `None`.

`server_factory` is a zero-argument callable returning SSHServer; `process_factory` is a callable receiving SSHServerProcess and may be asynchronous. `server_host_keys` accepts key/path entries or key/certificate pairs, and `authorized_client_keys` a loaded authorization object or `None`. Transport selections `kex_algs`, `encryption_algs`, `mac_algs`, `compression_algs` and `signature_algs` accept algorithm-name sequences. `send_server_host_keys` is boolean.

`host_based_auth`, `trust_client_host`, `kbdint_auth`, `gss_kex` and `gss_auth` are boolean options; `gss_host` is service-principal text and `gss_store` a string mapping with `keytab`. `login_timeout`, `rekey_seconds` and `keepalive_interval` are numeric seconds, `rekey_bytes` and `keepalive_count_max` integers.

`encoding` is a codec-name string or `None`, `window` an integer, `allow_pty` and `line_editor` booleans, and `line_history` and `max_line_length` integers. `agent_forwarding` and `x11_forwarding` are booleans; `x11_auth_path` names an authorization file as text.

`sftp_factory` is a callable receiving SSHServerChannel and returning SFTPServer, `sftp_version` an integer protocol version, and `allow_scp` a boolean.

## `velnora.run_client`

`run_client(sock, host=..., **options)` is awaitable and an asynchronous context manager yielding SSHClientConnection. `sock` is a connected socket; `host` is text. It accepts the `config`, `known_hosts`, `agent_path`, `client_keys` and `username` connection options.

## `velnora.run_server`

`run_server(sock, config=..., server_factory=..., server_host_keys=..., process_factory=..., encoding=...)` is awaitable and an asynchronous context manager yielding SSHServerConnection. `sock` is a connected socket; the remaining arguments have the listener-option types.

## `velnora.connect_reverse`

`connect_reverse(host, port, config=..., server_host_keys=..., server_factory=..., process_factory=..., tunnel=...)` is awaitable and an asynchronous context manager yielding SSHServerConnection. Its host and port are text and integer; server choices have listener-option types and the tunnel is an SSHClientConnection. Establishment failure uses `ConnectionLost`, `HostKeyNotVerifiable` or `PermissionDenied`.

## `velnora.listen_reverse`

`listen_reverse(host, port, acceptor=..., error_handler=..., **options)` is an awaitable asynchronous context manager yielding SSHAcceptor. It accepts `config`, `known_hosts`, `username`, `client_keys` and `agent_path` with client-option types. `acceptor(conn)` receives an authenticated SSHClientConnection; `error_handler(conn, exc)` receives the connection and its establishment exception.

## `velnora.get_server_host_key`

Await `get_server_host_key(host, port, config=...)` for an SSHKey representing the presented host identity; it exposes `export_public_key()`. Host is text, port integer, configuration a filename or `None`.

## `velnora.get_server_auth_methods`

Await `get_server_auth_methods(host, port, config=..., username=...)` for a sequence of authentication-method strings. Host and username are text, port integer and configuration a filename or `None`.

## `velnora.SSHClientConnectionOptions`

`SSHClientConnectionOptions(config=..., login_timeout=...)` constructs a connection-options object. Configuration accepts `None` and login timeout is numeric seconds. Invalid settings raise `ValueError`.

## `velnora.SSHServerConnectionOptions`

`SSHServerConnectionOptions(config=..., login_timeout=...)` constructs a connection-options object. Configuration accepts `None` and login timeout is numeric seconds. Invalid settings raise `ValueError`.

## `velnora.SSHAcceptor`

`SSHAcceptor` is the listener returned by connection listeners. `get_port()` returns the bound TCP port as an integer. `close()` requests closure; `wait_closed()` is awaitable.

## `velnora.SSHClientConnection`

`close()`, `abort()` and `disconnect(code, reason)` request connection termination; `code` is an integer symbolic status and `reason` text. Await `wait_closed()` for closure; `is_closed()` returns boolean.

`get_server_host_key()` returns SSHKey. `get_extra_info(name)` accepts text names: `username` (authenticated user text), `host` (destination text), `sockname` and `peername` (socket address tuples), `socket` (socket supporting `getsockopt`), `send_cipher`, `recv_cipher`, `send_mac`, `send_compression` and `recv_compression` (negotiated algorithm-name text).

`set_keepalive(interval=..., count_max=...)` accepts a numeric interval and integer allowance. Invalid settings raise `ValueError`.

Await `create_session(session_factory, command=..., subsystem=..., env=..., send_env=..., request_pty=..., term_type=..., term_size=..., term_modes=..., encoding=..., errors=..., x11_forwarding=..., x11_display=..., x11_auth_path=..., x11_single_connection=...)` for `(channel, session)`. The factory takes no arguments and returns SSHClientSession; command/subsystem/terminal type are text or `None`; environment is a text mapping; send-environment selection a text sequence; terminal size a tuple of two character dimensions or four character/pixel dimensions; terminal modes an integer-to-integer mapping. A two-element terminal-size tuple has zero pixel dimensions. Terminal-request selection is boolean or a mode label `force` or `auto`. Encoding is codec text or `None`, errors a codec-error policy string; X11 selection boolean or the optional-setup label `ignore_failure`, display text or `None`, authorization path text and single-connection boolean.

Await `open_session(command=..., **options)` for `(stdin, stdout, stderr)`: an SSHWriter and two SSHReader objects. It accepts the session-creation options. Session refusal raises `ChannelOpenError` with an integer `code`.

`create_process(command=..., input=..., stdin=..., stdout=..., stderr=..., encoding=..., recv_eof=..., **options)` is awaitable and an asynchronous context manager yielding SSHClientProcess. It accepts session options. Input is text or bytes; redirections accept paths, file-like objects, integer pipe descriptors, sockets, asyncio streams, remote process streams and the `PIPE`, `DEVNULL` and `STDOUT` sentinels in the corresponding stream positions.

Await `run(command=..., input=..., stdin=..., stdout=..., stderr=..., check=..., encoding=..., recv_eof=..., **options)` for SSHCompletedProcess. It accepts session and process input/redirection options; check and EOF-control choices are boolean. Failures expose `ProcessError` or `TimeoutError` with captured process fields.

Await `create_subprocess(protocol_factory, command)` for `(transport, protocol)`, an SSHSubprocessTransport and the SSHSubprocessProtocol returned by the zero-argument factory.

Await `open_connection(remote_host, remote_port, orig_host=..., orig_port=...)` or `open_unix_connection(remote_path)` for `(reader, writer)`. Hosts/paths are text and ports integers. Failure raises `ChannelOpenError`.

Await `create_server(session_factory, listen_host, listen_port)` for an SSHListener. The callback receives origin host text and port integer and may be asynchronous; it returns a forwarding session or raises `ChannelOpenError`. Await `forward_connection(dest_host, dest_port)` for a forwarding session.

`forward_local_port(listen_host, listen_port, dest_host, dest_port)`, `forward_remote_port(listen_host, listen_port, dest_host, dest_port)`, `forward_local_path(listen_path, dest_path)` and `forward_remote_path(listen_path, dest_path)` are awaitable asynchronous context managers yielding SSHListener. Hosts and paths are text and ports integers. Local-listener failures use `OSError` and remote-listener failures `ChannelListenError`.

`forward_local_port_to_path(listen_host, listen_port, dest_path)`, `forward_remote_port_to_path(listen_host, listen_port, dest_path)`, `forward_local_path_to_port(listen_path, dest_host, dest_port)` and `forward_remote_path_to_port(listen_path, dest_host, dest_port)` are awaitable asynchronous context managers yielding SSHListener; host/path arguments are text and ports integers.

`forward_socks(listen_host, listen_port)` is an awaitable asynchronous context manager yielding SSHListener; host is text and port integer.

`connect_ssh(host, port, **options)` is an awaitable asynchronous context manager yielding SSHClientConnection, with client connection-option types.

Await `create_tun(session_factory, remote_unit=...)` or `create_tap(session_factory, remote_unit=...)` for `(channel, session)`, an SSHTunTapChannel and factory-created SSHTunTapSession. The factory takes no arguments; remote unit is integer or `None`. Failure raises `ChannelOpenError`. `create_tuntap_channel()` returns an SSHTunTapChannel.

`start_sftp_client(sftp_version=...)` is awaitable and an asynchronous context manager yielding SFTPClient. Protocol version is integer. Failures use `ChannelOpenError` or `SFTPBadMessage`.

## `velnora.SSHServerConnection`

`close()` and await `wait_closed()` provide connection closure. `get_extra_info(name)` exposes `username` and `host` text, and `socket` supporting `getsockopt`.

`get_key_option(option)` returns the selected restriction: `command` text; `environment` a text mapping; `permitopen` a set of `(host, port)` pairs with host text and port integer or `None`; `None` denotes an unrestricted destination port.

`check_key_permission(permission)` and `check_certificate_permission(permission)` take permission-name text and return boolean. Permission names are `pty`, `X11-forwarding`, `agent-forwarding` and `port-forwarding`.

`send_auth_banner(msg, lang)` accepts banner text and language-tag text.

`get_agent_path()` returns a forwarded-agent UNIX socket path string or `None`. `create_agent_channel()` returns an SSHAgentChannel.

Await `create_x11_connection(session_factory)` for an X11 channel/session pair or `ChannelOpenError`. The factory takes no arguments and returns SSHTCPSession.

Await `forward_connection(dest_host, dest_port)` for a forwarding session; host is text and port integer.

`set_keepalive(interval=..., count_max=...)` takes a numeric interval in seconds and an integer unanswered-request allowance.

## `velnora.SSHListener`

Forwarding calls return `SSHListener` objects supporting asynchronous context management, `get_port()` returning the bound TCP port integer, `close()` and awaitable `wait_closed()`.

## `velnora.SSHServer`

Subclass `SSHServer` for the server-factory interface. `connection_made(conn)` receives SSHServerConnection; `connection_lost(exc)` receives an exception or `None`; `auth_completed()` is a notification.

`begin_auth(username)` receives user text and returns boolean, synchronously or asynchronously. `public_key_auth_supported()`, `password_auth_supported()`, `host_based_auth_supported()` and `kbdint_auth_supported()` return booleans. `validate_public_key(username, key)` and `validate_password(username, password)` receive user text plus SSHKey or password text and return boolean.

`validate_host_public_key(client_host, client_addr, client_port, key)` receives host/address text, integer port and SSHKey. `validate_host_based_user(username, client_host, client_username)` receives three text values. `validate_gss_principal(username, user_principal, host_principal)` receives three text values. Each returns a boolean.

`validate_password` can raise `PasswordChangeRequired`. `change_password(username, old_password, new_password)` receives text values and returns boolean. `get_kbdint_challenge(username, lang, submethods)` returns boolean or `(name, instructions, lang, prompts)`, whose first three fields are text and prompts a sequence of `(prompt, echo)` text/boolean pairs. `validate_kbdint_response(username, responses)` accepts user text and a response-text sequence, returning boolean or another challenge tuple.

`session_requested()` returns SSHServerSession or boolean refusal.

`connection_requested(dest_host, dest_port, orig_host, orig_port)` receives host text and integer ports, returning a boolean, SSHTCPSession or awaitable forwarding session. `unix_connection_requested(dest_path)` receives path text and returns boolean or an application session.

`server_requested(listen_host, listen_port)` and `unix_server_requested(listen_path)` receive host/path text and integer port and return booleans.

`tun_requested(unit)` and `tap_requested(unit)` receive an integer interface number or `None`, returning SSHTunTapSession or boolean refusal.

## `velnora.SSHClient`

Subclass `SSHClient` for the client-factory interface. `connection_lost(exc)` receives an exception or `None`. `auth_banner_received(msg, lang)` receives banner text and language-tag text.

`validate_host_public_key(host, addr, port, key)` receives host/address text, integer port and SSHKey and returns a boolean host-validation decision.

`password_change_requested(prompt, lang)` receives text and returns `(old_password, new_password)` text values. `password_changed()` and `password_change_failed()` are notifications.

`kbdint_auth_requested()` returns submethod-selection text or `None`. `kbdint_challenge_received(name, instructions, lang, prompts)` receives three text fields and a sequence of `(prompt, echo)` text/boolean pairs and returns response texts.

## `velnora.SSHClientSession`

Subclass `SSHClientSession` for session factories. `data_received(data, datatype)` receives text or bytes matching the channel encoding, with `datatype` equal to `None` for ordinary output or `EXTENDED_DATA_STDERR` for error output.

## `velnora.SSHServerSession`

Subclass `SSHServerSession` for application sessions. `connection_made(channel)` receives SSHServerChannel; `connection_lost(exc)` receives an exception or `None`. `session_started()` is a readiness notification.

`shell_requested()`, `exec_requested(command)` and `subsystem_requested(subsystem)` return boolean acceptance; command/subsystem arguments are text.

`pty_requested(term_type, term_size, term_modes)` receives terminal text, a four-integer tuple `(width, height, pixwidth, pixheight)` and integer-to-integer modes, returning boolean acceptance. `terminal_size_changed(width, height, pixwidth, pixheight)` receives four integers. `break_received(msec)` receives an integer duration and returns boolean; `signal_received(signal)` receives signal-name text.

`data_received(data, datatype)` receives text or bytes with ordinary-input datatype `None`. `eof_received()` is an end-of-input callback returning boolean.

## `velnora.SSHTCPSession`

Subclass `SSHTCPSession` for forwarding application sessions. `connection_made(channel)` receives the channel, `session_started()` notifies readiness, `data_received(data, datatype)` receives bytes and `None` datatype, and `eof_received()` returns boolean. The channel exposes `write(data)` and `write_eof()`.

## `velnora.SSHUNIXSession`

`SSHUNIXSession` is a zero-argument session factory accepted by an agent channel's `open` operation.

## `velnora.SSHTunTapSession`

Subclass `SSHTunTapSession` for packet sessions. `connection_made(channel)` receives SSHTunTapChannel, `session_started()` notifies readiness, `data_received(data, datatype)` receives one packet as bytes and ordinary-data `None` datatype, and `connection_lost(exc)` receives an exception or `None`.

## `velnora.SSHClientChannel`

`write(data)` accepts text or bytes according to channel encoding. `write_eof()` sends the output EOF indication. `pause_reading()` and `resume_reading()` are input controls. `close()` requests closure; `wait_closed()` is awaitable.

`change_terminal_size(width, height, pixwidth=..., pixheight=...)` accepts integer dimensions. `send_break(msec)` accepts integer milliseconds and `send_signal(signal)` signal-name text.

`get_exit_status()` returns the integer exit status, using -1 for signal termination. `get_exit_signal()` returns `None` or `(signal, core_dumped, msg, lang)` with text, boolean, text and text fields.

## `velnora.SSHServerChannel`

`get_connection()` returns SSHServerConnection. `get_extra_info('username')` returns user text.

`get_command()` and `get_subsystem()` return text or `None`. `get_environment()` returns a mapping of text names to text values.

`get_terminal_type()` returns terminal text or `None`; `get_terminal_size()` a four-integer `(width, height, pixwidth, pixheight)` tuple; `get_terminal_modes()` an integer mapping; `get_terminal_mode(mode)` the selected integer value.

`write(data)` and `write_stderr(data)` accept text or bytes according to channel encoding and address ordinary/error output. `write_eof()` sends output EOF. `pause_reading()` and `resume_reading()` control input; `close()` and awaited `wait_closed()` provide closure.

`exit(status)` takes an integer status; `exit_with_signal(signal, core_dumped=..., msg=..., lang=...)` takes signal-name text, boolean core-dump flag, message text and language-tag text.

`get_agent_path()` returns agent-socket path text or `None`.

`get_x11_display()` returns `None` or `<host>:<display-number>.<screen-number>` text.

## `velnora.SSHTunTapChannel`

`write(data)` accepts packet bytes. `close()` requests closure; `wait_closed()` is awaitable. Await `open(session_factory, mode, unit)` for the selected packet session; mode is integer and unit integer or `None`. Channel refusal raises `ChannelOpenError`.

## `velnora.SSHReader`

Session output is exposed through `SSHReader`. Await `read(n=...)`, `readline()`, `readexactly(n)` or `readuntil(separator, max_separator_len=...)` for text or bytes matching the stream encoding. Lengths are integers; separator is matching text/bytes, a tuple of such sequences, or a compiled regular expression. The reader is asynchronously iterable over lines.

Incomplete reads raise `asyncio.IncompleteReadError` exposing `partial` in the stream's text/bytes type. Invalid delimiter requests raise `ValueError`.

Strict text conversion failure is reported as `ProtocolError`.

Transport interruption during an unfinished read raises `ConnectionLost`.

## `velnora.SSHWriter`

An `SSHWriter` exposes `channel`. `write(data)` takes text or bytes matching the stream encoding; `drain()` is awaitable; `write_eof()` sends EOF; `can_write_eof()` returns boolean. `close()` requests closure and `wait_closed()` is awaitable. Pending-output failures use `ConnectionError` or `ConnectionLost`.

## `velnora.SSHCompletedProcess`

Completed process results expose `stdout` and `stderr` as text or bytes matching process encoding, `exit_status` as integer, `exit_signal` as `None` or `(signal, core_dumped, msg, lang)` (text, boolean, text, text), and `returncode` as integer. A signal outcome has exit_status -1 and a returncode equal to the negative POSIX signal number; an ordinary outcome carries its exit status as returncode.

## `velnora.SSHClientProcess`

A process is an asynchronous context manager. `stdin` is SSHWriter; `stdout` and `stderr` are SSHReader. `wait_closed()` is awaitable.

Await `wait(check=..., timeout=...)` for SSHCompletedProcess; check is boolean and timeout numeric seconds. Await `communicate(input)` with message bytes for `(stdout, stderr)` bytes. Completion failures use `ProcessError` or `TimeoutError`.

`send_signal(signal)` takes signal-name text; `terminate()` and `kill()` are process controls.

Await `redirect_stdin(source, send_eof=...)` or `redirect_stdout(target)` to select a redirection. The source and target accept file-like objects; output also accepts `PIPE`. The EOF choice is boolean.

## `velnora.SSHServerProcess`

The process-factory argument is `SSHServerProcess`, exposing `command` and `term_type` as text or `None`, `env` as a text mapping, `channel` as SSHServerChannel, and `get_extra_info('username')` as text. `stdin` is SSHReader; `stdout` and `stderr` are SSHWriter.

`exit(status)` takes an integer; `exit_with_signal(signal)` takes signal-name text.

Await `redirect(stdin=..., stdout=..., recv_eof=..., send_eof=...)` or `redirect_stderr(source, send_eof=...)`. Server stdin redirection names a destination; stdout/stderr redirection names a source. Carriers include paths, file-like objects, integer pipe descriptors, sockets and asyncio streams; EOF choices are boolean.

## `velnora.SSHSubprocessProtocol`

Subclass `SSHSubprocessProtocol`. `pipe_data_received(fd, data)` receives integer descriptor 1 for stdout or 2 for stderr and data bytes. `pipe_connection_lost(fd, exc)` receives the descriptor and an exception or `None`.

## `velnora.SSHSubprocessTransport`

`get_pipe_transport(fd)` takes integer 0 for stdin and returns a write-pipe object exposing `write(data)` for bytes and `write_eof()`. `get_returncode()` returns the process integer returncode. `close()` requests closure.

## `velnora.SSHLineEditorChannel`

The application channel for edited sessions exposes `set_line_mode(line_mode)` and `set_echo(echo)` taking booleans; `clear_input()`; `set_input(line, pos)` taking pending-line text and integer cursor position.

`register_key(key, handler)` takes key-sequence text and `handler(line, pos)`. The handler returns boolean or `(new_line, new_pos)` text/integer pair. A pair with position -1 carries signal-name text instead of pending-line text. `unregister_key(key)` takes key-sequence text.

Terminal output is a text stream interpreted as ANSI/VT terminal text and cursor-control sequences; terminal dimensions are supplied through session terminal metadata.

## `velnora.SFTPClient`

The SFTP context yields `SFTPClient` with integer `version`. `open(path, pflags_or_mode, encoding=..., block_size=...)` is awaitable and an asynchronous context manager yielding SFTPClientFile; path is text or path-like, mode text, encoding codec text, block size integer.

Await `stat(path)` or `lstat(path)` for SFTPAttrs and `statvfs(path)` for SFTPVFSAttrs. Await `chmod(path, mode, follow_symlinks=...)`, `chown(path, uid, gid)`, `utime(path, times, follow_symlinks=...)` and `truncate(path, size)` for metadata operations. Mode, ownership and size are integers; times an access/modification timestamp pair; link-following boolean.

Await `makedirs(path)`, `rmdir(path)`, `rmtree(path)`, `remove(path)`, `rename(oldpath, newpath)`, `posix_rename(oldpath, newpath)`, `link(oldpath, newpath)`, or `symlink(oldpath, newpath)` for path operations. Await `chdir(path)` for working-directory selection, and `getcwd()`, `realpath(path)` or `readlink(path)` for path text. Await `readdir(path)` for a sequence of SFTPName objects with `filename` text and `attrs`.

Await `glob(patterns, error_handler=...)` for a list of path strings; patterns accepts text. `error_handler(exc)` receives an SFTP exception.

Await `get(remotepaths, localpath=..., preserve=..., recurse=..., follow_symlinks=..., block_size=..., progress_handler=..., error_handler=...)`, `put(localpaths, remotepath=..., preserve=..., recurse=..., follow_symlinks=...)` or `copy(srcpaths, dstpath=..., preserve=..., recurse=..., follow_symlinks=..., remote_only=...)` for transfer completion. Sources are one path or a sequence of paths; destinations paths; transfer choices booleans and block size integer. Local paths accept text/path-like values; remote paths here are text. Output consists of destination filesystem files, directories, links, file bytes, permission bits and access/modification timestamps under caller-selected paths.

`progress_handler(srcpath, dstpath, bytes_copied, total_bytes)` receives two path-byte values and two integer byte counts. `error_handler(exc)` receives a transfer exception; a handler-raised exception propagates to the caller.

Await `remote_copy(src, dst, src_offset=..., src_length=..., dst_offset=...)` with open SFTPClientFile source/destination and integer byte offsets and length.

Operation failure forms are `SFTPNoSuchFile`, `SFTPPermissionDenied`, `SFTPOpUnsupported`, `SFTPFailure`, `SFTPFileAlreadyExists`, `SFTPFileIsADirectory`, `SFTPBadMessage`, `SFTPConnectionLost` and `SFTPInvalidHandle`. A destination-directory failure can use `SFTPNotADirectory` or local `NotADirectoryError`.

## `velnora.SFTPClientFile`

An SFTP open file supports asynchronous context management. Await `read(size=..., offset=...)` for bytes or text matching the file mode/encoding. Await `write(data, offset=...)` for integer bytes written. Await `seek(offset, from_what=...)` and `tell()` for the integer file position. Offsets and sizes are integers; seek origin accepts `os.SEEK_CUR` and `os.SEEK_END` in addition to beginning-relative positioning.

Await `stat()` for SFTPAttrs. Await `truncate(size)`, `chmod(mode)`, `chown(uid, gid)` or `utime(times)` for metadata completion.

Await `fsync()` for synchronization completion.

Await `lock(offset, length, flags)` with integers, or `close()` for closure. Closed-file access failure uses `ValueError`.

## `velnora.SFTPAttrs`

Returned `SFTPAttrs` expose `size` (file byte size), `permissions` (mode/type bits), `uid` and `gid` (ownership), `atime` and `mtime` (Unix-second access and modification times) as integer fields.

## `velnora.SFTPVFSAttrs`

Returned `SFTPVFSAttrs` expose integer `bsize` (filesystem block size), `frsize` (fundamental allocation-unit size) and `blocks` (total allocation-unit count).

## `velnora.SFTPName`

Directory records expose `filename` and `attrs`. Client `readdir` names are text; server `scandir` names are mutable bytes. `attrs` is SFTPAttrs.

## `velnora.SFTPServer`

`SFTPServer(chan, chroot=...)` accepts SSHServerChannel and a local path-like root or `None`. Applications may subclass it. `map_path(path)` takes client-path bytes and returns local-path bytes. `scandir(path)` is asynchronously iterable over SFTPName records whose `filename` bytes can be assigned. Application filesystem refusals can raise `SFTPPermissionDenied`.

## `velnora.scp`

Await `scp(srcpaths, dstpath, recurse=..., preserve=..., progress_handler=..., error_handler=..., **connect_options)` for completion returning `None`. Local endpoints are text or path-like paths; remote endpoints are `(SSHClientConnection, path)` or `((host, port), path)`. Sources may be an endpoint sequence. Recursion and preservation choices are boolean. Connection keywords are `config`, `known_hosts`, `client_keys`, `agent_path` and `username` with client-connection types. Output is filesystem bytes, directories, permission bits and access/modification times at caller-selected destination paths.

`progress_handler(srcpath, dstpath, bytes_copied, total_bytes)` receives two byte paths and two integer byte counts. `error_handler(exc)` receives an `OSError` or transfer exception; handler-raised exceptions propagate.

Failure forms are `ValueError`, `ChannelOpenError`, `SFTPFailure`, `SFTPConnectionLost`, `SFTPBadMessage` and `FileNotFoundError`.

## `velnora.ChannelListenError`

`ChannelListenError` is an exception exported by velnora. Listener creation/refusal exception.

## `velnora.ConnectionLost`

`ConnectionLost` is an exception exported by velnora. Connection-loss or incomplete-login timeout exception.

## `velnora.HostKeyNotVerifiable`

`HostKeyNotVerifiable` is an exception exported by velnora. Host-identity verification failure exception.

## `velnora.IllegalUserName`

`IllegalUserName` is an exception exported by velnora. Unsafe authorization-user identity exception.

## `velnora.KeyExchangeFailed`

`KeyExchangeFailed` is an exception exported by velnora. SSH algorithm-negotiation failure exception.

## `velnora.MACError`

`MACError` is an exception exported by velnora. SSH transport-integrity failure exception delivered to the connection-loss callback.

## `velnora.PermissionDenied`

`PermissionDenied` is an exception exported by velnora. Authentication-denial exception.

## `velnora.ProtocolError`

`ProtocolError` is an exception exported by velnora. Invalid SSH protocol/data exception.

## `velnora.ProtocolNotSupported`

`ProtocolNotSupported` is an exception exported by velnora. Unsupported SSH protocol-version exception.

## `velnora.KeyGenerationError`

`KeyGenerationError` is an exception exported by velnora. Key or certificate generation failure exception.

## `velnora.KeyImportError`

`KeyImportError` is an exception exported by velnora. Key or certificate input failure exception.

## `velnora.KeyExportError`

`KeyExportError` is an exception exported by velnora. Key serialization failure exception.

## `velnora.KeyEncryptionError`

`KeyEncryptionError` is an exception exported by velnora. Private-key protection/decryption failure exception.

## `velnora.SFTPBadMessage`

`SFTPBadMessage` is an exception exported by velnora. Invalid SFTP/SCP peer data or negotiation exception.

## `velnora.SFTPConnectionLost`

`SFTPConnectionLost` is an exception exported by velnora. File-transfer connection-loss exception.

## `velnora.SFTPFailure`

`SFTPFailure` is an exception exported by velnora. File-operation or transfer failure exception.

## `velnora.SFTPFileAlreadyExists`

`SFTPFileAlreadyExists` is an exception exported by velnora. Existing-file conflict exception.

## `velnora.SFTPFileIsADirectory`

`SFTPFileIsADirectory` is an exception exported by velnora. Directory-as-file transfer failure exception.

## `velnora.SFTPInvalidHandle`

`SFTPInvalidHandle` is an exception exported by velnora. Invalid remote-file-handle exception.

## `velnora.SFTPNoSuchFile`

`SFTPNoSuchFile` is an exception exported by velnora. Missing-file/path or unmatched-search exception.

## `velnora.SFTPNotADirectory`

`SFTPNotADirectory` is an exception exported by velnora. Destination-directory failure exception.

## `velnora.SFTPOpUnsupported`

`SFTPOpUnsupported` is an exception exported by velnora. Unavailable filesystem-operation exception.

## `velnora.SFTPPermissionDenied`

`SFTPPermissionDenied` is an exception exported by velnora. File-service permission-denial exception; applications can construct it with diagnostic text.

## `velnora.ChannelOpenError`

`ChannelOpenError(code, reason)` is an exception with integer `code` identifying the channel-open failure category. Applications can raise it with an integer symbolic failure code and diagnostic text.

## `velnora.PasswordChangeRequired`

`PasswordChangeRequired(prompt, lang)` is the server password-change request exception; prompt and language tag are caller-supplied text carried to the client's password-change callback.

## `velnora.ConfigParseError`

`ConfigParseError` is the configuration-failure exception. Its string form starts with `<source path> line <line number>:` and then carries a diagnostic reason. The path identifies the source file and the decimal number its line.

## `velnora.ProcessError`

`ProcessError` is the unsuccessful-process exception. Readable fields are `command` (text or `None`), `stdout` and `stderr` (text or bytes), `exit_status` (integer), `exit_signal` (`None` or signal-name/core-flag/message/language tuple) and `returncode` (integer). Termination fields have the same representation as completed-process results.

## `velnora.TimeoutError`

`TimeoutError` exported by velnora is the process-completion timeout exception. It exposes `command` (text or `None`), `stdout` and `stderr` (text or bytes collected before expiry).

## `velnora.DISC_BY_APPLICATION`

`DISC_BY_APPLICATION` is the integer symbolic code for application-requested disconnect status.

## `velnora.OPEN_ADMINISTRATIVELY_PROHIBITED`

`OPEN_ADMINISTRATIVELY_PROHIBITED` is the integer symbolic code for channel refusal by policy.

## `velnora.OPEN_REQUEST_X11_FORWARDING_FAILED`

`OPEN_REQUEST_X11_FORWARDING_FAILED` is the integer symbolic code for X11 session setup failure.

## `velnora.OPEN_REQUEST_PTY_FAILED`

`OPEN_REQUEST_PTY_FAILED` is the integer symbolic code for terminal request failure.

## `velnora.OPEN_REQUEST_SESSION_FAILED`

`OPEN_REQUEST_SESSION_FAILED` is the integer symbolic code for shell/command/subsystem request failure.

## `velnora.EXTENDED_DATA_STDERR`

`EXTENDED_DATA_STDERR` is the integer symbolic code for channel error-output datatype.

## `velnora.PIPE`

`PIPE` is the process-redirection sentinel naming the process stream interface.

## `velnora.DEVNULL`

`DEVNULL` is the process-redirection sentinel naming the null input/output destination.

## `velnora.STDOUT`

`STDOUT` is the process-redirection sentinel naming ordinary output as the error-output destination.

## `ssh_config`

The client `config` option names an OpenSSH client configuration text file. Its records have `<directive> <arguments>` form, with quoted argument text, blank lines and `#` comments. `Include <path-pattern>` names another configuration file or file-name pattern.

Scalar directive names are `Hostname`, `Port`, `User`, `AddressFamily`, `BindAddress`, `HostKeyAlias`, `IdentityAgent`, `IdentitiesOnly`, `GSSAPIAuthentication`, `HostbasedAuthentication`, `TCPKeepAlive`, `KbdInteractiveAuthentication`, `PasswordAuthentication`, `PubkeyAuthentication`, `Compression`, `RemoteCommand`, `RequestTTY`, `ProxyJump`, `ProxyCommand`, `ConnectTimeout`, `CanonicalizeHostname` and `Tag`; each is followed by its selected argument.

List/path directive names are `IdentityFile`, `CertificateFile`, `SendEnv`, `UserKnownHostsFile`, `GlobalKnownHostsFile`, `PreferredAuthentications`, `Ciphers`, `MACs`, `KexAlgorithms` and `HostKeyAlgorithms`. `SetEnv` carries `<name>=<value>` assignments. Algorithm and authentication lists use comma-separated names.

`Host <patterns>` and `Match <conditions>` introduce conditional records. Client condition names are `all`, `host`, `originalhost`, `user`, `localuser`, `tagged`, `exec`, `localnetwork`, `canonical` and `final`. Negation uses a leading `!`; name-pattern syntax includes `*` and `?`.

Substitution syntax is `%h` (destination host), `%n` (original host), `%p` (port), `%r` (remote user), `%u` (local user), `%d` (local home), `%i` (local user id), `%l` (full local host name), `%L` (short local host name), `%%` (percent), and `${<name>}` (environment value). Proxy-command stdin/stdout carry bidirectional SSH bytes.

Additional scalar directive names are `EnableSSHKeysign`, `GSSAPIKeyExchange`, `GSSAPIDelegateCredentials`, `ForwardX11Trusted`, `ForwardAgent`, `ServerAliveInterval` and `ServerAliveCountMax`. `CASignatureAlgorithms` carries a comma-separated signature-name list. `RekeyLimit <byte-quantity> [<time-quantity>]` carries quantity text.

`PKCS11Provider` takes a provider-library path. Canonicalization directive forms are `CanonicalDomains <domain> ...`, `CanonicalizeFallbackLocal <yes|no>`, `CanonicalizeMaxDots <integer>` and `CanonicalizePermittedCNAMEs <host-patterns>:<alias-patterns> ...`.

## `sshd_config`

The server `config` option names an OpenSSH server configuration text file with `<directive> <arguments>` records, quoting, blank lines and `#` comments. The directive names are `AddressFamily`, `Port`, `HostKey`, `HostCertificate`, `AuthorizedKeysFile`, `PubkeyAuthentication`, `PasswordAuthentication`, `KbdInteractiveAuthentication`, `Ciphers`, `MACs`, `KexAlgorithms`, `Compression`, `PermitTTY`, `TCPKeepAlive`, `UseDNS`, `LoginGraceTime` and `AllowAgentForwarding`, followed by selected arguments.

`Match <conditions>` uses `address`, `localaddress`, `user`, `host` and `exec` conditions, with `!` negation. `AuthorizedKeysFile` has `%u` user substitution and `${<name>}` environment substitution.

Additional directive names are `CASignatureAlgorithms` (comma-separated signature names), `RekeyLimit <byte-quantity> [<time-quantity>]`, `ClientAliveInterval <seconds>` and `ClientAliveCountMax <integer>`. `Match` also accepts `localport <integer>`.

`GSSAPIKeyExchange` takes `yes` or `no`. Outbound reverse-server connections accept `CanonicalizeHostname <yes|no|always>`, `CanonicalDomains <domain> ...`, `CanonicalizeFallbackLocal <yes|no>`, `CanonicalizeMaxDots <integer>` and `CanonicalizePermittedCNAMEs <host-patterns>:<alias-patterns> ...`.

## `known_hosts`

Host-trust inputs use OpenSSH `known_hosts` text records: `[<marker>] <host-patterns> <algorithm> <base64-identity> [<comment>]`. Host patterns include plain host/address text, `[<host>]:<port>`, comma-separated patterns, hashed-host fields, and network text. Marker spellings are `@cert-authority` and `@revoked`. Subject-pattern records use an X.509 algorithm name followed by `subject=<distinguished-name-pattern>`. The document may have blank lines and `#` comments; files have caller-selected paths.

## `authorized_keys`

Authorization inputs use OpenSSH `authorized_keys` text: `[<comma-separated-options>] <algorithm> <base64-identity> [<comment>]` or an X.509 `subject=<pattern>` identity. Option names are `cert-authority`, `from`, `principals`, `subject`, `command`, `environment` and `permitopen`; valued options use `<name>="<value>"`. Environment values are `<name>=<value>`; permitted destinations use `<host>:<port>` or `[<IPv6 address>]:<port>`. The port component is decimal integer text or `*`.

Permission option spellings are `no-pty`, `no-X11-forwarding`, `no-agent-forwarding` and `no-port-forwarding`.

## `allowed_signers`

Allowed-signers input is text or bytes containing `<principal-patterns> [<options>] <algorithm> <base64-identity>` records. Principal patterns are comma-separated. Option spellings are `cert-authority`, `namespaces="<patterns>"`, `valid-after=<timestamp>` and `valid-before=<timestamp>`; options are comma-separated. Timestamp syntax uses calendar digits `YYYYMMDD` or `YYYYMMDDHHMMSS`, with `Z` marking UTC. Files have caller-selected paths.

## `id_ed25519`

The local default Ed25519 identity-file path is `~/.ssh/id_ed25519`; `HOME` supplies the home directory for this path.

## `SOCKS`

The listener returned by `forward_socks` exchanges SOCKS bytes. SOCKS4/4a CONNECT requests are version byte, command byte, big-endian uint16 destination port, four address bytes and a NUL-terminated user id; the 4a hostname follows as NUL-terminated ASCII. A SOCKS4 reply is eight bytes: zero byte, reply-status byte, uint16 port and IPv4 address; status 90 is the granted reply.

SOCKS5 method negotiation is version byte, method-count byte and method bytes, with a two-byte version/method response. The unauthenticated selection response is `\x05\x00`. CONNECT request/reply headers are version, command/status, reserved-zero and address-type bytes; IPv4, domain and IPv6 address types are 1, 3 and 4. Addresses have four bytes, one-byte length plus ASCII name, or sixteen bytes respectively, followed by uint16 network-order port. Reply status zero is success.

Failed destination access can have a protocol reply followed by EOF/reset/silence, or EOF/reset/silence during the reply.

## `Xauthority`

`DISPLAY` carries local display text and `XAUTHORITY` an authorization-file path; an explicit `x11_auth_path` selects the caller's local input file or the server authorization output file. Display text has `<host>:<display-number>.<screen-number>` form, addressing TCP port 6000 plus the display number.

The authorization file is a concatenation of records. Each has a big-endian uint16 address family and four uint16-length-prefixed byte fields: address, ASCII display number, authorization protocol and authorization data. The protocol name carried here is `MIT-MAGIC-COOKIE-1`. Address-family codes are 0 for packed IPv4, 6 for packed IPv6, 256 for a local host name, and 65535 for an address wildcard.

## `X11`

Forwarded display streams use X11 setup framing: `B` or `l` byte-order byte, padding byte, then five uint16 fields in the selected order (major/minor version, authorization-protocol length, authorization-data length, padding). Protocol and authorization bytes are padded separately to multiples of four bytes; subsequent traffic is bytes.

An X11 refusal is clean EOF or a setup-failure packet: zero status byte, reason-byte count, major/minor uint16 version fields, uint16 additional-data length in four-byte units, then padded reason bytes.

## `sftp`

The `sftp` SSH subsystem carries standard SFTP packets: uint32 network-order payload length, one-byte packet type, then payload. Initialization type 1 carries uint32 requested version; version response type 2 carries uint32 version followed by extension-name/value SSH string pairs. Subsequent requests and responses carry uint32 request id after the type.

SFTP v3 request payloads are: open (type 3): path SSH string, uint32 open flags, attributes; close (4): handle string; read (5): handle string, uint64 byte offset, uint32 length; write (6): handle string, uint64 offset, data string; lstat/stat (7/17): path string; fstat (8): handle string. Open flags encode read, write, append, create, truncate and exclusive creation as bits 1, 2, 4, 8, 16 and 32.

Status response type 101 has request id, uint32 status, diagnostic string and language string; handle response 102 has request id and handle string; data response 103 has request id and data string; attributes response 105 has request id and attributes. V3 attributes carry a flags uint32 followed by selected size uint64, uid/gid uint32 pair, permissions uint32 and access/modification uint32 time pair, selected by bits 1, 2, 4 and 8.

Extended request type 200 carries request id and extension-name SSH string. `fsync@openssh.com` adds a handle string. `copy-data` adds source handle string, uint64 source offset and length, destination handle string and uint64 destination offset.

## `scp`

The remote executable request forms are `scp -f <path>` for a source and `scp -t <path>` for a destination. Its stdin/stdout carry SCP protocol bytes. A file record is `C<octal-mode> <decimal-size> <basename>\n` followed by file bytes and a status byte, with zero-byte acknowledgements. Error records are byte 1 or 2 followed by a newline-terminated diagnostic. Transfer-command failure is exposed as a nonzero remote `exit_status` and diagnostic `stderr`.

## `velnora.public_key.SSHOpenSSHCertificate`

`validate(cert_type, principal)` takes an integer certificate role and a principal text value or `None`, returns `None` on successful validation and raises `ValueError` on validation failure.

## `velnora.public_key.SSHX509Certificate`

`validate_chain(trust_chain, trusted_certs, trusted_cert_paths, purposes, user_principal=..., host_principal=...)` takes certificate sequences, certificate-path sequences, purpose OID sequences, the purpose-check mode label `any` or `None`, and principal text. It returns `None` on successful validation and raises `ValueError` on validation failure.

## `velnora.public_key.SSHX509CertificateChain`

`validate_chain(trusted_certs, trusted_cert_paths, revoked_certs, purposes, user_principal=..., host_principal=...)` accepts certificate collections, trusted path sequences, purpose OID strings or `None`, and principal text. It returns `None` on successful validation and raises `ValueError` on validation failure.

## `velnora.channel.SSHAgentChannel`

Await `open(session_factory)` on the channel returned by `create_agent_channel()`. The factory returns SSHUNIXSession. Refusal raises `ChannelOpenError` with integer `code`.

## `SSH-2.0-`

The TCP identification carrier is an ASCII line beginning `SSH-2.0-` followed by software-identification text and a line terminator.
