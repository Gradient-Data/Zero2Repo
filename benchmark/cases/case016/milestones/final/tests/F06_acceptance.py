# feature: F06
"""Acceptance tests for the /prosecheck command router.

Assertions follow the feature's public contract. Host payload keys are
only how a value is sent.
"""

from __future__ import annotations

import ctypes
import errno
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest

from _harness import ENV_PLUGIN_ROOT, HarnessError
from F02_helpers import (
    NOTEBOOK_EXT,
    pad_file_to_size,
    runtime_token,
    window_body,
    write_docx,
    write_notebook,
    write_plain,
    write_pptx,
)
from F04_helpers import (
    BANNED_VOCABULARY,
    has_cleanup_switch_finish,
    has_light_tells,
    hook_connect_observer,
    require_banned_list,
    require_exported_contract_omits_machine_identity,
    require_full_scoring,
    require_hook_success,
    require_lite_omits_scoring,
    require_strict_cleanup,
    require_not_source_code_scope,
    session_start,
    standalone_word_present,
)
from F05_helpers import (
    fire_pinned,
    pinned_score,
    BETWEEN_CAPS,
    OVER_BOTH_4MB,
    OVER_BOTH_4MB_OTHER,
    OVER_BOTH_512,
    files_holding_basename,
    fire_tool,
    interpreter_standin,
    measure_path,
    measure_text,
    phrase_for_band,
    prose_dense,
    prose_under,
)
from F06_helpers import (
    CHECK_NOT_SCORED_PHRASES,
    CHECK_PATH_ARTIFACTS,
    HELP_LIST,
    NAMED,
    NOT_AUTHOR,
    PLAIN,
    SUBCOMMANDS,
    age_file,
    assert_one_level_line,
    block_reason,
    check_over_cap_figure,
    check_path_argument,
    clear_stored_level,
    command_registrations,
    command_reply,
    cursor_rule_body,
    doctor_checks,
    doctor_lines,
    emitted_failure_standin,
    failed_row_reason,
    fault_closer_ok,
    first_window_only,
    fresh_word,
    has_phrase,
    already_for,
    healthy_closer_ok,
    help_entry_line,
    help_listed_in_command_slot,
    high_confidence_prose,
    invoke_shipped_command,
    is_binary_row,
    is_success,
    label_hits,
    many_label_prose,
    mode_line_level,
    names_post_write_detector,
    no_score_integers,
    node_kept_without_interpreters,
    off_closer_ok,
    parse_check_summary,
    parse_scored_row,
    prompt_submission,
    prose_with_confidence_reason,
    reports_word_as_unknown,
    require_check_summary,
    require_contract_section,
    require_empty_show,
    require_four_healthy_checks,
    require_no_score,
    require_outside_text_in_place,
    require_prose_glob_front_matter,
    require_same_rule_bytes,
    require_scored_row_shows,
    require_strict_clean_band_apart,
    resolution_lines,
    row_order,
    shared_sweep_clock,
    show_row,
    shows_integer,
    size_skip_figures,
    standalone_count,
    stamp_cutoff_offset,
    states_prose_only_scope,
    stats_level,
    stats_session_score,
    stats_values,
    window_named,
    scored_prose,
    zero_label_prose,
)

UNDER_BOTH = 400 * 1024
OUTSIDE = (
    "The mill wheel turns after rain. The clerk copies the parish list "
    "by hand and leaves the totals in the margin. Neighbours argue about "
    "the footbridge, then fix the loose plank before dark."
)


def _ask(ws, words="", form=PLAIN, **kwargs):
    """One command identity, read as a block decision's reason.

    *words* empty is the bare invocation. A subcommand, an unknown word,
    or check with or without a path is that word on *form*. Both forms
    share this reader. The text returned is the reason, not every string
    in the body.
    """
    prompt = form if not words else f"{form} {words}"
    return command_reply(ws, prompt, **kwargs)


def _status(ws, form=PLAIN):
    """Command reply and joined delivery for one status read.

    The reply is the report. The joined delivery still carries the stored
    level, including strings that sit beside the reply.
    """
    obj, joined = prompt_submission(ws, f"{form} status")
    return block_reason(obj, joined), joined


def _store(ws, level, form=PLAIN):
    reply = _ask(ws, level, form)
    if level == "on":
        if not standalone_word_present(reply, "on"):
            raise HarnessError(f"on reply does not name on; text={reply[:300]!r}")
        if standalone_count(reply, "full") < 1:
            raise HarnessError(f"on reply does not name full; text={reply[:300]!r}")
    elif not standalone_word_present(reply, level):
        raise HarnessError(
            f"{level} reply does not name that level; text={reply[:300]!r}"
        )
    return reply


def _non_namespaced_command_line(line):
    """A command line in the non-namespaced spelling.

    The namespaced form contains the shorter token as a prefix, so that
    token has to be read after the namespaced form is set aside. Mentioning
    the namespaced form elsewhere on the line does not hide the shorter one.
    """
    return PLAIN in line.replace(NAMED, " ")


def _help_has_list(text):
    for line in text.splitlines():
        if help_listed_in_command_slot(line):
            raise AssertionError("help lists help as its own subcommand")
    for word in HELP_LIST:
        if not standalone_word_present(text, word):
            raise AssertionError(f"help is missing {word}; text={text[:500]!r}")
        lines = [
            line
            for line in text.splitlines()
            if standalone_word_present(line, word) and _non_namespaced_command_line(line)
        ]
        if not lines:
            raise AssertionError(
                f"help does not put {word} on a non-namespaced command line"
            )


def _no_score(reply, *paths):
    """No 0-100 integer once the paths this reply names are removed."""
    require_no_score(reply, *paths)


def _bytes_same(path, before):
    after = path.read_bytes()
    assert after == before, f"{path.name} bytes changed"
    flipped = bytearray(before)
    if not flipped:
        flipped = bytearray(b"\x00")
    flipped[0] ^= 0x01
    assert bytes(flipped) != before


def _check_facts(text, measured, base):
    summary = parse_check_summary(text)
    assert summary.base.endswith(base)
    assert summary.phrase == phrase_for_band(measured.band)
    assert summary.band == measured.band
    assert summary.confidence == measured.confidence
    assert summary.score == measured.score
    assert NOT_AUTHOR not in text
    return summary


def _plant(ws, name, text):
    return write_plain(ws, name, text)


def _save(ws, path, session):
    fire_tool(ws, "Write", session_id=session, file_path=str(path))


def _empty_show(text, absent):
    require_empty_show(text, absent)


def _agents(ws):
    return Path(ws.path) / "AGENTS.md"


def _rule(ws):
    return Path(ws.path) / ".cursor" / "rules" / "prosecheck.mdc"


def _clear_export(ws):
    agents = _agents(ws)
    if agents.is_dir() and not agents.is_symlink():
        shutil.rmtree(agents)
    elif agents.exists() or agents.is_symlink():
        agents.unlink()
    cursor = Path(ws.path) / ".cursor"
    if cursor.is_dir() and not cursor.is_symlink():
        shutil.rmtree(cursor)
    elif cursor.exists() or cursor.is_symlink():
        cursor.unlink()


def _assistant(text, output, cache, mid=None):
    message = {
        "usage": {
            "output_tokens": output,
            "cache_read_input_tokens": cache,
        },
        "content": [{"type": "text", "text": text}],
    }
    if mid is not None:
        message["id"] = mid
    return {"type": "assistant", "message": message}


def _other_row(kind, text, output, cache):
    """A transcript row whose type is not assistant.

    The text sits where an assistant row's text sits. The two usage
    fields are present so a row that is skipped only when usage is
    missing still carries them. The type word has no digits.
    """
    if not isinstance(kind, str) or kind == "" or kind == "assistant":
        raise HarnessError(f"non-assistant row type is not usable: {kind!r}")
    if any(ch.isdigit() for ch in kind):
        raise HarnessError(f"non-assistant row type contains a digit: {kind!r}")
    return {
        "type": kind,
        "message": {
            "usage": {
                "output_tokens": output,
                "cache_read_input_tokens": cache,
            },
            "content": [{"type": "text", "text": text}],
        },
    }


def _write_jsonl(directory, name, entries):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n",
        encoding="utf-8",
    )
    return path


def _prose_slice(text):
    stripped = re.sub(r"```[\s\S]*?```", " ", text)
    if len(stripped) > 40000:
        stripped = stripped[-40000:]
    return stripped.strip()


def _agreed_score(left, right):
    """Score of both entries, when the join does not change the number.

    The specification says both texts are scored. It does not name the
    characters placed between them, so the two arms are usable only when
    a space, a line break, and a blank line all yield one score, and that
    score is not the first entry alone.
    """
    scores = {
        measure_text(sep.join((left, right))).score
        for sep in ("\n\n", "\n", " ")
    }
    if len(scores) != 1:
        raise HarnessError(
            f"joined prose score depends on the separator: {scores}"
        )
    combined = scores.pop()
    only = measure_text(left).score
    if combined == only:
        raise HarnessError("adding the second entry did not move the score")
    return combined


def test_both_forms_show_help_and_cross_read_the_stored_level(isolated_ws):
    ws = isolated_ws
    plain = _ask(ws)
    named = _ask(ws, form=NAMED)
    for text in (plain, named):
        assert standalone_word_present(text, "full")
        _help_has_list(text)
    _store(ws, "strict", NAMED)
    assert_one_level_line(_status(ws, PLAIN), "strict")
    _store(ws, "lite", PLAIN)
    assert_one_level_line(_status(ws, NAMED), "lite")


def _help_level(text):
    """Contract: the first line of help names the live level and no other."""
    first = next(line for line in text.splitlines() if line.strip())
    named = [w for w in ("lite", "full", "strict", "off") if standalone_word_present(first, w)]
    assert len(named) == 1, (named, first)
    return named[0]


def test_bare_invocation_names_the_level_after_it_changes(isolated_ws):
    ws = isolated_ws
    before_plain = _ask(ws)
    before_named = _ask(ws, form=NAMED)
    _store(ws, "strict")
    after_plain = _ask(ws)
    after_named = _ask(ws, form=NAMED)
    for before, after in (
        (before_plain, after_plain),
        (before_named, after_named),
    ):
        assert _help_level(before) == "full"
        assert _help_level(after) == "strict"


def test_namespaced_form_covers_every_subcommand(isolated_ws):
    ws = isolated_ws
    _help_has_list(_ask(ws, "help", NAMED))
    healthy = _ask(ws, "doctor", NAMED)
    require_four_healthy_checks(healthy, "full")
    measured = scored_prose()
    path = _plant(ws, fresh_word() + ".md", measured.text)
    checked = _ask(ws, f"check {path}", NAMED)
    summary = parse_check_summary(checked)
    assert summary.base.endswith(path.name)
    assert summary.score == measured.score
    _empty_show(_ask(ws, "show", NAMED), "")
    _store(ws, "strict")
    transcript = _write_jsonl(
        Path(ws.path),
        "named.jsonl",
        [_assistant(OUTSIDE, 410, 820)],
    )
    stats = _ask(ws, "stats", NAMED, transcript_path=str(transcript))
    values = stats_values(stats)
    assert values.get("output") == 410 and values.get("cache") == 820, stats
    assert stats_level(stats) == "strict", stats
    _store(ws, "lite", NAMED)
    assert_one_level_line(_status(ws, NAMED), "lite")
    _store(ws, "full", NAMED)
    assert_one_level_line(_status(ws), "full")
    off_reply = _store(ws, "off", NAMED)
    assert off_reply.strip()
    assert_one_level_line(_status(ws, NAMED), "off")
    _store(ws, "on", NAMED)
    assert_one_level_line(_status(ws, NAMED), "full")
    _clear_export(ws)
    _ask(ws, "init", NAMED, cwd=str(ws.path))
    assert _agents(ws).is_file()
    assert _rule(ws).is_file()


def test_command_still_replies_when_ordinary_prompts_go_silent(isolated_ws):
    ws = isolated_ws
    ordinary = "Please keep the parish notes."
    full_reason = _ask(ws, "full")
    assert standalone_word_present(full_reason, "full")
    reminded_obj, reminded = prompt_submission(ws, ordinary)
    assert reminded_obj is None or reminded_obj.get("decision") != "block"
    assert standalone_word_present(reminded, "full")
    off_reason = _ask(ws, "off")
    assert off_reason.strip()
    assert standalone_word_present(off_reason, "off")
    silent_obj, silent = prompt_submission(ws, ordinary)
    assert silent == ""
    assert silent_obj is None


def test_level_verbs_store_and_status_is_one_line(isolated_ws):
    ws = isolated_ws
    assert_one_level_line(_status(ws), "full")
    for level in ("lite", "full", "strict", "off"):
        _store(ws, level)
        assert_one_level_line(_status(ws), level)
    _store(ws, "full", NAMED)
    assert_one_level_line(_status(ws), "full")
    _store(ws, "off", NAMED)
    assert_one_level_line(_status(ws), "off")


def test_on_stores_full_and_confirms_both_words(isolated_ws):
    ws = isolated_ws
    _store(ws, "off")
    on_reply = _store(ws, "on")
    _store(ws, "full")
    assert standalone_count(on_reply, "full") >= 1
    assert_one_level_line(_status(ws), "full")
    _store(ws, "off")
    named_on = _store(ws, "on", NAMED)
    assert standalone_word_present(named_on, "on")
    assert standalone_count(named_on, "full") >= 1
    assert_one_level_line(_status(ws), "full")


def test_entire_prompt_stop_phrases_store_off(isolated_ws):
    ws = isolated_ws
    for phrase in ("stop prosecheck", "prosecheck off"):
        _store(ws, "full")
        phrase_reason = command_reply(ws, phrase)
        assert phrase_reason.strip()
        assert standalone_word_present(phrase_reason, "off")
        assert_one_level_line(_status(ws), "off")
        for built in (
            f"{fresh_word()} {phrase}",
            f"{phrase} {fresh_word()}",
        ):
            _store(ws, "full")
            built_obj, reply = prompt_submission(ws, built)
            assert built_obj is None or built_obj.get("decision") != "block"
            assert_one_level_line(_status(ws), "full")
            assert standalone_word_present(reply, "full")


def test_unknown_word_lists_the_valid_commands_and_keeps_the_level(isolated_ws):
    ws = isolated_ws
    _store(ws, "strict")
    for form in (PLAIN, NAMED):
        word = fresh_word()
        reply = _ask(ws, word, form)
        for sub in SUBCOMMANDS:
            assert standalone_word_present(reply, sub)
        assert reports_word_as_unknown(reply, word), reply
        assert_one_level_line(_status(ws), "strict")


def test_help_lists_every_subcommand_except_itself(isolated_ws):
    ws = isolated_ws
    for form in (PLAIN, NAMED):
        _help_has_list(_ask(ws, "help", form))


def test_help_names_the_live_level_by_count(isolated_ws):
    ws = isolated_ws
    before = _ask(ws, "help")
    _store(ws, "strict")
    after = _ask(ws, "help")
    assert _help_level(before) == "full"
    assert _help_level(after) == "strict"


@pytest.mark.parametrize("form", (PLAIN, NAMED), ids=("plain", "named"))
def test_help_names_the_threshold_integers_and_the_export_path(isolated_ws, form):
    ws = isolated_ws
    text = _ask(ws, "help", form)
    scope = [
        line
        for line in text.splitlines()
        if all(standalone_word_present(line, w) for w in ("code", "commits", "config", "chat"))
        and has_phrase(line, "never")
    ]
    assert scope, text[:500]
    assert "prosecheck this" in text
    assert "humanize this" in text

    def line_with(command):
        hits = [line for line in text.splitlines() if f"{PLAIN} {command}" in line]
        if len(hits) != 1:
            raise AssertionError(f"help has no single {command} line; text={text[:500]!r}")
        return hits[0]

    full_line = line_with("full")
    strict_line = line_with("strict")
    lite_line = line_with("lite")
    init_line = line_with("init")
    assert shows_integer(full_line, 40)
    assert shows_integer(strict_line, 20)
    assert not shows_integer(lite_line, 40)
    assert not shows_integer(lite_line, 20)
    assert "AGENTS.md" in init_line
    for phrase in ("contract", "scoring"):
        assert has_phrase(lite_line, phrase), (phrase, lite_line)
    for phrase in ("contract", "guard", "(default)"):
        assert phrase.lower() in full_line.lower(), (phrase, full_line)
    for phrase in ("guard", "scrub"):
        assert has_phrase(strict_line, phrase), (phrase, strict_line)
    off_line = help_entry_line(text, "off")
    on_line = help_entry_line(text, "on")
    assert has_phrase(off_line, "disable"), off_line
    assert has_phrase(on_line, "re-enable"), on_line
    check_line = line_with("check")
    for phrase in ("score", "rewrite"):
        assert has_phrase(check_line, phrase), (phrase, check_line)
    assert has_phrase(line_with("doctor"), "health")
    stats_line = line_with("stats")
    for phrase in ("token", "prose"):
        assert has_phrase(stats_line, phrase), (phrase, stats_line)
    for phrase in ("contract",):
        assert has_phrase(init_line, phrase), (phrase, init_line)


@pytest.mark.parametrize("form", (PLAIN, NAMED), ids=("plain", "named"))
def test_check_report_matches_the_detector_and_does_not_rewrite(isolated_ws, form):
    ws = isolated_ws
    measured = prose_with_confidence_reason()
    path = _plant(ws, fresh_word() + ".md", measured.text)
    before = path.read_bytes()
    reply = _ask(ws, f"check {check_path_argument(path, 'bare')}", form)
    require_check_summary(reply, measured, path.name, reason=True)
    again = _ask(ws, f"check {path}", form)
    require_check_summary(again, measured, path.name, reason=True)
    _bytes_same(path, before)
    high = high_confidence_prose()
    if high.reason:
        raise HarnessError(
            f"no-reason fixture still carries a reason: {high.reason!r}"
        )
    high_path = _plant(ws, fresh_word() + ".md", high.text)
    high_before = high_path.read_bytes()
    high_reply = _ask(ws, f"check {high_path}", form)
    require_check_summary(high_reply, high, high_path.name, reason=False)
    _bytes_same(high_path, high_before)


@pytest.mark.parametrize("form", (PLAIN, NAMED), ids=("plain", "named"))
def test_check_prints_between_one_and_eight_labels_with_hit_counts(isolated_ws, form):
    ws = isolated_ws
    measured = many_label_prose()
    if len(measured.labels) <= 8:
        raise HarnessError("label-cap fixture does not exceed eight labels")
    path = _plant(ws, fresh_word() + ".md", measured.text)
    reply = _ask(ws, f"check {path}", form)
    summary = parse_check_summary(reply)
    assert not summary.tells_none
    assert 1 <= len(summary.tells) <= 8, summary.tells
    hits = label_hits(measured.text)
    for label, count in summary.tells:
        assert label in measured.labels, label
        assert count == hits[label], (label, count, hits[label])


@pytest.mark.parametrize("form", (PLAIN, NAMED), ids=("plain", "named"))
def test_check_without_findings_has_a_visible_indication(isolated_ws, form):
    ws = isolated_ws
    dense = many_label_prose()
    quiet = zero_label_prose()
    path = _plant(ws, fresh_word() + ".md", quiet.text)
    reply = _ask(ws, f"check {path}", form)
    summary = _check_facts(reply, quiet, path.name)
    assert summary.tells_none, reply
    assert summary.tells == ()
    for label in dense.labels:
        assert label not in reply


@pytest.mark.parametrize("form", (PLAIN, NAMED), ids=("plain", "named"))
@pytest.mark.parametrize("artifact", CHECK_PATH_ARTIFACTS)
def test_check_strips_surrounding_quotes_and_a_leading_at(
    isolated_ws, form, artifact
):
    ws = isolated_ws
    measured = prose_with_confidence_reason()
    path = _plant(ws, fresh_word() + ".md", measured.text)
    reply = _ask(ws, f"check {check_path_argument(path, artifact)}", form)
    require_check_summary(reply, measured, path.name, reason=True)


def test_check_asks_for_a_path(isolated_ws):
    ws = isolated_ws
    _store(ws, "strict")
    asked_obj, asked_joined = prompt_submission(ws, f"{PLAIN} check")
    asked = block_reason(asked_obj, asked_joined)
    assert asked.strip()
    no_score_integers(asked)
    no_score_integers(asked_joined)
    # Contract: the no-path reply is not the unknown-subcommand reply,
    # whose stated mark is the word unknown.
    assert not standalone_word_present(asked, "unknown"), asked


def test_check_not_a_file_unreadable_and_pdf_rtf_differ(isolated_ws):
    ws = isolated_ws
    folder = Path(ws.path) / fresh_word()
    folder.mkdir()
    missing = Path(ws.path) / (fresh_word() + ".md")
    pdf = write_plain(ws, fresh_word() + ".pdf", b"%PDF-1.1\n")
    rtf = write_plain(ws, fresh_word() + ".rtf", b"{\\rtf1 hi}")
    empty = _plant(ws, fresh_word() + ".md", "")
    before = {path: path.read_bytes() for path in (pdf, rtf, empty)}
    directory = _ask(ws, f"check {folder}")
    absent = _ask(ws, f"check {missing}")
    pdf_reply = _ask(ws, f"check {pdf}")
    rtf_reply = _ask(ws, f"check {rtf}")
    _ask(ws, f"check {empty}")
    for reply, path in (
        (directory, folder),
        (absent, missing),
        (pdf_reply, pdf),
        (rtf_reply, rtf),
    ):
        _no_score(reply, path)
    assert str(missing) in absent

    def only(reply, phrase):
        assert has_phrase(reply, phrase), (phrase, reply)
        others = [p for p in CHECK_NOT_SCORED_PHRASES if p != phrase and has_phrase(reply, p)]
        assert not others, (others, reply)

    only(directory, "not a file")
    only(absent, "cannot read")
    only(pdf_reply, "no readable text")
    only(rtf_reply, "no readable text")
    assert pdf.name in pdf_reply and rtf.name in rtf_reply
    # Same report for both formats (relational promise).
    assert pdf_reply.replace(pdf.name, "<base>") == rtf_reply.replace(rtf.name, "<base>")
    for path, blob in before.items():
        _bytes_same(path, blob)


def _rel(ws, path):
    return str(Path(path).relative_to(ws.path))


def test_check_over_cap_names_kilobytes_and_no_score(isolated_ws):
    ws = isolated_ws
    prose = scored_prose()

    def plain_pair(suffix):
        under = _plant(ws, fresh_word() + suffix, prose.text)
        pad_file_to_size(under, UNDER_BOTH)
        under_reply = _ask(ws, f"check {under}")
        assert parse_check_summary(under_reply).score == measure_path(ws, _rel(ws, under)).score
        over = _plant(ws, fresh_word() + suffix, prose.text)
        pad_file_to_size(over, OVER_BOTH_512)
        before = over.read_bytes()
        over_reply = _ask(ws, f"check {over}")
        assert check_over_cap_figure(over_reply) == 512, over_reply
        _no_score(over_reply, over)
        _bytes_same(over, before)

    plain_pair(".md")
    plain_pair(".txt")
    between = write_docx(ws, fresh_word() + ".docx", prose.text)
    pad_file_to_size(between, BETWEEN_CAPS)
    between_reply = _ask(ws, f"check {between}")
    assert between.name in between_reply
    assert parse_check_summary(between_reply).score == measure_path(ws, _rel(ws, between)).score
    notebook = write_notebook(ws, fresh_word() + NOTEBOOK_EXT, markdown=prose.text)
    pad_file_to_size(notebook, BETWEEN_CAPS)
    notebook_reply = _ask(ws, f"check {notebook}")
    assert notebook.name in notebook_reply
    assert parse_check_summary(notebook_reply).score == measure_path(ws, _rel(ws, notebook)).score

    for suffix, size in (
        (".docx", OVER_BOTH_4MB),
        (".docx", OVER_BOTH_4MB_OTHER),
        (".pptx", OVER_BOTH_4MB),
        (NOTEBOOK_EXT, OVER_BOTH_4MB),
    ):
        if suffix == NOTEBOOK_EXT:
            path = write_notebook(ws, fresh_word() + suffix, markdown=prose.text)
        elif suffix == ".pptx":
            path = write_pptx(ws, fresh_word() + suffix, prose.text)
        else:
            path = write_docx(ws, fresh_word() + suffix, prose.text)
        pad_file_to_size(path, size)
        reply = _ask(ws, f"check {path}")
        _no_score(reply, path)
        assert check_over_cap_figure(reply) == 4096, reply


def test_check_python_missing_names_no_score(isolated_ws):
    ws = isolated_ws
    path = _plant(ws, fresh_word() + ".md", scored_prose().text)
    before = path.read_bytes()
    missing_py = _ask(ws, f"check {path}", env_updates=node_kept_without_interpreters())
    _no_score(missing_py, path)
    assert has_phrase(missing_py, "detector unavailable"), missing_py
    assert not has_phrase(missing_py, "cannot read"), missing_py
    assert not has_phrase(missing_py, "no report"), missing_py
    _bytes_same(path, before)


def test_check_names_the_file_only_for_no_output_and_stated_failure(isolated_ws):
    ws = isolated_ws
    path = _plant(ws, fresh_word() + ".md", scored_prose().text)
    before = path.read_bytes()
    mark = fresh_word()
    failure = fresh_word()
    with interpreter_standin(ws, stdout=None, exit_code=0) as quiet:
        no_output = _ask(ws, f"check {path}", env_updates=quiet.env_updates)
    with interpreter_standin(ws, stdout=None, exit_code=211) as quiet_fail:
        silent = _ask(ws, f"check {path}", env_updates=quiet_fail.env_updates)
    with interpreter_standin(ws, stdout=f"note {mark}\n", exit_code=0) as junk:
        not_report = _ask(ws, f"check {path}", env_updates=junk.env_updates)
    with emitted_failure_standin(ws, failure) as failed:
        stated = _ask(ws, f"check {path}", env_updates=failed.env_updates)
    missing_py = _ask(ws, f"check {path}", env_updates=node_kept_without_interpreters())
    unreadable = _ask(ws, f"check {Path(ws.path) / 'gone.md'}")
    for reply in (no_output, silent, not_report, stated, missing_py):
        _no_score(reply.replace(failure, " ").replace(mark, " "), path)
    assert path.name in no_output
    assert failure not in no_output
    assert has_phrase(no_output, "no report"), no_output
    assert path.name in silent
    assert failure not in silent
    assert has_phrase(silent, "failed"), silent
    assert not has_phrase(silent, "no report"), silent
    assert path.name not in not_report
    assert failure not in not_report
    assert has_phrase(not_report, "no report"), not_report
    assert path.name in stated
    assert failure in stated
    assert has_phrase(stated, "failed"), stated
    assert not has_phrase(missing_py, "no report")
    assert not has_phrase(unreadable, "no report")
    _bytes_same(path, before)


@pytest.mark.parametrize("form", (PLAIN, NAMED), ids=("plain", "named"))
def test_check_names_the_window_only_when_truncated(isolated_ws, form):
    ws = isolated_ws
    exact = write_docx(ws, fresh_word() + ".docx", window_body(262144))
    longer = write_docx(ws, fresh_word() + ".docx", window_body(262145))
    assert exact.stat().st_size < 4 * 1024 * 1024
    assert longer.stat().st_size < 4 * 1024 * 1024
    exact_reply = _ask(ws, f"check {exact}", form)
    longer_reply = _ask(ws, f"check {longer}", form)
    exact_summary = parse_check_summary(exact_reply)
    longer_summary = parse_check_summary(longer_reply)
    assert exact_summary.coverage is None
    assert not window_named(exact_reply)
    assert longer_summary.coverage is not None
    assert first_window_only(longer_summary.coverage), longer_summary.coverage





@pytest.mark.parametrize("form", (PLAIN, NAMED), ids=("plain", "named"))
def test_doctor_healthy_on_install_shows_four_successes_and_the_caps(isolated_ws, form):
    ws = isolated_ws
    levels = ("lite", "full", "strict") if form == PLAIN else ("full",)
    for level in levels:
        _store(ws, level)
        reply = _ask(ws, "doctor", form)
        require_four_healthy_checks(reply, level)
        _title, _checks, closer = doctor_lines(reply)
        healthy_closer_ok(closer, form)


def test_doctor_does_not_pass_without_running_the_detector(isolated_ws):
    ws = isolated_ws
    _store(ws, "full")
    with interpreter_standin(ws, sleep_s=0.05, forward=True) as stand:
        before = stand.invocations()
        healthy = _ask(ws, "doctor", env_updates=stand.env_updates)
        assert stand.invocations() > before
        mid = stand.invocations()
        probe_env = dict(os.environ)
        probe_env.update(stand.env_updates)
        probe_env["F05_STUB_PROBE"] = "1"
        subprocess.run(
            [str(stand.root / "python3"), "-c", "import sys"],
            env=probe_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        assert stand.invocations() > mid
    require_four_healthy_checks(healthy, "full")
    with interpreter_standin(ws, stdout="not a score\n", exit_code=0) as stand:
        before_fault = stand.invocations()
        faulty = _ask(ws, "doctor", NAMED, env_updates=stand.env_updates)
        assert stand.invocations() > before_fault
    checks = doctor_checks(faulty)
    assert is_success(checks["mode"]) and mode_line_level(checks["mode"]) == "full"
    assert is_success(checks["detector"])
    assert is_success(checks["settings"])
    python_run = checks["python"]
    assert not is_success(python_run), python_run
    assert "python not found" not in python_run.lower()
    _title, _c, closer = doctor_lines(faulty)
    fault_closer_ok(closer)


def test_doctor_python_missing_keeps_the_detector_line(isolated_ws):
    ws = isolated_ws
    _store(ws, "full")
    missing = _ask(ws, "doctor", env_updates=node_kept_without_interpreters())
    checks = doctor_checks(missing)
    python_line = checks["python"].lower()
    assert not is_success(checks["python"])
    for phrase in ("python not found", "not re-scored"):
        assert phrase in python_line, (phrase, python_line)
    # Contract: the shaped-prose statement is free wording carrying "prose".
    assert has_phrase(python_line, "prose"), python_line
    detector = checks["detector"]
    assert is_success(detector)
    assert "python" not in detector.lower()
    assert is_success(checks["mode"]) and mode_line_level(checks["mode"]) == "full"
    assert is_success(checks["settings"])
    fault_closer_ok(doctor_lines(missing)[2])
    root = Path(tempfile.mkdtemp(prefix="f06-detect-"))
    try:
        (root / "scripts").mkdir()
        moved = _ask(ws, "doctor", env_updates={ENV_PLUGIN_ROOT: str(root)})
    finally:
        os.rmdir(root / "scripts")
        root.rmdir()
    moved_checks = doctor_checks(moved)
    moved_detector = moved_checks["detector"]
    assert not is_success(moved_detector), moved_detector
    assert not is_success(moved_detector), moved_detector
    assert "python" not in moved_detector.lower()
    fault_closer_ok(doctor_lines(moved)[2])


def _try_create(directory: Path) -> bool:
    """Whether this process can create a file in *directory*.

    A successful create is removed. A permission error is the blocked
    result. Any other failure is not treated as blocked.
    """
    probe = directory / ("probe-" + fresh_word())
    try:
        probe.write_text("x", encoding="utf-8")
    except PermissionError:
        return False
    except OSError as exc:
        raise HarnessError(
            f"settings directory probe failed: {exc}"
        ) from exc
    probe.unlink()
    return True


# prctl securebits. NOROOT stops a root exec from regaining every
# capability, so a mode bit applies to the hook the same way it applies
# to an unprivileged process. The bit is restored after the window.
_PR_GET_SECUREBITS = 27
_PR_SET_SECUREBITS = 28
_SECBIT_NOROOT = 1
_SAVED_SECUREBITS: int | None = None


def _prctl(option: int, arg2: int = 0) -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    rc = libc.prctl(option, arg2, 0, 0, 0)
    if rc < 0:
        err = ctypes.get_errno()
        raise HarnessError(f"prctl {option} failed: errno={err}")
    return int(rc)


def _hold_root_mode_bits() -> None:
    """Make hook children honor directory mode bits even when uid is 0."""
    global _SAVED_SECUREBITS
    if _SAVED_SECUREBITS is not None:
        raise HarnessError("root mode-bit window is already open")
    current = _prctl(_PR_GET_SECUREBITS)
    if current & _SECBIT_NOROOT:
        _SAVED_SECUREBITS = current
        return
    _prctl(_PR_SET_SECUREBITS, current | _SECBIT_NOROOT)
    _SAVED_SECUREBITS = current


def _release_root_mode_bits() -> None:
    global _SAVED_SECUREBITS
    saved = _SAVED_SECUREBITS
    _SAVED_SECUREBITS = None
    if saved is None:
        return
    _prctl(_PR_SET_SECUREBITS, saved)


def _grant_other_access(root: Path) -> list[tuple[Path, int]]:
    """Let a process without override read *root* and the directories above it.

    The product tree may be private to another uid. Mode bits on the
    settings folder still decide whether that folder is writable. The
    returned modes are what the tree had before this grant.
    """
    changed: list[tuple[Path, int]] = []

    def widen(path: Path, extra: int) -> None:
        if path.is_symlink():
            return
        mode = path.stat().st_mode & 0o777
        if mode & extra == extra:
            return
        changed.append((path, mode))
        os.chmod(path, mode | extra)

    current = root.resolve()
    ancestors: list[Path] = []
    while True:
        ancestors.append(current)
        if current == current.parent:
            break
        current = current.parent
    for path in reversed(ancestors):
        widen(path, 0o005)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(dirpath)
        widen(base, 0o005)
        for name in dirnames:
            path = base / name
            if not path.is_symlink():
                widen(path, 0o005)
        for name in filenames:
            path = base / name
            if not path.is_symlink():
                widen(path, 0o004)
    return changed


def _child_cannot_create(directory: Path) -> bool:
    """A fresh child cannot create a file in *directory*.

    The child is the same kind of exec the hook will be. A child that
    still creates the file means the folder is writable for the product.
    """
    probe = directory / ("probe-" + fresh_word())
    script = (
        "import pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text('x', encoding='utf-8')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, str(probe)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=5,
        check=False,
    )
    created = probe.exists()
    if created:
        probe.unlink()
    if completed.returncode < 0:
        raise HarnessError(
            "settings probe was killed: "
            f"signal={-completed.returncode} stderr={completed.stderr[:200]!r}"
        )
    return not created and completed.returncode != 0


@contextmanager
def _settings_unwritable(ws):
    """The settings folder is not writable for the doctor process.

    A mode bit is enough when this process is not privileged. A privileged
    process still creates files in a mode-555 directory, and a root exec
    would too, so hook children are started without that override for the
    window. Afterwards this process can create a file there again.
    """
    config = Path(ws.config_dir)
    os.chmod(config, 0o555)
    limited = False
    opened: list[tuple[Path, int]] = []
    try:
        if _try_create(config):
            opened = _grant_other_access(Path(ws.root))
            _hold_root_mode_bits()
            limited = True
            if not _child_cannot_create(config):
                raise HarnessError("settings directory stayed writable")
        elif not _child_cannot_create(config):
            raise HarnessError("settings directory stayed writable")
        yield
    finally:
        if limited:
            _release_root_mode_bits()
        for path, mode in reversed(opened):
            if path.exists() or path.is_symlink():
                os.chmod(path, mode)
        os.chmod(config, 0o755)
        probe = config / ("probe-" + fresh_word())
        probe.write_text("x", encoding="utf-8")
        if probe.read_text(encoding="utf-8") != "x":
            raise HarnessError(
                "settings directory did not accept a write after restore"
            )
        probe.unlink()


def _require_off_doctor(reply, form):
    checks = doctor_checks(reply)
    mode = checks["mode"]
    assert not is_success(mode), mode
    assert mode_line_level(mode) == "off", mode
    assert f"{PLAIN} on" in mode and standalone_word_present(mode, "on"), mode
    assert is_success(checks["detector"])
    assert is_success(checks["python"])
    assert is_success(checks["settings"])
    off_closer_ok(doctor_lines(reply)[2], form)


def test_doctor_off_mode_and_faults_use_the_stated_spellings(isolated_ws):
    ws = isolated_ws
    _store(ws, "off")
    with interpreter_standin(ws, sleep_s=0.05, forward=True) as stand:
        before = stand.invocations()
        named_off = _ask(ws, "doctor", NAMED, env_updates=stand.env_updates)
        assert stand.invocations() > before
    _require_off_doctor(named_off, NAMED)
    with interpreter_standin(ws, sleep_s=0.05, forward=True) as stand:
        before = stand.invocations()
        plain_off = _ask(ws, "doctor", env_updates=stand.env_updates)
        assert stand.invocations() > before
    _require_off_doctor(plain_off, PLAIN)
    with _settings_unwritable(ws):
        both = _ask(ws, "doctor", NAMED)
    both_checks = doctor_checks(both)
    assert not is_success(both_checks["settings"])
    assert not is_success(both_checks["settings"])
    fault_closer_ok(doctor_lines(both)[2])
    _store(ws, "full")
    with _settings_unwritable(ws):
        settings = _ask(ws, "doctor")
    checks = doctor_checks(settings)
    assert is_success(checks["mode"]) and mode_line_level(checks["mode"]) == "full"
    assert is_success(checks["detector"])
    assert is_success(checks["python"])
    fault = checks["settings"]
    assert not is_success(fault), fault
    assert not is_success(fault), fault
    assert "python" not in fault.lower()
    fault_closer_ok(doctor_lines(settings)[2])


def test_show_empty_ledger_names_the_deliverable_suffixes(isolated_ws):
    ws = isolated_ws
    session = runtime_token("s")
    absent = fresh_word() + ".md"
    empty = _ask(ws, "show", session_id=session)
    _empty_show(empty, absent)
    measured = prose_dense()
    path = _plant(ws, fresh_word() + ".md", measured.text)
    _save(ws, path, session)
    shown = _ask(ws, "show", session_id=session)
    require_scored_row_shows(show_row(shown, path.name), measured)
    assert NOT_AUTHOR not in shown


def test_show_lists_newest_first_against_name_and_score_order(isolated_ws):
    ws = isolated_ws
    session = runtime_token("s")
    older_text = prose_dense()
    newer_text = prose_under()
    assert newer_text.score < older_text.score
    assert older_text.score - newer_text.score >= 2
    # The third row's score sits strictly between the other two. The guard
    # reads it from this detector's own report with the score set there.
    newest_text, newest_report = pinned_score(
        newer_text.score + 1 + secrets.randbelow(older_text.score - newer_text.score - 1)
    )
    assert newer_text.score < newest_text.score < older_text.score
    older = _plant(ws, "a" + fresh_word() + ".md", older_text.text)
    newer = _plant(ws, "z" + fresh_word() + ".md", newer_text.text)
    newest = _plant(ws, "m" + fresh_word() + ".md", newest_text.text)
    assert newer.name > older.name
    assert older.name < newest.name < newer.name
    _save(ws, older, session)
    _save(ws, newer, session)
    fire_pinned(ws, newest_report, tool="Write", session_id=session, file_path=str(newest))
    for form in (PLAIN, NAMED):
        shown = _ask(ws, "show", form, session_id=session)
        names = [newest.name, newer.name, older.name]
        assert row_order(shown, names) == names, shown





def test_show_flagged_bit_only_when_the_row_has_labels(isolated_ws):
    ws = isolated_ws
    session = runtime_token("s")
    flagged = prose_dense()
    under = prose_under()
    quiet = zero_label_prose()
    if len(flagged.labels) <= 5:
        raise HarnessError("show label-cap fixture does not exceed five labels")
    if not under.labels:
        raise HarnessError("under-threshold fixture has no labels")
    flagged_path = _plant(ws, fresh_word() + ".md", flagged.text)
    under_path = _plant(ws, fresh_word() + ".md", under.text)
    quiet_path = _plant(ws, fresh_word() + ".md", quiet.text)
    for path in (flagged_path, under_path, quiet_path):
        _save(ws, path, session)
    shown = _ask(ws, "show", session_id=session)
    flagged_row = require_scored_row_shows(show_row(shown, flagged_path.name), flagged)
    assert flagged_row.clause == "flagged", flagged_row
    assert 1 <= len(flagged_row.labels) <= 5, flagged_row.labels
    assert all(label in flagged.labels for label in flagged_row.labels), flagged_row.labels
    under_row = require_scored_row_shows(show_row(shown, under_path.name), under)
    assert under_row.clause == "under", under_row
    assert 1 <= len(under_row.labels) <= 5
    assert all(label in under.labels for label in under_row.labels), under_row.labels
    quiet_row = require_scored_row_shows(show_row(shown, quiet_path.name), quiet)
    assert quiet_row.clause is None and quiet_row.labels == (), quiet_row


def test_show_names_the_window_only_when_truncated(isolated_ws):
    ws = isolated_ws
    session = runtime_token("s")
    exact = write_docx(ws, fresh_word() + ".docx", window_body(262144))
    longer = write_docx(ws, fresh_word() + ".docx", window_body(262145))
    for path in (exact, longer):
        _save(ws, path, session)
    shown = _ask(ws, "show", session_id=session)
    exact_body = show_row(shown, exact.name)
    longer_body = show_row(shown, longer.name)
    assert not parse_scored_row(exact_body).truncated
    assert not window_named(exact_body)
    assert parse_scored_row(longer_body).truncated
    assert first_window_only(longer_body)


def test_show_size_binary_and_failed_rows_differ(isolated_ws):
    ws = isolated_ws
    session = runtime_token("s")
    scored = prose_under()
    scored_path = _plant(ws, fresh_word() + ".md", scored.text)
    sized = _plant(ws, fresh_word() + ".md", "note")
    pad_file_to_size(sized, OVER_BOTH_512)
    archive = write_notebook(ws, fresh_word() + NOTEBOOK_EXT, markdown="note")
    pad_file_to_size(archive, OVER_BOTH_4MB)
    binary = write_plain(ws, fresh_word() + ".pdf", b"%PDF-1.1\n")
    missing = Path(ws.path) / (fresh_word() + ".md")
    for path in (scored_path, sized, archive, binary, missing):
        _save(ws, path, session)
    shown = _ask(ws, "show", session_id=session)
    require_scored_row_shows(show_row(shown, scored_path.name), scored)
    size_row = show_row(shown, sized.name)
    assert 512 in size_skip_figures(size_row), size_row
    archive_row = show_row(shown, archive.name)
    assert 4096 in size_skip_figures(archive_row), archive_row
    binary_row = show_row(shown, binary.name)
    assert is_binary_row(binary_row), binary_row
    failed_row = show_row(shown, missing.name)
    reason = failed_row_reason(failed_row)
    assert reason and re.search(r"[A-Za-z]{3,}", reason), failed_row
    for row in (size_row, archive_row, binary_row, failed_row):
        no_score_integers(row)
        assert not row.startswith("reads"), row


def test_show_omits_parent_path_and_body(isolated_ws):
    ws = isolated_ws
    session = runtime_token("s")
    parent_token = "parent" + fresh_word()
    body_token = "body" + fresh_word()
    folder = Path(ws.path) / parent_token
    folder.mkdir()
    path = write_plain(ws, f"{parent_token}/note.md", prose_under().text + " " + body_token)
    _save(ws, path, session)
    shown = _ask(ws, "show", session_id=session)
    assert "note.md" in shown
    assert parent_token not in shown
    assert body_token not in shown


def test_show_sessions_do_not_mix(isolated_ws):
    ws = isolated_ws
    first = runtime_token("a")
    second = runtime_token("b")
    path_a = _plant(ws, fresh_word() + ".md", prose_under().text)
    path_b = _plant(ws, fresh_word() + ".md", prose_dense().text)
    _save(ws, path_a, first)
    _save(ws, path_b, second)
    for form in (PLAIN, NAMED):
        shown_a = _ask(ws, "show", form, session_id=first)
        shown_b = _ask(ws, "show", form, session_id=second)
        assert path_a.name in shown_a and path_b.name not in shown_a
        assert path_b.name in shown_b and path_a.name not in shown_b


def test_show_omits_a_ledger_only_when_older_than_seven_days(isolated_ws):
    ws = isolated_ws
    day_ms = 24 * 3600 * 1000

    def shown_after_later_session(offset_ms):
        session = runtime_token("s")
        path = _plant(ws, fresh_word() + ".md", prose_under().text)
        _save(ws, path, session)
        ledgers = files_holding_basename(ws.config_dir, path.name)
        if len(ledgers) != 1:
            raise HarnessError(f"expected one ledger holding {path.name}, found {ledgers}")
        # The later session (its start and the show that follows) runs on one
        # clock, so the ledger's age is the same offset for every hook of that
        # session, whichever of them sweeps.
        with shared_sweep_clock() as (clock_ms, env):
            stamp_cutoff_offset(ledgers[0], clock_ms, offset_ms)
            require_hook_success(session_start(ws, env_updates=env))
            shown = _ask(ws, "show", session_id=session, env_updates=env)
        return path.name, shown

    # Signed offset from the seven-day cutoff on the sweep's clock.
    # Negative is younger, zero is exactly seven days, positive is older.
    # More than seven days is not listed by the later session.
    older_name, older_shown = shown_after_later_session(day_ms)
    assert older_name not in older_shown
    _empty_show(older_shown, older_name)
    just_past_name, just_past_shown = shown_after_later_session(1000)
    assert just_past_name not in just_past_shown
    _empty_show(just_past_shown, just_past_name)
    # Not more than seven days, including exactly seven days, stays listed.
    younger_name, younger_shown = shown_after_later_session(-day_ms)
    assert younger_name in younger_shown
    exact_name, exact_shown = shown_after_later_session(0)
    assert exact_name in exact_shown


def test_init_exports_a_portable_contract_and_a_prose_rule(isolated_ws):
    ws = isolated_ws
    outside = "Parish mill wheel stays in the margin."
    for word in BANNED_VOCABULARY:
        if standalone_word_present(outside, word):
            raise HarnessError("outside text collides with a banned word")
    _agents(ws).write_text(outside + "\n", encoding="utf-8")
    _store(ws, "full")
    _ask(ws, "init", cwd=str(ws.path))
    agents = _agents(ws).read_text(encoding="utf-8")
    rule = _rule(ws).read_text(encoding="utf-8")
    assert outside in agents
    require_exported_contract_omits_machine_identity(agents)
    body = cursor_rule_body(rule)
    assert states_prose_only_scope(body), body[:500]
    require_banned_list(body)
    require_not_source_code_scope(body)
    require_not_source_code_scope(rule)
    require_prose_glob_front_matter(rule)
    assert shows_integer(agents, 40)
    require_full_scoring(agents)
    require_not_source_code_scope(agents)
    assert not shows_integer(rule, 40)
    assert not has_light_tells(rule)
    # Contract: the shipped rule names neither detect.py nor any word
    # beginning with detect, so it carries no post-write detector step.
    assert not names_post_write_detector(rule), rule[:500]
    assert not has_cleanup_switch_finish(agents)
    _clear_export(ws)
    _ask(ws, "init", NAMED, cwd=str(ws.path))
    named_agents = _agents(ws).read_text(encoding="utf-8")
    require_exported_contract_omits_machine_identity(named_agents)
    require_not_source_code_scope(named_agents)


def _export_at(ws, level, env=None):
    _store(ws, level)
    _clear_export(ws)
    _ask(ws, "init", cwd=str(ws.path), env_updates=env)
    return _agents(ws).read_text(encoding="utf-8")


def test_init_lite_omits_detector_resolution(isolated_ws):
    ws = isolated_ws
    lite = _export_at(ws, "lite")
    full_unset = _export_at(ws, "full", {ENV_PLUGIN_ROOT: None})
    strict_unset = _export_at(ws, "strict", {ENV_PLUGIN_ROOT: None})
    full_set = _export_at(ws, "full")
    strict_set = _export_at(ws, "strict")
    for text in (lite, full_unset, strict_unset, full_set, strict_set):
        require_exported_contract_omits_machine_identity(text)
    assert not standalone_word_present(lite, "skills")
    assert not standalone_word_present(lite, "plugins")
    assert not standalone_word_present(lite, ENV_PLUGIN_ROOT)
    assert not resolution_lines(lite)
    assert not shows_integer(lite, 40)
    assert not has_light_tells(lite)
    assert not has_cleanup_switch_finish(lite)
    require_lite_omits_scoring(lite, full_unset)
    require_lite_omits_scoring(lite, full_set)
    # Contract: one resolution line names CLAUDE_PLUGIN_ROOT, skills and
    # plugins together, and export writes that same line whether or not
    # the variable is set.
    for text in (full_unset, strict_unset, full_set, strict_set):
        assert len(resolution_lines(text)) == 1, resolution_lines(text)
    assert resolution_lines(full_set) == resolution_lines(full_unset)
    assert resolution_lines(strict_set) == resolution_lines(strict_unset)
    assert has_cleanup_switch_finish(strict_unset)
    assert not has_cleanup_switch_finish(full_unset)
    assert has_cleanup_switch_finish(strict_set)
    assert not has_cleanup_switch_finish(full_set)
    require_full_scoring(full_unset)
    require_full_scoring(full_set)
    require_strict_cleanup(strict_unset, full_unset)
    require_strict_cleanup(strict_set, full_set)
    require_strict_clean_band_apart(strict_unset, lite)
    require_strict_clean_band_apart(strict_set, lite)


def test_init_second_time_does_not_duplicate_or_overwrite(isolated_ws):
    ws = isolated_ws
    outside = "Parish mill wheel stays in the margin."
    outside_text = outside + "\n"
    _agents(ws).write_text(outside_text, encoding="utf-8")
    _store(ws, "full")
    _ask(ws, "init", cwd=str(ws.path))
    rule_bytes = _rule(ws).read_bytes()
    first_body = _agents(ws).read_text(encoding="utf-8")
    delve_after_first = standalone_count(first_body, "delve")
    assert delve_after_first >= 1
    require_outside_text_in_place(first_body, outside_text)

    def section_left_once():
        body = _agents(ws).read_text(encoding="utf-8")
        assert outside in body
        require_outside_text_in_place(body, outside_text)
        assert standalone_count(body, "delve") == delve_after_first
        require_contract_section(body, word="delve", count=delve_after_first)
        return body

    for _ in range(2):
        reply = _ask(ws, "init", cwd=str(ws.path))
        section_left_once()
        assert _rule(ws).read_bytes() == rule_bytes
        assert already_for(reply, "AGENTS.md"), reply
        assert already_for(reply, "prosecheck.mdc"), reply

    def prepare_split(drop):
        _clear_export(ws)
        _agents(ws).write_text(outside_text, encoding="utf-8")
        _ask(ws, "init", cwd=str(ws.path))
        drop()
        return _ask(ws, "init", cwd=str(ws.path))

    def drop_rule():
        target = _rule(ws)
        target.unlink()
        assert not target.exists()

    def drop_agents():
        target = _agents(ws)
        target.unlink()
        assert not target.exists()

    for _ in range(2):
        reply = prepare_split(drop_rule)
        marker_body = section_left_once()
        assert outside in marker_body
        require_contract_section(marker_body, word="delve", count=delve_after_first)
        require_same_rule_bytes(_rule(ws), rule_bytes)
        require_prose_glob_front_matter(_rule(ws).read_text(encoding="utf-8"))
        assert already_for(reply, "AGENTS.md"), reply
    for _ in range(2):
        reply = prepare_split(drop_agents)
        rewritten = _agents(ws).read_text(encoding="utf-8")
        require_contract_section(
            rewritten,
            word="delve",
            count=delve_after_first,
        )
        require_same_rule_bytes(_rule(ws), rule_bytes)
        assert already_for(reply, "prosecheck.mdc"), reply
    _clear_export(ws)
    _agents(ws).write_text(outside_text, encoding="utf-8")
    _ask(ws, "init", cwd=str(ws.path))
    kept = _rule(ws).read_bytes()
    _agents(ws).unlink()
    assert not _agents(ws).exists()
    again = _ask(ws, "init", cwd=str(ws.path))
    assert already_for(again, "prosecheck.mdc"), again
    assert _rule(ws).read_bytes() == kept
    require_contract_section(
        _agents(ws).read_text(encoding="utf-8"),
        word="delve",
        count=delve_after_first,
    )


def test_init_off_writes_nothing_and_echoes_the_typed_form(isolated_ws):
    ws = isolated_ws
    _store(ws, "off")
    plain = _ask(ws, "init", cwd=str(ws.path))
    assert not _agents(ws).exists()
    assert not _rule(ws).exists()
    assert plain.strip()
    assert standalone_word_present(plain, "off")
    assert has_phrase(plain, "switched off"), plain
    assert re.search(rf"{re.escape(PLAIN)} on(?![A-Za-z:-])", plain), plain
    _store(ws, "full")
    _clear_export(ws)
    _ask(ws, "init", cwd=str(ws.path))
    agents_bytes = _agents(ws).read_bytes()
    rule_bytes = _rule(ws).read_bytes()
    _store(ws, "off")
    named = _ask(ws, "init", NAMED, cwd=str(ws.path))
    assert _agents(ws).read_bytes() == agents_bytes
    assert _rule(ws).read_bytes() == rule_bytes
    assert NAMED in named
    assert has_phrase(named, "switched off"), named
    assert re.search(rf"{re.escape(NAMED)} on(?![A-Za-z:-])", named), named


# Opens that mean this path is not a file the process can use. Anything
# else (a full disk, a killed probe) is not "blocked".
_BLOCKED_OPEN = frozenset(
    {
        errno.EACCES,
        errno.EPERM,
        errno.ENOENT,
        errno.ENOTDIR,
        errno.EISDIR,
        errno.EROFS,
    }
)


def _owner_can_open(path: Path, kind: str) -> bool:
    """Whether this process can read or write *path*.

    A write that creates a missing path is removed. Opening an existing
    file for write does not change its bytes. A permission or path error
    is the blocked result. Any other failure is not treated as blocked.
    """
    try:
        if kind == "read":
            path.read_bytes()
            return True
        if path.exists():
            fd = os.open(path, os.O_WRONLY)
            os.close(fd)
            return True
        path.write_text("x", encoding="utf-8")
    except OSError as exc:
        if exc.errno in _BLOCKED_OPEN:
            return False
        raise HarnessError(
            f"init target probe failed for {path}: {exc}"
        ) from exc
    path.unlink()
    return True


def _child_can_open(path: Path, kind: str) -> bool:
    """A fresh child can read or write *path*.

    The child is the same kind of exec the hook will be. A child that
    still opens the path means the hook can too. A write that creates a
    missing path is removed. A killed child is not a permission result.
    """
    existed = path.exists()
    script = (
        "import errno, os, pathlib, sys\n"
        "path = pathlib.Path(sys.argv[1])\n"
        "kind = sys.argv[2]\n"
        "blocked = {errno.EACCES, errno.EPERM, errno.ENOENT, errno.ENOTDIR, errno.EISDIR, errno.EROFS}\n"
        "try:\n"
        "    if kind == 'read':\n"
        "        path.read_bytes()\n"
        "    elif path.exists():\n"
        "        fd = os.open(path, os.O_WRONLY)\n"
        "        os.close(fd)\n"
        "    else:\n"
        "        path.write_text('x', encoding='utf-8')\n"
        "except OSError as exc:\n"
        "    if exc.errno in blocked:\n"
        "        sys.exit(1)\n"
        "    sys.stderr.write(repr(exc))\n"
        "    sys.exit(2)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, str(path), kind],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=5,
        check=False,
    )
    created = (not existed) and path.exists()
    if created:
        path.unlink()
    if completed.returncode < 0:
        raise HarnessError(
            "init target probe was killed: "
            f"signal={-completed.returncode} stderr={completed.stderr[:200]!r}"
        )
    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False
    raise HarnessError(
        "init target probe failed: "
        f"code={completed.returncode} stderr={completed.stderr[:200]!r}"
    )


@contextmanager
def _init_target_blocked(path: Path, *, read: bool = False, write: bool = False):
    """*path* is one a hook child cannot read or cannot write.

    A mode bit this process can still use is not that target. When the
    owner can still open the file, hook children are started without the
    override that ignores mode bits, and the child probe is what decides.
    The hook has to run inside this window.
    """
    if not read and not write:
        raise HarnessError(f"init target {path} names no blocked open")
    limited = False
    try:
        owner_slips = (read and _owner_can_open(path, "read")) or (
            write and _owner_can_open(path, "write")
        )
        if owner_slips:
            _hold_root_mode_bits()
            limited = True
        if read and _child_can_open(path, "read"):
            raise HarnessError(f"{path} stayed readable for a hook child")
        if write and _child_can_open(path, "write"):
            raise HarnessError(f"{path} stayed writable for a hook child")
        yield
    finally:
        if limited:
            _release_root_mode_bits()


def test_init_reports_when_it_cannot_write(isolated_ws):
    ws = isolated_ws
    _store(ws, "full")
    success = _ask(ws, "init", cwd=str(ws.path))
    assert _agents(ws).is_file() and _rule(ws).is_file()
    _clear_export(ws)
    agents = _agents(ws)
    agents.write_text("keep\n", encoding="utf-8")
    os.chmod(agents, 0)
    try:
        with _init_target_blocked(agents, read=True, write=True):
            reply = _ask(ws, "init", cwd=str(ws.path))
    finally:
        os.chmod(agents, 0o644)
    assert success not in reply
    assert has_phrase(reply, "cannot read") or has_phrase(reply, "cannot write"), reply
    assert "delve" not in agents.read_text(encoding="utf-8")
    _clear_export(ws)
    agents.write_text("keep\n", encoding="utf-8")
    os.chmod(agents, 0o444)
    try:
        with _init_target_blocked(agents, write=True):
            reply = _ask(ws, "init", cwd=str(ws.path))
    finally:
        os.chmod(agents, 0o644)
    assert success not in reply
    assert has_phrase(reply, "cannot write"), reply
    assert agents.read_text(encoding="utf-8") == "keep\n"
    _clear_export(ws)
    cursor = Path(ws.path) / ".cursor"
    cursor.write_text("not a directory\n", encoding="utf-8")
    rule = _rule(ws)
    with _init_target_blocked(rule, write=True):
        reply = _ask(ws, "init", cwd=str(ws.path))
    assert success not in reply
    assert has_phrase(reply, "cannot write"), reply
    assert not rule.exists()


def test_stats_prefers_the_named_transcript_else_the_newest(isolated_ws):
    ws = isolated_ws
    _store(ws, "strict")
    named = _write_jsonl(
        Path(ws.path),
        "named.jsonl",
        [_assistant(OUTSIDE, 410, 820)],
    )
    projects = Path(ws.config_dir) / "projects" / runtime_token("p")
    older = _write_jsonl(projects, "old.jsonl", [_assistant(OUTSIDE, 510, 910)])
    # znew sorts after old, so the first name in the folder is the older file.
    newer = _write_jsonl(projects, "znew.jsonl", [_assistant(OUTSIDE, 610, 710)])
    age_file(older, days=1)
    listed = sorted(path.name for path in projects.glob("*.jsonl"))
    assert listed and listed[0] == older.name
    assert newer.name in listed and newer.name != listed[0]
    assert newer.stat().st_mtime > older.stat().st_mtime
    reply = _ask(ws, "stats", transcript_path=str(named))
    named_again = _ask(ws, "stats", NAMED, transcript_path=str(named))
    for text in (reply, named_again):
        assert stats_values(text) == {"turns": 1, "output": 410, "cache": 820}, text
        assert stats_level(text) == "strict", text
    _store(ws, "lite")
    unnamed = _ask(ws, "stats")
    assert stats_values(unnamed) == {"turns": 1, "output": 610, "cache": 710}, unnamed
    assert stats_level(unnamed) == "lite", unnamed


def test_stats_counts_assistant_turns_and_keeps_the_two_token_fields_distinct(isolated_ws):
    ws = isolated_ws
    _store(ws, "strict")
    mixed_entries = [
        _assistant("The clerk lists the mill fees.", 251, 820),
        _assistant("The clerk lists the bridge fees.", 263, 840),
        {
            "type": "user",
            "message": {
                "usage": {
                    "output_tokens": 990,
                    "cache_read_input_tokens": 980,
                },
                "content": [{"type": "text", "text": "ignore this usage"}],
            },
        },
    ]
    # Shared message id, plus one assistant entry with no identifier.
    shared_entries = [
        _assistant("The clerk lists the mill fees.", 450, 860, mid="same"),
        _assistant("The clerk lists the bridge fees.", 450, 860, mid="same"),
        _assistant("The clerk lists the gate fees.", 120, 140),
    ]
    mixed = _write_jsonl(Path(ws.path), "mixed.jsonl", mixed_entries)
    shared_tokens = _write_jsonl(
        Path(ws.path), "shared-tokens.jsonl", shared_entries
    )
    reply = _ask(ws, "stats", transcript_path=str(mixed))
    shared_token_reply = _ask(ws, "stats", transcript_path=str(shared_tokens))
    assert stats_values(reply) == {
        "turns": 2,
        "output": 251 + 263,
        "cache": 820 + 840,
    }, reply
    assert stats_values(shared_token_reply) == {
        "turns": 2,
        "output": 450 + 120,
        "cache": 860 + 140,
    }, shared_token_reply
    left = (OUTSIDE + " ") * 2
    right = "It is crucial to delve into the tapestry. " * 4
    combined = _agreed_score(left, right)
    shared = _write_jsonl(
        Path(ws.path),
        "shared.jsonl",
        [
            _assistant(left, 450, 860, mid="same"),
            _assistant(right, 450, 860, mid="same"),
        ],
    )
    shared_reply = _ask(ws, "stats", transcript_path=str(shared))
    assert stats_values(shared_reply)["turns"] == 1, shared_reply
    assert stats_session_score(shared_reply) == combined, shared_reply
    first = _write_jsonl(
        Path(ws.path),
        "swap-a.jsonl",
        [_assistant(OUTSIDE, 410, 820)],
    )
    second = _write_jsonl(
        Path(ws.path),
        "swap-b.jsonl",
        [_assistant(OUTSIDE, 820, 410)],
    )
    left_reply = _ask(ws, "stats", transcript_path=str(first))
    right_reply = _ask(ws, "stats", transcript_path=str(second))
    assert stats_values(left_reply) == {"turns": 1, "output": 410, "cache": 820}
    assert stats_values(right_reply) == {"turns": 1, "output": 820, "cache": 410}


def test_stats_scores_only_the_trimmed_unfenced_tail(isolated_ws):
    ws = isolated_ws
    level = "strict"
    _store(ws, level)
    output_total = 1720
    cache_total = 3450
    totals = {"turns": 1, "output": output_total, "cache": cache_total}
    outside = (OUTSIDE + " ") * 2
    assert len(outside) > 200
    inside = prose_dense().text
    fenced = outside + "\n```\n" + inside + "\n```\n"
    expected = measure_text(_prose_slice(fenced)).score
    included = measure_text(outside + "\n" + inside).score
    assert expected != included
    for variant in (outside, outside + " ", outside + "\n"):
        if measure_text(variant).score != measure_text(outside).score:
            raise HarnessError("a trailing space changes the outside score")
    fenced_path = _write_jsonl(
        Path(ws.path),
        "fenced.jsonl",
        [_assistant(fenced, output_total, cache_total)],
    )
    fenced_reply = _ask(ws, "stats", transcript_path=str(fenced_path))
    assert stats_values(fenced_reply) == totals, fenced_reply
    assert stats_session_score(fenced_reply) == expected, fenced_reply
    body = window_body(200)
    padded = "\n\n" + body + "\n\n"
    assert len(padded) > 200 and len(padded.strip()) == 200
    short = _write_jsonl(
        Path(ws.path),
        "short.jsonl",
        [_assistant(padded, output_total, cache_total)],
    )
    short_reply = _ask(ws, "stats", transcript_path=str(short))
    assert stats_values(short_reply) == totals, short_reply
    assert stats_level(short_reply) == level, short_reply
    assert stats_session_score(short_reply) is None, short_reply
    longer_body = body + "x"
    assert len(longer_body.strip()) == 201
    long = _write_jsonl(
        Path(ws.path),
        "long.jsonl",
        [_assistant(longer_body, output_total, cache_total)],
    )
    long_reply = _ask(ws, "stats", transcript_path=str(long))
    long_score = measure_text(_prose_slice(longer_body)).score
    assert stats_session_score(long_reply) == long_score, long_reply
    suffix = ("The mill wheel turns after the rain. " * 2000)[:40000]
    assert len(suffix) == 40000
    prefix = prose_dense().text
    assert measure_text(suffix).score != measure_text(prefix + suffix).score
    tail = _write_jsonl(
        Path(ws.path),
        "tail.jsonl",
        [_assistant(prefix + suffix, output_total, cache_total)],
    )
    tail_reply = _ask(ws, "stats", transcript_path=str(tail))
    assert stats_session_score(tail_reply) == measure_text(suffix).score, tail_reply


def test_stats_non_assistant_text_does_not_move_the_session_prose_score(isolated_ws):
    ws = isolated_ws
    level = "strict"
    _store(ws, level)
    output_total = 1720
    cache_total = 3450
    excluded_output = 990
    excluded_cache = 980
    totals = {"turns": 1, "output": output_total, "cache": cache_total}
    kind = "note" + "".join(ch for ch in fresh_word() if ch.isalpha())
    short = window_body(180)
    carried = prose_dense().text.strip()
    base = (OUTSIDE + " ") * 2
    if "```" in short or "```" in carried or "```" in base:
        raise HarnessError("stats prose fixtures must not contain a code fence")
    if not 100 < len(_prose_slice(short)) <= 200:
        raise HarnessError("short assistant text has to sit below the 200-character threshold")
    if len(_prose_slice(carried)) <= 200 or len(_prose_slice(base)) <= 200:
        raise HarnessError("the long texts have to clear 200 characters")
    if len(_prose_slice(short + "\n\n" + carried)) <= 200:
        raise HarnessError("adding the long text has to clear 200 characters")
    base_score = measure_text(_prose_slice(base)).score
    joined_scores = {
        measure_text(_prose_slice(sep.join((base, carried)))).score
        for sep in ("\n\n", "\n", " ")
    }
    if base_score in joined_scores:
        raise HarnessError(
            "adding the carried text has to move the score off the assistant "
            f"slice; base={base_score} joined={joined_scores}"
        )

    def no_score(reply):
        assert stats_values(reply) == totals, reply
        assert stats_level(reply) == level, reply
        assert stats_session_score(reply) is None, reply

    below = _write_jsonl(
        Path(ws.path),
        "below.jsonl",
        [
            _assistant(short, output_total, cache_total),
            _other_row(kind, "", excluded_output, excluded_cache),
        ],
    )
    with_carried = _write_jsonl(
        Path(ws.path),
        "carried.jsonl",
        [
            _assistant(short, output_total, cache_total),
            _other_row(kind, carried, excluded_output, excluded_cache),
        ],
    )
    no_score(_ask(ws, "stats", transcript_path=str(below)))
    no_score(_ask(ws, "stats", transcript_path=str(with_carried)))
    as_assistant = _write_jsonl(
        Path(ws.path),
        "as-assistant.jsonl",
        [_assistant(carried, output_total, cache_total)],
    )
    assistant_reply = _ask(ws, "stats", transcript_path=str(as_assistant))
    assert stats_values(assistant_reply) == totals, assistant_reply
    assert stats_session_score(assistant_reply) is not None, assistant_reply
    scoring = _write_jsonl(
        Path(ws.path),
        "scoring.jsonl",
        [
            _assistant(base, output_total, cache_total),
            _other_row(kind, "", excluded_output, excluded_cache),
        ],
    )
    scoring_with = _write_jsonl(
        Path(ws.path),
        "scoring-with.jsonl",
        [
            _assistant(base, output_total, cache_total),
            _other_row(kind, carried, excluded_output, excluded_cache),
        ],
    )
    scoring_reply = _ask(ws, "stats", transcript_path=str(scoring))
    scoring_with_reply = _ask(ws, "stats", transcript_path=str(scoring_with))
    assert stats_values(scoring_reply) == totals, scoring_reply
    assert stats_values(scoring_with_reply) == totals, scoring_with_reply
    scoring_score = stats_session_score(scoring_reply)
    assert scoring_score is not None, scoring_reply
    assert stats_session_score(scoring_with_reply) == scoring_score, scoring_with_reply


def test_stats_missing_transcript_has_no_counts(isolated_ws):
    ws = isolated_ws
    level = "strict"
    _store(ws, level)
    readable = _write_jsonl(
        Path(ws.path),
        "readable.jsonl",
        [
            _assistant("The clerk lists the mill fees.", 860, 1725),
            _assistant("The clerk lists the bridge fees.", 860, 1725),
        ],
    )
    readable_reply = _ask(ws, "stats", transcript_path=str(readable))
    assert stats_values(readable_reply) == {"turns": 2, "output": 1720, "cache": 3450}
    # A readable transcript with no assistant entry still names the three
    # quantities, and each of them is 0.
    empty = _write_jsonl(
        Path(ws.path),
        "empty.jsonl",
        [
            {
                "type": "user",
                "message": {
                    "content": [{"type": "text", "text": "The clerk asks the fee."}],
                },
            }
        ],
    )
    empty_reply = _ask(ws, "stats", transcript_path=str(empty))
    assert stats_values(empty_reply) == {"turns": 0, "output": 0, "cache": 0}, empty_reply
    name = fresh_word()
    if not re.search(r"\d", name):
        name += "7"
    missing = Path(ws.path) / (name + ".jsonl")
    reply = _ask(ws, "stats", transcript_path=str(missing))
    assert reply.strip()
    # Contract: no assistant-turn line and no token-total line.
    assert stats_values(reply) == {}, reply


def test_shipped_command_file_forwards_arguments(isolated_ws):
    ws = isolated_ws
    found = command_registrations()
    assert found
    for _path, body in found:
        # The body's next token after the command is the argument slot,
        # not one of the twelve subcommands written into the template.
        rest = body[len(PLAIN) :].strip()
        assert rest
        slot = rest.split()[0]
        assert slot not in SUBCOMMANDS
        clear_stored_level(ws)
        assert_one_level_line(_status(ws), "full")
        invoke_shipped_command(ws, "strict", body=body)
        assert_one_level_line(_status(ws), "strict")
        word = fresh_word()
        reply = invoke_shipped_command(ws, word, body=body)
        assert reports_word_as_unknown(reply, word), reply
        assert_one_level_line(_status(ws), "strict")


def test_commands_open_no_socket(isolated_ws):
    ws = isolated_ws
    path = _plant(ws, fresh_word() + ".md", scored_prose().text)
    transcript = _write_jsonl(
        Path(ws.path),
        "net.jsonl",
        [_assistant(OUTSIDE, 410, 820)],
    )
    with hook_connect_observer() as observer:
        env = observer.env_updates
        _ask(ws, f"check {path}", env_updates=env)
        _ask(ws, "doctor", env_updates=env)
        _ask(ws, "stats", env_updates=env, transcript_path=str(transcript))
        _clear_export(ws)
        _ask(ws, "init", cwd=str(ws.path), env_updates=env)
        assert observer.n_connects == 0
        observer.fire_positive_control("127.0.0.1", 9)
