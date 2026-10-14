# feature: F05
"""Observation helpers for the saved-file guard.

New names for this slice only. Sealed harness, F01, F02, and F04 helpers
are imported, not copied.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from _harness import (
    ENV_PLUGIN_ROOT,
    HarnessError,
    RunResult,
    detector_script,
    file_mode,
    node_executable,
    read_file,
)
from F01_helpers import (
    AI_REGISTER,
    BAND_RANGES,
    CONFIDENCE_LABELS,
    SCAN_CAP,
    HUMANIZED_CODING,
    SHORT_FACTUAL,
    SHORT_SLOP,
    SNOW_AND_ROAD,
    band_named_for_score,
    neutral_words,
    pad_human,
    scan_path,
    scan_stdin,
)
from F02_helpers import (
    NOTEBOOK_EXT,
    ZIP_EXTS,
    runtime_token,
    standalone_int_present,
    write_notebook,
    write_plain,
    write_zip_slop,
)

PRODUCT_NAME = "prosecheck"
WINDOW_PLAIN = 262144
WINDOW_GROUPED = "262,144"
PLAIN_KB = 512
ARCHIVE_KB_FIGURES = (4096,)
LEVEL_WORDS = ("lite", "full", "strict", "off")
CONFIDENCE_WORDS = ("none", "low", "moderate", "high")

# L22 names these as the plugin's hook phrases, one per L98 band.
PHRASE_BY_BAND = {
    "clean": "reads clean",
    "light tells": "reads mostly clean",
    "mixed": "reads with some AI tells",
    "heavy tells": "reads with heavy AI tells",
    "pervasive tells": "reads with pervasive AI tells",
}

# Decimal 512 KB is still within a 1024-based 512 KB. 513 KiB is past both.
DECIMAL_512_KB = 512 * 1000
OVER_BOTH_512 = 513 * 1024
# Past both readings of 512 KB, under both readings of 4 MB.
BETWEEN_CAPS = 600 * 1024
OVER_BOTH_4MB = 4 * 1024 * 1024 + 64 * 1024
OVER_BOTH_4MB_OTHER = 4 * 1024 * 1024 + 256 * 1024

_CACHE: dict[str, "Measured"] = {}


@dataclass(frozen=True)
class Measured:
    text: str
    score: int
    band: str
    confidence: str
    reason: str
    labels: tuple[str, ...]


@dataclass
class Standin:
    """Interpreter stand-in planted ahead of every other directory on PATH."""

    root: Path
    log: Path
    env_updates: dict[str, str]

    def invocations(self) -> int:
        try:
            body = self.log.read_text(encoding="utf-8")
        except OSError as exc:
            raise HarnessError(f"cannot read stand-in log {self.log}: {exc}") from exc
        return len([line for line in body.splitlines() if line.strip()])


# ---------------------------------------------------------------------------
# Detector report, read as the Interface Contract states it: one JSON object;
# ``_metrics`` carries ``ai_tell_score`` / ``ai_tell_band`` / ``confidence`` /
# ``confidence_reason``; every other member is one fired finding whose
# ``label`` is a string.
# ---------------------------------------------------------------------------

METRICS_KEY = "_metrics"
SCORE_KEY = "ai_tell_score"
BAND_KEY = "ai_tell_band"
CONFIDENCE_KEY = "confidence"
REASON_KEY = "confidence_reason"


def detector_report(text: str, *, source: str = "detector stdout") -> dict[str, Any]:
    """Parse a detector success report: one JSON object with a ``_metrics`` object."""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{source} is not one JSON object: {exc}; text={text[:400]!r}")
    assert isinstance(obj, dict), f"{source} is not a JSON object: {type(obj).__name__}"
    metrics = obj.get(METRICS_KEY)
    assert isinstance(metrics, dict), f"{source} has no {METRICS_KEY} object"
    return obj


def bind_guard_metrics() -> None:
    """Kept for callers; the report members are stated, nothing is bound."""
    return None


def _from_report(text: str, report: Mapping[str, Any]) -> Measured:
    metrics = report[METRICS_KEY]
    score = metrics.get(SCORE_KEY)
    assert isinstance(score, int) and not isinstance(score, bool) and 0 <= score <= 100, (
        f"{METRICS_KEY}.{SCORE_KEY} is not an integer 0-100: {score!r}"
    )
    band = metrics.get(BAND_KEY)
    confidence = metrics.get(CONFIDENCE_KEY)
    assert confidence in CONFIDENCE_LABELS, (
        f"{METRICS_KEY}.{CONFIDENCE_KEY} is not a confidence word: {confidence!r}"
    )
    expected_band = band_named_for_score(score)
    if band != expected_band:
        raise HarnessError(
            f"detector band {band!r} is not the band named for score {score} "
            f"({expected_band!r})"
        )
    reason = ""
    if confidence != "high":
        reason = metrics.get(REASON_KEY)
        assert isinstance(reason, str) and reason.strip(), (
            f"confidence {confidence!r} without a readable {REASON_KEY}"
        )
    labels = tuple(
        dict.fromkeys(
            value["label"]
            for key, value in report.items()
            if key != METRICS_KEY
            and isinstance(value, Mapping)
            and isinstance(value.get("label"), str)
            and value["label"].strip()
        )
    )
    return Measured(
        text=text,
        score=score,
        band=band,
        confidence=confidence,
        reason=reason,
        labels=labels,
    )


def measure_text(text: str) -> Measured:
    result = scan_stdin(text)
    if result.returncode != 0:
        raise HarnessError(
            "detector did not score the probe text: "
            f"exit={result.returncode} stderr={result.stderr_text[:400]!r}"
        )
    measured = _from_report(text, detector_report(result.stdout_text))
    print(
        f"[F05] measured score={measured.score} band={measured.band!r} "
        f"confidence={measured.confidence!r} labels={len(measured.labels)} "
        f"chars={len(text)}",
        flush=True,
    )
    return measured


def measure_path(ws, relpath: str) -> Measured:
    result = scan_path(ws, relpath)
    if result.returncode != 0:
        raise HarnessError(
            f"detector did not score {relpath}: "
            f"exit={result.returncode} stderr={result.stderr_text[:400]!r}"
        )
    measured = _from_report(
        "", detector_report(result.stdout_text, source=f"detector report for {relpath}")
    )
    print(
        f"[F05] measured path {relpath} score={measured.score} "
        f"band={measured.band!r} confidence={measured.confidence!r} "
        f"labels={len(measured.labels)}",
        flush=True,
    )
    return measured


def phrase_for_band(band: str) -> str:
    phrase = PHRASE_BY_BAND.get(band)
    if phrase is None:
        raise HarnessError(f"no hook phrase for band {band!r}")
    return phrase


def fresh_name(suffix: str) -> str:
    return runtime_token("f") + suffix


def plant_prose(ws, relpath: str, text: str) -> Path:
    ext = Path(relpath).suffix.lower()
    if ext == NOTEBOOK_EXT:
        return write_notebook(ws, relpath, markdown=text)
    if ext in ZIP_EXTS:
        return write_zip_slop(ws, relpath, text)
    return write_plain(ws, relpath, text)


def nudge_text(result: RunResult) -> str:
    """The guard's nudge, read from the stated post-tool-use envelope.

    Silence is empty standard output. Anything else on standard output is
    exactly one JSON object whose ``hookSpecificOutput`` object carries
    ``hookEventName`` ``PostToolUse`` and a non-empty ``additionalContext``
    string; that string is returned. The hook always exits 0.
    """
    assert result.returncode == 0, (
        "hook exited non-zero; that is not silence: "
        f"exit={result.returncode} stderr={result.stderr_text[:400]!r} "
        f"stdout={result.stdout_text[:400]!r}"
    )
    raw = result.stdout_text
    if raw == "":
        return ""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"hook stdout is not the JSON envelope: {exc}; text={raw[:400]!r}"
        ) from exc
    assert isinstance(obj, dict), f"hook stdout JSON is not an object: {raw[:400]!r}"
    inner = obj.get("hookSpecificOutput")
    assert isinstance(inner, dict), f"envelope has no hookSpecificOutput object: {raw[:400]!r}"
    assert inner.get("hookEventName") == "PostToolUse", (
        f"hookEventName is not PostToolUse: {inner.get('hookEventName')!r}"
    )
    context = inner.get("additionalContext")
    assert isinstance(context, str) and context != "", (
        f"additionalContext is not a non-empty string: {raw[:400]!r}"
    )
    return context


def require_silent(result: RunResult) -> None:
    text = nudge_text(result)
    assert text == "", f"hook emitted a nudge; text={text[:400]!r}"


def block_reply(result: RunResult) -> str:
    """The ``reason`` of the stated command block object."""
    assert result.returncode == 0, (
        f"prompt-submit exited {result.returncode}; stderr={result.stderr_text[:400]!r}"
    )
    raw = result.stdout_text
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"command reply is not JSON: {exc}; text={raw[:400]!r}") from exc
    assert isinstance(obj, dict) and obj.get("decision") == "block", (
        f"command reply is not a block decision: {raw[:400]!r}"
    )
    reason = obj.get("reason")
    assert isinstance(reason, str), f"block reason is not a string: {raw[:400]!r}"
    return reason


def show_text(ws, session_id: str | None = None) -> str:
    payload: dict[str, Any] = {"prompt": "/prosecheck show"}
    if session_id is not None:
        payload["session_id"] = session_id
    result = ws.invoke_hook("prompt-submit", payload=payload)
    text = block_reply(result)
    assert text.strip(), "show returned an empty reply"
    print(
        f"[F05] show session={session_id!r} chars={len(text)}",
        flush=True,
    )
    return text


# ---------------------------------------------------------------------------
# Stated text forms
#
# Nudge, one line per flagged file (several lines joined by a newline):
#   prosecheck: <base> <phrase> (score <n>, band <band>[<coverage>]). Flagged: <l1>; <l2>. <ask containing the word fix>
# Show scored row:
#   <base> - <phrase> (score <n>/<band>[<coverage>])[ - <state>: <labels>]  (state carries flagged or under)
# Show other rows:
#   <base> - not scored: <free text naming <KB> KB>
#   <base> - <free text containing "not re-scored", not "not scored:">
#   <base> - not scored: <reason>
# <coverage> is exactly ", first 262,144 characters only".
# ---------------------------------------------------------------------------

COVERAGE_NOTE = ", first 262,144 characters only"
FIX_WORD = re.compile(r"(?i)(?<![a-z])fix")
_PHRASES_ALT = "|".join(
    re.escape(p) for p in sorted(PHRASE_BY_BAND.values(), key=len, reverse=True)
)
_BANDS_ALT = "|".join(re.escape(b) for b in sorted(BAND_RANGES, key=len, reverse=True))


@dataclass(frozen=True)
class Nudge:
    base: str
    phrase: str
    score: int
    band: str
    truncated: bool
    labels: tuple[str, ...]


def nudge_lines(text: str) -> list[str]:
    return [line for line in text.split("\n")]


def parse_nudge(text: str, base: str) -> Nudge:
    """The single nudge line for *base*, parsed in its stated form."""
    head = f"prosecheck: {base} "
    lines = [line for line in nudge_lines(text) if line.startswith(head)]
    assert len(lines) == 1, (
        f"expected exactly one nudge line for {base!r}, got {len(lines)}; text={text[:600]!r}"
    )
    line = lines[0]
    pattern = (
        r"^prosecheck: " + re.escape(base) + r" (?P<phrase>" + _PHRASES_ALT + r")"
        r" \(score (?P<score>\d+), band (?P<band>" + _BANDS_ALT + r")"
        r"(?P<cov>" + re.escape(COVERAGE_NOTE) + r")?\)\. Flagged: (?P<labels>.+?)\. "
        r"(?P<ask>.*)$"
    )
    match = re.match(pattern, line)
    assert match, f"nudge line for {base!r} is not in the stated form: {line!r}"
    assert FIX_WORD.search(match.group("ask")), (
        f"nudge line for {base!r} does not ask for a fix: {line!r}"
    )
    return Nudge(
        base=base,
        phrase=match.group("phrase"),
        score=int(match.group("score")),
        band=match.group("band"),
        truncated=match.group("cov") is not None,
        labels=tuple(match.group("labels").split("; ")),
    )


def nudge_bases(text: str) -> list[str]:
    """Base names of the nudge lines in *text*, in order (first token after the prefix)."""
    out = []
    for line in nudge_lines(text):
        if line.startswith("prosecheck: "):
            out.append(line[len("prosecheck: "):].split(" ", 1)[0])
    return out


@dataclass(frozen=True)
class ShowRow:
    kind: str  # "scored", "size", "binary", "failed"
    line: str
    phrase: str | None = None
    score: int | None = None
    band: str | None = None
    truncated: bool = False
    status: str | None = None  # "flagged", "under", or None (no labels clause)
    labels: tuple[str, ...] = ()
    kbs: tuple[int, ...] = ()  # every <n> KB figure in a size-skip row
    reason: str | None = None


def show_rows_for(text: str, base: str) -> list[str]:
    head = f"{base} - "
    return [line.strip() for line in text.split("\n") if line.strip().startswith(head)]


def show_row(text: str, base: str) -> ShowRow:
    """The single show row for *base*, parsed in its stated form."""
    rows = show_rows_for(text, base)
    assert len(rows) == 1, (
        f"expected exactly one show row for {base!r}, got {len(rows)}; text={text[:600]!r}"
    )
    line = rows[0]
    rest = line[len(base) + 3:]
    scored = re.match(
        r"^(?P<phrase>" + _PHRASES_ALT + r") \(score (?P<score>\d+)/(?P<band>" + _BANDS_ALT
        + r")(?P<cov>, first (?:262,144|262144) characters only)?\)(?P<tail>.*)$",
        rest,
    )
    if scored:
        tail = scored.group("tail")
        status = None
        labels: tuple[str, ...] = ()
        if tail:
            clause = re.match(r"^ - (?P<state>[^:]*): (?P<labels>.+)$", tail)
            if not clause:
                raise AssertionError(f"scored row has an unstated tail: {line!r}")
            state = clause.group("state")
            if re.search(r"(?i)(?<![a-z])flagged(?![a-z])", state):
                status = "flagged"
            elif re.search(r"(?i)(?<![a-z])under(?![a-z])", state):
                status = "under"
            else:
                raise AssertionError(f"scored row clause names neither flagged nor under: {line!r}")
            labels = tuple(clause.group("labels").split("; "))
        return ShowRow(
            kind="scored", line=line, phrase=scored.group("phrase"),
            score=int(scored.group("score")), band=scored.group("band"),
            truncated=scored.group("cov") is not None, status=status, labels=labels,
        )
    size = re.match(r"(?i)^not scored: .*?(?<![0-9])(\d+) KB(?![A-Za-z]).*$", rest)
    if size:
        kbs = tuple(int(n) for n in re.findall(r"(?i)(?<![0-9])(\d+) KB(?![A-Za-z])", rest))
        return ShowRow(kind="size", line=line, kbs=kbs)
    low = rest.lower()
    if "not re-scored" in low and "not scored:" not in low:
        return ShowRow(kind="binary", line=line)
    if low.startswith("not scored: "):
        reason = rest[len("not scored: "):]
        assert reason.strip(), f"failed row has no reason: {line!r}"
        assert not re.search(r"(?i)(?<![0-9])\d+ KB(?![A-Za-z])", reason), f"failed row reads as a size skip: {line!r}"
        return ShowRow(kind="failed", line=line, reason=reason)
    raise AssertionError(f"show row for {base!r} is not in a stated form: {line!r}")


def require_scored_row(text: str, base: str, measured: "Measured") -> ShowRow:
    row = show_row(text, base)
    assert row.kind == "scored", f"{base!r} is not a scored row: {row.line!r}"
    assert row.score == measured.score, f"row score {row.score} != {measured.score}: {row.line!r}"
    assert row.band == measured.band, f"row band {row.band!r} != {measured.band!r}"
    assert row.phrase == phrase_for_band(measured.band), f"row phrase {row.phrase!r}"
    return row


def fire_tool(
    ws,
    tool: str,
    *,
    session_id: str | None = None,
    file_path: str | None = None,
    notebook_path: str | None = None,
    content: str | None = None,
    command: str | None = None,
    cwd: str | None = None,
    env_updates: Mapping[str, str | None] | None = None,
    timeout: float | None = None,
    process_cwd: str | None = None,
) -> tuple[RunResult, str]:
    tool_input: dict[str, Any] = {}
    if file_path is not None:
        tool_input["file_path"] = file_path
    if notebook_path is not None:
        tool_input["notebook_path"] = notebook_path
    if content is not None:
        tool_input["content"] = content
    if command is not None:
        tool_input["command"] = command
    payload: dict[str, Any] = {"tool_name": tool, "tool_input": tool_input}
    if session_id is not None:
        payload["session_id"] = session_id
    if cwd is not None:
        payload["cwd"] = cwd
    result = ws.invoke_hook(
        "post-tool-use",
        payload=payload,
        env_updates=env_updates,
        timeout=timeout,
        cwd=process_cwd,
    )
    text = nudge_text(result)
    print(
        f"[F05] {tool} exit={result.returncode} nudge_chars={len(text)} "
        f"session={session_id!r}",
        flush=True,
    )
    return result, text


def require_flagged_envelope(
    text: str,
    *,
    base: str,
    measured: Measured,
) -> Nudge:
    """The nudge line for *base* carries the stated facts of *measured*.

    Base name, hook phrase for the band, score, band, one to five of the
    detector's fired labels, and the stated fix ask. More than five fired
    labels are never all listed.
    """
    assert text.strip(), "flagged save emitted an empty envelope"
    nudge = parse_nudge(text, base)
    assert nudge.score == measured.score, (
        f"nudge score {nudge.score} is not the detector score {measured.score}"
    )
    assert nudge.band == measured.band, (
        f"nudge band {nudge.band!r} is not the detector band {measured.band!r}"
    )
    assert nudge.phrase == phrase_for_band(measured.band), (
        f"nudge phrase {nudge.phrase!r} is not the phrase for {measured.band!r}"
    )
    assert 1 <= len(nudge.labels) <= 5, (
        f"nudge lists {len(nudge.labels)} labels; it must list one to five: {nudge.labels!r}"
    )
    assert len(set(nudge.labels)) == len(nudge.labels), f"repeated label: {nudge.labels!r}"
    for label in nudge.labels:
        assert label in measured.labels, (
            f"nudge label {label!r} is not one the detector fired: {measured.labels!r}"
        )
    if len(measured.labels) > 5:
        assert len(nudge.labels) < len(measured.labels)
    print(
        f"[F05] envelope names {base!r} score={measured.score} "
        f"band={measured.band!r} labels={len(nudge.labels)}/{len(measured.labels)}",
        flush=True,
    )
    return nudge


def snapshot_config(config_dir: Path) -> dict[str, bytes]:
    try:
        names = list(os.listdir(config_dir))
    except OSError as exc:
        raise HarnessError(f"cannot list config dir {config_dir}: {exc}") from exc
    snap: dict[str, bytes] = {}
    for name in names:
        path = config_dir / name
        try:
            info = path.stat()
        except OSError as exc:
            raise HarnessError(f"cannot stat {path}: {exc}") from exc
        if not stat.S_ISREG(info.st_mode):
            continue
        try:
            snap[name] = path.read_bytes()
        except OSError as exc:
            raise HarnessError(f"cannot read {path}: {exc}") from exc
    return snap


def changed_config_files(config_dir: Path, before: Mapping[str, bytes]) -> list[Path]:
    after = snapshot_config(config_dir)
    changed: list[Path] = []
    for name, blob in after.items():
        if before.get(name) != blob:
            changed.append(config_dir / name)
    return changed


def ledger_file_is_private(path: Path, *, parent: str, marker: str) -> bool:
    """Owner-only, and the body holds neither the parent directory nor the planted marker.

    Stat or read failure raises. A group/other bit, the parent directory, or
    the marker returns False — it is not reported as a missing file.
    """
    mode = file_mode(path)
    text = read_file(path)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        return False
    if parent and parent in text:
        return False
    if marker and marker in text:
        return False
    return True


def files_holding_basename(config_dir: Path, base: str) -> list[Path]:
    """Regular files under *config_dir*, at any depth, whose bytes hold *base*.

    A stat or read failure raises. A directory that cannot be walked raises.
    An empty list means no file holds the name.
    """
    needle = base.encode("utf-8")
    found: list[Path] = []
    root = Path(config_dir)
    try:
        walker = os.walk(root)
    except OSError as exc:
        raise HarnessError(f"cannot walk config dir {root}: {exc}") from exc
    for dirpath, _dirnames, filenames in walker:
        for filename in filenames:
            path = Path(dirpath) / filename
            try:
                info = path.lstat()
            except OSError as exc:
                raise HarnessError(f"cannot stat {path}: {exc}") from exc
            if not stat.S_ISREG(info.st_mode):
                continue
            try:
                blob = path.read_bytes()
            except OSError as exc:
                raise HarnessError(f"cannot read {path}: {exc}") from exc
            if needle in blob:
                found.append(path)
    return found


def assert_private_ledger_snapshot(
    config_dir: Path,
    *,
    base: str,
    parent: str,
    marker: str,
) -> list[Path]:
    """Every file that holds this session's base name is owner-only.

    That includes a file in a subdirectory. The body holds neither the
    document text nor the full path. A top-level settings file does not
    have to change.
    """
    holders = files_holding_basename(config_dir, base)
    assert holders, (
        f"no file under the config directory holds the session base name {base!r}"
    )
    for path in holders:
        assert ledger_file_is_private(path, parent=parent, marker=marker), (
            f"record {path} is group/other-readable or holds the "
            "parent directory or the document marker"
        )
    nested = Path(config_dir) / fresh_name(".dir")
    nested.mkdir()
    control = nested / fresh_name(".control")
    control.write_text(base + "\n" + marker + "\n" + parent, encoding="utf-8")
    os.chmod(control, 0o640)
    assert not ledger_file_is_private(control, parent=parent, marker=marker), (
        "privacy observer accepted a group-readable file that contains the marker"
    )
    control.unlink()
    nested.rmdir()
    print(
        f"[F05] {len(holders)} record file(s) holding {base!r} are owner-only",
        flush=True,
    )
    return holders


def own_nudge_section(text: str, name: str, others: Sequence[str]) -> str:
    """The nudge line that belongs to *name* (one stated line per flagged file)."""
    head = f"prosecheck: {name} "
    lines = [line for line in nudge_lines(text) if line.startswith(head)]
    assert len(lines) == 1, (
        f"expected one nudge line for {name!r}, got {len(lines)}; text={text[:600]!r}"
    )
    return lines[0]


def status_remainder(
    text: str,
    name: str,
    measured: Measured,
    *,
    session_id: str | None = None,
    directory: str | None = None,
    others: Sequence[str] = (),
) -> str:
    """Flagged bit of the scored row for *name*, read from its stated clause.

    Returns ``"flagged"`` (state word flagged), ``"under"`` (state word
    under), or ``"none"`` (no labels clause).
    """
    row = require_scored_row(text, name, measured)
    return row.status or "none"


def find_exact(target: int) -> Measured:
    """A scored file at exactly *target*, confidence other than none.

    Pads stay long enough that a short-document floor cannot skip the
    target. A score of 40 also needs a detector label, because the
    strict envelope must name one. The score is whatever the detector
    returns; the search only chooses text.
    """
    seen: list[Measured] = []

    def take(text: str) -> Measured | None:
        measured = measure_text(text)
        seen.append(measured)
        if (
            measured.score == target
            and measured.confidence != "none"
            and measured.confidence in CONFIDENCE_LABELS
            and (measured.labels or target < 40)
        ):
            return measured
        return None

    def climb(text: str, steps: int) -> Measured | None:
        current = text
        for _ in range(steps):
            current += " delve"
            hit = take(current)
            if hit:
                return hit
            if seen[-1].score > target:
                return None
        return None

    bases = [pad_human(n) for n in (180, 260, 340)]
    for base in bases:
        hit = take(base)
        if hit:
            return hit
        if seen[-1].score < target and seen[-1].confidence != "none":
            hit = climb(base, 30)
            if hit:
                return hit

    overs = [
        item
        for item in seen
        if item.score > target and item.confidence != "none"
    ]
    overs.sort(key=lambda item: item.score)
    if overs:
        current = overs[0].text
        for _ in range(16):
            current = current + " " + pad_human(24)
            hit = take(current)
            if hit:
                return hit
            if seen[-1].score < target and seen[-1].confidence != "none":
                hit = climb(current, 16)
                if hit:
                    return hit
                break
    scores = sorted({item.score for item in seen})
    print(f"[F05] exact-{target} missed scores={scores}", flush=True)
    raise HarnessError(
        f"fixture cannot measure a file whose score is exactly {target} "
        f"with confidence other than none; saw scores {scores}"
    )


def prose_exact(target: int) -> Measured:
    key = f"exact:{target}"
    if key not in _CACHE:
        _CACHE[key] = find_exact(target)
        item = _CACHE[key]
        if item.confidence == "none":
            raise HarnessError(
                f"exact score {target} was measured at confidence none"
            )
    return _CACHE[key]


def prose_above_20_not_40() -> Measured:
    """A file scored above 20 and below 40, confidence other than none.

    Exactly 40 is a separate case. This one is the full-level unflagged
    score that strict still flags.
    """
    key = "above20-below40"
    if key in _CACHE:
        return _CACHE[key]
    light = prose_for_band("light tells")
    if 20 < light.score < 40 and light.confidence != "none":
        _CACHE[key] = light
        return light
    for target in (25, 30, 35, 21, 39):
        try:
            item = find_exact(target)
        except HarnessError:
            continue
        if 20 < item.score < 40 and item.confidence != "none":
            _CACHE[key] = item
            return item
    raise HarnessError(
        "fixture cannot measure a file scored above 20 and below 40 "
        "with confidence other than none"
    )


def prose_dense() -> Measured:
    key = "dense"
    if key not in _CACHE:
        chosen: Measured | None = None
        for text in (AI_REGISTER, AI_REGISTER + "\n" + SHORT_SLOP):
            measured = measure_text(text)
            if measured.score > 40 and measured.confidence != "none" and len(measured.labels) > 5:
                chosen = measured
                break
        if chosen is None:
            raise HarnessError(
                "fixture cannot measure a dense file scored above 40 with "
                "more than five detector labels and confidence other than none"
            )
        _CACHE[key] = chosen
    return _CACHE[key]


def prose_for_band(band: str) -> Measured:
    """A scored file whose detector band is exactly *band*.

    Clean may sit at or under 20. The three bands above 40 must be
    flaggable: confidence other than none, and at least one label.
    """
    if band not in BAND_RANGES:
        raise HarnessError(f"unknown band {band!r}")
    key = f"band:{band}"
    if key in _CACHE:
        return _CACHE[key]
    lo, hi = BAND_RANGES[band]
    flagged = lo > 40
    human = pad_human(120)
    slop = AI_REGISTER.strip()
    seen: list[Measured] = []

    def consider(text: str) -> Measured | None:
        measured = measure_text(text)
        seen.append(measured)
        if not lo <= measured.score <= hi:
            return None
        if measured.confidence not in CONFIDENCE_LABELS:
            return None
        if flagged and (measured.confidence == "none" or not measured.labels):
            return None
        if band == "clean" and measured.confidence == "none":
            return None
        return measured

    # Varied punctuation and the humanized sample sit in clean when the
    # padded human paragraphs do not. Stacking catalogue vocabulary on the
    # register sample is what pushes a heavy file into pervasive.
    varied = (
        "The lock opened at six; the tide was already on the wall. "
        "I counted fourteen boats (three of them empty) and wrote the numbers in the margin. "
        "Then the rain started. Not a drizzle, a proper downpour that turned the lane to paste. "
        "We waited. The kettle clicked. Someone swore, quietly, and someone else laughed. "
        "By noon the sky had torn open again, and the road crew was back with the same dented thermos they carry every Thursday. "
    )
    vocab = (
        "Additionally this crucial tapestry is a pivotal vibrant testament underscoring the intricate interplay. "
        "It garners support and bolsters results while fostering growth and showcasing work and emphasizing an enduring enhancement. "
        "Teams leverage tools and utilize methods and facilitate change and encompass a holistic paradigm. "
        "The transformative unprecedented myriad plethora is robust and seamlessly navigates as leaders embark on the journey. "
        "The multifaceted realm elevates teams and empowers residents and unlocks value, capturing the essence of the landscape. "
    )
    probes = [
        varied * 4,
        HUMANIZED_CODING,
        human,
        SHORT_FACTUAL,
        pad_human(40),
        SHORT_SLOP,
        slop,
        slop + "\n" + slop,
        SHORT_SLOP + "\n" + slop,
        slop + "\n" + (vocab * 6),
    ]
    slop_bits = [part for part in re.split(r"(?<=[.!?])\s+", slop) if part.strip()]
    blended = human
    for bit in slop_bits:
        blended = blended + " " + bit
        probes.append(blended)
    for words in (30, 80, 160, 280):
        probes.append(slop + "\n" + pad_human(words))
        probes.append(SHORT_SLOP + "\n" + pad_human(words))

    chosen: Measured | None = None
    for text in probes:
        chosen = consider(text)
        if chosen is not None:
            break
    if chosen is None:
        scores = sorted({item.score for item in seen})
        raise HarnessError(
            f"fixture cannot measure a {band!r} file"
            + (" above the default threshold" if flagged else "")
            + f"; saw scores {scores}"
        )
    _CACHE[key] = chosen
    return chosen


def prose_under() -> Measured:
    key = "under"
    if key not in _CACHE:
        chosen: Measured | None = None
        for text in (
            pad_human(80) + " They delve into the parish records after the flood.",
            pad_human(120),
            SHORT_FACTUAL + " " + pad_human(40),
        ):
            measured = measure_text(text)
            if (
                measured.score <= 40
                and measured.confidence != "none"
                and measured.labels
            ):
                chosen = measured
                break
        if chosen is None:
            raise HarnessError(
                "fixture cannot measure an unflagged file at or under 40 "
                "with a detector label and confidence other than none"
            )
        _CACHE[key] = chosen
    return _CACHE[key]


def prose_none() -> Measured:
    """Under 40 words, two decisive families, score above 40, confidence none."""
    key = "none"
    if key not in _CACHE:
        candidates = (
            "Send the draft to [Your Name] before noon. "
            "See https://example.com/post?utm_source=chatgpt.com for the note.",
            "I hope this helps. As of my last training the lock still opens at dawn.",
            "I hope this helps. As of my last training, see "
            "https://example.com/post?utm_source=chatgpt.com today.",
        )
        chosen: Measured | None = None
        for text in candidates:
            measured = measure_text(text)
            words = len(re.findall(r"\S+", text))
            if (
                words < 40
                and measured.score > 40
                and measured.confidence == "none"
                and measured.labels
            ):
                chosen = measured
                break
        if chosen is None:
            raise HarnessError(
                "fixture cannot measure a below-40-word file scored above 40 "
                "at confidence none"
            )
        _CACHE[key] = chosen
    return _CACHE[key]


def similar_clean(target_chars: int) -> Measured:
    words = max(50, target_chars // 6)
    measured = measure_text(pad_human(words))
    if measured.score > 40 or measured.confidence == "none":
        raise HarnessError(
            "similar-length human prose is not an unflagged scored file: "
            f"score={measured.score} confidence={measured.confidence!r}"
        )
    return measured


def repeat_to(text: str, n: int) -> str:
    if n < 1:
        raise HarnessError("repeat length must be positive")
    unit = text if text else "bridge"
    reps = (n // len(unit)) + 1
    return (unit * reps)[:n]


def _walk_integers(obj: Any) -> list[int]:
    found: list[int] = []

    def walk(value: Any) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, int):
            found.append(value)
            return
        if isinstance(value, Mapping):
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    walk(obj)
    return found


def _dense_report_text() -> str:
    dense = prose_dense()
    result = scan_stdin(dense.text)
    if result.returncode != 0:
        raise HarnessError(
            f"detector did not score the dense sample: exit={result.returncode}"
        )
    return result.stdout_text


def pinned_score(score: int) -> tuple[Measured, str]:
    """A real detector report whose score is set to *score*, for the guard.

    The report is this detector's own JSON for the dense sample with
    ``_metrics.ai_tell_score`` set to *score* and ``_metrics.ai_tell_band``
    set to the band named for that score. Confidence and labels stay as the
    detector reported them. The guard reads it through an interpreter
    stand-in, so its threshold behaviour is observed at an exact score.
    """
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
        raise HarnessError(f"pinned score must be an integer 0-100, got {score!r}")
    dense = prose_dense()
    pinned = copy.deepcopy(detector_report(_dense_report_text()))
    band = band_named_for_score(score)
    pinned[METRICS_KEY][SCORE_KEY] = score
    pinned[METRICS_KEY][BAND_KEY] = band
    text = json.dumps(pinned, ensure_ascii=False)
    measured = _from_report(dense.text, detector_report(text, source=f"pinned:{score}"))
    if measured.confidence == "none" or not measured.labels:
        raise HarnessError("dense sample has confidence none or no labels")
    print(f"[F05] pinned score={score} band={band!r} conf={measured.confidence!r}", flush=True)
    return measured, text


def fire_pinned(ws, report_text: str, **fire_kwargs: Any) -> tuple[RunResult, str]:
    """Fire the guard while the interpreter it launches prints *report_text*."""
    with interpreter_standin(ws, stdout=report_text, exit_code=0) as stand:
        started = stand.invocations()
        fire_kwargs.setdefault("timeout", 20)
        outcome = fire_tool(ws, env_updates=stand.env_updates, **fire_kwargs)
        if stand.invocations() <= started:
            raise HarnessError("stand-in was not on the detector path")
    return outcome


def missing_score_arms(leftover: int) -> tuple[str, str, tuple[int, ...]]:
    """A successful detector report with ``_metrics.ai_tell_score`` removed.

    Both strings are that same JSON report. The second also carries
    *leftover* on a ``_metrics`` member that is not the score (other
    ``_metrics`` members are free). The third value is every integer still
    on that second report. Findings stay in place.
    """
    if isinstance(leftover, bool) or not isinstance(leftover, int):
        raise HarnessError(f"leftover must be an integer, got {leftover!r}")
    result = scan_stdin(SHORT_SLOP)
    if result.returncode != 0:
        raise HarnessError(
            "detector did not produce a successful report to strip: "
            f"exit={result.returncode} stderr={result.stderr_text[:400]!r}"
        )
    report = detector_report(result.stdout_text)
    bare = copy.deepcopy(report)
    assert SCORE_KEY in bare[METRICS_KEY]
    del bare[METRICS_KEY][SCORE_KEY]
    if not [key for key in bare if key != METRICS_KEY]:
        raise HarnessError("short slop report has no findings")
    counted = copy.deepcopy(bare)
    free_key = next(
        key for key in ("n", "leftover", "count_not_score") if key not in counted[METRICS_KEY]
    )
    counted[METRICS_KEY][free_key] = leftover
    leftovers = tuple(dict.fromkeys(_walk_integers(counted)))
    if leftover not in leftovers:
        raise HarnessError("planted non-score integer is not on the report")
    without_score = json.dumps(bare, ensure_ascii=False)
    with_leftover = json.dumps(counted, ensure_ascii=False)
    print(
        f"[F05] missing-score report leftover={leftover} integers={leftovers}",
        flush=True,
    )
    return without_score, with_leftover, leftovers


@contextmanager
def interpreter_standin(
    ws,
    *,
    sleep_s: float | None = None,
    stdout: str | None = None,
    exit_code: int = 0,
    forward: bool = False,
) -> Iterator[Standin]:
    """Plant python / python3 / py ahead of PATH. Prove one probe invocation first."""
    root = Path(tempfile.mkdtemp(prefix="f05-py-"))
    log = root / "invocations.log"
    log.write_text("", encoding="utf-8")
    real = shlex.quote(sys.executable)
    log_q = shlex.quote(str(log))
    lines = [
        "#!/bin/sh",
        f"log={log_q}",
        'if [ -z "$log" ]; then echo "stand-in log unset" >&2; exit 97; fi',
        'echo invoked >> "$log"',
        'if [ "$F05_STUB_PROBE" = "1" ]; then exit 0; fi',
    ]
    if sleep_s is not None:
        lines.append(f"sleep {sleep_s}")
    if forward:
        lines.append(f"exec {real} \"$@\"")
    elif stdout is not None:
        lines.append(f"printf '%s' {shlex.quote(stdout)}")
        lines.append(f"exit {int(exit_code)}")
    else:
        lines.append(f"exit {int(exit_code)}")
    script = "\n".join(lines) + "\n"
    for name in ("python", "python3", "py"):
        path = root / name
        path.write_text(script, encoding="utf-8")
        path.chmod(0o755)
    base = ws.env.get("PATH", os.environ.get("PATH", ""))
    updates = {
        "PATH": str(root) + os.pathsep + base,
        "F05_STUB_LOG": str(log),
    }
    stand = Standin(root=root, log=log, env_updates=updates)
    probe_env = dict(os.environ)
    probe_env.update(updates)
    probe_env["F05_STUB_PROBE"] = "1"
    probe = subprocess.run(
        [str(root / "python3"), "-c", "print('probe')"],
        env=probe_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=5,
        check=False,
    )
    try:
        if probe.returncode != 0 or stand.invocations() < 1:
            raise HarnessError(
                "interpreter stand-in did not run under a direct probe: "
                f"exit={probe.returncode} stderr={probe.stderr!r} "
                f"invocations={stand.invocations()}"
            )
        print(
            f"[F05] stand-in probe ok invocations={stand.invocations()} "
            f"sleep={sleep_s} forward={forward} exit={exit_code}",
            flush=True,
        )
        yield stand
    finally:
        shutil.rmtree(root, ignore_errors=True)


def updates_without_interpreters() -> dict[str, str]:
    root = Path(tempfile.mkdtemp(prefix="f05-nopy-"))
    path = str(root)
    for name in ("python", "python3", "py"):
        found = shutil.which(name, path=path)
        if found:
            raise HarnessError(
                f"{name} is still visible on a path that should lack interpreters: {found}"
            )
    return {"PATH": path}


def relocated_plugin_root() -> tuple[Path, dict[str, str]]:
    """A temp install root whose detector file is the real script, via a symlink."""
    root = Path(tempfile.mkdtemp(prefix="f05-root-"))
    scripts = root / "scripts"
    scripts.mkdir()
    real = detector_script()
    (scripts / "detect.py").symlink_to(real)
    return root, {ENV_PLUGIN_ROOT: str(root)}


def basename_absent(text: str, base: str) -> None:
    assert base not in text, f"{base!r} was recorded; text={text[:400]!r}"


def config_omits(paths: Sequence[Path], base: str) -> None:
    for path in paths:
        try:
            blob = path.read_bytes()
        except OSError as exc:
            raise HarnessError(f"cannot read {path}: {exc}") from exc
        assert base.encode("utf-8") not in blob, (
            f"{base!r} was written into config file {path.name}"
        )


def elapsed_call(fn):
    start = time.monotonic()
    value = fn()
    return time.monotonic() - start, value


_CHILD_SITES = '''\
import os
import socket

_log = os.environ.get("_F05_CONNECT_LOG", "")

def _rec(kind, dest):
    if not _log:
        return
    try:
        with open(_log, "a", encoding="utf-8") as handle:
            handle.write(kind + " " + str(dest) + "\\n")
    except OSError:
        pass

_rec("child-start", os.getpid())
_socket_connect = socket.socket.connect

def _connect(self, address):
    _rec("connect", address)
    return _socket_connect(self, address)

socket.socket.connect = _connect
_create_connection = socket.create_connection

def _creating(*args, **kwargs):
    _rec("create_connection", args[0] if args else "")
    return _create_connection(*args, **kwargs)

socket.create_connection = _creating
'''

_NODE_PRELOAD = r"""
"use strict";
const fs = require("fs");
const logp = process.env._F05_CONNECT_LOG;
function rec(kind, dest) {
  if (!logp) return;
  try { fs.appendFileSync(logp, kind + " " + String(dest) + "\n"); } catch (e) {}
}
function wrap(obj, name) {
  if (!obj || typeof obj[name] !== "function") return;
  const orig = obj[name];
  obj[name] = function (...args) {
    rec(name, args[0] && (args[0].host || args[0].hostname || args[0].path || args[0]));
    return orig.apply(this, args);
  };
}
try {
  const net = require("net");
  wrap(net.Socket.prototype, "connect");
  wrap(net, "connect");
  wrap(net, "createConnection");
} catch (e) {}
try {
  const http = require("http");
  wrap(http, "request");
  wrap(http, "get");
} catch (e) {}
try {
  const https = require("https");
  wrap(https, "request");
  wrap(https, "get");
} catch (e) {}
"""


def _strace_follows_children(strace: str, node: str, probe_log: Path) -> bool:
    probe = subprocess.run(
        [
            strace,
            "-f",
            "-qq",
            "-e",
            "trace=connect",
            "-o",
            str(probe_log),
            node,
            "-e",
            "process.exit(0)",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5,
        check=False,
    )
    return probe.returncode == 0


@contextmanager
def guard_connect_observer() -> Iterator[Any]:
    """Count connects from the hook and from the detector child.

    A Python child is visible because its startup imports a socket wrapper.
    When strace can follow forks, its connect trace is counted too. If a
    detector-style child connect is not visible, this raises instead of
    reporting zero.
    """
    tmp = Path(tempfile.mkdtemp(prefix="f05-net-"))
    log = tmp / "connects.log"
    log.write_text("", encoding="utf-8")
    (tmp / "sitecustomize.py").write_text(_CHILD_SITES, encoding="utf-8")
    preload = tmp / "preload.js"
    preload.write_text(_NODE_PRELOAD, encoding="utf-8")
    try:
        real_node = node_executable()
    except FileNotFoundError as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        raise HarnessError(f"cannot observe hook connects: {exc}") from exc

    strace = shutil.which("strace")
    strace_dir = tmp / "strace"
    strace_dir.mkdir()
    use_strace = False
    if strace:
        try:
            use_strace = _strace_follows_children(strace, real_node, tmp / "probe.log")
        except (OSError, subprocess.TimeoutExpired):
            use_strace = False
    wrapper = tmp / "node"
    if use_strace:
        wrapper.write_text(
            "#!/bin/sh\n"
            f"dir={shlex.quote(str(strace_dir))}\n"
            'n=0\n'
            'while [ -e "$dir/call.$n" ]; do n=$((n+1)); done\n'
            f"exec {shlex.quote(strace)} -f -qq -e trace=connect "
            '-o "$dir/call.$n" '
            f"{shlex.quote(real_node)} \"$@\"\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
        node_path = f"{tmp}{os.pathsep}{os.environ.get('PATH', '')}"
    else:
        node_path = os.environ.get("PATH", "")

    base_pythonpath = os.environ.get("PYTHONPATH", "")
    pythonpath = str(tmp) if not base_pythonpath else str(tmp) + os.pathsep + base_pythonpath
    env_updates = {
        "PATH": node_path,
        "PYTHONPATH": pythonpath,
        "NODE_OPTIONS": f"--require={preload}",
        "_F05_CONNECT_LOG": str(log),
    }

    def _log_text() -> str:
        try:
            return log.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise HarnessError(
                f"connect observer cannot read its log: {exc}"
            ) from exc

    def _strace_inet() -> int:
        if not use_strace:
            return 0
        total = 0
        try:
            names = list(strace_dir.iterdir())
        except OSError as exc:
            raise HarnessError(
                f"connect observer cannot list strace logs: {exc}"
            ) from exc
        for path in names:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                raise HarnessError(
                    f"connect observer cannot read {path.name}: {exc}"
                ) from exc
            total += sum(
                1
                for line in text.splitlines()
                if "AF_INET" in line or "AF_INET6" in line
            )
        return total

    class Observer:
        def __init__(self) -> None:
            # Class-body assignment does not close over the function local.
            self.env_updates = env_updates

        @property
        def n_connects(self) -> int:
            body = _log_text()
            logged = sum(
                1
                for line in body.splitlines()
                if line.startswith("connect ") or line.startswith("create_connection ")
                or line.startswith("request ") or line.startswith("get ")
            )
            return logged + _strace_inet()

        @property
        def child_starts(self) -> int:
            body = _log_text()
            return sum(1 for line in body.splitlines() if line.startswith("child-start "))

        def prove_child_visible(self) -> None:
            """A Python child that connects must move the count. Blind is a failure."""
            before = self.n_connects
            starts = self.child_starts
            env = dict(os.environ)
            env.update(self.env_updates)
            child = (
                "import socket\n"
                "s = socket.socket()\n"
                "s.settimeout(0.4)\n"
                "try:\n"
                "    s.connect(('127.0.0.1', 9))\n"
                "except OSError:\n"
                "    pass\n"
            )
            launch = (
                "require('child_process').spawnSync("
                f"{json.dumps(sys.executable)}, ['-c', {json.dumps(child)}], "
                "{env: process.env, timeout: 4000});"
            )
            completed = subprocess.run(
                [real_node, "-e", launch],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=8,
                check=False,
            )
            if self.child_starts <= starts or self.n_connects <= before:
                raise HarnessError(
                    "connect observer cannot see a detector-style child; "
                    "refusing to report a zero connect count. "
                    f"exit={completed.returncode} "
                    f"stderr={completed.stderr[:300]!r} "
                    f"starts={self.child_starts} connects={self.n_connects}"
                )

    observer = Observer()
    try:
        observer.prove_child_visible()
        yield observer
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


__all__ = [
    "COVERAGE_NOTE",
    "FIX_ASK",
    "Nudge",
    "ShowRow",
    "block_reply",
    "detector_report",
    "nudge_bases",
    "parse_nudge",
    "require_scored_row",
    "show_row",
    "show_rows_for",
    "ARCHIVE_KB_FIGURES",
    "BETWEEN_CAPS",
    "DECIMAL_512_KB",
    "Measured",
    "OVER_BOTH_4MB",
    "OVER_BOTH_4MB_OTHER",
    "OVER_BOTH_512",
    "PLAIN_KB",
    "PRODUCT_NAME",
    "Standin",
    "WINDOW_GROUPED",
    "WINDOW_PLAIN",
    "assert_private_ledger_snapshot",
    "basename_absent",
    "changed_config_files",
    "config_omits",
    "elapsed_call",
    "find_exact",
    "fire_tool",
    "fresh_name",
    "guard_connect_observer",
    "interpreter_standin",
    "ledger_file_is_private",
    "measure_path",
    "measure_text",
    "missing_score_arms",
    "pinned_score",
    "fire_pinned",
    "nudge_text",
    "phrase_for_band",
    "plant_prose",
    "prose_dense",
    "prose_exact",
    "prose_for_band",
    "prose_none",
    "prose_under",
    "relocated_plugin_root",
    "repeat_to",
    "require_flagged_envelope",
    "require_silent",
    "show_text",
    "similar_clean",
    "status_remainder",
    "snapshot_config",
    "standalone_int_present",
    "updates_without_interpreters",
]
