# oggrepack — Full Product Requirements Document

## Product overview

**oggrepack** is a command-line tool that losslessly recompresses Ogg Vorbis and Ogg Opus files. A caller compresses a seekable input to a oggrepack archive and later expands that archive; the expanded file is byte-identical to the original. The product detects the codec from the input. Archives are typically smaller than the source `.ogg` or `.opus` file; the typical percentage is not specified. What is required is a minimum (FP-04): at effort 9 the archive of an ordinary file is smaller than that file, and at no effort does an archive carry the file's audio packets as stored copies.

The first-time path is: invoke oggrepack with the compress verb, an Ogg Vorbis or Ogg Opus file, and a destination path; then invoke it with the expand verb on that archive and a destination path; the recovered bytes equal the original. Batch mode processes many paths in one invocation. Optional progress writes to standard error. Releases are not backwards or forwards compatible until v2.0; expanding an archive whose format generation is not the one this product writes is refused.

This document specifies **user-observable behavior only**. The exact spellings of verbs, options, environment variables and output forms are in the Interface Contract; internal construction is out of scope. Every feature point corresponds to behavior that exists in the finished product. Feature points are ordered so foundational capabilities come first; a later feature point may refine an earlier one only when it says so explicitly.

## Terminology

| Term | Meaning in this PRD |
| --- | --- |
| **oggrepack** | The product: a command-line lossless recompressor for Ogg Vorbis and Ogg Opus. |
| **Compress** | The `e` verb: read a seekable Ogg Vorbis or Ogg Opus file and write a oggrepack archive. |
| **Expand** | The `d` verb: read a oggrepack archive and write the original Ogg bytes. |
| **Archive** | The file oggrepack writes on compress and reads on expand. On Unix and Linux, batch compress names it by appending `.orp` to the input path. |
| **Ogg Vorbis file** | A seekable Ogg bitstream whose first page carries a Vorbis identification header as defined by the Vorbis I specification. |
| **Ogg Opus file** | A seekable Ogg bitstream whose first page carries an OpusHead identification header as defined by RFC 7845. |
| **Link** | One logical bitstream in a chained Ogg file, beginning at a beginning-of-stream page and ending at the corresponding end-of-stream page (or at end of file when the final end-of-stream flag is absent but the last packet is complete — FP-06). |
| **Effort** | An integer from 1 through 9 selected with `-1` … `-9`. Higher values spend more encoder work. The default is 9. |
| **Batch** | The `-b` / `--batch` mode: every remaining argument after the verb is an input path; destinations are derived. |
| **Refusal** | Compress or expand does not succeed. The process exits with status 1 (unless a higher status from FP-01 applies). A diagnostic is written to standard error. No usable destination is delivered for that input. |
| **Usage error** | The command line cannot be interpreted. Exit status 2. No archive is written. |
| **File-access error** | A named path cannot be opened, read, or written, or the input and output name the same file. Exit status 3. |
| **Completion indication** | A progress update reporting that an operation reached 100%. |
| **Progress run** | Progress output up to and including one completion indication. |

## Public surface inventory

oggrepack is a **command-line program**. It is C99, uses only the C and math libraries at runtime, and is invoked as `oggrepack` with a verb and paths. There is no library API in this product’s public contract.

Its capabilities are:

- The program itself: help, version, verbs, options, environment overrides, and the five exit-status classes (FP-01).
- Compress and expand of Ogg Vorbis, including legal packet variations, comments, and determinism (FP-02).
- Compress and expand of Ogg Opus, including family-0 mono and stereo, extended frame headers, RFC 6716 padding, comments, and the packet-size caps (FP-03).
- Effort `-1` through `-9`, default `-9` (FP-04).
- Refusal of files that cannot be reproduced exactly, wrong-type inputs, and foreign archive generations (FP-05).
- Chained bitstreams, and Vorbis files that omit a final end-of-stream flag when they end on a complete packet (FP-06).
- Batch processing with derived names, larger inputs first, continuation after a refusal, and `--jobs` (FP-07).
- Opt-in progress on standard error (FP-08).
- The `dump` and `pages` inspection verbs (FP-09).

Build, packaging, sanitizer and SIMD configure switches, Windows, Windows 95, and MS-DOS ports, and fuzzing are not feature points. They are not part of the product a first-time user must have.

## Non-functional constraints

- **Form factor:** A C99 command-line tool. No GPU, no accelerator, no runtime third-party libraries beyond the C and math libraries.
- **Host:** Linux x86_64. The program builds from this repository (`./configure` then `make`; a git checkout runs `./bootstrap` first) and runs on seekable files.
- **Hardware:** CPU-only.
- **I/O:** Input and output must be seekable files. Standard input / standard output pipes are not a supported compress or expand path.
- **Memory:** Supported hosts apply a per-process memory cap to reject unreasonable allocations. The environment variable `ORP_MEMCAP` overrides that cap in MiB; `0` disables it. A non-empty value that is not a non-negative integer is a usage error on every invocation, including version (FP-01). Sanitizer builds omit the cap. The numeric default when the variable is unset, whether a particular huge allocation is actually aborted, and the effect of a well-formed numeric override on allocations are host- and build-dependent and are not specified.
- **Code path:** The product may carry CPU-specific code paths beside its portable one. The optional override `ORP_SIMD` forces either the portable path or a CPU-specific path; without it the implementer chooses. Forcing the portable path is always accepted. Forcing a CPU-specific path when this build has none usable on this CPU and OS, or giving any other value, is a usage error on every invocation, including version. Which path was dispatched is reported by version (FP-01). Archives are bit-identical, and expands lossless, whichever path ran, for either codec and at any effort.
- **Mapping:** `--no-mmap` is accepted on compress and expand. Compress with and without that option on the same input and effort writes byte-identical archives, for either codec and at any effort. How the option is implemented is out of scope.
- **Portability of archives:** An archive written on one supported host expands on another supported host of this same product generation. Expand needs nothing but the archive: once compress has finished, the archive expands to the original bytes even after the original input and every other file, process, or shared-memory object that compress left on the host are gone, and whatever the archive's name, the working directory and the home directory (FP-02, FP-03).
- **Typical size:** not specified. The size requirements are in FP-04.
- **License:** GNU GPL version 3. Not a runtime behavior.

## Required substance (global)

Every feature point is delivered by the `oggrepack` binary on real files: compress recompresses the input's own packets and framing, and expand restores the original file byte for byte.

## Non-goals

- Lossy transcoding, sample-accurate decode-and-re-encode that changes Ogg framing, or any expand that is not byte-identical to the original file.
- Ogg codecs other than Vorbis and Opus (Theora, Speex, Opus with channel mapping family other than 0, Vorbis floor type 0, codebook lookup type 2).
- Reading or writing non-seekable streams as the compress or expand operands.
- Backwards or forwards compatibility with archives from a different oggrepack generation before v2.0.
- Guaranteeing a particular wall-clock speed. Speed relationships across efforts are the implementer’s.
- Windows Unicode paths, Windows 95, MS-DOS 8.3 names, and the DOS batch rule that expands Opus to `.opu` are out of scope. The product targets Linux.
- Build-time sanitizers, SIMD configure switches, and fuzzing.

---

## Feature points

### FP-01: Command invocation, verbs, help, version, and exit status

**Public entry:** The `oggrepack` program. The caller supplies options, then a verb, then the paths that verb requires. Verbs are exactly: `e` (compress), `d` (expand), `dump` (FP-09), and `pages` (FP-09). Options that this feature point itself interprets are help (`-h` / `--help`), version (`-v` / `--version`), and unknown tokens. Compress, expand, batch, progress, effort, and inspection behavior are specified in later feature points; this feature point is how a caller reaches them and how the process reports success or failure.

**Normal behavior:**

- Help writes a usage summary to standard output and exits 0. The summary names the four verbs, the effort range `-1` … `-9` and the default effort, batch, jobs, progress, progress-lines, and the no-mmap option. It also names the five exit-status classes below.
- Version writes identity to standard output and exits 0. The identity names the product, its release, the build host (the configure host triple the program was built for), whether the portable or a CPU-specific code path was dispatched, and whether Ogg Opus encode and decode are compiled into this binary. Help and version output differ.
- Compress with a valid Ogg Vorbis or Ogg Opus input and a distinct destination path exits 0 and writes that destination (FP-02, FP-03). Expand with a valid archive from this product generation and a distinct destination path exits 0 and writes the original bytes.
- The five exit-status classes are: **0** success; **1** malformed, unsupported, or unrecognized input (a refusal); **2** usage error; **3** file-access error; **4** internal error. Status 4 is reserved for product bugs; no caller input is required to produce it.
- Diagnostics for refusal, usage error, and file-access error go to standard error. Successful compress and expand have no required standard output.

**Boundary / error behavior:**

- No arguments is a usage error (exit 2). An unknown verb is a usage error. An unknown option is a usage error.
- Compress without both an input path and an output path is a usage error. Expand without both paths is a usage error. `dump` and `pages` without exactly one path are usage errors. Batch without at least one file path after a compress or expand verb, and batch combined with any verb other than compress or expand, are usage errors (FP-07).
- `--jobs` requires a positive decimal integer with no sign and no trailing text; any other value is a usage error.
- A missing input path, a missing directory on the output path, an input that cannot be opened, or a non-seekable operand is a file-access error (exit 3). Its diagnostic names the path. A well-formed command aimed at a file that is not there is 3, not 1.
- If the input path and the output path name the same file, whether by the same path string or by two paths that resolve to the same existing file, compress and expand are file-access errors and leave the input bytes unchanged.
- Malformed `ORP_MEMCAP` and illegal or unavailable `ORP_SIMD` overrides are usage errors on every verb and on version (Non-functional constraints).

---

### FP-02: Lossless Ogg Vorbis compress and expand

**Public entry:** `oggrepack e` with a seekable Ogg Vorbis input and a distinct output path; `oggrepack d` with a oggrepack archive produced from that input and a distinct output path. Codec detection for compress uses the first Ogg page. Expand detects a Vorbis archive from the archive itself, never from the file name. Effort (FP-04), refusals (FP-05), chaining (FP-06), batch (FP-07), and progress (FP-08) refine this path; this feature point is the single-file lossless round-trip.

**Normal behavior:**

- Compress of a valid Ogg Vorbis file writes an archive and exits 0. The archive is not a copy of the input. Expand of that archive writes a file whose bytes are identical to the original input, and exits 0.
- Compress detects Vorbis from the first page of the input: the page is an Ogg page as defined by RFC 3533, and its first complete packet is a Vorbis identification header as defined by the Vorbis I specification. A file whose first page is OpusHead takes the Opus path (FP-03), not this one. File names and suffixes play no part in detection.
- The round-trip is **byte-identical**, including Ogg page framing, checksums, granule positions, serial numbers, packet contents, comment packets, and any padding bits that were in the original packets.
- The same input, same effort, and same options, compressed twice (in separate invocations, and with or without `--no-mmap`), produce byte-identical archives.
- Every legal Vorbis audio packet encoding round-trips, wherever the packet sits in the stream: packets that carry extra padding beyond the coded payload, packets that are shorter than a canonical encoding of the same symbols, and packets that use any legal floor subclass choice.
- Comment packets of any legal size and content are part of the original bytes and therefore part of the round-trip.
- Expand needs only the archive (Non-functional constraints, Portability of archives).
- Size requirements are in FP-04.

**Boundary / error behavior:**

- A file that is not Ogg, or whose first page is not a Vorbis identification header and not OpusHead, is refused (FP-05). Expand of an Ogg file is refused: expand requires a oggrepack archive.
- Compress of a oggrepack archive is refused: compress requires an Ogg Vorbis or Ogg Opus file.
- Vorbis floor type 0 and codebook lookup type 2, as defined by the Vorbis I specification, are unsupported: such a file is refused.
- Input and output must be seekable. A non-seekable operand fails as a file-access error rather than a silent truncation.
- Overwrite of the input through the output path is a file-access error (FP-01).

---

### FP-03: Lossless Ogg Opus compress and expand

**Public entry:** The same compress and expand verbs as FP-02, when the input is Ogg Opus. Compress detects Opus from the first Ogg page’s OpusHead packet as defined by RFC 7845. Expand detects an Opus archive from the archive itself.

**Normal behavior:**

- Compress of a valid Ogg Opus file that this product supports writes an archive and exits 0. Expand of that archive writes a file byte-identical to the original input and exits 0.
- Supported streams are logical bitstreams with **channel mapping family 0** and **one or two channels** (mono or stereo), as those terms are used in RFC 7845. SILK, CELT, and hybrid packets that appear in such a stream are all in scope.
- Audio packets and the OpusHead packet are limited to **61,440 bytes**, the maximum Opus packet size in RFC 7845 section 6; a packet of exactly that size is accepted. OpusTags comment packets may be up to **120 MiB** and are still part of the byte-identical round-trip.
- Extended Opus frame headers and padding on any audio packet, including RFC 6716 code-3 padding within the 61,440-byte packet limit, still compress and expand to the original bytes.
- The same input compressed twice at the same effort, in separate invocations and with or without `--no-mmap`, produces byte-identical archives.
- Expand needs only the archive, as for Vorbis.
- Whether an archive was made from Ogg Opus is reported by `dump` (FP-09).

**Boundary / error behavior:**

- Channel mapping family other than 0 is refused. Channel count other than 1 or 2 under family 0 is refused. These checks apply to every link of the input. The diagnostic of a mapping-family refusal states the rejected family value as a decimal number; the diagnostic of a channel-count refusal states the rejected channel count as a decimal number.
- An Opus audio or OpusHead packet larger than 61,440 bytes is refused, wherever it occurs. An OpusTags packet larger than 120 MiB is refused.
- A nonzero Ogg version on any page (RFC 3533 version field) is refused.
- Chained Ogg Opus is supported (FP-06). That later feature point is the chained case; this feature point is a single logical stream.
- Expand selects the codec from the archive. Expanding a Vorbis archive recovers Vorbis bytes (FP-02); expanding an Opus archive recovers Opus bytes, whatever the archive or destination file is named. Expand does not transcode. Expand of an Ogg Opus file is refused.

---

### FP-04: Effort selection

**Public entry:** The effort options `-1` through `-9` on a compress invocation (single-file or batch). Expand does not take an effort that changes decoded bytes: the archive already stores what expand needs. If no effort option is given, compress uses **9**.

**Normal behavior:**

- Each of `-1` through `-9` is accepted on compress. The last effort option on the command line is the one that applies when several are given. Omitting effort produces the same archive as `-9`.
- Expand of an archive produced at any effort in 1 through 9 recovers the original bytes. Whether archives produced at adjacent efforts differ in size or bytes is the implementer’s, except for the collection totals below. Speed at any effort is the implementer’s.
- Over any collection of ordinary valid Ogg Vorbis files this product accepts, the **total** size of the archives produced at effort 9 is **strictly smaller** than the total size of the archives produced at effort 1, whenever the collection has enough audio for the totals to differ.
- Over any collection of valid family-0 Ogg Opus files this product accepts, the total size of the archives produced at effort 9 is **less than or equal to** the total size produced at effort 1.
- At effort 9, compress of an ordinary accepted file writes an archive strictly smaller than that file. An ordinary file here is a single-link Ogg Vorbis file, or a single-link family-0 mono or stereo Ogg Opus file, carrying encoder-produced audio: identification, comment, and (for Vorbis) setup headers, then audio packets without added padding, ending on an end-of-stream page; how packets are laid out on valid pages, and the comment text, may be anything valid.
- At every effort, the archive is a recompression, not a stored copy: it does not contain most of the input's audio data verbatim (audio packets shorter than 16 bytes are left out of that rule).

**Boundary / error behavior:**

- There is no effort 0 and no effort 10. Those tokens are not effort options; `-0` is an unknown option (usage error, FP-01).
- An effort option given with expand is accepted and does not change the recovered bytes.

---

### FP-05: Exact-reproduction refusals

**Public entry:** Compress (`e`) or expand (`d`) on a file that this product will not reproduce exactly, on a file of the wrong type for the verb, or on an archive whose format generation is not this product’s. Batch (FP-07) uses the same per-file refusal and continues with other files.

**Normal behavior:**

- Every accepted compress is a promise that expand will restore the original bytes. If the product cannot keep that promise for a given input, it refuses rather than writing an archive that would expand incorrectly.
- A refusal exits 1 for a single-file invocation, writes a diagnostic to standard error, and does not leave a successful archive at the destination as the outcome of that file. The diagnostic identifies the offending input. Compress of a file that is not Ogg Vorbis or Ogg Opus (including an Ogg file whose first page carries neither identification header, and a oggrepack archive) and compress of an Ogg Vorbis file with a page whose checksum does not match name the input path. Every other refusal names either the input path or the refused construct, at the implementer's choice. A destination path may exist as a partial write; it must not expand to a file the caller could mistake for a successful round-trip of that input.
- A page whose stored checksum does not match the CRC-32 that RFC 3533 defines for that page (computed over the page bytes with the checksum field treated as zero) is refused, on any page and for either codec.
- On compress of an Ogg Vorbis file, a page that follows a finished end-of-stream page of the same logical stream with no new beginning-of-stream, and a packet that continues onto a following page that is not marked as a continuation, are each refused. On compress of a supported family-0 Ogg Opus file, those same two framings are accepted, and expand of that archive restores the original bytes. Trailing bytes after the last Ogg page that are not a following chained link are refused on both codecs.
- Unsupported Vorbis features are refused, including floor type 0 and codebook lookup type 2 as defined by the Vorbis I specification, and any codebook that cannot be reproduced exactly.
- Unsupported Opus mapping and packet limits are refused as in FP-03.
- Expand of a file that is not a oggrepack archive of this product generation is refused. Compress of a file that is not Ogg Vorbis or Ogg Opus is refused. The diagnostics of these two wrong-type refusals are worded differently from each other: they differ in more than the paths they name.
- Each archive records the format generation that wrote it, and every archive this product writes records the same generation whatever the input, codec, or effort. Expand of an archive whose recorded generation is not this product’s, whether lower or higher, is refused (exit 1), and its diagnostic states the generation value the archive carries as a decimal number. The generation is examined before anything else in the archive's contents, so such an archive is refused for its generation even when nothing else about it would be accepted.

**Boundary / error behavior:**

- A truncated archive either refuses (exit 1) or, if it exits 0, writes a destination that matches the original source of that archive. It must not crash. An archive whose interior bytes are altered exits 0 or 1 and must not crash; undetectable interior damage may exit 0 with a destination that does not match the original. Exit 4 or a crash is never the outcome of damaged caller input.
- Vorbis files that omit the final end-of-stream flag but end on a complete packet are **accepted** (FP-06), not refused.
- Vorbis audio packets with extra padding that is a legal packet ending are **accepted** (FP-02), not refused.
- An incomplete final packet (the input ends in the middle of a packet) is refused on compress of either codec, in any link.
- A missing file is a file-access error (exit 3), not a refusal (exit 1).

---

### FP-06: Chained bitstreams and Vorbis files without a final end-of-stream flag

**Public entry:** Compress and expand (FP-02, FP-03) when the input is a chained Ogg file, or a Vorbis file whose last page does not have the end-of-stream flag set. This feature point changes the set of inputs FP-02 and FP-03 accept; it does not change the byte-identical expand contract.

**Normal behavior:**

- A chained Ogg Vorbis file (two or more links, each a Vorbis logical stream) compresses and expands to the original bytes. Links may differ in length and content. A later link may replay headers that already appeared; the original framing is still restored.
- A chained Ogg Opus file whose every link is a supported family-0 mono or stereo stream compresses and expands to the original bytes. Links may differ in mode (SILK, CELT, hybrid), channel count (mono or stereo), and identification-header fields, as long as each link stays on family 0 with one or two channels. Whether a chained archive is smaller than encoding the parts separately is not specified.
- In any link of a Vorbis file, the comment and setup header packets may share a page with that link's audio packets.
- A Vorbis stream, single or chained, that is otherwise valid, ends on a complete packet, and lacks the end-of-stream flag on its last page, compresses and expands to those original bytes, whatever precedes it in the file.
- Compress and expand of a chain write a destination that is not a copy of the source.

**Boundary / error behavior:**

- A page that belongs to a stream that has already ended (a page after end-of-stream for that stream, without a new beginning-of-stream) is refused on an Ogg Vorbis file and accepted on a supported family-0 Ogg Opus file (FP-05).
- An Opus chain that includes a link with channel mapping family other than 0, or with a channel count other than 1 or 2, is refused, whichever link it is.
- An incomplete final packet is refused (FP-05).

---

### FP-07: Batch compress and expand

**Public entry:** `oggrepack -b` / `--batch` followed by `e` or `d` and one or more input paths. Optional `--jobs=N` (or `-j N`) is accepted. Effort, progress, and no-mmap apply to the whole batch.

**Normal behavior:**

- Every remaining path after the verb is an input. There is no separate output operand.
- On Linux and other Unix hosts, batch compress writes, beside each input, a destination whose name is the input path with `.orp` appended. Batch expand strips a trailing `.orp` to recover the original path; if the input name has no `.orp` suffix, expand appends `.out`.
- Each file is processed as a single-file compress or expand (FP-02, FP-03) with the same effort and options, whichever codec each member uses. Success for a file means that file’s destination exists and, for expand, matches the original source; for compress, a later expand of that destination matches the original source, and the archive equals the one single-file compress writes.
- Larger inputs start first: members are started in decreasing order of input size. With one job, each member runs to completion, diagnostics included, before the next smaller member starts.
- After a refusal or a file-access error on one file, remaining files still run. The process exit status is the **highest** nonzero status reported by any file (1, 2, 3, or 4 as in FP-01). If at least one file was refused and no higher status occurred, the status is 1.
- When at least one member does not succeed, standard error carries a batch summary giving the number of members that did not succeed and the number of input paths given. A batch in which every member succeeds carries no summary. Successful members of a batch with failures still have valid destinations.
- Without `--jobs`, the program chooses a positive job count. That automatic count, and how many files overlap in time, are the implementer's. With `--jobs=N`, N must be a positive integer (FP-01).
- Batch progress uses separate lines labeled with the member's file name (FP-08).

**Boundary / error behavior:**

- Batch with no file paths, or with a verb other than `e` or `d`, is a usage error, also when that verb is not a known verb.
- `--jobs=0` and non-integer job counts are usage errors (FP-01).
- A missing path in a batch of otherwise valid files yields exit 3 (file-access) if that is the highest status, and the valid files still encode or expand.
- DOS replacement of the extension and `.opu` for expanded Opus is not a Linux obligation.

---

### FP-08: Opt-in progress on standard error

**Public entry:** `-p` / `--progress` and `--progress-lines` on compress, expand, or batch. Progress is off by default.

**Normal behavior:**

- With progress off, compress and expand of a valid file write no progress to standard error. A successful run may be silent on standard error.
- With `-p`, `--progress`, or `--progress-lines` on a single-file compress or expand of a valid file, standard error carries progress for that operation, ending in at least one completion indication; this holds for both codecs.
- `--progress-lines` turns progress on by itself and writes each update as a separate line suitable for a log; a run of a valid file writes more than one such line. Batch mode always uses line-oriented progress when progress is on, and labels each line with the name of the member it reports on, for compress and for expand.
- Enabling progress does not change archive bytes: compress with progress and compress without progress on the same input and effort write identical archives, at every effort, for both codecs, for every progress option, and for batch compress. Expand with progress still recovers the original bytes.

**Boundary / error behavior:**

- Progress is opt-in. Absence of the option is not a failure.
- A refusal with progress on still writes the refusal diagnostic (FP-05) to standard error, exits 1, and delivers no usable destination. Progress being on does not change that status or hide the diagnostic.

---

### FP-09: Archive dump and Ogg page listing

**Public entry:** `oggrepack dump` with one archive path; `oggrepack pages` with one Ogg file path.

**Normal behavior:**

- `dump` on a valid archive written by this product exits 0 and writes a layout description to standard output. It reports whether the archive was made from Ogg Opus or Ogg Vorbis; that report depends only on the codec, never on the content, size, or name of the file. It reports the encoding stage stored in the archive, which depends only on the effort the archive was made at, never on the input.
- `pages` on a valid Ogg Vorbis or Ogg Opus file exits 0 and lists every page of the file, in order, whatever the file is named. For each page it reports whether the page reconstructs: a page reconstructs when its stored bytes equal the RFC 3533 serialization of its parsed header fields and body, with the CRC-32 recomputed over the page with the checksum field treated as zero. Every page of a well-formed file reconstructs. A page whose stored checksum does not match does not reconstruct; listing continues past it and still exits 0 as long as the file still parses as Ogg pages.
- `pages` does not modify the file.

**Boundary / error behavior:**

- `dump` on a missing path is a file-access error (exit 3). `pages` on a missing path is a file-access error.
- `pages` on a file that is not Ogg, including an archive of this product, is refused (exit 1). `dump` on a file that is not a oggrepack archive of this generation, including an Ogg file and an archive whose recorded generation is not this product's, is refused.
- Extra operands beyond one path are usage errors (FP-01).
