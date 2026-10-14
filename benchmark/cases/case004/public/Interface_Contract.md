# Interface Contract

This document is the shell of the Signtoken library: the entries a caller imports and calls, what each accepts, and the exact form of what each returns or raises. What the product does with those inputs is specified in the Full PRD. Anything this document does not fix is stated below as the implementer’s choice.

## Package and layout

- The product is an importable Python library (Python 3.10 or newer), not a command-line program, service or wire protocol. There is no console script, no `python -m` entry, and no configuration file.
- The installable distribution and the importable top-level package are both named `signtoken`. The package is a single top-level directory `src/signtoken` (src layout); placing `src` on the import path makes it importable.
- Importing the package performs no I/O on caller files, starts no processes, and opens no sockets. Library calls return or raise; none exits the host process.
- These names are importable from the package root (`from signtoken import <name>`, or `signtoken.<name>`). Each is a class:

| Name | Role |
| --- | --- |
| `Signer` | basic signer (PRD FP-01) |
| `TimestampSigner` | timestamped signer (FP-03) |
| `Serializer` | serialize-and-sign helper (FP-02) |
| `TimedSerializer` | timestamped serialize-and-sign helper (FP-03) |
| `URLSafeSerializer` | URL-safe serialize-and-sign helper (FP-04) |
| `URLSafeTimedSerializer` | URL-safe timestamped serialize-and-sign helper (FP-04) |
| `HMACAlgorithm` | HMAC signing algorithm |
| `NoneAlgorithm` | no-op signing algorithm |
| `BadData`, `BadSignature`, `BadTimeSignature`, `SignatureExpired`, `BadPayload` | failure classes (see **Failures**) |

  Other public names may also be exported; that is the implementer’s choice.

## Common input conventions

- `secret_key` — first positional argument of every helper: one secret (`str` or `bytes`) or a sequence of secrets ordered oldest to newest. Text is encoded as UTF-8.
- `salt` — `str` or `bytes`; when omitted, a product-defined default is used (`<default>` in the signatures below). The default value is the implementer’s choice; it is the same for `Signer` and `TimestampSigner`, and the same for all four serializer types.
- `sep` — the separator, `str` or `bytes`, default `"."`.
- `key_derivation` — one of the strings `"concat"`, `"django-concat"`, `"hmac"`, `"none"`; when omitted or `None`, the default scheme.
- `digest_method` — a hash constructor from `hashlib` (for example `hashlib.sha1`); when omitted or `None`, the signer type’s `default_digest_method`.
- `algorithm` — an algorithm **instance** (`HMACAlgorithm(...)` or `NoneAlgorithm()`); when omitted or `None`, HMAC with the signer’s digest.
- Values to sign are `str` or `bytes`; tokens passed to recovery/load may be `str` or `bytes`.
- **Clock input.** Timestamped helpers read the system wall clock as a Unix-epoch number through the Python standard library (`time.time` or `time.time_ns`) at each call; which of the two is used, and whether it is looked up on the `time` module or imported by name, is the implementer’s choice. No other time source is used.

## Token forms

Placeholders: `<sep>` is the separator; `<payload>` is the signed value’s bytes; `<signature>`, `<time>` and `<b64payload>` are defined below.

| Helper | Token form | Type |
| --- | --- | --- |
| `Signer.sign` | `<payload><sep><signature>` | `bytes` |
| `TimestampSigner.sign` | `<payload><sep><time><sep><signature>` | `bytes` |
| `Serializer.dumps` | `<serialized><sep><signature>` | `str` when the dump/load object’s `dumps` returns `str`, else `bytes` |
| `TimedSerializer.dumps` | `<serialized><sep><time><sep><signature>` | as `Serializer.dumps` |
| `URLSafeSerializer.dumps` | `<b64payload><sep><signature>` | `str` |
| `URLSafeTimedSerializer.dumps` | `<b64payload><sep><time><sep><signature>` | `str` |

- `<serialized>` — exactly the output of the dump/load object’s `dumps(obj, **serializer_kwargs)` (UTF-8 encoded when it is text).
- `<signature>` — the signing algorithm’s output bytes encoded as URL-safe base64 (RFC 4648 §5) with the `=` padding removed. Under `NoneAlgorithm` it is empty.
- `<time>` — the signing time, written in characters from the URL-safe alphabet (letters, digits, `-`, `_`) and never containing `<sep>`. Its encoding is the implementer’s choice, except that it is at most 11 characters long. A time field of more than 11 characters from that alphabet is therefore never a signing time as the product writes it: a token whose signature verifies and whose time field is that long is refused as a malformed timestamp (PRD FP-03).
- `<b64payload>` — either the serialized payload encoded as URL-safe base64 (RFC 4648 §5) without padding, or `<sep>` followed by the compressed serialized payload encoded the same way. The compression format and level are the implementer’s choice.
- The signature covers everything before the last `<sep>`.

## `Signer`

```
Signer(secret_key, salt=<default>, sep=".", key_derivation=None, digest_method=None, algorithm=None)
```

- `Signer.default_digest_method` — class attribute holding a hash constructor. A subclass may assign another hash constructor to it in its class body.
- `sign(value) -> bytes` — token in the form above.
- `unsign(signed_value) -> bytes` — the payload; raises `BadSignature` on refusal.
- `validate(signed_value) -> bool` — `True` or `False`; never raises for a bad token.
- A refused separator makes the constructor raise; the exception class is the implementer’s choice.
- A key-derivation name outside the four built-in names makes construction or `sign` raise (exception class the implementer’s choice), or yields tokens that `unsign` refuses.

## `TimestampSigner`

```
TimestampSigner(secret_key, salt=<default>, sep=".", key_derivation=None, digest_method=None, algorithm=None)
```

- Same constructor, `default_digest_method`, refusals and `sign` signature as `Signer`.
- `unsign(signed_value, max_age=None, return_timestamp=False)` — returns the payload as `bytes`, or, when `return_timestamp` is true, the tuple `(payload_bytes, signed_at)` where `signed_at` is a `datetime.datetime` with `tzinfo` UTC. `max_age` is a number of seconds or `None` (no age check). Raises a failure class on refusal.
- `validate(signed_value, max_age=None) -> bool` — never raises for a bad, expired, or timestamp-less token.

## `HMACAlgorithm` / `NoneAlgorithm`

```
HMACAlgorithm(digest_method=None)
NoneAlgorithm()
```

- Instances are passed as a signer’s `algorithm`. `HMACAlgorithm` with no `digest_method` uses SHA-1. `NoneAlgorithm` produces an empty signature.

## `Serializer` and `TimedSerializer`

```
Serializer(secret_key, salt=<default>, serializer=None, serializer_kwargs=None, signer=None, signer_kwargs=None, fallback_signers=None)
TimedSerializer(secret_key, salt=<default>, serializer=None, serializer_kwargs=None, signer=None, signer_kwargs=None, fallback_signers=None)
```

- `serializer` — an object (module or instance) with `dumps(obj, **kwargs)` returning `str` or `bytes` and `loads(data)`. Default: the standard `json` module.
- `serializer_kwargs` — a mapping of keyword arguments passed to every `serializer.dumps` call.
- `signer` — a signer **class**; default `Signer` for `Serializer`, `TimestampSigner` for `TimedSerializer`. It is called as `signer(secret_key, salt=salt, **signer_kwargs)`.
- `signer_kwargs` — mapping of signer constructor keywords (`sep`, `key_derivation`, `digest_method`, `algorithm`).
- `fallback_signers` — a list whose items are each a mapping of signer keywords, a signer class, or a `(signer_class, mapping)` tuple.
- An illegal `sep` in `signer_kwargs` makes the constructor or the first `dumps` raise; no token is returned.

Methods:

| Method | Returns |
| --- | --- |
| `dumps(obj, salt=None)` | token (form above) |
| `dump(obj, f, salt=None)` | writes the `dumps` token with `f.write`; return value is the implementer’s choice |
| `loads(s, salt=None)` (`Serializer`) | the object |
| `loads(s, max_age=None, return_timestamp=False, salt=None)` (`TimedSerializer`) | the object, or `(obj, signed_at)` when `return_timestamp` is true (`signed_at` as on `TimestampSigner.unsign`) |
| `load(f, salt=None)` | `loads(f.read())` |
| `loads_unsafe(s, salt=None)` (`Serializer`); `loads_unsafe(s, max_age=None, salt=None)` (`TimedSerializer`) | a 2-tuple `(signature_valid, obj)`: `(True, obj)`, `(False, obj)`, or `(False, None)` when no object can be produced; raises `BadPayload` for a payload-decode failure |
| `load_unsafe(f, salt=None)` | `loads_unsafe(f.read())` |

`f` is a text stream for `str` tokens and a binary stream for `bytes` tokens. A refusing `loads`/`load` raises a failure class.

## `URLSafeSerializer` and `URLSafeTimedSerializer`

```
URLSafeSerializer(secret_key, salt=<default>, serializer=None, serializer_kwargs=None, signer=None, signer_kwargs=None, fallback_signers=None)
URLSafeTimedSerializer(secret_key, salt=<default>, serializer=None, serializer_kwargs=None, signer=None, signer_kwargs=None, fallback_signers=None)
```

- `salt` may be passed positionally as the second argument.
- Same parameters and methods as `Serializer` / `TimedSerializer` respectively (`URLSafeTimedSerializer.loads` and `loads_unsafe` take `max_age`, and `loads` takes `return_timestamp`). The default dump/load object is compact JSON. `dumps` returns `str`.

## Failures

Every refusal by `unsign`, `loads`, `load`, and `loads_unsafe` raises an instance of one of these classes, all subclasses of `Exception`:

| Class | Base | Attributes | Raised for (PRD kind) |
| --- | --- | --- | --- |
| `BadData` | `Exception` | — | base of all failure classes |
| `BadSignature` | `BadData` | `payload`: the token’s unverified payload section as `bytes`, or `None` when the token has none | signature mismatch; on timestamped helpers, the plain signature mismatch (an instance that is not a `BadTimeSignature`) |
| `BadTimeSignature` | `BadSignature` | `payload`: as above (without the time field); `date_signed`: the decoded signing time as a `datetime.datetime` with `tzinfo` UTC, or `None` when there is none; `reason`: the string `"missing"` for a missing timestamp, the string `"malformed"` for a malformed timestamp, `None` otherwise | time-signature failure, missing timestamp, malformed timestamp |
| `SignatureExpired` | `BadTimeSignature` | `payload`, `date_signed` (always a datetime), `reason` (`None`) | expired token |
| `BadPayload` | `BadData` | `original_error`: the exception raised while decoding or deserializing the payload | payload-decode failure |

- Failure messages (`str()`) are free text, the implementer’s choice.
- For the serializers, `payload` is the payload section as it appears in the token (for URL-safe helpers, still in its encoded form), as `bytes`.
