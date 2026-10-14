# Signtoken — Full Product Requirements Document

## Product overview

**Signtoken** is a Python library of helpers for passing data to untrusted environments and getting it back intact. A token is cryptographically signed so that a later load can tell whether anyone changed the payload. The receiver can read the data; they cannot produce a different payload that still verifies, unless they also have the secret key.

The product’s own three-line summary of what it delivers:

- Data is cryptographically signed so a token that has been tampered with is rejected.
- How the payload is serialized is customizable. The default is JSON.
- A timestamp can be recorded at sign time and checked automatically on load. Data is compressed when that actually shortens a URL-safe token.

A first-time integrator constructs a URL-safe serialize-and-sign helper with a secret key and a salt, dumps a mapping, hands the resulting text token to a client or email link, and later loads that same token to recover the mapping. That path is specified under FP-04. It rests on the basic signer (FP-01) and the serialize-and-sign helper (FP-02). Timestamped helpers (FP-03) add an age check on top of those.

This document specifies **user- and integrator-observable behavior only**. Exact published symbol names, import paths, call spellings, token layouts and failure forms belong in the Interface Contract, not here. Every feature point below corresponds to behavior that exists in the finished Signtoken product. Feature points are ordered so foundational capabilities come first; a later feature point may refine an earlier one only when it says so explicitly.

## Terminology

| Term | Meaning in this PRD |
| --- | --- |
| **Secret key** | A value only the signer’s owner should know. It may be one key or a list of keys oldest-to-newest for rotation. Changing the secret invalidates tokens that were signed with keys no longer in the list. |
| **Salt** | Extra material mixed with the secret to isolate signing contexts. The salt does not have to be secret; it does have to differ between contexts that must not accept each other’s tokens. |
| **Token** | The signed string or byte string emitted by a helper. A valid token verifies and yields the original payload; a tampered token does not. |
| **Signer** | The basic helper: it signs raw byte values and later verifies them. It does not serialize objects and does not record a timestamp. Specified in FP-01. |
| **Serializer** | A helper that serializes an object with an internal dump/load object (JSON by default), then signs that payload with a signer. Specified in FP-02. |
| **Timestamped signer / timestamped serializer** | The signer and serializer variants that also record signing time and can refuse a token older than a caller-supplied maximum age. Specified in FP-03. |
| **URL-safe serializer** | A serializer whose tokens use only a URL-safe alphabet, and that compresses the payload when compression shortens it. Specified in FP-04. The URL-safe timestamped serializer is the same encoding plus FP-03’s age check. |
| **Separator** | The delimiter between the payload, any timestamp field, and the signature. The product default is a period. |
| **Digest** | The hash function used by the HMAC signature and by key derivation. The product default is SHA-1. |
| **Key-derivation scheme** | How the signing key is derived from the secret and the salt. The four built-in names are `concat`, `django-concat`, `hmac`, and `none`. The product default is `django-concat`. |
| **Fallback signing configuration** | An extra signing setup a serializer tries when the current configuration cannot verify a token, so parameters can be upgraded without instantly invalidating old tokens. |
| **Unsafe load** | An inspection entry for signature problems: it reports whether the signature verified, and yields the payload when that payload can still be decoded. A signature mismatch does not abort the caller. It does not make a bad token valid. |
| **Signature mismatch** | The refusal kind for a token whose signature does not verify (or that has no separator). It carries the unverified payload section when the token has one. |
| **Payload-decode failure** | The refusal kind for a token whose signature verifies but whose payload cannot be decoded or deserialized. It retains the underlying decode error. |
| **Core capability** | A user-observable capability that reflects Signtoken’s design goal. |

## Public surface inventory

Signtoken is a **library**, not a command users type. Integrators install the package and construct helpers in Python.

The public surfaces are:

- The signer: sign a value, recover the original bytes from a valid token, check validity without recovering the payload, reject a tampered or separator-less value, isolate contexts with a salt, rotate keys, choose a digest and a key-derivation scheme, and opt into HMAC or a no-op algorithm (FP-01).
- The serializer: dump an object to a signed token and load it back; dump and load through a file stream; inspect a failed signature; unsafe load; per-call salt; custom dump/load object; fallback signing configurations (FP-02).
- Timestamped signing and serialize-and-sign: record signing time, enforce a maximum age in seconds, return the signing time as a timezone-aware UTC datetime, and distinguish expiry from a missing or malformed timestamp and from a mere signature mismatch (FP-03).
- URL-safe serialize-and-sign, with and without timestamps: tokens restricted to a URL-safe alphabet, compression when it shortens the payload, and the round-trip of a mapping through a URL-safe helper (FP-04).

Standalone URL-safe encoding helpers exist so signatures can be encoded; they are not a separate core capability. Failure kinds (signature mismatch, payload-decode failure, missing or malformed timestamp, time-signature failure, expired signature) are specified with the helper that raises them, not as their own feature point.

## Non-functional constraints

- **Form factor:** A pure-Python library. No compiled extensions, native code, GPU, or accelerator are required or claimed. Zero declared runtime dependencies.
- **Language:** Python 3.10 or newer.
- **Platforms:** Intended to work on Linux, macOS, and Windows. Linux with a supported interpreter is the reference platform.
- **Hardware:** CPU-only. There is no accelerator profile.
- **Integrity, not confidentiality:** A verified token yields the original object. The payload is not encrypted. Anyone who can see a default JSON token can read the JSON text in it; they still cannot forge a new payload that verifies without the secret.
- **Default digest:** SHA-1. A project that wants a different digest configures one (FP-01, FP-02).
- **Default key derivation:** `django-concat`.
- **Default separator:** a period.
- **Default payload format (serializer):** JSON from the language’s built-in JSON library. The URL-safe helper uses compact JSON (no whitespace outside strings) so tokens stay short.
- **Clock:** Signing time and check time are read from the system clock (seconds since the Unix epoch) at the moment of each call, truncated to whole seconds.

## Core capabilities (global)

Every feature point below is a **core capability**. None is an accelerator-backed feature. A token is accepted only when its signature verifies under the configured secret, salt, scheme, digest and algorithm, and a timestamped helper enforces the maximum age.

## Non-goals

- Encrypting payloads so the receiver cannot read them. Signtoken signs; it does not hide.
- Being a general-purpose JWT / JWS stack. JSON Web Signature helpers were removed; they are not part of this product.
- Shipping a command-line program, HTTP server, or cookie framework. Those are application patterns that *use* tokens; they are not Signtoken commands.
- Treating the exported URL-safe base64 encode/decode utilities as a core capability. They exist to serve the signer and the URL-safe serializer.
- A header-bearing token format. A header-related failure kind exists for historical reasons; no remaining public helper emits a separate signed header.
- Guaranteeing a particular token throughput or token size beyond the compression rule in FP-04.
- Key-generation or key-storage machinery. How an application creates and rotates the list of secrets is outside the library; the library accepts one key or a list (FP-01).

---

## Feature points

### FP-01: Cryptographic signing of byte values

**Public entry:** Signtoken’s signing helper, constructed with a secret key. The caller may also supply a salt, a separator, a digest, a key-derivation scheme, and a signing algorithm. This is the basic system: it signs bytes (or text, which is encoded as UTF-8) and later verifies them. It does not serialize objects (FP-02), does not record a timestamp (FP-03), and does not rewrite the payload into a URL-safe alphabet (FP-04).

**Normal behavior:**

- Signing a value yields a byte-string token made of the payload, the separator, and a signature. Text is encoded as UTF-8 before signing. Recovering a valid token with an equivalently configured signer yields the payload as bytes; recovery does not record whether the original was text or bytes.
- A separate validity check reports success or failure as a boolean, never returns the payload, and never raises for a bad token.
- The payload may itself contain the separator. The signature never contains the separator, so the signature section is everything after the last separator and the payload section is everything before it.
- Under HMAC, any alteration of a signed token — to the payload, the separator or the signature, including truncation or a single changed bit — makes recovery refuse the token as a signature mismatch and the validity check report failure.
- A refused token that contains the separator carries its unverified payload section (bytes) on the failure. A value that contains no separator at all is refused as a signature mismatch that carries no payload.
- The signing key is derived from the secret and the salt. Signers that share a secret but differ in salt do not recover each other’s tokens, except under the `none` scheme, where the salt is not mixed in. When the caller omits the salt, a fixed product-defined default salt is used, so identically constructed signers interchange tokens.
- The secret may be a list of keys ordered oldest to newest. Signing uses the newest key. Recovery accepts a token that any key currently in the list verifies; a token signed only with a key that is no longer in the list is refused.
- The four built-in key-derivation schemes are `concat`, `django-concat`, `hmac`, and `none`; the default is `django-concat`. Every scheme round-trips under its own signer. Under `none` the signing key is the secret itself; `concat`, `django-concat` and `hmac` each mix the salt into the key, and the four schemes derive different keys from the same secret and salt, so tokens do not interchange between schemes.
- The digest may be any hash constructor of the language’s standard hashing library. The default is SHA-1; passing SHA-1 explicitly yields the same tokens as the default. The digest is used by the HMAC signature and by key derivation, so the signature length follows the digest size, and signers with different digests do not recover each other’s tokens.
- A signer type may declare its own default digest; it applies whenever no digest is passed at construction. A digest passed at construction always takes precedence.
- The default signing algorithm is HMAC (RFC 2104) with the configured digest, keyed with the derived key, computed over the payload bytes. The caller may instead supply a no-op algorithm whose signature is empty: such a signer still round-trips, but provides no tamper detection — a changed payload with an empty signature is recovered as the changed payload and reported valid. An HMAC signer refuses no-op tokens and a no-op signer refuses HMAC tokens.

**Boundary / error behavior:**

- A separator that is an ASCII letter, an ASCII digit, a hyphen, an underscore, or an equals sign is refused when the signer is constructed, because those characters can appear in an encoded signature. Other separators, including the default period, are accepted.
- A key-derivation name other than the four built-in names is not treated as the default: no verified token is produced under it (construction or signing refuses, or the emitted token does not verify).
- A wrong secret, a changed payload or signature, or a wrong salt (except under `none`) all refuse recovery; none of those paths returns a value as a successful recovery.

---

### FP-02: Serialize and sign structured objects

**Public entry:** Signtoken’s serialize-and-sign helper, constructed with a secret key. The caller may also supply a salt, an internal dump/load object, extra dump options, a signer type, signing options, and fallback signing configurations. This helper wraps a signer (FP-01) so callers can round-trip objects other than raw bytes. It does not add a timestamp unless the timestamped serializer of FP-03 is used, and it does not force a URL-safe alphabet unless the URL-safe helper of FP-04 is used.

**This feature point uses FP-01.** The helper constructs its signer from the signer type with the helper’s secret, salt and signing options; secret lists, salts, separators, digests, and key-derivation schemes behave as in FP-01 for that signer.

**Normal behavior:**

- Dump serializes the object with the dump/load object and signs the serialized payload; load verifies and deserializes it. Dump then load recovers an object equal to any value the dump/load object can represent.
- The default dump/load object is the language’s built-in JSON library used with its default settings: the payload section of a default token is exactly the text that library produces for the object.
- When the dump/load object produces text, dump returns text; when it produces bytes, dump returns bytes. Load accepts a token as text or as its UTF-8 bytes.
- An object can be dumped into a file stream (the token is written) and loaded back from that stream (the whole stream is read and loaded); the result equals the original. Unsafe load works the same way from a stream.
- A salt passed to an individual dump or load call replaces the helper’s salt for that call. A token loads only under the salt it was dumped with, except under the `none` scheme, where the salt is not mixed in.
- The caller may replace the dump/load object with any object that offers dump and load. Extra dump options are passed unchanged to every dump call of that object.
- Replacing the signer type or the signing options changes the signer the helper builds; dump then load still round-trips, and helpers whose signing configurations differ (for example in key-derivation scheme or digest) neither produce equal tokens for the same object nor load each other’s tokens. When the signing options name no digest, the signer type’s own default digest applies; a digest named in the signing options takes precedence.
- Fallback signing configurations are tried, in the order listed, after the current configuration fails to verify a token; the first one that verifies is used, and a token verified by any of them loads. Each fallback item is one of: a mapping of signing options, used with the helper’s signer type in place of the current signing options; a signer type, constructed with the helper’s current signing options; or a pair of a signer type and a mapping of signing options. Every fallback is tried with each key of the secret list.
- When load refuses a token as a signature mismatch, the failure carries the unverified payload section; deserializing it with the helper’s dump/load object recovers the object that was dumped. That is inspection, not a successful load.
- Unsafe load returns a pair: whether the signature verified, and the object. For a valid token it is (true, object). For a signature mismatch it is (false, object) when the carried payload can still be deserialized, and (false, no object) when there is no payload or it cannot be deserialized. A signature mismatch never aborts the caller.

**Boundary / error behavior:**

- Any alteration of a dumped token is refused as a signature mismatch; it never yields a successful load.
- When the signature verifies but the payload cannot be deserialized, load refuses with a payload-decode failure that retains the error the dump/load object raised. This includes a JSON helper given a verified payload in another format. Unsafe load raises the same payload-decode failure instead of returning a pair.
- A signature mismatch and a payload-decode failure are different refusal kinds.
- If the current configuration and every fallback fail to verify, load refuses with a signature mismatch.

---

### FP-03: Timestamped signatures and expiry

**Public entry:** Signtoken’s timestamped signer and timestamped serialize-and-sign helper. Each is constructed like the corresponding helper in FP-01 or FP-02 (the timestamped serializer uses the timestamped signer by default) and records the signing time in the token. On recovery or load, the caller may supply a maximum age in seconds and may ask to receive the signing time. **This feature point refines FP-01 and FP-02:** the basic signer and serializer do not record or check age. A timestamped helper that is also URL-safe is specified with FP-04; the rules here still apply there.

A timestamped signer still satisfies every FP-01 obligation, and a timestamped serializer every FP-02 obligation. A timestamped helper uses the same default salt, key derivation and signature as its non-timestamped counterpart, so a token from an equally configured non-timestamped helper (same secret, and same salt or both omitted) verifies on it; the same holds between the URL-safe helper and the URL-safe timestamped helper. The obligations below are the time field and the age check.

**Normal behavior:**

- The token carries a time field between the payload and the signature, separated by the separator; the signature covers the payload and the time field. The time field records the signing time in whole seconds since the Unix epoch, read from the system clock when the token is signed. Signing does not convert the clock reading to a calendar date, so it succeeds even when the clock reports an instant past the last date the language’s standard date-time type can represent. The payload may contain the separator; the time field is the part between the last two separators.
- With no maximum age, recovery yields the original value (bytes for the signer, the object for the serializer) regardless of age. Asking for the signing time yields the value and a timezone-aware UTC datetime equal to the recorded signing second; any equivalently configured helper reads the same signing time from the token.
- With a maximum age of N seconds, the age is the current system-clock time in whole seconds minus the recorded signing second. The token is **expired** when the age is greater than N or less than zero; otherwise it is accepted. The age is checked only after the signature verifies.
- An expired failure carries the payload and the signing time. A validity check given a maximum age reports failure on an expired token and success otherwise; unsafe load given a maximum age returns (false, object) for an expired token.
- On a timestamped serializer with fallbacks, a configuration that verifies the signature but finds the token expired ends the search: the load is refused as expired and later fallbacks are not tried.

**Boundary / error behavior:**

- **Missing timestamp:** the signature verifies but the signed part contains no separator, so there is no time field. It carries no signing time.
- **Malformed timestamp:** the signature verifies but the time field does not decode to a signing time as the product writes it. It carries no signing time.
- **Time-signature failure:** the signature does not verify and the signed part contains a separator. It is a signature mismatch that carries the payload (the part before the time field) and, when the time field decodes to a representable time, that signing time. When the time field decodes to a time that the language’s standard date-time type cannot represent as a UTC calendar date and time, the refusal is a malformed timestamp instead.
- A token whose signature does not verify and whose signed part has no separator is a plain signature mismatch, not a missing timestamp.
- Expired, missing-timestamp, malformed-timestamp, time-signature and plain signature-mismatch refusals are different kinds. Expiry is never a successful load.
- A missing-timestamp refusal and a malformed-timestamp refusal each identify their own kind on the failure; a time-signature, expired or plain signature-mismatch refusal identifies neither.

---

### FP-04: URL-safe tokens

**Public entry:** Signtoken’s URL-safe serialize-and-sign helper, and the URL-safe timestamped serialize-and-sign helper. **This feature point refines FP-02:** the token is text in a restricted alphabet, and the payload is compressed when that shortens it. The URL-safe timestamped helper also applies FP-03.

The URL-safe helper still satisfies the serializer behavior of FP-02 (object round-trip, tamper refusal, salt, fallbacks, unsafe load, streams, custom dump/load object). The URL-safe timestamped helper also satisfies FP-03.

**Normal behavior:**

- Dump returns text. Every character of a token is an ASCII letter, digit, underscore, hyphen, or period.
- The default dump/load object writes JSON with no whitespace outside strings.
- The serialized payload is compressed with a lossless general-purpose format that substantially shrinks highly repetitive data. Compression is used only when it makes the payload strictly shorter, and a payload that it shrinks substantially is always compressed; otherwise the payload is left uncompressed. The payload section is the URL-safe base64 encoding of the (possibly compressed) payload, and a compressed payload section is marked by a leading separator. Both forms load, on the same helper and on any equivalently configured helper.
- The URL-safe timestamped helper dumps and loads the same objects, still as URL-safe text, and applies FP-03’s time field, maximum age and signing time to compressed and uncompressed tokens alike.

**Boundary / error behavior:**

- Any alteration of a URL-safe token, compressed or not, is refused as a signature mismatch.
- With a verifying signature, a payload section that is not valid URL-safe base64, a payload marked compressed that is not an intact compressed stream as the product writes it, or a payload that does not deserialize is refused as a payload-decode failure.
- Characters outside the URL-safe alphabet are not required to be accepted; tokens the product emits never contain them.
