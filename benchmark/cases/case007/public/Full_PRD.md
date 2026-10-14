# Otpkit — Full Product Requirements Document

## Product overview

**Otpkit** is a Python library for generating and verifying one-time passwords. It is used to implement two-factor (2FA) or multi-factor (MFA) authentication in web applications and in other systems that require users to log in.

Open MFA standards are defined in RFC 4226 (HOTP: An HMAC-Based One-Time Password Algorithm) and RFC 6238 (TOTP: Time-Based One-Time Password Algorithm). Otpkit implements server-side support for both of these standards. Client-side support can be enabled by sending authentication codes to users over SMS or email (HOTP) or, for TOTP, by instructing users to use Google Authenticator, Authy, or another compatible app. Users can set up auth tokens in their apps by scanning otpauth URIs that Otpkit provides (typically rendered as QR codes by the integrator).

A first-time integrator generates a random shared secret, constructs a time-based helper with that secret, reads the code for the current clock, and checks a candidate code the user typed. The same secret can instead drive an HMAC-based helper whose codes are indexed by a counter the application stores. Either helper can emit an otpauth URI so a phone app can be provisioned; Otpkit can also parse such a URI back into a helper that produces the same codes.

This document specifies **user- and integrator-observable behavior only**. Exact published symbol names, import paths, and call spellings belong in the Interface Contract, not here. Every feature point below corresponds to behavior that exists in the finished Otpkit product. Feature points are ordered so foundational capabilities come first; a later feature point may depend on an earlier one, never the reverse.

The security checklist in the project README (HTTPS, secret storage, replay denial in the application database, brute-force throttling, and considering FIDO U2F / WebAuthn for new applications) is **integrator guidance**, not a library obligation. Otpkit generates and verifies codes; it does not store used codes, rate-limit logins, or render QR images.

## Terminology

| Term | Meaning in this PRD |
| --- | --- |
| **Shared secret** | The key stored on both the server and the client. Helpers consume it as base32 text (RFC 4648 base32 alphabet). Missing base32 padding is accepted. Letter case in the secret does not matter. |
| **One-time password / code** | The short value a helper emits or checks. A successful generation returns a **text string** of decimal digits. The string is exactly as wide as the configured digit count; leading zeros are kept. A code is never returned as a bare integer. |
| **HMAC-based helper (HOTP)** | A helper whose codes are indexed by a counter the caller supplies. Specified in FP-02. |
| **Time-based helper (TOTP)** | A helper whose codes are indexed by the current time, divided into fixed-length steps. Specified in FP-03. |
| **Digit count** | How many characters each code contains. The product default is 6. Construction refuses a count greater than 10. An otpauth URI may carry only 6, 7, or 8. |
| **Digest** | The hash function used inside HMAC. The product default is SHA1. SHA256 and SHA512 are also supported. A digest whose output is shorter than 18 bytes, or whose output length is chosen by the caller rather than fixed, is refused. |
| **Starting counter** | For an HMAC-based helper, the counter value that relative count zero maps to. The product default is 0. The code for relative count N is the code for counter (starting counter + N). |
| **Time-step length** | For a time-based helper, how many seconds a code remains the current code. The product default is 30. |
| **Time-step number** | The instant's Unix time in whole seconds (any fraction of a second discarded toward zero), divided by the time-step length, with the quotient truncated toward zero (not floored). The Unix time of a timezone-aware datetime is taken in UTC; that of a timezone-naive datetime is taken in the host local timezone. |
| **Acceptance window** | How many time steps on either side of a target instant a time-based check will still accept. Zero means only the target step. |
| **Compatibility-equivalent** | Two texts are compatibility-equivalent when their Unicode NFKC normalisations are identical. |
| **Account name** | The account label stored on a helper and written into an otpauth URI path. When the caller never supplies one (or supplies an empty one), the product uses the placeholder Secret. |
| **Issuer** | The organization title stored on a helper and written into an otpauth URI (path prefix and query field). |
| **otpauth URI** | A provisioning URI whose scheme is otpauth, whose type is totp or hotp, and whose query carries at least the shared secret. Specified in FP-04 and FP-05. Compatible with the Google Authenticator Key URI Format. |
| **Percent-encoding** | RFC 3986 percent-encoding of the UTF-8 bytes of a text, with uppercase hexadecimal digits. Which characters are left as they are is stated wherever the encoding is used (FP-04). |

## Public surface inventory

Otpkit is a **library**, not a command users type. Integrators install the package and construct helpers in Python. There is no command-line product, no HTTP server, and no QR-code renderer.

The public surfaces, grouped by feature point, are:

- Random shared-secret generation as a base32 string or as a hex string, with a 160-bit minimum (FP-01).
- HMAC-based codes: emit the code for a counter, and accept or reject a candidate at a counter, as defined by RFC 4226 (FP-02).
- Time-based codes: emit the code for the current clock or for a given instant, accept or reject a candidate with an optional acceptance window, and report the matching time-step number, as defined by RFC 6238 (FP-03).
- Build an otpauth URI from an HMAC-based or time-based helper so a compatible app can be provisioned (FP-04).
- Parse an otpauth URI back into a helper that produces the same codes and can rebuild an equivalent URI (FP-05).

Feature points below group these entries by capability. They do not invent additional product surfaces.

## Non-functional constraints

- **Form factor:** A pure-Python library. No compiled extensions, native code, GPU, or accelerator are required or claimed. Zero declared runtime dependencies.
- **Language:** Python 3.8 or newer, including the CPython and PyPy implementations the project supports.
- **Platforms:** Intended to work on Linux, macOS, and Windows. Linux with a supported interpreter is the reference platform.
- **Hardware:** CPU-only. The library runs on a real host able to import the installed package and run Python. There is no accelerator profile.
- **Code representation:** Generated codes are text strings of the configured width.
- **Secret representation:** Helpers take the shared secret as base32 text. A secret whose length is not a multiple of eight is accepted; the missing padding is supplied by the library. Hex secrets produced by FP-01 are for applications that want a hex-encoded key; the HOTP and TOTP helpers still consume base32.
- **Default digit count:** 6.
- **Default digest:** SHA1.
- **Default time-step length:** 30 seconds.
- **Default HMAC starting counter:** 0.
- **URI type set (finite):** totp and hotp. No other otpauth type is accepted.
- **URI algorithm set (finite):** SHA1, SHA256, SHA512.
- **URI digit-count set (finite):** 6, 7, and 8.
- **Versioning:** The package follows Semantic Versioning 2.0.0. That policy is background; it is not a runtime obligation.

## Required substance (global)

Every code Otpkit emits or accepts is computed from the shared secret and the counter or time-step number by the HMAC procedure of RFC 4226 (and RFC 6238 for time-based codes). Every URI Otpkit builds is otpauth text built from the helper's state (FP-04), and every parse follows the FP-05 rules.

## Non-goals

- Rendering QR codes, sending SMS or email, or shipping a phone client. Otpkit emits codes and otpauth URIs; the integrator renders and delivers them.
- Storing used codes, timestamps, or hashes in a database in order to deny replay. The README tells application authors to do that. The library check of a candidate does not consume the code: checking the same valid candidate twice at the same counter or the same instant succeeds both times. A time-based helper can report the matching time-step number (FP-03) so the application can refuse a repeated step; the library itself does not remember previous successes.
- Transport confidentiality, rate limiting, or secret-at-rest storage. Those are application obligations listed in the README checklist.
- FIDO U2F, WebAuthn, or the sister project Warpkit. The README recommends them for new applications; they are not this product.
- Steam TOTP. A third-party contribution exists that emits five-character Steam codes. It is not described by a standard, is not officially supported, and is provided for reference only. It is **not** a core capability of this product.
- A command-line program, HTTP server, or authentication framework.
- The RFC 4226 and RFC 6238 recommendations beyond computing and checking codes: look-ahead counter resynchronization, throttling, a time origin other than Unix time 0, and clock-drift compensation other than the caller-chosen acceptance window.
- Guaranteeing a particular code-generation throughput.
- Treating packaging scripts, the Makefile, or the project's own development tooling as product capabilities.

---

## Feature points

### FP-01: Random shared-secret generation

**Public entry:** Otpkit’s random-secret helpers. One helper emits a base32 secret compatible with Google Authenticator and other OTP apps. The other emits a hex-encoded secret for applications that want that format. Neither helper constructs an HMAC-based or time-based generator; FP-02 and FP-03 consume a secret the caller already has.

**Normal behavior:**

- A base32 secret uses only the characters `A` through `Z` and `2` through `7`. With no length override its length is 32.
- A hex secret uses only the characters `A` through `F` and `0` through `9` (uppercase letters only). With no length override its length is 40.
- The caller may request a length. Any requested length at or above the minimum (32 for base32, 40 for hex, i.e. 160 bits) succeeds and returns a string of exactly that length from the same alphabet.
- Each generation draws a new string at random from the stated alphabet (a cryptographically suitable random source).

**Boundary / error behavior:**

- A requested length below the minimum (below 32 for base32, below 40 for hex) does not succeed. The caller observes a failure, and no secret is returned.

---

### FP-02: HMAC-based one-time passwords (HOTP)

**Public entry:** Otpkit’s HMAC-based helper, constructed with a shared secret in base32. The caller may also supply a digit count, a digest, an account name, an issuer, and a starting counter. This helper emits and checks codes indexed by a counter. It does not consult the clock (FP-03) and does not build or parse otpauth URIs (FP-04, FP-05).

**Normal behavior:**

- The code at relative count N is the HOTP value defined by RFC 4226 for the key (the base32-decoded secret) and the counter (starting counter + N), with the configured digest in place of SHA-1 and the configured digit count: the truncated value modulo 10 to the power of the digit count, written in decimal and left-padded with zeros to exactly the digit count.
- The secret is decoded as RFC 4648 base32 without regard to letter case; when its length is not a multiple of eight, the missing `=` padding is supplied. A lowercase secret produces the same codes as the same secret in uppercase, and an unpadded secret the same codes as its padded spelling.
- The default digit count is 6 and the default digest is SHA1. An explicit SHA1 digest, an explicit digit count of 6, or an explicit starting counter of 0 produces the same codes as leaving that option at the default. Digit counts from 1 to 10 are accepted.
- Changing the starting counter shifts the codes: relative count N on a helper whose starting counter is K yields the same code as relative count K + N on a helper whose starting counter is 0.
- The account name and the issuer do not change the codes.
- Checking a candidate at a relative count succeeds exactly when the candidate is compatibility-equivalent (identical after Unicode NFKC normalisation of both texts) to the code at that relative count; otherwise it fails. A check returns a negative result for a wrong candidate and does not abort the caller. A check never consumes a code: checking the same valid candidate again at the same count succeeds again, and a failed check leaves the helper emitting the same codes.
- Generated codes are text strings. They are exactly as wide as the digit count. They are not integers.

**Boundary / error behavior:**

- Asking for the code at a relative count whose counter (starting counter + N) is negative does not succeed: the caller observes a failure and no code is returned. This is distinguishable from checking a wrong candidate, which returns a negative result and does not abort the caller.
- Constructing a helper with a digit count greater than 10 does not succeed.
- Constructing a helper with a digest whose output is shorter than 18 bytes, or whose output length is chosen by the caller rather than fixed, does not succeed. SHA1, SHA256, and SHA512 are accepted.
- Checking a code that belongs to a different counter fails. The helper does not advance or store a counter of its own; the caller always supplies the counter to check against, and the process clock plays no part.

---

### FP-03: Time-based one-time passwords (TOTP)

**Public entry:** Otpkit’s time-based helper, constructed with a shared secret in base32. The caller may also supply a digit count, a digest, an account name, an issuer, and a time-step length. This helper emits and checks codes indexed by time. **This feature point uses the same construction rules as FP-02** for the secret, digit count (default 6, greater than 10 refused) and digest (default SHA1; SHA256 and SHA512 accepted; a digest with output shorter than 18 bytes or of caller-chosen length refused). Codes remain text strings of the configured width. The obligations below are the clock, the time-step, the acceptance window, and RFC 6238.

**Normal behavior:**

- The code for an instant is the RFC 6238 TOTP value with T0 = 0: the FP-02 HOTP value, under the configured digest and digit count, for the counter equal to the instant's time-step number (see Terminology: whole seconds, then division by the time-step length, each truncated toward zero). The account name and the issuer do not change the codes; an explicit time-step length of 30, digit count of 6 or SHA1 digest produces the same codes as the defaults.
- The helper accepts either a Unix timestamp (integer or real number) or a datetime as the instant to use. A timezone-aware datetime is read as UTC. A timezone-naive datetime is read in the host local timezone. A Unix timestamp, an aware datetime and a naive local datetime that denote the same absolute instant yield the same code; an aware and a naive datetime with the same civil fields denote different instants whenever the host timezone is not UTC.
- The current clock is the host wall clock, read at the moment of each current-clock generation or check; a value read earlier is not reused, and no other time source is consulted.
- Asking for the code at the current clock yields the same string as asking for the code at that same current instant supplied explicitly.
- A time-step length other than 30 changes which instants share a code: all instants with the same time-step number share one code.
- The caller may ask for the code at a given instant plus a whole-step offset k (0 when not given): that is the code for time-step number (step of the instant) + k.
- Checking a candidate at an instant with acceptance window w (default 0) succeeds exactly when the candidate is compatibility-equivalent (as in FP-02) to the code of some time-step number from (step − w) to (step + w); otherwise it fails with a negative result and does not abort the caller. With no instant supplied, the check uses the current clock. A code therefore stops being accepted with window 0 once the clock has moved into the next time step.
- The caller may ask a check to return the matching time-step number when the candidate is accepted: the time-step number whose code matched. When the candidate is not accepted within the window, the check returns a negative result and no time-step number. The library does not remember previous successes: repeating an accepted check returns the same result.
- Checks never consume a code and never change what the helper emits.

**Boundary / error behavior:**

- A code is produced only for a non-negative time-step number (after any offset), with the time-step number computed by the truncation rule in Terminology. An instant (plus offset) whose time-step number is negative does not succeed: no code is returned.
- Asking a matching-time-step check to use a negative acceptance window does not succeed: the caller observes a failure and no time-step number is returned. A window of 0 or a positive window is accepted.
- A digit count above 10 and a digest that FP-02 refuses are refused at construction, as in FP-02.
- A wrong code, a code from outside the acceptance window, or a code from a different secret fails the check. Failure of a check is a negative result, not an aborted caller, except for the negative-window case above.

---

### FP-04: otpauth provisioning URI generation

**Public entry:** The provisioning-URI builder on an HMAC-based helper (FP-02) or a time-based helper (FP-03). The caller may override the account name, the issuer, and — for an HMAC-based helper — the starting counter written into the URI. The caller may also attach extra query fields; an image field is accepted only when it is a valid https URL. This feature point emits URIs. Parsing them is FP-05.

**Normal behavior:**

- The URI is `otpauth://` + type + `/` + label + `?` + query. A time-based helper produces type totp. An HMAC-based helper produces type hotp.
- **Label.** Without an issuer, the label is the encoded account name. With an issuer, the label is the encoded issuer, a literal (unencoded) colon, and the encoded account name. In the label each part is percent-encoded with every character escaped except ASCII letters, digits, `-`, `.`, `_`, `~` and `/`.
- **Query.** The query is `key=value` pairs joined by `&`, in exactly this order: `secret` (the secret text exactly as supplied at construction, or as read from the parsed URI, without changing its case or padding); `issuer` when an issuer is present; `counter` for an HMAC-based helper — always, written as a decimal integer, including 0; `algorithm` only when the digest is not SHA1, spelled in uppercase (SHA256, SHA512); `digits` only when the digit count is not 6; `period` (time-based helper only) only when the time-step length is not 30; then each extra field in the order the caller supplied them. Every key and value is percent-encoded with every character escaped except ASCII letters, digits, `-`, `.`, `_` and `~`; a space is written `%20`, never a plus sign.
- **State and overrides.** The account name, issuer, starting counter, digit count, digest and time-step length come from the helper as constructed. A build-time account name or issuer that is supplied and non-empty replaces the stored one for that build only; an omitted or empty one leaves the stored value. A build-time starting counter, when supplied (including 0), is the counter written for that build. When no account name was ever supplied, the account name is the placeholder Secret. When no issuer is stored or supplied, the URI has no issuer anywhere.
- **Extra fields.** An extra query field whose value is text is written as described above. An image field's value must be an https URL with both a host and a path.
- Building a URI does not require a successful prior check, and no check (successful or failed) changes the helper's secret, account, issuer, or any later URI it builds.

**Boundary / error behavior:**

- An image field whose value is not an https URL with both a host and a path is refused. The build does not succeed.
- An extra query field whose value is not text is refused. The build does not succeed.

---

### FP-05: otpauth provisioning URI parsing

**Public entry:** Otpkit’s provisioning-URI parser. The caller supplies one URI string. A successful parse returns an HMAC-based helper (FP-02) or a time-based helper (FP-03) that can emit codes and can build a URI (FP-04). **This feature point is the inverse of FP-04** for well-formed otpauth URIs of type totp or hotp, except that an image query field is not recovered on rebuild.

**Normal behavior:**

- The URI type (the part after `otpauth://` and before the path) selects the helper kind: totp yields a time-based helper; hotp yields an HMAC-based helper.
- **Label.** The path after its leading `/` is split at the first literal (unencoded) colon, before any decoding: the part before it is the issuer and the part after it the account name; with no literal colon the whole path is the account name and the label carries no issuer. Each part is then percent-decoded on its own, so an encoded colon (`%3A`) belongs to the part it appears in. The path may be empty; a URI with no account name yields a helper whose account name is the placeholder Secret.
- **Query.** Pairs are split at `&` and `=` and each key and value is percent-decoded (a `+` decodes to a space). The field secret is the shared secret. The field counter becomes the HMAC starting counter, period the time-step length, digits the digit count, and algorithm the digest (SHA1, SHA256, or SHA512). An omitted field takes the construction default. When secret, counter, period, digits or algorithm appears more than once, the last occurrence takes effect. The field issuer sets the issuer. Any other field (including image, whatever its value) is accepted and ignored.
- **Issuer agreement.** Every issuer value the URI carries — the label issuer, if any, and each issuer query occurrence, in order — must equal the issuer already read; repeated equal values are accepted.
- The returned helper emits the same codes as a helper constructed directly with the same secret and options, and building a URI from it with no overrides yields the same URI a helper with that state builds under FP-04. Consequently parsing a URI built under FP-04 and rebuilding it with no overrides yields the original string, except that an image field is dropped.

**Boundary / error behavior:**

- A URI whose scheme is not otpauth is refused.
- An otpauth URI that carries no secret, or an empty secret, is refused.
- An otpauth URI whose type is neither totp nor hotp is refused.
- A digits value that is present and is not 6, 7, or 8 is refused, and a digits, period or counter value that is not an integer is refused.
- An algorithm value other than SHA1, SHA256, or SHA512 is refused.
- An issuer value that differs from the issuer already read (label or earlier query occurrence) is refused, even when a later occurrence agrees again.
- Each of those refusals is a failed parse: no helper is returned. They are distinguishable from a successful parse that then fails a later code check.
