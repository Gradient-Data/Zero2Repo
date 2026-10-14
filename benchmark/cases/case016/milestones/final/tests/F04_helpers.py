# feature: F04
"""Observation helpers for the always-on writing contract (FP-04).

New names for this slice only. Sealed F00–F03 helpers are imported, not
copied. Every hook observation goes through ``_harness.invoke_hook``.
"""

from __future__ import annotations

import hashlib
import json
import os
import pwd
import re
import secrets
import shlex
import shutil
import subprocess
import tempfile
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from _harness import (
    HarnessError,
    RunResult,
    detector_script,
    mode_flag_path,
    node_executable,
)
from F02_helpers import runtime_token, standalone_int_present

# Level words the PRD names as the stored operating level (L26, L198, L216).
ON_LEVELS: tuple[str, ...] = ("off", "lite", "full", "strict")

# L200 banned-vocabulary list as standalone words. "landscape" / "journey"
# without the parenthetical "abstract". "game-changer" hyphenated.
BANNED_VOCABULARY: tuple[str, ...] = (
    "delve",
    "tapestry",
    "pivotal",
    "crucial",
    "leverage",
    "robust",
    "seamless",
    "foster",
    "underscore",
    "showcase",
    "landscape",
    "journey",
    "realm",
    "multifaceted",
    "holistic",
    "testament",
    "vibrant",
    "comprehensive",
    "plethora",
    "myriad",
    "boast",
    "elevate",
    "empower",
    "unlock",
    "game-changer",
    "supercharge",
    "genuinely",
    "fascinating",
    "nuanced",
)

CONTEXT_ONLY: frozenset[str] = frozenset({"comprehensive", "boast"})

# Named scoring targets the contract may carry: 20, 40, clean, light tells.
C_SCORING: tuple[Any, ...] = (20, 40, "clean", "light tells")

WELCOME_COMMANDS: tuple[str, ...] = (
    "/prosecheck doctor",
    "/prosecheck check",
    "/prosecheck off",
    "/prosecheck help",
)

# Named welcome quantities (L203 / L216). The archive cap is the 4 MB
# quantity, not a bare digit 4, so 4 is not in this tuple.
WELCOME_INTS: tuple[int, ...] = (71, 512, 262144)

# "4 MB" / "4MB": the named archive cap. Spacing between the digit and the
# unit is not graded. A standalone 4 is not this cap.
_ARCHIVE_MB_CAP = re.compile(
    r"(?<![A-Za-z0-9])4\s*MB(?![A-Za-z0-9])",
    flags=re.IGNORECASE,
)

_FRAME_SEED = secrets.token_hex(6)

# Interface Contract, `scripts/detect.py`: the cleanup switch is spelled
# exactly `--clean`. It is read as that literal, never discovered from usage.
CLEANUP_SWITCH = "--clean"

# Interface Contract, hook stdout envelopes: prompt-submit (ordinary prompt)
# and subagent-start answer with one JSON object
# {"hookSpecificOutput": {"hookEventName": <event>, "additionalContext": <text>}}.
REMINDER_EVENT = "UserPromptSubmit"
SUBAGENT_EVENT = "SubagentStart"

# Interface Contract, finding members: key `<N>_<slug>`.
_FINDING_KEY = re.compile(r"^[1-9][0-9]*_")


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def _tokenize(text: str) -> list[str]:
    folded = _fold(text)
    if not folded:
        return []
    return folded.split(" ")


def _standalone_pattern(token: str) -> str:
    escaped = re.escape(token)
    return rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])"


def standalone_word_present(text: str, word: str) -> bool:
    return re.search(_standalone_pattern(word), str(text), flags=re.IGNORECASE) is not None


def named_int_present(text: str, value: int) -> bool:
    """Named quantity, accepting optional comma grouping (L203: 262,144)."""
    if standalone_int_present(text, value):
        return True
    grouped = f"{value:,}"
    return re.search(_standalone_pattern(grouped), str(text)) is not None


def without_machine_paths(text: str, *paths: str) -> str:
    """Contract text with the exact known machine paths removed (L212).

    The Interface Contract declares the detector path free in a live
    contract, so that exact string (and the harness's own planted paths)
    is not read. No pattern-based path stripping: only these exact strings.
    """
    known: list[str] = [p for p in paths if p]
    try:
        known.append(str(Path.cwd().resolve()))
    except OSError as exc:
        raise HarnessError(f"cannot read the working directory: {exc}") from exc
    plugin = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin:
        known.append(plugin)
    try:
        known.append(str(detector_script()))
    except FileNotFoundError:
        # The path string can still sit in the contract when the file is
        # absent. Absence of the file is not absence of a score target.
        pass
    # Longer paths first so a directory prefix is removed before a fragment.
    ordered = sorted({p for p in known if p}, key=len, reverse=True)
    out = strip_hook_covariates(text, *ordered)
    return _fold(out)


def named_score_present(text: str, value: int, *paths: str) -> bool:
    """Whether *value* is still a standalone integer after machine paths go."""
    return named_int_present(without_machine_paths(text, *paths), value)


def _strip_standalone(text: str, token: str | int) -> str:
    if isinstance(token, int):
        grouped = f"{token:,}"
        out = re.sub(_standalone_pattern(grouped), " ", str(text))
        return re.sub(rf"(?<!\d){token}(?!\d)", " ", out)
    if token == "light tells":
        return re.sub(
            r"(?i)(?<![A-Za-z])light\s+tells(?![A-Za-z])",
            " ",
            str(text),
        )
    return re.sub(_standalone_pattern(str(token)), " ", str(text), flags=re.IGNORECASE)


def _walk_strings(value: Any) -> list[str]:
    found: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, str):
            found.append(item)
        elif isinstance(item, Mapping):
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return found


def _walk_keys(value: Any) -> list[str]:
    found: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                found.append(str(key))
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return found




def workspace_paths(ws) -> tuple[str, ...]:
    """Paths and user-name tokens planted by the harness, not product output."""
    found: list[str] = [
        str(ws.path),
        str(ws.home),
        str(ws.config_dir),
        str(ws.root),
        str(ws.home.name),
        str(ws.path.name),
    ]
    try:
        script = detector_script(root=ws.root)
        found.append(str(script))
        found.append(script.name)
        found.append(str(script.parent))
    except FileNotFoundError:
        pass
    env = getattr(ws, "env", {}) or {}
    for key in ("USER", "LOGNAME", "USERNAME", "HOME"):
        val = env.get(key) or os.environ.get(key)
        if val:
            found.append(str(val))
            found.append(Path(str(val)).name)
    return tuple(dict.fromkeys(p for p in found if p))


def require_hook_success(result: RunResult) -> None:
    """Non-success on these hooks is unexpected (L210). Empty stdout is not."""
    if result.returncode != 0:
        raise HarnessError(
            f"hook must succeed so the host session continues; "
            f"exit={result.returncode} stderr={result.stderr_text!r} "
            f"stdout={result.stdout_text[:500]!r}"
        )


def joined_stdout(result: RunResult) -> str:
    """Join string values when stdout is JSON; otherwise the raw text.

    Consume the walk inside this helper. Does not grade the exit status.
    Empty stdout is an empty delivery, not a crashed probe.
    """
    text = result.stdout_text
    if text == "":
        return ""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(obj, (dict, list)):
        return "\n".join(_walk_strings(obj))
    if isinstance(obj, str):
        return obj
    return text


def delivered_text(result: RunResult) -> str:
    """Joined stdout after a successful exit.

    A successful exit is graded only for malformed JSON and an unreadable
    mode flag. Callers that are not those arms use ``joined_stdout``.
    """
    require_hook_success(result)
    return joined_stdout(result)


def hook_context(result: RunResult, event: str) -> str:
    """``hookSpecificOutput.additionalContext`` of the stated envelope.

    Interface Contract: stdout is one JSON object
    ``{"hookSpecificOutput": {"hookEventName": <event>, "additionalContext": <text>}}``.
    Read directly at that path; other members are not read.
    """
    require_hook_success(result)
    text = result.stdout_text
    assert text != "", f"{event} hook stdout is empty; expected the JSON envelope"
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"{event} hook stdout is not one JSON object: {exc}; text={text[:500]!r}"
        ) from exc
    assert isinstance(obj, dict), (
        f"{event} hook JSON is {type(obj).__name__}, not an object"
    )
    inner = obj.get("hookSpecificOutput")
    assert isinstance(inner, dict), (
        f"{event} envelope has no hookSpecificOutput object; obj={obj!r:.500}"
    )
    assert inner.get("hookEventName") == event, (
        f"envelope hookEventName is {inner.get('hookEventName')!r}, not {event!r}"
    )
    context = inner.get("additionalContext")
    assert isinstance(context, str), (
        f"{event} envelope additionalContext is not a string: {context!r:.200}"
    )
    return context


def subagent_contract(result: RunResult) -> str:
    """The contract carried in the subagent-start envelope (L207).

    Raw text on stdout is not delivery; the context is read at
    ``hookSpecificOutput.additionalContext`` with event ``SubagentStart``.
    """
    return hook_context(result, SUBAGENT_EVENT)


def reminder_text(result: RunResult) -> str:
    """The ordinary-prompt reminder: ``additionalContext`` of the
    ``UserPromptSubmit`` envelope."""
    return hook_context(result, REMINDER_EVENT)


def session_text(result: RunResult) -> str:
    """Session-start delivery: stdout as plain text after a successful exit.

    Interface Contract: session-start prints plain text (the one-time
    welcome, when shown, then the writing contract), not a JSON envelope.
    """
    require_hook_success(result)
    return result.stdout_text


def session_start(
    ws,
    payload: Mapping[str, Any] | None = None,
    stdin: bytes | str | None = None,
    env_updates: Mapping[str, str | None] | None = None,
) -> RunResult:
    return ws.invoke_hook(
        "session-start",
        payload=payload,
        stdin=stdin,
        env_updates=env_updates,
    )


def subagent_start(
    ws,
    payload: Mapping[str, Any] | None = None,
    stdin: bytes | str | None = None,
    env_updates: Mapping[str, str | None] | None = None,
) -> RunResult:
    return ws.invoke_hook(
        "subagent-start",
        payload=payload,
        stdin=stdin,
        env_updates=env_updates,
    )


def user_prompt(
    ws,
    prompt: str,
    env_updates: Mapping[str, str | None] | None = None,
) -> tuple[RunResult, dict[str, Any]]:
    """Fire prompt-submit. Does not route through plugin_prompt (JSON-only)."""
    marker = runtime_token("hook")
    payload = {
        "prompt": prompt,
        "marker": marker,
        "event": "prompt-submit",
    }
    result = ws.invoke_hook(
        "prompt-submit",
        payload=payload,
        env_updates=env_updates,
    )
    return result, payload


def payload_string_values(payload: Mapping[str, Any] | None) -> tuple[str, ...]:
    if payload is None:
        return ()
    return tuple(_walk_strings(payload))




def strip_hook_covariates(
    text: str,
    *paths: str,
    levels: Sequence[str] = (),
    extra: Sequence[Any] = (),
    stdin_strings: Sequence[str] = (),
    json_obj: Mapping[str, Any] | None = None,
) -> str:
    out = str(text)
    for path in paths:
        if path:
            out = out.replace(str(path), " ")
            out = out.replace(str(path).replace("\\", "/"), " ")
    for key in ("USER", "LOGNAME", "USERNAME"):
        val = os.environ.get(key)
        if val:
            out = out.replace(val, " ")
    home = os.environ.get("HOME")
    if home:
        out = out.replace(home, " ")
        out = out.replace(Path(home).name, " ")
    for raw in stdin_strings:
        if raw:
            out = out.replace(str(raw), " ")
            try:
                out = out.replace(json.dumps(raw)[1:-1], " ")
            except (TypeError, ValueError):
                pass
    if isinstance(json_obj, Mapping):
        keys = _walk_keys(json_obj)
        key_set = set(keys)
        for key in keys:
            out = _strip_standalone(out, key)
        for value in _walk_strings(json_obj):
            if value in key_set:
                out = out.replace(value, " ")
    for level in levels:
        if level:
            out = _strip_standalone(out, str(level))
    for item in extra:
        out = _strip_standalone(out, item)
    return _fold(out)












def contains_every_banned_word(text: str) -> bool:
    if not _fold(text):
        raise HarnessError("empty text cannot show the banned-vocabulary list")
    return all(standalone_word_present(text, word) for word in BANNED_VOCABULARY)




def _finding_objects(findings: Any) -> list[Mapping[str, Any]]:
    if findings is None:
        raise HarnessError("findings are missing; cannot read the report")
    if isinstance(findings, Mapping):
        items = list(findings.values())
    elif isinstance(findings, list):
        items = list(findings)
    else:
        raise HarnessError(
            f"findings are {type(findings).__name__}, not an object or list"
        )
    objects: list[Mapping[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise HarnessError(
                f"finding is {type(item).__name__}, not an object"
            )
        objects.append(item)
    return objects


def report_findings_direct(result: RunResult) -> dict[str, Mapping[str, Any]]:
    """Finding members of a detector success report, read at the stated form.

    Interface Contract: exit 0, stdout one JSON object; `_metrics` is an
    object; every other member is a finding keyed `<N>_<slug>` whose value
    carries a positive integer `count`.
    """
    assert result.returncode == 0, (
        f"detector failed: exit={result.returncode} stderr={result.stderr_text!r}"
    )
    try:
        report = json.loads(result.stdout_text)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"detector stdout is not JSON: {exc}") from exc
    assert isinstance(report, dict), "detector report is not a JSON object"
    assert isinstance(report.get("_metrics"), dict), "report has no _metrics object"
    findings: dict[str, Mapping[str, Any]] = {}
    for key, value in report.items():
        if key == "_metrics":
            continue
        assert _FINDING_KEY.match(str(key)), (
            f"report member {key!r} is neither _metrics nor a <N>_<slug> finding"
        )
        assert isinstance(value, dict), f"finding {key!r} is not an object"
        count = value.get("count")
        assert isinstance(count, int) and not isinstance(count, bool) and count > 0, (
            f"finding {key!r} count is not a positive integer: {count!r}"
        )
        findings[str(key)] = value
    return findings


def require_probe_finding(findings: Any) -> None:
    """The two-sentence probe produced at least one finding (L201 / L216).

    A stand-in sibling is not required to be finding-free. Residual text
    after the planted word is stripped is not this observation.
    """
    objects = _finding_objects(findings)
    assert objects, "two-sentence probe produced no finding"




def two_sentence_probe(word: str) -> str:
    digest = hashlib.sha256(f"{_FRAME_SEED}:{word}".encode("utf-8")).hexdigest()
    first = f"frame{digest[:10]}"
    second = f"next{digest[10:20]}"
    return (
        f"The {first} notes mentioned {word} in passing yesterday. "
        f"The {second} report mentioned {word} again this morning."
    )


def stored_session_text(level: str, *, paths_into: list[str] | None = None) -> str:
    """Session-start delivery at a pre-stored level (no first-run extra)."""
    from _harness import workspace as _workspace

    with _workspace() as ws:
        ws.write_mode_flag(level)
        result = session_start(ws)
        text = session_text(result)
        if paths_into is not None:
            paths_into.extend(workspace_paths(ws))
        print(
            f"[F04] stored {level} session-start len={len(text)} "
            f"exit={result.returncode}",
            flush=True,
        )
        return text


def make_flag_unwritable(ws) -> None:
    """Replace the config directory with a file so the flag cannot be written."""
    cfg = ws.config_dir
    if cfg.is_dir():
        shutil.rmtree(cfg)
    elif cfg.exists():
        cfg.unlink()
    cfg.write_text("not-a-directory\n", encoding="utf-8")


def make_flag_unreadable(ws) -> Path:
    """Install a non-file at the flag path (not a one-word readable value)."""
    dest = mode_flag_path(ws.config_dir)
    if dest.exists() or dest.is_symlink():
        if dest.is_dir() and not dest.is_symlink():
            shutil.rmtree(dest)
        else:
            dest.unlink()
    dest.mkdir()
    return dest


def ordinary_prompt() -> str:
    return f"Please summarise the {runtime_token('ask')} notes for the archive."


def has_light_tells(text: str) -> bool:
    return (
        re.search(r"(?i)(?<![A-Za-z])light\s+tells(?![A-Za-z])", str(text))
        is not None
    )


def archive_mb_cap_present(text: str) -> bool:
    """Whether *text* states the archive cap as 4 MB (L203 / L216).

    A standalone digit 4 is not that cap. The unit may sit against the
    digit or after whitespace; either rendering is the named quantity.
    """
    return _ARCHIVE_MB_CAP.search(str(text)) is not None


def has_named_welcome_facts(text: str) -> bool:
    """True only when every named welcome fact is present (L203 / L216)."""
    return not missing_welcome_facts(text)


def missing_welcome_facts(text: str) -> tuple[str, ...]:
    """Named welcome facts that are absent from *text*."""
    missing: list[str] = []
    if not _fold(text):
        return tuple(str(v) for v in WELCOME_INTS) + ("4 MB",) + WELCOME_COMMANDS
    for value in WELCOME_INTS:
        if not named_int_present(text, value):
            missing.append(str(value))
    if not archive_mb_cap_present(text):
        missing.append("4 MB")
    for command in WELCOME_COMMANDS:
        if command not in str(text):
            missing.append(command)
    return tuple(missing)


def present_welcome_facts(text: str) -> tuple[str, ...]:
    """Named welcome facts that appear in *text* — each one, not all-or-nothing.

    The archive cap is reported only as 4 MB. A bare digit 4 is not that fact,
    so a later or unwritable delivery may still contain an unrelated 4.
    """
    present: list[str] = []
    for value in WELCOME_INTS:
        if named_int_present(text, value):
            present.append(str(value))
    if archive_mb_cap_present(text):
        present.append("4 MB")
    for command in WELCOME_COMMANDS:
        if command in str(text):
            present.append(command)
    return tuple(present)


def require_named_welcome_facts(text: str) -> None:
    missing = missing_welcome_facts(text)
    assert not missing, (
        "writable first session-start must include the named welcome facts "
        "(71 patterns, 512 KB, 4 MB, 262,144 characters, and the four "
        f"slash commands); missing={missing!r}"
    )


def require_welcome_facts_absent(text: str) -> None:
    """Each named fact is absent. Not-all (any one missing) is not this observation.

    Empty text is not a pass: the caller must still require the banned-list
    contract on a later / unwritable start. This helper only names which
    facts remain.
    """
    present = present_welcome_facts(text)
    assert not present, (
        "a later start on the same config, or an unwritable arm, must omit "
        f"every named welcome fact; still present={present!r}"
    )


def require_stored_on_level(flag: str | None) -> None:
    """A fresh writable install stores the default level word ``full``.

    ``lite`` or ``strict`` is not that default. The stored word is ``full``;
    surrounding whitespace is not a second character the spec grades.
    """
    stored = flag.strip() if isinstance(flag, str) else None
    assert stored == "full", (
        "a fresh writable install stores the default level full; "
        f"stored={flag!r}"
    )


def _machine_user_name() -> str:
    try:
        name = pwd.getpwuid(os.getuid()).pw_name
    except KeyError as exc:
        raise HarnessError(f"cannot read the user name: {exc}") from exc
    if not isinstance(name, str) or not name.strip():
        raise HarnessError(f"user name is empty: {name!r}")
    return name


def require_exported_contract_omits_machine_identity(text: str) -> None:
    """The contract ``/prosecheck init`` writes omits this machine's detector
    path and the user name (L212). A live session delivery is not this
    observation. The banned-vocabulary list is the positive carrier that
    an export happened; omitting the path from an empty file is not.
    """
    require_banned_list(text)
    try:
        detector = str(detector_script())
    except FileNotFoundError as exc:
        raise HarnessError(f"cannot locate this machine's detector: {exc}") from exc
    if not detector or detector in {".", "/"}:
        raise HarnessError(f"detector path is not usable: {detector!r}")
    user = _machine_user_name()
    user_re = re.compile(rf"(?<!\w){re.escape(user)}(?!\w)")
    witness = f"witness {detector} {user}"
    if detector not in witness or user_re.search(witness) is None:
        raise HarnessError(
            "identity check cannot see a planted detector path or user name"
        )
    assert detector not in text, (
        "exported contract names this machine's detector path"
    )
    assert user_re.search(text) is None, (
        "exported contract names the user name"
    )


def has_cleanup_switch_finish(text: str) -> bool:
    """Whether the delivery asks for a finish through the FP-03 switch.

    The switch is the stated literal ``--clean``. Checked on the raw text:
    stripping the band word ``clean`` would eat the switch.
    """
    return CLEANUP_SWITCH in str(text)


_SOURCE_CODE = re.compile(r"(?i)\bsource[- ]code\b")
_SOURCE_CODE_DENIAL = re.compile(r"(?i)\b(?:never|not)\b")


def names_source_code_without_denial(text: str, *paths: str) -> bool:
    """True when a sentence names source code with no ``never`` / ``not`` before it.

    Contract shell part: wherever the writing contract names source code,
    the standalone word ``never`` or ``not`` comes earlier in the same
    sentence; a sentence ends at ``.``, ``!``, ``?`` or a line break.
    """
    stripped = strip_hook_covariates(text, *paths, levels=ON_LEVELS)
    for sentence in re.split(r"[.!?\n]", stripped):
        for source_m in _SOURCE_CODE.finditer(sentence):
            if _SOURCE_CODE_DENIAL.search(sentence, 0, source_m.start()) is None:
                return True
    return False


def require_banned_list(text: str) -> None:
    assert contains_every_banned_word(text), (
        "writing contract is missing a named banned-vocabulary word"
    )


def require_not_source_code_scope(text: str, *paths: str) -> None:
    """The delivery names source code only as something it never / does not cover."""
    assert not names_source_code_without_denial(text, *paths), (
        "session-start delivery names source code with no never / not before it in the sentence"
    )


def require_empty_stdout(result: RunResult) -> None:
    """Off-arm hooks emit empty standard output, not empty joined strings."""
    require_hook_success(result)
    assert result.stdout == b"", (
        "hook must emit empty standard output; "
        f"stdout={result.stdout[:400]!r}"
    )


def require_full_scoring(text: str, *paths: str) -> None:
    """Stored full / no-flag / unreadable-default: banned list plus the
    named post-write scoring targets (score at most 40, and clean or
    light tells). The integer is read after this machine's detector path
    is removed, so a 40 that lives only in that path is not the target.
    """
    require_banned_list(text)
    assert named_score_present(text, 40, *paths), (
        "full contract does not name the score-40 target"
    )
    assert standalone_word_present(text, "clean") or has_light_tells(text), (
        "full contract does not name the clean or light-tells target bands"
    )


def require_lite_omits_scoring(lite_text: str, full_text: str, *paths: str) -> None:
    """Lite still emits the writing contract (banned list) and omits the
    named post-write scoring targets full carries (L202 / L216): the
    score-40 target and the ``light tells`` band. ``clean`` alone is not the
    discriminator — every level's silent rule may speak of clean prose — so
    the omission is told by 40 and ``light tells``, with the live full
    delivery as the baseline that has them.
    """
    require_banned_list(lite_text)
    assert named_score_present(full_text, 40, *paths) and (
        standalone_word_present(full_text, "clean") or has_light_tells(full_text)
    ), (
        "stored-full live baseline does not name the score-40 target and a "
        "clean / light-tells band (lite omit has no live baseline)"
    )
    assert not named_score_present(lite_text, 40, *paths), (
        "lite contract still names the score-40 post-write scoring target"
    )
    assert not has_light_tells(lite_text), (
        "lite contract still names the light-tells post-write scoring band"
    )


def require_strict_cleanup(strict_text: str, full_text: str, *paths: str) -> None:
    """Strict: score-20, the clean band, and a finish through the cleanup
    switch that full does not carry.

    The stated switch spelling ``--clean`` contains the band word. That spelling
    is not the band: ``clean`` counts only when it is still present after
    the spelling is removed. The two target integers are read off the
    deliveries; they are not compared to each other as literals.
    """
    assert named_score_present(strict_text, 20, *paths), (
        "strict contract does not name the score-20 target"
    )
    flag = CLEANUP_SWITCH
    apart = re.sub(re.escape(flag), " ", str(strict_text), flags=re.IGNORECASE)
    assert standalone_word_present(apart, "clean"), (
        "strict contract does not name the clean band apart from the cleanup switch"
    )
    assert named_score_present(full_text, 40, *paths), (
        "full sibling does not name the score-40 target (live baseline)"
    )
    assert has_cleanup_switch_finish(strict_text), (
        "strict contract does not ask for a finish through the cleanup switch"
    )
    assert not has_cleanup_switch_finish(full_text), (
        "full contract must not carry the cleanup-switch finish that strict has"
    )


def require_short_reminder(
    result: RunResult,
    *,
    level: str,
    session_text: str = "",
    full_text: str = "",
    lite_text: str = "",
    stdin_strings: Sequence[str] = (),
    paths: Sequence[str] = (),
) -> str:
    """Prompt-submit names the live level (L205 / L216). The remainder of
    that reminder is inventory, not an independently graded leftover.
    """
    text = reminder_text(result)
    assert text.strip(), f"prompt-submit at {level} emitted nothing"
    assert standalone_word_present(text, level), (
        f"prompt reminder does not name {level!r}; text={text[:400]!r}"
    )
    print(f"[F04] reminder names {level!r} len={len(text)}", flush=True)
    return text


_CONNECT_PRELOAD = r"""
"use strict";
const fs = require("fs");
const logp = process.env._F04_CONNECT_LOG;
function rec(kind, dest) {
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
  const dgram = require("dgram");
  wrap(dgram.Socket.prototype, "send");
  wrap(dgram.Socket.prototype, "connect");
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


@contextmanager
def hook_connect_observer() -> Iterator[Any]:
    """Count network connections from hook processes, including clients
    that ignore HTTP_PROXY / HTTPS_PROXY / ALL_PROXY.

    A Node preload records net / dgram / http / https calls. Starting a
    local program is not a connection. When strace is on PATH, a node
    wrapper also records AF_INET / AF_INET6 connect() syscalls. Failure
    to install the observer raises; it does not return zero.
    """
    tmp = Path(tempfile.mkdtemp(prefix="f04-net-"))
    log = tmp / "connects.log"
    log.write_text("", encoding="utf-8")
    preload = tmp / "preload.js"
    preload.write_text(_CONNECT_PRELOAD, encoding="utf-8")
    try:
        real_node = node_executable()
    except FileNotFoundError as exc:
        raise HarnessError(f"cannot observe hook connects: {exc}") from exc
    strace = shutil.which("strace")
    wrapper = tmp / "node"
    strace_log = tmp / "strace.log"
    if strace:
        probe = subprocess.run(
            [
                strace,
                "-f",
                "-qq",
                "-e",
                "trace=connect",
                "-o",
                str(tmp / "probe.log"),
                real_node,
                "-e",
                "process.exit(0)",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        if probe.returncode != 0:
            strace = None
    if strace:
        wrapper.write_text(
            "#!/bin/sh\n"
            f"exec {shlex.quote(strace)} -f -qq -e trace=connect "
            f"-o {shlex.quote(str(strace_log))} "
            f"{shlex.quote(real_node)} \"$@\"\n",
            encoding="utf-8",
        )
    else:
        wrapper.write_text(
            "#!/bin/sh\n"
            f"exec {shlex.quote(real_node)} \"$@\"\n",
            encoding="utf-8",
        )
    wrapper.chmod(0o755)

    def _inet_syscalls() -> int:
        if not strace_log.exists():
            return 0
        text = strace_log.read_text(encoding="utf-8", errors="replace")
        return sum(
            1
            for line in text.splitlines()
            if "AF_INET" in line or "AF_INET6" in line
        )

    def _preload_events() -> int:
        if not log.exists():
            return 0
        body = log.read_text(encoding="utf-8", errors="replace").strip()
        if not body:
            return 0
        return len([ln for ln in body.splitlines() if ln.strip()])

    class Observer:
        env_updates = {
            "PATH": f"{tmp}{os.pathsep}{os.environ.get('PATH', '')}",
            "NODE_OPTIONS": f"--require={preload}",
            "_F04_CONNECT_LOG": str(log),
        }

        @property
        def n_connects(self) -> int:
            return _preload_events() + _inet_syscalls()

        def fire_positive_control(self, host: str, port: int) -> None:
            before = self.n_connects
            env = dict(os.environ)
            env.update(self.env_updates)
            script = (
                "const n=require('net');"
                f"const s=n.connect({int(port)},{json.dumps(host)},"
                "()=>{s.end();process.exit(0)});"
                "s.on('error',()=>process.exit(0));"
                "setTimeout(()=>process.exit(0),1500);"
            )
            completed = subprocess.run(
                [str(wrapper), "-e", script],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            if completed.returncode not in (0, None) and self.n_connects <= before:
                raise HarnessError(
                    "connect observer positive control did not record a connect; "
                    f"exit={completed.returncode} n={self.n_connects}"
                )
            deadline = time.time() + 2.0
            while time.time() < deadline and self.n_connects <= before:
                time.sleep(0.05)
            if self.n_connects <= before:
                raise HarnessError(
                    "connect observer saw no connect from the positive control"
                )

    try:
        yield Observer()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
