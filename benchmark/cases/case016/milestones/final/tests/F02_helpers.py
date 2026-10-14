# feature: F02
"""Observation helpers for twenty-format extraction, size caps, and the window.

New names for this slice only. Sealed F01 helpers are imported, not copied.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from _harness import HarnessError, RunResult, invoke, invoke_hook, workspace
from F01_helpers import unicode_len

PLAIN_EXTS: tuple[str, ...] = (
    ".md",
    ".mdx",
    ".markdown",
    ".txt",
    ".text",
    ".rst",
    ".tex",
    ".org",
    ".adoc",
)
ZIP_EXTS: tuple[str, ...] = (
    ".docx",
    ".docm",
    ".pptx",
    ".pptm",
    ".xlsx",
    ".xlsm",
    ".odt",
    ".odp",
    ".ods",
    ".epub",
)
NOTEBOOK_EXT = ".ipynb"

PLAIN_CAP = 512 * 1024
ARCHIVE_CAP = 4 * 1024 * 1024

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_ODF_T = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
_ODF_O = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"

# Detector command forms the Interface Contract states.
CLEANUP_FLAG = "--clean"
HELP_FLAG = "--help"
USAGE_SYNOPSIS = "usage: detect.py [--clean] [--ci] [--] [FILE]"
EMPTY_INPUT_ERROR = "empty input"
CANNOT_READ_PREFIX = "cannot read input:"
EXIT_EMPTY_OR_UNREADABLE = 1
EXIT_UNKNOWN_OPTION = 2
METRICS_KEY = "_metrics"


def _xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def runtime_token(prefix: str) -> str:
    return f"{prefix}{secrets.token_hex(5)}"


def _runtime_token(prefix: str) -> str:
    return runtime_token(prefix)


def slop_extract_body() -> str:
    """English slop that contains “delve” and “game-changer”, with runtime filler.

    Under 120 words it carries three or more score-moving families that L108
    names as constructable fires (AI vocabulary; “it's worth noting that”;
    “stands as a testament”), so the L103 floor of 45 puts it at 40 or more.
    """
    stamp = _runtime_token("batch")
    n = 40 + secrets.randbelow(80)
    return (
        "In today's fast-paced digital landscape, it is crucial to delve into the "
        f"multifaceted tapestry of pivotal solutions across {n} workshops. "
        f"This comprehensive guide will showcase a robust, seamless framework "
        f"that empowers teams to unlock their full potential in {stamp}. "
        "It is not just a tool, it is a game-changer. "
        "It's worth noting that this guide stands as a testament to the craft."
    )


def slop_extract_twin() -> str:
    stamp = _runtime_token("twin")
    n = 40 + secrets.randbelow(80)
    return (
        "In this shifting digital landscape, it is crucial to delve into the "
        f"multifaceted tapestry of pivotal ideas across {n} studios. "
        f"This field guide will showcase a robust, seamless path "
        f"that empowers groups to unlock their full potential in {stamp}. "
        "It is not just a service, it is a game-changer. "
        "It's worth noting that this path stands as a testament to the trade."
    )


def stone_bridge_body() -> str:
    year = 1900 + secrets.randbelow(50)
    miles = 2 + secrets.randbelow(6)
    return (
        f"The bridge carried coal until {year + 58}. Its six arches were built from "
        f"stone quarried {miles} miles upstream, and the mortar has been repointed "
        f"twice, once in {year} and again after the flood. Nobody has found the "
        "original drawings. What survives is a contractor's invoice and a "
        "photograph of the opening, taken from the far bank."
    )


def write_plain(
    ws,
    relpath: str,
    text: str | bytes,
    *,
    encoding: str = "utf-8",
) -> Path:
    if isinstance(text, bytes):
        return ws.write(relpath, text)
    return ws.write(relpath, text.encode(encoding))


def _zip_write(path: Path, members: Sequence[tuple[str, str | bytes]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, payload in members:
            zf.writestr(name, payload)
    return path


def write_docx(ws, relpath: str, text: str) -> Path:
    body = f"<w:p><w:r><w:t>{_xml(text)}</w:t></w:r></w:p>"
    xml = (
        f'<?xml version="1.0"?><w:document xmlns:w="{_W}">'
        f"<w:body>{body}</w:body></w:document>"
    )
    return _zip_write(
        ws.resolve(relpath),
        (
            ("[Content_Types].xml", '<?xml version="1.0"?><Types/>'),
            ("word/document.xml", xml),
        ),
    )


def write_docm(ws, relpath: str, text: str) -> Path:
    return write_docx(ws, relpath, text)


def write_pptx(ws, relpath: str, text: str) -> Path:
    return write_pptx_slides(ws, relpath, (("slide1.xml", text),))


def write_pptx_slides(
    ws,
    relpath: str,
    slides: Sequence[tuple[str, str]],
    *,
    later_numbered_first: bool = False,
) -> Path:
    ordered = list(slides)
    if later_numbered_first:
        ordered = list(reversed(list(slides)))
    members: list[tuple[str, str | bytes]] = [
        ("[Content_Types].xml", '<?xml version="1.0"?><Types/>'),
    ]
    for name, payload in ordered:
        xml = (
            f'<?xml version="1.0"?><sld xmlns:a="{_A}">'
            f"<a:p><a:r><a:t>{_xml(payload)}</a:t></a:r></a:p></sld>"
        )
        members.append((f"ppt/slides/{name}", xml))
    return _zip_write(ws.resolve(relpath), members)


def write_pptm(ws, relpath: str, text: str) -> Path:
    return write_pptx(ws, relpath, text)


def write_xlsx(
    ws,
    relpath: str,
    text: str | None = None,
    *,
    shared_strings: Sequence[str] | None = None,
    sheets: Sequence[tuple[str, str]] | None = None,
    sheet_xml: str | None = None,
    later_numbered_first: bool = False,
) -> Path:
    members: list[tuple[str, str | bytes]] = [
        ("[Content_Types].xml", '<?xml version="1.0"?><Types/>'),
    ]
    if shared_strings is not None:
        items = "".join(f"<si><t>{_xml(s)}</t></si>" for s in shared_strings)
        members.append(
            (
                "xl/sharedStrings.xml",
                f'<?xml version="1.0"?><sst xmlns="{_P}">{items}</sst>',
            )
        )
    elif text is not None:
        members.append(
            (
                "xl/sharedStrings.xml",
                f'<?xml version="1.0"?><sst xmlns="{_P}">'
                f"<si><t>{_xml(text)}</t></si></sst>",
            )
        )
        sheet_xml = (
            f'<?xml version="1.0"?><worksheet xmlns="{_P}"><sheetData>'
            f'<row><c t="s"><v>0</v></c></row>'
            f"</sheetData></worksheet>"
        )
    if sheets is not None:
        ordered = list(sheets)
        if later_numbered_first:
            ordered = list(reversed(list(sheets)))
        for name, xml in ordered:
            members.append((f"xl/worksheets/{name}", xml))
    elif sheet_xml is not None:
        members.append(("xl/worksheets/sheet1.xml", sheet_xml))
    return _zip_write(ws.resolve(relpath), members)


def write_xlsm(
    ws,
    relpath: str,
    text: str | None = None,
    **kwargs: Any,
) -> Path:
    return write_xlsx(ws, relpath, text, **kwargs)


def write_odt(ws, relpath: str, xml_body: str | None = None, *, text: str | None = None) -> Path:
    if xml_body is None:
        if text is None:
            raise HarnessError("write_odt needs xml_body or text")
        xml_body = f"<text:p>{_xml(text)}</text:p>"
    content = (
        '<?xml version="1.0"?>'
        f'<office:document-content xmlns:office="{_ODF_O}" xmlns:text="{_ODF_T}">'
        f"<office:body><office:text>{xml_body}</office:text></office:body>"
        "</office:document-content>"
    )
    return _zip_write(
        ws.resolve(relpath),
        (("mimetype", "application/vnd.oasis.opendocument.text"), ("content.xml", content)),
    )


def write_odp(ws, relpath: str, xml_body: str | None = None, *, text: str | None = None) -> Path:
    return write_odt(ws, relpath, xml_body, text=text)


def write_ods(ws, relpath: str, xml_body: str | None = None, *, text: str | None = None) -> Path:
    return write_odt(ws, relpath, xml_body, text=text)


def write_epub(
    ws,
    relpath: str,
    body: str | None = None,
    *,
    chapters: Sequence[tuple[str, str]] | None = None,
    later_numbered_first: bool = False,
) -> Path:
    members: list[tuple[str, str | bytes]] = []
    if chapters is not None:
        ordered = list(chapters)
        if later_numbered_first:
            ordered = list(reversed(list(chapters)))
        for name, inner in ordered:
            members.append(
                (
                    name,
                    '<?xml version="1.0"?>'
                    '<html xmlns="http://www.w3.org/1999/xhtml">'
                    f"<body>{inner}</body></html>",
                )
            )
    else:
        if body is None:
            raise HarnessError("write_epub needs body or chapters")
        members.append(
            (
                "chapter.xhtml",
                '<?xml version="1.0"?>'
                '<html xmlns="http://www.w3.org/1999/xhtml">'
                f"<body><p>{_xml(body)}</p></body></html>",
            )
        )
    return _zip_write(ws.resolve(relpath), members)


def write_notebook(
    ws,
    relpath: str,
    *,
    markdown: str | Sequence[str] | None = None,
    code_source: str | Sequence[str] | None = None,
    output_text: str | None = None,
    cells: Sequence[Mapping[str, Any]] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> Path:
    if cells is not None:
        nb_cells: list[Any] = list(cells)
    else:
        nb_cells = []
        if markdown is not None:
            nb_cells.append(
                {"cell_type": "markdown", "source": markdown, "metadata": {}}
            )
        if code_source is not None:
            cell: dict[str, Any] = {
                "cell_type": "code",
                "source": code_source,
                "metadata": {},
            }
            if output_text is not None:
                cell["outputs"] = [
                    {
                        "output_type": "stream",
                        "name": "stdout",
                        "text": output_text,
                    }
                ]
            else:
                cell["outputs"] = []
            nb_cells.append(cell)
    obj: dict[str, Any] = {
        "cells": nb_cells,
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 2,
    }
    if extra:
        obj.update(extra)
    return ws.write(relpath, json.dumps(obj))


def write_zip_slop(ws, relpath: str, text: str) -> Path:
    ext = Path(relpath).suffix.lower()
    writers = {
        ".docx": write_docx,
        ".docm": write_docm,
        ".pptx": write_pptx,
        ".pptm": write_pptm,
        ".xlsx": write_xlsx,
        ".xlsm": write_xlsm,
        ".odt": lambda w, r, t: write_odt(w, r, text=t),
        ".odp": lambda w, r, t: write_odp(w, r, text=t),
        ".ods": lambda w, r, t: write_ods(w, r, text=t),
        ".epub": write_epub,
    }
    writer = writers.get(ext)
    if writer is None:
        raise HarnessError(f"no zip writer for extension {ext!r}")
    return writer(ws, relpath, text)


def cleanup_flag_from_usage(usage: str | None = None) -> str:
    """The cleanup switch the Contract states (``--clean``). Usage is not read."""
    return CLEANUP_FLAG


def _cleanup_flag() -> str:
    return CLEANUP_FLAG


def _stdout_is_report(text: str) -> bool:
    """True when *text* is the stated success report: one JSON object with ``_metrics``."""
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(obj, dict) and isinstance(obj.get(METRICS_KEY), dict)


# ---------------------------------------------------------------------------
# Detector failure forms (stated): stdout empty; last non-empty stderr line is
# one JSON object {"error": <string>}; exit 1 empty/unreadable, 2 unknown option.
# ---------------------------------------------------------------------------


def detector_error(result: RunResult) -> str:
    """Return the ``error`` string of a failed detector run (stated form)."""
    assert result.returncode != 0, (
        f"expected a failing status, got 0; stdout={result.stdout_text[:300]!r}"
    )
    assert result.stdout_text.strip() == "", (
        f"failure printed on stdout: {result.stdout_text[:300]!r}"
    )
    lines = [ln for ln in result.stderr_text.splitlines() if ln.strip()]
    assert lines, f"failure wrote nothing on stderr; exit={result.returncode}"
    assert "Traceback (most recent call last)" not in result.stderr_text, (
        f"failure printed a traceback: {result.stderr_text!r}"
    )
    try:
        obj = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"last stderr line is not a JSON object: {lines[-1]!r} ({exc})"
        ) from None
    assert isinstance(obj, dict) and isinstance(obj.get("error"), str), (
        f"last stderr line is not {{\"error\": <string>}}: {lines[-1]!r}"
    )
    return obj["error"]


def require_empty_input_error(result: RunResult) -> str:
    msg = detector_error(result)
    assert result.returncode == EXIT_EMPTY_OR_UNREADABLE, (
        f"empty input exit {result.returncode}, stated {EXIT_EMPTY_OR_UNREADABLE}"
    )
    assert msg == EMPTY_INPUT_ERROR, f"empty-input error is {msg!r}"
    return msg


def require_cannot_read_error(result: RunResult) -> str:
    msg = detector_error(result)
    assert result.returncode == EXIT_EMPTY_OR_UNREADABLE, (
        f"unreadable input exit {result.returncode}, stated {EXIT_EMPTY_OR_UNREADABLE}"
    )
    assert msg.startswith(CANNOT_READ_PREFIX), f"unreadable-input error is {msg!r}"
    return msg


def require_unknown_option_error(result: RunResult, token: str) -> str:
    msg = detector_error(result)
    assert result.returncode == EXIT_UNKNOWN_OPTION, (
        f"unknown option exit {result.returncode}, stated {EXIT_UNKNOWN_OPTION}"
    )
    assert token in msg, f"unknown-option error does not name {token!r}: {msg!r}"
    assert HELP_FLAG in msg, f"unknown-option error does not point at {HELP_FLAG}: {msg!r}"
    return msg


def states_one_file_at_a_time(stderr: str, first_operand: str) -> bool:
    """Contract: a stderr notice line, not a JSON object, naming the first operand."""
    def _json_object(line: str) -> bool:
        try:
            return isinstance(json.loads(line), dict)
        except ValueError:
            return False
    return any(
        first_operand in line and not _json_object(line.strip())
        for line in stderr.splitlines()
    )


def extract_via_cleanup(ws, relpath: str) -> str:
    """Observe extracted plain text via the cleanup switch (L170, L177).

    Success status; stdout is text, not a structured report. Non-success
    or report-shaped stdout raises.
    """
    flag = _cleanup_flag()
    dest = ws.resolve(relpath)
    result = ws.invoke([flag, str(dest)])
    if result.returncode != 0:
        raise HarnessError(
            f"cleanup extract failed: exit={result.returncode} "
            f"stderr={result.stderr_text!r} stdout={result.stdout_text[:500]!r}"
        )
    text = result.stdout_text
    if _stdout_is_report(text):
        raise HarnessError(
            "cleanup printed a structured report instead of extracted text; "
            f"stdout={text[:500]!r}"
        )
    print(
        f"[F02] cleanup extract path={relpath!r} chars={unicode_len(text)}",
        flush=True,
    )
    return text


def assert_extract_has_words(text: str, *words: str) -> None:
    missing = [w for w in words if w not in text]
    assert not missing, f"extract is missing {missing!r}; excerpt={text[:400]!r}"


def assert_no_markup(text: str) -> None:
    assert "<" not in text, f"extract leaked markup: excerpt={text[:400]!r}"


def tokens_in_relative_order(text: str, first: str, second: str) -> None:
    i1 = text.find(first)
    i2 = text.find(second)
    assert i1 != -1, f"first token {first!r} missing; excerpt={text[:400]!r}"
    assert i2 != -1, f"second token {second!r} missing; excerpt={text[:400]!r}"
    assert i1 < i2, (
        f"expected {first!r} before {second!r}; "
        f"indexes {i1} and {i2}; excerpt={text[:400]!r}"
    )


def pad_file_to_size(path: str | Path, n: int) -> Path:
    """Grow on-disk size without changing extractable prose.

    Zip archives get an extra stored member. Plain text and notebooks
    get trailing bytes that the extractors do not treat as extra prose
    (spaces after a JSON object; trailing spaces after a ZIP EOCD are
    not members; plain text padding sits past the named body as
    trailing whitespace that does not add distinctive words).
    """
    dest = Path(path)
    try:
        size = dest.stat().st_size
    except OSError as exc:
        raise HarnessError(f"cannot stat {dest} to pad: {exc}") from exc
    if size > n:
        raise HarnessError(f"{dest} is {size} bytes, larger than pad target {n}")
    if size == n:
        return dest
    extra = n - size
    suffix = dest.suffix.lower()
    if suffix in ZIP_EXTS:
        _pad_zip_exact(dest, n)
        return dest
    with dest.open("ab") as fh:
        fh.write(b" " * extra)
    got = dest.stat().st_size
    if got != n:
        raise HarnessError(f"padded {dest} to {got}, wanted {n}")
    return dest


def _pad_zip_exact(path: Path, n: int) -> None:
    """Rebuild a zip so on-disk size is exactly *n* via a stored pad member."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            kept = [
                (info, zf.read(info.filename))
                for info in zf.infolist()
                if not info.filename.startswith("padding/")
            ]
    except zipfile.BadZipFile as exc:
        raise HarnessError(f"cannot rebuild zip {path}: {exc}") from exc
    empty = _zip_bytes_with_pad(kept, 0)
    overhead = len(empty)
    if overhead > n:
        raise HarnessError(
            f"zip {path} without padding is {overhead} bytes, larger than {n}"
        )
    blob = _zip_bytes_with_pad(kept, n - overhead)
    if len(blob) != n:
        raise HarnessError(
            f"stored pad is not linear: overhead={overhead} "
            f"got={len(blob)} wanted={n}"
        )
    path.write_bytes(blob)
    if path.stat().st_size != n:
        raise HarnessError(
            f"zip pad wrote {path.stat().st_size} bytes, wanted {n}"
        )


def _zip_bytes_with_pad(
    kept: Sequence[tuple[zipfile.ZipInfo, bytes]], pad_len: int
) -> bytes:
    import io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for info, data in kept:
            zf.writestr(info, data)
        zf.writestr(
            "padding/blob.bin",
            b"\x00" * pad_len,
            compress_type=zipfile.ZIP_STORED,
        )
    return buf.getvalue()


def _hook_strings(result: RunResult) -> list[str]:
    if result.returncode != 0:
        raise HarnessError(
            f"plugin hook failed: exit={result.returncode} "
            f"stderr={result.stderr_text!r} stdout={result.stdout_text[:500]!r}"
        )
    text = result.stdout_text
    if text == "":
        return []
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HarnessError(
            f"hook stdout is not JSON: {exc}; text={text[:500]!r}"
        ) from exc
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, str):
            found.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(obj)
    return found


# ---------------------------------------------------------------------------
# Hook stdout envelopes (stated forms)
# ---------------------------------------------------------------------------


def block_reply(result: RunResult) -> str:
    """The ``reason`` of the prompt-submit block decision (stated envelope)."""
    if result.returncode != 0:
        raise HarnessError(
            f"prompt-submit hook failed: exit={result.returncode} "
            f"stderr={result.stderr_text!r}"
        )
    try:
        obj = json.loads(result.stdout_text)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"command stdout is not one JSON object: {result.stdout_text[:400]!r} ({exc})"
        ) from None
    assert isinstance(obj, dict), f"command stdout is not an object: {obj!r}"
    assert obj.get("decision") == "block", f"command is not a block decision: {obj!r}"
    reason = obj.get("reason")
    assert isinstance(reason, str), f"block reason is not a string: {obj!r}"
    return reason


def guard_nudge(result: RunResult) -> str:
    """The post-tool-use correction text, or ``""`` when the hook printed nothing.

    Flagged: one JSON object ``{"hookSpecificOutput": {"hookEventName":
    "PostToolUse", "additionalContext": <nudge>}}``. Not flagged / skipped:
    empty standard output.
    """
    if result.returncode != 0:
        raise HarnessError(
            f"post-tool-use hook failed: exit={result.returncode} "
            f"stderr={result.stderr_text!r}"
        )
    text = result.stdout_text
    if text.strip() == "":
        return ""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"guard stdout is not JSON: {text[:400]!r} ({exc})") from None
    hso = obj.get("hookSpecificOutput") if isinstance(obj, dict) else None
    assert isinstance(hso, dict), f"guard stdout lacks hookSpecificOutput: {obj!r}"
    assert hso.get("hookEventName") == "PostToolUse", f"guard event name: {hso!r}"
    ctx = hso.get("additionalContext")
    assert isinstance(ctx, str) and ctx.strip(), f"guard additionalContext: {hso!r}"
    return ctx


_NUDGE_SCORE = re.compile(r"\(score (\d{1,3}), band ")


def nudge_score(nudge: str, base: str) -> int:
    """Score field ``(score <n>, band <band>`` of a guard nudge naming *base*."""
    assert nudge.startswith("prosecheck: "), f"nudge form: {nudge[:300]!r}"
    assert base in nudge, f"nudge does not name {base!r}: {nudge[:300]!r}"
    found = _NUDGE_SCORE.findall(nudge)
    assert len(found) == 1, f"nudge score field not found once: {nudge[:300]!r}"
    return int(found[0])


def plugin_prompt(ws, prompt: str) -> tuple[RunResult, str]:
    """Fire the prompt-submit hook with a slash-command prompt; return the reply."""
    result = ws.invoke_hook(
        "prompt-submit",
        payload={"prompt": prompt},
    )
    reply = block_reply(result)
    print(
        f"[F02] prompt {prompt[:80]!r} exit={result.returncode} reply={reply[:200]!r}",
        flush=True,
    )
    return result, reply


def check_file(ws, relpath: str) -> tuple[RunResult, str]:
    dest = ws.resolve(relpath)
    return plugin_prompt(ws, "/prosecheck check " + str(dest))


def show_session(ws) -> tuple[RunResult, str]:
    """Read the session ledger through the public show command."""
    return plugin_prompt(ws, "/prosecheck show")


def guard_write(ws, relpath: str) -> tuple[RunResult, str]:
    """Fire the post-tool-use hook for a Write; return ``(result, nudge or "")``."""
    dest = ws.resolve(relpath)
    result = ws.invoke_hook(
        "post-tool-use",
        payload={
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(dest),
                "content": dest.read_text(encoding="utf-8", errors="replace")
                if dest.suffix.lower() not in ZIP_EXTS
                else "document",
            },
            "cwd": str(ws.path),
        },
    )
    nudge = guard_nudge(result)
    print(
        f"[F02] guard write {relpath!r} exit={result.returncode} nudge={nudge[:200]!r}",
        flush=True,
    )
    return result, nudge


# ---------------------------------------------------------------------------
# /prosecheck check reply (stated forms)
# ---------------------------------------------------------------------------

_CHECK_SCORE_LINE = re.compile(
    r"^(?P<base>.+) - (?P<phrase>.+) \(score (?P<score>\d{1,3})/100, band: (?P<band>[a-z ]+)\)$"
)
_CHECK_SCORE_ANY = re.compile(r"\(score \d{1,3}/100, band: ")


def check_scored(reply: str) -> dict[str, Any]:
    """First line of a scored check reply: ``<base> - <phrase> (score <n>/100, band: <band>)``."""
    first = reply.splitlines()[0] if reply.splitlines() else ""
    m = _CHECK_SCORE_LINE.match(first)
    assert m, f"check reply first line is not the scored form: {reply[:400]!r}"
    return {
        "base": m.group("base"),
        "phrase": m.group("phrase"),
        "score": int(m.group("score")),
        "band": m.group("band"),
    }


def check_has_score(reply: str) -> bool:
    """True when the reply carries the stated score field."""
    return _CHECK_SCORE_ANY.search(reply) is not None


def score_in_check_reply(text: str, *, expected: int | None = None) -> int:
    """Read the stated score field of a scored check reply."""
    rec = check_scored(text)
    if expected is not None:
        assert rec["score"] == expected, (
            f"check score {rec['score']} != detector score {expected}; reply={text[:400]!r}"
        )
    return rec["score"]


NOT_SCORED_MARKS = ("not a file", "cannot read", "no readable text", "detector unavailable", "no report")
_STANDALONE_0_100 = re.compile(r"(?<![\d.,])(?:100|[1-9]?\d)(?![\d]|[.,]\d)")


def _without_paths(reply: str, *paths: str) -> str:
    tokens = set()
    for path in paths:
        if path:
            tokens.add(str(path))
            tokens.add(Path(str(path)).name)
    out = reply
    for token in sorted(tokens, key=len, reverse=True):
        out = out.replace(token, " ")
    return out


def check_not_scored(reply: str, *paths: str) -> str:
    """A not-scored check reply, read as the Contract states it.

    Non-empty; no score field; no standalone integer 0-100 once the named
    path(s) and their base names are removed. Returns the reply with those
    paths removed. Line count, prefix and the position of the mark are free.
    """
    assert reply.strip(), "check reply is empty"
    assert not check_has_score(reply), f"not-scored reply carries a score: {reply[:400]!r}"
    rest = _without_paths(reply, *paths)
    found = _STANDALONE_0_100.findall(rest)
    assert not found, (
        f"not-scored reply shows an integer from 0 through 100 {found}: {reply[:400]!r}"
    )
    return rest


def not_scored_marks(text: str) -> list[str]:
    """Which of the Contract's not-scored marks the text carries."""
    low = text.lower()
    return [mark for mark in NOT_SCORED_MARKS if mark in low]


_OVER_KB = re.compile(r"(?i)(?<![A-Za-z])over (\d+) KB(?![A-Za-z])")


def kilobyte_figure(cap_bytes: int) -> int:
    """Named on-disk cap expressed in kilobytes (512 KB, 4 MB -> 4096 KB)."""
    if cap_bytes < 1024 or cap_bytes % 1024 != 0:
        raise HarnessError(
            f"cap {cap_bytes} is not a whole number of kilobytes"
        )
    return cap_bytes // 1024


def _cap_figures(cap_bytes: int) -> tuple[int, ...]:
    kb = kilobyte_figure(cap_bytes)
    # PRD FP-02: caps are in binary units, so the 4 MB cap is 4096 KB.
    return (kb,)


def require_check_over_cap(reply: str, *, cap_bytes: int, path: str | None = None) -> None:
    """Over-cap reply: ``over <KB> KB`` with the cap's kilobyte figure; no score."""
    rest = check_not_scored(reply, *([path] if path else []))
    m = _OVER_KB.search(rest)
    assert m, f"over-cap check reply has no over <KB> KB: {reply[:400]!r}"
    assert int(m.group(1)) in _cap_figures(cap_bytes), (
        f"over-cap reply names {m.group(1)} KB, stated {_cap_figures(cap_bytes)}"
    )


def require_check_cannot_read(reply: str, path: str, typed: str | None = None) -> None:
    """Missing path: exactly the mark ``cannot read`` and the path as typed."""
    shown = typed if typed is not None else path
    assert shown in reply, f"cannot-read reply does not carry {shown!r}: {reply[:400]!r}"
    rest = check_not_scored(reply, path, shown)
    assert not_scored_marks(rest) == ["cannot read"], (
        f"cannot-read reply marks {not_scored_marks(rest)}: {reply[:400]!r}"
    )
    assert not _OVER_KB.search(rest)


def require_check_not_a_file(reply: str, *paths: str) -> None:
    """Directory: exactly the mark ``not a file``."""
    rest = check_not_scored(reply, *paths)
    assert not_scored_marks(rest) == ["not a file"], (
        f"not-a-file reply marks {not_scored_marks(rest)}: {reply[:400]!r}"
    )
    assert not _OVER_KB.search(rest)


# ---------------------------------------------------------------------------
# /prosecheck show reply (stated forms)
# ---------------------------------------------------------------------------


def show_row(reply: str, basename: str) -> str:
    """Remainder of the newest row ``<file> - <rest>`` for *basename*.

    A row is optional leading whitespace, then the base name and `` - ``;
    other lines (such as a heading) are free and may be absent.
    """
    head = f"{basename} - "
    for line in reply.splitlines():
        if line.strip().startswith(head):
            return line.strip()[len(head):]
    raise AssertionError(f"show has no row for {basename!r}: {reply[:400]!r}")


_SHOW_SCORE = re.compile(r"\(score \d{1,3}/")
_SHOW_SIZE_SKIP = re.compile(r"(?i)^not scored: .*?(?<![0-9])(\d+) KB(?![A-Za-z]).*$")


def require_binary_ledger_record(blob: str, basename: str) -> None:
    """Binary row: ``<file> - binary, ... (not re-scored)``; no score, not a size skip."""
    rest = show_row(blob, basename)
    assert "not re-scored" in rest.lower(), f"binary row does not say not re-scored: {rest!r}"
    assert not _SHOW_SCORE.search(rest), f"binary row carries a score: {rest!r}"
    assert not _SHOW_SIZE_SKIP.match(rest), f"binary row is a size skip: {rest!r}"
    print(f"[F02] ledger binary row {basename!r}: {rest!r}", flush=True)


def require_show_size_skip(blob: str, basename: str, *, cap_bytes: int) -> None:
    """Size-skip row: ``<file> - not scored: <free text naming <KB> KB>``; no score."""
    rest = show_row(blob, basename)
    assert _SHOW_SIZE_SKIP.match(rest), f"size-skip row is not the stated form: {rest!r}"
    named = [int(n) for n in re.findall(r"(?i)(?<![0-9])(\d+) KB(?![A-Za-z])", rest)]
    assert set(named) & set(_cap_figures(cap_bytes)), (
        f"size-skip row names {named} KB, stated {_cap_figures(cap_bytes)}"
    )
    assert not _SHOW_SCORE.search(rest)


def standalone_int_present(text: str, value: int) -> bool:
    return re.search(rf"(?<!\d){value}(?!\d)", str(text)) is not None


def window_body(n: int) -> str:
    """Exactly *n* characters of extractable padding with no leading/trailing space.

    Ordinary space-separated words, so a test about the window length does
    not also time a single very long token (that budget has its own test).
    """
    if n < 1:
        raise HarnessError("window body length must be positive")
    body = ("bridge " * (n // 7 + 2))[:n]
    if body.endswith(" "):
        body = body[:-1] + "s"
    return body


def spreadsheet_sheet_xml(
    *,
    shared_indices: Sequence[str] = (),
    inline: Sequence[str] = (),
    string_typed: Sequence[str] = (),
    formula_cache: Sequence[tuple[str, str]] = (),
    extra_cells: str = "",
) -> str:
    cells: list[str] = []
    for index in shared_indices:
        cells.append(f'<c t="s"><v>{_xml(index)}</v></c>')
    for token in inline:
        cells.append(f'<c t="inlineStr"><is><t>{_xml(token)}</t></is></c>')
    for token in string_typed:
        cells.append(f'<c t="str"><v>{_xml(token)}</v></c>')
    for formula, cached in formula_cache:
        cells.append(
            f'<c t="str"><f>{_xml(formula)}</f><v>{_xml(cached)}</v></c>'
        )
    row = "<row>" + "".join(cells) + extra_cells + "</row>"
    return (
        f'<?xml version="1.0"?><worksheet xmlns="{_P}">'
        f"<sheetData>{row}</sheetData></worksheet>"
    )
