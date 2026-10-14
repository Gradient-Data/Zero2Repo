# Interface Contract

This document is the complete shell of Otpkit: what a caller imports and calls, what each call accepts, and the form of everything it hands back. What the product computes, and under which conditions, is stated in the Full PRD.

## Package

- The product is an importable Python package named `otpkit`. Its source lives in a single top-level package directory `otpkit` under `src` (src layout); putting `src` on the import path is enough to import it.
- These names are importable from the package root (`import otpkit` / `from otpkit import <name>`): `random_base32`, `random_hex`, `HOTP`, `TOTP`, `parse_uri`. Other public names are the implementer's choice.
- There is no command-line program, no `python -m` entry, no configuration file and no network service. Importing the package and calling any entry below performs no file, process, environment or socket I/O, prints nothing, and never exits the host process; every outcome is a return value or a raised exception.

## Value forms used below

- `<base32 secret>`: a `str` of base32 text.
- `<code>`: a `str` of decimal digits whose length is the helper's digit count. Never an `int`.
- `<candidate>`: a `str`.
- `<digest>`: a hash constructor from the standard `hashlib` module (for example `hashlib.sha256`).
- `<instant>`: a Unix timestamp (`int` or `float`, seconds) or a `datetime.datetime` (timezone-aware or naive).
- `<count>`, `<offset>`, `<window>`, `<initial count>`, `<length>`, `<digits>`, `<interval>`: `int`.
- `<text>`: a `str`.
- `<default>`: the parameter is optional and its default is the product default the PRD states.

**Failure forms.** Where a call below "raises", the caller observes an exception; its class and message are the implementer's choice. Where a call below "refuses", it either raises (class and message free) or returns a value of a different kind than its success value (stated per call); which of the two is the implementer's choice.

## `otpkit.random_base32`

```
random_base32(length=<default>) -> str
```

- `length` may be passed positionally or by name.
- Success: a `str` of `length` characters from the base32 secret alphabet.
- Failure: raises; no string is returned.

## `otpkit.random_hex`

```
random_hex(length=<default>) -> str
```

- `length` may be passed positionally or by name.
- Success: a `str` of `length` characters from the hex secret alphabet.
- Failure: raises; no string is returned.

## `otpkit.HOTP`

```
HOTP(<base32 secret>, digits=<default>, digest=<default>, name=<text>, issuer=<text>, initial_count=<default>)
```

- The secret is the first positional argument. The other parameters are passed by name: `digits` (digit count), `digest` (a `<digest>`), `name` (account name, optional), `issuer` (issuer, optional), `initial_count` (starting counter).
- Success: an `HOTP` instance. Refused construction: raises, or returns something that is not an `HOTP`/`TOTP` instance.

```
helper.at(<count>) -> <code>
```

- `<count>` is the relative count, positional. Success: a `<code>`. Failure: raises; no code is returned.

```
helper.verify(<candidate>, <count>) -> bool
```

- Both positional. Returns `True` when the candidate is accepted and `False` when it is not; a rejected candidate never raises.

```
helper.provisioning_uri(name=<text>, initial_count=<initial count>, issuer_name=<text>, **<extra fields>) -> str
```

- Every argument is passed by name and is optional: `name` (account-name override), `initial_count` (starting-counter override), `issuer_name` (issuer override; the constructor spelling is `issuer`). Any other keyword `<key>=<value>` is an extra query field named `<key>`; `image` is such a field.
- Success: a `str`, the otpauth URI in the form below. Refused build: raises, or returns a value that is not otpauth text.

## `otpkit.TOTP`

```
TOTP(<base32 secret>, digits=<default>, digest=<default>, name=<text>, issuer=<text>, interval=<default>)
```

- The secret is the first positional argument. The other parameters are passed by name: `digits`, `digest`, `name`, `issuer` as for `HOTP`; `interval` (time-step length in seconds).
- Success: a `TOTP` instance. Refused construction: raises, or returns something that is not an `HOTP`/`TOTP` instance.

```
helper.now() -> <code>
```

- No arguments. The current instant is read from the process clock, at the time of the call, through one of the Python standard-library wall-clock functions `time.time`, `time.time_ns`, `datetime.datetime.now`, `datetime.datetime.utcnow` or `datetime.datetime.today` (whether it is looked up on its module at call time or a name for it was imported at module import); the same holds wherever an instant is omitted below.

```
helper.at(<instant>, <offset>) -> <code>
```

- `<instant>` positional; `<offset>` (whole time steps) positional and optional (`<default>`). Success: a `<code>`. Refused: raises, or returns a value that is not a decimal-digit `str`.

```
helper.verify(<candidate>, <instant>, <window>) -> bool
helper.verify(<candidate>, valid_window=<window>) -> bool
```

- `<candidate>` positional. `<instant>` is the second positional argument and optional (omitted: the process clock). The acceptance window is the third positional argument or the keyword `valid_window`, optional (`<default>`).
- Returns `True` when the candidate is accepted and `False` when it is not; a rejected candidate never raises.

```
helper.verify_and_get_timecode(<candidate>, <instant>, <window>) -> int | False
```

- All three positional; `<instant>` and `<window>` optional (omitted instant: the process clock; omitted window: `<default>`).
- Accepted: the matching time-step number as an `int` (never a `bool`). Not accepted: returns `False`, never raises. Refused window: raises; no step number is returned.

```
helper.provisioning_uri(name=<text>, issuer_name=<text>, **<extra fields>) -> str
```

- As for `HOTP.provisioning_uri`, without `initial_count`.

## `otpkit.parse_uri`

```
parse_uri(<uri>) -> HOTP | TOTP
```

- `<uri>` is a `str`, positional.
- Success: a `TOTP` instance for type `totp`, an `HOTP` instance for type `hotp`; the returned helper offers every method listed above for its class.
- Refused parse: raises, or returns something that is not an `HOTP`/`TOTP` instance (for example `None`).

## otpauth URI form

Built and parsed URIs have the form

```
otpauth://<type>/<label>?<key>=<value>&<key>=<value>...
```

- `<type>`: `totp` or `hotp`.
- `<label>`: `<account>` or `<issuer>:<account>`, each part percent-encoded; the separating colon is literal.
- `<key>` names written by the builder: `secret`, `issuer`, `counter`, `algorithm`, `digits`, `period`, then the caller's extra field names (such as `image`). `<value>` is percent-encoded text; `counter`, `digits` and `period` values are decimal integers; `algorithm` values are `SHA1`, `SHA256` or `SHA512`.
- Which keys appear, their order, and which characters are percent-encoded are product behaviour stated in the PRD (FP-04); the parser reads the same keys (FP-05).
- The placeholder account name is the text `Secret`.
