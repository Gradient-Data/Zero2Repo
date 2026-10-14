# Interface Contract

## Product overview

**oggrepack** is a command-line tool that losslessly recompresses Ogg Vorbis and Ogg Opus files. A caller compresses a seekable input to a oggrepack archive and later expands that archive. Behaviour is specified in the PRD; this document is the product's shell: how a caller invokes it and the form of everything it writes.

The finished product is one compiled **C99** executable named `oggrepack`. It uses only the C and math libraries at runtime. There is no library API, no importable package, and no wire protocol. Operands are seekable files; standard input and standard output are not compress or expand operands.

Documented execution is Linux x86_64, CPU-only. A git checkout is built with `./bootstrap`, then `./configure`, then `make`.

## Binary and invocation

The Autotools `bin_PROGRAMS` artifact is `oggrepack` at the built repository root. A caller spawns it with an argument vector, working directory, standard streams, and environment of its choice, then observes the exit status, standard output, standard error, and the files named as destinations.

```
oggrepack [<option>...] e <input> <output>
oggrepack [<option>...] d <input> <output>
oggrepack [<option>...] -b e <input>...
oggrepack [<option>...] -b d <input>...
oggrepack [<option>...] dump <archive>
oggrepack [<option>...] pages <ogg-file>
oggrepack -h | --help
oggrepack -v | --version
```

**Verbs.** Exactly `e` (compress), `d` (expand), `dump`, and `pages`, lowercase. `e` and `d` take an input path and an output path; with `-b` / `--batch` they take one or more input paths and no output operand. `dump` and `pages` take exactly one path.

**Options.** Options precede the verb.

| token | argument | meaning |
| --- | --- | --- |
| `-h`, `--help` | none | usage summary on standard output |
| `-v`, `--version` | none | identity on standard output |
| `-b`, `--batch` | none | every argument after the verb is an input path; destinations are derived |
| `-j <n>`, `--jobs <n>`, `--jobs=<n>` | `<n>`: decimal digits only | how many batch members run at once |
| `-p`, `--progress` | none | progress on standard error |
| `--progress-lines` | none | progress on standard error as separate lines |
| `--no-mmap` | none | accepted on compress and expand |
| `-1` … `-9` | none | effort on compress; effort has a default |

**Environment.**

| variable | value | meaning |
| --- | --- | --- |
| `ORP_MEMCAP` | `<mib>`: decimal digits | memory-cap override in MiB; `0` disables the cap |
| `ORP_SIMD` | `portable` or `native` | code-path override: `portable` forces the portable path, `native` forces a CPU-specific path |

There is no configuration file.

**Batch destinations.** Batch compress writes `<input>.orp` for each `<input>`. Batch expand of `<name>.orp` writes `<name>`; batch expand of an input whose name does not end in `.orp` writes `<input>.out`.

## Exit status and channels

| status | class |
| --- | --- |
| `0` | success |
| `1` | refusal: malformed, unsupported, or unrecognized input |
| `2` | usage error |
| `3` | file-access error |
| `4` | internal error |

For statuses `1`, `2`, and `3` standard error is non-empty and carries the diagnostic; the wording of every diagnostic is the implementer's choice. A file-access diagnostic contains the path that could not be opened or created. A refusal diagnostic contains the input path unless the PRD says otherwise for that refusal. A usage error writes no archive. Successful `e` and `d` put nothing required on standard output. Lines on standard error other than those this document states are free.

## Help

`-h` and `--help` exit `0` and write a usage summary on standard output. The summary contains, as whole tokens: the verbs `e`, `d`, `dump`, `pages`; the option stems `batch`, `jobs`, `progress`, `progress-lines`, `no-mmap` (with or without leading dashes); the status digits `0`, `1`, `2`, `3`, `4`. It writes the effort range on one line as `-1`, a separator of the implementer's choice, then `-9`, and it names the default effort as an effort option token `-<n>` separate from that range. Other text is free.

## Version

`-v` and `--version` exit `0` and write identity on standard output, including these lines (other lines free, any order):

```
oggrepack <release>[ <free text>]
host: <host-triple>
opus: <opus-component>
dispatch: <path>
```

- `<release>`: a release identifier containing at least one digit; dotted form not required.
- `<host-triple>`: the configure host triple of the build, `<cpu>-<vendor>-<os>`.
- The `opus:` line is present when Ogg Opus encode and decode are compiled in and absent otherwise; `<opus-component>` is free non-empty text.
- `<path>`: `portable` or `native`, naming the code path this invocation dispatched.

## Archive file

An archive is a binary file whose layout is the implementer's choice except for one field: the byte at offset 9 (counting from 0) is the format generation, an unsigned 8-bit integer from 1 through 254. Every archive this product writes carries the same generation value. When reading an archive (`d`, `dump`), the product checks this byte before any other validation of the archive beyond the bytes at offsets 0 through 8; an archive whose generation byte is not this product's is refused as a foreign generation (PRD FP-05).

## `dump`

On success `dump` exits `0` and writes on standard output these two lines (leading whitespace allowed, any order):

```
stage: <stage>
codec: <codec>
```

where `<stage>` is the decimal encoding stage stored in the archive and `<codec>` is `opus` for an archive made from Ogg Opus and `vorbis` for an archive made from Ogg Vorbis. Other lines are free and contain no line of either form.

## `pages`

On success `pages` exits `0` and writes on standard output one line per Ogg page, in file order:

```
<indent>page <index> <free columns> <status>
```

- `<indent>`: zero or more spaces; `<index>`: decimal page index counting from 0.
- `<status>`, last on the line: `ok` when the page reconstructs as FP-09 defines, `mismatch` when it does not.

Other lines are free and contain no line of the page form.

## Batch summary

In batch, the first occurrence of a member's input path on standard error is in that member's own diagnostic or progress output; no earlier line names it.

When at least one batch member does not succeed, standard error carries one line ending in

```
batch failed: <failed>/<attempted>
```

where `<failed>` is the decimal count of members that did not succeed and `<attempted>` the decimal count of input paths. A batch in which every member succeeds writes no such line.

## Progress

Progress goes to standard error. A progress update that reports completion contains the literal `100%` exactly once; no other progress text contains `100%`. With `--progress-lines`, and in batch whenever progress is on, each update is one line terminated by `\n` that contains no carriage return and contains the name of the file it reports on. Other progress text, and the separators of `-p` / `--progress` updates in single-file mode, are free.
