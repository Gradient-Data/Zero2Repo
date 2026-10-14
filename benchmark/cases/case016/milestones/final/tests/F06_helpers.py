# feature: F06
"""Observation helpers for the /prosecheck command router.

Every reply is read through the form the Interface Contract states for
it: the block decision's ``reason``, then the labelled lines and the
exact phrases the Contract fixes for each subcommand. Nothing here
induces a spelling from a live reply, compares leftover words, or
scrapes integers out of free text.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from _harness import HarnessError, mode_flag_path, repo_root
from F01_helpers import HUMANIZED_CODING, scan_stdin
from F02_helpers import runtime_token
from F04_helpers import (
    delivered_text,
    require_full_scoring,
    standalone_word_present,
)
from F05_helpers import (
    LEVEL_WORDS,
    Measured,
    Standin,
    measure_text,
    pad_human,
    phrase_for_band,
    prose_dense,
    prose_under,
)

PLAIN = "/prosecheck"
NAMED = "/prosecheck:prosecheck"
SUBCOMMANDS: tuple[str, ...] = (
    "lite",
    "full",
    "strict",
    "off",
    "on",
    "status",
    "show",
    "check",
    "doctor",
    "stats",
    "init",
    "help",
)
HELP_LIST: tuple[str, ...] = tuple(word for word in SUBCOMMANDS if word != "help")
PROSE_GLOBS: tuple[str, ...] = (
    "*.md",
    "*.mdx",
    "*.markdown",
    "*.txt",
    "*.rst",
    "*.tex",
    "*.org",
    "*.adoc",
)
CODE_GLOBS: tuple[str, ...] = ("*.py", "*.js", "*.ts", "*.json")
DAY = 24 * 3600
NOT_AUTHOR = "was written by"
# One artifact at a time. A path that carries both a leading @ and quotes
# is at-double or at-single: the @ comes first, then one pair of quotes.
# Quotes that wrap the @ are not a spelling the lines require.
CHECK_PATH_ARTIFACTS: tuple[str, ...] = (
    "bare",
    "double",
    "single",
    "at",
    "at-double",
    "at-single",
)
# Contract: the scan window written with or without a thousands comma.
WINDOW_SPELLINGS: tuple[str, ...] = ("262,144", "262144")
# Contract: doctor success marker.
OK_MARK = "[OK]"
# Contract: shipped host-menu command documents (plugin-root relative).
MENU_DOCUMENTS: tuple[str, ...] = (
    "install/prosecheck-command.md",
    "commands/prosecheck.md",
)
HOOK_PHRASES: tuple[str, ...] = (
    "reads clean",
    "reads mostly clean",
    "reads with some AI tells",
    "reads with heavy AI tells",
    "reads with pervasive AI tells",
)
BAND_NAMES: tuple[str, ...] = (
    "clean",
    "light tells",
    "mixed",
    "heavy tells",
    "pervasive tells",
)


# ---------------------------------------------------------------------------
# Integers and phrases (Contract forms)
# ---------------------------------------------------------------------------

_STANDALONE_INT = re.compile(r"(?<![A-Za-z0-9])(\d+)(?![A-Za-z0-9])")
_GROUPED_INT = r"\d{1,3}(?:,\d{3})+|\d+"


def standalone_integers(text: str) -> list[int]:
    """Every standalone run of digits (not glued to a letter or digit)."""
    return [int(m.group(1)) for m in _STANDALONE_INT.finditer(text)]


def shows_integer(text: str, value: int) -> bool:
    """*value* as a standalone integer, or with a thousands comma."""
    if int(value) in standalone_integers(text):
        return True
    grouped = f"{int(value):,}"
    return grouped != str(value) and re.search(
        rf"(?<![A-Za-z0-9,]){re.escape(grouped)}(?![A-Za-z0-9]|,\d)", text
    ) is not None


def no_score_integers(text: str) -> None:
    """Contract: the reply carries no standalone integer from 0 through 100."""
    found = [n for n in standalone_integers(text) if 0 <= n <= 100]
    if found:
        raise AssertionError(
            f"reply still has a 0-100 integer {found}; text={text[:400]!r}"
        )


def already_for(text: str, filename: str) -> bool:
    """Contract: a reply line carrying the word ``already`` and naming *filename*."""
    return any(
        has_phrase(line, "already") and filename in line for line in text.splitlines()
    )


def has_phrase(text: str, phrase: str) -> bool:
    """Case-insensitive phrase presence, bounded by non-word characters."""
    return re.search(
        rf"(?<![A-Za-z0-9]){re.escape(phrase)}(?![A-Za-z0-9])", text, re.IGNORECASE
    ) is not None


def window_named(text: str) -> bool:
    return any(spelling in text for spelling in WINDOW_SPELLINGS)


def first_window_only(text: str) -> bool:
    """Contract coverage clause: ``first <window> characters only``."""
    return re.search(
        r"first (?:262,144|262144) characters only", text
    ) is not None


def without_paths(text: str, *paths: object) -> str:
    """*text* with each given path and its base name removed (exact strings)."""
    tokens: list[str] = []
    for path in paths:
        tokens.append(str(path))
        tokens.append(Path(str(path)).name)
    out = text
    for token in sorted({t for t in tokens if t}, key=len, reverse=True):
        out = out.replace(token, " ")
    return out


def require_no_score(reply: str, *paths: object) -> None:
    """No 0-100 integer once the paths the reply names are removed."""
    no_score_integers(without_paths(reply, *paths))


# ---------------------------------------------------------------------------
# Detector facts (stated detector shell: findings keyed <N>_<slug>)
# ---------------------------------------------------------------------------


def label_hits(text: str) -> dict[str, int]:
    """Detector label -> hit count, read from the stated JSON report."""
    result = scan_stdin(text)
    if result.returncode != 0:
        raise HarnessError(
            "detector did not score the label probe: "
            f"exit={result.returncode} stderr={result.stderr_text[:300]!r}"
        )
    report = json.loads(result.stdout_text)
    hits: dict[str, int] = {}
    for key, value in report.items():
        if key == "_metrics" or not isinstance(value, Mapping):
            continue
        label = value.get("label")
        if isinstance(label, str) and label.strip():
            hits[label] = int(value["count"])
    return hits


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

_CHECK_HEAD = re.compile(
    r"^(?P<base>.+?) - (?P<phrase>reads[^()]*?) "
    r"\(score (?P<score>\d+)/100, band: (?P<band>[^)]+)\)$"
)
_TELL = re.compile(r"(?P<label>.+?) \(x(?P<count>\d+)\)$")


@dataclass(frozen=True)
class CheckSummary:
    base: str
    phrase: str
    score: int
    band: str
    confidence: str
    reason: str
    coverage: str | None
    tells: tuple[tuple[str, int], ...]
    tells_none: bool
    lines: tuple[str, ...]


def parse_check_summary(text: str) -> CheckSummary:
    """The scored check reply, line by line as the Contract states it."""
    lines = tuple(line.rstrip() for line in text.splitlines() if line.strip())
    heads = [m for m in (_CHECK_HEAD.match(line) for line in lines) if m]
    assert len(heads) == 1, f"check reply has no single summary line; text={text[:500]!r}"
    head = heads[0]
    conf = [line for line in lines if line.startswith("confidence: ")]
    assert len(conf) == 1, f"check reply has no single confidence line; text={text[:500]!r}"
    word, _sep, reason = conf[0][len("confidence: "):].partition(" - ")
    coverage = [line for line in lines if line.startswith("coverage:")]
    assert len(coverage) <= 1, coverage
    tells_lines = [line for line in lines if line.startswith("tells: ")]
    assert len(tells_lines) == 1, f"check reply has no single tells line; text={text[:500]!r}"
    body = tells_lines[0][len("tells: "):]
    tells: list[tuple[str, int]] = []
    none = body == "none"
    if not none:
        for piece in body.split("; "):
            m = _TELL.match(piece)
            assert m, f"tells entry is not '<label> (x<count>)': {piece!r}"
            tells.append((m.group("label"), int(m.group("count"))))
    return CheckSummary(
        base=head.group("base"),
        phrase=head.group("phrase"),
        score=int(head.group("score")),
        band=head.group("band"),
        confidence=word.strip(),
        reason=reason,
        coverage=coverage[0] if coverage else None,
        tells=tuple(tells),
        tells_none=none,
        lines=lines,
    )


def require_check_summary(
    text: str,
    measured: Measured,
    base: str,
    *,
    reason: bool,
) -> CheckSummary:
    """The scored check reply matches the detector on this file."""
    summary = parse_check_summary(text)
    assert summary.base.endswith(base), (summary.base, base)
    assert summary.phrase == phrase_for_band(measured.band), summary
    assert summary.band == measured.band, summary
    assert summary.score == measured.score, (summary.score, measured.score)
    assert summary.confidence == measured.confidence, summary
    assert NOT_AUTHOR not in text
    assert any(has_phrase(line, "report only") for line in summary.lines), text
    if reason:
        if not measured.reason:
            raise HarnessError("reason arm has no detector reason to require")
        assert summary.reason == measured.reason, (summary.reason, measured.reason)
    return summary


CHECK_NOT_SCORED_PHRASES: tuple[str, ...] = (
    "not a file",
    "cannot read",
    "no readable text",
    "detector unavailable",
    "no report",
)


def check_over_cap_figure(text: str) -> int | None:
    """The kilobyte figure in ``over <KB> KB``, or None."""
    m = re.search(r"(?i)(?<![A-Za-z])over (\d+) KB(?![A-Za-z])", text)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


def doctor_lines(text: str) -> tuple[str, list[str], str]:
    """Title (first non-empty line), check lines, closer (last non-empty line)."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 6:
        raise AssertionError(f"doctor reply is not title + 4 checks + closer: {text[:500]!r}")
    return lines[0], lines[1:-1], lines[-1]


def is_success(line: str) -> bool:
    return OK_MARK in line


_MODE_LINE = re.compile(r"(?<![A-Za-z])mode: (lite|full|strict|off)(?![A-Za-z])")


def doctor_check_kind(line: str) -> str | None:
    """Which of the four checks *line* is, by its stated phrase."""
    lowered = line.lower()
    kinds = []
    if _MODE_LINE.search(line):
        kinds.append("mode")
    has_python = re.search(r"(?<![a-z])python(?![a-z])", lowered) is not None
    if has_python:
        kinds.append("python")
    elif re.search(r"(?<![a-z])detector(?![a-z])", lowered):
        kinds.append("detector")
    if re.search(r"(?<![a-z])settings(?![a-z])", lowered):
        kinds.append("settings")
    if len(kinds) != 1:
        return None
    return kinds[0]


def doctor_checks(text: str) -> dict[str, str]:
    """The four check lines keyed mode / detector / python / settings."""
    _title, checks, _closer = doctor_lines(text)
    assert len(checks) == 4, checks
    found: dict[str, str] = {}
    for line in checks:
        kind = doctor_check_kind(line)
        assert kind is not None and kind not in found, (kind, line, checks)
        found[kind] = line
    return found


def mode_line_level(line: str) -> str | None:
    m = _MODE_LINE.search(line)
    return m.group(1) if m else None


def require_four_healthy_checks(text: str, level: str) -> dict[str, str]:
    checks = doctor_checks(text)
    for kind, line in checks.items():
        assert is_success(line), (kind, line)
    assert mode_line_level(checks["mode"]) == level, checks["mode"]
    _t, _c, closer = doctor_lines(text)
    assert OK_MARK not in closer, closer
    return checks


def _names_command(text: str, word: str) -> bool:
    return any(
        re.search(rf"{re.escape(f)} {word}(?![A-Za-z:-])", text)
        for f in (PLAIN, NAMED)
    )


def healthy_closer_ok(closer: str, form: str) -> None:
    assert has_phrase(closer, "512 KB"), closer
    assert re.search(r"(?<![0-9])4 ?MB(?![A-Za-z])", closer), closer
    assert window_named(closer), closer
    assert re.search(rf"{re.escape(form)} show(?![A-Za-z:-])", closer), closer
    assert f"{PLAIN} doctor" not in closer, closer


def fault_closer_ok(closer: str) -> None:
    assert f"{PLAIN} doctor" in closer, closer
    assert has_phrase(closer, "fix"), closer
    assert not _names_command(closer, "show"), closer
    assert not _names_command(closer, "on"), closer


def off_closer_ok(closer: str, form: str) -> None:
    assert re.search(rf"{re.escape(form)} on(?![A-Za-z:-])", closer), closer
    assert has_phrase(closer, "scored"), closer
    assert f"{PLAIN} doctor" not in closer, closer
    assert not has_phrase(closer, "not re-scored"), closer


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def show_row(text: str, name: str) -> str:
    """The one row line ``<name> - <body>``; returns the body."""
    rows = [
        line.strip()[len(name) + 3:]
        for line in text.splitlines()
        if line.strip().startswith(name + " - ")
    ]
    assert len(rows) == 1, f"show has no single row for {name!r}; text={text[:500]!r}"
    return rows[0]


def row_order(text: str, names: Sequence[str]) -> list[str]:
    """*names* in the order their rows appear."""
    order: list[tuple[int, str]] = []
    for index, line in enumerate(text.splitlines()):
        for name in names:
            if line.strip().startswith(name + " - "):
                order.append((index, name))
    return [name for _i, name in sorted(order)]


_SCORED_ROW = re.compile(
    r"^(?P<phrase>reads[^()]*?) \(score (?P<score>\d+)/(?P<band>[a-z ]+?)"
    r"(?P<cov>, first (?:262,144|262144) characters only)?\)"
    r"(?: - (?P<state>[^:]*): (?P<labels>.+))?$"
)


@dataclass(frozen=True)
class ScoredRow:
    phrase: str
    score: int
    band: str
    truncated: bool
    clause: str | None  # "flagged", "under", or None
    labels: tuple[str, ...]


def _row_state(state: str) -> str | None:
    if re.search(r"(?i)(?<![a-z])flagged(?![a-z])", state):
        return "flagged"
    if re.search(r"(?i)(?<![a-z])under(?![a-z])", state):
        return "under"
    return None


def parse_scored_row(body: str) -> ScoredRow:
    m = _SCORED_ROW.match(body)
    assert m, f"show row is not a scored row: {body!r}"
    labels = tuple(m.group("labels").split("; ")) if m.group("labels") else ()
    clause = None
    if m.group("labels"):
        clause = _row_state(m.group("state"))
        assert clause, f"show row clause names neither flagged nor under: {body!r}"
    return ScoredRow(
        phrase=m.group("phrase"),
        score=int(m.group("score")),
        band=m.group("band"),
        truncated=bool(m.group("cov")),
        clause=clause,
        labels=labels,
    )


def require_scored_row_shows(body: str, measured: Measured) -> ScoredRow:
    row = parse_scored_row(body)
    assert row.phrase == phrase_for_band(measured.band), row
    assert row.score == measured.score, (row.score, measured.score)
    assert row.band == measured.band, row
    assert NOT_AUTHOR not in body
    return row


def size_skip_figures(body: str) -> tuple[int, ...]:
    """Every ``<n> KB`` figure of a ``not scored: `` row; empty when it has none."""
    if not body.lower().startswith("not scored: "):
        return ()
    return tuple(int(n) for n in re.findall(r"(?i)(?<![0-9])(\d+) KB(?![A-Za-z])", body))


def is_binary_row(body: str) -> bool:
    return "not re-scored" in body.lower() and "not scored:" not in body.lower()


def failed_row_reason(body: str) -> str | None:
    if not body.lower().startswith("not scored: ") or size_skip_figures(body):
        return None
    return body[len("not scored: "):]


def require_empty_show(text: str, absent: str = "") -> None:
    assert ".docx" in text and ".pdf" in text, text
    assert has_phrase(text, "nothing scored yet"), text
    no_score_integers(text)
    if absent:
        assert absent not in text


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

_STATS_LABELS = {
    "turns": "assistant turns",
    "output": "output tokens",
    "cache": "cache-read input tokens",
}


def stats_values(text: str) -> dict[str, int]:
    """Labelled stats quantities present in the reply (each label at most once)."""
    out: dict[str, int] = {}
    for key, label in _STATS_LABELS.items():
        hits = re.findall(
            rf"(?m)^\s*{re.escape(label)}: ({_GROUPED_INT})\s*$", text
        )
        assert len(hits) <= 1, (label, hits, text)
        if hits:
            out[key] = int(hits[0].replace(",", ""))
    return out


def stats_session_score(text: str) -> int | None:
    hits = re.findall(r"session prose ai_tell_score: (\d+)(?!\d)", text)
    assert len(hits) <= 1, (hits, text)
    return int(hits[0]) if hits else None


def stats_level(text: str) -> str | None:
    hits = re.findall(r"(?<![A-Za-z])level: (lite|full|strict|off)(?![A-Za-z])", text)
    assert len(hits) <= 1, (hits, text)
    return hits[0] if hits else None


# ---------------------------------------------------------------------------
# unknown word, init, export
# ---------------------------------------------------------------------------


def reports_word_as_unknown(text: str, word: str) -> bool:
    """One line carries the word ``unknown`` and the typed word."""
    return any(
        standalone_word_present(line, "unknown") and word in line
        for line in text.splitlines()
    )


def resolution_lines(text: str) -> list[str]:
    """Export lines naming CLAUDE_PLUGIN_ROOT, skills and plugins together."""
    return [
        line
        for line in text.splitlines()
        if "CLAUDE_PLUGIN_ROOT" in line
        and standalone_word_present(line, "skills")
        and standalone_word_present(line, "plugins")
    ]


def require_strict_clean_band_apart(strict_text: str, lite_text: str) -> None:
    """Strict names the band ``clean`` on a line the lite export lacks.

    The cleanup switch spelling ``--clean`` is not that word.
    """
    lite_lines = set(lite_text.splitlines())
    hits = [
        line
        for line in strict_text.splitlines()
        if line not in lite_lines
        and standalone_word_present(line.replace("--clean", " "), "clean")
    ]
    assert hits, "strict export does not name the clean band apart from --clean and lite"


def states_prose_only_scope(text: str) -> bool:
    return has_phrase(text, "prose deliverables only")


def names_post_write_detector(text: str) -> bool:
    """Contract: the Cursor rule names neither detect.py nor any detect* word."""
    return "detect.py" in text or re.search(r"(?i)(?<![a-z])detect", text) is not None


def command_registrations(root: Path | None = None) -> list[tuple[Path, str]]:
    """The shipped host-menu command documents at the stated locations."""
    base = root if root is not None else repo_root()
    found: list[tuple[Path, str]] = []
    for rel in MENU_DOCUMENTS:
        path = base / rel
        if not path.is_file():
            continue
        body = _command_document_body(path.read_text(encoding="utf-8"))
        assert body is not None, f"{rel} is not a command document"
        found.append((path, body))
    if not found:
        raise AssertionError(
            f"no shipped command document at {MENU_DOCUMENTS} under {base}"
        )
    return found


def _submit_prompt(
    ws,
    prompt: str,
    *,
    session_id: str | None = None,
    transcript_path: str | None = None,
    env_updates: Mapping[str, str | None] | None = None,
    cwd: str | None = None,
):
    """One prompt-submit. Host fields are only how the payload is sent."""
    payload: dict[str, Any] = {"prompt": prompt}
    if session_id is not None:
        payload["session_id"] = session_id
    if transcript_path is not None:
        payload["transcript_path"] = transcript_path
    return ws.invoke_hook(
        "prompt-submit",
        payload=payload,
        env_updates=env_updates,
        cwd=cwd,
    )



def prompt_submission(
    ws,
    prompt: str,
    *,
    session_id: str | None = None,
    transcript_path: str | None = None,
    env_updates: Mapping[str, str | None] | None = None,
    cwd: str | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """JSON object, if the body is one, and the joined delivery text.

    Empty stdout is silence: no object. A failed exit raises. A body that
    is not a JSON object is not a decision; the joined text is still
    returned so a reminder written as plain text stays observable.
    """
    result = _submit_prompt(
        ws,
        prompt,
        session_id=session_id,
        transcript_path=transcript_path,
        env_updates=env_updates,
        cwd=cwd,
    )
    text = delivered_text(result)
    raw = result.stdout_text
    if raw == "":
        return None, ""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None, text
    if isinstance(obj, dict):
        return obj, text
    return None, text



def block_reason(obj: dict[str, Any] | None, joined: str) -> str:
    """Reason of a block decision. That reason is the command reply.

    Joining every string in the body is not this reply. A decision that
    is not a block is not a command reply. Text that is not the reason
    is not the reply the rest of an assertion may read.
    """
    if not isinstance(obj, dict):
        raise AssertionError(
            "command hook did not return a decision object; "
            f"text={joined[:400]!r}"
        )
    decision = obj.get("decision")
    if decision != "block":
        raise AssertionError(
            "command hook did not block the prompt; "
            f"decision={decision!r} text={joined[:400]!r}"
        )
    reason = obj.get("reason")
    if not isinstance(reason, str):
        raise AssertionError(
            "block decision reason is not the command reply; "
            f"text={joined[:400]!r}"
        )
    return reason



def command_reply(
    ws,
    prompt: str,
    *,
    session_id: str | None = None,
    transcript_path: str | None = None,
    env_updates: Mapping[str, str | None] | None = None,
    cwd: str | None = None,
) -> str:
    """Command reply for one command identity.

    The identity is the prompt: either form of a subcommand, a bare
    invocation, an unknown word, check with or without a path, or an
    entire-prompt phrase that stores off. The reply is the reason of a
    block decision. A non-blocking envelope fails. A block whose reason
    is not the text the caller reads fails. Joining every string in the
    body does not satisfy this read. A prompt that is not a command
    stays on ``prompt_submission``.
    """
    obj, joined = prompt_submission(
        ws,
        prompt,
        session_id=session_id,
        transcript_path=transcript_path,
        env_updates=env_updates,
        cwd=cwd,
    )
    return block_reason(obj, joined)



def level_bearing_line(text: str, level: str) -> str:
    """The single line of a joined status delivery that names *level*."""
    if "\n" in level or level not in LEVEL_WORDS:
        raise HarnessError(f"not a stored level: {level!r}")
    lines = [
        line
        for line in text.splitlines()
        if standalone_word_present(line, level)
    ]
    if len(lines) != 1:
        raise HarnessError(
            f"status delivery does not name {level!r} on exactly one line; "
            f"lines={lines!r} text={text[:400]!r}"
        )
    return lines[0]



def assert_one_level_line(observed: tuple[str, str], level: str) -> None:
    """The status report is one line and names only this stored level.

    *observed* is the command reply and the joined delivery. The reply is
    the report. A block decision joined beside that reply is not another
    line of the report. The reply itself must be a single line. The joined
    delivery must still name this level on exactly one line and no other
    stored level.
    """
    if (
        not isinstance(observed, tuple)
        or len(observed) != 2
        or not all(isinstance(part, str) for part in observed)
    ):
        raise HarnessError(
            "status observation must be the command reply and the joined delivery"
        )
    reply, joined = observed
    if "\n" in level or level not in LEVEL_WORDS:
        raise HarnessError(f"not a stored level: {level!r}")
    if len(reply.splitlines()) != 1:
        raise HarnessError(
            f"status report is not one line; reply={reply[:400]!r}"
        )
    level_bearing_line(joined, level)
    present = [word for word in LEVEL_WORDS if standalone_word_present(joined, word)]
    if present != [level]:
        raise HarnessError(
            f"status names {present}, not only {level!r}; text={joined[:400]!r}"
        )
    reply_present = [
        word for word in LEVEL_WORDS if standalone_word_present(reply, word)
    ]
    if reply_present != [level]:
        raise HarnessError(
            f"status report names {reply_present}, not only {level!r}; "
            f"reply={reply[:400]!r}"
        )



def standalone_count(text: str, word: str) -> int:
    if not word:
        raise HarnessError("standalone count has no word")
    pattern = rf"(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])"
    return len(re.findall(pattern, text))



def fresh_word() -> str:
    """A word that is not one of the twelve subcommands and not a substring of them."""
    for _ in range(20):
        word = "qw" + runtime_token("z")
        if any(word in cmd or cmd in word for cmd in SUBCOMMANDS):
            continue
        if word.lower() in {"on", "off", "help"}:
            continue
        return word
    raise HarnessError("could not mint a word outside the subcommand list")



def many_label_prose() -> Measured:
    """Scored prose with strictly more than eight detector labels."""
    measured = prose_dense()
    if len(measured.labels) > 8:
        return measured
    extra = measured.text + "\n" + measured.text
    again = measure_text(extra)
    if len(again.labels) <= 8:
        raise HarnessError(
            "fixture does not fire more than eight labels; "
            f"dense={len(measured.labels)} doubled={len(again.labels)}"
        )
    return again



def zero_label_prose() -> Measured:
    measured = measure_text(HUMANIZED_CODING)
    if measured.labels:
        measured = measure_text(pad_human(80))
    if measured.labels:
        raise HarnessError(
            "fixture still has detector labels; "
            f"labels={measured.labels!r}"
        )
    return measured



def scored_prose() -> Measured:
    """Ordinary scored prose for tests that only need a readable file.

    Unlike :func:`zero_label_prose` it does not require that no pattern
    fired, so a test about another reply does not hinge on that.
    """
    return measure_text(pad_human(80))



def high_confidence_prose() -> Measured:
    measured = measure_text(pad_human(320))
    if measured.confidence != "high":
        measured = measure_text(pad_human(480))
    if measured.confidence != "high":
        raise HarnessError(
            f"fixture confidence is {measured.confidence!r}, not high"
        )
    return measured



def prose_with_confidence_reason() -> Measured:
    """Short prose whose detector confidence carries a reason.

    High confidence is the arm with no reason. A sample that comes back
    high, or with an empty reason, is not this fixture.
    """
    measured = prose_under()
    if measured.confidence == "high" or not measured.reason:
        measured = measure_text(pad_human(80))
    if measured.confidence == "high" or not measured.reason:
        raise HarnessError(
            "fixture has no non-high confidence with a reason to require; "
            f"confidence={measured.confidence!r} reason={measured.reason!r}"
        )
    return measured



def check_path_argument(path: Path, artifact: str) -> str:
    """The check argument for one path spelling.

    bare is the path. double and single are one surrounding pair of
    quotes. at is one leading @. at-double and at-single put that @
    before the quotes. Each spelling is separate.
    """
    text = os.fspath(path)
    if artifact == "bare":
        return text
    if artifact == "double":
        return f'"{text}"'
    if artifact == "single":
        return f"'{text}'"
    if artifact == "at":
        return f"@{text}"
    if artifact == "at-double":
        return f'@"{text}"'
    if artifact == "at-single":
        return f"@'{text}'"
    raise HarnessError(f"unknown check path artifact: {artifact!r}")



def doctor_check_lines(text: str) -> list[str]:
    """The four-or-so check lines between the title and the closer.

    The title is the first non-empty line and the closer is the last.
    The check lines are the non-empty lines between those two. A line is
    not selected by dropping success markers, so the closer is never one
    of these lines, and neither is the title. A reply with no room for
    both a title and a closer is not a health check.
    """
    if not isinstance(text, str):
        raise HarnessError(f"doctor reply is not text: {text!r}")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        raise HarnessError(
            f"doctor reply has no title and closer; text={text[:400]!r}"
        )
    return lines[1:-1]



def normalised(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()



def strip_tokens(text: str, tokens: Sequence[object]) -> str:
    out = text
    ordered = sorted(
        {str(token) for token in tokens if token is not None and str(token) != ""},
        key=len,
        reverse=True,
    )
    for token in ordered:
        if token.isdigit():
            out = re.sub(rf"(?<!\d){re.escape(token)}(?!\d)", " ", out)
        elif re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]*", token):
            out = re.sub(
                rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])",
                " ",
                out,
            )
        else:
            out = out.replace(token, " ")
    return normalised(out)



def star_patterns(text: str) -> list[str]:
    found: list[str] = []
    # A glob list may be space-, comma-, or bracket-delimited.
    for raw in re.findall(r"[^\s,\[\]]*\*[^\s,\[\]]*", text):
        token = raw.strip("`'\"),]")
        if token:
            found.append(token)
    return found



def prose_glob_of(pattern: str) -> str | None:
    if "{" in pattern or "}" in pattern:
        return None
    for glob in sorted(PROSE_GLOBS, key=len, reverse=True):
        if pattern == glob or pattern.endswith(glob):
            return glob
    return None



def cursor_rule_front_matter(text: str) -> str | None:
    """Interior of the closed leading front-matter block, or None if absent.

    The block opens on the first line and closes on a later line that is
    only the delimiter, the same block the body helper strips. None means
    that block is absent: the file does not open with it, or the opening
    never closes. That absence is the observation, not a failed read.
    Globs written only after the block are not part of this text. An
    empty string is a closed block with no interior.
    """
    if not isinstance(text, str):
        raise HarnessError("cursor rule is not text")
    if not text.startswith("---"):
        return None
    newline = text.find("\n")
    if newline < 0 or text[:newline].strip() != "---":
        return None
    lines = text[newline + 1 :].splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.strip() == "---":
            return "".join(lines[:index])
    return None



def require_prose_glob_front_matter(text: str) -> None:
    """The front matter is the list that limits the rule to the prose globs.

    That list is the star tokens inside the closed leading block: the
    eight prose globs, and not ``*.py``, ``*.js``, ``*.ts``, or ``*.json``.
    Star tokens collected from the whole file, or from a body that lists
    the prose globs with no front matter, are not this list. A brace is
    not one of the eight. The body is a separate check.
    """
    if not isinstance(text, str) or not text.strip():
        raise HarnessError("cursor rule has no text")
    matter = cursor_rule_front_matter(text)
    assert matter is not None, "cursor rule has no front matter"
    patterns = star_patterns(matter)
    assert len(patterns) == 8, (
        "front matter does not list eight prose globs; "
        f"patterns={patterns!r}"
    )
    found = {prose_glob_of(pattern) for pattern in patterns}
    assert found == set(PROSE_GLOBS), (
        f"front matter glob list is {found!r}, not the prose globs"
    )
    for pattern in patterns:
        assert prose_glob_of(pattern) is not None, pattern
    for code in CODE_GLOBS:
        assert code not in matter, f"front matter includes {code}"



def age_file(path: Path, *, days: float, youth: float = 0.0) -> None:
    """Set mtime to *days* ago, then shift it by *youth* seconds.

    Positive *youth* moves the stamp toward now. Negative *youth* moves it
    further into the past, so an age can sit just past a whole-day boundary.
    It does not assert the file was removed.
    """
    stamp = time.time() - days * DAY + youth
    try:
        os.utime(path, (stamp, stamp))
    except OSError as exc:
        raise HarnessError(f"cannot set mtime on {path}: {exc}") from exc



SEVEN_DAYS_MS = 7 * 24 * 3600 * 1000


@contextmanager
def shared_sweep_clock() -> Iterator[tuple[int, dict[str, str]]]:
    """One millisecond clock for a ledger stamp and the sweep that reads it.

    The yielded env freezes ``Date.now`` and a no-argument ``Date`` at that
    clock for the hook process. The yielded integer is the same instant, so
    an mtime can be placed at a signed offset from the seven-day cutoff the
    sweep computes. A missing or non-numeric clock fails the preload rather
    than falling through to the wall clock.
    """
    clock_ms = int(time.time() * 1000)
    tmp = Path(tempfile.mkdtemp(prefix="f06-sweep-clock-"))
    preload = tmp / "clock.js"
    preload.write_text(
        "const fixed = Number(process.env.F06_SWEEP_CLOCK_MS);\n"
        "if (!Number.isFinite(fixed)) {\n"
        "  throw new Error('F06_SWEEP_CLOCK_MS is missing');\n"
        "}\n"
        "const NativeDate = Date;\n"
        "function FrozenDate(...args) {\n"
        "  if (args.length === 0) return new NativeDate(fixed);\n"
        "  return new NativeDate(...args);\n"
        "}\n"
        "FrozenDate.now = function () { return fixed; };\n"
        "FrozenDate.parse = NativeDate.parse;\n"
        "FrozenDate.UTC = NativeDate.UTC;\n"
        "FrozenDate.prototype = NativeDate.prototype;\n"
        "global.Date = FrozenDate;\n",
        encoding="utf-8",
    )
    env = {
        "NODE_OPTIONS": f"--require={preload}",
        "F06_SWEEP_CLOCK_MS": str(clock_ms),
    }
    try:
        yield clock_ms, env
    finally:
        shutil.rmtree(tmp, ignore_errors=True)



def stamp_cutoff_offset(path: Path, clock_ms: int, offset_ms: int) -> None:
    """Place *path*'s mtime at a signed offset from the seven-day cutoff.

    The cutoff is *clock_ms* minus seven days, the same subtraction the
    sweep performs on this clock. A negative *offset_ms* is younger than
    seven days. Zero is exactly seven days. A positive *offset_ms* is older.
    """
    if not isinstance(offset_ms, int):
        raise HarnessError(f"offset_ms must be an int, got {offset_ms!r}")
    mtime_ms = (clock_ms - SEVEN_DAYS_MS) - offset_ms
    try:
        os.utime(path, ns=(mtime_ms * 1_000_000, mtime_ms * 1_000_000))
    except OSError as exc:
        raise HarnessError(f"cannot set mtime on {path}: {exc}") from exc



def clear_stored_level(ws) -> None:
    """Drop a stored level so the next read is one this document did not set.

    A missing flag is the default level. An earlier document's flag must
    not remain. A failure to remove the flag is not that default.
    """
    flag = mode_flag_path(ws.config_dir)
    try:
        if flag.is_symlink() or flag.exists():
            flag.unlink()
    except OSError as exc:
        raise HarnessError(f"cannot clear stored level at {flag}: {exc}") from exc
    if flag.exists() or flag.is_symlink():
        raise HarnessError(f"stored level still present at {flag}")



def invoke_shipped_command(ws, arguments: str, *, body: str, **kwargs) -> str:
    """Submit one command document's own body to the prompt-submit router.

    The host inserts the user's arguments only into the argument slot
    that body already contains. A body with no slot is submitted
    unchanged, so those arguments are not in the prompt the router sees.
    The document is not spawned: the router only ever sees that prompt.
    """
    if not isinstance(body, str) or body.strip() == "":
        raise HarnessError("shipped command document has no body to submit")
    placeholder = "$ARGUMENTS"
    prompt = body.replace(placeholder, arguments) if placeholder in body else body
    return command_reply(ws, prompt, **kwargs)



def _command_document_body(text: str) -> str | None:
    """The prompt template when *text* is a host-menu command document.

    Optional front matter is a leading closed block. The body that
    remains is the template only when that body itself begins with the
    slash command. A later line of a different file is not this body.
    """
    if not isinstance(text, str):
        raise HarnessError("command document is not text")
    body = _without_front_matter(text).strip()
    # The namespaced spelling starts with the shorter command, so it is
    # recognised first. A longer token that merely begins with the
    # command is not the template.
    for command in (NAMED, PLAIN):
        if body == command:
            return body
        if body.startswith(command) and body[len(command)].isspace():
            return body
    return None



def _without_front_matter(text: str) -> str:
    """Text after a leading closed front-matter block.

    The block opens on the first line and closes on a later line that is
    only the delimiter. A rule later in the file is not front matter.
    An unclosed opening is not front matter either: the text stays whole.
    """
    if not text.startswith("---"):
        return text
    newline = text.find("\n")
    if newline < 0 or text[:newline].strip() != "---":
        return text
    lines = text[newline + 1 :].splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.strip() == "---":
            return "".join(lines[index + 1 :])
    return text



def help_entry_line(text: str, command: str) -> str:
    """The one help line that lists *command*.

    ``off`` and ``on`` may share a line. A later use of the word inside a
    description is not another listing. Missing or repeated listings raise.
    """
    if command not in HELP_LIST:
        raise HarnessError(f"not a help-list command: {command!r}")
    hits: list[str] = []
    for raw in text.splitlines():
        if PLAIN not in raw:
            continue
        listed: list[str] = []
        # Each non-namespaced command on the line lists the words right after
        # it (Contract: a line that contains /prosecheck followed by the word;
        # off and on may share one line, as "off | on" or "off | /prosecheck on").
        for occurrence in re.finditer(re.escape(PLAIN) + r"(?![\w:])", raw):
            after = raw[occurrence.end():]
            for word in re.findall(r"[A-Za-z]+", after):
                lowered = word.lower()
                if lowered in HELP_LIST:
                    listed.append(lowered)
                    continue
                break
        if command in listed:
            hits.append(raw)
    if len(hits) != 1:
        raise HarnessError(
            f"help does not list {command} on exactly one line; "
            f"hits={hits!r} text={text[:500]!r}"
        )
    return hits[0]



def help_listed_in_command_slot(line: str) -> bool:
    """True when *line* lists help in the subcommand slot.

    The line starts with the non-namespaced command after optional leading
    whitespace. Command words are the tokens immediately after that prefix,
    the same slot the other subcommands occupy, and they stop when the
    description starts. help in that slot is a listing. A later use of the
    word, including the help command inside a description, is not.
    """
    body = line.lstrip()
    if body.startswith(NAMED) or not body.startswith(PLAIN):
        return False
    rest = body[len(PLAIN) :]
    if rest[:1].isalnum() or rest[:1] == "_":
        return False
    for word in re.findall(r"[A-Za-z]+", rest):
        lowered = word.lower()
        if lowered == "help":
            return True
        if lowered in HELP_LIST:
            continue
        break
    return False



def require_outside_text_in_place(text: str, outside: str) -> None:
    """Text that already sat outside the contract section is still those bytes.

    *outside* is the text that was in the file before init, including the
    newline the caller wrote. The export must still begin with that text:
    the section is appended, and the earlier bytes stay where they were.
    An empty export, or outside text with no bytes, is a failure to
    observe, not an unchanged file.
    """
    if not isinstance(outside, str) or outside == "":
        raise HarnessError("outside text has no bytes")
    if not isinstance(text, str) or text == "":
        raise HarnessError("export has no text to compare with the outside bytes")
    try:
        outside_bytes = outside.encode("utf-8")
        text_bytes = text.encode("utf-8")
    except UnicodeError as exc:
        raise HarnessError(f"export text is not utf-8: {exc}") from exc
    assert text_bytes.startswith(outside_bytes), (
        "text outside the contract section is not the original bytes"
    )



def require_same_rule_bytes(path: Path, shipped: bytes) -> None:
    """The Cursor rule file is the shipped copy init already wrote.

    A missing path is a failure, not an unchanged rule. Bytes that differ
    from that copy are a different file. An unreadable path is a failure
    too: the helper has no bytes to compare.
    """
    if not isinstance(shipped, (bytes, bytearray)) or not bytes(shipped):
        raise HarnessError("shipped cursor rule has no bytes")
    if not path.is_file():
        raise HarnessError(f"cursor rule was not written: {path}")
    try:
        found = path.read_bytes()
    except OSError as exc:
        raise HarnessError(f"cursor rule could not be read: {path}: {exc}") from exc
    assert found == bytes(shipped)



def require_contract_section(text: str, *, word: str, count: int) -> None:
    """One copy of the full-level writing contract.

    The banned-vocabulary list, the score-40 target, and clean or light
    tells are that contract. *count* is how many times *word* stood alone
    in the first export, and *word* is one that export actually contained.
    A missing contract has a lower count. A second copy of the section
    has a higher count. An empty file is not the contract.
    """
    if count < 1:
        raise HarnessError("first export did not contain the contract word")
    if not word or not str(text).strip():
        raise HarnessError("contract section check has no export text")
    require_full_scoring(text)
    found = standalone_count(text, word)
    assert found == count, (
        f"contract section count for {word!r} is {found}, first export had {count}"
    )



def cursor_rule_body(text: str) -> str:
    """The Cursor rule after a closed front-matter block.

    A file with no front matter is all body. Front matter that does not
    close, or that leaves no body, is not an observation.
    """
    if not isinstance(text, str) or not text.strip():
        raise HarnessError("cursor rule has no text")
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    if len(parts) < 3 or not parts[2].strip():
        raise HarnessError("cursor rule front matter does not leave a body")
    return parts[2]



def node_kept_without_interpreters() -> dict[str, str]:
    """A PATH with no Python, and a node symlink so the hook can still start.

    The sealed no-interpreter path is empty. The hook process is started
    by name, so node has to remain visible or the probe cannot run.
    """
    from F05_helpers import updates_without_interpreters

    updates = updates_without_interpreters()
    node = shutil.which("node")
    if not node:
        raise HarnessError("node is not on PATH before the no-python arm")
    link = Path(updates["PATH"]) / "node"
    link.symlink_to(node)
    if shutil.which("python3", path=updates["PATH"]) or shutil.which(
        "python", path=updates["PATH"]
    ):
        raise HarnessError("python is still visible after interpreters were removed")
    return updates



@contextmanager
def emitted_failure_standin(ws, text: str) -> Iterator[Standin]:
    """Plant interpreters that emit *text* and then exit non-zero.

    The failure is that text. An empty body is not this case, and the
    exit status is not the failure. A probe that does not run raises.
    """
    if text is None or not str(text).strip():
        raise HarnessError("a stated failure has no text the detector emitted")
    root = Path(tempfile.mkdtemp(prefix="f06-fail-"))
    log = root / "invocations.log"
    log.write_text("", encoding="utf-8")
    script = "\n".join(
        [
            "#!/bin/sh",
            f"log={shlex.quote(str(log))}",
            'if [ -z "$log" ]; then echo "stand-in log unset" >&2; exit 97; fi',
            'echo invoked >> "$log"',
            'if [ "$F05_STUB_PROBE" = "1" ]; then exit 0; fi',
            f"printf '%s\\n' {shlex.quote(str(text))} >&2",
            "exit 1",
        ]
    ) + "\n"
    for name in ("python", "python3", "py"):
        path = root / name
        path.write_text(script, encoding="utf-8")
        path.chmod(0o755)
    base = ws.env.get("PATH", os.environ.get("PATH", ""))
    updates = {"PATH": str(root) + os.pathsep + base}
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
                "emitted-failure stand-in did not run under a direct probe: "
                f"exit={probe.returncode} stderr={probe.stderr!r} "
                f"invocations={stand.invocations()}"
            )
        yield stand
    finally:
        shutil.rmtree(root, ignore_errors=True)



