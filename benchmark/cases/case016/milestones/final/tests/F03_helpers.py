# feature: F03
"""Observation helpers for the detector cleanup switch (FP-03).

New names for this slice only. Sealed F01/F02 helpers are imported, not copied.
"""

from __future__ import annotations

import secrets
import subprocess
import time
import unicodedata
from typing import Any, Sequence

from _harness import HarnessError, RunResult, workspace
from F01_helpers import (
    TAG_BLOCK_62,
    invisible_count_of,
    nonstandard_space_count_of,
    require_absent_finding,
    require_finding,
    require_success_report,
    scan_stdin,
    unicode_len,
)
from F02_helpers import (
    CLEANUP_FLAG,
    _stdout_is_report,
    runtime_token,
)

# Named probe identities the PRD froze (L172, L174, L187).
CELLULOSE_CLEAN = "Cellulose is dense."
PASSWORD_CLEAN = "The password field is wrong."
PASSWORD_DIRTY = "The p\u0430ssword field is wr\u043eng."
MOSKVA_LINE = "\u041c\u043e\u0441\u043a\u0432\u0430 is the capital of Russia."
FOUR_SPACE_LINE = "    indented code block"
FIGURE_40_EUR = "40\u202fEUR"
CAFE = "caf\u00e9"
NIHONGO = "\u65e5\u672c\u8a9e"

ZWSP = "\u200b"
NBSP = "\u00a0"
NNBSP = "\u202f"
IDEOGRAPHIC_SPACE = "\u3000"
WORD_JOINER = "\u2060"
BOM_CHAR = "\ufeff"
LTR_MARK = "\u200e"
STRAY_VS = "\ufe00"

# England flag: black flag + TAG g b e n g + cancel. Named England only (L175).
ENGLAND_FLAG = (
    "\U0001f3f4"
    "\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067"
    "\U000e007f"
)

# TAG payload letters that are not in the England-flag tag run.
_TAG_AFTER_FLAG = chr(0xE0041) + chr(0xE0042)

_ZIP_MAGIC = b"PK"


def cleanup_switch() -> str:
    """The cleanup switch the Contract states (``--clean``)."""
    return CLEANUP_FLAG


def tag_payload() -> str:
    """A TAG-block payload that is not the England-flag tag letters."""
    return _TAG_AFTER_FLAG


def england_flag_sequence() -> str:
    return ENGLAND_FLAG


def cellulose_probe(*, newline: bool = True, trailing: str = "   ") -> str:
    """Amended L187 Cellulose construction."""
    body = "Cellulose" + ZWSP + " is" + NBSP + "dense." + tag_payload()[0] + trailing
    return body + ("\n" if newline else "")


def dirty_visible_twin(first: str, second: str, *, newline: bool = True) -> str:
    """Same debris classes as Cellulose, different visible words."""
    body = first + ZWSP + " is" + NBSP + second + tag_payload()[0] + "   "
    return body + ("\n" if newline else "")


def cleaned_visible_twin(first: str, second: str, *, newline: bool = True) -> str:
    body = f"{first} is {second}"
    return body + ("\n" if newline else "")


def require_scrubbed_stdout(result: RunResult) -> str:
    """Cleanup success: text on stdout, not a structured report. Never a sentinel."""
    if result.returncode != 0:
        raise HarnessError(
            f"cleanup failed: exit={result.returncode} "
            f"stderr={result.stderr_text!r} stdout={result.stdout[:500]!r}"
        )
    try:
        text = result.stdout_text
    except HarnessError as exc:
        raise HarnessError(
            f"cleanup stdout is not UTF-8 text: {exc}; raw={result.stdout[:80]!r}"
        ) from exc
    if _stdout_is_report(text):
        raise HarnessError(
            "cleanup printed a structured report instead of scrubbed text; "
            f"stdout={text[:500]!r}"
        )
    return text


def scrub_stdin(text: str | bytes) -> str:
    flag = cleanup_switch()
    result = scan_stdin(text, extra_args=(flag,))
    return require_scrubbed_stdout(result)


def scrub_path(ws, relpath: str) -> RunResult:
    """Cleanup on a file path. Returns the raw RunResult (bytes visible)."""
    flag = cleanup_switch()
    dest = ws.resolve(relpath)
    result = ws.invoke([flag, str(dest)])
    if result.returncode != 0:
        raise HarnessError(
            f"cleanup path {relpath!r} failed: exit={result.returncode} "
            f"stderr={result.stderr_text!r} stdout={result.stdout[:500]!r}"
        )
    return result


def rescan_text(text: str) -> tuple[Any, dict[str, Any]]:
    result = scan_stdin(text)
    return require_success_report(result, input_chars=unicode_len(text))


def without_class(text: str, debris: Sequence[str]) -> str:
    drop = set(debris)
    return "".join(ch for ch in text if ch not in drop)


def jobless_frame(mark: str) -> str:
    """Plant *mark* between Latin letters of a runtime word."""
    word = "bridge" + secrets.token_hex(2)
    if len(word) < 4:
        word = "bridge"
    dirty_word = word[:3] + mark + word[3:]
    return f"The {dirty_word} holds the lock."


def assert_jobless_class_removed(name: str, mark: str) -> None:
    """One jobless class is gone; surviving Latin letters are the concatenation."""
    if name == "tag-block":
        frame = TAG_BLOCK_62
        debris = [ch for ch in frame if not ch.isascii()]
    else:
        frame = jobless_frame(mark)
        debris = list(mark)
    expected = without_class(frame, debris)
    baseline = scan_stdin(frame)
    b_findings, _b_m = require_success_report(baseline, input_chars=unicode_len(frame))
    require_finding(b_findings, 62)
    out = scrub_stdin(frame)
    print(f"[F03] jobless {name} out={out!r}", flush=True)
    for ch in debris:
        assert ch not in out
    assert out.rstrip("\n") == expected.rstrip("\n")
    assert latin_letters(out) == latin_run_without_class(frame, debris)
    findings, metrics = rescan_text(out)
    assert invisible_count_of(metrics) == 0
    assert nonstandard_space_count_of(metrics) == 0
    require_absent_finding(findings, 62)
    require_absent_finding(findings, 67)


def latin_run_without_class(text: str, debris: Sequence[str]) -> str:
    """Latin letters of *text* with the named debris class taken out."""
    kept = without_class(text, debris)
    return "".join(ch for ch in kept if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))


def latin_letters(text: str) -> str:
    return "".join(ch for ch in text if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))


def first_content_leading_spaces(text: str) -> int:
    for line in text.splitlines():
        if line.strip():
            n = 0
            for ch in line:
                if ch == " ":
                    n += 1
                else:
                    break
            return n
    raise HarnessError(f"no content line to measure indentation: {text!r}")


def gap_between(text: str, left: str, right: str) -> str:
    """The span of *text* that sits between *left* and the later *right*.

    Missing endpoints are a failed observation, not an empty gap.
    """
    i = text.find(left)
    if i < 0:
        raise HarnessError(f"{left!r} missing from cleaned stdout: {text!r}")
    j = text.find(right, i + len(left))
    if j < 0:
        raise HarnessError(
            f"{right!r} missing after {left!r} in cleaned stdout: {text!r}"
        )
    return text[i + len(left) : j]


def assert_operand_unchanged(
    ws,
    relpath: str,
    before_bytes: bytes,
) -> None:
    """The original path's bytes after cleanup equal the bytes from before (L177).

    A sidecar elsewhere in the workspace is not this observation. Positive
    control: the same observer sees a difference when this test process
    writes the file.
    """
    dest = ws.resolve(relpath)
    after_bytes = dest.read_bytes()
    print(
        f"[F03] operand {relpath!r} bytes_before={len(before_bytes)} "
        f"bytes_after={len(after_bytes)}",
        flush=True,
    )
    assert after_bytes == before_bytes, (
        f"cleanup wrote {relpath!r}: before={before_bytes[:40]!r} "
        f"after={after_bytes[:40]!r}"
    )
    dest.write_bytes(before_bytes + b"\x00")
    control = dest.read_bytes()
    assert control != before_bytes, (
        "byte observer did not see the test-process write (positive control)"
    )
    dest.write_bytes(before_bytes)


def stdout_is_zip_bytes(blob: bytes) -> bool:
    return blob.startswith(_ZIP_MAGIC)


def finish_within_8s(
    extra_args: Sequence[str] = (),
    *,
    stdin: str | bytes | None = None,
) -> RunResult:
    """Detector command must finish within 8 seconds (L176). Hang is a failure."""
    t0 = time.monotonic()
    try:
        with workspace() as ws:
            result = ws.invoke(list(extra_args), stdin=stdin, timeout=8)
    except subprocess.TimeoutExpired:
        raise AssertionError(
            "detector command did not finish within 8 seconds"
        ) from None
    elapsed = time.monotonic() - t0
    print(f"[F03] finish_within_8s elapsed={elapsed:.3f}s", flush=True)
    assert elapsed <= 8.0, f"elapsed {elapsed:.3f}s exceeds 8 seconds"
    return result


def runtime_english_pair() -> tuple[str, str]:
    a = "Oak" + secrets.token_hex(3)
    b = "firm" + secrets.token_hex(3) + "."
    return a, b


# Single-script alphabets for constructable URL runs (L173). Not a TLD list.
_CYRILLIC_URL_LETTERS = "абвгдежзийклмнопрстуфхцчшщъыьэюя"
_GREEK_URL_LETTERS = "αβγδεζηθικλμνξοπρστυφχψω"


def _script_chunk(alphabet: str, n: int) -> str:
    if n < 1:
        raise HarnessError(f"URL chunk length must be positive, got {n}")
    if not alphabet:
        raise HarnessError("URL alphabet is empty")
    return "".join(secrets.choice(alphabet) for _ in range(n))


def single_script_url_run(alphabet: str) -> str:
    """A constructable single-script non-Latin URL run (letters.letters/letters).

    The PRD names the URL-run kind, not a TLD or an http spelling.
    """
    return (
        f"{_script_chunk(alphabet, 6)}.{_script_chunk(alphabet, 4)}/"
        f"{_script_chunk(alphabet, 5)}"
    )


def cyrillic_url_alphabet() -> str:
    return _CYRILLIC_URL_LETTERS


def greek_url_alphabet() -> str:
    return _GREEK_URL_LETTERS


def keep_sequence_cases() -> list[tuple[str, str]]:
    """L175 kinds as constructable strings, with a runtime base where allowed."""
    stamp = runtime_token("keep")
    flag = england_flag_sequence()
    public_ivs = "\u845b\U000e0100"
    cjk = secrets.choice(["\u8fba", "\u845b", "\u8fbb"])
    vs = chr(0xE0100 + 1 + secrets.randbelow(8))
    runtime_ivs = cjk + vs
    public_family = "\U0001f468\u200d\U0001f469\u200d\U0001f467"
    other_families = (
        "\U0001f468\u200d\U0001f469\u200d\U0001f466",
        "\U0001f469\u200d\U0001f469\u200d\U0001f467",
        "\U0001f468\u200d\U0001f468\u200d\U0001f467",
    )
    runtime_family = secrets.choice(other_families)
    public_vs16 = "\u2764\ufe0f"
    runtime_vs16 = secrets.choice(["\u2600\ufe0f", "\u2714\ufe0f", "\u2713\ufe0f"])
    public_key = "1\ufe0f\u20e3"
    runtime_key = secrets.choice(list("23456789")) + "\ufe0f\u20e3"
    public_persian = "\u0645\u06cc\u200c\u0631\u0648\u062f"
    runtime_persian = "\u0645\u06cc\u200c\u0622\u06cc\u062f"
    public_deva = "\u0915\u094d\u200d\u0937"
    runtime_deva = "\u0924\u094d\u200d\u0930"
    public_ar = "\u0627\u0644\u0627\u0633\u0645 \u200fAhmed\u200e"
    runtime_ar = "\u0627\u0644\u0643\u062a\u0627\u0628 \u200fNour\u200e"
    public_thai = "\u0e2a\u0e27\u0e31\u0e2a\u0e14\u0e35\u200b\u0e04\u0e23\u0e31\u0e1a"
    runtime_thai = "\u0e02\u0e2d\u0e1a\u0e04\u0e38\u0e13\u200b\u0e04\u0e48\u0e30"
    public_cyr = "\u041d\u0430\u0441\u043e\u0441 \u043f\u0435\u0440\u0435\u043a\u0430\u0447\u0438\u0432\u0430\u0435\u0442."
    runtime_cyr = "\u0420\u0435\u043a\u0430 \u0442\u0435\u0447\u0451\u0442 \u0431\u044b\u0441\u0442\u0440\u043e."
    public_el = "\u0397 \u03b1\u03bd\u03c4\u03bb\u03af\u03b1 \u03bb\u03b5\u03b9\u03c4\u03bf\u03c5\u03c1\u03b3\u03b5\u03af."
    runtime_el = "\u039f \u03ae\u03bb\u03b9\u03bf\u03c2 \u03bb\u03ac\u03bc\u03c0\u03b5\u03b9."
    public_comb = "Andre\u0301"
    runtime_comb = "flo\u0303w"
    public_math = "\U0001d6fc"
    runtime_math = secrets.choice(["\U0001d6fd", "\U0001d6fe", "\U0001d6ff"])
    public_ja = "\u5ddd\u304c\u9759\u304b\u306b\u6d41\u308c\u308b\u3002"
    runtime_ja = "\u6a4b\u304c\u9577\u3044\u3002"
    return [
        ("england-flag", f"Match in {flag} {stamp}."),
        ("ivs-public", f"The name {public_ivs} here {stamp}."),
        ("ivs-runtime", f"The name {runtime_ivs} here {stamp}."),
        ("family-public", f"We shipped {public_family} today {stamp}."),
        ("family-runtime", f"We shipped {runtime_family} today {stamp}."),
        ("vs16-public", f"It works {public_vs16} now {stamp}."),
        ("vs16-runtime", f"It works {runtime_vs16} now {stamp}."),
        ("keycap-public", f"Press {public_key} to continue {stamp}."),
        ("keycap-runtime", f"Press {runtime_key} to continue {stamp}."),
        ("persian-public", f"{public_persian} {stamp}."),
        ("persian-runtime", f"{runtime_persian} {stamp}."),
        ("deva-public", f"{public_deva} in Hindi {stamp}."),
        ("deva-runtime", f"{runtime_deva} in Hindi {stamp}."),
        ("arabic-public", f"{public_ar} here {stamp}."),
        ("arabic-runtime", f"{runtime_ar} here {stamp}."),
        ("thai-public", f"{public_thai} {stamp}."),
        ("thai-runtime", f"{runtime_thai} {stamp}."),
        ("cyrillic-public", public_cyr),
        ("cyrillic-runtime", runtime_cyr),
        ("greek-public", public_el),
        ("greek-runtime", runtime_el),
        ("combining-public", f"{public_comb} measured the rate {stamp}."),
        ("combining-runtime", f"{runtime_comb} measured the rate {stamp}."),
        ("cafe-named", f"The {CAFE} sits {stamp}."),
        ("nihongo-named", f"{NIHONGO} {stamp}."),
        ("japanese-prose-public", public_ja),
        ("japanese-prose-runtime", runtime_ja),
        ("math-greek-public", f"Let {public_math} be the angle {stamp}."),
        ("math-greek-runtime", f"Let {runtime_math} be the angle {stamp}."),
    ]


def ordinary_space_twin(text: str) -> str:
    """Same letters with non-standard spaces turned into U+0020."""
    out: list[str] = []
    for ch in text:
        if ch not in " \t\n\r" and unicodedata.category(ch) == "Zs":
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def named_file_in_stderr(stderr: str, path: str) -> bool:
    """The scanned (first) operand, as given on argv, is named on stderr."""
    return path in stderr
