# Interface Contract

The package is importable as `cobaltform` from the product directory. Classes and functions are imported from their stated submodules, for example `from cobaltform.core import Integer`; the submodules are `cobaltform.core`, `parser`, `pem`, `util`, `algos`, `keys`, `x509`, `crl`, `csr`, `ocsp`, `cms`, `pkcs12`, `tsp` and `pdf`.

ASN.1 binary input, encoded output and binary payloads use Python `bytes`; text uses `str`. ASN.1 objects expose `native` as a Python value. Records use mappings with the documented field names; homogeneous collections use lists; bit-name values use sets; positional bits use tuples of integers. Named fields are accessed with string subscripts, collection members with integer subscripts. Collections support iteration and `len()`. Selected ASN.1 values retain their object interfaces until `native` is read.

An absent optional ASN.1 field is a field object whose `native` is `None` and whose `dump()` returns `b''`. A present empty collection has `native` equal to `[]`; these are distinct return forms.

The Python result types include `bool`, `int`, `str`, `bytes`, `tuple`, `list` and `set`, with record values exposed as dictionary mappings. A field's listed type describes its `native` value unless the description names a typed ASN.1 object.

Date-time values expose Python-style calendar formatting. On an extended date-time value, `strftime("%Y-%m-%d")` returns `<YYYY>-<MM>-<DD>` with a four-digit year and two-digit month and day. `isoformat()` returns `<YYYY>-<MM>-<DD>T<HH>:<MM>:<SS>`, followed by `.ffffff` when microseconds are nonzero and by a signed `<HH>:<MM>` UTC offset when timezone-aware. Numeric components are zero-padded; the fraction has six digits.

## `cobaltform`

`cobaltform` is the Python package namespace for the documented submodule imports.

## `cobaltform.algos`

`cobaltform.algos` exposes the following public names:

- `AlgorithmIdentifier`

- `AnyAlgorithmIdentifier`

- `DSASignature`

- `DigestAlgorithm`

- `EncryptionAlgorithm`

- `HmacAlgorithm`

- `KdfAlgorithm`

- `KeyExchangeAlgorithm`

- `Pkcs5MacAlgorithm`

- `SignedDigestAlgorithm`

Signature-family strings are `rsassa_pkcs1v15`, `rsassa_pss`, `dsa`, `ecdsa`, `ed25519` and `ed448`. Derivation-family strings are `pbkdf1`, `pbkdf2`, `pkcs12_kdf` and `scrypt`. Cipher-family strings are `des`, `tripledes`, `rc2`, `rc4`, `rc5` and `aes`; mode strings are `ecb`, `cbc`, `ofb`, `cfb`, `wrap`, `gcm`, `ccm` and `wrap_pad`.

### MAC algorithm OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.3.14.3.2.10` | `des_mac` |
| `1.2.840.113549.2.7` | `sha1` |
| `1.2.840.113549.2.8` | `sha224` |
| `1.2.840.113549.2.9` | `sha256` |
| `1.2.840.113549.2.10` | `sha384` |
| `1.2.840.113549.2.11` | `sha512` |
| `1.2.840.113549.2.12` | `sha512_224` |
| `1.2.840.113549.2.13` | `sha512_256` |
| `2.16.840.1.101.3.4.2.13` | `sha3_224` |
| `2.16.840.1.101.3.4.2.14` | `sha3_256` |
| `2.16.840.1.101.3.4.2.15` | `sha3_384` |
| `2.16.840.1.101.3.4.2.16` | `sha3_512` |

### Digest algorithm OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.2.840.113549.2.2` | `md2` |
| `1.2.840.113549.2.5` | `md5` |
| `1.3.14.3.2.26` | `sha1` |
| `2.16.840.1.101.3.4.2.4` | `sha224` |
| `2.16.840.1.101.3.4.2.1` | `sha256` |
| `2.16.840.1.101.3.4.2.2` | `sha384` |
| `2.16.840.1.101.3.4.2.3` | `sha512` |
| `2.16.840.1.101.3.4.2.5` | `sha512_224` |
| `2.16.840.1.101.3.4.2.6` | `sha512_256` |
| `2.16.840.1.101.3.4.2.7` | `sha3_224` |
| `2.16.840.1.101.3.4.2.8` | `sha3_256` |
| `2.16.840.1.101.3.4.2.9` | `sha3_384` |
| `2.16.840.1.101.3.4.2.10` | `sha3_512` |
| `2.16.840.1.101.3.4.2.11` | `shake128` |
| `2.16.840.1.101.3.4.2.12` | `shake256` |
| `2.16.840.1.101.3.4.2.17` | `shake128_len` |
| `2.16.840.1.101.3.4.2.18` | `shake256_len` |

### Mask-generation OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.2.840.113549.1.1.8` | `mgf1` |

### Trailer enumeration

| Numeric identity | Text identity |
| --- | --- |
| `1` | `trailer_field_bc` |

### Signature algorithm OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.2.840.113549.1.1.4` | `md5_rsa` |
| `1.2.840.113549.1.1.5` | `sha1_rsa` |
| `1.2.840.113549.1.1.2` | `md2_rsa` |
| `1.2.840.113549.1.1.14` | `sha224_rsa` |
| `1.2.840.113549.1.1.11` | `sha256_rsa` |
| `1.2.840.113549.1.1.12` | `sha384_rsa` |
| `1.2.840.113549.1.1.13` | `sha512_rsa` |
| `1.2.840.113549.1.1.10` | `rsassa_pss` |
| `1.2.840.10040.4.3` | `sha1_dsa` |
| `2.16.840.1.101.3.4.3.1` | `sha224_dsa` |
| `2.16.840.1.101.3.4.3.2` | `sha256_dsa` |
| `2.16.840.1.101.3.4.3.3` | `sha384_dsa` |
| `2.16.840.1.101.3.4.3.4` | `sha512_dsa` |
| `1.2.840.10045.4.1` | `sha1_ecdsa` |
| `1.2.840.10045.4.3.1` | `sha224_ecdsa` |
| `1.2.840.10045.4.3.2` | `sha256_ecdsa` |
| `1.2.840.10045.4.3.3` | `sha384_ecdsa` |
| `1.2.840.10045.4.3.4` | `sha512_ecdsa` |
| `2.16.840.1.101.3.4.3.5` | `sha3_224_dsa` |
| `2.16.840.1.101.3.4.3.6` | `sha3_256_dsa` |
| `2.16.840.1.101.3.4.3.7` | `sha3_384_dsa` |
| `2.16.840.1.101.3.4.3.8` | `sha3_512_dsa` |
| `2.16.840.1.101.3.4.3.9` | `sha3_224_ecdsa` |
| `2.16.840.1.101.3.4.3.10` | `sha3_256_ecdsa` |
| `2.16.840.1.101.3.4.3.11` | `sha3_384_ecdsa` |
| `2.16.840.1.101.3.4.3.12` | `sha3_512_ecdsa` |
| `2.16.840.1.101.3.4.3.13` | `sha3_224_rsa` |
| `2.16.840.1.101.3.4.3.14` | `sha3_256_rsa` |
| `2.16.840.1.101.3.4.3.15` | `sha3_384_rsa` |
| `2.16.840.1.101.3.4.3.16` | `sha3_512_rsa` |
| `1.2.840.113549.1.1.1` | `rsassa_pkcs1v15` |
| `1.2.840.10040.4.1` | `dsa` |
| `1.2.840.10045.4` | `ecdsa` |
| `1.3.101.112` | `ed25519` |
| `1.3.101.113` | `ed448` |
| `0.4.0.127.0.7.1.1.4.1.1` | `sha1_ecdsa_plain` |
| `0.4.0.127.0.7.1.1.4.1.2` | `sha224_ecdsa_plain` |
| `0.4.0.127.0.7.1.1.4.1.3` | `sha256_ecdsa_plain` |
| `0.4.0.127.0.7.1.1.4.1.4` | `sha384_ecdsa_plain` |
| `0.4.0.127.0.7.1.1.4.1.5` | `sha512_ecdsa_plain` |
| `0.4.0.127.0.7.1.1.4.1.8` | `sha3_224_ecdsa_plain` |
| `0.4.0.127.0.7.1.1.4.1.9` | `sha3_256_ecdsa_plain` |
| `0.4.0.127.0.7.1.1.4.1.10` | `sha3_384_ecdsa_plain` |
| `0.4.0.127.0.7.1.1.4.1.11` | `sha3_512_ecdsa_plain` |

### Derivation algorithm OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.2.840.113549.1.5.12` | `pbkdf2` |
| `1.3.6.1.4.1.11591.4.11` | `scrypt` |

### Key-exchange algorithm OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.2.840.113549.1.3.1` | `dh` |

### RC5 parameter version

| Numeric identity | Text identity |
| --- | --- |
| `16` | `v1-0` |

### OAEP source OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.2.840.113549.1.1.9` | `p_specified` |

### Encryption algorithm OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.3.14.3.2.7` | `des` |
| `1.2.840.113549.3.7` | `tripledes_3key` |
| `1.2.840.113549.3.2` | `rc2` |
| `1.2.840.113549.3.4` | `rc4` |
| `1.2.840.113549.3.9` | `rc5` |
| `2.16.840.1.101.3.4.1.1` | `aes128_ecb` |
| `2.16.840.1.101.3.4.1.2` | `aes128_cbc` |
| `2.16.840.1.101.3.4.1.3` | `aes128_ofb` |
| `2.16.840.1.101.3.4.1.4` | `aes128_cfb` |
| `2.16.840.1.101.3.4.1.5` | `aes128_wrap` |
| `2.16.840.1.101.3.4.1.6` | `aes128_gcm` |
| `2.16.840.1.101.3.4.1.7` | `aes128_ccm` |
| `2.16.840.1.101.3.4.1.8` | `aes128_wrap_pad` |
| `2.16.840.1.101.3.4.1.21` | `aes192_ecb` |
| `2.16.840.1.101.3.4.1.22` | `aes192_cbc` |
| `2.16.840.1.101.3.4.1.23` | `aes192_ofb` |
| `2.16.840.1.101.3.4.1.24` | `aes192_cfb` |
| `2.16.840.1.101.3.4.1.25` | `aes192_wrap` |
| `2.16.840.1.101.3.4.1.26` | `aes192_gcm` |
| `2.16.840.1.101.3.4.1.27` | `aes192_ccm` |
| `2.16.840.1.101.3.4.1.28` | `aes192_wrap_pad` |
| `2.16.840.1.101.3.4.1.41` | `aes256_ecb` |
| `2.16.840.1.101.3.4.1.42` | `aes256_cbc` |
| `2.16.840.1.101.3.4.1.43` | `aes256_ofb` |
| `2.16.840.1.101.3.4.1.44` | `aes256_cfb` |
| `2.16.840.1.101.3.4.1.45` | `aes256_wrap` |
| `2.16.840.1.101.3.4.1.46` | `aes256_gcm` |
| `2.16.840.1.101.3.4.1.47` | `aes256_ccm` |
| `2.16.840.1.101.3.4.1.48` | `aes256_wrap_pad` |
| `1.2.840.113549.1.5.13` | `pbes2` |
| `1.2.840.113549.1.5.1` | `pbes1_md2_des` |
| `1.2.840.113549.1.5.3` | `pbes1_md5_des` |
| `1.2.840.113549.1.5.4` | `pbes1_md2_rc2` |
| `1.2.840.113549.1.5.6` | `pbes1_md5_rc2` |
| `1.2.840.113549.1.5.10` | `pbes1_sha1_des` |
| `1.2.840.113549.1.5.11` | `pbes1_sha1_rc2` |
| `1.2.840.113549.1.12.1.1` | `pkcs12_sha1_rc4_128` |
| `1.2.840.113549.1.12.1.2` | `pkcs12_sha1_rc4_40` |
| `1.2.840.113549.1.12.1.3` | `pkcs12_sha1_tripledes_3key` |
| `1.2.840.113549.1.12.1.4` | `pkcs12_sha1_tripledes_2key` |
| `1.2.840.113549.1.12.1.5` | `pkcs12_sha1_rc2_128` |
| `1.2.840.113549.1.12.1.6` | `pkcs12_sha1_rc2_40` |
| `1.2.840.113549.1.1.1` | `rsaes_pkcs1v15` |
| `1.2.840.113549.1.1.7` | `rsaes_oaep` |

### Password-MAC OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.2.840.113549.1.5.14` | `pbmac1` |

## `cobaltform.algos.AlgorithmIdentifier`

Import `AlgorithmIdentifier` from `cobaltform.algos`. `AlgorithmIdentifier(value)` accepts a field mapping; `load(encoded_data)` accepts ASN.1 `bytes`. Both return a record with string field indexing, field assignment, `native` mapping and `dump() -> bytes`.

### Description fields

| Field | Exchanged value |
| --- | --- |
| `algorithm` | OID object: `native` is a name or numeric identity string; `dotted` is the dotted numeric identity string. |
| `parameters` | Typed parameter value or open ASN.1 value; `native` exposes its Python value and `dump()` its ASN.1 bytes. |

## `cobaltform.algos.AnyAlgorithmIdentifier`

Import `AnyAlgorithmIdentifier` from `cobaltform.algos`. `AnyAlgorithmIdentifier.load(encoded_data)` accepts ASN.1 `bytes` and returns a record with string field indexing, field assignment, `native` mapping and `dump() -> bytes`.

### Description fields

| Field | Exchanged value |
| --- | --- |
| `algorithm` | OID object: `native` is a name or numeric identity string; `dotted` is the dotted numeric identity string. |
| `parameters` | Typed parameter value or open ASN.1 value; `native` exposes its Python value and `dump()` its ASN.1 bytes. |

## `cobaltform.algos.DSASignature`

Import `DSASignature` from `cobaltform.algos`. `DSASignature(value)` accepts a mapping and `load(encoded_data)` accepts ASN.1 `bytes`, returning a typed record. `dump()` returns ASN.1 signature `bytes`.

### Signature fields

| Field | Exchanged value |
| --- | --- |
| `r` | Integer first signature component. |
| `s` | Integer second signature component. |

`from_p1363(data)` is a class method accepting binary integer-pair `bytes` and returning a `DSASignature`. `to_p1363(width=<int>)` returns unsigned big-endian bytes for the first component followed by the second, in equal-width halves; `width` is the optional byte width of each half. A refused width raises `ValueError`.

## `cobaltform.algos.DigestAlgorithm`

Import `DigestAlgorithm` from `cobaltform.algos`. `DigestAlgorithm(value)` accepts a field mapping; `load(encoded_data)` accepts ASN.1 `bytes`. Both return a record with string field indexing, field assignment, `native` mapping and `dump() -> bytes`.

### Description fields

| Field | Exchanged value |
| --- | --- |
| `algorithm` | OID object: `native` is a name or numeric identity string; `dotted` is the dotted numeric identity string. |
| `parameters` | Typed parameter value or open ASN.1 value; `native` exposes its Python value and `dump()` its ASN.1 bytes. |

## `cobaltform.algos.EncryptionAlgorithm`

Import `EncryptionAlgorithm` from `cobaltform.algos`. `EncryptionAlgorithm(value)` accepts a field mapping; `load(encoded_data)` accepts ASN.1 `bytes`. Both return a record with string field indexing, field assignment, `native` mapping and `dump() -> bytes`.

### Description fields

| Field | Exchanged value |
| --- | --- |
| `algorithm` | OID object: `native` is a name or numeric identity string; `dotted` is the dotted numeric identity string. |
| `parameters` | Typed parameter value or open ASN.1 value; `native` exposes its Python value and `dump()` its ASN.1 bytes. |

### OAEP parameter fields

| Field | Exchanged value |
| --- | --- |
| `hash_algorithm` | Digest description. |
| `mask_gen_algorithm` | Description with `algorithm` and digest-description `parameters`. |
| `p_source_algorithm` | Description with `algorithm` and binary `parameters` for the source label. |

### RC2 parameter fields

| Field | Exchanged value |
| --- | --- |
| `rc2_parameter_version` | Integer parameter version. |
| `iv` | Initialization-vector bytes. |

### RC5 parameter fields

| Field | Exchanged value |
| --- | --- |
| `version` | Named parameter-version string. |
| `rounds` | Integer round count. |
| `block_size_in_bits` | Integer bit count. |
| `iv` | Initialization-vector bytes. |

### CCM parameter fields

| Field | Exchanged value |
| --- | --- |
| `aes_nonce` | Nonce bytes. |
| `aes_icvlen` | Integer authentication-tag byte count. |

### Password parameter fields

| Field | Exchanged value |
| --- | --- |
| `salt` | Salt bytes. |
| `iterations` | Integer iteration count. |

### PBES2 parameter fields

| Field | Exchanged value |
| --- | --- |
| `key_derivation_func` | Derivation description with `algorithm` and structured `parameters`. |
| `encryption_scheme` | Encryption description with `algorithm` and `parameters`. |

`kdf` returns `str`, representing the derivation family.

`kdf_hmac` returns `str`, representing the derivation digest.

`kdf_salt` returns `bytes`, representing the salt. Unavailable parameter information raises `ValueError`.

`kdf_iterations` returns `int`, representing the iteration count.

`key_length` returns `int`, representing the key length in bytes.

`encryption_mode` returns `str`, representing the cipher mode.

`encryption_cipher` returns `str`, representing the cipher identity.

`encryption_block_size` returns `int`, representing the block size in bytes.

`encryption_iv` returns `bytes | None`, representing the stored initialization vector or its absence.

DES, TripleDES, AES CBC and AES OFB parameters use ASN.1 OCTET STRING and accept binary `bytes`. RC2, RC5 and CCM parameter records use SEQUENCE in their table orders, with INTEGER members and OCTET STRING vectors or nonces. Other open parameters accept typed ASN.1 values.

## `cobaltform.algos.HmacAlgorithm`

Import `HmacAlgorithm` from `cobaltform.algos`. `HmacAlgorithm(value)` accepts a field mapping; `load(encoded_data)` accepts ASN.1 `bytes`. Both return a record with string field indexing, field assignment, `native` mapping and `dump() -> bytes`.

### Description fields

| Field | Exchanged value |
| --- | --- |
| `algorithm` | OID object: `native` is a name or numeric identity string; `dotted` is the dotted numeric identity string. |
| `parameters` | Typed parameter value or open ASN.1 value; `native` exposes its Python value and `dump()` its ASN.1 bytes. |

## `cobaltform.algos.KdfAlgorithm`

Import `KdfAlgorithm` from `cobaltform.algos`. `KdfAlgorithm(value)` accepts a field mapping; `load(encoded_data)` accepts ASN.1 `bytes`. Both return a record with string field indexing, field assignment, `native` mapping and `dump() -> bytes`.

### Description fields

| Field | Exchanged value |
| --- | --- |
| `algorithm` | OID object: `native` is a name or numeric identity string; `dotted` is the dotted numeric identity string. |
| `parameters` | Typed parameter value or open ASN.1 value; `native` exposes its Python value and `dump()` its ASN.1 bytes. |

### PBKDF2 parameter fields

| Field | Exchanged value |
| --- | --- |
| `salt` | Choice value with `name: str`, `chosen`, and `native`; supplied salt bytes or an algorithm-description record. |
| `iteration_count` | Integer iteration count. |
| `key_length` | Integer byte count or absent field. |
| `prf` | MAC description with `algorithm` and `parameters`. |

The salt choice identifiers are `specified` for salt bytes and `other_source` for an algorithm-description record.

### Scrypt parameter fields

| Field | Exchanged value |
| --- | --- |
| `salt` | Salt bytes. |
| `cost_parameter` | Integer cost parameter. |
| `block_size` | Integer block-size parameter. |
| `parallelization_parameter` | Integer parallelization parameter. |
| `key_length` | Integer byte count or absent field. |

## `cobaltform.algos.KeyExchangeAlgorithm`

Import `KeyExchangeAlgorithm` from `cobaltform.algos`. `KeyExchangeAlgorithm(value)` accepts a field mapping; `load(encoded_data)` accepts ASN.1 `bytes`. Both return a record with string field indexing, field assignment, `native` mapping and `dump() -> bytes`.

### Description fields

| Field | Exchanged value |
| --- | --- |
| `algorithm` | OID object: `native` is a name or numeric identity string; `dotted` is the dotted numeric identity string. |
| `parameters` | Typed parameter value or open ASN.1 value; `native` exposes its Python value and `dump()` its ASN.1 bytes. |

### DH parameter fields

| Field | Exchanged value |
| --- | --- |
| `p` | Integer domain prime. |
| `g` | Integer generator. |
| `private_value_length` | Integer length or absent field. |

## `cobaltform.algos.Pkcs5MacAlgorithm`

Import `Pkcs5MacAlgorithm` from `cobaltform.algos`. `Pkcs5MacAlgorithm(value)` accepts a field mapping; `load(encoded_data)` accepts ASN.1 `bytes`. Both return a record with string field indexing, field assignment, `native` mapping and `dump() -> bytes`.

### Description fields

| Field | Exchanged value |
| --- | --- |
| `algorithm` | OID object: `native` is a name or numeric identity string; `dotted` is the dotted numeric identity string. |
| `parameters` | Typed parameter value or open ASN.1 value; `native` exposes its Python value and `dump()` its ASN.1 bytes. |

### PBMAC1 parameter fields

| Field | Exchanged value |
| --- | --- |
| `key_derivation_func` | Derivation description with `algorithm` and `parameters`. |
| `message_auth_scheme` | MAC description with `algorithm` and `parameters`. |

## `cobaltform.algos.SignedDigestAlgorithm`

Import `SignedDigestAlgorithm` from `cobaltform.algos`. `SignedDigestAlgorithm(value)` accepts a field mapping; `load(encoded_data)` accepts ASN.1 `bytes`. Both return a record with string field indexing, field assignment, `native` mapping and `dump() -> bytes`.

### Description fields

| Field | Exchanged value |
| --- | --- |
| `algorithm` | OID object: `native` is a name or numeric identity string; `dotted` is the dotted numeric identity string. |
| `parameters` | Typed parameter value or open ASN.1 value; `native` exposes its Python value and `dump()` its ASN.1 bytes. |

`signature_algo` is a signature-family string. Unavailable information is signalled by `ValueError`.

`hash_algo` is a digest-identity string. Unavailable information is signalled by `ValueError`.

`cms_hash_algo` is a CMS digest-identity string. Unavailable information is signalled by `ValueError`.

### Structured signature parameters

| Field | Exchanged value |
| --- | --- |
| `hash_algorithm` | Digest description with `algorithm` and `parameters`. |
| `mask_gen_algorithm` | Description with `algorithm` and a digest description in `parameters`. |
| `salt_length` | Integer byte count. |
| `trailer_field` | Named trailer identifier string. |

## `cobaltform.cms`

`cobaltform.cms` exposes the following public names:

- `AttCertIssuer`

- `AttCertSubject`

- `AttributeCertificateV1`

- `CertificateChoices`

- `ContentInfo`

- `DigestedData`

- `EncapsulatedContentInfo`

- `IetfAttrValue`

- `KeyAgreementRecipientIdentifier`

- `OriginatorIdentifierOrKey`

- `RecipientIdentifier`

- `RecipientInfo`

- `RevocationInfoChoice`

- `SMIMEEncryptionKeyPreference`

- `SignerIdentifier`

- `Time`

### CMS version

| Numeric identity | Text identity |
| --- | --- |
| `0` | `v0` |
| `1` | `v1` |
| `2` | `v2` |
| `3` | `v3` |
| `4` | `v4` |

### CMS attribute OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.2.840.113549.1.9.3` | `content_type` |
| `1.2.840.113549.1.9.4` | `message_digest` |
| `1.2.840.113549.1.9.5` | `signing_time` |
| `1.2.840.113549.1.9.6` | `counter_signature` |
| `1.2.840.113549.1.9.15` | `smime_capabilities` |
| `1.2.840.113549.1.9.16.2.11` | `encrypt_key_pref` |
| `1.2.840.113549.1.9.16.2.14` | `signature_time_stamp_token` |
| `1.2.840.113549.1.9.52` | `cms_algorithm_protection` |
| `1.3.6.1.4.1.311.2.4.1` | `microsoft_nested_signature` |
| `1.3.6.1.4.1.311.3.3.1` | `microsoft_time_stamp_token` |

### Content-type OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.2.840.113549.1.7.1` | `data` |
| `1.2.840.113549.1.7.2` | `signed_data` |
| `1.2.840.113549.1.7.3` | `enveloped_data` |
| `1.2.840.113549.1.7.4` | `signed_and_enveloped_data` |
| `1.2.840.113549.1.7.5` | `digested_data` |
| `1.2.840.113549.1.7.6` | `encrypted_data` |
| `1.2.840.113549.1.9.16.1.2` | `authenticated_data` |
| `1.2.840.113549.1.9.16.1.9` | `compressed_data` |
| `1.2.840.113549.1.9.16.1.23` | `authenticated_enveloped_data` |

### Attribute-certificate version

| Numeric identity | Text identity |
| --- | --- |
| `0` | `v1` |
| `1` | `v2` |

### Clearance bit positions

| Numeric identity | Text identity |
| --- | --- |
| `1` | `unclassified` |
| `2` | `restricted` |
| `4` | `secret` |
| `5` | `top_secret` |

### Attribute-certificate attribute OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.3.6.1.5.5.7.10.1` | `authentication_info` |
| `1.3.6.1.5.5.7.10.2` | `access_identity` |
| `1.3.6.1.5.5.7.10.3` | `charging_identity` |
| `1.3.6.1.5.5.7.10.4` | `group` |
| `2.5.4.72` | `role` |
| `2.5.4.55` | `clearance` |
| `1.3.6.1.4.1.601.10.4.1` | `timing_metrics` |
| `1.3.6.1.4.1.601.10.4.2` | `timing_policy` |

### Other revocation-format OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.3.6.1.5.5.7.16.2` | `ocsp_response` |
| `1.3.6.1.5.5.7.16.4` | `scvp` |

### Compression algorithm OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.2.840.113549.1.9.16.3.8` | `zlib` |

## `cobaltform.cms.AttCertIssuer`

Import `AttCertIssuer` from `cobaltform.cms`. `AttCertIssuer((name, value))` constructs a choice. `name` is its alternative identifier, `chosen` its typed value, and `native` the selected Python value. The choice has the shared ASN.1 value interfaces.

Alternative input names and value shapes:

| Alternative | Value |
| --- | --- |
| `v2_form` | Record with `issuer_name` general-name collection. |

## `cobaltform.cms.AttCertSubject`

Import `AttCertSubject` from `cobaltform.cms`. `AttCertSubject((name, value))` constructs a choice. `name` is its alternative identifier, `chosen` its typed value, and `native` the selected Python value. The choice has the shared ASN.1 value interfaces.

Alternative input names and value shapes:

| Alternative | Value |
| --- | --- |
| `subject_name` | General-name collection. |

## `cobaltform.cms.AttributeCertificateV1`

Import `AttributeCertificateV1` from `cobaltform.cms`. `AttributeCertificateV1.load(encoded_data)` accepts ASN.1 bytes and returns an attribute-certificate record with string field access, `native` and `dump() -> bytes`.

### Attribute-certificate fields

| Field | Exchanged value |
| --- | --- |
| `ac_info` | Attribute-certificate information record. |
| `signature_algorithm` | Signature description. |
| `signature` | Signature bytes. |

### Version-one information fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `subject` | `AttCertSubject`. |
| `issuer` | General-name collection. |
| `signature` | Signature description. |
| `serial_number` | Integer. |
| `att_cert_validity_period` | Validity record with date-time fields `not_before_time` and `not_after_time`. |
| `attributes` | Collection of attributes with OID `type` and `values` collection. |

## `cobaltform.cms.CertificateChoices`

Import `CertificateChoices` from `cobaltform.cms`. `CertificateChoices((name, value))` constructs a choice. `name` is its alternative identifier, `chosen` its typed value, and `native` the selected Python value. The choice has the shared ASN.1 value interfaces.

Alternative input names and value shapes:

| Alternative | Value |
| --- | --- |
| `certificate` | `Certificate`. |
| `extended_certificate` | Extended-certificate record. |
| `v1_attr_cert` | Version-one attribute certificate. |
| `v2_attr_cert` | Version-two attribute certificate. |
| `other` | Other-certificate record. |

### Extended-certificate fields

| Field | Exchanged value |
| --- | --- |
| `extended_certificate_info` | Record containing integer `version`, `certificate` and `attributes`. |
| `signature_algorithm` | Signature description. |
| `signature` | Signature bytes. |

### Extended-certificate information fields

| Field | Exchanged value |
| --- | --- |
| `version` | Integer. |
| `certificate` | `Certificate`. |
| `attributes` | Collection of open attribute records with `type` OID and `values` collection. |

### Other-certificate fields

| Field | Exchanged value |
| --- | --- |
| `other_cert_format` | OID with `dotted` numeric identity. |
| `other_cert` | Open ASN.1 value. |

### Attribute-certificate fields

| Field | Exchanged value |
| --- | --- |
| `ac_info` | Attribute-certificate information record. |
| `signature_algorithm` | Signature description. |
| `signature` | Signature bytes. |

### Version-two information fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `holder` | Record with general-name collection `entity_name`. |
| `issuer` | `AttCertIssuer`. |
| `signature` | Signature description. |
| `serial_number` | Integer. |
| `att_cert_validity_period` | Record with date-times `not_before_time` and `not_after_time`. |
| `attributes` | Attribute-certificate attribute collection. |

### Attribute fields

| Field | Exchanged value |
| --- | --- |
| `type` | OID object with name-or-identity `native`. |
| `values` | Collection of typed attribute values. |

### Authentication fields

| Field | Exchanged value |
| --- | --- |
| `service` | General-name value. |
| `ident` | General-name value. |
| `auth_info` | Bytes or absent field. |

### Group or charging fields

| Field | Exchanged value |
| --- | --- |
| `policy_authority` | General-name list or absent field. |
| `values` | `IetfAttrValue` collection. |

### Role fields

| Field | Exchanged value |
| --- | --- |
| `role_authority` | General-name list or absent field. |
| `role_name` | General-name value. |

### Clearance fields

| Field | Exchanged value |
| --- | --- |
| `policy_id` | OID string. |
| `class_list` | Set of class-name strings. |
| `security_categories` | Category collection or absent field. |

### Security-category fields

| Field | Exchanged value |
| --- | --- |
| `type` | OID string. |
| `value` | Open ASN.1 value. |

### Timing-metric fields

| Field | Exchanged value |
| --- | --- |
| `ntp_time` | Time-component record. |
| `offset` | Time-component record. |
| `delay` | Time-component record. |
| `expiration` | Time-component record. |
| `leap_event` | Leap-event collection or absent field. |

### Time-component fields

| Field | Exchanged value |
| --- | --- |
| `major` | Integer. |
| `fractional_seconds` | Integer. |
| `sign` | Integer or absent field. |

### Leap-event fields

| Field | Exchanged value |
| --- | --- |
| `leap_time` | Time-component record. |
| `action` | Integer. |

### Timing-policy fields

| Field | Exchanged value |
| --- | --- |
| `policy_id` | OID string list. |
| `max_offset` | Time-component record or absent field. |
| `max_delay` | Time-component record or absent field. |

Timing metrics, timing policies, time components and leap-event records use ASN.1 SEQUENCE in their respective table orders. Time-component members and leap actions use INTEGER. Leap events use SET OF. Policy identities use SEQUENCE OF OBJECT IDENTIFIER; maximum offset and delay use context-specific explicit tags 0 and 1 around time-component records. Timing-attribute values use SET OF.

## `cobaltform.cms.ContentInfo`

Import `ContentInfo` from `cobaltform.cms`. `ContentInfo(value)` accepts a field mapping; `load(encoded_data)` accepts ASN.1 bytes. The returned record supports named field indexing and assignment, nested `native` values, and `dump() -> bytes`.

### Content fields

| Field | Exchanged value |
| --- | --- |
| `content_type` | OID object with name-or-identity `native` and numeric `dotted` strings. |
| `content` | Typed content record, binary value, or absent field. |

An `encap_content_info` record has `content_type` and `content` fields. The content is a binary value or typed document in a direct-content form, and an embedded value exposing `parsed` in an octet-carried form. An absent `content` uses the shared absence form.

### Signed-content fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `digest_algorithms` | Collection of digest descriptions. |
| `encap_content_info` | Encapsulation record. |
| `certificates` | Certificate-choice collection or absent field. |
| `crls` | Revocation-choice collection or absent field. |
| `signer_infos` | Signer-information collection. |

### Signer-information fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `sid` | `SignerIdentifier`. |
| `digest_algorithm` | Digest description. |
| `signed_attrs` | CMS attribute collection or absent field. |
| `signature_algorithm` | Signature description. |
| `signature` | Signature bytes. |
| `unsigned_attrs` | CMS attribute collection or absent field. |

### CMS attribute fields

| Field | Exchanged value |
| --- | --- |
| `type` | OID object with name-or-identity `native` and numeric `dotted` strings. |
| `values` | Indexed, iterable typed-value collection with list `native`. Open values retain `native` and `dump()`. |

### Encrypted-content fields

| Field | Exchanged value |
| --- | --- |
| `content_type` | OID name or identity string. |
| `content_encryption_algorithm` | Description with `algorithm` and `parameters`. |
| `encrypted_content` | Ciphertext bytes or absent field. |

### Enveloped-content fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `recipient_infos` | Recipient-choice collection. |
| `encrypted_content_info` | Encrypted-content record. |

### Signed-and-enveloped-content fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `recipient_infos` | Recipient-choice collection. |
| `digest_algorithms` | Digest-description collection. |
| `encrypted_content_info` | Encrypted-content record. |
| `signer_infos` | Signer-information collection. |

### Encrypted-data fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `encrypted_content_info` | Encrypted-content record. |

### Authenticated-content fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `recipient_infos` | Recipient-choice collection. |
| `mac_algorithm` | MAC description. |
| `digest_algorithm` | Digest description or absent field. |
| `encap_content_info` | Encapsulation record. |
| `auth_attrs` | Attribute collection or absent field. |
| `mac` | Authentication bytes. |
| `unauth_attrs` | Attribute collection or absent field. |

### Authenticated-enveloped-content fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `recipient_infos` | Recipient-choice collection. |
| `auth_encrypted_content_info` | Encrypted-content record. |
| `mac` | Authentication bytes. |

### Compressed-content fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `compression_algorithm` | Description with `algorithm`. |
| `encap_content_info` | Encapsulation record with compressed content bytes. |

A compressed content record exposes `decompressed` as bytes. Invalid-compressed-data rejection is signalled by `zlib.error`.

### S/MIME capability fields

| Field | Exchanged value |
| --- | --- |
| `capability_id` | Algorithm identity string. |
| `parameters` | Open ASN.1 value or absent field. |

### Algorithm-protection fields

| Field | Exchanged value |
| --- | --- |
| `digest_algorithm` | Digest description. |
| `signature_algorithm` | Signature description or absent field. |
| `mac_algorithm` | MAC description or absent field. |

A CMS signing-certificate attribute has its signing-certificate record at `values[index]`.

### Signing-certificate fields

| Field | Exchanged value |
| --- | --- |
| `certs` | Certificate-reference collection. |
| `policies` | Policy-information collection or absent field. |

### Certificate-reference fields

| Field | Exchanged value |
| --- | --- |
| `cert_hash` | Bytes. |
| `issuer_serial` | Issuer-and-serial record or absent field. |

### Version-two certificate-reference fields

| Field | Exchanged value |
| --- | --- |
| `hash_algorithm` | Digest description. |
| `cert_hash` | Bytes. |
| `issuer_serial` | Issuer-and-serial record or absent field. |

### Issuer-and-serial fields

| Field | Exchanged value |
| --- | --- |
| `issuer` | List of general-name values. |
| `serial_number` | Integer. |

## `cobaltform.cms.DigestedData`

Import `DigestedData` from `cobaltform.cms`. `DigestedData(value)` accepts a field mapping and returns an ASN.1 record supporting named field access, `native` and `dump() -> bytes`.

### Digested-content fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `digest_algorithm` | Digest description. |
| `encap_content_info` | Encapsulation record with `content_type` and `content`. |
| `digest` | Digest bytes. |

## `cobaltform.cms.EncapsulatedContentInfo`

Import `EncapsulatedContentInfo` from `cobaltform.cms`. `EncapsulatedContentInfo(value)` accepts a field mapping and `load(encoded_data)` accepts ASN.1 bytes. The record supports `native`, `dump() -> bytes` and named field access.

### Encapsulation fields

| Field | Exchanged value |
| --- | --- |
| `content_type` | OID object with name-or-identity `native`. |
| `content` | Embedded value exposing `native` and a typed `parsed` document, or absent field. |

## `cobaltform.cms.IetfAttrValue`

Import `IetfAttrValue` from `cobaltform.cms`. `IetfAttrValue((name, value))` constructs a choice. `name` is its alternative identifier, `chosen` its typed value, and `native` the selected Python value. The choice has the shared ASN.1 value interfaces.

Alternative input names and value shapes:

| Alternative | Value |
| --- | --- |
| `octets` | Bytes. |
| `oid` | Dotted identity string. |
| `string` | Text. |

## `cobaltform.cms.KeyAgreementRecipientIdentifier`

Import `KeyAgreementRecipientIdentifier` from `cobaltform.cms`. `KeyAgreementRecipientIdentifier((name, value))` constructs a choice. `name` is its alternative identifier, `chosen` its typed value, and `native` the selected Python value. The choice has the shared ASN.1 value interfaces.

Alternative input names and value shapes:

| Alternative | Value |
| --- | --- |
| `r_key_id` | Record containing `subject_key_identifier` bytes, optional `date` date-time, and optional `other` key attribute. |

## `cobaltform.cms.OriginatorIdentifierOrKey`

Import `OriginatorIdentifierOrKey` from `cobaltform.cms`. `OriginatorIdentifierOrKey((name, value))` constructs a choice. `name` is its alternative identifier, `chosen` its typed value, and `native` the selected Python value. The choice has the shared ASN.1 value interfaces.

Alternative input names and value shapes:

| Alternative | Value |
| --- | --- |
| `subject_key_identifier` | Identifier bytes. |

## `cobaltform.cms.RecipientIdentifier`

Import `RecipientIdentifier` from `cobaltform.cms`. `RecipientIdentifier((name, value))` constructs a choice. `name` is its alternative identifier, `chosen` its typed value, and `native` the selected Python value. The choice has the shared ASN.1 value interfaces.

Alternative input names and value shapes:

| Alternative | Value |
| --- | --- |
| `issuer_and_serial_number` | Mapping with `issuer` (`Name`) and `serial_number` (integer). |
| `subject_key_identifier` | Identifier bytes. |

## `cobaltform.cms.RecipientInfo`

Import `RecipientInfo` from `cobaltform.cms`. `RecipientInfo((name, value))` constructs a choice. `name` is its alternative identifier, `chosen` its typed value, and `native` the selected Python value. The choice has the shared ASN.1 value interfaces.

Alternative input names and value shapes:

| Alternative | Value |
| --- | --- |
| `ktri` | Key-transport recipient record. |
| `kari` | Key-agreement recipient record. |
| `kekri` | Key-encryption-key recipient record. |
| `pwri` | Password recipient record. |
| `ori` | Other-recipient record. |

### Key-transport recipient fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `rid` | `RecipientIdentifier`. |
| `key_encryption_algorithm` | Algorithm description. |
| `encrypted_key` | Bytes. |

### Key-agreement recipient fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `originator` | `OriginatorIdentifierOrKey`. |
| `ukm` | Bytes or absent field. |
| `key_encryption_algorithm` | Algorithm description. |
| `recipient_encrypted_keys` | Collection of recipient encrypted-key records. |

### Key-encryption-key recipient fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `kekid` | Key-identifier record. |
| `key_encryption_algorithm` | Algorithm description. |
| `encrypted_key` | Bytes. |

### Password recipient fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `key_derivation_algorithm` | Derivation description or absent field. |
| `key_encryption_algorithm` | Algorithm description. |
| `encrypted_key` | Bytes. |

### Other-recipient fields

| Field | Exchanged value |
| --- | --- |
| `ori_type` | OID with `dotted` numeric identity. |
| `ori_value` | Open ASN.1 value. |

### Recipient encrypted-key fields

| Field | Exchanged value |
| --- | --- |
| `rid` | `KeyAgreementRecipientIdentifier`. |
| `encrypted_key` | Bytes. |

### Key-identifier fields

| Field | Exchanged value |
| --- | --- |
| `key_identifier` | Bytes. |
| `date` | Date-time or absent field. |
| `other` | Key-attribute record or absent field. |

### Recipient key-identifier fields

| Field | Exchanged value |
| --- | --- |
| `subject_key_identifier` | Bytes. |
| `date` | Date-time or absent field. |
| `other` | Key-attribute record or absent field. |

### Key-attribute fields

| Field | Exchanged value |
| --- | --- |
| `key_attr_id` | OID string. |
| `key_attr` | Open ASN.1 value. |

## `cobaltform.cms.RevocationInfoChoice`

Import `RevocationInfoChoice` from `cobaltform.cms`. `RevocationInfoChoice((name, value))` constructs a choice. `name` is its alternative identifier, `chosen` its typed value, and `native` the selected Python value. The choice has the shared ASN.1 value interfaces.

Alternative input names and value shapes:

| Alternative | Value |
| --- | --- |
| `crl` | `CertificateList`. |
| `other` | Record containing `other_rev_info_format` OID and open or typed `other_rev_info`. |

### Other-revocation fields

| Field | Exchanged value |
| --- | --- |
| `other_rev_info_format` | OID object with name-or-identity `native`. |
| `other_rev_info` | Typed response, SCVP record, or open ASN.1 value. |

### SCVP fields

| Field | Exchanged value |
| --- | --- |
| `request` | `ContentInfo` or absent field. |
| `response` | `ContentInfo`. |

## `cobaltform.cms.SMIMEEncryptionKeyPreference`

Import `SMIMEEncryptionKeyPreference` from `cobaltform.cms`. `SMIMEEncryptionKeyPreference((name, value))` constructs a choice. `name` is its alternative identifier, `chosen` its typed value, and `native` the selected Python value. The choice has the shared ASN.1 value interfaces.

Alternative input names and value shapes:

| Alternative | Value |
| --- | --- |
| `recipient_key_id` | Recipient key-identifier record. |

## `cobaltform.cms.SignerIdentifier`

Import `SignerIdentifier` from `cobaltform.cms`. `SignerIdentifier((name, value))` constructs a choice. `name` is its alternative identifier, `chosen` its typed value, and `native` the selected Python value. The choice has the shared ASN.1 value interfaces.

Alternative input names and value shapes:

| Alternative | Value |
| --- | --- |
| `issuer_and_serial_number` | Mapping with `issuer` (`Name`) and `serial_number` (integer). |
| `subject_key_identifier` | Identifier bytes. |

## `cobaltform.cms.Time`

Import `Time` from `cobaltform.cms`. `Time((name, value))` constructs a choice. `name` is its alternative identifier, `chosen` its typed value, and `native` the selected Python value. The choice has the shared ASN.1 value interfaces.

Alternative input names and value shapes:

| Alternative | Value |
| --- | --- |
| `utc_time` | Date-time. |
| `generalized_time` | Date-time. |

## `cobaltform.core`

`cobaltform.core` exposes the following public names:

- `Any`

- `Asn1Value`

- `BMPString`

- `BitString`

- `Boolean`

- `CharacterString`

- `Choice`

- `Concat`

- `Enumerated`

- `GeneralString`

- `GeneralizedTime`

- `GraphicString`

- `IA5String`

- `Integer`

- `IntegerBitString`

- `IntegerOctetString`

- `Null`

- `NumericString`

- `ObjectIdentifier`

- `OctetBitString`

- `OctetString`

- `ParsableOctetBitString`

- `ParsableOctetString`

- `PrintableString`

- `Sequence`

- `SequenceOf`

- `Set`

- `SetOf`

- `TeletexString`

- `UTCTime`

- `UTF8String`

- `UniversalString`

- `VideotexString`

- `VisibleString`

## `cobaltform.core.Any`

Import `Any` from `cobaltform.core`. `Any(value)` accepts a typed ASN.1 value. `load(encoded_data)` accepts ASN.1 `bytes`. `parse(spec)` takes an ASN.1 class and returns a typed object; `parsed` exposes the parsed object. `native` exposes its Python value. `dump()` returns ASN.1 `bytes`. Interpretation rejection is `ValueError`.

## `cobaltform.core.Asn1Value`

Import `Asn1Value` from `cobaltform.core`. `Asn1Value.load(encoded_data)` accepts `bytes` and returns an ASN.1 object whose concrete public type is available to `isinstance`. `native` exposes the corresponding Python value.

### Shared value operations

`load(encoded_data, strict=<bool>, **kwargs)` is a class method returning a typed ASN.1 object. `strict` is the optional complete-consumption keyword. Tagging keywords accepted on construction and loading are `explicit` and `implicit`.

`dump(force=<bool>)` returns encoded ASN.1 `bytes`; `force` is the optional canonical-output keyword. `contents` exposes ASN.1 contents as `bytes`, excluding the element's framing.

`copy()` returns another ASN.1 object with the same public value type and field-access and serialization interfaces.

`retag(tagging)` accepts a dictionary containing `explicit` or `implicit` and returns a tagged value object. `untag()` returns a value object without special tagging. Tag syntax is an integer tag, a `(class, tag)` pair, or, for nested `explicit` tagging, a tuple of such pairs. The numeric class codes are `0` for universal, `1` for application, `2` for context-specific and `3` for private.

Document rejection, including incomplete documents and incompatible ASN.1 types, is signalled by `ValueError`. The exception may arise when constructing or loading the object, reading interpreted fields, or serializing it.

### Diagnostic output

`debug()` writes a text tree to stdout. Field subtrees have labels `Field "<field name>"`. Lines within a subtree have these forms:

- `Header: 0x<hexadecimal octets>`
- `Data: 0x<hexadecimal octets>`
- `Native: <Python value representation>`
- `<method> <class> tag <tag number>`
- `<class> tag <tag number> (explicitly tagged)`
- `<method> <class> <tag number>` for the underlying explicitly tagged value.

The method and class words include `primitive`, `universal` and `context`. Indentation expresses containment: an interpreted document inside a carrier has its data and native lines further indented than the carrier's data line.

## `cobaltform.core.BMPString`

Import `BMPString` from `cobaltform.core`. `BMPString(value)` accepts `str` and returns a typed value with `native: str`. `load(encoded_data)` accepts `bytes`; `dump(force=<bool>)` returns ASN.1 `bytes`.

Text encoding failure is exposed as `UnicodeEncodeError`.

## `cobaltform.core.BitString`

Import `BitString` from `cobaltform.core`. `BitString(value)` returns a typed ASN.1 value. `native` is a tuple of bit integers, or a set of enabled names for a named-bit subclass. Its `load(encoded_data)` and `dump(force=<bool>)` use the shared `Asn1Value` interfaces.

A subclass may declare `_map` as a dictionary from integer bit positions to name strings.

For a named-bit subclass, construction accepts a set of names or a positional tuple of bit integers. `value[name]` returns `bool`; `value[name] = enabled` accepts `bool`. A rejected selection or positional value raises `ValueError`.

`cast(other_class)` accepts a target ASN.1 class and returns an instance of that class. `contents` is `bytes`. A rejected cast raises `TypeError`.

BIT STRING `contents` use an unused-bit-count octet followed by binary payload octets. OCTET STRING `contents` consist of payload octets.

The constructor value has type positional bit tuple or declared-name set.

## `cobaltform.core.Boolean`

Import `Boolean` from `cobaltform.core`. `Boolean(value)` returns a typed ASN.1 value. `native` is `bool`. Its `load(encoded_data)` and `dump(force=<bool>)` use the shared `Asn1Value` interfaces.

The constructor value has type `bool`.

## `cobaltform.core.CharacterString`

Import `CharacterString` from `cobaltform.core`. `CharacterString(value)` accepts `str` and returns a typed value with `native: str`. `load(encoded_data)` accepts `bytes`; `dump(force=<bool>)` returns ASN.1 `bytes`.

Text encoding failure is exposed as `UnicodeEncodeError`.

## `cobaltform.core.Choice`

Import `Choice` from `cobaltform.core`. A caller-defined subclass declares `_alternatives` as a list of `(name, spec)` tuples. Construction accepts `Subclass(name, value)`, `Subclass(name=<str>, value=<value>)`, or `Subclass((name, value))`. Tagging is passed with `explicit` or `implicit`. `load(encoded_data)` returns a selection object; `name` is its string alternative identifier, `chosen` the typed selected value, and `native` the selected Python value. A rejected selection or tagging request raises `ValueError`.

## `cobaltform.core.Concat`

Import `Concat` from `cobaltform.core`. A subclass declares `_child_specs` as a list of ASN.1 classes. `Subclass(value)` accepts a list of ASN.1 objects. `load(encoded_data, strict=<bool>)` accepts `bytes` and an optional complete-consumption keyword. Integer indexing returns component objects; `dump()` returns concatenated ASN.1 `bytes`. Rejection is signalled by `ValueError`.

## `cobaltform.core.Enumerated`

Import `Enumerated` from `cobaltform.core`. `Enumerated(value)` returns a typed ASN.1 value. `native` is a declared name as `str`. Its `load(encoded_data)` and `dump(force=<bool>)` use the shared `Asn1Value` interfaces.

A subclass may declare `_map` as a dictionary from integers to name strings.

A rejected supplied enumeration value raises `ValueError`. A rejected encoded enumeration value raises `ValueError` or `KeyError` when interpreted.

The constructor value has type integer identity or declared-name `str`.

## `cobaltform.core.GeneralString`

Import `GeneralString` from `cobaltform.core`. `GeneralString(value)` accepts `str` and returns a typed value with `native: str`. `load(encoded_data)` accepts `bytes`; `dump(force=<bool>)` returns ASN.1 `bytes`.

Text encoding failure is exposed as `UnicodeEncodeError`.

## `cobaltform.core.GeneralizedTime`

Import `GeneralizedTime` from `cobaltform.core`. `GeneralizedTime(value)` accepts a time string or a Python `datetime`. `load(encoded_data)` accepts ASN.1 `bytes`; `dump()` returns ASN.1 `bytes`. `native` is a date-time object with calendar/time component attributes and `utcoffset()` access. Rejection is `ValueError`.

The date-time result exposes `hour`, `minute`, `second`, `microsecond` and `tzinfo`.

## `cobaltform.core.GraphicString`

Import `GraphicString` from `cobaltform.core`. `GraphicString(value)` accepts `str` and returns a typed value with `native: str`. `load(encoded_data)` accepts `bytes`; `dump(force=<bool>)` returns ASN.1 `bytes`.

Text encoding failure is exposed as `UnicodeEncodeError`.

## `cobaltform.core.IA5String`

Import `IA5String` from `cobaltform.core`. `IA5String(value)` accepts `str` and returns a typed value with `native: str`. `load(encoded_data)` accepts `bytes`; `dump(force=<bool>)` returns ASN.1 `bytes`.

Text encoding failure is exposed as `UnicodeEncodeError`.

## `cobaltform.core.Integer`

Import `Integer` from `cobaltform.core`. `Integer(value)` returns a typed ASN.1 value. `native` is `int`, or a declared name as `str`. Its `load(encoded_data)` and `dump(force=<bool>)` use the shared `Asn1Value` interfaces.

A subclass may declare `_map` as a dictionary from integers to name strings.

A rejected supplied named value raises `ValueError`.

The constructor value has type `int` or declared-name `str`.

## `cobaltform.core.IntegerBitString`

Import `IntegerBitString` from `cobaltform.core`. `IntegerBitString(value)` returns a typed ASN.1 value. `native` is `int`. Its `load(encoded_data)` and `dump(force=<bool>)` use the shared `Asn1Value` interfaces.

`cast(other_class)` accepts a target ASN.1 class and returns an instance of that class. `contents` is `bytes`. A rejected cast raises `TypeError`.

`contents` contain an unused-bit-count octet followed by an unsigned big-endian integer payload; the count identifies non-value bits at the end of that payload.

The constructor value has type `int`.

## `cobaltform.core.IntegerOctetString`

Import `IntegerOctetString` from `cobaltform.core`. `IntegerOctetString(value)` returns a typed ASN.1 value. `native` is `int`. Its `load(encoded_data)` and `dump(force=<bool>)` use the shared `Asn1Value` interfaces.

`cast(other_class)` accepts a target ASN.1 class and returns an instance of that class. `contents` is `bytes`. A rejected cast raises `TypeError`.

`set_encoded_width(width)` accepts an integer byte width. The value remains accessible through `native`, and serialized bytes through `dump()`.

`contents` are the unsigned big-endian integer payload bytes.

The constructor value has type `int`.

## `cobaltform.core.Null`

Import `Null` from `cobaltform.core`. `Null()` returns a typed ASN.1 value. `native` is `None`. Its `load(encoded_data)` and `dump(force=<bool>)` use the shared `Asn1Value` interfaces.

## `cobaltform.core.NumericString`

Import `NumericString` from `cobaltform.core`. `NumericString(value)` accepts `str` and returns a typed value with `native: str`. `load(encoded_data)` accepts `bytes`; `dump(force=<bool>)` returns ASN.1 `bytes`.

Text encoding failure is exposed as `UnicodeEncodeError`.

## `cobaltform.core.ObjectIdentifier`

Import `ObjectIdentifier` from `cobaltform.core`. `ObjectIdentifier(value)` returns a typed ASN.1 value. `native` is `str`. Its `load(encoded_data)` and `dump(force=<bool>)` use the shared `Asn1Value` interfaces.

A subclass may declare `_map` as a dictionary from dotted OID strings to name strings.

`dotted` is the numeric OID as dotted `str`. Class methods `map(value)` and `unmap(value)` accept a string and return its name or dotted-identity string respectively. A rejected identifier or supplied name raises `ValueError`.

The constructor value has type numeric dotted `str` or declared-name `str`.

## `cobaltform.core.OctetBitString`

Import `OctetBitString` from `cobaltform.core`. `OctetBitString(value)` returns a typed ASN.1 value. `native` is `bytes`. Its `load(encoded_data)` and `dump(force=<bool>)` use the shared `Asn1Value` interfaces.

`cast(other_class)` accepts a target ASN.1 class and returns an instance of that class. `contents` is `bytes`. A rejected cast raises `TypeError`.

The constructor value has type `bytes`.

## `cobaltform.core.OctetString`

Import `OctetString` from `cobaltform.core`. `OctetString(value)` returns a typed ASN.1 value. `native` is `bytes`. Its `load(encoded_data)` and `dump(force=<bool>)` use the shared `Asn1Value` interfaces.

`cast(other_class)` accepts a target ASN.1 class and returns an instance of that class. `contents` is `bytes`. A rejected cast raises `TypeError`.

The constructor value has type `bytes`.

## `cobaltform.core.ParsableOctetBitString`

Import `ParsableOctetBitString` from `cobaltform.core`. `ParsableOctetBitString(value)` accepts a typed ASN.1 value or payload `bytes`. `load(encoded_data)` accepts ASN.1 `bytes`. `parse(spec)` takes an ASN.1 class and returns a typed object; `parsed` exposes the parsed object. `native` exposes its Python value, or the binary payload for an unbound embedded carrier. `dump()` returns ASN.1 `bytes`. Interpretation rejection is `ValueError`.

## `cobaltform.core.ParsableOctetString`

Import `ParsableOctetString` from `cobaltform.core`. `ParsableOctetString(value)` accepts a typed ASN.1 value or payload `bytes`. `load(encoded_data)` accepts ASN.1 `bytes`. `parse(spec)` takes an ASN.1 class and returns a typed object; `parsed` exposes the parsed object. `native` exposes its Python value, or the binary payload for an unbound embedded carrier. `dump()` returns ASN.1 `bytes`. Interpretation rejection is `ValueError`.

## `cobaltform.core.PrintableString`

Import `PrintableString` from `cobaltform.core`. `PrintableString(value)` accepts `str` and returns a typed value with `native: str`. `load(encoded_data)` accepts `bytes`; `dump(force=<bool>)` returns ASN.1 `bytes`.

Text encoding failure is exposed as `UnicodeEncodeError`.

## `cobaltform.core.Sequence`

Import `Sequence` from `cobaltform.core`. A subclass is constructed as `Subclass(value)` with a dictionary of named fields. `_fields` is a list of `(name, spec)` or `(name, spec, params)` tuples. `name` is a string, `spec` is an ASN.1 class, and `params` is a dictionary with `optional`, `default`, `explicit` or `implicit` entries. The class can itself appear as a field's `spec`.

`record[name]` returns a typed field; `record[name] = value` replaces a field and `del record[name]` removes it. `native` is a mapping from field names to Python values. Schema-free sequence members are accessed as `record[index]`.

An OID association is declared with `_oid_pair = (identifier_field, value_field)` and `_oid_specs`, a dictionary from identity strings to ASN.1 classes. These declarations apply to fields declared as `Any`, `ParsableOctetString` or `ParsableOctetBitString`.

## `cobaltform.core.SequenceOf`

Import `SequenceOf` from `cobaltform.core`. A caller-defined subclass declares `_child_spec` as an ASN.1 class. `Subclass(value)` accepts a list of native or typed member values. Integer indexing returns typed members; iteration yields members; `len()` returns the count; `native` is a list. The collection has the shared `load()` and `dump(force=<bool>)` interfaces.

`append(value)` accepts a native or typed member value. `collection[index] = value` replaces a member; `del collection[index]` removes a member.

## `cobaltform.core.Set`

Import `Set` from `cobaltform.core`. A caller-defined record subclass uses `_fields` with the same declaration and dictionary construction forms as `Sequence`. String subscripts return typed fields; `native` is a named mapping. It has the shared `load()` and `dump(force=<bool>)` interfaces.

## `cobaltform.core.SetOf`

Import `SetOf` from `cobaltform.core`. A caller-defined subclass declares `_child_spec` as an ASN.1 class. `Subclass(value)` accepts a list of native or typed member values. Integer indexing returns typed members; iteration yields members; `len()` returns the count; `native` is a list. The collection has the shared `load()` and `dump(force=<bool>)` interfaces.

## `cobaltform.core.TeletexString`

Import `TeletexString` from `cobaltform.core`. `TeletexString(value)` accepts `str` and returns a typed value with `native: str`. `load(encoded_data)` accepts `bytes`; `dump(force=<bool>)` returns ASN.1 `bytes`.

## `cobaltform.core.UTCTime`

Import `UTCTime` from `cobaltform.core`. `UTCTime(value)` accepts a time string or a Python `datetime`. `load(encoded_data)` accepts ASN.1 `bytes`; `dump()` returns ASN.1 `bytes`. `native` is a date-time object with calendar/time component attributes and `utcoffset()` access. Rejection is `ValueError`.

The date-time result exposes `year`, `month`, `day`, `hour`, `minute`, `second` and `utcoffset()`.

## `cobaltform.core.UTF8String`

Import `UTF8String` from `cobaltform.core`. `UTF8String(value)` accepts `str` and returns a typed value with `native: str`. `load(encoded_data)` accepts `bytes`; `dump(force=<bool>)` returns ASN.1 `bytes`.

Text encoding failure is exposed as `UnicodeEncodeError`.

## `cobaltform.core.UniversalString`

Import `UniversalString` from `cobaltform.core`. `UniversalString(value)` accepts `str` and returns a typed value with `native: str`. `load(encoded_data)` accepts `bytes`; `dump(force=<bool>)` returns ASN.1 `bytes`.

Text encoding failure is exposed as `UnicodeEncodeError`.

## `cobaltform.core.VideotexString`

Import `VideotexString` from `cobaltform.core`. `VideotexString(value)` accepts `bytes`; `native` is `bytes`. `load(encoded_data)` and `dump(force=<bool>)` use the shared ASN.1 value interfaces.

## `cobaltform.core.VisibleString`

Import `VisibleString` from `cobaltform.core`. `VisibleString(value)` accepts `str` and returns a typed value with `native: str`. `load(encoded_data)` accepts `bytes`; `dump(force=<bool>)` returns ASN.1 `bytes`.

Text encoding failure is exposed as `UnicodeEncodeError`.

## `cobaltform.crl`

`cobaltform.crl` exposes the following public names:

- `CRLEntryExtensions`

- `CertificateList`

- `RevokedCertificates`

- `TBSCertListExtensions`

### Document version

| Numeric identity | Text identity |
| --- | --- |
| `0` | `v1` |
| `1` | `v2` |

### CRL extension OIDs

| Numeric identity | Text identity |
| --- | --- |
| `2.5.29.18` | `issuer_alt_name` |
| `2.5.29.20` | `crl_number` |
| `2.5.29.27` | `delta_crl_indicator` |
| `2.5.29.28` | `issuing_distribution_point` |
| `2.5.29.35` | `authority_key_identifier` |
| `2.5.29.46` | `freshest_crl` |
| `1.3.6.1.5.5.7.1.1` | `authority_information_access` |

### Revocation-reason enumeration

| Numeric identity | Text identity |
| --- | --- |
| `0` | `unspecified` |
| `1` | `key_compromise` |
| `2` | `ca_compromise` |
| `3` | `affiliation_changed` |
| `4` | `superseded` |
| `5` | `cessation_of_operation` |
| `6` | `certificate_hold` |
| `8` | `remove_from_crl` |
| `9` | `privilege_withdrawn` |
| `10` | `aa_compromise` |

### CRL-entry extension OIDs

| Numeric identity | Text identity |
| --- | --- |
| `2.5.29.21` | `crl_reason` |
| `2.5.29.23` | `hold_instruction_code` |
| `2.5.29.24` | `invalidity_date` |
| `2.5.29.29` | `certificate_issuer` |

## `cobaltform.crl.CRLEntryExtensions`

Import `CRLEntryExtensions` from `cobaltform.crl`. `CRLEntryExtensions(value)` accepts a list of extension mappings using `extn_id`, `critical` and `extn_value`, and returns an ASN.1 collection with the shared collection interfaces.

## `cobaltform.crl.CertificateList`

Import `CertificateList` from `cobaltform.crl`. `CertificateList(value)` accepts a mapping; `load(encoded_data)` accepts ASN.1 bytes. The record supports nested field indexing and assignment, `native`, and `dump() -> bytes`.

### CRL fields

| Field | Exchanged value |
| --- | --- |
| `tbs_cert_list` | CRL-body record. |
| `signature_algorithm` | Signature description. |
| `signature` | Signature bytes. |

### CRL-body fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string or absent field. |
| `signature` | Signature description. |
| `issuer` | `Name`. |
| `this_update` | Time choice. |
| `next_update` | Time choice or absent field. |
| `revoked_certificates` | Revoked-entry collection or absent field. |
| `crl_extensions` | Extension collection or absent field. |

`issuer` returns `Name`.

`signature` returns signature bytes.

`critical_extensions` returns set of extension name or numeric-identity strings.

`authority_key_identifier` returns key identifier bytes or `None`.

`issuer_cert_urls` returns list of URI strings.

`delta_crl_distribution_points` returns list of distribution-point objects using the fields described for `Certificate`.

`sha1` returns digest bytes.

`sha256` returns digest bytes.

`issuer_alt_name_value` returns the typed extension value or `None`.

`crl_number_value` returns the typed extension value or `None`.

`delta_crl_indicator_value` returns the typed extension value or `None`.

`issuing_distribution_point_value` returns the typed extension value or `None`.

`authority_key_identifier_value` returns the typed extension value or `None`.

`freshest_crl_value` returns the typed extension value or `None`.

`authority_information_access_value` returns the typed extension value or `None`.

### CRL extension fields

| Field | Exchanged value |
| --- | --- |
| `extn_id` | OID object with name-or-identity `native` and numeric `dotted` strings. |
| `critical` | Boolean. |
| `extn_value` | Embedded value with `contents: bytes`, `parsed` typed value and `native`. |

### Issuing-distribution-point value

| Field | Exchanged value |
| --- | --- |
| `distribution_point` | Distribution-point choice. |
| `only_contains_user_certs` | Boolean. |
| `only_contains_ca_certs` | Boolean. |
| `only_some_reasons` | Set of reason names or absent field. |
| `indirect_crl` | Boolean. |
| `only_contains_attribute_certs` | Boolean. |

## `cobaltform.crl.RevokedCertificates`

Import `RevokedCertificates` from `cobaltform.crl`. `RevokedCertificates(value)` accepts a list of revoked-entry mappings and returns an indexed, iterable collection supporting `len()`, `native`, and `dump()`.

### Entry fields

| Field | Exchanged value |
| --- | --- |
| `user_certificate` | Integer certificate serial number. |
| `revocation_date` | Time choice. |
| `crl_entry_extensions` | Entry-extension collection or absent field. |

### Entry-extension fields

| Field | Exchanged value |
| --- | --- |
| `extn_id` | OID object with name-or-identity `native` and numeric `dotted` strings. |
| `critical` | Boolean. |
| `extn_value` | Embedded value with `contents: bytes`, `parsed` typed value and `native`. |

An entry exposes `critical_extensions` as a set of extension name or identity strings.

An entry exposes `crl_reason_value` as a typed reason value or `None`.

An entry exposes `invalidity_date_value` as a typed invalidity date or `None`.

An entry exposes `certificate_issuer_value` as a typed general-name collection or `None`.

An entry exposes `issuer_name` as a `Name` or `None`.

## `cobaltform.crl.TBSCertListExtensions`

Import `TBSCertListExtensions` from `cobaltform.crl`. `TBSCertListExtensions(value)` accepts a list of extension mappings using `extn_id`, `critical` and `extn_value`, and returns an ASN.1 collection with the shared collection interfaces.

## `cobaltform.csr`

`cobaltform.csr` exposes the following public names:

- `CRIAttributes`

- `CertificationRequest`

### Document version

| Numeric identity | Text identity |
| --- | --- |
| `0` | `v1` |

### Request attribute OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.2.840.113549.1.9.7` | `challenge_password` |
| `1.2.840.113549.1.9.9` | `extended_certificate_attributes` |
| `1.2.840.113549.1.9.14` | `extension_request` |
| `1.3.6.1.4.1.311.13.2.2` | `microsoft_enrollment_csp_provider` |
| `1.3.6.1.4.1.311.13.2.3` | `microsoft_os_version` |
| `1.3.6.1.4.1.311.21.20` | `microsoft_request_client_info` |

## `cobaltform.csr.CRIAttributes`

Import `CRIAttributes` from `cobaltform.csr`. `CRIAttributes(value)` accepts a list of attribute dictionaries and returns an indexed, iterable collection with the shared ASN.1 collection interfaces.

### Request-attribute fields

| Field | Exchanged value |
| --- | --- |
| `type` | OID object with name-or-identity `native` and numeric `dotted` strings. |
| `values` | Typed collection of attribute values, or supplied open ASN.1 collection. |

### Nested open-attribute fields

| Field | Exchanged value |
| --- | --- |
| `type` | OID object. |
| `values` | Collection of ASN.1 values. |

### Enrollment-provider fields

| Field | Exchanged value |
| --- | --- |
| `keyspec` | Integer key specification. |
| `cspname` | Provider text. |
| `signature` | Tuple of bit integers. |

### Request-client fields

| Field | Exchanged value |
| --- | --- |
| `clientid` | Integer client identity. |
| `machinename` | Machine-name text. |
| `username` | User-name text. |
| `processname` | Process-name text. |

Password and operating-system attribute values have a text-list `native` form. Requested-extension values are collections of extension records with `extn_id`, `critical` and embedded `extn_value`, using the extension and general-name interfaces described for `Certificate`.

Microsoft enrollment-provider and request-client values are ASN.1 SEQUENCE records in their respective table orders. Provider fields use INTEGER, BMPString and BIT STRING. Client fields use INTEGER followed by three UTF8String values. Their attribute value collections use SET OF; operating-system values use SET OF DirectoryString.

## `cobaltform.csr.CertificationRequest`

Import `CertificationRequest` from `cobaltform.csr`. `CertificationRequest(value)` accepts a field mapping; `load(encoded_data)` accepts ASN.1 bytes. The result supports nested indexing and assignment, `native`, and `dump() -> bytes`.

### Request fields

| Field | Exchanged value |
| --- | --- |
| `certification_request_info` | Request-information record. |
| `signature_algorithm` | Signature description. |
| `signature` | Signature bytes. |

### Request-information fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `subject` | `Name`. |
| `subject_pk_info` | `PublicKeyInfo`. |
| `attributes` | Request-attribute collection or absent field. |

## `cobaltform.keys`

`cobaltform.keys` exposes the following public names:

- `DSAParams`

- `DSAPrivateKey`

- `ECDomainParameters`

- `ECPoint`

- `ECPointBitString`

- `ECPrivateKey`

- `EncryptedPrivateKeyInfo`

- `NamedCurve`

- `PrivateKeyInfo`

- `PublicKeyInfo`

- `RSAPrivateKey`

- `RSAPublicKey`

### RSA private-key version

| Numeric identity | Text identity |
| --- | --- |
| `0` | `two-prime` |
| `1` | `multi` |

### Explicit EC domain version

| Numeric identity | Text identity |
| --- | --- |
| `1` | `ecdpVer1` |

### EC field OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.2.840.10045.1.1` | `prime_field` |

### Named-curve OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.2.840.10045.3.0.1` | `c2pnb163v1` |
| `1.2.840.10045.3.0.2` | `c2pnb163v2` |
| `1.2.840.10045.3.0.3` | `c2pnb163v3` |
| `1.2.840.10045.3.0.4` | `c2pnb176w1` |
| `1.2.840.10045.3.0.5` | `c2tnb191v1` |
| `1.2.840.10045.3.0.6` | `c2tnb191v2` |
| `1.2.840.10045.3.0.7` | `c2tnb191v3` |
| `1.2.840.10045.3.0.8` | `c2onb191v4` |
| `1.2.840.10045.3.0.9` | `c2onb191v5` |
| `1.2.840.10045.3.0.10` | `c2pnb208w1` |
| `1.2.840.10045.3.0.11` | `c2tnb239v1` |
| `1.2.840.10045.3.0.12` | `c2tnb239v2` |
| `1.2.840.10045.3.0.13` | `c2tnb239v3` |
| `1.2.840.10045.3.0.14` | `c2onb239v4` |
| `1.2.840.10045.3.0.15` | `c2onb239v5` |
| `1.2.840.10045.3.0.16` | `c2pnb272w1` |
| `1.2.840.10045.3.0.17` | `c2pnb304w1` |
| `1.2.840.10045.3.0.18` | `c2tnb359v1` |
| `1.2.840.10045.3.0.19` | `c2pnb368w1` |
| `1.2.840.10045.3.0.20` | `c2tnb431r1` |
| `1.2.840.10045.3.1.2` | `prime192v2` |
| `1.2.840.10045.3.1.3` | `prime192v3` |
| `1.2.840.10045.3.1.4` | `prime239v1` |
| `1.2.840.10045.3.1.5` | `prime239v2` |
| `1.2.840.10045.3.1.6` | `prime239v3` |
| `1.2.840.10045.3.1.1` | `secp192r1` |
| `1.2.840.10045.3.1.7` | `secp256r1` |
| `1.3.132.0.1` | `sect163k1` |
| `1.3.132.0.2` | `sect163r1` |
| `1.3.132.0.3` | `sect239k1` |
| `1.3.132.0.4` | `sect113r1` |
| `1.3.132.0.5` | `sect113r2` |
| `1.3.132.0.6` | `secp112r1` |
| `1.3.132.0.7` | `secp112r2` |
| `1.3.132.0.8` | `secp160r1` |
| `1.3.132.0.9` | `secp160k1` |
| `1.3.132.0.10` | `secp256k1` |
| `1.3.132.0.15` | `sect163r2` |
| `1.3.132.0.16` | `sect283k1` |
| `1.3.132.0.17` | `sect283r1` |
| `1.3.132.0.22` | `sect131r1` |
| `1.3.132.0.23` | `sect131r2` |
| `1.3.132.0.24` | `sect193r1` |
| `1.3.132.0.25` | `sect193r2` |
| `1.3.132.0.26` | `sect233k1` |
| `1.3.132.0.27` | `sect233r1` |
| `1.3.132.0.28` | `secp128r1` |
| `1.3.132.0.29` | `secp128r2` |
| `1.3.132.0.30` | `secp160r2` |
| `1.3.132.0.31` | `secp192k1` |
| `1.3.132.0.32` | `secp224k1` |
| `1.3.132.0.33` | `secp224r1` |
| `1.3.132.0.34` | `secp384r1` |
| `1.3.132.0.35` | `secp521r1` |
| `1.3.132.0.36` | `sect409k1` |
| `1.3.132.0.37` | `sect409r1` |
| `1.3.132.0.38` | `sect571k1` |
| `1.3.132.0.39` | `sect571r1` |
| `1.3.36.3.3.2.8.1.1.1` | `brainpoolp160r1` |
| `1.3.36.3.3.2.8.1.1.2` | `brainpoolp160t1` |
| `1.3.36.3.3.2.8.1.1.3` | `brainpoolp192r1` |
| `1.3.36.3.3.2.8.1.1.4` | `brainpoolp192t1` |
| `1.3.36.3.3.2.8.1.1.5` | `brainpoolp224r1` |
| `1.3.36.3.3.2.8.1.1.6` | `brainpoolp224t1` |
| `1.3.36.3.3.2.8.1.1.7` | `brainpoolp256r1` |
| `1.3.36.3.3.2.8.1.1.8` | `brainpoolp256t1` |
| `1.3.36.3.3.2.8.1.1.9` | `brainpoolp320r1` |
| `1.3.36.3.3.2.8.1.1.10` | `brainpoolp320t1` |
| `1.3.36.3.3.2.8.1.1.11` | `brainpoolp384r1` |
| `1.3.36.3.3.2.8.1.1.12` | `brainpoolp384t1` |
| `1.3.36.3.3.2.8.1.1.13` | `brainpoolp512r1` |
| `1.3.36.3.3.2.8.1.1.14` | `brainpoolp512t1` |

### EC private-key version

| Numeric identity | Text identity |
| --- | --- |
| `1` | `ecPrivkeyVer1` |

### Private-key algorithm OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.2.840.113549.1.1.1` | `rsa` |
| `1.2.840.113549.1.1.10` | `rsassa_pss` |
| `1.2.840.10040.4.1` | `dsa` |
| `1.2.840.10045.2.1` | `ec` |
| `1.3.101.110` | `x25519` |
| `1.3.101.111` | `x448` |
| `1.3.101.112` | `ed25519` |
| `1.3.101.113` | `ed448` |

### Public-key algorithm OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.2.840.113549.1.1.1` | `rsa` |
| `1.2.840.113549.1.1.7` | `rsaes_oaep` |
| `1.2.840.113549.1.1.10` | `rsassa_pss` |
| `1.2.840.10040.4.1` | `dsa` |
| `1.2.840.10045.2.1` | `ec` |
| `1.2.840.10046.2.1` | `dh` |
| `1.3.101.110` | `x25519` |
| `1.3.101.111` | `x448` |
| `1.3.101.112` | `ed25519` |
| `1.3.101.113` | `ed448` |

## `cobaltform.keys.DSAParams`

Import `DSAParams` from `cobaltform.keys`. `DSAParams(value)` accepts a field mapping. `load(encoded_data)` accepts ASN.1 `bytes`; both return a typed record. String indexing reads fields; assignment replaces fields; `native` is the Python field mapping; `dump(force=<bool>)` returns ASN.1 `bytes`.

### Domain fields

| Field | Exchanged value |
| --- | --- |
| `p` | Integer prime. |
| `q` | Integer subgroup order. |
| `g` | Integer generator. |

`q_byte_size` is an integer byte count for the subgroup order.

## `cobaltform.keys.DSAPrivateKey`

Import `DSAPrivateKey` from `cobaltform.keys`. `DSAPrivateKey(value)` accepts a field mapping. `load(encoded_data)` accepts ASN.1 `bytes`; both return a typed record. String indexing reads fields; assignment replaces fields; `native` is the Python field mapping; `dump(force=<bool>)` returns ASN.1 `bytes`.

### Private-key fields

| Field | Exchanged value |
| --- | --- |
| `version` | Integer version. |
| `p` | Integer domain component. |
| `q` | Integer domain component. |
| `g` | Integer domain component. |
| `public_key` | Integer public component. |
| `private_key` | Integer private component. |

The standalone OpenSSL DSA wire form is an ASN.1 SEQUENCE of INTEGER values in the table order.

## `cobaltform.keys.ECDomainParameters`

Import `ECDomainParameters` from `cobaltform.keys`. `ECDomainParameters((name, value))` accepts a named domain alternative and its value. It returns a choice with `name: str`, `chosen` as its typed value, and `native` as the chosen Python value.

Alternative input names and value shapes:

| Alternative | Value |
| --- | --- |
| `named` | Curve name or dotted numeric identity string; selected value has `native: str` and `dotted: str`. |
| `specified` | Domain field mapping. |
| `implicit_ca` | `None`. |

### Specified-domain fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `field_id` | Record with `field_type` and `parameters`. |
| `curve` | Record with binary `a`, binary `b` and optional binary `seed`. |
| `base` | Point bytes. |
| `order` | Integer subgroup order. |
| `cofactor` | Integer cofactor or absent field. |
| `hash` | Digest description or absent field. |

### Field-description fields

| Field | Exchanged value |
| --- | --- |
| `field_type` | Field-identity string. |
| `parameters` | Typed field parameters. |

### Curve-description fields

| Field | Exchanged value |
| --- | --- |
| `a` | Coefficient bytes. |
| `b` | Coefficient bytes. |
| `seed` | Seed bytes or absent field. |

`key_size` is an integer scalar-width byte count. Unavailable domain information raises `ValueError`.

## `cobaltform.keys.ECPoint`

Import `ECPoint` from `cobaltform.keys`. `ECPoint(value)` accepts binary point bytes. `to_coords()` returns a two-item tuple of integers `(x, y)`. A rejected point representation raises `ValueError`.

## `cobaltform.keys.ECPointBitString`

Import `ECPointBitString` from `cobaltform.keys`. `ECPointBitString(value)` accepts binary point bytes. `to_coords()` returns a two-item tuple of integers `(x, y)`. A rejected point representation raises `ValueError`.

## `cobaltform.keys.ECPrivateKey`

Import `ECPrivateKey` from `cobaltform.keys`. `ECPrivateKey(value)` accepts a field mapping. `load(encoded_data)` accepts ASN.1 `bytes`; both return a typed record. String indexing reads fields; assignment replaces fields; `native` is the Python field mapping; `dump(force=<bool>)` returns ASN.1 `bytes`.

### Private-key fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string; construction also accepts its integer identity. |
| `private_key` | Integer scalar through `native`; encoded scalar bytes through `contents`; ASN.1 bytes through `dump()`. |
| `parameters` | Domain-parameter choice or absent field. |
| `public_key` | EC point bytes or absent field. |

## `cobaltform.keys.EncryptedPrivateKeyInfo`

Import `EncryptedPrivateKeyInfo` from `cobaltform.keys`. `EncryptedPrivateKeyInfo(value)` accepts a field mapping. `load(encoded_data)` accepts ASN.1 `bytes`; both return a typed record. String indexing reads fields; assignment replaces fields; `native` is the Python field mapping; `dump(force=<bool>)` returns ASN.1 `bytes`.

### Encrypted container fields

| Field | Exchanged value |
| --- | --- |
| `encryption_algorithm` | Description with `algorithm` and `parameters`. |
| `encrypted_data` | Ciphertext bytes. |

## `cobaltform.keys.NamedCurve`

Import `NamedCurve` from `cobaltform.keys`. `NamedCurve(value)` accepts a curve name or dotted OID string. `native` is the curve name string; `dotted` is the numeric-identity string.

`NamedCurve.register(name, oid, key_size)` is a class method with text name, dotted identity string and integer private-scalar width in bytes.

## `cobaltform.keys.PrivateKeyInfo`

Import `PrivateKeyInfo` from `cobaltform.keys`. `PrivateKeyInfo(value)` accepts a field mapping. `load(encoded_data)` accepts ASN.1 `bytes`; both return a typed record. String indexing reads fields; assignment replaces fields; `native` is the Python field mapping; `dump(force=<bool>)` returns ASN.1 `bytes`.

### Container fields

| Field | Exchanged value |
| --- | --- |
| `version` | Integer version. |
| `private_key_algorithm` | Description with `algorithm` and `parameters`. |
| `private_key` | Embedded private value; `parsed` returns its typed value. |
| `attributes` | Collection of attribute records or absent field. |

### Attribute fields

| Field | Exchanged value |
| --- | --- |
| `type` | OID object with `dotted: str`. |
| `values` | Collection of open ASN.1 values supporting indexed assignment. |

`wrap(private_key, algorithm)` is a class method. The key argument is standalone key ASN.1 `bytes` or a typed standalone key object; `algorithm` is a string identity. The return is a `PrivateKeyInfo` object.

`algorithm`: String key algorithm identity.

`curve`: Tuple `(alternative_name, domain_value)`; the domain value is a named-curve string, a specified-domain mapping, or `None`. Incompatible key requests raise `ValueError`.

`hash_algo`: Digest-family string or `None` for unavailable information. Incompatible key requests raise `ValueError`.

`bit_size`: Integer bit count for the key size.

`byte_size`: Integer byte count for the key size.

## `cobaltform.keys.PublicKeyInfo`

Import `PublicKeyInfo` from `cobaltform.keys`. `PublicKeyInfo(value)` accepts a field mapping. `load(encoded_data)` accepts ASN.1 `bytes`; both return a typed record. String indexing reads fields; assignment replaces fields; `native` is the Python field mapping; `dump(force=<bool>)` returns ASN.1 `bytes`.

### Container fields

| Field | Exchanged value |
| --- | --- |
| `algorithm` | Description with `algorithm` and `parameters`. |
| `public_key` | Public-key payload; `native` is binary for an opaque or EC point value, and `parsed` exposes a structured or integer key value. |

### DH domain fields

| Field | Exchanged value |
| --- | --- |
| `p` | Integer prime. |
| `g` | Integer generator. |
| `q` | Integer subgroup order. |

`wrap(public_key, algorithm)` is a class method. The key argument is standalone key ASN.1 `bytes` or a typed standalone key object; `algorithm` is a string identity. The return is a `PublicKeyInfo` object.

`algorithm`: String key algorithm identity.

`curve`: Tuple `(alternative_name, domain_value)`; the domain value is a named-curve string, a specified-domain mapping, or `None`. Incompatible key requests raise `ValueError`.

`hash_algo`: Digest-family string or `None` for unavailable information. Incompatible key requests raise `ValueError`.

`bit_size`: Integer bit count for the key size.

`byte_size`: Integer byte count for the key size.

`sha1` returns digest `bytes`.

`sha256` returns digest `bytes`.

## `cobaltform.keys.RSAPrivateKey`

Import `RSAPrivateKey` from `cobaltform.keys`. `RSAPrivateKey(value)` accepts a field mapping. `load(encoded_data)` accepts ASN.1 `bytes`; both return a typed record. String indexing reads fields; assignment replaces fields; `native` is the Python field mapping; `dump(force=<bool>)` returns ASN.1 `bytes`.

### Private-key fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string; construction also accepts its integer identity. |
| `modulus` | Integer key component. |
| `public_exponent` | Integer key component. |
| `private_exponent` | Integer key component. |
| `prime1` | Integer key component. |
| `prime2` | Integer key component. |
| `exponent1` | Integer key component. |
| `exponent2` | Integer key component. |
| `coefficient` | Integer key component. |
| `other_prime_infos` | Collection of additional-prime records or absent field. |

### Additional-prime fields

| Field | Exchanged value |
| --- | --- |
| `prime` | Integer prime. |
| `exponent` | Integer exponent. |
| `coefficient` | Integer coefficient. |

## `cobaltform.keys.RSAPublicKey`

Import `RSAPublicKey` from `cobaltform.keys`. `RSAPublicKey(value)` accepts a field mapping. `load(encoded_data)` accepts ASN.1 `bytes`; both return a typed record. String indexing reads fields; assignment replaces fields; `native` is the Python field mapping; `dump(force=<bool>)` returns ASN.1 `bytes`.

### Public-key fields

| Field | Exchanged value |
| --- | --- |
| `modulus` | Integer modulus. |
| `public_exponent` | Integer exponent. |

## `cobaltform.ocsp`

`cobaltform.ocsp` exposes the following public names:

- `BasicOCSPResponse`

- `CertStatus`

- `OCSPRequest`

- `OCSPResponse`

- `RequestExtensions`

- `ResponderId`

- `ResponseDataExtensions`

- `SingleResponseExtensions`

- `TBSRequestExtensions`

### Document version

| Numeric identity | Text identity |
| --- | --- |
| `0` | `v1` |

### Per-request extension OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.3.6.1.5.5.7.48.1.7` | `service_locator` |

### Response-type OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.3.6.1.5.5.7.48.1.1` | `basic_ocsp_response` |

### Request-wide extension OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.3.6.1.5.5.7.48.1.2` | `nonce` |
| `1.3.6.1.5.5.7.48.1.4` | `acceptable_responses` |
| `1.3.6.1.5.5.7.48.1.8` | `preferred_signature_algorithms` |

### Response-status enumeration

| Numeric identity | Text identity |
| --- | --- |
| `0` | `successful` |
| `1` | `malformed_request` |
| `2` | `internal_error` |
| `3` | `try_later` |
| `5` | `sign_required` |
| `6` | `unauthorized` |

### Single-response extension OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.3.6.1.5.5.7.48.1.3` | `crl` |
| `1.3.6.1.5.5.7.48.1.6` | `archive_cutoff` |
| `2.5.29.21` | `crl_reason` |
| `2.5.29.24` | `invalidity_date` |
| `2.5.29.29` | `certificate_issuer` |
| `1.3.6.1.4.1.11129.2.4.5` | `signed_certificate_timestamp_list` |

### Response-wide extension OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.3.6.1.5.5.7.48.1.2` | `nonce` |
| `1.3.6.1.5.5.7.48.1.9` | `extended_revoke` |

## `cobaltform.ocsp.BasicOCSPResponse`

Import `BasicOCSPResponse` from `cobaltform.ocsp`. `BasicOCSPResponse(value)` accepts a field mapping. The returned record supports named field indexing, nested field assignment, field deletion, `native` and `dump() -> bytes`.

### Basic-response fields

| Field | Exchanged value |
| --- | --- |
| `tbs_response_data` | Response-data record. |
| `signature_algorithm` | Signature description. |
| `signature` | Signature bytes. |
| `certs` | Certificate collection or absent field. |

### Response-data fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `responder_id` | `ResponderId` choice. |
| `produced_at` | Date-time. |
| `responses` | Indexed single-response collection. |
| `response_extensions` | Extension collection or absent field. |

### Single-response fields

| Field | Exchanged value |
| --- | --- |
| `cert_id` | Certificate identifier with `hash_algorithm`, `issuer_name_hash`, `issuer_key_hash` and `serial_number`, using the identifier form described for `OCSPRequest`. |
| `cert_status` | `CertStatus` choice. |
| `this_update` | Date-time. |
| `next_update` | Date-time or absent field. |
| `single_extensions` | Extension collection or absent field. |

A SingleResponse entry exposes `critical_extensions` as a set of extension name or identity strings.

The entry exposes `crl_value` as a typed extension value or `None`.

The entry exposes `archive_cutoff_value` as a typed extension value or `None`.

The entry exposes `crl_reason_value` as a typed extension value or `None`.

The entry exposes `invalidity_date_value` as a typed extension value or `None`.

The entry exposes `certificate_issuer_value` as a typed extension value or `None`.

## `cobaltform.ocsp.CertStatus`

Import `CertStatus` from `cobaltform.ocsp`. `CertStatus((name, value))` returns a choice with `name`, `chosen` and `native`.

Alternative input names and value shapes:

| Alternative | Value |
| --- | --- |
| `good` | Construction accepts `None`; `native` and `chosen.native` are the status-name string. |
| `unknown` | Construction accepts `None`; `native` and `chosen.native` are the status-name string. |
| `revoked` | Record with `revocation_time` date-time and optional `revocation_reason` reason name. |

## `cobaltform.ocsp.OCSPRequest`

Import `OCSPRequest` from `cobaltform.ocsp`. `OCSPRequest(value)` accepts a field mapping; `load(encoded_data)` accepts ASN.1 bytes. The returned record supports named field indexing, nested field assignment, field deletion, `native` and `dump() -> bytes`.

### Request fields

| Field | Exchanged value |
| --- | --- |
| `tbs_request` | Request-body record. |
| `optional_signature` | Signature record or absent field. |

### Request-body fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `requestor_name` | `GeneralName` or absent field. |
| `request_list` | Indexed request-entry collection. |
| `request_extensions` | Extension collection or absent field. |

### Request-entry fields

| Field | Exchanged value |
| --- | --- |
| `req_cert` | Certificate-identifier record. |
| `single_request_extensions` | Extension collection or absent field. |

### Certificate-identifier fields

| Field | Exchanged value |
| --- | --- |
| `hash_algorithm` | Digest description. |
| `issuer_name_hash` | Bytes. |
| `issuer_key_hash` | Bytes. |
| `serial_number` | Integer. |

### Signature fields

| Field | Exchanged value |
| --- | --- |
| `signature_algorithm` | Signature description. |
| `signature` | Signature bytes. |
| `certs` | Certificate collection or absent field. |

`critical_extensions` is a set of extension name or numeric-identity strings.

`nonce_value` returns the typed extension value or `None`.

`acceptable_responses_value` returns the typed extension value or `None`.

`preferred_signature_algorithms_value` returns the typed extension value or `None`.

A Request entry exposes `critical_extensions` as a set of extension name or identity strings.

The entry exposes `service_locator_value` as a typed extension value or `None`.

## `cobaltform.ocsp.OCSPResponse`

Import `OCSPResponse` from `cobaltform.ocsp`. `OCSPResponse(value)` accepts a field mapping; `load(encoded_data)` accepts ASN.1 bytes. The returned record supports named field indexing, nested field assignment, field deletion, `native` and `dump() -> bytes`.

### Response fields

| Field | Exchanged value |
| --- | --- |
| `response_status` | Status name string. |
| `response_bytes` | Response-bytes record or absent field. |

### Response-bytes fields

| Field | Exchanged value |
| --- | --- |
| `response_type` | OID object with name-or-identity `native`. |
| `response` | Embedded response whose `parsed` is a typed document. |

`critical_extensions` is a set of extension name or numeric-identity strings.

`nonce_value` returns the typed extension value or `None`.

`extended_revoke_value` returns the typed extension value or `None`.

## `cobaltform.ocsp.RequestExtensions`

Import `RequestExtensions` from `cobaltform.ocsp`. `RequestExtensions(value)` accepts a list of extension dictionaries and returns an indexed, iterable ASN.1 collection.

### Extension fields

| Field | Exchanged value |
| --- | --- |
| `extn_id` | OID object with name-or-identity `native` and numeric `dotted` strings. |
| `critical` | Boolean. |
| `extn_value` | Embedded value exposing `contents: bytes`, `parsed` typed value and `native`. |

### Service-locator value fields

| Field | Exchanged value |
| --- | --- |
| `issuer` | `Name`. |
| `locator` | Access-description collection using `access_method` and `access_location`. |

## `cobaltform.ocsp.ResponderId`

Import `ResponderId` from `cobaltform.ocsp`. `ResponderId((name, value))` returns a choice with `name`, `chosen` and `native`.

Alternative input names and value shapes:

| Alternative | Value |
| --- | --- |
| `by_name` | `Name`. |
| `by_key` | Identifier bytes. |

## `cobaltform.ocsp.ResponseDataExtensions`

Import `ResponseDataExtensions` from `cobaltform.ocsp`. `ResponseDataExtensions(value)` accepts a list of extension dictionaries and returns an indexed, iterable ASN.1 collection.

### Extension fields

| Field | Exchanged value |
| --- | --- |
| `extn_id` | OID object with name-or-identity `native` and numeric `dotted` strings. |
| `critical` | Boolean. |
| `extn_value` | Embedded value exposing `contents: bytes`, `parsed` typed value and `native`. |

## `cobaltform.ocsp.SingleResponseExtensions`

Import `SingleResponseExtensions` from `cobaltform.ocsp`. `SingleResponseExtensions(value)` accepts a list of extension dictionaries and returns an indexed, iterable ASN.1 collection.

### Extension fields

| Field | Exchanged value |
| --- | --- |
| `extn_id` | OID object with name-or-identity `native` and numeric `dotted` strings. |
| `critical` | Boolean. |
| `extn_value` | Embedded value exposing `contents: bytes`, `parsed` typed value and `native`. |

### CRL-reference value fields

| Field | Exchanged value |
| --- | --- |
| `crl_url` | URI text or absent field. |
| `crl_num` | Integer or absent field. |
| `crl_time` | Date-time or absent field. |

## `cobaltform.ocsp.TBSRequestExtensions`

Import `TBSRequestExtensions` from `cobaltform.ocsp`. `TBSRequestExtensions(value)` accepts a list of extension dictionaries and returns an indexed, iterable ASN.1 collection.

### Extension fields

| Field | Exchanged value |
| --- | --- |
| `extn_id` | OID object with name-or-identity `native` and numeric `dotted` strings. |
| `critical` | Boolean. |
| `extn_value` | Embedded value exposing `contents: bytes`, `parsed` typed value and `native`. |

### Preferred-signature value fields

| Field | Exchanged value |
| --- | --- |
| `sig_identifier` | Signature algorithm description. |
| `cert_identifier` | Public-key algorithm description or absent field. |

## `cobaltform.parser`

`cobaltform.parser` exposes the following public names:

- `emit`

- `parse`

- `peek`

## `cobaltform.parser.emit`

Import `emit` from `cobaltform.parser`. `emit(class_, method, tag, contents)` takes integer class, form and tag identifiers and content `bytes`. Its class and form codes are those stated for `parse`. It returns encoded element `bytes`. Refusal uses `ValueError` for argument-value rejection and `TypeError` for argument-type rejection.

## `cobaltform.parser.parse`

Import `parse` from `cobaltform.parser`. `parse(contents, strict=<bool>)` accepts ASN.1 `bytes` and an optional complete-consumption keyword. It returns a six-item tuple `(class_, method, tag, header, contents, trailer)`: the first three entries are integer class, form and tag identifiers; the final three are header, content and terminator `bytes`. Class codes are universal `0`, application `1`, context-specific `2`, private `3`; form codes are primitive `0` and constructed `1`. Refusal uses `ValueError` for ASN.1 data rejection and `TypeError` for input-type rejection.

## `cobaltform.parser.peek`

Import `peek` from `cobaltform.parser`. `peek(contents)` accepts ASN.1 `bytes` and returns an `int` byte count for the encoded element. Refusal uses `ValueError` for ASN.1 data rejection and `TypeError` for input-type rejection.

## `cobaltform.pdf`

`cobaltform.pdf` exposes the following public names:

- `RevocationInfoArchival`

Import `cobaltform.pdf` for the PDF structures reached through certificate `extn_value.parsed` and CMS attribute `values`. Archival extension values are records with an integer `version`. Credential values have `native: None`. Timestamp extension fields are given below.

### Timestamp extension fields

| Field | Exchanged value |
| --- | --- |
| `version` | Integer. |
| `location` | `GeneralName` choice. |
| `requires_auth` | Boolean. |

### Archival extension fields

| Field | Exchanged value |
| --- | --- |
| `version` | Integer. |

### PDF identity forms

| Carrier | OID | Text identity |
| --- | --- | --- |
| Certificate extension | `1.2.840.113583.1.1.9.2` | `adobe_archive_rev_info` |
| Certificate extension | `1.2.840.113583.1.1.9.1` | `adobe_timestamp` |
| Certificate extension | `1.2.840.113583.1.1.10` | `adobe_ppklite_credential` |
| Extended key usage | `1.2.840.113583.1.1.5` | `pdf_signing` |
| CMS attribute type | `1.2.840.113583.1.1.8` | `adobe_revocation_info_archival` |

Adobe archival and timestamp extensions use ASN.1 SEQUENCE in their table orders; versions use INTEGER, timestamp location uses GeneralName and authentication uses BOOLEAN. Credential extension contents use NULL.

## `cobaltform.pdf.RevocationInfoArchival`

Import `RevocationInfoArchival` from `cobaltform.pdf`. `RevocationInfoArchival.load(encoded_data)` accepts ASN.1 bytes and returns an archival record accepted in CMS attribute `values`. It supports named fields, `native`, and `dump() -> bytes`.

### Archival fields

| Field | Exchanged value |
| --- | --- |
| `crl` | Collection of `CertificateList` values or absent field. |
| `ocsp` | Collection of `OCSPResponse` values or absent field. |
| `other_rev_info` | Collection of other-revocation records or absent field. |

### Other-revocation fields

| Field | Exchanged value |
| --- | --- |
| `type` | OID string. |
| `value` | Bytes. |

The archival record is an ASN.1 SEQUENCE. Its `crl`, `ocsp` and `other_rev_info` fields use context-specific explicit tags 0, 1 and 2, respectively, around SEQUENCE OF collections. Other-revocation records use SEQUENCE with OBJECT IDENTIFIER `type` followed by OCTET STRING `value`.

## `cobaltform.pem`

`cobaltform.pem` exposes the following public names:

- `armor`

- `detect`

- `unarmor`

## `cobaltform.pem.armor`

Import `armor` from `cobaltform.pem`. `armor(type_name, der_bytes, headers=<dict[str, str]>)` accepts a text identity, binary payload, and optional text header mapping. It returns ASCII PEM as `bytes`. The opening line has form `-----BEGIN <identity>-----`, the closing line `-----END <identity>-----`; optional headers have form `<name>: <value>`, and payload lines contain Base64 text. Input-type rejection raises `TypeError`; ASCII encoding failure raises `UnicodeEncodeError`.

## `cobaltform.pem.detect`

Import `detect` from `cobaltform.pem`. `detect(byte_string)` accepts `bytes` and returns a `bool` indicating a PEM opening boundary. Input-type rejection raises `TypeError`.

## `cobaltform.pem.unarmor`

Import `unarmor` from `cobaltform.pem`. `unarmor(pem_bytes, multiple=<bool>)` accepts `bytes` and an optional all-blocks keyword. The single-block result is `(type_name, headers, der_bytes)`, with `type_name: str`, `headers: dict[str, str]`, and payload `der_bytes: bytes`. With `multiple=True`, the return is an iterable of such tuples. Malformed-PEM rejection is `ValueError`; input-type rejection is `TypeError`. Either exception may be raised on the call or while consuming the iterable.

The ordinary boundary lines are `-----BEGIN <identity>-----` and `-----END <identity>-----`. The spaced boundary lines are `---- BEGIN <identity> ----` and `---- END <identity> ----`. Header lines have form `<name>: <value>`; block payloads use Base64 text.

## `cobaltform.pkcs12`

`cobaltform.pkcs12` exposes the following public names:

- `AuthenticatedSafe`

- `Pfx`

- `SafeContents`

### Document version

| Numeric identity | Text identity |
| --- | --- |
| `3` | `v3` |

### Bag attribute OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.2.840.113549.1.9.20` | `friendly_name` |
| `1.2.840.113549.1.9.21` | `local_key_id` |
| `1.3.6.1.4.1.311.17.1` | `microsoft_local_machine_keyset` |
| `2.16.840.1.113894.746875.1.1` | `trusted_key_usage` |

### Bag identity OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.2.840.113549.1.12.10.1.1` | `key_bag` |
| `1.2.840.113549.1.12.10.1.2` | `pkcs8_shrouded_key_bag` |
| `1.2.840.113549.1.12.10.1.3` | `cert_bag` |
| `1.2.840.113549.1.12.10.1.4` | `crl_bag` |
| `1.2.840.113549.1.12.10.1.5` | `secret_bag` |
| `1.2.840.113549.1.12.10.1.6` | `safe_contents` |

### Certificate-bag identity OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.2.840.113549.1.9.22.1` | `x509` |
| `1.2.840.113549.1.9.22.2` | `sdsi` |

## `cobaltform.pkcs12.AuthenticatedSafe`

Import `AuthenticatedSafe` from `cobaltform.pkcs12`. `AuthenticatedSafe(value)` accepts a list of `ContentInfo` field mappings. It returns a collection of typed `ContentInfo` values with integer indexing, iteration, `len()`, `native` and `dump() -> bytes`.

## `cobaltform.pkcs12.Pfx`

Import `Pfx` from `cobaltform.pkcs12`. `Pfx(value)` accepts a field mapping; `load(encoded_data)` accepts ASN.1 bytes. The returned record supports named field indexing and replacement, `native`, and `dump() -> bytes`.

### PFX fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string; construction also accepts its integer identity. |
| `auth_safe` | `ContentInfo`. |
| `mac_data` | MAC-data record or absent field. |

### MAC-data fields

| Field | Exchanged value |
| --- | --- |
| `mac` | Record containing `digest_algorithm` and binary `digest`. |
| `mac_salt` | Salt bytes. |
| `iterations` | Integer iteration count. |

`authenticated_safe` returns an indexed, iterable `AuthenticatedSafe` collection supporting `len()`.

## `cobaltform.pkcs12.SafeContents`

Import `SafeContents` from `cobaltform.pkcs12`. `SafeContents(value)` accepts a list of safe-bag field mappings. `SafeContents.load(encoded_data)` accepts ASN.1 bytes. The result is an indexed, iterable collection with `len()`, `native`, and `dump() -> bytes`.

### Safe-bag fields

| Field | Exchanged value |
| --- | --- |
| `bag_id` | OID object with a bag-name string `native`. |
| `bag_value` | Typed bag value, including a key record or nested safe-contents collection. |
| `bag_attributes` | Attribute collection or absent field. |

### Certificate-bag fields

| Field | Exchanged value |
| --- | --- |
| `cert_id` | Certificate identity-name string. |
| `cert_value` | Embedded certificate whose `parsed` exposes a `Certificate`, or opaque binary `native` value. |

### CRL-bag fields

| Field | Exchanged value |
| --- | --- |
| `crl_id` | OID identity string. |
| `crl_value` | Bytes. |

### Secret-bag fields

| Field | Exchanged value |
| --- | --- |
| `secret_type_id` | OID identity string. |
| `secret_value` | Bytes. |

### Bag-attribute fields

| Field | Exchanged value |
| --- | --- |
| `type` | OID object with name-or-identity `native` and numeric `dotted` strings. |
| `values` | Collection of typed values whose `native` is a list; text, binary, purpose-name and open-value members use their corresponding Python forms. |

Both `x509` and opaque `sdsi` certificate-bag payloads use OCTET STRING under the explicit context-specific tag 0 of `cert_value`.

## `cobaltform.tsp`

`cobaltform.tsp` exposes the following public names:

- `Evidence`

- `PKIStatusInfo`

- `TSTInfo`

- `TimeStampReq`

- `TimeStampResp`

- `TimeStampedData`

### Document version

| Numeric identity | Text identity |
| --- | --- |
| `1` | `v1` |

### Timestamp-status enumeration

| Numeric identity | Text identity |
| --- | --- |
| `0` | `granted` |
| `1` | `granted_with_mods` |
| `2` | `rejection` |
| `3` | `waiting` |
| `4` | `revocation_warning` |
| `5` | `revocation_notification` |

### Timestamp-failure bit positions

| Numeric identity | Text identity |
| --- | --- |
| `0` | `bad_alg` |
| `2` | `bad_request` |
| `5` | `bad_data_format` |
| `14` | `time_not_available` |
| `15` | `unaccepted_policy` |
| `16` | `unaccepted_extensions` |
| `17` | `add_info_not_available` |
| `25` | `system_failure` |

### Timestamp integration identity forms

| Carrier | OID | Text identity |
| --- | --- | --- |
| CMS content type | `1.2.840.113549.1.9.16.1.4` | `tst_info` |
| CMS content type | `1.2.840.113549.1.9.16.1.31` | `timestamped_data` |
| CMS attribute type | `1.2.840.113549.1.9.16.2.12` | `signing_certificate` |
| CMS attribute type | `1.2.840.113549.1.9.16.2.47` | `signing_certificate_v2` |

## `cobaltform.tsp.Evidence`

Import `Evidence` from `cobaltform.tsp`. `Evidence((name, value))` accepts an evidence-alternative name and value. The result exposes `name`, typed `chosen`, selected `native`, and the shared ASN.1 value interfaces.

Alternative input names and value shapes:

| Alternative | Value |
| --- | --- |
| `tst_evidence` | Timestamp-entry collection. |
| `ers_evidence` | Evidence record. |
| `other_evidence` | Other-evidence record. |

### Timestamp-entry fields

| Field | Exchanged value |
| --- | --- |
| `time_stamp` | `EncapsulatedContentInfo`. |
| `crl` | `CertificateList` or absent field. |

### Evidence-record fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `digest_algorithms` | Digest-description collection. |
| `crypto_infos` | Attribute collection or absent field. |
| `encryption_info` | Encryption-information record or absent field. |
| `archive_time_stamp_sequence` | Archive-entry collection. |

### Encryption-information fields

| Field | Exchanged value |
| --- | --- |
| `encryption_info_type` | OID string. |
| `encryption_info_value` | Open ASN.1 value. |

### Archive-entry fields

| Field | Exchanged value |
| --- | --- |
| `digest_algorithm` | Digest description or absent field. |
| `attributes` | Attribute collection or absent field. |
| `reduced_hashtree` | List of lists of bytes or absent field. |
| `time_stamp` | CMS `ContentInfo`. |

### Other-evidence fields

| Field | Exchanged value |
| --- | --- |
| `oe_type` | OID string. |
| `oe_value` | Open ASN.1 value. |

### Evidence wire forms

Timestamp entries, evidence records, encryption information, archive entries and other evidence use ASN.1 SEQUENCE in their respective table orders. Timestamp-entry, digest-description and archive-entry collections use SEQUENCE OF. The evidence alternatives use context-specific implicit tags 0, 1 and 2 for `tst_evidence`, `ers_evidence` and `other_evidence`, respectively.

An archive entry's optional digest description, attributes and partial hash tree use context-specific implicit tags 0, 1 and 2. Attributes use SEQUENCE OF attribute records, and each attribute's values use SET OF. Partial hash trees use SEQUENCE OF SEQUENCE OF OCTET STRING. An evidence record's optional crypto information and encryption information use context-specific implicit tags 0 and 1. Its version uses INTEGER. Encryption-information type and other-evidence type use OBJECT IDENTIFIER; their values use open ASN.1 encodings.

## `cobaltform.tsp.PKIStatusInfo`

Import `PKIStatusInfo` from `cobaltform.tsp`. `PKIStatusInfo(value)` accepts a mapping; `load(encoded_data)` accepts ASN.1 bytes. The returned record supports named field indexing and assignment, `native`, and `dump() -> bytes`.

### Status fields

| Field | Exchanged value |
| --- | --- |
| `status` | Status name string. |
| `status_string` | List of text strings or absent field. |
| `fail_info` | Set of failure-name strings or absent field. |

## `cobaltform.tsp.TSTInfo`

Import `TSTInfo` from `cobaltform.tsp`. `TSTInfo(value)` accepts a mapping. The returned record supports named field indexing and assignment, `native`, and `dump() -> bytes`.

### Timestamp-information fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `policy` | OID string. |
| `message_imprint` | Message-imprint record using the form described for `TimeStampReq`. |
| `serial_number` | Integer. |
| `gen_time` | Aware date-time. |
| `accuracy` | Accuracy record or absent field. |
| `ordering` | Boolean. |
| `nonce` | Integer or absent field. |
| `tsa` | General-name value or absent field. |
| `extensions` | Extension collection using the form described for `TimeStampReq`, or absent field. |

### Accuracy fields

| Field | Exchanged value |
| --- | --- |
| `seconds` | Integer or absent field. |
| `millis` | Integer or absent field. |
| `micros` | Integer or absent field. |

Within a timestamp-token `ContentInfo`, the timestamp information is reached at `content`, then `encap_content_info`, then `content.parsed`.

## `cobaltform.tsp.TimeStampReq`

Import `TimeStampReq` from `cobaltform.tsp`. `TimeStampReq(value)` accepts a mapping; `load(encoded_data)` accepts ASN.1 bytes. The returned record supports named field indexing and assignment, `native`, and `dump() -> bytes`.

### Request fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `message_imprint` | Message-imprint record. |
| `req_policy` | OID string or absent field. |
| `nonce` | Integer or absent field. |
| `cert_req` | Boolean. |
| `extensions` | Extension collection or absent field. |

### Message-imprint fields

| Field | Exchanged value |
| --- | --- |
| `hash_algorithm` | Digest description with `algorithm` and `parameters`. |
| `hashed_message` | Digest bytes. |

### Extension fields

| Field | Exchanged value |
| --- | --- |
| `extn_id` | OID string. |
| `critical` | Boolean. |
| `extn_value` | Bytes. |

## `cobaltform.tsp.TimeStampResp`

Import `TimeStampResp` from `cobaltform.tsp`. `TimeStampResp(value)` accepts a mapping; `load(encoded_data)` accepts ASN.1 bytes. The returned record supports named field indexing and assignment, `native`, and `dump() -> bytes`.

### Response fields

| Field | Exchanged value |
| --- | --- |
| `status` | `PKIStatusInfo`. |
| `time_stamp_token` | CMS `ContentInfo`. |

## `cobaltform.tsp.TimeStampedData`

Import `TimeStampedData` from `cobaltform.tsp`. `TimeStampedData(value)` accepts a mapping; `load(encoded_data)` accepts ASN.1 bytes. The returned record supports named field indexing and assignment, `native`, and `dump() -> bytes`.

### Timestamped-data fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `data_uri` | URI text or absent field. |
| `meta_data` | Metadata record or absent field. |
| `content` | Bytes or absent field. |
| `temporal_evidence` | `Evidence` choice. |

### Metadata fields

| Field | Exchanged value |
| --- | --- |
| `hash_protected` | Boolean. |
| `file_name` | Text or absent field. |
| `media_type` | Text or absent field. |
| `other_meta_data` | Attribute collection with `type` and `values`, or absent field. |

Timestamped data and metadata use ASN.1 SEQUENCE in their respective table orders. Version uses INTEGER; data URI and media type use IA5String; hash protection uses BOOLEAN; file name uses UTF8String; content uses OCTET STRING; other metadata uses SEQUENCE OF attribute records with OBJECT IDENTIFIER `type` and SET OF open `values`.

## `cobaltform.util`

`cobaltform.util` exposes the following public names:

- `extended_date`

- `extended_datetime`

- `iri_to_uri`

- `uri_to_iri`

## `cobaltform.util.extended_date`

Import `extended_date` from `cobaltform.util`. `extended_date(year, month, day)` takes integer calendar components and returns an extended date object. Rejection is `ValueError`.

## `cobaltform.util.extended_datetime`

Import `extended_datetime` from `cobaltform.util`. The construction forms are `extended_datetime(year, month, day)` and `extended_datetime(year, month, day, hour, minute, second, tzinfo=<timezone>)`, with integer calendar/time components and a timezone object. An extended date-time value exposes `year`, `month`, `day`, `hour`, `minute`, `second`, `microsecond` (integers), `utcoffset() -> timedelta | None`, `strftime(format) -> str`, `isoformat() -> str`, and `replace(day=<int>) -> date-time`. It supports `<` with Python `datetime`, `+` with `timedelta`, and equality with date-time values. Rejection is `ValueError`.

## `cobaltform.util.iri_to_uri`

Import `iri_to_uri` from `cobaltform.util`. `iri_to_uri(value, normalize=<bool>)` accepts `str` and the optional normalization keyword, and returns ASCII URI `bytes`. Input-type rejection raises `TypeError`.

## `cobaltform.util.uri_to_iri`

Import `uri_to_iri` from `cobaltform.util`. `uri_to_iri(value)` accepts URI `bytes` and returns Unicode `str`. Input-type rejection raises `TypeError`.

## `cobaltform.x509`

`cobaltform.x509` exposes the following public names:

- `Certificate`

- `CertificateAux`

- `DNSName`

- `DirectoryString`

- `EmailAddress`

- `Extensions`

- `GeneralName`

- `GeneralNames`

- `Name`

- `NameTypeAndValue`

- `RDNSequence`

- `RelativeDistinguishedName`

- `SubjectDirectoryAttribute`

- `SubjectDirectoryAttributes`

- `Time`

- `TrustedCertificate`

- `URI`

- `strict_teletex`

### Key-usage bit positions

| Numeric identity | Text identity |
| --- | --- |
| `0` | `digital_signature` |
| `2` | `key_encipherment` |
| `8` | `decipher_only` |

### Distinguished-name attribute OIDs

| Numeric identity | Text identity |
| --- | --- |
| `2.5.4.3` | `common_name` |
| `2.5.4.4` | `surname` |
| `2.5.4.5` | `serial_number` |
| `2.5.4.6` | `country_name` |
| `2.5.4.7` | `locality_name` |
| `2.5.4.8` | `state_or_province_name` |
| `2.5.4.9` | `street_address` |
| `2.5.4.10` | `organization_name` |
| `2.5.4.11` | `organizational_unit_name` |
| `2.5.4.12` | `title` |
| `2.5.4.15` | `business_category` |
| `2.5.4.17` | `postal_code` |
| `2.5.4.20` | `telephone_number` |
| `2.5.4.41` | `name` |
| `2.5.4.42` | `given_name` |
| `2.5.4.43` | `initials` |
| `2.5.4.44` | `generation_qualifier` |
| `2.5.4.45` | `unique_identifier` |
| `2.5.4.46` | `dn_qualifier` |
| `2.5.4.65` | `pseudonym` |
| `2.5.4.97` | `organization_identifier` |
| `2.23.133.2.1` | `tpm_manufacturer` |
| `2.23.133.2.2` | `tpm_model` |
| `2.23.133.2.3` | `tpm_version` |
| `2.23.133.2.4` | `platform_manufacturer` |
| `2.23.133.2.5` | `platform_model` |
| `2.23.133.2.6` | `platform_version` |
| `1.2.840.113549.1.9.1` | `email_address` |
| `1.3.6.1.4.1.311.60.2.1.1` | `incorporation_locality` |
| `1.3.6.1.4.1.311.60.2.1.2` | `incorporation_state_or_province` |
| `1.3.6.1.4.1.311.60.2.1.3` | `incorporation_country` |
| `0.9.2342.19200300.100.1.1` | `user_id` |
| `0.9.2342.19200300.100.1.25` | `domain_component` |
| `0.2.262.1.10.7.20` | `name_distinguisher` |

### Reason-flag bit positions

| Numeric identity | Text identity |
| --- | --- |
| `1` | `key_compromise` |
| `2` | `ca_compromise` |
| `3` | `affiliation_changed` |
| `4` | `superseded` |
| `5` | `cessation_of_operation` |
| `6` | `certificate_hold` |
| `7` | `privilege_withdrawn` |
| `8` | `aa_compromise` |

### Policy-qualifier OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.3.6.1.5.5.7.2.1` | `certification_practice_statement` |

### Key-purpose OIDs

| Numeric identity | Text identity |
| --- | --- |
| `2.5.29.37.0` | `any_extended_key_usage` |
| `1.3.6.1.5.5.7.3.1` | `server_auth` |
| `1.3.6.1.5.5.7.3.2` | `client_auth` |
| `1.3.6.1.5.5.7.3.4` | `email_protection` |

### Access-method OIDs

| Numeric identity | Text identity |
| --- | --- |
| `1.3.6.1.5.5.7.48.1` | `ocsp` |
| `1.3.6.1.5.5.7.48.2` | `ca_issuers` |
| `1.3.6.1.5.5.7.48.5` | `ca_repository` |

### Netscape certificate-type bit positions

| Numeric identity | Text identity |
| --- | --- |
| `0` | `ssl_client` |
| `1` | `ssl_server` |
| `5` | `ssl_ca` |
| `7` | `object_signing_ca` |

### Document version

| Numeric identity | Text identity |
| --- | --- |
| `0` | `v1` |
| `1` | `v2` |
| `2` | `v3` |

### Generation-method enumeration

| Numeric identity | Text identity |
| --- | --- |
| `0` | `internal` |
| `1` | `injected` |
| `2` | `internal_revocable` |
| `3` | `injected_revocable` |

### Generation-location enumeration

| Numeric identity | Text identity |
| --- | --- |
| `0` | `tpm_manufacturer` |
| `1` | `platform_manufacturer` |
| `2` | `ek_cert_signer` |

### Certificate-generation-location enumeration

| Numeric identity | Text identity |
| --- | --- |
| `0` | `tpm_manufacturer` |
| `1` | `platform_manufacturer` |
| `2` | `ek_cert_signer` |

### Assurance-level enumeration

| Numeric identity | Text identity |
| --- | --- |
| `1` | `level1` |
| `2` | `level2` |
| `3` | `level3` |
| `4` | `level4` |
| `5` | `level5` |
| `6` | `level6` |
| `7` | `level7` |

### Evaluation-status enumeration

| Numeric identity | Text identity |
| --- | --- |
| `0` | `designed_to_meet` |
| `1` | `evaluation_in_progress` |
| `2` | `evaluation_completed` |

### Strength enumeration

| Numeric identity | Text identity |
| --- | --- |
| `0` | `basic` |
| `1` | `medium` |
| `2` | `high` |

### Security-level enumeration

| Numeric identity | Text identity |
| --- | --- |
| `1` | `level1` |
| `2` | `level2` |
| `3` | `level3` |
| `4` | `level4` |

### Subject-directory attribute OIDs

| Numeric identity | Text identity |
| --- | --- |
| `2.5.4.52` | `supported_algorithms` |
| `2.23.133.2.16` | `tpm_specification` |
| `2.23.133.2.17` | `tcg_platform_specification` |
| `2.23.133.2.18` | `tpm_security_assertions` |
| `1.3.6.1.5.5.7.9.3` | `pda_gender` |

### Certificate extension OIDs

| Numeric identity | Text identity |
| --- | --- |
| `2.5.29.9` | `subject_directory_attributes` |
| `2.5.29.14` | `key_identifier` |
| `2.5.29.15` | `key_usage` |
| `2.5.29.16` | `private_key_usage_period` |
| `2.5.29.17` | `subject_alt_name` |
| `2.5.29.18` | `issuer_alt_name` |
| `2.5.29.19` | `basic_constraints` |
| `2.5.29.30` | `name_constraints` |
| `2.5.29.31` | `crl_distribution_points` |
| `2.5.29.32` | `certificate_policies` |
| `2.5.29.33` | `policy_mappings` |
| `2.5.29.35` | `authority_key_identifier` |
| `2.5.29.36` | `policy_constraints` |
| `2.5.29.37` | `extended_key_usage` |
| `2.5.29.46` | `freshest_crl` |
| `2.5.29.54` | `inhibit_any_policy` |
| `1.3.6.1.5.5.7.1.1` | `authority_information_access` |
| `1.3.6.1.5.5.7.1.11` | `subject_information_access` |
| `1.3.6.1.5.5.7.1.24` | `tls_feature` |
| `1.3.6.1.5.5.7.48.1.5` | `ocsp_no_check` |
| `1.2.840.113533.7.65.0` | `entrust_version_extension` |
| `2.16.840.1.113730.1.1` | `netscape_certificate_type` |
| `1.3.6.1.4.1.11129.2.4.2` | `signed_certificate_timestamp_list` |
| `1.3.6.1.4.1.311.20.2` | `microsoft_enroll_certtype` |

## `cobaltform.x509.Certificate`

Import `Certificate` from `cobaltform.x509`. `Certificate(value)` accepts a field mapping; `Certificate.load(encoded_data)` accepts ASN.1 bytes. The returned record supports named field indexing, nested assignment, `native` and `dump() -> bytes`.

### Certificate fields

| Field | Exchanged value |
| --- | --- |
| `tbs_certificate` | Certificate-body record. |
| `signature_algorithm` | Signature algorithm description. |
| `signature_value` | Signature bytes. |

### Certificate-body fields

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `serial_number` | Integer serial number. |
| `signature` | Signature algorithm description. |
| `issuer` | `Name`. |
| `validity` | Record containing `not_before` and `not_after` time choices. |
| `subject` | `Name`. |
| `subject_public_key_info` | `PublicKeyInfo` record. |
| `issuer_unique_id` | Unique-identifier bytes or absent field. |
| `subject_unique_id` | Unique-identifier bytes or absent field. |
| `extensions` | Extension collection or absent field. |

### Validity fields

| Field | Exchanged value |
| --- | --- |
| `not_before` | `Time` choice. |
| `not_after` | `Time` choice. |

### Extension fields

| Field | Exchanged value |
| --- | --- |
| `extn_id` | OID with `native` name or numeric identity and `dotted` numeric identity, both strings. |
| `critical` | Boolean criticality. |
| `extn_value` | Embedded value with payload `contents: bytes`, typed `parsed`, and `native`. |

`issuer` returns `Name` for the issuer.

`subject` returns `Name` for the subject.

`serial_number` returns integer serial number.

`not_valid_before` returns date-time validity start.

`not_valid_after` returns date-time validity end.

`public_key` returns `PublicKeyInfo`.

`signature` returns signature `bytes`.

`signature_algo` returns signature-family string.

`hash_algo` returns digest-identity string.

`key_identifier` returns binary key identifier or `None`.

`authority_key_identifier` returns binary authority key identifier or `None`.

`ca` returns boolean authority status.

`max_path_length` returns integer path length or `None`.

`self_issued` returns boolean issuer/subject comparison result.

`self_signed` returns status string: `maybe` denotes a possible self-signature and `no` denotes no self-signature candidate.

`critical_extensions` returns set of extension name or numeric-identity strings.

`crl_distribution_points` returns list of distribution-point objects.

`delta_crl_distribution_points` returns list of delta distribution-point objects.

`ocsp_urls` returns list of URI strings.

`valid_domains` returns list of DNS identity strings.

`valid_ips` returns list of IP identity strings.

`sha1` returns digest `bytes`.

`sha256` returns digest `bytes`.

`sha1_fingerprint` returns a hexadecimal text string, with optional ASCII whitespace between octets.

`sha256_fingerprint` returns a hexadecimal text string, with optional ASCII whitespace between octets.

`private_key_usage_period_value` returns the typed extension value or `None`.

`subject_directory_attributes_value` returns the typed extension value or `None`.

`key_identifier_value` returns the typed extension value or `None`.

`key_usage_value` returns the typed extension value or `None`.

`subject_alt_name_value` returns the typed extension value or `None`.

`issuer_alt_name_value` returns the typed extension value or `None`.

`basic_constraints_value` returns the typed extension value or `None`.

`name_constraints_value` returns the typed extension value or `None`.

`crl_distribution_points_value` returns the typed extension value or `None`.

`certificate_policies_value` returns the typed extension value or `None`.

`policy_mappings_value` returns the typed extension value or `None`.

`authority_key_identifier_value` returns the typed extension value or `None`.

`policy_constraints_value` returns the typed extension value or `None`.

`freshest_crl_value` returns the typed extension value or `None`.

`inhibit_any_policy_value` returns the typed extension value or `None`.

`extended_key_usage_value` returns the typed extension value or `None`.

`authority_information_access_value` returns the typed extension value or `None`.

`subject_information_access_value` returns the typed extension value or `None`.

`tls_feature_value` returns the typed extension value or `None`.

`ocsp_no_check_value` returns the typed extension value or `None`.

`is_valid_domain_ip(domain_ip)` accepts text and returns `bool` for the identity-match result. Input-type rejection raises `TypeError`.

### Private-key usage value

| Field | Exchanged value |
| --- | --- |
| `not_before` | Date-time or absent field. |
| `not_after` | Date-time or absent field. |

### Basic constraints value

| Field | Exchanged value |
| --- | --- |
| `ca` | Boolean. |
| `path_len_constraint` | Integer or absent field. |

### Name constraints value

| Field | Exchanged value |
| --- | --- |
| `permitted_subtrees` | Collection of subtree records or absent field. |
| `excluded_subtrees` | Collection of subtree records or absent field. |

### Subtree value

| Field | Exchanged value |
| --- | --- |
| `base` | General-name value. |
| `minimum` | Integer. |
| `maximum` | Integer or absent field. |

### Distribution-point value

| Field | Exchanged value |
| --- | --- |
| `distribution_point` | Choice with `name`, `chosen` and selected-value `native`. |
| `reasons` | Set of reason names or absent field. |
| `crl_issuer` | List of general-name values or absent field. |

### Policy value

| Field | Exchanged value |
| --- | --- |
| `policy_identifier` | OID identity string. |
| `policy_qualifiers` | Collection of qualifier records or absent field. |

### Policy-qualifier value

| Field | Exchanged value |
| --- | --- |
| `policy_qualifier_id` | OID name or identity string. |
| `qualifier` | Typed qualifier value. |

### Policy mapping value

| Field | Exchanged value |
| --- | --- |
| `issuer_domain_policy` | OID identity string. |
| `subject_domain_policy` | OID identity string. |

### Authority-key identifier value

| Field | Exchanged value |
| --- | --- |
| `key_identifier` | Bytes or absent field. |
| `authority_cert_issuer` | General-name list or absent field. |
| `authority_cert_serial_number` | Integer or absent field. |

### Policy-constraints value

| Field | Exchanged value |
| --- | --- |
| `require_explicit_policy` | Integer or absent field. |
| `inhibit_policy_mapping` | Integer or absent field. |

### Information-access value

| Field | Exchanged value |
| --- | --- |
| `access_method` | OID name or identity string. |
| `access_location` | General-name value. |

### Entrust version value

| Field | Exchanged value |
| --- | --- |
| `entrust_vers` | Text. |
| `entrust_info_flags` | Tuple of bit integers. |

A distribution-point choice exposes the alternative name `full_name`; its selected value is a general-name collection.

Entrust version information uses an ASN.1 SEQUENCE with GeneralString `entrust_vers` and BIT STRING `entrust_info_flags`. Netscape certificate type uses BIT STRING; timestamp-list data uses OCTET STRING; Microsoft certificate-type text uses BMPString.

## `cobaltform.x509.CertificateAux`

Import `CertificateAux` from `cobaltform.x509`. `CertificateAux(value)` accepts an auxiliary field mapping. `load(encoded_data)` accepts ASN.1 bytes. The result supports string field access, `native` and `dump() -> bytes`.

### Auxiliary fields

| Field | Exchanged value |
| --- | --- |
| `trust` | Collection of purpose identity strings or absent field. |
| `reject` | Collection of purpose identity strings or absent field. |
| `alias` | Text or absent field. |
| `keyid` | Bytes or absent field. |
| `other` | Collection of algorithm descriptions or absent field. |

## `cobaltform.x509.DNSName`

Import `DNSName` from `cobaltform.x509`. `DNSName(value)` accepts text and returns a typed name value with equality returning `bool`. `load(encoded_data)` accepts ASN.1 bytes; `native` exposes text and `dump()` encoded bytes.

## `cobaltform.x509.DirectoryString`

Import `DirectoryString` from `cobaltform.x509`. `DirectoryString((name, value))` accepts an alternative-name string and text value. `load(encoded_data)` accepts ASN.1 bytes; `native` is text and `name` identifies the selected string alternative. `dump()` returns ASN.1 bytes.

Alternative input names and value shapes:

| Alternative | Value |
| --- | --- |
| `utf8_string` | Text. |
| `printable_string` | Text. |

A refused text decoding raises `UnicodeDecodeError`.

## `cobaltform.x509.EmailAddress`

Import `EmailAddress` from `cobaltform.x509`. `EmailAddress(value)` accepts text and returns a typed name value with equality returning `bool`. `load(encoded_data)` accepts ASN.1 bytes; `native` exposes text and `dump()` encoded bytes.

## `cobaltform.x509.Extensions`

Import `Extensions` from `cobaltform.x509`. `Extensions(value)` accepts a list of extension field dictionaries and returns an indexed, iterable collection. Each extension has `extn_id`, `critical` and `extn_value` fields, as described for `Certificate`.

## `cobaltform.x509.GeneralName`

Import `GeneralName` from `cobaltform.x509`. Construction accepts `GeneralName((name, value))` or `GeneralName(name, value)`. `load(encoded_data)` accepts ASN.1 bytes. The result has `name: str`, `chosen` as its selected typed value, `native` as its Python value and `dump(force=<bool>) -> bytes`.

Alternative input names and value shapes:

| Alternative | Value |
| --- | --- |
| `other_name` | Mapping with `type_id` (OID) and `value` (open ASN.1 value). |
| `rfc822_name` | Email-address text or an `EmailAddress` object. |
| `dns_name` | DNS text or a `DNSName` object. |
| `x400_address` | Record with `built_in_standard_attributes`, including `organization_name` text. |
| `directory_name` | `Name` object. |
| `edi_party_name` | Alternative identifier exposed by `name`. |
| `uniform_resource_identifier` | URI text. |
| `ip_address` | Address text, optionally followed by `/` and a decimal prefix length. |
| `registered_id` | Dotted OID string. |

`==` and `!=` return `bool`; selected values reached through `chosen` also support equality. Refused comparisons raise `ValueError`. Address-data rejection raises `ValueError` or `OSError`; prefix-data rejection raises `ValueError`.

## `cobaltform.x509.GeneralNames`

Import `GeneralNames` from `cobaltform.x509`. `GeneralNames(value)` accepts a list of `GeneralName` objects or choice inputs. It returns an indexed, iterable collection with `native` as a list of selected Python values.

## `cobaltform.x509.Name`

Import `Name` from `cobaltform.x509`. `Name(name='', value=<RDNSequence>)` constructs a distinguished-name choice. `Name.load(encoded_data)` accepts ASN.1 bytes. `chosen` is an indexed, iterable `RDNSequence`. Each RDN is an indexed, iterable collection of `NameTypeAndValue` records. `dump(force=<bool>)` returns name ASN.1 bytes.

`Name.build(name_dict, use_printable=<bool>)` accepts an attribute dictionary and an optional text-selection keyword. Keys are attribute-name strings or dotted OID strings; values are text or binary values as appropriate to the attribute. It returns `Name`. A refused attribute raises `ValueError`.

`native` is an attribute mapping. A value is text or bytes for a single occurrence, and a list of those values for repeated occurrences. The attribute keys used by construction and the native view are:

`incorporation_country`, `incorporation_state_or_province`, `incorporation_locality`, `business_category`, `serial_number`, `country_name`, `postal_code`, `state_or_province_name`, `locality_name`, `street_address`, `organization_name`, `organizational_unit_name`, `title`, `common_name`, `user_id`, `initials`, `generation_qualifier`, `surname`, `given_name`, `name`, `pseudonym`, `dn_qualifier`, `telephone_number`, `email_address`, `domain_component`, `name_distinguisher`, `organization_identifier`, `tpm_manufacturer`, `tpm_model`, `tpm_version`, `platform_manufacturer`, `platform_model`, `platform_version`, `unique_identifier`.

`==` and `!=` between names return `bool`. Refused directory-text comparison raises `ValueError`.

`sha1` returns name digest `bytes`.

`sha256` returns name digest `bytes`.

`human_friendly` is a text value consisting of labelled attribute fields. A field has form `<label>: <value>`; repeated values are separated by `, `. Fields use `, ` or `; ` as their separator; fields containing comma-separated value lists use `; ` between fields. A binary value uses a Python bytes-literal representation. Labels are:

`Incorporation Country`, `Incorporation State/Province`, `Incorporation Locality`, `Business Category`, `Serial Number`, `Country`, `Postal Code`, `State/Province`, `Locality`, `Street Address`, `Organization`, `Organizational Unit`, `Title`, `Common Name`, `User ID`, `Initials`, `Generation Qualifier`, `Surname`, `Given Name`, `Name`, `Pseudonym`, `DN Qualifier`, `Telephone Number`, `Email Address`, `Domain Component`, `Name Distinguisher`, `Organization Identifier`, `TPM Manufacturer`, `TPM Model`, `TPM Version`, `Platform Manufacturer`, `Platform Model`, `Platform Version`, `Unique Identifier`.

On the ASN.1 wire, `telephone_number` uses PrintableString; `email_address` and `domain_component` use IA5String; `unique_identifier` uses BIT STRING with binary-octet interpretation. The TPM and platform manufacturer, model and version attributes use UTF8String. The other listed attributes use DirectoryString.

## `cobaltform.x509.NameTypeAndValue`

Import `NameTypeAndValue` from `cobaltform.x509`. `NameTypeAndValue(value)` accepts a field dictionary and returns a record supporting string field access and field assignment.

### Attribute fields

| Field | Exchanged value |
| --- | --- |
| `type` | OID object with `dotted: str`. |
| `value` | Typed directory string or binary ASN.1 value with `native`. |

## `cobaltform.x509.RDNSequence`

Import `RDNSequence` from `cobaltform.x509`. `RDNSequence(value)` accepts a list of relative distinguished names and returns an indexed, iterable collection supporting `len()`.

## `cobaltform.x509.RelativeDistinguishedName`

Import `RelativeDistinguishedName` from `cobaltform.x509`. `RelativeDistinguishedName(value)` accepts a list of name-attribute records and returns an indexed, iterable collection supporting `len()`.

## `cobaltform.x509.SubjectDirectoryAttribute`

Import `SubjectDirectoryAttribute` from `cobaltform.x509`. `SubjectDirectoryAttribute.load(encoded_data)` accepts ASN.1 bytes and returns an attribute record with field access, `native` and `dump() -> bytes`.

### Attribute fields

| Field | Exchanged value |
| --- | --- |
| `type` | OID object with `native` name or identity and `dotted` numeric identity. |
| `values` | Collection of typed or open attribute values. |

## `cobaltform.x509.SubjectDirectoryAttributes`

Import `SubjectDirectoryAttributes` from `cobaltform.x509`. `SubjectDirectoryAttributes(value)` accepts a list of attribute mappings or `SubjectDirectoryAttribute` objects and returns an indexed, iterable collection. Attribute records have `type` and `values` fields; `dump()` returns ASN.1 bytes.

### Supported-algorithm value fields

| Field | Exchanged value |
| --- | --- |
| `algorithm_identifier` | Algorithm description. |
| `intended_usage` | Set of usage names or absent field. |
| `intended_certificate_policies` | Policy-information collection or absent field. |

### TPM specification values

| Field | Exchanged value |
| --- | --- |
| `family` | Text. |
| `level` | Integer. |
| `revision` | Integer. |

### Platform specification values

| Field | Exchanged value |
| --- | --- |
| `version` | Version-component record. |
| `platform_class` | Bytes. |

### Platform version components

| Field | Exchanged value |
| --- | --- |
| `major_version` | Integer. |
| `minor_version` | Integer. |
| `revision` | Integer. |

### Security assertion values

| Field | Exchanged value |
| --- | --- |
| `version` | Version name string. |
| `field_upgradable` | Boolean. |
| `ek_generation_type` | Generation-method name string or absent field. |
| `ek_generation_location` | Location name string or absent field. |
| `ek_certificate_generation_location` | Location name string or absent field. |
| `cc_info` | Common Criteria record or absent field. |
| `fips_level` | FIPS record or absent field. |
| `iso_9000_certified` | Boolean. |
| `iso_9000_uri` | Text or absent field. |

### Common Criteria values

| Field | Exchanged value |
| --- | --- |
| `version` | Text. |
| `assurance_level` | Level name string. |
| `evaluation_status` | Status name string. |
| `plus` | Boolean. |
| `strengh_of_function` | Strength name string or absent field. |
| `profile_oid` | OID string or absent field. |
| `profile_url` | Reference record or absent field. |
| `target_oid` | OID string or absent field. |
| `target_uri` | Reference record or absent field. |

### FIPS values

| Field | Exchanged value |
| --- | --- |
| `version` | Text. |
| `level` | Level name string. |
| `plus` | Boolean. |

### Reference values

| Field | Exchanged value |
| --- | --- |
| `uniform_resource_identifier` | URI text. |
| `hash_algorithm` | Digest description or absent field. |
| `hash_value` | Tuple of bit integers or absent field. |

TPM specification, platform specification, platform version, security assertion, Common Criteria, FIPS and reference records use ASN.1 SEQUENCE in the respective table orders. Attribute value collections use SET OF. TPM family uses UTF8String; specification levels, revisions and platform-version components use INTEGER; platform class uses OCTET STRING.

Security-assertion version uses INTEGER and flags use BOOLEAN. Generation method, generation location and certificate-generation location use context-specific implicit tags 0, 1 and 2 on ENUMERATED values. Common Criteria and FIPS records use context-specific implicit tags 3 and 4. ISO certification uses context-specific implicit tag 5 on BOOLEAN; its URI uses IA5String.

Common Criteria version uses IA5String; assurance and evaluation status use ENUMERATED; plus uses BOOLEAN. Its strength, profile identity, profile reference, target identity and target reference use context-specific implicit tags 0 through 4, respectively, on ENUMERATED, OBJECT IDENTIFIER, reference SEQUENCE, OBJECT IDENTIFIER and reference SEQUENCE. FIPS version uses IA5String, level uses ENUMERATED and plus uses BOOLEAN. A reference uses IA5String, an optional digest description and optional BIT STRING in that order.

## `cobaltform.x509.Time`

Import `Time` from `cobaltform.x509`. `Time(value)` accepts a one-entry choice mapping or an alternative/value pair. Its alternatives are `utc_time` and `general_time`, with date-time values. `name` identifies the alternative and `native` exposes the date-time.

## `cobaltform.x509.TrustedCertificate`

Import `TrustedCertificate` from `cobaltform.x509`. `TrustedCertificate(value)` accepts a two-item list containing a `Certificate` and `CertificateAux`. `load(encoded_data)` accepts concatenated document bytes. Integer index `0` selects the certificate and `1` the auxiliary record. `dump()` returns concatenated ASN.1 bytes.

## `cobaltform.x509.URI`

Import `URI` from `cobaltform.x509`. `URI(value)` accepts URI text and returns a typed value. Equality with another `URI` returns `bool`.

## `cobaltform.x509.strict_teletex`

Import `strict_teletex` from `cobaltform.x509`. `strict_teletex()` returns a context manager used as `with strict_teletex():` to select directory-string Teletex interpretation within that scope.

## `cobaltform.algos.AnyAlgorithmIdentifier.load`

Stated under `cobaltform.algos.AnyAlgorithmIdentifier`.

## `cobaltform.algos.DSASignature.from_p1363`

Stated under `cobaltform.algos.DSASignature`.

## `cobaltform.algos.DSASignature.load`

Stated under `cobaltform.algos.DSASignature`.

## `cobaltform.cms.AttributeCertificateV1.load`

Stated under `cobaltform.cms.AttributeCertificateV1`.

## `cobaltform.cms.ContentInfo.load`

Stated under `cobaltform.cms.ContentInfo`.

## `cobaltform.core.Any.load`

Stated under `cobaltform.core.Any`.

## `cobaltform.core.Asn1Value.load`

Stated under `cobaltform.core.Asn1Value`.

## `cobaltform.core.BitString.load`

Stated under `cobaltform.core.BitString`.

## `cobaltform.core.Boolean.load`

Import `Boolean` from `cobaltform.core`. `Boolean(value)` returns a typed ASN.1 value. `native` is `bool`. Its `load(encoded_data)` and `dump(force=<bool>)` use the shared `Asn1Value` interfaces.

The constructor value has type `bool`.

## `cobaltform.core.Integer.load`

Stated under `cobaltform.core.Integer`.

## `cobaltform.core.ObjectIdentifier.load`

Stated under `cobaltform.core.ObjectIdentifier`.

## `cobaltform.core.OctetString.load`

Stated under `cobaltform.core.OctetString`.

## `cobaltform.core.UTCTime.load`

Stated under `cobaltform.core.UTCTime`.

## `cobaltform.core.VideotexString.load`

Import `VideotexString` from `cobaltform.core`. `VideotexString(value)` accepts `bytes`; `native` is `bytes`. `load(encoded_data)` and `dump(force=<bool>)` use the shared ASN.1 value interfaces.

## `cobaltform.crl.CertificateList.load`

Stated under `cobaltform.crl.CertificateList`.

## `cobaltform.csr.CertificationRequest.load`

Stated under `cobaltform.csr.CertificationRequest`.

## `cobaltform.keys.DSAParams.load`

Stated under `cobaltform.keys.DSAParams`.

## `cobaltform.keys.ECPrivateKey.load`

Stated under `cobaltform.keys.ECPrivateKey`.

## `cobaltform.keys.NamedCurve.register`

Stated under `cobaltform.keys.NamedCurve`.

## `cobaltform.keys.PrivateKeyInfo.load`

Stated under `cobaltform.keys.PrivateKeyInfo`.

## `cobaltform.keys.PrivateKeyInfo.wrap`

Stated under `cobaltform.keys.PrivateKeyInfo`.

## `cobaltform.keys.PublicKeyInfo.load`

Stated under `cobaltform.keys.PublicKeyInfo`.

## `cobaltform.keys.PublicKeyInfo.wrap`

Stated under `cobaltform.keys.PublicKeyInfo`.

## `cobaltform.keys.RSAPublicKey.load`

Stated under `cobaltform.keys.RSAPublicKey`.

## `cobaltform.ocsp.OCSPRequest.load`

Stated under `cobaltform.ocsp.OCSPRequest`.

## `cobaltform.ocsp.OCSPResponse.load`

Stated under `cobaltform.ocsp.OCSPResponse`.

## `cobaltform.pdf.RevocationInfoArchival.load`

Stated under `cobaltform.pdf.RevocationInfoArchival`.

## `cobaltform.pkcs12.Pfx.load`

Stated under `cobaltform.pkcs12.Pfx`.

## `cobaltform.pkcs12.SafeContents.load`

Stated under `cobaltform.pkcs12.SafeContents`.

## `cobaltform.tsp.TimeStampReq.load`

Stated under `cobaltform.tsp.TimeStampReq`.

## `cobaltform.x509.Certificate.load`

Stated under `cobaltform.x509.Certificate`.

## `cobaltform.x509.CertificateAux.load`

Stated under `cobaltform.x509.CertificateAux`.

## `cobaltform.x509.DirectoryString.load`

Stated under `cobaltform.x509.DirectoryString`.

## `cobaltform.x509.GeneralName.load`

Stated under `cobaltform.x509.GeneralName`.

## `cobaltform.x509.Name.build`

Stated under `cobaltform.x509.Name`.

## `cobaltform.x509.Name.load`

Stated under `cobaltform.x509.Name`.

## `cobaltform.x509.SubjectDirectoryAttribute.load`

Stated under `cobaltform.x509.SubjectDirectoryAttribute`.

## `cobaltform.x509.TrustedCertificate.load`

Stated under `cobaltform.x509.TrustedCertificate`.
